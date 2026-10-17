"""Prove parallel CI retains the complete collection and fails closed."""

from copy import deepcopy
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
from types import SimpleNamespace

import pytest

import python_shards
from python_shards import identity, partition, verify


def raw_results():
    nodes = [f"{directory}/test_{module}.py::test_case[{case}]"
             for directory, module, size in (("tests", "a", 5), ("scripts/ci", "b", 3),
                                             ("scripts/release", "c", 2))
             for case in range(size)]
    return [{"schema": 1, "identity": identity(), "index": index, "count": 3,
             "collected": nodes, "selected": selected, "collection_errors": 0,
             "exitstatus": 0, "reports": {
                 node: {"setup": "passed", "call": "passed", "teardown": "passed"}
                 for node in selected}}
            for index, selected in enumerate(partition(nodes, 3))]


def complete_results():
    return telemetry_results()


def test_partition_keeps_every_module_and_its_order_together():
    results = complete_results()
    assert verify(results, 3, identity()) == 10
    assert [len(r["selected"]) for r in results] == [5, 3, 2]
    for result in results:
        assert len({node.split("::", 1)[0] for node in result["selected"]}) == 1
    assert partition(results[0]["collected"], 3) == [r["selected"] for r in results]


def test_runtime_hints_balance_slow_modules_without_splitting_them():
    nodes = [f"tests/test_{module}.py::test_case[{case}]"
             for module, size in (("a", 5), ("b", 4), ("c", 3))
             for case in range(size)]
    shards = partition(nodes, 2, {"tests/test_b.py": 100})
    assert [[node.split("::", 1)[0] for node in shard] for shard in shards] == [
        ["tests/test_b.py"] * 4,
        ["tests/test_a.py"] * 5 + ["tests/test_c.py"] * 3,
    ]
    assert [node for shard in shards for node in shard] != nodes
    assert sorted(node for shard in shards for node in shard) == sorted(nodes)


def test_committed_runtime_hints_are_valid_test_modules():
    raw = python_shards.decode_json(python_shards.TIMINGS.read_bytes())
    # Every stored hint is validated and kept, whether or not inputs changed.
    timings = python_shards.load_timings()
    assert timings, "committed manifest must contain validated module costs"
    root = Path(__file__).resolve().parents[2]
    assert all((root / module).is_file() for module in timings)
    assert dict(timings) == raw["module_seconds"]
    assert timings.mode == ("lower_bound" if raw["schema"] == 1 else "complete")
    assert timings.manifest_digest == hashlib.sha256(
        python_shards.TIMINGS.read_bytes()).hexdigest()
    if raw["schema"] != 1:
        inventory = raw["module_inventory_digests"]
        if raw["schema"] == 3:
            inventory = python_shards.fingerprints_from_records(inventory)
        assert timings.module_inventory_digests == inventory


