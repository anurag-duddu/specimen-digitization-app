// The cost meter's allocation operations against real PostgreSQL and SQL Connect
// (docs/execution/golive/COST_METER.md, PR 3). Synthetic rows only; no cloud, model or image I/O.
import assert from 'node:assert/strict';
import {createHash, randomUUID} from 'node:crypto';

const host = process.env.FIREBASE_DATACONNECT_EMULATOR_HOST;
assert.match(host || '', /^127\.0\.0\.1:[0-9]{1,5}$/);
const base = `http://${host}/v1/projects/demo-specimen-data/locations/us-east4/services/specimen-digitization-service`;
async function call(path, body) {
  const response = await fetch(base + path, {method:'POST', headers:{'Content-Type':'application/json', Authorization:'Bearer owner'}, body:JSON.stringify(body)});
  return response.json();
}
const raw = (query, variables={}) => call(':executeGraphql', {query, variables});
const op = (operationName, variables, mutation=false, impersonate) => call(`/connectors/specimen-server:impersonate${mutation?'Mutation':'Query'}`, {operationName, variables, extensions:impersonate ? {impersonate} : undefined});
const ok = result => { assert.ok(!result.code && !result.errors?.length, JSON.stringify(result)); return result.data; };
const denied = (result, why='') => assert.ok(result.code || result.errors?.length, `${why} ${JSON.stringify(result)}`);

// projection.derived_id: uuid5 in the projection namespace over the parts joined by '/'.
const NAMESPACE = 'cc7d6cad-7ceb-55e7-9831-a83a5b2f8e85';
function uuid5(name, namespace=NAMESPACE) {
  const hash = createHash('sha1').update(Buffer.concat([Buffer.from(namespace.replaceAll('-', ''), 'hex'), Buffer.from(name, 'utf8')])).digest();
  hash[6] = (hash[6] & 0x0f) | 0x50; hash[8] = (hash[8] & 0x3f) | 0x80;
  const hex = hash.subarray(0, 16).toString('hex');
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
}
assert.equal(uuid5('urn:fieldmuseum:specimen-digitization:projection:v1', '6ba7b811-9dad-11d1-80b4-00c04fd430c8'), NAMESPACE);

const organizationId = randomUUID(), otherOrganization = randomUUID();
const insects = randomUUID(), child = randomUUID(), sibling = randomUUID(), foreign = randomUUID();
ok(await raw(`mutation {
 organization_insert(data:{id:"${organizationId}",name:"Synthetic allocation scope"})
 o2: organization_insert(data:{id:"${otherOrganization}",name:"Synthetic allocation other"})
 collection_insert(data:{organizationId:"${organizationId}",id:"${insects}",name:"Synthetic insects"})
 c2: collection_insert(data:{organizationId:"${organizationId}",id:"${sibling}",name:"Synthetic sibling"})
 c4: collection_insert(data:{organizationId:"${otherOrganization}",id:"${foreign}",name:"Synthetic foreign"})
}`));
ok(await raw(`mutation { collection_insert(data:{organizationId:"${organizationId}",id:"${child}",name:"Synthetic child",parentId:"${insects}"}) }`));
// uid, collection, role, organization active, collection active
const actors = [
  ['alloc-worker', insects, 'operator', true, true], ['alloc-worker', child, 'operator', true, true],
  ['alloc-reviewer', insects, 'reviewer', true, true], ['alloc-viewer', insects, 'viewer', true, true],
  ['alloc-admin', sibling, 'admin', true, true], ['alloc-stranger', sibling, 'operator', true, true],
  ['alloc-inactive-org', insects, 'admin', false, true], ['alloc-inactive-collection', insects, 'operator', true, false],
];
const seen = new Set();
for (const [uid, collectionId, role, orgActive, collectionActive] of actors) {
  if (!seen.has(uid)) {
    seen.add(uid);
    ok(await raw(`mutation { organizationMember_insert(data:{organizationId:"${organizationId}",uid:"${uid}",active:${orgActive}}) }`));
  }
  ok(await raw(`mutation { collectionMember_insert(data:{organizationId:"${organizationId}",collectionId:"${collectionId}",uid:"${uid}",active:${collectionActive},role:"${role}",canViewSensitive:false}) }`));
}
ok(await raw(`mutation {
 organizationMember_insert(data:{organizationId:"${otherOrganization}",uid:"alloc-foreign-admin",active:true})
 collectionMember_insert(data:{organizationId:"${otherOrganization}",collectionId:"${foreign}",uid:"alloc-foreign-admin",active:true,role:"admin",canViewSensitive:false})
}`));

