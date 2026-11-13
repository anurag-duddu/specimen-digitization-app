"""Work package 1.3's rework (gap report item 2(b), the coordinator's ruling C2 of 2026-11-13): on the
units path an expert's several_possibilities answer is put to the rule of
docs/product-requirements/FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md section 4 with its options
offered to every label (step._by_rule). One backed candidate settles as rules 4 and 5 say,
cleared or marked; with none the field stays ambiguous with rule 6's options, the readers' texts
and the answer's (P7, step._unsettled_options). Every test runs on both arms (conftest.py). A
test built on test_step.build_rig asserts on the old arm what main stores, the field ambiguous
with the answer's own options; the taxon and IRN test also asserts on both arms that
step._by_rule puts neither to the rule, and a test that builds its readings itself and calls
step._by_rule runs the same on both arms."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest
from test_first_pass_advice import with_units
from test_settlement_rule import findings, images, naming
from test_step import (
    LABEL,
    TEXT,
    Gazetteer,
    Scripted,
    a_second_label,
    answering,
    from_tgn,
    build_rig,
    every_field,
    label_with,
    reasons_for,
    research,
    settle,
)

from specimen_digitization.application.domain import Disposition, Evidence, FieldValue, LookupStatus, ValueState
from specimen_digitization.application.first_pass import source_units
from specimen_digitization.application.reading_units import UNCERTAIN, ReadingUnits
from specimen_digitization.application.storage import LocalBlobs
from specimen_digitization.application.workflow import store_reading_units
from specimen_digitization.field_research import agreement
from specimen_digitization.field_research import step as field_step
from specimen_digitization.field_research.contracts import (
    FIELD_TOOLS,
    Candidate,
    FieldAnswer,
    FieldOutcome,
    FieldTask,
    Reading,
    SourceAnswer,
    SourceCandidate,
)

SHRUBS = every_field(("habitat", "1A", "Shrubs", "habitat: Shrubs"), ("habitat", "1B", "Shurbs", "habitat: Shurbs"))


def several(*options, explanation="The readers' texts differ."):
    return answering(FieldAnswer(outcome="several_possibilities", options=list(options), explanation=explanation))


def old_path_unchanged(run, key, options):
    """The old path: ambiguous, the answer's options in the reason, no settlement finding."""
    value = run.fields[key]
    assert (value.state, value.literal) == (ValueState.AMBIGUOUS, None)
    assert value.reason.endswith(" Options: " + "; ".join(options) + ".")
    assert findings(run, key) == []


def test_readers_that_agree_with_the_image_uncertain_settle_marked(tmp_path, first_pass_path):
    """Both readers write the habitat and the image is uncertain everywhere; the expert answers
    several_possibilities. Two readers agreeing back the text alone: settled, marked text_only,
    its code in the run's reasons, the record to review."""
    rig = build_rig(tmp_path)
    run = rig.specimen.run
    options = (LABEL["habitat"], "grassland")
    if first_pass_path == "units":
        images(rig, lambda unit: UNCERTAIN)
    settle(rig, Scripted({"habitat": several(*options)}))
    if first_pass_path == "old":
        return old_path_unchanged(run, "habitat", options)
    region = run.regions[0].id
    habitat = run.fields["habitat"]
    assert (habitat.state, habitat.literal) == (ValueState.SUPPORTED, LABEL["habitat"])
    # The expert's explanation and options, then the marked value's sentence (step._settlement).
    assert habitat.reason == ("The readers' texts differ. Options: Synthetic grassland; grassland. Marked for a "
        "person: only readers that agree or another label back this text; neither the image nor an approved source "
        "does.")
    assert findings(run, "habitat") == [(f"marked:habitat:{region}:text_only", "warning")]
    assert reasons_for(run, "habitat") == [f"marked:habitat:{region}:text_only"]
    assert run.disposition == Disposition.REVIEW


def test_the_image_naming_a_readers_text_clears_it(tmp_path, first_pass_path):
    """1A writes "Shrubs", 1B "Shurbs", and the image names 1A's text; the expert answers
    several_possibilities with both: the IMAGE backing alone clears 1A's text (rule 4)."""
    rig = build_rig(tmp_path, TEXT.replace("Synthetic grassland", "Shrubs"),
        TEXT.replace("Synthetic grassland", "Shurbs"), candidates=SHRUBS)
    run = rig.specimen.run
    if first_pass_path == "units":
        naming(rig, 0)
    settle(rig, Scripted({"habitat": several("Shrubs", "Shurbs")}))
    if first_pass_path == "old":
        return old_path_unchanged(run, "habitat", ("Shrubs", "Shurbs"))
    habitat = run.fields["habitat"]
    assert (habitat.state, habitat.literal) == (ValueState.SUPPORTED, "Shrubs")
    assert habitat.settled_observation_ids == [run.observations[0].id]
    assert findings(run, "habitat") == [(f"cleared:habitat:{run.regions[0].id}", "info")]
    assert not reasons_for(run, "habitat")


