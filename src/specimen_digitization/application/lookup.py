"""Bounded, read-only GBIF COL XR name matching with typed failure fidelity."""

import hashlib
import re
import time
from dataclasses import dataclass

import httpx
from .domain import Lookup, LookupStatus
from .storage import BlobStore
from .reliability import retry_after

COL_XR = "7ddf754f-d193-4cc9-b351-99906754a03b"
# COL XR's licence, cited per GBIF's citation guidelines (PLAN 4.8).
GBIF_LICENSE = "CC BY 4.0 (COL XR, checklist " + COL_XR + ")"
# GBIF.md 126-130 as HARNESS.md section 6 applies them, with the coordinator's
# rulings of 22:46Z on 2026-09-25 on homonyms and exact synonyms: a match type
# GBIF documents is never malformed, and only row 1 at the label's rank succeeds.
GBIF_MATCH_TYPES = frozenset({"EXACT", "FUZZY", "VARIANT", "HIGHERRANK"})
SYNONYM_STATUSES = frozenset(
    {"SYNONYM", "HETEROTYPIC_SYNONYM", "HOMOTYPIC_SYNONYM", "PROPARTE_SYNONYM"}
)
# A label's qualifiers after a genus ("sp. 1", "cf."), and the clauses that
# name a person rather than the taxon (det., leg., coll.).
QUALIFIERS = frozenset({"sp", "spp", "cf", "aff", "nr", "near"})
PERSON_CLAUSES = frozenset({"det", "leg", "coll", "col"})
SUBSPECIES_MARKERS = frozenset({"ssp", "subsp"})
MAX_NAME_LENGTH = 500  # A longer name from GBIF is malformed, not a candidate.
GENUS = re.compile(r"[A-Z][a-z]+\Z")
SUBGENUS = re.compile(r"\(([A-Z][a-z]+)\)\Z")
EPITHET = re.compile(r"[a-z]+(?:-[a-z]+)*\Z")
# An old capitalized epithet (a patronym or a place), never a person's surname.
CAPITALIZED_EPITHET = re.compile(r"[A-Z][a-z]+(?:i|ae|orum|arum|ensis)\Z")
AUTHOR_WORD = re.compile(
    r"\(?(?:[A-Z][A-Za-z'\-]*\.?|[A-Z]\.(?:[A-Z]\.)*|&|et|al\.|de|da|van|von|der|"
    r"den|la|le|du|di|in)[,)]?\Z"
)
YEAR = re.compile(r"\(?[12]\d{3}\)?,?\Z")


@dataclass(frozen=True)
class ScientificName:
    """The scientific name a taxon literal writes, word for word."""

    genus: str
    subgenus: str | None
    epithets: tuple[str, ...]  # as written
    marker: str | None  # the subspecies or variety marker, as written
    rank: str  # GENUS, SPECIES, SUBSPECIES or VARIETY
    authorship: str | None

    @property
    def canonical(self) -> str:
        """GBIF's `canonicalName` form, for comparison: no subgenus and no
        authorship, epithets in lower case, and "var." only for a variety."""
        words = [self.genus] + [e.lower() for e in self.epithets[:1]]
        if len(self.epithets) > 1:
            if self.rank == "VARIETY":
                words.append("var.")
            words.append(self.epithets[1].lower())
        return " ".join(words)

    @property
    def query(self) -> str:
        """The name exactly as the literal writes it: nothing is added."""
        words = [self.genus]
        if self.subgenus:
            words.append(f"({self.subgenus})")
        words += list(self.epithets[:1])
        if len(self.epithets) > 1:
            words += ([self.marker] if self.marker else []) + [self.epithets[1]]
        if self.authorship:
            words.append(self.authorship)
        return " ".join(words)


def _bare(word: str) -> str:
    return word.rstrip(".:").lower()


def _epithet(word: str) -> bool:
    return bool(EPITHET.match(word) or CAPITALIZED_EPITHET.match(word))


