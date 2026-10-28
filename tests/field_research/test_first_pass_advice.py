"""The first pass's pick is advice to the field harness (the owner, 2026-10-25).

His words: "There an LLM opinion that's put in front along with actual Raw
transcription per model to the harness if needed as then harness does its
thing per field and settles as written or derived and so on", and, asked
whether the harness should be free to settle a field on any model's raw
transcription when evidence supports it, even if the LLM pass picked a
different one: "This is exactly what should have been happening".

Each case runs the ordinary workflow's run (test_step's rig) through the
step, with label 1's first pass recorded as adjudicate records it. Until
2026-10-25 a label's decided transcript decided its text (G19's NOT_DECIDED),
and no case recorded how a label settled.

Where the first pass's verdict at the difference names its preferred reader
(the pick was confirmed against the image there), only a source's exact
confirmation overrides it; another label's agreement or a near spelling
leaves the field unresolved, for a person to choose, with a
first_pass_conflict finding (the coordinator's decision of 2026-10-25 on
#414's review). G19 lets a pick stand only where every material difference's
verdict supports it (integrity.verify_evidence checks it), so through the
step a recorded pick is always confirmed at the difference; the uncertain
verdict beside a pick is a unit case of agreement.labels.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
from types import SimpleNamespace

import pytest
import test_step as rig_module
from PIL import Image
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
    from_tgn,
    guatemalan,
    label_with,
    reasons_for,
    resolved,
    settle,
)

from specimen_digitization.application.domain import Disposition, FieldValue, Observation, Region, ValueState
from specimen_digitization.application.first_pass import (
    adjudication_record,
    alignment_units,
    synthetic_decision,
)
from specimen_digitization.application.reading_units import UNCERTAIN
from specimen_digitization.application.workflow import store_reading_units
from specimen_digitization.application.region_pixels import region_png
from specimen_digitization.field_research import agreement, experts
from specimen_digitization.field_research import step as field_step
from specimen_digitization.field_research.contracts import (
    FIELD_TOOLS,
    Candidate,
    FieldAnswer,
    FieldOutcome,
    FieldTask,
    Reading,
)
from specimen_digitization.field_research.experts import INPUT_PREFIX

LA, ONE_A = (TEXT.replace("collection_code: SYNTHETIC", f"collection_code: {code}") for code in ("la", "1a"))
CODES = every_field(("collection_code", "1A", "la", "collection_code: la"),
    ("collection_code", "1B", "1a", "collection_code: 1a"))
RATIONALE = "The first character is a lower-case l: its top is a loop, with no serif."
NOTES = ("Reads the l the image shows.", "Reads the l as a one.")
# The review's probe (#414, round 1): 1A, which the first pass preferred,
# writes "1a"; 1B and both readers of label 2 write "la", a shared misread.
PROBE_CODES = every_field(("collection_code", "1A", "1a", "collection_code: 1a"),
    ("collection_code", "1B", "la", "collection_code: la"))
LABEL_2_LA = [("collection_code", name, "la", "collection_code: la") for name in ("2A", "2B")]


def prefer(rig, reader, *, rationale=RATIONALE, notes=NOTES):
    """Label 1's first pass as adjudicate records it (first_pass.adjudication_record):
    it preferred reader `reader` (0 for 1A, 1 for 1B; None for no reader),
    with `rationale`, a note per reader and its verdict at each difference.
    On the units path (rig_module.PATH), whose first pass prefers no reader:
    label 1's units with the image naming reader `reader`'s text at each unit
    where the readers' texts differ (image_at_differences)."""
    run = rig.specimen.run
    region = run.regions[0]
    readings = [o for o in run.observations if o.region_id == region.id]
    if rig_module.PATH == "units":
        [entry] = [entry for entry in run.reading_units if entry.label == region.id]
        store_reading_units(run, [image_at_differences(entry, readings[reader].id if reader is not None else None)])
        return
    synthetic = synthetic_decision(rig.blobs, region, readings)
    # A pick stands only where every material difference's verdict supports
    # it (G19), so its verdicts name it; with no pick they are uncertain.
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


def image_at_differences(units, reader):
    """A label's units with the image at each unit where its readers' texts differ naming
    `reader`'s text there (an observation id), or uncertain when `reader` is None or wrote
    nothing there; the other units as they are."""
    return units.model_copy(update={"units": [
        unit.model_copy(update={"image": unit.readers[reader].text if reader and unit.readers[reader].text
            else UNCERTAIN}) if len({span.text for span in unit.readers.values()}) > 1 else unit
        for unit in units.units]})


def person_transcribed(run, reading, **update):
    """Label 1's transcript as a person's decision leaves it (application/api.py): reading
    `reading`'s text, resolved, with `update`; on the units path its units then come from
    the person's text (first_pass.source_units), as the decision regenerates them."""
    run.transcripts[0] = run.transcripts[0].model_copy(update={"text": reading.literal_text, "resolved": True,
        "selected_observation_id": reading.id, **update})
    if rig_module.PATH == "units":
        from specimen_digitization.application.first_pass import source_units

        store_reading_units(run, [source_units(run, run.regions[0].id)])


def with_units(readings, images=None):
    """Readings (contracts.Reading) with their label's units from the alignment
    (first_pass.alignment_units, keyed by observation id), as the workflow gives them: a
    label with one reading as the alignment leaves them, each image uncertain; one with
    two or more with each image naming the text where every reader wrote the same text
    (test_step.seen_units), and, for a label in `images` (region id to observation id or
    None), image_at_differences with that reader."""
    from dataclasses import replace

    found = {}
    for region in dict.fromkeys(reading.region_id for reading in readings):
        group = [SimpleNamespace(id=r.observation_id, literal_text=r.text) for r in readings if r.region_id == region]
        units = alignment_units(region, group)
        if len(group) > 1:
            units = rig_module.seen_units(units)
        if region in (images or {}):
            units = image_at_differences(units, images[region])
        found[region] = units
    return tuple(replace(reading, units=found[reading.region_id]) for reading in readings)


def settlement_findings(run, key):
    """The units path's findings of how each label settled the field `key` (step._settlement)."""
    return sorted((f.reason_code, f.severity) for f in run.findings
        if f.rule_id == field_step.SETTLEMENT and f.field_key == key)


