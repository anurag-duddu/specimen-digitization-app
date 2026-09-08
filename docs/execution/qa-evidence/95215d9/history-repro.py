import json,uuid,hashlib,time
from pathlib import Path
import httpx
from specimen_digitization.application.production import SqlConnectRepository,actor_uid
from specimen_digitization.application.domain import Scope
from specimen_digitization.application.api import SYNTHETIC_ORG,SYNTHETIC_COLLECTION
from specimen_digitization.application.storage import digest
p=Path(Path('/tmp/specimen-qa-current-path').read_text());token=(p/'token').read_text();c=httpx.Client(base_url='http://127.0.0.1:8124',headers={'Authorization':'Bearer '+token},timeout=90);repo=SqlConnectRepository(project='demo-specimen-data',emulator_host='127.0.0.1:9519');actor_uid.set('synthetic-reviewer');scope=Scope(organization_id=SYNTHETIC_ORG,collection_id=SYNTHETIC_COLLECTION);prefix=f'/v1/organizations/{SYNTHETIC_ORG}';old=json.loads((p/'pre-b04-raw-snapshots.json').read_text());results=[];checkpoints={}
def get(path,**kw):
 r=c.get(path,**kw);r.raise_for_status();return r.json()
def record(case,passed,**extra):
 results.append({'case':case,'passed':passed,**extra});print(case,passed,flush=True);assert passed
for ix,(ident,baseline) in enumerate(old.items()):
 path=prefix+'/specimens/'+ident;before=get(path+'/workspace');expected_events={e['sequence']:e for e in before['events']};rawfile=p/'api-state'/'blobs'/before['observations'][0]['raw_ref'];raw=rawfile.read_bytes();first=None;maxsize=0;sizes=[]
 try:
  # Existing near-cap records recover first; then at least100 ordinary approvals,
  # plus110 alternating missing/restored evidence approvals on the blocked fixture.
  for step in range(211 if ix==0 else 101):
   if ix==0 and step>=101 and step%2==1:rawfile.unlink()
   else:rawfile.write_bytes(raw)
   current=get(path+'/workspace');body={'kind':'approve','expected_revision':current['revision'],'base_record_version_id':current['record_version_id'],'reason':'Independent QA bounded history verification'};key=str(uuid.uuid4());r=c.post(path+'/decisions',headers={'Idempotency-Key':key},json=body);r.raise_for_status();after=r.json()
   expected=None if ix==0 and step>=101 and step%2==1 else 'cleared'
   assert after.get('disposition')==expected,(step,after)
   if step==0:first=(body,key,after);record(ident+'_legacy_recovered',after['disposition']=='cleared')
   state=repo.get(scope,ident);n=len(state.model_dump_json().encode());maxsize=max(n,maxsize);sizes.append(n)
   current=get(path+'/workspace')
   for e in current['events']:
    if e['sequence'] in expected_events:assert expected_events[e['sequence']]==e
    else:expected_events[e['sequence']]=e
  record(ident+'_continued_reviews',True,approvals=len(sizes),max_snapshot_bytes=maxsize,last_snapshot_bytes=sizes[-1])
 finally:rawfile.write_bytes(raw)
 current=get(path+'/workspace');through=current['revision'];after_cursor=0;revisions=[];history_events={};page_count=0
 while True:
  page=get(path+'/history',params={'after_revision':after_cursor,'through_revision':through,'limit':13});assert page['through_revision']==through;page_count+=1
  for item in page['items']:
   rev=item['revision'];revisions.append(rev);historic=get(path+'/history/'+str(rev));stored=repo.version(scope,ident,rev);assert digest(stored.model_dump(mode='json'))==item['sha256']
   for e in historic['events']:
    if e['sequence'] in history_events:assert history_events[e['sequence']]==e
    else:history_events[e['sequence']]=e
  if page['next_cursor'] is None:break
  assert page['next_cursor']>after_cursor;after_cursor=page['next_cursor']
 record(ident+'_all_revision_pages',revisions==list(range(1,through+1)),count=len(revisions),pages=page_count)
 record(ident+'_audit_sequence_complete',history_events==expected_events and sorted(history_events)==list(range(1,max(history_events)+1)),events=len(history_events))
 unchanged=[]
 for prior in baseline['snapshots']:
  now=repo.execute('GetSnapshot',dict(repo.variables(scope),id=ident,revision=prior['revision']))['specimenSnapshot'];unchanged.append(now==prior)
 record(ident+'_all_legacy_raw_snapshots_unchanged',all(unchanged),count=len(unchanged))
 body,key,response=first;replayed=c.post(path+'/decisions',headers={'Idempotency-Key':key},json=body);record(ident+'_original_receipt_stable',replayed.status_code==200 and replayed.json()==response)
 stale=c.post(path+'/decisions',headers={'Idempotency-Key':str(uuid.uuid4())},json=body);record(ident+'_stale_write_denied',stale.status_code==409)
 ref=current['events'][-1]['before'];history=get(ref['history_url']);record(ident+'_run_reference_resolves',digest(history['run'])==ref['run_sha256'])
 record(ident+'_wrong_run_digest_denied',c.get(path+'/history/'+str(through),params={'run_sha256':'wrong'}).status_code==409)
 record(ident+'_wrong_run_id_denied',c.get(path+'/history/'+str(through),params={'run_id':str(uuid.uuid4())}).status_code==409)
 record(ident+'_page_limit_denied',c.get(path+'/history',params={'limit':51}).status_code==422)
 # Retain exact workspaces and one history page for process-restart comparison.
 checkpoints[ident]={'workspace':get(path+'/workspace'),'page':get(path+'/history',params={'through_revision':through,'limit':7}),'old_workspace':get(path+'/history/28')}
(p/'history-restart-checkpoints.json').write_text(json.dumps(checkpoints));(p/'history-evidence.json').write_text(json.dumps({'candidate':'95215d9','transport':'actualTCP8124 SQL9519 PG5569 retained pre-repair database','results':results},indent=2)+'\n');c.close()
