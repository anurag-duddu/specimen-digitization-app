"""WP 2.3c of docs/execution/units/PLAN.md: a failed check is handled before it is marked. The owner typed
on 2026-11-14: "4 shouldn't be flagged. It should be caught and handled. Goal isn't to throw everything at
the user it is to help by being in in autonomy as much as possible." and "Harness needs to work and do its
magic".

1. The collectors' role marker ("leg.", "coll.", "Coll.": the notation collected_by) is never part of
   the literal (ontology_checks.without_role, on the units path).
2. When every answer of an expert is refused by its checks, the units path keeps each refusal's check
   and literal (FieldOutcome.rejected), and the field's reason names them (census cause H1).
3. One re-ask before a mark (field_research/reask.py).
4. The image test's neighbour guard narrowed (agreement.image_names with the field's key): close to the
   wp15c follow-up's variant N2, a line break ends the walk, for a field other than a precise location
   whose covering units its readers write alike, where the next line is certainly not the field's: wholly
   other settled fields' texts or text of another kind (Codex's round 1 on PR #439 and the coordinator's
   ruling). The brief's N1 (a differing neighbour blocks only when
   its image is uncertain or not visible) was tried and rejected: it cleared a cut-short value on PR
   #425's pinned reviewer inputs (test_settlement_rule.py's TABLE: "forest" of "cloud forest", "trap" of
   "light trap", "Danaus plexippus" of the trinomial, "Mt. McKinley" of "E Slope Mt. McKinley").

Every test runs on both first-pass paths (conftest.py), unless its module sets one. On the old path,
live in production until WP 1.8, each test asserts origin/main's result."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from test_elevations_and_extent import DAVAO_AND_PI, LACKS, extent_marks
from test_first_pass_advice import with_units
from test_precise_location_extent import MCKINLEY
from test_step import TEXT, TODAY, DavaoProvince, Scripted, answering, build_rig, mounted, settle

from specimen_digitization.application.domain import FieldValue, ValueState
from specimen_digitization.application.organiser import parse_locator
from specimen_digitization.application.reading_units import NOT_VISIBLE, UNCERTAIN, ReadingUnit, ReadingUnits, UnitText
from specimen_digitization.field_research import agreement, budget, experts, ontology_checks
from specimen_digitization.field_research import step as field_step
from specimen_digitization.field_research.contracts import FIELD_TOOLS, Candidate, FieldAnswer, FieldOutcome, FieldTask
from specimen_digitization.field_research.contracts import Reading

FIELDS = [key for key in FIELD_TOOLS if key != "identified_by_irn"]


def answer(literal, explanation="Both readers write it."):
    return FieldAnswer(outcome="resolved", literal=literal, reading_names=["1A", "1B"], explanation=explanation)


# ---- 1. the collectors' role marker -------------------------------------------------------------

@pytest.mark.parametrize(("literal", "name"), [
    ("H. Hoogstraal leg.", "H. Hoogstraal"),
    ("H.Hoogstraal leg.", "H.Hoogstraal"),
    ("leg. H. Hoogstraal", "H. Hoogstraal"),
    ("H. Hoogstraal coll.", "H. Hoogstraal"),
    ("Coll. H. Hoogstraal", "H. Hoogstraal"),
    ("H. Hoogstraal, leg.", "H. Hoogstraal"),
    ("leg. H. Hoogstraal leg.", "H. Hoogstraal"),
    ("leg.", ""),
    ("  coll. ", ""),
    ("F.G. Werner", None),
    ("J. Legrand", None),
    ("Legrand", None),
    ("H. Hoogstraalleg.", None),
    ("leg.H. Hoogstraal", None),
    ("Leg. H. Hoogstraal", None),
    ("H. Hoogstraal det.", None),
    ("leg. et det. J. Smith", None),
    ("J. Dupont et coll.", None),
    ("J. Dupont & coll.", None),
    ("J. Dupont and coll.", None),
    ("leg. y J. Smith", None),
    ("J. Smith det. leg.", None),
    ("A. Smith & B. Jones leg.", "A. Smith & B. Jones"),
], ids=lambda value: repr(value))
def test_the_role_marker_is_read_off_the_edge_of_a_collectors_literal(literal, name):
    """ontology_checks.without_role: a marker of the notation collected_by, as a whole token at the
    literal's edge, is the role; the name is the rest, but only when it is a name alone: another role
    word in it ("det."), or a joiner at its edge ("et", "&", "and", "y"), keeps the literal as it is (G51's
    round 1 on PR #439). A marker inside a word, glued to the name, in another spelling or of another role
    is no collectors' marker."""
    found = ontology_checks.without_role(literal)
    assert (found.name if found is not None else None) == name
    if found is not None and found.name:
        assert literal[found.start:found.end] == found.name


def test_the_markers_are_the_ontology_s_notation():
    assert ontology_checks.role_markers() == ("leg.", "coll.", "Coll.")


def collectors_run(tmp_path, line, literal, candidate=None):
    """test_step's label with its collectors line `line`, the organiser's candidate `candidate` (the line
    when None) in both readings, the collectors' expert answering `literal` from both."""
    rig = build_rig(tmp_path, TEXT.replace("leg. J. Smith", line),
        candidates=[("collectors", name, line if candidate is None else candidate, line) for name in ("1A", "1B")])
    settle(rig, Scripted({"collectors": answering(answer(literal))}))
    return rig, rig.specimen.run


@pytest.mark.parametrize(("line", "units", "old"), [
    ("H. Hoogstraal leg.", "H. Hoogstraal", "H. Hoogstraal leg."),
    ("leg. H. Hoogstraal", "H. Hoogstraal", "leg. H. Hoogstraal"),
    ("H. Hoogstraal coll.", "H. Hoogstraal", "H. Hoogstraal coll."),
    ("Coll. H. Hoogstraal", "H. Hoogstraal", "Coll. H. Hoogstraal"),
    ("F.G. Werner", "F.G. Werner", "F.G. Werner"),
    ("J. Legrand", "J. Legrand", "J. Legrand"),
    ("leg. et det. J. Smith", "leg. et det. J. Smith", "leg. et det. J. Smith"),
    ("J. Dupont et coll.", "J. Dupont et coll.", "J. Dupont et coll."),
    ("J. Dupont & coll.", "J. Dupont & coll.", "J. Dupont & coll."),
], ids=["leg-after", "leg-before", "coll", "Coll", "no-marker", "leg-inside-a-word", "leg-et-det", "et-coll",
    "and-coll"])
def test_the_collectors_settle_without_the_marker_of_their_role_on_the_units_path(tmp_path, first_pass_path, line,
        units, old):
    """The plan's cases (WP 2.3c, change 1): the organiser and the expert give the whole line; on the units
    path the name settles without the marker, a verbatim span of the label: its row locates the name, and
    its line keeps the marker as evidence of the role, which the reason names. On the old path the line
    settles whole, as on origin/main."""
    rig, run = collectors_run(tmp_path, line, line)
    value = run.fields["collectors"]
    assert value.state == ValueState.SUPPORTED
    if first_pass_path == "old":
        assert value.literal == old and "notation collected_by" not in value.reason
        return
    assert (value.literal, value.parsed) == (units, units)
    assert set(value.verbatim_by_observation.values()) <= {units}
    rows = {item.id: item for item in run.evidence}
    readings = {reading.observation_id: reading for reading in field_step.run_readings(run)}
    located = [rows[i] for i in value.evidence_ids if rows[i].kind == "literal"
        and value.evidence_relations.get(i) == "supports" and (where := parse_locator(rows[i].locator)) is not None
        and readings[where.observation_id].text[where.literal_start:where.literal_end] == units]
    assert located and all(line in row.excerpt for row in located)
    if units != line:
        marker = ontology_checks.without_role(line).marker
        assert (f"The marker {marker!r} beside the name says its role, collected by (notation collected_by): "
            "the name is settled without it.") in value.reason
    else:
        assert "notation collected_by" not in value.reason


def test_the_name_alone_settles_beside_a_candidate_that_holds_the_marker_on_the_units_path(tmp_path,
        first_pass_path):
    """The organiser's candidate is "H. Hoogstraal leg." and the expert answers the name. On the units path
    the candidate is read without its marker (step._without_roles), so the name is the candidate and
    settles. On the old path the name cuts the candidate and is refused, as on origin/main."""
    rig, run = collectors_run(tmp_path, "H. Hoogstraal leg.", "H. Hoogstraal")
    value = run.fields["collectors"]
    if first_pass_path == "units":
        assert (value.state, value.literal) == (ValueState.SUPPORTED, "H. Hoogstraal")
    else:
        assert value.state == ValueState.UNRESOLVED and value.reason.startswith(agreement.NOT_CANDIDATE)


def test_the_reason_names_the_marker_only_beside_a_name_alone(tmp_path, first_pass_path):
    """G51's round 1 on PR #439: the reason's sentence about the marker is true of what settles. The
    organiser's candidate "J. Dupont et", which the line writes before "coll.", ends with a joiner: it is
    no name alone (ontology_checks.plain_name), so its reason says nothing of the marker, on both paths."""
    rig, run = collectors_run(tmp_path, "J. Dupont et coll.", "J. Dupont et", candidate="J. Dupont et")
    value = run.fields["collectors"]
    assert (value.state, value.literal) == (ValueState.SUPPORTED, "J. Dupont et")
    assert "notation collected_by" not in value.reason


def test_a_literal_that_is_the_marker_alone_settles_nothing_on_the_units_path(tmp_path, first_pass_path):
    """The plan's case: a literal that is the marker alone. On the units path it is refused
    (agreement.ROLE_ONLY), the field unresolved, and the organiser's candidate that is the marker alone is
    left out of the task. On the old path it settles as written, as on origin/main."""
    rig, run = collectors_run(tmp_path, "leg.", "leg.")
    value = run.fields["collectors"]
    if first_pass_path == "units":
        assert value.state == ValueState.UNRESOLVED and value.reason.startswith(agreement.ROLE_ONLY)
        assert field_step._without_roles([Candidate("1A", "leg.", "leg.", "e1")]) == []
    else:
        assert (value.state, value.literal) == (ValueState.SUPPORTED, "leg.")


def test_the_collectors_expert_s_own_checks_read_the_literal_without_the_marker(first_pass_path):
    """experts._Expert.validate: on the units path the expert's "H. Hoogstraal leg." passes its checks as
    "H. Hoogstraal", the name its candidate gives (step.build_tasks reads candidates so), and the marker
    alone is refused with ROLE_ONLY's retry. On the old path the literal stays whole, as on origin/main."""
    from pydantic_ai import ModelRetry

    readings = (Reading("1A", "r1", "o1a", "raw_reading", "H. Hoogstraal leg."),
        Reading("1B", "r1", "o1b", "raw_reading", "H. Hoogstraal leg."))
    units = first_pass_path == "units"
    if units:
        readings = with_units(readings)
    candidates = tuple(Candidate(name, "H. Hoogstraal leg.", "H. Hoogstraal" if units else "H. Hoogstraal leg.",
        f"e{name}") for name in ("1A", "1B"))
    task = FieldTask("collectors", True, FieldValue(), candidates, ())
    expert = experts._Expert(task, readings, SimpleNamespace(sources=()), None)
    given = expert.validate(answer("H. Hoogstraal leg."))
    assert given.literal == ("H. Hoogstraal" if units else "H. Hoogstraal leg.")
    if units:
        with pytest.raises(ModelRetry, match="marker of the collectors' role"):
            expert.validate(answer("leg."))


# ---- 2. the refused answers' checks (census cause H1) -------------------------------------------

def refusing_model(literal):
    """A model that answers `literal` from both readers every time it is asked."""
    def respond(messages, info):
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"outcome": "resolved",
            "literal": literal, "reading_names": ["1A", "1B"], "explanation": "Both readers write it."})])
    return FunctionModel(respond)


