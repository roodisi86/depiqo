"""Depiqo Business: the workspace for property managers."""
import csv
import io
from datetime import timedelta

from flask import (Blueprint, Response, abort, current_app, flash, g, redirect, render_template, request,
                   send_file, url_for)

from .. import billing, db, finance, imports, providers, release_form, rules, services
from .. import states as S
from ..partners import bank, partner_status, send_mail
from ..security import PERMISSIONS, ROLE_LABELS, audit, can, org_required, require
from ..storage import KINDS, UploadError, file_path, save_upload
from ..util import (eur, now, now_iso, parse_date, parse_euros, sha256, today, token, valid_email, valid_iban)

bp = Blueprint("business", __name__, url_prefix="/app")


def deposit_or_404(pid):
    d = services.get_deposit(pid, org_id=g.org["id"])
    if not d:
        abort(404)
    return d


def deposit_rows(where="", params=(), limit=None):
    sql = ("SELECT d.*, p.address, p.city, p.postcode, t.name AS tenant_name, t.email AS tenant_email, b.provider AS bank_provider "
           "FROM deposits d JOIN properties p ON p.id = d.property_id JOIN tenants t ON t.id = d.tenant_id "
           "LEFT JOIN bank_accounts b ON b.deposit_id = d.id WHERE d.org_id = ? " + where +
           " ORDER BY d.updated_at DESC" + (f" LIMIT {int(limit)}" if limit else ""))
    return db.all_(sql, (g.org["id"], *params))


# ------------------------------------------------------------ dashboard

@bp.route("")
@org_required
def dashboard():
    org_id = g.org["id"]
    active_statuses = tuple(S.ACTIVE)
    ph = ",".join("?" * len(active_statuses))
    kpi = {
        "active": db.scalar(f"SELECT COUNT(*) FROM deposits WHERE org_id = ? AND status IN ({ph})", (org_id, *active_statuses)),
        # Only what is legally locked: a lock confirmed by the bank, or proven legal security for a deposit held elsewhere.
        "locked_value": db.scalar(
            "SELECT COALESCE(SUM(CASE WHEN holding = 'depiqo' THEN eligible_value_cents ELSE amount_cents END), 0) FROM deposits "
            "WHERE org_id = ? AND status NOT IN (?, ?) AND ((holding = 'depiqo' AND legal_lock_status = 'active' "
            "AND id IN (SELECT deposit_id FROM bank_accounts WHERE provider = ?)) "
            "OR (holding = 'external' AND evidence_level = 'legal'))", (org_id, S.CLOSED, S.CANCELLED, services.active_provider())),
        "declared_only": db.scalar("SELECT COUNT(*) FROM deposits WHERE org_id = ? AND holding = 'external' AND evidence_level IN ('declared', 'document') "
                                   "AND status NOT IN (?, ?)", (org_id, S.CLOSED, S.CANCELLED)),
        "awaiting": db.scalar("SELECT COUNT(*) FROM deposits WHERE org_id = ? AND status IN (?, ?, ?)",
                              (org_id, S.INVITED, S.ID_PENDING, S.AWAITING_PAYMENT)),
        "disputes": db.scalar("SELECT COUNT(*) FROM deposits WHERE org_id = ? AND status = ?", (org_id, S.DISPUTED)),
        "on_depiqo": db.scalar(f"SELECT COUNT(*) FROM deposits WHERE org_id = ? AND holding = 'depiqo' AND status IN ({ph})", (org_id, *active_statuses)),
        "interest": db.scalar("SELECT COALESCE(SUM(b.ledger_interest_cents), 0) FROM bank_accounts b JOIN deposits d ON d.id = b.deposit_id WHERE d.org_id = ?", (org_id,)),
    }
    groups = services.action_centre(org_id)
    kpi["due_soon"] = len({i["d"]["id"] for grp in groups for i in grp["tasks"] if i["deadline"] and i["deadline"]["days_left"] <= 7})
    kpi["tasks"] = sum(len(grp["tasks"]) for grp in groups)
    events = db.all_("SELECT e.*, d.pid, d.reference FROM deposit_events e JOIN deposits d ON d.id = e.deposit_id "
                     "WHERE e.org_id = ? ORDER BY e.id DESC LIMIT 8", (org_id,))
    places, places_total = providers.overview(org_id)
    return render_template("business/dashboard.html", kpi=kpi, groups=groups, events=events, partner=partner_status(),
                           places=places, places_total=places_total,
                           est=billing.estimate(g.org, today().strftime("%Y-%m")) if can("billing.view") else None)


# ------------------------------------------------------------ list & create

FILTERS = {
    "actie": ("Actie nodig", (S.CONCEPT, S.AWAITING_PAYMENT, S.MOVE_OUT, S.DISPUTED, S.AGREED, S.ID_FAILED, S.LEGAL_HOLD)),
    "lopend": ("Lopend", tuple(S.ACTIVE)),
    "gesloten": ("Gesloten", (S.CLOSED, S.CANCELLED)),
    "alle": ("Alle", None),
}