def test_readers_that_differ_only_in_case_and_spacing_are_one_candidate(tmp_path, first_pass_path):
    """1A writes "shrubs,  mostly forest", 1B "Shrubs, mostly forest": one text, letter case
    and spacing aside, so the two readers back one candidate. With the image uncertain it
    settles on the first reader's spelling, marked text_only, the expert's several_possibilities
    with both spellings notwithstanding."""
    first, second = "shrubs,  mostly forest", "Shrubs, mostly forest"
    rig = build_rig(tmp_path, TEXT.replace("Synthetic grassland", first), TEXT.replace("Synthetic grassland", second),
        candidates=every_field(("habitat", "1A", first, "habitat: " + first),
            ("habitat", "1B", second, "habitat: " + second)))
    run = rig.specimen.run
    if first_pass_path == "units":
        images(rig, lambda unit: UNCERTAIN)
    settle(rig, Scripted({"habitat": several(first, second)}))
    if first_pass_path == "old":
        return old_path_unchanged(run, "habitat", (first, second))
    habitat = run.fields["habitat"]
    assert (habitat.state, habitat.literal) == (ValueState.SUPPORTED, first)
    assert findings(run, "habitat") == [(f"marked:habitat:{run.regions[0].id}:text_only", "warning")]


def test_no_backed_candidate_leaves_the_field_ambiguous_with_the_readers_and_the_answers_texts(
        tmp_path, first_pass_path):
    """1A writes "Shrubs", 1B "Shurbs", the image is uncertain and no source checks a habitat:
    nothing backs either text (rule 6). The expert lists "Shrubs" and "SHRUBS", leaving out
    1B's text: the options are the readers' texts and the answer's, letter case and spacing
    aside (P7), so 1B's "Shurbs" is among them."""
    rig = build_rig(tmp_path, TEXT.replace("Synthetic grassland", "Shrubs"),
        TEXT.replace("Synthetic grassland", "Shurbs"), candidates=SHRUBS)
    run = rig.specimen.run
    if first_pass_path == "units":
        images(rig, lambda unit: UNCERTAIN)
    settle(rig, Scripted({"habitat": several("Shrubs", "SHRUBS")}))
    if first_pass_path == "old":
        return old_path_unchanged(run, "habitat", ("Shrubs", "SHRUBS"))
    habitat = run.fields["habitat"]
    assert (habitat.state, habitat.literal) == (ValueState.AMBIGUOUS, None)
    assert habitat.reason == "The readers' texts differ. Options: Shrubs; Shurbs."
    assert findings(run, "habitat") == []


def test_the_union_keeps_an_option_only_the_answer_gives(tmp_path, first_pass_path):
    """1A writes the city "Logan", 1B "Lagan", the image uncertain there; the expert asks GEOLocate
    about "Springfield", whose answer gives that name (test_step.FakeSources), and lists "Logan"
    and "Springfield", a name only that answer gives (experts._Expert._validate_options accepts
    a candidate name it received). Nothing backs either reader's text (rule 6): the options are
    the readers' texts in reading order, then the answer's not among them (P7,
    step._unsettled_options), "Logan; Lagan; Springfield"."""
    rig = build_rig(tmp_path, label_with(city="Logan"), label_with(city="Lagan"), candidates=every_field(
        ("city", "1A", "Logan", "city: Logan"), ("city", "1B", "Lagan", "city: Lagan")))
    run = rig.specimen.run

    async def script(task, readings, tools):
        answer = await tools.lookup("geolocate", "Springfield, Cook, Illinois, United States", field_key=task.key)
        assert [candidate.name for candidate in answer.candidates] == ["Springfield"]
        return FieldOutcome(task.key, FieldAnswer(outcome="several_possibilities", options=["Logan", "Springfield"],
            explanation="The readers' texts differ."), evidence=[answer.evidence], model_calls=1)

    settle(rig, Scripted({"city": script}))
    if first_pass_path == "old":
        return old_path_unchanged(run, "city", ("Logan", "Springfield"))
    city = run.fields["city"]
    assert (city.state, city.literal) == (ValueState.AMBIGUOUS, None)
    assert city.reason == "The readers' texts differ. Options: Logan; Lagan; Springfield."


