"""Work package 1.3 of docs/execution/units/PLAN.md: the rule of
docs/product-requirements/FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md section 4 on the units path
(agreement.labels_by_rule), its findings and reasons (step._settlement, step.marked_reasons), how
an expert's literal maps to the units that cover it (agreement.literal_places, covering_units,
image_names), and the given-up check (step.scientific_reasons).

Every test here runs once, on the units path: this module's first_pass_path fixture replaces
conftest.py's. A step-level test builds its run with test_step.build_rig, whose first pass names
in the image the text at each unit where every reader wrote the same text (test_step.seen_units);
a test sets label 1's images otherwise where it says so."""

from __future__ import annotations

import asyncio
import hashlib
import io
import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
import test_step as rig_module
from PIL import Image
from test_first_pass_advice import (
    LA,
    LABEL_2_LA,
    ONE_A,
    PROBE_CODES,
    code_answer,
    image_at_differences,
    person_transcribed,
    with_units,
)
from test_step import (
    COLLECTORS,
    GUATEMALAN,
    LABEL,
    TEXT,
    FakeSources,
    Gazetteer,
    Scripted,
    a_second_label,
    answering,
    build_rig,
    confirming,
    every_field,
    from_tgn,
    guatemalan,
    label_with,
    mounted,
    reasons_for,
    resolved,
    settle,
)

from specimen_digitization.application.domain import Disposition, FieldValue, Observation, Region, ValueState
from specimen_digitization.application.region_pixels import region_png
from specimen_digitization.application.first_pass import alignment_units
from specimen_digitization.application.reading_units import (
    NOT_VISIBLE,
    UNCERTAIN,
    ReadingUnit,
    ReadingUnits,
    UnitText,
    problems,
)
from specimen_digitization.application.storage import LocalBlobs
from specimen_digitization.application.workflow import FIELD_RESEARCH, store_reading_units
from specimen_digitization.field_research import agreement
from specimen_digitization.field_research import step as field_step
from specimen_digitization.field_research.contracts import (
    FIELD_TOOLS,
    Candidate,
    FieldAnswer,
    FieldOutcome,
    FieldTask,
    Reading,
)


@pytest.fixture(autouse=True)
def first_pass_path(monkeypatch):
    monkeypatch.setattr(rig_module, "PATH", "units")
    return "units"


def images(rig, image):
    """Label 1's units with the image `image(unit)` gives each unit."""
    run = rig.specimen.run
    [entry] = [entry for entry in run.reading_units if entry.label == run.regions[0].id]
    store_reading_units(run, [entry.model_copy(update={"units": [
        unit.model_copy(update={"image": image(unit)}) for unit in entry.units]})])


def naming(rig, reader):
    """Label 1's units with the image naming reader `reader`'s text (0 for 1A, 1 for 1B) at each
    unit where the readers' texts differ (test_first_pass_advice.image_at_differences)."""
    run = rig.specimen.run
    [entry] = [entry for entry in run.reading_units if entry.label == run.regions[0].id]
    store_reading_units(run, [image_at_differences(entry, run.observations[reader].id)])


def findings(run, key):
    """How each label settled the field `key`: the units path's findings (step._settlement)."""
    return sorted((f.reason_code, f.severity) for f in run.findings
        if f.rule_id == "field_settlement" and f.field_key == key)


def place_script(literal, reading, *, asked, value=None, authority_id):
    """A province or city expert: Getty TGN asked each of `asked`, then `literal` from `reading`,
    citing the first answer."""
    async def script(task, readings, tools):
        answers = [await tools.lookup("tgn", query, field_key=task.key) for query in asked]
        return FieldOutcome(task.key, resolved(literal, reading=reading, value=value, authority_id=authority_id,
            cited=[answers[0].evidence.id]), evidence=[answer.evidence for answer in answers], model_calls=1)
    return script


INDIANA = TEXT.replace("Illinois", "Indiana")
ILINOIS = TEXT.replace("Illinois", "Ilinois")
STATES = {"Indiana": [("province_state", "1A", "Indiana", "province_state: Indiana")],
    "Ilinois": [("province_state", "1A", "Ilinois", "province_state: Ilinois")]}
ILLINOIS_1B = [("province_state", "1B", "Illinois", "province_state: Illinois")]
HABITATS = every_field(("habitat", "1A", "Shrubs", "habitat: Shrubs"), ("habitat", "1B", "Shurbs", "habitat: Shurbs"))


# ---- rule 3's backings and rule 4: one candidate backed ---------------------------------------

def test_image_only_clears(tmp_path):
    """1A writes "Shrubs", 1B "Shurbs", no source checks a habitat, and the image names 1A's text:
    an IMAGE backing alone clears it (rule 4)."""
    rig = build_rig(tmp_path, TEXT.replace("Synthetic grassland", "Shrubs"),
        TEXT.replace("Synthetic grassland", "Shurbs"), candidates=HABITATS)
    run = rig.specimen.run
    naming(rig, 0)
    settle(rig, Scripted({"habitat": answering(resolved("Shrubs", reading="1A"))}))
    habitat = run.fields["habitat"]
    region = run.regions[0].id
    assert findings(run, "habitat") == [(f"cleared:habitat:{region}", "info")]
    assert (habitat.state, habitat.literal) == (ValueState.SUPPORTED, "Shrubs")
    assert not reasons_for(run, "habitat")


def test_source_only_clears(tmp_path):
    """1A writes "Indiana", 1B "Illinois", the image is uncertain there, and Getty TGN confirms
    1B's text and finds nothing for 1A's: a SOURCE backing alone clears it."""
    rig = build_rig(tmp_path, INDIANA, TEXT, candidates=every_field(*STATES["Indiana"], *ILLINOIS_1B))
    run = rig.specimen.run
    settle(rig, Scripted({"province_state": confirming("Illinois", source="tgn", absent=["Indiana"])}))
    region = run.regions[0].id
    assert findings(run, "province_state") == [(f"cleared:province_state:{region}", "info")]
    province = run.fields["province_state"]
    assert (province.state, province.literal, province.authority_id) == (
        ValueState.SUPPORTED, "Illinois", "tgn:Illinois")
    assert not reasons_for(run, "province_state")


def test_readers_that_agree_with_the_image_uncertain_settle_marked(tmp_path):
    """Both readers write the habitat "Synthetic grassland" and the image is uncertain
    everywhere: readers agreeing alone back it, so it settles marked (rule 4), the code in
    the run's reasons, and the record goes to review."""
    rig = build_rig(tmp_path)
    run = rig.specimen.run
    images(rig, lambda unit: UNCERTAIN)
    settle(rig, Scripted())
    region = run.regions[0].id
    assert findings(run, "habitat") == [(f"marked:habitat:{region}:text_only", "warning")]
    habitat = run.fields["habitat"]
    assert (habitat.state, habitat.literal) == (ValueState.SUPPORTED, LABEL["habitat"])
    assert habitat.reason.endswith("Marked for a person: only readers that agree or another label back this "
        "text; neither the image nor an approved source does.")
    assert reasons_for(run, "habitat") == [f"marked:habitat:{region}:text_only"]
    assert run.disposition == Disposition.REVIEW


def test_another_label_alone_settles_marked(tmp_path, monkeypatch):
    """Label 1's readers write "1a" and "la", the image uncertain there; both readers of label 2
    write "la": another label alone backs it, so label 1 settles marked; label 2, whose image
    names its text, clears."""
    a_second_label(monkeypatch, "collection_code: la")
    rig = build_rig(tmp_path, ONE_A, LA, candidates=[*PROBE_CODES, *LABEL_2_LA])
    run = rig.specimen.run
    settle(rig, Scripted({"collection_code": answering(code_answer("la", "1B", "2A", "2B"))}))
    first, second = (region.id for region in run.regions)
    code = run.fields["collection_code"]
    assert (code.state, code.literal) == (ValueState.SUPPORTED, "la")
    assert findings(run, "collection_code") == [(f"cleared:collection_code:{second}", "info"),
        (f"marked:collection_code:{first}:text_only", "warning")]
    assert run.disposition == Disposition.REVIEW


def test_the_image_and_readers_that_agree_clear(tmp_path):
    """Both readers write the habitat and the image names it: cleared."""
    rig = build_rig(tmp_path)
    run = rig.specimen.run
    settle(rig, Scripted())
    region = run.regions[0].id
    assert findings(run, "habitat") == [(f"cleared:habitat:{region}", "info")]
    assert not reasons_for(run, "habitat")


def test_a_source_and_readers_that_agree_clear(tmp_path):
    """Both readers write the country, the image is uncertain everywhere, and Getty TGN
    confirms it: cleared, while the habitat beside it, with no source, is marked."""
    rig = build_rig(tmp_path)
    run = rig.specimen.run
    images(rig, lambda unit: UNCERTAIN)
    settle(rig, Scripted())
    region = run.regions[0].id
    assert findings(run, "country") == [(f"cleared:country:{region}", "info")]
    assert not reasons_for(run, "country")
    assert reasons_for(run, "habitat") == [f"marked:habitat:{region}:text_only"]


# ---- rule 5: a conflict, and rule 1's merge ----------------------------------------------------

def test_the_image_against_a_source_of_another_place_settles_the_sources_text_marked(tmp_path):
    """The image names 1A's "Indiana"; Getty TGN confirms 1B's "Illinois" and finds nothing for
    "Indiana": two different places. SOURCE above IMAGE: "Illinois", marked, "Indiana" listed
    in the reason and its row cited by the finding."""
    rig = build_rig(tmp_path, INDIANA, TEXT, candidates=every_field(*STATES["Indiana"], *ILLINOIS_1B))
    run = rig.specimen.run
    naming(rig, 0)
    settle(rig, Scripted({"province_state": confirming("Illinois", source="tgn", absent=["Indiana"])}))
    region = run.regions[0].id
    assert findings(run, "province_state") == [(f"marked:province_state:{region}:conflict", "warning")]
    province = run.fields["province_state"]
    assert (province.state, province.literal) == (ValueState.SUPPORTED, "Illinois")
    assert province.reason.endswith("Marked for a person: another text has backing too: 'Indiana'.")
    [marked] = [f for f in run.findings if f.rule_id == "field_settlement" and f.field_key == "province_state"]
    rows = {item.id: item for item in run.evidence}
    assert [rows[i].excerpt for i in marked.evidence_ids] == ["province_state: Indiana"]
    assert reasons_for(run, "province_state") == [f"marked:province_state:{region}:conflict"]


@pytest.mark.parametrize(("named", "literal", "value"), [(0, "Ilinois", "Illinois"), (None, "Illinois", None)],
    ids=["image-names-the-near-spelling", "image-uncertain"])