@bp.route("/borgen")
@org_required
def deposits():
    f = request.args.get("filter", "lopend")
    if f not in FILTERS:
        f = "lopend"
    where, params = "", []
    statuses = FILTERS[f][1]
    if statuses:
        where += f" AND d.status IN ({','.join('?' * len(statuses))})"
        params += list(statuses)
    region = request.args.get("regio")
    if region in rules.REGIONS:
        where += " AND d.region = ?"
        params.append(region)
    holding = request.args.get("waar")
    if holding in ("depiqo", "external"):
        where += " AND d.holding = ?"
        params.append(holding)
    evidence = request.args.get("bewijs")
    if evidence in S.EVIDENCE:
        where += " AND d.evidence_level = ?"
        params.append(evidence)
    place = request.args.get("aanbieder")
    if place == "depiqo":
        where += " AND d.holding = 'depiqo'"
    elif place == "onbekend":
        where += " AND d.holding = 'external' AND d.provider_kind IS NULL"
    elif place in providers.PROVIDER_KINDS:
        where += " AND d.holding = 'external' AND d.provider_kind = ?"
        params.append(place)
    else:
        place = None
    q = (request.args.get("q") or "").strip()
    if q:
        where += " AND (p.address LIKE ? OR t.name LIKE ? OR d.reference LIKE ? OR p.city LIKE ?)"
        like = f"%{q[:60]}%"
        params += [like, like, like, like]
    rows = deposit_rows(where, params, limit=500)
    deadlines = {r["id"]: services.deadline_info(r) for r in rows}
    return render_template("business/deposits.html", rows=rows, f=f, FILTERS=FILTERS, q=q, region=region, waar=holding,
                           evidence=evidence, place=place, deadlines=deadlines, REGIONS=rules.REGIONS)


@bp.route("/borgen/nieuw", methods=["GET", "POST"])
@org_required
def new_deposit():
    require("deposit.edit")
    props = db.all_("SELECT * FROM properties WHERE org_id = ? ORDER BY address", (g.org["id"],))
    partner = partner_status()
    form = request.form if request.method == "POST" else {"region": "NL", "holding": "depiqo" if partner["available"] else "external",
                                                           "lease_start": today().isoformat()}
    error = None
    if request.method == "POST":
        rent = parse_euros(form.get("rent"))
        amount = parse_euros(form.get("amount"))
        email = (form.get("tenant_email") or "").strip().lower()
        iban = (form.get("external_iban") or "").replace(" ", "").upper() or None
        external = form.get("holding") == "external"
        prov, prov_errors = providers.clean_fields(form) if external else ({}, [])
        if external and providers.parse_kind(form.get("provider_kind")) in providers.NO_TENANT_PAYMENT:
            iban = None  # the tenant pays nobody: a stray IBAN in the hidden field is not kept
        if external and prov.get("provider_kind") not in providers.GUARANTEE_KINDS:
            prov["guarantee_expires_on"] = None  # the field is hidden for other kinds; a leftover value is not kept
        if not valid_email(email):
            error = "Vul een geldig e-mailadres van de huurder in."
        elif external and iban and not valid_iban(iban):
            error = "Dat rekeningnummer (IBAN) klopt niet."
        elif prov_errors:
            error = " ".join(prov_errors)
        else:
            prop_id = form.get("property_id")
            data = {"property_id": int(prop_id) if prop_id and prop_id.isdigit() else None,
                    "address": form.get("address", ""), "postcode": form.get("postcode", ""), "city": form.get("city", ""),
                    "region": form.get("region"), "tenant_name": form.get("tenant_name", ""), "tenant_email": email,
                    "tenant_phone": form.get("tenant_phone") or None, "rent_cents": rent or 0, "amount_cents": amount or 0,
                    "holding": form.get("holding"), "lease_start": form.get("lease_start"), "lease_end": form.get("lease_end") or None,
                    "external_iban": iban if external else None, **prov}
            if data["property_id"]:
                prop = db.one("SELECT region FROM properties WHERE id = ? AND org_id = ?", (data["property_id"], g.org["id"]))
                if prop:
                    data["region"] = prop["region"]
            try:
                d = services.create_deposit(g.org["id"], g.user["id"], data)
                audit("deposit.created", f"deposit:{d['pid']}", {"provider_kind": d["provider_kind"]} if d["provider_kind"] else None)
                for w in providers.warnings_for(d):
                    flash(w, "warn")
                if form.get("send_invite"):
                    services.send_invite(d, g.user["id"])
                    flash("Dossier aangemaakt en uitnodiging verstuurd.", "ok")
                else:
                    flash("Dossier opgeslagen als concept.", "ok")
                return redirect(url_for("business.deposit", pid=d["pid"]))
            except services.WorkflowError as exc:
                error = str(exc)
    return render_template("business/new_deposit.html", props=props, form=form, error=error, REGIONS=rules.REGIONS,
                           plan=billing.plan_for(g.org), partner=partner, RULE_VERSION=rules.RULE_VERSION)


