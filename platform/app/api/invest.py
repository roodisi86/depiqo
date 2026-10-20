"""Depiqo Invest for the app. The same functions as the web wallet (investing.py) and the same fail-closed rules:
404 unless Invest is offered to this tenant or they already have an account, 503 without a partner, new
accounts and purchases only while the landlord's organisation offers Invest. An order needs a quote first
(costs and risk, valid 10 minutes) and an explicit risk acknowledgement."""
import json
from datetime import timedelta

from flask import Response, current_app, g, jsonify, request

from .. import db, investing
from ..security import NO_ORG, audit
from ..util import MONTHS_NL, dumps, now, now_iso, parse_date, token
from . import ApiError, body, bp, field_error, idempotent, iso_date, money, page_args, paged, sandbox_only, tenant_api, true_field

QUOTE_TTL = timedelta(minutes=10)
ORDER_STATUS = {"pending": "Wordt uitgevoerd", "executed": "Uitgevoerd", "failed": "Niet uitgevoerd"}
ACCOUNT_STATUS = {"draft": "Nog niet geopend", "pending": "Wordt geopend", "active": "Actief", "closed": "Gesloten"}
RANGES = (("1M", 30, 60), ("6M", 182, 60), ("1Y", 365, 60), ("max", None, 120))
WARNING_CONFIRMATION = ("Ik heb deze waarschuwing gelezen. Ik begrijp dat beleggen mogelijk niet bij mij past en dat ik geld kan "
                        "verliezen. Ik wil toch zelf verder.")


def _audit(action, data=None):
    audit(f"invest.{action}", f"user:{g.api_user['id']}", (data or {}) | {"via": "app"}, org_id=NO_ORG)


def invest_guard():
    vis = investing.visibility(g.api_user["id"])
    if vis == "hidden":
        raise ApiError(404, "invest_not_offered", "Beleggen is niet beschikbaar voor jou. Je verhuurder biedt het niet aan.")
    if vis == "unavailable":
        raise ApiError(503, "partner_unavailable", "Beleggen is nu niet beschikbaar: er is geen beleggingspartner gekoppeld. Er wordt geen geld verplaatst.")
    return investing.account_for_user(g.api_user["id"])


def rejected(exc):
    if isinstance(exc, investing.InvestRateLimited):
        return ApiError(429, "too_many_attempts", str(exc), headers={"Retry-After": "900"})
    if isinstance(exc, investing.InvestUnavailable):
        return ApiError(503, "partner_unavailable", str(exc))
    return ApiError(409, "invest_rejected", str(exc))


def active_account():
    acct = invest_guard()
    if not acct or acct["status"] != "active":
        raise ApiError(409, "account_not_active", "Je beleggingsrekening is nog niet actief.")
    return acct


# ------------------------------------------------------------ serialisation

def costs_json(c):
    return {"amount": money(c["amount"]), "service_fee_bps": c["fee_bps"], "ongoing_charges_bps": round(c["ocf_bps"], 2),
            "transaction_cost_bps": c["tx_bps"], "service_1y": money(c["service_1y"]), "fund_1y": money(c["fund_1y"]),
            "transactions": money(c["tx"]), "total_1y": money(c["total_1y"]), "service_3y": money(c["service_3y"]),
            "fund_3y": money(c["fund_3y"]), "total_3y": money(c["total_3y"]), "percent_per_year": round(c["pct_per_year"], 4),
            "note": "Kosten in euro voor dit bedrag, als de waarde gelijk blijft. De lopende kosten zitten in de koers van de fondsen."}


def scenarios_json(rows):
    return {"items": [{"key": s["key"], "label": s["label"], "yearly_return": s["rate"], "value_after_1y": money(s["y1"]),
                       "value_after_3y": money(s["y3"]), "result_1y": money(s["y1_result"]), "result_3y": money(s["y3_result"])} for s in rows],
            "note": "Dit zijn voorbeelden, geen voorspelling. Na kosten."}


