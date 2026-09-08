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
[[ -n "${GOOGLE_GHA_CREDS_PATH:-}" && -f "${GOOGLE_GHA_CREDS_PATH:-}" ]] || fail 'keyless Google credential file is missing'
[[ -d "$artifact_dir" ]] || fail 'tested Hosting artifact is missing'
[[ -f "$metadata_file" ]] || fail 'deployment metadata is missing'

artifact_sha="$(jq -r '.commitSha // empty' "$metadata_file")"
[[ "$artifact_sha" == "$GITHUB_SHA" ]] || fail 'artifact SHA does not match the workflow SHA'

npx --yes firebase-tools@15.8.0 deploy \
  --only hosting \
  --project "$expected_project" \
  --non-interactive \
  --message "GitHub Actions ${GITHUB_SHA}"