def second_label_read(monkeypatch, *texts):
    """build_rig's specimen with a second label its readers read as `texts`,
    in route order; "" for a reader that read nothing, which
    extraction_readings leaves out."""
    original = rig_module.make_specimen

    def make(blobs, first=TEXT, other=None):
        specimen = original(blobs, first, other)
        run = specimen.run
        output = io.BytesIO()
        Image.new("RGB", (100, 100), "white").save(output, format="JPEG", quality=95)
        region = Region(asset_id=specimen.asset.id, x=0, y=50, width=100, height=50, order=1,
            method="synthetic_fixture_region", version="1")
        crop_png = region_png(Image.open(io.BytesIO(output.getvalue())), region)
        region.crop_ref = blobs.put(crop_png)
        run.regions.append(region)
        crop = hashlib.sha256(crop_png).hexdigest()
        for route, text in zip(run.profile.routes, texts, strict=True):
            raw = ("SYNTHETIC FIXTURE " + route + "\n" + text).encode()
            run.observations.append(Observation(region_id=region.id, route_id=route, model_id="synthetic-" + route,
                provider="synthetic", prompt_version="prompt:" + route, input_sha256=crop,
                input_asset_id=specimen.asset.id, input_crop_ref=region.crop_ref, literal_text=text,
                raw_ref=blobs.put(raw), raw_sha256=hashlib.sha256(raw).hexdigest()))
            run.completed_steps.append(f"transcribe:{region.id}:{route}")
        if len(set(texts)) > 1 and rig_module.PATH == "old":
            # Its first pass picked no reading, as make_specimen's.
            run.completed_steps.append(f"first_pass:{region.id}")
        return specimen
    monkeypatch.setattr(rig_module, "make_specimen", make)


def first_pass_findings(run):
    return sorted((f.reason_code, f.severity) for f in run.findings if f.rule_id == "first_pass_preference")


def code_answer(literal, *names):
    return FieldAnswer(outcome="resolved", literal=literal, reading_names=list(names), explanation="Settled.")


# ---- 1: another label of the specimen backs a reader the first pass did not prefer

@pytest.mark.parametrize("answer", [code_answer("la", "1B", "2A", "2B"), code_answer("1a", "1A")],
    ids=["the-shared-misread", "the-preferred-reading"])
def test_a_shared_misread_on_another_label_never_overrides_an_image_confirmed_pick(tmp_path, monkeypatch, answer,
        first_pass_path):
    """The review's probe: label 1's 1A, which the first pass preferred with
    its verdict at that very difference, writes "1a"; 1B writes "la", and so
    do both readers of label 2. No source checks the collection code. The
    other label's agreement does not outweigh the first pass's look at label
    1's image, nor does the pick outweigh it: the field is ambiguous for
    review, with a first_pass_conflict warning, whichever text the answer
    gives. Round 1 settled "la" and refused "1a"; before 2026-10-25 "la" was
    refused as NOT_DECIDED (unresolved) and "1a" as LABELS_DIFFER. On the units
    path, the image naming 1A's "1a" at the difference: label 1 settles on
    "1a" (an IMAGE backing above another label's TEXT, rule 5), label 2 on
    "la", and the labels differ: ambiguous (LABELS_DIFFER) either way."""
    a_second_label(monkeypatch, "collection_code: la")
    rig = build_rig(tmp_path, ONE_A, LA, candidates=[*PROBE_CODES, *LABEL_2_LA])
    run = rig.specimen.run
    prefer(rig, 0)
    first = run.regions[0].id
    settle(rig, Scripted({"collection_code": answering(answer)}))
    code = run.fields["collection_code"]
    assert (code.state, code.literal) == (ValueState.AMBIGUOUS, None)
    assert "mandatory_unresolved:collection_code" in run.reasons
    if first_pass_path == "units":
        assert code.reason == agreement.LABELS_DIFFER + " Settled."
        assert first_pass_findings(run) == [] and settlement_findings(run, "collection_code") == []
        return
    assert code.reason == agreement.FIRST_PASS_CONFLICT + " Settled."
    assert first_pass_findings(run) == [(f"first_pass_conflict:collection_code:{first}", "warning")]


def test_with_no_pick_another_label_whose_readers_agree_settles_the_field(tmp_path, monkeypatch, first_pass_path):
    """The probe's readings with a first pass that preferred no reader: label
    2's two readers back 1B's "la", the field settles on it, and the step
    records that label 1 had no preference to follow. Before 2026-10-25:
    ambiguous, as readers that differ. On the units path, the image
    uncertain at label 1's difference: another label alone backs "la", so it
    settles marked, and the record goes to review (rule 4)."""
    a_second_label(monkeypatch, "collection_code: la")
    rig = build_rig(tmp_path, ONE_A, LA, candidates=[*PROBE_CODES, *LABEL_2_LA])
    run = rig.specimen.run
    prefer(rig, None)
    first, second = (region.id for region in run.regions)
    settle(rig, Scripted({"collection_code": answering(code_answer("la", "1B", "2A", "2B"))}))
    code = run.fields["collection_code"]
    assert (code.state, code.literal) == (ValueState.SUPPORTED, "la")
    if first_pass_path == "units":
        assert reasons_for(run, "collection_code") == [f"marked:collection_code:{first}:text_only"]
        assert run.disposition == Disposition.REVIEW
        assert settlement_findings(run, "collection_code") == [(f"cleared:collection_code:{second}", "info"),
            (f"marked:collection_code:{first}:text_only", "warning")]
        [marked] = [f for f in run.findings if f.reason_code.startswith("marked:")]
        rows = {item.id: item for item in run.evidence}
        # Its detail: label 1's other candidate, 1A's "1a".
        assert marked.evidence_ids and all(rows[i].region_id == first and rows[i].observation_ids
            == [run.observations[0].id] for i in marked.evidence_ids)
        return
    assert not reasons_for(run, "collection_code")
    assert first_pass_findings(run) == [(f"first_pass_absent:collection_code:{first}", "info")]
    [finding] = [f for f in run.findings if f.rule_id == "first_pass_preference"]
    rows = {item.id: item for item in run.evidence}
    reader_b = run.observations[1].id
    assert finding.evidence_ids and all(rows[i].region_id == first and rows[i].observation_ids == [reader_b]
        for i in finding.evidence_ids)
    assert second not in finding.reason_code  # label 2's readers agree: nothing to follow or override


