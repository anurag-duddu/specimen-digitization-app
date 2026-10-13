"""The Python scope classifier may optimize only an exact frontend-only diff."""

from pathlib import Path
import subprocess

import pytest

import python_scope


def test_only_flutter_and_the_append_only_log_use_focused_contracts():
    full, reasons = python_scope.requires_full_python([
        "apps/specimen_digitization/lib/src/workspace.dart",
        "apps/specimen_digitization/test/workspace_queue_refresh_test.dart",
        "apps/specimen_digitization/android/app/build.gradle.kts",
        "docs/SESSION_LEARNINGS.md",
    ])
    assert (full, reasons) == (False, [])


@pytest.mark.parametrize("path", [
    "src/specimen_digitization/application/api.py",
    "tests/test_application.py",
    "scripts/ci/verify.sh",
    ".github/workflows/ci-cd.yml",
    "pyproject.toml",
    "uv.lock",
    "firebase.json",
    "README.md",
    "docs/DEPLOYMENT.md",
    "apps/specimen_digitization-not-really/lib/a.dart",
])
def test_every_other_path_requires_the_full_collection(path):
    assert python_scope.requires_full_python([path]) == (True, [path])


@pytest.mark.parametrize("paths", [[], ["../outside"], ["/absolute"]])
def test_empty_or_unsafe_paths_fail_closed(paths):
    full, reasons = python_scope.requires_full_python(paths)
    assert full and reasons


@pytest.mark.parametrize("event", ["push", "workflow_dispatch", "schedule", ""])
def test_every_event_other_than_a_pull_request_is_full(event):
    full, reasons = python_scope.classify(event, "", "")
    assert full and reasons == [f"<{event or 'missing-event'}>"]


def test_pull_request_diff_uses_both_sides_of_renames(monkeypatch):
    observed = {}

    def run(command, **kwargs):
        observed.update(command=command, kwargs=kwargs)
        return subprocess.CompletedProcess(command, 0,
            b"src/specimen_digitization/api.py\0apps/specimen_digitization/lib/api.dart\0", b"")

    monkeypatch.setattr(python_scope.subprocess, "run", run)
    base, head = "a" * 40, "b" * 40
    full, reasons = python_scope.classify("pull_request", base, head)
    assert (full, reasons) == (True, ["src/specimen_digitization/api.py"])
    assert observed["command"] == [
        "git", "diff", "--name-only", "--no-renames", "-z", base, head]
    assert observed["kwargs"] == {"check": True, "capture_output": True}


@pytest.mark.parametrize("base,head", [("short", "b" * 40), ("a" * 40, "HEAD"), ("A" * 40, "b" * 40)])
def test_invalid_pull_request_identity_is_refused(base, head):
    with pytest.raises(ValueError, match="full commit SHAs"):
        python_scope.changed_paths(base, head)


@pytest.mark.parametrize("error", [
    ValueError("bad identity"),
    UnicodeDecodeError("utf-8", b"x", 0, 1, "bad path"),
    subprocess.CalledProcessError(128, ["git", "diff"]),
    OSError("git unavailable"),
])
def test_pull_request_comparison_failure_selects_the_complete_suite(monkeypatch, error):
    def fail(base, head):
        raise error

    monkeypatch.setattr(python_scope, "changed_paths", fail)
    full, reasons = python_scope.classify("pull_request", "a" * 40, "b" * 40)
    assert full and reasons == [f"<comparison-failed:{type(error).__name__}>"]


def test_cli_appends_the_github_output(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(python_scope, "changed_paths", lambda base, head: [
        "apps/specimen_digitization/lib/main.dart", "docs/SESSION_LEARNINGS.md"])
    output = tmp_path / "github-output"
    assert python_scope.main([
        "--event", "pull_request", "--base", "a" * 40, "--head", "b" * 40,
        "--output", str(output),
    ]) == 0
    assert output.read_text() == "full=false\n"
    assert "focused frontend contracts" in capsys.readouterr().out
