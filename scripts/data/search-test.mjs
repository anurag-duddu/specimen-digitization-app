// Named server connector operations against real disposable PostgreSQL.
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {execFileSync} from 'node:child_process';
const host=process.env.FIREBASE_DATACONNECT_EMULATOR_HOST || '127.0.0.1:9549';
assert.match(host,/^(127\.0\.0\.1|localhost):\d+$/);
const base=`http://${host}/v1/projects/demo-specimen-data/locations/us-east4/services/specimen-digitization-service`;
async function request(path,body){return (await fetch(base+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})).json();}
const raw=query=>request(':executeGraphql',{query});
const op=variables=>request('/connectors/specimen-server:impersonateQuery',{operationName:'SearchSpecimens',variables});
function ok(r){assert.ok(!r.code&&!r.errors?.length,JSON.stringify(r));return r.data;}
function denied(r){assert.ok(r.code||r.errors?.length,JSON.stringify(r));}
const organizationId=randomUUID(),collectionId=randomUUID(),actorUid='search-reviewer';
const scope={organizationId,collectionId,actorUid};
const past='2020-01-01T00:00:00Z',nextDay='2020-01-02T00:00:00Z',cutoff='2026-01-01T00:00:00Z';
const first={...scope,cutoff,afterCreatedAt:null,afterId:'',limit:100,includeSensitive:true};
const search=async filters=>ok(await op({...first,...filters})).items;
const ident=n=>`20000000-0000-4000-8000-${n.toString(16).padStart(12,'0')}`;
ok(await raw(`mutation @transaction {
 organization_insert(data:{id:"${organizationId}",name:"Synthetic search"})
 collection_insert(data:{organizationId:"${organizationId}",id:"${collectionId}",name:"Search insects"})
 organizationMember_insert(data:{organizationId:"${organizationId}",uid:"${actorUid}",active:true})
 collectionMember_insert(data:{organizationId:"${organizationId}",collectionId:"${collectionId}",uid:"${actorUid}",active:true,role:"reviewer",canViewSensitive:true})
}`));
const count=2037;
// Use parameter-free locally generated SQL to seed realistic immutable histories
// efficiently; all values originate here and no network credentials are used.
const psql=sql=>execFileSync(process.env.PSQL_BIN||'/opt/homebrew/opt/postgresql@18/bin/psql',['-h','127.0.0.1','-p',process.env.SPECIMEN_TEST_PG_PORT||'5599','-d','specimen-digitization-database','-v','ON_ERROR_STOP=1','-At'],{input:sql,encoding:'utf8',maxBuffer:4*1024*1024});
const q=s=>"'"+s.replaceAll("'","''")+"'";
const payload=n=>({id:ident(n),version:2,batch_id:n%2?'batch-b':'batch-a',created_at:'1999-01-01T00:00:00Z',asset:{id:`asset-${n}`,filename:`label-${n}.jpg`,uploader:n%3?'other':'uploader-a'},run:{id:`run-${n}`,stage:n%2?'classify':'finalized',profile:{id:'profile-a',version:n%3?'v2':'v1',synthetic:true},reasons:n%5?[]:['reason-a'],blocker:n%7?null:'blocker-a',review_risk:n%4===0?null:{composite:n%4===1?0:n%4===2?75:'75'}}});
for(let start=0;start<count;start+=100){
 const summaries=[],snapshots=[];
 for(let n=start;n<Math.min(start+100,count);n++){
  summaries.push(`('${organizationId}','${collectionId}','${ident(n)}',2,'${n%2?'running':'completed'}',${n%2?'NULL':"'cleared'"},${n%11===0},'${actorUid}','${n<1000?past:nextDay}','${past}')`);
  for(const revision of [1,2]){const p=payload(n);if(revision===1){p.batch_id='historical-only';p.run.review_risk={composite:99};}snapshots.push(`('${organizationId}','${collectionId}','${ident(n)}',${revision},'0.2',${q(JSON.stringify(p))}::jsonb,'${'a'.repeat(64)}','${past}')`);}
 }
 psql(`INSERT INTO specimen (organization_id,collection_id,id,revision,state,disposition,sensitive,created_by,created_at,updated_at) VALUES ${summaries}; INSERT INTO specimen_snapshot (organization_id,collection_id,specimen_id,revision,contract_version,snapshot,sha256,created_at) VALUES ${snapshots};`);
}
let rows=await search({limit:3});assert.equal(rows.length,3);assert.equal(rows[0].synthetic,true);assert.ok(rows[0].createdAt.startsWith('2020-01-01'));assert.equal(rows[0].activeRunId,'run-0');assert.equal(rows[0].domainCreatedAt,'1999-01-01T00:00:00Z');assert.ok(!('snapshot' in rows[0]));
assert.equal((await search({batchId:'historical-only'})).length,0);
const checks=[['batchId','batch-a',n=>n%2===0],['uploader','uploader-a',n=>n%3===0],['status','completed',n=>n%2===0],['stage','classify',n=>n%2===1],['disposition','cleared',n=>n%2===0],['profileVersion','v1',n=>n%3===0],['reasonCode','reason-a',n=>n%5===0],['blocker','blocker-a',n=>n%7===0],['riskMin',50,n=>n%4===2],['riskMax',0,n=>n%4===1]];
for(const [key,value,predicate] of checks){rows=await search({[key]:value});assert.equal(rows.length,100,key);for(const r of rows)assert.ok(predicate(parseInt(r.id.slice(-12),16)),key);}
for(const [key,value] of [['specimenId',ident(42)],['assetId','asset-42'],['activeRunId','run-42']])assert.deepEqual((await search({[key]:value})).map(r=>r.id),[ident(42)]);
rows=await search({batchId:'batch-a',uploader:'uploader-a',reasonCode:'reason-a',profileId:'profile-a',profileVersion:'v1',riskMin:75,riskMax:75});
assert.ok(rows.length>0);for(const r of rows)assert.equal(parseInt(r.id.slice(-12),16)%30,0);
assert.equal((await search({profileId:'absent'})).length,0);
assert.deepEqual(await search({batchId:null,reasonCode:null,createdFrom:null,riskMin:null}),await search({}));
assert.equal((await search({createdFrom:nextDay}))[0].id,ident(1000));
assert.ok((await search({createdBefore:nextDay})).every(r=>r.createdAt.startsWith('2020-01-01')));
assert.equal((await search({createdBefore:past})).length,0);
for(const n of [0,1,2,3])assert.equal((await search({specimenId:ident(n)}))[0].risk,[null,0,75,null][n]);
console.log('PASS persisted fields, exact current revision, AND filters, typed timestamp boundaries and nullable numeric risk');
// A committed insert after cutoff cannot extend this page sequence.
const laterId=ident(count+1);
const insertLater=()=>psql(`INSERT INTO specimen (organization_id,collection_id,id,revision,state,sensitive,created_by,created_at,updated_at) VALUES ('${organizationId}','${collectionId}','${laterId}',2,'running',false,'${actorUid}','2026-02-01T00:00:00Z','2026-02-01T00:00:00Z'); INSERT INTO specimen_snapshot (organization_id,collection_id,specimen_id,revision,contract_version,snapshot,sha256,created_at) VALUES ('${organizationId}','${collectionId}','${laterId}',2,'0.2',${q(JSON.stringify(payload(count+1)))}::jsonb,'${'b'.repeat(64)}','2026-02-01T00:00:00Z');`);
let cursor={},seen=new Set();
while(true){rows=await search({...cursor,batchId:'batch-a',limit:37});if(!rows.length)break;for(const r of rows){assert.ok(!seen.has(r.id));seen.add(r.id);}if(seen.size===37)insertLater();cursor={afterCreatedAt:rows.at(-1).createdAt,afterId:rows.at(-1).id};}
assert.equal(seen.size,Math.ceil(count/2));assert.ok(seen.has(ident(count-1)));assert.ok(!seen.has(laterId));
assert.deepEqual((await search({specimenId:laterId,cutoff:'2026-03-01T00:00:00Z'})).map(r=>r.id),[laterId]);
// A new current revision changes membership immediately, without rewriting old snapshots.
psql(`INSERT INTO specimen_snapshot (organization_id,collection_id,specimen_id,revision,contract_version,snapshot,sha256,created_at) SELECT organization_id,collection_id,specimen_id,3,contract_version,jsonb_set(snapshot,'{batch_id}','"changed-current"'::jsonb),sha256,created_at FROM specimen_snapshot WHERE organization_id='${organizationId}' AND collection_id='${collectionId}' AND specimen_id='${ident(0)}' AND revision=2; UPDATE specimen SET revision=3 WHERE organization_id='${organizationId}' AND collection_id='${collectionId}' AND id='${ident(0)}';`);
assert.equal((await search({specimenId:ident(0),batchId:'batch-a'})).length,0);
assert.equal((await search({batchId:'changed-current'}))[0].revision,3);
assert.ok((await search({includeSensitive:false})).every(r=>!r.sensitive));
for(const filters of [{actorUid:'outsider'},{collectionId:randomUUID()},{limit:101},{riskMin:101},{riskMin:80,riskMax:20},{afterId:ident(1)},{afterCreatedAt:past},{createdFrom:nextDay,createdBefore:past}])denied(await op({...first,...filters}));
psql(`UPDATE collection_member SET can_view_sensitive=false WHERE organization_id='${organizationId}' AND collection_id='${collectionId}' AND uid='${actorUid}'`);
denied(await op(first));assert.ok((await search({includeSensitive:false})).every(r=>!r.sensitive));
psql(`UPDATE collection_member SET active=false WHERE organization_id='${organizationId}' AND collection_id='${collectionId}' AND uid='${actorUid}'`);
denied(await op({...first,...cursor,includeSensitive:false}));
console.log('PASS composite keyset across timestamp ties, scope, sensitivity and mid-page revocation');
psql('ANALYZE specimen; ANALYZE specimen_snapshot;');
const plan=psql(`EXPLAIN (ANALYZE, FORMAT JSON) SELECT s.id,s.created_at,v.snapshot #>> '{asset,filename}' FROM specimen s JOIN specimen_snapshot v ON v.organization_id=s.organization_id AND v.collection_id=s.collection_id AND v.specimen_id=s.id AND v.revision=s.revision WHERE s.organization_id='${organizationId}' AND s.collection_id='${collectionId}' AND s.created_at<='${cutoff}' AND (s.created_at > '${nextDay}' OR (s.created_at = '${nextDay}' AND s.id::text COLLATE "C" > '${ident(1900)}')) ORDER BY s.created_at,s.id::text COLLATE "C" LIMIT 37`);
assert.match(plan,/specimen_search_cursor/,'scoped date cursor index must be present and selected');console.log('PASS measured scoped composite cursor index with current snapshot join');

const batchPlan=psql(`EXPLAIN (ANALYZE, FORMAT JSON) SELECT s.id FROM specimen s JOIN specimen_snapshot v ON v.organization_id=s.organization_id AND v.collection_id=s.collection_id AND v.specimen_id=s.id AND v.revision=s.revision WHERE s.organization_id='${organizationId}' AND s.collection_id='${collectionId}' AND v.snapshot #>> '{batch_id}' = 'changed-current' ORDER BY s.created_at,s.id::text COLLATE "C" LIMIT 37`);
assert.match(batchPlan,/snapshot_search_batch/);console.log('PASS selective persisted batch expression index with exact revision join');
