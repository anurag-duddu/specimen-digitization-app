"""One expert per field (FIELD_RESEARCH.md steps 3 to 5), driven by scripted models.

Each test scripts the model with a pydantic_ai FunctionModel and answers lookups
from a fake SourceTools, so nothing leaves the process and nothing is paid for.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic_ai import ModelRetry
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.instrumented import InstrumentationSettings

from specimen_digitization.application.domain import Evidence, FieldValue, LookupStatus, ValueState
from specimen_digitization.field_research import agreement, experts
from specimen_digitization.field_research.checks import collapse
from specimen_digitization.field_research.budget import CostMeter
from specimen_digitization.field_research.contracts import (
    FIELD_TOOLS,
    Candidate,
    FieldAnswer,
    FieldTask,
    PlaceRef,
    Reading,
    SourceAnswer,
    SourceCandidate,
)
from specimen_digitization.field_research.experts import EXHAUSTED, INPUT_PREFIX, make_resolver

PILOT_DATES = {
    "version": "date-rules-v1", "two_digit_year_century": 1900, "roman_numeral_months": True,
}
READINGS = (
    Reading("1A", "region-1", "obs-1a", "decided_transcript",
            "Epipsocus sp. 1\nP.I. Mindanao, Davao\n4-5-48 coll. F. G. Werner"),
    Reading("1B", "region-1", "obs-1b", "raw_reading",
            "Epipsocus sp. 1\nP.I. Mindanao Davao\n4-5-48 coll. F.G. Werner"),
    Reading("2A", "region-2", "obs-2a", "raw_reading", "alt. 1500 ft\nca. 1200 m"),
)
CONTEXT = {
    "country": FieldValue(state=ValueState.SUPPORTED, literal="P.I."),
    "city": FieldValue(state=ValueState.AMBIGUOUS,
                       verbatim_by_observation={"obs-1a": "Davao", "obs-1b": "Davao"}),
    "habitat": FieldValue(),
}
# As sources.py stores a success: the locator is the candidate GBIF decided.
GBIF_EVIDENCE = Evidence(id="ev-gbif-1", kind="authority", source="gbif", locator="gbif:1234",
                         excerpt="Epipsocus Hagen, 1866")
GBIF_SUCCESS = SourceAnswer(
    source_id="gbif",
    query="Epipsocus",
    status=LookupStatus.SUCCESS,
    candidates=(SourceCandidate("Epipsocus Hagen, 1866", "gbif:1234", "GENUS", "Psocodea"),),
    evidence=GBIF_EVIDENCE,
    note="GBIF: exact accepted match at genus rank",
    taxonomy_lookup={"lookup": "gbif-1"},
)


# The organiser's candidates for READINGS: a resolved literal is one of them (B2).
OFFERED = {
    "taxon": [("1A", "Epipsocus sp. 1"), ("1B", "Epipsocus sp. 1")],
    "country": [("1A", "P.I."), ("1B", "P.I.")],
    "city": [("1A", "Davao"), ("1B", "Davao")],
    "precise_location": [("1A", "Mindanao, Davao")],
    "date_visited_from": [("1A", "4-5-48"), ("1B", "4-5-48")],
    "elevation_from_ft": [("2A", "1500")],
    "collectors": [("1A", "F. G. Werner"), ("1B", "F.G. Werner")],
}


def offered(*pairs) -> list[Candidate]:
    """Organiser candidates ((reading, literal)), each quoting its literal."""
    return [Candidate(name, literal, literal, f"ev-{name}-{literal}") for name, literal in pairs]


def task(key: str, *, current: FieldValue | None = None, candidates=None) -> FieldTask:
    """The field's task with `candidates`, by default the organiser's for READINGS."""
    found = offered(*OFFERED.get(key, ())) if candidates is None else candidates
    return FieldTask(key=key, mandatory=True, current=current or FieldValue(),
                     candidates=tuple(found), tools=FIELD_TOOLS[key])


def meter(cap: int = 1_000_000) -> CostMeter:
    return CostMeter(cap, input_micros_per_million=200_000, output_micros_per_million=600_000)


class FakeTools:
    """A record's approved sources, answering from a table."""

    def __init__(self, answers=None, sources=("gbif", "geolocate", "tgn", "wikidata", "nga")):
        self.answers = dict(answers or {})
        self.sources = tuple(sources)
        self.calls: list[tuple[str, str, str]] = []

    async def lookup(self, source_id: str, query: str, *, field_key: str) -> SourceAnswer:
        self.calls.append((source_id, query, field_key))
        answer = self.answers[(source_id, query)]
        if isinstance(answer, BaseException):
            raise answer
        return answer


Step = Callable[[list[ModelMessage], AgentInfo], ModelResponse]


class Script:
    """A model that plays its steps in order and records what each request saw."""

    def __init__(self, *steps: Step | dict) -> None:
        self.steps = list(steps)
        self.seen: list[tuple[list[ModelMessage], AgentInfo]] = []

    def __call__(self, messages, info):
        self.seen.append((list(messages), info))
        step = self.steps.pop(0)
        return step(messages, info) if callable(step) else final(**step)(messages, info)

    def model(self):
        return FunctionModel(self)


def final(**answer) -> Step:
    answer.setdefault("explanation", "Scripted answer.")
    return lambda messages, info: ModelResponse(
        parts=[ToolCallPart(info.output_tools[0].name, answer)])


def call(tool: str, **args) -> Step:
    return lambda messages, info: ModelResponse(parts=[ToolCallPart(tool, args)])


def retries(messages: list[ModelMessage]) -> list[str]:
    return [part.model_response() for m in messages if isinstance(m, ModelRequest)
            for part in m.parts if isinstance(part, RetryPromptPart)]


def tool_returns(messages: list[ModelMessage]) -> list[object]:
    return [part.content for m in messages if isinstance(m, ModelRequest)
            for part in m.parts if isinstance(part, ToolReturnPart)]


def resolve(script: Script, field: FieldTask, tools=None, *, cost: CostMeter | None = None, **kw):
    resolver = make_resolver(model_factory=script.model, meter=cost or meter(),
                             date_rules=PILOT_DATES, **kw)
    return asyncio.run(resolver(field, READINGS, CONTEXT, tools=tools or FakeTools()))


GBIF_ANSWER = dict(
    outcome="resolved", literal="Epipsocus sp. 1", reading_names=["1A", "1b"],
    value="Epipsocus Hagen, 1866", authority_id="gbif:1234", source_evidence_ids=["ev-gbif-1"],
    explanation="GBIF matches the genus Epipsocus exactly; sp. 1 is genus-level (G25).",
)


def test_a_taxon_resolves_on_a_cited_gbif_success():
    tools = FakeTools({("gbif", "Epipsocus"): GBIF_SUCCESS})
    script = Script(call("lookup", source="gbif", query="Epipsocus"), GBIF_ANSWER)
    cost = meter()

    outcome = resolve(script, task("taxon"), tools, cost=cost)

    assert outcome.failure is None
    assert outcome.answer.outcome == "resolved"
    assert outcome.answer.reading_names == ["1A", "1B"]  # named as the readings name themselves
    assert outcome.answer.value == "Epipsocus Hagen, 1866"
    assert outcome.evidence == [GBIF_EVIDENCE]
    assert outcome.lookups == [{"lookup": "gbif-1"}]
    assert tools.calls == [("gbif", "Epipsocus", "taxon")]
    assert outcome.model_calls == 2 and outcome.cost_micros == cost.spent_micros > 0
    # The model saw the source's answer compactly, with the id to cite.
    shown = tool_returns(script.seen[1][0])[0]
    assert shown["evidence_id"] == "ev-gbif-1" and shown["status"] == "success"
    assert shown["candidates"] == [{"name": "Epipsocus Hagen, 1866", "authority_id": "gbif:1234",
                                    "kind": "GENUS", "detail": "Psocodea"}]


def test_the_expert_gets_its_brief_its_tools_and_every_reading_as_evidence():
    script = Script(dict(outcome="sources_cannot_resolve", explanation="No lookup made."))

    resolve(script, task("taxon", current=FieldValue(
        state=ValueState.AMBIGUOUS, verbatim_by_observation={"obs-1a": "Epipsocus sp. 1"}),
        candidates=[Candidate("1A", "Epipsocus sp. 1", "Epipsocus sp. 1", "ev-1")]))

    messages, info = script.seen[0]
    assert "You are the expert for ONE field" in info.instructions
    assert "Field: Taxon (taxon)" in info.instructions
    assert "Field: Country (country)" not in info.instructions
    assert [tool.name for tool in info.function_tools] == ["lookup"]
    lookup = info.function_tools[0]
    assert "gbif: the whole scientific name" in lookup.description and "geolocate" not in lookup.description
    assert lookup.parameters_json_schema["properties"]["source"]["enum"] == ["gbif"]
    assert info.model_settings["max_tokens"] == 2048 and info.model_settings["temperature"] == 0
    [request] = messages
    [prompt] = [p.content for p in request.parts if isinstance(p, UserPromptPart)]
    assert prompt.startswith(INPUT_PREFIX)
    document = json.loads(prompt.removeprefix(INPUT_PREFIX))
    assert document["field"] == {"key": "taxon", "label": "Taxon"}
    assert [r["name"] for r in document["readings"]] == ["1A", "1B", "2A"]
    assert document["readings"][0]["text"] == READINGS[0].text
    assert document["organiser_value"]["verbatim_by_observation"] == {"1A": "Epipsocus sp. 1"}
    assert document["organiser_candidates"] == [
        {"reading": "1A", "quote": "Epipsocus sp. 1", "literal": "Epipsocus sp. 1"}]
    assert document["other_fields"] == {"country": "P.I.", "city": ["Davao"]}


@pytest.mark.parametrize(
    ("key", "tools"),
    [("date_visited_from", ["parse_date"]), ("elevation_from_ft", ["parse_elevation"]),
     ("fmnh_ins_number", ["check_catalog_number"]), ("collectors", [])],
)
def test_each_field_gets_only_its_own_tools(key, tools):
    script = Script(dict(outcome="label_lacks_value"))

    resolve(script, task(key))

    assert [tool.name for tool in script.seen[0][1].function_tools] == tools


def test_every_call_starts_with_fresh_context():
    script = Script(dict(outcome="label_lacks_value"), dict(outcome="label_lacks_value"))
    resolver = make_resolver(model_factory=script.model, meter=meter())

    async def twice():
        await resolver(task("habitat"), READINGS, CONTEXT, tools=FakeTools())
        await resolver(task("habitat"), READINGS, CONTEXT, tools=FakeTools())

    asyncio.run(twice())

    assert [len(messages) for messages, _ in script.seen] == [1, 1]


def test_a_literal_not_in_the_reading_is_sent_back_then_accepted_when_corrected():
    script = Script(
        dict(outcome="resolved", literal="F.G. Werner", reading_names=["1A"]),
        dict(outcome="resolved", literal="F. G. Werner", reading_names=["1A"]),
    )

    outcome = resolve(script, task("collectors"))

    assert outcome.failure is None
    assert (outcome.answer.literal, outcome.answer.reading_names) == ("F. G. Werner", ["1A"])
    [message] = retries(script.seen[1][0])
    assert "does not contain the literal 'F.G. Werner' exactly" in message
    assert outcome.model_calls == 2


