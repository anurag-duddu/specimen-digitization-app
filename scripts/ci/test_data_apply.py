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
import release_clone
import release_google
import release_initialize as I
from release_diagnostics import HTTPFailure
from test_data_first_initialization import RELEASE_PG, error, inventory, node, release_sql
from test_data_released_deploy import (CANARIES, INSTANCE, KEYS, MERGED, MERGED_CATALOG, MERGED_SCHEMA, OPS, RULES, RULESET,
                                       SCHEMA, SHA, UPDATED, record, state, tree)

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
# The first apply (D1): its claim, the fixed clone restored from this attempt's backup, checked and deleted, then the rest.
CLONED, GENERATION, DEADLINE = f"projects/{D.PROJECT}/instances/{D.CLONE}", "1790165000000001", record()["expires_at_unix"]
FIRST_ORDER = ["backup", "claim", "clone-create", "clone-restore", "restored", "clone-delete", *ORDER[1:]]
CLAIMED = "the first production restore is already claimed; the coordinator decides"
UNKNOWN = "the restore claim failed or its outcome is unknown; the coordinator decides"
RECIPE = "the SQL instance does not fit the restore clone's recipe"
NOT_OURS = "the restore clone is not provably this run's; the coordinator deletes it"
IAM = {"name": "cloudsql.iam_authentication", "value": "on"}


def unlabelled(cloud):
    cloud.live["data", SCHEMA]["labels"].pop("source-sha")


def operation(kind, target, name, status="DONE"):
    return {"kind": "sql#operation", "name": name, "status": status, "operationType": kind, "targetId": target,
            "targetProject": D.PROJECT, "user": ACTOR}


