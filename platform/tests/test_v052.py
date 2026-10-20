"""Regression tests for the review of Depiqo Invest 0.5.0 (version 0.5.2). One class per finding; the setups
follow the reviewer's probes (review05/probe_v050.py), the assertions check the corrected behaviour.

    python -m unittest discover -s tests -v
"""
import json
import os
import sys
import unittest
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import db, finance, investing, mfa, services  # noqa: E402
from app import states as S  # noqa: E402
from app.partners import sign_webhook  # noqa: E402
from app.util import now_iso  # noqa: E402
import test_v050 as T  # noqa: E402  (module import: its classes must not be collected twice)


class Base(T.Base):
    agreed_with_invest = T.DoorbeleggenTest.agreed_with_invest
    choose = T.DoorbeleggenTest.choose
    cash = T.DoorbeleggenTest.cash

    def payout_ok(self, bank_acct, tenant=185000, ev="pok"):
        return self.webhook(self.app.test_client(), "payout.completed", {"event_id": ev, "external_id": bank_acct["external_id"],
                                                                         "tenant_cents": tenant, "landlord_cents": 15000, "ref": "p"}).get_json()

    def to_month_end_and_one(self):
        """Advance the sandbox clock past the next month end."""
        for _ in range(40):
            with self.ctx():
                d0 = investing.invest_day()
            self.day(1)
            if (d0 + timedelta(days=1)).month != d0.month:
                return
        raise AssertionError("no month end within 40 days")

    def ledger_never_negative(self):
        with self.app.app_context():
            rows = db.all_("SELECT account_id, day, amount_cents FROM invest_transactions ORDER BY account_id, day, id")
        running = {}
        for r in rows:
            running[r["account_id"]] = running.get(r["account_id"], 0) + r["amount_cents"]
            self.assertGreaterEqual(running[r["account_id"]], 0, "cash below zero in the ledger")


# ====================================================================== H1 negative cash through the fee

class H1NegativeCashTest(Base):
    def test_sell_all_withdraw_then_month_end_never_negative(self):
        c, uid, _ = self.funded("500,00", buy="400,00")
        self.day(3)
        self.act(c, "verkopen", all="1")
        self.day(1)
        with self.ctx():
            a = self.acct(uid)
            s = investing.summary(a)
            owed = investing.fee_owed_cents(a)
        self.assertGreater(owed, 0)
        self.assertEqual(s["available"], s["cash"] - owed)  # the fee already owed is not available
        with self.app.app_context():
            db.run("UPDATE invest_accounts SET own_iban = 'NL91ABNA0417164300', own_iban_usable_from = ?", (now_iso(),))
        r = self.act(c, "opnemen", amount=f"{(s['available'] + 1) / 100:.2f}".replace(".", ","))
        self.assertIn("Je kunt alleen geld opnemen dat vrij", r.get_data(as_text=True))
        self.act(c, "opnemen", amount=f"{s['available'] / 100:.2f}".replace(".", ","))
        self.day(1)
        self.to_month_end_and_one()
        with self.ctx():
            a = self.acct(uid)
            cash = investing.cash_cents(a["id"])
            fee = -db.scalar("SELECT COALESCE(SUM(amount_cents), 0) FROM invest_transactions WHERE kind = 'fee'")
        self.assertGreaterEqual(cash, 0)
        self.assertGreaterEqual(fee, owed)
        self.ledger_never_negative()

    def test_fee_is_capped_and_the_rest_carried_over(self):
        c, uid, _ = self.funded("100,00")
        with self.ctx():
            a = self.acct(uid)
            iid = investing._enqueue(a["id"], "sandbox", "fee", {"amount_cents": 15000, "period": "test"}, "invest-fee:test")
            investing.dispatch(ids=[iid])
            p = investing.partner()
            events = p.settle(investing.invest_day(), kinds=("fee",), same_day=True)
            self.assertEqual(events[0][1]["amount_cents"], 10000)  # the sandbox never charges more than the cash
            investing.handle_event("sandbox", *events[0])
            a = self.acct(uid)
            self.assertEqual((investing.cash_cents(a["id"]), a["fee_carry_cents"]), (0, 5000))
            self.assertEqual(investing.available_cents(a["id"]), 0)

    def test_an_event_that_would_make_cash_negative_is_refused(self):
        c, uid, _ = self.funded("100,00")
        with self.ctx():
            a = self.acct(uid)
            iid = investing._enqueue(a["id"], "sandbox", "fee", {"amount_cents": 99999, "period": "test"}, "invest-fee:neg")
            investing.dispatch(ids=[iid])
            r = investing.handle_event("sandbox", "fee.charged", {"event_id": "neg", "external_id": a["external_id"], "ref": "invest-fee:neg",
                                                                  "amount_cents": 99999, "fills": []})
            self.assertEqual(r, "ignored")
            self.assertEqual(investing.cash_cents(a["id"]), 10000)
            self.assertIn("negatief", db.scalar("SELECT error FROM invest_events WHERE external_event_id = 'neg'"))


