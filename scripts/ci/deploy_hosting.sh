#!/usr/bin/env bash
set -euo pipefail

readonly expected_repository="anurag-duddu/specimen-digitization-app"
readonly expected_ref="refs/heads/main"
readonly expected_workflow_ref="anurag-duddu/specimen-digitization-app/.github/workflows/ci-cd.yml@refs/heads/main"
readonly expected_environment="production"
readonly expected_project="specimen-digitization"
readonly artifact_dir="apps/specimen_digitization/build/web"
readonly metadata_file="$artifact_dir/deployment.json"

fail() {
  printf 'Production deploy refused: %s\n' "$1" >&2
  exit 1
}

[[ "${GITHUB_ACTIONS:-}" == "true" ]] || fail 'not running in GitHub Actions'
[[ "${GITHUB_EVENT_NAME:-}" == "push" ]] || fail 'event is not push'
[[ "${GITHUB_REPOSITORY:-}" == "$expected_repository" ]] || fail 'repository is not approved'
[[ "${GITHUB_REF:-}" == "$expected_ref" ]] || fail 'ref is not main'
[[ "${GITHUB_WORKFLOW_REF:-}" == "$expected_workflow_ref" ]] || fail 'workflow identity is not approved'
[[ "${DEPLOYMENT_ENVIRONMENT:-}" == "$expected_environment" ]] || fail 'environment is not production'
[[ "${GITHUB_SHA:-}" =~ ^[0-9a-f]{40}$ ]] || fail 'commit SHA is missing or invalid'
[[ "${GITHUB_RUN_ID:-}" =~ ^[1-9][0-9]*$ ]] || fail 'workflow run ID is missing or invalid'
[[ "${GITHUB_RUN_ATTEMPT:-}" =~ ^[1-9][0-9]*$ ]] || fail 'workflow run attempt is missing or invalid'
[[ -n "${GOOGLE_GHA_CREDS_PATH:-}" && -f "${GOOGLE_GHA_CREDS_PATH:-}" ]] || fail 'keyless Google credential file is missing'
[[ -d "$artifact_dir" ]] || fail 'tested Hosting artifact is missing'
[[ -f "$metadata_file" ]] || fail 'deployment metadata is missing'

# Streaming rejects duplicate fields and multiple documents before any last-key
# normalization. The artifact must come from this exact protected run attempt.
jq --exit-status --null-input --stream \
  --arg repository "$expected_repository" --arg sha "$GITHUB_SHA" \
  --arg run_id "$GITHUB_RUN_ID" --arg run_attempt "$GITHUB_RUN_ATTEMPT" '
  [inputs] as $events
  | if ($events | length) != 7 or ($events | map(select(length == 1)) | length) != 1
    then error("one complete marker object required") else $events end
  | map(select(length == 2)) as $pairs
  | if ($pairs | map(.[0]) | sort) != [["builtAt"], ["commitSha"], ["repository"], ["runAttempt"], ["runId"], ["schemaVersion"]]
    then error("invalid marker shape") else $pairs end
  | map({key: .[0][0], value: .[1]}) | from_entries
  | . as $marker
  | if .schemaVersion == 1 and .repository == $repository
    and .commitSha == $sha and .runId == $run_id and .runAttempt == $run_attempt
    and (.builtAt | type == "string")
    and ((.builtAt | fromdateiso8601 | strftime("%Y-%m-%dT%H:%M:%SZ")) == $marker.builtAt)
    then true else error("invalid marker identity or fields") end
  ' "$metadata_file" >/dev/null 2>&1 \
  || fail 'artifact metadata does not match the exact workflow repository, SHA, run and attempt'

npx --yes firebase-tools@15.8.0 deploy \
  --only hosting \
  --project "$expected_project" \
  --non-interactive \
  --message "GitHub Actions ${GITHUB_SHA}"
