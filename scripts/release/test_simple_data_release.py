"""The simple data release: Data Connect's diff and the additive rule, the skips, the first rows, the init SQL."""
import base64
import copy
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import time
from types import SimpleNamespace
from uuid import UUID

import pytest

import data_release as D

ROOT = D.ROOT
PREPARED = D.reviewed.B._prepared
TREE = (ROOT / PREPARED.TREE_PATH).read_bytes()
INIT_SQL, DATA_SQL = ROOT / "scripts/release/sql/initialize.sql", ROOT / "scripts/release/data_sql.mjs"
# Synthetic stand-ins for the private values; none may ever reach the log.
ADMIN = {"uid": "admin-uid-canary", "email": "owner-canary@example.org", "emailVerified": True, "disabled": False}
ORGANIZATION, NAME, WORKER = "c0ffee00-7f3a-4b1c-8d2e-0000000000aa", "Canary Museum", "worker-uid-canary-0000000001"
OPERATION = f"projects/{D.PROJECT}/locations/{D.REGION}/operations/operation-1-abc"
STEP_NAMES = ["init", "diff", "apply", "schema", "indexes", "connector", "rules", "bootstrap"]
CREATE_TABLE = ('CREATE TABLE "public"."collection" ("organization_id" uuid NOT NULL, "id" uuid NOT NULL DEFAULT '
                'uuid_generate_v4(), "parent_id" uuid NULL, PRIMARY KEY ("organization_id", "id"), CONSTRAINT "scope_ref_1" '
                'FOREIGN KEY ("organization_id", "parent_id") REFERENCES "public"."collection" ("organization_id", "id") '
                "ON DELETE SET NULL)")
CREATE_INDEX = 'CREATE INDEX "specimen_due_work" ON "public"."specimen" ("organization_id", "state")'
# What Data Connect's migrator plans against a database that holds the four supplemental indexes (emulator 3.2.0).
OWN_INDEXES = ("auxiliary_text_cursor", "specimen_search_cursor", "specimen_text_cursor", "snapshot_search_batch")
DROPS = [f'DROP INDEX "public"."{name}"' for name in OWN_INDEXES]
SET_ASIDE = ("diff: set aside {} DROP INDEX statement(s), never run: Data Connect does not know the release's own "
             "supplemental indexes; they stay")
REFUSED = "diff: not additive, nothing was applied: {}. A destructive schema change stops the release and needs the owner's decision"


def bare(value):
    """SQL Connect returns UUID scalars without hyphens."""
    return UUID(value).hex


def artifact():
    """The owner's hierarchy artifact over the committed collection tree, with synthetic identifiers."""
    collections = [{"key": entry["key"], "id": f"c0ffee00-7f3a-4b1c-8d2e-{index:012x}", "name": entry["name"],
                    "parent": entry["parent"]} for index, entry in enumerate(PREPARED.tree_entries(TREE), start=1)]
    return PREPARED.prepare_first_scope_hierarchy(
        auth_record=ADMIN, requested_email=ADMIN["email"], requested_uid=ADMIN["uid"], organization_id=ORGANIZATION,
        organization_name=NAME, collections=collections, admin_collection_key="insects", tree=TREE)


def encoded(payload):
    return base64.b64encode(json.dumps(payload).encode()).decode()


def private(payload):
    values = {ADMIN["uid"], ADMIN["email"], ORGANIZATION, NAME, WORKER, payload["artifact_sha256"], encoded(payload),
              *(entry["id"] for entry in payload["hierarchy"]["collections"])}
    return values | {bare(entry["id"]) for entry in payload["hierarchy"]["collections"]} | {bare(ORGANIZATION)}


def incompatible(diffs, violation="INCOMPATIBLE_SCHEMA", **detail):
    """A validate-only schema update's 400 body, in the shape firebase-tools 15.8.0 reads (lib/dataconnect/errors.js)."""
    return {"error": {"code": 400, "status": "FAILED_PRECONDITION", "message": "schema is incompatible", "details": [
        {"@type": "type.googleapis.com/google.firebase.dataconnect.v1.IncompatibleSqlSchemaError", "diffs": diffs, **detail},
        {"@type": "type.googleapis.com/google.rpc.PreconditionFailure",
         "violations": [{"type": violation, "subject": "main"}]}]}}


def entry(sql, **more):
    return {"sql": sql, "description": "a change", "destructive": False, **more}


def files(folder):
    return [{"path": name, "content": text} for name, text in D.committed(folder).items()]


class Answer:
    def __init__(self, status, body):
        self.status_code, self.body = status, body

    def json(self):
        if self.body is None:
            raise ValueError("no JSON")
        return copy.deepcopy(self.body)


class Scripted:
    """A session that answers from a script, one item per request: an Answer, or an exception to raise."""

    def __init__(self, *script):
        self.script, self.requests = list(script), []

    def request(self, method, url, json=None, params=None, timeout=None):
        self.requests.append((method, url.split("/v1/", 1)[1]))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def busy(status=503):
    return Answer(status, {"error": {"code": status, "message": "try later"}})


class Google:
    """A scripted Google behind the authorized session: the Data Connect schema, connector and operations, the Storage
    rules, the worker's secret and the application's rows behind the admin GraphQL endpoints. `events` lists every
    effect in order; `calls` lists every request."""

    def __init__(self, payload=None):
        self.payload, self.calls, self.events = payload, [], []
        # The live placeholder: no source files, and a datasource that says more than a release sends.
        self.schema = {"name": D.SCHEMA, "source": {}, "datasources": [{"postgresql": {
            "database": D.DATABASE, "schemaValidation": "STRICT", "cloudSql": {
                "instance": f"projects/{D.PROJECT}/locations/{D.REGION}/instances/{D.INSTANCE}",
                "edition": "EDITION_ENTERPRISE"}}}]}
        self.connector, self.diff, self.release, self.rulesets = None, None, None, {}
        self.rows = {"organization": None, "collections": [], "organizationMembers": [], "members": []}
        self.secret_status, self.graphql_error = 200, None

    def converge(self):
        """Everything already equals the committed files."""
        self.schema["source"], self.connector = {"files": files("dataconnect/schema")}, {
            "name": D.CONNECTOR, "source": {"files": files("dataconnect/connector")}}
        self.rulesets["live"] = (ROOT / "storage.rules").read_text()
        self.release = f"projects/{D.PROJECT}/rulesets/live"
        return self

    def seed(self, worker=True):
        """The rows a finished bootstrap leaves behind."""
        variables, entries = self.payload["request"]["variables"], self.payload["hierarchy"]["collections"]
        ids = {item["key"]: item["id"] for item in entries}
        self.rows = {
            "organization": {"id": bare(ORGANIZATION), "name": variables["organizationName"]},
            "collections": [{"id": bare(item["id"]), "organizationId": bare(ORGANIZATION), "name": item["name"],
                             "parentId": bare(ids[item["parent"]]) if item["parent"] else None} for item in entries],
            "organizationMembers": [{"uid": variables["uid"], "active": True}],
            "members": [{"uid": variables["uid"], "collectionId": bare(variables["collectionId"]), "active": True,
                         "role": "admin", "canViewSensitive": False}]}
        if worker:
            self.rows["organizationMembers"].append({"uid": WORKER, "active": True})
            self.rows["members"].append({"uid": WORKER, "collectionId": bare(ids["insects"]), "active": True,
                                         "role": "operator", "canViewSensitive": False})
        return self

    def request(self, method, url, json=None, params=None, timeout=None):
        assert timeout == D.HTTP_SECONDS, "every request carries a timeout"
        resource, params = url.split("/v1/", 1)[1], params or {}
        self.calls.append((method, resource))
        return Answer(*self.answer(method, url, resource, json, params))

    def answer(self, method, url, resource, body, params):
        if url == D.WORKER_UID_URL:
            assert method == "GET"
            return self.secret_status, {"payload": {"data": base64.b64encode(WORKER.encode()).decode()}}
        if url.startswith(D.RULES):
            return self.storage(method, resource, body)
        if resource.endswith((":executeGraphql", ":executeGraphqlRead")):
            assert method == "POST" and resource.startswith(D.SERVICE + ":")
            return self.graphql(resource.rsplit(":", 1)[1], body)
        if resource == OPERATION:
            return 200, {"name": OPERATION, "done": True, "response": {}}
        role = {D.SCHEMA: "schema", D.CONNECTOR: "connector"}[resource]
        if method == "GET":
            live = getattr(self, role)
            return (200, live) if live else (404, {"error": {"code": 404, "message": "not found"}})
        assert method == "PATCH" and params.get("allowMissing") == "true" and body["name"] == resource
        if params.get("validateOnly") == "true":
            self.events.append("diff")
            return (400, self.diff) if self.diff else (200, {})
        self.events.append(role)
        setattr(self, role, {**(getattr(self, role) or {}), "name": resource, "source": copy.deepcopy(body["source"])})
        return 200, {"name": OPERATION, "done": False}

    def storage(self, method, resource, body):
        if resource == D.RULE_RELEASE and method == "GET":
            return (200, {"name": D.RULE_RELEASE, "rulesetName": self.release}) if self.release else (404, {})
        if resource == D.RULE_RELEASE and method == "PATCH":
            self.events.append("release")
            self.release = body["release"]["rulesetName"]
            return 200, {"name": D.RULE_RELEASE, "rulesetName": self.release}
        if resource == f"projects/{D.PROJECT}/releases" and method == "POST":
            self.events.append("release")
            self.release = body["rulesetName"]
            return 200, body
        if resource == f"projects/{D.PROJECT}/rulesets" and method == "POST":
            self.events.append("ruleset")
            name = f"new{len(self.rulesets)}"
            self.rulesets[name] = body["source"]["files"][0]["content"]
            return 200, {"name": f"projects/{D.PROJECT}/rulesets/{name}"}
        assert method == "GET"
        name = resource.rsplit("/", 1)[1]
        return 200, {"name": resource, "source": {"files": [{"name": "storage.rules", "content": self.rulesets[name]}]}}

    def graphql(self, verb, body):
        query, variables = body["query"], body.get("variables", {})
        if self.graphql_error and verb == "executeGraphql":
            return 200, {"errors": [{"message": self.graphql_error, "path": ["organization_insert"]}]}
        if query == D.ANY_ORGANIZATION:
            return 200, {"data": {"organizations": [self.rows["organization"]] if self.rows["organization"] else []}}
        if query == D.reviewed.READ_SCOPE:
            assert variables["limit"] == len(variables["ids"]) + 1 and variables["organizationId"] == ORGANIZATION
            return 200, {"data": {**copy.deepcopy(self.rows), "matchingCollections": copy.deepcopy(self.rows["collections"])}}
        if query == D.reviewed.READ_WORKER:
            return 200, {"data": {
                "organizationMember": next((row for row in self.rows["organizationMembers"] if row["uid"] == variables["uid"]), None),
                "members": [row for row in self.rows["members"] if row["uid"] == variables["uid"]]}}
        assert verb == "executeGraphql"
        if query.startswith("mutation PrepareFirstScopeHierarchy("):
            assert body == self.payload["request"] and self.rows["organization"] is None
            self.events.append("hierarchy")
            self.seed(worker=False)
        else:
            assert query.startswith("mutation PrepareWorkerMembership(") and variables["uid"] == WORKER
            self.events.append("worker")
            self.rows["organizationMembers"].append({"uid": WORKER, "active": True})
            self.rows["members"].append({"uid": WORKER, "collectionId": bare(variables["c0"]), "active": True,
                                         "role": "operator", "canViewSensitive": False})
        return 200, {"data": {}}

    def writes(self):
        """Every request that is not a read: all but GETs, the validate-only diff and read-only GraphQL."""
        return [event for event in self.events if event != "diff"]


