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
// The envelope's owner-set commit or, never with it, the commit of the gate record Python admitted (G11).
assert.ok((env.RELEASE_AUTHORIZED_SHA === undefined) !== (env.RELEASE_GATE_SHA === undefined));
assert.equal(env.RELEASE_AUTHORIZED_SHA ?? env.RELEASE_GATE_SHA, env.GITHUB_SHA);
const [mode, instance, output, input] = process.argv.slice(2);
assert.ok(['inventory', 'indexes', 'indexed', 'catalog', 'summary', 'migrate', 'migrated'].includes(mode));
assert.ok(['specimen-digitization-instance', 'specimen-digitization-restore-20260908-r1'].includes(instance));
const ACTOR = 'specimen-data-release@specimen-digitization.iam';
const OWNER = 'firebaseowner_specimen-digitization-database_public';
// RELEASE.md 4.3 steps 3 and 5, and 4.4's verify, serve only a gate record's commit, on the source instance.
if (mode.startsWith('migrate') || mode === 'indexed') {
  assert.ok(env.RELEASE_GATE_SHA !== undefined && instance === 'specimen-digitization-instance');
}
// Every index in public with what deploy_data.verify_indexes checks: its table, method, validity, keys and definition.
const INDEXES = `SELECT c.relname AS name, t.relname AS table_name, a.amname AS method,
    i.indisvalid AS valid, i.indisunique AS unique, pg_get_expr(i.indpred,i.indrelid) AS predicate,
    ARRAY(SELECT pg_get_indexdef(c.oid,k,false) FROM generate_series(1,i.indnkeyatts) k ORDER BY k) AS keys,
    ARRAY(SELECT pg_get_indexdef(c.oid,k,false) FROM generate_series(i.indnkeyatts+1,i.indnatts) k ORDER BY k) AS includes,
    pg_get_indexdef(c.oid) AS definition FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
    JOIN pg_class t ON t.oid=i.indrelid JOIN pg_am a ON a.oid=c.relam
    JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' ORDER BY c.relname`;
