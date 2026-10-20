"""Tests for version 0.6.0: the JSON API for the tenant app (/api/v1), notifications, push outbox, languages,
support, environments and the OpenAPI spec.

    python -m unittest discover -s tests -v
"""
import io
import json
import os
import re
import sys
import unittest
from datetime import timedelta
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.util import today as local_today  # noqa: E402
from app import apitokens, create_app, db, i18n, investing, mfa, notify, services  # noqa: E402
from app import states as S  # noqa: E402
from app.util import now, now_iso, sha256  # noqa: E402
import test_v030 as tv  # noqa: E402
import test_v050 as t5  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PW = tv.PW
DEVICE = {"name": "Testtelefoon", "platform": "ios", "app_version": "1.0.0"}
API = "/api/v1"


class ApiBase(t5.Base):
    # ---- API helpers
    def api(self):
        return self.app.test_client()

    def call(self, method, path, tok=None, json_body=None, headers=None, **kw):
        h = dict(headers or {})
        if tok:
            h["Authorization"] = f"Bearer {tok}"
        c = kw.pop("client", None) or self.api()
        return c.open(API + path, method=method, json=json_body, headers=h, **kw)

    def login(self, email="tess@huurder.test", password=PW, device=None, expect=200):
        r = self.call("POST", "/auth/login", json_body={"email": email, "password": password, "device": device or DEVICE})
        self.assertEqual(r.status_code, expect, r.get_data(as_text=True))
        return r.get_json()

    def tess(self):
        """Tess with a Depiqo deposit awaiting payment, logged in on the API. Returns (tokens, web client, user id, deposit)."""
        c, uid, d = self.tenant()
        return self.login(), c, uid, d

    def err(self, r, status, code):
        self.assertEqual(r.status_code, status, r.get_data(as_text=True))
        body = r.get_json()
        self.assertEqual(body["error"]["code"], code, body)
        self.assertIsInstance(body["error"]["message"], str)
        self.assertIsInstance(body["error"]["fields"], dict)
        return body["error"]

    def enable_2fa(self, uid):
        with self.app.app_context():
            mfa.start_setup(uid)
            user = db.one("SELECT * FROM users WHERE id = ?", (uid,))
            codes = mfa.confirm_setup(user, mfa.totp(user["totp_pending_secret"]))
            db.run("UPDATE users SET totp_last_step = NULL WHERE id = ?", (uid,))
            return db.scalar("SELECT totp_secret FROM users WHERE id = ?", (uid,)), codes

    def active_invest(self, tok, deposit="500,00"):
        """Onboarding through the API, then a sandbox deposit. Returns the account row."""
        self.assertEqual(self.call("POST", "/invest/appropriateness", tok, {"answers": t5.PASSEND}).status_code, 201)
        terms = self.call("GET", "/invest/terms", tok).get_json()
        self.call("POST", "/invest/terms", tok, {"partner_version": terms["partner"]["version"], "depiqo_version": terms["depiqo"]["version"],
                                                 "accept_partner": True, "accept_depiqo": True})
        r = self.call("POST", "/invest/account", tok, {"portfolio": "neutraal"})
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        uid = self.uid("tess@huurder.test")
        acct = self.acct(uid)
        if acct["status"] == "pending":
            with self.ctx():
                investing.activate_sandbox_account(acct["id"])
        r = self.call("POST", "/invest/sandbox/deposit", tok, {"amount_cents": int(deposit.replace(",", "").replace(".", ""))},
                      headers={"Idempotency-Key": "dep-" + sha256(now_iso() + deposit)[:12]})
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        return self.acct(uid)

    def quote(self, tok, **body):
        r = self.call("POST", "/invest/orders/quote", tok, body)
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        return r.get_json()

    def proposed(self):
        """Tess's Depiqo deposit with a proposed settlement of € 150."""
        mgr, d = self.to_secured()
        token = self.csrf(mgr)
        mgr.post(f"/app/borgen/{d['pid']}/vertrek", data={"move_out_date": local_today().isoformat(), "csrf_token": token})
        mgr.post(f"/app/borgen/{d['pid']}/afrekening-opslaan", data={"cat_0": "damage", "desc_0": "Gat in de muur", "amount_0": "150,00", "csrf_token": token})
        mgr.post(f"/app/borgen/{d['pid']}/afrekening-voorstellen", data={"csrf_token": token})
        self.assertEqual(self.row()["status"], S.SETTLEMENT_PROPOSED)
        return mgr, self.row()


# ====================================================================== auth

