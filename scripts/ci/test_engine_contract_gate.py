"""Fail-closed engine evidence contracts. Synthetic controls are not engine green."""
from __future__ import annotations

import copy
import errno
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
GATE = Path(os.environ.get("ENGINE_GATE_SOURCE", ROOT / "scripts/ci/engine_contract_gate.py"))
SELECTION = ROOT / "scripts/data/engine-contract-selection.json"


@pytest.fixture
def gate():
    spec = importlib.util.spec_from_file_location("engine_contract_gate_under_test", GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def phase_control_bytes(tmp_path_factory):
    """Immutable report from nine real, passing synthetic subprocess bodies."""
    root = tmp_path_factory.mktemp("phase-control")
    tests = root / "tests"
    tests.mkdir()
    (tests / "test_sqlconnect_application.py").write_text(
        "def test_real_sql_adapter_workflow_cas_and_reconstruction(): pass\n")
    (tests / "test_hardening_concurrency.py").write_text(
        "import pytest\n@pytest.mark.parametrize('adapter', ['sql'])\n"
        "def test_same_source_concurrent_http_completion_is_authorized_duplicate(adapter): pass\n"
        "@pytest.mark.parametrize('adapter', ['sql'])\n"
        "def test_shared_circuit_survives_worker_restart_and_fences_half_probe(adapter): pass\n")
    (tests / "engine_sqlconnect_authorization_contract.py").write_text(
        "import pytest\n@pytest.mark.parametrize('scope', ['foreign_actor','foreign_organization','foreign_collection'])\n"
        "def test_v3_read_write_scope_denial(scope): pass\n"
        "def test_v3_cas_has_one_winner_and_one_receipt(): pass\n"
        "def test_v3_failed_write_rolls_back_snapshot_receipt_audit_outbox(): pass\n"
        "def test_v3_revocation_blocks_read_write(): pass\n")
    output = root / "phases.json"
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
               ENGINE_CONTRACT_PYTEST_REPORT=str(output), PYTHONPATH=str(GATE.parent))
    nodes = json.loads(SELECTION.read_text())["python_nodes"]
    completed = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                                "-p", "engine_contract_gate", *nodes], cwd=root, env=env,
                               capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return output.read_bytes()


@pytest.fixture
def control(gate, tmp_path, monkeypatch, phase_control_bytes):
    """Independent scratch files provide expected hashes; result claims cannot set them."""
    selection = gate.load_selection(SELECTION)
    (tmp_path / "src").mkdir()
    (tmp_path / "src/app.py").write_text("VALUE = 1\n")
    (tmp_path / "scripts/data").mkdir(parents=True)
    (tmp_path / "scripts/data/engine-contract-selection.json").write_bytes(SELECTION.read_bytes())
    (tmp_path / "scripts/data/engine-toolchain.json").write_text(json.dumps(gate.APPROVED_TOOLCHAIN))
    (tmp_path / "firebase.json").write_text('{"emulators":{}}')
    (tmp_path / "storage.rules").write_text("deny all")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='fixture'\n")
    (tmp_path / "uv.lock").write_text("version = 1\n")
    files = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())

    def git(root, *args):
        if args == ("rev-parse", "HEAD"):
            return "a" * 40
        if args == ("ls-files", "-z"):
            return "\0".join(files) + "\0"
        if args == ("diff", "--name-only", "HEAD"):
            return ""
        raise AssertionError(args)

    monkeypatch.setattr(gate, "git", git)
    env = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": "anurag-duddu/specimen-digitization-app",
           "GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "42", "GITHUB_RUN_ATTEMPT": "2",
           "GITHUB_EVENT_NAME": "workflow_dispatch", "ENGINE_CACHE_MODE": "normal"}
    expected = gate.expected_context(tmp_path, tmp_path / "scripts/data/engine-contract-selection.json", env)
    tools = {name: {**{k: value[k] for k in ("version", "bytes", "sha256")},
                    "path": "/private/engines/" + name}
             for name, value in gate.APPROVED_TOOLCHAIN["assets"].items()}
    evidence = {
        "schema": 1, "engine_flag": "true", "tools": tools,
        "runtime": runtime_control(),
        "postgres_server_version": "16.15 (Ubuntu fixture)",
        "preflight": {"project": "demo-specimen-data", "host": "127.0.0.1", "ports": [5559, 9509, 9299],
                      "postgres_host": "127.0.0.1:5559", "dataconnect_host": "127.0.0.1:9509",
                      "python_host": "127.0.0.1:9509", "storage_host": "127.0.0.1:9299",
                      "ports_free_before": True, "credentials_absent": True},
        "seed": {"organization": "00000000-0000-4000-8000-000000000001",
                 "collection": "00000000-0000-4000-8000-000000000002", "uid": "synthetic-reviewer",
                 "organization_active": True, "collection_active": True, "role": "reviewer", "can_view_sensitive": True},
        "readiness": [{"id": name, "outcome": "passed", "seconds": 0.01} for name in selection["readiness"]],
        "stages": [{"id": name, "outcome": "passed", "seconds": 0.01} for name in selection["stages"]],
        "node_events": [{"id": name, "outcome": "passed", "seconds": 0.01}
                        for name in selection["connector_groups"] + selection["storage_assertions"]],
        "processes": [{"id": name, "pid": 100 + i, "owned": True, "stopped": True, "waited": True}
                      for i, name in enumerate(selection["processes"])],
        "cleanup": {"outcome": "passed", "seconds": 0.01, "ports_free_after": True, "survivors": []},
        "cache": {"mode": "normal", "restore": "hit", "directory_private": True,
                  "directory_fresh": False, "entries_before": 3}}
    report = json.loads(phase_control_bytes)
    result = {"schema": 1, "complete": True, "context_start": copy.deepcopy(expected),
              "context_end": copy.deepcopy(expected), "pytest": report, "lifecycle": evidence,
              "exitstatus": 0, "seconds": 1.0, "runtime_observed": runtime_control()}
    # Recorder-owned registrations are separate from harness cleanup claims.
    launches, cleanups = [], []
    for i, process in enumerate(evidence["processes"]):
        launch = {"id": process["id"], "pid": process["pid"], "birth_id": f"{i + 1:064x}",
                  "os_started_ns": 1700000000000000000 + i * 10,
                  "instance": f"{i + 1:032x}", "started_ns": 10 + i * 10}
        process.update(launch, ended_ns=15 + i * 10)
        launches.append(launch)
        cleanups.append(copy.deepcopy(process))
    result["process_receipts"] = {"schema": 1, "started_ns": 1, "ended_ns": 100,
                                  "epoch_started_ns": 1700000000000000000, "epoch_ended_ns": 1700000000000000100,
                                  "launches": launches, "cleanups": cleanups}
    gate.validate(result, expected, selection)
    return result, expected, selection, tmp_path, env


