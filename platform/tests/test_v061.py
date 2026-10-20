"""Regression tests for version 0.6.1: the eight findings of the review of the 0.6.0 API, and the reviewer's probes.

    python -m unittest discover -s tests -v
"""
import base64
import io
import json
import os
import sys
import threading
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import apitokens, db, i18n, investing, mfa, util  # noqa: E402
from app import states as S  # noqa: E402
from app.security import attempt_done, attempt_start  # noqa: E402
import test_v060 as T  # noqa: E402  (module import: its classes must not be collected twice)

API = T.API
DEVICE = T.DEVICE
PW = T.PW


def cur(v):
    return base64.urlsafe_b64encode(json.dumps(v).encode()).decode().rstrip("=")


class Base(T.ApiBase):
    def second_tenant(self):
        mgr = self.client("admin@b.test")
        self.create(mgr, tenant_email="otto@huurder.test", tenant_name="Otto Ander", address="Andere straat 9")
        raw = self.invite_link().split("/t/")[1]
        r = self.call("POST", f"/invites/{raw}/accept", json_body={"password": "Lang-genoeg-wachtwoord-1", "confirm_details": True, "device": DEVICE})
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        return r.get_json()

    def with_2fa(self):
        """Tess with an active, funded investment account and 2FA on, logged in with the second step."""
        tok, _, uid, d = self.tess()
        self.active_invest(tok["access_token"])
        secret, codes = self.enable_2fa(uid)
        ch = self.login()
        tok = self.call("POST", "/auth/mfa", json_body={"mfa_token": ch["mfa_token"], "code": mfa.totp(secret)}).get_json()
        with self.app.app_context():
            db.run("UPDATE users SET totp_last_step = NULL WHERE id = ?", (uid,))
            db.run("DELETE FROM login_attempts")
        return tok["access_token"], uid, secret, codes


# ====================================================================== 1. IBAN second factor

class IbanCodeTest(Base):
    def test_wrong_codes_are_rate_limited(self):
        a, uid, secret, _ = self.with_2fa()
        statuses = [self.call("POST", "/invest/iban", a, {"iban": "NL91ABNA0417164300", "code": f"{i:06d}"}).status_code for i in range(7)]
        self.assertEqual(statuses[:5], [409] * 5)
        self.assertEqual(statuses[5:], [429, 429])
        e = self.err(self.call("POST", "/invest/iban", a, {"iban": "NL91ABNA0417164300", "code": mfa.totp(secret)}), 429, "too_many_attempts")
        self.assertIn("15 minuten", e["message"])
        # the counters are the same as for the second login step
        ch = self.login()
        self.err(self.call("POST", "/auth/mfa", json_body={"mfa_token": ch["mfa_token"], "code": mfa.totp(secret)}), 429, "too_many_attempts")

    def test_recovery_code_is_not_consumed(self):
        a, uid, secret, codes = self.with_2fa()
        left = self.call("GET", "/me", a).get_json()["recovery_codes_left"]
        e = self.err(self.call("POST", "/invest/iban", a, {"iban": "NL91ABNA0417164300", "code": codes[0]}), 409, "invest_rejected")
        self.assertIn("6 cijfers", e["message"])
        self.assertEqual(self.call("GET", "/me", a).get_json()["recovery_codes_left"], left)
        with self.app.app_context():
            self.assertFalse(db.scalar("SELECT COUNT(*) FROM login_attempts"))  # a wrong format is not a guess
        r = self.call("POST", "/invest/iban", a, {"iban": "NL91ABNA0417164300", "code": mfa.totp(secret)})
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        self.assertTrue(r.get_json()["usable_now"])

    def test_web_route_uses_the_same_limit(self):
        c, uid, _ = self.funded("500,00")
        secret, _ = self.enable_2fa(uid)
        with self.app.app_context():
            db.run("UPDATE users SET totp_last_step = NULL WHERE id = ?", (uid,))
        for i in range(5):
            self.act(c, "rekening", iban="NL91ABNA0417164300", code=f"{i:06d}")
        html = self.act(c, "rekening", iban="NL91ABNA0417164300", code=mfa.totp(secret)).get_data(as_text=True)
        self.assertIn("Te veel verkeerde codes", html)
        self.assertIsNone(self.acct(uid)["own_iban"])


# ====================================================================== 2. account deletion

