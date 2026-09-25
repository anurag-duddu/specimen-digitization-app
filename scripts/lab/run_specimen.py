"""Run one pilot specimen through the lane on this workstation (docs/execution/golive/LAB.md)."""

from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import traceback

import lab_checks

BUCKET = "specimen-digitization.firebasestorage.app"
PREFIX = "microscopic-slides/"
# USD per million tokens, input then output (docs/execution/LIVE_PILOT_COST.md 42-47).
PRICES = {"handwriting-qwen": (0.20, 0.70), "handwriting-muse": (0.30, 1.20)}
TOKEN_VARIABLES = ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACEHUB_API_TOKEN", "LOGFIRE_TOKEN")
SHAPES = re.compile(
    r"hf_[A-Za-z0-9]{16,}|(?<=Bearer )[A-Za-z0-9._~+/=-]+|ya29\.[A-Za-z0-9._-]+"
    r"|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"
)
TEXT_SUFFIXES = {".json", ".md", ".txt", ".log"}
# Until production's reserve-then-settle ledger lands, every paid attempt whose usage the run did not
# settle stays reserved at the full per-call bound: an unknown outcome (coordinator, 2026-09-23) and,
# since #86, a call that returned and then failed with a known blocker, whose usage the workflow does
# not record. The bound is the readers' and extraction's usage limit (production.py,
# total_tokens_limit=16000) at the highest known price. SAM 3 on this workstation is free.
PAID_STEP = re.compile(r"transcribe:|parse$|first_pass|harness|extract")
CALL_TOKEN_BOUND = 16_000


def subject_id(value):
    if not re.fullmatch(r"subject_[0-9]{1,12}", value):
        raise argparse.ArgumentTypeError("expected subject_<digits>")
    return value