def reject(gate, control, mutate, match):
    result, expected, selection, _, _ = control
    bad = copy.deepcopy(result)
    mutate(bad)
    with pytest.raises(ValueError, match=match):
        gate.validate(bad, expected, selection)


@pytest.mark.parametrize("flag", ["unset", "false"])
def test_record_requires_explicit_engine_flag(flag, tmp_path):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    env.pop("SPECIMEN_TEST_SQL_EMULATOR", None)
    if flag == "false":
        env["SPECIMEN_TEST_SQL_EMULATOR"] = flag
    completed = subprocess.run([sys.executable, str(GATE), "record", "--selection", str(SELECTION),
                                "--results", str(tmp_path), "--", sys.executable, "-c", "raise AssertionError('ran')"],
                               env=env, capture_output=True, text=True, timeout=30)
    assert completed.returncode != 0
    assert "SPECIMEN_TEST_SQL_EMULATOR=true" in completed.stderr
    assert not (tmp_path / "engine-contract.json").exists()


@pytest.mark.parametrize("fault", ["empty", "wrong", "extra", "missing", "duplicate_node", "duplicate_phase", "duplicate_json_key"])
def test_verify_requires_exact_inventory(gate, control, tmp_path, fault):
    result, expected, selection, _, _ = control
    bad = copy.deepcopy(result)
    nodes = bad["pytest"]["selected"]
    if fault == "empty":
        nodes.clear()
    elif fault == "wrong":
        nodes[0] = "tests/other.py::test_wrong"
    elif fault == "extra":
        nodes.append("tests/other.py::test_extra")
    elif fault == "missing":
        nodes.pop()
    elif fault == "duplicate_node":
        nodes.append(nodes[0])
    elif fault == "duplicate_phase":
        bad["pytest"]["events"].append(copy.deepcopy(bad["pytest"]["events"][0]))
    else:
        path = tmp_path / "duplicate.json"
        path.write_text(json.dumps(result).replace('"schema": 1', '"schema": 99, "schema": 1', 1))
        with pytest.raises(ValueError, match="duplicate JSON key"):
            gate.read_json(path)
        return
    with pytest.raises(ValueError, match="inventory|phase"):
        gate.validate(bad, expected, selection)


@pytest.mark.parametrize("fault", ["all_skipped_exit0", "xfail", "xpass", "setup_failed", "call_failed", "teardown_failed", "missing_call", "collection_error", "nonzero_exit"])
def test_verify_requires_all_phases_passed(gate, control, fault):
    def mutate(r):
        events = r["pytest"]["events"]
        if fault == "all_skipped_exit0":
            for event in events:
                event["outcome"] = "skipped"
        elif fault in ("xfail", "xpass"):
            events[1].update(outcome="skipped" if fault == "xfail" else "passed", wasxfail="expected fault")
        elif fault.endswith("_failed"):
            events[("setup_failed", "call_failed", "teardown_failed").index(fault)]["outcome"] = "failed"
        elif fault == "missing_call":
            events.pop(1)
        elif fault == "collection_error":
            r["pytest"]["collection_events"].append({"nodeid": "bad", "outcome": "failed"})
        else:
            r["pytest"]["exitstatus"] = 1
    reject(gate, control, mutate, "phase|collection|exit|xfail")


@pytest.mark.parametrize("fault", ["sha", "run", "attempt", "selection", "config", "toolchain", "source_changed"])
def test_verify_binds_current_identity(gate, control, fault):
    def mutate(r):
        key = {"sha": "source_sha", "run": "run_id", "attempt": "run_attempt",
               "selection": "selection_digest", "config": "config_digest", "toolchain": "toolchain_digest",
               "source_changed": "source_digest"}[fault]
        # Forging both ends must not overcome independently recomputed expected values.
        for part in ("context_start", "context_end"):
            r[part][key] = "forged"
    reject(gate, control, mutate, "identity|context|fingerprint")


@pytest.mark.parametrize("fault", ["binary", "java", "postgres", "seed", "readiness", "stage", "cleanup", "partial"])
def test_verify_requires_engine_lifecycle(gate, control, fault):
    def mutate(r):
        e = r["lifecycle"]
        if fault == "binary":
            e["tools"]["dataconnect"]["sha256"] = "0" * 64
        elif fault in ("java", "postgres"):
            e["runtime"].pop(fault)
        elif fault == "seed":
            e["seed"]["organization_active"] = False
        elif fault == "readiness":
            e["readiness"][0]["outcome"] = "failed"
        elif fault == "stage":
            e["stages"].pop()
        elif fault == "cleanup":
            e["cleanup"]["ports_free_after"] = False
        else:
            r["complete"] = False
    reject(gate, control, mutate, "tool|runtime|seed|readiness|stage|cleanup|complete")


@pytest.mark.parametrize("fault", ["missing_mode", "wrong_mode", "cold_hit", "reused_directory"])
def test_verify_rejects_false_cold_provenance(gate, control, fault):
    result, expected, selection, _, _ = control
    for mode in ("normal", "cold"):
        valid = copy.deepcopy(result)
        target = copy.deepcopy(expected)
        target["cache_mode"] = mode
        valid["context_start"]["cache_mode"] = valid["context_end"]["cache_mode"] = mode
        valid["lifecycle"]["cache"].update(mode=mode, restore="bypassed" if mode == "cold" else "hit",
                                            directory_fresh=mode == "cold", entries_before=0 if mode == "cold" else 3)
        gate.validate(valid, target, selection)
        assert valid["pytest"] == result["pytest"]
    bad = copy.deepcopy(valid)
    cache = bad["lifecycle"]["cache"]
    if fault == "missing_mode":
        cache.pop("mode")
    elif fault == "wrong_mode":
        cache["mode"] = "normal"
    elif fault == "cold_hit":
        cache["restore"] = "hit"
    else:
        cache.update(directory_fresh=False, entries_before=1)
    with pytest.raises(ValueError, match="cache|cold"):
        gate.validate(bad, target, selection)


