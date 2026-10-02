"""The approved, finite A/B bootstrap recovery window; never a timestamp authority.

ROOT must first verify the new push's native attempt-1 run_started_at is in
[the frozen activation T0, T0 + 600]. Only with that independent witness is
C = that immutable attempt timestamp - 600 <= T0. GitHub's attempt API exposes
the timestamp but does not promise queue semantics. This module neither knows
T0 nor substitutes a caller timestamp for the required ROOT witness.

The workflow transports only the presence of the existing bootstrap secret.
Ordinary releases after its removal keep their existing G11 admission. Every
guarded job re-reads exact attempt 1 of its own main push, and the gate keeps
its existing keys, digest transport and one-hour maximum. A may initialize;
B must be attempt 2, after the whole successful A and its signed receipts.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import math
from pathlib import Path
import re
import tempfile
import time

from release_admission import gh_json, require, strict_json
from release_context import PROJECT, REPOSITORY

MODE = "RELEASE_RECOVERY_WINDOW"
WORKFLOW = ".github/workflows/data-release.yml"
REPOSITORY_ID = 1360732425
ANCHOR_SECONDS, B_START_SECONDS = 600, 3000
INIT_SECONDS, DATA_SECONDS = 4500, 6900
RUN_SECONDS, CLEANUP_SECONDS = 3600, 300
OPERATING_SECONDS = DATA_SECONDS - CLEANUP_SECONDS
SOURCE, DATABASE = "specimen-digitization-instance", "specimen-digitization-database"
SERVICE = f"projects/{PROJECT}/locations/us-east4/services/specimen-digitization-service"
JOBS = frozenset(("Admit the merged commit after its checks",
    "Read the live data plane and release the merged files",
    "Initialize the existing, empty database with a one-time principal",
    "Revoke and delete only the initializer principal this run created",
    "Migrate the initialized database as its owner and release the merged files"))
DATA_FACTS = frozenset(("phase", "schema_etag", "schema_update_time", "connector_etag", "storage_ruleset",
    "source_sha_label", "backup_id", "first_restore", "tables", "views", "bootstrap", "worker_membership"))


def enabled(env, plane):
    value = env.get(MODE, "false")
    require(type(value) is str and value in {"true", "false"}, "invalid protected recovery presence flag")
    return plane in {"data", "data-initialization"} and value == "true"


def current_time(now=None):
    value = time.time() if now is None else now
    require(type(value) in {int, float} and math.isfinite(value) and value > 0,
            "invalid protected recovery clock")
    return value


def timestamp(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value),
            "invalid native attempt timestamp")
    return int(datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp())


def validate_run(value, record, attempt):
    expected = {"id": record["release_run_id"], "run_attempt": attempt, "head_sha": record["source_sha"],
                "head_branch": "main", "event": "push", "path": WORKFLOW}
    require(isinstance(value, dict) and all(type(value.get(key)) is type(wanted) and value[key] == wanted
            for key, wanted in expected.items()) and isinstance(value.get("repository"), dict)
            and value["repository"].get("id") == REPOSITORY_ID and isinstance(value.get("head_repository"), dict)
            and value["head_repository"].get("id") == REPOSITORY_ID,
            "native recovery attempt differs from the admitted push")
    return value


def successful_jobs(record, gh):
    jobs, total = [], None
    for page in range(1, 101):
        result = gh(f"repos/{REPOSITORY}/actions/runs/{record['release_run_id']}/attempts/1/jobs?per_page=100&page={page}")
        require(isinstance(result, dict) and isinstance(result.get("jobs"), list)
                and type(result.get("total_count")) is int and 0 <= result["total_count"] <= 10000,
                "invalid prior initialization job listing")
        total = result["total_count"] if total is None else total
        require(result["total_count"] == total, "prior initialization job count changed")
        jobs.extend(result["jobs"])
        require(len(jobs) <= total, "prior initialization job listing exceeds its count")
        if len(jobs) == total:
            break
        require(result["jobs"], "prior initialization job pagination is incomplete")
    else:
        raise ValueError("prior initialization job pagination is incomplete")
    require(len(jobs) == len(JOBS) and all(isinstance(job, dict) and isinstance(job.get("name"), str) for job in jobs)
            and {job["name"] for job in jobs} == JOBS,
            "prior initialization jobs are missing or ambiguous")
    require(all(isinstance(job, dict) and job.get("status") == "completed" and job.get("conclusion") == "success"
                and job.get("head_sha") == record["source_sha"] and type(job.get("run_id")) is int
                and job["run_id"] == record["release_run_id"] and type(job.get("run_attempt")) is int
                and job["run_attempt"] == 1 for job in jobs), "prior initialization jobs did not all succeed")


def observe(record, env, *, now=None, gh=None):
    """Derive a fixed origin from the exact native A attempt, never the latest run."""
    if not enabled(env, record.get("plane")):
        return None
    require(record.get("version") == "protected-release-gate/v1"
            and type(record.get("release_run_attempt")) is int and record["release_run_attempt"] in {1, 2},
            "finite recovery admits only its two ordered attempts")
    require(type(record.get("release_run_id")) is int and 1 <= record["release_run_id"] <= 2**53
            and isinstance(record.get("source_sha"), str) and re.fullmatch(r"[0-9a-f]{40}", record["source_sha"]),
            "invalid protected recovery run binding")
    gh = gh_json if gh is None else gh
    path = f"repos/{REPOSITORY}/actions/runs/{record['release_run_id']}/attempts"
    prior = validate_run(gh(path + "/1"), record, 1)
    started = timestamp(prior.get("run_started_at"))
    require(started >= ANCHOR_SECONDS and started <= current_time(now), "native recovery anchor is future-dated")
    if record["release_run_attempt"] == 2:
        require(record["plane"] == "data" and prior.get("status") == "completed"
                and prior.get("conclusion") == "success", "B requires the whole successful A")
        successful_jobs(record, gh)
        current = validate_run(gh(path + "/2"), record, 2)
        require(current.get("status") == "in_progress" and started <= timestamp(current.get("run_started_at")) <= current_time(now),
                "B is not the active second attempt of A's push")
    else:
        require(prior.get("status") == "in_progress", "A is not the active first attempt")
    origin = started - ANCHOR_SECONDS
    end = INIT_SECONDS if record["plane"] == "data-initialization" else DATA_SECONDS
    if record["release_run_attempt"] == 2:
        end = min(end, OPERATING_SECONDS)
    return {"origin": origin, "attempt": record["release_run_attempt"],
            "start_before": origin + B_START_SECONDS,
            "expires_before": origin + end, "cleanup_before": origin + DATA_SECONDS}


def admit_record(record, env, *, now=None, gh=None):
    """After all GitHub waits/reads, mint only the remaining fixed window."""
    window = observe(record, env, now=now, gh=gh)
    if window is None:
        return record
    actual = current_time(now)
    if window["attempt"] == 2:
        require(actual < window["start_before"], "B admission missed the finite activation window")
    issued = int(actual)
    expires = min(issued + RUN_SECONDS, window["expires_before"])
    require(actual < expires, "protected recovery admission waited past its fixed deadline")
    return {**record, "issued_at_unix": issued, "expires_at_unix": expires}


def readmit_record(record, env, *, now=None, gh=None):
    """Re-observe the fixed origin; never reissue or extend the signed gate."""
    window = observe(record, env, now=now, gh=gh)
    if window is None:
        return record
    require(record["expires_at_unix"] <= min(record["issued_at_unix"] + RUN_SECONDS, window["expires_before"]),
            "gate exceeds the fixed protected recovery deadline")
    require(record["issued_at_unix"] <= current_time(now) < record["expires_at_unix"],
            "protected recovery gate expired during re-admission")
    if window["attempt"] == 2:
        require(record["issued_at_unix"] < window["start_before"], "B gate was issued after its start boundary")
    return record


def require_secret_presence(env, secrets):
    # Legacy/offline callers have no flag. The reviewed workflow supplies a
    # literal bool from secret PRESENCE; absence never authorizes this recovery.
    if MODE in env:
        require(enabled(env, "data") == bool(secrets.get("DATA_BOOTSTRAP_ARTIFACT_B64")),
                "protected bootstrap presence and recovery guard disagree")


def qualified_prior(record, *, gh=None, fetch=None):
    """Consume exactly A1's three subject-bound attested receipts, privately."""
    require(record["release_run_attempt"] == 2, "prior initialization is only for B")
    gh = gh_json if gh is None else gh
    listing = gh(f"repos/{REPOSITORY}/actions/runs/{record['release_run_id']}/artifacts?per_page=100")
    require(isinstance(listing, dict) and isinstance(listing.get("artifacts"), list)
            and type(listing.get("total_count")) is int and listing["total_count"] == len(listing["artifacts"]),
            "incomplete prior initialization artifact listing")
    if fetch is None:
        from deploy_runtime import checked, verified_receipt_bytes

        def fetch(name, filename):
            with tempfile.TemporaryDirectory() as folder:
                checked(["gh", "run", "download", str(record["release_run_id"]), "--repo", REPOSITORY,
                         "--name", name, "--dir", folder])
                path = Path(folder) / filename
                return strict_json(verified_receipt_bytes(path, hashlib.sha256(path.read_bytes()).hexdigest(),
                                                          record["source_sha"], "data-release.yml"))
    values = {}
    for prefix, filename in (("data-receipt", "data-receipt.json"), ("data-initializer", "data-initializer.json"),
                             ("data-initialized", "data-initialized.json")):
        name = f"{prefix}-{record['source_sha']}-1"
        matches = [item for item in listing["artifacts"] if isinstance(item, dict) and item.get("name") == name]
        require(len(matches) == 1 and matches[0].get("expired") is False
                and isinstance(matches[0].get("workflow_run"), dict)
                and matches[0]["workflow_run"].get("id") == record["release_run_id"]
                and matches[0]["workflow_run"].get("head_sha") == record["source_sha"],
                "prior initialization artifact is missing, expired or foreign")
        values[prefix] = fetch(name, filename)
    binding = {"source_sha": record["source_sha"], "run_id": record["release_run_id"], "run_attempt": 1}
    for value in values.values():
        require(isinstance(value, dict) and all(type(value.get(key)) is type(wanted) and value[key] == wanted
                for key, wanted in binding.items()), "attested A receipt differs from this push and attempt")
    released, initialized, principal = (values[key] for key in ("data-receipt", "data-initialized", "data-initializer"))
    require(set(released) == {"version", *binding, *DATA_FACTS} and released.get("version") == "data-released/v1"
            and released.get("phase") == "initialize" and released.get("bootstrap") == "deferred"
            and released.get("backup_id") is None and released.get("first_restore") is None,
            "A did not defer bootstrap after first initialization")
    require(set(principal) == {"version", *binding, "instance", "database", "postconditions_sha256"}
            and principal.get("version") == "data-initializer/v1" and principal.get("instance") == SOURCE
            and principal.get("database") == DATABASE and isinstance(principal.get("postconditions_sha256"), str)
            and re.fullmatch(r"[0-9a-f]{64}", principal["postconditions_sha256"]), "A initializer receipt is malformed")
    require(set(initialized) == {"version", "phase", *binding, "schema_etag", "schema_update_time", "connector_etag",
                                "storage_ruleset", "tables", "views"}
            and initialized.get("version") == "data-initialized/v1" and initialized.get("phase") == "initialize"
            and all(isinstance(initialized.get(key), str) and initialized[key] for key in
                    ("schema_etag", "schema_update_time", "connector_etag", "storage_ruleset"))
            and type(initialized.get("tables")) is int and initialized["tables"] > 0
            and type(initialized.get("views")) is int and initialized["views"] >= 0,
            "A's completed migration receipt is malformed")
    return principal, initialized


