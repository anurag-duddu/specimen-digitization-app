// The cost meter's three connector operations against real PostgreSQL and SQL Connect
// (docs/execution/golive/COST_METER.md). Synthetic rows only; no cloud, model or image I/O.
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
const denied = result => assert.ok(result.code || result.errors?.length, JSON.stringify(result));

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
 organization_insert(data:{id:"${organizationId}",name:"Synthetic cost scope"})
 o2: organization_insert(data:{id:"${otherOrganization}",name:"Synthetic other scope"})
 collection_insert(data:{organizationId:"${organizationId}",id:"${insects}",name:"Synthetic insects"})
 c2: collection_insert(data:{organizationId:"${organizationId}",id:"${sibling}",name:"Synthetic sibling"})
 c4: collection_insert(data:{organizationId:"${otherOrganization}",id:"${foreign}",name:"Synthetic foreign"})
}`));
ok(await raw(`mutation { collection_insert(data:{organizationId:"${organizationId}",id:"${child}",name:"Synthetic child",parentId:"${insects}"}) }`));
// uid, collection, role, can view sensitive, organization active, collection active
const actors = [
  ['worker', insects, 'operator', false, true, true], ['worker', child, 'operator', false, true, true],
  ['reviewer', insects, 'reviewer', true, true, true], ['manager', insects, 'manager', true, true, true],
  ['viewer', insects, 'viewer', true, true, true], ['admin', sibling, 'admin', false, true, true],
  ['stranger', sibling, 'operator', true, true, true], ['inactive-org', insects, 'admin', true, false, true],
  ['inactive-collection', insects, 'admin', true, true, false],
];
const orgs = new Map();
for (const [uid, collectionId, role, sensitive, orgActive, collectionActive] of actors) {
  if (!orgs.has(uid)) {
    orgs.set(uid, true);
    ok(await raw(`mutation { organizationMember_insert(data:{organizationId:"${organizationId}",uid:"${uid}",active:${orgActive}}) }`));
  }
  ok(await raw(`mutation { collectionMember_insert(data:{organizationId:"${organizationId}",collectionId:"${collectionId}",uid:"${uid}",active:${collectionActive},role:"${role}",canViewSensitive:${sensitive}}) }`));
}
ok(await raw(`mutation {
 organizationMember_insert(data:{organizationId:"${otherOrganization}",uid:"foreign-admin",active:true})
 collectionMember_insert(data:{organizationId:"${otherOrganization}",collectionId:"${foreign}",uid:"foreign-admin",active:true,role:"admin",canViewSensitive:true})
}`));

const specimen = randomUUID(), sensitive = randomUUID(), nested = randomUUID();
const runOne = randomUUID(), runTwo = randomUUID();
const at = (day, hour=12) => `2026-10-${String(day).padStart(2, '0')}T${String(hour).padStart(2, '0')}:00:00+00:00`;
const paid = (step, kind, name, cost, basis='computed', day=1, extra={}) => ({
  step, attempt:1, kind, [kind === 'model' ? 'route_id' : kind === 'service' ? 'service' : 'tool_id']:name,
  reserved_micros:cost + 100, usage:kind === 'model' ? {input_tokens:120, output_tokens:40} : {seconds:2.5, instance:{first:true, idle_seconds:0, request_seconds:2.5}},
  outcome:'completed', cost_micros:cost, cost_basis:basis, price_list:{version:'2026-10-17', as_of:'2026-10-17'}, at:at(day), ...extra});
const callsOne = [paid('segment', 'service', 'sam3', 1500), paid('transcribe:r1:handwriting-qwen', 'model', 'handwriting-qwen', 210)];
const callsTwo = [paid('segment', 'service', 'sam3', 900, 'computed', 2), paid('transcribe:r1:handwriting-qwen', 'model', 'handwriting-qwen', 0, 'refused', 2, {failure_code:'provider_refused'})];
// Two runs over four revisions: the sweep must return each run's latest revision.
const snapshots = [[1, runOne, callsOne.slice(0, 1)], [2, runOne, callsOne], [3, runTwo, callsTwo.slice(0, 1)], [4, runTwo, callsTwo]];
async function seedSpecimen(collectionId, id, isSensitive, revisions) {
  ok(await raw(`mutation { specimen_insert(data:{organizationId:"${organizationId}",collectionId:"${collectionId}",id:"${id}",revision:${revisions.at(-1)[0]},state:"finalized",sensitive:${isSensitive},createdBy:"worker"}) }`));
  for (const [revision, runId, calls] of revisions) {
    ok(await raw(`mutation($snapshot: Any!) { specimenSnapshot_insert(data:{organizationId:"${organizationId}",collectionId:"${collectionId}",specimenId:"${id}",revision:${revision},contractVersion:"0.1",snapshot:$snapshot,sha256:"${'a'.repeat(64)}"}) }`,
      {snapshot:{id, run:{id:runId, stage:'finalized', paid_calls:calls}}}));
  }
}
await seedSpecimen(insects, specimen, false, snapshots);
await seedSpecimen(insects, sensitive, true, [[1, randomUUID(), callsOne]]);
await seedSpecimen(child, nested, false, [[1, randomUUID(), [paid('parse', 'model', 'harness-qwen', 70, 'reserved', 3)]]]);

const stageOf = step => ({segment:'label_finding', parse:'structuring', classify:'classification', field_research:'field_research'})[step]
  ?? ({transcribe:'reading', first_pass:'first_pass'})[step.split(':')[0]] ?? step.split(':')[0];
function rows(collectionId, specimenId, runId, calls) {
  const seen = new Map();
  return calls.map(c => {
    const key = `${c.step}/${c.attempt}/${c.kind}`, ordinal = seen.get(key) ?? 0; seen.set(key, ordinal + 1);
    return {organization_id:organizationId, collection_id:collectionId, id:uuid5(`cost/${specimenId}/${runId}/${c.step}/${c.attempt}/${c.kind}/${ordinal}`),
      source:'paid_call', specimen_id:specimenId, run_id:runId, step:c.step, stage:stageOf(c.step), attempt:c.attempt, kind:c.kind, ordinal,
      provider:c.kind === 'model' ? 'huggingface' : c.kind === 'service' ? 'google_cloud' : 'tool', resource:c.route_id ?? c.service ?? c.tool_id,
      usage:c.usage, reserved_micros:c.reserved_micros, cost_micros:c.cost_micros, list_cost_micros:c.cost_micros, cost_basis:c.cost_basis,
      outcome:c.outcome, failure_code:c.failure_code ?? null, price_list_version:c.price_list.version, price_list_as_of:c.price_list.as_of,
      occurred_at:c.at, month:c.at.slice(0, 7)};
  });
}
const upsert = (actorUid, collectionId, specimenId, rowList) => op('UpsertCostEntriesV1', {organizationId, collectionId, specimenId, actorUid, rowsJson:JSON.stringify(rowList)}, true);
async function stored(collectionId, specimenId) {
  return ok(await raw(`query { costEntries(where:{organizationId:{eq:"${organizationId}"},collectionId:{eq:"${collectionId}"},specimenId:{eq:"${specimenId}"}}, orderBy:{id:ASC}, limit:2000) { id runId costMicros listCostMicros reservedMicros costBasis month usage updatedAt createdAt } }`)).costEntries;
}

// ---- UpsertCostEntriesV1 ----------------------------------------------------
const first = [...rows(insects, specimen, runOne, callsOne), ...rows(insects, specimen, runTwo, callsTwo)];
assert.equal(ok(await upsert('worker', insects, specimen, first)).upserted, 4);
const written = await stored(insects, specimen);
assert.equal(written.length, 4);
assert.deepEqual(written.map(row => row.id.replaceAll('-', '')).sort(), first.map(row => row.id.replaceAll('-', '')).sort());
assert.deepEqual(written.map(row => [row.costMicros, row.costBasis]).sort(), [['0', 'refused'], ['1500', 'computed'], ['210', 'computed'], ['900', 'computed']]);
assert.ok(written.every(row => row.month === '2026-10'));
await new Promise(resolve => setTimeout(resolve, 20));
assert.equal(ok(await upsert('worker', insects, specimen, first)).upserted, 4, 'a resend rewrites the same rows');
assert.deepEqual(await stored(insects, specimen), written, 'an identical resend keeps every value and updatedAt');
const changed = first.map((row, n) => n === 0 ? {...row, cost_micros:1600, list_cost_micros:1600} : row);
assert.equal(ok(await upsert('worker', insects, specimen, changed)).upserted, 4);
const after = await stored(insects, specimen);
const moved = after.filter(row => written.find(old => old.id === row.id).updatedAt !== row.updatedAt);
assert.equal(moved.length, 1, 'only the changed row has a new updatedAt');
assert.equal(moved[0].costMicros, '1600');
assert.ok(after.every(row => row.createdAt === written.find(old => old.id === row.id).createdAt), 'createdAt never moves');
console.log('PASS upsert writes one row per paid call, an identical resend changes nothing, a change moves only its own updatedAt');

const count = async () => (await stored(insects, specimen)).length + (await stored(insects, sensitive)).length + (await stored(child, nested)).length;
const before = await count();
// Authorization: below operator, outside the collection, an inactive scope, a sensitive specimen without access.
for (const actorUid of ['viewer', 'stranger', 'admin', 'inactive-org', 'inactive-collection', 'missing']) denied(await upsert(actorUid, insects, specimen, changed));
for (const impersonate of [{unauthenticated:true}, {authClaims:{sub:'worker'}}]) denied(await op('UpsertCostEntriesV1', {organizationId, collectionId:insects, specimenId:specimen, actorUid:'worker', rowsJson:JSON.stringify(changed)}, true, impersonate));
const sensitiveRows = rows(insects, sensitive, runOne, callsOne);
denied(await upsert('worker', insects, sensitive, sensitiveRows));
denied(await upsert('worker', sibling, specimen, changed), 'another collection');
denied(await upsert('worker', insects, randomUUID(), changed), 'an unknown specimen');
assert.equal(await count(), before);
// Malformed rows: any one refuses the whole call.
const bad = [
  {...changed[0], kind:'allocation'}, {...changed[0], cost_micros:-1}, {...changed[0], cost_micros:1.5},
  {...changed[0], list_cost_micros:'10'}, {...changed[0], cost_basis:'allocated'}, {...changed[0], specimen_id:nested},
  {...changed[0], organization_id:otherOrganization}, {...changed[0], collection_id:child},
  {...changed[0], id:randomUUID()}, {...changed[0], ordinal:1}, {...changed[0], month:'2026-11'},
  {...changed[0], occurred_at:'yesterday'}, {...changed[0], source:'allocation'}, {...changed[0], usage:'tokens'},
  {...changed[0], attempt:0}, {...changed[0], step:''},
];
for (const row of bad) denied(await upsert('worker', insects, specimen, [changed[1], row]));
denied(await upsert('worker', insects, specimen, []), 'an empty call');
denied(await upsert('worker', insects, specimen, [changed[1], {...changed[0], cost_micros:1000000000000000, list_cost_micros:1000000000000000}]), 'sixteen digits');
// At most 500 rows a call: 501 valid rows are refused whole, 500 are written (in a month no total below reads).
const many = rows(insects, specimen, randomUUID(), Array.from({length:501}, () => paid('classify', 'model', 'harness-qwen', 1)))
  .map(row => ({...row, occurred_at:'2025-01-15T00:00:00+00:00', month:'2025-01'}));
denied(await upsert('worker', insects, specimen, many));
assert.equal(await count(), before);
assert.equal(ok(await upsert('worker', insects, specimen, many.slice(0, 500))).upserted, 500);
const manyIds = new Set(many.slice(0, 500).map(row => row.id.replaceAll('-', '')));
assert.equal((await stored(insects, specimen)).filter(row => manyIds.has(row.id.replaceAll('-', ''))).length, 500);
denied(await upsert('worker', insects, specimen, [changed[1], changed[1]]), 'a duplicate id');
denied(await op('UpsertCostEntriesV1', {organizationId, collectionId:insects, specimenId:specimen, actorUid:'worker', rowsJson:'{"rows":[]}'}, true));
assert.deepEqual((await stored(insects, specimen)).filter(row => !manyIds.has(row.id.replaceAll('-', ''))), after, 'a refused call writes nothing');
assert.equal(await count(), before + 500);
// A member who may view sensitive records writes them.
assert.equal(ok(await upsert('reviewer', insects, sensitive, sensitiveRows)).upserted, 2);
assert.equal(ok(await upsert('worker', child, nested, rows(child, nested, runOne, [paid('parse', 'model', 'harness-qwen', 70, 'reserved', 3)]))).upserted, 1);
console.log('PASS upsert refuses viewers, other collections, inactive scopes, clients and sensitive records without access');
console.log('PASS upsert refuses a call with any malformed row (kind, basis, amount, scope, specimen, id, month, time, usage) and writes nothing');

// ---- ListRunPaidCallsV1 -----------------------------------------------------
const page = async (actorUid, variables={}) => JSON.parse(ok(await op('ListRunPaidCallsV1', {organizationId, collectionId:insects, actorUid, afterId:'', since:'1970-01-01T00:00:00Z', limit:25, ...variables})).page.page_json);
const swept = await page('worker');
assert.equal(swept.specimens, 1, 'the worker sees no sensitive specimen');
assert.equal(swept.last_id, specimen);
assert.deepEqual(swept.items.map(item => [item.specimen_id, item.run_id, item.revision, item.paid_calls.length]).sort(),
  [[specimen, runOne, 2, 2], [specimen, runTwo, 4, 2]].sort(), 'each run from its latest revision, earlier runs included');
assert.deepEqual(swept.items.find(item => item.run_id === runTwo).paid_calls, callsTwo);
const all = await page('reviewer');
assert.equal(all.specimens, 2);
assert.equal(all.last_id, [specimen, sensitive].sort().at(-1));
const one = await page('reviewer', {limit:1}), two = await page('reviewer', {limit:1, afterId:one.last_id});
assert.deepEqual([one.last_id, two.last_id], [specimen, sensitive].sort());
assert.equal((await page('reviewer', {limit:1, afterId:two.last_id})).specimens, 0);
assert.equal((await page('reviewer', {since:'2099-01-01T00:00:00Z'})).specimens, 0, 'since filters by the specimen save');
assert.equal((await page('viewer')).specimens, 2, 'any active member reads its own collection');
for (const variables of [{limit:26}, {limit:0}, {afterId:'not-an-id'}]) denied(await op('ListRunPaidCallsV1', {organizationId, collectionId:insects, actorUid:'worker', afterId:'', since:'1970-01-01T00:00:00Z', limit:25, ...variables}));
for (const actorUid of ['stranger', 'inactive-org', 'inactive-collection', 'missing']) denied(await op('ListRunPaidCallsV1', {organizationId, collectionId:insects, actorUid, afterId:'', since:'1970-01-01T00:00:00Z', limit:25}));
denied(await op('ListRunPaidCallsV1', {organizationId, collectionId:insects, actorUid:'worker', afterId:'', since:'1970-01-01T00:00:00Z', limit:25}, false, {unauthenticated:true}));
console.log('PASS the sweep page returns each run of a specimen at its latest revision, in id order, scoped and sensitivity-filtered');

// ---- CostTotalsV1 -----------------------------------------------------------
// Eleven large calls in November: their sum is above 2^53 and must arrive exact.
const large = Array.from({length:11}, () => paid('field_research', 'model', 'harness-qwen', 999999999999999, 'computed', 1, {reserved_micros:999999999999999}));
const novemberRun = randomUUID();
const november = rows(insects, specimen, novemberRun, large).map(row => ({...row, occurred_at:'2026-11-01T00:00:00+00:00', month:'2026-11'}));
assert.equal(ok(await upsert('worker', insects, specimen, november)).upserted, 11);
const totals = async (actorUid, fromMonth='2026-10', toMonth='2026-11') => ok(await op('CostTotalsV1', {organizationId, actorUid, fromMonth, toMonth}));
const result = await totals('admin');
const groups = JSON.parse(result.totals.totals_json);
assert.equal(groups.admitted, true);
assert.deepEqual(result.collections.map(c => c.name).sort(), ['Synthetic child', 'Synthetic insects', 'Synthetic sibling']);
assert.equal(result.collections.find(c => c.name === 'Synthetic child').parentId.replaceAll('-', ''), insects.replaceAll('-', ''));
const key = g => [g.collection_id, g.month, g.stage, g.source, g.kind, g.provider, g.resource, g.cost_basis].join('|');
assert.deepEqual(Object.fromEntries(groups.groups.map(g => [key(g), [g.cost_micros, g.list_cost_micros, g.entries]])), {
  // 1600 and 900 on the specimen's two runs, 1500 on the sensitive specimen.
  [`${insects}|2026-10|label_finding|paid_call|service|google_cloud|sam3|computed`]: ['4000', '4000', '3'],
  [`${insects}|2026-10|reading|paid_call|model|huggingface|handwriting-qwen|computed`]: ['420', '420', '2'],
  [`${insects}|2026-10|reading|paid_call|model|huggingface|handwriting-qwen|refused`]: ['0', '0', '1'],
  [`${insects}|2026-11|field_research|paid_call|model|huggingface|harness-qwen|computed`]: ['10999999999999989', '10999999999999989', '11'],
  [`${child}|2026-10|structuring|paid_call|model|huggingface|harness-qwen|reserved`]: ['70', '70', '1'],
});
assert.ok(groups.groups.every(g => /^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$/.test(g.updated_at)));
const october = JSON.parse((await totals('admin', '2026-10', '2026-10')).totals.totals_json).groups;
assert.deepEqual(october.map(g => g.month), ['2026-10', '2026-10', '2026-10', '2026-10'], 'the month range bounds the sums');
assert.deepEqual(JSON.parse((await totals('admin', '2026-12', '2027-01')).totals.totals_json).groups, []);
console.log('PASS totals sum each collection, month, stage, kind, provider, resource and basis exactly, above 2^53 too, within the month range');
for (const actorUid of ['worker', 'reviewer', 'manager', 'viewer', 'stranger', 'inactive-org', 'inactive-collection', 'foreign-admin', 'missing']) {
  denied(await op('CostTotalsV1', {organizationId, actorUid, fromMonth:'2026-10', toMonth:'2026-11'}));
}
for (const [fromMonth, toMonth] of [['2026-13', '2026-13'], ['2026-1', '2026-02'], ['2026-11', '2026-10'], ['', '2026-10'], ['2026-10', '2026-10-01']]) {
  denied(await op('CostTotalsV1', {organizationId, actorUid:'admin', fromMonth, toMonth}));
}
for (const impersonate of [{unauthenticated:true}, {authClaims:{sub:'admin'}}]) denied(await op('CostTotalsV1', {organizationId, actorUid:'admin', fromMonth:'2026-10', toMonth:'2026-11'}, false, impersonate));
const own = ok(await op('CostTotalsV1', {organizationId:otherOrganization, actorUid:'foreign-admin', fromMonth:'2026-10', toMonth:'2026-11'}));
assert.deepEqual(JSON.parse(own.totals.totals_json).groups, [], 'another organization sees none of these rows');
assert.deepEqual(own.collections.map(c => c.name), ['Synthetic foreign']);
console.log('PASS totals need an active administrator of a collection in that organization and valid months; clients are refused');
