#!/usr/bin/env bash
# Smoke the public API after a release: it serves this commit, it is ready, and
# a request without Google sign-in reaches the application.
# Usage: smoke_api.sh [URL]   (or SMOKE_URL=...; either one skips the gcloud lookup, for a local server)
set -euo pipefail

[[ "${GITHUB_SHA:-}" =~ ^[0-9a-f]{40}$ ]] || { printf 'GITHUB_SHA must be the released commit.\n' >&2; exit 1; }
poll="${POLL_SECONDS:-10}"
# One budget for all three checks: 18 tries of 10 s is about 3 minutes.
tries_left=18
url="${1:-${SMOKE_URL:-}}"
if [[ -z "$url" ]]; then
  url="$(gcloud run services describe specimen-api --region us-east4 --project specimen-digitization --format='value(status.url)')"
  [[ "$url" =~ ^https://[a-z0-9.-]+\.run\.app$ ]] || { printf 'Unexpected API URL: %s\n' "$url" >&2; exit 1; }
fi
body="$(mktemp "${TMPDIR:-/tmp}/specimen-api-smoke.XXXXXX")"
trap 'rm -f "$body"' EXIT

version_ok() {
  [[ "$status" == "200" ]] \
    && jq --exit-status --arg sha "$GITHUB_SHA" '.source_sha == $sha and .mode == "production"' "$body" >/dev/null 2>&1
}
ready_ok() { [[ "$status" == "200" ]] && jq --exit-status '.status == "ready"' "$body" >/dev/null 2>&1; }
# Exactly 401 is the application refusing a request without a bearer identity. A 403 comes from
# Google in front of the service, which means the public invoker binding is missing.
session_ok() { [[ "$status" == "401" ]]; }

# A new revision, a first public binding and the readiness probes all settle within minutes, so each
# check retries inside the shared budget and reports the last answer when the budget is spent.
check() {
  local path="$1" accept="$2"
  while true; do
    : > "$body"
    status="$(curl --silent --show-error --max-time 30 --output "$body" --write-out '%{http_code}' "$url$path")" || true
    if "$accept"; then
      printf '%s answered %s as expected.\n' "$path" "$status"
      return 0
    fi
    tries_left=$((tries_left - 1))
    ((tries_left > 0)) || break
    sleep "$poll"
  done
  printf '%s failed with HTTP %s; the last body was:\n' "$path" "$status" >&2
  head -c 2000 "$body" >&2
  printf '\n' >&2
  if [[ "$status" == "403" ]]; then
    printf 'public access is not set: the owner runs scripts/ops/owner_setup.sh once\n' >&2
  fi
  exit 1
}

check /version version_ok
check /health/ready ready_ok
check /v1/session session_ok
printf 'API smoke passed for %s at %s.\n' "$GITHUB_SHA" "$url"
