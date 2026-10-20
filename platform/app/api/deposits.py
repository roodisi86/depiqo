"""Deposits as the tenant sees them: overview, detail, identity, documents, settlement, release form and
doorbeleggen. Every rule is the one of the web wallet (services.py, investing.py)."""
import json

from flask import Response, g, jsonify, request, send_file

from .. import db, investing, providers, release_form, rules, services
from .. import states as S
from ..security import NO_ORG, audit
from ..storage import KINDS, UploadError, file_path, save_upload
from . import ApiError, body, bp, field_error, idempotent, iso_date, money, page_args, paged, str_field, tenant_api, true_field
from .me import TENANT_EVENT_TYPES

TENANT_UPLOAD_KINDS = ("photo", "inspection", "other")  # what a tenant adds in the wallet (same choice as the web form)

STEP_LABELS = {"invited": "Uitnodiging", "id_pending": "Identiteit", "awaiting_payment": "Storten", "secured": "Borg veilig",
               "move_out": "Vertrek", "settlement": "Afrekening", "payout": "Uitbetaling", "closed": "Afgerond"}
STEP_OF = {S.CONCEPT: "invited", S.INVITED: "invited", S.ID_PENDING: "id_pending", S.ID_FAILED: "id_pending",
           S.AWAITING_PAYMENT: "awaiting_payment", S.PAYMENT_RECEIVED: "secured", S.SECURED: "secured", S.MOVE_OUT: "move_out",
           S.SETTLEMENT_PROPOSED: "settlement", S.DISPUTED: "settlement", S.AGREED: "payout", S.PAYOUT_PENDING: "payout", S.CLOSED: "closed"}


def my_deposit(pid):
    d = services.get_deposit(pid, tenant_ids=g.tenant_ids)
    if not d or d["status"] == S.CONCEPT:
        raise ApiError(404, "not_found", "Deze borg bestaat niet of is niet van jou.")
    return d


def progress(d):
    steps = ["invited", "id_pending", "awaiting_payment", "secured", "move_out", "settlement", "payout", "closed"]
    labels = dict(STEP_LABELS)
    if d["holding"] == "external":
        steps.remove("id_pending")
        labels["secured"] = "Borg geregistreerd"
        labels["payout"] = "Vrijgave"
        if d["provider_kind"] in providers.NO_TENANT_PAYMENT:
            labels["awaiting_payment"] = "Borg regelen"
    status = d["status"]
    if status == S.LEGAL_HOLD:
        status = d["hold_previous_status"] or S.SECURED
    current = STEP_OF.get(status)
    idx = steps.index(current) if current in steps else -1
    out = []
    for i, code in enumerate(steps):
        if d["status"] == S.CANCELLED:
            state = "cancelled"
        elif current == "closed" or i < idx:
            state = "done"
        elif i == idx:
            state = "current"
        else:
            state = "upcoming"
        out.append({"code": code, "label": labels[code], "state": state})
    return {"steps": out, "current": None if d["status"] == S.CANCELLED else current, "on_hold": d["status"] == S.LEGAL_HOLD}


def location(d, acct):
    a = services.assurance(d)
    base = {"assurance": a, "evidence": None}
    if d["holding"] == "depiqo":
        return base | {"kind": "depiqo_account", "label": "Borgrekening op jouw naam bij de partnerbank" if acct
                       else "Borgrekening op jouw naam, zodra je identiteit is bevestigd",
                       "account_open": bool(acct), "sandbox": bool(acct and acct["provider"] == "sandbox"),
                       "interest_rate_bps": acct["interest_rate_bps"] if acct else None,
                       "provider_name": None, "reference_label": None, "reference": None, "guarantee": None}
    kind = d["provider_kind"]
    info = providers.PROVIDER_KINDS.get(kind)
    guarantee = None
    if kind in providers.GUARANTEE_KINDS:
        exp = providers.expiry_info(d)
        text = ("Je hebt geen geld gestort. Een derde staat garant. Bij schade kan die het bedrag op jou verhalen." if kind == "borggarantie"
                else "Het OCMW of je lokaal bestuur staat in voor je waarborg. Je hebt zelf geen geld gestort.")
        warning = warning_key = None
        if exp and exp[0] <= providers.EXPIRY_WARN_DAYS:
            warning_key = "expired" if exp[0] < 0 else "expiring"
            warning = ("Je garantie is verlopen." if exp[0] < 0 else "Je garantie loopt binnenkort af.") + \
                " Neem contact op met je verhuurder en de garantsteller."
        guarantee = {"kind": kind, "text": text, "expires_on": d["guarantee_expires_on"], "days_left": exp[0] if exp else None,
                     "warning": warning, "warning_key": warning_key}
    ev = S.EVIDENCE.get(d["evidence_level"])
    return base | {
        "kind": kind or "unknown", "label": info["tenant"] if info else "Bij je verhuurder",
        "account_open": None, "sandbox": False, "interest_rate_bps": None,
        "provider_name": d["provider_name"], "reference_label": info["reference_label"] if info and d["provider_reference"] else None,
        "reference": d["provider_reference"], "guarantee": guarantee,
        "evidence": {"level": d["evidence_level"], "label": ev["label"], "tenant": ev["tenant"]} if ev else None,
    }