def probe_readings(verdict, *, label_2=("la", "la")):
    """The probe as agreement.labels reads it, label 1's first pass
    preferring 1A with `verdict` at the one difference ("1A", "uncertain")."""
    from specimen_digitization.field_research.contracts import FirstPassAdvice

    advice = FirstPassAdvice(preferred="1A", rationale="", reader_notes={}, differences=(
        {"texts": {"1A": "1a", "1B": "la"}, "verdict": verdict, "spans": {"1A": (17, 19), "1B": (17, 19)}},))
    label_1 = (Reading("1A", "r1", "o1a", "decided_transcript", "collection_code: 1a", first_pass=advice),
        Reading("1B", "r1", "o1b", "raw_reading", "collection_code: la", first_pass=advice))
    second = tuple(Reading(f"2{letter}", "r2", f"o2{letter}", "raw_reading", f"collection_code: {text}")
        for letter, text in zip("AB", label_2))
    readings = label_1 + second
    task = FieldTask("collection_code", True, FieldValue(state=ValueState.AMBIGUOUS),
        tuple(Candidate(r.name, r.text, r.text.split(": ")[1], "ev-" + r.name) for r in readings),
        FIELD_TOOLS["collection_code"])
    return task, readings


@pytest.mark.parametrize(("verdict", "settled", "preference"), [
    ("1A", frozenset(), "conflict"),
    ("uncertain", frozenset({"la"}), "overridden"),
    ("neither", frozenset({"la"}), "overridden"),
])
def test_another_label_overrides_a_pick_only_where_the_first_pass_did_not_confirm_it(verdict, settled, preference,
        first_pass_path):
    """agreement.labels on the probe: where the verdict at the difference
    names the preferred reader, label 2's agreement makes a conflict; where
    it is uncertain or neither (a record G19 would not let a pick stand in,
    so a unit case), it settles label 1 on "la" against the pick. On the
    units path (the probe's readings with units, the image naming 1A's "1a"
    at the difference for the verdict "1A", else uncertain): label 1 settles
    on "1a", marked with "la" listed, where the image names it (rule 5);
    else on "la", marked, as only another label backs it (rule 4)."""
    task, readings = probe_readings(verdict)
    if first_pass_path == "units":
        readings = with_units(readings, {"r1": "o1a" if verdict == "1A" else None})
        found = agreement.labels(task, readings, [])
        if verdict == "1A":
            assert (found["r1"].settled, found["r1"].why, found["r1"].others) == (
                frozenset({"1a"}), agreement.CONTESTED, ("la",))
        else:
            assert (found["r1"].settled, found["r1"].why) == (frozenset({"la"}), agreement.TEXT_ONLY)
        assert (found["r2"].settled, found["r2"].cleared) == (frozenset({"la"}), True)
        refused = agreement.refusal(task, readings, literal="la", named=[readings[1], *readings[2:]], value=None,
            authority_id=None, cited=[], received=[])
        assert (refused.reason if refused else None) == (agreement.LABELS_DIFFER if verdict == "1A" else None)
        return
    found = agreement.labels(task, readings, [])
    assert (found["r1"].settled, found["r1"].preference) == (settled, preference)
    assert found["r2"].basis == agreement.BY_AGREEMENT
    refused = agreement.refusal(task, readings, literal="la", named=[readings[1], *readings[2:]], value=None,
        authority_id=None, cited=[], received=[])
    assert (refused.reason if refused else None) == (agreement.FIRST_PASS_CONFLICT if not settled else None)


def test_a_label_one_reader_read_backs_nothing(tmp_path, monkeypatch, first_pass_path):
    """Label 2's second reader read nothing, so only 2A writes "la": one
    model's text backs no reader of label 1, whose first pass preferred no
    reader, and the field goes to review as readers that differ. Round 1
    settled it on "la"; before 2026-10-25 it went to review too. The second
    control, on the units path, which has no preferred reader to fall back on
    (agreement.BY_FIRST_PASS): label 1 does not settle either, and the answer
    is refused with the first control's reason."""
    second_label_read(monkeypatch, "collection_code: la", "")
    rig = build_rig(tmp_path, ONE_A, LA, candidates=[*PROBE_CODES, LABEL_2_LA[0]])
    run = rig.specimen.run
    prefer(rig, None)
    assert [r.name for r in field_step.run_readings(run) if r.region_id == run.regions[1].id] == ["2A"]
    settle(rig, Scripted({"collection_code": answering(code_answer("la", "1B", "2A"))}))
    code = run.fields["collection_code"]
    assert (code.state, code.literal, code.reason) == (ValueState.AMBIGUOUS, None, agreement.DIFFER + " Settled.")
    assert "mandatory_unresolved:collection_code" in run.reasons
    # With a pick whose verdict there is uncertain, label 1 follows it: the
    # one reader of label 2 backs nothing.
    task, readings = probe_readings("uncertain", label_2=("la",))
    if first_pass_path == "units":
        readings = with_units(readings, {"r1": None})
        assert agreement.labels(task, readings, [])["r1"].settled == frozenset()
        refused = agreement.refusal(task, readings, literal="1a", named=[readings[0]], value=None,
            authority_id=None, cited=[], received=[])
        assert (refused.reason, refused.differ) == (agreement.DIFFER, True)
        return
    found = agreement.labels(task, readings, [])["r1"]
    assert (found.settled, found.basis, found.preference) == (
        frozenset({"1a"}), agreement.BY_FIRST_PASS, agreement.FOLLOWED)


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

