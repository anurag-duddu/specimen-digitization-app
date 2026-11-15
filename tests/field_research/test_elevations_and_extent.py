"""WP 2.3b of docs/execution/units/PLAN.md: the elevation unit rule (elevation_unit_feet), the
fields derived from a held source, an elevation inside a precise location, a precise location
cut short (precise_location_extent), the country-only locality and derive.py's rules from the
ontology file (docs/product-requirements/FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md section 4,
"The check stage"; field_research/ontology_checks.py).

Every test runs on both first-pass paths (conftest.py). On the units path the change applies; on
the old path, live in production until WP 1.8, each test asserts origin/main's result, so a gate
that leaks fails here."""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal

import pytest
from pydantic_ai import ModelRetry
from test_precise_location_extent import ELEVATION_REVIEW_CASES, MCKINLEY, YEPOCAPA, label_readings, whole
from test_step import (
    ABBREVIATED_COUNTRY,
    COLLECTORS,
    DavaoProvince,
    IN_GUATEMALA,
    IN_YEPOCAPA,
    LABEL,
    TEXT,
    TODAY,
    Gazetteer,
    Scripted,
    answering,
    build_rig,
    field_checks,
    from_tgn,
    label_with,
    research,
    resolved,
    settle,
)

from specimen_digitization import ontology
from specimen_digitization.application.domain import FieldValue, RunFinding, ValueState
from specimen_digitization.field_research import agreement, derive, experts, ontology_checks
from specimen_digitization.field_research import step as field_step
from specimen_digitization.field_research.contracts import FIELD_TOOLS, FieldAnswer, FieldTask

LACKS = FieldAnswer(outcome="label_lacks_value", explanation="Not on the label.")
CANNOT = FieldAnswer(outcome="sources_cannot_resolve", explanation="No unit is written with this number.")
ELEVATIONS = ("elevation_from_m", "elevation_to_m", "elevation_from_ft", "elevation_to_ft")
PARTNERS = ("elevation_from_m", "elevation_to_m", "elevation_to_ft")
# The Philippines, settled on Getty TGN's nation (test_step's Gazetteer).
PHILIPPINES = {"country": from_tgn("Philippines", "Philippines", None, "tgn:1000135")}
NO_PLACES_BELOW = dict.fromkeys(("province_state", "county", "city"), answering(LACKS))
STAGE = "check_stage"


def elevation_label(written, other=None):
    """test_step's label with the Philippines as its country, no place below it, and the elevation line
    `written` (reader 1A) and `other` (reader 1B; `written` when None)."""
    places = dict(country="Philippines", province_state=None, county=None, city=None)
    return (label_with(**places, elevation_from_ft=written),
        None if other is None else label_with(**places, elevation_from_ft=other))


def settled_elevations(tmp_path, written, other=None, **scripts):
    """The elevation label read by both readers, the country's expert settling the Philippines, the foot
    field's expert unable to resolve the number, every other elevation field's answering that the label
    lacks it; researched, applied and finalized."""
    text, second = elevation_label(written, other)
    rig = build_rig(tmp_path, text, second)
    settle(rig, Scripted({**PHILIPPINES, **NO_PLACES_BELOW, "elevation_from_ft": answering(CANNOT),
        **dict.fromkeys(PARTNERS, answering(LACKS)), **scripts}), tools=Gazetteer(rig.blobs))
    return rig, rig.specimen.run


def state_of(run, key):
    value = run.fields[key]
    return value.state, value.literal, value.parsed, value.layer


# ---- 1. the elevation unit rule (elevation_unit_feet) ------------------------------------------

def test_6400_with_b_s_foot_mark_and_the_philippines_cleared_settles_6400_ft_cleared(tmp_path, first_pass_path):
    """The plan's case, 105526322's shape: reader A writes "Elev.6400", reader B "Elev.6400'", the
    Philippines cleared. 6400 m is above Mount Apo (2,954 m) and 6,400 ft (1,950.72 m) is not: on the units
    path the foot field settles 6400, cleared, its reason naming the rule, and derivation fills its
    partners, each naming its rule. On the old path the field stays unresolved and its partners settle
    absent, as on origin/main."""
    rig, run = settled_elevations(tmp_path, "Elev.6400", "Elev.6400'")

    assert state_of(run, "country")[:2] == (ValueState.SUPPORTED, "Philippines")
    if first_pass_path == "units":
        value = run.fields["elevation_from_ft"]
        assert state_of(run, "elevation_from_ft") == (ValueState.SUPPORTED, "6400", "6400", "settled")
        assert ontology_checks.cleared_country(run) is run.fields["country"]
        assert value.reason.startswith("Basis: inferred, rule elevation_unit_feet: reader 1B writes 6400 with the "
            "foot mark or ft at unit ")
        assert "6400 m is above the highest point of Philippines, Mount Apo, 2954 m" in value.reason
        assert "6400 ft (1950.7200 m) is not" in value.reason
        assert not any(code.startswith("marked:elevation") for code in field_step.marked_reasons(run))
        derived = {key: run.fields[key] for key in PARTNERS}
        assert {key: (value.state, value.parsed, value.layer) for key, value in derived.items()} == {
            "elevation_from_m": (ValueState.SUPPORTED, "1950.72", "derived"),
            "elevation_to_m": (ValueState.SUPPORTED, "1950.72", "derived"),
            "elevation_to_ft": (ValueState.SUPPORTED, "6400", "derived")}
        assert all(value.reason.endswith("Basis: derived, rule elevation_conversion.") for value in derived.values())
        rows = {item.id: item for item in run.evidence}
        [inferred] = [rows[i] for i in value.evidence_ids if rows[i].locator == ontology_checks.INFERRED]
        assert inferred.kind == "derived" and inferred.excerpt.startswith(
            "elevation_from_ft = 6400: inferred as feet (rule elevation_unit_feet): reader 1B")
        assert json.loads(rig.blobs.get(inferred.raw_ref))["highest_point"] == {
            "country": "Q928", "point": "Q455963", "elevation_m": "2954"}
        assert field_checks(run, ["elevation_from_ft"]) == []
    else:
        assert state_of(run, "elevation_from_ft")[0] == ValueState.UNRESOLVED
        assert [run.fields[key].state for key in PARTNERS] == [ValueState.NOT_PRESENT] * 3


