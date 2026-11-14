"""WP 2.3a of docs/execution/units/PLAN.md: the check stage
(docs/product-requirements/FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md section 4, "The check stage";
field_research/ontology_checks.py), its place, date, code and label-routing checks, and the named
cases of the plan's WP 2.3 row that belong to them.

Every test runs on both first-pass paths (conftest.py). On the units path the stage marks a value
that fails a rule of the ontology; on the old path, live in production until WP 1.8, nothing
changes: each test asserts the old path's result as main gives it, so a gate that leaks fails here.

The gazetteer answers are made up in the shape sources._place gives them (each place's parents,
nearest first, its country last), not recorded responses."""

from __future__ import annotations

import asyncio
import hashlib
import json

import pytest
from pydantic_ai import ModelRetry
from test_experts import PILOT_DATES
from test_step import (
    COLLECTORS,
    FakeSources,
    Scripted,
    a_second_label,
    answering,
    build_rig,
    from_tgn,
    label_with,
    research,
    resolved,
    settle,
)

from specimen_digitization import ontology
from specimen_digitization.application.domain import Evidence, FieldValue, LookupStatus, ValueState
from specimen_digitization.application.workflow import store_reading_units
from specimen_digitization.field_research import agreement, checks, experts
from specimen_digitization.field_research import step as field_step
from specimen_digitization.field_research.contracts import FieldAnswer, PlaceRef, SourceAnswer, SourceCandidate
from specimen_digitization.field_research.step import apply_outcomes, build_tasks

# The check stage's findings (ontology_checks.CHECK_STAGE); the derived rules by field
# (ontology_checks.DERIVED_RULES), as test_the_stage_s_names_are_these_and_its_rules_are_rules_of_the_file_that_
# name_their_field pins them.
STAGE = "check_stage"
DERIVED_RULES = {"elevation_from_m": "elevation_conversion", "elevation_to_m": "elevation_conversion",
    "elevation_from_ft": "elevation_conversion", "elevation_to_ft": "elevation_conversion",
    "date_visited_to": "end_date_from_one_date", **dict.fromkeys(("country", "province_state", "county"),
        "place_parents_derived")}
COUNTY_KIND = "counties, second level subdivisions (political entities)"
US = ("United States", "tgn:United States")
# Getty TGN's places these tests add to test_step's (TGN_PLACES): name -> (record, kind, parents).
PLACES = {
    "Coles": ("tgn:Coles", COUNTY_KIND, (("Illinois", "tgn:Illinois"), US)),
    "Gary": ("tgn:Gary", "inhabited places", (("Lake", "tgn:Lake"), ("Indiana", "tgn:Indiana"), US)),
    # The nation Georgia, and a county Fulton in the US state Georgia: two places of one name.
    "Georgia": ("tgn:georgia-nation", "nations", ()),
    "Fulton": ("tgn:Fulton", COUNTY_KIND, (("Georgia", "tgn:georgia-state"), US)),
    # A county whose record names only its country.
    "Lonely": ("tgn:Lonely", COUNTY_KIND, (US,)),
}
LACKS = FieldAnswer(outcome="label_lacks_value", explanation="Not on the label.")
CANNOT = FieldAnswer(outcome="sources_cannot_resolve", explanation="No source settles it.")


class Places(FakeSources):
    """test_step's FakeSources, whose Getty TGN also answers PLACES."""

    def _answer(self, source_id, query):
        if source_id != "tgn" or query not in PLACES:
            return super()._answer(source_id, query)
        record, kind, parents = PLACES[query]
        raw = json.dumps({"source": source_id, "query": query}).encode()
        candidate = SourceCandidate(query, record, kind, "in " + ", ".join(name for name, _ in parents) or None,
            tuple(PlaceRef(name, key) for name, key in parents))
        evidence = Evidence(kind="authority", source="tgn", locator=record, raw_ref=self.blobs.put(raw),
            digest=hashlib.sha256(raw).hexdigest(), excerpt=f"match\n{query} | {record} | {kind} | {candidate.detail}")
        return SourceAnswer("tgn", query, LookupStatus.SUCCESS, (candidate,), evidence, note="match")


