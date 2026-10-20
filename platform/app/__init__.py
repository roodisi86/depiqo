"""Depiqo platform: Flask application factory."""
import os
import secrets

from flask import Flask, g, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix

from . import db
from . import states as S
from .partners import partner_status
from .security import ROLE_LABELS, can, check_csrf, csrf_token, load_session, should_enable_2fa, two_factor_enabled
from .util import date_nl, datetime_nl, eur, format_iban, pct


ENVIRONMENTS = ("development", "staging", "production")


def create_app(overrides=None):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app = Flask(__name__, template_folder="templates", static_folder="static")
    env = os.environ.get("DEPIQO_ENV", "development")
    if env not in ENVIRONMENTS:
        raise RuntimeError(f"DEPIQO_ENV must be one of {', '.join(ENVIRONMENTS)}.")
    # 0.6.0: production never runs sandbox partners, whatever DEPIQO_SANDBOX says. Staging may (and shows STAGING).
    sandbox_on = os.environ.get("DEPIQO_SANDBOX", "1") == "1" and env != "production"
    app.config.update(
        ENV_NAME=env,
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        DATABASE_PATH=os.environ.get("DATABASE_PATH", os.path.join(root, "instance", "depiqo.sqlite3")),
        STORAGE_DIR=os.environ.get("STORAGE_DIR", os.path.join(root, "instance", "storage")),
        BASE_URL=os.environ.get("BASE_URL", "http://localhost:5000"),
        SECURE_COOKIES=env in ("staging", "production"),
        TRUST_PROXY=os.environ.get("TRUST_PROXY") == "1",
        SANDBOX=sandbox_on,
        # Explicit partner choice. 'sandbox' only works while SANDBOX is on; empty or unknown = no partner (fail closed).
        BANK_PARTNER=os.environ.get("BANK_PARTNER", "sandbox" if sandbox_on else ""),
        DISPATCH_INLINE=os.environ.get("DISPATCH_INLINE", "1") == "1",   # try to send a bank instruction right after commit
        MAX_INSTRUCTION_ATTEMPTS=int(os.environ.get("MAX_INSTRUCTION_ATTEMPTS", "5")),
        RELEASE_CONFIRM_DAYS=int(os.environ.get("RELEASE_CONFIRM_DAYS", "5")),
        DECLARED_MAX_DAYS=int(os.environ.get("DECLARED_MAX_DAYS", "14")),
        REQUIRE_2FA_FOR_STAFF=os.environ.get("REQUIRE_2FA_FOR_STAFF", "1" if env in ("staging", "production") else "0") == "1",
        IMPORT_MAX_ROWS=5000,
        IMPORT_MAX_BYTES=2 * 1024 * 1024,
        BANK_WEBHOOK_SECRET=os.environ.get("BANK_WEBHOOK_SECRET", "sandbox-secret-change-me"),
        # 0.5.0 Depiqo Invest: the investment partner, chosen like BANK_PARTNER and failing closed the same way.
        INVEST_PARTNER=os.environ.get("INVEST_PARTNER", "sandbox" if sandbox_on else ""),
        INVEST_WEBHOOK_SECRET=os.environ.get("INVEST_WEBHOOK_SECRET", "sandbox-invest-secret-change-me"),
        SMTP_HOST=os.environ.get("SMTP_HOST"),
        SMTP_PORT=os.environ.get("SMTP_PORT", "587"),
        SMTP_USER=os.environ.get("SMTP_USER"),
        SMTP_PASSWORD=os.environ.get("SMTP_PASSWORD"),
        MAIL_FROM=os.environ.get("MAIL_FROM", "Depiqo <no-reply@getdepiqo.com>"),
        MAX_CONTENT_LENGTH=12 * 1024 * 1024,
        MAX_UPLOAD_BYTES=10 * 1024 * 1024,
        # 0.6.0 tenant app (JSON API under /api/v1)
        APP_MIN_VERSION_IOS=os.environ.get("APP_MIN_VERSION_IOS", "1.0.0"),
        APP_MIN_VERSION_ANDROID=os.environ.get("APP_MIN_VERSION_ANDROID", "1.0.0"),
        SUPPORT_EMAIL=os.environ.get("SUPPORT_EMAIL", "support@getdepiqo.com"),
        PRIVACY_URL=os.environ.get("PRIVACY_URL", "https://getdepiqo.com/privacy"),
        TERMS_URL=os.environ.get("TERMS_URL", "https://getdepiqo.com/voorwaarden"),
        APP_IOS_TEAM_ID=os.environ.get("APP_IOS_TEAM_ID", ""),
        APP_BUNDLE_ID=os.environ.get("APP_BUNDLE_ID", "com.getdepiqo.app"),
        ANDROID_SHA256_CERT=os.environ.get("ANDROID_SHA256_CERT", ""),
        # Push via Expo. Off in sandbox and development: messages go to the outbox as 'skipped' (note 'sandbox').
        PUSH_SEND=os.environ.get("PUSH_SEND", "1" if env == "production" and not sandbox_on else "0") == "1",
        EXPO_ACCESS_TOKEN=os.environ.get("EXPO_ACCESS_TOKEN"),
    )
    if overrides:
        app.config.update(overrides)
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                      SESSION_COOKIE_SECURE=app.config["SECURE_COOKIES"], SESSION_COOKIE_NAME="dpq_flash")
    if env == "production":
        app.config["SANDBOX"] = False  # also when an override tried to switch it on
    if env in ("staging", "production"):  # hosted: the same checks; staging may run the sandbox and shows STAGING
        if not os.environ.get("SECRET_KEY"):
            raise RuntimeError(f"SECRET_KEY must be set in {env}.")
        if app.config["BANK_WEBHOOK_SECRET"] == "sandbox-secret-change-me":
            raise RuntimeError(f"BANK_WEBHOOK_SECRET must be set in {env}.")
        if app.config["INVEST_PARTNER"] not in ("", "sandbox") and app.config["INVEST_WEBHOOK_SECRET"] == "sandbox-invest-secret-change-me":
            raise RuntimeError(f"INVEST_WEBHOOK_SECRET must be set in {env} for a real investment partner.")
        if not (os.environ.get("BASE_URL") or "").startswith("https://"):
            raise RuntimeError(f"BASE_URL must be set to the public https:// address in {env}.")

    os.makedirs(os.path.dirname(app.config["DATABASE_PATH"]), exist_ok=True)
    if not app.config["SECRET_KEY"]:
        # Development: one stable key per installation, shared by all worker processes.
        key_file = os.path.join(os.path.dirname(app.config["DATABASE_PATH"]), "secret_key")
        try:
            fd = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(secrets.token_hex(32))
        except FileExistsError:
            pass
        with open(key_file) as f:
            app.config["SECRET_KEY"] = f.read().strip()
    if app.config["TRUST_PROXY"]:
        # Exactly one trusted proxy in front (the host's load balancer): take the address it saw.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    os.makedirs(app.config["STORAGE_DIR"], exist_ok=True)
    db.migrate(app.config["DATABASE_PATH"], os.path.join(root, "migrations"))

    from . import api
    from .views import admin, applinks, auth, business, invest, support_admin, wallet, webhooks
    app.register_blueprint(api.bp)
    app.register_blueprint(applinks.bp)
    app.register_blueprint(support_admin.bp)
    app.register_blueprint(invest.bp)
    app.register_blueprint(invest.staff_bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(business.bp)
    app.register_blueprint(wallet.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(webhooks.bp)
    app.teardown_appcontext(db.close_db)

    @app.before_request
    def _before():
        g.nonce = secrets.token_urlsafe(16)
        if request.path.startswith("/api/"):
            # The app API never reads the web session cookie and needs no CSRF token: bearer tokens only (see app/api).
            g.user = g.session = g.membership = g.org = None
            g.tenant_ids = []
            return
        load_session()
        check_csrf()

    @app.after_request
    def _headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self' https://fonts.googleapis.com; "
            "font-src https://fonts.gstatic.com; script-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'self'")
        if app.config["SECURE_COOKIES"]:
            resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if request.path.startswith(("/app", "/wallet", "/admin", "/api/")):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(405)
    @app.errorhandler(413)
    def _error(err):
        code = getattr(err, "code", 500)
        if request.path.startswith("/api/"):
            return api.http_error(code)
        titles = {400: "Dat ging niet goed", 403: "Geen toegang", 404: "Niet gevonden", 413: "Bestand te groot"}
        texts = {403: "Je hebt geen rechten voor deze pagina of actie.", 404: "Deze pagina bestaat niet of je hebt er geen toegang toe.",
                 413: "Het bestand is groter dan 10 MB."}
        text = texts.get(code) or getattr(err, "description", "") or "Probeer het opnieuw."
        return render_template("error.html", title=titles.get(code, "Fout"), text=text, code=code), code

    @app.errorhandler(500)
    def _server_error(err):
        if request.path.startswith("/api/"):
            return api.http_error(500)
        return render_template("error.html", title="Fout", text="Er ging iets mis. Probeer het later opnieuw.", code=500), 500

    from . import investing as _investing
    from . import providers as _providers
    from . import services as _services

    def _display_status(d, tenant=False):
        return _services.display_status(d, tenant)

    def _assurance(d):
        return _services.assurance(d)

    def _bps(v):
        """Basis points as a Dutch percentage with two decimals: 25 -> '0,25%'."""
        return f"{(v or 0) / 100:.2f}%".replace(".", ",")

    def _units(u):
        return f"{(u or 0) / 10000:,.4f}".replace(",", " ").replace(".", ",").replace(" ", ".")

    app.jinja_env.filters.update(eur=eur, date_nl=date_nl, datetime_nl=datetime_nl, iban=format_iban, pct=pct, bps=_bps, units=_units)
    app.jinja_env.globals.update(
        csrf_token=csrf_token, can=can, S=S, LABELS=S.LABELS, TENANT_LABELS=S.TENANT_LABELS, TONE=S.TONE,
        ROLE_LABELS=ROLE_LABELS, sandbox=lambda: app.config["SANDBOX"], display_status=_display_status, assurance=_assurance,
        EVIDENCE=S.EVIDENCE, should_enable_2fa=should_enable_2fa, two_factor_enabled=two_factor_enabled, partner_status=partner_status,
        PROVIDER_KINDS=_providers.PROVIDER_KINDS, provider_label=_providers.label, region_warnings=_providers.region_warnings,
        evidence_hint=_providers.evidence_hint, GUARANTEE_KINDS=_providers.GUARANTEE_KINDS, NO_TENANT_PAYMENT=_providers.NO_TENANT_PAYMENT,
        INVEST_SEPARATION=_investing.SEPARATION_TEXT, INVEST_RISK=_investing.RISK_TEXT,
        invest_visibility=lambda: _investing.visibility(g.user["id"]) if g.get("user") and g.get("tenant_ids") else "hidden")
    return app
