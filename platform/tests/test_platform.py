"""Tests for rules, state machine, billing, the full deposit flow and security boundaries.

    python -m unittest discover -s tests -v
"""
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.util import today as local_today  # noqa: E402
from app import billing, create_app, db, rules  # noqa: E402
from app import states as S  # noqa: E402
from app.partners import sign_webhook  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.util import now_iso, parse_euros, valid_iban  # noqa: E402

PW = "Correct-Horse-2026"


class RulesTest(unittest.TestCase):
    def test_max_amounts(self):
        self.assertEqual(rules.max_amount_cents("NL", 120000, "2024-01-01")[0], 240000)
        self.assertEqual(rules.max_amount_cents("VL", 100000, "2024-01-01")[0], 300000)
        self.assertEqual(rules.max_amount_cents("VL", 100000, "2018-06-01")[0], 200000)
        self.assertEqual(rules.max_amount_cents("BRU", 100000, "2025-01-01")[0], 200000)

    def test_validation_messages(self):
        self.assertEqual(rules.validate_deposit("NL", 120000, 240000, "2026-01-01"), [])
        errs = rules.validate_deposit("NL", 120000, 240001, "2026-01-01")
        self.assertTrue(any("maximaal 2 maanden" in e for e in errs))
        self.assertTrue(rules.validate_deposit("NL", 120000, 200000, "2026-02-01", "2026-01-01"))

    def test_deadlines(self):
        d = {"region": "NL", "lease_end": "2026-10-01", "move_out_date": None}
        self.assertEqual(rules.deadline(d, False)[0], date(2026, 10, 15))
        self.assertEqual(rules.deadline(d, True)[0], date(2026, 10, 31))
        b = {"region": "BRU", "lease_end": None, "move_out_date": "2026-01-31"}
        self.assertEqual(rules.deadline(b, False)[0], date(2026, 3, 31))
        v = {"region": "VL", "lease_end": "2026-10-01", "move_out_date": None}
        due, statutory, _ = rules.deadline(v, True)
        self.assertFalse(statutory)


class StatesTest(unittest.TestCase):
    def test_payment_alone_never_secures(self):
        with self.assertRaises(S.TransitionError):
            S.check(S.AWAITING_PAYMENT, S.PAYMENT_RECEIVED, "tenant")
        with self.assertRaises(S.TransitionError):
            S.check(S.AWAITING_PAYMENT, S.SECURED, "tenant")
        S.check(S.PAYMENT_RECEIVED, S.SECURED, "bank")

    def test_terminal_and_hold(self):
        with self.assertRaises(S.TransitionError):
            S.check(S.CLOSED, S.SECURED, "bank")
        with self.assertRaises(S.TransitionError):
            S.check(S.LEGAL_HOLD, S.MOVE_OUT, "user")


class BillingTest(unittest.TestCase):
    def test_essential_example(self):
        # 99 + (360 - 100) * 0,75 + 540 * 0,40 + 30 * 5,00 = 99 + 195 + 216 + 150
        lines, total = billing.price(360, 540, 30, "essential")
        self.assertEqual(total, 66000)
        by_kind = {l["kind"]: l for l in lines}
        self.assertEqual(by_kind["included"]["quantity"], 100)
        self.assertEqual(by_kind["extra_external"]["quantity"], 260)
        self.assertEqual(by_kind["extra_depiqo"]["quantity"], 540)
        self.assertEqual(by_kind["new"]["total_cents"], 15000)

    def test_professional_example(self):
        # 299 + 0 external extra + (540 - 140) * 0,25 + 30 * 3,00 = 299 + 100 + 90
        lines, total = billing.price(360, 540, 30, "professional")
        self.assertEqual(total, 48900)
        by_kind = {l["kind"]: l for l in lines}
        self.assertEqual(by_kind["extra_external"]["quantity"], 0)
        self.assertEqual(by_kind["extra_depiqo"]["quantity"], 400)

    def test_included_applies_to_external_first(self):
        _, total = billing.price(80, 40, 0, "essential")
        self.assertEqual(total, 9900 + 20 * 40)  # the 20 left over are Depiqo dossiers, the cheaper kind

    def test_all_lines_are_shown(self):
        lines, total = billing.price(0, 0, 0, "essential")
        self.assertEqual([l["kind"] for l in lines], ["base", "included", "extra_external", "extra_depiqo", "new"])
        self.assertEqual(total, 9900)

    def test_pilot_is_free(self):
        lines, total = billing.price(200, 200, 12, "professional", pilot=True)
        self.assertEqual(total, 0)
        self.assertEqual(lines[-1]["kind"], "pilot")
        self.assertEqual(lines[-1]["total_cents"], -(29900 + 12 * 300))

    def test_enterprise_overrides_fall_back_to_professional(self):
        org = {"plan": "enterprise", "ent_base_cents": 100000, "ent_included": 2000, "ent_extra_external_cents": None,
               "ent_extra_depiqo_cents": 10, "ent_new_dossier_cents": 0}
        plan = billing.plan_for(org)
        self.assertEqual((plan["base_cents"], plan["included"], plan["extra_external_cents"], plan["extra_depiqo_cents"],
                          plan["new_dossier_cents"]), (100000, 2000, 45, 10, 0))
        _, total = billing.price(1500, 1000, 50, plan)
        self.assertEqual(total, 100000 + 500 * 10)

    def test_overrides_ignored_without_enterprise(self):
        org = {"plan": "essential", "ent_base_cents": 1, "ent_included": 1, "ent_extra_external_cents": 1,
               "ent_extra_depiqo_cents": 1, "ent_new_dossier_cents": 1}
        self.assertEqual(billing.plan_for(org)["base_cents"], 9900)


