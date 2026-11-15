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
from collections import Counter

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
from specimen_digitization.field_research.contracts import (
    FieldAnswer,
    FieldOutcome,
    PlaceRef,
    SourceAnswer,
    SourceCandidate,
)
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
    # Lake County, Illinois, whose name Gary's chain also holds, as Lake County, Indiana (tgn:Lake): G51's B4.
    "Lake": ("tgn:Lake-IL", COUNTY_KIND, (("Illinois", "tgn:Illinois"), US)),
    # The same county as NGA names it: its parents by name (its country with its code), no record of their own.
    "nga:Lake": ("nga:lake-il", "A.ADM2", (("Illinois", None), ("United States", None))),
    # NGA's nation Guatemala (its record carries GT), and two towns whose country NGA names by code.
    "nga:Guatemala": ("nga:-1135822", "A.PCLI", (("GT", None),), "GT"),
    "nga:Yepocapa": ("nga:-1143757", "P.PPLA2", (("Chimaltenango", None), ("GT", None))),
    "nga:Tapachula": ("nga:tapachula", "P.PPLA2", (("Chiapas", None), ("MX", None))),
    # Fulton County as NGA names it (its first-level unit Georgia, by name, and its country's code), and
    # the nation Georgia as Wikidata holds it (its record carries P297 GE).
    "nga:Fulton": ("nga:fulton", "A.ADM2", (("Georgia", None), ("United States", None))),
    "wikidata:Georgia": ("wikidata:Q230", "sovereign state, country", (), "GE"),
    # Getty TGN's nations, as their records' kinds name TGN's nation type.
    "United States": ("tgn:United States", "nations", ()),
    "Guatemala": ("tgn:7005493", "nations", ()),
    "Honduras": ("tgn:honduras-nation", "nations", ()),
    # Guatemala City as sources._place gives its record: its department Guatemala (tgn:1000621) kept, the
    # nation Guatemala (tgn:7005493) dropped for having that name (Codex's round-2 input).
    "Guatemala City": ("tgn:7005498", "inhabited places, national capitals", (("Guatemala", "tgn:1000621"),)),
    # The department Guatemala's TGN record, its types as tests/fixtures/georeferencing/tgn_records.json gives
    # them: no nation's.
    "Guatemala, department": ("tgn:1000621",
        "departments (political divisions), agricultural land, first level subdivisions (political entities)",
        (("Guatemala", "tgn:7005493"),)),
    # A town whose TGN chain stops short: its response lacked the ancestor row above its county.
    "Partial": ("tgn:partial", "inhabited places", (("Somewhere", "tgn:somewhere-county"),)),
    # TGN's records on 2026-11-14 (G51's round-2 probe): Aurora's preferred parent is Arapahoe County;
    # its non-preferred parent Adams County is not read (georef_tgn: the preferred chain only).
    "Colorado": ("tgn:7007158", "states (political divisions), first level subdivisions (political entities)",
        (US,)),
    "Adams": ("tgn:2000192", COUNTY_KIND, (("Colorado", "tgn:7007158"), US)),
    "Aurora": ("tgn:2015136", "inhabited places", (("Arapahoe", "tgn:2000194"), ("Colorado", "tgn:7007158"), US)),
}
LACKS = FieldAnswer(outcome="label_lacks_value", explanation="Not on the label.")
CANNOT = FieldAnswer(outcome="sources_cannot_resolve", explanation="No source settles it.")


class Places(FakeSources):
    """test_step's FakeSources, whose Getty TGN also answers PLACES."""

    def _answer(self, source_id, query):
        found = PLACES.get(f"{source_id}:{query}") or (PLACES.get(query) if source_id == "tgn" else None)
        if found is None:
            return super()._answer(source_id, query)
        record, kind, parents, *code = found
        raw = json.dumps({"source": source_id, "query": query}).encode()
        # NGA's parent country carries its ISO code (sources._parent); a nation's record carries its own.
        candidate = SourceCandidate(query, record, kind, "in " + ", ".join(name for name, _ in parents) or None,
            tuple(PlaceRef(name, key, ("US" if name == "United States" else name if len(name) == 2 else None)
                if source_id == "nga" else None) for name, key in parents), iso_code=code[0] if code else None)
        evidence = Evidence(kind="authority", source=source_id, locator=record, raw_ref=self.blobs.put(raw),
            digest=hashlib.sha256(raw).hexdigest(), excerpt=f"match\n{query} | {record} | {kind} | {candidate.detail}")
        return SourceAnswer(source_id, query, LookupStatus.SUCCESS, (candidate,), evidence, note="match")


def georgia_and_the_us(task, readings, tools):
    """The country's expert: Getty TGN asked "Georgia" and "United States" (the US state Georgia on the
    label makes the other nation worth asking), then the nation Georgia."""
    async def script():
        georgia = await tools.lookup("tgn", "Georgia", field_key=task.key)
        us = await tools.lookup("tgn", "United States", field_key=task.key)
        return FieldOutcome(task.key, resolved("Georgia", authority_id="tgn:georgia-nation",
            cited=[georgia.evidence.id]), evidence=[georgia.evidence, us.evidence], model_calls=1)
    return script()


def fulton_and_the_us(task, readings, tools):
    """The county's expert: Getty TGN asked "Fulton" and "United States", then Fulton."""
    async def script():
        fulton = await tools.lookup("tgn", "Fulton", field_key=task.key)
        us = await tools.lookup("tgn", "United States", field_key=task.key)
        return FieldOutcome(task.key, resolved("Fulton", authority_id="tgn:Fulton", cited=[fulton.evidence.id]),
            evidence=[fulton.evidence, us.evidence], model_calls=1)
    return script()


FULTON = label_with(country="Georgia", province_state=None, county="Fulton", city=None)


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