def tgn(name):
    """A place expert settling on Getty TGN's record for `name` (test_step's or PLACES)."""
    return from_tgn(name, name, None, PLACES[name][0] if name in PLACES else f"tgn:{name}")


def marks(run):
    """The check stage's findings' codes."""
    return sorted(f.reason_code for f in run.findings if f.rule_id == STAGE)


def value_of(run, key):
    value = run.fields[key]
    return value.state, value.literal, value.parsed, value.normalized, value.authority_id, value.layer


def code(run, key, check):
    return field_step.marked_code(key, run.regions[0].id, check)


# ---- places ------------------------------------------------------------------------------

def test_a_city_outside_the_settled_county_is_marked_on_the_units_path(tmp_path, first_pass_path):
    """The plan's case: a settled Coles County, then an exact "Chicago" under Illinois. Getty TGN's
    Chicago lies in Cook County, Illinois; the refusal at apply time holds a city to its county only
    for a near spelling, so the city settles on both paths, and on the units path the check stage
    marks it (place_chain), its reason naming the rule; on the old path nothing marks it."""
    rig = build_rig(tmp_path, label_with(county="Coles"))
    run = rig.specimen.run
    settle(rig, Scripted({"county": tgn("Coles"), "city": tgn("Chicago")}), tools=Places(rig.blobs))

    assert value_of(run, "county")[:2] == (ValueState.SUPPORTED, "Coles")
    assert value_of(run, "city") == (ValueState.SUPPORTED, "Chicago", "Chicago", None, "tgn:Chicago", "settled")
    if first_pass_path == "units":
        assert marks(run) == [code(run, "city", "place_chain")]
        assert code(run, "city", "place_chain") in run.reasons
        assert run.fields["city"].reason.endswith(
            "Marked for a person, rule place_chain: the source's record for 'Chicago' (tgn:Chicago) places it in "
            "Cook, Illinois, United States, not in the county settled above it, 'Coles'.")
    else:
        assert marks(run) == [] and not any(reason.startswith("marked:city:") for reason in run.reasons)
        assert "rule place_chain" not in run.fields["city"].reason


def test_a_city_inside_its_settled_county_is_not_marked(tmp_path, first_pass_path):
    """test_step's synthetic label: Chicago in Cook County, Illinois, United States, each settled on
    Getty TGN's record. Every place lies in those above it: nothing is marked on either path."""
    rig = build_rig(tmp_path)
    run = rig.specimen.run
    settle(rig, Scripted({"city": tgn("Chicago")}), tools=Places(rig.blobs))

    assert [value_of(run, key)[0] for key in agreement.PLACE_ORDER] == [ValueState.SUPPORTED] * 4
    assert marks(run) == []


def test_a_county_in_a_state_named_as_the_settled_country_is_marked_by_the_check_stage(tmp_path, first_pass_path):
    """From WP 2.1's review, round 4: the country Georgia settled, then a county Fulton whose source
    names the US state Georgia. agreement.lies_in matches a parent by name, so the refusal at apply
    time lets it pass on both paths, as today; on the units path the check stage marks it
    (place_within_settled_places): the record's country, its last parent, is the United States."""
    rig = build_rig(tmp_path, label_with(country="Georgia", province_state=None, county="Fulton", city=None))
    run = rig.specimen.run
    settle(rig, Scripted({"country": tgn("Georgia"), "province_state": answering(LACKS), "county": tgn("Fulton"),
        "city": answering(LACKS)}), tools=Places(rig.blobs))

    assert value_of(run, "country")[:2] == (ValueState.SUPPORTED, "Georgia")
    assert value_of(run, "county")[:2] == (ValueState.SUPPORTED, "Fulton")
    if first_pass_path == "units":
        assert marks(run) == [code(run, "county", "place_within_settled_places")]
        assert run.fields["county"].reason.endswith(
            "Marked for a person, rule place_within_settled_places: the source's record for 'Fulton' (tgn:Fulton) "
            "places it in Georgia, United States, not in the country settled above it, 'Georgia'.")
    else:
        assert marks(run) == []


