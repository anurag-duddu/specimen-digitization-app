// Synthetic-only qualification of the actual named native registration DML.
// A compiler success or a fake operation client does not prove this transaction.
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';

const host = process.env.FIREBASE_DATACONNECT_EMULATOR_HOST;
assert.match(host, /^127\.0\.0\.1:\d+$/);
const base = `http://${host}/v1/projects/demo-specimen-data/locations/us-east4/services/specimen-digitization-service`;
async function call(path, body) {
  const response = await fetch(base + path, {method: 'POST',
    headers: {'Content-Type': 'application/json', Authorization: 'Bearer owner'},
    body: JSON.stringify(body)});
  assert.equal(response.status, 200);
  return response.json();
}
const raw = (query, variables = {}) => call(':executeGraphql', {query, variables});
const ok = response => {
  assert.ok(!response.errors?.length && !response.code, JSON.stringify(response));
  return response.data;
};
const denied = response => assert.ok(response.errors?.length || response.code, JSON.stringify(response));
const [org, coll, specimen, profile, run, record, binding] = Array.from({length: 7}, randomUUID);
const scope = `organizationId:"${org}",collectionId:"${coll}"`;
const hex = 'a'.repeat(64);
const fields = ['fmnh_ins_number', 'collection_code', 'country', 'province_state', 'county',
  'city', 'precise_location', 'elevation_from_m', 'elevation_to_m', 'elevation_from_ft',
  'elevation_to_ft', 'habitat', 'collection_method', 'date_visited_from', 'date_visited_to',
  'collectors', 'verbatim_dts', 'taxon', 'identified_by_irn', 'date_identified'];
const canonical = {record_revision: 1, record_version_id: record, canonical_run_id: run,
  host_record_version_id: `${run}:1`, snapshot_sha256: hex};
const policy = {ceiling_micro_usd: 1000000, external_settled_micro_usd: 583219};
const registration = {publication_version: 'research-publication/v2', binding_id: binding,
  base_canonical: canonical, current_canonical: canonical, publication_transition: null,
  source_sha256: hex, canonical_profile_digest: hex, job_id: 'synthetic-job', job_key: 'synthetic-key',
  generation: 1, input_digest: hex, runtime_binding_digest: hex, profile_digest: hex,
  program_key: 'synthetic-program', journal_budget_policy: policy, state_revision: 1,
  semantic_mapping: {field_mapping: Object.fromEntries(fields.map(field => [field, field]))},
  semantic_mapping_digest: hex, policy_digest: hex, authority_digest: hex,
  import_proof_id: binding, import_proof_digest: hex, current_chain_digest: hex};
const state = {budget_policy: policy, jobs: {'synthetic-key': {
  identity: {organization_id: org, collection_id: coll, specimen_id: specimen, job_id: 'synthetic-job'},
  record_revision: 1, generation: 1, pins: {input_digest: hex}, binding_digest: hex}}};
ok(await raw(`mutation Seed($state:Any!, $stateJson:String!) @transaction {
  organization_insert(data:{id:"${org}",name:"synthetic native registration"})
  collection_insert(data:{organizationId:"${org}",id:"${coll}",name:"synthetic"})
  organizationMember_insert(data:{organizationId:"${org}",uid:"worker",active:true})
  collectionMember_insert(data:{${scope},uid:"worker",active:true,role:"operator",canViewSensitive:false})
  viewerOrg:organizationMember_insert(data:{organizationId:"${org}",uid:"viewer",active:true})
  viewerMember:collectionMember_insert(data:{${scope},uid:"viewer",active:true,role:"viewer",canViewSensitive:false})
  specimen_insert(data:{${scope},id:"${specimen}",revision:1,state:"running",sourceChecksum:"${hex}",sensitive:false,createdBy:"worker"})
  profileVersion_insert(data:{${scope},id:"${profile}",profileKey:"synthetic",version:"1",configObject:"{}",configSha256:"${hex}"})
  pipelineRun_insert(data:{${scope},id:"${run}",specimenId:"${specimen}",profileVersionId:"${profile}",pinnedVersions:{},inputSha256:"${hex}"})
  specimen_update(key:{${scope},id:"${specimen}"},data:{activeRunId:"${run}"})
  recordVersion_insert(data:{${scope},id:"${record}",runId:"${run}",policyVersion:"synthetic",reasonCodes:[],summary:"synthetic"})
  specimenSnapshot_insert(data:{${scope},specimenId:"${specimen}",revision:1,contractVersion:"synthetic",snapshot:{},sha256:"${hex}"})
  ${fields.map((field, index) => `field${index}:resolvedField_insert(data:{${scope},id:"${randomUUID()}",recordVersionId:"${record}",fieldKey:"${field}",state:"unresolved",fieldGroup:"mandatory"})`).join('\n')}
  researchHarnessState_insert(data:{organizationId:"${org}",programKey:"synthetic-program",revision:1,contractVersion:"research-durability/v1",state:$state,stateJson:$stateJson})
}`, {state, stateJson: JSON.stringify(state)}));
const variables = {organizationId: org, collectionId: coll, specimenId: specimen, actorUid: 'worker'};
const register = (payload = registration, overrides = {}) => call('/connectors/specimen-server:impersonateMutation',
  {operationName: 'RegisterCanonicalResearchBindingV2', variables: {...variables,
    registrationJson: JSON.stringify(payload), ...overrides}});