def test_a_city_outside_the_settled_county_on_tgn_s_preferred_chain_alone_is_not_marked(tmp_path, first_pass_path):
    """The plan's case: a settled Coles County, then an exact "Chicago" under Illinois, each on its Getty
    TGN record, Chicago's preferred chain Cook, Illinois and the United States. TGN places a place under
    several parents and the records read give its preferred chain alone, so Coles missing from it does not
    show Chicago outside Coles: the check abstains (the coordinator's ruling of round 2, part 2; the plan's
    WP 2.3 row: marked when the record's whole parent set is known). The city settles on both paths."""
    rig = build_rig(tmp_path, label_with(county="Coles"))
    run = rig.specimen.run
    settle(rig, Scripted({"county": tgn("Coles"), "city": tgn("Chicago")}), tools=Places(rig.blobs))

    assert value_of(run, "county")[:2] == (ValueState.SUPPORTED, "Coles")
    assert value_of(run, "city") == (ValueState.SUPPORTED, "Chicago", "Chicago", None, "tgn:Chicago", "settled")
    assert marks(run) == [] and "Marked for a person" not in run.fields["city"].reason


def test_a_city_inside_its_settled_county_is_not_marked(tmp_path, first_pass_path):
    """test_step's synthetic label: Chicago in Cook County, Illinois, United States, each settled on
    Getty TGN's record. Every place lies in those above it: nothing is marked on either path."""
    rig = build_rig(tmp_path)
    run = rig.specimen.run
    settle(rig, Scripted({"city": tgn("Chicago")}), tools=Places(rig.blobs))

    assert [value_of(run, key)[0] for key in agreement.PLACE_ORDER] == [ValueState.SUPPORTED] * 4
    assert marks(run) == []


@pytest.mark.parametrize("shape", ["nga-wikidata-iso", "tgn-nation-looked-up", "tgn"])
def test_a_county_in_a_state_named_as_the_settled_country_is_marked_by_the_check_stage(tmp_path, first_pass_path,
        shape):
    """From WP 2.1's review, round 4: the country Georgia settled, then a county Fulton whose source names
    the US state Georgia. agreement.lies_in matches a parent by name, so the refusal at apply time lets it
    pass on both paths, as today. A place lies in one nation:
    - nga-wikidata-iso: the country settles on Wikidata's nation (P297 GE), Fulton on NGA's record, whose
      country carries US. The codes differ: on the units path the county is marked
      (place_within_settled_places).
    - tgn-nation-looked-up: both are Getty TGN records, Fulton's chain the state Georgia and the United
      States, and the country's expert also asked TGN "United States", whose record's kind is TGN's nation
      type. Fulton's chain reaches a nation the stage knows, another than the settled one: marked.
    - tgn: the same without that lookup. A parent carries no type, so the stage cannot see that Fulton's
      chain reaches its nation, and the check abstains (the coordinator's ruling of round 2)."""
    rig = build_rig(tmp_path, FULTON)
    run = rig.specimen.run
    scripts = {
        "nga-wikidata-iso": {"country": from_tgn("Georgia", "Georgia", None, "wikidata:Q230", source="wikidata"),
            "county": from_tgn("Fulton", "Fulton", None, "nga:fulton", source="nga")},
        "tgn-nation-looked-up": {"country": georgia_and_the_us, "county": tgn("Fulton")},
        "tgn": {"country": tgn("Georgia"), "county": tgn("Fulton")}}[shape]
    settle(rig, Scripted({**scripts, "province_state": answering(LACKS), "city": answering(LACKS)}),
        tools=Places(rig.blobs))

    assert value_of(run, "country")[:2] == (ValueState.SUPPORTED, "Georgia")
    assert value_of(run, "county")[:2] == (ValueState.SUPPORTED, "Fulton")
    if first_pass_path == "units" and shape != "tgn":
        record, country = ("nga:fulton", "wikidata:Q230") if shape == "nga-wikidata-iso" else (
            "tgn:Fulton", "tgn:georgia-nation")
        assert marks(run) == [code(run, "county", "place_within_settled_places")]
        assert code(run, "county", "place_within_settled_places") in run.reasons
        assert run.fields["county"].reason.endswith(
            f"Marked for a person, rule place_within_settled_places: the source's record for 'Fulton' ({record}) "
            f"places it in Georgia, United States, not in the country settled above it, 'Georgia' ({country}).")
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


def test_a_derived_province_on_tgn_s_preferred_chain_alone_is_not_marked(tmp_path, first_pass_path):
    """From WP 2.1's review, round 4: a province text "Cook" unresolved, a settled county Cook in Illinois
    and a settled city Gary in Indiana. Derivation fills the province as Illinois (tgn:Illinois) from the
    county alone (derive._can_derive_place), on both paths, as today. Gary's preferred TGN chain (Lake,
    Indiana, the United States) does not hold it, but a preferred chain alone shows no place outside a
    province: the check abstains (the coordinator's ruling of round 2, part 2)."""
    rig = build_rig(tmp_path, label_with(province_state=None, county="Cook", city="Gary"))
    run = cook_and_gary(rig)

    assert value_of(run, "province_state") == (ValueState.SUPPORTED, None, "Illinois", None, "tgn:Illinois", "derived")
    assert value_of(run, "city")[:2] == (ValueState.SUPPORTED, "Gary")
    assert marks(run) == []
    assert run.fields["province_state"].reason.endswith("Basis: derived, rule place_parents_derived.") == (
        first_pass_path == "units")