def test_every_refused_answer_keeps_its_check_and_literal_on_the_units_path_only(first_pass_path):
    """make_resolver: each answer the expert gave is refused ("Hoogstral" is in no reading), so the
    resolver's fallback (experts.UNCHECKED) stands. On the units path the outcome keeps each refusal's
    check and literal, in the order given; on the old path none, as on origin/main."""
    readings = (Reading("1A", "r1", "o1a", "raw_reading", "H. Hoogstraal"),
        Reading("1B", "r1", "o1b", "raw_reading", "H. Hoogstraal"))
    if first_pass_path == "units":
        readings = with_units(readings)
    task = FieldTask("collectors", True, FieldValue(), (), ())
    resolver = experts.make_resolver(model_factory=lambda: refusing_model("Hoogstral"),
        meter=budget.CostMeter(10_000_000, input_micros_per_million=200_000, output_micros_per_million=600_000))
    outcome = asyncio.run(resolver(task, readings, {}, tools=SimpleNamespace(sources=())))
    assert outcome.fallback and outcome.answer.explanation == experts.UNCHECKED
    if first_pass_path == "units":
        assert outcome.rejected and set(outcome.rejected) == {("literal_not_in_reading", "Hoogstral")}
        assert len(outcome.rejected) == outcome.model_calls
    else:
        assert outcome.rejected == ()


