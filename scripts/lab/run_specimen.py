"""Run one pilot specimen through the lane on this workstation (docs/execution/golive/LAB.md)."""

from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import traceback
from urllib.parse import parse_qsl, unquote, urlsplit

import lab_checks

BUCKET = "specimen-digitization.firebasestorage.app"
PREFIX = "microscopic-slides/"
# USD per million tokens, input then output (docs/execution/LIVE_PILOT_COST.md 42-47).
PRICES = {"handwriting-qwen": (0.20, 0.70), "handwriting-muse": (0.30, 1.20)}
# What PLAN 7.7 keeps out of shared logs and issues: token values, instance addresses (the app pins the
# SAM 3 endpoint into a run's dependencies, so it reaches snapshot.json) and billing ids. Private values
# such as the administrator's UID come from the file LAB_REDACT_VALUES_FILE names.
TOKEN_VARIABLES = ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACEHUB_API_TOKEN", "LOGFIRE_TOKEN",
                   "LOGFIRE_READ_TOKEN", "SPECIMEN_SAM3_ENDPOINT", "SPECIMEN_SAM3_LAB_TOKEN",
                   "SPECIMEN_GOOGLE_MAPS_API_KEY", "HF_BILL_TO")
SHAPES = re.compile(
    r"hf_[A-Za-z0-9]{16,}|(?<=Bearer )[A-Za-z0-9._~+/=-]+|ya29\.[A-Za-z0-9._-]+"
    r"|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"
    r"|(?:https?://)?[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.run\.app(?:/[A-Za-z0-9._~/%-]*)?"  # stops at quotes
    r"|[A-Za-z0-9._%+-]+(?:@|%40)[A-Za-z0-9.-]+\.[A-Za-z]{2,}"  # an email, also percent-encoded
    r"|AIza[0-9A-Za-z_-]{35}|pylf_[A-Za-z0-9_]{8,}",  # Google API keys and Logfire tokens
    re.I,
)
LOGFIRE_ORG = re.compile(r"(logfire-(?:us|eu)\.pydantic\.dev/)[^/\s\"']+", re.I)
# Always redacted, even with a stray invalid byte; any other artifact is redacted when it decodes as UTF-8.
TEXT_SUFFIXES = {".json", ".jsonl", ".md", ".txt", ".log", ".csv", ".html", ".xml"}
MIN_VALUE = 3  # a shorter private value is never matched
REPOSITORY = Path(__file__).resolve().parents[2]
PRIVATE_ROOT = Path.home() / "specimen-release-private"  # PLAN 840: private artifacts, never in a repository
# Fields that name a person, redacted by field wherever they appear (PLAN 7.7): the snapshot's uploader,
# actors and classification_selection.actor_id, and the SQL columns, including SourceAsset.uploaderUid and
# ProfileVersion.approvedBy.
PERSON_FIELDS = {"uploader", "actor", "actor_id", "actor_uid", "created_by", "uid", "user_id", "uploader_uid",
                 "approved_by"}
# Until production's reserve-then-settle ledger lands, every paid attempt whose usage the run did not
# settle stays reserved at the full per-call bound: an unknown outcome (coordinator, 2026-09-23) and,
# since #86, a call that returned and then failed with a known blocker, whose usage the workflow does
# not record. The coordinator's ruling names the bound, not a figure: the lab's figure is the readers' and
# extraction's usage limit (production.py, total_tokens_limit=16000) at the highest known price, a worst case
# for the call's cost that sits below PLAN 4.3's reservation floor of 20,000 micro-dollars per request. A run
# that cannot be priced once its lane started is held whole at --max-run-usd. SAM 3 on this workstation is free.
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
    parser.add_argument("--report-only", action="store_true",
                        help="rebuild the subject report from the run folders, for example after a verdict.md")
    return parser.parse_args(argv)


