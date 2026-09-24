"""The first initialization on the gate path (RELEASE.md 4.3, T3c1): the Node connector serves an admitted gate
record's commit, the release identity reads the application database's summary, and the one-time initializer
commits on the source instance alone, then is disposed of only as this run's own.

Synthetic connector, pg, Google, GitHub and attestation replies; never network, credentials or cloud.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace

import pytest

import deploy_data as D
import deploy_runtime
import release_gate as G
import release_google
import release_initialize as I
from test_data_released_deploy import EMPTY, SHA, record


def node(tmp_path, script, mode, env, answers, instance=I.SOURCE):
    """Run a release Node script against fake connector and pg modules that answer each query from a list."""
    modules = tmp_path / "node_modules"
    for name in ("firebase-tools", "pg", "@google-cloud/cloud-sql-connector"):
        (modules / name).mkdir(parents=True, exist_ok=True)
        (modules / name / "package.json").write_text('{"version":"15.8.0","main":"index.js"}')
    (modules / "@google-cloud/cloud-sql-connector/index.js").write_text("exports.AuthTypes={IAM:'IAM'};exports.IpAddressTypes="
        "{PUBLIC:'PUBLIC'};exports.Connector=class{async getOptions(){return {}}close(){}};")
    (modules / "pg/index.js").write_text("const fs=require('node:fs'),env=process.env;exports.Pool=class{constructor(o)"
        "{fs.appendFileSync(env.TEST_TRACE,o.user+' '+o.database+'\\n')}async connect(){return {release(){},async query(sql)"
        "{for(const [key,value] of JSON.parse(env.TEST_ANSWERS)) if(sql.includes(key)) return value;throw Error('unexpected')}}}"
        "async end(){}};")
    output, trace = tmp_path / "output.json", tmp_path / "trace.txt"
    trace.write_text("")
    context = {"PATH": os.environ["PATH"], "GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": D.REPOSITORY, "GITHUB_SHA": SHA,
               "GITHUB_EVENT_NAME": "push", "GITHUB_REF": "refs/heads/main", "GITHUB_REF_PROTECTED": "true",
               "GITHUB_WORKFLOW_REF": f"{D.REPOSITORY}/.github/workflows/data-release.yml@refs/heads/main",
               "RELEASE_NODE_ROOT": str(tmp_path), "TEST_TRACE": str(trace), "TEST_ANSWERS": json.dumps(answers)}
    result = subprocess.run(["node", script, mode, instance, str(output)], cwd=D.ROOT, env={**context, **env},
                            capture_output=True, timeout=30)
    return result.returncode, json.loads(output.read_text()) if output.exists() else None, trace.read_text().splitlines()


@pytest.mark.parametrize("shas,passes", [({"RELEASE_GATE_SHA": SHA}, True), ({"RELEASE_AUTHORIZED_SHA": SHA}, True),
    ({"RELEASE_GATE_SHA": SHA, "RELEASE_AUTHORIZED_SHA": SHA}, False), ({}, False), ({"RELEASE_GATE_SHA": "b" * 40}, False)],
    ids=["gate", "envelope", "both", "neither", "other-commit"])
def test_the_summary_reads_the_application_database_as_the_release_identity_for_one_admitted_commit(tmp_path, shas, passes):
    code, value, trace = node(tmp_path, "scripts/ci/release_sql.mjs", "summary", {"DEPLOYMENT_ENVIRONMENT": "data-production", **shas},
                              [["SELECT current_database() AS name", {"rows": [{"name": D.DATABASE}]}],
                               ["AS roles", [{"command": "BEGIN"}, {"command": "SELECT", "rows": [EMPTY]}, {"command": "COMMIT"}]]])
    assert (code == 0, value, trace) == (passes, EMPTY if passes else None, [f"{I.MAINTENANCE} {D.DATABASE}"] if passes else [])


@pytest.mark.parametrize("mode,instance,shas,passes", [
    ("initialize", I.SOURCE, {"RELEASE_GATE_SHA": SHA}, True),
    ("initialize", I.SOURCE, {"RELEASE_AUTHORIZED_SHA": SHA}, False),  # the envelope still needs its clone's postconditions
    ("initialize", I.CLONE, {"RELEASE_GATE_SHA": SHA}, False), ("capability", I.SOURCE, {"RELEASE_GATE_SHA": SHA}, False),
], ids=["gate-source", "envelope-without-clone", "gate-clone", "gate-envelope-mode"])
def test_the_initializer_commits_on_the_source_alone_only_on_the_gate_path(tmp_path, mode, instance, shas, passes):
    answers = [["session_user AS actor", {"rows": [{"database": I.DATABASE, "actor": I.INITIALIZER_SQL, "effective": I.INITIALIZER_SQL}]}],
               ["backend_type=", {"rows": [{"count": 0}]}], ["$guard$", []], ["COMMIT", []],
               ["$postconditions$", [{"command": "SELECT", "rows": [{"postconditions": {"database_owner": "cloudsqlsuperuser"}}]}]]]
    env = {"DEPLOYMENT_ENVIRONMENT": "data-initialization-production", "RELEASE_SERVICE_ACCOUNT": I.INITIALIZER_SQL + ".gserviceaccount.com",
           "INITIALIZATION_DEADLINE": str(int(time.time()) + 300), "INITIALIZATION_FILES": json.dumps(I.fingerprints()), **shas}
    code, value, trace = node(tmp_path, "scripts/ci/release_initialize.mjs", mode, env, answers, instance)
    assert (code == 0, value and value["postconditions"]) == (passes, {"database_owner": "cloudsqlsuperuser"} if passes else None)


NOW = 1790164900  # Inside record()'s one-hour window.
INTENT = f"initializer-create-{I.SOURCE}.json"


def operation(kind, actor, at):
    return {"name": f"{kind.lower()}-{at}", "status": "DONE", "targetId": I.SOURCE, "targetProject": I.PROJECT, "operationType": kind,
            "user": actor + ".gserviceaccount.com", "insertTime": datetime.fromtimestamp(at, timezone.utc).isoformat()}


class Cloud:
    """The source instance's principal, application database and user operations, behind one job's gate record."""
    def __init__(self, plane, attempt, creator=I.INITIALIZER_SQL):
        self.plane, self.packet, self.creator = plane, record(plane, release_run_attempt=attempt), creator
        self.principal, self.database, self.operations, self.calls = None, True, [], []

    def request(self, api, method, resource, *, body=None, params=None, missing=False):
        self.calls.append((method, resource.rsplit("/", 1)[-1]))
        if self.plane == "data-initialization":
            I.validate_request(api, method, resource, body, params or None, gate=True)  # the real transport guard
        if method == "POST":
            self.principal = {"name": body["name"], "type": body["type"], "databaseRoles": body["databaseRoles"]}
            self.operations.append(operation("CREATE_USER", self.creator, time.time() + 5))
            return self.operations[-1]
        if resource.endswith("/users"):
            return {"items": [self.principal] if self.principal else []}
        if resource.endswith("/operations"):
            return {"items": self.operations}
        if resource.endswith("/databases/" + I.DATABASE):
            return {"name": I.DATABASE, "instance": I.SOURCE, "project": I.PROJECT} if self.database else None
        return {"name": I.SOURCE, "project": I.PROJECT, "region": "us-east4", "state": "RUNNABLE"}

    def dispose_initializer(self, instance, action):
        self.calls.append((action, instance))
        self.principal = {**self.principal, "databaseRoles": []} if action == "revoke" else None
        self.operations.append(operation("UPDATE_USER" if action == "revoke" else "DELETE_USER", I.MAINTENANCE, time.time()))
        return self.operations[-1]


@pytest.fixture
def jobs(tmp_path, monkeypatch):
    """The initialize and dispose-initializer steps, faking only the clock, signatures, this run's artifacts and Node."""
    clock, native, published = [NOW], [], {}
    monkeypatch.setattr(time, "time", lambda: clock[0])
    monkeypatch.setattr(time, "sleep", lambda seconds: pytest.fail("every observation here is immediate"))
    monkeypatch.setattr(I, "require_protected_initializer_environment", lambda plan: None)
    monkeypatch.setattr(I, "native", lambda directory, instance, mode, *, files, deadline, gate_sha=None: native.append(
        (mode, instance, gate_sha, deadline)) or {"instance": instance, "mode": mode, "files": files, "postconditions": {"owner": "x"}})
    monkeypatch.setattr(D, "gh_json", lambda path: {"total_count": len(published), "artifacts": [
        {"name": name, "expired": False, "workflow_run": {"id": 456}} for name in published]})
    monkeypatch.setattr(deploy_runtime, "checked", lambda command, **kwargs: Path(command[9], INTENT).write_bytes(published[command[7]])
                        if command[:7] == ["gh", "run", "download", "456", "--repo", D.REPOSITORY, "--name"] else pytest.fail("download"))
    monkeypatch.setattr(deploy_runtime, "verified_receipt_bytes", lambda path, sha256, source, workflow: Path(path).read_bytes()
                        if (hashlib.sha256(Path(path).read_bytes()).hexdigest(), source, workflow) == (sha256, SHA, "data-release.yml")
                        else pytest.fail("only this commit's signed intent is consumed"))
    for job in ("initialize", "dispose"):
        (tmp_path / job).mkdir()

    def initialize(cloud, publish=True):
        I.prepare_owned_initializer(cloud, tmp_path / "initialize")
        if publish:  # the workflow signs and uploads the intent between the two steps
            published[f"initializer-intent-{SHA}-{cloud.packet['release_run_attempt']}"] = (tmp_path / "initialize" / INTENT).read_bytes()
        I.initialize_existing(cloud, tmp_path / "initialize", tmp_path / "data-initializer.json")
        return json.loads((tmp_path / "data-initializer.json").read_text())

    def dispose(cloud, initializer=None):
        clock[0] = NOW + 100
        if initializer:
            cloud.principal, cloud.operations = initializer.principal, list(initializer.operations)
        return I.dispose_owned_initializer(cloud, tmp_path / "dispose")
    return SimpleNamespace(initialize=initialize, dispose=dispose, native=native, published=published, directory=tmp_path,
                           clock=clock)


