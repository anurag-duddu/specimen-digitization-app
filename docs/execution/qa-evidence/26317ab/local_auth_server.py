import sys,json,argparse
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'tests'))
from test_application import intake,TOKEN
from specimen_digitization.application.api import local_app
from fastapi.testclient import TestClient
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
import uvicorn
p=argparse.ArgumentParser();p.add_argument('--init',action='store_true');a=p.parse_args();root=Path('/tmp/specimen-qa-local-auth');
if a.init:assert not root.exists()
app=local_app(root,TOKEN)
@app.middleware('http')
async def controlled_outage(request,call_next):
 if (root/'collection-outage').exists() and request.url.path.startswith('/v1/organizations/'):
  return JSONResponse({'error':{'code':'runtime_unavailable','message':'Synthetic QA collection service unavailable','retryable':True}},status_code=503)
 return await call_next(request)
app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:3004'],allow_methods=['GET','POST','PUT'],allow_headers=['Authorization','Content-Type','Idempotency-Key','Upload-Offset','X-Firebase-AppCheck'],expose_headers=['X-Content-SHA256','X-Specimen-Revision'])
if a.init:
 with TestClient(app) as http:row=intake(http)
 (root/'manifest.json').write_text(json.dumps({'specimen_id':row['specimen_id']}))
print('QA-owned synthetic API; controlled collection outage marker; no production services',flush=True)
uvicorn.run(app,host='127.0.0.1',port=8128,log_level='warning')