// ---- the measures: specimens, saves, SAM 3 calls and assets around 2026-10-19 (Pacific) ----
const DAY_START = '2026-10-19T07:00:00Z', DAY_END = '2026-10-20T07:00:00Z', MONTH_START = '2026-10-01T07:00:00Z';
const s1 = randomUUID(), s2 = randomUUID(), s3 = randomUUID(), sF = randomUUID();
for (const [org, collectionId, id, created, sensitive] of [[organizationId, insects, s1, '2026-10-05T12:00:00Z', false],
  [organizationId, child, s2, '2026-10-19T10:00:00Z', true], [organizationId, insects, s3, '2026-10-21T12:00:00Z', false],
  [otherOrganization, foreign, sF, '2026-10-02T12:00:00Z', false]]) {
  ok(await raw(`mutation { specimen_insert(data:{organizationId:"${org}",collectionId:"${collectionId}",id:"${id}",revision:1,state:"finalized",sensitive:${sensitive},createdBy:"alloc-worker",createdAt:"${created}"}) }`));
}
// actor, collection, specimen, organization, time: the worker's gaps are 900 (capped), 100 and 900 (capped).
const receipts = [
  ['alloc-worker', insects, s1, organizationId, '2026-10-19T06:50:00Z'],
  ['alloc-worker', insects, s1, organizationId, '2026-10-19T07:05:00Z'],
  ['alloc-worker', child, s2, organizationId, '2026-10-19T07:06:40Z'],
  ['alloc-worker', insects, s1, organizationId, '2026-10-19T09:00:00Z'],
  ['alloc-worker', insects, s1, organizationId, '2026-10-20T07:00:00Z'],
  ['alloc-reviewer', insects, s1, organizationId, '2026-10-19T08:00:00Z'],
  ['alloc-reviewer', foreign, sF, otherOrganization, '2026-10-19T12:00:00Z'],
];
for (const [n, [uid, collectionId, specimenId, org, created]] of receipts.entries()) {
  ok(await raw(`mutation { requestReceipt_insert(data:{organizationId:"${org}",collectionId:"${collectionId}",actorUid:"${uid}",operation:"save:${specimenId}",idempotencyKey:"alloc-${n}",requestSha256:"${'b'.repeat(64)}",specimenId:"${specimenId}",revision:${n + 2},createdAt:"${created}"}) }`));
}
for (const [collectionId, specimenId, bytes, created] of [[insects, s1, '1000', '2026-10-05T12:00:00Z'],
  [child, s2, '2500', '2026-10-19T10:00:00Z'], [insects, s3, '7', '2026-10-21T12:00:00Z']]) {
  ok(await raw(`mutation { sourceAsset_insert(data:{organizationId:"${organizationId}",collectionId:"${collectionId}",id:"${randomUUID()}",specimenId:"${specimenId}",kind:"original",bucket:"synthetic",objectName:"${randomUUID()}",generation:"1",sha256:"${'c'.repeat(64)}",mimeType:"image/png",byteSize:"${bytes}",acquisitionMethod:"upload",uploaderUid:"alloc-worker",createdAt:"${created}"}) }`));
}
async function paidCall(collectionId, specimenId, kind, resource, usage, cost, occurredAt) {
  ok(await raw(`mutation($usage: Any) { costEntry_insert(data:{organizationId:"${organizationId}",collectionId:"${collectionId}",id:"${randomUUID()}",source:"paid_call",specimenId:"${specimenId}",runId:"${randomUUID()}",step:"segment",stage:"label_finding",attempt:1,kind:"${kind}",ordinal:0,provider:"google_cloud",resource:"${resource}",usage:$usage,costMicros:"${cost}",listCostMicros:"${cost}",costBasis:"computed",occurredAt:"${occurredAt}",month:"${occurredAt.slice(0, 7)}"}) }`, {usage}));
}
await paidCall(insects, s1, 'service', 'sam3', {seconds:12.5, instance:{first:false, idle_seconds:2, request_seconds:7.5}}, 1500, '2026-10-19T08:00:00Z');
await paidCall(child, s2, 'service', 'sam3', {seconds:3.25}, 400, '2026-10-19T09:00:00Z');
await paidCall(insects, s1, 'service', 'sam3', {seconds:4, instance:{first:true, idle_seconds:0, request_seconds:2.5}}, 300, '2026-10-10T08:00:00Z');
await paidCall(insects, s1, 'model', 'handwriting-qwen', {input_tokens:10}, 99, '2026-10-19T08:00:00Z');