def test_an_elevation_settles_with_the_value_its_check_gives(tmp_path, first_pass_path):
    """Both readers write "1500 ft" and the image names it; the expert answers
    several_possibilities. The rule clears it, with the number the elevation check reads as its
    value (step._check_results), as a resolved answer's would be."""
    rig = build_rig(tmp_path)
    run = rig.specimen.run
    decisions = {}
    prepared, outcomes, calls = research(rig, Scripted({"elevation_from_ft": several("1500 ft", "1500")}))
    field_step.apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls, decisions=decisions)
    if first_pass_path == "old":
        return old_path_unchanged(run, "elevation_from_ft", ("1500 ft", "1500"))
    # The field's trace names the rule (step.trace_fields).
    assert decisions["elevation_from_ft"] == {"rule": "rule_settled"}
    elevation = run.fields["elevation_from_ft"]
    assert (elevation.state, elevation.literal, elevation.parsed) == (ValueState.SUPPORTED, "1500 ft", "1500")
    assert findings(run, "elevation_from_ft") == [(f"cleared:elevation_from_ft:{run.regions[0].id}", "info")]


RANGE = TEXT + "\nalt. 1200-1500 m"
RANGES = every_field(*((key, name, "1200-1500 m", "alt. 1200-1500 m") for key in ("elevation_from_m", "elevation_to_m")
    for name in ("1A", "1B")))


def test_an_elevation_range_settles_each_field_on_its_end_of_the_range(tmp_path, first_pass_path):
    """Both readers write "alt. 1200-1500 m" and the image names it; each metres field's expert
    answers several_possibilities. The elevation check's one successful result reads the range as
    1200 to 1500: the lower field settles on 1200 and the upper on 1500, as their briefs take
    them (step.UPPER_ELEVATION), cleared."""
    rig = build_rig(tmp_path, RANGE, candidates=RANGES)
    run = rig.specimen.run
    options = ("1200-1500 m", "1200-1500")
    settle(rig, Scripted({key: several(*options) for key in ("elevation_from_m", "elevation_to_m")}))
    for key, value in (("elevation_from_m", "1200"), ("elevation_to_m", "1500")):
        if first_pass_path == "old":
            old_path_unchanged(run, key, options)
            continue
        elevation = run.fields[key]
        assert (elevation.state, elevation.literal, elevation.parsed) == (ValueState.SUPPORTED, "1200-1500 m", value)
        assert findings(run, key) == [(f"cleared:{key}:{run.regions[0].id}", "info")]


FEET = TEXT.replace("elevation_from_ft: 1500 ft", "alt. 1200-1500 ft")
FEET_RANGES = every_field(*((key, name, "1200-1500 ft", "alt. 1200-1500 ft") for key in ("elevation_from_ft", "elevation_to_ft")
    for name in ("1A", "1B")))


def test_a_feet_range_settles_each_field_on_its_end_of_the_range(tmp_path, first_pass_path):
    """As the metres range above, in feet: both readers write "alt. 1200-1500 ft", the image names
    it, each feet field's expert answers several_possibilities, and the lower field settles on
    1200 and the upper on 1500 (step.UPPER_ELEVATION), cleared."""
    rig = build_rig(tmp_path, FEET, candidates=FEET_RANGES)
    run = rig.specimen.run
    options = ("1200-1500 ft", "1200-1500")
    settle(rig, Scripted({key: several(*options) for key in ("elevation_from_ft", "elevation_to_ft")}))
    for key, value in (("elevation_from_ft", "1200"), ("elevation_to_ft", "1500")):
        if first_pass_path == "old":
            old_path_unchanged(run, key, options)
            continue
        elevation = run.fields[key]
        assert (elevation.state, elevation.literal, elevation.parsed) == (ValueState.SUPPORTED, "1200-1500 ft", value)
        assert findings(run, key) == [(f"cleared:{key}:{run.regions[0].id}", "info")]


def test_an_elevation_the_check_reads_as_ambiguous_is_not_put_to_the_rule(tmp_path, first_pass_path):
    """Both readers write "alt. 1200 m-4000 ft", a range in two units, and the image names it; the
    metres field's expert lists it. The elevation check reads it as ambiguous (mixed_units), no
    successful result, so the answer is not put to the rule (step._by_rule): the field stays
    ambiguous, and no check of the step refused a rule's answer (its decision is empty)."""
    rig = build_rig(tmp_path, TEXT + "\nalt. 1200 m-4000 ft", candidates=every_field(*(
        ("elevation_from_m", name, "1200 m-4000 ft", "alt. 1200 m-4000 ft") for name in ("1A", "1B"))))
    run = rig.specimen.run
    options = ("1200 m-4000 ft", "1200 m")
    decisions = {}
    prepared, outcomes, calls = research(rig, Scripted({"elevation_from_m": several(*options)}))
    field_step.apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls, decisions=decisions)
    old_path_unchanged(run, "elevation_from_m", options)
    assert decisions["elevation_from_m"] == {}


