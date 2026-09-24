"""The thread's assembly, part by part (docs/execution/golive/DATA_CONTRACT.md 8, S5 T3).

Every thread here is assembled from GetRunThreadV1's rows for what the projection writer wrote,
so the response is checked against the writer's own rows. These cover the run's state, trace,
image, segmentation, coverage check, regions and tool calls, the current rows' ids and the read
bounds.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from specimen_digitization.application.api import summary
from specimen_digitization.application.domain import AuditEvent, Run
from specimen_digitization.application.integrity import EvidenceIntegrityError
from specimen_digitization.application.projection import derived_id, writes
from specimen_digitization.application.thread import (
    CALIBRATION,
    KEY_LIMITS,
    LIMITS,
    NESTED_LIMITS,
    TRACE_URL_SETTING,
    ThreadTooLarge,
    assemble,
    keys,
    trace_url_template,
)

from test_projection import locate, size
from test_projection_decisions import Handoff
from thread_fixtures import TRACE, ReviewCall, TracedField, fixed, rows, synthetic_run

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = "https://logfire.example.test/trace/{trace_id}"


def written(specimen):
    """Everything a reviewer's save writes for the specimen's active run."""
    return writes(specimen, locate, size, "reviewer-uid", reviewer=True)


def thread(specimen, run=None, *, history=None, template=TEMPLATE):
    """The response for one run: its rows from what was written, and the snapshot."""
    run = run or specimen.run
    data = rows(written(specimen) if history is None else history, specimen.id, run.id, keys(specimen, run))
    view = specimen if run is specimen.run else specimen.model_copy(update={"run": run})
    result = assemble(
        specimen, run, data, status=summary(view)["status"], trace_url_template=template
    )
    return result.model_dump(mode="json")


def stored(s, label):
    """The asset row the writer derives for a stored response (DATA_CONTRACT.md 5)."""
    return derived_id("asset", s.id, "demo-bucket", f"application/sha256/{label * 64}", "7")


def test_the_run_its_image_and_segmentation_come_from_the_snapshot():
    s = synthetic_run()
    # Paid calls pass through as S3 records them, keys it adds later included (LANE.md T2c).
    s.run.paid_calls[0]["later_key"] = {"kept": True}
    result = thread(s)
    assert (result["specimen_id"], result["revision"]) == (s.id, 12)
    assert result["run"] == {
        "run_id": s.run.id,
        "status": "completed",
        "stage": "finalized",
        "blocker": None,
        "next_retry_at": None,
        "profile": {"key": "zoology_insects_slides", "version": "1.0.0"},
        # The ledger's revision stays in the snapshot.
        "allowance": {
            "allowance_micros": 5000000,
            "reserved_total_micros": 60000,
            "remaining_micros": 4940000,
            "at": "2026-09-23T12:02:00+00:00",
        },
        "paid_calls": s.run.paid_calls,
        "actual_cost_micros": 23200,
    }
    reserved = result["run"]["paid_calls"][2]
    assert (reserved["kind"], reserved["route_id"], reserved["usage"], reserved["cost_basis"]) == (
        "model",
        "handwriting-muse",
        None,
        "reserved",
    )
    assert result["run"]["paid_calls"][0]["later_key"] == {"kept": True}
    assert result["trace"] == {
        "trace_id": TRACE,
        "url": f"https://logfire.example.test/trace/{TRACE}",
    }
    assert result["image"] == {
        "asset_id": s.asset.id,
        "sha256": s.asset.sha256,
        "width": 4000,
        "height": 3000,
        "pixel_basis": "original_pixel_edges",
    }
    assert result["segmentation"] == {
        "model_revision": "sam3-fixture-revision",
        "settings": {"prompt": "label", "parameters": {"label_threshold": 0.5}},
    }
    s.run.stage, s.run.disposition = "processing_blocked", None
    s.run.blocker, s.run.next_retry_at = "provider_error", "2026-09-23T13:00:00+00:00"
    blocked = thread(s)["run"]
    assert (blocked["status"], blocked["stage"], blocked["blocker"], blocked["next_retry_at"]) == (
        "processing_blocked",
        "processing_blocked",
        "provider_error",
        "2026-09-23T13:00:00+00:00",
    )


def test_the_allowance_and_paid_calls_are_absent_until_the_program_reserves():
    s = synthetic_run()
    s.run.program_allowance, s.run.paid_calls = None, []
    s.run.usage.actual_cost_micros = None
    run = thread(s)["run"]
    assert (run["allowance"], run["paid_calls"], run["actual_cost_micros"]) == (None, [], None)
    # Before S3's fields reach the domain, a run without them reads the same way.
    plain = synthetic_run()
    plain.run = Run(id=plain.run.id, profile=plain.run.profile, stage="transcribe")
    result = thread(plain)
    assert (result["run"]["allowance"], result["run"]["paid_calls"]) == (None, [])
    assert result["trace"] == {"trace_id": None, "url": None}
    assert result["coverage_check"] == {
        "status": "not_run",
        "checks": [],
        "evidence_id": None,
        "checked_at": None,
    }
    assert (result["segmentation"], result["regions"]) == (None, [])


def test_a_first_pass_decision_shows_its_call_its_rationale_and_its_handoff():
    s = synthetic_run()
    left, _ = s.run.regions
    qwen, muse = s.run.observations[:2]
    call = s.run.transcripts[0].first_pass_call
    region = thread(s)["regions"][0]
    assert (region["region_id"], region["ordinal"], region["rotation_quarter_turns"]) == (left.id, 0, 0)
    assert region["geometry"] == {"x": 180, "y": 1210, "width": 1320, "height": 640}
    assert [r["observation_id"] for r in region["readings"]] == [qwen.id, muse.id]
    reading = region["readings"][1]
    assert reading == {
        "observation_id": muse.id,
        "route_id": "handwriting-muse",
        "model": "model/handwriting-muse",
        "provider": "fixture-provider",
        "prompt_version": "p" * 64,
        "literal_text": "Chicago, Il1. VII-46 Cook Co.",
        "unreadable_spans": ["Il1."],
        "outcome": "validated_output",
        "raw_response": {"asset_id": stored(s, "d"), "sha256": "d" * 64},
    }
    first, second = sorted((qwen.id, muse.id), key=lambda i: i.replace("-", ""))
    assert region["comparisons"] == [
        {
            "left_observation_id": first,
            "right_observation_id": second,
            "algorithm": "bounded-levenshtein-fraction-v1",
            "ratio": 1 / 29,
            "edit_distance": 1,
            "length_basis": 29,
            "status": "difference",
            "reasons": ["one_substitution"],
            "calibration": CALIBRATION,
        }
    ]
    assert CALIBRATION == "uncalibrated review priority"
    decision = region["first_pass"]
    assert decision["model_call"] == {
        "observation_id": call.id,
        "route_id": "first-pass",
        "model": "model/first-pass",
        "provider": "fixture-provider",
        "prompt_version": "p" * 64,
        "outcome": "validated_output",
        "raw_response": {"asset_id": stored(s, "f"), "sha256": "f" * 64},
    }
    assert {k: v for k, v in decision.items() if k != "model_call"} == {
        "decision_kind": "first_pass",
        "selected_observation_id": qwen.id,
        "decided_text": qwen.literal_text,
        "unresolved": False,
        "rationale": "The crop shows a lowercase l.",
        # What each reader returned to the harness: the selected one, and the other with its note.
        "handoffs": [
            {
                "observation_id": qwen.id,
                "role": "decided_transcript",
                "handed_text": qwen.literal_text,
                "note": None,
            },
            {
                "observation_id": muse.id,
                "role": "raw_reading",
                "handed_text": muse.literal_text,
                "note": "Reads the l as a one.",
            },
        ],
    }
    # The first pass's call is not a reading of the region.
    assert call.id not in {r["observation_id"] for r in region["readings"]}


def test_a_region_without_a_recorded_decision_has_no_first_pass():
    s = synthetic_run()
    s.run.transcripts = s.run.transcripts[:1]
    regions = thread(s)["regions"]
    assert regions[0]["first_pass"] is not None
    assert (regions[1]["first_pass"], regions[1]["reviewer_decision"]) == (None, None)


def reviewed(s, index=0, *, text="Chicago, Ill. VII-46 Cook Co.", reason="Read under the microscope."):
    """A reviewer's decision on one region, as the snapshot then records it."""
    transcript = s.run.transcripts[index]
    s.run.transcripts[index] = transcript.model_copy(
        update={
            "decision_kind": "human",
            "actor": "reviewer-uid",
            "resolved": True,
            "text": text,
            "reason": reason,
            "selected_observation_id": None,
            "first_pass_call": None,
            "handoffs": [],
        }
    )
    return s