def test_a_value_from_no_received_candidate_is_refused():
    tools = FakeTools({("gbif", "Epipsocus"): GBIF_SUCCESS})
    invented = {**GBIF_ANSWER, "value": "Epipsocus Banks, 1920", "authority_id": None}
    script = Script(call("lookup", source="gbif", query="Epipsocus"), invented, GBIF_ANSWER)

    outcome = resolve(script, task("taxon"), tools)

    assert outcome.answer.value == "Epipsocus Hagen, 1866"
    [message] = retries(script.seen[2][0])
    assert "'Epipsocus Banks, 1920' differs from the literal" in message


def test_an_expert_that_keeps_inventing_a_value_goes_to_review():
    tools = FakeTools({("gbif", "Epipsocus"): GBIF_SUCCESS})
    invented = {**GBIF_ANSWER, "value": "Epipsocus Banks, 1920", "authority_id": None}
    script = Script(call("lookup", source="gbif", query="Epipsocus"), invented, invented, invented)

    outcome = resolve(script, task("taxon"), tools)

    # Not an outage, so never a retry: a person reads the field.
    assert outcome.failure is None
    assert outcome.answer == FieldAnswer(outcome="sources_cannot_resolve", explanation=experts.UNCHECKED)
    assert experts.UNCHECKED == "The expert's answer could not be checked against the readings and sources."
    assert outcome.evidence == [GBIF_EVIDENCE]  # what it gathered is still reported
    assert outcome.model_calls == 4
    # The resolver's answer, not the expert's (owner decision B never clears on it).
    assert outcome.fallback


GBIF_TWO = SourceAnswer(
    source_id="gbif", query="Epipsocus", status=LookupStatus.SUCCESS,
    candidates=(SourceCandidate("Epipsocus Hagen, 1866", "gbif:1234", "GENUS"),
                SourceCandidate("Episcopus Other, 1900", "gbif:2", "GENUS", "alternative, fuzzy match")),
    evidence=GBIF_EVIDENCE, note="success",
)
GBIF_UNRELATED = SourceAnswer(
    source_id="gbif", query="Bombus impatiens", status=LookupStatus.SUCCESS,
    candidates=(SourceCandidate("Bombus impatiens Cresson, 1863", "gbif:999", "SPECIES"),),
    evidence=Evidence(id="ev-gbif-9", kind="authority", source="gbif", locator="gbif:999",
                      excerpt="Bombus impatiens Cresson, 1863"),
    note="success",
)


@pytest.mark.parametrize(("received", "given", "says"), [
    # GBIF was asked about a name no reading writes (the reviewer's first probe).
    (GBIF_UNRELATED, dict(literal="Epipsocus sp. 1", value="Bombus impatiens Cresson, 1863",
                          authority_id="gbif:999", source_evidence_ids=["ev-gbif-9"]),
     "query must be that whole scientific name"),
    # The alternative GBIF listed, not the candidate it decided (the second probe).
    (GBIF_TWO, dict(literal="Epipsocus sp. 1", value="Episcopus Other, 1900", authority_id="gbif:2",
                    source_evidence_ids=["ev-gbif-1"]), "the candidate GBIF decided"),
    # The decided candidate's id with another candidate's name.
    (GBIF_TWO, dict(literal="Epipsocus sp. 1", value="Episcopus Other, 1900", authority_id="gbif:1234",
                    source_evidence_ids=["ev-gbif-1"]), "differs from the literal"),
    # G25: a genus-level identification is settled on its genus alone.
    (GBIF_SUCCESS, dict(literal="Epipsocus sp. 1", value="Epipsocus Hagen, 1866",
                        authority_id="gbif:1234", source_evidence_ids=["ev-gbif-1"]), None),
])
def test_a_taxon_resolves_only_on_the_candidate_gbif_decided_for_its_literal(received, given, says):
    made = expert("taxon", [received])
    given_answer = answer(outcome="resolved", reading_names=["1A"], **given)

    if says is None:
        assert made.validate(given_answer).value == given["value"]
        return
    with pytest.raises(ModelRetry, match=says):
        made.validate(given_answer)


@pytest.mark.parametrize(("literal", "query", "says"), [
    # GBIF's answer for part of the name the label writes (the review's B2).
    ("Danaus plexippus megalippe", "Danaus plexippus", "whole scientific name"),
    ("Bombus impatiens on Solidago canadensis", "Solidago canadensis", "whole scientific name"),
    ("Danaus plexippus megalippe", "Danaus plexippus megalippe", None),
    ("Epipsocus sp.", "Epipsocus", None),  # G25: a genus-level identification, at genus rank
])
def test_a_taxon_resolves_only_on_gbifs_answer_for_the_whole_name_its_literal_writes(literal, query, says):
    readings = (Reading("1A", "region-1", "obs-1a", "decided_transcript", literal + "\nleg. F. G. Werner"),)
    found = SourceAnswer("gbif", query, LookupStatus.SUCCESS, (SourceCandidate("Decided name", "gbif:7"),),
                         Evidence(id="ev-gbif-7", kind="authority", source="gbif", locator="gbif:7",
                                  excerpt="Decided name"), note="success")
    made = experts._Expert(task("taxon", candidates=offered(("1A", literal))), readings, FakeTools(), PILOT_DATES)
    made.calls.append(experts._Call("gbif", query, LookupStatus.SUCCESS, found))
    given = answer(outcome="resolved", literal=literal, reading_names=["1A"], value="Decided name",
                   authority_id="gbif:7", source_evidence_ids=["ev-gbif-7"])

    if says is None:
        assert made.validate(given).value == "Decided name"
        return
    with pytest.raises(ModelRetry, match=says):
        made.validate(given)


# A resolved literal is a whole organiser candidate (the second review's B2).

DANAUS = SourceAnswer("gbif", "Danaus plexippus", LookupStatus.SUCCESS,
                      (SourceCandidate("Danaus plexippus (Linnaeus, 1758)", "5133088", "SPECIES"),),
                      Evidence(id="ev-species", kind="authority", source="gbif", locator="5133088",
                               excerpt="Danaus plexippus (Linnaeus, 1758) | 5133088 | SPECIES | "), note="exact")
GENUS = SourceAnswer("gbif", "Danaus", LookupStatus.SUCCESS,
                     (SourceCandidate("Danaus Kluk, 1780", "5133074", "GENUS"),),
                     Evidence(id="ev-genus", kind="authority", source="gbif", locator="5133074",
                              excerpt="Danaus Kluk, 1780 | 5133074 | GENUS | "), note="exact")
SAN_PEDRO = SourceAnswer("geolocate", "San Pedro, Guatemala", LookupStatus.SUCCESS,
                         (SourceCandidate("San Pedro", "geolocate:1"),),
                         Evidence(id="ev-town", kind="authority", source="geolocate", locator="geolocate:1",
                                  excerpt="San Pedro"), note="match")


@pytest.mark.parametrize(("key", "written", "piece", "received", "rest"), [
    # Both readers write the trinomial; the answer is the binomial GBIF was asked.
    ("taxon", "Danaus plexippus megalippe", "Danaus plexippus", DANAUS,
     dict(value="Danaus plexippus (Linnaeus, 1758)", authority_id="5133088", source_evidence_ids=["ev-species"])),
    # A species label answered at its genus.
    ("taxon", "Danaus plexippus", "Danaus", GENUS,
     dict(value="Danaus Kluk, 1780", authority_id="5133074", source_evidence_ids=["ev-genus"])),
    # The day dropped from a date, which then parses at month precision.
    ("date_visited_from", "3 Sept. '46", "Sept. '46", None, dict(value="1946-09")),
    # A town cut out of its whole name, which GEOLocate then finds.
    ("city", "San Pedro Sacatepequez", "San Pedro", SAN_PEDRO,
     dict(authority_id="geolocate:1", source_evidence_ids=["ev-town"])),
])
def test_a_resolved_literal_is_a_whole_candidate_never_a_piece_of_a_reading(key, written, piece, received, rest):
    readings = tuple(Reading(name, "region-1", f"obs-{name}", "raw_reading", f"{written}\nleg. F. G. Werner")
                     for name in ("1A", "1B"))
    made = experts._Expert(task(key, candidates=offered(("1A", written), ("1B", written))), readings,
                           FakeTools(), PILOT_DATES)
    if received is not None:
        made.calls.append(experts._Call(received.source_id, received.query, received.status, received))
    if key == "date_visited_from":
        assert asyncio.run(made.parse_date(piece))["status"] == "success"
    given = answer(outcome="resolved", literal=piece, reading_names=["1A", "1B"], **rest)

    with pytest.raises(ModelRetry, match="whole and exactly as the candidate gives it") as refused:
        made.validate(given)
    assert f"1A: {written!r}" in str(refused.value) and "Never shorten" in str(refused.value)
    assert agreement.literal_refusal(made.task, readings, literal=written, named=readings) is None


def test_an_expert_that_shortens_the_name_after_the_whole_name_retry_goes_to_review():
    """The review's B2 at the real expert: GBIF was asked part of the name the
    label writes; the retry asks for the whole name, and an answer that
    shortens the literal to that part instead is sent back too."""
    tri = "Danaus plexippus megalippe"
    readings = (Reading("1A", "r1", "o1a", "decided_transcript", tri + "\nleg. F. G. Werner"),
                Reading("1B", "r1", "o1b", "raw_reading", tri + "\nleg. F. G. Werner"))
    field = task("taxon", current=FieldValue(state=ValueState.SUPPORTED, literal=tri),
                 candidates=offered(("1A", tri), ("1B", tri)))
    first = dict(outcome="resolved", literal=tri, reading_names=["1A"], value="Danaus plexippus (Linnaeus, 1758)",
                 authority_id="5133088", source_evidence_ids=["ev-species"], explanation="GBIF")
    shortened = dict(first, literal="Danaus plexippus")
    script = Script(call("lookup", source="gbif", query="Danaus plexippus"), first, shortened, shortened)
    resolver = make_resolver(model_factory=script.model, meter=meter(), date_rules=PILOT_DATES)

    outcome = asyncio.run(resolver(field, readings, {}, tools=FakeTools({("gbif", "Danaus plexippus"): DANAUS})))

    assert outcome.failure is None
    assert outcome.answer == FieldAnswer(outcome="sources_cannot_resolve", explanation=experts.UNCHECKED)
    whole, piece = retries(script.seen[-1][0])
    assert f"the whole name {tri!r} writes" in whole and "Keep the literal whole" in whole
    assert "whole and exactly as the candidate gives it" in piece


def test_a_taxon_candidate_whose_quote_writes_a_longer_name_is_sent_back():
    """The third review's N3 at the expert: both readers' candidate is the
    binomial, quoting the trinomial line, and GBIF was asked the binomial."""
    tri = "Danaus plexippus megalippe"
    readings = tuple(Reading(name, "r1", f"o{name}", "raw_reading", tri + "\nleg. F. G. Werner")
                     for name in ("1A", "1B"))
    cut = task("taxon", candidates=[Candidate(name, tri, "Danaus plexippus", f"ev-{name}") for name in ("1A", "1B")])
    made = experts._Expert(cut, readings, FakeTools(), PILOT_DATES)
    made.calls.append(experts._Call("gbif", DANAUS.query, DANAUS.status, DANAUS))
    given = answer(outcome="resolved", literal="Danaus plexippus", reading_names=["1A", "1B"],
                   value="Danaus plexippus (Linnaeus, 1758)", authority_id="5133088",
                   source_evidence_ids=["ev-species"])

    with pytest.raises(ModelRetry, match="writes the longer name 'Danaus plexippus megalippe'"):
        made.validate(given)
    refused = agreement.literal_refusal(cut, readings, literal="Danaus plexippus", named=readings)
    assert refused.reason == agreement.PART_OF_NAME
    # A keyed line's candidate quotes its key and the same name: it settles.
    keyed = task("taxon", candidates=[Candidate(name, "taxon: Danaus plexippus", "Danaus plexippus", f"ev-{name}")
                                      for name in ("1A", "1B")])
    plain = tuple(Reading(name, "r1", f"o{name}", "raw_reading", "taxon: Danaus plexippus") for name in ("1A", "1B"))
    assert agreement.literal_refusal(keyed, plain, literal="Danaus plexippus", named=plain) is None


