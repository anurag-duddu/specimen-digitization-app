"""Missing is not empty: test the actual protected initialization boundaries."""
import copy
import importlib
from functools import lru_cache
from pathlib import Path

import pytest

import deploy_data as data
from test_data_release import plan as ordinary_plan, recovery_packet, SHA

NOW = 1788890400


def init_module():
    return importlib.import_module("release_initialize")


@lru_cache
def catalog_recipient():
    import hashlib
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    public = rsa.generate_private_key(public_exponent=65537, key_size=3072).public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    return {"public_key_pem": public.decode(), "public_key_sha256": hashlib.sha256(public).hexdigest()}


def plan():
    value = ordinary_plan()
    value.update(version="data-initialize-missing/v1", schema_mode="initialize_missing",
                 schema_etag=None, connector_etag=None, storage_release_etag=None)
    value["recovery"].update(backup_id=None, expires_at_unix=NOW + 7000)
    value["recovery"]["recipe"]["source_version"] = "POSTGRES_18"
    value["catalog_recipient"] = copy.deepcopy(catalog_recipient())
    value["initialization"] = {
        "files": init_module().fingerprints(), "catalog_sha256": "c" * 64,
        "authority_sha256": "1" * 64, "review_sha256": "2" * 64,
        "privilege_window_seconds": 600,
        "identity": {"project_number": "716045864126", "pool_id": "github-actions",
                     "provider": "/".join(["projects", "716045864126", "locations", "global",
                         "workloadIdentityPools", "github-actions", "providers", "specimen-data-initialize"])},
        "permissions": sorted(init_module().PERMISSIONS),
        "conditional_binding_sha256": "d" * 64,
        "disposal_binding_sha256": "e" * 64,
        "disposal_permissions": sorted("cloudsql.users." + action for action in ("get", "list", "update", "delete")),
        "service_agent": "service-716045864126@gcp-sa-firebasedataconnect.iam",
    }
    return value


def packet():
    return {**recovery_packet(), "source_sha": SHA, "authorization_sha256": "1" * 64,
            "independent_review": {"report_sha256": "2" * 64},
            "identity": {"project_number": "716045864126"},
            "release_run_id": 123, "release_run_attempt": 1,
            "issued_at_unix": NOW - 10, "expires_at_unix": NOW + 7100}


def native_recovery():
    from datetime import datetime,timezone
    return {'clone':data.CLONE,'source':data.SOURCE,'source_sha':SHA,'backup_id':'123','run_id':123,'run_attempt':1,
            'create_operation':'owned-create','restore_operation':'owned-restore','expires_at_unix':NOW+7000,
            'create_time':datetime.fromtimestamp(NOW,timezone.utc).isoformat(),
            'native_restore_verified':True,'inventory_sha256':'c'*64}


def creation_intents(authority, recovery):
    return {instance: {"version": "initializer-create-intent/v1", "operation": "initializer-create-" + instance,
        "outcome": "prepared", "source_sha": authority["source_sha"], "run_id": authority["release_run_id"],
        "run_attempt": authority["release_run_attempt"], "initial_absence_observed": True,
        "absence_at_unix": NOW, "not_before_unix": NOW, "privilege_deadline_unix": recovery["privilege_deadline_unix"],
        "recovery_sha256": init_module().sha(recovery)} for instance in (data.SOURCE, data.CLONE)}


def test_missing_database_is_an_explicit_separate_phase():
    p = plan()
    assert data.validate_plan(p, packet(), now=NOW) is p
    with pytest.raises(ValueError):
        data.validate_plan({**p, "version": "data-apply/v1"}, packet(), now=NOW)
    assert data.validate_plan(ordinary_plan(), recovery_packet(), now=NOW)


@pytest.mark.parametrize("change", [
    lambda p: p.update(schema_mode="initialize_empty"),
    lambda p: p.update(schema_etag="existing"),
    lambda p: p.update(writers="quiet"),
    lambda p: p["initialization"].update(privilege_window_seconds=601),
    lambda p: p["initialization"].update(privilege_window_seconds=True),
    lambda p: p["initialization"].update(authority_sha256="9" * 64),
    lambda p: p["initialization"].update(review_sha256="9" * 64),
    lambda p: p["initialization"].update(sql="CREATE ROLE arbitrary"),
    lambda p: p["initialization"].update(service_agent="guessed@project.iam"),
    lambda p: p["initialization"]["permissions"].append("resourcemanager.projects.setIamPolicy"),
    lambda p: p["initialization"]["files"].update({"scripts/ci/initialize_database.sql": "0" * 64}),
    lambda p: p["recovery"]["recipe"].update(source_version="POSTGRES_15"),
])
def test_missing_plan_cannot_expand_authority_identity_sql_or_window(change):
    p = plan()
    change(p)
    with pytest.raises(ValueError):
        data.validate_plan(p, packet(), now=NOW)


