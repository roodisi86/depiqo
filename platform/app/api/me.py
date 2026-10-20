"""The tenant's own account: profile, notification preferences, data export, account deletion and notifications."""
import json
import re

from flask import Response, g, jsonify

from .. import apitokens, db, i18n, investing, mfa, notify
from .. import states as S
from ..security import NO_ORG, attempt_done, attempt_start, audit, client_ip, verify_password
from ..util import dumps, now_iso
from . import ApiError, body, bp, current_lang, field_error, money, page_args, paged, tenant_api, true_field

TENANT_EVENT_TYPES = ("status", "interest", "payment")  # what the wallet shows a tenant (same as the web page)


def invest_info(user_id):
    vis = investing.visibility(user_id)
    acct = investing.account_for_user(user_id)
    return {"visibility": vis, "eligible": vis == "available", "offered_by_landlord": investing.org_enabled_for(user_id),
            "account_status": acct["status"] if acct else None}


def me_json(user):
    return {"id": user["id"], "name": user["name"], "email": user["email"], "two_factor_enabled": mfa.enabled(user),
            "recovery_codes_left": mfa.recovery_left(user["id"]) if mfa.enabled(user) else None,
            "created_at": user["created_at"], "invest": invest_info(user["id"]),
            "notification_preferences": notify.prefs(user), "language": i18n.user_lang(user),
            "deposit_count": db.scalar("SELECT COUNT(*) FROM deposits d JOIN tenants t ON t.id = d.tenant_id WHERE t.user_id = ? AND d.status != ?",
                                       (user["id"], S.CONCEPT))}


@bp.route("/me", methods=["GET"])
@tenant_api
def me():
    return jsonify(me_json(g.api_user))


@bp.route("/me", methods=["PATCH"])
@tenant_api
def update_me():
    data = body()
    unknown = set(data) - {"name", "notification_preferences", "language"}
    if unknown:
        raise ApiError(422, "unknown_field", "Dit veld kun je hier niet wijzigen.", {k: "Onbekend veld." for k in sorted(unknown)})
    uid = g.api_user["id"]
    changed = []
    if "name" in data:
        name = data["name"]
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120:
            raise field_error("name", "Vul je naam in (maximaal 120 tekens).")
        db.run("UPDATE users SET name = ? WHERE id = ?", (name.strip(), uid))
        changed.append("name")
    if "language" in data:
        if data["language"] not in i18n.LANGS:
            raise field_error("language", "Kies nl, fr of en.")
        db.run("UPDATE users SET language = ? WHERE id = ?", (data["language"], uid))
        changed.append("language")
    if "notification_preferences" in data:
        prefs = data["notification_preferences"]
        push = prefs.get("push") if isinstance(prefs, dict) else None
        if not isinstance(push, dict) or set(push) - set(notify.CATEGORIES) or not all(isinstance(v, bool) for v in push.values()):
            raise field_error("notification_preferences", "Geef per soort (deposit, invest, security, support) true of false.")
        merged = notify.prefs(g.api_user)
        merged["push"].update(push)
        db.run("UPDATE users SET notification_prefs = ? WHERE id = ?", (dumps(merged), uid))
        changed.append("notification_preferences")
    audit("account.updated", f"user:{uid}", {"fields": changed}, org_id=NO_ORG)
    return jsonify(me_json(db.one("SELECT * FROM users WHERE id = ?", (uid,))))


# ------------------------------------------------------------ data export

def _rows(sql, params=()):
    return [dict(r) for r in db.all_(sql, params)]