def chimaltenango(cited, *, images=None):
    """Label 1: 1A writes "province_state: Chimaltenago", 1B "province_state: Chimaltenango"
    (105526328's province); Getty TGN as the pilot's recordings answer each text (test_step.Gazetteer:
    "Chimaltenango" the department and its town, nothing for "Chimaltenago"); the expert's
    several_possibilities with both texts, citing those answers when `cited`."""
    readings = with_units(tuple(Reading(f"1{letter}", "r1", f"o1{letter.lower()}", "raw_reading",
        f"province_state: {name}") for letter, name in zip("AB", ("Chimaltenago", "Chimaltenango"))), images)
    task = FieldTask("province_state", True, FieldValue(state=ValueState.AMBIGUOUS), tuple(
        Candidate(r.name, r.text, r.text.split(": ")[1], "ev-" + r.name) for r in readings),
        FIELD_TOOLS["province_state"])
    with tempfile.TemporaryDirectory() as folder:
        gazetteer = Gazetteer(LocalBlobs(Path(folder)))
        answers = [asyncio.run(gazetteer.lookup("tgn", query, field_key="province_state"))
            for query in ("Chimaltenango", "Chimaltenago")]
    outcome = FieldOutcome("province_state", FieldAnswer(outcome="several_possibilities",
        options=["Chimaltenago", "Chimaltenango"], source_evidence_ids=[a.evidence.id for a in answers] if cited
        else [], explanation="The readers spell the department two ways."), model_calls=1)
    return task, readings, answers, outcome


def test_a_place_is_put_to_the_rule_on_the_source_answers_the_expert_cites():
    """Getty TGN confirms "Chimaltenango", one letter from 1A's text, and finds nothing for 1A's
    "Chimaltenago": one candidate with a SOURCE backing (rule 1). The answer put to the rule is
    the confirmed text resolved from 1B, with the department's record from the answer the expert
    cites (agreement.place_settling); citing nothing, a place has no lookup to settle on
    (common.txt's place line), so it is not put to the rule. Built here, the readings carry
    units on both arms."""
    task, readings, answers, outcome = chimaltenango(cited=True)
    ruled = field_step._by_rule(task, outcome, readings, answers)
    assert (ruled.answer.outcome, ruled.answer.literal, ruled.answer.reading_names, ruled.answer.value,
        ruled.answer.authority_id, ruled.answer.source_evidence_ids) == ("resolved", "Chimaltenango", ["1B"], None,
        "tgn:1000565", [a.evidence.id for a in answers])
    assert ruled.answer.explanation == ("The readers spell the department two ways. "
        "Options: Chimaltenago; Chimaltenango.")
    task, readings, answers, outcome = chimaltenango(cited=False)
    assert field_step._by_rule(task, outcome, readings, answers) is None


@pytest.mark.parametrize("key", ["taxon", "identified_by_irn"])
def test_a_taxon_and_the_identified_by_irn_are_not_put_to_the_rule(tmp_path, key, first_pass_path):
    """Spec section 4: when a field's parts are on different labels, the expert answers
    several_possibilities with the parts named per label, the owner's words there naming taxa;
    and the identified-by IRN gets no model call. Both readers write the field's text and the
    image names it: a several_possibilities answer is not put to the rule (step._by_rule), on
    either arm, and the taxon's stays ambiguous with its options."""
    rig = build_rig(tmp_path)
    run = rig.specimen.run
    readings = field_step.run_readings(run)
    [task] = [task for task in field_step.build_tasks(run)[1] if task.key == key]
    options = (LABEL[key], LABEL[key][:6])
    outcome = FieldOutcome(key, FieldAnswer(outcome="several_possibilities", options=list(options),
        explanation="x"), model_calls=1)
    assert field_step._by_rule(task, outcome, readings, []) is None
    if key == "taxon":
        settle(rig, Scripted({"taxon": several(*options)}))
        old_path_unchanged(run, "taxon", options)


def test_the_rules_answer_refused_when_applied_leaves_the_experts_own(tmp_path, first_pass_path):
    """The label's province line reads "Chimaltenago" (1A) and "Chimaltenango" (1B), its country
    "United States". Put to the rule, the several_possibilities answer settles the department of
    Guatemala, which the settled country does not hold (step._misfit refuses it when applied):
    the field is then as the expert's own answer leaves it, ambiguous with its options, and its
    decision names the refusal."""
    rig = build_rig(tmp_path, label_with(province_state="Chimaltenago"), label_with(province_state="Chimaltenango"),
        candidates=every_field(("province_state", "1A", "Chimaltenago", "province_state: Chimaltenago"),
            ("province_state", "1B", "Chimaltenango", "province_state: Chimaltenango")))
    run = rig.specimen.run

    async def script(task, readings, tools):
        answers = [await tools.lookup("tgn", query, field_key=task.key) for query in ("Chimaltenango", "Chimaltenago")]
        return FieldOutcome(task.key, FieldAnswer(outcome="several_possibilities",
            options=["Chimaltenago", "Chimaltenango"], source_evidence_ids=[a.evidence.id for a in answers],
            explanation="The readers spell the department two ways."), evidence=[a.evidence for a in answers],
            model_calls=1)

    decisions = {}
    prepared, outcomes, calls = research(rig, Scripted({"province_state": script}), tools=Gazetteer(rig.blobs))
    field_step.apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls, decisions=decisions)
    old_path_unchanged(run, "province_state", ("Chimaltenago", "Chimaltenango"))
    if first_pass_path == "units":
        assert decisions["province_state"] == {"refusal": decisions["province_state"]["refusal"]}
        assert decisions["province_state"]["refusal"] not in (None, "")