def portfolio_json(code):
    p = investing.PORTFOLIOS[code]
    return {"code": code, "label": p["label"], "risk": p["risk"], "risk_scale": 7, "summary": p["summary"],
            "funds": [{"fund": f, "name": investing.FUNDS[f]["name"], "asset": investing.FUNDS[f]["asset"], "weight_bps": w,
                       "ongoing_charges_bps": investing.FUNDS[f]["ocf_bps"]} for f, w in p["weights"].items()]}


def account_json(a):
    iban = a["own_iban"]
    return {"reference": a["reference"], "status": a["status"], "status_label": ACCOUNT_STATUS[a["status"]],
            "portfolio": a["portfolio"], "portfolio_label": investing.PORTFOLIOS[a["portfolio"]]["label"] if a["portfolio"] else None,
            "pending_switch": a["pending_switch"], "switch_note": a["switch_note"],
            "fee_rate_bps": a["fee_rate_bps"], "pending_fee_bps": a["pending_fee_bps"],
            "own_iban": {"masked": f"{iban[:4]} … {iban[-4:]}", "registered_at": a["own_iban_registered_at"],
                         "usable_from": a["own_iban_usable_from"], "usable_now": (a["own_iban_usable_from"] or "") <= now_iso()} if iban else None,
            "opened_at": a["opened_at"], "activated_at": a["activated_at"]}


def order_json(o):
    return {"id": o["id"], "side": o["side"], "portfolio": o["portfolio"], "portfolio_label": investing.PORTFOLIOS[o["portfolio"]]["label"],
            "amount": money(o["amount_cents"]), "sell_all": bool(o["sell_all"]), "purpose": o["purpose"], "status": o["status"],
            "status_label": ORDER_STATUS.get(o["status"], o["status"]), "executed_amount": money(o["executed_amount_cents"]),
            "executed_day": o["executed_day"], "created_at": o["created_at"], "error": o["error"]}


def withdrawal_json(w):
    return {"id": w["id"], "amount": money(w["amount_cents"]), "iban_masked": f"{w['iban'][:4]} … {w['iban'][-4:]}", "status": w["status"],
            "status_label": w["label"], "day": w["day"], "created_at": w["created_at"]}


def transaction_json(t):
    return {"id": t["id"], "kind": t["kind"], "amount": money(t["amount_cents"]), "description": t["description"], "day": t["day"],
            "at": t["at"]}


def summary_json(s):
    return {"day": iso_date(s["day"]), "value": money(s["total"]), "invested_value": money(s["invested_value"]), "cash": money(s["cash"]),
            "available": money(s["available"]), "reserved": money(s["reserved"]), "net_deposits": money(s["net_in"]),
            "result": money(s["result"]), "result_pct": round(s["result_pct"], 2) if s["result_pct"] is not None else None,
            "fees_paid": money(s["fees"]), "accrued_fee": money(s["accrued_fee"]), "sellable": money(s["sellable"]),
            "fee_rate_bps": s["fee_rate_bps"],
            "positions": [{"fund": p["fund"], "name": p["name"], "asset": p["asset"], "units_1e4": p["units_1e4"],
                           "units": f"{p['units_1e4'] / 10000:.4f}", "price_1e4": p["price_1e4"], "value": money(p["value"])} for p in s["positions"]]}


def chart_json(account_id):
    day = investing.invest_day()
    values, nets = {}, {}
    for key, days, points in RANGES:
        pts = investing.history(account_id, points=points, since=day - timedelta(days=days) if days else None)
        values[key] = [[d.isoformat(), v] for d, v, _ in pts]
        nets[key] = [[d.isoformat(), n] for d, _, n in pts]
    return values, nets


def onboarding_json(uid, acct):
    appr = investing.latest_appropriateness(uid)
    t = investing.terms()
    accepted = bool(acct and acct["status"] == "draft" and acct["terms_partner_version"] == t["partner"]["version"]
                    and acct["terms_depiqo_version"] == t["depiqo"]["version"])
    if not appr:
        step = "appropriateness"
    elif not investing.may_continue(appr):
        step = "confirm_warning"
    elif not accepted:
        step = "terms"
    else:
        step = "open_account"
    return {"next_step": step, "offered_by_landlord": investing.org_enabled_for(uid), "terms_accepted": accepted,
            "appropriateness": appropriateness_json(appr)}