@pytest.mark.parametrize("change", ["unchanged", "source", "new_module"])
@pytest.mark.parametrize("schema", [2, 3])
def test_committed_complete_manifest_allows_changed_input_fallback(tmp_path, monkeypatch,
                                                                  change, schema):
    # Synthetic complete costs exercise the I27 integration boundary without
    # changing the committed timing file or claiming new measurements.
    modules = {"tests/test_application.py": (100, 1),
               "scripts/ci/test_python_shards.py": (1, 3),
               "scripts/ci/test_python_scope.py": (1, 2)}
    inventory = {module: [f"{module}::test_case[{i}]" for i in range(size)]
                 for module, (size, _) in modules.items()}
    nodes = [node for module_nodes in inventory.values() for node in module_nodes]
    measured_sources = {module: "a" * 64 for module in modules}
    inventory_digests = {module: python_shards.digest(module_nodes)
                         for module, module_nodes in inventory.items()}
    manifest = {"schema": schema, "mode": "complete",
                "measurement_identity": {"GITHUB_SHA": "a" * 40,
                                         "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "2"},
                "inventory_digest": python_shards.digest(nodes),
                "timing_manifest_digest": "b" * 64,
                "source_fingerprints": measured_sources,
                "module_inventory_digests": inventory_digests,
                "module_seconds": {module: seconds for module, (_, seconds) in modules.items()}}
    if schema == 3:
        for field in ("source_fingerprints", "module_inventory_digests"):
            manifest[field] = [{"path": path, "sha256": sha}
                               for path, sha in sorted(manifest[field].items())]
    path = tmp_path / "complete-timings.json"
    path.write_text(json.dumps(manifest))
    current_sources = dict(measured_sources)
    added = {}
    if change == "source":
        current_sources["tests/test_application.py"] = "c" * 64
    elif change == "new_module":
        new_module = "scripts/ci/test_refresh_python_shard_timings.py"
        current_sources[new_module] = "c" * 64
        nodes += [f"{new_module}::test_new"]
        added = {new_module: 0.1}
    load = python_shards.load_timings
    monkeypatch.setattr(python_shards, "TIMINGS", path)
    monkeypatch.setattr(python_shards, "source_fingerprints", lambda: current_sources)
    monkeypatch.setattr(python_shards, "load_timings", lambda: load(path))
    # The real committed-manifest contract must pass both immediately after
    # calibration and after ordinary source changes, including new modules.
    test_committed_runtime_hints_are_valid_test_modules()
    hints = python_shards.load_timings()
    # Changed sources keep every measured cost and exact weight; only a new
    # module, whose inventory was never measured, gets the item prior.
    assert dict(hints) == manifest["module_seconds"]
    assert hints.mode == "complete"
    assert hints.module_inventory_digests == inventory_digests
    assert python_shards.module_weights(nodes, hints) == {**manifest["module_seconds"], **added}
    assert partition(nodes, 2, hints) != partition(nodes, 2, {})
    shards = partition(nodes, 2, hints)
    assert Counter(node for shard in shards for node in shard) == Counter(nodes)
    for module in {node.split("::", 1)[0] for node in nodes}:
        module_nodes = [node for node in nodes if node.split("::", 1)[0] == module]
        owners = [shard for shard in shards if module_nodes[0] in shard]
        assert len(owners) == 1
        assert [node for node in owners[0] if node in set(module_nodes)] == module_nodes


@pytest.mark.parametrize("value", [
    {}, {"schema": 2, "module_seconds": {}},
    {"schema": 1, "module_seconds": []},
    {"schema": 1, "module_seconds": {"../test.py": 1}},
    {"schema": 1, "module_seconds": {"test.py": 0}},
    {"schema": 1, "module_seconds": {"test.py": True}},
])
def test_invalid_runtime_hints_fail_closed(tmp_path, value):
    path = tmp_path / "timings.json"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="invalid Python shard timings"):
        python_shards.load_timings(path)


@pytest.mark.parametrize("change", [
    lambda r: r.pop(),
    lambda r: r.append(deepcopy(r[0])),
    lambda r: r[1].update(index=0),
    lambda r: r[0].update(index=True),
    lambda r: r[0].update(count=2),
    lambda r: r[0].update(exitstatus=1),
    lambda r: r[0].update(exitstatus=5),
    lambda r: r[0].update(collection_errors=1),
    lambda r: r[0].update(identity={**identity(), "GITHUB_SHA": "wrong"}),
    lambda r: r[0].update(identity={**identity(), "GITHUB_RUN_ID": "wrong"}),
    lambda r: r[0].update(identity={**identity(), "GITHUB_RUN_ATTEMPT": "wrong"}),
    lambda r: r[1].update(collected=r[1]["collected"][:-1]),
    lambda r: r[0].update(selected=r[0]["selected"][:-1]),
    lambda r: r[0]["reports"].pop(r[0]["selected"][0]),
    lambda r: r[0]["reports"].update({"extra": {"setup": "passed"}}),
    lambda r: r[0]["reports"][r[0]["selected"][0]].pop("teardown"),
    lambda r: r[0]["reports"][r[0]["selected"][0]].pop("call"),
    lambda r: r[0]["reports"][r[0]["selected"][0]].update(setup="failed"),
    lambda r: r[0]["reports"][r[0]["selected"][0]].update(call="failed"),
    lambda r: r[0]["reports"][r[0]["selected"][0]].update(teardown="failed"),
])
def test_aggregate_refuses_missing_failed_stale_or_incomplete_results(change):
    results = complete_results()
    change(results)
    with pytest.raises((ValueError, KeyError, TypeError, IndexError)):
        verify(results, 3, identity())