def test_a_code_candidate_whose_quote_writes_a_genus_before_it_is_a_piece_of_the_name():
    """B1 of #289's review: a candidate "sp. 1" quoting "Epipsocus sp. 1", or
    "Epipsocus" with "sp. 1" on the next line, cuts the genus off its name."""
    code = "sp. 1 \N{FEMALE SIGN}"
    for written in ("Epipsocus " + code, "Epipsocus\n" + code):
        readings = tuple(Reading(name, "r1", f"o{name}", "raw_reading", written) for name in ("1A", "1B"))
        cut = task("taxon", candidates=[Candidate(name, written, code, f"ev-{name}") for name in ("1A", "1B")])
        refused = agreement.literal_refusal(cut, readings, literal=code, named=readings)
        assert refused is not None and refused.reason == agreement.PART_OF_NAME
        assert "writes the longer name 'Epipsocus'" in refused.retry
    # The code on a line of its own, below a line with no genus at its end, settles.
    alone = "Mossy forest 6400'\n" + code
    readings = tuple(Reading(name, "r1", f"o{name}", "raw_reading", alone) for name in ("1A", "1B"))
    own = task("taxon", candidates=[Candidate(name, alone, code, f"ev-{name}") for name in ("1A", "1B")])
    assert agreement.literal_refusal(own, readings, literal=code, named=readings) is None


def test_the_reviewers_taxon_probes_end_in_review_not_resolved():
    for received, value, authority in ((GBIF_UNRELATED, "Bombus impatiens Cresson, 1863", "gbif:999"),
                                       (GBIF_TWO, "Episcopus Other, 1900", "gbif:2")):
        tools = FakeTools({("gbif", received.query): received})
        given = dict(outcome="resolved", literal="Epipsocus sp. 1", reading_names=["1A"], value=value,
                     authority_id=authority, source_evidence_ids=[received.evidence.id])
        script = Script(call("lookup", source="gbif", query=received.query), given, given, given)

        outcome = resolve(script, task("taxon"), tools)

        assert outcome.answer.outcome == "sources_cannot_resolve" and outcome.failure is None


def test_label_lacks_value_carries_no_value():
    script = Script(
        dict(outcome="label_lacks_value", literal="Davao"),
        dict(outcome="label_lacks_value", explanation="No reading names a county."),
    )

    outcome = resolve(script, task("county"))

    assert outcome.failure is None and outcome.answer.outcome == "label_lacks_value"
    assert outcome.answer.literal is None
    assert "leave literal, value and authority_id empty" in retries(script.seen[1][0])[0]


def test_several_possibilities_from_a_date_check():
    script = Script(
        call("parse_date", literal="4-5-48"),
        dict(outcome="several_possibilities", options=["1948-04-05", "1948-06-04"]),
        dict(outcome="several_possibilities", options=["1948-04-05", "1948-05-04"],
             literal="4-5-48", reading_names=["1A", "1B"]),
    )

    outcome = resolve(script, task("date_visited_from"))

    assert outcome.failure is None
    assert outcome.answer.options == ["1948-04-05", "1948-05-04"]
    assert tool_returns(script.seen[1][0])[0]["status"] == "ambiguous"
    assert "'1948-06-04' is not text a reading contains" in retries(script.seen[2][0])[0]


def test_one_reading_of_an_ambiguous_date_is_sent_back_and_both_go_to_review():
    script = Script(
        call("parse_date", literal="4-5-48"),
        dict(outcome="resolved", literal="4-5-48", reading_names=["1A"], value="1948-04-05",
             explanation="Another label writes the month by name."),
        dict(outcome="several_possibilities", options=["1948-04-05", "1948-05-04"],
             literal="4-5-48", reading_names=["1A"], explanation="Day and month can be read either way."),
    )

    outcome = resolve(script, task("date_visited_from"))

    assert tool_returns(script.seen[1][0])[0]["status"] == "ambiguous"
    assert "'1948-04-05' differs from the literal" in retries(script.seen[2][0])[0]
    assert outcome.failure is None and outcome.answer.outcome == "several_possibilities"
    assert outcome.answer.options == ["1948-04-05", "1948-05-04"]


def test_a_resolved_value_comes_from_a_check_that_settles_the_literal():
    script = Script(
        call("parse_elevation", literal="1500 ft"),
        dict(outcome="resolved", literal="1500 ft", reading_names=["2A"], value="1500"),
    )

    outcome = resolve(script, task("elevation_from_ft", candidates=offered(("2A", "1500 ft"))))

    assert tool_returns(script.seen[1][0])[0]["status"] == "success"
    assert outcome.failure is None and outcome.answer.value == "1500"


@pytest.mark.parametrize("failure", [
    SourceAnswer("gbif", "Epipsocus", LookupStatus.TIMEOUT, (), None, "GBIF timed out"),
    RuntimeError("socket closed"),
])
def test_a_source_outage_leaves_the_field_for_retry(failure):
    tools = FakeTools({("gbif", "Epipsocus"): failure})
    script = Script(
        call("lookup", source="gbif", query="Epipsocus"),
        dict(outcome="sources_cannot_resolve", explanation="GBIF did not answer."),
    )

    outcome = resolve(script, task("taxon"), tools)

    assert outcome.failure == "source_unavailable"
    assert outcome.answer.outcome == "sources_cannot_resolve"  # kept for the retry
    assert tool_returns(script.seen[1][0])[0]["status"] in {"timeout", "provider_error"}


TGN_DOWN = SourceAnswer("tgn", "Davao", LookupStatus.AUTHORIZATION, (), None,
                        "Getty TGN refused the request with HTTP 403")
WIKIDATA_NONE = SourceAnswer("wikidata", "Davao", LookupStatus.NO_MATCH, (),
                             Evidence(id="ev-wd-1", kind="lookup", source="wikidata", locator=None,
                                      excerpt="Wikidata has no place for 'Davao'"),
                             "Wikidata has no place for 'Davao'")


@pytest.mark.parametrize("answer", [
    dict(outcome="sources_cannot_resolve", literal="Davao", reading_names=["1A"],
         explanation="Getty TGN did not answer; Wikidata has no town Davao."),
    dict(outcome="label_lacks_value", explanation="No reading names a town."),
    dict(outcome="several_possibilities", options=["Davao", "Mindanao"],
         explanation="The town may be either."),
])
def test_one_source_down_among_several_leaves_the_experts_own_answer(answer):
    """One dead source does not void the field: Wikidata answered, so the
    expert's unresolved answer stands for review, naming Getty TGN."""
    tools = FakeTools({("tgn", "Davao"): TGN_DOWN, ("wikidata", "Davao"): WIKIDATA_NONE})
    script = Script(
        lambda messages, info: ModelResponse(parts=[
            ToolCallPart("lookup", {"source": "tgn", "query": "Davao"}),
            ToolCallPart("lookup", {"source": "wikidata", "query": "Davao"})]),
        answer,
    )

    outcome = resolve(script, task("city"), tools)

    assert outcome.failure is None and outcome.answer.outcome == answer["outcome"]
    assert outcome.unreachable == ("tgn",)
    assert outcome.evidence == [WIKIDATA_NONE.evidence]


@pytest.mark.parametrize("others", [
    # Every lookup failed operationally: Wikidata timed out too.
    {("wikidata", "Davao"): SourceAnswer("wikidata", "Davao", LookupStatus.TIMEOUT, (), None)},
    # A refused query is no answer either.
    {("geolocate", "Davao"): SourceAnswer("geolocate", "Davao", LookupStatus.POLICY, (), None)},
])
def test_an_expert_none_of_whose_lookups_answered_waits_for_a_retry(others):
    tools = FakeTools({("tgn", "Davao"): TGN_DOWN, **others})
    [(source, query)] = others
    script = Script(
        lambda messages, info: ModelResponse(parts=[
            ToolCallPart("lookup", {"source": "tgn", "query": "Davao"}),
            ToolCallPart("lookup", {"source": source, "query": query})]),
        dict(outcome="sources_cannot_resolve", explanation="No source answered."),
    )

    outcome = resolve(script, task("city"), tools)

    assert outcome.failure == "source_unavailable"
    unreachable = ("tgn", "wikidata") if source == "wikidata" else ("tgn",)
    assert outcome.unreachable == unreachable


def test_a_query_that_later_succeeds_clears_its_outage():
    tools = FakeTools({("gbif", "Epipsocus"): GBIF_SUCCESS})
    script = Script(
        call("lookup", source="gbif", query="Epipsocus"),
        dict(outcome="sources_cannot_resolve", explanation="GBIF answered; not settled."),
    )
    flaky = iter([SourceAnswer("gbif", "Epipsocus", LookupStatus.RATE_LIMITED, (), None)])

    async def lookup(source_id, query, *, field_key):
        return next(flaky, GBIF_SUCCESS)

    tools.lookup = lookup  # type: ignore[method-assign]
    script.steps.insert(1, call("lookup", source="gbif", query="Epipsocus"))

    outcome = resolve(script, task("taxon"), tools)

    assert outcome.failure is None and outcome.answer.outcome == "sources_cannot_resolve"


def test_an_unapproved_source_is_refused_without_a_call():
    tools = FakeTools(sources=("geolocate",))
    script = Script(call("lookup", source="tgn", query="Davao"),
                    dict(outcome="sources_cannot_resolve", explanation="No source settled it."))

    outcome = resolve(script, task("city"), tools)

    assert tools.calls == []
    refused = tool_returns(script.seen[1][0])[0]
    assert refused["status"] == "policy_blocked" and "geolocate" in refused["note"]
    assert outcome.failure is None  # a refusal is not an outage


def test_a_budget_that_cannot_fit_a_call_fails_the_field():
    script = Script(dict(outcome="label_lacks_value"))

    outcome = resolve(script, task("habitat"), cost=meter(cap=100))

    assert outcome.failure == "budget_exhausted" and outcome.answer is None
    assert script.seen == [] and outcome.model_calls == 0


def test_a_request_over_the_input_bound_fails_the_field_as_too_large_not_as_the_cost_limit():
    script = Script(dict(outcome="label_lacks_value"))
    huge = (Reading("9A", "region-9", "obs-9a", "raw_reading", "x" * 200_000),)
    resolver = make_resolver(model_factory=script.model, meter=meter(), date_rules=PILOT_DATES)

    outcome = asyncio.run(resolver(task("habitat"), READINGS + huge, CONTEXT, tools=FakeTools()))

    assert (outcome.answer, outcome.failure) == (None, "input_too_large")
    assert script.seen == [] and outcome.model_calls == 0


class _Client:
    def __init__(self):
        self.closed = 0

    async def close(self):
        self.closed += 1


