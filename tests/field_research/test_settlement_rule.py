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
from types import SimpleNamespace

import pytest
import test_step as rig_module
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

from specimen_digitization.application.domain import Disposition, FieldValue, ValueState
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
    # A part of a unit: the number of "Elev.6400" and the name of "H. Hoogstraal leg.".
    (PILOT, "a", "6400", ["L2:2"], True),
    (PILOT, "a", "H. Hoogstraal", ["L2:3"], True),
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
    A wrote more (agreement._bounded)."""
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
    the same text, spacing aside, so B's own spelling of the town there is its text too
    (agreement.own_text): two readers back it, and it settles marked."""
    a, b = reading_of("a", JOINED_UNCERTAIN), reading_of("b", JOINED_UNCERTAIN)
    task = FieldTask("city", True, FieldValue(), (Candidate("1A", "Yepocapa, 4800 ft.", "Yepocapa", "ev-a"),),
        FIELD_TOOLS["city"])
    label = agreement.labels(task, (a, b), [])["L3"]
    assert [(candidate.texts, candidate.readers) for candidate in label.candidates] == [(frozenset({"Yepocapa"}), 2)]
    assert (label.settled, label.why) == (frozenset({"Yepocapa"}), agreement.TEXT_ONLY)
    assert agreement.own_text(a, b, "Yepocapa") == frozenset({"Yepocapa"})


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


def test_two_literals_of_one_written_text_are_two_candidates():
    """A limit of this package: both readers write "Elev.6400 ft", and the organiser gives 1A the
    literal "Elev.6400 ft" and 1B "6400 ft". The image names the text there, so each literal has an
    IMAGE backing; nothing merges texts of one place, so 1A's, the earlier reader's, settles
    marked, 1B's listed."""
    readings = with_units(tuple(Reading(f"1{letter}", "r1", f"o1{letter.lower()}", "raw_reading",
        "Elev.6400 ft") for letter in "AB"))
    task = FieldTask("elevation_from_ft", True, FieldValue(), (Candidate("1A", "Elev.6400 ft", "Elev.6400 ft", "ev-a"),
        Candidate("1B", "Elev.6400 ft", "6400 ft", "ev-b")), FIELD_TOOLS["elevation_from_ft"])
    label = agreement.labels(task, readings, [])["r1"]
    assert [candidate.backings for candidate in label.candidates] == [frozenset({agreement.IMAGE})] * 2
    assert (label.settled, label.why, label.others) == (frozenset({"Elev.6400 ft"}), agreement.CONTESTED,
        ("6400 ft",))


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


def test_the_same_place_settles_on_the_text_the_image_names(tmp_path):
    """Codex 2: 1A writes "Yepocapa,", 1B "Yepocapa", one GEOLocate answer confirms both as one
    town, and the image names 1A's "Yepocapa,". The merged candidate's literal is the image's
    text: an answer of 1B's spelling is refused, and 1A's settles."""
    places = dict(country="Guatemala", province_state="Chimaltenango", county=None)
    candidates = [*COLLECTORS, *((key, name, value, f"{key}: {value}") for key, value in places.items()
        if value for name in ("1A", "1B")),
        ("city", "1A", "Yepocapa,", "city: Yepocapa,"), ("city", "1B", "Yepocapa", "city: Yepocapa")]
    for literal, reading, state in (("Yepocapa", "1B", ValueState.AMBIGUOUS), ("Yepocapa,", "1A", ValueState.SUPPORTED)):
        rig = build_rig(tmp_path / reading, label_with(**places, city="Yepocapa,"), label_with(**places, city="Yepocapa"),
            candidates=candidates)
        naming(rig, 0)

        async def city(task, readings, tools, literal=literal, reading=reading):
            answer = await tools.lookup("geolocate", "Yepocapa, Chimaltenango, Guatemala", field_key=task.key)
            return FieldOutcome(task.key, resolved(literal, reading=reading, value="Yepocapa",
                authority_id=answer.candidates[0].authority_id, cited=[answer.evidence.id]),
                evidence=[answer.evidence], model_calls=1)
        settle(rig, Scripted({"country": from_tgn("Guatemala", "Guatemala", None, "tgn:7005493"),
            "province_state": from_tgn("Chimaltenango", "Chimaltenango", None, "tgn:1000565"), "city": city}),
            tools=Gazetteer(rig.blobs))
        city = rig.specimen.run.fields["city"]
        assert (city.state, city.literal) == (state, literal if state == ValueState.SUPPORTED else None)


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
    the habitat from 1B only. A's own text there is "shrubs" (agreement.own_text), so the label
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


