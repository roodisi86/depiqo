"""Adapters for external partners: bank, identity verification and e-mail.

Each partner sits behind a small interface so a real provider can replace the sandbox
without touching the workflow. Only the sandbox implementations exist today; they never
move real money and every screen that shows them says so.

Bank partner selection is explicit and fails closed:

    BANK_PARTNER=sandbox   only works while DEPIQO_SANDBOX=1
    BANK_PARTNER=<name>    a real adapter registered in BANK_ADAPTERS (none yet)
    anything else          DisabledBank: no account can be opened, no instruction is sent

See docs/ARCHITECTUUR.md for the adapter contract (methods, idempotency keys, webhook events).
"""
import hashlib
import hmac
import json
import secrets
import smtplib
from email.message import EmailMessage

from flask import current_app

from . import db
from .util import dumps, now_iso

NO_PARTNER_MESSAGE = "Er is geen financiële partner gekoppeld."


class PartnerError(Exception):
    """The partner refused or could not be reached. The instruction may be retried."""


class PartnerUnavailable(PartnerError):
    """No partner is configured, or the configured one may not be used. Never retried automatically."""


# ============================================================ bank

class BankPartner:
    """Contract every bank adapter must fulfil.

    The bank is the source of truth. Depiqo sends instructions (always with an idempotency key:
    the same key must give the same result and never a second account or payout) and records
    what the bank reports through events (webhooks). Status changes follow those events only.
    """
    name = "abstract"
    display_name = "Partnerbank"  # shown as custodian (bewaarder) of the deposit
    available = True
    is_sandbox = False

    def open_account(self, deposit, tenant, idempotency_key):
        """-> dict(external_id, iban, holder_name, interest_rate_bps, provider_ref)"""
        raise NotImplementedError

    def payment_instructions(self, account, deposit):
        """-> dict(iban, beneficiary, reference, amount_cents). Read only, no idempotency key."""
        raise NotImplementedError

    def request_block(self, account, idempotency_key):
        """-> dict(provider_ref). The bank confirms later with account.blocked."""
        raise NotImplementedError

    def request_release(self, account, tenant_cents, landlord_cents, reference, idempotency_key, tenant_destination=None):
        """-> dict(provider_ref). The bank confirms later with payout.completed carrying the paid amounts.
        tenant_destination (0.5.0, optional): dict(iban, reference) when the tenant chose to receive their share
        on their own investment account; otherwise the bank pays the tenant's own account."""
        raise NotImplementedError


class DisabledBank(BankPartner):
    """Used when no real partner is configured. Every call refuses."""
    name = "none"
    display_name = "Geen partnerbank"
    available = False

    def __init__(self, reason=NO_PARTNER_MESSAGE):
        self.reason = reason

    def _refuse(self, *args, **kwargs):
        raise PartnerUnavailable(self.reason)

    open_account = payment_instructions = request_block = request_release = _refuse


def _sandbox_iban():
    """A syntactically valid NL IBAN in a range no real bank uses (bank code DPQB)."""
    bban = "DPQB" + "".join(secrets.choice("0123456789") for _ in range(10))
    rearranged = bban + "NL00"
    digits = "".join(str(int(ch, 36)) for ch in rearranged)
    check = 98 - int(digits) % 97
    return f"NL{check:02d}{bban}"


