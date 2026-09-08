#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"
storage_port="${SPECIMEN_TEST_STORAGE_PORT:-9299}"
[[ "$storage_port" =~ ^[0-9]+$ && "$storage_port" -gt 1024 && "$storage_port" -lt 65536 ]] || exit 1
[[ "$storage_port" != 3000 && "$storage_port" != 8000 ]] || exit 1
test_dir="$(mktemp -d "${TMPDIR:-/tmp}/specimen-storage-test.XXXXXX")"
node - "$repo_root" "$storage_port" "$test_dir" <<'JS'
const fs = require('node:fs');
const [root,port,destination] = process.argv.slice(2);
fs.writeFileSync(`${destination}/firebase.json`, JSON.stringify({
 storage:{rules:`${root}/storage.rules`},
 emulators:{storage:{host:'127.0.0.1',port:Number(port)},ui:{enabled:false},singleProjectMode:true}
}));
JS
# Caller selects Java21+ using task-scoped JAVA_HOME/PATH, never global config.
firebase emulators:exec --only storage --project demo-specimen-data \
  --config "$test_dir/firebase.json" 'node scripts/data/storage-test.mjs'
printf 'Storage emulator configuration retained at %s\n' "$test_dir"
