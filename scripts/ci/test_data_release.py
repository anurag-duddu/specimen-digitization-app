import importlib
import copy
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent))
M = importlib.import_module("deploy_data")
SHA = "a" * 40


def plan():
    return {"version": "data-apply/v1", "source_sha": SHA, "schema_mode": "validate_existing",
            "source_files": M.source_fingerprints(), "database_etag": "expected",
            "schema_etag": "schema", "connector_etag": "connector", "storage_release_etag": "release",
            "recovery": {"backup_id": "123", "clone": "specimen-digitization-restore-20260908-r1",
                         "recipe": {"tier": "db-f1-micro", "source_version": "POSTGRES_15", "source_edition": "ENTERPRISE", "source_disk_gb": 10}, "expires_at_unix": 1788892000},
            "writers": "no_runtime_exists", "bootstrap": None}


def test_exact_data_plan_needs_no_preexisting_data_success_receipt():
    assert M.validate_plan(plan(), {"source_sha": SHA}, now=1788890400)["schema_mode"] == "validate_existing"


@pytest.mark.parametrize("change", [
    lambda p: p.update(source_sha="b" * 40),
    lambda p: p.update(schema_mode="NONE"),
    lambda p: p.update(schema_mode="force_destructive"),
    lambda p: p.update(writers="assumed_quiet"),
    lambda p: p["recovery"].update(clone="specimen-digitization-instance"),
    lambda p: p["recovery"].update(recipe=None),
    lambda p: p["recovery"].update(expires_at_unix=1788890000),
    lambda p: p["recovery"].update(expires_at_unix=1788899000),
    lambda p: p["source_files"].update({"dataconnect/sql/search-indexes.sql": "b" * 64}),
    lambda p: p.update(command="arbitrary"),
])
def test_wrong_targets_unverified_recovery_stale_sql_and_unsafe_modes_fail_closed(change):
    p = plan()
    change(p)
    with pytest.raises(ValueError):
        M.validate_plan(p, {"source_sha": SHA}, now=1788890400)


def test_empty_schema_initialization_is_explicit_additive_only():
    p = plan()
    p.update(schema_mode="initialize_empty", schema_etag=None, connector_etag=None)
    M.validate_plan(p, {"source_sha": SHA}, now=1788890400)
    schema, connector = M.data_bodies(p)
    assert schema["datasources"][0]["postgresql"]["schemaMigration"] == "MIGRATE_COMPATIBLE"
    assert "schemaValidation" not in schema["datasources"][0]["postgresql"]
    assert schema["datasources"][0]["postgresql"]["cloudSql"]["instance"] == "projects/specimen-digitization/locations/us-east4/instances/specimen-digitization-instance"
    assert connector["name"].endswith("/connectors/specimen-server")


def test_catalog_comparison_cannot_pass_on_counts_only_or_missing_indexes():
    left = {"rows": [{"count": 1, "sha256": "a" * 64}], "indexes": [], "columns": [], "constraints": [], "sequences": []}
    right = {**left, "rows": [{"count": 1, "sha256": "b" * 64}]}
    with pytest.raises(ValueError):
        M.compare_restore(left, right)
    with pytest.raises(ValueError):
        M.verify_indexes(left)


def test_native_clone_creation_refuses_preexisting_resource_and_only_deletes_owned_create_time():
    with pytest.raises(ValueError):
        M.validate_clone_ownership({"name": "specimen-digitization-instance"}, {"clone": M.CLONE}, 123)
    with pytest.raises(ValueError):
        M.validate_clone_ownership({"name": M.CLONE, "createTime": "changed", "settings": {"userLabels": {"release-run": "123"}}},
                                   {"clone": M.CLONE, "run_id": 123, "create_time": "original"}, 123)


