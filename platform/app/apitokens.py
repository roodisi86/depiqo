"""Bearer tokens for the tenant app (0.6.0).

Per device session (api_devices): an access token (15 minutes) and a refresh token (30 days). Both are
random and stored only as SHA-256 hashes. A refresh token works once: using it returns a new pair and
marks the old one used. A used refresh token that is presented again means two parties hold the same
token (theft or a copied backup): the whole device session is revoked and every token of it stops
working. The tenant sees and revokes device sessions on the web page Beveiliging and via the API.
"""
from datetime import timedelta

from . import db
from .util import now, now_iso, parse_dt, sha256, token

ACCESS_TTL = timedelta(minutes=15)
REFRESH_TTL = timedelta(days=30)
MFA_TTL = timedelta(minutes=5)
MFA_MAX_ATTEMPTS = 5


class TokenProblem(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def _iso(dt):
    return dt.isoformat(timespec="seconds")


def create_device(user_id, device, ip=None, mfa=False):
    t = now_iso()
    return db.run("INSERT INTO api_devices (user_id, device_name, platform, app_version, created_at, last_seen_at, last_ip, mfa_at) "
                  "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                  (user_id, device["name"], device["platform"], device["app_version"], t, t, ip, t if mfa else None))


def issue(device_id):
    """A new access and refresh token for this device session. Returns the raw values once."""
    access, refresh = token(), token()
    t = now()
    db.run("INSERT INTO api_access_tokens (device_id, token_hash, created_at, expires_at) VALUES (?, ?, ?, ?)",
           (device_id, sha256(access), _iso(t), _iso(t + ACCESS_TTL)))
    rid = db.run("INSERT INTO api_refresh_tokens (device_id, token_hash, created_at, expires_at) VALUES (?, ?, ?, ?)",
                 (device_id, sha256(refresh), _iso(t), _iso(t + REFRESH_TTL)))
    return {"access_token": access, "access_expires_at": _iso(t + ACCESS_TTL), "refresh_token": refresh,
            "refresh_expires_at": _iso(t + REFRESH_TTL), "token_type": "Bearer", "expires_in": int(ACCESS_TTL.total_seconds()),
            "_refresh_id": rid}


def authenticate(raw):
    """-> (user row, device row). Raises TokenProblem."""
    if not raw:
        raise TokenProblem("token_missing", "Log in om verder te gaan.")
    row = db.one("SELECT * FROM api_access_tokens WHERE token_hash = ?", (sha256(raw),))
    if not row:
        raise TokenProblem("token_invalid", "Je sessie is niet geldig. Log opnieuw in.")
    device = db.one("SELECT * FROM api_devices WHERE id = ?", (row["device_id"],))
    if not device or device["revoked_at"]:
        raise TokenProblem("device_revoked", "Dit apparaat is afgemeld. Log opnieuw in.")
    if parse_dt(row["expires_at"]) <= now():
        raise TokenProblem("token_expired", "Je sessie is verlopen. Vernieuw je sessie.")
    user = db.one("SELECT * FROM users WHERE id = ? AND deleted_at IS NULL", (device["user_id"],))
    if not user:
        raise TokenProblem("token_invalid", "Je sessie is niet geldig. Log opnieuw in.")
    return user, device


def touch(device, ip, app_version=None):
    db.run("UPDATE api_devices SET last_seen_at = ?, last_ip = ?, app_version = COALESCE(?, app_version) WHERE id = ?",
           (now_iso(), ip, app_version, device["id"]))


def rotate(raw):
    """Exchange a refresh token for a new pair. Reuse of a used token revokes the device session.
    Returns (tokens, device row). Raises TokenProblem."""
    if not raw:
        raise TokenProblem("token_missing", "Stuur je vernieuwingstoken mee.")
    with db.transaction():
        row = db.one("SELECT * FROM api_refresh_tokens WHERE token_hash = ?", (sha256(raw),))
        if not row:
            raise TokenProblem("token_invalid", "Je sessie is niet geldig. Log opnieuw in.")
        device = db.one("SELECT * FROM api_devices WHERE id = ?", (row["device_id"],))
        if not device or device["revoked_at"]:
            raise TokenProblem("device_revoked", "Dit apparaat is afgemeld. Log opnieuw in.")
        if row["used_at"]:
            _revoke(device["id"], "refresh_reuse")
            reused = True
        else:
            reused = False
            if parse_dt(row["expires_at"]) <= now():
                raise TokenProblem("token_expired", "Je sessie is verlopen. Log opnieuw in.")
            claimed = db.get_db().execute("UPDATE api_refresh_tokens SET used_at = ? WHERE id = ? AND used_at IS NULL",
                                          (now_iso(), row["id"])).rowcount
            if claimed != 1:
                _revoke(device["id"], "refresh_reuse")
                reused = True
    if reused:
        # outside the transaction above, so the revocation is committed before we answer
        raise TokenProblem("refresh_token_reused", "Deze sessie is om veiligheidsredenen beëindigd. Log opnieuw in.")
    tokens = issue(device["id"])
    db.run("UPDATE api_refresh_tokens SET replaced_by = ? WHERE id = ?", (tokens["_refresh_id"], row["id"]))
    return tokens, device


def _revoke(device_id, reason):
    db.run("UPDATE api_devices SET revoked_at = ?, revoked_reason = ? WHERE id = ? AND revoked_at IS NULL", (now_iso(), reason, device_id))
    # access tokens stay (stored hashed) so a request with one gets the clear answer device_revoked
    db.run("UPDATE api_access_tokens SET expires_at = ? WHERE device_id = ? AND expires_at > ?", (now_iso(), device_id, now_iso()))
    db.run("UPDATE api_refresh_tokens SET used_at = COALESCE(used_at, ?) WHERE device_id = ?", (now_iso(), device_id))
    db.run("UPDATE push_tokens SET active = 0, deactivated_at = ?, deactivated_reason = 'apparaat afgemeld' WHERE device_id = ? AND active = 1",
           (now_iso(), device_id))


def revoke_device(device_id, reason):
    with db.transaction():
        _revoke(device_id, reason)


def revoke_all(user_id, reason):
    """After a password reset or a change to two-factor authentication: every app session of the user ends."""
    with db.transaction():
        for d in db.all_("SELECT id FROM api_devices WHERE user_id = ? AND revoked_at IS NULL", (user_id,)):
            _revoke(d["id"], reason)


def devices(user_id):
    return db.all_("SELECT * FROM api_devices WHERE user_id = ? AND revoked_at IS NULL ORDER BY last_seen_at DESC", (user_id,))


# ------------------------------------------------------------ second step (2FA) at login

def start_challenge(user_id, device_json):
    raw = token()
    t = now()
    db.run("INSERT INTO api_mfa_challenges (user_id, token_hash, device_json, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
           (user_id, sha256(raw), device_json, _iso(t), _iso(t + MFA_TTL)))
    return raw, _iso(t + MFA_TTL)


def challenge(raw):
    row = db.one("SELECT * FROM api_mfa_challenges WHERE token_hash = ?", (sha256(raw or ""),))
    if not row or row["used_at"] or parse_dt(row["expires_at"]) <= now() or row["attempts"] >= MFA_MAX_ATTEMPTS:
        raise TokenProblem("mfa_token_invalid", "Deze inlogpoging is verlopen. Log opnieuw in met je wachtwoord.")
    return row


def claim_attempt(row):
    """Reserves one of the five attempts before the code is checked (0.6.1): one atomic update, so parallel
    requests can never use more than five. False when none are left or the challenge is used or expired."""
    return db.get_db().execute("UPDATE api_mfa_challenges SET attempts = attempts + 1 WHERE id = ? AND attempts < ? AND used_at IS NULL "
                               "AND expires_at > ?", (row["id"], MFA_MAX_ATTEMPTS, now_iso())).rowcount == 1


def challenge_used(row):
    return db.get_db().execute("UPDATE api_mfa_challenges SET used_at = ? WHERE id = ? AND used_at IS NULL", (now_iso(), row["id"])).rowcount == 1
