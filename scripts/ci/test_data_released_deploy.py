"""The data plane's envelope-free release (RELEASE.md 4.2): its phase comes from live state, read with GETs only.

Synthetic Google responses, gate records and merged trees; never network, credentials or cloud.
"""
import base64
import binascii
import copy
import hashlib
import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

import deploy_data as D
import release_gate as G
from release_diagnostics import HTTPFailure

SHA = "a" * 40
SCHEMA, CONNECTOR = f"{D.PREFIX}/schemas/main", f"{D.PREFIX}/connectors/specimen-server"
INSTANCE = f"projects/{D.PROJECT}/instances/{D.SOURCE}"
DATABASE = f"{INSTANCE}/databases/{D.DATABASE}"
RULESET = f"projects/{D.PROJECT}/rulesets/0f6e2a57-1c3b-4d8e-9a70-5b2c4d6e8f10"
UPDATED = "2026-09-23T08:00:00.123456789Z"
KEYS = {"version", "source_sha", "run_id", "run_attempt", "phase", "schema_etag", "schema_update_time",
        "connector_etag", "storage_ruleset", "source_sha_label", "backup_id", "tables", "views"}
FIRST = "the first apply's clone arrives with the next pull request"
# Private-looking values a live resource may carry; none may reach a receipt, a step output or the log.
CANARIES = ("canary-uid-7f3a", "canary-account@example.invalid", "canary-fingerprint", "canary-address")
MERGED_SCHEMA = "type Specimen @table {\n  id: UUID!\n  label: String\n}\n"
OPERATIONS = ("query ListSpecimens($organizationId: UUID!, $actorUid: String!) @auth(level: NO_ACCESS) {\n"
              "  organizationMember(key: {organizationId: $organizationId, uid: $actorUid})"
              ' @check(expr: "this != null") { uid }\n  specimens { id }\n}\n')
RULES = "rules_version = '2';\nservice firebase.storage {\n  match /b/{bucket}/o {\n    allow read, write: if false;\n  }\n}\n"
MERGED, OPS = {"schema.gql": MERGED_SCHEMA}, {"operations.gql": OPERATIONS}
# The first initialization's catalog summary (RELEASE.md 4.3 step 1), as the Node connector returns it.
ROLES = [f"firebase{role}_{D.DATABASE}_public" for role in ("owner", "reader", "writer")]
EMPTY = {"expected_database": True, "expected_actor": True, "relations": 0, "views": 0, "routines": 0, "types": 0,
         "extensions": [], "roles": []}
INITIALIZED = {**EMPTY, "routines": 10, "extensions": ["uuid-ossp"], "roles": ROLES}
EARLIER = f"data-initializer-{SHA}-1"
STOP = "the application database is neither empty nor initialized by this run; adopting it needs a ruling"
# The catalog release_sql.mjs reads read-only for the merged tree below (RELEASE.md 4.4, Verify).
MERGED_CATALOG = {"expected_database": True, "expected_actor": True, "tables": ["public.specimen"], "views": [],
                  "owners": [D.OWNER], "extensions": ["plpgsql", "uuid-ossp"], "postconditions": {"schema_owner": D.OWNER}}


def record(plane="data", **changes):
    return {"version": G.RECORD_VERSION, "plane": plane, "repository": "anurag-duddu/specimen-digitization-app",
            "project": D.PROJECT, "source_sha": SHA, "source_tree_sha": "d" * 40, "pull_request": 15, "ci_run_id": 123,
            "ci_run_attempt": 1, "release_run_id": 456, "release_run_attempt": 2, "issued_at_unix": 1790164800,
            "expires_at_unix": 1790168400, "identity": G.identity(plane) if plane in G.GATE_PLANES else {}, **changes}


def source(files):
    return {"files": [{"path": path, "content": content} for path, content in files.items()]}