@bp.route("/borgen/<pid>/aanbieder", methods=["GET", "POST"])
@org_required
def edit_provider(pid):
    """Record or correct where a deposit held elsewhere sits (admin and manager, while the dossier runs)."""
    require("deposit.edit")
    d = deposit_or_404(pid)
    if d["holding"] != "external" or d["status"] in (S.CLOSED, S.CANCELLED):
        flash("Waar de borg staat, pas je alleen aan bij een lopende borg die elders staat.", "error")
        return redirect(url_for("business.deposit", pid=pid))
    prop = db.one("SELECT * FROM properties WHERE id = ?", (d["property_id"],))
    form = request.form if request.method == "POST" else {k: d[k] or "" for k in services.PROVIDER_FIELDS}
    error = None
    if request.method == "POST":
        fields, errors = providers.clean_fields(form)
        iban = (form.get("external_iban") or "").replace(" ", "").upper() or None
        if fields["provider_kind"] in providers.NO_TENANT_PAYMENT:
            iban = None
        if fields["provider_kind"] not in providers.GUARANTEE_KINDS:
            fields["guarantee_expires_on"] = None
        if iban and not valid_iban(iban):
            errors.append("Dat rekeningnummer (IBAN) klopt niet.")
        if errors:
            error = " ".join(errors)
        else:
            try:
                d, changes = services.update_provider(d, g.user["id"], {**fields, "external_iban": iban})
                if changes:
                    audit("deposit.provider_updated", f"deposit:{pid}", {k: {"van": old, "naar": new} for k, (old, new) in changes.items()})
                    flash("Gegevens van de aanbieder opgeslagen.", "ok")
                    for w in providers.warnings_for(d):
                        flash(w, "warn")
                else:
                    flash("Er is niets gewijzigd.", "ok")
                return redirect(url_for("business.deposit", pid=pid) + "#aanbieder")
            except services.WorkflowError as exc:
                error = str(exc)
    return render_template("business/edit_provider.html", d=d, prop=prop, form=form, error=error, rules=rules.for_deposit(d),
                           locked=d["evidence_level"] in ("verified", "legal"))


@bp.route("/borgen/<pid>/vrijgaveformulier.pdf")
@org_required
def release_form_pdf(pid):
    require("deposit.view")
    d = deposit_or_404(pid)
    if not services.release_form_available(d):
        abort(404)
    pdf = release_form.build(d)
    audit("deposit.release_form", f"deposit:{pid}")
    services.add_event(d, "user", "document", "Vrijgaveformulier gedownload", g.user["id"])
    return Response(pdf, mimetype="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename=vrijgaveformulier-{d['reference']}.pdf"})


# ------------------------------------------------------------ detail & actions

@bp.route("/borgen/<pid>")
@org_required
def deposit(pid):
    d = deposit_or_404(pid)
    prop = db.one("SELECT * FROM properties WHERE id = ?", (d["property_id"],))
    tenant = db.one("SELECT * FROM tenants WHERE id = ?", (d["tenant_id"],))
    events = db.all_("SELECT e.*, u.name AS user_name FROM deposit_events e LEFT JOIN users u ON u.id = e.actor_user_id "
                     "WHERE e.deposit_id = ? ORDER BY e.id DESC", (d["id"],))
    docs = db.all_("SELECT * FROM documents WHERE deposit_id = ? ORDER BY id DESC", (d["id"],))
    acct = services.account_for(d)
    settlement = services.current_settlement(d)
    lines = services.settlement_lines(settlement)
    dispute = services.open_dispute(d) or db.one("SELECT * FROM disputes WHERE deposit_id = ? ORDER BY id DESC LIMIT 1", (d["id"],))
    instructions, pay_problem = services.payment_details(d, g.org) if d["holding"] == "depiqo" else (None, None)
    return render_template("business/deposit.html", d=d, prop=prop, tenant=tenant, events=events, docs=docs, acct=acct,
                           settlement=settlement, lines=lines, total=services.settlement_total(settlement), dispute=dispute,
                           deadline=services.deadline_info(d), rules=rules.for_deposit(d), KINDS=KINDS,
                           CATEGORIES=services.CATEGORIES, instructions=instructions, pay_problem=pay_problem,
                           split=services.payout_split(d) if d["status"] == S.AGREED else None,
                           SECURITY_TYPES=services.SECURITY_TYPES, LOCK_STATUSES=services.LOCK_STATUSES,
                           coverage=services.coverage_bps(d), balances=services.balances(d, acct),
                           evidence_history=services.evidence_history(d), bank_instructions=services.instructions_for(d),
                           INSTRUCTION_KINDS=services.INSTRUCTION_KINDS, INSTRUCTION_STATUSES=services.INSTRUCTION_STATUSES,
                           mails=services.mails_for(d), partner=partner_status(), can_invite=services.can_invite(d),
                           provider_warnings=providers.warnings_for(d), release_form=services.release_form_available(d),
                           release_basis=services.release_basis(d) if d["status"] in (S.AGREED, S.CLOSED) else None,
                           expiry=providers.expiry_info(d),
                           max_amount=rules.max_amount_cents(d["region"], d["rent_cents"], d["lease_start"], d["rule_version"]))