# ====================================================================== H2 staff retry revives a failed order

class H2RetryTest(Base):
    def test_failed_order_stays_failed(self):
        c, uid, _ = self.funded("500,00")
        investing.SandboxInvest.failures = {"order"}
        try:
            self.act(c, "kopen", amount="300,00")
            with self.ctx():
                for _ in range(6):
                    db.run("UPDATE invest_instructions SET status = 'sent', sent_at = '2000-01-01T00:00:00' WHERE kind = 'order' AND status = 'pending'")
                    investing.dispatch()
                i = db.one("SELECT * FROM invest_instructions WHERE kind = 'order'")
                o = db.one("SELECT * FROM invest_orders")
        finally:
            investing.SandboxInvest.failures = set()
        self.assertEqual((i["status"], o["status"]), ("failed", "failed"))
        self.assertIn("Mislukt", c.get("/wallet/beleggen").get_data(as_text=True))
        st = self.client("staff@depiqo.test")
        page = st.get("/admin/beleggen").get_data(as_text=True)
        self.assertIn("Definitief", page)
        r = st.post(f"/admin/beleggen/opdrachten/{i['id']}/opnieuw", data={"csrf_token": self.csrf(st, "/admin/beleggen")}, follow_redirects=True)
        self.assertIn("niet opnieuw verstuurd", r.get_data(as_text=True))
        self.day(1)
        with self.app.app_context():
            self.assertEqual(db.scalar("SELECT status FROM invest_orders"), "failed")
            self.assertEqual(db.scalar("SELECT status FROM invest_instructions WHERE kind = 'order'"), "failed")
            self.assertEqual(db.scalar("SELECT COUNT(*) FROM invest_fills"), 0)

    def test_a_failed_fee_charge_may_be_retried(self):
        c, uid, _ = self.funded("100,00")
        with self.ctx():
            a = self.acct(uid)
            iid = investing._enqueue(a["id"], "sandbox", "fee", {"amount_cents": 10, "period": "x"}, "invest-fee:retry")
            db.run("UPDATE invest_instructions SET status = 'failed' WHERE id = ?", (iid,))
            investing.retry_instruction(iid)
            self.assertEqual(db.scalar("SELECT status FROM invest_instructions WHERE id = ?", (iid,)), "pending")


# ====================================================================== H3 stale doorbeleggen choice

