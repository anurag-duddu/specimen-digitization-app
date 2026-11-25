"""Getty TGN's records when the SPARQL endpoint refuses the request for them: the
chain reads them through the reconciliation service's data extension, in the one
request that is left within MAX_CALLS, every exchange kept. Offline: the recorded
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


def recorded_ids(reading=READING):
    return [hit["id"].split("/")[1] for hit in fixture("tgn_reconcile.json")["responses"][reading]]


class Refusing:
    """The reconciliation service answers as recorded and the SPARQL endpoint
    answers `sparql` (a status, with a block page) for every request, as it does
    for Google Cloud's addresses."""

    def __init__(self, sparql=403):
        self.sparql = sparql
        self.calls = []

    async def __call__(self, url, params):
        self.calls.append((url, params))
        if url == tgn.RECONCILE:
            results = fixture("tgn_reconcile.json")["responses"][READING]
            return 200, body({"q0": {"result": results}})
        assert url == tgn.SPARQL
        return self.sparql, b"<html><body>Forbidden</body></html>"


class Extension:
    """The data extension answers from the recording for the ids asked."""

    def __init__(self, answer=None):
        self.answer = answer
        self.calls = []

    async def __call__(self, url, params):
        self.calls.append((url, params))
        assert url == tgn.RECONCILE and list(params) == ["extend"]
        if isinstance(self.answer, Exception):
            raise self.answer
        if self.answer is not None:
            return self.answer
        asked = {item.split("/")[1] for item in json.loads(params["extend"])["ids"]}
        rows = {
            key: value
            for key, value in fixture("tgn_extension.json")["response"]["rows"].items()
            if key.split("/")[1] in asked
        }
        return 200, body({"rows": rows})


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [401, 403])
async def test_refused_records_are_read_through_the_data_extension(code):
    fetch, post = Refusing(code), Extension()
    result = await lookup("tgn", READING, fetch, post)
    expected = await lookup("tgn", READING, FixtureFetch("tgn", READING))
    assert result.status is LookupStatus.SUCCESS and result.fallback is None
    assert result.extension == f"refused the request (HTTP {code})"
    assert {place.record_id for place in result.places} == {place.record_id for place in expected.places}
    assert len(result.places) == 10
    # The reconciliation request, the refused SPARQL request and the extension: three,
    # as many as MAX_CALLS lets through, each kept with the digest of its bytes.
    assert len(result.exchanges) == MAX_CALLS == 3
    assert [(exchange.url, exchange.http_status) for exchange in result.exchanges] == [
        (tgn.RECONCILE, 200), (tgn.SPARQL, code), (tgn.RECONCILE, 200)]
    for exchange in result.exchanges:
        assert exchange.response_digest == hashlib.sha256(exchange.response_body).hexdigest()
    form = dict(result.exchanges[2].params)
    assert list(form) == ["extend"] and form == post.calls[0][1]
    # The form names the ten places the reconciliation found, and nothing of the reading.
    assert json.loads(form["extend"])["ids"] == [f"tgn/{record}" for record in recorded_ids()]
    assert "mckinley" not in form["extend"].lower()
    assert [call[0] for call in fetch.calls] == [tgn.RECONCILE, tgn.SPARQL] and len(post.calls) == 1


@pytest.mark.asyncio
async def test_without_a_post_a_refused_records_request_stays_refused():
    # As before: a caller that gives no post (the research harness's broker) gets the refusal.
    for code, status in ((403, LookupStatus.AUTHORIZATION), (401, LookupStatus.AUTHENTICATION)):
        result = await lookup("tgn", READING, Refusing(code))
        assert result.status is status and result.places == () and result.extension is None
        assert [(exchange.url, exchange.http_status) for exchange in result.exchanges] == [
            (tgn.RECONCILE, 200), (tgn.SPARQL, code)]


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [404, 500, 503])
async def test_only_a_refusal_sends_the_records_to_the_extension(code):
    # Any other SPARQL failure is no sign that the extension would answer: it ends as it did.
    post = Extension()
    result = await lookup("tgn", READING, Refusing(code), post)
    assert result.status is LookupStatus.PROVIDER and post.calls == []