class DeletionTest(Base):
    def test_support_copy_reset_attempts_and_invest_records(self):
        tok, _, uid, d = self.tess()
        a = tok["access_token"]
        acct = self.active_invest(a, deposit="25,00")
        self.call("POST", "/invest/iban", a, {"iban": "NL91ABNA0417164300"})  # notice mail (kept as a record)
        q = self.quote(a, side="buy", amount_cents=2500)
        self.assertEqual(self.call("POST", "/support", a, {"category": "account", "message": "Mijn geheime vraag over mijn leven"}).status_code, 201)
        anon = self.app.test_client()
        anon.post("/wachtwoord-vergeten", data={"email": "tess@huurder.test", "csrf_token": self.anon(anon, "/wachtwoord-vergeten")})
        with self.app.app_context():
            db.run("UPDATE deposits SET status = ? WHERE id = ?", (S.CLOSED, d["id"]))
            db.run("DELETE FROM invest_transactions WHERE account_id = ?", (acct["id"],))  # as if everything was withdrawn
        prev = self.call("GET", "/me/delete-request", a).get_json()
        self.assertTrue(prev["possible"], prev)
        r = self.call("POST", "/me/delete-request", a, {"confirm": True, "password": PW})
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        anon_mail = f"verwijderd-{uid}@verwijderd.depiqo.invalid"
        with self.app.app_context():
            support = db.all_("SELECT * FROM outbox_emails WHERE to_email = 'support@getdepiqo.com'")
            self.assertTrue(support)
            for m in support:
                self.assertNotIn("geheime vraag", m["body_text"])
                self.assertNotIn("tess@huurder.test", m["body_text"] + m["subject"])
                self.assertNotIn("Tess", m["body_text"] + m["subject"])
            self.assertFalse(db.scalar("SELECT COUNT(*) FROM login_attempts WHERE email LIKE '%tess@huurder.test%'"))
            self.assertEqual(db.scalar("SELECT COUNT(*) FROM invest_quotes WHERE quote_key = ?", (q["quote_id"],)), 1)  # kept
            notice = db.one("SELECT * FROM outbox_emails WHERE subject = 'Je rekeningnummer voor opnames is gewijzigd'")
            self.assertEqual(notice["to_email"], anon_mail)
            self.assertNotIn("Tess", notice["body_text"])
            self.assertFalse(db.scalar("SELECT COUNT(*) FROM outbox_emails WHERE to_email = 'tess@huurder.test' AND deposit_id IS NULL"))
            self.assertFalse(db.scalar("SELECT COUNT(*) FROM outbox_emails WHERE subject LIKE 'Nieuw wachtwoord%'"))
            self.assertTrue(db.scalar("SELECT COUNT(*) FROM outbox_emails WHERE deposit_id = ?", (d["id"],)))  # the landlord's file
        text = " ".join(r.get_json()["deleted_now"] + r.get_json()["kept_by_law"])
        for phrase in ("supportmailbox", "inlogpogingen", "offertes", "opnamerekening", "wachtwoord te herstellen"):
            self.assertIn(phrase, text)


# ====================================================================== 3. multipart idempotency

class MultipartIdempotencyTest(Base):
    def test_retry_with_same_key_replays(self):
        tok, _, _, d = self.tess()
        a = tok["access_token"]
        out = []
        for _ in range(2):
            r = self.call("POST", f"/deposits/{d['pid']}/documents", a, headers={"Idempotency-Key": "upload-retry-1"},
                          data={"kind": "photo", "file": (io.BytesIO(b"%PDF-1.4 same bytes"), "foto.pdf")}, content_type="multipart/form-data")
            out.append((r.status_code, r.headers.get("Idempotent-Replayed"), r.get_json()["id"]))
        self.assertEqual(out[0][0], 201)
        self.assertEqual(out[1], (201, "true", out[0][2]))
        with self.app.app_context():
            self.assertEqual(db.scalar("SELECT COUNT(*) FROM documents WHERE deposit_id = ? AND uploaded_by_kind = 'tenant'", (d["id"],)), 1)
        r = self.call("POST", f"/deposits/{d['pid']}/documents", a, headers={"Idempotency-Key": "upload-retry-1"},
                      data={"kind": "photo", "file": (io.BytesIO(b"%PDF-1.4 other bytes"), "foto.pdf")}, content_type="multipart/form-data")
        self.err(r, 422, "idempotency_key_reused")


# ====================================================================== 4. cursors and nested JSON

