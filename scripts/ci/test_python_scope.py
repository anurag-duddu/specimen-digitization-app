"""The Python scope classifier may optimize only an exact frontend-only diff."""

from pathlib import Path
import subprocess
import sys

import pytest

import python_scope


def test_unproven_focused_closure_falls_back_to_full():
    full, reasons = python_scope.requires_full_python([
        "apps/specimen_digitization/lib/src/workspace.dart",
        "apps/specimen_digitization/test/workspace_queue_refresh_test.dart",
        "apps/specimen_digitization/android/app/build.gradle.kts",
        "docs/SESSION_LEARNINGS.md",
    ])
    assert full and reasons
    assert python_scope.requires_full_python([
        "apps/specimen_digitization/lib/main.dart",
    ]) == (True, ["<focused-contract-closure-unproven>"])


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
            b"D\0src/specimen_digitization/api.py\0A\0apps/specimen_digitization/lib/api.dart\0", b"")

    monkeypatch.setattr(python_scope.subprocess, "run", run)
    base, head = "a" * 40, "b" * 40
    full, reasons = python_scope.classify("pull_request", base, head)
    assert (full, reasons) == (True, ["src/specimen_digitization/api.py"])
    assert observed["command"] == [
        "git", "diff", "--name-status", "--no-renames", "-z", base, head]
    assert observed["kwargs"] == {"check": True, "capture_output": True}


@pytest.mark.parametrize("base,head", [("short", "b" * 40), ("a" * 40, "HEAD"), ("A" * 40, "b" * 40)])
def test_invalid_pull_request_identity_is_refused(base, head):
    with pytest.raises(ValueError, match="full commit SHAs"):
        python_scope.changed_entries(base, head)


@pytest.mark.parametrize("error", [
    ValueError("bad identity"),
    UnicodeDecodeError("utf-8", b"x", 0, 1, "bad path"),
    subprocess.CalledProcessError(128, ["git", "diff"]),
    OSError("git unavailable"),
])
def test_pull_request_comparison_failure_selects_the_complete_suite(monkeypatch, error):
    def fail(base, head):
        raise error

    monkeypatch.setattr(python_scope, "changed_entries", fail)
    full, reasons = python_scope.classify("pull_request", "a" * 40, "b" * 40)
    assert full and reasons == [f"<comparison-failed:{type(error).__name__}>"]


def test_cli_appends_the_github_output(monkeypatch, tmp_path, capsys):
    _diff(monkeypatch, b"M\0apps/specimen_digitization/lib/main.dart\0M\0docs/SESSION_LEARNINGS.md\0")
    output = tmp_path / "github-output"
    output.write_text("existing=value\n")
    assert python_scope.main([
        "--event", "pull_request", "--base", "a" * 40, "--head", "b" * 40,
        "--output", str(output),
    ]) == 0
    assert output.read_text() == "existing=value\nfull=true\n"
    printed = capsys.readouterr().out
    assert "full collection" in printed
    assert "<focused-contract-closure-unproven>" in printed


FRONTEND = "apps/specimen_digitization/"
BASE, HEAD = "a" * 40, "b" * 40


def _diff(monkeypatch, data):
    monkeypatch.setattr(python_scope.subprocess, "run", lambda command, **kwargs:
                        subprocess.CompletedProcess(command, 0, data, b""))


def _qualified(monkeypatch):
    # Exercise status/path policy independently of the current all-full fallback.
    # This is a test double, never a production qualification mechanism.
    monkeypatch.setattr(python_scope, "focused_contracts_qualified", lambda: True, raising=False)


@pytest.mark.parametrize("prefix", ["", FRONTEND, FRONTEND + "packages/specimen_ui/"])
@pytest.mark.parametrize("name", [
    "uv.lock", "pubspec.lock", "unknown.lock", "package-lock.json",
    "npm-shrinkwrap.json", "pnpm-lock.yaml", "yarn.lock", "Pipfile.lock",
    "poetry.lock", "Cargo.lock", "Gemfile.lock", "composer.lock", "packages.lock.json",
    "bun.lockb", "flake.lock", ".terraform.lock.hcl", "Package.resolved", "go.sum",
])
def test_all_lockfiles_require_full_python(monkeypatch, prefix, name):
    _qualified(monkeypatch)
    path = prefix + name
    assert python_scope.requires_full_python([path]) == (True, [path])


