"""The `taxonomy_verifier` harness tool (HARNESS.md section 6; G23, G25, G28).

GBIF species match v2 against the pinned COL XR checklist decides the outcome,
as GBIF.md 118-130 sets it. Global Names Verifier and the Catalogue of Life
API are asked too, each recorded as its own source call; they support the
evidence and never change the outcome, and a disagreement with GBIF is a
warning. BugGuide is not called.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import NamedTuple
from urllib.parse import quote

import httpx

from .domain import Lookup, LookupStatus, now
from .harness_tools import SourceCall, TaxonCandidate, ToolResult, with_retries
from .lookup import GbifTaxonomy
from .reliability import retry_after

TOOL_VERSION = "taxonomy-verifier-v1"
GNV_URL = "https://verifier.globalnames.org/api/v1/verifications/"
COL_URL = "https://api.checklistbank.org/dataset/3LR/match/nameusage"
QUALIFIERS = frozenset({"sp", "spp", "ssp", "cf", "aff", "nr", "near", "var"})
# A supporting source that answered; anything else is unavailable, not a disagreement.
ANSWERS = frozenset(
    {
        LookupStatus.SUCCESS,
        LookupStatus.NO_MATCH,
        LookupStatus.AMBIGUOUS,
        LookupStatus.EMPTY,
    }
)
STATUSES = {
    401: LookupStatus.AUTHENTICATION,
    403: LookupStatus.AUTHORIZATION,
    429: LookupStatus.RATE_LIMITED,
}


class Verification(NamedTuple):
    result: ToolResult
    gbif: Lookup  # the deciding lookup, kept on the run for the policy engine


def query_name(literal: str) -> str | None:
    """The scientific name in a taxon literal: its first capitalized word and
    the lower-case epithets after it, ending at a qualifier ("sp. 1") or any
    other word. Every word comes from the literal; nothing is added."""
    words = literal.split()
    start = next(
        (
            i
            for i, word in enumerate(words)
            if word.isalpha() and word[0].isupper() and word.lower() not in QUALIFIERS
        ),
        None,
    )
    if start is None:
        return None
    name = [words[start]]
    for word in words[start + 1 :]:
        bare = word.rstrip(".")
        if not bare.isalpha() or not bare.islower() or bare in QUALIFIERS:
            break
        name.append(word)
    return " ".join(name)


def _get(url, params, client):
    """One bounded GET: (status code, body, Retry-After, failure code)."""
    try:
        if client is not None:
            response = client.get(url, params=params, timeout=20)
            return (
                response.status_code,
                response.content,
                response.headers.get("Retry-After", ""),
                None,
            )
        from .http_effect import bounded_http

        captured = bounded_http(
            url, timeout_seconds=20, max_bytes=1024 * 1024, params=params
        )
        if captured["failure"] or captured["truncated"]:
            return None, b"", "", captured["failure"] or "truncated"
        return captured["status_code"], captured["body"], captured["retry_after"], None
    except httpx.TimeoutException:
        return None, b"", "", "timeout"
    except httpx.HTTPError:
        return None, b"", "", "provider_error"


def _source_call(source, query, attempt, blobs, fetched, decide) -> SourceCall:
    status, body, retry, failure = fetched
    call = {"source": source, "query": query, "retrieved_at": now(), "attempt": attempt}
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
    try:
        outcome = decide(json.loads(body))
    except (ValueError, TypeError, AttributeError, IndexError, KeyError):
        outcome = LookupStatus.MALFORMED
    return SourceCall(
        **call,
        outcome=outcome,
        raw_ref=blobs.put(body),
        response_sha256=hashlib.sha256(body).hexdigest(),
    )


def _gnv_outcome(payload) -> LookupStatus:
    first = payload["names"][0]
    match = first["matchType"]
    if match == "NoMatch":
        return LookupStatus.NO_MATCH
    best = first.get("bestResult") or {}
    if match == "Exact" and best.get("taxonomicStatus") == "Accepted":
        return LookupStatus.SUCCESS
    return LookupStatus.AMBIGUOUS


def _col_outcome(name):
    def decide(payload) -> LookupStatus:
        usage = payload.get("usage") or {}
        if payload.get("type") == "none" or not payload.get("match"):
            return LookupStatus.NO_MATCH
        if usage.get("status") == "accepted" and usage.get("name") == name:
            return LookupStatus.SUCCESS
        return LookupStatus.AMBIGUOUS

    return decide


def _gbif_taxa(lookup: Lookup) -> list[TaxonCandidate]:
    usage = next(iter(lookup.candidates), None)
    if not isinstance(usage, dict) or not usage.get("key"):
        return []
    accepted = (lookup.metadata or {}).get("accepted_usage") or {}
    return [
        TaxonCandidate(
            source="gbif",
            usage_key=str(usage["key"]),
            name=usage.get("name") or "",
            canonical_name=usage.get("canonicalName"),
            authorship=usage.get("authorship"),
            rank=usage.get("rank"),
            status=usage.get("status"),
            accepted_usage_key=str(accepted["key"]) if accepted.get("key") else None,
        )
    ]


def verify_taxon(
    literal: str, *, blobs, client: httpx.Client | None = None, sleep=time.sleep
) -> Verification:
    """Verify the scientific name in a taxon literal (G23)."""
    name = query_name(literal)
    gbif, lookups = GbifTaxonomy(blobs, client), []

    def gbif_call(attempt: int) -> SourceCall:
        lookups.append(gbif.lookup(name))
        found = lookups[-1]
        return SourceCall(
            source="gbif",
            query=found.query,
            retrieved_at=found.retrieved_at,
            outcome=found.status,
            attempt=attempt,
            raw_ref=found.raw_ref,
            response_sha256=found.digest,
            retry_after_seconds=found.retry_after_seconds,
        )

    if name is None:
        empty = Lookup(
            provider="gbif",
            adapter_version="species-match-v2.1",
            query={"scientificName": literal},
            status=LookupStatus.NO_MATCH,
        )
        return Verification(
            ToolResult(
                tool="taxonomy_verifier",
                tool_version=TOOL_VERSION,
                outcome=LookupStatus.NO_MATCH,
                warnings=["no_scientific_name"],
            ),
            empty,
        )
    calls = with_retries(gbif_call, sleep=sleep)
    gnv = with_retries(
        lambda attempt: _source_call(
            "gnv",
            {"name": name, "data_sources": "1|11"},
            attempt,
            blobs,
            _get(GNV_URL + quote(name), {"data_sources": "1|11"}, client),
            _gnv_outcome,
        ),
        sleep=sleep,
    )
    col = with_retries(
        lambda attempt: _source_call(
            "col",
            {"q": name, "dataset": "3LR"},
            attempt,
            blobs,
            _get(COL_URL, {"q": name}, client),
            _col_outcome(name),
        ),
        sleep=sleep,
    )
    decided = lookups[-1]
    warnings = []
    for final in (gnv[-1], col[-1]):
        if final.outcome not in ANSWERS:
            warnings.append(f"taxonomy_support_unavailable:{final.source}")
        elif (final.outcome == LookupStatus.SUCCESS) != (
            decided.status == LookupStatus.SUCCESS
        ):
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