def test_a_source_and_a_text_one_letter_from_it_are_one_candidate(tmp_path, named, literal, value):
    """1A writes "Ilinois", 1B "Illinois"; Getty TGN confirms "Illinois" and finds nothing for
    "Ilinois": one candidate (rule 1). With the image naming 1A's text its literal is 1A's and
    its value the state; with the image uncertain its literal is the confirmed text. Cleared
    either way."""
    rig = build_rig(tmp_path, ILINOIS, TEXT, candidates=every_field(*STATES["Ilinois"], *ILLINOIS_1B))
    run = rig.specimen.run
    if named is not None:
        naming(rig, named)
    reading = "1A" if named is not None else "1B"
    settle(rig, Scripted({"province_state": place_script(literal, reading, asked=("Illinois", "Ilinois"),
        value=value, authority_id="tgn:Illinois")}))
    region = run.regions[0].id
    assert findings(run, "province_state") == [(f"cleared:province_state:{region}", "info")]
    province = run.fields["province_state"]
    assert (province.state, province.literal, province.normalized, province.authority_id) == (
        ValueState.SUPPORTED, literal, value, "tgn:Illinois")
    assert not reasons_for(run, "province_state")
    if named is not None:
        assert "near_spelling:province_state" in [f.reason_code for f in run.findings]
        assert "reader 1B's 'Illinois'" in province.reason


def rig_answers(rig, key, *queries, sources=FakeSources):
    """The rig's readings, the field's task and the sources' answers to `queries` (Getty TGN)."""
    run = rig.specimen.run
    readings = field_step.run_readings(run)
    [task] = [task for task in field_step.build_tasks(run)[1] if task.key == key]
    tools = sources(rig.blobs)
    return readings, task, [asyncio.run(tools.lookup("tgn", query, field_key=key)) for query in queries]


def test_a_near_spelling_of_the_sources_one_candidate_is_a_source_backing(tmp_path):
    """No reader's text is confirmed by its own name: 1A writes "Chikag", 1B "Chicag", and
    Getty TGN, asked "Chicago", finds it, and nothing for either text. 1B's text, one letter
    from the candidate, has a SOURCE backing (rule 3), and the city settles cleared."""
    rig = build_rig(tmp_path, TEXT.replace("city: Chicago", "city: Chikag"),
        TEXT.replace("city: Chicago", "city: Chicag"), candidates=every_field(
            ("city", "1A", "Chikag", "city: Chikag"), ("city", "1B", "Chicag", "city: Chicag")))
    run = rig.specimen.run
    readings, task, answers = rig_answers(rig, "city", "Chicago", "Chicag", "Chikag")
    label = agreement.labels(task, readings, answers)[run.regions[0].id]
    assert {candidate.texts: candidate.backings for candidate in label.candidates} == {
        frozenset({"Chicag"}): frozenset({agreement.SOURCE}), frozenset({"Chikag"}): frozenset()}
    settle(rig, Scripted({"city": place_script("Chicag", "1B", asked=("Chicago", "Chicag", "Chikag"),
        value="Chicago", authority_id="tgn:Chicago")}))
    city = run.fields["city"]
    assert (city.state, city.literal, city.normalized) == (ValueState.SUPPORTED, "Chicag", "Chicago")
    assert findings(run, "city") == [(f"cleared:city:{run.regions[0].id}", "info")]


def test_an_exact_name_beside_its_near_spelling_is_one_candidate_never_two_backings(tmp_path):
    """1A writes "Ilinois", 1B "Illinois"; Getty TGN confirms "Illinois" by its own name and finds
    nothing for "Ilinois". The near spelling backs nothing of its own: the two are one
    candidate, the only backed one."""
    rig = build_rig(tmp_path, ILINOIS, TEXT, candidates=every_field(*STATES["Ilinois"], *ILLINOIS_1B))
    readings, task, answers = rig_answers(rig, "province_state", "Illinois", "Ilinois")
    label = agreement.labels(task, readings, answers)[rig.specimen.run.regions[0].id]
    assert [(candidate.texts, SOURCE_OF(candidate)) for candidate in label.candidates] == [
        (frozenset({"Ilinois", "Illinois"}), True)]
    assert label.settled == frozenset({"Illinois"}) and label.cleared


def SOURCE_OF(candidate):
    return agreement.SOURCE in candidate.backings


def three_readers(texts, region="r1", prefix="1"):
    return tuple(Reading(f"{prefix}{letter}", region, f"o{prefix}{letter.lower()}", "raw_reading", text)
        for letter, text in zip("ABC", texts))


def task_of(key, readings, literal_of):
    return FieldTask(key, True, FieldValue(state=ValueState.AMBIGUOUS),
        tuple(Candidate(r.name, r.text, literal_of(r.text), "ev-" + r.name) for r in readings), FIELD_TOOLS[key])


@pytest.mark.parametrize("named", ["o1c", None], ids=["image-names-C", "image-uncertain"])
def test_two_texts_confirmed_as_different_places_merge_nothing(tmp_path, named):
    """A "Chimaltenago", one letter from B "Chimaltenango", and C "Escuintla", B and C both
    confirmed by Getty TGN as departments: nothing merges, neither B nor C has a SOURCE backing,
    and the label settles on the image's text when it names one, else not at all (rule 6)."""
    readings = with_units(three_readers([f"province_state: {name}" for name in
        ("Chimaltenago", "Chimaltenango", "Escuintla")]), {"r1": named})
    task = task_of("province_state", readings, lambda text: text.split(": ")[1])
    gazetteer = Gazetteer(LocalBlobs(tmp_path))
    answers = [asyncio.run(gazetteer.lookup("tgn", query, field_key="province_state"))
        for query in ("Chimaltenago", "Chimaltenango", "Escuintla")]
    label = agreement.labels(task, readings, answers)["r1"]
    assert not any(SOURCE_OF(candidate) for candidate in label.candidates)
    assert len(label.candidates) == 3
    if named:
        assert (label.settled, label.cleared) == (frozenset({"Escuintla"}), True)
        return
    assert label.settled == frozenset()
    refused = agreement.refusal(task, readings, literal="Chimaltenango", named=[readings[1]], value=None,
        authority_id="tgn:1000565", cited=answers[1:2], received=answers)
    assert (refused.reason, refused.differ) == (agreement.DIFFER, True)


def test_readers_that_agree_against_another_labels_text_with_the_image_uncertain_are_ambiguous():
    """Label 1: 1A and 1B write "la", 1C "1a", the image uncertain there; both readers of label 2
    write "1a". Readers agreeing back one text and another label the other, and neither the
    image nor a source backs one: the field is ambiguous, both texts its options (rule 5)."""
    label_1 = three_readers(["code la", "code la", "code 1a"])
    label_2 = tuple(Reading(f"2{letter}", "r2", f"o2{letter.lower()}", "raw_reading", "code 1a") for letter in "AB")
    readings = with_units((*label_1, *label_2), {"r1": None})
    task = task_of("collection_code", readings, lambda text: text.split(" ")[1])
    found = agreement.labels(task, readings, [])
    assert (found["r1"].settled, found["r1"].options) == (frozenset(), ("la", "1a"))
    refused = agreement.refusal(task, readings, literal="la", named=list(readings[:2]), value=None,
        authority_id=None, cited=[], received=[])
    assert (refused.reason, refused.differ, refused.options) == (agreement.TEXTS_CONTESTED, True, ("la", "1a"))


def test_two_readers_of_three_back_their_text_marked():
    """A "P-95", B "P-95", C "P-93", the image uncertain there: "P-95", backed by two readers of
    three, settles marked (rule 4)."""
    readings = with_units(three_readers(["code P-95", "code P-95", "code P-93"]), {"r1": None})
    task = task_of("collection_code", readings, lambda text: text.split(" ")[1])
    label = agreement.labels(task, readings, [])["r1"]
    assert (label.settled, label.cleared, label.why) == (frozenset({"P-95"}), False, agreement.TEXT_ONLY)
    assert agreement.refusal(task, readings, literal="P-95", named=list(readings[:2]), value=None,
        authority_id=None, cited=[], received=[]) is None


def test_candidates_that_tie_on_the_rank_do_not_settle():
    """Both readers write "Mindanao" and "Davao Prov." on one label, and the image names both:
    two candidates with IMAGE and TEXT backings, two readers each, reader A first. Nothing
    ranks one above the other: the label does not settle, both texts its options."""
    readings = with_units(tuple(Reading(f"1{letter}", "r1", f"o1{letter.lower()}", "raw_reading",
        "Mindanao,\nDavao Prov.") for letter in "AB"))
    task = FieldTask("province_state", True, FieldValue(), tuple(Candidate(f"1{letter}", text, text, f"ev{letter}{n}")
        for letter in "AB" for n, text in enumerate(("Davao Prov.", "Mindanao"))), FIELD_TOOLS["province_state"])
    label = agreement.labels(task, readings, [])["r1"]
    assert (label.settled, label.tied, label.options) == (frozenset(), True, ("Davao Prov.", "Mindanao"))
    refused = agreement.refusal(task, readings, literal="Davao Prov.", named=list(readings), value=None,
        authority_id=None, cited=[], received=[])
    assert refused.reason == agreement.TIED


# ---- rule 2: a person's text --------------------------------------------------------------------

def test_a_persons_text_binds_against_an_exact_source_match(tmp_path):
    """A reviewer transcribed label 1 as 1A's "Chimaltenago"; 1B wrote "Chimaltenango", which
    Getty TGN confirms by its own name. The person's text settles, cleared (rule 2), the
    department its value through the near spelling; the label's units are the person's text's."""
    first, second = (label_with(**GUATEMALAN, province_state=name) for name in ("Chimaltenago", "Chimaltenango"))
    rig = build_rig(tmp_path, first, second, candidates=[*COLLECTORS,
        *(("country", name, "Guatemala", "country: Guatemala") for name in ("1A", "1B")),
        ("province_state", "1A", "Chimaltenago", "province_state: Chimaltenago"),
        ("province_state", "1B", "Chimaltenango", "province_state: Chimaltenango")])
    run = rig.specimen.run
    person_transcribed(run, run.observations[0], actor="reviewer@example.org")
    settle(rig, guatemalan(province_state=place_script("Chimaltenago", "1A",
        asked=("Chimaltenango", "Chimaltenago"), value="Chimaltenango", authority_id="tgn:1000565")),
        tools=Gazetteer(rig.blobs))
    region = run.regions[0].id
    assert findings(run, "province_state") == [(f"cleared:province_state:{region}", "info")]
    place = run.fields["province_state"]
    assert (place.state, place.literal, place.normalized) == (ValueState.SUPPORTED, "Chimaltenago", "Chimaltenango")
    [units] = run.reading_units
    assert set(units.units[0].readers) == {"person"}


# ---- the given-up check, the reasons and the disposition ----------------------------------------

