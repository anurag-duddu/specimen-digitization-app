"""Authored fixtures for the approved human scope; never live acceptance proof."""

import copy
import hashlib
import json
from pathlib import Path

import pytest
from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelResponse, ToolCallPart

from acceptance import InvalidEvidence, file_digest
from human_review import evaluate, literal_output
from specimen_digitization.hub_models import SAM3_MODEL
from specimen_digitization.transcription import LiteralTranscription
from test_acceptance import CANDIDATE, MANIFEST_SHA, claimed_live_report, manifest


MANUAL = (
    "HUMAN-LABEL-COVERAGE", "HUMAN-FIELD-SEPARATION",
    "HUMAN-NO-AUTOMATIC-CLEARANCE", "HUMAN-ACCESSIBLE-REVIEW",
)
ROUTES = {
    "handwriting-qwen": ("Qwen/Qwen3-VL-30B-A3B-Instruct", "novita"),
    "handwriting-muse": ("meta-models/Muse-Glimmer-30B", "deepinfra"),
}


def decision():
    return {
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


SCOPE_SHA = hashlib.sha256((json.dumps(decision(), sort_keys=True, indent=2) + "\n").encode()).hexdigest()

def write(root, name, value):
    path = root / name
    path.write_text(json.dumps(value))
    return {"path": name, "sha256": file_digest(path)}


def packet(root):
    source = manifest()
    report = claimed_live_report(root)
    report["scope_sha256"] = SCOPE_SHA
    report["human_results"] = []
    for case in MANUAL:
        report["human_results"].append(dict(copy.deepcopy(report["results"][-1]), case_id=case))
    report["human_records"] = []
    checkpoint_files = {"model.safetensors": "a" * 64, "config.json": "e" * 64}
    checkpoint_sha = hashlib.sha256(json.dumps(checkpoint_files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    report["deployment"]["sam_checkpoint_sha256"] = checkpoint_sha
    report["deployment"]["sam_model_revision"] = SAM3_MODEL.revision
    for item in source["specimens"]:
        ident = item["specimen_id"]
        original = root / (ident + ".png")
        original.write_bytes(("authored fixture original " + ident).encode())
        original_sha = file_digest(original)
        item["source_objects"][0].update(sha256=original_sha, size_bytes=original.stat().st_size)
        item["application_source"].update(sha256=original_sha, size_bytes=original.stat().st_size, blob_ref=original_sha + ":2")
        mask = root / (ident + "-mask.png")
        mask.write_bytes(("authored mask " + ident).encode())
        mask_sha = file_digest(mask)
        crop = root / (ident + "-crop.png")
        crop.write_bytes(("authored crop " + ident).encode())
        crop_sha = file_digest(crop)
        region = {"id": ident + "-region", "method": "sam3", "version": SAM3_MODEL.revision, "mask_ref": mask_sha + ":3"}
        observations, raws, crops = [], {}, {}
        for route, (model, provider) in ROUTES.items():
            obs_id = ident + route
            output = {"verbatim_text": "Literal\n[unreadable]", "lines": ["Literal", "[unreadable]"], "unreadable_spans": ["[unreadable]"]}
            raw = write(root, obs_id + ".json", [{"kind": "response", "finish_reason": "stop", "parts": [{"part_kind": "tool-call", "args": output}]}])
            raws[obs_id] = raw
            crops[obs_id] = {"path": crop.name, "sha256": crop_sha}
            observations.append({
                "id": obs_id, "region_id": region["id"], "route_id": route,
                "model_id": model, "provider": provider, "completion_state": "validated_output",
                "finish_state": "stop", "input_sha256": crop_sha,
                "prompt_version": "9" * 64, "literal_text": output["verbatim_text"],
                "unreadable_spans": output["unreadable_spans"], "raw_sha256": raw["sha256"],
            })
        before = {
            "specimen_id": ident, "organization_id": item["organization_id"], "collection_id": item["collection_id"], "revision": 2, "record_version_id": ident + "-v2",
            "asset": {"sha256": original_sha, "size_bytes": original.stat().st_size},
            "events": [],
            "run": {
                "id": ident + "-run", "profile": {"synthetic": False, "institutional_policy_approved": False, "semantics_confirmed": False},
                "stage": "processing_blocked", "blocker": "pilot_evidence_review_required",
                "disposition": None, "human_approved": False, "coverage_confirmed": False,
                "regions": [region], "observations": observations, "transcripts": [],
            },
        }
        after = copy.deepcopy(before)
        after.update(revision=3, record_version_id=ident + "-v3", events=[{"action": "review_coverage", "reason": "Authored fixture review"}])
        after["run"]["coverage_confirmed"] = True
        receipt = {
            "model_id": "facebook/sam3", "model_revision": SAM3_MODEL.revision,
            "checkpoint_sha256": checkpoint_sha, "checkpoint_files": checkpoint_files, "manifest_sha256": MANIFEST_SHA,
            "source": copy.deepcopy(item["source_objects"][0]), "regions": [region],
            "masks": [{"sha256": mask_sha, "generation": "3", "encoding": "binary-png-original-pixels"}],
        }
        report["human_records"].append({
            "specimen_id": ident,
            "original": {"path": original.name, "sha256": original_sha},
            "before_review": write(root, ident + "-before.json", before),
            "after_save": write(root, ident + "-saved.json", after),
            "after_reload": write(root, ident + "-reload.json", after),
            "sam_receipt": write(root, ident + "-sam.json", receipt),
            "raw_observations": raws, "crops": crops,
            "masks": {region["id"]: {"path": mask.name, "sha256": mask_sha}},
        })
    return source, report


def check(root, source, report, scope=None):
    return evaluate(source, MANIFEST_SHA, report, root, CANDIDATE, decision() if scope is None else scope)


def mutate_file(root, report, field, edit):
    row = report["human_records"][0]
    descriptor = row[field]
    payload = json.loads((root / descriptor["path"]).read_text())
    edit(payload)
    row[field] = write(root, descriptor["path"], payload)


def test_human_scope_can_be_ready_while_full_prd_is_incomplete(tmp_path):
    source, report = packet(tmp_path)
    for row in report["results"]:
        if row["case_id"].startswith("PRD-"):
            row.update(status="not_run", reason="Full criterion remains unqualified")
    result = check(tmp_path, source, report)
    assert result["human_review_preflight"] == "ready_for_independent_review"
    assert result["full_prd_preflight"] == "incomplete"
    assert len(result["full_prd_pending"]) == 20
    assert result["release_accepted"] is False
    assert result["full_prd_qualified"] is False


def test_all_generic_passes_without_actual_records_remain_pending(tmp_path):
    source, report = packet(tmp_path)
    report["human_records"] = []
    result = check(tmp_path, source, report)
    assert "HUMAN-RECORDS" in result["pending"]


@pytest.mark.parametrize("status", ["blocked", "not_run", "failed"])
@pytest.mark.parametrize("case", ["UI-PROCESSING", "AUTH-APPCHECK", *MANUAL])
def test_required_human_cases_cannot_be_deferred_or_skipped(tmp_path, case, status):
    source, report = packet(tmp_path)
    row = next(row for row in report["results"] + report["human_results"] if row["case_id"] == case)
    row["status"] = status
    result = check(tmp_path, source, report)
    assert case in result["pending"]


@pytest.mark.parametrize("change", ["pin", "unapproved", "expanded", "budget", "sensitive", "clearance"])
def test_scope_is_exactly_authorized_and_cannot_expand(tmp_path, change):
    source, report = packet(tmp_path)
    scope = decision()
    if change == "pin": report["scope_sha256"] = "a" * 64
    if change == "unapproved": scope["status"] = "proposed"
    if change == "expanded": scope["specimen_count"] = 11
    if change == "budget": scope["total_limit_micros"] = 5_000_001
    if change == "sensitive": scope["initial_admin_sensitive_access"] = True
    if change == "clearance": scope["automated_clearance"] = "approved"
    with pytest.raises(InvalidEvidence):
        check(tmp_path, source, report, scope)


@pytest.mark.parametrize("field,edit", [
    ("before_review", lambda p: p["run"].update(blocker="cost_budget_exhausted")),
    ("before_review", lambda p: p["run"]["profile"].update(synthetic=True)),
    ("before_review", lambda p: p["run"]["observations"].pop()),
    ("before_review", lambda p: p["run"]["regions"].append({"id":"missed-region"})),
    ("before_review", lambda p: p["run"]["observations"][0].update(completion_state="truncated")),
    ("before_review", lambda p: p["run"]["observations"][0].update(literal_text="invented text")),
    ("before_review", lambda p: p["run"]["observations"][0].update(route_id="handwriting-muse")),
    ("after_save", lambda p: p.update(revision=2)),
    ("after_save", lambda p: p["run"].update(coverage_confirmed=False)),
    ("after_reload", lambda p: p["run"].update(disposition="cleared")),
    ("after_reload", lambda p: p["run"]["observations"][0].update(literal_text="overwritten raw")),
    ("sam_receipt", lambda p: p["source"].update(sha256="a"*64)),
    ("sam_receipt", lambda p: p.update(model_id="synthetic-sam")),
    ("sam_receipt", lambda p: p.update(regions=[])),
])
def test_partial_processing_fabrication_or_missing_persistence_fails(tmp_path, field, edit):
    source, report = packet(tmp_path)
    mutate_file(tmp_path, report, field, edit)
    with pytest.raises(InvalidEvidence):
        check(tmp_path, source, report)


def test_no_specimen_or_subcriterion_can_disappear(tmp_path):
    source, report = packet(tmp_path)
    report["human_records"].pop()
    with pytest.raises(InvalidEvidence):
        check(tmp_path, source, report)
    source, report = packet(tmp_path)
    report["human_results"].pop()
    with pytest.raises(InvalidEvidence):
        check(tmp_path, source, report)


def test_workspace_scope_and_retained_masks_are_required(tmp_path):
    source, report = packet(tmp_path)
    for field in ("before_review", "after_save", "after_reload"):
        mutate_file(tmp_path, report, field, lambda p: p.update(organization_id="outside-scope"))
    with pytest.raises(InvalidEvidence):
        check(tmp_path, source, report)


def test_sam_receipt_without_mask_bytes_cannot_complete_review(tmp_path):
    source, report = packet(tmp_path)
    report["human_records"][0]["masks"] = {}
    with pytest.raises(InvalidEvidence):
        check(tmp_path, source, report)


def test_raw_literal_truncation_is_rejected_even_with_valid_saved_snapshots(tmp_path):
    source, report = packet(tmp_path)
    first = report["human_records"][0]
    obs_id = next(iter(first["raw_observations"]))
    entry = first["raw_observations"][obs_id]
    raw = json.loads((tmp_path / entry["path"]).read_text())
    raw[-1]["finish_reason"] = "length"
    first["raw_observations"][obs_id] = write(tmp_path, entry["path"], raw)
    for field in ("before_review", "after_save", "after_reload"):
        mutate_file(tmp_path, report, field, lambda p: p["run"]["observations"][0].update(raw_sha256=first["raw_observations"][obs_id]["sha256"]))
    with pytest.raises(InvalidEvidence):
        check(tmp_path, source, report)


def test_missing_input_crop_bytes_cannot_complete_review(tmp_path):
    source, report = packet(tmp_path)
    report["human_records"][0].pop("crops", None)
    with pytest.raises(InvalidEvidence):
        check(tmp_path, source, report)


def test_omitted_optional_raw_uncertainty_retains_schema_default(tmp_path):
    source, report = packet(tmp_path)
    record = report["human_records"][0]
    obs_id = next(iter(record["raw_observations"]))
    entry = record["raw_observations"][obs_id]
    raw = json.loads((tmp_path / entry["path"]).read_text())
    raw[-1]["parts"][0]["args"].pop("unreadable_spans")
    record["raw_observations"][obs_id] = write(tmp_path, entry["path"], raw)
    for field in ("before_review", "after_save", "after_reload"):
        mutate_file(tmp_path, report, field, lambda p: p["run"]["observations"][0].update(unreadable_spans=[], raw_sha256=record["raw_observations"][obs_id]["sha256"]))
    result = check(tmp_path, source, report)
    assert result["human_review_preflight"] == "ready_for_independent_review"


def test_human_skeleton_generation_never_looks_like_acceptance():
    from human_review import skeleton
    result = skeleton(CANDIDATE, MANIFEST_SHA)
    assert result["release_accepted"] is False
    assert result["full_prd_qualified"] is False
    assert result["human_review_preflight"] == "not_run"


def test_cli_binds_scope_bytes_and_returns_nonzero_for_pending(tmp_path, monkeypatch, capsys):
    from human_review import main
    scope_path = tmp_path / "scope.json"
    scope_path.write_text(json.dumps(decision(), sort_keys=True, indent=2) + "\n")
    scope_path.chmod(0o600)
    assert file_digest(scope_path) == SCOPE_SHA
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest()))
    manifest_path.chmod(0o600)
    argv = ["human_review.py", str(manifest_path), "--approved-manifest-sha256",
            file_digest(manifest_path), "--candidate-sha", CANDIDATE,
            "--scope-decision", str(scope_path), "--approved-scope-sha256", SCOPE_SHA,
            "--evidence-root", str(tmp_path)]
    monkeypatch.setattr("sys.argv", argv)
    assert main() == 0  # Template generation is explicitly not execution.
    template = json.loads(capsys.readouterr().out)
    assert template["human_review_preflight"] == "not_run"
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(template))
    monkeypatch.setattr("sys.argv", argv + ["--report", str(report_path)])
    assert main() == 1
    result = json.loads(capsys.readouterr().out)
    assert len(result["full_prd_pending"]) == 47
    assert set(MANUAL) <= set(result["pending"])
    assert not result["release_accepted"] and not result["full_prd_qualified"]
    scope_path.write_text(scope_path.read_text() + " ")
    assert main() == 2
    assert json.loads(capsys.readouterr().out)["human_review_preflight"] == "invalid"


