"""The harness's `geography_lookup` tool on the Google Geocoding API (G10).

What a request carries passes PLAN 4.8's place-request filter first
(`place_text`, HARNESS.md section 7): nothing else leaves, and a query the
filter refuses, or leaves nothing of, sends no request.

Google's terms let us keep only its place ID (G26): each attempt stores the place
ID, our outcome and a sha256 fingerprint of the full response. Google's names,
address components and coordinates are read in memory to compute outcomes and are
never returned, stored or logged; the key is redacted from httpx's request logs.
Label notations such as "Prov." are dropped before comparing, and aliases the
harness supplies count as matches (G29). precise_location only helps form the
address: it is verbatim text that no geocoder result settles (PRD 519). An
accepted S8 plan replaces this module (G12).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import nullcontext
from functools import partial
from types import MappingProxyType

import httpx

from .domain import OPERATIONAL, LookupStatus, now
from .harness_knowledge import KNOWLEDGE
from .harness_tools import (
    RETRYABLE,
    GeographyQuery,
    PlaceCandidate,
    SourceCall,
    ToolResult,
    with_retries,
)
from .place_text import PLACE_FIELDS, ReviewerValue, fold, place_request_text
from .reliability import retry_after
from .storage import BlobStore

TOOL_VERSION = "google-geocoding-v3"  # v3: PLAN 4.8's filter (HARNESS.md 7).
GEOCODING_URL = "https://maps.googleapis.com/maps/api/geocode/json"
GEOCODING_COST_MICROS = 5000  # Reserved per request, before it is sent.
KEY_VARIABLE = "SPECIMEN_GOOGLE_MAPS_API_KEY"
SOURCE = "google-maps-geocoding"  # Pinned by the data contract (#88, rule 1.6).
# Assigned literals form the address from the most to the least precise field.
ADDRESS_ORDER = ("precise_location", "city", "county", "province_state", "country")
# The Google address component types that can confirm each field.
LEVELS = {
    "country": frozenset({"country"}),
    "province_state": frozenset(
        {"administrative_area_level_1", "administrative_area_level_2"}
    ),
    "county": frozenset({"administrative_area_level_2", "administrative_area_level_3"}),
    "city": frozenset(
        {"locality", "postal_town", "administrative_area_level_3", "sublocality"}
    ),
}
# Label notations dropped as whole words before comparing (G29).
# Names compare as S8's place tool compares them (agreed with S8, 2026-09-23):
# unit words written after the name ("Davao Prov.") or before it ("Mun.
# Yepocapa"), a link word after a leading one, and feature notations (G29).
UNIT_WORDS = frozenset(
    {
        *("prov", "province", "dept", "department", "co", "county", "state"),
        *("region", "mun", "municipio", "municipality", "depto", "departamento"),
        *("provincia", "estado"),
    }
)
LINKS = frozenset({"de", "del", "of"})
FEATURES = {"mt": "mount"}
NO_ALIASES: Mapping[str, Sequence[str]] = MappingProxyType({})
# Google's statuses besides OK; INVALID_REQUEST and any other are malformed.
STATUSES = {
    "ZERO_RESULTS": LookupStatus.NO_MATCH,
    "OVER_QUERY_LIMIT": LookupStatus.RATE_LIMITED,
    "OVER_DAILY_LIMIT": LookupStatus.AUTHENTICATION,
    "REQUEST_DENIED": LookupStatus.AUTHENTICATION,
    "UNKNOWN_ERROR": LookupStatus.PROVIDER,
}
# HTTP answers besides 200; any other is a provider error.
HTTP_STATUSES = {
    401: LookupStatus.AUTHENTICATION,
    403: LookupStatus.AUTHORIZATION,
    429: LookupStatus.RATE_LIMITED,
}
KEY_IN_LOGS = re.compile(r"\bkey=[^&#\s\"']*", re.IGNORECASE)


class RedactMapsKey(logging.Filter):
    """Rewrites `key=<value>` to `key=[redacted]` in `httpx` log records: httpx
    logs every request URL at INFO, and the Geocoding key travels in the URL."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except (TypeError, ValueError, KeyError):
            return True  # A malformed logging call; logging reports it itself.
        redacted = KEY_IN_LOGS.sub("key=[redacted]", message)
        if redacted != message:
            record.msg, record.args = redacted, ()
        return True


def install_key_redaction() -> None:
    """Add the filter to the `httpx` logger once, however often this runs; it
    compares class names, so a reloaded module does not add a second one."""
    httpx_logger = logging.getLogger("httpx")
    installed = {type(f).__name__ for f in httpx_logger.filters}
    if RedactMapsKey.__name__ not in installed:
        httpx_logger.addFilter(RedactMapsKey())