class Cloud:
    """The live data plane behind the release job's gate record: by default an additive change over the commit it last
    applied, OLD. Each effect and each Node run is one ordered event; `fail` names the one that fails, and each operation
    named in `pending` never finishes."""

    def __init__(self, schema=LIVE, label=OLD, rules="rules_version = '2';\n"):
        self.plane, self.packet, self.events, self.fail, self.status = "data", record(), [], None, "ahead"
        self.live = state(schema, OPS, rules=rules)
        self.live["data", SCHEMA]["labels"] = {"team": "specimen", **({"source-sha": label} if label else {})}
        self.live["sql", INSTANCE].update(databaseVersion="POSTGRES_18", settings={
            "dataDiskSizeGb": "10", "edition": "ENTERPRISE", "databaseFlags": [IAM],
            "backupConfiguration": {"enabled": True, "pointInTimeRecoveryEnabled": True}})
        self.diff, self.backup, self.compared, self.patches = [ADD] if schema == LIVE else [], {}, [], []
        self.catalog, self.indexes, self.restored = copy.deepcopy(MERGED_CATALOG), inventory(), copy.deepcopy(MERGED_CATALOG)
        self.claims, self.response, self.clone, self.pending, self.swap = [], {}, lambda clone: None, set(), False

    def effect(self, name):
        self.events.append(name)
        if name == self.fail:
            raise HTTPFailure(503)

    def operation(self, kind, target, name):
        """A Cloud SQL operation of the release identity; a pending one stays pending on every read."""
        value = operation(kind, target, name, "PENDING" if name in self.pending else "DONE")
        self.live["sql", f"projects/{D.PROJECT}/operations/{name}"] = value
        return value

    def claim_restore(self, payload, directory):
        """The fixed key's create-only insert: the first wins, every later one finds it (HTTP 412)."""
        self.effect("claim")
        self.claims.append(json.loads(payload))
        if len(self.claims) > 1 or isinstance(self.response, Exception):
            raise self.response if isinstance(self.response, Exception) else HTTPFailure(412)
        return {"kind": "storage#object", "bucket": release_clone.BUCKET, "name": release_clone.KEY, "generation": GENERATION,
                "metageneration": "1", "size": str(len(payload)), "temporaryHold": True, "contentType": "application/json",
                "md5Hash": release_clone.checksum(payload), **self.response}

    def request(self, api, method, resource, *, body=None, params=None, missing=False, diff=False):
        if method == "GET":
            if (api, resource) not in self.live:
                return None if missing else pytest.fail("unexpected read")
            if isinstance(self.live[api, resource], Exception):
                raise self.live[api, resource]
            return copy.deepcopy(self.live[api, resource])
        gate, claim = getattr(self, "_gate_effect", None), getattr(self, "_gate_claim", None)
        if api == "sql" and method == "DELETE":
            assert resource == CLONED
            self.effect("clone-delete")
            del self.live["sql", CLONED]
            return self.operation("DELETE", D.CLONE, "delete-operation")
        if api == "sql" and resource == f"projects/{D.PROJECT}/instances":
            assert (gate, claim) == ("clone-create", GENERATION)
            self.effect("clone-create")
            self.cloned, self.live["sql", CLONED] = body, {**copy.deepcopy(body), "createTime": utc(NOW - 1)}
            self.clone(self.live["sql", CLONED])
            return self.operation("CREATE", D.CLONE, "create-operation")
        if api == "sql" and resource == f"{CLONED}/restoreBackup":
            assert (gate, claim) == ("clone-restore", GENERATION)
            self.effect("clone-restore")
            self.restore = body
            return self.operation("RESTORE_VOLUME", D.CLONE, "restore-operation")
        if api == "sql":
            assert (method, resource, gate) == ("POST", f"projects/{D.PROJECT}/backups", "backup")
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
    """release_sql.mjs as the release identity for the admitted commit, on the source but for the restored clone: each
    mode one event; `fail` exits 1."""
    def run(command, **kwargs):
        assert command[:2] == ["node", "scripts/ci/release_sql.mjs"]
        assert command[3] == (D.CLONE if command[2] == "restored" else D.SOURCE)
        assert command[4].endswith(f"{command[3]}-{command[2]}.json")
        assert kwargs["env"]["RELEASE_GATE_SHA"] == SHA and 0 < kwargs["timeout"] <= 300
        cloud.events.append(command[2])
        if command[2] == cloud.fail:
            return subprocess.CompletedProcess(command, 1, b"", b"")
        if command[2] == "migrate":
            cloud.diff = []  # committed: Data Connect's next diff finds nothing
        if command[2] == "restored" and cloud.swap:
            cloud.live["sql", CLONED]["createTime"] = utc(NOW)  # another clone of the same name replaced this run's
        cloud.indexes = inventory() if command[2] == "indexes" else cloud.indexes
        count = len(json.loads(Path(command[5]).read_text())["statements"]) if command[2] == "migrate" else 0
        answer = {"migrated": cloud.catalog, "indexed": cloud.indexes, "indexes": inventory(), "restored": cloud.restored,
                  "migrate": {"version": "data-migration/v1", "statements": count, "committed": True}}[command[2]]
        Path(command[4]).write_text(json.dumps(answer))
        Path(command[4]).chmod(0o600)
        return subprocess.CompletedProcess(command, 0, b"", b"")
    return run


@pytest.fixture
def released(tmp_path, monkeypatch, capsys):
    """deploy_released_data at a fixed instant; every exit keeps the receipt, the step output and the log public."""
    output, steps, clock = *tree(tmp_path, monkeypatch), [NOW]
    monkeypatch.setattr(time, "time", lambda: clock[0])
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
    run.clock = clock
    return run


