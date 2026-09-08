import os,json,hashlib,io,time,uuid
from pathlib import Path
import httpx
from PIL import Image,PngImagePlugin
from specimen_digitization.application.api import SYNTHETIC_ORG,SYNTHETIC_COLLECTION
from specimen_digitization.application.demo import fixture
p=Path(Path('/tmp/specimen-qa-current-path').read_text()); token=(p/'token').read_text()
prefix=f'/v1/organizations/{SYNTHETIC_ORG}'
c=httpx.Client(base_url='http://127.0.0.1:8124',headers={'Authorization':'Bearer '+token},timeout=45)
results=[]
def check(name,actual,expected):
 results.append({'case':name,'actual':actual,'expected':expected,'status':'passed' if actual==expected else 'failed'}); (p/'http-negative-evidence.json').write_text(json.dumps(results,indent=2))
def req(method,path,key=None,**kw):
 return c.request(method,path,headers={'Idempotency-Key':key or str(uuid.uuid4())},**kw)
def make(raw=None,**meta):
 if raw is None:
  im=Image.open(io.BytesIO(fixture())); info=PngImagePlugin.PngInfo();info.add_text('qa_case',str(uuid.uuid4()));out=io.BytesIO();im.save(out,format='PNG',pnginfo=info);raw=out.getvalue()
 b=req('POST',prefix+'/batches',json={'collection_id':SYNTHETIC_COLLECTION,'display_name':'QA independent synthetic'});b.raise_for_status()
 data={'client_item_id':str(uuid.uuid4()),'filename':'qa-synthetic.png','media_type':'image/png','size_bytes':len(raw),'width':1000,'height':520,'sha256':hashlib.sha256(raw).hexdigest(),**meta}
 r=req('POST',prefix+'/batches/'+b.json()['batch_id']+'/items',json=data);r.raise_for_status();u=r.json();u['_raw']=raw;return u
check('session_sql_transport',c.get('/v1/session').json()['persistence'],'sql_connect')
check('anonymous_session',httpx.get(str(c.base_url)+'/v1/session').status_code,401)
check('wrong_bearer',httpx.get(str(c.base_url)+'/v1/session',headers={'Authorization':'Bearer invalid'}).status_code,401)
check('cross_org_list',req('GET','/v1/organizations/'+str(uuid.uuid4())+'/specimens',params={'collection_id':SYNTHETIC_COLLECTION}).status_code,403)
check('cross_collection_list',req('GET',prefix+'/specimens',params={'collection_id':str(uuid.uuid4())}).status_code,403)
valid=make();path=prefix+'/uploads/'+valid['upload_id'];raw=valid['_raw']
r=req('PUT',path+'/content',content=raw[:137],headersx=None) if False else c.put(path+'/content',content=raw[:137],headers={'Upload-Offset':'0'})
check('partial_offset',r.json()['offset'],137)
check('same_chunk_replay',c.put(path+'/content',content=raw[:137],headers={'Upload-Offset':'0'}).json()['offset'],137)
check('changed_chunk_replay',c.put(path+'/content',content=b'x'*137,headers={'Upload-Offset':'0'}).status_code,409)
check('premature_complete',req('POST',path+'/complete',json={'expected_revision':r.json()['revision']}).status_code,409)
r=c.put(path+'/content',content=raw[137:],headers={'Upload-Offset':'137'});r.raise_for_status();v=r.json()['revision'];key=str(uuid.uuid4());body={'expected_revision':v,'reason':'QA original completion'}
done=req('POST',path+'/complete',key=key,json=body);done.raise_for_status();ident=done.json()['specimen_id'];sp=prefix+'/specimens/'+ident
for _ in range(200):
 w=c.get(sp+'/workspace').json()
 if w.get('disposition'):break
 time.sleep(.05)
check('automatic_background_review',w.get('disposition'),'needs_human_review')
check('original_bytes_digest',hashlib.sha256(c.get(prefix+'/assets/'+w['asset']['id']+'/content').content).hexdigest(),hashlib.sha256(raw).hexdigest())
check('original_no_store',c.get(prefix+'/assets/'+w['asset']['id']+'/content').headers.get('cache-control'),'no-store')
changed=req('POST',path+'/complete',key=key,json={'expected_revision':v,'reason':'CHANGED PAYLOAD'})
check('complete_changed_payload_same_key',changed.status_code,409)
# Identical completion should return the first logical response, not a later processing snapshot.
replay=req('POST',path+'/complete',key=key,json=body)
check('complete_exact_replay_response',replay.json(),done.json())
for name,bytes_,meta in [('truncated',raw[:60],{}),('hash_mismatch',raw,{'sha256':'f'*64}),('mime_mismatch',raw,{'media_type':'image/jpeg'}),('dimension_mismatch',raw,{'width':999}),('random_bytes',b'not an image',{})]:

 if name in {'mime_mismatch','dimension_mismatch'}:
  im=Image.open(io.BytesIO(raw));info=PngImagePlugin.PngInfo();info.add_text('qa_negative',str(uuid.uuid4()));out=io.BytesIO();im.save(out,format='PNG',pnginfo=info);bytes_=out.getvalue()
 u=make(bytes_,**meta);up=prefix+'/uploads/'+u['upload_id'];rr=c.put(up+'/content',content=bytes_);rr.raise_for_status();bad=req('POST',up+'/complete',json={'expected_revision':rr.json()['revision']})
 check(name+'_rejected',bad.status_code>=400,True)
 try:
  missing=c.get(prefix+'/specimens/'+u['specimen_id']).status_code
 except httpx.ReadError:
  check(name+'_keepalive_survives',False,True)
  missing=httpx.get(str(c.base_url)+prefix+'/specimens/'+u['specimen_id'],headers={'Authorization':'Bearer '+token}).status_code
 check(name+'_no_record',missing,404)
 results.append({'case':name+'_error_class','status':'observed','http':bad.status_code,'body':bad.json()})
(p/'http-negative-evidence.json').write_text(json.dumps({'candidate':'4c71e13','mode':'synthetic','transport':'SQL Connect9519/PostgreSQL5569 with local immutable blobs','specimen_id':ident,'results':results},indent=2))
(p/'workspace-positive.json').write_text(json.dumps(w,indent=2))
print(json.dumps({'results':[{k:v for k,v in r.items() if k in ('case','status','http')} for r in results],'evidence':str(p/'http-negative-evidence.json')},indent=2))