class UtilTest(unittest.TestCase):
    def test_parse_euros(self):
        self.assertEqual(parse_euros("2.400,50"), 240050)
        self.assertEqual(parse_euros("2400.5"), 240050)
        self.assertEqual(parse_euros("2400"), 240000)
        self.assertIsNone(parse_euros("12abc"))
        self.assertIsNone(parse_euros("-5"))

    def test_iban(self):
        self.assertTrue(valid_iban("NL91 ABNA 0417 1643 00"))
        self.assertFalse(valid_iban("NL91 ABNA 0417 1643 01"))


class FlowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app = create_app({"DATABASE_PATH": os.path.join(self.tmp, "t.sqlite3"), "STORAGE_DIR": os.path.join(self.tmp, "files"),
                               "BASE_URL": "http://localhost", "TESTING": True})
        os.makedirs(self.app.config["STORAGE_DIR"], exist_ok=True)
        with self.app.app_context():
            self.org = db.run("INSERT INTO organizations (name, created_at) VALUES ('Org A', ?)", (now_iso(),))
            self.org2 = db.run("INSERT INTO organizations (name, created_at) VALUES ('Org B', ?)", (now_iso(),))
            db.run("INSERT INTO users (email, name, password_hash, is_staff, created_at) VALUES ('staff@depiqo.test', 'Staff', ?, 1, ?)",
                   (hash_password(PW), now_iso()))
            for email, org, role in (("admin@a.test", self.org, "admin"), ("manager@a.test", self.org, "manager"),
                                     ("finance@a.test", self.org, "finance"), ("viewer@a.test", self.org, "viewer"),
                                     ("admin@b.test", self.org2, "admin")):
                uid = db.run("INSERT INTO users (email, name, password_hash, created_at) VALUES (?, ?, ?, ?)",
                             (email, email.split("@")[0].title(), hash_password(PW), now_iso()))
                db.run("INSERT INTO memberships (user_id, org_id, role, created_at) VALUES (?, ?, ?, ?)", (uid, org, role, now_iso()))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---- helpers
    def client(self, email=None):
        c = self.app.test_client()
        if email:
            r = c.post("/login", data={"email": email, "password": PW, "csrf_token": self.anon(c)})
            self.assertEqual(r.status_code, 302, r.data[:300])
        return c

    def anon(self, c, path="/login"):
        html = c.get(path).get_data(as_text=True)
        return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)

    def accept(self, c, link):
        return c.post(link, data={"confirm_details": "1", "password": PW, "csrf_token": self.anon(c, link)})

    def csrf(self, c, path="/app"):
        html = c.get(path).get_data(as_text=True)
        return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)

    def create(self, c, **over):
        data = {"address": "Teststraat 1", "postcode": "1000 AA", "city": "Amsterdam", "region": "NL", "tenant_name": "Tess Huurder",
                "tenant_email": "tess@huurder.test", "rent": "1.000,00", "amount": "2.000,00", "holding": "depiqo",
                "lease_start": (local_today() - timedelta(days=400)).isoformat(), "send_invite": "1"}
        data.update(over)
        data["csrf_token"] = self.csrf(c)
        return c.post("/app/borgen/nieuw", data=data)

    def deposit(self, **where):
        with self.app.app_context():
            return db.one("SELECT * FROM deposits ORDER BY id DESC LIMIT 1")

    def invite_link(self):
        with self.app.app_context():
            body = db.scalar("SELECT body_text FROM outbox_emails WHERE body_text LIKE '%/t/%' ORDER BY id DESC LIMIT 1")
        return re.search(r"http://localhost(/t/[\w-]+)", body).group(1)

    def webhook(self, c, etype, data):
        body = json.dumps({"type": etype, "data": data}).encode()
        sig = sign_webhook(body, self.app.config["BANK_WEBHOOK_SECRET"])
        return c.post("/webhooks/bank/sandbox", data=body, headers={"X-Depiqo-Signature": sig, "Content-Type": "application/json"})

    def account(self, d):
        with self.app.app_context():
            return db.one("SELECT * FROM bank_accounts WHERE deposit_id = ?", (d["id"],))

    # ---- the full journey
    def test_full_deposit_lifecycle(self):
        mgr = self.client("manager@a.test")
        r = self.create(mgr)
        self.assertEqual(r.status_code, 302)
        d = self.deposit()
        self.assertEqual(d["status"], S.INVITED)

        tenant = self.app.test_client()
        link = self.invite_link()
        page = tenant.get(link)
        self.assertIn("Org A", page.get_data(as_text=True))
        r = self.accept(tenant, link)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.deposit()["status"], S.ID_PENDING)
        # invite is single use
        self.assertEqual(self.app.test_client().get(link).status_code, 410)

        token = self.csrf(tenant, f"/wallet/borg/{d['pid']}")
        tenant.post(f"/wallet/borg/{d['pid']}/identiteit", data={"full_name": "Tess Huurder", "birth_date": "1995-01-01", "csrf_token": token})
        self.assertEqual(self.deposit()["status"], S.AWAITING_PAYMENT)
        acct = self.account(d)
        self.assertTrue(valid_iban(acct["iban"]))
        sec = self.deposit()
        self.assertEqual((sec["security_type"], sec["custodian"], sec["beneficiary"], sec["legal_lock_status"]),
                         ("bank_deposit", "Sandbox-partnerbank", "Org A", "none"))

        anon = self.app.test_client()
        r = self.webhook(anon, "deposit.received", {"event_id": "e1", "external_id": acct["external_id"], "amount_cents": 200000, "ref": "r1"})
        self.assertEqual(r.json["result"], "processed")
        self.assertEqual(self.deposit()["status"], S.PAYMENT_RECEIVED)
        r = self.webhook(anon, "deposit.received", {"event_id": "e1", "external_id": acct["external_id"], "amount_cents": 200000, "ref": "r1"})
        self.assertEqual(r.json["result"], "duplicate")
        self.assertEqual(self.account(d)["ledger_balance_cents"], 200000)
        sec = self.deposit()
        self.assertEqual((sec["legal_lock_status"], sec["asset_value_cents"], sec["eligible_value_cents"]), ("requested", 200000, None))
        self.webhook(anon, "account.blocked", {"event_id": "e2", "external_id": acct["external_id"]})
        self.assertEqual(self.deposit()["status"], S.SECURED)
        from app import services
        sec = self.deposit()
        self.assertEqual((sec["legal_lock_status"], sec["eligible_value_cents"]), ("active", 200000))
        self.assertEqual(services.coverage_bps(sec), 10000)
        html = mgr.get(f"/app/borgen/{d['pid']}").get_data(as_text=True)
        for text in ("Zekerheid", "Bankdeposito bij partnerbank", "Sandbox-partnerbank", "Actief, ten gunste van de verhuurder", "100%"):
            self.assertIn(text, html)

        token = self.csrf(mgr)
        mgr.post(f"/app/borgen/{d['pid']}/vertrek", data={"move_out_date": local_today().isoformat(), "csrf_token": token})
        self.assertEqual(self.deposit()["status"], S.MOVE_OUT)
        mgr.post(f"/app/borgen/{d['pid']}/afrekening-opslaan", data={"cat_0": "damage", "desc_0": "Gat in de muur", "amount_0": "150,00", "csrf_token": token})
        mgr.post(f"/app/borgen/{d['pid']}/afrekening-voorstellen", data={"csrf_token": token})
        self.assertEqual(self.deposit()["status"], S.SETTLEMENT_PROPOSED)

        token = self.csrf(tenant, f"/wallet/borg/{d['pid']}")
        tenant.post(f"/wallet/borg/{d['pid']}/akkoord", data={"csrf_token": token})
        self.assertEqual(self.deposit()["status"], S.AGREED)

        # A manager may not start a payout; finance may.
        self.assertEqual(mgr.post(f"/app/borgen/{d['pid']}/uitbetalen", data={"csrf_token": self.csrf(mgr)}).status_code, 403)
        fin = self.client("finance@a.test")
        fin.post(f"/app/borgen/{d['pid']}/uitbetalen", data={"csrf_token": self.csrf(fin)})
        self.assertEqual(self.deposit()["status"], S.PAYOUT_PENDING)
        with self.app.app_context():
            ev = db.one("SELECT data_json FROM deposit_events WHERE deposit_id = ? AND to_status = ?", (d["id"], S.PAYOUT_PENDING))
        self.assertEqual(json.loads(ev["data_json"]), {"huurder": 185000, "verhuurder": 15000})
        # 0.3.0: the bank reports what it actually paid; it must match the release instruction.
        self.webhook(anon, "payout.completed", {"event_id": "e3", "external_id": acct["external_id"], "tenant_cents": 185000,
                                                "landlord_cents": 15000, "ref": "p1"})
        self.assertEqual(self.deposit()["status"], S.CLOSED)
        sec = self.deposit()
        self.assertEqual((sec["legal_lock_status"], sec["asset_value_cents"], sec["eligible_value_cents"]), ("released", 0, 0))

    def test_dispute_needs_document_and_never_auto_decides(self):
        mgr = self.client("admin@a.test")
        self.create(mgr, holding="external", external_iban="NL91ABNA0417164300")
        d = self.deposit()
        tenant = self.app.test_client()
        link = self.invite_link()
        self.accept(tenant, link)
        self.assertEqual(self.deposit()["status"], S.AWAITING_PAYMENT)
        token = self.csrf(mgr)
        mgr.post(f"/app/borgen/{d['pid']}/ontvangst", data={"csrf_token": token})
        self.assertEqual(self.deposit()["status"], S.SECURED)
        sec = self.deposit()
        # 0.3.0: a confirmation by the manager is a declaration; it does not count as eligible security.
        self.assertEqual((sec["security_type"], sec["custodian"], sec["legal_lock_status"], sec["asset_value_cents"], sec["eligible_value_cents"],
                          sec["evidence_level"]), ("external_account", None, "none", 200000, None, "declared"))
        mgr.post(f"/app/borgen/{d['pid']}/vertrek", data={"move_out_date": local_today().isoformat(), "csrf_token": token})
        mgr.post(f"/app/borgen/{d['pid']}/afrekening-opslaan", data={"cat_0": "damage", "desc_0": "Schilderwerk", "amount_0": "500", "csrf_token": token})
        mgr.post(f"/app/borgen/{d['pid']}/afrekening-voorstellen", data={"csrf_token": token})
        t = self.csrf(tenant, f"/wallet/borg/{d['pid']}")
        tenant.post(f"/wallet/borg/{d['pid']}/betwisten", data={"reason": "Dit was er al bij de start van de huur.", "csrf_token": t})
        self.assertEqual(self.deposit()["status"], S.DISPUTED)
        r = mgr.post(f"/app/borgen/{d['pid']}/geschil-afsluiten", data={"kind": "agreement", "landlord_amount": "200", "csrf_token": token}, follow_redirects=True)
        self.assertIn("Voeg het getekende akkoord", r.get_data(as_text=True))
        self.assertEqual(self.deposit()["status"], S.DISPUTED)
        pdf = io.BytesIO(b"%PDF-1.4 test agreement")
        mgr.post(f"/app/borgen/{d['pid']}/documenten", data={"kind": "agreement", "file": (pdf, "akkoord.pdf"), "csrf_token": token},
                 content_type="multipart/form-data")
        with self.app.app_context():
            doc_id = db.scalar("SELECT id FROM documents WHERE deposit_id = ?", (d["id"],))
        mgr.post(f"/app/borgen/{d['pid']}/geschil-afsluiten", data={"kind": "agreement", "landlord_amount": "200", "document_id": doc_id, "csrf_token": token})
        self.assertEqual(self.deposit()["status"], S.AGREED)

    # ---- security boundaries
    def test_csrf_required(self):
        mgr = self.client("manager@a.test")
        r = mgr.post("/app/borgen/nieuw", data={"address": "x"})
        self.assertEqual(r.status_code, 400)

    def test_organisation_isolation(self):
        a = self.client("admin@a.test")
        self.create(a)
        d = self.deposit()
        b = self.client("admin@b.test")
        self.assertEqual(b.get(f"/app/borgen/{d['pid']}").status_code, 404)
        self.assertEqual(b.post(f"/app/borgen/{d['pid']}/annuleren", data={"csrf_token": self.csrf(b)}).status_code, 404)
        self.assertNotIn(d["reference"], b.get("/app/borgen?filter=alle").get_data(as_text=True))

    def test_viewer_cannot_write(self):
        v = self.client("viewer@a.test")
        self.assertEqual(v.get("/app/borgen/nieuw").status_code, 403)
        self.assertEqual(v.post("/app/team", data={"email": "x@y.test", "role": "admin", "csrf_token": self.csrf(v)}).status_code, 403)

    def test_tenant_sees_only_own_deposit(self):
        a = self.client("admin@a.test")
        self.create(a)
        tenant = self.app.test_client()
        self.accept(tenant, self.invite_link())
        self.create(a, tenant_email="other@huurder.test", tenant_name="Ander", address="Anderstraat 2")
        other = self.deposit()
        self.assertEqual(tenant.get(f"/wallet/borg/{other['pid']}").status_code, 404)
        self.assertEqual(tenant.get("/app").status_code, 302)

    def test_login_lockout(self):
        c = self.app.test_client()
        for _ in range(5):
            c.post("/login", data={"email": "admin@a.test", "password": "wrong-password-1", "csrf_token": self.anon(c)})
        r = c.post("/login", data={"email": "admin@a.test", "password": PW, "csrf_token": self.anon(c)})
        self.assertEqual(r.status_code, 200)
        self.assertIn("Te veel mislukte pogingen", r.get_data(as_text=True))

    def test_upload_rejects_wrong_type(self):
        a = self.client("admin@a.test")
        self.create(a)
        d = self.deposit()
        r = a.post(f"/app/borgen/{d['pid']}/documenten", data={"kind": "photo", "file": (io.BytesIO(b"<script>alert(1)</script>"), "x.pdf"),
                                                               "csrf_token": self.csrf(a)}, content_type="multipart/form-data", follow_redirects=True)
        self.assertIn("Alleen PDF, JPG en PNG", r.get_data(as_text=True))

    def test_password_reset(self):
        c = self.app.test_client()
        c.post("/wachtwoord-vergeten", data={"email": "viewer@a.test", "csrf_token": self.anon(c, "/wachtwoord-vergeten")})
        r = c.post("/wachtwoord-vergeten", data={"email": "nobody@a.test", "csrf_token": self.anon(c, "/wachtwoord-vergeten")})
        self.assertIn("Als dit adres bij ons bekend is", r.get_data(as_text=True))
        with self.app.app_context():
            body = db.scalar("SELECT body_text FROM outbox_emails WHERE to_email = 'viewer@a.test'")
            self.assertEqual(db.scalar("SELECT COUNT(*) FROM outbox_emails WHERE to_email = 'nobody@a.test'"), 0)
        path = re.search(r"http://localhost(/wachtwoord/[\w-]+)", body).group(1)
        n = self.app.test_client()
        r = n.post(path, data={"password": "Nieuw-Wachtwoord-2026", "csrf_token": self.anon(n, path)})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.app.test_client().get(path).status_code, 410)

    def test_anonymous_csrf_is_per_browser(self):
        a, b = self.app.test_client(), self.app.test_client()
        self.assertNotEqual(self.anon(a), self.anon(b))
        r = b.post("/login", data={"email": "admin@a.test", "password": PW, "csrf_token": self.anon(a)})
        self.assertEqual(r.status_code, 400)

    def test_webhook_signature(self):
        body = json.dumps({"type": "account.blocked", "data": {"event_id": "x"}}).encode()
        r = self.app.test_client().post("/webhooks/bank/sandbox", data=body, headers={"X-Depiqo-Signature": "bad"})
        self.assertEqual(r.status_code, 401)

    def test_max_deposit_enforced(self):
        a = self.client("admin@a.test")
        r = self.create(a, amount="2.500,00", send_invite="")
        self.assertIn("maximaal 2 maanden", r.get_data(as_text=True))

    def test_bank_holding_cannot_be_confirmed_by_staff(self):
        a = self.client("admin@a.test")
        self.create(a)
        d = self.deposit()
        tenant = self.app.test_client()
        self.accept(tenant, self.invite_link())
        r = a.post(f"/app/borgen/{d['pid']}/ontvangst", data={"csrf_token": self.csrf(a)}, follow_redirects=True)
        self.assertIn("bevestigt de bank", r.get_data(as_text=True))
        self.assertNotEqual(self.deposit()["status"], S.SECURED)

    def test_security_headers(self):
        r = self.app.test_client().get("/login")
        self.assertIn("default-src 'self'", r.headers["Content-Security-Policy"])
        self.assertEqual(r.headers["X-Frame-Options"], "DENY")

    def test_billing_counts_only_activated(self):
        a = self.client("admin@a.test")
        self.create(a, send_invite="")  # concept: not billed
        self.create(a, tenant_email="b@huurder.test", address="B 1")  # invited: billed
        with self.app.app_context():
            org = db.one("SELECT * FROM organizations WHERE id = ?", (self.org,))
            est = billing.estimate(org, local_today().strftime("%Y-%m"))
        self.assertEqual(est["counts"]["depiqo"], 1)
        self.assertEqual(est["new"], 1)
        self.assertEqual(est["subtotal"], 9900 + 500)  # Essential base plus one new dossier

    # ---- regression tests for the security review of 19 October 2026
    def _to_awaiting_payment(self):
        mgr = self.client("admin@a.test")
        self.create(mgr)
        d = self.deposit()
        tenant = self.app.test_client()
        link = self.invite_link()
        self.accept(tenant, link)
        tenant.post(f"/wallet/borg/{d['pid']}/identiteit",
                    data={"full_name": "Tess Huurder", "birth_date": "1995-01-01", "csrf_token": self.csrf(tenant, f"/wallet/borg/{d['pid']}")})
        self.assertEqual(self.deposit()["status"], S.AWAITING_PAYMENT)
        return mgr, d

    def test_viewer_cannot_simulate_bank(self):
        _, d = self._to_awaiting_payment()
        v = self.client("viewer@a.test")
        r = v.post(f"/app/borgen/{d['pid']}/sandbox/storting", data={"csrf_token": self.csrf(v)})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.deposit()["status"], S.AWAITING_PAYMENT)

    def test_mailbox_is_staff_only(self):
        r = self.app.test_client().get("/admin/postvak")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])
        self.assertIn(self.client("admin@a.test").get("/admin/mail").status_code, (403, 404))

    def test_login_next_is_local_only(self):
        from app.views.auth import safe_next
        for bad in ("//evil.example", "/\t/evil.example", "/\\evil.example", "https://evil.example", "/\n/evil.example", " /x"):
            self.assertIsNone(safe_next(bad), bad)
        self.assertEqual(safe_next("/app/borgen?filter=alle"), "/app/borgen?filter=alle")
        c = self.app.test_client()
        r = c.post("/login?next=/%09/evil.example", data={"email": "admin@a.test", "password": PW, "csrf_token": self.anon(c)})
        self.assertNotIn("evil", r.headers["Location"])

    def test_reset_requests_do_not_lock_login(self):
        c = self.app.test_client()
        for _ in range(6):
            c.post("/wachtwoord-vergeten", data={"email": "admin@a.test", "csrf_token": self.anon(c, "/wachtwoord-vergeten")})
        self.client("admin@a.test")  # asserts a successful login

    def test_reset_invalidates_other_links(self):
        c = self.app.test_client()
        for _ in range(2):
            c.post("/wachtwoord-vergeten", data={"email": "viewer@a.test", "csrf_token": self.anon(c, "/wachtwoord-vergeten")})
        with self.app.app_context():
            bodies = [r[0] for r in db.all_("SELECT body_text FROM outbox_emails WHERE to_email = 'viewer@a.test' ORDER BY id")]
        first, second = (re.search(r"http://localhost(/wachtwoord/[\w-]+)", b).group(1) for b in bodies)
        n = self.app.test_client()
        n.post(second, data={"password": "Nieuw-Wachtwoord-2026", "csrf_token": self.anon(n, second)})
        self.assertEqual(self.app.test_client().get(first).status_code, 410)

    def test_invoice_period_validated(self):
        with self.app.app_context():
            org = db.one("SELECT * FROM organizations WHERE id = ?", (self.org,))
            for bad in (" 2026-09", "2026-+9", "1999-01", "2026-13", "2026-9"):
                self.assertFalse(billing.valid_period(org, bad), bad)
                with self.assertRaises(ValueError):
                    billing.issue_invoice(org, bad)

    def test_vat_rounds_half_up(self):
        self.assertEqual(billing.vat_cents(4850, 2100), 1019)
        self.assertEqual(billing.vat_cents(4900, 2100), 1029)

    def test_origin_must_match_exactly(self):
        c = self.client("admin@a.test")
        r = c.post("/app/instellingen", data={"name": "X", "csrf_token": self.csrf(c)}, headers={"Origin": "http://localhost.evil.com"})
        self.assertEqual(r.status_code, 400)

    def test_legal_hold_catches_up_with_bank(self):
        mgr, d = self._to_awaiting_payment()
        acct = self.account(d)
        mgr.post(f"/app/borgen/{d['pid']}/blokkade", data={"reason": "Beslag", "csrf_token": self.csrf(mgr)})
        self.assertEqual(self.deposit()["status"], S.LEGAL_HOLD)
        anon = self.app.test_client()
        self.webhook(anon, "deposit.received", {"event_id": "h1", "external_id": acct["external_id"], "amount_cents": 200000, "ref": "r"})
        self.webhook(anon, "account.blocked", {"event_id": "h2", "external_id": acct["external_id"]})
        self.assertEqual(self.deposit()["status"], S.LEGAL_HOLD)
        mgr.post(f"/app/borgen/{d['pid']}/blokkade-opheffen", data={"csrf_token": self.csrf(mgr)})
        self.assertEqual(self.deposit()["status"], S.SECURED)

    def test_bank_event_amount_and_payout_guards(self):
        _, d = self._to_awaiting_payment()
        acct = self.account(d)
        anon = self.app.test_client()
        for amount in (-5, 12.5, "100", 0):
            r = self.webhook(anon, "deposit.received", {"event_id": f"x{amount}", "external_id": acct["external_id"], "amount_cents": amount, "ref": "r"})
            self.assertEqual(r.status_code, 422, amount)
        r = self.webhook(anon, "payout.completed", {"event_id": "p0", "external_id": acct["external_id"]})
        self.assertEqual(r.json["result"], "ignored")
        self.assertEqual(self.account(d)["status"], "open")

    def test_viewer_does_not_see_costs(self):
        html = self.client("viewer@a.test").get("/app").get_data(as_text=True)
        self.assertNotIn("Kosten deze maand", html)
        self.assertIn("Kosten deze maand", self.client("admin@a.test").get("/app").get_data(as_text=True))

    # ---- pricing plans and security model (0.2.0)
    def _org(self, org_id=None):
        with self.app.app_context():
            return db.one("SELECT * FROM organizations WHERE id = ?", (org_id or self.org,))

    def test_new_dossiers_counted_per_month(self):
        from app.util import add_months, today
        a = self.client("admin@a.test")
        self.create(a, tenant_email="new@huurder.test", address="Nieuw 1")  # invited this month: active and new
        self.create(a, tenant_email="gone@huurder.test", address="Weg 1")
        gone = self.deposit()
        a.post(f"/app/borgen/{gone['pid']}/annuleren", data={"csrf_token": self.csrf(a)})  # cancelled: never counted
        self.create(a, tenant_email="old@huurder.test", address="Oud 1")
        old = self.deposit()
        last = add_months(today().replace(day=1), -1)
        with self.app.app_context():
            db.run("UPDATE deposits SET activated_at = ? WHERE id = ?", (f"{last.isoformat()}T09:00:00+00:00", old["id"]))
            est = billing.estimate(self._org(), today().strftime("%Y-%m"))
            prev = billing.estimate(self._org(), last.strftime("%Y-%m"))
        self.assertEqual(est["counts"]["depiqo"], 2)  # new one and last month's one
        self.assertEqual(est["new"], 1)
        self.assertEqual(est["subtotal"], 9900 + 500)
        self.assertEqual((prev["counts"]["depiqo"], prev["new"]), (1, 1))

    def test_pilot_estimate_is_zero(self):
        from app.util import today
        a = self.client("admin@a.test")
        self.create(a)
        with self.app.app_context():
            db.run("UPDATE organizations SET pilot_until = '2099-01-01' WHERE id = ?", (self.org,))
            est = billing.estimate(self._org(), today().strftime("%Y-%m"))
        self.assertTrue(est["pilot"])
        self.assertEqual((est["subtotal"], est["vat"], est["total"]), (0, 0, 0))
        self.assertEqual(est["lines"][-1]["kind"], "pilot")

    def test_enterprise_estimate_uses_overrides(self):
        from app.util import today
        a = self.client("admin@a.test")
        self.create(a)
        with self.app.app_context():
            db.run("UPDATE organizations SET plan = 'enterprise', ent_base_cents = 50000, ent_included = 0, ent_new_dossier_cents = 0 WHERE id = ?",
                   (self.org,))
            est = billing.estimate(self._org(), today().strftime("%Y-%m"))
        self.assertEqual(est["subtotal"], 50000 + 25)  # Depiqo extra falls back to Professional (€ 0,25)

    def test_plan_switch_permissions(self):
        for email in ("viewer@a.test", "manager@a.test", "finance@a.test"):
            c = self.client(email)
            r = c.post("/app/facturatie/plan", data={"plan": "professional", "csrf_token": self.csrf(c)})
            self.assertEqual(r.status_code, 403, email)
        self.assertEqual(self._org()["plan"], "essential")
        a = self.client("admin@a.test")
        a.post("/app/facturatie/plan", data={"plan": "professional", "csrf_token": self.csrf(a)})
        self.assertEqual(self._org()["plan"], "professional")
        with self.app.app_context():
            self.assertEqual(db.scalar("SELECT COUNT(*) FROM audit_log WHERE action = 'billing.plan_changed' AND org_id = ?", (self.org,)), 1)
        r = a.post("/app/facturatie/plan", data={"plan": "enterprise", "csrf_token": self.csrf(a)}, follow_redirects=True)
        self.assertIn("Enterprise is op aanvraag", r.get_data(as_text=True))
        self.assertEqual(self._org()["plan"], "professional")
        # The staff route is not reachable for an organisation admin.
        r = a.post(f"/admin/organisaties/{self.org}/plan", data={"plan": "enterprise", "csrf_token": self.csrf(a)})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(self._org()["plan"], "professional")
        html = a.get("/app/facturatie").get_data(as_text=True)
        self.assertIn("Huidig plan", html)
        self.assertIn("Op aanvraag", html)

    def test_staff_sets_enterprise(self):
        st = self.client("staff@depiqo.test")
        token = self.csrf(st, "/admin")
        r = st.post(f"/admin/organisaties/{self.org}/plan", data={"plan": "enterprise", "base_cents": "750,00", "included": "1500",
                                                                  "extra_external_cents": "0,30", "extra_depiqo_cents": "0,15",
                                                                  "new_dossier_cents": "2", "csrf_token": token})
        self.assertEqual(r.status_code, 302)
        org = self._org()
        self.assertEqual((org["plan"], org["ent_base_cents"], org["ent_included"], org["ent_extra_external_cents"],
                          org["ent_extra_depiqo_cents"], org["ent_new_dossier_cents"]), ("enterprise", 75000, 1500, 30, 15, 200))
        self.assertIn("Enterprise", st.get("/admin").get_data(as_text=True))
        # An enterprise organisation cannot switch itself back.
        a = self.client("admin@a.test")
        a.post("/app/facturatie/plan", data={"plan": "essential", "csrf_token": self.csrf(a)})
        self.assertEqual(self._org()["plan"], "enterprise")
        # Back to a fixed plan clears the overrides; incomplete enterprise numbers are refused.
        st.post(f"/admin/organisaties/{self.org}/plan", data={"plan": "professional", "csrf_token": token})
        self.assertEqual((self._org()["plan"], self._org()["ent_base_cents"]), ("professional", None))
        st.post(f"/admin/organisaties/{self.org}/plan", data={"plan": "enterprise", "base_cents": "abc", "csrf_token": token})
        self.assertEqual(self._org()["plan"], "professional")

    def test_interest_raises_collateral_value(self):
        from app import services
        _, d = self._to_awaiting_payment()
        acct = self.account(d)
        anon = self.app.test_client()
        self.webhook(anon, "deposit.received", {"event_id": "i1", "external_id": acct["external_id"], "amount_cents": 200000, "ref": "r"})
        self.webhook(anon, "account.blocked", {"event_id": "i2", "external_id": acct["external_id"]})
        self.webhook(anon, "interest.credited", {"event_id": "i3", "external_id": acct["external_id"], "amount_cents": 3000, "ref": "int"})
        sec = self.deposit()
        self.assertEqual((sec["asset_value_cents"], sec["eligible_value_cents"]), (203000, 203000))
        self.assertEqual(services.coverage_bps(sec), 10150)
        self.assertIsNone(services.coverage_bps({"eligible_value_cents": None, "amount_cents": 100}))

    def test_migration_backfills_security_model(self):
        import glob
        src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations")
        old_dir = os.path.join(self.tmp, "old-migrations")
        os.makedirs(old_dir)
        for f in sorted(glob.glob(os.path.join(src, "*.sql"))):
            if os.path.basename(f)[:3] in ("001", "002"):  # the schema as it was before 003
                shutil.copy(f, old_dir)
        path = os.path.join(self.tmp, "old.sqlite3")
        db.migrate(path, old_dir)
        conn = db.connect(path)
        conn.execute("INSERT INTO organizations (id, name, created_at) VALUES (1, 'Oud BV', '2026-01-01')")
        conn.execute("INSERT INTO properties (id, org_id, address, postcode, city, region, created_at) VALUES (1, 1, 'A 1', '1000 AA', 'X', 'NL', '2026-01-01')")
        conn.execute("INSERT INTO tenants (id, org_id, name, email, created_at) VALUES (1, 1, 'T', 't@t.test', '2026-01-01')")
        for i, (holding, status) in enumerate((("external", "secured"), ("depiqo", "disputed"), ("depiqo", "closed"), ("depiqo", "invited")), 1):
            conn.execute("INSERT INTO deposits (id, pid, reference, org_id, property_id, tenant_id, region, holding, rent_cents, amount_cents, status, "
                         "lease_start, rule_version, created_at, updated_at, secured_at) VALUES (?, ?, ?, 1, 1, 1, 'NL', ?, 100000, 200000, ?, "
                         "'2026-01-01', 'x', '2026-01-01', '2026-01-01', ?)",
                         (i, f"p{i}", f"R{i}", holding, status, None if status == "invited" else "2026-01-02"))
        for dep_id, st, bal in ((2, "blocked", 201000), (3, "closed", 0)):
            conn.execute("INSERT INTO bank_accounts (deposit_id, provider, external_id, iban, holder_name, status, ledger_balance_cents, opened_at) "
                         "VALUES (?, 'sandbox', ?, 'NL00', 'T', ?, ?, '2026-01-01')", (dep_id, f"x{dep_id}", st, bal))
        conn.close()
        shutil.copy(os.path.join(src, "003_plans_and_security.sql"), old_dir)
        db.migrate(path, old_dir)
        conn = db.connect(path)
        rows = {r["id"]: tuple(r)[1:] for r in conn.execute(
            "SELECT id, security_type, custodian, beneficiary, legal_lock_status, asset_value_cents, eligible_value_cents FROM deposits")}
        self.assertEqual(conn.execute("SELECT plan FROM organizations").fetchone()[0], "essential")
        conn.close()
        self.assertEqual(rows[1], ("external_account", None, "Oud BV", "none", 200000, 200000))
        self.assertEqual(rows[2], ("bank_deposit", "Sandbox-partnerbank", "Oud BV", "active", 201000, 201000))
        self.assertEqual(rows[3], ("bank_deposit", "Sandbox-partnerbank", "Oud BV", "released", 0, 0))
        self.assertEqual(rows[4], ("bank_deposit", None, "Oud BV", "none", None, None))

    def test_csv_guard_covers_tab_and_cr(self):
        from app.views.business import _csv_safe
        for v in ("=1+1", "\t=1", "\r=1", "@x", "-1"):
            self.assertTrue(_csv_safe(v).startswith("'"), repr(v))


if __name__ == "__main__":
    unittest.main()
