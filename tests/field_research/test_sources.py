"""Field research's approved sources (FIELD_RESEARCH.md, Sources): one request per
distinct query per record, bounded retries, GEOLocate spacing, and every response
stored once as evidence that passes the integrity check. Offline: recorded
GEOLocate and gazetteer bodies, small GBIF bodies, a fake clock."""

import asyncio
import contextvars
import hashlib
import io
import json
import logging
import re
import threading
import time
from collections import Counter
from pathlib import Path

import httpx
import pytest
from PIL import Image

from specimen_digitization.application import georef_nga as nga
from specimen_digitization.application import georef_tgn as tgn
from specimen_digitization.application import georef_wikidata as wikidata
from specimen_digitization.application.domain import (
    Asset,
    Lookup,
    LookupStatus,
    Run,
    Scope,
    Specimen,
)
from specimen_digitization.application.integrity import (
    EvidenceIntegrityError,
    verify_evidence,
)
from specimen_digitization.application.storage import LocalBlobs
from specimen_digitization.field_research.contracts import PlaceRef, SourceCandidate
from specimen_digitization.field_research import sources as approved_sources
from specimen_digitization.field_research.sources import (
    EXCERPT_LIMIT,
    ApprovedSources,
    approved_registry,
    cache_key,
    excerpt,
)
from specimen_digitization.research_harness.committed_pins import _committed_registry
from specimen_digitization.research_harness.sources import SOURCE_PACER

TESTS = Path(__file__).parents[1]
GEOREF = TESTS / "fixtures" / "georeferencing"
GEOLOCATE = TESTS / "research_harness" / "fixtures" / "geolocate"
ID_FORMAT = re.compile(r"geolocate:[0-9a-f]{16}")


class Clock:
    """A fake monotonic clock. Its sleep returns at once and moves on the time of
    the task that slept, so the waits of concurrent tasks overlap as real ones do."""

    def __init__(self):
        self.slept = []
        self._now = contextvars.ContextVar("fake_now", default=0.0)

    def __call__(self):
        return self._now.get()

    async def sleep(self, seconds):
        self.slept.append(seconds)
        self._now.set(self._now.get() + seconds)
        await asyncio.sleep(0)


class CountingBlobs(LocalBlobs):
    def __init__(self, root):
        super().__init__(root)
        self.puts = []

    def put(self, data):
        self.puts.append(data)
        return super().put(data)


class Server:
    """An offline provider: records each request with the fake time, yields so a
    concurrent lookup can run, then answers with `reply`."""

    def __init__(self, reply, clock):
        self.reply = reply
        self.clock = clock
        self.requests = []

    async def __call__(self, request):
        self.requests.append((self.clock(), request))
        await asyncio.sleep(0)
        answer = self.reply(request)
        return answer if isinstance(answer, httpx.Response) else httpx.Response(200, json=answer)

    def urls(self):
        return [f"{request.url.host}{request.url.path}" for _, request in self.requests]


def make(tmp_path, reply, **options):
    clock = Clock()
    server = Server(reply, clock)
    blobs = CountingBlobs(tmp_path / "blobs")
    tools = ApprovedSources(
        blobs=blobs,
        client=httpx.AsyncClient(transport=httpx.MockTransport(server)),
        sleep=clock.sleep,
        clock=clock,
        **options,
    )
    return tools, server, clock, blobs


def nothing(request):
    raise AssertionError(f"no request may be sent: {request.url}")


def stored(blobs, evidence):
    """The evidence names bytes the store holds, by their digest."""
    data = blobs.get(evidence.raw_ref)
    assert hashlib.sha256(data).hexdigest() == evidence.digest
    return data


def lines(evidence):
    return evidence.excerpt.split("\n")


# --- GBIF, with Catalogue of Life and Global Names Verifier alongside ---

INSECTA = [
    {"rank": "KINGDOM", "name": "Animalia"},
    {"rank": "CLASS", "name": "Insecta"},
    {"rank": "ORDER", "name": "Hymenoptera"},
    {"rank": "FAMILY", "name": "Apidae"},
]
MELLIFERA = {
    "key": "1341976",
    "name": "Apis mellifera Linnaeus, 1758",
    "canonicalName": "Apis mellifera",
    "authorship": "Linnaeus, 1758",
    "rank": "SPECIES",
    "status": "ACCEPTED",
}
CERANA = {
    "key": "1341977",
    "name": "Apis cerana Fabricius, 1793",
    "canonicalName": "Apis cerana",
    "authorship": "Fabricius, 1793",
    "rank": "SPECIES",
    "status": "ACCEPTED",
}
GNV_EXACT = {"names": [{"matchType": "Exact", "bestResult": {"taxonomicStatus": "Accepted"}}]}
GNV_NONE = {"names": [{"matchType": "NoMatch"}]}
COL_EXACT = {"type": "exact", "match": True, "usage": {"name": "Apis mellifera", "status": "accepted"}}
COL_NONE = {"type": "none", "match": False}


def gbif_match(match, usage=None, alternatives=()):
    return {
        "usage": usage,
        "classification": INSECTA,
        "diagnostics": {
            "matchType": match,
            "confidence": 97,
            "alternatives": [
                {"usage": other, "classification": INSECTA, "diagnostics": {"matchType": "FUZZY"}}
                for other in alternatives
            ],
        },
    }


def taxonomy(match, gnv=GNV_EXACT, col=COL_EXACT):
    """GBIF's match (a body, or a callable for each match request), its index, GNV and COL."""

    def reply(request):
        if request.url.host == "api.gbif.org":
            if request.url.path.endswith("/metadata"):
                return {"alias": "fixture-index"}
            return match(request) if callable(match) else match
        if request.url.host == "verifier.globalnames.org":
            return gnv
        assert request.url.host == "api.checklistbank.org"
        return col

    return reply