class InputTest(Base):
    def test_huge_or_strange_cursors_are_400(self):
        tok, *_ = self.tess()
        a = tok["access_token"]
        self.active_invest(a)
        for path in ("/notifications", "/deposits", "/support", "/invest/orders", "/invest/withdrawals"):
            for bad in ([10 ** 30], [-1], [True], [[1]], [1.5]):
                self.err(self.call("GET", f"{path}?cursor={cur(bad)}", a), 400, "invalid_cursor")
        self.err(self.call("GET", f"/invest/transactions?cursor={cur(['2026-10-20', 10 ** 30])}", a), 400, "invalid_cursor")
        self.err(self.call("GET", f"/activity?cursor={cur(['2026', 0, 10 ** 30])}", a), 400, "invalid_cursor")
        deep = base64.urlsafe_b64encode(("[" * 5000 + "]" * 5000).encode()).decode()
        self.err(self.call("GET", f"/notifications?cursor={deep}", a), 400, "invalid_cursor")

    def test_deeply_nested_json_is_400(self):
        self.app.config["PROPAGATE_EXCEPTIONS"] = False
        r = self.api().post(API + "/auth/login", data="[" * 100000 + "]" * 100000, content_type="application/json")
        self.err(r, 400, "invalid_json")

    def test_strange_accept_language(self):
        tok, *_ = self.tess()
        r = self.call("GET", "/me", tok["access_token"], headers={"Accept-Language": "en;q=nan, fr;q=inf, de;q=0.9"})
        self.assertEqual((r.status_code, r.headers["Content-Language"]), (200, "nl"))

    def test_bearer_in_query_string_is_ignored(self):
        tok, *_ = self.tess()
        self.err(self.api().get(API + "/me?access_token=" + tok["access_token"]), 401, "token_missing")


# ====================================================================== 5. sandbox endpoint outside the sandbox

class SandboxEndpointTest(Base):
    def test_not_found_before_anything_else(self):
        tok, *_ = self.tess()
        a = tok["access_token"]
        self.app.config["SANDBOX"] = False
        self.err(self.call("POST", "/invest/sandbox/deposit", a, {"amount_cents": 100}), 404, "not_found")
        self.err(self.call("POST", "/invest/sandbox/deposit", a, {"amount_cents": 100}, headers={"Idempotency-Key": "sbx-key-123"}), 404, "not_found")
        self.err(self.call("POST", "/invest/sandbox/deposit", None, {"amount_cents": 100}), 404, "not_found")  # also without login
        self.app.config["SANDBOX"] = True
        self.err(self.call("POST", "/invest/sandbox/deposit", None, {"amount_cents": 100}), 401, "token_missing")


# ====================================================================== 6. local time

class LocalTimeTest(unittest.TestCase):
    def test_winter_and_summer_time(self):
        winter = datetime(2026, 12, 1, 12, 0, tzinfo=timezone.utc)
        summer = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
        self.assertEqual(i18n.datetime_text(winter, "en"), "1 December 2026, 13:00")
        self.assertEqual(i18n.datetime_text(summer, "fr"), "1 juillet 2026, 14:00")
        self.assertEqual(util.datetime_nl(winter), "1 dec 2026, 13:00")
        self.assertEqual(util.datetime_nl(summer), "1 jul 2026, 14:00")


# ====================================================================== 7. push token ownership

class PushTokenOwnerTest(Base):
    TOKEN = "ExponentPushToken[abcdefghij1234567890]"

    def test_token_of_a_live_session_does_not_move(self):
        tok, *_ = self.tess()
        a = tok["access_token"]
        self.assertEqual(self.call("POST", "/devices/push-token", a, {"token": self.TOKEN, "platform": "ios"}).status_code, 201)
        other = self.second_tenant()
        b = other["access_token"]
        self.err(self.call("POST", "/devices/push-token", b, {"token": self.TOKEN, "platform": "ios"}), 409, "push_token_in_use")
        with self.app.app_context():
            self.assertEqual(db.scalar("SELECT user_id FROM push_tokens"), self.uid("tess@huurder.test"))
        # the same user on a new device: fine
        a2 = self.login(device={"name": "Nieuwe telefoon", "platform": "ios", "app_version": "1.0.0"})["access_token"]
        self.assertEqual(self.call("POST", "/devices/push-token", a2, {"token": self.TOKEN, "platform": "ios"}).status_code, 201)
        # after logging out there, the phone may be used by someone else
        self.call("POST", "/auth/logout", a2)
        self.assertEqual(self.call("POST", "/devices/push-token", b, {"token": self.TOKEN, "platform": "ios"}).status_code, 201)
        with self.app.app_context():
            self.assertEqual(db.scalar("SELECT user_id FROM push_tokens"), self.uid("otto@huurder.test"))