class Redactor:
    """PLAN 7.7's categories, in any case. The private values come from the caller, which read the values
    file once (values_file); the redactor never reads a file itself."""

    def __init__(self, env, values=()):
        found = {(env.get(name) or "").strip() for name in TOKEN_VARIABLES} | {v.strip() for v in values}
        found = {v for v in found if len(v) >= MIN_VALUE}
        longest_first = sorted((v for v in found if len(v) >= 8), key=len, reverse=True)
        self.patterns = [re.compile(re.escape(v), re.I) for v in longest_first]
        # A short value is matched as a whole word, so it cannot mangle ordinary text.
        self.patterns += [re.compile(rf"(?<![\w-]){re.escape(v)}(?![\w-])", re.I) for v in found if len(v) < 8]
        try:
            home = str(Path.home())
        except RuntimeError:
            home = ""
        # The account name in a home path can equal the Logfire organization slug (PLAN 7.7).
        self.home = re.compile(re.escape(home) + r"(?![\w.-])") if len(home) > 1 else None

    def __call__(self, text):
        if self.home:
            text = self.home.sub("~", text)
        for pattern in self.patterns:
            text = pattern.sub("[redacted]", text)
        return SHAPES.sub("[redacted]", LOGFIRE_ORG.sub(r"\1[redacted]", text))