def is_effect(api, method, resource, params=None):
    if method == "GET":
        return False
    if api == "data" and method == "POST" and resource == SERVICE + ":executeGraphqlRead":
        return False
    if api == "identity" and method == "POST" and resource == f"projects/{PROJECT}/accounts:lookup":
        return False
    if (api == "data" and method == "PATCH" and resource in {SERVICE + "/schemas/main", SERVICE + "/connectors/specimen-server"}
            and isinstance(params, dict) and params.get("validateOnly") == "true"):
        return False
    return True


class FirstEffect:
    """One B process: latch before its first actual write, including unknown sends.

    The latch creates no retry permission. Existing ownership/intents still
    govern every effect, and cleanup after a sent effect keeps the fixed cap.
    Read-only POSTs and validate-only PATCHes cannot start B's write window.
    """
    def __init__(self, record, window, *, clock=None):
        require(window["attempt"] == 2, "first-effect boundary belongs only to B")
        self.start_before = window["start_before"]
        self.expires = min(record["expires_at_unix"], window["expires_before"])
        self.clock = time.time if clock is None else clock
        self.started = False

    def budget(self, api, method, resource, params=None):
        """Hard bound refresh/dispatch/body reads for the first possible send."""
        now = current_time(self.clock())
        deadline = self.expires
        if is_effect(api, method, resource, params) and not self.started:
            deadline = min(deadline, self.start_before)
        require(now < deadline, "B dispatch has no remaining fixed authority")
        return deadline - now

    def __call__(self, api, method, resource, params=None):
        now = self.clock()
        require(current_time(now) < self.expires, "B effect exceeded its original fixed gate")
        if is_effect(api, method, resource, params) and not self.started:
            require(now < self.start_before, "B first effect missed the finite activation window")
            # Set before dispatch: a sent write with unknown outcome is still
            # a write; its owned cleanup must not be barred by the start cutoff.
            self.started = True