class AuthTest(ApiBase):
    def test_config_is_public(self):
        r = self.call("GET", "/config")
        self.assertEqual(r.status_code, 200)
        c = r.get_json()
        self.assertEqual(c["minimum_app_version"], {"ios": "1.0.0", "android": "1.0.0"})
        self.assertTrue(c["sandbox"])
        self.assertEqual(c["environment"], "development")
        self.assertEqual(c["banner"], "SANDBOX")
        self.assertEqual(c["languages"], ["nl", "fr", "en"])
        self.assertIn("/wachtwoord-vergeten", c["links"]["password_reset"])
        self.assertEqual(r.headers["Cache-Control"], "no-store")

    def test_login_tokens_and_me(self):
        tok, *_ = self.tess()
        self.assertEqual(tok["token_type"], "Bearer")
        self.assertEqual(tok["expires_in"], 900)
        self.assertFalse(tok["mfa_required"])
        me = self.call("GET", "/me", tok["access_token"]).get_json()
        self.assertEqual((me["email"], me["two_factor_enabled"]), ("tess@huurder.test", False))
        self.assertEqual(me["invest"]["visibility"], "available")
        self.err(self.call("GET", "/me"), 401, "token_missing")
        self.err(self.call("GET", "/me", "nonsense"), 401, "token_invalid")
        with self.app.app_context():  # tokens are stored as hashes only
            self.assertFalse(db.scalar("SELECT COUNT(*) FROM api_access_tokens WHERE token_hash = ?", (tok["access_token"],)))
            self.assertTrue(db.scalar("SELECT COUNT(*) FROM api_access_tokens WHERE token_hash = ?", (sha256(tok["access_token"]),)))
            self.assertTrue(db.scalar("SELECT COUNT(*) FROM api_refresh_tokens WHERE token_hash = ?", (sha256(tok["refresh_token"]),)))
            dev = db.one("SELECT * FROM api_devices WHERE id = ?", (tok["device_id"],))
        self.assertEqual((dev["device_name"], dev["platform"], dev["app_version"]), ("Testtelefoon", "ios", "1.0.0"))

    def test_wrong_password_lockout_shared_with_web(self):
        self.tenant()
        for _ in range(5):
            self.err(self.call("POST", "/auth/login", json_body={"email": "tess@huurder.test", "password": "fout-wachtwoord-12", "device": DEVICE}),
                     401, "invalid_credentials")
        e = self.err(self.call("POST", "/auth/login", json_body={"email": "tess@huurder.test", "password": PW, "device": DEVICE}),
                     429, "too_many_attempts")
        self.assertIn("15 minuten", e["message"])
        web = self.app.test_client()
        r = web.post("/login", data={"email": "tess@huurder.test", "password": PW, "csrf_token": self.anon(web)})
        self.assertIn("Te veel mislukte pogingen", r.get_data(as_text=True))

    def test_staff_and_business_users_refused(self):
        self.err(self.call("POST", "/auth/login", json_body={"email": "staff@depiqo.test", "password": PW, "device": DEVICE}), 403, "staff_not_allowed")
        e = self.err(self.call("POST", "/auth/login", json_body={"email": "admin@a.test", "password": PW, "device": DEVICE}), 403, "not_a_tenant")
        self.assertIn("Depiqo Business", e["message"])
        with self.app.app_context():
            self.assertFalse(db.scalar("SELECT COUNT(*) FROM api_devices"))

    def test_device_fields_validated(self):
        self.tenant()
        r = self.call("POST", "/auth/login", json_body={"email": "tess@huurder.test", "password": PW, "device": {"name": "x", "platform": "web"}})
        e = self.err(r, 422, "validation_failed")
        self.assertIn("device.platform", e["fields"])

    def test_old_app_version_refused(self):
        self.tenant()
        self.app.config["APP_MIN_VERSION_IOS"] = "2.1.0"
        e = self.err(self.call("POST", "/auth/login", json_body={"email": "tess@huurder.test", "password": PW, "device": DEVICE}),
                     426, "app_update_required")
        self.assertEqual(e["fields"]["minimum_version"], "2.1.0")
        self.assertEqual(self.call("GET", "/config", headers={"X-App-Platform": "ios", "X-App-Version": "1.0.0"}).status_code, 200)
        self.err(self.call("GET", "/me", headers={"X-App-Platform": "ios", "X-App-Version": "1.9.9"}), 426, "app_update_required")

    def test_two_factor_with_totp_then_recovery_code(self):
        _, _, uid, _ = self.tess()
        secret, codes = self.enable_2fa(uid)
        first = self.login()
        self.assertTrue(first["mfa_required"])
        self.assertNotIn("access_token", first)
        self.err(self.call("POST", "/auth/mfa", json_body={"mfa_token": first["mfa_token"], "code": "000000"}), 401, "invalid_code")
        r = self.call("POST", "/auth/mfa", json_body={"mfa_token": first["mfa_token"], "code": mfa.totp(secret)})
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        tok = r.get_json()
        self.assertEqual(tok["second_factor"], "totp")
        self.assertEqual(self.call("GET", "/me", tok["access_token"]).status_code, 200)
        self.err(self.call("POST", "/auth/mfa", json_body={"mfa_token": first["mfa_token"], "code": mfa.totp(secret)}), 401, "mfa_token_invalid")
        second = self.login()
        r = self.call("POST", "/auth/mfa", json_body={"mfa_token": second["mfa_token"], "code": codes[0]})
        self.assertEqual(r.get_json()["second_factor"], "recovery")
        self.assertEqual(r.get_json()["recovery_codes_left"], 9)
        with self.app.app_context():
            self.assertTrue(db.scalar("SELECT mfa_at FROM api_devices WHERE id = ?", (tok["device_id"],)))

    def test_mfa_token_expires_and_attempts_are_limited(self):
        _, _, uid, _ = self.tess()
        secret, _ = self.enable_2fa(uid)
        ch = self.login()
        with self.app.app_context():
            db.run("UPDATE api_mfa_challenges SET expires_at = ?", ((now() - timedelta(seconds=1)).isoformat(timespec="seconds"),))
        self.err(self.call("POST", "/auth/mfa", json_body={"mfa_token": ch["mfa_token"], "code": mfa.totp(secret)}), 401, "mfa_token_invalid")
        ch = self.login()
        for _ in range(5):
            self.call("POST", "/auth/mfa", json_body={"mfa_token": ch["mfa_token"], "code": "123456"})
        r = self.call("POST", "/auth/mfa", json_body={"mfa_token": ch["mfa_token"], "code": mfa.totp(secret)})
        self.assertIn(r.status_code, (401, 429))

    def test_refresh_rotates_and_reuse_revokes_device(self):
        tok, *_ = self.tess()
        r = self.call("POST", "/auth/refresh", json_body={"refresh_token": tok["refresh_token"]})
        self.assertEqual(r.status_code, 200)
        new = r.get_json()
        self.assertNotEqual(new["refresh_token"], tok["refresh_token"])
        self.assertEqual(new["device_id"], tok["device_id"])
        self.assertEqual(self.call("GET", "/me", new["access_token"]).status_code, 200)
        # the old refresh token again: someone else holds it, the whole device session ends
        self.err(self.call("POST", "/auth/refresh", json_body={"refresh_token": tok["refresh_token"]}), 401, "refresh_token_reused")
        self.err(self.call("GET", "/me", new["access_token"]), 401, "device_revoked")
        self.err(self.call("POST", "/auth/refresh", json_body={"refresh_token": new["refresh_token"]}), 401, "device_revoked")
        with self.app.app_context():
            self.assertEqual(db.scalar("SELECT revoked_reason FROM api_devices WHERE id = ?", (tok["device_id"],)), "refresh_reuse")
            self.assertTrue(db.scalar("SELECT COUNT(*) FROM audit_log WHERE action = 'api.refresh_reuse' AND org_id IS NULL"))

    def test_expiry_of_access_and_refresh_tokens(self):
        tok, *_ = self.tess()
        past = (now() - timedelta(seconds=1)).isoformat(timespec="seconds")
        with self.app.app_context():
            db.run("UPDATE api_access_tokens SET expires_at = ?", (past,))
        self.err(self.call("GET", "/me", tok["access_token"]), 401, "token_expired")
        with self.app.app_context():
            db.run("UPDATE api_refresh_tokens SET expires_at = ?", (past,))
        self.err(self.call("POST", "/auth/refresh", json_body={"refresh_token": tok["refresh_token"]}), 401, "token_expired")
        self.assertEqual(apitokens.ACCESS_TTL, timedelta(minutes=15))
        self.assertEqual(apitokens.REFRESH_TTL, timedelta(days=30))

    def test_logout_and_devices(self):
        a, *_ = self.tess()
        b = self.login(device={"name": "Tablet", "platform": "android", "app_version": "1.2.0"})
        items = self.call("GET", "/auth/devices", a["access_token"]).get_json()["items"]
        self.assertEqual({d["name"] for d in items}, {"Testtelefoon", "Tablet"})
        self.assertEqual([d["current"] for d in items if d["name"] == "Testtelefoon"], [True])
        self.assertEqual(self.call("DELETE", f"/auth/devices/{b['device_id']}", a["access_token"]).status_code, 204)
        self.err(self.call("GET", "/me", b["access_token"]), 401, "device_revoked")
        self.err(self.call("DELETE", f"/auth/devices/{b['device_id']}", a["access_token"]), 404, "not_found")
        self.assertEqual(self.call("POST", "/auth/logout", a["access_token"]).status_code, 204)
        self.err(self.call("GET", "/me", a["access_token"]), 401, "device_revoked")

    def test_devices_on_web_security_page(self):
        tok, web, *_ = self.tess()
        html = web.get("/account/beveiliging").get_data(as_text=True)
        self.assertIn("Apps en apparaten", html)
        self.assertIn("Testtelefoon", html)
        web.post("/account/beveiliging", data={"action": "revoke_device", "device_id": tok["device_id"],
                                               "csrf_token": self.csrf(web, "/account/beveiliging")})
        self.err(self.call("GET", "/me", tok["access_token"]), 401, "device_revoked")
        other = self.client("admin@a.test")
        r = other.post("/account/beveiliging", data={"action": "revoke_device", "device_id": 999, "csrf_token": self.csrf(other, "/account/beveiliging")})
        self.assertEqual(r.status_code, 404)

    def test_password_reset_and_2fa_change_end_app_sessions(self):
        tok, web, uid, _ = self.tess()
        anon = self.app.test_client()
        anon.post("/wachtwoord-vergeten", data={"email": "tess@huurder.test", "csrf_token": self.anon(anon, "/wachtwoord-vergeten")})
        with self.app.app_context():
            body = db.scalar("SELECT body_text FROM outbox_emails WHERE subject LIKE 'Nieuw wachtwoord%' ORDER BY id DESC LIMIT 1")
        link = re.search(r"http://localhost(/wachtwoord/[\w-]+)", body).group(1)
        anon.post(link, data={"password": "Een-heel-nieuw-wachtwoord-9", "csrf_token": self.anon(anon, link)})
        self.err(self.call("GET", "/me", tok["access_token"]), 401, "device_revoked")
        tok2 = self.login(password="Een-heel-nieuw-wachtwoord-9")
        self.enable_2fa(uid)
        with self.app.test_request_context("/"):
            from flask import g
            g.session = None
            from app.security import end_other_sessions
            end_other_sessions(uid)
        self.err(self.call("GET", "/me", tok2["access_token"]), 401, "device_revoked")

    def test_cookie_only_mutation_refused_and_cookie_never_authenticates(self):
        _, web, _, _ = self.tess()
        r = web.post(API + "/auth/logout")
        self.err(r, 403, "cookie_auth_not_allowed")
        r = web.post(API + "/me/export")
        self.err(r, 403, "cookie_auth_not_allowed")
        self.err(web.get(API + "/me"), 401, "token_missing")

    def test_json_errors_everywhere(self):
        self.err(self.call("GET", "/bestaat-niet"), 404, "not_found")
        self.err(self.call("PUT", "/config"), 405, "method_not_allowed")
        r = self.api().post(API + "/auth/login", data="email=x", content_type="application/x-www-form-urlencoded")
        self.err(r, 415, "unsupported_media_type")
        r = self.api().post(API + "/auth/login", data="{niet json", content_type="application/json")
        self.err(r, 400, "invalid_json")

    def test_new_device_login_notification(self):
        tok, *_ = self.tess()
        items = self.call("GET", "/notifications", tok["access_token"]).get_json()["items"]
        self.assertIn("new_device_login", [n["type"] for n in items])


# ====================================================================== invitations

class InviteTest(ApiBase):
    def test_preview_and_accept_new_tenant(self):
        mgr = self.client("admin@a.test")
        self.create(mgr, tenant_email="nina@huurder.test", tenant_name="Nina Nieuw")
        raw = self.invite_link().split("/t/")[1]
        info = self.call("GET", f"/invites/{raw}").get_json()
        self.assertEqual(info["landlord"]["name"], "Org A")
        self.assertEqual(info["address"]["street"], "Teststraat 1")
        self.assertEqual(info["amount"], {"cents": 200000, "currency": "EUR"})
        self.assertTrue(info["reference"].startswith("DPQ-"))
        self.assertFalse(info["existing_account"])
        self.err(self.call("POST", f"/invites/{raw}/accept", json_body={"password": "Lang-genoeg-wachtwoord-1", "device": DEVICE}),
                 422, "confirm_details_required")
        self.err(self.call("POST", f"/invites/{raw}/accept", json_body={"password": "kort", "confirm_details": True, "device": DEVICE}),
                 422, "weak_password")
        r = self.call("POST", f"/invites/{raw}/accept", json_body={"password": "Lang-genoeg-wachtwoord-1", "confirm_details": True, "device": DEVICE})
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        body = r.get_json()
        self.assertEqual(body["status"], S.ID_PENDING)
        self.assertEqual(self.call("GET", f"/deposits/{body['deposit_pid']}", body["access_token"]).status_code, 200)
        self.err(self.call("GET", f"/invites/{raw}"), 410, "invite_expired")

    def test_existing_tenant_accepts_with_login(self):
        tok, *_ = self.tess()
        mgr = self.client("admin@a.test")
        self.create(mgr, address="Tweede straat 2")
        raw = self.invite_link().split("/t/")[1]
        self.assertTrue(self.call("GET", f"/invites/{raw}").get_json()["existing_account"])
        self.err(self.call("POST", f"/invites/{raw}/accept", json_body={"confirm_details": True}), 409, "login_required")
        r = self.call("POST", f"/invites/{raw}/accept", tok["access_token"], {"confirm_details": True})
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        self.assertEqual(len(self.call("GET", "/deposits", tok["access_token"]).get_json()["items"]), 2)

    def test_business_user_is_sent_to_the_web(self):
        mgr = self.client("admin@a.test")
        self.create(mgr, tenant_email="manager@a.test", tenant_name="Manager")
        raw = self.invite_link().split("/t/")[1]
        e = self.err(self.call("POST", f"/invites/{raw}/accept", json_body={"confirm_details": True}), 409, "use_web")
        self.assertIn(f"/t/{raw}", e["fields"]["url"])


# ====================================================================== deposits

