"""Getty TGN's records through the reconciliation service's data extension when
the SPARQL endpoint refuses them, as it does Google Cloud's addresses (Cloud
Logging, 2026-11-16 to 2026-11-23: 142 unanswered Getty requests, all to
vocab.getty.edu, none to services.getty.edu). Offline: recorded TGN answers."""

import hashlib
import json
import logging
from urllib.parse import parse_qs

import httpx
import pytest

from specimen_digitization.application import georef_tgn as tgn
from specimen_digitization.application.domain import LookupStatus
from specimen_digitization.field_research.contracts import PlaceRef

from test_sources import make, recorded, stored, unanswered

READING = "Chimaltenango"


def getty(sparql=None, extension=None, hits=1):
    """Getty as Cloud Run meets it: the reconciliation search answers as recorded
    (its first `hits`), the SPARQL endpoint answers `sparql` (a refusal by
    default), the data extension answers `extension` (as recorded by default;
    a response, or an exception raised as the transport's)."""
    sparql = httpx.Response(403, text="<html>Forbidden</html>") if sparql is None else sparql

    def reply(request):
        url = f"https://{request.url.host}{request.url.path}"
        if url == tgn.SPARQL:
            return sparql
        assert url == tgn.RECONCILE
        if request.method == "GET":
            query = json.loads(request.url.params["queries"])["q0"]["query"]
            found = recorded("tgn_reconcile.json")["responses"][query][:hits]
            return {"q0": {"result": found}}
        assert request.method == "POST"
        if isinstance(extension, Exception):
            raise extension
        if extension is not None:
            return extension
        asked = {item.split("/")[1] for item in json.loads(parse_qs(request.content.decode())["extend"][0])["ids"]}
        rows = {
            key: value
            for key, value in recorded("tgn_extension.json")["response"]["rows"].items()
            if key.split("/")[1] in asked
        }
        return {"rows": rows}

    return reply


@pytest.mark.asyncio
async def test_refused_records_are_read_through_the_extension_and_settle_one_place(tmp_path):
    tools, server, _, blobs = make(tmp_path, getty())
    answer = await tools.lookup("tgn", READING, field_key="city")
    assert answer.status is LookupStatus.SUCCESS
    [candidate] = answer.candidates
    assert (candidate.name, candidate.authority_id) == ("Chimaltenango", "tgn:1016636")
    # Names, never ids, for its kinds and ancestors: the level types first, the ancestors
    # as Getty writes them, the nation with no record of its own.
    assert candidate.kind.split(", ")[:2] == ["inhabited places", "cities"]
    # As the SPARQL read leaves it: the places below the nation, nearest first, and the nation
    # last (derive reads the last parent as the country); no continent, no root.
    assert candidate.parents == (PlaceRef("Chimaltenango", None, None), PlaceRef("Guatemala", None, None))
    assert answer.note == (
        "Getty TGN's SPARQL endpoint refused the request (HTTP 403); the places' details were "
        "read from its reconciliation service instead, which names their place types and "
        "ancestors but gives no ids for them. Getty TGN has one place for 'Chimaltenango': Chimaltenango"
    )
    assert [(request.method, request.url.host) for _, request in server.requests] == [
        ("GET", "services.getty.edu"), ("GET", "vocab.getty.edu"), ("POST", "services.getty.edu")]
    # The POST is the form the adapter writes: TGN ids and property names, nothing of the reading.
    post = server.requests[2][1]
    assert post.headers["content-type"] == "application/x-www-form-urlencoded"
    assert parse_qs(post.content.decode()) == {"extend": [tgn.extend_params(["1016636"])["extend"]]}
    assert READING.lower() not in post.content.decode().lower()
    # One record keeps every response that came back: the search, the refusal, the extension
    # (with the form it answered), each stored response by its digest.
    record = json.loads(stored(blobs, answer.evidence))
    exchanges = record["exchanges"]
    assert [(item["url"].split("?")[0], item["http_status"]) for item in exchanges] == [
        (tgn.RECONCILE, 200), (tgn.SPARQL, 403), (tgn.RECONCILE, 200)]
    assert [("form" in item) for item in exchanges] == [False, False, True]
    assert exchanges[2]["form"] == tgn.extend_params(["1016636"])
    for item in (exchanges[0], exchanges[2]):
        assert hashlib.sha256(blobs.get(item["raw_ref"])).hexdigest() == item["sha256"]