install_key_redaction()


def comparison_key(name: str) -> str:
    """The key names compare by (G29): folded, feature notations read ("Mt." is
    "mount"), unit words dropped, with a link word after a leading one."""
    kept: list[str] = []
    after_unit = False
    for word in fold(name).split():
        word = FEATURES.get(word, word)
        if word in UNIT_WORDS:
            after_unit = not kept
        elif after_unit and word in LINKS:
            after_unit = False
        else:
            after_unit = False
            kept.append(word)
    return " ".join(kept)


def one_letter_apart(literal: str, name: str) -> bool:
    """G34's gate on two names: both full names, keys exactly one letter apart."""
    return (
        _full_name(literal)
        and _full_name(name)
        and _letters_apart(comparison_key(literal), comparison_key(name)) == 1
    )


def assigned_literals(query: GeographyQuery) -> dict[str, list[str]]:
    """Each assigned field's literals, in the order the query gives them."""
    fields: dict[str, list[str]] = {}
    for item in query.literals:
        if item.field_key is not None:
            fields.setdefault(item.field_key, []).append(item.literal)
    return fields


def reported_literals(query: GeographyQuery) -> dict[str, list[str]]:
    """The assigned fields the tool reports on: all but precise_location, which
    stays verbatim locality text that no geocoder result settles (PRD 519;
    where such a phrase is waits for S8's D3)."""
    fields = assigned_literals(query)
    fields.pop("precise_location", None)
    return fields


def geocoding_address(query: GeographyQuery) -> tuple[str, str | None]:
    """The address PLAN 4.8 lets leave, or the fixed code refusing the query.
    Every literal, the unassigned locality text's too, must be character for
    character in a reading, except a place value the reviewer entered or
    changed in "fill the rest", a source though no reading holds it. The
    query's sources go to the filter with the readings as its context (4.8 in
    #191); a non-place field's literal is never a source and refuses the query.
    Each value is cut with its own lists: a reviewer's with `reviewer`, so the
    reviewer's own non-place values alone cut the reviewer's own text (#208's
    security review). Google's row of 4.8 sends a literal with its reading's
    place fields, so the address is the place-field literals from the most to
    the least precise field, each as written after the cuts, and never the
    unassigned text."""
    knowledge = KNOWLEDGE.get(query.knowledge_id or "")
    if knowledge is None:
        return "", "place_knowledge_unavailable"
    sent: dict[str, list[str]] = {}
    for item in query.literals:
        reviewer = None
        if item.reviewer:
            reviewer = ReviewerValue(
                anchors=item.anchors,
                non_place_literals=query.reviewer_non_place_literals,
            )
        elif not any(item.literal in reading for reading in query.reading_texts):
            return "", "place_text_refused"
        elif item.field_key is None:
            continue  # Unassigned text: a source for S8's tiers, never sent.
        if item.field_key not in PLACE_FIELDS:
            return "", "place_text_refused"
        text = place_request_text(
            item.literal,
            sources=query.sources,
            non_place_literals=query.non_place_literals,
            knowledge=knowledge,
            readings=query.reading_texts,
            reviewer=reviewer,
        )
        if text is None:
            return "", "place_text_refused"
        if text:
            sent.setdefault(item.field_key, []).append(text)
    return ", ".join(text for key in ADDRESS_ORDER for text in sent.get(key, [])), None


def map_geocoding_response(
    query: GeographyQuery,
    http_status: int,
    payload: object,
    aliases: Mapping[str, Sequence[str]] = NO_ALIASES,
) -> tuple[LookupStatus, dict[str, LookupStatus], list[PlaceCandidate], list[str]]:
    """Map one Geocoding response to our outcomes and warnings (G10). The whole
    mapping is this function, because owner decisions change only it.
    `payload` is the parsed JSON body, None when it did not parse; `aliases`
    maps a folded literal to more folded names that count as matches (G29).
    Google's names are compared here in memory; only outcomes and the place
    ID leave (G26)."""
    fields = reported_literals(query)
    body = payload if isinstance(payload, dict) else {}
    status, results = body.get("status"), body.get("results")
    if http_status != 200:
        outcome = HTTP_STATUSES.get(http_status, LookupStatus.PROVIDER)
    elif status != "OK":
        # str(): the status may be any JSON value, hashable or not.
        outcome = STATUSES.get(str(status), LookupStatus.MALFORMED)
    elif not (isinstance(results, list) and results and all(map(_place_id, results))):
        outcome = LookupStatus.MALFORMED
    elif len(results) > 1 or results[0].get("partial_match"):
        outcome = LookupStatus.AMBIGUOUS
    else:
        outcome = LookupStatus.SUCCESS
    if outcome != LookupStatus.SUCCESS:
        return outcome, dict.fromkeys(fields, outcome), [], []
    result, table = results[0], _alias_table(aliases)
    outcomes = {
        key: _confirmed(key, texts, result, table) for key, texts in fields.items()
    }
    # G34: a field no name matches clears on a near spelling, with the place ID
    # and no name, only when every other admin field, at least one, matched by
    # name or alias and one component alone is within one edit of its literal.
    matched = {key for key, value in outcomes.items() if value == LookupStatus.SUCCESS}
    near = [
        key
        for key, value in outcomes.items()
        if value == LookupStatus.NO_MATCH
        and matched
        and matched == set(outcomes) - {key}
        and _near_spelling(key, fields[key], result)
    ]
    outcomes.update(dict.fromkeys(near, LookupStatus.SUCCESS))
    places = [
        PlaceCandidate(
            field_key=key, source=SOURCE, source_record_id=result["place_id"]
        )
        for key, value in outcomes.items()
        if value == LookupStatus.SUCCESS
    ]
    return outcome, outcomes, places, [f"near_spelling:{key}" for key in near]


