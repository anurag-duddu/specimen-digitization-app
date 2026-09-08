// Seed only the disposable demo emulator. Never sends real credentials or data.
import assert from 'node:assert/strict';
const host=process.env.FIREBASE_DATACONNECT_EMULATOR_HOST || '127.0.0.1:9499';
assert.match(host,/^(127\.0\.0\.1|localhost):\d+$/);
const organizationId='00000000-0000-4000-8000-000000000001';
const collectionId='00000000-0000-4000-8000-000000000002';
const query=`mutation @transaction {
 organization_upsert(data:{id:"${organizationId}",name:"Synthetic demonstration"})
 collection_upsert(data:{organizationId:"${organizationId}",id:"${collectionId}",name:"Synthetic Insects"})
 organizationMember_upsert(data:{organizationId:"${organizationId}",uid:"synthetic-reviewer",active:true})
 collectionMember_upsert(data:{organizationId:"${organizationId}",collectionId:"${collectionId}",uid:"synthetic-reviewer",active:true,role:"reviewer",canViewSensitive:true})
}`;
const r=await fetch(`http://${host}/v1/projects/demo-specimen-data/locations/us-east4/services/specimen-digitization-service:executeGraphql`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query})});
const result=await r.json();assert.ok(!result.code&&!result.errors?.length,JSON.stringify(result));
console.log('Seeded synthetic-reviewer in canonical demonstration scope; emulator only');