class DepositTest(ApiBase):
    def test_list_and_detail(self):
        tok, _, _, d = self.tess()
        a = tok["access_token"]
        items = self.call("GET", "/deposits", a).get_json()["items"]
        self.assertEqual([i["pid"] for i in items], [d["pid"]])
        x = self.call("GET", f"/deposits/{d['pid']}", a).get_json()
        self.assertEqual((x["status"], x["status_label"], x["display_key"]), ("awaiting_payment", "Stort je borg", "awaiting_payment"))
        self.assertEqual(x["landlord"]["name"], "Org A")
        figs = {f["key"]: f for f in x["amounts"]}
        self.assertEqual(list(figs), ["obligation", "received", "locked", "interest"])
        self.assertEqual(figs["obligation"]["value"], {"cents": 200000, "currency": "EUR"})
        self.assertIsNone(figs["received"]["value"])
        self.assertFalse(figs["received"]["known"])
        self.assertEqual(figs["received"]["explanation_key"], "no_payment_reported")
        self.assertEqual(x["progress"]["current"], "awaiting_payment")
        self.assertEqual([s["state"] for s in x["progress"]["steps"]][:4], ["done", "done", "current", "upcoming"])
        self.assertEqual(x["next_action"]["code"], "pay")
        self.assertTrue(x["payment_instructions"]["iban"])
        self.assertEqual(x["payment_instructions"]["amount"]["cents"], 200000)
        self.assertEqual(x["location"]["kind"], "depiqo_account")
        self.assertTrue(x["location"]["sandbox"])
        self.assertTrue(x["events"])
        self.assertTrue(all(e["type"] in ("status", "payment", "interest") for e in x["events"]))
        self.assertEqual(x["events"][0]["key"], "status_changed")
        self.assertIn("to_status", x["events"][0]["params"])

    def test_payment_events_and_notifications(self):
        tok, _, _, d = self.tess()
        acct = self.account(d)
        anon = self.app.test_client()
        self.webhook(anon, "deposit.received", {"event_id": "p1", "external_id": acct["external_id"], "amount_cents": 200000, "ref": "r"})
        self.webhook(anon, "account.blocked", {"event_id": "p2", "external_id": acct["external_id"]})
        a = tok["access_token"]
        x = self.call("GET", f"/deposits/{d['pid']}", a).get_json()
        self.assertEqual(x["display_key"], "secured_bank_confirmed")
        events = self.call("GET", f"/deposits/{d['pid']}/events?limit=2", a).get_json()
        self.assertEqual(len(events["items"]), 2)
        self.assertTrue(events["next_cursor"])
        more = self.call("GET", f"/deposits/{d['pid']}/events?limit=50&cursor={events['next_cursor']}", a).get_json()
        self.assertFalse(set(e["id"] for e in more["items"]) & set(e["id"] for e in events["items"]))
        types = [n["type"] for n in self.call("GET", "/notifications", a).get_json()["items"]]
        self.assertIn("payment_received", types)
        self.assertIn("deposit_secured", types)
        received = [e for e in self.call("GET", f"/deposits/{d['pid']}/events?limit=50", a).get_json()["items"]
                    if e["params"].get("to_status") == "payment_received"]
        self.assertEqual(received[0]["params"]["amount_cents"], 200000)

    def test_other_tenants_deposit_is_404_everywhere(self):
        tok, *_ = self.tess()
        mgr = self.client("admin@a.test")
        self.create(mgr, tenant_email="ander@huurder.test", tenant_name="Ander", address="Anderstraat 9")
        other = self.row()
        a = tok["access_token"]
        for method, path, body in (("GET", "", None), ("GET", "/documents", None), ("GET", "/documents/1", None), ("GET", "/settlement", None),
                                   ("GET", "/events", None), ("GET", "/release-form", None), ("GET", "/payout-choice", None),
                                   ("POST", "/identity", {"full_name": "X", "birth_date": "1990-01-01"}),
                                   ("POST", "/settlement/agree", {"confirm": True}), ("POST", "/settlement/dispute", {"reason": "Lang genoeg bezwaar hier"}),
                                   ("POST", "/payout-choice", {"confirm": True}), ("DELETE", "/payout-choice", None)):
            self.err(self.call(method, f"/deposits/{other['pid']}{path}", a, body), 404, "not_found")

    def test_identity(self):
        mgr = self.client("admin@a.test")
        self.create(mgr)
        raw = self.invite_link().split("/t/")[1]
        tok = self.call("POST", f"/invites/{raw}/accept", json_body={"password": PW, "confirm_details": True, "device": DEVICE}).get_json()
        pid = tok["deposit_pid"]
        r = self.call("POST", f"/deposits/{pid}/identity", tok["access_token"], {"full_name": "Tess Huurder", "birth_date": "1995-01-01"})
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        self.assertEqual(r.get_json()["result"], "account_open")
        self.assertEqual(r.get_json()["deposit"]["status"], S.AWAITING_PAYMENT)
        self.err(self.call("POST", f"/deposits/{pid}/identity", tok["access_token"], {"full_name": "Tess", "birth_date": "1995-01-01"}),
                 409, "identity_not_possible")

    def test_documents(self):
        tok, _, _, d = self.tess()
        a = tok["access_token"]
        jpeg = b"\xff\xd8\xff\xe0" + b"0" * 2000
        r = self.api().post(f"{API}/deposits/{d['pid']}/documents", headers={"Authorization": f"Bearer {a}"},
                            data={"kind": "photo", "file": (io.BytesIO(jpeg), "camera.jpg")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        doc = r.get_json()
        self.assertEqual((doc["mime"], doc["uploaded_by"], doc["kind"]), ("image/jpeg", "tenant", "photo"))
        listing = self.call("GET", f"/deposits/{d['pid']}/documents", a).get_json()
        self.assertIn(doc["id"], [x["id"] for x in listing["items"]])
        self.assertEqual([k["kind"] for k in listing["upload_kinds"]], ["photo", "inspection", "other"])
        got = self.call("GET", f"/deposits/{d['pid']}/documents/{doc['id']}", a)
        self.assertEqual(got.data, jpeg)
        got.close()
        r = self.api().post(f"{API}/deposits/{d['pid']}/documents", headers={"Authorization": f"Bearer {a}"},
                            data={"kind": "photo", "file": (io.BytesIO(b"MZ\x90\x00 exe"), "virus.jpg")}, content_type="multipart/form-data")
        self.assertIn("PDF, JPG en PNG", self.err(r, 422, "upload_rejected")["fields"]["file"])
        r = self.api().post(f"{API}/deposits/{d['pid']}/documents", headers={"Authorization": f"Bearer {a}"},
                            data={"kind": "court", "file": (io.BytesIO(jpeg), "x.jpg")}, content_type="multipart/form-data")
        self.err(r, 422, "validation_failed")
        r = self.api().post(f"{API}/deposits/{d['pid']}/documents", headers={"Authorization": f"Bearer {a}"},
                            data={"kind": "photo", "file": (io.BytesIO(b"\xff\xd8\xff" + b"0" * (10 * 1024 * 1024)), "groot.jpg")},
                            content_type="multipart/form-data")
        self.assertIn("10 MB", self.err(r, 422, "upload_rejected")["fields"]["file"])
        self.err(self.call("POST", f"/deposits/{d['pid']}/documents", a, {"kind": "photo"}), 415, "unsupported_media_type")
        with self.app.app_context():
            db.run("UPDATE deposits SET status = 'cancelled' WHERE id = ?", (d["id"],))
        r = self.api().post(f"{API}/deposits/{d['pid']}/documents", headers={"Authorization": f"Bearer {a}"},
                            data={"kind": "photo", "file": (io.BytesIO(jpeg), "x.jpg")}, content_type="multipart/form-data")
        self.err(r, 409, "deposit_closed")

    def test_settlement_agree(self):
        mgr, d = self.proposed()
        a = self.login()["access_token"]
        s = self.call("GET", f"/deposits/{d['pid']}/settlement", a).get_json()["settlement"]
        self.assertTrue(s["can_respond"])
        self.assertEqual(s["deductions"]["cents"], 15000)
        self.assertEqual(s["back_to_tenant"]["cents"], 185000)
        self.assertEqual(s["lines"][0]["category"], "damage")
        self.err(self.call("POST", f"/deposits/{d['pid']}/settlement/agree", a, {}), 422, "confirm_required")
        r = self.call("POST", f"/deposits/{d['pid']}/settlement/agree", a, {"confirm": True})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["deposit"]["status"], S.AGREED)
        self.err(self.call("POST", f"/deposits/{d['pid']}/settlement/agree", a, {"confirm": True}), 409, "settlement_not_open")
        self.assertIn("settlement_proposed", [n["type"] for n in self.call("GET", "/notifications", a).get_json()["items"]])

    def test_settlement_dispute_and_outcome(self):
        mgr, d = self.proposed()
        a = self.login()["access_token"]
        self.err(self.call("POST", f"/deposits/{d['pid']}/settlement/dispute", a, {"reason": "Nee"}), 422, "reason_required")
        r = self.call("POST", f"/deposits/{d['pid']}/settlement/dispute", a, {"reason": "De schade was er al bij de start, zie de foto."})
        self.assertEqual(r.get_json()["deposit"]["status"], S.DISPUTED)
        self.assertEqual(r.get_json()["settlement"]["dispute"]["status"], "open")
        doc = self.upload(mgr, d, "agreement")
        with self.ctx():
            services.resolve_dispute(self.row(), self.uid("admin@a.test"), "agreement", 5000, "Samen opgelost", doc)
        n = [x for x in self.call("GET", "/notifications", a).get_json()["items"] if x["type"] == "dispute_resolved"][0]
        self.assertIn("€ 50,00", n["body"])

    def test_release_form_for_external_deposit(self):
        mgr, d = self.external_awaiting()
        mgr.post(f"/app/borgen/{d['pid']}/ontvangst", data={"csrf_token": self.csrf(mgr)})
        a = self.login()["access_token"]
        self.err(self.call("GET", f"/deposits/{d['pid']}/release-form", a), 404, "not_available")
        token = self.csrf(mgr)
        mgr.post(f"/app/borgen/{d['pid']}/vertrek", data={"move_out_date": local_today().isoformat(), "csrf_token": token})
        mgr.post(f"/app/borgen/{d['pid']}/afrekening-opslaan", data={"cat_0": "damage", "desc_0": "Muur", "amount_0": "100,00", "csrf_token": token})
        mgr.post(f"/app/borgen/{d['pid']}/afrekening-voorstellen", data={"csrf_token": token})
        self.call("POST", f"/deposits/{d['pid']}/settlement/agree", a, {"confirm": True})
        x = self.call("GET", f"/deposits/{d['pid']}", a).get_json()
        self.assertTrue(x["release_form_available"])
        self.assertEqual(x["next_action"]["code"], "release_form")
        r = self.call("GET", f"/deposits/{d['pid']}/release-form", a)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data.startswith(b"%PDF"))
        self.assertEqual(r.mimetype, "application/pdf")