// ---- CostAllocationInputsV1 -------------------------------------------------
const inputs = (actorUid, variables={}, collectionId=insects) => op('CostAllocationInputsV1', {organizationId, collectionId, actorUid, dayStart:DAY_START, dayEnd:DAY_END, monthStart:MONTH_START, gapSeconds:900, ...variables});
const measured = JSON.parse(ok(await inputs('alloc-worker')).inputs.inputs_json);
assert.equal(measured.admitted, true);
const by = Object.fromEntries(measured.collections.map(c => [c.collection_id, c]));
for (const id of [insects, child, sibling, foreign]) assert.ok(by[id], 'every collection of the deployment, other organizations too');
const numbers = c => Object.fromEntries(Object.entries(c).filter(([key]) => !key.endsWith('_id')).map(([key, value]) => [key, Number(value)]));
assert.deepEqual(numbers(by[insects]), {saves:3, month_saves:4, worker_seconds:1800, month_worker_seconds:2700,
  sam_seconds:7.5, month_sam_seconds:10, sam_direct_micros:1500, asset_bytes:1000, specimens:1});
assert.deepEqual(numbers(by[child]), {saves:1, month_saves:1, worker_seconds:100, month_worker_seconds:100,
  sam_seconds:3.25, month_sam_seconds:3.25, sam_direct_micros:400, asset_bytes:2500, specimens:1});
assert.deepEqual(numbers(by[foreign]), {saves:1, month_saves:1, worker_seconds:0, month_worker_seconds:0,
  sam_seconds:0, month_sam_seconds:0, sam_direct_micros:0, asset_bytes:0, specimens:1});
assert.equal(by[foreign].organization_id, otherOrganization);
assert.ok(Object.values(by[insects]).every(value => typeof value === 'string'), 'sums are text');
// The seconds are the caller's own: the reviewer's one save in Insects is its capped gap, not the worker's 1,800.
assert.equal(Number(JSON.parse(ok(await inputs('alloc-reviewer')).inputs.inputs_json).collections.find(c => c.collection_id === insects).worker_seconds), 900);
console.log('PASS inputs give every collection its saves, the caller\'s capped processing gaps, SAM 3 seconds and charges, bytes and specimens');
for (const actorUid of ['alloc-viewer', 'alloc-stranger', 'alloc-inactive-org', 'alloc-inactive-collection', 'missing']) denied(await inputs(actorUid), actorUid);
denied(await inputs('alloc-worker', {}, sibling), 'a collection the worker is not a member of');
for (const gapSeconds of [0, 3601]) denied(await inputs('alloc-worker', {gapSeconds}), `gap ${gapSeconds}`);
for (const impersonate of [{unauthenticated:true}, {authClaims:{sub:'alloc-worker'}}]) denied(await op('CostAllocationInputsV1', {organizationId, collectionId:insects, actorUid:'alloc-worker', dayStart:DAY_START, dayEnd:DAY_END, monthStart:MONTH_START, gapSeconds:900}, false, impersonate));
for (const window of [{dayEnd:'2026-10-21T07:00:00Z'}, {dayEnd:DAY_START}, {monthStart:'2026-10-20T07:00:00Z'}, {monthStart:'2026-09-01T07:00:00Z'}]) {
  const answer = JSON.parse(ok(await inputs('alloc-worker', window)).inputs.inputs_json);
  assert.deepEqual(answer, {admitted:false, collections:[]}, JSON.stringify(window));
}
console.log('PASS inputs need an active operator or above of the named collection, a bounded gap and a day inside its month');

