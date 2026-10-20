// Synthetic tenants and members; real SQL Connect authorization and upsert for the
// monthly budget caps (dataconnect/connector/tenant_budget.gql). No cost or ledger.
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';

const host = process.env.FIREBASE_DATACONNECT_EMULATOR_HOST;
assert.match(host || '', /^127\.0\.0\.1:[0-9]{1,5}$/);
const base = `http://${host}/v1/projects/demo-specimen-data/locations/us-east4/services/specimen-digitization-service`;
async function call(path, body) {
  const response = await fetch(base + path, {method:'POST', headers:{'Content-Type':'application/json', Authorization:'Bearer owner'}, body:JSON.stringify(body)});
  return response.json();
}
const raw = query => call(':executeGraphql', {query});
const op = (operationName, variables, mutation=false, impersonate) => call(`/connectors/specimen-server:impersonate${mutation?'Mutation':'Query'}`, {operationName,variables,extensions:{impersonate}});
const ok = result => { assert.ok(!result.code && !result.errors?.length, JSON.stringify(result)); return result.data; };
const denied = result => assert.ok(result.code || result.errors?.length, JSON.stringify(result));
const micros = value => value === null ? null : Number(value);

const organizationId=randomUUID(), collectionId=randomUUID(), childId=randomUUID();
const otherOrganization=randomUUID(), otherCollection=randomUUID();
ok(await raw(`mutation {
 organization_insert(data:{id:"${organizationId}",name:"Synthetic caps scope"})
 parent: collection_insert(data:{organizationId:"${organizationId}",id:"${collectionId}",name:"Synthetic parent"})
 other: organization_insert(data:{id:"${otherOrganization}",name:"Synthetic other scope"})
 otherCollection: collection_insert(data:{organizationId:"${otherOrganization}",id:"${otherCollection}",name:"Synthetic other collection"})
}`));
ok(await raw(`mutation {
 collection_insert(data:{organizationId:"${organizationId}",id:"${childId}",name:"Synthetic child",parentId:"${collectionId}"})
}`));
const actors = [
 ['viewer','viewer',collectionId,true,true], ['operator','operator',collectionId,true,true],
 ['reviewer','reviewer',collectionId,true,true], ['manager','manager',collectionId,true,true],
 ['admin','admin',collectionId,true,true], ['child-admin','admin',childId,true,true],
 ['inactive-org','admin',collectionId,false,true], ['inactive-collection','admin',collectionId,true,false],
];
for (const [uid,role,collection,orgActive,collectionActive] of actors) {
  ok(await raw(`mutation {
   organizationMember_insert(data:{organizationId:"${organizationId}",uid:"${uid}",active:${orgActive}})
   collectionMember_insert(data:{organizationId:"${organizationId}",collectionId:"${collection}",uid:"${uid}",active:${collectionActive},role:"${role}",canViewSensitive:false})
  }`));
}
ok(await raw(`mutation {
 organizationMember_insert(data:{organizationId:"${otherOrganization}",uid:"other-admin",active:true})
 collectionMember_insert(data:{organizationId:"${otherOrganization}",collectionId:"${otherCollection}",uid:"other-admin",active:true,role:"admin",canViewSensitive:false})
}`));
const read = (actorUid, collection=collectionId, organization=organizationId) =>
  op('TenantBudgetCapsV1', {organizationId:organization, collectionId:collection, actorUid});
const set = (actorUid, collectionKey, monthlyCapMicros, collection=collectionId, organization=organizationId) =>
  op('SetTenantBudgetCapV1', {organizationId:organization, collectionId:collection, collectionKey, monthlyCapMicros, actorUid}, true);
const caps = async (actorUid='viewer') => Object.fromEntries(ok(await read(actorUid)).tenantBudgetCaps
  .map(row => [row.collectionKey, micros(row.monthlyCapMicros)]));

// Nothing is set until an administrator sets it; any active member reads the tree.
const first = ok(await read('viewer'));
assert.deepEqual(first.tenantBudgetCaps, []);
assert.deepEqual(new Map(first.collections.map(row => [row.id.replaceAll('-',''), row.parentId?.replaceAll('-','') ?? null])),
  new Map([[collectionId.replaceAll('-',''), null], [childId.replaceAll('-',''), collectionId.replaceAll('-','')]].sort()));
for (const actorUid of ['operator','reviewer','manager','admin']) ok(await read(actorUid));
ok(await read('child-admin', childId));
for (const [actorUid, collection] of [['inactive-org',collectionId],['inactive-collection',collectionId],['missing',collectionId],['admin',childId],['child-admin',collectionId]]) {
  denied(await read(actorUid, collection));
}
denied(await read('other-admin'));

// Only an active admin of the named collection of the organization sets a cap.
for (const actorUid of ['viewer','operator','reviewer','manager','inactive-org','inactive-collection','missing','other-admin']) {
  denied(await set(actorUid, 'organization', 5000000));
}
denied(await set('child-admin', 'organization', 5000000));  // Not an admin of the named collection.
assert.deepEqual(await caps(), {});
ok(await set('admin', 'organization', 5000000));
ok(await set('child-admin', childId, 1000000, childId));
const stored = ok(await read('viewer')).tenantBudgetCaps;
console.log(`INFO Int64 crosses the wire as ${typeof stored[0].monthlyCapMicros}`);
assert.deepEqual(await caps(), {organization:5000000, [childId]:1000000});

// An upsert: one row per key, replaced in place, and cleared with null.
ok(await set('admin', 'organization', 6000000));
ok(await set('admin', childId, 0));
assert.deepEqual(await caps(), {organization:6000000, [childId]:0});
ok(await set('admin', 'organization', null));
assert.deepEqual(await caps(), {organization:null, [childId]:0});
const updated = ok(await raw(`query { tenantBudgetCaps(where:{organizationId:{eq:"${organizationId}"}}) { collectionKey updatedBy } }`));
assert.deepEqual(Object.fromEntries(updated.tenantBudgetCaps.map(row => [row.collectionKey, row.updatedBy])),
  {organization:'admin', [childId]:'admin'});

// The key is the organization or one of its collections; a cap is never negative.
for (const key of ['not-a-collection', otherCollection, randomUUID(), childId.toUpperCase()]) {
  denied(await set('admin', key, 1));
}
denied(await set('admin', collectionId, -1));
denied(await set('other-admin', collectionId, 1, otherCollection, otherOrganization));
assert.deepEqual(await caps(), {organization:null, [childId]:0});

// Another organization's caps never cross over.
ok(await set('other-admin', 'organization', 7000000, otherCollection, otherOrganization));
assert.deepEqual(await caps(), {organization:null, [childId]:0});
assert.deepEqual(ok(await read('other-admin', otherCollection, otherOrganization)).tenantBudgetCaps.map(row => micros(row.monthlyCapMicros)), [7000000]);

// No client identity reaches either operation.
for (const impersonate of [{unauthenticated:true},{authClaims:{sub:'admin'}}]) {
  denied(await op('TenantBudgetCapsV1', {organizationId, collectionId, actorUid:'admin'}, false, impersonate));
  denied(await op('SetTenantBudgetCapV1', {organizationId, collectionId, collectionKey:'organization', monthlyCapMicros:1, actorUid:'admin'}, true, impersonate));
}
assert.deepEqual(await caps(), {organization:null, [childId]:0});
console.log('PASS tenant budget caps: any active member reads the organization caps and tree, only an active admin of the named collection sets one, upsert in place, null clears');
console.log('PASS tenant budget caps: key is the organization or its own collection, never negative, no cross-organization read or write, client identities denied');
