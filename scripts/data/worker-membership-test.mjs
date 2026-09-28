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
function python(code, input = {}) {
  return JSON.parse(execFileSync(process.env.DATA_TEST_PYTHON || '.venv/bin/python', ['-c', `import importlib.util,json,sys,uuid
s=importlib.util.spec_from_file_location('bootstrap','scripts/data/bootstrap_admin.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
args=json.load(sys.stdin)
${code}`], {encoding: 'utf8', input: JSON.stringify(input)}));
}
const apply = request => raw(request.query, request.variables);
async function members(organizationId) {
  return ok(await raw(`query {
    organizationMembers(where:{organizationId:{eq:"${organizationId}"}}, orderBy:{uid:ASC}) {uid active}
    collectionMembers(where:{organizationId:{eq:"${organizationId}"}}, orderBy:[{uid:ASC},{collectionId:ASC}]) {uid active role canViewSensitive collectionId}
  }`));
}

// The approved hierarchy artifact: the committed tree with synthetic identifiers, bootstrapped first,
// so the organization and its administrator exist exactly as the release creates them.
const artifact = python(`tree=(m.ROOT/m.TREE_PATH).read_bytes()
collections=[{**entry,'id':str(uuid.uuid4())} for entry in m.tree_entries(tree)]
print(json.dumps(m.prepare_first_scope_hierarchy(tree=tree,collections=collections,**args)))`, {
  auth_record: {uid: 'synthetic-admin', email: 'synthetic@example.invalid', emailVerified: true, disabled: false},
  requested_email: 'synthetic@example.invalid', requested_uid: 'synthetic-admin',
  organization_id: randomUUID(), organization_name: 'Synthetic museum', admin_collection_key: 'insects',
});
ok(await apply(artifact.request));
const org = artifact.request.variables.organizationId;
const idOf = key => artifact.hierarchy.collections.find(entry => entry.key === key).id;
const insects = idOf('insects'), other = idOf('mammals');
const prepare = uid => python('print(json.dumps(m.worker_membership_request(**args)))',
  {artifact, approved_sha256: artifact.artifact_sha256, uid, collection_keys: ['insects']});
// The rendered document with hand-set values, for what the allow-list already refuses in Python.
const documentFor = (uid, ...collections) => ({
  query: python(`print(json.dumps(m.worker_membership_mutation(${collections.length})))`),
  variables: Object.fromEntries([['organizationId', org], ['uid', uid],
    ...collections.map((collection, index) => [`c${index}`, collection])]),
});

const request = prepare('synthetic-worker');
assert.equal(request.mode, 'worker-membership-bootstrap/v1');
assert.deepEqual(request.variables, {organizationId: org, uid: 'synthetic-worker', c0: insects});
ok(await apply(request));
const after = await members(org);
assert.deepEqual(after.organizationMembers, [{uid: 'synthetic-admin', active: true}, {uid: 'synthetic-worker', active: true}]);
const worker = after.collectionMembers.filter(m => m.uid === 'synthetic-worker');
assert.deepEqual(worker.map(({collectionId, ...rest}) => rest), [{uid: 'synthetic-worker', active: true, role: 'operator', canViewSensitive: false}]);
assert.equal(worker[0].collectionId.replaceAll('-', ''), insects.replaceAll('-', ''));
console.log('PASS the worker becomes an active, nonsensitive operator in exactly the allow-listed collection');

// An organization member without collection rows, and a leftover collection row without an
// organization member: an administrator's, with sensitive access, that a new organization row would make live.
ok(await raw(`mutation @transaction {
  o: organizationMember_insert(data:{organizationId:"${org}",uid:"synthetic-member-only",active:true})
  l: collectionMember_insert(data:{organizationId:"${org}",collectionId:"${other}",uid:"synthetic-leftover",active:true,role:"admin",canViewSensitive:true})
}`));
const seeded = await members(org);
denied(await apply(request));
denied(await apply(documentFor('synthetic-admin', other)));
denied(await apply(prepare('synthetic-member-only')));
denied(await apply(prepare('synthetic-leftover')));
denied(await apply(documentFor('synthetic-second-worker', other, randomUUID())));
const unchanged = await members(org);
assert.deepEqual(unchanged, seeded);
assert.ok(!unchanged.organizationMembers.some(m => ['synthetic-leftover', 'synthetic-second-worker'].includes(m.uid)));
console.log('PASS a replay, an existing member, a leftover collection row and an unknown collection are refused with nothing written');

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
