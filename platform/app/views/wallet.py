"""Depiqo Wallet: the tenant's view of their deposit."""
from flask import Blueprint, Response, abort, current_app, flash, g, redirect, render_template, request, send_file, url_for

from .. import db, investing, providers, release_form, rules, services
from .. import states as S
from ..security import audit, tenant_required
from ..storage import KINDS, UploadError, file_path, save_upload

bp = Blueprint("wallet", __name__, url_prefix="/wallet")


def my_deposit(pid):
    d = services.get_deposit(pid, tenant_ids=g.tenant_ids)
    if not d:
        abort(404)
    return d


@bp.route("")
@tenant_required
def home():
    ph = ",".join("?" * len(g.tenant_ids))
    rows = db.all_(f"SELECT d.*, p.address, p.city, o.name AS org_name FROM deposits d JOIN properties p ON p.id = d.property_id "
                   f"JOIN organizations o ON o.id = d.org_id WHERE d.tenant_id IN ({ph}) AND d.status != ? ORDER BY d.created_at DESC",
                   (*g.tenant_ids, S.CONCEPT))
    if len(rows) == 1:
        return redirect(url_for("wallet.deposit", pid=rows[0]["pid"]))
    return render_template("wallet/home.html", rows=rows, figures_for={r["id"]: services.balances(r) for r in rows})


@bp.route("/borg/<pid>")
@tenant_required
def deposit(pid):
    d = my_deposit(pid)
    org = db.one("SELECT * FROM organizations WHERE id = ?", (d["org_id"],))
    prop = db.one("SELECT * FROM properties WHERE id = ?", (d["property_id"],))
    acct = services.account_for(d)
    settlement = services.current_settlement(d)
    visible_settlement = settlement if settlement and settlement["status"] != "draft" else None
    lines = services.settlement_lines(visible_settlement)
    docs = db.all_("SELECT * FROM documents WHERE deposit_id = ? ORDER BY id DESC", (d["id"],))
    events = db.all_("SELECT * FROM deposit_events WHERE deposit_id = ? AND type IN ('status', 'interest', 'payment') ORDER BY id DESC LIMIT 12", (d["id"],))
    instructions, pay_problem = (services.payment_details(d, org) if d["status"] == S.AWAITING_PAYMENT else (None, None))
    opening = d["status"] == S.ID_PENDING and services.open_instruction(d) is not None
    return render_template("wallet/deposit.html", d=d, org=org, prop=prop, acct=acct, settlement=visible_settlement, lines=lines,
                           total=services.settlement_total(visible_settlement), docs=docs, events=events, instructions=instructions,
                           pay_problem=pay_problem, opening=opening, balances=services.balances(d, acct),
                           deadline=services.deadline_info(d), rules=rules.for_deposit(d), KINDS=KINDS,
                           CATEGORIES=services.CATEGORIES, split=services.payout_split(d) if d["status"] in (S.AGREED, S.PAYOUT_PENDING) else None,
                           release_form=services.release_form_available(d), expiry=providers.expiry_info(d),
                           invest_payout=_invest_payout(d))


def _invest_payout(d):
    """Doorbeleggen: only when Invest is available to this tenant; never shown on Business pages."""
    if d["holding"] != "depiqo" or investing.visibility(g.user["id"]) == "hidden":
        return None
    choice = investing.payout_choice(d["id"])
    can = investing.can_choose_payout(d, g.user["id"])
    if not choice and not can:
        return None
    return {"choice": choice, "can": can, "partner": investing.partner().display_name}


@bp.route("/borg/<pid>/vrijgaveformulier.pdf")
@tenant_required
def release_form_pdf(pid):
    d = my_deposit(pid)  # only the tenant's own deposits
    if not services.release_form_available(d):
        abort(404)
    pdf = release_form.build(d)
    audit("deposit.release_form", f"deposit:{pid}", {"by": "tenant"}, org_id=d["org_id"])
    services.add_event(d, "tenant", "document", "Vrijgaveformulier gedownload door de huurder", g.user["id"])
    return Response(pdf, mimetype="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename=vrijgaveformulier-{d['reference']}.pdf"})


@bp.route("/borg/<pid>/<action>", methods=["POST"])
@tenant_required
def action(pid, action):
    d = my_deposit(pid)
    uid = g.user["id"]
    try:
        if action == "identiteit":
            d = services.verify_identity(d, uid, request.form.get("full_name"), request.form.get("birth_date"))
            if d["status"] == S.AWAITING_PAYMENT:
                flash("Je identiteit is bevestigd en je borgrekening is geopend.", "ok")
            elif d["status"] == S.ID_PENDING and services.open_instruction(d):
                flash("Je identiteit is bevestigd. De bank opent nu je borgrekening. Je krijgt bericht zodra je kunt storten.", "ok")
            elif d["status"] == S.ID_PENDING:
                flash("Je identiteit is bevestigd, maar de bank kon je borgrekening nog niet openen. Probeer het later opnieuw. "
                      "Betaal nog niets.", "error")
            else:
                flash("Je identiteit kon niet worden bevestigd. Controleer je gegevens en probeer het opnieuw.", "error")
        elif action == "akkoord":
            services.tenant_agree(d, uid)
            flash("Je bent akkoord gegaan. De uitbetaling wordt gestart.", "ok")
        elif action == "betwisten":
            services.tenant_dispute(d, uid, request.form.get("reason"))
            flash("Je bezwaar is vastgelegd. Je verhuurder neemt contact met je op.", "ok")
        elif action == "documenten":
            doc_id = save_upload(request.files.get("file"), d, request.form.get("kind"), "tenant", uid)
            services.add_event(d, "tenant", "document", "Huurder heeft een document toegevoegd", uid)
            audit("document.uploaded", f"document:{doc_id}", org_id=d["org_id"])
            flash("Document toegevoegd.", "ok")
        else:
            abort(404)
    except (services.WorkflowError, UploadError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("wallet.deposit", pid=pid))


@bp.route("/documenten/<int:doc_id>")
@tenant_required
def download(doc_id):
    doc = db.one("SELECT doc.* FROM documents doc JOIN deposits d ON d.id = doc.deposit_id WHERE doc.id = ? AND d.tenant_id IN (%s)"
                 % ",".join("?" * len(g.tenant_ids)), (doc_id, *g.tenant_ids))
    if not doc:
        abort(404)
    audit("document.downloaded", f"document:{doc_id}", org_id=doc["org_id"])
    return send_file(file_path(doc), mimetype=doc["mime"], as_attachment=True, download_name=doc["filename"])