class H3StaleChoiceTest(Base):
    def test_choice_on_a_stale_page_after_payout_started_is_refused(self):
        c, uid, d, bank_acct = self.agreed_with_invest()
        stale = self.row(d["pid"])  # the tenant's page loaded the deposit while it was agreed
        with self.ctx():
            services.start_payout(self.row(d["pid"]), None)
            payload = json.loads(db.scalar("SELECT payload_json FROM bank_instructions WHERE kind = 'release'"))
            with self.assertRaisesRegex(investing.InvestError, "uitbetaling is al gestart"):
                investing.choose_payout(stale, uid, True)
            self.assertIsNone(investing.payout_choice(d["id"]))
        self.assertNotIn("tenant_destination", payload)
        before = self.cash(uid)
        self.assertEqual(self.payout_ok(bank_acct)["result"], "processed")
        self.assertEqual(self.cash(uid), before)  # the bank paid the tenant's own account: nothing on Invest

    def test_choice_cannot_change_once_the_release_exists(self):
        c, uid, d, bank_acct = self.agreed_with_invest()
        self.choose(c, d, confirm="1")
        stale = self.row(d["pid"])
        with self.ctx():
            services.start_payout(self.row(d["pid"]), None)
            with self.assertRaisesRegex(investing.InvestError, "uitbetaling is al gestart"):
                investing.choose_payout(stale, uid, False)
            self.assertEqual(investing.payout_choice(d["id"])["status"], "chosen")

    def test_credit_follows_the_release_instruction_not_the_choice_table(self):
        c, uid, d, bank_acct = self.agreed_with_invest()
        with self.ctx():
            services.start_payout(self.row(d["pid"]), None)  # own account
            acct = self.acct(uid)
            db.run("INSERT INTO invest_payout_choices (deposit_id, account_id, user_id, destination_iban, reference, status, chosen_at) "
                   "VALUES (?, ?, ?, 'X', ?, 'chosen', ?)", (d["id"], acct["id"], uid, acct["reference"], now_iso()))  # a row that sneaked in
        before = self.cash(uid)
        self.payout_ok(bank_acct)
        self.assertEqual(self.cash(uid), before)


# ====================================================================== H4 doorbeleggen fail closed (and M2)

class H4FailClosedPayoutTest(Base):
    def test_org_switched_off_pays_own_account_and_flags_it(self):
        c, uid, d, bank_acct = self.agreed_with_invest()
        self.choose(c, d, confirm="1")
        with self.app.app_context():
            db.run("UPDATE organizations SET invest_enabled = 0")
            mails = db.scalar("SELECT COUNT(*) FROM outbox_emails")
        with self.ctx():
            services.start_payout(self.row(d["pid"]), None)
            payload = json.loads(db.scalar("SELECT payload_json FROM bank_instructions WHERE kind = 'release'"))
            choice = db.one("SELECT * FROM invest_payout_choices")
            audit = db.one("SELECT * FROM audit_log WHERE action = 'invest.payout_fallback'")
            mail = db.one("SELECT * FROM outbox_emails ORDER BY id DESC LIMIT 1")
            staff_rows, _ = finance.reconciliation(only_exceptions=True)
            org_rows, _ = finance.reconciliation(org_id=self.org, only_exceptions=True)
        self.assertNotIn("tenant_destination", payload)
        self.assertEqual(choice["status"], "fallback")
        self.assertIsNone(audit["org_id"])
        self.assertGreater(mail["id"], mails)
        self.assertIsNone(mail["deposit_id"])  # not in the landlord's communication log
        self.assertIn("eigen rekening", mail["subject"])
        self.assertTrue(any("Doorbeleggen niet gelukt" in e for r in staff_rows for e in r["exceptions"]))
        self.assertFalse(any("Doorbeleggen" in e for r in org_rows for e in r["exceptions"]))
        before = self.cash(uid)
        self.payout_ok(bank_acct)
        self.assertEqual(self.cash(uid), before)
        self.assertIn("Doorbeleggen met een afwijking", self.client("staff@depiqo.test").get("/admin/beleggen").get_data(as_text=True))

    def test_partner_off_at_payout_is_unrecorded_not_paid(self):
        c, uid, d, bank_acct = self.agreed_with_invest()
        self.choose(c, d, confirm="1")
        with self.ctx():
            services.start_payout(self.row(d["pid"]), None)
        before = self.cash(uid)
        self.app.config["INVEST_PARTNER"] = ""
        try:
            self.assertEqual(self.payout_ok(bank_acct)["result"], "processed")
        finally:
            self.app.config["INVEST_PARTNER"] = "sandbox"
        with self.ctx():
            ch = db.one("SELECT * FROM invest_payout_choices")
            staff_rows, _ = finance.reconciliation(only_exceptions=False)
        self.assertEqual((ch["status"], ch["paid_cents"]), ("unrecorded", 185000))
        self.assertEqual(self.cash(uid), before)
        self.assertTrue(any("niet verwerkt op de beleggingsrekening" in e for r in staff_rows for e in r["exceptions"]))
        # the partner reports the incoming money later: recorded and paid in one go
        with self.ctx():
            a = self.acct(uid)
            r = investing.handle_event("sandbox", "deposit.received", {"event_id": "late", "external_id": a["external_id"], "amount_cents": 185000,
                                                                       "ref": f"payout:{d['pid']}"})
            self.assertEqual(r, "processed")
            self.assertEqual(db.scalar("SELECT status FROM invest_payout_choices"), "paid")
        self.assertEqual(self.cash(uid), before + 185000)

    def test_deposit_of_an_organisation_without_invest(self):
        """M2: the check is on the deposit's organisation, not on any organisation of the person."""
        c, uid, d, _ = self.agreed_with_invest()
        with self.app.app_context():
            tid = db.run("INSERT INTO tenants (org_id, name, email, user_id, created_at) VALUES (?, 'Tess', 'tess@huurder.test', ?, ?)",
                         (self.org2, uid, now_iso()))
            pid_ = db.run("INSERT INTO properties (org_id, address, postcode, city, region, created_at) VALUES (?, 'B 1', '1000 AA', 'X', 'NL', ?)",
                          (self.org2, now_iso()))
            db.run("INSERT INTO deposits (pid, reference, org_id, property_id, tenant_id, region, holding, rent_cents, amount_cents, status, "
                   "lease_start, rule_version, created_at, updated_at) VALUES ('orgbdeposit1', 'DPQ-002-00001', ?, ?, ?, 'NL', 'depiqo', 100000, "
                   "200000, 'agreed', '2024-01-01', '2026-10-18', ?, ?)", (self.org2, pid_, tid, now_iso(), now_iso()))
        other = self.row("orgbdeposit1")
        with self.ctx():
            self.assertFalse(investing.can_choose_payout(other, uid))
            self.assertTrue(investing.can_choose_payout(d, uid))
            with self.assertRaises(investing.InvestError):
                investing.choose_payout(other, uid, True)


