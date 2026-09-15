"""Executable guarantees for the release packet generator.

The generator exists to make the existing admission gate usable, never easier to
pass. Every test here asserts a refusal, a derivation, or a binding; none of them
assert that a packet is admitted. Admission remains the workflow's decision.
"""
import base64
import copy
import hashlib
import importlib
import json
from pathlib import Path
import stat
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent))
MINT = importlib.import_module("mint_release_packet")
ADMISSION = importlib.import_module("release_admission")
PACKET = importlib.import_module("validate_release_packet")

REPOSITORY = "anurag-duddu/specimen-digitization-app"
SOURCE = "a" * 40
TREE = "d" * 40
HEAD = "e" * 40
NOW = 1788890400.0
COORDINATOR = "01a082b2-c2c3-70d2-be90-7bfb622c9102"
REVIEWER = "01a082b4-a9bc-7413-a3c5-505b61c2f4db"
PROJECT_NUMBER = "716045864126"
MANIFEST = "3" * 64
RUN, ATTEMPT = 456, 1
CI_RUN, CI_ATTEMPT = 123, 1


# ---------------------------------------------------------------- fixtures ---


def ledger_entries(categories, *, plane="runtime", run=RUN, attempt=ATTEMPT, ceiling=100000):
    return [{"operation_id": f"{plane}-{run}-{attempt}-{category}", "plane": plane,
             "run_id": run, "run_attempt": attempt, "category": category, "state": "reserved",
             "amount_micros": ceiling, "day_utc": "2026-09-08"} for category in sorted(categories)]


def ledger(version="release-cost-ledger/v1", **overrides):
    value = {"version": version, "currency": "USD", "manifest_sha256": MANIFEST,
             "scope": "entire_first_ten_all_sessions_and_retries",
             "entries": ledger_entries(ADMISSION.CATEGORIES)}
    value.update(overrides)
    return value


def candidate_evidence():
    """Digests the generator cannot derive; every one is a real release artifact."""
    return {
        "images": {role: {"reference": f"us-east4-docker.pkg.dev/specimen-digitization/"
                                       f"specimen-runtime/{role}@sha256:{'b' * 64}",
                          "provenance_sha256": "c" * 64} for role in ("api", "worker", "sam")},
        "sam_model": {"artifacts_sha256": "1" * 64, "config_sha256": "2" * 64},
        "data": {key: "4" * 64 for key in ("schema_sha256", "connector_sha256", "storage_rules_sha256",
                                           "backup_restore_evidence_sha256", "compatibility_evidence_sha256")},
        "approvals": {key: "5" * 64 for key in ("contract_sha256", "bootstrap_sha256",
                                                "budget_sha256", "provider_data_sha256")},
        "public_config_sha256": "6" * 64,
        "rollback_sha256": "7" * 64,
    }


def github_facts(*, main_sha=SOURCE, conclusion="success", jobs=None):
    checks = [{"name": name, "status": "completed", "conclusion": "success", "head_sha": SOURCE,
               "run_id": CI_RUN, "run_attempt": CI_ATTEMPT,
               "html_url": f"https://github.com/{REPOSITORY}/actions/runs/{CI_RUN}/job/{700 + index}"}
              for index, name in enumerate(sorted(PACKET.CHECKS))]
    return {
        f"repos/{REPOSITORY}/commits/main": {"sha": main_sha, "commit": {"tree": {"sha": TREE}}},
        f"repos/{REPOSITORY}/commits/{SOURCE}/pulls": [
            {"number": 15, "merged_at": "2026-09-08T00:00:00Z", "merge_commit_sha": SOURCE,
             "base": {"ref": "main"}, "head": {"sha": HEAD}}],
        f"repos/{REPOSITORY}/pulls/15": {
            "number": 15, "merged": True, "merge_commit_sha": SOURCE,
            "base": {"ref": "main", "repo": {"id": 1360732425}},
            "head": {"sha": HEAD, "repo": {"id": 1360732425}}},
        f"repos/{REPOSITORY}/commits/{HEAD}": {"sha": HEAD, "commit": {"tree": {"sha": TREE}}},
        f"repos/{REPOSITORY}/actions/runs?head_sha={SOURCE}&per_page=100": {"total_count": 1, "workflow_runs": [
            {"id": CI_RUN, "run_attempt": CI_ATTEMPT, "head_sha": SOURCE, "head_branch": "main",
             "event": "push", "path": ".github/workflows/ci-cd.yml", "status": "completed",
             "conclusion": conclusion, "repository": {"id": 1360732425},
             "head_repository": {"id": 1360732425}}]},
        f"repos/{REPOSITORY}/actions/runs/{CI_RUN}": {
            "id": CI_RUN, "run_attempt": CI_ATTEMPT, "head_sha": SOURCE, "head_branch": "main",
            "event": "push", "path": ".github/workflows/ci-cd.yml", "status": "completed",
            "conclusion": conclusion, "repository": {"id": 1360732425},
            "head_repository": {"id": 1360732425}},
        f"repos/{REPOSITORY}/actions/runs/{CI_RUN}/attempts/{CI_ATTEMPT}/jobs?per_page=100&page=1": {
            "total_count": len(checks), "jobs": checks if jobs is None else jobs},
    }


