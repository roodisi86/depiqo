"""JSON API for the Depiqo tenant app (0.6.0), under /api/v1.

Tenants only (Depiqo Wallet and Invest); business users keep the web app. Bearer tokens only: no
cookies, so no CSRF token. A mutating request that carries the web session cookie but no bearer
token is refused, so a browser can never act through the cookie. Errors are always
{"error": {"code", "message", "fields"}} with a fitting HTTP status. Money is integer cents with the
currency, dates are ISO 8601. Every rule lives in the existing services (services.py, investing.py):
this package only translates between HTTP and those functions.
"""
import base64
import hashlib
import json
import re
import sqlite3
from datetime import timedelta
from functools import wraps

from flask import Blueprint, current_app, g, jsonify, make_response, request

from .. import apitokens, db, i18n
from ..security import SESSION_COOKIE, client_ip
from ..util import now, sha256

bp = Blueprint("api", __name__, url_prefix="/api/v1")
API_VERSION = "0.6.1"
MUTATING = ("POST", "PUT", "PATCH", "DELETE")
IDEMPOTENCY_TTL = timedelta(hours=24)


class ApiError(Exception):
    def __init__(self, status, code, message, fields=None, headers=None):
        super().__init__(message)
        self.status, self.code, self.message, self.fields, self.headers = status, code, message, fields or {}, headers or {}


def current_lang():
    """Accept-Language (nl, fr, en) first, then the user's own preference, then Dutch."""
    if g.get("lang"):
        return g.lang
    return i18n.pick(request.headers.get("Accept-Language")) or (i18n.user_lang(g.api_user) if g.get("api_user") else i18n.DEFAULT)


def localize(code, message, fields):
    """Messages are written in Dutch. In French or English the catalog text for the error code is used; the
    specific Dutch text then travels along as 'detail' when it says more than the generic text."""
    lang = current_lang()
    if lang == "nl":
        return message, fields, None
    key = f"error.{code}"
    if not i18n.has(key):
        return message, fields, None
    text = i18n.t(key, lang)
    detail = message if message != i18n.raw(key, "nl") else None
    out = {k: (i18n.t(i18n.FIELD_KEYS[v], lang) if isinstance(v, str) and v in i18n.FIELD_KEYS else text if isinstance(v, str) else v)
           for k, v in (fields or {}).items()}
    return text, out, detail


def error_response(status, code, message, fields=None, headers=None):
    message, fields, detail = localize(code, message, fields)
    err = {"code": code, "message": message, "fields": fields or {}}
    if detail:
        err["detail"] = detail
    resp = jsonify({"error": err})
    resp.headers["Content-Language"] = current_lang()
    resp.status_code = status
    for k, v in (headers or {}).items():
        resp.headers[k] = v
    return resp


@bp.errorhandler(ApiError)
def _api_error(exc):
    return error_response(exc.status, exc.code, exc.message, exc.fields, exc.headers)


HTTP_ERRORS = {
    400: ("bad_request", "Dit verzoek klopt niet."),
    401: ("unauthorized", "Log in om verder te gaan."),
    403: ("forbidden", "Je hebt hier geen toegang toe."),
    404: ("not_found", "Niet gevonden."),
    405: ("method_not_allowed", "Deze methode kan hier niet."),
    413: ("file_too_large", "Het bestand is groter dan 10 MB."),
    415: ("unsupported_media_type", "Stuur JSON met Content-Type application/json."),
    429: ("rate_limited", "Te veel pogingen. Probeer het later opnieuw."),
    500: ("server_error", "Er ging iets mis bij Depiqo. Probeer het later opnieuw."),
}


def http_error(code):
    """Used by the app-wide error handlers for paths under /api/: the same JSON shape for 404, 405, 413 and 500."""
    c, msg = HTTP_ERRORS.get(code, ("error", "Er ging iets mis."))
    return error_response(code, c, msg)


# ------------------------------------------------------------ request guard

def _bearer():
    header = request.headers.get("Authorization") or ""
    if header[:7].lower() == "bearer ":
        return header[7:].strip()
    return None


def version_tuple(v):
    parts = re.findall(r"\d+", v or "")
    return tuple(int(p) for p in parts[:3]) + (0,) * (3 - min(len(parts), 3))


def minimum_version(platform):
    return current_app.config.get("APP_MIN_VERSION_IOS" if platform == "ios" else "APP_MIN_VERSION_ANDROID") or "0.0.0"


def check_app_version(platform, version):
    if platform in ("ios", "android") and version and version_tuple(version) < version_tuple(minimum_version(platform)):
        raise ApiError(426, "app_update_required", "Deze versie van de app wordt niet meer ondersteund. Werk de app bij.",
                       {"minimum_version": minimum_version(platform)})