def test_a_derived_country_that_a_place_below_it_lies_outside_is_marked(tmp_path, first_pass_path):
    """A derived country fails the place chain: the county Fulton settles on its TGN record (the state
    Georgia, the United States), and the country holds the nation Georgia (tgn:georgia-nation) derived, as
    a derived value of this attempt; the county's expert asked TGN "United States" too, a nation the stage
    knows. The stage, run as apply_outcomes runs it last, marks the derived country (place_parents_derived),
    its reason the derivation's text, its basis, then the mark (round 1, finding 4). apply_outcomes does
    not make this input itself: derive.fill derives a country only from a place's own chain."""
    from specimen_digitization.field_research.ontology_checks import stage

    rig = build_rig(tmp_path, label_with(country=None, province_state=None, county="Fulton", city=None))
    run = rig.specimen.run
    prepared, outcomes, calls = research(rig, Scripted({"country": answering(LACKS),
        "province_state": answering(LACKS), "county": fulton_and_the_us, "city": answering(LACKS)}),
        tools=Places(rig.blobs))
    apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls)
    assert value_of(run, "county")[:2] == (ValueState.SUPPORTED, "Fulton")
    run.fields["country"] = FieldValue(state=ValueState.SUPPORTED, parsed="Georgia", authority_id="tgn:georgia-nation",
        layer="derived", derived_from=["county"], reason="Derived: the settled county authority names this place.")
    received = {}
    for call in calls:
        received.setdefault(call.field_key, []).append(call.answer)
    stage(run, readings=field_step.run_readings(run), received=received, researched=list(run.fields),
        derived=["country"], human=())

    assert marks(run) == [code(run, "country", "place_parents_derived")]
    mark = ("Marked for a person, rule place_parents_derived: this country was derived (tgn:georgia-nation), and the "
        "county settled below it, 'Fulton', lies in Georgia, United States by its source's record (tgn:Fulton), not "
        "in it.")
    assert run.fields["country"].reason == (
        f"Derived: the settled county authority names this place. Basis: derived, rule place_parents_derived. {mark}")


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
        # The finding cites both dates' evidence (G51's N15).
        [finding] = [f for f in run.findings if f.rule_id == STAGE]
        assert set(finding.evidence_ids) == {i for key in ("date_visited_from", "date_identified")
            for i in run.fields[key].evidence_ids} and finding.evidence_ids
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
    ("III-25", "VIII-25 1948", False),
    # A date that punctuation separates from the code beside it (round 1, finding 3).
    ("IV-23-48", "IV-23-48;IV-29-68-4", False), ("IV-23-48", "IV-23-48,IV-29-68-4", False),
    ("IV-23-48", "IV-23-48/IV-29-68-4", False), ("IV-23-48", "IV-29-68-4;IV-23-48", False)])
def test_a_literal_is_in_a_code_only_inside_a_match_of_the_ontology_s_slide_code(literal, text, inside):
    assert checks.in_a_code(literal, text) is inside


@pytest.mark.parametrize("separator", [";", ",", "/"])
def test_a_date_punctuation_separates_from_a_slide_code_is_a_date_on_both_paths(first_pass_path, separator):
    """Round 1 of #436, finding 3: "IV-23-48;IV-29-68-4" writes a collecting date, then a slide code. The
    date settles on both paths; on the units path the veto names only a literal inside the code."""
    text = f"Guatemala IV-23-48{separator}IV-29-68-4"
    result = checks.parse_date("IV-23-48", reading_texts=[text, text], date_rules=PILOT_DATES,
        units=first_pass_path == "units")
    assert (result.status, result.values) == (LookupStatus.SUCCESS, ("1948-04-23",))
    inside = checks.parse_date("IV-29-68", reading_texts=[text, text], date_rules=PILOT_DATES,
        units=first_pass_path == "units")
    assert (inside.status, inside.values) == (LookupStatus.NO_MATCH, ())


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
    """The stage run again over the Georgia/Fulton label (the country's expert asked TGN "United States"
    too) and a determination dated a day before the collecting date: every value but its reason stays as
    it was, and no mark is made twice. A person's value is never marked: with the county and the
    determination date a person's (step.human_keys), the collecting date is marked instead, and the county
    is not."""
    from specimen_digitization.field_research.ontology_checks import stage

    rig = build_rig(tmp_path, label_with(country="Georgia", province_state=None, county="Fulton", city=None,
        date_visited_from="1946-09-06", date_identified="1946-09-05"))
    run = rig.specimen.run
    prepared, outcomes, calls = research(rig, Scripted({"country": georgia_and_the_us, "county": tgn("Fulton"),
        "province_state": answering(LACKS), "city": answering(LACKS),
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
    assert sorted(again) == sorted([code(run, "county", "place_within_settled_places"),
        code(run, "date_identified", "date_order")])
    assert [f for f in run.findings if f.rule_id != STAGE] == [f for f in findings if f.rule_id != STAGE]
    assert len(marks(run)) == 2
    # A field this attempt did not research keeps its mark, and it is not made again.
    stage(run, readings=readings, received=received, researched=[], derived=[], human=())
    assert marks(run) == sorted(again)

    stage(run, readings=readings, received=received, researched=list(run.fields), derived=[],
        human={"county", "date_identified"})
    assert marks(run) == [code(run, "date_visited_from", "date_order")]
    assert {key: value.model_dump(exclude={"reason"}) for key, value in run.fields.items()} == before


# ---- round 1 of #436's review --------------------------------------------------------------

def test_a_persons_derived_place_is_never_marked_the_place_below_it_is(tmp_path, first_pass_path):
    """Round 1, finding 2: a person kept a derived country Georgia (tgn:georgia-nation; a field review
    accepts a derived value, application/api.py, and human_field_carry carries it), and a county Fulton
    then settles on its TGN record (the state Georgia, the United States), its expert having asked TGN
    "United States", a nation the stage knows. apply_outcomes lets Fulton pass by name. The person's
    country is not marked, whatever its layer; on the units path the county is
    (place_within_settled_places). On the old path nothing is marked."""
    from specimen_digitization.application.human_field_carry import KEY

    rig = build_rig(tmp_path, FULTON)
    run = rig.specimen.run
    kept = FieldValue(state=ValueState.SUPPORTED, parsed="Georgia", authority_id="tgn:georgia-nation",
        layer="derived", derived_from=["province_state"], reason="A person kept this country.")
    run.fields["country"] = kept
    run.dependencies[KEY] = {"country": {"reviewed": True}}
    assert field_step.human_keys(run) == {"country"}
    prepared, outcomes, calls = research(rig, Scripted({"province_state": answering(LACKS),
        "county": fulton_and_the_us, "city": answering(LACKS)}), tools=Places(rig.blobs))
    apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls)

    assert run.fields["country"] == kept
    assert value_of(run, "county")[:2] == (ValueState.SUPPORTED, "Fulton")
    assert marks(run) == ([code(run, "county", "place_within_settled_places")] if first_pass_path == "units" else [])


COLES_ATTEMPT = label_with(county="Coles")


def two_attempts(rig, tools, county, city, **scripts):
    """Attempt 1 settles the country, the province and the city `city` while the county stays
    unresolved; attempt 2 researches what is left and settles the county `county`. The city is not
    researched again (step.build_tasks leaves a settled field out), so attempt 2 receives no answer
    for it."""
    run = rig.specimen.run
    first = Scripted({"county": answering(CANNOT), "city": city, **scripts})
    prepared, outcomes, calls = research(rig, first, tools=tools())
    apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls)
    assert run.fields["city"].state == ValueState.SUPPORTED and run.fields["county"].state != ValueState.SUPPORTED
    prepared, outcomes, calls = research(rig, Scripted({"county": county}), tools=tools())
    assert "city" not in {task.key for task in prepared[1]} and "city" not in {call.field_key for call in calls}
    apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls)
    assert run.fields["county"].state == ValueState.SUPPORTED
    return run


