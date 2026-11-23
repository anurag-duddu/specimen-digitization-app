"""A locality's printed heading is not part of the Precise Location (lane LOC1 of the autonomy program, 2026-11-23).

The owner's words: "Yes, fix it" (2026-11-23). Everything else here is the coordinator's brief for the lane or this
lane's own reading. Production record d6a58cb2 (slide 105527241, on origin/main 681313a2) settled the Precise
Location "Loc: AFGHANISTAN,\\n27 km. north of Kunduz"; the truth sheet's value has no "Loc:". A precise location
literal that starts with a locality heading is now refused (agreement.LOCALITY_HEADING, locality_heading), as PR
#464 refuses a habitat that starts with the heading "Host": the expert is sent back, the answer is never rewritten.

The heading forms are the ones the truth sheets' transcripts and the recorded readings of the 100 truth slides write
before a locality: "Loc:", "LOC:", "LOC.", "LOC." with no space after it, and "Locality" with no mark
(~/specimen-golive/autonomy-program/LOC1/headings.txt). Apart from the production answer, the label texts here are
made up.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic_ai import ModelRetry
from test_first_pass_advice import with_units
from test_habitat_changes_no_other_field import expert_answering
from test_step import COLLECTORS, TEXT, Scripted, answering, build_rig, research, settle

from specimen_digitization.application.domain import FieldValue, ValueState
from specimen_digitization.field_research import agreement, experts
from specimen_digitization.field_research import step as field_step
from specimen_digitization.field_research.contracts import FieldAnswer, FieldTask, Reading

# Slide 105527241's host-data label as its readers write it, and the Precise Location production settled on it.
LABEL_105527241 = ("Chicago Natural History Museum\nHost Data\nLoc: AFGHANISTAN,\n27 km. north of Kunduz\n"
    "Date 13-VII-1965\nCollr SA")
PRODUCTION_ANSWER = "Loc: AFGHANISTAN,\n27 km. north of Kunduz"
WITHOUT_HEADING = "AFGHANISTAN,\n27 km. north of Kunduz"


def two_readers_of(first, second):
    return with_units((Reading("2A", "label2", "obs2a", "raw_reading", first),
        Reading("2B", "label2", "obs2b", "raw_reading", second)))


def locality_expert(readings):
    task = FieldTask("precise_location", False, FieldValue(), (), ("geolocate",))
    return experts._Expert(task, readings, SimpleNamespace(sources=("geolocate",)), None)


def resolved(literal, *names):
    return FieldAnswer(outcome="resolved", literal=literal, reading_names=list(names) or ["1A", "1B"],
        explanation="The label writes this locality.")


# ---- the heading ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize(("literal", "heading"), [
    ("Loc: AFGHANISTAN,", True), ("LOC: USA: NEBRASKA", True), ("LOC. PERU: Yura,", True),
    ("LOC.PERU: Yura, Arequipa 8200'", True), ("Loc:AFGHANISTAN", True), ("Loc.", True), ("Loc:", True),
    ("Locality Logan Canyon", True), ("LOCALITY: Logan Canyon", True), ("Locality", True), ("(Loc:) Kunduz", True),
    (PRODUCTION_ANSWER, True),
    (WITHOUT_HEADING, False), ("Loc Ninh, Binh Phuoc", False), ("Locust Grove", False), ("Loch Ness", False),
    ("Locarno", False), ("Localities near Kunduz", False), ("Kunduz, Loc: Afghanistan", False),
    ("27 km. north of Kunduz\nLoc: AFGHANISTAN", False), ("", False), (None, False),
])
def test_a_text_that_starts_with_a_locality_heading(literal, heading):
    assert agreement.locality_heading(literal) is heading


def test_the_production_answer_of_slide_105527241_is_refused_and_never_rewritten():
    """Production settled this answer on origin/main 681313a2. The expert's own check now sends the expert back
    with the reason; the locality after the heading, given with its line break or a space for it, passes."""
    readings = two_readers_of(LABEL_105527241, LABEL_105527241)
    with pytest.raises(ModelRetry, match="leave the heading out") as refused:
        locality_expert(readings).validate(resolved(PRODUCTION_ANSWER, "2A", "2B"))
    assert refused.value.check == "locality_heading"
    assert field_step.refusal_code(agreement.LOCALITY_HEADING) == "locality_heading"
    for given in (WITHOUT_HEADING, "AFGHANISTAN, 27 km. north of Kunduz"):
        assert locality_expert(readings).validate(resolved(given, "2A", "2B")).literal == WITHOUT_HEADING


@pytest.mark.parametrize("literal", ["LOC. Asheville School\nNorth Carolina", "Locality Asheville School"])
def test_each_heading_form_is_refused_by_the_experts_check(literal):
    label = f"Synthetic Museum\n{literal}\n3-VII-1950"
    readings = two_readers_of(label, label)
    with pytest.raises(ModelRetry) as refused:
        locality_expert(readings).validate(resolved(literal, "2A", "2B"))
    assert refused.value.check == "locality_heading"


def test_a_word_that_only_starts_with_loc_and_a_heading_inside_the_text_are_not_refused():
    for literal in ("Locust Grove", "Loc Ninh", "Kunduz, Loc: Afghanistan"):
        label = f"Synthetic Museum\n{literal}\n3-VII-1950"
        readings = two_readers_of(label, label)
        assert locality_expert(readings).validate(resolved(literal, "2A", "2B")).literal == literal


def test_only_the_precise_location_has_this_rule_and_the_habitats_heading_rule_is_unchanged():
    label = "Synthetic Museum\nHost: Mus\nLoc: Synthetic Co."
    readings = two_readers_of(label, label)
    refusal = agreement.literal_refusal(FieldTask("precise_location", False, FieldValue(), (), ()), readings,
        literal="Loc: Synthetic Co.", named=list(readings))
    assert refusal.reason == agreement.LOCALITY_HEADING and not refusal.differ
    habitat = FieldTask("habitat", False, FieldValue(), (), ())
    assert agreement.literal_refusal(habitat, readings, literal="Loc: Synthetic Co.", named=list(readings)) is None
    assert agreement.literal_refusal(habitat, readings, literal="Host: Mus", named=list(readings)).reason == (
        agreement.HOST_HEADING)
    other = FieldTask("collection_method", False, FieldValue(), (), ())
    assert agreement.literal_refusal(other, readings, literal="Loc: Synthetic Co.", named=list(readings)) is None


def test_the_heading_check_is_left_out_only_where_the_caller_says_so():
    """As the habitat's: the expert's own check and the application to the record refuse (the default); only the
    step's pass before its guard on shared text leaves the check out (step._BEFORE_GUARD)."""
    readings = (Reading("1A", "label1", "obs1a", "raw_reading", LABEL_105527241),
        Reading("1B", "label1", "obs1b", "raw_reading", LABEL_105527241))
    task = FieldTask("precise_location", False, FieldValue(), (), ())
    assert agreement.literal_refusal(task, readings, literal=PRODUCTION_ANSWER, named=readings).reason == (
        agreement.LOCALITY_HEADING)
    assert agreement.literal_refusal(task, readings, literal=PRODUCTION_ANSWER, named=readings, heading=False) is None