# Stable keys for the explanations of services.balances(), so the app can translate them.
NOTE_KEYS = {
    "Volgens het huurcontract": "per_lease", "Er is nog geen borgrekening": "no_account", "Nog geen blokkering": "no_lock_yet",
    "Nog geen rente bijgeschreven": "no_interest_yet", "Bevestigd door de bank": "bank_confirmed",
    "Nog geen storting gemeld door de bank": "no_payment_reported", "Sandboxrekening: niet bevestigd door een echte bank": "sandbox_unconfirmed",
    "Niet bevestigd door de actieve bankpartner": "not_confirmed_by_active_bank", "Blokkering bevestigd door de bank": "lock_confirmed_by_bank",
    "Aangevraagd, nog niet bevestigd door de bank": "lock_requested", "Vrijgegeven bij de uitbetaling": "released_at_payout",
    "Bijgeschreven door de bank, voor de huurder": "interest_credited", "Geen geld gestort: een derde staat garant": "guarantee_no_money",
    "Geen geld van de huurder: via het OCMW": "ocmw_no_money", "Nog geen ontvangst gemeld": "no_receipt_reported",
    "Alleen verklaard door de beheerder, niet aangetoond": "declared_only", "Bankbewijs ontvangen": "bank_proof_received",
    "Geverifieerd door Depiqo": "verified_by_depiqo", "Juridische zekerheid aangetoond": "legal_security_proven",
    "Vrijgegeven bij de aanbieder": "released_by_provider", "Terugbetaald of geannuleerd": "repaid_or_cancelled",
    "Garantie aangetoond, geen geld geblokkeerd": "guarantee_proven", "Blokkeringsattest of e-DEPO aangetoond": "lock_certificate_proven",
    "Geen juridische blokkering aangetoond": "no_legal_lock", "Valt buiten Depiqo bij een borg elders": "outside_depiqo",
}


def amounts(d, acct):
    return [{"key": f["key"], "label": f["label"], "value": money(f["value"]), "known": f["value"] is not None, "explanation": f["note"],
             "explanation_key": NOTE_KEYS.get(f["note"], "other")} for f in services.balances(d, acct)]


def next_action(d, pay, problem):
    s = d["status"]
    if s in (S.ID_PENDING, S.ID_FAILED) and d["holding"] == "depiqo":
        if services.open_instruction(d):
            return {"code": "wait", "label": "Je borgrekening wordt geopend", "description": "Je identiteit is bevestigd. De bank opent nu je rekening."}
        if not services.bank().available:
            return {"code": "wait", "label": "Even geduld", "description": "Er is geen financiële partner gekoppeld. Betaal niets en neem contact op met je verhuurder."}
        return {"code": "verify_identity", "label": "Bevestig je identiteit", "description": "De partnerbank opent de borgrekening op jouw naam."}
    if s == S.AWAITING_PAYMENT:
        if pay:
            return {"code": "pay", "label": "Stort je borg", "description": "Maak het bedrag over met precies deze gegevens."}
        if problem:
            return {"code": "wait", "label": "Betaal nu niets", "description": problem}
        return {"code": "wait", "label": "Je borg wordt geregeld", "description": "Je hoeft niets over te maken. Je verhuurder regelt de rest."}
    if s == S.SETTLEMENT_PROPOSED:
        return {"code": "respond_settlement", "label": "Bekijk de eindafrekening", "description": "Ga akkoord of maak bezwaar."}
    if s == S.AGREED:
        if investing.visibility(g.api_user["id"]) == "available" and investing.can_choose_payout(d, g.api_user["id"]):
            return {"code": "choose_payout_destination", "label": "Kies waar je jouw deel ontvangt",
                    "description": "Op je eigen rekening (standaard) of op je beleggingsrekening. Wijzigen kan tot de uitbetaling start."}
        if services.release_form_available(d):
            return {"code": "release_form", "label": "Vrijgaveformulier", "description": "Teken het formulier samen met je verhuurder en stuur het naar de aanbieder."}
    if s == S.DISPUTED:
        return {"code": "wait", "label": "Je bezwaar is vastgelegd", "description": "Je verhuurder neemt contact met je op. Depiqo beslist niet in een geschil."}
    return None


