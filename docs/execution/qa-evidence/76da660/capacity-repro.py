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

fresh();sizes=[];accepted=0
for attempt in range(1,25):
 before=workspace();r=c.post(path+'/decisions',headers={'Idempotency-Key':str(uuid.uuid4())},json={'kind':'approve','expected_revision':before['revision'],'base_record_version_id':before['record_version_id'],'reason':'Independent QA ordinary repeated synthetic review'})
 saved=repo.get(scope,w['specimen_id']);v=saved.model_dump(mode='json');entry={'attempt':attempt,'http':r.status_code,'snapshot_bytes':len(saved.model_dump_json().encode()),'audit_bytes':len(json.dumps(v['audit'],separators=(',',':'),ensure_ascii=False).encode()),'audit_entries':len(saved.audit),'previous_runs':len(saved.previous_runs)};sizes.append(entry)
 if r.status_code!=200:break
 accepted+=1
result={'candidate':'76da660','transport':'actual TCP8124 SQL9519 PG5569','case':'ordinary_approvals_without_fault_injection','accepted_decisions':accepted,'specimen_id':w['specimen_id'],'growth':sizes};(p/'capacity-evidence.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));c.close()
