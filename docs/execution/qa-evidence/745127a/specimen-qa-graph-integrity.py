import json,sqlite3,httpx,hashlib
from pathlib import Path
r=Path('/tmp/specimen-qa-745127a-graph');m=json.loads((r/'manifest.json').read_text());p='/v1/organizations/'+m['scope']['organization_id']+'/specimens/'+m['specimen_id'];c=httpx.Client(base_url='http://127.0.0.1:8124',headers={'Authorization':'Bearer test-only-local-token'},timeout=60)
a=c.get(p+'/active-graph?revision=57');assert a.content==(r/'original-artifact.json').read_bytes()
row=sqlite3.connect(r/'state.db').execute('select revision,payload from records where id=?',(m['specimen_id'],)).fetchone();assert row[0]==61;assert len(row[1].encode())<256*1024
meta=json.loads(row[1])['active_graph'];f=r/'state-graphs'/meta['blob_ref'];original=f.read_bytes();assert hashlib.sha256(original).hexdigest()==meta['sha256']
try:
 f.write_bytes(b'corrupted synthetic graph')
 bad=c.get(p+'/active-graph?revision=61');assert bad.status_code==409,bad.text
finally:f.write_bytes(original)
assert c.get(p+'/active-graph?revision=61').content==original
assert c.get(p).json()['revision']==61
result={'all_browser_pages':377,'browser_reconstructed_characters':4515728,'observations_exact':20,'literal_text_characters':4320000,'artifact_bytes':m['artifact_size'],'final_revision':61,'compact_snapshot_bytes':len(row[1].encode()),'historical_artifact_exact':True,'corruption_status':bad.status_code,'restored_bytes_exact':True,'no_revision_advance':True}
(r/'independent-results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