@pytest.mark.parametrize("fault", ["nan", "infinity", "negative", "schema", "denial", "duplicate_stage", "extra_stage", "process", "flag", "extra_collection", "local", "collection_unfinished", "wasxfail_empty"])
def test_verify_additional_fail_closed_boundaries(gate, control, fault):
    def mutate(r):
        if fault in ("nan", "infinity", "negative"):
            r["pytest"]["events"][0]["seconds"] = {"nan": float("nan"), "infinity": float("inf"), "negative": -1}[fault]
        elif fault == "schema":
            r["schema"] = 2
        elif fault == "denial":
            events = r["lifecycle"]["node_events"]
            events.pop(next(i for i, event in enumerate(events) if event["id"] == "storage.anonymous.read"))
        elif fault == "duplicate_stage":
            r["lifecycle"]["stages"].append(r["lifecycle"]["stages"][0])
        elif fault == "extra_stage":
            r["lifecycle"]["stages"].append({"id": "extra", "outcome": "passed", "seconds": 0})
        elif fault == "process":
            r["lifecycle"]["processes"][0]["stopped"] = False
        elif fault == "flag":
            r["lifecycle"]["engine_flag"] = "false"
        elif fault == "extra_collection":
            r["pytest"]["collected"].append("unexpected")
        elif fault == "local":
            r["context_start"]["qualification"] = "local"
        elif fault == "collection_unfinished":
            r["pytest"]["finished"] = False
        else:
            r["pytest"]["events"][1]["wasxfail"] = ""
    reject(gate, control, mutate, ".+")


def test_expected_hashes_come_from_current_files(gate, control):
    result, _, selection, root, env = control
    for path in ("src/app.py", "firebase.json", "scripts/data/engine-toolchain.json", "scripts/data/engine-contract-selection.json"):
        file = root / path
        original = file.read_bytes()
        file.write_bytes(original + b"\n")
        current = gate.expected_context(root, root / "scripts/data/engine-contract-selection.json", env)
        with pytest.raises(ValueError, match="context|identity|fingerprint"):
            gate.validate(result, current, selection)
        file.write_bytes(original)


@pytest.mark.parametrize("fault", ["missing", "partial", "symlink", "extra", "unknown", "nan", "duplicate_nested"])
def test_result_file_boundary(gate, control, tmp_path, fault):
    result = control[0]
    output = tmp_path / "results"
    output.mkdir()
    path = output / "engine-contract.json"
    path.write_text(json.dumps(result))
    if fault == "missing":
        path.unlink()
    elif fault == "partial":
        path.rename(output / "engine-contract.json.partial")
    elif fault == "symlink":
        path.rename(tmp_path / "target.json")
        path.symlink_to(tmp_path / "target.json")
    elif fault == "extra":
        (output / "engine-contract-old.json").write_text("{}")
    elif fault == "unknown":
        path.write_text('{"schema": 99}')
    elif fault == "nan":
        path.write_text('{"schema": 1, "seconds": NaN}')
    else:
        path.write_text('{"schema":1,"nested":{"id":1,"id":2}}')
    with pytest.raises((ValueError, OSError)):
        gate.read_result(output)


def run_tiny(gate, tmp_path, source, args=()):
    module = tmp_path / "test_tiny.py"
    module.write_text(source)
    output = tmp_path / "phases.json"
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
               ENGINE_CONTRACT_PYTEST_REPORT=str(output), PYTHONPATH=str(GATE.parent))
    completed = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "engine_contract_gate",
                                "--rootdir", str(tmp_path), str(module), *args], cwd=tmp_path, env=env,
                               capture_output=True, text=True, timeout=30)
    assert output.exists(), completed.stdout + completed.stderr
    return completed, gate.read_json(output)


def test_reporter_integration_preserves_phase_events(gate, tmp_path):
    completed, report = run_tiny(gate, tmp_path,
        "import pytest\n@pytest.fixture\ndef broken():\n yield\n assert False, 'teardown proof'\n"
        "def test_pass(): pass\n@pytest.mark.xfail(reason='xfail proof')\ndef test_xfail(): assert False\n"
        "@pytest.mark.xfail(reason='xpass proof')\ndef test_xpass(): pass\ndef test_teardown(broken): pass\n")
    assert completed.returncode == 1
    assert report["finished"] is True
    assert len(report["collected"]) == len(report["selected"]) == 4
    assert len(report["events"]) == 12
    assert [(e["phase"], e["outcome"]) for e in report["events"][-3:]] == [("setup", "passed"), ("call", "passed"), ("teardown", "failed")]
    assert [e["wasxfail"] for e in report["events"] if e["wasxfail"] is not None] == ["xfail proof", "xpass proof"]


def test_engine_results_are_separate_from_default_shard_inventory(gate, tmp_path):
    default_file = tmp_path / "test_default.py"
    default_file.write_text("def test_default(): pass\n")
    engine_file = tmp_path / "engine_contract.py"
    engine_file.write_text("def test_engine(): pass\n")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    default = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", str(tmp_path)],
                             cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
    assert default.returncode == 0
    assert "test_default.py::test_default" in default.stdout
    assert "engine_contract.py::test_engine" not in default.stdout
    completed, report = run_tiny(gate, tmp_path, "def test_explicit(): pass\n")
    assert completed.returncode == 0
    assert report["selected"] == ["test_tiny.py::test_explicit"]
    frozen = gate.load_selection(SELECTION)
    assert len(frozen["python_nodes"]) == 9
    assert len(frozen["residual_opt_in_sql"]) == 17
    assert len(frozen["connector_groups"]) == 19
    assert len(frozen["storage_assertions"]) == 13
    assert all("engine_sqlconnect_authorization_contract.py" in node for node in frozen["python_nodes"][3:])


def test_reporter_preserves_duplicate_events(gate):
    from types import SimpleNamespace
    reporter = gate.Reporter(Path("unused"))
    event = SimpleNamespace(nodeid="test.py::test_a", when="call", outcome="passed", duration=0.1)
    reporter.pytest_runtest_logreport(event)
    reporter.pytest_runtest_logreport(event)
    assert len(reporter.events) == 2


def test_local_environment_cannot_qualify(gate, control):
    _, _, _, root, env = control
    env.pop("GITHUB_ACTIONS")
    with pytest.raises(ValueError, match="hosted"):
        gate.expected_context(root, root / "scripts/data/engine-contract-selection.json", env)


def test_source_change_during_record_never_publishes(gate, control, monkeypatch):
    result, expected, selection, root, _ = control
    output = root / "results"
    def run(*args, **kwargs):
        (root / "src/app.py").write_text("VALUE = 2\n")
        return 0, result["pytest"], result["lifecycle"], result["process_receipts"]
    monkeypatch.setattr(gate, "run_command", run)
    monkeypatch.setattr(gate, "inspect_tools", lambda *_: {"tools": result["lifecycle"]["tools"], "runtime": result["lifecycle"]["runtime"]})
    monkeypatch.setattr(gate, "assert_cleanup", lambda *_: None)
    env = control[-1] | {"SPECIMEN_TEST_SQL_EMULATOR": "true"}
    with pytest.raises(ValueError, match="source|context|fingerprint"):
        gate.record(root, root / "scripts/data/engine-contract-selection.json", output, ["fixture"], env)
    assert not (output / "engine-contract.json").exists()