def test_an_agreed_label_whose_first_pass_was_given_up_goes_to_review_with_tiling_units(tmp_path):
    """Both readers agree, and the units path's first pass is refused on every attempt: the
    label gets the alignment's units, which tile its readings, and goes to review however its
    fields settle (step.scientific_reasons)."""
    rig = build_rig(tmp_path, refused=True)
    region = rig.specimen.run.regions[0].id
    mounted(rig, Scripted())
    run = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert run.completed_steps[-1] == FIELD_RESEARCH
    [transcript] = run.transcripts
    assert (transcript.decision_kind, transcript.resolved) == ("identical_readings", True)
    assert f"unresolved_transcription:{region}" in run.reasons and run.disposition == Disposition.REVIEW
    [units] = run.reading_units
    readings = [o for o in run.observations if o.region_id == region]
    assert units == alignment_units(region, readings)
    assert problems(units, {o.id: o.literal_text for o in readings}) == []


def test_a_marked_fields_code_is_a_reason_and_the_record_goes_to_review(tmp_path):
    """Through the workflow's field research step, the image uncertain everywhere: each field
    readers' agreement alone backs is marked, its code in the stored run's reasons, and the
    record's disposition is needs_human_review. A person's approval clears the marks."""
    rig = build_rig(tmp_path)
    images(rig, lambda unit: UNCERTAIN)
    rig.repository.save(rig.principal, rig.specimen, rig.specimen.version, "units", "units")
    mounted(rig, Scripted())
    run = rig.workflow.step(rig.principal, rig.specimen.id).run
    region = run.regions[0].id
    stored = rig.repository.get(rig.principal.scope, rig.specimen.id).run
    assert f"marked:habitat:{region}:text_only" in stored.reasons
    assert stored.reasons == field_step.marked_reasons(stored)
    assert stored.disposition == Disposition.REVIEW == "needs_human_review"
    stored.human_approved = True
    field_step.refinalize(stored)
    assert (stored.reasons, stored.disposition) == ([], Disposition.CLEARED)


# ---- how a literal maps to the units that cover it -----------------------------------------------

def units_of(label, texts_by_unit, images_by_unit, fields_by_unit=None):
    """A label's units built by hand: `texts_by_unit` gives each unit's text per reader (keys
    "a", "b"), joined by single spaces in each reader's text; `fields_by_unit` each unit's
    fields advice (none by default)."""
    offsets = {key: 0 for key in texts_by_unit[0]}
    units = []
    for number, (texts, image, fields) in enumerate(zip(texts_by_unit, images_by_unit,
            fields_by_unit or [[]] * len(texts_by_unit)), 1):
        readers = {}
        for key, text in texts.items():
            readers[key] = UnitText(text=text, start=offsets[key], end=offsets[key] + len(text))
            offsets[key] += len(text) + (1 if text else 0)
        units.append(ReadingUnit(id=f"{label}:{number}", label=label, lines=(1, 1), readers=readers, image=image,
            fields=fields))
    return ReadingUnits(label=label, units=units)


def reading_of(key, units):
    text = " ".join(unit.readers[key].text for unit in units.units if unit.readers[key].text)
    return Reading("1" + key.upper(), units.label, key, "raw_reading", text, units=units)


PILOT = units_of("L2", [{"a": "6-Sept-1946,", "b": "6-Sept-1946,"}, {"a": "Elev.6400", "b": "Elev.6400'"},
    {"a": "H. Hoogstraal leg.", "b": "H. Hoogstraal leg."}], ["6-Sept-1946,", "Elev.6400", "H. Hoogstraal leg."])
JOINED = units_of("L3", [{"a": "Yepocapa, 4800", "b": "Yepocapa,4800"}, {"a": "ft.", "b": "ft."}],
    ["Yepocapa,4800", "ft."])


@pytest.mark.parametrize(("units", "key", "literal", "covering", "named"), [
    # A part of a unit: the number of "Elev.6400", and the name of "H. Hoogstraal leg.".
    (PILOT, "a", "6400", ["L2:2"], True),
    # Beside "Elev.6400", which the readers write differently, and the image does not judge
    # not visible: the image names no text there (image_names).
    (PILOT, "a", "H. Hoogstraal", ["L2:3"], False),
    # B wrote "Elev.6400'", which the image does not name.
    (PILOT, "b", "6400", ["L2:2"], False),
    # A literal over two units.
    (PILOT, "a", "6-Sept-1946, Elev.6400", ["L2:1", "L2:2"], True),
    # The first pass joined two fields' values in one unit (t1-330): the town is a part of it,
    # inside a word for B ("Yepocapa,4800"), and the image names B's text, A's spacing aside.
    (JOINED, "a", "Yepocapa", ["L3:1"], True),
    (JOINED, "b", "Yepocapa", ["L3:1"], True),
    (JOINED, "a", "4800 ft.", ["L3:1", "L3:2"], True),
    # A text the reading does not write maps to no unit.
    (PILOT, "a", "Hoogstral", [], False),
], ids=["number-of-a-unit", "name-of-a-unit", "another-readers-text-named", "two-units", "joined-town-a",
    "joined-town-b-inside-a-word", "joined-over-two-units", "not-written"])
def test_a_literal_maps_to_the_units_that_cover_it(units, key, literal, covering, named):
    reading = reading_of(key, units)
    assert [[unit.id for unit in place] for place in agreement.covering_units(reading, literal)] == (
        [covering] if covering else [])
    assert agreement.image_names(reading, literal) is named


def test_a_whole_word_place_comes_before_a_place_inside_a_word():
    """agreement.literal_places: "la" stands as a word in "code la" and inside "Guatemala";
    only the word is its place. "6400" stands only inside "Elev.6400": that is its place."""
    assert agreement.literal_places("Guatemala, code la", "la") == [(16, 18)]
    assert agreement.literal_places("Elev.6400 Elev.6400", "6400") == [(5, 9), (15, 19)]
    assert agreement.literal_places("E Slope Mt.\nMcKinley", "Mt. McKinley") == [(8, 20)]
    assert agreement.literal_places("anything", "") == agreement.literal_places("anything", " \n") == []


OWN = "Elev.6400"
IMAGES = {
    # The image as the unit's own text, character for character: named, exact or not.
    "own-text": (OWN, True, True),
    # The reader's text in other letter case: named, but not character for character.
    "own-text-other-case": ("ELEV.6400", True, False),
    # Another reader's different text there: not named.
    "another-text": ("Elev.6400'", False, False),
    UNCERTAIN: (UNCERTAIN, False, False),
    NOT_VISIBLE: (NOT_VISIBLE, False, False),
}


@pytest.mark.parametrize(("image", "named", "exact"), IMAGES.values(), ids=list(IMAGES))
def test_the_image_names_a_readers_text_only_as_that_text(image, named, exact):
    """image_names over the values a unit's image takes (ReadingUnit.image: a reader's text,
    uncertain or not visible), for reader A, whose text there is "Elev.6400"."""
    other = "Elev.6400'" if image == "Elev.6400'" else "ELEV.6400"
    units = units_of("L", [{"a": OWN, "b": other}, {"a": "x", "b": "x"}], [image, "x"])
    reading = reading_of("a", units)
    assert agreement.image_names(reading, "6400") is named
    assert agreement.image_names(reading, "6400", exact=True) is exact


@pytest.mark.parametrize(("next_image", "named"), [(NOT_VISIBLE, True), (UNCERTAIN, False), ("megalippe", False)],
    ids=["not-visible", "uncertain", "the-other-readers-text"])
def test_a_text_another_reader_writes_more_of_is_named_only_where_the_more_is_not_visible(next_image, named):
    """B writes "Danaus plexippus", A "Danaus plexippus megalippe"; the image names the two
    words both write. B's text is named only when the image shows nothing at the unit where
    A wrote more (agreement.image_names' guard on units where the readers differ in presence)."""
    units = units_of("L", [{"a": "Danaus", "b": "Danaus"}, {"a": "plexippus", "b": "plexippus"},
        {"a": "megalippe", "b": ""}], ["Danaus", "plexippus", next_image])
    assert agreement.image_names(reading_of("b", units), "Danaus plexippus") is named


def test_no_units_or_no_reader_of_them_maps_to_nothing():
    """A reading with no units, or one its label's units do not name, maps to no unit."""
    assert agreement.covering_units(Reading("1A", "L2", "a", "raw_reading", "Elev.6400"), "6400") == []
    stranger = Reading("1C", "L2", "c", "raw_reading", "Elev.6400", units=PILOT)
    assert agreement.covering_units(stranger, "6400") == [] and not agreement.image_names(stranger, "6400")


JOINED_UNCERTAIN = units_of("L3", [{"a": "Yepocapa, 4800", "b": "Yepocapa,4800"}, {"a": "ft.", "b": "ft."}],
    [UNCERTAIN, UNCERTAIN])


def test_a_reader_with_no_text_for_the_field_writes_its_own_text_at_the_place_another_reader_writes_one():
    """t1-330's joined unit: A writes "Yepocapa, 4800 ft.", B "Yepocapa,4800 ft.", the
    organiser files the town from 1A only, and the image is uncertain. At A's unit B wrote
    the same text, spacing aside, so B's spelling of the town there is its candidate too
    (agreement._label_texts): two readers agree on it, and it settles marked."""
    a, b = reading_of("a", JOINED_UNCERTAIN), reading_of("b", JOINED_UNCERTAIN)
    task = FieldTask("city", True, FieldValue(), (Candidate("1A", "Yepocapa, 4800 ft.", "Yepocapa", "ev-a"),),
        FIELD_TOOLS["city"])
    label = agreement.labels(task, (a, b), [])["L3"]
    assert [(candidate.texts, candidate.readers) for candidate in label.candidates] == [(frozenset({"Yepocapa"}), 2)]
    assert (label.settled, label.why) == (frozenset({"Yepocapa"}), agreement.TEXT_ONLY)


# ---- what the experts receive ---------------------------------------------------------------------

@pytest.mark.parametrize("units", [True, False], ids=["units", "readings-without-units"])
def test_the_expert_takes_the_units_path_s_instructions_and_request(tmp_path, units):
    """The real resolver's model request, for the habitat: on the units path (readings with
    their label's units) the units path's instructions (prompts.instructions(key, units=True))
    and a request that carries the units (experts.units_document); for readings without units,
    the old path's instructions and no units."""
    import json
    from dataclasses import replace

    from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart
    from pydantic_ai.models.function import FunctionModel

    from specimen_digitization.field_research import experts
    from specimen_digitization.field_research.budget import CostMeter
    from specimen_digitization.field_research.experts import INPUT_PREFIX
    from specimen_digitization.field_research.prompts import instructions

    rig = build_rig(tmp_path)
    readings = field_step.run_readings(rig.specimen.run)
    if not units:
        readings = tuple(replace(reading, units=None) for reading in readings)
    [task] = [task for task in field_step.build_tasks(rig.specimen.run)[1] if task.key == "habitat"]
    seen = []

    def model(messages, info):
        [request] = [message for message in messages if isinstance(message, ModelRequest)][:1]
        seen.append((request.instructions, [part.content for part in request.parts if part.part_kind == "user-prompt"]))
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"outcome": "label_lacks_value",
            "explanation": "Not on the label."})])

    resolver = experts.make_resolver(model_factory=lambda: FunctionModel(model),
        meter=CostMeter(1_000_000, input_micros_per_million=200_000, output_micros_per_million=600_000))
    asyncio.run(resolver(task, readings, {}, tools=FakeSources(rig.blobs)))
    [(given, [prompt])] = seen[:1]
    document = json.loads(prompt.removeprefix(INPUT_PREFIX))
    assert given == instructions("habitat", units=units).strip()
    if units:
        assert document["units"] == experts.units_document(readings) and list(document["units"]) == ["1"]
    else:
        assert "units" not in document