@bp.route("/me/export", methods=["POST"])
@tenant_api
def export():
    """Everything Depiqo holds about this tenant, as one JSON file. Secrets (password hash, 2FA secret, token
    hashes) are left out."""
    user = g.api_user
    uid = user["id"]
    deposits = []
    for d in db.all_("SELECT d.*, o.name AS org_name, p.address, p.postcode, p.city FROM deposits d JOIN tenants t ON t.id = d.tenant_id "
                     "JOIN organizations o ON o.id = d.org_id JOIN properties p ON p.id = d.property_id WHERE t.user_id = ? AND d.status != ? "
                     "ORDER BY d.id", (uid, S.CONCEPT)):
        ph = ",".join("?" * len(TENANT_EVENT_TYPES))
        deposits.append({
            "pid": d["pid"], "reference": d["reference"], "landlord": d["org_name"],
            "address": {"street": d["address"], "postcode": d["postcode"], "city": d["city"]}, "region": d["region"], "holding": d["holding"],
            "status": d["status"], "amount": money(d["amount_cents"]), "rent": money(d["rent_cents"]), "lease_start": d["lease_start"],
            "lease_end": d["lease_end"], "move_out_date": d["move_out_date"], "created_at": d["created_at"],
            "provider": {"kind": d["provider_kind"], "name": d["provider_name"], "reference": d["provider_reference"],
                         "guarantee_expires_on": d["guarantee_expires_on"]} if d["holding"] == "external" else None,
            "events": _rows(f"SELECT at, type, message FROM deposit_events WHERE deposit_id = ? AND type IN ({ph}) ORDER BY id",
                            (d["id"], *TENANT_EVENT_TYPES)),
            "documents": _rows("SELECT id, kind, filename, mime, size_bytes, uploaded_by_kind, created_at FROM documents WHERE deposit_id = ? ORDER BY id",
                               (d["id"],)),
            "settlements": [dict(s) | {"lines": _rows("SELECT category, description, amount_cents, document_id FROM settlement_lines WHERE settlement_id = ?",
                                                      (s["id"],))}
                            for s in _rows("SELECT id, status, created_at, proposed_at, responded_at, tenant_comment FROM settlements "
                                           "WHERE deposit_id = ? AND status != 'draft' ORDER BY id", (d["id"],))],
            "disputes": _rows("SELECT opened_at, reason, status, resolution_note, landlord_amount_cents, resolved_at FROM disputes WHERE deposit_id = ?",
                              (d["id"],)),
            "identity_checks": _rows("SELECT provider, status, created_at, completed_at FROM kyc_checks WHERE deposit_id = ?", (d["id"],)),
            "bank_account": next(iter(_rows("SELECT provider, iban, status, opened_at, closed_at, ledger_balance_cents, ledger_interest_cents "
                                             "FROM bank_accounts WHERE deposit_id = ?", (d["id"],))), None),
        })
    acct = investing.account_for_user(uid)
    invest = None
    if acct:
        invest = {
            "account": {k: acct[k] for k in ("reference", "status", "portfolio", "provider", "terms_partner_version", "terms_partner_at",
                                             "terms_depiqo_version", "terms_depiqo_at", "fee_rate_bps", "own_iban", "own_iban_registered_at",
                                             "created_at", "opened_at", "activated_at")},
            "appropriateness": [dict(r) | {"answers": json.loads(r["answers_json"]), "reasons": json.loads(r["reasons_json"])}
                                for r in _rows("SELECT questionnaire_version, answers_json, score, result, reasons_json, warning_confirmed_at, created_at "
                                               "FROM invest_appropriateness WHERE user_id = ? ORDER BY id", (uid,))],
            "orders": _rows("SELECT id, side, portfolio, amount_cents, sell_all, purpose, status, executed_amount_cents, executed_day, created_at "
                            "FROM invest_orders WHERE account_id = ? ORDER BY id", (acct["id"],)),
            "transactions": _rows("SELECT kind, amount_cents, description, day, at FROM invest_transactions WHERE account_id = ? ORDER BY day, id",
                                  (acct["id"],)),
            "withdrawals": [investing.withdrawal_view(r) for r in
                            db.all_("SELECT * FROM invest_instructions WHERE account_id = ? AND kind = 'withdraw' ORDER BY id", (acct["id"],))],
            "payout_choices": _rows("SELECT c.status, c.chosen_at, c.paid_cents, c.paid_at, d.reference FROM invest_payout_choices c "
                                    "JOIN deposits d ON d.id = c.deposit_id WHERE c.user_id = ?", (uid,)),
        }
    data = {
        "format": "depiqo-export-1", "exported_at": now_iso(),
        "user": {"id": uid, "email": user["email"], "name": user["name"], "created_at": user["created_at"],
                 "last_login_at": user["last_login_at"], "two_factor_enabled": mfa.enabled(user),
                 "notification_preferences": notify.prefs(user), "language": i18n.user_lang(user)},
        "deposits": deposits, "invest": invest,
        "notifications": _rows("SELECT type, title, body, link_path, created_at, read_at FROM notifications WHERE user_id = ? ORDER BY id", (uid,)),
        "support": [dict(t) | {"messages": _rows("SELECT author_kind, body, created_at FROM support_messages WHERE ticket_id = ? ORDER BY id", (t["id"],))}
                    for t in _rows("SELECT id, category, subject, status, created_at, updated_at, closed_at FROM support_tickets WHERE user_id = ? ORDER BY id",
                                   (uid,))],
        "devices": _rows("SELECT device_name, platform, app_version, created_at, last_seen_at, revoked_at, revoked_reason FROM api_devices "
                         "WHERE user_id = ? ORDER BY id", (uid,)),
        "audit_log": _rows("SELECT at, action, target, ip FROM audit_log WHERE user_id = ? ORDER BY id", (uid,)),
    }
    audit("account.exported", f"user:{uid}", org_id=NO_ORG)
    return Response(dumps(data), mimetype="application/json",
                    headers={"Content-Disposition": f"attachment; filename=depiqo-export-{now_iso()[:10]}.json"})