// ---- UpsertCostAllocationsV1 -------------------------------------------------
function allocation(collectionId, method, {day='2026-10-19', start='2026-10-19T07:00:00+00:00', resource='specimen-sam', stage='label_finding', cost=1000, list=cost, zone='America/Los_Angeles'}={}) {
  return {organization_id:organizationId, collection_id:collectionId, id:uuid5(`cost-allocation/${day}/${resource}/${collectionId}/${method}`),
    source:'allocation', specimen_id:null, run_id:null, step:`allocation:${resource}`, stage, attempt:1, kind:'allocation', ordinal:0,
    provider:'google_cloud', resource, usage:{request_seconds:7.5}, reserved_micros:null, cost_micros:cost, list_cost_micros:list,
    cost_basis:'allocated', outcome:null, failure_code:null, price_list_version:'infrastructure-prices-2026-10-20', price_list_as_of:'2026-10-20',
    occurred_at:start, month:start.slice(0, 7), billing_day:day, allocation_method_id:method,
    allocation_method_details:{billing_day:day, time_zone:zone, hours:24, hourly_seconds:['0', '12.5']}};
}
const upsert = (actorUid, collectionId, rows) => op('UpsertCostAllocationsV1', {organizationId, collectionId, actorUid, rowsJson:JSON.stringify(rows)}, true);
async function stored(collectionId) {
  return ok(await raw(`query { costEntries(where:{organizationId:{eq:"${organizationId}"},collectionId:{eq:"${collectionId}"},source:{eq:"allocation"}}, orderBy:{id:ASC}, limit:500) { id stage resource costMicros listCostMicros costBasis month occurredAt allocationMethodId allocationMethodDetails usage updatedAt createdAt } }`)).costEntries;
}
const rows = [
  allocation(insects, 'sam-residual', {cost:-1960}),
  allocation(insects, 'free-allowance', {cost:-1040, list:0}),
  allocation(insects, 'database-specimens', {resource:'cloud-sql', stage:'database', cost:328603}),
  allocation(insects, 'worker-processing-time', {resource:'specimen-worker', stage:'worker', cost:15013}),
  // Daylight saving ends on 2026-11-01: that day starts at 07:00Z, the next at 08:00Z.
  allocation(insects, 'api-requests', {day:'2026-11-01', start:'2026-11-01T07:00:00+00:00', resource:'specimen-api', stage:'api', cost:381}),
  allocation(insects, 'api-requests', {day:'2026-11-02', start:'2026-11-02T08:00:00Z', resource:'specimen-api', stage:'api', cost:383}),
];
assert.equal(ok(await upsert('alloc-worker', insects, rows)).upserted, rows.length);
const written = await stored(insects);
assert.equal(written.length, rows.length);
assert.deepEqual(written.map(row => row.id.replaceAll('-', '')).sort(), rows.map(row => row.id.replaceAll('-', '')).sort());
const byMethod = Object.fromEntries(written.filter(row => row.month === '2026-10').map(row => [row.allocationMethodId, row]));
assert.deepEqual([byMethod['sam-residual'].costMicros, byMethod['free-allowance'].costMicros, byMethod['free-allowance'].listCostMicros], ['-1960', '-1040', '0']);
assert.ok(written.every(row => row.costBasis === 'allocated' && row.allocationMethodDetails.time_zone === 'America/Los_Angeles'));
assert.deepEqual(written.filter(row => row.month === '2026-11').map(row => row.costMicros).sort(), ['381', '383']);
await new Promise(resolve => setTimeout(resolve, 20));
assert.equal(ok(await upsert('alloc-worker', insects, rows)).upserted, rows.length, 'a resend rewrites the same rows');
assert.deepEqual(await stored(insects), written, 'an identical resend keeps every value and updatedAt');
const changed = rows.map((row, n) => n === 0 ? {...row, cost_micros:-1961, list_cost_micros:-1961} : row);
assert.equal(ok(await upsert('alloc-reviewer', insects, changed)).upserted, rows.length);
const after = await stored(insects);
const moved = after.filter(row => written.find(old => old.id === row.id).updatedAt !== row.updatedAt);
assert.deepEqual(moved.map(row => row.costMicros), ['-1961'], 'only the changed row has a new updatedAt');
assert.ok(after.every(row => row.createdAt === written.find(old => old.id === row.id).createdAt), 'createdAt never moves');
console.log('PASS allocation rows upsert by their derived ids, credits and a residual negative, and an identical resend changes nothing');