def redact_people(value):
    if isinstance(value, dict):
        return {k: ("[redacted]" if k in PERSON_FIELDS and v else redact_people(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_people(v) for v in value]
    return value


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


def values_file(name):
    """The private values the redactor needs, and any reason to refuse. The file must be under
    ~/specimen-release-private/ (PLAN 840): its location is checked before any read, and it is read once,
    from the resolved path."""
    if not name:
        return set(), ["LAB_REDACT_VALUES_FILE is not set"]
    path = Path(name).expanduser().resolve()
    if PRIVATE_ROOT.expanduser().resolve() not in path.parents:
        return set(), [f"LAB_REDACT_VALUES_FILE must be under {PRIVATE_ROOT}"]
    try:
        text = path.read_text()
    except (OSError, UnicodeDecodeError):
        return set(), ["LAB_REDACT_VALUES_FILE is unreadable"]
    if not text.strip():
        return set(), ["LAB_REDACT_VALUES_FILE is empty"]
    values = {line.strip() for line in text.splitlines() if len(line.strip()) >= MIN_VALUE}
    if not values:
        return set(), [f"LAB_REDACT_VALUES_FILE has no value of at least {MIN_VALUE} characters"]
    return values, []


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
            data = json.dumps(redact_people(data), indent=2, ensure_ascii=False, default=str)
        if isinstance(data, str):
            data = data.encode()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:  # an image or other binary file is written as it came
            text = data.decode("utf-8", errors="replace") if target.suffix.lower() in TEXT_SUFFIXES else None
        if text is not None:
            clean = self.redact(text)
            if clean != text:
                self.record["redacted_files"].append(name)
            data = clean.encode()
        target.write_bytes(data)

    def failed(self, name, exc):
        """A failure outside any phase, such as the lane's teardown: recorded, never lost."""
        self.record["phases"].append({"name": name, "status": "failed", "seconds": 0.0,
                                      "error": self.redact(f"{type(exc).__name__}: {exc}")})
        self.log.write(self.redact(traceback.format_exc()))

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


def occurrence_request(url, params=None):
    """A request to GBIF's occurrence API as a client sends it: the host in any case, the path percent-decoded
    without dot segments, and occurrence query keys in the parameters or in the URL."""
    parts = urlsplit(str(url))
    keys = query_keys(params) | query_keys(parts.query)
    return unquote(parts.hostname or "").lower() == "api.gbif.org" and (
        lab_checks.decoded(parts.path).startswith("/v1/occurrence") or bool(keys & lab_checks.OCCURRENCE_KEYS))


def query_keys(params):
    if isinstance(params, bytes):
        params = params.decode("utf-8", errors="replace")
    if isinstance(params, str):
        return {key.lower() for key, _ in parse_qsl(params, keep_blank_values=True)}
    if isinstance(params, dict):
        return {str(key).lower() for key in params}
    if isinstance(params, (list, tuple)):
        return {str(pair[0]).lower() for pair in params if isinstance(pair, (list, tuple)) and pair}
    return set()


@contextmanager
def count_gbif_occurrence(record):
    """D4 is held, so its occurrence check sends nothing. GBIF reads leave through bounded_http, whose
    request is counted here in the parent before the child process sends it; injected httpx clients are
    counted too. Without the hook the count is None, which stage 7 reads as not checked."""
    import httpx

    try:
        from specimen_digitization.application import http_effect
    except ImportError:
        http_effect = None
    bounded = getattr(http_effect, "bounded_http", None)
    record["gbif_occurrence_requests"] = 0 if bounded else None
    sync_send, async_send = httpx.Client.send, httpx.AsyncClient.send

    def count(url, params=None):
        if occurrence_request(url, params) and record["gbif_occurrence_requests"] is not None:
            record["gbif_occurrence_requests"] += 1

    def counted_bounded(url, *args, **kwargs):
        count(url, kwargs.get("params"))
        return bounded(url, *args, **kwargs)

    def counted_send(self, request, *args, **kwargs):
        count(request.url)
        return sync_send(self, request, *args, **kwargs)

    async def counted_async_send(self, request, *args, **kwargs):
        count(request.url)
        return await async_send(self, request, *args, **kwargs)

    if bounded:
        http_effect.bounded_http = counted_bounded
    httpx.Client.send, httpx.AsyncClient.send = counted_send, counted_async_send
    try:
        yield
    finally:
        httpx.Client.send, httpx.AsyncClient.send = sync_send, async_send
        if bounded:
            http_effect.bounded_http = bounded


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
    values, problems = values_file(env.get("LAB_REDACT_VALUES_FILE"))  # located first, then read once
    if not options.report_only:
        problems += preflight(options, env, loadavg)
    if problems:
        print("refused: " + "; ".join(problems), file=sys.stderr)
        return 3
    redact = Redactor(env, values)
    if options.report_only:  # a person's verdict reaches the subject report without another run
        write_subject_report(options, redact)
        print(f"rebuilt the report of {options.subject}")
        return 0
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
    lane_started = priced = False
    try:
        source = evidence = None
        with run.phase("fetch"):
            data, meta = fetch(options.subject)
            source = dict(meta, size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
            run.write(f"inputs/{options.subject}.jpeg", data)
            run.write("inputs/source.json", source)
        record["source"] = source
        if source and not options.dry_run:
            try:
                with ExitStack() as stack, lab_trace(options, record, redact), count_gbif_occurrence(record):
                    specimen_id = actions = None
                    with run.phase("ingest"):
                        lane = stack.enter_context(lane_factory(path / "state", options, env))
                        lane_started = True  # completing the upload starts processing, so paid calls may run
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
            except Exception as exc:  # the lane's teardown: the run is still priced, scored and written
                run.failed("teardown", exc)
        if evidence:
            with run.phase("check"):
                record["costs"] = price(evidence["snapshot"])  # before scoring, so a failed check keeps it
                priced = True
                record["timings"] = timings(evidence["snapshot"])
                evidence["gbif_occurrence_requests"] = record.get("gbif_occurrence_requests")
                evidence["d4_blob_hits"] = [name for name, blob in evidence["artifacts"].items()
                                            if name.startswith("receipts/") and lab_checks.occurrence_blob(
                                                blob.decode("utf-8", errors="replace"))]
                record["stages"] = lab_checks.check_stages(evidence, source, options.subject)
                if record["costs"]["total_usd"] > options.max_run_usd:
                    record["stages"].append({"stage": "cost", "name": "Run cost", "status": "failed",
                                             "detail": f"above --max-run-usd {options.max_run_usd}"})
    finally:
        if lane_started and not priced:
            record["costs"] = {"total_usd": options.max_run_usd, "held_at_run_bound": True}
        code = finish(options, run, clock)
    return code


def finish(options, run, clock):
    """run.json, the run's report and the subject report, written whatever happened before."""
    record = run.record
    # The lab's running tally against its share of G9; production's ledger never sees lab calls (G30).
    record["lab_spend_usd"] = recorded_spend(options.runs_root) + record["costs"]["total_usd"]
    record["lab_allowance_usd"] = options.lab_allowance_usd
    record["phases"].append({"name": "report", "status": "passed", "seconds": 0.0})
    record["result"] = "dry-run" if options.dry_run and record.get("source") else lab_checks.verdict(
        record["phases"], record["stages"])
    record["finished_at"] = clock().isoformat()
    try:
        run.write("run.json", record)
        run.write("report.md", render(record))
        write_subject_report(options, run.redact)
    finally:
        run.log.close()
    print(f"{record['result']}: {run.path}")
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
        label = s["name"] if s["stage"] in ("trace", "cost", "d4") else f"{s['stage']} {s['name']}"
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
              *(["The run could not be priced after its lane started, so it is held whole at --max-run-usd.", ""]
                if costs.get("held_at_run_bound") else []),
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
    lines = [f"# {options.subject}", "", f"Lab runs, newest first. Files: `{root}`. A person's verdict lives in "
             "the run's `verdict.md`, which the runner never writes.", "",
             "| Run | Commit | Result | Stages passed | Cost USD | Segmentation | Person's verdict |",
             "|---|---|---|---|---|---|---|"]
    latest, verdicts = None, []
    for path in sorted(root.iterdir(), key=run_key, reverse=True):
        try:
            r = json.loads((path / "run.json").read_text())
        except (OSError, ValueError):
            continue
        latest = latest or path
        passed = sum(s["status"] == "passed" for s in r["stages"])
        try:
            verdict = (path / "verdict.md").read_bytes().decode("utf-8").strip()
        except FileNotFoundError:
            verdict = ""
        except UnicodeDecodeError:
            verdict = "(verdict.md is not UTF-8 text: save it as UTF-8, then rebuild with --report-only)"
        except OSError:
            verdict = "(verdict.md cannot be read: fix it, then rebuild with --report-only)"
        if verdict:
            verdicts += ["", f"### {r['run']}", ""] + [("###" + x if x.startswith("#") else x)
                                                       for x in verdict.splitlines()]
        lines.append(f"| {r['run']} | {str(r['commit'].get('head'))[:12]} | {r['result']} | "
                     f"{passed}/{len(r['stages'])} | {r['costs']['total_usd']:.4f} | "
                     f"{r['options']['segmentation']} | "
                     f"{cell(verdict.splitlines()[0].lstrip('# ')) if verdict else '—'} |")
    if verdicts:
        lines += ["", "## Verdicts recorded by a person"] + verdicts
    if latest:
        try:
            body = (latest / "report.md").read_text().splitlines()
        except (OSError, ValueError):
            body = ["(report.md is missing or unreadable)"]
        lines += ["", "## Latest run", ""] + [("#" + x if x.startswith("#") else x) for x in body]
    options.reports_root.mkdir(parents=True, exist_ok=True)
    (options.reports_root / f"{options.subject}.md").write_text(redact("\n".join(lines) + "\n"))


def fetch_gcs(subject):
    from google.cloud import storage

    name = PREFIX + subject + ".jpeg"
    blob = storage.Client(project="specimen-digitization").bucket(BUCKET).get_blob(name, timeout=60)
    if blob is None:
        raise FileNotFoundError(f"gs://{BUCKET}/{name}")
    return blob.download_as_bytes(timeout=120), {
        "bucket": BUCKET, "object_name": name, "generation": str(blob.generation),
        "md5": blob.md5_hash, "media_type": blob.content_type,
    }


def git_commit():
    root = Path(__file__).resolve().parents[2]

    def git(*args):
        return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True).stdout.strip()

    return {"head": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain")),
            "origin_main_base": git("merge-base", "HEAD", "origin/main")}


def main(argv=None):
    options = parse_args(argv)
    os.environ["APP_ENV"] = "lab"
    if options.segmentation == "reviewed-region":
        for name in ("SPECIMEN_SAM3_ENDPOINT", "SPECIMEN_SAM3_REVISION"):
            os.environ.pop(name, None)
    import lab_lane

    return execute(options, fetch=fetch_gcs, lane_factory=lab_lane.production_lane, env=os.environ,
                   clock=lambda: datetime.now(timezone.utc), loadavg=os.getloadavg, commit=git_commit)


if __name__ == "__main__":
    sys.exit(main())