@pytest.mark.parametrize("failure", ["none", "cleanup", "cleanup_source_change", "wrapper_exit", "pytest_exit"])
def test_record_and_verify_boundary(gate, control, monkeypatch, failure):
    result, _, _, root, env = control
    output = root / "results"
    def run(*args, **kwargs):
        assert not (output / "engine-contract.json").exists()
        report = copy.deepcopy(result["pytest"])
        if failure == "pytest_exit":
            report["exitstatus"] = 1
        return int(failure == "wrapper_exit"), report, result["lifecycle"], result["process_receipts"]
    def cleanup(lifecycle):
        assert not (output / "engine-contract.json").exists()
        if failure == "cleanup":
            raise ValueError("owned cleanup failed")
        if failure == "cleanup_source_change":
            (root / "src/app.py").write_text("VALUE = 3\n")
    monkeypatch.setattr(gate, "run_command", run)
    monkeypatch.setattr(gate, "inspect_tools", lambda *_: {"tools": result["lifecycle"]["tools"], "runtime": result["lifecycle"]["runtime"]})
    monkeypatch.setattr(gate, "assert_cleanup", cleanup)
    monkeypatch.setattr(gate, "ROOT", root)
    for key, value in (env | {"SPECIMEN_TEST_SQL_EMULATOR": "true"}).items():
        monkeypatch.setenv(key, value)
    args = ["--selection", str(root / "scripts/data/engine-contract-selection.json"), "--results", str(output)]
    status = gate.main(["record", *args, "--", "fixture"])
    assert status == int(failure != "none")
    if failure != "none":
        assert not (output / "engine-contract.json").exists()
    else:
        assert gate.main(["verify", *args]) == 0
        saved = gate.read_result(output)
        assert saved["pytest"] == result["pytest"]
        assert saved["lifecycle"] == result["lifecycle"]


def test_reporter_collection_errors_reach_verifier(gate, tmp_path):
    completed, report = run_tiny(gate, tmp_path, "raise RuntimeError('collection proof')\n")
    assert completed.returncode != 0
    assert report["collection_events"] == [{"nodeid": "test_tiny.py", "outcome": "failed"}]
    assert report["events"] == []


@pytest.mark.parametrize("key,value", [("GITHUB_SHA", "b" * 40), ("GITHUB_RUN_ID", ""),
                                       ("GITHUB_RUN_ATTEMPT", "0"), ("ENGINE_CACHE_MODE", ""),
                                       ("ENGINE_CACHE_MODE", "unknown"), ("GITHUB_EVENT_NAME", "schedule")])
def test_expected_context_rejects_invalid_environment(gate, control, key, value):
    _, _, _, root, env = control
    env[key] = value
    with pytest.raises(ValueError):
        gate.expected_context(root, root / "scripts/data/engine-contract-selection.json", env)


@pytest.mark.parametrize("event", ["push", "pull_request"])
def test_cold_mode_is_dispatch_only(gate, control, event):
    _, _, _, root, env = control
    env.update(GITHUB_EVENT_NAME=event, ENGINE_CACHE_MODE="cold")
    with pytest.raises(ValueError, match="dispatch-only"):
        gate.expected_context(root, root / "scripts/data/engine-contract-selection.json", env)


@pytest.mark.parametrize("field", ["postgres_host", "dataconnect_host", "python_host", "storage_host"])
def test_verify_rejects_host_drift(gate, control, field):
    reject(gate, control, lambda r: r["lifecycle"]["preflight"].update({field: "127.0.0.1:9999"}), "host mismatch")


def test_reporter_keeps_original_collection_before_deselection(gate, tmp_path):
    completed, report = run_tiny(gate, tmp_path, "def test_keep(): pass\ndef test_drop(): pass\n", ("-k", "test_keep"))
    assert completed.returncode == 0
    assert report["collected"] == ["test_tiny.py::test_keep", "test_tiny.py::test_drop"]
    assert report["selected"] == ["test_tiny.py::test_keep"]
    assert len(report["events"]) == 3


@pytest.mark.parametrize("scratch_failure", [False, True])
def test_record_final_waits_for_scratch_cleanup(gate, control, monkeypatch, scratch_failure):
    result, _, _, root, env = control
    output = root / "results"
    original_temporary = gate.tempfile.TemporaryDirectory
    class CheckedScratch:
        def __init__(self, **kwargs):
            self.owner = original_temporary(**kwargs)
        def __enter__(self):
            return self.owner.__enter__()
        def __exit__(self, *args):
            assert not (output / "engine-contract.json").exists(), "final published before scratch cleanup"
            self.owner.__exit__(*args)
            if scratch_failure:
                raise OSError("scratch cleanup failed")
    monkeypatch.setattr(gate.tempfile, "TemporaryDirectory", CheckedScratch)
    monkeypatch.setattr(gate, "run_command", lambda *_: (0, result["pytest"], result["lifecycle"], result["process_receipts"]))
    monkeypatch.setattr(gate, "inspect_tools", lambda *_: {"tools": result["lifecycle"]["tools"], "runtime": result["lifecycle"]["runtime"]})
    monkeypatch.setattr(gate, "assert_cleanup", lambda *_: None)
    args = (root, root / "scripts/data/engine-contract-selection.json", output, ["fixture"],
            env | {"SPECIMEN_TEST_SQL_EMULATOR": "true"})
    if scratch_failure:
        with pytest.raises(OSError, match="scratch cleanup failed"):
            gate.record(*args)
        assert not (output / "engine-contract.json").exists()
    else:
        gate.record(*args)
        assert (output / "engine-contract.json").is_file()


PROCESS_FAULTS = (
    "no_registry", "no_launch", "no_cleanup", "missing_birth", "mismatched_birth",
    "launch_missing_birth", "cleanup_missing_birth", "cleanup_mismatched_birth",
    "unbound_receipt", "aliased_receipt", "aliased_os_instance", "missing_start",
    "missing_end", "invalid_start", "invalid_end", "boolean_time", "nan_time",
    "negative_time", "reversed_time", "before_window", "after_window", "missing_window",
    "invalid_window", "overlapping_pid_reuse",
    "missing_os_start", "invalid_os_start", "old_os_start", "future_os_start",
    "missing_epoch_window", "invalid_epoch_window",
)


