"""Run the entire pytest collection in isolated, complete-file CI shards."""

import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time


TIMINGS = Path(__file__).with_name("python_shard_timings.json")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def decode_json(contents):
    """Reject duplicate fields before JSON objects can hide repeated phases."""
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON field: {key}")
            result[key] = value
        return result
    return json.loads(contents, object_pairs_hook=unique)


def valid_digest(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def valid_path(value):
    return (isinstance(value, str) and bool(value) and not Path(value).is_absolute()
            and ".." not in Path(value).parts)


def valid_record_path(value):
    """Schema-3 paths are canonical relative POSIX names, with no aliases."""
    return (isinstance(value, str) and bool(value) and "\\" not in value
            and ":" not in value
            and all(part not in {"", ".", ".."} for part in value.split("/"))
            and not any(ord(character) < 32 or ord(character) == 127 for character in value))


def fingerprints_from_records(records):
    """Read explicit path/SHA-256 records without silently replacing duplicates."""
    if type(records) is not list:
        raise ValueError("fingerprints must be path/sha256 records")
    result = {}
    for record in records:
        if (type(record) is not dict or set(record) != {"path", "sha256"}
                or not valid_record_path(record["path"]) or not valid_digest(record["sha256"])):
            raise ValueError("invalid path/sha256 record")
        if record["path"] in result:
            raise ValueError("duplicate fingerprint path")
        result[record["path"]] = record["sha256"]
    return result


def fingerprint_records(fingerprints):
    """Serialize digest metadata as deterministic, explicitly typed records."""
    if type(fingerprints) is not dict:
        raise ValueError("fingerprints must be a mapping")
    records = [{"path": path, "sha256": sha} for path, sha in fingerprints.items()]
    fingerprints_from_records(records)
    return sorted(records, key=lambda record: record["path"])


def finite_seconds(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def validate_fingerprints(value):
    if (type(value) is not dict or not value
            or any(not valid_path(path) or not valid_digest(sha)
                   for path, sha in value.items())):
        raise ValueError("invalid source/input fingerprints")


def validate_measurement_identity(value):
    if (type(value) is not dict
            or set(value) != {"GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"}
            or not isinstance(value.get("GITHUB_SHA"), str)
            or not re.fullmatch(r"[0-9a-f]{40}", value["GITHUB_SHA"])
            or any(not isinstance(value[key], str)
                   or not re.fullmatch(r"[1-9][0-9]*", value[key])
                   for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"))):
        raise ValueError("unbound measurement identity")


def source_fingerprints(root=None):
    """Fingerprint Python sources and test assets plus locked/configured inputs.

    The timing manifest itself is excluded: its SHA is bound separately, and
    including it here would make a refreshed manifest invalidate itself.
    """
    root = Path.cwd() if root is None else Path(root)
    paths = set()
    for directory in ("src", "scripts", "tests"):
        for path in (root / directory).rglob("*"):
            relative = path.relative_to(root)
            if (path.is_file() and "__pycache__" not in relative.parts
                    and not any(part.startswith(".") for part in relative.parts)
                    and path.name != TIMINGS.name
                    and path.suffix not in {".pyc", ".pyo"}):
                paths.add(path)
    paths.update(root.glob("*.py"))
    for name in ("pyproject.toml", "uv.lock", "pytest.ini", "setup.cfg", "tox.ini"):
        path = root / name
        if path.is_file():
            paths.add(path)
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(paths)}


class TimingHints(dict):
    """Keep legacy lower bounds distinct from complete phase measurements."""
    def __init__(self, values=(), *, mode="lower_bound", manifest_digest=None,
                 module_inventory_digests=None):
        super().__init__(values)
        if mode not in {"lower_bound", "complete"}:
            raise ValueError("invalid timing mode")
        self.mode = mode
        self.manifest_digest = manifest_digest or digest(
            {"mode": mode, "module_seconds": dict(self)})
        self.module_inventory_digests = module_inventory_digests


def timing_hints(value):
    return value if isinstance(value, TimingHints) else TimingHints(value or {})


def load_timings(path=TIMINGS, *, fingerprints=None):
    """Load schema-1 lower bounds or schema-2/3 complete measured module costs.

    Measurement SHA identifies the original run, not the future commit carrying
    this file. Changed sources/inputs conservatively invalidate complete costs.
    Schema 3 makes paths and SHA-256 values explicit record fields; schemas 1
    and 2 retain their original mapping representation and validation.
    """
    try:
        contents = Path(path).read_bytes()
        raw = decode_json(contents)
        if (type(raw.get("schema")) is not int or raw["schema"] not in (1, 2, 3)
                or type(raw.get("module_seconds")) is not dict):
            raise ValueError("unsupported timing schema")
        records = raw["schema"] == 3
        if records and set(raw) != {"schema", "mode", "measurement_identity", "inventory_digest",
                                    "timing_manifest_digest", "source_fingerprints",
                                    "module_inventory_digests", "module_seconds"}:
            raise ValueError("invalid schema-3 timing fields")
        timings = raw["module_seconds"]
        complete = raw["schema"] in (2, 3)
        for module, seconds in timings.items():
            if (not (valid_record_path(module) if records else valid_path(module))
                    or not module.endswith(".py")
                    or not finite_seconds(seconds) or (not complete and seconds == 0)):
                raise ValueError("invalid module timing")
        inventory = None
        if complete:
            if raw["mode"] != "complete" or not valid_digest(raw["inventory_digest"]):
                raise ValueError("invalid complete timing provenance")
            validate_measurement_identity(raw["measurement_identity"])
            sources = (fingerprints_from_records(raw["source_fingerprints"]) if records
                       else raw["source_fingerprints"])
            validate_fingerprints(sources)
            if not valid_digest(raw["timing_manifest_digest"]):
                raise ValueError("invalid input timing manifest digest")
            inventory = (fingerprints_from_records(raw["module_inventory_digests"]) if records
                         else raw["module_inventory_digests"])
            if (type(inventory) is not dict or set(inventory) != set(timings)
                    or any(not valid_digest(sha) for sha in inventory.values())):
                raise ValueError("invalid module inventory digests")
            current = source_fingerprints() if fingerprints is None else fingerprints
            if current != sources:
                timings = {}
                inventory = {}
        return TimingHints(timings, mode="complete" if complete else "lower_bound",
                           manifest_digest=hashlib.sha256(contents).hexdigest(),
                           module_inventory_digests=inventory)
    except (OSError, ValueError, KeyError, AttributeError, TypeError) as error:
        raise ValueError(f"invalid Python shard timings: {error}") from error


def partition(nodeids, count, timings=None):
    """Keep modules together while balancing measured time plus collection size."""
    if type(count) is not int or count < 1 or len(set(nodeids)) != len(nodeids):
        raise ValueError("invalid shard count or duplicate collected node IDs")
    module_nodes = {}
    for node in nodeids:
        module_nodes.setdefault(node.split("::", 1)[0], []).append(node)
    sizes = {module: len(nodes) for module, nodes in module_nodes.items()}
    timings = timing_hints(timings)
    loads = [0.0] * count
    owners = {}
    # Unknown/new/changed modules always keep every item and its prior cost.
    # Complete measurements replace that prior; legacy lower bounds add to it.
    weights = {}
    for module in sizes:
        prior = sizes[module] / 10
        measured = module in timings
        if timings.module_inventory_digests is not None:
            measured &= timings.module_inventory_digests.get(module) == digest(module_nodes[module])
        seconds = timings[module] if measured else 0
        weights[module] = (seconds if measured and timings.mode == "complete"
                           else prior + seconds)
    assigned = [0] * count
    for module in sorted(sizes, key=lambda name: (-weights[name], name)):
        index = min(range(count), key=lambda shard: (
            loads[shard], assigned[shard] if weights[module] == 0 else 0, shard))
        owners[module] = index
        loads[index] += weights[module]
        assigned[index] += 1
    return [[node for node in nodeids if owners[node.split("::", 1)[0]] == index]
            for index in range(count)]


def identity():
    return {name: os.environ.get(name, "") for name in
            ("GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT")}


class Shard:
    def __init__(self, index, count, output, timings=None):
        self.index, self.count, self.output = index, count, Path(output)
        self.timings = timing_hints(timings)
        self.started = time.monotonic()
        self.collection_finished = None
        self.fingerprints = source_fingerprints()
        self.durations = {}
        self.collected, self.selected, self.reports = [], [], {}
        self.collection_errors = 0

    def pytest_collection_modifyitems(self, session, config, items):
        self.collected = [item.nodeid for item in items]
        self.selected = partition(self.collected, self.count, self.timings)[self.index]
        selected = set(self.selected)
        kept = [item for item in items if item.nodeid in selected]
        removed = [item for item in items if item.nodeid not in selected]
        items[:] = kept
        config.hook.pytest_deselected(items=removed)
        self.collection_finished = time.monotonic()
        print(f"\nShard {self.index + 1}/{self.count}: "
              f"{len(kept)} of {len(self.collected)} collected tests")

    def pytest_collectreport(self, report):
        if report.failed:
            self.collection_errors += 1

    def pytest_runtest_logreport(self, report):
        phases = self.reports.setdefault(report.nodeid, {})
        if report.when in phases:
            raise ValueError("duplicate test phase report")
        if not finite_seconds(report.duration):
            raise ValueError("invalid test phase duration")
        phases[report.when] = report.outcome
        self.durations.setdefault(report.nodeid, {})[report.when] = report.duration

    def pytest_sessionfinish(self, session, exitstatus):
        finished = time.monotonic()
        fingerprints = source_fingerprints()
        if self.fingerprints is not None and fingerprints != self.fingerprints:
            raise ValueError("source/input changed during shard execution")
        collection_finished = self.collection_finished or finished
        result = {"schema": 2,
                  "inventory_digest": digest(self.collected),
                  "timing_manifest_digest": self.timings.manifest_digest,
                  "timing_mode": self.timings.mode,
                  "source_fingerprints": fingerprints,
                  "durations": self.durations,
                  "telemetry": {"collection_seconds": collection_finished - self.started,
                                "execution_seconds": finished - collection_finished},
                  "identity": identity(), "index": self.index,
                  "count": self.count, "collected": self.collected,
                  "selected": self.selected, "reports": self.reports,
                  "collection_errors": self.collection_errors,
                  "exitstatus": int(exitstatus)}
        self.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.output.with_suffix(".tmp")
        write_started = time.monotonic()
        contents = json.dumps(result)
        temporary.write_text(contents, encoding="utf-8")
        temporary.replace(self.output)
        print(f"Shard result: {len(contents.encode())} bytes; "
              f"serialization/write {time.monotonic() - write_started:.6f}s")


def verify(results, count, expected_identity, timings=None, *, fingerprints=None):
    """A green aggregate means every collected test completed exactly once."""
    if (type(expected_identity) is not dict
            or set(expected_identity) != {"GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"}
            or not all(isinstance(value, str) for value in expected_identity.values())):
        raise ValueError("malformed expected execution identity")
    if type(count) is not int or count < 1 or len(results) != count:
        raise ValueError("missing or extra shard results")
    if (any(type(r["index"]) is not int for r in results)
            or {r["index"] for r in results} != set(range(count))):
        raise ValueError("missing or duplicate shard index")
    collected = results[0]["collected"]
    if (type(collected) is not list or not collected
            or not all(isinstance(node, str) and node for node in collected)):
        raise ValueError("empty or malformed complete collection")
    timings = timing_hints(timings)
    assignments = partition(collected, count, timings)
    sources = results[0]["source_fingerprints"]
    validate_fingerprints(sources)
    if fingerprints is not None and sources != fingerprints:
        raise ValueError("stale source/input fingerprints")
    observed = []
    for result in results:
        index = result["index"]
        if (type(index) is not int or type(result["schema"]) is not int
                or result["schema"] != 2
                or type(result["count"]) is not int or result["count"] != count
                or result["identity"] != expected_identity
                or result["collected"] != collected
                or type(result["exitstatus"]) is not int or result["exitstatus"] != 0
                or type(result["collection_errors"]) is not int
                or result["collection_errors"] != 0):
            raise ValueError("failed, stale or inconsistent shard result")
        if (result["timing_manifest_digest"] != timings.manifest_digest
                or result["timing_mode"] != timings.mode):
            raise ValueError("inconsistent timing manifest or mode")
        if (result["inventory_digest"] != digest(collected)
                or result["source_fingerprints"] != sources):
            raise ValueError("inconsistent inventory or source provenance")
        telemetry = result["telemetry"]
        if (type(telemetry) is not dict
                or set(telemetry) != {"collection_seconds", "execution_seconds"}
                or not all(finite_seconds(value) for value in telemetry.values())):
            raise ValueError("invalid phase telemetry duration")
        if result["selected"] != assignments[index] or not result["selected"]:
            raise ValueError("incomplete or incorrect shard assignment")
        if (type(result["reports"]) is not dict
                or list(result["reports"]) != result["selected"]):
            raise ValueError("missing or extra executed test")
        durations = result["durations"]
        if type(durations) is not dict or list(durations) != result["selected"]:
            raise ValueError("missing or extra phase duration nodes")
        for node, phases in result["reports"].items():
            if type(phases) is not dict:
                raise ValueError("malformed test phases")
            if (set(phases) - {"setup", "call", "teardown"}
                    or phases.get("setup") not in {"passed", "skipped"}
                    or phases.get("teardown") not in {"passed", "skipped"}
                    or (phases["setup"] == "passed"
                        and phases.get("call") not in {"passed", "skipped"})
                    or (phases["setup"] == "skipped" and "call" in phases)):
                raise ValueError("failed or incomplete test phases")
            expected_phases = (["setup", "teardown"] if phases["setup"] == "skipped"
                               else ["setup", "call", "teardown"])
            if list(phases) != expected_phases:
                raise ValueError("incorrect test phase order")
            if (type(durations[node]) is not dict or list(durations[node]) != expected_phases
                    or not all(finite_seconds(value) for value in durations[node].values())):
                raise ValueError("invalid or incomplete phase durations")
            observed.append(node)
    if Counter(observed) != Counter(collected):
        raise ValueError("full test collection was not executed exactly once")
    return len(observed)


def cleanup_workers(processes):
    """Signal only sessions created by this runner, escalate and reap owners."""
    for process in processes:
        if process.poll() is None:
            # Popen owns a new session, so its PID is its private group ID.
            if hasattr(process, "pid"):
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            else:
                process.terminate()
    for process in processes:
        if process.poll() is None:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        # Also clean descendants if the runner exited before interruption.
        if hasattr(process, "pid"):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def hosted_config(count):
    """One configured hosted count supplies matrix and both command arguments."""
    if type(count) is not int or count < 1:
        raise ValueError("invalid hosted shard count")
    return {"matrix": {"index": list(range(count))},
            "run_args": ["--count", str(count)],
            "verify_args": ["--count", str(count)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    config = commands.add_parser("config")
    config.add_argument("--count", type=int, required=True)
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
    if args.command == "config":
        print(json.dumps(hosted_config(args.count)))
        return 0
    timings = load_timings()
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
                         "--output", str(output)], stdout=stream, stderr=subprocess.STDOUT,
                        start_new_session=True)
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
            cleanup_workers(processes)
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

        return pytest.main(sys.argv[1:], plugins=[Shard(
            args.index, args.count, args.output, timings)])
    try:
        results = [decode_json(Path(path).read_text(encoding="utf-8")) for path in args.results]
        total = verify(results, args.count, identity(), timings,
                       fingerprints=source_fingerprints())
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        print(f"Python shard verification failed: {error}", file=sys.stderr)
        return 1
    print(f"All {total} collected Python tests completed exactly once across {args.count} shards.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