REASON_KEYS = {
    "Je gaf aan dat een belegging niet in waarde kan dalen. Dat kan wel.": "thinks_no_loss",
    "Een verlies kan je huur of vaste lasten in gevaar brengen.": "cannot_bear_loss",
    "Je hebt dit geld binnen een jaar nodig. Beleggen is voor geld dat je langer kunt missen.": "short_horizon",
    "Je doel past niet bij beleggen voor de langere termijn.": "goal_mismatch",
    "Je kennis en ervaring met beleggen zijn nog beperkt.": "limited_knowledge",
}


def appropriateness_json(a):
    if not a:
        return None
    reasons = json.loads(a["reasons_json"])
    return {"result": a["result"], "reasons": reasons, "reason_keys": [REASON_KEYS.get(r, "other") for r in reasons], "created_at": a["created_at"],
            "warning_confirmed_at": a["warning_confirmed_at"], "may_continue": investing.may_continue(a),
            "requires_confirmation": a["result"] == "niet_passend" and not a["warning_confirmed_at"],
            "confirmation_text": WARNING_CONFIRMATION if a["result"] == "niet_passend" else None}


# ------------------------------------------------------------ overview

@bp.route("/invest", methods=["GET"])
@tenant_api
def overview():
    acct = invest_guard()
    uid = g.api_user["id"]
    p = investing.partner()
    out = {"partner": {"name": p.display_name, "sandbox": p.is_sandbox}, "role_text": investing.role_text(p),
           "separation_text": investing.SEPARATION_TEXT, "risk_text": investing.RISK_TEXT, "offered_by_landlord": investing.org_enabled_for(uid),
           "account": account_json(acct) if acct and acct["status"] != "draft" else None, "onboarding": None, "summary": None,
           "chart": None, "chart_net_deposits": None, "costs": None, "withdrawals": [], "minimum_order": money(investing.MIN_ORDER_CENTS)}
    if not acct or acct["status"] == "draft":
        out["onboarding"] = onboarding_json(uid, acct)
        return jsonify(out)
    if acct["status"] in ("active", "closed"):
        s = investing.summary(acct)
        out["summary"] = summary_json(s)
        out["chart"], out["chart_net_deposits"] = chart_json(acct["id"])
        out["costs"] = costs_json(investing.costs(max(s["total"], 0), acct["portfolio"], s["fee_rate_bps"])) if acct["portfolio"] else None
        out["withdrawals"] = [withdrawal_json(w) for w in investing.pending_withdrawals(acct["id"])[:5]]
    return jsonify(out)


@bp.route("/invest/portfolios", methods=["GET"])
@tenant_api
def portfolios():
    acct = invest_guard()
    raw = request.args.get("amount_cents", "100000")
    if not raw.isdigit():
        raise field_error("amount_cents", "Geef een bedrag in centen.")
    amount = min(max(int(raw), investing.MIN_ORDER_CENTS), 10_000_000)
    fee = acct["fee_rate_bps"] if acct and acct["fee_rate_bps"] is not None else investing.fee_bps()
    return jsonify({"amount": money(amount), "fee_rate_bps": fee, "current": acct["portfolio"] if acct else None,
                    "items": [portfolio_json(c) | {"costs": costs_json(investing.costs(amount, c, fee)),
                                                   "scenarios": scenarios_json(investing.scenarios(amount, c, fee))}
                              for c in investing.PORTFOLIOS],
                    "risk_text": investing.RISK_TEXT, "advice_note": "Depiqo geeft geen advies. Je kiest zelf."})


# ------------------------------------------------------------ onboarding

