"""Depiqo staff back office: organisations, reconciliation, bank instructions, unit economics,
invoices, evidence verification, outbox and audit log."""
import re
from datetime import date

from flask import Blueprint, Response, abort, current_app, flash, g, redirect, render_template, request, send_file, url_for

from .. import billing, db, finance, rules, services
from .. import states as S
from ..partners import partner_status
from ..security import audit, staff_required
from ..storage import KINDS, file_path
from ..util import add_months, now_iso, parse_euros, today

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("")
@staff_required
def home():
    orgs = db.all_("SELECT o.*, (SELECT COUNT(*) FROM deposits d WHERE d.org_id = o.id AND d.status NOT IN (?, ?, ?)) AS active, "
                   "(SELECT COUNT(*) FROM memberships m WHERE m.org_id = o.id) AS members FROM organizations o ORDER BY o.name",
                   (S.CONCEPT, S.CLOSED, S.CANCELLED))
    bank_errors = db.all_("SELECT * FROM bank_events WHERE error IS NOT NULL ORDER BY id DESC LIMIT 20")
    overdue = []
    for d in db.all_("SELECT d.*, o.name AS org_name FROM deposits d JOIN organizations o ON o.id = d.org_id WHERE d.status IN (?, ?, ?, ?)",
                     (S.MOVE_OUT, S.SETTLEMENT_PROPOSED, S.AGREED, S.DISPUTED)):
        info = services.deadline_info(d)
        if info and info["statutory"] and info["days_left"] < 0:
            overdue.append((d, info))
    plans = {o["id"]: billing.plan_for(o) for o in orgs}
    exceptions, totals = finance.reconciliation(only_exceptions=True)
    return render_template("admin/home.html", orgs=orgs, plans=plans, PLANS=billing.PLANS, bank_errors=bank_errors, overdue=overdue,
                           exceptions=exceptions[:8], totals=totals, instructions=finance.failed_instructions(),
                           INSTRUCTION_KINDS=services.INSTRUCTION_KINDS, INSTRUCTION_STATUSES=services.INSTRUCTION_STATUSES,
                           partner=partner_status(), this_month=today().strftime("%Y-%m"))


@bp.route("/organisaties", methods=["POST"])
@staff_required
def create_org():
    name = " ".join((request.form.get("name") or "").split())  # no newlines or control whitespace
    if not name:
        flash("Vul een naam in.", "error")
        return redirect(url_for("admin.home"))
    pilot = request.form.get("pilot") == "1"
    plan = request.form.get("plan") if request.form.get("plan") in billing.SELF_SERVICE else "essential"
    with db.transaction():
        org_id = db.run("INSERT INTO organizations (name, country, pilot_until, plan, created_at) VALUES (?, ?, ?, ?, ?)",
                        (name[:120], request.form.get("country") or "NL", add_months(today(), 6).isoformat() if pilot else None,
                         plan, now_iso()))
        org = db.one("SELECT * FROM organizations WHERE id = ?", (org_id,))
        billing.record_plan_change(org, plan, None, today().replace(day=1), g.user["id"])
    audit("org.created", f"org:{org_id}", {"pilot": pilot, "plan": plan}, org_id=org_id)
    flash("Organisatie aangemaakt. Nodig nu de eerste beheerder uit via 'Uitnodigen'.", "ok")
    return redirect(url_for("admin.home"))


@bp.route("/organisaties/<int:org_id>/plan", methods=["POST"])
@staff_required
def set_plan(org_id):
    """Staff only: any plan, including Enterprise with its own numbers, from the current month or later."""
    org = db.one("SELECT * FROM organizations WHERE id = ?", (org_id,))
    if not org:
        abort(404)
    plan = request.form.get("plan")
    if plan not in billing.PLANS:
        flash("Kies een geldig plan.", "error")
        return redirect(url_for("admin.home"))
    month = (request.form.get("valid_from") or today().strftime("%Y-%m")).strip()
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month) or month < today().strftime("%Y-%m"):
        flash("Kies een ingangsmaand vanaf deze maand (JJJJ-MM). Een afgelopen maand wijzig je met een creditnota.", "error")
        return redirect(url_for("admin.home"))
    valid_from = date(int(month[:4]), int(month[5:]), 1)
    overrides = {}
    if plan == "enterprise":
        for field in billing.HISTORY_FIELDS:
            raw = (request.form.get(field) or "").strip()
            if field == "included":
                value = int(raw) if raw.isdigit() and len(raw) <= 7 else None
            else:
                value = parse_euros(raw)
            if value is None:
                flash("Vul voor Enterprise alle bedragen en het aantal inbegrepen dossiers in (0 of meer).", "error")
                return redirect(url_for("admin.home"))
            overrides[field] = value
    billing.record_plan_change(org, plan, overrides, valid_from, g.user["id"])
    audit("billing.plan_changed", f"org:{org_id}", {"from": org["plan"], "to": plan, "valid_from": valid_from.isoformat(), **overrides},
          org_id=org_id)
    flash(f"Plan van {org['name']} is {billing.PLANS[plan]['label']} vanaf {month}.", "ok")
    return redirect(url_for("admin.home"))