def mark_the_country(monkeypatch):
    """Each label that settles the country settles it marked: the settlement's cleared finding for the
    country becomes the marked one a conflict gives (step.marked_code)."""
    settlement = field_step._settlement

    def marked(run, task, outcome, **kwargs):
        settlement(run, task, outcome, **kwargs)
        for finding in run.findings:
            if finding.field_key == "country" and finding.reason_code.startswith("cleared:country:"):
                finding.reason_code = field_step.marked_code("country", finding.reason_code.split(":")[2], "conflict")
                finding.severity = "warning"

    monkeypatch.setattr(field_step, "_settlement", marked)


def test_the_same_with_the_philippines_marked_stays_unresolved(tmp_path, monkeypatch, first_pass_path):
    """The plan's case: the country must be cleared, not marked. With the Philippines settled marked, the
    foot field stays unresolved on both paths."""
    mark_the_country(monkeypatch)
    rig, run = settled_elevations(tmp_path, "Elev.6400", "Elev.6400'")

    assert state_of(run, "country")[0] == ValueState.SUPPORTED
    assert state_of(run, "elevation_from_ft")[0] == ValueState.UNRESOLVED
    assert ontology_checks.cleared_country(run) is None


def test_a_country_not_settled_from_the_label_or_with_no_cleared_label_is_not_cleared(tmp_path, first_pass_path):
    """cleared_country: the country settled from the label with a label's cleared finding; a derived
    country, or one whose cleared finding is missing, is not cleared, and nor is a check stage's marked
    country."""
    rig, run = settled_elevations(tmp_path, "Elev.6400", "Elev.6400'")
    country = run.fields["country"]
    if first_pass_path == "old":
        assert ontology_checks.cleared_country(run) is None  # the old path records no settlement
        return
    assert ontology_checks.cleared_country(run) is country
    run.fields["country"] = country.model_copy(update={"layer": "derived"})
    assert ontology_checks.cleared_country(run) is None
    run.fields["country"] = country
    findings = list(run.findings)
    run.findings[:] = [f for f in findings if not f.reason_code.startswith("cleared:country:")]
    assert ontology_checks.cleared_country(run) is None
    run.findings[:] = [*findings, RunFinding(rule_id=STAGE, rule_version="v", severity="warning",
        field_key="country", reason_code="marked:country:r1:place_parents_derived")]
    assert ontology_checks.cleared_country(run) is None


@pytest.mark.parametrize(("written", "other"), [("Elev.6400", "Elev.6400"), ("Elev.6400", "Elev.6400 feet")],
    ids=["no-mark", "feet-spelled-out"])
def test_6400_with_no_foot_mark_stays_unresolved(tmp_path, first_pass_path, written, other):
    """The plan's case: without (a), a reader's foot mark or "ft" at the unit, the field is unresolved on
    both paths: magnitude alone never decides. Condition (a) counts the mark and "ft" only."""
    rig, run = settled_elevations(tmp_path, written, other)

    assert state_of(run, "elevation_from_ft")[0] == ValueState.UNRESOLVED


@pytest.mark.parametrize(("number", "inferred"), [
    ("16000", False),  # the plan's case: 16,000 ft is 4,876.8 m, above Mount Apo: (c) fails
    ("9692", False),   # 2,954.12 m: (c) fails by 0.12 m
    ("9691", True),    # 2,953.82 m: (c) holds
    ("2955", True),    # one metre above Mount Apo: (b) holds
    ("2954", False),   # Mount Apo's height itself: (b) needs the number above it
    ("2000", False),   # possible in metres: (b) fails
])
def test_conditions_b_and_c_bound_the_number(tmp_path, first_pass_path, number, inferred):
    """(b) the number read as metres is above the Philippines' highest point, Mount Apo, 2,954 m; (c) the
    number read as feet is not above it. Only on the units path, and only when both hold, the number
    settles in feet."""
    rig, run = settled_elevations(tmp_path, f"Elev.{number}", f"Elev.{number}'")

    found = state_of(run, "elevation_from_ft")
    if inferred and first_pass_path == "units":
        assert found == (ValueState.SUPPORTED, number, number, "settled")
        assert run.fields["elevation_from_m"].parsed == str(
            (Decimal(number) * Decimal("0.3048")).quantize(Decimal("0.01")))
    else:
        assert found[0] == ValueState.UNRESOLVED


@pytest.mark.parametrize(("written", "other"), [("Elev. 6400", "Elev. 6400 m"), ("Elev. 6400'", "Elev. 6400 m")],
    ids=["bare-and-metres", "mark-and-metres"])
def test_a_reader_who_writes_metres_keeps_today_s_unit_differs_path(tmp_path, first_pass_path, written, other):
    """The plan's case: a reader wrote "m". The foot field's answer of the number is refused as today
    (UNIT_DIFFERS) on both paths, and nothing is inferred."""
    rig, run = settled_elevations(tmp_path, written, other,
        elevation_from_ft=answering(resolved("6400", reading="1B")))

    value = run.fields["elevation_from_ft"]
    assert (value.state, value.reason.split(" Settled.")[0]) == (ValueState.UNRESOLVED, agreement.UNIT_DIFFERS)


