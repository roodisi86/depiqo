"""Authentication, sessions, CSRF, roles, organisation isolation and audit logging."""
import hmac
from datetime import timedelta
from functools import wraps
from urllib.parse import urlsplit

from flask import abort, current_app, flash, g, has_request_context, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from . import db
from .util import dumps, now, now_iso, parse_dt, sha256, token

SESSION_COOKIE = "dpq_session"
SESSION_IDLE = timedelta(hours=2)
SESSION_MAX = timedelta(hours=12)
MIN_PASSWORD = 12

ROLE_LABELS = {"admin": "Beheerder organisatie", "manager": "Vastgoedbeheerder",
               "finance": "Financieel medewerker", "viewer": "Alleen lezen"}

# What each role may do. Checked server-side on every write; the UI only hides buttons.
PERMISSIONS = {
    "deposit.view": {"admin", "manager", "finance", "viewer"},
    "deposit.edit": {"admin", "manager"},
    "deposit.confirm_receipt": {"admin", "finance"},
    "deposit.payout": {"admin", "finance"},
    "deposit.legal_hold": {"admin"},
    "document.upload": {"admin", "manager", "finance"},
    "settlement.edit": {"admin", "manager"},
    "dispute.resolve": {"admin", "manager"},
    "team.manage": {"admin"},
    "billing.view": {"admin", "finance"},
    "billing.issue": {"admin"},
    "settings.edit": {"admin"},
    "export": {"admin", "finance", "manager"},
    "deposit.remind": {"admin", "manager"},
    "deposit.import": {"admin"},           # imported external deposits start as declared receipts
    "reconciliation.view": {"admin", "finance"},
}


# ---------------------------------------------------------------- passwords

def hash_password(password):
    return generate_password_hash(password, method="scrypt")


_DUMMY_HASH = None


def verify_password(password_hash, password):
    """Always does the full scrypt work, so response time does not reveal whether an account exists."""
    global _DUMMY_HASH
    if not password_hash:
        if _DUMMY_HASH is None:
            _DUMMY_HASH = generate_password_hash("not-a-real-password", method="scrypt")
        check_password_hash(_DUMMY_HASH, password or "")
        return False
    return check_password_hash(password_hash, password)


def password_problem(password, email=""):
    if len(password or "") < MIN_PASSWORD:
        return f"Kies een wachtwoord van minstens {MIN_PASSWORD} tekens."
    if email and email.split("@")[0].lower() in password.lower():
        return "Gebruik je e-mailadres niet in je wachtwoord."
    if len(set(password)) < 6:
        return "Kies een wachtwoord met meer verschillende tekens."
    return None


# ---------------------------------------------------------------- rate limiting

def login_blocked(email, ip):
    since = (now() - timedelta(minutes=15)).isoformat(timespec="seconds")
    per_email = db.scalar("SELECT COUNT(*) FROM login_attempts WHERE email = ? AND ok = 0 AND at > ?", (email, since))
    per_ip = db.scalar("SELECT COUNT(*) FROM login_attempts WHERE ip = ? AND ok = 0 AND at > ?", (ip, since))
    return per_email >= 5 or per_ip >= 30


def record_login_attempt(email, ip, ok):
    db.run("INSERT INTO login_attempts (email, ip, ok, at) VALUES (?, ?, ?, ?)", (email, ip, 1 if ok else 0, now_iso()))


MAX_FAILS_PER_KEY = 5
MAX_FAILS_PER_IP = 30


def attempt_start(email, ip):
    """Reserves an attempt before the password or code is checked (0.6.1). The attempt is written first, counted
    as a failure, and only then are the failures counted, so parallel requests can never get past the limit
    together. Returns the attempt id, or None when blocked (the reserved row is removed again, so hammering
    a blocked account does not extend the block)."""
    aid = db.run("INSERT INTO login_attempts (email, ip, ok, at) VALUES (?, ?, 0, ?)", (email, ip, now_iso()))
    since = (now() - timedelta(minutes=15)).isoformat(timespec="seconds")
    per_email = db.scalar("SELECT COUNT(*) FROM login_attempts WHERE email = ? AND ok = 0 AND at > ?", (email, since))
    per_ip = db.scalar("SELECT COUNT(*) FROM login_attempts WHERE ip = ? AND ok = 0 AND at > ?", (ip, since))
    if per_email > MAX_FAILS_PER_KEY or per_ip > MAX_FAILS_PER_IP:
        db.run("DELETE FROM login_attempts WHERE id = ?", (aid,))
        return None
    return aid