def test_a_retry_checks_a_place_an_earlier_attempt_settled_on_its_stored_record(tmp_path, monkeypatch,
        first_pass_path):
    """Round 1, finding 1, on responses as the sources store them (test_agreement.Recorded): attempt 1
    settles the city Chimaltenango on Getty TGN's town (tgn:1016636, recorded: its chain the department
    Chimaltenango, tgn:1000565, and the nation Guatemala, tgn:7005493), while the country "Honduras", which
    only a second label writes, stays unresolved. Attempt 2 settles that country on a TGN nation; its
    expert asked TGN "Guatemala" too, so the stage knows tgn:7005493 is a nation. The city is not
    researched again. Its record, read again from the record's blob store
    (ontology_checks.stored_answers), ends at the nation Guatemala, another than the settled Honduras: on
    the units path the city is marked (place_within_settled_places). On the old path nothing is marked."""
    from test_agreement import Recorded

    a_second_label(monkeypatch, "Honduras")
    rig = build_rig(tmp_path, label_with(country=None, province_state=None, county=None, city="Chimaltenango"),
        candidates=[*COLLECTORS, *(("country", name, "Honduras", "Honduras") for name in ("2A", "2B"))])
    run = rig.specimen.run
    nations = [("tgn", name, [(name, PLACES[name][0], "nations", ())]) for name in ("Honduras", "Guatemala")]
    tools = lambda: Recorded(rig.blobs, nations)  # noqa: E731
    prepared, outcomes, calls = research(rig, Scripted({"country": answering(CANNOT),
        "province_state": answering(LACKS), "county": answering(LACKS),
        "city": from_tgn("Chimaltenango", "Chimaltenango", None, "tgn:1016636")}), tools=tools())
    apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls)
    assert value_of(run, "city")[:2] == (ValueState.SUPPORTED, "Chimaltenango")
    assert run.fields["country"].state != ValueState.SUPPORTED and marks(run) == []

    async def honduras(task, readings, tools):
        answer = await tools.lookup("tgn", "Honduras", field_key=task.key)
        other = await tools.lookup("tgn", "Guatemala", field_key=task.key)
        return FieldOutcome(task.key, resolved("Honduras", authority_id="tgn:honduras-nation",
            cited=[answer.evidence.id], reading="2A"), evidence=[answer.evidence, other.evidence], model_calls=1)

    prepared, outcomes, calls = research(rig, Scripted({"country": honduras}), tools=tools())
    assert "city" not in {task.key for task in prepared[1]} | {call.field_key for call in calls}
    apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls)

    assert value_of(run, "country")[:2] == (ValueState.SUPPORTED, "Honduras")
    if first_pass_path == "units":
        assert marks(run) == [code(run, "city", "place_within_settled_places")]
        assert run.fields["city"].reason.endswith(
            "Marked for a person, rule place_within_settled_places: the source's record for 'Chimaltenango' "
            "(tgn:1016636) places it in Chimaltenango, Guatemala, not in the country settled above it, "
            "'Honduras' (tgn:honduras-nation).")
        [finding] = [f for f in run.findings if f.rule_id == STAGE]
        # The finding cites the city's stored record and the country's evidence.
        assert set(run.fields["city"].evidence_ids) | set(run.fields["country"].evidence_ids) == set(
            finding.evidence_ids)
    else:
        assert marks(run) == []


def test_a_retry_abstains_on_a_place_whose_earlier_record_cannot_be_read_again(tmp_path, first_pass_path):
    """Round 1, finding 1, the coordinator's input: attempt 1 settles the United States, Illinois and
    Chicago, the county unresolved; attempt 2 settles only Coles County. test_step's sources store no
    response a lookup could be asked again from, so Chicago's record cannot be read again: the
    check abstains (the coordinator's ruling of round 1, part 2: a place check marks only a certain
    conflict) and the stage counts the record not read again. Nothing is marked on either path."""
    from specimen_digitization.field_research.ontology_checks import stage

    rig = build_rig(tmp_path, COLES_ATTEMPT)
    run = two_attempts(rig, lambda: Places(rig.blobs), county=tgn("Coles"), city=tgn("Chicago"))

    assert marks(run) == []
    tally = Counter()
    stage(run, readings=field_step.run_readings(run), received={}, researched=["county"], derived=[], human=(),
        blobs=rig.blobs, tally=tally)
    assert marks(run) == [] and tally["place:records_not_read_again"] >= 1


# ---- round 1 of #436's review, part 2 (G51; the coordinator's ruling: a place check marks only a
# certain conflict, and abstains without an identity both records carry) -----------------------

@pytest.mark.parametrize("county", ["tgn", "nga"])
def test_a_city_in_another_county_of_the_settled_county_s_name_is_not_marked(tmp_path, first_pass_path, county):
    """G51's B4: the county Lake settles on Lake County, Illinois (TGN's record, or NGA's), and the city Gary
    on its TGN record, whose preferred chain holds Lake County, Indiana (another record of that name),
    Indiana and the United States. A name is never the place, and a preferred chain alone shows no place
    outside a county: the check abstains in both shapes (the coordinator's ruling of round 2, part 2)."""
    rig = build_rig(tmp_path, label_with(province_state=None, county="Lake", city="Gary"))
    run = rig.specimen.run
    script = tgn("Lake") if county == "tgn" else from_tgn("Lake", "Lake", None, "nga:lake-il", source="nga")
    settle(rig, Scripted({"province_state": answering(LACKS), "county": script, "city": tgn("Gary")}),
        tools=Places(rig.blobs))

    assert value_of(run, "county")[:2] == (ValueState.SUPPORTED, "Lake")
    assert value_of(run, "city")[:2] == (ValueState.SUPPORTED, "Gary")
    assert marks(run) == []


