#!/usr/bin/env python3
"""Separate mandatory engine evidence recorder/verifier and pytest plugin.

No pytest dependency is imported by the CLI. The harness runs as record's child,
loads this file as a pytest plugin, and writes lifecycle.json to the private path
in ENGINE_CONTRACT_LIFECYCLE. Only record publishes engine-contract.json, after
child exit, owned-process cleanup checks, and a second source fingerprint.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import secrets
import socket
import socketserver
import stat
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
SELECTION_PATH = "scripts/data/engine-contract-selection.json"
REPOSITORY = "anurag-duddu/specimen-digitization-app"
APPROVED_TOOLCHAIN = {
    "schema": 1,
    "assets": {
        "dataconnect": {"version": "3.2.0", "bytes": 30744760,
                        "sha256": "82bd05e748526330b94b2d2d797507175ea1251b1760f64bc1d1e904f23c2f22",  # pragma: allowlist secret (approved public engine asset digest)
                        "url": "https://storage.googleapis.com/firemat-preview-drop/emulator/dataconnect-emulator-linux-amd64-v3.2.0"},
        "storage": {"version": "1.1.3", "bytes": 52892936,
                    "sha256": "0cd52db6f6271d62078f805220706377c849220b73bd68aa27078d977df9c900",  # pragma: allowlist secret (approved public engine asset digest)
                    "url": "https://storage.googleapis.com/firebase-preview-drop/emulator/cloud-storage-rules-runtime-v1.1.3.jar"},
        "firebase": {"version": "15.8.0", "bytes": 285548396,
                     "sha256": "9b0fd84d6b9b7d62dbea76a4753f7098fbdc8c5ad8dea8da0432852fd99bdd57",  # pragma: allowlist secret (approved public engine asset digest)
                     "url": "https://github.com/firebase/firebase-tools/releases/download/v15.8.0/firebase-tools-linux"},
    },
    "runtime": {"java": "21.0.12+1", "postgres": "16.15", "node": "22.23.3",
                "image_os": "ubuntu24", "image_version": "20261012.334.1", "postgres_bin": "/usr/lib/postgresql/16/bin",
                "java_home_env": "JAVA_HOME_21_X64", "postgres_clients": ["initdb", "pg_ctl", "createdb", "psql", "pg_dump", "pg_restore"],
                "uuid_ossp": True, "postgres_server": "16.15"},
}
SOURCE_PREFIXES = ("src/", "tests/", "scripts/", "dataconnect/", ".github/")
CONFIG_FILES = {"pyproject.toml", "uv.lock", "storage.rules", "firebase.json", "firebase.data-emulator.json",
                "pytest.ini", "conftest.py", "setup.cfg", "tox.ini", ".python-version", ".gitattributes"}
SEED = {"organization": "00000000-0000-4000-8000-000000000001",
        "collection": "00000000-0000-4000-8000-000000000002", "uid": "synthetic-reviewer",
        "organization_active": True, "collection_active": True, "role": "reviewer", "can_view_sensitive": True}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError(f"nonfinite JSON number: {value}")


def regular_file(path):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        require(not part.is_symlink(), f"symlinked input: {part}")
    require(stat.S_ISREG(path.stat().st_mode), f"not a regular file: {path}")
    return path


def read_json(path):
    return json.loads(regular_file(path).read_text(encoding="utf-8"), object_pairs_hook=unique_object,
                      parse_constant=reject_constant)


def read_result(directory):
    directory = Path(directory)
    # Shard artifacts may share the aggregate directory. No other engine final or
    # partial is accepted, and arbitrary JSON filenames cannot stand in for final.
    require(not directory.is_symlink(), "symlinked results directory")
    matches = sorted(p.name for p in directory.glob("engine-contract*"))
    require(matches == ["engine-contract.json"], "missing, extra or partial engine result")
    result = read_json(directory / "engine-contract.json")
    require(type(result) is dict and type(result.get("schema")) is int and result["schema"] == 1, "unknown result schema")
    return result


def seconds(value):
    require(type(value) in (float, int) and math.isfinite(value) and value >= 0, "invalid phase/event seconds")


def exact_ids(actual, expected, label):
    require(type(actual) is list and all(type(v) is str for v in actual) and actual == expected and len(actual) == len(set(actual)),
            f"{label} inventory mismatch or duplicate")


def load_selection(path):
    selection = read_json(path)
    require(type(selection) is dict and type(selection.get("schema")) is int and selection["schema"] == 1, "unknown selection schema")
    require(selection.get("tier") == "mandatory-engine-contracts", "wrong selection tier")
    for field, count in (("python_nodes", 9), ("connector_groups", 19), ("storage_assertions", 13), ("residual_opt_in_sql", 17)):
        ids = selection.get(field)
        require(type(ids) is list and len(ids) == count and all(type(v) is str and v for v in ids)
                and len(set(ids)) == count, f"{field} selection inventory mismatch")
    for field in ("stages", "readiness", "processes"):
        ids = selection.get(field)
        require(type(ids) is list and bool(ids) and all(type(v) is str and v for v in ids)
                and len(set(ids)) == len(ids), f"{field} selection inventory mismatch")
    require(selection.get("toolchain") == "scripts/data/engine-toolchain.json", "unexpected toolchain path")
    return selection


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip("\n")


def file_hash(path):
    with regular_file(path).open("rb") as handle:
        h = hashlib.sha256()
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def source_fingerprints(root):
    paths = sorted(p for p in git(root, "ls-files", "-z").split("\0") if p and (p.startswith(SOURCE_PREFIXES) or p in CONFIG_FILES))
    require(bool(paths), "empty tracked source inventory")
    # Hash names as well as bytes: tracked additions and deletions invalidate.
    return {p: file_hash(root / p) for p in paths}


def expected_context(root, selection_path, env=None):
    env = os.environ if env is None else env
    require(env.get("GITHUB_ACTIONS") == "true" and env.get("GITHUB_REPOSITORY") == REPOSITORY,
            "hosted canonical identity required; local diagnostics cannot qualify")
    sha = git(root, "rev-parse", "HEAD")
    require(re.fullmatch(r"[0-9a-f]{40}", sha) is not None and env.get("GITHUB_SHA") == sha,
            "checkout SHA differs from canonical hosted identity")
    for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"):
        require(re.fullmatch(r"[1-9][0-9]*", env.get(key, "")) is not None, f"invalid hosted {key}")
    event = env.get("GITHUB_EVENT_NAME")
    require(event in ("push", "pull_request", "workflow_dispatch"), "unexpected hosted event identity")
    mode = env.get("ENGINE_CACHE_MODE")
    require(mode in ("normal", "cold"), "explicit expected cache mode required")
    require(mode == "normal" or event == "workflow_dispatch", "cold cache mode is dispatch-only")
    root = Path(root)
    canonical = root / SELECTION_PATH
    require(regular_file(selection_path).read_bytes() == regular_file(canonical).read_bytes(),
            "selection is not the current checkout selection")
    selection = load_selection(canonical)
    toolchain_path = root / selection["toolchain"]
    require(digest(read_json(toolchain_path)) == digest(APPROVED_TOOLCHAIN), "unapproved toolchain configuration")
    changed = git(root, "diff", "--name-only", "HEAD").splitlines()
    require(not any(p.startswith(SOURCE_PREFIXES) or p in CONFIG_FILES for p in changed),
            "dirty source/config/helper checkout cannot qualify hosted identity")
    fingerprints = source_fingerprints(root)
    require(SELECTION_PATH in fingerprints and selection["toolchain"] in fingerprints,
            "selection/toolchain must be tracked approved source inputs")
    config = {p: value for p, value in fingerprints.items() if p in CONFIG_FILES or p.startswith(("dataconnect/", "scripts/data/"))}
    return {"qualification": "hosted", "repository": REPOSITORY, "source_sha": sha,
            "run_id": env["GITHUB_RUN_ID"], "run_attempt": env["GITHUB_RUN_ATTEMPT"], "event": event,
            "cache_mode": mode, "selection_digest": file_hash(canonical), "toolchain_digest": file_hash(toolchain_path),
            "config_digest": digest(config), "source_digest": digest(fingerprints), "source_fingerprints": fingerprints}


def passed_events(events, ids, label):
    require(type(events) is list and all(type(e) is dict for e in events), f"missing or malformed {label} events")
    exact_ids([event.get("id") for event in events], ids, label)
    for event in events:
        require(event.get("outcome") == "passed" and event.get("wasxfail") is None, f"{label} event failed or xfail")
        seconds(event.get("seconds"))


LAUNCH_FIELDS = {"id", "pid", "birth_id", "os_started_ns", "instance", "started_ns"}
CLEANUP_FIELDS = LAUNCH_FIELDS | {"ended_ns", "owned", "stopped", "waited"}


def timestamp(value):
    require(type(value) is int and value > 0, "invalid process lifecycle timestamp")


def validate_processes(result, selection):
    """Bind harness claims to recorder-owned, live-OS registration receipts."""
    receipts = result.get("process_receipts")
    require(type(receipts) is dict and type(receipts.get("schema")) is int and receipts["schema"] == 1,
            "missing or unknown process receipt schema")
    for field in ("started_ns", "ended_ns", "epoch_started_ns", "epoch_ended_ns"):
        timestamp(receipts.get(field))
    require(receipts["started_ns"] < receipts["ended_ns"] and receipts["epoch_started_ns"] < receipts["epoch_ended_ns"],
            "invalid process receipt lifecycle window")
    processes = result["lifecycle"].get("processes")
    for rows, label in ((processes, "owned process"), (receipts.get("launches"), "process launch receipt"),
                        (receipts.get("cleanups"), "process cleanup receipt")):
        require(type(rows) is list and all(type(row) is dict for row in rows), f"malformed {label} inventory")
        exact_ids([row.get("id") for row in rows], selection["processes"], label)
    instances, births, pid_ends = set(), set(), {}
    last_start = receipts["started_ns"]
    for process, launch, cleanup in zip(processes, receipts["launches"], receipts["cleanups"]):
        require(set(launch) == LAUNCH_FIELDS and set(cleanup) == set(process) == CLEANUP_FIELDS,
                "missing or extra process receipt fields")
        require(type(launch["pid"]) is int and launch["pid"] > 1, "invalid process receipt PID")
        require(type(launch["birth_id"]) is str and re.fullmatch(r"[0-9a-f]{64}", launch["birth_id"]) is not None,
                "missing or invalid process birth identity")
        require(type(launch["instance"]) is str and re.fullmatch(r"[0-9a-f]{32}", launch["instance"]) is not None,
                "invalid process receipt instance")
        timestamp(launch["os_started_ns"])
        require(receipts["epoch_started_ns"] - 10**9 <= launch["os_started_ns"] <= receipts["epoch_ended_ns"],
                "process OS birth timestamp outside recorder lifecycle window")
        birth = (launch["pid"], launch["birth_id"])
        require(launch["instance"] not in instances and birth not in births, "aliased process instance/birth receipt")
        instances.add(launch["instance"])
        births.add(birth)
        require(all(cleanup.get(key) == value and type(cleanup.get(key)) is type(value) for key, value in launch.items())
                and all(process[key] == value and type(process[key]) is type(value) for key, value in cleanup.items()),
                "unbound or mismatched process ownership/cleanup receipt")
        for field in ("started_ns", "ended_ns"):
            timestamp(cleanup[field])
        require(last_start <= cleanup["started_ns"] < cleanup["ended_ns"] <= receipts["ended_ns"],
                "invalid process lifecycle timestamp order/window")
        require(cleanup["started_ns"] >= pid_ends.get(cleanup["pid"], 0), "overlapping process PID lifecycles")
        last_start = cleanup["started_ns"]
        pid_ends[cleanup["pid"]] = cleanup["ended_ns"]
        require(cleanup["owned"] is True and cleanup["stopped"] is True and cleanup["waited"] is True,
                "owned process cleanup failed")


def validate(result, expected, selection):
    """Validate against independently derived checkout/environment expectations."""
    require(type(result) is dict and type(result.get("schema")) is int and result["schema"] == 1, "unknown result schema")
    require(result.get("complete") is True, "incomplete engine result")
    require(expected.get("qualification") == "hosted", "local identity cannot qualify")
    for field in ("context_start", "context_end"):
        require(result.get(field) == expected, f"{field} identity/context/source fingerprint mismatch")
    require(type(result.get("exitstatus")) is int and result["exitstatus"] == 0, "nonzero wrapper exit")
    seconds(result.get("seconds"))
    report = result.get("pytest", {})
    require(type(report) is dict, "malformed pytest report")
    require(type(report.get("schema")) is int and report["schema"] == 1 and report.get("finished") is True,
            "pytest collection/session unfinished or unknown schema")
    require(report.get("collection_events") == [], "pytest collection error")
    require(type(report.get("exitstatus")) is int and report["exitstatus"] == 0, "nonzero pytest exit")
    exact_ids(report.get("collected"), selection["python_nodes"], "collected Python")
    exact_ids(report.get("selected"), selection["python_nodes"], "selected Python")
    events = report.get("events")
    require(type(events) is list and all(type(e) is dict for e in events), "missing or malformed phase events")
    expected_phases = [(node, phase) for node in selection["python_nodes"] for phase in ("setup", "call", "teardown")]
    actual_phases = [(event.get("nodeid"), event.get("phase")) for event in events]
    require(actual_phases == expected_phases and len(set(actual_phases)) == len(actual_phases),
            "phase inventory mismatch, missing call/teardown or duplicate phase")
    for event in events:
        require(event.get("outcome") == "passed" and "wasxfail" in event and event["wasxfail"] is None,
                "mandatory phase failed, skipped or wasxfail")
        seconds(event.get("seconds"))
    lifecycle = result.get("lifecycle", {})
    require(type(lifecycle) is dict, "malformed lifecycle")
    require(type(lifecycle.get("schema")) is int and lifecycle["schema"] == 1, "unknown lifecycle schema")
    require(lifecycle.get("engine_flag") == "true", "missing explicit engine flag")
    tools = lifecycle.get("tools", {})
    require(type(tools) is dict and set(tools) == set(APPROVED_TOOLCHAIN["assets"]), "missing or extra engine tool")
    for name, approved in APPROVED_TOOLCHAIN["assets"].items():
        observed = tools[name]
        require(type(observed) is dict and all(type(observed.get(key)) is type(approved[key]) and observed[key] == approved[key]
                                             for key in ("version", "bytes", "sha256"))
                and type(observed.get("path")) is str and Path(observed["path"]).is_absolute(), f"unapproved engine tool {name}")
    require(digest(lifecycle.get("runtime")) == digest(APPROVED_TOOLCHAIN["runtime"]), "missing or unapproved runtime tool versions")
    preflight = lifecycle.get("preflight", {})
    require(preflight.get("project") == "demo-specimen-data" and preflight.get("host") == "127.0.0.1"
            and preflight.get("ports_free_before") is True and preflight.get("credentials_absent") is True, "unsafe loopback/demo preflight")
    ports = preflight.get("ports", [])
    require(type(ports) is list and len(ports) == 3 and all(type(p) is int and 1024 < p < 65536 and p not in (3000, 8000) for p in ports)
            and len(set(ports)) == 3, "invalid preflight port inventory")
    require(preflight.get("postgres_host") == f"127.0.0.1:{ports[0]}"
            and preflight.get("dataconnect_host") == preflight.get("python_host") == f"127.0.0.1:{ports[1]}"
            and preflight.get("storage_host") == f"127.0.0.1:{ports[2]}", "loopback engine/Python host mismatch")
    require(digest(lifecycle.get("seed")) == digest(SEED), "seed missing or mismatch")
    passed_events(lifecycle.get("readiness"), selection["readiness"], "readiness")
    passed_events(lifecycle.get("stages"), selection["stages"], "stage")
    passed_events(lifecycle.get("node_events"), selection["connector_groups"] + selection["storage_assertions"], "Node assertion")
    validate_processes(result, selection)
    cleanup = lifecycle.get("cleanup", {})
    require(cleanup.get("outcome") == "passed" and cleanup.get("ports_free_after") is True and cleanup.get("survivors") == [],
            "cleanup missing, failed or surviving processes/ports")
    seconds(cleanup.get("seconds"))
    cache = lifecycle.get("cache", {})
    require(cache.get("mode") == expected["cache_mode"] and cache.get("directory_private") is True, "cache mode/private directory mismatch")
    require(type(cache.get("entries_before")) is int and cache["entries_before"] >= 0
            and type(cache.get("directory_fresh")) is bool, "invalid cache freshness evidence")
    if expected["cache_mode"] == "cold":
        require(cache.get("restore") == "bypassed" and cache["directory_fresh"] is True and cache["entries_before"] == 0,
                "false cold cache provenance")
    else:
        require(cache.get("restore") in ("hit", "miss"), "invalid normal cache restore evidence")


def atomic_json(path, value):
    path = Path(path)
    require(not path.exists() and not path.is_symlink(), f"refusing existing result: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    # A crash leaves .partial, which read_result refuses; success is atomic.
    temporary = path.with_name(path.name + ".partial")
    with temporary.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, allow_nan=False, separators=(",", ":"))
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def inspect_tools(env):
    """Before launch, verify approved executable bytes and runner-provided tools."""
    require(not any(env.get(name) for name in ("GOOGLE_APPLICATION_CREDENTIALS", "FIREBASE_TOKEN", "CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE")),
            "engine preflight refuses cloud credential environment")
    require(platform.system() == "Linux" and platform.machine() == "x86_64", "unapproved engine tool platform")
    variables = {"dataconnect": "DATACONNECT_EMULATOR_BIN", "storage": "STORAGE_RULES_RUNTIME_JAR", "firebase": "FIREBASE_CLI_BIN"}
    observed = {}
    for name, variable in variables.items():
        approved = APPROVED_TOOLCHAIN["assets"][name]
        path = regular_file(env.get(variable, ""))
        require(path.stat().st_size == approved["bytes"] and file_hash(path) == approved["sha256"], f"engine tool bytes/hash mismatch: {name}")
        if name != "storage":
            require(os.access(path, os.X_OK), f"engine tool not executable: {name}")
        observed[name] = {"path": str(path), **{k: approved[k] for k in ("version", "bytes", "sha256")}}
    runtime = APPROVED_TOOLCHAIN["runtime"]
    require(env.get("ImageOS") == runtime["image_os"], "unapproved runtime ImageOS")
    require(env.get("ImageVersion") == runtime["image_version"], "unapproved runtime ImageVersion")
    require(env.get("POSTGRES_BIN") == runtime["postgres_bin"], "unapproved PostgreSQL tool path")
    require(Path("/usr/share/postgresql/16/extension/uuid-ossp.control").is_file(), "missing PostgreSQL uuid-ossp extension")
    java = Path(env.get("JAVA_HOME_21_X64", "")) / "bin/java"
    require(java.is_absolute() and env.get("JAVA_HOME") == env.get("JAVA_HOME_21_X64"), "Java21 explicit home required")
    commands = [([str(java), "-version"], runtime["java"]), (["node", "--version"], "v" + runtime["node"])]
    commands += [([str(Path(runtime["postgres_bin"]) / name), "--version"], runtime["postgres"]) for name in runtime["postgres_clients"]]
    for command, version in commands:
        probe = subprocess.run(command, env=env, capture_output=True, text=True, timeout=15)
        output = probe.stdout + probe.stderr
        if command[0] == "node":
            matches = probe.stdout.strip() == version
        elif command[0] == str(java):
            build = re.search(r"build ([0-9][0-9.+]+)(?:-LTS)?[,)]", output)
            matches = build is not None and build[1] == version
        else:
            pg_version = re.search(r"\(PostgreSQL\) ([0-9]+(?:\.[0-9]+)+)", output)
            matches = pg_version is not None and pg_version[1] == version
        require(probe.returncode == 0 and matches, f"runtime version preflight failed: {command[0]}")
    return observed


def process_birth(pid):
    """Read an OS birth identity, never one supplied by the harness.

    Linux ticks plus boot UUID disambiguate recycled PIDs. Darwin's OS start
    time supports local contract diagnostics only (tools require hosted Linux).
    Return None only for an absent process; permission/read errors fail closed.
    """
    require(type(pid) is int and pid > 1, "invalid process PID")
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return None
    if sys.platform == "linux":
        try:
            fields = Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()
        except FileNotFoundError:
            return None
        ticks = int(fields[19])  # field 22; comm can itself contain spaces/parentheses
        boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        epoch = next(int(line.split()[1]) for line in Path("/proc/stat").read_text().splitlines() if line.startswith("btime "))
        born_ns = epoch * 10**9 + ticks * 10**9 // os.sysconf("SC_CLK_TCK")
        return digest({"boot_id": boot, "start_ticks": ticks}), born_ns
    require(sys.platform == "darwin", "unsupported OS process birth identity")
    probe = subprocess.run(["ps", "-p", str(pid), "-o", "lstart="], capture_output=True, text=True,
                           env=dict(os.environ, LC_ALL="C"), timeout=5)
    if probe.returncode == 1 and not probe.stdout.strip():
        return None
    require(probe.returncode == 0, "OS process birth lookup failed")
    started = probe.stdout.strip()
    born_ns = int(datetime.strptime(started, "%a %b %d %H:%M:%S %Y").timestamp()) * 10**9
    return digest({"darwin_lstart": started}), born_ns


class ProcessRegistry:
    """Recorder memory, populated while engines live; never loaded from a file."""
    def __init__(self, roles):
        self.roles = list(roles)
        self.started_ns = time.monotonic_ns()
        self.epoch_ns = time.time_ns()
        self.launches = []
        self.cleanups = []
        self.errors = []

    def start(self, role, pid):
        require(len(self.launches) < len(self.roles) and role == self.roles[len(self.launches)],
                "unexpected/duplicate process launch role or order")
        birth = process_birth(pid)
        require(birth is not None, "process absent at launch registration")
        birth_id, born_ns = birth
        # OS birth clocks have tick/second granularity. One second covers that
        # rounding, while refusing an unrelated long-running process.
        require(self.epoch_ns - 10**9 <= born_ns <= time.time_ns(), "process birth predates recorder launch window")
        require(not any(row["pid"] == pid and row["birth_id"] == birth_id for row in self.launches),
                "aliased OS process instance")
        require(not any(row["pid"] == pid and not any(end["instance"] == row["instance"] for end in self.cleanups)
                        for row in self.launches), "overlapping process PID lifecycles")
        receipt = {"id": role, "pid": pid, "birth_id": birth_id, "os_started_ns": born_ns, "instance": secrets.token_hex(16),
                   "started_ns": time.monotonic_ns()}
        self.launches.append(receipt)
        return dict(receipt)

    def end(self, receipt, waited):
        require(type(receipt) is dict and set(receipt) == LAUNCH_FIELDS, "malformed process launch receipt")
        launch = next((row for row in self.launches if row["instance"] == receipt.get("instance")), None)
        require(launch is not None and receipt == launch
                and all(type(receipt[key]) is type(value) for key, value in launch.items()),
                "unbound or mismatched process cleanup receipt")
        require(not any(row["instance"] == launch["instance"] for row in self.cleanups), "duplicate process cleanup receipt")
        require(waited is True, "process wait acknowledgement required")
        current = process_birth(launch["pid"])
        require(current is None or current[0] != launch["birth_id"], "owned process still running at cleanup")
        cleanup = {**launch, "ended_ns": time.monotonic_ns(), "owned": True, "stopped": True, "waited": True}
        self.cleanups.append(cleanup)
        return dict(cleanup)

    def snapshot(self):
        require(not self.errors, "process registration failed: " + "; ".join(self.errors))
        require(len(self.launches) == len(self.cleanups) == len(self.roles), "missing process launch/cleanup receipts")
        # Independent processes (e.g. PostgreSQL) can stop after later-launched
        # children. Publish in frozen role order, keeping unique instance links.
        cleanups = [next(row for row in self.cleanups if row["instance"] == launch["instance"]) for launch in self.launches]
        return {"schema": 1, "started_ns": self.started_ns, "ended_ns": time.monotonic_ns(),
                "epoch_started_ns": self.epoch_ns, "epoch_ended_ns": time.time_ns(),
                "launches": [dict(row) for row in self.launches], "cleanups": [dict(row) for row in cleanups]}


def process_request(request, env=None):
    env = os.environ if env is None else env
    port = int(env.get("ENGINE_CONTRACT_PROCESS_PORT", "0"))
    token = env.get("ENGINE_CONTRACT_PROCESS_TOKEN")
    require(0 < port < 65536 and token, "process registration requires live recorder environment")
    with socket.create_connection(("127.0.0.1", port), timeout=5) as connection:
        connection.sendall((json.dumps({"token": token, **request}, allow_nan=False) + "\n").encode())
        with connection.makefile("rb") as stream:
            response = json.loads(stream.readline(65537), object_pairs_hook=unique_object, parse_constant=reject_constant)
    require(response.get("ok") is True, "process registration: " + str(response.get("error")))
    return response["receipt"]


@contextmanager
def process_server(roles):
    registry = ProcessRegistry(roles)
    token = secrets.token_hex(32)

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            self.connection.settimeout(5)
            try:
                raw = self.rfile.readline(65537)
                require(len(raw) <= 65536 and raw.endswith(b"\n"), "malformed process registration frame")
                request = json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)
                require(type(request) is dict and request.get("token") == token, "invalid process registration token")
                if request.get("action") == "start":
                    require(set(request) == {"token", "action", "id", "pid"}, "invalid process launch request")
                    receipt = registry.start(request["id"], request["pid"])
                else:
                    require(request.get("action") == "end" and set(request) == {"token", "action", "receipt", "waited"},
                            "invalid process cleanup request")
                    receipt = registry.end(request["receipt"], request["waited"])
                response = {"ok": True, "receipt": receipt}
            except (ValueError, OSError, KeyError, TypeError, IndexError, subprocess.SubprocessError) as error:
                registry.errors.append(str(error))
                response = {"ok": False, "error": str(error)}
            self.wfile.write((json.dumps(response, allow_nan=False) + "\n").encode())

    with socketserver.TCPServer(("127.0.0.1", 0), Handler) as server:
        worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        worker.start()
        try:
            yield registry, {"ENGINE_CONTRACT_PROCESS_PORT": str(server.server_address[1]),
                             "ENGINE_CONTRACT_PROCESS_TOKEN": token}
        finally:
            server.shutdown()
            worker.join()


def assert_cleanup(lifecycle):
    """Check registered instances, allowing PID recycling, and loopback ports."""
    for process in lifecycle["processes"]:
        current = process_birth(process["pid"])
        require(current is None or current[0] != process["birth_id"],
                f"owned process still exists after cleanup: {process['id']}")
    for port in lifecycle["preflight"]["ports"]:
        with socket.socket() as server:
            # Closed TCP connections can retain TIME_WAIT after engine exit.
            # Reuse their address without permitting a surviving listener;
            # Linux socket(7) requires the former socket to opt into reuse too.
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(("127.0.0.1", port))


def run_command(command, env, scratch):
    report_path = scratch / "pytest-phases.json"
    lifecycle_path = scratch / "lifecycle.json"
    roles = load_selection(ROOT / SELECTION_PATH)["processes"]
    with process_server(roles) as (registry, registration_env):
        child_env = dict(env, **registration_env, ENGINE_CONTRACT_PYTEST_REPORT=str(report_path),
                         ENGINE_CONTRACT_LIFECYCLE=str(lifecycle_path))
        # Output is streamed to the job log, never buffered away from the owner.
        completed = subprocess.run(command, env=child_env, check=False)
    return completed.returncode, read_json(report_path), read_json(lifecycle_path), registry.snapshot()


def record(root, selection_path, output, command, env=None):
    env = dict(os.environ if env is None else env)
    require(env.get("SPECIMEN_TEST_SQL_EMULATOR") == "true", "record requires SPECIMEN_TEST_SQL_EMULATOR=true")
    require(bool(command), "record requires a harness command after --")
    output = Path(output)
    require(not output.is_symlink(), "symlinked record output")
    require(not output.exists() or not list(output.iterdir()), "record output must be a fresh empty directory")
    output.mkdir(parents=True, exist_ok=True)
    os.chmod(output, 0o700)
    started = time.monotonic()
    initial = expected_context(root, selection_path, env)
    selection = load_selection(selection_path)
    actual_tools = inspect_tools(env)
    with tempfile.TemporaryDirectory(prefix=".engine-contract-", dir=output) as temp:
        exitstatus, report, lifecycle, process_receipts = run_command(command, env, Path(temp))
        result = {"schema": 1, "complete": True, "context_start": initial,
                  "context_end": initial, "pytest": report,
                  "lifecycle": lifecycle, "process_receipts": process_receipts,
                  "exitstatus": exitstatus, "seconds": time.monotonic() - started}
        validate(result, initial, selection)
        require(lifecycle["tools"] == actual_tools, "reported engine tool paths differ from inspected bytes")
        assert_cleanup(lifecycle)
        require(inspect_tools(env) == actual_tools, "engine tool bytes changed during execution")
    # Even scratch cleanup must complete before a final success marker exists.
    result["context_end"] = expected_context(root, selection_path, env)
    result["seconds"] = time.monotonic() - started
    validate(result, initial, selection)
    atomic_json(output / "engine-contract.json", result)
    return result


class Reporter:
    """Append phase reports; never turn phase/node events into overwriting maps."""
    def __init__(self, output):
        self.output = Path(output)
        self.collected = []
        self.selected = []
        self.events = []
        self.collection_events = []

    def pytest_collection_modifyitems(self, session, config, items):
        self.collected = [item.nodeid for item in items]

    def pytest_collection_finish(self, session):
        self.selected = [item.nodeid for item in session.items]

    def pytest_collectreport(self, report):
        if report.failed:
            self.collection_events.append({"nodeid": report.nodeid, "outcome": report.outcome})

    def pytest_runtest_logreport(self, report):
        self.events.append({"nodeid": report.nodeid, "phase": report.when, "outcome": report.outcome,
                            "wasxfail": getattr(report, "wasxfail", None), "seconds": report.duration})

    def pytest_sessionfinish(self, session, exitstatus):
        atomic_json(self.output, {"schema": 1, "collected": self.collected, "selected": self.selected,
                                  "events": self.events, "collection_events": self.collection_events,
                                  "exitstatus": int(exitstatus), "finished": True})


Reporter.pytest_collection_modifyitems.pytest_impl = {"tryfirst": True}


def pytest_configure(config):
    path = os.environ.get("ENGINE_CONTRACT_PYTEST_REPORT")
    if path:
        config.pluginmanager.register(Reporter(path), "mandatory-engine-phase-reporter")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("record", "verify"):
        sub = commands.add_parser(action)
        sub.add_argument("--selection", type=Path, required=True)
        sub.add_argument("--results", type=Path, required=True)
        if action == "record":
            sub.add_argument("command", nargs=argparse.REMAINDER)
    start = commands.add_parser("process-start", help="register a live owned engine immediately after launch")
    start.add_argument("--id", required=True)
    start.add_argument("--pid", type=int, required=True)
    end = commands.add_parser("process-end", help="acknowledge wait and verify cleanup of a registered instance")
    end.add_argument("--receipt", type=Path, required=True)
    end.add_argument("--waited", action="store_true", required=True)
    args = parser.parse_args(argv)
    try:
        if args.action in ("process-start", "process-end"):
            request = ({"action": "start", "id": args.id, "pid": args.pid} if args.action == "process-start" else
                       {"action": "end", "receipt": read_json(args.receipt), "waited": args.waited})
            print(json.dumps(process_request(request), allow_nan=False, separators=(",", ":")))
            return 0
        if args.action == "record":
            command = args.command[1:] if args.command[:1] == ["--"] else args.command
            record(ROOT, args.selection, args.results, command)
        else:
            expected = expected_context(ROOT, args.selection)
            validate(read_result(args.results), expected, load_selection(args.selection))
        print("mandatory engine contract evidence verified")
        return 0
    except (ValueError, OSError, KeyError, TypeError, AttributeError, subprocess.SubprocessError) as error:
        print(f"engine contract gate: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