@pytest.mark.asyncio
async def test_a_working_sparql_endpoint_never_reaches_the_extension():
    post = Extension()
    result = await lookup("tgn", READING, FixtureFetch("tgn", READING), post)
    assert result.status is LookupStatus.SUCCESS and result.extension is None
    assert post.calls == [] and len(result.exchanges) == 3


@pytest.mark.asyncio
async def test_an_extension_that_gets_no_answer_leaves_the_refusal():
    result = await lookup("tgn", READING, Refusing(403), Extension(SearchUnanswered("did not answer after 3 attempts")))
    assert result.status is LookupStatus.AUTHORIZATION and result.places == ()
    assert result.extension is None and len(result.exchanges) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("answer", "status"),
    [
        ((403, b"<html>Forbidden</html>"), LookupStatus.AUTHORIZATION),
        ((401, b""), LookupStatus.AUTHENTICATION),
        ((429, b""), LookupStatus.RATE_LIMITED),
        ((200, b""), LookupStatus.MALFORMED),
        ((200, b"<html>"), LookupStatus.MALFORMED),
        ((200, body({"rows": {}})), LookupStatus.MALFORMED),
    ],
)
async def test_an_extension_answer_with_no_place_is_never_no_match(answer, status):
    # The search found places and the SPARQL endpoint was refused: a reply that holds none
    # is an outage, never a ruling-out of the reading.
    result = await lookup("tgn", READING, Refusing(403), Extension(answer))
    assert result.status is status and result.places == ()
    assert result.status is not LookupStatus.NO_MATCH and result.extension is None
    assert len(result.exchanges) == 3


@pytest.mark.asyncio
async def test_an_extension_that_returns_a_place_not_asked_is_malformed():
    rows = fixture("tgn_extension.json")["response"]["rows"]
    extra = {"tgn/9999999": rows["tgn/1105587"]}
    result = await lookup("tgn", READING, Refusing(403), Extension((200, body({"rows": extra}))))
    assert result.status is LookupStatus.MALFORMED and result.places == ()
    assert result.reason == "records exceeded requested TGN ids"


@pytest.mark.asyncio
async def test_an_extension_that_leaves_out_a_place_is_ambiguous_and_keeps_the_rest():
    rows = fixture("tgn_extension.json")["response"]["rows"]
    asked = recorded_ids()
    kept = {f"tgn/{record}": rows[f"tgn/{record}"] for record in asked[:-1]}
    result = await lookup("tgn", READING, Refusing(403), Extension((200, body({"rows": kept}))))
    assert result.status is LookupStatus.AMBIGUOUS and result.places == ()
    assert result.reason == "requested TGN records were incomplete"


@pytest.mark.asyncio
async def test_a_refused_search_that_also_has_its_records_refused_is_not_read_through_the_extension():
    # The reconciliation request itself is refused: the search goes through SPARQL, which
    # refuses it, and no ids were ever found to ask the extension for.
    class Both(Refusing):
        async def __call__(self, url, params):
            self.calls.append((url, params))
            return 403, b"<html>Forbidden</html>"

    post = Extension()
    result = await lookup("tgn", READING, Both(), post)
    assert result.status is LookupStatus.AUTHORIZATION and post.calls == []
    assert result.fallback == "refused the request (HTTP 403)"


@pytest.mark.asyncio
async def test_the_other_sources_take_no_post():
    for source, reading in (("wikidata", "Davao Province"), ("nga", "Yepocapa")):
        post = Extension()
        result = await lookup(source, reading, FixtureFetch(source, reading), post)
        assert result.status is LookupStatus.SUCCESS and post.calls == []