class Sql:
    """data_sql.mjs's modes over a pretend database; a migration makes the next diff empty."""

    def __init__(self, google, initialized=True, indexed=True, invalid=()):
        self.google, self.initialized, self.indexed, self.invalid = google, initialized, indexed, list(invalid)
        self.calls, self.plans = [], []

    def __call__(self, mode, *arguments):
        self.calls.append(mode)
        if mode == "probe":
            return {"owner_role": self.initialized, "uuid_ossp_in_public": self.initialized, "default_privileges": True}
        if mode == "init":
            self.google.events.append("init")
            self.initialized = True
        elif mode == "migrate":
            self.google.events.append("migrate")
            self.plans.append(json.loads(Path(arguments[0]).read_text()))
            self.google.diff = None
        else:
            assert (mode, arguments) == ("indexes", D.INDEX_FILES)
            created, self.indexed = [] if self.indexed else ["specimen_text_cursor", "snapshot_search_batch"], True
            self.google.events.extend(["indexes"] if created else [])
            return {"created": created, "invalid": self.invalid}


def release(google, sql=None, text=""):
    return D.Release(D.Api(google), sql or Sql(google), text)


@pytest.fixture(autouse=True)
def waits(monkeypatch):
    """No test waits; the seconds each would have slept are recorded. Only the release module's view of time is
    replaced: the real time.sleep stays, since subprocess waits with it."""
    slept = []
    monkeypatch.setattr(D, "time", SimpleNamespace(sleep=slept.append, monotonic=time.monotonic))
    return slept


# The diff and the additive rule.

def test_a_recorded_incompatible_schema_answer_parses_to_its_statements():
    body = incompatible([entry(CREATE_TABLE), entry(CREATE_INDEX)], destructive=False)
    diffs, destructive = D.parse_diff(body)
    assert [diff["sql"] for diff in diffs] == [CREATE_TABLE, CREATE_INDEX] and destructive is False
    assert D.parse_diff(incompatible([entry(CREATE_INDEX)], destructive=True))[1] is True


@pytest.mark.parametrize("body, reason", [
    (incompatible([entry(CREATE_TABLE)], violation="INACCESSIBLE_SCHEMA"), "INACCESSIBLE_SCHEMA"),
    ({"error": {"code": 400, "message": "schema.gql:3: unknown type Specimn", "details": [
        {"@type": "type.googleapis.com/google.firebase.dataconnect.v1.GraphqlError"}]}}, "unknown type Specimn"),
    ({"error": {"code": 400, "message": "two diffs", "details": incompatible([entry(CREATE_INDEX)])["error"]["details"] * 2}},
     "two diffs"),
    (incompatible([]), "no readable statements"),
    (incompatible([{"description": "no sql"}]), "no readable statements"),
    (None, "no message"),
])
def test_any_other_answer_is_a_failure_that_says_why(body, reason):
    with pytest.raises(D.Failure, match=re.escape(reason)):
        D.parse_diff(body)


@pytest.mark.parametrize("diffs", [[], [entry(CREATE_TABLE)]])
def test_a_schema_the_live_connector_does_not_fit_has_its_own_message_and_names_the_connector(diffs):
    # Alone, or beside a SQL diff: the live connector still holds an operation the committed schema dropped.
    body = incompatible(diffs) if diffs else {"error": {"code": 400, "message": "", "details": [
        {"@type": "type.googleapis.com/google.rpc.PreconditionFailure", "violations": []}]}}
    body["error"]["message"] = "connector specimen-server:\n  operation ListOld uses field Specimen.old"
    body["error"]["details"][-1]["violations"].append({"type": "INCOMPATIBLE_CONNECTOR", "subject": D.CONNECTOR})
    google = Google()
    google.diff = body
    run = release(google)
    with pytest.raises(D.Failure) as failure:
        D.diff(run)
    assert str(failure.value) == (
        f"diff: the committed schema does not fit the live connector ({D.CONNECTOR}); this needs the owner's decision. "
        "Data Connect said: connector specimen-server: operation ListOld uses field Specimen.old")
    assert "refused the committed schema" not in str(failure.value)
    # Nothing is applied and the connector is neither removed nor rewritten.
    assert run.statements == [] and run.sql.calls == [] and google.writes() == []
    assert not any(method == "DELETE" or resource == D.CONNECTOR for method, resource in google.calls)


# The release's own supplemental indexes: Data Connect does not know them and may ask to remove them.

def test_the_releases_own_indexes_are_read_from_the_committed_index_files():
    assert D.own_indexes() == set(OWN_INDEXES)
    created = re.findall(r"CREATE INDEX CONCURRENTLY IF NOT EXISTS (\w+)", "".join((ROOT / file).read_text() for file in D.INDEX_FILES))
    assert sorted(created) == sorted(OWN_INDEXES)


@pytest.mark.parametrize("sql", [
    *DROPS,
    'DROP INDEX "public"."specimen_text_cursor";',
    'DROP INDEX IF EXISTS "public"."specimen_text_cursor"',
    'DROP INDEX CONCURRENTLY "public"."specimen_text_cursor"',
    'DROP INDEX CONCURRENTLY IF EXISTS "public"."specimen_text_cursor" ;',
    'DROP INDEX "specimen_text_cursor"',
    "DROP INDEX public.specimen_text_cursor",
    "drop index if exists specimen_text_cursor;\n",
    "DROP INDEX Public.Specimen_Text_Cursor",
])
def test_a_drop_of_one_own_index_is_recognised_in_the_forms_the_differ_writes(sql):
    assert D.own_index_drop(sql, D.own_indexes())


