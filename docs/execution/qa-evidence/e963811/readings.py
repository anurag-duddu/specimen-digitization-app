import sys,json,hashlib,time,random
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'tests'))
import test_application as ta
from test_authority_runtime import running_api
from specimen_digitization.application.api import create_app
from specimen_digitization.application.storage import LocalBlobs,SQLiteRepository
from specimen_digitization.application.workflow import SyntheticAdapters
from specimen_digitization.application.reading_evidence import align_readings,ReadingEvidenceInput
root=Path(Path('/tmp/specimen-qa-wave2-path').read_text().strip()); results=[]
cases=[('unicode','😀e\u0301\r\nবাংলা １２3\nالعربية','😀é\r\nবাংলা １２4\nالعربية'),('insert','😀\r\nabc','😀\r\nab中c'),('delete','😀\r\na中bc','😀\r\nabc'),('long','a'*9000,'b'*9000)]
for name,left,right in cases:
    blobs=LocalBlobs(root/name/'blobs');repo=SQLiteRepository(root/name/'state.db')
    app=create_app(mode='synthetic',repository=repo,blobs=blobs,adapters=SyntheticAdapters(blobs,left,right),token=ta.TOKEN)
    with running_api(app) as http:
        row=ta.intake(http);path=ta.PREFIX+'/specimens/'+row['specimen_id']
        for _ in range(300):
            w=http.get(path+'/workspace',headers=ta.HEADERS).json()
            if w['status'] in ('completed','processing_blocked'):break
            time.sleep(.02)
        assert [o['literal_text'] for o in w['observations']]==[left,right]
        alignment=http.get(path+'/disagreements/'+w['run']['regions'][0]['id'],headers=ta.HEADERS).json()
        if name=='long':
            assert alignment['status']=='policy_blocked' and alignment['edit_distance'] is None and alignment['alternatives']==[]
            assert 'reading_disagreement' in w['run']['review_risk']['unmeasured']
        else:
            assert alignment['status']=='disagreement'
            for alternative in alignment['alternatives']:
                for side,text in [('left',left),('right',right)]:
                    span=alternative[side];a=span['start'];b=span['end']
                    assert text[a['codepoint']:b['codepoint']]==span['text']
                    assert text.encode('utf-8')[a['utf8_byte']:b['utf8_byte']].decode()==span['text']
                    assert text.encode('utf-16-le')[2*a['utf16_codeunit']:2*b['utf16_codeunit']].decode('utf-16-le')==span['text']
        for ob,text in zip(w['observations'],[left,right]):
            r=http.get(path+'/observations/'+ob['id']+'/raw',headers=ta.HEADERS)
            assert r.status_code==200 and hashlib.sha256(r.content).hexdigest()==ob['raw_sha256']
            metadata=http.get(path+'/observations/'+ob['id']+'/metadata',headers=ta.HEADERS).json()
            assert metadata['language_state']=='unknown' and metadata['script_state']=='unknown'
            assert metadata['reference']['text_sha256']==hashlib.sha256(text.encode()).hexdigest()
        results.append({'case':name,'alignment':alignment,'disposition':w['disposition'],'unmeasured':w['run']['review_risk']['unmeasured'],'pass':True})
# Independent distance oracle: full matrix, small deterministic multilingual inputs.
rng=random.Random(781);alphabet='a中😀é\u0301\r\n１'
for i in range(300):
    a=''.join(rng.choices(alphabet,k=rng.randint(1,18)));b=''.join(rng.choices(alphabet,k=rng.randint(1,18)))
    matrix=[[0]*(len(b)+1) for _ in range(len(a)+1)]
    for x in range(len(a)+1):matrix[x][0]=x
    for y in range(len(b)+1):matrix[0][y]=y
    for x in range(1,len(a)+1):
        for y in range(1,len(b)+1):matrix[x][y]=min(matrix[x-1][y]+1,matrix[x][y-1]+1,matrix[x-1][y-1]+(a[x-1]!=b[y-1]))
    result=align_readings(ReadingEvidenceInput(observation_id='a',region_id='r',source_ref='a',text=a),ReadingEvidenceInput(observation_id='b',region_id='r',source_ref='b',text=b))
    assert result.edit_distance==matrix[-1][-1],(i,a,b,result)
    # Reconstruct target using reported source spans and replacement strings.
    transformed=a
    for alt in reversed(result.alternatives): transformed=transformed[:alt.left.start.codepoint]+alt.right.text+transformed[alt.left.end.codepoint:]
    assert transformed==b,(i,a,b,result)
(root/'reading-results.json').write_text(json.dumps({'http_cases':results,'independent_oracle_cases':300,'passed':True},indent=2,ensure_ascii=False))
print('4 actual HTTP cases plus 300 independent distance/reconstruction oracle cases passed')