// Step 3 re-reads every statement of the plan Python wrote exactly as deploy_data.py does, before any connection,
// against the plan's own relaxed table.column pairs, which Python derives from the schema gate.
const TOKEN = /([ \t\n\r\f\v]+)|("(?:[^"]|"")+")|('(?:[^']|'')*')|([A-Za-z_][A-Za-z0-9_]*)|([0-9]+(?:\.[0-9]+)?)|([(),.;[\]])|([-+*/<>=~!@#%^&|`?:]+)|([\s\S])/g;
function allowed(sql, relaxed) {
  if (typeof sql !== 'string' || !sql.length || sql.length > 65536 || sql.includes('\\')) return false;
  const kinds = ['space', 'ident', 'string', 'word', 'number', 'punct', 'operator', 'other'];
  let t = [...sql.matchAll(TOKEN)].map(m => [kinds[m.slice(1).findIndex(g => g !== undefined)], m[0]]).filter(([k]) => k !== 'space');
  if (t.some(([k, v]) => k === 'other' || k === 'operator' && /--|\/\*|\*\//.test(v))) return false;
  const is = (at, v) => t[at]?.[0] === 'punct' && t[at][1] === v;
  if (is(t.length - 1, ';')) t = t.slice(0, -1);
  let depth = 0;
  for (let at = 0; at < t.length && depth >= 0; at++) {
    if (is(at, ';')) return false;
    depth += is(at, '(') ? 1 : is(at, ')') ? -1 : 0;
  }
  if (depth) return false;
  const word = (at, ...ws) => ws.every((w, i) => t[at + i]?.[0] === 'word' && t[at + i][1].toUpperCase() === w) ? at + ws.length : null;
  const name = at => {
    const [k, v] = t[at] ?? [];
    if (k !== 'word' && k !== 'ident') throw new Error('name');
    return [k === 'word' ? v.toLowerCase() : v.slice(1, -1).replaceAll('""', '"'), at + 1];
  };
  const table = at => {
    let [value, next] = name(at);
    if (is(next, '.')) {
      if (value !== 'public') throw new Error('schema');
      [value, next] = name(next + 1);
    }
    return [value, next];
  };
  const close = at => {
    for (let i = at, d = 0; i < t.length; i++) if (!(d += is(i, '(') ? 1 : is(i, ')') ? -1 : 0)) return i;
    return -1;
  };
  try {
    let at = word(0, 'CREATE', 'TABLE');
    if (at !== null) {
      [, at] = table(word(at, 'IF', 'NOT', 'EXISTS') ?? at);
      return is(at, '(') && close(at) === t.length - 1;
    }
    if ((at = word(0, 'CREATE', 'VIEW')) !== null) {
      [, at] = table(at);
      if (is(at, '(')) at = close(at) + 1;
      return word(at, 'AS') !== null && ['SELECT', 'WITH', 'VALUES'].some(w => word(at + 1, w) !== null);
    }
    if ((at = word(0, 'CREATE', 'INDEX') ?? word(0, 'CREATE', 'UNIQUE', 'INDEX')) !== null) {
      at = word(at, 'IF', 'NOT', 'EXISTS') ?? at;
      if (word(at, 'CONCURRENTLY') !== null || (at = word(name(at)[1], 'ON')) === null) return false;
      [, at] = table(at);
      return is(at, '(') || word(at, 'USING') !== null;
    }
    if ((at = word(0, 'ALTER', 'TABLE')) === null) return false;
    let relation;
    [relation, at] = table(at);
    const starts = [at];
    for (let i = at, d = 0; i < t.length; i++) {
      d += is(i, '(') ? 1 : is(i, ')') ? -1 : 0;
      if (is(i, ',') && !d) starts.push(i + 1);
    }
    return starts.every((start, k) => {
      const end = k + 1 < starts.length ? starts[k + 1] - 1 : t.length;
      let a;
      if ((a = word(start, 'ADD', 'COLUMN')) !== null) return name(word(a, 'IF', 'NOT', 'EXISTS') ?? a)[1] < end;
      if ((a = word(start, 'ADD', 'CONSTRAINT')) !== null) {
        a = name(a)[1];
        return word(a, 'UNIQUE') !== null || word(a, 'FOREIGN', 'KEY') !== null;
      }
      if ((a = word(start, 'ALTER', 'COLUMN')) === null) return false;
      const [column, next] = name(a);
      return word(next, 'DROP', 'NOT', 'NULL') === end && relaxed.has(`${relation}.${column}`);
    });
  } catch {
    return false;
  }
}
let statements;
if (mode === 'migrate') {
  const plan = JSON.parse(readFileSync(input, 'utf8'));
  assert.deepEqual(Object.keys(plan).sort(), ['relaxed', 'source_sha', 'statements', 'version']);
  assert.ok(plan.version === 'data-migration/v1' && plan.source_sha === env.RELEASE_GATE_SHA);
  // Sorted and duplicate-free, each one table.column pair of lower-case SQL names.
  assert.ok(Array.isArray(plan.relaxed) && plan.relaxed.every((pair, at) => typeof pair === 'string'
    && /^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$/.test(pair) && (at === 0 || plan.relaxed[at - 1] < pair)));
  const relaxed = new Set(plan.relaxed);
  statements = plan.statements;
  assert.ok(Array.isArray(statements) && statements.length > 0 && statements.length <= 1000
    && statements.every(sql => allowed(sql, relaxed)));
}
const require = createRequire(join(resolve(env.RELEASE_NODE_ROOT), 'node_modules/firebase-tools/package.json'));
assert.equal(require('./package.json').version, '15.8.0');
const {Connector, AuthTypes, IpAddressTypes} = require('@google-cloud/cloud-sql-connector');
const {Pool} = require('pg');
const connector = new Connector();
const connectionOptions = {...(await connector.getOptions({
  instanceConnectionName: `specimen-digitization:us-east4:${instance}`,
  ipType: IpAddressTypes.PUBLIC, authType: AuthTypes.IAM,
})), user: ACTOR,
  max: 1, connectionTimeoutMillis: 15000,
  statement_timeout: 120000, application_name: 'protected-data-release'};
const initialDatabase = mode === 'catalog' ? 'postgres' : 'specimen-digitization-database';
let pool = new Pool({...connectionOptions, database: initialDatabase});
let client;
try {
  client = await pool.connect();
  assert.equal((await client.query('SELECT current_database() AS name')).rows[0].name, initialDatabase);
  if (mode === 'summary') {
    assert.equal(instance, 'specimen-digitization-instance');
    const results = await client.query(readFileSync('scripts/ci/release_sql_summary.sql', 'utf8'));
    const values = results.filter(result => result.command === 'SELECT').at(-1).rows;
    assert.equal(values.length, 1);
    writeFileSync(output, JSON.stringify(values[0]), {mode: 0o600});
  } else if (mode === 'catalog') {
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
  } else if (mode === 'migrate') {
    // One transaction as the owner role (RELEASE.md 4.3 step 3). search_path is public alone, behind the implicit
    // pg_catalog, so Data Connect's unqualified uuid_generate_v4() and names resolve to public. The extended protocol
    // makes PostgreSQL itself refuse a second command in any statement.
    await client.query('BEGIN');
    try {
      for (const setting of ["lock_timeout = '5s'", "statement_timeout = '30s'", "idle_in_transaction_session_timeout = '30s'",
        'search_path = public', `ROLE "${OWNER}"`]) await client.query(`SET LOCAL ${setting}`);
      assert.deepEqual((await client.query('SELECT current_database() AS database, session_user AS actor, current_user AS effective')).rows[0],
        {database: 'specimen-digitization-database', actor: ACTOR, effective: OWNER});
      for (const text of statements) await client.query({text, queryMode: 'extended'});
      await client.query('COMMIT');
    } catch (error) {
      await client.query('ROLLBACK').catch(() => {});
      throw error;
    }
    writeFileSync(output, JSON.stringify({version: 'data-migration/v1', statements: statements.length, committed: true}), {mode: 0o600});
  } else if (mode === 'migrated') {
    // Step 5, read only: the initializer's own postconditions (the owner owns every relation in public, the writer and
    // reader hold exactly the default privileges, and the extensions are plpgsql and uuid-ossp), then the relations.
    await client.query('BEGIN TRANSACTION READ ONLY');
    await client.query("SET LOCAL statement_timeout = '30s'");
    const results = await client.query(readFileSync('scripts/ci/initialize_postconditions.sql', 'utf8'));
    const postconditions = results.filter(result => result.command === 'SELECT').at(-1).rows[0].postconditions;
    const catalog = (await client.query(`WITH relations AS (SELECT n.nspname || '.' || c.relname AS qualified, c.relkind,
        pg_get_userbyid(c.relowner)::text AS owner FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE left(n.nspname, 3) <> 'pg_' AND n.nspname <> 'information_schema')
      SELECT current_database() = 'specimen-digitization-database' AS expected_database, session_user = '${ACTOR}' AS expected_actor,
        ARRAY(SELECT qualified FROM relations WHERE relkind IN ('r', 'p', 'f') ORDER BY 1) AS tables,
        ARRAY(SELECT qualified FROM relations WHERE relkind IN ('v', 'm') ORDER BY 1) AS views,
        ARRAY(SELECT DISTINCT owner FROM relations ORDER BY 1) AS owners,
        ARRAY(SELECT extname::text FROM pg_extension ORDER BY 1) AS extensions`)).rows[0];
    await client.query('COMMIT');
    writeFileSync(output, JSON.stringify({...catalog, postconditions}), {mode: 0o600});
  } else if (mode === 'indexed') {
    // RELEASE.md 4.4, Verify: the supplemental index inventory, read only; no row is read.
    await client.query('BEGIN TRANSACTION READ ONLY');
    await client.query("SET LOCAL statement_timeout = '30s'");
    const indexes = (await client.query(INDEXES)).rows;
    await client.query('COMMIT');
    writeFileSync(output, JSON.stringify({version: 'native-sql-indexes/v1', instance, indexes}), {mode: 0o600});
  } else {
  // The pre-existing data-release database identity must already have the exact
  // maintenance grants. No role creation or privilege escalation.
  if (mode === 'indexes') {
    assert.equal(instance, 'specimen-digitization-instance');
    // As the owner role (RELEASE.md 4.3 step 4). CREATE INDEX CONCURRENTLY cannot run in a transaction, so this
    // is the session's SET ROLE; the connection ends with this mode.
    await client.query(`SET ROLE "${OWNER}"`);
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
  const indexes = (await client.query(INDEXES)).rows;
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