@bp.route("/invest/appropriateness", methods=["GET"])
@tenant_api
def appropriateness():
    acct = invest_guard()
    return jsonify({"version": investing.QUESTIONNAIRE_VERSION,
                    "questions": [{"key": q["key"], "text": q["text"], "options": [{"value": v, "label": label} for v, label, _ in q["options"]]}
                                  for q in investing.QUESTIONS],
                    "latest": appropriateness_json(investing.latest_appropriateness(g.api_user["id"])),
                    "can_answer": (not acct or acct["status"] == "draft") and investing.org_enabled_for(g.api_user["id"])})


@bp.route("/invest/appropriateness", methods=["POST"])
@tenant_api
def appropriateness_answer():
    acct = invest_guard()
    uid = g.api_user["id"]
    if acct and acct["status"] != "draft":
        raise ApiError(409, "account_exists", "Je hebt al een beleggingsrekening.")
    if not investing.org_enabled_for(uid):
        raise ApiError(409, "invest_not_offered", "Je verhuurder biedt Beleggen niet meer aan. Een nieuwe rekening openen kan niet.")
    answers = body().get("answers")
    if not isinstance(answers, dict):
        raise field_error("answers", "Stuur je antwoorden als object: vraag -> antwoord.")
    missing = {q["key"]: "Beantwoord deze vraag." for q in investing.QUESTIONS
               if answers.get(q["key"]) not in {v for v, _, _ in q["options"]}}
    if missing:
        raise ApiError(422, "validation_failed", "Beantwoord alle vragen.", missing)
    try:
        a = investing.record_appropriateness(uid, answers)
    except investing.InvestError as exc:
        raise rejected(exc)
    _audit("appropriateness", {"result": a["result"], "score": a["score"]})
    return jsonify(appropriateness_json(a) | {"risk_text": investing.RISK_TEXT}), 201


@bp.route("/invest/appropriateness/confirm", methods=["POST"])
@tenant_api
def appropriateness_confirm():
    invest_guard()
    true_field(body(), "confirm", "Bevestig dat je de waarschuwing hebt gelezen en toch verder wilt.")
    try:
        investing.confirm_warning(g.api_user["id"])
    except investing.InvestError as exc:
        raise rejected(exc)
    _audit("appropriateness_warning_confirmed")
    return jsonify(appropriateness_json(investing.latest_appropriateness(g.api_user["id"])))


@bp.route("/invest/terms", methods=["GET"])
@tenant_api
def terms():
    acct = invest_guard()
    t = investing.terms()
    return jsonify(t | {"accepted": {"partner_version": acct["terms_partner_version"], "partner_at": acct["terms_partner_at"],
                                     "depiqo_version": acct["terms_depiqo_version"], "depiqo_at": acct["terms_depiqo_at"]} if acct else None,
                        "risk_text": investing.RISK_TEXT})


@bp.route("/invest/terms", methods=["POST"])
@tenant_api
def terms_accept():
    acct = invest_guard()
    uid = g.api_user["id"]
    data = body()
    true_field(data, "accept_partner", "Ga akkoord met de voorwaarden van de partner.")
    true_field(data, "accept_depiqo", "Ga akkoord met de voorwaarden van Depiqo Invest.")
    t = investing.terms()
    if data.get("partner_version") != t["partner"]["version"] or data.get("depiqo_version") != t["depiqo"]["version"]:
        raise ApiError(409, "terms_outdated", "De voorwaarden zijn gewijzigd. Lees de nieuwe versie en ga opnieuw akkoord.",
                       {"partner_version": t["partner"]["version"], "depiqo_version": t["depiqo"]["version"]})
    if not acct or acct["status"] != "draft" or not investing.may_continue(investing.latest_appropriateness(uid)):
        raise ApiError(409, "invest_rejected", "Doe eerst de kennis- en ervaringstoets." if not acct or acct["status"] == "draft"
                       else "Je rekening is al geopend.")
    if not investing.org_enabled_for(uid):
        raise ApiError(409, "invest_not_offered", "Je verhuurder biedt Beleggen niet meer aan. Een nieuwe rekening openen kan niet.")
    db.run("UPDATE invest_accounts SET terms_partner_version = ?, terms_partner_at = ?, terms_depiqo_version = ?, terms_depiqo_at = ? "
           "WHERE id = ? AND status = 'draft'", (t["partner"]["version"], now_iso(), t["depiqo"]["version"], now_iso(), acct["id"]))
    _audit("terms_accepted", {"partner": t["partner"]["version"], "depiqo": t["depiqo"]["version"]})
    return jsonify({"accepted": True, "partner_version": t["partner"]["version"], "depiqo_version": t["depiqo"]["version"]})


