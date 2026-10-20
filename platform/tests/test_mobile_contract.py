"""Financial contract between the platform and the tenant app (release validation, step 6).

    python3 -m unittest tests.test_mobile_contract -v

Seeds the full demo (seed.py) into a temporary directory, logs in through /api/v1 as every seeded tenant that
has an account, and checks every deposit the app would show against the platform's own rules, recomputed
here from the database (an independent oracle, not services.balances() itself):

- "Ontvangen" (received) is null unless there is bank evidence (Depiqo account: deposit transactions booked
  from bank events) or document evidence (held elsewhere: evidence level document, verified or legal with the
  matching evidence record), and never for a guarantee or OCMW (no money from the tenant).
- "Bevestigd geblokkeerd" (confirmed blocked) is null unless the active bank partner confirmed the block
  (Depiqo account) or Depiqo staff recorded legal security with a blocking certificate (held elsewhere).
- "Rente" (interest) is always null for deposits held elsewhere, and for a Depiqo account equals the
  interest the bank credited.
- No /api/v1 route releases deposit money: the routes are enumerated from app.url_map and compared with a
  reviewed list, and the API package is checked for calls into the payout and bank-instruction code.

Nothing here changes platform behaviour. A failure means the API shows money that is not proven, or the API
grew a route that needs review.
"""
import ast
import contextlib
import glob
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import db, providers  # noqa: E402
from app import states as S  # noqa: E402

PASSWORD = "Depiqo-demo-2026"
DEVICE = {"name": "Contracttest", "platform": "android", "app_version": "1.0.0"}
API = "/api/v1"
AMOUNT_KEYS = ["obligation", "received", "locked", "interest"]

# Every mutating /api/v1 route, reviewed: none of them releases deposit money. A new route makes this test fail
# on purpose, so that somebody checks it before it ships in the app.
REVIEWED_MUTATING_ROUTES = {
    ("DELETE", "/api/v1/auth/devices/<int:device_id>"),          # ends a device session
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/logout"),
    ("POST", "/api/v1/auth/mfa"),
    ("POST", "/api/v1/auth/refresh"),
    ("POST", "/api/v1/deposits/<pid>/documents"),                 # tenant uploads a photo or document
    ("POST", "/api/v1/deposits/<pid>/identity"),                  # identity check; may ask the bank to OPEN an account
    ("POST", "/api/v1/deposits/<pid>/payout-choice"),             # chooses a destination; the payout itself is started by finance staff
    ("DELETE", "/api/v1/deposits/<pid>/payout-choice"),
    ("POST", "/api/v1/deposits/<pid>/settlement/agree"),          # agreement only; status 'agreed', no bank instruction
    ("POST", "/api/v1/deposits/<pid>/settlement/dispute"),
    ("POST", "/api/v1/devices/push-token"),
    ("POST", "/api/v1/invest/account"),                           # Invest: the tenant's own money, never the deposit
    ("POST", "/api/v1/invest/appropriateness"),
    ("POST", "/api/v1/invest/appropriateness/confirm"),
    ("POST", "/api/v1/invest/fee-change"),
    ("POST", "/api/v1/invest/iban"),
    ("POST", "/api/v1/invest/orders"),
    ("POST", "/api/v1/invest/orders/quote"),
    ("POST", "/api/v1/invest/sandbox/deposit"),
    ("POST", "/api/v1/invest/terms"),
    ("POST", "/api/v1/invest/withdrawals"),                       # from the investment account to the tenant's own IBAN
    ("POST", "/api/v1/invites/<token>/accept"),
    ("PATCH", "/api/v1/me"),
    ("POST", "/api/v1/me/delete-request"),
    ("POST", "/api/v1/me/export"),
    ("POST", "/api/v1/notifications/<int:notification_id>/read"),
    ("POST", "/api/v1/support"),
}

