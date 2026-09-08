from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("release_packet", Path(__file__).with_name("validate_release_packet.py"))
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def candidate():
    return json.loads((ROOT / "infra/release/candidate.example.json").read_text())


def test_example_is_explicitly_incomplete():
    assert MODULE.validate(candidate())
    with pytest.raises(ValueError, match="incomplete candidate"):
        MODULE.validate(candidate(), require_ready=True)


@pytest.mark.parametrize("count", [9, 11, True, "10"])
def test_reject_expanded_or_invalid_pilot(count):
    p = candidate()
    p["pilot"]["specimen_count"] = count
    with pytest.raises(ValueError, match="exactly ten"):
        MODULE.validate(p)


@pytest.mark.parametrize("reference", [
    "us-east4-docker.pkg.dev/specimen-digitization/specimen-runtime/api:latest",
    "us-east4-docker.pkg.dev/other/specimen-runtime/api@sha256:" + "a" * 64,
    "us-east4-docker.pkg.dev/specimen-digitization/specimen-runtime/worker@sha256:" + "a" * 64,
])
def test_reject_mutable_foreign_or_wrong_role_image(reference):
    p = candidate()
    p["images"]["api"]["reference"] = reference
    with pytest.raises(ValueError):
        MODULE.validate(p)


def test_reject_stale_image_and_checks():
    for entry in ["image", "check"]:
        p = candidate()
        p["source_sha"] = "a" * 40
        target = p["images"]["api"] if entry == "image" else p["checks"]["Python tests"]
        target["source_sha"] = "b" * 40
        with pytest.raises(ValueError):
            MODULE.validate(p)


def test_reject_missing_mobile_gate_and_private_fields():
    p = candidate()
    del p["checks"]["Flutter ios build"]
    with pytest.raises(ValueError):
        MODULE.validate(p)
    p = candidate()
    p["pilot"]["objects"] = []
    with pytest.raises(ValueError):
        MODULE.validate(p)


def complete_structure():
    p = candidate()
    p["source_sha"] = "a" * 40
    for role, entry in p["images"].items():
        entry.update(reference=f"us-east4-docker.pkg.dev/specimen-digitization/specimen-runtime/{role}@sha256:" + "b" * 64,
                     source_sha=p["source_sha"], provenance_sha256="c" * 64)
    for group in [p["data"], p["approvals"]]:
        for key in group:
            group[key] = "d" * 64
    p["pilot"]["manifest_sha256"] = "e" * 64
    p["public_config_sha256"] = p["rollback_sha256"] = "f" * 64
    for entry in p["checks"].values():
        entry.update(source_sha=p["source_sha"], conclusion="success", run_url="https://github.com/anurag-duddu/specimen-digitization-app/actions/runs/123")
    return p


def test_complete_structure_does_not_claim_live_verification():
    assert MODULE.validate(complete_structure(), require_ready=True) == []


@pytest.mark.parametrize("conclusion", ["skipped", "cancelled", "failure", "not_run"])
def test_no_non_success_check_counts_as_complete(conclusion):
    p = complete_structure()
    p["checks"]["Flutter android build"]["conclusion"] = conclusion
    with pytest.raises(ValueError, match="incomplete candidate"):
        MODULE.validate(p, require_ready=True)