@pytest.mark.parametrize(("reader", "settles"), [(None, True), (0, False)], ids=["no-pick", "confirmed-pick"])
def test_a_place_settles_on_a_near_spelling_of_one_readers_text_unless_the_pick_was_confirmed(tmp_path,
        reader, settles, first_pass_path):
    """105526330's province, its readers apart: 1A writes "Chimaltenaqo", 1B
    "Chimaltenago". Getty TGN knows the department Chimaltenango, one letter
    from 1B's text and two from 1A's, and finds nothing for 1A's text. With
    no pick, the province settles on 1B's text as a near spelling, inside the
    settled country (G34), with its near_spelling warning; the one-letter
    bound is unchanged, so 1A's text could not settle so. Where the first
    pass preferred 1A with its verdict at that difference, a near spelling
    does not outweigh it: review, with a first_pass_conflict warning. Before
    2026-10-25: ambiguous with no pick (no near spelling among readers that
    differ), unresolved as NOT_DECIDED with one. On the units path the near
    spelling is 1B's SOURCE backing (rule 3): with the image uncertain it
    settles cleared; with the image naming 1A's text it settles too, marked,
    1A's text listed (rule 5)."""
    first, second = (label_with(**GUATEMALAN, province_state=name) for name in ("Chimaltenaqo", "Chimaltenago"))
    rig = build_rig(tmp_path, first, second, candidates=[*COLLECTORS,
        *(("country", name, "Guatemala", "country: Guatemala") for name in ("1A", "1B")),
        ("province_state", "1A", "Chimaltenaqo", "province_state: Chimaltenaqo"),
        ("province_state", "1B", "Chimaltenago", "province_state: Chimaltenago")])
    run = rig.specimen.run
    prefer(rig, reader)

    async def province(task, readings, tools):
        found = await tools.lookup("tgn", "Chimaltenango", field_key=task.key)
        missing = await tools.lookup("tgn", "Chimaltenaqo", field_key=task.key)
        return FieldOutcome(task.key, resolved("Chimaltenago", reading="1B", value="Chimaltenango",
            authority_id="tgn:1000565", cited=[found.evidence.id]), evidence=[found.evidence, missing.evidence],
            model_calls=1)
    settle(rig, guatemalan(province_state=province), tools=Gazetteer(rig.blobs))
    place = run.fields["province_state"]
    region = run.regions[0].id
    if first_pass_path == "units":
        assert (place.state, place.literal, place.normalized, place.authority_id) == (
            ValueState.SUPPORTED, "Chimaltenago", "Chimaltenango", "tgn:1000565")
        assert "near_spelling:province_state" in [f.reason_code for f in run.findings]
        if settles:
            assert not reasons_for(run, "province_state")
            assert settlement_findings(run, "province_state") == [(f"cleared:province_state:{region}", "info")]
        else:
            assert reasons_for(run, "province_state") == [f"marked:province_state:{region}:conflict"]
            assert place.reason.endswith("Marked for a person: another text has backing too: 'Chimaltenaqo'.")
        return
    if not settles:
        assert (place.state, place.literal) == (ValueState.AMBIGUOUS, None)
        assert place.reason == agreement.FIRST_PASS_CONFLICT + " Settled."
        assert "mandatory_unresolved:province_state" in run.reasons
        assert first_pass_findings(run) == [(f"first_pass_conflict:province_state:{region}", "warning")]
        return
    assert (place.state, place.literal, place.normalized, place.authority_id) == (
        ValueState.SUPPORTED, "Chimaltenago", "Chimaltenango", "tgn:1000565")
    assert not reasons_for(run, "province_state")
    codes = [f.reason_code for f in run.findings]
    assert "near_spelling:province_state" in codes
    assert first_pass_findings(run) == [(f"first_pass_absent:province_state:{region}", "info")]


class WithPazum(Gazetteer):
    """Getty TGN as Gazetteer answers it, and "Pazum", a town one letter from
    1B's "Patzum" (and two from 1A's "Patzun"), in Chimaltenango, Guatemala;
    nothing for "Patzun" or "Patzum" (the review's third finding on #414)."""

    PLACES = {**Gazetteer.PLACES, "Pazum": [("Pazum", "tgn:pazum", "inhabited places",
        (("Chimaltenango", "tgn:1000565"), ("Guatemala", "tgn:7005493")))]}


def test_a_near_spelling_of_the_other_readers_town_never_overrides_a_confirmed_pick(tmp_path, first_pass_path):
    """The review's third finding: 1A, which the first pass preferred with
    its verdict at that difference, writes the town "Patzun", 1B "Patzum".
    TGN finds nothing for either, and "Pazum", one letter from 1B's text, in
    the province and country both readers write. The near spelling of the
    other reader's text does not outweigh the first pass's look at the image:
    the city is ambiguous for review, with a first_pass_conflict warning.
    Round 1 settled it as Pazum; before 2026-10-25 it was unresolved as
    NOT_DECIDED. On the units path, the image naming 1A's "Patzun": the near
    spelling is 1B's SOURCE backing, above 1A's IMAGE (rule 5), so the city
    settles as Pazum, marked, "Patzun" listed."""
    first, second = (label_with(country="Guatemala", province_state="Chimaltenango", county=None, city=town)
        for town in ("Patzun", "Patzum"))
    rig = build_rig(tmp_path, first, second, candidates=[*COLLECTORS,
        *((key, name, text, f"{key}: {text}") for key, text in (("country", "Guatemala"),
            ("province_state", "Chimaltenango")) for name in ("1A", "1B")),
        ("city", "1A", "Patzun", "city: Patzun"), ("city", "1B", "Patzum", "city: Patzum")])
    run = rig.specimen.run
    prefer(rig, 0)

    async def city(task, readings, tools):
        asked = [await tools.lookup("tgn", query, field_key=task.key) for query in ("Patzun", "Patzum", "Pazum")]
        return FieldOutcome(task.key, resolved("Patzum", reading="1B", value="Pazum", authority_id="tgn:pazum",
            cited=[asked[2].evidence.id]), evidence=[item.evidence for item in asked], model_calls=1)
    settle(rig, guatemalan(province_state=from_tgn("Chimaltenango", "Chimaltenango", None, "tgn:1000565"),
        city=city), tools=WithPazum(rig.blobs))
    assert run.fields["province_state"].state == ValueState.SUPPORTED
    town = run.fields["city"]
    if first_pass_path == "units":
        assert (town.state, town.literal, town.normalized, town.authority_id) == (
            ValueState.SUPPORTED, "Patzum", "Pazum", "tgn:pazum")
        assert reasons_for(run, "city") == [f"marked:city:{run.regions[0].id}:conflict"]
        assert town.reason.endswith("Marked for a person: another text has backing too: 'Patzun'.")
        return
    assert (town.state, town.literal, town.reason) == (ValueState.AMBIGUOUS, None,
        agreement.FIRST_PASS_CONFLICT + " Settled.")
    assert "mandatory_unresolved:city" in run.reasons
    assert first_pass_findings(run) == [(f"first_pass_conflict:city:{run.regions[0].id}", "warning")]