def test_a_city_whose_province_is_written_and_unsettled_is_refused_as_today(tmp_path, first_pass_path):
    """From WP 2.1's review, round 4: the country United States settled, a province written "Cook"
    and unsettled, a settled county Cook, an exact city Gary in Indiana: refused at apply time
    (NO_PROVINCE), on both paths, and the check stage marks no value it did not settle."""
    text = label_with(province_state="Cook", county="Cook", city="Gary")
    places = [(key, name, literal, f"{key}: {literal}") for key, literal in (
        ("country", "United States"), ("province_state", "Cook"), ("county", "Cook"), ("city", "Gary"))
        for name in ("1A", "1B")]
    rig = build_rig(tmp_path, text, candidates=[*places, *COLLECTORS])
    run = rig.specimen.run
    decisions: dict[str, dict] = {}
    prepared, outcomes, calls = research(rig, Scripted({"province_state": answering(CANNOT), "county": tgn("Cook"),
        "city": tgn("Gary")}), tools=Places(rig.blobs))
    apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls, decisions=decisions)

    assert value_of(run, "county")[:2] == (ValueState.SUPPORTED, "Cook")
    assert run.fields["city"].state != ValueState.SUPPORTED
    assert decisions["city"]["refusal"] == "no_province"
    assert [mark for mark in marks(run) if ":city:" in mark] == []


def cook_and_gary(rig):
    """A county Cook and a city Gary researched in this attempt; the province's text "Cook" left
    unresolved by an earlier one (no organiser row of this label names a province)."""
    run = rig.specimen.run
    run.fields["province_state"] = FieldValue(state=ValueState.UNRESOLVED, literal="Cook",
        reason="No source settles the province.")
    prepared, outcomes, calls = research(rig, Scripted({"county": tgn("Cook"), "city": tgn("Gary")}),
        tools=Places(rig.blobs))
    keep = {"country", "county", "city"}
    apply_outcomes(run, None, [task for task in prepared[1] if task.key in keep],
        [outcome for outcome in outcomes if outcome.key in keep], blobs=rig.blobs,
        calls=[call for call in calls if call.field_key in keep])
    return run


def test_a_derived_province_that_fails_the_place_chain_is_marked(tmp_path, first_pass_path):
    """From WP 2.1's review, round 4: a province text "Cook" unresolved, a settled county Cook in
    Illinois and a settled city Gary in Indiana. Derivation fills the province as Illinois from the
    county alone (derive._can_derive_place), on both paths, as today; on the units path the check
    stage marks that derived province (place_parents_derived): the city settled below it lies in
    Indiana by its record; and the city, outside the settled county (place_chain)."""
    rig = build_rig(tmp_path, label_with(province_state=None, county="Cook", city="Gary"))
    run = cook_and_gary(rig)

    assert value_of(run, "province_state") == (ValueState.SUPPORTED, None, "Illinois", None, "tgn:Illinois", "derived")
    assert value_of(run, "city")[:2] == (ValueState.SUPPORTED, "Gary")
    if first_pass_path == "units":
        assert marks(run) == sorted([code(run, "province_state", "place_parents_derived"),
            code(run, "city", "place_chain")])
        assert ("Marked for a person, rule place_parents_derived: this province or state was derived, and the city "
            "settled below it, 'Gary', lies in Lake, Indiana, United States by its source's record (tgn:Gary), "
            "not in it.") in run.fields["province_state"].reason
    else:
        assert marks(run) == []
        assert "Basis:" not in run.fields["province_state"].reason


@pytest.mark.parametrize(("county", "province"), [("Cook", "Illinois"), ("Lonely", None)],
    ids=["record-names-the-state", "record-names-only-the-country"])
