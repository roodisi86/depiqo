"""Tests for version 0.5.0: Depiqo Invest against the sandbox investment partner.

    python -m unittest discover -s tests -v
"""
import json
import os
import shutil
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.util import today as local_today  # noqa: E402
from app import db, finance, investing, services  # noqa: E402
from app import states as S  # noqa: E402
from app.partners import sign_webhook  # noqa: E402
import test_v030 as tv  # noqa: E402  (module import: its classes must not be collected twice)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASSEND = {"experience": "soms", "funds": "pot", "risk": "beide", "spread": "kleiner", "horizon": "lang", "loss": "ja",
           "drop": "wachten", "goal": "opbouwen"}
NIET = {**PASSEND, "risk": "stijgt", "loss": "nee"}


class Base(tv.Base):
    def setUp(self):
        super().setUp()
        with self.app.app_context():
            db.run("UPDATE organizations SET invest_enabled = 1 WHERE id = ?", (self.org,))

    def tenant(self):
        """A tenant of org A with a Depiqo deposit account (identity verified), logged in. Returns (client, user_id, deposit)."""
        mgr, d = self._to_awaiting_payment()
        tenant = self.app.test_client()
        tenant.post("/login", data={"email": "tess@huurder.test", "password": tv.PW, "csrf_token": self.anon(tenant)})
        return tenant, self.uid("tess@huurder.test"), d

    def onboard(self, c, portfolio="neutraal", answers=PASSEND, confirm=False):
        c.post("/wallet/beleggen/toets", data={**answers, "csrf_token": self.csrf(c, "/wallet/beleggen/toets")})
        if confirm:
            c.post("/wallet/beleggen/toets/uitslag", data={"confirm": "1", "csrf_token": self.csrf(c, "/wallet/beleggen/toets/uitslag")})
        c.post("/wallet/beleggen/portefeuille", data={"portfolio": portfolio, "csrf_token": self.csrf(c, "/wallet/beleggen/portefeuille")})
        c.post("/wallet/beleggen/voorwaarden", data={"accept_partner": "1", "accept_depiqo": "1",
                                                     "csrf_token": self.csrf(c, "/wallet/beleggen/voorwaarden")})

    def acct(self, uid):
        with self.app.app_context():
            return investing.account_for_user(uid)

    def act(self, c, action, **data):
        if action == "kopen":
            data.setdefault("confirm", "1")  # 0.5.2: a purchase is confirmed after seeing costs and risk
        return c.post(f"/wallet/beleggen/actie/{action}", data={**data, "csrf_token": self.csrf(c, "/wallet/beleggen")}, follow_redirects=True)

    def day(self, n=1):
        with self.ctx():
            investing.advance_day(n)

    def funded(self, deposit="500,00", buy=None):
        c, uid, d = self.tenant()
        self.onboard(c)
        self.act(c, "storten", amount=deposit)
        if buy:
            self.act(c, "kopen", amount=buy)
        return c, uid, d


# ====================================================================== appropriateness

