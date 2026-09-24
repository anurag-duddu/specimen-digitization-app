#!/usr/bin/env python3
"""Protected, named data deployment with native restore and owned-clone cleanup."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

from release_admission import (admit, digest, exact_keys, gh_json, integer, materialize_inputs,
                               private_bytes, read_bound_plan, require, strict_json)
from release_context import PROJECT, REPOSITORY
from release_google import Google, cleanup_packet, cleanup_permit
from release_diagnostics import HTTPFailure, public_failure, stage
import release_gate
import schema_gate

ROOT = Path(__file__).resolve().parents[2]
PREFIX = f"projects/{PROJECT}/locations/us-east4/services/specimen-digitization-service"
SOURCE = "specimen-digitization-instance"
CLONE = "specimen-digitization-restore-20260908-r1"
DATABASE = "specimen-digitization-database"
RULE_RELEASE = f"projects/{PROJECT}/releases/firebase.storage/{PROJECT}.firebasestorage.app"
SCHEMA_NAME, CONNECTOR_NAME = f"{PREFIX}/schemas/main", f"{PREFIX}/connectors/specimen-server"
RULESET = re.compile(rf"projects/{re.escape(PROJECT)}/rulesets/[A-Za-z0-9_-]{{1,100}}")
# An etag is an opaque public revision: printable, without whitespace, bounded.
REVISION = re.compile(r"[\x21-\x7e]{1,500}")
# An extension name the first initialization may print: a bare identifier, never a workflow command or a value.
EXTENSION = re.compile(r"[a-z][a-z0-9_-]{0,62}")
COUNTS = ("relations", "views", "routines", "types")
APPLICATION_ROLES = {role: f"firebase{role}_{DATABASE}_public" for role in ("owner", "writer", "reader")}
OWNER = APPLICATION_ROLES["owner"]
# RELEASE.md 4.3 step 3 reads a diff statement as tokens: ASCII space, a quoted identifier, a string, a word, a number,
# punctuation, an operator run or any other character. A backslash or an "other" token refuses it, so no escape string
# or dollar quote can move a statement boundary. release_sql.mjs reads each statement the same way before it runs.
SQL_TOKEN = re.compile(r"""(?P<space>[ \t\n\r\f\v]+)|(?P<ident>"(?:[^"]|"")+")|(?P<string>'(?:[^']|'')*')"""
                       r"|(?P<word>[A-Za-z_][A-Za-z0-9_]*)|(?P<number>[0-9]+(?:\.[0-9]+)?)|(?P<punct>[(),.;\[\]])"
                       r"|(?P<operator>[-+*/<>=~!@#%^&|`?:]+)|(?P<other>[\s\S])")
# A diff statement is named by its longest leading keywords in this list, else "other"; never by its own text.
KINDS = frozenset(("CREATE TABLE", "CREATE VIEW", "CREATE INDEX", "CREATE UNIQUE INDEX", "ALTER TABLE", "CREATE EXTENSION",
    "CREATE SCHEMA", "CREATE OR REPLACE", "CREATE MATERIALIZED VIEW", "CREATE FUNCTION", "CREATE TRIGGER", "CREATE TYPE",
    "CREATE SEQUENCE", "CREATE ROLE", "CREATE", "ALTER", "DROP TABLE", "DROP INDEX", "DROP VIEW", "DROP SCHEMA",
    "DROP EXTENSION", "DROP", "TRUNCATE", "GRANT", "REVOKE", "DO", "COMMENT", "INSERT", "UPDATE", "DELETE", "SELECT", "SET",
    "RESET", "COPY", "CALL", "VACUUM", "ANALYZE", "REINDEX", "LOCK", "REFRESH"))
# Empty-scope creation modes. Each requires the reviewed evidence recipient and
# publishes its own signed receipt; the legacy first-admin mode does neither.
FIRST_SCOPE_MODES = {"first-scope-owner-bootstrap/v1", "first-scope-hierarchy-bootstrap/v1"}
FIRST_SCOPE_RECEIPTS = {"first-scope-owner-applied/v1", "first-scope-hierarchy-applied/v1"}
INDEXES = {"specimen_text_cursor", "auxiliary_text_cursor", "specimen_search_cursor", "snapshot_search_batch"}
INDEX_SPECS = {
    "specimen_text_cursor": ("specimen", ["organization_id", "collection_id", "id::text COLLATE C"], ["created_at", "revision", "state", "disposition", "work_available_at", "active_run_id", "sensitive"]),
    "auxiliary_text_cursor": ("auxiliary_document", ["organization_id", "collection_id", "kind", "id::text COLLATE C"], ["created_at", "revision"]),
    "specimen_search_cursor": ("specimen", ["organization_id", "collection_id", "created_at", "id::text COLLATE C"], ["id", "revision", "state", "disposition", "sensitive"]),
    "snapshot_search_batch": ("specimen_snapshot", ["organization_id", "collection_id", "snapshot #>> '{batch_id}'::text[]", "specimen_id", "revision"], []),
    "specimen_scope_checksum": ("specimen", ["organization_id", "collection_id", "source_checksum"], []),
}
CATALOG_BOOLEANS = {"expected_database", "expected_actor", "application_database_exists", "application_catalog_observed",
    "owner_exists", "reader_exists", "writer_exists",
    "expected_roles_without_global_privileges", "owner_public_schema", "owner_only_approved_tables_in_database",
    "owner_has_no_parent_memberships", "current_can_select_all_public_tables", "current_can_select_sequences",
    "current_can_maintain_required_tables", "current_can_create_required_indexes", "current_has_global_privileges"}


def catalog_fingerprint():
    return hashlib.sha256((ROOT / "scripts/ci/release_sql_catalog.sql").read_bytes()).hexdigest()


def approved_tables():
    """The committed application tables, derived from the schema that publishes them.

    One source of truth: a table added to or removed from `schema.gql` changes
    this set, and every count checked against it follows, instead of drifting
    apart from a number written out by hand.
    """
    return {re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
            for name in re.findall(r"type (\w+) @table", (ROOT / "dataconnect/schema/schema.gql").read_text())}


def validate_catalog(value):
    exact_keys(value, CATALOG_BOOLEANS | {"approved_tables", "public_table_count", "unapproved_table_count"}, "public catalog observations")
    require(all(type(value[k]) is bool for k in CATALOG_BOOLEANS), "catalog observations must be booleans")
    require(value["expected_database"] and value["expected_actor"], "wrong catalog database or maintenance identity")
    require(value["application_database_exists"] == value["application_catalog_observed"],
            "existing application database requires its own observed catalog")
    expected_tables = approved_tables()
    require(isinstance(value["approved_tables"], list) and all(isinstance(name, str) for name in value["approved_tables"])
            and len(set(value["approved_tables"])) == len(value["approved_tables"])
            and set(value["approved_tables"]) <= expected_tables, "catalog output may contain only committed application table names")
    for key in ("public_table_count", "unapproved_table_count"):
        integer(value[key], 0, 100000, key)
    require(value["public_table_count"] == len(value["approved_tables"]) + value["unapproved_table_count"], "catalog counts disagree")
    if not value["application_catalog_observed"]:
        require(value["public_table_count"] == 0 and not any(value[key] for key in (
            "owner_public_schema", "owner_only_approved_tables_in_database", "current_can_select_all_public_tables",
            "current_can_select_sequences", "current_can_maintain_required_tables", "current_can_create_required_indexes")),
            "absent application database cannot assert schema or table capabilities")
    return value


def sql_catalog(directory):
    target = directory / "sql-catalog.json"
    result = subprocess.run(["node", "scripts/ci/release_sql.mjs", "catalog", SOURCE, str(target)],
                            cwd=ROOT, capture_output=True, timeout=60)
    require(result.returncode == 0, "named read-only IAM SQL catalog unavailable; no identity or privilege is created")
    return validate_catalog(strict_json(private_bytes(target)))


def inventory_catalog(google, plan, directory, output):
    source = google.request("sql", "GET", f"projects/{PROJECT}/instances/{SOURCE}")
    require(source.get("region") == "us-east4" and source.get("settings", {}).get("settingsVersion") == plan["database_etag"],
            "named SQL target changed before read-only catalog")
    catalog = sql_catalog(directory)
    output.write_text(json.dumps({"version": "data-inventory/v1", "source_sha": google.packet["source_sha"],
        "run_id": google.packet["release_run_id"], "run_attempt": google.packet["release_run_attempt"],
        "catalog_sha256": plan["catalog_sha256"], "catalog": catalog,
        "schema_ready": False, "data_ready": False, "release_accepted": False}, sort_keys=True) + "\n")


def source_fingerprints():
    paths = [ROOT / "dataconnect/dataconnect.yaml", ROOT / "dataconnect/connector/connector.yaml", ROOT / "storage.rules"]
    paths += sorted((ROOT / "dataconnect/schema").glob("*.gql"))
    paths += sorted((ROOT / "dataconnect/connector").glob("*.gql"))
    paths += sorted((ROOT / "dataconnect/sql").glob("*.sql"))
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def validate_bootstrap_plan(bootstrap):
    payload = bootstrap.get("payload") if isinstance(bootstrap, dict) else None
    first_scope = isinstance(payload, dict) and payload.get("schema_version") in FIRST_SCOPE_MODES
    exact_keys(bootstrap, {"payload", "sha256"} | ({"evidence_recipient"} if first_scope else set()), "bootstrap")
    digest(bootstrap["sha256"], "bootstrap artifact")
    if first_scope:
        from bootstrap_release import validate_evidence_recipient
        validate_evidence_recipient(bootstrap["evidence_recipient"])


