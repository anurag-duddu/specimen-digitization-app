import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const {scope,id}=JSON.parse(await readFile(process.env.DATA_RESTART_PROOF,'utf8'));
const host=process.env.FIREBASE_DATACONNECT_EMULATOR_HOST;
assert.match(host,/^127\.0\.0\.1:\d+$/);
const base=`http://${host}/v1/projects/demo-specimen-data/locations/us-east4/services/specimen-digitization-service/connectors/specimen-server:impersonateQuery`;
for(const revision of [1,3]) {
 const r=await fetch(base,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({operationName:'GetSnapshot',variables:{...scope,id,revision}})});
 const result=await r.json();assert.ok(!result.code&&!result.errors?.length,JSON.stringify(result));
 assert.equal(result.data.specimenSnapshot.snapshot.version,revision);
}
console.log('PASS SQL Connect process restart reconstructs current and immutable prior snapshots');
