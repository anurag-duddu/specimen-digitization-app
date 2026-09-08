"""Worker startup uses only synthetic mounted configuration, without providers."""

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from specimen_digitization.application import worker
from specimen_digitization.application.collection_profiles import insects_registry, SegmentationSettings
from specimen_digitization.application.evidence_pilot import read_evidence_profile
from specimen_digitization.application.worker_launch import PilotLaunch, read_launch, verify_source_manifest
from specimen_digitization.application.workflow import OperationalBlock
from test_pilot_manifest import pilot_payload


def mount(tmp_path, name, raw):
    path = tmp_path / name
    path.write_bytes(raw)
    path.chmod(0o444)
    return path, hashlib.sha256(raw).hexdigest()


def mounted_args(tmp_path, monkeypatch, *, evidence=True):
    payload = pilot_payload()
    manifest, manifest_pin = mount(tmp_path, "source.json", json.dumps(payload).encode())
    scope = {key: payload["specimens"][0][key] for key in ("organization_id", "collection_id")}
    profile = insects_registry().profiles[0].model_copy(update={
        "collection_id": scope["collection_id"],
        "segmentation_settings": SegmentationSettings(prompt="label"),
    })
    profile_path, profile_pin = mount(tmp_path, "profile.json", profile.model_dump_json().encode())
    launch = PilotLaunch(
        source_manifest_sha256=manifest_pin, authorization_reference=payload["authorization_reference"],
        scope=scope,
        specimens=[{
            "specimen_id": item["specimen_id"], "asset_sha256": item["application_source"]["sha256"],
            "blob_ref": item["application_source"]["blob_ref"],
        } for item in payload["specimens"]],
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        total_cost_limit_micros=10000, per_specimen_cost_limit_micros=1000,
        per_specimen_call_limit=32, per_specimen_token_limit=160000,
        effect_timeout_seconds=120,
        hf_secret_resource="/".join(("projects", "specimen-digitization", "secrets", "synthetic-only", "versions", "1")),
        evidence_only=evidence, evidence_profile_sha256=profile_pin if evidence else None,
    )
    launch_path, launch_pin = mount(tmp_path, "launch.json", launch.model_dump_json().encode())
    monkeypatch.setenv("SPECIMEN_LAUNCH_POLICY_SHA256", launch_pin)
    # Isolate copies for exact cleanup assertions without changing source files.
    temporary = tmp_path / "runtime"
    temporary.mkdir()
    monkeypatch.setattr("tempfile.tempdir", str(temporary))
    return SimpleNamespace(
        mode="production", materialize_config=True, launch_policy=launch_path,
        source_manifest=manifest, evidence_only=evidence,
        evidence_profile=profile_path if evidence else None,
    ), launch, temporary


@pytest.mark.parametrize("evidence", [True, False])
def test_materialized_worker_args_preserve_strict_pins_readers_and_cleanup(tmp_path, monkeypatch, evidence):
    args, expected, temporary = mounted_args(tmp_path, monkeypatch, evidence=evidence)
    original_paths = (args.launch_policy, args.source_manifest, args.evidence_profile)
    with worker.materialized_worker_args(args) as staged:
        assert staged is not args
        assert staged.launch_policy != args.launch_policy
        assert staged.source_manifest != args.source_manifest
        launch = read_launch(staged.launch_policy, os.environ["SPECIMEN_LAUNCH_POLICY_SHA256"])
        assert launch == expected
        verify_source_manifest(staged.source_manifest, launch)
        if evidence:
            assert read_evidence_profile(staged.evidence_profile, launch.evidence_profile_sha256).state == "draft"
        for path in (staged.launch_policy, staged.source_manifest, staged.evidence_profile):
            if path:
                assert path.stat().st_mode & 0o777 == 0o600
                assert path.stat().st_uid == os.getuid()
    assert not list(temporary.iterdir())
    assert (args.launch_policy, args.source_manifest, args.evidence_profile) == original_paths
    assert args.launch_policy.stat().st_mode & 0o777 == 0o444


def test_opt_out_leaves_existing_private_reader_policy_unchanged(tmp_path, monkeypatch):
    args, _, temporary = mounted_args(tmp_path, monkeypatch)
    args.materialize_config = False
    with worker.materialized_worker_args(args) as unchanged:
        assert unchanged is args
        with pytest.raises(OperationalBlock, match="private_configuration"):
            read_launch(unchanged.launch_policy, os.environ["SPECIMEN_LAUNCH_POLICY_SHA256"])
    assert not list(temporary.iterdir())


@pytest.mark.parametrize("target", ["launch_policy", "source_manifest", "evidence_profile"])
def test_each_mount_is_pinned_and_failure_cleans_prior_stages(tmp_path, monkeypatch, target):
    args, _, temporary = mounted_args(tmp_path, monkeypatch)
    source = getattr(args, target)
    source.chmod(0o600)
    source.write_bytes(source.read_bytes() + b" ")
    source.chmod(0o444)
    with pytest.raises(OperationalBlock, match="materialization") as caught:
        with worker.materialized_worker_args(args):
            pytest.fail("Unpinned input yielded")
    assert str(source) not in str(caught.value)
    assert not list(temporary.iterdir())