@bp.route("/invest/account", methods=["POST"])
@tenant_api
@idempotent()
def open_account():
    acct = invest_guard()
    uid = g.api_user["id"]
    portfolio = body().get("portfolio")
    if portfolio not in investing.PORTFOLIOS:
        raise field_error("portfolio", "Kies een portefeuille: defensief, neutraal of offensief.")
    t = investing.terms()
    if not acct or acct["status"] != "draft":
        raise ApiError(409, "invest_rejected", "Doe eerst de kennis- en ervaringstoets." if not acct else "Je rekening is al geopend.")
    if acct["terms_partner_version"] != t["partner"]["version"] or acct["terms_depiqo_version"] != t["depiqo"]["version"]:
        raise ApiError(409, "terms_not_accepted", "Ga eerst akkoord met de huidige voorwaarden (POST /invest/terms).")
    try:
        investing.choose_portfolio(uid, portfolio)
        acct = investing.open_account(uid, True, True)
    except investing.InvestError as exc:
        raise rejected(exc)
    _audit("account_opened", {"portfolio": portfolio})
    return jsonify({"account": account_json(acct), "message": "Je beleggingsrekening wordt geopend bij de partner."}), 201


@bp.route("/invest/deposit-instructions", methods=["GET"])
@tenant_api
def deposit_instructions():
    acct = active_account()
    try:
        p = investing.partner_for(acct)
        i = p.deposit_instructions(acct)
    except investing.InvestError as exc:
        raise rejected(exc)
    return jsonify({"iban": i["iban"], "beneficiary": i["beneficiary"], "reference": i["reference"], "sandbox": p.is_sandbox,
                    "note": "Maak geld over vanaf een rekening op je eigen naam en vermeld altijd het kenmerk. Je borg gebruik je hier nooit voor."})


@bp.route("/invest/sandbox/deposit", methods=["POST"])
@sandbox_only
@tenant_api
@idempotent(required=True)
def sandbox_deposit():
    acct = active_account()
    p = investing.partner()
    if not (p.available and p.is_sandbox):
        raise ApiError(404, "not_found", "Alleen in de sandbox.")
    amount = int_amount(body())
    try:
        result = investing.simulate_deposit(acct, amount)
    except investing.InvestError as exc:
        raise rejected(exc)
    _audit("storten", {"amount_cents": amount, "sandbox": True})
    return jsonify({"result": result, "summary": summary_json(investing.summary(acct))}), 201


def int_amount(data, name="amount_cents"):
    v = data.get(name)
    if not isinstance(v, int) or isinstance(v, bool) or v <= 0:
        raise field_error(name, "Geef een bedrag in centen, groter dan nul.")
    return v


# ------------------------------------------------------------ quote and order