@pytest.mark.asyncio
async def test_gbif_success_names_the_settled_usage_and_keeps_its_lookup(tmp_path):
    tools, server, _, blobs = make(
        tmp_path, taxonomy(gbif_match("EXACT", MELLIFERA, alternatives=[CERANA]))
    )
    answer = await tools.lookup("gbif", "Apis mellifera Linnaeus, 1758", field_key="taxon")
    assert answer.status is LookupStatus.SUCCESS
    assert answer.candidates == (
        SourceCandidate(
            name="Apis mellifera Linnaeus, 1758",
            authority_id="gbif:1341976",
            kind="SPECIES",
            detail="ACCEPTED; Insecta > Hymenoptera > Apidae",
        ),
        SourceCandidate(
            name="Apis cerana Fabricius, 1793",
            authority_id="gbif:1341977",
            kind="SPECIES",
            detail="ACCEPTED; Insecta > Hymenoptera > Apidae; alternative, fuzzy match",
        ),
    )
    assert answer.note == (
        "GBIF settles 'Apis mellifera Linnaeus, 1758' as Apis mellifera Linnaeus, 1758 "
        "at species rank; neither Catalogue of Life nor Global Names Verifier disagrees"
    )
    lookup = answer.taxonomy_lookup
    assert isinstance(lookup, Lookup) and lookup.provider == "gbif"
    assert lookup.status is LookupStatus.SUCCESS
    evidence = answer.evidence
    assert (evidence.kind, evidence.source, evidence.locator) == ("authority", "gbif", "gbif:1341976")
    # GBIF's own response, as stored once by the lookup behind the verification.
    assert (evidence.raw_ref, evidence.digest) == (lookup.raw_ref, lookup.digest)
    assert json.loads(stored(blobs, evidence))["usage"]["key"] == "1341976"
    assert lines(evidence)[1:] == [
        "Apis mellifera Linnaeus, 1758 | gbif:1341976 | SPECIES | ACCEPTED; Insecta > Hymenoptera > Apidae",
        "Apis cerana Fabricius, 1793 | gbif:1341977 | SPECIES | "
        "ACCEPTED; Insecta > Hymenoptera > Apidae; alternative, fuzzy match",
    ]
    assert sorted(server.urls()) == [
        "api.checklistbank.org/dataset/316321/match/nameusage",
        "api.gbif.org/v2/species/match",
        "api.gbif.org/v2/species/match/metadata",
        "verifier.globalnames.org/api/v1/verifications/Apis mellifera",
    ]


@pytest.mark.asyncio
async def test_gbif_no_match_keeps_the_response_without_a_locator(tmp_path):
    tools, _, _, blobs = make(tmp_path, taxonomy(gbif_match("NONE"), GNV_NONE, COL_NONE))
    answer = await tools.lookup("gbif", "Xus yus", field_key="taxon")
    assert answer.status is LookupStatus.NO_MATCH
    assert answer.candidates == ()
    assert answer.note == (
        "GBIF has no match for 'Xus yus'; neither Catalogue of Life nor Global Names Verifier disagrees"
    )
    assert (answer.evidence.kind, answer.evidence.locator) == ("lookup", None)
    stored(blobs, answer.evidence)


@pytest.mark.asyncio
async def test_gbif_ambiguous_lists_its_candidates_and_the_disagreement(tmp_path):
    tools, _, _, blobs = make(
        tmp_path, taxonomy(gbif_match("FUZZY", MELLIFERA, alternatives=[CERANA]), col=COL_NONE)
    )
    answer = await tools.lookup("gbif", "Apis melifera", field_key="taxon")
    assert answer.status is LookupStatus.AMBIGUOUS
    assert [item.authority_id for item in answer.candidates] == ["gbif:1341976", "gbif:1341977"]
    # GNV's exact accepted answer disagrees with GBIF's undecided one; COL's none does not.
    assert answer.note == (
        "GBIF cannot settle 'Apis melifera' (fuzzy match, 2 candidates); "
        "Global Names Verifier disagrees"
    )
    assert (answer.evidence.kind, answer.evidence.locator) == ("authority", None)
    stored(blobs, answer.evidence)


@pytest.mark.asyncio
async def test_gbif_retries_through_the_record_clock_and_bounds_each_request(tmp_path):
    replies = iter(
        [
            httpx.Response(429, headers={"Retry-After": "1"}, json={}),
            gbif_match("EXACT", MELLIFERA),
        ]
    )
    tools, server, clock, _ = make(tmp_path, taxonomy(lambda request: next(replies)))
    answer = await tools.lookup("gbif", "Apis mellifera Linnaeus, 1758", field_key="taxon")
    assert answer.status is LookupStatus.SUCCESS
    assert server.urls().count("api.gbif.org/v2/species/match") == 2
    assert clock.slept and min(clock.slept) >= 1
    # verify_taxon asks for up to 20 s; each request is held to 15.
    for _, request in server.requests:
        assert max(request.extensions["timeout"].values()) <= 15


@pytest.mark.asyncio
async def test_gbif_never_carries_the_record_place_text(tmp_path):
    tools, server, _, _ = make(
        tmp_path, taxonomy(gbif_match("NONE"), GNV_NONE, COL_NONE), place_text=("Davao",)
    )
    await tools.lookup("gbif", "Epipsocus Davao 1946", field_key="taxon")
    [match] = [r for _, r in server.requests if r.url.path == "/v2/species/match"]
    assert match.url.params["scientificName"] == "Epipsocus"
    assert all("Davao" not in str(request.url) for _, request in server.requests)


@pytest.mark.asyncio
async def test_gbif_concurrent_duplicates_make_one_verification(tmp_path):
    tools, server, _, _ = make(tmp_path, taxonomy(gbif_match("EXACT", MELLIFERA)))
    first, second = await asyncio.gather(
        tools.lookup("gbif", "Apis mellifera Linnaeus, 1758", field_key="taxon"),
        tools.lookup("gbif", "Apis  mellifera\nLinnaeus, 1758", field_key="taxon"),
    )
    assert len(server.requests) == 4  # GBIF match and index, GNV, COL: once
    assert second.evidence is first.evidence
    assert second.taxonomy_lookup is first.taxonomy_lookup
    assert second.query == "Apis  mellifera\nLinnaeus, 1758"


