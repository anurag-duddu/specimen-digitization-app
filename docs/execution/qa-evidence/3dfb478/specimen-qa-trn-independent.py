import sys,json,tempfile
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'tests'))
from test_reading_declarations_runtime import app_at,DeclaredAdapters
from test_application import intake,HEADERS,PREFIX,TOKEN,SYNTHETIC_ORG,SYNTHETIC_COLLECTION
from specimen_digitization.application.api import create_app
from specimen_digitization.application.storage import SQLiteRepository,LocalBlobs
from fastapi.testclient import TestClient
root=Path(tempfile.mkdtemp(prefix='specimen-qa-trn-'));results={}
for mode,expected in [('mixed',(True,False)),('conflicting',(False,True)),('unknown',(False,False))]:
 r=root/mode
 with TestClient(app_at(r,mode)) as c:
  row=intake(c);path=PREFIX+'/specimens/'+row['specimen_id'];w=c.get(path+'/workspace',headers=HEADERS).json();obs=w['observations'][0];op=path+'/observations/'+obs['id'];original=c.get(op+'/declarations',headers=HEADERS).json();raw=c.get(op+'/raw',headers=HEADERS).content;lab=w['run']['label_language_handling']['labels'][0];assert (lab['mixed_declared'],lab['conflicting_candidates'])==expected;assert lab['unmeasured'] and w['run']['label_language_handling']['confidence'] is None
  base=w['revision'];body={'kind':'reading_metadata','target_id':obs['id'],'after':{'language_candidates':['French'],'script_candidates':['Latin']},'reason':'Independent synthetic declaration','expected_revision':base,'base_record_version_id':w['record_version_id']}
  invalid=[{**body,'reason':'  '},{**body,'after':{'actor':'spoofed'}},{**body,'after':{'reported_confidence':.99}},{**body,'after':{'language_candidates':['x']*9}},{**body,'after':{'language_candidates':['x'*101]}},{**body,'after':{'language_candidates':['English',' English ']}},{**body,'after':{'language_candidates':['French'],'language_relation':'cooccurring'}}]
  for i,bad in enumerate(invalid):
   resp=c.post(path+'/decisions',headers={**HEADERS,'Idempotency-Key':f'invalid-{i}'},json=bad);assert resp.status_code==422,resp.text
   assert c.get(path,headers=HEADERS).json()['revision']==base
  approve=c.post(path+'/decisions',headers={**HEADERS,'Idempotency-Key':'initial-approval'},json={**body,'kind':'approve'});assert approve.status_code==200;w=approve.json();assert w['run']['human_approved']
  preserved=w['run']['phase_results'];authority=w['run']['authority_receipts']
  for i,langs in enumerate([['French'],['日本語','English'],[]]):
   b={**body,'after':{'language_candidates':langs,'script_candidates':['Latin'],'language_relation':'cooccurring' if len(langs)>1 else 'unspecified'},'expected_revision':w['revision'],'base_record_version_id':w['record_version_id']};h={**HEADERS,'Idempotency-Key':f'valid-{i}'}
   resp=c.post(path+'/decisions',headers=h,json=b);assert resp.status_code==200,resp.text;new=resp.json();assert new['revision']==w['revision']+1 and not new['run']['human_approved'];assert new['observations']==w['observations'] and new['run']['phase_results']==preserved and new['run']['authority_receipts']==authority
   assert c.post(path+'/decisions',headers=h,json=b).json()==new
   assert c.post(path+'/decisions',headers={**h,'Idempotency-Key':f'stale-{i}'},json=b).status_code==409
   w=new
  lineage=c.get(op+'/declarations',headers=HEADERS).json();hist=lineage['human_history'];assert len(hist)==3 and hist[2]['supersedes']==hist[1]['id'] and hist[1]['supersedes']==hist[0]['id'];assert all(x['actor']=='synthetic-reviewer' and x['reason']==body['reason'] for x in hist);assert lineage['model']==original['model'];assert c.get(op+'/raw',headers=HEADERS).content==raw
  old=c.get(op+f'/declarations?revision={base}',headers=HEADERS).json();assert old['human_history']==[] and old['model']==original['model']
 # Same persisted state, injected local identity and mutable membership; no Firebase claim.
 access={'role':'viewer','active':True,'sensitive':True};b=LocalBlobs(r/'blobs');repo=SQLiteRepository(r/'state.db')
 app=create_app(mode='emulator',repository=repo,blobs=b,adapters=DeclaredAdapters(b,mode),identity_verifier=lambda bearer,check:'independent-user',memberships=lambda user:[{'organization_id':SYNTHETIC_ORG,'collection_id':SYNTHETIC_COLLECTION,'role':access['role'],'can_view_sensitive':access['sensitive']}] if access['active'] else [])
 with TestClient(app) as c:
  for role in ['viewer','operator']:
   access['role']=role;view=c.get(path+'/workspace',headers=HEADERS).json();assert 'reading_metadata' not in view['available_actions'];resp=c.post(path+'/decisions',headers=HEADERS,json={**body,'expected_revision':w['revision'],'base_record_version_id':w['record_version_id']});assert resp.status_code==403
  access['role']='reviewer';assert c.get(op+'/declarations',headers=HEADERS).status_code==200
  access['active']=False
  for suffix in ['',f'?revision={base}']:assert c.get(op+'/declarations'+suffix,headers=HEADERS).status_code in (403,404)
  access['active']=True;assert c.get(op+f'/declarations?revision={base}',headers=HEADERS).json()==old
 results[mode]={'initial_revision':base,'final_revision':w['revision'],'invalid_cases_no_mutation':len(invalid),'human_history':3,'raw_model_phases_authority_preserved':True,'approval_invalidated':True,'viewer_operator_write_denied':True,'current_and_historical_revocation':True}
(root/'results.json').write_text(json.dumps(results,indent=2)+'\n');Path('/tmp/specimen-qa-trn-independent-path').write_text(str(root));print(json.dumps(results))