def test_a_reviewers_decision_goes_beside_the_first_pass_and_never_replaces_it():
    s = synthetic_run()
    history = written(s)
    before = thread(s, history=history)["regions"]
    # Only a first pass so far: no reviewer's decision on either region.
    assert [r["reviewer_decision"] for r in before] == [None, None]
    reviewed(s)
    after = thread(s, history=history + written(s))["regions"]
    # The model's decision stays, with its call and what each reader handed the harness.
    assert after[0]["first_pass"] == before[0]["first_pass"]
    assert after[0]["first_pass"]["decision_kind"] == "first_pass"
    assert len(after[0]["first_pass"]["handoffs"]) == 2
    assert after[0]["reviewer_decision"] == {
        "decided_text": "Chicago, Ill. VII-46 Cook Co.",
        "unresolved": False,
        "rationale": "Read under the microscope.",
    }
    assert after[1] == before[1]
    # Until a reviewer's save writes its row, the thread shows no reviewer's decision.
    worker_only = history + writes(s, locate, size, "worker-uid")
    region = thread(s, history=worker_only)["regions"][0]
    assert (region["first_pass"], region["reviewer_decision"]) == (before[0]["first_pass"], None)


def test_after_a_review_the_first_pass_is_the_regions_latest_model_decision():
    s = synthetic_run()
    history = written(s)
    # The first pass decided the region again before the reviewer did.
    s.run.transcripts[0] = s.run.transcripts[0].model_copy(update={"reason": "A second look: a lowercase l."})
    history += written(s)
    reviewed(s)
    history += written(s)
    first = thread(s, history=history)["regions"][0]["first_pass"]
    assert (first["decision_kind"], first["rationale"]) == ("first_pass", "A second look: a lowercase l.")
    assert [h["role"] for h in first["handoffs"]] == ["decided_transcript", "raw_reading"]


