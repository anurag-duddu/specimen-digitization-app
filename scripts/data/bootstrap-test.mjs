// Synthetic-only tests of the exact prepared maintenance transaction. Local only.
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {execFileSync} from 'node:child_process';

const host = process.env.FIREBASE_DATACONNECT_EMULATOR_HOST;
assert.match(host, /^(127\.0\.0\.1|localhost):\d+$/);
const base = `http://${host}/v1/projects/demo-specimen-data/locations/us-east4/services/specimen-digitization-service`;
async function raw(query, variables) {
  const response = await fetch(`${base}:executeGraphql`, {method: 'POST',
    headers: {'Content-Type': 'application/json', Authorization: 'Bearer owner'},
    body: JSON.stringify({query, variables})});
  return response.json();
}
const ok = result => { assert.ok(!result.errors?.length && !result.code, JSON.stringify(result)); return result.data; };
const denied = result => assert.ok(result.errors?.length || result.code, JSON.stringify(result));
function prepare(organizationId, collectionId, uid = 'synthetic-admin') {
  const code = `import importlib.util,json,sys
s=importlib.util.spec_from_file_location('bootstrap','scripts/data/bootstrap_admin.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
print(json.dumps(m.prepare_bootstrap(**json.load(sys.stdin))['request']))`;
  return JSON.parse(execFileSync(process.env.DATA_TEST_PYTHON || '.venv/bin/python', ['-c', code], {
    encoding: 'utf8', input: JSON.stringify({
      auth_record: {uid, email: 'synthetic@example.invalid', emailVerified: true, disabled: false},
      requested_email: 'synthetic@example.invalid', requested_uid: uid,
      organization_id: organizationId, collection_id: collectionId,
    }),
  }));
}
const apply = request => raw(request.query, request.variables);
async function scope() {
  const organizationId = randomUUID(), collectionId = randomUUID();
  ok(await raw(`mutation @transaction {
    organization_insert(data:{id:"${organizationId}",name:"Synthetic bootstrap organization"})
    collection_insert(data:{organizationId:"${organizationId}",id:"${collectionId}",name:"Synthetic bootstrap collection"})
  }`));
  return {organizationId, collectionId};
}
async function members(organizationId) {
  return ok(await raw(`query {
    organizationMembers(where:{organizationId:{eq:"${organizationId}"}}) {uid active}
    collectionMembers(where:{organizationId:{eq:"${organizationId}"}}) {uid active role canViewSensitive collectionId}
  }`));
}
const first = await scope();
const request = prepare(first.organizationId, first.collectionId);
ok(await apply(request));
let rows = await members(first.organizationId);
assert.deepEqual(rows.organizationMembers, [{uid: 'synthetic-admin', active: true}]);
assert.deepEqual(rows.collectionMembers, [{uid: 'synthetic-admin', active: true, role: 'admin', canViewSensitive: false, collectionId: first.collectionId.replaceAll('-', '')}]);
denied(await apply(request));
denied(await apply(prepare(first.organizationId, first.collectionId, 'synthetic-other')));
assert.deepEqual(await members(first.organizationId), rows);
console.log('PASS first-admin atomic insert, least-sensitive default, duplicate and second-admin denial');

const collision = await scope();
ok(await raw(`mutation { collectionMember_insert(data:{organizationId:"${collision.organizationId}",collectionId:"${collision.collectionId}",uid:"synthetic-admin",active:false,role:"reviewer",canViewSensitive:false}) }`));
rows = await members(collision.organizationId);
denied(await apply(prepare(collision.organizationId, collision.collectionId)));
assert.deepEqual(await members(collision.organizationId), rows);
console.log('PASS existing inactive membership cannot be reactivated or elevated');

const existingOrganizationMember = await scope();
ok(await raw(`mutation { organizationMember_insert(data:{organizationId:"${existingOrganizationMember.organizationId}",uid:"synthetic-admin",active:false}) }`));
rows = await members(existingOrganizationMember.organizationId);
denied(await apply(prepare(existingOrganizationMember.organizationId, existingOrganizationMember.collectionId)));
assert.deepEqual(await members(existingOrganizationMember.organizationId), rows);
console.log('PASS existing inactive organization membership cannot be reactivated');

// An inactive administrator is still a previous bootstrap; another collection
// in the same organization must not reopen this one-time maintenance path.
const inactiveAdmin = await scope(), nextCollection = randomUUID();
ok(await raw(`mutation @transaction {
  collectionMember_insert(data:{organizationId:"${inactiveAdmin.organizationId}",collectionId:"${inactiveAdmin.collectionId}",uid:"synthetic-prior-admin",active:false,role:"admin",canViewSensitive:false})
  collection_insert(data:{organizationId:"${inactiveAdmin.organizationId}",id:"${nextCollection}",name:"Synthetic additional collection"})
}`));
rows = await members(inactiveAdmin.organizationId);
denied(await apply(prepare(inactiveAdmin.organizationId, nextCollection)));
assert.deepEqual(await members(inactiveAdmin.organizationId), rows);
console.log('PASS prior inactive administrator in another collection blocks a new bootstrap');

// Remove only the precondition from a synthetic test copy to force the second
// INSERT's composite-key collision, proving the first INSERT is rolled back.
const collidingRequest = prepare(collision.organizationId, collision.collectionId);
collidingRequest.query = collidingRequest.query.replace(
  /    priorMemberships: collectionMembers[^\n]*\n[^\n]*\n/, '');
assert.ok(!collidingRequest.query.includes('priorMemberships'));
denied(await apply(collidingRequest));
assert.equal((await members(collision.organizationId)).organizationMembers.length, 0);
assert.deepEqual((await members(collision.organizationId)).collectionMembers,
  [{uid: 'synthetic-admin', active: false, role: 'reviewer', canViewSensitive: false,
    collectionId: collision.collectionId.replaceAll('-', '')}]);
console.log('PASS second insert unique-key collision rolls back organization membership');

const mismatched = await scope();
denied(await apply(prepare(mismatched.organizationId, first.collectionId)));
assert.deepEqual(await members(mismatched.organizationId), {organizationMembers: [], collectionMembers: []});
console.log('PASS cross-organization collection binding denied without partial membership');
denied(await apply(prepare(randomUUID(), randomUUID())));
console.log('PASS nonexistent organization cannot be bootstrapped');

const race = await scope();
const outcomes = await Promise.all(['synthetic-racer-a', 'synthetic-racer-b'].map(uid =>
  apply(prepare(race.organizationId, race.collectionId, uid))));
assert.equal(outcomes.filter(result => !result.errors?.length && !result.code).length, 1, JSON.stringify(outcomes));
rows = await members(race.organizationId);
assert.equal(rows.organizationMembers.length, 1);
assert.equal(rows.collectionMembers.length, 1);
assert.equal(rows.organizationMembers[0].uid, rows.collectionMembers[0].uid);
console.log('PASS concurrent distinct-UID first-admin attempts serialize with exactly one winner');
