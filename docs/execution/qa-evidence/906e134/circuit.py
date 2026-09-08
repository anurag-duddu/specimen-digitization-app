import sys,json,time,subprocess,hashlib
from pathlib import Path
from datetime import datetime,timedelta,timezone
from uuid import uuid4
from specimen_digitization.application.production import SqlConnectRepository,actor_uid
from specimen_digitization.application.api import SYNTHETIC_ORG,SYNTHETIC_COLLECTION
from specimen_digitization.application.domain import Scope
from specimen_digitization.application.circuit_runtime import RepositoryCircuitStore
from specimen_digitization.application.provider_circuit import ProviderCircuit,CircuitKey,PermitToken
root=Path(Path('/tmp/specimen-qa-hardening-path').read_text().strip())/'circuit';root.mkdir(exist_ok=True)
scope=Scope(organization_id=SYNTHETIC_ORG,collection_id=SYNTHETIC_COLLECTION)
def store():
 actor_uid.set('synthetic-reviewer');return RepositoryCircuitStore(SqlConnectRepository(project='demo-specimen-data',emulator_host='127.0.0.1:9519'),scope)
if len(sys.argv)>1:
 config=json.loads((root/'config.json').read_text());key=CircuitKey.model_validate(config['key']);clock=datetime.fromisoformat(config['time']);s=store();load=s.load;first=[True]
 def synchronized_load(k):
  value=load(k)
  if first[0]:
   first[0]=False;(root/('ready-'+sys.argv[1])).touch();deadline=time.monotonic()+15
   while not (root/'go').exists():
    assert time.monotonic()<deadline;time.sleep(.01)
  return value
 s.load=synchronized_load
 result=ProviderCircuit(s,lambda:clock).admit(key,45)
 print(result.model_dump_json());sys.exit(0)
clock=[datetime.now(timezone.utc)];key=CircuitKey(organization_id=SYNTHETIC_ORG,collection_id=SYNTHETIC_COLLECTION,provider='qa-shared-process',config_sha256=hashlib.sha256(str(uuid4()).encode()).hexdigest());c=ProviderCircuit(store(),lambda:clock[0])
for _ in range(3):
 a=c.admit(key,45);assert a.status=='permitted';assert c.record_failure(a.token,'timeout').status=='recorded'
assert ProviderCircuit(store(),lambda:clock[0]).admit(key,45).status=='open'
clock[0]+=timedelta(seconds=31);(root/'config.json').write_text(json.dumps({'key':key.model_dump(),'time':clock[0].isoformat()}))
children=[subprocess.Popen([sys.executable,__file__,str(i)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for i in range(4)]
try:
 deadline=time.monotonic()+20
 while len(list(root.glob('ready-*')))<4:
  assert time.monotonic()<deadline;time.sleep(.03)
 (root/'go').touch();outputs=[]
 for process in children:
  out,err=process.communicate(timeout=20);assert process.returncode==0,err;outputs.append(json.loads(out))
finally:
 for process in children:
  if process.poll() is None:process.kill();process.wait()
assert [o['status'] for o in outputs].count('permitted')==1 and [o['status'] for o in outputs].count('busy')==3,outputs
probe=PermitToken.model_validate(next(o['token'] for o in outputs if o['status']=='permitted'))
assert ProviderCircuit(store(),lambda:clock[0]).admit(key,45).status=='busy'
clock[0]+=timedelta(seconds=46);expired=ProviderCircuit(store(),lambda:clock[0]).admit(key,45);assert expired.status=='open'
assert c.record_success(probe).status=='stale'
clock[0]+=timedelta(seconds=61);fresh=ProviderCircuit(store(),lambda:clock[0]);new=fresh.admit(key,45);assert new.status=='permitted';assert fresh.record_success(new.token).status=='recorded'
closed=ProviderCircuit(store(),lambda:clock[0]);normal=closed.admit(key,45);assert normal.status=='permitted' and not normal.token.probe
assert closed.record_failure(normal.token,'rate_limited',retry_after=600).status=='recorded';clock[0]+=timedelta(seconds=599);assert ProviderCircuit(store(),lambda:clock[0]).admit(key,45).status=='open';clock[0]+=timedelta(seconds=1);assert ProviderCircuit(store(),lambda:clock[0]).admit(key,45).status=='permitted'
result={'pass':True,'persistence':'actual SQL Connect/PostgreSQL worker_cursor CAS under same synthetic owner identity','independent_interpreters':4,'synchronized_initial_load':True,'half_open_permitted':1,'half_open_busy':3,'fresh_interpreter_state_retained':True,'expired_probe_reopens':True,'late_probe_success_rejected':True,'probe_success_closes':True,'provider_minimum_600s_preserved':True,'all_child_processes_reaped':True}
(root.parent/'circuit-results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
