// Synthetic metadata and real SQL Connect authorization; no model or image I/O.
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

const organizationId=randomUUID(), collectionId=randomUUID();
ok(await raw(`mutation {
 organization_insert(data:{id:"${organizationId}",name:"Synthetic ledger scope"})
 collection_insert(data:{organizationId:"${organizationId}",id:"${collectionId}",name:"Synthetic ledger collection"})
}`));
const actors = [
 ['owner','reviewer',true,true,true], ['sibling','reviewer',true,true,true],
 ['operator','operator',true,true,true], ['manager','manager',true,true,true],
 ['admin','admin',true,true,true], ['viewer','viewer',true,true,true],
 ['non-sensitive-admin','admin',false,true,true],
 ['inactive-org','reviewer',true,false,true], ['inactive-collection','reviewer',true,true,false],
];
for (const [uid,role,sensitive,orgActive,collectionActive] of actors) {
  ok(await raw(`mutation {
   organizationMember_insert(data:{organizationId:"${organizationId}",uid:"${uid}",active:${orgActive}})
   collectionMember_insert(data:{organizationId:"${organizationId}",collectionId:"${collectionId}",uid:"${uid}",active:${collectionActive},role:"${role}",canViewSensitive:${sensitive}})
  }`));
}
const scope = {organizationId,collectionId,actorUid:'owner'};
const request = (kind, actorUid='owner') => ({...scope,actorUid,kind,id:randomUUID(),payload:{launch_sha256:'a'.repeat(64),runs:{}},operation:'synthetic-control',idempotencyKey:randomUUID(),requestSha256:'b'.repeat(64)});
for (const kind of ['pilot_launch','worker_cursor']) {
  const create=request(kind);
  ok(await op('CreateDocument',create,true));
  const read={...scope,kind,id:create.id};
  const original=ok(await op('GetDocument',read)).auxiliaryDocument;
  assert.equal(original.revision,1);
  assert.equal(original.createdBy,'owner');
  assert.equal(ok(await op('GetDocumentVersion',{...read,revision:1})).auxiliaryVersion.revision,1);
  for (const actorUid of ['sibling','non-sensitive-admin','inactive-org','inactive-collection','missing']) {
    denied(await op('GetDocument',{...read,actorUid}));
    denied(await op('GetDocumentVersion',{...read,actorUid,revision:1}));
    denied(await op('SaveDocument',{...create,actorUid,expectedRevision:1,idempotencyKey:randomUUID()},true));
  }
  for (const impersonate of [{unauthenticated:true},{authClaims:{sub:'owner'}}]) {
    denied(await op('GetDocument',read,false,impersonate));
    denied(await op('CreateDocument',request(kind),true,impersonate));
  }
  denied(await op('ListDocuments',{...scope,kind,limit:100,offset:0}));
  denied(await op('ListDocumentPage',{...scope,kind,cutoff:new Date().toISOString(),afterId:'',limit:100}));
  denied(await op('CreateDocument',{...request(kind),collectionId:randomUUID()},true));
  for (const actorUid of ['viewer','non-sensitive-admin','inactive-org','inactive-collection','missing']) {
    denied(await op('CreateDocument',request(kind,actorUid),true));
  }
  const save={...create,payload:{...create.payload,runs:{synthetic:{cost_micros:17}}},expectedRevision:1,idempotencyKey:randomUUID()};
  ok(await op('SaveDocument',save,true));
  denied(await op('SaveDocument',{...save,idempotencyKey:randomUUID()},true));
  assert.equal(ok(await op('GetDocument',read)).auxiliaryDocument.revision,2);
  assert.deepEqual(ok(await op('GetDocumentVersion',{...read,revision:1})).auxiliaryVersion.payload,original.payload);
  for (const actorUid of ['operator','reviewer','manager','admin']) {
    ok(await op('CreateDocument',request(kind,actorUid==='reviewer'?'owner':actorUid),true));
  }
}
denied(await op('CreateDocument',request('unchecked_control_kind'),true));
console.log('PASS pilot_launch and worker_cursor creator-only read/history/save, active scope, writer roles, sensitivity, CAS and immutable history');
console.log('PASS anonymous/client/unknown-kind/cross-collection denial and control documents excluded from both list operations');
