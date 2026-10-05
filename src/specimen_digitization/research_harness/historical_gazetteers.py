"""Bounded tier-1 gazetteer orchestration for a qualified source dispatcher.

``filtered_name`` must be the output of the geography place-text filter. This
is an internal broker API, never a public model tool accepting raw label text.
The caller's ``fetch`` records each full response durably before returning it;
this module makes no network request, grants no source qualification, and does
not turn a historical candidate into a settled modern location.
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from specimen_digitization.application.domain import LookupStatus
from specimen_digitization.application.georef_places import Place
from specimen_digitization.application import georef_nga as nga
from specimen_digitization.application import georef_tgn as tgn
from specimen_digitization.application import georef_wikidata as wikidata

Fetch = Callable[[str, dict[str, str]], Awaitable[tuple[int, bytes]]]
MAX_CALLS = 3
MAX_BODY_BYTES = 2_000_000
SOURCES = frozenset({tgn.SOURCE, wikidata.SOURCE, nga.SOURCE})


@dataclass(frozen=True, slots=True)
class Exchange:
    """One attempted request, including response bytes for the caller's receipt."""

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


async def lookup(source_id: str, filtered_name: str, fetch: Fetch) -> HistoricalLookup:
    """Search one source by filtered place text, then read only its returned IDs.

    Every stage is capped and a non-success result ends the chain. The broker
    owns source registration, place-text filtering, durable fetch receipts,
    retries and the decision about whether a returned place is qualified.
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
    except (KeyError, OverflowError, TypeError, ValueError):
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


async def _request(
    url: str, params: dict[str, str], fetch: Fetch, calls: list[Exchange]
) -> tuple[LookupStatus | None, int | None, bytes | None]:
    if len(calls) >= MAX_CALLS:
        return LookupStatus.AMBIGUOUS, None, None
    sent = tuple(params.items())
    try:
        status, body = await fetch(url, dict(params))
    except TimeoutError:
        calls.append(Exchange(url, sent, None, None, None, "timeout"))
        return LookupStatus.TIMEOUT, None, None
    except Exception:
        calls.append(Exchange(url, sent, None, None, None, "fetch_error"))
        return LookupStatus.PROVIDER, None, None
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
    failure, status, body = await _request(
        tgn.RECONCILE, tgn.reconcile_params(filtered_name), fetch, calls
    )
    if failure is not None:
        return _result(failure, calls)
    outcome, hits = tgn.parse_reconcile(status, body)
    if outcome != LookupStatus.SUCCESS:
        return _result(outcome, calls)
    if len(hits) > tgn.LIMIT:
        return _result(LookupStatus.AMBIGUOUS, calls, reason="reconciliation exceeded hit limit")
    ids = tuple(dict.fromkeys(hit.id for hit in hits))
    failure, status, body = await _request(tgn.SPARQL, tgn.records_params(ids), fetch, calls)
    if failure is not None:
        return _result(failure, calls)
    outcome, places = tgn.parse_records(status, body)
    if outcome != LookupStatus.SUCCESS:
        return _result(outcome, calls)
    returned = {place.record_id for place in places}
    if len(places) > tgn.LIMIT or returned - set(ids):
        return _result(LookupStatus.MALFORMED, calls, reason="records exceeded requested TGN ids")
    if returned != set(ids):
        return _result(LookupStatus.AMBIGUOUS, calls, reason="requested TGN records were incomplete")
    place_ids = tuple(place.record_id for place in places)
    failure, status, body = await _request(tgn.SPARQL, tgn.names_params(place_ids), fetch, calls)
    if failure is not None:
        return _result(failure, calls)
    outcome, names = tgn.parse_names(status, body)
    if outcome != LookupStatus.SUCCESS:
        return _result(outcome, calls)
    if set(names) - set(place_ids):
        return _result(LookupStatus.MALFORMED, calls, reason="names exceeded requested TGN ids")
    return _result(LookupStatus.SUCCESS, calls, tgn.with_names(places, names))


async def _wikidata(filtered_name: str, fetch: Fetch, calls: list[Exchange]) -> HistoricalLookup:
    failure, status, body = await _request(
        wikidata.API, wikidata.search_params(filtered_name), fetch, calls
    )
    if failure is not None:
        return _result(failure, calls)
    outcome, hits = wikidata.parse_search(status, body)
    if outcome != LookupStatus.SUCCESS:
        return _result(outcome, calls)
    if len(hits) > wikidata.MAX_SEARCH:
        return _result(LookupStatus.AMBIGUOUS, calls, reason="search exceeded hit limit")
    ids = tuple(dict.fromkeys(hit.id for hit in hits))
    failure, status, body = await _request(
        wikidata.API, wikidata.entities_params(ids), fetch, calls
    )
    if failure is not None:
        return _result(failure, calls)
    outcome, places = wikidata.parse_entities(status, body)
    if outcome != LookupStatus.SUCCESS:
        return _result(outcome, calls)
    returned = {place.record_id for place in places}
    if len(places) > wikidata.MAX_SEARCH or returned - set(ids):
        return _result(
            LookupStatus.MALFORMED, calls, reason="entities exceeded requested Wikidata ids"
        )
    if returned != set(ids):
        return _result(
            LookupStatus.AMBIGUOUS, calls, reason="requested Wikidata entities were incomplete"
        )
    references = sorted(wikidata.referenced_ids(places))
    if len(references) > wikidata.MAX_IDS:
        return _result(LookupStatus.AMBIGUOUS, calls, reason="reference ids exceeded call limit")
    if not references:
        return _result(LookupStatus.SUCCESS, calls, places)
    failure, status, body = await _request(
        wikidata.API, wikidata.labels_params(references), fetch, calls
    )
    if failure is not None:
        return _result(failure, calls)
    outcome, labels = wikidata.parse_labels(status, body)
    if outcome != LookupStatus.SUCCESS:
        return _result(outcome, calls)
    if set(labels) - set(references):
        return _result(
            LookupStatus.MALFORMED, calls, reason="labels exceeded requested Wikidata ids"
        )
    if set(labels) != set(references):
        return _result(LookupStatus.AMBIGUOUS, calls, reason="requested Wikidata labels were incomplete")
    return _result(LookupStatus.SUCCESS, calls, wikidata.name_refs(places, labels))


async def _nga(filtered_name: str, fetch: Fetch, calls: list[Exchange]) -> HistoricalLookup:
    failure, status, body = await _request(
        nga.NAMES, nga.search_params(filtered_name), fetch, calls
    )
    if failure is not None:
        return _result(failure, calls)
    outcome, ids = nga.parse_search(status, body)
    if outcome != LookupStatus.SUCCESS:
        return _result(outcome, calls)
    if len(ids) > nga.MAX_IDS:
        return _result(LookupStatus.AMBIGUOUS, calls, reason="search exceeded feature limit")
    failure, status, body = await _request(nga.NAMES, nga.features_params(ids), fetch, calls)
    if failure is not None:
        return _result(failure, calls)
    outcome, places = nga.parse_features(status, body)
    if outcome != LookupStatus.SUCCESS:
        return _result(outcome, calls)
    returned = {place.record_id for place in places}
    if len(places) > nga.MAX_IDS or returned - set(ids):
        return _result(LookupStatus.MALFORMED, calls, reason="features exceeded requested GNS ids")
    if returned != set(ids):
        return _result(LookupStatus.AMBIGUOUS, calls, reason="requested GNS features were incomplete")
    codes = sorted(nga.unit_codes(places))
    if len(codes) > nga.MAX_IDS:
        return _result(LookupStatus.AMBIGUOUS, calls, reason="unit codes exceeded call limit")
    if not codes:
        return _result(LookupStatus.SUCCESS, calls, places)
    failure, status, body = await _request(nga.UNITS, nga.units_params(codes), fetch, calls)
    if failure is not None:
        return _result(failure, calls)
    outcome, units = nga.parse_units(status, body)
    if outcome != LookupStatus.SUCCESS:
        return _result(outcome, calls)
    if set(units) - set(codes):
        return _result(LookupStatus.MALFORMED, calls, reason="units exceeded requested GNS codes")
    if set(units) != set(codes):
        return _result(LookupStatus.AMBIGUOUS, calls, reason="requested GNS units were incomplete")
    return _result(LookupStatus.SUCCESS, calls, nga.name_units(places, units))