# ====================================================================== H5 switch keeps the portfolio until done

class H5SwitchTest(Base):
    def test_failed_sale_leaves_the_portfolio(self):
        c, uid, _ = self.funded("500,00", buy="400,00")
        self.day(1)
        self.act(c, "wisselen", portfolio="offensief", confirm="1")
        with self.ctx():
            a = self.acct(uid)
            self.assertEqual((a["portfolio"], a["pending_switch"]), ("neutraal", "offensief"))
            i = db.one("SELECT * FROM invest_instructions WHERE kind = 'order' ORDER BY id DESC LIMIT 1")
            r = investing.handle_event("sandbox", "order.failed", {"event_id": "fx", "external_id": a["external_id"], "ref": i["idempotency_key"],
                                                                   "reason": "x"})
            a = self.acct(uid)
        self.assertEqual(r, "processed")
        self.assertEqual((a["portfolio"], a["pending_switch"]), ("neutraal", None))
        self.assertIn("Wisselen is niet gelukt", a["switch_note"])
        self.assertIn("Wisselen is niet gelukt", c.get("/wallet/beleggen").get_data(as_text=True))

    def test_buy_that_cannot_be_placed_is_queued_not_a_422(self):
        c, uid, _ = self.funded("500,00", buy="400,00")
        self.day(1)
        self.act(c, "wisselen", portfolio="offensief", confirm="1")
        from unittest import mock
        with self.ctx(), mock.patch.object(investing, "place_order", side_effect=investing.InvestError("partner even niet bereikbaar")):
            investing.dispatch()
            db.run("UPDATE invest_sandbox_clock SET offset_days = offset_days + 1")
            p = investing.partner()
            events = p.settle(investing.invest_day())
            results = [investing.handle_event("sandbox", t, pl) for t, pl in events]  # the follow-up purchase cannot be placed
            a = self.acct(uid)
        self.assertEqual(results, ["processed"])  # the sale is processed, no error back to the partner
        self.assertEqual((a["portfolio"], a["pending_switch"]), ("neutraal", "offensief"))  # not changed before the buy exists
        self.day(1)  # partner reachable again: the purchase is placed, then the portfolio changes
        with self.ctx():
            a = self.acct(uid)
            buy = db.one("SELECT * FROM invest_orders WHERE purpose = 'switch_buy'")
        self.assertEqual((a["portfolio"], a["pending_switch"]), ("offensief", None))
        self.assertIsNotNone(buy)