def state(schema=None, connector=None, rules=RULES):
    """Live resources by (api, resource). No schema files is the placeholder; None leaves the rest absent."""
    datasource = {"database": D.DATABASE, "cloudSql": {"instance": f"projects/{D.PROJECT}/locations/us-east4/instances/{D.SOURCE}"}}
    live = {("data", SCHEMA): {"name": SCHEMA, "uid": CANARIES[0], "etag": "schema-etag", "updateTime": UPDATED,
                               "reconciling": False, "source": source(schema) if schema else {},
                               "datasources": [{"postgresql": {**datasource, "schemaMigration": "MIGRATE_COMPATIBLE"}
                                                if schema else {**datasource, "schemaValidation": "STRICT", "ephemeral": True}}]},
            ("sql", INSTANCE): {"name": D.SOURCE, "project": D.PROJECT, "region": "us-east4", "state": "RUNNABLE",
                                "serviceAccountEmailAddress": CANARIES[1], "ipAddresses": [{"ipAddress": CANARIES[3]}]},
            ("sql", DATABASE): {"name": D.DATABASE, "instance": D.SOURCE, "project": D.PROJECT}}
    if connector is not None:
        live["data", CONNECTOR] = {"name": CONNECTOR, "uid": CANARIES[0], "etag": "connector-etag", "reconciling": False,
                                   "source": source(connector)}
    if rules is not None:
        live["rules", D.RULE_RELEASE] = {"name": D.RULE_RELEASE, "rulesetName": RULESET}
        live["rules", RULESET] = {"name": RULESET, "source": {"files": [
            {"name": "storage.rules", "content": rules, "fingerprint": CANARIES[2]}]}}
    return live


class FakeGoogle:
    def __init__(self, live, packet):
        self.live, self.packet, self.calls, self.error = live, packet, [], None

    def request(self, api, method, resource, *, body=None, params=None, missing=False):
        self.calls.append((api, method, resource))
        if method != "GET":
            pytest.fail("choosing the data phase never changes live state")
        if (api, resource) not in self.live:
            if missing:
                return None
            raise HTTPFailure(404)
        return copy.deepcopy(self.live[api, resource])


def tree(tmp_path, monkeypatch):
    """The merged tree as the repository root, and the receipt and step output paths; no bootstrap artifact."""
    root, output, steps = tmp_path / "merged", tmp_path / "data-released.json", tmp_path / "github-output"
    for relative, text in (("dataconnect/schema/schema.gql", MERGED_SCHEMA), ("storage.rules", RULES),
                           ("dataconnect/connector/operations.gql", OPERATIONS),
                           ("dataconnect/connector/connector.yaml", "connectorId: specimen-server\n")):
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_text(text)
    steps.touch()
    monkeypatch.setattr(D, "ROOT", root)
    monkeypatch.setenv("GITHUB_OUTPUT", str(steps))
    monkeypatch.delenv("DATA_BOOTSTRAP_ARTIFACT_B64", raising=False)
    return output, steps


@pytest.fixture
def release(tmp_path, monkeypatch, capsys):
    """Run the release against live resources; every exit keeps the receipt, the step output and the log public."""
    output, steps = tree(tmp_path, monkeypatch)

    def run(live, packet=None, summary=EMPTY, listing=()):
        from test_data_first_initialization import inventory  # that module imports this one
        google = FakeGoogle(live, record() if packet is None else packet)
        monkeypatch.setattr(D, "Google", lambda path, plane: google if plane == "data" else pytest.fail("data only"))
        # Verify's reads (RELEASE.md 4.4): the catalog and the supplemental index inventory, for the admitted commit.
        reads = {"migrated": MERGED_CATALOG, "indexed": inventory()}
        monkeypatch.setattr(D, "gate_sql", lambda mode, directory, sha, *inputs, **kwargs: copy.deepcopy(reads[mode])
                            if sha == SHA and not inputs else pytest.fail("verify reads only"))
        if summary is not None:
            monkeypatch.setattr(D, "first_catalog", lambda directory, sha: copy.deepcopy(summary) if (directory, sha)
                                == (tmp_path / "release", SHA) else pytest.fail("the admitted commit reads it"), raising=False)
        artifacts = [{"name": name, "expired": False, "workflow_run": {"id": 456}} for name in listing]
        monkeypatch.setattr(D, "gh_json", lambda path: listing if isinstance(listing, dict) else {
            "total_count": len(artifacts), "artifacts": artifacts} if path == f"repos/{D.REPOSITORY}/actions/runs/456/"
            "artifacts?per_page=100" else pytest.fail("only this run's artifacts are listed"), raising=False)
        try:
            D.deploy_released_data(tmp_path / "release" / "packet.json", output)
        except ValueError as error:
            google.error = str(error)
        receipt = json.loads(output.read_text()) if output.exists() else None
        google.log = capsys.readouterr().out
        assert receipt is None or set(receipt) == KEYS
        assert not any(value in text for value in CANARIES for text in (output.read_text() if receipt else "",
                                                                         steps.read_text(), google.log))
        return google, receipt, steps.read_text()
    return run