def attempt_done(attempt_id, ok):
    """A successful attempt stops counting as a failure."""
    if ok and attempt_id:
        db.run("UPDATE login_attempts SET ok = 1 WHERE id = ?", (attempt_id,))


# ---------------------------------------------------------------- sessions

def client_ip():
    # With TRUST_PROXY, ProxyFix has already set remote_addr from the proxy's own X-Forwarded-For entry.
    return request.remote_addr or ""


def start_session(user_id, response, mfa=False):
    """mfa: the user passed the second factor in this login (stored per session as mfa_at)."""
    raw = token()
    created = now()
    org = db.one("SELECT org_id FROM memberships WHERE user_id = ? ORDER BY id LIMIT 1", (user_id,))
    db.run("INSERT INTO sessions (token_hash, user_id, csrf_token, active_org_id, created_at, last_seen_at, expires_at, ip, user_agent, mfa_at) "
           "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
           (sha256(raw), user_id, token(), org["org_id"] if org else None, created.isoformat(timespec="seconds"),
            created.isoformat(timespec="seconds"), (created + SESSION_MAX).isoformat(timespec="seconds"),
            client_ip(), (request.headers.get("User-Agent") or "")[:200], created.isoformat(timespec="seconds") if mfa else None))
    db.run("UPDATE users SET last_login_at = ? WHERE id = ?", (now_iso(), user_id))
    response.set_cookie(SESSION_COOKIE, raw, httponly=True, samesite="Lax",
                        secure=current_app.config["SECURE_COOKIES"], max_age=int(SESSION_MAX.total_seconds()), path="/")
    return response


def end_other_sessions(user_id, mark_current_mfa=None):
    """After a change to the second factor: every other session of this user ends. mark_current_mfa
    True/False sets or clears mfa_at on the current session."""
    current = g.session["id"] if g.get("session") else -1
    db.run("DELETE FROM sessions WHERE user_id = ? AND id != ?", (user_id, current))
    from . import apitokens
    apitokens.revoke_all(user_id, "security_change")  # app sessions end too
    if mark_current_mfa is not None and current != -1:
        db.run("UPDATE sessions SET mfa_at = ? WHERE id = ?", (now_iso() if mark_current_mfa else None, current))


def end_session(response):
    raw = request.cookies.get(SESSION_COOKIE)
    if raw:
        db.run("DELETE FROM sessions WHERE token_hash = ?", (sha256(raw),))
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


def load_session():
    """Runs before every request: sets g.user, g.session, g.membership, g.org, g.tenant_ids."""
    g.user = g.session = g.membership = g.org = None
    g.tenant_ids = []
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        return
    sess = db.one("SELECT * FROM sessions WHERE token_hash = ?", (sha256(raw),))
    if not sess:
        return
    t = now()
    if parse_dt(sess["expires_at"]) < t or parse_dt(sess["last_seen_at"]) + SESSION_IDLE < t:
        db.run("DELETE FROM sessions WHERE id = ?", (sess["id"],))
        return
    db.run("UPDATE sessions SET last_seen_at = ? WHERE id = ?", (t.isoformat(timespec="seconds"), sess["id"]))
    g.session = sess
    g.user = db.one("SELECT * FROM users WHERE id = ?", (sess["user_id"],))
    if sess["active_org_id"]:
        g.membership = db.one("SELECT * FROM memberships WHERE user_id = ? AND org_id = ?", (g.user["id"], sess["active_org_id"]))
        if g.membership:
            g.org = db.one("SELECT * FROM organizations WHERE id = ?", (sess["active_org_id"],))
    g.tenant_ids = [r["id"] for r in db.all_("SELECT id FROM tenants WHERE user_id = ?", (g.user["id"],))]


