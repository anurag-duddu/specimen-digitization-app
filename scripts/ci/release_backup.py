"""Optional finite retention for one new protected-workflow source backup."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
import re
import time

from release_admission import digest, exact_keys, integer, private_bytes, require, strict_json
from release_context import PROJECT

SOURCE = "specimen-digitization-instance"
SOURCE_RESOURCE = f"projects/{PROJECT}/instances/{SOURCE}"
RUNS = SOURCE_RESOURCE + "/backupRuns"
MAX_SECONDS = 172 * 3600
MAX_BYTES = 10 * 1024**3


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def timestamp(value):
    require(isinstance(value, str) and re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})", value), "native UTC timestamp required")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def utc(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")


def validate_retention(retention, packet, *, now, restore_expiry=None, disk_gb=None):
    exact_keys(retention, {"expires_at_unix", "max_chargeable_bytes"}, "finite backup retention")
    integer(retention["expires_at_unix"], 1, 2**53, "backup expiry")
    integer(retention["max_chargeable_bytes"], 1, MAX_BYTES, "maximum backup chargeable bytes")
    require(packet["issued_at_unix"] <= now < packet["expires_at_unix"], "backup authority expired")
    require(max(now, packet["expires_at_unix"], restore_expiry or 0) < retention["expires_at_unix"]
            <= packet["issued_at_unix"] + MAX_SECONDS, "finite backup expiry does not cover recovery or exceeds 172 hours")
    if disk_gb is not None:
        integer(disk_gb, 1, 10, "finite backup source disk GiB")
        require(disk_gb * 1024**3 <= retention["max_chargeable_bytes"], "source disk exceeds reserved backup bytes")
    return retention


def native_bytes(value, maximum):
    require(isinstance(value, str) and re.fullmatch(r"0|[1-9][0-9]*", value), "native backup byte count required")
    result = int(value)
    require(result <= maximum, "native backup exceeds reserved maximum chargeable bytes")
    return result


def backup_name(value):
    require(isinstance(value, str) and re.fullmatch(
        rf"projects/{PROJECT}/backups/[A-Za-z0-9_-]{{1,200}}", value), "original project backup resource required")
    return value


def save(path, value, *, create=False):
    flags = os.O_WRONLY | os.O_NOFOLLOW | (os.O_CREAT | os.O_EXCL if create else os.O_TRUNC)
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        json.dump(value, handle, sort_keys=True)
        handle.flush(); os.fsync(handle.fileno())
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def inventory(google):
    result, seen = {}, set()
    params = {}
    for _ in range(100):
        value = google.request("sql", "GET", RUNS, params=params)
        require(isinstance(value, dict) and "error" not in value and "warning" not in value
                and "warnings" not in value and isinstance(value.get("items", []), list), "complete source backup inventory required")
        for item in value.get("items", []):
            require(isinstance(item, dict) and isinstance(item.get("id"), str)
                    and re.fullmatch(r"[1-9][0-9]*", item["id"]) and item["id"] not in result,
                    "duplicate or malformed source backup inventory")
            result[item["id"]] = item
        cursor = value.get("nextPageToken", "")
        require(isinstance(cursor, str), "native backup page token must be a string")
        if not cursor:
            return result
        require(cursor not in seen, "backup inventory pagination did not progress")
        seen.add(cursor)
        params = {"pageToken": cursor}
    raise ValueError("backup inventory exceeds bounded pages")


def wait_original(google, operation, submitted, record):
    require(isinstance(operation, dict) and operation.get("kind") == "sql#operation"
            and operation.get("targetProject") == PROJECT and operation.get("targetId") == SOURCE
            and operation.get("operationType") == "BACKUP_VOLUME"
            and operation.get("user") == f"specimen-data-release@{PROJECT}.iam.gserviceaccount.com",
            "backup operation source/type/actor differs")
    require(isinstance(operation.get("name"), str) and re.fullmatch(r"[A-Za-z0-9_-]{1,200}", operation["name"]), "original backup operation required")
    require(submitted <= timestamp(operation.get("insertTime")) <= time.time(), "backup operation predates original intent")
    identity = {k: operation[k] for k in ("name", "kind", "targetId", "targetProject", "operationType", "user", "insertTime")}
    context = operation.get("backupContext", {})
    require(isinstance(context, dict), "malformed original backup context")
    deadline = min(time.time() + 900, google.packet["expires_at_unix"])
    for _ in range(181):
        record(operation)
        require(time.time() < deadline, "backup operation deadline expired")
        require(all(operation.get(k) == v for k, v in identity.items())
                and isinstance(operation.get("backupContext", {}), dict)
                and all(operation.get("backupContext", {}).get(k) == v for k, v in context.items()),
                "original backup operation or mapping changed")
        require(operation.get("status") in {"PENDING", "RUNNING", "DONE"}
                and "error" not in operation and "apiWarning" not in operation, "backup operation failed or unknown")
        if operation["status"] == "DONE":
            return operation
        require(time.time() + 5 < deadline, "backup operation deadline reached")
        time.sleep(5)
        previous = getattr(google, "sql_read_deadline", None)
        google.sql_read_deadline = deadline
        try:
            operation = google.request("sql", "GET", f"projects/{PROJECT}/operations/{identity['name']}")
        finally:
            google.sql_read_deadline = previous
    raise ValueError("backup operation read bound exceeded")


def ensure_finite_backup(google, directory, retention, source):
    require(isinstance(source, dict) and source.get("name") == SOURCE and source.get("project") == PROJECT
            and source.get("region") == "us-east4" and source.get("state") == "RUNNABLE", "observed named source required")
    disk = source.get("settings", {}).get("dataDiskSizeGb")
    require(isinstance(disk, str) and re.fullmatch(r"[1-9][0-9]*", disk), "observed source disk bound required")
    validate_retention(retention, google.packet, now=time.time(), disk_gb=int(disk))
    description = "specimen-first-ten-" + google.packet["pilot"]["manifest_sha256"]
    receipt_path = directory / "native-backup.json"
    require(not os.path.lexists(receipt_path), "backup operation already recorded; reconcile without replay")
    before = inventory(google)
    require(not any(b.get("description") == description for b in before.values()), "this cohort already has a backup; never recreate")
    require(google.request("sql", "GET", SOURCE_RESOURCE) == source, "source changed before finite backup")
    submitted = int(time.time())
    validate_retention(retention, google.packet, now=time.time(), disk_gb=int(disk))
    body = {"instance": SOURCE, "description": description, "location": "us-east4", "expiryTime": utc(retention["expires_at_unix"])}
    receipt = {"source": SOURCE, "source_sha": google.packet["source_sha"], "run_id": google.packet["release_run_id"],
        "run_attempt": google.packet["release_run_attempt"], "description": description,
        "submitted_at_unix": submitted, "outcome": "unknown", "retention": retention,
        "request": {"method": "POST", "resource": f"projects/{PROJECT}/backups", "body": body}}
    save(receipt_path, receipt, create=True)
    validate_retention(retention, google.packet, now=time.time(), disk_gb=int(disk))
    operation = google.request("sql", "POST", f"projects/{PROJECT}/backups", body=body)
    receipt["original_operation"] = operation
    save(receipt_path, receipt)
    def record(value):
        receipt["last_operation"] = value
        save(receipt_path, receipt)
    final = wait_original(google, operation, submitted, record)
    context = final.get("backupContext", {})
    name = backup_name(context.get("name"))
    backup_id = context.get("backupId")
    require(isinstance(backup_id, str) and re.fullmatch(r"[1-9][0-9]*", backup_id)
            and backup_id not in before, "original operation lacks a new backupRun ID")
    run_resource = f"{RUNS}/{backup_id}"
    backup = google.request("sql", "GET", name)
    receipt["backup"] = backup
    save(receipt_path, receipt)
    require(backup.get("name") == name and backup.get("kind") == "sql#backup"
            and backup.get("state") == "SUCCESSFUL" and backup.get("type") == "ON_DEMAND"
            and backup.get("instance") == SOURCE and backup.get("description") == description
            and backup.get("location") == "us-east4" and backup.get("backupRun") == run_resource
            and "error" not in backup and not backup.get("instanceDeletionTime"), "native finite backup mapping/source differs")
    require(timestamp(backup.get("expiryTime")) == retention["expires_at_unix"], "native backup expiry differs or missing")
    charged = native_bytes(backup.get("maxChargeableBytes"), retention["max_chargeable_bytes"])
    run = google.request("sql", "GET", run_resource)
    receipt["backup_run"] = run
    save(receipt_path, receipt)
    require(run.get("id") == backup_id and run.get("kind") == "sql#backupRun" and run.get("status") == "SUCCESSFUL"
            and run.get("type") == "ON_DEMAND" and run.get("instance") == SOURCE and run.get("description") == description
            and run.get("location") == "us-east4" and "error" not in run, "native restore backupRun mapping differs")
    require(native_bytes(run.get("maxChargeableBytes"), retention["max_chargeable_bytes"]) == charged,
            "backup and backupRun chargeable bytes disagree")
    require(submitted <= timestamp(run.get("endTime")) <= time.time(), "new backupRun completion outside original intent")
    require(google.request("sql", "GET", SOURCE_RESOURCE) == source, "source changed during finite backup")
    after = inventory(google)
    require(after.get(backup_id) == run and {k: v for k, v in after.items() if k != backup_id} == before,
            "existing source backups changed or unexpected new backup")
    require(time.time() < google.packet["expires_at_unix"], "finite backup readback exceeded authority")
    proof = {"backup_name": name, "backup_run": run_resource, "backup_id": backup_id,
        "expires_at_unix": retention["expires_at_unix"], "max_chargeable_bytes": charged,
        "original_operation": operation["name"], "source_sha256": sha(source), "backup_sha256": sha(backup),
        "backup_run_sha256": sha(run), "observed_at_unix": int(time.time())}
    receipt.update(backup_id=backup_id, outcome="successful", retention_proof=proof)
    save(receipt_path, receipt)
    return backup_id


def validate_proof(proof, retention, backup_id, packet):
    exact_keys(proof, {"backup_name", "backup_run", "backup_id", "expires_at_unix", "max_chargeable_bytes",
        "original_operation", "source_sha256", "backup_sha256", "backup_run_sha256", "observed_at_unix"}, "native finite backup proof")
    backup_name(proof["backup_name"])
    require(proof["backup_id"] == backup_id and proof["backup_run"] == f"{RUNS}/{backup_id}"
            and proof["expires_at_unix"] == retention["expires_at_unix"], "finite proof backup ID or expiry differs")
    integer(proof["max_chargeable_bytes"], 0, retention["max_chargeable_bytes"], "observed chargeable backup bytes")
    integer(proof["observed_at_unix"], packet["issued_at_unix"], packet["expires_at_unix"] - 1, "backup observation time")
    require(isinstance(proof["original_operation"], str) and re.fullmatch(r"[A-Za-z0-9_-]{1,200}", proof["original_operation"]), "original backup operation proof missing")
    for key in ("source_sha256", "backup_sha256", "backup_run_sha256"):
        digest(proof[key], key)
    return proof


def attach_proof(native, plan, packet, directory):
    if "backup_retention" in plan["recovery"]:
        receipt = strict_json(private_bytes(directory / "native-backup.json"))
        require(receipt.get("outcome") == "successful" and receipt.get("source") == SOURCE
                and receipt.get("source_sha") == packet["source_sha"]
                and receipt.get("run_id") == packet["release_run_id"]
                and receipt.get("run_attempt") == packet["release_run_attempt"]
                and receipt.get("retention") == plan["recovery"]["backup_retention"], "finite backup receipt missing or belongs to another attempt")
        native["backup_retention"] = validate_proof(receipt.get("retention_proof"),
            plan["recovery"]["backup_retention"], native["backup_id"], packet)
