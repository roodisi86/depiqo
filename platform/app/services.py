"""Deposit workflows. Every status change goes through `transition`, which enforces the
state machine and writes the audit trail in the same transaction.

Bank instructions (open an account, block it, release it) never call the bank inside a
database transaction. They are written to the `bank_instructions` outbox in the same
transaction as the state change, and sent afterwards by `dispatch_instructions()`.
"""
import json
import sqlite3
from datetime import timedelta

from flask import current_app

from . import db, notify, providers, rules
from . import states as S
from .partners import PartnerError, PartnerUnavailable, bank, bank_for_account, kyc, provider_allowed, send_mail
from .security import hash_password
from .util import dumps, eur, new_pid, now, now_iso, parse_date, parse_dt, sha256, today, token


class WorkflowError(Exception):
    """A user-facing problem: shown as a message, nothing is changed."""


# ------------------------------------------------------------ core

def get_deposit(pid, org_id=None, tenant_ids=None):
    d = db.one("SELECT * FROM deposits WHERE pid = ?", (pid,))
    if not d:
        return None
    if org_id is not None and d["org_id"] != org_id:
        return None
    if tenant_ids is not None and d["tenant_id"] not in tenant_ids:
        return None
    return d


def reload(deposit):
    return db.one("SELECT * FROM deposits WHERE id = ?", (deposit["id"],))


def add_event(deposit, actor_kind, type_, message, actor_user_id=None, from_status=None, to_status=None, data=None):
    db.run("INSERT INTO deposit_events (deposit_id, org_id, at, actor_kind, actor_user_id, type, from_status, to_status, message, data_json) "
           "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
           (deposit["id"], deposit["org_id"], now_iso(), actor_kind, actor_user_id, type_, from_status, to_status,
            message, dumps(data) if data else None))


def transition(deposit, target, actor_kind, message, actor_user_id=None, data=None, extra_sets=None):
    try:
        S.check(deposit["status"], target, actor_kind)
    except S.TransitionError as exc:
        raise WorkflowError(str(exc)) from exc
    sets = {"status": target, "updated_at": now_iso()}
    if target == S.SECURED:
        sets["secured_at"] = now_iso()
    if target in (S.CLOSED, S.CANCELLED):
        sets["closed_at"] = now_iso()
    if target == S.INVITED and not deposit["activated_at"]:
        sets["activated_at"] = now_iso()
    sets.update(extra_sets or {})
    cols = ", ".join(f"{k} = ?" for k in sets)  # keys are fixed column names in this module, never user input
    with db.transaction():
        changed = db.get_db().execute(f"UPDATE deposits SET {cols} WHERE id = ? AND status = ?",
                                      (*sets.values(), deposit["id"], deposit["status"])).rowcount
        if changed != 1:
            raise WorkflowError("Het dossier is intussen gewijzigd. Laad de pagina opnieuw.")
        add_event(deposit, actor_kind, "status", message, actor_user_id, deposit["status"], target, data)
    return reload(deposit)


def base_url():
    return current_app.config["BASE_URL"].rstrip("/")


def _no_partner(extra=""):
    partner = bank()
    return WorkflowError(" ".join(x for x in (getattr(partner, "reason", ""), extra) if x))


# ------------------------------------------------------------ create & invite

def next_reference(org_id):
    n = db.scalar("SELECT COUNT(*) FROM deposits WHERE org_id = ?", (org_id,)) + 1
    return f"DPQ-{org_id:03d}-{n:05d}"


def validate_new(data):
    """All checks for a new deposit that do not need the database. Returns a list of problems."""
    errors = rules.validate_deposit(data["region"], data["rent_cents"], data["amount_cents"],
                                    data["lease_start"], data.get("lease_end"))
    if data["holding"] not in ("depiqo", "external"):
        errors.append("Kies waar de borg komt te staan.")
    if data["holding"] == "depiqo" and not bank().available:
        errors.append("Er is geen financiële partner gekoppeld, dus een Depiqo-borgrekening kan nu niet. Kies 'Elders'.")
    if (data["holding"] == "external" and providers.needs_iban(data.get("provider_kind")) and not data.get("external_iban")
            and not data.get("existing")):
        errors.append("Vul het rekeningnummer in waarop de huurder de borg stort.")
    errors += providers.validate(data)
    if not data.get("tenant_name") or not data.get("tenant_email"):
        errors.append("Vul naam en e-mailadres van de huurder in.")
    if not data.get("property_id") and not (data.get("address") and data.get("postcode") and data.get("city")):
        errors.append("Kies een pand of vul adres, postcode en plaats in.")
    return errors


def create_deposit(org_id, user_id, data):
    """data: address, postcode, city, region, property_id?, tenant_name, tenant_email, tenant_phone,
    rent_cents, amount_cents, holding, lease_start, lease_end, external_iban, and for a deposit held
    elsewhere optionally provider_kind, provider_name, provider_reference, guarantee_expires_on."""
    errors = validate_new(data)
    if errors:
        raise WorkflowError(" ".join(errors))
    with db.transaction():
        if data.get("property_id"):
            prop = db.one("SELECT * FROM properties WHERE id = ? AND org_id = ?", (data["property_id"], org_id))
            if not prop:
                raise WorkflowError("Dat pand bestaat niet in je organisatie.")
            if prop["region"] != data["region"]:
                raise WorkflowError("De regio van het dossier moet overeenkomen met de regio van het pand.")
            property_id = prop["id"]
        else:
            property_id = db.run("INSERT INTO properties (org_id, address, postcode, city, region, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                                 (org_id, data["address"].strip(), data["postcode"].strip().upper(), data["city"].strip(),
                                  data["region"], now_iso()))
        tenant = db.one("SELECT * FROM tenants WHERE org_id = ? AND lower(email) = lower(?)", (org_id, data["tenant_email"]))
        tenant_id = tenant["id"] if tenant else db.run(
            "INSERT INTO tenants (org_id, name, email, phone, created_at) VALUES (?, ?, ?, ?, ?)",
            (org_id, data["tenant_name"].strip(), data["tenant_email"].strip().lower(), data.get("tenant_phone"), now_iso()))
        org = db.one("SELECT name FROM organizations WHERE id = ?", (org_id,))
        kind = data.get("provider_kind") if data["holding"] == "external" else None
        dep_id = db.run(
            "INSERT INTO deposits (pid, reference, org_id, property_id, tenant_id, region, holding, rent_cents, amount_cents, status, "
            "lease_start, lease_end, rule_version, external_iban, created_by, created_at, updated_at, security_type, beneficiary, import_batch_id, "
            "provider_kind, provider_name, provider_reference, guarantee_expires_on, custodian) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (new_pid(), next_reference(org_id), org_id, property_id, tenant_id, data["region"], data["holding"],
             data["rent_cents"], data["amount_cents"], S.CONCEPT, data["lease_start"], data.get("lease_end") or None,
             rules.RULE_VERSION, data.get("external_iban"), user_id, now_iso(), now_iso(),
             "bank_deposit" if data["holding"] == "depiqo" else providers.security_type_for(kind), org["name"], data.get("import_batch_id"),
             kind, data.get("provider_name") if kind else None, data.get("provider_reference") if kind else None,
             data.get("guarantee_expires_on") if kind else None,
             providers.custodian_for(kind, data.get("provider_name")) if kind else None))
        deposit = db.one("SELECT * FROM deposits WHERE id = ?", (dep_id,))
        add_event(deposit, "user", "created",
                  f"Dossier {'geïmporteerd' if data.get('import_batch_id') else 'aangemaakt'}: {eur(deposit['amount_cents'])}",
                  user_id, None, S.CONCEPT)
    return deposit


def _invite_token(deposit, days=14):
    raw = token()
    expires = (now() + timedelta(days=days)).isoformat(timespec="seconds")
    db.run("UPDATE deposits SET invite_token_hash = ?, invite_expires_at = ? WHERE id = ?", (sha256(raw), expires, deposit["id"]))
    return raw


# Statuses in which a tenant without an account may still be invited to the wallet (imported deposits).
WALLET_INVITABLE = (S.SECURED, S.MOVE_OUT, S.SETTLEMENT_PROPOSED, S.AGREED, S.DISPUTED)


def can_invite(deposit):
    if deposit["status"] in (S.CONCEPT, S.INVITED):
        return True
    if deposit["status"] in WALLET_INVITABLE:
        return not db.scalar("SELECT user_id FROM tenants WHERE id = ?", (deposit["tenant_id"],))
    return False


