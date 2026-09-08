import json,os,uuid
from pathlib import Path
from specimen_digitization.application.domain import *
from specimen_digitization.application.api import SYNTHETIC_ORG,SYNTHETIC_COLLECTION
from specimen_digitization.application.production import SqlConnectRepository,actor_uid
from specimen_digitization.application.storage import SQLiteRepository,SnapshotTooLarge,digest,Missing
from specimen_digitization.application.policy import evaluate,finalize
p=Path(Path('/tmp/specimen-qa-current-path').read_text()); actor_uid.set('synthetic-reviewer')
scope=Scope(organization_id=SYNTHETIC_ORG,collection_id=SYNTHETIC_COLLECTION);principal=Principal(user_id='synthetic-reviewer',scope=scope,role='reviewer')
results=[]
for transport,repo in [('sqlite',SQLiteRepository(p/'boundary.sqlite3')),('sql_connect',SqlConnectRepository(project='demo-specimen-data',emulator_host='127.0.0.1:9519'))]:
 for target in (262143,262144,262145):
  specimen=Specimen(scope=scope,asset=Asset(sha256=digest(str(uuid.uuid4())),blob_ref='a'*64,media_type='image/png',size_bytes=1,width=1,height=1,filename='boundary-synthetic.png',uploader='synthetic-reviewer'),run=Run(),audit=[AuditEvent(actor='synthetic-reviewer',action='boundary_test',reason='é😀"\\\n')])
  specimen.audit[0].reason += 'x'*(target-len(specimen.model_dump_json().encode()))
  assert len(specimen.model_dump_json().encode())==target
  key=str(uuid.uuid4());status='accepted'
  try: saved=repo.create(principal,specimen,key,digest({'case':key}))
  except SnapshotTooLarge: status='rejected'
  expected='accepted' if target<=262144 else 'rejected'
  results.append({'transport':transport,'bytes':target,'expected':expected,'actual':status,'passed':status==expected})
  if status=='accepted':
   assert repo.get(scope,specimen.id)==saved
   old=saved.version; mutation=saved.model_copy(deep=True);mutation.audit[0].reason+='🦋'*10
   try: repo.save(principal,mutation,old,'oversize-'+key,digest({'over':key})); outcome='accepted'
   except SnapshotTooLarge: outcome='rejected'
   results.append({'transport':transport,'case':'overlimit_save_atomic','passed':outcome=='rejected' and repo.get(scope,specimen.id)==saved})
  else:
   try: repo.get(scope,specimen.id);absent=False
   except Missing: absent=True
   # A corrected request under the rejected key proves no success receipt survived.
   specimen.audit[0].reason='corrected synthetic fixture'
   saved=repo.create(principal,specimen,key,digest({'corrected':key}))
   results.append({'transport':transport,'case':'rejected_create_no_record_or_receipt','passed':absent and saved.version==1})
(p/'history-boundary-evidence.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results,indent=2))
