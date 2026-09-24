"""The harness's tool ledger (HARNESS.md section 10)."""

import hashlib
import json

import pytest

from specimen_digitization.application.domain import Lookup
from specimen_digitization.application.domain import LookupStatus as S
from specimen_digitization.application.field_resolution import Reading
from specimen_digitization.application.harness_ledger import (
    ToolLedger,
    Tools,
    call_key,
)
from specimen_digitization.application.harness_tools import (
    PlaceCandidate,
    SourceCall,
    TaxonCandidate,
    ToolResult,
)
from specimen_digitization.application.taxonomy_tool import Verification

DECIDED = Reading(
    "r1",
    "o-muse",
    "decided_transcript",
    "Chimaltenango, GUAT.\nEpipsocus sp.\n12-VI-1946\nFMNH INS 0123456",
)
RAW = Reading("r1", "o-qwen", "raw_reading", "Chimaltenago, GUAT.\nEpipocous sp.")
GOOGLE = "google-maps-geocoding"


def source_call(source, outcome=S.SUCCESS, attempt=1, **extra):
    return SourceCall(
        source=source,
        query={"name": "Epipsocus"},
        retrieved_at="2026-09-23T00:00:00Z",
        outcome=outcome,
        attempt=attempt,
        **extra,
    )


GBIF_TAXON = TaxonCandidate(
    source="gbif",
    usage_key="8MQRG",
    name="Epipsocus Hagen, 1866",
    rank="GENUS",
    status="ACCEPTED",
)


def taxonomy(outcome=S.SUCCESS, *, warnings=(), gbif_attempts=(S.SUCCESS,)):
    calls = [source_call("gbif", o, attempt=i + 1) for i, o in enumerate(gbif_attempts)]
    calls += [source_call("gnv"), source_call("col")]
    result = ToolResult(
        tool="taxonomy_verifier",
        tool_version="taxonomy-verifier-v1",
        outcome=outcome,
        taxa=[GBIF_TAXON] if outcome == S.SUCCESS else [],
        sub_calls=calls,
        warnings=list(warnings),
    )
    return Verification(
        result,
        Lookup(
            provider="gbif",
            adapter_version="species-match-v2.1",
            query={"scientificName": "Epipsocus"},
            status=outcome,
        ),
    )


def geography(field_outcomes, place_id="ChIJ-chimaltenango"):
    places = [
        PlaceCandidate(field_key=k, source=GOOGLE, source_record_id=place_id)
        for k, v in field_outcomes.items()
        if v == S.SUCCESS
    ]
    return ToolResult(
        tool="geography_lookup",
        tool_version="google-geocoding-v1",
        outcome=S.SUCCESS,
        field_outcomes=field_outcomes,
        places=places,
        sub_calls=[
            SourceCall(
                source=GOOGLE,
                query={"address": "x"},
                retrieved_at="t",
                outcome=S.SUCCESS,
                raw_ref="blob-1",
                response_sha256="f" * 64,
            )
        ],
    )


def validator(tool, outcome, parsed=None, warnings=()):
    return ToolResult(
        tool=tool,
        tool_version=f"{tool}-v1",
        outcome=outcome,
        parsed=parsed,
        warnings=list(warnings),
    )


class Fakes:
    """Each tool answers with a preset result and counts its calls."""

    def __init__(self, taxon=None, place=None, date=None, catalog=None):
        self.answers = {
            "taxon": taxon,
            "place": place,
            "date": date,
            "catalog": catalog,
        }
        self.calls = []

    def tools(self):
        def answer(kind):
            def run(*args, **kwargs):
                self.calls.append((kind, args, kwargs))
                return self.answers[kind]

            return run

        return Tools(
            verify_taxon=answer("taxon"),
            geocode=answer("place"),
            parse_date=answer("date"),
            check_catalog_number=answer("catalog"),
        )


def ledger(fakes):
    ticks = iter(f"2026-09-23T00:00:{n:02d}Z" for n in range(60))
    return ToolLedger(fakes.tools(), asset_id="asset-1", clock=lambda: next(ticks))


def taxon_arguments(literal, reading):
    return {"literal": literal}


def test_the_call_key_is_the_one_agreed_with_s5():
    fields = {
        "phase": "lookup",
        "tool": "taxonomy_verifier",
        "source": "gbif",
        "input_source": "raw_reading",
        "region_id": "r1",
        "observation_id": "o-qwen",
        "attempt": 2,
        "arguments": {"literal": "Epipsocus"},
    }
    digest = hashlib.sha256(
        json.dumps({"literal": "Epipsocus"}, separators=(",", ":")).encode()
    ).hexdigest()[:16]

    assert (
        call_key(fields)
        == f"lookup:taxonomy_verifier:gbif:raw_reading:r1:o-qwen:{digest}:2"
    )
    missing = call_key(
        {**fields, "source": None, "region_id": None, "observation_id": None}
    )
    assert missing == f"lookup:taxonomy_verifier:-:raw_reading:-:-:{digest}:2"