def send_invite(deposit, user_id):
    """Concept or open invitation: the normal invitation. An imported deposit without a tenant account:
    an invitation to Depiqo Wallet only, without a status change."""
    if not can_invite(deposit):
        raise WorkflowError("Een uitnodiging kan alleen bij een concept, een openstaande uitnodiging of een geïmporteerde borg zonder huurdersaccount.")
    tenant = db.one("SELECT * FROM tenants WHERE id = ?", (deposit["tenant_id"],))
    org = db.one("SELECT * FROM organizations WHERE id = ?", (deposit["org_id"],))
    prop = db.one("SELECT * FROM properties WHERE id = ?", (deposit["property_id"],))
    term = rules.for_deposit(deposit).term
    with db.transaction():
        raw = _invite_token(deposit)
        if deposit["status"] in (S.CONCEPT, S.INVITED):
            deposit = transition(deposit, S.INVITED, "user",
                                 "Uitnodiging opnieuw verstuurd" if deposit["status"] == S.INVITED else "Uitnodiging verstuurd naar de huurder",
                                 user_id)
            send_mail(tenant["email"], f"{org['name']} vraagt je {term} via Depiqo",
                      f"Hallo {tenant['name']},\n\n{org['name']} regelt de {term} voor {prop['address']}, {prop['city']} via Depiqo.\n"
                      f"Bedrag: {eur(deposit['amount_cents'])}\nKenmerk: {deposit['reference']}\n\n"
                      f"Open je uitnodiging: {base_url()}/t/{raw}\n\n"
                      "Controleer altijd dat het webadres begint met het officiële Depiqo-domein en dat de naam van je verhuurder en het adres kloppen. "
                      "Depiqo vraagt nooit om je bankcode.\n\nDeze link is 14 dagen geldig.", deposit_id=deposit["id"])
        else:
            add_event(deposit, "user", "invite", "Huurder uitgenodigd voor Depiqo Wallet", user_id)
            send_mail(tenant["email"], f"Je {term} bij {org['name']} staat in Depiqo",
                      f"Hallo {tenant['name']},\n\n{org['name']} heeft de {term} voor {prop['address']}, {prop['city']} in Depiqo gezet.\n"
                      f"Bedrag: {eur(deposit['amount_cents'])}\nKenmerk: {deposit['reference']}\n\n"
                      f"In Depiqo Wallet zie je waar je borg staat en wat er gebeurt bij je vertrek: {base_url()}/t/{raw}\n\n"
                      "Je hoeft niets te betalen. Depiqo vraagt nooit om je bankcode.\n\nDeze link is 14 dagen geldig.",
                      deposit_id=deposit["id"])
        notify.notify_tenant_of(deposit, "invite", {"landlord": org["name"], "address": prop["address"], "city": prop["city"]})
    return reload(deposit)


def deposit_by_invite(raw):
    d = db.one("SELECT * FROM deposits WHERE invite_token_hash = ?", (sha256(raw or ""),))
    if not d or not d["invite_expires_at"] or parse_dt(d["invite_expires_at"]) < now():
        return None
    return d