def test_the_initializer_creates_its_own_principal_once_then_initializes_the_existing_database(jobs):
    cloud = Cloud("data-initialization", attempt=1)
    assert jobs.initialize(cloud) == {"version": "data-initializer/v1", "source_sha": SHA, "run_id": 456, "run_attempt": 1,
        "instance": I.SOURCE, "database": I.DATABASE, "postconditions_sha256": I.sha({"owner": "x"})}
    assert cloud.principal == {"name": I.INITIALIZER_SQL, "type": "CLOUD_IAM_SERVICE_ACCOUNT", "databaseRoles": ["cloudsqlsuperuser"]}
    # One POST, the envelope's CREATE_USER; one transaction on the source, bound to the commit and the gate record's deadline.
    assert [call for call in cloud.calls if call[0] != "GET"] == [("POST", "users")]
    assert jobs.native == [("initialize", I.SOURCE, SHA, cloud.packet["expires_at_unix"])]
    with pytest.raises(ValueError, match="never be adopted"):
        I.initialize_existing(cloud, jobs.directory / "initialize", jobs.directory / "again.json")
    assert [call for call in cloud.calls if call[0] != "GET"] == [("POST", "users")] and len(jobs.native) == 1


@pytest.mark.parametrize("change,message", [
    (lambda cloud: setattr(cloud, "principal", {"name": I.INITIALIZER_SQL}), "never be adopted"),
    (lambda cloud: setattr(cloud, "database", False), "application database is missing"),
    (lambda cloud: setattr(cloud, "packet", {**cloud.packet, "identity": G.identity("data")}), "initializer identity"),
    (lambda cloud: setattr(cloud, "plane", "data"), "initializer identity"),
    (lambda cloud: setattr(cloud, "creator", I.MAINTENANCE), "operation identity"),
], ids=["existing-principal", "missing-database", "data-provider", "data-plane", "foreign-creation"])
def test_the_initializer_never_adopts_never_creates_a_database_and_runs_only_as_itself(jobs, change, message):
    cloud = Cloud("data-initialization", attempt=1)
    change(cloud)
    with pytest.raises(ValueError, match=message):
        jobs.initialize(cloud)
    assert jobs.native == [] and not any(call[0] == "POST" and call[1] != "users" for call in cloud.calls)
    # Only an observed absence and an existing database let the intent, and so any effect, exist.
    assert (jobs.directory / "initialize" / INTENT).exists() is (cloud.creator == I.MAINTENANCE)


