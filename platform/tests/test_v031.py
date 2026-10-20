"""Regression tests for the review of 0.3.0 (version 0.3.1). One test class per defect; the setups
follow the reviewer's probes, the assertions check the corrected behaviour.

    python -m unittest discover -s tests -v
"""
import glob
import os
import shutil
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import billing, db, finance, services  # noqa: E402
from app import states as S  # noqa: E402
from app.partners import PartnerError, SandboxBank  # noqa: E402
from app.util import today  # noqa: E402
import test_v030 as tv  # noqa: E402  (module import: its classes must not be collected twice)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Base(tv.Base):
    def to_id_pending_with_pending_open(self):
        """Depiqo deposit, tenant verified identity, open instruction still pending (inline dispatch off)."""
        self.app.config["DISPATCH_INLINE"] = False
        mgr = self.client("admin@a.test")
        self.create(mgr)
        d = self.deposit()
        tenant = self.app.test_client()
        self.accept(tenant, self.invite_link())
        tenant.post(f"/wallet/borg/{d['pid']}/identiteit",
                    data={"full_name": "Tess Huurder", "birth_date": "1995-01-01", "csrf_token": self.csrf(tenant, f"/wallet/borg/{d['pid']}")})
        self.assertEqual(self.row()["status"], S.ID_PENDING)
        return mgr, tenant, self.row()


# 1. HIGH: payout.completed before the dispatcher records the acknowledgement
class PayoutTimingTest(Base):
    def test_payout_event_during_release_call_is_processed(self):
        mgr, d = self.to_agreed()
        fin = self.client("finance@a.test")
        orig = SandboxBank.request_release
        holder = {}

        def fast_bank(self_, account, t, l, ref, key):
            resp = orig(self_, account, t, l, ref, key)
            body = {"event_id": "pay-fast", "external_id": account["external_id"], "tenant_cents": t, "landlord_cents": l, "ref": "p"}
            holder["result"] = services.handle_bank_event("sandbox", "payout.completed", body)
            return resp
        with mock.patch.object(SandboxBank, "request_release", fast_bank):
            fin.post(f"/app/borgen/{d['pid']}/uitbetalen", data={"csrf_token": self.csrf(fin)})
        self.assertEqual(holder["result"], "processed")
        self.assertEqual(self.row()["status"], S.CLOSED)
        with self.app.app_context():
            # the late acknowledgement does not overwrite the confirmation
            self.assertEqual(db.scalar("SELECT status FROM bank_instructions WHERE kind = 'release'"), "confirmed")

    def test_timing_refusal_does_not_consume_the_event_id(self):
        mgr, d = self.to_agreed()
        acct = self.account(d)
        body = {"event_id": "early", "external_id": acct["external_id"], "tenant_cents": 185000, "landlord_cents": 15000, "ref": "p"}
        anon = self.app.test_client()
        self.assertEqual(self.webhook(anon, "payout.completed", body).get_json()["result"], "ignored")
        with self.app.app_context():
            self.assertEqual(db.scalar("SELECT retryable FROM bank_events WHERE external_event_id = 'early'"), 1)
        fin = self.client("finance@a.test")
        fin.post(f"/app/borgen/{d['pid']}/uitbetalen", data={"csrf_token": self.csrf(fin)})
        self.assertEqual(self.webhook(anon, "payout.completed", body).get_json()["result"], "processed")  # the bank's retry
        self.assertEqual(self.row()["status"], S.CLOSED)
        self.assertEqual(self.webhook(anon, "payout.completed", body).get_json()["result"], "duplicate")  # processed once

    def test_staff_can_reprocess_an_event_with_an_error(self):
        mgr, d = self.to_agreed()
        acct = self.account(d)
        body = {"event_id": "early2", "external_id": acct["external_id"], "tenant_cents": 185000, "landlord_cents": 15000, "ref": "p"}
        self.webhook(self.app.test_client(), "payout.completed", body)
        fin = self.client("finance@a.test")
        fin.post(f"/app/borgen/{d['pid']}/uitbetalen", data={"csrf_token": self.csrf(fin)})
        with self.app.app_context():
            ev_id = db.scalar("SELECT id FROM bank_events WHERE external_event_id = 'early2'")
        org_admin = self.client("admin@a.test")
        self.assertEqual(org_admin.post(f"/admin/bankberichten/{ev_id}/opnieuw", data={"csrf_token": self.csrf(org_admin)}).status_code, 404)
        st = self.client("staff@depiqo.test")
        self.assertIn("Opnieuw verwerken", st.get("/admin").get_data(as_text=True))
        st.post(f"/admin/bankberichten/{ev_id}/opnieuw", data={"csrf_token": self.csrf(st, "/admin")})
        self.assertEqual(self.row()["status"], S.CLOSED)
        with self.app.app_context():
            self.assertIsNone(db.scalar("SELECT error FROM bank_events WHERE external_event_id = 'early2'"))