def fake_github(facts):
    def call(path):
        if path not in facts:
            raise ValueError(f"unexpected GitHub request: {path}")
        return copy.deepcopy(facts[path])
    return call


def fake_git(tip=SOURCE, tree=TREE):
    return lambda *args: {("rev-parse", "origin/main"): tip,
                          ("rev-parse", f"{SOURCE}^{{tree}}"): tree,
                          ("rev-parse", f"{tip}^{{tree}}"): tree}[args]


def inputs(tmp_path, *, cost_ledger=None, **overrides):
    cost_ledger = ledger() if cost_ledger is None else cost_ledger
    files = {
        "plan": json.dumps({"version": "runtime-prepare/v1", "source_sha": SOURCE}).encode(),
        "authorization": b'{"version":"release-authorization/v1"}',
        "review_report": b'{"version":"independent-review/v1"}',
        "ledger": (json.dumps(cost_ledger, sort_keys=True, separators=(",", ":")) + "\n").encode(),
        "cost_review": b'{"version":"cohort-budget/v2"}',
    }
    paths = {}
    for name, raw in files.items():
        path = tmp_path / f"{name}.json"
        path.write_bytes(raw)
        path.chmod(0o600)
        paths[name] = path
    values = {
        "plane": "runtime", "release_run_id": RUN, "release_run_attempt": ATTEMPT,
        "plan_path": paths["plan"], "authorization_path": paths["authorization"],
        "review_report_path": paths["review_report"], "ledger_path": paths["ledger"],
        "cost_review_path": paths["cost_review"], "reviewer_session": REVIEWER,
        "coordinator_session": COORDINATOR,
        "project_number": PROJECT_NUMBER, "pool_id": "github-actions",
        "pilot_manifest_sha256": MANIFEST, "candidate_evidence": candidate_evidence(),
        "window_seconds": 1800, "accept_legacy_budget": True,
    }
    values.update(overrides)
    return MINT.Inputs(**values)


def mint(tmp_path, *, facts=None, git=None, **overrides):
    return MINT.mint(inputs(tmp_path, **overrides),
                     github=fake_github(github_facts() if facts is None else facts),
                     git=fake_git() if git is None else git, now=NOW)


# ------------------------------------------------------- the happy contract ---


def test_minted_bundle_is_exactly_what_the_release_workflow_will_restore(tmp_path):
    minted = mint(tmp_path)
    raw = ADMISSION.decode_release_inputs(minted.secret)
    assert hashlib.sha256(raw).hexdigest() == minted.variables["RELEASE_INPUTS_SHA256"]
    bundle = json.loads(raw)
    assert set(bundle) == {"packet", "plan", "evidence"}
    assert set(bundle["evidence"]) == {"independent_review", "authorization", "shared_budget_ledger"}
    packet = json.loads(bundle["packet"])
    assert hashlib.sha256(bundle["packet"].encode()).hexdigest() == minted.variables["RELEASE_PACKET_SHA256"]
    assert packet["evidence"] == {name: hashlib.sha256(value.encode()).hexdigest()
                                  for name, value in bundle["evidence"].items()}
    assert minted.variables["RELEASE_BUDGET_LEDGER_SHA256"] == packet["budget"]["ledger_sha256"]


def test_minted_packet_satisfies_the_untouched_admission_validator(tmp_path):
    minted = mint(tmp_path)
    environment = MINT.release_environment(minted.packet)
    observed = MINT.observed_snapshot(minted.packet, fake_github(github_facts()))
    assert ADMISSION.validate_admission(minted.packet, environment, observed, now=NOW) == minted.packet
    ADMISSION.validate_cost_ledger(json.loads(minted.evidence["shared_budget_ledger"]), minted.packet)


