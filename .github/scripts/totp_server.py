"""CI-only helper: serves the current TOTP code for the e2e test account on http://127.0.0.1:5055/totp.

    python3 .github/scripts/totp_server.py <totp_secret file> &

A slow simulator can take well over a minute from flow start to typing the code, so the flow asks for the code
at the moment it types it (mobile/.maestro/scripts/totp.js) instead of receiving it when the flow starts.
Uses the platform's own mfa.totp(); listens on localhost only and exists only on the CI runner.
"""
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "platform"))

from app import mfa  # noqa: E402

with open(sys.argv[1]) as f:
    SECRET = f.read().strip()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/totp":
            self.send_response(404)
            self.end_headers()
            return
        body = mfa.totp(SECRET, at=time.time()).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


HTTPServer(("127.0.0.1", 5055), Handler).serve_forever()
