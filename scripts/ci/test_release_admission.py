"""Executable negative tests for the real release authorization boundary."""
import copy
import hashlib
import importlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent))
MODULE = importlib.import_module("release_admission")
REPOSITORY = "anurag-duddu/specimen-digitization-app"
SHA = "a" * 40
TREE = "d" * 40
NOW = 1788890400


def packet(plane="runtime"):
    return {
        "version": "protected-release/v1", "plane": plane,
        "repository": REPOSITORY, "project": "specimen-digitization",
        "source_sha": SHA, "source_tree_sha": TREE, "pull_request": 15,
        "ci_run_id": 123, "ci_run_attempt": 1, "release_run_id": 456, "release_run_attempt": 1,
        "issued_at_unix": NOW - 10, "expires_at_unix": NOW + 1200,
        "authorization_sha256": "1" * 64,
        "independent_review": {
            "source_tree_sha": TREE, "reviewer_session": "independent-session",
            "coordinator_session": "coordinator-session", "report_sha256": "2" * 64,
        },
        "identity": {
            "project_number": "123456789", "pool_id": "github-actions",
            "provider": f"projects/123456789/locations/global/workloadIdentityPools/github-actions/providers/specimen-{plane}-release",
        },
        "pilot": {"specimen_count": 10, "manifest_sha256": "3" * 64},
        "budget": {
            "version": "shared-release-reservations/v1", "currency": "USD",
            "scope": "entire_first_ten_all_sessions_and_retries", "manifest_sha256": "3" * 64,
            "total_limit_micros": 5000000, "daily_limit_micros": 5000000,
            "ledger_sha256": "4" * 64, "resets_allowed": False,
            "reservations": [{"category": category, "ceiling_micros": 100000,
                              "basis_sha256": "5" * 64} for category in sorted(MODULE.CATEGORIES)],
        },
        "plan_sha256": "6" * 64,
        "evidence": {"independent_review": "2" * 64, "authorization": "1" * 64,
                     "shared_budget_ledger": "4" * 64},
    }


def environment(p):
    plane = p["plane"]
    return {
        "GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": REPOSITORY,
        "GITHUB_REPOSITORY_ID": "1360732425", "GITHUB_REPOSITORY_OWNER_ID": "140138196",
        "GITHUB_EVENT_NAME": "push", "GITHUB_REF": "refs/heads/main", "GITHUB_REF_PROTECTED": "true",
        "GITHUB_WORKFLOW_REF": f"{REPOSITORY}/.github/workflows/{plane}-release.yml@refs/heads/main",
        "GITHUB_SHA": SHA, "GITHUB_RUN_ID": "456", "GITHUB_RUN_ATTEMPT": "1", "DEPLOYMENT_ENVIRONMENT": f"{plane}-production",
        "RELEASE_AUTHORIZED_SHA": SHA, "RELEASE_PROJECT": "specimen-digitization",
        "RELEASE_SERVICE_ACCOUNT": f"specimen-{plane}-release@specimen-digitization.iam.gserviceaccount.com",
        "RELEASE_PACKET_SHA256": hashlib.sha256(json.dumps(p).encode()).hexdigest(),
    }


def snapshot():
    return {
        "main": {"sha": SHA, "commit": {"tree": {"sha": TREE}}},
        "pull": {"number": 15, "merged": True, "merge_commit_sha": SHA,
                 "base": {"ref": "main", "repo": {"id": 1360732425}},
                 "head": {"sha": "e" * 40, "repo": {"id": 1360732425}}},
        "pull_head": {"sha": "e" * 40, "commit": {"tree": {"sha": TREE}}},
        "run": {"id": 123, "run_attempt": 1, "head_sha": SHA, "head_branch": "main",
                "event": "push", "path": ".github/workflows/ci-cd.yml", "status": "completed", "conclusion": "success",
                "repository": {"id": 1360732425}, "head_repository": {"id": 1360732425}},
        "jobs": [{"name": name, "status": "completed", "conclusion": "success", "head_sha": SHA,
                  "run_id": 123, "run_attempt": 1} for name in MODULE.CHECKS],
    }


@pytest.mark.parametrize("plane", ["runtime", "data"])
def test_exact_authorized_private_packet_and_independent_github_observations(plane):
    p = packet(plane)
    assert MODULE.validate_admission(p, environment(p), snapshot(), now=NOW) == p


