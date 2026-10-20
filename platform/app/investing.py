"""Depiqo Invest: tenants invest their own money at a licensed investment partner.

Separation from the deposit is the first rule. A deposit is never invested and never used as
collateral; Invest has its own tables, keyed by the person (users.id) and never by an organisation.
The only bridge is the tenant's explicit choice, before a release, to receive their share of the
deposit on their own investment account (invest_payout_choices).

Depiqo gives no advice. The partner owns the client relationship: identity checks, the
appropriateness assessment, custody on the tenant's name, order execution and statements. Depiqo
refers, shows the overview and charges a service fee that the partner collects.

The partner sits behind InvestmentPartner, chosen with INVEST_PARTNER and failing closed exactly
like the bank (see partners.bank()). Instructions go through an outbox (invest_instructions) with
idempotency keys; the partner reports through events (webhook with HMAC, idempotent per event id).

Money is in cents. Units carry 4 decimals (units_1e4 = units x 10000), prices are euro x 10000
(price_1e4). Rounding is explicit: units are rounded down, amounts half up to the cent unless stated.
"""
import json
import math
import random
import secrets
import sqlite3
import threading
from datetime import date, timedelta

from flask import current_app

from . import db, i18n, notify
from .util import dumps, now, now_iso, parse_date, today, valid_iban

NO_PARTNER_MESSAGE = "Er is geen beleggingspartner gekoppeld."
MIN_ORDER_CENTS = 2500
QUESTIONNAIRE_VERSION = "2026-10"
DEPIQO_TERMS_VERSION = "depiqo-invest-2026-10-19"
DEFAULT_FEE_BPS = 25             # Depiqo service fee: 0,25% per year over the value of the investments
TRANSACTION_COST_BPS = 0         # sandbox partner charges no transaction costs; a real partner may
MICRO = 1_000_000                # fee accrual in millionths of a cent


SEPARATION_TEXT = ("Je borg staat op de geblokkeerde borgrekening, of waar je verhuurder hem bewaart. Hij wordt nooit belegd en nooit "
                   "als onderpand gebruikt. Beleggen doe je met je eigen geld, op een aparte rekening op jouw naam.")
RISK_TEXT = ("Beleggen brengt risico met zich mee. De waarde van je belegging kan dalen en je kunt geld verliezen, ook je inleg. "
             "Het depositogarantiestelsel geldt niet voor beleggingen.")


class InvestError(Exception):
    """A user-facing problem: shown as a message, nothing is changed."""


class InvestUnavailable(InvestError):
    """No partner, or the partner may not act on this account. Never retried automatically."""


class InvestRateLimited(InvestError):
    """Too many wrong codes (0.6.1): the same counters as the second login step."""


class InvestPartnerError(InvestError):
    """A temporary failure at the partner; the dispatcher retries."""


# ================================================================ funds and model portfolios

# Generic fund names, no real products. drift and vol are yearly, in the sandbox price model only.
# Ongoing charges (lopende kosten) are taken inside the fund: the sandbox price is net of them.
FUNDS = {
    "geldmarkt": {"name": "Geldmarktfonds euro", "asset": "Geldmarkt", "ocf_bps": 10, "drift": 0.022, "vol": 0.004},
    "obligaties_kort": {"name": "Kortlopende obligaties euro", "asset": "Obligaties", "ocf_bps": 15, "drift": 0.025, "vol": 0.025},
    "obligaties_wereld": {"name": "Wereldwijde obligaties (euro-afgedekt)", "asset": "Obligaties", "ocf_bps": 18, "drift": 0.03, "vol": 0.05},
    "aandelen_wereld": {"name": "Wereldwijde aandelen", "asset": "Aandelen", "ocf_bps": 22, "drift": 0.07, "vol": 0.15},
}

PORTFOLIOS = {
    "defensief": {
        "label": "Defensief", "risk": 2,
        "summary": "80% geldmarkt en kortlopende obligaties, 20% wereldwijde aandelen.",
        "weights": {"geldmarkt": 4000, "obligaties_kort": 4000, "aandelen_wereld": 2000},
        "scenarios": {"gunstig": 0.05, "neutraal": 0.02, "ongunstig": -0.06},
    },
    "neutraal": {
        "label": "Neutraal", "risk": 4,
        "summary": "50% obligaties, 50% wereldwijde aandelen.",
        "weights": {"obligaties_kort": 2500, "obligaties_wereld": 2500, "aandelen_wereld": 5000},
        "scenarios": {"gunstig": 0.12, "neutraal": 0.04, "ongunstig": -0.15},
    },
    "offensief": {
        "label": "Offensief", "risk": 6,
        "summary": "90% wereldwijde aandelen, 10% obligaties.",
        "weights": {"obligaties_wereld": 1000, "aandelen_wereld": 9000},
        "scenarios": {"gunstig": 0.20, "neutraal": 0.06, "ongunstig": -0.25},
    },
}
SCENARIO_LABELS = {"gunstig": "Gunstig", "neutraal": "Neutraal", "ongunstig": "Ongunstig"}


def portfolio_ocf_bps(code):
    """Weighted ongoing charges of a model portfolio, in hundredths of a basis point precision kept as float bps."""
    p = PORTFOLIOS[code]
    return sum(FUNDS[f]["ocf_bps"] * w for f, w in p["weights"].items()) / 10000


def round_half_up(numerator, denominator):
    """Integer division rounded half up (for non-negative values), the rounding rule for money here."""
    return (2 * numerator + denominator) // (2 * denominator)


def costs(amount_cents, portfolio, fee_bps=None):
    """Costs in euro cents before any commitment, assuming the value stays equal to the amount.
    Returns dict with per-year and 3-year figures per component and in total."""
    fee_bps = DEFAULT_FEE_BPS if fee_bps is None else fee_bps
    ocf = portfolio_ocf_bps(portfolio)
    service_1 = round_half_up(amount_cents * fee_bps, 10000)
    fund_1 = round_half_up(int(round(amount_cents * ocf * 100)), 1_000_000)
    tx = round_half_up(amount_cents * TRANSACTION_COST_BPS, 10000)
    return {
        "amount": amount_cents, "fee_bps": fee_bps, "ocf_bps": ocf, "tx_bps": TRANSACTION_COST_BPS,
        "service_1y": service_1, "fund_1y": fund_1, "tx": tx,
        "total_1y": service_1 + fund_1 + tx,
        "service_3y": 3 * service_1, "fund_3y": 3 * fund_1,
        "total_3y": 3 * service_1 + 3 * fund_1 + tx,
        "pct_per_year": (fee_bps + ocf) / 100,
    }


def scenarios(amount_cents, portfolio, fee_bps=None):
    """Illustrative outcomes, not forecasts: a yearly return per scenario, compounded, minus the costs."""
    c = costs(amount_cents, portfolio, fee_bps)
    out = []
    for key, r in PORTFOLIOS[portfolio]["scenarios"].items():
        y1 = int(round(amount_cents * (1 + r))) - c["total_1y"]
        y3 = int(round(amount_cents * (1 + r) ** 3)) - c["total_3y"]
        out.append({"key": key, "label": SCENARIO_LABELS[key], "rate": r, "y1": y1, "y3": y3,
                    "y1_result": y1 - amount_cents, "y3_result": y3 - amount_cents})
    return out


# ================================================================ sandbox price series

SERIES_START = date(2023, 1, 2)
_series = {}
_series_lock = threading.Lock()


def _extend(fund, upto_index):
    state = _series.get(fund)
    if state is None:
        state = {"rng": random.Random(f"depiqo-sandbox-{fund}"), "prices": [1_000_000]}  # 100,0000 euro on SERIES_START
        _series[fund] = state
    f = FUNDS[fund]
    mu = (f["drift"] - f["ocf_bps"] / 10000) / 365  # net of ongoing charges: fund costs are inside the price
    sigma = f["vol"] / math.sqrt(365)
    prices = state["prices"]
    while len(prices) <= upto_index:
        step = state["rng"].gauss(mu - sigma * sigma / 2, sigma)
        prices.append(max(1, int(round(prices[-1] * math.exp(step)))))


def price_1e4(fund, day):
    """Deterministic daily price (euro x 10000) of a sandbox fund. Same input, same price, in every process."""
    day = parse_date(day)
    idx = max(0, (day - SERIES_START).days)
    with _series_lock:
        _extend(fund, idx)
        return _series[fund]["prices"][idx]


def value_cents(units_1e4, price):
    """Value of a holding, rounded half up to the cent."""
    return round_half_up(units_1e4 * price, 1_000_000)


# ================================================================ partner interface

class InvestmentPartner:
    """Contract for an investment partner (a licensed investment firm). The partner is the source of
    truth for accounts, cash, positions, prices and statements. Depiqo sends instructions with an
    idempotency key and records what the partner reports through events."""
    name = "abstract"
    display_name = "Beleggingspartner"
    available = True
    is_sandbox = False
    client_money_iban = None
    terms_version = None

    def assess_appropriateness(self, user, answers):
        """-> dict(result 'passend'|'niet_passend', score, reasons). The partner's assessment (MiFID)."""
        raise NotImplementedError

    def open_account(self, user, account, idempotency_key):
        """-> dict(external_id, status 'pending'|'active', provider_ref). Activation later via account.activated."""
        raise NotImplementedError

    def deposit_instructions(self, account):
        """-> dict(iban, beneficiary, reference). Read only."""
        raise NotImplementedError

    def place_order(self, account, order, idempotency_key):
        """order: dict(side, portfolio, amount_cents, sell_all). -> dict(provider_ref). Confirmed by order.executed."""
        raise NotImplementedError

    def withdraw(self, account, amount_cents, iban, idempotency_key):
        """-> dict(provider_ref). Confirmed by withdrawal.completed."""
        raise NotImplementedError

    def charge_fee(self, account, amount_cents, period, idempotency_key):
        """Collect Depiqo's service fee from the client account. -> dict(provider_ref). Confirmed by fee.charged."""
        raise NotImplementedError

    def price(self, fund, day):
        """Closing price (euro x 10000) for a day. Read only."""
        raise NotImplementedError

    def verify_account_holder(self, iban, name):
        """-> dict(match: bool, holder). A real partner checks the account holder name (for example with a
        name check at the receiving bank) before it pays out to a new account."""
        raise NotImplementedError

    def today(self):
        return today()


class DisabledInvest(InvestmentPartner):
    name = "none"
    display_name = "Geen beleggingspartner"
    available = False

    def __init__(self, reason=NO_PARTNER_MESSAGE):
        self.reason = reason

    def _refuse(self, *args, **kwargs):
        raise InvestUnavailable(self.reason)

    assess_appropriateness = open_account = deposit_instructions = place_order = withdraw = charge_fee = price = _refuse
    verify_account_holder = _refuse


def _sandbox_client_iban():
    bban = "DPQI" + "0000005005"
    digits = "".join(str(int(ch, 36)) for ch in bban + "NL00")
    return f"NL{98 - int(digits) % 97:02d}{bban}"


