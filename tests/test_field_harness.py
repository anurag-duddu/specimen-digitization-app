"""The stage 7 field harness (HARNESS.md section 11)."""

import hashlib
import json
import time
from functools import partial

import httpx
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
    resolve,
    run_harness,
)
from specimen_digitization.application.field_resolution import Reading
from specimen_digitization.application.field_validators import (
    catalog_number_validator,
    date_parser,
)
from specimen_digitization.application.harness_ledger import ToolLedger, Tools
from specimen_digitization.application.harness_tools import (
    Check,
    Derivation,
    PlaceCandidate,
    SourceCall,
    SourceRef,
    TaxonCandidate,
    ToolResult,
)
from specimen_digitization.application.reliability import AdapterFailure
from specimen_digitization.application.storage import LocalBlobs
from specimen_digitization.application.taxonomy_tool import Verification, verify_taxon

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

    def verify_taxon(self, literal, place_text=()):
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


def harness(*turns, seen=None, fakes=None, readings=READINGS, plan=PLAN, blobs=None):
    fakes = fakes or Fakes()
    ledger = ToolLedger(fakes.tools(), asset_id="asset-1")
    outcome = run_harness(
        model(*turns, seen=seen),
        "You are the field harness.",
        plan=plan,
        readings=readings,
        notes={"o-qwen": "misread Werner"},
        ledger=ledger,
        asset_id="asset-1",
        blobs=blobs if blobs is not None else Blobs(),
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


def test_two_identical_calls_in_one_response_make_one_request():
    # pydantic-ai runs a response's tool calls in parallel threads unless told
    # otherwise. The harness runs them one at a time, so the ledger's record of
    # the first answers the second, and the caps count exactly.
    class Slow(Fakes):
        def verify_taxon(self, literal, place_text=()):
            time.sleep(0.05)  # Both calls would be in flight together.
            return super().verify_taxon(literal)

    twice = [("verify_taxon", {"reading": "2A", "literal": "Epipsocus"})] * 2

    _, fakes = harness(twice, FULL, fakes=Slow())

    assert len([c for c in fakes.calls if c[0] == "taxon"]) == 1


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


ELEVATIONS = FieldPlan(
    mandatory=(
        "elevation_from_m",
        "elevation_to_m",
        "elevation_from_ft",
        "elevation_to_ft",
    )
)


def test_elevations_the_label_leaves_out_are_derived_with_evidence():
    # G37: one stated elevation fills both ends and, by the exact factor, feet.
    reading = Reading("r1", "o-muse", "decided_transcript", "Volcan Fuego, 1200 m")

    outcome, _ = harness(
        answer(**{"1A": {"elevation_from_m": "1200 m"}}),
        readings=[reading],
        plan=ELEVATIONS,
    )

    fields = outcome.fields
    assert (fields["elevation_from_m"].literal, fields["elevation_from_m"].layer) == (
        "1200 m",
        "verbatim",
    )
    assert {
        k: (v.parsed, v.layer) for k, v in fields.items() if k != "elevation_from_m"
    } == {
        "elevation_to_m": ("1200", "derived"),
        "elevation_from_ft": ("3937.01", "derived"),
        "elevation_to_ft": ("3937.01", "derived"),
    }
    rules = {e.locator for e in outcome.evidence if e.kind == "derivation"}
    assert rules == {"derivation:stated_elevation", "derivation:unit_conversion"}


def test_a_value_the_model_asserts_without_a_record_does_not_count():
    # #124: a derived value counts only with its record. The agent can only
    # propose what a reading says; the metres come from G41's rule alone.
    reading = Reading("r1", "o-muse", "decided_transcript", "Volcan Fuego, 3937 ft")
    asserted = answer(
        **{"1A": {"elevation_from_ft": "3937 ft", "elevation_from_m": "1250 m"}}
    )
    seen = []

    outcome, _ = harness(
        asserted,
        answer(**{"1A": {"elevation_from_ft": "3937 ft"}}),
        seen=seen,
        readings=[reading],
        plan=ELEVATIONS,
    )

    retry = [
        p.content
        for m in seen[1][0]
        for p in getattr(m, "parts", [])
        if type(p).__name__ == "RetryPromptPart"
    ]
    assert retry == ["elevation_from_m: copy the literal exactly as reading 1A has it"]
    metres = outcome.fields["elevation_from_m"]
    assert (metres.layer, metres.parsed, metres.derived_from) == (
        "derived",
        "1200",
        ["elevation_from_ft"],
    )
    (rule,) = [
        e
        for e in outcome.evidence
        if e.id in metres.evidence_ids and e.kind == "derivation"
    ]
    assert (rule.source, rule.locator) == (
        "apply_derivations",
        "derivation:unit_conversion",
    )


def test_a_geography_results_derivation_fills_a_field_the_label_leaves_out():
    # G37: S8's tool derives the county by containment from the settled city.
    class Deriving(Fakes):
        def geocode(self, query):
            county = Derivation(
                field_key="county",
                value="Chimaltenango",
                method="containment",
                authority=SourceRef(name="gadm", record_id="GTM.4_1", version="4.1"),
                inputs={"city": "place-chimaltenango"},
                evidence=[Check(name="circle_inside_unit", result="supports")],
            )
            result = super().geocode(query)
            return result.model_copy(update={"derivations": [county]})

    plan = FieldPlan(
        mandatory=(*PLAN.mandatory, "county"),
        optional=PLAN.optional,
        tools={**PLAN.tools, "county": "geography_lookup"},
    )

    outcome, _ = harness(FULL, fakes=Deriving(), plan=plan)

    county = outcome.fields["county"]
    assert (county.layer, county.parsed, county.authority_id) == (
        "derived",
        "Chimaltenango",
        "GTM.4_1",
    )
    assert county.derived_from == ["city"]
    # It names the geography call that returned it (#124, PLAN 4.8).
    (call,) = [r for r in outcome.tool_calls if r.tool == "geography_lookup"]
    assert county.evidence_relations[call.evidence_id] == "supports"


def _county_derivation(inputs, *, authority="gadm", value="Synthetic County"):
    return Derivation(
        field_key="county",
        value=value,
        method="containment",
        authority=SourceRef(name=authority, record_id="synthetic-unit", version="v1"),
        inputs=inputs,
        evidence=[Check(name="containment", result="supports")],
    )


def _geography_source(source, status=S.SUCCESS, *, attempt=1, raw_ref="source-record"):
    return SourceCall(
        source=source,
        query={"address": "synthetic locality"},
        retrieved_at="t",
        outcome=status,
        attempt=attempt,
        raw_ref=raw_ref,
    )


def _county_result(derivation, sources, *, field_status=S.SUCCESS, status=S.SUCCESS):
    return ToolResult(
        tool="geography_lookup",
        tool_version="v1",
        outcome=status,
        field_outcomes={"city": field_status},
        places=[PlaceCandidate(
            field_key="city", source=GOOGLE, source_record_id="place-local",
        )] if field_status == S.SUCCESS else [],
        sub_calls=sources,
        derivations=[derivation],
    )


def _county_harness(result, *, readings=None, literals=None):
    class Deriving(Fakes):
        def geocode(self, query):
            self.calls.append(("geocode", query))
            return result(query) if callable(result) else result

    readings = readings or [Reading(
        "r1", "o-local", "decided_transcript", "Chimaltenango; Guatemala",
    )]
    literals = literals or {"1A": {"city": "Chimaltenango", "country": "Guatemala"}}
    plan = FieldPlan(
        mandatory=("city", "country", "county"),
        tools={"city": "geography_lookup", "county": "geography_lookup"},
    )
    blobs = Blobs()
    outcome, fakes = harness(
        answer(**literals), fakes=Deriving(), readings=readings, plan=plan, blobs=blobs,
    )
    assert outcome.failure is None
    return outcome, blobs, fakes


def _county_record(outcome, blobs):
    county = outcome.fields["county"]
    rule = next(
        e for e in outcome.evidence
        if e.kind == "derivation" and e.id in county.evidence_ids
    )
    raw = blobs.puts[int(rule.raw_ref.removeprefix("blob-")) - 1]
    assert hashlib.sha256(raw).hexdigest() == rule.digest
    return json.loads(raw)


@pytest.mark.parametrize("inputs,expected", [
    ({"city": "place-local"}, True),
    ({"city": "stale-place"}, False),
    ({}, False),
])
def test_geography_derivation_requires_nonempty_matching_settled_inputs(inputs, expected):
    result = _county_result(_county_derivation(inputs), [_geography_source(GOOGLE)])

    outcome, blobs, _ = _county_harness(result)

    assert outcome.blocker is None
    county = outcome.fields["county"]
    assert (county.layer == "derived") == expected
    if expected:
        assert county.state == V.SUPPORTED and county.derived_from == ["city"]
        (call,) = outcome.tool_calls
        assert _county_record(outcome, blobs)["call_evidence_ids"] == [call.evidence_id]
        assert county.evidence_relations[call.evidence_id] == "supports"


@pytest.mark.parametrize("raw_ref", [None, "failed-source-record"])
@pytest.mark.parametrize("authority", ["gadm", GOOGLE])
def test_policy_failed_producer_cannot_derive_from_an_independently_settled_country(
    raw_ref, authority
):
    result = _county_result(
        _county_derivation({"country": "Guatemala"}, authority=authority),
        [_geography_source(GOOGLE, S.POLICY, raw_ref=raw_ref)],
        field_status=S.POLICY,
        status=S.POLICY,
    )

    outcome, _, _ = _county_harness(result)

    assert outcome.fields["country"].state == V.SUPPORTED
    assert outcome.blocker == "harness_geography_lookup_policy_blocked"
    assert outcome.fields["county"].layer != "derived"
    (call,) = outcome.tool_calls
    assert call.outcome == S.POLICY
    assert (call.evidence_id is None) == (raw_ref is None)
    assert not any(e.kind == "derivation" for e in outcome.evidence)


@pytest.mark.parametrize("authority_status,expected", [(S.SUCCESS, True), (S.POLICY, False)])
def test_recorded_authority_source_cannot_borrow_another_sources_success(
    authority_status, expected
):
    result = _county_result(
        _county_derivation({"city": "place-local"}),
        [_geography_source(GOOGLE), _geography_source("gadm", authority_status)],
    )

    outcome, blobs, _ = _county_harness(result)

    assert outcome.blocker is None
    county = outcome.fields["county"]
    assert (county.layer == "derived") == expected
    assert len(outcome.tool_calls) == 2
    if expected:
        assert set(_county_record(outcome, blobs)["call_evidence_ids"]) == {
            call.evidence_id for call in outcome.tool_calls
        }
    else:
        assert not any(e.kind == "derivation" for e in outcome.evidence)


@pytest.mark.parametrize("authority,expected", [("open-boundaries", True), ("gadm", False)])
def test_successful_recorded_open_producer_survives_an_unrelated_failed_field(
    authority, expected
):
    result = _county_result(
        _county_derivation({"country": "Guatemala"}, authority=authority),
        [_geography_source(GOOGLE, S.POLICY), _geography_source("open-boundaries")],
        field_status=S.POLICY,
        status=S.POLICY,
    )

    outcome, blobs, _ = _county_harness(result)

    assert outcome.blocker == "harness_geography_lookup_policy_blocked"
    assert outcome.fields["country"].state == V.SUPPORTED
    county = outcome.fields["county"]
    assert (county.layer == "derived") == expected
    if expected:
        failed, successful = outcome.tool_calls
        assert _county_record(outcome, blobs)["call_evidence_ids"] == [successful.evidence_id]
        assert county.evidence_relations[successful.evidence_id] == "supports"
        assert failed.evidence_id not in county.evidence_ids


def test_partial_geography_keeps_all_successful_producers_and_no_failed_supports():
    result = _county_result(
        _county_derivation({"city": "place-local"}),
        [_geography_source(GOOGLE), _geography_source("gadm"),
         _geography_source("failed-secondary", S.PROVIDER)],
        status=S.PROVIDER,
    )

    outcome, blobs, _ = _county_harness(result)

    assert outcome.blocker is None
    county = outcome.fields["county"]
    assert county.state == V.SUPPORTED and county.layer == "derived"
    successful = {call.evidence_id for call in outcome.tool_calls if call.outcome == S.SUCCESS}
    (failed,) = [call for call in outcome.tool_calls if call.outcome == S.PROVIDER]
    assert set(_county_record(outcome, blobs)["call_evidence_ids"]) == successful
    assert all(county.evidence_relations[eid] == "supports" for eid in successful)
    assert failed.evidence_id not in county.evidence_ids
    assert any(e.id == failed.evidence_id for e in outcome.evidence)


@pytest.mark.parametrize("statuses,expected", [
    ((S.PROVIDER, S.SUCCESS), True),
    ((S.SUCCESS, S.POLICY), False),
])
def test_authority_eligibility_uses_its_final_attempt_and_preserves_retry_history(statuses, expected):
    result = _county_result(
        _county_derivation({"city": "place-local"}),
        [_geography_source(GOOGLE), *[
            _geography_source("gadm", status, attempt=index)
            for index, status in enumerate(statuses, 1)
        ]],
    )

    outcome, blobs, _ = _county_harness(result)

    county = outcome.fields["county"]
    assert (county.layer == "derived") == expected
    google, first, final = outcome.tool_calls
    assert first.outcome == statuses[0] and first.evidence_id is None
    assert final.outcome == statuses[1] and final.evidence_id is not None
    if expected:
        assert set(_county_record(outcome, blobs)["call_evidence_ids"]) == {
            google.evidence_id, final.evidence_id,
        }
        assert first.evidence_id not in county.evidence_ids


def test_success_without_a_producing_evidence_record_cannot_derive():
    result = _county_result(
        _county_derivation({"country": "Guatemala"}, authority=GOOGLE),
        [_geography_source(GOOGLE, raw_ref=None)],
        field_status=S.POLICY,
        status=S.POLICY,
    )

    outcome, _, _ = _county_harness(result)

    assert outcome.blocker == "harness_geography_lookup_policy_blocked"
    assert outcome.tool_calls[0].outcome == S.SUCCESS
    assert outcome.tool_calls[0].evidence_id is None
    assert outcome.fields["county"].layer != "derived"


def test_failed_first_reading_cannot_poison_a_successful_derivation_fallback():
    def geography(query):
        city = next(item.literal for item in query.literals if item.field_key == "city")
        successful = city == "Right City"
        status = S.SUCCESS if successful else S.NO_MATCH
        return _county_result(
            _county_derivation(
                {"city": "place-local"}, value="Right County" if successful else "Wrong County",
            ),
            [_geography_source(GOOGLE, status)],
            field_status=status,
            status=status,
        )

    readings = [
        Reading("r1", "o-chosen", "decided_transcript", "Wrong City; Guatemala"),
        Reading("r1", "o-raw", "raw_reading", "Right City; Guatemala"),
    ]
    outcome, blobs, fakes = _county_harness(geography, readings=readings, literals={
        "1A": {"city": "Wrong City", "country": "Guatemala"},
        "1B": {"city": "Right City", "country": "Guatemala"},
    })

    assert outcome.blocker is None and len(fakes.calls) == 2
    city = outcome.fields["city"]
    assert city.state == V.SUPPORTED and city.literal == "Wrong City"
    county = outcome.fields["county"]
    assert county.state == V.SUPPORTED and county.parsed == "Right County"
    failed, successful = outcome.tool_calls
    assert (failed.outcome, successful.outcome) == (S.NO_MATCH, S.SUCCESS)
    assert successful.observation_id == "o-raw"
    assert _county_record(outcome, blobs)["call_evidence_ids"] == [successful.evidence_id]
    assert failed.evidence_id not in county.evidence_ids
    assert county.evidence_relations[successful.evidence_id] == "supports"


def test_agreeing_labels_derive_elevations_without_choosing_a_verbatim():
    readings = [
        Reading("r1", "o-first", "decided_transcript", "6400 ft"),
        Reading("r2", "o-second", "decided_transcript", "6400 ft"),
    ]
    blobs = Blobs()
    outcome, _ = harness(
        answer(**{
            "1A": {"elevation_from_ft": "6400 ft"},
            "2A": {"elevation_from_ft": "6400 ft"},
        }),
        readings=readings,
        plan=ELEVATIONS,
        blobs=blobs,
    )

    assert outcome.failure is None and outcome.blocker is None
    stated = outcome.fields["elevation_from_ft"]
    assert (stated.state, stated.layer, stated.literal) == (
        V.SUPPORTED, "settled", None,
    )
    assert stated.normalized == "6400 ft"
    assert stated.verbatim_by_observation == {
        "o-first": "6400 ft", "o-second": "6400 ft",
    }
    assert stated.settled_observation_ids == ["o-first", "o-second"]
    assert stated.source_observation_id is None
    literals = [e for e in outcome.evidence if e.id in stated.evidence_ids]
    assert {tuple(e.observation_ids) for e in literals} == {
        ("o-first",), ("o-second",),
    }
    for key, expected in {
        "elevation_to_ft": "6400",
        "elevation_from_m": "1950.72",
        "elevation_to_m": "1950.72",
    }.items():
        derived = outcome.fields[key]
        assert (derived.state, derived.layer, derived.parsed, derived.literal) == (
            V.SUPPORTED, "derived", expected, None,
        )
        assert derived.derived_from == ["elevation_from_ft"]
        assert all(derived.evidence_relations[e.id] == "supports" for e in literals)
        (rule,) = [e for e in outcome.evidence if e.id in derived.evidence_ids
                   and e.kind == "derivation"]
        assert derived.evidence_relations[rule.id] == "decides"
        raw = blobs.puts[int(rule.raw_ref.removeprefix("blob-")) - 1]
        assert hashlib.sha256(raw).hexdigest() == rule.digest
        record = json.loads(raw)["derivation"]
        assert record["inputs"] == {"elevation_from_ft": "6400 ft"}
        assert record["authority"]["version"] == "derivation-rules-v1"


@pytest.mark.parametrize("literal, feet, metres", [
    ("-10 ft", "-10", "-3.05"),
    ("-10.5 ft", "-10.5", "-3.2"),
    ("-1,234.5 ft", "-1234.5", "-376.28"),
    ("+10 ft", "10", "3.05"),
    ("0 ft", "0", "0"),
    ("1,234.5 ft", "1234.5", "376.28"),
])
def test_signed_elevations_keep_the_literal_and_derived_value(literal, feet, metres):
    blobs = Blobs()
    outcome, _ = harness(
        answer(**{"1A": {"elevation_from_ft": literal}}),
        readings=[Reading("r1", "o-number", "decided_transcript", literal)],
        plan=ELEVATIONS,
        blobs=blobs,
    )

    assert outcome.failure is None and outcome.blocker is None
    assert outcome.fields["elevation_from_ft"].literal == literal
    assert {key: value.parsed for key, value in outcome.fields.items()
            if key != "elevation_from_ft"} == {
        "elevation_to_ft": feet,
        "elevation_from_m": metres,
        "elevation_to_m": metres,
    }
    for key in ("elevation_from_m", "elevation_to_m"):
        derived = outcome.fields[key]
        (rule,) = [e for e in outcome.evidence if e.id in derived.evidence_ids
                   and e.kind == "derivation"]
        record = json.loads(blobs.puts[int(rule.raw_ref.removeprefix("blob-")) - 1])
        assert record["derivation"]["inputs"] == {"elevation_from_ft": literal}


@pytest.mark.parametrize("labels", [1, 2])
@pytest.mark.parametrize("literal, feet, metres", [
    ("−10 ft", "-10", "-3.05"),
    (".5 ft", "0.5", "0.15"),
    ("-.5 ft", "-0.5", "-0.15"),
    ("+.5 ft", "0.5", "0.15"),
    ("−.5 ft", "-0.5", "-0.15"),
    ("−1,234.5 ft.", "-1234.5", "-376.28"),
])
def test_complete_elevation_quantities_keep_sign_magnitude_and_grounding(
    literal, feet, metres, labels
):
    readings = [
        Reading(f"r{index}", f"o-quantity-{index}", "decided_transcript", literal)
        for index in range(1, labels + 1)
    ]
    blobs = Blobs()
    outcome, _ = harness(
        answer(**{
            f"{index}A": {"elevation_from_ft": literal}
            for index in range(1, labels + 1)
        }),
        readings=readings,
        plan=ELEVATIONS,
        blobs=blobs,
    )

    assert outcome.failure is None and outcome.blocker is None
    stated = outcome.fields["elevation_from_ft"]
    assert stated.literal == (literal if labels == 1 else None)
    if labels == 2:
        assert stated.verbatim_by_observation == {
            reading.observation_id: literal for reading in readings
        }
    literals = [e for e in outcome.evidence if e.id in stated.evidence_ids]
    assert {tuple(e.observation_ids) for e in literals} == {
        (reading.observation_id,) for reading in readings
    }
    assert {key: value.parsed for key, value in outcome.fields.items()
            if value.layer == "derived"} == {
        "elevation_to_ft": feet,
        "elevation_from_m": metres,
        "elevation_to_m": metres,
    }
    for value in outcome.fields.values():
        if value.layer != "derived":
            continue
        assert value.derived_from == ["elevation_from_ft"]
        assert all(value.evidence_relations[e.id] == "supports" for e in literals)
        (rule,) = [e for e in outcome.evidence if e.id in value.evidence_ids
                   and e.kind == "derivation"]
        raw = blobs.puts[int(rule.raw_ref.removeprefix("blob-")) - 1]
        assert hashlib.sha256(raw).hexdigest() == rule.digest
        assert json.loads(raw)["derivation"]["inputs"] == {
            "elevation_from_ft": literal,
        }


@pytest.mark.parametrize("labels", [1, 2])
@pytest.mark.parametrize("literal", [
    "±10 ft", "±.5 ft", "+/-10 ft", "~10 ft", "10? ft", ">10 ft",
    "10e3 ft", "10.5.3 ft", "10-20 ft", "10–20 ft", "1,23 ft", "--10 ft",
])
def test_ambiguous_or_partial_elevation_quantities_gain_no_derived_authority(
    literal, labels
):
    readings = [
        Reading(f"r{index}", f"o-quantity-{index}", "decided_transcript", literal)
        for index in range(1, labels + 1)
    ]
    outcome, _ = harness(
        answer(**{
            f"{index}A": {"elevation_from_ft": literal}
            for index in range(1, labels + 1)
        }),
        readings=readings,
        plan=ELEVATIONS,
    )

    assert outcome.failure is None and outcome.blocker is None
    stated = outcome.fields["elevation_from_ft"]
    assert stated.literal == (literal if labels == 1 else None)
    if labels == 2:
        assert stated.verbatim_by_observation == {
            reading.observation_id: literal for reading in readings
        }
    assert all(value.layer != "derived" for value in outcome.fields.values())
    assert not any(e.kind == "derivation" for e in outcome.evidence)


@pytest.mark.parametrize("text, start, end, low, high", [
    ("10-20 ft", "10", "20 ft", "3.05", "6.1"),
    ("10.5-20.25 ft", "10.5", "20.25 ft", "3.2", "6.17"),
    ("+10-+20 ft", "+10", "+20 ft", "3.05", "6.1"),
    ("-20--10 ft", "-20", "-10 ft", "-6.1", "-3.05"),
])
def test_stated_range_endpoints_keep_their_signs(text, start, end, low, high):
    outcome, _ = harness(
        answer(**{"1A": {"elevation_from_ft": start, "elevation_to_ft": end}}),
        readings=[Reading("r1", "o-range", "decided_transcript", text)],
        plan=ELEVATIONS,
    )

    assert outcome.failure is None and outcome.blocker is None
    assert outcome.fields["elevation_from_ft"].literal == start
    assert outcome.fields["elevation_to_ft"].literal == end
    assert outcome.fields["elevation_from_m"].parsed == low
    assert outcome.fields["elevation_to_m"].parsed == high


@pytest.mark.parametrize("broken", ["raises", "answers-nothing"])
def test_a_tool_that_breaks_during_the_run_is_a_harness_failure(broken):
    class Broken(Fakes):
        def verify_taxon(self, literal, place_text=()):
            # It raises, or answers nothing (None).
            if broken == "raises":
                raise ValueError("a bug in the tool")

    check = [("verify_taxon", {"reading": "2A", "literal": "Epipsocus"})]

    outcome, _ = harness(check, FULL, fakes=Broken())

    assert outcome.failure == "harness_tool_failed"
    assert all(value == FieldValue() for value in outcome.fields.values())


def test_a_resolution_that_raises_is_a_harness_failure_that_keeps_nothing():
    # An answer the validator never saw: reading 1A has no "Guatemala", so
    # the resolver refuses it (literal_not_in_source) before any call.
    fakes = Fakes()
    ledger = ToolLedger(fakes.tools(), asset_id="asset-1")
    output = HarnessOutput.model_validate(answer(**{"1A": {"country": "Guatemala"}}))

    outcome = resolve(PLAN, labelled(READINGS), output, ledger, "asset-1", Blobs())

    assert outcome.failure == "harness_resolution_failed"
    assert all(value == FieldValue() for value in outcome.fields.values())
    assert (outcome.evidence, outcome.findings, outcome.blocker) == ([], [], None)
    assert fakes.calls == []


def test_a_provider_failure_while_resolving_stays_an_operational_block():
    class Down(Fakes):
        def verify_taxon(self, literal, place_text=()):
            raise AdapterFailure("gbif_unavailable", S.PROVIDER)

    ledger = ToolLedger(Down().tools(), asset_id="asset-1")
    output = HarnessOutput.model_validate(answer(**{"2A": {"taxon": "Epipsocus"}}))

    with pytest.raises(AdapterFailure):
        resolve(PLAN, labelled(READINGS), output, ledger, "asset-1", Blobs())


def test_the_final_taxonomy_call_sends_no_word_of_its_readings_place_literals(tmp_path):
    # #134's verdict (precondition D): the literal the coordinator's 02:07Z
    # ruling of 2026-09-26 pins, on the real taxonomy tool.
    text = "Davao, Mindanao\nEpipsocus Davao, Mindanao 1946"
    reading = Reading("r1", "o-muse", "decided_transcript", text)
    sent = []

    def endpoint(request):
        sent.append(str(request.url))
        if request.url.path.endswith("/metadata"):
            return httpx.Response(200, json={"alias": "fixture-index"})
        return httpx.Response(200, json={"diagnostics": {"matchType": "NONE"}})

    tools = Tools(
        verify_taxon=partial(
            verify_taxon,
            blobs=LocalBlobs(tmp_path),
            client=httpx.Client(transport=httpx.MockTransport(endpoint)),
            sleep=lambda s: None,
        ),
        geocode=Fakes().geocode,
        parse_date=partial(date_parser, date_rules=DATE_RULES),
        check_catalog_number=catalog_number_validator,
    )
    output = HarnessOutput.model_validate(
        answer(
            **{
                "1A": {
                    "taxon": "Epipsocus Davao, Mindanao 1946",
                    "city": "Davao",
                    "precise_location": "Davao, Mindanao",
                }
            }
        )
    )

    resolve(
        PLAN, labelled([reading]), output, ToolLedger(tools, asset_id="a"), "a", Blobs()
    )

    assert sent
    assert not [
        url for url in sent if "davao" in url.lower() or "mindanao" in url.lower()
    ]