def test_initializer_plane_cannot_use_ordinary_identity():
    from release_context import validate_context
    from test_release_context import valid_context
    env = valid_context("data")
    with pytest.raises(ValueError):
        validate_context(env, "data-initialization", SHA)
    env.update(DEPLOYMENT_ENVIRONMENT="data-initialization-production",
               RELEASE_SERVICE_ACCOUNT="specimen-data-initialize@specimen-digitization.iam.gserviceaccount.com")
    validate_context(env, "data-initialization", SHA)


def test_role_replacement_uses_query_parameters_and_never_additive_body_roles():
    module = init_module()
    method, resource, kwargs = module.user_request(data.CLONE, "revoke")
    assert method == "PUT" and resource.endswith(data.CLONE + "/users")
    assert kwargs == {"params": {"name": module.INITIALIZER_SQL, "revokeExistingRoles": "true"}, "body": {}}
    method, resource, kwargs = module.user_request(data.CLONE, "create")
    assert method == "POST"
    assert kwargs["body"]["databaseRoles"] == ["cloudsqlsuperuser"]
    assert "password" not in kwargs["body"]
    with pytest.raises(ValueError):
        module.user_request("unowned-target", "create")


def test_fresh_restore_receipt_and_consumed_source_bytes_precede_initialization():
    module = init_module()
    p = plan()
    receipt = module.recovery_receipt(packet(), p, native_recovery(), NOW)
    module.validate_recovery_receipt(receipt, packet(), p, now=NOW + 1)
    for change in (lambda r: r.update(native_restore_verified=False),
                   lambda r: r.update(source_sha="b" * 40),
                   lambda r: r.update(run_attempt=2),
                   lambda r: r.update(parity_at_unix=NOW - 601),
                   lambda r: r["initialization_files"].update({"scripts/ci/initialize_database.sql": "0" * 64})):
        wrong = copy.deepcopy(receipt)
        change(wrong)
        with pytest.raises(ValueError):
            module.validate_recovery_receipt(wrong, packet(), p, now=NOW + 1)


def test_unknown_write_is_fenced_before_sending_and_cannot_be_replayed(tmp_path):
    module = init_module()
    calls = []
    def uncertain():
        calls.append(1)
        assert (tmp_path / "create-source.json").exists()
        raise TimeoutError("unknown native outcome")
    with pytest.raises(TimeoutError):
        module.once(tmp_path, "create-source", uncertain)
    with pytest.raises(ValueError, match="replay"):
        module.once(tmp_path, "create-source", uncertain)
    assert calls == [1]


@pytest.mark.parametrize("changed", [{"name": "foreign-operation"}, {"targetId": "other-instance"},
    {"targetProject": "other-project"}, {"operationType": "DELETE_USER"},
    {"user": "other@project.iam.gserviceaccount.com"}, {"insertTime": "2020-01-01T00:00:00Z"}])
def test_native_poll_preserves_original_operation_provenance(monkeypatch, changed):
    from datetime import datetime, timezone
    original = {"name": "owned-create-user", "targetId": data.CLONE, "targetProject": data.PROJECT,
        "operationType": "CREATE_USER", "user": init_module().INITIALIZER_SQL + ".gserviceaccount.com",
        "insertTime": datetime.fromtimestamp(NOW + 1, timezone.utc).isoformat(), "status": "PENDING"}
    class Google:
        packet = packet()
        def request(self, *args, **kwargs):
            return {**original, **changed, "status": "DONE"}
    monkeypatch.setattr(data.time, "time", lambda: NOW + 2)
    monkeypatch.setattr(data.time, "sleep", lambda n: None)
    with pytest.raises(ValueError):
        data.wait_sql(Google(), original, maximum_seconds=60)