def test_the_refused_answers_are_named_in_the_reason_and_never_sent_to_a_model(tmp_path, first_pass_path):
    """The step: the field stays unresolved on both paths. On the units path its reason ends with the
    refused answers and their checks (step._rejected_note); on the old path the reason is the fallback's
    alone, as on origin/main, even for an outcome that carries refusals. The next attempt's request for
    the field carries neither the sentence nor the refused literal."""
    rig = build_rig(tmp_path)
    refused = (("not_candidate", "J. Smyth"), ("literal_not_in_reading", "Hoogstral"))
    fallback = FieldOutcome("collectors", FieldAnswer(outcome="sources_cannot_resolve", explanation=experts.UNCHECKED),
        fallback=True, model_calls=2, rejected=refused)

    async def script(task, readings, tools):
        return fallback

    settle(rig, Scripted({"collectors": script}))
    run = rig.specimen.run
    value = run.fields["collectors"]
    assert value.state == ValueState.UNRESOLVED
    if first_pass_path == "units":
        assert value.reason == (f"{experts.UNCHECKED} Refused answers: 'J. Smyth' by not_candidate; 'Hoogstral' by "
            "literal_not_in_reading.")
    else:
        assert value.reason == experts.UNCHECKED
    readings, tasks, context = field_step.build_tasks(run)
    [task] = [task for task in tasks if task.key == "collectors"]
    sent = experts._Expert(task, readings, SimpleNamespace(sources=()), None).prompt(context)
    assert "Refused answers" not in sent and "Hoogstral" not in sent and "J. Smyth" not in sent


# ---- 3. one re-ask before a mark ----------------------------------------------------------------

CUT = "E. slope Mt. McKinley"
SAW = ("it ends its line, and the label's next line, 'Davao Prov.', writes the settled province or state "
    "'Davao Prov.'; Precise Location takes every line of the locality, the higher places included")
ASKED = ("Your answer 'E. slope Mt. McKinley' failed the check precise_location_extent: it ends its line, and the "
    "label's next line, 'Davao Prov.', writes the settled province or state 'Davao Prov.'; Precise Location takes "
    "every line of the locality, the higher places included. Answer once more; your answer goes through every check "
    "again.")


def reask():
    """field_research/reask.py, imported where a test uses it (the module is new in WP 2.3c)."""
    from specimen_digitization.field_research import reask as module

    return module


def locality(first, second=None, *, failure=None, look=False):
    """The precise location's expert: `first` from both readers; asked again (FieldTask.reask), `second`,
    or `failure`; with `look`, a lookup first when asked again. Its `asked` lists each request's re-ask."""
    asked = []

    async def script(task, readings, tools):
        asked.append(task.reask)
        if task.reask is not None:
            if look:
                await tools.lookup("geolocate", "Davao, Philippines", field_key=task.key)
            if failure is not None:
                return FieldOutcome(task.key, None, failure=failure, model_calls=1)
            return FieldOutcome(task.key, answer(second or first, "Both readers write the locality."), model_calls=1)
        return FieldOutcome(task.key, answer(first, "Both readers write the locality."), model_calls=1)

    script.asked = asked
    return script


def mckinley(tmp_path, script):
    rig = build_rig(tmp_path, MCKINLEY + "\n3 Sept. '46\nF.G. Werner")
    resolver = Scripted({**{key: answering(LACKS) for key in FIELDS}, **DAVAO_AND_PI, "precise_location": script})
    return rig, resolver


def settle_reasking(rig, resolver):
    """As step.FieldResearchStep.run: research, the one re-ask (reask.again), apply and finalize."""
    run = rig.specimen.run
    tools = DavaoProvince(rig.blobs)
    prepared = field_step.build_tasks(run)
    calls = []

    async def go():
        outcomes = await field_step.research_fields(run, resolver=resolver, tools=tools, prepared=prepared,
            calls=calls)
        return await reask().again(run, None, prepared, outcomes, resolver=resolver, tools=tools, calls=calls,
            blobs=rig.blobs, asset_id=rig.specimen.asset.id)

    outcomes, unused = asyncio.run(go())
    field_step.apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls, unused=unused)
    field_step.finalize_fields(run, None, outcomes, specimen=rig.specimen, blobs=rig.blobs, today=TODAY)
    return outcomes, unused, calls


