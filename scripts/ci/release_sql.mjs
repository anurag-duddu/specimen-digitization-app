// CI-only named SQL verification/index repair. Never creates users or passwords.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync, writeFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {join, resolve} from 'node:path';
const env = process.env;
assert.equal(env.GITHUB_ACTIONS, 'true');
assert.equal(env.GITHUB_REPOSITORY, 'anurag-duddu/specimen-digitization-app');
assert.equal(env.GITHUB_EVENT_NAME, 'push');
assert.equal(env.GITHUB_REF, 'refs/heads/main');
assert.equal(env.DEPLOYMENT_ENVIRONMENT, 'data-production');
assert.equal(env.GITHUB_WORKFLOW_REF, `${env.GITHUB_REPOSITORY}/.github/workflows/data-release.yml@refs/heads/main`);
assert.equal(env.RELEASE_AUTHORIZED_SHA, env.GITHUB_SHA);
const [mode, instance, output] = process.argv.slice(2);
assert.ok(['inventory', 'indexes', 'catalog'].includes(mode));
assert.ok(['specimen-digitization-instance', 'specimen-digitization-restore-20260908-r1'].includes(instance));
const require = createRequire(join(resolve(env.RELEASE_NODE_ROOT), 'node_modules/firebase-tools/package.json'));
assert.equal(require('./package.json').version, '15.8.0');
const {Connector, AuthTypes, IpAddressTypes} = require('@google-cloud/cloud-sql-connector');
const {Pool} = require('pg');
const connector = new Connector();
const connectionOptions = {...(await connector.getOptions({
  instanceConnectionName: `specimen-digitization:us-east4:${instance}`,
  ipType: IpAddressTypes.PUBLIC, authType: AuthTypes.IAM,
})), user: 'specimen-data-release@specimen-digitization.iam',
  max: 1, connectionTimeoutMillis: 15000,
  statement_timeout: 120000, application_name: 'protected-data-release'};