def test_skip_and_xfail_retain_pytest_semantics():
    results = complete_results()
    reports = results[0]["reports"]
    reports[results[0]["selected"][0]] = {"setup": "skipped", "teardown": "passed"}
    reports[results[0]["selected"][1]]["call"] = "skipped"
    reports[results[0]["selected"][2]]["teardown"] = "skipped"
    results[0]["durations"][results[0]["selected"][0]].pop("call")
    assert verify(results, 3, identity()) == 10


def test_duplicate_collection_is_refused():
    with pytest.raises(ValueError, match="duplicate"):
        partition(["test_a.py::test_one", "test_a.py::test_one"], 3)


def invoke(directory, *args):
    script = Path(__file__).with_name("python_shards.py")
    return subprocess.run([sys.executable, str(script), *args], cwd=directory,
                          capture_output=True, text=True)


def test_real_pytest_discovery_phases_fixtures_and_cli_aggregate(tmp_path):
    for directory in ("tests", "scripts/ci", "scripts/release"):
        root = tmp_path / directory
        root.mkdir(parents=True)
        name = directory.replace("/", "_")
        (root / f"test_{name}.py").write_text(
            "import pytest\nfrom pathlib import Path\n"
            "@pytest.fixture(scope='module', autouse=True)\n"
            "def once():\n"
            f"    path = Path.cwd() / '{name}-fixture.txt'\n"
            "    assert not path.exists()\n"
            "    path.write_text('once')\n"
            "@pytest.mark.parametrize('value', [1, 2])\n"
            "def test_pass(value):\n    assert value > 0\n"
            "@pytest.mark.skip(reason='original skip')\n"
            "def test_skip():\n    assert False\n"
            "@pytest.mark.xfail(reason='original xfail', strict=True)\n"
            "def test_xfail():\n    assert False\n"
        )
    paths = []
    for index in range(3):
        output = tmp_path / f"shard-{index}.json"
        result = invoke(tmp_path, "run", "--index", str(index), "--count", "3",
                        "--output", str(output))
        assert result.returncode == 0, result.stdout + result.stderr
        paths.append(output)
    results = [json.loads(path.read_text()) for path in paths]
    assert verify(results, 3, identity(), python_shards.load_timings()) == 12
    assert {node.split("/", 1)[0] for node in results[0]["collected"]} == {"tests", "scripts"}
    result = invoke(tmp_path, "verify", "--count", "3", *map(str, paths))
    assert result.returncode == 0, result.stderr
    assert "12 collected Python tests completed exactly once" in result.stdout
    paths[0].write_text("{}")
    assert invoke(tmp_path, "verify", "--count", "3", *map(str, paths)).returncode == 1


@pytest.mark.parametrize("color", ["no", "yes"], ids=["plain", "color"])
def test_local_parallel_command_runs_all_modules_and_propagates_failure(tmp_path, monkeypatch, color):
    # Child pytest processes inherit these options; exercise both display modes.
    monkeypatch.setenv("PYTEST_ADDOPTS", f"{os.environ.get('PYTEST_ADDOPTS', '')} --color={color}")
    sgr = re.compile(r"\x1b\[[0-9;]*m")
    for index in range(3):
        (tmp_path / f"test_{index}.py").write_text(
            "import pytest\n@pytest.mark.parametrize('value', [1, 2])\n"
            "def test_pass(value):\n    assert value > 0\n")
    result = invoke(tmp_path, "local", "--count", "3")
    assert result.returncode == 0, result.stdout + result.stderr
    assert bool(sgr.search(result.stdout)) == (color == "yes")
    assert "6 collected Python tests completed exactly once" in result.stdout
    (tmp_path / "test_1.py").write_text("def test_fail():\n    assert False\n")
    result = invoke(tmp_path, "local", "--count", "3")
    assert result.returncode == 1
    assert bool(sgr.search(result.stdout)) == (color == "yes")
    assert "FAILED test_1.py::test_fail" in sgr.sub("", result.stdout)


@pytest.mark.parametrize("count", ["0", "-1", "7"])
def test_local_invalid_count_does_not_start_workers(tmp_path, count):
    result = invoke(tmp_path, "local", "--count", count)
    assert result.returncode == 2
    assert "Python shard logs" not in result.stdout