@pytest.mark.parametrize("mode", ["fixture", "emulator", "owner_report"])
def test_nonlive_manual_subcriterion_cannot_complete_human_gate(tmp_path, mode):
    source, report = packet(tmp_path)
    report["human_results"][0]["mode"] = mode
    assert MANUAL[0] in check(tmp_path, source, report)["pending"]


def test_old_review_event_cannot_substitute_for_a_new_save(tmp_path):
    source, report = packet(tmp_path)
    saved = json.loads((tmp_path / report["human_records"][0]["after_save"]["path"]).read_text())
    mutate_file(tmp_path, report, "before_review", lambda p: p.update(events=saved["events"]))
    with pytest.raises(InvalidEvidence):
        check(tmp_path, source, report)


def test_missing_run_identity_cannot_claim_persistence(tmp_path):
    source, report = packet(tmp_path)
    for field in ("before_review", "after_save", "after_reload"):
        mutate_file(tmp_path, report, field, lambda p: p["run"].pop("id"))
    with pytest.raises(InvalidEvidence):
        check(tmp_path, source, report)


def test_json_parses_verified_bytes_even_when_path_changes_after_hash(tmp_path, monkeypatch):
    import human_review
    entry = write(tmp_path, "original.json", {"original": True})
    original_hash = hashlib.sha256
    def changed(raw):
        result = original_hash(raw)
        (tmp_path / entry["path"]).write_text('{"swapped": true}')
        return result
    monkeypatch.setattr(hashlib, "sha256", changed)
    assert human_review.json_artifact(tmp_path, entry) == {"original": True}


