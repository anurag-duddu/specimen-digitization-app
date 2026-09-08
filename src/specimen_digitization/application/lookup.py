"""Bounded, read-only GBIF COL XR name matching with typed failure fidelity."""

import hashlib
import httpx
from .domain import Lookup, LookupStatus
from .storage import BlobStore
from .reliability import retry_after

COL_XR = "7ddf754f-d193-4cc9-b351-99906754a03b"


class GbifTaxonomy:
    def __init__(self, blobs: BlobStore, client: httpx.Client | None = None):
        self.blobs = blobs
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(20, connect=5),
            follow_redirects=False,
            headers={
                "User-Agent": "SpecimenDigitization/0.1 (https://github.com/anurag-duddu/specimen-digitization-app)"
            },
        )

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
        try:
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
            }
            alternatives = diagnostics.get("alternatives", [])
            result.candidates = ([usage] if isinstance(usage, dict) else []) + (
                alternatives if isinstance(alternatives, list) else []
            )
            if match_type == "NONE":
                result.status = LookupStatus.NO_MATCH
            elif (
                match_type == "EXACT"
                and isinstance(usage, dict)
                and usage.get("key")
                and usage.get("rank") == "SPECIES"
                and not alternatives
            ):
                result.status = LookupStatus.SUCCESS
            elif match_type in {"FUZZY", "HIGHERRANK", "EXACT"}:
                result.status = LookupStatus.AMBIGUOUS
            else:
                result.status = LookupStatus.MALFORMED
            metadata = self.client.get("https://api.gbif.org/v2/species/match/metadata")
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