@pytest.mark.asyncio
async def test_closing_ends_a_running_gbif_verification_at_once(tmp_path):
    """Research ended with a GBIF request in flight: its worker thread must not
    hold the step, since asyncio.run waits for every worker thread."""
    asked = asyncio.Event()

    async def hang(request):
        asked.set()
        await asyncio.sleep(3600)

    tools = ApprovedSources(blobs=CountingBlobs(tmp_path / "blobs"),
                            client=httpx.AsyncClient(transport=httpx.MockTransport(hang)))
    field = asyncio.ensure_future(tools.lookup("gbif", "Apis mellifera", field_key="taxon"))
    await asyncio.wait_for(asked.wait(), 5)
    [shared] = tools._answers.values()
    field.cancel()  # The research deadline cancels the field's expert,
    tools.close()  # and the record's lookups end with the research.
    began = time.monotonic()
    answer = await asyncio.wait_for(shared, 5)
    assert time.monotonic() - began < 2
    assert answer.status is not LookupStatus.SUCCESS and answer.evidence is None
    assert not tools._running


@pytest.mark.asyncio
async def test_gbif_queries_that_differ_in_case_are_different_questions(tmp_path):
    # A scientific name's case is part of it: "apis" names no genus.
    assert cache_key("gbif", "Apis mellifera", "taxon") != cache_key("gbif", "apis mellifera", "taxon")
    assert cache_key("gbif", "Apis  mellifera", "taxon") == cache_key("gbif", "Apis mellifera", "taxon")
    assert cache_key("tgn", "Davao", "city") == cache_key("tgn", "DAVAO", "city")
    tools, server, _, _ = make(tmp_path, taxonomy(gbif_match("EXACT", MELLIFERA)))
    upper = await tools.lookup("gbif", "Apis mellifera", field_key="taxon")
    lower = await tools.lookup("gbif", "apis mellifera", field_key="taxon")
    assert upper.status is LookupStatus.SUCCESS
    assert lower.taxonomy_lookup is not upper.taxonomy_lookup and lower.evidence is not upper.evidence


# --- GEOLocate ---

YEPOCAPA = "Yepocapa, Chimaltenango, Guatemala"
YEPOCAPA_JSON = {"country": "Guatemala", "state": "Chimaltenango", "locality": "Yepocapa", "place": "Yepocapa"}


def recorded_geolocate(name):
    def reply(request):
        return httpx.Response(200, content=(GEOLOCATE / name).read_bytes())

    return reply


@pytest.mark.asyncio
async def test_geolocate_success_keeps_coordinates_out_of_the_identifier(tmp_path):
    tools, server, _, blobs = make(tmp_path, recorded_geolocate("yepocapa-modern.json"))
    answer = await tools.lookup("geolocate", YEPOCAPA, field_key="city")
    assert answer.status is LookupStatus.SUCCESS
    [candidate] = answer.candidates
    assert (candidate.name, candidate.authority_id) == ("Yepocapa", "geolocate:76853dedbc6ff5ce")
    assert ID_FORMAT.fullmatch(candidate.authority_id)
    assert "14.501946, -90.953956" in candidate.detail
    assert answer.note == "GEOLocate confirms 'Yepocapa': 2 of 2 match(es) agree within 10 km of each other"
    evidence = answer.evidence
    assert (evidence.kind, evidence.source, evidence.locator) == (
        "authority",
        "geolocate",
        "geolocate:76853dedbc6ff5ce",
    )
    assert stored(blobs, evidence) == (GEOLOCATE / "yepocapa-modern.json").read_bytes()
    [(_, request)] = server.requests
    assert (request.url.scheme, request.url.host, request.url.path) == (
        "https",
        "geo-locate.org",
        "/webservices/geolocatesvcv2/glcwrap.aspx",
    )
    assert dict(request.url.params) == {
        "Country": "Guatemala",
        "State": "Chimaltenango",
        "County": "",
        "Locality": "Yepocapa",
        "hwyX": "false",
        "enableH2O": "false",
        "doUncert": "true",
        "doPoly": "false",
        "displacePoly": "false",
        "languageKey": "0",
        "fmt": "json",
    }


@pytest.mark.asyncio
async def test_geolocate_no_match_says_where_the_place_is(tmp_path):
    tools, _, _, blobs = make(tmp_path, recorded_geolocate("yepocapa-modern.json"))
    answer = await tools.lookup(
        "geolocate", "Yepocapa, Chimaltenago, Guatemala", field_key="province_state"
    )
    assert answer.status is LookupStatus.NO_MATCH and answer.candidates == ()
    assert answer.note == "GEOLocate places 'Yepocapa' in CHIMALTENANGO, not 'Chimaltenago'"
    assert (answer.evidence.kind, answer.evidence.locator) == ("lookup", None)
    stored(blobs, answer.evidence)


