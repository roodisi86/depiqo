"""App configuration, login with optional second step, token refresh, logout, device sessions,
invitations and push tokens."""
import json
import re

from flask import current_app, g, jsonify

from .. import apitokens, db, i18n, mfa, notify, rules, services
from ..security import NO_ORG, attempt_done, attempt_start, audit, client_ip, password_problem, verify_password
from ..util import dumps, now_iso, sha256
from . import (API_VERSION, ApiError, body, bp, check_app_version, field_error, minimum_version, money, require_user,
               str_field, tenant_api, tenant_problem, true_field)


# ------------------------------------------------------------ config (public)

@bp.route("/config", methods=["GET"])
def config():
    cfg = current_app.config
    base = services.base_url()
    env = cfg.get("ENV_NAME")
    sandbox = bool(cfg.get("SANDBOX"))
    return jsonify({
        "api_version": API_VERSION,
        "environment": env,
        "banner": "STAGING" if env == "staging" else ("SANDBOX" if sandbox else None),
        "languages": list(i18n.LANGS), "default_language": i18n.DEFAULT,
        "minimum_app_version": {"ios": minimum_version("ios"), "android": minimum_version("android")},
        "features": {"wallet": True, "invest": "per_user", "push": True, "document_upload": True},
        "support_email": cfg.get("SUPPORT_EMAIL"),
        "links": {"privacy": cfg.get("PRIVACY_URL"), "terms": cfg.get("TERMS_URL"),
                  "password_reset": f"{base}/wachtwoord-vergeten", "security": f"{base}/account/beveiliging", "web": base},
        "sandbox": sandbox,
    })


# ------------------------------------------------------------ login

def _device(data):
    d = data.get("device")
    if not isinstance(d, dict):
        raise field_error("device", "Stuur de gegevens van het apparaat mee (name, platform, app_version).")
    name = d.get("name")
    platform = d.get("platform")
    version = d.get("app_version")
    if not isinstance(name, str) or not name.strip():
        raise field_error("device.name", "Geef de naam van het apparaat.")
    if platform not in ("ios", "android"):
        raise field_error("device.platform", "Platform is ios of android.")
    if not isinstance(version, str) or not re.fullmatch(r"\d{1,3}(\.\d{1,3}){0,2}", version.strip()):
        raise field_error("device.app_version", "Geef de versie van de app, bijvoorbeeld 1.0.0.")
    check_app_version(platform, version.strip())
    return {"name": re.sub(r"[\x00-\x1f]", "", name.strip())[:80], "platform": platform, "app_version": version.strip()}


def _session_response(user, device_id, status=200, extra=None):
    tokens = apitokens.issue(device_id)
    tokens.pop("_refresh_id", None)
    payload = {**tokens, "device_id": device_id, "user": {"id": user["id"], "name": user["name"], "email": user["email"]}}
    payload.update(extra or {})
    resp = jsonify(payload)
    resp.status_code = status
    return resp


def _new_device_session(user, device, second_factor=None):
    device_id = apitokens.create_device(user["id"], device, client_ip(), mfa=bool(second_factor))
    audit("api.login", f"user:{user['id']}", {"device": device_id, "platform": device["platform"], "second_factor": second_factor},
          org_id=NO_ORG, user_id=user["id"])
    db.run("UPDATE users SET last_login_at = ? WHERE id = ?", (now_iso(), user["id"]))
    notify.notify(user["id"], "new_device_login", {"device": device["name"], "platform": f"@platform.{device['platform']}", "login_at": now_iso()},
                  "/app-link/beveiliging")
    return device_id