const valid = changed[3];
const bad = [
  {...valid, id:randomUUID()}, {...valid, collection_id:child}, {...valid, organization_id:otherOrganization},
  {...valid, source:'paid_call'}, {...valid, kind:'model'}, {...valid, specimen_id:s1}, {...valid, run_id:randomUUID()},
  {...valid, step:'segment'}, {...valid, stage:'reading'}, {...valid, attempt:2}, {...valid, ordinal:1}, {...valid, provider:'huggingface'},
  {...valid, reserved_micros:5}, {...valid, cost_basis:'computed'}, {...valid, outcome:'completed'},
  {...valid, cost_micros:-1, list_cost_micros:-1}, {...valid, cost_micros:5, list_cost_micros:6}, {...valid, cost_micros:1.5, list_cost_micros:1.5},
  {...valid, cost_micros:'10', list_cost_micros:'10'}, {...valid, cost_micros:1000000000000000, list_cost_micros:1000000000000000},
  {...changed[1], list_cost_micros:5}, {...changed[1], cost_micros:5},
  {...valid, allocation_method_id:'guess'}, {...valid, allocation_method_details:'details'},
  {...valid, allocation_method_details:{...valid.allocation_method_details, time_zone:undefined}},
  {...valid, occurred_at:'2026-10-19T00:00:00Z'}, {...valid, month:'2026-11'}, {...valid, billing_day:'2026-10-18'},
  {...valid, occurred_at:'yesterday'}, {...valid, usage:'seconds'}, {...valid, price_list_version:null},
  {...rows[5], start:undefined, occurred_at:'2026-11-02T07:00:00Z'},
];
for (const row of bad) denied(await upsert('alloc-worker', insects, [changed[2], row]), JSON.stringify(row).slice(0, 120));
denied(await upsert('alloc-worker', insects, []), 'an empty call');
denied(await upsert('alloc-worker', insects, [changed[2], changed[2]]), 'a duplicate id');
denied(await op('UpsertCostAllocationsV1', {organizationId, collectionId:insects, actorUid:'alloc-worker', rowsJson:'{"rows":[]}'}, true));
for (const actorUid of ['alloc-viewer', 'alloc-stranger', 'alloc-admin', 'alloc-inactive-org', 'alloc-inactive-collection', 'missing']) denied(await upsert(actorUid, insects, changed), actorUid);
for (const impersonate of [{unauthenticated:true}, {authClaims:{sub:'alloc-worker'}}]) denied(await op('UpsertCostAllocationsV1', {organizationId, collectionId:insects, actorUid:'alloc-worker', rowsJson:JSON.stringify(changed)}, true, impersonate));
denied(await upsert('alloc-worker', sibling, [allocation(sibling, 'database-specimens', {resource:'cloud-sql', stage:'database'})]), 'a collection the worker is not in');
assert.deepEqual(await stored(insects), after, 'a refused call writes nothing');
assert.deepEqual(await stored(sibling), []);
console.log('PASS the upsert refuses any malformed row, a viewer, another collection, inactive scopes and clients, and writes nothing');

// ---- CostAllocationStatusV1 and the signed totals -------------------------------
const status = async (actorUid, org=organizationId) => JSON.parse(ok(await op('CostAllocationStatusV1', {organizationId:org, actorUid})).status.status_json);
assert.deepEqual(await status('alloc-admin'), {admitted:true, latest_occurred_at:'2026-11-02T08:00:00Z', entries:'6'});
assert.deepEqual(await status('alloc-foreign-admin', otherOrganization), {admitted:true, latest_occurred_at:null, entries:'0'});
for (const actorUid of ['alloc-worker', 'alloc-reviewer', 'alloc-viewer', 'alloc-inactive-org', 'alloc-foreign-admin', 'missing']) {
  denied(await op('CostAllocationStatusV1', {organizationId, actorUid}), actorUid);
}
for (const impersonate of [{unauthenticated:true}, {authClaims:{sub:'alloc-admin'}}]) denied(await op('CostAllocationStatusV1', {organizationId, actorUid:'alloc-admin'}, false, impersonate));
const totals = JSON.parse(ok(await op('CostTotalsV1', {organizationId, actorUid:'alloc-admin', fromMonth:'2026-10', toMonth:'2026-10'})).totals.totals_json);
const sam = totals.groups.filter(g => g.source === 'allocation' && g.stage === 'label_finding');
assert.deepEqual(sam.map(g => [g.cost_basis, g.cost_micros, g.list_cost_micros, g.entries]), [['allocated', '-3001', '-1961', '2']]);
console.log('PASS status names the latest allocation day for an administrator only, and totals sum credits as signed text');
