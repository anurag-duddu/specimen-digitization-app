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


def test_published_creation_intents_precede_every_privileged_effect():
    import yaml
    workflow = yaml.safe_load((init.ROOT / ".github/workflows/data-release.yml").read_text())
    steps = workflow["jobs"]["initialize"]["steps"]
    prepare = next(i for i, step in enumerate(steps) if "--prepare-initializer-intents" in step.get("run", ""))
    publish = next(i for i, step in enumerate(steps) if step.get("with", {}).get("name", "").startswith("initializer-intents-"))
    attest = next(i for i, step in enumerate(steps) if "initializer-create-*.json" in step.get("with", {}).get("subject-path", ""))
    effect = next(i for i, step in enumerate(steps) if "--initialize " in step.get("run", ""))
    assert prepare < attest < publish < effect
    assert "if" not in steps[effect], "effect must retain default success dependency"
    disposal = workflow["jobs"]["dispose-initializer"]
    assert disposal["if"].startswith("always()")
    assert disposal["environment"] == "data-production"
    assert disposal["concurrency"]["group"] == "specimen-protected-mutation"
    assert any(step.get("with", {}).get("name", "").startswith("initializer-intents-") for step in disposal["steps"])
    assert "dispose-initializer" in workflow["jobs"]["cleanup"]["needs"]


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


@pytest.mark.parametrize("mode,fault", [("disposal-check", None), ("disposal-absent", None),
    ("disposal-check", "memberships"), ("disposal-check", "dependencies"),
    ("disposal-check", "sessions"), ("disposal-check", "privileged"), ("disposal-absent", "present")])
def test_actual_node_disposal_requires_absence_or_narrow_dependency_free_principal(tmp_path, mode, fault):
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
 if(sql.includes('FROM pg_roles WHERE rolname='))return {rows:env.TEST_MODE==='disposal-absent'&&env.TEST_FAULT!=='present'?[]:[{oid:42,narrow:env.TEST_FAULT!=='privileged'}]};
 if(sql.includes('pg_auth_members'))return {rows:[{count:env.TEST_FAULT==='memberships'?1:0}]};
 if(sql.includes('pg_shdepend'))return {rows:[{count:env.TEST_FAULT==='dependencies'?1:0}]};
 throw Error('unhandled SQL');}}}
async end(){trace('pool.end')}
};
''')
    trace, output = tmp_path / "trace.txt", tmp_path / "result.json"
    env = dict(os.environ, GITHUB_ACTIONS="true", GITHUB_REPOSITORY="anurag-duddu/specimen-digitization-app",
        GITHUB_EVENT_NAME="push", GITHUB_REF="refs/heads/main", GITHUB_REF_PROTECTED="true",
        GITHUB_WORKFLOW_REF="anurag-duddu/specimen-digitization-app/.github/workflows/data-release.yml@refs/heads/main",
        GITHUB_SHA="a" * 40, RELEASE_AUTHORIZED_SHA="a" * 40, DEPLOYMENT_ENVIRONMENT="data-production",
        RELEASE_SERVICE_ACCOUNT=init.MAINTENANCE + ".gserviceaccount.com", RELEASE_NODE_ROOT=str(tmp_path),
        INITIALIZATION_DEADLINE=str(int(time.time()) + 180), INITIALIZATION_FILES=json.dumps(init.fingerprints()),
        TEST_MODE=mode, TEST_FAULT=fault or "", TEST_ACTOR=init.MAINTENANCE, TEST_TRACE=str(trace))
    result = subprocess.run(["node", str(init.ROOT / "scripts/ci/release_initialize.mjs"), mode, init.SOURCE, str(output)],
        cwd=init.ROOT, env=env, capture_output=True, timeout=10)
    assert (result.returncode == 0) == (fault is None), result.stderr.decode()
    assert output.exists() == (fault is None)
    assert trace.read_text().splitlines() == ["release", "pool.end", "connector.close"]
