"""Bounded tier-1 gazetteer orchestration for a qualified source dispatcher.

``filtered_name`` must be the output of the geography place-text filter. This
is an internal broker API, never a public model tool accepting raw label text.
The caller's ``fetch`` records each full response durably before returning it;
this module makes no network request, grants no source qualification, and does
not turn a historical candidate into a settled modern location.
"""

from __future__ import annotations

import dataclasses
import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import ParamSpec, TypeVar

from specimen_digitization.application.domain import LookupStatus
from specimen_digitization.application.georef_places import Place
from specimen_digitization.application import georef_nga as nga
from specimen_digitization.application import georef_tgn as tgn
from specimen_digitization.application import georef_wikidata as wikidata

Fetch = Callable[[str, dict[str, str]], Awaitable[tuple[int, bytes]]]
MAX_CALLS = 3
MAX_BODY_BYTES = 2_000_000
SOURCES = frozenset({tgn.SOURCE, wikidata.SOURCE, nga.SOURCE})
# Getty TGN reconciliation answers that send its search to the SPARQL endpoint.
SEARCH_REFUSALS = frozenset({401, 403})
# What a later request's parser says of a reply that holds nothing it can use:
# no body (EMPTY), no row or none to use (NO_MATCH), or a body that is not the
# answer or holds a row it cannot read, even beside readable ones (MALFORMED).
# Once the search has found something, such a reply is no answer about the
# query, so the lookup is MALFORMED (`_later`), never NO_MATCH, which would
# rule a reading out.
UNREAD = frozenset({LookupStatus.EMPTY, LookupStatus.NO_MATCH, LookupStatus.MALFORMED})
# Why a Getty TGN search through the SPARQL endpoint that found no place is
# AMBIGUOUS, never NO_MATCH: Getty's full-text index matches a name's words as
# written, not across accents or word stems ("Solola" finds neither Guatemalan
# place whose name ends in an accented a, tgn:1016724 and tgn:1000765, and
# "Chimaltenangos" finds no Chimaltenango; probed 2026-10-11), so the place
# the name means may be there under another spelling.
SPARQL_FOUND_NOTHING = "the SPARQL search found no place, which rules nothing out"
_P = ParamSpec("_P")
_R = TypeVar("_R")


class _MalformedSource(Exception):
    """A local source parser or request builder rejected provider data."""


class SearchUnanswered(Exception):
    """Raised by a caller's fetch for Getty TGN's reconciliation request only,
    when that request got no response at all, so nothing came back to capture.
    The TGN search then goes through the SPARQL endpoint instead. Every other
    fetch exception still reaches the owning broker unchanged. `reason` says
    what happened in a few plain words ("did not answer after 3 attempts")."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _source_value(operation: Callable[_P, _R], *args: _P.args, **kwargs: _P.kwargs) -> _R:
    # Keep this boundary around local parsing/building only. In particular,
    # durable fetch and receipt failures must reach the owning broker unchanged.
    try:
        return operation(*args, **kwargs)
    except (KeyError, OverflowError, TypeError, ValueError) as error:
        raise _MalformedSource from error


@dataclass(frozen=True, slots=True)
class Exchange:
    """One returned response, including bytes for the caller's receipt."""

    url: str
    params: tuple[tuple[str, str], ...]
    http_status: int | None
    response_body: bytes | None
    response_digest: str | None
    failure: str | None = None


@dataclass(frozen=True, slots=True)
class HistoricalLookup:
    status: LookupStatus
    places: tuple[Place, ...]
    exchanges: tuple[Exchange, ...]
    reason: str | None = None
    # Why Getty TGN's search went through the SPARQL endpoint, when it did:
    # "refused the request (HTTP 403)", or a SearchUnanswered's reason.
    fallback: str | None = None
    # The later request whose reply could not be read once the search had found
    # something, when the lookup is MALFORMED for it (`_later`): "record" or
    # "name" (Getty TGN), "entity" or "label" (Wikidata), "feature" or "unit" (NGA).
    unread: str | None = None