class AppropriatenessTest(Base):
    def test_logic(self):
        self.assertEqual(investing.assess(PASSEND)["result"], "passend")
        cases = {"risk": "stijgt", "loss": "nee", "horizon": "kort", "goal": "snel"}
        for key, value in cases.items():
            out = investing.assess({**PASSEND, key: value})
            self.assertEqual(out["result"], "niet_passend", key)
            self.assertTrue(out["reasons"])
        low = investing.assess({**PASSEND, "experience": "nooit", "funds": "weet_niet", "spread": "weet_niet", "drop": "twijfel"})
        self.assertEqual((low["result"], low["score"]), ("niet_passend", 9))
        with self.assertRaises(investing.InvestError):
            investing.assess({k: v for k, v in PASSEND.items() if k != "goal"})
        self.assertGreaterEqual(len(investing.QUESTIONS), 6)
        self.assertLessEqual(len(investing.QUESTIONS), 8)

    def test_not_passend_needs_explicit_confirmation(self):
        c, uid, _ = self.tenant()
        c.post("/wallet/beleggen/toets", data={**NIET, "csrf_token": self.csrf(c, "/wallet/beleggen/toets")})
        html = c.get("/wallet/beleggen/toets/uitslag").get_data(as_text=True)
        self.assertIn("Beleggen past mogelijk niet bij je", html)
        self.assertIn("Waarschuwing", html)
        self.assertEqual(c.get("/wallet/beleggen/portefeuille").status_code, 302)  # blocked until confirmed
        c.post("/wallet/beleggen/toets/uitslag", data={"csrf_token": self.csrf(c, "/wallet/beleggen/toets/uitslag")})  # box not ticked
        with self.app.app_context():
            a = investing.latest_appropriateness(uid)
        self.assertIsNone(a["warning_confirmed_at"])
        c.post("/wallet/beleggen/toets/uitslag", data={"confirm": "1", "csrf_token": self.csrf(c, "/wallet/beleggen/toets/uitslag")})
        with self.app.app_context():
            a = investing.latest_appropriateness(uid)
        self.assertEqual((a["result"], json.loads(a["answers_json"])["risk"], a["questionnaire_version"]), ("niet_passend", "stijgt", "2026-10"))
        self.assertTrue(a["warning_confirmed_at"] and a["created_at"])
        self.assertEqual(c.get("/wallet/beleggen/portefeuille").status_code, 200)


# ====================================================================== costs, scenarios, prices

class CostsAndPricesTest(Base):
    def test_cost_examples(self):
        c = investing.costs(100000, "neutraal")
        self.assertEqual((c["service_1y"], c["fund_1y"], c["tx"], c["total_1y"]), (250, 193, 0, 443))  # 0,1925% fund costs: 192,5 -> 193
        self.assertEqual((c["service_3y"], c["fund_3y"], c["total_3y"]), (750, 579, 1329))
        self.assertEqual(investing.costs(100000, "neutraal", fee_bps=50)["service_1y"], 500)
        sc = {s["key"]: s for s in investing.scenarios(100000, "offensief")}
        self.assertEqual(set(sc), {"gunstig", "neutraal", "ongunstig"})
        self.assertLess(sc["ongunstig"]["y3_result"], 0)
        c_, uid, _ = self.tenant()
        c_.post("/wallet/beleggen/toets", data={**PASSEND, "csrf_token": self.csrf(c_, "/wallet/beleggen/toets")})
        html = c_.get("/wallet/beleggen/portefeuille?bedrag=1.000,00").get_data(as_text=True)
        for text in ("Scenario's, geen voorspelling", "€ 4,43", "€ 13,29", "Servicekosten Depiqo (0,25% per jaar)", "Je kunt geld verliezen",
                     "Het depositogarantiestelsel geldt niet voor beleggingen", "Risico 4/7"):
            self.assertIn(text, html, text)

    def test_price_series_is_deterministic(self):
        a = [investing.price_1e4(f, "2025-06-30") for f in investing.FUNDS]
        saved = dict(investing._series)
        investing._series.clear()
        try:
            b = [investing.price_1e4(f, "2025-06-30") for f in investing.FUNDS]  # a fresh series gives the same prices
        finally:
            investing._series.update(saved)
        self.assertEqual(a, b)
        self.assertEqual(investing.price_1e4("geldmarkt", "2023-01-02"), 1_000_000)
        self.assertEqual(investing.price_1e4("geldmarkt", "2020-01-01"), 1_000_000)  # before the start: the first price
        self.assertTrue(all(investing.price_1e4(f, date(2026, 1, 1)) > 0 for f in investing.FUNDS))

    def test_allocation_and_rounding(self):
        parts = investing.allocate(12347, "defensief")
        self.assertEqual(sum(a for _, a in parts), 12347)
        self.assertEqual(dict(parts)["geldmarkt"], 4938 + 2)  # floor per fund, remainder to the largest weight (first of equals)
        self.assertEqual(investing.value_cents(8414, 1188429), 9999)  # 0,8414 x 118,8429 = 99,99
        self.assertEqual(investing.round_half_up(5, 10), 1)
        self.assertEqual(investing.round_half_up(4, 10), 0)


