"""Decision-bound first-ten human review evidence projection; no live actions."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path

from specimen_digitization.hub_models import SAM3_MODEL

from acceptance import (
    InvalidEvidence, JOURNEY_CASES, LIVE_CASES, MODES, STATES, artifact, artifact_path,
    evaluate as full_evaluate, keys, manifest_ids, nonempty, private_manifest,
    parse_json, read_json, require, sha, skeleton as full_skeleton,
)

# Public decision metadata, frozen to the coordinator's exact canonical artifact.
# Its digest is documented in RELEASE_ACCEPTANCE.md and the CLI invocation.
APPROVED_SCOPE = {
    "version": "human-review-release-scope/v1", "status": "approved",
    "date": "2026-09-08",
    "coordinator_task": "01a082b2-c2c3-70d2-be90-7bfb622c9102",
    "source_scope": "previously approved first ten existing Firebase specimens; no substitutions",
    "user_selection": "Complete human review: process all 10, compare readings, correct and save records; defer automated classification and clearance.",
    "automated_classification": "deferred", "automated_clearance": "deferred",
    "human_review_end_to_end": "required", "specimen_count": 10,
    "total_limit_micros": 5_000_000,
    "budget_scope": "entire_first_ten_all_sessions_and_retries",
    "initial_admin_sensitive_access": False,
    "changes_infrastructure_authorization": False, "release_accepted": False,
}
APPROVED_SCOPE_SHA256 = hashlib.sha256(
    (json.dumps(APPROVED_SCOPE, sort_keys=True, indent=2) + "\n").encode()
).hexdigest()
MANUAL_CASES = (
    "HUMAN-LABEL-COVERAGE", "HUMAN-FIELD-SEPARATION",
    "HUMAN-NO-AUTOMATIC-CLEARANCE", "HUMAN-ACCESSIBLE-REVIEW",
)
REQUIRED_CASES = set(JOURNEY_CASES + LIVE_CASES)
ROUTES = {
    "handwriting-qwen": ("Qwen/Qwen3-VL-30B-A3B-Instruct", "novita"),
    "handwriting-muse": ("meta-models/Muse-Glimmer-30B", "deepinfra"),
}


def validate_scope(value):
    expected = APPROVED_SCOPE
    require(isinstance(value, dict), "Scope decision missing")
    for key, expected_value in expected.items():
        require(type(value.get(key)) is type(expected_value) and value[key] == expected_value,
                "Approved human scope changed")


def skeleton(candidate_sha, manifest_sha):
    result = full_skeleton(candidate_sha, manifest_sha)
    result["scope_sha256"] = APPROVED_SCOPE_SHA256
    result.update(release_accepted=False, full_prd_qualified=False, human_review_preflight="not_run")
    template = result["results"][0]
    result["human_results"] = [dict(template, case_id=case) for case in MANUAL_CASES]
    result["human_records"] = []
    return result


def json_artifact(root, entry):
    path = artifact_path(root, entry)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode),
                "JSON evidence must be a regular file")
        raw = stream.read(16 * 1024 * 1024 + 1)
    require(len(raw) <= 16 * 1024 * 1024, "JSON evidence exceeds size bound")
    require(hashlib.sha256(raw).hexdigest() == entry["sha256"], "Parsed evidence bytes changed")
    return parse_json(raw)


def manual_results(rows, root, candidate_sha, manifest_sha, ids):
    require(isinstance(rows, list), "Human subcriteria missing")
    seen, pending = set(), []
    for row in rows:
        require(isinstance(row, dict), "Invalid human case")
        case = row.get("case_id")
        require(case in MANUAL_CASES and case not in seen, "Unknown/duplicate human case")
        seen.add(case)
        require(row.get("candidate_sha") == candidate_sha, "Stale human case candidate")
        require(row.get("manifest_sha256") == manifest_sha, "Stale human case cohort")
        require(row.get("status") in STATES and row.get("mode") in MODES, "Invalid human case state")
        tested = row.get("specimen_ids")
        require(isinstance(tested, list) and all(isinstance(i, str) for i in tested)
                and len(set(tested)) == len(tested) and set(tested) <= ids,
                "Invalid human case specimens")
        entries = row.get("artifacts")
        require(isinstance(entries, list), "Human case evidence missing")
        for entry in entries:
            artifact(root, entry)
        if row["status"] == "passed":
            require(entries, "Passing human case needs retained evidence")
            for field in ("observer", "started_at_utc", "ended_at_utc", "command",
                          "expected", "actual", "transport"):
                require(nonempty(row.get(field)), "Passing human case metadata missing")
            require(type(row.get("exit_code")) is int and row["exit_code"] == 0,
                    "Human case command failed")
        if row["status"] != "passed" or row["mode"] != "live":
            pending.append(case)
        elif case != "HUMAN-ACCESSIBLE-REVIEW":
            require(set(tested) == ids, "Full ten human case coverage required")
    require(seen == set(MANUAL_CASES), "Missing human subcriteria")
    return pending


def literal_output(raw, observation):
    require(isinstance(raw, list) and raw, "Raw reader output missing")
    final = raw[-1]
    require(isinstance(final, dict) and final.get("kind") == "response",
            "Raw reader response missing")
    require(final.get("finish_reason") not in {"length", "max_tokens", "content_filter", "error"},
            "Reader output incomplete")
    candidates = []
    for part in final.get("parts", []):
        if not isinstance(part, dict):
            continue
        value = part.get("args") if part.get("part_kind") == "tool-call" else part.get("content")
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                continue
        if isinstance(value, dict) and "verbatim_text" in value:
            candidates.append(value)
    require(len(candidates) == 1, "Raw literal output missing or ambiguous")
    output = candidates[0]
    lines = output.get("lines")
    require(isinstance(lines, list) and lines and all(isinstance(line, str) for line in lines),
            "Raw literal lines missing")
    require("\n".join(lines) == output.get("verbatim_text") == observation.get("literal_text"),
            "Literal text differs from retained raw output")
    # LiteralTranscription defines this optional field with an empty-list default.
    spans = output.get("unreadable_spans", [])
    require(isinstance(spans, list)
            and all(isinstance(value, str) for value in spans)
            and spans == observation.get("unreadable_spans"),
            "Uncertainty differs from raw output")


def human_records(rows, manifest, manifest_sha, root, deployment):
    require(isinstance(rows, list), "Human records missing")
    if not rows:
        return False
    require(deployment.get("sam_model_revision") == SAM3_MODEL.revision,
            "Unapproved SAM model revision")
    expected = {s["specimen_id"]: s for s in manifest["specimens"]}
    require(len(rows) == 10, "Full ten human records required")
    seen = set()
    for row in rows:
        keys(row, ("specimen_id", "original", "before_review", "after_save", "after_reload",
                   "sam_receipt", "raw_observations", "masks", "crops"))
        ident = row["specimen_id"]
        require(ident in expected and ident not in seen, "Duplicate or outside-cohort record")
        seen.add(ident)
        approved = expected[ident]
        original = approved["source_objects"][approved["application_source"]["source_object_index"]]
        artifact(root, row["original"])
        require(row["original"]["sha256"] == original["sha256"], "Wrong original bytes")
        before, saved, reopened = [json_artifact(root, row[key]) for key in
                                   ("before_review", "after_save", "after_reload")]
        for value in (before, saved, reopened):
            require(isinstance(value, dict) and value.get("specimen_id") == ident,
                    "Workspace specimen mismatch")
            require(all(value.get(key) == approved[key] for key in ("organization_id", "collection_id")),
                    "Workspace collection scope mismatch")
            asset, run = value.get("asset", {}), value.get("run", {})
            require(asset.get("sha256") == original["sha256"]
                    and asset.get("size_bytes") == original["size_bytes"], "Original binding changed")
            require(nonempty(run.get("id")), "Retained run identity missing")
            profile = run.get("profile", {})
            require(profile.get("synthetic") is False, "Synthetic output cannot qualify")
            require(profile.get("institutional_policy_approved") is False
                    and profile.get("semantics_confirmed") is False
                    and run.get("human_approved") is False and run.get("disposition") is None,
                    "Institutional clearance is not qualified")
            require(run.get("stage") == "processing_blocked"
                    and run.get("blocker") == "pilot_evidence_review_required",
                    "Actual reader completion required; operational block cannot qualify")
        require(type(before.get("revision")) is int and type(saved.get("revision")) is int
                and saved["revision"] > before["revision"], "Saved revision did not advance")
        require(nonempty(saved.get("record_version_id"))
                and saved["record_version_id"] != before.get("record_version_id"),
                "Saved record version did not advance")
        for key in ("revision", "record_version_id", "asset", "run", "events"):
            require(saved.get(key) == reopened.get(key), "Saved record did not survive reload")
        require(saved["run"].get("coverage_confirmed") is True, "Human label coverage unconfirmed")
        events = saved.get("events")
        require(isinstance(events, list) and any(isinstance(e, dict)
                and str(e.get("action", "")).startswith("review") and nonempty(e.get("reason"))
                and e not in before.get("events", [])
                for e in events), "New saved human review history missing")
        require(saved["run"].get("id") == before["run"].get("id")
                and saved["run"].get("observations") == before["run"].get("observations")
                and saved["run"].get("regions") == before["run"].get("regions"),
                "Review replaced independent raw observations or regions")
        receipt = json_artifact(root, row["sam_receipt"])
        require(isinstance(receipt, dict) and receipt.get("model_id") == "facebook/sam3"
                and receipt.get("model_revision") == deployment.get("sam_model_revision")
                and sha(receipt.get("model_revision"), 40)
                and receipt.get("checkpoint_sha256") == deployment.get("sam_checkpoint_sha256")
                and sha(receipt.get("checkpoint_sha256"))
                and receipt.get("manifest_sha256") == manifest_sha,
                "SAM provenance mismatch")
        checkpoint_files = receipt.get("checkpoint_files")
        require(isinstance(checkpoint_files, dict) and checkpoint_files
                and all(nonempty(name) and sha(value) for name, value in checkpoint_files.items()),
                "Checkpoint file evidence missing")
        require(hashlib.sha256(json.dumps(checkpoint_files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                == receipt["checkpoint_sha256"], "Checkpoint file map digest mismatch")
        require(checkpoint_files.get("config.json") == deployment.get("sam_config_sha256"),
                "SAM config provenance mismatch")
        source = receipt.get("source", {})
        require(all(source.get(key) == original[key] for key in
                    ("bucket", "object_name", "generation", "sha256", "size_bytes")),
                "SAM original source mismatch")
        regions = before["run"].get("regions")
        require(isinstance(regions, list) and 0 < len(regions) <= 64
                and receipt.get("regions") == regions, "SAM region evidence incomplete")
        require(all(isinstance(r, dict) and r.get("method") == "sam3"
                    and r.get("version") == SAM3_MODEL.revision for r in regions),
                "Retained region uses an unapproved segmentation method or revision")
        region_ids = [r.get("id") for r in regions]
        require(all(nonempty(i) for i in region_ids) and len(set(region_ids)) == len(region_ids),
                "Invalid retained regions")
        masks = receipt.get("masks")
        require(isinstance(row["masks"], dict) and set(row["masks"]) == set(region_ids)
                and isinstance(masks, list) and len(masks) == len(regions),
                "Retained SAM mask bytes missing")
        for region, mask in zip(regions, masks, strict=True):
            entry = row["masks"][region["id"]]
            artifact(root, entry)
            require(entry["sha256"] == mask.get("sha256")
                    and region.get("mask_ref") == f"{mask.get('sha256')}:{mask.get('generation')}"
                    and mask.get("encoding") == "binary-png-original-pixels",
                    "SAM mask binding mismatch")
        observations = before["run"].get("observations")
        require(isinstance(observations, list) and len(observations) == 2 * len(regions),
                "Two readers required for every retained region")
        raw_entries = row["raw_observations"]
        require(isinstance(raw_entries, dict), "Raw observation artifacts missing")
        require(isinstance(row["crops"], dict), "Reader crop evidence missing")
        pairs, observation_ids = set(), set()
        for observation in observations:
            require(isinstance(observation, dict), "Invalid observation")
            obs_id, route = observation.get("id"), observation.get("route_id")
            require(nonempty(obs_id) and obs_id not in observation_ids and obs_id in raw_entries,
                    "Observation identity missing/duplicate")
            observation_ids.add(obs_id)
            region_id = observation.get("region_id")
            require(region_id in region_ids and route in ROUTES and (region_id, route) not in pairs,
                    "Independent reader route missing/duplicated")
            pairs.add((region_id, route))
            require((observation.get("model_id"), observation.get("provider")) == ROUTES[route],
                    "Unapproved reader route")
            require(observation.get("completion_state") == "validated_output"
                    and observation.get("finish_state") not in {"length", "max_tokens", "content_filter", "error"}
                    and nonempty(observation.get("literal_text"))
                    and sha(observation.get("input_sha256")) and sha(observation.get("prompt_version")),
                    "Reader output or provenance incomplete")
            require(obs_id in row["crops"], "Reader crop bytes missing")
            crop = row["crops"][obs_id]
            artifact(root, crop)
            require(crop["sha256"] == observation["input_sha256"], "Reader crop digest mismatch")
            entry = raw_entries[obs_id]
            require(entry.get("sha256") == observation.get("raw_sha256"), "Raw reader digest mismatch")
            literal_output(json_artifact(root, entry), observation)
        require(set(raw_entries) == observation_ids == set(row["crops"]), "Raw observation/crop set differs")
    require(seen == set(expected), "Full ten human records required")
    return True


def evaluate(manifest, manifest_sha, report, root, candidate_sha, scope_decision):
    validate_scope(scope_decision)
    require(report.get("scope_sha256") == APPROVED_SCOPE_SHA256, "Wrong approved scope pin")
    full = full_evaluate(manifest, manifest_sha, report, root, candidate_sha)
    pending = [case for case in full["pending"] if case in REQUIRED_CASES or not case.startswith("PRD-")]
    pending += manual_results(report.get("human_results"), root, candidate_sha,
                              manifest_sha, manifest_ids(manifest))
    if not human_records(report.get("human_records"), manifest, manifest_sha, root, report["deployment"]):
        pending.append("HUMAN-RECORDS")
    return {
        **full, "scope": "human-review-first-ten/v1", "scope_sha256": APPROVED_SCOPE_SHA256,
        "human_review_preflight": "incomplete" if pending else "ready_for_independent_review",
        "full_prd_preflight": full["evidence_preflight"], "full_prd_pending": full["pending"],
        "full_prd_qualified": False, "release_accepted": False, "pending": pending,
        "evidence_preflight": "incomplete" if pending else "ready_for_independent_review",
        "deferred_capabilities": ["automated_classification", "automated_clearance"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--approved-manifest-sha256", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--scope-decision", type=Path, required=True)
    parser.add_argument("--approved-scope-sha256", required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--evidence-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        require(args.approved_scope_sha256 == APPROVED_SCOPE_SHA256, "Scope authority changed")
        scope = private_manifest(args.scope_decision, args.approved_scope_sha256)
        validate_scope(scope)
        require(sha(args.approved_manifest_sha256) and sha(args.candidate_sha, 40), "Source pins missing")
        manifest = private_manifest(args.manifest, args.approved_manifest_sha256)
        manifest_ids(manifest)
        if args.report is None:
            print(json.dumps(skeleton(args.candidate_sha, args.approved_manifest_sha256), indent=2))
            return 0
        result = evaluate(manifest, args.approved_manifest_sha256, read_json(args.report),
                          args.evidence_root, args.candidate_sha, scope)
        print(json.dumps(result, indent=2))
        return 1 if result["pending"] else 0
    except (InvalidEvidence, OSError, ValueError, TypeError, KeyError, AttributeError):
        print(json.dumps({"human_review_preflight": "invalid", "release_accepted": False,
                          "full_prd_qualified": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