async def lookup(source_id: str, filtered_name: str, fetch: Fetch) -> HistoricalLookup:
    """Search one source by filtered place text, then read only its returned IDs.

    Every stage is capped and a non-success result ends the chain. Only the
    search can answer NO_MATCH: once it has found something, a later reply
    with nothing its parser can use makes the lookup MALFORMED (`_later`).
    The broker owns source registration, place-text filtering, durable fetch receipts,
    retries and the decision about whether a returned place is qualified.
    Fetch, capture, and receipt exceptions propagate to that owner; this
    parser cannot declare an uncertain effect settled or refund its cost.
    One exception is the fetch's own signal: when Getty TGN's reconciliation
    request is refused (SEARCH_REFUSALS) or the fetch raises SearchUnanswered
    for it, TGN is searched through its SPARQL endpoint instead (`_tgn_search`).
    """
    if source_id not in SOURCES:
        raise ValueError("unknown historical gazetteer source")
    calls: list[Exchange] = []
    try:
        {
            tgn.SOURCE: tgn.reconcile_params,
            wikidata.SOURCE: wikidata.search_params,
            nga.SOURCE: nga.search_params,
        }[source_id](filtered_name)
    except ValueError:
        return _result(LookupStatus.POLICY, calls, reason="invalid filtered place text")
    try:
        if source_id == tgn.SOURCE:
            return await _tgn(filtered_name, fetch, calls)
        if source_id == wikidata.SOURCE:
            return await _wikidata(filtered_name, fetch, calls)
        return await _nga(filtered_name, fetch, calls)
    except _MalformedSource:
        return _result(
            LookupStatus.MALFORMED, calls, reason="invalid source identifier or response"
        )


def _result(
    status: LookupStatus,
    calls: list[Exchange],
    places: tuple[Place, ...] = (),
    reason: str | None = None,
) -> HistoricalLookup:
    return HistoricalLookup(status, places, tuple(calls), reason)


def _later(outcome: LookupStatus, calls: list[Exchange], request: str) -> HistoricalLookup:
    """The end of a lookup whose search found something, at a later request
    (`request`: "record", "name", "entity", "label", "feature" or "unit") that
    did not succeed. A reply that holds nothing its parser can use (UNREAD) is
    MALFORMED, an outage: the search reported something there, so it never
    rules a reading out as NO_MATCH would. Any other outcome (a refusal, a
    rate limit, a server error) ends the lookup as it is."""
    if outcome not in UNREAD:
        return _result(outcome, calls)
    return HistoricalLookup(
        LookupStatus.MALFORMED,
        (),
        tuple(calls),
        f"the search found places but the {request} reply could not be read",
        unread=request,
    )


async def _request(
    url: str, params: dict[str, str], fetch: Fetch, calls: list[Exchange]
) -> tuple[LookupStatus | None, int | None, bytes | None]:
    if len(calls) >= MAX_CALLS:
        return LookupStatus.AMBIGUOUS, None, None
    sent = tuple(params.items())
    status, body = await fetch(url, dict(params))
    if type(status) is not int or not 100 <= status <= 599 or type(body) is not bytes:
        calls.append(Exchange(url, sent, None, None, None, "invalid_fetch_result"))
        return LookupStatus.MALFORMED, None, None
    digest = hashlib.sha256(body).hexdigest()
    if len(body) > MAX_BODY_BYTES:
        calls.append(Exchange(url, sent, status, None, digest, "body_too_large"))
        return LookupStatus.MALFORMED, None, None
    calls.append(Exchange(url, sent, status, body, digest))
    return None, status, body


