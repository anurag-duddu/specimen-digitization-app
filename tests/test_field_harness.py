"""The stage 7 field harness (HARNESS.md section 11)."""

import json
from functools import partial

import pytest
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from specimen_digitization.application.domain import FieldValue, Lookup
from specimen_digitization.application.domain import LookupStatus as S
from specimen_digitization.application.domain import ValueState as V
from specimen_digitization.application.field_harness import (
    MAX_GEOCODING_REQUESTS,
    MAX_OUTPUT_TOKENS,
    MAX_TOOL_CALLS,
    REQUEST_LIMIT,
    FieldPlan,
    HarnessOutput,
    build_request,
    labelled,
    output_problems,
    run_harness,
)
from specimen_digitization.application.field_resolution import Reading
from specimen_digitization.application.field_validators import (
    catalog_number_validator,
    date_parser,
)
from specimen_digitization.application.harness_ledger import ToolLedger, Tools
from specimen_digitization.application.harness_tools import (
    PlaceCandidate,
    SourceCall,
    TaxonCandidate,
    ToolResult,
)
from specimen_digitization.application.reliability import AdapterFailure
from specimen_digitization.application.taxonomy_tool import Verification

DATE_RULES = {
    "version": "date-rules-v1",
    "two_digit_year_century": 1900,
    "roman_numeral_months": True,
}
PLAN = FieldPlan(
    mandatory=(
        "fmnh_ins_number",
        "country",
        "city",
        "precise_location",
        "collectors",
        "date_visited_from",
        "date_identified",
        "taxon",
    ),
    optional=("identified_by_irn",),
    tools={
        "fmnh_ins_number": "catalog_number_validator",
        "country": "geography_lookup",
        "city": "geography_lookup",
        "precise_location": "geography_lookup",
        "date_visited_from": "date_parser",
        "date_identified": "date_parser",
        "taxon": "taxonomy_verifier",
    },
)
LOCALITY = "Chimaltenango, GUAT.\nE. slope Volcan Fuego\n4-5-48 F.G. Werner"
DECIDED = Reading("r1", "o-muse", "decided_transcript", LOCALITY)
RAW = Reading("r1", "o-qwen", "raw_reading", LOCALITY.replace("Werner", "Wermer"))
DET = Reading(
    "r2", "o-det", "decided_transcript", "Epipsocus\ndet. 13-5-48\nFMNH INS 0123456"
)
READINGS = [DECIDED, RAW, DET]
GOOGLE = "google-maps-geocoding"


def answer(**by_reading):
    """The harness's final output: {reading: {field: literal}}."""
    return {
        "literals": [
            {"field_key": key, "reading": reading, "literal": literal}
            for reading, fields in by_reading.items()
            for key, literal in fields.items()
        ]
    }


FULL = answer(
    **{
        "1A": {
            "country": "GUAT.",
            "city": "Chimaltenango",
            "precise_location": "E. slope Volcan Fuego",
            "collectors": "F.G. Werner",
            "date_visited_from": "4-5-48",
        },
        "1B": {
            "country": "GUAT.",
            "city": "Chimaltenango",
            "precise_location": "E. slope Volcan Fuego",
            "collectors": "F.G. Wermer",
            "date_visited_from": "4-5-48",
        },
        "2A": {
            "taxon": "Epipsocus",
            "date_identified": "13-5-48",
            "fmnh_ins_number": "FMNH INS 0123456",
        },
    }
)


class Fakes:
    """Taxonomy and geography fakes; the validators are the real ones."""

    def __init__(self):
        self.calls = []

    def verify_taxon(self, literal):
        self.calls.append(("taxon", literal))
        taxon = TaxonCandidate(
            source="gbif",
            usage_key="8MQRG",
            name="Epipsocus Hagen, 1866",
            rank="GENUS",
            status="ACCEPTED",
        )
        calls = [
            SourceCall(
                source=s, query={"name": literal}, retrieved_at="t", outcome=S.SUCCESS
            )
            for s in ("gbif", "gnv", "col")
        ]
        result = ToolResult(
            tool="taxonomy_verifier",
            tool_version="v1",
            outcome=S.SUCCESS,
            taxa=[taxon],
            sub_calls=calls,
        )
        return Verification(
            result,
            Lookup(
                provider="gbif",
                adapter_version="v2",
                query={"scientificName": literal},
                status=S.SUCCESS,
            ),
        )

    def geocode(self, query):
        fields = {item.field_key: item.literal for item in query.literals}
        self.calls.append(("geocode", fields))
        outcomes = {k: S.SUCCESS for k in fields if k in ("city", "country")}
        places = [
            PlaceCandidate(
                field_key=k, source=GOOGLE, source_record_id="place-chimaltenango"
            )
            for k in outcomes
        ]
        call = SourceCall(
            source=GOOGLE,
            query={"address": "x"},
            retrieved_at="t",
            outcome=S.SUCCESS,
            raw_ref="blob",
        )
        return ToolResult(
            tool="geography_lookup",
            tool_version="v1",
            outcome=S.SUCCESS,
            field_outcomes=outcomes,
            places=places,
            sub_calls=[call],
        )

    def tools(self):
        return Tools(
            verify_taxon=self.verify_taxon,
            geocode=self.geocode,
            parse_date=partial(date_parser, date_rules=DATE_RULES),
            check_catalog_number=catalog_number_validator,
        )


