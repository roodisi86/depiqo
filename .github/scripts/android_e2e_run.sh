#!/usr/bin/env bash
# Runs inside reactivecircus/android-emulator-runner (one line in `script:`, so this file holds the logic).
#
#   .github/scripts/android_e2e_run.sh <variant> <apk> <out-dir>
#
# variant: nl          suite in Dutch
#          large-dark  suite in Dutch with font scale 1.3 and dark mode
#          fr-en       suite in French, then again in English
# Captures logcat for the whole run (raw, for the token scan) and a copy filtered to the app (the artifact).
# Exit code: non-zero when a flow failed, the app crashed, or a token was found in the log.
set -uo pipefail

variant=${1:?variant}
apk=${2:?apk}
out=${3:?out dir}
repo=$(cd "$(dirname "$0")/../.." && pwd)
APP_ID=com.getdepiqo.app.dev
mkdir -p "$out"
out=$(cd "$out" && pwd)
status=0

adb wait-for-device
# Let the emulator settle, and keep system "isn't responding" dialogs (a slow CI emulator's launcher) from covering
# the app: one such dialog made a whole run fail at the first screen.
for i in $(seq 1 60); do [ "$(adb shell getprop sys.boot_completed | tr -d '\r')" = "1" ] && break; sleep 2; done
adb shell settings put global hide_error_dialogs 1 || true
adb shell settings put global window_animation_scale 0 || true
adb shell settings put global transition_animation_scale 0 || true
adb shell settings put global animator_duration_scale 0 || true
adb shell input keyevent 82 || true
adb shell am broadcast -a android.intent.action.CLOSE_SYSTEM_DIALOGS >/dev/null 2>&1 || true
sleep 15
adb shell getprop ro.build.version.release | sed 's/^/Android /'
adb install -r -g "$apk"
adb shell pm list packages | grep -q "package:$APP_ID" || { echo "APK did not install as $APP_ID" >&2; exit 1; }

case "$variant" in
  nl|fr-en) ;;
  large-dark)
    adb shell settings put system font_scale 1.3
    adb shell cmd uimode night yes
    sleep 3
    echo "font_scale=$(adb shell settings get system font_scale | tr -d '\r') night=$(adb shell cmd uimode night | tr -d '\r')"
    ;;
  *) echo "unknown variant $variant" >&2; exit 2 ;;
esac
case "$variant" in
  fr-en) langs="fr en" ;;
  *) langs="nl" ;;
esac

adb logcat -c
adb logcat -v threadtime > "$out/logcat-full.txt" 2>&1 &
logcat_pid=$!

for lang in $langs; do
  bash "$repo/mobile/.maestro/run-suite.sh" android "$lang" "$out/maestro-$lang" || status=1
done

kill "$logcat_pid" 2>/dev/null
wait "$logcat_pid" 2>/dev/null

# The app's own lines: JS console (ReactNativeJS), React Native, Expo modules, crashes, and anything naming the package.
# grep exits 1 when nothing matched (an empty copy is not an error); 2 is a real error and fails the run.
grep -E "ReactNativeJS|ReactNative|ReactHost|Expo|expo\.|AndroidRuntime|$APP_ID" "$out/logcat-full.txt" > "$out/logcat-app.txt" || [ $? -eq 1 ] || status=1
echo "logcat: $(wc -l < "$out/logcat-full.txt") lines, $(wc -l < "$out/logcat-app.txt") for the app"

if grep -q "FATAL EXCEPTION" "$out/logcat-full.txt" && grep -A3 "FATAL EXCEPTION" "$out/logcat-full.txt" | grep -q "$APP_ID"; then
  echo "The app crashed (FATAL EXCEPTION for $APP_ID); see logcat-app.txt" >&2
  status=1
fi

# No access, refresh or 2FA token may ever reach the device log (the full log, not only the filtered copy).
if ! python3 "$repo/.github/scripts/scan_logs_for_tokens.py" "$E2E_WORK/db/depiqo.sqlite3" "$out/logcat-full.txt" "$out/logcat-app.txt"; then
  echo "Token scan failed" >&2
  status=1
fi
# The full log stays out of the artifact: it holds the whole emulator, not only this app.
rm -f "$out/logcat-full.txt"

exit $status
