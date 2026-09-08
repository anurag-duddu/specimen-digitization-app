import json,hashlib,httpx
from pathlib import Path
r=Path('/tmp/specimen-qa-745127a-graph');m=json.loads((r/'manifest.json').read_text());p='/v1/organizations/'+m['scope']['organization_id']+'/specimens/'+m['specimen_id'];c=httpx.Client(base_url='http://127.0.0.1:8124',headers={'Authorization':'Bearer test-only-local-token'},timeout=60)
w=c.get(p+"/workspace");assert w.status_code==413,w.text
(r/'workspace-receipt.json').write_text(w.text)
a=c.get(p+'/active-graph?revision=57');assert a.status_code==200
assert len(a.content)==m['artifact_size'] and hashlib.sha256(a.content).hexdigest()==m['artifact_sha256']==a.headers['x-content-sha256']
assert a.headers['x-specimen-revision']=='57'
g=a.json();assert g['scope']==m['scope'] and g['specimen_id']==m['specimen_id'] and g['revision']==57
assert len(g['run']['observations'][0]['literal_text'])==4320000
(r/'original-artifact.json').write_bytes(a.content)
assert httpx.get('http://127.0.0.1:8124'+p+'/active-graph?revision=57').status_code==401
assert c.get(p.replace(m['scope']['organization_id'],'00000000-0000-4000-8000-000000000099')+'/active-graph?revision=57').status_code in (403,404)
print(json.dumps({'workspace_status':w.status_code,'artifact_bytes':len(a.content),'identity_digest_headers':'passed','missing_auth_wrong_scope':'denied','receipt':w.json()}))