@pytest.mark.parametrize("sql", [
    'DROP INDEX "public"."specimen_due_work"',
    'DROP INDEX "public"."specimen_text_cursor" CASCADE',
    'DROP INDEX "public"."specimen_text_cursor", "public"."specimen_due_work"',
    'DROP INDEX "other"."specimen_text_cursor"',
    'DROP INDEX "PUBLIC"."specimen_text_cursor"',
    'DROP INDEX "public"."Specimen_Text_Cursor"',
    'DROP INDEX "public"."specimen_text_cursor"; DROP TABLE "public"."specimen"',
    'DROP INDEX "public"."specimen_text_cursor" -- and more',
    'DROP TABLE "public"."specimen_text_cursor"',
    'ALTER TABLE "public"."specimen" DROP CONSTRAINT "specimen_text_cursor"',
])
def test_any_other_removal_is_not_set_aside_and_stays_refused(sql):
    assert not D.own_index_drop(sql, D.own_indexes()) and D.refusal(sql) is not None


def test_drops_of_the_releases_own_indexes_alone_are_no_sql_change_and_nothing_runs(capsys):
    google = Google().converge()
    google.diff = incompatible([entry(sql, destructive=True) for sql in DROPS], destructive=True)
    run = release(google)
    D.diff(run)
    D.apply(run)
    D.schema(run)
    assert run.statements == [] and run.sql.calls == [] and google.writes() == []
    assert capsys.readouterr().out.splitlines() == [
        "diff: 4 SQL statement(s) from Data Connect", *(f"  [{at}] {sql}" for at, sql in enumerate(DROPS, 1)),
        SET_ASIDE.format(4), "apply: no SQL change, skipped", "schema: live sources equal the committed ones, skipped"]


def test_only_the_other_statements_of_a_mixed_diff_are_applied(capsys):
    google = Google()
    mixed = [entry(DROPS[0], destructive=True), entry(CREATE_TABLE), entry(DROPS[1], destructive=True),
             entry(CREATE_INDEX), entry(DROPS[2], destructive=True), entry(DROPS[3], destructive=True)]
    google.diff = incompatible(mixed, destructive=True)
    run = release(google)
    D.diff(run)
    D.apply(run)
    assert run.statements == [CREATE_TABLE, CREATE_INDEX] and run.sql.plans == [{"statements": [CREATE_TABLE, CREATE_INDEX]}]
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "diff: 6 SQL statement(s) from Data Connect" and out[-2:] == [
        SET_ASIDE.format(4), "apply: committed 2 statement(s) in one transaction"]


@pytest.mark.parametrize("extra, reasons", [
    (entry('DROP INDEX "public"."specimen_due_work"'), ["statement 5 DROP removes or renames something"]),
    (entry('DROP INDEX "public"."specimen_due_work"', destructive=True),
     ["Data Connect marked the diff destructive", "statement 5 Data Connect marked it destructive"]),
    (entry('DROP TABLE "public"."specimen"'), ["statement 5 DROP removes or renames something"]),
    (entry('DROP TABLE "public"."specimen"', destructive=True),
     ["Data Connect marked the diff destructive", "statement 5 Data Connect marked it destructive"]),
])
def test_another_removal_is_refused_exactly_as_before_even_with_the_four_present(extra, reasons):
    google = Google()
    google.diff = incompatible([*(entry(sql, destructive=True) for sql in DROPS), extra], destructive=True)
    run = release(google)
    with pytest.raises(D.Failure) as failure:
        D.diff(run)
    assert str(failure.value) == REFUSED.format("; ".join(reasons))
    assert run.statements == [] and run.sql.calls == [] and google.writes() == []


def test_a_destructive_mark_no_set_aside_statement_explains_still_refuses():
    google = Google()
    google.diff = incompatible([entry(CREATE_INDEX)], destructive=True)
    with pytest.raises(D.Failure) as failure:
        D.diff(release(google))
    assert str(failure.value) == REFUSED.format("Data Connect marked the diff destructive")


@pytest.mark.parametrize("sql", [
    CREATE_TABLE,
    CREATE_INDEX,
    'CREATE UNIQUE INDEX "specimen_scope_checksum" ON "public"."specimen" USING btree ("organization_id", "source_checksum")',
    'ALTER TABLE "public"."specimen" ADD COLUMN "note" text NULL DEFAULT \'x, y\'',
    'ALTER TABLE "public"."source_asset" ADD CONSTRAINT "specimen_unique_1" UNIQUE ("bucket", "object_name")',
    'ALTER TABLE "public"."label_region" ADD CONSTRAINT "scope_ref_16" FOREIGN KEY ("organization_id") REFERENCES '
    '"public"."source_asset" ("organization_id") ON DELETE CASCADE',
    'ALTER TABLE "public"."source_asset" ALTER COLUMN "width" DROP NOT NULL, ALTER COLUMN "height" drop  not null',
    'CREATE EXTENSION IF NOT EXISTS "uuid-ossp"',
    'ALTER TABLE "public"."specimen" ADD COLUMN "drop" text, ADD COLUMN "Rename Delete" text',
    "ALTER TABLE \"public\".\"specimen\" ADD COLUMN \"note\" text DEFAULT 'drop table x; truncate it''s delete'",
    'ALTER TABLE "public"."specimen" ADD COLUMN "deleted_at" timestamptz, ADD COLUMN dropped boolean',
])
def test_additive_statements_are_accepted(sql):
    assert D.refusal(sql) is None


@pytest.mark.parametrize("sql, word", [
    ('DROP TABLE "public"."specimen"', "DROP"),
    ('drop table "public"."specimen"', "DROP"),
    ('ALTER TABLE "public"."specimen" DROP COLUMN "note"', "DROP"),
    ('ALTER TABLE "public"."specimen" ADD COLUMN "a" text, DROP COLUMN "note"', "DROP"),
    ('ALTER TABLE "public"."specimen" DROP CONSTRAINT "scope_ref_3"', "DROP"),
    ('ALTER TABLE "public"."specimen" ALTER COLUMN "note" DROP DEFAULT', "DROP"),
    ('DROP INDEX "public"."specimen_due_work"', "DROP"),
    ('TRUNCATE "public"."specimen"', "TRUNCATE"),
    ('DELETE FROM "public"."specimen"', "DELETE"),
    ('ALTER TABLE "public"."specimen" RENAME COLUMN "note" TO "notes"', "RENAME"),
    ('ALTER TABLE "public"."specimen" RENAME TO "specimens"', "RENAME"),
    (CREATE_INDEX + '; DROP TABLE "public"."specimen"', "DROP"),
    ('CREATE RULE r AS ON DELETE TO "public"."specimen" DO INSTEAD NOTHING', "DELETE"),
])
def test_removing_statements_are_refused_by_their_keyword(sql, word):
    assert D.refusal(sql).startswith(word + " ")


@pytest.mark.parametrize("sql", [
    "ALTER TABLE public.specimen ADD COLUMN note text DEFAULT E'\\'' ; DROP TABLE specimen --'",
    CREATE_INDEX + " /* ' */ ; DROP TABLE specimen /* ' */",
    CREATE_INDEX + " -- ' \n; DROP TABLE specimen -- '",
    "DO $do$ BEGIN EXECUTE 'x'; END $do$",
    "SELECT $$ ' $$ ; DROP TABLE specimen; --'",
    "ALTER TABLE public.specimen ADD COLUMN note text DEFAULT 'unbalanced",
])
def test_a_statement_whose_quoting_cannot_be_read_safely_is_refused(sql):
    assert "safely" in D.refusal(sql)


def test_the_diff_step_prints_every_statement_and_keeps_them_for_the_apply(capsys):
    google = Google()
    google.diff = incompatible([entry(CREATE_TABLE), entry("CREATE INDEX a\n  ON b (c)")])
    run = release(google)
    D.diff(run)
    assert run.statements == [CREATE_TABLE, "CREATE INDEX a\n  ON b (c)"] and google.calls == [("PATCH", D.SCHEMA)]
    assert capsys.readouterr().out.splitlines() == [
        "diff: 2 SQL statement(s) from Data Connect", f"  [1] {CREATE_TABLE}",
        "  [2] CREATE INDEX a ON b (c)"]