@pytest.mark.parametrize("not_before,now", [(NOW + 50, NOW), (NOW, record()["expires_at_unix"] - 100)],
                         ids=["before-its-window", "too-near-the-deadline"])
def test_the_creation_never_precedes_its_published_window_or_crowds_the_deadline(jobs, not_before, now):
    cloud = Cloud("data-initialization", attempt=1)
    I.prepare_owned_initializer(cloud, jobs.directory / "initialize")
    intent = jobs.directory / "initialize" / INTENT
    intent.write_text(json.dumps({**json.loads(intent.read_text()), "not_before_unix": not_before}))
    jobs.clock[0] = now
    with pytest.raises(ValueError, match="create window"):
        I.initialize_existing(cloud, jobs.directory / "initialize", jobs.directory / "late.json")
    assert [call for call in cloud.calls if call[0] != "GET"] == [] and jobs.native == []


def test_the_gate_transport_refuses_a_database_creation_and_the_clone():
    create = ("sql", "POST", f"projects/{I.PROJECT}/instances/{I.SOURCE}/databases",
              {"project": I.PROJECT, "instance": I.SOURCE, "name": I.DATABASE}, None)
    I.validate_request(*create)  # the envelope's absent-database path is unchanged
    for request in (create, ("sql", "GET", f"projects/{I.PROJECT}/instances/{I.CLONE}/users", None, None)):
        with pytest.raises(ValueError):
            I.validate_request(*request, gate=True)