def test_a_country_s_row_is_its_wikidata_item_s_else_its_name_s(tmp_path, first_pass_path):
    """highest_point: the table's row by the country's Wikidata item, else by its name (normalized, else
    parsed, else its literal); a country with neither has no row."""
    rig, run = settled_elevations(tmp_path, "Elev.6400", "Elev.6400'")
    country = run.fields["country"]
    assert ontology_checks.highest_point(country).point_name == "Mount Apo"
    assert ontology_checks.highest_point(country.model_copy(update={"authority_id": "wikidata:Q774"})).point == \
        "Q818467"
    assert ontology_checks.highest_point(country.model_copy(update={"authority_id": "wikidata:Q1"})) is None
    assert ontology_checks.highest_point(country.model_copy(update={"normalized": "Atlantis"})) is None
    assert ontology_checks.highest_point(country.model_copy(update={"normalized": "philippines"})).country == "Q928"
    assert ontology_checks.highest_point(country.model_copy(update={"parsed": None, "literal": "Atlantis"})) is None


def test_a_number_on_two_units_or_another_held_elevation_is_not_inferred(tmp_path, first_pass_path):
    """foot_number needs exactly one unit of the run's labels so written; infer_feet needs every other
    elevation field open. Each, broken on the 105526322 shape, leaves the field held."""
    rig, run = settled_elevations(tmp_path, "Elev.6400", "Elev.6400'")
    readings = field_step.run_readings(run)
    if first_pass_path == "old":
        assert ontology_checks.foot_number(run, readings, None) is None  # the old path stores no units
        return
    found = ontology_checks.foot_number(run, readings, None)
    assert found is not None and found.number == "6400" and len(found.marked) == 1
    assert ontology_checks.foot_number(run, readings, "6401") is None
    label = run.reading_units[0]
    twice = label.model_copy(update={"units": [*label.units, found.unit.model_copy(update={"id": "x"})]})
    run.reading_units = [twice]
    assert ontology_checks.foot_number(run, readings, None) is None
    run.reading_units = [label]
    held = FieldValue(state=ValueState.UNRESOLVED, literal="6400")
    run.fields.update({"elevation_from_ft": held, "elevation_from_m": FieldValue(), "elevation_to_m": FieldValue(),
        "elevation_to_ft": FieldValue(state=ValueState.UNRESOLVED, literal="6400")})
    assert ontology_checks.infer_feet(run, readings=readings, eligible=ELEVATIONS) == []
    run.fields["elevation_to_ft"] = FieldValue()
    assert ontology_checks.infer_feet(run, readings=readings, eligible=ELEVATIONS) == ["elevation_from_ft"]
    run.fields["elevation_from_ft"] = held
    assert ontology_checks.infer_feet(run, readings=readings, eligible=PARTNERS) == []
    run.fields["elevation_from_ft"] = FieldValue(state=ValueState.UNRESOLVED, literal="6400 ft")
    assert ontology_checks.infer_feet(run, readings=readings, eligible=ELEVATIONS) == []


def one_unit(*texts):
    """A run whose one label "r1" has one unit, each reader's text at it the whole of that reader's
    reading, and the readings."""
    from types import SimpleNamespace

    from specimen_digitization.application.reading_units import ReadingUnit, ReadingUnits, UnitText
    from specimen_digitization.field_research.contracts import Reading

    readings = tuple(Reading(f"1{chr(65 + i)}", "r1", f"o{i}", "raw_reading", text) for i, text in enumerate(texts))
    unit = ReadingUnit(id="r1:1", label="r1", lines=(1, 1), image="uncertain",
        readers={reading.observation_id: UnitText(text=reading.text, start=0, end=len(reading.text))
            for reading in readings})
    return SimpleNamespace(reading_units=[ReadingUnits(label="r1", units=[unit])]), readings


@pytest.mark.parametrize(("texts", "marked"), [
    (("Elev.6400", "Elev.6400'"), ["o1"]),
    (("Elev.6400", "Elev.6400 ft."), ["o1"]),
    (("Elev.6400", "Elev.6400\N{RIGHT SINGLE QUOTATION MARK}"), ["o1"]),
    (("Elev.6400", "Elev.6400'", "Elev 6400'"), ["o1", "o2"]),
    (("Elev.6400", "Elev 6400"), None),                        # no reader's mark
    (("Elev.6400", "Elev.6400 feet"), None),                   # a foot, but neither the mark nor "ft"
    (("Elev.6400'", "Elev 6400'"), None),                      # every reader writes the unit
    (("Elev.6400", "Elev.6400'", "Elev.6400 m"), None),        # a reader writes metres
    (("Elev.6400", "Elev.6400'", "Elev.6401'"), None),         # two numbers
    (("6-Sept-1946, Elev.6400", "6-Sept-1946, Elev.6400'"), None),  # more than one number at the unit
    (("Elev.6400", ""), None),                                 # a reader writes nothing there
    (("500 m N of Elev.6400", "500 m N of Elev.6400'"), None),  # more than one number, one a distance
])
def test_condition_a_is_one_number_a_reader_marks_and_another_leaves_bare(first_pass_path, texts, marked):
    """foot_number, condition (a): every reader of the unit writes one number, the same, at least one with
    the foot mark (straight, curly or a prime) or "ft" right after it, at least one with no unit, and none
    with another unit or as a distance."""
    run, readings = one_unit(*texts)

    found = ontology_checks.foot_number(run, readings, None)

    assert (None if found is None else [obs for obs, _, _ in found.marked]) == marked
    if found is not None:
        assert found.number == "6400" and ontology_checks.foot_number(run, readings, "6400") == found
        assert ontology_checks.foot_number(run, readings, "6400 ft") is None


# ---- 2. dependent fields wait for their source ---------------------------------------------------

