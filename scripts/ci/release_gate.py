#!/usr/bin/env python3
"""Credential-free gate for the runtime and data release planes (owner decision G11).

It replaces the owner-minted envelope with facts GitHub reports about the
merged commit: the commit is on main, exactly one merged pull request of this
repository produced it with the reviewed tree, and all five required checks
passed in the latest attempt of its CI/CD push run. The record written here
grants nothing by itself: each later admission reads it by its exported digest
and observes the same facts again. Never a product-readiness verdict.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from release_admission import gh_json, read_packet, require
from release_context import PROJECT, REPOSITORY, validate_context
from validate_release_packet import CHECKS, SHA, exact_keys
import release_recovery_window as recovery

RECORD_VERSION = "protected-release-gate/v1"
PROJECT_NUMBER = "716045864126"
POOL_ID = "github-actions"
POOL = f"projects/{PROJECT_NUMBER}/locations/global/workloadIdentityPools/{POOL_ID}"
# Each gate plane: the release it belongs to, and its fixed Workload Identity provider. A job of the data
# release never waits for a data release, because it is one; only a runtime plane may carry a data run (D3).
GATE_PLANES = {"runtime-build": ("runtime", f"{POOL}/providers/specimen-runtime-build"),
               "runtime": ("runtime", f"{POOL}/providers/specimen-runtime-release"),
               "data": ("data", f"{POOL}/providers/specimen-data-release"),
               "data-initialization": ("data", f"{POOL}/providers/specimen-data-initialize")}
PROVIDERS = {plane: provider for plane, (_, provider) in GATE_PLANES.items()}
WINDOW_SECONDS = 3600
POLL_SECONDS = 30
MAX_WAIT_SECONDS = 5400
DATA_MAX_WAIT_SECONDS = 3300
REPOSITORY_ID = 1360732425
CI_WORKFLOW = ".github/workflows/ci-cd.yml"
DATA_WORKFLOW = ".github/workflows/data-release.yml"
DATA_RECORD_KEYS = {"data_run_id", "data_run_attempt"}
RECORD_KEYS = {"version", "plane", "repository", "project", "source_sha", "source_tree_sha", "pull_request",
               "ci_run_id", "ci_run_attempt", "release_run_id", "release_run_attempt", "issued_at_unix",
               "expires_at_unix", "identity"}


def field(value: object, *keys: str) -> object:
    """Read a nested API value; a missing or null level reads as None."""
    for key in keys:
        value = value.get(key) if isinstance(value, dict) else None
    return value


def positive(value: object) -> bool:
    return type(value) is int and 1 <= value <= 2**53


def is_sha(value: object) -> bool:
    return isinstance(value, str) and SHA.fullmatch(value) is not None


def run_number(env: dict[str, str], key: str) -> int:
    value = env.get(key)
    require(isinstance(value, str) and re.fullmatch(r"[1-9][0-9]{0,15}", value) and int(value) <= 2**53,
            f"release context rejected: {key}")
    return int(value)


def identity(plane: str) -> dict:
    return {"project_number": PROJECT_NUMBER, "pool_id": POOL_ID, "provider": PROVIDERS[plane]}


def workflow_run(sha: str, workflow: str, deadline: float, gh, clock, sleep) -> dict:
    """The one push run of a workflow for the commit, polled until it completes or the deadline passes."""
    name = workflow.rsplit("/", 1)[-1]
    path = f"repos/{REPOSITORY}/actions/workflows/{name}/runs?head_sha={sha}&event=push&branch=main&per_page=20"
    while True:
        listing = field(gh(path), "workflow_runs")
        require(isinstance(listing, list), f"invalid {name} run listing")
        runs = [run for run in listing if field(run, "head_sha") == sha and field(run, "event") == "push"
                and field(run, "head_branch") == "main" and field(run, "path") == workflow]
        require(len(runs) <= 1, f"ambiguous {name} runs for the merged commit")
        if runs and runs[0].get("status") == "completed":
            return runs[0]
        require(clock() < deadline, f"{name} run for the merged commit did not finish in time")
        sleep(POLL_SECONDS)


def observe(sha: str, *, wait_seconds: int, gh=gh_json, clock=time.time, sleep=time.sleep, wait_data: bool = True) -> dict:
    """Read the GitHub facts about one merged commit without credentials.

    CI/CD is awaited first because both workflows start on the same push; the
    source facts are read after it, so they are as fresh as the checks.
    """
    require(is_sha(sha), "invalid release source")
    require(type(wait_seconds) is int and 0 <= wait_seconds <= MAX_WAIT_SECONDS, "invalid CI/CD wait")
    base = f"repos/{REPOSITORY}"
    require(type(wait_data) is bool, "invalid data wait")
    require(wait_data or wait_seconds <= DATA_MAX_WAIT_SECONDS, "invalid data wait")
    deadline = clock() + wait_seconds
    run = workflow_run(sha, CI_WORKFLOW, deadline, gh, clock, sleep)
    data_run = workflow_run(sha, DATA_WORKFLOW, deadline, gh, clock, sleep) if wait_data else None
    run_id, attempt = run.get("id"), run.get("run_attempt")
    require(positive(run_id) and positive(attempt), "invalid CI/CD run")
    jobs = []
    for page in range(1, 101):
        listing = gh(f"{base}/actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100&page={page}")
        require(isinstance(field(listing, "jobs"), list) and type(field(listing, "total_count")) is int,
                "invalid CI job listing")
        jobs.extend(listing["jobs"])
        if len(jobs) >= listing["total_count"]:
            break
    else:
        raise ValueError("CI job pagination did not reconcile")
    pulls = gh(f"{base}/commits/{sha}/pulls")
    require(isinstance(pulls, list), "invalid pull request listing")
    merged = [pull for pull in pulls if field(pull, "merge_commit_sha") == sha and field(pull, "merged_at")]
    require(len(merged) == 1, "the merged commit needs exactly one merged pull request")
    number = merged[0].get("number")
    require(positive(number), "invalid pull request")
    pull = gh(f"{base}/pulls/{number}")
    head = field(pull, "head", "sha")
    require(field(pull, "number") == number and is_sha(head), "pull request differs from its listing")
    return {"compare": gh(f"{base}/compare/{sha}...main"), "commit": gh(f"{base}/commits/{sha}"),
            "pull": pull, "pull_head": gh(f"{base}/commits/{head}"), "run": run, "jobs": jobs, "data_run": data_run}


def validate_facts(sha: str, observed: dict, *, wait_data: bool = True) -> dict:
    """Derive the gate facts from GitHub observations only, never from a record."""
    compare, pull, head, commit, run = (observed[key] for key in ("compare", "pull", "pull_head", "commit", "run"))
    require(field(compare, "status") in {"identical", "ahead"} and field(compare, "base_commit", "sha") == sha,
            "merged commit is not on main")
    tree = field(commit, "commit", "tree", "sha")
    require(field(commit, "sha") == sha and is_sha(tree), "invalid merged commit tree")
    require(field(pull, "merged") is True and field(pull, "merge_commit_sha") == sha and positive(field(pull, "number"))
            and field(pull, "base", "ref") == "main" and field(pull, "base", "repo", "id") == REPOSITORY_ID
            and field(pull, "head", "repo", "id") == REPOSITORY_ID, "no matching merged pull request of this repository")
    require(is_sha(field(pull, "head", "sha")) and field(head, "sha") == field(pull, "head", "sha")
            and field(head, "commit", "tree", "sha") == tree, "merged tree differs from the reviewed pull request tree")
    run_id, attempt = field(run, "id"), field(run, "run_attempt")
    expected = {"head_sha": sha, "head_branch": "main", "event": "push", "path": CI_WORKFLOW,
                "status": "completed", "conclusion": "success"}
    require(all(field(run, key) == value for key, value in expected.items()) and positive(run_id) and positive(attempt)
            and field(run, "repository", "id") == REPOSITORY_ID and field(run, "head_repository", "id") == REPOSITORY_ID,
            "untrusted, unfinished or failed CI/CD run")
    jobs = observed["jobs"]
    require(isinstance(jobs, list), "invalid CI job listing")
    for name in sorted(CHECKS):
        matches = [job for job in jobs if field(job, "name") == name]
        require(len(matches) == 1, f"missing or ambiguous required check: {name}")
        job = matches[0]
        require(job.get("status") == "completed" and job.get("conclusion") == "success" and job.get("head_sha") == sha
                and job.get("run_id") == run_id and job.get("run_attempt") == attempt,
                f"required check failed on the merged commit: {name}")
    facts = {"source_tree_sha": tree, "pull_request": pull["number"], "ci_run_id": run_id, "ci_run_attempt": attempt}
    require(type(wait_data) is bool, "invalid data wait")
    if wait_data:
        data = observed.get("data_run")
        data_id, data_attempt = field(data, "id"), field(data, "run_attempt")
        require(all(field(data, key) == value for key, value in {**expected, "path": DATA_WORKFLOW}.items())
                and positive(data_id) and positive(data_attempt) and field(data, "repository", "id") == REPOSITORY_ID
                and field(data, "head_repository", "id") == REPOSITORY_ID,
                "the same commit's data release did not succeed")
        facts.update(data_run_id=data_id, data_run_attempt=data_attempt)
    return facts


def observed_for_plane(sha: str, plane: str, wait_seconds: int, observer):
    """Runtime D3 waits for data; data jobs only await CI, so cannot wait for themselves.

    The injected observer preserves the offline test seam; validation still requires
    all runtime data facts regardless of how observations were supplied.
    """
    return (observe(sha, wait_seconds=wait_seconds, wait_data=GATE_PLANES[plane][0] == "runtime")
            if observer is None else observer(sha, wait_seconds=wait_seconds))


def admit_gate(plane: str, env: dict[str, str], *, wait_seconds: int, now: float | None = None,
               observe=None) -> dict:
    """Admit a release job from GitHub facts, before any cloud credential exists."""
    require(plane in GATE_PLANES, "unknown gate plane")
    limit = MAX_WAIT_SECONDS if GATE_PLANES[plane][0] == "runtime" else DATA_MAX_WAIT_SECONDS
    require(type(wait_seconds) is int and 0 <= wait_seconds <= limit, "invalid release wait")
    sha = env.get("GITHUB_SHA", "")
    # Reject the context before any GitHub request.
    validate_context(env, plane, sha, envelope=False)
    release_run_id, release_run_attempt = run_number(env, "GITHUB_RUN_ID"), run_number(env, "GITHUB_RUN_ATTEMPT")
    facts = validate_facts(sha, observed_for_plane(sha, plane, wait_seconds, observe),
                           wait_data=GATE_PLANES[plane][0] == "runtime")
    # Issued after the wait, so the whole window remains for the steps that follow.
    issued = int(time.time() if now is None else now)
    record = {"version": RECORD_VERSION, "plane": plane, "repository": REPOSITORY, "project": PROJECT,
              "source_sha": sha, **facts, "release_run_id": release_run_id, "release_run_attempt": release_run_attempt,
              "issued_at_unix": issued, "expires_at_unix": issued + WINDOW_SECONDS, "identity": identity(plane)}
    return recovery.admit_record(record, env, now=now)


def write_record(record: dict, path: Path, env: dict[str, str]) -> str:
    """Write the owner-only record once and export its digest and fixed provider to later steps."""
    targets = env.get("GITHUB_ENV"), env.get("GITHUB_OUTPUT")
    require(all(targets), "GitHub step files required")
    provider, source = field(record, "identity", "provider"), field(record, "source_sha")
    # Only fixed providers and hex digests reach the step files, so no line can be injected.
    require(is_gate_record(record) and provider in PROVIDERS.values() and is_sha(source),
            "only an admitted gate record is written")
    mode = str(recovery.enabled(env, record["plane"])).lower() if recovery.MODE in env else None
    raw = json.dumps(record, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    path = Path(path)
    path.parent.mkdir(mode=0o700, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(raw)
    value = hashlib.sha256(raw).hexdigest()
    with open(targets[0], "a", encoding="utf-8") as handle:
        handle.write(f"RELEASE_PACKET_SHA256={value}\n")
        if mode is not None:
            handle.write(f"{recovery.MODE}={mode}\n")
    with open(targets[1], "a", encoding="utf-8") as handle:
        handle.write(f"provider={provider}\nsource_sha={source}\n")
        if mode is not None:
            handle.write(f"recovery_window={mode}\n")
    return value


def is_gate_record(value: object) -> bool:
    return isinstance(value, dict) and value.get("version") == RECORD_VERSION


def readmit(path: Path, plane: str, env: dict[str, str], *, now: float | None = None, observe=None) -> dict:
    """Re-admit a later step from its digest-pinned record and the same GitHub facts, without waiting."""
    require(plane in GATE_PLANES, "unknown gate plane")
    keys = RECORD_KEYS | (DATA_RECORD_KEYS if GATE_PLANES[plane][0] == "runtime" else set())
    record = exact_keys(read_packet(Path(path), env), keys, "gate record")
    require(record["version"] == RECORD_VERSION and plane in GATE_PLANES and record["plane"] == plane,
            "wrong gate record or plane")
    require(record["repository"] == REPOSITORY and record["project"] == PROJECT, "foreign gate record target")
    require(exact_keys(record["identity"], {"project_number", "pool_id", "provider"}, "gate identity") == identity(plane),
            "wrong or unpinned WIF provider")
    for key, name in (("release_run_id", "GITHUB_RUN_ID"), ("release_run_attempt", "GITHUB_RUN_ATTEMPT")):
        require(positive(record[key]) and record[key] == run_number(env, name), "gate record is for another run or attempt")
    recovery_now = now
    now = time.time() if now is None else now
    issued, expires = record["issued_at_unix"], record["expires_at_unix"]
    require(positive(issued) and positive(expires) and issued <= now < expires <= issued + WINDOW_SECONDS,
            "gate record expired, future-dated or exceeds one hour")
    validate_context(env, plane, record["source_sha"], envelope=False)
    facts = validate_facts(record["source_sha"], observed_for_plane(record["source_sha"], plane, 0, observe),
                           wait_data=GATE_PLANES[plane][0] == "runtime")
    require(all(type(record[key]) is type(value) and record[key] == value for key, value in facts.items()),
            "GitHub facts changed since admission")
    return recovery.readmit_record(record, env, now=recovery_now)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plane", choices=sorted(GATE_PLANES), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wait-seconds", type=int, default=0)
    args = parser.parse_args()
    env, release = dict(os.environ), GATE_PLANES[args.plane][0].capitalize()
    try:
        write_record(admit_gate(args.plane, env, wait_seconds=args.wait_seconds), args.output, env)
    except (ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        # Never echo record values, identities or API bodies: workflow logs are public.
        raise SystemExit(f"{release} release gate blocked ({type(exc).__name__}); inspect the gate checks privately.") from None
    print(f"{release} release gate passed; deployment and readiness are separate gates.")


if __name__ == "__main__":
    main()