def as_today(tmp_path, script):
    """The precise location as the stage leaves it with no re-ask: state, literal, reason and its findings."""
    rig, resolver = mckinley(tmp_path / "today", script)
    settle(rig, resolver, tools=DavaoProvince(rig.blobs))
    return seen(rig.specimen.run)


def seen(run):
    """The precise location's state, literal, reason, findings and reasons, its label's id as "L" (each rig
    has its own)."""
    value = run.fields["precise_location"]
    region = run.regions[0].id
    return (value.state, value.literal, value.reason,
        sorted(f.reason_code.replace(region, "L") for f in run.findings if f.field_key == "precise_location"),
        sorted(reason.replace(region, "L") for reason in run.reasons if ":precise_location:" in reason))


def test_a_cut_short_precise_location_is_asked_again_once_and_its_whole_locality_settles(tmp_path,
        first_pass_path):
    """The plan's change 3: the stage marks "E. slope Mt. McKinley" cut short (precise_location_extent);
    on the units path the field is put back to its expert once, its request naming the check and what it
    saw. Its answer, the whole locality, goes through every check again and settles, its reason naming
    the re-ask, with no mark of the stage. On the old path nothing is asked again and nothing is marked."""
    script = locality(CUT, MCKINLEY)
    rig, resolver = mckinley(tmp_path, script)
    settle_reasking(rig, resolver)
    run = rig.specimen.run
    value = run.fields["precise_location"]
    if first_pass_path == "old":
        assert script.asked == [None] and value.literal == CUT and extent_marks(run) == []
        return
    assert script.asked == [None, ASKED]
    assert ASKED == reask().ASKED.format(literal=CUT, check="precise_location_extent", saw=SAW)
    assert (value.state, value.literal) == (ValueState.SUPPORTED, MCKINLEY) and extent_marks(run) == []
    assert (f"Re-asked once, after the check precise_location_extent failed on the expert's answer {CUT!r}: "
        f"{SAW}.") in value.reason
    assert not [reason for reason in run.reasons if reason.startswith("marked:precise_location:")]


@pytest.mark.parametrize("how", ["the-same-answer", "a-timeout", "a-fallback"])
def test_a_re_ask_that_fails_leaves_the_field_marked_as_today(tmp_path, first_pass_path, how):
    """The answer of the re-ask goes through every check again: the same cut-short literal is marked
    again, and a re-ask that fails (a timeout) or whose answer is the resolver's fallback keeps the field's
    earlier answer. Either way the field is as it is with no re-ask: its value, reason, findings and
    reasons."""
    if how == "a-timeout":
        script = locality(CUT, failure="timeout")
    elif how == "a-fallback":
        script = locality(CUT)
        inner = script

        async def script(task, readings, tools):
            found = await inner(task, readings, tools)
            if task.reask is not None:
                return FieldOutcome(task.key, FieldAnswer(outcome="sources_cannot_resolve",
                    explanation=experts.UNCHECKED), fallback=True, model_calls=1)
            return found
        script.asked = inner.asked
    else:
        script = locality(CUT, CUT)
    rig, resolver = mckinley(tmp_path, script)
    outcomes, _, _ = settle_reasking(rig, resolver)
    assert seen(rig.specimen.run) == as_today(tmp_path, locality(CUT))
    [given] = [outcome for outcome in outcomes if outcome.key == "precise_location"]
    assert given.reasked is None and given.answer.literal == CUT
    if first_pass_path == "units":
        assert len(script.asked) == 2 and given.model_calls == 2
        assert extent_marks(rig.specimen.run)
    else:
        assert script.asked == [None]


def test_a_re_ask_whose_answer_leads_the_stage_to_mark_another_field_is_not_kept(tmp_path, first_pass_path,
        monkeypatch):
    """The coordinator's ruling on G51's round 1: a re-asked answer is kept only when the stage, run again,
    marks no field it did not mark before the re-ask. Here a check is made to mark the determination date
    whenever the precise location is the whole locality: the whole locality is not kept, and the field is
    as it is with no re-ask."""
    from specimen_digitization.field_research.ontology_checks import Mark

    dates = ontology_checks._date_marks

    def marking(fields, human):
        found = dates(fields, human)
        if fields["precise_location"].literal == MCKINLEY:
            found.append(Mark("date_identified", "date_order", "Marked for a person, rule date_order: a test.", (),
                "a test"))
        return found

    monkeypatch.setattr(ontology_checks, "_date_marks", marking)
    script = locality(CUT, MCKINLEY)
    rig, resolver = mckinley(tmp_path, script)
    outcomes, _, _ = settle_reasking(rig, resolver)
    assert seen(rig.specimen.run) == as_today(tmp_path, locality(CUT))
    [given] = [outcome for outcome in outcomes if outcome.key == "precise_location"]
    assert given.reasked is None
    assert len(script.asked) == (2 if first_pass_path == "units" else 1)


def test_a_field_is_asked_again_at_most_once_an_attempt(tmp_path, first_pass_path):
    """The bound: reask.again asks each field once; asked again on its own outcomes it asks nothing, as
    the re-ask's outcome is never asked again (FieldOutcome.reasked), and a field marked again keeps
    its earlier answer."""
    script = locality(CUT, CUT)
    rig, resolver = mckinley(tmp_path, script)
    run = rig.specimen.run
    tools = DavaoProvince(rig.blobs)
    prepared = field_step.build_tasks(run)
    calls = []

    async def go():
        outcomes = await field_step.research_fields(run, resolver=resolver, tools=tools, prepared=prepared,
            calls=calls)
        first, _ = await reask().again(run, None, prepared, outcomes, resolver=resolver, tools=tools, calls=calls,
            blobs=rig.blobs)
        kept = [replace_reasked(outcome) for outcome in first]
        return await reask().again(run, None, prepared, kept, resolver=resolver, tools=tools, calls=calls,
            blobs=rig.blobs)

    asyncio.run(go())
    assert len(script.asked) == (2 if first_pass_path == "units" else 1)