# ====================================================================== H6 unknown account does not consume the event id

class H6RetryableEventTest(Base):
    def test_activation_before_the_account_is_known(self):
        c, uid, _ = self.funded("100,00")
        with self.ctx():
            a = self.acct(uid)
            db.run("UPDATE invest_accounts SET status = 'pending', external_id = NULL WHERE id = ?", (a["id"],))
            r1 = investing.handle_event("sandbox", "account.activated", {"event_id": "act-1", "external_id": "sbi_x"})
            self.assertEqual(db.scalar("SELECT retryable FROM invest_events WHERE external_event_id = 'act-1'"), 1)
            db.run("UPDATE invest_accounts SET external_id = 'sbi_x' WHERE id = ?", (a["id"],))
            r2 = investing.handle_event("sandbox", "account.activated", {"event_id": "act-1", "external_id": "sbi_x"})
            r3 = investing.handle_event("sandbox", "account.activated", {"event_id": "act-1", "external_id": "sbi_x"})
        self.assertEqual((r1, r2, r3), ("ignored", "processed", "duplicate"))
        self.assertEqual(self.acct(uid)["status"], "active")

    def test_staff_reprocess(self):
        c, uid, _ = self.funded("100,00")
        with self.ctx():
            ext = self.acct(uid)["external_id"]
            investing.handle_event("sandbox", "deposit.received", {"event_id": "bad-day", "external_id": ext, "amount_cents": 500, "ref": "r9",
                                                                    "day": "1999-01-01"})
            ev = db.one("SELECT * FROM invest_events WHERE external_event_id = 'bad-day'")
            db.run("UPDATE invest_events SET payload_json = ? WHERE id = ?",
                   (json.dumps({"event_id": "bad-day", "external_id": ext, "amount_cents": 500, "ref": "r9"}), ev["id"]))
        st = self.client("staff@depiqo.test")
        r = st.post(f"/admin/beleggen/berichten/{ev['id']}/opnieuw", data={"csrf_token": self.csrf(st, "/admin/beleggen")}, follow_redirects=True)
        self.assertIn("Bericht opnieuw verwerkt", r.get_data(as_text=True))
        with self.app.app_context():
            self.assertEqual(investing.cash_cents(self.acct(uid)["id"]), 10500)


# ====================================================================== M1 organisation switch off

class M1ToggleOffTest(Base):
    def test_existing_investor_keeps_access_but_cannot_buy(self):
        c, uid, d = self.funded("500,00", buy="300,00")
        self.day(1)
        with self.app.app_context():
            db.run("UPDATE organizations SET invest_enabled = 0")
            db.run("UPDATE invest_accounts SET own_iban = 'NL91ABNA0417164300', own_iban_usable_from = ?", (now_iso(),))
        html = c.get("/wallet/beleggen").get_data(as_text=True)
        self.assertIn("biedt Beleggen niet meer aan", html)
        self.assertNotIn("Kosten bekijken", html)
        self.assertIn("niet meer aan", self.act(c, "kopen", amount="50,00").get_data(as_text=True))
        self.assertIn("niet meer aan", self.act(c, "wisselen", portfolio="offensief", confirm="1").get_data(as_text=True))
        self.assertIn("verkooporder staat klaar", self.act(c, "verkopen", amount="50,00").get_data(as_text=True))
        self.assertIn("Je opname staat klaar", self.act(c, "opnemen", amount="50,00").get_data(as_text=True))
        with self.ctx():
            period = investing.statement_periods(self.acct(uid))[0]
        self.assertEqual(c.get(f"/wallet/beleggen/overzicht/{period}.pdf").status_code, 200)
        self.day(1)
        with self.app.app_context():
            self.assertEqual(db.scalar("SELECT COUNT(*) FROM invest_orders WHERE status = 'executed'"), 2)


