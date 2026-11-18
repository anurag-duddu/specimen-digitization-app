"""Autonomy program, work package S1 (docs/execution/autonomy/PLAN.md): the holds the free replay R0
measured as rule mechanics, not doubt, removed, and the holds that guard a real conflict kept.

- C3: a label's unresolved_transcription no longer repeats a field cleared as not on the label or a
  field waiting for a held source; a label no field is drawn from is held only while a field the
  organiser found text for on it is.
- C4: a place's literal over one line break is the same text as with a space (C4a); a precise location
  keeps the elevation whose number its elevation field settled (C4b, in test_elevations_and_extent);
  a place below the country settles inside the country settled from another reading of its label
  (C4c); an expert whose request its sources made too long answers on a shortened one (C4d).
- The empty-record guard: a record with no value in any field is never finished without a person.
"""

from __future__ import annotations

import asyncio

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from test_step import (
    LABEL,
    SMITH_OR_SMYTH,
    SMYTH,
    TEXT,
    TODAY,
    DavaoProvince,
    Scripted,
    answering,
    build_rig,
    every_field,
    label_with,
    settle,
)

from specimen_digitization.application.domain import (
    Disposition,
    Evidence,
    FieldValue,
    LookupStatus,
    ValueState,
)
from specimen_digitization.field_research import agreement, budget, experts
from specimen_digitization.field_research import step as field_step
from specimen_digitization.field_research.contracts import (
    FIELD_TOOLS,
    FieldAnswer,
    FieldOutcome,
    FieldTask,
    Reading,
    SourceAnswer,
    SourceCandidate,
)

LACKS = FieldAnswer(outcome="label_lacks_value", explanation="Not on the label.")


def unresolved_labels(run):
    return [reason for reason in run.reasons if reason.startswith("unresolved_transcription:")]


# ---- C3: the label's hold repeats no field's -------------------------------------------------------

# The synthetic label without its county and city lines; reader 1B writes the slide's own code
# differently on a line no field holds (as R0's labels write a slide code), so its transcript is open;
# a line both write sits between it and the collectors' line, which the image test's neighbour guard
# would otherwise leave text_only.
NO_COUNTY = label_with(county=None, city=None) + "\nslide\n10-6-78-1a"
NO_COUNTY_OTHER = label_with(county=None, city=None) + "\nslide\n10-6-78-la"
# The organiser offers the county the province's text (as on 105526324, whose county is "Davao Prov.").
COUNTY_IS_THE_PROVINCE = every_field(*(("county", name, "Illinois", "province_state: Illinois")
    for name in ("1A", "1B")), *(("city", name, "Illinois", "province_state: Illinois") for name in ("1A", "1B")))


def test_a_county_cleared_as_not_on_the_label_no_longer_holds_its_label(tmp_path):
    """R0's standalone case (4 specimens a run): the county and the city, whose only organiser text is
    the settled province's, clear as not on the label (owner decision A); the readers differ on a line
    no field holds. On main the label still went to review (unresolved_transcription), the county
    not being SUPPORTED; now nothing holds the record."""
    rig = build_rig(tmp_path, NO_COUNTY, NO_COUNTY_OTHER, candidates=COUNTY_IS_THE_PROVINCE)
    run = rig.specimen.run
    settle(rig, Scripted({"county": answering(LACKS), "city": answering(LACKS)}))

    rows = {item.id: item for item in run.evidence}
    allowed = field_step.not_on_label_keys(field_step.profile_of(run))
    assert all(field_step.not_on_label(key, run.fields[key], run, rows, allowed) for key in ("county", "city"))
    assert unresolved_labels(run) == []
    assert (run.disposition, run.reasons) == (Disposition.CLEARED, [])