@bp.route("/auth/login", methods=["POST"])
def login():
    data = body()
    email = (data.get("email") or "").strip().lower() if isinstance(data.get("email"), str) else ""
    password = data.get("password") if isinstance(data.get("password"), str) else ""
    if not email or not password:
        raise ApiError(422, "validation_failed", "Vul je e-mailadres en wachtwoord in.",
                       {k: "Vul dit veld in." for k, v in (("email", email), ("password", password)) if not v})
    device = _device(data)
    attempt = attempt_start(email, client_ip())
    if not attempt:
        raise ApiError(429, "too_many_attempts", "Te veel mislukte pogingen. Wacht 15 minuten en probeer het opnieuw.", headers={"Retry-After": "900"})
    user = db.one("SELECT * FROM users WHERE email = ? AND deleted_at IS NULL", (email,))
    ok = verify_password(user["password_hash"] if user else None, password) and bool(user)
    attempt_done(attempt, ok)
    if not ok:
        raise ApiError(401, "invalid_credentials", "Dat e-mailadres en wachtwoord passen niet bij elkaar.")
    problem = tenant_problem(user)
    if problem:
        raise problem
    if mfa.enabled(user):
        raw, expires = apitokens.start_challenge(user["id"], dumps(device))
        return jsonify({"mfa_required": True, "mfa_token": raw, "mfa_expires_at": expires,
                        "message": "Vul de code uit je authenticator-app in, of een herstelcode."}), 200
    device_id = _new_device_session(user, device)
    return _session_response(user, device_id, extra={"mfa_required": False})


@bp.route("/auth/mfa", methods=["POST"])
def login_mfa():
    data = body()
    try:
        ch = apitokens.challenge(data.get("mfa_token") if isinstance(data.get("mfa_token"), str) else "")
    except apitokens.TokenProblem as exc:
        raise ApiError(401, exc.code, exc.message)
    user = db.one("SELECT * FROM users WHERE id = ? AND deleted_at IS NULL", (ch["user_id"],))
    if not user or not mfa.enabled(user):
        raise ApiError(401, "mfa_token_invalid", "Deze inlogpoging is verlopen. Log opnieuw in met je wachtwoord.")
    if not apitokens.claim_attempt(ch):  # atomic: at most five codes per challenge, also with parallel requests
        raise ApiError(401, "mfa_token_invalid", "Deze inlogpoging is verlopen. Log opnieuw in met je wachtwoord.")
    attempt = attempt_start("mfa:" + user["email"], "mfa:" + client_ip())
    if not attempt:
        db.run("UPDATE api_mfa_challenges SET used_at = ? WHERE id = ?", (now_iso(), ch["id"]))
        raise ApiError(429, "too_many_attempts", "Te veel verkeerde codes. Wacht 15 minuten en log opnieuw in.", headers={"Retry-After": "900"})
    code = data.get("code") if isinstance(data.get("code"), str) else ""
    kind = mfa.verify(user, code)
    attempt_done(attempt, bool(kind))
    if not kind:
        raise ApiError(401, "invalid_code", "Deze code klopt niet of is al gebruikt. Probeer de volgende code uit je app.")
    if not apitokens.challenge_used(ch):
        raise ApiError(401, "mfa_token_invalid", "Deze inlogpoging is al gebruikt. Log opnieuw in met je wachtwoord.")
    problem = tenant_problem(user)
    if problem:
        raise problem
    if kind == "recovery":
        audit("mfa.recovery_used", f"user:{user['id']}", {"left": mfa.recovery_left(user["id"])}, org_id=NO_ORG, user_id=user["id"])
    device_id = _new_device_session(user, json.loads(ch["device_json"]), second_factor=kind)
    return _session_response(user, device_id, extra={"second_factor": kind, "recovery_codes_left": mfa.recovery_left(user["id"])})


@bp.route("/auth/refresh", methods=["POST"])
def refresh():
    data = body()
    raw = data.get("refresh_token") if isinstance(data.get("refresh_token"), str) else ""
    try:
        tokens, device = apitokens.rotate(raw)
    except apitokens.TokenProblem as exc:
        if exc.code == "refresh_token_reused":
            dev = db.one("SELECT d.* FROM api_devices d JOIN api_refresh_tokens r ON r.device_id = d.id WHERE r.token_hash = ?",
                         (sha256(raw),))
            if dev:
                audit("api.refresh_reuse", f"user:{dev['user_id']}", {"device": dev["id"]}, org_id=NO_ORG, user_id=dev["user_id"])
        raise ApiError(401, exc.code, exc.message)
    tokens.pop("_refresh_id", None)
    return jsonify({**tokens, "device_id": device["id"]})


