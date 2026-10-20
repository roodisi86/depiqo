"""In-app notifications for tenants and the push outbox (Expo).

A notification is stored per user with a fixed title per type, a body with the details (shown in the
app after login) and a deep link path. Push messages carry only the fixed title and a fixed line,
never amounts, addresses or names: the app loads the details after authentication.

Push sending goes through an outbox (push_messages). With PUSH_SEND off (sandbox and development,
and always in tests unless switched on) a message is written with status 'skipped' and note
'sandbox'. The dispatcher posts pending messages to Expo, records the tickets, and later reads the
receipts; DeviceNotRegistered deactivates the token.
"""
import json
import urllib.request

from flask import current_app

from . import db, i18n
from .util import dumps, now_iso

EXPO_SEND_URL = "https://exp.host/--/api/v2/push/send"
EXPO_RECEIPTS_URL = "https://exp.host/--/api/v2/push/getReceipts"
PUSH_BODY = i18n.M["push.body"][0]

# type: category. Title (fixed, never amounts or personal data) and body (with parameters) come from the
# catalog in app/i18n.py: notif.<type>.title and notif.<type>.body, in Dutch, French and English.
TYPES = {
    "invite": "deposit", "payment_received": "deposit", "deposit_secured": "deposit", "settlement_proposed": "deposit",
    "dispute_resolved": "deposit", "payout_completed": "deposit", "release_confirmed": "deposit",
    "invest_order_executed": "invest", "invest_order_failed": "invest", "invest_withdrawal_completed": "invest",
    "invest_withdrawal_failed": "invest", "invest_fee_change": "invest",
    "new_device_login": "security", "support_reply": "support",
}
CATEGORIES = ("deposit", "invest", "security", "support")


def prefs(user):
    """Notification preferences of a user row, with defaults filled in."""
    try:
        raw = json.loads(user["notification_prefs"] or "{}")
    except (ValueError, TypeError):
        raw = {}
    push = {c: bool((raw.get("push") or {}).get(c, True)) for c in CATEGORIES}
    return {"push": push}


def deposit_link(deposit):
    return f"/app-link/borg/{deposit['pid']}"


INVEST_LINK = "/app-link/beleggen"


def render(type_, params, lang):
    """(title, body) of a notification in a language."""
    params = params or {}
    return i18n.t(f"notif.{type_}.title", lang), i18n.t(f"notif.{type_}.body", lang, **params)


