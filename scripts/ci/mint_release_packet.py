#!/usr/bin/env python3
"""Assemble one release input bundle from observed facts and private evidence.

This tool exists so that a `protected-release/v1` packet no longer has to be
written out by hand. It grants nothing. Every value it produces is either read
back from git, the GitHub API and the clock, or supplied by the operator as a
private artifact whose exact bytes travel in the bundle. Nothing is defaulted,
inferred or filled in: an absent input stops the run.

The generator validates its own output through the untouched release validators
before it reports anything. Passing here means the packet is well formed and
source-bound; admission, cloud credentials and product acceptance remain
separate gates that this tool cannot satisfy or weaken.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))

from release_admission import (CATEGORIES, decode_release_inputs, encode_release_inputs,
                               private_bytes, strict_json, validate_admission, validate_cost_ledger)
from release_context import PLANES, PROJECT, REPOSITORY
from validate_release_packet import CHECKS, DIGEST, IMAGE, SHA, validate

from specimen_digitization.hub_models import SAM3_MODEL
from specimen_digitization.release_budget import (APPROVAL_SHA256, APPROVED_LIMIT_MICROS,
                                                  LEGACY_LIMIT_MICROS)

CI_WORKFLOW = ".github/workflows/ci-cd.yml"
REPOSITORY_ID = 1360732425
PACKET_MAX_BYTES = 65536
RUN_URL = re.compile(rf"https://github\.com/{re.escape(REPOSITORY)}/actions/runs/[1-9][0-9]*(?:/job/[1-9][0-9]*)?")
LEDGER_DIALECTS = {"release-cost-ledger/v1", "release-cost-ledger/v2", "release-cost-ledger/v3"}
APPROVED_DIALECT = "release-cost-ledger/v3"
EVIDENCE_NAMES = ("independent_review", "authorization", "shared_budget_ledger")


class Refused(ValueError):
    """The generator declined to mint. The message names the exact gate."""


def refuse(condition: object, message: str) -> None:
    if not condition:
        raise Refused(message)


def canonical(value: object) -> bytes:
    """The byte form every consumer digests: sorted, compact, newline-terminated."""
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


# ------------------------------------------------------------------ inputs ---


@dataclass
class Inputs:
    """Everything the generator cannot observe for itself."""

    plane: str
    release_run_id: int
    release_run_attempt: int
    plan_path: Path
    authorization_path: Path
    review_report_path: Path
    ledger_path: Path
    cost_review_path: Path
    reviewer_session: str
    project_number: str
    pool_id: str
    pilot_manifest_sha256: str
    candidate_evidence: dict
    coordinator_session: str | None = None
    window_seconds: int = 1800
    accept_legacy_budget: bool = False
    registry: object = None


@dataclass
class Minted:
    packet: dict
    packet_raw: bytes
    plan_raw: bytes
    evidence: dict
    bundle_raw: bytes
    secret: str
    variables: dict
    candidate: dict
    candidate_raw: bytes
    notes: list = field(default_factory=list)


def read_private(path: object, label: str) -> bytes:
    """Private release evidence must already be a private regular file we own."""
    refuse(path is not None, f"{label} is required; no value was supplied")
    path = Path(path)
    try:
        return private_bytes(path)
    except (OSError, ValueError) as exc:
        raise Refused(
            f"{label} is required but the file is missing or unreadable as private input: {path}\n"
            f"  ({exc}). If the file exists, restrict it with: chmod 600 {path}"
        ) from None


def check_identity(inputs: Inputs) -> None:
    refuse(inputs.plane in PLANES, f"unknown release plane: {inputs.plane!r}; expected one of {sorted(PLANES)}")
    for name in ("release_run_id", "release_run_attempt"):
        value = getattr(inputs, name)
        refuse(type(value) is int and 1 <= value <= 2 ** 53, f"{name} must be the positive integer GitHub assigns")
    refuse(isinstance(inputs.reviewer_session, str) and 1 <= len(inputs.reviewer_session) <= 100,
           "the independent reviewer session is required and is never chosen by this tool")
    refuse(isinstance(inputs.project_number, str) and re.fullmatch(r"[1-9][0-9]{0,19}", inputs.project_number),
           "the numeric cloud project number is required; read it from the live project, never from an example")
    refuse(isinstance(inputs.pool_id, str) and re.fullmatch(r"[a-z][a-z0-9-]{2,31}", inputs.pool_id),
           "the workload identity pool id is required and must be the observed pool")
    refuse(isinstance(inputs.pilot_manifest_sha256, str) and DIGEST.fullmatch(inputs.pilot_manifest_sha256),
           "the frozen pilot manifest digest is required as 64 hexadecimal characters")
    refuse(type(inputs.window_seconds) is int and 60 <= inputs.window_seconds <= 7200,
           "the authorization window must be between 60 and 7200 seconds")


# ------------------------------------------------------- observed the facts ---


def git_output(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=False, timeout=30)
    refuse(result.returncode == 0, f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def gh_json(path: str) -> object:
    result = subprocess.run(["gh", "api", path], capture_output=True, check=False, timeout=60)
    refuse(result.returncode == 0,
           f"GitHub could not be read ({path}). Sign in with `gh auth login` and try again.")
    return json.loads(result.stdout)


def current_main(github) -> tuple[str, str]:
    main = github(f"repos/{REPOSITORY}/commits/main")
    source_sha = main.get("sha")
    tree_sha = main.get("commit", {}).get("tree", {}).get("sha")
    refuse(isinstance(source_sha, str) and SHA.fullmatch(source_sha), "GitHub did not report a usable main commit")
    refuse(isinstance(tree_sha, str) and SHA.fullmatch(tree_sha), "GitHub did not report a usable main tree")
    return source_sha, tree_sha


def confirm_local_source(git, source_sha: str, tree_sha: str) -> None:
    """A packet minted against a stale checkout is the failure that blocks planes."""
    local = git("rev-parse", "origin/main")
    refuse(local == source_sha,
           "refusing to mint: this checkout is not at the current tip of main.\n"
           f"  GitHub main is {source_sha}\n"
           f"  origin/main here is {local}\n"
           "  Run `git fetch origin main` and mint again from the current tip. A packet bound to an\n"
           "  older commit is rejected at admission and blocks the release plane it was meant to open.")
    local_tree = git("rev-parse", f"{source_sha}^{{tree}}")
    refuse(local_tree == tree_sha,
           f"refusing to mint: the local tree for {source_sha} is {local_tree}, but GitHub reports {tree_sha}")


def confirm_unmoved(observed_sha: object, source_sha: str) -> None:
    """main moving mid-mint would bind the packet to a commit that is no longer the tip."""
    refuse(observed_sha == source_sha,
           f"main moved from {source_sha} to {observed_sha} while this packet was being assembled.\n"
           "  Nothing was written. Mint again against the new tip.")


def resolve_pull_request(github, source_sha: str) -> dict:
    listed = github(f"repos/{REPOSITORY}/commits/{source_sha}/pulls")
    refuse(isinstance(listed, list), "GitHub did not report pull requests for the candidate commit")
    merged = [entry for entry in listed
              if entry.get("merged_at") and entry.get("merge_commit_sha") == source_sha
              and entry.get("base", {}).get("ref") == "main"]
    refuse(len(merged) == 1,
           f"expected exactly one merged main pull request whose merge commit is {source_sha}; found {len(merged)}.\n"
           "  Production sources reach main only through a merged pull request.")
    return github(f"repos/{REPOSITORY}/pulls/{merged[0]['number']}")


def resolve_ci_run(github, source_sha: str) -> dict:
    listed = github(f"repos/{REPOSITORY}/actions/runs?head_sha={source_sha}&per_page=100")
    runs = [run for run in listed.get("workflow_runs", [])
            if run.get("path") == CI_WORKFLOW and run.get("event") == "push"
            and run.get("head_branch") == "main"]
    refuse(runs, f"no CI/CD push run on main was found for {source_sha}; the candidate has not been built")
    run = max(runs, key=lambda entry: entry.get("run_attempt", 0))
    refuse(run.get("status") == "completed",
           f"the CI/CD run {run.get('id')} for {source_sha} is still {run.get('status')}. Wait for it to finish.")
    refuse(run.get("conclusion") == "success",
           f"the CI/CD run {run.get('id')} for {source_sha} concluded {run.get('conclusion')!r}, not success.\n"
           "  Fix the failing check and let a new run finish. A failed gate is never minted around.")
    return run


def resolve_jobs(github, run: dict) -> list:
    jobs, run_id, attempt = [], run["id"], run["run_attempt"]
    for page in range(1, 101):
        result = github(f"repos/{REPOSITORY}/actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100&page={page}")
        jobs.extend(result["jobs"])
        if len(jobs) >= result["total_count"]:
            return jobs
    raise Refused("CI job pagination did not reconcile")


def derive_checks(jobs: list, source_sha: str, run: dict) -> dict:
    """Every required check is transcribed from the observed job, never asserted."""
    checks = {}
    for name in CHECKS:
        matches = [job for job in jobs if job.get("name") == name]
        refuse(len(matches) == 1, f"missing or ambiguous required check {name!r}: found {len(matches)} jobs")
        job = matches[0]
        refuse(job.get("status") == "completed" and job.get("conclusion") == "success",
               f"required check {name!r} is {job.get('status')}/{job.get('conclusion')!r}, not a successful gate")
        refuse(job.get("head_sha") == source_sha and job.get("run_id") == run["id"]
               and job.get("run_attempt") == run["run_attempt"],
               f"required check {name!r} did not run on this exact source and attempt")
        url = job.get("html_url") or ""
        if RUN_URL.fullmatch(url) is None:
            url = f"https://github.com/{REPOSITORY}/actions/runs/{run['id']}"
        checks[name] = {"source_sha": source_sha, "conclusion": "success", "run_url": url}
    return checks


def observed_snapshot(packet: dict, github) -> dict:
    """The same independent observation release admission performs for itself."""
    pull = github(f"repos/{REPOSITORY}/pulls/{packet['pull_request']}")
    run = github(f"repos/{REPOSITORY}/actions/runs/{packet['ci_run_id']}")
    return {"main": github(f"repos/{REPOSITORY}/commits/main"), "pull": pull,
            "pull_head": github(f"repos/{REPOSITORY}/commits/{pull['head']['sha']}"),
            "run": run, "jobs": resolve_jobs(github, run)}


def release_environment(packet: dict) -> dict:
    """The exact environment the protected release job will present."""
    environment, workflow, identity = PLANES[packet["plane"]]
    return {
        "GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": REPOSITORY,
        "GITHUB_REPOSITORY_ID": str(REPOSITORY_ID), "GITHUB_REPOSITORY_OWNER_ID": "140138196",
        "GITHUB_EVENT_NAME": "push", "GITHUB_REF": "refs/heads/main", "GITHUB_REF_PROTECTED": "true",
        "GITHUB_WORKFLOW_REF": f"{REPOSITORY}/.github/workflows/{workflow}@refs/heads/main",
        "GITHUB_SHA": packet["source_sha"],
        "GITHUB_RUN_ID": str(packet["release_run_id"]),
        "GITHUB_RUN_ATTEMPT": str(packet["release_run_attempt"]),
        "DEPLOYMENT_ENVIRONMENT": environment,
        "RELEASE_AUTHORIZED_SHA": packet["source_sha"], "RELEASE_PROJECT": PROJECT,
        "RELEASE_SERVICE_ACCOUNT": f"{identity}@{PROJECT}.iam.gserviceaccount.com",
    }


# ------------------------------------------------------- budget derivation ---


def budget_authority(ledger: dict, accept_legacy: bool) -> tuple[bool, int]:
    """Select the spending authority the ledger actually carries.

    The two dialects latch together: `release-cost-ledger/v3` pairs with
    `shared-release-reservations/v2` and the approved USD 12 ceiling; anything
    older pairs with v1 reservations and USD 5. Mixing them is not a smaller
    budget, it is a rejected packet, so the choice is made here and stated.
    """
    version = ledger.get("version")
    refuse(version in LEDGER_DIALECTS,
           f"unsupported shared cost ledger dialect {version!r}; expected one of {sorted(LEDGER_DIALECTS)}")
    if version == APPROVED_DIALECT:
        return True, APPROVED_LIMIT_MICROS
    refuse(accept_legacy,
           f"the shared budget ledger is {version!r}, not {APPROVED_DIALECT!r}.\n"
           f"  Only a {APPROVED_DIALECT!r} ledger can select shared-release-reservations/v2 and bind the\n"
           f"  approved USD 12 ceiling ({APPROVED_LIMIT_MICROS} micros). With this ledger the packet falls\n"
           f"  back to the legacy USD 5 authority ({LEGACY_LIMIT_MICROS} micros), and admission rejects any\n"
           "  reservation above it. Supply the approved v3 ledger, or pass --accept-legacy-budget to mint\n"
           "  deliberately under the older USD 5 authority.")
    return False, LEGACY_LIMIT_MICROS


def coordinator_session(ledger: dict, supplied: str | None) -> str:
    """v2/v3 ledgers name their own coordinator; a v1 ledger has no anchor."""
    anchor = ledger.get("accounting")
    observed = anchor.get("coordinator_task") if isinstance(anchor, dict) else None
    if isinstance(observed, str) and observed:
        refuse(supplied in (None, observed),
               f"the supplied coordinator session {supplied!r} is not the ledger's accounting coordinator {observed!r}")
        return observed
    refuse(isinstance(supplied, str) and 1 <= len(supplied) <= 100,
           "this ledger carries no accounting coordinator, so the coordinator session must be supplied")
    return supplied


def derive_reservations(ledger: dict, plane: str, run_id: int, attempt: int, basis_sha256: str) -> list:
    """Reservations are read out of the ledger; this tool never authors a figure."""
    held: dict[str, int] = {}
    for entry in ledger.get("entries", []):
        if not isinstance(entry, dict):
            continue
        if (entry.get("plane"), entry.get("run_id"), entry.get("run_attempt")) != (plane, run_id, attempt):
            continue
        refuse(entry.get("state") == "reserved",
               f"the ledger already records operation {entry.get('operation_id')!r} as {entry.get('state')!r}.\n"
               "  This run may already have spent. Reconcile the ledger; do not replay it.")
        held[entry["category"]] = held.get(entry["category"], 0) + entry["amount_micros"]
    refuse(held,
           f"the shared ledger holds no reserved rows for {plane} run {run_id} attempt {attempt}.\n"
           "  Reservations are a spending decision recorded by the coordinator before minting; this tool\n"
           "  reads them and will not create them. Reserve the cost first, then mint against that ledger.")
    missing = sorted(CATEGORIES - set(held))
    refuse(not missing,
           f"the ledger reserves only {len(held)} of {len(CATEGORIES)} required cost categories for this run.\n"
           f"  Missing: {', '.join(missing)}. Every category must be reserved once before a release is admitted.")
    return [{"category": category, "ceiling_micros": held[category], "basis_sha256": basis_sha256}
            for category in sorted(held)]


def build_budget(ledger: dict, ledger_sha: str, inputs: Inputs, basis_sha256: str) -> dict:
    amended, ceiling = budget_authority(ledger, inputs.accept_legacy_budget)
    anchor = ledger.get("accounting")
    if isinstance(anchor, dict) and isinstance(anchor.get("snapshot_json"), str):
        recorded = strict_json(anchor["snapshot_json"]).get("limit_micros")
        if type(recorded) is int and 0 < recorded < ceiling:
            ceiling = recorded
    reservations = derive_reservations(ledger, inputs.plane, inputs.release_run_id,
                                       inputs.release_run_attempt, basis_sha256)
    return {
        "version": "shared-release-reservations/v2" if amended else "shared-release-reservations/v1",
        **({"approval_sha256": APPROVAL_SHA256} if amended else {}),
        "currency": "USD", "scope": "entire_first_ten_all_sessions_and_retries",
        "manifest_sha256": inputs.pilot_manifest_sha256,
        "total_limit_micros": ceiling, "daily_limit_micros": ceiling,
        "ledger_sha256": ledger_sha, "resets_allowed": False, "reservations": reservations,
    }


# --------------------------------------------------- public candidate facts ---


def registry_images(source_sha: str, registry) -> dict:
    """Immutable digests read back from Artifact Registry, when the images exist."""
    resolved = {}
    for role in ("api", "worker", "sam"):
        described = registry(role, source_sha)
        refuse(isinstance(described, dict), f"Artifact Registry did not describe the {role} image")
        reference, provenance = described.get("reference"), described.get("provenance_sha256")
        refuse(isinstance(reference, str) and IMAGE.fullmatch(reference),
               f"Artifact Registry returned an unusable {role} image reference: {reference!r}")
        refuse(isinstance(provenance, str) and DIGEST.fullmatch(provenance),
               f"the {role} image has no usable provenance digest")
        resolved[role] = {"reference": reference, "provenance_sha256": provenance}
    return resolved


def gcloud_image(role: str, source_sha: str) -> dict:
    repository = f"us-east4-docker.pkg.dev/{PROJECT}/specimen-runtime/{role}"
    result = subprocess.run(
        ["gcloud", "artifacts", "docker", "images", "describe", f"{repository}:{source_sha}",
         "--show-provenance", "--format=json"], capture_output=True, text=True, check=False, timeout=120)
    refuse(result.returncode == 0,
           f"Artifact Registry could not describe the {role} image for {source_sha}.\n"
           f"  ({result.stderr.strip().splitlines()[-1] if result.stderr.strip() else 'no detail'})\n"
           "  Either the image has not been published yet, or this machine has no read access. Publish the\n"
           "  runtime images first, or record their digests in the evidence file instead of querying.")
    described = json.loads(result.stdout)
    digest = described.get("image_summary", {}).get("digest", "")
    provenance = described.get("provenance_summary", {}).get("provenance_sha256")
    return {"reference": f"{repository}@{digest}", "provenance_sha256": provenance}


def build_candidate(source_sha: str, checks: dict, inputs: Inputs) -> dict:
    """The public readiness packet: derived source facts plus recorded evidence."""
    supplied = inputs.candidate_evidence
    refuse(isinstance(supplied, dict), "the candidate evidence digests are required")
    images = (registry_images(source_sha, inputs.registry) if inputs.registry is not None
              else supplied.get("images", {}))
    refuse(isinstance(images, dict) and set(images) == {"api", "worker", "sam"},
           "image evidence is required for api, worker and sam")
    model = supplied.get("sam_model", {})
    refuse(isinstance(model, dict), "SAM model artifact digests are required")
    return {
        "version": 1, "repository": REPOSITORY, "project": PROJECT, "source_sha": source_sha,
        "images": {role: {"reference": images[role].get("reference"), "source_sha": source_sha,
                          "provenance_sha256": images[role].get("provenance_sha256")}
                   for role in ("api", "worker", "sam")},
        "data": supplied.get("data", {}),
        "pilot": {"specimen_count": 10, "manifest_sha256": inputs.pilot_manifest_sha256},
        "checks": checks,
        "approvals": supplied.get("approvals", {}),
        "public_config_sha256": supplied.get("public_config_sha256"),
        "rollback_sha256": supplied.get("rollback_sha256"),
        "sam_model": {"repository": SAM3_MODEL.repo_id, "revision": SAM3_MODEL.revision,
                      "artifacts_sha256": model.get("artifacts_sha256"),
                      "config_sha256": model.get("config_sha256")},
    }


# -------------------------------------------------------------------- mint ---


def mint(inputs: Inputs, *, github=gh_json, git=git_output, now=None) -> Minted:
    check_identity(inputs)
    now = time.time() if now is None else now
    notes = []

    source_sha, tree_sha = current_main(github)
    confirm_local_source(git, source_sha, tree_sha)
    pull = resolve_pull_request(github, source_sha)
    run = resolve_ci_run(github, source_sha)
    jobs = resolve_jobs(github, run)
    checks = derive_checks(jobs, source_sha, run)

    plan_raw = read_private(inputs.plan_path, "the deployment plan")
    authorization_raw = read_private(inputs.authorization_path, "the authorization artifact")
    review_raw = read_private(inputs.review_report_path, "the independent review report")
    ledger_raw = read_private(inputs.ledger_path, "the shared budget ledger")
    cost_review_raw = read_private(inputs.cost_review_path, "the cost review artifact")

    ledger = strict_json(ledger_raw)
    refuse(isinstance(ledger, dict), "the shared budget ledger must be a JSON object")
    refuse(ledger.get("manifest_sha256") == inputs.pilot_manifest_sha256,
           f"the ledger is for cohort {ledger.get('manifest_sha256')!r}, not the supplied pilot manifest\n"
           f"  {inputs.pilot_manifest_sha256!r}. One of the two is the wrong artifact; do not reconcile by editing.")
    budget = build_budget(ledger, sha256(ledger_raw), inputs, sha256(cost_review_raw))
    notes.append(f"budget authority: {budget['version']} at {budget['total_limit_micros']} micros total/daily")

    evidence = {"independent_review": review_raw.decode("utf-8"),
                "authorization": authorization_raw.decode("utf-8"),
                "shared_budget_ledger": ledger_raw.decode("utf-8")}
    refuse(set(evidence) == set(EVIDENCE_NAMES),
           "the bundle's evidence names must be exactly the three the release consumer restores")
    role = {"runtime-build": "runtime-build", "data-initialization": "data-initialize"}.get(
        inputs.plane, f"{inputs.plane}-release")
    packet = {
        "version": "protected-release/v1", "plane": inputs.plane,
        "repository": REPOSITORY, "project": PROJECT,
        "source_sha": source_sha, "source_tree_sha": tree_sha,
        "pull_request": pull["number"], "ci_run_id": run["id"], "ci_run_attempt": run["run_attempt"],
        "release_run_id": inputs.release_run_id, "release_run_attempt": inputs.release_run_attempt,
        "issued_at_unix": int(now), "expires_at_unix": int(now) + inputs.window_seconds,
        "authorization_sha256": sha256(authorization_raw),
        "independent_review": {
            "source_tree_sha": tree_sha, "reviewer_session": inputs.reviewer_session,
            "coordinator_session": coordinator_session(ledger, inputs.coordinator_session),
            "report_sha256": sha256(review_raw),
        },
        "identity": {
            "project_number": inputs.project_number, "pool_id": inputs.pool_id,
            "provider": (f"projects/{inputs.project_number}/locations/global/workloadIdentityPools/"
                         f"{inputs.pool_id}/providers/specimen-{role}"),
        },
        "pilot": {"specimen_count": 10, "manifest_sha256": inputs.pilot_manifest_sha256},
        "budget": budget, "plan_sha256": sha256(plan_raw),
        "evidence": {name: sha256(value.encode("utf-8")) for name, value in evidence.items()},
    }

    # Self-validation through the untouched consumers. None of these are relaxed.
    observed = observed_snapshot(packet, github)
    confirm_unmoved(observed["main"].get("sha"), source_sha)
    validate_admission(packet, release_environment(packet), observed, now=now)
    validate_cost_ledger(ledger, packet)
    candidate = build_candidate(source_sha, checks, inputs)
    try:
        validate(candidate, require_ready=True, expected_source_sha=source_sha)
    except ValueError as exc:
        raise Refused(
            f"the public readiness candidate is not complete: {exc}\n"
            "  Every listed item is real release evidence produced elsewhere. Record the missing digests\n"
            "  and mint again; this tool will not substitute a placeholder for any of them."
        ) from None

    packet_raw = canonical(packet)
    refuse(len(packet_raw) <= PACKET_MAX_BYTES, "the packet exceeds the release consumer's size limit")
    bundle_raw = canonical({"packet": packet_raw.decode("utf-8"), "plan": plan_raw.decode("utf-8"),
                            "evidence": evidence})
    secret = encode_release_inputs(bundle_raw)
    refuse(decode_release_inputs(secret) == bundle_raw, "the encoded bundle did not decode back to its own bytes")
    if secret.startswith("H4sI"):
        notes.append("the bundle is carried in the approved deterministic gzip envelope")

    confirm_unmoved(current_main(github)[0], source_sha)

    return Minted(packet=packet, packet_raw=packet_raw, plan_raw=plan_raw, evidence=evidence,
                  bundle_raw=bundle_raw, secret=secret, candidate=candidate,
                  candidate_raw=canonical(candidate), notes=notes,
                  variables={"RELEASE_AUTHORIZED_SHA": source_sha,
                             "RELEASE_PACKET_SHA256": sha256(packet_raw),
                             "RELEASE_BUDGET_LEDGER_SHA256": packet["budget"]["ledger_sha256"],
                             "RELEASE_INPUTS_SHA256": sha256(bundle_raw)})


# ------------------------------------------------------------------ output ---


def install_secret(destination: Path, secret: str) -> Path:
    """The one place a secret value is allowed to land: a private file, once."""
    destination = Path(destination)
    try:
        handle = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        raise Refused(f"refusing to overwrite {destination}. Choose a new path or remove the old file first.") from None
    except OSError as exc:
        raise Refused(f"could not create {destination}: {exc}") from None
    with os.fdopen(handle, "w") as output:
        output.write(secret)
    return destination


def write_candidate(destination: Path, minted: Minted) -> Path:
    destination = Path(destination)
    refuse(not destination.exists(), f"refusing to overwrite {destination}")
    destination.write_bytes(minted.candidate_raw)
    return destination


def report(minted: Minted, secret_path: Path, candidate_path: Path | None = None) -> None:
    """Print what has to be installed. The secret value itself is never printed."""
    packet = minted.packet
    environment = PLANES[packet["plane"]][0]
    print("\nMinted one release input bundle. Nothing has been deployed and nothing is authorized yet.\n")
    print(f"  plane                {packet['plane']}")
    print(f"  GitHub environment   {environment}")
    print(f"  source commit        {packet['source_sha']}")
    print(f"  merged pull request  #{packet['pull_request']}")
    print(f"  CI run               {packet['ci_run_id']} attempt {packet['ci_run_attempt']} "
          "(all five required checks green on this exact commit)")
    print(f"  release run          {packet['release_run_id']} attempt {packet['release_run_attempt']}")
    print(f"  valid for            {packet['expires_at_unix'] - packet['issued_at_unix']} seconds "
          f"(until unix {packet['expires_at_unix']})")
    for note in minted.notes:
        print(f"  note                 {note}")
    print(f"\nThe secret value was written to {secret_path}, readable only by you.")
    print("It is not printed here. Do not paste it into a chat, an issue, a commit or a log.\n")
    if candidate_path is not None:
        print(f"The public readiness candidate was written to {candidate_path}.\n")
    print(f"These belong to the {environment} environment, not to the repository as a whole:")
    print("  GitHub -> Settings -> Environments -> "
          f"{environment} -> Environment secrets / Environment variables\n")
    print("  One secret:")
    print(f"    gh secret set RELEASE_INPUTS_B64 --env {environment} \\")
    print(f"      --repo {REPOSITORY} < {secret_path}\n")
    print("  Four variables:")
    for name in ("RELEASE_INPUTS_SHA256", "RELEASE_PACKET_SHA256",
                 "RELEASE_BUDGET_LEDGER_SHA256", "RELEASE_AUTHORIZED_SHA"):
        print(f"    gh variable set {name} --env {environment} \\")
        print(f"      --repo {REPOSITORY} --body {minted.variables[name]}")
    print("\nThe release workflow refuses this bundle unless all five values agree, unless the release\n"
          f"run is exactly {packet['release_run_id']} attempt {packet['release_run_attempt']}, and\n"
          "unless it starts before the deadline above. Installing these values deploys nothing by itself.")


# --------------------------------------------------------------------- CLI ---


PROMPTS = {
    "plan_path": ("The deployment plan file",
                  "The typed plan for this plane: what will be built or applied, bound to the live\n"
                  "resource state it was written against. The coordinator produces it."),
    "authorization_path": ("The authorization artifact file",
                           "The private record of the approval for this release. Its digest becomes the\n"
                           "packet's authorization anchor, so the exact original bytes are required."),
    "review_report_path": ("The independent review report file",
                           "The report written by the reviewer who is not the coordinator, against this\n"
                           "exact source tree."),
    "ledger_path": ("The shared budget ledger file",
                    "The cumulative cost ledger for the whole pilot, across every session and retry.\n"
                    f"The approved USD 12 ceiling needs {APPROVED_DIALECT}."),
    "cost_review_path": ("The cost review artifact file",
                         "The reviewed basis for each category's reservation ceiling."),
    "reviewer_session": ("The independent reviewer's session id",
                         "Who reviewed this release, as their session identifier. It must not be the\n"
                         "coordinator: one person cannot be both sides of an independent review."),
    "coordinator_session": ("The coordinator's session id",
                            "Only needed when the ledger carries no accounting coordinator of its own.\n"
                            "Press Enter to read it from the ledger."),
    "project_number": ("The numeric Google Cloud project number",
                       "The number, not the name. Read it from the live project; an example number\n"
                       "will be rejected by the identity check."),
    "pool_id": ("The workload identity pool id",
                "The pool that issues the release job's short-lived credential, e.g. github-actions."),
    "pilot_manifest_sha256": ("The frozen pilot manifest digest",
                              "64 hexadecimal characters identifying the exact ten specimens. It must\n"
                              "match the cohort the budget ledger accounts for."),
}


def ask(name: str, *, required: bool = True) -> str | None:
    title, explanation = PROMPTS[name]
    print(f"\n{title}")
    for line in explanation.splitlines():
        print(f"  {line}")
    value = input("  > ").strip()
    if value:
        return value
    if required:
        raise Refused(f"{title} is required. Nothing was minted.")
    return None


def resolve(args: argparse.Namespace, name: str, *, required: bool = True):
    value = getattr(args, name, None)
    if value:
        return value
    if args.no_prompt:
        refuse(not required, f"--{name.replace('_', '-')} is required when prompting is disabled")
        return None
    return ask(name, required=required)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Assemble one release input bundle. This grants nothing and deploys nothing.")
    parser.add_argument("--plane", required=True, choices=sorted(PLANES))
    parser.add_argument("--release-run-id", type=int, required=True,
                        help="the GitHub run id of the release run this packet authorizes")
    parser.add_argument("--release-run-attempt", type=int, default=1)
    parser.add_argument("--secret-out", type=Path, required=True,
                        help="private file to write the RELEASE_INPUTS_B64 value into")
    parser.add_argument("--candidate-out", type=Path, help="where to write the public readiness candidate")
    parser.add_argument("--evidence-digests", type=Path, required=True,
                        help="JSON file of the release evidence digests this tool cannot observe")
    parser.add_argument("--window-seconds", type=int, default=1800)
    parser.add_argument("--accept-legacy-budget", action="store_true",
                        help="deliberately mint under the legacy USD 5 authority")
    parser.add_argument("--from-registry", action="store_true",
                        help="read image references from Artifact Registry instead of the evidence file")
    parser.add_argument("--no-prompt", action="store_true", help="fail instead of asking for a missing value")
    for name in PROMPTS:
        parser.add_argument(f"--{name.replace('_', '-')}", type=Path if name.endswith("_path") else str)
    args = parser.parse_args(argv)

    try:
        evidence_path = Path(args.evidence_digests)
        refuse(evidence_path.is_file(), f"the evidence digest file is required: {evidence_path}")
        inputs = Inputs(
            plane=args.plane, release_run_id=args.release_run_id,
            release_run_attempt=args.release_run_attempt,
            plan_path=resolve(args, "plan_path"),
            authorization_path=resolve(args, "authorization_path"),
            review_report_path=resolve(args, "review_report_path"),
            ledger_path=resolve(args, "ledger_path"),
            cost_review_path=resolve(args, "cost_review_path"),
            reviewer_session=resolve(args, "reviewer_session"),
            coordinator_session=resolve(args, "coordinator_session", required=False),
            project_number=resolve(args, "project_number"),
            pool_id=resolve(args, "pool_id"),
            pilot_manifest_sha256=resolve(args, "pilot_manifest_sha256"),
            candidate_evidence=json.loads(evidence_path.read_text()),
            window_seconds=args.window_seconds,
            accept_legacy_budget=args.accept_legacy_budget,
            registry=gcloud_image if args.from_registry else None,
        )
        minted = mint(inputs)
        secret_path = install_secret(args.secret_out, minted.secret)
        candidate_path = write_candidate(args.candidate_out, minted) if args.candidate_out else None
        report(minted, secret_path, candidate_path)
    except Refused as exc:
        print(f"\nNothing was minted.\n\n{exc}\n", file=sys.stderr)
        return 1
    except (ValueError, OSError) as exc:
        print(f"\nNothing was minted.\n\n{exc}\n", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
