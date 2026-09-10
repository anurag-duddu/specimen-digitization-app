#!/usr/bin/env python3
"""Source-bound predeployment admission, never a product-readiness verdict.

The environment's independently reviewed packet digest is the authorization
anchor. GitHub facts are fetched again without cloud credentials; packet claims
cannot stand in for merged-source or successful-check observations.
"""
from __future__ import annotations

import base64
from datetime import date, datetime, timezone
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time
from uuid import UUID
import zlib

from release_context import PLANES, PROJECT, REPOSITORY, validate_context
from validate_release_packet import CHECKS, DIGEST, SHA, exact_keys

CATEGORIES = {"provider", "api", "worker", "sam", "build", "storage", "network",
              "restore", "identity", "secrets", "telemetry"}


def require(value: object, message: str) -> None:
    if not value:
        raise ValueError(message)


def digest(value: object, label: str, pattern=DIGEST) -> None:
    require(isinstance(value, str) and pattern.fullmatch(value), f"invalid {label}")


def integer(value: object, minimum: int, maximum: int, label: str) -> None:
    require(type(value) is int and minimum <= value <= maximum, f"invalid {label}")


def validate_budget(b: object, manifest_sha: str) -> None:
    b = exact_keys(b, {"version", "currency", "scope", "manifest_sha256", "total_limit_micros",
                       "daily_limit_micros", "ledger_sha256", "resets_allowed", "reservations"}, "budget")
    require(b["version"] == "shared-release-reservations/v1" and b["currency"] == "USD", "unsupported budget")
    require(b["scope"] == "entire_first_ten_all_sessions_and_retries" and b["resets_allowed"] is False,
            "budget must be shared across every session and retry without a reset")
    require(b["manifest_sha256"] == manifest_sha, "budget is for a different cohort")
    integer(b["total_limit_micros"], 1, 5000000, "total budget")
    integer(b["daily_limit_micros"], 1, b["total_limit_micros"], "daily budget")
    digest(b["ledger_sha256"], "shared budget ledger")
    require(isinstance(b["reservations"], list), "budget reservations required")
    names, total = [], 0
    for entry in b["reservations"]:
        entry = exact_keys(entry, {"category", "ceiling_micros", "basis_sha256"}, "reservation")
        require(entry["category"] in CATEGORIES, "unknown budget category")
        integer(entry["ceiling_micros"], 0, 5000000, "reservation ceiling")
        digest(entry["basis_sha256"], "reservation basis")
        names.append(entry["category"])
        total += entry["ceiling_micros"]
    require(len(names) == len(CATEGORIES) and set(names) == CATEGORIES, "every cost category is required once")
    require(0 < total <= min(b["total_limit_micros"], b["daily_limit_micros"]), "shared reservations exceed budget")