@pytest.mark.parametrize("path", [
    "dataconnect/schema/schema.gql", "dataconnect/connector/queries.gql",
    "infra/main.tf", "storage.rules", "firebase.json", ".firebaserc",
    "scripts/release/data_release.py", "scripts/ci/unknown.py",
    ".github/workflows/runtime-release.yml", "schema/unknown.json", "unknown/new.file",
    FRONTEND + "unknown/new.file", FRONTEND + "schema/schema.gql",
    FRONTEND + "infra/main.tf", FRONTEND + "scripts/release/deploy.sh",
])
def test_schema_infra_release_and_unknown_paths_are_full(monkeypatch, path):
    _qualified(monkeypatch)
    assert python_scope.requires_full_python([path]) == (True, [path])


@pytest.mark.parametrize("status,paths", [
    ("D", (FRONTEND + "lib/old.dart",)),
    ("R100", (FRONTEND + "lib/old.dart", FRONTEND + "lib/new.dart")),
    ("R050", ("src/backend.py", FRONTEND + "lib/new.dart")),
    ("C100", (FRONTEND + "lib/old.dart", FRONTEND + "lib/new.dart")),
    ("T", (FRONTEND + "lib/main.dart",)),
    ("U", (FRONTEND + "lib/main.dart",)),
    ("X", (FRONTEND + "lib/main.dart",)),
    ("B", (FRONTEND + "lib/main.dart",)),
])
def test_flutter_deletion_and_rename_are_full(monkeypatch, status, paths):
    _qualified(monkeypatch)
    data = "\0".join((status, *paths, "")).encode()
    _diff(monkeypatch, data)
    entries = python_scope.changed_entries(BASE, HEAD)
    assert entries == [python_scope.Change(status, paths)]
    full, reasons = python_scope.classify("pull_request", BASE, HEAD)
    assert full, f"unsafe {status} entry selected focused contracts"
    assert all(path in reasons for path in paths), "both sides must survive into diagnostics"


def test_delete_add_rename_is_full(monkeypatch):
    _qualified(monkeypatch)
    _diff(monkeypatch, (f"D\0{FRONTEND}lib/old.dart\0A\0{FRONTEND}lib/new.dart\0").encode())
    assert python_scope.changed_entries(BASE, HEAD) == [
        python_scope.Change("D", (FRONTEND + "lib/old.dart",)),
        python_scope.Change("A", (FRONTEND + "lib/new.dart",)),
    ]
    full, reasons = python_scope.classify("pull_request", BASE, HEAD)
    assert full and FRONTEND + "lib/old.dart" in reasons


@pytest.mark.parametrize("data", [
    b"M", b"M\0", b"M\0apps/specimen_digitization/lib/main.dart",
    b"M\0\0", b"\0", b"M\0\0M\0valid\0",
    b"M\0apps/specimen_digitization/lib/main.dart\0\0",
    b"R100\0apps/specimen_digitization/lib/old.dart\0",
    b"C100\0old\0", b"R101\0old\0new\0", b"R99\0old\0new\0",
    b"R\0old\0new\0", b"C-01\0old\0new\0", b"Q\0unknown\0",
    b"MM\0file\0", b"M\tfile\0", b"\xff\0file\0", b"M\0\xff\0",
    b"M\0apps/specimen_digitization/lib/good.dart\0R100\0old\0",
])
def test_malformed_name_status_fails_closed(monkeypatch, data):
    _qualified(monkeypatch)
    _diff(monkeypatch, data)
    with pytest.raises((ValueError, UnicodeError)):
        python_scope.changed_entries(BASE, HEAD)
    full, reasons = python_scope.classify("pull_request", BASE, HEAD)
    assert full and reasons[0].startswith("<comparison-failed:")