def _confirmed(
    key: str, texts: list[str], result: dict, aliases: dict[str, set[str]]
) -> LookupStatus:
    """SUCCESS when every literal of the field, folded or through an alias,
    equals the folded long or short name of a component at one of the field's
    levels; an empty fold never matches."""
    names = {comparison_key(name) for names in _names_at(key, result) for name in names}

    def accepted(text: str) -> set[str]:
        folded = comparison_key(text)
        return {folded, *aliases.get(folded, ())} if folded else set()

    matched = all(not names.isdisjoint(accepted(text)) for text in texts)
    return LookupStatus.SUCCESS if matched else LookupStatus.NO_MATCH


def _names_at(
    key: str, result: dict, kinds: Sequence[str] = ("long_name", "short_name")
) -> list[set[str]]:
    """The names of each component at the field's levels, as Google gives them."""
    levels, components = LEVELS.get(key, frozenset()), []
    parts = result.get("address_components")
    for part in parts if isinstance(parts, list) else []:
        types = part.get("types") if isinstance(part, dict) else None
        if isinstance(types, list) and levels.intersection(map(str, types)):
            labels = [part.get(kind) for kind in kinds]
            components.append({x for x in labels if isinstance(x, str) and fold(x)})
    return components


def _near_spelling(key: str, texts: list[str], result: dict) -> bool:
    """Exactly one component at the field's levels has a long name one letter
    from every literal of the field, both full names (G34). Never a short name:
    a code such as "PH" is not a name, and "P.I." is not a full one."""
    near = [
        names
        for names in _names_at(key, result, ("long_name",))
        if all(any(one_letter_apart(text, name) for name in names) for text in texts)
    ]
    return len(near) == 1


def _letters_apart(a: str, b: str, cap: int = 2) -> int:
    """Single-character insertions, deletions and substitutions between two
    keys, counted up to `cap`."""
    if a == b:
        return 0
    if abs(len(a) - len(b)) >= cap:
        return cap
    previous = list(range(len(b) + 1))
    for i, left in enumerate(a, 1):
        current = [i]
        for j, right in enumerate(b, 1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (left != right),
                )
            )
        if min(current) >= cap:
            return cap
        previous = current
    return min(previous[-1], cap)


def _full_name(name: str) -> bool:
    """Every word a notation or a full word, and some word not a notation: no
    period inside a word, no period after four letters or fewer, no digit, and
    not three capitals or fewer ("PH", "PHL", "RP")."""
    words = [word.strip(",;:") for word in name.split()]
    names = [word for word in words if not _notation(word)]
    return bool(names) and all(_full_word(word) for word in names)


def _notation(word: str) -> bool:
    folded = fold(word)
    return folded in FEATURES or folded in UNIT_WORDS or folded == "mount"


def _full_word(word: str) -> bool:
    letters = sum(c.isalpha() for c in word)
    if any(c.isdigit() for c in word) or re.search(r"\.\w", word):
        return False
    if word.endswith(".") and letters <= 4:
        return False
    return not (word.isupper() and letters <= 3)


def _alias_table(aliases: Mapping[str, Sequence[str]]) -> dict[str, set[str]]:
    """The aliases keyed like the literals and names they meet; a bare string
    is one name, not a sequence of letters, and an empty key names nothing."""
    table: dict[str, set[str]] = {}
    for literal, names in aliases.items():
        extra = [names] if isinstance(names, str) else names
        table.setdefault(comparison_key(literal), set()).update(
            filter(None, map(comparison_key, extra))
        )
    return table


