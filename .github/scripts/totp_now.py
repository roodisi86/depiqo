"""Prints a TOTP code for the CI test account, made with the platform's own mfa.totp().

    python3 .github/scripts/totp_now.py <totp_secret file>

The code is for the NEXT 30-second step. The platform accepts the current step and one either side, so this code
is valid right away and for 60 to 90 seconds, enough for Maestro to launch the app, log in and type it. It is
never printed anywhere else (the runner passes it to Maestro as an environment value).
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "platform"))

from app import mfa  # noqa: E402

if len(sys.argv) != 2:
    sys.exit("usage: totp_now.py <secret-file>")
with open(sys.argv[1]) as f:
    secret = f.read().strip()
print(mfa.totp(secret, at=time.time() + mfa.STEP))