def validate_admission(p: object, env: dict[str, str], observed: dict, *, now: float | None = None) -> dict:
    p = exact_keys(p, {"version", "plane", "repository", "project", "source_sha", "source_tree_sha",
                       "pull_request", "ci_run_id", "ci_run_attempt", "release_run_id", "release_run_attempt", "issued_at_unix", "expires_at_unix",
                       "authorization_sha256", "independent_review", "identity", "pilot", "budget",
                       "plan_sha256", "evidence"}, "authorization packet")
    require(p["version"] == "protected-release/v1", "unsupported authorization version")
    require(p["repository"] == REPOSITORY and p["project"] == PROJECT, "foreign authorization target")
    validate_context(env, p["plane"], p["source_sha"])
    digest(p["source_tree_sha"], "source tree", SHA)
    for field in ("pull_request", "ci_run_id", "ci_run_attempt", "release_run_id", "release_run_attempt"):
        integer(p[field], 1, 2**53, field)
    require(env.get("GITHUB_RUN_ID") == str(p["release_run_id"])
            and env.get("GITHUB_RUN_ATTEMPT") == str(p["release_run_attempt"]), "unapproved release run or attempt")
    now = time.time() if now is None else now
    integer(p["issued_at_unix"], 1, 2**53, "authorization issue time")
    integer(p["expires_at_unix"], 1, 2**53, "authorization deadline")
    require(p["issued_at_unix"] <= now < p["expires_at_unix"] <= p["issued_at_unix"] + 7200,
            "authorization expired, future-dated or exceeds two hours")
    for field in ("authorization_sha256", "plan_sha256"):
        digest(p[field], field)
    review = exact_keys(p["independent_review"], {"source_tree_sha", "reviewer_session", "coordinator_session", "report_sha256"}, "review")
    require(review["source_tree_sha"] == p["source_tree_sha"], "independent review is stale")
    require(all(isinstance(review[k], str) and 1 <= len(review[k]) <= 100 for k in ("reviewer_session", "coordinator_session"))
            and review["reviewer_session"] != review["coordinator_session"], "independent reviewer required")
    digest(review["report_sha256"], "independent review report")
    identity = exact_keys(p["identity"], {"project_number", "pool_id", "provider"}, "identity")
    require(isinstance(identity["project_number"], str) and re.fullmatch(r"[1-9][0-9]{0,19}", identity["project_number"]),
            "observed numeric cloud project identity required")
    require(isinstance(identity["pool_id"], str) and re.fullmatch(r"[a-z][a-z0-9-]{2,31}", identity["pool_id"]), "invalid identity pool")
    role = {"runtime-build": "runtime-build", "data-initialization": "data-initialize"}.get(p["plane"], f"{p['plane']}-release")
    expected_provider = (f"projects/{identity['project_number']}/locations/global/workloadIdentityPools/"
                         f"{identity['pool_id']}/providers/specimen-{role}")
    require(identity["provider"] == expected_provider, "wrong or unpinned WIF provider")
    pilot = exact_keys(p["pilot"], {"specimen_count", "manifest_sha256"}, "pilot")
    require(type(pilot["specimen_count"]) is int and pilot["specimen_count"] == 10, "exactly ten specimens required")
    digest(pilot["manifest_sha256"], "frozen manifest")
    validate_budget(p["budget"], pilot["manifest_sha256"])
    evidence = exact_keys(p["evidence"], {"independent_review", "authorization", "shared_budget_ledger"}, "evidence")
    require(evidence == {"independent_review": review["report_sha256"], "authorization": p["authorization_sha256"],
                         "shared_budget_ledger": p["budget"]["ledger_sha256"]}, "evidence references disagree")

    # These observations come from the GitHub API, not the supplied packet.
    main, pull, run = observed["main"], observed["pull"], observed["run"]
    require(main.get("sha") == p["source_sha"] and main.get("commit", {}).get("tree", {}).get("sha") == p["source_tree_sha"],
            "candidate is not the current main source/tree")
    require(pull.get("number") == p["pull_request"] and pull.get("merged") is True
            and pull.get("merge_commit_sha") == p["source_sha"] and pull.get("base", {}).get("ref") == "main"
            and pull.get("base", {}).get("repo", {}).get("id") == 1360732425
            and pull.get("head", {}).get("repo", {}).get("id") == 1360732425, "candidate lacks a matching merged repository PR")
    require(observed["pull_head"].get("sha") == pull.get("head", {}).get("sha")
            and observed["pull_head"].get("commit", {}).get("tree", {}).get("sha") == p["source_tree_sha"],
            "merged source differs from the reviewed PR tree")
    required_run = {"id": p["ci_run_id"], "run_attempt": p["ci_run_attempt"], "head_sha": p["source_sha"],
                    "head_branch": "main", "event": "push", "path": ".github/workflows/ci-cd.yml", "status": "completed", "conclusion": "success"}
    require(all(run.get(k) == value for k, value in required_run.items())
            and run.get("repository", {}).get("id") == 1360732425
            and run.get("head_repository", {}).get("id") == 1360732425, "untrusted, stale or unfinished CI run")
    for name in CHECKS:
        matches = [job for job in observed["jobs"] if job.get("name") == name]
        require(len(matches) == 1, f"missing or ambiguous required check: {name}")
        job = matches[0]
        require(job.get("status") == "completed" and job.get("conclusion") == "success"
                and job.get("head_sha") == p["source_sha"] and job.get("run_id") == p["ci_run_id"]
                and job.get("run_attempt") == p["ci_run_attempt"], f"required exact-source check failed: {name}")
    return p


