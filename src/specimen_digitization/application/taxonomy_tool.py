"""The `taxonomy_verifier` harness tool (HARNESS.md section 6; G23, G25, G28).

GBIF species match v2 against the pinned COL XR checklist decides the outcome,
as GBIF.md 126-130 sets it with the coordinator's rulings of 22:46Z on
2026-09-25. Global Names Verifier and the Catalogue of Life API are asked too,
each recorded as its own source call; they support the evidence and never
change the outcome, and a disagreement with GBIF is a warning. BugGuide is not
called.
"""

from __future__ import annotations

import hashlib
import time
from typing import NamedTuple
from urllib.parse import quote

import httpx

from .domain import Lookup, LookupStatus, now
from .harness_tools import SourceCall, TaxonCandidate, ToolResult, with_retries
from .lookup import (
    GBIF_LICENSE,
    SYNONYM_STATUSES,
    GbifTaxonomy,
    no_name_lookup,
    parse_json,
    scientific_name,
)
from .reliability import retry_after

TOOL_VERSION = "taxonomy-verifier-v3"
GNV_URL = "https://verifier.globalnames.org/api/v1/verifications/"
# The Catalogue of Life release, pinned in the evidence (PRD 543): COL26.9,
# issued 2026-09-11, the release the `3LR` alias named on 2026-09-25.
COL_RELEASE = "316321"
COL_URL = f"https://api.checklistbank.org/dataset/{COL_RELEASE}/match/nameusage"
LICENSES = {
    "gbif": GBIF_LICENSE,
    "gnv": "CC BY 4.0 (Catalogue of Life and GBIF Backbone Taxonomy, via Global "
    "Names Verifier)",
    "col": "CC BY 4.0 (Catalogue of Life, COL26.9, 2026-09-11)",
}
# One deadline for the whole tool, half the default external step timeout;
# GBIF decides first, and the supporting sources get only the time left.
DEADLINE_SECONDS = 60
SUPPORT_MIN_SECONDS = 5
# A supporting source that answered; anything else is unavailable, not a disagreement.
ANSWERS = frozenset(
    {
        LookupStatus.SUCCESS,
        LookupStatus.NO_MATCH,
        LookupStatus.AMBIGUOUS,
        LookupStatus.EMPTY,
    }
)
# The match types Global Names Verifier documents; any other is malformed.
GNV_MATCH_TYPES = frozenset(
    {"NoMatch", "Exact", "Fuzzy", "PartialExact", "PartialFuzzy", "FacetedSearch", "Virus"}
)
# A body the fetch could not read whole or decode: malformed, never retried.
UNREADABLE = frozenset({"truncated", "unsupported_encoding"})
STATUSES = {
    401: LookupStatus.AUTHENTICATION,
    403: LookupStatus.AUTHORIZATION,
    429: LookupStatus.RATE_LIMITED,
}


class Verification(NamedTuple):
    result: ToolResult
    gbif: Lookup  # the deciding lookup, kept on the run for the policy engine


def query_name(literal: str) -> str | None:
    """The scientific name a taxon literal writes, as GBIF is asked for it
    (`lookup.scientific_name`), or None when it writes none."""
    parsed = scientific_name(literal)
    return parsed.query if parsed else None


def _get(url, params, client, timeout):
    """One bounded GET: (status code, body, Retry-After, failure code). A
    truncated body is `truncated`, and one in an encoding the fetch cannot read
    `unsupported_encoding`; the source call records either as malformed."""
    try:
        if client is not None:
            response = client.get(url, params=params, timeout=timeout)
            return (
                response.status_code,
                response.content,
                response.headers.get("Retry-After", ""),
                None,
            )
        from .http_effect import bounded_http

        captured = bounded_http(
            url, timeout_seconds=timeout, max_bytes=1024 * 1024, params=params
        )
        if captured["failure"]:
            return None, b"", "", captured["failure"]
        if captured["truncated"] or captured.get("unsupported_encoding"):
            failure = "truncated" if captured["truncated"] else "unsupported_encoding"
            return captured["status_code"], captured["body"], "", failure
        return captured["status_code"], captured["body"], captured["retry_after"], None
    except httpx.TimeoutException:
        return None, b"", "", "timeout"
    except httpx.HTTPError:
        return None, b"", "", "provider_error"