def test_a_real_conflict_still_holds_its_label(tmp_path):
    """G19 kept: the readers differ on the collectors ("J. Smith" and "J. Smyth") and the field is left
    for a person, so the label's reason stays beside the field's own."""
    rig = build_rig(tmp_path, TEXT, SMYTH, candidates=every_field(*SMITH_OR_SMYTH))
    run = rig.specimen.run
    settle(rig, Scripted({"collectors": answering(FieldAnswer(outcome="several_possibilities",
        options=["J. Smith", "J. Smyth"], explanation="The readers differ."))}))

    region = run.regions[0].id
    assert run.reasons[:1] == [f"unresolved_transcription:{region}"]
    assert any(reason.endswith(":collectors") for reason in run.reasons)


def second_label(run):
    """The run with a second label whose two readers' observations no field is drawn from and no
    transcript resolves (R0's labels with no field drawn: r1/three 105526325 and 105526326)."""
    region = run.regions[0].model_copy(update={"id": "label-2", "order": 1})
    run.regions.append(region)
    run.observations.extend(item.model_copy(update={"id": f"{item.id}-2", "region_id": region.id})
        for item in list(run.observations))
    return region


def test_a_label_no_field_is_drawn_from_holds_only_while_a_field_with_its_text_is_held(tmp_path, monkeypatch):
    """C3's second half: a label no field is drawn from, on which the organiser found text for some
    field, is unresolved_transcription only while one of those fields has a reason of its own (on main
    it always held the record). With no organiser text on it at all it still holds: its reason is the
    only thing standing for text no field took (WP 2.R's inputs, test_review_rules; R0 kept these too)."""
    rig = build_rig(tmp_path)
    run = rig.specimen.run
    settle(rig, Scripted())
    assert (run.disposition, run.reasons) == (Disposition.CLEARED, [])
    region = second_label(run)

    def reasons():
        work = dict.fromkeys(run.fields, field_step.RESOLVED)
        return field_step.scientific_reasons(run, work, mandatory=field_step.profile_of(run).mandatory_fields,
            qualified=frozenset(), today=TODAY, allowed=field_step.not_on_label_keys(field_step.profile_of(run)))

    assert f"unresolved_transcription:{region.id}" in reasons()
    # The organiser's text on it for the collectors, which are held: the label holds too.
    monkeypatch.setattr(field_step, "_label_candidate_keys",
        lambda run, region_id: frozenset({"collectors"}) if region_id == region.id else frozenset())
    run.fields["collectors"] = run.fields["collectors"].model_copy(update={"state": ValueState.AMBIGUOUS})
    held = reasons()
    assert f"unresolved_transcription:{region.id}" in held and "mandatory_unresolved:collectors" in held
    assert held.index(f"unresolved_transcription:{region.id}") < held.index("mandatory_unresolved:collectors")
    # The same text for a field that settled: nothing holds the label.
    monkeypatch.setattr(field_step, "_label_candidate_keys",
        lambda run, region_id: frozenset({"habitat"}) if region_id == region.id else frozenset())
    assert f"unresolved_transcription:{region.id}" not in reasons()


@pytest.mark.parametrize(("reason", "fields"), [
    ("mandatory_unresolved:county", ("county",)),
    ("marked:collectors:label-1:text_only", ("collectors",)),
    ("taxonomy_unresolved", ("taxon",)),
    ("identifier_format", ("fmnh_ins_number",)),
    ("date_order", ("date_visited_from", "date_visited_to", "date_identified")),
    ("elevation_invalid:ft", ("elevation_from_ft", "elevation_to_ft")),
    ("elevation_units_conflict:from", ("elevation_from_m", "elevation_from_ft")),
    ("unresolved_transcription:label-1", ()),
    ("label_coverage_unconfirmed", ()),
])
def test_each_reason_holds_the_fields_it_names(reason, fields):
    keys = ("county", "collectors", "taxon", "fmnh_ins_number", "date_visited_from", "date_visited_to",
        "date_identified", "elevation_from_m", "elevation_to_m", "elevation_from_ft", "elevation_to_ft")
    assert set(field_step._reason_fields(reason, dict.fromkeys(keys, FieldValue()))) == set(fields)


# ---- C4a: a line break is white space in a place's literal ----------------------------------------

