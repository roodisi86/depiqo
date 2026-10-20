#!/usr/bin/env bash
# Publish a CI output folder to the orphan branch "ci-results", so results can be read with plain git
# (no access to the Actions log or artifact download hosts needed).
#   publish_results.sh <label> <folder>
# Writes to ci-results:<label>/<run_id>-<attempt>/ and replaces ci-results:<label>/latest/.
# Never fails the job: publishing is best effort and runs after the real steps.
set -u
label="$1"; src="$2"
if [ ! -d "$src" ]; then echo "publish_results: $src does not exist, nothing to publish"; exit 0; fi
src="$(cd "$src" && pwd)"
run="${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}"
repo_url="https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
work="$(mktemp -d)"
cd "$work" || exit 0
git init -q
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git remote add origin "$repo_url"
for attempt in 1 2 3 4 5 6; do
  if git fetch -q --depth 1 origin ci-results 2>/dev/null; then
    git checkout -q -B ci-results FETCH_HEAD
  else
    git checkout -q --orphan ci-results
    git rm -rq --cached . 2>/dev/null || true
  fi
  rm -rf "$label/latest" "$label/$run"
  mkdir -p "$label/latest" "$label/$run"
  cp -R "$src"/. "$label/latest/"
  cp -R "$src"/. "$label/$run/"
  {
    echo "run_id=${GITHUB_RUN_ID:-}"
    echo "attempt=${GITHUB_RUN_ATTEMPT:-}"
    echo "sha=${GITHUB_SHA:-}"
    echo "workflow=${GITHUB_WORKFLOW:-}"
    echo "job=${GITHUB_JOB:-}"
    echo "date=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } > "$label/latest/_run.txt"
  # No app binaries or big files in git: those stay in the Actions artifacts.
  find "$label" -type f \( -name '*.apk' -o -name '*.aab' -o -name '*.ipa' -o -name '*.zip' -o -size +8M \) -delete
  cp "$label/latest/_run.txt" "$label/$run/_run.txt"
  # Keep the branch small: only the 5 newest runs per label.
  ls -1d "$label"/*/ 2>/dev/null | grep -v '/latest/$' | sort -t/ -k2 -r | tail -n +6 | xargs -r rm -rf
  git add -A "$label"
  git commit -qm "ci-results: $label run $run" || { echo "nothing new to publish"; exit 0; }
  if git push -q origin ci-results 2>/dev/null; then
    echo "Published $src to ci-results:$label/latest"
    exit 0
  fi
  echo "push raced with another job, retry $attempt"
  sleep $((attempt * 3))
done
echo "::warning::Could not publish results to ci-results after retries"
exit 0
