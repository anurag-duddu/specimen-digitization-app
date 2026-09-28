"""Reject temporary SQL Connect reads before signing readiness or bootstrapping."""
import copy
import hashlib
import json
from pathlib import Path
import pytest
import deploy_data as D
import release_initialize as I
from test_data_initialization import packet
from test_initialization_placeholder import prepared, placeholder


def apply_with_ephemeral_readback(tmp_path, monkeypatch, ephemeral=True):
    p=prepared()
    p['schema_mode']='initialize_empty'
    class Google:
        def __init__(self):
            self.packet={**packet(),'identity':{'project_number':'716045864126'}}
            self.schema_applied=False
            self.ephemeral=ephemeral
            self.connector_applied=False
            self.rules=None
            self.calls=[]
        def request(self,api,method,resource,**kwargs):
            self.calls.append((api,method,resource,copy.deepcopy(kwargs)))
            if api=='data':
                if method=='GET':
                    if resource.endswith('/schemas/main'):
                        if not self.schema_applied: return placeholder()
                        return {'name':resource,'etag':'applied-schema','reconciling':False,'datasources':[{'postgresql':{'database':D.DATABASE, 'cloudSql':{'instance':f'projects/{D.PROJECT}/locations/us-east4/instances/{D.SOURCE}'}, 'schemaMigration':'MIGRATE_COMPATIBLE', 'ephemeral':self.ephemeral}}]}
                    return {'name':resource,'etag':'applied-connector','reconciling':False} if self.connector_applied else None
                assert method=='PATCH'
                if not kwargs.get('params',{}).get('validateOnly'):
                    if resource.endswith('/schemas/main'): self.schema_applied=True
                    else: self.connector_applied=True
                return {'name':'synthetic-operation'}
            assert api=='rules'
            if method=='GET': return self.rules
            if resource.endswith('/rulesets'): return {'name':f'projects/{D.PROJECT}/rulesets/synthetic'}
            self.rules=kwargs['body']
            return self.rules
        def wait(self,*args): return None
    native={'clone':D.CLONE,'source':D.SOURCE,'native_restore_verified':True,'deleted_at_unix':1788890550,'deadline_exceeded':False,'run_id':123,'run_attempt':1,'source_sha':p['source_sha']}
    raw=json.dumps(native).encode()
    def cleanup(*args):
        path=tmp_path/'native-recovery.json';path.write_bytes(raw);path.chmod(0o600)
    monkeypatch.setattr(D,'sql_inventory',lambda *a,**k:{'rows':[{}]*len(D.approved_tables())})
    monkeypatch.setattr(D,'verify_indexes',lambda *a:None)
    monkeypatch.setattr(I,'native',lambda *a,**k:None)
    monkeypatch.setattr(D,'cleanup_rehearsal',cleanup)
    google=Google(); output=tmp_path/'data-ready.json'
    D.apply_compatible(google,p,tmp_path/'packet.json',output,{})
    return google,p,output,raw



@pytest.mark.parametrize("ephemeral", [True, 0, 1, "false", None])
def test_temporary_or_ambiguous_service_never_receives_readiness(tmp_path, monkeypatch, ephemeral):
    with pytest.raises(ValueError, match="persistent"):
        apply_with_ephemeral_readback(tmp_path, monkeypatch, ephemeral)
    assert not (tmp_path / "data-ready.json").exists()


def test_persistent_service_can_receive_schema_readiness(tmp_path, monkeypatch):
    _, _, output, _ = apply_with_ephemeral_readback(tmp_path, monkeypatch, False)
    assert json.loads(output.read_bytes())["schema_ready"] is True


def test_later_bootstrap_rechecks_persistent_datasource(tmp_path, monkeypatch):
    import deploy_runtime as R
    google, _, output, native_raw = apply_with_ephemeral_readback(tmp_path, monkeypatch, False)
    raw = output.read_bytes()
    receipt = json.loads(raw)
    binding = {"source_sha": receipt["source_sha"], "run_id": 123, "run_attempt": 1,
               "sha256": hashlib.sha256(raw).hexdigest()}
    def download(command):
        folder = Path(command[-1])
        name = command[command.index("--name") + 1]
        (folder / ("native-recovery.json" if name.startswith("native-recovery-") else "data-ready.json")).write_bytes(
            native_raw if name.startswith("native-recovery-") else raw)
    monkeypatch.setattr(R, "checked", download)
    monkeypatch.setattr(R, "verified_receipt_bytes", lambda *args: raw)
    assert D.verify_schema_receipt(google, {"schema_receipt": binding})["schema_ready"] is True
    google.ephemeral = True
    with pytest.raises(ValueError, match="persistent"):
        D.verify_or_bootstrap(google, {"version": "data-bootstrap/v1", "schema_receipt": binding,
                                      "bootstrap": {}}, tmp_path / "bootstrap-result.json")
    assert not (tmp_path / "bootstrap-result.json").exists()


@pytest.mark.parametrize("change", [
    lambda p: p.update(database="foreign"),
    lambda p: p.update(cloudSql={"instance": "foreign"}),
    lambda p: p.update(schema="foreign"),
    lambda p: p.update(schemaValidation="NONE"),
    lambda p: p.update(schemaMigration="MIGRATE_COMPATIBLE"),
])
def test_other_or_unverified_datasource_never_receives_readiness(change):
    schema, _ = D.data_bodies({"schema_mode": "validate_existing", "schema_etag": None, "connector_etag": None})
    D.verify_persistent_schema(schema)
    change(schema["datasources"][0]["postgresql"])
    with pytest.raises(ValueError):
        D.verify_persistent_schema(schema)