def test_each_experts_inference_client_is_closed():
    clients = []

    def factory():
        model = Script(dict(outcome="label_lacks_value")).model()
        model.client = _Client()  # As model_gateway.model_for's AsyncInferenceClient.
        clients.append(model.client)
        return model

    resolver = make_resolver(model_factory=factory, meter=meter())

    async def two():
        await resolver(task("habitat"), READINGS, CONTEXT, tools=FakeTools())
        await resolver(task("collectors"), READINGS, CONTEXT, tools=FakeTools())

    asyncio.run(two())

    assert [client.closed for client in clients] == [1, 1]


def test_the_field_deadline_is_a_timeout():
    cost = meter()

    async def slow(messages, info):
        await asyncio.sleep(5)

    resolver = make_resolver(model_factory=lambda: FunctionModel(slow), meter=cost,
                             field_timeout_seconds=0.05)
    outcome = asyncio.run(resolver(task("habitat"), READINGS, CONTEXT, tools=FakeTools()))

    assert outcome.failure == "timeout" and outcome.answer is None
    # The cancelled request keeps its worst case: it may have been billed.
    assert cost.outstanding_micros == 0 and cost.spent_micros == outcome.cost_micros > 0


# An expert's budget: the real run of 2026-10-09 (twelve fields on seven
# specimens ran out of tool calls or requests, and the resolver's fallback
# replaced the expert's own answer).

# 105526321's labels as its readers wrote them in that run (sex sign left out).
MCKINLEY = (
    Reading("1A", "region-1", "obs-1a", "decided_transcript", "FMNHINS\n4486784"),
    Reading("1B", "region-1", "obs-1b", "raw_reading", "FMNHINS\n4486784"),
    Reading("2A", "region-2", "obs-2a", "decided_transcript",
            "10-6-78-la\nE. slope Mt. McKinley\nDavao Prov.\nMindanao, P.I.\nF.G. Werner\n"
            "3 sept. '46\nMossy forest 6400'\nsp. 30"),
    Reading("2B", "region-2", "obs-2b", "raw_reading",
            "10-6-78-1a\nE.slope Mt. McKinley\nDavao Prov.\nMindanao, P.I.\nF.G. Wermer\n"
            "3 Sept. '46\nMossy forest 6400'\nSp.30"),
)
# The organiser's city for 105526321: the mountain.
MCKINLEY_CITY = FieldTask(
    key="city", mandatory=True, current=FieldValue(state=ValueState.SUPPORTED, literal="Mt. McKinley"),
    candidates=tuple(offered(("2A", "Mt. McKinley"), ("2B", "Mt. McKinley"))), tools=FIELD_TOOLS["city"])
# Its city expert's lookups in that run, turn by turn: twelve, then a thirteenth
# that the tool-call limit stopped.
MCKINLEY_TURNS = (
    (("tgn", "Mount McKinley, Davao, Philippines"), ("wikidata", "Mount McKinley, Davao, Philippines"),
     ("geolocate", "Mt. McKinley, Davao, Philippines"), ("nga", "Mount McKinley, Davao, Philippines")),
    (("geolocate", "McKinley, Davao, Philippines"), ("tgn", "McKinley, Davao, Philippines"),
     ("wikidata", "McKinley, Davao, Philippines"), ("nga", "McKinley, Davao, Philippines")),
    (("geolocate", "Mount McKinley, Davao, Philippines"), ("nga", "Mount McKinley, Mindanao, Philippines"),
     ("wikidata", "Mount McKinley, Mindanao, Philippines"), ("tgn", "Mount McKinley, Mindanao, Philippines")),
    (("geolocate", "McKinley, Mindanao, Philippines"),),
)


def no_place(source: str, query: str) -> SourceAnswer:
    return SourceAnswer(source, query, LookupStatus.NO_MATCH, (),
                        Evidence(id=f"ev-{source}-{query}", kind="lookup", source=source, locator=None,
                                 excerpt="no place"), "no place")


def lookups(*pairs) -> Step:
    """One turn that asks each (source, query) at once."""
    return lambda messages, info: ModelResponse(parts=[
        ToolCallPart("lookup", {"source": source, "query": query}) for source, query in pairs])


def resolve_on(readings, script: Script, field: FieldTask, tools=None, *, cost=None, **kw):
    resolver = make_resolver(model_factory=script.model, meter=cost or meter(), date_rules=PILOT_DATES, **kw)
    return asyncio.run(resolver(field, readings, CONTEXT, tools=tools or FakeTools()))


def mckinley(*after: Step | dict):
    """105526321's city expert: its four turns of lookups, then `after`."""
    tools = FakeTools({pair: no_place(*pair) for turn in MCKINLEY_TURNS for pair in turn})
    return tools, Script(*(lookups(*turn) for turn in MCKINLEY_TURNS), *after)


def test_an_expert_out_of_tool_calls_answers_from_what_it_has():
    """The thirteenth lookup is over the limit: the expert is asked once more,
    its tools withheld, and its own answer stands (no fallback), so the
    not-on-the-label rule can read it."""
    tools, script = mckinley(dict(outcome="label_lacks_value",
                                  explanation="Mt. McKinley is a mountain; no reading names a town."))
    cost = meter()

    outcome = resolve_on(MCKINLEY, script, MCKINLEY_CITY, tools, cost=cost)

    assert (outcome.failure, outcome.fallback, outcome.answer.outcome) == (None, False, "label_lacks_value")
    assert len(tools.calls) == 12  # the thirteenth never ran
    assert outcome.model_calls == 5 and outcome.cost_micros == cost.spent_micros
    messages, info = script.seen[-1]
    assert info.function_tools == []  # its tools are withheld
    last = messages[-1]
    assert [p.content for p in last.parts if isinstance(p, ToolReturnPart)] == [experts.NOT_RUN]
    assert isinstance(last.parts[-1], UserPromptPart) and last.parts[-1].content == experts.ANSWER_NOW_PROMPT


def test_an_expert_out_of_requests_answers_from_what_it_has():
    tools = FakeTools({("gbif", q): SourceAnswer("gbif", q, LookupStatus.NO_MATCH, (), None)
                       for q in ("Epipsocus", "Epipsocvs")})
    script = Script(call("lookup", source="gbif", query="Epipsocus"),
                    call("lookup", source="gbif", query="Epipsocvs"),
                    dict(outcome="sources_cannot_resolve", literal="Epipsocus sp. 1", reading_names=["1A"],
                         explanation="GBIF has no match for either spelling."))
    cost = meter()

    outcome = resolve(script, task("taxon"), tools, cost=cost, request_limit=2)

    assert (outcome.failure, outcome.fallback) == (None, False)
    assert (outcome.answer.outcome, outcome.answer.literal) == ("sources_cannot_resolve", "Epipsocus sp. 1")
    assert outcome.model_calls == 3 and outcome.cost_micros == cost.spent_micros
    messages, info = script.seen[2]
    assert info.function_tools == []
    # The last lookup's result, which the request limit kept from being sent, is in it.
    assert [r["query"] for r in tool_returns(messages)] == ["Epipsocus", "Epipsocvs"]
    assert messages[-1].parts[-1].content == experts.ANSWER_NOW_PROMPT


def test_an_answer_now_that_breaks_its_checks_leaves_the_fallback():
    tools = FakeTools({("gbif", "Epipsocus"): SourceAnswer("gbif", "Epipsocus", LookupStatus.NO_MATCH, (), None)})
    # A taxon resolved with no GBIF success is sent back, and no request is left.
    script = Script(call("lookup", source="gbif", query="Epipsocus"),
                    dict(outcome="resolved", literal="Epipsocus sp. 1", reading_names=["1A"]))

    outcome = resolve(script, task("taxon"), tools, request_limit=1)

    assert outcome.answer == FieldAnswer(outcome="sources_cannot_resolve", explanation=EXHAUSTED)
    assert outcome.fallback and outcome.failure is None and outcome.model_calls == 2


class Refusing(CostMeter):
    """A run ceiling that pays for `allowed` requests and refuses the next."""

    def __init__(self, allowed: int):
        super().__init__(1_000_000, input_micros_per_million=200_000, output_micros_per_million=600_000)
        self.allowed = allowed

    async def reserve(self, input_tokens, output_tokens):
        if self.allowed == 0:
            raise experts.BudgetExhausted("run_cost_ceiling")
        self.allowed -= 1
        return await super().reserve(input_tokens, output_tokens)


def test_an_answer_now_the_run_ceiling_cannot_pay_for_is_never_sent():
    tools = FakeTools({("gbif", "Epipsocus"): SourceAnswer("gbif", "Epipsocus", LookupStatus.NO_MATCH, (), None)})
    script = Script(call("lookup", source="gbif", query="Epipsocus"),
                    dict(outcome="sources_cannot_resolve", explanation="Never sent."))
    cost = Refusing(allowed=1)

    outcome = resolve(script, task("taxon"), tools, cost=cost, request_limit=1)

    assert outcome.answer == FieldAnswer(outcome="sources_cannot_resolve", explanation=EXHAUSTED)
    assert outcome.fallback and len(script.seen) == 1 and outcome.model_calls == 1
    assert cost.outstanding_micros == 0 and cost.spent_micros == outcome.cost_micros


def test_tool_results_tell_an_expert_near_its_limits_to_answer_now():
    tools, script = mckinley(dict(outcome="label_lacks_value", explanation="No town."))

    resolve_on(MCKINLEY, script, MCKINLEY_CITY, tools)

    first, second = (tool_returns(script.seen[turn][0])[-4:] for turn in (1, 2))
    assert not any("budget" in result for result in first)  # eight of twelve left
    assert all(result["budget"].startswith("Answer now") for result in second)  # four left
    assert "(tool calls left: 4 of 12; turns left: 4 of 6)" in second[0]["budget"]
    # The last turn: one lookup a turn, five turns made, one left.
    tools = FakeTools({("gbif", q): SourceAnswer("gbif", q, LookupStatus.NO_MATCH, (), None)
                       for q in ("A", "B", "C", "D", "E")})
    script = Script(*(call("lookup", source="gbif", query=q) for q in "ABCDE"),
                    dict(outcome="sources_cannot_resolve", explanation="No match."))
    resolve(script, task("taxon"), tools)
    budgets = [result.get("budget") for result in tool_returns(script.seen[-1][0])]
    assert budgets[:4] == [None] * 4 and "turns left: 1 of 6" in budgets[4]


# 105526330's label 2 (decided reading) as its reader wrote it in that run.
LABEL_330 = (Reading("2A", "region-2", "obs-2a", "decided_transcript",
                     "IV-29-68-2\nYepocapa,4800 ft.\nChimaltenago\nGuatemala,IV-25\n1948, R.D. Mitchell"),)


def test_a_repeated_check_is_answered_from_its_first_call(monkeypatch):
    """105526330's date expert asked parse_date the same thing three times."""
    from specimen_digitization.field_research import checks

    runs = []
    parse = checks.parse_date
    monkeypatch.setattr(checks, "parse_date", lambda *args, **kw: runs.append(args) or parse(*args, **kw))
    same = {"literal": "IV-25\n1948", "year_literal": "1948"}
    script = Script(
        lambda messages, info: ModelResponse(parts=[
            ToolCallPart("parse_date", same), ToolCallPart("parse_date", {**same, "literal": "IV-25 1948"})]),
        call("parse_date", **same),
        dict(outcome="sources_cannot_resolve", explanation="parse_date reads no date there."),
    )
    field = FieldTask(key="date_visited_from", mandatory=True,
                      current=FieldValue(state=ValueState.SUPPORTED, literal="IV-25\n1948"),
                      candidates=tuple(offered(("2A", "IV-25\n1948"))), tools=FIELD_TOOLS["date_visited_from"])

    resolve_on(LABEL_330, script, field)

    assert runs == [("IV-25\n1948",), ("IV-25 1948",)]  # the repeat ran nothing
    first, _, again = tool_returns(script.seen[2][0])
    assert again["repeat"] == experts.REPEAT_NOTE
    assert {key: value for key, value in again.items() if key != "repeat"} == first


