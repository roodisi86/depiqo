"""Deposit state machine.

The single rule that matters most: a deposit only becomes SECURED on a confirmation
from the bank (depiqo holding) or an explicit receipt declaration by a finance user
(external holding). A payment instruction or a tenant's "I paid" never secures it.

SECURED means "the security is registered". How strong that security is, is a separate
fact: the evidence level (external holding) or the bank's lock (Depiqo account). Screens
never show SECURED on its own; they use display_status(), which only shows the green
"Zekerheid bevestigd" when the bank confirmed the lock or legal security was proven.
"""

CONCEPT = "concept"
INVITED = "invited"
ID_PENDING = "id_pending"
AWAITING_PAYMENT = "awaiting_payment"
PAYMENT_RECEIVED = "payment_received"
SECURED = "secured"
MOVE_OUT = "move_out"
SETTLEMENT_PROPOSED = "settlement_proposed"
AGREED = "agreed"
DISPUTED = "disputed"
PAYOUT_PENDING = "payout_pending"
CLOSED = "closed"
CANCELLED = "cancelled"
ID_FAILED = "id_failed"
LEGAL_HOLD = "legal_hold"

LABELS = {
    CONCEPT: "Concept",
    INVITED: "Uitnodiging verstuurd",
    ID_PENDING: "Identificatie loopt",
    AWAITING_PAYMENT: "Wacht op storting",
    PAYMENT_RECEIVED: "Storting ontvangen, bevestiging bank",
    SECURED: "Zekerheid geregistreerd",
    MOVE_OUT: "Vertrek gestart",
    SETTLEMENT_PROPOSED: "Afrekening voorgesteld",
    AGREED: "Akkoord, klaar voor uitbetaling",
    DISPUTED: "Betwist",
    PAYOUT_PENDING: "Uitbetaling loopt",
    CLOSED: "Uitbetaald en gesloten",
    CANCELLED: "Geannuleerd",
    ID_FAILED: "Identificatie mislukt",
    LEGAL_HOLD: "Juridische blokkade",
}

TENANT_LABELS = {
    CONCEPT: "In voorbereiding",
    INVITED: "Bevestig je gegevens",
    ID_PENDING: "Bevestig je identiteit",
    AWAITING_PAYMENT: "Stort je borg",
    PAYMENT_RECEIVED: "Storting ontvangen, wacht op de bank",
    SECURED: "Je borg is geregistreerd",
    MOVE_OUT: "Je vertrek is gestart",
    SETTLEMENT_PROPOSED: "Bekijk de eindafrekening",
    AGREED: "Akkoord, uitbetaling volgt",
    DISPUTED: "Je hebt de afrekening betwist",
    PAYOUT_PENDING: "Uitbetaling loopt",
    CLOSED: "Uitbetaald",
    CANCELLED: "Geannuleerd",
    ID_FAILED: "Identificatie niet gelukt",
    LEGAL_HOLD: "Tijdelijk geblokkeerd",
}

TONE = {
    CONCEPT: "neutral", INVITED: "info", ID_PENDING: "info", AWAITING_PAYMENT: "wait",
    PAYMENT_RECEIVED: "wait", SECURED: "info", MOVE_OUT: "info", SETTLEMENT_PROPOSED: "wait",
    AGREED: "ok", DISPUTED: "alert", PAYOUT_PENDING: "wait", CLOSED: "done",
    CANCELLED: "neutral", ID_FAILED: "alert", LEGAL_HOLD: "alert",
}

# Ordered happy path, used for progress bars.
PATH = [CONCEPT, INVITED, ID_PENDING, AWAITING_PAYMENT, PAYMENT_RECEIVED, SECURED, MOVE_OUT,
        SETTLEMENT_PROPOSED, AGREED, PAYOUT_PENDING, CLOSED]

TRANSITIONS = {
    CONCEPT: {INVITED, CANCELLED, SECURED},  # SECURED only by the import of an existing external deposit
    INVITED: {ID_PENDING, AWAITING_PAYMENT, CANCELLED, INVITED},
    ID_PENDING: {AWAITING_PAYMENT, ID_FAILED, CANCELLED},
    ID_FAILED: {ID_PENDING, CANCELLED},
    AWAITING_PAYMENT: {PAYMENT_RECEIVED, SECURED, CANCELLED},
    PAYMENT_RECEIVED: {SECURED},
    SECURED: {MOVE_OUT},
    MOVE_OUT: {SETTLEMENT_PROPOSED, AGREED},
    SETTLEMENT_PROPOSED: {AGREED, DISPUTED, MOVE_OUT},
    DISPUTED: {AGREED, SETTLEMENT_PROPOSED},
    AGREED: {PAYOUT_PENDING, CLOSED},
    PAYOUT_PENDING: {CLOSED},
    CLOSED: set(),
    CANCELLED: set(),
}

# Which actor kinds may cause a transition into a state. Guards SECURED in particular.
ALLOWED_ACTORS = {
    PAYMENT_RECEIVED: {"bank"},
    SECURED: {"bank", "user"},      # "user" only for external holding, checked in services
    CLOSED: {"bank", "user", "system"},
}

ACTIVE = {INVITED, ID_PENDING, ID_FAILED, AWAITING_PAYMENT, PAYMENT_RECEIVED, SECURED, MOVE_OUT,
          SETTLEMENT_PROPOSED, AGREED, DISPUTED, PAYOUT_PENDING, LEGAL_HOLD}
