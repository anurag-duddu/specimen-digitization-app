"""Expired or uncertain initialization can only dispose positively owned privilege."""
import json
from datetime import datetime, timezone

import pytest

import release_initialize as init
from test_data_initialization import NOW, packet, plan, native_recovery, creation_intents


@pytest.mark.parametrize("fault", [None, "ambiguous", "foreign_actor", "preexisting", "missing_intent",
    "recreated", "intervening_delete", "foreign_update", "recreated_after_revoke",
    "own_update", "foreign_delete", "foreign_create", "own_create_after_window", "delete_before_creation"])
def test_ordinary_disposal_reconciles_unknown_source_create_without_replaying(tmp_path, monkeypatch, fault):
    authority, proposed = packet(), plan()
    recovery = init.recovery_receipt(authority, proposed, native_recovery(), NOW)
    operation = {"name": "owned-source-create", "status": "DONE", "operationType": "CREATE_USER",
        "targetId": init.SOURCE, "targetProject": init.PROJECT, "user": init.INITIALIZER_SQL + ".gserviceaccount.com",
        "insertTime": datetime.fromtimestamp(NOW + 1, timezone.utc).isoformat()}
    # Published before effects; no response/outcome file survived the runner.
    journal = creation_intents(authority, recovery)[init.SOURCE]
    if fault == "foreign_actor":
        operation["user"] = "unowned@project.iam.gserviceaccount.com"
    if fault == "preexisting":
        journal["initial_absence_observed"] = False
    operations = [operation, {**operation, "name": "ambiguous-create"}] if fault == "ambiguous" else [operation]
    deleted = {**operation, "name": "original-deletion", "operationType": "DELETE_USER",
               "insertTime": datetime.fromtimestamp(NOW + 10, timezone.utc).isoformat()}
    recreated = {**operation, "name": "foreign-recreation", "user": "another-admin@example.invalid",
                 "insertTime": datetime.fromtimestamp(NOW + 20, timezone.utc).isoformat()}
    if fault == "recreated":
        operations.extend([deleted, recreated])
    elif fault == "intervening_delete":
        operations.append(deleted)
    elif fault == "foreign_update":
        operations.append({**recreated, "operationType": "UPDATE_USER"})
    elif fault == "own_update":
        operations.append({**deleted, "operationType": "UPDATE_USER"})
    elif fault == "foreign_delete":
        operations.append({**recreated, "operationType": "DELETE_USER"})
    elif fault == "foreign_create":
        operations.append(recreated)
    elif fault == "own_create_after_window":
        operations.append({**operation, "name": "late-recreation", "insertTime": datetime.fromtimestamp(NOW + 601, timezone.utc).isoformat()})
    elif fault == "delete_before_creation":
        operations.append({**deleted, "insertTime": datetime.fromtimestamp(NOW + 0.5, timezone.utc).isoformat()})
    trace = []
    class Google:
        plane = "data"
        packet = authority
        present = True
        def request(self, api, method, resource, **kwargs):
            assert method == "GET"
            if resource.endswith("/operations"):
                return {"items": operations}
            if resource.endswith("/users"):
                return {"items": [{"name": init.INITIALIZER_SQL, "type": "CLOUD_IAM_SERVICE_ACCOUNT"}] if self.present else []}
            raise AssertionError(resource)
        def dispose_initializer(self, instance, action):
            trace.append((instance, action))
            if fault == "recreated_after_revoke" and action == "revoke":
                operations.extend([deleted, recreated])
            if action == "delete":
                self.present = False
            return {"name": "owned-" + action, "status": "DONE", "targetId": instance, "targetProject": init.PROJECT,
                "operationType": "UPDATE_USER" if action == "revoke" else "DELETE_USER",
                "user": init.MAINTENANCE + ".gserviceaccount.com",
                "insertTime": datetime.fromtimestamp(NOW + 602, timezone.utc).isoformat()}
    google = Google()
    def native(directory, instance, mode, **kwargs):
        trace.append((instance, mode))
        assert mode in {"disposal-check", "disposal-absent"}
        return {"instance": instance, "mode": mode, "files": init.fingerprints(), "verified": True}
    monkeypatch.setattr(init, "native", native)
    monkeypatch.setattr(init.time, "time", lambda: NOW + 602)
    journals = {} if fault == "missing_intent" else {init.SOURCE: journal}
    if fault:
        with pytest.raises(ValueError):
            init.dispose_initializer_target(google, init.SOURCE, recovery, journals, tmp_path)
        assert not any(action == "delete" or action == "revoke" and fault != "recreated_after_revoke" for _, action in trace)
        assert google.present
    else:
        result = init.dispose_initializer_target(google, init.SOURCE, recovery, journals, tmp_path)
        assert not google.present
        assert trace == [(init.SOURCE, "revoke"), (init.SOURCE, "disposal-check"),
                         (init.SOURCE, "delete"), (init.SOURCE, "disposal-absent")]
        assert result["privilege_deadline_exceeded"] is True
        assert result["principal_absence_verified"] is True
        assert result["release_accepted"] is False
    state = json.loads((tmp_path / ("initializer-disposal-" + init.SOURCE + ".json")).read_bytes())
    assert state["outcome"] == ("blocked" if fault else "complete")