def validate_plan(plan, packet, *, now=None):
    if isinstance(plan, dict) and plan.get("version") == "data-initialization-inventory/v1":
        from release_initialize import fingerprints, validate_catalog_recipient
        exact_keys(plan, {"version", "source_sha", "database_etag", "initialization_files", "catalog_recipient"}, "full initialization inventory")
        validate_catalog_recipient(plan["catalog_recipient"])
        require(plan["source_sha"] == packet["source_sha"] and plan["initialization_files"] == fingerprints(), "catalog source changed")
        require(isinstance(plan["database_etag"], str) and 0 < len(plan["database_etag"]) <= 500, "observed SQL revision required")
        return plan
    if isinstance(plan, dict) and plan.get("version") == "data-inventory/v1":
        exact_keys(plan, {"version", "source_sha", "database_etag", "catalog_sha256"}, "catalog phase")
        require(plan["source_sha"] == packet["source_sha"] and plan["catalog_sha256"] == catalog_fingerprint(), "catalog source mismatch")
        require(isinstance(plan["database_etag"], str) and 0 < len(plan["database_etag"]) <= 500, "observed SQL revision required")
        return plan
    if isinstance(plan, dict) and plan.get("version") in {"data-bootstrap/v1", "data-verify/v1"}:
        exact_keys(plan, {"version", "source_sha", "source_files", "schema_receipt", "bootstrap"}, "readiness phase")
        require(plan["source_sha"] == packet["source_sha"] and plan["source_files"] == source_fingerprints(), "compatible current data source required")
        receipt = exact_keys(plan["schema_receipt"], {"source_sha", "sha256", "run_id", "run_attempt"}, "previous schema receipt")
        require(isinstance(receipt["source_sha"], str) and re.fullmatch(r"[a-f0-9]{40}", receipt["source_sha"]), "invalid schema source")
        digest(receipt["sha256"], "schema receipt")
        for key in ("run_id", "run_attempt"):
            integer(receipt[key], 1, 2**53, key)
        require((plan["bootstrap"] is not None) == (plan["version"] == "data-bootstrap/v1"), "bootstrap artifact and phase must agree")
        if plan["bootstrap"] is not None:
            validate_bootstrap_plan(plan["bootstrap"])
        return plan
    initializing = isinstance(plan, dict) and plan.get("version") == "data-initialize-missing/v1"
    exact_keys(plan, {"version", "source_sha", "schema_mode", "source_files", "database_etag", "schema_etag",
                     "connector_etag", "storage_release_etag", "recovery", "writers", "bootstrap"}
                     | ({"initialization", "catalog_recipient"} if initializing else set())
                     | ({"schema_placeholder"} if initializing and "schema_placeholder" in plan else set()), "data plan")
    require(plan["version"] in {"data-apply/v1", "data-initialize-missing/v1"} and plan["source_sha"] == packet["source_sha"], "data source mismatch")
    require(plan["schema_mode"] in ({"initialize_missing"} if initializing else {"validate_existing", "initialize_empty"}), "unapproved migration mode")
    require(plan["source_files"] == source_fingerprints(), "committed data source fingerprints changed")
    require(plan["writers"] == "no_runtime_exists", "first-release data changes require independently absent runtime writers")
    for key in ("database_etag", "schema_etag", "connector_etag", "storage_release_etag"):
        require(plan[key] is None or isinstance(plan[key], str) and 0 < len(plan[key]) <= 500, "invalid expected data revision")
    recovery = exact_keys(plan["recovery"], {"backup_id", "clone", "recipe", "expires_at_unix", "allowance"}
                          | ({"backup_retention"} if "backup_retention" in plan["recovery"] else set()), "recovery")
    require(recovery["clone"] == CLONE and (recovery["backup_id"] is None or isinstance(recovery["backup_id"], str)
            and re.fullmatch(r"[1-9][0-9]*", recovery["backup_id"])), "unapproved recovery target or backup")
    exact_keys(recovery["recipe"], {"tier", "source_version", "source_edition", "source_disk_gb"}, "restore recipe")
    now = time.time() if now is None else now
    integer(recovery["expires_at_unix"], 1, 2**53, "recovery expiry")
    require(now < recovery["expires_at_unix"] <= now + 7200, "recovery deadline expired or over two hours")
    from release_clone import validate_allowance
    validate_allowance(recovery["allowance"], packet, recovery["expires_at_unix"], now=now)
    if "backup_retention" in recovery:
        from release_backup import validate_retention
        require(recovery["backup_id"] is None, "finite retention applies only to the one new backup")
        validate_retention(recovery["backup_retention"], packet, now=now,
                           restore_expiry=recovery["expires_at_unix"], disk_gb=recovery["recipe"]["source_disk_gb"])
    if plan["bootstrap"] is not None:
        validate_bootstrap_plan(plan["bootstrap"])
    if initializing:
        from release_initialize import validate_plan as validate_initialization
        validate_initialization(plan, packet)
    return plan


def committed_source(folder):
    """One folder's committed *.gql files as a Data Connect source, exactly as a release sends them."""
    return {"files": [{"path": path.name, "content": path.read_text()} for path in sorted((ROOT / folder).glob("*.gql"))]}


def committed_rules():
    """The committed Storage rules as a ruleset source, exactly as a release publishes them."""
    return {"files": [{"name": "storage.rules", "content": (ROOT / "storage.rules").read_text()}]}


def data_bodies(plan):
    postgres = {"database": DATABASE, "cloudSql": {
        "instance": f"projects/{PROJECT}/locations/us-east4/instances/{SOURCE}"}}
    if plan["schema_mode"] == "initialize_empty":
        postgres["schemaMigration"] = "MIGRATE_COMPATIBLE"
    else:
        postgres["schemaValidation"] = "COMPATIBLE"
    schema = {"name": f"{PREFIX}/schemas/main", "source": committed_source("dataconnect/schema"), "datasources": [{"postgresql": postgres}]}
    connector = {"name": f"{PREFIX}/connectors/specimen-server", "source": committed_source("dataconnect/connector")}
    if plan["schema_etag"]:
        schema["etag"] = plan["schema_etag"]
    if plan["connector_etag"]:
        connector["etag"] = plan["connector_etag"]
    return schema, connector


def compare_restore(left, right):
    for field in ("rows", "indexes", "columns", "constraints", "sequences", "schema"):
        require(field in left and left[field] == right.get(field), f"native restore {field} mismatch")


def verify_indexes(inventory):
    by_name = {value["name"]: value for value in inventory["indexes"]}
    require(len(by_name) == len(inventory["indexes"]), "ambiguous index names")
    normalize = lambda value: re.sub(r'[\s()"]', '', value)
    for name, (table, keys, includes) in INDEX_SPECS.items():
        actual = by_name.get(name, {})
        expected_definition = f"CREATE {'UNIQUE ' if name == 'specimen_scope_checksum' else ''}INDEX {name} ON public.{table} USING btree ({', '.join(keys)})"
        if includes:
            expected_definition += " INCLUDE (" + ", ".join(includes) + ")"
        require(actual.get("valid") is True and actual.get("unique") is (name == "specimen_scope_checksum")
                and actual.get("table_name") == table and actual.get("method") == "btree"
                and actual.get("predicate") is None
                and normalize(actual.get("definition", "")) == normalize(expected_definition)
                and actual.get("includes") == includes, "required index definition missing, invalid or mismatched")


