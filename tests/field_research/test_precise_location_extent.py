"""WP 2.2: Precise Location is the label's locality as written (the ontology's rule
precise_location_extent), on the units path; the old path is unchanged.

The cases are the two pilot labels the plan names, from tests/fixtures/field_model_pilot_rows.json:
105526329's town-only locality, "Yepocapa, 4800 ft." over "Chimaltenango, Guatemala" (its truth
row's precise location is the locality's lines as written, :325), and 105526321's whole locality
block, "E. slope Mt. McKinley" over "Davao Prov." over "Mindanao, P.I." (:30). Each test runs on
both paths (conftest.py): on the units path the whole locality settles, is not cleared as not on
the label and is not refused for its elevation; on the old path each keeps origin/main's result.
"""

from __future__ import annotations

import pytest
from test_first_pass_advice import with_units
from test_step import (
    IN_YEPOCAPA,
    LACKS,
    TODAY,
    Gazetteer,
    answering,
    build_rig,
    cleared_as_not_on_label,
    not_on_label_rows,
    research,
)

from specimen_digitization.application.domain import ValueState
from specimen_digitization.field_research import agreement
from specimen_digitization.field_research import step as field_step
from specimen_digitization.field_research.contracts import FIELD_TOOLS, FieldAnswer, FieldTask, Reading
from specimen_digitization.application.domain import FieldValue

# 105526329 (field_model_pilot_rows.json:300-325), the department as the plan's brief spells it.
YEPOCAPA = "Yepocapa, 4800 ft.\nChimaltenango, Guatemala"
# 105526321's locality block (field_model_pilot_rows.json:5-30).
MCKINLEY = "E. slope Mt. McKinley\nDavao Prov.\nMindanao, P.I."
# The same block with its elevation among the lines, as 105526326's label writes it (:202).
MCKINLEY_3300 = "E. slope Mt. McKinley\nDavao, Prov. 3300'\nMindanao, P.I."
FIELDS = [key for key in FIELD_TOOLS if key != "identified_by_irn"]


def label_readings(text, units):
    readings = (Reading("1A", "r1", "o1a", "raw_reading", text), Reading("1B", "r1", "o1b", "raw_reading", text))
    return with_units(readings) if units else readings


@pytest.mark.parametrize("literal", [YEPOCAPA, "Yepocapa, 4800 ft.", MCKINLEY_3300])
def test_a_precise_location_holding_an_elevation_among_its_lines_is_refused_on_the_old_path_only(
        first_pass_path, literal):
    """agreement.literal_refusal on the precise location read from the transcript: on the units
    path (readings that carry their units) an elevation written among the locality's lines is part
    of it; on the old path it is another field's text (HOLDS_AN_ELEVATION), as on origin/main."""
    text = YEPOCAPA if literal.startswith("Yepocapa") else MCKINLEY_3300
    readings = label_readings(text, first_pass_path == "units")
    task = FieldTask("precise_location", True, FieldValue(), (), FIELD_TOOLS["precise_location"])

    refused = agreement.literal_refusal(task, readings, literal=literal, named=readings)

    if first_pass_path == "units":
        assert refused is None
    else:
        assert refused is not None and refused.reason == agreement.HOLDS_AN_ELEVATION


@pytest.mark.parametrize("literal", ["Yepocapa, IV-24-48", "Yepocapa, 4800 ft. IV-24-48 to V-2-48"])
def test_a_precise_location_holding_a_date_is_still_refused_on_both_paths(first_pass_path, literal):
    """The rule names the higher places and an elevation, never a date: a date or a range of dates
    the precise location writes beside its locality (not as a number with an elevation unit) is
    refused on both paths."""
    readings = label_readings(literal + "\nChimaltenango, Guatemala", first_pass_path == "units")
    task = FieldTask("precise_location", True, FieldValue(), (), FIELD_TOOLS["precise_location"])

    refused = agreement.literal_refusal(task, readings, literal=literal, named=readings)

    assert refused is not None and refused.reason in (agreement.HOLDS_A_DATE, agreement.HOLDS_A_RANGE,
        agreement.HOLDS_AN_ELEVATION)
    if first_pass_path == "units":
        assert refused.reason != agreement.HOLDS_AN_ELEVATION


def whole(text):
    return answering(FieldAnswer(outcome="resolved", literal=text, reading_names=["1A", "1B"],
        explanation="Both readers write the locality."))


