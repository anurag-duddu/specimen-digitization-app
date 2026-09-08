import json,threading,time,socket,secrets,uuid
from pathlib import Path
import httpx,uvicorn
from specimen_digitization.application.api import create_app,SYNTHETIC_ORG,SYNTHETIC_COLLECTION,SYNTHETIC_TEXT
from specimen_digitization.application.production import SqlConnectRepository,actor_uid
from specimen_digitization.application.storage import LocalBlobs
from specimen_digitization.application.workflow import SyntheticAdapters
from specimen_digitization.application.domain import Scope
p=Path(Path('/tmp/specimen-qa-current-path').read_text());base='http://127.0.0.1:9519/v1/projects/demo-specimen-data/locations/us-east4/services/specimen-digitization-service';ident='7aced055-21bd-5cb0-86dd-cd5c60ed957b';prefix=f'/v1/organizations/{SYNTHETIC_ORG}';path=prefix+'/specimens/'+ident
results=[]
def gql(query):
 r=httpx.post(base+':executeGraphql',headers={'Authorization':'Bearer owner'},json={'query':query},timeout=45);r.raise_for_status();v=r.json();assert not v.get('errors'),v;return v
user='qa_history_viewer'
def seed(active=True,sensitive=True):
 gql(f'mutation @transaction {{organizationMember_upsert(data:{{organizationId:"{SYNTHETIC_ORG}",uid:"{user}",active:true}}) collectionMember_upsert(data:{{organizationId:"{SYNTHETIC_ORG}",collectionId:"{SYNTHETIC_COLLECTION}",uid:"{user}",active:{str(active).lower()},role:"viewer",canViewSensitive:{str(sensitive).lower()}}})}}')
seed();repo=SqlConnectRepository(project='demo-specimen-data',emulator_host='127.0.0.1:9519');blobs=LocalBlobs(p/'api-state'/'blobs');token=secrets.token_urlsafe(32)
def verify(t,check):
 if t!=token:raise PermissionError('QA invalid token')
 return user
app=create_app(mode='emulator',repository=repo,blobs=blobs,adapters=SyntheticAdapters(blobs,SYNTHETIC_TEXT),identity_verifier=verify,memberships=repo.memberships)
with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error',access_log=False));thread=threading.Thread(target=server.run);thread.start()
for _ in range(100):
 if server.started:break
 time.sleep(.05)
c=httpx.Client(base_url=f'http://127.0.0.1:{port}',headers={'Authorization':'Bearer '+token},timeout=45)
def check(name,http,expected):
 results.append({'case':name,'http':http,'passed':http in expected});assert http in expected
try:
 check('viewer_historical_read',c.get(path+'/history/28').status_code,[200]);check('viewer_historical_page',c.get(path+'/history').status_code,[200])
 check('anonymous_history',httpx.get(f'http://127.0.0.1:{port}'+path+'/history').status_code,[401])
 check('wrong_organization_history',c.get(path.replace(SYNTHETIC_ORG,str(uuid.uuid4()))+'/history').status_code,[403,404])
 seed(sensitive=False);check('sensitive_permission_removed',c.get(path+'/history/28').status_code,[403,404,409])
 seed();check('sensitive_permission_restored',c.get(path+'/history/28').status_code,[200])
 seed(active=False);check('membership_revoked_version',c.get(path+'/history/28').status_code,[403,404]);check('membership_revoked_page',c.get(path+'/history').status_code,[403,404]);seed()
 actor_uid.set(user);scope=Scope(organization_id=SYNTHETIC_ORG,collection_id=SYNTHETIC_COLLECTION);saved=repo.execute('GetSnapshot',dict(repo.variables(scope),id=ident,revision=1))['specimenSnapshot']
 def update_sha(sha):gql(f'mutation {{specimenSnapshot_update(key:{{organizationId:"{SYNTHETIC_ORG}",collectionId:"{SYNTHETIC_COLLECTION}",specimenId:"{ident}",revision:1}},data:{{sha256:"{sha}"}})}}')
 try:
  update_sha('0'*64);check('SQL_snapshot_checksum_tamper_denied',c.get(path+'/history/1').status_code,[409]);check('SQL_tampered_snapshot_page_denied',c.get(path+'/history',params={'limit':1}).status_code,[409])
 finally:update_sha(saved['sha256'])
 check('SQL_snapshot_checksum_restored',c.get(path+'/history/1').status_code,[200]);record=repo.execute('GetSnapshot',dict(repo.variables(scope),id=ident,revision=1))['specimenSnapshot'];assert record==saved
finally:
 seed();c.close();server.should_exit=True;thread.join(timeout=10)
(p/'history-auth-evidence.json').write_text(json.dumps({'candidate':'95215d9','boundary':'actualTCP SQL memberships + injected QA verifier; no Firebase cryptography claim; own snapshot digest fault restored','results':results},indent=2)+'\n');print(json.dumps(results,indent=2))
