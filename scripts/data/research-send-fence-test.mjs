// Synthetic-only qualification against the real local PostgreSQL connector.
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {execFileSync, spawn} from 'node:child_process';
import {setTimeout as delay} from 'node:timers/promises';

const host = process.env.FIREBASE_DATACONNECT_EMULATOR_HOST;
assert.match(host, /^(127\.0\.0\.1|localhost):\d+$/);
const base = `http://${host}/v1/projects/demo-specimen-data/locations/us-east4/services/specimen-digitization-service`;
async function call(path, body) {
  const response = await fetch(base + path, {method: 'POST',
    headers: {'Content-Type': 'application/json', Authorization: 'Bearer owner'}, body: JSON.stringify(body)});
  return response.json();
}
const raw = query => call(':executeGraphql', {query});
const op = (operationName, variables) => call('/connectors/specimen-server:impersonateMutation',
  {operationName, variables, extensions: {}});
const ok = r => { assert.ok(!r.errors?.length && !r.code, JSON.stringify(r)); return r.data; };
const denied = r => assert.ok(r.errors?.length || r.code, JSON.stringify(r));
const [org, coll, specimen, profile, run, record, binding] = Array.from({length: 7}, randomUUID);
const scope = `organizationId:"${org}",collectionId:"${coll}"`;
const hex = 'a'.repeat(64);
ok(await raw(`mutation {
  organization_insert(data:{id:"${org}",name:"synthetic send fence"})
  collection_insert(data:{organizationId:"${org}",id:"${coll}",name:"synthetic"})
  organizationMember_insert(data:{organizationId:"${org}",uid:"worker",active:true})
  collectionMember_insert(data:{${scope},uid:"worker",active:true,role:"operator",canViewSensitive:false})
  viewerOrg:organizationMember_insert(data:{organizationId:"${org}",uid:"viewer",active:true})
  viewerCollection:collectionMember_insert(data:{${scope},uid:"viewer",active:true,role:"viewer",canViewSensitive:false})
  specimen_insert(data:{${scope},id:"${specimen}",revision:1,state:"running",sensitive:false,createdBy:"worker"})
  profileVersion_insert(data:{${scope},id:"${profile}",profileKey:"synthetic",version:"1",configObject:"{}",configSha256:"${hex}"})
  pipelineRun_insert(data:{${scope},id:"${run}",specimenId:"${specimen}",profileVersionId:"${profile}",pinnedVersions:{},inputSha256:"${hex}"})
  specimen_update(key:{${scope},id:"${specimen}"},data:{activeRunId:"${run}"})
  recordVersion_insert(data:{${scope},id:"${record}",runId:"${run}",policyVersion:"synthetic",reasonCodes:[],summary:"synthetic"})
  specimenSnapshot_insert(data:{${scope},specimenId:"${specimen}",revision:1,contractVersion:"synthetic",snapshot:{},sha256:"${hex}"})
  canonicalResearchBindingV2_insert(data:{${scope},specimenId:"${specimen}",bindingId:"${binding}",registrationRevision:1,active:true,
    baseCanonicalRevision:1,baseRecordVersionId:"${record}",baseSnapshotSha256:"${hex}",baseHostRecordVersionId:"synthetic",
    canonicalRunId:"${run}",currentCanonicalRevision:1,currentRecordVersionId:"${record}",currentSnapshotSha256:"${hex}",currentHostRecordVersionId:"synthetic",
    jobId:"synthetic-job",jobKey:"synthetic-key",generation:1,inputDigest:"${hex}",profileDigest:"${hex}",runtimeBindingDigest:"${hex}",
    canonicalProfileDigest:"${hex}",sourceSha256:"${hex}",semanticMappingDigest:"${hex}",policyDigest:"${hex}",programKey:"synthetic-program",
    semanticMapping:{},authorityDigest:"${hex}",importProofId:"${randomUUID()}",importProofDigest:"${hex}",currentChainDigest:"${hex}",
    publicationVersion:"research-publication/v2",registeredBy:"worker"})
}`));
const vars = {organizationId: org, collectionId: coll, specimenId: specimen, actorUid: 'worker',
  programKey: 'synthetic-program', sensitive: false};