def test_identical_readings_are_the_models_decision_with_no_call_and_no_notes():
    s = synthetic_run()
    qwen, muse = s.run.observations[:2]
    s.run.observations[1] = muse.model_copy(update={"literal_text": qwen.literal_text, "unreadable_spans": []})
    s.run.transcripts[0] = s.run.transcripts[0].model_copy(
        update={
            "decision_kind": "identical_readings",
            "first_pass_call": None,
            "reason": None,
            "differences": [],
            "disagreement_ratio": 0.0,
            "alignment_status": "identical",
            "alignment_reasons": [],
            "handoffs": [
                Handoff(observation_id=qwen.id, role="decided_transcript", handed_text=qwen.literal_text),
                Handoff(observation_id=muse.id, role="raw_reading", handed_text=qwen.literal_text),
            ],
        }
    )
    region = thread(s)["regions"][0]
    first = region["first_pass"]
    assert (first["decision_kind"], first["selected_observation_id"], first["unresolved"]) == (
        "identical_readings",
        qwen.id,
        False,
    )
    assert (first["decided_text"], first["rationale"], first["model_call"]) == (qwen.literal_text, None, None)
    assert [(h["role"], h["observation_id"], h["note"]) for h in first["handoffs"]] == [
        ("decided_transcript", qwen.id, None),
        ("raw_reading", muse.id, None),
    ]
    assert region["reviewer_decision"] is None