# ------------------------------------------------------------ account deletion

DELETED_NOW = [
    "Je naam, e-mailadres en wachtwoord: je account wordt geanonimiseerd en je kunt niet meer inloggen.",
    "Twee-stapsverificatie, herstelcodes, sessies op de website en alle apparaten en tokens in de app.",
    "Je meldingen, pushtokens, voorkeuren en taalkeuze.",
    "Je vragen aan support, ook de kopie die naar de supportmailbox van Depiqo ging (de inhoud wordt gewist).",
    "E-mails van Depiqo aan jou die niet bij een borgdossier of je beleggingsrekening horen, zoals links om je wachtwoord te herstellen.",
    "De registratie van je inlogpogingen.",
]
KEPT_BY_LAW = [
    "Je borgdossiers: je verhuurder moet die bewaren (huurcontract, betalingen, afrekening, documenten, en de e-mails daarover). Ze blijven "
    "bij je verhuurder, met je naam en e-mailadres zoals hij die heeft, maar zonder koppeling aan je Depiqo-account.",
    "Je beleggingsgegevens: de rekening, de kennis- en ervaringstoets, de offertes met kosten en risico die je zag, orders, transacties en "
    "de berichten over je rekening (voorstel servicevergoeding, opnamerekening). De partner moet die volgens de wet bewaren; Depiqo bewaart "
    "zijn kopie zolang de partner dat moet. In die berichten worden je naam en e-mailadres verwijderd.",
    "Het auditlog: wie wat wanneer deed, zonder je naam en e-mailadres.",
]


def deletion_blockers(uid):
    out = []
    ph = ",".join("?" * 3)
    for d in db.all_(f"SELECT d.pid, d.reference, p.address FROM deposits d JOIN tenants t ON t.id = d.tenant_id JOIN properties p ON p.id = d.property_id "
                     f"WHERE t.user_id = ? AND d.status NOT IN ({ph})", (uid, S.CLOSED, S.CANCELLED, S.CONCEPT)):
        out.append({"code": "open_deposit", "deposit_pid": d["pid"],
                    "message": f"Je borg voor {d['address']} ({d['reference']}) loopt nog.",
                    "next_step": "Wacht tot je borg is terugbetaald of vrijgegeven. Daarna kun je je account verwijderen."})
    acct = investing.account_for_user(uid)
    if acct and acct["status"] == "pending":
        out.append({"code": "invest_pending", "message": "Je beleggingsrekening wordt nog geopend bij de partner.",
                    "next_step": "Wacht tot de rekening actief is, of neem contact op met Depiqo."})
    elif acct and acct["status"] == "active":
        s = investing.summary(acct)
        open_orders = db.scalar("SELECT COUNT(*) FROM invest_orders WHERE account_id = ? AND status = 'pending'", (acct["id"],))
        running = db.scalar("SELECT COUNT(*) FROM invest_instructions WHERE account_id = ? AND kind IN ('withdraw', 'fee') "
                            "AND status IN ('pending', 'sent', 'acknowledged')", (acct["id"],))
        if s["total"] > 0 or open_orders or running:
            out.append({"code": "invest_balance", "message": "Op je beleggingsrekening staat nog geld, of er lopen nog orders of opnames.",
                        "next_step": "Verkoop je beleggingen en neem je geld op naar je eigen rekening. Daarna kun je je account verwijderen."})
    return out