def model(*turns, seen=None):
    """A fake provider: each turn is a final answer (dict), a list of tool
    calls ((name, args), ...), or an exception; the last turn repeats."""
    seen = [] if seen is None else seen

    def respond(messages, info):
        seen.append((messages, info))
        turn = turns[min(len(seen), len(turns)) - 1]
        if isinstance(turn, Exception):
            raise turn
        if isinstance(turn, dict):
            return ModelResponse(
                parts=[ToolCallPart(info.output_tools[0].name, json.dumps(turn))]
            )
        return ModelResponse(
            parts=[ToolCallPart(name, json.dumps(args)) for name, args in turn]
        )

    return FunctionModel(respond, model_name="fake-harness")


class Blobs:
    def __init__(self):
        self.puts = []

    def put(self, data: bytes) -> str:
        self.puts.append(data)
        return f"blob-{len(self.puts)}"


def harness(*turns, seen=None, fakes=None, readings=READINGS):
    fakes = fakes or Fakes()
    ledger = ToolLedger(fakes.tools(), asset_id="asset-1")
    outcome = run_harness(
        model(*turns, seen=seen),
        "You are the field harness.",
        plan=PLAN,
        readings=readings,
        notes={"o-qwen": "misread Werner"},
        ledger=ledger,
        asset_id="asset-1",
        blobs=Blobs(),
        timeout_seconds=30,
    )
    return outcome, fakes


def test_readings_are_named_by_label_and_the_request_names_no_model():
    names = labelled(READINGS)
    request = build_request(PLAN, names, {"o-qwen": "misread Werner"})

    assert list(names) == ["1A", "1B", "2A"]
    assert "Reading 1A (decided transcript):" in request
    assert "Reading 1B (raw reading; first pass: misread Werner):" in request
    assert (
        "taxon [taxonomy_verifier]" in request
        and "Optional fields: identified_by_irn" in request
    )
    assert "qwen" not in request.replace("o-qwen", "") and "Label 2:" in request


def test_output_problems_name_each_fault():
    names = labelled(READINGS)
    bad = HarnessOutput.model_validate(
        answer(
            **{"1A": {"habitat": "forest", "city": "Chimaltenago"}, "9Z": {"city": "x"}}
        )
    )
    twice = HarnessOutput.model_validate(
        {
            "literals": [
                {"field_key": "city", "reading": "1A", "literal": t}
                for t in ("Chimaltenango", "GUAT.")
            ]
        }
    )

    assert output_problems(bad, names, PLAN) == [
        "habitat is not a field of this profile",
        "city: copy the literal exactly as reading 1A has it",
        "9Z is not a reading you were given",
    ]
    assert output_problems(twice, names, PLAN) == [
        "city: give one literal per reading, not two for 1A"
    ]


def test_every_field_is_decided_from_recorded_outcomes():
    outcome, fakes = harness(FULL)

    fields = outcome.fields
    assert (fields["taxon"].state, fields["taxon"].authority_id) == (
        V.SUPPORTED,
        "8MQRG",
    )
    assert (fields["city"].authority_id, fields["city"].normalized) == (
        "place-chimaltenango",
        "Chimaltenango",
    )
    # Verbatim locality text: transcribed, never settled by a geocoder (PRD 515).
    assert (
        fields["precise_location"].literal,
        fields["precise_location"].authority_id,
    ) == ("E. slope Volcan Fuego", None)
    assert (fields["collectors"].state, fields["collectors"].literal) == (
        V.SUPPORTED,
        "F.G. Werner",
    )
    assert fields["fmnh_ins_number"].parsed == "0123456"
    assert fields["identified_by_irn"] == FieldValue()  # Not on the label.
    assert outcome.blocker is None and outcome.failure is None
    geocodes = [c for c in fakes.calls if c[0] == "geocode"]
    assert len(geocodes) == 1  # The decided transcript settled city and country.
    assert {r.tool for r in outcome.tool_calls} == {
        "taxonomy_verifier",
        "geography_lookup",
        "date_parser",
        "catalog_number_validator",
    }
    assert [lookup.status for lookup in outcome.lookups] == [S.SUCCESS]


def test_a_numeric_date_takes_the_order_the_specimens_dates_fix():
    outcome, _ = harness(FULL)

    visited = outcome.fields["date_visited_from"]
    # 4-5-48 reads both ways; the det label's 13-5-48 fixes day-month (G33).
    assert (visited.state, visited.parsed, visited.precision) == (
        V.SUPPORTED,
        "1948-05-04",
        "day",
    )
    assert visited.century_rule == "date-rules-v1:two_digit_year_century=1900"
    order = next(e for e in outcome.evidence if e.kind == "date_order")
    assert order.id in visited.evidence_ids and order.observation_ids == ["o-det"]


