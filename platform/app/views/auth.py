"""Login, logout, staff invitations and tenant invitations."""
from datetime import timedelta
from urllib.parse import urlsplit

import time

from flask import Blueprint, abort, flash, g, make_response, redirect, render_template, request, session, url_for

from .. import apitokens, db, mfa, services
from ..security import (attempt_done, attempt_start, audit, client_ip, end_other_sessions, end_session, hash_password, login_blocked,
                        login_required, password_problem, record_login_attempt, start_session, two_factor_enabled, verify_password)
from ..partners import send_mail
from ..util import now, now_iso, parse_dt, sha256, token

bp = Blueprint("auth", __name__)


def home_for_user():
    if g.user and g.user["is_staff"] and not g.membership:
        return url_for("admin.home")
    if g.membership:
        return url_for("business.dashboard")
    if g.tenant_ids:
        return url_for("wallet.home")
    return url_for("auth.login")


def safe_next(target):
    """Only a local path on this site. Browsers strip tabs and newlines and treat \\ as /, so reject those."""
    if not target or any(ord(ch) < 33 or ch == "\\" for ch in target):
        return None
    if not target.startswith("/") or target.startswith("//"):
        return None
    parts = urlsplit(target)
    if parts.scheme or parts.netloc:
        return None
    return target


@bp.route("/")
def index():
    if not g.user:
        return redirect(url_for("auth.login"))
    return redirect(home_for_user())


@bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    email = ""
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        ip = client_ip()
        attempt = attempt_start(email, ip)
        if not attempt:
            error = "Te veel mislukte pogingen. Wacht 15 minuten en probeer het opnieuw."
        else:
            user = db.one("SELECT * FROM users WHERE email = ? AND deleted_at IS NULL", (email,))
            ok = verify_password(user["password_hash"] if user else None, password) and bool(user)
            attempt_done(attempt, ok)
            if ok:
                target = safe_next(request.args.get("next")) or url_for("auth.index")
                if two_factor_enabled(user):
                    return _start_second_step(user, target)
                audit("login", f"user:{user['id']}", user_id=user["id"], org_id=None)
                return start_session(user["id"], make_response(redirect(target)))
            error = "Dat e-mailadres en wachtwoord passen niet bij elkaar."
    return render_template("auth/login.html", error=error, email=email)


MFA_SECONDS = 300


def _start_second_step(user, target):
    """Password was right; the session only starts after the code. The pending login lives in the
    signed Flask cookie for five minutes and is bound to this browser."""
    session["mfa"] = {"uid": user["id"], "next": target, "exp": int(time.time()) + MFA_SECONDS}
    return redirect(url_for("auth.login_code"))


@bp.route("/login/code", methods=["GET", "POST"])
def login_code():
    pending = session.get("mfa")
    if not pending or pending.get("exp", 0) < time.time():
        session.pop("mfa", None)
        return redirect(url_for("auth.login"))
    user = db.one("SELECT * FROM users WHERE id = ?", (pending["uid"],))
    if not user or not two_factor_enabled(user):
        session.pop("mfa", None)
        return redirect(url_for("auth.login"))
    error = None
    if request.method == "POST":
        attempt = attempt_start("mfa:" + user["email"], "mfa:" + client_ip())
        if not attempt:
            error = "Te veel verkeerde codes. Wacht 15 minuten en log opnieuw in."
            session.pop("mfa", None)
        else:
            kind = mfa.verify(user, request.form.get("code"))
            attempt_done(attempt, bool(kind))
            if kind:
                session.pop("mfa", None)
                audit("login", f"user:{user['id']}", {"second_factor": kind}, user_id=user["id"], org_id=None)
                if kind == "recovery":
                    audit("mfa.recovery_used", f"user:{user['id']}", {"left": mfa.recovery_left(user["id"])}, user_id=user["id"], org_id=None)
                return start_session(user["id"], make_response(redirect(safe_next(pending.get("next")) or url_for("auth.index"))), mfa=True)
            error = "Deze code klopt niet of is al gebruikt. Probeer de volgende code uit je app."
    return render_template("auth/login_code.html", error=error)


# ------------------------------------------------------------ account security (2FA)

def _security_page(**extra):
    user = db.one("SELECT * FROM users WHERE id = ?", (g.user["id"],))
    pending = user["totp_pending_secret"]
    return render_template("account/security.html", user=user, enabled=two_factor_enabled(user), pending=pending,
                           devices=apitokens.devices(user["id"]),
                           uri=mfa.otpauth_uri(pending, user["email"]) if pending else None,
                           grouped=mfa.group(pending) if pending else None,
                           left=mfa.recovery_left(user["id"]) if two_factor_enabled(user) else 0, **extra)