def settled_run(tmp_path, text, scripts):
    """The label `text` read alike by both readers, every field's expert scripted (`scripts`, else
    label_lacks_value), applied and finalized; the run and the step's decisions."""
    from test_step import Scripted

    rig = build_rig(tmp_path, text)
    run = rig.specimen.run
    prepared, outcomes, calls = research(rig, Scripted({**{key: answering(LACKS) for key in FIELDS}, **scripts}),
        tools=Gazetteer(rig.blobs))
    decisions: dict[str, dict] = {}
    field_step.apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls, decisions=decisions)
    field_step.finalize_fields(run, None, outcomes, specimen=rig.specimen, blobs=rig.blobs, today=TODAY)
    return rig, run, decisions


def test_105526329s_whole_locality_with_its_elevation_settles_on_the_units_path(tmp_path, first_pass_path):
    """The town-only locality with its elevation, the elevation settled from its own text: on the
    units path the precise location is the two lines as written; on the old path it goes to review
    as text the elevation field claims (step._taken), as on origin/main."""
    from test_step import resolved

    rig, run, decisions = settled_run(tmp_path, YEPOCAPA, {**IN_YEPOCAPA,
        "elevation_from_ft": answering(resolved("4800 ft.", value="4800")),
        "precise_location": whole(YEPOCAPA)})
    place = run.fields["precise_location"]
    assert run.fields["elevation_from_ft"].state == ValueState.SUPPORTED
    if first_pass_path == "units":
        assert (place.state, place.literal) == (ValueState.SUPPORTED, YEPOCAPA)
        assert "refusal" not in decisions.get("precise_location", {})
    else:
        assert (place.state, place.literal) == (ValueState.UNRESOLVED, None)
        assert place.reason == (field_step.TAKEN.format(other="Elevation From (ft)")
            + " Both readers write the locality.")


def test_105526321s_whole_locality_block_settles_as_written_on_both_paths(tmp_path, first_pass_path):
    """The whole block, its province and country lines included, read from the transcript: it
    settles as written on both paths (no check of either path cuts it)."""
    rig, run, _ = settled_run(tmp_path, MCKINLEY + "\n3 Sept. '46\nMossy forest 6400'\nF.G. Werner",
        {"precise_location": whole(MCKINLEY)})
    place = run.fields["precise_location"]
    assert (place.state, place.literal) == (ValueState.SUPPORTED, MCKINLEY)


def test_a_town_only_locality_is_not_cleared_as_not_on_the_label_on_the_units_path(tmp_path, first_pass_path):
    """105526329's town settled and the precise location's expert finding none (as main's brief
    asks for a town-only locality, precise_location.txt:12): on the old path rule A clears it as
    not on the label (mark_not_on_label's condition 7), as on origin/main; on the units path the
    label's locality is its precise location, so rule A declines it (precise_location_extent) and a
    person sees it."""
    rig, run, decisions = settled_run(tmp_path, YEPOCAPA, {**IN_YEPOCAPA})
    assert run.fields["city"].state == ValueState.SUPPORTED
    place = run.fields["precise_location"]
    assert place.state == ValueState.NOT_PRESENT
    if first_pass_path == "units":
        assert "precise_location" not in cleared_as_not_on_label(run)
        assert not not_on_label_rows(run, "precise_location")
        assert decisions["precise_location"]["rule"] == "A_declined:precise_location_extent"
        assert "mandatory_unresolved:precise_location" in run.reasons
    else:
        assert "precise_location" in cleared_as_not_on_label(run)
        assert decisions["precise_location"]["rule"] == "A_not_on_label"


def test_a_precise_location_that_is_the_towns_text_is_not_cleared_on_the_units_path(tmp_path, first_pass_path):
    """The expert answers the town alone, the settled city's text: on the old path it is no finer
    locality and clears as not on the label (step._repeats_a_place), as on origin/main; on the units
    path a town-only locality is still a precise location, so the value stands as settled."""
    rig, run, decisions = settled_run(tmp_path, YEPOCAPA, {**IN_YEPOCAPA, "precise_location": whole("Yepocapa")})
    place = run.fields["precise_location"]
    if first_pass_path == "units":
        assert (place.state, place.literal) == (ValueState.SUPPORTED, "Yepocapa")
        assert "precise_location" not in cleared_as_not_on_label(run)
    else:
        assert (place.state, place.literal) == (ValueState.NOT_PRESENT, None)
        assert decisions["precise_location"] == {"refusal": "place_text_only", "rule": "A_not_on_label"}
        assert "precise_location" in cleared_as_not_on_label(run)