def test_a_shorter_readers_text_is_not_backed_through_the_longer_readers_image():
    """Claude C1: A writes "Danaus plexippus megalippe", B "Danaus plexippus", the image names
    each unit's text, and the organiser files the taxon from 1B only. A's own text at B's place
    is the trinomial (the unit beside it where B wrote nothing is A's), so the binomial has no
    backing of A's: the trinomial settles, and the binomial is refused."""
    units = units_of("L", [{"a": "Danaus", "b": "Danaus"}, {"a": "plexippus", "b": "plexippus"},
        {"a": "megalippe", "b": ""}], ["Danaus", "plexippus", "megalippe"])
    a, b = reading_of("a", units), reading_of("b", units)
    task = FieldTask("taxon", True, FieldValue(), (Candidate("1B", "Danaus plexippus", "Danaus plexippus", "ev-b"),),
        FIELD_TOOLS["taxon"])
    label = agreement.labels(task, (a, b), [])["L"]
    assert label.settled == frozenset({"Danaus plexippus megalippe"})
    refused = agreement.refusal(task, (a, b), literal="Danaus plexippus", named=[b], value=None,
        authority_id=None, cited=[], received=[])
    assert refused is not None and refused.differ
    assert agreement.own_text(b, a, "Danaus plexippus") == frozenset({"Danaus plexippus megalippe"})


def test_more_readers_rank_one_image_backed_text_above_another():
    """Claude C2 (a), rule 5's readers tie-break: A and B write "Mindanao," over "Davao Prov.",
    C "Mindanao," alone; the image names both texts. Both candidates have IMAGE and TEXT;
    "Mindanao", which three readers write, settles marked, "Davao Prov." listed."""
    texts = ("Mindanao,\nDavao Prov.", "Mindanao,\nDavao Prov.", "Mindanao,")
    readings = with_units(three_readers(texts), {"r1": "o1a"})
    task = FieldTask("province_state", True, FieldValue(), tuple(Candidate(name, text, literal, f"ev-{name}{literal}")
        for name, text in zip(("1A", "1B", "1C"), texts) for literal in ("Davao Prov.", "Mindanao")
        if literal in text), FIELD_TOOLS["province_state"])
    label = agreement.labels(task, readings, [])["r1"]
    assert {candidate.texts: (candidate.backings, candidate.readers) for candidate in label.candidates} == {
        frozenset({"Mindanao"}): (frozenset({agreement.IMAGE, agreement.TEXT}), 3),
        frozenset({"Davao Prov."}): (frozenset({agreement.IMAGE, agreement.TEXT}), 2)}
    assert (label.settled, label.why, label.others) == (frozenset({"Mindanao"}), agreement.CONTESTED, ("Davao Prov.",))


def test_a_text_beside_a_unit_its_reader_left_out_on_the_left_is_not_image_backed():
    """Claude C2 (c), _bounded's leftward extension: A writes "E Slope Mt. McKinley", B
    "Mt. McKinley", the image names A's text at each unit. B's text has no IMAGE backing (the
    unit before it, where B wrote nothing, is not "not visible"); A's text settles cleared."""
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


@pytest.mark.parametrize("names", [("b",), ("a", "b")], ids=["names-1B", "names-both"])
@pytest.mark.parametrize(("light", "settled", "trap_refused"), [(NOT_VISIBLE, "trap", False),
    ("light", "light trap", True)], ids=["light-not-visible", "image-names-light"])