# ====================================================================== orders and execution

class OrderTest(Base):
    def test_buy_executes_at_the_next_price(self):
        c, uid, _ = self.funded("500,00")
        a = self.acct(uid)
        self.assertEqual(a["status"], "active")  # identity checked for the deposit account: activated at once in the sandbox
        self.act(c, "kopen", amount="400,00")
        with self.app.app_context():
            o = db.one("SELECT * FROM invest_orders")
        self.assertEqual((o["side"], o["status"], o["amount_cents"]), ("buy", "pending", 40000))
        with self.ctx():
            self.assertEqual(investing.summary(a)["available"], 10000)  # reserved for the pending order
            next_day = investing.invest_day() + timedelta(days=1)
        self.day()
        with self.app.app_context():
            o = db.one("SELECT * FROM invest_orders")
            fills = db.all_("SELECT * FROM invest_fills")
            cash = investing.cash_cents(a["id"])
        self.assertEqual(o["status"], "executed")
        for f in fills:
            self.assertEqual(f["price_1e4"], investing.price_1e4(f["fund"], next_day))
            self.assertLessEqual(f["units_1e4"] * f["price_1e4"], 1_000_000 * 40000)
        spent = sum(f["amount_cents"] for f in fills)
        self.assertLessEqual(spent, 40000)
        self.assertGreaterEqual(spent, 40000 - 3)  # units rounded down: at most a cent per fund stays as cash
        self.assertEqual((o["executed_amount_cents"], cash), (spent, 50000 - spent))
        html = c.get("/wallet/beleggen").get_data(as_text=True)
        self.assertIn("<polyline", html)
        self.assertIn("Uitgevoerd", html)

    def test_sell_withdraw_and_limits(self):
        c, uid, _ = self.funded("500,00", buy="400,00")
        self.day()
        r = self.act(c, "kopen", amount="10,00")
        self.assertIn("minimaal € 25", r.get_data(as_text=True))
        r = self.act(c, "kopen", amount="300,00")
        self.assertIn("niet genoeg geld", r.get_data(as_text=True))
        self.act(c, "verkopen", amount="100,00")
        # 0.5.2: withdrawals only to the tenant's registered own account (without 2FA: after a cooling-off period)
        r = self.act(c, "rekening", iban="NL00BANK1234")
        self.assertIn("IBAN) klopt niet", r.get_data(as_text=True))
        self.act(c, "rekening", iban="NL91 ABNA 0417 1643 00")
        self.assertIn("nieuwe rekeningnummer gebruiken vanaf", self.act(c, "opnemen", amount="100,00").get_data(as_text=True))
        with self.app.app_context():
            db.run("UPDATE invest_accounts SET own_iban_usable_from = '2000-01-01T00:00:00+00:00'")
        r = self.act(c, "opnemen", amount="100,00")
        self.assertIn("Je opname staat klaar", r.get_data(as_text=True))
        self.day()
        with self.app.app_context():
            sell = db.one("SELECT * FROM invest_orders WHERE side = 'sell'")
            out = db.one("SELECT * FROM invest_transactions WHERE kind = 'withdrawal'")
        self.assertEqual(sell["status"], "executed")
        self.assertGreaterEqual(sell["executed_amount_cents"], 10000)  # units rounded up: the proceeds cover the amount
        self.assertEqual(out["amount_cents"], -10000)
        self.act(c, "verkopen", all="1")
        self.day()
        with self.app.app_context():
            self.assertEqual(investing.units_by_fund(self.acct(uid)["id"]), {})

    def test_switch_portfolio_sells_then_buys(self):
        c, uid, _ = self.funded("500,00", buy="400,00")
        self.day()
        r = self.act(c, "wisselen", portfolio="offensief")
        self.assertIn("Bevestig", r.get_data(as_text=True))
        self.act(c, "wisselen", portfolio="offensief", confirm="1")
        self.day()  # the sale
        self.day()  # the purchase with the proceeds
        with self.app.app_context():
            orders = db.all_("SELECT purpose, side, status, portfolio FROM invest_orders ORDER BY id")
            units = investing.units_by_fund(self.acct(uid)["id"])
        self.assertEqual([tuple(o) for o in orders[1:]], [("switch_sell", "sell", "executed", "neutraal"), ("switch_buy", "buy", "executed", "offensief")])
        self.assertEqual(set(units), {"obligaties_wereld", "aandelen_wereld"})


