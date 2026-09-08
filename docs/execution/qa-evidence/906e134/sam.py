import sys,json,os,time,threading,tempfile
from pathlib import Path
from datetime import datetime,timedelta
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
sys.path.insert(0,str(Path.cwd()/'tests'))
from test_worker_recovery import setup
from test_sam3_runtime import local_sam_effect
from specimen_digitization.application.production import Sam3Service
from specimen_digitization.application.workflow import Workflow,SyntheticAdapters
from specimen_digitization.application.storage import digest,SQLiteRepository
from specimen_digitization.application import bounded_effect
root=Path(Path('/tmp/specimen-qa-hardening-path').read_text().strip());results=[]
for scenario in ['auth_delay','drip','oversize','http_401']:
 state={'requests':0};observed=[];before=set(Path(tempfile.gettempdir()).glob('specimen-effect-*'))
 class Handler(BaseHTTPRequestHandler):
  def do_POST(self):
   state['requests']+=1;self.rfile.read(int(self.headers['Content-Length']))
   self.send_response(401 if scenario=='http_401' else 200)
   self.end_headers()
   try:
    if scenario=='drip':
     for _ in range(100):self.wfile.write(b' ');self.wfile.flush();time.sleep(.08)
    elif scenario=='oversize':self.wfile.write(b'x'*(1024*1024+16384))
    else:self.wfile.write(b'controlled synthetic unauthorized')
   except (BrokenPipeError,ConnectionResetError):pass
  def log_message(self,*a):pass
 server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 os.environ['SPECIMEN_TEST_SAM_ORIGIN']=f'http://127.0.0.1:{server.server_port}'
 os.environ['SPECIMEN_TEST_SAM_AUTH_DELAY']='12' if scenario=='auth_delay' else '0'
 repo,blobs,p,items=setup(root/scenario);item=items[0];item.run.completed_steps=['pin_dependencies','classify','quality_check'];item.run.profile.execution.external_timeout_seconds=3;item=repo.save(p,item,item.version,'ready',digest('ready'))
 original=bounded_effect.run_isolated
 def recording(*a,**kw):
  result=original(*a,**kw);observed.append(result);return result
 bounded_effect.run_isolated=recording
 class Adapter(SyntheticAdapters):
  def segment(self,s):return Sam3Service('https://synthetic.run.app',blobs,effect=local_sam_effect).segment(s)
 try:
  start=time.monotonic();w=Workflow(repo,blobs,Adapter(blobs,'synthetic')).step(p,item.id);elapsed=time.monotonic()-start
  assert elapsed<6 and len(observed)==1,(elapsed,observed)
  effect=observed[0];assert effect.cleanup_complete
  try:os.kill(effect.worker_pid,0);raise AssertionError('Effect child survived')
  except ProcessLookupError:pass
  calls=state['requests'];assert calls==(0 if scenario=='auth_delay' else 1)
  expected='sam3_http_error' if scenario=='http_401' else 'external_outcome_unknown'
  assert w.run.blocker==expected and w.run.disposition is None,(scenario,w.run.blocker)
  # Restart both repository and workflow, then advance beyond the retained lease.
  future=datetime.fromisoformat(w.run.lease_until)+timedelta(seconds=1) if w.run.lease_until else datetime.now().astimezone()+timedelta(minutes=10)
  for _ in range(3):
   fresh=Workflow(SQLiteRepository(repo.path),blobs,Adapter(blobs,'synthetic'),clock=lambda:future).step(p,item.id)
   assert state['requests']==calls and fresh.run.blocker==expected and fresh.run.disposition is None
  assert set(Path(tempfile.gettempdir()).glob('specimen-effect-*'))==before
  results.append({'scenario':scenario,'pass':True,'actual_tcp_requests':calls,'elapsed_seconds':elapsed,'isolated_status':effect.status,'worker_reaped':True,'private_ipc_cleaned':True,'retained_blocker':w.run.blocker,'restart_after_lease_no_repeat':True,'external_calls_reserved':w.run.usage.external_calls})
 finally:
  bounded_effect.run_isolated=original;server.shutdown();server.server_close();thread.join()
(root/'sam-results.json').write_text(json.dumps(results,indent=2));print(json.dumps(results))