def summary_json(d, org_name, prop):
    key, label, tone = services.display(d, True)
    acct = services.account_for(d) if d["holding"] == "depiqo" else None
    return {"pid": d["pid"], "reference": d["reference"], "region": d["region"], "term": rules.for_deposit(d).term, "holding": d["holding"],
            "provider_kind": d["provider_kind"] if d["holding"] == "external" else None,
            "evidence_level": d["evidence_level"] if d["holding"] == "external" else None,
            "address": {"street": prop["address"], "postcode": prop["postcode"], "city": prop["city"]}, "landlord": {"name": org_name},
            "status": d["status"], "status_label": S.TENANT_LABELS[d["status"]], "display_key": key, "display_label": label, "tone": tone,
            "amounts": amounts(d, acct), "updated_at": d["updated_at"]}


EVENT_KEYS = {"payment": "payment_received", "interest": "interest_credited", "document": "document_added", "invite": "invited"}


def event_json(e):
    """An event as a stable key with parameters (for translation in the app) plus the Dutch text."""
    try:
        data = json.loads(e["data_json"]) if e["data_json"] else {}
    except ValueError:
        data = {}
    params = {k: v for k, v in data.items() if k.endswith("_cents")}
    if e["type"] == "status":
        key = "status_changed"
        params.update({"from_status": e["from_status"], "to_status": e["to_status"]})
    else:
        key = EVENT_KEYS.get(e["type"], e["type"])
    return {"id": e["id"], "at": e["at"], "type": e["type"], "key": key, "params": params, "message": e["message"], "actor": e["actor_kind"]}


def detail_json(d):
    org = db.one("SELECT * FROM organizations WHERE id = ?", (d["org_id"],))
    prop = db.one("SELECT * FROM properties WHERE id = ?", (d["property_id"],))
    acct = services.account_for(d) if d["holding"] == "depiqo" else None
    r = rules.for_deposit(d)
    pay, problem = (services.payment_details(d, org) if d["status"] == S.AWAITING_PAYMENT else (None, None))
    deadline = services.deadline_info(d)
    ph = ",".join("?" * len(TENANT_EVENT_TYPES))
    events = db.all_(f"SELECT * FROM deposit_events WHERE deposit_id = ? AND type IN ({ph}) ORDER BY id DESC LIMIT 20", (d["id"], *TENANT_EVENT_TYPES))
    split = services.payout_split(d) if d["status"] in (S.AGREED, S.PAYOUT_PENDING) else None
    return summary_json(d, org["name"], prop) | {
        "rent": money(d["rent_cents"]), "lease_start": d["lease_start"], "lease_end": d["lease_end"], "move_out_date": d["move_out_date"],
        "progress": progress(d), "location": location(d, acct),
        "deadline": {"date": iso_date(deadline["date"]), "statutory": deadline["statutory"], "why": deadline["why"],
                     "days_left": deadline["days_left"]} if deadline else None,
        "release_rule": r.release_note,
        "next_action": next_action(d, pay, problem),
        "payment_instructions": {"iban": pay["iban"], "beneficiary": pay["beneficiary"], "amount": money(pay["amount_cents"]),
                                 "reference": pay["reference"],
                                 "warning": "Kloppen naam, bedrag en kenmerk niet met je huurcontract? Betaal niet en bel je verhuurder."} if pay else None,
        "payment_problem": problem,
        "payout": {"to_tenant": money(split[0]), "to_landlord": money(split[1])} if split else None,
        "release_form_available": services.release_form_available(d),
        "interest_note": f"Rente: {acct['interest_rate_bps'] / 100:.2f}% per jaar, volledig voor jou".replace(".", ",") if acct else None,
        "events": [event_json(e) for e in events], "events_path": f"/api/v1/deposits/{d['pid']}/events",
    }