def corrupt_process(result, fault):
    receipts = result["process_receipts"]
    process = result["lifecycle"]["processes"][0]
    launch, cleanup = receipts["launches"][0], receipts["cleanups"][0]
    if fault == "no_registry":
        result.pop("process_receipts")
    elif fault == "no_launch":
        receipts["launches"].pop(0)
    elif fault == "no_cleanup":
        receipts["cleanups"].pop(0)
    elif fault == "missing_birth":
        process.pop("birth_id")
    elif fault == "mismatched_birth":
        process["birth_id"] = "f" * 64
    elif fault == "launch_missing_birth":
        launch.pop("birth_id")
    elif fault == "cleanup_missing_birth":
        cleanup.pop("birth_id")
    elif fault == "cleanup_mismatched_birth":
        cleanup["birth_id"] = "f" * 64
    elif fault == "unbound_receipt":
        cleanup["instance"] = "f" * 32
    elif fault in ("aliased_receipt", "aliased_os_instance", "overlapping_pid_reuse"):
        other_launch = receipts["launches"][1]
        other_cleanup = receipts["cleanups"][1]
        other_process = result["lifecycle"]["processes"][1]
        for row in (other_launch, other_cleanup, other_process):
            if fault == "aliased_receipt":
                row["instance"] = launch["instance"]
            else:
                row["pid"] = launch["pid"]
                if fault == "aliased_os_instance":
                    row["birth_id"] = launch["birth_id"]
                else:
                    row["started_ns"] = process["ended_ns"] - 1
    elif fault == "missing_window":
        receipts.pop("ended_ns")
    elif fault == "invalid_window":
        receipts["ended_ns"] = receipts["started_ns"]
    elif fault == "missing_epoch_window":
        receipts.pop("epoch_started_ns")
    elif fault == "invalid_epoch_window":
        receipts["epoch_ended_ns"] = receipts["epoch_started_ns"]
    elif fault in ("missing_os_start", "invalid_os_start", "old_os_start", "future_os_start"):
        for row in (process, launch, cleanup):
            if fault == "missing_os_start":
                row.pop("os_started_ns")
            else:
                row["os_started_ns"] = {"invalid_os_start": True,
                    "old_os_start": receipts["epoch_started_ns"] - 10**9 - 1,
                    "future_os_start": receipts["epoch_ended_ns"] + 1}[fault]
    else:
        key = "started_ns" if fault in ("missing_start", "invalid_start", "before_window") else "ended_ns"
        for row in ((launch, cleanup, process) if key == "started_ns" else (cleanup, process)):
            if fault in ("missing_start", "missing_end"):
                row.pop(key)
            else:
                row[key] = {"invalid_start": "10", "invalid_end": float("inf"), "boolean_time": True,
                            "nan_time": float("nan"), "negative_time": -1, "reversed_time": 9,
                            "before_window": 0, "after_window": 101}[fault]


@pytest.mark.parametrize("fault", PROCESS_FAULTS)
def test_verify_requires_bound_process_instances_and_times(gate, control, fault):
    reject(gate, control, lambda r: corrupt_process(r, fault), "process|receipt|birth|timestamp|lifecycle")


def test_verify_accepts_sequential_restarts_and_pid_reuse(gate, control):
    result, expected, selection, _, _ = control
    valid = copy.deepcopy(result)
    # The OS can recycle a PID after the previous instance has been reaped.
    # Distinct roles/births/tokens and nonoverlapping lifetimes remain required.
    pid = valid["lifecycle"]["processes"][0]["pid"]
    for rows in (valid["lifecycle"]["processes"], valid["process_receipts"]["launches"],
                 valid["process_receipts"]["cleanups"]):
        for row in rows:
            row["pid"] = pid
    gate.validate(valid, expected, selection)


@pytest.mark.parametrize("fault", PROCESS_FAULTS)
def test_record_withholds_final_for_invalid_process_receipts(gate, control, monkeypatch, fault):
    result, _, _, root, env = control
    bad = copy.deepcopy(result)
    corrupt_process(bad, fault)
    monkeypatch.setattr(gate, "run_command", lambda *_: (0, bad["pytest"], bad["lifecycle"], bad.get("process_receipts")))
    monkeypatch.setattr(gate, "inspect_tools", lambda *_: {"tools": bad["lifecycle"]["tools"], "runtime": bad["lifecycle"]["runtime"]})
    monkeypatch.setattr(gate, "assert_cleanup", lambda *_: None)
    output = root / "invalid-process-output"
    with pytest.raises(ValueError, match="process|receipt|birth|timestamp|lifecycle"):
        gate.record(root, root / "scripts/data/engine-contract-selection.json", output, ["fixture"],
                    env | {"SPECIMEN_TEST_SQL_EMULATOR": "true"})
    assert not (output / "engine-contract.json").exists()


@pytest.mark.parametrize("fault", ["dead_pid", "birth_changed", "unbound", "alias", "still_running", "not_waited", "too_old"])
def test_registration_checks_live_os_identity(gate, monkeypatch, fault):
    registry = gate.ProcessRegistry(["first", "second"])
    identity = ["a" * 64, gate.time.time_ns()]
    monkeypatch.setattr(gate, "process_birth", lambda pid: tuple(identity))
    if fault == "dead_pid":
        def absent(pid):
            raise ProcessLookupError(pid)
        monkeypatch.setattr(gate, "process_birth", absent)
        with pytest.raises(ProcessLookupError):
            registry.start("first", 100)
        return
    if fault == "too_old":
        identity[1] = 1
        with pytest.raises(ValueError, match="launch|birth"):
            registry.start("first", 100)
        return
    launch = registry.start("first", 100)
    assert launch["birth_id"] == identity[0]
    assert launch["started_ns"] >= registry.started_ns
    if fault == "alias":
        with pytest.raises(ValueError, match="alias|instance"):
            registry.start("second", 100)
        return
    receipt = dict(launch)
    if fault == "birth_changed":
        receipt["birth_id"] = "b" * 64
    elif fault == "unbound":
        receipt["instance"] = "b" * 32
    if fault != "still_running":
        monkeypatch.setattr(gate, "process_birth", lambda pid: None)
    with pytest.raises(ValueError, match="process|receipt|wait"):
        registry.end(receipt, waited=fault != "not_waited")


def test_process_receipt_cli_and_recorder_registry(gate, tmp_path, monkeypatch):
    """Real children and CLI/recorder IPC; OS birth lookup is an injected fixture.

    The local macOS sandbox denies ps. Linux /proc parsing is tested separately;
    canonical hosted runs use the unpatched OS reader and cannot qualify here.
    """
    def birth(pid):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return None
        return f"{pid:064x}", gate.time.time_ns()
    monkeypatch.setattr(gate, "process_birth", birth)
    with gate.process_server(["first", "second"]) as (registry, child_env):
        for role in ("first", "second"):
            child = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.read()"], stdin=subprocess.PIPE)
            try:
                env = dict(os.environ, **child_env, PYTHONDONTWRITEBYTECODE="1")
                start = subprocess.run([sys.executable, str(GATE), "process-start", "--id", role, "--pid", str(child.pid)],
                                       env=env, capture_output=True, text=True, timeout=30)
                assert start.returncode == 0, start.stderr
                receipt = json.loads(start.stdout)
                assert receipt["birth_id"] == gate.process_birth(child.pid)[0]
                receipt_path = tmp_path / (role + ".json")
                receipt_path.write_text(start.stdout)
                child.communicate(timeout=30)
                end = subprocess.run([sys.executable, str(GATE), "process-end", "--receipt", str(receipt_path), "--waited"],
                                     env=env, capture_output=True, text=True, timeout=30)
                assert end.returncode == 0, end.stderr
                cleanup = json.loads(end.stdout)
                assert cleanup["instance"] == receipt["instance"]
                assert cleanup["ended_ns"] > receipt["started_ns"]
                assert cleanup["owned"] is cleanup["stopped"] is cleanup["waited"] is True
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=30)
        observed = registry.snapshot()
    assert [row["id"] for row in observed["launches"]] == ["first", "second"]
    assert [row["id"] for row in observed["cleanups"]] == ["first", "second"]
    assert observed["started_ns"] < observed["ended_ns"]