def parse_args(argv=None):
    home = Path.home() / "specimen-golive"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("subject", type=subject_id)
    parser.add_argument("--runs-root", type=Path, default=home / "runs")
    parser.add_argument("--reports-root", type=Path, default=home / "reports")
    parser.add_argument("--segmentation", choices=("sam3", "reviewed-region"), default="sam3")
    parser.add_argument("--persistence", choices=("sql-emulator", "sqlite"), default="sql-emulator")
    parser.add_argument("--logfire", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--max-load", type=float, default=12.0)
    parser.add_argument("--max-run-usd", type=float, default=0.75)
    parser.add_argument("--lab-allowance-usd", type=float, default=5.00)
    parser.add_argument("--timeout-seconds", type=float, default=1800)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


class Redactor:
    def __init__(self, env):
        values = {env.get(name) or "" for name in TOKEN_VARIABLES}
        self.values = sorted((v for v in values if len(v) >= 8), key=len, reverse=True)

    def __call__(self, text):
        for value in self.values:
            text = text.replace(value, "[redacted]")
        return SHAPES.sub("[redacted]", text)


def recorded_spend(runs_root):
    total = 0.0
    for path in runs_root.glob("*/*/run.json"):
        try:
            total += float(json.loads(path.read_text())["costs"]["total_usd"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return total


def preflight(options, env, loadavg):
    problems = []
    load = loadavg()[0]
    if load >= options.max_load:
        problems.append(f"one-minute load {load:.1f} is at or above {options.max_load:g}")
    spent = recorded_spend(options.runs_root)
    if spent + options.max_run_usd > options.lab_allowance_usd:
        problems.append(
            f"lab spend {spent:.4f} plus this run's bound {options.max_run_usd:.2f} "
            f"exceeds the lab allowance {options.lab_allowance_usd:.2f} USD"
        )
    if not options.dry_run and env.get("SPECIMEN_APPROVED_INFERENCE") != "true":
        problems.append("SPECIMEN_APPROVED_INFERENCE is not true")
    if not options.dry_run and not env.get("HF_TOKEN"):
        problems.append("HF_TOKEN is not set")
    return problems


def run_directory(root, now):
    stamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root.mkdir(parents=True, exist_ok=True)
    for n in range(1, 1000):
        path = root / (stamp if n == 1 else f"{stamp}-{n}")
        try:
            path.mkdir()
            return path
        except FileExistsError:
            continue
    raise FileExistsError(root / stamp)


def price(snapshot):
    readings, unpriced, readers_usd, reader_tokens, total_tokens = [], [], 0.0, 0, 0
    for run in [*(snapshot.get("previous_runs") or []), snapshot["run"]]:
        total_tokens += (run.get("usage") or {}).get("tokens") or 0
        for o in run.get("observations") or []:
            if o["route_id"] not in PRICES:
                unpriced += [o["route_id"]] if o["route_id"] not in unpriced else []
                continue
            cost_in, cost_out = PRICES[o["route_id"]]
            usd = (o["input_tokens"] * cost_in + o["output_tokens"] * cost_out) / 1e6
            readers_usd += usd
            reader_tokens += o["input_tokens"] + o["output_tokens"]
            readings.append({"observation": o["id"], "route": o["route_id"], "usd": round(usd, 6),
                             "input_tokens": o["input_tokens"], "output_tokens": o["output_tokens"]})
    top = max(max(p) for p in PRICES.values()) / 1e6
    other = max(0, total_tokens - reader_tokens)
    # Every attempt of a paid step beyond the one that completed has no settled usage on the run.
    unsettled = [step for run in [*(snapshot.get("previous_runs") or []), snapshot["run"]]
                 for step, count in (run.get("attempts") or {}).items() if PAID_STEP.match(step)
                 for _ in range(count - (step in (run.get("completed_steps") or [])))]
    unsettled_usd = len(unsettled) * CALL_TOKEN_BOUND * top
    return {"readings": readings, "readers_usd": readers_usd, "unpriced_routes": unpriced,
            "other_tokens": other, "other_usd_upper_bound": other * top,
            "unsettled_attempts": unsettled, "unsettled_usd_bound": unsettled_usd,
            "total_usd": readers_usd + other * top + unsettled_usd, "sam3_usd": 0.0}


def timings(snapshot):
    steps, previous = [], None
    for event in snapshot.get("audit") or []:
        at = datetime.fromisoformat(event["created_at"])
        if event["action"] == "workflow_step" and previous:
            steps.append({"step": event["reason"], "seconds": round((at - previous).total_seconds(), 3)})
        previous = at
    return steps


class Run:
    """One lab run's record and files; every text written passes the redactor."""

    def __init__(self, options, path, redact, record):
        self.options, self.path, self.redact, self.record = options, path, redact, record
        self.log = (path / "runner.log").open("a", buffering=1)  # line by line, for a live view

    def write(self, name, data):
        if Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError(f"unsafe artifact path {name}")
        target = self.path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, (dict, list)):
            data = json.dumps(data, indent=2, ensure_ascii=False, default=str)
        if isinstance(data, str):
            data = data.encode()
        if target.suffix in TEXT_SUFFIXES:
            text = data.decode("utf-8", errors="replace")
            clean = self.redact(text)
            if clean != text:
                self.record["redacted_files"].append(name)
            data = clean.encode()
        target.write_bytes(data)

    @contextmanager
    def phase(self, name):
        entry = {"name": name, "status": "passed"}
        self.record["phases"].append(entry)
        began = time.monotonic()
        try:
            yield entry
        except Exception as exc:
            entry["status"] = "failed"
            entry["error"] = self.redact(f"{type(exc).__name__}: {exc}")
            self.log.write(self.redact(traceback.format_exc()))
        finally:
            entry["seconds"] = round(time.monotonic() - began, 3)
            self.log.write(f"{name}: {entry['status']} in {entry['seconds']} s\n")


@contextmanager
def lab_trace(options, record, redact):
    if not options.logfire:
        yield
        return
    import logfire
    from specimen_digitization.observability import configure_observability

    try:
        configure_observability(send_to_logfire=True)
    except Exception as exc:  # a lab run without traces still records every other stage
        record["trace"]["error"] = redact(f"{type(exc).__name__}: {exc}")
        yield
        return
    with logfire.span("lab specimen run {subject}", subject=options.subject, lab_run=record["run"]) as span:
        record["trace"]["lab_trace_id"] = format(span.get_span_context().trace_id, "032x")
        yield
    logfire.force_flush()


def execute(options, *, fetch, lane_factory, env, clock, loadavg, commit):
    redact = Redactor(env)
    problems = preflight(options, env, loadavg)
    if problems:
        print("refused: " + "; ".join(problems), file=sys.stderr)
        return 3
    started = clock()
    path = run_directory(options.runs_root / options.subject, started)
    record = {
        "subject": options.subject, "run": path.name, "started_at": started.isoformat(),
        "commit": commit(), "options": {k: str(v) for k, v in vars(options).items()},
        "phases": [{"name": "preflight", "status": "passed", "seconds": 0.0}],
        "stages": [], "actions": [], "costs": {"total_usd": 0.0}, "timings": [],
        "trace": {"lab_trace_id": None, "app_trace_id": None}, "redacted_files": [],
        "approvals": "synthetic mode: the profile's approvals are a local fixture",
    }
    run = Run(options, path, redact, record)
    source = evidence = None
    with run.phase("fetch"):
        data, meta = fetch(options.subject)
        source = dict(meta, size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
        run.write(f"inputs/{options.subject}.jpeg", data)
        run.write("inputs/source.json", source)
    record["source"] = source
    if source and not options.dry_run:
        with ExitStack() as stack, lab_trace(options, record, redact):
            specimen_id = actions = None
            with run.phase("ingest"):
                lane = stack.enter_context(lane_factory(path / "state", options, env))
                specimen_id = lane.ingest(options.subject + ".jpeg", data, "image/jpeg")
                record["specimen_id"] = specimen_id
            if specimen_id:
                with run.phase("process"):
                    actions = lane.process(specimen_id, time.monotonic() + options.timeout_seconds)
                record["actions"] = actions or []
                with run.phase("collect"):
                    evidence = lane.collect(specimen_id)
                    evidence["actions"] = record["actions"]
                    for name, blob in evidence["artifacts"].items():
                        run.write(name, blob)
                    for table, rows in evidence["rows"].items():
                        run.write(f"rows/{table}.json", rows)
                    run.write("snapshot.json", evidence["snapshot"])
                    run.write("workspace.json", evidence["workspace"])
                    record["rows"] = {t: len(r) for t, r in evidence["rows"].items()}
    if evidence:
        with run.phase("check"):
            record["stages"] = lab_checks.check_stages(evidence, source, options.subject)
            record["costs"] = price(evidence["snapshot"])
            record["timings"] = timings(evidence["snapshot"])
            if record["costs"]["total_usd"] > options.max_run_usd:
                record["stages"].append({"stage": "cost", "name": "Run cost", "status": "failed",
                                         "detail": f"above --max-run-usd {options.max_run_usd}"})
    # The lab's running tally against its share of G9; production's ledger never sees lab calls (G30).
    record["lab_spend_usd"] = recorded_spend(options.runs_root) + record["costs"]["total_usd"]
    record["lab_allowance_usd"] = options.lab_allowance_usd
    record["phases"].append({"name": "report", "status": "passed", "seconds": 0.0})
    record["result"] = "dry-run" if options.dry_run and source else lab_checks.verdict(
        record["phases"], record["stages"])
    record["finished_at"] = clock().isoformat()
    run.write("run.json", record)
    run.write("report.md", render(record))
    write_subject_report(options, redact)
    run.log.close()
    print(f"{record['result']}: {path}")
    return {"pass": 0, "dry-run": 0, "incomplete": 1, "fail": 1}.get(record["result"], 2)


def cell(value):
    return str(value).replace("|", "\\|").replace("\n", " / ")


def render(record):
    commit = record["commit"]
    lines = [
        f"# {record['subject']}: lab run {record['run']}", "",
        f"Result: **{record['result']}**. Commit `{str(commit.get('head'))[:12]}`"
        f"{' (uncommitted changes)' if commit.get('dirty') else ''}. Segmentation "
        f"`{record['options']['segmentation']}`, persistence `{record['options']['persistence']}`. "
        f"Approvals: {record['approvals']}.", "",
        "## Stages", "", "| Stage | Status | Detail |", "|---|---|---|",
    ]
    for s in record["stages"]:
        label = s["name"] if s["stage"] in ("trace", "cost") else f"{s['stage']} {s['name']}"
        lines.append(f"| {label} | {s['status']} | {cell(s['detail'])} |")
    lines += ["", "## Phases", "", "| Phase | Status | Seconds | Error |", "|---|---|---|---|"]
    lines += [f"| {p['name']} | {p['status']} | {p['seconds']} | {cell(p.get('error', ''))} |"
              for p in record["phases"]]
    costs = record["costs"]
    lines += ["", "## Cost", "", f"Total USD {costs['total_usd']:.6f}: readers "
              f"{costs.get('readers_usd', 0):.6f}, other tokens {costs.get('other_tokens', 0)} "
              f"at most {costs.get('other_usd_upper_bound', 0):.6f}, SAM 3 local 0. Unpriced routes: "
              f"{costs.get('unpriced_routes', [])}. Paid attempts without settled usage, held at the full "
              f"per-call bound: {costs.get('unsettled_attempts', [])}, USD {costs.get('unsettled_usd_bound', 0):.6f}.", "",
              f"Lab spend to date: USD {record['lab_spend_usd']:.6f} of {record['lab_allowance_usd']:.2f}, "
              "the lab's share of G9, kept apart from production's model allowance (G30)."]
    lines += ["", "## Lab actions", ""] + [f"- {cell(a)}" for a in record["actions"] or ["none"]]
    lines += ["", "## Trace", "", f"Lab trace id `{record['trace']['lab_trace_id']}` "
              f"(environment `lab`); trace id stored by the app: {record['trace']['app_trace_id']}."]
    lines += ["", "## Step timings (seconds since the previous event)", ""]
    lines += [f"- {t['step']}: {t['seconds']}" for t in record["timings"]] or ["- none recorded"]
    if record["redacted_files"]:
        lines += ["", f"Redacted before writing: {record['redacted_files']}."]
    return "\n".join(lines) + "\n"


def run_key(path):
    stamp, _, n = path.name.partition("-")
    return stamp, int(n or 1)


def write_subject_report(options, redact):
    root = options.runs_root / options.subject
    lines = [f"# {options.subject}", "", f"Lab runs, newest first. Files: `{root}`.", "",
             "| Run | Commit | Result | Stages passed | Cost USD | Segmentation |",
             "|---|---|---|---|---|---|"]
    latest = None
    for path in sorted(root.iterdir(), key=run_key, reverse=True):
        try:
            r = json.loads((path / "run.json").read_text())
        except (OSError, ValueError):
            continue
        latest = latest or path
        passed = sum(s["status"] == "passed" for s in r["stages"])
        lines.append(f"| {r['run']} | {str(r['commit'].get('head'))[:12]} | {r['result']} | "
                     f"{passed}/{len(r['stages'])} | {r['costs']['total_usd']:.4f} | "
                     f"{r['options']['segmentation']} |")
    if latest:
        body = (latest / "report.md").read_text().splitlines()
        lines += ["", "## Latest run", ""] + [("#" + x if x.startswith("#") else x) for x in body]
    options.reports_root.mkdir(parents=True, exist_ok=True)
    (options.reports_root / f"{options.subject}.md").write_text(redact("\n".join(lines) + "\n"))
