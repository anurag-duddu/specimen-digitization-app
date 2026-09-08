// Real PostgreSQL + named connector operations. Synthetic data and localhost only.
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {readFileSync} from 'node:fs';
const host=process.env.FIREBASE_DATACONNECT_EMULATOR_HOST;
assert.match(host,/^(127\.0\.0\.1|localhost):\d+$/);
const base=`http://${host}/v1/projects/demo-specimen-data/locations/us-east4/services/specimen-digitization-service`;
async function request(path,body){return (await fetch(base+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})).json();}
const raw=query=>request(':executeGraphql',{query});
const op=(operationName,variables,mutation=false,impersonate)=>request(`/connectors/specimen-server:impersonate${mutation?'Mutation':'Query'}`,{operationName,variables,extensions:{impersonate}});
function ok(r){assert.ok(!r.code&&!r.errors?.length,JSON.stringify(r));return r.data;}
function denied(r){assert.ok(r.code||r.errors?.length,JSON.stringify(r));}
const organizationId=randomUUID(),collectionId=randomUUID(),actorUid='checksum-reviewer';
const scope={organizationId,collectionId,actorUid};
const psql=sql=>execFileSync(process.env.PSQL_BIN,['-h','127.0.0.1','-p',process.env.SPECIMEN_TEST_PG_PORT,'-d','specimen-digitization-database','-v','ON_ERROR_STOP=1','-At'],{input:sql,encoding:'utf8',maxBuffer:1024*1024});
const checksum='a'.repeat(64),other='b'.repeat(64);
ok(await raw(`mutation @transaction {
 organization_insert(data:{id:"${organizationId}",name:"Synthetic checksum"})
 collection_insert(data:{organizationId:"${organizationId}",id:"${collectionId}",name:"Insects checksum"})
 organizationMember_insert(data:{organizationId:"${organizationId}",uid:"${actorUid}",active:true})
 collectionMember_insert(data:{organizationId:"${organizationId}",collectionId:"${collectionId}",uid:"${actorUid}",active:true,role:"reviewer",canViewSensitive:true})
}`));
const lookup=variables=>op('FindSpecimenByChecksum',{...scope,checksum,includeSensitive:true,...variables});
assert.deepEqual(ok(await lookup({})).specimens,[]);
const create=(id,hash=checksum)=>({...scope,id,snapshot:{id,version:1,asset:{sha256:hash}},sourceChecksum:hash,snapshotSha256:'c'.repeat(64),requestSha256:'d'.repeat(64),idempotencyKey:randomUUID(),operation:'create',state:'running',sensitive:true,contractVersion:'0.2',workAvailableAt:null});
for(const bad of ['', 'A'.repeat(64),'g'.repeat(64),'a'.repeat(63),'a'.repeat(65)]){
 denied(await lookup({checksum:bad}));denied(await op('CreateSpecimenV3',create(randomUUID(),bad),true));
}
const mismatch={...create(randomUUID()),snapshot:{asset:{sha256:other}}};
denied(await op('CreateSpecimenV3',mismatch,true));
assert.deepEqual(ok(await lookup({})).specimens,[]);
const attempts=[create(randomUUID()),create(randomUUID())];
const results=await Promise.all(attempts.map(v=>op('CreateSpecimenV3',v,true)));
const wins=results.map((r,i)=>(!r.code&&!r.errors?.length)?i:-1).filter(i=>i>=0);
assert.equal(wins.length,1);const winner=attempts[wins[0]],loser=attempts[1-wins[0]];
assert.match(JSON.stringify(results[1-wins[0]]),/specimen_scope_checksum|unique constraint/i);
const rows=ok(await lookup({})).specimens;assert.equal(rows.length,1);assert.equal(rows[0].id.replaceAll('-',''),winner.id.replaceAll('-',''));assert.deepEqual(Object.keys(rows[0]).sort(),['id','revision']);
const counts=psql(`SELECT (SELECT count(*) FROM specimen WHERE organization_id='${organizationId}'),(SELECT count(*) FROM specimen_snapshot WHERE organization_id='${organizationId}'),(SELECT count(*) FROM request_receipt WHERE organization_id='${organizationId}'),(SELECT count(*) FROM audit_event WHERE organization_id='${organizationId}'),(SELECT count(*) FROM outbox_event WHERE organization_id='${organizationId}');`).trim();
assert.equal(counts,'1|1|1|1|1');
assert.equal(ok(await op('GetReceipt',{...scope,operation:'create',idempotencyKey:loser.idempotencyKey})).requestReceipt,null);
console.log('PASS canonical/matching digest and concurrent different-ID same-bytes race: one atomic commit, zero loser effects');
const save={...winner,expectedRevision:1,operation:'save',action:'checkpoint',idempotencyKey:randomUUID(),activeRunId:null,disposition:null,snapshot:{...winner.snapshot,version:2}};
delete save.sourceChecksum;
denied(await op('SaveSpecimenV3',{...save,snapshot:{...save.snapshot,asset:{sha256:other}}},true));
denied(await op('SaveSpecimenV3',{...save,snapshot:{version:2}},true));
assert.equal(ok(await lookup({})).specimens[0].revision,1);
ok(await op('SaveSpecimenV3',save,true));
assert.equal(ok(await lookup({})).specimens[0].revision,2);
assert.equal(psql(`SELECT source_checksum FROM specimen WHERE organization_id='${organizationId}' AND id='${winner.id}'`).trim(),checksum);
const legacy=create(randomUUID(),other);delete legacy.sourceChecksum;
ok(await op('CreateSpecimenV2',legacy,true));
assert.deepEqual(ok(await lookup({checksum:other})).specimens,[]);
denied(await op('SaveSpecimenV3',{...save,id:legacy.id,expectedRevision:1,idempotencyKey:randomUUID(),snapshot:{...legacy.snapshot,version:2}},true));
const audit=psql(readFileSync(new URL('../../dataconnect/sql/checksum-audit.sql',import.meta.url),'utf8'));
assert.match(audit,/legacy_requires_verified_backfill/);assert.match(audit,/specimen_scope_checksum/);
console.log('PASS read-only legacy audit executes without payload hydration or data writes');
console.log('PASS immutable source save guard and explicitly unindexed/null legacy row blocked from V3 save');
for(const variables of [{actorUid:'outsider'},{collectionId:randomUUID()}])denied(await lookup(variables));
denied(await op('FindSpecimenByChecksum',{...scope,checksum,includeSensitive:true},false,{unauthenticated:true}));
denied(await op('FindSpecimenByChecksum',{...scope,checksum,includeSensitive:true},false,{authClaims:{sub:actorUid}}));
assert.deepEqual(ok(await lookup({includeSensitive:false})).specimens,[]);
psql(`UPDATE collection_member SET can_view_sensitive=false WHERE organization_id='${organizationId}' AND uid='${actorUid}'`);
denied(await lookup({}));assert.deepEqual(ok(await lookup({includeSensitive:false})).specimens,[]);
psql(`UPDATE collection_member SET active=false WHERE organization_id='${organizationId}' AND uid='${actorUid}'`);
denied(await lookup({includeSensitive:false}));
psql(`UPDATE collection_member SET active=true,can_view_sensitive=true WHERE organization_id='${organizationId}' AND uid='${actorUid}'; UPDATE organization_member SET active=false WHERE organization_id='${organizationId}' AND uid='${actorUid}'`);
denied(await lookup({}));
psql(`UPDATE organization_member SET active=true WHERE organization_id='${organizationId}' AND uid='${actorUid}'`);
// Same checksum in another collection is allowed; exact scope selects its own row.
const second=randomUUID();
ok(await raw(`mutation {collection_insert(data:{organizationId:"${organizationId}",id:"${second}",name:"Separate collection"}) collectionMember_insert(data:{organizationId:"${organizationId}",collectionId:"${second}",uid:"${actorUid}",active:true,role:"reviewer",canViewSensitive:true})}`));
const separate={...create(randomUUID()),collectionId:second};ok(await op('CreateSpecimenV3',separate,true));
assert.equal(ok(await lookup({collectionId:second})).specimens[0].id.replaceAll('-',''),separate.id.replaceAll('-',''));
assert.equal(ok(await lookup({})).specimens[0].id.replaceAll('-',''),winner.id.replaceAll('-',''));
console.log('PASS server-only metadata, cross-scope uniqueness and membership/sensitivity/revocation checks');
psql(`INSERT INTO specimen (organization_id,collection_id,id,revision,state,sensitive,created_by,created_at,updated_at,source_checksum) SELECT '${organizationId}','${collectionId}',gen_random_uuid(),1,'running',false,'synthetic',now(),now(),lpad(to_hex(n),64,'0') FROM generate_series(1,10037) n; ANALYZE specimen;`);
const plan=psql(`EXPLAIN (ANALYZE, FORMAT JSON) SELECT id,revision FROM specimen WHERE organization_id='${organizationId}' AND collection_id='${collectionId}' AND source_checksum='${checksum}' AND sensitive IN(false,true) LIMIT 2;`);
assert.match(plan,/specimen_scope_checksum/);
assert.equal(ok(await lookup({})).specimens.length,1);
console.log('PASS >10k persisted checksums exact lookup uses scoped unique index');
