"""WP 1.3's rework, gap report item 3: the units path's expert request against the input bound
(budget.DEFAULT_MAX_INPUT_TOKENS, 48,000 bytes), on the two province experts WP 1.5 refused as
input_too_large (r1/pair 105526325 and r2/pair 105526324; tests/fixtures/
units_province_request_<slide>.json, from WP 1.5's stored runs). A stored run keeps the expert's
lookups, not its messages, so each conversation here is rebuilt: its lookups, grouped by query (the
first with the NGA lookup that timed out), two answers the checks refuse, each with as long an
explanation as an answer may give, then the request for its answer once its turns are used up.
That the rebuilt conversation fits shows nothing about the refused production request, which was
larger. Every test here runs once: this module's first_pass_path fixture replaces conftest.py's,
as no run is built."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from specimen_digitization.application.domain import Evidence, FieldValue, LookupStatus
from specimen_digitization.application.reading_units import ReadingUnits
from specimen_digitization.field_research import budget, experts
from specimen_digitization.field_research.contracts import (
    Candidate,
    FieldAnswer,
    FieldTask,
    Reading,
    SourceAnswer,
    SourceCandidate,
)

FIXTURES = Path(__file__).parents[1] / "fixtures"
SLIDES = ("105526325", "105526324")
# The largest request of each rebuilt conversation, in bytes (budget.input_token_bound), with WP 2.2's
# instructions: the province expert's rules (ontology.render_instructions("expert", "province_state"),
# 523 bytes with the blank line before them) in, common.txt's two date notation lines replaced (573
# bytes out; test_units_instructions.py). On main 530b2cf18 they were 47,867 and 47,495.
LARGEST = {"105526325": 47_817, "105526324": 47_445}


@pytest.fixture(autouse=True)
def first_pass_path():
    return "units"


def loaded(slide):
    """The fixture's readings (with their units), the province task, the other fields' values and
    the lookups, by source and query."""
    data = json.loads((FIXTURES / f"units_province_request_{slide}.json").read_text(encoding="utf-8"))
    readings = tuple(Reading(r["name"], r["region_id"], r["observation_id"], r["input_source"], r["text"],
        units=ReadingUnits.model_validate(r["units"]) if r["units"] is not None else None) for r in data["readings"])
    given = data["task"]
    task = FieldTask(given["key"], given["mandatory"], FieldValue.model_validate(given["current"]),
        tuple(Candidate(**candidate) for candidate in given["candidates"]), tuple(given["tools"]))
    context = {key: FieldValue(literal=value["literal"], verbatim_by_observation=value["verbatim_by_observation"])
        for key, value in data["context"].items()}
    lookups = {(item["source"], item["query"]): SourceAnswer(item["source"], item["query"],
        LookupStatus(item["status"]), tuple(SourceCandidate(**candidate) for candidate in item["candidates"]),
        Evidence(**item["evidence"]), note=item["note"]) for item in data["lookups"]}
    return readings, task, context, lookups


class Stored:
    """The province expert's sources: each stored lookup's answer; NGA timed out."""

    sources = ("geolocate", "tgn", "wikidata", "nga")

    def __init__(self, lookups):
        self.lookups = lookups

    async def lookup(self, source_id, query, *, field_key):
        if (source_id, query) in self.lookups:
            return self.lookups[(source_id, query)]
        return SourceAnswer(source_id, query, LookupStatus.TIMEOUT, (), None, note="timed out")


def conversation(lookups, literal=None):
    """The rebuilt conversation (module docstring) as a FunctionModel's turns; with `literal`, both refused
    answers give that literal (as for an expert other than the province's)."""
    queries = list(dict.fromkeys(query for _, query in lookups))
    turns = [[ToolCallPart("lookup", {"source": source, "query": query})
        for source, query in [*(key for key in lookups if key[1] == each), *((("nga", each),) if each == queries[0]
            else ())]] for each in queries]
    [wikidata] = [answer for (source, _), answer in lookups.items()
        if source == "wikidata" and answer.status == LookupStatus.SUCCESS]
    # As long as an answer's explanation may be (experts.MAX_EXPLANATION).
    explanation = ("The readings write 'Davao Prov.' and 'Mindanao'; Wikidata confirms Davao as the province, and "
        "Mindanao is the island the province lies on, so the province is Davao. " * 5)[:experts.MAX_EXPLANATION]
    refused = [{"outcome": "resolved", "literal": literal or "Mindanao", "reading_names": ["2A", "2B"],
        "source_evidence_ids": [wikidata.evidence.id], "explanation": explanation},
        {"outcome": "resolved", "literal": literal or "Mindanao", "reading_names": ["2A"], "value": literal or "Mindanao",
         "source_evidence_ids": [wikidata.evidence.id], "explanation": explanation}]
    sent = []

    def respond(messages, info):
        sent.append(len(messages))
        if len(sent) <= len(turns):
            return ModelResponse(parts=turns[len(sent) - 1])
        given = refused[len(sent) - len(turns) - 1] if len(sent) - len(turns) <= len(refused) else {
            "outcome": "sources_cannot_resolve", "explanation": "The sources do not settle the province."}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, given)])

    return respond, len(turns) + len(refused) + 1


