import argparse,json
from pathlib import Path
from specimen_digitization.application.api import create_app,SYNTHETIC_TEXT
from specimen_digitization.application.storage import SQLiteRepository,LocalBlobs
from specimen_digitization.application.workflow import SyntheticAdapters
import uvicorn
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--port',type=int,required=True);a=p.parse_args();assert (a.root/'state.db').exists()
b=LocalBlobs(a.root/'blobs');app=create_app(mode='synthetic',repository=SQLiteRepository(a.root/'state.db'),blobs=b,adapters=SyntheticAdapters(b,SYNTHETIC_TEXT),token='test-only-local-token',origins=['http://localhost:3000'])
print('QA independently executed synthetic state; readback only; no processing POST',flush=True)
uvicorn.run(app,host='127.0.0.1',port=a.port,log_level='warning')
