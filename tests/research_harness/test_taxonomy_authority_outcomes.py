"""Synthetic GBIF response cases exercise the actual taxonomy source adapter."""
import asyncio
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from specimen_digitization.application.domain import LookupStatus
from specimen_digitization.application.lookup import COL_XR
from specimen_digitization.research_harness.contracts import FieldKey, SourceQuery
from specimen_digitization.research_harness.sources import FixtureSourceTransport, SourceBroker, insects_registry

from test_taxon_input_reconciliation import request_for


def usage(name, rank, *, key="FIXTUREUSAGE", status="ACCEPTED", authorship="Fixture, 1900"):
    return {"key": key, "name": name + " " + authorship, "canonicalName": name,
            "rank": rank, "status": status, "authorship": authorship}


def execute(literal, payload):
    calls = []
    async def read(url, policy):
        calls.append(url)
        return 200, json.dumps(payload).encode()
    registry = insects_registry()
    broker = SourceBroker(registry, transport=FixtureSourceTransport(read))
    policy = registry.get("gbif").model_copy(update={"source_release": "synthetic-col-xr"})
    request = request_for((("raw", literal, "raw_reading"),))
    query = SourceQuery(source_id="gbif", field_key=FieldKey.TAXON, query_text=literal)
    result = asyncio.run(broker._execute(policy, request, query))
    assert len(calls) == 1
    return result, parse_qs(urlsplit(calls[0]).query)


def gbif(found, *, match="EXACT", alternatives=(), accepted=None):
    payload = {"usage": found, "classification": [{"rank": "CLASS", "name": "Insecta"}],
        "diagnostics": {"matchType": match, "alternatives": list(alternatives)}}
    if accepted:
        payload["acceptedUsage"] = accepted
    return payload


@pytest.mark.parametrize("literal", ["Danaus", "Danaus sp.30"])
def test_g25_genus_label_does_not_require_or_invent_a_species(literal):
    result, params = execute(literal, gbif(usage("Danaus", "GENUS")))
    candidate = json.loads(result.candidate_json[0])
    assert result.status == LookupStatus.SUCCESS and params["taxonRank"] == ["GENUS"]
    assert params["scientificName"] == ["Danaus"]
    assert candidate["rank"] == "GENUS" and candidate["input_literal"] == literal
    assert candidate["authority_id"] == f"{COL_XR}:FIXTUREUSAGE"


def test_historical_synonym_retains_written_name_and_returns_accepted_usage():
    written = "Oldgenus specimenus"
    result, params = execute(written, gbif(usage(written, "SPECIES", status="SYNONYM"),
        accepted=usage("Newgenus specimenus", "SPECIES", key="FIXTUREACCEPTED")))
    candidate = json.loads(result.candidate_json[0])
    assert result.status == LookupStatus.SUCCESS and params["scientificName"] == [written]
    assert candidate["input_literal"] == written and candidate["value"] == "Newgenus specimenus Fixture, 1900"
    assert candidate["authority_id"] == f"{COL_XR}:FIXTUREACCEPTED"


def test_genus_match_cannot_clear_a_written_species():
    result, _ = execute("Danaus plexippus", gbif(usage("Danaus", "GENUS"), match="HIGHERRANK"))
    assert result.status == LookupStatus.AMBIGUOUS


def test_exact_homonym_tie_remains_ambiguous_even_with_query_context_support():
    found = usage("Danaus", "GENUS")
    other = {"usage": usage("Danaus", "GENUS", key="FIXTUREOTHER", authorship="Another, 1910"),
        "classification": [{"rank": "CLASS", "name": "Insecta"}], "diagnostics": {"matchType": "EXACT"}}
    result, _ = execute("Danaus", gbif(found, alternatives=(other,)))
    assert result.status == LookupStatus.AMBIGUOUS


def test_negative_response_never_exposes_a_success_candidate():
    result, _ = execute("Danaus", gbif(usage("Unrelated", "GENUS"), match="NONE"))
    assert result.status == LookupStatus.NO_MATCH and result.candidate_json == ()