class DoorbeleggenApiTest(ApiBase):
    """Doorbeleggen through the API with the same rules as 0.5.2."""
    agreed_with_invest = t5.DoorbeleggenTest.agreed_with_invest
    def test_choose_and_cancel_then_closed_after_payout(self):
        c, uid, d, _ = self.agreed_with_invest()
        a = self.login()["access_token"]
        opt = self.call("GET", f"/deposits/{d['pid']}/payout-choice", a).get_json()
        self.assertEqual((opt["available"], opt["destination"]), (True, "own"))
        self.assertIn("geld verliezen", opt["risk_text"])
        self.err(self.call("POST", f"/deposits/{d['pid']}/payout-choice", a, {}), 422, "confirm_required")
        r = self.call("POST", f"/deposits/{d['pid']}/payout-choice", a, {"confirm": True})
        self.assertEqual(r.get_json()["destination"], "invest")
        self.assertEqual(self.call("DELETE", f"/deposits/{d['pid']}/payout-choice", a).get_json()["destination"], "own")
        self.call("POST", f"/deposits/{d['pid']}/payout-choice", a, {"confirm": True})
        fin = self.client("finance@a.test")
        fin.post(f"/app/borgen/{d['pid']}/uitbetalen", data={"csrf_token": self.csrf(fin)})
        self.err(self.call("DELETE", f"/deposits/{d['pid']}/payout-choice", a), 409, "payout_choice_closed")
        self.err(self.call("POST", f"/deposits/{d['pid']}/payout-choice", a, {"confirm": True}), 409, "payout_choice_closed")

    def test_org_switch_off_blocks_new_choice(self):
        c, uid, d, _ = self.agreed_with_invest()
        a = self.login()["access_token"]
        with self.app.app_context():
            db.run("UPDATE organizations SET invest_enabled = 0")
        self.assertFalse(self.call("GET", f"/deposits/{d['pid']}/payout-choice", a).get_json()["available"])
        self.err(self.call("POST", f"/deposits/{d['pid']}/payout-choice", a, {"confirm": True}), 409, "payout_choice_closed")

    def test_without_invest_payout_choice_is_hidden(self):
        tok, *_ = self.tess()
        with self.app.app_context():
            db.run("UPDATE organizations SET invest_enabled = 0")
        d = self.row()
        self.err(self.call("GET", f"/deposits/{d['pid']}/payout-choice", tok["access_token"]), 404, "not_found")


# ====================================================================== invest