@bp.route("/invest/orders/quote", methods=["POST"])
@tenant_api
def quote():
    acct = active_account()
    data = body()
    side = data.get("side")
    if side not in ("buy", "sell", "switch"):
        raise field_error("side", "Kies buy, sell of switch.")
    s = investing.summary(acct)
    rate = s["fee_rate_bps"]
    sell_all = False
    portfolio = acct["portfolio"]
    try:
        if side in ("buy", "switch"):
            investing.require_offered(g.api_user["id"])
    except investing.InvestError as exc:
        raise rejected(exc)
    if acct["pending_switch"]:
        raise ApiError(409, "invest_rejected", "Je portefeuille wordt nog gewisseld. Wacht tot dat klaar is.")
    if side == "buy":
        amount = int_amount(data)
        if amount < investing.MIN_ORDER_CENTS:
            raise field_error("amount_cents", "Je koopt voor minimaal € 25.", "amount_below_minimum")
        c = investing.costs(amount, portfolio, rate)
        sc = scenarios_json(investing.scenarios(amount, portfolio, rate))
    elif side == "sell":
        sell_all = data.get("sell_all") is True
        amount = s["sellable"] if sell_all else int_amount(data)
        if not sell_all and amount < investing.MIN_ORDER_CENTS:
            raise field_error("amount_cents", "Je verkoopt voor minimaal € 25, of kies sell_all.", "amount_below_minimum")
        c = investing.costs(amount, portfolio, rate)
        sc = None
    else:
        portfolio = data.get("portfolio")
        if portfolio not in investing.PORTFOLIOS or portfolio == acct["portfolio"]:
            raise field_error("portfolio", "Kies een andere portefeuille.")
        amount = max(s["total"], investing.MIN_ORDER_CENTS)
        c = investing.costs(amount, portfolio, rate)
        sc = scenarios_json(investing.scenarios(amount, portfolio, rate))
    t = now()
    key = "q_" + token()[:32]
    payload = {
        "quote_id": key, "side": side, "amount": money(amount), "sell_all": sell_all, "portfolio": portfolio_json(portfolio),
        "costs": costs_json(c) if side != "sell" else {"transactions": money(c["tx"]), "transaction_cost_bps": c["tx_bps"],
                                                        "note": "Bij verkopen rekent de partner geen extra kosten. De servicekosten lopen door over wat belegd blijft."},
        "scenarios": sc, "risk_text": investing.RISK_TEXT, "separation_text": investing.SEPARATION_TEXT, "role_text": investing.role_text(),
        "execution_note": "De partner voert je order uit tegen de volgende koers." if side != "switch" else
        "Eerst wordt alles verkocht, daarna wordt de nieuwe portefeuille gekocht met de opbrengst. Tot dat klaar is, blijft je huidige portefeuille staan.",
        "available": money(s["available"]), "sellable": money(s["sellable"]), "current_value": money(s["total"]),
        "requires_risk_acknowledgement": True,
        "created_at": t.isoformat(timespec="seconds"), "expires_at": (t + QUOTE_TTL).isoformat(timespec="seconds"),
    }
    db.run("INSERT INTO invest_quotes (quote_key, user_id, account_id, side, amount_cents, sell_all, portfolio, fee_bps, payload_json, created_at, expires_at) "
           "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
           (key, g.api_user["id"], acct["id"], side, None if sell_all else amount, 1 if sell_all else 0, portfolio, rate, dumps(payload),
            payload["created_at"], payload["expires_at"]))
    return jsonify(payload), 201


