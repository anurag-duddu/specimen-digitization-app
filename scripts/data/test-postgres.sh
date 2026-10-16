#!/usr/bin/env bash
# Real PostgreSQL is required: bundled PGlite cannot prove concurrent CAS.
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
exec node "$repo_root/scripts/data/engine-contract-reporter.mjs" sql "$@"