@pytest.mark.asyncio
async def test_the_refused_sparql_request_is_logged_and_the_extension_is_not(tmp_path, caplog):
    tools, _, _, _ = make(tmp_path, getty())
    with caplog.at_level(logging.WARNING, logger="specimen_digitization.field_research.sources"):
        await tools.lookup("tgn", READING, field_key="city")
    [line] = unanswered(caplog)
    assert (line["source"], line["host"], line["http_status"], line["attempt"]) == (
        "tgn", "vocab.getty.edu", "403", "1")
    assert READING.lower() not in caplog.text.lower()


@pytest.mark.asyncio
async def test_several_places_stay_ambiguous_as_the_reconciliation_search_reads_them(tmp_path):
    tools, _, _, _ = make(tmp_path, getty(hits=3))
    answer = await tools.lookup("tgn", "Mount McKinley", field_key="precise_location")
    assert answer.status is LookupStatus.AMBIGUOUS and len(answer.candidates) == 3
    assert answer.note.startswith("Getty TGN's SPARQL endpoint refused the request (HTTP 403); ")


@pytest.mark.asyncio
async def test_a_nation_read_through_the_extension_settles_the_country_level(tmp_path):
    tools, _, _, _ = make(tmp_path, getty())
    answer = await tools.lookup("tgn", "Philippines", field_key="country")
    [candidate] = answer.candidates
    assert answer.status is LookupStatus.SUCCESS
    assert candidate.authority_id == "tgn:1000135" and candidate.kind.split(", ")[0] == "nations"
    # Its own country, as SPARQL reads a nation, named as the reconciliation service names it
    # ("Philippines"), not by Getty's preferred term in the place's own language ("Pilipinas").
    assert candidate.name == "Philippines"
    assert candidate.parents == (PlaceRef("Philippines", "tgn:1000135", None),)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("extension", "attempts", "line"),
    [
        (httpx.Response(403, text="<html>Forbidden</html>"), 1, {"http_status": "403", "error": "-"}),
        (httpx.ReadTimeout("slow"), 3, {"http_status": "-", "error": "ReadTimeout"}),
        (httpx.Response(502), 3, {"http_status": "502", "error": "-"}),
    ],
)
async def test_when_the_extension_fails_too_the_lookup_stays_the_refusal(
    tmp_path, caplog, extension, attempts, line
):
    from specimen_digitization.field_research.experts import SOURCE_OUTAGES

    tools, server, _, _ = make(tmp_path, getty(extension=extension))
    with caplog.at_level(logging.WARNING, logger="specimen_digitization.field_research.sources"):
        answer = await tools.lookup("tgn", READING, field_key="city")
    assert answer.status is LookupStatus.AUTHORIZATION and answer.status in SOURCE_OUTAGES
    assert answer.evidence is None and answer.candidates == ()
    assert answer.note == "Getty TGN refused the request with HTTP 403"
    assert [request.method for _, request in server.requests].count("POST") == attempts
    hosts = [(item["host"], item["http_status"], item["error"]) for item in unanswered(caplog)]
    assert hosts == [("vocab.getty.edu", "403", "-"), ("services.getty.edu", line["http_status"], line["error"])]


@pytest.mark.asyncio
async def test_an_extension_answer_with_a_place_not_asked_is_not_an_answer(tmp_path):
    rows = recorded("tgn_extension.json")["response"]["rows"]
    tools, _, _, _ = make(tmp_path, getty(extension={"rows": {"tgn/9999999": rows["tgn/1016636"]}}))
    answer = await tools.lookup("tgn", READING, field_key="city")
    assert answer.status is LookupStatus.MALFORMED and answer.candidates == ()
    assert answer.note == "Getty TGN's answer could not be read: records exceeded requested TGN ids"


