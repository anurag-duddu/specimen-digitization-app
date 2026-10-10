"""Offline custody and call limits for the historical gazetteer orchestrator."""

import hashlib
import json
import re
from pathlib import Path

import pytest

from specimen_digitization.application.domain import LookupStatus
from specimen_digitization.application import georef_nga as nga
from specimen_digitization.application import georef_tgn as tgn
from specimen_digitization.application import georef_wikidata as wikidata
from specimen_digitization.research_harness.compatibility import PublicationUnavailable
from specimen_digitization.research_harness.historical_gazetteers import (
    MAX_BODY_BYTES,
    lookup,
)
from specimen_digitization.research_harness.persistence import HeldUnknown, StaleWork

FIXTURES = Path(__file__).parent / "fixtures" / "georeferencing"


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def body(data):
    return json.dumps(data).encode()


class FixtureFetch:
    """Return only rows for identifiers the preceding answer supplied."""

    def __init__(self, source, reading):
        self.source = source
        self.reading = reading
        self.calls = []

    async def __call__(self, url, params):
        self.calls.append((url, params))
        if self.source == "tgn":
            if len(self.calls) == 1:
                assert url == tgn.RECONCILE
                assert json.loads(params["queries"])["q0"]["query"] == self.reading
                results = fixture("tgn_reconcile.json")["responses"][self.reading]
                return 200, body({"q0": {"result": results}})
            assert url == tgn.SPARQL
            ids = set(re.findall(r"tgn:([0-9]+)", params["query"]))
            if len(self.calls) == 2:
                source = fixture("tgn_records.json")
            else:
                source = fixture("tgn_names.json")
            rows = [
                row
                for row in source["bindings"]
                if row.get("place", {}).get("value", "").rsplit("/", 1)[-1] in ids
            ]
            return 200, body({"results": {"bindings": rows}})
        if self.source == "wikidata":
            assert url == wikidata.API
            if len(self.calls) == 1:
                assert params["search"] == self.reading
                return 200, body(fixture("wikidata_search.json")["responses"][self.reading])
            ids = set(params["ids"].split("|"))
            source = fixture(
                "wikidata_entities.json" if len(self.calls) == 2 else "wikidata_labels.json"
            )
            # Q928's recorded label is in the entity snapshot; the reduced
            # labels snapshot omitted it because its original batch read Q928.
            recorded = source["entities"]
            if len(self.calls) == 3:
                recorded = fixture("wikidata_entities.json")["entities"] | recorded
            entities = {item: value for item, value in recorded.items() if item in ids}
            return 200, body({"entities": entities})
        if len(self.calls) == 1:
            assert url == nga.NAMES and self.reading in params["where"]
            rows = fixture("nga_search.json")["responses"][self.reading]
        elif len(self.calls) == 2:
            assert url == nga.NAMES
            ids = set(re.findall(r"-?[0-9]+", params["where"]))
            rows = [
                row
                for row in fixture("nga_features.json")["features"]
                if str(row["ufi"]) in ids
            ]
        else:
            assert url == nga.UNITS
            codes = set(re.findall(r"'([A-Z]{2}-[A-Z0-9]+)'", params["where"]))
            rows = [row for row in fixture("nga_units.json")["features"] if row["adm1"] in codes]
        return 200, body({"features": [{"attributes": row} for row in rows]})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source", "reading", "record_id"),
    [
        ("tgn", "Mount McKinley", "1105587"),
        ("wikidata", "Davao Province", "Q15095071"),
        ("nga", "Yepocapa", "-1143757"),
    ],
)
async def test_three_call_chains_keep_only_same_source_ids(source, reading, record_id):
    fetch = FixtureFetch(source, reading)
    result = await lookup(source, reading, fetch)
    assert result.status is LookupStatus.SUCCESS
    assert record_id in {place.record_id for place in result.places}
    assert len(result.exchanges) == len(fetch.calls) == 3
    for exchange, (url, params) in zip(result.exchanges, fetch.calls, strict=True):
        assert exchange.url == url
        assert dict(exchange.params) == params
        assert exchange.http_status == 200
        assert exchange.response_digest == hashlib.sha256(exchange.response_body).hexdigest()
        assert exchange.failure is None