def test_a_persons_label_s_units_reach_the_experts_under_the_person_s_reading(tmp_path):
    """A label a person transcribed: its units, keyed `person`, reach the request under the name
    of the reading that holds the person's transcription (experts.units_document)."""
    from specimen_digitization.field_research import experts

    rig = build_rig(tmp_path, TEXT, TEXT.replace("Synthetic grassland", "Synthetic grasland"))
    run = rig.specimen.run
    person_transcribed(run, run.observations[0], actor="reviewer@example.org")
    readings = field_step.run_readings(run)
    assert [(r.name, r.input_source) for r in readings] == [("1A", "decided_transcript"), ("1B", "raw_reading")]
    document = experts.units_document(readings)
    assert {name for unit in document["1"] for name in unit["readers"]} == {"1A"}
    assert "".join(unit["readers"]["1A"] for unit in document["1"]).replace(" ", "") == (
        run.observations[0].literal_text.replace(" ", "").replace("\n", ""))


@pytest.mark.parametrize(("named", "spelling", "marked"), [(None, "shrubs, mostly forest", True),
    (1, "Shrubs, mostly forest", False)], ids=["image-uncertain", "image-names-1B"])
def test_readers_that_differ_only_in_case_settle_on_the_images_spelling_else_the_first_readers(
        tmp_path, named, spelling, marked):
    """105526322's habitat through the step: 1A writes "shrubs, mostly forest", 1B "Shrubs,
    mostly forest", one text letter case aside. With the image uncertain there, readers
    agreeing alone back it: 1A's spelling, marked. With the image naming 1B's text, 1B's
    spelling, cleared (agreement._spelled)."""
    first, second = "shrubs, mostly forest", "Shrubs, mostly forest"
    rig = build_rig(tmp_path, TEXT.replace("Synthetic grassland", first), TEXT.replace("Synthetic grassland", second),
        candidates=every_field(("habitat", "1A", first, "habitat: " + first),
            ("habitat", "1B", second, "habitat: " + second)))
    run = rig.specimen.run
    if named is not None:
        naming(rig, named)
    settle(rig, Scripted({"habitat": answering(resolved(spelling, reading="1A" if named is None else "1B"))}))
    region = run.regions[0].id
    assert (run.fields["habitat"].state, run.fields["habitat"].literal) == (ValueState.SUPPORTED, spelling)
    assert findings(run, "habitat") == ([(f"marked:habitat:{region}:text_only", "warning")] if marked
        else [(f"cleared:habitat:{region}", "info")])


def test_a_given_up_label_a_person_has_transcribed_since_no_longer_goes_to_review_for_it(tmp_path):
    """The given-up agreed label above, then transcribed by a person (first_pass.person_decided),
    its units from the person's text: the given-up check no longer sends it to review."""
    rig = build_rig(tmp_path, refused=True)
    region = rig.specimen.run.regions[0].id
    mounted(rig, Scripted())
    run = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert f"unresolved_transcription:{region}" in run.reasons
    person_transcribed(run, run.observations[0], actor="reviewer@example.org")
    field_step.refinalize(run)
    assert f"unresolved_transcription:{region}" not in run.reasons


def test_a_literal_inside_another_at_the_same_place_is_no_rival_of_it():
    """Both readers write "Elev.6400 ft", and the organiser gives 1A the literal "Elev.6400 ft"
    and 1B "6400 ft". The image names the text there, and both readers agree on each literal,
    so each has IMAGE and TEXT; "6400 ft" lies inside "Elev.6400 ft" at the same place, so it
    is no rival (agreement._nested): "Elev.6400 ft" settles cleared, and an answer of "6400 ft"
    is refused."""
    readings = with_units(tuple(Reading(f"1{letter}", "r1", f"o1{letter.lower()}", "raw_reading",
        "Elev.6400 ft") for letter in "AB"))
    task = FieldTask("elevation_from_ft", True, FieldValue(), (Candidate("1A", "Elev.6400 ft", "Elev.6400 ft", "ev-a"),
        Candidate("1B", "Elev.6400 ft", "6400 ft", "ev-b")), FIELD_TOOLS["elevation_from_ft"])
    label = agreement.labels(task, readings, [])["r1"]
    assert [candidate.backings for candidate in label.candidates] == [frozenset({agreement.IMAGE,
        agreement.TEXT})] * 2
    assert (label.settled, label.cleared, label.others) == (frozenset({"Elev.6400 ft"}), True, ())
    assert agreement.refusal(task, readings, literal="6400 ft", named=[readings[1]], value=None, authority_id=None,
        cited=[], received=[]) is not None


# ---- PR #425's first review round ------------------------------------------------------------

def province_readings(*names, region="r1"):
    return three_readers([f"province_state: {name}" for name in names], region=region)


@pytest.mark.parametrize(("named", "contested"), [(None, False), ("o1c", True)],
    ids=["image-uncertain", "image-names-Indiana"])
def test_a_confirmed_text_in_two_spellings_keeps_its_source_backing(tmp_path, named, contested):
    """Codex 1: A "Illinois", B "ILLINOIS", C "Indiana"; Getty TGN confirms Illinois and finds
    nothing for Indiana. A's and B's texts are one candidate (agreement_key), which the source
    confirms: cleared with the image uncertain; with the image naming C's "Indiana", SOURCE
    still ranks above IMAGE, and Illinois settles marked."""
    readings = with_units(province_readings("Illinois", "ILLINOIS", "Indiana"), {"r1": named})
    task = task_of("province_state", readings, lambda text: text.split(": ")[1])
    sources = FakeSources(LocalBlobs(tmp_path))
    answers = [asyncio.run(sources.lookup("tgn", query, field_key="province_state")) for query in ("Illinois", "Indiana")]
    label = agreement.labels(task, readings, answers)["r1"]
    assert {candidate.texts: SOURCE_OF(candidate) for candidate in label.candidates} == {
        frozenset({"Illinois", "ILLINOIS"}): True, frozenset({"Indiana"}): False}
    why = agreement.CONTESTED if contested else None
    assert (label.settled, label.cleared, label.why) == (frozenset({"Illinois"}), not contested, why)


def test_a_decomposed_accent_is_found_where_the_reading_writes_it():
    """Codex 3: both readers write "Cafe" with a combining acute accent; the candidate is
    collapsed to NFC, one character for the accented "e". Its places are found in NFC and
    given as the reading's own offsets, so the image naming the text there backs it, and it
    clears."""
    decomposed, composed = "Cafe\u0301 forest", "Caf\u00e9 forest"
    assert agreement.literal_places("habitat: " + decomposed, composed) == [(9, 21)]
    readings = with_units(tuple(Reading(f"1{letter}", "r1", f"o1{letter.lower()}", "raw_reading",
        "habitat: " + decomposed) for letter in "AB"))
    task = task_of("habitat", readings, lambda text: text.split(": ")[1])
    label = agreement.labels(task, readings, [])["r1"]
    assert (label.settled, label.cleared) == (frozenset({composed}), True)


def test_a_readers_own_spelling_is_its_text_whichever_reader_the_organiser_filed():
    """Codex 4: A writes "shrubs", B "Shrubs", the image names A's text, and the organiser files
    the habitat from 1B only. A's text there is "shrubs" (agreement._label_texts), so the label
    settles on the image's spelling, cleared, and an answer of B's spelling is refused."""
    readings = with_units(tuple(Reading(f"1{letter}", "r1", f"o1{letter.lower()}", "raw_reading",
        f"habitat: {text}") for letter, text in (("A", "shrubs"), ("B", "Shrubs"))), {"r1": "o1a"})
    task = FieldTask("habitat", True, FieldValue(), (Candidate("1B", "habitat: Shrubs", "Shrubs", "ev-b"),),
        FIELD_TOOLS["habitat"])
    label = agreement.labels(task, readings, [])["r1"]
    assert (label.settled, label.cleared) == (frozenset({"shrubs"}), True)
    refused = agreement.refusal(task, readings, literal="Shrubs", named=[readings[1]], value=None,
        authority_id=None, cited=[], received=[])
    assert (refused.reason, refused.differ) == (agreement.DIFFER, True)


def test_a_text_read_from_the_transcript_settles_on_the_image_alone(tmp_path):
    """Codex 5: 1A writes "habitat: Shrubs", 1B "habitat: Shurbs", the organiser files no
    habitat, and the image names 1A's text. The expert reads "Shrubs" from 1A's transcript;
    1B's own text there, "Shurbs", is its candidate, and the image backs 1A's: cleared."""
    rig = build_rig(tmp_path, TEXT.replace("Synthetic grassland", "Shrubs"),
        TEXT.replace("Synthetic grassland", "Shurbs"), candidates=[c for c in every_field() if c[0] != "habitat"])
    run = rig.specimen.run
    naming(rig, 0)
    settle(rig, Scripted({"habitat": answering(resolved("Shrubs", reading="1A"))}))
    assert (run.fields["habitat"].state, run.fields["habitat"].literal) == (ValueState.SUPPORTED, "Shrubs")
    assert findings(run, "habitat") == [(f"cleared:habitat:{run.regions[0].id}", "info")]


def test_sources_cannot_resolve_on_a_label_nothing_backs_is_ambiguous_with_the_readers_texts(tmp_path):
    """Codex 6, rule 6: 1A writes "Shrubs", 1B "Shurbs", the image is uncertain there, and the
    expert answers sources_cannot_resolve: the habitat is ambiguous, each reader's text an
    option. The resolver's fallback in place of an answer stays unresolved."""
    from specimen_digitization.field_research.contracts import FieldAnswer

    for fallback, state in ((False, ValueState.AMBIGUOUS), (True, ValueState.UNRESOLVED)):
        rig = build_rig(tmp_path / str(fallback), TEXT.replace("Synthetic grassland", "Shrubs"),
            TEXT.replace("Synthetic grassland", "Shurbs"), candidates=HABITATS)

        async def declined(task, readings, tools):
            return FieldOutcome(task.key, FieldAnswer(outcome="sources_cannot_resolve",
                explanation="Nothing decides."), model_calls=1, fallback=fallback)
        settle(rig, Scripted({"habitat": declined}))
        habitat = rig.specimen.run.fields["habitat"]
        assert habitat.state == state
        if not fallback:
            assert habitat.reason == "Nothing decides. Options: Shrubs; Shurbs."