# 2. MEDIUM: with the sandbox off, a sandbox lock is not confirmed security
class UntrustedLockTest(Base):
    def test_sandbox_lock_not_confirmed_when_sandbox_is_off(self):
        _, d = self.to_secured()
        self.app.config["SANDBOX"] = False
        self.app.config["BANK_PARTNER"] = ""
        a = self.client("admin@a.test")
        page = a.get(f"/app/borgen/{d['pid']}").get_data(as_text=True)
        self.assertNotIn(">Zekerheid bevestigd<", page)
        self.assertIn("SANDBOX, niet bevestigd", page)
        self.assertIn("Sandboxrekening: niet bevestigd door een echte bank", page)
        dash = a.get("/app").get_data(as_text=True)
        self.assertRegex(dash, r"Bevestigd geblokkeerd</span><b>€ 0</b>")
        with self.ctx():
            self.assertEqual(services.display_status(self.row()), ("SANDBOX, niet bevestigd", "wait"))
            figs = {f["key"]: f["value"] for f in services.balances(self.row())}
            self.assertIsNone(figs["locked"])
            rows, totals = finance.reconciliation(org_id=self.org)
        self.assertEqual(totals["locked"], 0)
        self.assertTrue(any("Sandboxrekening" in e for r in rows for e in r["exceptions"]))
        self.assertIn("SANDBOX, niet bevestigd", a.get("/app/export.csv").get_data(as_text=True))
        # With the sandbox on, the same lock is confirmed again.
        self.app.config["SANDBOX"] = True
        self.app.config["BANK_PARTNER"] = "sandbox"
        with self.ctx():
            self.assertEqual(services.display_status(self.row()), ("Zekerheid bevestigd", "ok"))