@bp.route("/auth/logout", methods=["POST"])
@tenant_api
def logout():
    apitokens.revoke_device(g.api_device["id"], "logout")
    audit("api.logout", f"user:{g.api_user['id']}", {"device": g.api_device["id"]}, org_id=NO_ORG)
    return "", 204


def device_json(d, current_id=None):
    return {"id": d["id"], "name": d["device_name"], "platform": d["platform"], "app_version": d["app_version"],
            "created_at": d["created_at"], "last_seen_at": d["last_seen_at"], "second_factor": bool(d["mfa_at"]),
            "current": d["id"] == current_id}


@bp.route("/auth/devices", methods=["GET"])
@tenant_api
def devices():
    return jsonify({"items": [device_json(d, g.api_device["id"]) for d in apitokens.devices(g.api_user["id"])]})


@bp.route("/auth/devices/<int:device_id>", methods=["DELETE"])
@tenant_api
def revoke_device(device_id):
    d = db.one("SELECT * FROM api_devices WHERE id = ? AND user_id = ? AND revoked_at IS NULL", (device_id, g.api_user["id"]))
    if not d:
        raise ApiError(404, "not_found", "Dit apparaat bestaat niet of is al afgemeld.")
    apitokens.revoke_device(device_id, "revoked_by_user")
    audit("api.device_revoked", f"user:{g.api_user['id']}", {"device": device_id}, org_id=NO_ORG)
    return "", 204


# ------------------------------------------------------------ invitations (anti-phishing check, accept)

def _invite(raw):
    d = services.deposit_by_invite(raw)
    if not d:
        raise ApiError(410, "invite_expired", "Deze link is verlopen of al gebruikt. Vraag je verhuurder om een nieuwe uitnodiging.")
    return d


@bp.route("/invites/<token>", methods=["GET"])
def invite(token):
    raw = token
    d = _invite(raw)
    org = db.one("SELECT name FROM organizations WHERE id = ?", (d["org_id"],))
    prop = db.one("SELECT * FROM properties WHERE id = ?", (d["property_id"],))
    tenant = db.one("SELECT * FROM tenants WHERE id = ?", (d["tenant_id"],))
    existing = db.one("SELECT id FROM users WHERE lower(email) = lower(?) AND password_hash IS NOT NULL", (tenant["email"],))
    r = rules.for_deposit(d)
    return jsonify({
        "landlord": {"name": org["name"]},
        "address": {"street": prop["address"], "postcode": prop["postcode"], "city": prop["city"]},
        "amount": money(d["amount_cents"]), "reference": d["reference"], "region": d["region"], "term": r.term,
        "holding": d["holding"], "tenant": {"name": tenant["name"], "email": tenant["email"]},
        "existing_account": bool(existing), "expires_at": d["invite_expires_at"],
        "check": "Controleer dat de naam van je verhuurder, het adres, het bedrag en het kenmerk kloppen met je huurcontract. "
                 "Klopt iets niet? Ga niet verder en bel je verhuurder op een nummer dat je zelf opzoekt. Depiqo vraagt nooit om je bankcode.",
    })


