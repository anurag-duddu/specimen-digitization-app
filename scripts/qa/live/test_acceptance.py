"""Adversarial tests of the QA gate; all identifiers and artifacts are authored fixtures."""

import copy
import json

import pytest

from acceptance import (
    CASES,
    InvalidEvidence,
    artifact,
    evaluate,
    file_digest,
    manifest_ids,
    read_json,
    skeleton,
)


CANDIDATE = "a" * 40
MANIFEST_SHA = "b" * 64


def specimen_id(i):
    return f"00000000-0000-4000-8000-{i:012d}"


def manifest():
    return {
        "schema_version": "specimen-pilot/v1",
        "status": "ready",
        "project_id": "specimen-digitization",
        "authorization_reference": "fixture-only-no-authorization",
        "selection": {
            "order": "explicit_source_order",
            "source_inventory_sha256": "e" * 64,
        },
        "specimens": [
            {
                "ordinal": i,
                "specimen_id": specimen_id(i),
                "organization_id": specimen_id(100),
                "collection_id": specimen_id(101),
                "source_objects": [
                    {
                        "bucket": "fixture-only",
                        "object_name": f"fixture-{i}.png",
                        "generation": "1",
                        "sha256": f"{i:064x}",
                        "size_bytes": 123,
                    }
                ],
                "application_source": {
                    "blob_ref": f"{i:064x}:2",
                    "sha256": f"{i:064x}",
                    "size_bytes": 123,
                    "source_object_index": 0,
                },
            }
            for i in range(1, 11)
        ],
    }


CATEGORIES = (
    "provider", "api", "worker", "sam", "build", "storage", "network",
    "restore", "identity", "secrets", "telemetry",
)


def budget(root):
    evidence = root / "budget-fixture.txt"
    evidence.write_text("Authored budget fixture, not billing evidence.\n")
    return {
        "schema_version": "cohort-budget/v1",
        "currency": "USD",
        "manifest_sha256": MANIFEST_SHA,
        "authorization_reference": "fixture-only-shared-authorization",
        "scope": "entire_first_ten_all_sessions_and_retries",
        "mode": "live",  # Claimed live only to test validator mechanics.
        "total_limit_microusd": 5_000_000,
        "daily_limit_microusd": 5_000_000,
        "categories": {
            category: {
                "reconciled": True,
                "artifacts": [{"path": evidence.name, "sha256": file_digest(evidence)}],
            }
            for category in CATEGORIES
        },
        "entries": [
            {
                "operation_id": "fixture-reader-1",
                "category": "provider",
                "day_utc": "2026-09-08",
                "state": "settled",
                "amount_microusd": 1_000_000,
            },
            {
                "operation_id": "fixture-worker-1",
                "category": "worker",
                "day_utc": "2026-09-08",
                "state": "reserved",
                "amount_microusd": 2_000_000,
            },
        ],
    }