@pytest.mark.asyncio
async def test_geolocate_ambiguous_lists_agreeing_matches_far_apart(tmp_path):
    tools, _, _, _ = make(tmp_path, recorded_geolocate("apo-modern.json"))
    answer = await tools.lookup("geolocate", "Mount Apo, Philippines", field_key="country")
    assert answer.status is LookupStatus.AMBIGUOUS
    assert [item.authority_id for item in answer.candidates] == [
        "geolocate:8547b94161036b7e",
        "geolocate:9a70a95409b960e3",
        "geolocate:3e5a153ca95eedd5",
    ]
    assert answer.evidence.locator is None
    assert [line.split(" | ")[1] for line in lines(answer.evidence)[1:]] == [
        item.authority_id for item in answer.candidates
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(("key", "literal", "query", "settles"), [
    # The third review's N2: a province literal "Yepocapa" in the place slot. GEOLocate's
    # candidate is the query's state part, which it only repeats: a province inferred
    # from a locality (province_state.txt), never a confirmation of it.
    ("province_state", "Yepocapa", YEPOCAPA, False),
    ("country", "Yepocapa", YEPOCAPA, False),
    # A city is GEOLocate's to confirm, when the literal is the query's first part.
    ("city", "Yepocapa", YEPOCAPA, True),
    ("city", "Chimaltenango", YEPOCAPA, False),
])
async def test_geolocate_settles_only_a_city_never_a_part_it_was_given(tmp_path, key, literal, query, settles):
    from specimen_digitization.application.domain import FieldValue, ValueState
    from specimen_digitization.field_research import agreement
    from specimen_digitization.field_research.contracts import FIELD_TOOLS, Candidate, FieldTask, Reading

    tools, _, _, _ = make(tmp_path, recorded_geolocate("yepocapa-modern.json"))
    answer = await tools.lookup("geolocate", query, field_key=key)
    assert answer.status is LookupStatus.SUCCESS
    [one] = answer.candidates
    text = f"Guatemala\n{key}: {literal}\nleg. J. Smith"
    readings = (Reading("1A", "r1", "o1a", "decided_transcript", text),
                Reading("1B", "r1", "o1b", "raw_reading", text))
    task = FieldTask(key, True, FieldValue(state=ValueState.SUPPORTED, literal=literal),
                     (Candidate("1A", f"{key}: {literal}", literal, "ev-1a"),), FIELD_TOOLS[key])
    refused = agreement.refusal(task, readings, literal=literal, named=[readings[0]], value=one.name,
                                authority_id=one.authority_id, cited=[answer], received=[answer])
    basis = agreement.place_basis(task, literal, one.name, one.authority_id, [answer])
    if settles:
        assert (refused, basis) == (None, agreement.ASKED)
        return
    assert refused.reason == agreement.NO_PLACE and basis is None


@pytest.mark.asyncio
async def test_two_fields_on_one_locality_share_one_request_and_one_stored_body(tmp_path):
    tools, server, _, blobs = make(tmp_path, recorded_geolocate("yepocapa-modern.json"))
    city, province, written = await asyncio.gather(
        tools.lookup("geolocate", YEPOCAPA, field_key="city"),
        tools.lookup("geolocate", YEPOCAPA, field_key="province_state"),
        # The interpretation written out as JSON is the same request.
        tools.lookup("geolocate", json.dumps({**YEPOCAPA_JSON, "value": "Yepocapa"}), field_key="city"),
    )
    assert [item.status for item in (city, province, written)] == [LookupStatus.SUCCESS] * 3
    # Each field's own value is what GEOLocate confirmed.
    assert [item.candidates[0].name for item in (city, province)] == ["Yepocapa", "Chimaltenango"]
    assert len(server.requests) == 1
    assert city.evidence.raw_ref == province.evidence.raw_ref == written.evidence.raw_ref
    assert len(blobs.puts) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "field_key", "reason"),
    [
        ("Yepocapa", "city", "GEOLocate takes a place and its country, comma separated"),
        ("Yepocapa, , Guatemala", "city", "GEOLocate takes a place and its country, comma separated"),
        ("Yepocapa, Chimaltenango, Guatemala", "county", "GEOLocate confirms a county only inside the USA"),
        ("{Yepocapa}", "city", "GEOLocate query_text must be one JSON object"),
        (
            json.dumps({**YEPOCAPA_JSON, "value": "Yepocapa", "latitude": 14.5, "longitude": -90.9, "radius_km": 5}),
            "city",
            "omit latitude, longitude and radius_km",
        ),
        (YEPOCAPA, "not_a_field", "GEOLocate checks a record field"),
    ],
)
async def test_an_unsendable_geolocate_query_is_refused_without_a_request(
    tmp_path, query, field_key, reason
):
    tools, server, _, _ = make(tmp_path, nothing)
    answer = await tools.lookup("geolocate", query, field_key=field_key)
    assert answer.status is LookupStatus.POLICY and answer.evidence is None
    assert reason in answer.note
    assert server.requests == []


@pytest.mark.asyncio
async def test_geolocate_requests_start_at_least_three_seconds_apart(tmp_path):
    tools, server, _, _ = make(tmp_path, recorded_geolocate("yepocapa-modern.json"))
    await asyncio.gather(
        tools.lookup("geolocate", YEPOCAPA, field_key="city"),
        tools.lookup("geolocate", "Yepocapa town, Chimaltenango, Guatemala", field_key="precise_location"),
        tools.lookup("geolocate", "Yepocapa village, Chimaltenango, Guatemala", field_key="precise_location"),
    )
    starts = sorted(at for at, _ in server.requests)
    assert len(starts) == 3
    assert all(later - earlier >= 3 for earlier, later in zip(starts, starts[1:], strict=False))


def test_geolocate_spacing_holds_across_records(tmp_path):
    """Each record has its own sources; the spacing between GEOLocate requests is
    the process's, as the six-specialist harness keeps it."""
    blobs = LocalBlobs(tmp_path / "blobs")
    client = httpx.AsyncClient(transport=httpx.MockTransport(nothing))
    first, second = (ApprovedSources(blobs=blobs, client=client) for _ in range(2))
    assert first._pacer is second._pacer is SOURCE_PACER


# --- At most two requests at a time to each gazetteer ---


class Held:
    """An offline provider that holds each request a moment and counts the
    requests in flight to each host, from any thread."""

    def __init__(self, seconds=0.02):
        self.seconds = seconds
        self._lock = threading.Lock()
        self.active, self.peak, self.total = Counter(), Counter(), Counter()

    async def __call__(self, request):
        host = request.url.host
        with self._lock:
            self.active[host] += 1
            self.total[host] += 1
            self.peak[host] = max(self.peak[host], self.active[host])
        try:
            await asyncio.sleep(self.seconds)
        finally:
            with self._lock:
                self.active[host] -= 1
        return httpx.Response(404)  # Final: one request per lookup.


def held_sources(tmp_path, held, slots=None):
    """A record's sources over `held`, with the process's slots unless given."""
    given = {} if slots is None else {"slots": slots}
    return ApprovedSources(blobs=LocalBlobs(tmp_path / "blobs"),
                           client=httpx.AsyncClient(transport=httpx.MockTransport(held)), **given)