def test_a_text_beside_a_unit_its_reader_left_out_on_the_left_is_not_image_backed():
    """Claude C2 (c): A writes "E Slope Mt. McKinley", B "Mt. McKinley", the image names A's
    text at each unit. B's text has no IMAGE backing (the unit before it, where B wrote nothing
    and A wrote text, is not "not visible"); "Mt. McKinley" lies inside A's text there (no
    rival of it, agreement._nested), and A's text settles cleared."""
    units = units_of("L", [{"a": "E Slope", "b": ""}, {"a": "Mt.", "b": "Mt."}, {"a": "McKinley", "b": "McKinley"}],
        ["E Slope", "Mt.", "McKinley"])
    a, b = reading_of("a", units), reading_of("b", units)
    assert not agreement.image_names(b, "Mt. McKinley") and agreement.image_names(a, "E Slope Mt. McKinley")
    task = FieldTask("precise_location", True, FieldValue(), (
        Candidate("1A", "E Slope Mt. McKinley", "E Slope Mt. McKinley", "ev-a"),
        Candidate("1B", "Mt. McKinley", "Mt. McKinley", "ev-b")), FIELD_TOOLS["precise_location"])
    label = agreement.labels(task, (a, b), [])["L"]
    assert (label.settled, label.cleared) == (frozenset({"E Slope Mt. McKinley"}), True)


@pytest.mark.parametrize(("second", "named"), [(UNCERTAIN, False), ("la", True)], ids=["one-uncertain", "both-named"])
def test_the_image_must_name_a_text_at_every_place_the_reader_writes_it(second, named):
    """Claude C2 (d): a reading writes "la" at two places; the image names it at the first. It
    backs the text only when it names it at the second too."""
    units = units_of("L", [{"a": "la", "b": "la"}, {"a": "x", "b": "x"}, {"a": "la", "b": "la"}], ["la", "x", second])
    assert agreement.image_names(reading_of("a", units), "la") is named


# ---- PR #425's second review round -----------------------------------------------------------

def test_a_confirmed_text_beside_its_spacing_variant_settles_on_the_confirmed_spelling(tmp_path):
    """Codex round 2, D1: A writes "Chi mal ten ango", B "Chimaltenango", one candidate by
    agreement_key, the image uncertain there, and Getty TGN confirms B's text by its own name.
    The candidate settles on the text the source confirmed, cleared, and an answer of B's text
    passes."""
    readings = with_units(province_readings("Chi mal ten ango", "Chimaltenango"), {"r1": None})
    task = task_of("province_state", readings, lambda text: text.split(": ")[1])
    answers = [asyncio.run(Gazetteer(LocalBlobs(tmp_path)).lookup("tgn", "Chimaltenango", field_key="province_state"))]
    label = agreement.labels(task, readings, answers)["r1"]
    assert (label.settled, label.cleared, label.basis) == (frozenset({"Chimaltenango"}), True, agreement.BY_SOURCE)
    assert agreement.refusal(task, readings, literal="Chimaltenango", named=[readings[1]], value=None,
        authority_id="tgn:1000565", cited=answers, received=answers) is None


def adjacent(label, texts, images):
    """A label's units whose readers "a" and "b" both write `texts`, with nothing between them."""
    units, offset = [], 0
    for number, (text, image) in enumerate(zip(texts, images), 1):
        span = UnitText(text=text, start=offset, end=offset + len(text))
        units.append(ReadingUnit(id=f"{label}:{number}", label=label, lines=(1, 1), readers={"a": span, "b": span},
            image=image))
        offset += len(text)
    return ReadingUnits(label=label, units=units)


def test_a_literal_after_a_composed_sequence_starts_at_its_own_character():
    """Codex round 2, D2: "e" with a combining acute accent before "x" is "\u00e9x" in NFC, as a
    Hangul initial and medial before "x" are one syllable and "x". "x" is found at the reading's
    own (2, 3), not over the accent or the medial. On a label whose units are "e" with its accent,
    the image uncertain, and "x", which the image names, the readers' "x" clears."""
    assert agreement.literal_places("e\u0301x", "x") == [(2, 3)]
    assert agreement.literal_places("\u1100\u1161x", "x") == [(2, 3)]
    assert agreement.literal_places("e\u0301x", "\u00e9x") == [(0, 3)]
    assert agreement.literal_places("e\u0301x", "e") == []
    units = adjacent("L", ["e\u0301", "x"], [UNCERTAIN, "x"])
    readings = tuple(Reading(f"1{key.upper()}", "L", key, "raw_reading", "e\u0301x", units=units) for key in "ab")
    assert not problems(units, {"a": "e\u0301x", "b": "e\u0301x"})
    task = FieldTask("habitat", True, FieldValue(), tuple(Candidate(r.name, r.text, "x", "ev-" + r.name)
        for r in readings), FIELD_TOOLS["habitat"])
    label = agreement.labels(task, readings, [])["L"]
    assert (label.settled, label.cleared) == (frozenset({"x"}), True)


MIXED = ("a", "e", "x", " ", "\u0301", "\u0300", "\u0323", "\u00e9", "\u1100", "\u1161", "\u11a8")


def test_every_place_found_starts_and_ends_where_the_readings_nfc_splits():
    """Codex round 2, D2, seeded: readings of combining marks, Hangul jamo, plain letters and
    spaces; each literal a cut of a reading's NFC. Every place literal_places gives starts and
    ends at an offset where the reading splits under NFC (the NFC of the parts before and after
    it, joined, is the reading's NFC), and starts and ends at no combining mark but at the
    reading's ends, so not inside a combining sequence or a syllable; the reading's text there
    is the literal in NFC, white space aside."""
    import random
    import unicodedata

    def nfc(text):
        return unicodedata.normalize("NFC", text)

    rng = random.Random(1303)
    found = 0
    for _ in range(500):
        raw = "".join(rng.choice(MIXED) for _ in range(rng.randint(1, 12)))
        normal = nfc(raw)
        for _ in range(4):
            first, last = sorted(rng.sample(range(len(normal) + 1), 2))
            literal = normal[first:last]
            for start, end in agreement.literal_places(raw, literal):
                found += 1
                assert nfc(raw[:start]) + nfc(raw[start:]) == normal
                assert nfc(raw[:end]) + nfc(raw[end:]) == normal
                assert all(at in (0, len(raw)) or not unicodedata.combining(raw[at]) for at in (start, end))
                assert nfc(raw[start:end]).split() == nfc(literal).split()
    assert found > 500


def test_sources_cannot_resolve_quoting_a_transcript_text_on_a_label_nothing_backs_is_ambiguous(tmp_path):
    """Codex round 2, D6: 1A writes "habitat: Shrubs", 1B "habitat: Shurbs", the image uncertain
    there, and the organiser files no habitat. The expert answers sources_cannot_resolve with the
    literal "Shrubs" from 1A and both texts as options. Nothing backs either reader's text: the
    habitat is ambiguous, each an option."""
    from specimen_digitization.field_research.contracts import FieldAnswer

    rig = build_rig(tmp_path, TEXT.replace("Synthetic grassland", "Shrubs"),
        TEXT.replace("Synthetic grassland", "Shurbs"), candidates=[c for c in every_field() if c[0] != "habitat"])

    async def declined(task, readings, tools):
        return FieldOutcome(task.key, FieldAnswer(outcome="sources_cannot_resolve", literal="Shrubs",
            reading_names=["1A"], options=["Shrubs", "Shurbs"], explanation="Nothing decides."), model_calls=1)
    settle(rig, Scripted({"habitat": declined}))
    habitat = rig.specimen.run.fields["habitat"]
    assert (habitat.state, habitat.literal) == (ValueState.AMBIGUOUS, None)
    assert habitat.reason == "Nothing decides. Options: Shrubs; Shurbs."


# ---- every reviewer input of PR #425, through the step (rounds 1 to 4, P1-P8) ------------------
#
# Each row is one or two labels given as units, the organiser's candidates, the sources and the
# expert's answer. The row runs through the step on test_step's rig: the rig's specimen holds the
# rows' readings (a third reader, or a second label, added as a_second_label adds one), the
# organiser's candidates are applied, the row's units are stored as the first pass's, and the
# field is researched, applied and finalized (settle). The test asserts the stored FieldValue
# (state, literal, normalized value), the field's settlement findings (cleared:/marked:) and the
# run's reasons that name the field, label ids written L1, L2.

def unit(*texts, image=0, fields=(), sep=" "):
    """A unit: each reader's text there, in reading order; its image (a reader's index, whose
    text it names, or UNCERTAIN, NOT_VISIBLE or a text); the fields advice; the separator
    written after it in each reader's text that writes it."""
    return SimpleNamespace(texts=texts, image=image, fields=list(fields), sep=sep)