def strict_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    def nonfinite(value):
        raise ValueError("nonfinite JSON constant")
    return json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)


def private_bytes(path: Path, limit: int = 1048576) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_mode & 0o077 == 0
                and info.st_uid == os.geteuid(), "owned private regular file required")
        raw = handle.read(limit + 1)
    require(len(raw) <= limit, "private input exceeds size limit")
    return raw


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
    snapshot = exact_keys(strict_json(raw), {"schema", "currency", "scope", "accounting_start_unix", "resets_allowed",
        "limit_micros", "coordinator_task", "frozen_metadata_sha256", "prior_evidence", "entries", "total_held_micros",
        "actual_prior_total_micros", "available_for_further_workloads_micros", "authorized_next_operation",
        "production_admission_compatible", "notes", "created_at"}, "coordinator snapshot")
    require(snapshot["schema"] == "coordinator-cumulative-release-budget/v1"
            and snapshot["currency"] == ledger["currency"] and snapshot["scope"] == ledger["scope"]
            and snapshot["coordinator_task"] == task and snapshot["resets_allowed"] is False,
            "accounting scope or reset mismatch")
    integer(snapshot["accounting_start_unix"], 1, packet["issued_at_unix"], "snapshot accounting start")
    require(snapshot["accounting_start_unix"] == anchor["accounting_start_unix"], "accounting start changed")
    integer(snapshot["limit_micros"], 1, 5000000, "accounting limit")
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
        integer(row["held_micros"], 1 if row["state"] == "unknown" else 0, 5000000, "coordinator liability")
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
        integer(entry["amount_micros"], expected["held_micros"], 5000000, "retained liability")
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


def validate_cost_ledger(ledger, packet):
    require(isinstance(ledger, dict), "invalid shared cost ledger")
    version = ledger.get("version")
    require(version in ("release-cost-ledger/v1", "release-cost-ledger/v2"), "unsupported shared cost ledger")
    additions = {"accounting", "operator_entries", "prior_uncertainty"} if version == "release-cost-ledger/v2" else set()
    ledger = exact_keys(ledger, {"version", "currency", "manifest_sha256", "scope", "entries"} | additions, "shared cost ledger")
    require(ledger["currency"] == "USD"
            and ledger["scope"] == "entire_first_ten_all_sessions_and_retries"
            and ledger["manifest_sha256"] == packet["pilot"]["manifest_sha256"], "shared ledger scope mismatch")
    require(isinstance(ledger["entries"], list), "cost entries required")
    seen, by_day, admitted = set(), {}, {name: 0 for name in CATEGORIES}
    for entry in ledger["entries"]:
        exact_keys(entry, {"operation_id", "plane", "run_id", "run_attempt", "category", "state", "amount_micros", "day_utc"}, "cost entry")
        ident = entry["operation_id"]
        require(isinstance(ident, str) and 1 <= len(ident) <= 200 and ident not in seen, "duplicate or invalid cost operation")
        seen.add(ident)
        require(entry["plane"] in PLANES and entry["category"] in CATEGORIES, "unrecognized cost owner/category")
        integer(entry["run_id"], 1, 2**53, "cost run")
        integer(entry["run_attempt"], 1, 2**53, "cost attempt")
        require(entry["state"] in {"settled", "unknown", "reserved"}, "invalid cost state")
        integer(entry["amount_micros"], 1 if entry["state"] == "unknown" else 0, 5000000, "cost liability")
        day = entry["day_utc"]
        require(isinstance(day, str) and date.fromisoformat(day).isoformat() == day, "invalid cost day")
        by_day[day] = by_day.get(day, 0) + entry["amount_micros"]
        if (entry["plane"], entry["run_id"], entry["run_attempt"]) == (packet["plane"], packet["release_run_id"], packet["release_run_attempt"]):
            require(entry["state"] == "reserved", "this operation may already have run; reconcile without replay")
            admitted[entry["category"]] += entry["amount_micros"]
    carry = 0
    if version == "release-cost-ledger/v2":
        operators, prior = coordinator_liabilities(ledger, packet, seen)
        for entry in operators:
            by_day[entry["day_utc"]] = by_day.get(entry["day_utc"], 0) + entry["amount_micros"]
        carry = prior["amount_micros"]
        by_day.setdefault(prior["day_utc"], 0)
    require(sum(by_day.values()) + carry <= packet["budget"]["total_limit_micros"], "cumulative shared budget exhausted")
    # An aggregate uncertainty has no verified service-day allocation. Retain
    # its full hold against every represented day, but count it once cumulatively.
    require(all(value + carry <= packet["budget"]["daily_limit_micros"] for value in by_day.values()), "daily shared budget exhausted")
    require(admitted == {entry["category"]: entry["ceiling_micros"] for entry in packet["budget"]["reservations"]},
            "planned operations lack exact existing reservations in the shared ledger")