class InvestApiTest(ApiBase):
    def test_hidden_and_unavailable(self):
        tok, *_ = self.tess()
        a = tok["access_token"]
        with self.app.app_context():
            db.run("UPDATE organizations SET invest_enabled = 0")
        self.err(self.call("GET", "/invest", a), 404, "invest_not_offered")
        self.assertEqual(self.call("GET", "/me", a).get_json()["invest"]["visibility"], "hidden")
        with self.app.app_context():
            db.run("UPDATE organizations SET invest_enabled = 1")
        self.app.config["INVEST_PARTNER"] = ""
        self.err(self.call("GET", "/invest", a), 503, "partner_unavailable")

    def test_onboarding(self):
        tok, *_ = self.tess()
        a = tok["access_token"]
        q = self.call("GET", "/invest/appropriateness", a).get_json()
        self.assertEqual(len(q["questions"]), 8)
        self.assertTrue(q["can_answer"])
        self.assertNotIn("points", json.dumps(q))
        e = self.err(self.call("POST", "/invest/appropriateness", a, {"answers": {"experience": "soms"}}), 422, "validation_failed")
        self.assertIn("funds", e["fields"])
        r = self.call("POST", "/invest/appropriateness", a, {"answers": t5.NIET}).get_json()
        self.assertEqual((r["result"], r["requires_confirmation"], r["may_continue"]), ("niet_passend", True, False))
        self.assertIn("thinks_no_loss", r["reason_keys"])
        self.assertEqual(self.call("GET", "/invest", a).get_json()["onboarding"]["next_step"], "confirm_warning")
        self.err(self.call("POST", "/invest/appropriateness/confirm", a, {}), 422, "confirm_required")
        self.assertTrue(self.call("POST", "/invest/appropriateness/confirm", a, {"confirm": True}).get_json()["may_continue"])
        self.assertEqual(self.call("GET", "/invest", a).get_json()["onboarding"]["next_step"], "terms")
        self.err(self.call("POST", "/invest/account", a, {"portfolio": "neutraal"}), 409, "terms_not_accepted")
        terms = self.call("GET", "/invest/terms", a).get_json()
        self.assertIn("geen advies", terms["depiqo"]["text"])
        self.err(self.call("POST", "/invest/terms", a, {"partner_version": "oud", "depiqo_version": terms["depiqo"]["version"],
                                                        "accept_partner": True, "accept_depiqo": True}), 409, "terms_outdated")
        self.err(self.call("POST", "/invest/terms", a, {"partner_version": terms["partner"]["version"], "depiqo_version": terms["depiqo"]["version"],
                                                        "accept_partner": True}), 422, "accept_depiqo_required")
        self.call("POST", "/invest/terms", a, {"partner_version": terms["partner"]["version"], "depiqo_version": terms["depiqo"]["version"],
                                               "accept_partner": True, "accept_depiqo": True})
        self.assertEqual(self.call("GET", "/invest", a).get_json()["onboarding"]["next_step"], "open_account")
        self.err(self.call("POST", "/invest/account", a, {"portfolio": "agressief"}), 422, "validation_failed")
        r = self.call("POST", "/invest/account", a, {"portfolio": "neutraal"})
        self.assertEqual(r.status_code, 201)
        self.assertIn(r.get_json()["account"]["status"], ("pending", "active"))
        acct = self.acct(self.uid("tess@huurder.test"))
        self.assertEqual((acct["terms_depiqo_version"], acct["fee_rate_bps"]), (investing.DEPIQO_TERMS_VERSION, 25))
        with self.app.app_context():
            self.assertTrue(db.scalar("SELECT COUNT(*) FROM audit_log WHERE action = 'invest.account_opened' AND org_id IS NULL"))
            self.assertFalse(db.scalar("SELECT COUNT(*) FROM audit_log WHERE action LIKE 'invest.%' AND org_id IS NOT NULL"))

    def test_portfolios_with_costs(self):
        tok, *_ = self.tess()
        p = self.call("GET", "/invest/portfolios?amount_cents=100000", tok["access_token"]).get_json()
        self.assertEqual([x["code"] for x in p["items"]], ["defensief", "neutraal", "offensief"])
        neutraal = p["items"][1]
        self.assertEqual(neutraal["costs"]["service_1y"], {"cents": 250, "currency": "EUR"})
        self.assertEqual(len(neutraal["scenarios"]["items"]), 3)
        self.err(self.call("GET", "/invest/portfolios?amount_cents=abc", tok["access_token"]), 422, "validation_failed")

    def test_quote_then_order(self):
        tok, *_ = self.tess()
        a = tok["access_token"]
        self.active_invest(a)
        q = self.quote(a, side="buy", amount_cents=10000)
        self.assertEqual(q["amount"]["cents"], 10000)
        self.assertIn("geld verliezen", q["risk_text"])
        self.assertTrue(q["requires_risk_acknowledgement"])
        self.assertEqual(q["costs"]["service_1y"]["cents"], 25)
        self.assertEqual(len(q["scenarios"]["items"]), 3)
        self.err(self.call("POST", "/invest/orders/quote", a, {"side": "buy", "amount_cents": 1000}), 422, "amount_below_minimum")
        self.err(self.call("POST", "/invest/orders", a, {"quote_id": q["quote_id"], "risk_acknowledged": True}), 400, "idempotency_key_required")
        self.err(self.call("POST", "/invest/orders", a, {"quote_id": q["quote_id"]}, headers={"Idempotency-Key": "order-0001"}),
                 422, "risk_acknowledged_required")
        r = self.call("POST", "/invest/orders", a, {"quote_id": q["quote_id"], "risk_acknowledged": True}, headers={"Idempotency-Key": "order-0002"})
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        order = r.get_json()["order"]
        self.assertEqual((order["side"], order["status"], order["amount"]["cents"]), ("buy", "pending", 10000))
        self.err(self.call("POST", "/invest/orders", a, {"quote_id": q["quote_id"], "risk_acknowledged": True}, headers={"Idempotency-Key": "order-0003"}),
                 409, "quote_used")
        q2 = self.quote(a, side="buy", amount_cents=5000)
        with self.app.app_context():
            db.run("UPDATE invest_quotes SET expires_at = ? WHERE quote_key = ?", ((now() - timedelta(seconds=1)).isoformat(timespec="seconds"), q2["quote_id"]))
        self.err(self.call("POST", "/invest/orders", a, {"quote_id": q2["quote_id"], "risk_acknowledged": True}, headers={"Idempotency-Key": "order-0004"}),
                 409, "quote_expired")
        self.err(self.call("POST", "/invest/orders", a, {"quote_id": "q_bestaatniet", "risk_acknowledged": True}, headers={"Idempotency-Key": "order-0005"}),
                 404, "quote_not_found")
        q3 = self.quote(a, side="buy", amount_cents=900000)  # more than available: refused at order time, quote stays usable
        self.err(self.call("POST", "/invest/orders", a, {"quote_id": q3["quote_id"], "risk_acknowledged": True}, headers={"Idempotency-Key": "order-0006"}),
                 409, "invest_rejected")
        with self.app.app_context():
            self.assertIsNone(db.scalar("SELECT used_at FROM invest_quotes WHERE quote_key = ?", (q3["quote_id"],)))
        orders = self.call("GET", "/invest/orders", a).get_json()["items"]
        self.assertEqual(len(orders), 1)

    def test_idempotency_same_key_same_response_no_double_order(self):
        tok, *_ = self.tess()
        a = tok["access_token"]
        acct = self.active_invest(a)
        q = self.quote(a, side="buy", amount_cents=10000)
        body = {"quote_id": q["quote_id"], "risk_acknowledged": True}
        r1 = self.call("POST", "/invest/orders", a, body, headers={"Idempotency-Key": "same-key-1"})
        r2 = self.call("POST", "/invest/orders", a, body, headers={"Idempotency-Key": "same-key-1"})
        self.assertEqual(r1.status_code, 201)
        self.assertEqual((r2.status_code, r2.get_json()), (201, r1.get_json()))
        self.assertEqual(r2.headers.get("Idempotent-Replayed"), "true")
        with self.app.app_context():
            self.assertEqual(db.scalar("SELECT COUNT(*) FROM invest_orders WHERE account_id = ?", (acct["id"],)), 1)
        self.err(self.call("POST", "/invest/orders", a, {**body, "extra": 1}, headers={"Idempotency-Key": "same-key-1"}), 422, "idempotency_key_reused")
        self.err(self.call("POST", "/invest/orders", a, body, headers={"Idempotency-Key": "kort"}), 400, "invalid_idempotency_key")
        # withdrawals: same key, one instruction
        with self.app.app_context():
            db.run("UPDATE invest_accounts SET own_iban = 'NL91ABNA0417164300', own_iban_usable_from = ? WHERE id = ?", (now_iso(), acct["id"]))
        w1 = self.call("POST", "/invest/withdrawals", a, {"amount_cents": 5000}, headers={"Idempotency-Key": "withdraw-1"})
        w2 = self.call("POST", "/invest/withdrawals", a, {"amount_cents": 5000}, headers={"Idempotency-Key": "withdraw-1"})
        self.assertEqual((w1.status_code, w2.get_json()), (201, w1.get_json()))
        with self.app.app_context():
            self.assertEqual(db.scalar("SELECT COUNT(*) FROM invest_instructions WHERE account_id = ? AND kind = 'withdraw'", (acct["id"],)), 1)
            # after 24 hours the key is forgotten
            db.run("UPDATE api_idempotency SET created_at = ?", ((now() - timedelta(hours=25)).isoformat(timespec="seconds"),))
        self.assertEqual(self.call("POST", "/invest/withdrawals", a, {"amount_cents": 5000}, headers={"Idempotency-Key": "withdraw-1"}).status_code, 201)
        # another user's key space is separate
        self.assertIsNone(r2.headers.get("Set-Cookie"))

    def test_order_execution_notification_and_read(self):
        tok, *_ = self.tess()
        a = tok["access_token"]
        self.active_invest(a)
        q = self.quote(a, side="buy", amount_cents=20000)
        self.call("POST", "/invest/orders", a, {"quote_id": q["quote_id"], "risk_acknowledged": True}, headers={"Idempotency-Key": "exec-0001"})
        self.day()
        notes = self.call("GET", "/notifications", a).get_json()
        executed = [n for n in notes["items"] if n["type"] == "invest_order_executed"][0]
        self.assertEqual(executed["title"], "Je order is uitgevoerd")
        self.assertIn("Neutraal", executed["body"])
        unread = notes["unread_count"]
        r = self.call("POST", f"/notifications/{executed['id']}/read", a)
        self.assertTrue(r.get_json()["read_at"])
        self.assertEqual(self.call("GET", "/notifications", a).get_json()["unread_count"], unread - 1)
        o = self.call("GET", "/invest", a).get_json()
        self.assertEqual(o["summary"]["invested_value"]["cents"] > 0, True)
        self.assertEqual(set(o["chart"]), {"1M", "6M", "1Y", "max"})
        point = o["chart"]["max"][-1]
        self.assertTrue(re.fullmatch(r"\d{4}-\d{2}-\d{2}", point[0]))
        self.assertIsInstance(point[1], int)
        self.assertEqual(self.call("GET", "/invest/orders", a).get_json()["items"][0]["status"], "executed")
        # someone else's notification
        other = self.login("tess@huurder.test")  # same user: fine
        with self.app.app_context():
            nid = notify.notify(self.uid("admin@a.test"), "new_device_login", {"device": "x", "platform": "@platform.ios", "login_at": now_iso()})
        self.err(self.call("POST", f"/notifications/{nid}/read", other["access_token"]), 404, "not_found")

    def test_sell_and_switch_via_quote(self):
        tok, *_ = self.tess()
        a = tok["access_token"]
        self.active_invest(a)
        q = self.quote(a, side="buy", amount_cents=30000)
        self.call("POST", "/invest/orders", a, {"quote_id": q["quote_id"], "risk_acknowledged": True}, headers={"Idempotency-Key": "buy-00001"})
        self.day()
        s = self.quote(a, side="sell", amount_cents=5000)
        self.assertNotIn("service_1y", s["costs"])
        r = self.call("POST", "/invest/orders", a, {"quote_id": s["quote_id"], "risk_acknowledged": True}, headers={"Idempotency-Key": "sell-0001"})
        self.assertEqual(r.get_json()["order"]["side"], "sell")
        self.day()
        sw = self.quote(a, side="switch", portfolio="defensief")
        self.assertEqual(sw["portfolio"]["code"], "defensief")
        r = self.call("POST", "/invest/orders", a, {"quote_id": sw["quote_id"], "risk_acknowledged": True}, headers={"Idempotency-Key": "switch-001"})
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        self.assertEqual(r.get_json()["account"]["pending_switch"], "defensief")
        self.err(self.call("POST", "/invest/orders/quote", a, {"side": "buy", "amount_cents": 5000}), 409, "invest_rejected")

    def test_buy_refused_when_landlord_switches_off(self):
        tok, *_ = self.tess()
        a = tok["access_token"]
        self.active_invest(a)
        with self.app.app_context():
            db.run("UPDATE organizations SET invest_enabled = 0")
        self.assertEqual(self.call("GET", "/invest", a).status_code, 200)  # existing investor keeps access
        e = self.err(self.call("POST", "/invest/orders/quote", a, {"side": "buy", "amount_cents": 5000}), 409, "invest_rejected")
        self.assertIn("biedt Beleggen niet meer aan", e["message"])

    def test_withdrawal_iban_rules(self):
        tok, _, uid, _ = self.tess()
        a = tok["access_token"]
        self.active_invest(a)
        self.err(self.call("POST", "/invest/withdrawals", a, {"amount_cents": 5000}, headers={"Idempotency-Key": "w-00000001"}), 409, "invest_rejected")
        self.err(self.call("POST", "/invest/iban", a, {"iban": "NL00FOUT"}), 409, "invest_rejected")
        r = self.call("POST", "/invest/iban", a, {"iban": "NL91ABNA0417164300"}).get_json()
        self.assertFalse(r["usable_now"])
        self.assertEqual(r["cooling_off_days"], 7)
        e = self.err(self.call("POST", "/invest/withdrawals", a, {"amount_cents": 5000}, headers={"Idempotency-Key": "w-00000002"}), 409, "invest_rejected")
        self.assertIn("vanaf", e["message"])
        secret, _ = self.enable_2fa(uid)
        self.err(self.call("POST", "/invest/iban", a, {"iban": "NL02ABNA0123456789", "code": "000000"}), 409, "invest_rejected")
        r = self.call("POST", "/invest/iban", a, {"iban": "NL02ABNA0123456789", "code": mfa.totp(secret)})
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        self.assertTrue(r.get_json()["usable_now"])
        w = self.call("POST", "/invest/withdrawals", a, {"amount_cents": 5000}, headers={"Idempotency-Key": "w-00000003"})
        self.assertEqual(w.status_code, 201, w.get_data(as_text=True))
        self.assertEqual(w.get_json()["withdrawal"]["iban_masked"], "NL02 … 6789")
        self.day()
        self.assertIn("invest_withdrawal_completed", [n["type"] for n in self.call("GET", "/notifications", a).get_json()["items"]])
        self.assertEqual(self.call("GET", "/invest/withdrawals", a).get_json()["items"][0]["status"], "confirmed")

    def test_transactions_pagination_statements_and_fee_change(self):
        tok, *_ = self.tess()
        a = tok["access_token"]
        acct = self.active_invest(a)
        for i in range(3):
            self.call("POST", "/invest/sandbox/deposit", a, {"amount_cents": 1000 + i}, headers={"Idempotency-Key": f"dep-extra-{i}"})
        p1 = self.call("GET", "/invest/transactions?limit=2", a).get_json()
        self.assertEqual(len(p1["items"]), 2)
        p2 = self.call("GET", f"/invest/transactions?limit=2&cursor={p1['next_cursor']}", a).get_json()
        self.assertTrue(p2["items"])
        self.assertFalse({x["id"] for x in p1["items"]} & {x["id"] for x in p2["items"]})
        self.err(self.call("GET", "/invest/transactions?cursor=@@@", a), 400, "invalid_cursor")
        st = self.call("GET", "/invest/statements", a).get_json()["items"]
        self.assertTrue(st)
        pdf = self.call("GET", f"/invest/statements/{st[0]['period']}", a)
        self.assertTrue(pdf.data.startswith(b"%PDF"))
        self.err(self.call("GET", "/invest/statements/1999-01", a), 404, "not_found")
        self.assertIsNone(self.call("GET", "/invest/fee-change", a).get_json()["pending_bps"])
        with self.ctx():
            investing.set_fee_bps(30, self.uid("staff@depiqo.test"))
        fc = self.call("GET", "/invest/fee-change", a).get_json()
        self.assertEqual(fc["pending_bps"], 30)
        self.assertIn("invest_fee_change", [n["type"] for n in self.call("GET", "/notifications", a).get_json()["items"]])
        self.err(self.call("POST", "/invest/fee-change", a, {}), 422, "accept_required")
        self.assertEqual(self.call("POST", "/invest/fee-change", a, {"accept": True}).get_json()["account"]["fee_rate_bps"], 30)
        self.assertEqual(self.acct(acct["user_id"])["fee_rate_bps"], 30)

    def test_deposit_instructions(self):
        tok, *_ = self.tess()
        a = tok["access_token"]
        self.err(self.call("GET", "/invest/deposit-instructions", a), 409, "account_not_active")
        acct = self.active_invest(a)
        i = self.call("GET", "/invest/deposit-instructions", a).get_json()
        self.assertEqual((i["iban"], i["reference"]), (investing.SandboxInvest.client_money_iban, acct["reference"]))


# ====================================================================== notifications, push, languages

