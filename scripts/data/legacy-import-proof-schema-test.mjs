// Local native physical schema probe; read-only, no proof or authority rows.
// SOURCE UNRUN. This is not authenticated production or paid-worker acceptance.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';

const psql = process.env.PSQL_BIN;
const port = process.env.SPECIMEN_TEST_PG_PORT;
assert.ok(psql, 'the isolated PostgreSQL harness must supply PSQL_BIN');
assert.match(port || '', /^\d+$/);
assert.ok(Number(port) >= 1024 && Number(port) <= 65535);
assert.ok(![3000, 8000].includes(Number(port)), 'an isolated local test port is required');

// Read only system catalogs. No SELECT reads, creates or imports proof history.
const sql = `BEGIN TRANSACTION READ ONLY;
SELECT json_build_object(
  'schema', n.nspname,
  'table', c.relname,
  'kind', c.relkind,
  'columns', (SELECT json_agg(json_build_object('name', a.attname, 'not_null', a.attnotnull)
      ORDER BY a.attnum) FROM pg_attribute a WHERE a.attrelid=c.oid
      AND a.attnum>0 AND NOT a.attisdropped),
  'primary_key', (SELECT json_agg(a.attname ORDER BY k.ordinality)
      FROM pg_constraint p CROSS JOIN LATERAL unnest(p.conkey) WITH ORDINALITY k(attnum, ordinality)
      JOIN pg_attribute a ON a.attrelid=p.conrelid AND a.attnum=k.attnum
      WHERE p.conrelid=c.oid AND p.contype='p')
)
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' AND c.relname='research_ledger_import_proof_v1';
COMMIT;`;
const output = execFileSync(psql, [
  '-h', '127.0.0.1', '-p', port, '-d', 'specimen-digitization-database',
  '-X', '-q', '-A', '-t', '-v', 'ON_ERROR_STOP=1', '-c', sql,
], { encoding: 'utf8', timeout: 10000 }).trim();
const lines = output.split('\n').filter(Boolean);
assert.equal(lines.length, 1, 'the retained legacy proof type must declare exactly one physical table');
const actual = JSON.parse(lines[0]);
assert.equal(actual.schema, 'public');
assert.equal(actual.table, 'research_ledger_import_proof_v1');
assert.equal(actual.kind, 'r');
const columns = [
  'organization_id', 'program_key', 'id', 'legacy_collection_id', 'legacy_document_id',
  'legacy_document_revision', 'legacy_document_kind', 'legacy_payload', 'legacy_payload_digest',
  'ledger_digest', 'import_digest', 'proof_digest', 'settled_micro_usd', 'held_micro_usd',
  'lag_reserve_micro_usd', 'shared_reserve_micro_usd', 'ceiling_micro_usd',
  'authority_complete', 'old_engine_quiescent', 'verified_at', 'valid_until',
];
const byName = (left, right) => left.name.localeCompare(right.name);
assert.deepEqual(actual.columns.sort(byName), columns.map(name => ({ name, not_null: true })).sort(byName));
assert.deepEqual(actual.primary_key, ['organization_id', 'program_key', 'id']);
console.log('PASS retained legacy proof physical table, columns and scoped primary key; no rows written');