def replace_reasked(outcome):
    from dataclasses import replace

    return replace(outcome, reasked="asked") if outcome.key == "precise_location" else outcome


def test_a_re_ask_whose_answer_is_not_kept_records_its_lookups_and_decides_nothing(tmp_path, first_pass_path):
    """A re-ask that looks a place up and gives the cut-short literal again: its lookup is recorded on the
    run (a tool call and its evidence, step.apply_outcomes' `unused`), the field cites none of it, and the
    field is as it is with no re-ask."""
    script = locality(CUT, CUT, look=True)
    rig, resolver = mckinley(tmp_path, script)
    _, unused, calls = settle_reasking(rig, resolver)
    run = rig.specimen.run
    assert seen(run) == as_today(tmp_path, locality(CUT))
    if first_pass_path == "old":
        assert unused == []
        return
    [call] = unused
    assert call not in calls and call.answer.evidence.id in {item.id for item in run.evidence}
    assert call.answer.evidence.id in {record.evidence_id for record in run.tool_calls}
    assert call.answer.evidence.id not in run.fields["precise_location"].evidence_ids


def test_a_person_s_value_is_never_asked_again(tmp_path, first_pass_path, monkeypatch):
    """reask.to_ask: a field a person decided is never put back to an expert, whatever the stage marks."""
    rig, resolver = mckinley(tmp_path, locality(CUT))
    run = rig.specimen.run
    prepared = field_step.build_tasks(run)
    calls = []
    outcomes = asyncio.run(field_step.research_fields(run, resolver=resolver, tools=DavaoProvince(rig.blobs),
        prepared=prepared, calls=calls))
    copy, decisions = reask()._trial(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls, asset_id=None)
    asked = reask().to_ask(run, copy, decisions, outcomes)
    assert set(asked) == ({"precise_location"} if first_pass_path == "units" else set())
    monkeypatch.setattr(field_step, "human_keys", lambda run: frozenset({"precise_location"}))
    assert reask().to_ask(run, copy, decisions, outcomes) == {}


def test_the_step_asks_again_on_the_units_path_only(tmp_path, first_pass_path):
    """Through the workflow (step.FieldResearchStep.run): on the units path the marked field is asked again
    within the attempt and its whole locality settles, the run's paid call counting both requests; on the
    old path the expert is asked once."""
    script = locality(CUT, MCKINLEY)
    rig, resolver = mckinley(tmp_path, script)
    mounted(rig, resolver, sources=DavaoProvince)
    run = rig.workflow.step(rig.principal, rig.specimen.id).run
    value = run.fields["precise_location"]
    if first_pass_path == "units":
        assert script.asked == [None, ASKED] and value.literal == MCKINLEY
        assert not [reason for reason in run.reasons if reason.startswith("marked:precise_location:")]
    else:
        assert script.asked == [None] and value.literal == CUT
    paid = [call for call in run.paid_calls if call["step"] == field_step.STEP][-1]
    assert paid["usage"]["model_calls"] == len(resolver.calls)


def test_the_re_ask_sentence_follows_the_input_in_the_expert_s_request_on_the_units_path(first_pass_path):
    """experts._Expert.prompt: the re-ask's sentence (FieldTask.reask) after the input, after
    experts.REASK_PREFIX, on the units path; never on the old path."""
    readings = (Reading("1A", "r1", "o1a", "raw_reading", MCKINLEY), Reading("1B", "r1", "o1b", "raw_reading", MCKINLEY))
    if first_pass_path == "units":
        readings = with_units(readings)
    task = FieldTask("precise_location", True, FieldValue(), (), FIELD_TOOLS["precise_location"], reask=ASKED)
    sent = experts._Expert(task, readings, SimpleNamespace(sources=()), None).prompt({})
    if first_pass_path == "units":
        assert sent.endswith(f"\n\n{experts.REASK_PREFIX}{ASKED}")
    else:
        assert ASKED not in sent and experts.REASK_PREFIX not in sent


# ---- 4. the neighbour guard narrowed ------------------------------------------------------------

def label_of(rows, images):
    """One label's two readers ("a", "b") and its units by hand: `rows` gives each unit's line and each
    reader's text there; a unit follows the last one on its line after a space, on the next line after a
    line break. `images` gives each unit's image (a reader's key, whose text it names, or a judgement)."""
    texts, units = {"a": "", "b": ""}, []
    previous = None
    for number, ((line, a, b), image) in enumerate(zip(rows, images), 1):
        first, last = line if isinstance(line, tuple) else (line, line)
        readers = {}
        for key, text in (("a", a), ("b", b)):
            if texts[key]:
                texts[key] += " " if first == previous else "\n"
            readers[key] = UnitText(text=text, start=len(texts[key]), end=len(texts[key]) + len(text))
            texts[key] += text
        units.append(ReadingUnit(id=f"L:{number}", label="L", lines=(first, last), readers=readers,
            image=readers[image].text if image in readers else image))
        previous = last
    built = ReadingUnits(label="L", units=units)
    return {key: Reading(f"1{key.upper()}", "L", key, "raw_reading", text, units=built) for key, text in texts.items()}


# 105526322's collectors' line below its elevation's, where reader B writes the foot mark.
HOOGSTRAAL = [(1, "6-Sept-1946,", "6-Sept-1946,"), (1, "Elev.6400", "Elev.6400'"), (2, "H. Hoogstraal leg.",
    "H. Hoogstraal leg.")]