def stamp(value):
    require(isinstance(value, str), "native resource timestamp missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(parsed.tzinfo is not None, "native timestamp must have a timezone")
    return parsed.timestamp()


def creation_proof(clone, operations, packet):
    labels = clone.get("settings", {}).get("userLabels", {})
    require(clone.get("name") == CLONE and all(labels.get(k) == v for k, v in {
        "release-run": str(packet["release_run_id"]), "release-attempt": str(packet["release_run_attempt"]),
        "source-sha": packet["source_sha"], "purpose": "isolated-restore-rehearsal"}.items()),
        "refusing cleanup of preexisting or mismatched SQL ownership labels")
    created = stamp(clone.get("createTime"))
    require(packet["issued_at_unix"] <= created <= packet["expires_at_unix"], "clone was not created under this authority")
    matches = [o for o in operations if o.get("operationType") == "CREATE" and o.get("targetId") == CLONE
               and o.get("targetProject") == PROJECT and o.get("user") == f"specimen-data-release@{PROJECT}.iam.gserviceaccount.com"
               and packet["issued_at_unix"] <= stamp(o.get("insertTime")) <= created + 60]
    require(len(matches) == 1 and re.fullmatch(r"[A-Za-z0-9_-]+", matches[0].get("name", "")), "unique native owned create operation required")
    return {"clone": CLONE, "source": SOURCE, "source_sha": packet["source_sha"],
            "run_id": packet["release_run_id"], "run_attempt": packet["release_run_attempt"],
            "create_operation": matches[0]["name"], "create_time": clone["createTime"],
            "expires_at_unix": min(packet["expires_at_unix"], packet.get("clone_expires_at_unix", packet["expires_at_unix"]), int(created) + 7200)}


def list_sql(google, resource, **params):
    result, seen = [], set()
    for _ in range(100):
        response = google.request("sql", "GET", resource, params=params)
        result.extend(response.get("items", []))
        cursor = response.get("nextPageToken")
        if not cursor:
            return result
        require(isinstance(cursor, str) and cursor not in seen, "native SQL pagination did not progress")
        seen.add(cursor); params["pageToken"] = cursor
    raise ValueError("native SQL inventory exceeded bounded pages")


def ensure_backup(google, backup_id, directory, *, retention=None, source=None):
    if retention is not None:
        from release_backup import ensure_finite_backup
        require(backup_id is None, "finite retention cannot adopt an existing backup")
        return ensure_finite_backup(google, directory, retention, source)
    resource = f"projects/{PROJECT}/instances/{SOURCE}/backupRuns"
    description = "specimen-first-ten-" + google.packet["pilot"]["manifest_sha256"]
    receipt_path = directory / "native-backup.json"
    if backup_id is None:
        require(not receipt_path.exists(), "backup operation already recorded; reconcile without replay")
        require(not any(b.get("description") == description for b in list_sql(google, resource)),
                "this cohort already has a native backup operation; bind its verified ID without recreating")
        # Write intent first. An ambiguous response is a retained liability, never
        # permission to send a second backup operation in this attempt.
        receipt = {"source": SOURCE, "run_id": google.packet["release_run_id"],
                   "run_attempt": google.packet["release_run_attempt"], "description": description,
                   "submitted_at_unix": int(time.time()), "outcome": "unknown"}
        receipt_path.write_text(json.dumps(receipt)); receipt_path.chmod(0o600)
        operation = google.request("sql", "POST", resource, body={"description": description, "location": "us-east4"})
        receipt["operation"] = operation.get("name")
        receipt_path.write_text(json.dumps(receipt))
        operation = wait_sql(google, operation, maximum_seconds=900)
        backup_id = operation.get("backupContext", {}).get("backupId")
        require(isinstance(backup_id, str) and re.fullmatch(r"[1-9][0-9]*", backup_id), "native backup operation lacks a bound backup ID")
    backup = google.request("sql", "GET", f"{resource}/{backup_id}")
    require(backup.get("id") == backup_id and backup.get("status") == "SUCCESSFUL"
            and backup.get("instance") == SOURCE, "successful native source backup required")
    if receipt_path.exists():
        receipt = strict_json(private_bytes(receipt_path))
        require(backup.get("description") == description and backup.get("type") == "ON_DEMAND", "native backup creation binding changed")
        receipt.update(backup_id=backup_id, outcome="successful")
        receipt_path.write_text(json.dumps(receipt))
    return backup_id


def sql_inventory(directory, instance, *, repair=False):
    target = directory / f"{instance}-{'repair' if repair else 'inventory'}.json"
    result = subprocess.run(["node", "scripts/ci/release_sql.mjs", "indexes" if repair else "inventory", instance, str(target)],
                            cwd=ROOT, capture_output=True, timeout=300)
    require(result.returncode == 0, "named IAM SQL verification failed; no database users/roles/passwords are created")
    return strict_json(private_bytes(target))


def wait_sql(google, operation, maximum_seconds=1800):
    name = operation.get("name", "")
    require(isinstance(name, str) and re.fullmatch(r"[a-zA-Z0-9_-]+", name), "invalid native SQL operation")
    identity = {key: operation[key] for key in ("name", "kind", "targetId", "targetProject", "operationType", "user", "insertTime")
                if key in operation}
    deadline = min(time.time() + maximum_seconds, google.packet["expires_at_unix"])
    while operation.get("status") != "DONE":
        require(time.time() + 5 < deadline, "native SQL operation deadline reached; cleanup and reconcile")
        time.sleep(5)
        previous_deadline = getattr(google, "sql_read_deadline", None)
        google.sql_read_deadline = deadline
        try:
            operation = google.request("sql", "GET", f"projects/{PROJECT}/operations/{name}")
        finally:
            google.sql_read_deadline = previous_deadline
        require(isinstance(operation, dict) and all(operation.get(key) == value for key, value in identity.items()),
                "native SQL operation changed scope, actor or creation provenance while polling")
        require(time.time() < deadline, "native SQL completion arrived after the original deadline")
    require(time.time() < deadline, "native SQL completion exceeded its fixed deadline")
    require("error" not in operation, "native SQL operation failed")
    return operation


def clone_body(source, recipe, run_id, *, run_attempt, source_sha):
    exact_keys(recipe, {"tier", "source_version", "source_edition", "source_disk_gb"}, "restore recipe")
    require(recipe["tier"] in {"db-f1-micro", "db-g1-small", "db-custom-1-3840", "db-custom-2-7680"},
            "restore target exceeds bounded compatible tier; stop for cost reconciliation")
    integer(recipe["source_disk_gb"], 1, 65536, "restore disk size")
    require(source.get("region") == "us-east4" and source.get("databaseVersion") == recipe["source_version"]
            and source.get("settings", {}).get("edition", "ENTERPRISE") == recipe["source_edition"] == "ENTERPRISE"
            and str(source.get("settings", {}).get("dataDiskSizeGb")) == str(recipe["source_disk_gb"]), "observed SQL settings differ from restore recipe")
    flags = source["settings"].get("databaseFlags", [])
    require(any(value == {"name": "cloudsql.iam_authentication", "value": "on"} for value in flags), "existing IAM database authentication required")
    return {"name": CLONE, "region": "us-east4", "databaseVersion": recipe["source_version"],
            "settings": {"tier": recipe["tier"], "edition": recipe["source_edition"], "availabilityType": "ZONAL",
                         "dataDiskSizeGb": str(recipe["source_disk_gb"]), "dataDiskType": "PD_SSD", "storageAutoResize": False,
                         "backupConfiguration": {"enabled": False, "pointInTimeRecoveryEnabled": False},
                         "ipConfiguration": {"ipv4Enabled": True, "sslMode": "ENCRYPTED_ONLY"},
                         "databaseFlags": flags, "userLabels": {"release-run": str(run_id), "release-attempt": str(run_attempt),
                                                               "source-sha": source_sha, "purpose": "isolated-restore-rehearsal"}}}


def validate_clone_ownership(clone, receipt, run_id):
    require(clone.get("name") == receipt.get("clone") == CLONE and receipt.get("run_id") == run_id
            and isinstance(receipt.get("create_time"), str) and receipt["create_time"] == clone.get("createTime")
            and clone.get("settings", {}).get("userLabels", {}).get("release-run") == str(run_id)
            and clone.get("settings", {}).get("userLabels", {}).get("purpose") == "isolated-restore-rehearsal",
            "refusing cleanup of preexisting or mismatched SQL resource")


def cleanup_rehearsal(google, directory):
    receipt_path = directory / "native-recovery.json"
    clone = google.request("sql", "GET", f"projects/{PROJECT}/instances/{CLONE}", missing=True)
    if clone is None:
        return
    operations = list_sql(google, f"projects/{PROJECT}/operations", instance=CLONE, maxResults=100)
    proof = creation_proof(clone, operations, google.packet)
    receipt = strict_json(private_bytes(receipt_path)) if receipt_path.exists() else {}
    if receipt.get("create_time"):
        validate_clone_ownership(clone, receipt, google.packet["release_run_id"])
    proof["expires_at_unix"] = min(proof["expires_at_unix"], receipt.get("expires_at_unix", proof["expires_at_unix"]))
    receipt.update(proof)
    receipt["cleanup_observed_at_unix"] = int(time.time())
    receipt_path.write_text(json.dumps(receipt)); receipt_path.chmod(0o600)
    creating = next(o for o in operations if o.get("name") == proof["create_operation"])
    deadline = time.time() + 600
    while creating.get("status") != "DONE":
        require(time.time() + 5 < deadline, "owned clone creation still pending; immediate cleanup reconciliation required")
        time.sleep(5)
        creating = google.request("sql", "GET", f"projects/{PROJECT}/operations/{proof['create_operation']}")
    clone = google.request("sql", "GET", f"projects/{PROJECT}/instances/{CLONE}", missing=True)
    if clone is None:
        return
    validate_clone_ownership(clone, receipt, google.packet["release_run_id"])
    # A disposal obligation survives expiry/supersession. The transport permits
    # this exception only for the exact owned clone DELETE, never another write.
    operation = google.cleanup_clone()
    deadline = time.time() + 600
    while operation.get("status") != "DONE":
        require(time.time() + 5 < deadline, "owned restore cleanup not confirmed; immediate reconciliation required")
        time.sleep(5)
        operation = google.request("sql", "GET", f"projects/{PROJECT}/operations/{operation['name']}")
    require("error" not in operation, "owned restore deletion failed; immediate reconciliation required")
    require(google.request("sql", "GET", f"projects/{PROJECT}/instances/{CLONE}", missing=True) is None, "restore clone still exists")
    receipt["deleted_at_unix"] = int(time.time())
    receipt["lifetime_seconds"] = max(0, int(time.time() - stamp(receipt["create_time"])))
    receipt["deadline_exceeded"] = time.time() > receipt["expires_at_unix"]
    receipt_path.write_text(json.dumps(receipt, sort_keys=True))


def rehearse(google, plan, directory):
    source = google.request("sql", "GET", f"projects/{PROJECT}/instances/{SOURCE}")
    require(source.get("region") == "us-east4" and source.get("settings", {}).get("settingsVersion") == plan["database_etag"],
            "source SQL resource changed or wrong region")
    require(time.time() + 1800 < min(google.packet["expires_at_unix"], plan["recovery"]["expires_at_unix"]),
            "insufficient remaining restore/verification/cleanup window")
    require(google.request("sql", "GET", f"projects/{PROJECT}/instances/{CLONE}", missing=True) is None,
            "rehearsal clone already exists; never adopt or overwrite it")
    body = clone_body(source, plan["recovery"]["recipe"], google.packet["release_run_id"],
                      run_attempt=google.packet["release_run_attempt"], source_sha=google.packet["source_sha"])
    before = sql_inventory(directory, SOURCE)
    if plan["schema_mode"] == "initialize_empty":
        require(before["rows"] == [], "automatic compatible initialization requires an empty existing database")
    else:
        verify_indexes(before)
    require(not (directory / "native-recovery.json").exists(), "rehearsal operation already recorded; reconcile without replay")
    from release_clone import acquire
    winner = acquire(google, plan, directory)
    backup_args = {"retention": plan["recovery"]["backup_retention"], "source": source} if "backup_retention" in plan["recovery"] else {}
    backup_id = winner.effect("clone-backup", lambda: ensure_backup(google, plan["recovery"]["backup_id"], directory, **backup_args))
    from release_backup import attach_proof
    backup_proof = {"backup_id": backup_id}
    attach_proof(backup_proof, plan, google.packet, directory)
    operation = winner.effect("clone-create", lambda: google.request("sql", "POST", f"projects/{PROJECT}/instances", body=body))
    # Retain creation operation before waiting, so interrupted insertion is not
    # mistaken for permission to submit another native restore.
    creation = {"clone": CLONE, "source": SOURCE, "backup_id": backup_id,
                "run_id": google.packet["release_run_id"], "run_attempt": google.packet["release_run_attempt"],
                "create_operation": operation["name"], "expires_at_unix": plan["recovery"]["expires_at_unix"]}
    creation.update(backup_proof)
    receipt_path = directory / "native-recovery.json"
    receipt_path.write_text(json.dumps(creation)); receipt_path.chmod(0o600)
    wait_sql(google, operation, maximum_seconds=900)
    clone = google.request("sql", "GET", f"projects/{PROJECT}/instances/{CLONE}")
    creation["create_time"] = clone["createTime"]
    receipt_path.write_text(json.dumps(creation))
    validate_clone_ownership(clone, creation, google.packet["release_run_id"])
    operation = winner.effect("clone-restore", lambda: google.request("sql", "POST", f"projects/{PROJECT}/instances/{CLONE}/restoreBackup", body={
        "restoreBackupContext": {"backupRunId": backup_id, "instanceId": SOURCE, "project": PROJECT}}))
    creation["restore_operation"] = operation["name"]
    receipt_path.write_text(json.dumps(creation))
    wait_sql(google, operation, maximum_seconds=900)
    restored = sql_inventory(directory, CLONE)
    compare_restore(before, restored)
    compare_restore(before, sql_inventory(directory, SOURCE))
    creation["native_restore_verified"] = True
    creation["inventory_sha256"] = hashlib.sha256(json.dumps(restored, sort_keys=True).encode()).hexdigest()
    receipt_path.write_text(json.dumps(creation))
    return before


def deploy(path, output):
    google = Google(path, "data")
    with stage("data.plan"):
        plan = validate_plan(read_bound_plan(path.parent / "plan.json", google.packet), google.packet)
    if plan["version"] == "data-initialization-inventory/v1":
        from release_initialize import inspect_catalog
        inspect_catalog(google, plan, path.parent, output)
        return
    if plan["version"] == "data-inventory/v1":
        inventory_catalog(google, plan, path.parent, output)
        return
    if plan["version"] == "data-initialize-missing/v1":
        from release_initialize import prepare_recovery
        prepare_recovery(google, plan, path.parent, output)
        return
    if plan["version"] != "data-apply/v1":
        verify_or_bootstrap(google, plan, output)
        return
    # There is no unimplemented maintenance switch. Reject any runtime writer
    # resource instead of accepting a human boolean that it is quiesced.
    for resource in ("services/specimen-api", "jobs/specimen-worker"):
        require(google.request("run", "GET", f"projects/{PROJECT}/locations/us-east4/{resource}", missing=True) is None,
                "runtime writers exist; reviewed maintenance mode is required before later data migrations")
    before = rehearse(google, plan, path.parent)
    apply_compatible(google, plan, path, output, before)


def verify_persistent_schema(schema):
    """A reconciled temporary service cannot establish durable data readiness."""
    datasources = schema.get("datasources")
    require(isinstance(datasources, list) and len(datasources) == 1
            and isinstance(datasources[0], dict) and set(datasources[0]) == {"postgresql"},
            "one persistent PostgreSQL datasource required")
    postgres = datasources[0]["postgresql"]
    require(isinstance(postgres, dict) and postgres.get("ephemeral", False) is False
            and postgres.get("database") == DATABASE and postgres.get("schema", "public") == "public"
            and postgres.get("cloudSql") == {
                "instance": f"projects/{PROJECT}/locations/us-east4/instances/{SOURCE}"},
            "SQL Connect has not confirmed the expected persistent database")
    before_deploy = set(postgres) & {"schemaValidation", "schemaMigration"}
    require((before_deploy == {"schemaValidation"} and postgres["schemaValidation"] in {"COMPATIBLE", "STRICT"})
            or (before_deploy == {"schemaMigration"} and postgres["schemaMigration"] == "MIGRATE_COMPATIBLE"),
            "persistent SQL Connect schema compatibility is unverified")


def apply_compatible(google, plan, path, output, before):
    schema, connector = data_bodies(plan)
    if plan["version"] == "data-initialize-missing/v1":
        from release_initialize import verify_initialization_schema
        verify_initialization_schema(google, plan)
    else:
        for body, key in ((schema, "schema_etag"), (connector, "connector_etag")):
            current = google.request("data", "GET", body["name"], missing=True)
            require((current is None and plan[key] is None) or current and current.get("etag") == plan[key], "deployed data revision changed")
    google.request("data", "PATCH", schema["name"], body=schema, params={"allowMissing": "true", "validateOnly": "true"})
    # Direct APIs never invoke CLI provisioning or change Cloud SQL capacity/IAM.
    google.wait("data", google.request("data", "PATCH", schema["name"], body=schema, params={"allowMissing": "true"}))
    sql_inventory(path.parent, SOURCE, repair=True)
    google.request("data", "PATCH", connector["name"], body=connector, params={"allowMissing": "true", "validateOnly": "true"})
    google.wait("data", google.request("data", "PATCH", connector["name"], body=connector, params={"allowMissing": "true"}))
    after = sql_inventory(path.parent, SOURCE, repair=True)
    verify_indexes(after)
    require(len(after["rows"]) == len(approved_tables()), "unexpected application table count after schema publication")
    if plan["version"] == "data-initialize-missing/v1":
        from release_initialize import native
        native(path.parent, SOURCE, "post", files=plan["initialization"]["files"], deadline=google.packet["expires_at_unix"])
    if plan["schema_mode"] == "validate_existing":
        require(before["rows"] == after["rows"] and before["sequences"] == after["sequences"], "data or sequence values changed during compatible publication")
    ruleset = publish_rules(google, plan["storage_release_etag"])
    observations = {role: google.request("data", "GET", body["name"]) for role, body in (("schema", schema), ("connector", connector))}
    for value in observations.values():
        require(value.get("reconciling", False) is False and value.get("etag"), "data did not finish reconciling")
    verify_persistent_schema(observations["schema"])
    bootstrap_receipt = None
    if plan["bootstrap"] is not None:
        from bootstrap_release import bootstrap
        bootstrap_receipt = bootstrap(google, plan["bootstrap"]["payload"], plan["bootstrap"]["sha256"],
                                      plan["bootstrap"].get("evidence_recipient"))
    cleanup_rehearsal(google, path.parent)
    native_raw = private_bytes(path.parent / "native-recovery.json")
    native = strict_json(native_raw)
    require(native.get("native_restore_verified") is True and native.get("deleted_at_unix")
            and native.get("deadline_exceeded") is False, "native restore or bounded cleanup remains unverified")
    output.write_text(json.dumps({"version": "data-schema-ready/v1", "source_sha": google.packet["source_sha"],
                                 "run_id": google.packet["release_run_id"], "run_attempt": google.packet["release_run_attempt"],
                                 "source_files": plan["source_files"], "schema_ready": True, "data_ready": False,
                                 "native_restore_verified": True, "restore_receipt": {
                                     "run_id": native["run_id"], "run_attempt": native["run_attempt"], "source_sha": native["source_sha"],
                                     "sha256": hashlib.sha256(native_raw).hexdigest()},
                                 "membership_bootstrapped": plan["bootstrap"] is not None,
                                 **({"bootstrap_receipt": bootstrap_receipt} if bootstrap_receipt
                                    and bootstrap_receipt.get("version") in FIRST_SCOPE_RECEIPTS else {}),
                                 **{role: {"name": value["name"], "etag": value["etag"]} for role, value in observations.items()},
                                 "storage_ruleset": ruleset, "release_accepted": False}, sort_keys=True) + "\n")


def publish_rules(google, expected):
    """Release the committed Storage rules as a new ruleset over the expected live ruleset (None: no release yet)."""
    release = google.request("rules", "GET", RULE_RELEASE, missing=True)
    require((release.get("rulesetName") if release else None) == expected, "Storage release changed")
    rules = google.request("rules", "POST", f"projects/{PROJECT}/rulesets", body={"source": committed_rules()})
    require(isinstance(rules, dict) and isinstance(rules.get("name"), str) and RULESET.fullmatch(rules["name"]), "invalid new ruleset")
    body = {"name": RULE_RELEASE, "rulesetName": rules["name"]}
    if release:
        google.request("rules", "PATCH", RULE_RELEASE, body={"release": body}, params={"updateMask": "ruleset_name"})
    else:
        google.request("rules", "POST", f"projects/{PROJECT}/releases", body=body)
    reread = google.request("rules", "GET", RULE_RELEASE)
    require(reread.get("rulesetName") == rules["name"], "Storage publication mismatch")
    return rules["name"]


def complete_initialization(path, receipt_path, output):
    from release_initialize import verified_handoff, native
    google = Google(path, "data")
    plan = validate_plan(read_bound_plan(path.parent / "plan.json", google.packet), google.packet)
    require(plan["version"] == "data-initialize-missing/v1", "initialization continuation requires its own phase")
    result = verified_handoff(receipt_path, google.packet, plan, initialized=True)
    for resource in ("services/specimen-api", "jobs/specimen-worker"):
        require(google.request("run", "GET", f"projects/{PROJECT}/locations/us-east4/{resource}", missing=True) is None,
                "writer appeared after initialization")
    source = google.request("sql", "GET", f"projects/{PROJECT}/instances/{SOURCE}")
    require(source.get("settings", {}).get("settingsVersion") == plan["database_etag"], "source capacity or configuration changed")
    for instance in (SOURCE, CLONE):
        observed = native(path.parent, instance, "post", files=plan["initialization"]["files"], deadline=google.packet["expires_at_unix"])
        require(observed["postconditions"] == result["targets"][instance]["native"]["postconditions"], "initialized ownership/privileges changed")
    recovery = result["recovery"]["native_recovery"]
    clone = google.request("sql", "GET", f"projects/{PROJECT}/instances/{CLONE}")
    validate_clone_ownership(clone, recovery, google.packet["release_run_id"])
    recovery_path = path.parent / "native-recovery.json"
    recovery_path.write_text(json.dumps(recovery)); recovery_path.chmod(0o600)
    before = sql_inventory(path.parent, SOURCE)
    require(before["rows"] == [] and before["sequences"] == [], "new initialized database is not empty")
    # Reuse exactly this workflow's one backup/restore. Never call rehearse again.
    apply_compatible(google, {**plan, "schema_mode": "initialize_empty"}, path, output, before)


def verify_schema_receipt(google, plan):
    from deploy_runtime import checked, verified_receipt_bytes
    binding = plan["schema_receipt"]
    with tempfile.TemporaryDirectory() as folder:
        checked(["gh", "run", "download", str(binding["run_id"]), "--repo", REPOSITORY,
                 "--name", f"data-ready-{binding['source_sha']}-{binding['run_attempt']}", "--dir", folder])
        path = Path(folder) / "data-ready.json"
        raw = verified_receipt_bytes(path, binding["sha256"], binding["source_sha"], "data-release.yml")
        receipt = strict_json(raw)
        require(receipt.get("version") == "data-schema-ready/v1" and receipt.get("schema_ready") is True
                and receipt.get("native_restore_verified") is True and receipt.get("source_files") == source_fingerprints()
                and all(receipt.get(k) == binding[k] for k in ("source_sha", "run_id", "run_attempt")),
                "schema readiness evidence is stale or incompatible with committed data sources")
        restore = exact_keys(receipt["restore_receipt"], {"source_sha", "sha256", "run_id", "run_attempt"}, "native restore receipt")
        digest(restore["sha256"], "native restore")
        require(re.fullmatch(r"[a-f0-9]{40}", restore["source_sha"]), "invalid native restore source")
        for key in ("run_id", "run_attempt"):
            integer(restore[key], 1, 2**53, key)
        checked(["gh", "run", "download", str(restore["run_id"]), "--repo", REPOSITORY,
                 "--name", f"native-recovery-{restore['source_sha']}-{restore['run_attempt']}", "--dir", folder])
        native_raw = (Path(folder) / "native-recovery.json").read_bytes()
        require(hashlib.sha256(native_raw).hexdigest() == restore["sha256"], "native restore proof digest mismatch")
        native = strict_json(native_raw)
        require(native.get("native_restore_verified") is True and native.get("deleted_at_unix")
                and native.get("deadline_exceeded") is False and native.get("clone") == CLONE and native.get("source") == SOURCE
                and all(native.get(k) == restore[k] for k in ("source_sha", "run_id", "run_attempt")),
                "successful native restore and owned-clone cleanup evidence required")
    for role, suffix in (("schema", "schemas/main"), ("connector", "connectors/specimen-server")):
        expected = receipt[role]
        require(expected.get("name") in {f"{PREFIX}/{suffix}", f"projects/{google.packet['identity']['project_number']}/locations/us-east4/services/specimen-digitization-service/{suffix}"},
                "unapproved deployed data resource")
        observed = google.request("data", "GET", expected["name"])
        require(observed.get("etag") == expected["etag"] and observed.get("reconciling", False) is False, "deployed data changed after signed receipt")
        if role == "schema":
            verify_persistent_schema(observed)
    rules = google.request("rules", "GET", RULE_RELEASE)
    require(rules.get("rulesetName") == receipt["storage_ruleset"], "deployed Storage rules changed")
    return receipt


def verify_or_bootstrap(google, plan, output):
    receipt = verify_schema_receipt(google, plan)
    if plan["version"] == "data-bootstrap/v1":
        from bootstrap_release import bootstrap
        bootstrap_receipt = bootstrap(google, plan["bootstrap"]["payload"], plan["bootstrap"]["sha256"],
                                      plan["bootstrap"].get("evidence_recipient"))
        if bootstrap_receipt and bootstrap_receipt.get("version") in FIRST_SCOPE_RECEIPTS:
            receipt["bootstrap_receipt"] = bootstrap_receipt
        receipt["membership_bootstrapped"] = True
    receipt.update(source_sha=google.packet["source_sha"], run_id=google.packet["release_run_id"],
                   run_attempt=google.packet["release_run_attempt"], data_ready=False, release_accepted=False)
    output.write_text(json.dumps(receipt, sort_keys=True) + "\n")


def files_by(source, key):
    """A source's files as {name: content} under the given name key; anything else fails closed."""
    entries = source.get("files") if isinstance(source, dict) else None
    require(isinstance(entries, list) and all(isinstance(entry, dict) and isinstance(entry.get(key), str)
                                              and isinstance(entry.get("content"), str) for entry in entries),
            "invalid source files")
    files = {entry[key]: entry["content"] for entry in entries}
    require(len(files) == len(entries), "duplicate source file")
    return files


def revision(resource):
    value = resource.get("etag") if isinstance(resource, dict) else None
    require(isinstance(value, str) and REVISION.fullmatch(value), "live resource lacks a public revision")
    return value


def live_rules(google):
    """The live Storage rules release's ruleset name and source files; no release reads as (None, None)."""
    release = google.request("rules", "GET", RULE_RELEASE, missing=True)
    if release is None:
        return None, None
    name = release.get("rulesetName") if isinstance(release, dict) else None
    require(isinstance(name, str) and RULESET.fullmatch(name), "invalid live Storage rules release")
    ruleset = google.request("rules", "GET", name)
    return name, files_by(ruleset.get("source") if isinstance(ruleset, dict) else None, "name")


def blocked(reason):
    """Print a fixed, value-free reason, since the command line's exit hides exception text, and return it."""
    print(f"Data release blocked: {reason}.")
    return ValueError(reason)


def require_database(google):
    """The SQL instance runs and the application database exists; both are read, never changed."""
    instance = google.request("sql", "GET", f"projects/{PROJECT}/instances/{SOURCE}")
    if not (isinstance(instance, dict) and instance.get("name") == SOURCE and instance.get("project") == PROJECT
            and instance.get("region") == "us-east4" and instance.get("state") == "RUNNABLE"):
        raise blocked("the SQL instance is not runnable")
    database = google.request("sql", "GET", f"projects/{PROJECT}/instances/{SOURCE}/databases/{DATABASE}", missing=True)
    if not (isinstance(database, dict) and database.get("name") == DATABASE and database.get("instance") == SOURCE
            and database.get("project") == PROJECT):
        raise blocked("the application database is missing")


def first_catalog(directory, source_sha):
    """The application database's summary, read through the Node connector as the release identity (4.3 step 1)."""
    target = directory / "first-catalog.json"
    result = subprocess.run(["node", "scripts/ci/release_sql.mjs", "summary", SOURCE, str(target)], cwd=ROOT,
                            env=dict(os.environ, RELEASE_GATE_SHA=source_sha), capture_output=True, timeout=60)
    if result.returncode != 0:
        raise blocked("the application database's catalog could not be read")
    return strict_json(private_bytes(target))


def run_artifacts(record, prefix):
    """This run's unexpired <prefix>-<commit>-<attempt> artifacts from every attempt so far, by attempt (actions: read)."""
    listing = gh_json(f"repos/{REPOSITORY}/actions/runs/{record['release_run_id']}/artifacts?per_page=100")
    items = listing.get("artifacts") if isinstance(listing, dict) else None
    require(isinstance(items, list) and listing.get("total_count") == len(items), "incomplete run artifact listing")
    found = {}
    for item in items:
        match = re.fullmatch(rf"{prefix}-{record['source_sha']}-([1-9][0-9]{{0,5}})", str(release_gate.field(item, "name")))
        if match and release_gate.field(item, "expired") is False and release_gate.field(item, "workflow_run", "id") == record["release_run_id"]:
            attempt = int(match.group(1))
            require(attempt not in found and attempt <= record["release_run_attempt"], "ambiguous run artifact")
            found[attempt] = item
    return found


def first_step(record, directory):
    """RELEASE.md 4.3 step 1: initialize a new, empty database; migrate after this run's own earlier initializer; else stop."""
    summary = first_catalog(directory, record["source_sha"])
    names = summary.get("extensions") if isinstance(summary, dict) else None
    roles = summary.get("roles") if isinstance(summary, dict) else None
    if not (isinstance(summary, dict) and set(summary) == {*COUNTS, "expected_database", "expected_actor", "extensions", "roles"}
            and summary["expected_database"] is True and summary["expected_actor"] is True
            and all(type(summary[key]) is int and 0 <= summary[key] <= 10**9 for key in COUNTS)
            and isinstance(names, list) and len(names) <= 100
            and all(isinstance(name, str) and EXTENSION.fullmatch(name) and name != "plpgsql" for name in names)
            and len(set(names)) == len(names) and isinstance(roles, list)
            and all(name in APPLICATION_ROLES.values() for name in roles) and len(set(roles)) == len(roles)):
        raise blocked("the application database's catalog summary is malformed")
    present = {role: name in roles for role, name in APPLICATION_ROLES.items()}
    print("Application database: " + ", ".join(f"{summary[key]} {key}" for key in COUNTS)
          + f", {len(names)} extension(s) besides plpgsql ({', '.join(names) or 'none'}); Data Connect roles: "
          + ", ".join(f"{role} {'present' if value else 'absent'}" for role, value in present.items()) + ".")
    if not any(present.values()) and not names and not any(summary[key] for key in COUNTS):
        return "initialize"
    if all(present.values()) and any(attempt < record["release_run_attempt"] for attempt in run_artifacts(record, "data-initializer")):
        return "migrate"
    raise blocked("the application database is neither empty nor initialized by this run; adopting it needs a ruling")


def deploy_released_data(path, output):
    """Release the data plane from a gate record (G11, RELEASE.md 4.2): read live state, never change it.

    initialize: the placeholder schema and no connector; the initialization jobs (T3c) continue. verify: the
    live schema, connector and Storage rules equal the merged files, the schema is persistent and both are
    reconciled. apply: anything else the additive-only gate admits; the apply itself fails closed until T3d.
    Every other combination asks to reconcile. Once a data gate record is admitted, every exit writes the
    receipt, which holds the phase and public resource facts only.
    """
    targets = os.environ.get("GITHUB_OUTPUT")
    require(targets and output is not None, "GitHub step output and receipt path required")
    google = Google(path, "data")
    record = google.packet
    require(release_gate.is_gate_record(record) and record.get("plane") == "data", "a data gate record is required")
    if os.environ.get("DATA_BOOTSTRAP_ARTIFACT_B64"):
        # T3e reads the artifact; until then this release never decodes, prints or writes its value.
        print("A bootstrap artifact is present; the bootstrap arrives with T3e, so this release leaves it unread.")
    facts = dict.fromkeys(("phase", "schema_etag", "schema_update_time", "connector_etag", "storage_ruleset"))

    def choose(phase):
        facts["phase"] = phase
        print(f"Data release phase: {phase}.")

    def publish():
        with open(targets, "a", encoding="utf-8") as handle:
            handle.write(f"phase={facts['phase']}\n")

    try:
        schema = google.request("data", "GET", SCHEMA_NAME)
        etag, updated = revision(schema), schema.get("updateTime")
        stamp(updated)
        facts.update(schema_etag=etag, schema_update_time=updated)
        connector = google.request("data", "GET", CONNECTOR_NAME, missing=True)
        if connector is not None:
            facts["connector_etag"] = revision(connector)
        facts["storage_ruleset"], rules = live_rules(google)
        require_database(google)
        live_schema, live_connector = schema_gate.live_sources(schema, connector)
        if schema.get("reconciling", False) is not False:
            raise blocked("the live schema is still reconciling; reconcile it, then re-run this release")
        if not live_schema and connector is None:
            choose("initialize")
            publish()
            step = first_step(record, path.parent)
            print(f"First initialization step: {step}.")
            with open(targets, "a", encoding="utf-8") as handle:
                handle.write(f"init_step={step}\n")
            return
        if not live_schema or connector is None:
            raise blocked("the live schema and connector disagree; reconcile them, then re-run this release")
        merged_schema, merged_connector = (files_by(committed_source(folder), "path")
                                           for folder in ("dataconnect/schema", "dataconnect/connector"))
        if (live_schema, live_connector, rules) == (merged_schema, merged_connector, files_by(committed_rules(), "name")):
            choose("verify")
            verify_persistent_schema(schema)
            if connector.get("reconciling", False) is not False:
                raise blocked("the live connector is still reconciling; reconcile it, then re-run this release")
            publish()
            return
        choose("apply")
        publish()
        refusals = schema_gate.check_additive(live_schema, merged_schema, live_connector, merged_connector)
        if refusals:
            # Each line names a table, field or operation and the rule, never a value (RELEASE.md 4.1).
            print("\n".join(f"Refused: {line}" for line in refusals))
            raise blocked(f"the additive-only gate refused {len(refusals)} change(s)")
        raise blocked("the additive apply arrives with T3d; this phase fails closed until then")
    finally:
        output.write_text(json.dumps({"version": "data-released/v1", "source_sha": record["source_sha"],
                                      "run_id": record["release_run_id"], "run_attempt": record["release_run_attempt"],
                                      **facts}, sort_keys=True) + "\n")


class _Refused(ValueError):
    """A diff statement's fixed refusal reason."""


def migration_statement(sql, relaxed):
    """One diff statement's (kind, refusal); no refusal only for one statement of an allowed kind (RELEASE.md 4.3 step 3).
    Both are fixed text, never the statement's. relaxed: the (table, column) pairs whose NOT NULL may drop."""
    tokens = [(m.lastgroup, m.group()) for m in SQL_TOKEN.finditer(sql if isinstance(sql, str) else "") if m.lastgroup != "space"]
    words = []
    for token, text in tokens[:3]:
        if token != "word":
            break
        words.append(text.upper())
    kind = next((" ".join(words[:n]) for n in (3, 2, 1) if " ".join(words[:n]) in KINDS), "other")
    if not isinstance(sql, str) or not 0 < len(sql) <= 65536 or "\\" in sql or any(k == "other" for k, _ in tokens):
        return kind, "an unsupported character"
    if any(k == "operator" and ("--" in text or "/*" in text or "*/" in text) for k, text in tokens):
        return kind, "a comment"
    tokens = tokens[:-1] if tokens[-1:] == [("punct", ";")] else tokens
    if ("punct", ";") in tokens:
        return kind, "more than one statement"
    depth = 0
    for token in tokens:
        depth += {("punct", "("): 1, ("punct", ")"): -1}.get(token, 0)
        if depth < 0:
            break
    if depth:
        return kind, "unbalanced parentheses"
    try:
        return kind, None if _allowed(tokens, relaxed) else "not an allowed kind"
    except _Refused as refusal:
        return kind, str(refusal)


def _allowed(t, relaxed):
    """The allowed kinds over one statement's tokens: create table or view, create [unique] index, and alter table
    actions that add a column, add a unique or foreign key constraint, or drop NOT NULL on a relaxed column."""
    def word(at, *words):
        return at + len(words) if all(at + i < len(t) and t[at + i][0] == "word" and t[at + i][1].upper() == value
                                      for i, value in enumerate(words)) else None

    def name(at):
        kind, text = t[at] if at < len(t) else ("end", "")
        if kind not in ("word", "ident"):
            raise _Refused("not an allowed kind")
        return (text.lower() if kind == "word" else text[1:-1].replace('""', '"')), at + 1

    def table(at):
        value, at = name(at)
        if t[at:at + 1] == [("punct", ".")]:
            if value != "public":
                raise _Refused("outside the public schema")
            value, at = name(at + 1)
        return value, at

    def close(at):
        depth = 0
        for index in range(at, len(t)):
            depth += {("punct", "("): 1, ("punct", ")"): -1}.get(t[index], 0)
            if not depth:
                return index
        return -1

    if (at := word(0, "CREATE", "TABLE")) is not None:
        _, at = table(word(at, "IF", "NOT", "EXISTS") or at)
        return t[at:at + 1] == [("punct", "(")] and close(at) == len(t) - 1
    if (at := word(0, "CREATE", "VIEW")) is not None:
        _, at = table(at)
        at = close(at) + 1 if t[at:at + 1] == [("punct", "(")] else at
        return word(at, "AS") is not None and any(word(at + 1, key) is not None for key in ("SELECT", "WITH", "VALUES"))
    if (at := word(0, "CREATE", "INDEX") or word(0, "CREATE", "UNIQUE", "INDEX")) is not None:
        at = word(at, "IF", "NOT", "EXISTS") or at
        if word(at, "CONCURRENTLY") is not None or (at := word(name(at)[1], "ON")) is None:
            return False
        _, at = table(at)
        return t[at:at + 1] == [("punct", "(")] or word(at, "USING") is not None
    if (at := word(0, "ALTER", "TABLE")) is None:
        return False
    relation, at = table(at)
    starts, depth = [at], 0
    for index in range(at, len(t)):
        depth += {("punct", "("): 1, ("punct", ")"): -1}.get(t[index], 0)
        if t[index] == ("punct", ",") and not depth:
            starts.append(index + 1)
    for start, end in zip(starts, [index - 1 for index in starts[1:]] + [len(t)]):
        if (at := word(start, "ADD", "COLUMN")) is not None:
            allowed = name(word(at, "IF", "NOT", "EXISTS") or at)[1] < end
        elif (at := word(start, "ADD", "CONSTRAINT")) is not None:
            at = name(at)[1]
            allowed = word(at, "UNIQUE") is not None or word(at, "FOREIGN", "KEY") is not None
        elif (at := word(start, "ALTER", "COLUMN")) is not None:
            column, at = name(at)
            allowed = word(at, "DROP", "NOT", "NULL") == end
            if allowed and (relation, column) not in relaxed:
                raise _Refused("DROP NOT NULL outside the schema gate's named relaxations")
        else:
            allowed = False
        if not allowed:
            return False
    return True


def relaxations():
    """The schema gate's NOT NULL relaxations, {(Type, field): reason}. Every migration caller reads them here, so
    rebasing onto the gate's reading of the data contract (schema_gate.read_relaxations()) changes this line alone."""
    return schema_gate.NAMED_RELAXATIONS


def migration_plan(google, body, relaxed):
    """RELEASE.md 4.3 step 3: the statements of Data Connect's SQL diff, from a validate-only COMPATIBLE update of the
    merged schema; none when the database is already compatible. It reads the shape firebase-tools 15.8.0 reads
    (lib/dataconnect/errors.js 10-41, schemaMigration.js 56-81): a 400 whose error.details hold one
    IncompatibleSqlSchemaError, {diffs: [{sql, description, destructive}], destructive}, and a PreconditionFailure whose
    violations are INCOMPATIBLE_SCHEMA. INACCESSIBLE_SCHEMA lists the whole expected schema, not a diff. Unless every
    statement is allowed none runs, and the log names each refused one by its kind alone. relaxed: the merged
    schema's (table, column) pairs whose NOT NULL may drop, the same set the plan hands release_sql.mjs."""
    try:
        google.request("data", "PATCH", SCHEMA_NAME, body=body, params={"allowMissing": "true", "validateOnly": "true"}, diff=True)
        return []
    except HTTPFailure as failure:
        answer = getattr(failure, "body", None)
        if failure.http_status != 400 or answer is None:
            raise
    details = answer.get("error", {}).get("details") if isinstance(answer, dict) and isinstance(answer.get("error"), dict) else []
    details = [detail for detail in details if isinstance(detail, dict)] if isinstance(details, list) else []
    found = [detail for detail in details if "IncompatibleSqlSchemaError" in str(detail.get("@type"))]
    violations = [violation.get("type") if isinstance(violation, dict) else None
                  for detail in details if "google.rpc.PreconditionFailure" in str(detail.get("@type"))
                  for violation in (detail.get("violations") if isinstance(detail.get("violations"), list) else [None])]
    if len(found) != 1 or set(violations) != {"INCOMPATIBLE_SCHEMA"}:
        raise blocked("Data Connect did not answer with a SQL diff for this database")
    diffs = found[0].get("diffs")
    if not (set(found[0]) <= {"@type", "diffs", "destructive"} and type(found[0].get("destructive", False)) is bool
            and isinstance(diffs, list) and 0 < len(diffs) <= 1000 and all(
                isinstance(diff, dict) and set(diff) <= {"sql", "description", "destructive"} and isinstance(diff.get("sql"), str)
                and isinstance(diff.get("description", ""), str) and type(diff.get("destructive", False)) is bool for diff in diffs)):
        raise blocked("Data Connect's SQL diff is malformed")
    if found[0].get("destructive", False):
        raise blocked("Data Connect marked the SQL diff destructive")
    kinds, refusals = {}, []
    for at, diff in enumerate(diffs, 1):
        kind, reason = migration_statement(diff["sql"], relaxed)
        reason = "marked destructive" if diff.get("destructive", False) else reason
        kinds[kind] = kinds.get(kind, 0) + 1
        if reason:
            refusals.append(f"Refused: diff statement {at} of {len(diffs)} ({kind}): {reason}.")
    if refusals:
        print("\n".join(refusals))
        raise blocked(f"the migration refused {len(refusals)} of {len(diffs)} statement(s)")
    print("Migration: " + ", ".join(f"{count} {kind}" for kind, count in sorted(kinds.items())) + ".")
    return [diff["sql"] for diff in diffs]


def initializer_receipt(record):
    """This run's one attested data-initializer receipt, verified as disposal verifies the intent (RELEASE.md 4.3)."""
    from deploy_runtime import checked, verified_receipt_bytes
    receipts = run_artifacts(record, "data-initializer")
    if len(receipts) != 1:
        raise blocked("this run's attested initializer receipt is missing or ambiguous")
    (attempt,) = receipts
    with tempfile.TemporaryDirectory() as folder:
        checked(["gh", "run", "download", str(record["release_run_id"]), "--repo", REPOSITORY,
                 "--name", f"data-initializer-{record['source_sha']}-{attempt}", "--dir", folder])
        path = Path(folder) / "data-initializer.json"
        receipt = strict_json(verified_receipt_bytes(path, hashlib.sha256(path.read_bytes()).hexdigest(),
                                                     record["source_sha"], "data-release.yml"))
    expected = {"version": "data-initializer/v1", "source_sha": record["source_sha"], "run_id": record["release_run_id"],
                "run_attempt": attempt, "instance": SOURCE, "database": DATABASE}
    if not (isinstance(receipt, dict) and set(receipt) == {*expected, "postconditions_sha256"}
            and all(receipt[key] == value for key, value in expected.items())
            and isinstance(receipt["postconditions_sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", receipt["postconditions_sha256"])):
        raise blocked("this run's initializer receipt does not match its artifact")
    return receipt


def gate_sql(mode, directory, source_sha, *inputs):
    """One release_sql.mjs mode as specimen-data-release for the admitted gate record's commit; None when it fails."""
    target = directory / f"{SOURCE}-{mode}.json"
    result = subprocess.run(["node", "scripts/ci/release_sql.mjs", mode, SOURCE, str(target), *map(str, inputs)], cwd=ROOT,
                            env=dict(os.environ, RELEASE_GATE_SHA=source_sha), capture_output=True, timeout=300)
    return strict_json(private_bytes(target)) if result.returncode == 0 else None


def migrate_initialized(google, directory, output):
    """RELEASE.md 4.3 steps 3 to 5 on the gate path, as specimen-data-release. After this run's attested initializer, its
    exact postconditions and its principal's absence: Data Connect's diff runs client-side as the owner role in one
    transaction, then the schema (COMPATIBLE, on the live etag), the supplemental indexes, the connector and the Storage
    rules are released, and the catalog is checked. Every exit writes the data-initialized/v1 receipt, public facts only."""
    import release_initialize as initializer
    record = google.packet
    require(google.plane == "data" and release_gate.is_gate_record(record), "a data gate record is required")
    facts = dict.fromkeys(("schema_etag", "schema_update_time", "connector_etag", "storage_ruleset", "tables", "views"))
    try:
        require_database(google)
        receipt = initializer_receipt(record)
        post = initializer.native(directory, SOURCE, "post", files=initializer.fingerprints(), deadline=record["expires_at_unix"],
                                  gate_sha=record["source_sha"])["postconditions"]
        if initializer.sha(post) != receipt["postconditions_sha256"]:
            raise blocked("the database's postconditions changed since this run's initializer")
        if initializer.own_principal(google) is not None:
            raise blocked("the initializer's SQL principal still exists; dispose of it, then re-run")
        merged = [files_by(committed_source(folder), "path") for folder in ("dataconnect/schema", "dataconnect/connector")]
        tables, views, relaxed = schema_gate.declared_sql(merged[0], relaxations())
        schema, connector = google.request("data", "GET", SCHEMA_NAME), google.request("data", "GET", CONNECTOR_NAME, missing=True)
        live = schema_gate.live_sources(schema, connector)
        if schema.get("reconciling", False) is not False or live[0] not in ({}, merged[0]) or connector and live[1] != merged[1]:
            raise blocked("the live schema or connector is neither the placeholder nor the merged files; reconcile them")
        ruleset = (google.request("rules", "GET", RULE_RELEASE, missing=True) or {}).get("rulesetName")
        body, connector_body = data_bodies({"schema_mode": "validate_existing", "schema_etag": revision(schema),
                                            "connector_etag": connector and revision(connector)})
        statements = migration_plan(google, body, relaxed)
        if statements:
            # Node re-checks every statement against the same relaxed pairs, as sorted table.column names.
            plan = directory / "migration.json"
            with os.fdopen(os.open(plan, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600), "w") as handle:
                json.dump({"version": "data-migration/v1", "source_sha": record["source_sha"], "statements": statements,
                           "relaxed": sorted(f"{table}.{column}" for table, column in relaxed)}, handle)
            if gate_sql("migrate", directory, record["source_sha"], plan) != {
                    "version": "data-migration/v1", "statements": len(statements), "committed": True}:
                raise blocked("the migration transaction failed and rolled back; re-run once the database is idle")
        google.wait("data", google.request("data", "PATCH", SCHEMA_NAME, body=body, params={"allowMissing": "true"}))
        inventory = gate_sql("indexes", directory, record["source_sha"])
        if inventory is None:
            raise blocked("the supplemental indexes could not be created as the owner role")
        verify_indexes(inventory)
        google.request("data", "PATCH", CONNECTOR_NAME, body=connector_body, params={"allowMissing": "true", "validateOnly": "true"})
        google.wait("data", google.request("data", "PATCH", CONNECTOR_NAME, body=connector_body, params={"allowMissing": "true"}))
        facts["storage_ruleset"] = publish_rules(google, ruleset)
        schema, connector = (google.request("data", "GET", name) for name in (SCHEMA_NAME, CONNECTOR_NAME))
        if schema.get("reconciling", False) is not False or connector.get("reconciling", False) is not False:
            raise blocked("the schema or connector is still reconciling; re-run this job")
        verify_persistent_schema(schema)
        require(schema_gate.live_sources(schema, connector) == tuple(merged), "released data sources differ from the merged files")
        stamp(schema.get("updateTime"))
        facts.update(schema_etag=revision(schema), schema_update_time=schema["updateTime"], connector_etag=revision(connector))
        catalog = gate_sql("migrated", directory, record["source_sha"])
        if not (isinstance(catalog, dict) and catalog.get("expected_database") is True and catalog.get("expected_actor") is True
                and all(isinstance(catalog.get(key), list) for key in ("tables", "views", "owners", "extensions"))):
            raise blocked("the migrated catalog could not be read")
        if sorted(catalog["tables"]) != sorted(f"public.{name}" for name in tables):
            raise blocked("the catalog's tables differ from the merged schema's")
        if sorted(catalog["views"]) != sorted(f"public.{name}" for name in views):
            raise blocked("the catalog's views differ from the merged schema's")
        if catalog["owners"] != [OWNER]:
            raise blocked("a relation is not owned by the owner role")
        if catalog["extensions"] != ["plpgsql", "uuid-ossp"]:
            raise blocked("the extensions are not exactly plpgsql and uuid-ossp")
        if initializer.sha(catalog.get("postconditions")) != receipt["postconditions_sha256"]:
            raise blocked("the database's postconditions changed since this run's initializer")
        facts.update(tables=len(tables), views=len(views))
    finally:
        output.write_text(json.dumps({"version": "data-initialized/v1", "phase": "initialize", "source_sha": record["source_sha"],
                                      "run_id": record["release_run_id"], "run_attempt": record["release_run_attempt"],
                                      **facts}, sort_keys=True) + "\n")


@stage("data.receipt")
def emit_result_digest(path):
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as handle:
        handle.write("receipt_sha256=" + hashlib.sha256(path.read_bytes()).hexdigest() + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare-inputs", action="store_true")
    action.add_argument("--admit", action="store_true")
    action.add_argument("--deploy", action="store_true")
    action.add_argument("--cleanup", action="store_true")
    action.add_argument("--prepare-cleanup", action="store_true")
    action.add_argument("--prepare-initialization", action="store_true")
    action.add_argument("--prepare-initializer-intents", action="store_true")
    action.add_argument("--prepare-clone-intent", action="store_true")
    action.add_argument("--initialize", action="store_true")
    action.add_argument("--complete-initialization", action="store_true")
    action.add_argument("--dispose-initializer", action="store_true")
    action.add_argument("--migrate", action="store_true")
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.prepare_inputs or args.prepare_initialization:
            with stage("data.inputs"):
                materialize_inputs(args.packet.parent, dict(os.environ))
        if args.prepare_cleanup:
            packet = cleanup_packet(args.packet, dict(os.environ))
            with Path(os.environ["GITHUB_OUTPUT"]).open("a") as handle:
                handle.write(f"provider={packet['identity']['provider']}\n")
            args.packet.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            return
        if args.cleanup:
            cleanup_rehearsal(Google(args.packet, "data", cleanup=True), args.packet.parent)
            return
        if args.dispose_initializer and args.receipt is not None:
            from release_initialize import verified_disposal_inputs, dispose_initializer_target
            google = Google(args.packet, "data", cleanup=True)
            recovery, journals = verified_disposal_inputs(google.packet, args.receipt, args.packet.parent)
            failures = []
            for instance in (SOURCE, CLONE):
                try:
                    dispose_initializer_target(google, instance, recovery, journals, args.packet.parent)
                except (ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
                    failures.append(type(error).__name__)
            require(not failures, "one or more temporary principal disposals remain unconfirmed")
            return
        plane = "data-initialization" if args.prepare_initialization or args.initialize or args.prepare_initializer_intents else "data"
        with stage("data.admission"):
            packet = admit(args.packet, plane)
            gate = release_gate.is_gate_record(packet)
            # G11: a gate record replaces the envelope, its plan, --prepare-inputs and --receipt; release_gate.py
            # writes it, and only the release, initialize, dispose-initializer and migrate jobs read it (RELEASE.md 4.3).
            require(gate or not args.dispose_initializer, "signed recovery and creation journals required")
            require(gate or not args.migrate, "only a gate record migrates")
            require(not gate or args.receipt is None and (args.prepare_initializer_intents or args.dispose_initializer
                    or (args.deploy or args.initialize or args.migrate) and args.output is not None),
                    "a gate record releases only through its jobs")
        if gate:
            import release_initialize as initializer
            if args.deploy:
                deploy_released_data(args.packet, args.output)
            elif args.initialize:
                initializer.initialize_existing(Google(args.packet, plane), args.packet.parent, args.output)
            elif args.prepare_initializer_intents:
                initializer.prepare_owned_initializer(Google(args.packet, plane), args.packet.parent)
            elif args.migrate:
                migrate_initialized(Google(args.packet, plane), args.packet.parent, args.output)
            else:
                initializer.dispose_owned_initializer(Google(args.packet, plane), args.packet.parent)
            if args.deploy or args.initialize or args.migrate:
                emit_result_digest(args.output)
            return
        with stage("data.plan"):
            plan = validate_plan(read_bound_plan(args.packet.parent / "plan.json", packet), packet)
        if args.prepare_clone_intent:
            from release_clone import prepare_intent
            prepare_intent(args.packet, packet, plan)
            return
        if args.prepare_initialization or args.initialize or args.prepare_initializer_intents:
            from release_initialize import (verified_handoff, require_protected_initializer_environment, initialize_targets,
                prepare_initializer_intents, verified_disposal_inputs)
            require(plan["version"] == "data-initialize-missing/v1" and args.receipt is not None,
                    "initializer needs a verified preceding native restoration receipt")
            require(packet["identity"] == plan["initialization"]["identity"], "initializer identity differs from reviewed plan")
            require_protected_initializer_environment(plan)
            recovery = verified_handoff(args.receipt, packet, plan)
            if args.prepare_initializer_intents:
                prepare_initializer_intents(Google(args.packet, plane), plan, args.packet.parent, recovery)
            elif args.initialize:
                require(args.output is not None, "initialization output required")
                verified_recovery, journals = verified_disposal_inputs(packet, args.receipt, args.packet.parent)
                require(verified_recovery == recovery, "published recovery changed before effects")
                initialize_targets(Google(args.packet, plane), plan, args.packet.parent, recovery, args.output, prepared_intents=journals)
                emit_result_digest(args.output)
            else:
                with Path(os.environ["GITHUB_OUTPUT"]).open("a") as handle:
                    handle.write(f"provider={packet['identity']['provider']}\n")
            return
        if args.complete_initialization:
            require(args.output is not None and args.receipt is not None, "initialization continuation inputs required")
            try:
                complete_initialization(args.packet, args.receipt, args.output)
                emit_result_digest(args.output)
            finally:
                cleanup_rehearsal(Google(args.packet, "data", cleanup=True), args.packet.parent)
            return
        if args.deploy:
            require(args.output is not None, "output required")
            try:
                deploy(args.packet, args.output)
                emit_result_digest(args.output)
            finally:
                if plan["version"] == "data-apply/v1":
                    cleanup_rehearsal(Google(args.packet, "data", cleanup=True), args.packet.parent)
        else:
            with Path(os.environ["GITHUB_OUTPUT"]).open("a") as handle:
                handle.write(f"provider={packet['identity']['provider']}\n")
                handle.write("cleanup_permit=" + json.dumps(cleanup_permit(packet, plan.get("recovery", {}).get("expires_at_unix")), separators=(",", ":")) + "\n")
                handle.write("phase=" + plan["version"] + "\n")
            print("Protected data admission passed; native recovery and application remain separate gates.")
    except Exception as exc:
        raise SystemExit(public_failure(exc)) from None


if __name__ == "__main__":
    main()
