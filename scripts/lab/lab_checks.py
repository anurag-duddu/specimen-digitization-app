"""Score each PLAN 4.1 stage from what the app recorded (docs/execution/golive/LAB.md)."""

from __future__ import annotations

from itertools import permutations
import json
import re

METRIC = "bounded-levenshtein-fraction-v1"
SAM3_MODEL = "facebook/sam3"
SUBSTITUTE = "reviewed_region"
DISPOSITIONS = {"cleared", "needs_human_review", "deferred"}
BLOCKED = {"processing_blocked", "retry_scheduled"}
# D4 is held, so its occurrence check is off and sends nothing (PLAN 2, coordinator rulings). A request
# shows as the occurrence API, an occurrence query, or S8's markers (GEOREFERENCING.md 376-394).
D4_MARKERS = re.compile(r"/v1/occurrence|\bcatalogNumber\b|\brecordedBy\b|occurrence|museum_published", re.I)
D4_RECORDS = ("tool_calls", "lookups", "authority_results", "authority_receipts", "evidence")
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
        ("7", "Agentic harness", harness(runs, lookups)),
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
    status = (run.get("coverage_check") or {}).get("status")
    if subject in LAYOUT:
        missing = uncovered(LAYOUT[subject], regions, asset["width"], asset["height"])
        measure = (f"the lab's measure finds label box {missing} uncovered" if missing
                   else f"the lab's measure finds a distinct region on every label box {LAYOUT[subject]}")
    else:
        missing, measure = [], "label coverage not checked by the lab: no known layout for this subject"
    # A pass needs the lane's own check (G15, DATA_CONTRACT.md 612); the lab's boxes are ground truth.
    if status is None:
        return "not built", detail + f"; the run carries no coverage check (G15); {measure}"
    if status == "passed":
        return ("failed" if missing else "passed"), detail + f"; the lane's check passed; {measure}"
    if status == "failed":
        return "passed", detail + f"; the lane's check failed and sent the record to review; {measure}"
    return "not checked", detail + f"; the lane's check did not run ({status}); {measure}"


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


def harness(runs, lookups):
    hits = [f"{run.get('id', '?')[:8]}/{key}" for run in runs for key in D4_RECORDS
            if D4_MARKERS.search(json.dumps(run.get(key) or [], default=str))]
    if hits:
        return "failed", f"D4 is held, so its occurrence check is off, yet GBIF occurrence requests appear in {hits[:6]}"
    calls = runs[-1].get("tool_calls") or []
    if calls:
        return "not checked", f"{len(calls)} tool calls recorded; stage 7's checks follow S4's contract"
    return "not built", f"no tool-call record on this commit; deterministic lookups: {[x['status'] for x in lookups]}"


def queue(run, subject):
    disposition, reasons = run.get("disposition"), run.get("reasons") or []
    if subject in LAYOUT and disposition in DISPOSITIONS:
        # All ten go to needs human review (PLAN 8, 879-883); their reasons are compared by hand.
        if disposition != "needs_human_review":
            return "failed", f"one of the ten got {disposition}, but all ten go to needs human review; {reasons}"
        return "not checked", (f"needs human review, as expected; reasons compared by hand against "
                               f"expected-outcomes.md: {reasons}")
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