def test_the_validate_only_update_sends_the_committed_schema_in_compatible_mode():
    seen = []

    class Session:
        def request(self, method, url, json=None, params=None, timeout=None):
            seen.append((method, url, params, json))
            return Answer(200, {})

    D.diff(D.Release(D.Api(Session()), None))
    (method, url, params, body), = seen
    assert (method, url, params) == ("PATCH", D.DATA + D.SCHEMA, {"allowMissing": "true", "validateOnly": "true"})
    assert body == {"name": D.SCHEMA, "source": {"files": files("dataconnect/schema")}, "datasources": [{"postgresql": {
        "database": "specimen-digitization-database", "schemaValidation": "COMPATIBLE", "cloudSql": {
            "instance": "projects/specimen-digitization/locations/us-east4/instances/specimen-digitization-instance"}}}]}
    assert len(body["source"]["files"]) >= 6 and all(item["path"].endswith(".gql") for item in body["source"]["files"])


@pytest.mark.parametrize("diffs, detail, reasons", [
    ([entry(CREATE_INDEX), entry('DROP TABLE "public"."old"')], {}, ["statement 2 DROP removes or renames something"]),
    ([entry(CREATE_INDEX, destructive=True)], {}, ["statement 1 Data Connect marked it destructive"]),
    ([entry(CREATE_INDEX)], {"destructive": True}, ["Data Connect marked the diff destructive"]),
])
def test_a_diff_that_is_not_additive_stops_the_release_before_any_sql(capsys, diffs, detail, reasons):
    google = Google()
    google.diff = incompatible(diffs, **detail)
    run = release(google)
    with pytest.raises(D.Failure) as failure:
        D.diff(run)
    assert all(reason in str(failure.value) for reason in reasons) and "nothing was applied" in str(failure.value)
    assert str(failure.value).endswith(". A destructive schema change stops the release and needs the owner's decision")
    assert "by hand" not in str(failure.value)
    assert run.statements == [] and run.sql.calls == [] and google.writes() == []
    # Every statement is printed, the refused ones too.
    assert [line[6:] for line in capsys.readouterr().out.splitlines()[1:]] == [diff["sql"] for diff in diffs]


def test_a_server_error_on_the_diff_is_not_read_as_a_diff():
    class Session:
        def request(self, *args, **kwargs):
            return Answer(503, {"error": {"code": 503, "message": "try later"}})

    with pytest.raises(D.HttpFailure, match="HTTP 503: try later"):
        D.diff(D.Release(D.Api(Session()), None))


@pytest.mark.parametrize("error, line", [
    (D.GoogleAuthError("the credential is rejected by the attribute condition"),
     "Google refused the workflow's identity (the credential is rejected by the attribute condition); the owner runs "
     "scripts/ops/owner_setup.sh once"),
    (ConnectionError("reset"), "got no answer (ConnectionError); re-run the workflow"),
])
def test_a_refused_identity_or_a_lost_connection_is_one_actionable_line(error, line):
    class Session:
        def request(self, *args, **kwargs):
            raise error

    with pytest.raises(D.Failure) as failure:
        D.Api(Session()).call("GET", D.DATA + D.SCHEMA)
    assert str(failure.value) == f"GET {D.SCHEMA}" + (": " if "refused" in line else " ") + line


# Transient failures: a call that changes nothing is tried again, a write never is.

@pytest.mark.parametrize("first, problem", [
    (busy(503), "HTTP 503"), (busy(500), "HTTP 500"), (busy(502), "HTTP 502"), (busy(504), "HTTP 504"), (busy(429), "HTTP 429"),
    (ConnectionError("reset"), "no answer (ConnectionError)"), (TimeoutError("slow"), "no answer (TimeoutError)"),
])
def test_a_read_that_fails_transiently_is_tried_again_and_says_so(capsys, waits, first, problem):
    session = Scripted(first, Answer(200, {"name": D.SCHEMA}))
    assert D.Api(session).call("GET", D.DATA + D.SCHEMA) == {"name": D.SCHEMA}
    assert session.requests == [("GET", D.SCHEMA)] * 2 and waits == [D.BACKOFF_SECONDS]
    assert capsys.readouterr().out == f"GET {D.SCHEMA}: {problem} on attempt 1 of 3; trying again\n"


def test_three_transient_failures_in_a_row_stop_the_release(capsys, waits):
    session = Scripted(busy(), busy(), busy())
    with pytest.raises(D.HttpFailure, match="HTTP 503: try later"):
        D.Api(session).call("GET", D.DATA + D.SCHEMA)
    assert len(session.requests) == 3 == D.ATTEMPTS and waits == [D.BACKOFF_SECONDS, 2 * D.BACKOFF_SECONDS]
    assert capsys.readouterr().out.splitlines() == [
        f"GET {D.SCHEMA}: HTTP 503 on attempt {attempt} of 3; trying again" for attempt in (1, 2)]
    lost = Scripted(ConnectionError("a"), ConnectionError("b"), ConnectionError("c"))
    with pytest.raises(D.Failure, match=r"got no answer \(ConnectionError\); re-run the workflow"):
        D.Api(lost).call("GET", D.DATA + D.SCHEMA)
    assert len(lost.requests) == 3


def test_every_kind_of_read_is_tried_again(capsys):
    # The validate-only update, a read-only GraphQL call, the worker secret and an operation poll change nothing.
    session = Scripted(busy(), Answer(200, {}))
    D.diff(D.Release(D.Api(session), None))
    assert session.requests == [("PATCH", D.SCHEMA)] * 2
    session = Scripted(busy(), Answer(200, {"data": {"organizations": []}}))
    assert D.graphql(D.Api(session), "executeGraphqlRead", {"query": D.ANY_ORGANIZATION}, "the read") == {"organizations": []}
    assert session.requests == [("POST", f"{D.SERVICE}:executeGraphqlRead")] * 2
    session = Scripted(busy(), Answer(200, {"payload": {"data": "eA=="}}))
    assert D.Api(session).call("GET", D.WORKER_UID_URL, private=True) == {"payload": {"data": "eA=="}}
    session = Scripted(busy(), Answer(200, {"name": OPERATION, "done": True}))
    D.Api(session).wait({"name": OPERATION, "done": False}, "schema")
    assert session.requests == [("GET", OPERATION)] * 2
    # Each retry line names the method and the resource path, never a query, a body or a value.
    assert all(re.fullmatch(r"(GET|PATCH|POST) projects/[A-Za-z0-9_./:-]+: HTTP 503 on attempt 1 of 3; trying again", line)
               for line in capsys.readouterr().out.splitlines() if "trying again" in line)


@pytest.mark.parametrize("failure", [busy(), busy(429), ConnectionError("reset")])
def test_a_write_is_never_tried_again(capsys, waits, failure):
    def once(act):
        session = Scripted(failure)
        with pytest.raises(D.Failure):
            act(D.Api(session))
        assert len(session.requests) == 1
        return session

    once(lambda api: api.call("PATCH", D.DATA + D.SCHEMA, body={}, params={"allowMissing": "true"}))
    once(lambda api: api.call("PATCH", D.DATA + D.CONNECTOR, body={}, params={"allowMissing": "true"}))
    once(lambda api: api.call("POST", f"{D.RULES}projects/{D.PROJECT}/rulesets", body={}))
    once(lambda api: api.call("POST", f"{D.RULES}projects/{D.PROJECT}/releases", body={}))
    once(lambda api: api.call("PATCH", D.RULES + D.RULE_RELEASE, body={}))
    once(lambda api: D.graphql(api, "executeGraphql", {"query": "mutation M { x }"}, "the write"))
    assert waits == [] and capsys.readouterr().out == ""


def test_a_real_schema_update_that_fails_is_sent_once(waits):
    session = Scripted(Answer(200, {"name": D.SCHEMA, "source": {}}), busy())
    with pytest.raises(D.HttpFailure, match="HTTP 503"):
        D.schema(D.Release(D.Api(session), None))
    assert session.requests == [("GET", D.SCHEMA), ("PATCH", D.SCHEMA)] and waits == []


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409])
def test_an_answer_that_is_not_transient_is_not_tried_again(waits, status):
    session = Scripted(busy(status))
    with pytest.raises(D.HttpFailure):
        D.Api(session).call("GET", D.DATA + D.SCHEMA)
    missing = Scripted(busy(404))
    assert D.Api(missing).call("GET", D.DATA + D.CONNECTOR, missing=True) is None
    assert len(session.requests) == 1 == len(missing.requests) and waits == []