async def _tgn(filtered_name: str, fetch: Fetch, calls: list[Exchange]) -> HistoricalLookup:
    try:
        failure, status, body = await _request(
            tgn.RECONCILE, tgn.reconcile_params(filtered_name), fetch, calls
        )
    except SearchUnanswered as unanswered:
        return await _tgn_search(filtered_name, fetch, calls, unanswered.reason)
    if failure is not None:
        return _result(failure, calls)
    if status in SEARCH_REFUSALS:
        return await _tgn_search(
            filtered_name, fetch, calls, f"refused the request (HTTP {status})"
        )
    outcome, hits = _source_value(tgn.parse_reconcile, status, body)
    if outcome != LookupStatus.SUCCESS:
        return _result(outcome, calls)
    if len(hits) > tgn.LIMIT:
        return _result(LookupStatus.AMBIGUOUS, calls, reason="reconciliation exceeded hit limit")
    ids = tuple(dict.fromkeys(hit.id for hit in hits))
    failure, status, body = await _request(
        tgn.SPARQL, _source_value(tgn.records_params, ids), fetch, calls
    )
    if failure is not None:
        return _result(failure, calls)
    outcome, places = _source_value(tgn.parse_records, status, body)
    if outcome != LookupStatus.SUCCESS:
        return _later(outcome, calls, "record")
    returned = {place.record_id for place in places}
    if len(places) > tgn.LIMIT or returned - set(ids):
        return _result(LookupStatus.MALFORMED, calls, reason="records exceeded requested TGN ids")
    if returned != set(ids):
        return _result(LookupStatus.AMBIGUOUS, calls, reason="requested TGN records were incomplete")
    place_ids = tuple(place.record_id for place in places)
    failure, status, body = await _request(
        tgn.SPARQL, _source_value(tgn.names_params, place_ids), fetch, calls
    )
    if failure is not None:
        return _result(failure, calls)
    outcome, names = _source_value(tgn.parse_names, status, body)
    if outcome != LookupStatus.SUCCESS:
        return _later(outcome, calls, "name")
    if set(names) - set(place_ids):
        return _result(LookupStatus.MALFORMED, calls, reason="names exceeded requested TGN ids")
    return _result(LookupStatus.SUCCESS, calls, _source_value(tgn.with_names, places, names))


async def _tgn_search(
    filtered_name: str, fetch: Fetch, calls: list[Exchange], fallback: str
) -> HistoricalLookup:
    """Getty TGN's search through the SPARQL endpoint, once the reconciliation
    service refused the request or got no answer (`fallback` says which). The
    places come back as the reconciliation path returns them, in two more
    requests, so the chain stays within MAX_CALLS: one name search
    (tgn.SEARCH), which also returns every term of each place it finds, then
    the records of at most ten of those places (tgn.search_ids). A name
    search that finds no place is AMBIGUOUS (SPARQL_FOUND_NOTHING)."""
    try:
        result = await _tgn_sparql(filtered_name, fetch, calls)
    except _MalformedSource:
        result = _result(
            LookupStatus.MALFORMED, calls, reason="invalid source identifier or response"
        )
    return dataclasses.replace(result, fallback=fallback)


async def _tgn_sparql(
    filtered_name: str, fetch: Fetch, calls: list[Exchange]
) -> HistoricalLookup:
    failure, status, body = await _request(
        tgn.SPARQL, _source_value(tgn.search_params, filtered_name), fetch, calls
    )
    if failure is not None:
        return _result(failure, calls)
    outcome, found = _source_value(tgn.parse_search, status, body)
    if outcome == LookupStatus.NO_MATCH:
        return _result(LookupStatus.AMBIGUOUS, calls, reason=SPARQL_FOUND_NOTHING)
    if outcome != LookupStatus.SUCCESS:
        return _result(outcome, calls)
    ids = tgn.search_ids(filtered_name, found)
    failure, status, body = await _request(
        tgn.SPARQL, _source_value(tgn.records_params, ids), fetch, calls
    )
    if failure is not None:
        return _result(failure, calls)
    outcome, places = _source_value(tgn.parse_records, status, body)
    if outcome != LookupStatus.SUCCESS:
        return _later(outcome, calls, "record")
    returned = {place.record_id for place in places}
    if len(places) > tgn.LIMIT or returned - set(ids):
        return _result(LookupStatus.MALFORMED, calls, reason="records exceeded requested TGN ids")
    if returned != set(ids):
        return _result(LookupStatus.AMBIGUOUS, calls, reason="requested TGN records were incomplete")
    names = {record: found[record] for record in ids}
    return _result(LookupStatus.SUCCESS, calls, _source_value(tgn.with_names, places, names))


