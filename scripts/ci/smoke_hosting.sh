#!/usr/bin/env bash
set -euo pipefail

readonly expected_repository="anurag-duddu/specimen-digitization-app"
site_url="${1:-https://specimen-digitization.web.app}"
expected_sha="${2:-}"
html_file="$(mktemp /tmp/specimen-hosting-index.XXXXXX)"
metadata_file="$(mktemp /tmp/specimen-hosting-metadata.XXXXXX)"

cleanup() {
  rm -f "$html_file" "$metadata_file"
}
trap cleanup EXIT HUP INT TERM

if [[ "$site_url" != "https://specimen-digitization.web.app" ]]; then
  printf 'Smoke test refused for unexpected site: %s\n' "$site_url" >&2
  exit 1
fi
if [[ ! "$expected_sha" =~ ^[0-9a-f]{40}$ ]]; then
  printf 'Usage: %s https://specimen-digitization.web.app EXPECTED_40_CHARACTER_SHA\n' "$0" >&2
  exit 1
fi

curl --fail --silent --show-error \
  --retry 8 --retry-all-errors --retry-delay 5 \
  --header 'Cache-Control: no-cache' \
  "$site_url/?sha=$expected_sha" > "$html_file"
grep --fixed-strings '<title>Specimen Digitization</title>' "$html_file" >/dev/null

curl --fail --silent --show-error \
  --retry 8 --retry-all-errors --retry-delay 5 \
  --header 'Cache-Control: no-cache' \
  "$site_url/deployment.json?sha=$expected_sha" > "$metadata_file"

deployed_repository="$(jq -r '.repository // empty' "$metadata_file")"
deployed_sha="$(jq -r '.commitSha // empty' "$metadata_file")"
[[ "$deployed_repository" == "$expected_repository" ]] || {
  printf 'Unexpected deployed repository marker: %s\n' "$deployed_repository" >&2
  exit 1
}
[[ "$deployed_sha" == "$expected_sha" ]] || {
  printf 'Deployed SHA %s does not match expected SHA %s.\n' "$deployed_sha" "$expected_sha" >&2
  exit 1
}

printf 'Production smoke passed for %s at %s.\n' "$expected_sha" "$site_url"