def test_a_forbidden_call_names_the_owner_setup_and_a_private_one_quotes_nothing():
    class Session:
        def request(self, *args, **kwargs):
            return Answer(403, {"error": {"code": 403, "message": "Permission 'x.y.z' denied"}})

    with pytest.raises(D.HttpFailure) as public:
        D.Api(Session()).call("GET", D.DATA + D.SCHEMA)
    assert str(public.value) == (f"GET {D.SCHEMA} answered HTTP 403: Permission 'x.y.z' denied (the owner runs "
                                 "scripts/ops/owner_setup.sh once if a permission is missing)")
    with pytest.raises(D.HttpFailure) as private:
        D.Api(Session()).call("GET", D.DATA + D.SCHEMA, private=True)
    assert "denied" not in str(private.value) and private.value.body is None and private.value.status == 403


# The skips: a step whose live state equals the committed files sends nothing.

def test_schema_and_connector_equal_to_the_committed_files_are_not_sent_again(capsys):
    google = Google().converge()
    run = release(google)
    D.schema(run)
    D.connector(run)
    assert google.calls == [("GET", D.SCHEMA), ("GET", D.CONNECTOR)] and google.events == []
    assert capsys.readouterr().out.splitlines() == ["schema: live sources equal the committed ones, skipped",
                                                    "connector: live sources equal the committed ones, skipped"]


def test_the_live_datasource_may_say_more_than_the_release_sends():
    google = Google().converge()
    assert google.schema["datasources"][0]["postgresql"]["cloudSql"]["edition"] == "EDITION_ENTERPRISE"
    D.schema(release(google))
    assert google.events == []


def test_a_changed_or_missing_source_is_sent_and_its_operation_followed():
    google = Google().converge()
    google.schema["source"]["files"][0]["content"] += "# changed\n"
    google.connector = None
    run = release(google)
    D.schema(run)
    D.connector(run)
    assert google.events == ["schema", "connector"]
    assert google.calls == [("GET", D.SCHEMA), ("PATCH", D.SCHEMA), ("GET", OPERATION),
                            ("GET", D.CONNECTOR), ("PATCH", D.CONNECTOR), ("GET", OPERATION)]
    assert D.live_files(google.schema) == D.committed("dataconnect/schema")
    assert D.live_files(google.connector) == D.committed("dataconnect/connector")


def test_the_schema_is_sent_after_a_migration_even_when_its_files_are_equal():
    google = Google().converge()
    run = release(google)
    run.statements = [CREATE_INDEX]
    D.schema(run)
    assert google.events == ["schema"]


def test_an_operation_that_fails_or_never_finishes_stops_the_release(monkeypatch):
    api = D.Api(Google())
    with pytest.raises(D.Failure, match="schema: the operation failed: quota"):
        api.wait({"name": OPERATION, "done": True, "error": {"message": "quota"}}, "schema")
    with pytest.raises(D.Failure, match="without an operation to follow"):
        api.wait({"name": "projects/other/locations/elsewhere/operations/x"}, "schema")
    monkeypatch.setattr(D, "OPERATION_SECONDS", -1)
    with pytest.raises(D.Failure, match="still running"):
        api.wait({"name": OPERATION, "done": False}, "schema")


def test_storage_rules_are_published_only_when_they_differ(capsys):
    google = Google().converge()
    D.rules(release(google))
    assert google.events == [] and capsys.readouterr().out == "rules: the live ruleset equals storage.rules, skipped\n"
    google.rulesets["live"] += "// changed\n"
    D.rules(release(google))
    assert google.events == ["ruleset", "release"] and google.rulesets["new1"] == (ROOT / "storage.rules").read_text()
    assert google.release == f"projects/{D.PROJECT}/rulesets/new1"
    first = Google()
    D.rules(release(first))
    assert first.events == ["ruleset", "release"] and ("POST", f"projects/{D.PROJECT}/releases") in first.calls


def test_init_and_indexes_skip_when_everything_is_present(capsys):
    google = Google()
    run = release(google, Sql(google))
    D.init(run)
    D.indexes(run)
    assert run.sql.calls == ["probe", "indexes"] and google.events == []
    assert capsys.readouterr().out.splitlines() == ["init: all present, skipped", "indexes: all present, skipped"]


def test_init_runs_once_when_something_is_missing_and_requires_it_afterwards(capsys):
    google = Google()
    run = release(google, Sql(google, initialized=False))
    D.init(run)
    assert run.sql.calls == ["probe", "init", "probe"]
    assert capsys.readouterr().out.splitlines() == [
        "init: missing owner_role, uuid_ossp_in_public; running scripts/release/sql/initialize.sql",
        "init: created owner_role, uuid_ossp_in_public"]

    class Refusing(Sql):
        def __call__(self, mode, *arguments):
            if mode == "init":
                raise D.Failure("init: permission denied to grant role")
            return super().__call__(mode, *arguments)

    # What the probe found is in the log before anything is changed, so a failing init is not the only line.
    with pytest.raises(D.Failure, match="permission denied to grant role"):
        D.init(release(google, Refusing(google, initialized=False)))
    assert capsys.readouterr().out == ("init: missing owner_role, uuid_ossp_in_public; running "
                                       "scripts/release/sql/initialize.sql\n")

    class Stuck(Sql):
        def __call__(self, mode, *arguments):
            return super().__call__(mode, *arguments) if mode == "probe" else None

    with pytest.raises(D.Failure, match="still missing after scripts/release/sql/initialize.sql: owner_role, uuid_ossp_in_public"):
        D.init(release(google, Stuck(google, initialized=False)))


def test_an_invalid_index_fails_the_release_by_name_and_is_never_removed():
    google = Google()
    with pytest.raises(D.Failure, match="invalid index snapshot_search_batch; it is never removed automatically and "
                                        "needs the owner's decision"):
        D.indexes(release(google, Sql(google, invalid=["snapshot_search_batch"])))


# The first rows: read first, write once, read back.

def test_absent_rows_are_written_once_the_hierarchy_before_the_worker_and_read_back(capsys):
    payload = artifact()
    google = Google(payload)
    D.bootstrap(release(google, text=encoded(payload)))
    assert google.events == ["hierarchy", "worker"]
    service = D.SERVICE
    assert [call for call in google.calls if call[0] == "POST"] == [
        ("POST", f"{service}:executeGraphqlRead"), ("POST", f"{service}:executeGraphqlRead"),
        ("POST", f"{service}:executeGraphql"), ("POST", f"{service}:executeGraphqlRead"),
        ("POST", f"{service}:executeGraphql"), ("POST", f"{service}:executeGraphqlRead")]
    assert capsys.readouterr().out.splitlines() == [
        "bootstrap: wrote the organization, 18 collections and the owner's membership",
        "bootstrap: wrote the worker's operator membership"]
    again = len(google.calls)
    D.bootstrap(release(google, text=encoded(payload)))
    assert google.events == ["hierarchy", "worker"] and len(google.calls) == again + 3
    assert capsys.readouterr().out.splitlines() == ["bootstrap: hierarchy rows already match the artifact, skipped",
                                                    "bootstrap: worker membership already matches, skipped"]


def test_identical_rows_write_nothing_and_never_validate_the_artifact(monkeypatch):
    payload = artifact()
    google = Google(payload).seed()

    def refuse(*args, **kwargs):
        raise ValueError("the committed tree changed")

    # A later edit of the collection tree fails both validations; rows that already match never reach them.
    monkeypatch.setattr(D.reviewed.B, "validate_prepared", refuse)
    monkeypatch.setattr(PREPARED, "worker_membership_request", refuse)
    D.bootstrap(release(google, text=encoded(payload)))
    assert google.events == []
    absent = Google(payload)
    with pytest.raises(D.Failure, match="does not regenerate from this commit"):
        D.bootstrap(release(absent, text=encoded(payload)))
    assert absent.events == []


def test_without_the_artifact_an_existing_organization_skips_and_an_absent_one_fails(capsys):
    payload = artifact()
    google = Google(payload).seed()
    D.bootstrap(release(google))
    assert google.events == [] and google.calls == [("POST", f"{D.SERVICE}:executeGraphqlRead")]
    assert capsys.readouterr().out == ("bootstrap: an organization exists and DATA_BOOTSTRAP_ARTIFACT_B64 is not set, "
                                       "skipped without comparing\n")
    empty = Google(payload)
    with pytest.raises(D.Failure, match="no organization exists and DATA_BOOTSTRAP_ARTIFACT_B64 is not set; the owner "
                                        "runs scripts/ops/owner_setup.sh once"):
        D.bootstrap(release(empty))
    assert empty.events == []


def test_a_present_hierarchy_without_the_worker_writes_only_the_membership():
    payload = artifact()
    google = Google(payload).seed(worker=False)
    D.bootstrap(release(google, text=encoded(payload)))
    assert google.events == ["worker"]