@pytest.mark.asyncio
async def test_a_working_sparql_endpoint_is_read_as_before(tmp_path):
    def reply(request):
        if request.method == "POST":
            raise AssertionError("the extension is only for a refused SPARQL request")
        return getty(hits=1, sparql=None)(request) if request.url.host == "services.getty.edu" else (
            _recorded_sparql(request))

    tools, server, _, blobs = make(tmp_path, reply)
    answer = await tools.lookup("tgn", READING, field_key="city")
    assert answer.status is LookupStatus.SUCCESS
    assert answer.note == "Getty TGN has one place for 'Chimaltenango': Chimaltenango"
    assert [item.get("form") for item in json.loads(stored(blobs, answer.evidence))["exchanges"]] == [None] * 3


def _recorded_sparql(request):
    import re

    query = dict(request.url.params)["query"]
    ids = set(re.findall(r"tgn:([0-9]+)", query))
    source = "tgn_records.json" if "?ancestor" in query else "tgn_names.json"
    return {
        "results": {
            "bindings": [
                row
                for row in recorded(source)["bindings"]
                if row.get("place", {}).get("value", "").rsplit("/", 1)[-1] in ids
            ]
        }
    }


@pytest.mark.asyncio
async def test_the_identity_checks_abstain_on_a_place_read_through_the_extension(tmp_path):
    """Its ancestors have no ids, so ontology_checks.fits (a place's record inside the settled
    place above it, by an identity both carry) abstains, as it does for NGA's places; the name
    check a settled place must pass (agreement.lies_in) is unchanged."""
    from specimen_digitization.field_research.agreement import PlaceField, lies_in
    from specimen_digitization.field_research.ontology_checks import fits, tgn_nations

    tools, _, _, _ = make(tmp_path, getty())
    answer = await tools.lookup("tgn", READING, field_key="city")
    [candidate] = answer.candidates
    guatemala = PlaceField(("Guatemala",), "tgn:7005493", None)
    assert fits(candidate, "country", guatemala, tgn_nations([answer], guatemala)) is None
    assert fits(candidate, "province_state", PlaceField(("Chimaltenango",), "tgn:1000565", None)) is None
    assert lies_in(candidate, "city", guatemala) and lies_in(candidate, "city", PlaceField(("Chimaltenango",)))
    assert not lies_in(candidate, "city", PlaceField(("Honduras",)))


@pytest.mark.asyncio
async def test_a_settled_place_derives_its_province_and_country_from_the_parents_it_reads(tmp_path):
    """Review round 1 of #471: derive reads a candidate's last parent as its country and the one
    before as its province. A chain that ran on to the continent made the derived country "North
    and Central America" and the province "Guatemala", unflagged."""
    from types import SimpleNamespace

    from specimen_digitization.application.domain import ValueState
    from specimen_digitization.field_research import derive
    from specimen_digitization.field_research.contracts import FieldValue

    tools, _, _, _ = make(tmp_path, getty())
    answer = await tools.lookup("tgn", READING, field_key="city")
    [candidate] = answer.candidates
    city = FieldValue(state=ValueState.SUPPORTED, literal=READING, normalized=READING,
        authority_id=candidate.authority_id, evidence_ids=[answer.evidence.id], layer="settled")
    fields = {"country": FieldValue(state=ValueState.NOT_PRESENT),
        "province_state": FieldValue(state=ValueState.NOT_PRESENT),
        "county": FieldValue(state=ValueState.NOT_PRESENT), "city": city}
    run = SimpleNamespace(evidence=[], fields=fields)
    filled = derive.fill(run, eligible=["country", "province_state", "county"], asset_id=None,
        received={"city": [answer]})
    # The candidate has two parents, so its province and country, never a county (derive's rule).
    assert {key: fields[key].parsed for key in filled} == {"province_state": "Chimaltenango", "country": "Guatemala"}