def test_a_no_pick_decision_hands_every_raw_reading():
    s = synthetic_run()
    _, right = s.run.regions
    qwen, muse = s.run.observations[2:]
    result = thread(s)
    region = result["regions"][1]
    assert (region["region_id"], region["rotation_quarter_turns"]) == (right.id, 1)
    decision = region["first_pass"]
    assert (decision["selected_observation_id"], decision["unresolved"], decision["decided_text"]) == (None, True, "")
    assert decision["handoffs"] == [
        {"observation_id": qwen.id, "role": "raw_reading", "handed_text": qwen.literal_text, "note": "Reads the authority as L."},
        {"observation_id": muse.id, "role": "raw_reading", "handed_text": muse.literal_text, "note": "Reads the authority as Linn."},
    ]


def test_a_google_call_keeps_place_ids_and_a_no_match_is_a_call_too():
    s = synthetic_run()
    left, _ = s.run.regions
    place, nowhere = s.run.lookups[:2]
    result = thread(s)
    success, no_match = result["tool_calls"][:2]
    assert success == {
        "call_key": s.run.tool_calls[0].call_key,
        "phase": "lookup",
        "tool": "geocode",
        "tool_version": "geocode-1",
        "source": "google-maps-geocoding",
        "field_keys": ["province_state", "city"],
        "input_source": "decided_transcript",
        "region_id": left.id,
        "observation_id": None,
        "review_decision_id": None,
        "attempt": 1,
        "arguments": {"query": "Chicago, Ill."},
        "outcome": "success",
        # Rule 1.6: a Google call keeps place ids only.
        "result": {"place_ids": ["fixture-place"]},
        "error": None,
        "retry_after": None,
        "evidence_id": place.id,
        "started_at": "2026-09-23T12:04:00.000000Z",
        "completed_at": "2026-09-23T12:05:00.000000Z",
    }
    assert (no_match["outcome"], no_match["evidence_id"], no_match["field_keys"]) == ("no_match", nowhere.id, ["county"])


def test_every_other_outcome_stays_in_tool_calls_with_its_error_and_retry():
    s = synthetic_run()
    gbif_call = s.run.tool_calls[2]
    s.run.tool_calls.append(
        gbif_call.model_copy(
            update={
                "call_key": gbif_call.call_key[:-1] + "2",
                "attempt": 2,
                "outcome": "rate_limited",
                "result": {"error": "rate limited", "retry_after": 30},
                "evidence_id": None,
            }
        )
    )
    retried = thread(s)["tool_calls"][-1]
    assert (retried["attempt"], retried["outcome"], retried["evidence_id"]) == (2, "rate_limited", None)
    assert (retried["error"], retried["retry_after"]) == ("rate limited", 30)
    assert retried["result"] == {"error": "rate limited", "retry_after": 30}


def test_a_google_identity_that_keeps_a_name_leaves_the_run_without_a_thread():
    s = synthetic_run()
    city = s.run.fields["city"]
    s.run.fields["city"] = city.model_copy(
        update={"authority_identity": {**city.authority_identity, "name": "fixture-google-name"}}
    )
    # T2c: the writer refuses the run (G26, projection.GoogleContentStored), and so the thread does.
    with pytest.raises(EvidenceIntegrityError) as refused:
        keys(s, s.run)
    assert str(refused.value) == "field city keeps a Google name (G26)"


def test_a_call_on_a_reviewers_text_names_its_review_decision():
    s = synthetic_run()
    # G38's "fill the rest": a reviewer's decision, and a call that ran on the reviewer's text.
    asked = AuditEvent(
        actor="reviewer-uid",
        action="review_fill_the_rest",
        reason="Filled the county",
        before={},
        after={"county": "Cook"},
    )
    s.audit.append(asked)
    s.run.tool_calls.append(
        ReviewCall(
            call_key="lookup:geonames:review:1",
            phase="lookup",
            tool="geonames",
            tool_version="g1",
            source="geonames",
            field_keys=["county"],
            input_source="review",
            arguments={"name": "Cook"},
            outcome="no_match",
            result={},
            review_decision_id=asked.id,
        )
    )
    calls = thread(s)["tool_calls"]
    review = calls[-1]
    assert (review["input_source"], review["review_decision_id"]) == ("review", asked.id)
    assert (review["region_id"], review["observation_id"]) == (None, None)
    assert [c["review_decision_id"] for c in calls[:-1]] == [None] * (len(calls) - 1)