# ====================================================================== M3 risk and costs on every commitment

class M3CommitmentFormsTest(Base):
    def test_buy_needs_the_cost_page_and_a_confirmation(self):
        c, uid, _ = self.funded("500,00")
        r = c.post("/wallet/beleggen/actie/kopen", data={"amount": "400,00", "csrf_token": self.csrf(c, "/wallet/beleggen")}, follow_redirects=True)
        self.assertIn("Bevestig dat je de kosten", r.get_data(as_text=True))
        page = c.get("/wallet/beleggen/kopen?bedrag=400,00").get_data(as_text=True)
        for text in ("Kosten op € 400,00", "€ 1,77", "Scenario's, geen voorspelling", "Je kunt geld verliezen", 'name="confirm"'):
            self.assertIn(text, page, text)  # 0,25% + 0,1925% of € 400 = € 1,77 in the first year
        overview = c.get("/wallet/beleggen").get_data(as_text=True)
        self.assertIn("Die kan lager zijn dan nu", overview)  # sell form
        sw = c.get("/wallet/beleggen/wisselen?portefeuille=offensief").get_data(as_text=True)
        for text in ("Neutraal naar Offensief", "risico 6/7", "Scenario's, geen voorspelling", "Je kunt geld verliezen", "Lopende kosten fondsen (0,22% per jaar)"):
            self.assertIn(text, sw, text)

    def test_doorbeleggen_card_carries_the_risk(self):
        c, uid, d, _ = self.agreed_with_invest()
        html = c.get(f"/wallet/borg/{d['pid']}").get_data(as_text=True)
        self.assertIn("Waar wil je jouw deel ontvangen?", html)
        self.assertIn("Het depositogarantiestelsel geldt niet voor beleggingen", html)


# ====================================================================== M4 fee rate per account

class M4FeeRateTest(Base):
    def test_fee_change_needs_consent_and_never_works_backwards(self):
        c, uid, _ = self.funded("1.000,00", buy="1.000,00")
        self.day(2)
        with self.ctx():
            self.assertEqual(self.acct(uid)["fee_rate_bps"], 25)
        st = self.client("staff@depiqo.test")
        mails = self.mail_count()
        st.post("/admin/beleggen/servicevergoeding", data={"fee_pct": "0,75", "csrf_token": self.csrf(st, "/admin/beleggen")})
        with self.ctx():
            a = self.acct(uid)
            self.assertEqual((a["fee_rate_bps"], a["pending_fee_bps"]), (25, 75))
            self.assertEqual(investing.fee_bps(), 75)  # new accounts
        self.assertEqual(self.mail_count(), mails + 1)
        self.day(2)
        with self.ctx():
            a = self.acct(uid)
            units = investing.units_by_fund(a["id"])
            start = investing.parse_date(a["fee_accrued_through"])
        html = c.get("/wallet/beleggen").get_data(as_text=True)
        self.assertIn("Voorstel: nieuwe servicevergoeding", html)
        self.assertIn("0,25% per jaar over de waarde", html)  # still the agreed rate
        r = self.act(c, "servicevergoeding")
        self.assertIn("Vink aan", r.get_data(as_text=True))
        self.act(c, "servicevergoeding", accept="1")
        with self.ctx():
            a = self.acct(uid)
            self.assertEqual((a["fee_rate_bps"], a["pending_fee_bps"]), (75, None))
            self.assertEqual(a["fee_accrued_through"], investing.invest_day().isoformat())  # past days settled at the old rate first
            micro_at_accept = a["fee_accrued_micro"]
            day = investing.invest_day() + timedelta(days=1)
            expected = sum(investing.value_cents(u, investing.price_1e4(f, day)) for f, u in units.items()) * 75 * 100 // 365
        self.day(1)
        with self.ctx():
            a = self.acct(uid)
        if day.day != 1:  # unless a month end charged it in between
            self.assertEqual(a["fee_accrued_micro"] - micro_at_accept, expected)

    def mail_count(self):
        with self.app.app_context():
            return db.scalar("SELECT COUNT(*) FROM outbox_emails")