def test_a_province_derived_from_a_county_is_its_province_level_parent_never_the_country(
        tmp_path, first_pass_path, county, province):
    """From WP 2.1's review, round 4: a province derived from a settled county whose source names
    Illinois and the United States is Illinois, the county's province-level parent, never the
    country; a county whose record names only its country derives no province (derive.fill, the
    same on both paths). On the units path the derived value's reason names its rule."""
    rig = build_rig(tmp_path, label_with(province_state=None, county=county, city=None))
    run = rig.specimen.run
    settle(rig, Scripted({"province_state": answering(LACKS), "county": tgn(county), "city": answering(LACKS)}),
        tools=Places(rig.blobs))

    found = run.fields["province_state"]
    if province is None:
        assert found.state != ValueState.SUPPORTED and found.parsed is None
        return
    assert value_of(run, "province_state") == (ValueState.SUPPORTED, None, province, None, f"tgn:{province}",
        "derived")
    assert found.derived_from == ["county"]
    assert marks(run) == []
    assert found.reason.endswith("Basis: derived, rule place_parents_derived.") == (first_pass_path == "units")


def test_every_derived_value_names_its_rule_on_the_units_path_only(tmp_path, first_pass_path):
    """The plan's WP 2.3 acceptance, 0 derived values whose reason names no rule: test_step's label
    derives the elevations (elevation_conversion) and the collection's end date
    (end_date_from_one_date). On the old path their reasons are main's."""
    rig = build_rig(tmp_path)
    run = rig.specimen.run
    settle(rig, Scripted(), tools=Places(rig.blobs))

    derived = {key: value.reason for key, value in run.fields.items() if value.layer == "derived"}
    assert set(derived) == {"elevation_from_m", "elevation_to_m", "elevation_to_ft", "date_visited_to"}
    for key, reason in derived.items():
        named = f"Basis: derived, rule {DERIVED_RULES[key]}."
        assert reason.endswith(named) == (first_pass_path == "units"), (key, reason)
        assert reason.startswith("Derived: ")


def test_the_stage_s_names_are_these_and_its_rules_are_rules_of_the_file_that_name_their_field():
    from specimen_digitization.field_research import ontology_checks

    assert (ontology_checks.CHECK_STAGE, ontology_checks.DERIVED_RULES) == (STAGE, DERIVED_RULES)
    rules = {rule.id: rule for rule in ontology.ontology().rules}
    for key, rule in DERIVED_RULES.items():
        assert key in rules[rule].fields
    assert set(ontology_checks.CHECKS) <= set(rules)


# ---- dates -------------------------------------------------------------------------------

def dated(tmp_path, collected, identified):
    rig = build_rig(tmp_path, label_with(date_visited_from=collected, date_identified=identified))
    settle(rig, Scripted({"date_visited_from": answering(resolved(collected)),
        "date_identified": answering(resolved(identified))}), tools=Places(rig.blobs))
    return rig.specimen.run


def test_a_determination_on_the_collecting_day_is_allowed(tmp_path, first_pass_path):
    """The plan's case: collected 1946-09-06, determined 1946-09-06: the same day is allowed, on
    both paths."""
    run = dated(tmp_path, "1946-09-06", "1946-09-06")

    assert [value_of(run, key)[2] for key in ("date_visited_from", "date_identified")] == ["1946-09-06"] * 2
    assert marks(run) == [] and "date_order" not in run.reasons


def test_a_determination_before_the_collecting_date_is_marked_with_both_dates(tmp_path, first_pass_path):
    """The plan's case: determined before collected. Both paths keep the run's date_order reason, as
    today; on the units path the check stage also marks the determination date (date_order), its
    reason listing both dates."""
    run = dated(tmp_path, "1946-09-06", "1946-09-05")

    assert "date_order" in run.reasons
    assert value_of(run, "date_identified")[:3] == (ValueState.SUPPORTED, "1946-09-05", "1946-09-05")
    if first_pass_path == "units":
        assert marks(run) == [code(run, "date_identified", "date_order")]
        assert run.fields["date_identified"].reason.endswith(
            "Marked for a person, rule date_order: the determination date 1946-09-05 is before the collecting "
            "date 1946-09-06.")
    else:
        assert marks(run) == []


def test_a_year_agrees_with_a_day_in_that_year(tmp_path, first_pass_path):
    """The plan's case: "1946" against "1946-09-06" agree, compared on the parts both have, on the
    units path. The old path keeps today's date_order reason (step.scientific_reasons compares the
    year's first day)."""
    run = dated(tmp_path, "1946-09-06", "1946")

    assert value_of(run, "date_identified")[:3] == (ValueState.SUPPORTED, "1946", "1946")
    assert marks(run) == []
    assert ("date_order" in run.reasons) == (first_pass_path == "old")