def notify(user_id, type_, params=None, link=None):
    """Stores a notification (type and parameters, plus the Dutch text for the record) and queues a push per
    active token if the user allows this category. The push carries only the title and a fixed line, in the
    user's language. Safe inside a transaction; nothing here talks to the network."""
    if not user_id or type_ not in TYPES:
        return None
    user = db.one("SELECT * FROM users WHERE id = ? AND deleted_at IS NULL", (user_id,))
    if not user:
        return None
    category = TYPES[type_]
    title, body = render(type_, params, "nl")
    nid = db.run("INSERT INTO notifications (user_id, type, category, title, body, params_json, link_path, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                 (user_id, type_, category, title, body[:500], dumps(params or {}), link, now_iso()))
    if prefs(user)["push"].get(category, True):
        sending = push_enabled()
        lang = i18n.user_lang(user)
        push_title = i18n.t(f"notif.{type_}.title", lang)
        for t in db.all_("SELECT * FROM push_tokens WHERE user_id = ? AND active = 1", (user_id,)):
            db.run("INSERT INTO push_messages (user_id, push_token_id, notification_id, provider, title, body, data_json, status, note, created_at) "
                   "VALUES (?, ?, ?, 'expo', ?, ?, ?, ?, ?, ?)",
                   (user_id, t["id"], nid, push_title, i18n.t("push.body", lang), dumps({"notification_id": nid, "path": link, "type": type_}),
                    "pending" if sending else "skipped", None if sending else "sandbox", now_iso()))
    return nid


def notify_tenant_of(deposit, type_, params=None):
    """The user linked to the tenant of this deposit, if the tenant has an account."""
    uid = db.scalar("SELECT user_id FROM tenants WHERE id = ?", (deposit["tenant_id"],))
    return notify(uid, type_, params, deposit_link(deposit)) if uid else None


def notify_invest_account(account_id, type_, params=None):
    uid = db.scalar("SELECT user_id FROM invest_accounts WHERE id = ?", (account_id,))
    return notify(uid, type_, params, INVEST_LINK) if uid else None


# ------------------------------------------------------------ push dispatcher

def push_enabled():
    return bool(current_app.config.get("PUSH_SEND"))


def _post_json(url, payload):
    """POST JSON to Expo. Kept small so tests can replace it; the network is not used in sandbox."""
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    token_ = current_app.config.get("EXPO_ACCESS_TOKEN")
    if token_:
        headers["Authorization"] = f"Bearer {token_}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode() or "{}")


def deactivate_token(token_id, reason):
    db.run("UPDATE push_tokens SET active = 0, deactivated_at = ?, deactivated_reason = ? WHERE id = ? AND active = 1",
           (now_iso(), reason[:100], token_id))


def dispatch(limit=100):
    """Sends pending push messages to Expo in one batch. Returns counts. Without PUSH_SEND, pending rows
    (for example written before sending was switched off) are marked skipped."""
    out = {"sent": 0, "failed": 0, "skipped": 0}
    rows = db.all_("SELECT m.*, t.token, t.active FROM push_messages m JOIN push_tokens t ON t.id = m.push_token_id "
                   "WHERE m.status = 'pending' ORDER BY m.id LIMIT ?", (limit,))
    if not rows:
        return out
    if not push_enabled():
        for m in rows:
            db.run("UPDATE push_messages SET status = 'skipped', note = 'sandbox' WHERE id = ?", (m["id"],))
        out["skipped"] = len(rows)
        return out
    live = [m for m in rows if m["active"]]
    for m in rows:
        if not m["active"]:
            db.run("UPDATE push_messages SET status = 'skipped', note = 'token niet actief' WHERE id = ?", (m["id"],))
            out["skipped"] += 1
    if not live:
        return out
    payload = [{"to": m["token"], "title": m["title"], "body": m["body"], "data": json.loads(m["data_json"]), "sound": "default"} for m in live]
    try:
        resp = _post_json(EXPO_SEND_URL, payload)
    except Exception as exc:  # network or Expo down: stays pending, tried again (max 5 attempts)
        for m in live:
            db.run("UPDATE push_messages SET attempts = attempts + 1, note = ?, status = CASE WHEN attempts + 1 >= 5 THEN 'failed' ELSE 'pending' END "
                   "WHERE id = ?", (str(exc)[:200], m["id"]))
        out["failed"] = len(live)
        return out
    tickets = resp.get("data") or []
    for m, ticket in zip(live, tickets):
        if ticket.get("status") == "ok":
            db.run("UPDATE push_messages SET status = 'sent', ticket_id = ?, sent_at = ?, attempts = attempts + 1, note = NULL WHERE id = ?",
                   (ticket.get("id"), now_iso(), m["id"]))
            out["sent"] += 1
        else:
            error = (ticket.get("details") or {}).get("error") or ticket.get("message") or "onbekende fout"
            db.run("UPDATE push_messages SET status = 'failed', attempts = attempts + 1, note = ? WHERE id = ?", (str(error)[:200], m["id"]))
            if error == "DeviceNotRegistered":
                deactivate_token(m["push_token_id"], "DeviceNotRegistered")
            out["failed"] += 1
    return out


def check_receipts(limit=300):
    """Reads Expo receipts for sent messages. DeviceNotRegistered deactivates the token."""
    rows = db.all_("SELECT * FROM push_messages WHERE status = 'sent' AND ticket_id IS NOT NULL AND receipt_checked_at IS NULL "
                   "ORDER BY id LIMIT ?", (limit,))
    if not rows or not push_enabled():
        return 0
    try:
        resp = _post_json(EXPO_RECEIPTS_URL, {"ids": [m["ticket_id"] for m in rows]})
    except Exception:
        return 0
    receipts = resp.get("data") or {}
    done = 0
    for m in rows:
        r = receipts.get(m["ticket_id"])
        if r is None:
            continue  # not ready yet
        done += 1
        if r.get("status") == "ok":
            db.run("UPDATE push_messages SET status = 'delivered', receipt_checked_at = ? WHERE id = ?", (now_iso(), m["id"]))
            continue
        error = (r.get("details") or {}).get("error") or r.get("message") or "onbekende fout"
        db.run("UPDATE push_messages SET status = 'failed', receipt_checked_at = ?, note = ? WHERE id = ?", (now_iso(), str(error)[:200], m["id"]))
        if error == "DeviceNotRegistered":
            deactivate_token(m["push_token_id"], "DeviceNotRegistered")
    return done
