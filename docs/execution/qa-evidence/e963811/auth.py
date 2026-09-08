import sys,json
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'tests'))
from test_authority_runtime import running_api
import test_application as ta
from specimen_digitization.application.api import create_app,SYNTHETIC_COLLECTION,SYNTHETIC_ORG
from specimen_digitization.application.storage import SQLiteRepository,LocalBlobs
from specimen_digitization.application.workflow import SyntheticAdapters
from specimen_digitization.application.domain import Scope
root=Path(Path('/tmp/specimen-qa-wave2-path').read_text().strip());repo=SQLiteRepository(root/'unicode'/'state.db');blobs=LocalBlobs(root/'unicode'/'blobs')
scope=Scope(organization_id=SYNTHETIC_ORG,collection_id=SYNTHETIC_COLLECTION);record=repo.list(scope)[0]
permission={'sensitive':True,'member':True}
def members(user):return [{'organization_id':SYNTHETIC_ORG,'collection_id':SYNTHETIC_COLLECTION,'role':'reviewer','can_view_sensitive':permission['sensitive']}] if permission['member'] else []
app=create_app(mode='emulator',repository=repo,blobs=blobs,adapters=SyntheticAdapters(blobs,ta.SYNTHETIC_TEXT),identity_verifier=lambda token,appcheck:token,memberships=members)
headers={'Authorization':'Bearer qa-actor-a'};path=ta.PREFIX+'/specimens/'+record.id;results=[]
with running_api(app) as http:
    current=http.get(path+'/workspace',headers=headers);assert current.status_code==200,current.text
    w=current.json();ob=w['observations'][0]['id'];region=w['run']['regions'][0]['id']
    routes=[f'/observations/{ob}/raw',f'/observations/{ob}/metadata',f'/disagreements/{region}',f'/observations/{ob}/raw?revision={w["revision"]}']
    for route in routes: assert http.get(path+route,headers=headers).status_code==200
    params={'collection_id':SYNTHETIC_COLLECTION,'limit':1};page=http.get(ta.PREFIX+'/specimens',params=params,headers=headers).json();cursor=page['next_cursor']
    assert cursor
    r=http.get(ta.PREFIX+'/specimens',params=params|{'cursor':cursor},headers={'Authorization':'Bearer qa-actor-b'})
    assert r.status_code==422,r.text
    permission['sensitive']=False
    for route in routes:
        r=http.get(path+route,headers=headers); assert r.status_code==403,r.text
        results.append({'route':route,'revoked_sensitive_status':r.status_code})
    r=http.get(ta.PREFIX+'/specimens',params=params|{'cursor':cursor},headers=headers);assert r.status_code==422,r.text
    permission['member']=False
    for route in routes:
        r=http.get(path+route,headers=headers);assert r.status_code in (403,404),r.text
    permission.update(sensitive=True,member=True)
    for route in routes: assert http.get(path+route,headers=headers).status_code==200
(root/'auth-results.json').write_text(json.dumps({'pass':True,'transport':'actual HTTP; emulator-mode injected identities/membership policy; SQLite','current_and_pinned_artifacts':results,'actor_cursor_reuse_rejected':True,'permission_cursor_reuse_rejected':True,'membership_revoke_denied':True,'restored_access':True},indent=2))
print('current and pinned evidence revoke/restore, actor and permission cursor binding passed')
