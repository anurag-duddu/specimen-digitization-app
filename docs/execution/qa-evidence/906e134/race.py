import sys,json,hashlib,threading,io
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
sys.path.insert(0,str(Path.cwd()/'tests'))
from test_authority_runtime import running_api
from test_application import HEADERS,PREFIX,TOKEN,SYNTHETIC_COLLECTION,SYNTHETIC_ORG
from specimen_digitization.application.api import create_app,SYNTHETIC_TEXT
from specimen_digitization.application.production import SqlConnectRepository,actor_uid
from specimen_digitization.application.storage import LocalBlobs,digest,Conflict
from specimen_digitization.application.workflow import SyntheticAdapters
from specimen_digitization.application.collection_runtime import application_registry
from specimen_digitization.application.domain import Scope,Principal
from PIL import Image,PngImagePlugin
root=Path(Path('/tmp/specimen-qa-hardening-path').read_text().strip());blobs=LocalBlobs(root/'race-blobs')
repo=SqlConnectRepository(project='demo-specimen-data',emulator_host='127.0.0.1:9519')
barrier=threading.Barrier(4);operations=[];create_ids=[];original=repo.execute
# The barrier forces all four HTTP completions past their prechecks before real V3 writes.
def execute(operation,variables,mutation=False):
    operations.append(operation)
    if operation=='CreateSpecimenV3':
        create_ids.append(variables.get('specimenId'))
        barrier.wait(15)
    return original(operation,variables,mutation)
repo.execute=execute
app=create_app(mode='emulator',repository=repo,blobs=blobs,adapters=SyntheticAdapters(blobs,SYNTHETIC_TEXT),identity_verifier=lambda token,appcheck:'synthetic-reviewer',memberships=repo.memberships,profile_registry=application_registry(True))
out=io.BytesIO();meta=PngImagePlugin.PngInfo();meta.add_text('independent_case',str(uuid4()));Image.new('RGB',(137,89),'blue').save(out,format='PNG',pnginfo=meta);data=out.getvalue();sha=hashlib.sha256(data).hexdigest()
with running_api(app) as http:
    r=http.post(PREFIX+'/batches',headers={**HEADERS,'Idempotency-Key':str(uuid4())},json={'collection_id':SYNTHETIC_COLLECTION,'display_name':'Independent four-way atomic race'});assert r.status_code==200,r.text
    batch=r.json()['batch_id'];pending=[];proposed=[]
    for i in range(4):
        r=http.post(PREFIX+f'/batches/{batch}/items',headers={**HEADERS,'Idempotency-Key':str(uuid4())},json={'client_item_id':str(uuid4()),'filename':'independent-race.png','media_type':'image/png','size_bytes':len(data),'sha256':sha,'width':137,'height':89});assert r.status_code==200,r.text
        item=r.json();assert item['state']=='uploading';proposed.append(item['specimen_id'])
        chunk=http.put(item['upload_url'],headers=HEADERS,content=data);assert chunk.status_code==200,chunk.text
        pending.append((PREFIX+f"/uploads/{item['upload_id']}/complete",{'expected_revision':chunk.json()['revision']},{**HEADERS,'Idempotency-Key':str(uuid4())}))
    def complete(args):return http.post(args[0],json=args[1],headers=args[2])
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(complete,pending))
    assert all(r.status_code==200 for r in results),[(r.status_code,r.text) for r in results]
    bodies=[r.json() for r in results];ids={b['specimen_id'] for b in bodies};assert len(ids)==1 and len(set(proposed))==4
    assert sum(b.get('upload_state')=='duplicate' for b in bodies)==3,bodies
    for args,r in zip(pending,results):assert complete(args).json()==r.json()
    # Completion identity intentionally includes its key; changed keys must conflict.
    for args,r in zip(pending,results):assert http.post(args[0],json=args[1],headers={**args[2],'Idempotency-Key':str(uuid4())}).status_code==409
actor_uid.set('synthetic-reviewer');scope=Scope(organization_id=SYNTHETIC_ORG,collection_id=SYNTHETIC_COLLECTION);principal=Principal(user_id='synthetic-reviewer',scope=scope,role='reviewer');ident=next(iter(ids));specimen=repo.get(scope,ident)
assert specimen.version==1 and len(repo.find_checksum(scope,sha,True))==1
bad=specimen.model_copy(deep=True);bad.asset.sha256='a'*64
try:repo.save(principal,bad,1,'bad-checksum-'+str(uuid4()),digest('bad'));raise AssertionError('Changed checksum accepted')
except Conflict:pass
assert repo.get(scope,ident).version==1
valid=specimen.model_copy(deep=True);valid.run.blocker='qa_verification_only'
saved=repo.save(principal,valid,1,'valid-save-'+str(uuid4()),digest('valid'));assert saved.version==2 and saved.asset.sha256==sha
assert operations.count('CreateSpecimenV3')==4 and 'SaveSpecimenV3' in operations
assert not any(name in operations for name in ('CreateSpecimenV2','SaveSpecimenV2','CreateSpecimen','SaveSpecimen'))
result={'pass':True,'actual_transport':'HTTP API plus SQL Connect/PostgreSQL','forced_concurrent_v3_creates':4,'distinct_proposed_ids':len(set(proposed)),'committed_specimens':1,'authorized_duplicate_results':3,'original_key_replays_exact':True,'changed_key_completion_rejected':True,'before_valid_save_revision':1,'invalid_checksum_save_rejected':True,'valid_v3_save_revision':saved.version,'no_legacy_create_save_calls':True,'specimen_id':ident,'operation_counts':{name:operations.count(name) for name in sorted(set(operations))}}
(root/'race-results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