class PushTest(ApiBase):
    def token(self, a, value="ExponentPushToken[abcdefghij1234567890]"):
        return self.call("POST", "/devices/push-token", a, {"token": value, "platform": "ios"})

    def test_outbox_in_sandbox_is_skipped_and_has_no_personal_data(self):
        tok, _, _, d = self.tess()
        a = tok["access_token"]
        self.assertEqual(self.token(a).status_code, 201)
        self.err(self.token(a, "geen-token"), 422, "validation_failed")
        acct = self.account(d)
        self.webhook(self.app.test_client(), "deposit.received", {"event_id": "pp1", "external_id": acct["external_id"], "amount_cents": 200000, "ref": "r"})
        with self.app.app_context():
            msgs = db.all_("SELECT * FROM push_messages")
        self.assertTrue(msgs)
        for m in msgs:
            self.assertEqual((m["status"], m["note"], m["provider"]), ("skipped", "sandbox", "expo"))
            self.assertEqual(m["body"], "Open Depiqo voor de details.")
            self.assertNotRegex(m["title"] + m["body"], r"\d|€|Tess|Teststraat")
            self.assertEqual(set(json.loads(m["data_json"])), {"notification_id", "path", "type"})

    def test_dispatch_and_device_not_registered(self):
        tok, *_ = self.tess()
        a = tok["access_token"]
        self.token(a, "ExponentPushToken[aaaaaaaaaa1111111111]")
        self.app.config["PUSH_SEND"] = True
        with self.app.app_context():
            uid = self.uid("tess@huurder.test")
            notify.notify(uid, "deposit_secured")
            self.assertEqual(db.scalar("SELECT status FROM push_messages ORDER BY id DESC LIMIT 1"), "pending")
            with mock.patch.object(notify, "_post_json", return_value={"data": [{"status": "ok", "id": "ticket-1"}]}) as post:
                self.assertEqual(notify.dispatch()["sent"], 1)
            self.assertEqual(post.call_args[0][0], notify.EXPO_SEND_URL)
            self.assertEqual(post.call_args[0][1][0]["to"], "ExponentPushToken[aaaaaaaaaa1111111111]")
            with mock.patch.object(notify, "_post_json", return_value={"data": {"ticket-1": {"status": "error", "details": {"error": "DeviceNotRegistered"}}}}):
                self.assertEqual(notify.check_receipts(), 1)
            self.assertEqual(db.scalar("SELECT active FROM push_tokens"), 0)
            self.assertEqual(db.scalar("SELECT status FROM push_messages WHERE ticket_id = 'ticket-1'"), "failed")
            # a ticket error at sending time deactivates too
            db.run("UPDATE push_tokens SET active = 1")
            notify.notify(uid, "deposit_secured")
            with mock.patch.object(notify, "_post_json", return_value={"data": [{"status": "error", "details": {"error": "DeviceNotRegistered"}}]}):
                self.assertEqual(notify.dispatch()["failed"], 1)
            self.assertEqual(db.scalar("SELECT active FROM push_tokens"), 0)
            # Expo down: stays pending
            db.run("UPDATE push_tokens SET active = 1")
            notify.notify(uid, "deposit_secured")
            with mock.patch.object(notify, "_post_json", side_effect=OSError("netwerk")):
                notify.dispatch()
            self.assertEqual(db.scalar("SELECT status FROM push_messages ORDER BY id DESC LIMIT 1"), "pending")

    def test_token_moves_between_users_and_preferences(self):
        tok, *_ = self.tess()
        a = tok["access_token"]
        self.token(a)
        r = self.call("PATCH", "/me", a, {"notification_preferences": {"push": {"invest": False}}})
        self.assertEqual(r.get_json()["notification_preferences"]["push"], {"deposit": True, "invest": False, "security": True, "support": True})
        with self.app.app_context():
            uid = self.uid("tess@huurder.test")
            before = db.scalar("SELECT COUNT(*) FROM push_messages")
            notify.notify(uid, "invest_fee_change", {"new_bps": 30, "old_bps": 25})
            self.assertEqual(db.scalar("SELECT COUNT(*) FROM push_messages"), before)  # stored, not pushed
            notify.notify(uid, "deposit_secured")
            self.assertEqual(db.scalar("SELECT COUNT(*) FROM push_messages"), before + 1)
        self.err(self.call("PATCH", "/me", a, {"notification_preferences": {"push": {"marketing": True}}}), 422, "validation_failed")

    def test_revoked_device_deactivates_its_push_token(self):
        tok, *_ = self.tess()
        a = tok["access_token"]
        self.token(a)
        self.call("POST", "/auth/logout", a)
        with self.app.app_context():
            self.assertEqual(db.scalar("SELECT active FROM push_tokens"), 0)


class LanguageTest(ApiBase):
    def test_catalog_complete_for_all_codes_and_types(self):
        src = ""
        for name in os.listdir(os.path.join(ROOT, "app", "api")):
            if name.endswith(".py"):
                with open(os.path.join(ROOT, "app", "api", name), encoding="utf-8") as f:
                    src += f.read()
        with open(os.path.join(ROOT, "app", "apitokens.py"), encoding="utf-8") as f:
            src += f.read()
        codes = set(re.findall(r'ApiError\(\d+, "([a-z_]+)"', src)) | set(re.findall(r'TokenProblem\("([a-z_]+)"', src))
        codes |= set(re.findall(r'field_error\([^)]*?, "([a-z_]+)"\)', src))
        codes |= {f"{n}_required" for n in re.findall(r'true_field\([^,]+, "(\w+)"', src)}
        from app.api import HTTP_ERRORS
        codes |= {c for c, _ in HTTP_ERRORS.values()} | {"validation_failed"}
        keys = {f"error.{c}" for c in codes}
        for t in notify.TYPES:
            keys |= {f"notif.{t}.title", f"notif.{t}.body"}
        missing = sorted(k for k in keys if not i18n.has(k))
        self.assertEqual(missing, [], f"Ontbrekende sleutels in app/i18n.py: {missing}")
        self.assertEqual(i18n.missing(), [], f"Ontbrekende vertalingen: {i18n.missing()}")

    def test_fallback_to_dutch(self):
        self.assertEqual(i18n.t("error.not_found", "de"), "Niet gevonden.")
        self.assertEqual(i18n.pick("de-DE, fr;q=0.8, en;q=0.9"), "en")
        self.assertIsNone(i18n.pick("de"))
        self.assertEqual(i18n.money(123456, "fr"), "1 234,56 €")
        self.assertEqual(i18n.money(123456, "en"), "€1,234.56")

    def test_accept_language_for_errors_and_notifications(self):
        tok, *_ = self.tess()
        a = tok["access_token"]
        r = self.call("GET", "/deposits/bestaatniet", a, headers={"Accept-Language": "fr-BE,fr;q=0.9"})
        e = self.err(r, 404, "not_found")
        self.assertEqual(e["message"], "Introuvable.")
        self.assertEqual(r.headers["Content-Language"], "fr")
        r = self.call("PATCH", "/me", a, {"name": ""}, headers={"Accept-Language": "en"})
        e = self.err(r, 422, "validation_failed")
        self.assertEqual(e["message"], "Please check the data you entered.")
        self.assertIn("Vul je naam in", e["detail"])
        e = self.err(self.call("PATCH", "/me", a, {"pet": 1}, headers={"Accept-Language": "fr"}), 422, "unknown_field")
        self.assertEqual(e["fields"], {"pet": "Champ inconnu."})
        n = self.call("GET", "/notifications", a, headers={"Accept-Language": "en"}).get_json()["items"][0]
        self.assertEqual((n["title"], n["language"]), ("New login to your account", "en"))
        self.assertIn("Testtelefoon", n["body"])
        # stored preference when no header is sent
        self.call("PATCH", "/me", a, {"language": "fr"})
        n = self.call("GET", "/notifications", a).get_json()["items"][0]
        self.assertEqual(n["title"], "Nouvelle connexion à votre compte")
        self.err(self.call("PATCH", "/me", a, {"language": "de"}), 422, "validation_failed")

    def test_push_and_email_in_users_language(self):
        tok, _, uid, _ = self.tess()
        a = tok["access_token"]
        self.call("PATCH", "/me", a, {"language": "en"})
        self.call("POST", "/devices/push-token", a, {"token": "ExponentPushToken[bbbbbbbbbb2222222222]", "platform": "android"})
        with self.app.app_context():
            notify.notify(uid, "deposit_secured")
            m = db.one("SELECT * FROM push_messages ORDER BY id DESC LIMIT 1")
            self.assertEqual((m["title"], m["body"]), ("Your deposit is secured", "Open Depiqo for the details."))
            stored = db.one("SELECT * FROM notifications ORDER BY id DESC LIMIT 1")
            self.assertEqual(stored["title"], "Je borg staat veilig")  # the record stays in Dutch
        self.active_invest(a)
        self.call("POST", "/invest/iban", a, {"iban": "NL91ABNA0417164300"})
        with self.app.app_context():
            mail = db.one("SELECT * FROM outbox_emails ORDER BY id DESC LIMIT 1")
        self.assertEqual(mail["subject"], "Your account number for withdrawals has changed")
        self.assertIn("You can use it from", mail["body_text"])

    def test_labels_have_stable_keys(self):
        mgr, d = self.external_awaiting(provider_kind="borggarantie", provider_name="Garantiefonds C", provider_reference="G-1",
                                        guarantee_expires_on=(local_today() + timedelta(days=30)).isoformat())
        a = self.login()["access_token"]
        x = self.call("GET", f"/deposits/{d['pid']}", a).get_json()
        self.assertEqual((x["status"], x["display_key"], x["provider_kind"]), ("awaiting_payment", "awaiting_guarantee", "borggarantie"))
        self.assertEqual(x["location"]["guarantee"]["warning_key"], "expiring")
        self.assertEqual(x["next_action"]["code"], "wait")
        self.assertEqual({f["key"]: f["explanation_key"] for f in x["amounts"]}["received"], "guarantee_no_money")

    def test_all_balance_notes_have_keys(self):
        import inspect
        from app.api.deposits import NOTE_KEYS
        src = inspect.getsource(services.balances)
        labels = {"Vereiste borg", "Ontvangen", "Bevestigd geblokkeerd", "Rente"}
        notes = {s for s in re.findall(r'"([A-Z][^"]{6,})"', src) if s not in labels and not s.startswith("SELECT") and "\n" not in s}
        self.assertEqual(sorted(notes - set(NOTE_KEYS)), [])


# ====================================================================== me, export, deletion, support, activity

