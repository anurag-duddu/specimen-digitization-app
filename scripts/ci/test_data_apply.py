"""The data plane's apply while the runtime runs, and verify's SQL checks (RELEASE.md 4.4, T3d).

Over test_data_released_deploy's merged tree, with synthetic Google, GitHub and Node replies; never network, credentials
or cloud.
"""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace

import pytest

import deploy_data as D
import release_google
import release_initialize as I
from release_diagnostics import HTTPFailure
from test_data_first_initialization import RELEASE_PG, error, inventory, node, release_sql
from test_data_released_deploy import (CANARIES, FIRST, INSTANCE, KEYS, MERGED, MERGED_CATALOG, MERGED_SCHEMA, OPS, RULES,
                                       RULESET, SCHEMA, SHA, UPDATED, record, state, tree)

NOW, OLD, WEEK = 1790165000, "b" * 40, 7 * 86400  # inside record()'s window; the commit the plane last applied


def utc(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")


LIVE = {"schema.gql": MERGED_SCHEMA.replace("  label: String\n", "")}  # the merged tree adds a nullable field
ADD = 'ALTER TABLE "public"."specimen" ADD COLUMN "label" text NULL'
BACKUP_ID, BACKUP = "1790165000123", f"projects/{D.PROJECT}/backups/7d1c8e2a"
RUN, NEW = f"{INSTANCE}/backupRuns/{BACKUP_ID}", f"projects/{D.PROJECT}/rulesets/merged-rules"
ACTOR = f"specimen-data-release@{D.PROJECT}.iam.gserviceaccount.com"
ORDER = ["backup", "diff", "migrate", "schema", "indexes", "connector-check", "connector", "ruleset", "release", "migrated"]
NEWER = "the live schema came from a newer commit; this release would roll it back"
LABELS, PITR = "the live schema's labels are malformed", "point-in-time recovery is off on the SQL instance"
UNFINISHED = "this attempt's backup did not reach SUCCESSFUL"
NUMBER = record()["identity"]["project_number"]  # the project's numeric alias
APPLIED = {"schema_etag": "schema-etag-2", "connector_etag": "connector-etag-2", "storage_ruleset": NEW,
           "source_sha_label": SHA, "backup_id": BACKUP_ID, "tables": 1, "views": 0}


class Cloud:
    """The live data plane behind the release job's gate record: by default an additive change over the commit it last
    applied, OLD. Each effect and each Node run is one ordered event; `fail` names the one that fails."""

    def __init__(self, schema=LIVE, label=OLD, rules="rules_version = '2';\n"):
        self.plane, self.packet, self.events, self.fail, self.status = "data", record(), [], None, "ahead"
        self.live = state(schema, OPS, rules=rules)
        self.live["data", SCHEMA]["labels"] = {"team": "specimen", **({"source-sha": label} if label else {})}
        self.live["sql", INSTANCE]["settings"] = {"dataDiskSizeGb": "10", "backupConfiguration": {
            "enabled": True, "pointInTimeRecoveryEnabled": True}}
        self.diff, self.backup, self.compared, self.patches = [ADD] if schema == LIVE else [], {}, [], []
        self.catalog, self.indexes = copy.deepcopy(MERGED_CATALOG), inventory()

    def effect(self, name):
        self.events.append(name)
        if name == self.fail:
            raise HTTPFailure(503)

    def request(self, api, method, resource, *, body=None, params=None, missing=False, diff=False):
        if method == "GET":
            if (api, resource) not in self.live:
                return None if missing else pytest.fail("unexpected read")
            return copy.deepcopy(self.live[api, resource])
        if api == "sql":
            assert (method, resource, getattr(self, "_gate_effect", None)) == ("POST", f"projects/{D.PROJECT}/backups", "backup")
            self.effect("backup")
            self.sent, shared = body, {"type": "ON_DEMAND", "instance": D.SOURCE, "description": body["description"],
                                       "location": "us-east4", "maxChargeableBytes": "1048576", **self.backup}
            self.live["sql", BACKUP] = {"name": BACKUP, "kind": "sql#backup", "state": "SUCCESSFUL", "backupRun": RUN,
                                        "expiryTime": body["expiryTime"], **shared}
            self.live["sql", RUN] = {"id": BACKUP_ID, "kind": "sql#backupRun", "status": "SUCCESSFUL", **shared}
            return {"kind": "sql#operation", "name": "backup-operation", "status": "DONE", "operationType": "BACKUP_VOLUME",
                    "targetId": D.SOURCE, "targetProject": D.PROJECT, "user": ACTOR,
                    "backupContext": {"backupId": BACKUP_ID, "name": BACKUP}}
        if api == "data":
            role, check = ("schema" if resource == SCHEMA else "connector"), params.get("validateOnly") == "true"
            name = ("diff" if role == "schema" else "connector-check") if check else role
            self.effect(name)
            self.patches.append((name, copy.deepcopy(body)))
            if name == "diff" and self.diff:
                failure = HTTPFailure(400)
                failure.body = error([{"sql": sql} for sql in self.diff]) if diff else None
                raise failure
            if not check:
                self.live["data", resource] = {**body, "etag": f"{role}-etag-2", "updateTime": UPDATED, "reconciling": False}
            return {"name": f"projects/{D.PROJECT}/locations/us-east4/operations/{len(self.events)}"}
        self.effect("ruleset" if resource.endswith("/rulesets") else "release")
        if resource.endswith("/rulesets"):
            self.live["rules", NEW] = {"name": NEW, "source": body["source"]}
            return {"name": NEW}
        self.live["rules", D.RULE_RELEASE] = {"name": D.RULE_RELEASE, "rulesetName": NEW}
        return {}

    def wait(self, api, operation, **kwargs):
        return {}


def node_sql(cloud):
    """release_sql.mjs as the release identity for the admitted commit on the source: each mode one event; `fail` exits 1."""
    def run(command, **kwargs):
        assert command[:2] == ["node", "scripts/ci/release_sql.mjs"] and command[3] == D.SOURCE
        assert kwargs["env"]["RELEASE_GATE_SHA"] == SHA and 0 < kwargs["timeout"] <= 300
        cloud.events.append(command[2])
        if command[2] == cloud.fail:
            return subprocess.CompletedProcess(command, 1, b"", b"")
        if command[2] == "migrate":
            cloud.diff = []  # committed: Data Connect's next diff finds nothing
        cloud.indexes = inventory() if command[2] == "indexes" else cloud.indexes
        answer = {"migrated": cloud.catalog, "indexed": cloud.indexes, "indexes": inventory(),
                  "migrate": {"version": "data-migration/v1", "statements": 1, "committed": True}}[command[2]]
        Path(command[4]).write_text(json.dumps(answer))
        Path(command[4]).chmod(0o600)
        return subprocess.CompletedProcess(command, 0, b"", b"")
    return run


@pytest.fixture
def released(tmp_path, monkeypatch, capsys):
    """deploy_released_data at a fixed instant; every exit keeps the receipt, the step output and the log public."""
    output, steps = tree(tmp_path, monkeypatch)
    monkeypatch.setattr(time, "time", lambda: NOW)
    monkeypatch.setattr(time, "sleep", lambda seconds: pytest.fail("every operation here completes at once"))

    def run(cloud, directory="release"):
        monkeypatch.setattr(D, "Google", lambda path, plane: cloud)
        monkeypatch.setattr(D, "gh_json", lambda path: cloud.compared.append(path) or {"status": cloud.status})
        monkeypatch.setattr(D.subprocess, "run", node_sql(cloud))
        (tmp_path / directory).mkdir(exist_ok=True)
        steps.write_text("")
        try:
            D.deploy_released_data(tmp_path / directory / "packet.json", output)
            cloud.error = None
        except ValueError as failure:
            cloud.error = str(failure)
        cloud.log = capsys.readouterr().out
        value = json.loads(output.read_text())
        assert set(value) == KEYS and not any(canary in text for canary in CANARIES
                                              for text in (output.read_text(), steps.read_text(), cloud.log))
        return value, steps.read_text()
    return run


def receipt(phase="apply", **facts):
    """Public facts only, each as last observed: stopped before any effect unless facts say otherwise."""
    return {"version": "data-released/v1", "source_sha": SHA, "run_id": 456, "run_attempt": 2, "phase": phase,
            "schema_etag": "schema-etag", "schema_update_time": UPDATED, "connector_etag": "connector-etag",
            "storage_ruleset": RULESET, "source_sha_label": OLD, "backup_id": None, "tables": None, "views": None, **facts}


def test_an_additive_apply_backs_up_then_migrates_and_releases_the_merged_files_labelled_with_the_merged_commit(released):
    cloud = Cloud()
    value, outputs = released(cloud)
    assert cloud.error is None and outputs == "phase=apply\n" and cloud.events == ORDER and value == receipt(**APPLIED)
    assert cloud.compared == [f"repos/{D.REPOSITORY}/compare/{OLD}...{SHA}"] and "Migration: 1 ALTER TABLE." in cloud.log
    # This attempt's one backup, named by the commit, run and attempt; it expires 7 days after it is sent.
    assert cloud.sent == {"instance": D.SOURCE, "location": "us-east4", "expiryTime": utc(NOW + WEEK),
                          "description": f"specimen-data-release-{SHA}-456-2"}
    # Validate-only, then the apply: COMPATIBLE on the etag read at the start, the merged commit as its source-sha label.
    schema = [body for name, body in cloud.patches if name in ("diff", "schema")]
    assert len(schema) == 2 and all(body["etag"] == "schema-etag" and body["labels"] == {"team": "specimen", "source-sha": SHA}
                                    and body["datasources"][0]["postgresql"]["schemaValidation"] == "COMPATIBLE"
                                    and body["source"] == D.committed_source("dataconnect/schema") for body in schema)
    assert [body["etag"] for name, body in cloud.patches if name.startswith("connector")] == ["connector-etag"] * 2


@pytest.mark.parametrize("change,message,label", [
    (lambda cloud: setattr(cloud, "status", "behind"), NEWER, OLD),
    (lambda cloud: setattr(cloud, "status", "diverged"), NEWER, OLD),
    (lambda cloud: cloud.live["data", SCHEMA]["labels"].pop("source-sha"), FIRST, None),
    (lambda cloud: cloud.live["data", SCHEMA]["labels"].update({"source-sha": "main"}), LABELS, None),
    (lambda cloud: cloud.live["data", SCHEMA]["labels"].update(team=7), LABELS, OLD),
    (lambda cloud: cloud.live["sql", INSTANCE]["settings"]["backupConfiguration"].update(pointInTimeRecoveryEnabled=False),
     PITR, OLD),
    (lambda cloud: cloud.live["sql", INSTANCE]["settings"].pop("backupConfiguration"), PITR, OLD),
    (lambda cloud: (setattr(cloud, "status", "behind"), cloud.live["sql", INSTANCE].pop("settings")), NEWER, OLD),
], ids=["behind", "diverged", "no-label", "not-a-commit", "malformed-labels", "pitr-off", "no-backups", "guard-first"])
def test_each_precondition_stops_before_any_effect_with_its_fixed_reason(released, change, message, label):
    cloud = Cloud()
    change(cloud)
    value, outputs = released(cloud)
    assert cloud.error == message and f"Data release blocked: {message}." in cloud.log
    assert cloud.events == [] and outputs == "phase=apply\n" and value == receipt(source_sha_label=label)


@pytest.mark.parametrize("status", ["identical", "ahead"])
def test_the_merged_commit_may_be_the_labelled_one_or_a_descendant_of_it_as_the_runtimes_guard_reads_them(released, status):
    cloud = Cloud()
    cloud.status = status
    assert released(cloud)[0] == receipt(**APPLIED) and cloud.error is None and cloud.events == ORDER


@pytest.mark.parametrize("change,message", [
    ({"state": "FAILED"}, UNFINISHED), ({"status": "RUNNING"}, UNFINISHED), ({"description": "another backup"}, UNFINISHED),
    ({"expiryTime": utc(NOW + WEEK + 61)}, "the backup does not expire 7 days after it was taken"),
    ({"expiryTime": utc(NOW + WEEK - 61)}, "the backup does not expire 7 days after it was taken"),
    ({"maxChargeableBytes": str(10 * 1024**3 + 1)}, "the backup's bytes exceed the source disk's"),
], ids=["backup-failed", "run-unfinished", "another-backup", "expiry-late", "expiry-early", "bytes"])
def test_the_backup_must_succeed_expire_after_seven_days_and_hold_at_most_the_source_disks_bytes(released, change, message):
    cloud = Cloud()
    cloud.backup = change
    value, outputs = released(cloud)
    assert cloud.error == message and cloud.events == ["backup"] and value == receipt()
    cloud, cloud.backup = Cloud(), {"maxChargeableBytes": str(10 * 1024**3)}  # exactly the source disk's bytes
    assert released(cloud, "at-the-cap")[0]["backup_id"] == BACKUP_ID and cloud.error is None


@pytest.mark.parametrize("delta", [-60, 60])
def test_cloud_sqls_readback_of_the_expiry_may_differ_from_the_request_by_at_most_a_minute(released, delta):
    """RELEASE.md 4.4 item 1: the readback, not the request, is what Cloud SQL keeps; a minute absorbs its rounding."""
    cloud = Cloud()
    cloud.backup = {"expiryTime": utc(NOW + WEEK + delta)}
    value, _ = released(cloud, f"expiry{delta:+d}")
    assert cloud.error is None and value["backup_id"] == BACKUP_ID


@pytest.mark.parametrize("fail,rerun", [
    ("diff", ORDER), ("schema", [event for event in ORDER if event != "migrate"]),
    ("indexes", [event for event in ORDER if event != "migrate"]),
    ("connector-check", [event for event in ORDER if event != "migrate"]),
    ("ruleset", [event for event in ORDER if event != "migrate"]), ("migrated", ["migrated", "indexed"]),
], ids=["after-the-backup", "after-the-migration", "after-the-schema", "after-the-indexes", "after-the-connector",
        "after-the-rules"])
def test_a_re_run_after_each_effect_takes_its_own_backup_and_repeats_no_committed_step(released, fail, rerun):
    cloud = Cloud()
    cloud.fail = fail
    assert released(cloud)[0]["backup_id"] == BACKUP_ID and cloud.error and cloud.events[-1] == fail
    cloud.events, cloud.compared, cloud.fail, cloud.packet = [], [], None, record(release_run_attempt=3)
    value, outputs = released(cloud, "rerun")
    assert cloud.error is None and cloud.events == rerun and value["run_attempt"] == 3
    assert outputs == ("phase=verify\n" if fail == "migrated" else "phase=apply\n")
    # Once the schema carries the merged commit, the guard needs no comparison.
    assert cloud.compared == ([f"repos/{D.REPOSITORY}/compare/{OLD}...{SHA}"] if fail in ("diff", "schema") else [])
    assert "backup" not in rerun or cloud.sent["description"] == f"specimen-data-release-{SHA}-456-3"


def test_the_backup_intent_is_write_once_so_one_attempt_never_sends_a_second_backup(released):
    cloud = Cloud()
    cloud.fail = "diff"
    released(cloud)
    cloud.events, cloud.fail = [], None
    value, _ = released(cloud)
    assert cloud.error == "this attempt already sent its backup; re-run the job" and cloud.events == []
    assert value == receipt()


def test_verify_reads_the_catalog_then_the_index_inventory_read_only_and_changes_nothing(released):
    cloud = Cloud(MERGED, rules=RULES)
    value, outputs = released(cloud)
    assert cloud.error is None and outputs == "phase=verify\n" and cloud.events == ["migrated", "indexed"]
    assert value == receipt("verify", tables=1, views=0) and cloud.compared == []


@pytest.mark.parametrize("change", [lambda indexes: indexes.pop(), lambda indexes: indexes[0].update(valid=False),
                                    lambda indexes: indexes[1].update(definition="CREATE INDEX x ON public.specimen (id)")],
                         ids=["missing", "invalid", "changed"])
def test_a_missing_or_changed_supplemental_index_makes_the_phase_apply(released, change):
    cloud = Cloud(MERGED, rules=RULES)
    change(cloud.indexes["indexes"])
    value, outputs = released(cloud)
    assert cloud.error is None and outputs == "phase=apply\n" and "A supplemental index is missing or changed." in cloud.log
    assert cloud.events == ["migrated", "indexed", *(event for event in ORDER if event != "migrate")]
    assert value == receipt(**APPLIED)


@pytest.mark.parametrize("change,message", [
    (lambda catalog: catalog["tables"].append("public.canary_table"), "the catalog's tables differ from the merged schema's"),
    (lambda catalog: catalog["tables"].clear(), "the catalog's tables differ from the merged schema's"),
    (lambda catalog: catalog["views"].append("public.specimen_listing"), "the catalog's views differ from the merged schema's"),
    (lambda catalog: catalog["owners"].append("cloudsqlsuperuser"), "the catalog's relations are not all owned by the owner role"),
    (lambda catalog: catalog["extensions"].append("vector"), "the catalog's extensions are not exactly plpgsql and uuid-ossp"),
    (lambda catalog: catalog["postconditions"].update(schema_owner="cloudsqlsuperuser"),
     "the catalog's public schema is not owned by the owner role"),
    (lambda catalog: catalog.update(expected_actor=False), "the catalog could not be read"),
    (lambda catalog: catalog.pop("postconditions"), "the catalog could not be read"),
], ids=["extra-table", "no-table", "persisted-view", "foreign-owner", "extension", "schema-owner", "actor", "unchecked"])
@pytest.mark.parametrize("phase", ["verify", "apply"])
def test_the_catalog_must_hold_exactly_the_merged_tables_one_owner_and_the_two_extensions(released, change, message, phase):
    cloud = Cloud(MERGED, rules=RULES) if phase == "verify" else Cloud()
    change(cloud.catalog)
    value, outputs = released(cloud)
    assert cloud.error == message and value["tables"] is None
    assert (cloud.events, outputs) == ((["migrated"], "") if phase == "verify" else (ORDER, "phase=apply\n"))


def test_verify_stops_when_the_index_inventory_cannot_be_read(released):
    cloud = Cloud(MERGED, rules=RULES)
    cloud.fail = "indexed"
    value, outputs = released(cloud)
    assert cloud.error == "the supplemental index inventory could not be read" and outputs == ""
    assert cloud.events == ["migrated", "indexed"] and value == receipt("verify", tables=1, views=0)


def test_the_gate_transport_sends_the_applys_one_backup_and_no_other_recovery_effect(monkeypatch):
    google = object.__new__(release_google.Google)
    google.path, google.plane, google.packet = Path("packet.json"), "data", record(expires_at_unix=int(time.time()) + 600)
    monkeypatch.setattr(release_google, "admit", lambda path, plane: google.packet)
    sent = []
    google.session = SimpleNamespace(request=lambda method, url, **kwargs: sent.append(url) or SimpleNamespace(
        status_code=200, json=lambda: {"name": "operation"}))
    backups = f"projects/{D.PROJECT}/backups"
    with pytest.raises(ValueError, match="current recovery effect"):
        google.request("sql", "POST", backups, body={})
    google._gate_effect = "backup"
    for suffix in ("instances", f"instances/{D.CLONE}/restoreBackup", f"instances/{D.SOURCE}/backupRuns"):
        with pytest.raises(ValueError):
            google.request("sql", "POST", f"projects/{D.PROJECT}/{suffix}", body={})
    assert google.request("sql", "POST", backups, body={}) == {"name": "operation"}
    with pytest.raises(ValueError, match="replayed"):
        google.request("sql", "POST", f"projects/{NUMBER}/backups", body={})
    assert sent == [release_google.ORIGINS["sql"] + backups]


def test_node_reads_the_index_inventory_read_only_for_a_gate_records_commit_on_the_source_alone(tmp_path):
    rows = [{"name": "specimen_text_cursor", "valid": True}]
    code, value, trace = release_sql(tmp_path, "indexed", answers=json.dumps([["AS definition", {"rows": rows}]]))
    texts = [text for text, _ in trace[2:]]
    assert (code, value) == (0, {"version": "native-sql-indexes/v1", "instance": D.SOURCE, "indexes": rows})
    assert texts[:2] == ["BEGIN TRANSACTION READ ONLY", "SET LOCAL statement_timeout = '30s'"] and texts[3:] == ["COMMIT"]
    assert "pg_get_indexdef(c.oid) AS definition" in texts[2]
    for env, instance in (({"RELEASE_AUTHORIZED_SHA": SHA}, D.SOURCE), ({"RELEASE_GATE_SHA": SHA}, I.CLONE)):
        assert node(tmp_path, "scripts/ci/release_sql.mjs", "indexed", {"DEPLOYMENT_ENVIRONMENT": "data-production", **env}, [],
                    instance, pg=RELEASE_PG) == (1, None, [])