def test_the_rules_text_that_another_kind_of_field_settles_leaves_the_experts_own(tmp_path, first_pass_path):
    """The label writes no habitat line, and the habitat expert lists the precise location's text
    "Synthetic teaching garden": put to the rule, both readers write it and the image names it,
    but the precise location, another kind of field, settles that text (step._taken). The habitat
    is then as the expert's own answer leaves it, ambiguous with its options, and its decision
    says the text is taken."""
    rig = build_rig(tmp_path, label_with(habitat=None))
    run = rig.specimen.run
    options = (LABEL["precise_location"], "Synthetic teaching")
    decisions = {}
    prepared, outcomes, calls = research(rig, Scripted({"habitat": several(*options)}))
    field_step.apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls, decisions=decisions)
    old_path_unchanged(run, "habitat", options)
    assert decisions["habitat"].get("refusal") == ("taken" if first_pass_path == "units" else None)


def rival_rig(tmp_path, first_pass_path):
    """1A writes "Shrubs, forest", 1B "Shurbs, forest"; on the units arm the image names 1A's
    "Shrubs," and is uncertain at "forest"."""
    rig = build_rig(tmp_path, TEXT.replace("Synthetic grassland", "Shrubs, forest"),
        TEXT.replace("Synthetic grassland", "Shurbs, forest"), candidates=SHRUBS)
    if first_pass_path == "units":
        first = rig.specimen.run.observations[0].id

        def image(unit):
            texts = {span.text for span in unit.readers.values()}
            if len(texts) > 1:
                return unit.readers[first].text
            return UNCERTAIN if any("forest" in text for text in texts) else unit.image

        images(rig, image)
    return rig


def test_an_option_that_backs_a_rival_marks_the_rules_pick_and_lists_the_rival(tmp_path, first_pass_path):
    """1A writes "Shrubs, forest", 1B "Shurbs, forest"; the image names 1A's "Shrubs," and is
    uncertain at "forest". The expert lists "Shrubs" and "forest". Offered, "forest" is a rival
    both readers back, so rule 5 settles "Shrubs" (IMAGE above TEXT), marked as a conflict with
    "forest" listed, though the rule given "Shrubs" alone would clear it: the settlement is
    recorded with the answer's options offered (step._settlement)."""
    rig = rival_rig(tmp_path, first_pass_path)
    run = rig.specimen.run
    if first_pass_path == "units":
        readings = field_step.run_readings(run)
        [task] = [task for task in field_step.build_tasks(run)[1] if task.key == "habitat"]
        [offered] = agreement.labels(task, readings, [], offered=["Shrubs", "forest"]).values()
        [alone] = agreement.labels(task, readings, [], transcript="Shrubs",
            named=[readings[0]]).values()
        assert (offered.settled, offered.why, alone.settled, alone.cleared) == (
            frozenset({"Shrubs"}), "conflict", frozenset({"Shrubs"}), True)
    settle(rig, Scripted({"habitat": several("Shrubs", "forest")}))
    if first_pass_path == "old":
        return old_path_unchanged(run, "habitat", ("Shrubs", "forest"))
    habitat = run.fields["habitat"]
    assert (habitat.state, habitat.literal) == (ValueState.SUPPORTED, "Shrubs")
    assert habitat.reason.endswith("Marked for a person: another text has backing too: 'forest'.")
    assert findings(run, "habitat") == [(f"marked:habitat:{run.regions[0].id}:conflict", "warning")]


def test_the_answers_literal_is_offered_when_the_rules_settlement_is_recorded(tmp_path, first_pass_path):
    """The rival's label above, the answer giving "forest" as its literal (1A, 1B) and "Shrubs" and
    "Shurbs" as its options, as stored answers carry a literal beside their options. Offered with
    the literal, "forest" is the rival both readers back: "Shrubs" settles marked as a conflict,
    "forest" listed (step._settlement offers the answer's literal and options)."""
    rig = rival_rig(tmp_path, first_pass_path)
    run = rig.specimen.run
    settle(rig, Scripted({"habitat": answering(FieldAnswer(outcome="several_possibilities", literal="forest",
        reading_names=["1A", "1B"], options=["Shrubs", "Shurbs"], explanation="The readers' texts differ."))}))
    if first_pass_path == "old":
        return old_path_unchanged(run, "habitat", ("Shrubs", "Shurbs"))
    habitat = run.fields["habitat"]
    assert (habitat.state, habitat.literal) == (ValueState.SUPPORTED, "Shrubs")
    assert habitat.reason.endswith("Marked for a person: another text has backing too: 'forest'.")
    assert findings(run, "habitat") == [(f"marked:habitat:{run.regions[0].id}:conflict", "warning")]


