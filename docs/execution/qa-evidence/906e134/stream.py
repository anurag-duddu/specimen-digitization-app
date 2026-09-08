import sys,json,hashlib,threading
from pathlib import Path
from types import SimpleNamespace
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import requests
from specimen_digitization.application.production import GcsBlobs
from specimen_digitization.application.storage import Conflict,Missing
from specimen_digitization.application.blob_limits import BlobTooLarge
from specimen_digitization.application.workflow import OperationalBlock
root=Path(Path('/tmp/specimen-qa-hardening-path').read_text().strip());state={'body':b'complete','length':None,'status':200,'paths':[]};reads=[];responses=[];results=[]
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  state['paths'].append(self.path);self.send_response(state['status'])
  if state['length'] is not None:self.send_header('Content-Length',str(state['length']))
  if state['status']==302:self.send_header('Location','/should-never-follow')
  self.end_headers()
  try:self.wfile.write(state['body'])
  except (BrokenPipeError,ConnectionResetError):pass
 def log_message(self,*a):pass
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
class Transport:
 def get(self,url,**kwargs):
  assert kwargs['stream'] and kwargs['allow_redirects'] is False and kwargs['headers']['Accept-Encoding']=='identity'
  assert kwargs['params']['generation']=='12345'
  response=requests.get(f'http://127.0.0.1:{server.server_port}/object',**kwargs);responses.append(response);original=response.raw.read
  def read(*a,**kw):
   data=original(*a,**kw);reads.append({'requested':a[0],'returned':len(data)});return data
  response.raw.read=read;return response
blobs=GcsBlobs.__new__(GcsBlobs);blobs.bucket=SimpleNamespace(name='synthetic-bucket',client=SimpleNamespace(_http=Transport()));ref=hashlib.sha256(b'complete').hexdigest()+':12345'
cases=[('exact',b'complete',None,200,8,None),('overshoot',b'x'*100000,None,200,257,BlobTooLarge),('declared_oversize',b'x'*100000,100000,200,257,BlobTooLarge),('underdeclared',b'complete',3,200,8,Conflict),('digest_mismatch',b'tampered',None,200,8,Conflict),('invalid_length',b'complete','invalid',200,8,OperationalBlock),('redirect',b'',0,302,8,OperationalBlock),('missing',b'',0,404,8,Missing)]
try:
 for name,body,length,status,cap,error in cases:
  state.update(body=body,length=length,status=status);reads.clear();before=len(state['paths'])
  try:
   content=blobs.get_bounded(ref,cap);assert error is None and content==b'complete',name;outcome='complete'
  except Exception as exc:
   assert error is not None and isinstance(exc,error),(name,type(exc),str(exc));outcome=type(exc).__name__
  assert sum(r['returned'] for r in reads)<=cap+1
  assert responses[-1].raw.closed and len(state['paths'])==before+1
  assert 'generation=12345' in state['paths'][-1]
  results.append({'scenario':name,'pass':True,'outcome':outcome,'cap':cap,'application_bytes_read':sum(r['returned'] for r in reads),'requests':1,'response_closed':True})
finally:server.shutdown();server.server_close();thread.join()
(root/'stream-results.json').write_text(json.dumps(results,indent=2));print(json.dumps(results))