def test_minted_candidate_satisfies_the_untouched_readiness_validator(tmp_path):
    minted = mint(tmp_path)
    assert PACKET.validate(minted.candidate, require_ready=True, expected_source_sha=SOURCE) == []


def test_derived_facts_come_from_git_and_github_not_from_the_operator(tmp_path):
    packet = mint(tmp_path).packet
    assert packet["source_sha"] == SOURCE and packet["source_tree_sha"] == TREE
    assert packet["pull_request"] == 15
    assert packet["ci_run_id"] == CI_RUN and packet["ci_run_attempt"] == CI_ATTEMPT
    assert packet["issued_at_unix"] == int(NOW)
    assert packet["expires_at_unix"] == int(NOW) + 1800


def test_every_required_check_is_recorded_from_the_observed_ci_jobs(tmp_path):
    checks = mint(tmp_path).candidate["checks"]
    assert set(checks) == PACKET.CHECKS
    for name, entry in checks.items():
        assert entry["conclusion"] == "success" and entry["source_sha"] == SOURCE
        assert entry["run_url"].startswith(f"https://github.com/{REPOSITORY}/actions/runs/{CI_RUN}")


def test_reservations_are_read_out_of_the_ledger_not_authored(tmp_path):
    reservations = mint(tmp_path).packet["budget"]["reservations"]
    assert {entry["category"] for entry in reservations} == ADMISSION.CATEGORIES
    assert all(entry["ceiling_micros"] == 100000 for entry in reservations)


def test_a_ledger_that_names_its_coordinator_is_believed_over_the_operator():
    cost = ledger(version="release-cost-ledger/v2", accounting={"coordinator_task": COORDINATOR})
    assert MINT.coordinator_session(cost, None) == COORDINATOR
    assert MINT.coordinator_session(cost, COORDINATOR) == COORDINATOR
    with pytest.raises(MINT.Refused, match="coordinator"):
        MINT.coordinator_session(cost, REVIEWER)


def test_a_ledger_without_an_accounting_anchor_demands_the_coordinator():
    with pytest.raises(MINT.Refused, match="coordinator"):
        MINT.coordinator_session(ledger(), None)


# ------------------------------------------------- refusals that must stand ---


def test_a_packet_is_never_minted_against_a_stale_main(tmp_path):
    with pytest.raises(MINT.Refused, match="tip of main"):
        mint(tmp_path, git=fake_git(tip="f" * 40))


def test_main_moving_during_minting_is_caught_before_anything_is_returned(tmp_path):
    facts = github_facts()
    calls = {"count": 0}
    original = fake_github(facts)

    def moving(path):
        if path.endswith("/commits/main"):
            calls["count"] += 1
            if calls["count"] > 1:
                return {"sha": "f" * 40, "commit": {"tree": {"sha": TREE}}}
        return original(path)

    with pytest.raises(MINT.Refused, match="moved"):
        MINT.mint(inputs(tmp_path), github=moving, git=fake_git(), now=NOW)


def test_incomplete_ci_is_not_a_release_gate(tmp_path):
    with pytest.raises(MINT.Refused, match="CI"):
        mint(tmp_path, facts=github_facts(conclusion="failure"))


def test_a_missing_required_check_cannot_be_filled_in(tmp_path):
    facts = github_facts()
    key = f"repos/{REPOSITORY}/actions/runs/{CI_RUN}/attempts/{CI_ATTEMPT}/jobs?per_page=100&page=1"
    facts[key]["jobs"] = facts[key]["jobs"][:-1]
    facts[key]["total_count"] = len(facts[key]["jobs"])
    with pytest.raises(MINT.Refused, match="check"):
        mint(tmp_path, facts=facts)


@pytest.mark.parametrize("field", ["authorization_path", "review_report_path", "ledger_path",
                                   "plan_path", "cost_review_path"])
def test_an_absent_private_artifact_is_a_hard_stop_not_a_placeholder(tmp_path, field):
    with pytest.raises(MINT.Refused, match="required|missing|unreadable"):
        mint(tmp_path, **{field: tmp_path / "absent.json"})


