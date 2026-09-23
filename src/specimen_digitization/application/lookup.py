"""Bounded, read-only GBIF COL XR name matching with typed failure fidelity."""

import hashlib
import time
import httpx
from .domain import Lookup, LookupStatus
from .storage import BlobStore
from .reliability import retry_after

COL_XR = "7ddf754f-d193-4cc9-b351-99906754a03b"
# GBIF.md 118-130 as HARNESS.md section 6 applies it: a match type GBIF
# documents is never malformed, and only row 1 at the label's own rank succeeds.
GBIF_MATCH_TYPES = frozenset({"EXACT", "FUZZY", "VARIANT", "HIGHERRANK"})
LIVE_STATUSES = frozenset({"ACCEPTED", "PROVISIONALLY_ACCEPTED", "DOUBTFUL"})
QUALIFIERS = frozenset({"sp", "spp", "ssp", "cf", "aff", "nr", "near", "var"})


def label_rank(name: str) -> str:
    """The rank a label's name gives: a genus alone is genus rank (G25), one
    lower-case epithet a species, two a subspecies."""
    epithets = 0
    for word in name.split()[1:]:
        bare = word.rstrip(".")
        if not bare.isalpha() or not bare.islower() or bare in QUALIFIERS:
            break
        epithets += 1
    return ("GENUS", "SPECIES", "SUBSPECIES")[min(epithets, 2)]


def supported_match(name, usage, classification, alternatives) -> bool:
    """Row 1: an accepted usage in class Insecta at the label's own rank, with
    no plausible alternative (row 4: another exact, live usage of the same name
    with other authorship, a homonym). An exact synonym (row 2) is not."""
    if usage.get("status") != "ACCEPTED" or usage.get("rank") != label_rank(name):
        return False
    if not any(
        isinstance(c, dict) and c.get("rank") == "CLASS" and c.get("name") == "Insecta"
        for c in classification or []
    ):
        return False
    return not any(
        isinstance(other, dict)
        and (other.get("diagnostics") or {}).get("matchType") == "EXACT"
        and (other.get("usage") or {}).get("status") in LIVE_STATUSES
        and (other.get("usage") or {}).get("name") != usage.get("name")
        for other in alternatives or []
    )


class GbifTaxonomy:
    def __init__(self, blobs: BlobStore, client: httpx.Client | None = None):
        self.blobs = blobs
        self.client = client

    def lookup(self, name: str) -> Lookup:
        query = {
            "scientificName": name,
            "kingdom": "Animalia",
            "class": "Insecta",
            "checklistKey": COL_XR,
            "verbose": "true",
        }
        result = Lookup(
            provider="gbif",
            adapter_version="species-match-v2.1",
            query=query,
            status=LookupStatus.PROVIDER,
        )
        deadline = time.monotonic() + 20
        try:
            if self.client is None:
                from .http_effect import bounded_http

                captured = bounded_http(
                    "https://api.gbif.org/v2/species/match",
                    timeout_seconds=20,
                    max_bytes=1024 * 1024,
                    params=query,
                )
                if captured["failure"]:
                    result.status = (
                        LookupStatus.TIMEOUT
                        if captured["failure"] == "timeout"
                        else LookupStatus.PROVIDER
                    )
                    return result
                response = httpx.Response(
                    captured["status_code"],
                    content=captured["body"],
                    headers={"Retry-After": captured["retry_after"]},
                )
                if captured["truncated"] or captured.get("unsupported_encoding"):
                    result.raw_ref = self.blobs.put(captured["body"])
                    result.digest = hashlib.sha256(captured["body"]).hexdigest()
                    result.status = LookupStatus.MALFORMED
                    result.metadata = {
                        "truncated": captured["truncated"],
                        "unsupported_encoding": captured.get(
                            "unsupported_encoding", False
                        ),
                    }
                    return result
            else:
                response = self.client.get(
                    "https://api.gbif.org/v2/species/match", params=query
                )
            result.raw_ref = self.blobs.put(response.content)
            result.digest = hashlib.sha256(response.content).hexdigest()
            statuses = {
                401: LookupStatus.AUTHENTICATION,
                403: LookupStatus.AUTHORIZATION,
                429: LookupStatus.RATE_LIMITED,
            }
            if response.status_code != 200:
                result.status = statuses.get(
                    response.status_code, LookupStatus.PROVIDER
                )
                retry = response.headers.get("Retry-After", "")
                result.retry_after_seconds = retry_after(retry)
                return result
            if not response.content:
                result.status = LookupStatus.MALFORMED
                return result
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(
                payload.get("diagnostics"), dict
            ):
                result.status = LookupStatus.MALFORMED
                return result
            diagnostics = payload["diagnostics"]
            match_type = diagnostics.get("matchType")
            usage = payload.get("usage")
            result.metadata = {
                "diagnostics": diagnostics,
                "classification": payload.get("classification", []),
                "checklist_key": COL_XR,
                "accepted_usage": payload.get("acceptedUsage"),
            }
            alternatives = diagnostics.get("alternatives", [])
            accepted = payload.get("acceptedUsage")
            # Row 2: an exact synonym's accepted usage is its own candidate.
            result.candidates = (
                ([usage] if isinstance(usage, dict) else [])
                + ([accepted] if isinstance(accepted, dict) else [])
                + (alternatives if isinstance(alternatives, list) else [])
            )
            if match_type == "NONE":
                result.status = LookupStatus.NO_MATCH
            elif (
                match_type == "EXACT"
                and isinstance(usage, dict)
                and usage.get("key")
                and supported_match(
                    name, usage, payload.get("classification"), alternatives
                )
            ):
                result.status = LookupStatus.SUCCESS
            elif match_type in GBIF_MATCH_TYPES:
                result.status = LookupStatus.AMBIGUOUS
            else:
                result.status = LookupStatus.MALFORMED
            if self.client is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    result.status = LookupStatus.TIMEOUT
                    return result
                captured = bounded_http(
                    "https://api.gbif.org/v2/species/match/metadata",
                    timeout_seconds=remaining,
                    max_bytes=1024 * 1024,
                )
                if (
                    captured["failure"]
                    or captured["truncated"]
                    or captured.get("unsupported_encoding")
                ):
                    result.status = (
                        LookupStatus.TIMEOUT
                        if captured["failure"] == "timeout"
                        else LookupStatus.MALFORMED
                        if captured["truncated"] or captured.get("unsupported_encoding")
                        else LookupStatus.PROVIDER
                    )
                    return result
                metadata = httpx.Response(
                    captured["status_code"], content=captured["body"]
                )
            else:
                metadata = self.client.get(
                    "https://api.gbif.org/v2/species/match/metadata"
                )
            if metadata.status_code != 200:
                result.status = statuses.get(
                    metadata.status_code, LookupStatus.PROVIDER
                )
            else:
                result.metadata["index"] = metadata.json()
                result.metadata["metadata_raw_ref"] = self.blobs.put(metadata.content)
        except httpx.TimeoutException:
            result.status = LookupStatus.TIMEOUT
        except httpx.HTTPError:
            result.status = LookupStatus.PROVIDER
        except (ValueError, TypeError):
            result.status = LookupStatus.MALFORMED
        return result