def receipt(phase="apply", **facts):
    """Public facts only, each as last observed: stopped before any effect unless facts say otherwise."""
    return {"version": "data-released/v1", "source_sha": SHA, "run_id": 456, "run_attempt": 2, "phase": phase,
            "schema_etag": "schema-etag", "schema_update_time": UPDATED, "connector_etag": "connector-etag",
            "storage_ruleset": RULESET, "source_sha_label": OLD, "backup_id": None, "first_restore": None, "tables": None,
            "views": None, **facts}


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
    (lambda cloud: cloud.live["data", SCHEMA]["labels"].update({"source-sha": "main"}), LABELS, None),
    (lambda cloud: cloud.live["data", SCHEMA]["labels"].update(team=7), LABELS, OLD),
    (lambda cloud: cloud.live["sql", INSTANCE]["settings"]["backupConfiguration"].update(pointInTimeRecoveryEnabled=False),
     PITR, OLD),
    (lambda cloud: cloud.live["sql", INSTANCE]["settings"].pop("backupConfiguration"), PITR, OLD),
    (lambda cloud: (setattr(cloud, "status", "behind"), cloud.live["sql", INSTANCE].pop("settings")), NEWER, OLD),
    # The first apply's own: the recipe fits the source, and the fixed clone is absent.
    (lambda cloud: (unlabelled(cloud), cloud.live.update({("sql", CLONED): {"name": D.CLONE}})),
     "the restore clone already exists; the coordinator decides", None),
    # The clone roles are time-bounded: while the owner's window is closed the clone cannot even be read.
    (lambda cloud: (unlabelled(cloud), cloud.live.update({("sql", CLONED): HTTPFailure(403)})),
     "the restore clone cannot be read; the first apply needs the owner's window open", None),
    (lambda cloud: (unlabelled(cloud), cloud.live["sql", INSTANCE]["settings"]["databaseFlags"].clear()), RECIPE, None),
    (lambda cloud: (unlabelled(cloud), cloud.live["sql", INSTANCE]["settings"].update(edition="ENTERPRISE_PLUS")),
     RECIPE, None),
    (lambda cloud: (unlabelled(cloud), cloud.live["sql", INSTANCE].pop("databaseVersion")), RECIPE, None),
    (lambda cloud: (unlabelled(cloud), cloud.live["sql", INSTANCE]["settings"]["backupConfiguration"].clear()), PITR, None),
], ids=["behind", "diverged", "not-a-commit", "malformed-labels", "pitr-off", "no-backups", "guard-first", "clone-exists",
        "window-closed", "no-iam-authentication", "another-edition", "no-version", "first-pitr-off"])
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


def test_the_first_apply_claims_restores_its_backup_into_the_clone_checks_and_deletes_it_then_applies(released):
    cloud = Cloud(label=None)
    value, outputs = released(cloud)
    assert cloud.error is None and outputs == "phase=apply\n" and cloud.events == FIRST_ORDER and cloud.compared == []
    assert value == receipt(**APPLIED, first_restore="checked") and ("sql", CLONED) not in cloud.live
    # The claim binds the gate record's commit, this run and attempt, this attempt's backup, the clone and the source,
    # for a window from the claim to the gate record's deadline.
    assert cloud.claims == [{"version": "clone-allowance-claim/v2", "source_sha": SHA, "run_id": 456, "run_attempt": 2,
                             "backup_id": BACKUP_ID, "clone": D.CLONE, "source": D.SOURCE, "issued_at_unix": NOW,
                             "expires_at_unix": DEADLINE}]
    # The envelope's recipe at its smallest tier, on the source's region, version and disk; no backups, no point-in-time
    # recovery; labelled with this run and attempt. The restore reads this attempt's backup of the source.
    assert cloud.cloned == {"name": D.CLONE, "region": "us-east4", "databaseVersion": "POSTGRES_18", "settings": {
        "tier": "db-f1-micro", "edition": "ENTERPRISE", "availabilityType": "ZONAL", "dataDiskSizeGb": "10",
        "dataDiskType": "PD_SSD", "storageAutoResize": False, "backupConfiguration": {"enabled": False,
                                                                                      "pointInTimeRecoveryEnabled": False},
        "ipConfiguration": {"ipv4Enabled": True, "sslMode": "ENCRYPTED_ONLY"}, "databaseFlags": [IAM],
        "userLabels": {"release-run": "456", "release-attempt": "2", "source-sha": SHA,
                       "purpose": "isolated-restore-rehearsal"}}}
    assert cloud.restore == {"restoreBackupContext": {"backupRunId": BACKUP_ID, "instanceId": D.SOURCE, "project": D.PROJECT}}


