import sys, json, io, time, hashlib
from pathlib import Path
from uuid import uuid4
sys.path.insert(0,str(Path.cwd()/'tests'))
import test_application as ta
from test_authority_runtime import assembly, decision, running_api
from test_authority_registry import authority_server
from specimen_digitization.application.production import SqlConnectRepository, actor_uid
from specimen_digitization.application.domain import Scope
from specimen_digitization.application.api import create_app, SYNTHETIC_ORG, SYNTHETIC_COLLECTION
from specimen_digitization.application.image_codecs import CodecPolicy
from specimen_digitization.application.image_quality import ImageLimits
from specimen_digitization.application.storage import LocalBlobs, SQLiteRepository
from specimen_digitization.application.workflow import SyntheticAdapters
from PIL import Image, PngImagePlugin
root=Path('/tmp/specimen-qa-wave2-path').read_text().strip(); root=Path(root)
report={'candidate':'e963811','transport':'actual loopback HTTP API and Parties; SQL Connect/PostgreSQL for authority case','checks':[]}
def check(name, condition, detail=None):
    report['checks'].append({'name':name,'pass':bool(condition),'detail':detail})
    (root/'independent-results.json').write_text(json.dumps(report,indent=2))
    assert condition,(name,detail)
def getwork(http,path):
    for _ in range(300):
        r=http.get(path+'/workspace',headers=ta.HEADERS); assert r.status_code==200,r.text
        w=r.json()
        if w['status'] in ('completed','processing_blocked'): return w
        time.sleep(.05)
    raise AssertionError(w)
# Small explicit byte limit and memory enforcement opt-out ONLY for QA decoder execution on macOS.
pf=root/'preflight'; blobs=LocalBlobs(pf/'blobs'); repo=SQLiteRepository(pf/'state.db')
app=create_app(mode='synthetic',repository=repo,blobs=blobs,adapters=SyntheticAdapters(blobs, ta.SYNTHETIC_TEXT),token=ta.TOKEN,codec_policy=CodecPolicy(require_memory_limit=False,limits=ImageLimits(max_bytes=2048)))
with running_api(app) as http:
    endpoint=ta.PREFIX+'/images/preflight?collection_id='+SYNTHETIC_COLLECTION
    def counts():
        with repo.connect() as db:
            tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            return {t:db.execute('SELECT COUNT(*) FROM "'+t+'"').fetchone()[0] for t in tables}
    before=counts(); blob_before=sorted(p.name for p in blobs.root.iterdir())
    cases=[('valid_png',ta.image_bytes(),'image/png',200),('mismatched_mime',ta.image_bytes(),'image/jpeg',200),('corrupt_png',b'not PNG','image/png',200),('disabled_heic',b'fake-heic','image/heic',200),('oversize',b'x'*2049,'image/png',422),('empty',b'','image/png',422)]
    for name,data,mime,status in cases:
        r=http.post(endpoint,headers={**ta.HEADERS,'Content-Type':mime},content=data)
        check('preflight_'+name,r.status_code==status,{'status':r.status_code,'body':r.json()})
    r=http.post(endpoint,content=ta.image_bytes())
    check('preflight_missing_auth',r.status_code==401,r.status_code)
    r=http.post(endpoint.replace(SYNTHETIC_COLLECTION,str(uuid4())),headers=ta.HEADERS,content=ta.image_bytes())
    check('preflight_wrong_scope',r.status_code==403,r.status_code)
    check('preflight_zero_persistence',counts()==before and sorted(p.name for p in blobs.root.iterdir())==blob_before,{'before':before,'after':counts()})