def test_a_municipio_line_beside_the_settled_town_stands_on_the_units_path(tmp_path, first_pass_path):
    """105526328's locality (field_model_pilot_rows.json:268-289): the answer "Yepocapa, Mun." gives
    only a marker beside the settled town. On the old path it clears as not on the label
    (step._no_finer_place), as on origin/main; on the units path it stands as answered."""
    text = "Yepocapa, Mun.\nChimaltenango, Guatemala"
    rig, run, decisions = settled_run(tmp_path, text, {**IN_YEPOCAPA, "precise_location": whole("Yepocapa, Mun.")})
    place = run.fields["precise_location"]
    if first_pass_path == "units":
        assert (place.state, place.literal) == (ValueState.SUPPORTED, "Yepocapa, Mun.")
        assert "precise_location" not in cleared_as_not_on_label(run)
    else:
        assert (place.state, place.literal) == (ValueState.NOT_PRESENT, None)
        assert decisions["precise_location"]["refusal"] == "admin_marker_only"


# ---- round 1 of PR #435's review (Codex, finding 1): an elevation alone is no locality ----------------

@pytest.mark.parametrize("literal", ["4800 ft.", "Elev. 6400'"])
def test_an_elevation_alone_is_still_refused_as_a_precise_location_on_both_paths(first_pass_path, literal):
    """The units path's exception takes an elevation written among a locality's lines, never a literal
    that is only an elevation (and the words beside it): it is refused as on the old path."""
    readings = label_readings(literal + "\nIV-24-48", first_pass_path == "units")
    task = FieldTask("precise_location", True, FieldValue(), (), FIELD_TOOLS["precise_location"])

    refused = agreement.literal_refusal(task, readings, literal=literal, named=readings)

    assert refused is not None and refused.reason == agreement.HOLDS_AN_ELEVATION
    assert not agreement.locality_beyond_elevations(literal)
    assert agreement.locality_beyond_elevations("Yepocapa, " + literal)


def test_a_label_writing_only_an_elevation_gets_no_precise_location_on_either_path(tmp_path, first_pass_path):
    """Codex's input: a label that writes only "4800 ft.", read alike by both readers, and the precise
    location's expert resolving "4800 ft." from the transcript: refused on both paths, never stored."""
    rig, run, decisions = settled_run(tmp_path, "4800 ft.", {"precise_location": whole("4800 ft.")})
    place = run.fields["precise_location"]
    assert place.state != ValueState.SUPPORTED and place.literal is None
    assert place.reason.startswith(agreement.HOLDS_AN_ELEVATION)


def test_an_elevation_read_from_the_transcript_beside_an_elevation_only_precise_location_goes_to_review(
        tmp_path, first_pass_path):
    """The organiser offers "4800 ft." as the precise location, which its expert settles on that candidate,
    and the foot elevation's expert reads "4800 ft." from the transcript: the precise location's literal holds
    no locality text, so on the units path too the elevation is text another kind of field claims
    (step._taken), as on the old path."""
    from test_step import Scripted

    rig = build_rig(tmp_path, "4800 ft.\nIV-24-48", candidates=[
        ("precise_location", name, "4800 ft.", "4800 ft.") for name in ("1A", "1B")])
    run = rig.specimen.run
    prepared, outcomes, calls = research(rig, Scripted({**{key: answering(LACKS) for key in FIELDS},
        "precise_location": whole("4800 ft."),
        "elevation_from_ft": answering(FieldAnswer(outcome="resolved", literal="4800 ft.", value="4800",
            reading_names=["1A", "1B"], explanation="Both readers write it."))}), tools=Gazetteer(rig.blobs))
    decisions: dict[str, dict] = {}
    field_step.apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls, decisions=decisions)
    assert run.fields["elevation_from_ft"].state == ValueState.UNRESOLVED
    assert decisions["elevation_from_ft"]["refusal"] == "taken"


# ---- round 1 of PR #435's review (G51, B1 and B3) ---------------------------------------------------

@pytest.mark.parametrize("literal", ["Yepocapa, May 1948 M. Smith\nChimaltenango, Guatemala", "Yepocapa, 1948 M. Smith"])
def test_a_doubtful_elevation_is_never_passed_over_so_a_date_and_a_collector_stay_out(first_pass_path, literal):
    """G51's B1: "1948 M." before a name may be a year and a person's initial (written.Number.sign), not an
    elevation the reading writes with a unit. Only a definite elevation is passed over on the units path, so
    this literal is refused on both paths, as on main."""
    readings = label_readings(literal if "\n" in literal else literal + "\nChimaltenango, Guatemala",
        first_pass_path == "units")
    task = FieldTask("precise_location", True, FieldValue(), (), FIELD_TOOLS["precise_location"])

    refused = agreement.literal_refusal(task, readings, literal=literal, named=readings)

    assert refused is not None and refused.reason == agreement.HOLDS_AN_ELEVATION