def test_every_source_attempt_is_recorded_and_only_final_calls_carry_evidence():
    fakes = Fakes(taxon=taxonomy(gbif_attempts=(S.RATE_LIMITED, S.SUCCESS)))
    book = ledger(fakes)

    book.run("taxonomy_verifier", DECIDED, {"literal": "Epipsocus"}, ["taxon"])

    assert [(r.source, r.attempt, r.outcome) for r in book.records] == [
        ("gbif", 1, S.RATE_LIMITED),
        ("gbif", 2, S.SUCCESS),
        ("gnv", 1, S.SUCCESS),
        ("col", 1, S.SUCCESS),
    ]
    assert [r.evidence_id is not None for r in book.records] == [
        False,
        True,
        True,
        True,
    ]
    assert len({r.call_key for r in book.records}) == 4
    first = book.records[0]
    assert (first.phase, first.tool, first.input_source, first.region_id) == (
        "lookup",
        "taxonomy_verifier",
        "decided_transcript",
        "r1",
    )
    assert (
        first.observation_id is None
    )  # A call on the decided transcript names no reading.
    assert first.field_keys == ["taxon"] and first.arguments == {"literal": "Epipsocus"}
    assert [e.source for e in book.evidence] == ["gbif", "gnv", "col"]
    assert book.evidence[0].locator == "usage/8MQRG"
    assert [lookup.status for lookup in book.lookups] == [S.SUCCESS]


def test_a_request_runs_once_and_its_records_are_not_repeated():
    fakes = Fakes(taxon=taxonomy())
    book = ledger(fakes)

    first = book.run("taxonomy_verifier", RAW, {"literal": "Epipocous"}, ["taxon"])
    again = book.run("taxonomy_verifier", RAW, {"literal": "Epipocous"}, ["taxon"])

    assert first is again and len(fakes.calls) == 1 and len(book.records) == 3
    assert {r.observation_id for r in book.records} == {"o-qwen"}


def test_a_tool_the_profile_does_not_allow_never_runs():
    with pytest.raises(ValueError, match="tool_not_allowed:bugguide"):
        ledger(Fakes()).run("bugguide", DECIDED, {"literal": "x"}, ["taxon"])


def test_gbif_decides_and_supporting_sources_support_unless_they_disagree():
    warning = "taxonomy_source_disagreement:col"
    book = ledger(Fakes(taxon=taxonomy(warnings=[warning])))

    called = book.field_call("taxon", "taxonomy_verifier", taxon_arguments)(
        "Epipsocus", DECIDED
    )

    gbif, gnv, col = (e.id for e in book.evidence)
    assert (called.outcome, called.authority_id, called.normalized) == (
        S.SUCCESS,
        "8MQRG",
        "Epipsocus Hagen, 1866",
    )
    assert called.evidence == {
        gbif: "decides",
        gnv: "supports",
    }  # COL disagreed: not linked.
    assert called.warnings == {warning: (col,)}


def test_a_failed_lookup_settles_nothing_and_passes_its_outcome_on():
    book = ledger(Fakes(taxon=taxonomy(S.AMBIGUOUS, gbif_attempts=(S.AMBIGUOUS,))))

    called = book.field_call("taxon", "taxonomy_verifier", taxon_arguments)(
        "Epipsocus", DECIDED
    )

    assert (called.outcome, called.authority_id, called.evidence) == (
        S.AMBIGUOUS,
        None,
        {},
    )
    assert book.evidence[0].locator is None  # Nothing to locate (#88, 4.4).


