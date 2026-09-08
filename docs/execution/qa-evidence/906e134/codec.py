import sys,json,io,time,hashlib
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
import numpy as np
from PIL import Image
import pillow_heif
sys.path.insert(0,str(Path.cwd()/'tests'))
from test_codec_runtime import codec_app,upload_codec
from test_authority_runtime import running_api
from test_application import HEADERS,PREFIX
from specimen_digitization.application.domain import Scope
from specimen_digitization.application.workflow import crop_bytes
root=Path(Path('/tmp/specimen-qa-hardening-path').read_text().strip());home=root/'heic-independent';home.mkdir()
y,x=np.indices((80,120));pixels=np.stack(((x*2)%256,(y*3)%256,((x+y)*5)%256),axis=2).astype('uint8');exif=Image.Exif();exif[274]=6
buffer=io.BytesIO();pillow_heif.from_bytes('RGB',(120,80),pixels.tobytes()).save(buffer,quality=95,exif=exif.tobytes());data=buffer.getvalue();(root/'independent-pattern-orientation6.heic').write_bytes(data)
decoded=pillow_heif.read_heif(data);oracle=np.asarray(Image.frombytes(decoded.mode,decoded.size,decoded.data).convert('RGB'));assert decoded.size==(80,120)
def settled(http,path):
 for _ in range(300):
  r=http.get(path+'/workspace',headers=HEADERS);assert r.status_code==200,r.text;w=r.json()
  if w['status'] in ('completed','processing_blocked'):return w
  time.sleep(.03)
 raise AssertionError(w)
def region_request(http,path,w,turn):
 reg={**w['run']['regions'][0],'x':5,'y':7,'width':40,'height':50,'rotation_quarter_turns':turn,'method':'human','version':'independent-qa'}
 r=http.post(path+'/regions',headers={**HEADERS,'Idempotency-Key':str(uuid4())},json={'expected_revision':w['revision'],'base_run_id':w['run']['id'],'reason':'Independent patterned HEIC crop oracle','regions':[reg]});assert r.status_code==200,r.text
 return settled(http,path)
app=codec_app(home)
with running_api(app) as http:
 r=upload_codec(http,data,'image/heic',width=None,height=None);assert r.status_code==200,r.text;row=r.json();path=PREFIX+'/specimens/'+row['specimen_id'];w=settled(http,path)
 assert w['disposition']=='needs_human_review',w['blocker'];assert (w['asset']['width'],w['asset']['height'])==(80,120);assert w['asset']['pixel_basis']=='decoded_heif_primary_pixel_edges'
 assert http.get(PREFIX+'/assets/'+w['asset']['id']+'/content',headers=HEADERS).content==data
 metadata=w['asset']['processing_derivative'];canonical=app.state.workflow.blobs.get(metadata['blob_ref']);actual=np.asarray(Image.open(io.BytesIO(canonical)).convert('RGB'));assert np.array_equal(actual,oracle)
 old_revision=w['revision'];w=region_request(http,path,w,1);scope=Scope(organization_id=row['organization_id'],collection_id=row['collection_id']);record=app.state.workflow.repository.get(scope,row['specimen_id'])
 crop=crop_bytes(app.state.workflow.blobs,record,record.run.regions[0]);expected=np.rot90(oracle[7:57,5:45],-1);assert np.array_equal(np.asarray(Image.open(io.BytesIO(crop)).convert('RGB')),expected)
 first_revision=w['revision'];old=http.get(path+f'/history/{old_revision}',headers=HEADERS).json();assert old['asset']==w['asset']
# Restart with codecs explicitly disabled and a failing decode hook: retained pixels must suffice.
restarted=codec_app(home,False)
with patch('specimen_digitization.application.image_codecs.decode_image',side_effect=AssertionError('Optional codec re-run after restart')) as decoder:
 with running_api(restarted) as http:
  restored=settled(http,path);assert restored==w
  w=region_request(http,path,restored,3);record=restarted.state.workflow.repository.get(scope,row['specimen_id']);crop=crop_bytes(restarted.state.workflow.blobs,record,record.run.regions[0]);expected=np.rot90(oracle[7:57,5:45],-3);assert np.array_equal(np.asarray(Image.open(io.BytesIO(crop)).convert('RGB')),expected)
  assert decoder.call_count==0
  assert http.get(PREFIX+'/assets/'+w['asset']['id']+'/content',headers=HEADERS).content==data
result={'pass':True,'transport':'actual loopback HTTP API, SQLite, real pillow-heif codec child; explicit local memory exception','source_bytes':len(data),'source_size_before_container_transform':[120,80],'verified_decoded_pixel_basis':[80,120],'input_dimensions':'explicit null/null','source_returned_byte_exact':True,'nonuniform_canonical_pixels_match_independent_decode':True,'partial_original_basis_crop':[5,7,40,50],'clockwise_turns_checked':[1,3],'crop_pixels_match_numpy_oracle':True,'restart_same_workspace':True,'restart_with_disabled_codec_and_no_decode_calls':True,'old_asset_provenance_retained':True,'initial_revision':old_revision,'first_crop_revision':first_revision,'final_revision':w['revision'],'final_disposition':w['disposition'],'fixture':str(root/'independent-pattern-orientation6.heic')}
(root/'codec-results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