# Code that moves deposit money or talks to the bank about it. The API package must not reach any of it.
FORBIDDEN_CALLS = {
    "services": {"start_payout", "confirm_external_release", "enqueue_instruction", "dispatch_instructions", "_dispatch_one",
                 "retry_instruction", "handle_bank_event", "reprocess_bank_event", "_apply_bank_event", "_apply_payout",
                 "resolve_dispute", "confirm_external_receipt", "set_evidence"},
    "investing": {"dispatch", "_dispatch_one", "on_payout_completed", "_mark_payout_recorded"},
}


class MobileContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="depiqo-contract-")
        keys = ("DEPIQO_ENV", "DEPIQO_SANDBOX", "BANK_PARTNER", "INVEST_PARTNER", "DATABASE_PATH", "STORAGE_DIR", "SECRET_KEY")
        cls._saved_env = {k: os.environ.get(k) for k in keys}
        for k in keys:
            os.environ.pop(k, None)
        os.environ.update(DEPIQO_ENV="development", DEPIQO_SANDBOX="1",
                          DATABASE_PATH=os.path.join(cls.tmp, "depiqo.sqlite3"), STORAGE_DIR=os.path.join(cls.tmp, "storage"))
        import seed  # the real demo seed, unchanged
        saved_argv = sys.argv
        sys.argv = ["seed.py"]
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                seed.main()
        finally:
            sys.argv = saved_argv
        from app import create_app
        cls.app = create_app()

    @classmethod
    def tearDownClass(cls):
        for k, v in cls._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # ------------------------------------------------------------------ helpers

    def call(self, method, path, tok=None, body=None):
        h = {"X-App-Platform": "android", "X-App-Version": "1.0.0"}
        if tok:
            h["Authorization"] = f"Bearer {tok}"
        return self.app.test_client().open(API + path, method=method, json=body, headers=h)

    def login(self, email):
        r = self.call("POST", "/auth/login", body={"email": email, "password": PASSWORD, "device": DEVICE})
        self.assertEqual(r.status_code, 200, f"{email}: {r.get_data(as_text=True)}")
        j = r.get_json()
        self.assertFalse(j.get("mfa_required"), f"{email} has 2FA in the demo seed")
        return j["access_token"]

    def tenant_emails(self):
        with self.app.app_context():
            rows = db.all_("SELECT DISTINCT u.email FROM users u JOIN tenants t ON t.user_id = u.id "
                           "WHERE u.password_hash IS NOT NULL AND u.deleted_at IS NULL AND u.is_staff = 0 ORDER BY u.email")
        return [r["email"] for r in rows]

    def all_deposits(self, tok):
        items, cursor = [], None
        while True:
            r = self.call("GET", "/deposits?limit=100" + (f"&cursor={cursor}" if cursor else ""), tok)
            self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
            j = r.get_json()
            items += j["items"]
            cursor = j["next_cursor"]
            if not cursor:
                return items

    @staticmethod
    def figures(amounts):
        out = {}
        for a in amounts:
            out[a["key"]] = a
        return out

    # ------------------------------------------------------------------ oracle (the platform's rules, recomputed)

    def expected(self, d):
        """What each figure must be (cents or None) for deposit row d, from the database alone."""
        exp = {"obligation": d["amount_cents"]}
        closed = d["status"] in (S.CLOSED, S.CANCELLED)
        if d["holding"] == "depiqo":
            acct = db.one("SELECT * FROM bank_accounts WHERE deposit_id = ?", (d["id"],))
            if not acct:
                return exp | {"received": None, "locked": None, "interest": None}
            received = db.scalar("SELECT COALESCE(SUM(amount_cents), 0) FROM bank_transactions WHERE bank_account_id = ? AND kind = 'deposit'",
                                 (acct["id"],))
            exp["received"] = received or None
            # Block confirmed by the bank: lock active, account blocked, a processed account.blocked event for this account,
            # and the account belongs to the bank partner that is active now.
            from app.partners import bank
            partner = bank()
            active = partner.name if partner.available else ""
            blocked_event = any(
                json.loads(e["payload_json"]).get("external_id") == acct["external_id"]
                for e in db.all_("SELECT payload_json FROM bank_events WHERE type = 'account.blocked' AND processed_at IS NOT NULL "
                                 "AND error IS NULL AND provider = ?", (acct["provider"],)))
            confirmed = d["legal_lock_status"] == "active" and acct["provider"] == active and blocked_event
            exp["locked"] = d["eligible_value_cents"] if confirmed else None
            credited = db.scalar("SELECT COALESCE(SUM(amount_cents), 0) FROM bank_transactions WHERE bank_account_id = ? AND kind = 'interest'",
                                 (acct["id"],))
            exp["interest"] = credited or None
            return exp
        # Held elsewhere
        level = d["evidence_level"]
        records = db.all_("SELECT e.*, doc.kind AS doc_kind FROM deposit_evidence e LEFT JOIN documents doc ON doc.id = e.document_id "
                          "WHERE e.deposit_id = ?", (d["id"],))

        def has_record(lvl, staff=None, doc_kinds=None):
            for r in records:
                if r["level"] != lvl:
                    continue
                if staff is not None and bool(r["set_by_staff"]) != staff:
                    continue
                if doc_kinds is not None and r["doc_kind"] not in doc_kinds:
                    continue
                return True
            return False

        proven = ((level == "document" and has_record("document", doc_kinds=("bankbewijs",)))
                  or (level == "verified" and has_record("verified", staff=True))
                  or (level == "legal" and has_record("legal", staff=True, doc_kinds=("blokkering",))))
        if d["provider_kind"] in providers.NO_TENANT_PAYMENT:
            exp["received"] = None
        else:
            exp["received"] = d["amount_cents"] if proven else None
        legal = level == "legal" and has_record("legal", staff=True, doc_kinds=("blokkering",))
        exp["locked"] = d["amount_cents"] if legal and not closed else None
        exp["interest"] = None
        return exp

    # ------------------------------------------------------------------ tests

    def test_every_seeded_tenant_deposit_follows_the_rules(self):
        emails = self.tenant_emails()
        self.assertGreaterEqual(len(emails), 15, "the demo seed should have many tenant accounts")
        seen = 0
        kinds = set()
        for email in emails:
            tok = self.login(email)
            for item in self.all_deposits(tok):
                with self.subTest(tenant=email, deposit=item["address"]["street"]):
                    detail = self.call("GET", f"/deposits/{item['pid']}", tok)
                    self.assertEqual(detail.status_code, 200)
                    detail = detail.get_json()
                    # list and detail show the same four figures
                    self.assertEqual(item["amounts"], detail["amounts"])
                    self.assertEqual([a["key"] for a in detail["amounts"]], AMOUNT_KEYS)
                    got = self.figures(detail["amounts"])
                    with self.app.app_context():
                        d = db.one("SELECT * FROM deposits WHERE pid = ?", (item["pid"],))
                        exp = self.expected(d)
                    for key in AMOUNT_KEYS:
                        a = got[key]
                        value = a["value"]["cents"] if a["value"] is not None else None
                        self.assertEqual(a["known"], value is not None, f"{key}: 'known' must match the value")
                        if value is not None:
                            self.assertEqual(a["value"]["currency"], "EUR")
                        self.assertEqual(value, exp[key], f"{key} for {d['holding']}/{d['provider_kind']}/{d['evidence_level']}/{d['status']}")
                        self.assertTrue(a["explanation"], f"{key}: every figure carries an explanation")
                    if d["holding"] == "external":
                        self.assertIsNone(got["interest"]["value"], "no interest for deposits held elsewhere")
                    kinds.add((d["holding"], d["provider_kind"], d["evidence_level"]))
                    seen += 1
        self.assertGreaterEqual(seen, 15)
        # The demo covers the interesting cases; if the seed changes, this keeps the test meaningful.
        self.assertIn(("external", "borggarantie", "declared"), kinds)          # guarantee: received must be null
        self.assertTrue(any(k[0] == "depiqo" for k in kinds))
        self.assertTrue(any(k[2] == "legal" for k in kinds))
        self.assertTrue(any(k[2] == "document" for k in kinds))

    def test_guarantee_tenant_mila_has_no_received_money(self):
        tok = self.login("mila@huurder.test")
        items = self.all_deposits(tok)
        self.assertEqual(len(items), 1)
        f = self.figures(items[0]["amounts"])
        self.assertEqual(f["obligation"]["value"], {"cents": 250000, "currency": "EUR"})
        for key in ("received", "locked", "interest"):
            self.assertIsNone(f[key]["value"], key)
            self.assertFalse(f[key]["known"], key)
        self.assertEqual(f["received"]["explanation_key"], "guarantee_no_money")

    def test_no_api_route_releases_deposit_money(self):
        mutating = set()
        for rule in self.app.url_map.iter_rules():
            if not rule.rule.startswith(API + "/"):
                continue
            for m in rule.methods - {"GET", "HEAD", "OPTIONS"}:
                mutating.add((m, rule.rule))
        self.assertEqual(mutating - REVIEWED_MUTATING_ROUTES, set(), "new mutating /api/v1 routes: review them, then add them here")
        self.assertEqual(REVIEWED_MUTATING_ROUTES - mutating, set(), "routes in the reviewed list no longer exist")
        for method, path in mutating:
            low = path.lower()
            for word in ("release", "payout/start", "uitbetal", "vrijgave", "transfer", "bank"):
                self.assertNotIn(word, low, f"{method} {path}")

    def test_api_package_never_calls_payout_or_bank_instruction_code(self):
        offenders = []
        for f in sorted(glob.glob(os.path.join(ROOT, "app", "api", "*.py"))):
            with open(f, encoding="utf-8") as fh:
                src = fh.read()
            tree = ast.parse(src)
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in FORBIDDEN_CALLS:
                    if node.attr in FORBIDDEN_CALLS[node.value.id]:
                        offenders.append(f"{os.path.basename(f)}:{node.lineno} {node.value.id}.{node.attr}")
                if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[-1] in FORBIDDEN_CALLS:
                    for alias in node.names:
                        if alias.name in FORBIDDEN_CALLS[node.module.split(".")[-1]]:
                            offenders.append(f"{os.path.basename(f)}:{node.lineno} import {alias.name}")
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    low = node.value.lower()
                    if "bank_instructions" in low or "bank_transactions" in low:
                        offenders.append(f"{os.path.basename(f)}:{node.lineno} SQL on {low[:60]!r}")
        self.assertEqual(offenders, [])

    def test_agreeing_to_a_settlement_through_the_api_moves_no_money(self):
        """Sanne has a proposed settlement. Agreeing through the app records the agreement and nothing else:
        no release instruction, no payout transaction, status 'agreed' (finance staff start the payout on the web)."""
        tok = self.login("sanne@huurder.test")
        pid = self.all_deposits(tok)[0]["pid"]
        with self.app.app_context():
            d = db.one("SELECT * FROM deposits WHERE pid = ?", (pid,))
            before = (db.scalar("SELECT COUNT(*) FROM bank_instructions WHERE kind = 'release'"),
                      db.scalar("SELECT COUNT(*) FROM bank_transactions WHERE kind IN ('payout_tenant', 'payout_landlord')"))
        self.assertEqual(d["status"], S.SETTLEMENT_PROPOSED)
        r = self.call("POST", f"/deposits/{pid}/settlement/agree", tok, {"confirm": True})
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        with self.app.app_context():
            d = db.one("SELECT * FROM deposits WHERE pid = ?", (pid,))
            after = (db.scalar("SELECT COUNT(*) FROM bank_instructions WHERE kind = 'release'"),
                     db.scalar("SELECT COUNT(*) FROM bank_transactions WHERE kind IN ('payout_tenant', 'payout_landlord')"))
        self.assertEqual(d["status"], S.AGREED)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
