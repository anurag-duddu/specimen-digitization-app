"""WP 2.2: Precise Location is the label's locality as written (the ontology's rule
precise_location_extent), on the units path.

The cases are the pilot labels the plan names, from tests/fixtures/field_model_pilot_rows.json:
105526329's town-only locality, "Yepocapa, 4800 ft." over "Chimaltenango, Guatemala" (its truth
row's precise location is the locality's lines as written, :325), 105526321's whole locality
block, "E. slope Mt. McKinley" over "Davao Prov." over "Mindanao, P.I." (:30), and 105526328's
municipio line (:268-289). A precise location that holds an elevation is refused on both paths when no
elevation field settled its elevation text from the label; WP 2.3b's acceptance on the units path
(the coordinator's ruling of 2026-11-14) is tested in test_elevations_and_extent.py, and changes
here only test_105526329s_whole_locality_with_its_settled_elevation_settles_on_the_units_path.
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
def test_a_precise_location_holding_an_elevation_is_refused_when_no_elevation_settled(literal):
    """agreement.literal_refusal on the precise location read from the transcript, with no elevation field's
    literal given: a locality that writes an elevation among its lines is refused for it (HOLDS_AN_ELEVATION)
   , as on origin/main, so a person decides. WP 2.3b accepts it on the units path only when the
    elevation field settled its elevation text from that label (test_elevations_and_extent.py)."""
    text = YEPOCAPA if literal.startswith("Yepocapa") else MCKINLEY_3300
    readings = label_readings(text, True)
    task = FieldTask("precise_location", True, FieldValue(), (), FIELD_TOOLS["precise_location"])

    refused = agreement.literal_refusal(task, readings, literal=literal, named=readings)

    assert refused is not None and refused.reason == agreement.HOLDS_AN_ELEVATION


# The inputs PR #435's review rounds 1 and 2 (Codex and G51) found an elevation pass-over admitting: a date and
# a collector, an elevation with no locality, a spelled-out sea-level phrase. The coordinator's ruling of
# 2026-11-14 took the pass-over out of WP 2.2; WP 2.3's row names these cases.
ELEVATION_REVIEW_CASES = [
    "4800 ft.", "Elev. 6400'", "4800 ft. above sea level", "1200 m above sea level", "1200 m sobre el nivel del mar",
    "1500 m de altitud", "Yepocapa, 1948 M. Smith", "Yepocapa, May 1948 M. A. Smith", "Yepocapa, 1948 M. O'Brien",
    "Yepocapa, 1948 M. Smith-Jones", "Yepocapa, Sept. 46'",
]


@pytest.mark.parametrize("literal", ELEVATION_REVIEW_CASES)
def test_the_review_rounds_elevation_inputs_are_refused_as_a_precise_location_on_both_paths(literal):
    """Each is refused for an elevation it holds (agreement._holds_another_kind), as on
    origin/main, so no date, collector or elevation-only text settles as the precise location. WP 2.3b's rule
    accepts none of them, whatever elevation settled
    (test_elevations_and_extent.test_the_review_rounds_elevation_inputs_stay_refused_whatever_elevation_settled)."""
    readings = label_readings(literal + "\nChimaltenango, Guatemala", True)
    task = FieldTask("precise_location", True, FieldValue(), (), FIELD_TOOLS["precise_location"])

    refused = agreement.literal_refusal(task, readings, literal=literal, named=readings)

    assert refused is not None and refused.reason == agreement.HOLDS_AN_ELEVATION


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


def test_105526329s_whole_locality_with_its_settled_elevation_settles_on_the_units_path(tmp_path):
    """WP 2.3b changes the units path: the elevation text is the literal the elevation field
    settled from that label, so the whole locality settles as written (the ontology's rule
    precise_location_extent)."""
    from test_step import resolved

    rig, run, decisions = settled_run(tmp_path, YEPOCAPA, {**IN_YEPOCAPA,
        "elevation_from_ft": answering(resolved("4800 ft.", value="4800")),
        "precise_location": whole(YEPOCAPA)})
    place = run.fields["precise_location"]
    assert run.fields["elevation_from_ft"].state == ValueState.SUPPORTED
    assert (place.state, place.literal) == (ValueState.SUPPORTED, YEPOCAPA)


def test_105526321s_whole_locality_block_settles_as_written_on_both_paths(tmp_path):
    """The whole block, its province and country lines included, read from the transcript: it
    settles as written on both paths (no check of either path cuts it)."""
    rig, run, _ = settled_run(tmp_path, MCKINLEY + "\n3 Sept. '46\nMossy forest 6400'\nF.G. Werner",
        {"precise_location": whole(MCKINLEY)})
    place = run.fields["precise_location"]
    assert (place.state, place.literal) == (ValueState.SUPPORTED, MCKINLEY)


def test_a_town_only_locality_is_not_cleared_as_not_on_the_label_on_the_units_path(tmp_path):
    """on the units path the
    label's locality is its precise location, so rule A declines it (precise_location_extent) and a
    person sees it."""
    rig, run, decisions = settled_run(tmp_path, YEPOCAPA, {**IN_YEPOCAPA})
    assert run.fields["city"].state == ValueState.SUPPORTED
    place = run.fields["precise_location"]
    assert place.state == ValueState.NOT_PRESENT
    assert "precise_location" not in cleared_as_not_on_label(run)
    assert not not_on_label_rows(run, "precise_location")
    assert decisions["precise_location"]["rule"] == "A_declined:precise_location_extent"
    assert "mandatory_unresolved:precise_location" in run.reasons


def test_a_precise_location_that_is_the_towns_text_is_not_cleared_on_the_units_path(tmp_path):
    """on the units
    path a town-only locality is still a precise location, so the value stands as settled."""
    rig, run, decisions = settled_run(tmp_path, YEPOCAPA, {**IN_YEPOCAPA, "precise_location": whole("Yepocapa")})
    place = run.fields["precise_location"]
    assert (place.state, place.literal) == (ValueState.SUPPORTED, "Yepocapa")
    assert "precise_location" not in cleared_as_not_on_label(run)


def test_a_municipio_line_beside_the_settled_town_stands_on_the_units_path(tmp_path):
    """105526328's locality (field_model_pilot_rows.json:268-289): the answer "Yepocapa, Mun." gives
    only a marker beside the settled town. on the units path it stands as answered."""
    text = "Yepocapa, Mun.\nChimaltenango, Guatemala"
    rig, run, decisions = settled_run(tmp_path, text, {**IN_YEPOCAPA, "precise_location": whole("Yepocapa, Mun.")})
    place = run.fields["precise_location"]
    assert (place.state, place.literal) == (ValueState.SUPPORTED, "Yepocapa, Mun.")
    assert "precise_location" not in cleared_as_not_on_label(run)


# ---- PR #435's review, round 1 (G51, B3 (b)): the units gate of step.not_on_label -------------------

def older_codes_not_on_label_row(run, key, readings, blobs):
    """The check row the code before WP 2.2 stored for a field it cleared as not on the label
    (origin/main d83f4d6f1's step.mark_not_on_label: kind "derived", locator "check:not_on_label", the
    readings' excerpt, its record in the blobs), cited by the field as support."""
    import hashlib
    import json

    from specimen_digitization.application.domain import Evidence

    record = json.dumps({"field_key": key, "check": "not_on_label", "readings": [
        {"name": r.name, "region_id": r.region_id, "observation_id": r.observation_id,
         "input_source": r.input_source} for r in readings]}, sort_keys=True).encode()
    row = Evidence(kind="derived", asset_id=None, source=field_step.SOURCE, locator=field_step.NOT_ON_LABEL_CHECK,
        excerpt=field_step.not_on_label_excerpt(key, readings), raw_ref=blobs.put(record),
        digest=hashlib.sha256(record).hexdigest())
    run.evidence.append(row)
    value = run.fields[key]
    value.evidence_ids.append(row.id)
    value.evidence_relations[row.id] = "supports"


@pytest.mark.parametrize(("path", "cleared"), [("units", False), ("old", True)])
def test_a_precise_location_older_code_cleared_as_not_on_the_label_is_refinalized_by_its_runs_path(
        tmp_path, path, cleared):
    """G51's B3 (b): a stored precise location that the code before WP 2.2 cleared as not on the label
    (rule A, its check row stored), refinalized. On a units-path run step.not_on_label no longer clears
    it, so the record waits for a person. A record the old first pass wrote (its run's path "old", the
    default of a run stored without the key) keeps the rule it was cleared by, while a city or a county
    is settled: it stays cleared. mark_not_on_label never marks a precise location now
    ("precise_location_extent")."""
    from specimen_digitization.field_research.contracts import FieldOutcome

    rig, run, decisions = settled_run(tmp_path, YEPOCAPA, {**IN_YEPOCAPA})
    readings = field_step.run_readings(run)
    tasks = [FieldTask("precise_location", True, run.fields["precise_location"], (), FIELD_TOOLS["precise_location"])]
    why: dict[str, str] = {}
    assert field_step.mark_not_on_label(run, field_step.profile_of(run), tasks,
        [FieldOutcome("precise_location", LACKS, model_calls=1)], readings=readings, blobs=rig.blobs, why=why) == []
    assert why == {"precise_location": "precise_location_extent"}
    older_codes_not_on_label_row(run, "precise_location", readings, rig.blobs)
    assert not_on_label_rows(run, "precise_location")
    if path == "old":
        # As the old first pass stored a label its readers read alike: no first pass ran, so no
        # decision, no call and no reading units (origin/main's first_pass.adjudication_record).
        run.first_pass_decisions = []
        run.reading_units = []
        for transcript in run.transcripts:
            transcript.first_pass_call = None
        run.first_pass_path = path

    field_step.finalize_fields(run, None, [], specimen=rig.specimen, blobs=rig.blobs, today=TODAY)

    assert ("precise_location" in cleared_as_not_on_label(run)) == cleared
    assert ("mandatory_unresolved:precise_location" in run.reasons) != cleared