def test_a_source_confirming_the_other_readers_place_overrides_a_pick_that_wrote_none(tmp_path, first_pass_path):
    """The review's second finding: 1A, which the first pass preferred, writes
    no province; 1B writes "Chimaltenango", which Getty TGN confirms by its
    own name as a department of Guatemala, the country both write. A
    source's exact confirmation outweighs the pick, even where the first
    pass judged the image there: the province settles on 1B's text, and the
    step records that label 1 overrode its first pass. Before 2026-10-25:
    unresolved as NOT_DECIDED. On the units path its one text has a SOURCE
    backing, and the province settles cleared."""
    first = label_with(country="Guatemala", province_state=None, county=None, city=None)
    second = label_with(country="Guatemala", province_state="Chimaltenango", county=None, city=None)
    rig = build_rig(tmp_path, first, second, candidates=[*COLLECTORS,
        *(("country", name, "Guatemala", "country: Guatemala") for name in ("1A", "1B")),
        ("province_state", "1B", "Chimaltenango", "province_state: Chimaltenango")])
    run = rig.specimen.run
    prefer(rig, 0)
    if first_pass_path == "old":
        assert any(d.verdict == run.observations[0].id for d in run.transcripts[0].differences)

    async def province(task, readings, tools):
        found = await tools.lookup("tgn", "Chimaltenango", field_key=task.key)
        return FieldOutcome(task.key, resolved("Chimaltenango", reading="1B", authority_id="tgn:1000565",
            cited=[found.evidence.id]), evidence=[found.evidence], model_calls=1)
    settle(rig, guatemalan(province_state=province), tools=Gazetteer(rig.blobs))
    place = run.fields["province_state"]
    assert (place.state, place.literal, place.authority_id) == (ValueState.SUPPORTED, "Chimaltenango", "tgn:1000565")
    assert not reasons_for(run, "province_state")
    if first_pass_path == "units":
        assert settlement_findings(run, "province_state") == [(f"cleared:province_state:{run.regions[0].id}", "info")]
        return
    assert first_pass_findings(run) == [(f"first_pass_overridden:province_state:{run.regions[0].id}", "info")]


# ---- 3: nothing supports the other reader: the first pass's preference is followed

@pytest.mark.parametrize(("literal", "reading", "settles"), [("la", "1A", True), ("1a", "1B", False)])
def test_a_field_no_source_checks_follows_the_first_pass_when_nothing_backs_the_other_reader(tmp_path,
        literal, reading, settles, first_pass_path):
    """One label: 1A, which the first pass preferred, writes "la", 1B "1a",
    and no source checks the collection code. 1A's text settles, and the step
    records that the label followed its first pass; 1B's text, which nothing
    backs, is ambiguous for review. On the units path the image names 1A's
    "la": an IMAGE backing, cleared (rule 4)."""
    rig = build_rig(tmp_path, LA, ONE_A, candidates=CODES)
    run = rig.specimen.run
    prefer(rig, 0)
    settle(rig, Scripted({"collection_code": answering(code_answer(literal, reading))}))
    code = run.fields["collection_code"]
    if settles:
        assert (code.state, code.literal) == (ValueState.SUPPORTED, "la")
        if first_pass_path == "units":
            assert settlement_findings(run, "collection_code") == [(f"cleared:collection_code:{run.regions[0].id}", "info")]
            assert not reasons_for(run, "collection_code")
            return
        assert first_pass_findings(run) == [(f"first_pass_followed:collection_code:{run.regions[0].id}", "info")]
        return
    assert (code.state, code.literal) == (ValueState.AMBIGUOUS, None)
    assert code.reason == agreement.DIFFER + " Settled."
    assert first_pass_findings(run) == []


# ---- 4: the experts receive the first pass's opinion beside the raw readings

def test_each_expert_receives_each_labels_first_pass_opinion_beside_the_raw_readings(tmp_path, first_pass_path):
    """The request names the reader the first pass preferred, its rationale,
    its note on each reader and each material difference with its verdict,
    by label number and reader name. Before 2026-10-25 the experts never saw
    them. On the units path the request carries the label's units in place
    of that opinion (experts.units_document), the unit at the difference
    with the image naming 1A's text."""
    rig = build_rig(tmp_path, LA, ONE_A, candidates=CODES)
    run = rig.specimen.run
    prefer(rig, 0)
    readings = field_step.run_readings(run)
    [task] = [task for task in field_step.build_tasks(run)[1] if task.key == "collection_code"]
    made = experts._Expert(task, readings, SimpleNamespace(sources=()), None)
    document = json.loads(made.prompt({"habitat": FieldValue()}).removeprefix(INPUT_PREFIX))
    if first_pass_path == "units":
        assert "first_pass" not in document
        assert document["units"] == {"1": experts.units_document(readings)["1"]}
        [unit] = [unit for unit in document["units"]["1"] if unit["readers"] == {"1A": "la", "1B": "1a"}]
        assert unit["image"] == "la"
        assert len(document["units"]["1"]) == len(run.reading_units[0].units)
        assert [(r["name"], r["input_source"]) for r in document["readings"]] == [
            ("1A", "raw_reading"), ("1B", "raw_reading")]
        return
    assert document["first_pass"] == {"1": {"preferred": "1A", "rationale": RATIONALE,
        "reader_notes": {"1A": NOTES[0], "1B": NOTES[1]},
        "differences": [{"texts": {"1A": "la", "1B": "1a"}, "verdict": "1A"}]}}
    assert [(r["name"], r["input_source"]) for r in document["readings"]] == [
        ("1A", "decided_transcript"), ("1B", "raw_reading")]