def test_each_run_reads_its_own_rows():
    s = synthetic_run()
    first = s.run
    history = written(s)
    # A new run reuses the region ids (rule 1.5); everything else in it is new.
    second = synthetic_run(
        ident=lambda n: fixed(n) if n in (10, 11) else f"00000000-0000-4000-9000-{n:012d}"
    ).run
    s.previous_runs, s.run = [first], second
    history += written(s)
    newest = thread(s, history=history)
    older = thread(s, first, history=history)
    assert newest["run"]["run_id"] == second.id and older["run"]["run_id"] == first.id
    assert [r["region_id"] for r in newest["regions"]] == [r["region_id"] for r in older["regions"]]
    assert {o["observation_id"] for r in older["regions"] for o in r["readings"]} == {o.id for o in first.observations}
    assert {o["observation_id"] for r in newest["regions"] for o in r["readings"]} == {o.id for o in second.observations}


def test_a_run_without_rows_yet_reads_from_the_snapshot_alone():
    s = synthetic_run()
    result = thread(s, history=[])
    assert (result["regions"], result["tool_calls"]) == ([], [])
    assert result["run"]["run_id"] == s.run.id
    # The trace id is the run's own until its row records it.
    assert result["trace"]["trace_id"] == TRACE
    assert result["coverage_check"]["status"] == "passed"
    assert result["coverage_check"]["evidence_id"] is None


def test_the_coverage_check_reports_each_check():
    s = synthetic_run()
    coverage = thread(s)["coverage_check"]
    assert coverage == {
        "status": "passed",
        "checks": [
            {"name": "region_count", "passed": True, "detail": {"found": 2, "min": 1, "max": 3, "reason_codes": []}},
            {
                "name": "full_image",
                "passed": True,
                "detail": {"counted": 2, "outside": 0, "threshold": 0.5, "min_inside_fraction": 0.5, "reason_codes": []},
            },
        ],
        # The evidence item the writer records from the check (section 2).
        "evidence_id": derived_id("coverage", s.run.id, "e" * 64),
        "checked_at": "2026-09-23T12:01:00+00:00",
    }
    # A failed check names its own codes.
    check = dict(s.run.coverage_check)
    check.update(
        outcome="unconfirmed",
        region_count=4,
        reason_codes=["label_coverage_unconfirmed", "label_region_count_out_of_range", "cross_check_detection_outside_labels"],
        cross_check=dict(check["cross_check"], counted=3, uncovered_boxes=[[0, 0, 10, 10]]),
    )
    s.run.coverage_check = check
    failed = thread(s)["coverage_check"]
    assert failed["status"] == "failed"
    assert failed["checks"] == [
        {
            "name": "region_count",
            "passed": False,
            "detail": {"found": 4, "min": 1, "max": 3, "reason_codes": ["label_region_count_out_of_range"]},
        },
        {
            "name": "full_image",
            "passed": False,
            "detail": {
                "counted": 3,
                "outside": 1,
                "threshold": 0.5,
                "min_inside_fraction": 0.5,
                "reason_codes": ["cross_check_detection_outside_labels"],
            },
        },
    ]
    # The range is null when the check did not record it, although the pinned profile has one.
    unranged = {k: v for k, v in check.items() if k not in ("min_label_regions", "max_label_regions")}
    s.run.coverage_check = unranged
    assert s.run.profile_snapshot["segmentation_settings"]["coverage"]["max_label_regions"] == 3
    region_count = thread(s)["coverage_check"]["checks"][0]["detail"]
    assert (region_count["min"], region_count["max"]) == (None, None)
    s.run.coverage_check = dict(check, outcome="unconfirmed", reason_codes=["label_coverage_unconfirmed", "zero_regions"], region_count=0)
    zero = thread(s)["coverage_check"]["checks"]
    assert (zero[0]["passed"], zero[0]["detail"]["reason_codes"], zero[1]["passed"]) == (False, ["zero_regions"], True)
    # Without its evidence blob the check has no evidence item.
    s.run.coverage_check = {**check, "evidence_ref": None}
    assert thread(s)["coverage_check"]["evidence_id"] is None