# Not PAYOUT_PENDING: the release order is already at the bank and cannot be held from here.
HOLDABLE = ACTIVE - {LEGAL_HOLD, PAYOUT_PENDING}


class TransitionError(Exception):
    pass


def check(current, target, actor_kind):
    if current == LEGAL_HOLD:
        raise TransitionError("Dit dossier heeft een juridische blokkade. Hef die eerst op.")
    if target not in TRANSITIONS.get(current, set()):
        raise TransitionError(f"Van '{LABELS.get(current, current)}' kan het dossier niet naar '{LABELS.get(target, target)}'.")
    allowed = ALLOWED_ACTORS.get(target)
    if allowed and actor_kind not in allowed:
        raise TransitionError(f"'{LABELS[target]}' kan alleen door {', '.join(sorted(allowed))} worden gezet.")


# ---------------------------------------------------------------- evidence and display

EVIDENCE_LEVELS = ("declared", "document", "verified", "legal")
EVIDENCE = {
    "declared": {"short": "Verklaard", "label": "Verklaard door beheerder", "tone": "wait",
                 "secured": "Ontvangst verklaard door beheerder", "tenant": "Ontvangst verklaard door je verhuurder"},
    "document": {"short": "Bankbewijs", "label": "Bankdocument ontvangen", "tone": "neutral",
                 "secured": "Bankbewijs ontvangen, niet geverifieerd", "tenant": "Bankbewijs van je verhuurder ontvangen"},
    "verified": {"short": "Geverifieerd", "label": "Extern geverifieerd door Depiqo", "tone": "info",
                 "secured": "Ontvangst geverifieerd door Depiqo", "tenant": "Ontvangst geverifieerd door Depiqo"},
    "legal": {"short": "Juridisch zeker", "label": "Juridische zekerheid bevestigd", "tone": "ok",
              "secured": "Zekerheid bevestigd", "tenant": "Je borg staat veilig"},
}
CONFIRMED_LABEL = "Zekerheid bevestigd"


def _get(row, key):
    try:
        return row[key]
    except (KeyError, IndexError):
        return None


UNTRUSTED_LOCK = {"code": "untrusted", "short": "SANDBOX, niet bevestigd",
                  "label": "Blokkering op een sandboxrekening of bij een andere partner: niet bevestigd door de actieve bank", "tone": "wait"}


def assurance(d, lock_trusted=True):
    """How strong the security of this deposit is, whatever its status. None if nothing is known yet.
    lock_trusted: the account is held by the active partner (see services.lock_trusted). A lock on a
    sandbox account while the sandbox is off is never shown as confirmed.
    Returns dict(code, short, label, tone)."""
    if _get(d, "holding") == "depiqo":
        lock = _get(d, "legal_lock_status")
        if lock in ("active", "requested") and not lock_trusted:
            return UNTRUSTED_LOCK
        if lock == "active":
            return {"code": "bank", "short": "Bank bevestigd", "label": "Blokkering bevestigd door de bank", "tone": "ok"}
        if lock == "requested":
            return {"code": "bank_requested", "short": "Blokkering aangevraagd", "label": "Blokkering aangevraagd bij de bank", "tone": "wait"}
        if lock == "released":
            return {"code": "released", "short": "Vrijgegeven", "label": "Blokkering vrijgegeven", "tone": "done"}
        return None
    level = _get(d, "evidence_level")
    if level in EVIDENCE:
        e = EVIDENCE[level]
        return {"code": level, "short": e["short"], "label": e["label"], "tone": e["tone"]}
    return None


def display(d, tenant=False, lock_trusted=True):
    """(key, label, tone) for a deposit row. SECURED depends on the evidence; nothing else changes. The key is
    stable (for the app to translate): the status itself, or a refinement such as 'secured_bank_confirmed'."""
    status = d["status"]
    if _get(d, "holding") == "external":
        # 0.4.0: a guarantee is not paid, and a provider releases (it does not pay out through Depiqo).
        if status == AWAITING_PAYMENT and _get(d, "provider_kind") in ("borggarantie", "ocmw"):
            return "awaiting_guarantee", ("Je borg wordt geregeld" if tenant else "Wacht op garantie of attest"), "wait"
        if status == CLOSED and _get(d, "release_document_id"):
            return "released", ("Vrijgegeven" if tenant else "Vrijgegeven en gesloten"), "done"
    if status == SECURED:
        if _get(d, "holding") == "depiqo":
            if _get(d, "legal_lock_status") == "active" and not lock_trusted:
                return "secured_untrusted_lock", UNTRUSTED_LOCK["short"], "wait"
            if _get(d, "legal_lock_status") == "active":
                return "secured_bank_confirmed", ("Je borg staat veilig" if tenant else CONFIRMED_LABEL), "ok"
        else:
            level = _get(d, "evidence_level")
            e = EVIDENCE.get(level)
            if e:
                return f"secured_{level}", (e["tenant"] if tenant else e["secured"]), e["tone"]
    return status, (TENANT_LABELS if tenant else LABELS)[status], TONE[status]


def display_status(d, tenant=False, lock_trusted=True):
    """(label, tone) for a deposit row; see display()."""
    return display(d, tenant, lock_trusted)[1:]


def progress(status):
    if status in PATH:
        return (PATH.index(status) + 1) / len(PATH)
    return 0