def test_a_one_line_field_whose_readers_agree_is_named_across_a_line_break(first_pass_path):
    """The named case: "H. Hoogstraal leg.", which both readers write and the image names, on the line
    below "6-Sept-1946, Elev.6400" / "6-Sept-1946, Elev.6400'", a date and an elevation
    (written.other_kind). For the collectors the walk outward stops at the line break, so the image names
    it; main's walk (no key) and the precise location's (ACROSS_LINES) still stop at the differing unit,
    and so does the collectors' when the two are on one line."""
    readings = label_of(HOOGSTRAAL, ["a", "a", "a"])
    assert agreement.image_names(readings["a"], "H. Hoogstraal", key="collectors")
    assert not agreement.image_names(readings["a"], "H. Hoogstraal")
    assert not agreement.image_names(readings["a"], "H. Hoogstraal", key="precise_location")
    same_line = label_of([(1, *row[1:]) for row in HOOGSTRAAL], ["a", "a", "a"])
    assert not agreement.image_names(same_line["a"], "H. Hoogstraal", key="collectors")
    task = FieldTask("collectors", True, FieldValue(), tuple(Candidate(name, "H. Hoogstraal leg.", "H. Hoogstraal",
        f"e{name}") for name in ("1A", "1B")), ())
    label = agreement.labels(task, tuple(readings.values()), [])["L"]
    assert (label.settled, label.cleared) == (frozenset({"H. Hoogstraal"}), True)


# 105526328's third label (wp15c r1/pair), lines 5 to 7: the elevation's readers differ, and so do the
# next line's; the image names reader A's text at both.
ELEVATION_800 = [(5, "IV-24-48", "IV-24-48"), (6, "Elev. +800 ft.", "Elev. 4800 ft."),
    (7, "lot #2 cut branch", "lot #a cut branch")]


def test_105526328_s_elev_800_ft_stays_held(first_pass_path):
    """The named case: where the readers differ at the field's own unit, the walk is main's, so a
    differing unit on the next line still keeps the image from naming A's "Elev. +800 ft." (truth 4800
    ft.): the expert's several_possibilities stays unsettled by the rule (step._by_rule), and an answer of
    A's text has no IMAGE backing."""
    readings = label_of(ELEVATION_800, ["a", "a", "a"])
    assert not agreement.image_names(readings["a"], "Elev. +800 ft.", key="elevation_from_ft")
    assert not agreement.image_names(readings["a"], "Elev. +800 ft.")
    task = FieldTask("elevation_from_ft", True, FieldValue(), (Candidate("1A", "Elev. +800 ft.", "Elev. +800 ft.", "ea"),
        Candidate("1B", "Elev. 4800 ft.", "Elev. 4800 ft.", "eb")), FIELD_TOOLS["elevation_from_ft"])
    several = FieldOutcome("elevation_from_ft", FieldAnswer(outcome="several_possibilities",
        options=["Elev. +800 ft.", "Elev. 4800 ft."], explanation="The readers write two numbers."))
    assert field_step._by_rule(task, several, tuple(readings.values()), (), date_rules=None) is None
    label = agreement.labels(task, tuple(readings.values()), [])["L"]
    assert not label.cleared
    # The line above differing too, a date there: where the readers differ at the field's own unit the walk
    # is main's whatever the next line holds.
    dated = label_of([(5, "IV-24-48", "IV-24-46"), ELEVATION_800[1]], ["a", "a"])
    assert not agreement.image_names(dated["a"], "Elev. +800 ft.", key="elevation_from_ft")


@pytest.mark.parametrize(("rows", "named"), [
    ([(1, "Shrubs", "Shrubs"), (1, "IV-24-48", "IV-24-46")], False),
    ([(1, "IV-24-48", "IV-24-46"), (1, "Shrubs", "Shrubs")], False),
    ([(1, "Shrubs", "Shrubs"), (2, "IV-24-48", "IV-24-46")], True),
], ids=["same-line-after", "same-line-before", "next-line"])
def test_a_neighbour_on_the_field_s_own_line_blocks_as_on_main(first_pass_path, rows, named):
    """The line-break stop is a stop at a line break only: a habitat's differing neighbour on its own line
    (a date) blocks as on main, before it or after it, even where the whole line is accounted for (here
    another settled field wrote "Shrubs"); on the next line it bounds nothing."""
    readings = label_of(rows, ["a", "a"])
    assert agreement.image_names(readings["a"], "Shrubs", key="habitat", settled=("Shrubs",)) is named


@pytest.mark.parametrize(("rows", "named"), [
    ([(1, "IV-24-48", "lot #2"), (2, "forest", "forest")], False),
    ([(1, "alt.", "alt"), (2, "forest", "forest")], False),
    ([((1, 2), "dry\nwet", "dry\nwet"), (2, "IV-24-48", "IV-24-46"), (3, "forest", "forest")], False),
    ([(1, "IV-24-48", "IV-24-46"), (2, "forest", "forest")], True),
], ids=["one-reader-s-line-only", "a-heading-with-no-elevation", "a-line-a-unit-crosses", "both-lines-a-date"])
def test_a_line_is_another_field_s_only_when_every_reader_s_text_there_is(first_pass_path, rows, named):
    """agreement._not_this_field: every reader's text on the line must be accounted for, an elevation's
    heading counts only beside an elevation, and a line another unit runs onto is never accounted for."""
    readings = label_of(rows, ["a"] * len(rows))
    assert agreement.image_names(readings["a"], "forest", key="habitat") is named


