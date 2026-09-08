#!/usr/bin/env bash
# Real local PostgreSQL is required: bundled PGlite cannot prove concurrent CAS.
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"
pg_bin="${POSTGRES_BIN:-/opt/homebrew/opt/postgresql@18/bin}"
dc_bin="${DATACONNECT_EMULATOR_BIN:-$HOME/.cache/firebase/emulators/dataconnect-emulator-3.2.0}"
pg_port="${SPECIMEN_TEST_PG_PORT:-5559}"
dc_port="${SPECIMEN_TEST_DC_PORT:-9509}"
[[ "$pg_port" =~ ^[0-9]+$ && "$dc_port" =~ ^[0-9]+$ ]] || exit 1
[[ "$pg_port" != 3000 && "$pg_port" != 8000 && "$dc_port" != 3000 && "$dc_port" != 8000 ]] || exit 1
[[ "$pg_port" != "$dc_port" ]] || exit 1
[[ -x "$pg_bin/initdb" && -x "$dc_bin" ]] || exit 1
node --input-type=module - "$pg_port" "$dc_port" <<'JS'
import net from 'node:net';
for (const port of process.argv.slice(2).map(Number)) {
  const server = net.createServer();
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(port, '127.0.0.1', resolve);
  });
  await new Promise(resolve => server.close(resolve));
}
JS
test_dir="$(mktemp -d "${TMPDIR:-/tmp}/specimen-data-test.XXXXXX")"
dc_pid=""
cleanup() {
  if [[ -n "$dc_pid" ]]; then kill "$dc_pid" 2>/dev/null || true; wait "$dc_pid" 2>/dev/null || true; fi
  "$pg_bin/pg_ctl" -D "$test_dir/cluster" -m fast stop >/dev/null 2>&1 || true
  printf 'Local synthetic test logs retained at %s\n' "$test_dir"
}
trap cleanup EXIT
"$dc_bin" build -config_dir dataconnect > "$test_dir/compile.json"
node -e 'const r=require(process.argv[1]); if(r.errors?.length) { console.error(r.errors); process.exit(1); }' "$test_dir/compile.json"
"$pg_bin/initdb" -D "$test_dir/cluster" -A trust --no-locale > "$test_dir/init.log"
"$pg_bin/pg_ctl" -D "$test_dir/cluster" -l "$test_dir/postgres.log" -o "-h 127.0.0.1 -p $pg_port -k $test_dir" start
"$pg_bin/createdb" -h 127.0.0.1 -p "$pg_port" specimen-digitization-database
export FIREBASE_DATACONNECT_EMULATOR_HOST="127.0.0.1:$dc_port"
export DATA_RESTART_PROOF="$test_dir/restart.json"
export DATA_TEST_DIR="$test_dir"
export DATA_TEST_EMULATOR_BIN="$dc_bin"
export POSTGRES_BIN="$pg_bin" SPECIMEN_TEST_PG_PORT="$pg_port"
database=specimen-digitization-database
start_connector() {
  "$dc_bin" dev -config_dir dataconnect -listen "$FIREBASE_DATACONNECT_EMULATOR_HOST" \
    -local_connection_string "postgresql://127.0.0.1:$pg_port/$database?sslmode=disable" \
    >> "$test_dir/connector-$database.log" 2>&1 &
  dc_pid=$!
  node scripts/data/wait-local.mjs
}
apply_supplemental_indexes() {
  "$pg_bin/psql" -h 127.0.0.1 -p "$pg_port" -d "$database" -v ON_ERROR_STOP=1 -f dataconnect/sql/paging-indexes.sql
  "$pg_bin/psql" -h 127.0.0.1 -p "$pg_port" -d "$database" -v ON_ERROR_STOP=1 -f dataconnect/sql/search-indexes.sql
}
start_connector
node scripts/data/connector-test.mjs
node scripts/data/bootstrap-test.mjs
apply_supplemental_indexes
PSQL_BIN="$pg_bin/psql" SPECIMEN_TEST_PG_PORT="$pg_port" node scripts/data/paging-test.mjs
PSQL_BIN="$pg_bin/psql" SPECIMEN_TEST_PG_PORT="$pg_port" node scripts/data/search-test.mjs
PSQL_BIN="$pg_bin/psql" SPECIMEN_TEST_PG_PORT="$pg_port" node scripts/data/checksum-test.mjs
kill "$dc_pid"
wait "$dc_pid" || true
dc_pid=""
printf 'INFO all synthetic application writers quiesced during schema reconciliation and index repair\n'
start_connector
index_count="$("$pg_bin/psql" -h 127.0.0.1 -p "$pg_port" -d specimen-digitization-database -Atc "SELECT count(*) FROM pg_index JOIN pg_class ON pg_class.oid = indexrelid WHERE relname IN ('specimen_text_cursor', 'auxiliary_text_cursor', 'specimen_search_cursor', 'snapshot_search_batch') AND indisvalid")"
printf '{"validSupplementalIndexesAfterEmulatorStartup":%s,"requiredPostSchemaPhase":"paging-indexes.sql + search-indexes.sql"}\n' "$index_count" > "$test_dir/source-reconciliation.json"
if [[ "$index_count" != "4" ]]; then
  printf 'OBSERVED emulator reconciliation removed supplemental indexes; explicit post-schema DDL reapplied\n'
fi
# Emulator reconciliation is not a production preservation guarantee. This
# explicit post-schema phase is required by the separate data rollout contract.
apply_supplemental_indexes
node scripts/data/restart-test.mjs
kill "$dc_pid"
wait "$dc_pid" || true
dc_pid=""
node scripts/data/backup-restore-test.mjs restore
database=specimen-digitization-restored
for restart_round in 1 2; do
  printf 'INFO restored connector restart and explicit post-schema phase round %s\n' "$restart_round"
  start_connector
  node scripts/data/backup-restore-test.mjs reconcile
  apply_supplemental_indexes
  node scripts/data/restart-test.mjs
  node scripts/data/backup-restore-test.mjs verify
  # An immediate repeat must preserve every definition and record exactly.
  apply_supplemental_indexes
  node scripts/data/backup-restore-test.mjs verify
  kill "$dc_pid"
  wait "$dc_pid" || true
  dc_pid=""
done
printf 'PASS two restored restarts, repeatable explicit index repair and idempotent DDL with writers quiesced\n'