@bp.route("/invites/<token>/accept", methods=["POST"])
def accept_invite(token):
    """Not idempotent by key (there may be no user yet): the invitation itself is single use. After a lost answer
    the tenant logs in with the password just chosen."""
    raw = token
    data = body()
    d = _invite(raw)
    true_field(data, "confirm_details", "Bevestig dat de naam van je verhuurder, het adres, het bedrag en het kenmerk kloppen.")
    tenant = db.one("SELECT * FROM tenants WHERE id = ?", (d["tenant_id"],))
    existing = db.one("SELECT * FROM users WHERE lower(email) = lower(?) AND password_hash IS NOT NULL", (tenant["email"],))
    if existing:
        if not g.api_user and not g.api_token_problem:
            if existing["is_staff"] or not db.scalar("SELECT 1 FROM tenants WHERE user_id = ?", (existing["id"],)):
                raise ApiError(409, "use_web", "Je hebt al een Depiqo-account. Open de uitnodiging op de website en log daar in.",
                               {"url": f"{services.base_url()}/t/{raw}"})
            raise ApiError(409, "login_required", "Er bestaat al een account met dit e-mailadres. Log eerst in en accepteer de uitnodiging daarna.")
        user = require_user()
        if user["id"] != existing["id"]:
            raise ApiError(403, "invite_for_other_account", "Deze uitnodiging is voor een ander e-mailadres.")
        try:
            uid, dep = services.accept_invite(raw, existing_user_id=user["id"])
        except services.WorkflowError as exc:
            raise ApiError(409, "invite_not_accepted", str(exc))
        audit("tenant.joined", f"deposit:{dep['pid']}", {"via": "app"}, org_id=dep["org_id"], user_id=uid)
        return jsonify({"deposit_pid": dep["pid"], "status": dep["status"]})
    password = data.get("password") if isinstance(data.get("password"), str) else ""
    problem = password_problem(password, tenant["email"])
    if problem:
        raise field_error("password", problem, "weak_password")
    device = _device(data)
    try:
        uid, dep = services.accept_invite(raw, password=password)
    except services.WorkflowError as exc:
        raise ApiError(409, "invite_not_accepted", str(exc))
    audit("tenant.joined", f"deposit:{dep['pid']}", {"via": "app"}, org_id=dep["org_id"], user_id=uid)
    user = db.one("SELECT * FROM users WHERE id = ?", (uid,))
    device_id = apitokens.create_device(uid, device, client_ip())
    audit("api.login", f"user:{uid}", {"device": device_id, "platform": device["platform"], "via": "invite"}, org_id=NO_ORG, user_id=uid)
    return _session_response(user, device_id, status=201, extra={"deposit_pid": dep["pid"], "status": dep["status"]})


# ------------------------------------------------------------ push tokens

EXPO_TOKEN = re.compile(r"^(ExponentPushToken|ExpoPushToken)\[[A-Za-z0-9_\-]{10,200}\]$")


@bp.route("/devices/push-token", methods=["POST"])
@tenant_api
def push_token():
    data = body()
    tok = str_field(data, "token", max_len=260)
    platform = data.get("platform")
    if not EXPO_TOKEN.match(tok):
        raise field_error("token", "Dit is geen geldige Expo-pushtoken.")
    if platform not in ("ios", "android"):
        raise field_error("platform", "Platform is ios of android.")
    uid, device_id = g.api_user["id"], g.api_device["id"]
    existing = db.one("SELECT * FROM push_tokens WHERE token = ?", (tok,))
    if existing and existing["user_id"] != uid:
        # 0.6.1: a token only moves to another account when the session it belonged to has ended
        old_device = db.one("SELECT revoked_at FROM api_devices WHERE id = ?", (existing["device_id"],)) if existing["device_id"] else None
        if old_device is not None and not old_device["revoked_at"]:
            raise ApiError(409, "push_token_in_use", "Deze pushtoken hoort bij een ander account dat nog is ingelogd op dit toestel. "
                                                     "Log daar eerst uit.")
    if existing:
        # The same phone, perhaps signed in as someone else now: the token moves to this user and device.
        db.run("UPDATE push_tokens SET user_id = ?, device_id = ?, platform = ?, active = 1, updated_at = ?, deactivated_at = NULL, "
               "deactivated_reason = NULL WHERE id = ?", (uid, device_id, platform, now_iso(), existing["id"]))
        tid = existing["id"]
    else:
        tid = db.run("INSERT INTO push_tokens (user_id, device_id, provider, token, platform, active, created_at, updated_at) "
                     "VALUES (?, ?, 'expo', ?, ?, 1, ?, ?)", (uid, device_id, tok, platform, now_iso(), now_iso()))
    # one active token per device session
    db.run("UPDATE push_tokens SET active = 0, deactivated_at = ?, deactivated_reason = 'vervangen' WHERE device_id = ? AND id != ? AND active = 1",
           (now_iso(), device_id, tid))
    audit("api.push_token", f"user:{uid}", {"device": device_id}, org_id=NO_ORG)
    return jsonify({"id": tid, "active": True}), 201