@pytest.mark.asyncio
async def test_at_most_two_requests_at_a_time_go_to_each_gazetteer(tmp_path):
    held = Held()
    tools = held_sources(tmp_path, held)
    await asyncio.gather(*(tools.lookup(source, f"Place {name}", field_key="city")
                           for source in ("tgn", "wikidata", "nga") for name in "ABCDE"))
    hosts = {"services.getty.edu", "www.wikidata.org", "geonames.nga.mil"}
    assert set(held.total) == hosts and all(held.total[host] == 5 for host in hosts)
    # Each source is held to two at once on its own, not all three to two together.
    assert {host: held.peak[host] for host in hosts} == dict.fromkeys(hosts, 2)


def test_the_limit_holds_across_records_on_their_own_loops_and_threads(tmp_path):
    """Each record researches on its own event loop (FieldResearchStep.run's
    asyncio.run), maybe in its own thread: the two slots are the process's."""
    held, slots = Held(), approved_sources.SourceSlots({"tgn": 2})

    def record(n):
        async def research():
            tools = held_sources(tmp_path / str(n), held, slots)
            await asyncio.gather(*(tools.lookup("tgn", f"Place {'XYZ'[n]}{name}", field_key="city")
                                   for name in "ABCD"))
        asyncio.run(research())

    threads = [threading.Thread(target=record, args=(n,)) for n in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert held.total["services.getty.edu"] == 12 and held.peak["services.getty.edu"] == 2
    assert slots.in_flight("tgn") == 0


def test_a_request_cancelled_while_it_waits_never_keeps_a_slot():
    async def scenario():
        slots = approved_sources.SourceSlots({"tgn": 1})
        entered, release = asyncio.Event(), asyncio.Event()

        async def hold():
            async with slots.slot("tgn"):
                entered.set()
                await release.wait()

        async def take():
            async with slots.slot("tgn"):
                pass

        first = asyncio.create_task(hold())
        await entered.wait()
        # Cancelled while it waits: it never had the slot.
        waiting = asyncio.create_task(take())
        await asyncio.sleep(0)
        waiting.cancel()
        # Cancelled just after the slot was passed to it: it passes it on.
        given = asyncio.create_task(take())
        await asyncio.sleep(0)
        release.set()
        await first
        given.cancel()
        results = await asyncio.gather(waiting, given, return_exceptions=True)
        assert all(isinstance(result, asyncio.CancelledError) for result in results)
        assert slots.in_flight("tgn") == 0
        await asyncio.wait_for(take(), 1)
        assert slots.in_flight("tgn") == 0

    asyncio.run(scenario())


def test_every_records_sources_share_the_process_slots_and_geolocate_keeps_its_spacing(tmp_path):
    blobs = LocalBlobs(tmp_path / "blobs")
    client = httpx.AsyncClient(transport=httpx.MockTransport(nothing))
    first, second = (ApprovedSources(blobs=blobs, client=client) for _ in range(2))
    assert first._slots is second._slots is approved_sources.SOURCE_SLOTS
    # GEOLocate is spaced (SOURCE_PACER), never held; GBIF is neither.
    assert approved_sources.SOURCE_SLOTS.limits == {"tgn": 2, "wikidata": 2, "nga": 2}
    assert first._pacer is SOURCE_PACER


# --- Retries and failures ---


def replies(*answers):
    """Each request gets the next answer; an exception is raised as the transport's."""
    queue = list(answers)

    def reply(request):
        answer = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(answer, Exception):
            raise answer
        return answer

    return reply


@pytest.mark.asyncio
async def test_rate_limit_then_success_waits_for_retry_after(tmp_path):
    tools, server, clock, _ = make(
        tmp_path,
        replies(
            httpx.Response(429, headers={"Retry-After": "5"}),
            httpx.Response(200, content=(GEOLOCATE / "yepocapa-modern.json").read_bytes()),
        ),
    )
    answer = await tools.lookup("geolocate", YEPOCAPA, field_key="city")
    assert answer.status is LookupStatus.SUCCESS
    first, second = (at for at, _ in server.requests)
    assert second - first >= 5
    assert max(clock.slept) >= 5


@pytest.mark.asyncio
async def test_a_retry_after_over_ten_seconds_ends_the_retries(tmp_path):
    tools, server, clock, _ = make(
        tmp_path, replies(httpx.Response(429, headers={"Retry-After": "30"}))
    )
    answer = await tools.lookup("geolocate", YEPOCAPA, field_key="city")
    assert answer.status is LookupStatus.RATE_LIMITED and answer.evidence is None
    assert answer.note == (
        "GEOLocate asked to wait 30 s before another request, longer than a lookup waits"
    )
    assert len(server.requests) == 1 and clock.slept == []


@pytest.mark.asyncio
async def test_timeouts_exhaust_three_attempts_and_store_nothing(tmp_path):
    tools, server, _, blobs = make(tmp_path, replies(httpx.ReadTimeout("slow")))
    answer = await tools.lookup("geolocate", YEPOCAPA, field_key="city")
    assert answer.status is LookupStatus.TIMEOUT
    assert answer.evidence is None and answer.candidates == ()
    assert answer.note == "GEOLocate did not answer after 3 attempts"
    assert len(server.requests) == 3
    assert blobs.puts == []


@pytest.mark.asyncio
async def test_server_errors_exhaust_three_attempts(tmp_path):
    tools, server, _, _ = make(tmp_path, replies(httpx.Response(503)))
    answer = await tools.lookup("wikidata", "Davao Province", field_key="province_state")
    assert answer.status is LookupStatus.PROVIDER and answer.evidence is None
    assert answer.note == "Wikidata failed with HTTP 503 after 3 attempts"
    assert len(server.requests) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("code", "status"),
    [
        (404, LookupStatus.PROVIDER),
        (401, LookupStatus.AUTHENTICATION),
        (403, LookupStatus.AUTHORIZATION),
    ],
)
async def test_other_client_errors_are_final(tmp_path, code, status):
    tools, server, _, _ = make(tmp_path, replies(httpx.Response(code)))
    answer = await tools.lookup("geolocate", YEPOCAPA, field_key="city")
    assert answer.status is status and answer.evidence is None
    assert answer.note == f"GEOLocate refused the request with HTTP {code}"
    assert len(server.requests) == 1