def test_the_agent_checks_with_tools_and_sees_no_google_name():
    seen = []
    check = [
        (
            "geocode",
            {
                "reading": "1A",
                "fields": {
                    "country": "GUAT.",
                    "city": "Chimaltenango",
                    "precise_location": "E. slope Volcan Fuego",
                },
            },
        )
    ]

    outcome, fakes = harness(check, FULL, seen=seen)

    returned = [
        p
        for m in seen[1][0]
        for p in getattr(m, "parts", [])
        if isinstance(p, ToolReturnPart)
    ]
    assert returned[0].content == {
        "outcome": "success",
        "field_outcomes": {"city": "success", "country": "success"},
    }
    assert (
        len([c for c in fakes.calls if c[0] == "geocode"]) == 1
    )  # One request, reused.
    assert outcome.fields["city"].state == V.SUPPORTED


def test_every_request_is_capped_at_the_harness_output_budget():
    seen = []

    harness(FULL, seen=seen)

    assert [
        info.model_settings["max_tokens"] <= MAX_OUTPUT_TOKENS for _, info in seen
    ] == [True]


def test_an_answer_that_stays_invalid_is_a_harness_failure_for_review():
    invalid = answer(**{"1A": {"city": "Chimaltenago"}})

    outcome, _ = harness(invalid)

    assert outcome.failure == "harness_malformed_output"
    assert all(value == FieldValue() for value in outcome.fields.values())


def test_the_request_cap_is_a_harness_failure_for_review():
    seen = []
    forever = [("verify_taxon", {"reading": "2A", "literal": "Epipsocus"})]

    outcome, _ = harness(forever, seen=seen)

    assert outcome.failure == "harness_usage_limit" and len(seen) == REQUEST_LIMIT


def test_a_provider_error_stays_an_operational_block():
    error = ModelHTTPError(status_code=429, model_name="fake-harness", body="slow down")

    with pytest.raises(AdapterFailure) as failure:
        harness(error)

    assert failure.value.status == S.RATE_LIMITED


def returns(seen, turn):
    """The tool results the model saw at the start of this turn."""
    return [
        p.content
        for m in seen[turn][0]
        for p in getattr(m, "parts", [])
        if isinstance(p, ToolReturnPart)
    ]


def test_geocoding_is_one_budget_for_the_agent_and_the_final_lookups():
    # G30: at most four geocoding requests a run, whoever makes them.
    fields = ["GUAT.", "Chimaltenango", "E. slope Volcan Fuego", "Volcan Fuego"]
    checks = [
        [("geocode", {"reading": "1A", "fields": {"country": fields[0], "city": city}})]
        for city in (
            "Chimaltenango",
            "Volcan Fuego",
            "Chimaltenango, GUAT.",
            "GUAT.",
            "Fuego",
        )
    ]
    seen = []

    outcome, fakes = harness(*checks, FULL, seen=seen)

    assert len([c for c in fakes.calls if c[0] == "geocode"]) == MAX_GEOCODING_REQUESTS
    assert returns(seen, 5)[-1] == {
        "outcome": "not_checked",
        "reason": "the run's geocoding requests are used",
    }
    # The final lookup on 1A's answer would be a fifth request: refused, and
    # a refused paid request blocks the run (QUE-005).
    assert outcome.blocker == "harness_geography_lookup_policy_blocked"


def test_tool_calls_past_the_run_cap_are_refused_without_a_lookup():
    twice = [("verify_taxon", {"reading": "2A", "literal": "Epipsocus"})] * 2
    seen = []

    outcome, fakes = harness(*[twice] * 7, FULL, seen=seen)

    assert len([c for c in fakes.calls if c[0] == "taxon"]) == 1  # One request.
    history = returns(seen, len(seen) - 1)  # Every tool result, once each.
    assert (
        history.count(
            {"refused": "no tool calls remain in this run; give your final answer"}
        )
        == 14 - MAX_TOOL_CALLS
    )
    assert outcome.failure is None


def test_a_prompt_past_its_byte_cap_is_a_harness_failure_before_any_call():
    seen = []
    huge = Reading("r1", "o-muse", "decided_transcript", "x " * 7000)

    outcome, _ = harness(FULL, seen=seen, readings=[huge])

    assert outcome.failure == "harness_input_too_large" and seen == []


def test_a_tool_call_outside_the_profiles_fields_is_returned_for_a_retry():
    wrong = [("geocode", {"reading": "1A", "fields": {"collectors": "F.G. Werner"}})]
    seen = []

    outcome, _ = harness(wrong, FULL, seen=seen)

    retry = [
        p.content
        for m in seen[1][0]
        for p in getattr(m, "parts", [])
        if type(p).__name__ == "RetryPromptPart"
    ]
    assert retry == ["collectors is not a locality field"]
    assert outcome.fields["city"].state == V.SUPPORTED
