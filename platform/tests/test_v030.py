"""Tests for version 0.3.0: financial correctness (figures, evidence, fail-closed partner, outbox,
reconciliation) and pilot readiness (rules versions, plan history, unit economics, import, bulk
actions, action centre, two-factor authentication, communication log).

    python -m unittest discover -s tests -v
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import date, timedelta
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.util import today as local_today  # noqa: E402
from app import billing, create_app, db, finance, imports, mfa, partners, rules, services  # noqa: E402
from app import states as S  # noqa: E402
from app.partners import SandboxBank  # noqa: E402
from app.util import add_months, now, now_iso, today  # noqa: E402
import test_platform as tp  # noqa: E402  (module import: FlowTest itself must not be collected twice)

PW = tp.PW

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Base(unittest.TestCase):
    """Same fixtures and helpers as FlowTest (org A with four roles, org B, one staff user)."""
    setUp = tp.FlowTest.setUp
    tearDown = tp.FlowTest.tearDown
    client = tp.FlowTest.client
    anon = tp.FlowTest.anon
    accept = tp.FlowTest.accept
    csrf = tp.FlowTest.csrf
    create = tp.FlowTest.create
    deposit = tp.FlowTest.deposit
    invite_link = tp.FlowTest.invite_link
    webhook = tp.FlowTest.webhook
    account = tp.FlowTest.account
    _to_awaiting_payment = tp.FlowTest._to_awaiting_payment

    def ctx(self):
        return self.app.test_request_context("/")

    def row(self, pid=None):
        with self.app.app_context():
            if pid:
                return db.one("SELECT * FROM deposits WHERE pid = ?", (pid,))
            return db.one("SELECT * FROM deposits ORDER BY id DESC LIMIT 1")

    def uid(self, email):
        with self.app.app_context():
            return db.scalar("SELECT id FROM users WHERE email = ?", (email,))

    def to_secured(self):
        """Depiqo deposit, paid and blocked by the (sandbox) bank."""
        mgr, d = self._to_awaiting_payment()
        acct = self.account(d)
        anon = self.app.test_client()
        self.webhook(anon, "deposit.received", {"event_id": f"r{d['id']}", "external_id": acct["external_id"], "amount_cents": 200000, "ref": "r"})
        self.webhook(anon, "account.blocked", {"event_id": f"b{d['id']}", "external_id": acct["external_id"]})
        self.assertEqual(self.row()["status"], S.SECURED)
        return mgr, self.row()

    def to_agreed(self):
        mgr, d = self.to_secured()
        token = self.csrf(mgr)
        mgr.post(f"/app/borgen/{d['pid']}/vertrek", data={"move_out_date": local_today().isoformat(), "csrf_token": token})
        mgr.post(f"/app/borgen/{d['pid']}/afrekening-opslaan", data={"cat_0": "damage", "desc_0": "Gat in de muur", "amount_0": "150,00", "csrf_token": token})
        mgr.post(f"/app/borgen/{d['pid']}/afrekening-voorstellen", data={"csrf_token": token})
        with self.ctx():
            services.tenant_agree(self.row(), None)
        self.assertEqual(self.row()["status"], S.AGREED)
        return mgr, self.row()

    def external_awaiting(self, **over):
        mgr = self.client("admin@a.test")
        self.create(mgr, holding="external", external_iban="NL91ABNA0417164300", **over)
        d = self.row()
        self.accept(self.app.test_client(), self.invite_link())
        self.assertEqual(self.row()["status"], S.AWAITING_PAYMENT)
        return mgr, self.row()

    def upload(self, c, d, kind, name="bewijs.pdf"):
        c.post(f"/app/borgen/{d['pid']}/documenten", data={"kind": kind, "file": (io.BytesIO(b"%PDF-1.4 proof"), name),
                                                            "csrf_token": self.csrf(c)}, content_type="multipart/form-data")
        with self.app.app_context():
            return db.scalar("SELECT id FROM documents WHERE deposit_id = ? AND kind = ? ORDER BY id DESC LIMIT 1", (d["id"], kind))


# ====================================================================== P0.1 four figures

class FiguresTest(Base):
    def test_wallet_shows_dash_before_payment_never_the_obligation(self):
        mgr, d = self._to_awaiting_payment()
        with self.ctx():
            figs = {f["key"]: f for f in services.balances(self.row())}
        self.assertEqual(figs["obligation"]["value"], 200000)
        self.assertIsNone(figs["received"]["value"])
        self.assertIsNone(figs["locked"]["value"])
        self.assertIsNone(figs["interest"]["value"])
        tenant = self.app.test_client()
        tenant.post("/login", data={"email": "tess@huurder.test", "password": PW, "csrf_token": self.anon(tenant)})
        html = tenant.get(f"/wallet/borg/{d['pid']}").get_data(as_text=True)
        for label in ("Vereiste borg", "Ontvangen", "Bevestigd geblokkeerd", "Rente", "Nog geen storting gemeld door de bank"):
            self.assertIn(label, html)
        received = re.search(r"<dt>Ontvangen</dt><dd><b[^>]*>([^<]+)</b>", html).group(1)
        self.assertEqual(received, "—")

    def test_figures_follow_the_bank(self):
        mgr, d = self._to_awaiting_payment()
        acct = self.account(d)
        anon = self.app.test_client()
        self.webhook(anon, "deposit.received", {"event_id": "f1", "external_id": acct["external_id"], "amount_cents": 200000, "ref": "r"})
        with self.ctx():
            figs = {f["key"]: f["value"] for f in services.balances(self.row())}
        self.assertEqual((figs["received"], figs["locked"]), (200000, None))  # received, lock only requested
        self.webhook(anon, "account.blocked", {"event_id": "f2", "external_id": acct["external_id"]})
        self.webhook(anon, "interest.credited", {"event_id": "f3", "external_id": acct["external_id"], "amount_cents": 333, "ref": "i"})
        with self.ctx():
            figs = {f["key"]: f["value"] for f in services.balances(self.row())}
        self.assertEqual((figs["received"], figs["locked"], figs["interest"]), (200000, 200333, 333))
        html = mgr.get(f"/app/borgen/{d['pid']}").get_data(as_text=True)
        self.assertIn("Blokkering bevestigd door de bank", html)

    def test_external_declared_shows_no_received_amount(self):
        mgr, d = self.external_awaiting()
        mgr.post(f"/app/borgen/{d['pid']}/ontvangst", data={"csrf_token": self.csrf(mgr)})
        with self.ctx():
            figs = {f["key"]: f for f in services.balances(self.row())}
        self.assertIsNone(figs["received"]["value"])
        self.assertIsNone(figs["locked"]["value"])
        html = mgr.get(f"/app/borgen/{d['pid']}").get_data(as_text=True)
        self.assertIn("Alleen verklaard door de beheerder, niet aangetoond", html)

    def test_wallet_home_cards_use_figures(self):
        a = self.client("admin@a.test")
        self.create(a)
        tenant = self.app.test_client()
        self.accept(tenant, self.invite_link())
        self.create(a, address="Tweede 2")  # same tenant, second deposit
        self.accept(tenant, self.invite_link())
        html = tenant.get("/wallet").get_data(as_text=True)
        self.assertIn("Vereiste borg", html)
        self.assertIn("Bevestigd geblokkeerd", html)
        self.assertEqual(html.count("figs-compact"), 2)


# ====================================================================== P0.2 evidence levels

class EvidenceTest(Base):
    def test_declared_is_not_shown_as_confirmed(self):
        mgr, d = self.external_awaiting()
        mgr.post(f"/app/borgen/{d['pid']}/ontvangst", data={"csrf_token": self.csrf(mgr)})
        d = self.row()
        self.assertEqual((d["status"], d["evidence_level"], d["eligible_value_cents"]), (S.SECURED, "declared", None))
        self.assertEqual(S.display_status(d), ("Ontvangst verklaard door beheerder", "wait"))
        self.assertEqual(S.display_status(d, tenant=True)[0], "Ontvangst verklaard door je verhuurder")
        page = mgr.get(f"/app/borgen/{d['pid']}").get_data(as_text=True)
        self.assertIn("Ontvangst verklaard door beheerder", page)
        self.assertNotIn(">Zekerheid bevestigd<", page)
        listing = mgr.get("/app/borgen").get_data(as_text=True)
        self.assertIn("Ontvangst verklaard door beheerder", listing)
        self.assertIn(">Verklaard<", listing)
        dash = mgr.get("/app").get_data(as_text=True)
        self.assertIn("Bevestigd geblokkeerd", dash)
        self.assertIn("Bewijs ontbreekt", dash)
        csv_text = mgr.get("/app/export.csv").get_data(as_text=True)
        self.assertIn("bewijsniveau", csv_text.splitlines()[0])
        self.assertIn("Verklaard door beheerder", csv_text)

    def test_evidence_ladder_and_permissions(self):
        mgr, d = self.external_awaiting()
        proof = self.upload(mgr, d, "bankbewijs")
        mgr.post(f"/app/borgen/{d['pid']}/ontvangst", data={"document_id": proof, "csrf_token": self.csrf(mgr)})
        d = self.row()
        self.assertEqual(d["evidence_level"], "document")
        self.assertEqual(S.display_status(d)[1], "neutral")
        # The organisation cannot verify itself: the staff route is not reachable, the service refuses.
        self.assertEqual(mgr.post(f"/admin/borgen/{d['pid']}/bewijs", data={"level": "verified", "note": "x" * 20,
                                                                             "csrf_token": self.csrf(mgr)}).status_code, 404)
        with self.ctx(), self.assertRaises(services.WorkflowError):
            services.set_evidence(d, "verified", self.uid("admin@a.test"), "Zelf gecontroleerd door mij")
        st = self.client("staff@depiqo.test")
        token = self.csrf(st, "/admin")
        st.post(f"/admin/borgen/{d['pid']}/bewijs", data={"level": "verified", "note": "kort", "csrf_token": token})
        self.assertEqual(self.row()["evidence_level"], "document")  # note too short
        st.post(f"/admin/borgen/{d['pid']}/bewijs", data={"level": "verified", "note": "Afschrift gecontroleerd op naam en bedrag", "csrf_token": token})
        d = self.row()
        self.assertEqual((d["evidence_level"], d["eligible_value_cents"]), ("verified", 200000))
        self.assertNotEqual(S.display_status(d)[1], "ok")  # verified is still not green
        # Legal needs a blocking certificate.
        st.post(f"/admin/borgen/{d['pid']}/bewijs", data={"level": "legal", "csrf_token": token})
        self.assertEqual(self.row()["evidence_level"], "verified")
        cert = self.upload(mgr, d, "blokkering", "attest.pdf")
        st.post(f"/admin/borgen/{d['pid']}/bewijs", data={"level": "legal", "document_id": cert, "csrf_token": token})
        d = self.row()
        self.assertEqual((d["evidence_level"], d["legal_lock_status"]), ("legal", "active"))
        self.assertEqual(S.display_status(d), ("Zekerheid bevestigd", "ok"))
        with self.ctx():
            figs = {f["key"]: f["value"] for f in services.balances(d)}
            self.assertEqual(services.coverage_bps(d), 10000)
            with self.assertRaises(services.WorkflowError):  # never lowered
                services.set_evidence(d, "verified", None, "Terug naar verified", staff=True)
            hist = services.evidence_history(d)
        self.assertEqual(figs["locked"], 200000)
        self.assertEqual([h["level"] for h in hist], ["document", "verified", "legal"])

    def test_document_level_requires_bank_document(self):
        mgr, d = self.external_awaiting()
        mgr.post(f"/app/borgen/{d['pid']}/ontvangst", data={"csrf_token": self.csrf(mgr)})
        r = mgr.post(f"/app/borgen/{d['pid']}/bewijs", data={"csrf_token": self.csrf(mgr)}, follow_redirects=True)
        self.assertIn("Voeg eerst een bankbewijs toe", r.get_data(as_text=True))
        photo = self.upload(mgr, d, "photo")
        mgr.post(f"/app/borgen/{d['pid']}/bewijs", data={"document_id": photo, "csrf_token": self.csrf(mgr)})
        self.assertEqual(self.row()["evidence_level"], "declared")
        proof = self.upload(mgr, d, "bankbewijs")
        mgr.post(f"/app/borgen/{d['pid']}/bewijs", data={"document_id": proof, "csrf_token": self.csrf(mgr)})
        self.assertEqual(self.row()["evidence_level"], "document")

    def test_evidence_only_for_external_and_bank_confirmed_is_green(self):
        _, d = self.to_secured()
        self.assertEqual(S.display_status(d), ("Zekerheid bevestigd", "ok"))
        with self.ctx(), self.assertRaises(services.WorkflowError):
            services.set_evidence(d, "legal", None, "x" * 20, staff=True)


# ====================================================================== P0.3 fail-closed partner

class PartnerTest(Base):
    def other_app(self, **cfg):
        return create_app({"DATABASE_PATH": self.app.config["DATABASE_PATH"], "STORAGE_DIR": self.app.config["STORAGE_DIR"],
                           "BASE_URL": "http://localhost", "TESTING": True, **cfg})

    def test_sandbox_off_means_no_partner(self):
        _, d = self._to_awaiting_payment()
        acct = self.account(d)
        off = self.other_app(SANDBOX=False)
        with off.test_request_context("/"):
            p = partners.bank()
            self.assertFalse(p.available)
            self.assertIn("Er is geen financiële partner gekoppeld", p.reason)
            with self.assertRaises(partners.PartnerUnavailable):
                partners.bank_for_account(acct)
            self.assertIn("geen financiële partner", services.dispatch_instructions()["blocked"])
            with self.assertRaises(services.WorkflowError):  # sandbox events refused
                services.handle_bank_event("sandbox", "deposit.received", {"event_id": "z", "external_id": acct["external_id"],
                                                                           "amount_cents": 200000, "ref": "r"})
            pay, problem = services.payment_details(d)
            self.assertIsNone(pay)
            self.assertIn("geen financiële partner", problem)
        c = off.test_client()
        body = json.dumps({"type": "account.blocked", "data": {"event_id": "x", "external_id": acct["external_id"]}}).encode()
        sig = partners.sign_webhook(body, off.config["BANK_WEBHOOK_SECRET"])
        self.assertEqual(c.post("/webhooks/bank/sandbox", data=body, headers={"X-Depiqo-Signature": sig}).status_code, 404)
        # No new Depiqo account can be started; the screen says why.
        c.post("/login", data={"email": "admin@a.test", "password": PW, "csrf_token": self.anon(c)})
        html = c.get("/app/borgen/nieuw").get_data(as_text=True)
        self.assertIn("Er is geen financiële partner gekoppeld", html)
        token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
        r = c.post("/app/borgen/nieuw", data={"address": "X 1", "postcode": "1000 AA", "city": "A", "region": "NL", "tenant_name": "T",
                                              "tenant_email": "t2@huurder.test", "rent": "1000", "amount": "2000", "holding": "depiqo",
                                              "lease_start": "2026-01-01", "csrf_token": token})
        self.assertIn("geen financiële partner gekoppeld", r.get_data(as_text=True))
        self.assertIn("Er is geen financiële partner gekoppeld", c.get("/app").get_data(as_text=True))
        self.assertEqual(c.post(f"/app/borgen/{d['pid']}/sandbox/storting", data={"csrf_token": token}).status_code, 404)

    def test_unknown_partner_is_disabled_and_real_adapter_refuses_sandbox_accounts(self):
        with self.other_app(BANK_PARTNER="banqup").test_request_context("/"):
            self.assertIn("bestaat niet", partners.bank().reason)
        mgr, d = self.to_agreed()
        acct = self.account(d)

        class RealBank(partners.BankPartner):
            name = "testbank"
            calls = []

            def request_release(self, account, tenant_cents, landlord_cents, reference, idempotency_key):
                self.calls.append(idempotency_key)
                return {"provider_ref": "x"}

        partners.BANK_ADAPTERS["testbank"] = RealBank
        try:
            real = self.other_app(BANK_PARTNER="testbank", SANDBOX=False)
            with real.test_request_context("/"):
                with self.assertRaises(partners.PartnerUnavailable):
                    partners.bank_for_account(acct)
                with self.assertRaises(services.WorkflowError):
                    services.start_payout(services.reload(d), None)  # fails closed before any change
                self.assertEqual(services.reload(d)["status"], S.AGREED)
                # An instruction written for the sandbox is never sent by a real adapter.
                with db.transaction():
                    services.enqueue_instruction(d, acct, "release", {"tenant_cents": 1, "landlord_cents": 0, "reference": "r"}, "release:x")
                res = services.dispatch_instructions()
                self.assertEqual(res["failed"], 1)
                self.assertEqual(RealBank.calls, [])
                self.assertIn("sandbox", db.scalar("SELECT last_error FROM bank_instructions WHERE idempotency_key = 'release:x'"))
        finally:
            del partners.BANK_ADAPTERS["testbank"]

    def test_sandbox_marker_on_sandbox_accounts(self):
        mgr, d = self._to_awaiting_payment()
        self.assertIn("SANDBOX", mgr.get(f"/app/borgen/{d['pid']}").get_data(as_text=True))
        self.assertIn('class="tag sbx"', mgr.get("/app/borgen").get_data(as_text=True))
        lines = mgr.get("/app/export.csv").get_data(as_text=True).splitlines()
        self.assertTrue(lines[1].endswith(";ja"))


# ====================================================================== P0.4 outbox

class OutboxTest(Base):
    def test_payout_writes_instruction_with_the_state_change(self):
        mgr, d = self.to_agreed()
        self.app.config["DISPATCH_INLINE"] = False
        fin = self.client("finance@a.test")
        fin.post(f"/app/borgen/{d['pid']}/uitbetalen", data={"csrf_token": self.csrf(fin)})
        self.assertEqual(self.row()["status"], S.PAYOUT_PENDING)
        with self.app.app_context():
            instr = db.one("SELECT * FROM bank_instructions WHERE deposit_id = ? AND kind = 'release'", (d["id"],))
        self.assertEqual(instr["status"], "pending")
        self.assertEqual(json.loads(instr["payload_json"]), {"tenant_cents": 185000, "landlord_cents": 15000, "reference": d["reference"]})
        self.assertEqual(instr["idempotency_key"], f"release:{self.account(d)['id']}")
        # 0.3.1: the account is marked release_requested in the same transaction, before anything is sent
        self.assertEqual(self.account(d)["status"], "release_requested")
        st = self.client("staff@depiqo.test")
        st.post("/admin/opdrachten/versturen", data={"csrf_token": self.csrf(st, "/admin")})
        with self.app.app_context():
            self.assertEqual(db.scalar("SELECT status FROM bank_instructions WHERE id = ?", (instr["id"],)), "acknowledged")
        self.assertEqual(self.account(d)["status"], "release_requested")

    def test_no_instruction_without_state_change(self):
        _, d = self.to_agreed()
        with self.ctx():
            with mock.patch.object(services, "transition", side_effect=services.WorkflowError("gewijzigd")):
                with self.assertRaises(services.WorkflowError):
                    services.start_payout(services.reload(d), None)
            self.assertEqual(db.scalar("SELECT COUNT(*) FROM bank_instructions WHERE kind = 'release'"), 0)

    def test_retries_then_fails_then_staff_retry(self):
        self.app.config["MAX_INSTRUCTION_ATTEMPTS"] = 3
        _, d = self.to_agreed()
        SandboxBank.failures = {"release"}
        try:
            with self.ctx():
                d = services.start_payout(services.reload(d), None)  # inline attempt 1
                iid = db.scalar("SELECT id FROM bank_instructions WHERE kind = 'release'")
                self.assertEqual(db.one("SELECT status, attempts FROM bank_instructions WHERE id = ?", (iid,))[:], ("pending", 1))
                self.assertEqual(services.dispatch_instructions()["retry"], 1)
                self.assertEqual(services.dispatch_instructions()["failed"], 1)
                row = db.one("SELECT * FROM bank_instructions WHERE id = ?", (iid,))
                self.assertEqual((row["status"], row["attempts"]), ("failed", 3))
                self.assertIn("na 3 pogingen", row["last_error"])
                self.assertEqual(services.dispatch_instructions()["sent"], 0)  # failed rows are not picked up again
                rows, _ = finance.reconciliation(only_exceptions=True)
                self.assertTrue(any("Bankopdracht mislukt" in e for r in rows for e in r["exceptions"]))
        finally:
            SandboxBank.failures = set()
        st = self.client("staff@depiqo.test")
        st.post(f"/admin/opdrachten/{iid}/opnieuw", data={"csrf_token": self.csrf(st, "/admin")})
        with self.app.app_context():
            self.assertEqual(db.scalar("SELECT status FROM bank_instructions WHERE id = ?", (iid,)), "acknowledged")

    def test_idempotency_key_gives_one_account(self):
        _, d = self._to_awaiting_payment()
        with self.ctx():
            instr = db.one("SELECT * FROM bank_instructions WHERE deposit_id = ? AND kind = 'open'", (d["id"],))
            tenant = db.one("SELECT * FROM tenants WHERE id = ?", (d["tenant_id"],))
            again = SandboxBank().open_account(d, tenant, instr["idempotency_key"])
            self.assertEqual(again["iban"], self.account(d)["iban"])
            self.assertEqual(db.scalar("SELECT COUNT(*) FROM sandbox_bank_accounts"), 1)
            # A 'sent' row that never got an answer is resent with the same key: still one account.
            old = (now() - timedelta(hours=1)).isoformat(timespec="seconds")
            db.run("UPDATE bank_instructions SET status = 'sent', sent_at = ? WHERE id = ?", (old, instr["id"]))
            services.dispatch_instructions()
            self.assertEqual(db.scalar("SELECT COUNT(*) FROM sandbox_bank_accounts"), 1)
            self.assertEqual(db.scalar("SELECT COUNT(*) FROM bank_accounts WHERE deposit_id = ?", (d["id"],)), 1)

    def test_payout_amounts_must_match_instruction(self):
        mgr, d = self.to_agreed()
        fin = self.client("finance@a.test")
        fin.post(f"/app/borgen/{d['pid']}/uitbetalen", data={"csrf_token": self.csrf(fin)})
        acct = self.account(d)
        anon = self.app.test_client()
        r = self.webhook(anon, "payout.completed", {"event_id": "m1", "external_id": acct["external_id"], "tenant_cents": 200000,
                                                    "landlord_cents": 0, "ref": "p"})
        self.assertEqual(r.json["result"], "mismatch")
        self.assertEqual(self.row()["status"], S.PAYOUT_PENDING)
        with self.app.app_context():
            self.assertIn("wijkt af", db.scalar("SELECT error FROM bank_events WHERE external_event_id = 'm1'"))
        r = self.webhook(anon, "payout.completed", {"event_id": "m2", "external_id": acct["external_id"], "ref": "p"})
        self.assertEqual(r.json["result"], "mismatch")  # no amounts at all
        st = self.client("staff@depiqo.test")
        html = st.get("/admin/afstemming").get_data(as_text=True)
        self.assertIn("wijkt af van de opdracht", html)
        with self.ctx():  # the sandbox reports exactly what it was asked
            payload = SandboxBank().simulate("payout.completed", self.account(d))
            self.assertEqual((payload["tenant_cents"], payload["landlord_cents"]), (185000, 15000))
            self.assertEqual(services.handle_bank_event("sandbox", "payout.completed", payload), "processed")
            self.assertEqual(db.scalar("SELECT status FROM bank_instructions WHERE kind = 'release'"), "confirmed")
            kinds = sorted(r[0] for r in db.all_("SELECT kind FROM bank_transactions WHERE kind LIKE 'payout%'"))
        self.assertEqual(kinds, ["payout_landlord", "payout_tenant"])
        self.assertEqual(self.row()["status"], S.CLOSED)

    def test_cli_dispatch(self):
        _, d = self.to_agreed()
        self.app.config["DISPATCH_INLINE"] = False
        with self.ctx():
            services.start_payout(services.reload(d), None)
        env = {**os.environ, "DATABASE_PATH": self.app.config["DATABASE_PATH"], "STORAGE_DIR": self.app.config["STORAGE_DIR"]}
        out = subprocess.run([sys.executable, os.path.join(ROOT, "run.py"), "dispatch"], env=env, capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("Verstuurd: 1", out.stdout)
        with self.app.app_context():
            self.assertEqual(db.scalar("SELECT status FROM bank_instructions WHERE kind = 'release'"), "acknowledged")


# ====================================================================== P0.5 reconciliation

class ReconciliationTest(Base):
    def test_exceptions_are_listed(self):
        mgr, ext = self.external_awaiting(tenant_email="ext@huurder.test", address="Elders 1")
        mgr.post(f"/app/borgen/{ext['pid']}/ontvangst", data={"csrf_token": self.csrf(mgr)})
        _, dep = self.to_secured()
        old = (now() - timedelta(days=20)).isoformat(timespec="seconds")
        with self.ctx():
            db.run("UPDATE deposits SET evidence_set_at = ? WHERE id = ?", (old, ext["id"]))
            db.run("UPDATE bank_accounts SET ledger_balance_cents = 150000 WHERE deposit_id = ?", (dep["id"],))
            rows, totals = finance.reconciliation(org_id=self.org, only_exceptions=True)
        by_ref = {r["d"]["reference"]: r["exceptions"] for r in rows}
        self.assertTrue(any("al 20 dagen zonder bewijs" in e for e in by_ref[ext["reference"]]))
        self.assertTrue(any("lager dan de vereiste borg" in e for e in by_ref[dep["reference"]]))
        self.assertGreaterEqual(totals["exceptions"], 2)
        self.assertEqual(totals["locked"], 200000)  # only the bank-locked one; the declared one counts for nothing

    def test_release_not_confirmed_after_days(self):
        _, d = self.to_agreed()
        with self.ctx():
            services.start_payout(services.reload(d), None)
            db.run("UPDATE bank_instructions SET created_at = ? WHERE kind = 'release'",
                   ((now() - timedelta(days=9)).isoformat(timespec="seconds"),))
            rows, _ = finance.reconciliation(only_exceptions=True)
        self.assertTrue(any("Vrijgave al 9 dagen niet bevestigd" in e for r in rows for e in r["exceptions"]))

    def test_permissions(self):
        for email, code in (("viewer@a.test", 403), ("manager@a.test", 403), ("finance@a.test", 200), ("admin@a.test", 200)):
            self.assertEqual(self.client(email).get("/app/afstemming").status_code, code, email)
        self.assertEqual(self.client("admin@a.test").get("/admin/afstemming").status_code, 404)
        self.assertEqual(self.client("staff@depiqo.test").get("/admin/afstemming").status_code, 200)


# ====================================================================== P1.6 rules versions

class RulesVersionTest(Base):
    FAKE = "2000-01-01-test"

    def setUp(self):
        super().setUp()
        current = rules.RULESETS[rules.RULE_VERSION]
        nl = current.regions["NL"]
        from dataclasses import replace
        rules.RULESETS[self.FAKE] = rules.RuleSet(version=self.FAKE, internal_target_days=45,
                                                  regions={**current.regions, "NL": replace(nl, max_months=3, return_days=(7, 21))})

    def tearDown(self):
        rules.RULESETS.pop(self.FAKE, None)
        super().tearDown()

    def test_old_version_keeps_old_behaviour(self):
        old = {"region": "NL", "rule_version": self.FAKE, "lease_end": "2026-10-01", "move_out_date": None}
        new = {**old, "rule_version": rules.RULE_VERSION}
        self.assertEqual(rules.max_amount_cents("NL", 100000, "2024-01-01", self.FAKE), (300000, 3))
        self.assertEqual(rules.max_amount_cents("NL", 100000, "2024-01-01"), (200000, 2))
        self.assertEqual(rules.deadline(old, False)[0], date(2026, 10, 8))
        self.assertEqual(rules.deadline(new, False)[0], date(2026, 10, 15))
        self.assertEqual(rules.validate_deposit("NL", 100000, 300000, "2024-01-01", version=self.FAKE), [])
        self.assertTrue(rules.validate_deposit("NL", 100000, 300000, "2024-01-01"))
        vl_old = {**old, "region": "VL"}
        self.assertIn("45 dagen", rules.deadline(vl_old, True)[2])
        with self.assertRaises(rules.UnknownRuleVersion):
            rules.ruleset("1999-nope")
        # A stored deposit keeps its version on screen and in its deadline.
        a = self.client("admin@a.test")
        self.create(a)
        d = self.row()
        self.assertEqual(d["rule_version"], rules.RULE_VERSION)
        with self.app.app_context():
            db.run("UPDATE deposits SET rule_version = ? WHERE id = ?", (self.FAKE, d["id"]))
        html = a.get(f"/app/borgen/{d['pid']}").get_data(as_text=True)
        self.assertIn("max. € 3.000,00 (3 mnd)", html)
        self.assertIn(self.FAKE, html)


# ====================================================================== P1.7 plan history, credit notes, payment status

class PlanHistoryTest(Base):
    def history(self, plan, valid_from):
        with self.app.app_context():
            db.run("INSERT INTO organization_plan_history (org_id, plan, valid_from, created_at) VALUES (?, ?, ?, ?)",
                   (self.org, plan, valid_from.isoformat(), now_iso()))
            db.run("UPDATE organizations SET plan = ?, created_at = ? WHERE id = ?", (plan, "2025-01-01T00:00:00+00:00", self.org))

    def org_row(self):
        with self.app.app_context():
            return db.one("SELECT * FROM organizations WHERE id = ?", (self.org,))

    def test_self_service_change_starts_next_month(self):
        first = today().replace(day=1)
        self.history("essential", add_months(first, -3))
        a = self.client("admin@a.test")
        r = a.post("/app/facturatie/plan", data={"plan": "professional", "csrf_token": self.csrf(a)}, follow_redirects=True)
        self.assertIn("Het geldt vanaf 1 ", r.get_data(as_text=True))
        with self.app.app_context():
            org = db.one("SELECT * FROM organizations WHERE id = ?", (self.org,))
            self.assertEqual(org["plan"], "professional")  # the latest choice
            self.assertEqual(billing.plan_for_period(org, first.strftime("%Y-%m"))["code"], "essential")
            self.assertEqual(billing.plan_for_period(org, add_months(first, 1).strftime("%Y-%m"))["code"], "professional")
            self.assertEqual(billing.estimate(org, first.strftime("%Y-%m"))["lines"][0]["unit_cents"], 9900)
        html = a.get("/app/facturatie").get_data(as_text=True)
        self.assertIn("Plangeschiedenis", html)
        self.assertNotIn("Maak deze factuur aan voordat je van plan wisselt", html)

    def test_invoice_uses_plan_of_its_month(self):
        first = today().replace(day=1)
        self.history("essential", add_months(first, -3))
        st = self.client("staff@depiqo.test")
        st.post(f"/admin/organisaties/{self.org}/plan", data={"plan": "professional", "valid_from": first.strftime("%Y-%m"),
                                                              "csrf_token": self.csrf(st, "/admin")})
        r = st.post(f"/admin/organisaties/{self.org}/plan", data={"plan": "essential", "valid_from": add_months(first, -1).strftime("%Y-%m"),
                                                                  "csrf_token": self.csrf(st, "/admin")}, follow_redirects=True)
        self.assertIn("Kies een ingangsmaand vanaf deze maand", r.get_data(as_text=True))
        last = add_months(first, -1).strftime("%Y-%m")
        with self.app.app_context():
            inv = billing.issue_invoice(self.org_row(), last)
            self.assertEqual(inv["plan"], "essential")
            self.assertEqual(json.loads(inv["lines_json"])[0]["unit_cents"], 9900)
            self.assertEqual(billing.estimate(self.org_row(), first.strftime("%Y-%m"))["plan"]["code"], "professional")

    def test_credit_note_and_payment_status(self):
        first = today().replace(day=1)
        self.history("essential", add_months(first, -3))
        last = add_months(first, -1).strftime("%Y-%m")
        with self.app.app_context():
            inv = billing.issue_invoice(self.org_row(), last)
        self.assertEqual(billing.payment_state(inv)[0], "open")
        self.assertEqual(billing.payment_state(inv, on=local_today() + timedelta(days=30))[0], "overdue")
        a = self.client("admin@a.test")
        self.assertEqual(a.post(f"/admin/facturen/{inv['id']}/betaald", data={"csrf_token": self.csrf(a)}).status_code, 404)
        st = self.client("staff@depiqo.test")
        token = self.csrf(st, "/admin")
        # 0.3.1: credit an open invoice; a credited invoice can no longer be marked paid
        st.post(f"/admin/facturen/{inv['id']}/crediteren", data={"reason": "Verkeerd plan", "csrf_token": token})
        st.post(f"/admin/facturen/{inv['id']}/betaald", data={"csrf_token": token})
        with self.app.app_context():
            orig = db.one("SELECT * FROM invoices WHERE id = ?", (inv["id"],))
            credit = db.one("SELECT * FROM invoices WHERE kind = 'credit'")
            self.assertEqual((orig["status"], orig["payment_status"]), ("credited", "open"))
            self.assertEqual((credit["credit_for_id"], credit["total_cents"]), (inv["id"], -inv["total_cents"]))
            self.assertTrue(billing.invoice_pdf(credit, self.org_row()).startswith(b"%PDF"))
            again = billing.issue_invoice(self.org_row(), last)  # a credited month can be invoiced again
            self.assertNotEqual(again["number"], inv["number"])
            with self.assertRaises(ValueError):
                billing.issue_invoice(self.org_row(), last)
            with self.assertRaises(ValueError):
                billing.credit_invoice(credit["id"], "Nog een keer")
        html = a.get("/app/facturatie").get_data(as_text=True)
        self.assertIn("Creditnota", html)
        self.assertIn("Gecrediteerd", html)


# ====================================================================== P1.8 unit economics

class UnitEconomicsTest(Base):
    def test_numbers_warning_and_settings(self):
        a = self.client("admin@a.test")
        self.create(a)
        self.create(a, tenant_email="b@huurder.test", address="B 1")
        with self.ctx():
            ue = finance.unit_economics()
        row = next(r for r in ue["rows"] if r["org"]["id"] == self.org)
        self.assertEqual((row["depiqo"], row["new_depiqo"]), (2, 2))
        self.assertEqual(row["billed"], 9900 + 2 * 500)
        self.assertEqual(row["cost"], 2 * 50 + 2 * 200)
        self.assertEqual(row["margin"], 9900 + 1000 - 500)
        self.assertEqual(row["marginal_depiqo"], 40 - 50)
        self.assertTrue(row["warn"])
        st = self.client("staff@depiqo.test")
        html = st.get("/admin/unit-economics").get_data(as_text=True)
        self.assertIn("Partnerkosten zijn aannames", html)
        self.assertIn("Negatieve marge per Depiqo-borgrekening", html)
        st.post("/admin/unit-economics", data={"partner_cost_active_cents": "0,20", "partner_cost_new_cents": "1,00",
                                              "partner_cost_external_cents": "0", "csrf_token": self.csrf(st, "/admin")})
        with self.ctx():
            self.assertEqual(finance.get_settings()["partner_cost_active_cents"], 20)
            row = next(r for r in finance.unit_economics()["rows"] if r["org"]["id"] == self.org)
        self.assertEqual((row["cost"], row["marginal_depiqo"]), (2 * 20 + 2 * 100, 20))
        self.assertNotIn("Negatieve marge per Depiqo-borgrekening", st.get("/admin/unit-economics").get_data(as_text=True))
        self.assertEqual(a.get("/admin/unit-economics").status_code, 404)


# ====================================================================== P1.9 import

def csv_bytes(rows, delimiter=";", bom=True, encoding="utf-8"):
    import csv
    out = io.StringIO()
    csv.writer(out, delimiter=delimiter, lineterminator="\r\n").writerows([imports.COLUMNS, *rows])
    return (("\ufeff" if bom else "") + out.getvalue()).encode(encoding)


GOOD = [
    ("Kerkstraat 1", "1017 GA", "Amsterdam", "NL", "Anna Boer", "anna@huurder.test", "1.250,00", "2.500,00", "01-05-2023", "external", "", "declared"),
    ("Meir 10", "2000", "Antwerpen", "VL", "Bart Peeters", "bart@huurder.test", "950", "2850", "2024-09-01", "elders", "", ""),
]


class ImportTest(Base):
    def upload_csv(self, c, data, name="borgen.csv"):
        return c.post("/app/borgen/import", data={"file": (io.BytesIO(data), name), "csrf_token": self.csrf(c)},
                      content_type="multipart/form-data")

    def test_preview_then_commit_in_one_go(self):
        a = self.client("admin@a.test")
        r = self.upload_csv(a, csv_bytes(GOOD))
        self.assertEqual(r.status_code, 302)
        preview = a.get(r.headers["Location"]).get_data(as_text=True)
        self.assertIn("Alles klopt", preview)
        with self.app.app_context():
            self.assertEqual(db.scalar("SELECT COUNT(*) FROM deposits"), 0)  # nothing before the commit
            batch = db.one("SELECT * FROM import_batches")
        mails_before = self.mail_count()
        a.post(f"/app/borgen/import/{batch['id']}/bevestigen", data={"csrf_token": self.csrf(a)})
        with self.app.app_context():
            rows = db.all_("SELECT * FROM deposits ORDER BY id")
        self.assertEqual(len(rows), 2)
        for d in rows:
            self.assertEqual((d["status"], d["evidence_level"], d["holding"], d["import_batch_id"]), (S.SECURED, "declared", "external", batch["id"]))
            self.assertIsNone(d["eligible_value_cents"])
        self.assertTrue(rows[0]["activated_at"].startswith("2023-05-01"))
        self.assertEqual(rows[1]["amount_cents"], 285000)
        self.assertEqual(self.mail_count(), mails_before)  # no invitations unless chosen
        r = a.post(f"/app/borgen/import/{batch['id']}/bevestigen", data={"csrf_token": self.csrf(a)}, follow_redirects=True)
        self.assertIn("al verwerkt", r.get_data(as_text=True))
        with self.app.app_context():
            self.assertEqual(db.scalar("SELECT COUNT(*) FROM deposits"), 2)
        # Imported with an old lease start: not 'new' this month for billing.
        with self.app.app_context():
            org = db.one("SELECT * FROM organizations WHERE id = ?", (self.org,))
            self.assertEqual(billing.estimate(org, today().strftime("%Y-%m"))["new"], 0)

    def mail_count(self):
        with self.app.app_context():
            return db.scalar("SELECT COUNT(*) FROM outbox_emails")

    def test_errors_per_row_block_the_commit(self):
        bad = GOOD + [
            ("Laan 3", "1000 AA", "Amsterdam", "XX", "C", "c@huurder.test", "1000", "2000", "2024-01-01", "external", "", ""),
            ("Laan 4", "1000 AA", "Amsterdam", "NL", "D", "d@huurder.test", "1000", "2500", "2024-01-01", "external", "", ""),
            ("=HYPERLINK(1)", "1000 AA", "Amsterdam", "NL", "E", "e@huurder.test", "1000", "2000", "2024-01-01", "external", "", ""),
            ("Laan 6", "1000 AA", "Amsterdam", "NL", "F", "geen-mail", "1000", "2000", "31-02-2024", "external", "NL00BANK", "verified"),
            GOOD[0],
        ]
        a = self.client("admin@a.test")
        r = self.upload_csv(a, csv_bytes(bad))
        html = a.get(r.headers["Location"] + "?toon=fouten").get_data(as_text=True)
        for text in ("Kies Nederland, Vlaanderen of Brussel", "maximaal 2 maanden", "formules zijn niet toegestaan",
                     "geen geldig adres", "Start huur", "IBAN klopt niet", "alleen &#39;declared&#39;", "al eerder in het bestand",
                     "Nog niet importeren"):
            self.assertIn(text, html)
        with self.app.app_context():
            batch = db.one("SELECT * FROM import_batches")
        self.assertEqual((batch["row_count"], batch["error_count"]), (7, 5))
        r = a.post(f"/app/borgen/import/{batch['id']}/bevestigen", data={"csrf_token": self.csrf(a)}, follow_redirects=True)
        self.assertIn("Er staan nog fouten", r.get_data(as_text=True))
        with self.app.app_context():
            self.assertEqual(db.scalar("SELECT COUNT(*) FROM deposits"), 0)

    def test_formats_limits_and_permissions(self):
        a = self.client("admin@a.test")
        with self.ctx():
            rows = imports.parse(csv_bytes(GOOD, delimiter=",", bom=False, encoding="cp1252"), self.org)  # comma, no BOM, Windows-1252
            self.assertEqual([r["errors"] for r in rows], [[], []])
            rows = imports.parse(imports.template_csv().encode("utf-8"), self.org)  # the template parses cleanly
            self.assertEqual([r["errors"] for r in rows], [[], [], []])  # 0.4.0: a third example row (a guarantee)
            with self.assertRaises(imports.ImportProblem):
                imports.parse(b"adres;plaats\nx;y\n", self.org)
            with self.assertRaises(imports.ImportProblem) as cm:
                imports.parse(csv_bytes([GOOD[0]] * 5001), self.org)
            self.assertIn("meer dan 5000 rijen", str(cm.exception))
        big = csv_bytes([GOOD[0]]) + b"x" * (2 * 1024 * 1024)
        self.assertIn("groter dan 2 MB", self.upload_csv(a, big).get_data(as_text=True))
        self.assertEqual(a.get("/app/borgen/import/sjabloon.csv").status_code, 200)
        m = self.client("manager@a.test")
        self.assertEqual(m.get("/app/borgen/import").status_code, 403)
        self.assertEqual(self.client("admin@b.test").get("/app/borgen/import/1").status_code, 404)

    def test_import_with_invitations_links_wallet_without_status_change(self):
        a = self.client("admin@a.test")
        r = self.upload_csv(a, csv_bytes(GOOD[:1]))
        batch_id = int(r.headers["Location"].rstrip("/").split("/")[-1])
        a.post(f"/app/borgen/import/{batch_id}/bevestigen", data={"send_invites": "1", "csrf_token": self.csrf(a)})
        with self.app.app_context():
            body = db.scalar("SELECT body_text FROM outbox_emails ORDER BY id DESC LIMIT 1")
        self.assertIn("Je hoeft niets te betalen", body)
        link = re.search(r"http://localhost(/t/[\w-]+)", body).group(1)
        tenant = self.app.test_client()
        self.assertEqual(tenant.post(link, data={"confirm_details": "1", "password": PW, "csrf_token": self.anon(tenant, link)}).status_code, 302)
        d = self.row()
        self.assertEqual(d["status"], S.SECURED)
        html = tenant.get(f"/wallet/borg/{d['pid']}").get_data(as_text=True)
        self.assertIn("Ontvangst verklaard door je verhuurder", html)


# ====================================================================== P1.10 bulk actions

class BulkTest(Base):
    def test_bulk_invite_remind_and_export(self):
        a = self.client("admin@a.test")
        self.create(a, send_invite="", tenant_email="c1@huurder.test", address="C 1")
        concept = self.row()
        _, awaiting = self._to_awaiting_payment()
        mgr, ext = self.external_awaiting(tenant_email="x@huurder.test", address="X 1")
        mgr.post(f"/app/borgen/{ext['pid']}/ontvangst", data={"csrf_token": self.csrf(mgr)})
        b = self.client("admin@b.test")
        self.create(b, tenant_email="other@huurder.test")
        foreign = self.row()
        pids = [concept["pid"], awaiting["pid"], ext["pid"], foreign["pid"]]
        r = a.post("/app/borgen/bulk", data={"action": "uitnodigen", "pids": pids, "csrf_token": self.csrf(a)}, follow_redirects=True)
        html = r.get_data(as_text=True)
        self.assertIn("1 uitnodiging verstuurd, 3 overgeslagen", html)  # only the concept; the others have no fitting status
        self.assertEqual(self.row(concept["pid"])["status"], S.INVITED)
        r = a.post("/app/borgen/bulk", data={"action": "herinneren", "pids": pids, "csrf_token": self.csrf(a)}, follow_redirects=True)
        self.assertIn("1 herinnering verstuurd, 3 overgeslagen", r.get_data(as_text=True))
        r = a.post("/app/borgen/bulk", data={"action": "herinneren", "pids": [awaiting["pid"]], "csrf_token": self.csrf(a)}, follow_redirects=True)
        self.assertIn("al een herinnering verstuurd", r.get_data(as_text=True))
        with self.app.app_context():
            self.assertEqual(db.scalar("SELECT COUNT(*) FROM outbox_emails WHERE subject LIKE 'Herinnering%'"), 1)
        r = a.post("/app/borgen/bulk", data={"action": "export", "pids": [ext["pid"], foreign["pid"]], "csrf_token": self.csrf(a)})
        text = r.get_data(as_text=True)
        self.assertEqual(r.mimetype, "text/csv")
        self.assertEqual(len(text.strip().splitlines()), 2)  # header + only our own selected dossier
        self.assertIn(ext["reference"], text)
        self.assertNotIn(foreign["reference"], text)
        v = self.client("viewer@a.test")
        self.assertEqual(v.post("/app/borgen/bulk", data={"action": "uitnodigen", "pids": pids, "csrf_token": self.csrf(v)}).status_code, 403)
        f = self.client("finance@a.test")
        self.assertEqual(f.post("/app/borgen/bulk", data={"action": "herinneren", "pids": pids, "csrf_token": self.csrf(f)}).status_code, 403)
        self.assertEqual(f.post("/app/borgen/bulk", data={"action": "export", "pids": pids, "csrf_token": self.csrf(f)}).status_code, 200)


# ====================================================================== P1.11 action centre

class ActionCentreTest(Base):
    def test_grouped_tasks_with_direct_actions(self):
        a = self.client("admin@a.test")
        self.create(a, send_invite="", tenant_email="c1@huurder.test", address="Conceptlaan 1")
        concept = self.row()
        _, awaiting = self._to_awaiting_payment()
        mgr, ext = self.external_awaiting(tenant_email="x@huurder.test", address="Elderslaan 1")
        with self.ctx():
            groups = {g["key"]: [i["d"]["pid"] for i in g["tasks"]] for g in services.action_centre(self.org)}
        self.assertEqual(groups["uitnodigen"], [concept["pid"]])
        self.assertEqual(groups["herinneren"], [awaiting["pid"]])
        self.assertEqual(groups["bevestigen"], [ext["pid"]])
        mgr.post(f"/app/borgen/{ext['pid']}/ontvangst", data={"csrf_token": self.csrf(mgr)})
        with self.ctx():
            groups = {g["key"]: [i["d"]["pid"] for i in g["tasks"]] for g in services.action_centre(self.org)}
        self.assertEqual(groups["bewijs"], [ext["pid"]])
        html = a.get("/app").get_data(as_text=True)
        for text in ("Vandaag te doen", "Uitnodigen", "Herinneren", "Bewijs ontbreekt", "Herinnering sturen", "Bankbewijs toevoegen"):
            self.assertIn(text, html)
        r = a.post(f"/app/borgen/{concept['pid']}/uitnodigen", data={"next": "dashboard", "csrf_token": self.csrf(a)})
        self.assertTrue(r.headers["Location"].endswith("/app"))
        self.assertEqual(self.row(concept["pid"])["status"], S.INVITED)
        # Viewers see the tasks but no action buttons.
        self.assertNotIn("Herinnering sturen</button>", self.client("viewer@a.test").get("/app").get_data(as_text=True))

    def test_sorted_by_deadline(self):
        with self.ctx():
            uid = self.uid("admin@a.test")
            ds = []
            for i, days in enumerate((3, 40)):  # moved out 3 and 40 days ago: 40 is overdue (NL 14 days)
                d = services.create_deposit(self.org, uid, {"address": f"Weg {i}", "postcode": "1000 AA", "city": "A", "region": "NL",
                                                           "tenant_name": "T", "tenant_email": f"t{i}@huurder.test", "rent_cents": 100000,
                                                           "amount_cents": 200000, "holding": "external", "lease_start": "2022-01-01",
                                                           "external_iban": "NL91ABNA0417164300"})
                db.run("UPDATE deposits SET status = ?, move_out_date = ? WHERE id = ?", (S.MOVE_OUT, (local_today() - timedelta(days=days)).isoformat(), d["id"]))
                ds.append(d)
            groups = services.action_centre(self.org)
        afrekenen = next(g for g in groups if g["key"] == "afrekenen")
        self.assertEqual([i["d"]["pid"] for i in afrekenen["tasks"]], [ds[1]["pid"], ds[0]["pid"]])
        self.assertEqual(groups[0]["key"], "afrekenen")  # the group with an overdue task comes first


# ====================================================================== P1.12 two-factor authentication

class TwoFactorTest(Base):
    def test_rfc6238_vectors(self):
        key = b"12345678901234567890"
        for t, code in ((59, "94287082"), (1111111109, "07081804"), (1111111111, "14050471"), (1234567890, "89005924"),
                        (2000000000, "69279037"), (20000000000, "65353130")):
            self.assertEqual(mfa.hotp(key, t // 30, digits=8), code, t)

    def test_window_and_replay(self):
        secret = mfa.new_secret()
        t = 1_800_000_000
        step = t // 30
        self.assertEqual(mfa.match_step(secret, mfa.totp(secret, t), at=t), step)
        self.assertEqual(mfa.match_step(secret, mfa.totp(secret, t - 30), at=t), step - 1)
        self.assertEqual(mfa.match_step(secret, mfa.totp(secret, t + 30), at=t), step + 1)
        self.assertIsNone(mfa.match_step(secret, mfa.totp(secret, t + 90), at=t))
        self.assertIsNone(mfa.match_step(secret, mfa.totp(secret, t), last_step=step, at=t))  # used once
        self.assertTrue(mfa.otpauth_uri(secret, "a@b.test").startswith("otpauth://totp/Depiqo%3Aa%40b.test?secret="))

    def enable(self, c, email):
        c.post("/account/beveiliging", data={"action": "start", "csrf_token": self.csrf(c, "/account/beveiliging")})
        page = c.get("/account/beveiliging").get_data(as_text=True)
        secret = re.search(r'data-totp-secret="([A-Z2-7]+)"', page).group(1)
        self.assertIn("otpauth://totp/", page)
        r = c.post("/account/beveiliging", data={"action": "confirm", "code": "000000", "csrf_token": self.csrf(c, "/account/beveiliging")})
        self.assertIn("Deze code klopt niet", r.get_data(as_text=True))
        r = c.post("/account/beveiliging", data={"action": "confirm", "code": mfa.totp(secret), "csrf_token": self.csrf(c, "/account/beveiliging")})
        codes = re.findall(r'<li class="mono">([a-z0-9]{5}-[a-z0-9]{5})</li>', r.get_data(as_text=True))
        self.assertEqual(len(codes), 10)
        return secret, codes

    def login_password(self, email):
        c = self.app.test_client()
        r = c.post("/login", data={"email": email, "password": PW, "csrf_token": self.anon(c)})
        return c, r

    def test_enable_and_login_with_code_and_recovery(self):
        a = self.client("finance@a.test")
        secret, codes = self.enable(a, "finance@a.test")
        with self.app.app_context():
            u = db.one("SELECT * FROM users WHERE email = 'finance@a.test'")
            self.assertTrue(u["totp_enabled_at"])
            self.assertEqual(db.scalar("SELECT COUNT(*) FROM recovery_codes WHERE user_id = ?", (u["id"],)), 10)
            self.assertFalse(any(c in str(db.all_("SELECT code_hash FROM recovery_codes")) for c in codes))  # only hashes
        c, r = self.login_password("finance@a.test")
        self.assertTrue(r.headers["Location"].endswith("/login/code"))
        self.assertEqual(c.get("/app").status_code, 302)  # no session yet
        r = c.post("/login/code", data={"code": mfa.totp(secret), "csrf_token": self.anon(c, "/login/code")})
        self.assertIn("al gebruikt", r.get_data(as_text=True))  # same step as the confirmation: replay refused
        r = c.post("/login/code", data={"code": mfa.totp(secret, time.time() + 30), "csrf_token": self.anon(c, "/login/code")})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(c.get("/app").status_code, 200)
        # A recovery code works once.
        c2, _ = self.login_password("finance@a.test")
        r = c2.post("/login/code", data={"code": codes[0].upper().replace("-", " "), "csrf_token": self.anon(c2, "/login/code")})
        self.assertEqual(r.status_code, 302)
        c3, _ = self.login_password("finance@a.test")
        r = c3.post("/login/code", data={"code": codes[0], "csrf_token": self.anon(c3, "/login/code")})
        self.assertEqual(r.status_code, 200)
        with self.app.app_context():
            self.assertEqual(mfa.recovery_left(u["id"]), 9)
            self.assertEqual(db.scalar("SELECT COUNT(*) FROM audit_log WHERE action = 'mfa.recovery_used'"), 1)

    def test_wrong_codes_are_rate_limited(self):
        a = self.client("viewer@a.test")
        self.enable(a, "viewer@a.test")
        c, _ = self.login_password("viewer@a.test")
        for _ in range(5):
            c.post("/login/code", data={"code": "123456", "csrf_token": self.anon(c, "/login/code")})
        r = c.post("/login/code", data={"code": "123456", "csrf_token": self.anon(c, "/login/code")}, follow_redirects=True)
        self.assertIn("Te veel verkeerde codes", r.get_data(as_text=True))

    def test_password_reset_does_not_skip_second_factor(self):
        a = self.client("viewer@a.test")
        self.enable(a, "viewer@a.test")
        c = self.app.test_client()
        c.post("/wachtwoord-vergeten", data={"email": "viewer@a.test", "csrf_token": self.anon(c, "/wachtwoord-vergeten")})
        with self.app.app_context():
            body = db.scalar("SELECT body_text FROM outbox_emails WHERE to_email = 'viewer@a.test' ORDER BY id DESC LIMIT 1")
        path = re.search(r"http://localhost(/wachtwoord/[\w-]+)", body).group(1)
        n = self.app.test_client()
        r = n.post(path, data={"password": "Nieuw-Wachtwoord-2026", "csrf_token": self.anon(n, path)})
        self.assertTrue(r.headers["Location"].endswith("/login/code"))
        self.assertEqual(n.get("/app").status_code, 302)

    def test_banner_and_staff_requirement(self):
        self.assertIn("Zet twee-stapsverificatie aan", self.client("admin@a.test").get("/app").get_data(as_text=True))
        self.assertNotIn("Zet twee-stapsverificatie aan", self.client("viewer@a.test").get("/app").get_data(as_text=True))
        st = self.client("staff@depiqo.test")
        self.assertEqual(st.get("/admin").status_code, 200)  # off by default outside production
        self.app.config["REQUIRE_2FA_FOR_STAFF"] = True
        r = st.get("/admin/afstemming")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/account/beveiliging", r.headers["Location"])
        self.enable(st, "staff@depiqo.test")
        self.assertEqual(st.get("/admin/afstemming").status_code, 200)
        self.assertNotIn("Zet twee-stapsverificatie aan", st.get("/admin").get_data(as_text=True))
        with mock.patch.dict(os.environ, {"DEPIQO_ENV": "production", "SECRET_KEY": "x" * 40, "BANK_WEBHOOK_SECRET": "y" * 40,
                                          "BASE_URL": "https://app.example.test"}):
            prod = create_app({"DATABASE_PATH": os.path.join(self.tmp, "p.sqlite3"), "STORAGE_DIR": os.path.join(self.tmp, "pf")})
        self.assertTrue(prod.config["REQUIRE_2FA_FOR_STAFF"])

    def test_disable_needs_a_code(self):
        a = self.client("admin@a.test")
        secret, _ = self.enable(a, "admin@a.test")
        r = a.post("/account/beveiliging", data={"action": "disable", "code": "111111", "csrf_token": self.csrf(a, "/account/beveiliging")})
        self.assertIn("Vul een geldige code", r.get_data(as_text=True))
        a.post("/account/beveiliging", data={"action": "disable", "code": mfa.totp(secret, time.time() + 30),
                                             "csrf_token": self.csrf(a, "/account/beveiliging")})
        with self.app.app_context():
            self.assertIsNone(db.scalar("SELECT totp_enabled_at FROM users WHERE email = 'admin@a.test'"))


# ====================================================================== P1.13 communication log

class CommunicationLogTest(Base):
    def test_mails_per_deposit(self):
        mgr, d = self._to_awaiting_payment()
        mgr.post(f"/app/borgen/{d['pid']}/herinneren", data={"csrf_token": self.csrf(mgr)})
        with self.app.app_context():
            db.run("UPDATE outbox_emails SET error = 'SMTP 550' WHERE subject LIKE 'Herinnering%'")
            db.run("INSERT INTO outbox_emails (to_email, subject, body_text, created_at, provider, sent_at, deposit_id) VALUES (?, ?, ?, ?, 'smtp', ?, ?)",
                   ("tess@huurder.test", "Verzonden test", "x", now_iso(), now_iso(), d["id"]))
        html = mgr.get(f"/app/borgen/{d['pid']}").get_data(as_text=True)
        section = html[html.index('id="communicatie"'):]
        for text in ("vraagt je waarborgsom via Depiqo", "Herinnering: stort je waarborgsom", "tess@huurder.test", "In outbox", "Mislukt", "Verzonden"):
            self.assertIn(text, section)
        self.create(self.client("admin@b.test"), tenant_email="other@huurder.test")
        self.assertNotIn("other@huurder.test", section)


# ====================================================================== migration 004

class Migration004Test(Base):
    def test_backfill(self):
        import glob
        src = os.path.join(ROOT, "migrations")
        old_dir = os.path.join(self.tmp, "m")
        os.makedirs(old_dir)
        for f in sorted(glob.glob(os.path.join(src, "*.sql"))):
            if os.path.basename(f)[:3] in ("001", "002", "003"):
                shutil.copy(f, old_dir)
        path = os.path.join(self.tmp, "old.sqlite3")
        db.migrate(path, old_dir)
        conn = db.connect(path)
        conn.execute("INSERT INTO organizations (id, name, plan, created_at) VALUES (1, 'Oud BV', 'professional', '2026-03-15T10:00:00+00:00')")
        conn.execute("INSERT INTO properties (id, org_id, address, postcode, city, region, created_at) VALUES (1, 1, 'A 1', '1000 AA', 'X', 'NL', '2026-01-01')")
        conn.execute("INSERT INTO tenants (id, org_id, name, email, created_at) VALUES (1, 1, 'T', 't@t.test', '2026-01-01')")
        for i, (holding, status) in enumerate((("external", "secured"), ("depiqo", "payout_pending")), 1):
            conn.execute("INSERT INTO deposits (id, pid, reference, org_id, property_id, tenant_id, region, holding, rent_cents, amount_cents, status, "
                         "lease_start, rule_version, created_at, updated_at, secured_at, eligible_value_cents) VALUES (?, ?, ?, 1, 1, 1, 'NL', ?, 100000, 200000, ?, "
                         "'2026-01-01', '2026-10-18', '2026-01-01', '2026-01-01', '2026-01-02', 200000)", (i, f"p{i}", f"DPQ-001-0000{i}", holding, status))
        conn.execute("INSERT INTO bank_accounts (deposit_id, provider, external_id, iban, holder_name, status, ledger_balance_cents, opened_at) "
                     "VALUES (2, 'sandbox', 'x2', 'NL00', 'T', 'release_requested', 200000, '2026-01-01')")
        conn.execute("INSERT INTO sandbox_bank_accounts (external_id, iban, holder_name, created_at) VALUES ('x2', 'NL00X', 'T', '2026-01-01')")
        conn.execute("INSERT INTO deposit_events (deposit_id, org_id, at, actor_kind, type, to_status, message, data_json) "
                     "VALUES (2, 1, '2026-02-01', 'user', 'status', 'payout_pending', 'm', '{\"huurder\":180000,\"verhuurder\":20000}')")
        conn.execute("INSERT INTO invoices (org_id, period, number, status, subtotal_cents, vat_cents, total_cents, lines_json, issued_at) "
                     "VALUES (1, '2026-03', 'DPQ-2026-00001', 'paid', 100, 21, 121, '[]', '2026-04-01T09:00:00+00:00')")
        conn.execute("INSERT INTO outbox_emails (to_email, subject, body_text, created_at, provider) VALUES ('t@t.test', 's', 'Kenmerk: DPQ-001-00002', '2026-01-01', 'outbox')")
        conn.close()
        shutil.copy(os.path.join(src, "004_evidence_outbox_history_2fa.sql"), old_dir)
        db.migrate(path, old_dir)
        conn = db.connect(path)
        ext = conn.execute("SELECT evidence_level, eligible_value_cents FROM deposits WHERE id = 1").fetchone()
        self.assertEqual(tuple(ext), ("declared", None))
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM deposit_evidence WHERE deposit_id = 1").fetchone()[0], 1)
        instr = conn.execute("SELECT kind, status, payload_json, idempotency_key FROM bank_instructions").fetchone()
        self.assertEqual((instr[0], instr[1], instr[3]), ("release", "acknowledged", "release:1"))
        self.assertEqual(json.loads(instr[2]), {"tenant_cents": 180000, "landlord_cents": 20000, "reference": "DPQ-001-00002"})
        self.assertEqual(tuple(conn.execute("SELECT release_tenant_cents, release_landlord_cents FROM sandbox_bank_accounts").fetchone()), (180000, 20000))
        self.assertEqual(tuple(conn.execute("SELECT plan, valid_from FROM organization_plan_history").fetchone()), ("professional", "2026-03-01"))
        inv = conn.execute("SELECT kind, status, payment_status, due_at FROM invoices").fetchone()
        self.assertEqual(tuple(inv), ("invoice", "issued", "paid", "2026-04-15"))
        self.assertEqual(conn.execute("SELECT deposit_id FROM outbox_emails").fetchone()[0], 2)
        conn.close()


if __name__ == "__main__":
    unittest.main()