def test_an_elevation_s_partners_wait_while_it_is_held(tmp_path, first_pass_path):
    """105526324's shape: the foot field held (readers write "3300," and "3300'" and its expert gives two
    possibilities) in Guatemala, where 3300 m is below Tajumulco and nothing is inferred. On the units path
    its partners wait, unknown, their reason naming it, never settled absent; on the old path they settle
    absent, as on origin/main."""
    places = dict(country="Guatemala", province_state=None, county=None, city=None)
    rig = build_rig(tmp_path, label_with(**places, elevation_from_ft="3300,"),
        label_with(**places, elevation_from_ft="3300'"))
    run = rig.specimen.run
    settle(rig, Scripted({**IN_GUATEMALA, "province_state": answering(LACKS),
        "elevation_from_ft": answering(FieldAnswer(outcome="several_possibilities", options=["3300", "3300'"],
            explanation="The readers differ on the mark.")),
        **dict.fromkeys(PARTNERS, answering(LACKS))}), tools=Gazetteer(rig.blobs))

    assert state_of(run, "elevation_from_ft")[0] in (ValueState.AMBIGUOUS, ValueState.UNRESOLVED)
    if first_pass_path == "units":
        for key in PARTNERS:
            value = run.fields[key]
            assert value.state == ValueState.UNKNOWN, key
            assert value.reason.startswith("Waits for Elevation From (ft), which is not settled: this field is "
                "derived from it once it settles (rule elevation_conversion), and is not settled absent before. ")
    else:
        assert [run.fields[key].state for key in PARTNERS] == [ValueState.NOT_PRESENT] * 3


def test_6400_with_no_mark_leaves_its_partners_waiting(tmp_path, first_pass_path):
    """The no-mark case's partners: on the units path they wait for the foot field; on the old path they
    settle absent."""
    rig, run = settled_elevations(tmp_path, "Elev.6400", "Elev.6400")

    states = [run.fields[key].state for key in PARTNERS]
    assert states == ([ValueState.UNKNOWN] * 3 if first_pass_path == "units" else [ValueState.NOT_PRESENT] * 3)


def test_105526325_s_held_date_leaves_date_visited_to_waiting(tmp_path, first_pass_path):
    """105526325's "1X-14-46": Date Visited From held (its expert cannot resolve it), Date Visited To's expert
    answering that the label lacks it. On the units path Date Visited To waits, its reason naming Date
    Visited From; on the old path it settles absent, as on origin/main."""
    rig = build_rig(tmp_path, label_with(date_visited_from="1X-14-46"))
    run = rig.specimen.run
    settle(rig, Scripted({"date_visited_from": answering(CANNOT), "date_visited_to": answering(LACKS)}))

    assert run.fields["date_visited_from"].state == ValueState.UNRESOLVED
    value = run.fields["date_visited_to"]
    if first_pass_path == "units":
        assert value.state == ValueState.UNKNOWN and not value.literal
        assert value.reason.startswith("Waits for Date Visited From, which is not settled: this field is derived "
            "from it once it settles (rule end_date_from_one_date)")
    else:
        assert value.state == ValueState.NOT_PRESENT


def test_a_waiting_end_date_is_derived_once_its_start_settles(tmp_path, first_pass_path):
    """Two attempts: the first leaves Date Visited From held, so Date Visited To waits (units path) or
    settles absent (old path); the second settles the start, and derivation fills the end as today, on
    both paths."""
    rig = build_rig(tmp_path)
    run = rig.specimen.run
    settle(rig, Scripted({"date_visited_from": answering(CANNOT), "date_visited_to": answering(LACKS)}))
    settle(rig, Scripted({"date_visited_from": answering(resolved(LABEL["date_visited_from"])),
        "date_visited_to": answering(LACKS)}))

    value = run.fields["date_visited_to"]
    assert (value.state, value.parsed, value.layer) == (ValueState.SUPPORTED, "2020-06-01", "derived")


def test_a_field_settled_absent_beside_a_settled_source_does_not_wait(tmp_path, first_pass_path):
    """wait_for_sources: only a held source (ambiguous, unresolved or unknown) makes a field wait, and only
    a field settled absent with no text waits."""
    rig, run = settled_elevations(tmp_path, "Elev.6400", "Elev.6400")
    for key in ELEVATIONS:
        run.fields[key] = FieldValue(state=ValueState.NOT_PRESENT)
    assert ontology_checks.wait_for_sources(run, eligible=ELEVATIONS) == {}
    run.fields["elevation_from_ft"] = FieldValue(state=ValueState.AMBIGUOUS)
    run.fields["elevation_to_ft"] = FieldValue(state=ValueState.NOT_PRESENT, literal="6400")
    assert ontology_checks.wait_for_sources(run, eligible=PARTNERS) == {
        "elevation_from_m": ["elevation_from_ft"], "elevation_to_m": ["elevation_from_ft"]}
    # An unknown source holds its fields too; a field outside `eligible` (a person's) never waits.
    run.fields.update({"date_visited_from": FieldValue(), "date_visited_to": FieldValue(state=ValueState.NOT_PRESENT)})
    assert ontology_checks.wait_for_sources(run, eligible=["elevation_from_m"]) == {}
    assert ontology_checks.wait_for_sources(run, eligible=["date_visited_to"]) == {
        "date_visited_to": ["date_visited_from"]}
    assert run.fields["date_visited_to"].state == ValueState.UNKNOWN


# ---- 3. an elevation inside a precise location ---------------------------------------------------

YEPOCAPA_ELEVATION = {"r1": {"4800 ft."}}


@pytest.mark.parametrize(("literal", "elevations", "accepted"), [
    (YEPOCAPA, YEPOCAPA_ELEVATION, True),
    ("Yepocapa, 4800 ft.", YEPOCAPA_ELEVATION, True),
    (YEPOCAPA, None, False),
    (YEPOCAPA, {"r1": {"4800"}}, False),
    (YEPOCAPA, {"r1": {"4800 ft"}}, False),
    (YEPOCAPA, {"r2": {"4800 ft."}}, False),
    (YEPOCAPA, "any", True),
], ids=["whole-settled", "town-line-settled", "nothing-settled", "number-settled", "other-text-settled",
        "other-label-settled", "expert-check"])