# ====================================================================== fail closed

class FailClosedTest(Base):
    def test_no_partner_hides_and_refuses(self):
        c, uid, d = self.tenant()
        self.assertEqual(c.get("/wallet/beleggen").status_code, 200)
        for setting in ({"INVEST_PARTNER": ""}, {"INVEST_PARTNER": "onbekend"}, {"SANDBOX": False}):
            old = {k: self.app.config[k] for k in setting}
            self.app.config.update(setting)
            try:
                for path in ("/wallet/beleggen", "/wallet/beleggen/toets", "/wallet/beleggen/portefeuille"):
                    self.assertEqual(c.get(path).status_code, 404, (setting, path))
                html = c.get(f"/wallet/borg/{d['pid']}").get_data(as_text=True)
                self.assertIn("Nog niet beschikbaar", html)
                self.assertNotIn('href="/wallet/beleggen"', html)
                with self.ctx():
                    self.assertFalse(investing.partner().available)
                    with self.assertRaises(investing.InvestUnavailable):
                        investing.record_appropriateness(uid, PASSEND)
                body = json.dumps({"type": "deposit.received", "data": {"event_id": "x"}}).encode()
                r = self.app.test_client().post("/webhooks/invest/sandbox", data=body, headers={
                    "X-Depiqo-Signature": sign_webhook(body, self.app.config["INVEST_WEBHOOK_SECRET"]), "Content-Type": "application/json"})
                self.assertEqual(r.status_code, 404)
            finally:
                self.app.config.update(old)

    def test_org_toggle(self):
        c, uid, d = self.tenant()
        with self.app.app_context():
            db.run("UPDATE organizations SET invest_enabled = 0")
        self.assertEqual(c.get("/wallet/beleggen").status_code, 404)
        html = c.get(f"/wallet/borg/{d['pid']}").get_data(as_text=True)
        self.assertNotIn("Beleggen", html)
        st = self.client("staff@depiqo.test")
        st.post(f"/admin/beleggen/organisaties/{self.org}", data={"enabled": "1", "csrf_token": self.csrf(st, "/admin/beleggen")})
        self.assertEqual(c.get("/wallet/beleggen").status_code, 200)


# ====================================================================== privacy

class PrivacyTest(Base):
    def test_business_users_see_nothing(self):
        c, uid, d = self.funded("500,00", buy="400,00")
        self.day()
        with self.app.app_context():
            ref = self.acct(uid)["reference"]
        for email in ("admin@a.test", "manager@a.test", "finance@a.test", "viewer@a.test", "admin@b.test"):
            b = self.client(email)
            for path in ("/wallet/beleggen", "/wallet/beleggen/toets", "/wallet/beleggen/portefeuille", "/wallet/beleggen/voorwaarden",
                         "/wallet/beleggen/overzicht/2026-10.pdf", "/admin/beleggen"):
                self.assertEqual(b.get(path).status_code, 404, (email, path))
            self.assertEqual(b.post("/wallet/beleggen/actie/kopen", data={"amount": "50", "csrf_token": self.csrf(b)}).status_code, 404)
        for path in (f"/app/borgen/{d['pid']}", "/app", "/app/borgen", "/app/afstemming"):
            html = self.client("admin@a.test").get(path).get_data(as_text=True)
            for word in ("Beleggen", "belegging", ref, "Sandbox-beleggingspartner"):
                self.assertNotIn(word, html, (path, word))

    def test_staff_cannot_place_orders(self):
        st = self.client("staff@depiqo.test")
        self.assertEqual(st.get("/admin/beleggen").status_code, 200)
        for action in ("kopen", "verkopen", "opnemen"):
            self.assertEqual(st.post(f"/admin/beleggen/{action}", data={"csrf_token": self.csrf(st, "/admin/beleggen")}).status_code, 404)
        self.assertEqual(st.get("/wallet/beleggen").status_code, 404)  # staff are not tenants