def test_the_clone_is_checked_against_the_live_schema_its_backup_holds_and_the_source_against_the_merged_one(released):
    (D.ROOT / "dataconnect/schema/schema.gql").write_text(MERGED_SCHEMA + "type Note @table {\n  id: UUID!\n}\n")
    cloud = Cloud(label=None)
    cloud.diff.append('CREATE TABLE "public"."note" ("id" uuid NOT NULL, PRIMARY KEY ("id"))')
    cloud.catalog["tables"] = ["public.note", "public.specimen"]
    assert released(cloud)[0]["tables"] == 2 and cloud.error is None and cloud.events == FIRST_ORDER
    cloud = Cloud(label=None)
    cloud.restored["tables"] = ["public.note", "public.specimen"]
    released(cloud, "merged-tables")
    assert cloud.error == "the restored clone's tables differ from the live schema's"


@pytest.mark.parametrize("change,message", [
    (lambda catalog: catalog["tables"].append("public.canary_table"), "tables differ from the live schema's"),
    (lambda catalog: catalog["owners"].append("cloudsqlsuperuser"), "relations are not all owned by the owner role"),
    (lambda catalog: catalog["extensions"].append("vector"), "extensions are not exactly plpgsql and uuid-ossp"),
    (lambda catalog: catalog["postconditions"].update(schema_owner="cloudsqlsuperuser"),
     "public schema is not owned by the owner role"),
], ids=["extra-table", "foreign-owner", "extension", "schema-owner"])
def test_a_clone_that_fails_its_catalog_check_is_deleted_as_this_runs_and_stops_the_first_apply(released, change, message):
    """The clone is checked as the source is, with messages that name it."""
    message = f"the restored clone's {message}"
    cloud = Cloud(label=None)
    change(cloud.restored)
    value, outputs = released(cloud)
    assert cloud.error == message and cloud.events == FIRST_ORDER[:6] and ("sql", CLONED) not in cloud.live
    assert value == receipt(source_sha_label=None, backup_id=BACKUP_ID, first_restore="claimed")


@pytest.mark.parametrize("response,message", [
    (HTTPFailure(412), CLAIMED), (HTTPFailure(403), UNKNOWN), (TimeoutError(), UNKNOWN), ({"temporaryHold": False}, UNKNOWN),
    ({"generation": "0"}, UNKNOWN),
], ids=["claimed", "refused", "unknown", "not-held", "no-generation"])
def test_an_existing_or_unproven_claim_stops_the_first_apply_before_its_clone(released, response, message):
    cloud = Cloud(label=None)
    cloud.response = response
    value, _ = released(cloud)
    assert cloud.error == message and cloud.events == ["backup", "claim"] and ("sql", CLONED) not in cloud.live
    assert value == receipt(source_sha_label=None, backup_id=BACKUP_ID)


def test_a_re_run_after_the_claim_finds_it_and_stops_since_deleting_a_claim_never_refunds_it(released):
    cloud = Cloud(label=None)
    cloud.fail = "clone-create"
    released(cloud)
    assert cloud.events == ["backup", "claim", "clone-create"] and len(cloud.claims) == 1
    cloud.events, cloud.fail, cloud.packet = [], None, record(release_run_attempt=3)
    value, _ = released(cloud, "rerun")
    assert cloud.error == CLAIMED and cloud.events == ["backup", "claim"] and cloud.claims[1]["run_attempt"] == 3
    assert value["backup_id"] == BACKUP_ID and value["first_restore"] is None