class MeTest(ApiBase):
    def test_patch_me(self):
        tok, *_ = self.tess()
        a = tok["access_token"]
        r = self.call("PATCH", "/me", a, {"name": "Tess de Huurder"})
        self.assertEqual(r.get_json()["name"], "Tess de Huurder")
        e = self.err(self.call("PATCH", "/me", a, {"email": "x@y.test"}), 422, "unknown_field")
        self.assertIn("email", e["fields"])
        self.err(self.call("PATCH", "/me", a, {"name": ""}), 422, "validation_failed")

    def test_export_contents(self):
        tok, _, uid, d = self.tess()
        a = tok["access_token"]
        self.enable_2fa(uid)
        tok = self.login()  # 2FA is on now; the old session was ended
        secret = None
        with self.app.app_context():
            secret = db.scalar("SELECT totp_secret FROM users WHERE id = ?", (uid,))
        a = self.call("POST", "/auth/mfa", json_body={"mfa_token": tok["mfa_token"], "code": mfa.totp(secret)}).get_json()["access_token"]
        self.call("POST", "/support", a, {"category": "deposit", "message": "Wanneer krijg ik mijn borg terug?", "deposit_pid": d["pid"]})
        r = self.call("POST", "/me/export", a)
        self.assertEqual(r.status_code, 200)
        self.assertIn("attachment", r.headers["Content-Disposition"])
        data = json.loads(r.data)
        self.assertEqual(data["user"]["email"], "tess@huurder.test")
        self.assertEqual([x["pid"] for x in data["deposits"]], [d["pid"]])
        self.assertTrue(data["deposits"][0]["events"])
        self.assertTrue(data["notifications"])
        self.assertTrue(data["devices"])
        self.assertEqual(data["support"][0]["category"], "deposit")
        text = r.get_data(as_text=True)
        for secret_field in ("password_hash", "totp_secret", "token_hash", secret):
            self.assertNotIn(secret_field, text)
        with self.app.app_context():
            self.assertTrue(db.scalar("SELECT COUNT(*) FROM audit_log WHERE action = 'account.exported' AND org_id IS NULL"))

    def test_delete_refused_while_deposit_open_or_invest_balance(self):
        tok, *_ = self.tess()
        a = tok["access_token"]
        prev = self.call("GET", "/me/delete-request", a).get_json()
        self.assertFalse(prev["possible"])
        self.assertEqual(prev["blockers"][0]["code"], "open_deposit")
        self.assertTrue(prev["kept_by_law"])
        self.err(self.call("POST", "/me/delete-request", a, {"password": "fout-wachtwoord-1", "confirm": True}), 422, "invalid_password")
        e = self.err(self.call("POST", "/me/delete-request", a, {"password": PW, "confirm": True}), 409, "deletion_blocked")
        self.assertIn("loopt nog", e["message"])
        self.active_invest(a)
        with self.app.app_context():
            db.run("UPDATE deposits SET status = 'closed'")
        blockers = self.call("GET", "/me/delete-request", a).get_json()["blockers"]
        self.assertEqual([b["code"] for b in blockers], ["invest_balance"])
        self.err(self.call("POST", "/me/delete-request", a, {"password": PW, "confirm": True}), 409, "deletion_blocked")

    def test_delete_anonymises(self):
        tok, _, uid, d = self.tess()
        a = tok["access_token"]
        self.call("POST", "/devices/push-token", a, {"token": "ExponentPushToken[cccccccccc3333333333]", "platform": "ios"})
        with self.app.app_context():
            db.run("UPDATE deposits SET status = 'closed'")
        self.err(self.call("POST", "/me/delete-request", a, {"password": PW}), 422, "confirm_required")
        r = self.call("POST", "/me/delete-request", a, {"password": PW, "confirm": True})
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        self.assertTrue(r.get_json()["deleted"])
        with self.app.app_context():
            u = db.one("SELECT * FROM users WHERE id = ?", (uid,))
            self.assertTrue(u["email"].endswith("@verwijderd.depiqo.invalid"))
            self.assertEqual((u["name"], u["password_hash"], u["totp_secret"]), ("Verwijderde gebruiker", None, None))
            self.assertTrue(u["deleted_at"])
            self.assertIsNone(db.scalar("SELECT user_id FROM tenants WHERE email = 'tess@huurder.test'"))
            self.assertTrue(db.scalar("SELECT COUNT(*) FROM deposits WHERE id = ?", (d["id"],)))  # kept for the landlord
            self.assertFalse(db.scalar("SELECT COUNT(*) FROM notifications WHERE user_id = ?", (uid,)))
            self.assertFalse(db.scalar("SELECT COUNT(*) FROM push_tokens WHERE user_id = ?", (uid,)))
            self.assertEqual(db.scalar("SELECT org_id FROM audit_log WHERE action = 'account.deleted'"), None)
            self.assertTrue(db.scalar("SELECT COUNT(*) FROM audit_log WHERE action = 'account.deleted'"))
        self.err(self.call("GET", "/me", a), 401, "token_invalid")  # every token of the account is deleted
        self.err(self.call("POST", "/auth/login", json_body={"email": "tess@huurder.test", "password": PW, "device": DEVICE}), 401, "invalid_credentials")

    def test_support_ticket_flow(self):
        tok, _, uid, d = self.tess()
        a = tok["access_token"]
        self.err(self.call("POST", "/support", a, {"category": "geld", "message": "Hallo daar, een vraag"}), 422, "validation_failed")
        self.err(self.call("POST", "/support", a, {"category": "deposit", "message": "kort"}), 422, "validation_failed")
        r = self.call("POST", "/support", a, {"category": "deposit", "message": "Wanneer krijg ik mijn borg terug?", "deposit_pid": d["pid"]})
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        t = r.get_json()
        self.assertEqual((t["status"], t["deposit_pid"]), ("open", d["pid"]))
        with self.app.app_context():
            mail = db.one("SELECT * FROM outbox_emails ORDER BY id DESC LIMIT 1")
        self.assertEqual(mail["to_email"], "support@getdepiqo.com")
        self.assertIsNone(mail["deposit_id"])  # never in the landlord's communication log
        mgr = self.client("admin@a.test")
        self.assertNotIn("Wanneer krijg ik", mgr.get(f"/app/borgen/{d['pid']}").get_data(as_text=True))
        for i in range(2):
            self.call("POST", "/support", a, {"category": "app", "message": f"Nog een vraag nummer {i}"})
        self.err(self.call("POST", "/support", a, {"category": "app", "message": "Vierde vraag binnen tien minuten"}), 429, "support_rate_limited")
        staff = self.client("staff@depiqo.test")
        page = staff.get("/admin/support").get_data(as_text=True)
        self.assertIn("Wanneer krijg ik", staff.get(f"/admin/support/{t['id']}").get_data(as_text=True))
        self.assertIn("Mijn borg", page)
        staff.post(f"/admin/support/{t['id']}", data={"action": "reply", "body": "Binnen 14 dagen na het einde van de huur.",
                                                       "csrf_token": self.csrf(staff, f"/admin/support/{t['id']}")})
        mine = self.call("GET", "/support", a).get_json()["items"]
        answered = [x for x in mine if x["id"] == t["id"]][0]
        self.assertEqual(answered["status"], "answered")
        self.assertEqual(answered["messages"][-1]["author"], "staff")
        self.assertIn("support_reply", [n["type"] for n in self.call("GET", "/notifications", a).get_json()["items"]])
        staff.post(f"/admin/support/{t['id']}", data={"action": "close", "csrf_token": self.csrf(staff, f"/admin/support/{t['id']}")})
        self.assertEqual([x for x in self.call("GET", "/support", a).get_json()["items"] if x["id"] == t["id"]][0]["status"], "closed")
        self.assertEqual(self.client("admin@a.test").get("/admin/support").status_code, 404)  # not for business users

    def test_activity_combines_deposit_and_invest(self):
        tok, _, _, d = self.tess()
        a = tok["access_token"]
        self.active_invest(a)
        items = self.call("GET", "/activity?limit=100", a).get_json()["items"]
        kinds = {i["type"] for i in items}
        self.assertEqual(kinds, {"deposit_event", "invest_transaction"})
        self.assertEqual(items, sorted(items, key=lambda i: i["at"], reverse=True))
        dep = [i for i in items if i["type"] == "invest_transaction"][0]
        self.assertEqual(dep["key"], "invest_deposit")
        page1 = self.call("GET", "/activity?limit=2", a).get_json()
        page2 = self.call("GET", f"/activity?limit=100&cursor={page1['next_cursor']}", a).get_json()
        self.assertEqual(len(page1["items"]) + len(page2["items"]), len(items))
        self.err(self.call("GET", "/activity?cursor=WzFd", a), 400, "invalid_cursor")


# ====================================================================== environments and financial safety