# Unique immutable source avoids the known pending SQL uniqueness race boundary.
out=io.BytesIO(); meta=PngImagePlugin.PngInfo(); meta.add_text('qa_synthetic_case',str(uuid4()))
Image.new('RGB',(120,80),'white').save(out,format='PNG',pnginfo=meta)
ta.image_bytes=lambda:out.getvalue(); ta.HEADERS['Idempotency-Key']='qa-wave2-'+str(uuid4())
fixture=authority_server.__wrapped__(); wire=next(fixture)
try:
    repo=SqlConnectRepository(project='demo-specimen-data',emulator_host='127.0.0.1:9519')
    app,state,_=assembly(root/'authority',wire,repository=repo)
    # Replace the fixture's list-first intent observer with exact specimen lookup.
    tool=app.state.workflow.authority_tools['parties']; from specimen_digitization.application.parties import PartiesAdapter
    ident=[None]; intents=[]; scope=Scope(organization_id=SYNTHETIC_ORG,collection_id=SYNTHETIC_COLLECTION)
    def lookup(query):
        actor_uid.set('synthetic-reviewer')
        row=repo.get(scope,ident[0])
        intents.append(any(v['state']=='intent' for v in row.run.authority_receipts.values()))
        return PartiesAdapter.lookup(tool,query)
    tool.lookup=lookup
    with running_api(app) as http:
        upload,data,progress=ta.intake(http,split=True)
        r=http.put(ta.PREFIX+f"/uploads/{upload['upload_id']}/content",headers={**ta.HEADERS,'Upload-Offset':'20'},content=data[20:]); assert r.status_code==200,r.text
        # Inspect persisted upload before completion to identify exactly its specimen.
        actor_uid.set('synthetic-reviewer')
        # completion begins background processing only after HTTP response; workflow wrapper captures exact id first.
        original_process=app.state.workflow.step
        def process(p,specimen_id,*args,**kwargs):
            ident[0]=specimen_id
            return original_process(p,specimen_id,*args,**kwargs)
        app.state.workflow.step=process
        done=http.post(ta.PREFIX+f"/uploads/{upload['upload_id']}/complete",headers=ta.HEADERS,json={'expected_revision':r.json()['revision']}); assert done.status_code==200,done.text
        ident[0]=done.json()['specimen_id']; path=ta.PREFIX+'/specimens/'+ident[0]; w=getwork(http,path)
        (root/'authority-initial.json').write_text(json.dumps(w,indent=2))
        check('exact_record_intent_before_tcp',intents==[True],intents)
        check('authority_initial_review',w['disposition']=='needs_human_review' and len(state['requests'])==1,{'blocker':w['blocker'],'disposition':w['disposition']})
        phases={}
        for phase in ('parse','plan','lookup','resolve','normalize','validate','finalize'):
            r=http.get(path+'/phases/'+phase,headers=ta.HEADERS)
            check('phase_'+phase,r.status_code==200,r.status_code); phases[phase]=r.json()
        (root/'phases-initial.json').write_text(json.dumps(phases,indent=2))
        check('quality_uncalibrated',w['asset']['quality_diagnostics']['metrics']['calibrated'] is False)
        endpoints=['/phases/lookup','/authority-results/parties?field_key=identified_by_irn','/authority-results/parties/raw?field_key=identified_by_irn','/observations/'+w['observations'][0]['id']+'/raw','/observations/'+w['observations'][0]['id']+'/metadata','/disagreements/'+w['run']['regions'][0]['id']]
        for endpoint in endpoints:
            good=http.get(path+endpoint,headers=ta.HEADERS)
            check('artifact_ok_'+endpoint,good.status_code==200,good.status_code)
            check('artifact_auth_'+endpoint,http.get(path+endpoint).status_code==401)
            check('artifact_scope_'+endpoint,http.get((path+endpoint).replace(SYNTHETIC_ORG,str(uuid4())),headers=ta.HEADERS).status_code in (403,404))
        for target,after in [('identified_by_irn',{'tool_id':'parties','field_key':'taxon','identifier':'emu:/fmnh/eparties/7'}),('identified_by_irn',{'tool_id':'parties','identifier':'emu:/other/eparties/7'}),('identified_by_irn',{'tool_id':'parties','identifier':'emu:/fmnh/eparties/999'})]:
            r=decision(http,path,w,'authority_resolution',str(uuid4()),target_id=target,after=after)
            check('reject_bad_selection_'+after['identifier']+after.get('field_key',''),r.status_code==422,r.text)
        check('rejected_decisions_no_revision_or_network',getwork(http,path)['revision']==w['revision'] and len(state['requests'])==1)
        r=decision(http,path,w,'authority_resolution',str(uuid4()),target_id='identified_by_irn',after={'tool_id':'parties','field_key':'identified_by_irn','identifier':'emu:/fmnh/eparties/7'}); assert r.status_code==200,r.text
        selected=r.json(); check('selection_is_not_approval',selected['disposition']=='needs_human_review')
        r=decision(http,path,selected,'approve',str(uuid4())); assert r.status_code==200,r.text
        approved=r.json(); check('separate_approval',approved['disposition']=='cleared' and len(state['requests'])==1)
        rawurl=path+'/authority-results/parties/raw?field_key=identified_by_irn'
        raw=http.get(rawurl,headers=ta.HEADERS); check('raw_bytes_and_headers',raw.content==state['body'] and raw.headers['cache-control']=='no-store' and raw.headers['x-content-type-options']=='nosniff')
        rawfile=root/'authority'/'blobs'/hashlib.sha256(state['body']).hexdigest(); original=rawfile.read_bytes()
        try:
            rawfile.write_bytes(b'QA corruption')
            r=http.get(rawurl,headers=ta.HEADERS)
            check('raw_corruption_fails_closed',r.status_code==503 and r.json()['error']['message']=='authority_artifact_integrity_failure',{'status':r.status_code,'body':r.text})
        finally: rawfile.write_bytes(original)
        check('raw_restored_exactly',http.get(rawurl,headers=ta.HEADERS).content==original)
        transcript=approved['run']['transcripts'][0]
        r=decision(http,path,approved,'transcription',str(uuid4()),target_id=transcript['region_id'],after={'text':transcript['text'].replace('Synthetic Collector','Synthetic Replacement'),'state':'supported'})
        assert r.status_code==200,r.text
        new=getwork(http,path); (root/'authority-corrected.json').write_text(json.dumps(new,indent=2))
        check('correction_requires_review_and_new_receipt',new['disposition']=='needs_human_review' and len(state['requests'])==2 and len(new['run']['authority_receipts'])==2)
        old=http.get(path+f"/history/{w['revision']}",headers=ta.HEADERS).json()
        check('historical_workspace_exact',old==w)
        for phase,body in phases.items():
            check('historical_phase_exact_'+phase,http.get(path+f"/phases/{phase}?revision={w['revision']}",headers=ta.HEADERS).json()==body)
        params={'collection_id':SYNTHETIC_COLLECTION,'specimen_id':ident[0],'limit':1}
        page=http.get(ta.PREFIX+'/specimens',params=params,headers=ta.HEADERS).json(); cursor=page['next_cursor']
        check('sql_search_metadata',page['items'][0]['revision']==new['revision'] and page['items'][0]['created_at']==new['created_at'])
        r=http.get(ta.PREFIX+'/specimens',params={**params,'cursor':cursor},headers=ta.HEADERS)
        check('sql_cursor_terminal_empty',r.status_code==200 and r.json()['items']==[])
        for extra in ({'cursor':cursor,'risk_min':0},{'risk_min':'NaN'},{'cursor':'1'},{'created_from':'2026-09-01'},{'unexpected':'x'}):
            r=http.get(ta.PREFIX+'/specimens',params=params|extra,headers=ta.HEADERS)
            check('search_invalid_'+str(extra),r.status_code==422,r.status_code)
        r=http.get(ta.PREFIX+'/specimens',params=list(params.items())+[('limit',2)],headers=ta.HEADERS)
        check('search_duplicate_filter',r.status_code==422,r.status_code)
finally:
    try: next(fixture)
    except StopIteration: pass
print(json.dumps({'checks':len(report['checks']),'passed':all(r['pass'] for r in report['checks']),'root':str(root)}))
