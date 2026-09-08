import json,hashlib,io,time
from pathlib import Path
import httpx,numpy as np,pillow_heif
from PIL import Image
from specimen_digitization.application.domain import Scope
from specimen_digitization.application.storage import SQLiteRepository,LocalBlobs
from specimen_digitization.application.workflow import crop_bytes
out=Path('/tmp/specimen-qa-n01-heic');out.mkdir(exist_ok=True);r=Path('/tmp/specimen-qa-ee4bec8-heic');m=json.loads((r/'manifest.json').read_text());source=Path(m['source']).read_bytes();c=httpx.Client(base_url='http://127.0.0.1:8124',headers={'Authorization':'Bearer test-only-local-token'});prefix='/v1/organizations/00000000-0000-4000-8000-000000000001';p=prefix+'/specimens/'+m['specimen_id']
for _ in range(100):
 w=c.get(p+'/workspace').json()
 if w['status'] in ('completed','processing_blocked'):break
 time.sleep(.05)
assert w['revision']>36 and len(w['run']['regions'])==1
reg=w['run']['regions'][0];assert [reg[k] for k in ['x','y','width','height','rotation_quarter_turns']]==[5,7,40,50,1],reg
assert w['asset']['pixel_basis']=='decoded_heif_primary_pixel_edges' and [w['asset']['width'],w['asset']['height']]==[80,120]
assert c.get(prefix+'/assets/'+w['asset']['id']+'/content').content==source
scope=Scope(organization_id=w['organization_id'],collection_id=w['collection_id']);row=SQLiteRepository(r/'state.db').get(scope,m['specimen_id']);blobs=LocalBlobs(r/'blobs');crop=crop_bytes(blobs,row,row.run.regions[0]);heif=pillow_heif.read_heif(source);oracle=np.asarray(Image.frombytes(heif.mode,heif.size,heif.data).convert('RGB'));expected=np.rot90(oracle[7:57,5:45],-1);assert np.array_equal(np.asarray(Image.open(io.BytesIO(crop)).convert('RGB')),expected)
initial=c.get(p+'/history/20').json();assert initial['asset']==w['asset'] and initial['run']['regions'][0]['rotation_quarter_turns']==0
assert not w['run']['human_approved'];(out/'verified-workspace.json').write_text(json.dumps(w));(out/'verified-crop.png').write_bytes(crop)
result={'saved_revision':w['revision'],'regions':1,'decoded_source_basis':[80,120],'saved_original_basis_crop':[5,7,40,50],'clockwise_quarter_turns':1,'original_bytes_exact':True,'crop_numpy_oracle_exact':True,'initial_history_asset_exact':True,'human_approved':False,'status':w['status'],'disposition':w['disposition']};(out/'independent-results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
