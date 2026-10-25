"""The first pass's pick is advice to the field harness (the owner, 2026-10-25).

His words: "There an LLM opinion that's put in front along with actual Raw
transcription per model to the harness if needed as then harness does its
thing per field and settles as written or derived and so on", and, asked
whether the harness should be free to settle a field on any model's raw
transcription when evidence supports it, even if the LLM pass picked a
different one: "This is exactly what should have been happening".

Each case runs the ordinary workflow's run (test_step's rig) through the
step, with label 1's first pass recorded as adjudicate records it. Until
2026-10-25 a label's decided transcript decided its text (G19's NOT_DECIDED):
cases 1 and 2 went to review, and no case recorded how a label settled.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from test_step import (
    COLLECTORS,
    GUATEMALAN,
    TEXT,
    Gazetteer,
    Scripted,
    a_second_label,
    answering,
    build_rig,
    every_field,
    guatemalan,
    label_with,
    reasons_for,
    resolved,
    settle,
)

from specimen_digitization.application.domain import FieldValue, ValueState
from specimen_digitization.application.first_pass import adjudication_record, synthetic_decision
from specimen_digitization.field_research import agreement, experts
from specimen_digitization.field_research import step as field_step
from specimen_digitization.field_research.contracts import FieldAnswer, FieldOutcome
from specimen_digitization.field_research.experts import INPUT_PREFIX

LA, ONE_A = (TEXT.replace("collection_code: SYNTHETIC", f"collection_code: {code}") for code in ("la", "1a"))
CODES = every_field(("collection_code", "1A", "la", "collection_code: la"),
    ("collection_code", "1B", "1a", "collection_code: 1a"))
RATIONALE = "The first character is a lower-case l: its top is a loop, with no serif."
NOTES = ("Reads the l the image shows.", "Reads the l as a one.")


def prefer(rig, reader, *, rationale=RATIONALE, notes=NOTES):
    """Label 1's first pass as adjudicate records it (first_pass.adjudication_record):
    it preferred reader `reader` (0 for 1A, 1 for 1B; None for no reader),
    with `rationale`, a note per reader and its verdict at each difference."""
    run = rig.specimen.run
    region = run.regions[0]
    readings = [o for o in run.observations if o.region_id == region.id]
    synthetic = synthetic_decision(rig.blobs, region, readings)
    chosen = readings[reader].id if reader is not None else None
    decision = synthetic.model_copy(update={"selected_observation_id": chosen, "rationale": rationale,
        "notes": {o.id: note for o, note in zip(readings, notes)},
        "differences": [d.model_copy(update={"verdict": chosen or "uncertain"}) for d in synthetic.differences]})
    texts = list(dict.fromkeys(o.literal_text for o in readings))
    text, resolved_, record = adjudication_record(readings, texts, False, decision)
    run.first_pass_decisions = [*run.first_pass_decisions, decision]
    index = next(i for i, t in enumerate(run.transcripts) if t.region_id == region.id)
    run.transcripts[index] = run.transcripts[index].model_copy(update={"text": text, "resolved": resolved_,
        **record})


def first_pass_findings(run):
    return sorted((f.reason_code, f.severity) for f in run.findings if f.rule_id == "first_pass_preference")


def code_answer(literal, *names):
    return FieldAnswer(outcome="resolved", literal=literal, reading_names=list(names), explanation="Settled.")


# ---- 1: another label of the specimen backs a reader the first pass did not prefer

@pytest.mark.parametrize(("reader", "status"), [(0, "overridden"), (None, "absent")])
def test_another_label_whose_readers_agree_settles_a_field_against_the_first_pass(tmp_path, monkeypatch,
        reader, status):
    """Label 1: 1A writes the code "la", 1B "1a"; its first pass preferred 1A
    (or no reader). Label 2: both readers write "1a". No source checks the
    collection code. Label 2 corroborates 1B's text, so the field settles on
    "1a", and the step records that label 1 overrode its first pass's
    preference (or had none). Before 2026-10-25: unresolved as NOT_DECIDED,
    or ambiguous as readers that differ."""
    a_second_label(monkeypatch, "collection_code: 1a")
    rig = build_rig(tmp_path, LA, ONE_A, candidates=[*CODES, *(("collection_code", name, "1a",
        "collection_code: 1a") for name in ("2A", "2B"))])
    run = rig.specimen.run
    prefer(rig, reader)
    first, second = (region.id for region in run.regions)
    settle(rig, Scripted({"collection_code": answering(code_answer("1a", "1B", "2A", "2B"))}))
    code = run.fields["collection_code"]
    assert (code.state, code.literal) == (ValueState.SUPPORTED, "1a")
    assert not reasons_for(run, "collection_code")
    assert first_pass_findings(run) == [(f"first_pass_{status}:collection_code:{first}", "info")]
    [finding] = [f for f in run.findings if f.rule_id == "first_pass_preference"]
    rows = {item.id: item for item in run.evidence}
    reader_b = run.observations[1].id
    assert finding.evidence_ids and all(rows[i].region_id == first and rows[i].observation_ids == [reader_b]
        for i in finding.evidence_ids)
    assert second not in finding.reason_code  # label 2's readers agree: nothing to follow or override


def test_without_another_labels_text_the_label_follows_its_first_pass(tmp_path, monkeypatch):
    """The control: label 2 writes "2b", which backs neither reader of label
    1. Label 1 settles on the first pass's preferred 1A ("la"), label 2 on
    "2b": the labels differ, as before."""
    a_second_label(monkeypatch, "collection_code: 2b")
    rig = build_rig(tmp_path, LA, ONE_A, candidates=[*CODES, *(("collection_code", name, "2b",
        "collection_code: 2b") for name in ("2A", "2B"))])
    run = rig.specimen.run
    prefer(rig, 0)
    settle(rig, Scripted({"collection_code": answering(code_answer("1a", "1B"))}))
    code = run.fields["collection_code"]
    assert (code.state, code.reason) == (ValueState.AMBIGUOUS, agreement.LABELS_DIFFER + " Settled.")
    assert first_pass_findings(run) == []


# ---- 2: a place's near spelling of a reader the first pass did not prefer

def test_a_place_settles_on_the_near_spelling_of_a_reader_the_first_pass_did_not_prefer(tmp_path):
    """105526330's province, its readers apart: 1A, which the first pass
    preferred, writes "Chimaltenaqo", 1B "Chimaltenago". Getty TGN knows the
    department Chimaltenango, one letter from 1B's text and two from 1A's,
    and finds nothing for 1A's text. The province settles on 1B's text as a
    near spelling, inside the settled country (G34), with its near_spelling
    warning, and the step records that label 1 overrode its first pass. The
    one-letter bound is unchanged: 1A's text could not settle so. Before
    2026-10-25: unresolved as NOT_DECIDED."""
    first, second = (label_with(**GUATEMALAN, province_state=name) for name in ("Chimaltenaqo", "Chimaltenago"))
    rig = build_rig(tmp_path, first, second, candidates=[*COLLECTORS,
        *(("country", name, "Guatemala", "country: Guatemala") for name in ("1A", "1B")),
        ("province_state", "1A", "Chimaltenaqo", "province_state: Chimaltenaqo"),
        ("province_state", "1B", "Chimaltenago", "province_state: Chimaltenago")])
    run = rig.specimen.run
    prefer(rig, 0)

    async def province(task, readings, tools):
        found = await tools.lookup("tgn", "Chimaltenango", field_key=task.key)
        missing = await tools.lookup("tgn", "Chimaltenaqo", field_key=task.key)
        return FieldOutcome(task.key, resolved("Chimaltenago", reading="1B", value="Chimaltenango",
            authority_id="tgn:1000565", cited=[found.evidence.id]), evidence=[found.evidence, missing.evidence],
            model_calls=1)
    settle(rig, guatemalan(province_state=province), tools=Gazetteer(rig.blobs))
    place = run.fields["province_state"]
    assert (place.state, place.literal, place.normalized, place.authority_id) == (
        ValueState.SUPPORTED, "Chimaltenago", "Chimaltenango", "tgn:1000565")
    assert not reasons_for(run, "province_state")
    codes = [f.reason_code for f in run.findings]
    assert "near_spelling:province_state" in codes
    assert first_pass_findings(run) == [(f"first_pass_overridden:province_state:{run.regions[0].id}", "info")]


# ---- 3: nothing supports the other reader: the first pass's preference is followed

@pytest.mark.parametrize(("literal", "reading", "settles"), [("la", "1A", True), ("1a", "1B", False)])
def test_a_field_no_source_checks_follows_the_first_pass_when_nothing_backs_the_other_reader(tmp_path,
        literal, reading, settles):
    """One label: 1A, which the first pass preferred, writes "la", 1B "1a",
    and no source checks the collection code. 1A's text settles, and the step
    records that the label followed its first pass; 1B's text, which nothing
    backs, is ambiguous for review."""
    rig = build_rig(tmp_path, LA, ONE_A, candidates=CODES)
    run = rig.specimen.run
    prefer(rig, 0)
    settle(rig, Scripted({"collection_code": answering(code_answer(literal, reading))}))
    code = run.fields["collection_code"]
    if settles:
        assert (code.state, code.literal) == (ValueState.SUPPORTED, "la")
        assert first_pass_findings(run) == [(f"first_pass_followed:collection_code:{run.regions[0].id}", "info")]
        return
    assert (code.state, code.literal) == (ValueState.AMBIGUOUS, None)
    assert code.reason == agreement.DIFFER + " Settled."
    assert first_pass_findings(run) == []


# ---- 4: the experts receive the first pass's opinion beside the raw readings

def test_each_expert_receives_each_labels_first_pass_opinion_beside_the_raw_readings(tmp_path):
    """The request names the reader the first pass preferred, its rationale,
    its note on each reader and each material difference with its verdict,
    by label number and reader name. Before 2026-10-25 the experts never saw
    them."""
    rig = build_rig(tmp_path, LA, ONE_A, candidates=CODES)
    run = rig.specimen.run
    prefer(rig, 0)
    readings = field_step.run_readings(run)
    [task] = [task for task in field_step.build_tasks(run)[1] if task.key == "collection_code"]
    made = experts._Expert(task, readings, SimpleNamespace(sources=()), None)
    document = json.loads(made.prompt({"habitat": FieldValue()}).removeprefix(INPUT_PREFIX))
    assert document["first_pass"] == {"1": {"preferred": "1A", "rationale": RATIONALE,
        "reader_notes": {"1A": NOTES[0], "1B": NOTES[1]},
        "differences": [{"texts": {"1A": "la", "1B": "1a"}, "verdict": "1A"}]}}
    assert [(r["name"], r["input_source"]) for r in document["readings"]] == [
        ("1A", "decided_transcript"), ("1B", "raw_reading")]


def test_a_first_pass_that_preferred_no_reader_still_reaches_the_experts(tmp_path):
    rig = build_rig(tmp_path, LA, ONE_A, candidates=CODES)
    run = rig.specimen.run
    prefer(rig, None)
    readings = field_step.run_readings(run)
    assert {r.input_source for r in readings} == {"raw_reading"}
    [task] = [task for task in field_step.build_tasks(run)[1] if task.key == "collection_code"]
    document = json.loads(experts._Expert(task, readings, SimpleNamespace(sources=()), None).prompt({})
        .removeprefix(INPUT_PREFIX))
    assert document["first_pass"]["1"]["preferred"] is None
    assert document["first_pass"]["1"]["differences"] == [{"texts": {"1A": "la", "1B": "1a"},
        "verdict": "uncertain"}]


# ---- 5: no first pass, readers that differ, nothing else: unchanged

def test_with_no_first_pass_readers_that_differ_still_go_to_review(tmp_path):
    """No first pass was recorded for the label (the rig's), its readers
    differ and no source or other label backs either: ambiguous for review,
    as before, and the experts' request has no first_pass."""
    rig = build_rig(tmp_path, LA, ONE_A, candidates=CODES)
    run = rig.specimen.run
    readings = field_step.run_readings(run)
    assert all(r.first_pass is None for r in readings)
    [task] = [task for task in field_step.build_tasks(run)[1] if task.key == "collection_code"]
    document = json.loads(experts._Expert(task, readings, SimpleNamespace(sources=()), None).prompt({})
        .removeprefix(INPUT_PREFIX))
    assert "first_pass" not in document
    settle(rig, Scripted({"collection_code": answering(code_answer("la", "1A"))}))
    code = run.fields["collection_code"]
    assert (code.state, code.literal, code.reason) == (ValueState.AMBIGUOUS, None, agreement.DIFFER + " Settled.")
    assert first_pass_findings(run) == []
