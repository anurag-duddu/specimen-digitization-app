"""The thread's assembly, field by field (docs/execution/golive/DATA_CONTRACT.md 8, S5 T3).

Every thread here is assembled from GetRunThreadV1's rows for what the projection writer wrote,
so the response is checked against the writer's own rows. Run this file to rewrite the canonical
example after a deliberate change: `uv run python tests/test_thread.py`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from specimen_digitization.application.api import summary
from specimen_digitization.application.domain import (
    AuditEvent,
    Disposition,
    Evidence,
    Lookup,
    LookupStatus,
    Run,
    ValueState,
)
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
    settled_observation_ids,
    trace_url_template,
)

from test_projection import locate, size
from test_projection_decisions import Handoff, ToolCallRecord
from thread_fixtures import TRACE, ReviewCall, TracedField, fixed, hexid, rows, synthetic_run

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "docs/execution/golive/thread-example.json"
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


def example_json() -> str:
    return json.dumps(thread(synthetic_run()), indent=2, ensure_ascii=False) + "\n"


def by_key(items, key):
    return {item[key]: item for item in items}


def stored(s, label):
    """The asset row the writer derives for a stored response (DATA_CONTRACT.md 5)."""
    return derived_id("asset", s.id, "demo-bucket", f"application/sha256/{label * 64}", "7")


def test_the_canonical_example_is_the_assembly_of_its_synthetic_run():
    # S6 builds against this file; it cannot drift from what the API serves.
    assert EXAMPLE.read_text() == example_json()


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
    assert (result["segmentation"], result["regions"], result["decision"]) == (None, [], None)


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


def test_a_no_pick_decision_hands_every_raw_reading_and_each_reader_keeps_its_verbatim():
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
    taxon = by_key(result["fields"], "field_key")["taxon"]
    assert taxon["verbatim"] == [
        {"text": "Aedes aegypti L.", "input_source": "raw_reading", "region_id": right.id, "observation_id": qwen.id},
        {"text": "Aedes aegypti Linn.", "input_source": "raw_reading", "region_id": right.id, "observation_id": muse.id},
    ]
    # G20: the reader a lookup confirmed carries the settled value, and only that reader is named.
    assert (taxon["normalized"], taxon["authority_id"], taxon["settled_observation_ids"]) == (
        "Aedes aegypti",
        "gbif:1651891",
        [qwen.id],
    )
    # With no reader confirmed, no settled value and no single verbatim is implied.
    field = s.run.fields["taxon"]
    s.run.fields["taxon"] = field.model_copy(
        update={"settled_observation_ids": [], "normalized": None, "authority_id": None, "evidence_ids": [], "evidence_relations": {}}
    )
    unconfirmed = by_key(thread(s)["fields"], "field_key")["taxon"]
    assert len(unconfirmed["verbatim"]) == 2
    assert (unconfirmed["normalized"], unconfirmed["authority_id"], unconfirmed["settled_observation_ids"], unconfirmed["evidence"]) == (
        None,
        None,
        [],
        [],
    )


def test_google_keeps_a_place_id_and_a_no_match_appears_only_in_tool_calls():
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
    fields = by_key(result["fields"], "field_key")
    state = fields["province_state"]
    assert state["evidence"] == [
        {
            "evidence_id": place.id,
            "relation": "supports",
            "source": "google-maps-geocoding",
            "locator": "place/fixture-place",
            "outcome": "success",
            # A lookup quotes no reading.
            "observation_ids": [],
        }
    ]
    # G26: Google confirms the label's own literal; it never supplies the value. A single-label
    # decided transcript keeps a null reading, and without a fallback it names none.
    assert (state["normalized"], state["authority_id"], state["settled_observation_ids"]) == (None, None, [])
    assert state["verbatim"] == [
        {"text": "Ill.", "input_source": "decided_transcript", "region_id": left.id, "observation_id": None}
    ]
    county = fields["county"]
    assert (county["state"], county["evidence"], county["authority_id"], county["settled_observation_ids"]) == ("unresolved", [], None, [])
    linked = {e["evidence_id"] for f in result["fields"] for e in f["evidence"]}
    assert nowhere.id not in linked


def test_a_field_on_two_labels_that_settled_alike_clears_with_every_labels_reading():
    s = synthetic_run()
    left, right = s.run.regions
    left_qwen, _, right_qwen, right_muse = s.run.observations
    place, place_right = s.run.lookups[0], s.run.lookups[4]
    by_qwen, by_muse = s.run.evidence
    city = by_key(thread(s)["fields"], "field_key")["city"]
    # G32: each label's own entry with its own input source; the decided label's entry names the
    # reading its first pass selected, and the right label's readers agree, so it brings one.
    assert city["verbatim"] == [
        {"text": "Chicago", "input_source": "decided_transcript", "region_id": left.id, "observation_id": left_qwen.id},
        {"text": "Chicago", "input_source": "raw_reading", "region_id": right.id, "observation_id": right_qwen.id},
    ]
    assert (city["state"], city["group"], city["authority_id"], city["normalized"]) == ("supported", "mandatory", "fixture-place", None)
    # Each label settled on its own evidence, named in verbatim order.
    assert city["settled_observation_ids"] == [left_qwen.id, right_qwen.id]
    # Each agreeing reader's literal is its own evidence (agreed with S4).
    assert [(e["evidence_id"], e["relation"], e["observation_ids"]) for e in city["evidence"]] == [
        (place.id, "supports", []),
        (place_right.id, "supports", []),
        (by_qwen.id, "supports", [right_qwen.id]),
        (by_muse.id, "supports", [right_muse.id]),
    ]
    assert (by_muse.source, city["evidence"][3]["outcome"], city["evidence"][3]["locator"]) == (
        "field_harness",
        "recorded",
        f"region:{right.id}",
    )


def test_a_field_on_two_labels_in_conflict_settles_nothing_though_its_evidence_links():
    s = synthetic_run()
    left_qwen, _, right_qwen, right_muse = s.run.observations
    by_qwen, by_muse = s.run.evidence
    s.run.fields["city"] = s.run.fields["city"].model_copy(
        update={
            "state": ValueState.AMBIGUOUS,
            "verbatim_by_observation": {left_qwen.id: "Chicago", right_qwen.id: "Cicero"},
            "settled_observation_ids": [],
            "authority_id": None,
            "evidence_ids": [by_qwen.id, by_muse.id],
            "evidence_relations": {by_qwen.id: "supports", by_muse.id: "supports"},
        }
    )
    s.run.reasons = ["mandatory_unresolved:county", "labels_conflict:city"]
    result = thread(s)
    city = by_key(result["fields"], "field_key")["city"]
    assert [(v["text"], v["observation_id"]) for v in city["verbatim"]] == [
        ("Chicago", left_qwen.id),
        ("Cicero", right_qwen.id),
    ]
    # Evidence links to the entry it names, settled or not; a link settles nothing.
    assert [(e["evidence_id"], e["observation_ids"]) for e in city["evidence"]] == [
        (by_qwen.id, [right_qwen.id]),
        (by_muse.id, [right_muse.id]),
    ]
    assert (city["state"], city["settled_observation_ids"], city["authority_id"]) == ("ambiguous", [], None)
    assert "labels_conflict:city" in result["decision"]["reason_codes"]


def test_an_entry_the_writers_rule_settles_is_listed_though_its_candidate_carries_no_value():
    s = synthetic_run()
    left_qwen, _, right_qwen, _ = s.run.observations
    # Both labels settled with no normalized, authority or parsed form, so no candidate carries
    # a value; the writer's rule (projection.settled_entries) still settles both entries.
    s.run.fields["city"] = s.run.fields["city"].model_copy(update={"authority_id": None})
    city = by_key(thread(s)["fields"], "field_key")["city"]
    assert (city["normalized"], city["authority_id"], city["parsed"]) == (None, None, None)
    assert city["settled_observation_ids"] == [left_qwen.id, right_qwen.id]


def test_readers_that_agree_without_a_pick_keep_one_verbatim_and_each_readers_evidence():
    s = synthetic_run()
    _, right = s.run.regions
    right_qwen, right_muse = s.run.observations[2:]
    by_qwen, by_muse = s.run.evidence
    # One label, no pick, and both readers read the text alike: one literal, from the first
    # reading, with each reader's own literal evidence (section 4.3; agreed with S4).
    s.run.fields["verbatim_dts"] = TracedField(
        state=ValueState.SUPPORTED,
        reason="transcribed_as_seen",
        literal="Chicago",
        input_source="raw_reading",
        source_region_id=right.id,
        source_observation_id=right_qwen.id,
        evidence_ids=[by_qwen.id, by_muse.id],
        evidence_relations={by_qwen.id: "supports", by_muse.id: "supports"},
    )
    field = by_key(thread(s)["fields"], "field_key")["verbatim_dts"]
    assert field["verbatim"] == [
        {"text": "Chicago", "input_source": "raw_reading", "region_id": right.id, "observation_id": right_qwen.id}
    ]
    assert [(e["evidence_id"], e["observation_ids"]) for e in field["evidence"]] == [
        (by_qwen.id, [right_qwen.id]),
        (by_muse.id, [right_muse.id]),
    ]
    # One verbatim that no lookup settled names no reading.
    assert (field["settled_observation_ids"], field["normalized"], field["authority_id"]) == ([], None, None)


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


def test_gbif_decides_and_catalogue_of_life_contradicts():
    s = synthetic_run()
    gbif, col = s.run.lookups[2:4]
    taxon = by_key(thread(s)["fields"], "field_key")["taxon"]
    assert taxon["evidence"] == [
        {"evidence_id": gbif.id, "relation": "decides", "source": "gbif", "locator": "gbif/species/1651891", "outcome": "success", "observation_ids": []},
        {"evidence_id": col.id, "relation": "contradicts", "source": "catalogue-of-life", "locator": "col/taxon/fixture-col-taxon", "outcome": "success", "observation_ids": []},
    ]
    assert (taxon["group"], taxon["state"]) == ("mandatory", "supported")


def test_findings_carry_their_severity_and_evidence_ids():
    s = synthetic_run()
    col = s.run.lookups[3]
    decision = thread(s)["decision"]
    assert {k: v for k, v in decision.items() if k != "findings"} == {
        "disposition": "needs_human_review",
        "policy_version": s.run.profile.policy_version,
        "reason_codes": ["mandatory_unresolved:county"],
        "summary": "Needs human review under insects-clearance-v1: county unresolved.",
    }
    assert decision["findings"] == [
        {
            "rule_id": "mandatory_unresolved",
            "rule_version": s.run.profile.policy_version,
            "severity": "hard",
            "outcome": "fail",
            "field_key": "county",
            "reason_code": "mandatory_unresolved:county",
            "evidence_ids": [],
        },
        {
            "rule_id": "taxonomy_source_disagreement",
            "rule_version": "g23-v1",
            "severity": "warning",
            "outcome": "fail",
            "field_key": "taxon",
            "reason_code": "taxonomy_source_disagreement",
            "evidence_ids": [col.id],
        },
    ]
    # Until the queue decides there is no decision.
    s.run.disposition, s.run.reasons = None, []
    assert thread(s)["decision"] is None


def test_dates_keep_their_precision_and_century_rule():
    fields = by_key(thread(synthetic_run())["fields"], "field_key")
    date = fields["date_visited_from"]
    assert (date["parsed"], date["precision"], date["century_rule"]) == (
        "1946-07",
        "month",
        "date-rules-v1:two_digit_year_century=1900",
    )
    assert (fields["city"]["parsed"], fields["city"]["precision"], fields["city"]["century_rule"]) == (None, None, None)


def test_every_field_of_the_record_is_listed_in_the_snapshots_order_with_its_group():
    s = synthetic_run()
    fields = thread(s)["fields"]
    assert [f["field_key"] for f in fields] == list(s.run.fields)
    irn = fields[-1]
    # G16: identified_by_irn is optional, and without a literal it has no verbatim.
    assert (irn["field_key"], irn["group"], irn["state"], irn["verbatim"], irn["evidence"]) == (
        "identified_by_irn",
        "optional",
        "unknown",
        [],
        [],
    )
    # Before the queue decides, a field without a literal has no rows; the rest keep their group.
    s.run.disposition = None
    early = thread(s)["fields"]
    assert "identified_by_irn" not in [f["field_key"] for f in early]
    assert by_key(early, "field_key")["county"]["group"] == "mandatory"


def test_a_value_confirmed_on_a_raw_reading_names_it_after_a_pick():
    s = synthetic_run()
    left, _ = s.run.regions
    qwen, muse = s.run.observations[:2]
    confirming = Lookup(
        provider="google-maps-geocoding",
        adapter_version="geocode-1",
        query={"address": "Cook Co."},
        status=LookupStatus.SUCCESS,
        metadata={"locator": "place/fixture-county"},
        raw_ref=f"{'b' * 64}:7",
        digest="b" * 64,
        retrieved_at="2026-09-23T12:06:00+00:00",
    )
    s.run.lookups.append(confirming)
    s.run.tool_calls.append(
        ToolCallRecord(
            call_key=f"lookup:geocode:raw_reading:{left.id}:{muse.id}:{'0af7' * 4}:1",
            phase="lookup",
            tool="geocode",
            tool_version="geocode-1",
            source="google-maps-geocoding",
            field_keys=["county"],
            input_source="raw_reading",
            region_id=left.id,
            observation_id=muse.id,
            arguments={"query": "Cook Co."},
            outcome="success",
            result={"place_ids": ["fixture-county"]},
            evidence_id=confirming.id,
        )
    )
    # The verbatim stays on the decided transcript; the confirmed reading is the settled value's provenance.
    s.run.fields["county"] = TracedField(
        state=ValueState.SUPPORTED,
        literal="Cook Co.",
        authority_id="fixture-county",
        evidence_ids=[confirming.id],
        evidence_relations={confirming.id: "supports"},
        input_source="decided_transcript",
        source_region_id=left.id,
    )
    s.run.reasons = []
    fields = by_key(thread(s)["fields"], "field_key")
    county = fields["county"]
    assert county["verbatim"] == [
        {"text": "Cook Co.", "input_source": "decided_transcript", "region_id": left.id, "observation_id": None}
    ]
    # G20's fallback: the reading the confirming call ran on, not the one the first pass selected.
    assert (county["authority_id"], county["settled_observation_ids"]) == ("fixture-county", [muse.id])
    assert qwen.id not in county["settled_observation_ids"]
    # A raw-reading call whose evidence contradicts the value confirms nothing.
    field = s.run.fields["county"]
    s.run.fields["county"] = field.model_copy(update={"evidence_relations": {confirming.id: "contradicts"}})
    assert by_key(thread(s)["fields"], "field_key")["county"]["settled_observation_ids"] == []
    # A value settled on the decided transcript itself names no reading.
    decided_call = s.run.tool_calls[-1].model_copy(update={"input_source": "decided_transcript", "observation_id": None})
    s.run.tool_calls[-1] = decided_call
    s.run.fields["county"] = field
    assert by_key(thread(s)["fields"], "field_key")["county"]["settled_observation_ids"] == []


@pytest.mark.parametrize("named", ["its decided reading", "the confirmed reading"])
def test_a_decided_label_settled_through_the_fallback_lists_the_reading_it_confirmed(named):
    """G20 inside G32: S4 names the label by its decided reading or by the confirmed raw reading."""
    s = synthetic_run()
    left, right = s.run.regions
    left_qwen, left_muse, right_qwen, _ = s.run.observations
    missed, place_right = s.run.lookups[1], s.run.lookups[4]
    # The left label's decided transcript found nothing; the fallback on its other reading did.
    fallback = place_right.model_copy(update={"id": fixed(40), "raw_ref": f"{'b' * 64}:7", "retrieved_at": "2026-09-23T12:06:00+00:00"})
    s.run.lookups.append(fallback)
    base = s.run.tool_calls[4]
    s.run.tool_calls[1] = s.run.tool_calls[1].model_copy(update={"field_keys": ["city"]})
    s.run.tool_calls.append(
        base.model_copy(
            update={
                "call_key": f"lookup:geocode:raw_reading:{left.id}:{left_muse.id}:{'0af7' * 4}:1",
                "region_id": left.id,
                "observation_id": left_muse.id,
                "evidence_id": fallback.id,
            }
        )
    )
    city = s.run.fields["city"]
    s.run.fields["city"] = city.model_copy(
        update={
            "settled_observation_ids": [left_qwen.id if named == "its decided reading" else left_muse.id, right_qwen.id],
            "evidence_ids": [fallback.id, place_right.id],
            "evidence_relations": {fallback.id: "supports", place_right.id: "supports"},
        }
    )
    field = by_key(thread(s)["fields"], "field_key")["city"]
    # The decided entry keeps its selected reading as its verbatim reading...
    assert [v["observation_id"] for v in field["verbatim"]] == [left_qwen.id, right_qwen.id]
    # ...and lists the raw reading the lookup confirmed as the reading through which it settled.
    assert field["settled_observation_ids"] == [left_muse.id, right_qwen.id]
    assert missed.id not in {e["evidence_id"] for e in field["evidence"]}


def test_labels_that_settle_a_date_alike_are_each_named():
    s = synthetic_run()
    left_qwen, _, right_qwen, _ = s.run.observations
    s.run.fields["date_visited_from"] = TracedField(
        state=ValueState.SUPPORTED,
        verbatim_by_observation={left_qwen.id: "VII-46", right_qwen.id: "VII.46"},
        input_source_by_observation={left_qwen.id: "decided_transcript", right_qwen.id: "raw_reading"},
        settled_observation_ids=[left_qwen.id, right_qwen.id],
        parsed="1946-07",
        precision="month",
        century_rule="date-rules-v1:two_digit_year_century=1900",
    )
    date = by_key(thread(s)["fields"], "field_key")["date_visited_from"]
    # A parsed value alone is a settled value (section 4.3).
    assert date["settled_observation_ids"] == [left_qwen.id, right_qwen.id]
    assert (date["parsed"], date["precision"], date["normalized"]) == ("1946-07", "month", None)


def test_each_field_shows_its_layer_and_a_derived_one_the_fields_it_came_from():
    s = synthetic_run()
    fields = by_key(thread(s)["fields"], "field_key")
    # G38's layers as the snapshot records them; a field with neither literal nor lookup has none.
    assert {key: (f["layer"], f["derived_from"]) for key, f in fields.items()} == {
        "province_state": ("settled", []),
        "city": ("settled", []),
        "county": ("verbatim", []),
        "date_visited_from": ("settled", []),
        "taxon": ("settled", []),
        "identified_by_irn": (None, []),
    }
    # G37: a label that leaves the county out has it filled from the settled city (S4's #144),
    # decided by its stored derivation record.
    rule = Evidence(
        kind="derivation",
        asset_id=s.asset.id,
        source="fixture-gazetteer",
        locator="derivation:containment",
        excerpt="Chicago lies in Cook County",
        raw_ref=f"{'7' * 64}:7",
        digest="7" * 64,
    )
    s.run.evidence.append(rule)
    derived = TracedField(
        state=ValueState.SUPPORTED,
        parsed="Cook County",
        authority_id="fixture-county",
        authority_identity={"name": "Cook County", "source": "fixture-gazetteer", "source_record_id": "fixture-county", "credit": "fixture credit"},
        evidence_ids=[rule.id],
        evidence_relations={rule.id: "decides"},
        reason="derived:containment",
        layer="derived",
        derived_from=["city"],
    )
    s.run.fields["county"] = derived
    s.run.reasons = []
    county = by_key(thread(s)["fields"], "field_key")["county"]
    # T2c: its derived candidate holds its value, identity and evidence, like any settled field's,
    # and adds no verbatim, since the label leaves the county out.
    assert (county["layer"], county["derived_from"], county["state"], county["verbatim"]) == (
        "derived",
        ["city"],
        "supported",
        [],
    )
    assert (county["parsed"], county["authority_id"], county["authority_identity"]["name"]) == (
        "Cook County",
        "fixture-county",
        "Cook County",
    )
    assert [(e["evidence_id"], e["relation"], e["source"]) for e in county["evidence"]] == [
        (rule.id, "decides", "fixture-gazetteer")
    ]
    assert county["settled_observation_ids"] == []
    # derived_from is the candidate's derivedFromFieldKeys when its row is written...
    data = rows(written(s), s.id, s.run.id, keys(s, s.run))
    row = next(c for c in data["runs"][0]["candidates"] if c["fieldKey"] == "county")
    assert row["derivedFromFieldKeys"] == ["city"]
    row["derivedFromFieldKeys"] = ["city", "province_state"]
    shown = assemble(s, s.run, data, status="completed").model_dump(mode="json")
    assert by_key(shown["fields"], "field_key")["county"]["derived_from"] == ["city", "province_state"]
    # ...else the snapshot's: a derived value without its record has no candidate (PLAN 4.8).
    s.run.fields["county"] = derived.model_copy(update={"evidence_ids": [], "evidence_relations": {}})
    uncounted = by_key(thread(s)["fields"], "field_key")["county"]
    assert (uncounted["derived_from"], uncounted["parsed"], uncounted["evidence"]) == (["city"], None, [])


def test_a_settled_value_shows_its_authoritys_identity():
    fields = by_key(thread(synthetic_run())["fields"], "field_key")
    # PLAN 4.8: the settled candidate's authorityIdentity; Google's keeps no name (G26).
    assert fields["city"]["authority_identity"] == {"source": "google-maps-geocoding", "source_record_id": "fixture-place"}
    assert fields["taxon"]["authority_identity"] == {
        "name": "Aedes aegypti",
        "source": "gbif",
        "source_record_id": "1651891",
        "credit": "fixture credit",
    }
    assert fields["county"]["authority_identity"] is None


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


def test_a_fields_findings_are_the_records_findings_that_name_it():
    s = synthetic_run()
    left, _ = s.run.regions
    # G45 (the owner, 2026-09-24): a value no lookup checks that does not look like its field's
    # kind goes to review with S4's reason code.
    s.run.fields["collector"] = TracedField(
        state=ValueState.SUPPORTED,
        literal="VI-24-68-7",
        input_source="decided_transcript",
        source_region_id=left.id,
    )
    s.run.reasons = ["mandatory_unresolved:county", "value_shape_mismatch:collector"]
    result = thread(s)
    fields = by_key(result["fields"], "field_key")
    # The same rows and shape as decision.findings, each on the field it names.
    for key, field in fields.items():
        assert field["findings"] == [f for f in result["decision"]["findings"] if f["field_key"] == key]
    assert [(f["severity"], f["reason_code"]) for f in fields["collector"]["findings"]] == [
        ("hard", "value_shape_mismatch:collector")
    ]
    assert [(f["severity"], f["reason_code"]) for f in fields["county"]["findings"]] == [
        ("hard", "mandatory_unresolved:county")
    ]
    assert [(f["severity"], f["reason_code"]) for f in fields["taxon"]["findings"]] == [
        ("warning", "taxonomy_source_disagreement")
    ]
    assert fields["city"]["findings"] == []
    # Before the queue decides there are none.
    s.run.disposition = None
    assert all(f["findings"] == [] for f in thread(s)["fields"])


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


def link(evidence_id, relation):
    return {"evidenceId": hexid(evidence_id), "relation": relation}


def candidate_row(n, *, source="decided_transcript", selected=None, reading=None, authority=None, normalized=None, parsed=None, links=()):
    """A field candidate as GetRunThreadV1 returns it, for rule cases the fixture does not cover."""
    return {
        "id": hexid(fixed(900 + n)),
        "fieldKey": "city",
        "state": "supported",
        "literalValue": "Chicago",
        "parsedValue": parsed,
        "normalizedValue": normalized,
        "authorityId": authority,
        "inputSource": source,
        "sourceObservationId": hexid(reading),
        "sourceTranscription": None
        if source != "decided_transcript"
        else {"selectedObservationId": hexid(selected), "region": {"domainRegionId": fixed(10 + n)}},
        "sourceObservation": None,
        "links": list(links),
    }


def call_row(evidence_id, reading, source="raw_reading"):
    return {"evidenceId": hexid(evidence_id), "inputSource": source, "observationId": hexid(reading)}


def ids_of(*candidates):
    return {candidate["id"] for candidate in candidates}


def test_settled_readings_follow_section_8_for_each_shape_of_field():
    # A per-label map (G32): each entry the writer's rule settles, in verbatim order, decided
    # labels by their selected reading, raw readings by their own.
    left, right = fixed(20), fixed(22)
    both = [
        candidate_row(0, selected=left, authority="fixture-place", links=[link(fixed(30), "supports")]),
        candidate_row(1, selected=right, authority="fixture-place", links=[link(fixed(35), "supports")]),
    ]
    calls = [call_row(fixed(30), None, "decided_transcript"), call_row(fixed(35), None, "decided_transcript")]
    assert settled_observation_ids(both, calls, mapped=True, settled=ids_of(*both)) == [left, right]
    assert settled_observation_ids(list(reversed(both)), calls, mapped=True, settled=ids_of(*both)) == [right, left]
    assert settled_observation_ids(both, calls, mapped=True, settled=ids_of(both[0])) == [left]
    raw = candidate_row(2, source="raw_reading", reading=fixed(23), normalized="Chicago")
    assert settled_observation_ids([candidate_row(0, authority="fixture-place"), raw], [], mapped=True, settled=ids_of(raw)) == [fixed(23)]
    # A candidate's values and links decide nothing: an entry the rule settles is listed without
    # a value, and one it does not settle is left out with one.
    bare = candidate_row(3, source="raw_reading", reading=fixed(24))
    dated = candidate_row(4, source="raw_reading", reading=fixed(25), parsed={"value": "1946-07", "precision": "month", "century_rule": None}, links=[link(fixed(38), "supports")])
    assert settled_observation_ids([bare, dated], [call_row(fixed(38), fixed(25))], mapped=True, settled=ids_of(bare)) == [fixed(24)]
    # A map's decided entry settled through the fallback lists the raw reading the lookup confirmed.
    fell_back = candidate_row(0, selected=left, authority="fixture-place", links=[link(fixed(39), "supports")])
    assert settled_observation_ids([fell_back, both[1]], [call_row(fixed(39), fixed(21)), *calls], mapped=True, settled=ids_of(fell_back, both[1])) == [fixed(21), right]
    # A single decided transcript: only G20's fallback names a reading, each reading once, with
    # or without a value on its candidate.
    confirmed = candidate_row(0, selected=left, authority="fixture-place", links=[link(fixed(36), "supports")])
    assert settled_observation_ids([confirmed], [call_row(fixed(36), fixed(21))], mapped=False) == [fixed(21)]
    plain = candidate_row(0, selected=left, links=[link(fixed(36), "supports")])
    assert settled_observation_ids([plain], [call_row(fixed(36), fixed(21))], mapped=False) == [fixed(21)]
    twice = candidate_row(0, selected=left, authority="k", links=[link(fixed(36), "decides"), link(fixed(37), "supports")])
    assert settled_observation_ids([twice], [call_row(fixed(36), fixed(21)), call_row(fixed(37), fixed(21))], mapped=False) == [fixed(21)]
    assert settled_observation_ids([confirmed], [call_row(fixed(36), None, "decided_transcript")], mapped=False) == []
    contradicted = candidate_row(0, selected=left, links=[link(fixed(36), "contradicts")])
    assert settled_observation_ids([contradicted], [call_row(fixed(36), fixed(21))], mapped=False) == []
    # Otherwise the list is empty: no fallback, or one raw reading outside a map.
    assert settled_observation_ids([candidate_row(0, selected=left)], [], mapped=False) == []
    assert settled_observation_ids([raw], [], mapped=False) == []
    assert settled_observation_ids([], [], mapped=True) == []


def test_the_thread_shows_the_state_the_snapshot_has_after_a_change_back():
    s = synthetic_run()
    history = written(s)
    s.run.disposition, s.run.reasons, s.run.disposition_summary = Disposition.CLEARED, [], "Cleared."
    s.run.fields["county"] = s.run.fields["county"].model_copy(update={"state": ValueState.SUPPORTED})
    history += written(s)
    assert thread(s, history=history)["decision"]["disposition"] == "cleared"
    # Back to the first state: its rows already exist, and the thread shows them again.
    first = synthetic_run()
    result = thread(first, history=history)
    assert result["decision"]["disposition"] == "needs_human_review"
    assert by_key(result["fields"], "field_key")["county"]["state"] == "unresolved"
    assert len(result["fields"]) == len(first.run.fields)


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
    assert (result["regions"], result["tool_calls"], result["fields"], result["decision"]) == ([], [], [], None)
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


if __name__ == "__main__":
    EXAMPLE.write_text(example_json())
