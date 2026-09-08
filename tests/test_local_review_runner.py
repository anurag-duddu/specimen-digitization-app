"""Protect local credentials, existing config and unrelated supervisor jobs."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    "local_review_runner",
    Path(__file__).resolve().parents[1] / "scripts/dev/local_review.py",
)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def test_retained_token_is_private_never_rotated_and_not_printed(tmp_path, capsys):
    root = tmp_path / "review"
    token = runner.private_token(root)
    assert token and runner.private_token(root) == token
    runner.write_access(root, {"web_port": 3000, "api_port": 8000, "source_sha": "test"})
    assert "Fixture token:" in (root / "ACCESS.md").read_text()
    assert (root / "ACCESS.md").stat().st_mode & 0o077 == 0
    assert (root / "token").stat().st_mode & 0o077 == 0
    assert token not in capsys.readouterr().out
    (root / "token").write_text("")
    with pytest.raises(ValueError, match="not replaced"):
        runner.private_token(root)
    assert (root / "token").read_text() == ""


def test_symlink_token_and_repository_state_are_rejected(tmp_path):
    target = tmp_path / "other"
    target.write_text("keep-me")
    (tmp_path / "token").symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        runner.private_token(tmp_path)
    assert target.read_text() == "keep-me"
    with pytest.raises(ValueError, match="outside"):
        runner.review_root(runner.REPO / "local-state")


def test_foreign_job_is_not_removed(tmp_path, monkeypatch):
    calls = []

    def foreign(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(
            returncode=0, stdout="ProgramArguments: unrelated-service"
        )

    monkeypatch.setattr(runner.subprocess, "run", foreign)
    with pytest.raises(ValueError, match="different owner"):
        runner.stop(tmp_path)
    assert all("remove" not in call for call in calls)


def test_existing_firebase_config_is_preserved_before_build(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / ".venv/bin").mkdir(parents=True)
    (repo / ".venv/bin/python").touch()
    lib = repo / "apps/specimen_digitization/lib"
    lib.mkdir(parents=True)
    (lib / "firebase_options.ci.dart").write_text("synthetic placeholder")
    target = lib / "firebase_options.dart"
    target.write_text("existing developer configuration")
    monkeypatch.setattr(runner, "REPO", repo)
    with pytest.raises(ValueError, match="Refusing to overwrite"):
        runner.build(tmp_path / "state", 8000, 3000)
    assert target.read_text() == "existing developer configuration"