# ====================================================================== 8. atomic attempt counting

class AttemptTest(Base):
    def test_reservation_blocks_the_sixth_attempt(self):
        with self.ctx():
            ids = [attempt_start("x@y.test", "1.2.3.4") for _ in range(6)]
            self.assertTrue(all(ids[:5]))
            self.assertIsNone(ids[5])
            self.assertEqual(db.scalar("SELECT COUNT(*) FROM login_attempts WHERE email = 'x@y.test'"), 5)  # the blocked one is not kept
            attempt_done(ids[0], True)
            self.assertIsNotNone(attempt_start("x@y.test", "1.2.3.4"))  # a success frees a place

    def test_challenge_attempts_are_claimed_atomically(self):
        _, _, uid, _ = self.tess()
        secret, _ = self.enable_2fa(uid)
        ch = self.login()
        with self.app.app_context():
            row = db.one("SELECT * FROM api_mfa_challenges ORDER BY id DESC LIMIT 1")
            claims = [apitokens.claim_attempt(row) for _ in range(7)]
        self.assertEqual(claims, [True] * 5 + [False] * 2)
        self.err(self.call("POST", "/auth/mfa", json_body={"mfa_token": ch["mfa_token"], "code": mfa.totp(secret)}), 401, "mfa_token_invalid")

    def test_parallel_wrong_logins_never_exceed_the_limit(self):
        self.tenant()
        results = []

        def go():
            with self.app.test_client() as c:
                r = c.post(API + "/auth/login", json={"email": "tess@huurder.test", "password": "fout-wachtwoord-99", "device": DEVICE})
                results.append(r.status_code)
        threads = [threading.Thread(target=go) for _ in range(8)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        with self.app.app_context():
            self.assertLessEqual(db.scalar("SELECT COUNT(*) FROM login_attempts WHERE email = 'tess@huurder.test' AND ok = 0"), 5)
        self.assertEqual(sorted(results).count(401) + sorted(results).count(429), 8)
        self.err(self.call("POST", "/auth/login", json_body={"email": "tess@huurder.test", "password": PW, "device": DEVICE}), 429, "too_many_attempts")

    def test_web_second_step_uses_the_reservation(self):
        c = self.client("admin@a.test")
        with self.app.app_context():
            uid = self.uid("admin@a.test")
        secret, _ = self.enable_2fa(uid)
        web = self.app.test_client()
        web.post("/login", data={"email": "admin@a.test", "password": PW, "csrf_token": self.anon(web)})
        for _ in range(5):
            web.post("/login/code", data={"code": "000000", "csrf_token": self.anon(web, "/login/code")})
        r = web.post("/login/code", data={"code": mfa.totp(secret), "csrf_token": self.anon(web, "/login/code")})
        self.assertIn("Te veel verkeerde codes", r.get_data(as_text=True))
        self.assertIsNotNone(c)


# ====================================================================== the reviewer's probes as regression tests

class ProbeTest(Base):
    def test_parallel_refresh_gives_at_most_one_new_pair(self):
        tok, *_ = self.tess()
        results = []

        def go():
            with self.app.test_client() as c:
                r = c.post(API + "/auth/refresh", json={"refresh_token": tok["refresh_token"]})
                results.append(r.status_code)
        threads = [threading.Thread(target=go) for _ in range(4)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertLessEqual(results.count(200), 1)

    def test_cross_tenant(self):
        tok, _, uid, d = self.tess()
        b = self.second_tenant()["access_token"]
        pid = d["pid"]
        for path in (f"/deposits/{pid}", f"/deposits/{pid}/events", f"/deposits/{pid}/documents", f"/deposits/{pid}/settlement",
                     f"/deposits/{pid}/release-form", f"/deposits/{pid}/payout-choice"):
            self.assertEqual(self.call("GET", path, b).status_code, 404, path)
        r = self.call("POST", f"/deposits/{pid}/documents", b, data={"kind": "photo", "file": (io.BytesIO(b"%PDF-1.4 x"), "x.pdf")},
                      content_type="multipart/form-data")
        self.assertEqual(r.status_code, 404)
        with self.app.app_context():
            nid = db.scalar("SELECT id FROM notifications WHERE user_id = ? LIMIT 1", (uid,))
        self.assertEqual(self.call("POST", f"/notifications/{nid}/read", b).status_code, 404)
        self.assertEqual(self.call("POST", "/support", b, {"category": "deposit", "message": "Vraag over borg van ander", "deposit_pid": pid}).status_code, 422)
        exp = self.call("POST", "/me/export", b).get_data(as_text=True)
        self.assertNotIn(pid, exp)
        self.assertNotIn("tess@huurder.test", exp)

    def test_quote_is_bound_to_user_and_body_fields_are_ignored(self):
        tok, *_ = self.tess()
        a = tok["access_token"]
        self.active_invest(a)
        q = self.quote(a, side="buy", amount_cents=5000)
        other = self.second_tenant()
        r = self.call("POST", "/invest/orders", other["access_token"], {"quote_id": q["quote_id"], "risk_acknowledged": True},
                      headers={"Idempotency-Key": "other-user-1"})
        self.assertIn(r.status_code, (404, 409))
        body = {"quote_id": q["quote_id"], "risk_acknowledged": True, "amount_cents": 40000, "side": "sell"}
        r = self.call("POST", "/invest/orders", a, body, headers={"Idempotency-Key": "order-key-1"})
        self.assertEqual((r.get_json()["order"]["amount"]["cents"], r.get_json()["order"]["side"]), (5000, "buy"))
        self.err(self.call("POST", "/invest/orders", a, {"quote_id": q["quote_id"], "risk_acknowledged": True},
                           headers={"Idempotency-Key": "order-key-2"}), 409, "quote_used")
        self.err(self.call("POST", "/invest/orders", a, {"quote_id": "q_x", "risk_acknowledged": True},
                           headers={"Idempotency-Key": "order-key-1"}), 422, "idempotency_key_reused")
        self.assertEqual(self.call("POST", "/invest/orders", a, body, headers={"Idempotency-Key": "order-key-1"}).headers.get("Idempotent-Replayed"), "true")

    def test_push_payload_has_no_amounts_or_names(self):
        tok, *_ = self.tess()
        a = tok["access_token"]
        self.call("POST", "/devices/push-token", a, {"token": "ExponentPushToken[abcdefghijklmnop]", "platform": "ios"})
        self.active_invest(a)
        q = self.quote(a, side="buy", amount_cents=5000)
        self.call("POST", "/invest/orders", a, {"quote_id": q["quote_id"], "risk_acknowledged": True}, headers={"Idempotency-Key": "push-ord-1"})
        self.day()
        with self.app.app_context():
            rows = db.all_("SELECT title, body, data_json FROM push_messages")
        self.assertTrue(rows)
        for r in rows:
            self.assertNotRegex(r["title"] + r["body"] + r["data_json"], r"\d+[,.]\d\d|€|Tess|Teststraat")

    def test_partner_off_in_production(self):
        tok, _, uid, d = self.tess()
        a = tok["access_token"]
        self.active_invest(a)
        q = self.quote(a, side="buy", amount_cents=5000)
        self.app.config.update(ENV_NAME="production", SANDBOX=False)
        for m, p, b, h in (("GET", "/invest", None, None),
                           ("POST", "/invest/orders", {"quote_id": q["quote_id"], "risk_acknowledged": True}, {"Idempotency-Key": "k-prod-1"}),
                           ("POST", "/invest/withdrawals", {"amount_cents": 100}, {"Idempotency-Key": "k-prod-2"}),
                           ("POST", "/invest/iban", {"iban": "NL91ABNA0417164300"}, None), ("GET", "/invest/statements", None, None),
                           ("POST", "/invest/fee-change", {"accept": True}, None), ("GET", f"/deposits/{d['pid']}/payout-choice", None, None)):
            self.err(self.call(m, p, a, b, headers=h), 503, "partner_unavailable")
        self.err(self.call("POST", "/invest/sandbox/deposit", a, {"amount_cents": 100}, headers={"Idempotency-Key": "k-prod-3"}), 404, "not_found")
        self.assertEqual(self.call("GET", f"/deposits/{d['pid']}", a).status_code, 200)
        self.assertEqual(self.call("GET", "/activity", a).status_code, 200)
        self.assertEqual(self.app.test_client().get("/.well-known/assetlinks.json").status_code, 404)


if __name__ == "__main__":
    unittest.main()