def receipt(phase, connector="connector-etag", ruleset=RULESET, **facts):
    return {"version": "data-released/v1", "source_sha": SHA, "run_id": 456, "run_attempt": 2, "phase": phase,
            "schema_etag": "schema-etag", "schema_update_time": UPDATED, "connector_etag": connector,
            "storage_ruleset": ruleset, **dict.fromkeys(("source_sha_label", "backup_id", "tables", "views")), **facts}


def gets(*resources):
    return [(api, "GET", resource) for api, resource in resources]


def test_the_placeholder_without_a_connector_initializes_and_changes_nothing(release):
    google, value, outputs = release(state(rules=None))
    assert google.error is None and outputs == "phase=initialize\ninit_step=initialize\n"
    assert value == receipt("initialize", connector=None, ruleset=None)
    assert google.calls == gets(("data", SCHEMA), ("data", CONNECTOR), ("rules", D.RULE_RELEASE), ("sql", INSTANCE),
                                ("sql", DATABASE))


@pytest.mark.parametrize("summary,listing,step", [
    (EMPTY, (), "initialize"), (INITIALIZED, (EARLIER,), "migrate"),
    ({**EMPTY, "roles": ROLES}, (EARLIER, f"data-initializer-{SHA}-2"), "migrate"),
], ids=["empty", "initialized-earlier", "roles-and-earlier-receipt"])
def test_step_one_initializes_an_empty_database_or_migrates_after_this_runs_earlier_initializer(release, summary, listing, step):
    google, value, outputs = release(state(rules=None), summary=summary, listing=listing)
    assert google.error is None and outputs == f"phase=initialize\ninit_step={step}\n"
    assert value == receipt("initialize", connector=None, ruleset=None)
    assert f"First initialization step: {step}." in google.log


@pytest.mark.parametrize("summary,listing", [
    ({**EMPTY, "relations": 1}, ()), ({**EMPTY, "views": 1}, ()), ({**EMPTY, "routines": 1}, ()), ({**EMPTY, "types": 1}, ()),
    ({**EMPTY, "extensions": ["uuid-ossp"]}, ()), ({**EMPTY, "roles": ROLES[:1]}, (EARLIER,)), (INITIALIZED, ()),
    (INITIALIZED, (f"data-initializer-{SHA}-2",)), (INITIALIZED, (f"data-initializer-{'b' * 40}-1",)),
    (INITIALIZED, (f"initializer-intent-{SHA}-1",)),
], ids=["relation", "view", "routine", "type", "extension", "one-role", "roles-without-receipt", "only-this-attempt",
        "another-commit", "intent-is-no-receipt"])
def test_step_one_stops_on_anything_else_and_prints_only_the_value_free_summary(release, summary, listing):
    google, value, outputs = release(state(rules=None), summary=summary, listing=listing)
    assert google.error == STOP and outputs == "phase=initialize\n"
    assert value == receipt("initialize", connector=None, ruleset=None) and "First initialization step" not in google.log
    assert len([line for line in google.log.splitlines() if line.startswith("Application database: ")]) == 1


def test_the_stopped_summary_is_one_fixed_line(release):
    log = release(state(rules=None), summary={**INITIALIZED, "roles": ROLES[1:]})[0].log
    assert ("Application database: 0 relations, 0 views, 10 routines, 0 types, 1 extension(s) besides plpgsql "
            "(uuid-ossp); Data Connect roles: owner absent, writer present, reader present.\n") in log