def test_the_lake_gary_derived_province_is_not_marked(tmp_path, first_pass_path):
    """G51's B4, the plan's Cook/Gary case with Lake County, Illinois in place of Cook County: the province
    "Lake" unresolved, derived as Illinois (tgn:Illinois) from the county. A preferred chain alone shows no
    place outside a province or a county: nothing is marked."""
    rig = build_rig(tmp_path, label_with(province_state=None, county="Lake", city="Gary"))
    run = rig.specimen.run
    run.fields["province_state"] = FieldValue(state=ValueState.UNRESOLVED, literal="Lake",
        reason="No source settles the province.")
    prepared, outcomes, calls = research(rig, Scripted({"county": tgn("Lake"), "city": tgn("Gary")}),
        tools=Places(rig.blobs))
    keep = {"country", "county", "city"}
    apply_outcomes(run, None, [task for task in prepared[1] if task.key in keep],
        [outcome for outcome in outcomes if outcome.key in keep], blobs=rig.blobs,
        calls=[call for call in calls if call.field_key in keep])

    assert value_of(run, "province_state")[2:] == ("Illinois", None, "tgn:Illinois", "derived")
    assert marks(run) == []


def test_aurora_in_adams_county_is_not_marked(tmp_path, first_pass_path):
    """G51's round-2 B1: TGN is polyhierarchical. Aurora (tgn:2015136) has the preferred parent Arapahoe
    County and the non-preferred parent Adams County (tgn:2000192); the record read gives the preferred chain
    alone (georef_tgn). "United States / Colorado / Adams / Aurora": every place settles on its TGN record, and
    Adams missing from Aurora's preferred chain marks nothing."""
    rig = build_rig(tmp_path, label_with(country="United States", province_state="Colorado", county="Adams",
        city="Aurora"))
    run = rig.specimen.run
    settle(rig, Scripted({key: tgn(name) for key, name in (("country", "United States"),
        ("province_state", "Colorado"), ("county", "Adams"), ("city", "Aurora"))}), tools=Places(rig.blobs))

    assert [value_of(run, key)[0] for key in agreement.PLACE_ORDER] == [ValueState.SUPPORTED] * 4
    assert marks(run) == []


@pytest.mark.parametrize(("source", "authority"), [("wikidata", "wikidata:Q1523937"), ("nga", "nga:-1143758")],
    ids=["wikidata-municipio", "nga-municipio"])
def test_105526329_without_its_department_line_is_not_marked(tmp_path, first_pass_path, source, authority):
    """G51's B2: 105526329's label with its department line left out, read through the recorded
    gazetteers (test_agreement.Recorded). The county settles on the municipio Yepocapa (Wikidata's or
    NGA's), the city on NGA's town Yepocapa, whose parents are named only (Chimaltenango, GT). The
    records carry no identity both can compare, so the check abstains on both paths."""
    from test_agreement import PLACES_329, Recorded

    text = label_with(country=None, province_state=None, county=None, city=None) + "\nYepocapa, 4800ft\nGuatemala"
    rig = build_rig(tmp_path, text)
    run = rig.specimen.run
    settle(rig, Scripted({"country": PLACES_329["country"], "city": PLACES_329["city"],
        "province_state": answering(LACKS), "county": from_tgn("Yepocapa", "Yepocapa", None, authority, source=source)}),
        tools=Recorded(rig.blobs))

    assert [value_of(run, key)[0] for key in ("country", "county", "city")] == [ValueState.SUPPORTED] * 3
    assert marks(run) == []


def test_a_country_on_one_label_and_an_nga_town_on_another_is_not_marked(tmp_path, monkeypatch, first_pass_path):
    """G51's B3: label 1's country Guatemala settles on Getty TGN's nation (tgn:7005493, which carries no
    ISO code); label 2 writes only "Yepocapa", and the city settles on NGA's town (Chimaltenango, GT).
    The two records share no identity (no record id, one ISO code only): the check abstains."""
    from test_agreement import PLACES_329, Recorded

    a_second_label(monkeypatch, "Yepocapa")
    rig = build_rig(tmp_path, label_with(country="Guatemala", province_state=None, county=None, city=None))
    run = rig.specimen.run

    async def city(task, readings, tools):
        answer = await tools.lookup("nga", "Yepocapa", field_key=task.key)
        return FieldOutcome(task.key, resolved("Yepocapa", authority_id="nga:-1143757", cited=[answer.evidence.id],
            reading="2A"), evidence=[answer.evidence], model_calls=1)

    settle(rig, Scripted({"country": from_tgn("Guatemala", "Guatemala", None, "tgn:7005493"),
        "province_state": answering(LACKS), "county": answering(LACKS), "city": city}),
        tools=Recorded(rig.blobs, [("tgn", "Guatemala", [("Guatemala", "tgn:7005493", "nations", ())])]))

    assert [value_of(run, key)[:2] for key in ("country", "city")] == [
        (ValueState.SUPPORTED, "Guatemala"), (ValueState.SUPPORTED, "Yepocapa")]
    assert PLACES_329 and marks(run) == []


@pytest.mark.parametrize(("texts", "date"), [
    (["Guatemala IV-29-68-4,IV-23-48"] * 2, True), (["IV-29-68-4;IV-23-48"] * 2, True),
    (["IV-23-48;IV-29-68-4"] * 2, True), (["IV-23-48,IV-29-68-4"] * 2, True),
    (["IV-29-68-4,IV-23-48", "IV-29-68-4, IV-23-48"], True),
    # Which occurrence counts: any reading's any occurrence inside a code (the rule's "any reading").
    (["IV-23-48 IV-23-48-4"] * 2, False), (["IV-23-48-4 IV-23-48"] * 2, False),
    (["IV-23-48", "IV-23-48-4"], False)],
    ids=["comma-code-first", "semicolon-code-first", "semicolon-date-first", "comma-date-first", "one-reader-spaced",
        "code-second", "code-first", "code-in-the-other-reading"])