@pytest.mark.parametrize(("collected", "identified", "before"), [
    ((1946, 9, 6), (1946, 9, 6), False), ((1946, 9, 6), (1946, 9, 5), True), ((1946, 9, 6), (1946,), False),
    ((1946,), (1946, 9, 6), False), ((1946, 9, 6), (1946, 8), True), ((1946, 9, 6), (1945,), True),
    ((1946, 9), (1946, 9, 1), False), ((1946, 9, 6), (1947, 1, 1), False)])
def test_dates_compare_on_the_parts_both_have(collected, identified, before):
    from specimen_digitization.field_research.ontology_checks import determined_before

    assert determined_before(collected, identified) is before


# ---- codes are no dates ------------------------------------------------------------------

CODE_READINGS = ["Guatemala I-23-48", "Guatemala VI-23-48-4"]


def test_a_date_one_reader_writes_inside_a_slide_code_is_no_date_on_the_units_path(first_pass_path):
    """From WP 2.1's review, round 5: the literal "I-23-48", reading A "Guatemala I-23-48", reading
    B "Guatemala VI-23-48-4": B writes a slide code there, and the code wins on the units path (no
    date). The old path keeps today's 1948-01-23: date_lines.places drops B, where the literal's
    "I" follows "V"."""
    units = first_pass_path == "units"
    result = checks.parse_date("I-23-48", reading_texts=CODE_READINGS, date_rules=PILOT_DATES, units=units)

    if units:
        assert (result.status, result.values, result.notes) == (LookupStatus.NO_MATCH, (), ("slide_code",))
    else:
        assert (result.status, result.values) == (LookupStatus.SUCCESS, ("1948-01-23",))
    # A collecting date beside a slide code is still a date (t1-329), on both paths.
    beside = checks.parse_date("IV-23-48", reading_texts=["IV-29-68-4 IV-23-48"], date_rules=PILOT_DATES,
        units=units)
    assert (beside.status, beside.values) == (LookupStatus.SUCCESS, ("1948-04-23",))


@pytest.mark.parametrize(("literal", "text", "inside"), [
    ("I-23-48", "Guatemala VI-23-48-4", True), ("IV-29-68", "slide IV-29-68-4,", True),
    ("6-78-1", "(10-6-78-1a)", True), ("I-23-48", "Guatemala I-23-48", False),
    ("IV-23-48", "IV-29-68-4 IV-23-48", False), ("I-23-48", "XVI-23-48-4", False),
    ("III-25", "VIII-25 1948", False)])
def test_a_literal_is_in_a_code_only_inside_a_longer_token_the_ontology_reads_as_a_slide_code(literal, text, inside):
    assert checks.in_a_code(literal, text) is inside


def test_the_date_experts_check_gives_no_date_inside_a_code_and_its_value_is_refused_on_the_units_path(
        tmp_path, first_pass_path):
    """The same readings as a date expert sees them (step.run_readings; on the units path with their
    units): its parse_date tool gives no date on the units path, so a resolved answer with the value
    1948-01-23 is refused there (experts._Expert.validate); on the old path the tool gives today's
    1948-01-23."""
    rig = build_rig(tmp_path, label_with(date_visited_from="Guatemala I-23-48"),
        label_with(date_visited_from="Guatemala VI-23-48-4"))
    readings, tasks, _ = build_tasks(rig.specimen.run)
    [task] = [task for task in tasks if task.key == "date_visited_from"]
    expert = experts._Expert(task, readings, Places(rig.blobs), PILOT_DATES)

    found = asyncio.run(expert.parse_date("I-23-48"))
    if first_pass_path == "units":
        assert expert.units and (found["status"], found["notes"]) == (str(LookupStatus.NO_MATCH), ["slide_code"])
        assert "readings" not in found
        with pytest.raises(ModelRetry, match="neither a candidate name"):
            expert.validate(FieldAnswer(outcome="resolved", literal="I-23-48", reading_names=["1A"],
                value="1948-01-23", explanation="The collecting date."))
    else:
        assert not expert.units and [reading["iso"] for reading in found["readings"]] == ["1948-01-23"]


