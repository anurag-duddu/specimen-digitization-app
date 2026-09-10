"""Generated responses only; no credentials or network."""
import copy
import importlib
import json
from datetime import datetime, timezone

import pytest

import deploy_data as data
from test_data_release import plan as legacy_plan, recovery_packet

NOW = 1788890400
LIMIT = 10 * 1024**3
NAME = f"projects/{data.PROJECT}/backups/generated-backup"
RUN = f"projects/{data.PROJECT}/instances/{data.SOURCE}/backupRuns/42"
DESC = "specimen-first-ten-" + "b" * 64


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat().replace("+00:00", "Z")


def retention():
    return {"expires_at_unix": NOW + 24 * 3600, "max_chargeable_bytes": LIMIT}


def packet():
    return {**recovery_packet(), "source_sha": "a" * 40, "release_run_id": 123, "release_run_attempt": 2,
            "identity": {"project_number": "716045864126"},
            "issued_at_unix": NOW, "expires_at_unix": NOW + 7100,
            "pilot": {"manifest_sha256": "b" * 64}}


def plan():
    p = legacy_plan()
    p["recovery"].update(backup_id=None, backup_retention=retention())
    return p


def source():
    return {"name": data.SOURCE, "project": data.PROJECT, "region": "us-east4", "state": "RUNNABLE",
            "databaseVersion": "POSTGRES_18", "settings": {"settingsVersion": "expected",
            "dataDiskSizeGb": "10", "edition": "ENTERPRISE", "backupConfiguration": {"enabled": False}}}


def operation():
    return {"name": "generated-op", "kind": "sql#operation", "targetProject": data.PROJECT,
            "targetId": data.SOURCE, "operationType": "BACKUP_VOLUME", "status": "DONE",
            "user": f"specimen-data-release@{data.PROJECT}.iam.gserviceaccount.com", "insertTime": iso(NOW + 1),
            "backupContext": {"name": NAME, "backupId": "42"}}


class Fake:
    def __init__(self):
        self.packet = packet()
        self.calls = []
        self.created = False
        self.source = source()
        self.op = operation()
        self.backup = {"name": NAME, "kind": "sql#backup", "type": "ON_DEMAND", "state": "SUCCESSFUL",
            "instance": data.SOURCE, "description": DESC, "location": "us-east4", "backupRun": RUN,
            "expiryTime": iso(retention()["expires_at_unix"]), "maxChargeableBytes": str(LIMIT),
            "backupInterval": {"startTime": iso(NOW + 1), "endTime": iso(NOW + 1)}}
        self.run = {"kind": "sql#backupRun", "id": "42", "instance": data.SOURCE, "type": "ON_DEMAND",
            "status": "SUCCESSFUL", "description": DESC, "location": "us-east4", "endTime": iso(NOW + 1),
            "maxChargeableBytes": str(LIMIT)}
        self.fail = None
        self.existing = []
        self.after_drift = False

    def request(self, api, method, resource, **kw):
        assert api == "sql"
        self.calls.append((method, resource, copy.deepcopy(kw)))
        if method == "POST":
            assert resource == f"projects/{data.PROJECT}/backups"
            self.created = True
            if self.fail:
                raise TimeoutError("generated unknown response")
            return copy.deepcopy(self.op)
        assert method == "GET"
        if resource.endswith("/backupRuns"):
            return {"items": copy.deepcopy(self.existing + ([self.run] if self.created else []))}
        if resource == f"projects/{data.PROJECT}/instances/{data.SOURCE}":
            v = copy.deepcopy(self.source)
            if self.created and self.after_drift:
                v["settings"]["backupConfiguration"]["enabled"] = True
            return v
        if resource == NAME:
            return copy.deepcopy(self.backup)
        if resource == RUN:
            return copy.deepcopy(self.run)
        if resource.endswith("/operations/generated-op"):
            return {**copy.deepcopy(self.op), "status": "DONE"}
        pytest.fail("unexpected route: " + resource)


def create(fake, directory):
    return data.ensure_backup(fake, None, directory, retention=retention(), source=source())


def test_optional_plan_admits_reviewed_finite_limits_and_legacy_absence():
    data.validate_plan(legacy_plan(), packet(), now=NOW)
    data.validate_plan(plan(), packet(), now=NOW)