def test_all_twenty_and_live_cases_start_pending(tmp_path):
    result = evaluate(
        manifest(), MANIFEST_SHA, skeleton(CANDIDATE, MANIFEST_SHA), tmp_path, CANDIDATE
    )
    assert result["release_accepted"] is False
    assert result["denominator"] == 10
    assert result["pending"] == list(CASES) + ["DEPLOYMENT-PROVENANCE", "COHORT-BUDGET"]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda m: m.update(status="metadata_frozen"),
        lambda m: m.update(allow_expansion=True),
        lambda m: m["selection"].update(unknown=True),
        lambda m: m["specimens"][0].update(unknown=True),
        lambda m: m["specimens"][0]["application_source"].update(unknown=True),
        lambda m: m["specimens"][0]["source_objects"][0].update(unknown=True),
        lambda m: m["specimens"][0]["source_objects"][0].update(
            bucket="https://fixture.invalid"
        ),
        lambda m: m["specimens"][0]["source_objects"][0].update(
            object_name="line\nbreak"
        ),
        lambda m: m["specimens"][0]["source_objects"][0].update(crc32c="invalid"),
        lambda m: m["specimens"][0]["source_objects"][0].update(md5_hash="invalid"),
        lambda m: m["specimens"].pop(),
        lambda m: m["specimens"].append(copy.deepcopy(m["specimens"][0])),
        lambda m: m["specimens"][1].update(specimen_id=specimen_id(1)),
        lambda m: m["specimens"].reverse(),
        lambda m: m["specimens"][0].update(collection_id=specimen_id(999)),
        lambda m: m["specimens"][0]["application_source"].update(source_object_index=1),
        lambda m: m["specimens"][0]["application_source"].update(sha256="f" * 64),
        lambda m: m["specimens"][0]["application_source"].update(
            blob_ref="f" * 64 + ":1"
        ),
        lambda m: m["specimens"][0]["source_objects"][0].pop("generation"),
        lambda m: m["specimens"][0]["source_objects"][0].update(generation="latest"),
        lambda m: m["specimens"][0]["source_objects"][0].update(sha256="unknown"),
        lambda m: m["specimens"][0]["source_objects"][0].update(size_bytes=True),
        lambda m: m["specimens"][1].update(
            source_objects=copy.deepcopy(m["specimens"][0]["source_objects"])
        ),
    ],
)
def test_cohort_cannot_shrink_expand_reorder_or_lose_immutability(mutation):
    value = manifest()
    mutation(value)
    with pytest.raises(InvalidEvidence):
        manifest_ids(value)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: r.update(candidate_sha="d" * 40),
        lambda r: r.update(manifest_sha256="d" * 64),
        lambda r: r["results"].pop(),
        lambda r: r["results"].append(copy.deepcopy(r["results"][0])),
        lambda r: r["results"][0].update(candidate_sha="d" * 40),
        lambda r: r["results"][0].update(manifest_sha256="d" * 64),
        lambda r: r["results"][0].update(specimen_ids=["unapproved-eleventh"]),
        lambda r: r["results"][0].update(status="passed"),
        lambda r: r["results"][0].update(status="skipped"),
    ],
)
def test_stale_and_incomplete_reports_are_rejected(tmp_path, mutation):
    report = skeleton(CANDIDATE, MANIFEST_SHA)
    mutation(report)
    with pytest.raises(InvalidEvidence):
        evaluate(manifest(), MANIFEST_SHA, report, tmp_path, CANDIDATE)


def passing_report(root):
    output = root / "fixture-evidence.txt"
    output.write_text("Authored fixture. This is not cloud acceptance.\n")
    report = skeleton(CANDIDATE, MANIFEST_SHA)
    for row in report["results"]:
        row.update(
            status="passed",
            mode="fixture",
            observer="QA-fixture",
            started_at_utc="2026-09-08T00:00:00Z",
            ended_at_utc="2026-09-08T00:00:01Z",
            command="fixture-command",
            expected="fixture expectation",
            actual="fixture observation",
            transport="fixture",
            exit_code=0,
            specimen_ids=[specimen_id(i) for i in range(1, 11)],
            artifacts=[{"path": output.name, "sha256": file_digest(output)}],
        )
    return report


@pytest.mark.parametrize("mode", ["fixture", "emulator", "owner_report"])
def test_non_live_evidence_can_never_complete_live_gate(tmp_path, mode):
    report = passing_report(tmp_path)
    for row in report["results"]:
        row["mode"] = mode
    result = evaluate(manifest(), MANIFEST_SHA, report, tmp_path, CANDIDATE)
    assert result["pending"] == list(CASES) + ["DEPLOYMENT-PROVENANCE", "COHORT-BUDGET"]
    assert not result["release_accepted"]


def test_digest_detects_changed_artifact_and_path_escape(tmp_path):
    report = passing_report(tmp_path)
    entry = report["results"][0]["artifacts"][0]
    (tmp_path / entry["path"]).write_text("changed")
    with pytest.raises(InvalidEvidence, match="digest mismatch"):
        artifact(tmp_path, entry)
    with pytest.raises(InvalidEvidence, match="Unsafe"):
        artifact(tmp_path, dict(entry, path="../outside.txt"))
    with pytest.raises(InvalidEvidence, match="Unsafe"):
        artifact(tmp_path, dict(entry, path=str(tmp_path / "fixture-evidence.txt")))
    (tmp_path / "escape").symlink_to(tmp_path.parent)
    with pytest.raises(InvalidEvidence, match="escapes"):
        artifact(tmp_path, dict(entry, path="escape/outside.txt"))