def test_a_repeated_lookup_is_sent_once():
    found = no_place("tgn", "Mount McKinley, Davao, Philippines")
    tools = FakeTools({("tgn", found.query): found})
    script = Script(lookups(("tgn", found.query), ("tgn", found.query)), lookups(("tgn", found.query)),
                    dict(outcome="label_lacks_value", explanation="No town."))

    outcome = resolve_on(MCKINLEY, script, MCKINLEY_CITY, tools)

    assert tools.calls == [("tgn", found.query, "city")]
    assert outcome.evidence == [found.evidence]
    shown = tool_returns(script.seen[2][0])
    assert ["repeat" in result for result in shown] == [False, True, True]


@pytest.mark.parametrize("key", ["country", "county"])
def test_the_country_and_county_experts_have_no_geolocate(key):
    """In the real runs of 2026-10-09 every county GEOLocate lookup was refused
    before it was sent (105526329's "Yepocapa, Chimaltenango, Guatemala"
    among them), and GEOLocate settles no country: their experts ask the
    gazetteers only."""
    from specimen_digitization.field_research.prompts import FIELD_LABELS, instructions

    assert FIELD_TOOLS[key] == ("tgn", "wikidata", "nga")
    brief = instructions(key).split(f"Field: {FIELD_LABELS[key]} ({key})", 1)[1]
    assert "geolocate" not in brief.lower()
    query = "Yepocapa, Chimaltenango, Guatemala"
    tools = FakeTools()
    script = Script(call("lookup", source="geolocate", query=query),
                    dict(outcome="sources_cannot_resolve", explanation="No source settled it."))

    outcome = resolve(script, task(key), tools)

    lookup = script.seen[0][1].function_tools[0]
    assert lookup.parameters_json_schema["properties"]["source"]["enum"] == ["tgn", "wikidata", "nga"]
    assert "geolocate" not in lookup.description
    assert tools.calls == [] and outcome.failure is None


def test_the_briefs_answer_label_lacks_value_for_a_value_the_label_does_not_write():
    """In the real run of 2026-10-09, 105526326's city expert (labels naming
    only "Davao, Prov.") and 105526329's date-identified expert (only a
    collecting date, "IV-23-48" with "R.D.mitchell") answered
    sources_cannot_resolve, so the not-on-the-label rule could not read them."""
    from specimen_digitization.field_research.prompts import instructions

    common = instructions("habitat")
    [lacks] = [line for line in common.splitlines() if line.startswith("- label_lacks_value:")]
    assert "A value you could only infer or look up is not on the label" in lacks
    [cannot] = [line for line in common.splitlines() if line.startswith("- sources_cannot_resolve:")]
    assert cannot.endswith("A value the labels do not write is label_lacks_value, never sources_cannot_resolve.")
    assert '"Davao Prov." names the province, never Davao City' in instructions("city")
    date = instructions("date_identified")
    assert 'with no "det." are the collector and the collecting date' in date
    assert "answer label_lacks_value, even when the labels write a collecting date" in date


def test_the_shared_brief_has_the_expert_stop_when_the_sources_have_answered():
    from specimen_digitization.field_research.prompts import instructions

    text = instructions("city")
    assert "Keep going until" not in text
    assert "Then stop and answer: when the sources have answered what they can" in text
    assert "the same name with other larger units after it is the same lookup" in text
    assert "when a tool result says to answer now, answer" in text


def test_an_experts_own_sources_cannot_resolve_is_no_fallback():
    script = Script(dict(outcome="sources_cannot_resolve", literal="Epipsocus sp. 1", reading_names=["1A"],
                         explanation="GBIF cannot settle the genus."))

    outcome = resolve(script, task("taxon"))

    assert outcome.answer.outcome == "sources_cannot_resolve" and outcome.answer.literal == "Epipsocus sp. 1"
    assert not outcome.fallback


def test_a_provider_error_is_a_model_error_logged_by_class_only(caplog):
    def broken(messages, info):
        raise ModelHTTPError(503, "deepseek", body="label text Epipsocus sp. 1")

    script = Script(broken)
    with caplog.at_level(logging.WARNING, logger="specimen_digitization.field_research.experts"):
        outcome = resolve(script, task("taxon"))

    assert outcome.failure == "model_error" and outcome.answer is None
    assert "ModelHTTPError" in caplog.text and "Epipsocus" not in caplog.text