@bp.route("/organisaties/<int:org_id>/uitnodigen", methods=["POST"])
@staff_required
def invite_admin(org_id):
    from datetime import timedelta

    from ..partners import send_mail
    from ..util import now, sha256, token, valid_email
    org = db.one("SELECT * FROM organizations WHERE id = ?", (org_id,))
    email = (request.form.get("email") or "").strip().lower()
    if not org or not valid_email(email):
        flash("Vul een geldig e-mailadres in.", "error")
        return redirect(url_for("admin.home"))
    raw = token()
    db.run("INSERT INTO invitations (org_id, email, role, token_hash, invited_by, expires_at, created_at) VALUES (?, ?, 'admin', ?, ?, ?, ?)",
           (org_id, email, sha256(raw), g.user["id"], (now() + timedelta(days=7)).isoformat(timespec="seconds"), now_iso()))
    send_mail(email, f"Je Depiqo-omgeving voor {org['name']} staat klaar",
              f"Accepteer je uitnodiging binnen 7 dagen: {services.base_url()}/uitnodiging/{raw}\n")
    audit("org.admin_invited", f"org:{org_id}", {"email": email}, org_id=org_id)
    flash(f"Uitnodiging verstuurd naar {email}.", "ok")
    return redirect(url_for("admin.home"))


# ------------------------------------------------------------ bank instructions

@bp.route("/opdrachten/versturen", methods=["POST"])
@staff_required
def dispatch():
    result = services.dispatch_instructions()
    audit("bank.dispatch", "bank_instructions", result, org_id=None)
    if result["blocked"]:
        flash(f"Niets verstuurd. {result['blocked']}", "error")
    else:
        flash(f"Opdrachten verstuurd: {result['sent']}. Opnieuw te proberen: {result['retry']}. Mislukt: {result['failed']}.",
              "ok" if not result["failed"] else "error")
    return redirect(request.form.get("back") if request.form.get("back") in ("/admin", "/admin/afstemming") else url_for("admin.home"))


@bp.route("/opdrachten/<int:instr_id>/opnieuw", methods=["POST"])
@staff_required
def retry(instr_id):
    try:
        instr = services.retry_instruction(instr_id)
        audit("bank.instruction_retry", f"instruction:{instr_id}", org_id=None)
        result = services.dispatch_instructions(ids=[instr_id])
        flash("Opdracht opnieuw verstuurd." if result["sent"] else
              (f"Niet verstuurd. {result['blocked']}" if result["blocked"] else "Opdracht staat weer in de wachtrij."),
              "ok" if result["sent"] else "error")
    except services.WorkflowError as exc:
        flash(str(exc), "error")
    return redirect(url_for("admin.home"))


@bp.route("/bankberichten/<int:event_id>/opnieuw", methods=["POST"])
@staff_required
def reprocess_event(event_id):
    try:
        result = services.reprocess_bank_event(event_id)
        audit("bank.event_reprocessed", f"bank_event:{event_id}", {"result": result}, org_id=None)
        flash("Bankbericht opnieuw verwerkt." if result == "processed" else
              "Bankbericht opnieuw bekeken, maar het geeft nog steeds een fout. Zie de melding.", "ok" if result == "processed" else "error")
    except services.WorkflowError as exc:
        flash(str(exc), "error")
    return redirect(url_for("admin.home"))


# ------------------------------------------------------------ reconciliation

@bp.route("/afstemming")
@staff_required
def reconciliation():
    only = request.args.get("alles") != "1"
    rows, totals = finance.reconciliation(only_exceptions=only)
    return render_template("admin/reconciliation.html", rows=rows, totals=totals, only=only, partner=partner_status(),
                           instructions=finance.failed_instructions(), INSTRUCTION_KINDS=services.INSTRUCTION_KINDS,
                           INSTRUCTION_STATUSES=services.INSTRUCTION_STATUSES)


# ------------------------------------------------------------ unit economics

@bp.route("/unit-economics", methods=["GET", "POST"])
@staff_required
def unit_economics():
    if request.method == "POST":
        values = {}
        current = finance.get_settings()
        for key in finance.SETTINGS:
            if key not in request.form:
                values[key] = current[key]  # a field that is not on the form keeps its value
                continue
            cents = parse_euros(request.form.get(key))
            if cents is None:
                flash("Vul elk bedrag in euro in, 0 of meer.", "error")
                return redirect(url_for("admin.unit_economics"))
            values[key] = cents
        finance.set_settings(values, g.user["id"])
        audit("staff.settings_changed", "unit_economics", values, org_id=None)
        flash("Aannames opgeslagen.", "ok")
        return redirect(url_for("admin.unit_economics"))
    return render_template("admin/unit_economics.html", ue=finance.unit_economics(), SETTINGS=finance.SETTINGS)


# ------------------------------------------------------------ invoices