def scientific_name(literal: str) -> ScientificName | None:
    """The scientific name a taxon literal writes, or None when it writes none.

    The literal must begin with a title-case genus. The words after it are read
    as a parenthesized subgenus, epithets (hyphenated, or an old capitalized
    epithet), a subspecies or variety marker with its epithet, and an
    author-year authorship. A qualifier ("sp. 1", "cf.") ends the name, and a
    det., leg. or coll. clause ends the literal. A word the literal does not
    write is never sent, and neither is text that is not a name (PLAN 4.8)."""
    words = literal.split()
    for index, word in enumerate(words):
        if _bare(word) in PERSON_CLAUSES:
            words = words[:index]
            break
    if not words or not GENUS.match(words[0]) or words[0].lower() in QUALIFIERS:
        return None
    genus, subgenus, epithets, marker, rank = words[0], None, [], None, "GENUS"
    rest = words[1:]
    if rest and SUBGENUS.match(rest[0]):
        subgenus, rest = SUBGENUS.match(rest[0]).group(1), rest[1:]
    if rest and _bare(rest[0]) not in QUALIFIERS and _epithet(rest[0]):
        epithets, rank, rest = [rest[0]], "SPECIES", rest[1:]
        if len(rest) > 1 and _bare(rest[0]) in SUBSPECIES_MARKERS and _epithet(rest[1]):
            epithets, marker, rank = epithets + [rest[1]], rest[0], "SUBSPECIES"
            rest = rest[2:]
        elif len(rest) > 1 and _bare(rest[0]) == "var" and _epithet(rest[1]):
            epithets, marker, rank = epithets + [rest[1]], rest[0], "VARIETY"
            rest = rest[2:]
        elif rest and EPITHET.match(rest[0]) and _bare(rest[0]) not in QUALIFIERS:
            epithets, rank, rest = epithets + [rest[0]], "SUBSPECIES", rest[1:]
    authorship = None
    if rest and _bare(rest[0]) not in QUALIFIERS:
        # Authorship only in the author-year form: a bare capitalized word after
        # a name may be a collector or a place, which is never sent (PLAN 4.8).
        taken = []
        for word in rest:
            taken.append(word)
            if YEAR.match(word):
                authorship = " ".join(taken)
                break
            if not AUTHOR_WORD.match(word):
                break
    return ScientificName(genus, subgenus, tuple(epithets), marker, rank, authorship)


def _in_insecta(classification) -> bool:
    """A compatible classification: class Insecta, the class the query takes
    from the profile (the coordinator's ruling of 22:46Z on 2026-09-25)."""
    return isinstance(classification, list) and any(
        isinstance(c, dict) and c.get("rank") == "CLASS" and c.get("name") == "Insecta"
        for c in classification
    )


def homonym_conflict(usage: dict, alternatives: list) -> bool:
    """GBIF.md 129 as the coordinator ruled (22:46Z on 2026-09-25): another
    EXACT alternative with the same canonical name and other authorship, in
    class Insecta, whatever its status. Non-exact alternatives and those outside
    the class are not plausible, and a duplicate of the same name and
    authorship is no conflict."""
    for other in alternatives:
        found = other["usage"]
        if (
            other["diagnostics"].get("matchType") == "EXACT"
            and found.get("canonicalName") == usage.get("canonicalName")
            and (found.get("authorship") or "").strip()
            != (usage.get("authorship") or "").strip()
            and _in_insecta(other.get("classification"))
        ):
            return True
    return False


def row_one(name: ScientificName, usage, classification, alternatives) -> bool:
    """Row 1 (GBIF.md 126): an accepted usage with a key, with the label's
    canonical name at the label's rank, a compatible classification and no
    homonym conflict."""
    return (
        isinstance(usage, dict)
        and usage.get("status") == "ACCEPTED"
        and bool(usage.get("key"))
        and usage.get("canonicalName") == name.canonical
        and usage.get("rank") == name.rank
        and _in_insecta(classification)
        and not homonym_conflict(usage, alternatives)
    )


def cleared_synonym(name: ScientificName, usage, accepted, classification, alternatives):
    """Row 2 (GBIF.md 127) as the coordinator ruled at 22:46Z (G28, G1): an
    exact synonym of the label's name clears when its accepted usage passes row
    1's test, the accepted usage GBIF returns at the label's rank, in Insecta,
    with no homonym conflict for the label's name."""
    return (
        isinstance(usage, dict)
        and usage.get("status") in SYNONYM_STATUSES
        and usage.get("canonicalName") == name.canonical
        and usage.get("rank") == name.rank
        and isinstance(accepted, dict)
        and bool(accepted.get("key"))
        and accepted.get("status") in (None, "ACCEPTED")
        and accepted.get("rank") == name.rank
        and _in_insecta(classification)
        and not homonym_conflict(usage, alternatives)
    )