@bp.before_request
def _guard():
    g.api_user = g.api_device = None
    g.api_token_problem = None
    g.lang = i18n.pick(request.headers.get("Accept-Language"))  # None: decided later from the user's preference
    raw = _bearer()
    if request.method in MUTATING and not raw and SESSION_COOKIE in request.cookies:
        raise ApiError(403, "cookie_auth_not_allowed",
                       "De app werkt niet met de inlog van de website. Stuur je toegangstoken mee in de Authorization-header.")
    if request.method in MUTATING and request.content_length and not (request.mimetype or "").endswith("json") \
            and request.mimetype != "multipart/form-data":
        raise ApiError(415, "unsupported_media_type", "Stuur JSON met Content-Type application/json.")
    if request.endpoint != "api.config":
        check_app_version(request.headers.get("X-App-Platform"), request.headers.get("X-App-Version"))
    if raw:
        try:
            g.api_user, g.api_device = apitokens.authenticate(raw)
        except apitokens.TokenProblem as exc:
            g.api_token_problem = exc
        else:
            apitokens.touch(g.api_device, client_ip(), request.headers.get("X-App-Version"))


@bp.after_request
def _no_store(resp):
    resp.headers["Cache-Control"] = "no-store"
    resp.headers.setdefault("Content-Language", current_lang())
    return resp


def tenant_problem(user):
    """Why this user may not use the app, or None. Staff and organisation members without a tenant role are refused."""
    if user["is_staff"]:
        return ApiError(403, "staff_not_allowed", "Medewerkers van Depiqo gebruiken de beheeromgeving op de website, niet de app.")
    if not db.scalar("SELECT 1 FROM tenants WHERE user_id = ?", (user["id"],)):
        if db.scalar("SELECT 1 FROM memberships WHERE user_id = ?", (user["id"],)):
            return ApiError(403, "not_a_tenant", "Deze app is voor huurders. Gebruik Depiqo Business op de website.")
        return ApiError(403, "not_a_tenant", "Er is nog geen borg aan dit account gekoppeld. Open de uitnodiging van je verhuurder.")
    return None


def require_user():
    if g.api_token_problem:
        p = g.api_token_problem
        raise ApiError(401, p.code, p.message, headers={"WWW-Authenticate": 'Bearer error="invalid_token"'})
    if not g.api_user:
        raise ApiError(401, "token_missing", "Log in om verder te gaan.", headers={"WWW-Authenticate": "Bearer"})
    problem = tenant_problem(g.api_user)
    if problem:
        raise problem
    g.tenant_ids = [r["id"] for r in db.all_("SELECT id FROM tenants WHERE user_id = ?", (g.api_user["id"],))]
    if not g.lang:
        g.lang = i18n.user_lang(g.api_user)
    g.user = g.api_user  # existing services and audit() read g.user
    return g.api_user


def tenant_api(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        require_user()
        return view(*args, **kwargs)
    return wrapper


# ------------------------------------------------------------ input

def body():
    if not request.content_length:
        return {}
    try:
        data = request.get_json(silent=True)
    except RecursionError:  # 0.6.1: deeply nested JSON is a bad request, not a server error
        raise ApiError(400, "invalid_json", "De body is geen geldig JSON-object.")
    if not isinstance(data, dict):
        raise ApiError(400, "invalid_json", "De body is geen geldig JSON-object.")
    return data


def field_error(field, message, code="validation_failed"):
    return ApiError(422, code, message, {field: message})


def int_field(data, name, required=True, minimum=None, maximum=None):
    v = data.get(name)
    if v is None:
        if required:
            raise field_error(name, "Vul dit veld in.")
        return None
    if not isinstance(v, int) or isinstance(v, bool):
        raise field_error(name, "Geef een geheel getal (bedragen in centen).")
    if (minimum is not None and v < minimum) or (maximum is not None and v > maximum):
        raise field_error(name, "Dit getal valt buiten de grenzen.")
    return v


def str_field(data, name, required=True, max_len=500):
    v = data.get(name)
    if v is None or (isinstance(v, str) and not v.strip()):
        if required:
            raise field_error(name, "Vul dit veld in.")
        return None
    if not isinstance(v, str):
        raise field_error(name, "Geef tekst.")
    return v.strip()[:max_len]


def true_field(data, name, message):
    if data.get(name) is not True:
        raise ApiError(422, f"{name}_required", message, {name: message})


# ------------------------------------------------------------ output

def money(cents):
    return None if cents is None else {"cents": int(cents), "currency": "EUR"}


def iso_date(value):
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)[:10]