@pytest.mark.parametrize("change", [
    lambda p: p["recovery"].update(backup_id="42"),
    lambda p: p["recovery"].update(backup_retention=None),
    lambda p: p["recovery"]["backup_retention"].update(expires_at_unix=NOW + 173 * 3600),
    lambda p: p["recovery"]["backup_retention"].update(expires_at_unix=NOW + 1),
    lambda p: p["recovery"]["backup_retention"].update(expires_at_unix=True),
    lambda p: p["recovery"]["backup_retention"].update(max_chargeable_bytes=LIMIT + 1),
    lambda p: p["recovery"]["backup_retention"].update(max_chargeable_bytes="10"),
    lambda p: p["recovery"]["backup_retention"].update(ttlDays="1"),
])
def test_invalid_optional_plan_never_qualifies(change):
    p = plan()
    change(p)
    with pytest.raises(ValueError):
        data.validate_plan(p, packet(), now=NOW)


def test_exact_expiring_request_restores_original_backup_run_and_retains_proof(tmp_path, monkeypatch):
    monkeypatch.setattr(data.time, "time", lambda: NOW + 1)
    f = Fake()
    assert create(f, tmp_path) == "42"
    posts = [c for c in f.calls if c[0] == "POST"]
    assert posts == [("POST", f"projects/{data.PROJECT}/backups", {"body": {
        "instance": data.SOURCE, "description": DESC, "location": "us-east4", "expiryTime": iso(NOW + 86400)}})]
    r = json.loads((tmp_path / "native-backup.json").read_bytes())
    assert r["outcome"] == "successful" and r["backup_id"] == "42"
    assert r["retention_proof"]["backup_run"] == RUN
    assert r["retention_proof"]["expires_at_unix"] == NOW + 86400
    assert r["retention_proof"]["max_chargeable_bytes"] == LIMIT
    assert r["retention_proof"]["original_operation"] == "generated-op"
    with pytest.raises(ValueError):
        create(f, tmp_path)
    assert len([c for c in f.calls if c[0] == "POST"]) == 1


@pytest.mark.parametrize("change", [
    lambda f: f.backup.pop("expiryTime"),
    lambda f: f.backup.update(expiryTime=iso(NOW + 86401)),
    lambda f: f.backup.update(maxChargeableBytes=str(LIMIT + 1)),
    lambda f: f.backup.update(maxChargeableBytes=LIMIT),
    lambda f: f.backup.update(backupRun=RUN.replace("/42", "/43")),
    lambda f: f.backup.update(instance="foreign"),
    lambda f: f.backup.update(type="AUTOMATED"),
    lambda f: f.backup.update(description="other cohort"),
    lambda f: f.op["backupContext"].update(name=NAME.replace(data.PROJECT, "foreign")),
    lambda f: f.op.update(targetId="foreign"),
    lambda f: f.run.update(maxChargeableBytes=str(LIMIT + 1)),
    lambda f: f.run.update(description="other cohort"),
    lambda f: setattr(f, "after_drift", True),
])
def test_unknown_mapping_expiry_size_or_source_stops_after_one_create(tmp_path, monkeypatch, change):
    monkeypatch.setattr(data.time, "time", lambda: NOW + 1)
    f = Fake()
    change(f)
    with pytest.raises(ValueError):
        create(f, tmp_path)
    assert len([c for c in f.calls if c[0] == "POST"]) == 1
    assert json.loads((tmp_path / "native-backup.json").read_bytes())["outcome"] != "successful"


def test_unknown_post_fences_every_second_creation(tmp_path, monkeypatch):
    monkeypatch.setattr(data.time, "time", lambda: NOW + 1)
    f = Fake()
    f.fail = True
    with pytest.raises(TimeoutError):
        create(f, tmp_path)
    with pytest.raises(ValueError):
        create(f, tmp_path)
    assert len([c for c in f.calls if c[0] == "POST"]) == 1


def test_preexisting_cohort_and_source_drift_prevent_creation(tmp_path, monkeypatch):
    monkeypatch.setattr(data.time, "time", lambda: NOW + 1)
    f = Fake()
    f.existing = [{"id": "7", "description": DESC}]
    with pytest.raises(ValueError):
        create(f, tmp_path)
    assert not any(c[0] == "POST" for c in f.calls)
    f.existing = []
    f.source["settings"]["settingsVersion"] = "changed"
    with pytest.raises(ValueError):
        create(f, tmp_path)
    assert not any(c[0] == "POST" for c in f.calls)


