"""Two-factor authentication: TOTP (RFC 6238, HMAC-SHA1, 6 digits, 30 seconds) and recovery codes.

Standard library only. No QR library is available, so the setup page shows the otpauth:// URI
and the base32 secret for manual entry in an authenticator app.

- A code is accepted for the current time step and one step either side (clock drift).
- A step that was used once is never accepted again (replay protection via users.totp_last_step).
- Ten recovery codes, stored as SHA-256 hashes, each usable once.
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

from . import db
from .util import now_iso, sha256

STEP = 30
DIGITS = 6
WINDOW = 1
RECOVERY_COUNT = 10
ISSUER = "Depiqo"


def new_secret():
    """160 random bits as base32 without padding (what authenticator apps expect)."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _key(secret):
    s = secret.upper().replace(" ", "")
    return base64.b32decode(s + "=" * (-len(s) % 8))


def hotp(key_bytes, counter, digits=DIGITS, digest=hashlib.sha1):
    mac = hmac.new(key_bytes, struct.pack(">Q", counter), digest).digest()
    offset = mac[-1] & 0x0F
    value = struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % (10 ** digits)).zfill(digits)


def totp(secret, at=None, digits=DIGITS):
    return hotp(_key(secret), int((time.time() if at is None else at) // STEP), digits)


def step_now(at=None):
    return int((time.time() if at is None else at) // STEP)


def match_step(secret, code, last_step=None, at=None):
    """Returns the matching time step, or None. Rejects steps at or before last_step (replay)."""
    code = "".join(ch for ch in (code or "") if ch.isdigit())
    if len(code) != DIGITS:
        return None
    key = _key(secret)
    current = step_now(at)
    for step in range(current - WINDOW, current + WINDOW + 1):
        if last_step is not None and step <= last_step:
            continue
        if hmac.compare_digest(hotp(key, step), code):
            return step
    return None


def otpauth_uri(secret, email):
    label = quote(f"{ISSUER}:{email}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(ISSUER)}&algorithm=SHA1&digits={DIGITS}&period={STEP}"


def group(secret):
    return " ".join(secret[i:i + 4] for i in range(0, len(secret), 4))


# ---------------------------------------------------------------- per user

def enabled(user):
    return bool(user and user["totp_enabled_at"] and user["totp_secret"])


def start_setup(user_id):
    secret = new_secret()
    db.run("UPDATE users SET totp_pending_secret = ? WHERE id = ?", (secret, user_id))
    return secret


def confirm_setup(user, code):
    """Turns 2FA on when the code matches the pending secret. Returns the recovery codes (shown once) or None."""
    secret = user["totp_pending_secret"]
    if not secret:
        return None
    step = match_step(secret, code)
    if step is None:
        return None
    with db.transaction():
        db.run("UPDATE users SET totp_secret = ?, totp_pending_secret = NULL, totp_enabled_at = ?, totp_last_step = ? WHERE id = ?",
               (secret, now_iso(), step, user["id"]))
        codes = _new_recovery_codes(user["id"])
    return codes


def disable(user_id):
    with db.transaction():
        db.run("UPDATE users SET totp_secret = NULL, totp_pending_secret = NULL, totp_enabled_at = NULL, totp_last_step = NULL WHERE id = ?",
               (user_id,))
        db.run("DELETE FROM recovery_codes WHERE user_id = ?", (user_id,))


def _recovery_code():
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    raw = "".join(secrets.choice(alphabet) for _ in range(10))
    return f"{raw[:5]}-{raw[5:]}"


def _normalise_recovery(code):
    s = "".join(ch for ch in (code or "").lower() if ch.isalnum())
    return f"{s[:5]}-{s[5:]}" if len(s) == 10 else None


def _new_recovery_codes(user_id):
    db.run("DELETE FROM recovery_codes WHERE user_id = ?", (user_id,))
    codes = [_recovery_code() for _ in range(RECOVERY_COUNT)]
    for c in codes:
        db.run("INSERT INTO recovery_codes (user_id, code_hash, created_at) VALUES (?, ?, ?)", (user_id, sha256(c), now_iso()))
    return codes


def regenerate_recovery_codes(user_id):
    with db.transaction():
        return _new_recovery_codes(user_id)


def recovery_left(user_id):
    return db.scalar("SELECT COUNT(*) FROM recovery_codes WHERE user_id = ? AND used_at IS NULL", (user_id,))


def verify_totp(user, code):
    """Only a TOTP code (never a recovery code): six digits, the step marked as used. True or False."""
    if not enabled(user) or not is_totp_format(code):
        return False
    step = match_step(user["totp_secret"], code, user["totp_last_step"])
    if step is None:
        return False
    return db.get_db().execute("UPDATE users SET totp_last_step = ? WHERE id = ? AND (totp_last_step IS NULL OR totp_last_step < ?)",
                               (step, user["id"], step)).rowcount == 1


def is_totp_format(code):
    return len("".join(ch for ch in (code or "") if ch.isdigit())) == DIGITS and all(ch.isdigit() or ch == " " for ch in (code or "").strip())


def verify(user, code):
    """Checks a login code: a TOTP code, or a recovery code. Returns 'totp', 'recovery' or None.
    Marks the TOTP step or the recovery code as used."""
    if not enabled(user):
        return None
    step = match_step(user["totp_secret"], code, user["totp_last_step"])
    if step is not None:
        changed = db.get_db().execute("UPDATE users SET totp_last_step = ? WHERE id = ? AND (totp_last_step IS NULL OR totp_last_step < ?)",
                                      (step, user["id"], step)).rowcount
        return "totp" if changed == 1 else None
    normal = _normalise_recovery(code)
    if normal:
        changed = db.get_db().execute("UPDATE recovery_codes SET used_at = ? WHERE user_id = ? AND code_hash = ? AND used_at IS NULL",
                                      (now_iso(), user["id"], sha256(normal))).rowcount
        if changed == 1:
            return "recovery"
    return None
