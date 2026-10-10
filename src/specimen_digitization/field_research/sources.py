"""The approved sources one record's field experts may ask (FIELD_RESEARCH.md, Sources).

One instance serves one record and starts empty. Each distinct query is sent
once and answered from the cache after, so experts asking the same thing at the
same time share one request. Every request is bounded (15 s, three attempts
with backoff and jitter, a Retry-After of at most 10 s honoured), GEOLocate
keeps its 3 s spacing, and the process sends at most two requests at a time to
each of Getty TGN, Wikidata and NGA (SOURCE_SLOTS). Every response that comes back is stored once and
becomes one Evidence.

The rules that decide an answer stay where they are: GBIF's in
application.taxonomy_tool.verify_taxon, GEOLocate's in research_harness.sources
and the historical gazetteers' in research_harness.historical_gazetteers. A
source problem is an answer with a plain note, never an exception; only a blob
store failure raises. Each request a source leaves unanswered is logged in one
WARNING line with its source, host and HTTP status or error, never its query.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import dataclasses
import hashlib
import json
import logging
import re
import threading
import time
import unicodedata
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from functools import cache
from urllib.parse import urlencode, urlsplit

import httpx

from specimen_digitization.application.domain import Evidence, Lookup, LookupStatus
from specimen_digitization.application.georef_places import Place, Ref
from specimen_digitization.application.harness_tools import SourceCall
from specimen_digitization.application.lookup import parse_json
from specimen_digitization.application.reliability import retry_after, retry_delay
from specimen_digitization.application.storage import BlobStore
from specimen_digitization.application.taxonomy_tool import COL_URL, Verification, verify_taxon
from specimen_digitization.research_harness import historical_gazetteers
from specimen_digitization.research_harness.contracts import FieldKey, SourceQuery
from specimen_digitization.research_harness.source_readiness import SOURCE_READINESS
from specimen_digitization.research_harness.sources import (
    _USA,
    GEOLOCATE_ENDPOINT,
    SOURCE_PACER,
    SOURCE_REQUEST_INTERVAL_SECONDS,
    GeolocateInterpretation,
    RequestPacer,
    SourcePolicy,
    SourceRegistry,
    _fold_words,
    geolocate_interpretation,
    geolocate_verdict,
    insects_registry,
    validate_destination,
)

from .contracts import PLACE_SOURCES, PlaceRef, SourceAnswer, SourceCandidate

LOGGER = logging.getLogger(__name__)
SOURCES = ("gbif", *PLACE_SOURCES)
NAMES = {
    "gbif": "GBIF",
    "geolocate": "GEOLocate",
    "tgn": "Getty TGN",
    "wikidata": "Wikidata",
    "nga": "NGA GEOnet Names Server",
}
SUPPORT = {"col": "Catalogue of Life", "gnv": "Global Names Verifier"}
# Where verify_taxon asks GBIF (application.lookup.GbifTaxonomy), for its log line.
GBIF_MATCH_URL = "https://api.gbif.org/v2/species/match"
REQUEST_TIMEOUT_SECONDS = 15.0
ATTEMPTS = 3
RETRY_AFTER_LIMIT_SECONDS = 10
# verify_taxon's own bound on a body when it makes its requests itself.
TAXONOMY_MAX_BYTES = 1024 * 1024
QUERY_LIMIT = 500  # research_harness.contracts.SourceQuery's bound
EXCERPT_LIMIT = 2_000
NOTE_LIMIT = 300  # of the note that heads an excerpt
MAX_TAXA = 10
MAX_KINDS = 3
# What research_harness.sources.BoundedHTTPTransport sends.
HEADERS = {
    "Accept": "application/json",
    "Accept-Encoding": "identity",
    "User-Agent": "FieldMuseumSpecimenResearch/1.0 "
    "(https://github.com/anurag-duddu/specimen-digitization-app)",
}
# A response with one of these statuses came back and is kept as evidence.
ANSWERED = frozenset(
    {
        LookupStatus.SUCCESS,
        LookupStatus.NO_MATCH,
        LookupStatus.AMBIGUOUS,
        LookupStatus.EMPTY,
        LookupStatus.MALFORMED,
    }
)
REFUSED = {
    401: LookupStatus.AUTHENTICATION,
    403: LookupStatus.AUTHORIZATION,
    429: LookupStatus.RATE_LIMITED,
}


@cache
def approved_registry() -> SourceRegistry:
    """The committed source registry, built as research_harness.committed_pins
    builds it: the owner's registry with the committed readiness rows."""
    present = {policy.id for policy in insects_registry().policies}
    return insects_registry(
        qualification_overrides={
            source_id: dict(row)
            for source_id, row in SOURCE_READINESS.items()
            if source_id in present
        }
    )


@cache
def taxonomy_policies() -> tuple[SourcePolicy, ...]:
    """Where verify_taxon may send its requests: GBIF, Global Names Verifier and
    Catalogue of Life as the committed registry approves them. verify_taxon
    asks COL's name match (taxonomy_tool.COL_URL), a path the committed pattern,
    written for the six specialists' name search, does not name."""
    registry = approved_registry()
    col = registry.get("catalogue_of_life")
    col = col.model_copy(
        update={
            "allowed_path_patterns": (
                *col.allowed_path_patterns,
                re.escape(urlsplit(COL_URL).path),
            )
        }
    )
    return registry.get("gbif"), registry.get("global_names_verifier"), col