def test_a_text_read_from_one_readers_transcript_settles_on_the_image_beside_a_longer_text(light, settled,
        trap_refused, names):
    """Codex round 2, D3: A writes "light trap", B "trap", in units "light" (B nothing) and "trap";
    the image `light` at the first and "trap" at the second, and no organiser candidate. The
    expert reads "trap" from B's transcript, or from both; A's own text there is "light trap"
    (own_text, in place of A's "trap": _texts_at_units), and no clause check intervenes. With
    "light" not visible, B's text has IMAGE and clears; with the image naming "light", A's has it:
    "light trap" clears and "trap" is refused."""
    units = units_of("L", [{"a": "light", "b": ""}, {"a": "trap", "b": "trap"}], [light, "trap"])
    readings = {key: reading_of(key, units) for key in "ab"}
    named = [readings[key] for key in names]
    task = FieldTask("collection_method", True, FieldValue(), (), FIELD_TOOLS["collection_method"])
    label = agreement.labels(task, tuple(readings.values()), [], transcript="trap", named=named)["L"]
    assert (label.settled, label.cleared) == (frozenset({settled}), True)
    refused = agreement.refusal(task, tuple(readings.values()), literal="trap", named=named, value=None,
        authority_id=None, cited=[], received=[])
    assert (refused is not None) is trap_refused


def test_another_readers_different_text_inside_one_unit_is_its_candidate_there(tmp_path):
    """Codex round 2, D4: one unit holds A's "province_state: Illinois" and B's "province_state:
    Indiana", and the image names B's. The organiser files A's "Illinois" alone; Getty TGN
    confirms Illinois, and nobody asked about Indiana. B's text there is "Indiana" (own_text: the
    two texts' shared beginning is not the place's), which the image backs, and "Illinois" has
    no SOURCE while "Indiana" is not ruled out: Indiana clears."""
    units = units_of("L", [{"a": "province_state: Illinois", "b": "province_state: Indiana"}],
        ["province_state: Indiana"])
    a, b = reading_of("a", units), reading_of("b", units)
    task = FieldTask("province_state", True, FieldValue(), (Candidate("1A", a.text, "Illinois", "ev-a"),),
        FIELD_TOOLS["province_state"])
    answers = [asyncio.run(FakeSources(LocalBlobs(tmp_path)).lookup("tgn", "Illinois", field_key="province_state"))]
    label = agreement.labels(task, (a, b), answers)["L"]
    assert {candidate.texts: candidate.backings for candidate in label.candidates} == {
        frozenset({"Illinois"}): frozenset(), frozenset({"Indiana"}): frozenset({agreement.IMAGE})}
    assert (label.settled, label.cleared) == (frozenset({"Indiana"}), True)
    assert agreement.own_text(a, b, "Illinois", "province_state") == frozenset({"Indiana"})


def test_a_unit_the_first_pass_advises_for_another_field_bounds_the_text():
    """Codex round 2, D5: A writes "Shrubs" and "1946", B "Shrubs" alone; the first unit is
    advised for the habitat, its image "Shrubs", the second for the date, its image "1946". The
    organiser files the habitat from 1B. The date's unit bounds the habitat's place (_bounded):
    A's text at B's place is "Shrubs", B's text keeps its IMAGE, and "Shrubs" clears."""
    units = units_of("L", [{"a": "Shrubs", "b": "Shrubs"}, {"a": "1946", "b": ""}], ["Shrubs", "1946"],
        [["habitat"], ["date_visited_from"]])
    a, b = reading_of("a", units), reading_of("b", units)
    task = FieldTask("habitat", True, FieldValue(), (Candidate("1B", "Shrubs", "Shrubs", "ev-b"),),
        FIELD_TOOLS["habitat"])
    label = agreement.labels(task, (a, b), [])["L"]
    assert [(candidate.texts, candidate.backings, candidate.readers) for candidate in label.candidates] == [
        (frozenset({"Shrubs"}), frozenset({agreement.IMAGE, agreement.TEXT}), 2)]
    assert (label.settled, label.cleared) == (frozenset({"Shrubs"}), True)
    assert agreement.own_text(b, a, "Shrubs", "habitat") == frozenset({"Shrubs"})


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