@pytest.mark.parametrize("left,claims", [(1800, False), (1801, True)], ids=["too-late", "in-time"])
def test_the_claim_needs_half_an_hour_of_the_gate_records_window_and_ends_at_its_deadline(released, left, claims):
    released.clock[0] = DEADLINE - left
    cloud = Cloud(label=None)
    value, _ = released(cloud)
    if not claims:
        assert cloud.error == "too little of the gate record's hour remains for the restore check; re-run the job"
        assert cloud.events == ["backup"] and cloud.claims == []
        return
    assert cloud.error is None and cloud.events == FIRST_ORDER
    assert (cloud.claims[0]["issued_at_unix"], cloud.claims[0]["expires_at_unix"]) == (DEADLINE - left, DEADLINE)


@pytest.mark.parametrize("change", [
    lambda cloud: setattr(cloud, "clone", lambda clone: clone["settings"]["userLabels"].update({"release-attempt": "1"})),
    lambda cloud: setattr(cloud, "clone", lambda clone: clone.update(createTime="2026-09-23T00:00:00Z")),
    lambda cloud: setattr(cloud, "swap", True),
], ids=["another-attempts-labels", "created-before-this-record", "replaced-after-the-check"])
def test_only_the_clone_this_run_created_and_proved_it_owns_is_ever_deleted(released, change):
    cloud = Cloud(label=None)
    change(cloud)
    released(cloud)
    assert cloud.error == NOT_OURS and ("sql", CLONED) in cloud.live and "clone-delete" not in cloud.events


@pytest.mark.parametrize("fail,message,events,left", [
    ("clone-create", "the restore clone could not be created; the coordinator decides", FIRST_ORDER[:3], False),
    ("clone-restore", "the backup could not be restored into the clone", [*FIRST_ORDER[:4], "clone-delete"], False),
    ("clone-delete", "the restore clone's deletion was not confirmed; the coordinator deletes it", FIRST_ORDER[:6], True),
], ids=["create-refused", "restore-refused", "delete-refused"])
def test_a_refused_clone_request_stops_with_its_fixed_reason_and_an_owned_clone_is_still_deleted(
        released, fail, message, events, left):
    cloud = Cloud(label=None)
    cloud.fail = fail
    value, _ = released(cloud)
    assert cloud.error == message and f"Data release blocked: {message}." in cloud.log and cloud.events == events
    assert (("sql", CLONED) in cloud.live) is left and value["first_restore"] == "claimed"


def test_every_clone_wait_ends_early_enough_to_delete_the_clone_within_the_gate_records_deadline(released, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda seconds: released.clock.__setitem__(0, released.clock[0] + seconds))
    cloud = Cloud(label=None)
    cloud.pending = {"create-operation"}
    released(cloud)
    # A clone still being created cannot be proved this run's, so the coordinator deletes it.
    assert cloud.error == ("the restore clone's creation did not complete in time; the coordinator deletes the clone if "
                           "it exists")
    assert cloud.events == ["backup", "claim", "clone-create"] and released.clock[0] <= DEADLINE - 600
    released.clock[0] = NOW
    cloud = Cloud(label=None)
    cloud.pending = {"restore-operation"}
    released(cloud, "restore")
    assert cloud.error == "the backup was not restored into the clone in time" and released.clock[0] <= DEADLINE - 600
    assert cloud.events == ["backup", "claim", "clone-create", "clone-restore", "clone-delete"]
    assert ("sql", CLONED) not in cloud.live