def test_failed_second_worker_start_cleans_first_worker(tmp_path, monkeypatch):
    class Child:
        terminated = False
        reaped = False

        def poll(self):
            return 0 if self.reaped else None

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            self.reaped = True
            return 0

    child = Child()
    calls = []

    def start(*args, **kwargs):
        calls.append(args)
        if len(calls) == 2:
            raise OSError("synthetic second launch failure")
        return child

    monkeypatch.setattr(python_shards.tempfile, "mkdtemp", lambda **kwargs: str(tmp_path))
    monkeypatch.setattr(python_shards.subprocess, "Popen", start)
    monkeypatch.setattr(sys, "argv", ["python_shards.py", "local", "--count", "3"])
    with pytest.raises(OSError, match="second launch"):
        python_shards.main()
    assert child.terminated and child.reaped


# Schema-2 fixtures deliberately use literal telemetry; production validators
# must check it independently rather than trusting a second generator.
def telemetry_results(count=3):
    results = raw_results()
    nodes = results[0]["collected"]
    if count != 3:
        nodes = [f"tests/test_{i}.py::test_case[{j}]"
                 for i in range(24) for j in range(2)]
        results = [{**deepcopy(results[0]), "index": i, "count": count,
                    "collected": nodes, "selected": selected,
                    "reports": {node: {"setup": "passed", "call": "passed",
                                       "teardown": "passed"} for node in selected}}
                   for i, selected in enumerate(partition(nodes, count))]
    import hashlib
    digest = hashlib.sha256(json.dumps(nodes, separators=(",", ":")).encode()).hexdigest()
    manifest_digest = hashlib.sha256(json.dumps(
        {"mode": "lower_bound", "module_seconds": {}}, sort_keys=True,
        separators=(",", ":")).encode()).hexdigest()
    for result in results:
        result.update(schema=2, inventory_digest=digest,
                      timing_manifest_digest=manifest_digest,
                      timing_mode="lower_bound", source_fingerprints={"test.py": "a" * 64},
                      durations={node: {phase: 0.25 for phase in phases}
                                 for node, phases in result["reports"].items()},
                      telemetry={"collection_seconds": 0.1, "execution_seconds": 1.0})
    return results


def test_aggregate_rejects_manifest_mismatch_even_if_partition_unchanged():
    results = telemetry_results()
    assert verify(results, 3, identity()) == 10
    results[1]["timing_manifest_digest"] = "b" * 64
    with pytest.raises(ValueError, match="manifest"):
        verify(results, 3, identity())


@pytest.mark.parametrize("count", [6, 8, 10, 12])
def test_duration_telemetry_cannot_change_coverage(count):
    results = telemetry_results(count)
    nodes = results[0]["collected"]
    assert verify(results, count, identity()) == len(nodes)
    for result in results:
        for phases in result["durations"].values():
            for phase in phases:
                phases[phase] = 1000000.0
    assert verify(results, count, identity()) == len(nodes)
    results[0]["reports"].pop(results[0]["selected"][0])
    with pytest.raises(ValueError):
        verify(results, count, identity())


def test_complete_duration_replaces_item_prior():
    nodes = [f"test_{module}.py::test_case[{i}]"
             for module, size in (("a", 100), ("b", 1), ("c", 1), ("new", 1))
             for i in range(size)]
    hints = python_shards.TimingHints({"test_a.py": 1, "test_b.py": 3,
                                      "test_c.py": 2}, mode="complete")
    shards = partition(nodes, 2, hints)
    assert shards[0] == ["test_b.py::test_case[0]", "test_new.py::test_case[0]"]
    assert shards[1] == nodes[:100] + ["test_c.py::test_case[0]"]
    assert sorted(node for shard in shards for node in shard) == sorted(nodes)
    assert partition(nodes, 2, dict(hints))[0] == nodes[:100]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, True, "1"])
def test_invalid_phase_durations_are_refused(value):
    results = telemetry_results()
    node = results[0]["selected"][0]
    results[0]["durations"][node]["call"] = value
    with pytest.raises(ValueError, match="duration"):
        verify(results, 3, identity())


@pytest.mark.parametrize("field", ["inventory_digest", "source_fingerprints", "timing_mode"])
def test_telemetry_provenance_mismatch_is_refused(field):
    results = telemetry_results()
    results[1][field] = None
    with pytest.raises(ValueError):
        verify(results, 3, identity())


def test_duplicate_phase_is_refused(tmp_path):
    shard = python_shards.Shard(0, 1, tmp_path / "result.json")
    report = SimpleNamespace(nodeid="test_a.py::test_one", when="call",
                             outcome="passed", duration=0.1)
    shard.pytest_runtest_logreport(report)
    with pytest.raises(ValueError, match="duplicate"):
        shard.pytest_runtest_logreport(report)