def test_native_reads_cannot_qualify_after_the_original_deadline(monkeypatch):
    clock = [NOW]
    monkeypatch.setattr(data.time, "time", lambda: clock[0])
    monkeypatch.setattr(data.time, "sleep", lambda n: None)
    class Google:
        packet = packet()
        def request(self, *args, **kwargs):
            clock[0] = NOW + 61
            return {"name": "owned", "status": "DONE"}
    with pytest.raises(ValueError):
        data.wait_sql(Google(), {"name": "owned", "status": "PENDING"}, maximum_seconds=60)
    clock[0] = NOW
    def read():
        clock[0] = NOW + 61
        return True
    with pytest.raises(ValueError):
        init_module().observe(read, bool, NOW + 60)


def test_qualification_failure_never_creates_source_and_still_cleans_up():
    module = init_module()
    calls = []
    def qualify(instance):
        calls.append(("initialize", instance))
        raise ValueError("native SET capability unsupported")
    with pytest.raises(ValueError):
        module.qualify_then_source(qualify, lambda target: calls.append(("cleanup", target)),
                                   lambda: calls.append(("source-recheck", data.SOURCE)))
    assert calls == [("initialize", data.CLONE), ("cleanup", data.CLONE)]


def test_same_initialization_and_cleanup_complete_on_clone_before_source():
    module = init_module()
    calls = []
    module.qualify_then_source(lambda target: calls.append(("initialize", target)),
                               lambda target: calls.append(("cleanup", target)),
                               lambda: calls.append(("source-recheck", data.SOURCE)))
    assert calls == [("initialize", data.CLONE), ("cleanup", data.CLONE),
                     ("source-recheck", data.SOURCE), ("initialize", data.SOURCE), ("cleanup", data.SOURCE)]


@pytest.mark.parametrize("failed_mode", [None, "capability", "initialize", "clean", "unknown_create", "expired_cleanup", "recreated_before_cleanup"])
def test_actual_initializer_orchestrator_proves_clone_cleanup_before_source(tmp_path,monkeypatch,failed_mode):
    module=init_module()
    p, authority=plan(),packet()
    recovery=module.recovery_receipt(authority,p,native_recovery(),NOW)
    trace=[]
    class Google:
        packet=authority
        user={}
        databases={}
        operations=[]
        def request(self,api,method,resource,**kw):
            instance=next((name for name in (data.SOURCE,data.CLONE) if '/'+name in resource),None)
            trace.append((method,instance,resource.rsplit('/',1)[-1]))
            if method=='GET':
                if resource.endswith('/operations'):
                    return {'items':[op for op in self.operations if op['targetId']==kw['params']['instance']]}
                if resource.endswith('/users'):return {'items':[self.user[instance]] if instance in self.user else []}
                if '/databases/' in resource:return self.databases.get(instance)
                if instance==data.CLONE:return {'name':data.CLONE,'createTime':native_recovery()['create_time'],
                    'settings':{'userLabels':{'release-run':'123','purpose':'isolated-restore-rehearsal'}}}
                return {'settings':{'settingsVersion':'expected'}}
            if resource.endswith('/users'):
                self.user[instance]={'name':module.INITIALIZER_SQL,'type':'CLOUD_IAM_SERVICE_ACCOUNT','databaseRoles':['cloudsqlsuperuser']}
                if failed_mode=='unknown_create':raise TimeoutError('CREATE_USER outcome not acknowledged')
            else:
                assert resource.endswith('/databases')
                self.databases[instance]={'project':data.PROJECT,'instance':instance,'name':data.DATABASE}
            from datetime import datetime,timezone
            operation={'name':'local-operation','status':'DONE','targetId':instance,'targetProject':data.PROJECT,
                    'operationType':'CREATE_USER' if resource.endswith('/users') else 'CREATE_DATABASE',
                    'user':module.INITIALIZER_SQL+'.gserviceaccount.com',
                    'insertTime':datetime.fromtimestamp(NOW+1,timezone.utc).isoformat()}
            self.operations.append(operation)
            return operation
        def cleanup_initializer(self,instance,action):
            trace.append((action,instance,'user'))
            if action=='revoke':self.user[instance]['databaseRoles']=[]
            else:del self.user[instance]
            from datetime import datetime,timezone
            operation={'name':'local-cleanup','status':'DONE','targetId':instance,'targetProject':data.PROJECT,
                'operationType':'UPDATE_USER' if action=='revoke' else 'DELETE_USER',
                'user':module.INITIALIZER_SQL+'.gserviceaccount.com',
                'insertTime':datetime.fromtimestamp(NOW+1,timezone.utc).isoformat()}
            self.operations.append(operation)
            return operation
    google=Google()
    def native(directory,instance,mode,**kwargs):
        trace.append((mode,instance,'native'))
        if instance==data.CLONE and mode=='initialize' and failed_mode=='recreated_before_cleanup':
            original=google.operations[0]
            google.operations.extend([{**original,'name':'intervening-delete','operationType':'DELETE_USER'},
                {**original,'name':'foreign-create','user':'another-admin@example.invalid'}])
            raise ValueError('same-named principal was replaced')
        if instance==data.CLONE and mode=='initialize' and failed_mode=='expired_cleanup':
            monkeypatch.setattr(module.time,'time',lambda:NOW+601)
            raise ValueError('SQL failed at deadline')
        if mode=='clean' and failed_mode=='expired_cleanup':
            assert kwargs['deadline']==NOW+600, 'never extend the original privilege window'
            raise ValueError('expired native verification')
        if instance==data.CLONE and mode==failed_mode:raise ValueError('native qualification failed')
        return {'instance':instance,'mode':mode,'files':p['initialization']['files'],'postconditions':{'qualified':True}}
    monkeypatch.setattr(module,'native',native)
    monkeypatch.setattr(module.time,'time',lambda:NOW+1)
    output=tmp_path/'result.json'
    if failed_mode:
        with pytest.raises((ValueError,TimeoutError)):module.initialize_targets(google,p,tmp_path,recovery,output,prepared_intents=creation_intents(authority,recovery))
        assert not any(instance==data.SOURCE for method,instance,what in trace)
        if failed_mode not in ('unknown_create','expired_cleanup','recreated_before_cleanup'):assert ('revoke',data.CLONE,'user') in trace
        else:assert not any(method in ('revoke','delete') for method,instance,what in trace)
        if failed_mode in ('unknown_create','clean','expired_cleanup'):
            import json
            state=json.loads((tmp_path/('initializer-cleanup-state-'+data.CLONE+'.json')).read_bytes())
            assert state['outcome']=='blocked' and state['requires_reconciliation'] is True
            assert state['privilege_deadline_unix']==NOW+600
        assert not output.exists()
    else:
        module.initialize_targets(google,p,tmp_path,recovery,output,prepared_intents=creation_intents(authority,recovery))
        assert trace.index(('delete',data.CLONE,'user')) < next(i for i,item in enumerate(trace) if item[1]==data.SOURCE)
        assert google.user=={}
        assert output.exists()


