"""Getty TGN's search when its reconciliation service refuses a request or gets
no answer: the chain searches the SPARQL endpoint instead and returns the same
places, within the same three exchanges, every one kept. Offline: the recorded
TGN answers in tests/fixtures/georeferencing."""

import hashlib
import json
import re

import pytest

from specimen_digitization.application import georef_tgn as tgn
from specimen_digitization.application.domain import LookupStatus
from specimen_digitization.research_harness.historical_gazetteers import (
    MAX_CALLS,
    SearchUnanswered,
    lookup,
)

from test_historical_gazetteers import FixtureFetch, body, fixture

READING = "Mount McKinley"


def recorded_ids(reading):
    return [hit["id"].split("/")[1] for hit in fixture("tgn_reconcile.json")["responses"][reading]]


def search_rows(ids):
    """The search's answer: every recorded term of each id, in the order given,
    as the search query returns them."""
    rows = fixture("tgn_names.json")["bindings"]
    return [row for record in ids for row in rows if row["place"]["value"] == tgn.TGN + record]


class Refused:
    """Reconciliation answers `refusal` (an HTTP status, or an exception the
    caller's fetch raises); the SPARQL endpoint answers from the recordings."""

    def __init__(self, refusal, search_ids=None, sparql_status=200):
        self.refusal = refusal
        self.search_ids = search_ids
        self.sparql_status = sparql_status
        self.calls = []

    async def __call__(self, url, params):
        self.calls.append((url, params))
        if url == tgn.RECONCILE:
            if isinstance(self.refusal, Exception):
                raise self.refusal
            return self.refusal, b"<html><body>Forbidden</body></html>"
        assert url == tgn.SPARQL
        if self.sparql_status != 200:
            return self.sparql_status, b"<html><body>Forbidden</body></html>"
        query = params["query"]
        if "luc:term" in query:
            ids = self.search_ids or list(reversed(recorded_ids(READING)))
            return 200, body({"results": {"bindings": search_rows(ids)}})
        ids = set(re.findall(r"tgn:([0-9]+)", query))
        rows = [
            row
            for row in fixture("tgn_records.json")["bindings"]
            if row["place"]["value"].rsplit("/", 1)[-1] in ids
        ]
        return 200, body({"results": {"bindings": rows}})


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [401, 403])
async def test_a_refused_reconciliation_finds_the_same_places_through_sparql(code):
    expected = await lookup("tgn", READING, FixtureFetch("tgn", READING))
    fetch = Refused(code)
    result = await lookup("tgn", READING, fetch)
    assert result.status is LookupStatus.SUCCESS
    assert result.fallback == f"refused the request (HTTP {code})"
    assert set(result.places) == set(expected.places) and len(result.places) == 10
    # The refused request and the two SPARQL requests are all kept, within the cap.
    assert len(result.exchanges) == len(fetch.calls) == MAX_CALLS == 3
    refused, search, records = result.exchanges
    assert (refused.url, refused.http_status) == (tgn.RECONCILE, code)
    assert json.loads(dict(refused.params)["queries"])["q0"]["query"] == READING
    assert 'luc:term "mount mckinley"' in dict(search.params)["query"]
    assert "?ancestor" in dict(records.params)["query"]
    for exchange in result.exchanges:
        assert exchange.response_digest == hashlib.sha256(exchange.response_body).hexdigest()
        assert exchange.failure is None
    assert [exchange.http_status for exchange in (search, records)] == [200, 200]


@pytest.mark.asyncio
async def test_a_reconciliation_that_got_no_answer_searches_sparql_too():
    fetch = Refused(SearchUnanswered("did not answer after 3 attempts"))
    result = await lookup("tgn", READING, fetch)
    assert result.status is LookupStatus.SUCCESS and len(result.places) == 10
    assert result.fallback == "did not answer after 3 attempts"
    # Nothing came back from the reconciliation request, so nothing of it is kept.
    assert [exchange.url for exchange in result.exchanges] == [tgn.SPARQL, tgn.SPARQL]
    assert len(fetch.calls) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(("code", "status"), [(403, LookupStatus.AUTHORIZATION), (401, LookupStatus.AUTHENTICATION)])