@pytest.mark.parametrize("interrupt_at", [1, 2, "wait"])
def test_runner_cleanup_escalates_and_reaps_on_interrupt(tmp_path, monkeypatch, interrupt_at):
    # Real children, with readiness supplied through stdout rather than a sleep.
    # Each TERM-resistant runner reaps its cooperative descendant on group TERM.
    original_popen = subprocess.Popen
    children, descendants, timed_out, killed = [], [], [], []
    code = (
        "import os, signal, subprocess, sys\n"
        "child = subprocess.Popen([sys.executable, '-c', "
        "'import os,signal; "
        "print(os.getpid(),flush=True); signal.pause()'], stdout=subprocess.PIPE, text=True)\n"
        "pid = child.stdout.readline().strip()\n"
        "def stop(sig, frame):\n"
        "    child.wait()\n"
        "    return\n"
        "signal.signal(signal.SIGTERM, stop)\n"
        "print(pid, flush=True)\n"
        "while True: signal.pause()\n"
    )
    competitor = original_popen([sys.executable, "-c", "import signal; signal.pause()"])

    class Owned:
        def __init__(self, process):
            self.process, self.pid = process, process.pid

        def poll(self):
            return self.process.poll()

        def terminate(self):
            self.process.terminate()

        def kill(self):
            killed.append(self.pid)
            self.process.kill()

        def wait(self, timeout=None):
            if timeout is None and interrupt_at == "wait" and not timed_out:
                raise KeyboardInterrupt("synthetic active interruption")
            try:
                return self.process.wait(timeout=0.05 if timeout is not None else 1)
            except subprocess.TimeoutExpired:
                timed_out.append(self.pid)
                raise

    def start(*args, **kwargs):
        if interrupt_at != "wait" and len(children) == interrupt_at:
            raise KeyboardInterrupt("synthetic launch interruption")
        assert kwargs.get("start_new_session") is True, "workers must own isolated groups"
        child = original_popen([sys.executable, "-c", code], start_new_session=True,
                               stdout=subprocess.PIPE, text=True)
        children.append(Owned(child))
        descendants.append(int(child.stdout.readline()))
        return children[-1]

    monkeypatch.setattr(python_shards.tempfile, "mkdtemp", lambda **kwargs: str(tmp_path))
    monkeypatch.setattr(python_shards.subprocess, "Popen", start)
    monkeypatch.setattr(sys, "argv", ["python_shards.py", "local", "--count", "3"])
    try:
        error = None
        try:
            python_shards.main()
        except BaseException as caught:
            error = caught
        assert timed_out, "real TERM-resistant child must reach TimeoutExpired"
        assert all(child.poll() is not None for child in children), "owned runner PID was not reaped"
        assert killed, "TimeoutExpired must escalate through process.kill"
        assert isinstance(error, KeyboardInterrupt), "cleanup must preserve the original interrupt"
        for pid in descendants:
            with pytest.raises(ProcessLookupError):
                os.kill(pid, 0)
        assert competitor.poll() is None, "cleanup terminated an unrelated process"
    finally:
        for child in children:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGKILL)
            child.process.wait(timeout=2)
        for pid in descendants:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        competitor.kill()
        competitor.wait(timeout=2)


@pytest.mark.parametrize("count", [6, 8, 10, 12])
def test_single_hosted_count_generates_matrix_and_both_arguments(tmp_path, count):
    result = invoke(tmp_path, "config", "--count", str(count))
    assert result.returncode == 0, result.stderr
    config = json.loads(result.stdout)
    assert config["matrix"] == {"index": list(range(count))}
    assert config["run_args"] == config["verify_args"] == ["--count", str(count)]


def test_local_default_stays_six(tmp_path, monkeypatch):
    calls = []

    def start(command, **kwargs):
        calls.append(command)
        raise OSError("stop before launching synthetic workers")

    monkeypatch.setattr(python_shards.tempfile, "mkdtemp", lambda **kwargs: str(tmp_path))
    monkeypatch.setattr(python_shards.subprocess, "Popen", start)
    monkeypatch.setattr(sys, "argv", ["python_shards.py", "local"])
    with pytest.raises(OSError, match="stop before"):
        python_shards.main()
    assert calls[0][calls[0].index("--count") + 1] == "6"


