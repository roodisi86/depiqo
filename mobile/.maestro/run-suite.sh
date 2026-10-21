#!/usr/bin/env bash
# Runs every Maestro flow in .maestro/flows once, in order, against the installed "Depiqo Dev" app.
#
#   mobile/.maestro/run-suite.sh <android|ios> <nl|fr|en> <out-dir>
#
# Needs: maestro on PATH, node, python3, a running CI backend (.github/scripts/start_backend.sh) and
#   E2E_WORK  the backend's work dir (invite_token, totp_secret, db/depiqo.sqlite3)
#   DEVICE    iOS only: the simulator UDID
# Writes to <out-dir>: junit/<flow>.xml, debug/<flow>/ (Maestro's own logs and failure screenshots),
# screenshots/*.png (takeScreenshot), maestro-env.txt (the UI strings used) and results.txt.
# Every flow runs even when an earlier one failed; the exit code is non-zero when any flow failed.
# Written for bash 3.2 too (macOS): empty arrays are expanded with ${a[@]+"${a[@]}"}.
set -uo pipefail

platform=${1:?android or ios}
lang=${2:?nl, fr or en}
out=${3:?output dir}
here=$(cd "$(dirname "$0")" && pwd)
mobile=$(dirname "$here")
repo=$(dirname "$mobile")
: "${E2E_WORK:?E2E_WORK must point at the backend work dir}"
APP_ID=com.getdepiqo.app.dev

case "$platform" in android|ios) ;; *) echo "unknown platform $platform" >&2; exit 2 ;; esac
mkdir -p "$out/junit" "$out/debug" "$out/screenshots"
out=$(cd "$out" && pwd)

node "$mobile/scripts/maestro-env.mjs" "$lang" > "$out/maestro-env.txt" || { echo "maestro-env failed" >&2; exit 2; }
envargs=(-e "PASSWORD=Depiqo-demo-2026" -e "PLATFORM=$platform")
while IFS= read -r line; do
  [ -n "$line" ] && envargs+=(-e "$line")
done < "$out/maestro-env.txt"

device_args=()
if [ "$platform" = ios ]; then
  : "${DEVICE:?DEVICE (simulator UDID) is required on iOS}"
  device_args=(--device "$DEVICE")
fi

run_flow() {  # <name> <flow file> [extra maestro args...]
  local name=$1 file=$2
  shift 2
  echo "::group::maestro $name ($platform, $lang)"
  ( cd "$out/screenshots" && maestro ${device_args[@]+"${device_args[@]}"} test \
      --format junit --output "$out/junit/$name.xml" \
      --debug-output "$out/debug/$name" \
      "${envargs[@]}" ${1+"$@"} "$file" )
  local status=$?
  if [ $status -ne 0 ]; then
    # Save what was on screen, as the accessibility tree, to see why an element was not found.
    mkdir -p "$out/debug/$name"
    maestro ${device_args[@]+"${device_args[@]}"} hierarchy > "$out/debug/$name/hierarchy-on-failure.json" 2>/dev/null || true
  fi
  echo "::endgroup::"
  return $status
}

open_invite_link() {
  local token
  token=$(cat "$E2E_WORK/invite_token")
  if [ "$platform" = android ]; then
    adb shell am start -W -a android.intent.action.VIEW -d "depiqo://t/$token" "$APP_ID" > /dev/null
  else
    xcrun simctl openurl "$DEVICE" "depiqo://t/$token"
  fi
}

# Start Maestro's driver once before the first flow, so a slow first start does not count against a flow.
maestro ${device_args[@]+"${device_args[@]}"} hierarchy > /dev/null 2>&1 || true

failed=()
: > "$out/results.txt"
for file in "$here"/flows/*.yaml; do
  name=$(basename "$file" .yaml)
  extra=()
  case "$name" in
    *2fa*)
      # The flow fetches the code when it types it (scripts/totp.js), from this helper on 127.0.0.1:5055.
      if [ -z "${totp_pid:-}" ]; then
        python3 "$repo/.github/scripts/totp_server.py" "$E2E_WORK/totp_secret" &
        totp_pid=$!
        sleep 1
      fi
      ;;
    *invite-deeplink*)
      if ! run_flow "$name-reset" "$here/subflows/reset-app.yaml"; then
        failed+=("$name (reset)")
        echo "$name FAILED (reset)" >> "$out/results.txt"
        continue
      fi
      open_invite_link || { failed+=("$name (open link)"); echo "$name FAILED (open link)" >> "$out/results.txt"; continue; }
      ;;
  esac
  if run_flow "$name" "$file" ${extra[@]+"${extra[@]}"}; then
    echo "$name ok" >> "$out/results.txt"
  elif [ "$name" != "${name%invite-deeplink}" ]; then
    failed+=("$name")
    echo "$name FAILED" >> "$out/results.txt"
  elif mv "$out/junit/$name.xml" "$out/junit/$name.attempt1.xml" 2>/dev/null; run_flow "$name" "$file" ${extra[@]+"${extra[@]}"}; then
    # One retry for a flow that failed once (a cold CI simulator sometimes fails to start Maestro's driver).
    # The report keeps both attempts; results.txt says it passed on the second try.
    echo "$name ok (tweede poging)" >> "$out/results.txt"
  else
    failed+=("$name")
    echo "$name FAILED" >> "$out/results.txt"
  fi
done

# Maestro writes takeScreenshot files to the working directory; collect any it put elsewhere too.
find "$out/debug" -name '*.png' | while IFS= read -r png; do
  [ -e "$out/screenshots/$(basename "$png")" ] || cp "$png" "$out/screenshots/"
done

[ -n "${totp_pid:-}" ] && kill "$totp_pid" 2>/dev/null

# Artifact uploads refuse some characters that Maestro puts in failure screenshot names (":" and others).
find "$out" -name '*[:<>|*?"]*' -type f | while IFS= read -r f; do
  d=$(dirname "$f"); b=$(basename "$f" | tr ':<>|*?"' '-------')
  mv "$f" "$d/$b"
done

echo "---- $platform $lang"
cat "$out/results.txt"
if [ ${#failed[@]} -gt 0 ]; then
  echo "FAILED flows ($platform, $lang): ${failed[*]}" >&2
  exit 1
fi