# 105526323's locality lines (results r1/pair: both readers).
DAVAO_LINES = "CNHM. E.Slope Mt.\nMcKinley, Davao\nProv., Mindanao P.I."
# What wp26's first pass attributed there (r1/pair 105526323): "Davao\nProv.," one unit of the precise
# location; on r1/three "Davao" the province's and the precise location's, "Prov.," the province's.
PLACE_WORDS = ("Davao", "Prov.", "McKinley", "Mindanao", "P.I.", "E.Slope", "Mt.")


def attributed(units, fields_of):
    """The units with each one's fields as `fields_of(text)` gives them for its first reader's text."""
    return units.model_copy(update={"units": [unit.model_copy(update={"fields": list(fields_of(
        next(iter(unit.readers.values())).text))}) for unit in units.units]})


def places_of(text):
    return ("province_state", "precise_location") if any(word in text for word in PLACE_WORDS) else ()


def two_readers(text, fields_of=places_of):
    """Label r1's two readers writing `text`, with the alignment's units, their fields `fields_of`."""
    from dataclasses import replace

    from test_first_pass_advice import with_units

    readings = with_units((Reading("1A", "r1", "o1a", "raw_reading", text),
        Reading("1B", "r1", "o1b", "raw_reading", text)))
    return tuple(replace(r, units=attributed(r.units, fields_of)) for r in readings)


def test_a_province_over_one_line_break_is_the_text_its_readers_write():
    """C4a: "Davao\\nProv.," is read from the transcript over the line break, and "Davao Prov.," is the same
    text, where the first pass attributes every unit it covers to places (agreement.place_units_only); on
    main both were refused (not_candidate, literal_not_in_reading)."""
    readings = two_readers(DAVAO_LINES)
    task = FieldTask("province_state", True, FieldValue(), (), FIELD_TOOLS["province_state"])

    assert agreement.across_lines("province_state", readings, "Davao Prov.,") == "Davao\nProv.,"
    assert agreement.literal_basis(task, readings, "Davao\nProv.,", readings) == agreement.TRANSCRIPT
    assert agreement.literal_refusal(task, readings, literal="Davao\nProv.,", named=readings) is None


@pytest.mark.parametrize("fields_of", [
    lambda text: (),                                                     # no unit names a field
    lambda text: ("collectors",) if "Prov." in text else places_of(text),  # another field's unit
    lambda text: ("province_state", "habitat") if "Davao" in text else places_of(text),
], ids=["unattributed", "another-fields-unit", "a-place-and-another-field"])
def test_a_place_over_a_line_break_needs_units_of_places_only(fields_of):
    """Codex's round 1 on #451: a line break is folded only where the first pass attributes every unit
    the literal covers to places; any unit with no field, or one naming another field, keeps main's
    refusal."""
    readings = two_readers(DAVAO_LINES, fields_of)
    task = FieldTask("province_state", True, FieldValue(), (), FIELD_TOOLS["province_state"])

    assert agreement.across_lines("province_state", readings, "Davao Prov.,") is None
    assert agreement.literal_basis(task, readings, "Davao\nProv.,", readings) is None


@pytest.mark.parametrize(("key", "literal"), [
    ("province_state", "McKinley, Davao\nProv., Mindanao P.I."),   # a whole line each side: still whole words
    ("province_state", "Slope Mt.\nMcKinley, Davao\nProv.,"),        # two line breaks
    ("collectors", "Davao\nProv.,"),                                # not a place value field
    ("date_visited_from", "Davao\nProv.,"),
])
def test_only_a_place_over_one_line_break_folds(key, literal):
    readings = two_readers(DAVAO_LINES)
    task = FieldTask(key, True, FieldValue(), (), FIELD_TOOLS[key])
    if literal.count("\n") == 1 and key in agreement.ONE_LINE_BREAK:
        assert agreement.literal_basis(task, readings, literal, readings) == agreement.TRANSCRIPT
        return
    assert agreement.literal_basis(task, readings, literal, readings) is None
    assert agreement.across_lines(key, readings, literal.replace("\n", " ")) is None


