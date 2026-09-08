#!/usr/bin/env bash
set -euo pipefail

readonly expected_repository="anurag-duddu/specimen-digitization-app"
target_dir="${1:-}"

if [[ "${GITHUB_ACTIONS:-}" != "true" ]]; then
  printf 'Deployment metadata may be generated only by GitHub Actions.\n' >&2
  exit 1
fi
if [[ "${GITHUB_REPOSITORY:-}" != "$expected_repository" ]]; then
  printf 'Unexpected GitHub repository: %s\n' "${GITHUB_REPOSITORY:-unset}" >&2
  exit 1
fi
if [[ ! "${GITHUB_SHA:-}" =~ ^[0-9a-f]{40}$ ]]; then
  printf 'GITHUB_SHA is missing or invalid.\n' >&2
  exit 1
fi
if [[ -z "$target_dir" || ! -d "$target_dir" ]]; then
  printf 'Usage: %s EXISTING_WEB_BUILD_DIRECTORY\n' "$0" >&2
  exit 1
fi

jq -n \
  --arg repository "$GITHUB_REPOSITORY" \
  --arg sha "$GITHUB_SHA" \
  --arg run_id "${GITHUB_RUN_ID:-unknown}" \
  --arg run_attempt "${GITHUB_RUN_ATTEMPT:-unknown}" \
  --arg built_at "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
  '{schemaVersion: 1, repository: $repository, commitSha: $sha, runId: $run_id, runAttempt: $run_attempt, builtAt: $built_at}' \
  > "$target_dir/deployment.json"