def through_step(tmp_path, monkeypatch, labels, candidates, key, script, *, tools=None, person=False):
    """Run the row through the step; (state, literal, normalized, authority_id, options, findings,
    reasons): the options the value's reason lists ("Options: ...")."""
    built = []
    for units in labels:
        readers = len(units[0].texts)
        texts, offsets = [""] * readers, [[] for _ in range(readers)]
        seps = [""] * readers
        for item in units:
            for index, text in enumerate(item.texts):
                if text and texts[index]:
                    texts[index] += seps[index]
                offsets[index].append((len(texts[index]), len(texts[index]) + len(text)))
                texts[index] += text
                if text:
                    seps[index] = item.sep
        built.append((units, texts, offsets))
    original = rig_module.make_specimen

    def make(blobs, first=None, other=None, **kwargs):
        specimen = original(blobs, built[0][1][0], built[0][1][1], **kwargs)
        run = specimen.run
        region = run.regions[0]
        for index, text in enumerate(built[0][1][2:], 2):
            route = f"synthetic-reader-{index}"
            raw = ("SYNTHETIC FIXTURE " + route + "\n" + text).encode()
            run.observations.append(run.observations[0].model_copy(update={"id": str(uuid.uuid4()),
                "route_id": route, "model_id": "synthetic-" + route, "literal_text": text,
                "raw_ref": blobs.put(raw), "raw_sha256": hashlib.sha256(raw).hexdigest()}))
            run.completed_steps.append(f"transcribe:{region.id}:{route}")
        for number, (_, texts, _) in enumerate(built[1:], 1):
            # As test_step.a_second_label adds a label: its own crop, one reading a route.
            output = io.BytesIO()
            Image.new("RGB", (100, 100), "white").save(output, format="JPEG", quality=95)
            extra = Region(asset_id=specimen.asset.id, x=0, y=50, width=100, height=50, order=number,
                method="synthetic_fixture_region", version="1")
            crop_png = region_png(Image.open(io.BytesIO(output.getvalue())), extra)
            extra.crop_ref = blobs.put(crop_png)
            run.regions.append(extra)
            crop = hashlib.sha256(crop_png).hexdigest()
            for route, text in zip(run.profile.routes, texts, strict=True):
                raw = ("SYNTHETIC FIXTURE " + route + "\n" + text).encode()
                run.observations.append(Observation(region_id=extra.id, route_id=route, model_id="synthetic-" + route,
                    provider="synthetic", prompt_version="prompt:" + route, input_sha256=crop,
                    input_asset_id=specimen.asset.id, input_crop_ref=extra.crop_ref, literal_text=text,
                    raw_ref=blobs.put(raw), raw_sha256=hashlib.sha256(raw).hexdigest()))
                run.completed_steps.append(f"transcribe:{extra.id}:{route}")
        return specimen

    monkeypatch.setattr(rig_module, "make_specimen", make)
    rig = build_rig(tmp_path, candidates=candidates)
    run = rig.specimen.run
    names = {}
    entries = []
    for number, (region, (units, texts, offsets)) in enumerate(zip(run.regions, built), 1):
        names[region.id] = f"L{number}"
        observations = [o for o in run.observations if o.region_id == region.id]
        readings = []
        for index, item in enumerate(units):
            readers = {o.id: UnitText(text=item.texts[i], start=offsets[i][index][0], end=offsets[i][index][1])
                for i, o in enumerate(observations)}
            image = (item.texts[item.image] if isinstance(item.image, int) else item.image)
            readings.append(ReadingUnit(id=f"{region.id}:{index + 1}", label=region.id, lines=(1, 1), readers=readers,
                image=image, fields=item.fields))
        entries.append(ReadingUnits(label=region.id, units=readings))
    store_reading_units(run, entries)
    if person:
        from test_first_pass_advice import person_transcribed

        person_transcribed(run, run.observations[0], actor="reviewer@example.org", reason="The label reads it.")
    settle(rig, Scripted({key: script}), **({"tools": tools(rig.blobs)} if tools else {}))
    value = run.fields[key]

    def named(code):
        for region, name in names.items():
            code = code.replace(region, name)
        return code
    found = [named(f.reason_code).replace(f":{key}:", ":") for f in run.findings
        if f.rule_id == "field_settlement" and f.field_key == key]
    reasons = [named(reason).replace(f":{key}", "") for reason in run.reasons if key in reason.split(":")]
    options = tuple(value.reason.split(" Options: ", 1)[1].rstrip(".").split("; ")) if " Options: " in (
        value.reason or "") else ()
    return value.state, value.literal, value.normalized, value.authority_id, options, found, reasons


def says(literal, *names, asks=(), cite=None, kind=None):
    """The expert's resolved answer: `literal`, naming `names`, after asking each of `asks`
    ((source, query)); with `cite` (an index into `asks`), citing that answer, its candidate
    whose kind holds `kind` the value and authority."""
    async def script(task, readings, tools):
        found = [await tools.lookup(source, query, field_key=task.key) for source, query in asks]
        value, authority, cited = None, None, []
        if cite is not None:
            answer = found[cite]
            candidate = next(c for c in answer.candidates if kind is None or kind in (c.kind or ""))
            value, authority, cited = candidate.name, candidate.authority_id, [answer.evidence.id]
        return FieldOutcome(task.key, FieldAnswer(outcome="resolved", literal=literal, reading_names=list(names),
            value=value, authority_id=authority, source_evidence_ids=cited, explanation="Settled."),
            evidence=[item.evidence for item in found if item.evidence is not None], model_calls=1)
    return script


def declines(literal=None, *names, options=()):
    """The expert's sources_cannot_resolve, with `literal` from `names` and `options`."""
    async def script(task, readings, tools):
        return FieldOutcome(task.key, FieldAnswer(outcome="sources_cannot_resolve", literal=literal,
            reading_names=list(names), options=list(options), explanation="Nothing decides."), model_calls=1)
    return script


def filed(key, *pairs):
    """The organiser's candidates: (reading, literal), each quoting its literal."""
    return [(key, name, literal, literal) for name, literal in pairs]


LIGHT_UNITS = [unit("light", "", image=0), unit("trap", "trap")]
DANAUS_UNITS = [unit("Danaus", "Danaus"), unit("plexippus", "plexippus"), unit("megalippe", "")]
SHRUB_UNITS = [unit("habitat:", "habitat:"), unit("Shrubs", "Shurbs", image=UNCERTAIN)]
CHI_UNITS = [unit("province_state:", "province_state:"), unit("Chi mal ten ango", "Chimaltenango", image=UNCERTAIN)]
MCKINLEY = [unit("E Slope", ""), unit("Mt.", "Mt."), unit("McKinley", "McKinley")]
TOWN = ("geolocate", "Yepocapa, Chimaltenango, Guatemala")


def same_town(image, literal, reading):
    return dict(labels=[[unit("city:", "city:"), unit("Yepocapa,", "Yepocapa", image=image)]],
        candidates=filed("city", ("1A", "Yepocapa,"), ("1B", "Yepocapa")), key="city",
        script=says(literal, reading, asks=[TOWN], cite=0), tools=Gazetteer)


def chi(image, literal, reading):
    units = [CHI_UNITS[0], unit("Chi mal ten ango", "Chimaltenango", image=image)]
    return dict(labels=[units], candidates=filed("province_state", ("1A", "Chi mal ten ango"), ("1B", "Chimaltenango")),
        key="province_state", script=says(literal, reading, asks=[("tgn", "Chimaltenango")], cite=0, kind="first level"),
        tools=Gazetteer)


