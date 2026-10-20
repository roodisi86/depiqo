"""Depiqo staff: support questions from the app. A reply becomes a notification for the tenant."""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .. import db, notify
from ..api.support import CATEGORIES, STATUS_LABELS
from ..security import NO_ORG, audit, staff_required
from ..util import now_iso

bp = Blueprint("support_admin", __name__, url_prefix="/admin/support")


@bp.route("")
@staff_required
def index():
    status = request.args.get("status", "open")
    where, params = ("", []) if status == "all" else (" WHERE t.status = ?", [status if status in STATUS_LABELS else "open"])
    rows = db.all_("SELECT t.*, u.name, u.email, d.reference, (SELECT COUNT(*) FROM support_messages m WHERE m.ticket_id = t.id) AS n "
                   "FROM support_tickets t JOIN users u ON u.id = t.user_id LEFT JOIN deposits d ON d.id = t.deposit_id"
                   + where + " ORDER BY t.id DESC LIMIT 200", params)
    counts = {r["status"]: r["n"] for r in db.all_("SELECT status, COUNT(*) AS n FROM support_tickets GROUP BY status")}
    return render_template("admin/support.html", rows=rows, status=status, counts=counts, CATEGORIES=CATEGORIES, STATUS_LABELS=STATUS_LABELS)


def _ticket(ticket_id):
    t = db.one("SELECT t.*, u.name, u.email, d.reference, d.pid FROM support_tickets t JOIN users u ON u.id = t.user_id "
               "LEFT JOIN deposits d ON d.id = t.deposit_id WHERE t.id = ?", (ticket_id,))
    if not t:
        abort(404)
    return t


@bp.route("/<int:ticket_id>")
@staff_required
def ticket(ticket_id):
    t = _ticket(ticket_id)
    msgs = db.all_("SELECT m.*, u.name AS author FROM support_messages m LEFT JOIN users u ON u.id = m.author_user_id "
                   "WHERE m.ticket_id = ? ORDER BY m.id", (ticket_id,))
    return render_template("admin/support_ticket.html", t=t, msgs=msgs, CATEGORIES=CATEGORIES, STATUS_LABELS=STATUS_LABELS)


@bp.route("/<int:ticket_id>", methods=["POST"])
@staff_required
def act(ticket_id):
    t = _ticket(ticket_id)
    action = request.form.get("action")
    if action == "reply":
        text = (request.form.get("body") or "").strip()
        if len(text) < 2:
            flash("Schrijf eerst een antwoord.", "error")
            return redirect(url_for("support_admin.ticket", ticket_id=ticket_id))
        with db.transaction():
            db.run("INSERT INTO support_messages (ticket_id, author_kind, author_user_id, body, created_at) VALUES (?, 'staff', ?, ?, ?)",
                   (ticket_id, g.user["id"], text[:4000], now_iso()))
            db.run("UPDATE support_tickets SET status = 'answered', updated_at = ?, closed_at = NULL WHERE id = ?", (now_iso(), ticket_id))
            notify.notify(t["user_id"], "support_reply", {"ticket": ticket_id}, f"/app-link/support/{ticket_id}")
            audit("support.replied", f"support:{ticket_id}", org_id=NO_ORG)
        flash("Antwoord verstuurd. De huurder krijgt een melding in de app.", "ok")
    elif action in ("close", "reopen"):
        closed = action == "close"
        db.run("UPDATE support_tickets SET status = ?, updated_at = ?, closed_at = ? WHERE id = ?",
               ("closed" if closed else "open", now_iso(), now_iso() if closed else None, ticket_id))
        audit(f"support.{'closed' if closed else 'reopened'}", f"support:{ticket_id}", org_id=NO_ORG)
        flash("Vraag gesloten." if closed else "Vraag staat weer open.", "ok")
    else:
        abort(400)
    return redirect(url_for("support_admin.ticket", ticket_id=ticket_id))