def test_a_write_whose_readback_differs_stops_the_release_before_the_worker():
    payload = artifact()
    google = Google(payload)
    google.seed = lambda worker=True: google  # the write is acknowledged but leaves no rows
    with pytest.raises(D.Failure, match="the hierarchy was written but its readback differs; this needs the owner's "
                                        "decision"):
        D.bootstrap(release(google, text=encoded(payload)))
    assert google.events == ["hierarchy"]


def change(name):
    def apply(google):
        rows = google.rows
        if name == "renamed organization":
            rows["organization"]["name"] = "Another Museum"
        elif name == "extra collection":
            rows["collections"].append({"id": bare("c0ffee00-7f3a-4b1c-8d2e-0000000000ff"),
                                        "organizationId": bare(ORGANIZATION), "name": "Extra", "parentId": None})
        elif name == "missing collection":
            rows["collections"].pop()
        elif name in ("extra member", "extra member before the worker"):
            rows["organizationMembers"].append({"uid": "someone-else", "active": True})
        elif name == "renamed organization and extra member":
            rows["organization"]["name"] = "Another Museum"
            rows["members"].append({"uid": "someone-else", "collectionId": rows["collections"][0]["id"], "active": True,
                                    "role": "operator", "canViewSensitive": False})
        elif name == "administrator demoted":
            next(row for row in rows["members"] if row["uid"] == ADMIN["uid"])["role"] = "operator"
        elif name == "administrator removed":
            rows.update(organizationMembers=[row for row in rows["organizationMembers"] if row["uid"] != ADMIN["uid"]],
                        members=[row for row in rows["members"] if row["uid"] != ADMIN["uid"]])
        elif name == "worker is an admin":
            next(row for row in rows["members"] if row["uid"] == WORKER)["role"] = "admin"
        elif name == "worker without the hierarchy":
            rows.update(organization=None, collections=[],
                        organizationMembers=[row for row in rows["organizationMembers"] if row["uid"] == WORKER],
                        members=[row for row in rows["members"] if row["uid"] == WORKER])
        else:
            assert name == "only the organization"
            rows.update(collections=[], organizationMembers=[], members=[])
    return apply


# Each drift, the parts the warning names for it, and whether the worker's membership had been written before it.
DRIFT = [
    ("renamed organization", "organization", True),
    ("extra collection", "collections", True),
    ("missing collection", "collections", True),
    ("extra member", "other memberships", True),
    ("extra member before the worker", "other memberships", False),
    ("renamed organization and extra member", "organization, other memberships", True),
    ("administrator demoted", "administrator membership", True),
    ("administrator removed", "administrator membership", True),
    ("worker is an admin", "worker membership", True),
    ("worker without the hierarchy", "organization, collections, administrator membership", True),
    ("only the organization", "collections, administrator membership", True),
]


def warning(parts, unwritten=""):
    return (f"::warning title=Bootstrap rows differ::bootstrap: live rows differ from the artifact ({parts}); nothing was "
            f"written{unwritten} and the release continues. If the live rows are the intended ones, the owner can remove "
            "the DATA_BOOTSTRAP_ARTIFACT_B64 secret to end this check")


@pytest.mark.parametrize("name, parts, worker", DRIFT)
def test_rows_that_differ_are_left_alone_with_one_warning_and_the_step_succeeds(capsys, name, parts, worker):
    payload = artifact()
    google = Google(payload).seed(worker=worker)
    change(name)(google)
    before = copy.deepcopy(google.rows)
    D.bootstrap(release(google, text=encoded(payload)))
    assert google.events == [] and google.rows == before
    assert all(call in (("GET", D.WORKER_UID_URL.split("/v1/")[1]), ("POST", f"{D.SERVICE}:executeGraphqlRead"))
               for call in google.calls)
    absent = not any(row["uid"] == WORKER for row in before["organizationMembers"])
    unwritten = "; the worker's membership is absent and was not written" if absent else ""
    out = capsys.readouterr().out
    # One annotation line that names the parts in plain words and nothing else: no id, name, email or UID.
    assert out == warning(parts, unwritten) + "\n"
    assert not any(value in out for value in private(payload) | {"someone-else", "Another Museum"})


def test_membership_rows_under_an_organization_that_reads_as_absent_still_stop_before_any_write():
    payload = artifact()
    google = Google(payload).seed()
    usual = google.graphql
    empty = {"organization": None, "collections": [], "matchingCollections": [], "organizationMembers": [], "members": []}
    google.graphql = lambda verb, body: (200, {"data": empty}) if body["query"] == D.reviewed.READ_SCOPE else usual(verb, body)
    with pytest.raises(D.Failure, match="the organization reads as absent while the worker's membership rows exist; "
                                        "nothing was written and this needs the owner's decision"):
        D.bootstrap(release(google, text=encoded(payload)))
    assert google.events == []


@pytest.mark.parametrize("text", ["not base64 !", base64.b64encode(b"not json").decode(),
                                  base64.b64encode(json.dumps({"request": {"variables": {}}}).encode()).decode()])
def test_an_unreadable_artifact_fails_before_any_request(text):
    google = Google()
    with pytest.raises(D.Failure, match="DATA_BOOTSTRAP_ARTIFACT_B64 is not the base64 of a hierarchy artifact"):
        D.bootstrap(release(google, text=text))
    assert google.calls == []


def test_no_private_value_is_ever_printed_or_raised(capsys):
    payload = artifact()
    secrets, raised = private(payload), []

    def attempt(google, text=encoded(payload)):
        try:
            D.bootstrap(release(google, text=text))
        except D.Failure as failure:
            raised.append(str(failure))

    attempt(Google(payload))
    attempt(Google(payload).seed())
    different = Google(payload).seed()
    different.rows["organization"]["name"] = "Another Museum"
    attempt(different)
    forbidden = Google(payload)
    forbidden.secret_status = 403
    attempt(forbidden)
    refused = Google(payload)
    refused.graphql_error = f"duplicate key value violates unique constraint: Key (id)=({ORGANIZATION}) for {WORKER}"
    attempt(refused)
    broken = Google(payload)
    broken.graphql = lambda verb, body: (_ for _ in ()).throw(KeyError(WORKER))
    attempt(broken)
    rejected = Google(payload)
    rejected.graphql = lambda verb, body: (400, {"error": {"code": 400, "message": f"bad variable {ORGANIZATION} for {WORKER}"}})
    attempt(rejected)
    # A read that is tried again prints its retry line; that line holds no value either.
    flaky, answers = Google(payload).seed(), iter([(503, {"error": {"message": f"busy {WORKER}"}})])
    usual = flaky.graphql
    flaky.graphql = lambda verb, body: next(answers, None) or usual(verb, body)
    attempt(flaky)
    attempt(Google(payload), text="")
    # A real validation failure: the artifact names a collection the committed tree does not.
    tampered = copy.deepcopy(payload)
    tampered["hierarchy"]["collections"][0]["name"] = "Renamed"
    attempt(Google(payload), text=encoded(tampered))
    output = capsys.readouterr()
    # The rows that differ raise nothing: they print the one warning.
    assert warning("organization") in output.out.splitlines()
    assert f"POST {D.SERVICE}:executeGraphqlRead: HTTP 503 on attempt 1 of 3; trying again" in output.out.splitlines()
    assert len(raised) == 6 and "HTTP 403" in raised[0] and "scripts/ops/owner_setup.sh" in raised[0]
    assert raised[3] == f"POST {D.SERVICE}:executeGraphqlRead answered HTTP 400"
    assert raised[5].startswith("bootstrap: the artifact does not regenerate from this commit (")
    assert raised[1] == ("bootstrap: the hierarchy write was refused by Data Connect at organization_insert; the "
                         "messages are withheld because they can hold private values")
    assert raised[2] == "bootstrap: stopped on an unexpected KeyError; nothing more was written"
    for text in (output.out, output.err, *raised):
        assert not any(value in text for value in secrets)


# The whole run.

def test_the_steps_run_in_the_documented_order():
    assert [step.__name__ for step in D.STEPS] == STEP_NAMES
    assert [step.__doc__.split(".")[0] for step in D.STEPS] == list("abcdefgh")


def run_main(monkeypatch, google, sql, payload):
    monkeypatch.setattr(D, "session", lambda: google)
    monkeypatch.setattr(D, "node_sql", sql)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    monkeypatch.setenv(D.ARTIFACT, encoded(payload))
    code = D.main()
    assert D.ARTIFACT not in os.environ, "no child process may inherit the artifact"
    return code


