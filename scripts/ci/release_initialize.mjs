// Named native SQL only; no password, supplied SQL, arbitrary actor or endpoint.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {join,resolve} from 'node:path';
const env=process.env;
assert.equal(env.GITHUB_ACTIONS,'true');
assert.equal(env.GITHUB_REPOSITORY,'anurag-duddu/specimen-digitization-app');
assert.equal(env.GITHUB_EVENT_NAME,'push');
assert.equal(env.GITHUB_REF,'refs/heads/main');
assert.equal(env.GITHUB_REF_PROTECTED,'true');
assert.equal(env.GITHUB_WORKFLOW_REF,`${env.GITHUB_REPOSITORY}/.github/workflows/data-release.yml@refs/heads/main`);
assert.equal(env.RELEASE_AUTHORIZED_SHA,env.GITHUB_SHA);
const [mode,instance,output]=process.argv.slice(2);
assert.ok(['inspect','absence','capability','initialize','clean','post','disposal-check','disposal-absent'].includes(mode));
assert.ok(['specimen-digitization-instance','specimen-digitization-restore-20260908-r1'].includes(instance));
const initializer=env.DEPLOYMENT_ENVIRONMENT==='data-initialization-production';
assert.equal(env.DEPLOYMENT_ENVIRONMENT,initializer?'data-initialization-production':'data-production');
assert.ok(initializer || ['inspect','absence','post','disposal-check','disposal-absent'].includes(mode));
if(mode.startsWith('disposal-')) assert.equal(initializer,false);
const actor=initializer?'specimen-data-initialize@specimen-digitization.iam':'specimen-data-release@specimen-digitization.iam';
assert.equal(env.RELEASE_SERVICE_ACCOUNT,actor+'.gserviceaccount.com');
const deadline=Number(env.INITIALIZATION_DEADLINE);
assert.ok(Number.isSafeInteger(deadline) && deadline*1000>Date.now());
const files=JSON.parse(env.INITIALIZATION_FILES);
const buffers={};
for(const name of ['scripts/ci/release_initialize.py','scripts/ci/release_initialize.mjs',
  'scripts/ci/initialize_database.sql','scripts/ci/initialize_catalog.sql','scripts/ci/initialize_postconditions.sql',
  'scripts/ci/release_catalog_envelope.py']) {
  const buffer=readFileSync(name); // Same verified bytes are consumed below.
  assert.equal(createHash('sha256').update(buffer).digest('hex'),files[name]); buffers[name]=buffer.toString('utf8');
}
assert.equal(Object.keys(files).length,6);
const require=createRequire(join(resolve(env.RELEASE_NODE_ROOT),'node_modules/firebase-tools/package.json'));
assert.equal(require('./package.json').version,'15.8.0');
const {Connector,AuthTypes,IpAddressTypes}=require('@google-cloud/cloud-sql-connector');
const {Pool}=require('pg');
const connector=new Connector();
let pool,client;
const database=['initialize','post'].includes(mode)?'specimen-digitization-database':'postgres';
try {
  const options=await connector.getOptions({instanceConnectionName:`specimen-digitization:us-east4:${instance}`,ipType:IpAddressTypes.PUBLIC,authType:AuthTypes.IAM});
  pool=new Pool({...options,user:actor,database,max:1,connectionTimeoutMillis:10000,
    statement_timeout:30000,lock_timeout:5000,idle_in_transaction_session_timeout:30000,
    application_name:`specimen-init-${env.GITHUB_RUN_ID}-${env.GITHUB_RUN_ATTEMPT}`});
  client=await pool.connect();
  const context=(await client.query('SELECT current_database() AS database,session_user AS actor,current_user AS effective')).rows[0];
  assert.deepEqual(context,{database,actor,effective:actor});
  const writers=(await client.query("SELECT count(*)::int AS count FROM pg_stat_activity WHERE backend_type='client backend' AND pid<>pg_backend_pid() AND datname IS NOT NULL")).rows[0].count;
  if(mode!=='inspect') assert.equal(writers,0,'unknown native client sessions require writer reconciliation');
  if(mode.startsWith('disposal-')) {
    const principal='specimen-data-initialize@specimen-digitization.iam';
    assert.equal((await client.query('SELECT count(*)::int AS count FROM pg_stat_activity WHERE usename=$1',[principal])).rows[0].count,0);
    const roles=(await client.query('SELECT oid,NOT (rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls) AS narrow FROM pg_roles WHERE rolname=$1',[principal])).rows;
    if(mode==='disposal-absent') assert.equal(roles.length,0);
    else {
      assert.equal(roles.length,1); assert.equal(roles[0].narrow,true);
      assert.equal((await client.query('SELECT count(*)::int AS count FROM pg_auth_members WHERE member=$1',[roles[0].oid])).rows[0].count,0);
      assert.equal((await client.query("SELECT count(*)::int AS count FROM pg_shdepend WHERE refclassid='pg_authid'::regclass AND refobjid=$1",[roles[0].oid])).rows[0].count,0);
    }
    writeFileSync(output,JSON.stringify({instance,mode,files,verified:true}),{mode:0o600});
  } else if(mode==='clean') {
    assert.equal((await client.query("SELECT count(*)::int AS count FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=session_user)")).rows[0].count,0);
    const safe=(await client.query('SELECT NOT (rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls) AS safe FROM pg_roles WHERE rolname=session_user')).rows[0];
    assert.equal(safe.safe,true);
    let denied=false;
    try {await client.query('SET ROLE cloudsqlsuperuser');} catch(error) {assert.equal(error.code,'42501');denied=true;}
    assert.equal(denied,true,'initializer still has managed-role SET capability');
    assert.equal((await client.query("SELECT count(*)::int AS count FROM pg_shdepend WHERE refclassid='pg_authid'::regclass AND refobjid=(SELECT oid FROM pg_roles WHERE rolname=session_user)")).rows[0].count,0);
    writeFileSync(output,JSON.stringify({instance,mode,files,roles_revoked:true,privileged_set_denied:true,dependencies:0}),{mode:0o600});
  } else if(mode==='initialize' || mode==='post') {
    assert.ok(deadline*1000-Date.now()>60000,'insufficient SQL/cleanup window');
    if(mode==='initialize') await client.query(buffers['scripts/ci/initialize_database.sql']);
    else await client.query('BEGIN READ ONLY');
    const results=await client.query(buffers['scripts/ci/initialize_postconditions.sql']);
    const post=results.filter(r=>r.command==='SELECT').at(-1).rows[0].postconditions;
    assert.equal(post.database_owner,'cloudsqlsuperuser');
    if(mode==='initialize' && instance==='specimen-digitization-instance') {
      const expected=JSON.parse(env.INITIALIZATION_EXPECTED_POST);
      const comparable=value=>Object.fromEntries(Object.entries(value).filter(([key])=>key!=='database_oid'));
      assert.deepEqual(comparable(post),comparable(expected),'source database properties/privileges differ from clone qualification');
    }
    await client.query('COMMIT');
    writeFileSync(output,JSON.stringify({instance,mode,files,postconditions:post}),{mode:0o600});
  } else {
    await client.query('BEGIN READ ONLY');
    const catalog=(await client.query(buffers['scripts/ci/initialize_catalog.sql'])).rows[0].catalog;
    // Retain native facts even when a later capability/absence guard rejects.
    writeFileSync(output,JSON.stringify({instance,mode,files,catalog,qualified:false}),{mode:0o600});
    let capability;
    assert.equal(catalog.server_major,18);
    if(mode!=='inspect') {
    assert.deepEqual(catalog.databases.map(d=>d.name),['postgres']);
    assert.deepEqual(catalog.namespaces.map(n=>n.name),['public']);
    for(const name of ['user_relations','user_routines','user_types','event_triggers','publications','foreign_servers','foreign_wrappers','large_objects']) assert.equal(catalog[name],0);
    for(const name of ['firebaseowner','firebasewriter','firebasereader'].map(p=>p+'_specimen-digitization-database_public')) assert.ok(!catalog.roles.some(r=>r.name===name));
    for(const name of ['specimen-api-runtime','specimen-worker-runtime'].map(p=>p+'@specimen-digitization.iam')) assert.ok(!catalog.roles.some(r=>r.name===name),'runtime SQL identities require separate review');
    for(const name of ['specimen-data-release@specimen-digitization.iam','service-716045864126@gcp-sa-firebasedataconnect.iam']) {
      const role=catalog.roles.find(r=>r.name===name); assert.ok(role?.login);
      for(const flag of ['super','create_role','create_db','replication','bypass_rls']) assert.equal(role[flag],false);
      assert.equal((await client.query("SELECT pg_has_role($1,'cloudsqlsuperuser','MEMBER') AS elevated",[name])).rows[0].elevated,false);
      assert.equal((await client.query("SELECT has_database_privilege($1,'postgres','CREATE') AS elevated",[name])).rows[0].elevated,false);
    }
    if(mode==='capability') {
      const login=catalog.roles.find(r=>r.name===actor);
      assert.equal(login?.login,true);
      for(const flag of ['super','create_role','create_db','replication','bypass_rls']) assert.equal(login[flag],false);
      const memberships=catalog.memberships.filter(r=>r.member===actor);
      assert.ok(memberships.length>0 && memberships.every(r=>r.role==='cloudsqlsuperuser' && r.admin===false && r.set===true));
      await client.query('SET LOCAL ROLE cloudsqlsuperuser');
      const observed=(await client.query('SELECT current_user AS actor,rolcreaterole AS create_role FROM pg_roles WHERE rolname=current_user')).rows[0];
      assert.deepEqual(observed,{actor:'cloudsqlsuperuser',create_role:true});
      capability={login,memberships,...observed};
      catalog.roles=catalog.roles.filter(r=>r.name!==actor);
      catalog.memberships=catalog.memberships.filter(r=>r.member!==actor);
    } else {
      assert.equal((await client.query("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='specimen-data-initialize@specimen-digitization.iam') AS present")).rows[0].present,false);
    }
    }
    await client.query('ROLLBACK');
    writeFileSync(output,JSON.stringify({instance,mode,files,catalog,qualified:true,capability,native_client_sessions:writers}),{mode:0o600});
  }
} finally {
  client?.release(true);
  await pool?.end();
  connector.close();
}