def unanswered(caplog):
    """The sources' log lines for unanswered lookups, as key=value maps."""
    prefix = "Field research lookup unanswered: "
    return [
        dict(pair.split("=", 1) for pair in record.getMessage().removeprefix(prefix).split())
        for record in caplog.records
        if record.name == "specimen_digitization.field_research.sources"
        and record.levelname == "WARNING" and record.getMessage().startswith(prefix)
    ]


TGN_HOST = "services.getty.edu"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reply", "status", "line"),
    [
        # As Getty TGN may answer Cloud Run's addresses: a refusal, or a redirect,
        # which is never followed. Either is an outage, and logged.
        (httpx.Response(403), LookupStatus.AUTHORIZATION,
         {"http_status": "403", "error": "-", "retry_after": "absent", "attempt": "1"}),
        (httpx.Response(302, headers={"Location": "https://www.getty.edu/blocked"}), LookupStatus.PROVIDER,
         {"http_status": "302", "error": "-", "retry_after": "absent", "attempt": "1"}),
        (httpx.Response(503, headers={"Retry-After": "1"}), LookupStatus.PROVIDER,
         {"http_status": "503", "error": "-", "retry_after": "present", "attempt": "3"}),
        (httpx.ConnectError("refused"), LookupStatus.PROVIDER,
         {"http_status": "-", "error": "ConnectError", "retry_after": "absent", "attempt": "3"}),
        (httpx.Response(429, headers={"Retry-After": "30"}), LookupStatus.RATE_LIMITED,
         {"http_status": "429", "error": "-", "retry_after": "present", "attempt": "1"}),
    ],
)
async def test_every_unanswered_tgn_lookup_is_an_outage_logged_without_its_query(
    tmp_path, caplog, reply, status, line
):
    from specimen_digitization.field_research.experts import SOURCE_OUTAGES

    tools, server, _, blobs = make(tmp_path, replies(reply))
    with caplog.at_level(logging.WARNING, logger="specimen_digitization.field_research.sources"):
        answer = await tools.lookup("tgn", "Davao Province, Philippines", field_key="province_state")
    assert answer.status is status and status in SOURCE_OUTAGES and answer.evidence is None
    assert {request.url.host for _, request in server.requests} == {TGN_HOST}
    assert unanswered(caplog) == [
        {"step": "field_research", "source": "tgn", "host": TGN_HOST, **line}
    ]
    assert "Davao" not in caplog.text and "Philippines" not in caplog.text


@pytest.mark.asyncio
async def test_an_unanswered_geolocate_or_gbif_lookup_is_logged_too(tmp_path, caplog):
    def reply(request):
        if request.url.host == "api.gbif.org":
            return httpx.Response(503)
        raise httpx.ReadTimeout("slow")

    tools, _, _, _ = make(tmp_path, reply)
    with caplog.at_level(logging.WARNING, logger="specimen_digitization.field_research.sources"):
        place = await tools.lookup("geolocate", YEPOCAPA, field_key="city")
        taxon = await tools.lookup("gbif", "Apis mellifera", field_key="taxon")
    assert (place.status, taxon.status) == (LookupStatus.TIMEOUT, LookupStatus.PROVIDER)
    lines_ = unanswered(caplog)
    assert [(item["source"], item["host"]) for item in lines_] == [
        ("geolocate", "geo-locate.org"), ("gbif", "api.gbif.org")]
    assert (lines_[0]["error"], lines_[0]["attempt"]) == ("ReadTimeout", "3")
    assert lines_[1]["error"] == "provider_error" and int(lines_[1]["attempt"]) >= 1
    assert "Yepocapa" not in caplog.text and "Apis" not in caplog.text


@pytest.mark.asyncio
async def test_an_answered_lookup_logs_nothing(tmp_path, caplog):
    tools, _, _, _ = make(tmp_path, gazetteers())
    with caplog.at_level(logging.WARNING, logger="specimen_digitization.field_research.sources"):
        answer = await tools.lookup("wikidata", "Davao Province", field_key="province_state")
    assert answer.status is LookupStatus.SUCCESS and unanswered(caplog) == []


@pytest.mark.asyncio
async def test_a_malformed_body_is_malformed_and_kept(tmp_path):
    tools, server, _, blobs = make(
        tmp_path, replies(httpx.Response(200, content=b"<html>maintenance</html>"))
    )
    answer = await tools.lookup("geolocate", YEPOCAPA, field_key="city")
    assert answer.status is LookupStatus.MALFORMED and answer.candidates == ()
    assert answer.note == "GEOLocate's answer could not be read"
    assert (answer.evidence.kind, answer.evidence.locator) == ("lookup", None)
    assert stored(blobs, answer.evidence) == b"<html>maintenance</html>"
    assert len(server.requests) == 1


# --- Getty TGN, Wikidata and NGA ---


def recorded(name):
    return json.loads((GEOREF / name).read_text(encoding="utf-8"))