def accept_invite(raw, password=None, existing_user_id=None):
    """Links the tenant to a user account. Returns (user_id, deposit)."""
    deposit = deposit_by_invite(raw)
    if not deposit:
        raise WorkflowError("Deze uitnodiging is verlopen of al gebruikt. Vraag je verhuurder om een nieuwe.")
    tenant = db.one("SELECT * FROM tenants WHERE id = ?", (deposit["tenant_id"],))
    with db.transaction():
        if existing_user_id:
            user_id = existing_user_id
        else:
            user = db.one("SELECT * FROM users WHERE lower(email) = lower(?)", (tenant["email"],))
            if user and user["password_hash"]:
                raise WorkflowError("Er bestaat al een account met dit e-mailadres. Log eerst in en open de link daarna opnieuw.")
            if user:
                db.run("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(password), user["id"]))
                user_id = user["id"]
            else:
                user_id = db.run("INSERT INTO users (email, name, password_hash, created_at) VALUES (?, ?, ?, ?)",
                                 (tenant["email"], tenant["name"], hash_password(password), now_iso()))
        db.run("UPDATE tenants SET user_id = ? WHERE id = ?", (user_id, tenant["id"]))
        db.run("UPDATE deposits SET invite_token_hash = NULL WHERE id = ?", (deposit["id"],))
        if deposit["status"] == S.INVITED:
            target = S.ID_PENDING if deposit["holding"] == "depiqo" else S.AWAITING_PAYMENT
            deposit = transition(deposit, target, "tenant", "Huurder heeft de uitnodiging geaccepteerd", user_id)
        else:
            add_event(deposit, "tenant", "invite", "Huurder heeft toegang tot Depiqo Wallet", user_id)
            deposit = reload(deposit)
    return user_id, deposit


def payment_details(deposit, org=None):
    """Where the tenant pays. Returns (dict or None, problem or None). Fails closed without a partner."""
    if deposit["holding"] == "external":
        if not deposit["external_iban"] or deposit["provider_kind"] in providers.NO_TENANT_PAYMENT:
            return None, None  # a guarantee or the OCMW: the tenant transfers nothing
        org = org or db.one("SELECT name FROM organizations WHERE id = ?", (deposit["org_id"],))
        return {"iban": deposit["external_iban"], "beneficiary": org["name"], "reference": deposit["reference"],
                "amount_cents": deposit["amount_cents"]}, None
    acct = account_for(deposit)
    if not acct:
        return None, None
    try:
        return bank_for_account(acct).payment_instructions(acct, deposit), None
    except PartnerUnavailable as exc:
        return None, str(exc)


def send_payment_reminder(deposit, user_id):
    if deposit["status"] != S.AWAITING_PAYMENT:
        raise WorkflowError("Een betaalherinnering stuur je alleen als de huurder nog moet storten.")
    if deposit["holding"] == "external" and deposit["provider_kind"] in providers.NO_TENANT_PAYMENT:
        raise WorkflowError("Bij een garantie of een waarborg via het OCMW stort de huurder niets. Een betaalherinnering past niet.")
    since = (now() - timedelta(hours=24)).isoformat(timespec="seconds")
    if db.scalar("SELECT COUNT(*) FROM deposit_events WHERE deposit_id = ? AND type = 'reminder' AND at > ?", (deposit["id"], since)):
        raise WorkflowError("Er is in de afgelopen 24 uur al een herinnering verstuurd.")
    pay, problem = payment_details(deposit)
    if problem:
        raise WorkflowError(problem)
    if not pay:
        raise WorkflowError("Er zijn nog geen betaalgegevens voor dit dossier.")
    tenant = db.one("SELECT * FROM tenants WHERE id = ?", (deposit["tenant_id"],))
    org = db.one("SELECT name FROM organizations WHERE id = ?", (deposit["org_id"],))
    term = rules.for_deposit(deposit).term
    with db.transaction():
        add_event(deposit, "user", "reminder", "Betaalherinnering verstuurd naar de huurder", user_id)
        send_mail(tenant["email"], f"Herinnering: stort je {term} voor {org['name']}",
                  f"Hallo {tenant['name']},\n\nWe hebben je {term} nog niet ontvangen.\n\n"
                  f"Bedrag: {eur(pay['amount_cents'])}\nRekeningnummer: {pay['iban']}\nTen name van: {pay['beneficiary']}\n"
                  f"Omschrijving: {pay['reference']}\n\nJe ziet dit ook in Depiqo Wallet: {base_url()}/wallet/borg/{deposit['pid']}\n\n"
                  "Kloppen naam, bedrag en kenmerk niet met je huurcontract? Betaal niet en bel je verhuurder op een nummer dat je zelf opzoekt.",
                  deposit_id=deposit["id"])
    return reload(deposit)


# ------------------------------------------------------------ identity

def verify_identity(deposit, user_id, full_name, birth_date):
    if deposit["status"] not in (S.ID_PENDING, S.ID_FAILED):
        raise WorkflowError("Identificatie is nu niet nodig.")
    if not full_name or not birth_date:
        raise WorkflowError("Vul je volledige naam en geboortedatum in.")
    partner = bank()
    if not partner.available:
        raise WorkflowError(f"{partner.reason} Je borgrekening kan nu niet worden geopend. Je verhuurder krijgt hierover bericht.")
    if open_instruction(deposit):
        raise WorkflowError("Je identiteit is al bevestigd. De bank opent nu je borgrekening.")
    tenant = db.one("SELECT * FROM tenants WHERE id = ?", (deposit["tenant_id"],))
    provider = kyc()
    ids = []
    with db.transaction():
        if deposit["status"] == S.ID_FAILED:
            deposit = transition(deposit, S.ID_PENDING, "tenant", "Nieuwe identificatiepoging", user_id)
        result = provider.verify(tenant, full_name, birth_date)
        db.run("INSERT INTO kyc_checks (deposit_id, tenant_id, provider, status, created_at, completed_at) VALUES (?, ?, ?, ?, ?, ?)",
               (deposit["id"], tenant["id"], provider.name, result, now_iso(), now_iso()))
        if result != "approved":
            return transition(deposit, S.ID_FAILED, "system", "Identificatie niet gelukt (sandbox)", user_id)
        ids.append(enqueue_instruction(deposit, None, "open", {"holder_name": tenant["name"], "reference": deposit["reference"]},
                                       f"open:{deposit['id']}"))
        add_event(deposit, "system", "kyc", "Identiteit bevestigd; opdracht aan de bank om de borgrekening te openen", user_id)
    _dispatch_after_commit(ids)
    return reload(deposit)


def account_for(deposit):
    return db.one("SELECT * FROM bank_accounts WHERE deposit_id = ?", (deposit["id"],))


# ------------------------------------------------------------ bank instruction outbox

INSTRUCTION_KINDS = {"open": "Rekening openen", "block": "Rekening blokkeren", "release": "Vrijgave en uitbetaling"}
INSTRUCTION_STATUSES = {"pending": "Klaar om te versturen", "sent": "Verstuurd, wacht op antwoord", "acknowledged": "Aangenomen door de bank",
                        "failed": "Mislukt", "confirmed": "Uitgevoerd"}
STALE_SENT = timedelta(minutes=10)  # a 'sent' row older than this is resent with the same idempotency key


def enqueue_instruction(deposit, account, kind, payload, idempotency_key):
    """Writes an instruction in the caller's transaction. The same key is never written twice."""
    partner = bank()
    try:
        return db.run("INSERT INTO bank_instructions (deposit_id, bank_account_id, provider, kind, idempotency_key, payload_json, status, created_at) "
                      "VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
                      (deposit["id"], account["id"] if account else None, account["provider"] if account else partner.name,
                       kind, idempotency_key, dumps(payload), now_iso()))
    except sqlite3.IntegrityError:
        existing = db.one("SELECT id, status FROM bank_instructions WHERE idempotency_key = ?", (idempotency_key,))
        if existing["status"] == "failed":
            # A new attempt by the user (for example a new identity check): send it again, same key.
            db.run("UPDATE bank_instructions SET status = 'pending', attempts = 0, last_error = NULL WHERE id = ? AND status = 'failed'",
                   (existing["id"],))
        return existing["id"]


def instructions_for(deposit):
    return db.all_("SELECT * FROM bank_instructions WHERE deposit_id = ? ORDER BY id", (deposit["id"],))


def open_instruction(deposit):
    return db.one("SELECT * FROM bank_instructions WHERE deposit_id = ? AND kind = 'open' AND status != 'failed'", (deposit["id"],))


def _dispatch_after_commit(ids):
    """Try to send right away (the normal case). Whatever is left is picked up by the dispatcher."""
    if ids and current_app.config.get("DISPATCH_INLINE", True) and not db.get_db().in_transaction:
        dispatch_instructions(ids=ids)


def dispatch_instructions(ids=None, limit=200):
    """Sends pending instructions to the partner. Safe to run often and from several places:
    each row is claimed with an optimistic update and sent with its idempotency key."""
    summary = {"sent": 0, "retry": 0, "failed": 0, "skipped": 0, "blocked": None}
    partner = bank()
    if not partner.available:
        summary["blocked"] = partner.reason
        return summary
    stale = (now() - STALE_SENT).isoformat(timespec="seconds")
    sql = "SELECT * FROM bank_instructions WHERE (status = 'pending' OR (status = 'sent' AND sent_at < ?))"
    params = [stale]
    if ids:
        sql += f" AND id IN ({','.join('?' * len(ids))})"
        params += list(ids)
    for row in db.all_(sql + " ORDER BY id LIMIT ?", (*params, limit)):
        summary[_dispatch_one(partner, row, stale)] += 1
    return summary


def _fail(instr, message, deposit=None):
    """Only from 'sent': a bank event may already have confirmed the instruction while our call timed out."""
    with db.transaction():
        changed = db.get_db().execute("UPDATE bank_instructions SET status = 'failed', last_error = ? WHERE id = ? AND status = 'sent'",
                                      (message[:300], instr["id"])).rowcount
        if changed != 1:
            return "skipped"
        deposit = deposit or db.one("SELECT * FROM deposits WHERE id = ?", (instr["deposit_id"],))
        add_event(deposit, "system", "exception", f"Bankopdracht '{INSTRUCTION_KINDS[instr['kind']]}' mislukt: {message[:200]}")
    return "failed"


def _dispatch_one(partner, instr, stale):
    max_attempts = int(current_app.config.get("MAX_INSTRUCTION_ATTEMPTS", 5))
    with db.transaction():
        claimed = db.get_db().execute(
            "UPDATE bank_instructions SET status = 'sent', attempts = attempts + 1, sent_at = ? "
            "WHERE id = ? AND (status = 'pending' OR (status = 'sent' AND sent_at < ?))", (now_iso(), instr["id"], stale)).rowcount
    if claimed != 1:
        return "skipped"  # another worker took it
    instr = db.one("SELECT * FROM bank_instructions WHERE id = ?", (instr["id"],))
    deposit = db.one("SELECT * FROM deposits WHERE id = ?", (instr["deposit_id"],))
    payload = json.loads(instr["payload_json"])
    if instr["provider"] != partner.name:
        return _fail(instr, f"Opdracht hoort bij partner '{instr['provider']}'. De ingestelde partner '{partner.name}' mag hem niet uitvoeren.", deposit)
    try:
        if instr["kind"] == "open":
            if deposit["status"] == S.CANCELLED:
                return _fail(instr, "Dossier geannuleerd; rekening niet geopend.", deposit)
            tenant = db.one("SELECT * FROM tenants WHERE id = ?", (deposit["tenant_id"],))
            resp = partner.open_account(deposit, tenant, instr["idempotency_key"])
        else:
            acct = db.one("SELECT * FROM bank_accounts WHERE id = ?", (instr["bank_account_id"],))
            bank_for_account(acct)  # refuses a sandbox account with a real adapter, and the reverse
            if instr["kind"] == "block":
                resp = partner.request_block(acct, instr["idempotency_key"])
            else:
                extra = {"tenant_destination": payload["tenant_destination"]} if payload.get("tenant_destination") else {}
                resp = partner.request_release(acct, payload["tenant_cents"], payload["landlord_cents"], payload["reference"],
                                               instr["idempotency_key"], **extra)
    except PartnerUnavailable as exc:
        return _fail(instr, str(exc), deposit)
    except PartnerError as exc:
        if instr["attempts"] >= max_attempts:
            return _fail(instr, f"{exc} (na {instr['attempts']} pogingen)", deposit)
        changed = db.get_db().execute("UPDATE bank_instructions SET status = 'pending', last_error = ? WHERE id = ? AND status = 'sent'",
                                      (str(exc)[:300], instr["id"])).rowcount
        return "retry" if changed == 1 else "skipped"
    with db.transaction():
        if db.scalar("SELECT status FROM bank_instructions WHERE id = ?", (instr["id"],)) != "sent":
            return "skipped"  # the bank already confirmed it through an event
        _on_acknowledged(partner, instr, db.one("SELECT * FROM deposits WHERE id = ?", (instr["deposit_id"],)), resp)
    return "sent"


def _on_acknowledged(partner, instr, deposit, resp):
    ref = resp.get("provider_ref")
    if instr["kind"] == "open":
        acct_id = db.scalar("SELECT id FROM bank_accounts WHERE deposit_id = ?", (deposit["id"],))
        if not acct_id:
            acct_id = db.run("INSERT INTO bank_accounts (deposit_id, provider, external_id, iban, holder_name, status, interest_rate_bps, opened_at) "
                             "VALUES (?, ?, ?, ?, ?, 'open', ?, ?)",
                             (deposit["id"], partner.name, resp["external_id"], resp["iban"], resp["holder_name"],
                              resp["interest_rate_bps"], now_iso()))
        db.run("UPDATE bank_instructions SET status = 'confirmed', confirmed_at = ?, provider_ref = ?, bank_account_id = ?, last_error = NULL "
               "WHERE id = ? AND status = 'sent'", (now_iso(), ref, acct_id, instr["id"]))
        org = db.one("SELECT name FROM organizations WHERE id = ?", (deposit["org_id"],))
        set_security(deposit, security_type="bank_deposit", custodian=partner.display_name, beneficiary=org["name"], asset_value_cents=0)
        if deposit["status"] == S.ID_PENDING:
            transition(deposit, S.AWAITING_PAYMENT, "system",
                       f"Borgrekening geopend bij de partnerbank{' (sandbox)' if partner.is_sandbox else ''}")
        else:
            add_event(deposit, "bank", "account", "Borgrekening geopend bij de partnerbank")
        return
    db.run("UPDATE bank_instructions SET status = 'acknowledged', provider_ref = ?, last_error = NULL WHERE id = ? AND status = 'sent'",
           (ref, instr["id"]))
    if instr["kind"] == "release":
        add_event(deposit, "bank", "instruction", "Bank heeft de vrijgave-opdracht aangenomen")


def reprocess_bank_event(event_row_id):
    """Staff: process a bank event that ended with an error again (same event_id, same payload)."""
    ev = db.one("SELECT * FROM bank_events WHERE id = ?", (event_row_id,))
    if not ev or ev["error"] is None:
        raise WorkflowError("Alleen een bankbericht met een fout kan opnieuw worden verwerkt.")
    payload = json.loads(ev["payload_json"])
    return handle_bank_event(ev["provider"], ev["type"], payload, reprocess=True)


def retry_instruction(instr_id):
    """Staff: put a failed instruction back in the queue with a fresh attempt count (same idempotency key)."""
    instr = db.one("SELECT * FROM bank_instructions WHERE id = ?", (instr_id,))
    if not instr or instr["status"] != "failed":
        raise WorkflowError("Alleen een mislukte opdracht kan opnieuw worden geprobeerd.")
    db.run("UPDATE bank_instructions SET status = 'pending', attempts = 0 WHERE id = ?", (instr_id,))
    return instr


# ------------------------------------------------------------ bank events

def _valid_amount(value, allow_zero=False):
    return isinstance(value, int) and not isinstance(value, bool) and (value >= 0 if allow_zero else value > 0)


def handle_bank_event(provider, event_type, payload, reprocess=False):
    """Idempotent: an event id is processed once. An event that was refused because of timing
    (retryable) is processed again when it arrives again; reprocess=True (staff) retries any event
    that ended with an error. Returns 'processed' | 'duplicate' | 'ignored' | 'mismatch'."""
    if not provider_allowed(provider):
        raise WorkflowError("Bankberichten van deze partner worden niet verwerkt: " + (getattr(bank(), "reason", "") or "andere partner ingesteld."))
    event_id = payload.get("event_id")
    if not event_id:
        raise WorkflowError("Bankbericht zonder event_id.")
    if event_type in ("deposit.received", "interest.credited") and not _valid_amount(payload.get("amount_cents")):
        raise WorkflowError("Bankbericht met een ongeldig bedrag.")
    def _replaceable(row):
        return row is not None and row["error"] is not None and (row["retryable"] or reprocess)
    existing = db.one("SELECT * FROM bank_events WHERE provider = ? AND external_event_id = ?", (provider, event_id))
    if existing and not _replaceable(existing):
        return "duplicate"
    ids = []
    with db.transaction():
        existing = db.one("SELECT * FROM bank_events WHERE provider = ? AND external_event_id = ?", (provider, event_id))
        if existing:
            if not _replaceable(existing):
                return "duplicate"
            db.run("DELETE FROM bank_events WHERE id = ?", (existing["id"],))  # processed again below, in the same transaction
        try:
            ev_id = db.run("INSERT INTO bank_events (provider, external_event_id, type, payload_json, received_at) VALUES (?, ?, ?, ?, ?)",
                           (provider, event_id, event_type, dumps(payload), now_iso()))
        except sqlite3.IntegrityError:
            return "duplicate"  # the same event arrived twice at the same moment
        result = _apply_bank_event(ev_id, provider, event_type, payload, ids)
    _dispatch_after_commit(ids)
    return result


def _event_error(ev_id, message, retryable=False):
    """retryable: refused because of timing (the account or instruction may not be recorded yet). The same
    event_id is processed again when the bank retries, or when staff chooses 'opnieuw verwerken'."""
    db.run("UPDATE bank_events SET error = ?, processed_at = ?, retryable = ? WHERE id = ?",
           (message[:300], now_iso(), 1 if retryable else 0, ev_id))


def _apply_bank_event(ev_id, provider, event_type, payload, ids):
    acct = db.one("SELECT * FROM bank_accounts WHERE provider = ? AND external_id = ?", (provider, payload.get("external_id")))
    if not acct:
        _event_error(ev_id, "onbekende rekening", retryable=True)
        return "ignored"
    deposit = db.one("SELECT * FROM deposits WHERE id = ?", (acct["deposit_id"],))
    if event_type == "deposit.received":
        amount = int(payload["amount_cents"])
        db.run("INSERT INTO bank_transactions (bank_account_id, kind, amount_cents, external_ref, at) VALUES (?, 'deposit', ?, ?, ?)",
               (acct["id"], amount, payload["ref"], now_iso()))
        db.run("UPDATE bank_accounts SET ledger_balance_cents = ledger_balance_cents + ? WHERE id = ?", (amount, acct["id"]))
        received = db.scalar("SELECT ledger_balance_cents FROM bank_accounts WHERE id = ?", (acct["id"],))
        sync_security_from_bank(deposit)
        if deposit["status"] == S.AWAITING_PAYMENT and received >= deposit["amount_cents"]:
            transition(deposit, S.PAYMENT_RECEIVED, "bank", f"Storting van {eur(amount)} ontvangen; blokkering wordt aangevraagd bij de bank",
                       data={"amount_cents": amount, "total_cents": received})
            ids.append(_request_block(deposit, acct))
        else:
            add_event(deposit, "bank", "payment", f"Storting van {eur(amount)} ontvangen; totaal {eur(received)} van {eur(deposit['amount_cents'])}",
                      data={"amount_cents": amount, "total_cents": received, "required_cents": deposit["amount_cents"]})
        notify.notify_tenant_of(deposit, "payment_received",
                                {"amount_cents": amount, "total_cents": received, "required_cents": deposit["amount_cents"]})
    elif event_type == "account.blocked":
        db.run("UPDATE bank_accounts SET status = 'blocked' WHERE id = ?", (acct["id"],))
        db.run("UPDATE bank_instructions SET status = 'confirmed', confirmed_at = ? WHERE bank_account_id = ? AND kind = 'block' AND status != 'confirmed'",
               (now_iso(), acct["id"]))
        set_security(deposit, legal_lock_status="active")
        sync_security_from_bank(deposit)
        if deposit["status"] == S.PAYMENT_RECEIVED:
            transition(deposit, S.SECURED, "bank", "Bank bevestigt: borg geblokkeerd ten gunste van de verhuurder")
            notify.notify_tenant_of(deposit, "deposit_secured")
    elif event_type == "interest.credited":
        amount = int(payload["amount_cents"])
        db.run("INSERT INTO bank_transactions (bank_account_id, kind, amount_cents, external_ref, at) VALUES (?, 'interest', ?, ?, ?)",
               (acct["id"], amount, payload["ref"], now_iso()))
        db.run("UPDATE bank_accounts SET ledger_interest_cents = ledger_interest_cents + ?, ledger_balance_cents = ledger_balance_cents + ? WHERE id = ?",
               (amount, amount, acct["id"]))
        sync_security_from_bank(deposit)
        add_event(deposit, "bank", "interest", f"Rente bijgeschreven: {eur(amount)}", data={"amount_cents": amount})
    elif event_type == "payout.completed":
        return _apply_payout(ev_id, acct, deposit, payload)
    else:
        _event_error(ev_id, "onbekend type")
        return "ignored"
    db.run("UPDATE bank_events SET processed_at = ? WHERE id = ?", (now_iso(), ev_id))
    return "processed"


def _apply_payout(ev_id, acct, deposit, payload):
    """The bank reports what it actually paid. It must match the release instruction to the cent."""
    instr = db.one("SELECT * FROM bank_instructions WHERE bank_account_id = ? AND kind = 'release' AND status IN ('pending', 'sent', 'acknowledged') "
                   "ORDER BY id DESC LIMIT 1", (acct["id"],))
    if not instr or acct["status"] != "release_requested":
        _event_error(ev_id, "uitbetaling zonder vrijgave-opdracht", retryable=True)
        return "ignored"
    paid_t, paid_l = payload.get("tenant_cents"), payload.get("landlord_cents")
    expected = json.loads(instr["payload_json"])
    if not (_valid_amount(paid_t, True) and _valid_amount(paid_l, True)) or (paid_t, paid_l) != (expected["tenant_cents"], expected["landlord_cents"]):
        shown = lambda v: eur(v) if _valid_amount(v, True) else "onbekend"  # noqa: E731
        message = (f"Uitbetaling wijkt af van de opdracht: huurder {shown(paid_t)} (opdracht {eur(expected['tenant_cents'])}), "
                   f"verhuurder {shown(paid_l)} (opdracht {eur(expected['landlord_cents'])}). Dossier blijft open.")
        _event_error(ev_id, message)
        db.run("UPDATE bank_instructions SET last_error = ? WHERE id = ?", (message[:300], instr["id"]))
        add_event(deposit, "bank", "exception", message)
        return "mismatch"
    ref = payload.get("ref") or payload["event_id"]
    for kind, amount in (("payout_tenant", paid_t), ("payout_landlord", paid_l)):
        if amount:
            db.run("INSERT INTO bank_transactions (bank_account_id, kind, amount_cents, external_ref, at) VALUES (?, ?, ?, ?, ?)",
                   (acct["id"], kind, amount, f"{ref}:{kind}", now_iso()))
    db.run("UPDATE bank_accounts SET status = 'closed', closed_at = ?, ledger_balance_cents = 0 WHERE id = ?", (now_iso(), acct["id"]))
    db.run("UPDATE bank_instructions SET status = 'confirmed', confirmed_at = ?, last_error = NULL WHERE id = ?", (now_iso(), instr["id"]))
    set_security(deposit, legal_lock_status="released", asset_value_cents=0, eligible_value_cents=0)
    from . import investing
    investing.on_payout_completed(deposit, paid_t, ref, expected.get("tenant_destination"))  # only after the amounts matched
    notify.notify_tenant_of(deposit, "payout_completed", {
        "tenant_cents": paid_t, "destination": "@dest.invest" if (expected.get("tenant_destination") or {}).get("type") == "invest" else "@dest.own"})
    if deposit["status"] == S.PAYOUT_PENDING:
        transition(deposit, S.CLOSED, "bank",
                   f"Bank bevestigt de uitbetaling: {eur(paid_t)} aan huurder, {eur(paid_l)} aan verhuurder; dossier gesloten",
                   data={"huurder": paid_t, "verhuurder": paid_l})
    db.run("UPDATE bank_events SET processed_at = ? WHERE id = ?", (now_iso(), ev_id))
    return "processed"


def _request_block(deposit, acct):
    iid = enqueue_instruction(deposit, acct, "block", {"reference": deposit["reference"]}, f"block:{acct['id']}")
    set_security(deposit, legal_lock_status="requested")
    return iid


# ------------------------------------------------------------ evidence (holding = 'external')

EVIDENCE_EDITABLE = (S.SECURED, S.MOVE_OUT, S.SETTLEMENT_PROPOSED, S.AGREED, S.DISPUTED, S.LEGAL_HOLD)


def _evidence_document(deposit, document_id, kinds):
    if not document_id:
        return None
    doc = db.one("SELECT * FROM documents WHERE id = ? AND deposit_id = ?", (document_id, deposit["id"]))
    if not doc:
        raise WorkflowError("Het gekozen document hoort niet bij dit dossier.")
    if doc["kind"] not in kinds:
        raise WorkflowError("Kies een document van het juiste soort.")
    return doc


def confirm_external_receipt(deposit, user_id, document_id=None):
    """The manager declares that the deposit arrived on their own account. That is a declaration,
    not proof: the evidence level is 'declared', or 'document' when a bank document is attached.
    Neither counts as eligible security (only 'verified' and 'legal' do)."""
    if deposit["holding"] != "external":
        raise WorkflowError("Bij een Depiqo-borgrekening bevestigt de bank de storting, niet een medewerker.")
    if deposit["status"] != S.AWAITING_PAYMENT:
        raise WorkflowError("Je verklaart de ontvangst nadat de huurder de uitnodiging heeft geaccepteerd en heeft gestort.")
    doc = _evidence_document(deposit, document_id, ("bankbewijs",))
    level = "document" if doc else "declared"
    org = db.one("SELECT name FROM organizations WHERE id = ?", (deposit["org_id"],))
    with db.transaction():
        d = transition(deposit, S.SECURED, "user",
                       "Ontvangst verklaard door de beheerder" + (" met bankbewijs" if doc else " (nog geen bankbewijs)"), user_id,
                       extra_sets={"security_type": providers.security_type_for(deposit["provider_kind"]), "beneficiary": org["name"],
                                   "asset_value_cents": deposit["amount_cents"], "eligible_value_cents": None,
                                   "evidence_level": level, "evidence_set_at": now_iso()})
        _record_evidence(d, level, user_id, None, doc["id"] if doc else None, False)
    return d


def _record_evidence(deposit, level, user_id, note, document_id, staff):
    db.run("INSERT INTO deposit_evidence (deposit_id, org_id, level, note, document_id, set_by, set_by_staff, at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
           (deposit["id"], deposit["org_id"], level, (note or "").strip()[:500] or None, document_id, user_id, 1 if staff else 0, now_iso()))


def set_evidence(deposit, level, user_id, note=None, document_id=None, staff=False):
    """Raise the evidence level. 'document' by the organisation (with a bank document);
    'verified' (with a note) and 'legal' (with a document) only by Depiqo staff. Never lowered."""
    if deposit["holding"] != "external":
        raise WorkflowError("Bewijsniveaus gelden alleen voor borgen die elders staan. Bij een Depiqo-borgrekening bevestigt de bank.")
    if level not in S.EVIDENCE_LEVELS:
        raise WorkflowError("Onbekend bewijsniveau.")
    if not deposit["evidence_level"] or deposit["status"] not in EVIDENCE_EDITABLE:
        raise WorkflowError("Eerst moet de ontvangst zijn verklaard, en het dossier mag niet gesloten zijn.")
    order = S.EVIDENCE_LEVELS.index
    if order(level) <= order(deposit["evidence_level"]):
        raise WorkflowError(f"Het bewijsniveau is al '{S.EVIDENCE[deposit['evidence_level']]['label']}'. Verlagen kan niet.")
    if level in ("verified", "legal") and not staff:
        raise WorkflowError("Alleen Depiqo stelt 'extern geverifieerd' of 'juridische zekerheid' vast.")
    if level == "legal" and not providers.legal_possible(deposit["provider_kind"]):
        raise WorkflowError("Geld op een rekening van de verhuurder of beheerder is niet juridisch geblokkeerd. "
                            "Het hoogste bewijsniveau is 'extern geverifieerd'. Staat de borg ergens anders, pas dan eerst de aanbieder aan.")
    sets = {"evidence_level": level, "evidence_set_at": now_iso()}
    doc = None
    if level == "document":
        doc = _evidence_document(deposit, document_id, ("bankbewijs",))
        if not doc:
            raise WorkflowError("Voeg eerst een bankbewijs toe bij Documenten (soort 'Bankbewijs van ontvangst') en kies het hier.")
    elif level == "verified":
        if len((note or "").strip()) < 10:
            raise WorkflowError("Leg in een notitie vast hoe de ontvangst is geverifieerd (minstens 10 tekens).")
        doc = _evidence_document(deposit, document_id, ("bankbewijs", "blokkering"))
        sets["eligible_value_cents"] = deposit["amount_cents"]
    elif level == "legal":
        doc = _evidence_document(deposit, document_id, ("blokkering",))
        if not doc:
            raise WorkflowError("Voeg het blokkeringsattest of het bewijs van e-DEPO toe (soort 'Blokkeringsattest of bewijs e-DEPO').")
        sets.update(eligible_value_cents=deposit["amount_cents"], legal_lock_status="active")
    cols = ", ".join(f"{k} = ?" for k in sets)  # fixed column names above
    with db.transaction():
        db.run(f"UPDATE deposits SET {cols} WHERE id = ?", (*sets.values(), deposit["id"]))
        _record_evidence(deposit, level, user_id, note, doc["id"] if doc else None, staff)
        add_event(deposit, "staff" if staff else "user", "evidence",
                  f"Bewijsniveau: {S.EVIDENCE[level]['label']}" + (f". {note.strip()[:200]}" if note and note.strip() else ""), user_id)
    return reload(deposit)


def evidence_history(deposit):
    return db.all_("SELECT e.*, u.name AS user_name, doc.filename FROM deposit_evidence e LEFT JOIN users u ON u.id = e.set_by "
                   "LEFT JOIN documents doc ON doc.id = e.document_id WHERE e.deposit_id = ? ORDER BY e.id", (deposit["id"],))


# ------------------------------------------------------------ security model
# The deposit row is the obligation (amount_cents). The columns below describe the collateral that
# covers it: what kind, who holds it, for whom, whether it is legally locked, and what it is worth.

SECURITY_TYPES = {
    "bank_deposit": "Bankdeposito bij partnerbank",
    "external_account": "Borg buiten Depiqo (verhuurder, bank of andere aanbieder)",
    "pledged_portfolio": "Verpande beleggingsrekening (toekomst)",
    "guarantee": "Garantie of borgstelling door een derde",
}
LOCK_STATUSES = {
    "none": "Geen",
    "requested": "Aangevraagd bij de bank",
    "active": "Actief, ten gunste van de verhuurder",
    "released": "Vrijgegeven",
}
_SECURITY_COLUMNS = ("security_type", "custodian", "beneficiary", "legal_lock_status", "asset_value_cents", "eligible_value_cents")


def set_security(deposit, **values):
    """Updates the security columns only; never the status (the state machine is untouched)."""
    if values.get("security_type", "bank_deposit") not in SECURITY_TYPES or values.get("legal_lock_status", "none") not in LOCK_STATUSES:
        raise ValueError("Onbekend type zekerheid of status van de blokkering.")
    cols = [k for k in values if k in _SECURITY_COLUMNS]  # fixed column names, never user input
    if cols:
        db.run(f"UPDATE deposits SET {', '.join(f'{c} = ?' for c in cols)} WHERE id = ?",
               (*(values[c] for c in cols), deposit["id"]))


def sync_security_from_bank(deposit):
    """Asset value follows the bank's ledger. Only a locked account counts as eligible collateral."""
    acct = account_for(deposit)
    if not acct or deposit["holding"] != "depiqo":
        return
    lock = db.scalar("SELECT legal_lock_status FROM deposits WHERE id = ?", (deposit["id"],))
    balance = acct["ledger_balance_cents"]
    set_security(deposit, asset_value_cents=balance, **({"eligible_value_cents": balance} if lock == "active" else {}))


def lock_trusted(deposit):
    """A bank lock only counts when the account is held by the active, available partner. With the
    sandbox switched off, sandbox locks are never shown or counted as confirmed."""
    if deposit["holding"] != "depiqo":
        return True
    try:
        provider = deposit["bank_provider"]
    except (KeyError, IndexError):
        provider = None
    if provider is None:
        try:
            provider = deposit["provider"]
        except (KeyError, IndexError):
            provider = None
    if provider is None:
        provider = db.scalar("SELECT provider FROM bank_accounts WHERE deposit_id = ?", (deposit["id"],))
    if provider is None:
        return True  # no account: there is no lock to trust or distrust
    partner = bank()
    return partner.available and partner.name == provider


def display_status(deposit, tenant=False):
    return S.display_status(deposit, tenant, lock_trusted(deposit))


def display(deposit, tenant=False):
    """(key, label, tone): display_status with a stable key for the app."""
    return S.display(deposit, tenant, lock_trusted(deposit))


def assurance(deposit):
    return S.assurance(deposit, lock_trusted(deposit))


def active_provider():
    partner = bank()
    return partner.name if partner.available else ""


def coverage_bps(deposit):
    """Eligible collateral as a share of the obligation, in basis points (10000 = 100%). None if unknown."""
    if deposit["eligible_value_cents"] is None or not deposit["amount_cents"]:
        return None
    return deposit["eligible_value_cents"] * 10000 // deposit["amount_cents"]


def _figure(key, label, value, note):
    return {"key": key, "label": label, "value": value, "note": note}


def balances(deposit, acct=False):
    """Four separate figures, never mixed: what is owed, what was received (proven), what is legally
    locked and what interest was credited. Unknown is None (shown as '—' with the note), never the
    obligation amount. acct: pass the bank account row (or None) to save a query."""
    d = deposit
    if acct is False:
        acct = account_for(d) if d["holding"] == "depiqo" else None
    closed = d["status"] in (S.CLOSED, S.CANCELLED)
    out = [_figure("obligation", "Vereiste borg", d["amount_cents"], "Volgens het huurcontract")]
    if d["holding"] == "depiqo":
        if not acct:
            out.append(_figure("received", "Ontvangen", None, "Er is nog geen borgrekening"))
            out.append(_figure("locked", "Bevestigd geblokkeerd", None, "Nog geen blokkering"))
            out.append(_figure("interest", "Rente", None, "Nog geen rente bijgeschreven"))
            return out
        received = db.scalar("SELECT COALESCE(SUM(amount_cents), 0) FROM bank_transactions WHERE bank_account_id = ? AND kind = 'deposit'",
                             (acct["id"],))
        out.append(_figure("received", "Ontvangen", received or None,
                           "Bevestigd door de bank" if received else "Nog geen storting gemeld door de bank"))
        lock = d["legal_lock_status"]
        if lock in ("active", "requested") and acct["provider"] != active_provider():
            out.append(_figure("locked", "Bevestigd geblokkeerd", None,
                               "Sandboxrekening: niet bevestigd door een echte bank" if acct["provider"] == "sandbox"
                               else "Niet bevestigd door de actieve bankpartner"))
        elif lock == "active":
            out.append(_figure("locked", "Bevestigd geblokkeerd", d["eligible_value_cents"], "Blokkering bevestigd door de bank"))
        else:
            note = {"requested": "Aangevraagd, nog niet bevestigd door de bank", "released": "Vrijgegeven bij de uitbetaling"}.get(lock, "Nog geen blokkering")
            out.append(_figure("locked", "Bevestigd geblokkeerd", None, note))
        interest = acct["ledger_interest_cents"]
        out.append(_figure("interest", "Rente", interest or None, "Bijgeschreven door de bank, voor de huurder" if interest else "Nog geen rente bijgeschreven"))
        return out
    level = d["evidence_level"]
    kind = d["provider_kind"]
    if kind in providers.NO_TENANT_PAYMENT:
        # No money changes hands: never show the obligation as money received.
        out.append(_figure("received", "Ontvangen", None,
                           "Geen geld gestort: een derde staat garant" if kind == "borggarantie" else "Geen geld van de huurder: via het OCMW"))
    else:
        received_note = {None: "Nog geen ontvangst gemeld", "declared": "Alleen verklaard door de beheerder, niet aangetoond",
                         "document": "Bankbewijs ontvangen", "verified": "Geverifieerd door Depiqo", "legal": "Juridische zekerheid aangetoond"}[level]
        out.append(_figure("received", "Ontvangen", d["amount_cents"] if level in ("document", "verified", "legal") else None, received_note))
    if closed:
        out.append(_figure("locked", "Bevestigd geblokkeerd", None,
                           "Vrijgegeven bij de aanbieder" if d["release_document_id"] else "Terugbetaald of geannuleerd"))
    elif level == "legal":
        out.append(_figure("locked", "Bevestigd geblokkeerd", d["amount_cents"],
                           "Garantie aangetoond, geen geld geblokkeerd" if kind == "borggarantie" else "Blokkeringsattest of e-DEPO aangetoond"))
    else:
        out.append(_figure("locked", "Bevestigd geblokkeerd", None, "Geen juridische blokkering aangetoond"))
    out.append(_figure("interest", "Rente", None, "Valt buiten Depiqo bij een borg elders"))
    return out


# ------------------------------------------------------------ end of lease

def start_move_out(deposit, user_id, move_out_date):
    d = parse_date(move_out_date)
    if not d:
        raise WorkflowError("Vul de datum in waarop de huurder vertrekt.")
    if d < parse_date(deposit["lease_start"]):
        raise WorkflowError("De vertrekdatum ligt voor de start van het huurcontract.")
    return transition(deposit, S.MOVE_OUT, "user", f"Vertrek gestart; vertrekdatum {d.isoformat()}", user_id,
                      extra_sets={"move_out_date": d.isoformat()})


def current_settlement(deposit):
    return db.one("SELECT * FROM settlements WHERE deposit_id = ? AND status != 'superseded' ORDER BY id DESC LIMIT 1", (deposit["id"],))


def settlement_lines(settlement):
    if not settlement:
        return []
    return db.all_("SELECT * FROM settlement_lines WHERE settlement_id = ? ORDER BY id", (settlement["id"],))


def settlement_total(settlement):
    if not settlement:
        return 0
    return db.scalar("SELECT COALESCE(SUM(amount_cents), 0) FROM settlement_lines WHERE settlement_id = ?", (settlement["id"],))


CATEGORIES = {"damage": "Schade", "rent_arrears": "Achterstallige huur", "service_costs": "Servicekosten",
              "energy": "Energie", "other": "Overig"}


def save_settlement(deposit, user_id, lines):
    """lines: list of dict(category, description, amount_cents, document_id). Replaces the draft."""
    if deposit["status"] not in (S.MOVE_OUT, S.DISPUTED):
        raise WorkflowError("Een eindafrekening maak je nadat het vertrek is gestart.")
    total = sum(l["amount_cents"] for l in lines)
    if total > deposit["amount_cents"]:
        raise WorkflowError(f"De inhoudingen ({eur(total)}) zijn hoger dan de borg ({eur(deposit['amount_cents'])}).")
    for l in lines:
        if l["category"] not in CATEGORIES or not l["description"].strip() or l["amount_cents"] <= 0:
            raise WorkflowError("Elke regel heeft een soort, een omschrijving en een bedrag hoger dan nul nodig.")
        if l.get("document_id") and not db.one("SELECT id FROM documents WHERE id = ? AND deposit_id = ?", (l["document_id"], deposit["id"])):
            raise WorkflowError("Het gekozen bewijsstuk hoort niet bij dit dossier.")
    with db.transaction():
        db.run("UPDATE settlements SET status = 'superseded' WHERE deposit_id = ? AND status IN ('draft', 'proposed', 'disputed')", (deposit["id"],))
        sid = db.run("INSERT INTO settlements (deposit_id, org_id, status, created_by, created_at) VALUES (?, ?, 'draft', ?, ?)",
                     (deposit["id"], deposit["org_id"], user_id, now_iso()))
        for l in lines:
            db.run("INSERT INTO settlement_lines (settlement_id, category, description, amount_cents, document_id) VALUES (?, ?, ?, ?, ?)",
                   (sid, l["category"], l["description"].strip()[:300], l["amount_cents"], l.get("document_id") or None))
        add_event(deposit, "user", "settlement", f"Concept-afrekening opgeslagen: {eur(total)} inhoudingen", user_id)
    return db.one("SELECT * FROM settlements WHERE id = ?", (sid,))


def propose_settlement(deposit, user_id):
    s = current_settlement(deposit)
    if not s or s["status"] != "draft":
        raise WorkflowError("Sla eerst een concept-afrekening op (eventueel zonder inhoudingen).")
    if not rules.settlement_allowed(deposit, today()):
        raise WorkflowError("De afrekening kan pas worden voorgesteld vanaf de vertrekdatum.")
    tenant = db.one("SELECT * FROM tenants WHERE id = ?", (deposit["tenant_id"],))
    total = settlement_total(s)
    with db.transaction():
        db.run("UPDATE settlements SET status = 'proposed', proposed_at = ? WHERE id = ?", (now_iso(), s["id"]))
        deposit = transition(deposit, S.SETTLEMENT_PROPOSED, "user",
                             f"Eindafrekening voorgesteld aan de huurder: {eur(total)} inhoudingen", user_id)
        send_mail(tenant["email"], "Je eindafrekening staat klaar",
                  f"Hallo {tenant['name']},\n\nDe eindafrekening voor dossier {deposit['reference']} staat klaar in Depiqo.\n"
                  f"Voorgestelde inhoudingen: {eur(total)}.\n\nBekijk de afrekening en het bewijs, en ga akkoord of geef aan dat je het oneens bent: "
                  f"{base_url()}/wallet/borg/{deposit['pid']}\n", deposit_id=deposit["id"])
        notify.notify_tenant_of(deposit, "settlement_proposed", {"deductions_cents": total})
    return deposit


def tenant_agree(deposit, user_id):
    s = current_settlement(deposit)
    if deposit["status"] != S.SETTLEMENT_PROPOSED or not s or s["status"] != "proposed":
        raise WorkflowError("Er staat geen afrekening open om op te reageren.")
    with db.transaction():
        db.run("UPDATE settlements SET status = 'agreed', responded_at = ? WHERE id = ?", (now_iso(), s["id"]))
        return transition(deposit, S.AGREED, "tenant", f"Huurder gaat akkoord met de afrekening ({eur(settlement_total(s))} inhoudingen)", user_id)


def tenant_dispute(deposit, user_id, reason):
    s = current_settlement(deposit)
    if deposit["status"] != S.SETTLEMENT_PROPOSED or not s:
        raise WorkflowError("Er staat geen afrekening open om te betwisten.")
    if len((reason or "").strip()) < 10:
        raise WorkflowError("Leg in een paar zinnen uit waarmee je het oneens bent.")
    with db.transaction():
        db.run("UPDATE settlements SET status = 'disputed', responded_at = ?, tenant_comment = ? WHERE id = ?",
               (now_iso(), reason.strip()[:2000], s["id"]))
        db.run("INSERT INTO disputes (deposit_id, org_id, settlement_id, opened_by_kind, reason, status, opened_at) VALUES (?, ?, ?, 'tenant', ?, 'open', ?)",
               (deposit["id"], deposit["org_id"], s["id"], reason.strip()[:2000], now_iso()))
        return transition(deposit, S.DISPUTED, "tenant", "Huurder betwist de afrekening", user_id, data={"reden": reason.strip()[:500]})


def open_dispute(deposit):
    return db.one("SELECT * FROM disputes WHERE deposit_id = ? AND status = 'open' ORDER BY id DESC LIMIT 1", (deposit["id"],))


def resolve_dispute(deposit, user_id, kind, landlord_cents, note, document_id):
    """Records an outcome that huurder and verhuurder reached, or a court decision. Depiqo never decides."""
    dispute = open_dispute(deposit)
    if deposit["status"] != S.DISPUTED or not dispute:
        raise WorkflowError("Er is geen open geschil.")
    if kind not in ("agreement", "court_decision"):
        raise WorkflowError("Kies of het om een akkoord of een vonnis gaat.")
    if landlord_cents is None or landlord_cents < 0 or landlord_cents > deposit["amount_cents"]:
        raise WorkflowError(f"Het bedrag voor de verhuurder moet tussen € 0 en {eur(deposit['amount_cents'])} liggen.")
    if not document_id:
        raise WorkflowError("Voeg het getekende akkoord of het vonnis toe als document.")
    if not db.one("SELECT id FROM documents WHERE id = ? AND deposit_id = ?", (document_id, deposit["id"])):
        raise WorkflowError("Het gekozen document hoort niet bij dit dossier.")
    with db.transaction():
        db.run("UPDATE disputes SET status = ?, resolution_note = ?, resolution_document_id = ?, landlord_amount_cents = ?, resolved_at = ? WHERE id = ?",
               (kind, (note or "").strip()[:2000], document_id, landlord_cents, now_iso(), dispute["id"]))
        db.run("UPDATE settlements SET status = 'superseded' WHERE deposit_id = ? AND status != 'superseded'", (deposit["id"],))
        sid = db.run("INSERT INTO settlements (deposit_id, org_id, status, created_by, created_at, proposed_at, responded_at) VALUES (?, ?, 'agreed', ?, ?, ?, ?)",
                     (deposit["id"], deposit["org_id"], user_id, now_iso(), now_iso(), now_iso()))
        if landlord_cents:
            db.run("INSERT INTO settlement_lines (settlement_id, category, description, amount_cents, document_id) VALUES (?, 'other', ?, ?, ?)",
                   (sid, "Volgens akkoord" if kind == "agreement" else "Volgens vonnis", landlord_cents, document_id))
        label = "akkoord tussen huurder en verhuurder" if kind == "agreement" else "beslissing van de rechter"
        notify.notify_tenant_of(deposit, "dispute_resolved", {"basis": f"@basis.{kind}", "landlord_cents": landlord_cents})
        return transition(deposit, S.AGREED, "user", f"Geschil afgesloten op basis van {label}: {eur(landlord_cents)} voor de verhuurder", user_id)


def payout_split(deposit):
    s = current_settlement(deposit)
    acct = account_for(deposit)
    available = acct["ledger_balance_cents"] if acct else deposit["amount_cents"]
    landlord = min(settlement_total(s) if s and s["status"] == "agreed" else 0, deposit["amount_cents"], available)
    return max(available - landlord, 0), landlord


def start_payout(deposit, user_id, document_id=None):
    """Depiqo account: a release instruction to the bank. Held elsewhere: the provider releases the deposit
    with its own procedure, and this records that it did (confirm_external_release, with proof)."""
    if deposit["status"] != S.AGREED:
        raise WorkflowError("Uitbetalen kan pas na akkoord of een afgesloten geschil.")
    if deposit["holding"] != "depiqo":
        return confirm_external_release(deposit, user_id, document_id)
    tenant_cents, landlord_cents = payout_split(deposit)
    if deposit["holding"] == "depiqo":
        acct = account_for(deposit)
        try:
            bank_for_account(acct)  # fail closed before anything changes
        except PartnerUnavailable as exc:
            raise WorkflowError(f"{exc} De uitbetaling kan niet starten.") from exc
        from . import investing
        with db.transaction():
            # Read inside the same IMMEDIATE transaction as the status change: a choice made on a stale page cannot
            # slip in between, and once the release instruction exists the choice can no longer change.
            if db.scalar("SELECT status FROM deposits WHERE id = ?", (deposit["id"],)) != S.AGREED:
                raise WorkflowError("Het dossier is intussen gewijzigd. Laad de pagina opnieuw.")
            destination = investing.payout_destination(deposit)  # the tenant's explicit choice (Invest), else their own account
            iid = enqueue_instruction(deposit, acct, "release",
                                      {"tenant_cents": tenant_cents, "landlord_cents": landlord_cents, "reference": deposit["reference"],
                                       **({"tenant_destination": destination} if destination else {})},
                                      f"release:{acct['id']}")
            # Same transaction: a payout confirmation that arrives before we record the bank's answer still matches.
            db.run("UPDATE bank_accounts SET status = 'release_requested' WHERE id = ?", (acct["id"],))
            deposit = transition(deposit, S.PAYOUT_PENDING, "user",
                                 f"Vrijgave-opdracht voor de bank klaargezet: {eur(tenant_cents)} aan huurder, {eur(landlord_cents)} aan verhuurder",
                                 user_id, data={"huurder": tenant_cents, "verhuurder": landlord_cents})
        _dispatch_after_commit([iid])
        return reload(deposit)


# ------------------------------------------------------------ release at an external provider

def release_form_available(deposit):
    """The release form exists for a deposit held elsewhere once the split is agreed: after the tenant's
    agreement or a resolved dispute (status agreed), and afterwards for the record (closed)."""
    if deposit["holding"] != "external" or deposit["status"] not in (S.AGREED, S.CLOSED):
        return False
    s = current_settlement(deposit)
    return bool(s) and s["status"] == "agreed"


def release_basis(deposit):
    """How the split was agreed: (text, date). From the resolved dispute if there was one, else the settlement."""
    s = current_settlement(deposit)
    dispute = db.one("SELECT * FROM disputes WHERE deposit_id = ? AND status IN ('agreement', 'court_decision') ORDER BY id DESC LIMIT 1",
                     (deposit["id"],))
    if dispute and s and dispute["resolved_at"] and parse_dt(s["created_at"]) >= parse_dt(dispute["resolved_at"]):
        text = ("Akkoord tussen huurder en verhuurder na een geschil" if dispute["status"] == "agreement"
                else "Beslissing van de rechter na een geschil")
        return text, dispute["resolved_at"]
    return "Akkoord van de huurder met de eindafrekening", (s["responded_at"] if s else None)


def confirm_external_release(deposit, user_id, document_id):
    """The provider (bank, e-DEPO, insurer, guarantor or the landlord's own account) has released the deposit
    as agreed. Recorded by finance or an admin with the provider's proof; closes the dossier through the
    normal transition AGREED -> CLOSED of the external path. Depiqo never releases anything itself."""
    if deposit["holding"] != "external":
        raise WorkflowError("Bij een Depiqo-borgrekening bevestigt de bank de uitbetaling, niet een medewerker.")
    if deposit["status"] != S.AGREED:
        raise WorkflowError("De vrijgave bevestig je na akkoord of een afgesloten geschil.")
    doc = _evidence_document(deposit, document_id, ("vrijgave",))
    if not doc:
        raise WorkflowError("Voeg eerst het bewijs van de aanbieder toe bij Documenten (soort 'Bewijs van vrijgave of terugbetaling') "
                            "en kies het hier.")
    tenant_cents, landlord_cents = payout_split(deposit)
    where = providers.label(deposit["provider_kind"])
    sets = {"asset_value_cents": 0, "eligible_value_cents": 0, "release_document_id": doc["id"]}
    if deposit["legal_lock_status"] in ("active", "requested"):
        sets["legal_lock_status"] = "released"
    with db.transaction():
        closed = transition(deposit, S.CLOSED, "user",
                            f"Vrijgave bij aanbieder bevestigd ({where}): {eur(tenant_cents)} aan huurder, {eur(landlord_cents)} aan verhuurder",
                            user_id, data={"huurder": tenant_cents, "verhuurder": landlord_cents, "bewijs": doc["id"]}, extra_sets=sets)
        notify.notify_tenant_of(deposit, "release_confirmed", {"tenant_cents": tenant_cents})
    return closed


PROVIDER_FIELDS = ("provider_kind", "provider_name", "provider_reference", "guarantee_expires_on", "external_iban")
PROVIDER_FIELD_LABELS = {"provider_kind": "soort", "provider_name": "naam", "provider_reference": "referentie",
                         "guarantee_expires_on": "garantie tot", "external_iban": "IBAN"}


def update_provider(deposit, user_id, fields):
    """Admin or manager: record or correct where a deposit held elsewhere sits. Only while the dossier runs.
    Once Depiqo verified the evidence (verified or legal) for this provider, only the expiry date of a
    guarantee can still change here. Returns (deposit, changes)."""
    if deposit["holding"] != "external":
        raise WorkflowError("Bij een Depiqo-borgrekening staat de borg bij de partnerbank. Daar is niets aan te passen.")
    if deposit["status"] in (S.CLOSED, S.CANCELLED):
        raise WorkflowError("Een gesloten of geannuleerd dossier pas je niet meer aan.")
    new = {k: fields.get(k) or None for k in PROVIDER_FIELDS}
    check = {**new, "holding": "external", "lease_start": deposit["lease_start"]}
    errors = providers.validate(check)
    if errors:
        raise WorkflowError(" ".join(errors))
    changes = {k: (deposit[k], new[k]) for k in PROVIDER_FIELDS if (deposit[k] or None) != new[k]}
    if not changes:
        return deposit, {}
    if deposit["evidence_level"] in ("verified", "legal") and set(changes) - {"guarantee_expires_on"}:
        raise WorkflowError("Depiqo heeft het bewijs voor deze aanbieder geverifieerd. Een andere aanbieder, naam, referentie of rekening "
                            "leg je vast via Depiqo, met nieuw bewijs.")
    sets = dict(new)
    sets["security_type"] = providers.security_type_for(new["provider_kind"])
    sets["custodian"] = providers.custodian_for(new["provider_kind"], new["provider_name"]) if new["provider_kind"] else None
    sets["updated_at"] = now_iso()
    cols = ", ".join(f"{k} = ?" for k in sets)  # fixed column names above, never user input
    summary = "; ".join(f"{PROVIDER_FIELD_LABELS[k]}: {_shown(k, old)} wordt {_shown(k, val)}" for k, (old, val) in changes.items())
    with db.transaction():
        changed = db.get_db().execute(f"UPDATE deposits SET {cols} WHERE id = ? AND status = ?",
                                      (*sets.values(), deposit["id"], deposit["status"])).rowcount
        if changed != 1:
            raise WorkflowError("Het dossier is intussen gewijzigd. Laad de pagina opnieuw.")
        add_event(deposit, "user", "provider", f"Aanbieder aangepast. {summary}"[:500], user_id,
                  data={k: v for k, (_, v) in changes.items()})
    return reload(deposit), changes


def _shown(field, value):
    if not value:
        return "leeg"
    if field == "provider_kind":
        return providers.label(value, short=True)
    return str(value)


# ------------------------------------------------------------ exceptions

def cancel(deposit, user_id, reason):
    acct = account_for(deposit)
    if acct and acct["ledger_balance_cents"] > 0:
        raise WorkflowError("Er staat al geld op de borgrekening. Annuleren kan dan niet; neem contact op met support.")
    with db.transaction():
        d = transition(deposit, S.CANCELLED, "user", f"Dossier geannuleerd: {(reason or 'geen reden opgegeven').strip()[:200]}", user_id)
        db.run("UPDATE bank_instructions SET status = 'failed', last_error = 'Dossier geannuleerd' WHERE deposit_id = ? AND kind = 'open' AND status = 'pending'",
               (deposit["id"],))
    return d


def set_legal_hold(deposit, user_id, on, reason):
    ids = []
    if on:
        if deposit["status"] not in S.HOLDABLE:
            raise WorkflowError("Dit dossier kan nu geen juridische blokkade krijgen.")
        if not (reason or "").strip():
            raise WorkflowError("Geef de reden van de blokkade op, zoals beslag of een lopende procedure.")
        with db.transaction():
            _set_status_if(deposit, S.LEGAL_HOLD, deposit["status"])
            add_event(deposit, "user", "status", f"Juridische blokkade: {reason.strip()[:200]}", user_id, deposit["status"], S.LEGAL_HOLD)
    else:
        if deposit["status"] != S.LEGAL_HOLD:
            raise WorkflowError("Er is geen blokkade om op te heffen.")
        with db.transaction():
            _set_status_if(deposit, deposit["hold_previous_status"], None)
            add_event(deposit, "user", "status", "Juridische blokkade opgeheven", user_id, S.LEGAL_HOLD, deposit["hold_previous_status"])
            reconcile_with_bank(reload(deposit), ids)
        _dispatch_after_commit(ids)
    return reload(deposit)


def _set_status_if(deposit, target, hold_previous):
    """Hold and release bypass the transition table, but keep the same optimistic check on the current status."""
    changed = db.get_db().execute("UPDATE deposits SET status = ?, hold_previous_status = ?, updated_at = ? WHERE id = ? AND status = ?",
                                  (target, hold_previous, now_iso(), deposit["id"], deposit["status"])).rowcount
    if changed != 1:
        raise WorkflowError("Het dossier is intussen gewijzigd. Laad de pagina opnieuw.")


def reconcile_with_bank(deposit, ids=None):
    """Catches up on bank messages that arrived while the dossier was on hold (they are recorded, not acted on)."""
    ids = [] if ids is None else ids
    acct = account_for(deposit)
    if not acct or deposit["holding"] != "depiqo":
        return deposit
    if deposit["status"] == S.ID_PENDING:
        deposit = transition(deposit, S.AWAITING_PAYMENT, "system", "Borgrekening was al geopend tijdens de blokkade")
    if deposit["status"] == S.AWAITING_PAYMENT and acct["ledger_balance_cents"] >= deposit["amount_cents"]:
        deposit = transition(deposit, S.PAYMENT_RECEIVED, "bank", "Storting was al ontvangen tijdens de blokkade; blokkering wordt aangevraagd")
        if acct["status"] != "blocked":
            ids.append(_request_block(deposit, acct))
    if deposit["status"] == S.PAYMENT_RECEIVED and acct["status"] == "blocked":
        deposit = transition(deposit, S.SECURED, "bank", "Bank had de borg al geblokkeerd tijdens de juridische blokkade")
    return deposit


# ------------------------------------------------------------ read models

def deadline_info(deposit):
    if deposit["status"] not in (S.MOVE_OUT, S.SETTLEMENT_PROPOSED, S.AGREED, S.DISPUTED, S.PAYOUT_PENDING):
        return None
    s = current_settlement(deposit)
    has_deductions = bool(s) and settlement_total(s) > 0
    due, statutory, why = rules.deadline(deposit, has_deductions)
    if not due:
        return None
    days = (due - today()).days
    return {"date": due, "statutory": statutory, "why": why, "days_left": days}


def mails_for(deposit):
    """Communication log: every message linked to this dossier, newest first."""
    return db.all_("SELECT id, to_email, subject, created_at, sent_at, provider, error FROM outbox_emails WHERE deposit_id = ? ORDER BY id DESC",
                   (deposit["id"],))


# Action centre: one group per kind of task, in this order when deadlines are equal.
ACTION_GROUPS = (
    ("uitnodigen", "Uitnodigen"),
    ("herinneren", "Herinneren"),
    ("bevestigen", "Ontvangst bevestigen"),
    ("afrekenen", "Afrekenen"),
    ("uitbetalen", "Uitbetalen"),
    ("betwisting", "Betwisting"),
    ("bewijs", "Bewijs ontbreekt"),
)
STALE_INVITE_DAYS = 3


def action_centre(org_id):
    """Tasks for today, grouped by action type. Each item has a direct action: a POST action on the
    deposit ('post', action, label) or a link to the deposit page ('link', anchor, label)."""
    rows = db.all_(
        "SELECT d.*, p.address, p.city, t.name AS tenant_name FROM deposits d "
        "JOIN properties p ON p.id = d.property_id JOIN tenants t ON t.id = d.tenant_id "
        "WHERE d.org_id = ? AND (d.status IN (?, ?, ?, ?, ?, ?, ?) OR (d.holding = 'external' AND d.evidence_level = 'declared' "
        "AND d.status NOT IN (?, ?)))",
        (org_id, S.CONCEPT, S.INVITED, S.ID_FAILED, S.AWAITING_PAYMENT, S.MOVE_OUT, S.AGREED, S.DISPUTED, S.CLOSED, S.CANCELLED))
    stale = (now() - timedelta(days=STALE_INVITE_DAYS)).isoformat(timespec="seconds")
    groups = {key: [] for key, _ in ACTION_GROUPS}
    for d in rows:
        info = deadline_info(d)
        item = {"d": d, "deadline": info, "urgency": info["days_left"] if info else 999}
        st = d["status"]
        if st == S.CONCEPT:
            groups["uitnodigen"].append({**item, "reason": "Uitnodiging nog niet verstuurd", "action": ("post", "uitnodigen", "Uitnodigen")})
        elif st == S.INVITED:
            if d["updated_at"] < stale:
                groups["herinneren"].append({**item, "reason": "Uitnodiging nog niet geopend", "action": ("post", "uitnodigen", "Opnieuw uitnodigen")})
        elif st == S.ID_FAILED:
            groups["herinneren"].append({**item, "reason": "Identificatie mislukt; huurder probeert opnieuw", "action": ("link", "", "Bekijken")})
        elif st == S.AWAITING_PAYMENT and d["holding"] == "depiqo":
            groups["herinneren"].append({**item, "reason": "Huurder heeft nog niet gestort", "action": ("post", "herinneren", "Herinnering sturen")})
        elif st == S.AWAITING_PAYMENT:
            groups["bevestigen"].append({**item, "reason": "Staat de borg op je rekening?", "action": ("link", "#volgende-stap", "Ontvangst bevestigen")})
        elif st == S.MOVE_OUT:
            groups["afrekenen"].append({**item, "reason": "Eindafrekening opstellen", "action": ("link", "#volgende-stap", "Afrekening maken")})
        elif st == S.AGREED and d["holding"] == "external":
            groups["uitbetalen"].append({**item, "reason": "Akkoord bereikt; vrijgave bij de aanbieder regelen",
                                         "action": ("link", "#volgende-stap", "Vrijgave regelen")})
        elif st == S.AGREED:
            groups["uitbetalen"].append({**item, "reason": "Akkoord bereikt", "action": ("link", "#volgende-stap", "Uitbetaling starten")})
        elif st == S.DISPUTED:
            groups["betwisting"].append({**item, "reason": "Huurder betwist de afrekening", "action": ("link", "#volgende-stap", "Geschil bekijken")})
        if d["holding"] == "external" and d["evidence_level"] == "declared" and st not in (S.CLOSED, S.CANCELLED):
            groups["bewijs"].append({**item, "reason": "Alleen verklaard; voeg een bankbewijs toe", "action": ("link", "#bewijs", "Bankbewijs toevoegen")})
    out = []
    for order, (key, label) in enumerate(ACTION_GROUPS):
        items = sorted(groups[key], key=lambda x: (x["urgency"], x["d"]["updated_at"]))
        if items:
            out.append({"key": key, "label": label, "tasks": items, "urgency": items[0]["urgency"], "order": order})
    out.sort(key=lambda g: (g["urgency"], g["order"]))
    return out