# 3. MEDIUM: 2FA changes end other sessions; staff pages need a session that passed the second factor
class SessionSecondFactorTest(Base):
    enable = tv.TwoFactorTest.enable

    def test_enabling_2fa_ends_password_only_sessions(self):
        self.app.config["REQUIRE_2FA_FOR_STAFF"] = True
        attacker = self.client("staff@depiqo.test")
        victim = self.client("staff@depiqo.test")
        secret, _ = self.enable(victim, "staff@depiqo.test")
        r = attacker.get("/admin/afstemming")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])  # the session is gone
        self.assertEqual(victim.get("/admin/afstemming").status_code, 200)

    def test_staff_gate_checks_the_session(self):
        self.app.config["REQUIRE_2FA_FOR_STAFF"] = True
        st = self.client("staff@depiqo.test")
        self.enable(st, "staff@depiqo.test")
        with self.app.app_context():
            db.run("UPDATE sessions SET mfa_at = NULL")  # a session that never passed the second factor
        r = st.get("/admin/afstemming")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/account/beveiliging", r.headers["Location"])

    def test_login_with_code_marks_the_session(self):
        self.app.config["REQUIRE_2FA_FOR_STAFF"] = True
        st = self.client("staff@depiqo.test")
        secret, _ = self.enable(st, "staff@depiqo.test")
        c = self.app.test_client()
        c.post("/login", data={"email": "staff@depiqo.test", "password": tv.PW, "csrf_token": self.anon(c)})
        c.post("/login/code", data={"code": tv.mfa.totp(secret, time.time() + 30), "csrf_token": self.anon(c, "/login/code")})
        self.assertEqual(c.get("/admin/afstemming").status_code, 200)

    def test_disable_and_new_codes_end_other_sessions(self):
        a = self.client("admin@a.test")
        other = self.client("admin@a.test")
        secret, codes = self.enable(a, "admin@a.test")
        self.assertEqual(other.get("/app").status_code, 302)  # ended when 2FA was turned on
        other2 = self.app.test_client()
        other2.post("/login", data={"email": "admin@a.test", "password": tv.PW, "csrf_token": self.anon(other2)})
        other2.post("/login/code", data={"code": tv.mfa.totp(secret, time.time() + 30), "csrf_token": self.anon(other2, "/login/code")})
        self.assertEqual(other2.get("/app").status_code, 200)
        a.post("/account/beveiliging", data={"action": "codes", "code": codes[0],
                                             "csrf_token": self.csrf(a, "/account/beveiliging")})
        self.assertEqual(other2.get("/app").status_code, 302)
        self.assertEqual(a.get("/app").status_code, 200)


# 4. MEDIUM: a staff plan change from this month supersedes a pending self-service change
class PlanSupersedeTest(Base):
    def test_staff_change_wins_over_scheduled_switch(self):
        a = self.client("admin@a.test")
        a.post("/app/facturatie/plan", data={"plan": "professional", "csrf_token": self.csrf(a, "/app/facturatie")})
        st = self.client("staff@depiqo.test")
        st.post(f"/admin/organisaties/{self.org}/plan", data={"plan": "enterprise", "valid_from": today().strftime("%Y-%m"),
                                                            "base_cents": "1000,00", "included": "1000", "extra_external_cents": "0,10",
                                                            "extra_depiqo_cents": "0,10", "new_dossier_cents": "1,00",
                                                            "csrf_token": self.csrf(st, "/admin")})
        with self.app.app_context():
            org = db.one("SELECT * FROM organizations WHERE id = ?", (self.org,))
            self.assertEqual(org["plan"], "enterprise")
            self.assertEqual(billing.plan_for_period(org, today().strftime("%Y-%m"))["code"], "enterprise")
            self.assertEqual(billing.plan_for_period(org, billing.next_month_start().strftime("%Y-%m"))["code"], "enterprise")