@pytest.mark.parametrize("fault", ["none", "absent", "permission", "recycled"])
def test_linux_birth_reader_uses_kernel_identity(gate, monkeypatch, fault):
    monkeypatch.setattr(gate.sys, "platform", "linux")
    monkeypatch.setattr(gate.os, "kill", lambda *_: None)
    monkeypatch.setattr(gate.os, "sysconf", lambda key: 100)
    ticks = [12345]
    def read(path, *args, **kwargs):
        name = str(path)
        if name == "/proc/101/stat":
            if fault == "absent":
                raise FileNotFoundError(name)
            if fault == "permission":
                raise PermissionError(name)
            # comm deliberately contains spaces and parentheses.
            return "101 (engine (worker)) " + " ".join(["S"] + ["0"] * 18 + [str(ticks[0])])
        if name == "/proc/stat":
            return "cpu 1 2 3\nbtime 1700000000\n"
        if name == "/proc/sys/kernel/random/boot_id":
            return "kernel-boot-identity\n"
        raise AssertionError(name)
    monkeypatch.setattr(gate.Path, "read_text", read)
    if fault == "permission":
        with pytest.raises(PermissionError):
            gate.process_birth(101)
    elif fault == "absent":
        assert gate.process_birth(101) is None
    else:
        identity, born_ns = gate.process_birth(101)
        assert identity == gate.digest({"boot_id": "kernel-boot-identity", "start_ticks": 12345})
        assert born_ns == 1700000123450000000
        if fault == "recycled":
            ticks[0] += 1
            assert gate.process_birth(101)[0] != identity


@pytest.mark.parametrize("fault", ["none", "unregistered", "mismatched_birth", "ignored_error", "missing_cleanup"])
def test_real_recorder_registry_boundary(gate, control, monkeypatch, fault):
    """The real child runner must return its live registry, never a harness file."""
    import socket
    result, _, selection, root, env = control
    lifecycle = copy.deepcopy(result["lifecycle"])
    with socket.socket() as first, socket.socket() as second, socket.socket() as third:
        servers = (first, second, third)
        for server in servers:
            server.bind(("127.0.0.1", 0))
        ports = [server.getsockname()[1] for server in servers]
    lifecycle["preflight"].update(ports=ports, postgres_host=f"127.0.0.1:{ports[0]}",
        dataconnect_host=f"127.0.0.1:{ports[1]}", python_host=f"127.0.0.1:{ports[1]}", storage_host=f"127.0.0.1:{ports[2]}")
    payload = root / "harness-input.json"
    payload.write_text(json.dumps({"lifecycle": lifecycle, "pytest": result["pytest"], "roles": selection["processes"]}))
    harness = root / "harness.py"
    harness.write_text('''import json, os, subprocess, sys
from pathlib import Path
import engine_contract_gate as gate
payload = json.loads(Path(sys.argv[1]).read_text())
fault = sys.argv[2]
rows = []
if fault != "unregistered":
    for i, role in enumerate(payload["roles"]):
        child = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.read()"], stdin=subprocess.PIPE)
        try:
            launch = gate.process_request({"action": "start", "id": role, "pid": child.pid})
            child.communicate(timeout=10)
            if fault == "missing_cleanup" and i == 0:
                continue
            cleanup = gate.process_request({"action": "end", "receipt": launch, "waited": True})
            rows.append(cleanup)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=10)
    if fault == "ignored_error":
        try:
            gate.process_request({"action": "start", "id": "unknown", "pid": 2147483647})
        except ValueError:
            pass
    payload["lifecycle"]["processes"] = rows
if fault == "mismatched_birth":
    rows[0]["birth_id"] = "f" * 64
Path(os.environ["ENGINE_CONTRACT_LIFECYCLE"]).write_text(json.dumps(payload["lifecycle"]))
Path(os.environ["ENGINE_CONTRACT_PYTEST_REPORT"]).write_text(json.dumps(payload["pytest"]))
''')
    def birth(pid):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return None
        return f"{pid:064x}", gate.time.time_ns()
    monkeypatch.setattr(gate, "process_birth", birth)
    monkeypatch.setattr(gate, "ROOT", root)
    monkeypatch.setattr(gate, "inspect_tools", lambda *_: {"tools": lifecycle["tools"], "runtime": lifecycle["runtime"]})
    output = root / "real-registry-result"
    args = (root, root / "scripts/data/engine-contract-selection.json", output,
            [sys.executable, str(harness), str(payload), fault],
            env | {"SPECIMEN_TEST_SQL_EMULATOR": "true", "PYTHONPATH": str(GATE.parent), "PYTHONDONTWRITEBYTECODE": "1"})
    if fault == "none":
        observed = gate.record(*args)
        saved = gate.read_result(output)
        assert saved == observed
        assert saved["lifecycle"]["processes"] == saved["process_receipts"]["cleanups"]
        assert len(saved["process_receipts"]["launches"]) == 7
    else:
        with pytest.raises(ValueError, match="process|receipt|registration"):
            gate.record(*args)
        assert not (output / "engine-contract.json").exists()


