"""CI only: extra test data on top of the demo seed, for the Maestro flows. Never used by seed.py or in development.

    cd platform && DATABASE_PATH=... STORAGE_DIR=... python3 ../.github/scripts/e2e_prepare.py <out-dir>

Uses the platform's own functions, on the freshly seeded CI database:
- lars@huurder.test gets two-step verification (TOTP, mfa.start_setup + mfa.confirm_setup). The secret goes to
  <out>/totp_secret (CI sandbox data, never a real account); .github/scripts/totp_now.py makes codes from it.
- Noor's open invitation (Biltstraat 301) gets a fresh token (services._invite_token, the function the invitation
  mail uses). The token goes to <out>/invite_token.
- <out>/e2e.json: the non-secret facts the flows assert.
Then checks both through the API (/api/v1) and exits non-zero if anything is not as expected.
"""
import json
import os
import sys

PLATFORM = os.getcwd()
sys.path.insert(0, PLATFORM)

from app import create_app, db, mfa, services  # noqa: E402

TOTP_EMAIL = "lars@huurder.test"
INVITE_ADDRESS = "Biltstraat 301"
PASSWORD = "Depiqo-demo-2026"


def fail(msg):
    print(f"e2e_prepare: {msg}", file=sys.stderr)
    sys.exit(1)


def write_secret(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(value)


def main():
    if len(sys.argv) != 2:
        fail("usage: e2e_prepare.py <out-dir>")
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    if os.environ.get("DEPIQO_ENV", "development") == "production":
        fail("refusing to run against production")
    app = create_app()
    if not app.config["SANDBOX"]:
        fail("the sandbox is off; the e2e data is for the sandbox only")
    with app.test_request_context("/"):
        user = db.one("SELECT * FROM users WHERE email = ?", (TOTP_EMAIL,))
        if not user:
            fail(f"{TOTP_EMAIL} not in the seed")
        if mfa.enabled(user):
            fail(f"{TOTP_EMAIL} already has 2FA; was the database seeded fresh?")
        mfa.start_setup(user["id"])
        user = db.one("SELECT * FROM users WHERE id = ?", (user["id"],))
        codes = mfa.confirm_setup(user, mfa.totp(user["totp_pending_secret"]))
        if not codes:
            fail("could not confirm the TOTP setup")
        # As the platform tests do: the setup code's step may be used again by the first login.
        db.run("UPDATE users SET totp_last_step = NULL WHERE id = ?", (user["id"],))
        secret = db.scalar("SELECT totp_secret FROM users WHERE id = ?", (user["id"],))

        d = db.one("SELECT d.* FROM deposits d JOIN properties p ON p.id = d.property_id WHERE p.address = ?", (INVITE_ADDRESS,))
        if not d or d["status"] != "invited":
            fail(f"no open invitation for {INVITE_ADDRESS}")
        raw = services._invite_token(d)
        org = db.one("SELECT name FROM organizations WHERE id = ?", (d["org_id"],))
        prop = db.one("SELECT * FROM properties WHERE id = ?", (d["property_id"],))
        facts = {"totp_email": TOTP_EMAIL, "invite": {"landlord": org["name"], "street": prop["address"], "postcode": prop["postcode"],
                                                    "city": prop["city"], "amount_cents": d["amount_cents"], "reference": d["reference"]}}

    write_secret(os.path.join(out, "totp_secret"), secret)
    write_secret(os.path.join(out, "invite_token"), raw)
    with open(os.path.join(out, "e2e.json"), "w") as f:
        json.dump(facts, f, indent=2)

    # Self-check through the API, as the app will see it.
    c = app.test_client()
    h = {"X-App-Platform": "android", "X-App-Version": "1.0.0"}
    r = c.post("/api/v1/auth/login", headers=h, json={"email": TOTP_EMAIL, "password": PASSWORD,
                                                       "device": {"name": "e2e_prepare", "platform": "android", "app_version": "1.0.0"}})
    if r.status_code != 200 or r.get_json().get("mfa_required") is not True:
        fail(f"login for {TOTP_EMAIL} does not ask for a second step: {r.status_code}")
    r = c.get(f"/api/v1/invites/{raw}", headers=h)
    if r.status_code != 200 or r.get_json()["landlord"]["name"] != facts["invite"]["landlord"]:
        fail(f"invitation not readable through the API: {r.status_code}")
    print(f"e2e_prepare: 2FA on for {TOTP_EMAIL}; invitation ready for {INVITE_ADDRESS} ({facts['invite']['landlord']}).")


if __name__ == "__main__":
    main()
