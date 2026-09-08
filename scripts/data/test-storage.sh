#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"
# Caller selects Java21+ using task-scoped JAVA_HOME/PATH, never global config.
firebase emulators:exec --only storage --project demo-specimen-data \
  --config firebase.data-emulator.json 'node scripts/data/storage-test.mjs'
