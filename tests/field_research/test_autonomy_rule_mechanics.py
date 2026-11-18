"""Autonomy program, work package S1 (docs/execution/autonomy/PLAN.md): the holds the free replay R0
measured as rule mechanics, not doubt, removed, and the holds that guard a real conflict kept.

- C3 (the strict duplicate only): a label whose every drawn field already has a review reason of its
  own is not also unresolved_transcription; any drawn field without one, a field cleared as not on
  the label among them, keeps the label's reason, as does a label no field is drawn from.
- C4d: an expert whose request its sources made too long answers once more on a shortened one.
- The empty-record guard: a record whose fields that describe the specimen are all settled with no
  value is never finished without a person.
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
from specimen_digitization.field_research import budget, experts
from specimen_digitization.field_research import step as field_step
from specimen_digitization.field_research.contracts import (
    FIELD_TOOLS,
    FieldAnswer,
    FieldTask,
    Reading,
    SourceAnswer,
    SourceCandidate,
)

LACKS = FieldAnswer(outcome="label_lacks_value", explanation="Not on the label.")


def unresolved_labels(run):
    return [reason for reason in run.reasons if reason.startswith("unresolved_transcription:")]


# ---- C3: the label's hold repeats no field's -------------------------------------------------------

# The synthetic label without its county and city lines, and a line that differs between the readers.
NO_COUNTY = label_with(county=None, city=None)
# The organiser offers the county and the city the province's text (as on 105526324, whose county is
# "Davao Prov."), and the method the habitat's text (as on 105526328).
COUNTY_IS_THE_PROVINCE = every_field(*(("county", name, "Illinois", "province_state: Illinois")
    for name in ("1A", "1B")), *(("city", name, "Illinois", "province_state: Illinois") for name in ("1A", "1B")))


@pytest.mark.parametrize(("first", "second"), [
    ("Malaise trap", "Malaise trep"), ("Malaise trap", ""), ("Malaise trap", "MALAISE TRAP"),
    ("Cook Co.", "Cock Co."), ("Cook Co.", ""), ("Cook County", "Cook Country"), ("Chicago", "Chicaqo"),
], ids=["trap-trep", "trap-absent", "trap-capitals", "cook-cock", "cook-absent", "county-country", "chicago"])
def test_a_label_whose_readers_differ_keeps_its_reason_beside_a_field_cleared_as_not_on_it(tmp_path, first,
        second):
    """G51's round 1 on #451 (its input on #441, on one label): the readers differ on a line ("Malaise
    trap" against "Malaise trep", left out or capitals; "Cook Co." against "Cock Co."), the county, the
    city and the method clear as not on the label (the organiser offered them other fields' text), and
    the label's unresolved_transcription is the one reason that sends that line to a person. S1's first
    head cleared the record; it stays in review, as on main."""
    other = NO_COUNTY + ("\n" + second if second else "")
    rig = build_rig(tmp_path, NO_COUNTY + "\n" + first, other, candidates=every_field(
        *(("county", name, "Illinois", "province_state: Illinois") for name in ("1A", "1B")),
        *(("city", name, "Illinois", "province_state: Illinois") for name in ("1A", "1B")),
        *(("collection_method", name, LABEL["habitat"], "habitat: " + LABEL["habitat"]) for name in ("1A", "1B"))))
    run = rig.specimen.run
    settle(rig, Scripted({"county": answering(LACKS), "city": answering(LACKS),
        "collection_method": answering(LACKS)}))

    assert unresolved_labels(run) == [f"unresolved_transcription:{run.regions[0].id}"]
    assert run.disposition == Disposition.REVIEW


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


def reasons_of(run):
    work = dict.fromkeys(run.fields, field_step.RESOLVED)
    profile = field_step.profile_of(run)
    return field_step.scientific_reasons(run, work, mandatory=profile.mandatory_fields, qualified=frozenset(),
        today=TODAY, allowed=field_step.not_on_label_keys(profile))


def test_a_label_whose_every_drawn_field_has_its_own_reason_drops_the_duplicate(tmp_path):
    """C3, the strict duplicate: when every field drawn from the label is held or marked by a reason of
    its own, a person goes to each of them, and the label's reason repeats them (main kept it). One
    drawn field settled with no reason of its own and the label's reason is back."""
    rig = build_rig(tmp_path, TEXT, SMYTH, candidates=every_field(*SMITH_OR_SMYTH))
    run = rig.specimen.run
    settle(rig, Scripted())
    region = run.regions[0].id
    kept = dict(run.fields)
    for key, value in kept.items():
        if key != field_step.IRN:
            run.fields[key] = value.model_copy(update={"state": ValueState.AMBIGUOUS})

    held = reasons_of(run)
    assert f"unresolved_transcription:{region}" not in held
    assert {f"mandatory_unresolved:{key}" for key in kept if key != field_step.IRN} <= set(held)

    run.fields["habitat"] = kept["habitat"]
    assert "mandatory_unresolved:habitat" not in reasons_of(run)
    assert f"unresolved_transcription:{region}" in reasons_of(run)


def second_label(run):
    """The run with a second label whose two readers' observations no field is drawn from and no
    transcript resolves (R0's labels with no field drawn: r1/three 105526325 and 105526326)."""
    region = run.regions[0].model_copy(update={"id": "label-2", "order": 1})
    run.regions.append(region)
    run.observations.extend(item.model_copy(update={"id": f"{item.id}-2", "region_id": region.id})
        for item in list(run.observations))
    return region


def test_a_label_no_field_is_drawn_from_keeps_its_reason(tmp_path):
    """A label no field is drawn from stays unresolved_transcription, as on main (WP 2.R's inputs)."""
    rig = build_rig(tmp_path)
    run = rig.specimen.run
    settle(rig, Scripted())
    assert (run.disposition, run.reasons) == (Disposition.CLEARED, [])
    region = second_label(run)

    assert f"unresolved_transcription:{region.id}" in reasons_of(run)


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


# ---- C4d: a request its sources made too long ----------------------------------------------------

# 105526323's locality lines (results r1/pair: both readers).
DAVAO_LINES = "CNHM. E.Slope Mt.\nMcKinley, Davao\nProv., Mindanao P.I."


def two_readers(text):
    return (Reading("1A", "r1", "o1a", "raw_reading", text), Reading("1B", "r1", "o1b", "raw_reading", text))


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
    """A record such as R0's 105526335 once its open fields settle absent (its labels write only
    "FMNHINS 4486770" and "LEWIS COLLECTION / col"): its catalogue number and collection code have
    values, every other field is settled with no value (cleared as not on the label, or none
    mandatory), and it still goes to a person, with its own reason. One value that describes the
    specimen, or one field still open (105526461 on the pair arm: its host, locality and date are
    written but left open, each with a reason of its own), and the guard says nothing."""
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
    # A field still open is held by its own reason, not this one.
    run.fields["habitat"] = FieldValue(state=ValueState.UNRESOLVED)
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