def test_the_code_veto_takes_each_occurrence_of_the_literal(first_pass_path, texts, date):
    """G51's B1: a date punctuation separates from a slide code is a date, the code first or last, in one
    reader or both. A literal one of whose occurrences, in any reading, lies inside a slide code's match is
    no date on the units path (G51's N14: not only its first occurrence). The old path gives main's
    result: a date, except where the date parser's own code veto sees the code (checks._date_check)."""
    units = first_pass_path == "units"
    result = checks.parse_date("IV-23-48", reading_texts=texts, date_rules=PILOT_DATES, units=units)
    if units:
        assert (result.status == LookupStatus.SUCCESS) is date
        assert result.values == (("1948-04-23",) if date else ())
    elif date:
        assert (result.status, result.values) == (LookupStatus.SUCCESS, ("1948-04-23",))


# ---- retries, reassessment and a person's value, through apply_outcomes (G51's B5) -----------

def fulton_and_a_failed_habitat(rig, **scripts):
    """Attempt 1 marks the county (Georgia/Fulton, the country's expert asking TGN "United States" too) on the
    units path, and the habitat's research fails."""
    from test_step import failing

    run = rig.specimen.run
    prepared, outcomes, calls = research(rig, Scripted({"country": georgia_and_the_us, "county": tgn("Fulton"),
        "province_state": answering(LACKS), "city": answering(LACKS), "habitat": failing("timeout"), **scripts}),
        tools=Places(rig.blobs))
    apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls)
    return run, prepared


def test_a_plain_retry_keeps_the_marks_of_fields_it_does_not_research(tmp_path, first_pass_path):
    """G51's N16: attempt 2 researches only the habitat, whose attempt 1 failed. The county's mark of attempt
    1 stays, though attempt 2 receives no answer for the county (test_step's sources store no response it
    could be read again from, so the stage abstains on it there)."""
    rig = build_rig(tmp_path, FULTON)
    run, _ = fulton_and_a_failed_habitat(rig)
    first = marks(run)
    assert first == ([code(run, "county", "place_within_settled_places")] if first_pass_path == "units" else [])
    prepared, outcomes, calls = research(rig, Scripted({"city": answering(LACKS), "province_state": answering(LACKS)}),
        tools=Places(rig.blobs))
    assert "habitat" in {task.key for task in prepared[1]} and "county" not in {task.key for task in prepared[1]}
    apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls)
    assert run.fields["habitat"].state == ValueState.SUPPORTED
    assert marks(run) == first


def test_a_reassessment_that_researches_a_marked_field_again_drops_its_stale_mark(tmp_path, first_pass_path):
    """G51's N2: a same-run reassessment researches the marked county again (location_reassessment), and its
    expert now finds no county on the label. The county's earlier mark goes with it."""
    rig = build_rig(tmp_path, FULTON)
    run, prepared = fulton_and_a_failed_habitat(rig)
    assert len(marks(run)) == (1 if first_pass_path == "units" else 0)
    [task] = [task for task in prepared[1] if task.key == "county"]
    apply_outcomes(run, None, [task], [FieldOutcome("county", LACKS, model_calls=1)], blobs=rig.blobs, calls=[])
    assert run.fields["county"].state == ValueState.NOT_PRESENT
    assert marks(run) == [] and not any(":county:" in reason for reason in field_step.marked_reasons(run))


def test_a_retry_adds_the_date_sentence_once(tmp_path, first_pass_path):
    """G51's N4: both dates are checked on every attempt; the determination's sentence is in its reason once
    after a retry."""
    rig = build_rig(tmp_path, label_with(country="Georgia", province_state=None, county="Fulton", city=None,
        date_visited_from="1946-09-06", date_identified="1946-09-05"))
    run, _ = fulton_and_a_failed_habitat(rig, date_visited_from=answering(resolved("1946-09-06")),
        date_identified=answering(resolved("1946-09-05")))
    prepared, outcomes, calls = research(rig, Scripted(), tools=Places(rig.blobs))
    apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls)
    sentence = "Marked for a person, rule date_order: the determination date 1946-09-05 is before the collecting date"
    assert run.fields["date_identified"].reason.count(sentence) == (1 if first_pass_path == "units" else 0)


def test_a_persons_value_with_no_layer_is_not_checked(tmp_path, first_pass_path):
    """G51's N6: a person's field decision from the app carries no layer (api.py's field review). A person's
    country Georgia (the nation's TGN record) above a county Fulton of the US state Georgia, whose expert asked
    TGN "United States" too, and a person's determination date before the collecting date: the stage checks
    neither, on either path."""
    from specimen_digitization.application.human_field_carry import KEY

    rig = build_rig(tmp_path, label_with(country="Georgia", province_state=None, county="Fulton", city=None,
        date_visited_from="1946-09-06", date_identified="1946-09-05"))
    run = rig.specimen.run
    run.fields["country"] = FieldValue(state=ValueState.SUPPORTED, literal="Georgia", authority_id="tgn:georgia-nation",
        reason="A person's decision.")
    run.fields["date_identified"] = FieldValue(state=ValueState.SUPPORTED, literal="1946-09-05", parsed="1946-09-05",
        reason="A person's decision.")
    run.dependencies[KEY] = {"country": {}, "date_identified": {}}
    prepared, outcomes, calls = research(rig, Scripted({"province_state": answering(LACKS), "county": fulton_and_the_us,
        "city": answering(LACKS), "date_visited_from": answering(resolved("1946-09-06"))}), tools=Places(rig.blobs))
    apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls)

    assert value_of(run, "county")[:2] == (ValueState.SUPPORTED, "Fulton")
    assert marks(run) == []


@pytest.mark.parametrize(("town", "marked"), [("Tapachula", True), ("Yepocapa", False)], ids=["codes-differ", "codes-agree"])
def test_a_country_and_a_town_on_two_labels_are_compared_by_their_iso_codes(tmp_path, monkeypatch, first_pass_path,
        town, marked):
    """The country Guatemala settles on NGA's nation, whose record carries GT; a second label writes only a
    town, which settles on NGA's record naming its country by code. Apply time does not hold the town to a
    country its reading does not write. Both records state an ISO 3166-1 code: Tapachula's MX is not GT, and
    on the units path the city is marked (place_within_settled_places); Yepocapa's GT is, and nothing is."""
    a_second_label(monkeypatch, town)
    rig = build_rig(tmp_path, label_with(country="Guatemala", province_state=None, county=None, city=None))
    run = rig.specimen.run

    async def city(task, readings, tools):
        answer = await tools.lookup("nga", town, field_key=task.key)
        return FieldOutcome(task.key, resolved(town, authority_id=PLACES[f"nga:{town}"][0], cited=[answer.evidence.id],
            reading="2A"), evidence=[answer.evidence], model_calls=1)

    settle(rig, Scripted({"country": from_tgn("Guatemala", "Guatemala", None, "nga:-1135822", source="nga"),
        "province_state": answering(LACKS), "county": answering(LACKS), "city": city}), tools=Places(rig.blobs))

    assert [value_of(run, key)[:2] for key in ("country", "city")] == [
        (ValueState.SUPPORTED, "Guatemala"), (ValueState.SUPPORTED, town)]
    # The town is the second label's.
    assert marks(run) == ([field_step.marked_code("city", run.regions[1].id, "place_within_settled_places")]
        if marked and first_pass_path == "units" else [])



