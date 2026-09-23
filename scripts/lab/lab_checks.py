"""Score each PLAN 4.1 stage from what the app recorded (docs/execution/golive/LAB.md)."""

from __future__ import annotations

METRIC = "bounded-levenshtein-fraction-v1"
SAM3_MODEL = "facebook/sam3"
SUBSTITUTE = "reviewed_region"
DISPOSITIONS = {"cleared", "needs_human_review", "deferred"}
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
        ("7", "Agentic harness", ("not built", "no tool-call record on this commit; "
                                  f"deterministic lookups: {[x['status'] for x in lookups]}")),
        ("8", "Queue decision", queue(run)),
        ("9", "Linkage", linkage(snap, runs)),
        ("trace", "Tracing", ("not built", "the run stores no trace id on this commit")),
    ]
    return [{"stage": k, "name": n, "status": s, "detail": d} for k, n, (s, d) in stages]


def verdict(phases, stages):
    if any(p["status"] == "failed" for p in phases):
        return "error"
    if any(s["status"] == "failed" for s in stages):
        return "fail"
    return "pass" if all(s["status"] == "passed" for s in stages) else "incomplete"


def blocked_or_failed(run, detail):
    if run.get("stage") == "processing_blocked":
        return "blocked", f"{run.get('blocker')} at {stalled(run)}; {detail}"
    return "failed", detail


def stalled(run):
    """Steps the app attempted but never completed: where a blocked run stopped."""
    done = set(run.get("completed_steps") or [])
    return [step for step in run.get("attempts") or {} if step not in done]


def images(asset, source, subject):
    same = asset.get("sha256") == source.get("sha256")
    named = asset.get("filename") == subject + ".jpeg"
    detail = f"asset {asset.get('sha256', '')[:12]} from {source.get('object_name')}"
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
    if subject not in LAYOUT:
        return "passed", detail + "; label coverage not checked: no known layout for this subject"
    missing = [b for b in LAYOUT[subject] if not covered(b, regions, asset["width"], asset["height"])]
    if missing:
        return "failed", detail + f"; no region covers label box {missing}"
    return "passed", detail + f"; covers every label box {LAYOUT[subject]}"


def covered(box, regions, width, height):
    lo, hi = box[0] * width, box[1] * width
    for r in regions:
        across = min(hi, r["x"] + r["width"]) - max(lo, r["x"])
        down = min(height, r["y"] + r["height"]) - max(0, r["y"])
        if across > 0 and down > 0 and across * down >= 0.5 * (hi - lo) * height:
            return True
    return False


def readers(run):
    routes = list((run.get("profile") or {}).get("routes") or [])
    regions, observations = run.get("regions") or [], run.get("observations") or []
    if not regions:
        return blocked_or_failed(run, "no regions to read")
    missing, partial = [], []
    for region in regions:
        for route in routes:
            found = [o for o in observations if o["region_id"] == region["id"] and o["route_id"] == route]
            if not found:
                missing.append(f"{region['id'][:8]}/{route}")
            elif not all(o.get(k) for o in found for k in PROVENANCE):
                partial.append(f"{region['id'][:8]}/{route}")
    if missing and not partial and run.get("stage") == "processing_blocked":
        return blocked_or_failed(run, f"missing {missing}")
    if missing or partial:
        return "failed", f"missing {missing}; incomplete provenance {partial}"
    return "passed", f"{len(observations)} readings over {len(regions)} region(s), routes {routes}"


def normalized(rows, snap):
    """S5's data contract: readings are model_observation rows with independent = true, sharing the
    snapshot's observation ids; a row reaches its specimen only through pipeline_run.specimen_id."""
    observations = rows.get("model_observation") or []
    if not observations:
        return "not built", f"no observation rows; tables with rows: {sorted(t for t in rows if rows[t])}"
    run = snap["run"]
    linked = any(r.get("id") == run["id"] and r.get("specimen_id") == snap["id"]
                 for r in rows.get("pipeline_run") or [])
    readings = {r["id"] for r in observations if r.get("run_id") == run["id"] and r.get("independent") is True}
    expected = {o["id"] for o in run.get("observations") or []}
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


def queue(run):
    disposition, reasons = run.get("disposition"), run.get("reasons") or []
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
