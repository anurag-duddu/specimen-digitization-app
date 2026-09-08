// Tests actual Storage emulator rules, not a reimplementation of those rules.
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
const host=process.env.FIREBASE_STORAGE_EMULATOR_HOST || '127.0.0.1:9299';
assert.match(host,/^(127\.0\.0\.1|localhost):\d+$/);
const base=`http://${host}/v0/b/demo-specimen-data.appspot.com/o`;
const name=`organizations/synthetic/collections/insects/originals/${randomUUID()}`;
const item=`${base}/${encodeURIComponent(name)}`;
const upload=await fetch(`${base}?uploadType=media&name=${encodeURIComponent(name)}`,{method:'POST',headers:{Authorization:'Bearer owner','Content-Type':'image/png'},body:new Uint8Array([137,80,78,71])});
assert.equal(upload.status,200,await upload.text());
const claims={sub:'synthetic-reviewer',user_id:'synthetic-reviewer',aud:'demo-specimen-data',iss:'https://securetoken.google.com/demo-specimen-data',iat:Math.floor(Date.now()/1000),exp:Math.floor(Date.now()/1000)+3600,firebase:{sign_in_provider:'custom'}};
const token=[{alg:'none',typ:'JWT'},claims].map(v=>Buffer.from(JSON.stringify(v)).toString('base64url')).join('.')+'.';
for(const headers of [{},{Authorization:`Bearer ${token}`}]){
 for(const [method,url,body] of [['GET',`${item}?alt=media`],['GET',base],['DELETE',item],['POST',`${base}?uploadType=media&name=${encodeURIComponent(name)}`,'replacement'],['POST',`${base}?uploadType=media&name=${encodeURIComponent(name+'-new')}`,'new']]){
  const r=await fetch(url,{method,headers,...(body?{body}:{})});
  assert.ok([401,403].includes(r.status),`${method} unexpected ${r.status}: ${await r.text()}`);
 }
}
console.log('PASS Storage denies anonymous/authenticated read, list, create, overwrite and delete');
const original=await fetch(`${item}?alt=media`,{headers:{Authorization:'Bearer owner'}});
assert.deepEqual(new Uint8Array(await original.arrayBuffer()),new Uint8Array([137,80,78,71]));
console.log('PASS original bytes unchanged after denied mutations; admin bypass explicitly demonstrated');