OUTCOMES = Path(__file__).parents[1] / "fixtures" / "units_several_possibilities_outcomes.json"


def stored_outcome(index):
    """A stored several_possibilities outcome of WP 1.5 (tests/fixtures/
    units_several_possibilities_outcomes.json): the field's task, the readings with their units,
    the field's lookups and the outcome."""
    case = json.loads(OUTCOMES.read_text(encoding="utf-8"))["cases"][index]
    readings = tuple(Reading(r["name"], r["region_id"], r["observation_id"], r["input_source"], r["text"],
        units=ReadingUnits.model_validate(r["units"]) if r["units"] is not None else None) for r in case["readings"])
    given = case["task"]
    task = FieldTask(given["key"], given["mandatory"], FieldValue.model_validate(given["current"]),
        tuple(Candidate(**candidate) for candidate in given["candidates"]), tuple(given["tools"]))
    lookups = [SourceAnswer(item["source"], item["query"], LookupStatus(item["status"]),
        tuple(SourceCandidate(**candidate) for candidate in item["candidates"]),
        Evidence(**item["evidence"]) if item["evidence"] else None, note=item["note"]) for item in case["lookups"]]
    return task, readings, lookups, FieldOutcome(task.key, FieldAnswer(**case["answer"]), model_calls=1)


@pytest.mark.parametrize(("index", "literal", "names"), [(0, "AZARBAITAN", ["2A"]), (1, None, None)],
    ids=["r1-pair-105526647-precise-location", "r1-pair-105526617-catalogue-number"])
def test_a_stored_answers_literal_is_offered_to_the_rule(index, literal, names):
    """Two stored answers whose literal the rule is offered beside their options (step._by_rule).
    105526647's precise location: the literal "AZARBAITAN" (2A), no options; the image names 2A's
    text there, so it is put to the rule on that text. 105526617's catalogue number: the literal
    "FMNHINS\n4486488" (1B), options "4456488" and "4486488"; offered, the literal is a backed text
    that holds the option "4486488" (P5), and it runs over two lines, which a catalogue number's
    literal may not (agreement.written_runs), so the answer is not put to the rule. Built here,
    the readings carry units on both arms."""
    task, readings, lookups, outcome = stored_outcome(index)
    ruled = field_step._by_rule(task, outcome, readings, lookups)
    if literal is None:
        assert ruled is None
    else:
        assert (ruled.answer.literal, ruled.answer.reading_names) == (literal, names)


def test_a_slide_code_is_never_put_to_the_rule_as_a_habitat(tmp_path, first_pass_path):
    """Both readers write the habitat line "IX-17-66-2", a slide code, and the image names it; the
    expert lists it. A written rule refuses a slide code as a habitat (extraction_refusal), so the
    answer is not put to the rule (step._by_rule), and the field stays ambiguous."""
    rig = build_rig(tmp_path, label_with(habitat="IX-17-66-2"))
    run = rig.specimen.run
    settle(rig, Scripted({"habitat": several("IX-17-66-2", "IX-17-66")}))
    old_path_unchanged(run, "habitat", ("IX-17-66-2", "IX-17-66"))


def test_a_persons_label_is_put_to_the_rule_on_the_persons_text(tmp_path, monkeypatch, first_pass_path):
    """Label 1's readers write "Synthetic  grassland" (two spaces); label 2's both write
    "Synthetic grassland", and a person transcribed label 2. Both labels settle that text, letter
    case and spacing aside; put to the rule, the literal is as the person's reading writes it
    (rule 2), from label 2's readings, not label 1's spacing, which comes first in reading order."""
    a_second_label(monkeypatch, "habitat: Synthetic grassland")
    rig = build_rig(tmp_path, TEXT.replace("Synthetic grassland", "Synthetic  grassland"))
    run = rig.specimen.run
    second = [o for o in run.observations if o.region_id == run.regions[1].id]
    [at] = [index for index, item in enumerate(run.transcripts) if item.region_id == run.regions[1].id]
    run.transcripts[at] = run.transcripts[at].model_copy(update={"text": second[0].literal_text,
        "resolved": True, "selected_observation_id": second[0].id, "actor": "reviewer@example.org"})
    if first_pass_path == "units":
        store_reading_units(run, [source_units(run, run.regions[1].id)])
    options = ("Synthetic grassland", "grassland")
    settle(rig, Scripted({"habitat": several(*options)}))
    if first_pass_path == "old":
        return old_path_unchanged(run, "habitat", options)
    habitat = run.fields["habitat"]
    assert (habitat.state, habitat.literal) == (ValueState.SUPPORTED, "Synthetic grassland")
    # The person's reading is the value's source (step._lineage).
    assert (habitat.input_source, habitat.source_region_id) == ("decided_transcript", run.regions[1].id)