# ---- label types never keep an expert from a unit ----------------------------------------

DETERMINATION = "det. J. Smith 1950\nYepocapa, Chimaltenango"


def test_a_determination_label_writing_a_locality_reaches_the_locality_expert(tmp_path, monkeypatch, first_pass_path):
    """The plan's case: a determination label that writes a locality. The precise location's expert
    receives that label's every reading whole and, on the units path, every unit of it, though each
    unit's advice names the determination's date alone (label_type_routing)."""
    a_second_label(monkeypatch, DETERMINATION)
    rig = build_rig(tmp_path)
    run = rig.specimen.run
    if first_pass_path == "units":
        [entry] = [entry for entry in run.reading_units if entry.label == run.regions[1].id]
        store_reading_units(run, [entry.model_copy(update={"units": [
            unit.model_copy(update={"fields": ["date_identified"]}) for unit in entry.units]})])
    readings, tasks, context = build_tasks(run)
    [task] = [task for task in tasks if task.key == "precise_location"]
    request = json.loads(experts._Expert(task, readings, Places(rig.blobs), PILOT_DATES).prompt(context)
        .removeprefix(experts.INPUT_PREFIX))

    second = [reading for reading in readings if reading.region_id == rig.specimen.run.regions[1].id]
    assert [reading.text for reading in second] == [DETERMINATION, DETERMINATION]
    given = {entry["name"]: entry["text"] for entry in request["readings"]}
    assert all(given.get(reading.name) == reading.text for reading in second)
    if first_pass_path == "units":
        number = second[0].name[:-1]
        units = request["units"][number]
        assert len(units) == len(second[0].units.units)
        assert all(unit["fields"] == ["date_identified"] for unit in units)
        assert any("Yepocapa" in (unit.get("text") or "".join(unit.get("readers", {}).values())) for unit in units)
    else:
        assert "units" not in request


# ---- what the stage leaves as it is --------------------------------------------------------

def test_the_stage_revises_no_value_marks_once_and_never_marks_a_persons_value(tmp_path, first_pass_path):
    """The stage run again over the Coles County label and a determination dated a day before the
    collecting date: every value but its reason stays as it was, and no mark is made twice. A person's
    value is never marked: with the city and the determination date a person's (step.human_keys), the
    collecting date is marked instead, and the city is not."""
    from specimen_digitization.field_research.ontology_checks import stage

    rig = build_rig(tmp_path, label_with(county="Coles", date_visited_from="1946-09-06",
        date_identified="1946-09-05"))
    run = rig.specimen.run
    prepared, outcomes, calls = research(rig, Scripted({"county": tgn("Coles"), "city": tgn("Chicago"),
        "date_visited_from": answering(resolved("1946-09-06")), "date_identified": answering(resolved("1946-09-05"))}),
        tools=Places(rig.blobs))
    apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls)
    received = {}
    for call in calls:
        received.setdefault(call.field_key, []).append(call.answer)
    before = {key: value.model_dump(exclude={"reason"}) for key, value in run.fields.items()}
    findings = list(run.findings)
    readings = field_step.run_readings(run)

    again = stage(run, readings=readings, received=received, researched=list(run.fields), derived=[], human=())
    assert {key: value.model_dump(exclude={"reason"}) for key, value in run.fields.items()} == before
    assert sorted(again) == sorted([code(run, "city", "place_chain"), code(run, "date_identified", "date_order")])
    assert [f for f in run.findings if f.rule_id != STAGE] == [f for f in findings if f.rule_id != STAGE]
    assert len(marks(run)) == 2
    # A field this attempt did not research keeps its mark, and it is not made again.
    stage(run, readings=readings, received=received, researched=[], derived=[], human=())
    assert marks(run) == sorted(again)

    stage(run, readings=readings, received=received, researched=list(run.fields), derived=[],
        human={"city", "date_identified"})
    assert marks(run) == [code(run, "date_visited_from", "date_order")]
    assert {key: value.model_dump(exclude={"reason"}) for key, value in run.fields.items()} == before
