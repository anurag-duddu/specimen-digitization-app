// Tests actual Storage emulator rules, not a reimplementation of those rules.
import assert from 'node:assert/strict';
import {passed} from './engine-contract-reporter.mjs';
import { randomUUID } from 'node:crypto';
const host=process.env.FIREBASE_STORAGE_EMULATOR_HOST || '127.0.0.1:9299';
assert.match(host,/^(127\.0\.0\.1|localhost):\d+$/);
const base=`http://${host}/v0/b/demo-specimen-data.appspot.com/o`;
const name=`organizations/synthetic/collections/insects/originals/${randomUUID()}`;
const item=`${base}/${encodeURIComponent(name)}`;
const upload=await fetch(`${base}?uploadType=media&name=${encodeURIComponent(name)}`,{method:'POST',headers:{Authorization:'Bearer owner','Content-Type':'image/png'},body:new Uint8Array([137,80,78,71])});
assert.equal(upload.status,200,await upload.text());
passed('storage.admin.create');
const claims={sub:'synthetic-reviewer',user_id:'synthetic-reviewer',aud:'demo-specimen-data',iss:'https://securetoken.google.com/demo-specimen-data',iat:Math.floor(Date.now()/1000),exp:Math.floor(Date.now()/1000)+3600,firebase:{sign_in_provider:'custom'}};
const token=[{alg:'none',typ:'JWT'},claims].map(v=>Buffer.from(JSON.stringify(v)).toString('base64url')).join('.')+'.';
const denialErrors=[];
const attackedOriginals=[];
for(const [identity,headers] of [['anonymous',{}],['authenticated',{Authorization:`Bearer ${token}`}]]){
 let actionIndex=0;
 for(const [method,url,body] of [['GET',`${item}?alt=media`],['GET',base],['DELETE',item],['POST',`${base}?uploadType=media&name=${encodeURIComponent(name)}`,'replacement'],['POST',`${base}?uploadType=media&name=${encodeURIComponent(name+'-new')}`,'new']]){
  const action=['read','list','delete','overwrite','create'][actionIndex++];
  const id=`storage.${identity}.${action}`;
  // Each denial has its own fresh existing object. If an allow-all mutant
  // deletes/overwrites one, subsequent denials still exercise real actions.
  const freshName=name+'-'+identity+'-'+action;
  const freshItem=`${base}/${encodeURIComponent(freshName)}`;
  attackedOriginals.push(freshItem);
  const setup=await fetch(`${base}?uploadType=media&name=${encodeURIComponent(freshName)}`,{method:'POST',headers:{Authorization:'Bearer owner','Content-Type':'image/png'},body:new Uint8Array([137,80,78,71])});
  assert.equal(setup.status,200,await setup.text());
  const freshUrl=action==='list'?url:action==='create'?`${base}?uploadType=media&name=${encodeURIComponent(freshName+'-new')}`:action==='overwrite'?`${base}?uploadType=media&name=${encodeURIComponent(freshName)}`:`${freshItem}${action==='read'?'?alt=media':''}`;
  const r=await fetch(freshUrl,{method,headers,...(body?{body}:{})});
  try {
   assert.ok([401,403].includes(r.status),`${id}: ${method} unexpected ${r.status}: ${await r.text()}`);
   passed(id);
  } catch(error) {denialErrors.push(error);console.error(error.message);}
 }
}
const original=await fetch(`${item}?alt=media`,{headers:{Authorization:'Bearer owner'}});
assert.equal(original.status,200,await original.clone().text());
passed('storage.admin.read');
assert.deepEqual(new Uint8Array(await original.arrayBuffer()),new Uint8Array([137,80,78,71]));
passed('storage.original-bytes');
// Retain the primary denial errors as the cause after original/admin checks.
// All ten independent actions ran, even when an allow-all response was seen.
if(denialErrors.length) throw new AggregateError(denialErrors,'Storage denial assertions failed');
for(const attacked of attackedOriginals) {
 const retained=await fetch(`${attacked}?alt=media`,{headers:{Authorization:'Bearer owner'}});
 assert.equal(retained.status,200,'Denied mutations must retain every attacked original');
 assert.deepEqual(new Uint8Array(await retained.arrayBuffer()),new Uint8Array([137,80,78,71]),'Denied overwrite changed original bytes');
}
console.log('PASS Storage denies anonymous/authenticated read, list, create, overwrite and delete');
console.log('PASS original bytes unchanged after denied mutations; admin bypass explicitly demonstrated');