# ---- round 2 of #436's review (Codex and G51 on 48cfbfa87; the coordinator's rulings: a TGN chain is taken
# to reach its nation only when proven, and below the country a check is inside or abstains) -------------

def city_on_a_second_label(rig, town):
    async def city(task, readings, tools):
        answer = await tools.lookup("tgn", town, field_key=task.key)
        return FieldOutcome(task.key, resolved(town, authority_id=PLACES[town][0], cited=[answer.evidence.id],
            reading="2A"), evidence=[answer.evidence], model_calls=1)
    return city


@pytest.mark.parametrize("town", ["Guatemala City", "Partial"])
def test_a_tgn_chain_not_known_to_reach_its_nation_abstains(tmp_path, monkeypatch, first_pass_path, town):
    """Codex's round-2 finding 1. Label 1's country settles on Getty TGN's nation; a second label writes only
    a town, which settles on its TGN record, its chain not ending at a nation the stage knows:
    - Guatemala City (tgn:7005498): sources._place keeps the department Guatemala (tgn:1000621) and drops the
      nation Guatemala (tgn:7005493), whose name another parent has;
    - Partial: its response lacked an ancestor row, and georef_tgn._place stopped the chain there.
    Either chain may be cut short: the check abstains, on both paths."""
    a_second_label(monkeypatch, town)
    country = "Guatemala" if town == "Guatemala City" else "United States"
    rig = build_rig(tmp_path, label_with(country=country, province_state=None, county=None, city=None))
    run = rig.specimen.run
    settle(rig, Scripted({"country": tgn(country), "province_state": answering(LACKS), "county": answering(LACKS),
        "city": city_on_a_second_label(rig, town)}), tools=Places(rig.blobs))

    assert [value_of(run, key)[:2] for key in ("country", "city")] == [
        (ValueState.SUPPORTED, country), (ValueState.SUPPORTED, town)]
    assert marks(run) == []


def mckinley(rig):
    """A TGN lookup of "Mount McKinley" as Recorded stores it, made by the precise location's expert; the
    run's row and call for it."""
    from test_agreement import Recorded

    run = rig.specimen.run

    async def looked_up(task, readings, tools):
        answer = await tools.lookup("tgn", "Mount McKinley", field_key=task.key)
        return FieldOutcome(task.key, LACKS, evidence=[answer.evidence], model_calls=1)

    prepared, outcomes, calls = research(rig, Scripted({"precise_location": looked_up}), tools=Recorded(rig.blobs))
    apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls)
    [row] = [row for row in run.evidence if row.source == "tgn" and "McKinley" in row.excerpt]
    [made] = [call for call in run.tool_calls if call.evidence_id == row.id]
    return run, row, made


def a_row_with_other_responses(rig, run, row, made, edit):
    """Another row of the same lookup: `row`'s stored record with each response edited by `edit`."""
    record = json.loads(rig.blobs.get(row.raw_ref))
    for exchange in record["exchanges"]:
        exchange["raw_ref"] = rig.blobs.put(edit(rig.blobs.get(exchange["raw_ref"])))
    raw = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    other = row.model_copy(update={"id": "other-" + row.id, "raw_ref": rig.blobs.put(raw),
        "digest": hashlib.sha256(raw).hexdigest()})
    run.evidence.append(other)
    run.tool_calls.append(made.model_copy(update={"evidence_id": other.id, "call_key": made.call_key + ":other"}))
    return other


def test_a_stored_row_is_rebuilt_only_from_its_own_responses(tmp_path, first_pass_path):
    """Codex's round-2 finding 2: two evidence rows of one TGN lookup, the same request URLs, whose responses
    differ only in the record of Mount McKinley's (tgn:1105587) nation: E1 (as recorded) the United States,
    tgn:7012149; E2 tgn:7012148. Their excerpts are equal (an excerpt names no parent's record). Each row is
    rebuilt from its own responses, with a lookup cache of its own: E1 keeps tgn:7012149, E2 tgn:7012148. The
    place settled on E1 lies in the settled country tgn:7012149, though tgn:7012148 is a nation the stage
    knows: no mark."""
    from specimen_digitization.field_research.ontology_checks import stage, stored_answers

    rig = build_rig(tmp_path)
    run, first, made = mckinley(rig)
    second = a_row_with_other_responses(rig, run, first, made, lambda body: body.replace(b"7012149", b"7012148"))

    found = {answer.evidence.id: answer for answer in stored_answers(run, rig.blobs, [first.id, second.id])[0]}
    nation = {row: next(c for c in found[row].candidates if c.authority_id == "tgn:1105587").parents[-1].authority_id
        for row in (first.id, second.id)}
    assert nation == {first.id: "tgn:7012149", second.id: "tgn:7012148"}

    run.fields["country"] = FieldValue(state=ValueState.SUPPORTED, literal="United States", parsed="United States",
        authority_id="tgn:7012149", evidence_ids=[second.id], layer="settled")
    for key in ("province_state", "county"):
        run.fields[key] = FieldValue(state=ValueState.NOT_PRESENT)
    run.fields["city"] = FieldValue(state=ValueState.SUPPORTED, literal="McKinley", parsed="McKinley, Mount",
        authority_id="tgn:1105587", evidence_ids=[first.id], layer="settled")
    raw = b"another nation"
    other_nation = SourceAnswer("tgn", "Atlantis", LookupStatus.SUCCESS, (SourceCandidate("Atlantis", "tgn:7012148",
        "nations"),), Evidence(kind="authority", source="tgn", locator="tgn:7012148", excerpt="match",
        raw_ref=rig.blobs.put(raw), digest=hashlib.sha256(raw).hexdigest()))
    run.findings[:] = [f for f in run.findings if f.rule_id != STAGE]
    stage(run, readings=field_step.run_readings(run), received={"country": [other_nation]},
        researched=list(run.fields), derived=[], human=(), blobs=rig.blobs)
    assert marks(run) == []