def test_preparation_is_read_only_and_must_observe_both_absent_targets(tmp_path, monkeypatch):
    authority, proposed = packet(), plan()
    recovery = init.recovery_receipt(authority, proposed, native_recovery(), NOW)
    calls = []
    class Google:
        packet = authority
        def request(self, api, method, resource, **kwargs):
            calls.append((method, resource))
            assert method == "GET"
            return {"items": []} if resource.endswith("/users") else None
    monkeypatch.setattr(init.time, "time", lambda: NOW + 1)
    init.prepare_initializer_intents(Google(), proposed, tmp_path, recovery)
    for instance in (init.SOURCE, init.CLONE):
        journal = json.loads((tmp_path / ("initializer-create-" + instance + ".json")).read_bytes())
        assert init.validate_creation_intent(journal, instance, authority, recovery) == journal
        assert any(instance in resource for _, resource in calls)
    with pytest.raises(FileExistsError):
        init.prepare_initializer_intents(Google(), proposed, tmp_path, recovery)


def node_disposal_fixture(tmp_path, mode, fault):
    import os
    from pathlib import Path
    import subprocess
    import time
    modules = tmp_path / "node_modules"
    for name in ("firebase-tools", "pg", "@google-cloud/cloud-sql-connector"):
        directory = modules / name
        directory.mkdir(parents=True)
        (directory / "package.json").write_text('{"version":"15.8.0","main":"index.js"}')
    (modules / "@google-cloud/cloud-sql-connector/index.js").write_text('''
const fs=require('node:fs');
exports.AuthTypes={IAM:'IAM'};exports.IpAddressTypes={PUBLIC:'PUBLIC'};
exports.Connector=class{async getOptions(){return {}} close(){fs.appendFileSync(process.env.TEST_TRACE,'connector.close\\n')}};
''')
    (modules / "pg/index.js").write_text('''
const fs=require('node:fs'), env=process.env, trace=x=>fs.appendFileSync(env.TEST_TRACE,x+'\\n');
exports.Pool=class{
constructor(options){if(options.user!==env.TEST_ACTOR||options.database!=='postgres')throw Error('wrong ordinary connection')}
async connect(){return {release(force){if(!force)throw Error('connection retained');trace('release')},async query(sql){
 if(/\\b(SET|CREATE|ALTER|DROP|GRANT|REVOKE)\\b/.test(sql))throw Error('disposal native check mutated');
 if(sql.includes('current_database()'))return {rows:[{database:'postgres',actor:env.TEST_ACTOR,effective:env.TEST_ACTOR}]};
 if(sql.includes('backend_type='))return {rows:[{count:0}]};
 if(sql.includes('pg_stat_activity'))return {rows:[{count:env.TEST_FAULT==='sessions'?1:0}]};
 if(sql===fs.readFileSync('scripts/ci/initialize_catalog.sql','utf8'))return {rows:[{catalog:JSON.parse(fs.readFileSync(env.TEST_CATALOG))}]};
 if(sql.includes('FROM pg_roles WHERE rolname='))return {rows:env.TEST_MODE==='disposal-absent'&&env.TEST_FAULT!=='present'?[]:[{oid:42,narrow:env.TEST_FAULT!=='privileged'}]};
 if(sql.includes('pg_auth_members'))return {rows:[{count:env.TEST_FAULT==='memberships'?1:0}]};
 if(sql.includes('pg_shdepend'))return {rows:[{count:env.TEST_FAULT==='dependencies'?1:0}]};
 throw Error('unhandled SQL');}}}
async end(){trace('pool.end')}
};
''')
    trace, output = tmp_path / "trace.txt", tmp_path / "result.json"
    from test_initializer_iam_membership import fixture
    catalog = fixture("disposal-check")
    if fault == "memberships":
        catalog["memberships"].append({"role": "pg_read_all_data", "member": init.INITIALIZER_SQL,
            "grantor": "cloudsqladmin", "admin": False, "inherit": True, "set": True})
    catalog_path = tmp_path / "synthetic-catalog.json"
    catalog_path.write_text(json.dumps(catalog))
    env = dict(os.environ, GITHUB_ACTIONS="true", GITHUB_REPOSITORY="anurag-duddu/specimen-digitization-app",
        GITHUB_EVENT_NAME="push", GITHUB_REF="refs/heads/main", GITHUB_REF_PROTECTED="true",
        GITHUB_WORKFLOW_REF="anurag-duddu/specimen-digitization-app/.github/workflows/data-release.yml@refs/heads/main",
        GITHUB_SHA="a" * 40, RELEASE_AUTHORIZED_SHA="a" * 40, DEPLOYMENT_ENVIRONMENT="data-production",
        RELEASE_SERVICE_ACCOUNT=init.MAINTENANCE + ".gserviceaccount.com", RELEASE_NODE_ROOT=str(tmp_path),
        INITIALIZATION_DEADLINE=str(int(time.time()) + 180), INITIALIZATION_FILES=json.dumps(init.fingerprints()),
        TEST_MODE=mode, TEST_FAULT=fault or "", TEST_ACTOR=init.MAINTENANCE, TEST_TRACE=str(trace),
        TEST_CATALOG=str(catalog_path))
    return env, trace, output