ACTIONS = {
    "uitnodigen": "deposit.edit", "annuleren": "deposit.edit", "ontvangst": "deposit.confirm_receipt",
    "bewijs": "deposit.confirm_receipt", "herinneren": "deposit.remind",
    "vertrek": "deposit.edit", "afrekening-opslaan": "settlement.edit", "afrekening-voorstellen": "settlement.edit",
    "geschil-afsluiten": "dispute.resolve", "uitbetalen": "deposit.payout", "vrijgave": "deposit.payout", "blokkade": "deposit.legal_hold",
    "blokkade-opheffen": "deposit.legal_hold",
}


def _doc_id(name):
    raw = request.form.get(name)
    return int(raw) if raw and raw.isdigit() else None


@bp.route("/borgen/<pid>/<action>", methods=["POST"])
@org_required
def deposit_action(pid, action):
    if action not in ACTIONS:
        abort(404)
    require(ACTIONS[action])
    d = deposit_or_404(pid)
    uid = g.user["id"]
    try:
        if action == "uitnodigen":
            services.send_invite(d, uid)
            flash("Uitnodiging verstuurd naar de huurder.", "ok")
        elif action == "annuleren":
            services.cancel(d, uid, request.form.get("reason"))
            flash("Dossier geannuleerd.", "ok")
        elif action == "ontvangst":
            d = services.confirm_external_receipt(d, uid, _doc_id("document_id"))
            if d["evidence_level"] == "document":
                flash("Ontvangst verklaard met bankbewijs. Depiqo kan de ontvangst nog extern verifiëren.", "ok")
            else:
                flash("Ontvangst verklaard. Dit is nog geen bewijs: voeg een bankbewijs toe om het bewijsniveau te verhogen.", "ok")
        elif action == "bewijs":
            services.set_evidence(d, "document", uid, request.form.get("note"), _doc_id("document_id"))
            flash("Bankbewijs vastgelegd. Het bewijsniveau is nu 'bankdocument ontvangen'.", "ok")
        elif action == "herinneren":
            services.send_payment_reminder(d, uid)
            flash("Betaalherinnering verstuurd.", "ok")
        elif action == "vertrek":
            services.start_move_out(d, uid, request.form.get("move_out_date"))
            flash("Vertrek gestart. Stel nu de eindafrekening op.", "ok")
        elif action == "afrekening-opslaan":
            lines = []
            for i in range(10):
                desc = (request.form.get(f"desc_{i}") or "").strip()
                amount = parse_euros(request.form.get(f"amount_{i}"))
                if not desc and not amount:
                    continue
                doc = request.form.get(f"doc_{i}")
                lines.append({"category": request.form.get(f"cat_{i}"), "description": desc, "amount_cents": amount or 0,
                              "document_id": int(doc) if doc and doc.isdigit() else None})
            services.save_settlement(d, uid, lines)
            flash("Concept-afrekening opgeslagen.", "ok")
        elif action == "afrekening-voorstellen":
            services.propose_settlement(d, uid)
            flash("Afrekening voorgesteld. De huurder krijgt een bericht.", "ok")
        elif action == "geschil-afsluiten":
            services.resolve_dispute(d, uid, request.form.get("kind"), parse_euros(request.form.get("landlord_amount")),
                                     request.form.get("note"), _doc_id("document_id"))
            flash("Uitkomst van het geschil vastgelegd.", "ok")
        elif action == "vrijgave":
            services.confirm_external_release(d, uid, _doc_id("document_id"))
            flash("Vrijgave bij de aanbieder bevestigd. Het dossier is gesloten.", "ok")
        elif action == "uitbetalen":
            d = services.start_payout(d, uid, _doc_id("document_id"))
            if d["holding"] != "depiqo":
                flash("Vrijgave bij de aanbieder bevestigd. Het dossier is gesloten.", "ok")
            else:
                instr = db.one("SELECT status FROM bank_instructions WHERE deposit_id = ? AND kind = 'release'", (d["id"],))
                flash("Uitbetaling gestart. De bank heeft de vrijgave-opdracht aangenomen." if instr and instr["status"] == "acknowledged"
                      else "Uitbetaling gestart. De vrijgave-opdracht staat klaar en wordt naar de bank gestuurd.", "ok")
        elif action == "blokkade":
            services.set_legal_hold(d, uid, True, request.form.get("reason"))
            flash("Juridische blokkade ingesteld.", "ok")
        elif action == "blokkade-opheffen":
            services.set_legal_hold(d, uid, False, None)
            flash("Blokkade opgeheven.", "ok")
        audit(f"deposit.{action}", f"deposit:{pid}")
    except services.WorkflowError as exc:
        flash(str(exc), "error")
    if request.form.get("next") == "dashboard":
        return redirect(url_for("business.dashboard"))
    return redirect(url_for("business.deposit", pid=pid))


