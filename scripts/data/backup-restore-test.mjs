// Real pg_dump/pg_restore proof for the disposable synthetic cluster only.
// This is neither a Cloud SQL backup nor evidence of production recovery.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {readFileSync, realpathSync, writeFileSync} from 'node:fs';
import {basename, join} from 'node:path';

const mode = process.argv[2];
assert.ok(['restore', 'reconcile', 'verify'].includes(mode), 'Use restore, reconcile or verify');
const directory = realpathSync(process.env.DATA_TEST_DIR);
const pgBin = process.env.POSTGRES_BIN;
const port = process.env.SPECIMEN_TEST_PG_PORT;
assert.match(port, /^\d+$/);
assert.ok(!['3000', '8000'].includes(port));
const source = 'specimen-digitization-database';
const restored = 'specimen-digitization-restored';
const connection = ['-h', '127.0.0.1', '-p', port];
// Ignore libpq overrides: even an inherited PGOPTIONS must not alter the proof.
const env = Object.fromEntries(Object.entries(process.env).filter(([key]) => !key.startsWith('PG')));
const run = (command, args, input) => execFileSync(join(pgBin, command), args, {
  encoding: 'utf8', input, env, maxBuffer: 128 * 1024 * 1024,
});
const sql = (database, query) => run('psql', [...connection, '-X', '-d', database, '-v', 'ON_ERROR_STOP=1', '-At'], query).trim();
assert.equal(realpathSync(sql(source, 'SHOW data_directory;')), realpathSync(join(directory, 'cluster')),
  'Refuse to run against any PostgreSQL cluster not owned by this test');
const digest = value => createHash('sha256').update(value).digest('hex');
const quote = value => `"${value.replaceAll('"', '""')}"`;
const supplemental = ['auxiliary_text_cursor', 'snapshot_search_batch', 'specimen_search_cursor', 'specimen_text_cursor'];

function inventory(database, requireSupplemental = true) {
  const tables = JSON.parse(sql(database, `SELECT coalesce(json_agg(x ORDER BY schema, name),'[]') FROM (
    SELECT n.nspname AS schema, c.relname AS name FROM pg_class c
    JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relkind IN ('r','p')
    AND n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema') x;`));
  const rows = tables.map(({schema, name}) => {
    const relation = `${quote(schema)}.${quote(name)}`;
    return {schema, name, count: Number(sql(database, `SELECT count(*) FROM ${relation};`)),
      sha256: digest(sql(database, `SELECT to_jsonb(t)::text FROM ${relation} t ORDER BY to_jsonb(t)::text COLLATE "C";`))};
  });
  const sequences = JSON.parse(sql(database, `SELECT coalesce(json_agg(x ORDER BY schema, name),'[]') FROM (
    SELECT n.nspname AS schema, c.relname AS name FROM pg_class c
    JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relkind='S'
    AND n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema') x;`))
    .map(({schema, name}) => ({schema, name,
      state: sql(database, `SELECT last_value, is_called FROM ${quote(schema)}.${quote(name)};`)}));
  for (const required of ['specimen', 'specimen_snapshot', 'request_receipt', 'audit_event', 'outbox_event',
    'source_asset', 'pipeline_run', 'label_region', 'model_observation', 'organization_member', 'collection_member']) {
    assert.ok(rows.some(row => row.schema === 'public' && row.name === required && row.count > 0),
      `Missing representative synthetic records in ${required}`);
  }
  // pg_dump 17+ emits fresh random psql restriction tokens; exclude only these
  // client-side guards when comparing otherwise complete schema definitions.
  const schema = run('pg_dump', [...connection, '-d', database, '--schema-only'])
    .split('\n').filter(line => !/^\\(?:un)?restrict /.test(line)).join('\n');
  const indexes = JSON.parse(sql(database, `SELECT coalesce(json_agg(x ORDER BY name),'[]') FROM (
    SELECT c.relname AS name, i.indisvalid AS valid, pg_get_indexdef(c.oid) AS definition
    FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
    WHERE c.relname IN (${supplemental.map(name => `'${name}'`).join(',')})) x;`));
  if (requireSupplemental) assert.deepEqual(indexes.map(index => index.name), supplemental,
    'Supplemental indexes missing after restore or explicit post-schema DDL');
  assert.ok(indexes.every(index => index.valid));
  const checksumIndex = JSON.parse(sql(database, `SELECT coalesce(json_agg(x),'[]') FROM (
    SELECT i.indisunique AS unique, i.indisvalid AS valid, pg_get_indexdef(c.oid) AS definition
    FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
    JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname='public' AND c.relname='specimen_scope_checksum') x;`));
  assert.equal(checksumIndex.length, 1, 'Core source checksum uniqueness index missing');
  assert.ok(checksumIndex[0].unique && checksumIndex[0].valid, 'Core checksum uniqueness must stay valid through all phases');
  return {schemaSha256: digest(schema), tables: rows, sequences, supplementalIndexes: indexes, checksumIndex};
}