def test_a_first_release_changes_everything_in_order_and_the_next_one_changes_nothing(monkeypatch, capsys):
    payload = artifact()
    google = Google(payload)
    google.diff = incompatible([entry(CREATE_TABLE), entry(CREATE_INDEX)])
    sql = Sql(google, initialized=False, indexed=False)
    assert run_main(monkeypatch, google, sql, payload) == 0
    assert google.events == ["init", "diff", "migrate", "schema", "indexes", "connector", "ruleset", "release",
                             "hierarchy", "worker"]
    assert sql.plans == [{"statements": [CREATE_TABLE, CREATE_INDEX]}]
    lines = capsys.readouterr().out.splitlines()
    assert [line.split(":")[0] for line in lines if not line.startswith("  [")] == [
        "init", "init", "diff", "apply", "schema", "indexes", "connector", "rules", "bootstrap", "bootstrap",
        "data release complete for " + "a" * 40]
    google.events.clear()
    sql.calls.clear()
    assert run_main(monkeypatch, google, sql, payload) == 0
    assert google.writes() == [] and sql.calls == ["probe", "indexes"]
    assert capsys.readouterr().out.splitlines() == [
        "init: all present, skipped", "diff: the database already fits the committed schema",
        "apply: no SQL change, skipped", "schema: live sources equal the committed ones, skipped",
        "indexes: all present, skipped", "connector: live sources equal the committed ones, skipped",
        "rules: the live ruleset equals storage.rules, skipped",
        "bootstrap: hierarchy rows already match the artifact, skipped",
        "bootstrap: worker membership already matches, skipped", "data release complete for " + "a" * 40]


def test_a_release_over_rows_that_differ_succeeds_with_the_warning_and_writes_nothing(monkeypatch, capsys):
    payload = artifact()
    google = Google(payload).converge().seed()
    google.rows["organizationMembers"].append({"uid": "another-member", "active": True})
    google.rows["collections"].append({"id": bare("c0ffee00-7f3a-4b1c-8d2e-0000000000ff"),
                                       "organizationId": bare(ORGANIZATION), "name": "Added Later", "parentId": None})
    sql = Sql(google)
    assert run_main(monkeypatch, google, sql, payload) == 0
    assert google.writes() == [] and sql.calls == ["probe", "indexes"]
    out = capsys.readouterr().out
    assert out.splitlines()[-2:] == [warning("collections, other memberships"), "data release complete for " + "a" * 40]
    assert not any(value in out for value in private(payload) | {"another-member", "Added Later"})


def test_a_release_whose_only_diff_is_the_own_index_drops_changes_nothing_and_succeeds(monkeypatch, capsys):
    payload = artifact()
    google = Google(payload).converge().seed()
    google.diff = incompatible([entry(sql, destructive=True) for sql in DROPS], destructive=True)
    sql = Sql(google)
    assert run_main(monkeypatch, google, sql, payload) == 0
    assert google.writes() == [] and sql.calls == ["probe", "indexes"] and sql.plans == []
    assert [line for line in capsys.readouterr().out.splitlines() if not line.startswith("  [")] == [
        "init: all present, skipped", "diff: 4 SQL statement(s) from Data Connect", SET_ASIDE.format(4),
        "apply: no SQL change, skipped", "schema: live sources equal the committed ones, skipped",
        "indexes: all present, skipped", "connector: live sources equal the committed ones, skipped",
        "rules: the live ruleset equals storage.rules, skipped",
        "bootstrap: hierarchy rows already match the artifact, skipped",
        "bootstrap: worker membership already matches, skipped", "data release complete for " + "a" * 40]


def test_a_failure_stops_the_run_with_one_line_and_a_non_zero_exit(monkeypatch, capsys):
    payload = artifact()
    google = Google(payload)
    google.diff = incompatible([entry('DROP TABLE "public"."specimen"')])
    sql = Sql(google)
    assert run_main(monkeypatch, google, sql, payload) == 1
    assert sql.calls == ["probe"] and google.writes() == []
    last = capsys.readouterr().out.splitlines()[-1]
    assert last == ("data release failed: diff: not additive, nothing was applied: statement 1 DROP removes or renames "
                    "something. A destructive schema change stops the release and needs the owner's decision")


