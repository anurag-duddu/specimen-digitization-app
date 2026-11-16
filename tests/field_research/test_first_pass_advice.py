"""No reader is preferred: each label settles by the settlement rule on its units (the owner,
2026-10-25; FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md section 4; agreement.labels_by_rule).

His words: "There an LLM opinion that's put in front along with actual Raw
transcription per model to the harness if needed as then harness does its
thing per field and settles as written or derived and so on", and, asked
whether the harness should be free to settle a field on any model's raw
transcription when evidence supports it, even if the LLM pass picked a
different one: "This is exactly what should have been happening".

Each case runs the ordinary workflow's run (test_step's rig) through the
step, label 1's units with the image naming one reader's text where the
readers differ, or uncertain there (prefer). Until 2026-10-25 a label's
decided transcript decided its text (G19's NOT_DECIDED); from then until
WP 1.8 the old first pass's preferred reader was advice to the experts. The
module keeps the cases of the reviews of #414, on the rule.
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
# The review's probe (#414, round 1): 1A writes "1a"; 1B and both readers of
# label 2 write "la", a shared misread.
PROBE_CODES = every_field(("collection_code", "1A", "1a", "collection_code: 1a"),
    ("collection_code", "1B", "la", "collection_code: la"))
LABEL_2_LA = [("collection_code", name, "la", "collection_code: la") for name in ("2A", "2B")]


def prefer(rig, reader):
    """Label 1's units with the image naming reader `reader`'s text (0 for 1A, 1 for 1B) at each
    unit where the readers' texts differ, or uncertain there for None (image_at_differences): the
    first pass's judgement of the image where the readers differ."""
    run = rig.specimen.run
    region = run.regions[0]
    readings = [o for o in run.observations if o.region_id == region.id]
    [entry] = [entry for entry in run.reading_units if entry.label == region.id]
    store_reading_units(run, [image_at_differences(entry, readings[reader].id if reader is not None else None)])


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
    `reading`'s text, resolved, with `update`; its units then come from the person's text
    (first_pass.source_units), as the decision regenerates them."""
    run.transcripts[0] = run.transcripts[0].model_copy(update={"text": reading.literal_text, "resolved": True,
        "selected_observation_id": reading.id, **update})
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
    """The findings of how each label settled the field `key` (step._settlement)."""
    return sorted((f.reason_code, f.severity) for f in run.findings
        if f.rule_id == "field_settlement" and f.field_key == key)


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
        return specimen
    monkeypatch.setattr(rig_module, "make_specimen", make)


def code_answer(literal, *names):
    return FieldAnswer(outcome="resolved", literal=literal, reading_names=list(names), explanation="Settled.")


# ---- 1: another label of the specimen backs a reader's text the image does not name

@pytest.mark.parametrize("answer", [code_answer("la", "1B", "2A", "2B"), code_answer("1a", "1A")],
    ids=["the-shared-misread", "the-images-reading"])
def test_a_shared_misread_on_another_label_leaves_labels_that_differ(tmp_path, monkeypatch, answer):
    """The review's probe: label 1's 1A writes "1a", 1B "la", and so do both
    readers of label 2; the image names 1A's "1a" at label 1's difference. No
    source checks the collection code. Label 1 settles on "1a" (an IMAGE
    backing above another label's TEXT, rule 5), label 2 on "la", and the
    labels differ: ambiguous (LABELS_DIFFER), whichever text the answer
    gives. Round 1 settled "la" and refused "1a"; before 2026-10-25 "la" was
    refused as NOT_DECIDED (unresolved) and "1a" as LABELS_DIFFER."""
    a_second_label(monkeypatch, "collection_code: la")
    rig = build_rig(tmp_path, ONE_A, LA, candidates=[*PROBE_CODES, *LABEL_2_LA])
    run = rig.specimen.run
    prefer(rig, 0)
    first = run.regions[0].id
    settle(rig, Scripted({"collection_code": answering(answer)}))
    code = run.fields["collection_code"]
    assert (code.state, code.literal) == (ValueState.AMBIGUOUS, None)
    assert "mandatory_unresolved:collection_code" in run.reasons
    assert code.reason == agreement.LABELS_DIFFER + " Settled."
    assert settlement_findings(run, "collection_code") == []


def test_with_the_image_uncertain_another_label_whose_readers_agree_settles_the_field(tmp_path, monkeypatch):
    """The probe's readings with the image uncertain at label 1's difference:
    label 2's two readers back 1B's "la" (TEXT), so the field settles on it,
    marked, and the record goes to review (rule 4); label 2 settles cleared.
    Before 2026-10-25: ambiguous, as readers that differ."""
    a_second_label(monkeypatch, "collection_code: la")
    rig = build_rig(tmp_path, ONE_A, LA, candidates=[*PROBE_CODES, *LABEL_2_LA])
    run = rig.specimen.run
    prefer(rig, None)
    first, second = (region.id for region in run.regions)
    settle(rig, Scripted({"collection_code": answering(code_answer("la", "1B", "2A", "2B"))}))
    code = run.fields["collection_code"]
    assert (code.state, code.literal) == (ValueState.SUPPORTED, "la")
    assert reasons_for(run, "collection_code") == [f"marked:collection_code:{first}:text_only"]
    assert run.disposition == Disposition.REVIEW
    assert settlement_findings(run, "collection_code") == [(f"cleared:collection_code:{second}", "info"),
        (f"marked:collection_code:{first}:text_only", "warning")]
    [marked] = [f for f in run.findings if f.reason_code.startswith("marked:")]
    rows = {item.id: item for item in run.evidence}
    # Its detail: label 1's other candidate, 1A's "1a".
    assert marked.evidence_ids and all(rows[i].region_id == first and rows[i].observation_ids
        == [run.observations[0].id] for i in marked.evidence_ids)


def probe_readings(*, label_2=("la", "la")):
    """The probe as agreement.labels reads it: label 1's 1A writes "1a" and 1B "la", label 2's
    readers `label_2`."""
    label_1 = (Reading("1A", "r1", "o1a", "raw_reading", "collection_code: 1a"),
        Reading("1B", "r1", "o1b", "raw_reading", "collection_code: la"))
    second = tuple(Reading(f"2{letter}", "r2", f"o2{letter}", "raw_reading", f"collection_code: {text}")
        for letter, text in zip("AB", label_2))
    readings = label_1 + second
    task = FieldTask("collection_code", True, FieldValue(state=ValueState.AMBIGUOUS),
        tuple(Candidate(r.name, r.text, r.text.split(": ")[1], "ev-" + r.name) for r in readings),
        FIELD_TOOLS["collection_code"])
    return task, readings


@pytest.mark.parametrize("verdict", ["1A", "uncertain"])
def test_another_label_backs_a_text_the_image_does_not_name_on_this_label(verdict):
    """agreement.labels on the probe, label 1's units with the image naming 1A's "1a" at the
    difference (`verdict` "1A") or uncertain there: label 1 settles on "1a", marked with "la"
    listed, where the image names it (rule 5); else on "la", marked, as only another label backs
    it (rule 4)."""
    task, readings = probe_readings()
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


def test_a_label_one_reader_read_backs_nothing(tmp_path, monkeypatch):
    """Label 2's second reader read nothing, so only 2A writes "la": one
    model's text backs no reader of label 1, whose image is uncertain at the
    difference, and the field goes to review as readers that differ. Round 1
    settled it on "la"; before 2026-10-25 it went to review too. With label 1
    alone and the image uncertain, label 1 does not settle either, and an
    answer naming 1A is refused as readers that differ."""
    second_label_read(monkeypatch, "collection_code: la", "")
    rig = build_rig(tmp_path, ONE_A, LA, candidates=[*PROBE_CODES, LABEL_2_LA[0]])
    run = rig.specimen.run
    prefer(rig, None)
    assert [r.name for r in field_step.run_readings(run) if r.region_id == run.regions[1].id] == ["2A"]
    settle(rig, Scripted({"collection_code": answering(code_answer("la", "1B", "2A"))}))
    code = run.fields["collection_code"]
    assert (code.state, code.literal, code.reason) == (ValueState.AMBIGUOUS, None, agreement.DIFFER + " Settled.")
    assert "mandatory_unresolved:collection_code" in run.reasons
    # With the image uncertain there, the one reader of label 2 backs nothing.
    task, readings = probe_readings(label_2=("la",))
    readings = with_units(readings, {"r1": None})
    assert agreement.labels(task, readings, [])["r1"].settled == frozenset()
    refused = agreement.refusal(task, readings, literal="1a", named=[readings[0]], value=None,
        authority_id=None, cited=[], received=[])
    assert (refused.reason, refused.differ) == (agreement.DIFFER, True)


def test_without_another_labels_text_the_label_settles_on_the_images_text(tmp_path, monkeypatch):
    """The control: label 2 writes "2b", which backs neither reader of label
    1. Label 1 settles on the text the image names, 1A's "la", label 2 on
    "2b": the labels differ, as before."""
    a_second_label(monkeypatch, "collection_code: 2b")
    rig = build_rig(tmp_path, LA, ONE_A, candidates=[*CODES, *(("collection_code", name, "2b",
        "collection_code: 2b") for name in ("2A", "2B"))])
    run = rig.specimen.run
    prefer(rig, 0)
    settle(rig, Scripted({"collection_code": answering(code_answer("1a", "1B"))}))
    code = run.fields["collection_code"]
    assert (code.state, code.reason) == (ValueState.AMBIGUOUS, agreement.LABELS_DIFFER + " Settled.")


# ---- 2: a place's near spelling of a reader's text the image does not name

@pytest.mark.parametrize(("reader", "settles"), [(None, True), (0, False)], ids=["image-uncertain", "image-names-1a"])
def test_a_place_settles_on_a_near_spelling_of_one_readers_text_marked_where_the_image_names_another(tmp_path,
        reader, settles):
    """105526330's province, its readers apart: 1A writes "Chimaltenaqo", 1B
    "Chimaltenago". Getty TGN knows the department Chimaltenango, one letter
    from 1B's text and two from 1A's, and finds nothing for 1A's text. The
    near spelling is 1B's SOURCE backing (rule 3), inside the settled country
    (G34), with its near_spelling warning; the one-letter bound is unchanged,
    so 1A's text could not settle so. With the image uncertain the province
    settles on 1B's text, cleared; with the image naming 1A's text it
    settles too, marked, 1A's text listed (rule 5). Before 2026-10-25:
    ambiguous (no near spelling among readers that differ)."""
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
    assert (place.state, place.literal, place.normalized, place.authority_id) == (
        ValueState.SUPPORTED, "Chimaltenago", "Chimaltenango", "tgn:1000565")
    assert "near_spelling:province_state" in [f.reason_code for f in run.findings]
    if settles:
        assert not reasons_for(run, "province_state")
        assert settlement_findings(run, "province_state") == [(f"cleared:province_state:{region}", "info")]
    else:
        assert reasons_for(run, "province_state") == [f"marked:province_state:{region}:conflict"]
        assert place.reason.endswith("Marked for a person: another text has backing too: 'Chimaltenaqo'.")


class WithPazum(Gazetteer):
    """Getty TGN as Gazetteer answers it, and "Pazum", a town one letter from
    1B's "Patzum" (and two from 1A's "Patzun"), in Chimaltenango, Guatemala;
    nothing for "Patzun" or "Patzum" (the review's third finding on #414)."""

    PLACES = {**Gazetteer.PLACES, "Pazum": [("Pazum", "tgn:pazum", "inhabited places",
        (("Chimaltenango", "tgn:1000565"), ("Guatemala", "tgn:7005493")))]}


def test_a_near_spelling_of_the_other_readers_town_settles_marked_against_the_images_text(tmp_path):
    """The review's third finding: 1A writes the town "Patzun", 1B "Patzum",
    and the image names 1A's "Patzun". TGN finds nothing for either, and
    "Pazum", one letter from 1B's text, in the province and country both
    readers write. The near spelling is 1B's SOURCE backing, above 1A's
    IMAGE (rule 5), so the city settles as Pazum, marked, "Patzun" listed.
    Round 1 settled it as Pazum, cleared; before 2026-10-25 it was
    unresolved as NOT_DECIDED."""
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
    assert (town.state, town.literal, town.normalized, town.authority_id) == (
        ValueState.SUPPORTED, "Patzum", "Pazum", "tgn:pazum")
    assert reasons_for(run, "city") == [f"marked:city:{run.regions[0].id}:conflict"]
    assert town.reason.endswith("Marked for a person: another text has backing too: 'Patzun'.")


def test_a_source_confirming_one_readers_place_settles_where_the_other_reader_wrote_none(tmp_path):
    """The review's second finding: 1A writes no province; 1B writes
    "Chimaltenango", which Getty TGN confirms by its own name as a
    department of Guatemala, the country both write. Its one text has a
    SOURCE backing, and the province settles on it, cleared, with the image
    naming 1A's text where the readers differ. Before 2026-10-25: unresolved
    as NOT_DECIDED."""
    first = label_with(country="Guatemala", province_state=None, county=None, city=None)
    second = label_with(country="Guatemala", province_state="Chimaltenango", county=None, city=None)
    rig = build_rig(tmp_path, first, second, candidates=[*COLLECTORS,
        *(("country", name, "Guatemala", "country: Guatemala") for name in ("1A", "1B")),
        ("province_state", "1B", "Chimaltenango", "province_state: Chimaltenango")])
    run = rig.specimen.run
    prefer(rig, 0)

    async def province(task, readings, tools):
        found = await tools.lookup("tgn", "Chimaltenango", field_key=task.key)
        return FieldOutcome(task.key, resolved("Chimaltenango", reading="1B", authority_id="tgn:1000565",
            cited=[found.evidence.id]), evidence=[found.evidence], model_calls=1)
    settle(rig, guatemalan(province_state=province), tools=Gazetteer(rig.blobs))
    place = run.fields["province_state"]
    assert (place.state, place.literal, place.authority_id) == (ValueState.SUPPORTED, "Chimaltenango", "tgn:1000565")
    assert not reasons_for(run, "province_state")
    assert settlement_findings(run, "province_state") == [(f"cleared:province_state:{run.regions[0].id}", "info")]


# ---- 3: nothing backs the other reader's text: the image's text settles

@pytest.mark.parametrize(("literal", "reading", "settles"), [("la", "1A", True), ("1a", "1B", False)])
def test_a_field_no_source_checks_settles_on_the_images_text_when_nothing_backs_the_other_reader(tmp_path,
        literal, reading, settles):
    """One label: 1A writes "la", 1B "1a", the image names 1A's "la", and no
    source checks the collection code. 1A's text settles, cleared (an IMAGE
    backing, rule 4); 1B's text, which nothing backs, is ambiguous for
    review."""
    rig = build_rig(tmp_path, LA, ONE_A, candidates=CODES)
    run = rig.specimen.run
    prefer(rig, 0)
    settle(rig, Scripted({"collection_code": answering(code_answer(literal, reading))}))
    code = run.fields["collection_code"]
    if settles:
        assert (code.state, code.literal) == (ValueState.SUPPORTED, "la")
        assert settlement_findings(run, "collection_code") == [(f"cleared:collection_code:{run.regions[0].id}", "info")]
        assert not reasons_for(run, "collection_code")
        return
    assert (code.state, code.literal) == (ValueState.AMBIGUOUS, None)
    assert code.reason == agreement.DIFFER + " Settled."


# ---- 4: the experts receive each label's units beside the raw readings

def test_each_expert_receives_each_labels_units_beside_the_raw_readings(tmp_path):
    """The request carries the label's units (experts.units_document), the
    unit at the difference with the image naming 1A's text, by label number
    and reader name, and each reading's name and text; no `first_pass` key.
    Before 2026-10-25 the experts never saw the first pass's judgement."""
    rig = build_rig(tmp_path, LA, ONE_A, candidates=CODES)
    run = rig.specimen.run
    prefer(rig, 0)
    readings = field_step.run_readings(run)
    [task] = [task for task in field_step.build_tasks(run)[1] if task.key == "collection_code"]
    made = experts._Expert(task, readings, SimpleNamespace(sources=()), None)
    document = json.loads(made.prompt({"habitat": FieldValue()}).removeprefix(INPUT_PREFIX))
    assert "first_pass" not in document
    assert document["units"] == {"1": experts.units_document(readings)["1"]}
    [unit] = [unit for unit in document["units"]["1"] if unit.get("readers") == {"1A": "la", "1B": "1a"}]
    assert unit["image"] == "la"
    assert len(document["units"]["1"]) == len(run.reading_units[0].units)
    # Each reading's name and text only (the request's bound, budget.DEFAULT_MAX_INPUT_TOKENS).
    assert [sorted(r) for r in document["readings"]] == [["name", "text"]] * 2
    assert [r["name"] for r in document["readings"]] == ["1A", "1B"]


def test_a_label_whose_image_is_uncertain_still_reaches_the_experts_with_its_units(tmp_path):
    rig = build_rig(tmp_path, LA, ONE_A, candidates=CODES)
    run = rig.specimen.run
    prefer(rig, None)
    readings = field_step.run_readings(run)
    assert {r.input_source for r in readings} == {"raw_reading"}
    [task] = [task for task in field_step.build_tasks(run)[1] if task.key == "collection_code"]
    document = json.loads(experts._Expert(task, readings, SimpleNamespace(sources=()), None).prompt({})
        .removeprefix(INPUT_PREFIX))
    # The units, the image uncertain at the difference.
    assert "first_pass" not in document
    [unit] = [unit for unit in document["units"]["1"] if unit.get("readers") == {"1A": "la", "1B": "1a"}]
    assert unit["image"] == UNCERTAIN


# ---- 5: the image uncertain, readers that differ, nothing else: review

def test_with_the_image_uncertain_readers_that_differ_still_go_to_review(tmp_path):
    """The rig's label: its units with the image uncertain where its readers
    differ, and no source or other label backs either text: ambiguous for
    review, and the experts' request has no `first_pass` key."""
    rig = build_rig(tmp_path, LA, ONE_A, candidates=CODES)
    run = rig.specimen.run
    readings = field_step.run_readings(run)
    [task] = [task for task in field_step.build_tasks(run)[1] if task.key == "collection_code"]
    document = json.loads(experts._Expert(task, readings, SimpleNamespace(sources=()), None).prompt({})
        .removeprefix(INPUT_PREFIX))
    assert "first_pass" not in document
    settle(rig, Scripted({"collection_code": answering(code_answer("la", "1A"))}))
    code = run.fields["collection_code"]
    assert (code.state, code.literal, code.reason) == (ValueState.AMBIGUOUS, None, agreement.DIFFER + " Settled.")


@pytest.mark.parametrize(("literal", "reading", "value", "settles"), [
    ("Chimaltenago", "1A", "Chimaltenango", True), ("Chimaltenango", "1B", None, False)])
def test_a_person_decided_transcript_binds_its_label_against_an_exact_source_match(tmp_path, literal, reading,
        value, settles):
    """A reviewer transcribed label 1 as 1A's "Chimaltenago"; reader 1B wrote
    "Chimaltenango", which Getty TGN confirms by its own name, finding
    nothing for "Chimaltenago". The person saw the image, so the label's
    text stays theirs, whatever the sources say (the coordinator's ruling of
    2026-10-25): the value still normalises to TGN's department through the
    one-letter near spelling of the person's own text, inside the settled
    country, while 1B's text, an exact match, is refused (PERSON_DECIDED).
    The label settles on the rule's binding step (agreement.BY_PERSON,
    rule 2), cleared."""
    first, second = (label_with(**GUATEMALAN, province_state=name) for name in ("Chimaltenago", "Chimaltenango"))
    rig = build_rig(tmp_path, first, second, candidates=[*COLLECTORS,
        *(("country", name, "Guatemala", "country: Guatemala") for name in ("1A", "1B")),
        ("province_state", "1A", "Chimaltenago", "province_state: Chimaltenago"),
        ("province_state", "1B", "Chimaltenango", "province_state: Chimaltenango")])
    run = rig.specimen.run
    reader_a = run.observations[0]
    person_transcribed(run, reader_a, actor="reviewer@example.org", reason="The label reads Chimaltenago.")
    readings = field_step.run_readings(run)
    assert [(r.name, r.input_source, r.person_decided) for r in readings] == [
        ("1A", "decided_transcript", True), ("1B", "raw_reading", False)]
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
        task = FieldTask("province_state", True, FieldValue(), tuple(Candidate(name, "", text, "ev-" + name)
            for name, text in (("1A", "Chimaltenago"), ("1B", "Chimaltenango"))), FIELD_TOOLS["province_state"])
        label = agreement.labels(task, readings, [])[run.regions[0].id]
        assert (label.basis, label.cleared, label.settled) == (
            agreement.BY_PERSON, True, frozenset({"Chimaltenago"}))
        assert settlement_findings(run, "province_state") == [(f"cleared:province_state:{run.regions[0].id}", "info")]
        return
    assert (place.state, place.literal) == (ValueState.AMBIGUOUS, None)
    assert place.reason == agreement.PERSON_DECIDED + " Settled."


def test_an_expert_naming_another_reader_of_a_person_decided_label_is_told_to_answer_with_the_persons(
        tmp_path):
    """Round 2 of #414's review: the real resolver's expert first answers
    with 1B's "Chimaltenango", which TGN confirms exactly, on a label a
    reviewer transcribed as 1A's "Chimaltenago". Its check sends it back
    naming the person's reading 1A (PERSON_DECIDED); it answers again with
    1A's text, the department as the value, and the field settles on the
    person's literal with the value normalised through the near spelling.
    The request names the label and its reading under person_decided. The
    retry says what to answer, never how the code decides (PR #425's seventh
    round)."""
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
    assert ("A person transcribed this label: reading 1A holds their transcription, which writes "
        "'Chimaltenago' for this field. Answer with the literal from reading 1A, naming that reading (a "
        "source answer you cite may give its value, with its authority_id), or answer "
        "several_possibilities or sources_cannot_resolve.") in retries[0]
    assert "one letter" not in retries[0]
    assert json.loads(prompts[0].removeprefix(INPUT_PREFIX))["person_decided"] == {"1": "1A"}
    place = run.fields["province_state"]
    assert (place.state, place.literal, place.normalized, place.authority_id) == (
        ValueState.SUPPORTED, "Chimaltenago", "Chimaltenango", "tgn:1000565")


# ---- t1-329 (the real-run measurement of 2026-10-25) ------------------------
# Reader 1A writes "Chimaltenago,", reader 1B "Chimaltenango,"; in that run the
# first pass saw 1A's spelling in the image.

T1_329 = [label_with(country="Guatemala", province_state=name, county=None, city=None)
    for name in ("Chimaltenago,", "Chimaltenango,")]


def t1_329_rig(tmp_path, province_readers=("1A", "1B")):
    """The t1-329 shape: the organiser's province candidates for
    `province_readers` (1A "Chimaltenago", 1B "Chimaltenango") and the
    country for both; the image names 1A's text where the readers differ."""
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
def test_a_source_confirming_the_other_readers_one_letter_correction_keeps_the_images_spelling(tmp_path,
        literal, reading, value, settles):
    """TGN confirms 1B's "Chimaltenango" by its own name and finds nothing for
    1A's "Chimaltenago", which the image names. Rule 1 merges the two texts
    into one candidate: the province's literal is 1A's, its value the
    department through the near spelling of 1B's correction, cleared, with a
    near_spelling warning and the reason naming reader 1B's text. An answer
    with 1B's text is sent back with what to answer alone. The real run of
    2026-10-25 (Wikidata, "Chimaltenango Department") settled 1B's
    literal."""
    rig = t1_329_rig(tmp_path)
    run = rig.specimen.run
    settle(rig, guatemalan(province_state=province_on(literal, reading, value)), tools=Gazetteer(rig.blobs))
    place = run.fields["province_state"]
    region = run.regions[0].id
    if not settles:
        assert (place.state, place.literal) == (ValueState.AMBIGUOUS, None)
        assert settlement_findings(run, "province_state") == []
        readings = field_step.run_readings(run)
        [task] = [task for task in field_step.build_tasks(run)[1] if task.key == "province_state"]
        answers = [asyncio.run(Gazetteer(rig.blobs).lookup("tgn", query, field_key="province_state"))
            for query in ("Chimaltenango", "Chimaltenago")]
        refused = agreement.refusal(task, readings, literal="Chimaltenango", named=[readings[1]], value=None,
            authority_id="tgn:1000565", cited=answers[:1], received=answers)
        # Codex round 8 (X1): what to answer, not why the image's spelling stands.
        assert refused.retry == ("Give 'Chimaltenago' as the literal, naming the reading that writes it, and "
            "the source's candidate as the value with its authority_id.")
        return
    assert (place.state, place.literal, place.normalized, place.authority_id) == (
        ValueState.SUPPORTED, "Chimaltenago", "Chimaltenango", "tgn:1000565")
    assert "near_spelling:province_state" in [f.reason_code for f in run.findings]
    assert settlement_findings(run, "province_state") == [(f"cleared:province_state:{region}", "info")]
    assert not reasons_for(run, "province_state")
    assert "reader 1B's 'Chimaltenango'" in place.reason


class WithMunicipio(Gazetteer):
    """Gazetteer, with the municipio of Chimaltenango, a second-level unit
    inside the department, among TGN's answer for "Chimaltenango" (as
    Wikidata's Q1002552 stood beside the department in the real run)."""

    PLACES = {**Gazetteer.PLACES, "Chimaltenango": [*Gazetteer.PLACES["Chimaltenango"],
        ("Chimaltenango", "tgn:chimaltenango-municipio", "second level subdivisions (political entities)",
            (("Chimaltenango", "tgn:1000565"), ("Guatemala", "tgn:7005493")))]}


def test_a_county_never_takes_another_readers_spelling_of_the_settled_province(tmp_path):
    """t1-329's county: the organiser filed the province only from 1B, so 1A
    writes no province text, and the province settles on 1B's
    "Chimaltenango" by TGN's exact match. The county's expert then read 1A's
    "Chimaltenago," from the transcript, one letter from the municipio
    Chimaltenango, in Guatemala: the same word of the label as the
    province's, in another reader's spelling, so it is refused
    (IS_THE_PROVINCE) and the county does not settle. The real run settled
    it as "Chimaltenago,", which the reference scores wrong. 1A's text at
    1B's unit is a candidate once the expert offers it, the image
    names it, and TGN rules it out: the province settles on 1A's spelling with
    TGN's name as its value (the one-letter rule), and the county's text is
    then the province's own text: the label writes no county (not present)."""
    rig = t1_329_rig(tmp_path, province_readers=("1B",))
    run = rig.specimen.run

    async def county(task, readings, tools):
        found = await tools.lookup("tgn", "Chimaltenango", field_key=task.key)
        missing = await tools.lookup("tgn", "Chimaltenago", field_key=task.key)
        return FieldOutcome(task.key, resolved("Chimaltenago,", reading="1A", value="Chimaltenango",
            authority_id="tgn:chimaltenango-municipio", cited=[found.evidence.id]),
            evidence=[found.evidence, missing.evidence], model_calls=1)
    province_script = province_on("Chimaltenago", "1A", "Chimaltenango")
    settle(rig, guatemalan(province_state=province_script, county=county), tools=WithMunicipio(rig.blobs))
    province = run.fields["province_state"]
    assert (province.state, province.literal) == (ValueState.SUPPORTED, "Chimaltenago")
    place = run.fields["county"]
    assert (place.state, place.literal) == (ValueState.NOT_PRESENT, None)
    assert '"Chimaltenago," is the text of the Province/State field' in place.reason
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