@pytest.mark.parametrize("mode,fault", [("disposal-check", None), ("disposal-absent", None),
    ("disposal-check", "memberships"), ("disposal-check", "dependencies"),
    ("disposal-check", "sessions"), ("disposal-check", "privileged"), ("disposal-absent", "present")])
def test_actual_node_disposal_requires_absence_or_narrow_dependency_free_principal(tmp_path, mode, fault):
    import subprocess
    env, trace, output = node_disposal_fixture(tmp_path, mode, fault)
    result = subprocess.run(["node", str(init.ROOT / "scripts/ci/release_initialize.mjs"), mode, init.SOURCE, str(output)],
        cwd=init.ROOT, env=env, capture_output=True, timeout=10)
    assert (result.returncode == 0) == (fault is None), result.stderr.decode()
    assert output.exists() == (fault is None)
    assert trace.read_text().splitlines() == ["release", "pool.end", "connector.close"]


def test_actual_python_disposal_delivers_an_integer_gate_bounded_deadline_to_actual_node(tmp_path, monkeypatch):
    import subprocess
    import time
    env, trace, output = node_disposal_fixture(tmp_path, "disposal-absent", None)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    started = int(time.time()) + 0.5
    authority = {**packet(), "issued_at_unix": int(started) - 5, "expires_at_unix": int(started) + 60}
    class Google:
        plane = "data"
        packet = authority
        sql_read_deadline = None
        def request(self, api, method, resource, **kwargs):
            assert api == "sql" and method == "GET" and resource.endswith("/users")
            return {"items": []}
    google, observed = Google(), []
    original_run = subprocess.run
    def run(*args, **kwargs):
        observed.append((kwargs["env"]["INITIALIZATION_DEADLINE"], kwargs["timeout"]))
        return original_run(*args, **kwargs)
    monkeypatch.setattr(init.time, "time", lambda: started)
    monkeypatch.setattr(init.subprocess, "run", run)
    result = init.dispose_initializer_target(google, init.SOURCE,
        {"privilege_deadline_unix": int(started) - 1}, {}, tmp_path)
    assert result["outcome"] == "complete" and result["principal_absence_verified"] is True
    assert result["release_accepted"] is False and google.sql_read_deadline is None
    assert len(observed) == 1
    wire, timeout = observed[0]
    assert wire.isascii() and wire.isdigit()
    assert int(wire) == authority["expires_at_unix"] <= started + 180
    assert 0 < timeout <= authority["expires_at_unix"] - started
    assert not output.exists()  # Python uses its named per-instance output.
    assert trace.read_text().splitlines() == ["release", "pool.end", "connector.close"]