def test_yepocapa_s_elevation_is_kept_only_as_the_literal_its_elevation_field_settled(first_pass_path, literal,
        elevations, accepted):
    """The plan's case, read from the transcript: "Yepocapa, 4800 ft." over "Chimaltenango, Guatemala" is
    accepted on the units path only when the elevation field settled "4800 ft." from that label (or, in
    the expert's own check, before any field settles: agreement.ANY_ELEVATION); otherwise refused for the
    elevation it holds. The old path refuses it whatever settled, as on origin/main."""
    readings = label_readings(YEPOCAPA, first_pass_path == "units")
    task = FieldTask("precise_location", True, FieldValue(), (), FIELD_TOOLS["precise_location"])
    if elevations == "any":
        elevations = agreement.ANY_ELEVATION

    refused = agreement.literal_refusal(task, readings, literal=literal, named=readings, elevations=elevations)

    if accepted and first_pass_path == "units":
        assert refused is None
    else:
        assert refused is not None and refused.reason == agreement.HOLDS_AN_ELEVATION


@pytest.mark.parametrize("literal", ELEVATION_REVIEW_CASES)
def test_the_review_rounds_elevation_inputs_stay_refused_whatever_elevation_settled(first_pass_path, literal):
    """The review rounds' inputs, each with its own elevation text (written.other_kind) settled from its
    label, and with every text (the expert's check): none is accepted on either path. "4800 ft.", "Elev.
    6400'" alone and the sea-level phrases have no Precise Location; the collector and date lines write
    no elevation at the end of their line, or a month before it."""
    from specimen_digitization.field_research import written

    readings = label_readings(literal + "\nChimaltenango, Guatemala", first_pass_path == "units")
    task = FieldTask("precise_location", True, FieldValue(), (), FIELD_TOOLS["precise_location"])
    own = written.other_kind(literal, place=True)[1]

    for elevations in ({"r1": {own}}, agreement.ANY_ELEVATION):
        refused = agreement.literal_refusal(task, readings, literal=literal, named=readings, elevations=elevations)
        assert refused is not None and refused.reason == agreement.HOLDS_AN_ELEVATION, elevations
    assert agreement.elevation_kept(literal) is None


@pytest.mark.parametrize(("literal", "kept"), [
    (YEPOCAPA, "4800 ft."), ("Yepocapa, 4800 ft.", "4800 ft."),
    ("E. slope Mt. McKinley\nDavao, Prov. 3300'\nMindanao, P.I.", "3300'"),
    ("Yepocapa, 4800 ft. 4800 ft.", None),          # written twice
    ("Yepocapa, 4800 ft. IV-24-48", None),          # a date after it on its line
    ("Yepocapa, 4800 ft.\nIV-24-48", None),         # a date on another line
    ("Yepocapa, 4800 ft.\n1200 m", None),           # a second elevation
    ("Elev. 4800 ft.", None),                       # a heading, no locality
    ("Guatemala", None),                            # no elevation at all
])
def test_elevation_kept_keeps_one_elevation_at_its_line_s_end_beside_a_locality(literal, kept):
    assert agreement.elevation_kept(literal) == kept


def test_an_organiser_candidate_holding_an_elevation_follows_the_same_rule(first_pass_path):
    """The candidate basis (agreement.literal_basis CANDIDATE): an organiser candidate "Yepocapa, 4800 ft.\\n
    Chimaltenango, Guatemala" taken as the precise location. On the units path it settles only when the
    elevation field settled "4800 ft." from its label, as the transcript basis does; on the old path it
    passes whatever settled, as on origin/main."""
    from specimen_digitization.field_research.contracts import Candidate

    readings = label_readings(YEPOCAPA, first_pass_path == "units")
    candidates = tuple(Candidate(reading.name, YEPOCAPA, YEPOCAPA, f"e-{reading.name}") for reading in readings)
    task = FieldTask("precise_location", True, FieldValue(), candidates, FIELD_TOOLS["precise_location"])
    assert agreement.literal_basis(task, readings, YEPOCAPA, readings) == agreement.CANDIDATE

    nothing = agreement.literal_refusal(task, readings, literal=YEPOCAPA, named=readings)
    settled = agreement.literal_refusal(task, readings, literal=YEPOCAPA, named=readings,
        elevations=YEPOCAPA_ELEVATION)

    if first_pass_path == "units":
        assert nothing is not None and nothing.reason == agreement.HOLDS_AN_ELEVATION
        assert settled is None
    else:
        assert nothing is None and settled is None


def settled_run(tmp_path, text, scripts, *, candidates=COLLECTORS):
    """test_precise_location_extent.settled_run with the organiser's `candidates`: the label `text` read
    alike by both readers, every field's expert scripted (`scripts`, else label_lacks_value), applied and
    finalized; the rig, the run and the step's decisions."""
    rig = build_rig(tmp_path, text, candidates=candidates)
    run = rig.specimen.run
    fields = [key for key in FIELD_TOOLS if key != "identified_by_irn"]
    prepared, outcomes, calls = research(rig, Scripted({**{key: answering(LACKS) for key in fields}, **scripts}),
        tools=Gazetteer(rig.blobs))
    decisions: dict[str, dict] = {}
    field_step.apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls, decisions=decisions)
    field_step.finalize_fields(run, None, outcomes, specimen=rig.specimen, blobs=rig.blobs, today=TODAY)
    return rig, run, decisions


