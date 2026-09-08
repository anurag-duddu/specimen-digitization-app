"""Failure retention and provenance checks for the independent local probe."""

import json

import pytest

import local_probe


def test_failed_probe_retains_completed_checks_and_private_state(tmp_path, monkeypatch):
    state = tmp_path / "failed-state"
    state.mkdir(mode=0o700)
    output = tmp_path / "evidence.json"
    monkeypatch.setattr("sys.argv", ["local_probe.py", "--output", str(output)])
    monkeypatch.setattr(
        local_probe, "source_identity", lambda: {"candidate_sha": "a" * 40}
    )
    monkeypatch.setattr(local_probe.tempfile, "mkdtemp", lambda **kwargs: str(state))

    def failed(root, checks):
        checks.append({"case": "fixture-failure", "status": "failed", "actual": 503})
        (root / "synthetic-state.txt").write_text("retained fixture state")
        raise AssertionError("private-content-must-not-leak")

    monkeypatch.setattr(local_probe, "run", failed)
    assert local_probe.main() == 1
    result = json.loads(output.read_text())
    assert result["probe_status"] == "failed"
    assert result["checks"][0]["status"] == "failed"
    assert result["failed_state_directory"] == str(state)
    assert (state / "synthetic-state.txt").exists()
    assert "private-content-must-not-leak" not in output.read_text()
    assert result["release_accepted"] is False


def test_dirty_product_source_cannot_be_attributed_to_head(monkeypatch):
    def git(command, **kwargs):
        return "a" * 40 if command[1] == "rev-parse" else " M src/product.py\n"

    monkeypatch.setattr(local_probe.subprocess, "check_output", git)
    with pytest.raises(RuntimeError, match="clean"):
        local_probe.source_identity()


def test_clean_identity_includes_harness_digest(monkeypatch):
    def git(command, **kwargs):
        return "a" * 40 if command[1] == "rev-parse" else ""

    monkeypatch.setattr(local_probe.subprocess, "check_output", git)
    identity = local_probe.source_identity()
    assert identity["candidate_sha"] == "a" * 40
    assert len(identity["harness_sha256"]) == 64


def test_changed_source_during_probe_fails_with_retained_evidence(
    tmp_path, monkeypatch
):
    output = tmp_path / "evidence.json"
    state = tmp_path / "state"
    state.mkdir()
    identities = iter(({"candidate_sha": "a" * 40}, {"candidate_sha": "b" * 40}))
    monkeypatch.setattr("sys.argv", ["local_probe.py", "--output", str(output)])
    monkeypatch.setattr(local_probe, "source_identity", lambda: next(identities))
    monkeypatch.setattr(local_probe.tempfile, "mkdtemp", lambda **kwargs: str(state))
    monkeypatch.setattr(local_probe, "run", lambda root, checks: (checks, "c" * 64))
    assert local_probe.main() == 1
    assert json.loads(output.read_text())["probe_status"] == "failed"


def test_existing_evidence_never_overwritten_or_run(tmp_path, monkeypatch):
    output = tmp_path / "evidence.json"
    output.write_text("earlier evidence")
    monkeypatch.setattr("sys.argv", ["local_probe.py", "--output", str(output)])
    monkeypatch.setattr(
        local_probe, "source_identity", lambda: pytest.fail("must not run")
    )
    with pytest.raises(FileExistsError):
        local_probe.main()
    assert output.read_text() == "earlier evidence"
