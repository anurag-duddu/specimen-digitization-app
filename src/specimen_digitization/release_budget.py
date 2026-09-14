"""Fixed September 14 release amendment; legacy authority remains unchanged."""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, datetime, timezone
from uuid import UUID

APPROVAL_SHA256 = "3303d129e5fde28d828729cd5b034a7981968c5cbbbad882a05367a5c361df2a"  # pragma: allowlist secret (approval record digest)
PREDECESSOR_LEDGER_SHA256 = "4eabef12c337ced7379a26c3cda45ec7546802de8ba4f5f072071deadd5d7a6d"  # pragma: allowlist secret (ledger digest)
LEGACY_LIMIT_MICROS = 5_000_000
APPROVED_LIMIT_MICROS = 12_000_000


def require(ok, message):
    if not ok:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def strict_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate predecessor JSON key")
            result[key] = value
        return result
    def finite(value):
        number = float(value)
        require(math.isfinite(number), "nonfinite predecessor number")
        return number
    def reject(value):
        raise ValueError("nonfinite predecessor constant")
    return json.loads(raw, object_pairs_hook=unique, parse_float=finite, parse_constant=reject)


def retained_rows(previous, current, label):
    require(type(previous) is list and type(current) is list, f"{label} rows required")
    def index(rows):
        result = {}
        for row in rows:
            require(type(row) is dict and type(row.get("operation_id")) is str,
                    f"invalid {label} identity")
            ident = row["operation_id"]
            require(ident not in result, f"duplicate {label} identity")
            result[ident] = canonical(row)
        return result
    prior, now = index(previous), index(current)
    require(all(now.get(key) == value for key, value in prior.items()),
            f"original {label} liability changed or omitted")


def predecessor_ledger(ledger):
    """Verify exact retained bytes and unchanged original liabilities, without I/O."""
    require(type(ledger) is dict and ledger.get("version") == "release-cost-ledger/v3",
            "approved budget requires complete successor accounting")
    ref = ledger.get("predecessor")
    require(type(ref) is dict and set(ref) == {"sha256", "json"}, "predecessor ledger required")
    raw = ref["json"]
    require(type(raw) is str and 0 < len(raw.encode()) <= 1048576, "bounded predecessor bytes required")
    require(ref["sha256"] == PREDECESSOR_LEDGER_SHA256
            == hashlib.sha256(raw.encode()).hexdigest(), "original ledger pin changed")
    prior = strict_json(raw)
    require(type(prior) is dict and prior.get("version") == "release-cost-ledger/v2",
            "original accounting dialect changed")
    for key in ("currency", "manifest_sha256", "scope", "prior_uncertainty"):
        require(canonical(ledger.get(key)) == canonical(prior[key]), f"original {key} changed")
    for key in ("entries", "operator_entries"):
        retained_rows(prior[key], ledger.get(key), key)
    require(type(ledger.get("accounting")) is dict, "accounting anchor required")
    for key in ("accounting_start_unix", "coordinator_task", "manifest_sha256"):
        require(canonical(ledger["accounting"].get(key)) == canonical(prior["accounting"][key]),
                f"original accounting {key} changed")
    return prior


def amended_snapshot(ledger, snapshot):
    prior = predecessor_ledger(ledger)
    require(snapshot.get("schema") == "coordinator-cumulative-release-budget/v2"
            and snapshot.get("approval_sha256") == APPROVAL_SHA256,
            "new accounting approval required")
    anchor = prior["accounting"]
    require(snapshot.get("predecessor_snapshot_sha256") == anchor["snapshot_sha256"]
            == hashlib.sha256(anchor["snapshot_json"].encode()).hexdigest(),
            "original snapshot pin changed")
    original = strict_json(anchor["snapshot_json"])
    require(original["schema"] == "coordinator-cumulative-release-budget/v1"
            and type(original["limit_micros"]) is int
            and 0 < original["limit_micros"] <= LEGACY_LIMIT_MICROS, "legacy snapshot changed")
    for key in ("currency", "scope", "accounting_start_unix", "resets_allowed", "coordinator_task",
                "frozen_metadata_sha256", "prior_evidence", "actual_prior_total_micros",
                "available_for_further_workloads_micros"):
        require(canonical(snapshot.get(key)) == canonical(original[key]), f"original snapshot {key} changed")
    retained_rows(original["entries"], snapshot.get("entries"), "snapshot")