@pytest.mark.parametrize("change", [
    lambda s: s.update(owner=CANARIES[1]), lambda s: s.pop("types"), lambda s: s.update(relations=-1),
    lambda s: s.update(views=True), lambda s: s.update(expected_actor=False), lambda s: s.update(expected_database=None),
    lambda s: s.update(extensions=["uuid-ossp\n::error::" + CANARIES[0]]), lambda s: s.update(extensions=["plpgsql"]),
    lambda s: s.update(extensions=["uuid-ossp", "uuid-ossp"]), lambda s: s.update(roles=[CANARIES[1]]),
    lambda s: s.update(roles=ROLES[:1] * 2), lambda s: s.update(roles=[{"name": CANARIES[3]}]),
])
def test_a_malformed_summary_stops_without_printing_any_of_it(release, change):
    summary = copy.deepcopy(EMPTY)
    change(summary)
    google, value, outputs = release(state(rules=None), summary=summary)
    assert google.error == "the application database's catalog summary is malformed" and outputs == "phase=initialize\n"
    assert "Application database" not in google.log


def test_an_unreadable_catalog_or_artifact_listing_stops_with_a_fixed_reason(release, monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(D.subprocess, "run", lambda command, **kwargs: calls.append((command, kwargs["env"]["RELEASE_GATE_SHA"]))
                        or subprocess.CompletedProcess(command, 1, b"", CANARIES[0].encode()))
    google, value, outputs = release(state(rules=None), summary=None)
    assert google.error == "the application database's catalog could not be read" and outputs == "phase=initialize\n"
    assert calls == [(["node", "scripts/ci/release_sql.mjs", "summary", D.SOURCE,
                       str(tmp_path / "release" / "first-catalog.json")], SHA)]
    google = release(state(rules=None), summary=INITIALIZED, listing={"total_count": 101, "artifacts": []})[0]
    assert google.error == "incomplete run artifact listing"


def test_live_sources_equal_to_the_merged_ones_verify_and_change_nothing(release):
    google, value, outputs = release(state(MERGED, OPS))
    assert google.error is None and outputs == "phase=verify\n" and value == receipt("verify", tables=1, views=0)
    assert google.calls == gets(("data", SCHEMA), ("data", CONNECTOR), ("rules", D.RULE_RELEASE), ("rules", RULESET),
                                ("sql", INSTANCE), ("sql", DATABASE))


@pytest.mark.parametrize("change,message", [
    (lambda live: live["data", SCHEMA]["datasources"][0]["postgresql"].update(ephemeral=True), "persistent"),
    (lambda live: live["data", SCHEMA]["datasources"][0]["postgresql"].update(database="other"), "persistent"),
    (lambda live: live["data", SCHEMA]["datasources"][0]["postgresql"].pop("schemaMigration"), "persistent"),
    (lambda live: live["data", CONNECTOR].update(reconciling=True), "reconcil"),
])
def test_verify_requires_a_persistent_schema_and_a_reconciled_connector(release, change, message):
    live = state(MERGED, OPS)
    change(live)
    google, value, outputs = release(live)
    assert message in google.error and outputs == "" and value == receipt("verify")


@pytest.mark.parametrize("live", [
    state({"schema.gql": "type Specimen @table {\n  id: UUID!\n}\n"}, OPS),
    state(MERGED, OPS, rules="rules_version = '2';\n"), state(MERGED, OPS, rules=None),
], ids=["new-nullable-field", "changed-rules", "no-rules-release"])
def test_an_additive_change_to_an_unlabelled_schema_is_the_first_apply_which_stops_before_any_effect(release, live):
    """RELEASE.md 4.4: a schema without the source-sha label is the first apply after T3c; its clone arrives with T3d's
    second pull request. The fake refuses every request but a GET."""
    google, value, outputs = release(live)
    assert google.error == FIRST and outputs == "phase=apply\n"
    assert value == receipt("apply", ruleset=RULESET if ("rules", RULESET) in live else None)


def test_a_non_additive_change_is_refused_by_count_with_value_free_lines(release):
    live = state({"schema.gql": "type Specimen @table {\n  id: UUID!\n  label: String!\n  note: String\n}\n"}, OPS)
    google, value, outputs = release(live)
    assert google.error == "the additive-only gate refused 2 change(s)"
    assert outputs == "phase=apply\n" and value == receipt("apply")
    assert "Specimen.note: field removed or renamed" in google.log
    assert "Specimen.label: NOT NULL dropped outside the named relaxations" in google.log


def test_a_changed_operation_is_refused_too(release):
    google, value, outputs = release(state(MERGED, {"operations.gql": OPERATIONS.replace("{ id }", "{ id label }")}))
    assert google.error == "the additive-only gate refused 1 change(s)" and "ListSpecimens: operation changed" in google.log


@pytest.mark.parametrize("live,connector", [
    (state(MERGED), None), (state(None, OPS), "connector-etag"), (state({}, {}), "connector-etag"),
    ({**state(MERGED, OPS), ("data", SCHEMA): {**state(MERGED)["data", SCHEMA], "reconciling": True}}, "connector-etag"),
    ({**state(), ("data", SCHEMA): {**state()["data", SCHEMA], "reconciling": True}}, None),
], ids=["schema-without-connector", "connector-without-schema", "connector-without-files", "schema-reconciling",
        "placeholder-reconciling"])
def test_any_other_combination_asks_to_reconcile(release, live, connector):
    google, value, outputs = release(live)
    assert "reconcile" in google.error and outputs == ""
    assert value == receipt(None, connector=connector)
    assert all(method == "GET" for _, method, _ in google.calls)


@pytest.mark.parametrize("change", [
    lambda live: live["sql", INSTANCE].update(state="SUSPENDED"), lambda live: live["sql", INSTANCE].update(state=None),
    lambda live: live["sql", INSTANCE].update(name="other"), lambda live: live.pop(("sql", DATABASE)),
    lambda live: live["sql", DATABASE].update(name="other"), lambda live: live.pop(("sql", INSTANCE)),
], ids=["suspended", "no-state", "other-instance", "no-database", "other-database", "no-instance"])
def test_the_sql_instance_must_run_and_the_application_database_exist(release, change):
    live = state(MERGED, OPS)
    change(live)
    google, value, outputs = release(live)
    assert google.error and outputs == "" and value == receipt(None)


@pytest.mark.parametrize("change", [
    lambda live: live.pop(("data", SCHEMA)), lambda live: live["data", SCHEMA].update(etag=None),
    lambda live: live["data", SCHEMA].update(updateTime="yesterday"), lambda live: live["data", CONNECTOR].pop("etag"),
    lambda live: live["rules", D.RULE_RELEASE].update(rulesetName="projects/other/rulesets/x"),
    lambda live: live["rules", D.RULE_RELEASE].update(rulesetName=f"projects/{D.PROJECT}/rulesets/../releases"),
    lambda live: live["rules", RULESET]["source"]["files"].append({"name": "storage.rules", "content": ""}),
    lambda live: live["data", SCHEMA]["source"]["files"].append({"path": "schema.gql", "content": ""}),
], ids=["no-schema", "no-schema-etag", "bad-update-time", "no-connector-etag", "foreign-ruleset", "ruleset-path",
        "duplicate-rules-file", "duplicate-schema-file"])
def test_missing_or_malformed_live_facts_fail_closed_before_a_phase(release, change):
    live = state(MERGED, OPS)
    change(live)
    google, value, outputs = release(live)
    assert google.error and outputs == "" and (value is None or value["phase"] is None)
    assert all(method == "GET" for _, method, _ in google.calls)


@pytest.mark.parametrize("packet", [
    {"version": "protected-release/v1", "plane": "data", "source_sha": SHA},
    record("data-initialization"), record("runtime"), record(plane="data", version="protected-release-gate/v2"),
])
def test_only_a_data_gate_record_releases_and_nothing_is_read_or_written_otherwise(release, packet):
    google, value, outputs = release(state(), packet)
    assert google.error and google.calls == [] and value is None and outputs == ""


def test_a_present_bootstrap_artifact_is_announced_never_decoded_printed_or_written(release, monkeypatch):
    artifact = "not base64 at all: canary-bootstrap-row"
    monkeypatch.setenv("DATA_BOOTSTRAP_ARTIFACT_B64", artifact)
    for module, name in ((base64, "b64decode"), (base64, "standard_b64decode"), (base64, "urlsafe_b64decode"),
                         (base64, "decodebytes"), (binascii, "a2b_base64")):
        monkeypatch.setattr(module, name, lambda *args, **kwargs: pytest.fail("the bootstrap arrives with T3e"))
    google, value, outputs = release(state(rules=None))
    assert google.error is None and outputs == "phase=initialize\ninit_step=initialize\n" and "T3e" in google.log
    assert artifact not in google.log + json.dumps(value) + outputs and "canary" not in google.log
    monkeypatch.setenv("DATA_BOOTSTRAP_ARTIFACT_B64", "")
    assert "T3e" not in release(state(rules=None))[0].log


def test_the_committed_sources_are_exactly_what_the_envelope_path_sends():
    schema, connector = D.data_bodies({"schema_mode": "validate_existing", "schema_etag": None, "connector_etag": None})
    assert schema["source"] == D.committed_source("dataconnect/schema") and schema["source"]["files"]
    assert connector["source"] == D.committed_source("dataconnect/connector") and connector["source"]["files"]
    assert D.committed_rules() == {"files": [{"name": "storage.rules", "content": (D.ROOT / "storage.rules").read_text()}]}


@pytest.fixture
def command_line(tmp_path, monkeypatch):
    """main() with a gate record admitted for the requested plane; the envelope's plan and deploy must stay unused."""
    calls, output, steps = [], tmp_path / "data-released.json", tmp_path / "github-output"
    steps.touch()
    monkeypatch.setenv("GITHUB_OUTPUT", str(steps))
    monkeypatch.setattr(D, "admit", lambda path, plane: record(plane))
    monkeypatch.setattr(D, "materialize_inputs", lambda *args: None)
    monkeypatch.setattr(D, "read_bound_plan", lambda *args: pytest.fail("a gate record has no plan"))
    monkeypatch.setattr(D, "deploy", lambda *args: pytest.fail("a gate record never takes the envelope path"))
    monkeypatch.setattr(D, "deploy_released_data", lambda *args: calls.append(args) or output.write_text("{}\n"))

    def run(*arguments):
        monkeypatch.setattr(sys, "argv", ["deploy_data.py", "--packet", str(tmp_path / "packet.json"), *arguments,
                                          "--output", str(output)])
        D.main()
        return calls, steps.read_text()
    run.calls = calls
    return run


def test_the_command_line_releases_a_gate_record_through_deploy_without_a_plan(tmp_path, command_line):
    calls, outputs = command_line("--deploy")
    assert calls == [(tmp_path / "packet.json", tmp_path / "data-released.json")]
    assert outputs == "receipt_sha256=" + hashlib.sha256(b"{}\n").hexdigest() + "\n"


@pytest.mark.parametrize("arguments,plane,step", [
    (["--prepare-initializer-intents"], "data-initialization", "prepare_owned_initializer"),
    (["--initialize"], "data-initialization", "initialize_existing"), (["--dispose-initializer"], "data", "dispose_owned_initializer"),
    (["--migrate"], "data", "migrate_initialized"),
])
def test_each_initialization_job_runs_its_own_step_from_its_own_gate_plane(tmp_path, command_line, monkeypatch, arguments, plane, step):
    import release_initialize
    steps = []
    monkeypatch.setattr(D, "Google", lambda path, used: SimpleNamespace(plane=used, packet=record(used)))
    for module in (release_initialize, D):
        monkeypatch.setattr(module, step, lambda google, directory, *output: steps.append((google.plane, directory))
                            or output and output[0].write_text("{}\n"), raising=False)
    command_line(*arguments)
    assert steps == [(plane, tmp_path)] and command_line.calls == []


@pytest.mark.parametrize("arguments", [["--admit"], ["--prepare-inputs"], ["--prepare-clone-intent"],
                                       ["--complete-initialization", "--receipt", "receipt.json"],
                                       ["--initialize", "--receipt", "receipt.json"], ["--migrate", "--receipt", "receipt.json"]])
def test_the_command_line_refuses_a_gate_record_for_any_other_action(command_line, arguments):
    with pytest.raises(SystemExit, match=r"^Data release blocked \[stage=data\.admission\]\.$"):
        command_line(*arguments)
    assert command_line.calls == []


def test_the_command_line_migrates_only_a_gate_record(command_line, monkeypatch):
    monkeypatch.setattr(D, "admit", lambda path, plane: {"version": "protected-release/v1", "plane": plane, "source_sha": SHA})
    with pytest.raises(SystemExit, match=r"^Data release blocked \[stage=data\.admission\]\.$"):
        command_line("--migrate")
