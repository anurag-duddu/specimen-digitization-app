import sys,json,argparse,hashlib
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'tests'))
from test_active_graph import MultiLabels
from test_application import intake,HEADERS,PREFIX,SYNTHETIC_ORG,SYNTHETIC_COLLECTION,TOKEN
from specimen_digitization.application.api import create_app,SYNTHETIC_TEXT
from specimen_digitization.application.domain import Principal,Scope
from specimen_digitization.application.storage import SQLiteRepository,LocalBlobs,digest
from fastapi.testclient import TestClient
import uvicorn
parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--port',type=int,default=8124);parser.add_argument('--init',action='store_true');args=parser.parse_args()
if args.init:assert not args.root.exists()
blobs=LocalBlobs(args.root/'blobs');repo=SQLiteRepository(args.root/'state.db')
app=create_app(mode='synthetic',repository=repo,blobs=blobs,adapters=MultiLabels(blobs,'Synthetic unstructured context '+('z'*9000)+'\n'+SYNTHETIC_TEXT),token=TOKEN,origins=['http://localhost:3000'])
if args.init:
 with TestClient(app) as http:row=intake(http)
 p=Principal(user_id='synthetic-reviewer',scope=Scope(organization_id=SYNTHETIC_ORG,collection_id=SYNTHETIC_COLLECTION),role='reviewer');s=repo.get(p.scope,row['specimen_id'])
 blocks=[]
 for i in range(360):
  marker=f'QA_PAGE_{i+1:04d}|';blocks.append(marker+(chr(65+i%26)*(12000-len(marker)-12))+f'|END_{i+1:04d}___')
 text=''.join(blocks);assert len(text)==4320000
 observation=s.run.observations[0];observation.literal_text=text;raw=json.dumps({'synthetic_qa_storage_fixture':True,'literal_text':text}).encode();observation.raw_ref=blobs.put(raw);observation.raw_sha256=hashlib.sha256(raw).hexdigest()
 saved=repo.save(p,s,s.version,'independent-large-graph',digest('synthetic-large-graph'))
 manifest={'specimen_id':saved.id,'revision':saved.version,'source_text_characters':len(text),'artifact_size':saved.active_graph['size_bytes'],'artifact_sha256':saved.active_graph['sha256'],'graph_ref':saved.active_graph['blob_ref'],'scope':p.scope.model_dump()}
 assert saved.active_graph['size_bytes']>4*1024*1024
 (args.root/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps({k:v for k,v in manifest.items() if k not in ('artifact_sha256','graph_ref')}),flush=True)
print('SYNTHETIC QA ONLY: exact complete oversized graph; no model, institutional or production service',flush=True)
uvicorn.run(app,host='127.0.0.1',port=args.port,log_level='warning')