def test_an_organiser_candidate_holding_a_date_is_refused_on_the_units_path(first_pass_path):
    """The candidate basis follows the transcript basis's whole rule on the units path: a candidate precise
    location that holds a date is refused (HOLDS_A_DATE), as the extent rule's instruction says ("never a
    collector or a date"); on the old path it passes, as on origin/main."""
    from specimen_digitization.field_research.contracts import Candidate

    literal = "Yepocapa, IV-24-48"
    readings = label_readings(literal + "\nChimaltenango, Guatemala", first_pass_path == "units")
    task = FieldTask("precise_location", True, FieldValue(),
        tuple(Candidate(reading.name, literal, literal, f"e-{reading.name}") for reading in readings),
        FIELD_TOOLS["precise_location"])

    refused = agreement.literal_refusal(task, readings, literal=literal, named=readings,
        elevations=agreement.ANY_ELEVATION)

    assert (refused.reason if refused else None) == (agreement.HOLDS_A_DATE if first_pass_path == "units" else None)


def yepocapa_run(tmp_path, elevation, *, candidate=False):
    """105526329's two locality lines read alike by both readers, its town and country settled, the
    precise location answered whole (the organiser's candidate for both readers when `candidate`) and
    the foot field's expert answering `elevation`; applied and finalized."""
    candidates = [*COLLECTORS, *(("precise_location", name, YEPOCAPA, YEPOCAPA) for name in ("1A", "1B"))] \
        if candidate else COLLECTORS
    return settled_run(tmp_path, YEPOCAPA, {**IN_YEPOCAPA, "elevation_from_ft": elevation,
        "precise_location": whole(YEPOCAPA)}, candidates=candidates)


@pytest.mark.parametrize("candidate", [False, True], ids=["transcript", "candidate"])
def test_105526329_s_whole_locality_settles_beside_its_settled_elevation_on_the_units_path(tmp_path,
        first_pass_path, candidate):
    """The elevation field's answer "4800 ft." from the label: on the units path the precise location settles
    as written, its elevation line included, on either basis, and the elevation settles beside it. On the
    old path, as on origin/main, the transcript's locality goes to review as text the elevation field
    claims (step._taken), and the organiser's candidate settles and takes the elevation's text, which goes
    to review instead."""
    rig, run, _ = yepocapa_run(tmp_path, answering(resolved("4800 ft.", value="4800")), candidate=candidate)

    place, height = run.fields["precise_location"], run.fields["elevation_from_ft"]
    if first_pass_path == "units":
        assert (place.state, place.literal) == (ValueState.SUPPORTED, YEPOCAPA)
        assert (height.state, height.literal) == (ValueState.SUPPORTED, "4800 ft.")
    elif candidate:
        assert (place.state, place.literal) == (ValueState.SUPPORTED, YEPOCAPA)
        assert height.state == ValueState.UNRESOLVED
        assert height.reason.startswith(field_step.TAKEN.format(other="Precise Location"))
    else:
        assert (place.state, place.literal) == (ValueState.UNRESOLVED, None)
        assert place.reason.startswith(field_step.TAKEN.format(other="Elevation From (ft)"))
        assert (height.state, height.literal) == (ValueState.SUPPORTED, "4800 ft.")


@pytest.mark.parametrize("candidate", [False, True], ids=["transcript", "candidate"])
@pytest.mark.parametrize("elevation", ["number", "none"])
def test_105526329_s_whole_locality_is_refused_beside_another_elevation_or_none(tmp_path, first_pass_path,
        candidate, elevation):
    """The elevation field settled the number "4800" (its literal another text than the locality's
    "4800 ft.") or nothing: on the units path the precise location is left for a person on either basis.
    On the old path the transcript's locality is refused and the organiser's candidate settles, as on
    origin/main."""
    answer = answering(resolved("4800", value="4800")) if elevation == "number" else answering(LACKS)
    rig, run, _ = yepocapa_run(tmp_path, answer, candidate=candidate)

    place = run.fields["precise_location"]
    if first_pass_path == "old" and candidate:
        assert (place.state, place.literal) == (ValueState.SUPPORTED, YEPOCAPA)
    else:
        assert place.state == ValueState.UNRESOLVED
        assert place.reason.startswith((agreement.HOLDS_AN_ELEVATION, field_step.TAKEN.format(
            other="Elevation From (ft)")))


def test_the_expert_s_own_check_lets_a_kept_elevation_pass_on_the_units_path_only(tmp_path, first_pass_path):
    """experts._Expert.validate: before any field settles, a precise location keeping an elevation the rule
    could accept passes on the units path (agreement.ANY_ELEVATION), and the step decides; a review-round
    input is still sent back. On the old path both are sent back, as on origin/main."""
    rig = build_rig(tmp_path, YEPOCAPA + "\nYepocapa, 1948 M. Smith\n" + label_with(precise_location=None))
    readings, tasks, _ = field_step.build_tasks(rig.specimen.run)
    [task] = [task for task in tasks if task.key == "precise_location"]
    expert = experts._Expert(task, readings, Gazetteer(rig.blobs), None)
    answer = FieldAnswer(outcome="resolved", literal=YEPOCAPA, reading_names=["1A", "1B"],
        explanation="The locality.")

    if first_pass_path == "units":
        assert expert.validate(answer).literal == YEPOCAPA
    else:
        with pytest.raises(ModelRetry, match="holds '4800 ft.'"):
            expert.validate(answer)
    with pytest.raises(ModelRetry, match="holds '1948 M.'"):
        expert.validate(answer.model_copy(update={"literal": "Yepocapa, 1948 M. Smith"}))