def test_the_settlement_gives_the_guard_the_other_settled_fields_texts(tmp_path, first_pass_path, monkeypatch):
    """step._settlement passes the texts of the other fields settled from the label (step._settled_texts)
    to the rule (agreement.labels' `settled`); every other call, and every call on the old path, passes
    none."""
    seen = []
    original = agreement.labels

    def spy(task, readings, answers, **kwargs):
        seen.append((task.key, tuple(kwargs.get("settled", ()))))
        return original(task, readings, answers, **kwargs)

    monkeypatch.setattr(agreement, "labels", spy)
    rig = build_rig(tmp_path)
    settle(rig, Scripted({}))
    run = rig.specimen.run
    given = [settled for key, settled in seen if key == "habitat" and settled]
    if first_pass_path == "old":
        assert not [settled for _, settled in seen if settled]
        return
    assert given == [field_step._settled_texts(run, "habitat")]
    assert "Chicago" in given[0] and "Synthetic grassland" not in given[0]


@pytest.mark.parametrize(("line", "text", "image", "named"), [
    (2, "megalippe", NOT_VISIBLE, True), (1, "megalippe", NOT_VISIBLE, True), (2, "megalippe", UNCERTAIN, False),
    (2, "megalippe", "a", False), (1, "megalippe", UNCERTAIN, False), (1, "megalippe", "a", False),
    (2, "IV-24-48", UNCERTAIN, True), (2, "IV-24-48", "a", True), (1, "IV-24-48", "a", False),
], ids=["not-visible-next-line", "not-visible-same-line", "uncertain-next-line", "named-next-line",
    "uncertain-same-line", "named-same-line", "a-date-next-line-uncertain", "a-date-next-line-named",
    "a-date-same-line"])
def test_a_differing_neighbour_blocks_as_on_main_unless_its_line_is_certainly_another_field_s(first_pass_path, line,
        text, image, named):
    """The named case and the line-break stop: A writes "Danaus plexippus" and then a text B does not write,
    and the image names the two words both write. A not-visible neighbour keeps main's result, named (the
    brief's N1 would block it), on the same line or the next. "megalippe" on the next line may go on with
    the taxon, so it blocks as on main whatever its image; a date there ("IV-24-48", written.other_kind)
    certainly does not, and bounds nothing. On the field's own line every differing neighbour that is
    not "not visible" blocks, as on main."""
    rows = [(1, "Danaus", "Danaus"), (1, "plexippus", "plexippus"), (line, text, "")]
    readings = label_of(rows, ["b", "b", image])
    assert agreement.image_names(readings["b"], "Danaus plexippus", key="taxon") is named
    if image == NOT_VISIBLE or line == 1:
        assert agreement.image_names(readings["b"], "Danaus plexippus") is named


@pytest.mark.parametrize(("key", "rows", "literal"), [
    ("collectors", [(1, "leg. J. Smith &", "leg. J. Smith &"), (2, "R. Jones", "R. James")], "J. Smith &"),
    ("habitat", [(1, "cloud", "rain"), (2, "forest", "forest")], "forest"),
    ("collection_method", [(1, "light", "flight"), (2, "trap", "trap")], "trap"),
    ("habitat", [(1, "cloud", "cloud"), (2, "forest", "fcrest")], "cloud"),
    ("collection_method", [(1, "light", "light"), (2, "trap", "trep")], "light"),
    ("collectors", [(1, "J. Smith &", "J. Smith &"), (2, "Hoogstraal", "Hoogstral")], "J. Smith &"),
    ("taxon", [(1, "Danaus", "Danaus"), (1, "plexippus", "plexippus"), (2, "megalippe", "")], "Danaus plexippus"),
    ("verbatim_dts", [(1, "6-Sept.", "6-Sept."), (2, "1946", "1948")], "6-Sept."),
], ids=["codex-collectors-and", "codex-cloud-forest", "codex-light-trap", "g51-cloud-forest", "g51-light-trap",
    "g51-collectors-and", "g51-danaus-megalippe", "g51-verbatim-dts-over-two-lines"])
def test_a_line_that_may_go_on_with_the_field_keeps_main_s_guard(first_pass_path, key, rows, literal):
    """Codex's and G51's round 1 on PR #439, the named cases: the readers agree at the literal's units, and
    the differing line beside it may be the same field's (a second collector after "&", "cloud" or "light"
    before or after the line, a subspecies, the year of verbatim D/T/S, whose brief keeps its line breaks).
    The walk is main's: the image does not name the literal, and the label settles it marked (text_only),
    never cleared."""
    readings = label_of(rows, ["a"] * len(rows))
    assert not agreement.image_names(readings["a"], literal, key=key)
    task = FieldTask(key, True, FieldValue(), tuple(Candidate(name, literal, literal, f"e{name}")
        for name in ("1A", "1B")), FIELD_TOOLS[key])
    label = agreement.labels(task, tuple(readings.values()), [])["L"]
    assert (label.settled, label.cleared, label.why) == (frozenset({literal}), False, agreement.TEXT_ONLY)


def test_a_not_visible_neighbour_on_the_next_line_keeps_main_s_walk(first_pass_path):
    """G51's probe_nv: "megalippe", which the image judges not visible, and "Hubner" / "Hiibner" on the
    next line. The line may go on with the taxon, so the walk is main's: past the not-visible unit to the
    differing one the image names, which blocks."""
    rows = [(1, "Danaus", "Danaus"), (1, "plexippus", "plexippus"), (2, "megalippe", ""), (2, "Hubner", "Hiibner")]
    readings = label_of(rows, ["b", "b", NOT_VISIBLE, "a"])
    assert not agreement.image_names(readings["b"], "Danaus plexippus", key="taxon")
    assert not agreement.image_names(readings["b"], "Danaus plexippus")


@pytest.mark.parametrize(("key", "rows", "literal", "named"), [
    ("elevation_from_ft", [(1, "4800 ft.", "4800 ft."), (2, "Elev. 1200", "Elev. 1250")], "4800 ft.", False),
    ("elevation_from_ft", [(1, "4800 ft.", "4800 ft."), (2, "IV-24-48", "IV-24-46")], "4800 ft.", True),
    ("habitat", [(1, "forest", "forest"), (2, "Elev. 1200", "Elev. 1250")], "forest", True),
    ("date_identified", [(1, "1950", "1950"), (2, "Elev. 1200", "Elev. 1250")], "1950", False),
], ids=["an-elevation-below-an-elevation", "a-date-below-an-elevation", "an-elevation-below-a-habitat",
    "a-date-field-keeps-its-line-breaks"])
