import json,tempfile,sys
from pathlib import Path
sys.path.insert(0,str(Path('tests').resolve()))
from test_application import client,intake,HEADERS,PREFIX
root=Path(tempfile.mkdtemp(prefix='specimen-qa-corrupt-own-'));c=client(root);s=intake(c);path=PREFIX+'/specimens/'+s['specimen_id'];before=c.get(path+'/workspace',headers=HEADERS).json();ref=before['observations'][0]['raw_ref'];source=root/'blobs'/ref;original=source.read_bytes();quarantine=root/'quarantined-raw';source.rename(quarantine)
body={'kind':'approve','expected_revision':before['revision'],'base_record_version_id':before['record_version_id'],'reason':'QA synthetic corruption negative: raw evidence is unavailable'}
response=c.post(path+'/decisions',headers={**HEADERS,'Idempotency-Key':'qa-corruption-approval'},json=body)
result={'case':'missing_raw_blob_at_finalization','mode':'synthetic-local-SQLite','injection':'Moved one own temporary raw-response blob to retained quarantine; no DB edits','missing_before_approval':not source.exists(),'http':response.status_code,'disposition':response.json().get('disposition'),'reason_codes':response.json().get('reason_codes'),'expected':'not cleared','passed':response.json().get('disposition')!='cleared','specimen_id':s['specimen_id'],'raw_ref':ref,'quarantine':str(quarantine)}
p=Path(Path('/tmp/specimen-qa-current-path').read_text());(p/'missing-raw-evidence.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2));c.close()