@bp.route("/facturen")
@staff_required
def invoices():
    rows = db.all_("SELECT i.*, o.name AS org_name, c.number AS credit_for_number FROM invoices i JOIN organizations o ON o.id = i.org_id "
                   "LEFT JOIN invoices c ON c.id = i.credit_for_id ORDER BY i.id DESC LIMIT 300")
    return render_template("admin/invoices.html", rows=rows, B=billing)


@bp.route("/facturen/<int:invoice_id>/<action>", methods=["POST"])
@staff_required
def invoice_action(invoice_id, action):
    inv = db.one("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
    if not inv:
        abort(404)
    try:
        if action == "betaald":
            billing.mark_paid(invoice_id)
            audit("invoice.paid", f"invoice:{inv['number']}", org_id=inv["org_id"])
            flash(f"Factuur {inv['number']} staat als betaald.", "ok")
        elif action == "crediteren":
            credit = billing.credit_invoice(invoice_id, request.form.get("reason"), g.user["id"])
            audit("invoice.credited", f"invoice:{inv['number']}", {"credit": credit["number"], "reason": request.form.get("reason")},
                  org_id=inv["org_id"])
            flash(f"Factuur {inv['number']} gecrediteerd met {credit['number']}.", "ok")
        else:
            abort(404)
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("admin.invoices"))


@bp.route("/facturen/<number>.pdf")
@staff_required
def invoice_pdf(number):
    inv = db.one("SELECT * FROM invoices WHERE number = ?", (number,))
    if not inv:
        abort(404)
    org = db.one("SELECT * FROM organizations WHERE id = ?", (inv["org_id"],))
    return Response(billing.invoice_pdf(inv, org), mimetype="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename={number}.pdf"})


# ------------------------------------------------------------ one deposit (evidence verification)

def _deposit(pid):
    d = services.get_deposit(pid)
    if not d:
        abort(404)
    return d


@bp.route("/borgen/<pid>")
@staff_required
def deposit(pid):
    d = _deposit(pid)
    org = db.one("SELECT * FROM organizations WHERE id = ?", (d["org_id"],))
    prop = db.one("SELECT * FROM properties WHERE id = ?", (d["property_id"],))
    tenant = db.one("SELECT * FROM tenants WHERE id = ?", (d["tenant_id"],))
    docs = db.all_("SELECT * FROM documents WHERE deposit_id = ? ORDER BY id DESC", (d["id"],))
    acct = services.account_for(d)
    return render_template("admin/deposit.html", d=d, org=org, prop=prop, tenant=tenant, docs=docs, acct=acct, KINDS=KINDS,
                           balances=services.balances(d, acct), evidence_history=services.evidence_history(d),
                           bank_instructions=services.instructions_for(d), INSTRUCTION_KINDS=services.INSTRUCTION_KINDS,
                           INSTRUCTION_STATUSES=services.INSTRUCTION_STATUSES, rules=rules.for_deposit(d),
                           events=db.all_("SELECT * FROM deposit_events WHERE deposit_id = ? ORDER BY id DESC LIMIT 30", (d["id"],)))


@bp.route("/borgen/<pid>/bewijs", methods=["POST"])
@staff_required
def set_evidence(pid):
    d = _deposit(pid)
    level = request.form.get("level")
    if level not in ("verified", "legal"):
        abort(400)
    doc = request.form.get("document_id")
    try:
        services.set_evidence(d, level, g.user["id"], request.form.get("note"), int(doc) if doc and doc.isdigit() else None, staff=True)
        audit("deposit.evidence", f"deposit:{pid}", {"level": level}, org_id=d["org_id"])
        flash(f"Bewijsniveau vastgelegd: {S.EVIDENCE[level]['label']}.", "ok")
    except services.WorkflowError as exc:
        flash(str(exc), "error")
    return redirect(url_for("admin.deposit", pid=pid))


@bp.route("/documenten/<int:doc_id>")
@staff_required
def download(doc_id):
    doc = db.one("SELECT * FROM documents WHERE id = ?", (doc_id,))
    if not doc:
        abort(404)
    audit("document.downloaded", f"document:{doc_id}", {"by": "staff"}, org_id=doc["org_id"])
    return send_file(file_path(doc), mimetype=doc["mime"], as_attachment=True, download_name=doc["filename"])


# ------------------------------------------------------------ mail & audit

@bp.route("/mail")
@staff_required
def outbox():
    rows = db.all_("SELECT * FROM outbox_emails ORDER BY id DESC LIMIT 100")
    return render_template("admin/outbox.html", rows=rows)


@bp.route("/audit")
@staff_required
def audit_log():
    rows = db.all_("SELECT a.*, u.email FROM audit_log a LEFT JOIN users u ON u.id = a.user_id ORDER BY a.id DESC LIMIT 300")
    return render_template("admin/audit.html", rows=rows)


@bp.route("/postvak")
@staff_required
def dev_mailbox():
    """Old demo address: the outbox holds reset and invite links, so it is staff-only like /admin/mail."""
    return redirect(url_for("admin.outbox"))