def test_finite_proof_is_required_by_signed_initialization_recovery(tmp_path, monkeypatch):
    import release_initialize as init
    from test_data_initialization import plan as initialization_plan, packet as initialization_packet, native_recovery
    monkeypatch.setattr(data.time, "time", lambda: NOW + 1)
    f = Fake()
    create(f, tmp_path)
    p, authority = initialization_plan(), initialization_packet()
    p["recovery"]["backup_retention"] = retention()
    native = native_recovery()
    native["backup_id"] = "42"
    proof = json.loads((tmp_path / "native-backup.json").read_bytes())["retention_proof"]
    native["backup_retention"] = proof
    receipt = init.recovery_receipt(authority, p, native, NOW + 2)
    init.validate_recovery_receipt(receipt, authority, p, now=NOW + 3)
    for change in [lambda n: n.pop("backup_retention"),
                   lambda n: n["backup_retention"].update(backup_id="43"),
                   lambda n: n["backup_retention"].update(expires_at_unix=NOW + 86401),
                   lambda n: n["backup_retention"].update(max_chargeable_bytes=LIMIT + 1)]:
        wrong = copy.deepcopy(receipt)
        change(wrong["native_recovery"])
        with pytest.raises(ValueError):
            init.validate_recovery_receipt(wrong, authority, p, now=NOW + 3)


def test_existing_backup_preservation_and_original_pending_operation(tmp_path, monkeypatch):
    now = [NOW + 1]
    monkeypatch.setattr(data.time, "time", lambda: now[0])
    monkeypatch.setattr(data.time, "sleep", lambda seconds: now.__setitem__(0, now[0] + seconds))
    f = Fake()
    f.op["status"] = "PENDING"
    f.existing = [{"id": "7", "description": "existing-unrelated", "status": "SUCCESSFUL"}]
    assert create(f, tmp_path) == "42"
    assert f.existing == [{"id": "7", "description": "existing-unrelated", "status": "SUCCESSFUL"}]
    assert len([c for c in f.calls if c[0] == "POST"]) == 1
    assert any(c[1].endswith("operations/generated-op") for c in f.calls)


def test_other_backup_change_cannot_be_hidden_by_new_success(tmp_path, monkeypatch):
    monkeypatch.setattr(data.time, "time", lambda: NOW + 1)
    f = Fake()
    f.existing = [{"id": "7", "description": "existing-unrelated"}]
    request = f.request
    def changed(api, method, resource, **kw):
        if f.created and resource.endswith("/backupRuns"):
            f.existing[0]["description"] = "changed"
        return request(api, method, resource, **kw)
    f.request = changed
    with pytest.raises(ValueError, match="existing source backups"):
        create(f, tmp_path)
    assert len([c for c in f.calls if c[0] == "POST"]) == 1


def test_expired_intent_setup_never_submits_backup(tmp_path, monkeypatch):
    module = importlib.import_module("release_backup")
    now = [NOW + 1]
    monkeypatch.setattr(data.time, "time", lambda: now[0])
    save = module.save
    def late(*args, **kwargs):
        save(*args, **kwargs)
        if kwargs.get("create"):
            now[0] = packet()["expires_at_unix"]
    monkeypatch.setattr(module, "save", late)
    f = Fake()
    with pytest.raises(ValueError):
        create(f, tmp_path)
    assert not any(c[0] == "POST" for c in f.calls)


def test_legacy_ensure_backup_body_remains_without_retention_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(data.time, "time", lambda: NOW + 1)
    f = Fake()
    request = f.request
    def legacy(api, method, resource, **kw):
        if method == "POST":
            f.calls.append((method, resource, kw))
            return {"name": "legacy-op", "status": "DONE", "backupContext": {"backupId": "42"}}
        return request(api, method, resource, **kw)
    f.request = legacy
    assert data.ensure_backup(f, None, tmp_path) == "42"
    posts = [c for c in f.calls if c[0] == "POST"]
    assert posts == [("POST", f"projects/{data.PROJECT}/instances/{data.SOURCE}/backupRuns",
                      {"body": {"description": DESC, "location": "us-east4"}})]


