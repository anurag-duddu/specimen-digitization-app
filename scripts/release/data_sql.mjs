// The SQL side of the data release; scripts/release/data_release.py runs one mode per step.
//   probe                      print, as JSON, which parts of the database initialization exist (read only)
//   init                       run sql/initialize.sql, one transaction that creates only what is missing
//   migrate <plan.json>        run the plan's statements in one transaction as the owner role
//   indexes <file.sql>...      create the missing supplemental indexes, then print the created and the invalid ones
// It connects as the release identity's IAM SQL user through the Cloud SQL Node connector: no password, no proxy.
// JSON answers go to stdout, everything a person reads goes to stderr.
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {dirname, join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const INSTANCE = 'specimen-digitization:us-east4:specimen-digitization-instance';
const DATABASE = 'specimen-digitization-database';
const ACTOR = 'specimen-data-release@specimen-digitization.iam';
const OWNER = 'firebaseowner_specimen-digitization-database_public';
const HERE = dirname(fileURLToPath(import.meta.url));

// One row, one JSON object of booleans: everything sql/initialize.sql leaves behind. Plain SQL without
// placeholders, so the unit test can run the same text through psql. Memberships are read as direct grants,
// because the release user also reaches the owner role through cloudsqlsuperuser while it holds that role.
const PROBE = `
WITH names AS (SELECT
    'firebaseowner_specimen-digitization-database_public'::text AS owner,
    'firebasewriter_specimen-digitization-database_public'::text AS writer,
    'firebasereader_specimen-digitization-database_public'::text AS reader,
    'specimen-data-release@specimen-digitization.iam'::text AS release,
    'service-716045864126@gcp-sa-firebasedataconnect.iam'::text AS agent),
  member AS (SELECT r.rolname::text AS role, u.rolname::text AS member
    FROM pg_catalog.pg_auth_members m JOIN pg_catalog.pg_roles r ON r.oid = m.roleid
    JOIN pg_catalog.pg_roles u ON u.oid = m.member WHERE m.inherit_option AND m.set_option),
  database_acl AS (SELECT a.grantee, a.privilege_type FROM pg_catalog.pg_database d,
    pg_catalog.aclexplode(coalesce(d.datacl, pg_catalog.acldefault('d', d.datdba))) a
    WHERE d.datname = pg_catalog.current_database()),
  schema_acl AS (SELECT a.grantee, a.privilege_type FROM pg_catalog.pg_namespace n,
    pg_catalog.aclexplode(coalesce(n.nspacl, pg_catalog.acldefault('n', n.nspowner))) a WHERE n.nspname = 'public'),
  default_acl AS (SELECT d.defaclobjtype::text AS kind, pg_catalog.pg_get_userbyid(a.grantee)::text AS grantee,
      a.privilege_type
    FROM pg_catalog.pg_default_acl d JOIN pg_catalog.pg_namespace n ON n.oid = d.defaclnamespace,
      pg_catalog.aclexplode(d.defaclacl) a, names
    WHERE n.nspname = 'public' AND pg_catalog.pg_get_userbyid(d.defaclrole) = names.owner)
SELECT pg_catalog.jsonb_build_object(
  'owner_role', EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = names.owner),
  'writer_role', EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = names.writer),
  'reader_role', EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = names.reader),
  'uuid_ossp_in_public', EXISTS (SELECT 1 FROM pg_catalog.pg_extension e
    JOIN pg_catalog.pg_namespace n ON n.oid = e.extnamespace WHERE e.extname = 'uuid-ossp' AND n.nspname = 'public'),
  'public_schema_owner', coalesce((SELECT pg_catalog.pg_get_userbyid(nspowner) = names.owner
    FROM pg_catalog.pg_namespace WHERE nspname = 'public'), false),
  'release_user_in_owner', EXISTS (SELECT 1 FROM member WHERE role = names.owner AND member = names.release),
  'data_connect_agent_in_writer', EXISTS (SELECT 1 FROM member WHERE role = names.writer AND member = names.agent),
  'database_connect_grants', (SELECT count(DISTINCT grantee) FROM database_acl WHERE privilege_type = 'CONNECT'
    AND pg_catalog.pg_get_userbyid(grantee) IN (names.owner, names.writer, names.reader)) = 3,
  'database_closed_to_public', NOT EXISTS (SELECT 1 FROM database_acl WHERE grantee = 0
    AND privilege_type IN ('CONNECT', 'TEMPORARY')),
  'schema_usage_grants', (SELECT count(DISTINCT grantee) FROM schema_acl WHERE privilege_type = 'USAGE'
    AND pg_catalog.pg_get_userbyid(grantee) IN (names.writer, names.reader)) = 2,
  'schema_closed_to_public', NOT EXISTS (SELECT 1 FROM schema_acl WHERE grantee = 0),
  'default_privileges', (SELECT count(*) FROM (SELECT DISTINCT kind, grantee, privilege_type FROM default_acl) p
    WHERE (p.kind = 'r' AND p.grantee = names.writer AND p.privilege_type IN ('SELECT', 'INSERT', 'UPDATE', 'DELETE'))
      OR (p.kind = 'r' AND p.grantee = names.reader AND p.privilege_type = 'SELECT')
      OR (p.kind = 'S' AND p.grantee = names.writer AND p.privilege_type = 'USAGE')) = 6
) AS present FROM names`;

const INVALID_INDEXES = `SELECT c.relname AS name FROM pg_catalog.pg_index i
  JOIN pg_catalog.pg_class c ON c.oid = i.indexrelid JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public' AND NOT i.indisvalid ORDER BY 1`;

async function connect() {
  const modules = process.env.RELEASE_NODE_MODULES;
  if (!modules) throw new Error('RELEASE_NODE_MODULES is not set; the workflow installs the connector and pg there');
  const require = createRequire(join(resolve(modules), 'package.json'));
  const {Connector, AuthTypes, IpAddressTypes} = require('@google-cloud/cloud-sql-connector');
  const {Pool} = require('pg');
  const connector = new Connector();
  let pool;
  try {
    const options = await connector.getOptions({
      instanceConnectionName: INSTANCE, ipType: IpAddressTypes.PUBLIC, authType: AuthTypes.IAM});
    pool = new Pool({...options, user: ACTOR, database: DATABASE, max: 1, connectionTimeoutMillis: 15000,
      statement_timeout: 120000, application_name: 'specimen-data-release'});
    return {connector, pool, client: await pool.connect()};
  } catch (error) {
    await pool?.end();
    connector.close();
    throw error;
  }
}

const MODES = {
  async probe(client) {
    console.log(JSON.stringify((await client.query(PROBE)).rows[0].present));
  },

  async init(client) {
    // The file is its own BEGIN ... COMMIT. A failure leaves the session inside the failed transaction.
    try {
      await client.query(readFileSync(join(HERE, 'sql/initialize.sql'), 'utf8'));
    } catch (error) {
      await client.query('ROLLBACK').catch(() => {});
      throw error;
    }
  },

  async migrate(client, [planPath]) {
    const {statements} = JSON.parse(readFileSync(planPath, 'utf8'));
    if (!Array.isArray(statements) || statements.length === 0 || !statements.every(sql => typeof sql === 'string')) {
      throw new Error('the plan holds no statements');
    }
    // One transaction as the owner role. search_path is public alone, so Data Connect's unqualified names and
    // uuid_generate_v4() resolve there. The extended protocol makes PostgreSQL refuse a second command in a statement.
    await client.query('BEGIN');
    try {
      for (const setting of ["lock_timeout = '5s'", "statement_timeout = '30s'",
        "idle_in_transaction_session_timeout = '30s'", 'search_path = public', `ROLE "${OWNER}"`]) {
        await client.query(`SET LOCAL ${setting}`);
      }
      for (const [at, text] of statements.entries()) {
        try {
          await client.query({text, queryMode: 'extended'});
        } catch (error) {
          error.message = `statement ${at + 1} of ${statements.length}: ${error.message}`;
          throw error;
        }
      }
      await client.query('COMMIT');
    } catch (error) {
      await client.query('ROLLBACK').catch(() => {});
      throw new Error(`${error.message}; rolled back, nothing was applied`);
    }
  },

  async indexes(client, files) {
    // CREATE INDEX CONCURRENTLY cannot run inside a transaction, so the owner role is set for the session.
    await client.query(`SET ROLE "${OWNER}"`);
    // A build cut short leaves an invalid index behind, so it gets far longer than an ordinary statement.
    await client.query("SET statement_timeout = '15min'");
    const created = [];
    for (const file of files) {
      const source = readFileSync(file, 'utf8').replace(/^\s*--.*$/gm, '');
      for (const statement of source.split(';').map(text => text.trim()).filter(Boolean)) {
        const name = /^CREATE INDEX CONCURRENTLY IF NOT EXISTS ([a-z_][a-z0-9_]*)\s/.exec(statement)?.[1];
        if (!name) throw new Error(`${file}: every statement must be CREATE INDEX CONCURRENTLY IF NOT EXISTS <name>`);
        const found = await client.query('SELECT pg_catalog.to_regclass($1) IS NOT NULL AS present', [`public.${name}`]);
        if (found.rows[0].present) continue;
        await client.query(statement);
        created.push(name);
      }
    }
    const invalid = (await client.query(INVALID_INDEXES)).rows.map(row => row.name);
    console.log(JSON.stringify({created, invalid}));
  },
};

const [mode, ...args] = process.argv.slice(2);
if (!Object.hasOwn(MODES, mode)) {
  console.error(`usage: node data_sql.mjs ${Object.keys(MODES).join('|')} [arguments]`);
  process.exit(2);
}
let connection;
try {
  connection = await connect();
  await MODES[mode](connection.client, args);
} catch (error) {
  console.error(`data_sql ${mode}: ${error.message}`);
  process.exitCode = 1;
} finally {
  connection?.client.release();
  await connection?.pool.end();
  connection?.connector.close();
}