def test_matching_report_and_receipts_cannot_change_the_approved_sam_revision(tmp_path):
    source, report = packet(tmp_path)
    report["deployment"]["sam_model_revision"] = "c" * 40
    for row in report["human_records"]:
        entry = row["sam_receipt"]
        receipt = json.loads((tmp_path / entry["path"]).read_text())
        receipt["model_revision"] = "c" * 40
        row["sam_receipt"] = write(tmp_path, entry["path"], receipt)
    with pytest.raises(InvalidEvidence):
        check(tmp_path, source, report)


@pytest.mark.parametrize("change", [{"version": "c" * 40}, {"method": "synthetic"}])
def test_retained_regions_must_use_the_approved_sam_method_and_revision(tmp_path, change):
    source, report = packet(tmp_path)
    for field in ("before_review", "after_save", "after_reload"):
        mutate_file(tmp_path, report, field, lambda p: p["run"]["regions"][0].update(change))
    mutate_file(tmp_path, report, "sam_receipt", lambda p: p["regions"][0].update(change))
    with pytest.raises(InvalidEvidence):
        check(tmp_path, source, report)


def test_json_artifact_never_requests_an_unbounded_read(tmp_path, monkeypatch):
    import io
    import os
    from human_review import json_artifact
    entry = write(tmp_path, "bounded.json", {"retained": True})
    observed = []
    class CheckedRead:
        def __init__(self, stream):
            self.stream = stream
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return self.stream.__exit__(*args)
        def __getattr__(self, name):
            return getattr(self.stream, name)
        def read(self, size=-1):
            observed.append(size)
            assert 0 <= size <= 16 * 1024 * 1024 + 1, "Unbounded evidence read"
            return self.stream.read(size)
    original_open, original_fdopen = io.open, os.fdopen
    def wrap(stream):
        return stream if isinstance(stream, CheckedRead) else CheckedRead(stream)
    monkeypatch.setattr(io, "open", lambda *a, **k: wrap(original_open(*a, **k)))
    monkeypatch.setattr(os, "fdopen", lambda *a, **k: wrap(original_fdopen(*a, **k)))
    assert json_artifact(tmp_path, entry) == {"retained": True}
    assert len(observed) == 1