@bp.route("/deposits", methods=["GET"])
@tenant_api
def deposits():
    limit, cursor = page_args()
    ph = ",".join("?" * len(g.tenant_ids))
    sql = (f"SELECT d.*, o.name AS org_name FROM deposits d JOIN organizations o ON o.id = d.org_id "
           f"WHERE d.tenant_id IN ({ph}) AND d.status != ?")
    params = [*g.tenant_ids, S.CONCEPT]
    if cursor:
        if len(cursor) != 1 or not isinstance(cursor[0], int):
            raise ApiError(400, "invalid_cursor", "Deze cursor is niet geldig.")
        sql += " AND d.id < ?"
        params.append(cursor[0])
    rows = db.all_(sql + " ORDER BY d.id DESC LIMIT ?", (*params, limit + 1))

    def render(r):
        prop = db.one("SELECT * FROM properties WHERE id = ?", (r["property_id"],))
        return summary_json(r, r["org_name"], prop)
    return jsonify(paged(rows, limit, lambda r: [r["id"]], render))


@bp.route("/deposits/<pid>", methods=["GET"])
@tenant_api
def deposit(pid):
    return jsonify(detail_json(my_deposit(pid)))


@bp.route("/deposits/<pid>/events", methods=["GET"])
@tenant_api
def deposit_events(pid):
    d = my_deposit(pid)
    limit, cursor = page_args()
    ph = ",".join("?" * len(TENANT_EVENT_TYPES))
    sql = f"SELECT * FROM deposit_events WHERE deposit_id = ? AND type IN ({ph})"
    params = [d["id"], *TENANT_EVENT_TYPES]
    if cursor:
        if len(cursor) != 1 or not isinstance(cursor[0], int):
            raise ApiError(400, "invalid_cursor", "Deze cursor is niet geldig.")
        sql += " AND id < ?"
        params.append(cursor[0])
    rows = db.all_(sql + " ORDER BY id DESC LIMIT ?", (*params, limit + 1))
    return jsonify(paged(rows, limit, lambda r: [r["id"]], event_json))


@bp.route("/deposits/<pid>/identity", methods=["POST"])
@tenant_api
@idempotent()
def identity(pid):
    d = my_deposit(pid)
    if d["holding"] == "depiqo" and d["status"] in (S.ID_PENDING, S.ID_FAILED) and not services.bank().available:
        raise ApiError(503, "partner_unavailable", "Er is geen financiële partner gekoppeld. Je borgrekening kan nu niet worden geopend. Betaal niets.")
    data = body()
    name = str_field(data, "full_name", max_len=200)
    birth = str_field(data, "birth_date", max_len=10)
    try:
        d = services.verify_identity(d, g.api_user["id"], name, birth)
    except services.WorkflowError as exc:
        raise ApiError(409, "identity_not_possible", str(exc))
    if d["status"] == S.AWAITING_PAYMENT:
        result, message = "account_open", "Je identiteit is bevestigd en je borgrekening is geopend."
    elif d["status"] == S.ID_PENDING and services.open_instruction(d):
        result, message = "opening", "Je identiteit is bevestigd. De bank opent nu je borgrekening. Je krijgt bericht zodra je kunt storten."
    elif d["status"] == S.ID_PENDING:
        result, message = "bank_unavailable", "Je identiteit is bevestigd, maar de bank kon je borgrekening nog niet openen. Betaal nog niets."
    else:
        result, message = "failed", "Je identiteit kon niet worden bevestigd. Controleer je gegevens en probeer het opnieuw."
    audit("deposit.identity", f"deposit:{pid}", {"result": result, "via": "app"}, org_id=d["org_id"])
    return jsonify({"result": result, "message": message, "deposit": detail_json(d)})


# ------------------------------------------------------------ documents

def document_json(doc, pid):
    return {"id": doc["id"], "kind": doc["kind"], "kind_label": KINDS.get(doc["kind"], doc["kind"]), "filename": doc["filename"],
            "mime": doc["mime"], "size_bytes": doc["size_bytes"], "created_at": doc["created_at"],
            "uploaded_by": "tenant" if doc["uploaded_by_kind"] == "tenant" else "landlord",
            "download_path": f"/api/v1/deposits/{pid}/documents/{doc['id']}"}


@bp.route("/deposits/<pid>/documents", methods=["GET"])
@tenant_api
def documents(pid):
    d = my_deposit(pid)
    docs = db.all_("SELECT * FROM documents WHERE deposit_id = ? ORDER BY id DESC", (d["id"],))
    return jsonify({"items": [document_json(x, pid) for x in docs],
                    "upload_kinds": [{"kind": k, "label": KINDS[k]} for k in TENANT_UPLOAD_KINDS],
                    "upload_allowed": d["status"] not in (S.CLOSED, S.CANCELLED), "max_bytes": 10 * 1024 * 1024,
                    "accepted_types": ["application/pdf", "image/jpeg", "image/png"]})