class SandboxInvest(InvestmentPartner):
    """Simulated partner. Executes orders, withdrawals and fees when its clock moves forward
    (tick), at that day's price. Uses Depiqo's shadow ledger as its own book; a real partner keeps its own."""
    name = "sandbox"
    display_name = "Sandbox-beleggingspartner"
    is_sandbox = True
    client_money_iban = _sandbox_client_iban()
    terms_version = "sandbox-partner-2026-10"
    failures = set()   # kinds that fail, for tests of retries

    def _remembered(self, key):
        row = db.one("SELECT response_json FROM sandbox_requests WHERE idempotency_key = ?", ("inv:" + key,))
        return json.loads(row["response_json"]) if row else None

    def _remember(self, key, kind, response):
        db.run("INSERT OR IGNORE INTO sandbox_requests (idempotency_key, kind, response_json, created_at) VALUES (?, ?, ?, ?)",
               ("inv:" + key, kind, dumps(response), now_iso()))
        return self._remembered(key)

    def _maybe_fail(self, kind):
        if kind in self.failures:
            raise InvestPartnerError("Sandbox: de beleggingspartner is niet bereikbaar (gesimuleerde storing).")

    def assess_appropriateness(self, user, answers):
        return assess(answers)

    def open_account(self, user, account, idempotency_key):
        known = self._remembered(idempotency_key)
        if known:
            return known
        self._maybe_fail("open")
        return self._remember(idempotency_key, "open", {"external_id": "sbi_" + secrets.token_hex(8), "status": "pending",
                                                        "provider_ref": "sbi_open_" + secrets.token_hex(4)})

    def deposit_instructions(self, account):
        return {"iban": self.client_money_iban, "beneficiary": f"{self.display_name}, klantengeld",
                "reference": account["reference"]}

    def _ack(self, kind, key):
        known = self._remembered(key)
        if known:
            return known
        self._maybe_fail(kind)
        return self._remember(key, kind, {"provider_ref": f"sbi_{kind}_" + secrets.token_hex(4)})

    def place_order(self, account, order, idempotency_key):
        return self._ack("order", idempotency_key)

    def withdraw(self, account, amount_cents, iban, idempotency_key):
        return self._ack("withdraw", idempotency_key)

    def charge_fee(self, account, amount_cents, period, idempotency_key):
        return self._ack("fee", idempotency_key)

    def price(self, fund, day):
        return price_1e4(fund, day)

    def verify_account_holder(self, iban, name):
        return {"match": True, "holder": name}  # sandbox: every account is in the tenant's own name

    def today(self):
        offset = db.scalar("SELECT offset_days FROM invest_sandbox_clock WHERE id = 1") or 0
        return today() + timedelta(days=offset)

    # ---- the sandbox side: produces the events a real partner would send
    def event_activated(self, account):
        return {"event_id": f"sbi_act_{account['id']}", "external_id": account["external_id"]}

    def event_deposit(self, account, amount_cents, ref=None):
        return {"event_id": "sbi_dep_" + secrets.token_hex(8), "external_id": account["external_id"],
                "amount_cents": amount_cents, "ref": ref or "dep_" + secrets.token_hex(6), "day": self.today().isoformat()}

    def settle(self, day, kinds=("order", "withdraw", "fee"), same_day=False):
        """Executes acknowledged instructions at the price of `day`: orders and withdrawals from earlier days
        (the next price), fees also on the day itself when same_day. Returns event (type, payload) pairs."""
        events = []
        ph = ",".join("?" * len(kinds))
        rows = db.all_("SELECT i.*, a.external_id FROM invest_instructions i JOIN invest_accounts a ON a.id = i.account_id "
                       f"WHERE i.provider = ? AND i.status = 'acknowledged' AND i.kind IN ({ph}) "
                       f"AND i.created_day {'<=' if same_day else '<'} ? ORDER BY i.id", (self.name, *kinds, day.isoformat()))
        for i in rows:
            p = json.loads(i["payload_json"])
            base = {"event_id": f"sbi_done_{i['id']}", "external_id": i["external_id"], "ref": i["idempotency_key"],
                    "day": day.isoformat()}
            if i["kind"] == "order":
                fills = self._order_fills(i["account_id"], p, day)
                if fills is None:
                    events.append(("order.failed", {**base, "reason": "Onvoldoende saldo of posities bij de partner."}))
                else:
                    events.append(("order.executed", {**base, "fills": fills}))
            elif i["kind"] == "withdraw":
                if cash_cents(i["account_id"]) >= p["amount_cents"]:
                    events.append(("withdrawal.completed", {**base, "amount_cents": p["amount_cents"]}))
                else:
                    events.append(("withdrawal.failed", {**base, "reason": "Onvoldoende saldo."}))
            else:
                cash = max(cash_cents(i["account_id"]), 0)
                shortfall = p["amount_cents"] - cash
                fills = (self._sell_fills(i["account_id"], shortfall, day, all_units=False) or []) if shortfall > 0 else []
                proceeds = sum(f["amount_cents"] for f in fills)
                # never more than the cash plus what the sale brought in; the rest is charged later
                events.append(("fee.charged", {**base, "amount_cents": min(p["amount_cents"], cash + proceeds), "fills": fills}))
        return events

    def _order_fills(self, account_id, p, day):
        if p["side"] == "buy":
            if cash_cents(account_id) < p["amount_cents"]:
                return None
            fills = []
            for fund, amount in allocate(p["amount_cents"], p["portfolio"]):
                px = self.price(fund, day)
                units = amount * 1_000_000 // px              # rounded down: never more than the money buys
                spent = value_cents(units, px)
                if units:
                    fills.append({"fund": fund, "units_1e4": units, "price_1e4": px, "amount_cents": spent})
            return fills
        return self._sell_fills(account_id, p["amount_cents"], day, all_units=bool(p.get("sell_all")))

    def _sell_fills(self, account_id, amount_cents, day, all_units):
        held = units_by_fund(account_id)
        vals = {f: value_cents(u, self.price(f, day)) for f, u in held.items() if u > 0}
        total = sum(vals.values())
        if not total:
            return [] if all_units else None
        if all_units or amount_cents >= total:
            return [{"fund": f, "units_1e4": -held[f], "price_1e4": self.price(f, day), "amount_cents": vals[f]} for f in vals]
        fills = []
        for f, v in vals.items():
            px = self.price(f, day)
            part = -(-amount_cents * v // total)                   # this fund's share, rounded up: the parts cover the amount
            units = min(held[f], -(-part * 1_000_000 // px))      # rounded up, so the proceeds cover the amount
            if units:
                fills.append({"fund": f, "units_1e4": -units, "price_1e4": px, "amount_cents": value_cents(units, px)})
        return fills


INVEST_ADAPTERS = {"sandbox": SandboxInvest}


def partner():
    """The configured investment partner or a DisabledInvest. Never falls back to the sandbox."""
    cfg = current_app.config
    name = (cfg.get("INVEST_PARTNER") or "").strip().lower()
    if not name:
        return DisabledInvest()
    adapter = INVEST_ADAPTERS.get(name)
    if adapter is None:
        return DisabledInvest(f"{NO_PARTNER_MESSAGE} De ingestelde partner '{name}' bestaat niet.")
    if adapter.is_sandbox and (not cfg.get("SANDBOX") or cfg.get("ENV_NAME") == "production"):
        return DisabledInvest(f"{NO_PARTNER_MESSAGE} De sandbox staat uit.")
    return adapter()


def partner_for(account):
    p = partner()
    if not p.available:
        raise InvestUnavailable(p.reason)
    if account["provider"] != p.name:
        raise InvestUnavailable(f"Deze beleggingsrekening hoort bij partner '{account['provider']}', niet bij '{p.name}'.")
    return p


def invest_day():
    """Today for Invest: the partner's business day (the sandbox clock can be moved forward)."""
    p = partner()
    return p.today() if p.available else today()


def terms(p=None):
    """The two texts a tenant accepts before an account is opened, each with its version."""
    p = p or partner()
    return {
        "partner": {"name": p.display_name, "version": p.terms_version,
                    "text": f"Ik ga akkoord met de klantvoorwaarden van {p.display_name} (versie {p.terms_version}). De partner opent de rekening, "
                            "bewaart mijn beleggingen op mijn naam en voert mijn orders uit."},
        "depiqo": {"version": DEPIQO_TERMS_VERSION,
                   "text": f"Ik ga akkoord met de voorwaarden van Depiqo Invest (versie {DEPIQO_TERMS_VERSION}): Depiqo geeft geen advies, toont "
                           f"mijn overzicht en rekent {_pct(fee_bps())} servicekosten per jaar over de waarde van mijn beleggingen, die de partner "
                           "maandelijks int."},
    }


def role_text(p=None):
    p = p or partner()
    return f"Depiqo verwijst door en toont je overzicht. Beleggen gebeurt bij {p.display_name}, een vergunde beleggingsonderneming."


# ================================================================ settings and visibility

def fee_bps():
    raw = db.scalar("SELECT value FROM staff_settings WHERE key = 'invest_fee_bps'")
    try:
        return int(raw) if raw is not None else DEFAULT_FEE_BPS
    except ValueError:
        return DEFAULT_FEE_BPS


def set_fee_bps(bps, user_id):
    """The rate for new accounts. Existing accounts keep the rate they agreed to: the new rate is stored as a
    proposal (pending_fee_bps) and only applies after the tenant accepts it, from that day on. Returns the
    number of existing accounts that received a notice."""
    if not isinstance(bps, int) or bps < 0 or bps > 200:
        raise InvestError("Kies een servicevergoeding tussen 0% en 2% per jaar.")
    from .partners import send_mail
    with db.transaction():
        db.run("INSERT INTO staff_settings (key, value, updated_at, updated_by) VALUES ('invest_fee_bps', ?, ?, ?) "
               "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at, updated_by = excluded.updated_by",
               (str(bps), now_iso(), user_id))
        db.run("UPDATE invest_accounts SET pending_fee_bps = NULL, pending_fee_notified_at = NULL WHERE fee_rate_bps = ?", (bps,))
        rows = db.all_("SELECT a.*, u.email, u.name, u.language FROM invest_accounts a JOIN users u ON u.id = a.user_id "
                       "WHERE a.status IN ('pending', 'active') AND a.fee_rate_bps IS NOT NULL AND a.fee_rate_bps != ? "
                       "AND (a.pending_fee_bps IS NULL OR a.pending_fee_bps != ?)", (bps, bps))
        for a in rows:
            db.run("UPDATE invest_accounts SET pending_fee_bps = ?, pending_fee_notified_at = ? WHERE id = ?", (bps, now_iso(), a["id"]))
            lang = i18n.norm(a["language"])  # 0.6.0: in the user's language
            send_mail(a["email"], i18n.t("mail.fee_change.subject", lang),
                      i18n.t("mail.fee_change.body", lang, name=a["name"], new_bps=bps, old_bps=a["fee_rate_bps"]) + "\n")
            notify.notify(a["user_id"], "invest_fee_change", {"new_bps": bps, "old_bps": a["fee_rate_bps"]}, notify.INVEST_LINK)
    return len(rows)


def org_enabled_for(user_id):
    return bool(db.scalar("SELECT 1 FROM tenants t JOIN organizations o ON o.id = t.org_id WHERE t.user_id = ? AND o.invest_enabled = 1 LIMIT 1",
                          (user_id,)))


def _dt(value):
    from .util import datetime_nl
    return datetime_nl(value)


def _pct(bps):
    return f"{bps / 100:.2f}%".replace(".", ",")


def has_account(user_id):
    return bool(db.scalar("SELECT 1 FROM invest_accounts WHERE user_id = ? AND status IN ('pending', 'active', 'closed')", (user_id,)))


def visibility(user_id):
    """'hidden', 'unavailable' (no partner) or 'available'. Someone who already has an account keeps access
    (read, sell, withdraw, statements) when the organisation switches Invest off; new accounts, new purchases
    and doorbeleggen need an organisation that offers it."""
    if not user_id or not (org_enabled_for(user_id) or has_account(user_id)):
        return "hidden"
    return "available" if partner().available else "unavailable"


def require_offered(user_id):
    if not org_enabled_for(user_id):
        raise InvestError("Je verhuurder biedt Beleggen niet meer aan. Nieuwe aankopen kunnen niet; verkopen, opnemen en je overzichten wel.")


# ================================================================ appropriateness (kennis- en ervaringstoets)

QUESTIONS = [
    {"key": "experience", "text": "Hoe vaak heb je de afgelopen drie jaar belegd?",
     "options": [("nooit", "Nooit", 0), ("soms", "Een paar keer", 1), ("regelmatig", "Regelmatig", 2)]},
    {"key": "funds", "text": "Wat is een beleggingsfonds?",
     "options": [("pot", "Een pot geld van veel beleggers, die samen in aandelen of obligaties belegt", 2),
                 ("spaar", "Een spaarrekening met een vaste rente", 0), ("weet_niet", "Weet ik niet", 0)]},
    {"key": "risk", "text": "Wat kan er gebeuren met de waarde van een belegging?",
     "options": [("beide", "Ze kan stijgen en dalen. Ik kan geld verliezen", 2),
                 ("stijgt", "Ze blijft gelijk of stijgt", 0), ("weet_niet", "Weet ik niet", 0)]},
    {"key": "spread", "text": "Wat doet spreiden over veel aandelen en obligaties?",
     "options": [("kleiner", "Het risico op een groot verlies door één bedrijf wordt kleiner", 2),
                 ("weg", "Het risico verdwijnt helemaal", 0), ("weet_niet", "Weet ik niet", 0)]},
    {"key": "horizon", "text": "Hoe lang kun je dit geld missen?",
     "options": [("kort", "Minder dan een jaar", 0), ("middel", "Een tot drie jaar", 1), ("lang", "Langer dan drie jaar", 2)]},
    {"key": "loss", "text": "Kun je een verlies dragen zonder dat je huur of vaste lasten in gevaar komen?",
     "options": [("ja", "Ja", 2), ("nee", "Nee", 0)]},
    {"key": "drop", "text": "Je belegging daalt in een jaar 20%. Wat doe je waarschijnlijk?",
     "options": [("wachten", "Ik wacht rustig af", 2), ("twijfel", "Ik twijfel en verkoop misschien een deel", 1),
                 ("verkopen", "Ik verkoop alles", 0)]},
    {"key": "goal", "text": "Wat is je doel?",
     "options": [("opbouwen", "Vermogen opbouwen voor later", 2), ("kort", "Geld voor uitgaven binnen een jaar, zoals een nieuwe borg", 0),
                 ("snel", "Snel veel winst maken", 0)]},
]
PASS_SCORE = 10


def assess(answers):
    """The appropriateness outcome. Not passend when a key condition fails or the score is too low.
    Returns dict(result, score, reasons) with reasons in plain Dutch."""
    score, reasons = 0, []
    for q in QUESTIONS:
        opts = {k: pts for k, _, pts in q["options"]}
        if answers.get(q["key"]) not in opts:
            raise InvestError("Beantwoord alle vragen.")
        score += opts[answers[q["key"]]]
    if answers["risk"] != "beide":
        reasons.append("Je gaf aan dat een belegging niet in waarde kan dalen. Dat kan wel.")
    if answers["loss"] != "ja":
        reasons.append("Een verlies kan je huur of vaste lasten in gevaar brengen.")
    if answers["horizon"] == "kort":
        reasons.append("Je hebt dit geld binnen een jaar nodig. Beleggen is voor geld dat je langer kunt missen.")
    if answers["goal"] != "opbouwen":
        reasons.append("Je doel past niet bij beleggen voor de langere termijn.")
    if score < PASS_SCORE and not reasons:
        reasons.append("Je kennis en ervaring met beleggen zijn nog beperkt.")
    return {"result": "niet_passend" if reasons else "passend", "score": score, "reasons": reasons}


def record_appropriateness(user_id, answers):
    p = partner()
    if not p.available:
        raise InvestUnavailable(p.reason)
    clean = {q["key"]: answers.get(q["key"]) for q in QUESTIONS}
    outcome = p.assess_appropriateness({"id": user_id}, clean)  # the partner's call, outside a transaction
    with db.transaction():
        aid = db.run("INSERT INTO invest_appropriateness (user_id, provider, questionnaire_version, answers_json, score, result, reasons_json, created_at) "
                     "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                     (user_id, p.name, QUESTIONNAIRE_VERSION, dumps(clean), outcome["score"], outcome["result"], dumps(outcome["reasons"]), now_iso()))
        acct = account_for_user(user_id)
        if acct and acct["status"] == "draft":
            db.run("UPDATE invest_accounts SET appropriateness_id = ? WHERE id = ?", (aid, acct["id"]))
        elif not acct:
            db.run("INSERT INTO invest_accounts (user_id, provider, reference, status, appropriateness_id, created_at) VALUES (?, ?, ?, 'draft', ?, ?)",
                   (user_id, p.name, _new_reference(), aid, now_iso()))
    return db.one("SELECT * FROM invest_appropriateness WHERE id = ?", (aid,))


def confirm_warning(user_id):
    a = latest_appropriateness(user_id)
    if not a or a["result"] != "niet_passend":
        raise InvestError("Er is geen waarschuwing om te bevestigen.")
    db.run("UPDATE invest_appropriateness SET warning_confirmed_at = ? WHERE id = ? AND warning_confirmed_at IS NULL", (now_iso(), a["id"]))


def latest_appropriateness(user_id):
    return db.one("SELECT * FROM invest_appropriateness WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,))


def may_continue(appr):
    return bool(appr) and (appr["result"] == "passend" or bool(appr["warning_confirmed_at"]))


# ================================================================ accounts

def _new_reference():
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "INV-" + "".join(secrets.choice(alphabet) for _ in range(8))


def account_for_user(user_id):
    return db.one("SELECT * FROM invest_accounts WHERE user_id = ?", (user_id,))


def choose_portfolio(user_id, code):
    if code not in PORTFOLIOS:
        raise InvestError("Kies een portefeuille.")
    acct = account_for_user(user_id)
    if not acct or not may_continue(latest_appropriateness(user_id)):
        raise InvestError("Doe eerst de kennis- en ervaringstoets.")
    if acct["status"] != "draft":
        raise InvestError("Je rekening is al geopend. Wisselen van portefeuille doe je in je overzicht.")
    db.run("UPDATE invest_accounts SET portfolio = ? WHERE id = ?", (code, acct["id"]))


def open_account(user_id, accept_partner, accept_depiqo):
    """Records both terms (versioned, timestamped) and the agreed service fee, and sends the open instruction."""
    p = partner()
    if not p.available:
        raise InvestUnavailable(p.reason)
    require_offered(user_id)
    acct = account_for_user(user_id)
    if not acct or acct["status"] != "draft" or not acct["portfolio"]:
        raise InvestError("Kies eerst een portefeuille.")
    appr = latest_appropriateness(user_id)
    if not may_continue(appr):
        raise InvestError("Doe eerst de kennis- en ervaringstoets.")
    if not (accept_partner and accept_depiqo):
        raise InvestError("Ga akkoord met de voorwaarden van de partner en van Depiqo.")
    with db.transaction():
        changed = db.get_db().execute(
            "UPDATE invest_accounts SET status = 'pending', provider = ?, appropriateness_id = ?, terms_partner_version = ?, terms_partner_at = ?, "
            "terms_depiqo_version = ?, terms_depiqo_at = ?, opened_at = ?, fee_rate_bps = ?, fee_rate_accepted_at = ? WHERE id = ? AND status = 'draft'",
            (p.name, appr["id"], p.terms_version, now_iso(), DEPIQO_TERMS_VERSION, now_iso(), now_iso(), fee_bps(), now_iso(), acct["id"])).rowcount
        if changed != 1:
            raise InvestError("Je rekening wordt al geopend.")
        iid = _enqueue(acct["id"], p.name, "open", {"reference": acct["reference"]}, f"invest-open:{acct['id']}")
    dispatch(ids=[iid])
    return account_for_user(user_id)


def activate_sandbox_account(account_id):
    """Sandbox console: the partner approves the account (as after its own identity check)."""
    p = partner()
    acct = db.one("SELECT * FROM invest_accounts WHERE id = ?", (account_id,))
    if not acct or not p.is_sandbox or acct["provider"] != p.name:
        raise InvestError("Alleen een sandboxrekening kan hier worden geactiveerd.")
    if acct["status"] != "pending" or not acct["external_id"]:
        raise InvestError("Deze rekening wacht niet op activering.")
    return handle_event(p.name, "account.activated", p.event_activated(acct))


# ================================================================ ledger read models

def cash_cents(account_id, as_of=None):
    if as_of:
        return db.scalar("SELECT COALESCE(SUM(amount_cents), 0) FROM invest_transactions WHERE account_id = ? AND day <= ?",
                         (account_id, str(as_of)))
    return db.scalar("SELECT COALESCE(SUM(amount_cents), 0) FROM invest_transactions WHERE account_id = ?", (account_id,))


def units_by_fund(account_id, as_of=None):
    sql = "SELECT fund, SUM(units_1e4) AS u FROM invest_fills WHERE account_id = ?"
    params = [account_id]
    if as_of:
        sql += " AND day <= ?"
        params.append(str(as_of))
    return {r["fund"]: r["u"] for r in db.all_(sql + " GROUP BY fund", params) if r["u"]}


def reserved_cents(account_id):
    """Cash promised to pending buys, withdrawals and fee charges (not available for a new order)."""
    buys = db.scalar("SELECT COALESCE(SUM(amount_cents), 0) FROM invest_orders WHERE account_id = ? AND side = 'buy' AND status = 'pending'",
                     (account_id,))
    outs = 0
    for r in db.all_("SELECT payload_json FROM invest_instructions WHERE account_id = ? AND kind IN ('withdraw', 'fee') "
                     "AND status IN ('pending', 'sent', 'acknowledged')", (account_id,)):
        outs += json.loads(r["payload_json"])["amount_cents"]
    return buys + outs


def fee_owed_cents(account):
    """Service fee accrued but not charged yet, rounded up to the cent, plus a remainder carried over."""
    return -(-(account["fee_accrued_micro"] or 0) // MICRO) + (account["fee_carry_cents"] or 0)


def available_cents(account_id):
    """What a buy or a withdrawal may use: cash minus reservations and the fee that is already owed."""
    acct = db.one("SELECT * FROM invest_accounts WHERE id = ?", (account_id,))
    return max(cash_cents(account_id) - reserved_cents(account_id) - fee_owed_cents(acct), 0)


def positions(account_id, day=None):
    p = partner()
    day = day or invest_day()
    out = []
    for fund, units in sorted(units_by_fund(account_id, day).items()):
        px = p.price(fund, day) if p.available else price_1e4(fund, day)
        out.append({"fund": fund, "name": FUNDS[fund]["name"], "asset": FUNDS[fund]["asset"], "units_1e4": units, "price_1e4": px,
                    "value": value_cents(units, px)})
    return out


def flows(account_id, as_of=None):
    """Net money put in: deposits and payouts in, minus withdrawals."""
    sql = "SELECT COALESCE(SUM(amount_cents), 0) FROM invest_transactions WHERE account_id = ? AND kind IN ('deposit', 'payout_in', 'withdrawal')"
    if as_of:
        return db.scalar(sql + " AND day <= ?", (account_id, str(as_of)))
    return db.scalar(sql, (account_id,))


def value_at(account_id, day):
    return cash_cents(account_id, day) + sum(value_cents(u, price_1e4(f, day)) for f, u in units_by_fund(account_id, day).items())


def summary(account):
    account = db.one("SELECT * FROM invest_accounts WHERE id = ?", (account["id"],)) or account
    day = invest_day()
    pos = positions(account["id"], day)
    cash = cash_cents(account["id"])
    invested_value = sum(p["value"] for p in pos)
    total = cash + invested_value
    net_in = flows(account["id"])
    result = total - net_in
    fees = -db.scalar("SELECT COALESCE(SUM(amount_cents), 0) FROM invest_transactions WHERE account_id = ? AND kind = 'fee'", (account["id"],))
    reserved = reserved_cents(account["id"])
    owed = fee_owed_cents(account)
    pending_sell = db.scalar("SELECT COALESCE(SUM(amount_cents), 0) FROM invest_orders WHERE account_id = ? AND side = 'sell' AND status = 'pending'",
                             (account["id"],))
    return {"day": day, "total": total, "cash": cash, "available": max(cash - reserved - owed, 0), "reserved": reserved + owed,
            "invested_value": invested_value, "net_in": net_in, "result": result,
            "result_pct": (result * 100 / net_in) if net_in > 0 else None, "fees": fees, "positions": pos,
            "sellable": max(invested_value - pending_sell, 0), "accrued_fee": owed,
            "fee_rate_bps": account["fee_rate_bps"] if account["fee_rate_bps"] is not None else fee_bps()}


def history(account_id, points=90, since=None):
    """(day, value_cents, net_in_cents) samples from the first movement (or `since`, if later) to today, for the chart."""
    first = db.scalar("SELECT MIN(day) FROM (SELECT day FROM invest_transactions WHERE account_id = ? UNION ALL "
                      "SELECT day FROM invest_fills WHERE account_id = ?)", (account_id, account_id))
    if not first:
        return []
    start, end = parse_date(first), invest_day()
    if since and since > start:
        start = min(since, end)
    span = max((end - start).days, 1)
    step = max(1, math.ceil(span / points))
    txs = db.all_("SELECT day, amount_cents, kind FROM invest_transactions WHERE account_id = ? ORDER BY day, id", (account_id,))
    fills = db.all_("SELECT day, fund, units_1e4 FROM invest_fills WHERE account_id = ? ORDER BY day, id", (account_id,))
    out, cash, net, units, ti, fi = [], 0, 0, {}, 0, 0
    days = [start + timedelta(days=i) for i in range(0, span, step)] + [end]
    for d in days:
        ds = d.isoformat()
        while ti < len(txs) and txs[ti]["day"] <= ds:
            cash += txs[ti]["amount_cents"]
            if txs[ti]["kind"] in ("deposit", "payout_in", "withdrawal"):
                net += txs[ti]["amount_cents"]
            ti += 1
        while fi < len(fills) and fills[fi]["day"] <= ds:
            units[fills[fi]["fund"]] = units.get(fills[fi]["fund"], 0) + fills[fi]["units_1e4"]
            fi += 1
        out.append((d, cash + sum(value_cents(u, price_1e4(f, d)) for f, u in units.items() if u), net))
    return out


def chart(account_id, width=340, height=150):
    """A server-rendered SVG line chart (no script, CSP-safe). Returns dict for the template or None."""
    pts = history(account_id)
    if len(pts) < 2:
        return None
    pad_l, pad_r, pad_t, pad_b = 4, 4, 10, 18
    vals = [v for _, v, _ in pts] + [n for _, _, n in pts]
    lo, hi = min(vals), max(vals)
    if hi == lo:
        hi = lo + 100
    span_days = max((pts[-1][0] - pts[0][0]).days, 1)

    def xy(d, v):
        x = pad_l + (d - pts[0][0]).days * (width - pad_l - pad_r) / span_days
        y = pad_t + (hi - v) * (height - pad_t - pad_b) / (hi - lo)
        return f"{x:.1f},{y:.1f}"
    value_line = " ".join(xy(d, v) for d, v, _ in pts)
    net_line = " ".join(xy(d, n) for d, _, n in pts)
    area = f"{pad_l},{height - pad_b} " + value_line + f" {width - pad_r},{height - pad_b}"
    return {"width": width, "height": height, "value": value_line, "net": net_line, "area": area,
            "start": pts[0][0], "end": pts[-1][0], "hi": hi, "lo": lo, "last": pts[-1][1], "base": height - pad_b}


def orders(account_id, limit=30):
    return db.all_("SELECT * FROM invest_orders WHERE account_id = ? ORDER BY id DESC LIMIT ?", (account_id, limit))


def transactions(account_id, limit=40):
    return db.all_("SELECT * FROM invest_transactions WHERE account_id = ? ORDER BY day DESC, id DESC LIMIT ?", (account_id, limit))


WITHDRAWAL_LABELS = {"confirmed": "Uitgevoerd", "failed": "Mislukt"}


def withdrawal_view(r):
    """A withdrawal instruction as the tenant sees it."""
    return json.loads(r["payload_json"]) | {"id": r["id"], "status": r["status"], "day": r["created_day"], "created_at": r["created_at"],
                                            "label": WITHDRAWAL_LABELS.get(r["status"], "Wordt verwerkt")}


def pending_withdrawals(account_id):
    """Withdrawals the tenant asked for, with their tenant-facing status (the last ten)."""
    return [withdrawal_view(r) for r in
            db.all_("SELECT * FROM invest_instructions WHERE account_id = ? AND kind = 'withdraw' ORDER BY id DESC LIMIT 10", (account_id,))]


# ================================================================ orders, withdrawals

def allocate(amount_cents, portfolio):
    """Split an amount over the funds of a model portfolio: rounded down per fund, the remainder to the largest weight."""
    weights = PORTFOLIOS[portfolio]["weights"]
    parts = {f: amount_cents * w // 10000 for f, w in weights.items()}
    largest = max(weights, key=weights.get)
    parts[largest] += amount_cents - sum(parts.values())
    return [(f, a) for f, a in parts.items() if a > 0]


def _require_active(account):
    if not account or account["status"] != "active":
        raise InvestError("Je beleggingsrekening is nog niet actief.")
    return partner_for(account)


def place_order(account, side, amount_cents, sell_all=False, purpose="order", switch_to=None, portfolio=None):
    """The cash and position checks run inside the same IMMEDIATE transaction as the reservation, so two
    requests can never spend the same money."""
    _require_active(account)
    if side not in ("buy", "sell"):
        raise InvestError("Onbekende order.")
    if side == "buy" and purpose == "order":
        require_offered(account["user_id"])
    with db.transaction():
        acct = db.one("SELECT * FROM invest_accounts WHERE id = ?", (account["id"],))
        if acct["pending_switch"] and purpose == "order":
            raise InvestError("Je portefeuille wordt nog gewisseld. Wacht tot dat klaar is.")
        s = summary(acct)
        if side == "buy":
            if not amount_cents or amount_cents < MIN_ORDER_CENTS:
                raise InvestError("Je koopt voor minimaal € 25.")
            if amount_cents > s["available"]:
                raise InvestError("Er staat niet genoeg geld vrij op je beleggingsrekening. Stort eerst bij.")
        else:
            if not s["sellable"]:
                raise InvestError("Je hebt nog geen beleggingen om te verkopen.")
            if sell_all:
                amount_cents = s["sellable"]
            elif not amount_cents or amount_cents < MIN_ORDER_CENTS:
                raise InvestError("Je verkoopt voor minimaal € 25, of kies alles verkopen.")
            elif amount_cents > s["sellable"]:
                raise InvestError("Dat is meer dan de waarde van je beleggingen.")
        portfolio = portfolio or acct["portfolio"]
        oid = db.run("INSERT INTO invest_orders (account_id, side, portfolio, amount_cents, sell_all, purpose, switch_to, status, created_day, created_at) "
                     "VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)",
                     (acct["id"], side, portfolio, amount_cents, 1 if sell_all else 0, purpose, switch_to, s["day"].isoformat(), now_iso()))
        iid = _enqueue(acct["id"], acct["provider"], "order",
                       {"side": side, "portfolio": portfolio, "amount_cents": amount_cents, "sell_all": bool(sell_all)},
                       f"invest-order:{oid}", order_id=oid)
    dispatch(ids=[iid])
    return db.one("SELECT * FROM invest_orders WHERE id = ?", (oid,))


def switch_portfolio(account, new_code, confirmed):
    """Change of portfolio = sell everything, then buy the new portfolio with the proceeds. The account keeps
    its portfolio until the sale executed and the new purchase was placed (pending_switch until then)."""
    _require_active(account)
    require_offered(account["user_id"])
    if new_code not in PORTFOLIOS or new_code == account["portfolio"]:
        raise InvestError("Kies een andere portefeuille.")
    if not confirmed:
        raise InvestError("Bevestig dat je alles verkoopt en daarna de nieuwe portefeuille koopt.")
    if db.scalar("SELECT COUNT(*) FROM invest_orders WHERE account_id = ? AND status = 'pending'", (account["id"],)) or account["pending_switch"]:
        raise InvestError("Er loopt nog een order. Wacht tot die is uitgevoerd.")
    if not summary(account)["sellable"]:
        db.run("UPDATE invest_accounts SET portfolio = ?, switch_note = NULL WHERE id = ?", (new_code, account["id"]))  # nothing to sell
        return
    db.run("UPDATE invest_accounts SET pending_switch = ?, switch_note = NULL WHERE id = ?", (new_code, account["id"]))
    try:
        place_order(account, "sell", 0, sell_all=True, purpose="switch_sell", switch_to=new_code)
    except InvestError:
        db.run("UPDATE invest_accounts SET pending_switch = NULL WHERE id = ?", (account["id"],))
        raise


def _switch_failed(account_id, note):
    db.run("UPDATE invest_accounts SET pending_switch = NULL, switch_note = ? WHERE id = ?", (note, account_id))


def continue_switches(account_id=None):
    """After the sale of a switch: place the purchase of the new portfolio, then (only then) change the portfolio.
    Safe to call often; a purchase that could not be placed is tried again on the next call."""
    sql = "SELECT * FROM invest_accounts WHERE pending_switch IS NOT NULL AND status = 'active'"
    params = ()
    if account_id:
        sql += " AND id = ?"
        params = (account_id,)
    done = 0
    for acct in db.all_(sql, params):
        sell = db.one("SELECT * FROM invest_orders WHERE account_id = ? AND purpose = 'switch_sell' ORDER BY id DESC LIMIT 1", (acct["id"],))
        if not sell or sell["status"] == "pending":
            continue
        if sell["status"] == "failed":
            _switch_failed(acct["id"], "Wisselen is niet gelukt: de verkoop ging niet door. Je portefeuille is niet veranderd.")
            continue
        if db.scalar("SELECT 1 FROM invest_orders WHERE account_id = ? AND purpose = 'switch_buy' AND id > ?", (acct["id"], sell["id"])):
            continue
        amount = min(sell["executed_amount_cents"] or 0, available_cents(acct["id"]))
        target = acct["pending_switch"]
        if amount < MIN_ORDER_CENTS:
            db.run("UPDATE invest_accounts SET portfolio = ?, pending_switch = NULL, switch_note = ? WHERE id = ?",
                   (target, "De opbrengst was te klein om opnieuw te beleggen. Je geld staat vrij op je rekening.", acct["id"]))
            continue
        try:
            place_order(acct, "buy", amount, purpose="switch_buy", portfolio=target)
        except InvestError:
            continue  # partner not reachable now: tried again later, the switch stays pending
        db.run("UPDATE invest_accounts SET portfolio = ?, pending_switch = NULL, switch_note = NULL WHERE id = ?", (target, acct["id"]))
        done += 1
    return done


def withdraw(account, amount_cents):
    """Only to the tenant's own registered account, once that registration is usable (see register_own_iban)."""
    p = _require_active(account)
    if not amount_cents or amount_cents <= 0:
        raise InvestError("Vul een bedrag in.")
    with db.transaction():
        acct = db.one("SELECT * FROM invest_accounts WHERE id = ?", (account["id"],))
        if not acct["own_iban"]:
            raise InvestError("Registreer eerst je eigen rekeningnummer.")
        if acct["own_iban_usable_from"] and acct["own_iban_usable_from"] > now_iso():
            from .util import datetime_nl
            raise InvestError(f"Je kunt je nieuwe rekeningnummer gebruiken vanaf {datetime_nl(acct['own_iban_usable_from'])}. "
                              "Dat is een veiligheidsmaatregel.")
        if amount_cents > available_cents(acct["id"]):
            raise InvestError("Je kunt alleen geld opnemen dat vrij op je beleggingsrekening staat. Verkoop eerst.")
        iid = _enqueue(acct["id"], p.name, "withdraw", {"amount_cents": amount_cents, "iban": acct["own_iban"]},
                       f"invest-withdraw:{acct['id']}:{secrets.token_hex(6)}")
    dispatch(ids=[iid])
    return iid


COOLING_OFF = timedelta(days=7)


def register_own_iban(account, user, iban, code=None):
    """Registers or changes the tenant's own account for withdrawals. With two-factor authentication on, a fresh
    code makes it usable at once; without, it is usable after a cooling-off period. The tenant gets an email
    either way. The partner checks the account holder name (the sandbox accepts the tenant's own name)."""
    from . import mfa
    from .partners import send_mail
    p = _require_active(account)
    iban = (iban or "").replace(" ", "").upper()
    if not valid_iban(iban):
        raise InvestError("Dat rekeningnummer (IBAN) klopt niet.")
    if iban == account["own_iban"]:
        raise InvestError("Dit rekeningnummer staat al geregistreerd.")
    if any(w["status"] in ("pending", "sent", "acknowledged") for w in pending_withdrawals(account["id"])):
        raise InvestError("Er loopt nog een opname. Wijzig je rekeningnummer daarna.")
    if mfa.enabled(user):
        # 0.6.1: only a TOTP code (a recovery code is never consumed here), checked for format first, and rate
        # limited with the same counters as the second login step (5 wrong codes per 15 minutes).
        if not mfa.is_totp_format(code):
            raise InvestError("Vul de code van 6 cijfers uit je authenticator-app in.")
        from flask import has_request_context
        from .security import attempt_done, attempt_start, client_ip
        attempt = attempt_start("mfa:" + user["email"], "mfa:" + (client_ip() if has_request_context() else ""))
        if not attempt:
            raise InvestRateLimited("Te veel verkeerde codes. Wacht 15 minuten en probeer het opnieuw.")
        ok = mfa.verify_totp(user, code)
        attempt_done(attempt, ok)
        if not ok:
            raise InvestError("Vul een geldige code uit je authenticator-app in.")
        usable = now_iso()
    else:
        usable = (now() + COOLING_OFF).isoformat(timespec="seconds")
    check = p.verify_account_holder(iban, user["name"])
    if not check.get("match"):
        raise InvestError("De partner kon niet bevestigen dat deze rekening op jouw naam staat.")
    db.run("UPDATE invest_accounts SET own_iban = ?, own_iban_registered_at = ?, own_iban_usable_from = ?, own_iban_holder = ? WHERE id = ?",
           (iban, now_iso(), usable, check.get("holder"), account["id"]))
    lang = i18n.user_lang(user)  # 0.6.0: in the user's language
    when = i18n.t("mail.iban_now", lang) if usable <= now_iso() else i18n.t("mail.iban_from", lang, usable_at=usable)
    send_mail(user["email"], i18n.t("mail.iban_changed.subject", lang),
              i18n.t("mail.iban_changed.body", lang, name=user["name"], iban_short=f"{iban[:4]} ... {iban[-4:]}", when=when) + "\n")
    return usable


# ================================================================ outbox and dispatcher

STALE_SENT = timedelta(minutes=10)


def _enqueue(account_id, provider, kind, payload, key, order_id=None):
    try:
        return db.run("INSERT INTO invest_instructions (account_id, provider, kind, order_id, idempotency_key, payload_json, status, created_at, created_day) "
                      "VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)",
                      (account_id, provider, kind, order_id, key, dumps(payload), now_iso(), invest_day().isoformat()))
    except sqlite3.IntegrityError:
        return db.scalar("SELECT id FROM invest_instructions WHERE idempotency_key = ?", (key,))


def dispatch(ids=None, limit=500):
    summary_ = {"sent": 0, "retry": 0, "failed": 0, "skipped": 0, "blocked": None}
    if db.get_db().in_transaction or not current_app.config.get("DISPATCH_INLINE", True) and ids:
        return summary_
    p = partner()
    if not p.available:
        summary_["blocked"] = p.reason
        return summary_
    stale = (now() - STALE_SENT).isoformat(timespec="seconds")
    sql = "SELECT * FROM invest_instructions WHERE (status = 'pending' OR (status = 'sent' AND sent_at < ?))"
    params = [stale]
    if ids:
        sql += f" AND id IN ({','.join('?' * len(ids))})"
        params += list(ids)
    for row in db.all_(sql + " ORDER BY id LIMIT ?", (*params, limit)):
        summary_[_dispatch_one(p, row, stale)] += 1
    return summary_


def _fail(instr, message):
    """The dispatcher gives up. The tenant sees the order or withdrawal as failed; that is final."""
    with db.transaction():
        changed = db.get_db().execute("UPDATE invest_instructions SET status = 'failed', last_error = ? WHERE id = ? AND status = 'sent'",
                                      (message[:300], instr["id"])).rowcount
        if changed and instr["order_id"]:
            db.run("UPDATE invest_orders SET status = 'failed', error = ? WHERE id = ? AND status = 'pending'", (message[:200], instr["order_id"]))
        if changed and instr["kind"] == "open":
            db.run("UPDATE invest_accounts SET status = 'draft' WHERE id = ? AND status = 'pending'", (instr["account_id"],))
    if changed and instr["order_id"]:
        continue_switches(instr["account_id"])
    return "failed" if changed else "skipped"


def _dispatch_one(p, instr, stale):
    max_attempts = int(current_app.config.get("MAX_INSTRUCTION_ATTEMPTS", 5))
    with db.transaction():
        claimed = db.get_db().execute("UPDATE invest_instructions SET status = 'sent', attempts = attempts + 1, sent_at = ? "
                                      "WHERE id = ? AND (status = 'pending' OR (status = 'sent' AND sent_at < ?))",
                                      (now_iso(), instr["id"], stale)).rowcount
    if claimed != 1:
        return "skipped"
    instr = db.one("SELECT * FROM invest_instructions WHERE id = ?", (instr["id"],))
    account = db.one("SELECT * FROM invest_accounts WHERE id = ?", (instr["account_id"],))
    payload = json.loads(instr["payload_json"])
    if instr["provider"] != p.name:
        return _fail(instr, f"Opdracht hoort bij partner '{instr['provider']}', niet bij '{p.name}'.")
    try:
        if instr["kind"] == "open":
            resp = p.open_account({"id": account["user_id"]}, account, instr["idempotency_key"])
        elif instr["kind"] == "order":
            resp = p.place_order(account, payload, instr["idempotency_key"])
        elif instr["kind"] == "withdraw":
            resp = p.withdraw(account, payload["amount_cents"], payload["iban"], instr["idempotency_key"])
        else:
            resp = p.charge_fee(account, payload["amount_cents"], payload["period"], instr["idempotency_key"])
    except InvestUnavailable as exc:
        return _fail(instr, str(exc))
    except InvestPartnerError as exc:
        if instr["attempts"] >= max_attempts:
            return _fail(instr, f"{exc} (na {instr['attempts']} pogingen)")
        db.run("UPDATE invest_instructions SET status = 'pending', last_error = ? WHERE id = ? AND status = 'sent'", (str(exc)[:300], instr["id"]))
        return "retry"
    activate = None
    with db.transaction():
        if db.scalar("SELECT status FROM invest_instructions WHERE id = ?", (instr["id"],)) != "sent":
            return "skipped"
        if instr["kind"] == "open":
            db.run("UPDATE invest_instructions SET status = 'confirmed', confirmed_at = ?, provider_ref = ? WHERE id = ?",
                   (now_iso(), resp.get("provider_ref"), instr["id"]))
            db.run("UPDATE invest_accounts SET external_id = ? WHERE id = ?", (resp["external_id"], account["id"]))
            if resp.get("status") == "active" or (p.is_sandbox and _identity_verified(account["user_id"])):
                activate = account["id"]
        else:
            db.run("UPDATE invest_instructions SET status = 'acknowledged', provider_ref = ?, last_error = NULL WHERE id = ? AND status = 'sent'",
                   (resp.get("provider_ref"), instr["id"]))
    if activate:
        acct = db.one("SELECT * FROM invest_accounts WHERE id = ?", (activate,))
        handle_event(p.name, "account.activated", p.event_activated(acct) if p.is_sandbox else {"external_id": acct["external_id"],
                                                                                             "event_id": f"act_{acct['id']}"})
    return "sent"


def _identity_verified(user_id):
    """Sandbox: the partner accepts an identity check the tenant already passed for a Depiqo deposit account."""
    return bool(db.scalar("SELECT 1 FROM kyc_checks k JOIN tenants t ON t.id = k.tenant_id WHERE t.user_id = ? AND k.status = 'approved' LIMIT 1",
                          (user_id,)))


def retry_instruction(instr_id):
    """Staff may resend only what nobody saw fail: a fee charge, or an account opening that still waits.
    An order or withdrawal the tenant saw as failed is final; the tenant places a new one if they still want it."""
    i = db.one("SELECT * FROM invest_instructions WHERE id = ?", (instr_id,))
    if not i or i["status"] != "failed":
        raise InvestError("Alleen een mislukte opdracht kan opnieuw.")
    if i["kind"] in ("order", "withdraw"):
        order = db.one("SELECT status FROM invest_orders WHERE id = ?", (i["order_id"],)) if i["order_id"] else None
        if not order or order["status"] != "pending":
            raise InvestError("De huurder zag deze order of opname als mislukt. Die wordt niet opnieuw verstuurd; de huurder plaatst zelf een nieuwe.")
    if i["kind"] == "open" and db.scalar("SELECT status FROM invest_accounts WHERE id = ?", (i["account_id"],)) != "pending":
        raise InvestError("De huurder moet de rekening zelf opnieuw aanvragen.")
    db.run("UPDATE invest_instructions SET status = 'pending', attempts = 0 WHERE id = ? AND status = 'failed'", (instr_id,))


def retryable_instruction(i):
    if i["kind"] == "fee":
        return True
    if i["kind"] == "open":
        return db.scalar("SELECT status FROM invest_accounts WHERE id = ?", (i["account_id"],)) == "pending"
    return False


# ================================================================ events from the partner

def provider_allowed(provider):
    p = partner()
    return p.available and p.name == provider


def _int(v, allow_zero=False):
    return isinstance(v, int) and not isinstance(v, bool) and (v >= 0 if allow_zero else v > 0)


class LedgerError(InvestError):
    """An event would break the ledger (for example negative cash). The whole event is refused."""


RETRYABLE = ("onbekende rekening", "onbekende opdracht")


def handle_event(provider, event_type, payload, reprocess=False):
    """Idempotent per event id. An event refused for a timing reason (account or instruction not known yet)
    does not consume its id: a resend is processed. reprocess=True (staff) retries any event with an error.
    The effect of an event is all or nothing (savepoint). Returns 'processed' | 'duplicate' | 'ignored'."""
    if not provider_allowed(provider):
        raise InvestError("Berichten van deze beleggingspartner worden niet verwerkt.")
    if not isinstance(payload, dict) or not payload.get("event_id"):
        raise InvestError("Bericht zonder event_id.")
    event_id = str(payload["event_id"])[:120]

    def replaceable(row):
        return row is not None and row["error"] is not None and (row["retryable"] or reprocess)
    existing = db.one("SELECT * FROM invest_events WHERE provider = ? AND external_event_id = ?", (provider, event_id))
    if existing and not replaceable(existing):
        return "duplicate"
    conn = db.get_db()
    with db.transaction():
        existing = db.one("SELECT * FROM invest_events WHERE provider = ? AND external_event_id = ?", (provider, event_id))
        if existing:
            if not replaceable(existing):
                return "duplicate"
            db.run("DELETE FROM invest_events WHERE id = ?", (existing["id"],))
        try:
            ev = db.run("INSERT INTO invest_events (provider, external_event_id, type, payload_json, received_at) VALUES (?, ?, ?, ?, ?)",
                        (provider, event_id, event_type, dumps(payload), now_iso()))
        except sqlite3.IntegrityError:
            return "duplicate"
        conn.execute("SAVEPOINT invest_event")
        try:
            error = _apply(provider, event_type, payload)
        except (InvestError, ValueError, TypeError, KeyError, AttributeError) as exc:
            error = f"ongeldig bericht: {exc}"[:300]
        if error:
            conn.execute("ROLLBACK TO invest_event")  # nothing of a refused event stays in the ledger
        conn.execute("RELEASE invest_event")
        db.run("UPDATE invest_events SET processed_at = ?, error = ?, retryable = ? WHERE id = ?",
               (now_iso(), error, 1 if error in RETRYABLE else 0, ev))
    if error:
        return "ignored"
    if event_type in ("order.executed", "order.failed") and not conn.in_transaction:
        acct = db.one("SELECT id FROM invest_accounts WHERE provider = ? AND external_id = ?", (provider, payload.get("external_id")))
        if acct:
            continue_switches(acct["id"])  # never raises: a purchase that cannot be placed now stays pending
    return "processed"


def reprocess_event(event_row_id):
    """Staff: process an event that ended with an error again (same id, same payload)."""
    ev = db.one("SELECT * FROM invest_events WHERE id = ?", (event_row_id,))
    if not ev or ev["error"] is None:
        raise InvestError("Alleen een bericht met een fout kan opnieuw worden verwerkt.")
    return handle_event(ev["provider"], ev["type"], json.loads(ev["payload_json"]), reprocess=True)


def _instr(account, ref, kind):
    return db.one("SELECT * FROM invest_instructions WHERE account_id = ? AND idempotency_key = ? AND kind = ?", (account["id"], ref or "", kind))


def _event_day(p, acct):
    """The business day of an event: a real ISO date between the opening of the account and tomorrow."""
    raw = p.get("day")
    if raw is None:
        return invest_day().isoformat()
    if not isinstance(raw, str) or len(raw) != 10:
        raise ValueError("ongeldige datum")
    d = date.fromisoformat(raw)
    # the partner's business days (the sandbox clock may differ from the calendar): from the day the account opened
    opened = parse_date(acct["activated_day"] or db.scalar(
        "SELECT MIN(created_day) FROM invest_instructions WHERE account_id = ? AND kind = 'open'", (acct["id"],)) or invest_day())
    if d < opened - timedelta(days=1) or d > invest_day() + timedelta(days=1):
        raise ValueError("datum buiten de looptijd van de rekening")
    return d.isoformat()


def _apply(provider, event_type, p):
    acct = db.one("SELECT * FROM invest_accounts WHERE provider = ? AND external_id = ?", (provider, p.get("external_id")))
    if not acct:
        return "onbekende rekening"
    if event_type == "account.activated":
        db.run("UPDATE invest_accounts SET status = 'active', activated_at = ?, activated_day = ?, fee_accrued_through = ? WHERE id = ? AND status = 'pending'",
               (now_iso(), invest_day().isoformat(), invest_day().isoformat(), acct["id"]))
        return None
    day = _event_day(p, acct)
    if event_type == "deposit.received":
        if not _int(p.get("amount_cents")) or not p.get("ref"):
            return "ongeldig bedrag of kenmerk"
        ref = str(p["ref"])[:120]
        if db.scalar("SELECT 1 FROM invest_transactions WHERE account_id = ? AND external_ref = ?", (acct["id"], ref)):
            return "storting met dit kenmerk is al verwerkt"
        kind = "payout_in" if ref.startswith("payout:") else "deposit"
        _tx(acct, kind, p["amount_cents"], "Terugbetaling van je borg ontvangen" if kind == "payout_in" else "Storting ontvangen", day, ref)
        if kind == "payout_in":
            _mark_payout_recorded(ref[len("payout:"):], acct, p["amount_cents"])
        return None
    if event_type in ("order.executed", "order.failed"):
        instr = _instr(acct, p.get("ref"), "order")
        if not instr:
            return "onbekende opdracht"
        if instr["status"] == "confirmed":
            return "order al verwerkt"
        order = db.one("SELECT * FROM invest_orders WHERE id = ?", (instr["order_id"],))
        if event_type == "order.failed":
            db.run("UPDATE invest_orders SET status = 'failed', error = ? WHERE id = ?", (str(p.get("reason") or "")[:200], order["id"]))
            db.run("UPDATE invest_instructions SET status = 'failed', last_error = ? WHERE id = ?", (str(p.get("reason") or "")[:300], instr["id"]))
            notify.notify_invest_account(acct["id"], "invest_order_failed", {"side": f"@side.{order['side']}", "amount_cents": order["amount_cents"],
                                                                             "reason": str(p.get("reason") or "")[:200]})
            return None
        fills = p.get("fills")
        if not isinstance(fills, list):
            return "ongeldige uitvoering"
        problem = _check_fills(acct, order["side"], fills, order["amount_cents"])
        if problem:
            return problem
        total = _apply_fills(acct, order["side"], fills, day, str(p["ref"]), order["id"])
        verb = "Gekocht" if order["side"] == "buy" else "Verkocht"
        _tx(acct, order["side"], -total if order["side"] == "buy" else total,
            f"{verb}: {PORTFOLIOS[order['portfolio']]['label']}", day, str(p["ref"]), order["id"])
        db.run("UPDATE invest_orders SET status = 'executed', executed_amount_cents = ?, executed_day = ?, executed_at = ? WHERE id = ?",
               (total, day, now_iso(), order["id"]))
        notify.notify_invest_account(acct["id"], "invest_order_executed", {"side": f"@side.{order['side']}", "amount_cents": total,
                                                                           "portfolio": f"@portfolio.{order['portfolio']}", "day_date": day})
        db.run("UPDATE invest_instructions SET status = 'confirmed', confirmed_at = ? WHERE id = ?", (now_iso(), instr["id"]))
        return None
    if event_type in ("withdrawal.completed", "withdrawal.failed"):
        instr = _instr(acct, p.get("ref"), "withdraw")
        if not instr:
            return "onbekende opdracht"
        if instr["status"] in ("confirmed", "failed"):
            return "opname al verwerkt"
        payload = json.loads(instr["payload_json"])
        if event_type == "withdrawal.failed":
            db.run("UPDATE invest_instructions SET status = 'failed', last_error = ? WHERE id = ?", (str(p.get("reason") or "")[:300], instr["id"]))
            notify.notify_invest_account(acct["id"], "invest_withdrawal_failed", {"amount_cents": payload["amount_cents"],
                                                                                  "reason": str(p.get("reason") or "")[:200]})
            return None
        if p.get("amount_cents") != payload["amount_cents"]:
            return "opgenomen bedrag wijkt af van de opdracht"
        _tx(acct, "withdrawal", -payload["amount_cents"], f"Opgenomen naar {payload['iban'][:4]} …{payload['iban'][-4:]}", day, str(p["ref"]))
        notify.notify_invest_account(acct["id"], "invest_withdrawal_completed", {"amount_cents": payload["amount_cents"],
                                                                                 "iban_tail": f"{payload['iban'][:4]} …{payload['iban'][-4:]}"})
        db.run("UPDATE invest_instructions SET status = 'confirmed', confirmed_at = ? WHERE id = ?", (now_iso(), instr["id"]))
        return None
    if event_type == "fee.charged":
        instr = _instr(acct, p.get("ref"), "fee")
        if not instr:
            return "onbekende opdracht"
        if instr["status"] == "confirmed":
            return "servicekosten al verwerkt"
        payload = json.loads(instr["payload_json"])
        charged = p.get("amount_cents")
        if not _int(charged, True) or charged > payload["amount_cents"]:
            return "servicekosten hoger dan de opdracht"
        fills = p.get("fills") or []
        if not isinstance(fills, list):
            return "ongeldige uitvoering"
        if fills:
            problem = _check_fills(acct, "sell", fills, None)
            if problem:
                return problem
            proceeds = _apply_fills(acct, "fee_sell", fills, day, str(p["ref"]), None)
            _tx(acct, "sell", proceeds, "Verkocht voor servicekosten", day, str(p["ref"]) + ":verkoop")
        if charged:
            _tx(acct, "fee", -charged, f"Servicekosten Depiqo {payload['period']}", day, str(p["ref"]))
        rest = payload["amount_cents"] - charged
        if rest:
            db.run("UPDATE invest_accounts SET fee_carry_cents = fee_carry_cents + ? WHERE id = ?", (rest, acct["id"]))  # charged later
        db.run("UPDATE invest_instructions SET status = 'confirmed', confirmed_at = ? WHERE id = ?", (now_iso(), instr["id"]))
        return None
    return "onbekend type"


def _check_fills(acct, side, fills, amount):
    """Every fill: a known fund, whole positive numbers, and an amount that matches units x price to the cent
    (one cent of rounding allowed). Sales never more than held; a purchase never more than the order."""
    held = units_by_fund(acct["id"])
    total = 0
    for f in fills:
        if not isinstance(f, dict) or f.get("fund") not in FUNDS:
            return "ongeldige uitvoering"
        u, px, amt = f.get("units_1e4"), f.get("price_1e4"), f.get("amount_cents")
        if not (isinstance(u, int) and not isinstance(u, bool) and u != 0 and _int(px) and _int(amt, True)):
            return "ongeldige uitvoering"
        if abs(amt - value_cents(abs(u), px)) > 1:
            return "bedrag van de uitvoering past niet bij stukken maal koers"
        if (side == "buy") != (u > 0):
            return "uitvoering past niet bij de order"
        if u < 0 and -u > held.get(f["fund"], 0):
            return "meer verkocht dan in bezit"
        total += amt
    if side == "buy" and amount is not None and total > amount:
        return "uitvoering hoger dan de order"
    return None


def _apply_fills(acct, kind, fills, day, ref, order_id):
    total = 0
    for f in fills:
        db.run("INSERT INTO invest_fills (account_id, order_id, kind, fund, units_1e4, price_1e4, amount_cents, day, external_ref) "
               "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
               (acct["id"], order_id, "buy" if kind == "buy" else ("fee_sell" if kind == "fee_sell" else "sell"), f["fund"], f["units_1e4"],
                f["price_1e4"], f["amount_cents"], day, ref))
        total += f["amount_cents"]
    return total


def _tx(acct, kind, amount, description, day, ref, order_id=None):
    db.run("INSERT INTO invest_transactions (account_id, kind, amount_cents, description, day, external_ref, order_id, at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
           (acct["id"], kind, amount, description[:200], day, ref, order_id, now_iso()))
    if amount < 0 and cash_cents(acct["id"]) < 0:
        raise LedgerError("saldo zou negatief worden")  # never: cash on an investment account is never below zero


def _mark_payout_recorded(pid, acct, amount):
    """The incoming share of a deposit release was recorded on the investment account: only now 'paid'."""
    db.run("UPDATE invest_payout_choices SET status = 'paid', paid_cents = ?, paid_at = ?, note = NULL "
           "WHERE account_id = ? AND status IN ('chosen', 'unrecorded') AND deposit_id = (SELECT id FROM deposits WHERE pid = ?)",
           (amount, now_iso(), acct["id"], pid))


# ================================================================ service fee

def accrue_fees(through_day=None, charge_now=False):
    """Accrues the service fee day by day on the value of the investments (cash is not charged), at each
    account's own agreed rate, and sends a fee instruction for every completed month. charge_now: also charge
    what accrued so far (staff button). Returns the number of fee instructions written."""
    p = partner()
    if not p.available:
        return 0
    through = parse_date(through_day) if through_day else invest_day()
    written = 0
    for acct in db.all_("SELECT * FROM invest_accounts WHERE status = 'active' AND provider = ?", (p.name,)):
        written += _accrue_account(acct, through, charge_now)
    dispatch()
    return written


def _accrue_account(acct, through, charge_now=False):
    bps = acct["fee_rate_bps"] if acct["fee_rate_bps"] is not None else fee_bps()
    last = parse_date(acct["fee_accrued_through"] or acct["activated_day"] or through.isoformat())
    micro = acct["fee_accrued_micro"]
    fills = db.all_("SELECT day, fund, units_1e4 FROM invest_fills WHERE account_id = ? ORDER BY day, id", (acct["id"],))
    units, fi, written = {}, 0, 0
    d = last + timedelta(days=1)
    with db.transaction():
        while fi < len(fills) and fills[fi]["day"] < d.isoformat():
            units[fills[fi]["fund"]] = units.get(fills[fi]["fund"], 0) + fills[fi]["units_1e4"]
            fi += 1
        while d <= through:
            while fi < len(fills) and fills[fi]["day"] <= d.isoformat():
                units[fills[fi]["fund"]] = units.get(fills[fi]["fund"], 0) + fills[fi]["units_1e4"]
                fi += 1
            value = sum(value_cents(u, price_1e4(f, d)) for f, u in units.items() if u)
            micro += value * bps * 100 // 365          # value x bps/10000 / 365, in millionths of a cent
            if (d + timedelta(days=1)).month != d.month:
                written += _charge(acct, micro, d.strftime("%Y-%m"), f"invest-fee:{acct['id']}:{d.strftime('%Y-%m')}")
                micro = 0
            d += timedelta(days=1)
        if charge_now and (micro >= MICRO // 2 or (acct["fee_carry_cents"] or 0) > 0):
            written += _charge(acct, micro, through.strftime("%Y-%m") + f" tot {through.day}", f"invest-fee:{acct['id']}:{through.isoformat()}")
            micro = 0
        db.run("UPDATE invest_accounts SET fee_accrued_micro = ?, fee_accrued_through = ? WHERE id = ?",
               (micro, max(through, last).isoformat(), acct["id"]))
    return written


def _charge(acct, micro, period, key):
    """Half up to the cent; a remainder that could not be charged earlier (fee_carry_cents) is added."""
    carry = db.scalar("SELECT fee_carry_cents FROM invest_accounts WHERE id = ?", (acct["id"],)) or 0
    amount = round_half_up(micro, MICRO) + carry
    if amount <= 0:
        return 0
    db.run("UPDATE invest_accounts SET fee_carry_cents = 0 WHERE id = ?", (acct["id"],))
    _enqueue(acct["id"], acct["provider"], "fee", {"amount_cents": amount, "period": period}, key)
    return 1


def accept_fee_change(account):
    """The tenant accepts the proposed service fee. Days until today are accrued at the old rate first, so a
    new rate never applies to the past."""
    acct = db.one("SELECT * FROM invest_accounts WHERE id = ?", (account["id"],))
    if not acct or acct["pending_fee_bps"] is None:
        raise InvestError("Er is geen voorstel voor een nieuwe servicevergoeding.")
    if acct["status"] == "active":
        _accrue_account(acct, invest_day())
    db.run("UPDATE invest_accounts SET fee_rate_bps = pending_fee_bps, fee_rate_accepted_at = ?, pending_fee_bps = NULL, "
           "pending_fee_notified_at = NULL WHERE id = ?", (now_iso(), acct["id"]))


# ================================================================ sandbox console

def sandbox_partner():
    p = partner()
    if not p.available or not p.is_sandbox:
        raise InvestUnavailable("De sandbox-beleggingspartner staat niet aan.")
    return p


def sandbox_settle(p=None):
    p = p or sandbox_partner()
    day = p.today()
    n = 0
    for etype, payload in p.settle(day):
        if handle_event(p.name, etype, payload) == "processed":
            n += 1
    return n


def advance_day(days=1):
    """Sandbox: the partner's clock moves forward. Orders, withdrawals and fees are executed at the new
    day's price, the service fee accrues, and a month end charges it."""
    p = sandbox_partner()
    done = 0
    for _ in range(days):
        dispatch()
        db.run("UPDATE invest_sandbox_clock SET offset_days = offset_days + 1 WHERE id = 1")
        done += sandbox_settle(p)
        continue_switches()
        accrue_fees()
        done += sandbox_settle_fees(p)
    return done


def sandbox_settle_fees(p):
    """Fees written today are collected the same day in the sandbox (a real partner reports when it collected)."""
    n = 0
    for etype, payload in p.settle(p.today(), kinds=("fee",), same_day=True):
        if handle_event(p.name, etype, payload) == "processed":
            n += 1
    return n


def charge_fees_now():
    p = sandbox_partner()
    written = accrue_fees(charge_now=True)
    sandbox_settle_fees(p)
    return written


def simulate_deposit(account, amount_cents):
    """Sandbox: the tenant's transfer arrives at the partner's client-money account."""
    p = sandbox_partner()
    if account["provider"] != p.name or account["status"] != "active":
        raise InvestError("Je beleggingsrekening is nog niet actief.")
    if not amount_cents or amount_cents <= 0 or amount_cents > 10_000_000:
        raise InvestError("Kies een bedrag tussen € 0,01 en € 100.000.")
    return handle_event(p.name, "deposit.received", p.event_deposit(account, amount_cents))


# ================================================================ doorbeleggen (tenant share of a deposit release)

def payout_choice(deposit_id):
    return db.one("SELECT * FROM invest_payout_choices WHERE deposit_id = ? AND status != 'cancelled'", (deposit_id,))


def can_choose_payout(deposit, user_id):
    """Doorbeleggen: a Depiqo deposit account, agreed and not paid out yet, an active investment account, and
    Invest offered by the organisation of THIS deposit."""
    from . import states as S
    acct = account_for_user(user_id)
    return (deposit["holding"] == "depiqo" and deposit["status"] == S.AGREED and acct is not None and acct["status"] == "active"
            and partner().available and acct["provider"] == partner().name
            and bool(db.scalar("SELECT invest_enabled FROM organizations WHERE id = ?", (deposit["org_id"],)))
            and not db.scalar("SELECT 1 FROM bank_instructions WHERE deposit_id = ? AND kind = 'release'", (deposit["id"],)))


_OPEN_FOR_CHOICE = ("EXISTS (SELECT 1 FROM deposits WHERE id = ? AND status = 'agreed') "
                    "AND NOT EXISTS (SELECT 1 FROM bank_instructions WHERE deposit_id = ? AND kind = 'release')")


def choose_payout(deposit, user_id, to_invest):
    """The tenant's explicit choice before the payout starts: own account (default) or Invest cash. Each change is
    one conditional statement on the deposit's current status, so a choice can never change once the bank
    release instruction exists (also not with a page that was loaded earlier)."""
    closed = InvestError("Dit kan niet meer: de uitbetaling is al gestart.")
    if not to_invest:
        if not payout_choice(deposit["id"]):
            return None
        changed = db.get_db().execute(
            "UPDATE invest_payout_choices SET status = 'cancelled', cancelled_at = ? WHERE deposit_id = ? AND status = 'chosen' AND " + _OPEN_FOR_CHOICE,
            (now_iso(), deposit["id"], deposit["id"], deposit["id"])).rowcount
        if changed != 1:
            raise closed
        return None
    if db.scalar("SELECT 1 FROM bank_instructions WHERE deposit_id = ? AND kind = 'release'", (deposit["id"],)) or \
            db.scalar("SELECT status FROM deposits WHERE id = ?", (deposit["id"],)) != "agreed":
        raise closed
    if not can_choose_payout(deposit, user_id):
        raise InvestError("Doorbeleggen kan alleen met een actieve beleggingsrekening, bij een Depiqo-borgrekening, na akkoord en voor de uitbetaling.")
    acct = account_for_user(user_id)
    instr = partner_for(acct).deposit_instructions(acct)
    with db.transaction():
        db.run("DELETE FROM invest_payout_choices WHERE deposit_id = ? AND status = 'cancelled' AND " + _OPEN_FOR_CHOICE,
               (deposit["id"], deposit["id"], deposit["id"]))
        changed = db.get_db().execute(
            "INSERT INTO invest_payout_choices (deposit_id, account_id, user_id, destination_iban, reference, status, chosen_at) "
            "SELECT ?, ?, ?, ?, ?, 'chosen', ? WHERE " + _OPEN_FOR_CHOICE + " ON CONFLICT(deposit_id) DO NOTHING",
            (deposit["id"], acct["id"], user_id, instr["iban"], instr["reference"], now_iso(), deposit["id"], deposit["id"])).rowcount
        if changed != 1 and not db.scalar("SELECT 1 FROM invest_payout_choices WHERE deposit_id = ? AND status = 'chosen'", (deposit["id"],)):
            raise closed
    return payout_choice(deposit["id"])


PAYOUT_FALLBACK_SUBJECT = "Je deel van de borg gaat naar je eigen rekening"


def notice_subjects():
    """Subjects of the mails about the investment account: records that are kept when an account is deleted."""
    return {PAYOUT_FALLBACK_SUBJECT} | {i18n.t(k, lang) for k in ("mail.iban_changed.subject", "mail.fee_change.subject") for lang in i18n.LANGS}


def payout_destination(deposit):
    """Called inside the start_payout transaction. The tenant's share goes to Invest only when everything is in
    order now: a partner, the tenant's active account at that partner, and Invest offered by this deposit's
    organisation. Otherwise the share goes to the tenant's own account; the choice becomes 'fallback', staff see
    it, and the tenant gets a message. Returns the destination for the release instruction, or None."""
    c = db.one("SELECT * FROM invest_payout_choices WHERE deposit_id = ? AND status = 'chosen'", (deposit["id"],))
    if not c:
        return None
    p = partner()
    acct = db.one("SELECT a.*, u.email, u.name FROM invest_accounts a JOIN users u ON u.id = a.user_id WHERE a.id = ?", (c["account_id"],))
    tenant_user = db.scalar("SELECT user_id FROM tenants WHERE id = ?", (deposit["tenant_id"],))
    problem = None
    if not p.available:
        problem = "geen beleggingspartner beschikbaar"
    elif not acct or acct["status"] != "active" or acct["provider"] != p.name:
        problem = "beleggingsrekening niet actief bij de huidige partner"
    elif not db.scalar("SELECT invest_enabled FROM organizations WHERE id = ?", (deposit["org_id"],)):
        problem = "Beleggen staat uit voor de organisatie van dit dossier"
    elif acct["user_id"] != tenant_user:
        problem = "rekening hoort niet bij de huurder van dit dossier"
    if problem:
        from .partners import send_mail
        from .security import NO_ORG, audit
        db.run("UPDATE invest_payout_choices SET status = 'fallback', note = ? WHERE id = ?", (problem, c["id"]))
        audit("invest.payout_fallback", f"deposit:{deposit['pid']}", {"reden": problem}, org_id=NO_ORG)
        if acct:
            # No deposit_id: this message must not appear in the dossier's communication log for the landlord.
            send_mail(acct["email"], PAYOUT_FALLBACK_SUBJECT,
                      f"Hallo {acct['name']},\n\nJe koos ervoor om je deel van de borg op je beleggingsrekening te ontvangen. "
                      "Dat kan nu niet, dus de bank betaalt het uit op je eigen rekening.\n")
        return None
    return {"type": "invest", "iban": c["destination_iban"], "reference": c["reference"]}


def on_payout_completed(deposit, tenant_cents, ref, destination=None):
    """Called inside the bank event transaction after the 0.3 amount check passed. Whether money went to Invest is
    decided only by the release instruction (destination), never by the choice table. The choice is 'paid' only
    when the money is recorded on the investment account in this same transaction; otherwise 'unrecorded', and
    Depiqo staff see it until the partner's deposit.received arrives."""
    if not destination or destination.get("type") != "invest":
        return
    acct = db.one("SELECT * FROM invest_accounts WHERE reference = ?", (destination.get("reference"),))
    recorded = False
    p = partner()
    if tenant_cents and acct and p.available and p.is_sandbox and acct["provider"] == p.name and acct["status"] == "active":
        result = handle_event(p.name, "deposit.received", {"event_id": f"sbi_payout_{deposit['id']}", "external_id": acct["external_id"],
                                                            "amount_cents": tenant_cents, "ref": f"payout:{deposit['pid']}",
                                                            "day": invest_day().isoformat()})
        recorded = result == "processed"
    if acct and not recorded:
        db.run("UPDATE invest_payout_choices SET status = 'unrecorded', paid_cents = ?, note = ? WHERE deposit_id = ? AND status IN ('chosen', 'fallback')",
               (tenant_cents, "betaald aan de partner, nog niet verwerkt op de beleggingsrekening", deposit["id"]))


def payout_exceptions():
    """Doorbeleggen that needs Depiqo staff: fell back to the tenant's own account, or paid but not recorded."""
    return db.all_("SELECT c.*, d.pid, d.reference AS deposit_reference, u.email FROM invest_payout_choices c JOIN deposits d ON d.id = c.deposit_id "
                   "JOIN users u ON u.id = c.user_id WHERE c.status IN ('fallback', 'unrecorded') ORDER BY c.id DESC")


# ================================================================ statements

def statement_periods(account):
    if not account["activated_day"]:
        return []
    first = db.scalar("SELECT MIN(day) FROM invest_transactions WHERE account_id = ?", (account["id"],)) or account["activated_day"]
    start, end = parse_date(first).replace(day=1), invest_day().replace(day=1)
    out = []
    while start <= end:
        out.append(start.strftime("%Y-%m"))
        start = (start + timedelta(days=32)).replace(day=1)
    return list(reversed(out))


def statement_data(account, period):
    y, m = int(period[:4]), int(period[5:7])
    first = date(y, m, 1)
    last = (first + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    end = min(last, invest_day())
    prev = first - timedelta(days=1)
    rows = db.all_("SELECT * FROM invest_transactions WHERE account_id = ? AND day >= ? AND day <= ? ORDER BY day, id",
                   (account["id"], first.isoformat(), end.isoformat()))
    sums = {k: sum(r["amount_cents"] for r in rows if r["kind"] in kinds)
            for k, kinds in (("in", ("deposit", "payout_in")), ("out", ("withdrawal",)), ("fees", ("fee",)))}
    return {"period": period, "first": first, "end": end, "value_start": value_at(account["id"], prev), "value_end": value_at(account["id"], end),
            "deposits": sums["in"], "withdrawals": -sums["out"], "fees": -sums["fees"],
            "orders": [r for r in rows if r["kind"] in ("buy", "sell")], "rows": rows,
            "positions": positions(account["id"], end)}


def statement_pdf(account, period, user_name, compress=True):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from xml.sax.saxutils import escape
    from .util import date_nl, eur

    s = statement_data(account, period)
    p = partner()
    navy = colors.Color(0.043, 0.078, 0.149)
    muted = colors.Color(0.37, 0.44, 0.51)
    line = colors.Color(0.85, 0.88, 0.9)
    base = ParagraphStyle("b", fontName="Helvetica", fontSize=9.5, leading=13, textColor=navy)
    small = ParagraphStyle("s", parent=base, fontSize=8.5, leading=11.5, textColor=muted)
    h1 = ParagraphStyle("h1", parent=base, fontName="Helvetica-Bold", fontSize=16, leading=20)
    h2 = ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=10.5, leading=14, spaceBefore=6)

    def P(t, st=base):
        return Paragraph(escape(str(t)), st)

    def table(rows, widths):
        t = Table(rows, colWidths=widths, hAlign="LEFT")
        t.setStyle(TableStyle([("ALIGN", (-1, 0), (-1, -1), "RIGHT"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, line),
                               ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                               ("FONTNAME", (0, 0), (-1, -1), "Helvetica"), ("FONTSIZE", (0, 0), (-1, -1), 9.5)]))
        return t

    w = A4[0] - 40 * mm
    story = [P(f"Maandoverzicht beleggingsrekening {period}", h1), Spacer(1, 2 * mm),
             P(f"{user_name} · rekening {account['reference']} · {p.display_name if p.available else account['provider']}", small),
             P(f"Periode {date_nl(s['first'])} tot en met {date_nl(s['end'])}.", small), Spacer(1, 4 * mm),
             P("Samenvatting", h2),
             table([["Waarde aan het begin", eur(s["value_start"])], ["Stortingen", eur(s["deposits"])], ["Opnames", eur(s["withdrawals"])],
                    ["Servicekosten Depiqo", eur(s["fees"])], ["Waarde aan het eind", eur(s["value_end"])]], (w - 40 * mm, 40 * mm)),
             P("Orders", h2)]
    if s["orders"]:
        story.append(table([[date_nl(r["day"]), r["description"], eur(abs(r["amount_cents"]))] for r in s["orders"]],
                           (30 * mm, w - 70 * mm, 40 * mm)))
    else:
        story.append(P("Geen orders in deze maand.", small))
    story.append(P("Posities aan het eind", h2))
    if s["positions"]:
        story.append(table([[pos["name"], f"{pos['units_1e4'] / 10000:.4f} stuks".replace(".", ","), eur(pos["value"])] for pos in s["positions"]],
                           (w - 80 * mm, 40 * mm, 40 * mm)))
    else:
        story.append(P("Geen posities.", small))
    story += [Spacer(1, 6 * mm),
              P("De lopende kosten van de fondsen zitten in de koers en staan niet apart in dit overzicht. Het officiële overzicht "
                "komt van de beleggingspartner. Je borg staat los van deze rekening en wordt nooit belegd.", small),
              P(role_text(p) if p.available else "", small)]
    import io
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=16 * mm,
                            title=f"Maandoverzicht {period}", author="Depiqo", pageCompression=1 if compress else 0)
    doc.build(story)
    return buf.getvalue()


# ================================================================ staff read models

def staff_overview():
    accounts = db.all_("SELECT a.*, u.email, u.name FROM invest_accounts a JOIN users u ON u.id = a.user_id ORDER BY a.id")
    rows, aum, investors = [], 0, 0
    for a in accounts:
        val = value_at(a["id"], invest_day()) if a["status"] in ("active", "closed") else 0
        rows.append({"a": a, "value": val})
        if a["status"] == "active":
            aum += val
            investors += 1 if val > 0 else 0
    by_status = {s: sum(1 for a in accounts if a["status"] == s) for s in ("draft", "pending", "active", "closed")}
    appr = {r["result"]: r["n"] for r in db.all_(
        "SELECT result, COUNT(*) AS n FROM (SELECT * FROM invest_appropriateness WHERE id IN (SELECT MAX(id) FROM invest_appropriateness GROUP BY user_id)) GROUP BY result")}
    confirmed = db.scalar("SELECT COUNT(*) FROM invest_appropriateness WHERE result = 'niet_passend' AND warning_confirmed_at IS NOT NULL "
                          "AND id IN (SELECT MAX(id) FROM invest_appropriateness GROUP BY user_id)")
    failed = [dict(i) | {"retryable": retryable_instruction(i)} for i in db.all_(
        "SELECT i.*, u.email FROM invest_instructions i JOIN invest_accounts a ON a.id = i.account_id JOIN users u ON u.id = a.user_id "
        "WHERE i.status = 'failed' ORDER BY i.id DESC LIMIT 50")]
    events_err = db.all_("SELECT * FROM invest_events WHERE error IS NOT NULL ORDER BY id DESC LIMIT 20")
    return {"rows": rows, "aum": aum, "investors": investors, "by_status": by_status, "appr": appr, "confirmed": confirmed,
            "failed": failed, "events_err": events_err, "day": invest_day(), "payout_exceptions": payout_exceptions(),
            "pending_fee": db.scalar("SELECT COUNT(*) FROM invest_accounts WHERE pending_fee_bps IS NOT NULL")}


def economics(period, cost_per_account_cents):
    """For unit economics: AUM, active investors, service fee revenue in the month (charged plus accrued) and cost."""
    ov = staff_overview()
    start = f"{period}-01"
    end = f"{period}-31"
    charged = -db.scalar("SELECT COALESCE(SUM(amount_cents), 0) FROM invest_transactions WHERE kind = 'fee' AND day >= ? AND day <= ?", (start, end))
    accrued = round_half_up(db.scalar("SELECT COALESCE(SUM(fee_accrued_micro), 0) FROM invest_accounts WHERE status = 'active'") or 0, MICRO)
    accounts = ov["by_status"]["active"]
    cost = accounts * cost_per_account_cents
    revenue_run_rate = round_half_up(ov["aum"] * fee_bps(), 10000 * 12)
    return {"aum": ov["aum"], "investors": ov["investors"], "accounts": accounts, "charged": charged, "accrued": accrued,
            "run_rate": revenue_run_rate, "cost": cost, "margin": revenue_run_rate - cost, "fee_bps": fee_bps()}