@pytest.mark.asyncio
async def test_reduced_fixture_cannot_claim_a_complete_result():
    fetch = FixtureFetch("tgn", "Mount Apo")
    result = await lookup("tgn", "Mount Apo", fetch)
    assert result.status is LookupStatus.AMBIGUOUS
    assert result.reason == "requested TGN records were incomplete"
    assert result.places == ()
    assert len(result.exchanges) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source", "empty"),
    [
        ("tgn", {"q0": {"result": []}}),
        ("wikidata", {"search": []}),
        ("nga", {"features": []}),
    ],
)
async def test_empty_search_stops_after_one_call(source, empty):
    calls = []

    async def fetch(url, params):
        calls.append((url, params))
        return 200, body(empty)

    result = await lookup(source, "Mount Apo", fetch)
    assert result.status is LookupStatus.NO_MATCH
    assert result.places == ()
    assert len(result.exchanges) == len(calls) == 1


@pytest.mark.asyncio
async def test_provider_failure_on_second_call_stops_chain():
    first = fixture("wikidata_search.json")["responses"]["Davao Province"]
    calls = []

    async def fetch(url, params):
        calls.append((url, params))
        return (200, body(first)) if len(calls) == 1 else (429, b"")

    result = await lookup("wikidata", "Davao Province", fetch)
    assert result.status is LookupStatus.RATE_LIMITED
    assert result.places == ()
    assert len(result.exchanges) == len(calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source", "search"),
    [
        (
            "tgn",
            {"q0": {"result": [{"id": f"tgn/{index}", "name": "Apo"} for index in range(11)]}},
        ),
        ("wikidata", {"search": [{"id": f"Q{index}"} for index in range(1, 9)]}),
        (
            "nga",
            {
                "features": [
                    {"attributes": {"ufi": index, "term_dt_f": None}}
                    for index in range(1, 52)
                ]
            },
        ),
    ],
)
async def test_search_over_cap_stops_without_followup(source, search):
    calls = []

    async def fetch(url, params):
        calls.append((url, params))
        return 200, body(search)

    result = await lookup(source, "Mount Apo", fetch)
    assert result.status is LookupStatus.AMBIGUOUS
    assert result.places == ()
    assert len(result.exchanges) == len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["tgn", "wikidata", "nga"])
async def test_unrequested_record_id_is_rejected_before_third_call(source):
    calls = []

    async def fetch(url, params):
        calls.append((url, params))
        if len(calls) == 1:
            if source == "tgn":
                return 200, body({"q0": {"result": [{"id": "tgn/1", "name": "One"}]}})
            if source == "wikidata":
                return 200, body({"search": [{"id": "Q1"}]})
            return 200, body({"features": [{"attributes": {"ufi": 1, "term_dt_f": None}}]})
        if source == "tgn":
            return 200, body({"results": {"bindings": [
                {"place": {"value": tgn.TGN + "2"}, "name": {"value": "Wrong"}}
            ]}})
        if source == "wikidata":
            return 200, body({"entities": {"Q2": {
                "id": "Q2", "labels": {"en": {"value": "Wrong"}}
            }}})
        return 200, body({"features": [{"attributes": {
            "ufi": 2, "full_name": "Wrong", "term_dt_f": None
        }}]})

    result = await lookup(source, "Mount Apo", fetch)
    assert result.status is LookupStatus.MALFORMED
    assert result.places == ()
    assert len(result.exchanges) == len(calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["tgn", "wikidata", "nga"])