class SafetyTest(ApiBase):
    PROD_ENV = {"DEPIQO_ENV": "production", "SECRET_KEY": "x" * 40, "BANK_WEBHOOK_SECRET": "y" * 40, "BASE_URL": "https://app.example.test",
                "DEPIQO_SANDBOX": "1"}

    def prod_app(self, **over):
        with mock.patch.dict(os.environ, self.PROD_ENV):
            return create_app({"DATABASE_PATH": self.app.config["DATABASE_PATH"], "STORAGE_DIR": self.app.config["STORAGE_DIR"],
                               "SANDBOX": True, "BANK_PARTNER": "sandbox", "INVEST_PARTNER": "sandbox", **over})

    def test_production_never_runs_sandbox_partners(self):
        prod = self.prod_app()
        self.assertFalse(prod.config["SANDBOX"])
        with prod.app_context():
            from app.partners import bank
            self.assertFalse(bank().available)
            self.assertFalse(investing.partner().available)
        with mock.patch.dict(os.environ, {"DEPIQO_ENV": "staging", "SECRET_KEY": "z" * 40, "BANK_WEBHOOK_SECRET": "w" * 40,
                                          "BASE_URL": "https://staging.example.test"}):
            st = create_app({"DATABASE_PATH": self.app.config["DATABASE_PATH"], "STORAGE_DIR": self.app.config["STORAGE_DIR"]})
        c = st.test_client().get(API + "/config").get_json()
        self.assertEqual((c["environment"], c["banner"], c["sandbox"]), ("staging", "STAGING", True))
        with mock.patch.dict(os.environ, {"DEPIQO_ENV": "test"}):
            with self.assertRaises(RuntimeError):
                create_app({"DATABASE_PATH": self.app.config["DATABASE_PATH"]})

    def test_every_money_and_invest_endpoint_fails_closed_in_production(self):
        tok, _, _, d = self.tess()
        self.active_invest(tok["access_token"])
        # a Depiqo deposit that still needs identity, and one agreed for doorbeleggen
        prod = self.prod_app()
        pc = prod.test_client()
        r = pc.post(API + "/auth/login", json={"email": "tess@huurder.test", "password": PW, "device": DEVICE})
        a = r.get_json()["access_token"]
        h = {"Authorization": f"Bearer {a}", "Idempotency-Key": "prod-check-1"}
        self.assertEqual(pc.get(API + "/config").get_json()["environment"], "production")
        calls = [("GET", "/invest", None), ("GET", "/invest/portfolios", None), ("GET", "/invest/appropriateness", None),
                 ("POST", "/invest/appropriateness", {"answers": t5.PASSEND}), ("POST", "/invest/appropriateness/confirm", {"confirm": True}),
                 ("GET", "/invest/terms", None), ("POST", "/invest/terms", {}), ("POST", "/invest/account", {"portfolio": "neutraal"}),
                 ("GET", "/invest/deposit-instructions", None), ("POST", "/invest/orders/quote", {"side": "buy", "amount_cents": 5000}),
                 ("POST", "/invest/orders", {"quote_id": "x", "risk_acknowledged": True}), ("GET", "/invest/orders", None),
                 ("POST", "/invest/iban", {"iban": "NL91ABNA0417164300"}), ("POST", "/invest/withdrawals", {"amount_cents": 100}),
                 ("GET", "/invest/withdrawals", None), ("GET", "/invest/transactions", None), ("GET", "/invest/statements", None),
                 ("GET", "/invest/statements/2026-10", None), ("GET", "/invest/fee-change", None), ("POST", "/invest/fee-change", {"accept": True}),
                 ("GET", f"/deposits/{d['pid']}/payout-choice", None), ("POST", f"/deposits/{d['pid']}/payout-choice", {"confirm": True}),
                 ("DELETE", f"/deposits/{d['pid']}/payout-choice", None)]
        for method, path, body in calls:
            r = pc.open(API + path, method=method, json=body, headers=h)
            self.assertEqual((r.status_code, r.get_json()["error"]["code"]), (503, "partner_unavailable"), f"{method} {path}")
        # sandbox endpoints do not exist outside the sandbox
        r = pc.post(API + "/invest/sandbox/deposit", json={"amount_cents": 100}, headers=h)
        self.assertEqual(r.status_code, 404)
        # opening a deposit account needs the bank
        with self.app.app_context():
            db.run("UPDATE deposits SET status = 'id_pending' WHERE id = ?", (d["id"],))
        r = pc.post(API + f"/deposits/{d['pid']}/identity", json={"full_name": "Tess", "birth_date": "1990-01-01"}, headers=h)
        self.assertEqual((r.status_code, r.get_json()["error"]["code"]), (503, "partner_unavailable"))
        detail = pc.get(API + f"/deposits/{d['pid']}", headers=h).get_json()
        self.assertEqual(detail["next_action"]["code"], "wait")

    def test_no_endpoint_moves_deposit_money(self):
        """The app can agree, dispute and choose a destination; releases only start server-side (landlord and bank)."""
        allowed = {("POST", "/api/v1/deposits/<pid>/identity"), ("POST", "/api/v1/deposits/<pid>/documents"),
                   ("POST", "/api/v1/deposits/<pid>/settlement/agree"), ("POST", "/api/v1/deposits/<pid>/settlement/dispute"),
                   ("POST", "/api/v1/deposits/<pid>/payout-choice"), ("DELETE", "/api/v1/deposits/<pid>/payout-choice")}
        found = {(m, r.rule) for r in self.app.url_map.iter_rules() if r.rule.startswith("/api/v1/deposits")
                 for m in r.methods - {"GET", "HEAD", "OPTIONS"}}
        self.assertEqual(found, allowed)
        for r in self.app.url_map.iter_rules():
            if r.rule.startswith("/api/"):
                self.assertNotRegex(r.rule, r"payout$|release$|uitbetal|vrijgave|transfer")


# ====================================================================== deep links and the spec

class WellKnownTest(ApiBase):
    def test_files(self):
        c = self.app.test_client()
        aasa = c.get("/.well-known/apple-app-site-association")
        self.assertEqual(aasa.mimetype, "application/json")
        d = aasa.get_json()["applinks"]["details"][0]
        self.assertEqual(d["appIDs"], ["TEAMID0000.com.getdepiqo.app"])
        self.assertEqual([x["/"] for x in d["components"]], ["/t/*", "/app-link/*"])
        self.app.config.update(APP_IOS_TEAM_ID="ABCDE12345", ANDROID_SHA256_CERT="AA:BB")
        self.assertEqual(c.get("/.well-known/apple-app-site-association").get_json()["applinks"]["details"][0]["appIDs"],
                         ["ABCDE12345.com.getdepiqo.app"])
        al = c.get("/.well-known/assetlinks.json").get_json()[0]
        self.assertEqual(al["target"]["package_name"], "com.getdepiqo.app")
        self.assertEqual(al["target"]["sha256_cert_fingerprints"], ["AA:BB"])
        self.app.config.update(ENV_NAME="production", APP_IOS_TEAM_ID="", ANDROID_SHA256_CERT="")
        self.assertEqual(c.get("/.well-known/apple-app-site-association").status_code, 404)
        self.assertEqual(c.get("/.well-known/assetlinks.json").status_code, 404)

    def test_web_fallback(self):
        c = self.app.test_client()
        self.assertTrue(c.get("/app-link/borg/abc123").headers["Location"].endswith("/wallet/borg/abc123"))
        self.assertTrue(c.get("/app-link/beleggen").headers["Location"].endswith("/wallet/beleggen"))
        self.assertTrue(c.get("/app-link/iets").headers["Location"].endswith("/wallet"))


def _spec_text():
    with open(os.path.join(ROOT, "docs", "api", "openapi.yaml"), encoding="utf-8") as f:
        return f.read()


def spec_operations(text):
    """(METHOD, path) pairs from the paths section, read without a YAML library."""
    ops, path, in_paths = set(), None, False
    for line in text.splitlines():
        if re.match(r"^paths:\s*$", line):
            in_paths = True
            continue
        if in_paths and re.match(r"^\S", line):
            break
        if not in_paths:
            continue
        m = re.match(r"^  (/[^:]*):\s*$", line)
        if m:
            path = m.group(1)
            continue
        m = re.match(r"^    (get|post|put|patch|delete):\s*$", line)
        if m and path:
            ops.add((m.group(1).upper(), path))
    return ops


class SpecTest(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        self.app = create_app({"DATABASE_PATH": os.path.join(self.tmp, "s.sqlite3"), "STORAGE_DIR": os.path.join(self.tmp, "f")})

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_spec_and_url_map_match_both_ways(self):
        routes = set()
        for r in self.app.url_map.iter_rules():
            if r.rule.startswith("/api/v1"):
                path = re.sub(r"<(?:\w+:)?(\w+)>", r"{\1}", r.rule[len("/api/v1"):]) or "/"
                routes |= {(m, path) for m in r.methods - {"HEAD", "OPTIONS"}}
        spec = spec_operations(_spec_text())
        self.assertEqual(sorted(routes - spec), [], "In de code maar niet in docs/api/openapi.yaml")
        self.assertEqual(sorted(spec - routes), [], "In docs/api/openapi.yaml maar niet in de code")

    def test_spec_structure(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML niet beschikbaar; de paden zijn al vergeleken")
        doc = yaml.safe_load(_spec_text())
        self.assertEqual(doc["openapi"], "3.1.0")
        self.assertIn("Error", doc["components"]["schemas"])
        refs = set(re.findall(r"\$ref: ['\"]?#/components/(\w+)/(\w+)", _spec_text()))
        for kind, name in refs:
            self.assertIn(name, doc["components"][kind], f"$ref naar onbekend {kind}/{name}")
        for path, item in doc["paths"].items():
            for method, op in item.items():
                if method == "parameters":
                    continue
                self.assertTrue(op.get("operationId"), f"{method} {path} zonder operationId")
                codes = {str(c) for c in op["responses"]}
                self.assertTrue(any(c.startswith("2") for c in codes), f"{method} {path} zonder succesantwoord")
                if path != "/config":
                    self.assertTrue(any(c.startswith("4") or c.startswith("5") for c in codes), f"{method} {path} zonder foutantwoord")


class ResponseSchemaTest(ApiBase):
    """Real responses validated against the schemas in docs/api/openapi.yaml (when PyYAML and jsonschema are installed)."""
    def validator(self, name):
        try:
            import yaml
            from jsonschema import Draft202012Validator
            from referencing import Registry, Resource
            from referencing.jsonschema import DRAFT202012
        except ImportError:
            self.skipTest("PyYAML of jsonschema niet beschikbaar")
        doc = yaml.safe_load(_spec_text())
        registry = Registry().with_resource("urn:spec", Resource.from_contents(doc, default_specification=DRAFT202012))
        return Draft202012Validator({"$ref": f"urn:spec#/components/schemas/{name}"}, registry=registry)

    def check(self, name, data):
        errors = list(self.validator(name).iter_errors(data))
        self.assertEqual([f"{list(e.path)}: {e.message}" for e in errors][:5], [], name)

    def test_responses_match_schemas(self):
        tok, _, _, d = self.tess()
        a = tok["access_token"]
        self.check("Config", self.call("GET", "/config").get_json())
        self.check("Session", tok)
        self.check("Me", self.call("GET", "/me", a).get_json())
        self.check("DepositSummary", self.call("GET", "/deposits", a).get_json()["items"][0])
        self.check("DepositDetail", self.call("GET", f"/deposits/{d['pid']}", a).get_json())
        for n in self.call("GET", "/notifications", a).get_json()["items"]:
            self.check("Notification", n)
        self.check("Error", self.call("GET", "/me").get_json())
        self.check("InvestOverview", self.call("GET", "/invest", a).get_json())
        self.active_invest(a)
        q = self.quote(a, side="buy", amount_cents=10000)
        self.check("Quote", q)
        r = self.call("POST", "/invest/orders", a, {"quote_id": q["quote_id"], "risk_acknowledged": True}, headers={"Idempotency-Key": "schema-001"})
        self.check("Order", r.get_json()["order"])
        self.check("InvestAccount", r.get_json()["account"])
        self.day()
        o = self.call("GET", "/invest", a).get_json()
        self.check("InvestOverview", o)
        for t in self.call("GET", "/invest/transactions", a).get_json()["items"]:
            self.check("InvestTransaction", t)
        for item in self.call("GET", "/activity", a).get_json()["items"]:
            self.check("ActivityItem", item)
        self.check("Terms", self.call("GET", "/invest/terms", a).get_json())
        self.check("SupportTicket", self.call("POST", "/support", a, {"category": "app", "message": "Hoe werkt de app precies?"}).get_json())
        self.check("DeletionInfo", self.call("GET", "/me/delete-request", a).get_json())
        self.check("PayoutChoice", {"available": False, "destination": "own", "choice": None, "partner": "x", "risk_text": "r",
                                    "confirmation_text": "c", "explanation": "e"})


if __name__ == "__main__":
    unittest.main()
