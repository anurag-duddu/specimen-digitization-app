#!/usr/bin/env bash
# Disposable real PostgreSQL + SQL Connect; no system service or cloud endpoint.
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"
pg_bin="${POSTGRES_BIN:-/opt/homebrew/opt/postgresql@18/bin}"
dc_bin="${DATACONNECT_EMULATOR_BIN:-$HOME/.cache/firebase/emulators/dataconnect-emulator-3.2.0}"
pg_port="${SPECIMEN_TEST_PG_PORT:-5549}"
dc_port="${SPECIMEN_TEST_DC_PORT:-9499}"
[[ "$pg_port" =~ ^[0-9]+$ && "$dc_port" =~ ^[0-9]+$ ]]
[[ -x "$pg_bin/initdb" && -x "$dc_bin" ]]
test_dir="$(mktemp -d "${TMPDIR:-/tmp}/specimen-data-serve.XXXXXX")"
dc_pid=""
cleanup() {
  if [[ -n "$dc_pid" ]]; then kill "$dc_pid" 2>/dev/null || true; wait "$dc_pid" 2>/dev/null || true; fi
  "$pg_bin/pg_ctl" -D "$test_dir/cluster" -m fast stop >/dev/null 2>&1 || true
  printf 'Stopped owned local processes. Synthetic cluster/logs retained: %s\n' "$test_dir"
}
trap cleanup EXIT
trap 'exit 130' INT TERM
"$pg_bin/initdb" -D "$test_dir/cluster" -A trust --no-locale > "$test_dir/init.log"
"$pg_bin/pg_ctl" -D "$test_dir/cluster" -l "$test_dir/postgres.log" -o "-h 127.0.0.1 -p $pg_port -k $test_dir" start
"$pg_bin/createdb" -h 127.0.0.1 -p "$pg_port" specimen-digitization-database
export FIREBASE_DATACONNECT_EMULATOR_HOST="127.0.0.1:$dc_port"
"$dc_bin" dev -config_dir dataconnect -listen "$FIREBASE_DATACONNECT_EMULATOR_HOST" \
  -local_connection_string "postgresql://127.0.0.1:$pg_port/specimen-digitization-database?sslmode=disable" \
  > "$test_dir/connector.log" 2>&1 &
dc_pid=$!
node scripts/data/wait-local.mjs
node scripts/data/seed-integration.mjs
"$pg_bin/psql" -h 127.0.0.1 -p "$pg_port" -d specimen-digitization-database -v ON_ERROR_STOP=1 -f dataconnect/sql/paging-indexes.sql
"$pg_bin/psql" -h 127.0.0.1 -p "$pg_port" -d specimen-digitization-database -v ON_ERROR_STOP=1 -f dataconnect/sql/search-indexes.sql
printf 'Synthetic SQL Connect ready at %s; Ctrl-C stops only this cluster.\n' "$FIREBASE_DATACONNECT_EMULATOR_HOST"
wait "$dc_pid"