def test_native_clone_recipe_rejects_upgrades_foreign_region_or_extra_instances():
    source = {"region": "us-east4", "databaseVersion": "POSTGRES_15", "settings": {"settingsVersion": "expected",
              "edition": "ENTERPRISE", "dataDiskSizeGb": "10", "databaseFlags": [{"name": "cloudsql.iam_authentication", "value": "on"}]}}
    recipe = {"tier": "db-f1-micro", "source_version": "POSTGRES_15", "source_edition": "ENTERPRISE", "source_disk_gb": 10}
    body = M.clone_body(source, recipe, 123, run_attempt=1, source_sha=SHA)
    assert body["name"] == M.CLONE and body["settings"]["dataDiskSizeGb"] == "10"
    assert body["settings"]["backupConfiguration"]["enabled"] is False
    recipe["tier"] = "db-custom-64-245760"
    with pytest.raises(ValueError):
        M.clone_body(source, recipe, 123, run_attempt=1, source_sha=SHA)


def test_names_and_validity_cannot_substitute_for_exact_index_definition():
    indexes = [{"name": name, "valid": True, "unique": name == "specimen_scope_checksum",
                "definition": "CREATE INDEX wrong ON public.specimen (id)"}
               for name in M.INDEXES | {"specimen_scope_checksum"}]
    with pytest.raises(ValueError):
        M.verify_indexes({"indexes": indexes})


def test_native_owned_creation_proof_survives_missing_local_receipt_and_expiry():
    p = {"release_run_id": 123, "release_run_attempt": 2, "source_sha": SHA,
         "issued_at_unix": 1788890400, "expires_at_unix": 1788897600}
    stamp = datetime.fromtimestamp(p["issued_at_unix"] + 60, timezone.utc).isoformat()
    clone = {"name": M.CLONE, "createTime": stamp, "settings": {"userLabels": {
        "release-run": "123", "release-attempt": "2", "source-sha": SHA, "purpose": "isolated-restore-rehearsal"}}}
    operation = {"name": "owned-operation", "status": "DONE", "operationType": "CREATE",
                 "targetId": M.CLONE, "targetProject": M.PROJECT,
                 "user": f"specimen-data-release@{M.PROJECT}.iam.gserviceaccount.com", "insertTime": stamp}
    proof = M.creation_proof(clone, [operation], p)
    assert proof["create_operation"] == "owned-operation"
    for key, value in (("user", "another@example.com"), ("targetId", M.SOURCE),
                       ("insertTime", "2020-01-01T00:00:00+00:00")):
        changed = {**operation, key: value}
        with pytest.raises(ValueError):
            M.creation_proof(clone, [changed], p)
    wrong = copy.deepcopy(clone)
    wrong["settings"]["userLabels"]["release-attempt"] = "1"
    with pytest.raises(ValueError):
        M.creation_proof(wrong, [operation], p)
    with pytest.raises(ValueError):
        M.creation_proof(clone, [operation, operation], p)


def test_on_demand_backup_requires_one_cohort_fence_and_native_success(tmp_path, monkeypatch):
    p = {"release_run_id": 123, "release_run_attempt": 2, "source_sha": SHA,
         "pilot": {"manifest_sha256": "b" * 64}, "issued_at_unix": 1788890400, "expires_at_unix": 1788897600}
    class Fake:
        packet = p
        writes = []
        def request(self, api, method, resource, **kw):
            if method == "POST":
                self.writes.append((resource, kw["body"]))
                return {"name": "backup-op", "status": "DONE", "backupContext": {"backupId": "42"}}
            if resource.endswith("/backupRuns"):
                return {"items": []}
            return {"id": "42", "instance": M.SOURCE, "status": "SUCCESSFUL", "type": "ON_DEMAND",
                    "description": "specimen-first-ten-" + "b" * 64}
    google = Fake()
    monkeypatch.setattr(M.time, "time", lambda: p["issued_at_unix"] + 1)
    assert M.ensure_backup(google, None, tmp_path) == "42"
    assert len(google.writes) == 1 and google.writes[0][0].endswith(M.SOURCE + "/backupRuns")
    assert "enabled" not in json.dumps(google.writes)
    with pytest.raises(ValueError, match="recorded"):
        M.ensure_backup(google, None, tmp_path)


