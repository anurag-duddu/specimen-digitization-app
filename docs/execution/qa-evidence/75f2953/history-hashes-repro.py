import json,httpx,uuid
from pathlib import Path
from specimen_digitization.application.storage import digest
p=Path(Path('/tmp/specimen-qa-current-path').read_text());old=json.loads((p/'pre-b04-raw-snapshots.json').read_text());c=httpx.Client(base_url='http://127.0.0.1:8124',headers={'Authorization':'Bearer '+(p/'token').read_text()},timeout=45);results=[]
for ident,prior in old.items():
 path='/v1/organizations/00000000-0000-4000-8000-000000000001/specimens/'+ident;page=c.get(path+'/history',params={'limit':50,'through_revision':28});page.raise_for_status();items=page.json()['items'];assert len(items)==28
 for row,item in zip(prior['snapshots'],items):
  assert row['revision']==item['revision'] and row['sha256']==item['sha256']
  rawrun=row['snapshot']['run'];ref=c.get(path+'/history/'+str(row['revision']),params={'run_id':rawrun['id'],'run_sha256':digest(rawrun)});ref.raise_for_status();assert ref.json()['revision']==row['revision']
 results.append({'specimen_id':ident,'original_stored_SHA_matches':28,'original_raw_run_refs_resolve':28,'passed':True})
 # Page bound remains frozen while a current review creates another revision.
 current=c.get(path+'/workspace').json();bound=current['revision'];frozen=c.get(path+'/history',params={'after_revision':bound-2,'through_revision':bound}).json()
 r=c.post(path+'/decisions',headers={'Idempotency-Key':str(uuid.uuid4())},json={'kind':'approve','reason':'Independent QA original retained hash check','expected_revision':bound,'base_record_version_id':current['record_version_id']});r.raise_for_status()
 assert c.get(path+'/history',params={'after_revision':bound-2,'through_revision':bound}).json()==frozen
 after=c.get(path+'/workspace').json();ref=after['events'][-1]['before'];assert ref['revision']==bound;resolved=c.get(ref['history_url']);resolved.raise_for_status();assert digest(current['run'])==ref['run_sha256']
 results.append({'specimen_id':ident,'frozen_page_unchanged_across_new_review':True,'new_review_before_ref_resolves':True,'passed':True})
c.close();(p/'history-hash-evidence.json').write_text(json.dumps({'candidate':'75f2953','transport':'actualTCP8124SQL9519; compared independently captured originalrawrows before repair','results':results},indent=2)+'\n');print(json.dumps(results,indent=2))