def cache_key(source_id: str, query: str, field_key: str) -> str:
    """A query as the cache compares it: NFC, whitespace collapsed, casefolded
    except for GBIF, where case is part of a scientific name ("apis" names no
    genus, and verify_taxon reads them apart). A GEOLocate query is its JSON
    object with sorted keys, and its field too, because geolocate_verdict
    checks the claimed value against the field."""
    text = query
    if source_id == "geolocate":
        try:
            parsed = parse_json(query)
        except (ValueError, RecursionError):
            parsed = None
        if isinstance(parsed, dict):
            text = json.dumps(parsed, sort_keys=True, ensure_ascii=False)
        text = f"{field_key}\n{text}"
    text = " ".join(unicodedata.normalize("NFC", text).split())
    return text if source_id == "gbif" else text.casefold()


def interpretation(query: str, field_key: FieldKey) -> str:
    """The GEOLocate interpretation a query names, as the JSON object
    research_harness.sources.geolocate_interpretation reads; a JSON object is
    taken as written. Otherwise the query is place words, comma separated, from
    the field's own place out to its country ("Yepocapa, Chimaltenango,
    Guatemala"; "Evanston, Cook, Illinois, USA"): the first part is the place
    GEOLocate looks for, the last its country, the part before the country its
    state or province and the part before that its county. The value checked
    is the field's own part: the country for country, the state for
    province_state and the county for county when the query names them, and
    the place otherwise. geolocate_interpretation then checks it as it checks
    any interpretation."""
    if query.lstrip().startswith("{"):
        return query
    parts = [part.strip() for part in query.split(",")]
    if not 2 <= len(parts) <= 4 or not all(parts):
        raise ValueError(
            "GEOLocate takes a place and its country, comma separated, "
            "with at most a state and a county between them"
        )
    place, country = parts[0], parts[-1]
    state = parts[-2] if len(parts) >= 3 else ""
    county = parts[-3] if len(parts) == 4 else ""
    value = {
        FieldKey.COUNTRY: country,
        FieldKey.PROVINCE_STATE: state or place,
        FieldKey.COUNTY: county or place,
    }.get(field_key, place)
    return json.dumps(
        {
            "country": country,
            "state": state,
            "county": county,
            "locality": place,
            "place": place,
            "value": value,
        },
        ensure_ascii=False,
    )


def geolocate_parents(place: GeolocateInterpretation, admin: str) -> tuple[PlaceRef, ...]:
    """Where a GEOLocate match lies, as the request and the match give it: the
    match's admin unit (the county inside the USA, the first-level unit outside
    it), the queried state inside the USA, where GEOLocate confines its search
    to that state, and the queried country, the only one GEOLocate searches
    (research_harness.sources: _geolocate_agrees, SourceBroker's request)."""
    usa = _fold_words(place.country) in _USA
    names = [admin, place.state if usa else "", place.country]
    return tuple(PlaceRef(name) for name in dict.fromkeys(name for name in names if name))


def place_name(query: str) -> str:
    """The name a gazetteer is searched for: the query up to its first comma,
    so "Yepocapa, Chimaltenango, Guatemala" searches "Yepocapa". The larger
    units stay with the expert, to compare with each candidate's parents."""
    return query.split(",", 1)[0].strip()


def excerpt(note: str, candidates: Sequence[SourceCandidate]) -> str:
    """The note, then each candidate verbatim on its own line as
    "name | authority_id | kind | detail", in at most EXCERPT_LIMIT characters.
    Only details are cut; a name never is, so a list whose names alone exceed
    the limit is kept whole."""
    head = note if len(note) <= NOTE_LIMIT else note[: NOTE_LIMIT - 3] + "..."
    if not candidates:
        return head
    fixed = [
        f"{item.name} | {item.authority_id or '-'} | {item.kind or '-'} | "
        for item in candidates
    ]
    budget = EXCERPT_LIMIT - len(head) - sum(map(len, fixed)) - len(fixed)
    details = _fit([item.detail or "" for item in candidates], budget)
    return "\n".join([head, *(line + detail for line, detail in zip(fixed, details, strict=True))])