def attribute_run_units(run, fields_of):
    """The run's stored units (Run.reading_units) with their fields as `fields_of` gives them."""
    run.reading_units = [attributed(units, fields_of) for units in run.reading_units]


def test_105526323_s_province_settles_on_its_two_line_text(tmp_path):
    """The province's expert gives "Davao Prov.," as one line; both readers write it over the line break,
    which the first pass attributes to places. The step settles it on the readers' own text, with its
    source's value; on main it was refused."""
    text = label_with(country=None, province_state=None, county=None, city=None) + "\n" + DAVAO_LINES
    rig = build_rig(tmp_path, text)
    run = rig.specimen.run
    attribute_run_units(run, places_of)
    answer = FieldAnswer(outcome="resolved", literal="Davao Prov.,", reading_names=["1A", "1B"], value="Davao",
        authority_id="wikidata:Q15095071", explanation="Both readers write Davao Prov. over the line break.")

    async def province(task, readings, tools):
        found = await tools.lookup("wikidata", "Davao Province, Philippines", field_key=task.key)
        return FieldOutcome(task.key, answer.model_copy(update={"source_evidence_ids": [
            found.evidence.id]}), evidence=[found.evidence], model_calls=1)

    settle(rig, Scripted({"province_state": province, **dict.fromkeys(("country", "county", "city"),
        answering(LACKS))}), tools=DavaoProvince(rig.blobs))

    place = run.fields["province_state"]
    assert (place.state, place.literal, place.normalized) == (ValueState.SUPPORTED, "Davao\nProv.,", "Davao")


# Codex's round 1 on #451: a collector line runs on into a town the organiser missed.
NEW_YORK = label_with(city=None).replace("leg. J. Smith", "leg. J. New\nYork")


def test_a_place_over_a_line_break_into_another_fields_line_is_refused(tmp_path):
    """Both readers write "leg. J. New" over "York"; the organiser gives the collectors "J. New" and no
    city. The city's expert answers "New\\nYork", value "New York", citing a gazetteer. On S1's first
    head the line break was folded and the place, read from the transcript, took precedence over the
    collector; now the first pass attributes nothing there to a place (no unit names a field), so the
    city is refused as on main and the collectors keep their own text."""
    rig = build_rig(tmp_path, NEW_YORK, candidates=[("collectors", name, "J. New", "leg. J. New")
        for name in ("1A", "1B")])
    run = rig.specimen.run

    async def city(task, readings, tools):
        found = await tools.lookup("geolocate", "New York, Illinois, United States", field_key=task.key)
        return FieldOutcome(task.key, FieldAnswer(outcome="resolved", literal="New\nYork", reading_names=["1A", "1B"],
            value="New York", authority_id=found.candidates[0].authority_id, source_evidence_ids=[found.evidence.id],
            explanation="The town New York."), evidence=[found.evidence], model_calls=1)

    settle(rig, Scripted({"city": city, "collectors": answering(FieldAnswer(outcome="resolved", literal="J. New",
        reading_names=["1A", "1B"], explanation="The collector."))}))

    assert run.fields["city"].state != ValueState.SUPPORTED
    assert "mandatory_unresolved:city" in run.reasons


# ---- C4c: the country settled from another reading of the label -----------------------------------

# Reader 1B writes the country in another spelling (105526596's 2B "Costa R.ica"); the country settled
# before this attempt from reader 1A's "United States", so it is not researched again.
ONE_COUNTRY = TEXT.replace("country: United States", "country: United Statcs")


def countries(first, second):
    """The organiser's candidates for every field, each reader's country as that reader writes it."""
    return every_field(("country", "1A", first, f"country: {first}"), ("country", "1B", second, f"country: {second}"))


def settled_country(run, literal="United States"):
    first = run.observations[0]
    # The organiser's rows stay cited, so each reader's own country text is still the one it writes.
    run.fields["country"] = run.fields["country"].model_copy(update=dict(state=ValueState.SUPPORTED,
        literal=literal, layer="settled", authority_id="tgn:United States", source_region_id=run.regions[0].id,
        verbatim_by_observation={first.id: literal}, settled_observation_ids=[first.id]))