const initialDatabase = mode === 'catalog' ? 'postgres' : 'specimen-digitization-database';
let pool = new Pool({...connectionOptions, database: initialDatabase});
let client;
try {
  client = await pool.connect();
  assert.equal((await client.query('SELECT current_database() AS name')).rows[0].name, initialDatabase);
  if (mode === 'catalog') {
    assert.equal(instance, 'specimen-digitization-instance');
    async function readCatalog() {
      const results = await client.query(readFileSync('scripts/ci/release_sql_catalog.sql', 'utf8'));
      const values = results.filter(result => result.command === 'SELECT').at(-1).rows;
      assert.equal(values.length, 1);
      assert.equal(values[0].expected_database, true);
      assert.equal(values[0].expected_actor, true);
      assert.equal(typeof values[0].application_database_exists, 'boolean');
      return values[0];
    }
    let observations = await readCatalog();
    assert.equal(observations.application_catalog_observed, false);
    if (observations.application_database_exists) {
      client.release(); client = undefined;
      await pool.end();
      pool = new Pool({...connectionOptions, database: 'specimen-digitization-database'});
      client = await pool.connect();
      assert.equal((await client.query('SELECT current_database() AS name')).rows[0].name, 'specimen-digitization-database');
      observations = await readCatalog();
      assert.equal(observations.application_database_exists, true);
      assert.equal(observations.application_catalog_observed, true);
    }
    writeFileSync(output, JSON.stringify(observations), {mode: 0o600});
  } else {
  // The pre-existing data-release database identity must already have the exact
  // maintenance grants. No role creation, privilege escalation or owner switching.
  if (mode === 'indexes') {
    assert.equal(instance, 'specimen-digitization-instance');
    for (const file of ['dataconnect/sql/paging-indexes.sql', 'dataconnect/sql/search-indexes.sql']) {
      const source = readFileSync(file, 'utf8').replace(/^\s*--.*$/gm, '');
      for (const sql of source.split(';').map(value => value.trim()).filter(Boolean)) {
        const statement = sql.replace(/^\s*--.*$/gm, '').trim();
        assert.match(statement, /^CREATE INDEX CONCURRENTLY IF NOT EXISTS /);
        await client.query(statement);
      }
    }
  }
  const refreshed = mode === 'indexes' || instance === 'specimen-digitization-restore-20260908-r1';
  if (refreshed) await client.query('ANALYZE');
  await client.query('BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY');
  const tables = (await client.query(`SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename`)).rows;
  const rows = [];
  for (const {tablename} of tables) {
    assert.match(tablename, /^[a-z][a-z0-9_]*$/);
    const data = await client.query(`SELECT to_jsonb(t)::text AS row FROM public."${tablename}" t ORDER BY to_jsonb(t)::text COLLATE "C"`);
    rows.push({table: tablename, count: data.rowCount,
      sha256: createHash('sha256').update(JSON.stringify(data.rows)).digest('hex')});
  }
  const indexes = (await client.query(`SELECT c.relname AS name, t.relname AS table_name, a.amname AS method,
    i.indisvalid AS valid, i.indisunique AS unique, pg_get_expr(i.indpred,i.indrelid) AS predicate,
    ARRAY(SELECT pg_get_indexdef(c.oid,k,false) FROM generate_series(1,i.indnkeyatts) k ORDER BY k) AS keys,
    ARRAY(SELECT pg_get_indexdef(c.oid,k,false) FROM generate_series(i.indnkeyatts+1,i.indnatts) k ORDER BY k) AS includes,
    pg_get_indexdef(c.oid) AS definition FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
    JOIN pg_class t ON t.oid=i.indrelid JOIN pg_am a ON a.oid=c.relam
    JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' ORDER BY c.relname`)).rows;
  const columns = (await client.query(`SELECT table_name,column_name,ordinal_position,column_default,is_nullable,data_type,
    udt_name FROM information_schema.columns WHERE table_schema='public' ORDER BY table_name,ordinal_position`)).rows;
  const constraints = (await client.query(`SELECT c.relname AS table_name, x.conname AS name,
    pg_get_constraintdef(x.oid) AS definition FROM pg_constraint x JOIN pg_class c ON c.oid=x.conrelid
    JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' ORDER BY c.relname,x.conname`)).rows;
  const sequenceNames = (await client.query(`SELECT sequencename FROM pg_sequences WHERE schemaname='public' ORDER BY sequencename`)).rows;
  const sequences = [];
  for (const {sequencename} of sequenceNames) {
    assert.match(sequencename, /^[a-z][a-z0-9_]*$/);
    sequences.push({name: sequencename, ...(await client.query(`SELECT last_value,is_called FROM public."${sequencename}"`)).rows[0]});
  }
  const schema = {};
  for (const [name, sql] of Object.entries({
    relations: `SELECT c.relname,c.relkind,c.relrowsecurity,c.relforcerowsecurity,c.reloptions,
      pg_get_userbyid(c.relowner) AS owner,c.relacl::text AS acl FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname='public' ORDER BY c.relname`,
    routines: `SELECT p.proname,pg_get_function_identity_arguments(p.oid) AS arguments,pg_get_functiondef(p.oid) AS definition
      FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.prokind IN ('f','p') ORDER BY 1,2`,
    views: `SELECT c.relname,pg_get_viewdef(c.oid) AS definition FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname='public' AND c.relkind IN ('v','m') ORDER BY c.relname`,
    triggers: `SELECT c.relname,t.tgname,pg_get_triggerdef(t.oid) AS definition FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
      JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' ORDER BY c.relname,t.tgname`,
    policies: `SELECT tablename,policyname,permissive,roles,cmd,qual,with_check FROM pg_policies WHERE schemaname='public' ORDER BY tablename,policyname`,
    enums: `SELECT t.typname,e.enumlabel,e.enumsortorder FROM pg_type t JOIN pg_enum e ON e.enumtypid=t.oid
      JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname='public' ORDER BY t.typname,e.enumsortorder`,
    extensions: `SELECT extname,extversion FROM pg_extension ORDER BY extname`,
  })) schema[name] = (await client.query(sql)).rows;
  let checksumPlan = null;
  if (tables.some(t => t.tablename === 'specimen')) {
    const sample = (await client.query(`SELECT organization_id,collection_id,source_checksum FROM specimen
      WHERE source_checksum IS NOT NULL ORDER BY organization_id,collection_id,source_checksum LIMIT 1`)).rows[0];
    if (sample) checksumPlan = (await client.query(`EXPLAIN (ANALYZE, FORMAT JSON) SELECT id,revision FROM specimen
      WHERE organization_id=$1 AND collection_id=$2 AND source_checksum=$3 LIMIT 2`,
      [sample.organization_id,sample.collection_id,sample.source_checksum])).rows;
  }
  await client.query('COMMIT');
  writeFileSync(output, JSON.stringify({version: 'native-sql-inventory/v1', instance, rows, indexes, columns, constraints,
    sequences, schema, statistics_refreshed: refreshed, checksum_plan: checksumPlan}), {mode: 0o600});
  }
} finally {
  client?.release();
  await pool.end();
  connector.close();
}
