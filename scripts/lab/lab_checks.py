"""Score each PLAN 4.1 stage from what the app recorded (docs/execution/golive/LAB.md)."""

from __future__ import annotations

from itertools import permutations
import json
import re
from urllib.parse import unquote

METRIC = "bounded-levenshtein-fraction-v1"
SAM3_MODEL = "facebook/sam3"
SUBSTITUTE = "reviewed_region"
DISPOSITIONS = {"cleared", "needs_human_review", "deferred"}
BLOCKED = {"processing_blocked", "retry_scheduled"}
# D4 is held, so its occurrence check is off and sends nothing (PLAN 2, coordinator rulings). PLAN 4.8's
# table lists GBIF only for species match (G23) and the held occurrence search. A GADM call fails on its own
# ground: PLAN 4.8 does not use GADM (coordinator ruling, 2026-09-25); it is not an occurrence request.
OCCURRENCE_KEYS = {"catalognumber", "recordedby", "occurrenceid", "institutioncode", "collectioncode",
                   "recordnumber", "eventdate", "locality"}
MUSEUM_PUBLISHED = re.compile(r'\\*"museum_published\\*"\s*:\s*true')  # S8's check ran, escaped or not
OCCURRENCE_SIGNAL = re.compile(r'\\*"occurrence\\*"\s*:\s*\\*"(?:supports|conflicts)')
IDENTITY = ("source", "provider", "source_id", "tool", "tool_id")
DOT_SEGMENT = re.compile(r"/(?!\.\.?/)[^/\s\"'?#]+/\.\./")  # "/x/../", which a client resolves to "/"
PROVENANCE = ("model_id", "provider", "prompt_version", "input_sha256", "raw_ref", "raw_sha256")
# Labels of the ten pilot slides as fractions of the frame's width, full height (S8's
# table and the images, 2026-09-23). The left box includes the barcode's printed catalog
# number; on 324-328 the locality is on a right-hand label next to the barcode.
LEFT_LABEL = [(0.0, 0.37)]
TWO_LABELS = [(0.0, 0.34), (0.62, 1.0)]
LAYOUT = {f"subject_1055263{n}": TWO_LABELS if 24 <= n <= 28 else LEFT_LABEL for n in range(21, 31)}


def label_boxes(subject):
    return LAYOUT.get(subject, LEFT_LABEL)


def check_stages(evidence, source, subject):
    snap = evidence["snapshot"]
    run, asset = snap["run"], snap["asset"]
    runs = [*(snap.get("previous_runs") or []), run]
    substituted = any(a.get("action") == SUBSTITUTE for a in evidence.get("actions") or [])
    rows = evidence.get("rows") or {}
    lookups = run.get("lookups") or []
    stages = [
        ("1", "Images in storage", images(asset, source, subject)),
        ("2", "Label segmentation", segmentation(run, runs, asset, subject, substituted)),
        ("3", "VLMs", readers(run)),
        ("4", "Raw transcripts to SQL", normalized(rows, snap)),
        ("5", "Disagreement score", disagreement(run)),
        ("6", "LLM first pass", ("not built", "no first-pass record on this commit")),
        ("7", "Agentic harness", harness(runs, lookups, evidence.get("gbif_occurrence_requests"),
                                         evidence.get("d4_blob_hits"))),
        ("8", "Queue decision", queue(run, subject)),
        ("9", "Linkage", linkage(snap, runs)),
        ("trace", "Tracing", tracing(run)),
    ]
    return [{"stage": k, "name": n, "status": s, "detail": d} for k, n, (s, d) in stages]


def verdict(phases, stages):
    if any(p["status"] == "failed" for p in phases):
        return "error"
    if any(s["status"] == "failed" for s in stages):
        return "fail"
    return "pass" if stages and all(s["status"] == "passed" for s in stages) else "incomplete"


def blocked_or_failed(run, detail):
    if run.get("stage") in BLOCKED:
        return "blocked", f"{run.get('blocker') or run.get('reasons')} at {stalled(run)}; {detail}"
    return "failed", detail


def stalled(run):
    """The step the app would run next, by its own rule; attempts count only external steps."""
    try:
        from specimen_digitization.application.domain import Run
        from specimen_digitization.application.workflow import Workflow

        return [Workflow.next_step(Run.model_validate(run))]
    except (ImportError, ValueError, KeyError, TypeError):  # another commit's model: what the app attempted
        done = set(run.get("completed_steps") or [])
        return [step for step in run.get("attempts") or {} if step not in done]