def both_readers(key, query, literal, authority_id):
    async def script(task, readings, tools):
        found = await tools.lookup("tgn", query, field_key=task.key)
        return FieldOutcome(task.key, FieldAnswer(outcome="resolved", literal=literal,
            reading_names=["1A", "1B"], authority_id=authority_id, source_evidence_ids=[found.evidence.id],
            explanation="Both readers write it."), evidence=[found.evidence], model_calls=1)
    return script


def test_a_province_settles_inside_the_country_another_reading_of_its_label_settled(tmp_path):
    """C4c: reader 1B writes "United Statcs", which no source confirms, where 1A's "United States"
    settled. The province both readers write, which its source places in the United States, settles;
    on main it was refused for 1B (NO_COUNTRY: "No country is settled for the reading that writes this
    place")."""
    rig = build_rig(tmp_path, TEXT, ONE_COUNTRY, candidates=countries("United States", "United Statcs"))
    run = rig.specimen.run
    settled_country(run)
    settle(rig, Scripted({"province_state": both_readers("province_state", "Illinois", "Illinois",
        "tgn:Illinois")}))

    place = run.fields["province_state"]
    assert (place.state, place.literal, place.authority_id) == (ValueState.SUPPORTED, "Illinois", "tgn:Illinois")


def test_a_province_outside_the_settled_country_is_still_refused(tmp_path):
    """The chain still holds: the country settled from 1A is another nation than the province's parent,
    so the province is refused (NOT_IN_COUNTRY), as on main."""
    rig = build_rig(tmp_path, TEXT, ONE_COUNTRY, candidates=countries("United States", "United Statcs"))
    run = rig.specimen.run
    settled_country(run, literal="Canada")
    run.fields["country"] = run.fields["country"].model_copy(update={"authority_id": "tgn:Canada"})
    settle(rig, Scripted({"province_state": both_readers("province_state", "Illinois", "Illinois",
        "tgn:Illinois")}))

    place = run.fields["province_state"]
    assert place.state != ValueState.SUPPORTED
    assert place.reason.startswith((agreement.NOT_IN_COUNTRY, agreement.NO_COUNTRY))


def test_a_province_with_no_country_settled_anywhere_is_still_refused(tmp_path):
    """No reading's country settled (both readers' texts unconfirmed): the place is refused, NO_COUNTRY,
    as on main (R0's 105526321, 105526461 and 105526359 stay held: plan WP S1)."""
    rig = build_rig(tmp_path, ONE_COUNTRY.replace("Statcs", "Statez"), ONE_COUNTRY,
        candidates=countries("United Statez", "United Statcs"))
    run = rig.specimen.run
    settle(rig, Scripted({"country": answering(FieldAnswer(outcome="sources_cannot_resolve",
        explanation="No source confirms it.")), "province_state": both_readers("province_state", "Illinois",
        "Illinois", "tgn:Illinois")}))

    place = run.fields["province_state"]
    assert place.state != ValueState.SUPPORTED and place.reason.startswith(agreement.NO_COUNTRY)


FRANCE = TEXT.replace("country: United States", "country: France")


def test_a_country_another_reading_of_the_label_contests_never_stands_for_it(tmp_path):
    """Codex's round 1 on #451: reader 1A writes "United States", 1B "France"; the country settled on 1A's
    text. The province both readers write, which its source places in the United States, is refused for
    1B as on main (NO_COUNTRY): the settled country stands for a reading only where every reading of the
    label writes it alike. On S1's first head the United States was put in for 1B and the province
    settled."""
    rig = build_rig(tmp_path, TEXT, FRANCE, candidates=countries("United States", "France"))
    run = rig.specimen.run
    settled_country(run)
    settle(rig, Scripted({"province_state": both_readers("province_state", "Illinois", "Illinois",
        "tgn:Illinois")}))

    place = run.fields["province_state"]
    assert place.state != ValueState.SUPPORTED and place.reason.startswith(agreement.NO_COUNTRY)