def read_packet(path: Path, env: dict[str, str]) -> dict:
    raw = private_bytes(path, 65536)
    expected = env.get("RELEASE_PACKET_SHA256", "")
    digest(expected, "externally pinned packet digest")
    require(hashlib.sha256(raw).hexdigest() == expected, "authorization packet digest mismatch")
    return strict_json(raw)


def verify_evidence(packet: dict, directory: Path) -> dict[str, bytes]:
    require(not directory.is_symlink(), "evidence directory must not be a symlink")
    verified = {}
    for name, expected in packet["evidence"].items():
        path = directory / f"{name}.json"
        try:
            raw = private_bytes(path)
        except (OSError, ValueError):
            raise ValueError(f"missing private evidence: {name}") from None
        require(hashlib.sha256(raw).hexdigest() == expected, f"evidence digest mismatch: {name}")
        verified[name] = raw
    return verified


def gh_json(path: str) -> object:
    result = subprocess.run(["gh", "api", path], capture_output=True, check=False, timeout=30)
    require(result.returncode == 0, "GitHub evidence request failed; release remains blocked")
    return json.loads(result.stdout)


def github_snapshot(packet: dict) -> dict:
    base = f"repos/{REPOSITORY}"
    pull = gh_json(f"{base}/pulls/{packet['pull_request']}")
    run = gh_json(f"{base}/actions/runs/{packet['ci_run_id']}")
    jobs = []
    for page in range(1, 101):
        result = gh_json(f"{base}/actions/runs/{packet['ci_run_id']}/attempts/{packet['ci_run_attempt']}/jobs?per_page=100&page={page}")
        jobs.extend(result["jobs"])
        if len(jobs) >= result["total_count"]:
            break
    else:
        raise ValueError("CI job pagination did not reconcile")
    return {"main": gh_json(f"{base}/commits/main"), "pull": pull,
            "pull_head": gh_json(f"{base}/commits/{pull['head']['sha']}"), "run": run, "jobs": jobs}


def admit(packet_path: Path, plane: str, *, now: float | None = None) -> dict:
    env = dict(os.environ)
    packet = read_packet(packet_path, env)
    require(packet.get("plane") == plane, "wrong release plane")
    # Reject context before any remote lookup. Rechecked immediately before every mutation.
    validate_context(env, plane, packet.get("source_sha", ""))
    validate_admission(packet, env, github_snapshot(packet), now=now)
    evidence = verify_evidence(packet, packet_path.parent / "evidence")
    require(env.get("RELEASE_BUDGET_LEDGER_SHA256") == packet["budget"]["ledger_sha256"],
            "shared budget authority changed; reconcile all planes before continuing")
    ledger = strict_json(evidence["shared_budget_ledger"])
    validate_cost_ledger(ledger, packet)
    plan = private_bytes(packet_path.parent / "plan.json")
    require(hashlib.sha256(plan).hexdigest() == packet["plan_sha256"], "deployment plan digest mismatch")
    return packet


