import json
from pathlib import Path
from uuid import UUID
from types import SimpleNamespace
from datetime import datetime,timezone,timedelta
from specimen_digitization.application.storage import SQLiteRepository
from specimen_digitization.application.worker import PollingWorker
root=Path(Path('/tmp/specimen-qa-wave2-path').read_text().strip());repo=SQLiteRepository(root/'worker-independent.db')
time=datetime.now(timezone.utc);clock=[time.isoformat()];due=(time-timedelta(seconds=1)).isoformat()
scopes=[{'organization_id':'qa-org','collection_id':f'qa-{i}','role':'reviewer'} for i in range(13)]
rows=[('qa-org',s['collection_id'],str(UUID(int=j)),1,'{}',f'{s["collection_id"]}:{j}',due,due,'ingested') for s in scopes for j in (2,3,4)]
with repo.connect() as db:db.executemany('INSERT INTO records(org,collection,id,revision,payload,checksum,work_available_at,created_at,state) VALUES(?,?,?,?,?,?,?,?,?)',rows)
visits=[];poison=('qa-0',str(UUID(int=2)));outage=[False]
def members(user):
    if outage[0]:raise OSError('QA injected membership outage')
    return scopes
def step(p,ident):
    key=(p.scope.collection_id,ident);visits.append(key)
    if key==poison:raise OSError('QA injected record failure')
    with repo.connect() as db:db.execute('UPDATE records SET work_available_at=NULL WHERE org=? AND collection=? AND id=?',(p.scope.organization_id,p.scope.collection_id,ident))
def worker():return PollingWorker(SQLiteRepository(repo.path),SimpleNamespace(step=step),'qa-worker',members,page_size=3,steps_per_scope=2,max_scopes=8,clock=lambda:clock[0])
w=worker();w.tick();assert len(visits)<=16
for _ in range(8):w.tick()
healthy={(r[1],r[2]) for r in rows}-{poison}
assert set(visits)-{poison}==healthy
assert all(visits.count(key)==1 for key in healthy)
# New due item sorts behind the retained keyset; wrap and new cutoff must recover it.
new=('qa-12',str(UUID(int=1)));future=(time+timedelta(seconds=1)).isoformat()
with repo.connect() as db:db.execute('INSERT INTO records(org,collection,id,revision,payload,checksum,work_available_at,created_at,state) VALUES(?,?,?,1,\'{}\',?,?,?,\'ingested\')',('qa-org',new[0],new[1],'new',future,future))
w=worker();old=len(visits)
for _ in range(4):w.tick()
assert new not in visits
clock[0]=(time+timedelta(seconds=5)).isoformat()
for _ in range(8):w.tick()
assert visits.count(new)==1
outage[0]=True;before=len(visits);w.tick();assert len(visits)==before and w.health.membership_errors==1
outage[0]=False;clock[0]=(time+timedelta(seconds=20)).isoformat();w.tick()
assert 'memberships' not in w.health.blocked_scopes
(root/'worker-results.json').write_text(json.dumps({'pass':True,'scopes':13,'initial_rows':39,'healthy_exactly_once':38,'poison_isolated':True,'per_tick_scope_budget':8,'per_scope_step_budget':2,'restart_persisted_cursor':True,'future_due_behind_cursor_recovered_once':True,'membership_outage_no_work':True,'health':w.health.__dict__},indent=2))
print('13 scopes /39 rows /38 healthy exactly once; poison isolated; restart and future eligibility wrap; membership outage/recovery passed')