def test_initializer_transport_rejects_arbitrary_roles_targets_and_policy_writes():
    module=init_module()
    for instance in (data.SOURCE,data.CLONE):
        module.validate_request('sql','GET','projects/'+data.PROJECT+'/operations',None,
                                {'instance':instance,'maxResults':100,'pageToken':'next-page'})
        for action in ('create','revoke','delete'):
            method,resource,kwargs=module.user_request(instance,action)
            module.validate_request('sql',method,resource,kwargs.get('body'),kwargs.get('params'))
    for api,method,resource,body,params in [
        ('project','POST','projects/specimen-digitization:setIamPolicy',{},None),
        ('sql','DELETE','projects/specimen-digitization/instances/'+data.SOURCE,None,None),
        ('sql','PUT','projects/specimen-digitization/instances/'+data.CLONE+'/users',{'databaseRoles':[]},{'name':module.INITIALIZER_SQL}),
        ('sql','POST','projects/specimen-digitization/instances/'+data.CLONE+'/users',{'name':module.MAINTENANCE,'databaseRoles':['cloudsqlsuperuser']},None),
        ('sql','GET','projects/specimen-digitization/operations',None,{'instance':'unowned','maxResults':100}),
        ('sql','GET','projects/specimen-digitization/operations',None,{'maxResults':100}),
    ]:
        with pytest.raises(ValueError):module.validate_request(api,method,resource,body,params)


def test_created_resource_propagation_retries_only_reads(monkeypatch):
    module=init_module()
    responses=iter([None,None,{'name':'observed-owned-resource'}])
    sleeps=[]
    monkeypatch.setattr(module.time,'time',lambda:NOW)
    monkeypatch.setattr(module.time,'sleep',lambda seconds:sleeps.append(seconds))
    assert module.observe(lambda:next(responses),bool,NOW+20)['name']=='observed-owned-resource'
    assert sleeps==[2,2]


