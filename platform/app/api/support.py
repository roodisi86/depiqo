"""Questions to Depiqo support from the app. A ticket is stored, Depiqo support gets an e-mail, and a reply by
Depiqo staff (admin page /admin/support) becomes a notification. Tickets are never linked to the landlord's
communication log, even when they mention a deposit."""
from datetime import timedelta

from flask import current_app, g, jsonify

from .. import db
from .. import states as S
from ..partners import send_mail
from ..security import NO_ORG, audit
from ..util import now, now_iso
from . import ApiError, body, bp, current_lang, field_error, idempotent, page_args, paged, tenant_api

CATEGORIES = {"deposit": "Mijn borg", "invest": "Beleggen", "account": "Mijn account", "app": "De app", "other": "Iets anders"}
STATUS_LABELS = {"open": "Open", "answered": "Beantwoord", "closed": "Gesloten"}
LIMITS = ((timedelta(minutes=10), 3), (timedelta(hours=24), 10))


def ticket_json(t):
    msgs = db.all_("SELECT * FROM support_messages WHERE ticket_id = ? ORDER BY id", (t["id"],))
    pid = db.scalar("SELECT pid FROM deposits WHERE id = ?", (t["deposit_id"],)) if t["deposit_id"] else None
    return {"id": t["id"], "category": t["category"], "category_label": CATEGORIES[t["category"]], "subject": t["subject"],
            "deposit_pid": pid, "status": t["status"], "status_label": STATUS_LABELS[t["status"]], "created_at": t["created_at"],
            "updated_at": t["updated_at"],
            "messages": [{"author": m["author_kind"], "body": m["body"], "created_at": m["created_at"]} for m in msgs]}


@bp.route("/support", methods=["POST"])
@tenant_api
@idempotent()
def create_ticket():
    data = body()
    uid = g.api_user["id"]
    category = data.get("category")
    if category not in CATEGORIES:
        raise field_error("category", "Kies een onderwerp: deposit, invest, account, app of other.")
    message = data.get("message") if isinstance(data.get("message"), str) else ""
    if not 10 <= len(message.strip()) <= 4000:
        raise field_error("message", "Beschrijf je vraag in 10 tot 4000 tekens.")
    subject = data.get("subject") if isinstance(data.get("subject"), str) and data.get("subject").strip() else CATEGORIES[category]
    deposit_id = None
    if data.get("deposit_pid") is not None:
        d = db.one("SELECT d.* FROM deposits d JOIN tenants t ON t.id = d.tenant_id WHERE d.pid = ? AND t.user_id = ? AND d.status != ?",
                   (str(data["deposit_pid"]), uid, S.CONCEPT))
        if not d:
            raise field_error("deposit_pid", "Deze borg is niet van jou.")
        deposit_id = d["id"]
    for window, maximum in LIMITS:
        since = (now() - window).isoformat(timespec="seconds")
        if db.scalar("SELECT COUNT(*) FROM support_tickets WHERE user_id = ? AND created_at > ?", (uid, since)) >= maximum:
            raise ApiError(429, "support_rate_limited", "Je hebt net al een paar vragen gestuurd. Probeer het later opnieuw.",
                           headers={"Retry-After": str(int(window.total_seconds()))})
    with db.transaction():
        tid = db.run("INSERT INTO support_tickets (user_id, category, subject, deposit_id, status, language, created_at, updated_at) "
                     "VALUES (?, ?, ?, ?, 'open', ?, ?, ?)", (uid, category, subject.strip()[:120], deposit_id, current_lang(), now_iso(), now_iso()))
        db.run("INSERT INTO support_messages (ticket_id, author_kind, author_user_id, body, created_at) VALUES (?, 'tenant', ?, ?, ?)",
               (tid, uid, message.strip(), now_iso()))
        # no deposit_id on the mail: the question must not show up in the landlord's communication log
        send_mail(current_app.config["SUPPORT_EMAIL"], f"[Depiqo support #{tid}] {CATEGORIES[category]}: {subject.strip()[:80]}",
                  f"Nieuwe vraag uit de app (#{tid}).\nVan: {g.api_user['name']} <{g.api_user['email']}>\nOnderwerp: {CATEGORIES[category]}\n"
                  f"Taal: {current_lang()}\n\n{message.strip()}\n\nBeantwoorden: {current_app.config['BASE_URL'].rstrip('/')}/admin/support/{tid}\n")
        audit("support.ticket_created", f"support:{tid}", {"category": category}, org_id=NO_ORG)
    return jsonify(ticket_json(db.one("SELECT * FROM support_tickets WHERE id = ?", (tid,)))), 201


@bp.route("/support", methods=["GET"])
@tenant_api
def tickets():
    limit, cursor = page_args()
    uid = g.api_user["id"]
    if cursor:
        if len(cursor) != 1 or not isinstance(cursor[0], int):
            raise ApiError(400, "invalid_cursor", "Deze cursor is niet geldig.")
        rows = db.all_("SELECT * FROM support_tickets WHERE user_id = ? AND id < ? ORDER BY id DESC LIMIT ?", (uid, cursor[0], limit + 1))
    else:
        rows = db.all_("SELECT * FROM support_tickets WHERE user_id = ? ORDER BY id DESC LIMIT ?", (uid, limit + 1))
    return jsonify(paged(rows, limit, lambda r: [r["id"]], ticket_json))
