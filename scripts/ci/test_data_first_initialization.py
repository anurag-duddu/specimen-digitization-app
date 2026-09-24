"""The first initialization on the gate path (RELEASE.md 4.3, T3c1 and T3c2): the Node connector serves an admitted
gate record's commit, the release identity reads the application database's summary, and the one-time initializer
commits on the source instance alone, then is disposed of only as this run's own. The migration then runs Data
Connect's diff client-side as the owner role.

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
import schema_gate
from test_data_released_deploy import EMPTY, SHA, record


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


# T3c2 (RELEASE.md 4.3 steps 3 to 5): Data Connect's diff, run client-side as the owner role, and read back.
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