def test_json_artifact_checks_open_descriptor_is_regular_before_read(tmp_path, monkeypatch):
    import os
    import stat
    from types import SimpleNamespace
    from human_review import json_artifact
    entry = write(tmp_path, "replaced.json", {"retained": True})
    monkeypatch.setattr(os, "fstat", lambda fd: SimpleNamespace(st_mode=stat.S_IFIFO))
    with pytest.raises(InvalidEvidence, match="regular"):
        json_artifact(tmp_path, entry)


# Recorded handwriting-qwen answers (PR #310): Novita's Qwen3-VL wrote each line
# break in verbatim_text as a space or U+21B5 while lines kept the breaks. The
# reader reads them as the lines joined with newlines; the checker must read the
# retained answer the same way.
RECORDED = json.loads(
    (Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "qwen_reader_answers.json").read_text()
)["answers"]
OTHER_BREAKS = ("space_joined_two_lines", "space_joined_six_lines", "newline_symbol")


def recorded_raw(name):
    """The retained raw response as production stores it: Pydantic AI's dump of the answer."""
    answer = RECORDED[name]["responses"][0]
    response = ModelResponse(
        parts=[ToolCallPart("final_result", answer["arguments"], answer["tool_call_id"])],
        model_name=answer["response_model"], provider_response_id=answer["response_id"],
        finish_reason="tool_call",
    )
    return json.loads(ModelMessagesTypeAdapter.dump_json([response]))