def _deletion_info(uid):
    blockers = deletion_blockers(uid)
    return {"possible": not blockers, "blockers": blockers, "deleted_now": DELETED_NOW, "kept_by_law": KEPT_BY_LAW,
            "how": "Stuur je wachtwoord en confirm=true naar POST /me/delete-request."}


@bp.route("/me/delete-request", methods=["GET"])
@tenant_api
def deletion_preview():
    return jsonify(_deletion_info(g.api_user["id"]))


@bp.route("/me/delete-request", methods=["POST"])
@tenant_api
def delete_account():
    data = body()
    user = g.api_user
    uid = user["id"]
    true_field(data, "confirm", "Bevestig dat je je account wilt verwijderen.")
    attempt = attempt_start(user["email"], client_ip())
    if not attempt:
        raise ApiError(429, "too_many_attempts", "Te veel mislukte pogingen. Wacht 15 minuten en probeer het opnieuw.", headers={"Retry-After": "900"})
    ok = verify_password(user["password_hash"], data.get("password") if isinstance(data.get("password"), str) else "")
    attempt_done(attempt, ok)
    if not ok:
        raise field_error("password", "Dit wachtwoord klopt niet.", "invalid_password")
    blockers = deletion_blockers(uid)
    if blockers:
        raise ApiError(409, "deletion_blocked", " ".join(f"{b['message']} {b['next_step']}" for b in blockers))
    email = user["email"]
    anon_email = f"verwijderd-{uid}@verwijderd.depiqo.invalid"
    with db.transaction():
        apitokens.revoke_all(uid, "account_deleted")
        db.run("UPDATE users SET email = ?, name = 'Verwijderde gebruiker', password_hash = NULL, totp_secret = NULL, totp_pending_secret = NULL, "
               "totp_enabled_at = NULL, totp_last_step = NULL, notification_prefs = NULL, deleted_at = ? WHERE id = ?",
               (anon_email, now_iso(), uid))
        db.run("DELETE FROM recovery_codes WHERE user_id = ?", (uid,))
        db.run("DELETE FROM sessions WHERE user_id = ?", (uid,))
        db.run("DELETE FROM password_resets WHERE user_id = ?", (uid,))
        db.run("DELETE FROM api_mfa_challenges WHERE user_id = ?", (uid,))
        db.run("DELETE FROM api_idempotency WHERE user_id = ?", (uid,))
        db.run("DELETE FROM api_access_tokens WHERE device_id IN (SELECT id FROM api_devices WHERE user_id = ?)", (uid,))
        db.run("DELETE FROM api_refresh_tokens WHERE device_id IN (SELECT id FROM api_devices WHERE user_id = ?)", (uid,))
        db.run("UPDATE api_devices SET device_name = 'verwijderd', last_ip = NULL WHERE user_id = ?", (uid,))
        db.run("DELETE FROM push_messages WHERE user_id = ?", (uid,))
        db.run("DELETE FROM push_tokens WHERE user_id = ?", (uid,))
        db.run("DELETE FROM notifications WHERE user_id = ?", (uid,))
        for tid in [r["id"] for r in db.all_("SELECT id FROM support_tickets WHERE user_id = ?", (uid,))]:
            # the copy in the support mailbox (outbox): keep that a mail went out, wipe who asked and what
            db.run("UPDATE outbox_emails SET subject = ?, body_text = ? WHERE subject LIKE ?",
                   (f"[Depiqo support #{tid}] verwijderd", f"Inhoud verwijderd: de huurder heeft het account verwijderd (vraag #{tid}).",
                    f"[Depiqo support #{tid}]%"))
        db.run("DELETE FROM support_messages WHERE ticket_id IN (SELECT id FROM support_tickets WHERE user_id = ?)", (uid,))
        db.run("DELETE FROM support_tickets WHERE user_id = ?", (uid,))
        db.run("DELETE FROM login_attempts WHERE email IN (?, ?, ?)", (email, "mfa:" + email, "reset:" + email))
        _scrub_mail(uid, email, user["name"], anon_email)
        db.run("UPDATE tenants SET user_id = NULL WHERE user_id = ?", (uid,))
        db.run("UPDATE invest_accounts SET status = 'closed' WHERE user_id = ? AND status IN ('draft', 'active')", (uid,))
        audit("account.deleted", f"user:{uid}", {"via": "app"}, org_id=NO_ORG, user_id=uid)
    return jsonify({"deleted": True, "deleted_now": DELETED_NOW, "kept_by_law": KEPT_BY_LAW})


