#!/usr/bin/env bash
# Starts the Depiqo platform for the e2e runs: fresh demo seed, CI-only extra data, gunicorn in the background.
#
#   .github/scripts/start_backend.sh <bind address:port> <work dir> [--no-e2e-data]
#
# --no-e2e-data: only the demo seed (for the platform's own browser test), without the CI-only extra data.
# development + sandbox (no real partners, no real money). The database, documents, logs and the CI-only secrets
# (TOTP secret, invitation token) live in <work dir>, outside the repository. Exits non-zero when the API does
# not answer /api/v1/config within 60 seconds.
set -euo pipefail

bind=${1:?bind address, e.g. 0.0.0.0:5000}
work=${2:?work dir}
extra=${3:-}
repo=$(cd "$(dirname "$0")/../.." && pwd)
port=${bind##*:}

mkdir -p "$work/db" "$work/logs"
export DEPIQO_ENV=development
export DEPIQO_SANDBOX=1
export DATABASE_PATH="$work/db/depiqo.sqlite3"
export STORAGE_DIR="$work/db/storage"
unset SECRET_KEY BANK_PARTNER INVEST_PARTNER

cd "$repo/platform"
python3 seed.py --reset | tee "$work/logs/seed.log"
if [ "$extra" != "--no-e2e-data" ]; then
  python3 "$repo/.github/scripts/e2e_prepare.py" "$work" | tee -a "$work/logs/seed.log"
fi

# One worker process with threads: SQLite in WAL mode, the same as a small staging host.
nohup gunicorn --workers 1 --threads 4 --bind "$bind" --access-logfile - --error-logfile - --capture-output \
  --access-logformat '%(t)s %(m)s %(U)s %(s)s %(L)ss' "run:app" > "$work/logs/backend.log" 2>&1 &
echo $! > "$work/backend.pid"

for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${port}/api/v1/config" -o "$work/logs/config.json"; then
    python3 - "$work/logs/config.json" <<'PY'
import json, sys
c = json.load(open(sys.argv[1]))
assert c["environment"] == "development" and c["sandbox"] is True, c
print(f"backend ready: API {c['api_version']}, environment {c['environment']}, banner {c['banner']}")
PY
    exit 0
  fi
  if ! kill -0 "$(cat "$work/backend.pid")" 2>/dev/null; then
    echo "backend exited:" >&2
    cat "$work/logs/backend.log" >&2
    exit 1
  fi
  sleep 1
done
echo "backend did not answer within 60 s" >&2
cat "$work/logs/backend.log" >&2
exit 1