@pytest.mark.parametrize("fault", ["old_schema", "bool_schema", "bool_collection_errors",
                                  "wrong_inventory", "reordered_selected", "reordered_reports",
                                  "missing_duration_node", "extra_duration_node",
                                  "missing_duration_phase", "extra_duration_phase",
                                  "bad_telemetry", "nonfinite_telemetry", "bad_sources"])
def test_malformed_schema_bound_telemetry_fails_closed(fault):
    results = telemetry_results()
    result = results[0]
    node = result["selected"][0]
    if fault == "old_schema":
        result["schema"] = 1
    elif fault == "bool_schema":
        result["schema"] = True
    elif fault == "bool_collection_errors":
        result["collection_errors"] = False
    elif fault == "wrong_inventory":
        result["inventory_digest"] = "c" * 64
    elif fault == "reordered_selected":
        result["selected"].reverse()
    elif fault == "reordered_reports":
        result["reports"] = dict(reversed(list(result["reports"].items())))
    elif fault == "missing_duration_node":
        result["durations"].pop(node)
    elif fault == "extra_duration_node":
        result["durations"]["extra"] = {"setup": 1.0}
    elif fault == "missing_duration_phase":
        result["durations"][node].pop("teardown")
    elif fault == "extra_duration_phase":
        result["durations"][node]["unknown"] = 0.0
    elif fault == "bad_telemetry":
        result["telemetry"].pop("execution_seconds")
    elif fault == "nonfinite_telemetry":
        result["telemetry"]["collection_seconds"] = float("inf")
    elif fault == "bad_sources":
        for item in results:
            item["source_fingerprints"] = {"../secret": "a" * 64}
    with pytest.raises(ValueError):
        verify(results, 3, identity())


def test_same_wrong_manifest_in_every_leaf_is_refused():
    results = telemetry_results()
    for result in results:
        result["timing_manifest_digest"] = "c" * 64
    with pytest.raises(ValueError, match="manifest"):
        verify(results, 3, identity())


def test_unknown_and_changed_module_inventory_retain_item_fallback():
    nodes = [f"test_{module}.py::test_case[{i}]" for module in ("a", "b", "new")
             for i in range(3)]
    hints = python_shards.TimingHints(
        {"test_a.py": 100, "test_b.py": 7}, mode="complete",
        module_inventory_digests={"test_a.py": "c" * 64,
                                  "test_b.py": python_shards.digest(nodes[3:6])})
    # A changed inventory keeps its measured seconds plus the item prior; only
    # an unchanged inventory makes a complete cost exact.
    assert python_shards.module_weights(nodes, hints) == pytest.approx(
        {"test_a.py": 100.3, "test_b.py": 7, "test_new.py": 0.3})
    assert sorted(node for shard in partition(nodes, 2, hints) for node in shard) == sorted(nodes)


def module_owners(shards):
    return {node.split("::", 1)[0]: index for index, shard in enumerate(shards) for node in shard}


def test_unrelated_source_change_keeps_measured_costs_and_spreads_heavy_modules(tmp_path):
    # After PR #343, one changed source file discarded every measured cost.
    # Few-node end-to-end modules then weighed 0.2 and shared one shard.
    heavy = ["tests/research_harness/test_heavy_a.py", "tests/research_harness/test_heavy_b.py"]
    wide = [f"tests/test_wide_{name}.py" for name in "abc"]
    inventory = {**{module: [f"{module}::test_flow[{i}]" for i in range(2)] for module in heavy},
                 **{module: [f"{module}::test_case[{i}]" for i in range(5)] for module in wide}}
    nodes = [node for module_nodes in inventory.values() for node in module_nodes]
    seconds = {**dict.fromkeys(heavy, 100.0), **dict.fromkeys(wide, 50.0)}
    measured_sources = python_shards.source_fingerprints()
    measured_sources["scripts/ci/python_scope.py"] = "0" * 64
    assert measured_sources != python_shards.source_fingerprints()
    manifest = {"schema": 3, "mode": "complete",
                "measurement_identity": {"GITHUB_SHA": "a" * 40,
                                         "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1"},
                "inventory_digest": python_shards.digest(nodes),
                "timing_manifest_digest": "b" * 64,
                "source_fingerprints": python_shards.fingerprint_records(measured_sources),
                "module_inventory_digests": python_shards.fingerprint_records(
                    {module: python_shards.digest(module_nodes)
                     for module, module_nodes in inventory.items()}),
                "module_seconds": seconds}
    path = tmp_path / "timings.json"
    path.write_text(json.dumps(manifest))
    hints = python_shards.load_timings(path)
    assert dict(hints) == seconds, "an unrelated source change must keep measured costs"
    shards = partition(nodes, 2, hints)
    owners = module_owners(shards)
    assert owners[heavy[0]] != owners[heavy[1]], "heavy modules must not share a shard"
    assert sorted(node for shard in shards for node in shard) == sorted(nodes)


