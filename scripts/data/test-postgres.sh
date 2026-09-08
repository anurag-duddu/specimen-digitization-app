#!/usr/bin/env bash
# Real local PostgreSQL is required: bundled PGlite cannot prove concurrent CAS.
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"
pg_bin="${POSTGRES_BIN:-/opt/homebrew/opt/postgresql@18/bin}"
dc_bin="${DATACONNECT_EMULATOR_BIN:-$HOME/.cache/firebase/emulators/dataconnect-emulator-3.2.0}"
pg_port="${SPECIMEN_TEST_PG_PORT:-5559}"
dc_port="${SPECIMEN_TEST_DC_PORT:-9509}"
[[ "$pg_port" =~ ^[0-9]+$ && "$dc_port" =~ ^[0-9]+$ ]]
[[ -x "$pg_bin/initdb" && -x "$dc_bin" ]]
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
start_connector() {
  "$dc_bin" dev -config_dir dataconnect -listen "$FIREBASE_DATACONNECT_EMULATOR_HOST" \
    -local_connection_string "postgresql://127.0.0.1:$pg_port/specimen-digitization-database?sslmode=disable" \
    > "$test_dir/connector.log" 2>&1 &
  dc_pid=$!
  node scripts/data/wait-local.mjs
}
start_connector
node scripts/data/connector-test.mjs
"$pg_bin/psql" -h 127.0.0.1 -p "$pg_port" -d specimen-digitization-database -v ON_ERROR_STOP=1 -f dataconnect/sql/paging-indexes.sql
"$pg_bin/psql" -h 127.0.0.1 -p "$pg_port" -d specimen-digitization-database -v ON_ERROR_STOP=1 -f dataconnect/sql/search-indexes.sql
PSQL_BIN="$pg_bin/psql" SPECIMEN_TEST_PG_PORT="$pg_port" node scripts/data/paging-test.mjs
PSQL_BIN="$pg_bin/psql" SPECIMEN_TEST_PG_PORT="$pg_port" node scripts/data/search-test.mjs
kill "$dc_pid"
wait "$dc_pid" || true
dc_pid=""
start_connector
node scripts/data/restart-test.mjs
index_count="$("$pg_bin/psql" -h 127.0.0.1 -p "$pg_port" -d specimen-digitization-database -Atc "SELECT count(*) FROM pg_index JOIN pg_class ON pg_class.oid = indexrelid WHERE relname IN ('specimen_text_cursor', 'auxiliary_text_cursor', 'specimen_search_cursor', 'snapshot_search_batch') AND indisvalid")"
[[ "$index_count" == "4" ]]
printf 'PASS supplemental keyset indexes remain valid after connector restart\n'