# ====================================================================== doorbeleggen

class DoorbeleggenTest(Base):
    def agreed_with_invest(self):
        c, uid, d = self.funded("100,00")
        mgr = self.client("admin@a.test")
        acct = self.account(d)
        anon = self.app.test_client()
        self.webhook(anon, "deposit.received", {"event_id": "dr1", "external_id": acct["external_id"], "amount_cents": 200000, "ref": "r"})
        self.webhook(anon, "account.blocked", {"event_id": "db1", "external_id": acct["external_id"]})
        token = self.csrf(mgr)
        mgr.post(f"/app/borgen/{d['pid']}/vertrek", data={"move_out_date": local_today().isoformat(), "csrf_token": token})
        mgr.post(f"/app/borgen/{d['pid']}/afrekening-opslaan", data={"cat_0": "damage", "desc_0": "Muur", "amount_0": "150,00", "csrf_token": token})
        mgr.post(f"/app/borgen/{d['pid']}/afrekening-voorstellen", data={"csrf_token": token})
        c.post(f"/wallet/borg/{d['pid']}/akkoord", data={"csrf_token": self.csrf(c, f"/wallet/borg/{d['pid']}")})
        self.assertEqual(self.row(d["pid"])["status"], S.AGREED)
        return c, uid, self.row(d["pid"]), acct

    def choose(self, c, d, **extra):
        return c.post(f"/wallet/beleggen/doorbeleggen/{d['pid']}", data={"destination": "invest", **extra,
                                                                         "csrf_token": self.csrf(c, f"/wallet/borg/{d['pid']}")},
                      follow_redirects=True)

    def test_explicit_choice_payout_to_partner_and_invest_deposit(self):
        c, uid, d, bank_acct = self.agreed_with_invest()
        html = c.get(f"/wallet/borg/{d['pid']}").get_data(as_text=True)
        self.assertIn("Waar wil je jouw deel ontvangen?", html)
        self.assertIn("Bevestig dat je", self.choose(c, d).get_data(as_text=True))  # no confirmation: not stored
        with self.app.app_context():
            self.assertIsNone(investing.payout_choice(d["id"]))
        self.choose(c, d, confirm="1")
        with self.app.app_context():
            choice = investing.payout_choice(d["id"])
            ref = self.acct(uid)["reference"]
        self.assertEqual((choice["status"], choice["reference"], choice["destination_iban"]), ("chosen", ref, investing.SandboxInvest.client_money_iban))
        self.assertTrue(choice["chosen_at"])
        fin = self.client("finance@a.test")
        page = fin.get(f"/app/borgen/{d['pid']}").get_data(as_text=True)
        self.assertIn("naar de rekening van de huurder", page)
        self.assertNotIn(ref, page)
        self.assertNotIn("belegg", page.lower())
        fin.post(f"/app/borgen/{d['pid']}/uitbetalen", data={"csrf_token": self.csrf(fin)})
        with self.app.app_context():
            payload = json.loads(db.scalar("SELECT payload_json FROM bank_instructions WHERE kind = 'release'"))
            sbx = json.loads(db.scalar("SELECT response_json FROM sandbox_requests WHERE kind = 'release'"))
        self.assertEqual(payload["tenant_destination"], {"type": "invest", "iban": investing.SandboxInvest.client_money_iban, "reference": ref})
        self.assertTrue(sbx["provider_ref"])
        before = self.cash(uid)
        # 0.3 verification still applies: a wrong amount records nothing on the investment side
        r = self.webhook(self.app.test_client(), "payout.completed", {"event_id": "pw", "external_id": bank_acct["external_id"],
                                                                      "tenant_cents": 185001, "landlord_cents": 15000, "ref": "p"})
        self.assertEqual(r.get_json()["result"], "mismatch")
        self.assertEqual(self.cash(uid), before)
        r = self.webhook(self.app.test_client(), "payout.completed", {"event_id": "pok", "external_id": bank_acct["external_id"],
                                                                      "tenant_cents": 185000, "landlord_cents": 15000, "ref": "p"})
        self.assertEqual(r.get_json()["result"], "processed")
        self.assertEqual(self.cash(uid), before + 185000)
        with self.app.app_context():
            tx = db.one("SELECT * FROM invest_transactions WHERE kind = 'payout_in'")
            self.assertEqual(investing.payout_choice(d["id"])["status"], "paid")
        self.assertEqual((tx["amount_cents"], tx["external_ref"]), (185000, f"payout:{d['pid']}"))
        self.assertNotIn("belegg", fin.get(f"/app/borgen/{d['pid']}").get_data(as_text=True).lower())

    def test_own_account_is_the_default_and_can_be_restored(self):
        c, uid, d, _ = self.agreed_with_invest()
        self.choose(c, d, confirm="1")
        c.post(f"/wallet/beleggen/doorbeleggen/{d['pid']}", data={"destination": "own", "csrf_token": self.csrf(c, f"/wallet/borg/{d['pid']}")})
        with self.ctx():
            self.assertIsNone(investing.payout_destination(self.row(d["pid"])))
            services.start_payout(self.row(d["pid"]), None)
            payload = json.loads(db.scalar("SELECT payload_json FROM bank_instructions WHERE kind = 'release'"))
        self.assertNotIn("tenant_destination", payload)

    def cash(self, uid):
        with self.app.app_context():
            return investing.cash_cents(self.acct(uid)["id"])


