import json,hashlib
from pathlib import Path
from copy import deepcopy
import httpx
from specimen_digitization.application.domain import Scope
from specimen_digitization.application.storage import SQLiteRepository,LocalBlobs
from specimen_digitization.application.profile_runtime import pinned_risk_resolution
from specimen_digitization.application.classifier_runtime import ConfiguredClassifier
from specimen_digitization.application.classification import ClassificationRequest
from specimen_digitization.application.collection_runtime import application_registry
from specimen_digitization.application.hf_collection_classifier import HFClassifierConfig
root=Path('/var/folders/nq/t4rvrkyx2dx2293cx4bn8gfm0000gn/T/specimen-runtime-wire-6st4c5ok');f=json.loads(Path('/tmp/specimen-qa-ee4bec8-runtime.json').read_text());heads={'Authorization':'Bearer test-only-local-token'};out={}
for name,port,key in [('policies',8124,'profile_variants'),('telemetry',8126,'observation_telemetry')]:
 work=f[key]['second' if name=='policies' else 'workspace'];scope=Scope(organization_id=work['organization_id'],collection_id=work['collection_id']);p='/v1/organizations/'+scope.organization_id+'/specimens/'+work['specimen_id'];c=httpx.Client(base_url=f'http://127.0.0.1:{port}',headers=heads)
 current=c.get(p+'/workspace');assert current.status_code==200;w=current.json();assert w['run']==work['run'];risk=w['run']['review_risk'];assert risk['composite'] is None and not risk['clearance_authority'];assert all(x['composite'] is None for k in ['labels','fields'] for x in risk[k]);assert risk['status']=='unmeasured'
 row=SQLiteRepository(root/name/'state.db').get(scope,work['specimen_id']);assert pinned_risk_resolution(row.run).status=='resolved'
 for field,edit in [('profile_rules',lambda v:v.update(profile_version='invalid')),('risk_policy_snapshot',lambda v:v['policy'].update(version='invalid')),('profile_snapshot',lambda v:v.update(version='invalid'))]:
  run=deepcopy(row.run);edit(getattr(run,field));assert pinned_risk_resolution(run).status=='blocked'
 run=deepcopy(row.run);run.risk_policy_snapshot={};assert pinned_risk_resolution(run).status=='blocked'
 if name=='policies':
  q='/v1/organizations/'+scope.organization_id+'/specimens';args={'collection_id':scope.collection_id};unfiltered=c.get(q,params=args).json();bounded=c.get(q,params={**args,'risk_min':0,'risk_max':100}).json();assert len(unfiltered['items'])==1 and unfiltered['items'][0]['risk'] is None and bounded['items']==[]
  old=f[key]['first'];hist=c.get(p+'/history/'+str(old['revision'])).json();assert hist['run']==old['run'];assert old['run']['review_risk']['policy_reference']!=risk['policy_reference'];assert [sum(x['contribution'] for x in v['run']['review_risk']['labels'][0]['components']) for v in [old,w]]==[40,60]
  assert [q['prompt'] for q in f[key]['sam_requests']]==['label','paper specimen labels'];assert all(q['parameters']=={} for q in f[key]['sam_requests'])
 else:
  assert len(w['observations'])==2;assert len({o['route_id'] for o in w['observations']})==2
  for o in w['observations']:
   assert o['latency_seconds']>0 and o['latency_basis']=='validated_agent_call_wall_seconds';assert o['finish_state']=='stop' and o['parameters'] is None and o['provider_model_id']=='synthetic-model-runtime';assert o['completion_state']=='validated_output'
   raw=c.get(p+'/observations/'+o['id']+'/raw').content;assert hashlib.sha256(raw).hexdigest()==o['raw_sha256']
 out[name]={'revision':w['revision'],'exact_fresh_execution_readback':True,'all_scoped_composites_null':True,'four_policy_tamper_classes_blocked':True}
# No configuration/unapproved config must not invoke even the injected child helper.
work=f['configured_classifier']['workspace'];scope=Scope(organization_id=work['organization_id'],collection_id=work['collection_id']);row=SQLiteRepository(root/'classifier'/'state.db').get(scope,work['specimen_id']);reg=application_registry(True);req=ClassificationRequest(asset_id=row.asset.id,input_sha256=row.asset.sha256,collection_ids=tuple(n.id for n in reg.nodes))
config=HFClassifierConfig(route_id='qa-denied',expected_model_id='fixture/none',expected_provider='novita',prompt_text='synthetic test',prompt_version='1',approved=False)
for cfg in [None,config]:
 facade=ConfiguredClassifier(LocalBlobs(root/'classifier'/'blobs'),cfg,effect=lambda p: (_ for _ in ()).throw(AssertionError('Must not invoke model')));row.run.dependencies['classifier']=facade.pin(row.run);result=facade.bind(row,reg).classify(req);assert result.status=='blocked' and result.reason=='approved_classifier_route_missing'
out['classifier_unconfigured_unapproved_no_child']=True
Path('/tmp/specimen-qa-ee4bec8-independent-results.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
