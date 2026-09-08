// Synthetic-only integration harness. Never contacts a cloud endpoint.
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
const host = process.env.FIREBASE_DATACONNECT_EMULATOR_HOST || '127.0.0.1:9499';
assert.match(host, /^(127\.0\.0\.1|localhost):\d+$/);
const base = `http://${host}/v1/projects/demo-specimen-data/locations/us-east4/services/specimen-digitization-service`;
async function call(path, body) {
  const response = await fetch(base + path, {method:'POST', headers:{'Content-Type':'application/json', 'Authorization':'Bearer owner'}, body:JSON.stringify(body)});
  const result = await response.json();
  return result;
}
const raw = query => call(':executeGraphql', {query});
const op = (operationName, variables, mutation=false, impersonate) => call(`/connectors/specimen-server:impersonate${mutation?'Mutation':'Query'}`, {operationName,variables,extensions: {impersonate}});
function ok(r) { assert.ok(!r.errors?.length && !r.code, JSON.stringify(r)); return r.data; }
function denied(r) { assert.ok(r.errors?.length || r.code, JSON.stringify(r)); }
const org=randomUUID(), collection=randomUUID(), id=randomUUID();
ok(await raw(`mutation @transaction {
 organization_insert(data:{id:"${org}",name:"Synthetic museum"})
 collection_insert(data:{organizationId:"${org}",id:"${collection}",name:"Synthetic insects"})
 organizationMember_insert(data:{organizationId:"${org}",uid:"reviewer",active:true})
 collectionMember_insert(data:{organizationId:"${org}",collectionId:"${collection}",uid:"reviewer",active:true,role:"reviewer",canViewSensitive:true})
}`));
const scope={organizationId:org,collectionId:collection,actorUid:'reviewer'};
const create={...scope,id,snapshot:{id,version:1,literal:'unchanged'},snapshotSha256:'a'.repeat(64),requestSha256:'b'.repeat(64),idempotencyKey:randomUUID(),operation:'create',state:'pending',sensitive:true,contractVersion:'v1'};
assert.equal(ok(await op('GetReceipt',{...scope,operation:'create',idempotencyKey:create.idempotencyKey})).requestReceipt,null);
ok(await op('CreateSpecimen',create,true));
console.log('PASS create transaction');
const duplicateId=randomUUID();
denied(await op('CreateSpecimen',{...create,id:duplicateId},true));
assert.equal(ok(await op('GetSpecimen',{...scope,id:duplicateId})).specimen,null);
console.log('PASS duplicate receipt rolls back newly inserted specimen');