def test_bootstrap_only_plan_requires_current_compatible_signed_schema_receipt():
    p = {"version": "data-bootstrap/v1", "source_sha": SHA, "source_files": M.source_fingerprints(),
         "schema_receipt": {"run_id": 123, "run_attempt": 2, "source_sha": "b" * 40, "sha256": "c" * 64},
         "bootstrap": {"payload": {"prepared": "test-only"}, "sha256": "d" * 64}}
    assert M.validate_plan(p, {"source_sha": SHA})["version"] == "data-bootstrap/v1"
    for change in (lambda p: p.update(bootstrap=None), lambda p: p.update(recovery=plan()["recovery"]),
                   lambda p: p["source_files"].update({"storage.rules": "0" * 64})):
        wrong = copy.deepcopy(p)
        change(wrong)
        with pytest.raises(ValueError):
            M.validate_plan(wrong, {"source_sha": SHA})


def test_bootstrap_path_never_rehearses_republishes_schema_or_touches_runtime_writers(tmp_path, monkeypatch):
    called = []
    google = type("Google", (), {"packet": {"source_sha": SHA, "release_run_id": 123, "release_run_attempt": 3},
                                 "request": lambda *a, **k: pytest.fail("schema/writer mutation is forbidden")})()
    p = {"version": "data-bootstrap/v1", "bootstrap": {"payload": {"approved": True}, "sha256": "d" * 64}}
    original = {"version": "data-schema-ready/v1", "source_sha": "b" * 40, "schema_ready": True,
                "data_ready": False, "native_restore_verified": True, "membership_bootstrapped": False}
    monkeypatch.setattr(M, "verify_schema_receipt", lambda *a: original)
    bootstrap = importlib.import_module("bootstrap_release")
    monkeypatch.setattr(bootstrap, "bootstrap", lambda *a: called.append(a))
    monkeypatch.setattr(M, "rehearse", lambda *a: pytest.fail("no second recovery rehearsal"))
    output = tmp_path / "receipt.json"
    M.verify_or_bootstrap(google, p, output)
    receipt = json.loads(output.read_bytes())
    assert len(called) == 1 and receipt["source_sha"] == SHA
    assert receipt["schema_ready"] is True and receipt["data_ready"] is False and receipt["membership_bootstrapped"] is True


def test_cleanup_performs_one_owned_delete_after_expiry_and_retains_deadline_violation(tmp_path, monkeypatch):
    from test_release_google import context
    _, p = context()
    timestamp = datetime.fromtimestamp(p["issued_at_unix"] + 60, timezone.utc).isoformat()
    clone = {"name": M.CLONE, "createTime": timestamp, "settings": {"userLabels": {
        "release-run": "123", "release-attempt": "2", "source-sha": SHA, "purpose": "isolated-restore-rehearsal"}}}
    operation = {"name": "owned-create", "operationType": "CREATE", "targetId": M.CLONE, "targetProject": M.PROJECT,
                 "user": f"specimen-data-release@{M.PROJECT}.iam.gserviceaccount.com", "insertTime": timestamp, "status": "DONE"}
    class Fake:
        packet = p
        current = clone
        deletes = 0
        def request(self, api, method, resource, **kw):
            assert method == "GET"
            if resource.endswith("/operations"):
                return {"items": [operation]}
            assert resource.endswith("/instances/" + M.CLONE)
            return self.current
        def cleanup_clone(self):
            self.deletes += 1
            assert json.loads((tmp_path / "native-recovery.json").read_text())["create_operation"] == "owned-create"
            self.current = None
            return {"name": "owned-delete", "status": "DONE"}
    google = Fake()
    monkeypatch.setattr(M.time, "time", lambda: p["expires_at_unix"] + 100)
    M.cleanup_rehearsal(google, tmp_path)
    receipt = json.loads((tmp_path / "native-recovery.json").read_text())
    assert google.deletes == 1 and receipt["deadline_exceeded"] is True
    M.cleanup_rehearsal(google, tmp_path)
    assert google.deletes == 1