INPUT_SECRET_MAX_BYTES = 48000
INPUT_RAW_MAX_BYTES = 1048576
INPUT_LEGACY_BASE64_MAX_BYTES = 4 * ((INPUT_RAW_MAX_BYTES + 2) // 3)


def encode_release_inputs(raw: bytes) -> str:
    """Fit exact original bundle bytes in one secret; compression grants no admission."""
    require(type(raw) is bytes and 0 < len(raw) <= INPUT_RAW_MAX_BYTES,
            "missing or oversized private release inputs")
    plain = base64.b64encode(raw).decode("ascii")
    if len(plain) <= INPUT_SECRET_MAX_BYTES:
        return plain
    output = io.BytesIO()
    # Empty filename, zero mtime and GzipFile's fixed OS byte make the envelope
    # deterministic without rewriting any original JSON or evidence bytes.
    with gzip.GzipFile(fileobj=output, mode="wb", filename="", mtime=0, compresslevel=9) as stream:
        stream.write(raw)
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    require(len(encoded) <= INPUT_SECRET_MAX_BYTES, "release inputs do not fit the single secret")
    return encoded


def decode_release_inputs(encoded: str) -> bytes:
    """Accept raw JSON or one complete gzip member, with bounded input and output."""
    # Preserve the existing raw-JSON decoder contract. New producers always
    # enforce the smaller secret ceiling; gzip does not expand the legacy limit.
    require(isinstance(encoded, str) and 0 < len(encoded) <= INPUT_LEGACY_BASE64_MAX_BYTES,
            "missing or oversized release input secret")
    wire = base64.b64decode(encoded, validate=True)
    # The gzip magic cannot prefix valid JSON. No JSON-controlled codec flag,
    # zlib/raw-deflate autodetection, second stream or trailing content is accepted.
    if wire.startswith(b"\x1f\x8b"):
        require(len(encoded) <= INPUT_SECRET_MAX_BYTES, "oversized compressed release input secret")
        try:
            stream = zlib.decompressobj(wbits=31)
            raw = stream.decompress(wire, INPUT_RAW_MAX_BYTES + 1)
        except zlib.error:
            raise ValueError("invalid compressed release inputs") from None
        require(len(raw) <= INPUT_RAW_MAX_BYTES and stream.eof
                and not stream.unconsumed_tail and not stream.unused_data,
                "oversized, incomplete or trailing compressed release inputs")
        # Never flush a decompressor: its length argument is not an output cap.
    else:
        raw = wire
    require(0 < len(raw) <= INPUT_RAW_MAX_BYTES, "missing or oversized private release inputs")
    return raw


def materialize_inputs(destination: Path, env: dict[str, str]) -> None:
    """Restore one reviewed private secret without accepting archive paths."""
    raw = decode_release_inputs(env.get("RELEASE_INPUTS_B64", ""))
    digest(env.get("RELEASE_INPUTS_SHA256"), "release input digest")
    require(hashlib.sha256(raw).hexdigest() == env["RELEASE_INPUTS_SHA256"], "release input digest mismatch")
    bundle = exact_keys(strict_json(raw), {"packet", "plan", "evidence"}, "private bundle")
    exact_keys(bundle["evidence"], {"independent_review", "authorization", "shared_budget_ledger"}, "private evidence")
    values = {"packet.json": bundle["packet"], "plan.json": bundle["plan"],
              **{f"evidence/{name}.json": value for name, value in bundle["evidence"].items()}}
    require(all(isinstance(value, str) for value in values.values()),
            "private bundle must retain exact original UTF-8 evidence bytes")
    contents = {name: value.encode("utf-8") for name, value in values.items()}
    require(not destination.exists(), "refuse to overwrite release inputs")
    destination.mkdir(mode=0o700)
    (destination / "evidence").mkdir(mode=0o700)
    for name, value in contents.items():
        descriptor = os.open(destination / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(value)


def read_bound_plan(path: Path, packet: dict) -> dict:
    raw = private_bytes(path)
    require(hashlib.sha256(raw).hexdigest() == packet["plan_sha256"], "deployment plan digest mismatch")
    return strict_json(raw)