def test_a_first_pass_that_preferred_no_reader_still_reaches_the_experts(tmp_path, first_pass_path):
    rig = build_rig(tmp_path, LA, ONE_A, candidates=CODES)
    run = rig.specimen.run
    prefer(rig, None)
    readings = field_step.run_readings(run)
    assert {r.input_source for r in readings} == {"raw_reading"}
    [task] = [task for task in field_step.build_tasks(run)[1] if task.key == "collection_code"]
    document = json.loads(experts._Expert(task, readings, SimpleNamespace(sources=()), None).prompt({})
        .removeprefix(INPUT_PREFIX))
    if first_pass_path == "units":
        # The units path: the units, the image uncertain at the difference.
        assert "first_pass" not in document
        [unit] = [unit for unit in document["units"]["1"] if unit["readers"] == {"1A": "la", "1B": "1a"}]
        assert unit["image"] == UNCERTAIN
        return
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


@pytest.mark.parametrize(("literal", "reading", "value", "settles"), [
    ("Chimaltenago", "1A", "Chimaltenango", True), ("Chimaltenango", "1B", None, False)])
def test_a_person_decided_transcript_binds_its_label_against_an_exact_source_match(tmp_path, literal, reading,
        value, settles, first_pass_path):
    """A reviewer transcribed label 1 as 1A's "Chimaltenago"; reader 1B wrote
    "Chimaltenango", which Getty TGN confirms by its own name, finding
    nothing for "Chimaltenago". The person saw the image, so the label's
    text stays theirs, whatever the sources say (the coordinator's ruling of
    2026-10-25): the value still normalises to TGN's department through the
    one-letter near spelling of the person's own text, inside the settled
    country, while 1B's text, an exact match, is refused. No first pass
    opinion reaches the experts for such a label. On the units path the same
    (rule 2), the label's units from the person's text, and the label
    settles on the rule's binding step (agreement.BY_PERSON), cleared."""
    first, second = (label_with(**GUATEMALAN, province_state=name) for name in ("Chimaltenago", "Chimaltenango"))
    rig = build_rig(tmp_path, first, second, candidates=[*COLLECTORS,
        *(("country", name, "Guatemala", "country: Guatemala") for name in ("1A", "1B")),
        ("province_state", "1A", "Chimaltenago", "province_state: Chimaltenago"),
        ("province_state", "1B", "Chimaltenango", "province_state: Chimaltenango")])
    run = rig.specimen.run
    reader_a = run.observations[0]
    person_transcribed(run, reader_a, actor="reviewer@example.org", reason="The label reads Chimaltenago.")
    readings = field_step.run_readings(run)
    assert [(r.name, r.input_source, r.first_pass.person_decided) for r in readings] == [
        ("1A", "decided_transcript", True), ("1B", "raw_reading", True)]
    [task] = [task for task in field_step.build_tasks(run)[1] if task.key == "collection_code"]
    document = json.loads(experts._Expert(task, readings, SimpleNamespace(sources=()), None).prompt({})
        .removeprefix(INPUT_PREFIX))
    assert "first_pass" not in document

    async def province(task, readings, tools):
        found = await tools.lookup("tgn", "Chimaltenango", field_key=task.key)
        missing = await tools.lookup("tgn", "Chimaltenago", field_key=task.key)
        return FieldOutcome(task.key, resolved(literal, reading=reading, value=value, authority_id="tgn:1000565",
            cited=[found.evidence.id]), evidence=[found.evidence, missing.evidence], model_calls=1)
    settle(rig, guatemalan(province_state=province), tools=Gazetteer(rig.blobs))
    place = run.fields["province_state"]
    if settles:
        assert (place.state, place.literal, place.normalized, place.authority_id) == (
            ValueState.SUPPORTED, "Chimaltenago", "Chimaltenango", "tgn:1000565")
        assert "near_spelling:province_state" in [f.reason_code for f in run.findings]
        if first_pass_path == "units":
            task = FieldTask("province_state", True, FieldValue(), tuple(Candidate(name, "", text, "ev-" + name)
                for name, text in (("1A", "Chimaltenago"), ("1B", "Chimaltenango"))), FIELD_TOOLS["province_state"])
            label = agreement.labels(task, readings, [])[run.regions[0].id]
            assert (label.basis, label.cleared, label.settled) == (
                agreement.BY_PERSON, True, frozenset({"Chimaltenago"}))
            assert settlement_findings(run, "province_state") == [(f"cleared:province_state:{run.regions[0].id}", "info")]
        return
    assert (place.state, place.literal) == (ValueState.AMBIGUOUS, None)
    assert place.reason == agreement.PERSON_DECIDED + " Settled."


