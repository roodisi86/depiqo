"""Smoke test of the tenant app API against a running development server with the demo data.

    python3 seed.py --reset && python3 run.py &
    python3 tests/api_smoke.py [http://127.0.0.1:5000]

Logs in as a seeded tenant with Invest (daan@huurder.test), reads the deposits, asks a quote, places an order
with an Idempotency-Key (twice: the second call must replay), reads the notifications, marks one as read and
logs out. Standard library only. Exits with 1 on the first failure.
"""
import json
import sys
import uuid
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5000").rstrip("/") + "/api/v1"
EMAIL, PASSWORD = "daan@huurder.test", "Depiqo-demo-2026"
DEVICE = {"name": "Rooktest", "platform": "ios", "app_version": "1.0.0"}


def call(method, path, token=None, body=None, headers=None):
    h = {"Accept": "application/json", "X-App-Platform": "ios", "X-App-Version": "1.0.0", **(headers or {})}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    if token:
        h["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None), dict(r.headers)
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, (json.loads(raw) if raw else None), dict(e.headers)


def check(ok, what, detail=None):
    print(("OK   " if ok else "FOUT ") + what + ("" if ok or detail is None else f"\n     {detail}"))
    if not ok:
        sys.exit(1)


def main():
    status, cfg, _ = call("GET", "/config")
    check(status == 200 and cfg["sandbox"], f"config (omgeving {cfg and cfg.get('environment')}, banner {cfg and cfg.get('banner')})", cfg)

    status, s, _ = call("POST", "/auth/login", body={"email": EMAIL, "password": PASSWORD, "device": DEVICE})
    check(status == 200 and s.get("access_token"), f"inloggen als {EMAIL}", s)
    tok = s["access_token"]

    status, me, _ = call("GET", "/me", tok)
    check(status == 200 and me["invest"]["eligible"], f"me: {me['name']}, beleggen {me['invest']['visibility']}", me)

    status, deps, _ = call("GET", "/deposits", tok)
    check(status == 200 and deps["items"], f"borgen: {len(deps['items'])}", deps)
    pid = deps["items"][0]["pid"]
    status, d, _ = call("GET", f"/deposits/{pid}", tok)
    check(status == 200, f"borg {d['reference']}: {d['display_key']} ({d['display_label']}), {len(d['events'])} gebeurtenissen", d)

    status, inv, _ = call("GET", "/invest", tok)
    check(status == 200 and inv["summary"], f"beleggen: waarde {inv['summary']['value']['cents'] / 100:.2f} EUR, "
                                            f"vrij {inv['summary']['available']['cents'] / 100:.2f} EUR", inv)

    if inv["summary"]["available"]["cents"] < 2500:  # sandbox: first put money on the account
        status, dep, _ = call("POST", "/invest/sandbox/deposit", tok, {"amount_cents": 5000}, {"Idempotency-Key": "smoke-dep-" + uuid.uuid4().hex[:8]})
        check(status == 201, f"sandbox: storting van 50,00 EUR ({dep and dep.get('result')})", dep)

    status, q, _ = call("POST", "/invest/orders/quote", tok, {"side": "buy", "amount_cents": 2500})
    check(status == 201 and q.get("quote_id"), f"offerte {q.get('quote_id')}: kosten 1 jaar {q['costs']['total_1y']['cents'] / 100:.2f} EUR, "
                                               f"geldig tot {q['expires_at']}", q)

    key = "smoke-" + uuid.uuid4().hex[:12]
    status, o, _ = call("POST", "/invest/orders", tok, {"quote_id": q["quote_id"], "risk_acknowledged": True}, {"Idempotency-Key": key})
    ok = status == 201 and o["order"]["status"] == "pending"
    check(ok, f"order {o['order']['id']} geplaatst: {o['order']['status_label']}" if ok else "order plaatsen", o)
    status, o2, h = call("POST", "/invest/orders", tok, {"quote_id": q["quote_id"], "risk_acknowledged": True}, {"Idempotency-Key": key})
    check(status == 201 and o2 == o and h.get("Idempotent-Replayed") == "true", "zelfde Idempotency-Key: zelfde antwoord, geen tweede order", o2)

    status, n, _ = call("GET", "/notifications?limit=5", tok, headers={"Accept-Language": "en"})
    check(status == 200 and n["items"], f"meldingen: {len(n['items'])} getoond, {n['unread_count']} ongelezen; laatste: {n['items'][0]['title']}", n)
    status, r, _ = call("POST", f"/notifications/{n['items'][0]['id']}/read", tok)
    check(status == 200 and r["read_at"], "melding gelezen", r)

    status, e, _ = call("GET", "/deposits/bestaat-niet", tok, headers={"Accept-Language": "fr"})
    check(status == 404 and e["error"]["code"] == "not_found", f"fout in het Frans: {e['error']['message']}", e)

    status, _, _ = call("POST", "/auth/logout", tok)
    check(status == 204, "uitloggen")
    status, e, _ = call("GET", "/me", tok)
    check(status == 401 and e["error"]["code"] == "device_revoked", "token werkt niet meer na uitloggen", e)
    print("Rooktest geslaagd.")


if __name__ == "__main__":
    main()