def gazetteers(tgn_hits=None):
    """The recorded gazetteer answers (tests/fixtures/georeferencing), each
    reduced to the identifiers its request names; `tgn_hits` keeps only the
    first reconciliation hits."""

    def reply(request):
        url = f"https://{request.url.host}{request.url.path}"
        params = dict(request.url.params)
        if url == tgn.RECONCILE:
            reading = json.loads(params["queries"])["q0"]["query"]
            hits = recorded("tgn_reconcile.json")["responses"][reading]
            return {"q0": {"result": hits[:tgn_hits]}}
        if url == tgn.SPARQL:
            ids = set(re.findall(r"tgn:([0-9]+)", params["query"]))
            source = "tgn_records.json" if "?ancestor" in params["query"] else "tgn_names.json"
            return {
                "results": {
                    "bindings": [
                        row
                        for row in recorded(source)["bindings"]
                        if row.get("place", {}).get("value", "").rsplit("/", 1)[-1] in ids
                    ]
                }
            }
        if url == wikidata.API:
            if "search" in params:
                return recorded("wikidata_search.json")["responses"][params["search"]]
            ids = set(params["ids"].split("|"))
            entities = recorded("wikidata_entities.json")["entities"]
            if params["props"] == "labels":
                entities = entities | recorded("wikidata_labels.json")["entities"]
            return {"entities": {key: value for key, value in entities.items() if key in ids}}
        where = params["where"]
        if url == nga.UNITS:
            codes = set(re.findall(r"'([A-Z]{2}-[A-Z0-9]+)'", where))
            rows = [row for row in recorded("nga_units.json")["features"] if row["adm1"] in codes]
        elif where.startswith("ufi IN"):
            ids = set(re.findall(r"-?[0-9]+", where))
            rows = [row for row in recorded("nga_features.json")["features"] if str(row["ufi"]) in ids]
        else:
            responses = recorded("nga_search.json")["responses"]
            rows = next(rows for name, rows in responses.items() if f"UPPER('{name}')" in where)
        return {"features": [{"attributes": row} for row in rows]}

    return reply


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source", "query", "tgn_hits", "status", "ids", "requests"),
    [
        ("tgn", "Chimaltenango", 1, LookupStatus.SUCCESS, ["tgn:1016636"], 3),
        ("tgn", "Chimaltenango", None, LookupStatus.AMBIGUOUS, ["tgn:1016636", "tgn:1000565"], 3),
        ("tgn", "Yepocapa", None, LookupStatus.NO_MATCH, [], 1),
        ("wikidata", "Davao Province", None, LookupStatus.SUCCESS, ["wikidata:Q15095071"], 3),
        # Two of the three entities are not in the recording: incomplete, never settled.
        ("wikidata", "Yepocapa", None, LookupStatus.AMBIGUOUS, [], 2),
        ("wikidata", "Chimaltenago", None, LookupStatus.NO_MATCH, [], 1),
        ("nga", "Mount Talomo", None, LookupStatus.SUCCESS, ["nga:-2455935"], 3),
        ("nga", "Yepocapa", None, LookupStatus.AMBIGUOUS, ["nga:-1143758", "nga:-1143757"], 3),
        ("nga", "Chimaltenago", None, LookupStatus.NO_MATCH, [], 1),
    ],
)
async def test_gazetteer_answers_and_their_evidence(
    tmp_path, source, query, tgn_hits, status, ids, requests
):
    tools, server, _, blobs = make(tmp_path, gazetteers(tgn_hits))
    answer = await tools.lookup(source, query, field_key="city")
    assert answer.status is status
    assert [item.authority_id for item in answer.candidates] == ids
    assert len(server.requests) == requests
    evidence = answer.evidence
    assert evidence.kind == ("authority" if ids else "lookup")
    assert evidence.locator == (ids[0] if status is LookupStatus.SUCCESS else None)
    # One record names every stored response of the chain by its digest.
    record = json.loads(stored(blobs, evidence))
    assert (record["source"], record["query"], record["status"]) == (source, query, status.value)
    assert len(record["exchanges"]) == requests
    for exchange in record["exchanges"]:
        assert hashlib.sha256(blobs.get(exchange["raw_ref"])).hexdigest() == exchange["sha256"]
    assert [line.split(" | ")[0] for line in lines(evidence)[1:]] == [
        item.name for item in answer.candidates
    ]


@pytest.mark.asyncio
async def test_a_gazetteer_place_reads_with_its_type_and_parents(tmp_path):
    tools, _, _, _ = make(tmp_path, gazetteers(tgn_hits=1))
    answer = await tools.lookup("tgn", "Chimaltenango", field_key="city")
    assert answer.candidates == (
        SourceCandidate(
            name="Chimaltenango",
            authority_id="tgn:1016636",
            kind="inhabited places, cities, department capitals",
            detail="in Chimaltenango, Guatemala",
            parents=(
                PlaceRef("Chimaltenango", "tgn:1000565"),
                PlaceRef("Guatemala", "tgn:7005493"),
            ),
        ),
    )
    assert answer.note == "Getty TGN has one place for 'Chimaltenango': Chimaltenango"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source", "query", "parents"),
    [
        # TGN and Wikidata name each parent by its own record.
        ("tgn", "Chimaltenango", [
            (PlaceRef("Chimaltenango", "tgn:1000565"), PlaceRef("Guatemala", "tgn:7005493")),
            (PlaceRef("Guatemala", "tgn:7005493"),),
        ]),
        ("wikidata", "Davao Province", [(PlaceRef("Philippines", "wikidata:Q928"),)]),
        # NGA names a first-order unit and a country code, no record of its own.
        ("nga", "Yepocapa", [(PlaceRef("Chimaltenango"), PlaceRef("GT"))] * 2),
    ],
)
async def test_a_gazetteer_place_names_the_places_it_lies_in(tmp_path, source, query, parents):
    tools, _, _, _ = make(tmp_path, gazetteers())
    answer = await tools.lookup(source, query, field_key="city")
    assert [item.parents for item in answer.candidates] == parents
    assert [item.detail.split(";")[0] for item in answer.candidates] == [
        "in " + ", ".join(parent.name for parent in found) for found in parents
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fixture", "query", "parents"),
    [
        # Outside the USA: the match's first-level unit, then the queried country.
        ("yepocapa-modern.json", YEPOCAPA, (PlaceRef("CHIMALTENANGO"), PlaceRef("Guatemala"))),
        # Inside it: the match's county, the queried state GEOLocate searched, the country.
        ("evanston-control.json", "Evanston, Cook, Illinois, USA",
         (PlaceRef("COOK"), PlaceRef("Illinois"), PlaceRef("USA"))),
    ],
)
async def test_a_geolocate_match_lies_in_its_unit_and_the_country_it_was_asked_in(
    tmp_path, fixture, query, parents
):
    tools, _, _, _ = make(tmp_path, recorded_geolocate(fixture))
    answer = await tools.lookup("geolocate", query, field_key="city")
    candidate = answer.candidates[0]
    assert candidate.parents == parents
    assert candidate.detail.startswith(
        f"GEOLocate matched {query.split(',')[0].upper()} in "
        + ", ".join(parent.name for parent in parents) + ";"
    )