def test_the_trace_link_is_built_from_the_configured_template():
    assert trace_url_template({}) is None
    assert trace_url_template({TRACE_URL_SETTING: ""}) is None
    assert trace_url_template({TRACE_URL_SETTING: TEMPLATE}) == TEMPLATE
    for bad in (
        "http://logfire.example.test/trace/{trace_id}",
        "https://logfire.example.test/trace",
        "https://logfire.example.test/{trace_id}/{trace_id}",
        "https://logfire.example.test/{trace_id}?q={span_id}",
        "https://someone@logfire.example.test/{trace_id}",
        "https:///{trace_id}",
    ):
        with pytest.raises(ValueError):
            trace_url_template({TRACE_URL_SETTING: bad})
    s = synthetic_run()
    assert thread(s, template=None)["trace"] == {"trace_id": TRACE, "url": None}
    s.run.trace_id = "0" * 32
    assert thread(s, history=[])["trace"]["url"] is None


def test_a_list_at_its_limit_is_refused_rather_than_shown_in_part():
    s = synthetic_run()
    data = rows(written(s), s.id, s.run.id, keys(s, s.run))
    region = data["runs"][0]["regions"][0]
    data["runs"][0]["regions"] = [region] * LIMITS["regions"]
    with pytest.raises(ThreadTooLarge):
        assemble(s, s.run, data, status="completed")
    s.run.fields = {f"field_{n}": TracedField(literal="x") for n in range(KEY_LIMITS["candidateIds"] + 1)}
    with pytest.raises(ThreadTooLarge):
        keys(s, s.run)


def test_the_keys_are_the_ids_of_the_rows_the_writer_writes():
    # The thread reads exactly the current rows: those the writer writes for the snapshot's run.
    s = reviewed(synthetic_run())
    written_rows = written(s)
    ids = {op: [w.variables["id"] for w in written_rows if w.operation == op] for op in (
        "AppendTranscriptionVersionV2", "AppendFieldCandidateV3", "AppendRecordVersionV2")}
    assert keys(s, s.run) == {
        "decisionIds": ids["AppendTranscriptionVersionV2"],
        "candidateIds": ids["AppendFieldCandidateV3"],
        "recordIds": ids["AppendRecordVersionV2"],
    }
    # The writer refuses a run whose stored calls hold a credential, and so the thread does (rule
    # 1.6), as a stored-evidence integrity failure whose message names where, never the value.
    call = s.run.tool_calls[0]
    s.run.tool_calls[0] = call.model_copy(update={"result": {"place_ids": ["fixture-place"], "names": ["x"]}})
    with pytest.raises(EvidenceIntegrityError, match=r"^tool call 0 \(geocode\) keeps more than place ids"):
        keys(s, s.run)
    credential = "AIza" + "0" * 35
    s.run.tool_calls[0] = call.model_copy(update={"arguments": {"query": "Chicago, Ill.", "key": credential}})
    with pytest.raises(EvidenceIntegrityError) as refused:
        assemble(s, s.run, {}, status="completed")
    assert str(refused.value) == "tool call 0 (geocode) holds a credential (rule 1.6)"


def test_the_limits_are_the_operations():
    source = (ROOT / "dataconnect/connector/thread.gql").read_text()
    limits = dict(re.findall(r"(\w+): \w+_on_\w+\([^)]*limit: (\d+)\)", source))
    assert {name: int(value) for name, value in limits.items()} == {
        **LIMITS,
        **NESTED_LIMITS,
        "decisions": KEY_LIMITS["decisionIds"],
        "candidates": KEY_LIMITS["candidateIds"],
        "records": KEY_LIMITS["recordIds"],
    }
    check = re.search(r"size\(vars\.decisionIds\) <= (\d+) && size\(vars\.candidateIds\) <= (\d+) && size\(vars\.recordIds\) <= (\d+)", source)
    assert tuple(int(n) for n in check.groups()) == tuple(KEY_LIMITS.values())