def test_logfire_shows_each_expert_as_its_own_agent(monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(experts, "agent_instrumentation", lambda: InstrumentationSettings(
        tracer_provider=provider, include_content=False, version=5))
    script = Script(dict(outcome="label_lacks_value"), dict(outcome="label_lacks_value"))
    resolver = make_resolver(model_factory=script.model, meter=meter())

    async def both():
        await resolver(task("taxon"), READINGS, CONTEXT, tools=FakeTools())
        await resolver(task("precise_location"), READINGS, CONTEXT, tools=FakeTools())

    asyncio.run(both())

    agents = {span.attributes["gen_ai.agent.name"]: span for span in exporter.get_finished_spans()
              if span.attributes and "gen_ai.agent.name" in span.attributes}
    assert {"field_taxon", "field_precise_location"} <= set(agents)
    assert agents["field_taxon"].attributes["gen_ai.agent.description"] == (
        "Expert for Taxon. Settles it from the label readings and its approved sources.")


def test_the_briefs_place_notations_are_the_tables():
    """The shared brief's notation line is rendered from the table the place
    rule reads (notations.NOTATIONS): every entry, and no other."""
    import re

    from specimen_digitization.field_research import notations
    from specimen_digitization.field_research.prompts import _ROOT, instructions

    assert (_ROOT / "common.txt").read_text(encoding="utf-8").count(notations.MARKER) == 1
    for key in FIELD_TOOLS:
        text = instructions(key)
        [line] = [line for line in text.splitlines() if line.startswith('- "') and "look it up as" in line]
        assert line == notations.brief_line() and notations.MARKER not in text
        listed = re.findall(r'"([^"]+)": [^(]+\((\w+); look it up as "([^"]+)"\)', line)
        assert listed == [(entry.notation, entry.field, entry.expansion) for entry in notations.NOTATIONS]
    # A notation is matched by the place comparison key, for its own field only.
    assert notations.expansion("P. I.", "country").expansion == "Philippine Islands"
    assert notations.expansion("P.I.", "province_state") is None and notations.expansion("Phil.", "country") is None


UNREACHABLE_LINE = (
    "- If a source cannot be reached (an error status and no evidence_id), decide with the sources that "
    "answered when they settle the field under these rules, and say in the explanation which source did "
    "not answer.")


def test_every_place_brief_has_its_expert_decide_with_the_sources_that_answered():
    """One unreachable source does not void a field (experts.make_resolver):
    every brief whose expert may ask Getty TGN says so, once."""
    from specimen_digitization.field_research.prompts import instructions

    places = [key for key, tools in FIELD_TOOLS.items() if "tgn" in tools]
    assert places == ["country", "province_state", "county", "city", "precise_location"]
    for key in FIELD_TOOLS:
        lines = instructions(key).splitlines()
        assert lines.count(UNREACHABLE_LINE) == (1 if key in places else 0), key


def test_the_taxon_brief_has_a_doubtful_or_distant_genus_looked_up_alone():
    """B4 of #289's fifth review: the brief no longer withholds the lookup
    for a genus in doubt, whatever its qualifier's spelling, and has every
    genus a label writes looked up before a morphocode stands alone, so that
    the GBIF guard (step._gbif_asked_another_name) sees it."""
    from specimen_digitization.field_research.prompts import instructions

    lines = instructions("taxon").splitlines()
    assert not [line for line in lines if "make no lookup" in line]
    [doubt] = [line for line in lines if "is in doubt" in line]
    assert "any spelling" in doubt and '"?"' in doubt
    assert all(f'"{qualifier}"' in doubt for qualifier in ("cf.", "cfr.", "c.f.", "aff.", "nr.", "conf.", "poss."))
    [alone] = [line for line in lines if line.startswith("- Still look up a doubtful genus alone")]
    assert "no qualifier and no epithet" in alone and "sources_cannot_resolve, whatever GBIF says" in alone
    [morphocode] = [line for line in lines if line.startswith("- Before you answer for a morphocode")]
    assert "look up alone any genus that any label writes anywhere" in morphocode
    assert "another label, with a qualifier or without" in morphocode
    assert "Only when no label writes a genus does the morphocode stand alone" in morphocode


def test_every_field_has_a_brief():
    from specimen_digitization.field_research.prompts import FIELD_LABELS, instructions

    assert set(FIELD_LABELS) == set(FIELD_TOOLS)
    for key, label in FIELD_LABELS.items():
        text = instructions(key)
        assert f"Field: {label} ({key})" in text
        assert text.isascii()
        brief = text.split(f"Field: {label} ({key})", 1)[1]
        assert len(brief.splitlines()) <= 25


# The checks on an answer, one rule at a time.

def expert(key: str, answers=()) -> experts._Expert:
    tools = FakeTools()
    made = experts._Expert(task(key), READINGS, tools, PILOT_DATES)
    for answer in answers:
        made.calls.append(experts._Call(answer.source_id, answer.query, answer.status, answer))
    return made


def answer(**fields) -> FieldAnswer:
    fields.setdefault("explanation", "Because.")
    return FieldAnswer(**fields)


@pytest.mark.parametrize(("key", "given", "says"), [
    ("identified_by_irn", dict(outcome="resolved"), "can never be resolved"),
    ("identified_by_irn", dict(outcome="sources_cannot_resolve", literal="F. G. Werner"),
     "Leave literal, value and authority_id empty"),
    ("precise_location", dict(outcome="resolved", literal="Mindanao, Davao", reading_names=["1A"],
                              authority_id="gbif:1234", source_evidence_ids=["ev-gbif-1"]),
     "verbatim locality text"),
    ("precise_location", dict(outcome="resolved", literal="Mindanao, Davao", reading_names=["1A"],
                              value="Davao City"), "verbatim locality text"),
    ("taxon", dict(outcome="resolved", literal="Epipsocus sp. 1", reading_names=["1A"]),
     "GBIF answer with status success"),
    ("elevation_from_m", dict(outcome="resolved", literal="1500", reading_names=["2A"]),
     "elevation_unit_conflict"),
    ("collectors", dict(outcome="resolved", literal="F. G. Werner", reading_names=["3A"]),
     "no reading named '3A'"),
    ("collectors", dict(outcome="resolved", literal="F. G. Werner", reading_names=[]),
     "reading_names"),
    ("collectors", dict(outcome="sources_cannot_resolve", source_evidence_ids=["ev-made-up"]),
     "'ev-made-up' is not the evidence_id"),
    ("collectors", dict(outcome="sources_cannot_resolve", explanation="x" * 601), "600"),
    ("collectors", dict(outcome="sources_cannot_resolve", explanation="  "), "explanation"),
    ("collectors", dict(outcome="several_possibilities", options=["F. G. Werner"]), "two"),
    ("taxon", dict(outcome="resolved", literal="Epipsocus sp. 1", reading_names=["1A"],
                   authority_id="gbif:9999", source_evidence_ids=["ev-gbif-1"]), "authority_id"),
])
def test_answers_that_break_a_rule_are_sent_back(key, given, says):
    made = expert(key, [GBIF_SUCCESS])

    with pytest.raises(ModelRetry, match=says.replace("(", r"\(")):
        made.validate(answer(**given))


# Readers that disagree (G19, G20, G27; the review's B1).

DISAGREEING = (
    Reading("1A", "region-1", "obs-1a", "raw_reading", "Chimaltenago, Guat.\nleg. J. Smith"),
    Reading("1B", "region-1", "obs-1b", "raw_reading", "Chimaltenango, Guat.\nleg. J. Smyth"),
)


def disagreeing(key: str, literals, answers=()) -> experts._Expert:
    """An expert whose organiser left the field ambiguous between two raw readers."""
    field = FieldTask(key=key, mandatory=True, current=FieldValue(state=ValueState.AMBIGUOUS),
                      candidates=tuple(Candidate(name, literal, literal, f"ev-{name}")
                                       for name, literal in literals), tools=FIELD_TOOLS[key])
    made = experts._Expert(field, DISAGREEING, FakeTools(), PILOT_DATES)
    for found in answers:
        made.calls.append(experts._Call(found.source_id, found.query, found.status, found))
    return made


def place(name: str, evidence_id: str) -> SourceAnswer:
    """Getty TGN's answer for `name`: one department of Guatemala of that name."""
    department = "departments (political divisions), first level subdivisions (political entities)"
    return SourceAnswer("tgn", name, LookupStatus.SUCCESS,
                        (SourceCandidate(name, f"tgn:{name}", department, "in Guatemala",
                                         (PlaceRef("Guatemala", "tgn:7005493"),)),),
                        Evidence(id=evidence_id, kind="authority", source="tgn",
                                 locator=f"tgn:{name}", excerpt=name), note="match")


def town(name: str, evidence_id: str) -> SourceAnswer:
    """GEOLocate's answer for a city `name` in Guatemala."""
    return SourceAnswer("geolocate", f"{name}, Guatemala", LookupStatus.SUCCESS,
                        (SourceCandidate(name, f"geolocate:{name}", None, "GEOLocate matched in Guatemala",
                                         (PlaceRef("Guatemala"),)),),
                        Evidence(id=evidence_id, kind="authority", source="geolocate",
                                 locator=f"geolocate:{name}", excerpt=name), note="match")


def test_a_pick_between_readers_with_no_source_is_sent_back():
    made = disagreeing("collectors", [("1A", "J. Smith"), ("1B", "J. Smyth")])

    with pytest.raises(ModelRetry, match="readers disagree on this field"):
        made.validate(answer(outcome="resolved", literal="J. Smith", reading_names=["1A"]))


def nothing(name: str, evidence_id: str, status=LookupStatus.NO_MATCH) -> SourceAnswer:
    """Getty TGN asked about `name`: no match, captured (or, with another
    status and no evidence, not captured)."""
    stored = None if status != LookupStatus.NO_MATCH else Evidence(
        id=evidence_id, kind="lookup", source="tgn", locator=None, excerpt="Getty TGN: no match")
    return SourceAnswer("tgn", name, status, (), stored, note=str(status))


@pytest.mark.parametrize(("answers", "cited", "says"), [
    # G27's example with no lookup at all.
    ((), [], "readers disagree on this field"),
    # Getty TGN confirms 1B's text, and finds nothing for 1A's (G20).
    ((place("Chimaltenango", "ev-b"), nothing("Chimaltenago", "ev-a")), ["ev-b"], None),
    # 1A's text was never asked about: a missing lookup is not a no-match (the second review's B1).
    ((place("Chimaltenango", "ev-b"),), ["ev-b"], "readers disagree on this field"),
    # A timeout is not a no-match either.
    ((place("Chimaltenango", "ev-b"), nothing("Chimaltenago", "ev-a", LookupStatus.TIMEOUT)), ["ev-b"],
     "readers disagree on this field"),
    # A success answer about 1A's text, whatever it names, is not "found nothing".
    ((place("Chimaltenango", "ev-b"), nothing("Chimaltenago", "ev-a"),
      SourceAnswer("geolocate", "Chimaltenago, Guatemala", LookupStatus.SUCCESS,
                   (SourceCandidate("Chimaltenango", "geolocate:Chimaltenango"),),
                   Evidence(id="ev-c", kind="authority", source="geolocate", locator="geolocate:Chimaltenango",
                            excerpt="Chimaltenango"))), ["ev-b"], "readers disagree on this field"),
    # A source confirms each reader's text: nothing decides between them.
    ((place("Chimaltenango", "ev-b"), place("Chimaltenago", "ev-a")), ["ev-b"],
     "readers disagree on this field"),
    # The confirming answer must be cited.
    ((place("Chimaltenango", "ev-b"), nothing("Chimaltenago", "ev-a")), [], "Cite the evidence_id"),
])
def test_a_place_the_readers_disagree_on_settles_only_on_a_source_confirming_one_reader(answers, cited, says):
    made = disagreeing("province_state", [("1A", "Chimaltenago"), ("1B", "Chimaltenango")], answers)
    given = answer(outcome="resolved", literal="Chimaltenango", reading_names=["1B"],
                   source_evidence_ids=cited, authority_id="tgn:Chimaltenango" if cited else None)

    if says is None:
        assert made.validate(given).literal == "Chimaltenango"
        return
    with pytest.raises(ModelRetry, match=says):
        made.validate(given)


def test_readers_that_differ_disagree_whatever_state_the_organiser_gave_the_field():
    """The organiser left the city supported on 1A's text, yet 1B writes
    another: only GEOLocate's answer for 1A's text is not enough (B1)."""
    readings = (Reading("1A", "region-1", "obs-1a", "raw_reading", "San Pedro, Guat."),
                Reading("1B", "region-1", "obs-1b", "raw_reading", "San Pablo, Guat."))
    field = task("city", current=FieldValue(state=ValueState.SUPPORTED, literal="San Pedro"),
                 candidates=offered(("1A", "San Pedro"), ("1B", "San Pablo")))
    made = experts._Expert(field, readings, FakeTools(), PILOT_DATES)
    made.calls.append(experts._Call("geolocate", SAN_PEDRO.query, SAN_PEDRO.status, SAN_PEDRO))
    given = answer(outcome="resolved", literal="San Pedro", reading_names=["1A"], authority_id="geolocate:1",
                   source_evidence_ids=["ev-town"])

    with pytest.raises(ModelRetry, match="readers disagree on this field"):
        made.validate(given)
    # Once TGN finds nothing for 1B's text, GEOLocate's answer settles it (G20).
    missing = nothing("San Pablo", "ev-none")
    made.calls.append(experts._Call("tgn", missing.query, missing.status, missing))
    assert made.validate(given).literal == "San Pedro"


YEPOCAPA = SourceAnswer("geolocate", "Yepocapa, Chimaltenango, Guatemala", LookupStatus.SUCCESS,
                        (SourceCandidate("Yepocapa", "geolocate:76853dedbc6ff5ce"),),
                        Evidence(id="ev-yepocapa", kind="authority", source="geolocate",
                                 locator="geolocate:76853dedbc6ff5ce", excerpt="Yepocapa"), note="match")


def test_a_place_text_was_looked_up_whatever_punctuation_the_label_writes_after_it():
    """The literal stays "Yepocapa," as written; the lookup of "Yepocapa" is
    about it. A near spelling is not."""
    literal = collapse("Yepocapa,")
    assert agreement.about(YEPOCAPA, literal) and agreement.about(nothing("Yepocapa", "ev-n"), literal)
    assert agreement.about(nothing("Yepocapa;", "ev-n"), collapse("Yepocapa"))
    assert not agreement.about(nothing("Yepocapo", "ev-n"), literal)
    assert not agreement.about(nothing("Yepocapa", "ev-n"), collapse("Yepocapa, Guat."))
    # Only the name before the first comma is searched (the third review's N2).
    assert agreement.about(nothing("San Pedro, Sacatepequez", "ev-n"), "San Pedro")
    assert not agreement.about(nothing("San Pedro, Sacatepequez", "ev-n"), "San Pedro Sacatepequez")


def test_readers_that_differ_on_a_town_written_with_a_comma_settle_on_its_lookup():
    """1A writes "Yepocapa," and 1B "Yepocapo,": GEOLocate confirms Yepocapa
    and Getty TGN finds nothing for Yepocapo (G20), so 1A's text settles,
    with GEOLocate's name as the value."""
    readings = (Reading("1A", "region-1", "obs-1a", "raw_reading", "Mun. Yepocapa, Chimaltenango"),
                Reading("1B", "region-1", "obs-1b", "raw_reading", "Mun. Yepocapo, Chimaltenango"))
    field = task("city", current=FieldValue(state=ValueState.AMBIGUOUS),
                 candidates=offered(("1A", "Yepocapa,"), ("1B", "Yepocapo,")))
    made = experts._Expert(field, readings, FakeTools(), PILOT_DATES)
    for found in (YEPOCAPA, nothing("Yepocapo", "ev-none")):
        made.calls.append(experts._Call(found.source_id, found.query, found.status, found))
    given = answer(outcome="resolved", literal="Yepocapa,", reading_names=["1A"], value="Yepocapa",
                   authority_id="geolocate:76853dedbc6ff5ce", source_evidence_ids=["ev-yepocapa"])

    accepted = made.validate(given)

    assert (accepted.literal, accepted.value) == ("Yepocapa,", "Yepocapa")


@pytest.mark.parametrize(("key", "authority", "says"), [
    # The third review's N4: one GEOLocate answer confirms both readers' texts as one town.
    ("city", "geolocate:76853dedbc6ff5ce", None),
    # Another candidate than the town both texts are confirmed as: a municipality TGN gives.
    ("city", "tgn:yepocapa-municipality", "which a source confirms as the same place"),
    # Only a place: the same lookup settles no collectors between readers that differ.
    ("collectors", None, "readers disagree on this field"),
])
def test_readers_whose_texts_match_the_place_confirming_both_by_its_comparison_key_settle_on_it(key, authority, says):
    readings = (Reading("1A", "region-1", "obs-1a", "raw_reading", "Mun. Yepocapa, Chimaltenango"),
                Reading("1B", "region-1", "obs-1b", "raw_reading", "Mun. Yepocapa Chimaltenango"))
    field = task(key, current=FieldValue(state=ValueState.AMBIGUOUS),
                 candidates=offered(("1A", "Yepocapa,"), ("1B", "Yepocapa")))
    made = experts._Expert(field, readings, FakeTools(), PILOT_DATES)
    municipality = tgn("Yepocapa", "ev-municipality", ("Yepocapa", "tgn:yepocapa-municipality",
                                                       "second level subdivisions (political entities)"))
    if key == "city":
        for found in (YEPOCAPA, municipality):
            made.calls.append(experts._Call(found.source_id, found.query, found.status, found))
    cited = {"geolocate:76853dedbc6ff5ce": ["ev-yepocapa"], "tgn:yepocapa-municipality": ["ev-municipality"]}
    given = answer(outcome="resolved", literal="Yepocapa", reading_names=["1B"], authority_id=authority,
                   source_evidence_ids=cited.get(authority, []))

    if says is None:
        assert made.validate(given).literal == "Yepocapa"
        found = agreement.labels(field, readings, [YEPOCAPA])
        assert [label.settled for label in found.values()] == [frozenset({"Yepocapa,", "Yepocapa"})]
        return
    with pytest.raises(ModelRetry, match=says):
        made.validate(given)


def test_a_taxons_readers_that_differ_settle_on_one_confirmed_reader_only():
    """Only a place's readers settle on one source confirming each: two
    readers of a taxon that GBIF both settle as one usage still disagree."""
    readings = (Reading("1A", "region-1", "obs-1a", "raw_reading", "Danaus plexippus"),
                Reading("1B", "region-1", "obs-1b", "raw_reading", "Danaus plexippus (Linnaeus, 1758)"))
    field = task("taxon", current=FieldValue(state=ValueState.AMBIGUOUS), candidates=offered(
        ("1A", "Danaus plexippus"), ("1B", "Danaus plexippus (Linnaeus, 1758)")))
    with_author = SourceAnswer("gbif", "Danaus plexippus (Linnaeus, 1758)", LookupStatus.SUCCESS,
                               DANAUS.candidates, DANAUS.evidence.model_copy(update={"id": "ev-author"}))
    refused = agreement.refusal(field, readings, literal="Danaus plexippus", named=readings[:1],
                                value="Danaus plexippus (Linnaeus, 1758)", authority_id="5133088",
                                cited=[DANAUS], received=[DANAUS, with_author])
    assert refused is not None and refused.reason == agreement.DIFFER


SACATEPEQUEZ = "Sacatep" + chr(0xE9) + "quez"  # As GEOLocate writes it.
TWO_LABELS = (
    Reading("1A", "region-1", "obs-1a", "raw_reading", "Chimaltenango, Guat."),
    Reading("1B", "region-1", "obs-1b", "raw_reading", "Chimaltenango, Guat."),
    Reading("2A", "region-2", "obs-2a", "raw_reading", "Sacatepequez"),
    Reading("2B", "region-2", "obs-2b", "raw_reading", "Sacatepequez"),
)


@pytest.mark.parametrize("second", [
    # Label 2 was never asked about.
    None,
    # Label 2 was asked about, and GEOLocate found only another spelling.
    SourceAnswer("geolocate", "Sacatepequez, Guatemala", LookupStatus.SUCCESS,
                 (SourceCandidate(SACATEPEQUEZ, "geolocate:" + SACATEPEQUEZ),),
                 Evidence(id="ev-2", kind="authority", source="geolocate", locator="geolocate:" + SACATEPEQUEZ,
                          excerpt=SACATEPEQUEZ), note="match"),
    # Label 2's own text confirmed, as another place.
    place("Sacatepequez", "ev-2"),
])
def test_a_field_on_two_labels_settles_only_when_both_settle_to_one_value(second):
    """G32 with the second review's B1: label 1 writes Chimaltenango, label 2
    Sacatepequez, each in both its readings."""
    field = task("province_state", current=FieldValue(state=ValueState.AMBIGUOUS),
                 candidates=offered(("1A", "Chimaltenango"), ("1B", "Chimaltenango"),
                                    ("2A", "Sacatepequez"), ("2B", "Sacatepequez")))
    first = place("Chimaltenango", "ev-1")
    received = [first] if second is None else [first, second]
    made = experts._Expert(field, TWO_LABELS, FakeTools(), PILOT_DATES)
    for found in received:
        made.calls.append(experts._Call(found.source_id, found.query, found.status, found))
    given = answer(outcome="resolved", literal="Chimaltenango", reading_names=["1A", "1B"],
                   authority_id="tgn:Chimaltenango", source_evidence_ids=["ev-1"])

    with pytest.raises(ModelRetry, match="labels write different text"):
        made.validate(given)
    refused = agreement.refusal(field, TWO_LABELS, literal="Chimaltenango", named=TWO_LABELS[:2], value=None,
                                authority_id="tgn:Chimaltenango", cited=[first], received=received)
    assert refused is not None and refused.differ and refused.reason == agreement.LABELS_DIFFER


def test_labels_that_write_one_name_differently_settle_on_one_gbif_usage():
    """G32's "same GBIF usage": label 1 writes the name, label 2 the name with
    its author; GBIF's decision for the name is the same usage for both."""
    readings = (Reading("1A", "region-1", "obs-1a", "raw_reading", "Danaus plexippus"),
                Reading("1B", "region-1", "obs-1b", "raw_reading", "Danaus plexippus"),
                Reading("2A", "region-2", "obs-2a", "raw_reading", "Danaus plexippus (Linnaeus, 1758)"),
                Reading("2B", "region-2", "obs-2b", "raw_reading", "Danaus plexippus (Linnaeus, 1758)"))
    field = task("taxon", current=FieldValue(state=ValueState.AMBIGUOUS), candidates=offered(
        ("1A", "Danaus plexippus"), ("1B", "Danaus plexippus"),
        ("2A", "Danaus plexippus (Linnaeus, 1758)"), ("2B", "Danaus plexippus (Linnaeus, 1758)")))
    settles = dict(literal="Danaus plexippus", named=readings[:2], value="Danaus plexippus (Linnaeus, 1758)",
                   cited=[DANAUS], received=[DANAUS])

    assert agreement.refusal(field, readings, authority_id="5133088", **settles) is None
    # Another usage than GBIF's decision for both labels does not settle them.
    assert agreement.refusal(field, readings, authority_id="5133099", **settles).differ


# A place value settles on the one candidate at its field's level (P1). The
# kinds are as the recorded pilot answers give them.

def tgn(query: str, evidence_id: str, *places: tuple) -> SourceAnswer:
    """Getty TGN's answer: success for one place, ambiguous for several. Each
    place is (name, authority_id, kind), and its parents as (name, authority_id)
    pairs when the recording gives them."""
    status = LookupStatus.SUCCESS if len(places) == 1 else LookupStatus.AMBIGUOUS
    return SourceAnswer("tgn", query, status,
                        tuple(SourceCandidate(name, authority, kind, None,
                                              tuple(PlaceRef(*parent) for parent in (rest[0] if rest else ())))
                              for name, authority, kind, *rest in places),
                        Evidence(id=evidence_id, kind="authority", source="tgn", locator=None, excerpt=query),
                        note=str(status))


NATION, FIRST, TOWN = ("nations, commonwealths, controlled regions",
                       "departments (political divisions), agricultural land, first level subdivisions "
                       "(political entities)", "inhabited places, cities, department capitals")
PHILIPPINES = tgn("P.I.", "ev-ph", ("Philippines", "tgn:1000135", NATION),
                  ("Philippine", "tgn:7268540", "inhabited places"), ("Philippine Sea", "tgn:7016773", "seas"))
IN_GUATEMALA = (("Guatemala", "tgn:7005493"),)
CHIMALTENANGO = tgn("Chimaltenango", "ev-chim",
                    ("Chimaltenango", "tgn:1016636", TOWN, (("Chimaltenango", "tgn:1000565"), *IN_GUATEMALA)),
                    ("Chimaltenango", "tgn:1000565", FIRST, IN_GUATEMALA))
DAVAO = tgn("Davao", "ev-davao-tgn",
            ("Davao del Norte", "tgn:1001216", "provinces, first level subdivisions (political entities)"),
            ("Davao", "tgn:7668798", "special cities, first level subdivisions (political entities)"),
            ("Davao", "tgn:1084177", "inhabited places, administrative centers, cities"))


@pytest.mark.parametrize(("key", "literal", "received", "value", "authority", "settles"), [
    # "P.I.": TGN's answer is ambiguous only because it also holds places that are no nation.
    ("country", "P.I.", PHILIPPINES, "Philippines", "tgn:1000135", True),
    # The department, not the town of the same name, is the province.
    ("province_state", "Chimaltenango", CHIMALTENANGO, "Chimaltenango", "tgn:1000565", True),
    ("province_state", "Chimaltenango", CHIMALTENANGO, "Chimaltenango", "tgn:1016636", False),
    # The town, never the department, is the city.
    ("city", "Chimaltenango", CHIMALTENANGO, "Chimaltenango", "tgn:1000565", False),
    ("city", "Chimaltenango", CHIMALTENANGO, "Chimaltenango", "tgn:1016636", True),
    # Two first level subdivisions: nothing tells them apart.
    ("province_state", "Davao", DAVAO, "Davao", "tgn:7668798", False),
    ("province_state", "Davao", DAVAO, "Davao del Norte", "tgn:1001216", False),
])
def test_a_place_settles_on_the_one_candidate_at_its_fields_level(key, literal, received, value, authority,
                                                                  settles):
    readings = (Reading("1A", "region-1", "obs-1a", "raw_reading", f"{literal}\nleg. J. Smith"),
                Reading("1B", "region-1", "obs-1b", "raw_reading", f"{literal}\nleg. J. Smith"))
    made = experts._Expert(task(key, candidates=offered(("1A", literal), ("1B", literal))), readings,
                           FakeTools(), PILOT_DATES)
    made.calls.append(experts._Call(received.source_id, received.query, received.status, received))
    given = answer(outcome="resolved", literal=literal, reading_names=["1A", "1B"],
                   value=None if value == literal else value, authority_id=authority,
                   source_evidence_ids=[received.evidence.id])

    if settles:
        assert made.validate(given).authority_id == authority
        return
    with pytest.raises(ModelRetry, match="exactly one candidate at this field's level"):
        made.validate(given)


@pytest.mark.parametrize(("source", "kind", "level"), [
    ("tgn", "nations, colonies, independent political entities", "country"),
    ("tgn", "provinces, first level subdivisions (political entities)", "province_state"),
    ("tgn", "inhabited places", "city"),
    ("tgn", "rivers", None),
    ("wikidata", "sovereign state, archipelagic state, country", "country"),
    ("wikidata", "former province of the Philippines, province of the Philippines", "province_state"),
    ("wikidata", "municipality of Guatemala", "city"),
    ("wikidata", "human settlement", "city"),
    ("wikidata", "government agency, historical society", None),
    ("nga", "A.PCLI", "country"),
    ("nga", "A.ADM1", "province_state"),
    ("nga", "A.ADM2", "county"),
    ("nga", "P.PPLA", "city"),
    ("nga", "H.STM", None),
])
def test_each_sources_kind_names_one_level(source, kind, level):
    found = SourceAnswer(source, "x", LookupStatus.SUCCESS, (SourceCandidate("X", f"{source}:1", kind),),
                         None)
    assert [key for key in sorted(agreement.PLACE_VALUE_FIELDS) if agreement.at_level(key, found)] == (
        [level] if level else [])


def test_readers_that_differ_settle_on_an_ambiguous_answer_with_one_candidate_at_the_level():
    """105526329's province: 2A writes Chimaltenango, 2B Chimaltenago. TGN's
    answer for Chimaltenango is ambiguous between the department and its
    town, and has nothing for Chimaltenago: the department settles it (G20)."""
    readings = (Reading("2A", "region-2", "obs-2a", "raw_reading", "Chimaltenango, Guatemala"),
                Reading("2B", "region-2", "obs-2b", "raw_reading", "Chimaltenago, Guatemala"))
    field = task("province_state", current=FieldValue(state=ValueState.AMBIGUOUS),
                 candidates=offered(("2A", "Chimaltenango"), ("2B", "Chimaltenago")))
    made = experts._Expert(field, readings, FakeTools(), PILOT_DATES)
    for found in (CHIMALTENANGO, nothing("Chimaltenago", "ev-none")):
        made.calls.append(experts._Call(found.source_id, found.query, found.status, found))
    given = answer(outcome="resolved", literal="Chimaltenango", reading_names=["2A"], authority_id="tgn:1000565",
                   source_evidence_ids=["ev-chim"])

    assert made.validate(given).authority_id == "tgn:1000565"
    # As a city, the same answer's one inhabited place is the town.
    assert agreement.identities([CHIMALTENANGO], "Chimaltenango", "city") == {"tgn:1016636"}


ESCUINTLA = tgn("Escuintla", "ev-esc", ("Escuintla", "tgn:1000566", FIRST, IN_GUATEMALA))
PHILIPPINES_BY_NAME = tgn("Philippines", "ev-ph-name", ("Philippines", "tgn:1000135", NATION),
                          ("Philippine", "tgn:7268540", "inhabited places"))
PHILIPPINE_ISLANDS = tgn("Philippine Islands", "ev-pi", ("Philippine Islands", "tgn:2578581", "ridges (landforms)"),
                         ("Philippines", "tgn:1000135", NATION), ("Philippine Sea", "tgn:7016773", "seas"))


@pytest.mark.parametrize(("key", "literal", "received", "value", "authority", "settles"), [
    # The lookup was asked the label's text, case and punctuation aside.
    ("province_state", "chimaltenango,", CHIMALTENANGO, "Chimaltenango", "tgn:1000565", True),
    ("country", "P.I.", PHILIPPINES, "Philippines", "tgn:1000135", True),
    # The candidate's own name, one letter from the label's text: the one-letter half of
    # G34, which the expert accepts; the step settles it only on the rest of G34
    # (test_a_place_fits_the_other_place_fields_its_reading_writes).
    ("province_state", "Chimaltenago", CHIMALTENANGO, "Chimaltenango", "tgn:1000565", True),
    # Two letters from it.
    ("province_state", "Chimaltango", CHIMALTENANGO, "Chimaltenango", "tgn:1000565", False),
    # A lookup that has nothing to do with what the label writes.
    ("province_state", "Chimaltenago", ESCUINTLA, "Escuintla", "tgn:1000566", False),
    # "P.I." read as the Philippines: the query is neither the label's text, nor the name the
    # notation table gives it, nor one letter from it.
    ("country", "P.I.", PHILIPPINES_BY_NAME, "Philippines", "tgn:1000135", False),
    # The notation table's name for "P.I." (P4).
    ("country", "P.I.", PHILIPPINE_ISLANDS, "Philippines", "tgn:1000135", True),
    # A notation the table does not hold.
    ("country", "Phil. Is.", PHILIPPINE_ISLANDS, "Philippines", "tgn:1000135", False),
])
def test_a_place_settles_only_on_a_lookup_of_the_labels_own_text(key, literal, received, value, authority,
                                                                  settles):
    # A province is written beside its country, which its department lies in.
    text = f"{literal}, Guatemala\nleg. J. Smith" if key == "province_state" else f"{literal}\nleg. J. Smith"
    readings = (Reading("1A", "region-1", "obs-1a", "decided_transcript", text),
                Reading("1B", "region-1", "obs-1b", "raw_reading", text))
    made = experts._Expert(task(key, candidates=offered(("1A", literal), ("1B", literal))), readings,
                           FakeTools(), PILOT_DATES)
    made.calls.append(experts._Call(received.source_id, received.query, received.status, received))
    given = answer(outcome="resolved", literal=literal, reading_names=["1A"], value=value,
                   authority_id=authority, source_evidence_ids=[received.evidence.id])

    if settles:
        assert made.validate(given).literal == literal
        return
    with pytest.raises(ModelRetry, match="asked the label's own text"):
        made.validate(given)


GUATEMALA = agreement.PlaceField(("Guatemala",), "tgn:7005493")
PHILIPPINES_SETTLED = agreement.PlaceField(("P.I.", "Philippines"), "tgn:1000135")


@pytest.mark.parametrize(("key", "candidate", "basis", "written", "settled", "reason"), [
    # The department, asked or one letter off, on a reading whose one other place field is
    # its country (G34's whole condition).
    ("province_state", CHIMALTENANGO.candidates[1], agreement.ASKED, {"country": GUATEMALA},
     {"country": GUATEMALA}, None),
    ("province_state", CHIMALTENANGO.candidates[1], agreement.NEAR_SPELLING, {"country": GUATEMALA},
     {"country": GUATEMALA}, None),
    # The reading also writes a city, which no province lies in.
    ("province_state", CHIMALTENANGO.candidates[1], agreement.NEAR_SPELLING,
     {"country": GUATEMALA, "city": agreement.PlaceField(("Yepocapa",))}, {"country": GUATEMALA},
     agreement.NEAR_UNFIT),
    # No other place field at all (this file's earlier case): no country settled for it.
    ("province_state", CHIMALTENANGO.candidates[1], agreement.NEAR_SPELLING, {}, {}, agreement.NO_COUNTRY),
    # A country one letter off needs another place field too, and none is its parent.
    ("country", tgn("Guatemala", "ev-gt", ("Guatemala", "tgn:7005493", NATION, IN_GUATEMALA)).candidates[0],
     agreement.NEAR_SPELLING, {}, {}, agreement.NEAR_UNFIT),
    # A Philippine label's country.
    ("province_state", CHIMALTENANGO.candidates[1], agreement.ASKED, {"country": PHILIPPINES_SETTLED},
     {"country": PHILIPPINES_SETTLED}, agreement.NOT_IN_COUNTRY),
    # TGN names a Philippine place's country "Pilipinas", by the record of the nation it
    # calls "Philippines" when searched.
    ("province_state", tgn("Davao", "ev-dv", ("Davao", "tgn:7668798", FIRST, (("Pilipinas", "tgn:1000135"),)))
     .candidates[0], agreement.ASKED, {"country": PHILIPPINES_SETTLED}, {"country": PHILIPPINES_SETTLED}, None),
    # The town lies in its department: a city settled inside the province settled for it.
    ("city", CHIMALTENANGO.candidates[0], agreement.ASKED, {"country": GUATEMALA},
     {"country": GUATEMALA, "province_state": agreement.PlaceField(("Chimaltenango",), "tgn:1000565")}, None),
    ("city", CHIMALTENANGO.candidates[0], agreement.ASKED, {"country": GUATEMALA},
     {"country": GUATEMALA, "province_state": agreement.PlaceField(("Escuintla",), "tgn:1000566")},
     agreement.NOT_IN_PROVINCE),
    # No parents, no settling.
    ("city", SourceCandidate("Yepocapa", "geolocate:1"), agreement.ASKED, {"country": GUATEMALA},
     {"country": GUATEMALA}, agreement.NO_PARENTS),
], ids=["asked", "near-spelling", "near-spelling-with-a-city", "near-spelling-alone", "country-near-spelling",
        "another-country", "by-record", "town-in-province", "town-in-another-province", "no-parents"])
def test_a_place_fits_the_other_place_fields_its_reading_writes(key, candidate, basis, written, settled, reason):
    refused = agreement.parents_refusal(key, candidate, basis, written=written, settled=settled)
    assert (refused.reason if refused else None) == reason


def test_readers_that_differ_in_lower_case_settle_on_the_lookup_of_their_name():
    """105526328's province: 3A writes "chimaltenango,", 3B "chimaltenago,",
    no reading decided. TGN, asked "Chimaltenango", has the department and its
    town, and nothing for "Chimaltenago": 3A's text settles (G20), case and
    the comma aside."""
    readings = (Reading("3A", "region-3", "obs-3a", "raw_reading", "Mun. Yepocapa, chimaltenango,"),
                Reading("3B", "region-3", "obs-3b", "raw_reading", "Mun. Yepocapa, chimaltenago,"))
    field = task("province_state", current=FieldValue(state=ValueState.AMBIGUOUS),
                 candidates=offered(("3A", "chimaltenango,"), ("3B", "chimaltenago,")))
    made = experts._Expert(field, readings, FakeTools(), PILOT_DATES)
    for found in (CHIMALTENANGO, nothing("Chimaltenago", "ev-none")):
        made.calls.append(experts._Call(found.source_id, found.query, found.status, found))
    given = answer(outcome="resolved", literal="chimaltenango,", reading_names=["3A"], value="Chimaltenango",
                   authority_id="tgn:1000565", source_evidence_ids=["ev-chim"])

    assert made.validate(given).value == "Chimaltenango"


def test_a_near_spelling_on_a_decided_label_settles_on_the_one_letter_bound():
    """105526330's province: the decided reading 2A writes "Chimaltenago", its
    other reader "Chimaltenango", and TGN knows only the second. The other
    reader's spelling as the literal is refused (G19); 2A's spelling, with
    TGN's department, one letter from it, as the value, settles (G27, G34)."""
    readings = (Reading("2A", "region-2", "obs-2a", "decided_transcript", "Chimaltenago, Guatemala"),
                Reading("2B", "region-2", "obs-2b", "raw_reading", "Chimaltenango, Guatemala"))
    field = task("province_state", current=FieldValue(state=ValueState.SUPPORTED, literal="Chimaltenago"),
                 candidates=offered(("2A", "Chimaltenago"), ("2B", "Chimaltenango")))
    made = experts._Expert(field, readings, FakeTools(), PILOT_DATES)
    for found in (CHIMALTENANGO, nothing("Chimaltenago", "ev-none")):
        made.calls.append(experts._Call(found.source_id, found.query, found.status, found))
    sourced = dict(authority_id="tgn:1000565", source_evidence_ids=["ev-chim"])

    with pytest.raises(ModelRetry, match="decided for this label"):
        made.validate(answer(outcome="resolved", literal="Chimaltenango", reading_names=["2B"], **sourced))
    kept = made.validate(answer(outcome="resolved", literal="Chimaltenago", reading_names=["2A"],
                                value="Chimaltenango", **sourced))
    assert (kept.literal, kept.value) == ("Chimaltenago", "Chimaltenango")
    assert agreement.place_basis(field, "Chimaltenago", "Chimaltenango", "tgn:1000565",
                                 [CHIMALTENANGO]) == agreement.NEAR_SPELLING


def test_a_place_resolves_only_on_a_place_sources_candidate():
    made = expert("city", [town("Davao", "ev-davao")])

    with pytest.raises(ModelRetry, match="place source's success or ambiguous answer"):
        made.validate(answer(outcome="resolved", literal="Davao", reading_names=["1A"]))
    accepted = made.validate(answer(outcome="resolved", literal="Davao", reading_names=["1A"],
                                    authority_id="geolocate:Davao", source_evidence_ids=["ev-davao"]))
    assert accepted.authority_id == "geolocate:Davao"


def test_a_label_with_a_decided_transcript_takes_its_text_from_it():
    """1A is label 1's decided transcript ("F. G. Werner"); reader 1B writes "F.G. Werner"."""
    made = expert("collectors")

    with pytest.raises(ModelRetry, match="decided for this label"):
        made.validate(answer(outcome="resolved", literal="F.G. Werner", reading_names=["1B"]))
    assert made.validate(answer(outcome="resolved", literal="F. G. Werner",
                                reading_names=["1A"])).literal == "F. G. Werner"


def test_a_resolved_elevation_in_its_own_unit_is_accepted():
    made = expert("elevation_from_ft")

    accepted = made.validate(answer(outcome="resolved", literal="1500", reading_names=["2a"]))

    assert accepted.reading_names == ["2A"]