class SandboxBank(BankPartner):
    name = "sandbox"
    display_name = "Sandbox-partnerbank"
    is_sandbox = True
    interest_rate_bps = 200  # 2,00% illustrative; a real partner supplies its own rate
    # Kinds of request that fail, to demo and test retries ({"release"} makes every release fail).
    failures = set()

    def _remembered(self, key):
        row = db.one("SELECT response_json FROM sandbox_requests WHERE idempotency_key = ?", (key,))
        return json.loads(row["response_json"]) if row else None

    def _remember(self, key, kind, response):
        db.run("INSERT OR IGNORE INTO sandbox_requests (idempotency_key, kind, response_json, created_at) VALUES (?, ?, ?, ?)",
               (key, kind, dumps(response), now_iso()))
        return self._remembered(key)

    def _maybe_fail(self, kind):
        if kind in self.failures:
            raise PartnerError("Sandbox: de bank is niet bereikbaar (gesimuleerde storing).")

    def open_account(self, deposit, tenant, idempotency_key):
        known = self._remembered(idempotency_key)
        if known:
            return known  # same key, same account: never a second one
        self._maybe_fail("open")
        external_id = "sbx_" + secrets.token_hex(8)
        iban = _sandbox_iban()
        db.run("INSERT INTO sandbox_bank_accounts (external_id, iban, holder_name, created_at) VALUES (?, ?, ?, ?)",
               (external_id, iban, tenant["name"], now_iso()))
        return self._remember(idempotency_key, "open", {
            "external_id": external_id, "iban": iban, "holder_name": tenant["name"],
            "interest_rate_bps": self.interest_rate_bps, "provider_ref": "sbx_open_" + secrets.token_hex(4)})

    def payment_instructions(self, account, deposit):
        return {"iban": account["iban"], "beneficiary": f"{account['holder_name']} (borgrekening)",
                "reference": deposit["reference"], "amount_cents": deposit["amount_cents"]}

    def request_block(self, account, idempotency_key):
        known = self._remembered(idempotency_key)
        if known:
            return known
        self._maybe_fail("block")
        # In the sandbox the "bank" blocks when someone presses the button (see the deposit page).
        return self._remember(idempotency_key, "block", {"provider_ref": "sbx_block_" + secrets.token_hex(4)})

    def request_release(self, account, tenant_cents, landlord_cents, reference, idempotency_key, tenant_destination=None):
        known = self._remembered(idempotency_key)
        if known:
            return known
        self._maybe_fail("release")
        db.run("UPDATE sandbox_bank_accounts SET release_tenant_cents = ?, release_landlord_cents = ? WHERE external_id = ?",
               (tenant_cents, landlord_cents, account["external_id"]))
        return self._remember(idempotency_key, "release", {"provider_ref": "sbx_release_" + secrets.token_hex(4)})

    # ---- sandbox-side simulation, used by the console; produces events like a real bank would
    def simulate(self, event_type, account, amount_cents=None, paid=None):
        """paid: optional (tenant_cents, landlord_cents) to override what the sandbox pays out (tests)."""
        payload = {"external_id": account["external_id"], "event_id": "evt_" + secrets.token_hex(8)}
        sbx = db.one("SELECT * FROM sandbox_bank_accounts WHERE external_id = ?", (account["external_id"],))
        if event_type == "deposit.received":
            payload.update(amount_cents=amount_cents, ref="dep_" + secrets.token_hex(6))
            db.run("UPDATE sandbox_bank_accounts SET balance_cents = balance_cents + ? WHERE id = ?", (amount_cents, sbx["id"]))
        elif event_type == "account.blocked":
            db.run("UPDATE sandbox_bank_accounts SET blocked = 1 WHERE id = ?", (sbx["id"],))
        elif event_type == "interest.credited":
            payload.update(amount_cents=amount_cents, ref="int_" + secrets.token_hex(6))
            db.run("UPDATE sandbox_bank_accounts SET balance_cents = balance_cents + ? WHERE id = ?", (amount_cents, sbx["id"]))
        elif event_type == "payout.completed":
            tenant_cents, landlord_cents = paid if paid else (sbx["release_tenant_cents"], sbx["release_landlord_cents"])
            payload.update(ref="pay_" + secrets.token_hex(6), tenant_cents=tenant_cents, landlord_cents=landlord_cents)
            db.run("UPDATE sandbox_bank_accounts SET balance_cents = 0, blocked = 0 WHERE id = ?", (sbx["id"],))
        return payload


# Real adapters (Banqup, Korfine, Certo, ...) register here under their configuration name.
BANK_ADAPTERS = {"sandbox": SandboxBank}