@pytest.mark.parametrize("field,value", [
    ("GITHUB_ACTIONS", "false"), ("GITHUB_EVENT_NAME", "workflow_dispatch"),
    ("GITHUB_EVENT_NAME", "workflow_run"), ("GITHUB_EVENT_NAME", "pull_request"),
    ("GITHUB_REF", "refs/heads/feature"), ("GITHUB_REF_PROTECTED", "false"),
    ("GITHUB_REPOSITORY_ID", "1"), ("GITHUB_REPOSITORY_OWNER_ID", "1"),
    ("GITHUB_REPOSITORY", "fork/repo"), ("GITHUB_SHA", "b" * 40),
    ("RELEASE_AUTHORIZED_SHA", "b" * 40), ("DEPLOYMENT_ENVIRONMENT", "production"),
    ("RELEASE_SERVICE_ACCOUNT", "github-firebase-hosting@specimen-digitization.iam.gserviceaccount.com"),
])
def test_untrusted_context_is_rejected_before_credentials(field, value):
    p = packet()
    env = environment(p)
    env[field] = value
    with pytest.raises(ValueError):
        MODULE.validate_admission(p, env, snapshot(), now=NOW)


@pytest.mark.parametrize("section,field,value", [
    ("main", "sha", "b" * 40), ("pull", "merged", False),
    ("pull", "merge_commit_sha", "b" * 40), ("pull", "number", 16),
    ("run", "head_sha", "b" * 40), ("run", "event", "pull_request"),
    ("run", "path", ".github/workflows/spoof.yml"), ("run", "run_attempt", 2),
    ("run", "head_branch", "feature"), ("run", "status", "in_progress"),
])
def test_live_github_facts_cannot_be_replaced_with_packet_claims(section, field, value):
    p = packet()
    observed = snapshot()
    observed[section][field] = value
    with pytest.raises(ValueError):
        MODULE.validate_admission(p, environment(p), observed, now=NOW)


@pytest.mark.parametrize("field,value", [
    ("conclusion", "skipped"), ("conclusion", "neutral"), ("conclusion", "failure"),
    ("conclusion", "cancelled"), ("status", "in_progress"),
    ("head_sha", "b" * 40), ("run_id", 456), ("run_attempt", 2),
])
def test_every_exact_source_platform_check_must_pass(field, value):
    p = packet()
    for index in range(5):
        observed = snapshot()
        observed["jobs"][index][field] = value
        with pytest.raises(ValueError):
            MODULE.validate_admission(p, environment(p), observed, now=NOW)


def test_missing_duplicate_or_conflicting_jobs_fail_closed():
    p = packet()
    for change in (lambda jobs: jobs.pop(), lambda jobs: jobs.append(copy.deepcopy(jobs[0]))):
        observed = snapshot()
        change(observed["jobs"])
        with pytest.raises(ValueError):
            MODULE.validate_admission(p, environment(p), observed, now=NOW)


@pytest.mark.parametrize("change", [
    lambda p: p.update(expires_at_unix=NOW),
    lambda p: p.update(issued_at_unix=NOW + 1),
    lambda p: p.update(expires_at_unix=NOW + 7201),
    lambda p: p["pilot"].update(specimen_count=11),
    lambda p: p["independent_review"].update(source_tree_sha="b" * 40),
    lambda p: p["independent_review"].update(reviewer_session="coordinator-session"),
    lambda p: p["identity"].update(provider=p["identity"]["provider"].replace("runtime", "data")),
    lambda p: p["identity"].update(project_number="987654321"),
    lambda p: p["evidence"].update(authorization="f" * 64),
    lambda p: p.update(arbitrary_command="echo bad"),
])
def test_deadline_source_independent_review_cohort_and_identity_bounds(change):
    p = packet()
    change(p)
    with pytest.raises(ValueError):
        MODULE.validate_admission(p, environment(p), snapshot(), now=NOW)


