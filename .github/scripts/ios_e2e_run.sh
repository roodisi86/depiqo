#!/usr/bin/env bash
# Boots an iPhone simulator, installs the Release .app and runs the Maestro suite.
#
#   .github/scripts/ios_e2e_run.sh <variant> <path/to/App.app> <out-dir>
#
# variant: nl | large-dark | fr-en (see android_e2e_run.sh). Picks an available iPhone 16, else iPhone 15, else
# any iPhone. Streams the app's unified log for the token scan.
set -uo pipefail

variant=${1:?variant}
app=${2:?app}
out=${3:?out dir}
repo=$(cd "$(dirname "$0")/../.." && pwd)
APP_ID=com.getdepiqo.app.dev
mkdir -p "$out"
out=$(cd "$out" && pwd)
status=0

udid=$(xcrun simctl list devices available -j | python3 -c '
import json, sys
devs = [d | {"runtime": r} for r, ds in json.load(sys.stdin)["devices"].items() if "iOS" in r for d in ds if d.get("isAvailable", True)]
def pick(prefix):
    c = [d for d in devs if d["name"].startswith(prefix)]
    c.sort(key=lambda d: d["runtime"], reverse=True)   # newest iOS runtime first
    return c[0] if c else None
d = pick("iPhone 16") or pick("iPhone 15") or pick("iPhone")
if not d:
    sys.exit("no iPhone simulator available")
print(d["udid"])
print(d["name"] + " (" + d["runtime"].split(".")[-1] + ")", file=sys.stderr)
') || { echo "no simulator" >&2; exit 1; }
export DEVICE=$udid

xcrun simctl boot "$udid" 2>/dev/null || echo "simctl boot: probably already booted; bootstatus decides"
xcrun simctl bootstatus "$udid" -b || { echo "simulator did not boot" >&2; exit 1; }

case "$variant" in
  nl|fr-en) ;;
  large-dark)
    xcrun simctl ui "$udid" appearance dark
    xcrun simctl ui "$udid" content_size extra-extra-large
    ;;
  *) echo "unknown variant $variant" >&2; exit 2 ;;
esac
case "$variant" in fr-en) langs="fr en" ;; *) langs="nl" ;; esac

xcrun simctl install "$udid" "$app" || { echo "install failed" >&2; exit 1; }

# The app's log lines (process name = the executable inside the .app).
exe=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "$app/Info.plist")
xcrun simctl spawn "$udid" log stream --level debug --style compact --predicate "process == \"$exe\"" > "$out/app-log.txt" 2>&1 &
log_pid=$!

for lang in $langs; do
  bash "$repo/mobile/.maestro/run-suite.sh" ios "$lang" "$out/maestro-$lang" || status=1
done

kill "$log_pid" 2>/dev/null
wait "$log_pid" 2>/dev/null
echo "app log: $(wc -l < "$out/app-log.txt") lines"

if ! python3 "$repo/.github/scripts/scan_logs_for_tokens.py" "$E2E_WORK/db/depiqo.sqlite3" "$out/app-log.txt"; then
  echo "Token scan failed" >&2
  status=1
fi
# Crash reports for the app, if any
find ~/Library/Logs/DiagnosticReports -name "${exe}*" -newer "$app/Info.plist" -exec cp {} "$out/" \; 2>/dev/null
if ls "$out"/"${exe}"*.ips >/dev/null 2>&1; then
  echo "The app crashed; crash report(s) in the artifact" >&2
  status=1
fi

exit $status
