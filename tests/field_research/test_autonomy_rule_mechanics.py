"""Autonomy program, work package S1 (docs/execution/autonomy/PLAN.md): the holds the free replay R0
measured as rule mechanics, not doubt, removed, and the holds that guard a real conflict kept.

- C3: a label's unresolved_transcription no longer repeats a field cleared as not on the label or a
  field waiting for a held source; a label no field is drawn from is held only while a field the
  organiser found text for on it is.
- C4: a place's literal over one line break is the same text as with a space (C4a); a precise location
  keeps the elevation whose number its elevation field settled (C4b, in test_elevations_and_extent);
  a place below the country settles inside the country settled from another reading of its label
  (C4c); an expert whose request its sources made too long answers on a shortened one (C4d).
- C1: a listed field whose own expert says the label lacks it clears as not on the label though the
  organiser offered text for it (the owner's rule change 1).
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
    research,
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


def two_readers(text):
    return (Reading("1A", "r1", "o1a", "raw_reading", text), Reading("1B", "r1", "o1b", "raw_reading", text))


def test_a_province_over_one_line_break_is_the_text_its_readers_write():
    """C4a: "Davao\\nProv.," is read from the transcript over the line break, and "Davao Prov.," is the same
    text: the place value fields fold one line break; on main both were refused (not_candidate,
    literal_not_in_reading)."""
    readings = two_readers(DAVAO_LINES)
    task = FieldTask("province_state", True, FieldValue(), (), FIELD_TOOLS["province_state"])

    assert agreement.across_lines("province_state", readings, "Davao Prov.,") == "Davao\nProv.,"
    assert agreement.literal_basis(task, readings, "Davao\nProv.,", readings) == agreement.TRANSCRIPT
    assert agreement.literal_refusal(task, readings, literal="Davao\nProv.,", named=readings) is None


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


def test_105526323_s_province_settles_on_its_two_line_text(tmp_path):
    """The province's expert gives "Davao Prov.," as one line; both readers write it over the line break.
    The step settles it on the readers' own text, with its source's value; on main it was refused."""
    text = label_with(country=None, province_state=None, county=None, city=None) + "\n" + DAVAO_LINES
    rig = build_rig(tmp_path, text)
    run = rig.specimen.run
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


# ---- C4c: the country settled from another reading of the label -----------------------------------

# Reader 1B writes the country in another spelling (105526596's 2B "Costa R.ica"); the country settled
# before this attempt from reader 1A's "United States", so it is not researched again.
ONE_COUNTRY = TEXT.replace("country: United States", "country: United Statse")


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
    """C4c: reader 1B writes "United Statse", which no source confirms, where 1A's "United States"
    settled. The province both readers write, which its source places in the United States, settles;
    on main it was refused for 1B (NO_COUNTRY: "No country is settled for the reading that writes this
    place")."""
    rig = build_rig(tmp_path, TEXT, ONE_COUNTRY, candidates=countries("United States", "United Statse"))
    run = rig.specimen.run
    settled_country(run)
    settle(rig, Scripted({"province_state": both_readers("province_state", "Illinois", "Illinois",
        "tgn:Illinois")}))

    place = run.fields["province_state"]
    assert (place.state, place.literal, place.authority_id) == (ValueState.SUPPORTED, "Illinois", "tgn:Illinois")


def test_a_province_outside_the_settled_country_is_still_refused(tmp_path):
    """The chain still holds: the country settled from 1A is another nation than the province's parent,
    so the province is refused (NOT_IN_COUNTRY), as on main."""
    rig = build_rig(tmp_path, TEXT, ONE_COUNTRY, candidates=countries("United States", "United Statse"))
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
    rig = build_rig(tmp_path, ONE_COUNTRY.replace("Statse", "Statez"), ONE_COUNTRY,
        candidates=countries("United Statez", "United Statse"))
    run = rig.specimen.run
    settle(rig, Scripted({"country": answering(FieldAnswer(outcome="sources_cannot_resolve",
        explanation="No source confirms it.")), "province_state": both_readers("province_state", "Illinois",
        "Illinois", "tgn:Illinois")}))

    place = run.fields["province_state"]
    assert place.state != ValueState.SUPPORTED and place.reason.startswith(agreement.NO_COUNTRY)


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


# ---- C1: blank is an answer for a listed field --------------------------------------------------

# The organiser's habitat is the method's text "trap", which no field settles (test_agreement's control).
TRAP = label_with(habitat=None, collection_method=None) + "\ntrap"
TRAP_HABITAT = every_field(*(("habitat", name, "trap", "trap") for name in ("1A", "1B")))


@pytest.mark.parametrize("answered", ["lacks", "cannot-resolve"])
def test_a_listed_field_its_expert_says_is_not_there_clears_whatever_the_organiser_offered(tmp_path, answered):
    """The owner's rule change 1 (2026-11-17): the whole label read by both readers and the habitat's own
    expert saying the label lacks it, the organiser's "trap" no longer refuses the absence (on main:
    A_declined:organiser_found_text). An expert that did not itself say so (sources_cannot_resolve) leaves
    the habitat for a person, as before."""
    rig = build_rig(tmp_path, TRAP, candidates=TRAP_HABITAT)
    run = rig.specimen.run
    habitat = answering(LACKS) if answered == "lacks" else answering(FieldAnswer(
        outcome="sources_cannot_resolve", explanation="It may be the method."))
    prepared, outcomes, calls = research(rig, Scripted({"habitat": habitat, "collection_method": answering(LACKS)}))
    decisions: dict[str, dict] = {}
    field_step.apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls, decisions=decisions)
    field_step.finalize_fields(run, None, outcomes, specimen=rig.specimen, blobs=rig.blobs, today=TODAY)

    if answered == "lacks":
        assert decisions["habitat"] == {"rule": "A_not_on_label"}
        assert "mandatory_unresolved:habitat" not in run.reasons
        return
    assert "rule" not in decisions.get("habitat", {}) or decisions["habitat"]["rule"] != "A_not_on_label"
    assert "mandatory_unresolved:habitat" in run.reasons


def test_a_field_off_the_list_stays_held_when_its_expert_says_it_is_not_there(tmp_path):
    """C1 adds no field to the list: the collectors (NEVER_NOT_ON_LABEL) stay held when their expert
    answers label_lacks_value, organiser text or none."""
    rig = build_rig(tmp_path, label_with())
    run = rig.specimen.run
    settle(rig, Scripted({"collectors": answering(LACKS)}))

    assert "mandatory_unresolved:collectors" in run.reasons
    assert "collectors" not in field_step.not_on_label_keys(field_step.profile_of(run))


def test_a_precise_location_its_expert_says_is_not_there_stays_held(tmp_path):
    """The precise-location extent rule stays (rule 7): its expert's label_lacks_value never clears it."""
    rig = build_rig(tmp_path)
    run = rig.specimen.run
    prepared, outcomes, calls = research(rig, Scripted({"precise_location": answering(LACKS)}))
    decisions: dict[str, dict] = {}
    field_step.apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls, decisions=decisions)

    assert decisions["precise_location"]["rule"].startswith("A_declined:")
    assert run.fields["precise_location"].state == ValueState.NOT_PRESENT


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