def _shape_ok(payload: dict) -> bool:
    """The parts the decision reads have the types GBIF documents. Anything
    else is `malformed_response`, never an exception."""

    def usage_ok(usage) -> bool:
        return usage is None or (
            isinstance(usage, dict)
            and isinstance(usage.get("key", ""), (str, int))
            and all(
                isinstance(usage.get(field), (str, type(None)))
                for field in ("name", "canonicalName", "authorship", "rank", "status")
            )
            and all(
                len(usage.get(field) or "") <= MAX_NAME_LENGTH
                for field in ("name", "canonicalName", "authorship")
            )
        )

    diagnostics = payload.get("diagnostics")
    if not isinstance(diagnostics, dict):
        return False
    alternatives = diagnostics.get("alternatives")
    return (
        (alternatives is None or isinstance(alternatives, list))
        and usage_ok(payload.get("usage"))
        and usage_ok(payload.get("acceptedUsage"))
        and isinstance(payload.get("classification") or [], list)
        and all(
            isinstance(other, dict)
            and isinstance(other.get("diagnostics"), dict)
            and isinstance(other.get("usage"), dict)
            and usage_ok(other["usage"])
            and isinstance(other.get("classification") or [], list)
            for other in alternatives or []
        )
    )


def selectable(usage: dict) -> dict:
    """GBIF v2 names a usage `name`; the reviewer's `taxonomy_resolution`
    decision selects by `scientificName` (api.py), so each candidate has it."""
    if "scientificName" not in usage and isinstance(usage.get("name"), str):
        return {**usage, "scientificName": usage["name"]}
    return usage


def no_name_lookup(literal: str) -> Lookup:
    """A literal that writes no scientific name: `no_match`, with no request."""
    return Lookup(
        provider="gbif",
        adapter_version="species-match-v2.2",
        query={},
        status=LookupStatus.NO_MATCH,
        metadata={"verbatim_name": literal, "reason": "no_scientific_name"},
    )


class GbifTaxonomy:
    def __init__(self, blobs: BlobStore, client: httpx.Client | None = None):
        self.blobs = blobs
        self.client = client

    def lookup(self, name: str | ScientificName, timeout: float = 20) -> Lookup:
        parsed = name if isinstance(name, ScientificName) else scientific_name(name)
        if parsed is None:
            return no_name_lookup(name)
        query = {
            "scientificName": parsed.query,
            "taxonRank": parsed.rank,
            "kingdom": "Animalia",
            "class": "Insecta",
            "checklistKey": COL_XR,
            "verbose": "true",
        }
        result = Lookup(
            provider="gbif",
            adapter_version="species-match-v2.2",
            query=query,
            status=LookupStatus.PROVIDER,
        )
        timeout = max(0.1, min(20.0, timeout))
        deadline = time.monotonic() + timeout
        try:
            if self.client is None:
                from .http_effect import bounded_http

                captured = bounded_http(
                    "https://api.gbif.org/v2/species/match",
                    timeout_seconds=timeout,
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
                    "https://api.gbif.org/v2/species/match",
                    params=query,
                    timeout=timeout,
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
            if not isinstance(payload, dict) or not _shape_ok(payload):
                result.status = LookupStatus.MALFORMED
                return result
            diagnostics = payload["diagnostics"]
            match_type = diagnostics.get("matchType")
            usage = payload.get("usage")
            accepted = payload.get("acceptedUsage")
            classification = payload.get("classification") or []
            alternatives = diagnostics.get("alternatives") or []
            result.metadata = {
                "diagnostics": diagnostics,
                "classification": classification,
                "checklist_key": COL_XR,
                "accepted_usage": accepted,
                "requested_rank": parsed.rank,
            }
            synonym = match_type == "EXACT" and cleared_synonym(
                parsed, usage, accepted, classification, alternatives
            )
            # A cleared synonym's accepted usage is the settled candidate; the
            # synonym and the other candidates stay on the record for review.
            first = [accepted, usage] if synonym else [usage, accepted]
            result.candidates = [
                selectable(found) for found in first if isinstance(found, dict)
            ] + [{**other, "usage": selectable(other["usage"])} for other in alternatives]
            if match_type == "NONE":
                result.status = LookupStatus.NO_MATCH
            elif synonym or (
                match_type == "EXACT"
                and row_one(parsed, usage, classification, alternatives)
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
                    "https://api.gbif.org/v2/species/match/metadata",
                    timeout=max(0.1, deadline - time.monotonic()),
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
        except (ValueError, TypeError, AttributeError, KeyError, RecursionError):
            result.status = LookupStatus.MALFORMED
        return result