# ---- through the step ----------------------------------------------------------------------------------------

HEADED_TEXT = TEXT.replace("precise_location: Synthetic teaching garden\n", "Loc: Synthetic\nteaching garden\n")
HEADED = "Loc: Synthetic\nteaching garden"
NOWHERE = "Text no reading writes"


def others(run):
    """Every field but Precise Location as the step leaves it; evidence ids are made anew on every application."""
    return {key: (value.state, value.literal, value.parsed, value.normalized, value.layer, value.reason)
        for key, value in run.fields.items() if key != "precise_location"}


def test_the_step_refuses_a_precise_location_that_starts_with_the_heading_and_nothing_else_moves(tmp_path):
    """The step repeats the check (agreement.refusal through step._refusal): the Precise Location is unresolved, its
    reason says why, and every other field ends as where the precise location answer settles nothing. On origin/main
    681313a2 it settles "Loc: Synthetic\\nteaching garden"."""
    runs = []
    for folder, literal in (("under-test", HEADED), ("baseline", NOWHERE)):
        rig = build_rig(tmp_path / folder, HEADED_TEXT, HEADED_TEXT, candidates=COLLECTORS)
        settle(rig, Scripted({"precise_location": answering(resolved(literal))}))
        runs.append(rig.specimen.run)
    run, baseline = runs
    value = run.fields["precise_location"]
    assert value.state == ValueState.UNRESOLVED and value.literal is None
    assert value.reason.startswith(agreement.LOCALITY_HEADING)
    assert others(run) == others(baseline)


def test_the_locality_after_the_heading_settles_through_the_step(tmp_path):
    rig = build_rig(tmp_path, HEADED_TEXT, HEADED_TEXT, candidates=COLLECTORS)
    run = rig.specimen.run
    settle(rig, Scripted({"precise_location": answering(resolved("Synthetic\nteaching garden"))}))
    value = run.fields["precise_location"]
    assert (value.state, value.literal) == (ValueState.SUPPORTED, "Synthetic\nteaching garden")


# ---- through the real resolver (experts.make_resolver: the expert's check and its retries) -----------------------

def through_the_resolver(tmp_path, *answers):
    rig = build_rig(tmp_path, HEADED_TEXT, HEADED_TEXT, candidates=COLLECTORS)
    run = rig.specimen.run
    expert, asked = expert_answering(*answers)
    prepared, outcomes, calls = research(rig, Scripted({"precise_location": expert}))
    [received] = [outcome for outcome in outcomes if outcome.key == "precise_location"]
    field_step.apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls)
    return run, received, asked


def test_an_expert_sent_back_for_the_heading_that_leaves_it_out_settles_the_locality(tmp_path):
    run, received, asked = through_the_resolver(tmp_path, HEADED, "Synthetic\nteaching garden")
    assert asked == [HEADED, "Synthetic\nteaching garden"]
    assert (received.answer.outcome, received.answer.literal, received.fallback) == (
        "resolved", "Synthetic\nteaching garden", False)
    value = run.fields["precise_location"]
    assert (value.state, value.literal) == (ValueState.SUPPORTED, "Synthetic\nteaching garden")


def test_limit_an_expert_that_repeats_the_heading_leaves_the_precise_location_unsettled(tmp_path):
    """The stated limit, as the habitat's: where no later RESOLVED answer of the attempt passes the check, the
    resolver's fallback is the outcome (sources_cannot_resolve, no literal) and the Precise Location does not settle,
    where origin/main settles the first answer."""
    run, received, asked = through_the_resolver(tmp_path, HEADED)
    assert len(asked) > 1 and set(asked) == {HEADED}
    assert (received.answer.outcome, received.answer.literal, received.fallback) == (
        "sources_cannot_resolve", None, True)
    assert run.fields["precise_location"].state == ValueState.UNRESOLVED