@pytest.mark.parametrize("state", ["unused", "listening", "time_wait"])
def test_record_cleanup_distinguishes_listener_from_time_wait(gate, control, monkeypatch, state):
    """Real TCP shutdown; synthetic harness/Git/tools/OS identity, never engines."""
    result, expected, selection, root, env = control
    valid = copy.deepcopy(result)
    output = root / "port-result"
    with socket.socket() as listener, socket.socket() as second, socket.socket() as third:
        # Linux requires SO_REUSEADDR on both the old and replacement sockets.
        # Also use it on the surviving-listener control: reuse cannot excuse it.
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.settimeout(5)
        for server in (listener, second, third):
            server.bind(("127.0.0.1", 0))
        ports = [server.getsockname()[1] for server in (listener, second, third)]
        port = ports[0]
        second.close()
        third.close()
        if state in ("listening", "time_wait"):
            listener.listen(1)
        if state == "time_wait":
            with socket.create_connection(("127.0.0.1", port), timeout=5) as client:
                peer, _ = listener.accept()
                with peer:
                    peer.settimeout(5)
                    # Server sends FIN first. EOF handshakes synchronize both
                    # closes without sleeps/retries and leave server TIME_WAIT.
                    peer.shutdown(socket.SHUT_WR)
                    assert client.recv(1) == b"", "client did not receive server FIN"
                    client.shutdown(socket.SHUT_WR)
                    assert peer.recv(1) == b"", "server did not receive client FIN"
        if state != "listening":
            listener.close()
            with socket.socket() as probe:
                probe.settimeout(5)
                assert probe.connect_ex(("127.0.0.1", port)) == errno.ECONNREFUSED, "unexpected surviving listener"
        if state == "time_wait":
            with socket.socket() as bare:
                with pytest.raises(OSError) as error:
                    bare.bind(("127.0.0.1", port))
                assert error.value.errno == errno.EADDRINUSE, "control did not retain TCP TIME_WAIT"
            with socket.socket() as replacement:
                replacement.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                replacement.bind(("127.0.0.1", port))
                replacement.listen(1)

        valid["lifecycle"]["preflight"].update(
            ports=ports, postgres_host=f"127.0.0.1:{ports[0]}",
            dataconnect_host=f"127.0.0.1:{ports[1]}", python_host=f"127.0.0.1:{ports[1]}",
            storage_host=f"127.0.0.1:{ports[2]}")
        gate.validate(valid, expected, selection)

        def run(*_):
            assert not (output / "engine-contract.json").exists(), "final published before harness exit"
            return 0, valid["pytest"], valid["lifecycle"], valid["process_receipts"]

        checked = []

        def birth(pid):
            assert not (output / "engine-contract.json").exists(), "final published before process cleanup"
            checked.append(pid)
            return None

        monkeypatch.setattr(gate, "run_command", run)
        monkeypatch.setattr(gate, "inspect_tools", lambda *_: {"tools": valid["lifecycle"]["tools"], "runtime": valid["lifecycle"]["runtime"]})
        monkeypatch.setattr(gate, "process_birth", birth)
        args = (root, root / "scripts/data/engine-contract-selection.json", output, ["fixture"],
                env | {"SPECIMEN_TEST_SQL_EMULATOR": "true"})
        if state == "listening":
            with pytest.raises(OSError) as error:
                gate.record(*args)
            assert error.value.errno == errno.EADDRINUSE, "live listener must refuse the cleanup bind"
            assert list(output.iterdir()) == [], "failed cleanup published a final or left partial evidence"
        else:
            observed = gate.record(*args)
            assert gate.read_result(output) == observed
            assert observed["complete"] is True
            assert [path.name for path in output.iterdir()] == ["engine-contract.json"]
        assert checked == [process["pid"] for process in valid["lifecycle"]["processes"]]


# Exact values are synthetic observations, independent of the approved majors.
def runtime_control():
    return {"java": "21.0.12+1", "postgres": "16.15", "node": "22.23.3",
            "image_os": "ubuntu24", "image_version": "20261012.334.1",
            "postgres_bin": "/usr/lib/postgresql/16/bin", "java_home_env": "JAVA_HOME_21_X64",
            "postgres_clients": ["initdb", "pg_ctl", "createdb", "psql", "pg_dump", "pg_restore"],
            "uuid_ossp": True, "postgres_server": "16.15",
            "postgres_client_versions": {name: "16.15" for name in
                ("initdb", "pg_ctl", "createdb", "psql", "pg_dump", "pg_restore")}}


@pytest.mark.parametrize("field,value", [("image_version", "20261019.400.1"),
    ("java", "21.0.13+11"), ("java", "21+35"), ("java", "21.0.13.1+11"),
    ("postgres", "16.16"), ("node", "22.24.0")])
def test_verify_accepts_new_runner_patch(gate, control, field, value):
    result, expected, selection, _, _ = control
    runtime = runtime_control()
    runtime[field] = value
    if field == "postgres":
        runtime["postgres_server"] = value
        runtime["postgres_client_versions"] = dict.fromkeys(runtime["postgres_clients"], value)
    result["lifecycle"]["runtime"] = runtime
    result["lifecycle"]["postgres_server_version"] = runtime["postgres_server"] + " (Ubuntu fixture)"
    result["runtime_observed"] = copy.deepcopy(runtime)
    gate.validate(result, expected, selection)


@pytest.mark.parametrize("field,value", [("java", "17.0.16+8"), ("java", "25.0.1+8"),
    ("node", "20.19.0"), ("node", "24.1.0"), ("postgres", "15.15"), ("postgres", "17.6"),
    ("postgres_bin", "/usr/lib/postgresql/15/bin"), ("postgres_bin", "/usr/lib/postgresql/17/bin"),
    ("image_version", ""), ("image_version", " "), ("image_version", None),
    ("java", "21garbage"), ("node", "22garbage"), ("postgres", "16garbage")])
def test_verify_rejects_unapproved_runtime(gate, control, field, value):
    result, expected, selection, _, _ = control
    runtime = runtime_control()
    runtime[field] = value
    if value is None:
        runtime.pop(field)
    result["lifecycle"]["runtime"] = runtime
    result["runtime_observed"] = copy.deepcopy(runtime)
    with pytest.raises(ValueError, match="runtime|version|PostgreSQL"):
        gate.validate(result, expected, selection)


@pytest.mark.parametrize("field", ["java", "node", "postgres", "image_version", "postgres_client_versions", "postgres_server"])
def test_verify_rejects_recorded_runtime_drift(gate, control, field):
    result, expected, selection, _, _ = control
    result["runtime_observed"] = runtime_control()
    result["lifecycle"]["runtime"] = runtime_control()
    result["lifecycle"]["runtime"][field] = {"java": "21.0.13+11", "node": "22.24.0",
        "postgres": "16.16", "image_version": "20261019.400.1", "postgres_server": "16.16",
        "postgres_client_versions": dict.fromkeys(runtime_control()["postgres_clients"], "16.16")}[field]
    with pytest.raises(ValueError, match="runtime.*observ|observ.*runtime"):
        gate.validate(result, expected, selection)