def _place_id(result: object) -> str | None:
    """The result's place ID, the one Google value we may keep (G26)."""
    place_id = result.get("place_id") if isinstance(result, dict) else None
    return place_id if isinstance(place_id, str) and place_id else None


def geocode_locality(
    query: GeographyQuery,
    *,
    blobs: BlobStore,
    api_key: str | None = None,
    client: httpx.Client | None = None,
    reserve_cost: Callable[[int], bool] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    aliases: Mapping[str, Sequence[str]] = NO_ALIASES,
) -> ToolResult:
    """Look a locality up on Google (G10) with bounded retries (HAR-009),
    recording every attempt as place ID, outcome and fingerprint only (G26).
    `aliases` come from the harness's profile knowledge (G29); the tool holds
    no table of its own."""
    address, refused = geocoding_address(query)
    if refused or not address:
        # Nothing leaves (PLAN 4.8), so no source call is recorded: a refused
        # query blocks the run; with nothing to ask, no field is found
        # (the coordinator's ruling of 2026-09-24).
        outcome = LookupStatus.POLICY if refused else LookupStatus.NO_MATCH
        return ToolResult(
            tool="geography_lookup",
            tool_version=TOOL_VERSION,
            outcome=outcome,
            field_outcomes=dict.fromkeys(reported_literals(query), outcome),
            warnings=[refused or "place_text_empty"],
        )
    key = os.environ.get(KEY_VARIABLE) if api_key is None else api_key
    mapped: dict[
        int, tuple[dict[str, LookupStatus], list[PlaceCandidate], list[str]]
    ] = {}

    def call(
        number: int, outcome: LookupStatus, error: str | None = None, **fields
    ) -> SourceCall:
        """One source call; `error` is a fixed code, never Google's text."""
        return SourceCall(
            source=SOURCE,
            query={"address": address},  # Never the key.
            retrieved_at=now(),
            attempt=number,
            outcome=outcome,
            sanitized_error=error,
            **fields,
        )

    def attempt(http: httpx.Client, number: int) -> SourceCall:
        if reserve_cost is not None and not reserve_cost(GEOCODING_COST_MICROS):
            return call(number, LookupStatus.POLICY, "cost_budget_exhausted")
        params = {"address": address, "key": key}
        try:
            response = http.get(GEOCODING_URL, params=params, timeout=10)
        except httpx.TimeoutException:
            return call(number, LookupStatus.TIMEOUT, "geocoding_timeout")
        except httpx.HTTPError:
            return call(number, LookupStatus.PROVIDER, "geocoding_transport_error")
        except Exception:  # noqa: BLE001 - deliberate, see below.
            # Its text may quote the request URL and with it the key, so only
            # a fixed code leaves (httpx.InvalidURL is outside HTTPError).
            return call(number, LookupStatus.PROVIDER, "geocoding_unexpected_error")
        code = response.status_code
        try:
            payload = json.loads(response.content) if code == 200 else None
        except (ValueError, RecursionError):
            payload = None
        outcome, fields, places, warnings = map_geocoding_response(
            query, code, payload, aliases
        )
        mapped[number] = (fields, places, warnings)
        results = payload.get("results") if isinstance(payload, dict) else None
        first = results[0] if isinstance(results, list) and results else None
        digest = hashlib.sha256(response.content).hexdigest()
        record = {  # Exactly what G26 lets us keep; never the response itself.
            "place_id": _place_id(first),
            "outcome": outcome.value,
            "response_sha256": digest,
        }
        if code != 200:
            error = f"geocoding_http_{code}"
        else:
            error = f"geocoding_{outcome.value}" if outcome in OPERATIONAL else None
        wait = response.headers.get("Retry-After") if outcome in RETRYABLE else None
        return call(
            number,
            outcome,
            error,
            raw_ref=blobs.put(json.dumps(record, sort_keys=True).encode()),
            response_sha256=digest,
            retry_after_seconds=retry_after(wait),
        )

    if not (key and key.strip()):
        calls = [call(1, LookupStatus.AUTHENTICATION, "maps_key_not_configured")]
    else:
        with httpx.Client() if client is None else nullcontext(client) as http:
            calls = with_retries(partial(attempt, http), sleep=sleep)
    final = calls[-1]
    everywhere = dict.fromkeys(reported_literals(query), final.outcome)
    fields, places, warnings = mapped.get(final.attempt, (everywhere, [], []))
    return ToolResult(
        tool="geography_lookup",
        tool_version=TOOL_VERSION,
        outcome=final.outcome,
        field_outcomes=fields,
        places=places,
        sub_calls=calls,
        warnings=warnings,
    )