def test_a_settled_precise_location_and_an_elevation_share_its_text_on_the_units_path(first_pass_path):
    """step._keeps_an_elevation, in both directions: the precise location keeps the elevation field's
    literal, on a label both are read from. Another literal, another label or another pair of fields
    shares nothing."""
    keeps = field_step._keeps_an_elevation
    assert keeps("precise_location", YEPOCAPA, {"r1"}, "elevation_from_ft", "4800 ft.", {"r1"})
    assert keeps("elevation_from_ft", "4800 ft.", {"r1"}, "precise_location", YEPOCAPA, {"r1"})
    assert not keeps("precise_location", YEPOCAPA, {"r1"}, "elevation_from_ft", "4800", {"r1"})
    assert not keeps("precise_location", YEPOCAPA, {"r1"}, "elevation_from_ft", "4800 ft.", {"r2"})
    assert not keeps("precise_location", YEPOCAPA, {"r1"}, "city", "4800 ft.", {"r1"})
    assert not keeps("collectors", YEPOCAPA, {"r1"}, "elevation_from_ft", "4800 ft.", {"r1"})


# ---- 4. a precise location cut short (precise_location_extent) ------------------------------------

# 105526321's province and country: "Davao Prov." settled on Wikidata's former province of the Philippines,
# which confirms the initials "P.I." (test_step's DavaoProvince).
DAVAO_AND_PI = {**ABBREVIATED_COUNTRY, "province_state": from_tgn("Davao Province, Philippines", "Davao Prov.", "Davao",
    "wikidata:Q15095071", source="wikidata")}


def mckinley_run(tmp_path, answered, text=MCKINLEY + "\n3 Sept. '46\nF.G. Werner", other=None):
    """105526321's locality block, its province "Davao Prov." and its country "P.I." settled, the precise
    location answered `answered` from the transcript."""
    rig = build_rig(tmp_path, text, other)
    run = rig.specimen.run
    fields = [key for key in FIELD_TOOLS if key != "identified_by_irn"]
    settle(rig, Scripted({**{key: answering(LACKS) for key in fields}, **DAVAO_AND_PI,
        "precise_location": whole(answered)}), tools=DavaoProvince(rig.blobs))
    assert [run.fields[key].state for key in ("province_state", "country")] == [ValueState.SUPPORTED] * 2
    return rig, run


def extent_marks(run):
    return [f.reason_code for f in run.findings if f.rule_id == STAGE and f.field_key == "precise_location"]


@pytest.mark.parametrize(("answered", "line", "level", "text"), [
    ("E. slope Mt. McKinley", "Davao Prov.", "province or state", "Davao Prov."),
    ("E. slope Mt. McKinley\nDavao Prov.", "Mindanao, P.I.", "country", "P.I."),
], ids=["before-the-province", "before-the-country"])
def test_a_precise_location_cut_short_before_a_line_holding_a_settled_higher_place_is_marked(tmp_path,
        first_pass_path, answered, line, level, text):
    """The plan's case: "E. slope Mt. McKinley" settled where the label goes on with "Davao Prov." and
    "Mindanao, P.I.", the province and the country settled; and the same block cut after its province's
    line. On the units path the precise location is marked, its reason naming the rule and the line; on
    the old path nothing is marked."""
    rig, run = mckinley_run(tmp_path, answered)

    place = run.fields["precise_location"]
    assert (place.state, place.literal) == (ValueState.SUPPORTED, answered)
    if first_pass_path == "units":
        code = field_step.marked_code("precise_location", run.regions[0].id, "precise_location_extent")
        assert extent_marks(run) == [code] and code in run.reasons
        assert place.reason.endswith(f"Marked for a person, rule precise_location_extent: the label's next line, "
            f"{line!r}, writes the {level} settled, {text!r}, so its locality goes on after this text.")
    else:
        assert extent_marks(run) == [] and "Marked for a person" not in place.reason


@pytest.mark.parametrize(("answered", "text", "other"), [
    # The whole block: the date and the collector follow it.
    (MCKINLEY, MCKINLEY + "\n3 Sept. '46\nF.G. Werner", None),
    # Cut within its line: the check abstains.
    ("E. slope Mt. McKinley\nDavao", MCKINLEY + "\n3 Sept. '46\nF.G. Werner", None),
    # The literal ends the reading's text: no next line.
    (MCKINLEY, "3 Sept. '46\nF.G. Werner\n" + MCKINLEY, None),
    # Reader 1B writes the literal before another line: the readings do not agree that it is cut short.
    ("E. slope Mt. McKinley\nDavao Prov.", MCKINLEY + "\n3 Sept. '46\nF.G. Werner",
     "E. slope Mt. McKinley\nDavao Prov.\n3 Sept. '46\nMindanao, P.I.\nF.G. Werner"),
], ids=["whole", "within-a-line", "no-next-line", "readers-differ"])
def test_the_cut_short_check_abstains_unless_certain(tmp_path, first_pass_path, answered, text, other):
    rig, run = mckinley_run(tmp_path, answered, text, other)

    assert extent_marks(run) == []