def test_a_country_marked_on_the_label_never_stands_for_another_reading(tmp_path):
    """The same alike spellings as the settling test, with the country marked on the label by an earlier
    pass (a conflict): the province is refused for 1B as on main."""
    from specimen_digitization.application.domain import RunFinding

    rig = build_rig(tmp_path, TEXT, ONE_COUNTRY, candidates=countries("United States", "United Statcs"))
    run = rig.specimen.run
    settled_country(run)
    run.findings.append(RunFinding(rule_id=field_step.SETTLEMENT, rule_version=field_step.SETTLEMENT_RULES,
        severity="warning", field_key="country", reason_code=field_step.marked_code("country", run.regions[0].id,
        "conflict"), evidence_ids=[]))
    settle(rig, Scripted({"province_state": both_readers("province_state", "Illinois", "Illinois",
        "tgn:Illinois")}))

    assert run.fields["province_state"].state != ValueState.SUPPORTED


# ---- C4d: a request its sources made too long ----------------------------------------------------

BIG = "x" * 9_000


def detailed(query, index):
    """A gazetteer's answer with five candidates whose details are long (TGN's parent strings)."""
    evidence = Evidence(id=f"ev-{index}", kind="authority", source="tgn", locator=None, excerpt=query)
    candidates = tuple(SourceCandidate(f"{query} {n}", f"tgn:{index}{n}", "inhabited places", BIG) for n in range(5))
    return SourceAnswer("tgn", query, LookupStatus.AMBIGUOUS, candidates, evidence, note="ambiguous " + BIG)


QUERIES = ("Davao", "Mindanao")


def province_task():
    return FieldTask("province_state", True, FieldValue(), (), FIELD_TOOLS["province_state"])


class Tools:
    sources = ("tgn",)

    def __init__(self):
        self.answers = {query: detailed(query, index) for index, query in enumerate(QUERIES)}

    async def lookup(self, source_id, query, *, field_key):
        return self.answers[query]


def scripted(final):
    """The province expert: one lookup per query, then (on whatever request comes next) `final`."""
    seen = []

    def respond(messages, info):
        seen.append((len(messages), budget.input_token_bound(list(messages), info.model_request_parameters)
            if hasattr(info, "model_request_parameters") else None, info.function_tools))
        turn = len(seen)
        if turn <= len(QUERIES) and info.function_tools:
            return ModelResponse(parts=[ToolCallPart("lookup", {"source": "tgn", "query": QUERIES[turn - 1]})])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, final)])
    return respond, seen


def run_expert(final):
    respond, seen = scripted(final)
    resolver = experts.make_resolver(model_factory=lambda: FunctionModel(respond),
        meter=budget.CostMeter(10_000_000, input_micros_per_million=200_000, output_micros_per_million=600_000))
    readings = two_readers(DAVAO_LINES)
    outcome = asyncio.run(resolver(province_task(), readings, {}, tools=Tools()))
    return outcome, seen


def test_a_request_its_sources_made_too_long_is_answered_on_a_shortened_one():
    """C4d: the second request (the prompt and a lookup's long answer) is over the input bound; on main
    the field failed as input_too_large. Now the answer is asked for once more, tools withheld, on the
    run so far with each lookup's result shortened to what an answer cites (its evidence_id, the
    candidates' names, records and kinds), and it stands."""
    outcome, seen = run_expert(dict(outcome="sources_cannot_resolve",
        explanation="TGN finds several places named Davao and none settles the province."))

    assert outcome.failure is None and outcome.fallback is False
    assert outcome.answer.outcome == "sources_cannot_resolve"
    # A lookup ran; the request after it was over the bound, and the answer came on one without tools.
    assert [bool(tools) for _, _, tools in seen] == [True, False]
    assert {item.id for item in outcome.evidence} == {"ev-0"}