@pytest.mark.parametrize("change", [
    lambda b: b.update(total_limit_micros=5000001),
    lambda b: b.update(daily_limit_micros=5000001),
    lambda b: b.update(total_limit_micros=True),
    lambda b: b.update(resets_allowed=True),
    lambda b: b.update(scope="per_session"),
    lambda b: b.update(manifest_sha256="b" * 64),
    lambda b: b["reservations"].pop(),
    lambda b: b["reservations"].append(copy.deepcopy(b["reservations"][0])),
    lambda b: b["reservations"][0].update(ceiling_micros=-1),
    lambda b: b["reservations"][0].update(ceiling_micros=5000000),
    lambda b: b["reservations"][0].update(basis_sha256=None),
])
def test_all_cloud_and_provider_categories_share_one_nonresettable_five_dollar_budget(change):
    p = packet()
    change(p["budget"])
    with pytest.raises(ValueError):
        MODULE.validate_admission(p, environment(p), snapshot(), now=NOW)


def test_private_bytes_require_external_digest_and_do_not_print_content(tmp_path):
    p = packet()
    path = tmp_path / "packet.json"
    path.write_text(json.dumps(p))
    path.chmod(0o600)
    assert MODULE.read_packet(path, environment(p)) == p
    path.write_text(json.dumps(p) + " ")
    with pytest.raises(ValueError, match="digest"):
        MODULE.read_packet(path, environment(p))


def test_evidence_files_are_required_and_hash_checked_without_symlink_escape(tmp_path):
    p = packet()
    directory = tmp_path / "evidence"
    directory.mkdir()
    for name in p["evidence"]:
        (directory / f"{name}.json").write_text("retained original evidence")
    with pytest.raises(ValueError, match="evidence"):
        MODULE.verify_evidence(p, directory)


def test_a_workflow_rerun_cannot_reuse_spend_authority_without_reconciliation():
    p = packet()
    env = environment(p)
    env["GITHUB_RUN_ATTEMPT"] = "2"
    with pytest.raises(ValueError, match="release run"):
        MODULE.validate_admission(p, env, snapshot(), now=NOW)


def ledger(p):
    return {"version": "release-cost-ledger/v1", "currency": "USD", "manifest_sha256": p["pilot"]["manifest_sha256"],
            "scope": "entire_first_ten_all_sessions_and_retries", "entries": [
                {"operation_id": f"runtime-456-1-{e['category']}", "plane": "runtime", "run_id": 456, "run_attempt": 1,
                 "category": e["category"], "state": "reserved", "amount_micros": e["ceiling_micros"], "day_utc": "2026-09-08"}
                for e in p["budget"]["reservations"]]}


def test_already_spent_shared_ledger_cannot_be_reset_by_another_plane_or_day():
    p = packet()
    cost = ledger(p)
    MODULE.validate_cost_ledger(cost, p)
    cost["entries"].append({"operation_id": "earlier-data-operation", "plane": "data", "run_id": 111, "run_attempt": 1,
                            "category": "restore", "state": "settled", "amount_micros": 5000000, "day_utc": "2026-09-07"})
    with pytest.raises(ValueError, match="cumulative"):
        MODULE.validate_cost_ledger(cost, p)


def test_missing_reservation_unknown_zero_and_duplicate_operation_are_not_available_budget():
    p = packet()
    for change in (lambda entries: entries.pop(), lambda entries: entries.append(copy.deepcopy(entries[0])),
                   lambda entries: entries[0].update(state="unknown", amount_micros=0)):
        cost = ledger(p)
        change(cost["entries"])
        with pytest.raises(ValueError):
            MODULE.validate_cost_ledger(cost, p)


def test_completed_but_failed_main_ci_is_not_a_release_gate():
    p = packet()
    observed = snapshot()
    observed["run"]["conclusion"] = "failure"
    with pytest.raises(ValueError):
        MODULE.validate_admission(p, environment(p), observed, now=NOW)


def test_duplicate_json_keys_are_rejected_before_authorization_parsing():
    with pytest.raises(ValueError, match="duplicate"):
        MODULE.strict_json('{"source_sha":"first","source_sha":"second"}')


def test_private_bytes_reject_symlinks_and_oversized_reads(tmp_path):
    target = tmp_path / "private"
    target.write_bytes(b"12345")
    target.chmod(0o600)
    link = tmp_path / "alias"
    link.symlink_to(target)
    with pytest.raises((ValueError, OSError)):
        MODULE.private_bytes(link)
    with pytest.raises(ValueError):
        MODULE.private_bytes(target, limit=4)