@bp.route("/invest/orders", methods=["POST"])
@tenant_api
@idempotent(required=True)
def place_order():
    acct = active_account()
    data = body()
    q = db.one("SELECT * FROM invest_quotes WHERE quote_key = ? AND user_id = ?", (data.get("quote_id") or "", g.api_user["id"]))
    if not q or q["account_id"] != acct["id"]:
        raise ApiError(404, "quote_not_found", "Deze offerte bestaat niet. Vraag eerst een offerte op.")
    if q["used_at"]:
        raise ApiError(409, "quote_used", "Deze offerte is al gebruikt. Vraag een nieuwe offerte op.")
    if q["expires_at"] <= now_iso():
        raise ApiError(409, "quote_expired", "Deze offerte is verlopen (na 10 minuten). Vraag een nieuwe offerte op.")
    true_field(data, "risk_acknowledged", "Bevestig dat je de kosten en het risico hebt gelezen.")
    claimed = db.get_db().execute("UPDATE invest_quotes SET used_at = ? WHERE id = ? AND used_at IS NULL", (now_iso(), q["id"])).rowcount
    if claimed != 1:
        raise ApiError(409, "quote_used", "Deze offerte is al gebruikt. Vraag een nieuwe offerte op.")
    try:
        if q["side"] == "switch":
            investing.switch_portfolio(acct, q["portfolio"], True)
            order = db.one("SELECT * FROM invest_orders WHERE account_id = ? AND purpose = 'switch_sell' ORDER BY id DESC LIMIT 1", (acct["id"],))
            fresh = investing.account_for_user(g.api_user["id"])
            if not fresh["pending_switch"]:
                order = None  # nothing to sell: the portfolio changed at once
        else:
            order = investing.place_order(acct, q["side"], q["amount_cents"] or 0, sell_all=bool(q["sell_all"]))
    except investing.InvestError as exc:
        db.run("UPDATE invest_quotes SET used_at = NULL WHERE id = ?", (q["id"],))
        raise rejected(exc)
    if order:
        db.run("UPDATE invest_quotes SET order_id = ? WHERE id = ?", (order["id"], q["id"]))
    action = {"buy": "kopen", "sell": "verkopen", "switch": "wisselen"}[q["side"]]
    _audit(action, {"quote": q["quote_key"], "order": order["id"] if order else None, "risk_acknowledged": True})
    messages = {"buy": "Je kooporder staat klaar. De partner voert hem uit tegen de volgende koers.",
                "sell": "Je verkooporder staat klaar. De partner voert hem uit tegen de volgende koers.",
                "switch": "Je portefeuille wordt gewisseld: eerst verkopen, daarna kopen."}
    return jsonify({"order": order_json(order) if order else None, "message": messages[q["side"]],
                    "account": account_json(investing.account_for_user(g.api_user["id"]))}), 201


@bp.route("/invest/orders", methods=["GET"])
@tenant_api
def orders():
    acct = active_or_closed()
    limit, cursor = page_args()
    rows = _by_id("SELECT * FROM invest_orders WHERE account_id = ?", acct["id"], cursor, limit)
    return jsonify(paged(rows, limit, lambda r: [r["id"]], order_json))


def active_or_closed():
    acct = invest_guard()
    if not acct or acct["status"] not in ("active", "closed"):
        raise ApiError(409, "account_not_active", "Je beleggingsrekening is nog niet actief.")
    return acct


def _by_id(sql, account_id, cursor, limit):
    if cursor:
        if len(cursor) != 1 or not isinstance(cursor[0], int):
            raise ApiError(400, "invalid_cursor", "Deze cursor is niet geldig.")
        return db.all_(sql + " AND id < ? ORDER BY id DESC LIMIT ?", (account_id, cursor[0], limit + 1))
    return db.all_(sql + " ORDER BY id DESC LIMIT ?", (account_id, limit + 1))


# ------------------------------------------------------------ withdrawals

@bp.route("/invest/iban", methods=["POST"])
@tenant_api
@idempotent()
def register_iban():
    acct = active_account()
    data = body()
    iban = data.get("iban") if isinstance(data.get("iban"), str) else ""
    code = data.get("code") if isinstance(data.get("code"), str) else None
    try:
        usable = investing.register_own_iban(acct, g.api_user, iban, code)
    except investing.InvestError as exc:
        raise rejected(exc)
    _audit("rekening")
    now_ = usable <= now_iso()
    return jsonify({"account": account_json(investing.account_for_user(g.api_user["id"])), "usable_from": usable, "usable_now": now_,
                    "message": "Je rekeningnummer is geregistreerd." + ("" if now_ else f" Je kunt het gebruiken vanaf {investing._dt(usable)}.")
                    + " Je krijgt hierover een e-mail.",
                    "cooling_off_days": investing.COOLING_OFF.days}), 201