@pytest.fixture
def runner_tools(gate, tmp_path, monkeypatch):
    runtime = runtime_control()
    cache = tmp_path / "tool-cache"
    node = cache / "node/22.23.3/x64/bin/node"
    node.parent.mkdir(parents=True)
    node.write_text("fixture")
    node.chmod(0o700)
    home = tmp_path / "jdk21"
    (home / "bin").mkdir(parents=True)
    (home / "bin/java").write_text("fixture")
    (home / "bin/java").chmod(0o700)
    env = {"ImageOS": "ubuntu24", "ImageVersion": runtime["image_version"],
           "JAVA_HOME_21_X64": str(home), "JAVA_HOME": str(home),
           "POSTGRES_BIN": runtime["postgres_bin"], "RUNNER_TOOL_CACHE": str(cache), "PATH": str(node.parent)}
    monkeypatch.setattr(gate.platform, "system", lambda: "Linux")
    monkeypatch.setattr(gate.platform, "machine", lambda: "x86_64")
    original = Path.is_file
    monkeypatch.setattr(Path, "is_file", lambda p: True if str(p) == "/usr/share/postgresql/16/extension/uuid-ossp.control" else original(p))
    for name, variable in {"dataconnect": "DATACONNECT_EMULATOR_BIN", "storage": "STORAGE_RULES_RUNTIME_JAR", "firebase": "FIREBASE_CLI_BIN"}.items():
        path = tmp_path / name
        path.write_bytes(b"fixture")
        path.chmod(0o700)
        monkeypatch.setitem(gate.APPROVED_TOOLCHAIN["assets"], name,
                            dict(gate.APPROVED_TOOLCHAIN["assets"][name], bytes=7, sha256=gate.file_hash(path)))
        env[variable] = str(path)
    def probe(command, **kwargs):
        name = Path(command[0]).name
        version = runtime["java"] if name == "java" else runtime["node"] if name == "node" else runtime["postgres_client_versions"].get(name, runtime["postgres"])
        output = f"OpenJDK Runtime Environment (build {version}-LTS)" if name == "java" else "v" + version if name == "node" else f"{name} (PostgreSQL) {version} (Ubuntu fixture)"
        return subprocess.CompletedProcess(command, 0, output, "")
    monkeypatch.setattr(gate.subprocess, "run", probe)
    return env, runtime, node


@pytest.mark.parametrize("field,value", [("image_version", "20261019.400.1"),
    ("java", "21.0.13+11"), ("java", "21+35"), ("java", "21.0.13.1+11"),
    ("postgres", "16.16"), ("node", "22.24.0")])
def test_preflight_accepts_new_runner_patch(gate, runner_tools, field, value):
    env, runtime, _ = runner_tools
    runtime[field] = value
    if field == "image_version":
        env["ImageVersion"] = value
    if field == "postgres":
        runtime["postgres_client_versions"] = dict.fromkeys(runtime["postgres_clients"], value)
    if field == "node":
        old_node = runner_tools[2]
        new_node = old_node.parents[3] / value / "x64/bin/node"
        new_node.parent.mkdir(parents=True)
        old_node.rename(new_node)
        env["PATH"] = str(new_node.parent)
    inspected = gate.inspect_tools(env)
    assert set(inspected["tools"]) == {"dataconnect", "storage", "firebase"}
    assert inspected["runtime"][field] == value


@pytest.mark.parametrize("field,value", [("java", "17.0.16+8"), ("java", "25.0.1+8"),
    ("node", "20.19.0"), ("node", "24.1.0"), ("postgres", "15.15"), ("postgres", "17.6"),
    ("ImageVersion", ""), ("ImageVersion", None),
    ("POSTGRES_BIN", "/usr/lib/postgresql/15/bin"), ("POSTGRES_BIN", "/usr/lib/postgresql/17/bin")])
def test_preflight_rejects_wrong_runtime(gate, runner_tools, field, value):
    env, runtime, _ = runner_tools
    if field in ("java", "node", "postgres"):
        runtime[field] = value
        if field == "postgres":
            runtime["postgres_client_versions"] = dict.fromkeys(runtime["postgres_clients"], value)
    elif value is None:
        env.pop(field)
    else:
        env[field] = value
    with pytest.raises(ValueError, match="runtime|version|PostgreSQL"):
        gate.inspect_tools(env)


def test_runner_node_selection_is_numeric_highest_22(gate, runner_tools):
    env, _, node = runner_tools
    for version in ("20.99.0", "24.0.0", "22.9.0", "22.24.0", "22.24.0-rc.1"):
        other = node.parents[3] / version / "x64/bin/node"
        other.parent.mkdir(parents=True)
        other.write_text("fixture")
        other.chmod(0o700)
    assert gate.select_node_bin(env) == node.parents[3] / "22.24.0/x64/bin"
    for directory in node.parents[3].glob("22.*"):
        import shutil
        shutil.rmtree(directory)
    with pytest.raises(ValueError, match="Node 22"):
        gate.select_node_bin(env)


@pytest.mark.parametrize("tool", ["java", "node", "psql", "postgres"])
def test_preflight_rejects_missing_tool(gate, runner_tools, monkeypatch, tool):
    env, _, _ = runner_tools
    probe = gate.subprocess.run
    def missing(command, **kwargs):
        if Path(command[0]).name == tool:
            raise FileNotFoundError("missing runtime tool: " + tool)
        return probe(command, **kwargs)
    monkeypatch.setattr(gate.subprocess, "run", missing)
    with pytest.raises((ValueError, OSError), match="missing|runtime"):
        gate.inspect_tools(env)


@pytest.mark.parametrize("tool,field,value", [("java", "java", "21.0.13+11"),
    ("node", "node", "22.24.0"), ("postgres", "postgres", "16.16"),
    ("image", "image_version", "20261019.400.1")])
def test_record_refuses_harness_runtime_claim_drift(gate, control, monkeypatch, tool, field, value):
    result, _, _, root, env = control
    observed = runtime_control()
    result["lifecycle"]["runtime"][field] = value
    monkeypatch.setattr(gate, "inspect_tools", lambda *_: {"tools": result["lifecycle"]["tools"], "runtime": observed})
    monkeypatch.setattr(gate, "run_command", lambda *_: (0, result["pytest"], result["lifecycle"], result["process_receipts"]))
    monkeypatch.setattr(gate, "assert_cleanup", lambda *_: None)
    output = root / "drift-result"
    with pytest.raises(ValueError, match="runtime.*observ|observ.*runtime"):
        gate.record(root, root / "scripts/data/engine-contract-selection.json", output, ["fixture"],
                    env | {"SPECIMEN_TEST_SQL_EMULATOR": "true"})
    assert not (output / "engine-contract.json").exists()


@pytest.mark.parametrize("version", ["15.15", "17.6", "16garbage", ""])
def test_verify_rejects_actual_server_version(gate, control, version):
    reject(gate, control, lambda r: r["lifecycle"].update(postgres_server_version=version), "PostgreSQL server version")


@pytest.mark.parametrize("client", ["initdb", "pg_ctl", "createdb", "psql", "pg_dump", "pg_restore"])
@pytest.mark.parametrize("version", ["15.15", "17.6", "", None])
def test_preflight_checks_every_pg_client(gate, runner_tools, client, version):
    env, runtime, _ = runner_tools
    runtime["postgres_client_versions"][client] = version
    with pytest.raises(ValueError, match="runtime.*version"):
        gate.inspect_tools(env)