def _fit(details: list[str], budget: int) -> list[str]:
    """Each detail cut to a fair share of `budget`, shortest first, so what a
    short one leaves goes to the others; a cut detail ends with "..."."""
    caps = [0] * len(details)
    left = max(0, budget)
    order = sorted(range(len(details)), key=lambda index: len(details[index]))
    for position, index in enumerate(order):
        caps[index] = min(len(details[index]), left // (len(order) - position))
        left -= caps[index]
    return [
        detail
        if len(detail) <= cap
        else detail[: cap - 3] + "..."
        if cap > 3
        else detail[:cap]
        for detail, cap in zip(details, caps, strict=True)
    ]


def _answer(
    source_id: str,
    query: str,
    status: LookupStatus,
    note: str,
    candidates: Sequence[SourceCandidate] = (),
    evidence: Evidence | None = None,
    taxonomy_lookup: Lookup | None = None,
) -> SourceAnswer:
    return SourceAnswer(
        source_id=source_id,
        query=query,
        status=status,
        candidates=tuple(candidates),
        evidence=evidence,
        note=note,
        taxonomy_lookup=taxonomy_lookup,
    )


def _evidence(
    source_id: str,
    status: LookupStatus,
    note: str,
    candidates: Sequence[SourceCandidate],
    raw_ref: str,
    digest: str,
    deciding: SourceCandidate | None = None,
) -> Evidence:
    """A stored response as evidence. Its locator is the deciding candidate's
    authority id, set only for a success that one candidate decides."""
    if deciding is None and len(candidates) == 1:
        deciding = candidates[0]
    return Evidence(
        kind="authority" if candidates else "lookup",
        source=source_id,
        locator=deciding.authority_id
        if status == LookupStatus.SUCCESS and deciding is not None
        else None,
        excerpt=excerpt(note, candidates),
        raw_ref=raw_ref,
        digest=digest,
    )


def _log_unanswered(
    source_id: str,
    url: str,
    *,
    attempt: int,
    http_status: int | None = None,
    error: str | None = None,
    retry_after: bool = False,
) -> None:
    """One WARNING line for a lookup a source left unanswered, as the worker
    logs a failed step (workflow._log_step_failure: key=value pairs): the
    source id, the host, the HTTP status or the error's class, whether the
    source sent a Retry-After, and the attempt the request ended on. Never
    the query, a parameter or a body, so no specimen text."""
    values = {
        "step": "field_research",
        "source": source_id,
        "host": urlsplit(url).hostname,
        "http_status": http_status,
        "error": error,
        "retry_after": "present" if retry_after else "absent",
        "attempt": attempt,
    }
    LOGGER.warning(
        "Field research lookup unanswered: %s",
        " ".join(f"{key}={'-' if value is None else value}" for key, value in values.items()),
    )


class _Unanswered(Exception):
    """No usable answer came back: the status to return and its plain note."""

    def __init__(self, status: LookupStatus, note: str):
        super().__init__(note)
        self.status = status
        self.note = note


@dataclass(frozen=True)
class _Fetched:
    """One final response to a GET. A 200 body is stored, once."""

    url: str
    status_code: int
    body: bytes
    raw_ref: str | None = None
    digest: str | None = None


def _forget_failure(cache: dict, key, task: asyncio.Future, keep: tuple = ()) -> None:
    # A storage failure is not an answer: the next lookup tries again. A
    # source that did not answer (`keep`) stays answered for this record.
    if task.cancelled() or (
        task.exception() is not None and not isinstance(task.exception(), keep)
    ):
        if cache.get(key) is task:
            del cache[key]


@dataclass(eq=False)
class _Waiter:
    """A request waiting for a slot, on its own event loop."""

    loop: asyncio.AbstractEventLoop
    future: asyncio.Future = field(init=False)
    granted: bool = False  # It was given a slot.
    gone: bool = False  # It stopped waiting without using one.

    def __post_init__(self):
        self.future = self.loop.create_future()

    def wake(self) -> None:
        if not self.future.done():
            self.future.set_result(None)


# How long a request waits for a slot (SourceSlots) before its lookup gives
# up unsent. A request holds its slot only while it is read, at most
# REQUEST_TIMEOUT_SECONDS (_read), so in two such bounds each slot of a
# source frees at least twice: with two slots, a request with up to three
# others waiting ahead of it is sent in time. It is a fifth of an expert's
# 150 s (experts.make_resolver's field_timeout_seconds), so a field whose
# lookup gives up still has the time to decide with its other sources.
SLOT_WAIT_SECONDS = 2 * REQUEST_TIMEOUT_SECONDS


class SlotBusy(Exception):
    """A request waited its SourceSlots' wait_seconds and got no slot."""


class SourceSlots:
    """At most `limits[source_id]` requests in flight to each source at once;
    a source with no limit is not held.

    The process's (SOURCE_SLOTS) is shared by every record's sources, as
    SOURCE_PACER's spacing is. Each record researches on an event loop of its
    own (FieldResearchStep.run's asyncio.run), maybe in a thread of its own,
    and an asyncio.Semaphore belongs to one loop, so the count is kept under a
    threading lock and a waiting request is woken on its own loop, first come
    first served. A request cancelled while it waits takes no slot, or passes
    on the one it was just given. A request that waits `wait_seconds` (None:
    no bound) without a slot stops waiting the same way and raises SlotBusy."""

    def __init__(self, limits: Mapping[str, int], wait_seconds: float | None = SLOT_WAIT_SECONDS):
        self.limits = dict(limits)
        self.wait_seconds = wait_seconds
        self._lock = threading.Lock()
        self._busy: dict[str, int] = {}
        self._waiting: dict[str, deque[_Waiter]] = {}

    def in_flight(self, source_id: str) -> int:
        with self._lock:
            return self._busy.get(source_id, 0)

    @asynccontextmanager
    async def slot(self, source_id: str) -> AsyncIterator[None]:
        limit = self.limits.get(source_id)
        if not limit:
            yield
            return
        await self._acquire(source_id, limit)
        try:
            yield
        finally:
            self._release(source_id)

    async def _acquire(self, source_id: str, limit: int) -> None:
        with self._lock:
            waiting = self._waiting.setdefault(source_id, deque())
            if self._busy.get(source_id, 0) < limit and not waiting:
                self._busy[source_id] = self._busy.get(source_id, 0) + 1
                return
            waiter = _Waiter(asyncio.get_running_loop())
            waiting.append(waiter)
        wait = asyncio.timeout(self.wait_seconds)
        try:
            async with wait:
                await waiter.future
        except BaseException as error:
            with self._lock:
                granted, waiter.gone = waiter.granted, True
                if not granted:
                    waiting.remove(waiter)
            if granted:
                self._release(source_id)
            # Only this wait's own bound; a cancellation stays one.
            if isinstance(error, TimeoutError) and wait.expired():
                raise SlotBusy(source_id) from None
            raise

    def _release(self, source_id: str) -> None:
        with self._lock:
            waiting = self._waiting.get(source_id)
            if not waiting:
                self._busy[source_id] -= 1
                return
            # The slot passes to the first waiter; the count stays.
            waiter = waiting.popleft()
            waiter.granted = True
        try:
            waiter.loop.call_soon_threadsafe(waiter.wake)
        except RuntimeError:
            # Its loop has closed: unless its task passed the slot on as it
            # was cancelled, the slot passes on from here.
            with self._lock:
                orphaned, waiter.gone = not waiter.gone, True
            if orphaned:
                self._release(source_id)


# Getty TGN, Wikidata and NGA each answer at most two of the process's
# requests at a time. GEOLocate keeps its 3 s spacing instead (SOURCE_PACER).
SOURCE_CONCURRENCY = {"tgn": 2, "wikidata": 2, "nga": 2}
SOURCE_SLOTS = SourceSlots(SOURCE_CONCURRENCY)


class _LoopTransport(httpx.BaseTransport):
    """verify_taxon's synchronous requests, sent by the record's AsyncClient on
    its event loop, so they share its transport and connection pool. Once the
    record's sources are closed a request fails at once, as one in flight then
    does: verify_taxon reads both as a request that could not be made."""

    def __init__(self, sources: ApprovedSources, loop):
        self._sources = sources
        self._loop = loop

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        sources = self._sources
        ended = httpx.RequestError("the record's lookups have ended", request=request)
        if sources.closed:
            raise ended
        future = sources._on_loop(self._loop, sources._send_taxonomy(request))
        try:
            return future.result(timeout=REQUEST_TIMEOUT_SECONDS + 5)
        except TimeoutError as error:
            future.cancel()
            raise httpx.ReadTimeout("no answer in time", request=request) from error
        except concurrent.futures.CancelledError:
            raise ended from None
        finally:
            sources._running.discard(future)


class ApprovedSources:
    """The approved sources of one record (contracts.SourceTools).

    A "gbif" query is a taxon name; a "geolocate" query is place words from the
    field's place out to its country, or the JSON interpretation itself
    (`interpretation`); a "tgn", "wikidata" or "nga" query is a place name,
    searched up to its first comma (`place_name`).

    `blobs` is the application's blob store (application.storage.BlobStore),
    `client` the AsyncClient every request goes through. `place_text` is the
    record's place-field literals and unassigned locality text, which a taxon
    request never carries (verify_taxon, PLAN 4.8). GEOLocate's spacing is the
    process's (research_harness.sources.SOURCE_PACER), so it holds across
    records; a test's own clock and sleep get a pacer of their own. At most two
    requests are in flight to Getty TGN, Wikidata and NGA each across the
    process (SOURCE_SLOTS, unless `slots` gives others).

    `close()` ends the record's lookups when its research ends.
    """

    def __init__(
        self,
        *,
        blobs: BlobStore,
        client: httpx.AsyncClient,
        sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
        sources: Sequence[str] = SOURCES,
        place_text: Sequence[str] = (),
        slots: SourceSlots | None = None,
    ):
        if isinstance(place_text, str):
            raise TypeError("place_text is a sequence of texts, not one string")
        self.blobs = blobs
        self.client = client
        self.sources = tuple(sources)
        self._sleep = sleep
        self._clock = clock
        self._place_text = tuple(place_text)
        self._registry = approved_registry()
        self._pacer = (
            SOURCE_PACER
            if sleep is asyncio.sleep and clock is time.monotonic
            else RequestPacer(SOURCE_REQUEST_INTERVAL_SECONDS, clock=clock, sleep=sleep)
        )
        self._slots = SOURCE_SLOTS if slots is None else slots
        self._answers: dict[tuple[str, str], asyncio.Task[SourceAnswer]] = {}
        self._responses: dict[str, asyncio.Task[_Fetched]] = {}
        # verify_taxon's requests and waits on the loop, from its worker threads.
        self._running: set[concurrent.futures.Future] = set()
        self.closed = False

    def close(self) -> None:
        """End this record's lookups: its research is over. A GBIF verification
        still running in its worker thread gets no more requests or waits and
        ends at once, instead of holding the step: asyncio.run waits for every
        worker thread before it returns."""
        self.closed = True
        for future in list(self._running):
            future.cancel()

    def _on_loop(self, loop, coroutine) -> concurrent.futures.Future:
        """Run a coroutine on the record's loop from a worker thread, cancelled
        by close()."""
        future = asyncio.run_coroutine_threadsafe(coroutine, loop)
        self._running.add(future)
        if self.closed:
            future.cancel()
        return future

    async def lookup(self, source_id: str, query: str, *, field_key: str) -> SourceAnswer:
        if source_id not in self.sources or source_id not in SOURCES:
            return _answer(
                source_id,
                query,
                LookupStatus.POLICY,
                f"{source_id!r} is not an approved source for this record; nothing was sent",
            )
        try:
            query.encode("utf-8")
        except UnicodeEncodeError:
            return _answer(
                source_id,
                query,
                LookupStatus.POLICY,
                f"The query holds characters that cannot be sent; nothing was sent to {NAMES[source_id]}",
            )
        key = (source_id, cache_key(source_id, query, field_key))
        task = self._answers.get(key)
        if task is None:
            task = asyncio.ensure_future(self._ask(source_id, query, field_key))
            self._answers[key] = task
            task.add_done_callback(
                lambda done, key=key: _forget_failure(self._answers, key, done)
            )
        # Shielded: one caller's cancellation leaves the shared request running.
        answer = await asyncio.shield(task)
        return answer if answer.query == query else dataclasses.replace(answer, query=query)

    async def _ask(self, source_id: str, query: str, field_key: str) -> SourceAnswer:
        policy = self._registry.get(source_id)
        if not policy.ready:
            return _answer(
                source_id,
                query,
                LookupStatus.POLICY,
                f"{NAMES[source_id]} is not qualified for use; nothing was sent",
            )
        if source_id == "gbif":
            return await self._taxon(query)
        if source_id == "geolocate":
            return await self._geolocate(policy, query, field_key)
        return await self._gazetteer(policy, query)

    # --- GBIF, with Catalogue of Life and Global Names Verifier alongside ---

    async def _taxon(self, query: str) -> SourceAnswer:
        # verify_taxon is synchronous; it runs in a worker thread and its
        # requests and waits come back to this loop.
        loop = asyncio.get_running_loop()
        verification = await asyncio.to_thread(self._verify, query, loop)
        decided, result = verification.gbif, verification.result
        asked = [call for call in result.sub_calls if call.source == "gbif"]
        status = decided.status
        if status not in ANSWERED:
            # verify_taxon made and retried GBIF's requests: its last call says
            # how it ended, as a status (no HTTP code reaches this far).
            last = asked[-1] if asked else None
            _log_unanswered(
                "gbif",
                GBIF_MATCH_URL,
                attempt=last.attempt if last else 0,
                error=status.value,
                retry_after=last is not None and last.retry_after_seconds is not None,
            )
            return _answer(
                "gbif", query, status, _taxon_failure(status, asked), taxonomy_lookup=decided
            )
        candidates = _taxa(decided) if status != LookupStatus.MALFORMED else ()
        note = _taxon_note(verification, candidates)
        evidence = None
        # A name with nothing it may send makes no request: nothing came back.
        if asked and decided.raw_ref and decided.digest:
            evidence = _evidence(
                "gbif",
                status,
                note,
                candidates,
                decided.raw_ref,
                decided.digest,
                deciding=candidates[0] if candidates else None,
            )
        return _answer("gbif", query, status, note, candidates, evidence, decided)

    def _verify(self, query: str, loop: asyncio.AbstractEventLoop) -> Verification:
        def sleep(seconds: float) -> None:
            if self.closed:
                return
            future = self._on_loop(loop, self._sleep(seconds))
            try:
                future.result()
            except concurrent.futures.CancelledError:
                pass  # Closed: the next request fails at once.
            finally:
                self._running.discard(future)

        with httpx.Client(
            transport=_LoopTransport(self, loop),
            headers=HEADERS,
            follow_redirects=False,
        ) as client:
            return verify_taxon(
                query,
                blobs=self.blobs,
                client=client,
                sleep=sleep,
                clock=self._clock,
                place_text=self._place_text,
            )

    async def _send_taxonomy(self, request: httpx.Request) -> httpx.Response:
        """One of verify_taxon's requests: to an approved destination only,
        within 15 s and its own 1 MiB bound. verify_taxon retries it."""
        url = str(request.url)
        if not any(_approved(policy, url) for policy in taxonomy_policies()):
            raise httpx.RequestError("destination is not an approved source", request=request)
        given = request.extensions.get("timeout")
        given = given if isinstance(given, dict) else {}
        request.extensions["timeout"] = {
            part: min(REQUEST_TIMEOUT_SECONDS, given.get(part) or REQUEST_TIMEOUT_SECONDS)
            for part in ("connect", "read", "write", "pool")
        }
        body = bytearray()
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                response = await self.client.send(request, stream=True, follow_redirects=False)
                try:
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > TAXONOMY_MAX_BYTES:
                            break  # A cut body reads as malformed, as verify_taxon's bound makes it.
                finally:
                    await response.aclose()
        except TimeoutError as error:
            raise httpx.ReadTimeout("no answer in time", request=request) from error
        kept = {
            name: value
            for name in ("content-type", "retry-after")
            if (value := response.headers.get(name)) is not None
        }
        return httpx.Response(
            response.status_code, headers=kept, content=bytes(body[:TAXONOMY_MAX_BYTES])
        )

    # --- GEOLocate ---

    async def _geolocate(self, policy: SourcePolicy, query: str, field_key: str) -> SourceAnswer:
        try:
            key = FieldKey(field_key)
        except ValueError:
            return _answer(
                "geolocate",
                query,
                LookupStatus.POLICY,
                f"GEOLocate checks a record field, and {field_key!r} is none; nothing was sent",
            )
        try:
            text = interpretation(query, key)
            if len(text) > QUERY_LIMIT:
                raise ValueError(f"a GEOLocate query is at most {QUERY_LIMIT} characters")
            place = geolocate_interpretation(text, key)
        except ValueError as error:
            return _answer(
                "geolocate", query, LookupStatus.POLICY, f"Nothing was sent to GEOLocate: {error}"
            )
        if place.latitude is not None:
            return _answer(
                "geolocate",
                query,
                LookupStatus.POLICY,
                "Nothing was sent to GEOLocate: omit latitude, longitude and radius_km; "
                "a placement is the derivation worker's",
            )
        # The request SourceBroker._execute sends: the place text only, never coordinates.
        url = (
            GEOLOCATE_ENDPOINT
            + "?"
            + urlencode(
                {
                    "Country": place.country,
                    "State": place.state,
                    "County": place.county,
                    "Locality": place.locality,
                    "hwyX": "false",
                    "enableH2O": "false",
                    "doUncert": "true",
                    "doPoly": "false",
                    "displacePoly": "false",
                    "languageKey": "0",
                    "fmt": "json",
                }
            )
        )
        try:
            fetched = await self._response(policy, url)
        except _Unanswered as failure:
            return _answer("geolocate", query, failure.status, failure.note)
        if fetched.status_code != 200:
            return _refused("geolocate", query, fetched.status_code)
        try:
            status, found, _count, note = geolocate_verdict(
                policy,
                SourceQuery(source_id="geolocate", field_key=key, query_text=text),
                parse_json(fetched.body),
            )
        except (ValueError, TypeError, KeyError, AttributeError, ArithmeticError, RecursionError):
            status, found, note = LookupStatus.MALFORMED, [], "GEOLocate's answer could not be read"
        candidates = tuple(
            SourceCandidate(
                name=item["value"],
                authority_id=item["authority_id"],
                detail=f"GEOLocate matched {item['match_name']} in "
                + ", ".join(parent.name for parent in geolocate_parents(place, item["match_admin"]))
                + f"; precision {item['match_precision']}, score {item['match_score']}; "
                f"{item['decimal_latitude']:.6f}, {item['decimal_longitude']:.6f}",
                parents=geolocate_parents(place, item["match_admin"]),
            )
            for item in found
        )
        evidence = _evidence(
            "geolocate", status, note, candidates, fetched.raw_ref, fetched.digest
        )
        return _answer("geolocate", query, status, note, candidates, evidence)

    # --- Getty TGN, Wikidata and NGA ---

    async def _gazetteer(self, policy: SourcePolicy, query: str) -> SourceAnswer:
        source_id, name = policy.id, NAMES[policy.id]
        searched = place_name(query)
        fetched: list[_Fetched] = []

        async def fetch(url: str, params: dict[str, str]) -> tuple[int, bytes]:
            response = await self._response(policy, url + "?" + urlencode(params))
            fetched.append(response)
            return response.status_code, response.body

        try:
            outcome = await historical_gazetteers.lookup(source_id, searched, fetch)
        except _Unanswered as failure:
            return _answer(source_id, query, failure.status, failure.note)
        status, places = outcome.status, outcome.places
        if status == LookupStatus.SUCCESS:
            status = (
                LookupStatus.NO_MATCH
                if not places
                else LookupStatus.SUCCESS
                if len(places) == 1
                else LookupStatus.AMBIGUOUS
            )
        candidates = tuple(_place(source_id, place) for place in places)
        note = _gazetteer_note(name, searched, status, outcome, fetched)
        if status not in ANSWERED or not fetched:
            return _answer(source_id, query, status, note)
        # Up to three responses answer one query: one record names each stored
        # response and its digest, and that record is the evidence.
        record = json.dumps(
            {
                "source": source_id,
                "query": query,
                "searched": searched,
                "status": status.value,
                "exchanges": [
                    {
                        "url": item.url,
                        "http_status": item.status_code,
                        "raw_ref": item.raw_ref,
                        "sha256": item.digest,
                    }
                    for item in fetched
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        raw_ref = await asyncio.to_thread(self.blobs.put, record)
        evidence = _evidence(
            source_id, status, note, candidates, raw_ref, hashlib.sha256(record).hexdigest()
        )
        return _answer(source_id, query, status, note, candidates, evidence)

    # --- HTTP ---

    async def _response(self, policy: SourcePolicy, url: str) -> _Fetched:
        """The final response to a GET of `url`, shared by every query of this
        record that needs it. Raises _Unanswered when none came back."""
        try:
            validate_destination(policy, url)
        except ValueError:
            raise _Unanswered(
                LookupStatus.POLICY,
                f"The request is outside {NAMES[policy.id]}'s approval; nothing was sent",
            ) from None
        task = self._responses.get(url)
        if task is None:
            task = asyncio.ensure_future(self._fetch(policy, url))
            self._responses[url] = task
            task.add_done_callback(
                lambda done: _forget_failure(self._responses, url, done, keep=(_Unanswered,))
            )
        return await asyncio.shield(task)

    async def _fetch(self, policy: SourcePolicy, url: str) -> _Fetched:
        response = await self._get(policy, url)
        if response.status_code != 200:
            return response
        raw_ref = await asyncio.to_thread(self.blobs.put, response.body)
        return dataclasses.replace(
            response, raw_ref=raw_ref, digest=hashlib.sha256(response.body).hexdigest()
        )

    async def _get(self, policy: SourcePolicy, url: str) -> _Fetched:
        """One GET with retries: a rate limit, a server error, a timeout or a
        transport error is tried again, ATTEMPTS times in all, with backoff and
        jitter and never sooner than the provider's Retry-After. A Retry-After
        over RETRY_AFTER_LIMIT_SECONDS ends the retries; any other answer is final.
        A final answer other than 200 (a refusal, a redirect, which is never
        followed) and a request that got none are logged (_log_unanswered)."""
        name = NAMES[policy.id]
        for attempt in range(1, ATTEMPTS + 1):
            await self._pacer.wait(policy.id)
            wait, retry, code, error = None, "", None, None
            try:
                async with self._slots.slot(policy.id):
                    code, body, retry = await self._read(url, policy.max_response_bytes, name)
            except _Unanswered:
                _log_unanswered(policy.id, url, attempt=attempt, error="response_too_large")
                raise
            except SlotBusy:
                # Every slot stayed taken (SLOT_WAIT_SECONDS): this request is
                # not sent, and the lookup gives up rather than spend its
                # field's time waiting.
                _log_unanswered(policy.id, url, attempt=attempt, error="slot_busy")
                sent = "" if attempt == 1 else f" again after {attempt - 1} attempt{'s' if attempt > 2 else ''}"
                raise _Unanswered(LookupStatus.TIMEOUT, f"{name} was busy; this lookup was not sent{sent}") from None
            except (httpx.TimeoutException, TimeoutError) as failure:
                status, note = LookupStatus.TIMEOUT, f"{name} did not answer after {ATTEMPTS} attempts"
                error = type(failure).__name__
            except httpx.HTTPError as failure:
                status, note = (
                    LookupStatus.PROVIDER,
                    f"{name} could not be reached after {ATTEMPTS} attempts",
                )
                error = type(failure).__name__
            else:
                if code != 429 and code < 500:
                    if code != 200:
                        _log_unanswered(
                            policy.id, url, attempt=attempt, http_status=code, retry_after=bool(retry)
                        )
                    return _Fetched(url, code, body)
                status = LookupStatus.RATE_LIMITED if code == 429 else LookupStatus.PROVIDER
                note = (
                    f"{name} was still rate limiting after {ATTEMPTS} attempts"
                    if code == 429
                    else f"{name} failed with HTTP {code} after {ATTEMPTS} attempts"
                )
                wait = retry_after(retry)
                if wait is not None and wait > RETRY_AFTER_LIMIT_SECONDS:
                    _log_unanswered(policy.id, url, attempt=attempt, http_status=code, retry_after=True)
                    raise _Unanswered(
                        status,
                        f"{name} asked to wait {wait} s before another request, "
                        f"longer than a lookup waits",
                    )
            if attempt < ATTEMPTS:
                await self._sleep(retry_delay(attempt, wait))
        _log_unanswered(
            policy.id, url, attempt=ATTEMPTS, http_status=code, error=error, retry_after=bool(retry)
        )
        raise _Unanswered(status, note)

    async def _read(self, url: str, limit: int, name: str) -> tuple[int, bytes, str]:
        async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
            async with self.client.stream(
                "GET",
                url,
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT_SECONDS,
                follow_redirects=False,
            ) as response:
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > limit:
                        raise _Unanswered(
                            LookupStatus.MALFORMED,
                            f"{name}'s answer is longer than {limit:,} bytes",
                        )
                return response.status_code, bytes(body), response.headers.get("Retry-After", "")


def _approved(policy: SourcePolicy, url: str) -> bool:
    try:
        validate_destination(policy, url)
    except ValueError:
        return False
    return True


def _refused(source_id: str, query: str, code: int) -> SourceAnswer:
    return _answer(
        source_id,
        query,
        REFUSED.get(code, LookupStatus.PROVIDER),
        f"{NAMES[source_id]} refused the request with HTTP {code}",
    )


def _classification(levels) -> str | None:
    """A classification as class > order > family."""
    names = [
        level["name"]
        for level in levels or ()
        if isinstance(level, dict)
        and level.get("rank") in ("CLASS", "ORDER", "FAMILY")
        and level.get("name")
    ]
    return " > ".join(names) or None


def _taxa(lookup: Lookup) -> tuple[SourceCandidate, ...]:
    """GBIF's usages, the settled one first (for a cleared synonym its accepted
    usage), then the other usage and GBIF's alternatives, at most MAX_TAXA."""
    classification = _classification((lookup.metadata or {}).get("classification"))
    found: list[SourceCandidate] = []
    seen: set[str] = set()
    for item in lookup.candidates:
        alternative = "diagnostics" in item
        usage = item.get("usage") if alternative else item
        if not isinstance(usage, dict) or not usage.get("key") or not usage.get("name"):
            continue
        key = str(usage["key"])
        if key in seen:
            continue
        seen.add(key)
        parts = [
            usage.get("status"),
            _classification(item.get("classification")) if alternative else classification,
        ]
        if alternative:
            match = (item.get("diagnostics") or {}).get("matchType")
            parts.append(f"alternative, {match.lower()} match" if match else "alternative")
        found.append(
            SourceCandidate(
                name=usage.get("scientificName") or usage["name"],
                authority_id=f"gbif:{key}",
                kind=usage.get("rank"),
                detail="; ".join(part for part in parts if part) or None,
            )
        )
        if len(found) == MAX_TAXA:
            break
    return tuple(found)


def _taxon_note(verification: Verification, candidates: Sequence[SourceCandidate]) -> str:
    """What GBIF decided, and whether Catalogue of Life or Global Names Verifier
    disagreed or did not answer, in one sentence."""
    decided, result = verification.gbif, verification.result
    if "no_scientific_name" in result.warnings:
        return "The query writes no scientific name, so nothing was sent to GBIF"
    if not any(call.source == "gbif" for call in result.sub_calls):
        return "Nothing was sent to GBIF: the genus is in doubt or is place text"
    asked = decided.query.get("scientificName", "")
    status = decided.status
    if status == LookupStatus.MALFORMED:
        return "GBIF's answer could not be read"
    if status == LookupStatus.SUCCESS and candidates:
        settled = candidates[0]
        decision = f"GBIF settles {asked!r} as {settled.name}" + (
            f" at {settled.kind.lower()} rank" if settled.kind else ""
        )
    elif status == LookupStatus.NO_MATCH:
        decision = f"GBIF has no match for {asked!r}"
    else:
        match = ((decided.metadata or {}).get("diagnostics") or {}).get("matchType")
        decision = (
            f"GBIF cannot settle {asked!r} ({(match or 'unclear').lower()} match, "
            f"{len(candidates)} candidate{'s' if len(candidates) != 1 else ''})"
        )
        if (decided.metadata or {}).get("partly_read"):
            decision += ", the name read only in part"
    said = []
    for source, name in SUPPORT.items():
        if f"taxonomy_support_unavailable:{source}" in result.warnings:
            said.append(f"{name} did not answer")
        elif f"taxonomy_source_disagreement:{source}" in result.warnings:
            said.append(f"{name} disagrees")
    support = " and ".join(said) or "neither Catalogue of Life nor Global Names Verifier disagrees"
    return f"{decision}; {support}"


def _taxon_failure(status: LookupStatus, asked: Sequence[SourceCall]) -> str:
    what = {
        LookupStatus.TIMEOUT: "did not answer",
        LookupStatus.RATE_LIMITED: "was rate limiting",
        LookupStatus.AUTHENTICATION: "refused access",
        LookupStatus.AUTHORIZATION: "refused access",
    }.get(status, "failed")
    count = len(asked)
    return f"GBIF {what} ({count} attempt{'s' if count != 1 else ''})"


def _parent(source_id: str, ref: Ref) -> PlaceRef:
    """A parent place as the gazetteer names it. Getty TGN and Wikidata name a
    parent by its own record (a TGN subject, a Wikidata item), so it carries
    that record's authority_id; NGA names a first-order unit code and a
    country code, which are no NGA record."""
    record = f"{source_id}:{ref.id}" if source_id in ("tgn", "wikidata") and ref.id else None
    return PlaceRef(ref.name or ref.id, record)


def _place(source_id: str, place: Place) -> SourceCandidate:
    kinds = [kind.name or kind.id for kind in place.kinds if kind.name or kind.id]
    parents = [_parent(source_id, parent) for parent in place.parents]
    if place.country and (place.country.name or place.country.id) not in [p.name for p in parents]:
        parents.append(_parent(source_id, place.country))
    detail = "in " + ", ".join(parent.name for parent in parents) if parents else ""
    valid = " ".join(
        part
        for part in (
            f"from {place.valid_from}" if place.valid_from else "",
            f"until {place.valid_to}" if place.valid_to else "",
        )
        if part
    )
    if valid:
        detail += ("; " if detail else "") + "valid " + valid
    return SourceCandidate(
        name=place.name,
        authority_id=f"{source_id}:{place.record_id}",
        kind=", ".join(kinds[:MAX_KINDS]) or None,
        detail=detail or None,
        parents=tuple(parents),
    )


def _gazetteer_note(
    name: str,
    query: str,
    status: LookupStatus,
    outcome: historical_gazetteers.HistoricalLookup,
    fetched: Sequence[_Fetched],
) -> str:
    places = outcome.places
    if status == LookupStatus.SUCCESS:
        return f"{name} has one place for {query!r}: {places[0].name}"
    if status == LookupStatus.AMBIGUOUS and places:
        return f"{name} has {len(places)} places for {query!r}"
    if status == LookupStatus.AMBIGUOUS:
        return f"{name} cannot settle {query!r}: {outcome.reason or 'its answer was incomplete'}"
    if status in (LookupStatus.NO_MATCH, LookupStatus.EMPTY):
        return f"{name} has no place for {query!r}"
    if status == LookupStatus.POLICY:
        return f"Nothing was sent to {name}: {outcome.reason or 'the place text was refused'}"
    if status == LookupStatus.MALFORMED:
        return f"{name}'s answer could not be read" + (
            f": {outcome.reason}" if outcome.reason else ""
        )
    code = fetched[-1].status_code if fetched else None
    if code is not None and code != 200:
        return f"{name} refused the request with HTTP {code}"
    return f"{name} reported {status.value.replace('_', ' ')}"
