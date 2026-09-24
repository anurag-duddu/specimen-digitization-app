"""The first initialization on the gate path (RELEASE.md 4.3, T3c1 and T3c2): the Node connector serves an admitted
gate record's commit, the release identity reads the application database's summary, and the one-time initializer
commits on the source instance alone, then is disposed of only as this run's own. The migration then runs Data
Connect's diff client-side as the owner role, and releases the merged files.

Synthetic connector, pg, Google, GitHub and attestation replies; never network, credentials or cloud.
"""
import copy
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
from release_diagnostics import HTTPFailure
import schema_gate
from test_data_released_deploy import EMPTY, RULESET, SHA, UPDATED, record


def node(tmp_path, script, mode, env, answers, instance=I.SOURCE, pg=None, extra=()):
    """Run a release Node script against fake connector and pg modules that answer each query from a list."""
    modules = tmp_path / "node_modules"
    for name in ("firebase-tools", "pg", "@google-cloud/cloud-sql-connector"):
        (modules / name).mkdir(parents=True, exist_ok=True)
        (modules / name / "package.json").write_text('{"version":"15.8.0","main":"index.js"}')
    (modules / "@google-cloud/cloud-sql-connector/index.js").write_text("exports.AuthTypes={IAM:'IAM'};exports.IpAddressTypes="
        "{PUBLIC:'PUBLIC'};exports.Connector=class{async getOptions(){return {}}close(){}};")
    (modules / "pg/index.js").write_text(pg or "const fs=require('node:fs'),env=process.env;exports.Pool=class{constructor(o)"
        "{fs.appendFileSync(env.TEST_TRACE,o.user+' '+o.database+'\\n')}async connect(){return {release(){},async query(sql)"
        "{for(const [key,value] of JSON.parse(env.TEST_ANSWERS)) if(sql.includes(key)) return value;throw Error('unexpected')}}}"
        "async end(){}};")
    output, trace = tmp_path / "output.json", tmp_path / "trace.txt"
    trace.write_text("")
    output.unlink(missing_ok=True)
    context = {"PATH": os.environ["PATH"], "GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": D.REPOSITORY, "GITHUB_SHA": SHA,
               "GITHUB_EVENT_NAME": "push", "GITHUB_REF": "refs/heads/main", "GITHUB_REF_PROTECTED": "true",
               "GITHUB_WORKFLOW_REF": f"{D.REPOSITORY}/.github/workflows/data-release.yml@refs/heads/main",
               "RELEASE_NODE_ROOT": str(tmp_path), "TEST_TRACE": str(trace), "TEST_ANSWERS": json.dumps(answers)}
    result = subprocess.run(["node", script, mode, instance, str(output), *extra], cwd=D.ROOT, env={**context, **env},
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


# T3c2 (RELEASE.md 4.3 steps 3 to 5): Data Connect's diff, run client-side as the owner role, then the merged files.
RELAXED = {("source_asset", "width"), ("source_asset", "height"), ("label_region", "crop_asset_id")}
ALLOWED = {
    "create-table": 'CREATE TABLE "public"."organization" ("id" uuid NOT NULL DEFAULT uuid_generate_v4(), '
                    '"name" text NOT NULL, PRIMARY KEY ("id"))',
    "create-table-with-keys": 'CREATE TABLE IF NOT EXISTS public.collection ("organization_id" uuid NOT NULL, "id" uuid NOT '
                              'NULL, "parent_id" uuid NULL, PRIMARY KEY ("organization_id", "id"), CONSTRAINT "scope_ref_1" '
                              'FOREIGN KEY ("organization_id", "parent_id") REFERENCES "public"."collection" ("organization_id", '
                              '"id") ON DELETE SET NULL)',
    "create-view": 'CREATE VIEW "public"."named_listing" AS SELECT id::text COLLATE "C" AS id, \'a;b--c/*\' AS note '
                   'FROM public.specimen',
    "add-column": 'ALTER TABLE "public"."specimen" ADD COLUMN "note" text NULL DEFAULT \'x, y\'',
    "create-index": 'CREATE INDEX "specimen_due_work" ON "public"."specimen" ("organization_id", "collection_id", "state");',
    "create-unique-index": 'CREATE UNIQUE INDEX "specimen_scope_checksum" ON "public"."specimen" USING btree '
                           '("organization_id", "collection_id", "source_checksum")',
    "add-unique": 'ALTER TABLE "public"."source_asset" ADD CONSTRAINT "specimen_unique_1" UNIQUE ("bucket", "object_name", '
                  '"generation")',
    "add-foreign-key": 'ALTER TABLE "public"."label_region" ADD CONSTRAINT "scope_ref_16" FOREIGN KEY ("organization_id", '
                       '"collection_id", "crop_asset_id") REFERENCES "public"."source_asset" ("organization_id", '
                       '"collection_id", "id")',
    "drop-not-null": 'ALTER TABLE "public"."source_asset" ALTER COLUMN "width" DROP NOT NULL, ALTER COLUMN "height" DROP NOT NULL',
    "drop-not-null-and-add": 'ALTER TABLE label_region ALTER COLUMN crop_asset_id DROP NOT NULL, ADD COLUMN "note" text NULL',
}
# Each is refused by its kind and a fixed reason. "canary" marks text that must never reach a log or a receipt.
REFUSED = {
    "extension": ('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"', "CREATE EXTENSION", "not an allowed kind"),
    "schema": ('CREATE SCHEMA IF NOT EXISTS "canary_schema"', "CREATE SCHEMA", "not an allowed kind"),
    "drop-table": ('DROP TABLE "public"."canary_table"', "DROP TABLE", "not an allowed kind"),
    "drop-index": ('DROP INDEX "public"."canary_index"', "DROP INDEX", "not an allowed kind"),
    "drop-constraint": ('ALTER TABLE "public"."specimen" DROP CONSTRAINT "canary_constraint"', "ALTER TABLE",
                        "not an allowed kind"),
    "drop-column": ('ALTER TABLE "public"."specimen" DROP COLUMN "canary_column"', "ALTER TABLE", "not an allowed kind"),
    "alter-type": ('ALTER TABLE "public"."specimen" ALTER COLUMN "canary_column" TYPE varchar(10)', "ALTER TABLE",
                   "not an allowed kind"),
    "set-not-null": ('ALTER TABLE "public"."specimen" ALTER COLUMN "canary_column" SET NOT NULL', "ALTER TABLE",
                     "not an allowed kind"),
    "drop-not-null-elsewhere": ('ALTER TABLE "public"."model_observation" ALTER COLUMN "run_id" DROP NOT NULL', "ALTER TABLE",
                                "DROP NOT NULL outside the schema gate's named relaxations"),
    "add-then-drop": ('ALTER TABLE "public"."specimen" ADD COLUMN "note" text NULL, DROP COLUMN "canary_column"', "ALTER TABLE",
                      "not an allowed kind"),
    "check": ('ALTER TABLE "public"."specimen" ADD CONSTRAINT "canary_check" CHECK (revision > 0)', "ALTER TABLE",
              "not an allowed kind"),
    "truncate": ('TRUNCATE "public"."canary_table"', "TRUNCATE", "not an allowed kind"),
    "grant": ('GRANT SELECT ON "public"."canary_table" TO PUBLIC', "GRANT", "not an allowed kind"),
    "revoke": ('REVOKE ALL ON SCHEMA public FROM "canary_role"', "REVOKE", "not an allowed kind"),
    "do": ("DO $canary$ BEGIN PERFORM 1; END $canary$", "DO", "an unsupported character"),
    "two-statements": ('CREATE INDEX "a" ON "public"."specimen" ("state"); DROP TABLE "canary_table"', "CREATE INDEX",
                       "more than one statement"),
    "line-comment": ('CREATE INDEX "a" ON "public"."specimen" ("state") --\n; DROP TABLE canary_table', "CREATE INDEX",
                     "a comment"),
    "block-comment": ('CREATE INDEX "a" ON "public"."specimen" ("state") /*; DROP TABLE canary_table */', "CREATE INDEX",
                      "a comment"),
    "escape-string": ("ALTER TABLE public.specimen ADD COLUMN note text DEFAULT E'\\'' ; DROP TABLE canary_table --'",
                      "ALTER TABLE", "an unsupported character"),
    "other-schema": ('CREATE TABLE "canary_schema"."a" ("id" uuid)', "CREATE TABLE", "outside the public schema"),
    "create-as": ('CREATE TABLE "public"."canary_table" AS SELECT 1', "CREATE TABLE", "not an allowed kind"),
    "replace-view": ('CREATE OR REPLACE VIEW "public"."canary_view" AS SELECT 1', "CREATE OR REPLACE", "not an allowed kind"),
    "materialized": ('CREATE MATERIALIZED VIEW "public"."canary_view" AS SELECT 1', "CREATE MATERIALIZED VIEW",
                     "not an allowed kind"),
    "concurrently": ('CREATE INDEX CONCURRENTLY "canary_index" ON "public"."specimen" ("state")', "CREATE INDEX",
                     "not an allowed kind"),
    "select": ("SELECT pg_sleep(60) AS canary", "SELECT", "not an allowed kind"),
    "unknown": ("canary_word (x)", "other", "not an allowed kind"),
}
RELEASE_PG = ("const fs=require('node:fs'),env=process.env,trace=x=>fs.appendFileSync(env.TEST_TRACE,JSON.stringify(x)+'\\n');"
              "exports.Pool=class{constructor(o){trace(['pool',o.user,o.database])}async end(){}async connect(){return {release(){},"
              "async query(q){const text=q.text??q;trace([text,q.queryMode??'simple']);"
              "if(text===env.TEST_FAIL) throw Object.assign(Error('canary'),{code:'57014'});"
              "for(const [key,value] of JSON.parse(env.TEST_ANSWERS)) if(text.includes(key)) return value;return {rows:[]}}}}};")
CONTEXT = {"database": D.DATABASE, "actor": I.MAINTENANCE, "effective": f"firebaseowner_{D.DATABASE}_public"}
NAMED = ["SELECT current_database() AS name", "simple"]
TRANSACTION = [[text, "simple"] for text in ("BEGIN", "SET LOCAL lock_timeout = '5s'", "SET LOCAL statement_timeout = '30s'",
               "SET LOCAL idle_in_transaction_session_timeout = '30s'", "SET LOCAL search_path = public",
               f'SET LOCAL ROLE "{CONTEXT["effective"]}"',
               "SELECT current_database() AS database, session_user AS actor, current_user AS effective")]


PAIRS = sorted(f"{table}.{column}" for table, column in RELAXED)


def plan(statements, **changes):
    """The data-migration/v1 plan Python writes: this commit's statements and the relaxed pairs. None drops a key."""
    value = {"version": "data-migration/v1", "source_sha": SHA, "statements": list(statements), "relaxed": PAIRS, **changes}
    return {key: item for key, item in value.items() if item is not None}


def release_sql(tmp_path, mode, statements=(), written=None, **env):
    """release_sql.mjs as the release identity for the admitted commit, with the plan Python writes for migrate."""
    path = tmp_path / "migration.json"
    path.write_text(json.dumps(plan(statements) if written is None else written))
    answers = [["AS name", {"rows": [{"name": D.DATABASE}]}], ["AS effective", {"rows": [CONTEXT]}]] + json.loads(
        env.pop("answers", "[]"))
    code, value, trace = node(tmp_path, "scripts/ci/release_sql.mjs", mode, {"DEPLOYMENT_ENVIRONMENT": "data-production",
                              "RELEASE_GATE_SHA": SHA, **env}, answers[::-1], pg=RELEASE_PG,
                              extra=[str(path)] if mode == "migrate" else [])
    return code, value, [json.loads(line) for line in trace]


def test_the_relaxable_columns_come_from_the_schema_gate_and_the_merged_schema_declares_no_persisted_view():
    merged = D.files_by(D.committed_source("dataconnect/schema"), "path")
    # Every @view here has sql, which Data Connect plans inline per query; none is a SQL view (RELEASE.md 4.3 step 5).
    assert schema_gate.declared_sql(merged, schema_gate.NAMED_RELAXATIONS) == (D.approved_tables(), set(), RELAXED)
    # The gate's relaxations come in as a parameter: another list narrows the relaxable pairs with it.
    assert schema_gate.declared_sql(merged, {("SourceAsset", "width"): "reason"})[2] == {("source_asset", "width")}


@pytest.mark.parametrize("sql", ALLOWED.values(), ids=ALLOWED)
def test_each_allowed_kind_passes(sql):
    assert D.migration_statement(sql, RELAXED)[1] is None


@pytest.mark.parametrize("sql,kind,reason", REFUSED.values(), ids=REFUSED)
def test_everything_else_is_refused_by_kind_and_node_refuses_it_again_before_connecting(tmp_path, sql, kind, reason):
    # Python and Node read the same relaxed set: Python's pairs, and the plan's "relaxed" for Node.
    assert D.migration_statement(sql, RELAXED) == (kind, reason)
    assert release_sql(tmp_path, "migrate", written=plan([ALLOWED["create-table"], sql], relaxed=PAIRS)) == (1, None, [])


def test_node_drops_not_null_only_on_a_pair_the_plan_lists(tmp_path):
    width = ALLOWED["drop-not-null"].split(",")[0]
    assert release_sql(tmp_path, "migrate", written=plan([width], relaxed=["source_asset.width"]))[:2] == (
        0, {"version": "data-migration/v1", "statements": 1, "committed": True})
    assert release_sql(tmp_path, "migrate", written=plan([width.replace("width", "height")], relaxed=["source_asset.width"])) == (
        1, None, [])


@pytest.mark.parametrize("changes", [
    {"relaxed": None}, {"relaxed": PAIRS[::-1]}, {"relaxed": [PAIRS[0], *PAIRS]}, {"relaxed": ",".join(PAIRS)},
    {"relaxed": ["Source_asset.width"]}, {"relaxed": ["source_asset"]}, {"relaxed": ["source_asset.width.x"]}, {"extra": []},
], ids=["missing", "unsorted", "duplicated", "not-a-list", "upper-case", "no-column", "three-parts", "extra-key"])
def test_node_refuses_a_plan_without_exactly_its_sorted_relaxed_pairs_before_connecting(tmp_path, changes):
    assert release_sql(tmp_path, "migrate", written=plan([ALLOWED["create-table"]]))[0] == 0
    assert release_sql(tmp_path, "migrate", written=plan([ALLOWED["create-table"]], **changes)) == (1, None, [])


def test_node_runs_every_allowed_kind_in_one_transaction_as_the_owner_through_the_extended_protocol(tmp_path):
    code, value, trace = release_sql(tmp_path, "migrate", ALLOWED.values())
    assert (code, value) == (0, {"version": "data-migration/v1", "statements": len(ALLOWED), "committed": True})
    assert trace == [["pool", I.MAINTENANCE, D.DATABASE], NAMED, *TRANSACTION,
                     *[[sql, "extended"] for sql in ALLOWED.values()], ["COMMIT", "simple"]]


def test_node_rolls_back_everything_when_a_statement_fails_or_the_role_differs_and_serves_only_this_commits_plan(tmp_path):
    statements = [ALLOWED["create-table"], ALLOWED["add-column"], ALLOWED["create-index"]]
    code, value, trace = release_sql(tmp_path, "migrate", statements, TEST_FAIL=statements[1])
    assert (code, value) == (1, None)
    assert trace[-3:] == [[statements[0], "extended"], [statements[1], "extended"], ["ROLLBACK", "simple"]]
    code, value, trace = release_sql(tmp_path, "migrate", statements, answers=json.dumps(
        [["AS effective", {"rows": [{**CONTEXT, "effective": I.MAINTENANCE}]}]]))
    assert (code, value) == (1, None) and trace[-2:] == [TRANSACTION[-1], ["ROLLBACK", "simple"]]
    assert release_sql(tmp_path, "migrate", written=plan(statements, source_sha="b" * 40)) == (1, None, [])
    assert release_sql(tmp_path, "migrate", []) == (1, None, [])


def test_node_creates_the_supplemental_indexes_concurrently_as_the_owner_role_of_the_session(tmp_path):
    code, _, trace = release_sql(tmp_path, "indexes")
    texts = [text for text, _ in trace[1:]]
    creates = [at for at, text in enumerate(texts) if text.startswith("CREATE INDEX CONCURRENTLY IF NOT EXISTS ")]
    assert code == 0 and len(creates) == 4 and texts[creates[0] - 1] == TRANSACTION[5][0].replace("LOCAL ", "")
    assert not any(text.startswith(("BEGIN", "SET LOCAL")) for text in texts[:creates[-1]])


POST = {"database_owner": "cloudsqlsuperuser", "schema_owner": CONTEXT["effective"]}
TABLES = sorted(D.approved_tables())
CATALOG = {"expected_database": True, "expected_actor": True, "tables": [f"public.{table}" for table in TABLES], "views": [],
           "owners": [CONTEXT["effective"]], "extensions": ["plpgsql", "uuid-ossp"], "postconditions": POST}


def test_node_checks_the_catalog_read_only_after_the_initializers_postconditions(tmp_path):
    catalog = {key: value for key, value in CATALOG.items() if key != "postconditions"}
    code, value, trace = release_sql(tmp_path, "migrated", answers=json.dumps([
        ["$postconditions$", [{"command": "DO"}, {"command": "SELECT", "rows": [{"postconditions": POST}]}]],
        ["AS extensions", {"rows": [catalog]}]]))
    texts = [text for text, _ in trace[2:]]
    assert (code, value) == (0, CATALOG) and texts[0] == "BEGIN TRANSACTION READ ONLY" and texts[-1] == "COMMIT"
    assert [at for at, text in enumerate(texts) if "$postconditions$" in text] == [2] and "AS extensions" in texts[3]


def error(diffs, violation="INCOMPATIBLE_SCHEMA", **detail):
    """A validate-only update's 400 body, in the shape firebase-tools 15.8.0 reads (lib/dataconnect/errors.js 10-41)."""
    return {"error": {"code": 400, "status": "FAILED_PRECONDITION", "message": "canary message", "details": [
        {"@type": "type.googleapis.com/google.firebase.dataconnect.v1.IncompatibleSqlSchemaError", "diffs": diffs, **detail},
        {"@type": "type.googleapis.com/google.rpc.PreconditionFailure", "violations": [{"type": violation, "subject": "canary"}]}]}}


class Plane:
    """The migrate job's live data plane behind its gate record; each effect and Node run is one ordered event."""
    def __init__(self, events, answer, attempt=1):
        self.plane, self.packet, self.events, self.answer = "data", record(release_run_attempt=attempt), events, answer
        datasource = {"database": D.DATABASE, "cloudSql": {"instance": f"projects/{D.PROJECT}/locations/us-east4/instances/{D.SOURCE}"}}
        self.live = {D.SCHEMA_NAME: {"name": D.SCHEMA_NAME, "etag": "placeholder-etag", "updateTime": UPDATED, "reconciling": False,
                                     "source": {}, "datasources": [{"postgresql": {**datasource, "schemaValidation": "STRICT",
                                                                                   "ephemeral": True}}]}}
        self.principal, self.release, self.patches = None, None, []

    def request(self, api, method, resource, *, body=None, params=None, missing=False, diff=False):
        if api == "sql" and method == "GET":
            return {"items": [self.principal] if self.principal else []} if resource.endswith("/users") else {
                "name": resource.rsplit("/", 1)[-1], "instance": D.SOURCE, "project": D.PROJECT, "region": "us-east4",
                "state": "RUNNABLE"}
        if api == "data" and method == "GET":
            assert resource in self.live or missing
            return copy.deepcopy(self.live.get(resource))
        if api == "data" and method == "PATCH":
            role, check = ("schema" if resource == D.SCHEMA_NAME else "connector"), params.get("validateOnly") == "true"
            self.patches.append((role, params, copy.deepcopy(body)))
            self.events.append(("diff" if role == "schema" else "connector-check") if check else role)
            if check and role == "schema" and self.answer is not None:
                failure = HTTPFailure(400)
                failure.body = self.answer if diff else None
                raise failure
            if not check:
                self.live[resource] = {**body, "etag": f"{role}-etag-2", "updateTime": UPDATED, "reconciling": False}
            return {"name": f"projects/{D.PROJECT}/locations/us-east4/operations/{len(self.events)}"}
        assert api == "rules" and resource in (D.RULE_RELEASE, f"projects/{D.PROJECT}/rulesets", f"projects/{D.PROJECT}/releases")
        if method == "GET":
            assert self.release is not None or missing
            return copy.deepcopy(self.release)
        self.events.append("ruleset" if resource.endswith("/rulesets") else "release")
        if resource.endswith("/rulesets"):
            return {"name": RULESET}
        self.release = {"name": D.RULE_RELEASE, "rulesetName": RULESET}
        return {}

    def wait(self, api, operation, **kwargs):
        assert api == "data" and operation["name"].startswith(f"projects/{D.PROJECT}/locations/us-east4/operations/")
        return {}


def inventory():
    """The supplemental index inventory release_sql.mjs indexes returns once every reviewed index exists."""
    indexes = []
    for name, (table, keys, includes) in D.INDEX_SPECS.items():
        definition = (f"CREATE {'UNIQUE ' if name == 'specimen_scope_checksum' else ''}INDEX {name} ON public.{table} USING btree "
                      f"({', '.join(keys)})" + (" INCLUDE (" + ", ".join(includes) + ")" if includes else ""))
        indexes.append({"name": name, "table_name": table, "method": "btree", "valid": True, "includes": includes,
                        "unique": name == "specimen_scope_checksum", "predicate": None, "definition": definition})
    return {"indexes": indexes, "rows": [{"table": table} for table in TABLES]}


@pytest.fixture
def migration(tmp_path, monkeypatch, capsys):
    """The migrate step, faking only this run's artifacts, their attestation, the post check and Node."""
    events, published, statements, plans = [], {}, [], []
    receipt = {"version": "data-initializer/v1", "source_sha": SHA, "run_id": 456, "run_attempt": 1, "instance": I.SOURCE,
               "database": I.DATABASE, "postconditions_sha256": I.sha(POST)}
    published[f"data-initializer-{SHA}-1"] = json.dumps(receipt).encode()
    monkeypatch.setattr(D, "gh_json", lambda path: {"total_count": len(published), "artifacts": [
        {"name": name, "expired": False, "workflow_run": {"id": 456}} for name in published]})
    monkeypatch.setattr(deploy_runtime, "checked", lambda command, **kwargs: Path(command[9], "data-initializer.json").write_bytes(
        published[command[7]]) if command[:7] == ["gh", "run", "download", "456", "--repo", D.REPOSITORY, "--name"]
        else pytest.fail("download"))
    monkeypatch.setattr(deploy_runtime, "verified_receipt_bytes", lambda path, sha256, source, workflow: Path(path).read_bytes()
                        if (hashlib.sha256(Path(path).read_bytes()).hexdigest(), source, workflow) == (sha256, SHA, "data-release.yml")
                        else pytest.fail("only this commit's signed receipt is consumed"))
    post = [POST]
    monkeypatch.setattr(I, "native", lambda directory, instance, mode, *, files, deadline, gate_sha=None: events.append(mode) or {
        "instance": instance, "mode": mode, "files": files, "postconditions": post[0]} if (instance, mode, files, gate_sha) == (
        I.SOURCE, "post", I.fingerprints(), SHA) else pytest.fail("only the gate path's post check"))
    outputs = {"indexes": inventory(), "migrated": copy.deepcopy(CATALOG)}

    def run(command, **kwargs):
        assert command[:2] == ["node", "scripts/ci/release_sql.mjs"] and command[3] == D.SOURCE
        assert kwargs["env"]["RELEASE_GATE_SHA"] == SHA and kwargs["cwd"] == D.ROOT
        events.append(command[2])
        if command[2] == "migrate":
            written = json.loads(D.private_bytes(Path(command[5])))
            assert set(written) == {"version", "source_sha", "statements", "relaxed"} and written["source_sha"] == SHA
            plans.append(written)
            statements.extend(written["statements"])
            outputs["migrate"] = {"version": "data-migration/v1", "statements": len(written["statements"]), "committed": True}
        Path(command[4]).write_text(json.dumps(outputs[command[2]]))
        Path(command[4]).chmod(0o600)
        return subprocess.CompletedProcess(command, 0, b"", b"")
    monkeypatch.setattr(D.subprocess, "run", run)
    output = tmp_path / "data-initialized.json"

    def migrate(plane):
        try:
            D.migrate_initialized(plane, tmp_path, output)
            plane.error = None
        except ValueError as failure:
            plane.error = str(failure)
        plane.log = capsys.readouterr().out
        assert "canary" not in plane.log
        return json.loads(output.read_text())
    return SimpleNamespace(migrate=migrate, events=events, published=published, statements=statements, outputs=outputs,
                           post=post, receipt=receipt, plans=plans)


DIFF = [ALLOWED["create-table"], ALLOWED["create-unique-index"]]
ORDER = ["post", "diff", "migrate", "schema", "indexes", "connector-check", "connector", "ruleset", "release", "migrated"]
EFFECTS = set(ORDER) - {"post", "diff"}


def initialized(attempt=1, **facts):
    return {"version": "data-initialized/v1", "phase": "initialize", "source_sha": SHA, "run_id": 456, "run_attempt": attempt,
            **dict.fromkeys(("schema_etag", "schema_update_time", "connector_etag", "storage_ruleset", "tables", "views")),
            **facts}


def test_the_owner_migrates_then_the_schema_indexes_connector_rules_and_catalog_follow_and_the_receipt_is_public(migration):
    plane = Plane(migration.events, error([{"sql": sql, "description": "canary description"} for sql in DIFF]))
    value = migration.migrate(plane)
    assert plane.error is None and migration.events == ORDER and migration.statements == DIFF
    assert "Migration: 1 CREATE TABLE, 1 CREATE UNIQUE INDEX." in plane.log
    # Validate-only, then the apply: COMPATIBLE, the merged sources, conditional on the placeholder's etag; never
    # Data Connect's server-side migration, which would run the DDL as its service agent.
    schema = [(params, body) for role, params, body in plane.patches if role == "schema"]
    assert [params for params, _ in schema] == [{"allowMissing": "true", "validateOnly": "true"}, {"allowMissing": "true"}]
    for _, body in schema:
        assert body["etag"] == "placeholder-etag" and body["source"] == D.committed_source("dataconnect/schema")
        assert body["datasources"] == [{"postgresql": {"database": D.DATABASE, "schemaValidation": "COMPATIBLE", "cloudSql": {
            "instance": f"projects/{D.PROJECT}/locations/us-east4/instances/{D.SOURCE}"}}}]
    assert [role for role, _, body in plane.patches if role == "connector" and "etag" not in body] == ["connector"] * 2
    assert value == initialized(schema_etag="schema-etag-2", schema_update_time=UPDATED, connector_etag="connector-etag-2",
                                storage_ruleset=RULESET, tables=len(TABLES), views=0)


def test_a_re_run_after_the_migration_committed_has_nothing_to_migrate_and_completes_the_release(migration):
    first = Plane(migration.events, error([{"sql": DIFF[0]}]))
    migration.migrate(first)  # Attempt 1 committed and released; attempt 2 consumes its receipt.
    plane = Plane(migration.events, None, attempt=2)
    plane.live, plane.release, migration.events[:] = first.live, first.release, []
    value = migration.migrate(plane)
    assert plane.error is None and migration.events == [event for event in ORDER if event != "migrate"]
    assert value["run_attempt"] == 2 and value["tables"] == len(TABLES)
    assert [body.get("etag") for _, _, body in plane.patches] == ["schema-etag-2"] * 2 + ["connector-etag-2"] * 2


def test_the_plan_carries_the_merged_schemas_relaxed_pairs_and_every_caller_reads_them_through_one_helper(
        migration, monkeypatch):
    """Rebasing onto relaxations read from the data contract repoints deploy_data.relaxations() alone."""
    merged = D.files_by(D.committed_source("dataconnect/schema"), "path")
    pairs = sorted(f"{table}.{column}" for table, column in schema_gate.declared_sql(merged, schema_gate.NAMED_RELAXATIONS)[2])
    assert D.relaxations() is schema_gate.NAMED_RELAXATIONS and pairs == PAIRS
    plane = Plane(migration.events, error([{"sql": ALLOWED["drop-not-null"]}]))
    migration.migrate(plane)
    assert plane.error is None and migration.plans == [
        {"version": "data-migration/v1", "source_sha": SHA, "statements": [ALLOWED["drop-not-null"]], "relaxed": pairs}]
    # A narrower list from the helper refuses the other column in Python and narrows the pairs Node reads.
    monkeypatch.setattr(D, "relaxations", lambda: {("SourceAsset", "width"): "reason"})
    plane = Plane(migration.events, error([{"sql": ALLOWED["drop-not-null"]}]))
    migration.migrate(plane)
    assert plane.error == "the migration refused 1 of 1 statement(s)" and len(migration.plans) == 1
    width = ALLOWED["drop-not-null"].split(",")[0]
    migration.migrate(Plane(migration.events, error([{"sql": width}])))
    assert migration.plans[1:] == [{"version": "data-migration/v1", "source_sha": SHA, "statements": [width],
                                    "relaxed": ["source_asset.width"]}]


@pytest.mark.parametrize("fault,message", [
    ("no-receipt", "this run's attested initializer receipt is missing or ambiguous"),
    ("two-receipts", "this run's attested initializer receipt is missing or ambiguous"),
    ("another-attempt", "this run's initializer receipt does not match its artifact"),
    ("changed-postconditions", "the database's postconditions changed since this run's initializer"),
    ("lingering-principal", "the initializer's SQL principal still exists; dispose of it, then re-run"),
    ("changed-schema", "the live schema or connector is neither the placeholder nor the merged files; reconcile them"),
])
def test_the_migration_needs_this_runs_receipt_the_exact_postconditions_no_principal_and_its_own_placeholder(
        migration, fault, message):
    plane = Plane(migration.events, error([{"sql": DIFF[0]}]), attempt=2)
    if fault == "no-receipt":
        migration.published.clear()
    elif fault == "two-receipts":
        migration.published[f"data-initializer-{SHA}-2"] = migration.published[f"data-initializer-{SHA}-1"]
    elif fault == "another-attempt":
        migration.published[f"data-initializer-{SHA}-1"] = json.dumps({**migration.receipt, "run_attempt": 2}).encode()
    elif fault == "changed-postconditions":
        migration.post[0] = {**POST, "schema_owner": "cloudsqlsuperuser"}
    elif fault == "lingering-principal":
        plane.principal = {"name": I.INITIALIZER_SQL, "type": "CLOUD_IAM_SERVICE_ACCOUNT"}
    else:
        plane.live[D.SCHEMA_NAME]["source"] = {"files": [{"path": "schema.gql", "content": "type A @table { id: UUID! }"}]}
    value = migration.migrate(plane)
    assert plane.error == message and f"Data release blocked: {message}." in plane.log
    assert not EFFECTS & set(migration.events) and plane.patches == [] and value == initialized(2)


def test_a_refused_statement_stops_everything_after_the_diff_and_the_log_names_kinds_only(migration):
    diffs = [{"sql": sql, "description": "canary description"} for sql, _, _ in REFUSED.values()]
    diffs += [{"sql": DIFF[1], "destructive": True}, {"sql": DIFF[0], "destructive": False}]
    plane = Plane(migration.events, error(diffs))
    value = migration.migrate(plane)
    assert plane.error == f"the migration refused {len(diffs) - 1} of {len(diffs)} statement(s)"
    assert migration.events == ["post", "diff"] and migration.statements == [] and value == initialized()
    assert [line for line in plane.log.splitlines() if line.startswith("Refused: ")] == [
        f"Refused: diff statement {at} of {len(diffs)} ({kind}): {reason}." for at, (_, kind, reason) in enumerate(REFUSED.values(), 1)
    ] + [f"Refused: diff statement {len(diffs) - 1} of {len(diffs)} (CREATE UNIQUE INDEX): marked destructive."]


@pytest.mark.parametrize("answer,message", [
    (error([{"sql": DIFF[0]}], violation="INACCESSIBLE_SCHEMA"), "Data Connect did not answer with a SQL diff for this database"),
    (error([{"sql": DIFF[0]}], violation="INCOMPATIBLE_CONNECTOR"), "Data Connect did not answer with a SQL diff for this database"),
    ({"error": {"details": [error([])["error"]["details"][1]]}}, "Data Connect did not answer with a SQL diff for this database"),
    (error([{"sql": DIFF[0]}, {"sql": DIFF[1], "canary": True}]), "Data Connect's SQL diff is malformed"),
    (error([{"sql": DIFF[0], "destructive": "no"}]), "Data Connect's SQL diff is malformed"),
    (error([]), "Data Connect's SQL diff is malformed"),
    (error([{"sql": DIFF[0]}], destructive=True), "Data Connect marked the SQL diff destructive"),
], ids=["inaccessible", "connector", "no-diff", "unknown-field", "bad-flag", "empty", "destructive"])
def test_only_an_incompatible_schema_diff_of_the_documented_shape_is_read(migration, answer, message):
    plane = Plane(migration.events, answer)
    assert migration.migrate(plane) == initialized() and plane.error == message
    assert migration.events == ["post", "diff"]


@pytest.mark.parametrize("change,message", [
    (lambda catalog: catalog["tables"].pop(), "the catalog's tables differ from the merged schema's"),
    (lambda catalog: catalog["tables"].append("public.canary_table"), "the catalog's tables differ from the merged schema's"),
    (lambda catalog: catalog["views"].append("public.specimen_listing"), "the catalog's views differ from the merged schema's"),
    (lambda catalog: catalog["owners"].append("cloudsqlsuperuser"), "a relation is not owned by the owner role"),
    (lambda catalog: catalog["extensions"].append("vector"), "the extensions are not exactly plpgsql and uuid-ossp"),
    (lambda catalog: catalog.update(postconditions={}), "the database's postconditions changed since this run's initializer"),
], ids=["missing-table", "extra-table", "persisted-view", "foreign-owner", "extension", "postconditions"])
def test_the_catalog_must_list_exactly_the_declared_tables_owned_by_the_owner_with_the_initializers_privileges(
        migration, change, message):
    change(migration.outputs["migrated"])
    plane = Plane(migration.events, error([{"sql": DIFF[0]}]))
    value = migration.migrate(plane)
    assert plane.error == message and migration.events == ORDER and value["tables"] is None and value["storage_ruleset"] == RULESET


def test_only_the_validate_only_schema_update_keeps_its_400_body(monkeypatch):
    google = object.__new__(release_google.Google)
    google.path, google.plane, google.packet = Path("packet.json"), "data", record(expires_at_unix=int(time.time()) + 600)
    monkeypatch.setattr(release_google, "admit", lambda path, plane: google.packet)
    answer = error([{"sql": DIFF[0]}])
    google.session = SimpleNamespace(request=lambda method, url, **kwargs: SimpleNamespace(status_code=400, json=lambda: answer))
    check = {"allowMissing": "true", "validateOnly": "true"}
    with pytest.raises(HTTPFailure) as failure:
        google.request("data", "PATCH", D.SCHEMA_NAME, body={}, params=check, diff=True)
    assert failure.value.http_status == 400 and failure.value.body == answer
    with pytest.raises(HTTPFailure) as failure:
        google.request("data", "PATCH", D.SCHEMA_NAME, body={}, params=check)
    assert failure.value.body is None
    for api, method, params in (("data", "PATCH", {"allowMissing": "true"}), ("rules", "PATCH", check), ("data", "POST", check)):
        with pytest.raises(ValueError, match="validate-only schema update"):
            google.request(api, method, D.SCHEMA_NAME, body={}, params=params, diff=True)
