#!/usr/bin/env bash
set -euo pipefail

readonly expected_repository="anurag-duddu/specimen-digitization-app"
site_url="${1:-https://specimen-digitization.web.app}"
expected_sha="${2:-}"

if [[ "$site_url" != "https://specimen-digitization.web.app" ]]; then
  printf 'Smoke test refused for unexpected site: %s\n' "$site_url" >&2
  exit 1
fi
if [[ ! "$expected_sha" =~ ^[0-9a-f]{40}$ ]]; then
  printf 'Usage: %s https://specimen-digitization.web.app EXPECTED_40_CHARACTER_SHA\n' "$0" >&2
  exit 1
fi

html_file="$(mktemp /tmp/specimen-hosting-index.XXXXXX)"
metadata_file="$(mktemp /tmp/specimen-hosting-metadata.XXXXXX)"
trap 'rm -f "$html_file" "$metadata_file"' EXIT HUP INT TERM

# One budget includes both documents, network failures and semantic propagation.
# Reject a reversing clock instead of extending authority to keep waiting.
clock_previous="$(date +%s)"
[[ "$clock_previous" =~ ^[0-9]{1,12}$ ]] || { printf 'Invalid smoke clock.\n' >&2; exit 1; }
clock_previous=$((10#$clock_previous))
readonly deadline=$((clock_previous + 300))
remaining=300
check_budget() {
  local clock_now
  clock_now="$(date +%s)"
  if [[ ! "$clock_now" =~ ^[0-9]{1,12}$ ]] || ((10#$clock_now < clock_previous)); then
    printf 'Invalid or reversing smoke clock.\n' >&2
    exit 1
  fi
  clock_previous=$((10#$clock_now))
  remaining=$((deadline - clock_previous))
  if ((remaining <= 0)); then
    printf 'Public verification deadline expired before the expected release qualified.\n' >&2
    exit 1
  fi
}

retry_pause() {
  check_budget
  local delay=5
  ((remaining >= delay)) || delay="$remaining"
  sleep "$delay"
}

fetch() {
  local url="$1" target="$2" status result=0 request_timeout connect_timeout
  check_budget
  request_timeout=$((remaining < 15 ? remaining : 15))
  connect_timeout=$((request_timeout < 5 ? request_timeout : 5))
  # Disable curlrc, redirects and internal retries. This loop owns every retry,
  # so no final curl retry can outlive the shared verification deadline.
  status="$(curl --disable --fail --silent --show-error \
    --proto '=https' --retry 0 --connect-timeout "$connect_timeout" --max-time "$request_timeout" \
    --max-filesize 1048576 --header 'Cache-Control: no-cache' \
    --output "$target" --write-out '%{http_code}' "$url")" || result=$?
  check_budget
  if [[ "$status" == "200" && "$result" == "0" ]]; then
    return 0
  fi
  if [[ "$status" =~ ^(408|429|5[0-9]{2})$ ]] \
    || [[ "$status" =~ ^(000|200)$ && "$result" =~ ^(5|6|7|16|18|28|35|52|55|56|92)$ ]]; then
    printf 'Transient public read failed; waiting within the existing deadline.\n' >&2
    return 1
  fi
  printf 'Public read failed with an unexpected HTTP or curl result.\n' >&2
  exit 1
}

# The fixed pass limit still terminates if the clock stops advancing entirely.
for ((smoke_attempt=1; smoke_attempt<=60; smoke_attempt++)); do
  # Recheck HTML on every pass; the qualifying marker is the final public read.
  if ! fetch "$site_url/?sha=$expected_sha" "$html_file"; then
    retry_pause
    continue
  fi
  if ! grep --extended-regexp --ignore-case '^[[:space:]]*<!doctype html>' "$html_file" >/dev/null \
    || ! grep --extended-regexp --ignore-case '<html([[:space:]>])' "$html_file" >/dev/null \
    || ! grep --fixed-strings '<title>Specimen Digitization</title>' "$html_file" >/dev/null; then
    printf 'Public response is not the expected application HTML/title.\n' >&2
    exit 1
  fi
  if ! fetch "$site_url/deployment.json?sha=$expected_sha" "$metadata_file"; then
    retry_pause
    continue
  fi

  # Streaming retains duplicate keys and multiple documents; ordinary parsing
  # would silently accept the last duplicate value. Only the emitted v1 shape
  # can qualify as current or enter the same-repository stale-marker wait.
  if ! deployed_sha="$(jq --exit-status --raw-output --null-input --stream --arg repository "$expected_repository" '
    [inputs] as $events
    | if ($events | length) != 7 or ($events | map(select(length == 1)) | length) != 1
      then error("one complete marker object required") else $events end
    | map(select(length == 2)) as $pairs
    | if ($pairs | map(.[0]) | sort) != [["builtAt"], ["commitSha"], ["repository"], ["runAttempt"], ["runId"], ["schemaVersion"]]
      then error("invalid marker shape") else $pairs end
    | map({key: .[0][0], value: .[1]}) | from_entries
    | . as $marker
    | if .schemaVersion == 1 and .repository == $repository
      and (.commitSha | type == "string" and test("^[0-9a-f]{40}$"))
      and (.runId | type == "string" and test("^[1-9][0-9]*$"))
      and (.runAttempt | type == "string" and test("^[1-9][0-9]*$"))
      and (.builtAt | type == "string")
      and ((.builtAt | fromdateiso8601 | strftime("%Y-%m-%dT%H:%M:%SZ")) == $marker.builtAt)
      then .commitSha else error("invalid marker identity or fields") end
    ' "$metadata_file" 2>/dev/null)"; then
    printf 'Malformed or foreign deployment marker; verification stopped.\n' >&2
    exit 1
  fi
  check_budget
  if [[ "$deployed_sha" == "$expected_sha" ]]; then
    printf 'Production smoke passed for %s at %s.\n' "$expected_sha" "$site_url"
    exit 0
  fi
  printf 'Same-repository marker is still %s; waiting for expected SHA %s.\n' "$deployed_sha" "$expected_sha" >&2
  retry_pause
done
check_budget
printf 'Public verification attempt limit exhausted before the expected release qualified.\n' >&2
exit 1