def test_the_release_never_runs_outside_the_workflow(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(D, "session", lambda: pytest.fail("no credentials are loaded outside the workflow"))
    assert D.main() == 2 and "runs only in the Data release workflow" in capsys.readouterr().out


def test_a_failed_sql_step_is_a_failure_with_its_own_message_and_a_json_answer_is_returned(monkeypatch, capsys):
    def fake(code, out, err=""):
        def run(command, **kwargs):
            assert command[:2] == ["node", str(DATA_SQL)] and kwargs["timeout"] == D.SQL_SECONDS and kwargs["cwd"] == ROOT
            return subprocess.CompletedProcess(command, code, stdout=out, stderr=err)
        return run

    monkeypatch.setattr(D.subprocess, "run", fake(0, '{"created": [], "invalid": []}\n'))
    assert D.node_sql("indexes", "a.sql") == {"created": [], "invalid": []}
    monkeypatch.setattr(D.subprocess, "run", fake(0, ""))
    assert D.node_sql("init") is None
    monkeypatch.setattr(D.subprocess, "run", fake(1, "", "a warning\ndata_sql migrate: statement 2 of 3: relation exists; "
                                                         "rolled back, nothing was applied\n"))
    with pytest.raises(D.Failure) as failure:
        D.node_sql("migrate", "plan.json")
    assert str(failure.value) == "migrate: statement 2 of 3: relation exists; rolled back, nothing was applied"
    assert capsys.readouterr().out == "a warning\n"
    monkeypatch.setattr(D.subprocess, "run", fake(1, ""))
    with pytest.raises(D.Failure, match="probe: the SQL step failed without a message"):
        D.node_sql("probe")


# The SQL files.

def test_initialize_sql_is_one_transaction_that_only_adds():
    sql = INIT_SQL.read_text()
    code = re.sub(r"^\s*--.*$", "", sql, flags=re.M)
    assert sql.isascii() and code.split()[0] == "BEGIN;" and code.split()[-1] == "COMMIT;"
    assert len(re.findall(r"^BEGIN;$", code, re.M)) == 1 and len(re.findall(r"^COMMIT;$", code, re.M)) == 1
    assert not re.search(r"\b(DROP|TRUNCATE|RENAME)\b|\bDELETE\s+FROM\b", sql, re.I)
    assert "session_user <>" not in sql and "never adopt" not in sql
    # The comments claim only what holds: an error rolls back, a powerless GRANT or REVOKE only warns, and the
    # owner change does not depend on the CREATE grant around it.
    assert "exactly as it was" not in sql and "needs the new owner to hold CREATE" not in sql
    assert "is only a warning" in sql and "PostgreSQL does not need" in sql
    assert ("RAISE EXCEPTION 'the data-release SQL user lacks cloudsqlsuperuser; the owner runs "
            "scripts/ops/owner_setup.sh once';") in sql
    assert re.findall(r"CREATE EXTENSION[^;]*;", code) == ['CREATE EXTENSION IF NOT EXISTS "uuid-ossp" SCHEMA public;']
    blocks = {name: body for name, body in re.findall(r"^DO \$(\w+)\$\n(.*?)\n\$\1\$;$", code, re.M | re.S)}
    assert list(blocks) == ["executor", "roles", "owner"]
    # Every CREATE ROLE sits behind an existence check, and every ALTER SCHEMA behind an owner check.
    assert code.count("CREATE ROLE") == 1 and re.search(
        r"IF NOT EXISTS \(SELECT 1 FROM pg_catalog\.pg_roles WHERE rolname = wanted\) THEN\s+EXECUTE pg_catalog\.format\(\s+"
        r"'CREATE ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS', wanted\);\s+END IF;",
        blocks["roles"])
    assert code.count("ALTER SCHEMA") == 1 and re.search(
        r"IF \(SELECT pg_catalog\.pg_get_userbyid\(nspowner\) FROM pg_catalog\.pg_namespace WHERE nspname = 'public'\)\s+"
        r"<> 'firebaseowner_specimen-digitization-database_public' THEN.*ALTER SCHEMA public OWNER TO", blocks["owner"], re.S)
    for name in ("firebaseowner", "firebasewriter", "firebasereader"):
        assert f"'{name}_specimen-digitization-database_public'" in blocks["roles"]
    # Every grant of the original initialization is still made.
    original = re.sub(r"^\s*--.*$", "", (ROOT / "scripts/ci/initialize_database.sql").read_text(), flags=re.M)
    kept = [" ".join(statement.split()) for statement in original.split(";")
            if statement.split()[:1] in (["GRANT"], ["REVOKE"]) or statement.split()[:3] == ["ALTER", "DEFAULT", "PRIVILEGES"]]
    assert len(kept) == 12 and all(statement in " ".join(code.split()) for statement in kept)


def test_data_sql_is_plain_ascii_with_a_psql_ready_probe_and_no_removal():
    text = DATA_SQL.read_text()
    probe = re.search(r"^const PROBE = `(.*?)`;$", text, re.M | re.S).group(1)
    assert text.isascii() and "${" not in probe and not re.search(r"\b(DROP|TRUNCATE)\b", text, re.I)
    assert "/^CREATE INDEX CONCURRENTLY IF NOT EXISTS ([a-z_][a-z0-9_]*)\\s/" in text
    assert "IpAddressTypes.PUBLIC" in text and "AuthTypes.IAM" in text and "process.env.RELEASE_NODE_MODULES" in text
    for file in D.INDEX_FILES:
        statements = [part.strip() for part in re.sub(r"^\s*--.*$", "", (ROOT / file).read_text(), flags=re.M).split(";")]
        assert all(re.match(r"CREATE INDEX CONCURRENTLY IF NOT EXISTS [a-z_][a-z0-9_]*\s", part) for part in statements if part)


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_data_sql_parses_and_refuses_an_unknown_mode():
    assert subprocess.run(["node", "--check", str(DATA_SQL)], capture_output=True, text=True, timeout=60).returncode == 0
    unknown = subprocess.run(["node", str(DATA_SQL), "remove"], capture_output=True, text=True, timeout=60, env={
        key: value for key, value in os.environ.items() if key != "RELEASE_NODE_MODULES"})
    assert unknown.returncode == 2 and unknown.stderr.startswith("usage: node data_sql.mjs probe|init|migrate|indexes")
    unset = subprocess.run(["node", str(DATA_SQL), "probe"], capture_output=True, text=True, timeout=60, env={
        key: value for key, value in os.environ.items() if key != "RELEASE_NODE_MODULES"})
    assert unset.returncode == 1 and unset.stdout == "" and "RELEASE_NODE_MODULES is not set" in unset.stderr


def test_new_release_files_are_ascii():
    for path in (ROOT / ".github/workflows/data-release.yml", ROOT / "scripts/release/data_release.py", Path(__file__)):
        assert path.read_text().isascii(), path.name


SNAPSHOT = """
SELECT 'role', rolname, rolcanlogin, rolsuper, rolcreaterole, rolcreatedb FROM pg_roles WHERE rolname !~ '^pg_' ORDER BY 2;
SELECT 'member', r.rolname, u.rolname, g.rolname, m.admin_option, m.inherit_option, m.set_option FROM pg_auth_members m
  JOIN pg_roles r ON r.oid = m.roleid JOIN pg_roles u ON u.oid = m.member JOIN pg_roles g ON g.oid = m.grantor
  WHERE r.rolname !~ '^pg_' ORDER BY 2, 3, 4;
SELECT 'database', pg_get_userbyid(datdba), datacl FROM pg_database WHERE datname = current_database();
SELECT 'schema', pg_get_userbyid(nspowner), nspacl FROM pg_namespace WHERE nspname = 'public';
SELECT 'default', pg_get_userbyid(defaclrole), defaclobjtype, defaclacl FROM pg_default_acl ORDER BY 2, 3;
SELECT 'extension', extname, extnamespace::regnamespace FROM pg_extension ORDER BY 2;
"""


@pytest.mark.skipif(any(shutil.which(tool) is None for tool in ("initdb", "pg_ctl", "psql")) or os.geteuid() == 0,
                    reason="requires non-root disposable local PostgreSQL tools; never connects to production")
def test_initialize_sql_runs_twice_on_a_local_postgresql_and_the_probe_sees_everything(tmp_path):
    """A throwaway local server with stand-ins for Cloud SQL's managed role and the two IAM users. The role syntax
    (WITH INHERIT TRUE, SET TRUE; pg_has_role 'SET') needs PostgreSQL 16 or newer; production runs 18."""
    release_user, agent = "specimen-data-release@specimen-digitization.iam", "service-716045864126@gcp-sa-firebasedataconnect.iam"
    # macOS refuses to start the server without a valid locale in the environment.
    env = {**os.environ, "LC_ALL": "C"}

    def command(arguments, **kwargs):
        return subprocess.run(arguments, capture_output=True, text=True, timeout=60, env=env, **kwargs)

    assert command(["initdb", "-D", str(tmp_path / "cluster"), "-U", "cloudsqladmin", "-A", "trust", "--no-locale"]).returncode == 0
    with socket.socket() as bound:
        bound.bind(("127.0.0.1", 0))
        port = str(bound.getsockname()[1])
    started = command(["pg_ctl", "-D", str(tmp_path / "cluster"), "-l", str(tmp_path / "postgres.log"), "-o",
                       f"-p {port} -h 127.0.0.1 -c unix_socket_directories='' -c fsync=off", "-w", "start"])
    assert started.returncode == 0, started.stderr

    def sql(text, user="cloudsqladmin", database=D.DATABASE):
        return command(["psql", "-X", "-v", "ON_ERROR_STOP=1", "-h", "127.0.0.1", "-p", port, "-U", user, "-d", database,
                        "-qAt"], input=text)

    def probe():
        answer = sql(re.search(r"^const PROBE = `(.*?)`;$", DATA_SQL.read_text(), re.M | re.S).group(1), user=release_user)
        assert answer.returncode == 0, answer.stderr
        return json.loads(answer.stdout)

    try:
        ready = sql("SELECT current_setting('server_version_num')::int >= 160000 AND EXISTS ("
                    "SELECT 1 FROM pg_available_extensions WHERE name = 'uuid-ossp')", database="postgres")
        if ready.stdout.strip() != "t":
            pytest.skip("needs PostgreSQL 16 or newer with the uuid-ossp extension available")
        setup = sql(f'''CREATE ROLE cloudsqlsuperuser NOLOGIN NOSUPERUSER CREATEROLE CREATEDB;
            CREATE ROLE "{release_user}" LOGIN; CREATE ROLE "{agent}" LOGIN;
            CREATE DATABASE "{D.DATABASE}" OWNER cloudsqlsuperuser;''', database="postgres")
        assert setup.returncode == 0, setup.stderr
        assert not any(probe().values())
        # Before the owner assigns cloudsqlsuperuser: one clear line, and nothing changes.
        before = sql(SNAPSHOT).stdout
        refused = sql(INIT_SQL.read_text(), user=release_user)
        assert refused.returncode != 0 and ("ERROR:  the data-release SQL user lacks cloudsqlsuperuser; the owner runs "
                                            "scripts/ops/owner_setup.sh once") in refused.stderr
        assert sql(SNAPSHOT).stdout == before and not any(probe().values())
        assert sql(f'GRANT cloudsqlsuperuser TO "{release_user}" WITH INHERIT TRUE, SET TRUE').returncode == 0
        first = sql(INIT_SQL.read_text(), user=release_user)
        assert first.returncode == 0, first.stderr
        created = sql(SNAPSHOT).stdout
        assert all(probe().values()) and len(probe()) == 12
        second = sql(INIT_SQL.read_text(), user=release_user)
        assert second.returncode == 0, second.stderr
        assert sql(SNAPSHOT).stdout == created and all(probe().values())
        # The release user keeps working once cloudsqlsuperuser is taken back: it migrates as the owner role, and the
        # Data Connect agent can write the table it made.
        assert sql(f'REVOKE cloudsqlsuperuser FROM "{release_user}"').returncode == 0
        owner = "firebaseowner_specimen-digitization-database_public"
        table = sql(f'BEGIN; SET LOCAL search_path = public; SET LOCAL ROLE "{owner}"; CREATE TABLE "public"."organization" '
                    '("id" uuid NOT NULL DEFAULT uuid_generate_v4(), "name" text NOT NULL, PRIMARY KEY ("id")); COMMIT;',
                    user=release_user)
        assert table.returncode == 0, table.stderr
        row = sql("INSERT INTO public.organization (name) VALUES ('x') RETURNING name", user=agent)
        assert row.returncode == 0 and row.stdout.strip() == "x", row.stderr
        assert all(probe().values())
    finally:
        command(["pg_ctl", "-D", str(tmp_path / "cluster"), "-m", "immediate", "-w", "stop"])