def test_one_geography_call_serves_every_locality_field_of_its_reading():
    outcomes = {"city": S.SUCCESS, "country": S.NO_MATCH}
    fakes = Fakes(place=geography(outcomes))
    book = ledger(fakes)
    literals = [["city", "Chimaltenango"], ["country", "GUAT."]]

    def arguments(literal, reading):
        return {"literals": literals}

    city = book.field_call("city", "geography_lookup", arguments)(
        "Chimaltenango", DECIDED
    )
    country = book.field_call("country", "geography_lookup", arguments)(
        "GUAT.", DECIDED
    )

    assert len(fakes.calls) == 1 and len(book.records) == 1
    (record,) = book.records
    assert record.field_keys == ["city", "country"] and record.source == GOOGLE
    assert record.result == {
        "place_ids": ["ChIJ-chimaltenango"]
    }  # Place IDs only (G26).
    (evidence,) = book.evidence
    assert (evidence.locator, evidence.raw_ref, evidence.excerpt) == (
        "place/ChIJ-chimaltenango",
        "blob-1",
        f"{GOOGLE} success",
    )
    assert (city.outcome, city.authority_id, city.normalized) == (
        S.SUCCESS,
        "ChIJ-chimaltenango",
        "Chimaltenango",
    )
    assert city.evidence == {
        evidence.id: "supports"
    }  # Google never decides (rule 1.6).
    assert (country.outcome, country.authority_id) == (S.NO_MATCH, None)
    query = fakes.calls[0][1][0]
    assert [
        (item.field_key, item.literal, item.source_observation_id)
        for item in query.literals
    ] == [
        ("city", "Chimaltenango", "o-muse"),
        ("country", "GUAT.", "o-muse"),
    ]


def test_validators_are_one_attempt_with_no_source_and_keep_their_verdict():
    reading = {
        "iso": "1946-06-12",
        "precision": "day",
        "century_rule": None,
        "order": "day-romanmonth-year",
        "year": 1946,
        "month": 6,
        "day": 12,
        "rules": [],
    }
    date = validator(
        "date_parser", S.SUCCESS, {"readings": [reading], "year_literal": None}
    )
    catalog = validator(
        "catalog_number_validator", S.SUCCESS, {"catalog_number": "0123456"}
    )
    fakes = Fakes(date=date, catalog=catalog)
    book = ledger(fakes)

    day = book.field_call(
        "date_visited_from",
        "date_parser",
        lambda literal, reading: {"literal": literal},
    )("12-VI-1946", DECIDED)
    number = book.field_call(
        "fmnh_ins_number",
        "catalog_number_validator",
        lambda literal, reading: {"literal": literal},
    )("FMNH INS 0123456", DECIDED)

    assert [(r.phase, r.source, r.attempt) for r in book.records] == [
        ("validate", None, 1),
        ("validate", None, 1),
    ]
    assert book.records[0].result == {
        "parsed": {"readings": [reading], "year_literal": None},
        "warnings": [],
    }
    assert [(e.kind, e.locator) for e in book.evidence] == [
        ("validation", "region:r1"),
        ("validation", "region:r1"),
    ]
    assert (day.parsed, day.precision, day.century_rule) == ("1946-06-12", "day", None)
    assert number.parsed == "0123456"
    assert fakes.calls[0][2] == {"source_text": DECIDED.text, "year_literal": None}


def test_an_operational_outcome_passes_through_for_the_resolver_to_block_on():
    fakes = Fakes(
        place=ToolResult(
            tool="geography_lookup",
            tool_version="v1",
            outcome=S.RATE_LIMITED,
            field_outcomes={"city": S.RATE_LIMITED},
        )
    )
    book = ledger(fakes)

    called = book.field_call(
        "city",
        "geography_lookup",
        lambda literal, reading: {"literals": [["city", literal]]},
    )("Chimaltenango", DECIDED)

    assert called.outcome == S.RATE_LIMITED and called.authority_id is None


def test_the_precise_location_is_never_settled_by_a_geography_result():
    book = ledger(Fakes(place=geography({"city": S.SUCCESS})))
    literals = [["precise_location", "Chimaltenango"], ["city", "Chimaltenango"]]
    call = book.field_call(
        "precise_location",
        "geography_lookup",
        lambda literal, reading: {"literals": literals},
    )

    with pytest.raises(ValueError, match="field_not_reported:precise_location"):
        call("Chimaltenango", DECIDED)


def test_a_near_spelling_settles_the_place_id_alone_with_a_finding():
    near = geography({"province_state": S.SUCCESS, "country": S.SUCCESS})
    near = near.model_copy(update={"warnings": ["near_spelling:province_state"]})
    book = ledger(Fakes(place=near))
    literals = [["province_state", "Chimaltenago"], ["country", "GUAT."]]

    def arguments(literal, reading):
        return {"literals": literals}

    province = book.field_call("province_state", "geography_lookup", arguments)(
        "Chimaltenago", DECIDED
    )
    country = book.field_call("country", "geography_lookup", arguments)(
        "GUAT.", DECIDED
    )

    (evidence,) = book.evidence
    assert (province.authority_id, province.normalized) == ("ChIJ-chimaltenango", None)
    assert province.warnings == {"near_spelling:province_state": (evidence.id,)}
    assert (country.normalized, country.warnings) == ("GUAT.", {})
