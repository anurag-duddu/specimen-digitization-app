import json,threading,time,socket,secrets,uuid,io,hashlib
from pathlib import Path
import httpx,uvicorn
from specimen_digitization.application.api import create_app,SYNTHETIC_ORG,SYNTHETIC_COLLECTION,SYNTHETIC_TEXT
from specimen_digitization.application.production import SqlConnectRepository,actor_uid
from specimen_digitization.application.storage import LocalBlobs
from specimen_digitization.application.workflow import SyntheticAdapters,Workflow
from specimen_digitization.application.domain import Scope,Principal,Region
from specimen_digitization.application.demo import fixture
from PIL import Image,PngImagePlugin
p=Path(Path('/tmp/specimen-qa-current-path').read_text());base='http://127.0.0.1:9519/v1/projects/demo-specimen-data/locations/us-east4/services/specimen-digitization-service'
# Seed test identities only. Do not alter existing source/workflow records.
roles={'qa_viewer':'viewer','qa_operator':'operator','qa_reviewer':'reviewer','qa_nosensitive':'reviewer'}
parts=[]
for user,role in roles.items():
 parts += [f'{user}org: organizationMember_upsert(data:{{organizationId:"{SYNTHETIC_ORG}",uid:"{user}",active:true}})',f'{user}col: collectionMember_upsert(data:{{organizationId:"{SYNTHETIC_ORG}",collectionId:"{SYNTHETIC_COLLECTION}",uid:"{user}",active:true,role:"{role}",canViewSensitive:{str(user!="qa_nosensitive").lower()}}})']
r=httpx.post(base+':executeGraphql',headers={'Authorization':'Bearer owner'},json={'query':'mutation @transaction {'+' '.join(parts)+'}'}).json()
assert not r.get('errors'),r
repo=SqlConnectRepository(project='demo-specimen-data',emulator_host='127.0.0.1:9519');blobs=LocalBlobs(p/'api-state'/'blobs');tokens={secrets.token_urlsafe(24):u for u in roles};token_for={u:t for t,u in tokens.items()}
def verify(token,check):
 if token not in tokens:raise PermissionError('QA token rejected')
 return tokens[token]
class DeclaredQAFixtureAdapters(SyntheticAdapters):
 def segment(self,specimen):
  return [Region(asset_id=specimen.asset.id,x=0,y=0,width=specimen.asset.width,height=specimen.asset.height,order=0,method='qa-fixture-only',version='qa-v1')]
app=create_app(mode='emulator',repository=repo,blobs=blobs,adapters=SyntheticAdapters(blobs,SYNTHETIC_TEXT),identity_verifier=verify,memberships=repo.memberships)
with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error',access_log=False));thread=threading.Thread(target=server.run);thread.start()
for _ in range(100):
 if server.started:break
 time.sleep(.05)
api=f'http://127.0.0.1:{port}';prefix=f'/v1/organizations/{SYNTHETIC_ORG}';known=json.loads((p/'workspace-positive.json').read_text());path=prefix+'/specimens/'+known['specimen_id'];results=[]
def request(user,method,path,**kw):return httpx.request(method,api+path,headers={'Authorization':'Bearer '+token_for[user],'Idempotency-Key':str(uuid.uuid4())},timeout=45,**kw)
try:
 for user in roles:
  rr=request(user,'GET',path+'/workspace')
  if user=='qa_nosensitive':
   results.append({'case':user+'_sensitive_workspace','http':rr.status_code,'passed':rr.status_code>=400});continue
  assert rr.status_code==200,rr.text;w=rr.json()
  body={'kind':'approve','expected_revision':w['revision'],'base_record_version_id':w['record_version_id'],'reason':'QA role gate test'}
  if user!='qa_reviewer':
   denied=request(user,'POST',path+'/decisions',json=body);results.append({'case':user+'_approve_denied','http':denied.status_code,'passed':denied.status_code==403,'available_actions':w['available_actions']})
  image=request(user,'GET',prefix+'/assets/'+w['asset']['id']+'/content');results.append({'case':user+'_authorized_source','passed':image.status_code==200})
 # Production profile generated through normal emulator-mode intake, processed with explicit local fixtures.
 user='qa_reviewer';raw=fixture();im=Image.open(io.BytesIO(raw));info=PngImagePlugin.PngInfo();info.add_text('qa','production-policy-negative-'+str(uuid.uuid4()));out=io.BytesIO();im.save(out,format='PNG',pnginfo=info);raw=out.getvalue()
 batch=request(user,'POST',prefix+'/batches',json={'collection_id':SYNTHETIC_COLLECTION,'display_name':'QA unapproved production profile'}).json()
 item=request(user,'POST',prefix+'/batches/'+batch['batch_id']+'/items',json={'client_item_id':str(uuid.uuid4()),'filename':'qa-unapproved-profile.png','media_type':'image/png','size_bytes':len(raw),'width':1000,'height':520,'sha256':hashlib.sha256(raw).hexdigest()}).json();up=prefix+'/uploads/'+item['upload_id']
 chunk=request(user,'PUT',up+'/content',content=raw);chunk.raise_for_status();done=request(user,'POST',up+'/complete',json={'expected_revision':chunk.json()['revision']});done.raise_for_status()
 scope=Scope(organization_id=SYNTHETIC_ORG,collection_id=SYNTHETIC_COLLECTION);principal=Principal(user_id=user,scope=scope,role='reviewer');actor_uid.set(user)
 Workflow(repo,blobs,DeclaredQAFixtureAdapters(blobs,SYNTHETIC_TEXT)).drain(principal,item['specimen_id'])
 wp=prefix+'/specimens/'+item['specimen_id'];w=request(user,'GET',wp+'/workspace').json();assert w['run']['profile']['synthetic'] is False
 body={'kind':'approve','expected_revision':w['revision'],'base_record_version_id':w['record_version_id'],'reason':'QA unresolved institutional policy negative'}
 denied_clear=request(user,'POST',wp+'/decisions',json=body);after=denied_clear.json()
 results.append({'case':'production_profile_HTTP_approval_blocks_unknown_semantics','http':denied_clear.status_code,'disposition':after.get('disposition'),'reasons':after.get('reason_codes'),'passed':after.get('disposition')!='cleared' and 'mandatory_semantics_unconfirmed' in after.get('reason_codes',[]) and 'institutional_policy_unapproved' in after.get('reason_codes',[])})
 # Real membership revocation between read and commit.
 rr=httpx.post(base+':executeGraphql',headers={'Authorization':'Bearer owner'},json={'query':f'mutation {{organizationMember_update(key:{{organizationId:"{SYNTHETIC_ORG}",uid:"qa_reviewer"}},data:{{active:false}})}}'}).json();assert not rr.get('errors'),rr
 stale=request(user,'POST',wp+'/decisions',json={**body,'expected_revision':after['revision'],'base_record_version_id':after['record_version_id']})
 results.append({'case':'revocation_between_read_and_commit','http':stale.status_code,'passed':stale.status_code in (403,404)})
 results.append({'case':'revoked_memberships','passed':request(user,'GET','/v1/session').json()['memberships']==[]})
finally:server.should_exit=True;thread.join(timeout=10)
(p/'sql-auth-policy-evidence.json').write_text(json.dumps({'identity':'explicit QA token verifier; NOT Firebase cryptographic identity proof','transport':'real TCP + SQL Connect/PostgreSQL; explicitly injected QA segmentation and synthetic observations/lookup; default production Profile unchanged','results':results},indent=2));print(json.dumps(results,indent=2))