@pytest.mark.parametrize("field,value", [
    ("reviewer_session", ""), ("reviewer_session", None),
    ("project_number", ""), ("project_number", "0"), ("pool_id", "X"),
    ("pilot_manifest_sha256", ""), ("pilot_manifest_sha256", "not-a-digest"),
])
def test_no_private_value_is_ever_invented_or_defaulted(tmp_path, field, value):
    with pytest.raises((MINT.Refused, ValueError)):
        mint(tmp_path, **{field: value})


def test_the_reviewer_may_not_be_the_coordinator(tmp_path):
    with pytest.raises((MINT.Refused, ValueError), match="reviewer|independent"):
        mint(tmp_path, coordinator_session=REVIEWER)


def test_a_pilot_manifest_that_disagrees_with_the_ledger_is_refused(tmp_path):
    with pytest.raises(MINT.Refused, match="manifest"):
        mint(tmp_path, pilot_manifest_sha256="9" * 64)


def test_reservations_are_never_invented_when_the_ledger_holds_none(tmp_path):
    with pytest.raises(MINT.Refused, match="reserv"):
        mint(tmp_path, cost_ledger=ledger(entries=[]))


def test_a_partial_reservation_set_cannot_be_completed_by_the_generator(tmp_path):
    partial = sorted(ADMISSION.CATEGORIES)[:-1]
    with pytest.raises((MINT.Refused, ValueError), match="categor|reserv"):
        mint(tmp_path, cost_ledger=ledger(entries=ledger_entries(partial)))


# ------------------------------------------------ the USD 12 approval latch ---


def test_a_v3_ledger_binds_the_approved_twelve_dollar_authority():
    assert MINT.budget_authority(ledger(version="release-cost-ledger/v3"), False) == (
        True, MINT.APPROVED_LIMIT_MICROS)


@pytest.mark.parametrize("version", ["release-cost-ledger/v1", "release-cost-ledger/v2"])
def test_a_legacy_ledger_never_silently_produces_the_approved_ceiling(version):
    assert MINT.budget_authority(ledger(version=version), True) == (False, MINT.LEGACY_LIMIT_MICROS)


def test_the_approved_ceiling_is_carried_into_the_packet_only_with_its_approval(tmp_path):
    budget = mint(tmp_path).packet["budget"]
    assert budget["version"] == "shared-release-reservations/v1"
    assert "approval_sha256" not in budget
    assert budget["total_limit_micros"] == MINT.LEGACY_LIMIT_MICROS


def test_the_legacy_five_dollar_fallback_must_be_accepted_out_loud(tmp_path):
    with pytest.raises(MINT.Refused, match="release-cost-ledger/v3"):
        mint(tmp_path, accept_legacy_budget=False)


@pytest.mark.parametrize("version", ["release-cost-ledger/v9", "", None])
def test_an_unknown_ledger_dialect_is_refused_outright(version):
    with pytest.raises(MINT.Refused, match="ledger dialect"):
        MINT.budget_authority(ledger(version=version), True)


# ------------------------------------------------------- secret containment ---


def test_the_secret_lands_only_in_a_private_file_the_operator_named(tmp_path, capsys):
    minted = mint(tmp_path)
    destination = tmp_path / "release-inputs.b64"
    MINT.install_secret(destination, minted.secret)
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert destination.read_text() == minted.secret
    MINT.report(minted, destination)
    printed = capsys.readouterr().out
    assert minted.secret not in printed
    assert minted.variables["RELEASE_INPUTS_SHA256"] in printed
    assert str(destination) in printed


def test_an_existing_secret_file_is_never_silently_overwritten(tmp_path):
    destination = tmp_path / "release-inputs.b64"
    destination.write_text("previous")
    with pytest.raises(MINT.Refused, match="overwrite"):
        MINT.install_secret(destination, "value")
    assert destination.read_text() == "previous"


def test_nothing_is_reported_when_the_readiness_validator_rejects_the_candidate(tmp_path):
    evidence = candidate_evidence()
    evidence["approvals"]["budget_sha256"] = None
    with pytest.raises(MINT.Refused, match="incomplete candidate|budget_sha256"):
        mint(tmp_path, candidate_evidence=evidence)


def test_the_bundle_fits_the_single_github_secret(tmp_path):
    minted = mint(tmp_path)
    assert 0 < len(minted.secret) <= ADMISSION.INPUT_SECRET_MAX_BYTES
    assert base64.b64decode(minted.secret, validate=True)