def bank():
    """The configured bank partner, or a DisabledBank. Never silently falls back to the sandbox."""
    cfg = current_app.config
    name = (cfg.get("BANK_PARTNER") or "").strip().lower()
    if not name:
        return DisabledBank()
    adapter = BANK_ADAPTERS.get(name)
    if adapter is None:
        return DisabledBank(f"{NO_PARTNER_MESSAGE} De ingestelde partner '{name}' bestaat niet.")
    if adapter.is_sandbox and (not cfg.get("SANDBOX") or cfg.get("ENV_NAME") == "production"):
        return DisabledBank(f"{NO_PARTNER_MESSAGE} De sandbox staat uit.")
    return adapter()


def bank_for_account(account):
    """The partner that may act on this account. Refuses sandbox accounts when the sandbox is off,
    and refuses a production adapter on an account that belongs to another provider."""
    partner = bank()
    if not partner.available:
        raise PartnerUnavailable(partner.reason)
    if account["provider"] != partner.name:
        if account["provider"] == "sandbox":
            raise PartnerUnavailable("Dit is een sandboxrekening. Een echte bankpartner mag deze rekening niet gebruiken.")
        raise PartnerUnavailable(f"Deze rekening hoort bij partner '{account['provider']}', niet bij '{partner.name}'.")
    return partner


def provider_allowed(provider):
    """Inbound events are only accepted from the configured, available partner."""
    partner = bank()
    return partner.available and partner.name == provider


def partner_status():
    """For screens: is a financial partner available, which one, and is it the sandbox."""
    partner = bank()
    return {"available": partner.available, "name": partner.name, "display_name": partner.display_name,
            "sandbox": partner.is_sandbox, "message": getattr(partner, "reason", "")}


def sign_webhook(body_bytes, secret):
    return hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()


def verify_webhook(body_bytes, signature, secret):
    expected = sign_webhook(body_bytes, secret)
    return hmac.compare_digest(expected, signature or "")


# ============================================================ identity

class SandboxKYC:
    """Approves every check unless the name contains 'TESTFAIL' (to demo the failure path)."""
    name = "sandbox"

    def verify(self, tenant, full_name, birth_date):
        if "TESTFAIL" in (full_name or "").upper():
            return "failed"
        return "approved"


def kyc():
    return SandboxKYC()


# ============================================================ e-mail

def send_mail(to_email, subject, body_text, deposit_id=None):
    """Every message is stored in the outbox. With SMTP configured it is also delivered.
    deposit_id links the message to a dossier for its communication log."""
    cfg = current_app.config
    provider = "smtp" if cfg.get("SMTP_HOST") else "outbox"
    mail_id = db.run("INSERT INTO outbox_emails (to_email, subject, body_text, created_at, provider, deposit_id) VALUES (?, ?, ?, ?, ?, ?)",
                     (to_email, subject, body_text, now_iso(), provider, deposit_id))
    if provider == "smtp":
        try:  # delivery failure must not break the workflow
            msg = EmailMessage()
            msg["From"] = cfg["MAIL_FROM"]
            msg["To"] = to_email
            msg["Subject"] = " ".join(subject.split())  # a newline in an org name must not break the header
            msg.set_content(body_text)
            with smtplib.SMTP(cfg["SMTP_HOST"], int(cfg.get("SMTP_PORT", 587)), timeout=15) as s:
                s.starttls()
                if cfg.get("SMTP_USER"):
                    s.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"])
                s.send_message(msg)
            db.run("UPDATE outbox_emails SET sent_at = ? WHERE id = ?", (now_iso(), mail_id))
        except Exception as exc:
            db.run("UPDATE outbox_emails SET error = ? WHERE id = ?", (str(exc)[:300], mail_id))
    return mail_id


__all__ = ["bank", "bank_for_account", "provider_allowed", "partner_status", "kyc", "send_mail", "sign_webhook",
           "verify_webhook", "dumps", "PartnerError", "PartnerUnavailable", "NO_PARTNER_MESSAGE"]
