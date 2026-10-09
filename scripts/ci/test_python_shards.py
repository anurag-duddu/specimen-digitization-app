"""Prove parallel CI retains the complete collection and fails closed."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

import python_shards
from python_shards import identity, partition, verify


def complete_results():
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


def test_partition_keeps_every_module_and_its_order_together():
    results = complete_results()
    assert verify(results, 3, identity()) == 10
    assert [len(r["selected"]) for r in results] == [5, 3, 2]
    for result in results:
        assert len({node.split("::", 1)[0] for node in result["selected"]}) == 1
    assert partition(results[0]["collected"], 3) == [r["selected"] for r in results]


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
    assert verify(results, 3, identity()) == 12
    assert {node.split("/", 1)[0] for node in results[0]["collected"]} == {"tests", "scripts"}
    result = invoke(tmp_path, "verify", "--count", "3", *map(str, paths))
    assert result.returncode == 0, result.stderr
    assert "12 collected Python tests completed exactly once" in result.stdout
    paths[0].write_text("{}")
    assert invoke(tmp_path, "verify", "--count", "3", *map(str, paths)).returncode == 1


def test_local_parallel_command_runs_all_modules_and_propagates_failure(tmp_path):
    for index in range(3):
        (tmp_path / f"test_{index}.py").write_text(
            "import pytest\n@pytest.mark.parametrize('value', [1, 2])\n"
            "def test_pass(value):\n    assert value > 0\n")
    result = invoke(tmp_path, "local", "--count", "3")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "6 collected Python tests completed exactly once" in result.stdout
    (tmp_path / "test_1.py").write_text("def test_fail():\n    assert False\n")
    result = invoke(tmp_path, "local", "--count", "3")
    assert result.returncode == 1
    assert "FAILED test_1.py::test_fail" in result.stdout


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


def test_measured_cost_balancing_spreads_slow_small_modules(monkeypatch):
    nodes = [f"test_{module}.py::test_case[{case}]"
             for module in "abcdef" for case in range(10)]
    monkeypatch.setattr(python_shards, "MODULE_COST_MS", {})
    old = partition(nodes, 3)
    costs = {"test_a.py": 10000, "test_d.py": 10000}
    monkeypatch.setattr(python_shards, "MODULE_COST_MS", costs)
    balanced = partition(nodes, 3)

    def load(shard):
        modules = {node.split("::", 1)[0] for node in shard}
        return sum(costs.get(module, 1000) for module in modules)

    assert max(map(load, balanced)) < max(map(load, old))
    assert sorted(node for shard in balanced for node in shard) == sorted(nodes)
    for module in "abcdef":
        expected = [node for node in nodes if node.startswith(f"test_{module}.py::")]
        owners = [shard for shard in balanced if expected[0] in shard]
        assert len(owners) == 1
        assert [node for node in owners[0] if node in expected] == expected
    assert partition(nodes, 3) == balanced


def test_weighted_aggregate_still_refuses_wrong_whole_module_owner(monkeypatch):
    monkeypatch.setattr(python_shards, "MODULE_COST_MS", {"tests/test_a.py": 10000})
    results = complete_results()
    assert verify(results, 3, identity()) == 10
    # Coverage and all phases still look complete; ownership is nevertheless wrong.
    results[0]["selected"], results[1]["selected"] = results[1]["selected"], results[0]["selected"]
    results[0]["reports"], results[1]["reports"] = results[1]["reports"], results[0]["reports"]
    with pytest.raises(ValueError, match="assignment"):
        verify(results, 3, identity())