async def _wikidata(filtered_name: str, fetch: Fetch, calls: list[Exchange]) -> HistoricalLookup:
    failure, status, body = await _request(
        wikidata.API, wikidata.search_params(filtered_name), fetch, calls
    )
    if failure is not None:
        return _result(failure, calls)
    outcome, hits = _source_value(wikidata.parse_search, status, body)
    if outcome != LookupStatus.SUCCESS:
        return _result(outcome, calls)
    if len(hits) > wikidata.MAX_SEARCH:
        return _result(LookupStatus.AMBIGUOUS, calls, reason="search exceeded hit limit")
    ids = tuple(dict.fromkeys(hit.id for hit in hits))
    failure, status, body = await _request(
        wikidata.API, _source_value(wikidata.entities_params, ids), fetch, calls
    )
    if failure is not None:
        return _result(failure, calls)
    outcome, places = _source_value(wikidata.parse_entities, status, body)
    if outcome != LookupStatus.SUCCESS:
        return _later(outcome, calls, "entity")
    returned = {place.record_id for place in places}
    if len(places) > wikidata.MAX_SEARCH or returned - set(ids):
        return _result(
            LookupStatus.MALFORMED, calls, reason="entities exceeded requested Wikidata ids"
        )
    if returned != set(ids):
        return _result(
            LookupStatus.AMBIGUOUS, calls, reason="requested Wikidata entities were incomplete"
        )
    references = sorted(_source_value(wikidata.referenced_ids, places))
    if len(references) > wikidata.MAX_IDS:
        return _result(LookupStatus.AMBIGUOUS, calls, reason="reference ids exceeded call limit")
    if not references:
        return _result(LookupStatus.SUCCESS, calls, places)
    failure, status, body = await _request(
        wikidata.API, _source_value(wikidata.labels_params, references), fetch, calls
    )
    if failure is not None:
        return _result(failure, calls)
    outcome, labels = _source_value(wikidata.parse_labels, status, body)
    if outcome != LookupStatus.SUCCESS:
        return _later(outcome, calls, "label")
    if set(labels) - set(references):
        return _result(
            LookupStatus.MALFORMED, calls, reason="labels exceeded requested Wikidata ids"
        )
    if set(labels) != set(references):
        return _result(LookupStatus.AMBIGUOUS, calls, reason="requested Wikidata labels were incomplete")
    return _result(LookupStatus.SUCCESS, calls, _source_value(wikidata.name_refs, places, labels))


async def _nga(filtered_name: str, fetch: Fetch, calls: list[Exchange]) -> HistoricalLookup:
    failure, status, body = await _request(
        nga.NAMES, nga.search_params(filtered_name), fetch, calls
    )
    if failure is not None:
        return _result(failure, calls)
    outcome, ids = _source_value(nga.parse_search, status, body)
    if outcome != LookupStatus.SUCCESS:
        return _result(outcome, calls)
    if len(ids) > nga.MAX_IDS:
        return _result(LookupStatus.AMBIGUOUS, calls, reason="search exceeded feature limit")
    failure, status, body = await _request(
        nga.NAMES, _source_value(nga.features_params, ids), fetch, calls
    )
    if failure is not None:
        return _result(failure, calls)
    outcome, places = _source_value(nga.parse_features, status, body)
    if outcome != LookupStatus.SUCCESS:
        return _later(outcome, calls, "feature")
    returned = {place.record_id for place in places}
    if len(places) > nga.MAX_IDS or returned - set(ids):
        return _result(LookupStatus.MALFORMED, calls, reason="features exceeded requested GNS ids")
    if returned != set(ids):
        return _result(LookupStatus.AMBIGUOUS, calls, reason="requested GNS features were incomplete")
    codes = sorted(_source_value(nga.unit_codes, places))
    if len(codes) > nga.MAX_IDS:
        return _result(LookupStatus.AMBIGUOUS, calls, reason="unit codes exceeded call limit")
    if not codes:
        return _result(LookupStatus.SUCCESS, calls, places)
    failure, status, body = await _request(
        nga.UNITS, _source_value(nga.units_params, codes), fetch, calls
    )
    if failure is not None:
        return _result(failure, calls)
    outcome, units = _source_value(nga.parse_units, status, body)
    if outcome != LookupStatus.SUCCESS:
        return _later(outcome, calls, "unit")
    if set(units) - set(codes):
        return _result(LookupStatus.MALFORMED, calls, reason="units exceeded requested GNS codes")
    if set(units) != set(codes):
        return _result(LookupStatus.AMBIGUOUS, calls, reason="requested GNS units were incomplete")
    return _result(LookupStatus.SUCCESS, calls, _source_value(nga.name_units, places, units))
