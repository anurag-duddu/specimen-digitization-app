import sys,json,argparse
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'tests'))
from test_codec_runtime import codec_app,upload_codec
from fastapi.testclient import TestClient
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
p=argparse.ArgumentParser();p.add_argument('--init',action='store_true');p.add_argument('--port',type=int,default=8127);a=p.parse_args();r=Path('/tmp/specimen-qa-ee4bec8-heic')
if a.init:assert not r.exists()
app=codec_app(r);app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:3000'],allow_methods=['GET','POST','PUT'],allow_headers=['Authorization','Content-Type','Idempotency-Key','Upload-Offset','X-Firebase-AppCheck'],expose_headers=['X-Content-SHA256','X-Specimen-Revision'])
if a.init:
 source=Path(Path('/tmp/specimen-qa-hardening-path').read_text().strip())/'independent-pattern-orientation6.heic';data=source.read_bytes()
 with TestClient(app) as c:resp=upload_codec(c,data,'image/heic',width=None,height=None);assert resp.status_code==200,resp.text;row=resp.json()
 (r/'manifest.json').write_text(json.dumps({'specimen_id':row['specimen_id'],'source':str(source)}));print(json.dumps({'specimen_id':row['specimen_id']}),flush=True)
uvicorn.run(app,host='127.0.0.1',port=a.port,log_level='warning')