def test_a_numeric_date_the_check_reads_two_ways_is_not_put_to_the_rule(tmp_path, first_pass_path):
    """Both readers write the date "4-5-48" and the image names it; the expert lists it. The date
    check reads it as 4 May or 5 April (day_month_order_ambiguous), no one value, so the answer is
    not put to the rule (step._by_rule) and the field stays ambiguous."""
    rig = build_rig(tmp_path, label_with(date_visited_from="4-5-48"))
    run = rig.specimen.run
    settle(rig, Scripted({"date_visited_from": several("4-5-48", "5-4-48")}))
    old_path_unchanged(run, "date_visited_from", ("4-5-48", "5-4-48"))


def test_two_texts_cited_as_two_places_settle_on_the_rules_ranked_pick():
    """1A writes "Escuintla", 1B and 1C "Chimaltenango", and the image names 1A's text; the
    expert cites Getty TGN's answers, which confirm each as a department of its own, and lists
    both. Neither text has a SOURCE backing (rule 1): IMAGE backs "Escuintla", TEXT
    "Chimaltenango", and rule 5 takes "Escuintla", marked as a conflict with "Chimaltenango"
    listed, its record from the cited answer that settles it. Built here, the readings carry units
    on both arms; the organiser gave a candidate to 1A alone."""
    readings = with_units(tuple(Reading(f"1{letter}", "r1", f"o1{letter.lower()}", "raw_reading",
        f"province_state: {name}") for letter, name in zip("ABC", ("Escuintla", "Chimaltenango", "Chimaltenango"))),
        {"r1": "o1a"})
    task = FieldTask("province_state", True, FieldValue(state=ValueState.AMBIGUOUS),
        (Candidate("1A", readings[0].text, "Escuintla", "ev-1A"),), FIELD_TOOLS["province_state"])
    with tempfile.TemporaryDirectory() as folder:
        gazetteer = Gazetteer(LocalBlobs(Path(folder)))
        answers = [asyncio.run(gazetteer.lookup("tgn", query, field_key="province_state"))
            for query in ("Escuintla", "Chimaltenango")]
    options = ["Escuintla", "Chimaltenango"]
    outcome = FieldOutcome("province_state", FieldAnswer(outcome="several_possibilities", options=options,
        source_evidence_ids=[a.evidence.id for a in answers], explanation="x"), model_calls=1)
    ruled = field_step._by_rule(task, outcome, readings, answers)
    assert (ruled.answer.literal, ruled.answer.reading_names, ruled.answer.authority_id) == (
        "Escuintla", ["1A"], "tgn:1000566")
    [label] = agreement.labels(task, readings, answers, transcript="Escuintla", named=[readings[0]],
        offered=options).values()
    assert (label.settled, label.why, label.others) == (frozenset({"Escuintla"}), "conflict", ("Chimaltenango",))


def test_an_abbreviation_two_cited_answers_expand_apart_is_not_put_to_the_rule(tmp_path, first_pass_path):
    """Both readers write the country "P.I." and the image names it; the expert cites Getty TGN's
    answers for "Philippine Islands" and "Pacific Islands", two nations "P.I." abbreviates
    (test_step.Gazetteer), and lists "P.I." and "Philippines". The cited answers settle "P.I." as
    two places, so it is not put to the rule (step._by_rule; the coordinator's ruling Y1): the
    field is as the expert's own answer leaves it, and no check refused a rule's answer."""
    rig = build_rig(tmp_path, label_with(country="P.I."))
    run = rig.specimen.run

    async def script(task, readings, tools):
        answers = [await tools.lookup("tgn", query, field_key=task.key)
            for query in ("Philippine Islands", "Pacific Islands")]
        return FieldOutcome(task.key, FieldAnswer(outcome="several_possibilities", options=["P.I.", "Philippines"],
            source_evidence_ids=[a.evidence.id for a in answers], explanation="Two nations fit."),
            evidence=[a.evidence for a in answers], model_calls=1)

    decisions = {}
    prepared, outcomes, calls = research(rig, Scripted({"country": script}), tools=Gazetteer(rig.blobs))
    field_step.apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls, decisions=decisions)
    old_path_unchanged(run, "country", ("P.I.", "Philippines"))
    assert decisions["country"].get("refusal") is None


class Amazonas(Gazetteer):
    """Getty TGN with two first-level units named "Amazonas", one in Brazil, one in Peru (made-up
    records)."""

    PLACES = {**Gazetteer.PLACES,
        "Amazonas, Brazil": [("Amazonas", "tgn:am-br", Gazetteer.FIRST, (("Brazil", "tgn:brazil"),))],
        "Amazonas, Peru": [("Amazonas", "tgn:am-pe", Gazetteer.FIRST, (("Peru", "tgn:peru"),))]}