@bp.route("/borgen/<pid>/documenten", methods=["POST"])
@org_required
def upload(pid):
    require("document.upload")
    d = deposit_or_404(pid)
    try:
        doc_id = save_upload(request.files.get("file"), d, request.form.get("kind"), "user", g.user["id"])
        services.add_event(d, "user", "document", f"Document toegevoegd: {KINDS[request.form.get('kind')]}", g.user["id"])
        audit("document.uploaded", f"document:{doc_id}")
        flash("Document toegevoegd.", "ok")
    except UploadError as exc:
        flash(str(exc), "error")
    return redirect(url_for("business.deposit", pid=pid) + "#documenten")


@bp.route("/documenten/<int:doc_id>")
@org_required
def download(doc_id):
    doc = db.one("SELECT * FROM documents WHERE id = ? AND org_id = ?", (doc_id, g.org["id"]))
    if not doc:
        abort(404)
    audit("document.downloaded", f"document:{doc_id}")
    return send_file(file_path(doc), mimetype=doc["mime"], as_attachment=True, download_name=doc["filename"])


@bp.route("/borgen/<pid>/sandbox/<event>", methods=["POST"])
@org_required
def sandbox(pid, event):
    if not current_app.config["SANDBOX"]:
        abort(404)
    require("deposit.confirm_receipt")  # simulating the bank is as strong as confirming receipt
    d = deposit_or_404(pid)
    acct = services.account_for(d)
    if not acct:
        flash("Er is nog geen borgrekening.", "error")
        return redirect(url_for("business.deposit", pid=pid))
    if acct["provider"] != "sandbox":
        abort(404)  # never simulate events for an account at a real partner
    partner = bank()
    if not getattr(partner, "is_sandbox", False):
        abort(404)
    mapping = {"storting": ("deposit.received", d["amount_cents"]), "blokkering": ("account.blocked", None),
               "rente": ("interest.credited", max(1, round(acct["ledger_balance_cents"] * acct["interest_rate_bps"] / 10000 / 12))),
               "uitbetaling": ("payout.completed", None)}
    if event not in mapping:
        abort(404)
    expected = {"storting": d["status"] == S.AWAITING_PAYMENT, "blokkering": d["status"] == S.PAYMENT_RECEIVED,
                "rente": acct["status"] in ("open", "blocked") and acct["ledger_balance_cents"] > 0,
                "uitbetaling": d["status"] == S.PAYOUT_PENDING and acct["status"] == "release_requested" and db.scalar(
                    "SELECT COUNT(*) FROM bank_instructions WHERE bank_account_id = ? AND kind = 'release' AND status IN ('sent', 'acknowledged')",
                    (acct["id"],)) > 0}
    if not expected[event]:
        flash("Dit bankbericht past niet bij de huidige stap van het dossier.", "error")
        return redirect(url_for("business.deposit", pid=pid))
    etype, amount = mapping[event]
    payload = partner.simulate(etype, acct, amount)
    try:
        result = services.handle_bank_event(partner.name, etype, payload)
        if result == "mismatch":
            flash("Sandbox-bank: de uitbetaling wijkt af van de opdracht. Het dossier blijft open.", "error")
        else:
            flash("Sandbox-bank: bericht verwerkt.", "ok")
    except services.WorkflowError as exc:
        flash(str(exc), "error")
    return redirect(url_for("business.deposit", pid=pid))


# ------------------------------------------------------------ bulk actions

BULK = {"uitnodigen": "deposit.edit", "herinneren": "deposit.remind", "export": "export"}


@bp.route("/borgen/bulk", methods=["POST"])
@org_required
def bulk():
    action = request.form.get("action")
    if action not in BULK:
        abort(400)
    require(BULK[action])
    pids = [p for p in request.form.getlist("pids") if p][:500]
    back = url_for("business.deposits", filter=request.form.get("filter") or "lopend")
    if not pids:
        flash("Selecteer eerst een of meer dossiers.", "error")
        return redirect(back)
    ph = ",".join("?" * len(pids))
    rows = deposit_rows(f" AND d.pid IN ({ph})", pids)  # only this organisation's dossiers
    if action == "export":
        audit("export.csv", "deposits:selection", {"count": len(rows)})
        return _csv_response(rows, f"depiqo-selectie-{today().isoformat()}.csv")
    done, skipped, reasons = 0, 0, {}
    for d in rows:
        try:
            if action == "uitnodigen":
                if not services.can_invite(d):
                    raise services.WorkflowError("Status laat geen uitnodiging toe")
                services.send_invite(d, g.user["id"])
            else:
                services.send_payment_reminder(d, g.user["id"])
            done += 1
        except services.WorkflowError as exc:
            skipped += 1
            reasons[str(exc)] = reasons.get(str(exc), 0) + 1
    skipped += len(pids) - len(rows)
    audit(f"deposit.bulk_{action}", "deposits:selection", {"done": done, "skipped": skipped})
    noun = ("uitnodiging" if done == 1 else "uitnodigingen") if action == "uitnodigen" else ("herinnering" if done == 1 else "herinneringen")
    flash(f"{done} {noun} verstuurd, {skipped} overgeslagen." + (" Overgeslagen omdat: " + "; ".join(
        f"{k.rstrip('.')} ({v})" for k, v in list(reasons.items())[:3]) + "." if reasons else ""), "ok" if done else "error")
    return redirect(back)


