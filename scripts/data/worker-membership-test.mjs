// Synthetic-only tests of the worker membership bootstrap (docs/execution/golive/WORKER_MEMBERSHIP.md).
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {execFileSync} from 'node:child_process';

const host = process.env.FIREBASE_DATACONNECT_EMULATOR_HOST;
assert.match(host, /^(127\.0\.0\.1|localhost):\d+$/);
const base = `http://${host}/v1/projects/demo-specimen-data/locations/us-east4/services/specimen-digitization-service`;
async function call(path, body) {
  const response = await fetch(base + path, {method: 'POST',
    headers: {'Content-Type': 'application/json', Authorization: 'Bearer owner'}, body: JSON.stringify(body)});
  return response.json();
}
const raw = (query, variables) => call(':executeGraphql', {query, variables});
const op = (operationName, variables) => call('/connectors/specimen-server:impersonateMutation', {operationName, variables, extensions: {}});
const ok = result => { assert.ok(!result.errors?.length && !result.code, JSON.stringify(result)); return result.data; };
const denied = result => assert.ok(result.errors?.length || result.code, JSON.stringify(result));
function prepare(organizationId, uid, collectionIds) {
  const code = `import importlib.util,json,sys
s=importlib.util.spec_from_file_location('bootstrap','scripts/data/bootstrap_admin.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
print(json.dumps(m.worker_membership_request(**json.load(sys.stdin))))`;
  return JSON.parse(execFileSync(process.env.DATA_TEST_PYTHON || '.venv/bin/python', ['-c', code], {
    encoding: 'utf8', input: JSON.stringify({organization_id: organizationId, uid, collection_ids: collectionIds}),
  }));
}
const apply = request => raw(request.query, request.variables);
async function members(organizationId) {
  return ok(await raw(`query {
    organizationMembers(where:{organizationId:{eq:"${organizationId}"}}, orderBy:{uid:ASC}) {uid active}
    collectionMembers(where:{organizationId:{eq:"${organizationId}"}}, orderBy:[{uid:ASC},{collectionId:ASC}]) {uid active role canViewSensitive collectionId}
  }`));
}

// An already bootstrapped organization: two collections and their administrator.
const org = randomUUID(), insects = randomUUID(), other = randomUUID();
ok(await raw(`mutation @transaction {
  o: organization_insert(data:{id:"${org}",name:"Synthetic museum"})
  c1: collection_insert(data:{organizationId:"${org}",id:"${insects}",name:"Synthetic insects"})
  c2: collection_insert(data:{organizationId:"${org}",id:"${other}",name:"Synthetic other"})
  m: organizationMember_insert(data:{organizationId:"${org}",uid:"synthetic-admin",active:true})
  a1: collectionMember_insert(data:{organizationId:"${org}",collectionId:"${insects}",uid:"synthetic-admin",active:true,role:"admin",canViewSensitive:false})
}`));
const before = await members(org);

const request = prepare(org, 'synthetic-worker', [insects]);
assert.equal(request.mode, 'worker-membership-bootstrap/v1');
ok(await apply(request));
const after = await members(org);
assert.deepEqual(after.organizationMembers, [{uid: 'synthetic-admin', active: true}, {uid: 'synthetic-worker', active: true}]);
const worker = after.collectionMembers.filter(m => m.uid === 'synthetic-worker');
assert.deepEqual(worker.map(({collectionId, ...rest}) => rest), [{uid: 'synthetic-worker', active: true, role: 'operator', canViewSensitive: false}]);
assert.equal(worker[0].collectionId.replaceAll('-', ''), insects.replaceAll('-', ''));
console.log('PASS the worker becomes an active, nonsensitive operator in exactly the listed collection');

denied(await apply(request));
denied(await apply(prepare(org, 'synthetic-admin', [insects])));
denied(await apply(prepare(org, 'synthetic-second-worker', [other, randomUUID()])));
const unchanged = await members(org);
assert.deepEqual(unchanged, after);
assert.ok(!unchanged.organizationMembers.some(m => m.uid === 'synthetic-second-worker'));
assert.deepEqual(before.collectionMembers.filter(m => m.uid === 'synthetic-admin'), unchanged.collectionMembers.filter(m => m.uid === 'synthetic-admin'));
console.log('PASS a replay, an existing member and an unknown collection are refused with nothing written');

// The worker can now save non-sensitive records and still cannot touch sensitive ones.
const create = sensitive => {
  const id = randomUUID(), sha = randomUUID().replaceAll('-', '').repeat(2);
  return op('CreateSpecimenV3', {organizationId: org, collectionId: insects, actorUid: 'synthetic-worker', id,
    snapshot: {id, asset: {sha256: sha, sensitive}}, snapshotSha256: 'a'.repeat(64), requestSha256: 'b'.repeat(64),
    idempotencyKey: randomUUID(), operation: 'create', state: 'pending', sensitive, contractVersion: 'v1',
    workAvailableAt: null, sourceChecksum: sha});
};
ok(await create(false));
denied(await create(true));
console.log('PASS the worker membership admits non-sensitive saves and refuses sensitive ones');