# (id, the row, what it is). A reviewer row keeps the reviewer's field; a "mechanics" row is not a
# reviewer input.
TABLE = [
    ("codex1-1-image-uncertain", lambda: dict(labels=[[unit("province_state:", "province_state:", "province_state:"),
        unit("Illinois", "ILLINOIS", "Indiana", image=UNCERTAIN)]], candidates=filed("province_state", ("1A", "Illinois"),
        ("1B", "ILLINOIS"), ("1C", "Indiana")), key="province_state", script=says("Illinois", "1A",
        asks=[("tgn", "Illinois"), ("tgn", "Indiana")], cite=0)), "Codex round 1, 1"),
    ("codex1-1-image-names-indiana", lambda: dict(labels=[[unit("province_state:", "province_state:", "province_state:"),
        unit("Illinois", "ILLINOIS", "Indiana", image=2)]], candidates=filed("province_state", ("1A", "Illinois"),
        ("1B", "ILLINOIS"), ("1C", "Indiana")), key="province_state", script=says("Illinois", "1A",
        asks=[("tgn", "Illinois"), ("tgn", "Indiana")], cite=0)), "Codex round 1, 1"),
    ("codex1-2-image-spelling", lambda: same_town(0, "Yepocapa,", "1A"), "Codex round 1, 2"),
    ("codex1-2-other-spelling", lambda: same_town(0, "Yepocapa", "1B"), "Codex round 1, 2"),
    ("codex1-3-decomposed", lambda: dict(labels=[[unit("habitat:", "habitat:"), unit("Cafe\u0301", "Cafe\u0301"),
        unit("forest", "forest")]], candidates=filed("habitat", ("1A", "Cafe\u0301 forest"), ("1B", "Cafe\u0301 forest")),
        key="habitat", script=says("Cafe\u0301 forest", "1A")), "Codex round 1, 3"),
    ("codex1-4-image-spelling", lambda: dict(labels=[[unit("habitat:", "habitat:"), unit("shrubs", "Shrubs", image=0)]],
        candidates=filed("habitat", ("1B", "Shrubs")), key="habitat", script=says("shrubs", "1A")), "Codex round 1, 4"),
    ("codex1-4-other-spelling", lambda: dict(labels=[[unit("habitat:", "habitat:"), unit("shrubs", "Shrubs", image=0)]],
        candidates=filed("habitat", ("1B", "Shrubs")), key="habitat", script=says("Shrubs", "1B")), "Codex round 1, 4"),
    ("codex1-5-transcript", lambda: dict(labels=[[SHRUB_UNITS[0], unit("Shrubs", "Shurbs", image=0)]], candidates=[],
        key="habitat", script=says("Shrubs", "1A")), "Codex round 1, 5"),
    ("codex1-6-nothing-backed", lambda: dict(labels=[SHRUB_UNITS], candidates=filed("habitat", ("1A", "Shrubs"),
        ("1B", "Shurbs")), key="habitat", script=declines()), "Codex round 1, 6"),
    ("claude1-c1-1B-only", lambda: dict(labels=[DANAUS_UNITS], candidates=filed("taxon", ("1B", "Danaus plexippus")),
        key="taxon", script=says("Danaus plexippus", "1B")), "Claude round 1, C1"),
    ("claude1-c1-trinomial-answered", lambda: dict(labels=[DANAUS_UNITS], candidates=filed("taxon",
        ("1B", "Danaus plexippus")), key="taxon", script=says("Danaus plexippus megalippe", "1A")), "Claude round 1, C1"),
    ("claude1-c1-both-filed", lambda: dict(labels=[DANAUS_UNITS], candidates=filed("taxon",
        ("1A", "Danaus plexippus megalippe"), ("1B", "Danaus plexippus")), key="taxon", script=says("Danaus plexippus", "1B")),
        "Claude round 1, C1"),
    ("claude1-c1-megalippe-not-visible", lambda: dict(labels=[[*DANAUS_UNITS[:2], unit("megalippe", "", image=NOT_VISIBLE)]],
        candidates=filed("taxon", ("1B", "Danaus plexippus")), key="taxon", script=says("Danaus plexippus", "1B")),
        "Claude round 1, C1"),
    ("claude1-c2a-mindanao", lambda: dict(labels=[[unit("Mindanao,", "Mindanao,", "Mindanao,", sep="\n"),
        unit("Davao Prov.", "Davao Prov.", "")]], candidates=filed("province_state", ("1A", "Mindanao"), ("1A", "Davao Prov."),
        ("1B", "Mindanao"), ("1B", "Davao Prov."), ("1C", "Mindanao")), key="province_state",
        script=says("Davao Prov.", "1A")), "Claude round 1, C2 (a)"),
    ("mechanics-c2a-mindanao-on-habitat", lambda: dict(labels=[[unit("Mindanao,", "Mindanao,", "Mindanao,", sep="\n"),
        unit("Davao Prov.", "Davao Prov.", "")]], candidates=filed("habitat", ("1A", "Mindanao"), ("1A", "Davao Prov."),
        ("1B", "Mindanao"), ("1B", "Davao Prov."), ("1C", "Mindanao")), key="habitat", script=says("Davao Prov.", "1A")),
        "mechanics: C2 (a)'s units on a field with no place check"),
    ("mechanics-readers-term", lambda: dict(labels=[[unit("Mindanao,", "Mindanao,", "Mindanao,", sep="\n"),
        unit("P.I.", "P.I.", "P.I.", sep="\n"), unit("Davao Prov.", "Davao Prov.", "Davao Pr.")]],
        candidates=filed("habitat", ("1A", "Mindanao"), ("1A", "Davao Prov."), ("1B", "Mindanao"), ("1B", "Davao Prov."),
        ("1C", "Mindanao")), key="habitat", script=says("Mindanao", "1A")), "mechanics: rule 5's readers term"),
    ("claude1-c2b-yepocapa", lambda: dict(labels=[[unit("Yepocapa, 4800", "Yepocapa,4800", image=UNCERTAIN),
        unit("ft.", "ft.", image=UNCERTAIN)]], candidates=filed("city", ("1A", "Yepocapa")), key="city",
        script=says("Yepocapa", "1A")), "Claude round 1, C2 (b)"),
    ("mechanics-c2b-yepocapa-on-habitat", lambda: dict(labels=[[unit("Yepocapa, 4800", "Yepocapa,4800", image=UNCERTAIN),
        unit("ft.", "ft.", image=UNCERTAIN)]], candidates=filed("habitat", ("1A", "Yepocapa")), key="habitat",
        script=says("Yepocapa", "1A")), "mechanics: C2 (b)'s units on a field with no place check"),
    ("claude1-c2c-mckinley-both-filed", lambda: dict(labels=[MCKINLEY], candidates=filed("precise_location",
        ("1A", "E Slope Mt. McKinley"), ("1B", "Mt. McKinley")), key="precise_location",
        script=says("E Slope Mt. McKinley", "1A")), "Claude round 1, C2 (c)"),
    ("claude1-c2c-mckinley-1B-only", lambda: dict(labels=[MCKINLEY], candidates=filed("precise_location",
        ("1B", "Mt. McKinley")), key="precise_location", script=says("Mt. McKinley", "1B")), "Claude round 1, C2 (c)"),
    ("claude1-c2d-one-place-uncertain", lambda: dict(labels=[[unit("la", "la"), unit("x", "x"),
        unit("la", "la", image=UNCERTAIN)]], candidates=filed("collection_code", ("1A", "la"), ("1B", "la")),
        key="collection_code", script=says("la", "1A")), "Claude round 1, C2 (d)"),
    ("claude1-c2d-both-named", lambda: dict(labels=[[unit("la", "la"), unit("x", "x"), unit("la", "la")]],
        candidates=filed("collection_code", ("1A", "la"), ("1B", "la")), key="collection_code", script=says("la", "1A")),
        "Claude round 1, C2 (d)"),
    ("codex2-d1-image-uncertain", lambda: chi(UNCERTAIN, "Chimaltenango", "1B"), "Codex round 2, D1"),
    ("claude3-2-image-names-spaced-answer-spaced", lambda: chi(0, "Chi mal ten ango", "1A"), "Claude round 3, 2"),
    ("claude3-2-image-names-spaced-answer-confirmed", lambda: chi(0, "Chimaltenango", "1B"), "Claude round 3, 2"),
    ("codex2-d2-composed", lambda: dict(labels=[[unit("e\u0301", "e\u0301", image=UNCERTAIN, sep=""), unit("x", "x")]],
        candidates=filed("habitat", ("1A", "x"), ("1B", "x")), key="habitat", script=says("x", "1A")), "Codex round 2, D2"),
    ("codex2-d4-illinois-answered", lambda: dict(labels=[[unit("province_state: Illinois", "province_state: Indiana",
        image=1)]], candidates=filed("province_state", ("1A", "Illinois")), key="province_state",
        script=says("Illinois", "1A", asks=[("tgn", "Illinois")], cite=0)), "Codex round 2, D4"),
    ("codex2-d5-shrubs-1946", lambda: dict(labels=[[unit("Shrubs", "Shrubs", fields=["habitat"]),
        unit("1946", "", fields=["date_visited_from"])]], candidates=filed("habitat", ("1B", "Shrubs")), key="habitat",
        script=says("Shrubs", "1B")), "Codex round 2, D5"),
    ("codex2-d6-transcript-literal", lambda: dict(labels=[SHRUB_UNITS], candidates=[], key="habitat",
        script=declines("Shrubs", "1A", options=["Shrubs", "Shurbs"])), "Codex round 2, D6"),
    ("codex3-1-inside-word", lambda: dict(labels=[[unit("x\u0301", "x\u0301", image=UNCERTAIN), unit("ax", "ax")]],
        candidates=filed("habitat", ("1A", "x"), ("1B", "x")), key="habitat", script=says("x", "1A")), "Codex round 3, 1"),
    ("codex3-2-semicolon-comma-1A", lambda: dict(labels=[[unit("Shrubs;1946", "Shrubs,1946", image=1)]],
        candidates=filed("habitat", ("1A", "Shrubs")), key="habitat", script=says("Shrubs", "1A")), "Codex round 3, 2"),
    ("codex3-2-semicolon-comma-1B", lambda: dict(labels=[[unit("Shrubs;1946", "Shrubs,1946", image=1)]],
        candidates=filed("habitat", ("1A", "Shrubs")), key="habitat", script=says("Shrubs", "1B")), "Codex round 3, 2"),
    ("codex3-2-shared-end", lambda: dict(labels=[[unit("A Shrubs", "B Shrubs", image=1)]],
        candidates=filed("habitat", ("1A", "Shrubs")), key="habitat", script=says("Shrubs", "1A")), "Codex round 3, 2"),
    ("codex3-3-shrubs-answered", lambda: dict(labels=[[unit("habitat: Shrubs; code A", "habitat: Grass; code B",
        image=1)]], candidates=filed("habitat", ("1A", "Shrubs")), key="habitat", script=says("Shrubs", "1A")),
        "Codex round 3, 3"),
    ("codex3-3-grass-answered", lambda: dict(labels=[[unit("habitat: Shrubs; code A", "habitat: Grass; code B",
        image=1)]], candidates=filed("habitat", ("1A", "Shrubs")), key="habitat", script=says("Grass", "1B")),
        "Codex round 3, 3"),
    ("codex3-4-light-advised-habitat", lambda: dict(labels=[[unit("light", "", fields=["habitat"]),
        unit("trap", "trap", fields=["collection_method"])]], candidates=filed("collection_method", ("1B", "trap")),
        key="collection_method", script=says("trap", "1B")), "Codex round 3, 4"),
    ("codex3-4-megalippe-advised-dts", lambda: dict(labels=[[unit("Danaus", "Danaus", fields=["taxon"]),
        unit("plexippus", "plexippus", fields=["taxon"]), unit("megalippe", "", fields=["verbatim_dts"])]],
        candidates=filed("taxon", ("1B", "Danaus plexippus")), key="taxon", script=says("Danaus plexippus", "1B")),
        "Codex round 3, 4"),
    ("codex3-5-options-no-literal", lambda: dict(labels=[SHRUB_UNITS], candidates=[], key="habitat",
        script=declines(None, "1A", "1B", options=["Shrubs", "Shurbs"])), "Codex round 3, 5"),
    ("codex3-6-options-a-subset", lambda: dict(labels=[SHRUB_UNITS], candidates=[], key="habitat",
        script=declines("Shrubs", "1A", options=["Shrubs"])), "Codex round 3, 6"),
    ("claude3-3a-danaus-advised-taxon", lambda: dict(labels=[[unit("Danaus", "Danaus", fields=["taxon"]),
        unit("plexippus", "plexippus", fields=["taxon"]), unit("megalippe", "", fields=["taxon"])]],
        candidates=filed("taxon", ("1B", "Danaus plexippus")), key="taxon", script=says("Danaus plexippus", "1B")),
        "Claude round 3, 3a"),
    ("claude3-3b-image-uncertain", lambda: dict(labels=[[unit("Elev. 6400 ft", "El. 6400 ft", image=UNCERTAIN)]],
        candidates=filed("elevation_from_ft", ("1A", "6400")), key="elevation_from_ft", script=says("6400", "1A")),
        "Claude round 3, 3b"),
    ("claude3-3b-image-names-1B", lambda: dict(labels=[[unit("Elev. 6400 ft", "El. 6400 ft", image=1)]],
        candidates=filed("elevation_from_ft", ("1A", "6400")), key="elevation_from_ft", script=says("6400", "1A")),
        "Claude round 3, 3b"),
    ("codex4-s1-names-1A", lambda: s1("1A"), "Codex round 4, 1"),
    ("codex4-s1-names-1B", lambda: s1("1B"), "Codex round 4, 1"),
    ("codex4-s1-names-both", lambda: s1("1A", "1B"), "Codex round 4, 1"),
    ("codex4-s2-person-two-lines", lambda: dict(labels=[[unit("Seliban Riv.", "Seliban Riv.", image=UNCERTAIN, sep="\n"),
        unit("Mt. Apo", "Mt. Apo", image=UNCERTAIN)]], candidates=filed("precise_location", ("1A", "Seliban Riv."),
        ("1A", "Mt. Apo")), key="precise_location", script=says("Seliban Riv.\nMt. Apo", "1A"), person=True),
        "Codex round 4, 2"),
    ("codex4-s3-sharp-s", lambda: dict(labels=[[unit("s s", "\u00df", image=UNCERTAIN)]], candidates=filed("habitat",
        ("1A", "s")), key="habitat", script=says("s", "1A")), "Codex round 4, 3"),
    ("codex4-s4-cloud-rain-forest", lambda: dict(labels=[[unit("cloud", "rain"), unit("forest", "forest")]],
        candidates=filed("habitat", ("1B", "forest")), key="habitat", script=says("forest", "1B")), "Codex round 4, 4"),
    ("codex4-s4-agreed-neighbour", lambda: dict(labels=[[unit("Shrubs", "Shrubs"), unit("1946", "1946")]],
        candidates=filed("habitat", ("1B", "Shrubs")), key="habitat", script=says("Shrubs", "1B")), "coordinator, round 4 (S4)"),
    ("codex4-s5-dry-forest", lambda: dict(labels=[[unit("dry forest", "dry forest", sep="\n"), unit("forest", "forest")]],
        candidates=filed("habitat", ("1A", "dry forest"), ("1B", "forest")), key="habitat", script=says("dry forest", "1A")),
        "Codex round 4, 5"),
    ("claude4-t1-reader-order", lambda: dict(labels=[[unit("Mindanao,", "", sep="\n"), unit("P.I.", "P.I.", sep="\n"),
        unit("", "Davao Prov.", image=1)]], candidates=filed("habitat", ("1A", "Mindanao"), ("1B", "Davao Prov.")),
        key="habitat", script=says("Mindanao", "1A")), "Claude round 4, T1"),
    ("claude4-t1-reader-order-other-answered", lambda: dict(labels=[[unit("Mindanao,", "", sep="\n"),
        unit("P.I.", "P.I.", sep="\n"), unit("", "Davao Prov.", image=1)]], candidates=filed("habitat", ("1A", "Mindanao"),
        ("1B", "Davao Prov.")), key="habitat", script=says("Davao Prov.", "1B")), "Claude round 4, T1"),
    ("claude4-t2-image-names-1B-answer-1A", lambda: same_town(1, "Yepocapa,", "1A"), "Claude round 4, T2"),
    ("claude4-t2-image-names-1B-answer-1B", lambda: same_town(1, "Yepocapa", "1B"), "Claude round 4, T2"),
    ("claude4-t3-options-union", lambda: dict(labels=[SHRUB_UNITS], candidates=[], key="habitat",
        script=declines("Shrubs", "1A", options=["Shrubs", "Shurbs", "Grassland"])), "Claude round 4, T3"),
    ("mechanics-s1-second-label-agrees-names-1A", lambda: s1("1A", agreed=True),
        "mechanics: the literal offered to every label, whatever readings the answer names (S1)"),
    ("mechanics-s1-second-label-agrees-names-1B", lambda: s1("1B", agreed=True),
        "mechanics: the literal offered to every label, whatever readings the answer names (S1)"),
    ("mechanics-s1-refusal-offers-every-label", lambda: dict(labels=[[unit("Shrubs", "Shrubs", image=UNCERTAIN)],
        [unit("Shrubs", "Shurbs", image=UNCERTAIN)], [unit("Shurbs", "Shurbs", image=UNCERTAIN)]],
        candidates=filed("habitat", ("1A", "Shrubs"), ("2B", "Shurbs"), ("3A", "Shurbs")), key="habitat",
        script=says("Shrubs", "1A")), "mechanics: the refusal offers the literal to every label (S1)"),
    ("mechanics-units-txt-example", lambda: dict(labels=[[unit("light", "", image=0), unit("trap", "trap")]],
        candidates=[], key="collection_method", script=says("light trap", "1A")), "mechanics: prompts/units.txt's example"),
]
for light, tag in ((NOT_VISIBLE, "not-visible"), (0, "image-names-light")):
    for names in (("1A",), ("1B",), ("1A", "1B")):
        TABLE.append((f"codex2-d3-claude3-1a-{tag}-names-" + "-".join(names), lambda light=light, names=names: dict(
            labels=[[unit("light", "", image=light), unit("trap", "trap")]], candidates=[], key="collection_method",
            script=says("trap", *names)), "Codex round 2, D3; Claude round 3, 1a"))