@bp.route("/account/beveiliging", methods=["GET", "POST"])
@login_required
def security():
    if request.method == "GET":
        return _security_page()
    action = request.form.get("action")
    user = db.one("SELECT * FROM users WHERE id = ?", (g.user["id"],))
    if action == "start":
        if two_factor_enabled(user):
            flash("Twee-stapsverificatie staat al aan.", "ok")
            return redirect(url_for("auth.security"))
        mfa.start_setup(user["id"])
        return redirect(url_for("auth.security"))
    if action == "confirm":
        codes = mfa.confirm_setup(user, request.form.get("code"))
        if not codes:
            return _security_page(error="Deze code klopt niet. Controleer de tijd op je telefoon en probeer de volgende code.")
        end_other_sessions(user["id"], mark_current_mfa=True)  # sessions opened with the password only end now
        audit("mfa.enabled", f"user:{user['id']}", user_id=user["id"])
        return _security_page(codes=codes, message="Twee-stapsverificatie staat aan. Bewaar je herstelcodes op een veilige plek.")
    if action in ("disable", "codes"):
        if not two_factor_enabled(user) or not mfa.verify(user, request.form.get("code")):
            return _security_page(error="Vul een geldige code uit je app in (of een herstelcode).")
        if action == "disable":
            mfa.disable(user["id"])
            end_other_sessions(user["id"], mark_current_mfa=False)
            audit("mfa.disabled", f"user:{user['id']}", user_id=user["id"])
            flash("Twee-stapsverificatie staat uit.", "ok")
            return redirect(url_for("auth.security"))
        codes = mfa.regenerate_recovery_codes(user["id"])
        end_other_sessions(user["id"])
        audit("mfa.recovery_regenerated", f"user:{user['id']}", user_id=user["id"])
        return _security_page(codes=codes, message="Nieuwe herstelcodes gemaakt. De oude werken niet meer.")
    if action == "cancel":
        db.run("UPDATE users SET totp_pending_secret = NULL WHERE id = ?", (user["id"],))
        return redirect(url_for("auth.security"))
    if action == "revoke_device":
        device_id = request.form.get("device_id", type=int)
        if not db.one("SELECT id FROM api_devices WHERE id = ? AND user_id = ? AND revoked_at IS NULL", (device_id, user["id"])):
            abort(404)
        apitokens.revoke_device(device_id, "revoked_on_web")
        audit("api.device_revoked", f"user:{user['id']}", {"device": device_id, "via": "web"}, user_id=user["id"])
        flash("Het apparaat is afgemeld. De app op dat apparaat vraagt opnieuw om in te loggen.", "ok")
        return redirect(url_for("auth.security"))
    abort(400)


@bp.route("/logout", methods=["POST"])
def logout():
    if g.user:
        audit("logout", f"user:{g.user['id']}")
    return end_session(make_response(redirect(url_for("auth.login"))))


@bp.route("/org/<int:org_id>", methods=["POST"])
def switch_org(org_id):
    if not g.user:
        abort(403)
    if not db.one("SELECT id FROM memberships WHERE user_id = ? AND org_id = ?", (g.user["id"], org_id)):
        abort(404)
    db.run("UPDATE sessions SET active_org_id = ? WHERE id = ?", (org_id, g.session["id"]))
    return redirect(url_for("business.dashboard"))


@bp.route("/wachtwoord-vergeten", methods=["GET", "POST"])
def forgot():
    sent = False
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        ip = client_ip()
        # Own counter ("reset:" keys): reset requests limit mail bombing but never lock out a login.
        if not login_blocked("reset:" + email, "reset:" + ip):
            record_login_attempt("reset:" + email, "reset:" + ip, False)
            user = db.one("SELECT * FROM users WHERE email = ? AND password_hash IS NOT NULL", (email,))
            if user:
                raw = token()
                db.run("INSERT INTO password_resets (user_id, token_hash, expires_at, created_at) VALUES (?, ?, ?, ?)",
                       (user["id"], sha256(raw), (now() + timedelta(hours=1)).isoformat(timespec="seconds"), now_iso()))
                send_mail(email, "Nieuw wachtwoord voor Depiqo",
                          f"Kies binnen een uur een nieuw wachtwoord: {services.base_url()}/wachtwoord/{raw}\n\n"
                          "Heb je dit niet aangevraagd? Dan hoef je niets te doen.")
                audit("password.reset_requested", f"user:{user['id']}", user_id=user["id"], org_id=None)
        sent = True  # same answer whether or not the address exists
    return render_template("auth/forgot.html", sent=sent)