# ====================================================================== M5 withdrawals only to the own account

class M5OwnIbanTest(Base):
    def test_cooling_off_without_2fa(self):
        c, uid, _ = self.funded("500,00")
        r = c.post("/wallet/beleggen/actie/opnemen", data={"amount": "50,00", "iban": "DE89370400440532013000",
                                                          "csrf_token": self.csrf(c, "/wallet/beleggen")}, follow_redirects=True)
        self.assertIn("Registreer eerst je eigen rekeningnummer", r.get_data(as_text=True))
        with self.app.app_context():
            self.assertEqual(db.scalar("SELECT COUNT(*) FROM invest_instructions WHERE kind = 'withdraw'"), 0)
            mails = db.scalar("SELECT COUNT(*) FROM outbox_emails")
        self.act(c, "rekening", iban="NL91 ABNA 0417 1643 00")
        with self.app.app_context():
            a = self.acct(uid)
            notice = db.one("SELECT * FROM outbox_emails ORDER BY id DESC LIMIT 1")
            self.assertEqual(db.scalar("SELECT COUNT(*) FROM outbox_emails"), mails + 1)
        self.assertEqual((a["own_iban"], a["own_iban_holder"]), ("NL91ABNA0417164300", "Tess Huurder"))
        self.assertGreater(a["own_iban_usable_from"], now_iso())
        self.assertIn("rekeningnummer voor opnames", notice["subject"])
        self.assertIn("gebruiken vanaf", self.act(c, "opnemen", amount="50,00").get_data(as_text=True))

    def test_fresh_2fa_code_makes_it_usable_at_once(self):
        c, uid, _ = self.funded("500,00")
        with self.app.app_context():
            secret = mfa.new_secret()
            db.run("UPDATE users SET totp_secret = ?, totp_enabled_at = ? WHERE id = ?", (secret, now_iso(), uid))
        r = self.act(c, "rekening", iban="NL91ABNA0417164300", code="000000")
        self.assertIn("geldige code", r.get_data(as_text=True))
        self.act(c, "rekening", iban="NL91ABNA0417164300", code=mfa.totp(secret))
        with self.app.app_context():
            self.assertLessEqual(self.acct(uid)["own_iban_usable_from"], now_iso())
        self.assertIn("Je opname staat klaar", self.act(c, "opnemen", amount="50,00").get_data(as_text=True))
        with self.app.app_context():
            payload = json.loads(db.scalar("SELECT payload_json FROM invest_instructions WHERE kind = 'withdraw'"))
        self.assertEqual(payload["iban"], "NL91ABNA0417164300")


# ====================================================================== M6 validation of partner messages

