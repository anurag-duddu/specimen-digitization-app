"""Run the entire pytest collection in isolated, complete-file CI shards."""

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


# Whole-module lower bounds from the 25 slowest phases of each Linux shard
# in main CI 37844910372/1 (cb38a8be), 2026-10-08. No runner/network reads.
# A 100 ms/item floor is a coarse estimate for unmeasured work, not a
# timeout or promised runtime. New/expanded modules retain that floor.
DEFAULT_ITEM_COST_MS = 100
MODULE_COST_MS = {
    "scripts/ops/test_simple_owner_setup.py": 30620,
    "tests/research_harness/test_agent_tools_sequential.py": 101540,
    "tests/research_harness/test_agent_visibility.py": 106200,
    "tests/research_harness/test_collection_workflow.py": 44090,
    "tests/research_harness/test_composed_queue_outcomes.py": 90740,
    "tests/research_harness/test_final_progress_carrier.py": 169860,
    "tests/research_harness/test_geography_hierarchy_publication.py": 97490,
    "tests/research_harness/test_native_retry_work_queue.py": 257040,
    "tests/research_harness/test_organiser_handover_composer.py": 193580,
    "tests/research_harness/test_organiser_raw_reading_composer.py": 127610,
    "tests/research_harness/test_parallel_roles.py": 706420,
    "tests/research_harness/test_people_publication.py": 139400,
    "tests/research_harness/test_production_e2e.py": 288250,
    "tests/research_harness/test_production_e2e_sam3_regions.py": 104460,
    "tests/research_harness/test_public_source_retry_api.py": 146760,
    "tests/research_harness/test_published_blocked_workflow.py": 137940,
    "tests/research_harness/test_run_budget_ceiling.py": 286790,
    "tests/research_harness/test_taxonomy_automatic_publication.py": 108660,
    "tests/research_harness/test_temporal_composer.py": 87250,
    "tests/research_harness/test_unkeyed_label_reading_citation.py": 231010,
    "tests/research_harness/test_unkeyed_label_review.py": 416160,
    "tests/test_model_runtime.py": 108540
}


def partition(nodeids, count):
    """Balance observed module costs, keeping fixtures and item order together."""
    if type(count) is not int or count < 1 or len(set(nodeids)) != len(nodeids):
        raise ValueError("invalid shard count or duplicate collected node IDs")
    sizes = Counter(node.split("::", 1)[0] for node in nodeids)
    costs = {module: max(size * DEFAULT_ITEM_COST_MS, MODULE_COST_MS.get(module, 0))
             for module, size in sizes.items()}
    loads = [0] * count
    owners = {}
    for module in sorted(sizes, key=lambda name: (-costs[name], name)):
        index = min(range(count), key=lambda shard: (loads[shard], shard))
        owners[module] = index
        loads[index] += costs[module]
    return [[node for node in nodeids if owners[node.split("::", 1)[0]] == index]
            for index in range(count)]


def identity():
    return {name: os.environ.get(name, "") for name in
            ("GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT")}


class Shard:
    def __init__(self, index, count, output):
        self.index, self.count, self.output = index, count, Path(output)
        self.collected, self.selected, self.reports = [], [], {}
        self.collection_errors = 0

    def pytest_collection_modifyitems(self, session, config, items):
        self.collected = [item.nodeid for item in items]
        self.selected = partition(self.collected, self.count)[self.index]
        selected = set(self.selected)
        kept = [item for item in items if item.nodeid in selected]
        removed = [item for item in items if item.nodeid not in selected]
        items[:] = kept
        config.hook.pytest_deselected(items=removed)
        print(f"\nShard {self.index + 1}/{self.count}: "
              f"{len(kept)} of {len(self.collected)} collected tests")

    def pytest_collectreport(self, report):
        if report.failed:
            self.collection_errors += 1

    def pytest_runtest_logreport(self, report):
        phases = self.reports.setdefault(report.nodeid, {})
        if report.when in phases:
            raise ValueError("duplicate test phase report")
        phases[report.when] = report.outcome

    def pytest_sessionfinish(self, session, exitstatus):
        result = {"schema": 1, "identity": identity(), "index": self.index,
                  "count": self.count, "collected": self.collected,
                  "selected": self.selected, "reports": self.reports,
                  "collection_errors": self.collection_errors,
                  "exitstatus": int(exitstatus)}
        self.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.output.with_suffix(".tmp")
        temporary.write_text(json.dumps(result), encoding="utf-8")
        temporary.replace(self.output)