function checksumRead(database, expected) {
  const literal = value => `'${value.replaceAll("'", "''")}'`;
  const where = `organization_id=${literal(expected.organization_id)} AND collection_id=${literal(expected.collection_id)} AND source_checksum=${literal(expected.source_checksum)}`;
  const query = `SELECT id,revision FROM specimen WHERE ${where}`;
  const rows = JSON.parse(sql(database, `SELECT json_agg(x) FROM (${query}) x;`));
  assert.deepEqual(rows, [{id: expected.id, revision: expected.revision}]);
  const plan = sql(database, `EXPLAIN (ANALYZE, FORMAT JSON) ${query};`);
  assert.match(plan, /specimen_scope_checksum/, 'Restored exact checksum read must use core scoped unique index');
  return {rows, explain: JSON.parse(plan)};
}

const evidencePath = join(directory, 'backup-restore-proof.json');
if (mode === 'restore') {
  const before = inventory(source);
  const dumpPath = join(directory, 'synthetic-full.dump');
  run('pg_dump', [...connection, '-d', source, '--format=custom', '--file', dumpPath]);
  // Never overwrite a database. createdb fails if this target already exists.
  run('createdb', [...connection, '--template=template0', restored]);
  run('pg_restore', [...connection, '-d', restored, '--exit-on-error', '--single-transaction', dumpPath]);
  // pg_dump does not carry planner statistics. Refresh them before evaluating
  // restored query plans; never force an index by disabling sequential scans.
  sql(restored, 'ANALYZE;');
  const after = inventory(restored);
  assert.deepEqual(after, before, 'Restored complete schema, rows or indexes differ');
  const expectedChecksumRead = JSON.parse(sql(source, `SELECT row_to_json(x) FROM (
    SELECT organization_id,collection_id,source_checksum,id,revision FROM specimen JOIN (
      SELECT organization_id,collection_id FROM specimen WHERE source_checksum IS NOT NULL
      GROUP BY organization_id,collection_id ORDER BY count(*) DESC LIMIT 1
    ) largest USING (organization_id,collection_id)
    WHERE source_checksum IS NOT NULL ORDER BY source_checksum,id LIMIT 1) x;`));
  const proof = {kind: 'local-synthetic-only', sourceDatabase: source, restoredDatabase: restored,
    postgresVersion: sql(source, 'SHOW server_version;'), dumpSha256: digest(readFileSync(dumpPath)),
    emulatorArtifact: {name: basename(process.env.DATA_TEST_EMULATOR_BIN),
      sha256: digest(readFileSync(process.env.DATA_TEST_EMULATOR_BIN)), versionSource: 'artifact filename'},
    before, after, restoreEqual: true, connectorRestartEqual: false, writersQuiesced: true,
    restoredStatisticsRefreshed: true,
    expectedChecksumRead, restoredChecksumRead: checksumRead(restored, expectedChecksumRead),
    reconciliationRounds: [], repairVerifications: []};
  writeFileSync(evidencePath, `${JSON.stringify(proof, null, 2)}\n`, {mode: 0o600});
  console.log(`PASS pg_dump/pg_restore into distinct disposable database: ${before.tables.length} tables, complete schema/data and four supplemental indexes equal`);
} else if (mode === 'reconcile') {
  const proof = JSON.parse(readFileSync(evidencePath, 'utf8'));
  const reconciled = inventory(restored, false);
  assert.deepEqual(reconciled.tables, proof.before.tables, 'Connector reconciliation changed restored records');
  assert.deepEqual(reconciled.sequences, proof.before.sequences, 'Connector reconciliation changed restored sequences');
  assert.deepEqual(reconciled.checksumIndex, proof.before.checksumIndex, 'Connector reconciliation changed core uniqueness');
  proof.afterConnectorReconciliation = reconciled;
  proof.supplementalIndexesRemovedByEmulator = supplemental.filter(name =>
    !reconciled.supplementalIndexes.some(index => index.name === name));
  proof.requiredPostSchemaPhase = ['dataconnect/sql/paging-indexes.sql', 'dataconnect/sql/search-indexes.sql'];
  proof.reconciliationRounds.push({inventory: reconciled, removedIndexes: proof.supplementalIndexesRemovedByEmulator});
  writeFileSync(evidencePath, `${JSON.stringify(proof, null, 2)}\n`, {mode: 0o600});
  if (proof.supplementalIndexesRemovedByEmulator.length) {
    console.log('OBSERVED emulator reconciliation removed supplemental indexes; explicit post-schema DDL required next');
  }
} else {
  const proof = JSON.parse(readFileSync(evidencePath, 'utf8'));
  try {
    const afterRestart = inventory(restored);
    assert.deepEqual(afterRestart, proof.before, 'Connector restart changed restored schema/data/indexes');
    proof.afterConnectorRestart = afterRestart;
    proof.connectorRestartEqual = true;
    proof.connectorRestartRequiresExplicitPostSchemaDdl = true;
    proof.repairVerifications.push({inventory: afterRestart,
      checksumRead: checksumRead(restored, proof.expectedChecksumRead)});
  } catch (error) {
    proof.connectorRestartEqual = false;
    proof.connectorRestartFailure = error.message;
    throw error;
  } finally {
    writeFileSync(evidencePath, `${JSON.stringify(proof, null, 2)}\n`, {mode: 0o600});
  }
  console.log('PASS restored connector read proof and complete schema/data/index equality after explicit post-schema DDL');
}