class M6ValidationTest(Base):
    def send(self, etype, data):
        body = json.dumps({"type": etype, "data": data}).encode()
        return self.app.test_client().post("/webhooks/invest/sandbox", data=body, headers={
            "X-Depiqo-Signature": sign_webhook(body, self.app.config["INVEST_WEBHOOK_SECRET"]), "Content-Type": "application/json"})

    def test_bad_day_is_refused_and_the_overview_still_works(self):
        c, uid, _ = self.funded("100,00")
        ext = self.acct(uid)["external_id"]
        for i, day in enumerate(("!", "2026-13-01", "1999-01-01", "2999-01-01", 20261019)):
            r = self.send("deposit.received", {"event_id": f"dz{i}", "external_id": ext, "amount_cents": 100, "ref": f"z{i}", "day": day})
            self.assertEqual(r.get_json()["result"], "ignored", day)
        self.app.config["PROPAGATE_EXCEPTIONS"] = False
        self.assertEqual(c.get("/wallet/beleggen").status_code, 200)
        with self.app.app_context():
            self.assertEqual(investing.cash_cents(self.acct(uid)["id"]), 10000)

    def test_fill_amount_must_match_units_times_price(self):
        c, uid, _ = self.funded("500,00", buy="400,00")
        self.day(1)
        self.act(c, "verkopen", amount="100,00")
        with self.ctx():
            a = self.acct(uid)
            i = db.one("SELECT * FROM invest_instructions WHERE kind = 'order' ORDER BY id DESC LIMIT 1")
            f = sorted(investing.units_by_fund(a["id"]))[0]
            base = {"external_id": a["external_id"], "ref": i["idempotency_key"]}
            cash = investing.cash_cents(a["id"])
            bad = [
                [{"fund": f, "units_1e4": -1, "price_1e4": 1, "amount_cents": 9_999_900}],   # the reviewer's probe
                [{"fund": f, "units_1e4": -10000, "price_1e4": 1_000_000, "amount_cents": 10002}],  # 2 cents off
                [{"fund": f, "units_1e4": 0, "price_1e4": 1_000_000, "amount_cents": 0}],
                [{"fund": f, "units_1e4": -1.5, "price_1e4": 1_000_000, "amount_cents": 15}],
                "geen lijst",
            ]
            for n, fills in enumerate(bad):
                self.assertEqual(investing.handle_event("sandbox", "order.executed", {**base, "event_id": f"fz{n}", "fills": fills}), "ignored", n)
            self.assertEqual(investing.cash_cents(a["id"]), cash)
            ok = [{"fund": f, "units_1e4": -10000, "price_1e4": 1_000_000, "amount_cents": 10001}]  # one cent of rounding is allowed
            self.assertEqual(investing.handle_event("sandbox", "order.executed", {**base, "event_id": "fok", "fills": ok}), "processed")


# ====================================================================== L1 cash checks in the reservation transaction

class L1ConcurrencyTest(Base):
    def test_two_orders_from_the_same_stale_read(self):
        c, uid, _ = self.funded("500,00")
        with self.ctx():
            stale = self.acct(uid)
            available = investing.summary(stale)["available"]  # both requests saw this
            investing.place_order(stale, "buy", available)
            with self.assertRaisesRegex(investing.InvestError, "niet genoeg geld"):
                investing.place_order(stale, "buy", available)
            with self.assertRaisesRegex(investing.InvestError, "Registreer eerst|vrij"):
                investing.withdraw(stale, available)
            self.assertEqual(db.scalar("SELECT COUNT(*) FROM invest_orders"), 1)


# ====================================================================== L2 audit never carries an organisation

class L2AuditTest(Base):
    def test_invest_audit_rows_have_no_org_even_for_members(self):
        c, uid, _ = self.tenant()
        with self.app.app_context():
            db.run("INSERT INTO memberships (user_id, org_id, role, created_at) VALUES (?, ?, 'viewer', ?)", (uid, self.org, now_iso()))
        c2 = self.app.test_client()
        c2.post("/login", data={"email": "tess@huurder.test", "password": T.tv.PW, "csrf_token": self.anon(c2)})
        self.onboard(c2)
        with self.app.app_context():
            rows = db.all_("SELECT action, org_id FROM audit_log WHERE action LIKE 'invest.%'")
        self.assertTrue(rows)
        self.assertTrue(all(r["org_id"] is None for r in rows), [dict(r) for r in rows])


# ====================================================================== CSV export

class ExportTest(Base):
    def test_business_export_has_nothing_from_invest(self):
        c, uid, d = self.funded("500,00", buy="400,00")
        self.day(1)
        with self.app.app_context():
            ref = self.acct(uid)["reference"]
        text = self.client("admin@a.test").get("/app/export.csv").get_data(as_text=True)
        for word in (ref, "belegg", "Invest", "INV-", "Sandbox-beleggingspartner"):
            self.assertNotIn(word, text)


if __name__ == "__main__":
    unittest.main()