@bp.route("/deposits/<pid>/documents/<int:doc_id>", methods=["GET"])
@tenant_api
def document_download(pid, doc_id):
    d = my_deposit(pid)
    doc = db.one("SELECT * FROM documents WHERE id = ? AND deposit_id = ?", (doc_id, d["id"]))
    if not doc:
        raise ApiError(404, "not_found", "Dit document bestaat niet.")
    audit("document.downloaded", f"document:{doc_id}", {"via": "app"}, org_id=doc["org_id"])
    return send_file(file_path(doc), mimetype=doc["mime"], as_attachment=True, download_name=doc["filename"])


@bp.route("/deposits/<pid>/documents", methods=["POST"])
@tenant_api
@idempotent()
def document_upload(pid):
    d = my_deposit(pid)
    if request.mimetype != "multipart/form-data":
        raise ApiError(415, "unsupported_media_type", "Stuur het bestand als multipart/form-data met de velden file en kind.")
    if d["status"] in (S.CLOSED, S.CANCELLED):
        raise ApiError(409, "deposit_closed", "Dit dossier is gesloten. Je kunt geen documenten meer toevoegen.")
    kind = request.form.get("kind")
    if kind not in TENANT_UPLOAD_KINDS:
        raise field_error("kind", "Kies het soort document: photo, inspection of other.")
    try:
        doc_id = save_upload(request.files.get("file"), d, kind, "tenant", g.api_user["id"])
    except UploadError as exc:
        raise field_error("file", str(exc), "upload_rejected")
    services.add_event(d, "tenant", "document", "Huurder heeft een document toegevoegd", g.api_user["id"])
    audit("document.uploaded", f"document:{doc_id}", {"via": "app"}, org_id=d["org_id"])
    return jsonify(document_json(db.one("SELECT * FROM documents WHERE id = ?", (doc_id,)), pid)), 201


# ------------------------------------------------------------ settlement

def settlement_json(d):
    s = services.current_settlement(d)
    if not s or s["status"] == "draft":
        return None
    lines = services.settlement_lines(s)
    total = services.settlement_total(s)
    acct = services.account_for(d) if d["holding"] == "depiqo" else None
    dispute = services.open_dispute(d)
    return {"status": s["status"], "proposed_at": s["proposed_at"], "responded_at": s["responded_at"],
            "deposit_amount": money(d["amount_cents"]),
            "lines": [{"category": l["category"], "category_label": services.CATEGORIES[l["category"]], "description": l["description"],
                       "amount": money(l["amount_cents"]), "document_id": l["document_id"],
                       "document_path": f"/api/v1/deposits/{d['pid']}/documents/{l['document_id']}" if l["document_id"] else None} for l in lines],
            "deductions": money(total), "back_to_tenant": money(max(d["amount_cents"] - total, 0)),
            "interest": money(acct["ledger_interest_cents"]) if acct and acct["ledger_interest_cents"] else None,
            "can_respond": d["status"] == S.SETTLEMENT_PROPOSED and s["status"] == "proposed",
            "tenant_comment": s["tenant_comment"],
            "dispute": {"opened_at": dispute["opened_at"], "reason": dispute["reason"], "status": dispute["status"]} if dispute else None,
            "note": "Depiqo beslist niet in een geschil. Jij en je verhuurder komen samen tot een akkoord, of de rechter beslist."}


@bp.route("/deposits/<pid>/settlement", methods=["GET"])
@tenant_api
def settlement(pid):
    return jsonify({"settlement": settlement_json(my_deposit(pid))})


@bp.route("/deposits/<pid>/settlement/agree", methods=["POST"])
@tenant_api
@idempotent()
def settlement_agree(pid):
    d = my_deposit(pid)
    true_field(body(), "confirm", "Bevestig dat je akkoord gaat met deze afrekening.")
    try:
        d = services.tenant_agree(d, g.api_user["id"])
    except services.WorkflowError as exc:
        raise ApiError(409, "settlement_not_open", str(exc))
    audit("settlement.agreed", f"deposit:{pid}", {"via": "app"}, org_id=d["org_id"])
    return jsonify({"message": "Je bent akkoord gegaan. De uitbetaling wordt gestart.", "settlement": settlement_json(d), "deposit": detail_json(d)})