# ------------------------------------------------------------ properties

@bp.route("/panden", methods=["GET", "POST"])
@org_required
def properties():
    error = None
    if request.method == "POST":
        require("deposit.edit")
        f = request.form
        if not (f.get("address") and f.get("postcode") and f.get("city")) or f.get("region") not in rules.REGIONS:
            error = "Vul adres, postcode, plaats en regio in."
        else:
            db.run("INSERT INTO properties (org_id, address, postcode, city, region, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                   (g.org["id"], f["address"].strip(), f["postcode"].strip().upper(), f["city"].strip(), f["region"], now_iso()))
            flash("Pand toegevoegd.", "ok")
            return redirect(url_for("business.properties"))
    rows = db.all_("SELECT p.*, (SELECT COUNT(*) FROM deposits d WHERE d.property_id = p.id AND d.status NOT IN (?, ?)) AS open_count "
                   "FROM properties p WHERE p.org_id = ? ORDER BY p.city, p.address", (S.CLOSED, S.CANCELLED, g.org["id"]))
    return render_template("business/properties.html", rows=rows, error=error, REGIONS=rules.REGIONS)


# ------------------------------------------------------------ team

@bp.route("/team", methods=["GET", "POST"])
@org_required
def team():
    error = None
    if request.method == "POST":
        require("team.manage")
        email = (request.form.get("email") or "").strip().lower()
        role = request.form.get("role")
        if not valid_email(email) or role not in ROLE_LABELS:
            error = "Vul een geldig e-mailadres in en kies een rol."
        elif db.one("SELECT 1 FROM memberships m JOIN users u ON u.id = m.user_id WHERE m.org_id = ? AND u.email = ?", (g.org["id"], email)):
            error = "Deze persoon is al lid van je organisatie."
        else:
            raw = token()
            db.run("INSERT INTO invitations (org_id, email, role, token_hash, invited_by, expires_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (g.org["id"], email, role, sha256(raw), g.user["id"], (now() + timedelta(days=7)).isoformat(timespec="seconds"), now_iso()))
            send_mail(email, f"Uitnodiging voor {g.org['name']} op Depiqo",
                      f"{g.user['name']} nodigt je uit voor {g.org['name']} op Depiqo als {ROLE_LABELS[role].lower()}.\n\n"
                      f"Accepteer binnen 7 dagen: {services.base_url()}/uitnodiging/{raw}\n")
            audit("team.invited", f"email:{email}", {"role": role})
            flash(f"Uitnodiging verstuurd naar {email}.", "ok")
            return redirect(url_for("business.team"))
    members = db.all_("SELECT m.*, u.name, u.email, u.last_login_at FROM memberships m JOIN users u ON u.id = m.user_id "
                      "WHERE m.org_id = ? ORDER BY u.name", (g.org["id"],))
    invites = db.all_("SELECT * FROM invitations WHERE org_id = ? AND accepted_at IS NULL ORDER BY id DESC", (g.org["id"],))
    return render_template("business/team.html", members=members, invites=invites, error=error, PERMISSIONS=PERMISSIONS)


@bp.route("/team/<int:member_id>", methods=["POST"])
@org_required
def team_member(member_id):
    require("team.manage")
    m = db.one("SELECT * FROM memberships WHERE id = ? AND org_id = ?", (member_id, g.org["id"]))
    if not m:
        abort(404)
    admins = db.scalar("SELECT COUNT(*) FROM memberships WHERE org_id = ? AND role = 'admin'", (g.org["id"],))
    if request.form.get("remove"):
        if m["role"] == "admin" and admins <= 1:
            flash("Er moet minstens één beheerder overblijven.", "error")
        else:
            db.run("DELETE FROM memberships WHERE id = ?", (m["id"],))
            db.run("DELETE FROM sessions WHERE user_id = ? AND active_org_id = ?", (m["user_id"], g.org["id"]))
            audit("team.removed", f"user:{m['user_id']}")
            flash("Toegang ingetrokken.", "ok")
    else:
        role = request.form.get("role")
        if role not in ROLE_LABELS:
            abort(400)
        if m["role"] == "admin" and role != "admin" and admins <= 1:
            flash("Er moet minstens één beheerder overblijven.", "error")
        else:
            db.run("UPDATE memberships SET role = ? WHERE id = ?", (role, m["id"]))
            audit("team.role_changed", f"user:{m['user_id']}", {"from": m["role"], "to": role})
            flash("Rol aangepast.", "ok")
    return redirect(url_for("business.team"))


# ------------------------------------------------------------ billing

def last_month():
    first = today().replace(day=1)
    prev = first - timedelta(days=1)
    return prev.strftime("%Y-%m")


@bp.route("/facturatie", methods=["GET", "POST"])
@org_required
def billing_page():
    require("billing.view")
    if request.method == "POST":
        require("billing.issue")
        period = (request.form.get("period") or last_month()).strip()
        if not billing.valid_period(g.org, period):
            flash("Kies een geldige maand (JJJJ-MM) na de start van je organisatie.", "error")
        elif period >= today().strftime("%Y-%m"):
            flash("Een factuur maak je pas na afloop van de maand.", "error")
        else:
            try:
                inv = billing.issue_invoice(g.org, period)
                audit("invoice.issued", f"invoice:{inv['number']}")
                flash(f"Factuur {inv['number']} aangemaakt.", "ok")
            except ValueError as exc:
                flash(str(exc), "error")
        return redirect(url_for("business.billing_page"))
    current = billing.estimate(g.org, today().strftime("%Y-%m"))
    previous = billing.estimate(g.org, last_month())
    invoices = db.all_("SELECT * FROM invoices WHERE org_id = ? ORDER BY period DESC, id DESC", (g.org["id"],))
    issued_prev = any(i["period"] == last_month() and i["kind"] == "invoice" and i["status"] == "issued" for i in invoices)
    chosen = billing.plan_for(g.org)
    upcoming = billing.plan_on(g.org, billing.next_month_start())
    return render_template("business/billing.html", current=current, previous=previous, invoices=invoices,
                           issued_prev=issued_prev, last_month=last_month(), B=billing, plan=current["plan"], chosen=chosen,
                           upcoming=upcoming if upcoming["code"] != current["plan"]["code"] else None,
                           next_month=billing.next_month_start(), history=billing.plan_history(g.org["id"]))


@bp.route("/facturatie/plan", methods=["POST"])
@org_required
def change_plan():
    require("billing.issue")
    new = request.form.get("plan")
    old = g.org["plan"]
    starts = billing.next_month_start()
    if old not in billing.SELF_SERVICE:
        flash("Je hebt een Enterprise-plan. Neem contact op met Depiqo om het te wijzigen.", "error")
    elif new not in billing.SELF_SERVICE:
        flash("Enterprise is op aanvraag. Neem contact op met Depiqo.", "error")
    elif new == old:
        flash(f"Je hebt al het plan {billing.PLANS[new]['label']}.", "ok")
    else:
        billing.record_plan_change(g.org, new, None, starts, g.user["id"])
        audit("billing.plan_changed", f"org:{g.org['id']}", {"from": old, "to": new, "valid_from": starts.isoformat()})
        from ..util import date_nl
        flash(f"Je plan wordt {billing.PLANS[new]['label']}. Het geldt vanaf {date_nl(starts)}.", "ok")
    return redirect(url_for("business.billing_page"))


@bp.route("/facturatie/<number>.pdf")
@org_required
def invoice_pdf(number):
    require("billing.view")
    inv = db.one("SELECT * FROM invoices WHERE number = ? AND org_id = ?", (number, g.org["id"]))
    if not inv:
        abort(404)
    pdf = billing.invoice_pdf(inv, g.org)
    return Response(pdf, mimetype="application/pdf", headers={"Content-Disposition": f"attachment; filename={number}.pdf"})


# ------------------------------------------------------------ reconciliation (finance)

@bp.route("/afstemming")
@org_required
def reconciliation():
    require("reconciliation.view")
    only = request.args.get("alles") != "1"
    rows, totals = finance.reconciliation(org_id=g.org["id"], only_exceptions=only)
    return render_template("business/reconciliation.html", rows=rows, totals=totals, only=only)


# ------------------------------------------------------------ import

@bp.route("/borgen/import", methods=["GET", "POST"])
@org_required
def import_upload():
    require("deposit.import")
    error = None
    if request.method == "POST":
        f = request.files.get("file")
        if not f or not f.filename:
            error = "Kies een CSV-bestand."
        else:
            data = f.read(current_app.config["IMPORT_MAX_BYTES"] + 1)
            try:
                batch_id = imports.create_batch(g.org["id"], g.user["id"], f.filename, data)
                audit("deposit.import_preview", f"import:{batch_id}")
                return redirect(url_for("business.import_preview", batch_id=batch_id))
            except imports.ImportProblem as exc:
                error = str(exc)
    recent = db.all_("SELECT * FROM import_batches WHERE org_id = ? ORDER BY id DESC LIMIT 5", (g.org["id"],))
    return render_template("business/import.html", error=error, recent=recent, COLUMNS=imports.COLUMNS, REQUIRED=imports.REQUIRED,
                           max_rows=current_app.config["IMPORT_MAX_ROWS"], partner=partner_status())


@bp.route("/borgen/import/sjabloon.csv")
@org_required
def import_template():
    require("deposit.import")
    return Response(imports.template_csv(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=depiqo-import-sjabloon.csv"})


@bp.route("/borgen/import/<int:batch_id>")
@org_required
def import_preview(batch_id):
    require("deposit.import")
    batch, rows = imports.get_batch(batch_id, g.org["id"])
    if not batch:
        abort(404)
    show = request.args.get("toon")
    shown = [r for r in rows if r["errors"]] if show == "fouten" else rows
    return render_template("business/import_preview.html", batch=batch, rows=shown[:1000], total=len(rows), show=show,
                           warn_count=sum(1 for r in rows if r.get("warnings")),
                           LABELS=imports.LABELS, REGIONS=rules.REGIONS, truncated=len(shown) > 1000)


@bp.route("/borgen/import/<int:batch_id>/<action>", methods=["POST"])
@org_required
def import_action(batch_id, action):
    require("deposit.import")
    batch, _ = imports.get_batch(batch_id, g.org["id"])
    if not batch:
        abort(404)
    if action == "annuleren":
        if batch["status"] == "preview":
            db.run("UPDATE import_batches SET status = 'discarded' WHERE id = ?", (batch_id,))
            flash("Import geannuleerd. Er is niets toegevoegd.", "ok")
        return redirect(url_for("business.import_upload"))
    if action != "bevestigen":
        abort(404)
    try:
        n, invited = imports.commit_batch(batch, g.user["id"], send_invites=request.form.get("send_invites") == "1")
        audit("deposit.imported", f"import:{batch_id}", {"count": n, "invited": invited})
        flash(f"{n} borgen geïmporteerd." + (f" {invited} huurders uitgenodigd." if invited else " Er zijn geen uitnodigingen verstuurd."), "ok")
        return redirect(url_for("business.deposits", filter="alle"))
    except services.WorkflowError as exc:
        flash(str(exc), "error")
        return redirect(url_for("business.import_preview", batch_id=batch_id))


# ------------------------------------------------------------ export & settings

CSV_HEADER = ["kenmerk", "adres", "plaats", "regio", "huurder", "borg_eur", "waar", "aanbieder_soort", "aanbieder", "referentie_aanbieder",
              "garantie_tot", "status", "bewijsniveau", "ontvangen_eur", "bevestigd_geblokkeerd_eur", "start_huur", "vertrek", "aangemaakt",
              "sandbox"]


def _money(cents):
    return "" if cents is None else f"{cents / 100:.2f}".replace(".", ",")


def _csv_response(rows, filename):
    out = io.StringIO()
    w = csv.writer(out, delimiter=";")
    w.writerow(CSV_HEADER)
    for r in rows:
        figures = {f["key"]: f["value"] for f in services.balances(r)}
        a = services.assurance(r)
        w.writerow([_csv_safe(r["reference"]), _csv_safe(r["address"]), _csv_safe(r["city"]), r["region"], _csv_safe(r["tenant_name"]),
                    _money(r["amount_cents"]), "Depiqo-borgrekening" if r["holding"] == "depiqo" else "Elders",
                    r["provider_kind"] or ("" if r["holding"] == "depiqo" else "onbekend"), _csv_safe(r["provider_name"]),
                    _csv_safe(r["provider_reference"]), r["guarantee_expires_on"] or "",
                    _csv_safe(services.display_status(r)[0]), _csv_safe(a["label"] if a else ""), _money(figures.get("received")),
                    _money(figures.get("locked")), r["lease_start"], r["move_out_date"] or "", r["created_at"][:10],
                    "ja" if r["bank_provider"] == "sandbox" else ""])
    return Response("﻿" + out.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename={filename}"})


@bp.route("/export.csv")
@org_required
def export():
    require("export")
    audit("export.csv", "deposits")
    return _csv_response(deposit_rows(), f"depiqo-borgen-{today().isoformat()}.csv")


def _csv_safe(value):
    """Prevents spreadsheet formula injection."""
    s = str(value or "")
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


@bp.route("/instellingen", methods=["GET", "POST"])
@org_required
def settings():
    error = None
    if request.method == "POST":
        require("settings.edit")
        name = " ".join((request.form.get("name") or "").split())  # no newlines or control whitespace
        billing_email = (request.form.get("billing_email") or "").strip().lower()
        if not name or (billing_email and not valid_email(billing_email)):
            error = "Vul een naam en een geldig e-mailadres in."
        else:
            db.run("UPDATE organizations SET name = ?, registration_number = ?, billing_email = ? WHERE id = ?",
                   (name[:120], (request.form.get("registration_number") or "").strip()[:40] or None, billing_email or None, g.org["id"]))
            audit("org.updated", f"org:{g.org['id']}")
            flash("Instellingen opgeslagen.", "ok")
            return redirect(url_for("business.settings"))
    orgs = db.all_("SELECT o.* FROM organizations o JOIN memberships m ON m.org_id = o.id WHERE m.user_id = ?", (g.user["id"],))
    return render_template("business/settings.html", error=error, orgs=orgs, REGIONS=rules.REGIONS, RULE_VERSION=rules.RULE_VERSION)
