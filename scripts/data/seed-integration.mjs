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
const r=await fetch(`http://${host}/v1/projects/demo-specimen-data/locations/us-east4/services/specimen-digitization-service:executeGraphql`,{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer owner'},body:JSON.stringify({query})});
assert.equal(r.status,200,'seed mutation HTTP failure');
const result=await r.json();assert.ok(!result.code&&!result.errors?.length,JSON.stringify(result));
// Read back exact canonical membership; a successful mutation response alone
// does not establish the identity/authorization Python will actually use.
const readback=await fetch(`http://${host}/v1/projects/demo-specimen-data/locations/us-east4/services/specimen-digitization-service:executeGraphql`,{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer owner'},body:JSON.stringify({query:`query {
 organizationMembers(where:{organizationId:{eq:"${organizationId}"},uid:{eq:"synthetic-reviewer"}}) { organizationId uid active }
 collectionMembers(where:{organizationId:{eq:"${organizationId}"},collectionId:{eq:"${collectionId}"},uid:{eq:"synthetic-reviewer"}}) { organizationId collectionId uid role active canViewSensitive }
}`})});
assert.equal(readback.status,200,'seed readback HTTP failure');
const observed=await readback.json();
assert.ok(!observed.code&&!observed.errors?.length,JSON.stringify(observed));
const normalize=id=>id.replaceAll('-','');
assert.equal(observed.data.organizationMembers.length,1,'seed organization membership missing/duplicate');
assert.equal(observed.data.collectionMembers.length,1,'seed collection membership missing/duplicate');
const organization=observed.data.organizationMembers[0], collection=observed.data.collectionMembers[0];
assert.deepEqual({...organization,organizationId:normalize(organization.organizationId)},
 {organizationId:normalize(organizationId),uid:'synthetic-reviewer',active:true});
assert.deepEqual({...collection,organizationId:normalize(collection.organizationId),collectionId:normalize(collection.collectionId)},
 {organizationId:normalize(organizationId),collectionId:normalize(collectionId),uid:'synthetic-reviewer',role:'reviewer',active:true,canViewSensitive:true});
if(process.env.ENGINE_CONTRACT_SEED_REPORT) {
 const {writeFileSync}=await import('node:fs');
 writeFileSync(process.env.ENGINE_CONTRACT_SEED_REPORT,JSON.stringify({organization:organizationId,collection:collectionId,uid:'synthetic-reviewer',organization_active:organization.active,collection_active:collection.active,role:collection.role,can_view_sensitive:collection.canViewSensitive}),{mode:0o600,flag:'wx'});
}
console.log('Seeded and verified synthetic-reviewer in canonical demonstration scope; emulator only');