def test_duplicate_json_keys_fail_closed(tmp_path):
    path = tmp_path / "ambiguous.json"
    path.write_text('{"denominator": 11, "denominator": 10}')
    with pytest.raises(InvalidEvidence, match="Duplicate"):
        read_json(path)


def claimed_live_report(tmp_path):
    report = passing_report(tmp_path)
    report["budget"] = budget(tmp_path)
    for row in report["results"]:
        row["mode"] = "live"  # Tests validation mechanics, never real evidence.
    report["deployment"] = {
        "repository": "anurag-duddu/specimen-digitization-app",
        "hosting_commit_sha": CANDIDATE,
        "api_commit_sha": CANDIDATE,
        "worker_commit_sha": CANDIDATE,
        "sam_commit_sha": CANDIDATE,
        "sam_model_id": "facebook/sam3",
        "sam_model_revision": "c" * 40,
        "sam_checkpoint_sha256": "d" * 64,
        "sam_config_sha256": "e" * 64,
        "main_workflow_conclusion": "success",
        "deploy_job_conclusion": "success",
        "main_workflow_url": "fixture",
        "deploy_job_url": "fixture",
        "api_image_digest": "sha256:" + "f" * 64,
        "worker_image_digest": "sha256:" + "f" * 64,
        "sam_image_digest": "sha256:" + "f" * 64,
        "connector_revision": "fixture",
        "storage_rules_revision": "fixture",
        "runtime_workflow_url": "fixture",
    }
    return report


def test_claimed_live_evidence_requires_full_cohort_and_still_needs_reviewer(tmp_path):
    report = claimed_live_report(tmp_path)
    result = evaluate(manifest(), MANIFEST_SHA, report, tmp_path, CANDIDATE)
    assert result["evidence_preflight"] == "ready_for_independent_review"
    assert not result["release_accepted"]
    report["results"][-1]["specimen_ids"].pop()
    with pytest.raises(InvalidEvidence, match="Full ten"):
        evaluate(manifest(), MANIFEST_SHA, report, tmp_path, CANDIDATE)


@pytest.mark.parametrize(
    "field,value",
    [
        ("sam_image_digest", None),
        ("sam_image_digest", "latest"),
        ("worker_image_digest", "latest"),
        ("api_image_digest", "latest"),
        ("sam_commit_sha", "b" * 40),
        ("sam_model_id", "unapproved-model"),
        ("sam_model_revision", None),
        ("sam_model_revision", "main"),
        ("sam_checkpoint_sha256", None),
        ("sam_checkpoint_sha256", "unknown"),
        ("sam_config_sha256", None),
        ("sam_config_sha256", "unknown"),
    ],
)
def test_missing_or_unpinned_runtime_provenance_blocks_preflight(
    tmp_path, field, value
):
    report = claimed_live_report(tmp_path)
    report["deployment"][field] = value
    result = evaluate(manifest(), MANIFEST_SHA, report, tmp_path, CANDIDATE)
    assert result["pending"] == ["DEPLOYMENT-PROVENANCE"]
    assert result["evidence_preflight"] == "incomplete"
    assert result["release_accepted"] is False


def test_cli_rejects_changed_manifest_before_emitting_report(
    tmp_path, monkeypatch, capsys
):
    from acceptance import main

    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(manifest()))
    path.chmod(0o600)
    frozen = file_digest(path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "acceptance.py",
            str(path),
            "--approved-manifest-sha256",
            frozen,
            "--candidate-sha",
            CANDIDATE,
        ],
    )
    assert main() == 0
    assert len(json.loads(capsys.readouterr().out)["results"]) == len(CASES)
    path.write_text(path.read_text() + "\n")
    assert main() == 2
    assert json.loads(capsys.readouterr().out)["release_accepted"] is False