@pytest.mark.parametrize("deadline", [100, 99, 100.5, True])
def test_native_deadline_refuses_expired_or_noninteger_inputs_before_launch(tmp_path, monkeypatch, deadline):
    calls = []
    monkeypatch.setattr(init.time, "time", lambda: 100)
    monkeypatch.setattr(init.subprocess, "run", lambda *args, **kwargs: calls.append(args))
    with pytest.raises(ValueError):
        init.native(tmp_path, init.SOURCE, "disposal-absent", files=init.fingerprints(), deadline=deadline)
    assert calls == []
    assert list(tmp_path.iterdir()) == []


def test_native_subsecond_remaining_time_has_no_one_second_floor(tmp_path, monkeypatch):
    from types import SimpleNamespace
    clock, calls = [99.75], []
    def run(command, **kwargs):
        calls.append(kwargs["timeout"])
        assert 0 < kwargs["timeout"] <= 0.25
        target = tmp_path / (init.SOURCE + "-disposal-absent.json")
        target.write_text(json.dumps({"instance": init.SOURCE, "mode": "disposal-absent", "files": init.fingerprints()}))
        target.chmod(0o600)
        clock[0] = 99.9
        return SimpleNamespace(returncode=0, stderr=b"")
    monkeypatch.setattr(init.time, "time", lambda: clock[0])
    monkeypatch.setattr(init.subprocess, "run", run)
    result = init.native(tmp_path, init.SOURCE, "disposal-absent", files=init.fingerprints(), deadline=100)
    assert result["mode"] == "disposal-absent" and calls == [0.25]


def test_native_late_success_is_retained_without_becoming_accepted_evidence(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from release_diagnostics import DiagnosticError
    clock, calls = [99.75], []
    target = tmp_path / (init.SOURCE + "-disposal-absent.json")
    def run(command, **kwargs):
        calls.append(command)
        target.write_text(json.dumps({"instance": init.SOURCE, "mode": "disposal-absent", "files": init.fingerprints()}))
        target.chmod(0o600)
        clock[0] = 100
        return SimpleNamespace(returncode=0, stderr=b"")
    monkeypatch.setattr(init.time, "time", lambda: clock[0])
    monkeypatch.setattr(init.subprocess, "run", run)
    with pytest.raises(DiagnosticError, match="catalog.native-execute"):
        init.native(tmp_path, init.SOURCE, "disposal-absent", files=init.fingerprints(), deadline=100)
    assert len(calls) == 1 and target.exists()


def test_expired_disposal_gate_blocks_before_observation_and_restores_prior_deadline(tmp_path, monkeypatch):
    calls = []
    class Google:
        plane = "data"
        packet = {**packet(), "expires_at_unix": 100}
        sql_read_deadline = 77
        def request(self, *args, **kwargs):
            calls.append(args)
    google = Google()
    monkeypatch.setattr(init.time, "time", lambda: 100.25)
    with pytest.raises(ValueError, match="disposal gate expired"):
        init.dispose_initializer_target(google, init.SOURCE,
            {"privilege_deadline_unix": 99}, {}, tmp_path)
    assert calls == [] and google.sql_read_deadline == 77
    state = json.loads((tmp_path / ("initializer-disposal-" + init.SOURCE + ".json")).read_bytes())
    assert state["outcome"] == "blocked" and state["principal_absence_verified"] is False
    assert state["release_accepted"] is False