for names in (("1A",), ("1B",), ("1A", "1B")):
    TABLE.append(("claude3-1b-two-line-locality-names-" + "-".join(names), lambda names=names: dict(
        labels=[[unit("Seliban Riv.", "Seliban Riv.", sep="\n"), unit("Mt. Apo", "Mt. Apo")]],
        candidates=filed("precise_location", *((name, line) for name in ("1A", "1B") for line in ("Seliban Riv.", "Mt. Apo"))),
        key="precise_location", script=says("Seliban Riv.\nMt. Apo", *names)), "Claude round 3, 1b"))


def s1(*names, agreed=False):
    """Codex round 4, 1: L1's readers "habitat: Shrubs; code A" and "habitat: Shrubs; code B", one
    unit, the image naming 1A's; L2's "Shrubs" and "Shurbs", one unit, the image uncertain (with
    `agreed`, both "Shrubs", the image naming it); the organiser's "Shrubs" from 1A; the answer
    "Shrubs" naming `names`."""
    second = unit("Shrubs", "Shrubs") if agreed else unit("Shrubs", "Shurbs", image=UNCERTAIN)
    return dict(labels=[[unit("habitat: Shrubs; code A", "habitat: Shrubs; code B", image=0)], [second]],
        candidates=filed("habitat", ("1A", "Shrubs")), key="habitat", script=says("Shrubs", *names))


# What the step stores for each row: (state, literal, normalized, authority_id, the options the
# value's reason lists, the field's settlement findings, the run's reasons that name the field).
def kept(literal, how, *, normalized=None, authority=None):
    """Supported on `literal`, the label cleared ("cleared") or marked ("text_only", "conflict")."""
    found = ["cleared:L1"] if how == "cleared" else [f"marked:L1:{how}"]
    return ValueState.SUPPORTED, literal, normalized, authority, (), found, [] if how == "cleared" else found


def refused(*options):
    """Ambiguous, a mandatory field unresolved, with the options the reason lists."""
    return ValueState.AMBIGUOUS, None, None, None, options, [], ["mandatory_unresolved"]


UNRESOLVED_PLACE = (ValueState.UNRESOLVED, None, None, None, (), [], ["mandatory_unresolved"])
TOWN_ID = "geolocate:Yepocapa, Chimaltenango, Guatemala"
EXPECTED: dict[str, tuple] = {
    "codex1-1-image-uncertain": kept("Illinois", "cleared", authority="tgn:Illinois"),
    "codex1-1-image-names-indiana": kept("Illinois", "conflict", authority="tgn:Illinois"),
    "codex1-2-image-spelling": kept("Yepocapa,", "cleared", normalized="Yepocapa", authority=TOWN_ID),
    "codex1-2-other-spelling": kept("Yepocapa", "cleared", authority=TOWN_ID),
    "codex1-3-decomposed": kept("Cafe\u0301 forest", "cleared"),
    "codex1-4-image-spelling": kept("shrubs", "cleared"),
    "codex1-4-other-spelling": refused(),
    "codex1-5-transcript": kept("Shrubs", "cleared"),
    "codex1-6-nothing-backed": refused("Shrubs", "Shurbs"),
    "claude1-c1-1B-only": kept("Danaus plexippus", "text_only"),
    "claude1-c1-trinomial-answered": kept("Danaus plexippus megalippe", "cleared"),
    "claude1-c1-both-filed": refused(),
    "claude1-c1-megalippe-not-visible": kept("Danaus plexippus", "cleared"),
    # The province with no source: the place check refuses it, whatever the rule gives.
    "claude1-c2a-mindanao": UNRESOLVED_PLACE,
    "mechanics-c2a-mindanao-on-habitat": kept("Davao Prov.", "conflict"),
    "mechanics-readers-term": kept("Mindanao", "conflict"),
    # The city with no source: the place check refuses it.
    "claude1-c2b-yepocapa": UNRESOLVED_PLACE,
    "mechanics-c2b-yepocapa-on-habitat": kept("Yepocapa", "text_only"),
    "claude1-c2c-mckinley-both-filed": kept("E Slope Mt. McKinley", "cleared"),
    "claude1-c2c-mckinley-1B-only": kept("Mt. McKinley", "text_only"),
    "claude1-c2d-one-place-uncertain": kept("la", "text_only"),
    "claude1-c2d-both-named": kept("la", "cleared"),
    "codex2-d1-image-uncertain": kept("Chimaltenango", "cleared", authority="tgn:1000565"),
    "claude3-2-image-names-spaced-answer-spaced": kept("Chi mal ten ango", "cleared", normalized="Chimaltenango",
        authority="tgn:1000565"),
    "claude3-2-image-names-spaced-answer-confirmed": kept("Chimaltenango", "cleared", authority="tgn:1000565"),
    "codex2-d2-composed": kept("x", "cleared"),
    "codex2-d4-illinois-answered": refused(),
    "codex2-d5-shrubs-1946": kept("Shrubs", "text_only"),
    "codex2-d6-transcript-literal": refused("Shrubs", "Shurbs"),
    "codex3-1-inside-word": kept("x", "cleared"),
    "codex3-2-semicolon-comma-1A": kept("Shrubs", "cleared"),
    "codex3-2-semicolon-comma-1B": kept("Shrubs", "cleared"),
    "codex3-2-shared-end": kept("Shrubs", "cleared"),
    "codex3-3-shrubs-answered": refused(),
    "codex3-3-grass-answered": kept("Grass", "cleared"),
    "codex3-4-light-advised-habitat": kept("trap", "text_only"),
    "codex3-4-megalippe-advised-dts": kept("Danaus plexippus", "text_only"),
    "codex3-5-options-no-literal": refused("Shrubs", "Shurbs"),
    "codex3-6-options-a-subset": refused("Shrubs", "Shurbs"),
    "claude3-3a-danaus-advised-taxon": kept("Danaus plexippus", "text_only"),
    "claude3-3b-image-uncertain": refused(),
    "claude3-3b-image-names-1B": kept("6400", "cleared"),
    "codex4-s1-names-1A": kept("Shrubs", "cleared"),
    "codex4-s1-names-1B": kept("Shrubs", "cleared"),
    "codex4-s1-names-both": kept("Shrubs", "cleared"),
    "codex4-s2-person-two-lines": kept("Seliban Riv.\nMt. Apo", "cleared"),
    "codex4-s3-sharp-s": refused(),
    "codex4-s4-cloud-rain-forest": kept("forest", "text_only"),
    "codex4-s4-agreed-neighbour": kept("Shrubs", "cleared"),
    "codex4-s5-dry-forest": refused("dry forest", "forest"),
    "claude4-t1-reader-order": kept("Mindanao", "conflict"),
    "claude4-t1-reader-order-other-answered": refused(),
    "claude4-t2-image-names-1B-answer-1A": refused(),
    "claude4-t2-image-names-1B-answer-1B": kept("Yepocapa", "cleared", authority=TOWN_ID),
    "claude4-t3-options-union": refused("Shrubs", "Shurbs", "Grassland"),
    "mechanics-units-txt-example": kept("light trap", "cleared"),
    # L2 holds 2A's "Shrubs" too: its two texts each backed only by another label, the field ambiguous.
    "mechanics-s1-refusal-offers-every-label": refused("Shrubs", "Shurbs"),
    **{f"mechanics-s1-second-label-agrees-names-{names}": (ValueState.SUPPORTED, "Shrubs", None, None, (),
        ["cleared:L1", "cleared:L2"], []) for names in ("1A", "1B")},
    **{f"codex2-d3-claude3-1a-not-visible-names-{names}": kept("trap", "cleared") for names in ("1A", "1B", "1A-1B")},
    **{f"codex2-d3-claude3-1a-image-names-light-names-{names}": kept("trap", "text_only")
        for names in ("1A", "1B", "1A-1B")},
    **{f"claude3-1b-two-line-locality-names-{names}": kept("Seliban Riv.\nMt. Apo", "cleared")
        for names in ("1A", "1B", "1A-1B")},
}


@pytest.mark.parametrize("row", [row for row, *_ in TABLE])
def test_every_reviewer_input_through_the_step(tmp_path, monkeypatch, row):
    """Each reviewer input of PR #425's four rounds (and the named mechanics rows), run through
    the step: the stored FieldValue's state, literal and normalized value, the field's
    cleared:/marked: findings and the run's reasons that name the field."""
    [(build, _)] = [(build, what) for name, build, what in TABLE if name == row]
    given = build()
    assert through_step(tmp_path, monkeypatch, given["labels"], given["candidates"], given["key"], given["script"],
        tools=given.get("tools"), person=given.get("person", False)) == EXPECTED[row]