async def test_when_the_sparql_endpoint_refuses_too_the_answer_stays_refused(code, status):
    fetch = Refused(403, sparql_status=code)
    result = await lookup("tgn", READING, fetch)
    assert result.status is status and result.places == ()
    assert result.fallback == "refused the request (HTTP 403)"
    assert [(exchange.url, exchange.http_status) for exchange in result.exchanges] == [
        (tgn.RECONCILE, 403), (tgn.SPARQL, code)]


@pytest.mark.asyncio
async def test_the_places_named_as_asked_are_the_ten_read():
    # Twelve places in the search's order, the ones named "McKinley, Mount" last.
    others = ["1103742", "1101719", "7668798", "1084177", "1001216", "1001218", "1001217"]
    mountains = ["2502238", "2502236", "2502235", "2502237", "1105587"]
    fetch = Refused(403, search_ids=others + mountains)
    result = await lookup("tgn", READING, fetch)
    asked = set(re.findall(r"tgn:([0-9]+)", fetch.calls[2][1]["query"]))
    assert len(asked) == tgn.LIMIT and set(mountains) <= asked
    assert asked == set(mountains + others[:5])
    assert {place.record_id for place in result.places} == asked


@pytest.mark.asyncio
async def test_an_empty_search_is_no_match_after_two_exchanges():
    async def fetch(url, params):
        if url == tgn.RECONCILE:
            return 403, b""
        return 200, body({"results": {"bindings": []}})

    result = await lookup("tgn", "Yepocapa", fetch)
    assert result.status is LookupStatus.NO_MATCH and result.places == ()
    assert len(result.exchanges) == 2 and result.fallback == "refused the request (HTTP 403)"


@pytest.mark.asyncio
async def test_an_unreadable_search_row_is_malformed_and_reads_no_records():
    async def fetch(url, params):
        if url == tgn.RECONCILE:
            return 403, b""
        rows = [{"place": {"value": "http://vocab.getty.edu/aat/300008347"},
                 "name": {"value": "Mount"}, "preferred": {"value": "true"}}]
        return 200, body({"results": {"bindings": rows}})

    result = await lookup("tgn", READING, fetch)
    assert result.status is LookupStatus.MALFORMED and result.places == ()
    assert len(result.exchanges) == 2


@pytest.mark.asyncio
async def test_records_beyond_the_searched_ids_are_malformed():
    class Extra(Refused):
        async def __call__(self, url, params):
            status, data = await super().__call__(url, params)
            if url == tgn.SPARQL and "?ancestor" in params["query"]:
                rows = json.loads(data)["results"]["bindings"]
                rows.append({"place": {"value": tgn.TGN + "1000135"}, "name": {"value": "Pilipinas"}})
                data = body({"results": {"bindings": rows}})
            return status, data

    result = await lookup("tgn", READING, Extra(403))
    assert result.status is LookupStatus.MALFORMED
    assert result.reason == "records exceeded requested TGN ids"


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [404, 429, 500, 302])
async def test_other_reconciliation_answers_end_the_chain_as_before(code):
    calls = []

    async def fetch(url, params):
        calls.append(url)
        return code, b""

    result = await lookup("tgn", READING, fetch)
    assert result.fallback is None and calls == [tgn.RECONCILE]
    assert result.status is tgn.STATUSES.get(code, LookupStatus.PROVIDER)


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [TimeoutError, PermissionError, ValueError])
async def test_any_other_fetch_exception_still_reaches_the_broker(error):
    failure = error("durable capture or receipt uncertain")
    fetch = Refused(failure)
    with pytest.raises(error) as raised:
        await lookup("tgn", READING, fetch)
    assert raised.value is failure and len(fetch.calls) == 1


@pytest.mark.asyncio
async def test_search_unanswered_on_a_sparql_request_reaches_the_broker():
    failure = SearchUnanswered("did not answer after 3 attempts")

    async def fetch(url, params):
        if url == tgn.RECONCILE:
            return 403, b""
        raise failure

    with pytest.raises(SearchUnanswered) as raised:
        await lookup("tgn", READING, fetch)
    assert raised.value is failure
