#!/usr/bin/env bash
# The runtime release waits here until the data release of the same commit has
# succeeded, so new code never serves against a schema that is not published yet.
set -euo pipefail

: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}" "${GITHUB_SHA:?GITHUB_SHA is required}"
poll="${POLL_SECONDS:-15}"
# A push starts both workflows together, so the data run may not be listed yet: 12 polls of 15 s is about 3 minutes.
absent_left=12
# A few failed reads in a row are GitHub hiccups; more means the token or the request is wrong.
errors_left=5
runs="repos/$GITHUB_REPOSITORY/actions/workflows/data-release.yml/runs?head_sha=$GITHUB_SHA&per_page=20"
# The newest run of any event counts: a manual run after a failed push run replaces it.
newest='[.workflow_runs[] | select(.head_branch == "main")] | sort_by(.run_number) | last // empty
  | "\(.status) \(.conclusion // "none") \(.html_url)"'

seen=""
while true; do
  if ! run="$(gh api "$runs" | jq --raw-output "$newest")"; then
    errors_left=$((errors_left - 1))
    if ((errors_left == 0)); then
      printf 'Could not read the data release runs of %s.\n' "$GITHUB_SHA" >&2
      exit 1
    fi
  elif [[ -z "$run" ]]; then
    errors_left=5
    absent_left=$((absent_left - 1))
    if ((absent_left == 0)); then
      printf 'No data release run exists for %s: run the "Data release" workflow on main, then re-run this job.\n' "$GITHUB_SHA" >&2
      exit 1
    fi
  else
    errors_left=5
    read -r status conclusion url <<< "$run"
    if [[ "$status" == "completed" ]]; then
      printf 'Data release %s finished with conclusion %s.\n' "$url" "$conclusion"
      [[ "$conclusion" == "success" ]] && exit 0
      printf 'The runtime is not released: fix and re-run the data release, then re-run this job.\n' >&2
      exit 1
    fi
    if [[ "$run" != "$seen" ]]; then
      printf 'Waiting for data release %s (%s).\n' "$url" "$status"
      seen="$run"
    fi
  fi
  sleep "$poll"
done