@pytest.mark.parametrize("pin", ["", "A" * 64, "0" * 64])
def test_required_independent_launch_pin_precedes_parsing(tmp_path, monkeypatch, pin):
    args, _, temporary = mounted_args(tmp_path, monkeypatch)
    monkeypatch.setenv("SPECIMEN_LAUNCH_POLICY_SHA256", pin)
    with pytest.raises(OperationalBlock, match="materialization"):
        with worker.materialized_worker_args(args):
            pytest.fail("Unpinned launch yielded")
    assert not list(temporary.iterdir())


@pytest.mark.parametrize("missing", ["launch_policy", "source_manifest", "evidence_profile"])
def test_missing_required_mount_blocks_and_cleans(tmp_path, monkeypatch, missing):
    args, _, temporary = mounted_args(tmp_path, monkeypatch)
    setattr(args, missing, None)
    with pytest.raises(OperationalBlock):
        with worker.materialized_worker_args(args):
            pytest.fail("Incomplete launch yielded")
    assert not list(temporary.iterdir())


def test_synthetic_opt_in_is_rejected(tmp_path, monkeypatch):
    args, _, temporary = mounted_args(tmp_path, monkeypatch)
    args.mode = "synthetic"
    with pytest.raises(OperationalBlock, match="production"):
        with worker.materialized_worker_args(args):
            pytest.fail("Synthetic mount materialization yielded")
    assert not list(temporary.iterdir())


def test_pinned_invalid_launch_still_fails_unchanged_schema_reader(tmp_path, monkeypatch):
    args, _, temporary = mounted_args(tmp_path, monkeypatch)
    args.launch_policy.chmod(0o600)
    args.launch_policy.write_bytes(b'{"invalid": "synthetic-only"}')
    args.launch_policy.chmod(0o444)
    monkeypatch.setenv("SPECIMEN_LAUNCH_POLICY_SHA256", hashlib.sha256(args.launch_policy.read_bytes()).hexdigest())
    with pytest.raises(OperationalBlock, match="contract_invalid"):
        with worker.materialized_worker_args(args):
            pytest.fail("Schema-invalid launch yielded")
    assert not list(temporary.iterdir())


def test_launch_evidence_mode_cannot_disagree_with_cli(tmp_path, monkeypatch):
    args, _, temporary = mounted_args(tmp_path, monkeypatch)
    args.evidence_only = False
    with pytest.raises(OperationalBlock, match="mode_mismatch"):
        with worker.materialized_worker_args(args):
            pytest.fail("Mode mismatch yielded")
    assert not list(temporary.iterdir())


def test_profile_cannot_be_materialized_without_launch_pin(tmp_path, monkeypatch):
    args, _, temporary = mounted_args(tmp_path, monkeypatch, evidence=False)
    args.evidence_profile = tmp_path / "profile.json"
    with pytest.raises(OperationalBlock, match="profile"):
        with worker.materialized_worker_args(args):
            pytest.fail("Unpinned profile yielded")
    assert not list(temporary.iterdir())


def test_copies_cleanup_when_worker_stops_with_error(tmp_path, monkeypatch):
    args, _, temporary = mounted_args(tmp_path, monkeypatch)
    with pytest.raises(SystemExit) as caught:
        with worker.materialized_worker_args(args):
            raise SystemExit(2)
    assert caught.value.code == 2
    assert not list(temporary.iterdir())


def test_actual_cli_opt_in_check_config_uses_staged_strict_readers(tmp_path, monkeypatch, capsys):
    args, expected, temporary = mounted_args(tmp_path, monkeypatch)
    seen = []

    def offline_launch(staged):
        launch = read_launch(staged.launch_policy, os.environ["SPECIMEN_LAUNCH_POLICY_SHA256"])
        verify_source_manifest(staged.source_manifest, launch)
        assert launch == expected
        seen.append(staged.launch_policy)
        return launch

    # Only provider approval checks are replaced; all three strict file readers run.
    monkeypatch.setattr(worker, "production_launch", offline_launch)
    monkeypatch.setattr(sys, "argv", [
        "specimen-worker", "--mode", "production", "--materialize-config", "--check-config",
        "--launch-policy", str(args.launch_policy), "--source-manifest", str(args.source_manifest),
        "--evidence-only", "--evidence-profile", str(args.evidence_profile),
    ])
    worker.main()
    output = json.loads(capsys.readouterr().out)
    assert output == {"status": "configured", "live_services_verified": False}
    assert seen and all(not path.exists() for path in seen)
    assert not list(temporary.iterdir())


def test_actual_cli_reports_sanitized_pin_failure(tmp_path, monkeypatch, capsys):
    args, _, temporary = mounted_args(tmp_path, monkeypatch)
    monkeypatch.delenv("SPECIMEN_LAUNCH_POLICY_SHA256")
    monkeypatch.setattr(sys, "argv", [
        "specimen-worker", "--mode", "production", "--materialize-config", "--check-config",
        "--launch-policy", str(args.launch_policy), "--source-manifest", str(args.source_manifest),
    ])
    with pytest.raises(SystemExit) as caught:
        worker.main()
    assert caught.value.code == 2
    output = capsys.readouterr().out
    assert json.loads(output)["status"] == "blocked"
    assert str(tmp_path) not in output
    assert not list(temporary.iterdir())
