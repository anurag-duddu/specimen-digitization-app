import json,uuid,hashlib,io,time
from PIL import Image,PngImagePlugin
from specimen_digitization.application.demo import fixture
from pathlib import Path
import httpx
from specimen_digitization.application.api import SYNTHETIC_ORG,SYNTHETIC_COLLECTION
from specimen_digitization.application.domain import Scope,Principal
from specimen_digitization.application.production import SqlConnectRepository,actor_uid
from specimen_digitization.application.storage import digest
p=Path(Path('/tmp/specimen-qa-current-path').read_text());token=(p/'token').read_text();w=json.loads((p/'workspace-positive.json').read_text());prefix=f'/v1/organizations/{SYNTHETIC_ORG}';path=prefix+'/specimens/'+w['specimen_id'];results=[]
c=httpx.Client(base_url='http://127.0.0.1:8124',headers={'Authorization':'Bearer '+token},timeout=45)
repo=SqlConnectRepository(project='demo-specimen-data',emulator_host='127.0.0.1:9519');actor_uid.set('synthetic-reviewer');scope=Scope(organization_id=SYNTHETIC_ORG,collection_id=SYNTHETIC_COLLECTION);principal=Principal(user_id='synthetic-reviewer',scope=scope,role='reviewer')
def fresh():
 global w,path
 im=Image.open(io.BytesIO(fixture()));info=PngImagePlugin.PngInfo();info.add_text('qa_case',str(uuid.uuid4()));out=io.BytesIO();im.save(out,format='PNG',pnginfo=info);raw=out.getvalue()
 b=c.post(prefix+'/batches',json={'collection_id':SYNTHETIC_COLLECTION,'display_name':'Independent repair integrity QA'},headers={'Idempotency-Key':str(uuid.uuid4())});b.raise_for_status()
 r=c.post(prefix+'/batches/'+b.json()['batch_id']+'/items',json={'client_item_id':str(uuid.uuid4()),'filename':'qa-repair-integrity.png','media_type':'image/png','size_bytes':len(raw),'width':1000,'height':520,'sha256':hashlib.sha256(raw).hexdigest()},headers={'Idempotency-Key':str(uuid.uuid4())});r.raise_for_status();u=r.json();up=prefix+'/uploads/'+u['upload_id']
 rr=c.put(up+'/content',content=raw);rr.raise_for_status();done=c.post(up+'/complete',json={'expected_revision':rr.json()['revision']},headers={'Idempotency-Key':str(uuid.uuid4())});done.raise_for_status();path=prefix+'/specimens/'+done.json()['specimen_id']
 for _ in range(200):
  w=workspace()
  if w.get('disposition'):return
  time.sleep(.05)
 raise AssertionError('worker did not finish')
def workspace():
 r=c.get(path+'/workspace');r.raise_for_status();return r.json()
def approve(w,key=None):
 body={'kind':'approve','expected_revision':w['revision'],'base_record_version_id':w['record_version_id'],'reason':'Independent QA synthetic evidence integrity test'}
 r=c.post(path+'/decisions',headers={'Idempotency-Key':key or str(uuid.uuid4())},json=body);r.raise_for_status();return r.json()
def blocked(x):return x.get('disposition') is None and x.get('status')=='processing_blocked' and x.get('reason_codes')==['evidence_integrity_failure']
def record(name,ok,**extra):
 results.append({'case':name,'passed':ok,**extra});print(name,ok);assert ok
for target in ['source','observation','lookup']:
 for damage in ['missing','corrupt']:
  fresh();before=workspace();ref={'source':before['asset']['blob_ref'],'observation':before['observations'][0]['raw_ref'],'lookup':before['run']['lookups'][0]['raw_ref']}[target];blob=p/'api-state'/'blobs'/ref;raw=blob.read_bytes();key=str(uuid.uuid4())
  try:
   if damage=='missing':blob.unlink()
   else:blob.write_bytes(b'QA corrupted own retained blob')
   denied=approve(before,key);record(target+'_'+damage+'_blocks',blocked(denied),status=denied.get('status'),disposition=denied.get('disposition'))
   record(target+'_'+damage+'_persisted',blocked(workspace()))
   record(target+'_'+damage+'_connection_alive',c.get('/v1/session').status_code==200)
  finally:blob.write_bytes(raw)
  restored=approve(workspace());record(target+'_'+damage+'_restored',restored.get('disposition')=='cleared')
  record(target+'_'+damage+'_receipt_immutable',approve(before,key)==denied)
for damage in ['wrong_digest','wrong_ref','wrong_asset','wrong_input','wrong_region_asset','wrong_evidence_ref']:
 fresh();original=repo.get(scope,w['specimen_id']);changed=original.model_copy(deep=True)
 if damage=='wrong_digest':changed.run.observations[0].raw_sha256='f'*64
 elif damage=='wrong_ref':changed.run.observations[0].raw_ref=changed.asset.blob_ref
 elif damage=='wrong_asset':changed.run.evidence[0].asset_id=str(uuid.uuid4())
 elif damage=='wrong_input':changed.run.observations[0].input_sha256='f'*64
 elif damage=='wrong_region_asset':changed.run.regions[0].asset_id=str(uuid.uuid4())
 else:changed.run.evidence[0].raw_ref=changed.asset.blob_ref;changed.run.evidence[0].digest='f'*64
 try:
  repo.save(principal,changed,changed.version,str(uuid.uuid4()),digest(damage));denied=approve(workspace());record(damage+'_blocks',blocked(denied));record(damage+'_persisted',blocked(workspace()))
 finally:
  latest=repo.get(scope,w['specimen_id']);latest.run=original.run;repo.save(principal,latest,latest.version,str(uuid.uuid4()),digest('restore-'+damage))
 record(damage+'_restored',approve(workspace()).get('disposition')=='cleared')
c.close();(p/'repair-integrity-evidence.json').write_text(json.dumps({'candidate':'25e8358','transport':'actual TCP8124 SQL Connect9519 PostgreSQL5569','mode':'synthetic; unique API intake; own retained storage and persisted graph faults restored','results':results},indent=2)+'\n')
