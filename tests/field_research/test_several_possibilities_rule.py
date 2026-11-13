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

import json
from pathlib import Path

import pytest
from test_settlement_rule import findings, images, naming
from test_step import (
    LABEL,
    TEXT,
    Gazetteer,
    Scripted,
    a_second_label,
    answering,
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
from specimen_digitization.application.workflow import store_reading_units
from specimen_digitization.field_research import agreement
from specimen_digitization.field_research import step as field_step
from specimen_digitization.field_research.agreement import PLACE_ORDER
from specimen_digitization.field_research.contracts import (
    Candidate,
    FieldAnswer,
    FieldOutcome,
    FieldTask,
    PlaceRef,
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
    """Both readers write "Elev. 4800 ft.", the organiser's candidate is "4800 ft" and the image
    names the text; the expert answers several_possibilities with the literal "Elev. 4800 ft."
    and its options, as r1/three 105526328's expert did. Put to the rule, the literal, offered,
    settles; applied, agreement.literal_refusal refuses it, as it extends the candidate
    (NOT_CANDIDATE): the field is then as the expert's own answer leaves it, ambiguous with its
    options, and its decision names the refusal."""
    rig = build_rig(tmp_path, TEXT.replace("elevation_from_ft: 1500 ft", "Elev. 4800 ft."), candidates=every_field(
        *(("elevation_from_ft", name, "4800 ft", "Elev. 4800 ft.") for name in ("1A", "1B"))))
    run = rig.specimen.run
    options = ("Elev. 4800 ft.", "Elev. +800 ft.")
    decisions = {}
    prepared, outcomes, calls = research(rig, Scripted({"elevation_from_ft": answering(FieldAnswer(
        outcome="several_possibilities", literal="Elev. 4800 ft.", reading_names=["1A"], options=list(options),
        explanation="The readers' texts differ."))}))
    field_step.apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls, decisions=decisions)
    old_path_unchanged(run, "elevation_from_ft", options)
    assert decisions["elevation_from_ft"] == ({"refusal": "not_candidate"} if first_pass_path == "units" else {})


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


@pytest.mark.parametrize(("index", "literal", "names"), [(0, "AZARBAITAN", ["2A"]), (1, None, None), (2, None, None)],
    ids=["r1-pair-105526647-precise-location", "r1-pair-105526617-catalogue-number", "r1-three-105526330-date-to"])
def test_a_stored_answers_literal_is_offered_to_the_rule(index, literal, names):
    """Three stored answers whose literal the rule is offered beside their options
    (step._by_rule). 105526647's precise location: the literal "AZARBAITAN" (2A), options
    "AZARBAITAN" and "AZARBAIJAN"; the image names 2A's text there, so it is put to the rule on
    that text. 105526617's catalogue number: the literal "FMNHINS\n4486488" (1B), options
    "4456488" and "4486488"; offered, the literal is a backed text that holds the option
    "4486488" (P5), and it runs over two lines, which a catalogue number's literal may not
    (agreement.written_runs), so the answer is not put to the rule. 105526330's date visited to:
    the literal "Guatemala, IV-25" (2A, 2B), options "1948-04-25" and "1948-04-26"; offered, the
    literal is a candidate beside the organiser's "1948", each backed by the readers' text alone:
    rule 5's text against text, which leaves the field ambiguous with both as options, as rule 6
    stores it, so the label settles neither and the answer is not put to the rule. Offered only
    their options, the rule would settle the last two on "4486488" and "1948". Built here, the
    readings carry units on both arms."""
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


class Records(Gazetteer):
    """Getty TGN and Wikidata answering these queries with these made-up records, one candidate
    each: two first-level units named "Amazonas", one in Brazil and one in Peru; Brazil's as TGN
    describes it with its parent and without it, and as Wikidata's own record; and two nations
    named "Congo" with no parents. Every other query as test_step.Gazetteer answers it."""

    BRAZIL, PERU = PlaceRef("Brazil", "tgn:brazil"), PlaceRef("Peru", "tgn:peru")
    RECORDS = {
        ("tgn", "Amazonas, Brazil"): SourceCandidate("Amazonas", "tgn:am-br", Gazetteer.FIRST, parents=(BRAZIL,)),
        ("tgn", "Amazonas, Peru"): SourceCandidate("Amazonas", "tgn:am-pe", Gazetteer.FIRST, parents=(PERU,)),
        ("tgn", "Amazonas, state"): SourceCandidate("Amazonas", "tgn:am-br", Gazetteer.FIRST),
        ("wikidata", "Amazonas, Brazil"): SourceCandidate("Amazonas", "wikidata:am-br", "state",
            parents=(PlaceRef("Brazil", "wikidata:brazil"),)),
        ("tgn", "Congo, Brazzaville"): SourceCandidate("Congo", "tgn:cg", Gazetteer.NATION, iso_code="CG"),
        ("tgn", "Congo, Kinshasa"): SourceCandidate("Congo", "tgn:cd", Gazetteer.NATION, iso_code="CD"),
    }

    def _answer(self, source_id, query):
        answer = super()._answer(source_id, query)
        if (source_id, query) not in self.RECORDS:
            return answer
        candidate = self.RECORDS[source_id, query]
        evidence = answer.evidence.model_copy(update={"kind": "authority", "locator": candidate.authority_id,
            "excerpt": f"match\n{candidate.name} | {candidate.authority_id} | {candidate.kind} | "})
        return SourceAnswer(source_id, query, LookupStatus.SUCCESS, (candidate,), evidence, note="match")


AMAZONAS = ("Amazonas", "Amazona")


@pytest.mark.parametrize(("key", "written", "cited", "also", "options"), [
    pytest.param("province_state", "Amazonas", (("tgn", "Amazonas, Brazil"), ("tgn", "Amazonas, Peru")), (), AMAZONAS,
        id="amazonas-brazil-and-peru"),
    pytest.param("country", "Congo", (("tgn", "Congo, Brazzaville"), ("tgn", "Congo, Kinshasa")), (), ("Congo", "Cong"),
        id="congo-two-records"),
    pytest.param("country", "P.I.", (("tgn", "Philippine Islands"), ("tgn", "Pacific Islands")), (),
        ("P.I.", "Philippines"), id="p-i-two-expansions"),
    pytest.param("province_state", "Amazonas", (("tgn", "Amazonas, Brazil"), ("tgn", "Amazonas, state")), (), AMAZONAS,
        id="one-record-described-twice"),
    pytest.param("province_state", "Amazonas", (("tgn", "Amazonas, Brazil"), ("wikidata", "Amazonas, Brazil")),
        (("tgn", "Amazonas, Peru"),), AMAZONAS, id="two-gazetteers"),
])
def test_a_place_fields_several_possibilities_is_not_put_to_the_rule(
        tmp_path, first_pass_path, key, written, cited, also, options):
    """Both readers write the place, the image names it, and the expert cites two answers and
    lists the options: "Amazonas" as Brazil's and Peru's units; "Congo" as two nations, "tgn:cg"
    and "tgn:cd", with no parents; "P.I." as "Philippine Islands" and "Pacific Islands", two
    nations it abbreviates (test_step.Gazetteer); "Amazonas" as one record described with its
    parent and without; "Amazonas" as Brazil's unit in Getty TGN and in Wikidata, Peru's asked
    too and not cited. Location reconciliation settles none of them, and a place value field's
    several_possibilities is not put to the rule (step._by_rule; the coordinator's ruling R5-1 of
    2026-11-13): on both arms the field stays ambiguous with the answer's options, no check
    refused a rule's answer, and no place above it is derived."""
    lacks = answering(FieldAnswer(outcome="label_lacks_value", explanation="Not on the label."))
    if key == "country":
        rig, others = build_rig(tmp_path, label_with(country=written)), {}
    else:
        rig = build_rig(tmp_path, label_with(country=None, province_state=written, county=None, city=None),
            candidates=[candidate for candidate in every_field(
                (key, "1A", written, f"{key}: {written}"), (key, "1B", written, f"{key}: {written}"))
                if candidate[0] not in ("country", "county", "city")])
        others = dict.fromkeys(("country", "county", "city"), lacks)
    run = rig.specimen.run

    async def script(task, readings, tools):
        answers = {lookup: await tools.lookup(*lookup, field_key=task.key) for lookup in (*cited, *also)}
        return FieldOutcome(task.key, FieldAnswer(outcome="several_possibilities", options=list(options),
            source_evidence_ids=[answers[lookup].evidence.id for lookup in cited], explanation="Two places fit."),
            evidence=[answer.evidence for answer in answers.values()], model_calls=1)

    decisions = {}
    prepared, outcomes, calls = research(rig, Scripted({key: script, **others}), tools=Records(rig.blobs))
    field_step.apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls, decisions=decisions)
    old_path_unchanged(run, key, options)
    assert decisions[key].get("refusal") is None and decisions[key].get("rule") != "rule_settled"
    assert not [above for above in PLACE_ORDER[:PLACE_ORDER.index(key)] if run.fields[above].layer == "derived"]


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