@pytest.mark.parametrize("path", [
    "../outside", "/absolute", "", ".", "apps/specimen_digitization/../backend.py",
    FRONTEND + "lib/./main.dart", FRONTEND + "lib//main.dart",
    FRONTEND + "lib/main.dart/", FRONTEND + "lib/line\nbreak.dart",
    FRONTEND + "lib/tab\tname.dart", FRONTEND + "lib/evil\\name.dart",
    FRONTEND + "lib/nul\0name.dart",
])
def test_noncanonical_paths_are_full_even_with_qualified_closure(monkeypatch, path):
    _qualified(monkeypatch)
    assert python_scope.requires_full_python([path]) == (True, [path])
    _diff(monkeypatch, f"M\0{path}\0".encode())
    full, reasons = python_scope.classify("pull_request", BASE, HEAD)
    assert full and reasons[0].startswith("<comparison-failed:")


@pytest.mark.parametrize("status", ["A", "M"])
def test_only_known_additions_and_modifications_could_use_proved_closure(monkeypatch, status):
    _qualified(monkeypatch)
    paths = [FRONTEND + "lib/main.dart", "docs/SESSION_LEARNINGS.md"]
    _diff(monkeypatch, "".join(f"{status}\0{path}\0" for path in paths).encode())
    assert python_scope.classify("pull_request", BASE, HEAD) == (False, [])


def test_empty_status_diff_is_full(monkeypatch):
    _qualified(monkeypatch)
    _diff(monkeypatch, b"")
    assert python_scope.classify("pull_request", BASE, HEAD) == (True, ["<empty-diff>"])


@pytest.mark.parametrize("event", ["pull_request_target", "merge_group", "release", "unknown"])
def test_non_pr_events_do_not_even_compare_git(monkeypatch, event):
    def unexpected(*args, **kwargs):
        pytest.fail("non-PR events must not invoke Git or qualification")

    monkeypatch.setattr(python_scope.subprocess, "run", unexpected)
    assert python_scope.classify(event, BASE, HEAD) == (True, [f"<{event}>"])


@pytest.mark.parametrize("identity", ["", "0" * 40, "HEAD", "a" * 39, "a" * 41, "a" * 40 + "\n"])
@pytest.mark.parametrize("side", ["base", "head"])
def test_invalid_identities_fail_closed_before_git(monkeypatch, identity, side):
    def unexpected(*args, **kwargs):
        pytest.fail("invalid identities must not invoke Git")

    monkeypatch.setattr(python_scope.subprocess, "run", unexpected)
    base, head = (identity, HEAD) if side == "base" else (BASE, identity)
    assert python_scope.classify("pull_request", base, head) == (
        True, ["<comparison-failed:ValueError>"])


def test_cli_in_a_fresh_process_defaults_to_full(tmp_path):
    output = tmp_path / "github-output"
    result = subprocess.run([
        sys.executable, str(Path(python_scope.__file__)),
        "--event", "pull_request", "--base", "invalid", "--head", HEAD,
        "--output", str(output),
    ], capture_output=True, text=True, check=True)
    assert output.read_text() == "full=true\n"
    assert "<comparison-failed:ValueError>" in result.stdout


@pytest.mark.parametrize("error", [
    subprocess.CalledProcessError(128, ["git", "diff"]),
    OSError("git unavailable"),
])
def test_failed_git_selects_full_from_the_subprocess_boundary(monkeypatch, error):
    _qualified(monkeypatch)

    def fail(command, **kwargs):
        raise error

    monkeypatch.setattr(python_scope.subprocess, "run", fail)
    assert python_scope.classify("pull_request", BASE, HEAD) == (
        True, [f"<comparison-failed:{type(error).__name__}>"])


def test_status_parser_preserves_record_order_scores_and_unicode(monkeypatch):
    _diff(monkeypatch, (
        f"M\0{FRONTEND}lib/café.dart\0R000\0old\0new\0C099\0source\0copy\0"
    ).encode())
    assert python_scope.changed_entries(BASE, HEAD) == [
        python_scope.Change("M", (FRONTEND + "lib/café.dart",)),
        python_scope.Change("R000", ("old", "new")),
        python_scope.Change("C099", ("source", "copy")),
    ]