def reader_observation(name):
    """The observation the reader makes of that answer (production.py: verbatim_text)."""
    output = LiteralTranscription.model_validate_json(RECORDED[name]["responses"][0]["arguments"])
    return {"literal_text": output.verbatim_text, "unreadable_spans": list(output.unreadable_spans)}


@pytest.mark.parametrize("name", OTHER_BREAKS + ("newline_joined",))
def test_retained_answer_is_read_by_the_reader_contract(name):
    raw, observation = recorded_raw(name), reader_observation(name)
    sent = json.loads(RECORDED[name]["responses"][0]["arguments"])
    assert observation["literal_text"] == "\n".join(sent["lines"])
    literal_output(raw, observation)


@pytest.mark.parametrize("name", OTHER_BREAKS)
def test_observation_that_kept_the_answers_break_form_is_refused(name):
    # The reader stores the newline form; an observation holding the provider's
    # own form was not made by the reader from this answer.
    sent = json.loads(RECORDED[name]["responses"][0]["arguments"])
    observation = dict(reader_observation(name), literal_text=sent["verbatim_text"])
    with pytest.raises(InvalidEvidence, match="Literal text differs"):
        literal_output(recorded_raw(name), observation)


@pytest.mark.parametrize("field", ["lines", "verbatim_text"])
def test_retained_answer_whose_words_differ_is_refused(field):
    # Recorded 2026-10-05: verbatim_text says "tap" where lines say "trap".
    sent = json.loads(RECORDED["words_differ"]["responses"][0]["arguments"])
    text = "\n".join(sent["lines"]) if field == "lines" else sent["verbatim_text"]
    observation = {"literal_text": text, "unreadable_spans": sent["unreadable_spans"]}
    with pytest.raises(InvalidEvidence):
        literal_output(recorded_raw("words_differ"), observation)


@pytest.mark.parametrize("name", OTHER_BREAKS)
def test_full_review_packet_accepts_a_recorded_answer_with_other_breaks(tmp_path, name):
    source, report = packet(tmp_path)
    record = report["human_records"][0]
    obs_id = next(iter(record["raw_observations"]))
    assert obs_id.endswith("handwriting-qwen")
    entry = record["raw_observations"][obs_id]
    record["raw_observations"][obs_id] = write(tmp_path, entry["path"], recorded_raw(name))
    observation = dict(reader_observation(name), raw_sha256=record["raw_observations"][obs_id]["sha256"])
    for field in ("before_review", "after_save", "after_reload"):
        mutate_file(tmp_path, report, field, lambda p: p["run"]["observations"][0].update(observation))
    result = check(tmp_path, source, report)
    assert result["human_review_preflight"] == "ready_for_independent_review"