def test_heavy_module_that_gains_a_test_keeps_its_measured_seconds():
    heavy = ["tests/research_harness/test_heavy_a.py", "tests/research_harness/test_heavy_b.py"]
    narrow = [f"tests/test_narrow_{name}.py" for name in "abcd"]
    measured = {**{module: [f"{module}::test_flow[{i}]" for i in range(2)] for module in heavy},
                **{module: [f"{module}::test_case"] for module in narrow}}
    collected = {**measured, heavy[0]: measured[heavy[0]] + [f"{heavy[0]}::test_added"]}
    nodes = [node for module_nodes in collected.values() for node in module_nodes]
    hints = python_shards.TimingHints(
        {**dict.fromkeys(heavy, 100.0), **dict.fromkeys(narrow, 25.0)}, mode="complete",
        module_inventory_digests={module: python_shards.digest(module_nodes)
                                  for module, module_nodes in measured.items()})
    shards = partition(nodes, 2, hints)
    owners = module_owners(shards)
    assert owners[heavy[0]] != owners[heavy[1]], "heavy modules must not share a shard"
    assert sorted(node for shard in shards for node in shard) == sorted(nodes)


def test_zero_complete_costs_keep_modules_distributed_and_every_node():
    nodes = [f"test_{i}.py::test_case" for i in range(12)]
    hints = python_shards.TimingHints({node.split("::")[0]: 0 for node in nodes}, mode="complete")
    shards = partition(nodes, 6, hints)
    assert all(shards), "zero complete measurements must not strand empty shards"
    assert sorted(node for shard in shards for node in shard) == sorted(nodes)


def test_fingerprint_inputs_exclude_manifest_but_track_source_and_assets(tmp_path):
    (tmp_path / "scripts/ci").mkdir(parents=True)
    (tmp_path / "tests/fixtures").mkdir(parents=True)
    source = tmp_path / "scripts/ci/helper.py"
    source.write_text("value = 1\n")
    manifest = tmp_path / "scripts/ci/python_shard_timings.json"
    manifest.write_text("{}")
    asset = tmp_path / "tests/fixtures/input.json"
    asset.write_text("{}")
    before = python_shards.source_fingerprints(tmp_path)
    manifest.write_text('{"different": true}')
    assert python_shards.source_fingerprints(tmp_path) == before
    source.write_text("value = 2\n")
    assert python_shards.source_fingerprints(tmp_path) != before
    source.write_text("value = 1\n")
    asset.write_text('{"changed": true}')
    assert python_shards.source_fingerprints(tmp_path) != before


def test_serialized_duplicate_phase_cannot_hide_a_failure():
    with pytest.raises(ValueError, match="duplicate JSON field: call"):
        python_shards.decode_json('{"reports":{"test.py::one": '
                                  '{"setup":"passed","call":"failed",'
                                  '"call":"passed","teardown":"passed"}}}')


def test_phase_order_is_verified_independently_of_node_order():
    results = telemetry_results()
    node = results[0]["selected"][0]
    results[0]["reports"][node] = {"call": "passed", "setup": "passed", "teardown": "passed"}
    with pytest.raises(ValueError, match="phase order"):
        verify(results, 3, identity())


def test_source_input_changes_during_discovery_prevent_result(tmp_path, monkeypatch):
    source = tmp_path / "test_source.py"
    source.write_text("VALUE = 1\n")
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "result.json"
    shard = python_shards.Shard(0, 1, output)
    source.write_text("VALUE = 2\n")
    with pytest.raises(ValueError, match="source/input changed"):
        shard.pytest_sessionfinish(None, 0)
    assert not output.exists(), "changed discovery input cannot produce a reusable result"
