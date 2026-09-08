// Actual named SQL Connect operations against disposable PostgreSQL, no cloud.
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
const host=process.env.FIREBASE_DATACONNECT_EMULATOR_HOST || '127.0.0.1:9529';
assert.match(host,/^(127\.0\.0\.1|localhost):\d+$/);
const base=`http://${host}/v1/projects/demo-specimen-data/locations/us-east4/services/specimen-digitization-service`;
async function request(path,body) {
 const r=await fetch(base+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 return r.json();
}
const raw=query=>request(':executeGraphql',{query});
const op=(operationName,variables,mutation=false)=>request(`/connectors/specimen-server:impersonate${mutation?'Mutation':'Query'}`,{operationName,variables});
function ok(r){assert.ok(!r.code&&!r.errors?.length,JSON.stringify(r));return r.data;}
function denied(r){assert.ok(r.code||r.errors?.length,JSON.stringify(r));}
const organizationId=randomUUID(),collectionId=randomUUID(),actorUid='paging-worker';
const scope={organizationId,collectionId,actorUid};
ok(await raw(`mutation @transaction {
 organization_insert(data:{id:"${organizationId}",name:"Synthetic paging"})
 collection_insert(data:{organizationId:"${organizationId}",id:"${collectionId}",name:"Synthetic insects"})
 organizationMember_insert(data:{organizationId:"${organizationId}",uid:"${actorUid}",active:true})
 collectionMember_insert(data:{organizationId:"${organizationId}",collectionId:"${collectionId}",uid:"${actorUid}",active:true,role:"reviewer",canViewSensitive:true})
}`));
const ident=n=>`10000000-0000-4000-8000-${n.toString(16).padStart(12,'0')}`;
const cutoff='2026-01-01T00:00:00Z',past='2020-01-01T00:00:00Z',future='2099-01-01T00:00:00Z';
const total=10037;
for(let start=0;start<=total+20;start+=500){
 const rows=[];
 for(let n=start;n<Math.min(start+500,total+21);n++) {
  const due=n>0&&n<=total;
  rows.push(`{organizationId:"${organizationId}",collectionId:"${collectionId}",id:"${ident(n)}",revision:1,state:"${n>total?'completed':(n%3===0?'retry_scheduled':'running')}",sensitive:true,createdBy:"${actorUid}",createdAt:"${past}",workAvailableAt:${due?(n===1?'null':`"${past}"`):`"${future}"`}}`);
 }
 ok(await raw(`mutation { specimen_insertMany(data:[${rows.join(',')}]) }`));
}
console.log('PASS seeded 10037 due summary rows, legacy null schedule, and nondue rows');
const seen=new Set();let afterId='',requests=0;
while(true){
 const items=ok(await op('ListDueWork',{...scope,cutoff,afterId,limit:100})).items;
 requests++;assert.ok(items.length<=100);
 if(!items.length)break;
 for(const row of items){assert.ok(!seen.has(row.id));assert.ok(row.id>afterId);assert.ok(!('snapshot' in row));seen.add(row.id);}
 afterId=items.at(-1).id;
 if(requests===1){
  // This old row becomes eligible behind the cursor; the next sweep must see it.
  // A new insertion after the fixed cutoff must not prolong this sweep.
  ok(await raw(`mutation {
   specimen_update(key:{organizationId:"${organizationId}",collectionId:"${collectionId}",id:"${ident(0)}"},data:{workAvailableAt:"${past}"})
   specimen_insert(data:{organizationId:"${organizationId}",collectionId:"${collectionId}",id:"${ident(total+100)}",revision:1,state:"running",sensitive:true,createdBy:"${actorUid}",createdAt:"2026-02-01T00:00:00Z",workAvailableAt:"${past}"})
  }`));
 }
 // Continuously requeue the early work. ID keyset still reaches all later work.
 if(requests%20===0)ok(await raw(`mutation { specimen_update(key:{organizationId:"${organizationId}",collectionId:"${collectionId}",id:"${ident(1)}"},data:{workAvailableAt:null}) }`));
}
assert.equal(seen.size,total);assert.ok(seen.has(ident(total)));assert.ok(!seen.has(ident(0)));
assert.equal(requests,Math.ceil(total/100)+1);
const next=ok(await op('ListDueWork',{...scope,cutoff:'2026-03-01T00:00:00Z',afterId:'',limit:100})).items;
assert.equal(next[0].id,ident(0));
const tail=ok(await op('ListDueWork',{...scope,cutoff:'2026-03-01T00:00:00Z',afterId:ident(total),limit:100})).items;
assert.ok(tail.some(r=>r.id===ident(total+100)));
console.log('PASS stable keyset traverses >10k under updates, with bounded pages and no duplicate/omission; next sweep recovers late due/inserts');
for(const variables of [{...scope,actorUid:'outsider'}, {...scope,collectionId:randomUUID()}])denied(await op('ListDueWork',{...variables,cutoff,afterId:'',limit:100}));
denied(await op('ListDueWork',{...scope,cutoff,afterId:'not-a-cursor',limit:100}));
denied(await op('ListDueWork',{...scope,cutoff:future,afterId:'',limit:100}));
for(const limit of [0,101,-1])denied(await op('ListDueWork',{...scope,cutoff,afterId:'',limit}));
ok(await raw(`mutation { collectionMember_update(key:{organizationId:"${organizationId}",collectionId:"${collectionId}",uid:"${actorUid}"},data:{active:false}) }`));
denied(await op('ListDueWork',{...scope,cutoff,afterId,limit:100}));
ok(await raw(`mutation { collectionMember_update(key:{organizationId:"${organizationId}",collectionId:"${collectionId}",uid:"${actorUid}"},data:{active:true}) }`));
console.log('PASS due page scope, page bounds and mid-scan revocation checks');
const id=randomUUID(),key=randomUUID();
const create={...scope,id,snapshot:{id,version:1},snapshotSha256:'a'.repeat(64),requestSha256:'b'.repeat(64),idempotencyKey:key,operation:'create',state:'running',sensitive:true,contractVersion:'0.2',workAvailableAt:future};
ok(await op('CreateSpecimenV2',create,true));
const row=ok(await raw(`query { specimens(where:{organizationId:{eq:"${organizationId}"},collectionId:{eq:"${collectionId}"},id:{eq:"${id}"}}){workAvailableAt revision createdAt} }`)).specimens[0];
assert.ok(row.workAvailableAt.startsWith('2099-01-01'));
const beforeId=(BigInt('0x'+id.replaceAll('-',''))-1n).toString(16).padStart(32,'0').replace(/^(.{8})(.{4})(.{4})(.{4})(.{12})$/, '$1-$2-$3-$4-$5');
assert.ok(!ok(await op('ListDueWork',{...scope,cutoff:row.createdAt,afterId:beforeId,limit:100})).items.some(item=>item.id===id));
const save={...create,expectedRevision:1,action:'checkpoint',operation:'save',idempotencyKey:randomUUID(),activeRunId:null,disposition:null,workAvailableAt:past,snapshot:{id,version:2}};
const raced=await Promise.all([1,2].map(n=>op('SaveSpecimenV2',{...save,idempotencyKey:randomUUID(),snapshot:{id,version:2,winner:n}},true)));
assert.equal(raced.filter(r=>!r.code&&!r.errors?.length).length,1);
assert.ok(ok(await op('ListDueWork',{...scope,cutoff:row.createdAt,afterId:beforeId,limit:100})).items.some(item=>item.id===id));
let history=ok(await op('ListSnapshotHistory',{...scope,id,afterRevision:0,throughRevision:2,limit:1})).specimenSnapshots;
assert.equal(history.length,1);assert.equal(history[0].revision,1);assert.ok(!('snapshot' in history[0]));
const third={...save,expectedRevision:2,idempotencyKey:randomUUID(),snapshot:{id,version:3},workAvailableAt:future};
ok(await op('SaveSpecimenV2',third,true));
history=ok(await op('ListSnapshotHistory',{...scope,id,afterRevision:1,throughRevision:2,limit:100})).specimenSnapshots;
assert.deepEqual(history.map(r=>r.revision),[2]);
const saved=ok(await raw(`query { specimens(where:{organizationId:{eq:"${organizationId}"},collectionId:{eq:"${collectionId}"},id:{eq:"${id}"}}){workAvailableAt revision createdAt} }`)).specimens[0];
assert.equal(saved.revision,3);assert.ok(saved.workAvailableAt.startsWith('2099-01-01'));
denied(await op('ListSnapshotHistory',{...scope,id,afterRevision:0,throughRevision:4,limit:100}));
console.log('PASS V2 scheduling atomic with racing CAS; fixed-revision history excludes concurrent appends and raw payloads');
const cursor={...scope,id:randomUUID(),kind:'worker_cursor',payload:{cutoff,after_id:ident(total)},operation:'cursor',idempotencyKey:randomUUID(),requestSha256:'c'.repeat(64)};
ok(await op('CreateDocument',cursor,true));
assert.equal(ok(await op('GetDocument',{...scope,id:cursor.id,kind:cursor.kind})).auxiliaryDocument.payload.after_id,ident(total));
ok(await raw(`mutation { organizationMember_insert(data:{organizationId:"${organizationId}",uid:"other-worker",active:true}) collectionMember_insert(data:{organizationId:"${organizationId}",collectionId:"${collectionId}",uid:"other-worker",active:true,role:"reviewer",canViewSensitive:true}) }`));
denied(await op('GetDocument',{...scope,actorUid:'other-worker',kind:cursor.kind,id:cursor.id}));
denied(await op('SaveDocument',{...cursor,actorUid:'other-worker',expectedRevision:1,idempotencyKey:randomUUID()},true));
denied(await op('GetDocumentVersion',{...scope,actorUid:'other-worker',kind:cursor.kind,id:cursor.id,revision:1}));
denied(await op('ListDocuments',{...scope,kind:'worker_cursor',limit:100,offset:0}));
console.log('PASS persisted worker cursor is scoped/owner-only and excluded from general document listings');


const summaryPage=ok(await op('ListSpecimenPage',{...scope,cutoff,afterId:'',limit:2,includeSensitive:true})).specimens;
assert.equal(summaryPage.length,2);assert.ok(summaryPage[0].id<summaryPage[1].id);assert.ok(!('snapshot' in summaryPage[0]));
const summaryNext=ok(await op('ListSpecimenPage',{...scope,cutoff,afterId:summaryPage[1].id,limit:2,includeSensitive:true})).specimens;
assert.ok(summaryNext.every(item=>item.id>summaryPage[1].id));
const docs=[randomUUID(),randomUUID(),randomUUID()].sort();
for(const docId of docs)ok(await raw(`mutation { auxiliaryDocument_insert(data:{organizationId:"${organizationId}",collectionId:"${collectionId}",kind:"batch",id:"${docId}",revision:1,payload:{synthetic:true},createdBy:"${actorUid}",createdAt:"${past}"}) }`));
const docPage=ok(await op('ListDocumentPage',{...scope,kind:'batch',cutoff,afterId:'',limit:2})).auxiliaryDocuments;
assert.deepEqual(docPage.map(item=>item.id),docs.slice(0,2));assert.ok(!('payload' in docPage[0]));
const docTail=ok(await op('ListDocumentPage',{...scope,kind:'batch',cutoff,afterId:docs[1],limit:2})).auxiliaryDocuments;
assert.deepEqual(docTail.map(item=>item.id),docs.slice(2));
ok(await raw(`mutation { collectionMember_update(key:{organizationId:"${organizationId}",collectionId:"${collectionId}",uid:"${actorUid}"},data:{role:"operator"}) }`));
ok(await op('ListDueWork',{...scope,cutoff,afterId:'',limit:1}));
ok(await op('SaveDocument',{...cursor,expectedRevision:1,idempotencyKey:randomUUID(),payload:{cutoff,after_id:ident(total),complete:true}},true));
ok(await raw(`mutation { collectionMember_update(key:{organizationId:"${organizationId}",collectionId:"${collectionId}",uid:"${actorUid}"},data:{canViewSensitive:false}) }`));
denied(await op('ListDueWork',{...scope,cutoff,afterId:'',limit:1}));
denied(await op('ListSnapshotHistory',{...scope,id,afterRevision:0,throughRevision:3,limit:1}));
denied(await op('ListSpecimenPage',{...scope,cutoff,afterId:'',limit:1,includeSensitive:true}));
assert.deepEqual(ok(await op('ListSpecimenPage',{...scope,cutoff,afterId:'',limit:1,includeSensitive:false})).specimens,[]);
console.log('PASS scoped specimen/document metadata keysets, operator cursor compatibility, and sensitivity gates');
if(process.env.PSQL_BIN) {
 const {execFileSync}=await import('node:child_process');
 const port=process.env.SPECIMEN_TEST_PG_PORT;
 assert.match(port,/^\d+$/);
 const sql=`ANALYZE public.specimen;
 EXPLAIN (ANALYZE, FORMAT JSON) SELECT id::text COLLATE "C" AS id,revision,state,work_available_at
 FROM public.specimen WHERE organization_id='${organizationId}' AND collection_id='${collectionId}'
 AND state IN ('pending','running','retry_scheduled') AND created_at<='${cutoff}'
 AND (work_available_at<='${cutoff}' OR work_available_at IS NULL)
 AND id::text COLLATE "C">'${ident(total-10)}' ORDER BY id LIMIT 100;`;
 const output=execFileSync(process.env.PSQL_BIN,['-h','127.0.0.1','-p',port,'-d','specimen-digitization-database','-qAt','-v','ON_ERROR_STOP=1','-c',sql],{encoding:'utf8'});
 const plan=JSON.parse(output)[0];
 assert.ok(JSON.stringify(plan).includes('specimen_text_cursor'));
 console.log('PASS equivalent scoped late-page SQL uses text-cursor index (not a production latency claim)');
}