# ====================================================================== fees and statements

class FeeAndStatementTest(Base):
    def test_fee_accrues_daily_and_is_charged_at_month_end(self):
        c, uid, _ = self.funded("1.000,00", buy="1.000,00")
        self.day()
        with self.ctx():
            a = self.acct(uid)
            start = investing.invest_day()
            days_to_end = ((start.replace(day=28) + timedelta(days=4)).replace(day=1) - start).days  # through the last day of the month
            expected = 0
            units = investing.units_by_fund(a["id"])
            for i in range(0, days_to_end):
                d = start + timedelta(days=i)
                expected += sum(investing.value_cents(u, investing.price_1e4(f, d)) for f, u in units.items()) * 25 * 100 // 365
            investing.advance_day(days_to_end - 1)
            fee = db.one("SELECT * FROM invest_transactions WHERE kind = 'fee'")
        self.assertIsNotNone(fee)
        self.assertEqual(-fee["amount_cents"], investing.round_half_up(expected, investing.MICRO))
        self.assertIn("Servicekosten Depiqo", fee["description"])
        html = c.get("/wallet/beleggen").get_data(as_text=True)
        self.assertIn("Servicekosten Depiqo", html)
        with self.ctx():
            ue = finance.unit_economics(investing.invest_day().strftime("%Y-%m"))
        self.assertEqual(ue["invest"]["accounts"], 1)
        self.assertGreater(ue["invest"]["aum"], 0)
        self.assertIn("Depiqo Invest", self.client("staff@depiqo.test").get("/admin/unit-economics").get_data(as_text=True))

    def test_fee_setting_and_charge_now(self):
        c, uid, _ = self.funded("1.000,00", buy="1.000,00")
        self.day(3)
        st = self.client("staff@depiqo.test")
        st.post("/admin/beleggen/servicevergoeding", data={"fee_pct": "0,50", "csrf_token": self.csrf(st, "/admin/beleggen")})
        with self.ctx():
            self.assertEqual(investing.fee_bps(), 50)
        st.post("/admin/beleggen/servicekosten", data={"csrf_token": self.csrf(st, "/admin/beleggen")})
        with self.app.app_context():
            self.assertGreaterEqual(db.scalar("SELECT COUNT(*) FROM invest_transactions WHERE kind = 'fee'"), 1)
            self.assertEqual(db.scalar("SELECT fee_accrued_micro FROM invest_accounts"), 0)  # nothing left to charge

    def test_statement_pdf(self):
        c, uid, _ = self.funded("500,00", buy="400,00")
        self.day()
        with self.ctx():
            a = self.acct(uid)
            period = investing.statement_periods(a)[0]
            raw = investing.statement_pdf(a, period, "Tess Huurder", compress=False).decode("latin-1")
            data = investing.statement_data(a, period)
        for text in (f"Maandoverzicht beleggingsrekening {period}", "Tess Huurder", a["reference"], "Stortingen", "500,00",
                     "Gekocht: Neutraal", "Servicekosten Depiqo", "Waarde aan het eind", "nooit belegd"):
            self.assertIn(text, raw, text)
        self.assertEqual(data["deposits"], 50000)
        r = c.get(f"/wallet/beleggen/overzicht/{period}.pdf")
        self.assertEqual((r.status_code, r.data[:5]), (200, b"%PDF-"))
        self.assertEqual(c.get("/wallet/beleggen/overzicht/1999-01.pdf").status_code, 404)


