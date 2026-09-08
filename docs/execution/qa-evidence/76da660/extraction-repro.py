import sys,tempfile,json,hashlib
from pathlib import Path
sys.path.insert(0,str(Path('tests').resolve()))
from test_application import client,intake
from specimen_digitization.application.domain import Scope
from specimen_digitization.application.api import local_app
from specimen_digitization.application.harness import extract_with_agent
from specimen_digitization.application.integrity import verify_evidence,EvidenceIntegrityError
from specimen_digitization.application.workflow import crop_bytes
from specimen_digitization.application.storage import LocalBlobs
from pydantic_ai.models.test import TestModel
root=Path(tempfile.mkdtemp(prefix='specimen-qa-extraction-'));c=client(root);row=intake(c);repo=c.app.state.workflow.repository;s=repo.get(Scope(organization_id=row['organization_id'],collection_id=row['collection_id']),row['specimen_id']);blobs=LocalBlobs(root/'blobs');s.run.profile.synthetic=False
for o in s.run.observations:
 r=next(r for r in s.run.regions if r.id==o.region_id);o.input_sha256=hashlib.sha256(crop_bytes(blobs,s,r)).hexdigest()
class FixtureGateway:
 def model_for(self,route):
  return TestModel(custom_output_args={'candidates':[{'field_key':'country','region_id':s.run.regions[0].id,'literal':'United States','source_excerpt':'country: United States'}],'unresolved':[]})
extract_with_agent(FixtureGateway(),blobs,s);e=s.run.evidence[-1];raw=blobs.get(e.raw_ref);assert e.source=='bounded_extraction_v1';assert e.digest==hashlib.sha256(raw).hexdigest();verify_evidence(s,blobs)
results={'candidate':'76da660','boundary':'actual extract_with_agent and real PydanticAI Agent with TestModel; local retained blobs, no live provider','production_profile':not s.run.profile.synthetic,'response_bytes':len(raw),'computed_digest_matches_retained_bytes':True,'positive_integrity_passed':True}
f=root/'blobs'/e.raw_ref
try:
 f.write_bytes(b'QA corrupted extraction response')
 try:verify_evidence(s,blobs);raise AssertionError('corrupt extraction accepted')
 except EvidenceIntegrityError:results['corrupt_extraction_blocked']=True
finally:f.write_bytes(raw)
verify_evidence(s,blobs);results['restored_extraction_passed']=True;c.close();p=Path(Path('/tmp/specimen-qa-current-path').read_text());(p/'extraction-evidence.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results,indent=2))