def test_a_stored_row_is_read_again_only_from_a_lookup_that_gives_its_excerpt(tmp_path, first_pass_path):
    """G51's round-2 B2: a rebuilt answer counts only when its excerpt is the row's. The row read again as
    stored; then with its excerpt changed; then with its stored responses swapped for an empty answer:
    neither later row is read again. And only a TGN, Wikidata or NGA lookup row (kind "authority") made by
    a call of its own source is read again."""
    from specimen_digitization.field_research.ontology_checks import stored_answers

    rig = build_rig(tmp_path)
    run, row, made = mckinley(rig)
    answers, missing = stored_answers(run, rig.blobs, [row.id])
    assert [answer.evidence.id for answer in answers] == [row.id] and not missing

    changed = row.model_copy(update={"id": "changed", "excerpt": row.excerpt.replace("McKinley", "McKinlay", 1)})
    run.evidence.append(changed)
    run.tool_calls.append(made.model_copy(update={"evidence_id": changed.id, "call_key": made.call_key + ":c"}))
    swapped = a_row_with_other_responses(rig, run, row, made, lambda body: b'{"results": {"bindings": []}}')
    elsewhere = row.model_copy(update={"id": "elsewhere"})
    run.evidence.append(elsewhere)
    run.tool_calls.append(made.model_copy(update={"evidence_id": elsewhere.id, "call_key": made.call_key + ":w",
        "source": "wikidata", "tool": "wikidata"}))
    looked = row.model_copy(update={"id": "looked", "kind": "lookup"})
    run.evidence.append(looked)
    run.tool_calls.append(made.model_copy(update={"evidence_id": looked.id, "call_key": made.call_key + ":l"}))
    answers, missing = stored_answers(run, rig.blobs, [changed.id, swapped.id, elsewhere.id, looked.id])
    assert answers == [] and missing == {changed.id, swapped.id, elsewhere.id}


def test_fits_decides_by_ids_and_codes_and_abstains_otherwise():
    """ontology_checks.fits on made-up records: inside by a parent's record or the same ISO code; outside
    only at the country, by different codes or two TGN nations' records the stage knows; abstaining below
    the country, on a TGN chain not ending at a known nation, and on a chain holding a parent of another
    gazetteer."""
    from specimen_digitization.field_research.agreement import PlaceField
    from specimen_digitization.field_research.ontology_checks import fits

    def record(*parents):
        return SourceCandidate("Town", "tgn:town", "inhabited places", parents=tuple(PlaceRef(*p) for p in parents))

    nation = PlaceField((), "tgn:A")
    chain = record(("County", "tgn:county"), ("Nation B", "tgn:B"))
    assert fits(chain, "country", nation, {"tgn:A", "tgn:B"}) is False
    assert fits(chain, "country", nation, {"tgn:A"}) is None
    assert fits(chain, "country", PlaceField((), "tgn:B"), {"tgn:B"}) is True
    assert fits(record(("County", "tgn:county"), ("Nation B", None)), "country", nation, {"tgn:A", "tgn:B"}) is None
    # A chain holding a parent of another gazetteer is not TGN's chain (G51's R7).
    assert fits(record(("County", "nga:county"), ("Nation B", "tgn:B")), "country", nation, {"tgn:A", "tgn:B"}) is None
    assert fits(chain, "province_state", PlaceField((), "tgn:province"), {"tgn:A", "tgn:B"}) is None
    assert fits(chain, "county", PlaceField((), "tgn:county"), ()) is True
    coded = record(("County", None), ("GT", None, "GT"))
    assert fits(coded, "country", PlaceField((), "nga:gt", "GT"), ()) is True
    assert fits(coded, "country", PlaceField((), "wikidata:Q783", "HN"), ()) is False
    assert fits(coded, "country", PlaceField((), "tgn:7005493"), ()) is None



def test_a_tgn_record_the_stage_holds_is_a_nation_only_by_tgn_s_nation_type(tmp_path, monkeypatch, first_pass_path):
    """Codex's round-3 finding 1: Guatemala City (tgn:7005498) with its department Guatemala (tgn:1000621) as
    its one parent, the country Guatemala settled on tgn:7005493, and the city's expert also holding TGN's
    record of that department (its types first-level subdivision, department, agricultural land:
    tgn_records.json). A record the stage holds is a nation only when its kinds name TGN's nation type
    (ontology_checks.tgn_nations), so the department is none and the chain is not known to reach its
    nation: the check abstains, on both paths."""
    from specimen_digitization.field_research.ontology_checks import tgn_nations

    a_second_label(monkeypatch, "Guatemala City")
    rig = build_rig(tmp_path, label_with(country="Guatemala", province_state=None, county=None, city=None))
    run = rig.specimen.run

    async def city(task, readings, tools):
        answer = await tools.lookup("tgn", "Guatemala City", field_key=task.key)
        department = await tools.lookup("tgn", "Guatemala, department", field_key=task.key)
        return FieldOutcome(task.key, resolved("Guatemala City", authority_id="tgn:7005498", cited=[answer.evidence.id],
            reading="2A"), evidence=[answer.evidence, department.evidence], model_calls=1)

    settle(rig, Scripted({"country": tgn("Guatemala"), "province_state": answering(LACKS), "county": answering(LACKS),
        "city": city}), tools=Places(rig.blobs))

    assert [value_of(run, key)[:2] for key in ("country", "city")] == [
        (ValueState.SUPPORTED, "Guatemala"), (ValueState.SUPPORTED, "Guatemala City")]
    assert marks(run) == []
    # The department's record, as the city's expert held it, names no nation's type.
    assert tgn_nations([Places(rig.blobs)._answer("tgn", "Guatemala, department")]) == frozenset()