async def test_unrequested_auxiliary_id_is_rejected_after_third_call(source):
    calls = []

    async def fetch(url, params):
        calls.append((url, params))
        stage = len(calls)
        if source == "tgn":
            if stage == 1:
                return 200, body({"q0": {"result": [{"id": "tgn/1", "name": "One"}]}})
            row = {"place": {"value": tgn.TGN + ("1" if stage == 2 else "2")}}
            row["name"] = {"value": "One" if stage == 2 else "Wrong"}
            return 200, body({"results": {"bindings": [row]}})
        if source == "wikidata":
            if stage == 1:
                return 200, body({"search": [{"id": "Q1"}]})
            if stage == 2:
                return 200, body({"entities": {"Q1": {
                    "id": "Q1",
                    "labels": {"en": {"value": "One"}},
                    "claims": {"P31": [{
                        "rank": "normal",
                        "mainsnak": {"datavalue": {"value": {"entity-type": "item", "id": "Q2"}}},
                    }]},
                }}})
            return 200, body({"entities": {"Q3": {
                "id": "Q3", "labels": {"en": {"value": "Wrong"}}
            }}})
        if stage == 1:
            return 200, body({"features": [{"attributes": {"ufi": 1, "term_dt_f": None}}]})
        if stage == 2:
            return 200, body({"features": [{"attributes": {
                "ufi": 1,
                "full_name": "One",
                "term_dt_f": None,
                "adm1": "PH-DVC",
            }}]})
        return 200, body({"features": [{"attributes": {
            "adm1": "GT-04", "adm1_name": "Wrong"
        }}]})

    result = await lookup(source, "Mount Apo", fetch)
    assert result.status is LookupStatus.MALFORMED
    assert result.places == ()
    assert len(result.exchanges) == len(calls) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["wikidata", "nga"])
async def test_no_references_skips_auxiliary_call(source):
    calls = []

    async def fetch(url, params):
        calls.append((url, params))
        if source == "wikidata":
            if len(calls) == 1:
                return 200, body({"search": [{"id": "Q1"}]})
            return 200, body({"entities": {"Q1": {
                "id": "Q1", "labels": {"en": {"value": "One"}}
            }}})
        if len(calls) == 1:
            return 200, body({"features": [{"attributes": {"ufi": 1, "term_dt_f": None}}]})
        return 200, body({"features": [{"attributes": {
            "ufi": 1, "full_name": "One", "term_dt_f": None
        }}]})

    result = await lookup(source, "Mount Apo", fetch)
    assert result.status is LookupStatus.SUCCESS
    assert len(result.places) == 1
    assert len(result.exchanges) == len(calls) == 2


@pytest.mark.asyncio
async def test_invalid_filtered_name_blocks_fetch_but_timeout_reaches_broker():
    calls = []

    async def fetch(url, params):
        calls.append((url, params))
        raise TimeoutError

    blocked = await lookup("nga", "3 Sept.\n1946", fetch)
    assert blocked.status is LookupStatus.POLICY and blocked.exchanges == ()
    with pytest.raises(TimeoutError):
        await lookup("nga", "Mount Apo", fetch)
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source", "reading"),
    [
        ("tgn", "Mount McKinley"),
        ("wikidata", "Davao Province"),
        ("nga", "Yepocapa"),
    ],
)
@pytest.mark.parametrize("failed_stage", [1, 2])
@pytest.mark.parametrize(
    "error_type",
    [
        HeldUnknown,
        StaleWork,
        PermissionError,
        PublicationUnavailable,
        TimeoutError,
        ValueError,
        TypeError,
        KeyError,
    ],
)
async def test_durable_fetch_failure_propagates_unchanged(
    source, reading, failed_stage, error_type
):
    fixture_fetch = FixtureFetch(source, reading)
    calls = []
    failure = error_type("durable capture or receipt uncertain")

    async def fetch(url, params):
        calls.append((url, params))
        if len(calls) == failed_stage:
            raise failure
        return await fixture_fetch(url, params)

    with pytest.raises(error_type) as raised:
        await lookup(source, reading, fetch)
    assert raised.value is failure
    assert len(calls) == failed_stage
    assert len(fixture_fetch.calls) == failed_stage - 1


@pytest.mark.asyncio
async def test_large_body_keeps_digest_and_stops():
    async def fetch(url, params):
        return 200, b"x" * (MAX_BODY_BYTES + 1)

    result = await lookup("tgn", "Mount Apo", fetch)
    assert result.status is LookupStatus.MALFORMED and result.places == ()
    (exchange,) = result.exchanges
    assert exchange.response_body is None and exchange.failure == "body_too_large"
    assert exchange.response_digest == hashlib.sha256(b"x" * (MAX_BODY_BYTES + 1)).hexdigest()