def images(asset, source, subject):
    same = asset.get("sha256") == source.get("sha256")
    named = asset.get("filename") == subject + ".jpeg"
    detail = (f"the asset's SHA-256 {'matches' if same else 'differs from'} the fetched object's; "
              f"file name {asset.get('filename')}, from {source.get('object_name')}")
    return ("passed" if same and named else "failed"), detail


def segmentation(run, runs, asset, subject, substituted):
    regions = run.get("regions") or []
    if substituted:
        blockers = [r["blocker"] for r in runs[:-1] if r.get("blocker")]
        return "substituted", f"{len(regions)} reviewer region(s) drawn by the lab after {blockers}"
    seg = run.get("segmentation") or {}
    if not regions or seg.get("model_id") != SAM3_MODEL:
        return blocked_or_failed(run, "no SAM 3 regions on the run")
    detail = f"{len(regions)} regions, revision {seg.get('model_revision')}, settings {seg.get('settings')}"
    check = run.get("coverage_check") or {}
    outcome, codes = check.get("outcome"), check.get("reason_codes") or []
    # A pass needs the lane's own check (G15), as #111 writes it on the run: outcome confirmed or unconfirmed.
    if not check:
        return "not built", detail + "; the run carries no coverage check (G15)"
    if subject not in LAYOUT:
        return "not checked", detail + f"; the lane's check reads {outcome}; outside the ten the lab has no layout"
    missing = uncovered(LAYOUT[subject], regions, asset["width"], asset["height"])
    measure = (f"the lab's measure finds label box {missing} uncovered" if missing
               else f"the lab's measure finds a distinct region on every label box {LAYOUT[subject]}")
    if outcome == "confirmed":
        return ("failed" if missing else "passed"), detail + f"; the lane's check confirmed coverage; {measure}"
    if outcome == "unconfirmed" and missing:
        return "passed", detail + f"; the lane's check caught it {codes}; {measure}"
    if outcome == "unconfirmed":
        return "not checked", (detail + f"; a false alarm: the lane's check reads unconfirmed {codes} while "
                               f"{measure}; G15 sends it to review, and the lab records it for calibration")
    return "not checked", detail + f"; the lane's check reads {outcome!r}; {measure}"


def covers(box, region, width, height):
    lo, hi = box[0] * width, box[1] * width
    across = min(hi, region["x"] + region["width"]) - max(lo, region["x"])
    down = min(height, region["y"] + region["height"]) - max(0, region["y"])
    return across > 0 and down > 0 and across * down >= 0.5 * (hi - lo) * height


def uncovered(boxes, regions, width, height):
    """Label boxes left uncovered when each box needs a region of its own."""
    fits = [[covers(box, region, width, height) for region in regions] for box in boxes]
    for chosen in permutations(range(len(regions)), len(boxes)):
        if all(fits[i][j] for i, j in enumerate(chosen)):
            return []
    return [box for i, box in enumerate(boxes) if not any(fits[i])] or list(boxes)


def readers(run):
    routes = list((run.get("profile") or {}).get("routes") or [])
    regions, observations = run.get("regions") or [], run.get("observations") or []
    if not regions:
        return blocked_or_failed(run, "no regions to read")
    missing, partial, doubled = [], [], []
    for region in regions:
        for route in routes:
            found = [o for o in observations if o["region_id"] == region["id"] and o["route_id"] == route]
            where = f"{region['id'][:8]}/{route}"
            if not found:
                missing.append(where)
            elif len(found) > 1:
                doubled.append(where)
            elif not all(found[0].get(k) for k in PROVENANCE):
                partial.append(where)
    if missing and not partial and not doubled and run.get("stage") in BLOCKED:
        return blocked_or_failed(run, f"missing {missing}")
    if missing or partial or doubled:
        return "failed", f"missing {missing}; incomplete provenance {partial}; more than one reading {doubled}"
    return "passed", f"{len(observations)} readings over {len(regions)} region(s), routes {routes}"