def page_args(default=20):
    try:
        limit = int(request.args.get("limit", default))
    except ValueError:
        raise ApiError(400, "invalid_limit", "limit moet een getal zijn.")
    limit = max(1, min(limit, 100))
    raw = request.args.get("cursor")
    cursor = None
    if raw:
        bad = ApiError(400, "invalid_cursor", "Deze cursor is niet geldig.")
        if len(raw) > 200:
            raise bad
        try:
            cursor = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode())
        except (ValueError, UnicodeDecodeError, RecursionError):
            raise bad
        # 0.6.1: a flat list of small values only; integers fit in SQLite (0 <= n < 2^63)
        if not isinstance(cursor, list) or not 1 <= len(cursor) <= 3:
            raise bad
        for v in cursor:
            if isinstance(v, bool) or not isinstance(v, (int, str)):
                raise bad
            if isinstance(v, int) and not 0 <= v < 2 ** 63:
                raise bad
            if isinstance(v, str) and len(v) > 40:
                raise bad
    return limit, cursor


def make_cursor(values):
    return base64.urlsafe_b64encode(json.dumps(values, separators=(",", ":")).encode()).decode().rstrip("=")


def paged(rows, limit, key, render):
    """rows were fetched with limit + 1. key(row) gives the cursor values for the last row of the page."""
    items = rows[:limit]
    return {"items": [render(r) for r in items], "next_cursor": make_cursor(key(items[-1])) if len(rows) > limit and items else None}


# ------------------------------------------------------------ idempotency

def request_digest():
    """What makes two requests 'the same' for an Idempotency-Key. JSON: the body as sent. Multipart (0.6.1): the
    form fields and per file its field, name, type and SHA-256, because the boundary differs on every send."""
    head = request.method + " " + request.path + "\n"
    if request.mimetype == "multipart/form-data":
        parts = [f"f:{k}={v}" for k, v in sorted(request.form.items(multi=True))]
        for key, f in sorted(request.files.items(multi=True), key=lambda kv: kv[0]):
            content = f.stream.read()
            f.stream.seek(0)
            parts.append(f"file:{key}:{f.filename}:{f.mimetype}:{hashlib.sha256(content).hexdigest()}")
        return sha256(head + "\n".join(parts))
    return sha256(head + request.get_data(as_text=True))


def sandbox_only(view):
    """0.6.1: outside the sandbox the endpoint does not exist (404 before anything else, also before login)."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_app.config.get("SANDBOX") or current_app.config.get("ENV_NAME") == "production":
            raise ApiError(404, "not_found", "Niet gevonden.")
        return view(*args, **kwargs)
    return wrapper


def idempotent(required=False):
    """Honours the Idempotency-Key header: the same key with the same request returns the stored response for
    24 hours, without running the action again. The same key with a different request is refused. Only
    successful responses are stored; after an error a retry runs the action again (it changed nothing)."""
    def deco(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            key = request.headers.get("Idempotency-Key")
            if not key:
                if required:
                    raise ApiError(400, "idempotency_key_required", "Stuur een Idempotency-Key mee, zodat een herhaald verzoek niet dubbel wordt uitgevoerd.")
                return view(*args, **kwargs)
            if not re.fullmatch(r"[A-Za-z0-9_\-:.]{8,100}", key):
                raise ApiError(400, "invalid_idempotency_key", "De Idempotency-Key moet 8 tot 100 tekens zijn (letters, cijfers, - _ : .).")
            uid = g.api_user["id"]
            cutoff = (now() - IDEMPOTENCY_TTL).isoformat(timespec="seconds")
            db.run("DELETE FROM api_idempotency WHERE user_id = ? AND created_at < ?", (uid, cutoff))
            digest = request_digest()
            try:
                row_id = db.run("INSERT INTO api_idempotency (user_id, idem_key, method, path, request_hash, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                                (uid, key, request.method, request.path, digest, now().isoformat(timespec="seconds")))
            except sqlite3.IntegrityError:
                known = db.one("SELECT * FROM api_idempotency WHERE user_id = ? AND idem_key = ?", (uid, key))
                if not known or known["request_hash"] != digest:
                    raise ApiError(422, "idempotency_key_reused", "Deze Idempotency-Key is al gebruikt voor een ander verzoek.")
                if known["status_code"] is None:
                    raise ApiError(409, "idempotency_in_progress", "Dit verzoek wordt al verwerkt. Probeer het zo opnieuw.")
                resp = make_response(known["response_json"], known["status_code"])
                resp.mimetype = "application/json"
                resp.headers["Idempotent-Replayed"] = "true"
                return resp
            try:
                resp = make_response(view(*args, **kwargs))
            except BaseException:
                db.run("DELETE FROM api_idempotency WHERE id = ?", (row_id,))
                raise
            if 200 <= resp.status_code < 300 and resp.is_json:
                db.run("UPDATE api_idempotency SET status_code = ?, response_json = ? WHERE id = ?",
                       (resp.status_code, resp.get_data(as_text=True), row_id))
            else:
                db.run("DELETE FROM api_idempotency WHERE id = ?", (row_id,))
            return resp
        wrapper.idempotent = True
        wrapper.idempotency_required = required
        return wrapper
    return deco


from . import activity, auth, deposits, invest, me, support  # noqa: E402,F401  (routes register on bp)