def verify(results, count, expected_identity):
    """A green aggregate means every collected test completed exactly once."""
    if len(results) != count:
        raise ValueError("missing or extra shard results")
    if {r["index"] for r in results} != set(range(count)):
        raise ValueError("missing or duplicate shard index")
    collected = results[0]["collected"]
    if not collected or not all(isinstance(node, str) for node in collected):
        raise ValueError("empty or malformed complete collection")
    assignments = partition(collected, count)
    observed = []
    for result in results:
        index = result["index"]
        if (type(index) is not int or result["schema"] != 1
                or type(result["count"]) is not int or result["count"] != count
                or result["identity"] != expected_identity
                or result["collected"] != collected
                or type(result["exitstatus"]) is not int or result["exitstatus"] != 0
                or result["collection_errors"] != 0):
            raise ValueError("failed, stale or inconsistent shard result")
        if result["selected"] != assignments[index] or not result["selected"]:
            raise ValueError("incomplete or incorrect shard assignment")
        if set(result["reports"]) != set(result["selected"]):
            raise ValueError("missing or extra executed test")
        for node, phases in result["reports"].items():
            if (set(phases) - {"setup", "call", "teardown"}
                    or phases.get("setup") not in {"passed", "skipped"}
                    or phases.get("teardown") not in {"passed", "skipped"}
                    or (phases["setup"] == "passed"
                        and phases.get("call") not in {"passed", "skipped"})
                    or (phases["setup"] == "skipped" and "call" in phases)):
                raise ValueError("failed or incomplete test phases")
            observed.append(node)
    if Counter(observed) != Counter(collected):
        raise ValueError("full test collection was not executed exactly once")
    return len(observed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("--index", type=int, required=True)
    run.add_argument("--count", type=int, required=True)
    run.add_argument("--output", required=True)
    run.add_argument("--collect-only", action="store_true")
    check = commands.add_parser("verify")
    check.add_argument("--count", type=int, required=True)
    check.add_argument("results", nargs="+")
    local = commands.add_parser("local")
    local.add_argument("--count", type=int, default=6)
    args = parser.parse_args()
    if args.command == "local":
        if not 1 <= args.count <= 6:
            parser.error("local shard count must be between one and six")
        directory = Path(tempfile.mkdtemp(prefix="specimen-python-shards-"))
        processes = []
        paths = []
        print(f"Python shard logs and results: {directory}", flush=True)
        failed = False
        try:
            for index in range(args.count):
                output = directory / f"shard-{index}.json"
                log = directory / f"shard-{index}.log"
                with log.open("w") as stream:
                    process = subprocess.Popen(
                        [sys.executable, str(Path(__file__).resolve()), "run",
                         "--index", str(index), "--count", str(args.count),
                         "--output", str(output)], stdout=stream, stderr=subprocess.STDOUT)
                processes.append(process)
                paths.append(output)
            for index, process in enumerate(processes):
                status = process.wait()
                print(f"Python shard {index + 1}/{args.count}: exit {status}", flush=True)
                failed |= status != 0
                log = directory / f"shard-{index}.log"
                lines = log.read_text().splitlines()
                print("\n".join(lines[-80:] if status else lines[-2:]), flush=True)
        finally:
            # An interrupted local gate must not leave its own test runners.
            for process in processes:
                if process.poll() is None:
                    process.terminate()
            for process in processes:
                if process.poll() is None:
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
        if failed:
            return 1
        args.results = list(map(str, paths))
    if args.command == "run":
        if not 0 <= args.index < args.count:
            parser.error("shard index must be within count")
        # Match the pytest console entry point's import path and argv. Keep
        # ordinary default discovery/prepend behavior, including scripts/.
        sys.path[0] = str(Path(sys.executable).parent)
        sys.argv = [str(Path(sys.executable).parent / "pytest"), "-q", "--durations=25"]
        if args.collect_only:
            sys.argv.append("--collect-only")
        import pytest

        return pytest.main(sys.argv[1:], plugins=[Shard(args.index, args.count, args.output)])
    try:
        results = [json.loads(Path(path).read_text(encoding="utf-8")) for path in args.results]
        total = verify(results, args.count, identity())
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        print(f"Python shard verification failed: {error}", file=sys.stderr)
        return 1
    print(f"All {total} collected Python tests completed exactly once across {args.count} shards.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