@pytest.mark.parametrize("initialization", [False, True])
@pytest.mark.parametrize("missing_proof", [False, True])
def test_recovery_requires_finite_proof_before_clone_and_restores_exact_id(
        tmp_path, monkeypatch, initialization, missing_proof):
    import release_initialize as init
    from test_data_initialization import plan as initialization_plan
    p = initialization_plan() if initialization else plan()
    p["recovery"].update(backup_id=None, backup_retention=retention(), expires_at_unix=NOW + 7000)
    p["recovery"]["recipe"]["source_version"] = "POSTGRES_18"
    p["schema_mode"] = "initialize_missing" if initialization else "initialize_empty"
    monkeypatch.setattr(data.time, "time", lambda: NOW + 1)
    f = Fake()
    f.source["settings"]["databaseFlags"] = [{"name": "cloudsql.iam_authentication", "value": "on"}]
    f.clone, f.restored = None, False
    request = f.request
    def recovery_request(api, method, resource, **kw):
        if api == "run":
            assert method == "GET"
            return None
        if method == "GET" and resource.endswith("/operations"):
            return {"items": []}
        if method == "GET" and resource.endswith("/" + data.CLONE):
            return copy.deepcopy(f.clone)
        if method == "POST" and (resource.endswith("/instances") or resource.endswith("/restoreBackup")):
            f.calls.append((method, resource, copy.deepcopy(kw)))
            if resource.endswith("/instances"):
                f.clone = {**kw["body"], "createTime": iso(NOW + 1)}
            else:
                assert kw["body"] == {"restoreBackupContext": {"backupRunId": "42", "instanceId": data.SOURCE, "project": data.PROJECT}}
                f.restored = True
            return {"name": "generated-clone-operation", "status": "DONE"}
        return request(api, method, resource, **kw)
    f.request = recovery_request
    catalog = {key: [] for key in ("rows", "indexes", "columns", "constraints", "sequences", "schema")}
    monkeypatch.setattr(data, "sql_inventory", lambda *a: copy.deepcopy(catalog))
    def native(directory, instance, mode, **kw):
        assert mode == "absence"
        if instance == data.CLONE:
            assert f.restored
    monkeypatch.setattr(init, "native", native)
    from test_clone_allowance import publish_fixture, Server
    f.path, f.plane = tmp_path / "packet.json", "data"
    f.claim_restore = Server().insert
    publish_fixture(f, p, monkeypatch)
    if missing_proof:
        monkeypatch.setattr(data, "ensure_backup", lambda *a, **kw: "42")
        with pytest.raises(FileNotFoundError, match="native-backup.json"):
            if initialization:
                init.prepare_recovery(f, p, tmp_path, tmp_path / "recovery.json")
            else:
                data.rehearse(f, p, tmp_path)
        assert not any(c[0] == "POST" for c in f.calls)
        return
    if initialization:
        output = tmp_path / "recovery.json"
        init.prepare_recovery(f, p, tmp_path, output)
        receipt = json.loads(output.read_bytes())
        init.validate_recovery_receipt(receipt, f.packet, p, now=NOW + 1)
    else:
        assert data.rehearse(f, p, tmp_path) == catalog
    native_receipt = json.loads((tmp_path / "native-recovery.json").read_bytes())
    assert native_receipt["backup_retention"]["backup_id"] == "42"
    assert native_receipt["backup_retention"]["expires_at_unix"] == retention()["expires_at_unix"]
    assert f.restored
    assert len([c for c in f.calls if c[0] == "POST"]) == 3


@pytest.mark.parametrize("change", [
    {"name": "different-operation"},
    {"backupContext": {"name": NAME, "backupId": "43"}},
    {"backupContext": {"name": NAME + "-other", "backupId": "42"}},
])
def test_poll_never_adopts_a_different_operation_or_backup(tmp_path, monkeypatch, change):
    now = [NOW + 1]
    monkeypatch.setattr(data.time, "time", lambda: now[0])
    monkeypatch.setattr(data.time, "sleep", lambda seconds: now.__setitem__(0, now[0] + seconds))
    f = Fake()
    f.op["status"] = "PENDING"
    request = f.request
    def changed(api, method, resource, **kw):
        value = request(api, method, resource, **kw)
        if resource.endswith("/operations/generated-op"):
            value.update(change)
        return value
    f.request = changed
    with pytest.raises(ValueError, match="original backup operation"):
        create(f, tmp_path)
    assert len([c for c in f.calls if c[0] == "POST"]) == 1


def test_expiry_between_clone_and_packet_deadline_is_rejected():
    p = plan()
    p["recovery"]["expires_at_unix"] = NOW + 7000
    p["recovery"]["backup_retention"]["expires_at_unix"] = NOW + 7100
    with pytest.raises(ValueError):
        data.validate_plan(p, packet(), now=NOW)