def test_the_input_bound_is_48000_bytes():
    """The bound the size test below measures against (budget.DEFAULT_MAX_INPUT_TOKENS): raising
    it is a change this test makes visible."""
    assert budget.DEFAULT_MAX_INPUT_TOKENS == 48_000


@pytest.mark.parametrize("slide", SLIDES)
def test_the_rebuilt_conversation_of_a_refused_province_request_fits_the_input_bound(monkeypatch, slide):
    """Every request of the rebuilt conversation (module docstring) is sent, the largest under the
    bound: the request carries each reading's name and text, an agreed unit's text once, and the
    instructions leave out the label notations the ontology's text gives (experts.units_document,
    prompts/units.txt). It shows the rebuilt conversation fits, not the refused one."""
    readings, task, context, lookups = loaded(slide)
    assert all(reading.units is not None for reading in readings)
    bounds = []
    measure = budget.input_token_bound

    def measured(messages, parameters):
        bounds.append(measure(messages, parameters))
        return bounds[-1]

    monkeypatch.setattr(budget, "input_token_bound", measured)
    respond, requests = conversation(lookups)
    resolver = experts.make_resolver(model_factory=lambda: FunctionModel(respond),
        meter=budget.CostMeter(10_000_000, input_micros_per_million=200_000, output_micros_per_million=600_000))
    outcome = asyncio.run(resolver(task, readings, context, tools=Stored(lookups)))
    assert outcome.failure is None and outcome.answer == FieldAnswer(outcome="sources_cannot_resolve",
        explanation="The sources do not settle the province.")
    assert len(bounds) == requests == 7
    assert max(bounds) == LARGEST[slide] <= budget.DEFAULT_MAX_INPUT_TOKENS


def test_a_unit_whose_readers_write_one_text_carries_it_once():
    """experts.units_document: a unit cut from two or more readings that each write the same
    text there carries it once (text); a unit whose readers differ, and a label with one
    reading, carry each reader's text (readers)."""
    from test_first_pass_advice import with_units

    pair = with_units((Reading("1A", "r1", "o1a", "raw_reading", "Shrubs, forest"),
        Reading("1B", "r1", "o1b", "raw_reading", "Shurbs, forest"),
        Reading("2A", "r2", "o2a", "raw_reading", "Mt. Apo")))
    document = experts.units_document(pair)
    assert [(unit.get("text"), unit.get("readers")) for unit in document["1"]] == [
        (None, {"1A": "Shrubs,", "1B": "Shurbs,"}), ("forest", None)]
    assert [unit["readers"] for unit in document["2"]] == [{"2A": "Mt."}, {"2A": "Apo"}]


# WP 2.2's review (G51, not blocking 2): the precise location expert's units-path instructions are now longer
# than the province's. The same rebuilt conversation given to each place expert, both refused answers forced to
# one literal no reading writes ("Mindanaq", refused as no candidate), measured in bytes at its largest request.
PLACE_EXPERTS = ("province_state", "precise_location", "city", "county", "country")
LARGEST_BY_EXPERT = {
    ("105526325", "province_state"): 46_179, ("105526325", "precise_location"): 46_690, ("105526325", "city"): 45_513,
    ("105526325", "county"): 46_065, ("105526325", "country"): 44_803,
    ("105526324", "province_state"): 45_807, ("105526324", "precise_location"): 46_271, ("105526324", "city"): 45_141,
    ("105526324", "county"): 45_693, ("105526324", "country"): 44_431,
}


@pytest.mark.parametrize("key", PLACE_EXPERTS)
@pytest.mark.parametrize("slide", SLIDES)
def test_the_rebuilt_conversation_given_to_each_place_expert_fits_the_input_bound(monkeypatch, slide, key):
    """It shows the margin of each place expert on one conversation, not a maximum over every conversation."""
    from dataclasses import replace

    from specimen_digitization.field_research.contracts import FIELD_TOOLS

    readings, task, context, lookups = loaded(slide)
    task = replace(task, key=key, tools=tuple(FIELD_TOOLS[key]))
    bounds = []
    measure = budget.input_token_bound
    monkeypatch.setattr(budget, "input_token_bound", lambda messages, parameters: bounds.append(
        measure(messages, parameters)) or bounds[-1])
    respond, requests = conversation(lookups, "Mindanaq")
    resolver = experts.make_resolver(model_factory=lambda: FunctionModel(respond),
        meter=budget.CostMeter(10_000_000, input_micros_per_million=200_000, output_micros_per_million=600_000))
    outcome = asyncio.run(resolver(task, readings, context, tools=Stored(lookups)))
    assert outcome.failure is None and outcome.answer.outcome == "sources_cannot_resolve"
    assert len(bounds) == requests == 7
    assert max(bounds) == LARGEST_BY_EXPERT[(slide, key)] <= budget.DEFAULT_MAX_INPUT_TOKENS