async function current() {
  return ok(await raw(`query {
    canonicalResearchBindingV2(key:{${scope},specimenId:"${specimen}"}) {
      bindingId registeredAt registeredBy registrationRevision currentCanonicalRevision currentSnapshotSha256 currentReceiptId
    }
    researchHarnessState(key:{organizationId:"${org}",programKey:"synthetic-program"}) {revision state stateJson}
    specimen(key:{${scope},id:"${specimen}"}) {revision state activeRunId sourceChecksum}
  }`));
}
const before = await current();
assert.equal(before.canonicalResearchBindingV2, null);
// The real operation's literal empty-payload probe must touch no row even when
// all required native tables, scope membership and twenty fields exist.
denied(await register({}));
assert.deepEqual(await current(), before);
denied(await register(registration, {actorUid: 'viewer'}));
denied(await register(registration, {collectionId: randomUUID()}));
denied(await register(registration, {actorUid: 'missing-worker'}));
for (const [table, key] of [
  ['organizationMember', `organizationId:"${org}",uid:"worker"`],
  ['collectionMember', `${scope},uid:"worker"`],
]) {
  ok(await raw(`mutation { ${table}_update(key:{${key}},data:{active:false}) }`));
  denied(await register());
  assert.deepEqual(await current(), before, `${table} inactivity allowed registration`);
  ok(await raw(`mutation { ${table}_update(key:{${key}},data:{active:true}) }`));
}
for (const delta of [
  {state_revision: 2}, {source_sha256: 'b'.repeat(64)}, {canonical_profile_digest: 'b'.repeat(64)},
  {journal_budget_policy: {...policy, ceiling_micro_usd: 5000000}},
  {runtime_binding_digest: 'b'.repeat(64)}, {generation: 2},
  {base_canonical: {...canonical, record_revision: 2}},
  {current_canonical: {...canonical, snapshot_sha256: 'b'.repeat(64)}},
  {semantic_mapping: {field_mapping: {country: 'country'}}},
]) {
  denied(await register({...registration, ...delta}));
  assert.deepEqual(await current(), before, 'refused registration changed native state');
}
assert.equal(ok(await register()).registered, 1);
const registered = await current();
assert.equal(registered.canonicalResearchBindingV2.bindingId.replaceAll('-', ''), binding.replaceAll('-', ''));
assert.deepEqual(registered.researchHarnessState, before.researchHarnessState);
assert.deepEqual(registered.specimen, before.specimen);
assert.equal(ok(await register()).registered, 1);
assert.deepEqual(await current(), registered, 'identical unpublished replay changed the registration');
denied(await register({...registration, binding_id: randomUUID()}));
assert.deepEqual(await current(), registered, 'same-current binding overwrite was admitted');

// A later real canonical revision is allowed to replace the stale binding, but
// a mismatched/old snapshot or base never becomes a "latest" fallback.
ok(await raw(`mutation @transaction {
  specimen_update(key:{${scope},id:"${specimen}"},data:{revision:2})
  specimenSnapshot_insert(data:{${scope},specimenId:"${specimen}",revision:2,contractVersion:"synthetic",snapshot:{},sha256:"${'b'.repeat(64)}"})
}`));
const nextState = structuredClone(state);
nextState.jobs['synthetic-key'].record_revision = 2;
ok(await raw(`mutation($state:Any!,$stateJson:String!) {
  researchHarnessState_update(key:{organizationId:"${org}",programKey:"synthetic-program"},
    data:{revision:2,state:$state,stateJson:$stateJson})
}`, {state: nextState, stateJson: JSON.stringify(nextState)}));
const next = {...canonical, record_revision: 2, snapshot_sha256: 'b'.repeat(64), host_record_version_id: `${run}:2`};
denied(await register());
const replacement = {...registration, binding_id: randomUUID(), state_revision: 2,
  base_canonical: next, current_canonical: next};
assert.equal(ok(await register(replacement)).registered, 1);
const replaced = await current();
assert.equal(replaced.canonicalResearchBindingV2.currentCanonicalRevision, 2);
assert.equal(replaced.canonicalResearchBindingV2.bindingId.replaceAll('-', ''), replacement.binding_id.replaceAll('-', ''));
assert.deepEqual(replaced.researchHarnessState.state, nextState);
console.log('PASS actual native registration, empty-payload rollback, actor/scope/budget/pin/revision refusals, replay and stale-binding replacement');

// Every remaining publication write must at least reach its own SQL admission
// count check. A generic errors assertion would hide another SQL grammar bug.
for (const [operationName, argument, message] of [
  ['RetainResearchPublicationIntentV2', 'intentJson', 'native v2 intent unavailable'],
  ['RetainResearchPublicationPreparationV2', 'preparationJson', 'native v2 preparation unavailable'],
  ['MarkResearchPublicationAttemptV2', 'admissionJson', 'native v2 attempt unavailable'],
  ['PublishCanonicalResearchV2', 'commitJson', 'native research publication unavailable'],
]) {
  const response = await call('/connectors/specimen-server:impersonateMutation',
    {operationName, variables: {...variables, [argument]: '{}'}});
  assert.ok(response.errors?.some(error => error.message.includes(message)), JSON.stringify(response));
  assert.deepEqual(await current(), replaced, `${operationName} changed native state on empty payload`);
}
console.log('PASS all four native publication writes parse and refuse empty inputs without changing native state');
