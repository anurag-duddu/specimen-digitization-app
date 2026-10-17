#!/usr/bin/env bash
# Real PostgreSQL is required: bundled PGlite cannot prove concurrent CAS.
set -euo pipefail
# Reject configuration before starting Node, which creates output and cleanup state.
if (( $# )); then
  if (( $# != 2 )) || [[ $1 != --python-contract-output || $2 == --* ]]; then
    printf '%s\n' 'unknown argument or missing value' >&2
    exit 2
  fi
fi
ports=("${SPECIMEN_TEST_PG_PORT:-5559}" "${SPECIMEN_TEST_DC_PORT:-9509}" "${SPECIMEN_TEST_STORAGE_PORT:-9299}")
for index in "${!ports[@]}"; do
  port=${ports[index]}
  # Normalize leading zeroes before bounded decimal arithmetic (never octal).
  while [[ $port == 0* && ${#port} -gt 1 ]]; do port=${port#0}; done
  if [[ ! $port =~ ^[0-9]+$ || ${#port} -gt 5 ]]; then
    printf '%s\n' 'invalid ports' >&2
    exit 2
  fi
  port=$((10#$port))
  if (( port <= 1024 || port >= 65536 || port == 3000 || port == 8000 )); then
    printf '%s\n' 'invalid ports' >&2
    exit 2
  fi
  ports[index]=$port
done
if (( ports[0] == ports[1] || ports[0] == ports[2] || ports[1] == ports[2] )); then
  printf '%s\n' 'invalid ports: duplicate values' >&2
  exit 2
fi
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
exec node "$repo_root/scripts/data/engine-contract-reporter.mjs" sql "$@"