def test_a_label_writing_a_year_and_a_collector_on_its_locality_line_gets_no_precise_location(tmp_path,
        first_pass_path):
    """G51's B1 input end to end: "Yepocapa, May 1948 M. Smith" over "Chimaltenango, Guatemala", the precise
    location's expert answering both lines from the transcript: never stored, on either path."""
    text = "Yepocapa, May 1948 M. Smith\nChimaltenango, Guatemala"
    rig, run, decisions = settled_run(tmp_path, text, {**IN_YEPOCAPA, "precise_location": whole(text)})
    place = run.fields["precise_location"]
    assert place.state != ValueState.SUPPORTED and place.literal is None
    assert decisions["precise_location"]["refusal"] == "holds_an_elevation"


@pytest.mark.parametrize("key", ["collection_code", "city"])
def test_only_the_precise_location_passes_over_an_elevation(first_pass_path, key):
    """G51's B3 (c): the units path's pass-over is the precise location's alone; a collection code or a city
    read from the transcript as "Yepocapa, 4800 ft." is refused for its elevation on both paths."""
    readings = label_readings(YEPOCAPA, first_pass_path == "units")
    task = FieldTask(key, True, FieldValue(), (), FIELD_TOOLS[key])

    refused = agreement.literal_refusal(task, readings, literal="Yepocapa, 4800 ft.", named=readings)

    assert refused is not None and refused.reason == agreement.HOLDS_AN_ELEVATION


def test_an_elevation_spelled_alike_by_another_reader_is_taken_on_the_old_path(tmp_path, first_pass_path):
    """G51's B3 (a): 1A writes "4800 ft.", 1B "4800 Ft."; the elevation settles on 1A's, and the precise
    location's expert answers 1B's "4800 Ft." from the transcript. step._taken's spelled-alike check finds the
    elevation's text: the precise location goes to review as text another kind of field claims ("taken"), on
    the old path and, as its literal holds no locality text, on the units path too."""
    from test_step import Scripted, resolved

    rig = build_rig(tmp_path, YEPOCAPA, YEPOCAPA.replace("4800 ft.", "4800 Ft."))
    run = rig.specimen.run
    prepared, outcomes, calls = research(rig, Scripted({**{key: answering(LACKS) for key in FIELDS}, **IN_YEPOCAPA,
        "elevation_from_ft": answering(resolved("4800 ft.", value="4800", reading="1A")),
        "precise_location": answering(FieldAnswer(outcome="resolved", literal="4800 Ft.", reading_names=["1B"],
            explanation="Read."))}), tools=Gazetteer(rig.blobs))
    decisions: dict[str, dict] = {}
    field_step.apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls, decisions=decisions)
    place = run.fields["precise_location"]
    assert place.state != ValueState.SUPPORTED
    assert decisions["precise_location"] == {"refusal": "taken"}
    assert place.reason.startswith(field_step.TAKEN.format(other="Elevation From (ft)"))


def test_a_units_path_run_cleared_as_not_on_the_label_by_older_code_goes_to_a_person_on_refinalize(tmp_path,
        first_pass_path):
    """G51's B3 (b): a stored precise location that the code before WP 2.2 cleared as not on the label (rule A,
    its check row stored), refinalized: on the units path step.not_on_label no longer clears it, so the record
    waits for a person; on the old path it stays cleared."""
    from specimen_digitization.field_research.contracts import FieldOutcome

    rig, run, decisions = settled_run(tmp_path, YEPOCAPA, {**IN_YEPOCAPA})
    readings = field_step.run_readings(run)
    tasks = [FieldTask("precise_location", True, run.fields["precise_location"], (), FIELD_TOOLS["precise_location"])]
    path = run.first_pass_path
    # The code before WP 2.2 marked it on either path (mark_not_on_label's condition 7 without the units gate).
    run.first_pass_path = "old"
    marked = field_step.mark_not_on_label(run, field_step.profile_of(run), tasks,
        [FieldOutcome("precise_location", LACKS, model_calls=1)], readings=readings, blobs=rig.blobs)
    run.first_pass_path = path
    assert "precise_location" in marked and not_on_label_rows(run, "precise_location")

    field_step.finalize_fields(run, None, [], specimen=rig.specimen, blobs=rig.blobs, today=TODAY)

    if first_pass_path == "units":
        assert "precise_location" not in cleared_as_not_on_label(run)
        assert "mandatory_unresolved:precise_location" in run.reasons
    else:
        assert "precise_location" in cleared_as_not_on_label(run)
        assert "mandatory_unresolved:precise_location" not in run.reasons
