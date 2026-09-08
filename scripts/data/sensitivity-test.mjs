// Explicit synthetic classifications only; no cloud resources or image bytes.
import assert from 'node:assert/strict';
import {createHash,randomUUID} from 'node:crypto';
const host=process.env.FIREBASE_DATACONNECT_EMULATOR_HOST;
assert.match(host || '',/^127\.0\.0\.1:[0-9]{1,5}$/);
const base=`http://${host}/v1/projects/demo-specimen-data/locations/us-east4/services/specimen-digitization-service`;
async function call(path,body) {
 const response=await fetch(base+path,{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer owner'},body:JSON.stringify(body)});
 return response.json();
}
const raw=query=>call(':executeGraphql',{query});
const op=(operationName,variables,mutation=false,impersonate)=>call(`/connectors/specimen-server:impersonate${mutation?'Mutation':'Query'}`,{operationName,variables,extensions:{impersonate}});
const ok=r=>{assert.ok(!r.code&&!r.errors?.length,JSON.stringify(r));return r.data;};
const denied=r=>{
 assert.ok(r.code||r.errors?.length,JSON.stringify(r));
 assert.ok(!r.errors?.some(error=>error.extensions?.code==='INVALID_ARGUMENT'),JSON.stringify(r));
};
const organizationId=randomUUID(),collectionId=randomUUID();
ok(await raw(`mutation {organization_insert(data:{id:"${organizationId}",name:"Synthetic sensitivity"}) collection_insert(data:{organizationId:"${organizationId}",id:"${collectionId}",name:"Synthetic sensitivity"})}`));
for (const [uid,role,sensitive] of [['ordinary','admin',false],['privileged','admin',true],['sibling','reviewer',false],['viewer','viewer',false]]) {
 ok(await raw(`mutation {organizationMember_insert(data:{organizationId:"${organizationId}",uid:"${uid}",active:true}) collectionMember_insert(data:{organizationId:"${organizationId}",collectionId:"${collectionId}",uid:"${uid}",active:true,role:"${role}",canViewSensitive:${sensitive}})}`));
}
const scope={organizationId,collectionId,actorUid:'ordinary'};
const document=(kind,sensitive=false,actorUid='ordinary')=>({...scope,actorUid,kind,id:randomUUID(),sensitive,payload:{sensitive,synthetic:true},operation:'synthetic-sensitivity',idempotencyKey:randomUUID(),requestSha256:'a'.repeat(64)});
const receipt=create=>({...scope,actorUid:create.actorUid,operation:create.operation,idempotencyKey:create.idempotencyKey});
const read=create=>({...scope,actorUid:create.actorUid,kind:create.kind,id:create.id});
for(const kind of ['batch','upload','pilot_launch','worker_cursor']) {
 const create=document(kind);
 ok(await op('CreateDocumentV2',create,true));
 assert.equal(ok(await op('GetDocumentV2',read(create))).auxiliaryDocument.sensitive,false);
 assert.equal(ok(await op('GetDocumentVersionV2',{...read(create),revision:1})).auxiliaryVersion.document.sensitive,false);
 assert.equal(ok(await op('GetDocumentReceiptV2',receipt(create))).auxiliaryReceipt.document.sensitive,false);
 const control=['pilot_launch','worker_cursor'].includes(kind);
 for(const operation of ['GetDocumentV2','GetDocumentVersionV2']) {
  const result=await op(operation,{...read(create),actorUid:'sibling',...(operation.includes('Version')?{revision:1}:{})});
  if(control)denied(result);else ok(result);
 }
 if(control)denied(await op('SaveDocumentV2',{...create,actorUid:'sibling',expectedRevision:1,idempotencyKey:randomUUID()},true));
 for(const impersonate of [{unauthenticated:true},{authClaims:{sub:'ordinary'}}]) {
  denied(await op('GetDocumentV2',read(create),false,impersonate));
  denied(await op('CreateDocumentV2',document(kind),true,impersonate));
 }
 denied(await op('CreateDocumentV2',document(kind,true),true));
 denied(await op('CreateDocumentV2',document(kind,false,'viewer'),true));
 denied(await op('CreateDocumentV2',{...document(kind),collectionId:randomUUID()},true));
 for(const value of [true,null,0,'false']) {
  denied(await op('CreateDocumentV2',{...document(kind),payload:{sensitive:value}},true));
 }
 denied(await op('CreateDocumentV2',{...document(kind),payload:{synthetic:true}},true));
 const save={...create,expectedRevision:1,payload:{...create.payload,saved:true},idempotencyKey:randomUUID()};
 ok(await op('SaveDocumentV2',save,true));
 denied(await op('SaveDocumentV2',{...save,idempotencyKey:randomUUID()},true));
 denied(await op('SaveDocumentV2',{...save,expectedRevision:2,sensitive:true,payload:{sensitive:true},idempotencyKey:randomUUID()},true));
 assert.equal(ok(await op('GetDocumentV2',read(create))).auxiliaryDocument.revision,2);
 assert.equal(ok(await op('GetDocumentVersionV2',{...read(create),revision:1})).auxiliaryVersion.payload.saved,undefined);
 for(const operation of ['ListDocumentsV2','ListDocumentPageV2']) {
  const vars={...scope,kind,includeSensitive:false,limit:100,...(operation==='ListDocumentsV2'?{offset:0}:{cutoff:new Date().toISOString(),afterId:''})};
  const result=await op(operation,vars);
  if(control)denied(result);else assert.ok(ok(result).auxiliaryDocuments.some(row=>row.id.replaceAll('-','')===create.id.replaceAll('-','')),JSON.stringify({operation,result,expected:create.id}));
  denied(await op(operation,{...vars,includeSensitive:true}));
 }
 // Privileged-owned controls permit promotion by their creator; ordinary docs
 // allow a scoped privileged writer to promote. No one can downgrade afterward.
 const promoted=control?document(kind,false,'privileged'):create;
 if(control)ok(await op('CreateDocumentV2',promoted,true));
 ok(await op('SaveDocumentV2',{...promoted,actorUid:'privileged',sensitive:true,payload:{sensitive:true},expectedRevision:control?1:2,idempotencyKey:randomUUID()},true));
 const latestRevision=control?2:3;
 denied(await op('SaveDocumentV2',{...promoted,actorUid:'privileged',sensitive:false,payload:{sensitive:false},expectedRevision:latestRevision,idempotencyKey:randomUUID()},true));
 for(const operation of ['GetDocumentV2','GetDocumentVersionV2']) {
  denied(await op(operation,{...read(promoted),actorUid:'ordinary',...(operation.includes('Version')?{revision:1}:{})}));
 }
 if(!control)denied(await op('GetDocumentReceiptV2',receipt(create)));
 if(!control) {
  for(const operation of ['ListDocumentsV2','ListDocumentPageV2']) {
   const vars={...scope,kind,includeSensitive:false,limit:100,...(operation==='ListDocumentsV2'?{offset:0}:{cutoff:new Date().toISOString(),afterId:''})};
   assert.ok(ok(await op(operation,vars)).auxiliaryDocuments.every(row=>row.id.replaceAll('-','')!==create.id.replaceAll('-','')));
  }
 }
 const legacy=document(kind,true,'privileged'); delete legacy.sensitive; delete legacy.payload.sensitive;
 ok(await op('CreateDocument',legacy,true));
 assert.equal(ok(await op('GetDocumentV2',read(legacy))).auxiliaryDocument.sensitive,true);
 denied(await op('GetDocumentV2',{...read(legacy),actorUid:'ordinary'}));
 denied(await op('CreateDocument',{...legacy,id:randomUUID(),idempotencyKey:randomUUID(),payload:{sensitive:false}},true));
 denied(await op('SaveDocument',{...legacy,expectedRevision:1,idempotencyKey:randomUUID(),payload:{sensitive:false}},true));
 assert.equal(ok(await op('GetDocumentV2',read(legacy))).auxiliaryDocument.revision,1);
}
denied(await op('CreateDocumentV2',document('unchecked_kind'),true));
console.log('PASS explicit non-sensitive auxiliary intake/control metadata, immutable history, filtered lists and creator-only controls');
console.log('PASS legacy defaults sensitive, payload/column binding, no downgrade, active scope/role/client/sensitivity/CAS denials');

const protectedDoc=document('batch');
ok(await op('CreateDocumentV2',protectedDoc,true));
for(const table of ['organizationMember','collectionMember']) {
 const memberKey={organizationId,uid:'ordinary',...(table==='collectionMember'?{collectionId}:{})};
 const key=Object.entries(memberKey).map(([name,value])=>`${name}:"${value}"`).join(',');
 ok(await raw(`mutation {${table}_update(key:{${key}},data:{active:false})}`));
 denied(await op('GetDocumentV2',read(protectedDoc)));
 denied(await op('GetDocumentVersionV2',{...read(protectedDoc),revision:1}));
 denied(await op('GetDocumentReceiptV2',receipt(protectedDoc)));
 denied(await op('SaveDocumentV2',{...protectedDoc,expectedRevision:1,idempotencyKey:randomUUID()},true));
 denied(await op('ListDocumentsV2',{...scope,kind:'batch',includeSensitive:false,limit:100,offset:0}));
 ok(await raw(`mutation {${table}_update(key:{${key}},data:{active:true})}`));
}
console.log('PASS new metadata reads/history/receipts/lists/writes recheck revocation at both membership levels');

function specimenRequest(sensitive,actorUid='privileged') {
 const id=randomUUID(),checksum=createHash('sha256').update(id).digest('hex');
 return {...scope,actorUid,id,sensitive,snapshot:{id,asset:{sha256:checksum,...(sensitive?{}:{sensitive:false})}},sourceChecksum:checksum,
  snapshotSha256:'c'.repeat(64),requestSha256:'d'.repeat(64),idempotencyKey:randomUUID(),operation:'synthetic-create',state:'running',contractVersion:'0.1',workAvailableAt:null};
}
const savedVars=(request,sensitive,expectedRevision=1)=>({...request,sensitive,expectedRevision,activeRunId:null,disposition:null,action:'synthetic-save',operation:'synthetic-save',idempotencyKey:randomUUID()});
function specimenOp(operation, input) {
 const variables={...input};
 if(operation!=='CreateSpecimenV3')delete variables.sourceChecksum;
 if(!operation.endsWith('V2')&&!operation.endsWith('V3'))delete variables.workAvailableAt;
 return op(operation,variables,true);
}
for(const operation of ['CreateSpecimen','CreateSpecimenV2','CreateSpecimenV3']) {
 ok(await specimenOp(operation,specimenRequest(false,'ordinary')));
 ok(await specimenOp(operation,specimenRequest(true)));
 const unknown=specimenRequest(false); delete unknown.snapshot.asset.sensitive;
 denied(await specimenOp(operation,unknown));
 for(const declared of [true,null,0,'false']) {
  const mismatch=specimenRequest(false);mismatch.snapshot.asset.sensitive=declared;
  denied(await specimenOp(operation,mismatch));
 }
}
for(const operation of ['SaveSpecimen','SaveSpecimenV2','SaveSpecimenV3']) {
 const legacy=specimenRequest(true);
 ok(await op('CreateSpecimenV3',legacy,true));
 const downgrade=savedVars(legacy,false);downgrade.snapshot={...legacy.snapshot,asset:{...legacy.snapshot.asset,sensitive:false}};
 denied(await specimenOp(operation,downgrade));
 const wrong=savedVars(legacy,true);wrong.snapshot={...legacy.snapshot,asset:{...legacy.snapshot.asset,sensitive:false}};
 denied(await specimenOp(operation,wrong));
 const ordinary=specimenRequest(false,'ordinary');
 ok(await op('CreateSpecimenV3',ordinary,true));
 ok(await specimenOp(operation,savedVars(ordinary,false)));
 const get={...scope,id:ordinary.id};
 assert.equal(ok(await op('GetSpecimen',get)).specimen.sensitive,false);
 assert.equal(ok(await op('GetSnapshot',{...get,revision:1})).specimenSnapshot.snapshot.asset.sensitive,false);
 assert.equal(ok(await op('ListSnapshotHistory',{...get,afterRevision:0,throughRevision:2,limit:100})).specimenSnapshots.length,2);
 const promote=savedVars(ordinary,true,2);promote.actorUid='privileged';promote.snapshot={...ordinary.snapshot,asset:{...ordinary.snapshot.asset,sensitive:true}};
 ok(await specimenOp(operation,promote));
 denied(await op('GetSnapshot',{...get,revision:1}));
 denied(await op('ListSnapshotHistory',{...get,afterRevision:0,throughRevision:3,limit:100}));
 denied(await specimenOp(operation,{...savedVars(ordinary,false,3),actorUid:'privileged'}));
}
console.log('PASS all named specimen versions bind explicit classification, reject legacy downgrade and protect history after promotion');