@bp.route("/deposits/<pid>/settlement/dispute", methods=["POST"])
@tenant_api
@idempotent()
def settlement_dispute(pid):
    d = my_deposit(pid)
    data = body()
    reason = data.get("reason") if isinstance(data.get("reason"), str) else ""
    if len(reason.strip()) < 10:
        raise field_error("reason", "Leg in een paar zinnen uit waarmee je het oneens bent.", "reason_required")
    try:
        d = services.tenant_dispute(d, g.api_user["id"], reason)
    except services.WorkflowError as exc:
        raise ApiError(409, "settlement_not_open", str(exc))
    audit("settlement.disputed", f"deposit:{pid}", {"via": "app"}, org_id=d["org_id"])
    return jsonify({"message": "Je bezwaar is vastgelegd. Je verhuurder neemt contact met je op.", "settlement": settlement_json(d),
                    "deposit": detail_json(d)})


@bp.route("/deposits/<pid>/release-form", methods=["GET"])
@tenant_api
def release_form_pdf(pid):
    d = my_deposit(pid)
    if not services.release_form_available(d):
        raise ApiError(404, "not_available", "Het vrijgaveformulier is er pas na akkoord, bij een borg die elders staat.")
    pdf = release_form.build(d)
    audit("deposit.release_form", f"deposit:{pid}", {"by": "tenant", "via": "app"}, org_id=d["org_id"])
    services.add_event(d, "tenant", "document", "Vrijgaveformulier gedownload door de huurder", g.api_user["id"])
    return Response(pdf, mimetype="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename=vrijgaveformulier-{d['reference']}.pdf"})


# ------------------------------------------------------------ doorbeleggen

def payout_choice_json(d):
    uid = g.api_user["id"]
    p = investing.partner()
    choice = investing.payout_choice(d["id"])
    can = investing.can_choose_payout(d, uid)
    return {"available": can, "destination": "invest" if choice and choice["status"] == "chosen" else "own",
            "choice": {"status": choice["status"], "chosen_at": choice["chosen_at"], "paid": money(choice["paid_cents"]),
                       "paid_at": choice["paid_at"]} if choice else None,
            "partner": p.display_name if p.available else None,
            "risk_text": investing.RISK_TEXT,
            "confirmation_text": "Ik kies er zelf voor om mijn deel van de borg op mijn beleggingsrekening te ontvangen. Daar kan de waarde dalen.",
            "explanation": "Je kunt dit wijzigen tot de uitbetaling start. Je verhuurder ziet alleen dat het naar jouw rekening gaat. "
                           "Het geld komt eerst als vrij geld binnen; je kiest zelf of je het belegt."}


def _payout_deposit(pid):
    d = my_deposit(pid)
    vis = investing.visibility(g.api_user["id"])
    if vis == "hidden":
        raise ApiError(404, "not_found", "Doorbeleggen is niet beschikbaar.")
    if vis == "unavailable":
        raise ApiError(503, "partner_unavailable", "Beleggen is nu niet beschikbaar: er is geen beleggingspartner gekoppeld. Er wordt geen geld verplaatst.")
    return d


@bp.route("/deposits/<pid>/payout-choice", methods=["GET"])
@tenant_api
def payout_choice(pid):
    return jsonify(payout_choice_json(_payout_deposit(pid)))


@bp.route("/deposits/<pid>/payout-choice", methods=["POST"])
@tenant_api
@idempotent()
def payout_choose(pid):
    d = _payout_deposit(pid)
    true_field(body(), "confirm", "Bevestig dat je jouw deel van de borg op je beleggingsrekening wilt ontvangen.")
    try:
        investing.choose_payout(d, g.api_user["id"], True)
    except investing.InvestError as exc:
        raise ApiError(409, "payout_choice_closed", str(exc))
    audit("invest.payout_choice", f"user:{g.api_user['id']}", {"deposit": pid, "invest": True, "via": "app"}, org_id=NO_ORG)
    return jsonify(payout_choice_json(d))


@bp.route("/deposits/<pid>/payout-choice", methods=["DELETE"])
@tenant_api
@idempotent()
def payout_cancel(pid):
    d = _payout_deposit(pid)
    try:
        investing.choose_payout(d, g.api_user["id"], False)
    except investing.InvestError as exc:
        raise ApiError(409, "payout_choice_closed", str(exc))
    audit("invest.payout_choice", f"user:{g.api_user['id']}", {"deposit": pid, "invest": False, "via": "app"}, org_id=NO_ORG)
    return jsonify(payout_choice_json(d))