@pytest.mark.parametrize('catalog_failure',[False,True])
def test_actual_recovery_checks_native_absence_and_restore_before_any_initialization(tmp_path,monkeypatch,catalog_failure):
    module=init_module()
    p,authority=plan(),packet()
    trace=[]
    class Google:
        packet=authority
        clone=None
        restored=False
        def request(self,api,method,resource,**kwargs):
            if method=='GET':
                if api=='run':return None
                if resource.endswith('/'+data.SOURCE):return {'region':'us-east4','databaseVersion':'POSTGRES_18',
                    'settings':{'settingsVersion':'expected','edition':'ENTERPRISE','dataDiskSizeGb':'10',
                    'databaseFlags':[{'name':'cloudsql.iam_authentication','value':'on'}]}}
                if resource.endswith('/'+data.CLONE):return self.clone
                if resource.endswith('/operations'):return {'items':[]}
                if '/backupRuns/' in resource:return {'endTime':native_recovery()['create_time']}
                pytest.fail('unexpected read '+resource)
            trace.append(resource.rsplit('/',1)[-1])
            if resource.endswith('/instances'):
                self.clone={**kwargs['body'],'createTime':native_recovery()['create_time']}
            else:
                assert resource.endswith('/restoreBackup')
                self.restored=True
            return {'name':'fixed-native-operation','status':'DONE'}
    google=Google()
    def native(directory,instance,mode,**kwargs):
        assert mode=='absence' and kwargs['expected_catalog']=='c'*64
        trace.append('catalog-'+instance)
        if catalog_failure:raise ValueError('postgres contains unknown user objects')
        if instance==data.CLONE:assert google.restored
        return {'catalog':{'observed':True}}
    def backup(*args):trace.append('backup');return '123'
    monkeypatch.setattr(module,'native',native)
    monkeypatch.setattr(data,'ensure_backup',backup)
    monkeypatch.setattr(module.time,'time',lambda:NOW)
    from test_clone_allowance import publish_fixture, Server
    google.path, google.plane = tmp_path / 'packet.json', 'data'
    server = Server()
    def claim(payload, directory):
        trace.append('claim')
        return server.insert(payload, directory)
    google.claim_restore = claim
    publish_fixture(google, p, monkeypatch)
    output=tmp_path/'recovery.json'
    if catalog_failure:
        with pytest.raises(ValueError):module.prepare_recovery(google,p,tmp_path,output)
        assert trace==['catalog-'+data.SOURCE] and not output.exists()
    else:
        module.prepare_recovery(google,p,tmp_path,output)
        assert trace==['catalog-'+data.SOURCE,'claim','backup','instances','restoreBackup','catalog-'+data.CLONE,'catalog-'+data.SOURCE]
        import json
        module.validate_recovery_receipt(json.loads(output.read_bytes()),authority,p,now=NOW)


def test_default_or_unprotected_initializer_environment_blocks_before_credentials(monkeypatch):
    module=init_module()
    import release_admission
    monkeypatch.setattr(release_admission,'gh_json',lambda path:{'deployment_branch_policy':None})
    with pytest.raises(ValueError,match='main-only'):
        module.require_protected_initializer_environment(plan())


def test_full_catalog_phase_needs_no_prior_catalog_hash_or_service_agent(tmp_path,monkeypatch):
    module=init_module()
    authority=packet()
    p={'version':'data-initialization-inventory/v1','source_sha':SHA,'database_etag':'expected',
       'initialization_files':module.fingerprints(), 'catalog_recipient':catalog_recipient()}
    assert data.validate_plan(p,authority)==p
    observed={'roles':[{'name':'postgres'}],'application_database_exists':False}
    def native(directory,instance,mode,**kwargs):
        assert instance==data.SOURCE and mode=='inspect' and 'expected_catalog' not in kwargs
        return {'catalog':observed,'native_client_sessions':0,
                'catalog_evidence':{'file':'fixed.encrypted.json','sha256':'a'*64}}
    class Google:
        packet=authority
        def request(self,api,method,resource,**kwargs):
            assert (api,method)==('sql','GET')
            return {'region':'us-east4','databaseVersion':'POSTGRES_18','settings':{'settingsVersion':'expected'}}
    monkeypatch.setattr(module,'native',native)
    output=tmp_path/'catalog.json'
    module.inspect_catalog(Google(),p,tmp_path,output)
    import json
    receipt=json.loads(output.read_bytes())
    assert 'catalog' not in receipt and receipt['catalog_sha256']==module.sha(observed)
    assert receipt['data_ready'] is False
