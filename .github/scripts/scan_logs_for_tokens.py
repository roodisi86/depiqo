"""Fails when a device log contains an API token.

    python3 .github/scripts/scan_logs_for_tokens.py <depiqo.sqlite3> <log> [<log> ...]

Three checks, none of which prints a token value:
1. "access_token" / "refresh_token" / "mfa_token" followed by a token-like value (a redacted value passes).
2. "Bearer <token-like value>".
3. Exact: every 43-character URL-safe string in the logs (the length of secrets.token_urlsafe(32)) is hashed and
   looked up in the CI database's api_access_tokens, api_refresh_tokens and api_mfa_challenges. A hit means a
   real token that the server issued during this run ended up in a log.
Exit 1 on any finding, 2 on a usage or database problem.
"""
import hashlib
import re
import sqlite3
import sys

KEYED = re.compile(r"(?i)(access_token|refresh_token|mfa_token)[\"'\\]*\s*[:=]\s*[\"'\\]*([A-Za-z0-9_\-]{20,})")
BEARER = re.compile(r"Bearer\s+([A-Za-z0-9_\-.~+/=]{20,})")
CANDIDATE = re.compile(r"(?<![A-Za-z0-9_\-])[A-Za-z0-9_\-]{43}(?![A-Za-z0-9_\-])")
TABLES = ("api_access_tokens", "api_refresh_tokens", "api_mfa_challenges")


def main():
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        conn = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
        known = set()
        for t in TABLES:
            known |= {r[0] for r in conn.execute(f"SELECT token_hash FROM {t}")}  # noqa: S608 (fixed table names)
    except sqlite3.Error as exc:
        print(f"scan: cannot read the CI database: {exc}", file=sys.stderr)
        return 2
    if not known:
        print("scan: the database has no issued tokens; did the flows log in at all?", file=sys.stderr)
        return 2
    findings = 0
    scanned = 0
    for path in sys.argv[2:]:
        with open(path, encoding="utf-8", errors="replace") as f:
            for n, line in enumerate(f, 1):
                scanned += 1
                for m in KEYED.finditer(line):
                    findings += 1
                    print(f"FOUT {path}:{n}: '{m.group(1)}' with a token-like value ({len(m.group(2))} chars)")
                for m in BEARER.finditer(line):
                    findings += 1
                    print(f"FOUT {path}:{n}: Bearer header with a value ({len(m.group(1))} chars)")
                for m in CANDIDATE.finditer(line):
                    if hashlib.sha256(m.group(0).encode("utf-8")).hexdigest() in known:
                        findings += 1
                        print(f"FOUT {path}:{n}: an API token issued in this run appears in the log")
    print(f"scan: {scanned} lines in {len(sys.argv) - 2} file(s), {len(known)} issued tokens checked, {findings} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