@pytest.mark.asyncio
async def test_a_gazetteer_searches_the_place_name_before_its_larger_units(tmp_path):
    tools, server, _, blobs = make(tmp_path, gazetteers())
    answer = await tools.lookup("nga", YEPOCAPA, field_key="city")
    assert answer.status is LookupStatus.AMBIGUOUS
    assert answer.note == "NGA GEOnet Names Server has 2 places for 'Yepocapa'"
    assert [item.detail for item in answer.candidates] == ["in Chimaltenango, GT"] * 2
    assert "UPPER('Yepocapa')" in server.requests[0][1].url.params["where"]
    record = json.loads(stored(blobs, answer.evidence))
    assert (record["query"], record["searched"]) == (YEPOCAPA, "Yepocapa")


@pytest.mark.asyncio
async def test_gazetteer_concurrent_duplicates_make_one_chain(tmp_path):
    tools, server, _, blobs = make(tmp_path, gazetteers())
    first, second = await asyncio.gather(
        tools.lookup("tgn", "Chimaltenango", field_key="city"),
        tools.lookup("tgn", " chimaltenango ", field_key="province_state"),
    )
    assert len(server.requests) == 3
    assert second.evidence is first.evidence
    assert len(blobs.puts) == 4  # three responses and the record naming them


@pytest.mark.asyncio
async def test_a_gazetteer_chain_retries_a_failed_step(tmp_path):
    recorded_reply = gazetteers()
    failures = [httpx.Response(503)]

    def reply(request):
        return failures.pop() if failures else recorded_reply(request)

    tools, server, _, _ = make(tmp_path, reply)
    answer = await tools.lookup("wikidata", "Davao Province", field_key="province_state")
    assert answer.status is LookupStatus.SUCCESS
    assert len(server.requests) == 4


@pytest.mark.asyncio
async def test_unprintable_place_text_is_refused_without_a_request(tmp_path):
    tools, server, _, _ = make(tmp_path, nothing)
    answer = await tools.lookup("tgn", "Davao\x00", field_key="city")
    assert answer.status is LookupStatus.POLICY and answer.evidence is None
    assert answer.note == "Nothing was sent to Getty TGN: invalid filtered place text"
    assert server.requests == []


# --- Policy, cache and evidence ---


@pytest.mark.asyncio
async def test_a_source_outside_the_approved_set_is_policy_without_a_request(tmp_path):
    tools, server, _, _ = make(tmp_path, nothing, sources=("gbif",))
    for source in ("bugguide", "google_maps", "tgn"):
        answer = await tools.lookup(source, "Davao", field_key="city")
        assert answer.status is LookupStatus.POLICY
        assert answer.evidence is None and answer.candidates == ()
        assert answer.note == f"{source!r} is not an approved source for this record; nothing was sent"
    assert server.requests == []


@pytest.mark.asyncio
async def test_a_cached_answer_is_the_same_evidence_stored_once(tmp_path):
    tools, server, _, blobs = make(tmp_path, recorded_geolocate("yepocapa-modern.json"))
    first = await tools.lookup("geolocate", YEPOCAPA, field_key="city")
    second = await tools.lookup("geolocate", "yepocapa,  chimaltenango,\nGUATEMALA", field_key="city")
    assert second.evidence is first.evidence
    assert second.query == "yepocapa,  chimaltenango,\nGUATEMALA"
    # A JSON interpretation is compared by its object, not its spelling.
    written = await tools.lookup("geolocate", json.dumps({**YEPOCAPA_JSON, "value": "Yepocapa"}), field_key="city")
    respelled = await tools.lookup(
        "geolocate", json.dumps({"value": "Yepocapa", **YEPOCAPA_JSON}, indent=2), field_key="city"
    )
    assert respelled.evidence is written.evidence
    assert len(blobs.puts) == 1
    assert len(server.requests) == 1


def test_the_registry_is_the_committed_one():
    assert approved_registry().digest == _committed_registry().digest


def test_an_excerpt_cuts_details_never_names():
    candidates = [
        SourceCandidate(name=f"Place {index}", authority_id=f"tgn:{index}", kind="inhabited places", detail="x" * 1000)
        for index in range(10)
    ]
    text = excerpt("Getty TGN has 10 places for 'Place'", candidates)
    assert len(text) <= EXCERPT_LIMIT
    rows = text.split("\n")[1:]
    assert [row.split(" | ")[0] for row in rows] == [item.name for item in candidates]
    assert all(row.endswith("...") for row in rows)


def specimen(blobs, run):
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2)).save(buffer, format="PNG")
    png = buffer.getvalue()
    asset = Asset(
        sha256=hashlib.sha256(png).hexdigest(),
        blob_ref=blobs.put(png),
        media_type="image/png",
        size_bytes=len(png),
        width=2,
        height=2,
        filename="label.png",
        uploader="test",
    )
    return Specimen(scope=Scope(organization_id="org", collection_id="insects"), asset=asset, run=run)


@pytest.mark.asyncio
@pytest.mark.parametrize("damaged", [None, "gbif", "geolocate", "tgn"])
async def test_the_evidence_passes_the_integrity_check(tmp_path, damaged):
    def reply(request):
        if request.url.host == "geo-locate.org":
            return recorded_geolocate("yepocapa-modern.json")(request)
        if request.url.host in {"api.gbif.org", "verifier.globalnames.org", "api.checklistbank.org"}:
            return taxonomy(gbif_match("EXACT", MELLIFERA))(request)
        return gazetteers(tgn_hits=1)(request)

    tools, _, _, blobs = make(tmp_path, reply)
    answers = {
        "gbif": await tools.lookup("gbif", "Apis mellifera Linnaeus, 1758", field_key="taxon"),
        "geolocate": await tools.lookup("geolocate", YEPOCAPA, field_key="city"),
        "tgn": await tools.lookup("tgn", "Chimaltenango", field_key="city"),
    }
    run = Run(
        evidence=[answer.evidence for answer in answers.values()],
        lookups=[answers["gbif"].taxonomy_lookup],
    )
    record = specimen(blobs, run)
    if damaged is None:
        verify_evidence(record, blobs)
        return
    # The check reads each evidence item's bytes: a changed one fails it.
    (tmp_path / "blobs" / answers[damaged].evidence.raw_ref).write_bytes(b"changed")
    with pytest.raises(EvidenceIntegrityError):
        verify_evidence(record, blobs)