def test_the_shortened_lookup_result_keeps_what_an_answer_cites():
    view = experts._candidate_view(detailed("Davao", 0))
    shortened = experts._shortened_result(view)

    assert shortened["evidence_id"] == "ev-0" and shortened["status"] == "ambiguous"
    assert [set(c) for c in shortened["candidates"]] == [{"name", "authority_id", "kind"}] * 5
    assert "note" not in shortened and len(str(shortened)) < len(str(view)) // 10
    # Any other tool's result is as it was.
    assert experts._shortened_result({"status": "success", "values": ["1948-04-25"]}) == {
        "status": "success", "values": ["1948-04-25"]}


def test_a_first_request_over_the_bound_still_fails_as_too_large():
    """The prompt alone over the bound: no lookup's answer to shorten, so the field fails as
    input_too_large, as on main (test_experts' own case)."""
    huge = (Reading("9A", "region-9", "obs-9a", "raw_reading", "x" * 200_000),)
    respond, seen = scripted(dict(outcome="label_lacks_value", explanation="-"))
    resolver = experts.make_resolver(model_factory=lambda: FunctionModel(respond),
        meter=budget.CostMeter(10_000_000, input_micros_per_million=200_000, output_micros_per_million=600_000))

    outcome = asyncio.run(resolver(province_task(), two_readers(DAVAO_LINES) + huge, {}, tools=Tools()))

    assert (outcome.answer, outcome.failure) == (None, "input_too_large") and seen == []


# ---- the empty-record guard --------------------------------------------------------------------

def empty_record_reasons(run):
    work = dict.fromkeys(run.fields, field_step.RESOLVED)
    profile = field_step.profile_of(run)
    return field_step.scientific_reasons(run, work, mandatory=(), qualified=frozenset(), today=TODAY,
        allowed=field_step.not_on_label_keys(profile))


def test_a_record_nothing_on_which_describes_the_specimen_is_never_finished(tmp_path):
    """R0's 105526335, whose labels write only "FMNHINS 4486770" and "LEWIS COLLECTION / col": with only
    its catalogue number and collection code holding a value, every other field blank (each cleared as
    not on the label, or none mandatory), it still goes to a person, with its own reason; one value
    that describes the specimen and the guard says nothing."""
    rig = build_rig(tmp_path)
    run = rig.specimen.run
    settle(rig, Scripted())
    assert (run.disposition, run.reasons) == (Disposition.CLEARED, [])

    kept = run.fields["habitat"]
    for key in run.fields:
        if key not in ("fmnh_ins_number", "collection_code"):
            run.fields[key] = FieldValue(state=ValueState.NOT_PRESENT)
    assert field_step.NO_SPECIMEN_VALUE in empty_record_reasons(run)

    run.fields["habitat"] = kept
    assert field_step.NO_SPECIMEN_VALUE not in empty_record_reasons(run)
    # A placeholder is no value.
    run.fields["habitat"] = FieldValue(state=ValueState.SUPPORTED, literal="unknown")
    assert field_step.NO_SPECIMEN_VALUE in empty_record_reasons(run)
    # A person's approval decides the record.
    run.human_approved = True
    assert field_step.NO_SPECIMEN_VALUE not in empty_record_reasons(run)


def test_the_empty_record_reason_has_reviewer_text_in_the_app():
    """The app words every record reason it shows (blockers.dart _recordMessages)."""
    from pathlib import Path

    blockers = (Path(__file__).parents[2] / "apps/specimen_digitization/lib/src/screens/workbench/blockers.dart")
    assert f"'{field_step.NO_SPECIMEN_VALUE}':" in blockers.read_text(encoding="utf-8")


def test_the_empty_record_guard_keeps_a_cleared_record_cleared(tmp_path):
    rig = build_rig(tmp_path)
    settle(rig, Scripted())
    assert field_step.NO_SPECIMEN_VALUE not in rig.specimen.run.reasons
    assert LABEL["habitat"] == rig.specimen.run.fields["habitat"].literal