def test_an_expert_naming_another_reader_of_a_person_decided_label_is_told_to_answer_with_the_persons(tmp_path):
    """Round 2 of #414's review: the real resolver's expert first answers
    with 1B's "Chimaltenango", which TGN confirms exactly, on a label a
    reviewer transcribed as 1A's "Chimaltenago". Its check sends it back
    naming the person's reading 1A (PERSON_DECIDED); it answers again with
    1A's text, the department as the value, and the field settles on the
    person's literal with the value normalised through the near spelling.
    The request names the label and its reading under person_decided."""
    from pydantic_ai.messages import ModelRequest, ModelResponse, RetryPromptPart, ToolCallPart, ToolReturnPart
    from pydantic_ai.models.function import FunctionModel

    from specimen_digitization.field_research.budget import CostMeter

    first, second = (label_with(**GUATEMALAN, province_state=name) for name in ("Chimaltenago", "Chimaltenango"))
    rig = build_rig(tmp_path, first, second, candidates=[*COLLECTORS,
        *(("country", name, "Guatemala", "country: Guatemala") for name in ("1A", "1B")),
        ("province_state", "1A", "Chimaltenago", "province_state: Chimaltenago"),
        ("province_state", "1B", "Chimaltenango", "province_state: Chimaltenango")])
    run = rig.specimen.run
    reader_a = run.observations[0]
    person_transcribed(run, reader_a, actor="reviewer@example.org")
    retries, prompts = [], []

    def model(messages, info):
        requests = [m for m in messages if isinstance(m, ModelRequest)]
        prompts.extend(part.content for part in requests[0].parts if part.part_kind == "user-prompt")
        returns = [part.content for m in requests for part in m.parts if isinstance(part, ToolReturnPart)]
        retries.extend(part.model_response() for m in requests[-1:] for part in m.parts
            if isinstance(part, RetryPromptPart))
        if not returns:
            return ModelResponse(parts=[ToolCallPart("lookup", {"source": "tgn", "query": query})
                for query in ("Chimaltenango", "Chimaltenago")])
        found = next(r for r in returns if r.get("query") == "Chimaltenango")
        cited = {"authority_id": "tgn:1000565", "source_evidence_ids": [found["evidence_id"]]}
        answer = ({"outcome": "resolved", "literal": "Chimaltenago", "reading_names": ["1A"],
                   "value": "Chimaltenango", **cited} if retries else
                  {"outcome": "resolved", "literal": "Chimaltenango", "reading_names": ["1B"], **cited})
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,
            {**answer, "explanation": "TGN holds the department."})])

    resolver = experts.make_resolver(model_factory=lambda: FunctionModel(model),
        meter=CostMeter(1_000_000, input_micros_per_million=200_000, output_micros_per_million=600_000))

    async def province(task, readings, tools):
        return await resolver(task, readings, {}, tools=tools)
    settle(rig, guatemalan(province_state=province), tools=Gazetteer(rig.blobs))
    assert retries and "A person transcribed this label: reading 1A holds their transcription" in retries[0]
    assert "'Chimaltenago'" in retries[0]
    assert json.loads(prompts[0].removeprefix(INPUT_PREFIX))["person_decided"] == {"1": "1A"}
    place = run.fields["province_state"]
    assert (place.state, place.literal, place.normalized, place.authority_id) == (
        ValueState.SUPPORTED, "Chimaltenago", "Chimaltenango", "tgn:1000565")


def test_a_verdict_on_a_word_that_only_contains_the_other_readers_text_is_no_conflict():
    """Round 2 of #414's review: 1B writes "la" inside "Guatemala" and as the
    code. The first pass confirmed its preferred 1A at "Guatemalo" against
    "Guatemala" and was uncertain at the code. Only the code word is where
    1B writes its text, so label 2's agreement settles label 1 on "la"
    (round 2's head read "la" inside "Guatemala" and made a conflict)."""
    from specimen_digitization.field_research.contracts import FirstPassAdvice

    assert agreement._places("Guatemala, code la", "la") == [(16, 18)]
    advice = FirstPassAdvice(preferred="1A", rationale="", reader_notes={}, differences=(
        {"texts": {"1A": "Guatemalo", "1B": "Guatemala"}, "verdict": "1A", "spans": {"1A": (0, 9), "1B": (0, 9)}},
        {"texts": {"1A": "1a", "1B": "la"}, "verdict": "uncertain", "spans": {"1A": (16, 18), "1B": (16, 18)}}))
    readings = (Reading("1A", "r1", "o1a", "decided_transcript", "Guatemalo, code 1a", first_pass=advice),
        Reading("1B", "r1", "o1b", "raw_reading", "Guatemala, code la", first_pass=advice),
        Reading("2A", "r2", "o2a", "raw_reading", "code la"), Reading("2B", "r2", "o2b", "raw_reading", "code la"))
    literals = {"1A": "1a", "1B": "la", "2A": "la", "2B": "la"}
    task = FieldTask("collection_code", True, FieldValue(state=ValueState.AMBIGUOUS),
        tuple(Candidate(r.name, r.text, literals[r.name], "ev-" + r.name) for r in readings),
        FIELD_TOOLS["collection_code"])
    found = agreement.labels(task, readings, [])["r1"]
    assert (found.settled, found.preference) == (frozenset({"la"}), "overridden")


# ---- t1-329 (the real-run measurement of 2026-10-25) ------------------------
# Reader 1A, the first pass's pick, writes "Chimaltenago,", reader 1B
# "Chimaltenango,"; the first pass's verdict at that difference names 1A.

T1_329 = [label_with(country="Guatemala", province_state=name, county=None, city=None)
    for name in ("Chimaltenago,", "Chimaltenango,")]


def t1_329_rig(tmp_path, province_readers=("1A", "1B")):
    """The t1-329 shape: the organiser's province candidates for
    `province_readers` (1A "Chimaltenago", 1B "Chimaltenango") and the
    country for both; the first pass preferred 1A."""
    texts = {"1A": "Chimaltenago", "1B": "Chimaltenango"}
    rig = build_rig(tmp_path, *T1_329, candidates=[*COLLECTORS,
        *(("country", name, "Guatemala", "country: Guatemala") for name in ("1A", "1B")),
        *(("province_state", name, texts[name], f"province_state: {texts[name]},") for name in province_readers)])
    prefer(rig, 0)
    return rig


def province_on(literal, reading, value=None):
    async def script(task, readings, tools):
        found = await tools.lookup("tgn", "Chimaltenango", field_key=task.key)
        missing = await tools.lookup("tgn", "Chimaltenago", field_key=task.key)
        return FieldOutcome(task.key, resolved(literal, reading=reading, value=value, authority_id="tgn:1000565",
            cited=[found.evidence.id]), evidence=[found.evidence, missing.evidence], model_calls=1)
    return script


@pytest.mark.parametrize(("literal", "reading", "value", "settles"), [
    ("Chimaltenago", "1A", "Chimaltenango", True), ("Chimaltenango", "1B", None, False)])