def _scrub_mail(uid, email, name, anon_email):
    """Mails to the user outside a deposit file: Invest notices are records (kept, name and address removed);
    everything else (password reset links and the like) is deleted. Mails in a deposit file belong to the landlord."""
    notices = investing.notice_subjects()
    for m in db.all_("SELECT * FROM outbox_emails WHERE lower(to_email) = lower(?) AND deposit_id IS NULL", (email,)):
        if m["subject"] in notices:
            body = re.sub(rf"^(Hallo|Bonjour|Hello) {re.escape(name)},", r"\1,", m["body_text"] or "")
            db.run("UPDATE outbox_emails SET to_email = ?, body_text = ? WHERE id = ?", (anon_email, body.replace(email, anon_email), m["id"]))
        else:
            db.run("DELETE FROM outbox_emails WHERE id = ?", (m["id"],))


# ------------------------------------------------------------ notifications

def notification_json(n):
    """Title and body in the language of the request (Accept-Language, else the user's preference)."""
    try:
        params = json.loads(n["params_json"]) if n["params_json"] else None
    except ValueError:
        params = None
    lang = current_lang()
    title, text = notify.render(n["type"], params, lang) if params is not None else (n["title"], n["body"])
    return {"id": n["id"], "type": n["type"], "category": n["category"], "title": title, "body": text, "params": params or {},
            "language": lang, "link_path": n["link_path"], "created_at": n["created_at"], "read_at": n["read_at"]}


@bp.route("/notifications", methods=["GET"])
@tenant_api
def notifications():
    limit, cursor = page_args()
    uid = g.api_user["id"]
    if cursor:
        if len(cursor) != 1 or not isinstance(cursor[0], int):
            raise ApiError(400, "invalid_cursor", "Deze cursor is niet geldig.")
        rows = db.all_("SELECT * FROM notifications WHERE user_id = ? AND id < ? ORDER BY id DESC LIMIT ?", (uid, cursor[0], limit + 1))
    else:
        rows = db.all_("SELECT * FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT ?", (uid, limit + 1))
    out = paged(rows, limit, lambda r: [r["id"]], notification_json)
    out["unread_count"] = db.scalar("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND read_at IS NULL", (uid,))
    return jsonify(out)


@bp.route("/notifications/<int:notification_id>/read", methods=["POST"])
@tenant_api
def notification_read(notification_id):
    uid = g.api_user["id"]
    n = db.one("SELECT * FROM notifications WHERE id = ? AND user_id = ?", (notification_id, uid))
    if not n:
        raise ApiError(404, "not_found", "Deze melding bestaat niet.")
    db.run("UPDATE notifications SET read_at = ? WHERE id = ? AND read_at IS NULL", (now_iso(), notification_id))
    return jsonify(notification_json(db.one("SELECT * FROM notifications WHERE id = ?", (notification_id,))))
