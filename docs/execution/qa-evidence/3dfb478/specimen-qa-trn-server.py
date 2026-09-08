import sys,json,argparse
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'tests'))
from test_reading_declarations_runtime import DeclaredAdapters
from test_application import intake,TOKEN
from specimen_digitization.application.api import create_app
from specimen_digitization.application.storage import SQLiteRepository,LocalBlobs
from fastapi.testclient import TestClient
import uvicorn
p=argparse.ArgumentParser();p.add_argument('--init',action='store_true');a=p.parse_args();r=Path('/tmp/specimen-qa-3dfb478-trn');
if a.init:assert not r.exists()
b=LocalBlobs(r/'blobs');app=create_app(mode='synthetic',repository=SQLiteRepository(r/'state.db'),blobs=b,adapters=DeclaredAdapters(b,'mixed'),token=TOKEN,origins=['http://localhost:3000'])
if a.init:
 with TestClient(app) as c:row=intake(c)
 (r/'manifest.json').write_text(json.dumps({'specimen_id':row['specimen_id']}));print(json.dumps({'specimen_id':row['specimen_id']}),flush=True)
uvicorn.run(app,host='127.0.0.1',port=8124,log_level='warning')