def test_a_re_run_disposal_proves_the_earlier_attempts_principal_then_revokes_and_deletes_it(jobs):
    initializer, cloud = Cloud("data-initialization", attempt=1), Cloud("data", attempt=2)
    jobs.initialize(initializer)
    state = jobs.dispose(cloud, initializer)
    assert state["outcome"] == "complete" and state["principal_absence_verified"] is True and cloud.principal is None
    assert [call for call in cloud.calls if call[0] != "GET"] == [("revoke", I.SOURCE), ("delete", I.SOURCE)]
    assert [(mode, gate) for mode, _, gate, _ in jobs.native[1:]] == [("disposal-check", SHA), ("disposal-absent", SHA)]


@pytest.mark.parametrize("fault", ["no-intent", "renamed-attempt", "intervening-creation", "creation-before-absence"])
def test_disposal_never_removes_a_principal_this_run_cannot_prove_it_created(jobs, fault):
    initializer, cloud = Cloud("data-initialization", attempt=1), Cloud("data", attempt=2)
    jobs.initialize(initializer, publish=fault != "no-intent")
    if fault == "renamed-attempt":
        jobs.published[f"initializer-intent-{SHA}-2"] = jobs.published.pop(f"initializer-intent-{SHA}-1")
    elif fault == "intervening-creation":
        initializer.operations += [operation(kind, "another-admin@example", NOW + 10) for kind in ("DELETE_USER", "CREATE_USER")]
    elif fault == "creation-before-absence":
        initializer.operations[0] = operation("CREATE_USER", I.INITIALIZER_SQL, NOW - 10)
    with pytest.raises(ValueError):
        jobs.dispose(cloud, initializer)
    assert cloud.principal is not None and [call for call in cloud.calls if call[0] != "GET"] == []


def test_disposal_without_any_intent_only_confirms_an_absent_principal(jobs):
    cloud = Cloud("data", attempt=1)
    assert jobs.dispose(cloud)["outcome"] == "complete" and cloud.calls == [("GET", "users")]
    assert [mode for mode, *_ in jobs.native] == ["disposal-absent"]


def test_ordinary_gate_disposal_re_admits_its_own_record_instead_of_an_envelope_permit(monkeypatch):
    google = object.__new__(release_google.Google)
    google.path, google.plane, google.packet, google.sql_read_deadline = Path("packet.json"), "data", record(), time.time() + 60
    admitted, sent = [], []
    monkeypatch.setattr(release_google, "admit", lambda path, plane: admitted.append(plane) or record())
    monkeypatch.setattr(release_google, "cleanup_packet", lambda *args: pytest.fail("a gate record has no cleanup permit"))
    google.session = SimpleNamespace(request=lambda method, url, **kwargs: sent.append((method, kwargs["params"])) or
                                     SimpleNamespace(status_code=200, json=lambda: {"name": "op"}))
    assert google.dispose_initializer(I.SOURCE, "delete") == {"name": "op"}
    assert admitted == ["data"] and sent == [("DELETE", {"name": I.INITIALIZER_SQL})]
