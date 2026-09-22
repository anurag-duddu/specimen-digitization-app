// Synthetic-only tests of the exact prepared maintenance transaction. Local only.
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {writeFileSync} from 'node:fs';

const host = process.env.FIREBASE_DATACONNECT_EMULATOR_HOST;
assert.match(host, /^(127\.0\.0\.1|localhost):\d+$/);
const base = `http://${host}/v1/projects/demo-specimen-data/locations/us-east4/services/specimen-digitization-service`;
async function raw(query, variables, readOnly = false) {
  const response = await fetch(`${base}:${readOnly ? 'executeGraphqlRead' : 'executeGraphql'}`, {method: 'POST',
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

function prepareFirst(organizationId, collectionId, uid = 'synthetic-owner') {
  const code = `import importlib.util,json,sys
s=importlib.util.spec_from_file_location('bootstrap','scripts/data/bootstrap_admin.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
args=json.load(sys.stdin)
# Before the repair this executes the real existing-scope operation on empty
# state, so the retained RED is the actual missing-scope denial.
if hasattr(m,'prepare_first_scope'):
    args.update(organization_name='Synthetic first organization',collection_name='Synthetic first collection')
    prepared=m.prepare_first_scope(**args)
else:
    prepared=m.prepare_bootstrap(**args)
print(json.dumps(prepared['request']))`;
  return JSON.parse(execFileSync(process.env.DATA_TEST_PYTHON || '.venv/bin/python', ['-c', code], {
    encoding: 'utf8', input: JSON.stringify({
      auth_record: {uid, email: 'synthetic@example.invalid', emailVerified: true, disabled: false},
      requested_email: 'synthetic@example.invalid', requested_uid: uid,
      organization_id: organizationId, collection_id: collectionId,
    }),
  }));
}
async function allScope(organizationId) {
  return ok(await raw(`query {
    organization(key:{id:"${organizationId}"}) {id name}
    collections(where:{organizationId:{eq:"${organizationId}"}}) {id organizationId name parentId}
    organizationMembers(where:{organizationId:{eq:"${organizationId}"}}) {uid active}
    collectionMembers(where:{organizationId:{eq:"${organizationId}"}}) {uid active role canViewSensitive collectionId}
  }`));
}
const empty = {organization: null, collections: [], organizationMembers: [], collectionMembers: []};
const freshOrg = randomUUID(), freshCollection = randomUUID();
assert.deepEqual(await allScope(freshOrg), empty);
const firstRequest = prepareFirst(freshOrg, freshCollection);
const firstResponse = await apply(firstRequest);
const inserted = ok(firstResponse);
assert.deepEqual(inserted, {
  organization_insert: {id: freshOrg.replaceAll('-', '')},
  collection_insert: {organizationId: freshOrg.replaceAll('-', ''), id: freshCollection.replaceAll('-', '')},
  organizationMember_insert: {organizationId: freshOrg.replaceAll('-', ''), uid: 'synthetic-owner'},
  collectionMember_insert: {organizationId: freshOrg.replaceAll('-', ''), collectionId: freshCollection.replaceAll('-', ''), uid: 'synthetic-owner'},
});
const firstRows = await allScope(freshOrg);
assert.deepEqual(firstRows, {
  organization: {id: freshOrg.replaceAll('-', ''), name: 'Synthetic first organization'},
  collections: [{id: freshCollection.replaceAll('-', ''), organizationId: freshOrg.replaceAll('-', ''),
    name: 'Synthetic first collection', parentId: null}],
  organizationMembers: [{uid: 'synthetic-owner', active: true}],
  collectionMembers: [{uid: 'synthetic-owner', active: true, role: 'admin', canViewSensitive: false,
    collectionId: freshCollection.replaceAll('-', '')}],
});
const readQuery = execFileSync(process.env.DATA_TEST_PYTHON || '.venv/bin/python', ['-c',
  'import sys;sys.path.insert(0,"scripts/ci");import bootstrap_release;print(bootstrap_release.READ_FIRST_SCOPE)'], {encoding: 'utf8'});
const firstReadback = ok(await raw(readQuery, {organizationId: freshOrg, collectionId: freshCollection}, true));
assert.deepEqual(firstReadback, {
  organization: firstRows.organization,
  collections: firstRows.collections,
  matchingCollections: firstRows.collections,
  organizationMembers: firstRows.organizationMembers,
  members: firstRows.collectionMembers,
});
denied(await apply(firstRequest));
denied(await apply(prepareFirst(freshOrg, freshCollection, 'synthetic-second-owner')));
assert.deepEqual(await allScope(freshOrg), firstRows);
console.log('PASS empty scope creates exact four rows, refuses replay and second owner');
console.log('PASS exact protected readback query through executeGraphqlRead');

// Inject a failing check directly after each later insert in a synthetic copy.
// This proves actual database transaction rollback at every partial-write edge.
const rollbackProof = [];
for (const field of ['collection_insert', 'organizationMember_insert', 'collectionMember_insert']) {
  const org = randomUUID(), collection = randomUUID();
  const request = prepareFirst(org, collection);
  const pattern = new RegExp(`(${field}\\(data:[\\s\\S]*?\\}\\))`);
  assert.match(request.query, pattern);
  request.query = request.query.replace(pattern, '$1 @check(expr: "false", message: "Synthetic rollback fault")');
  const response = await apply(request);
  denied(response);
  assert.ok(response.errors.some(error => error.path?.[0] === field &&
    error.message.includes('Synthetic rollback fault') && error.message.includes('rolled back')));
  const after = await allScope(org);
  assert.deepEqual(after, empty);
  rollbackProof.push({field, response, after});
}
console.log('PASS each later insert failure rolls back all four-table state');

const partialOrg = randomUUID(), partialCollection = randomUUID();
ok(await raw(`mutation { organization_insert(data:{id:"${partialOrg}",name:"Synthetic preserved partial"}) }`));
const partialRows = await allScope(partialOrg);
denied(await apply(prepareFirst(partialOrg, partialCollection)));
assert.deepEqual(await allScope(partialOrg), partialRows);
console.log('PASS partial existing organization is neither adopted nor renamed');

// The fixed collection ID may not silently bind to an already-used ID under a
// different organization; rejecting it also rolls back the new organization.
const foreignOrg = randomUUID();
const foreign = await apply(prepareFirst(foreignOrg, freshCollection));
denied(foreign);
assert.ok(foreign.errors.some(error => error.message.includes('Collection identifier already exists')));
assert.deepEqual(await allScope(foreignOrg), empty);
assert.deepEqual(await allScope(freshOrg), firstRows);
console.log('PASS foreign existing collection identifier leaves both scopes unchanged');

const newRaceOrg = randomUUID(), newRaceCollection = randomUUID();
const newRace = await Promise.all(['synthetic-racer-a', 'synthetic-racer-b'].map(uid =>
  apply(prepareFirst(newRaceOrg, newRaceCollection, uid))));
assert.equal(newRace.filter(result => !result.errors?.length && !result.code).length, 1, JSON.stringify(newRace));
const winner = await allScope(newRaceOrg);
assert.equal(winner.collections.length, 1);
assert.equal(winner.organizationMembers.length, 1);
assert.equal(winner.collectionMembers.length, 1);
assert.equal(winner.organizationMembers[0].uid, winner.collectionMembers[0].uid);
console.log('PASS simultaneous first-scope transactions have exactly one owner winner');
// A synthetic three-node tree proves the generated N-collection transaction: the
// parent rows must be written before their children inside one @transaction, and
// the reviewed parentId must come back from the protected readback query.
const syntheticTree = {
  schema_version: 'collection-tree/v1', recorded: '2026-09-22', source: 'synthetic',
  collections: [
    {key: 'zoology', name: 'Synthetic Zoology', parent: null},
    {key: 'insects', name: 'Synthetic Insects', parent: 'zoology'},
    {key: 'botany', name: 'Synthetic Botany', parent: null},
  ],
};
function prepareHierarchy(organizationId, ids, uid = 'synthetic-tree-owner') {
  const code = `import importlib.util,json,sys
s=importlib.util.spec_from_file_location('bootstrap','scripts/data/bootstrap_admin.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
args=json.load(sys.stdin)
tree=json.dumps(args.pop('tree')).encode()
print(json.dumps(m.prepare_first_scope_hierarchy(tree=tree,**args)['request']))`;
  return JSON.parse(execFileSync(process.env.DATA_TEST_PYTHON || '.venv/bin/python', ['-c', code], {
    encoding: 'utf8', input: JSON.stringify({
      auth_record: {uid, email: 'synthetic@example.invalid', emailVerified: true, disabled: false},
      requested_email: 'synthetic@example.invalid', requested_uid: uid,
      organization_id: organizationId, organization_name: 'Synthetic tree organization',
      admin_collection_key: 'insects', tree: syntheticTree,
      collections: syntheticTree.collections.map((entry, index) => ({
        key: entry.key, id: ids[index], name: entry.name, parent: entry.parent})),
    }),
  }));
}
const treeOrg = randomUUID(), treeIds = [randomUUID(), randomUUID(), randomUUID()];
assert.deepEqual(await allScope(treeOrg), empty);
const treeRequest = prepareHierarchy(treeOrg, treeIds);
const treeResponse = ok(await apply(treeRequest));
const bare = value => value.replaceAll('-', '');
assert.deepEqual(treeResponse, {
  organization_insert: {id: bare(treeOrg)},
  c0: {organizationId: bare(treeOrg), id: bare(treeIds[0])},
  c1: {organizationId: bare(treeOrg), id: bare(treeIds[1])},
  c2: {organizationId: bare(treeOrg), id: bare(treeIds[2])},
  organizationMember_insert: {organizationId: bare(treeOrg), uid: 'synthetic-tree-owner'},
  collectionMember_insert: {organizationId: bare(treeOrg), collectionId: bare(treeIds[1]),
    uid: 'synthetic-tree-owner'},
});
const hierarchyQuery = execFileSync(process.env.DATA_TEST_PYTHON || '.venv/bin/python', ['-c',
  'import sys;sys.path.insert(0,"scripts/ci");import bootstrap_release;print(bootstrap_release.READ_FIRST_SCOPE_HIERARCHY)'],
  {encoding: 'utf8'});
const treeReadback = ok(await raw(hierarchyQuery,
  {organizationId: treeOrg, ids: treeIds, limit: treeIds.length + 1}, true));
const byName = rows => [...rows].sort((a, b) => a.name.localeCompare(b.name));
const expectedRows = [
  {id: bare(treeIds[0]), organizationId: bare(treeOrg), name: 'Synthetic Zoology', parentId: null},
  {id: bare(treeIds[1]), organizationId: bare(treeOrg), name: 'Synthetic Insects', parentId: bare(treeIds[0])},
  {id: bare(treeIds[2]), organizationId: bare(treeOrg), name: 'Synthetic Botany', parentId: null},
];
assert.deepEqual(treeReadback.organization, {id: bare(treeOrg), name: 'Synthetic tree organization'});
assert.deepEqual(byName(treeReadback.collections), byName(expectedRows));
assert.deepEqual(byName(treeReadback.matchingCollections), byName(expectedRows));
assert.deepEqual(treeReadback.organizationMembers, [{uid: 'synthetic-tree-owner', active: true}]);
assert.deepEqual(treeReadback.members, [{uid: 'synthetic-tree-owner', collectionId: bare(treeIds[1]),
  active: true, role: 'admin', canViewSensitive: false}]);
console.log('PASS reviewed tree creates every collection with its exact parent in one transaction');

const treeRows = await allScope(treeOrg);
denied(await apply(treeRequest));
denied(await apply(prepareHierarchy(treeOrg, treeIds, 'synthetic-tree-second-owner')));
denied(await apply(prepareHierarchy(randomUUID(), treeIds)));
assert.deepEqual(await allScope(treeOrg), treeRows);
console.log('PASS reviewed tree refuses replay, a second owner and a reused identifier');

// A child whose parent row does not exist must roll the whole tree back, so no
// partially built hierarchy can survive a rejected transaction.
const orphanOrg = randomUUID(), orphanIds = [randomUUID(), randomUUID(), randomUUID()];
const orphan = prepareHierarchy(orphanOrg, orphanIds);
orphan.query = orphan.query.replace('name: $c1Name, parentId: $c0Id',
  `name: $c1Name, parentId: "${randomUUID()}"`);
denied(await apply(orphan));
assert.deepEqual(await allScope(orphanOrg), empty);
console.log('PASS an unknown parent rolls the whole reviewed tree back');

if (process.env.DATA_TEST_DIR) {
  writeFileSync(`${process.env.DATA_TEST_DIR}/first-scope-proof.json`, JSON.stringify({
    firstResponse, firstRows, firstReadback, rollbackProof, partialRows, newRace, winner,
    treeResponse, treeReadback, treeRows,
  }, null, 2) + '\n', {flag: 'wx', mode: 0o600});
}