def test_signed_compatibility_receipt_rejects_stale_sources_before_cloud_or_bootstrap(tmp_path, monkeypatch):
    import deploy_runtime
    original = {"version": "data-schema-ready/v1", "source_sha": "b" * 40, "run_id": 123, "run_attempt": 2,
                "schema_ready": True, "native_restore_verified": True, "source_files": {"storage.rules": "stale"}}
    raw = json.dumps(original).encode()
    import hashlib
    p = {"schema_receipt": {"run_id": 123, "run_attempt": 2, "source_sha": "b" * 40, "sha256": hashlib.sha256(raw).hexdigest()}}
    def download(command, **kw):
        (Path(command[-1]) / "data-ready.json").write_bytes(raw)
    monkeypatch.setattr(deploy_runtime, "checked", download)
    monkeypatch.setattr(deploy_runtime, "verify_attestation", lambda *a: json.dumps([{"verificationResult": {"statement": {
        "subject": [{"digest": {"sha256": hashlib.sha256(raw).hexdigest()}}]}}}]))
    google = type("Fake", (), {"request": lambda *a, **kw: pytest.fail("stale signed evidence cannot reach cloud")})()
    with pytest.raises(ValueError, match="stale"):
        M.verify_schema_receipt(google, p)


def test_deleted_clone_does_not_reset_the_single_rehearsal_allowance(tmp_path, monkeypatch):
    p = plan()
    p["recovery"]["expires_at_unix"] = 1788894000
    monkeypatch.setattr(M.time, "time", lambda: 1788890400)
    class Fake:
        packet = {"expires_at_unix": 1788897600, "release_run_id": 123, "release_run_attempt": 2, "source_sha": SHA}
        def request(self, api, method, resource, **kw):
            assert method == "GET", "no mutation before checking the one-clone allowance"
            if resource.endswith("/instances/" + M.SOURCE):
                return {"region": "us-east4", "databaseVersion": "POSTGRES_15", "settings": {"settingsVersion": "expected",
                        "dataDiskSizeGb": "10", "edition": "ENTERPRISE", "databaseFlags": [{"name": "cloudsql.iam_authentication", "value": "on"}]}}
            if resource.endswith("/instances/" + M.CLONE):
                return None
            if resource.endswith("/operations"):
                return {"items": [{"operationType": "CREATE", "targetId": M.CLONE, "targetProject": M.PROJECT}]}
            pytest.fail("unexpected request before replay fence")
    monkeypatch.setattr(M, "sql_inventory", lambda *a, **kw: pytest.fail("no SQL inventory/effects after prior native clone"))
    with pytest.raises(ValueError, match="already used"):
        M.rehearse(Fake(), p, tmp_path)


def test_inventory_phase_needs_exact_committed_readonly_catalog_and_database_revision():
    p = {"version": "data-inventory/v1", "source_sha": SHA, "database_etag": "expected",
         "catalog_sha256": M.catalog_fingerprint()}
    assert M.validate_plan(p, {"source_sha": SHA}) == p
    for key, value in (("catalog_sha256", "0" * 64), ("database_etag", None), ("command", "arbitrary")):
        with pytest.raises(ValueError):
            M.validate_plan({**p, key: value}, {"source_sha": SHA})


def test_catalog_inventory_never_creates_backup_schema_or_cleanup(tmp_path, monkeypatch):
    from types import SimpleNamespace
    requests = []
    def request(api, method, resource, **kw):
        requests.append((api, method, resource))
        return {"region": "us-east4", "settings": {"settingsVersion": "expected"}}
    google = SimpleNamespace(packet={"source_sha": SHA, "release_run_id": 123, "release_run_attempt": 1}, request=request)
    observed = {key: False for key in M.CATALOG_BOOLEANS}
    observed.update(expected_database=True, expected_actor=True, approved_tables=[], public_table_count=0, unapproved_table_count=0)
    monkeypatch.setattr(M, "sql_catalog", lambda *a: observed)
    output = tmp_path / "catalog.json"
    M.inventory_catalog(google, {"database_etag": "expected", "catalog_sha256": M.catalog_fingerprint()}, tmp_path, output)
    assert requests == [("sql", "GET", f"projects/{M.PROJECT}/instances/{M.SOURCE}")]
    receipt = json.loads(output.read_text())
    assert receipt["version"] == "data-inventory/v1" and receipt["data_ready"] is False
    with pytest.raises(ValueError):
        M.validate_catalog({**observed, "private_owner_dump": "must never be emitted"})