# ---------------------------------------------------------------- CSRF

def csrf_token():
    """Logged in: the token stored with the server-side session. Anonymous (login, invitations):
    a random token kept in Flask's signed session cookie, so it is per browser and works across workers."""
    if g.get("session"):
        return g.session["csrf_token"]
    if "anon_csrf" not in session:
        session["anon_csrf"] = token()
    return session["anon_csrf"]


def check_csrf():
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return
    if request.endpoint and request.endpoint.startswith("webhooks."):
        return  # signed with HMAC instead
    sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token") or ""
    if not hmac.compare_digest(sent, csrf_token()):
        abort(400, description="Het formulier is verlopen. Laad de pagina opnieuw en probeer het nog eens.")
    # Defence in depth: same-origin check on the Origin header when present.
    origin = request.headers.get("Origin")
    if origin and origin != "null":
        allowed = {_origin_of(current_app.config.get("BASE_URL") or ""), _origin_of(request.host_url)}
        if _origin_of(origin) not in allowed:
            abort(400, description="Verzoek van een onbekende herkomst.")


def _origin_of(url):
    """scheme://host[:port], lower case, default ports removed. Exact comparison, no prefix matching."""
    parts = urlsplit(url.strip())
    if not parts.scheme or not parts.hostname:
        return None
    port = parts.port
    default = {"http": 80, "https": 443}.get(parts.scheme)
    host = parts.hostname.lower()
    return f"{parts.scheme.lower()}://{host}" + (f":{port}" if port and port != default else "")


# ---------------------------------------------------------------- guards

def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not g.user:
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)
    return wrapper


def org_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not g.user:
            return redirect(url_for("auth.login", next=request.path))
        if not g.membership:
            if g.tenant_ids:
                return redirect(url_for("wallet.home"))
            abort(403)
        return view(*args, **kwargs)
    return wrapper


def can(permission):
    return bool(g.membership) and g.membership["role"] in PERMISSIONS[permission]


def require(permission):
    if not can(permission):
        abort(403)


def two_factor_enabled(user=None):
    user = user if user is not None else g.get("user")
    return bool(user and user["totp_enabled_at"] and user["totp_secret"])


def should_enable_2fa():
    """Staff and organisation admins see a banner until they turn on two-factor authentication."""
    if not g.get("user") or two_factor_enabled():
        return False
    return bool(g.user["is_staff"]) or bool(g.get("membership") and g.membership["role"] == "admin")


def staff_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not g.user:
            return redirect(url_for("auth.login", next=request.path))
        if not g.user["is_staff"]:
            abort(404)
        if current_app.config.get("REQUIRE_2FA_FOR_STAFF"):
            if not two_factor_enabled():
                flash("Zet eerst twee-stapsverificatie aan. Daarna kun je de beheeromgeving gebruiken.", "error")
                return redirect(url_for("auth.security"))
            if not g.session["mfa_at"]:
                # Logged in with the password only (before 2FA was on): this session never passed the second factor.
                flash("Log opnieuw in met je code om de beheeromgeving te gebruiken.", "error")
                return redirect(url_for("auth.security"))
        return view(*args, **kwargs)
    return wrapper


def tenant_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not g.user:
            return redirect(url_for("auth.login", next=request.path))
        if not g.tenant_ids:
            abort(403)
        return view(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------- audit

NO_ORG = object()  # audit marker: this row belongs to no organisation, even if the user is also a member of one (Invest)


def audit(action, target=None, data=None, org_id=None, user_id=None):
    if org_id is NO_ORG:
        org_value = None
    else:
        org_value = org_id if org_id is not None else (g.org["id"] if g.get("org") else None)
    db.run("INSERT INTO audit_log (at, org_id, user_id, action, target, ip, data_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
           (now_iso(), org_value,
            user_id if user_id is not None else (g.user["id"] if g.get("user") else None),
            action, target, client_ip() if has_request_context() else None, dumps(data) if data else None))