const state = {contract_version: 'research-durability/v1', program_key: vars.programKey,
  budget_policy: {ceiling_micro_usd: 1000000}, halted: false, effects: {},
  budget_totals: {held_micro_usd: 0, settled_micro_usd: 0}};
ok(await op('CreateResearchHarnessStateV1', {...vars, state, stateJson: JSON.stringify(state)}));
const authorization = {canonical_revision: 1, canonical_run_id: run, binding_id: binding,
  job_key: 'synthetic-key', generation: 1, record_version_id: record, snapshot_sha256: hex};
const compare = {...vars, expectedRevision: 1, state, stateJson: JSON.stringify(state),
  validUntil: null, reviewRequired: false,
  sendAuthorizationJson: JSON.stringify(authorization)};
denied(await op('CompareResearchHarnessStateV1', {...compare, actorUid: 'viewer'}));
denied(await op('CompareResearchHarnessStateV1', {...compare, sensitive: true}));
for (const [key, value] of Object.entries({canonical_revision: 2, canonical_run_id: randomUUID(),
  binding_id: randomUUID(), job_key: 'wrong', generation: 2, record_version_id: randomUUID(), snapshot_sha256: 'b'.repeat(64)})) {
  denied(await op('CompareResearchHarnessStateV1', {...compare,
    sendAuthorizationJson: JSON.stringify({...authorization, [key]: value})}));
}
ok(await op('CompareResearchHarnessStateV1', compare));
const psql = process.env.PSQL_BIN;
const pgargs = ['-h', '127.0.0.1', '-p', process.env.SPECIMEN_TEST_PG_PORT,
  '-d', 'specimen-digitization-database', '-qAt', '-v', 'ON_ERROR_STOP=1'];
assert.ok(psql && process.env.SPECIMEN_TEST_PG_PORT);
const human = spawn(psql, [...pgargs, '-c', `BEGIN;
  UPDATE public.specimen SET revision=2 WHERE organization_id='${org}' AND collection_id='${coll}' AND id='${specimen}';
  SELECT pg_sleep(1.5) /* lane_p_human_guard */; COMMIT;`], {stdio: ['ignore', 'pipe', 'pipe']});
let stderr = '';
human.stderr.on('data', data => { stderr += data; });
const ended = new Promise((resolve, reject) => {
  human.on('error', reject);
  human.on('exit', code => code === 0 ? resolve() : reject(new Error(`synthetic human transaction: ${stderr}`)));
});
let locked = false;
for (let n = 0; n < 40; n++) {
  const rows = execFileSync(psql, [...pgargs, '-c', `SELECT count(*) FROM pg_stat_activity
    WHERE pid <> pg_backend_pid() AND query LIKE '%lane_p_human_guard%' AND wait_event='PgSleep'`], {encoding: 'utf8'}).trim();
  if (rows === '1') { locked = true; break; }
  await delay(25);
}
assert.ok(locked, 'actual human transaction acquired its specimen row lock');
// The ordinary @check can see old revision1 before this SQL guard waits; after
// human commit, the MATERIALIZED locked row must be rechecked as revision2.
denied(await op('CompareResearchHarnessStateV1', {...compare, expectedRevision: 2}));
await ended;
const current = ok(await op('ReadResearchHarnessStateV1', vars));
assert.equal(current.read.researchHarnessState.revision, 2);
// A stale send cannot advance state, while receipt/settlement lifecycle can.
ok(await op('CompareResearchHarnessStateV1', {...compare, expectedRevision: 2, sendAuthorizationJson: null}));
assert.equal(ok(await op('ReadResearchHarnessStateV1', vars)).read.researchHarnessState.revision, 3);
console.log('PASS native exact-seven-key send guard, operator/sensitive denial, concurrent human row lock, rollback and receipt-only recovery');