def normalized(rows, snap):
    """S5's data contract: readings are model_observation rows with independent = true, sharing the
    snapshot's observation ids; a row reaches its specimen only through pipeline_run.specimen_id."""
    if not rows.get("pipeline_run"):
        return "not built", f"no pipeline_run rows; tables with rows: {sorted(t for t in rows if rows[t])}"
    run = snap["run"]
    linked = any(r.get("id") == run["id"] and r.get("specimen_id") == snap["id"]
                 for r in rows.get("pipeline_run") or [])
    expected = {o["id"] for o in run.get("observations") or []}
    if not expected:
        return blocked_or_failed(run, f"no readings to project; run row linked: {linked}")
    readings = {r["id"] for r in rows.get("model_observation") or []
                if r.get("run_id") == run["id"] and r.get("independent") is True}
    detail = (f"run row linked to specimen: {linked}; {len(readings & expected)} of {len(expected)} readings "
              f"as rows; {len(readings - expected)} rows without a reading")
    return ("passed" if linked and readings == expected else "failed"), detail


def disagreement(run):
    regions = run.get("regions") or []
    transcripts = {t["region_id"]: t for t in run.get("transcripts") or []}
    if not regions or not transcripts:
        return blocked_or_failed(run, "no transcripts to score")
    scores, unscored = [], []
    for region in regions:
        t = transcripts.get(region["id"]) or {}
        if t.get("disagreement_ratio") is None or t.get("alignment_algorithm") != METRIC:
            unscored.append(region["id"][:8])
        else:
            scores.append(f"{region['id'][:8]}={t['disagreement_ratio']:.3f}")
    if unscored:
        return "failed", f"unscored regions {unscored}"
    return "passed", f"{METRIC}: {', '.join(scores)}"


def harness(runs, lookups, requests, blob_hits):
    d4, gadm, other = gbif_calls(runs)
    d4 += list(blob_hits or [])
    if requests:
        d4.append(f"{requests} requests counted at bounded_http")
    failures = []
    if d4:
        failures.append(f"D4 is held, so its occurrence check is off, yet GBIF occurrence requests appear: {d4[:6]}")
    if gadm:
        failures.append(f"GADM is not used (PLAN 4.8), yet GADM calls appear: {gadm[:6]}")
    # Reporting other GBIF calls is the lab's own choice: PLAN 4.8's table has no row for them (G5).
    reported = ([f"GBIF calls outside PLAN 4.8's table, which the lab reports for the coordinator: {other[:6]}"]
                if other else [])
    if failures:
        return "failed", "; ".join(failures + reported)
    if requests is None:
        return "not checked", "; ".join(["the runner's D4 request count is unavailable: its hook is absent", *reported])
    calls = runs[-1].get("tool_calls") or []  # #134's ToolCallRecords (harness_ledger.py)
    if calls:
        return "not checked", "; ".join([f"{len(calls)} tool calls recorded; stage 7's checks follow S4's contract",
                                         *reported])
    if reported:
        return "not checked", reported[0]
    return "not built", f"no tool-call record on this commit; deterministic lookups: {[x.get('status') for x in lookups]}"


def decoded(text):
    """Percent-decoded, lower-case text whose paths lose every "." and ".." segment, as a client sends them."""
    text, previous = unquote(str(text)).lower(), None
    while text != previous:
        previous = text
        text = DOT_SEGMENT.sub("/", text.replace("/./", "/"))
    return text


def occurrence_request(text):
    """GBIF's occurrence API named in full, or S8's occurrence check having run, in any stored text."""
    text = str(text)
    return ("api.gbif.org/v1/occurrence" in decoded(text) or bool(MUSEUM_PUBLISHED.search(text))
            or bool(OCCURRENCE_SIGNAL.search(text)))


def occurrence_blob(text):
    """A receipt's blob showing an occurrence request, as text or as a record inside it."""
    if occurrence_request(text):
        return True
    try:
        data = json.loads(text)
    except ValueError:
        return False
    return any(occurrence_record(r) for r in records_in(data) if not held_by_policy(r))


def records_in(value):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from records_in(item)
    elif isinstance(value, list):
        for item in value:
            yield from records_in(item)


def held_by_policy(record):
    return "policy" in str(record.get("outcome") or record.get("status"))  # a held call sent nothing


def identity(record):
    return " ".join(str(record.get(key) or "") for key in IDENTITY).lower()