assert.equal(ok(await op('GetSpecimen',{...scope,id})).specimenSnapshots[0].snapshot.literal,'unchanged');
const save={...create,expectedRevision:1,idempotencyKey:randomUUID(),operation:'save',action:'checkpoint',snapshot:{id,version:2,literal:'unchanged'},state:'processing_blocked',activeRunId:null,disposition:null};
ok(await op('SaveSpecimen',save,true));
assert.equal(ok(await op('GetSpecimen',{...scope,id})).specimen.revision,2);
assert.equal(ok(await op('GetSnapshot',{...scope,id,revision:1})).specimenSnapshot.snapshot.version,1);
console.log('PASS CAS save and immutable prior snapshot');
denied(await op('SaveSpecimen',{...save,idempotencyKey:randomUUID()},true));
assert.equal(ok(await op('GetSpecimen',{...scope,id})).specimen.revision,2);
console.log('PASS stale write rolls back');
denied(await op('GetSpecimen',{...scope,id,actorUid:'outsider'}));
denied(await op('CreateSpecimen',{...create,id:randomUUID(),actorUid:'outsider'},true));
console.log('PASS unauthorized read/write');
const receipt=ok(await op('GetReceipt',{...scope,operation:'save',idempotencyKey:save.idempotencyKey})).requestReceipt;
assert.equal(receipt.revision,2);
assert.equal(receipt.requestSha256,save.requestSha256);
console.log('PASS idempotency receipt committed with snapshot');
denied(await op('GetSpecimen',{...scope,id},false,{unauthenticated:true}));
denied(await op('GetSpecimen',{...scope,id},false,{authClaims:{sub:'reviewer'}}));
console.log('PASS client access denied, including valid user');
const invalid={...save,expectedRevision:2,idempotencyKey:randomUUID(),state:'processing_blocked',disposition:'deferred'};
denied(await op('SaveSpecimen',invalid,true));
denied(await op('SaveSpecimen',{...invalid,state:'completed',disposition:'failed'},true));
assert.equal(ok(await op('GetSpecimen',{...scope,id})).specimen.revision,2);
console.log('PASS operational blocks cannot carry final disposition; invalid final queue rejected');
const doc={...scope,kind:'upload',id:randomUUID(),payload:{offset:0},operation:'upload_create',idempotencyKey:randomUUID(),requestSha256:'c'.repeat(64)};
ok(await op('CreateDocument',doc,true));
ok(await op('SaveDocument',{...doc,expectedRevision:1,payload:{offset:1024},idempotencyKey:randomUUID()},true));
assert.equal(ok(await op('GetDocument',{...scope,kind:'upload',id:doc.id})).auxiliaryDocument.payload.offset,1024);
assert.equal(ok(await op('GetDocumentVersion',{...scope,kind:'upload',id:doc.id,revision:1})).auxiliaryVersion.payload.offset,0);
denied(await op('SaveDocument',{...doc,expectedRevision:1,idempotencyKey:randomUUID()},true));
console.log('PASS upload metadata resume/CAS/history');
const raced=await Promise.all([1,2].map(n=>op('SaveSpecimen',{...save,expectedRevision:2,idempotencyKey:randomUUID(),snapshot:{id,version:3,winner:n}},true)));
assert.equal(raced.filter(r=>!r.code&&!r.errors?.length).length,1);
assert.equal(ok(await op('GetSpecimen',{...scope,id})).specimen.revision,3);
console.log('PASS concurrent writers yield one successful CAS');
const events=ok(await raw(`query { auditEvents(where:{organizationId:{eq:"${org}"},collectionId:{eq:"${collection}"},specimenId:{eq:"${id}"}}) { revision } outboxEvents(where:{organizationId:{eq:"${org}"},collectionId:{eq:"${collection}"},specimenId:{eq:"${id}"}}) { aggregateRevision } }`));
assert.equal(events.auditEvents.length,3); assert.equal(events.outboxEvents.length,3);
console.log('PASS one audit and outbox per committed revision, none for rejected CAS');
ok(await raw(`mutation { collectionMember_update(key:{organizationId:"${org}",collectionId:"${collection}",uid:"reviewer"},data:{canViewSensitive:false}) }`));
denied(await op('GetSpecimen',{...scope,id}));
assert.deepEqual(ok(await op('ListSpecimens',{...scope,limit:20,offset:0,includeSensitive:false})).specimens,[]);
denied(await op('ListSpecimens',{...scope,limit:20,offset:0,includeSensitive:true}));
console.log('PASS sensitive record read/list gates');
ok(await raw(`mutation { organizationMember_update(key:{organizationId:"${org}",uid:"reviewer"},data:{active:false}) }`));
denied(await op('GetReceipt',{...scope,operation:'save',idempotencyKey:save.idempotencyKey}));
console.log('PASS organization revocation rechecked');
ok(await raw(`mutation { organizationMember_update(key:{organizationId:"${org}",uid:"reviewer"},data:{active:true}) collectionMember_update(key:{organizationId:"${org}",collectionId:"${collection}",uid:"reviewer"},data:{canViewSensitive:true}) }`));
if(process.env.DATA_RESTART_PROOF) {
 const {writeFile}=await import('node:fs/promises');
 await writeFile(process.env.DATA_RESTART_PROOF,JSON.stringify({scope,id}));
}
const assetId=randomUUID(), profileId=randomUUID(), runId=randomUUID(), regionId=randomUUID();
const asset={...scope,id:assetId,specimenId:id,kind:'original',parentAssetId:null,bucket:'demo-specimen-data.appspot.com',objectName:`originals/${assetId}`,generation:'1',sha256:'d'.repeat(64),mimeType:'image/png',byteSize:'4',width:1,height:1,acquisitionMethod:'fixture',uploaderUid:'reviewer'};
ok(await op('AppendSourceAsset',asset,true));
ok(await op('AppendProfileVersion',{...scope,id:profileId,profileKey:'synthetic',version:'1',configObject:'profiles/synthetic',configSha256:'e'.repeat(64),approvedBy:null},true));
ok(await op('AppendPipelineRun',{...scope,id:runId,specimenId:id,profileVersionId:profileId,supersedesRunId:null,pinnedVersions:{profile:'1',code:'fixture'},inputSha256:'d'.repeat(64)},true));
ok(await op('AppendLabelRegion',{...scope,id:regionId,runId,sourceAssetId:assetId,cropAssetId:assetId,geometry:{bbox:[0,0,1,1]},ordinal:0,regionType:'label',segmentationVersion:'synthetic-only',supersedesRegionId:null},true));
const observation={...scope,id:randomUUID(),runId,regionId,rawAssetId:assetId,stepKey:'read-1',provider:'synthetic',modelVersion:'fixture1',promptVersion:'1',inputSha256:'d'.repeat(64),parameters:{},literalText:'literal evidence',outcome:'success',independent:true};
ok(await op('AppendModelObservation',observation,true));
denied(await op('AppendModelObservation',{...observation,id:randomUUID()},true));
denied(await op('AppendSourceAsset',{...asset,id:randomUUID()},true));
const rows=ok(await raw(`query { modelObservations(where:{organizationId:{eq:"${org}"},collectionId:{eq:"${collection}"},runId:{eq:"${runId}"}}) { literalText } }`));
assert.equal(rows.modelObservations.length,1);
assert.equal(rows.modelObservations[0].literalText,'literal evidence');
console.log('PASS normalized immutable asset/run/region/observation chain and logical-step/object uniqueness');
// A collection member cannot attach an asset to a specimen from a different scope.
const otherCollection=randomUUID();
ok(await raw(`mutation { collection_insert(data:{organizationId:"${org}",id:"${otherCollection}",name:"Other synthetic collection"}) collectionMember_insert(data:{organizationId:"${org}",collectionId:"${otherCollection}",uid:"reviewer",active:true,role:"reviewer",canViewSensitive:true}) }`));
denied(await op('AppendSourceAsset',{...asset,id:randomUUID(),collectionId:otherCollection,objectName:randomUUID()},true));
console.log('PASS composite foreign key rejects cross-collection specimen reference');