def _source_call(source, query, attempt, blobs, fetched, decide) -> SourceCall:
    status, body, retry, failure = fetched
    call = {
        "source": source,
        "query": query,
        "retrieved_at": now(),
        "attempt": attempt,
        "license": LICENSES[source],
    }
    if failure in UNREADABLE:
        # A body cut at the size limit, or in an encoding the fetch cannot
        # read, is malformed and not retried (HAR-009).
        return SourceCall(
            **call,
            outcome=LookupStatus.MALFORMED,
            raw_ref=blobs.put(body),
            response_sha256=hashlib.sha256(body).hexdigest(),
            sanitized_error=failure,
        )
    if failure or status != 200:
        outcome = (
            LookupStatus.TIMEOUT
            if failure == "timeout"
            else STATUSES.get(status, LookupStatus.PROVIDER)
        )
        return SourceCall(
            **call,
            outcome=outcome,
            retry_after_seconds=retry_after(retry),
            sanitized_error=failure or f"http_{status}",
        )
    error = None
    try:
        outcome = decide(parse_json(body))
    except (ValueError, TypeError, AttributeError, IndexError, KeyError, RecursionError):
        outcome, error = LookupStatus.MALFORMED, "malformed_response"
    return SourceCall(
        **call,
        outcome=outcome,
        raw_ref=blobs.put(body),
        response_sha256=hashlib.sha256(body).hexdigest(),
        sanitized_error=error,
    )


def _gnv_outcome(payload) -> LookupStatus:
    """GNV's answer, every field it reads typed: anything else is malformed,
    never a disagreement."""
    first = payload["names"][0]
    match = first["matchType"]
    best = first.get("bestResult")
    if not isinstance(match, str) or match not in GNV_MATCH_TYPES:
        raise ValueError("gnv_match_type")
    if best is None:
        best = {}
    if not isinstance(best, dict) or not isinstance(
        best.get("taxonomicStatus"), (str, type(None))
    ):
        raise ValueError("gnv_best_result")
    if match == "NoMatch":
        return LookupStatus.NO_MATCH
    if match == "Exact" and best.get("taxonomicStatus") == "Accepted":
        return LookupStatus.SUCCESS
    return LookupStatus.AMBIGUOUS


def _col_outcome(name):
    def decide(payload) -> LookupStatus:
        """COL's answer, every field it reads typed: anything else is
        malformed, never a disagreement."""
        match, kind, usage = payload.get("match"), payload.get("type"), payload.get("usage")
        if (
            not isinstance(match, bool)
            or not isinstance(kind, (str, type(None)))
            or not isinstance(usage, (dict, type(None)))
        ):
            raise ValueError("col_answer")
        usage = usage or {}
        if not all(
            isinstance(usage.get(field), (str, type(None))) for field in ("status", "name")
        ):
            raise ValueError("col_usage")
        if kind == "none" or not match:
            return LookupStatus.NO_MATCH
        if usage.get("status") == "accepted" and usage.get("name") == name:
            return LookupStatus.SUCCESS
        return LookupStatus.AMBIGUOUS

    return decide


def _gbif_taxa(lookup: Lookup) -> list[TaxonCandidate]:
    """GBIF's usages, the settled one first: for a cleared exact synonym, its
    accepted usage and then the synonym, which names it (GBIF.md 127)."""
    accepted = (lookup.metadata or {}).get("accepted_usage")
    accepted_key = (
        str(accepted["key"]) if isinstance(accepted, dict) and accepted.get("key") else None
    )
    return [
        TaxonCandidate(
            source="gbif",
            usage_key=str(usage["key"]),
            name=usage.get("name") or "",
            canonical_name=usage.get("canonicalName"),
            authorship=usage.get("authorship"),
            rank=usage.get("rank"),
            status=usage.get("status"),
            accepted_usage_key=(
                accepted_key if usage.get("status") in SYNONYM_STATUSES else None
            ),
        )
        for usage in lookup.candidates
        # Alternatives stay in the lookup's evidence.
        if isinstance(usage, dict) and "diagnostics" not in usage and usage.get("key")
    ]


