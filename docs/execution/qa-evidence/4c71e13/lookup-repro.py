import json,threading
from pathlib import Path
from http.server import HTTPServer,BaseHTTPRequestHandler
import httpx
from specimen_digitization.application.lookup import GbifTaxonomy
from specimen_digitization.application.storage import LocalBlobs
p=Path(Path('/tmp/specimen-qa-current-path').read_text());scenario={'kind':'none'};captured=[]
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  captured.append(self.path)
  code=200;body=b'{}';headers={}
  if self.path.startswith('/v2/species/match/metadata'):body=b'{"synthetic_metadata":true}'
  elif scenario['kind']=='none':body=b'{"diagnostics":{"matchType":"NONE"}}'
  elif scenario['kind']=='empty':body=b''
  elif scenario['kind']=='ambiguous':body=b'{"diagnostics":{"matchType":"FUZZY","alternatives":[{"key":"synthetic:2"}]}}'
  elif scenario['kind']=='success':body=b'{"diagnostics":{"matchType":"EXACT"},"usage":{"key":"synthetic:1","rank":"SPECIES","scientificName":"Danaus plexippus"}}'
  elif scenario['kind']=='rate':code=429;headers={'Retry-After':'2'}
  elif scenario['kind']=='auth':code=401
  self.send_response(code)
  for k,v in headers.items():self.send_header(k,v)
  self.end_headers();self.wfile.write(body)
server=HTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever);thread.start()
class LocalAuthorityClient:
 def get(self,url,**kwargs):
  # Redirect adapter's fixed external destination only within this QA transport.
  assert url.startswith('https://api.gbif.org/')
  return httpx.get(f'http://127.0.0.1:{server.server_port}/'+url.split('org/',1)[1],**kwargs)
results=[]
try:
 for name,expected in [('none','no_match'),('empty','malformed_response'),('ambiguous','ambiguous'),('success','success'),('rate','rate_limited'),('auth','authentication_error')]:
  scenario['kind']=name;r=GbifTaxonomy(LocalBlobs(p/'lookup-blobs'),LocalAuthorityClient()).lookup('Danaus plexippus');results.append({'case':name,'expected':expected,'actual':r.status.value,'passed':r.status.value==expected,'raw_digest_verified':r.digest==r.raw_ref,'retry_after':r.retry_after_seconds})
finally:server.shutdown();thread.join();server.server_close()
(p/'lookup-local-http-evidence.json').write_text(json.dumps({'mode':'synthetic controlled local HTTP authority; not real GBIF','requests':captured,'results':results},indent=2));print(json.dumps(results,indent=2))