def test_a_person_s_precise_location_is_never_marked_cut_short(first_pass_path):
    """_extent_marks: a person's precise location, or one that is not settled, is not checked."""
    from specimen_digitization.field_research.contracts import Reading

    text = MCKINLEY
    readings = (Reading("1A", "r1", "o1a", "raw_reading", text), Reading("1B", "r1", "o1b", "raw_reading", text))
    fields = {"precise_location": FieldValue(state=ValueState.SUPPORTED, literal="E. slope Mt. McKinley\nDavao Prov.",
        layer="settled", source_region_id="r1"),
        "country": FieldValue(state=ValueState.SUPPORTED, literal="P.I.", layer="settled", source_region_id="r1")}
    assert [mark.check for mark in ontology_checks._extent_marks(fields, readings, {}, ())] == [
        "precise_location_extent"]
    assert ontology_checks._extent_marks(fields, readings, {}, {"precise_location"}) == []
    held = {**fields, "precise_location": fields["precise_location"].model_copy(update={"state": ValueState.AMBIGUOUS})}
    assert ontology_checks._extent_marks(held, readings, {}, ()) == []
    derived = {**fields, "country": fields["country"].model_copy(update={"state": ValueState.UNRESOLVED})}
    assert ontology_checks._extent_marks(derived, readings, {}, ()) == []
    # The place's text inside a longer word on the next line is not that place.
    inside = (Reading("1A", "r1", "o1a", "raw_reading", "E. slope Mt. McKinley\nDavaoville\nP.I."),)
    davao = {"precise_location": fields["precise_location"].model_copy(update={"literal": "E. slope Mt. McKinley"}),
        "province_state": FieldValue(state=ValueState.SUPPORTED, literal="Davao", layer="settled", source_region_id="r1")}
    assert ontology_checks._extent_marks(davao, inside, {}, ()) == []
    assert [mark.check for mark in ontology_checks._extent_marks(davao, (Reading("1A", "r1", "o1a", "raw_reading",
        "E. slope Mt. McKinley\nDavao, Prov."),), {}, ())] == ["precise_location_extent"]


# ---- 5. a country-only locality ------------------------------------------------------------------

def test_a_label_whose_only_locality_text_is_its_country_settles_it_as_the_precise_location_on_the_units_path(
        tmp_path, first_pass_path):
    """A label whose only locality text is "Guatemala". The PRD's Precise Location is the verbatim locality
    as written (PRD.md:519, :774), Darwin Core's verbatimLocality (GEOREFERENCING.md:258), whose example
    keeps the country's line (:276): on the units path the answer "Guatemala" settles as written, and no
    check marks it. On the old path it is no finer locality than the settled country (step._repeats_a_place)
    and, with no city or county settled, waits for a person, as on origin/main."""
    text = "Guatemala\nIV-24-48\nR.D. Mitchell"
    rig, run, decisions = settled_run(tmp_path, text, {**IN_GUATEMALA, "province_state": answering(LACKS),
        "precise_location": whole("Guatemala")})

    place = run.fields["precise_location"]
    assert run.fields["country"].state == ValueState.SUPPORTED
    if first_pass_path == "units":
        assert (place.state, place.literal) == (ValueState.SUPPORTED, "Guatemala")
        assert extent_marks(run) == []
    else:
        assert place.state == ValueState.NOT_PRESENT
        assert decisions["precise_location"]["rule"] == "A_declined:no_city_or_county_settled"
        assert "mandatory_unresolved:precise_location" in run.reasons


# ---- 6. derive.py's rules from the file ----------------------------------------------------------

# ontology_checks.DERIVED_RULES before WP 2.3b, as origin/main 7f412f91d wrote it, in its order.
MAIN_DERIVED_RULES = {
    "country": "place_parents_derived", "province_state": "place_parents_derived", "county": "place_parents_derived",
    "elevation_from_m": "elevation_conversion", "elevation_to_m": "elevation_conversion",
    "elevation_from_ft": "elevation_conversion", "elevation_to_ft": "elevation_conversion",
    "date_visited_to": "end_date_from_one_date",
}


def test_derive_reads_its_rules_from_the_file_and_they_are_main_s():
    rules = {rule.id: rule for rule in ontology.ontology().rules}

    assert list(derive.DERIVED_RULES.items()) == list(MAIN_DERIVED_RULES.items())
    assert ontology_checks.DERIVED_RULES is derive.DERIVED_RULES
    assert {rule.id for rule in rules.values() if rule.derives} == set(MAIN_DERIVED_RULES.values())
    for key, rule in MAIN_DERIVED_RULES.items():
        assert key in rules[rule].fields


# What derive.fill writes for test_step's synthetic label, on origin/main 7f412f91d: each derived value's
# field, parsed value, precision, the fields it is derived from, and its one "derived" row's locator,
# excerpt and stored record.
def _derived_row(key, value, source, written, rule, said):
    return (key, value, None, [source], f"derivation:{rule}", f"{key} = {value}: {said} (from {source} = {written})",
        {"field_key": key, "inputs": {source: written}, "rule": rule, "rules_version": "field-research-derivations-v1",
         "value": value})


BOTH_ENDS = "one stated elevation is both the minimum and the maximum"
MAIN_DERIVATIONS = [
    _derived_row("elevation_from_m", "457.2", "elevation_from_ft", "1500", "unit_conversion",
        "1 ft = 0.3048 m, exact"),
    _derived_row("elevation_to_m", "457.2", "elevation_from_ft", "1500", "unit_conversion",
        f"{BOTH_ENDS}; 1 ft = 0.3048 m, exact"),
    _derived_row("elevation_to_ft", "1500", "elevation_from_ft", "1500", "stated_elevation", BOTH_ENDS),
    _derived_row("date_visited_to", "2020-06-01", "date_visited_from", "2020-06-01", "single_collecting_date",
        "the label states one collecting date, so the collection ends on the day it began (G44)"),
]


def test_derivation_writes_what_it_wrote_on_main(tmp_path, first_pass_path):
    """derive.fill's values, rows and records on test_step's label, pinned as origin/main writes them:
    reading the rules from the file changes none of them, on either path."""
    rig = build_rig(tmp_path)
    run = rig.specimen.run
    prepared, outcomes, calls = research(rig, Scripted())
    field_step.apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls)

    rows = {item.id: item for item in run.evidence}
    found = []
    for key, value in run.fields.items():
        if value.layer != "derived":
            continue
        [row] = [rows[i] for i in value.evidence_ids if rows[i].kind == "derived" and rows[i].locator.startswith(
            "derivation:")]
        found.append((key, value.parsed, value.precision, value.derived_from, row.locator, row.excerpt,
            json.loads(rig.blobs.get(row.raw_ref))))
    assert found == MAIN_DERIVATIONS