def exact_keys(value, fields, label):
    require(type(value) is dict and set(value) == fields, f"{label}: unexpected or missing fields")
    return value


def integer(value, minimum, maximum, label):
    require(type(value) is int and minimum <= value <= maximum, f"invalid {label}")


def digest(value, label):
    require(type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value), f"invalid {label}")


CATEGORIES = {"provider", "api", "worker", "sam", "build", "storage", "network",
              "restore", "identity", "secrets", "telemetry"}


def coordinator_liabilities(ledger, packet, seen):
    """Preserve pinned operator accounting; this is not a verified price bound."""
    anchor = exact_keys(ledger["accounting"], {"accounting_start_unix", "coordinator_task", "manifest_sha256",
                                             "snapshot_sha256", "snapshot_json"}, "accounting anchor")
    integer(anchor["accounting_start_unix"], 1, packet["issued_at_unix"], "accounting start")
    task = anchor["coordinator_task"]
    require(isinstance(task, str) and str(UUID(task)) == task, "invalid coordinator task UUID")
    require(task == packet["independent_review"]["coordinator_session"], "different accounting coordinator")
    require(anchor["manifest_sha256"] == ledger["manifest_sha256"], "accounting manifest mismatch")
    digest(anchor["snapshot_sha256"], "coordinator snapshot")
    raw = anchor["snapshot_json"]
    require(isinstance(raw, str) and 0 < len(raw.encode()) <= 65536, "invalid coordinator snapshot bytes")
    require(hashlib.sha256(raw.encode()).hexdigest() == anchor["snapshot_sha256"], "coordinator snapshot digest mismatch")
    amended = ledger["version"] == "release-cost-ledger/v3"
    maximum = APPROVED_LIMIT_MICROS if amended else 5000000
    extras = {"approval_sha256", "predecessor_snapshot_sha256"} if amended else set()
    snapshot = exact_keys(strict_json(raw), {"schema", "currency", "scope", "accounting_start_unix", "resets_allowed",
        "limit_micros", "coordinator_task", "frozen_metadata_sha256", "prior_evidence", "entries", "total_held_micros",
        "actual_prior_total_micros", "available_for_further_workloads_micros", "authorized_next_operation",
        "production_admission_compatible", "notes", "created_at"} | extras, "coordinator snapshot")
    if amended:
        amended_snapshot(ledger, snapshot)
    require(snapshot["schema"] == ("coordinator-cumulative-release-budget/v2" if amended
                                    else "coordinator-cumulative-release-budget/v1")
            and snapshot["currency"] == ledger["currency"] and snapshot["scope"] == ledger["scope"]
            and snapshot["coordinator_task"] == task and snapshot["resets_allowed"] is False,
            "accounting scope or reset mismatch")
    integer(snapshot["accounting_start_unix"], 1, packet["issued_at_unix"], "snapshot accounting start")
    require(snapshot["accounting_start_unix"] == anchor["accounting_start_unix"], "accounting start changed")
    integer(snapshot["limit_micros"], 1, maximum, "accounting limit")
    require(packet["budget"]["total_limit_micros"] <= snapshot["limit_micros"], "accounting limit increased")
    integer(snapshot["total_held_micros"], 1, snapshot["limit_micros"], "accounting total")
    digest(snapshot["frozen_metadata_sha256"], "frozen accounting metadata")
    prior_evidence = exact_keys(snapshot["prior_evidence"], {"path", "sha256"}, "prior evidence reference")
    digest(prior_evidence["sha256"], "prior evidence")
    require(isinstance(prior_evidence["path"], str) and 0 < len(prior_evidence["path"]) <= 4096,
            "invalid prior evidence reference")
    require(snapshot["actual_prior_total_micros"] is None
            and snapshot["available_for_further_workloads_micros"] is None
            and type(snapshot["production_admission_compatible"]) is bool,
            "prior uncertainty cannot be relabeled actual or available funds")
    require(isinstance(snapshot["notes"], list) and all(isinstance(note, str) for note in snapshot["notes"])
            and isinstance(snapshot["authorized_next_operation"], str), "invalid accounting annotations")
    require(isinstance(snapshot["created_at"], str), "invalid snapshot date")
    created = datetime.fromisoformat(snapshot["created_at"])
    require(created.tzinfo is not None and created.utcoffset().total_seconds() == 0
            and anchor["accounting_start_unix"] <= created.timestamp() <= packet["issued_at_unix"], "invalid snapshot date")
    require(isinstance(snapshot["entries"], list) and isinstance(ledger["operator_entries"], list), "operator accounting entries required")
    operators, prior, snapshot_seen, total = {}, None, set(), 0
    for row in snapshot["entries"]:
        require(isinstance(row, dict), "invalid coordinator entry")
        is_prior = "coverage" in row
        extra = {"coverage"} if is_prior else {"category", "plan_sha256"}
        exact_keys(row, {"operation_id", "owner_kind", "owner_task", "state", "held_micros"} | extra, "coordinator entry")
        ident = row["operation_id"]
        require(isinstance(ident, str) and 1 <= len(ident) <= 200 and ident not in snapshot_seen,
                "duplicate or invalid coordinator operation")
        snapshot_seen.add(ident)
        require(isinstance(row["owner_kind"], str) and row["owner_kind"] in {"coordinator", "operator"}
                and isinstance(row["owner_task"], str) and str(UUID(row["owner_task"])) == row["owner_task"]
                and (row["owner_kind"] != "coordinator" or row["owner_task"] == task), "unrecognized accounting owner")
        require(isinstance(row["state"], str) and row["state"] in {"settled", "unknown", "reserved"}, "invalid coordinator state")
        integer(row["held_micros"], 1 if row["state"] == "unknown" else 0, maximum, "coordinator liability")
        total += row["held_micros"]
        if is_prior:
            require(prior is None and row["state"] == "unknown" and row["owner_kind"] == "coordinator"
                    and isinstance(row["coverage"], str) and row["coverage"], "one explicit prior uncertainty required")
            prior = row
        else:
            require(isinstance(row["category"], str) and row["category"] in CATEGORIES, "unknown operator category")
            digest(row["plan_sha256"], "operator evidence")
            operators[ident] = row
    require(prior is not None and total == snapshot["total_held_micros"], "accounting holds omitted or total changed")
    start_day = datetime.fromtimestamp(anchor["accounting_start_unix"], timezone.utc).date().isoformat()
    issued_day = datetime.fromtimestamp(packet["issued_at_unix"], timezone.utc).date().isoformat()
    rows, observed = [], set()
    for entry in [*ledger["operator_entries"], ledger["prior_uncertainty"]]:
        is_prior = entry is ledger["prior_uncertainty"]
        exact_keys(entry, {"operation_id", "task_id", "state", "amount_micros", "day_utc", "evidence_sha256"}
                   | (set() if is_prior else {"category"}), "prior carry" if is_prior else "operator entry")
        ident = entry["operation_id"]
        require(isinstance(ident, str) and 1 <= len(ident) <= 200 and ident not in seen, "duplicate or invalid cost operation")
        seen.add(ident)
        expected = prior if is_prior else operators.get(ident)
        require(expected is not None and ident == expected["operation_id"], "operator or prior liability not in accounting snapshot")
        require(isinstance(entry["task_id"], str) and str(UUID(entry["task_id"])) == entry["task_id"]
                and entry["task_id"] == expected["owner_task"], "invalid operator task UUID")
        require(entry["state"] == expected["state"], "accounting liability state changed")
        integer(entry["amount_micros"], expected["held_micros"], maximum, "retained liability")
        digest(entry["evidence_sha256"], "retained operation evidence")
        require(entry["evidence_sha256"] == (prior_evidence["sha256"] if is_prior else expected["plan_sha256"]),
                "accounting evidence changed")
        day = entry["day_utc"]
        require(isinstance(day, str) and date.fromisoformat(day).isoformat() == day
                and start_day <= day <= issued_day, "invalid operator cost day")
        if is_prior:
            require(day == start_day, "prior carry must retain accounting start day")
        else:
            require(entry["category"] == expected["category"], "operator category changed")
            observed.add(ident)
            rows.append(entry)
    require(observed == set(operators), "operator liabilities omitted from accounting")
    return rows, ledger["prior_uncertainty"]