@bp.route("/wachtwoord/<raw>", methods=["GET", "POST"])
def reset(raw):
    row = db.one("SELECT * FROM password_resets WHERE token_hash = ? AND used_at IS NULL", (sha256(raw),))
    if not row or parse_dt(row["expires_at"]) < now():
        return render_template("error.html", title="Link verlopen", text="Deze link is verlopen of al gebruikt. Vraag een nieuwe aan.", code=410), 410
    user = db.one("SELECT * FROM users WHERE id = ?", (row["user_id"],))
    error = None
    if request.method == "POST":
        password = request.form.get("password") or ""
        error = password_problem(password, user["email"])
        if not error:
            with db.transaction():
                db.run("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(password), user["id"]))
                db.run("UPDATE password_resets SET used_at = ? WHERE user_id = ? AND used_at IS NULL", (now_iso(), user["id"]))
                db.run("DELETE FROM sessions WHERE user_id = ?", (user["id"],))
                apitokens.revoke_all(user["id"], "password_reset")
            audit("password.reset", f"user:{user['id']}", user_id=user["id"], org_id=None)
            if two_factor_enabled(user):
                return _start_second_step(user, url_for("auth.index"))  # a reset link never replaces the second factor
            return start_session(user["id"], make_response(redirect(url_for("auth.index"))))
    return render_template("auth/reset.html", error=error, email=user["email"])


@bp.route("/uitnodiging/<raw>", methods=["GET", "POST"])
def accept_staff_invite(raw):
    inv = db.one("SELECT * FROM invitations WHERE token_hash = ? AND accepted_at IS NULL", (sha256(raw),))
    if not inv or parse_dt(inv["expires_at"]) < now():
        return render_template("error.html", title="Uitnodiging verlopen",
                               text="Deze uitnodiging is verlopen of al gebruikt. Vraag een nieuwe aan.", code=410), 410
    org = db.one("SELECT * FROM organizations WHERE id = ?", (inv["org_id"],))
    existing = db.one("SELECT * FROM users WHERE email = ?", (inv["email"],))
    error = None
    if request.method == "POST":
        if existing:
            if not g.user or g.user["id"] != existing["id"]:
                return redirect(url_for("auth.login", next=request.path))
            user_id = existing["id"]
        else:
            name = (request.form.get("name") or "").strip()
            password = request.form.get("password") or ""
            error = "Vul je naam in." if not name else password_problem(password, inv["email"])
            if error:
                return render_template("auth/accept_staff.html", inv=inv, org=org, existing=existing, error=error)
            user_id = db.run("INSERT INTO users (email, name, password_hash, created_at) VALUES (?, ?, ?, ?)",
                             (inv["email"], name, hash_password(password), now_iso()))
        with db.transaction():
            db.run("INSERT OR IGNORE INTO memberships (user_id, org_id, role, created_at) VALUES (?, ?, ?, ?)",
                   (user_id, inv["org_id"], inv["role"], now_iso()))
            db.run("UPDATE invitations SET accepted_at = ? WHERE id = ?", (now_iso(), inv["id"]))
        audit("team.joined", f"user:{user_id}", {"role": inv["role"]}, org_id=inv["org_id"], user_id=user_id)
        if g.user:
            db.run("UPDATE sessions SET active_org_id = ? WHERE id = ?", (inv["org_id"], g.session["id"]))
            return redirect(url_for("business.dashboard"))
        return start_session(user_id, make_response(redirect(url_for("business.dashboard"))))
    return render_template("auth/accept_staff.html", inv=inv, org=org, existing=existing, error=error)


@bp.route("/t/<raw>", methods=["GET", "POST"])
def accept_tenant_invite(raw):
    deposit = services.deposit_by_invite(raw)
    if not deposit:
        return render_template("error.html", title="Uitnodiging verlopen",
                               text="Deze link is verlopen of al gebruikt. Vraag je verhuurder om een nieuwe uitnodiging.", code=410), 410
    org = db.one("SELECT * FROM organizations WHERE id = ?", (deposit["org_id"],))
    prop = db.one("SELECT * FROM properties WHERE id = ?", (deposit["property_id"],))
    tenant = db.one("SELECT * FROM tenants WHERE id = ?", (deposit["tenant_id"],))
    existing = db.one("SELECT * FROM users WHERE lower(email) = lower(?) AND password_hash IS NOT NULL", (tenant["email"],))
    error = None
    if request.method == "POST":
        if not request.form.get("confirm_details"):
            error = "Bevestig dat de naam van je verhuurder en het adres kloppen."
        elif existing:
            if not g.user or g.user["id"] != existing["id"]:
                return redirect(url_for("auth.login", next=request.path))
            try:
                services.accept_invite(raw, existing_user_id=existing["id"])
            except services.WorkflowError as exc:
                error = str(exc)
            else:
                return redirect(url_for("wallet.deposit", pid=deposit["pid"]))
        else:
            password = request.form.get("password") or ""
            error = password_problem(password, tenant["email"])
            if not error:
                try:
                    user_id, d = services.accept_invite(raw, password=password)
                except services.WorkflowError as exc:
                    error = str(exc)
                else:
                    audit("tenant.joined", f"deposit:{d['pid']}", org_id=d["org_id"], user_id=user_id)
                    return start_session(user_id, make_response(redirect(url_for("wallet.deposit", pid=d["pid"]))))
    return render_template("auth/accept_tenant.html", deposit=deposit, org=org, prop=prop, tenant=tenant,
                           existing=existing, error=error)