# 5. MEDIUM: zero and void invoices from 0.2 are not 'open' or overdue
class InvoiceMigrationTest(Base):
    def test_zero_and_void_invoices_after_migration(self):
        src = os.path.join(ROOT, "migrations")
        old = os.path.join(self.tmp, "m")
        os.makedirs(old)
        for f in sorted(glob.glob(os.path.join(src, "00[123]*.sql"))):
            shutil.copy(f, old)
        path = os.path.join(self.tmp, "old.sqlite3")
        db.migrate(path, old)
        c = db.connect(path)
        c.execute("INSERT INTO organizations (id, name, plan, pilot_until, created_at) VALUES (1, 'Pilot BV', 'essential', '2027-01-01', '2026-03-01T00:00:00+00:00')")
        c.execute("INSERT INTO invoices (org_id, period, number, status, subtotal_cents, vat_cents, total_cents, lines_json, issued_at) "
                  "VALUES (1, '2026-03', 'DPQ-2026-00001', 'issued', 0, 0, 0, '[]', '2026-04-01T09:00:00+00:00')")
        c.execute("INSERT INTO invoices (org_id, period, number, status, subtotal_cents, vat_cents, total_cents, lines_json, issued_at) "
                  "VALUES (1, '2026-04', 'DPQ-2026-00002', 'void', 9900, 2079, 11979, '[]', '2026-05-01T09:00:00+00:00')")
        c.execute("INSERT INTO invoices (org_id, period, number, status, subtotal_cents, vat_cents, total_cents, lines_json, issued_at) "
                  "VALUES (1, '2026-05', 'DPQ-2026-00003', 'issued', 9900, 2079, 11979, '[]', '2026-06-01T09:00:00+00:00')")
        c.close()
        for f in glob.glob(os.path.join(src, "00[45]*.sql")):
            shutil.copy(f, old)
        db.migrate(path, old)
        c = db.connect(path)
        rows = [dict(r) for r in c.execute("SELECT * FROM invoices ORDER BY id")]
        c.close()
        self.assertEqual([r["payment_status"] for r in rows], ["none", "none", "open"])
        self.assertEqual([billing.payment_state(r)[1] for r in rows], ["Niets te betalen", "Vervallen", "Te laat"])

    def test_void_invoice_cannot_be_marked_paid(self):
        with self.app.app_context():
            db.run("UPDATE organizations SET created_at = '2026-01-01T00:00:00+00:00' WHERE id = ?", (self.org,))
            inv = billing.issue_invoice(db.one("SELECT * FROM organizations WHERE id = ?", (self.org,)), "2026-08")
            db.run("UPDATE invoices SET status = 'void' WHERE id = ?", (inv["id"],))
            with self.assertRaises(ValueError):
                billing.mark_paid(inv["id"])


# 6. LOW-MED: credited invoices are not paid; paid invoices are not credited without a refund
class CreditPaidTest(Base):
    def test_credit_and_paid_exclude_each_other(self):
        with self.app.app_context():
            db.run("UPDATE organizations SET created_at = '2026-01-01T00:00:00+00:00' WHERE id = ?", (self.org,))
        with self.ctx():
            org = db.one("SELECT * FROM organizations WHERE id = ?", (self.org,))
            inv = billing.issue_invoice(org, "2026-08")
            billing.credit_invoice(inv["id"], "fout bedrag")
            with self.assertRaises(ValueError):
                billing.mark_paid(inv["id"])
            self.assertEqual(tuple(db.one("SELECT status, payment_status FROM invoices WHERE id = ?", (inv["id"],))), ("credited", "open"))
            inv2 = billing.issue_invoice(org, "2026-07")
            billing.mark_paid(inv2["id"])
            with self.assertRaises(ValueError) as cm:
                billing.credit_invoice(inv2["id"], "toch fout")
            self.assertIn("al betaald", str(cm.exception))
            self.assertEqual(db.scalar("SELECT COUNT(*) FROM invoices WHERE kind = 'credit'"), 1)


# 7. LOW-MED: a new identity check after a failed 'open' instruction sends it again
class FailedOpenTest(Base):
    def test_new_identity_check_resends_failed_open(self):
        SandboxBank.failures = {"open"}
        try:
            self.app.config["MAX_INSTRUCTION_ATTEMPTS"] = 1
            _, tenant, d = self.to_id_pending_with_pending_open()
            with self.ctx():
                services.dispatch_instructions()
                self.assertEqual(db.scalar("SELECT status FROM bank_instructions WHERE deposit_id = ?", (d["id"],)), "failed")
            # The bank is still down: the tenant is told so, not that the bank is opening the account.
            self.app.config["DISPATCH_INLINE"] = True
            r = tenant.post(f"/wallet/borg/{d['pid']}/identiteit", data={"full_name": "Tess Huurder", "birth_date": "1995-01-01",
                                                                         "csrf_token": self.csrf(tenant, f"/wallet/borg/{d['pid']}")}, follow_redirects=True)
            html = r.get_data(as_text=True)
            self.assertNotIn("De bank opent nu je borgrekening", html)
            self.assertIn("kon je borgrekening nog niet openen", html)
        finally:
            SandboxBank.failures = set()
        r = tenant.post(f"/wallet/borg/{d['pid']}/identiteit", data={"full_name": "Tess Huurder", "birth_date": "1995-01-01",
                                                                     "csrf_token": self.csrf(tenant, f"/wallet/borg/{d['pid']}")}, follow_redirects=True)
        self.assertIn("borgrekening is geopend", r.get_data(as_text=True))
        self.assertEqual(self.row()["status"], S.AWAITING_PAYMENT)
        with self.app.app_context():
            self.assertEqual([r[0] for r in db.all_("SELECT status FROM bank_instructions WHERE deposit_id = ?", (d["id"],))], ["confirmed"])