def test_only_another_kind_s_text_on_the_next_line_bounds_nothing(first_pass_path, key, rows, literal, named):
    """The coordinator's ruling on G51's round 1: "another kind" is a kind other than the field's own, so an
    elevation on the next line may go on with an elevation field and keeps main's walk; and the stop never
    applies to a field whose brief keeps line breaks (agreement.KEEPS_LINE_BREAKS: the dates, verbatim
    D/T/S, the precise location)."""
    readings = label_of(rows, ["a", "a"])
    assert agreement.image_names(readings["a"], literal, key=key) is named


@pytest.mark.parametrize(("settled", "named"), [(("Yepocapa",), True), ((), False), (("Yepo",), False)],
    ids=["another-field-s-text", "no-settled-text", "not-a-whole-word"])
def test_a_line_that_is_another_settled_field_s_text_bounds_nothing(first_pass_path, settled, named):
    """The line-break stop by another settled field's text (agreement.image_names' `settled`, from
    step._settled_texts): "forest" below "Yepocapa," / "Yepocapa" bounds nothing for the habitat when
    the city settled on "Yepocapa", blanked as a whole word, the comma left; with no such text, or one
    that is no whole word of the line, main's walk."""
    rows = [(1, "Yepocapa,", "Yepocapa"), (2, "forest", "forest")]
    readings = label_of(rows, ["a", "a"])
    assert agreement.image_names(readings["a"], "forest", key="habitat", settled=settled) is named


# ---- 5. an elevation whose expert names two (#437's G51 review, the coordinator's ruling) --------

@pytest.mark.parametrize("other", ["5000 ft.", "3300 ft."])
def test_an_elevation_whose_options_name_two_numbers_stays_held_on_both_paths(tmp_path, first_pass_path, other):
    """The named case: reader A writes "Elev.6400", reader B "Elev.6400'", and both write "Camp at <n> ft.";
    the elevation expert answers several_possibilities ["6400", "<n> ft."]. The settlement does not clear
    "<n> ft." because it alone carries a unit (step._by_rule, step.elevation_numbers): the field stays
    ambiguous with no cleared finding, and no partner is derived from it, on both paths, as the old path
    keeps it on origin/main 7f412f91d (where the units path cleared it)."""
    from test_elevations_and_extent import PARTNERS, PHILIPPINES, NO_PLACES_BELOW, elevation_label

    text, second = elevation_label("Elev.6400", "Elev.6400'")
    text, second = (body.replace("habitat: Synthetic grassland", f"habitat: Camp at {other}") for body in (text, second))
    rig = build_rig(tmp_path, text, second)
    several = FieldAnswer(outcome="several_possibilities", options=["6400", other],
        explanation="The label writes two elevations.")
    settle(rig, Scripted({**PHILIPPINES, **NO_PLACES_BELOW, "elevation_from_ft": answering(several),
        **dict.fromkeys(PARTNERS, answering(LACKS))}))
    run = rig.specimen.run
    value = run.fields["elevation_from_ft"]
    assert value.state == ValueState.AMBIGUOUS and value.literal is None
    assert not [f for f in run.findings if f.field_key == "elevation_from_ft" and f.reason_code.startswith("cleared:")]
    assert all(run.fields[key].parsed is None and run.fields[key].layer != "derived" for key in PARTNERS)


def test_the_elevations_an_expert_s_options_name():
    """step.elevation_numbers: one elevation however it is written, a range as one, two when the options
    write two."""
    assert field_step.elevation_numbers(["6400", "5000 ft."]) == {("6400",), ("5000",)}
    assert field_step.elevation_numbers(["Elev.6400", "Elev.6400'"]) == {("6400",)}
    assert field_step.elevation_numbers(["1,500 m", "1500"]) == {("1500",)}
    assert field_step.elevation_numbers(["1200-1500 m", "1200-1500"]) == {("1200", "1500")}
    assert field_step.elevation_numbers(["Elev. +800 ft.", "Elev. 4800 ft."]) == {("800",), ("4800",)}
    assert field_step.elevation_numbers(["ca.", ""]) == set()


@pytest.mark.parametrize("asked", [False, True], ids=["first", "re-ask"])
def test_a_re_ask_s_lookup_answer_does_not_repeat_its_call(first_pass_path, asked):
    """experts._Expert.lookup: in a re-ask's requests on the units path (FieldTask.reask) a lookup's answer
    leaves out the source and the query its call carries, which keeps the re-ask under the input bound
    (test_units_request_size.py); every other request keeps them, as on origin/main."""
    from specimen_digitization.application.domain import LookupStatus
    from specimen_digitization.field_research.contracts import SourceAnswer

    class One:
        sources = ("tgn",)

        async def lookup(self, source_id, query, *, field_key):
            return SourceAnswer(source_id, query, LookupStatus.NO_MATCH, (), None, note="nothing")

    readings = (Reading("1A", "r1", "o1a", "raw_reading", "Davao Prov."), Reading("1B", "r1", "o1b", "raw_reading",
        "Davao Prov."))
    if first_pass_path == "units":
        readings = with_units(readings)
    task = FieldTask("province_state", True, FieldValue(), (), ("tgn",), reask=ASKED if asked else None)
    got = asyncio.run(experts._Expert(task, readings, One(), None).lookup("tgn", "Davao, Philippines"))
    if first_pass_path == "units" and asked:
        assert "source" not in got and "query" not in got and got["status"] == "no_match"
    else:
        assert (got["source"], got["query"]) == ("tgn", "Davao, Philippines")