@pytest.mark.parametrize("order", [("Amazonas, Brazil", "Amazonas, Peru"), ("Amazonas, Peru", "Amazonas, Brazil")],
    ids=["brazil-first", "peru-first"])
def test_one_text_two_cited_answers_place_apart_stays_ambiguous_with_no_derived_country(
        tmp_path, first_pass_path, order):
    """Both readers write the province "Amazonas", the image names it, and the label writes no
    country; the expert cites Getty TGN's answers for "Amazonas, Brazil" and "Amazonas, Peru", one
    first-level unit each, and lists "Amazonas" and "Amazona". The cited answers settle the one
    text as two places (the coordinator's ruling Y1): it is not put to the rule, whichever answer
    is cited first, so the province stays ambiguous with the answer's options and no country is
    derived from it."""
    rig = build_rig(tmp_path, label_with(country=None, province_state="Amazonas", county=None, city=None),
        candidates=[candidate for candidate in every_field(
            ("province_state", "1A", "Amazonas", "province_state: Amazonas"),
            ("province_state", "1B", "Amazonas", "province_state: Amazonas"))
            if candidate[0] not in ("country", "county", "city")])
    run = rig.specimen.run

    async def script(task, readings, tools):
        answers = [await tools.lookup("tgn", query, field_key=task.key) for query in order]
        return FieldOutcome(task.key, FieldAnswer(outcome="several_possibilities", options=["Amazonas", "Amazona"],
            source_evidence_ids=[a.evidence.id for a in answers], explanation="Two units of this name."),
            evidence=[a.evidence for a in answers], model_calls=1)

    lacks = answering(FieldAnswer(outcome="label_lacks_value", explanation="Not on the label."))
    prepared, outcomes, calls = research(rig, Scripted({"province_state": script, "country": lacks, "county": lacks,
        "city": lacks}), tools=Amazonas(rig.blobs))
    field_step.apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls)
    old_path_unchanged(run, "province_state", ("Amazonas", "Amazona"))
    country = run.fields["country"]
    assert country.state != ValueState.SUPPORTED and country.layer != "derived"


def test_a_label_with_no_backed_candidate_takes_no_part_beside_one_that_settles(
        tmp_path, monkeypatch, first_pass_path):
    """Label 1's readers write "Shrubs" and "Shurbs", the image uncertain there; both readers of
    label 2 write "Synthetic grassland" and the image names it. The expert lists both texts. Put
    to the rule, label 1 backs nothing and takes no part (P1): label 2's text settles, cleared."""
    a_second_label(monkeypatch, "habitat: Synthetic grassland")
    rig = build_rig(tmp_path, TEXT.replace("Synthetic grassland", "Shrubs"),
        TEXT.replace("Synthetic grassland", "Shurbs"), candidates=SHRUBS)
    run = rig.specimen.run
    if first_pass_path == "units":
        images(rig, lambda unit: UNCERTAIN)
    settle(rig, Scripted({"habitat": several("Synthetic grassland", "Shrubs")}))
    if first_pass_path == "old":
        return old_path_unchanged(run, "habitat", ("Synthetic grassland", "Shrubs"))
    habitat = run.fields["habitat"]
    assert (habitat.state, habitat.literal) == (ValueState.SUPPORTED, "Synthetic grassland")
    assert findings(run, "habitat") == [(f"cleared:habitat:{run.regions[1].id}", "info")]


def test_the_rule_names_only_the_readings_that_write_its_text_as_whole_words(tmp_path, first_pass_path):
    """1A writes "Shrubs", 1B "Shrubsland" (which holds "Shrubs" inside a word, and is 1B's own
    candidate), and the image names 1A's text. Put to the rule, "Shrubs" clears, its literal
    named in 1A alone (a literal inside another reader's word is no text of that reader's)."""
    rig = build_rig(tmp_path, TEXT.replace("Synthetic grassland", "Shrubs"),
        TEXT.replace("Synthetic grassland", "Shrubsland"), candidates=every_field(
            ("habitat", "1A", "Shrubs", "habitat: Shrubs"), ("habitat", "1B", "Shrubsland", "habitat: Shrubsland")))
    run = rig.specimen.run
    if first_pass_path == "units":
        naming(rig, 0)
    settle(rig, Scripted({"habitat": several("Shrubs", "Shrubsland")}))
    if first_pass_path == "old":
        return old_path_unchanged(run, "habitat", ("Shrubs", "Shrubsland"))
    habitat = run.fields["habitat"]
    assert (habitat.state, habitat.literal, habitat.settled_observation_ids) == (
        ValueState.SUPPORTED, "Shrubs", [run.observations[0].id])
    assert findings(run, "habitat") == [(f"cleared:habitat:{run.regions[0].id}", "info")]