def species_match(record):
    """PLAN 4.8's species match (G23), by tool, adapter or path; #134's evidence has a usage/<key> locator."""
    version = str(record.get("adapter_version") or record.get("tool_version") or "").lower()
    return ("taxonomy_verifier" in identity(record) or version.startswith("species-match")
            or "/v2/species/match" in decoded(json.dumps(record, default=str))
            or str(record.get("locator") or "").lower().startswith("usage/"))


def occurrence_record(record):
    """A GBIF record for the occurrence search: by name, by the decoded path without a host, or by query keys."""
    if "gbif" not in identity(record):
        return False
    keys = {str(k).lower() for part in ("arguments", "query") for k in (record.get(part) or {})}
    return ("occurrence" in identity(record) or "/v1/occurrence" in decoded(json.dumps(record, default=str))
            or bool(keys & OCCURRENCE_KEYS))


def gbif_calls(runs):
    """Every run's GBIF calls as (occurrence requests, GADM calls, others); a call held by policy sent nothing."""
    d4, gadm, other = [], [], []
    for run in runs:
        where = str(run.get("id", "?"))[:8]
        # #134: a tool call names the evidence it wrote, so a failed species match's evidence, which has no
        # locator, is known by its id.
        species_evidence = {str(c["evidence_id"]) for c in run.get("tool_calls") or []
                            if isinstance(c, dict) and c.get("evidence_id") and species_match(c)}
        records = [(f"{key}[{i}]", r) for key in ("tool_calls", "lookups") for i, r in enumerate(run.get(key) or [])]
        records += [(f"authority_results.{k}", r) for k, r in (run.get("authority_results") or {}).items()]
        records += [(f"evidence[{i}]", r) for i, r in enumerate(run.get("evidence") or [])]
        for name, record in records:
            if not isinstance(record, dict) or held_by_policy(record):
                continue
            version = str(record.get("adapter_version") or record.get("tool_version") or "").lower()
            if occurrence_request(json.dumps(record, default=str)) or occurrence_record(record):
                d4.append(f"{where}/{name}")
            elif "gbif_gadm" in identity(record) or version.startswith("gbif-gadm"):
                gadm.append(f"{where}/{name}")
            elif ("gbif" in identity(record) and not species_match(record)
                  and str(record.get("id")) not in species_evidence):
                other.append(f"{where}/{name}")
        if occurrence_request(json.dumps(run.get("authority_receipts") or {}, default=str)):
            d4.append(f"{where}/authority_receipts")
    return d4, gadm, other


def queue(run, subject):
    disposition, reasons = run.get("disposition"), run.get("reasons") or []
    if subject in LAYOUT and disposition in DISPOSITIONS:
        # All ten go to needs human review (PLAN 8, 879-883); their reasons are compared by hand.
        if disposition != "needs_human_review":
            return "failed", f"one of the ten got {disposition}, but all ten go to needs human review; {reasons}"
        if not reasons:
            return "failed", "one of the ten went to review with no reason"
        return "not checked", (f"needs human review, as expected; reasons compared by hand against "
                               f"expected-outcomes.md, a wrong one recorded as a failure: {reasons}")
    if disposition in DISPOSITIONS and (reasons or disposition == "cleared"):
        return "passed", f"{disposition}: {reasons}"
    return blocked_or_failed(run, f"stage {run.get('stage')}, disposition {disposition}, reasons {reasons}")


def linkage(snap, runs):
    asset_id, problems = snap["asset"]["id"], []
    for run in runs:
        regions = {r["id"] for r in run.get("regions") or []}
        observations = {o["id"] for o in run.get("observations") or []}
        problems += [f"region {r['id'][:8]} not on asset" for r in run.get("regions") or []
                     if r["asset_id"] != asset_id]
        problems += [f"reading {o['id'][:8]} outside regions" for o in run.get("observations") or []
                     if o["region_id"] not in regions]
        problems += [f"transcript {t['region_id'][:8]} unlinked" for t in run.get("transcripts") or []
                     if t["region_id"] not in regions or not set(t["observation_ids"]) <= observations]
    if problems:
        return "failed", "; ".join(problems[:6])
    return "passed", f"{len(runs)} run(s) link to specimen {snap['id'][:8]} and asset {asset_id[:8]}"


def tracing(run):
    trace_id = run.get("trace_id")
    if not trace_id:
        return "not built", "the run stores no trace id (Run.trace_id)"
    return "not checked", (f"trace {trace_id} stored; what it shows (DoD-5) is read once the lab holds a "
                           "Logfire read token")