def test_the_gate_transport_sends_the_first_applys_clone_and_restore_only_after_its_claim(monkeypatch, tmp_path):
    google = object.__new__(release_google.Google)
    google.path, google.plane, google.packet = tmp_path / "packet.json", "data", record(expires_at_unix=int(time.time()) + 3000)
    monkeypatch.setattr(release_google, "admit", lambda path, plane: google.packet)
    sent = []
    google.session = SimpleNamespace(request=lambda method, url, **kwargs: sent.append((method, url)) or SimpleNamespace(
        status_code=200, json=lambda: {"name": "operation"}))
    effects = {"clone-create": f"projects/{D.PROJECT}/instances", "clone-restore": f"{CLONED}/restoreBackup"}
    for name, resource in effects.items():
        google._gate_effect = name
        with pytest.raises(ValueError, match="claim"):
            google.request("sql", "POST", resource, body={})
    google._gate_claim = GENERATION
    for name, resource in effects.items():
        google._gate_effect = name
        assert google.request("sql", "POST", resource, body={}) == {"name": "operation"}
        with pytest.raises(ValueError, match="replayed"):
            google.request("sql", "POST", resource, body={})
    # Of the instances, only the clone is ever deleted.
    with pytest.raises(ValueError, match="clone"):
        google.request("sql", "DELETE", f"projects/{D.PROJECT}/instances/{D.SOURCE}")
    assert google.request("sql", "DELETE", CLONED) == {"name": "operation"}
    assert sent == [("POST", release_google.ORIGINS["sql"] + resource) for resource in effects.values()] + [
        ("DELETE", release_google.ORIGINS["sql"] + CLONED)]


def test_the_gate_claim_is_bounded_by_its_own_window(monkeypatch, tmp_path):
    google = object.__new__(release_google.Google)
    google.path, google.plane, google.packet = tmp_path / "packet.json", "data", record(expires_at_unix=int(time.time()) + 3000)
    monkeypatch.setattr(release_google, "admit", lambda path, plane: google.packet)
    monkeypatch.setenv("RELEASE_SERVICE_ACCOUNT", release_clone.ACTOR)
    sent = []
    google.session = SimpleNamespace(request=lambda *args, **kwargs: sent.append(args) or SimpleNamespace(
        status_code=200, headers={}, close=lambda: None, iter_content=lambda **kw: iter([b'{"kind": "storage#object"}'])))
    near = release_clone.canonical({"version": "clone-allowance-claim/v2", "expires_at_unix": int(time.time()) + 1700})
    with pytest.raises(ValueError, match="claim authority"):
        google.claim_restore(near, tmp_path)
    assert sent == []
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    google.path = fresh / "packet.json"
    window = release_clone.canonical({"version": "clone-allowance-claim/v2", "expires_at_unix": int(time.time()) + 2000})
    assert google.claim_restore(window, fresh) == {"kind": "storage#object"} and len(sent) == 1


def test_node_reads_the_restored_clones_catalog_read_only_for_a_gate_records_commit_on_the_clone_alone(tmp_path):
    catalog = {key: value for key, value in MERGED_CATALOG.items() if key != "postconditions"}
    answers = [["$postconditions$", [{"command": "DO"}, {"command": "SELECT", "rows": [{"postconditions": {"x": 1}}]}]],
               ["AS extensions", {"rows": [catalog]}], ["AS name", {"rows": [{"name": D.DATABASE}]}]]
    env = {"DEPLOYMENT_ENVIRONMENT": "data-production", "RELEASE_GATE_SHA": SHA}
    code, value, trace = node(tmp_path, "scripts/ci/release_sql.mjs", "restored", env, answers, I.CLONE, pg=RELEASE_PG)
    texts = [json.loads(line)[0] for line in trace[2:]]
    assert (code, value) == (0, {**catalog, "postconditions": {"x": 1}})
    assert json.loads(trace[0]) == ["pool", I.MAINTENANCE, D.DATABASE]
    assert texts[0] == "BEGIN TRANSACTION READ ONLY" and texts[-1] == "COMMIT"
    # Gate-only and clone-only; migrate and migrated stay on the source.
    for mode, instance, shas in (("restored", D.SOURCE, {"RELEASE_GATE_SHA": SHA}),
                                 ("restored", I.CLONE, {"RELEASE_AUTHORIZED_SHA": SHA}),
                                 ("migrated", I.CLONE, {"RELEASE_GATE_SHA": SHA}), ("migrate", I.CLONE, {"RELEASE_GATE_SHA": SHA})):
        assert node(tmp_path, "scripts/ci/release_sql.mjs", mode, {"DEPLOYMENT_ENVIRONMENT": "data-production", **shas}, [],
                    instance, pg=RELEASE_PG) == (1, None, [])


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