# ====================================================================== idempotency

class IdempotencyTest(Base):
    def send(self, etype, data, secret=None):
        body = json.dumps({"type": etype, "data": data}).encode()
        sig = sign_webhook(body, secret or self.app.config["INVEST_WEBHOOK_SECRET"])
        return self.app.test_client().post("/webhooks/invest/sandbox", data=body, headers={"X-Depiqo-Signature": sig, "Content-Type": "application/json"})

    def test_webhook_signature_and_duplicates(self):
        c, uid, _ = self.funded("100,00")
        ext = self.acct(uid)["external_id"]
        ev = {"event_id": "dep-1", "external_id": ext, "amount_cents": 5000, "ref": "bank-1"}
        self.assertEqual(self.send("deposit.received", ev, secret="wrong").status_code, 401)
        self.assertEqual(self.send("deposit.received", ev).get_json()["result"], "processed")
        self.assertEqual(self.send("deposit.received", ev).get_json()["result"], "duplicate")
        self.assertEqual(self.send("deposit.received", {**ev, "event_id": "dep-2"}).get_json()["result"], "ignored")  # same bank ref: once
        with self.app.app_context():
            self.assertEqual(investing.cash_cents(self.acct(uid)["id"]), 15000)

    def test_instruction_keys_and_confirmed_orders(self):
        c, uid, _ = self.funded("500,00", buy="400,00")
        with self.ctx():
            a = self.acct(uid)
            key = db.scalar("SELECT idempotency_key FROM invest_instructions WHERE kind = 'order'")
            first = db.scalar("SELECT id FROM invest_instructions WHERE kind = 'order'")
            self.assertEqual(investing._enqueue(a["id"], "sandbox", "order", {}, key), first)  # same key, same instruction
            p = investing.partner()
            self.assertEqual(p.place_order(a, {}, key), p.place_order(a, {}, key))
        self.day()
        with self.ctx():
            ev = db.one("SELECT payload_json FROM invest_events WHERE type = 'order.executed'")
            payload = {**json.loads(ev["payload_json"]), "event_id": "replay"}
            self.assertEqual(investing.handle_event("sandbox", "order.executed", payload), "ignored")  # already confirmed
            self.assertEqual(db.scalar("SELECT COUNT(DISTINCT external_ref) FROM invest_fills"), 1)


# ====================================================================== migration 007

class Migration007Test(Base):
    def test_applies_on_006(self):
        import glob
        src = os.path.join(ROOT, "migrations")
        old_dir = os.path.join(self.tmp, "m7")
        os.makedirs(old_dir)
        for f in sorted(glob.glob(os.path.join(src, "*.sql"))):
            if os.path.basename(f)[:3] < "007":
                shutil.copy(f, old_dir)
        path = os.path.join(self.tmp, "old7.sqlite3")
        db.migrate(path, old_dir)
        shutil.copy(os.path.join(src, "007_invest.sql"), old_dir)
        db.migrate(path, old_dir)
        conn = db.connect(path)
        self.assertEqual(conn.execute("SELECT offset_days FROM invest_sandbox_clock").fetchone()[0], 0)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(invest_accounts)")]
        self.assertIn("user_id", cols)
        self.assertNotIn("org_id", cols)  # accounts belong to a person, never to an organisation
        conn.close()


if __name__ == "__main__":
    unittest.main()