def verify_taxon(
    literal: str,
    *,
    blobs,
    client: httpx.Client | None = None,
    sleep=time.sleep,
    clock=time.monotonic,
    deadline_seconds: float = DEADLINE_SECONDS,
) -> Verification:
    """Verify the scientific name in a taxon literal (G23)."""
    parsed = scientific_name(literal)
    if parsed is None:
        return Verification(
            ToolResult(
                tool="taxonomy_verifier",
                tool_version=TOOL_VERSION,
                outcome=LookupStatus.NO_MATCH,
                warnings=["no_scientific_name"],
            ),
            no_name_lookup(literal),
        )
    end = clock() + deadline_seconds
    gbif, lookups = GbifTaxonomy(blobs, client), []

    def left() -> float:
        return max(0.1, min(20.0, end - clock()))

    def gbif_call(attempt: int) -> SourceCall:
        lookups.append(gbif.lookup(parsed, timeout=left()))
        found = lookups[-1]
        return SourceCall(
            source="gbif",
            query=found.query,
            retrieved_at=found.retrieved_at,
            outcome=found.status,
            attempt=attempt,
            raw_ref=found.raw_ref,
            response_sha256=found.digest,
            license=LICENSES["gbif"],
            retry_after_seconds=found.retry_after_seconds,
            sanitized_error=None if found.status in ANSWERS else found.status.value,
        )

    calls = with_retries(gbif_call, sleep=sleep, deadline=end, clock=clock)
    name = parsed.canonical  # The supporting sources get the name alone.
    support = []
    for source, url, params, query, decide in (
        (
            "gnv",
            GNV_URL + quote(name),
            {"data_sources": "1|11"},
            {"name": name, "data_sources": "1|11"},
            _gnv_outcome,
        ),
        ("col", COL_URL, {"q": name}, {"q": name, "dataset": COL_RELEASE}, _col_outcome(name)),
    ):
        if end - clock() < SUPPORT_MIN_SECONDS:
            support.append(
                [
                    SourceCall(
                        source=source,
                        query=query,
                        retrieved_at=now(),
                        outcome=LookupStatus.TIMEOUT,
                        license=LICENSES[source],
                        sanitized_error="tool_deadline",
                    )
                ]
            )
            continue
        support.append(
            with_retries(
                lambda attempt, source=source, url=url, params=params, query=query, decide=decide: (
                    _source_call(
                        source,
                        query,
                        attempt,
                        blobs,
                        _get(url, params, client, left()),
                        decide,
                    )
                ),
                sleep=sleep,
                deadline=end,
                clock=clock,
            )
        )
    gnv, col = support
    decided = lookups[-1]
    # A name read only in part never succeeds (section 6).
    warnings = ["taxonomy_name_partly_read"] if parsed.partly_read else []
    for final in (gnv[-1], col[-1]):
        if final.outcome not in ANSWERS:
            warnings.append(f"taxonomy_support_unavailable:{final.source}")
        elif decided.status in ANSWERS and (final.outcome == LookupStatus.SUCCESS) != (
            decided.status == LookupStatus.SUCCESS
        ):
            # A disagreement needs GBIF's answer to disagree with.
            warnings.append(f"taxonomy_source_disagreement:{final.source}")
    return Verification(
        ToolResult(
            tool="taxonomy_verifier",
            tool_version=TOOL_VERSION,
            outcome=decided.status,
            taxa=_gbif_taxa(decided),
            sub_calls=[*calls, *gnv, *col],
            warnings=warnings,
        ),
        decided,
    )