def test_a_source_confirming_the_other_readers_one_letter_correction_keeps_the_preferred_spelling(tmp_path,
        literal, reading, value, settles, first_pass_path):
    """TGN confirms 1B's "Chimaltenango" by its own name and finds nothing for
    1A's "Chimaltenago". The first pass confirmed 1A's spelling against the
    image, so the label writes "Chimaltenago": the province's literal is 1A's
    and its value the department, through a near spelling of 1B's
    correction, with near_spelling and first_pass_followed (no override), the
    reason naming reader 1B. An answer with 1B's text is sent back for 1A's.
    The real run (Wikidata, "Chimaltenango Department") settled 1B's
    literal with first_pass_overridden, as did this branch before the fix.
    On the units path, the image naming 1A's text: rule 1's merge, one
    candidate, 1A's literal, the department its value, cleared; only the
    finding is another (cleared in place of first_pass_followed)."""
    rig = t1_329_rig(tmp_path)
    run = rig.specimen.run
    settle(rig, guatemalan(province_state=province_on(literal, reading, value)), tools=Gazetteer(rig.blobs))
    place = run.fields["province_state"]
    region = run.regions[0].id
    if not settles:
        assert (place.state, place.literal) == (ValueState.AMBIGUOUS, None)
        assert first_pass_findings(run) == [] and settlement_findings(run, "province_state") == []
        readings = field_step.run_readings(run)
        [task] = [task for task in field_step.build_tasks(run)[1] if task.key == "province_state"]
        answers = [asyncio.run(Gazetteer(rig.blobs).lookup("tgn", query, field_key="province_state"))
            for query in ("Chimaltenango", "Chimaltenago")]
        refused = agreement.refusal(task, readings, literal="Chimaltenango", named=[readings[1]], value=None,
            authority_id="tgn:1000565", cited=answers[:1], received=answers)
        assert "Your source confirms reader 1B's 'Chimaltenango'" in refused.retry
        assert "the label writes 'Chimaltenago'" in refused.retry
        return
    assert (place.state, place.literal, place.normalized, place.authority_id) == (
        ValueState.SUPPORTED, "Chimaltenago", "Chimaltenango", "tgn:1000565")
    assert "near_spelling:province_state" in [f.reason_code for f in run.findings]
    if first_pass_path == "units":
        assert settlement_findings(run, "province_state") == [(f"cleared:province_state:{region}", "info")]
        assert not reasons_for(run, "province_state")
    else:
        assert first_pass_findings(run) == [(f"first_pass_followed:province_state:{region}", "info")]
    assert "reader 1B's 'Chimaltenango'" in place.reason


class WithMunicipio(Gazetteer):
    """Gazetteer, with the municipio of Chimaltenango, a second-level unit
    inside the department, among TGN's answer for "Chimaltenango" (as
    Wikidata's Q1002552 stood beside the department in the real run)."""

    PLACES = {**Gazetteer.PLACES, "Chimaltenango": [*Gazetteer.PLACES["Chimaltenango"],
        ("Chimaltenango", "tgn:chimaltenango-municipio", "second level subdivisions (political entities)",
            (("Chimaltenango", "tgn:1000565"), ("Guatemala", "tgn:7005493")))]}


def test_a_county_never_takes_another_readers_spelling_of_the_settled_province(tmp_path, first_pass_path):
    """t1-329's county: the organiser filed the province only from 1B, so 1A
    writes no province text, and the province settles on 1B's
    "Chimaltenango" by TGN's exact match. The county's expert then read 1A's
    "Chimaltenago," from the transcript, one letter from the municipio
    Chimaltenango, in Guatemala: the same word of the label as the
    province's, in another reader's spelling, so it is refused
    (IS_THE_PROVINCE) and the county does not settle. The real run settled
    it as "Chimaltenago,", which the reference scores wrong. On the units
    path, which prefers no reader, the county's text read from 1A's
    transcript is refused before that check: 1B writes another text there
    (NOT_EVERY_READER), and the county is ambiguous."""
    rig = t1_329_rig(tmp_path, province_readers=("1B",))
    run = rig.specimen.run

    async def county(task, readings, tools):
        found = await tools.lookup("tgn", "Chimaltenango", field_key=task.key)
        missing = await tools.lookup("tgn", "Chimaltenago", field_key=task.key)
        return FieldOutcome(task.key, resolved("Chimaltenago,", reading="1A", value="Chimaltenango",
            authority_id="tgn:chimaltenango-municipio", cited=[found.evidence.id]),
            evidence=[found.evidence, missing.evidence], model_calls=1)
    settle(rig, guatemalan(province_state=province_on("Chimaltenango", "1B"), county=county),
        tools=WithMunicipio(rig.blobs))
    province = run.fields["province_state"]
    assert (province.state, province.literal) == (ValueState.SUPPORTED, "Chimaltenango")
    place = run.fields["county"]
    if first_pass_path == "units":
        assert (place.state, place.literal) == (ValueState.AMBIGUOUS, None)
        assert place.reason.startswith(agreement.NOT_EVERY_READER)
    else:
        assert (place.state, place.literal) == (ValueState.UNRESOLVED, None)
        assert place.reason.startswith(agreement.IS_THE_PROVINCE)
    assert "mandatory_unresolved:county" in run.reasons
    assert "near_spelling:county" not in [f.reason_code for f in run.findings]


def test_another_readers_spelling_of_a_settled_text_of_another_kind_is_taken():
    """The same rule for fields of different kinds (step._taken): the
    collectors settled on 1A's "J. Smith", and the habitat's expert read
    1B's "J. Smyth" from the transcript, one letter from it on the same
    label. Before, only the same string claimed text, so the habitat
    settled on the collector's name."""
    readings = (Reading("1A", "r1", "o1a", "raw_reading", "Guatemala\nleg. J. Smith"),
        Reading("1B", "r1", "o1b", "raw_reading", "Guatemala\nleg. J. Smyth"))
    tasks = {key: FieldTask(key, True, FieldValue(), (), FIELD_TOOLS[key]) for key in ("collectors", "habitat")}
    outcomes = [FieldOutcome("collectors", FieldAnswer(outcome="resolved", literal="J. Smith", reading_names=["1A"],
            explanation="Settled.")),
        FieldOutcome("habitat", FieldAnswer(outcome="resolved", literal="J. Smyth", reading_names=["1B"],
            explanation="Settled."))]
    settled = {"collectors": FieldValue(state=ValueState.SUPPORTED, literal="J. Smith", layer="verbatim",
        source_region_id="r1")}
    run = SimpleNamespace(evidence=[], fields={}, dependencies={})
    taken = field_step._taken(run, tasks, outcomes, readings, settled)
    assert taken == {"habitat": field_step.Taken("collectors")}
    assert not field_step._spelled_alike("1a", "la") and field_step._spelled_alike("J. Smyth,", "j. smith")