@bp.route("/invest/withdrawals", methods=["POST"])
@tenant_api
@idempotent(required=True)
def withdraw():
    acct = active_account()
    amount = int_amount(body())
    try:
        iid = investing.withdraw(acct, amount)
    except investing.InvestError as exc:
        raise rejected(exc)
    _audit("opnemen", {"amount_cents": amount})
    row = db.one("SELECT * FROM invest_instructions WHERE id = ?", (iid,))
    return jsonify({"withdrawal": withdrawal_json(investing.withdrawal_view(row)),
                    "message": "Je opname staat klaar. De partner maakt het geld over naar je eigen rekening."}), 201


@bp.route("/invest/withdrawals", methods=["GET"])
@tenant_api
def withdrawals():
    acct = active_or_closed()
    limit, cursor = page_args()
    rows = _by_id("SELECT * FROM invest_instructions WHERE kind = 'withdraw' AND account_id = ?", acct["id"], cursor, limit)
    return jsonify(paged(rows, limit, lambda r: [r["id"]], lambda r: withdrawal_json(investing.withdrawal_view(r))))


@bp.route("/invest/transactions", methods=["GET"])
@tenant_api
def transactions():
    acct = active_or_closed()
    limit, cursor = page_args()
    if cursor:
        if len(cursor) != 2 or not isinstance(cursor[0], str) or not isinstance(cursor[1], int):
            raise ApiError(400, "invalid_cursor", "Deze cursor is niet geldig.")
        rows = db.all_("SELECT * FROM invest_transactions WHERE account_id = ? AND (day < ? OR (day = ? AND id < ?)) "
                       "ORDER BY day DESC, id DESC LIMIT ?", (acct["id"], cursor[0], cursor[0], cursor[1], limit + 1))
    else:
        rows = db.all_("SELECT * FROM invest_transactions WHERE account_id = ? ORDER BY day DESC, id DESC LIMIT ?", (acct["id"], limit + 1))
    return jsonify(paged(rows, limit, lambda r: [r["day"], r["id"]], transaction_json))


# ------------------------------------------------------------ statements and fee change

@bp.route("/invest/statements", methods=["GET"])
@tenant_api
def statements():
    acct = active_or_closed()
    out = []
    for period in investing.statement_periods(acct):
        d = parse_date(period + "-01")
        out.append({"period": period, "label": f"{MONTHS_NL[d.month - 1]} {d.year}", "download_path": f"/api/v1/invest/statements/{period}"})
    return jsonify({"items": out})


@bp.route("/invest/statements/<period>", methods=["GET"])
@tenant_api
def statement(period):
    acct = active_or_closed()
    if period not in investing.statement_periods(acct):
        raise ApiError(404, "not_found", "Voor deze maand is er geen overzicht.")
    _audit("statement", {"period": period})
    return Response(investing.statement_pdf(acct, period, g.api_user["name"]), mimetype="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename=beleggen-{acct['reference']}-{period}.pdf"})


@bp.route("/invest/fee-change", methods=["GET"])
@tenant_api
def fee_change():
    acct = active_or_closed()
    pending = acct["pending_fee_bps"]
    return jsonify({"current_bps": acct["fee_rate_bps"], "pending_bps": pending, "proposed_at": acct["pending_fee_notified_at"],
                    "accept_text": f"Ik ga akkoord met de nieuwe servicevergoeding van {investing._pct(pending)} per jaar, vanaf vandaag." if pending is not None else None,
                    "note": "De nieuwe vergoeding geldt alleen als je akkoord gaat, en dan pas vanaf die dag. Tot dan blijft je huidige vergoeding gelden."})


@bp.route("/invest/fee-change", methods=["POST"])
@tenant_api
@idempotent()
def fee_change_accept():
    acct = active_or_closed()
    true_field(body(), "accept", "Vink aan dat je akkoord gaat met de nieuwe servicevergoeding.")
    try:
        investing.accept_fee_change(acct)
    except investing.InvestError as exc:
        raise rejected(exc)
    _audit("servicevergoeding")
    return jsonify({"account": account_json(investing.account_for_user(g.api_user["id"])),
                    "message": "Je nieuwe servicevergoeding geldt vanaf vandaag."})