# 8. LOW: a timeout never overwrites an instruction that the bank already confirmed
class ConfirmedNotOverwrittenTest(Base):
    def test_block_timeout_after_bank_blocked(self):
        self.app.config["MAX_INSTRUCTION_ATTEMPTS"] = 1
        mgr, d = self._to_awaiting_payment()
        acct = self.account(d)

        def slow_block(self_, account, key):
            services.handle_bank_event("sandbox", "account.blocked", {"event_id": "blk", "external_id": account["external_id"]})
            raise PartnerError("timeout")
        with mock.patch.object(SandboxBank, "request_block", slow_block):
            self.webhook(self.app.test_client(), "deposit.received",
                         {"event_id": "dep", "external_id": acct["external_id"], "amount_cents": 200000, "ref": "r"})
        with self.ctx():
            self.assertEqual(db.scalar("SELECT status FROM bank_instructions WHERE kind = 'block'"), "confirmed")
            rows, _ = finance.reconciliation(org_id=self.org, only_exceptions=True)
            self.assertEqual(rows, [])
            self.assertEqual(db.scalar("SELECT COUNT(*) FROM deposit_events WHERE type = 'exception'"), 0)
        self.assertEqual(self.row()["status"], S.SECURED)

    def test_retry_does_not_overwrite_acknowledged(self):
        mgr, d = self._to_awaiting_payment()
        acct = self.account(d)

        def ack_then_timeout(self_, account, key):
            # another worker recorded the acknowledgement meanwhile
            db.run("UPDATE bank_instructions SET status = 'acknowledged' WHERE kind = 'block'")
            raise PartnerError("timeout")
        with mock.patch.object(SandboxBank, "request_block", ack_then_timeout):
            self.webhook(self.app.test_client(), "deposit.received",
                         {"event_id": "dep2", "external_id": acct["external_id"], "amount_cents": 200000, "ref": "r"})
        with self.app.app_context():
            self.assertEqual(db.scalar("SELECT status FROM bank_instructions WHERE kind = 'block'"), "acknowledged")


# 9. LOW: a very long CSV field is a clear error, never a 500; text fields have a maximum length
class ImportLimitsTest(Base):
    upload_csv = tv.ImportTest.upload_csv

    def test_oversized_field_and_lengths(self):
        a = self.client("admin@a.test")
        self.app.config["PROPAGATE_EXCEPTIONS"] = False
        self.app.testing = False
        data = tv.csv_bytes([("A" * 140000, "1017 GA", "Amsterdam", "NL", "X", "x@h.test", "1000", "2000", "2024-01-01", "external", "", "")])
        r = self.upload_csv(a, data)
        self.assertEqual(r.status_code, 200)
        self.assertIn("kon niet worden gelezen", r.get_data(as_text=True))
        data = tv.csv_bytes([("B" * 250, "1017 GA", "Amsterdam", "NL", "N" * 130, "x@h.test", "1000", "2000", "2024-01-01", "external", "", "")])
        r = self.upload_csv(a, data)
        html = a.get(r.headers["Location"]).get_data(as_text=True)
        self.assertIn("Adres: maximaal 200 tekens", html)
        self.assertIn("Huurder: maximaal 120 tekens", html)
        self.assertNotIn("B" * 250, html)


if __name__ == "__main__":
    unittest.main()
