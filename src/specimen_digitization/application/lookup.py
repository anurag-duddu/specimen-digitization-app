"""Bounded, read-only GBIF COL XR name matching with typed failure fidelity."""

import hashlib
import json
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
# A pro parte synonym has several accepted usages, which GBIF.md 129 sends to
# review, so only the other synonyms can clear (the steward's review of round 2).
CLEARING_SYNONYMS = SYNONYM_STATUSES - {"PROPARTE_SYNONYM"}
# The name a literal writes (HARNESS.md section 6: S4's reading, as the
# steward's reviews tightened it). A qualifier ("sp. 1", "cf.") ends the name.
QUALIFIERS = frozenset("sp spp cf aff nr near".split())
# A clause naming a person, abbreviated or spelled out, ends the literal.
CLAUSES = frozenset(
    "det determ determined ident identif identified leg legit coll col "
    "collected collector collectors".split()
)
# Words that are never epithets, so the name ends before them: prepositions
# ("de" may still begin an author's name) and sex and life-stage words.
NEVER_EPITHETS = frozenset(
    "by in on at from ex de male males female females larva larvae nymph "
    "nymphs pupa pupae adult adults worker workers queen queens".split()
)
SUBSPECIES_MARKERS = frozenset({"ssp", "subsp"})
MARKERS = SUBSPECIES_MARKERS | {"var"}
STOPS = QUALIFIERS | CLAUSES | NEVER_EPITHETS | MARKERS
HYBRID_SIGNS = frozenset({"×", "x"})
# The particles of an author's name ("de Geer", "van der Linden").
PARTICLES = frozenset("de da di du van von der den la le".split())
MAX_WORDS = 40  # of a literal read; a name and its authorship are far shorter
MAX_WORD_LENGTH = 64  # a literal with a longer word among them writes no name
MAX_AUTHORS = 4
AUTHORSHIP_WORDS = 24
MAX_AUTHORSHIP_LENGTH = 200
MAX_NAME_LENGTH = 500  # A longer name from GBIF is malformed, not a candidate.
MAX_KEY_LENGTH = 64
MAX_CODE_LENGTH = 40  # a rank or a status
MAX_DEPTH = 32  # a body's nesting; GBIF's own is a few levels
GENUS = re.compile(r"[A-Z][a-z]+\Z")
SUBGENUS = re.compile(r"\(([A-Z][a-z]*\.?)\)\Z")  # "(Pyrobombus)" or "(P.)"
# An old capitalized epithet (a patronym or a place), never a person's surname.
CAPITALIZED_EPITHET = re.compile(r"[A-Z][a-z]+(?:i|ae|orum|arum|ensis)\Z")
INITIALS = re.compile(r"(?:[A-Z]\.)+\Z")  # "F." or "F.G."
YEAR = re.compile(r"[12]\d{3}\Z")


@dataclass(frozen=True)
class ScientificName:
    """The scientific name a taxon literal writes, word for word."""

    genus: str
    subgenus: str | None
    epithets: tuple[str, ...]  # as written
    marker: str | None  # the subspecies or variety marker, as written
    rank: str  # GENUS, SPECIES, SUBSPECIES or VARIETY
    authorship: str | None
    # Why the name was read only in part: "hybrid", or the word after a genus
    # that could be an epithet the reader does not take. Such a name never
    # succeeds (HARNESS.md section 6).
    partly_read: str | None = None

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


def _core(word: str) -> str:
    """A word without its trailing punctuation."""
    return word.rstrip(".,;:")


def _ends(word: str) -> bool:
    """Whether a word ends the name: a comma, a semicolon, a colon or a period."""
    return word[-1:] in {".", ",", ";", ":"}


def _hybrid(word: str) -> bool:
    return word in HYBRID_SIGNS or word.startswith("×")


def _epithet(word: str, capitalized: bool = True) -> bool:
    """An epithet as written: lower case with any accents or hyphens, or, when
    allowed, an old capitalized epithet; never a word that ends the name."""
    core = _core(word)
    if len(core) < 2 or core.lower() in STOPS:
        return False
    if capitalized and CAPITALIZED_EPITHET.match(core):
        return True
    return core[0].islower() and all(part.isalpha() for part in core.split("-"))


def _could_be_epithet(word: str) -> bool:
    """A word after a genus that could be an epithet the reader does not take:
    letters, and neither a word that ends the name nor an abbreviation of at
    most three letters ("Mt.")."""
    core = _core(word)
    return (
        len(core) > 1
        and all(part.isalpha() for part in core.split("-"))
        and core.lower() not in STOPS
        and not (word.endswith(".") and len(core) <= 3)
    )


def _surname(word: str) -> bool:
    """A title-case surname, perhaps abbreviated ("Fabr."), in any script."""
    core = word[:-1] if word.endswith(".") else word
    return (
        len(core) > 1
        and core[0].isupper()
        and core.replace("'", "").replace("-", "").isalpha()
    )


def _authorship(words: list[str]) -> tuple[str | None, int]:
    """An author-year authorship at the start of `words`, and the words it
    takes: one to four authors (title-case surnames, with any particles and
    initials), joined by "&", "et" or a comma, then a year; in parentheses or
    not, and bounded. Anything else is no authorship."""
    authors, pending, joined = 0, False, True
    for count, word in enumerate(words[:AUTHORSHIP_WORDS], 1):
        token = word[1:] if count == 1 and word.startswith("(") else word
        if YEAR.match(token.rstrip(".,;:)")):
            text = " ".join(words[:count])
            if authors and not pending and len(text) <= MAX_AUTHORSHIP_LENGTH:
                return text, count
            return None, 0
        bare = token.rstrip(",")
        if bare in {"&", "et"} and authors and not pending:
            joined = True
        elif bare == "al." and joined and authors:
            authors, joined = authors + 1, token.endswith(",")
        elif (INITIALS.match(bare) or bare in PARTICLES) and (joined or pending):
            pending = True
        elif _surname(bare) and (joined or pending):
            authors, pending, joined = authors + 1, False, token.endswith(",")
            if authors > MAX_AUTHORS:
                return None, 0
        else:
            return None, 0
    return None, 0


def scientific_name(literal: str) -> ScientificName | None:
    """The scientific name a taxon literal writes, or None when it writes none
    (HARNESS.md section 6).

    The literal must begin with a title-case genus. The words after it are read
    as a parenthesized subgenus, written out or abbreviated; epithets in lower
    case, with any accents or hyphens, or an old capitalized epithet; a
    subspecies or variety marker with its epithet; and a bounded author-year
    authorship. A qualifier, a hybrid sign and a word that is never an epithet
    end the name, and a clause naming a person ends the literal. A word the
    literal does not write is never sent, and neither is text that is no name
    (PLAN 4.8)."""
    words = literal.split(maxsplit=MAX_WORDS)[:MAX_WORDS]
    for index, word in enumerate(words):
        if _core(word).lower() in CLAUSES:
            words = words[:index]
            break
    if not words or any(len(word) > MAX_WORD_LENGTH for word in words):
        return None
    genus = _core(words[0])
    if not GENUS.match(genus) or genus.lower() in STOPS:
        return None
    subgenus, epithets, marker, rank, partly = None, [], None, "GENUS", None
    ended, rest = _ends(words[0]), words[1:]
    if not ended and rest and SUBGENUS.match(rest[0].rstrip(",;:")):
        subgenus = SUBGENUS.match(rest[0].rstrip(",;:")).group(1)
        ended, rest = rest[0][-1:] in {",", ";", ":"}, rest[1:]
    if not ended and rest and _epithet(rest[0]):
        epithets, rank = [_core(rest[0])], "SPECIES"
        ended, rest = _ends(rest[0]), rest[1:]
    if epithets and not ended and rest:
        if _core(rest[0]).lower() in MARKERS and len(rest) > 1 and _epithet(rest[1]):
            variety = _core(rest[0]).lower() == "var"
            epithets.append(_core(rest[1]))
            marker, rank = rest[0], "VARIETY" if variety else "SUBSPECIES"
            rest = rest[2:]
        elif _epithet(rest[0], capitalized=False):
            epithets.append(_core(rest[0]))
            rank, rest = "SUBSPECIES", rest[1:]
    if rest and _hybrid(rest[0]):
        partly = "hybrid"
    authorship = None
    if partly is None and rest:
        authorship, used = _authorship(rest)
        rest = rest[used:]
    if partly is None and not epithets and rest and _could_be_epithet(rest[0]):
        partly = _core(rest[0])
    return ScientificName(
        genus, subgenus, tuple(epithets), marker, rank, authorship, partly
    )


def _class_of(classification) -> str | None:
    """The class a classification names, or None when it names none."""
    return next(
        (
            level.get("name")
            for level in classification or []
            if isinstance(level, dict) and level.get("rank") == "CLASS"
        ),
        None,
    )


def _in_insecta(classification) -> bool:
    """A compatible classification: class Insecta, the class the query takes
    from the profile (the coordinator's ruling of 22:46Z on 2026-09-25)."""
    return _class_of(classification) == "Insecta"


def homonym_conflict(usage: dict, alternatives: list) -> bool:
    """GBIF.md 129 as the coordinator ruled (22:46Z on 2026-09-25): another
    EXACT alternative with the same canonical name and other authorship, in
    class Insecta, whatever its status. Non-exact alternatives and those outside
    the class are not plausible, and a duplicate of the same name and
    authorship is no conflict. One that lacks its class or its canonical name
    counts, as does one whose authorship, like the usage's, is empty: nothing
    shows it is another name (the steward's review of round 2)."""
    authorship = (usage.get("authorship") or "").strip()
    for other in alternatives:
        found = other["usage"]
        if other["diagnostics"].get("matchType") != "EXACT":
            continue
        if found.get("key") is not None and found.get("key") == usage.get("key"):
            continue  # The usage itself.
        name = found.get("canonicalName")
        if name is not None and name != usage.get("canonicalName"):
            continue
        if authorship and (found.get("authorship") or "").strip() == authorship:
            continue  # The same name and authorship again.
        found_class = _class_of(other.get("classification"))
        if found_class is not None and found_class != "Insecta":
            continue
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
    with no homonym conflict for the label's name. GBIF v2's accepted usage is
    the accepted name by definition, so a missing status counts as accepted and
    any other status sends the match to review (the coordinator's ruling of
    23:58Z). A pro parte synonym never clears."""
    return (
        isinstance(usage, dict)
        and usage.get("status") in CLEARING_SYNONYMS
        and usage.get("canonicalName") == name.canonical
        and usage.get("rank") == name.rank
        and isinstance(accepted, dict)
        and bool(accepted.get("key"))
        and accepted.get("status") in (None, "ACCEPTED")
        and accepted.get("rank") == name.rank
        and _in_insecta(classification)
        and not homonym_conflict(usage, alternatives)
    )


def _unique(pairs: list) -> dict:
    """A JSON object whose keys are unique: a key given twice is malformed,
    never silently its last value (the steward's review of round 2)."""
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate_key")
    return dict(pairs)


def parse_json(content: bytes):
    """A provider's body as JSON, refusing duplicate keys."""
    return json.loads(content, object_pairs_hook=_unique)


def _depth_ok(value, limit: int = MAX_DEPTH) -> bool:
    """Whether a parsed body nests no deeper than `limit`, checked without
    recursion, so a body the record cannot store is refused first."""
    stack = [(value, 1)]
    while stack:
        item, depth = stack.pop()
        if isinstance(item, (dict, list)):
            if depth > limit:
                return False
            children = item.values() if isinstance(item, dict) else item
            stack.extend((child, depth + 1) for child in children)
    return True


def _shape_ok(payload: dict) -> bool:
    """The parts the decision reads have the types GBIF documents, within their
    bounds. Anything else is `malformed_response`, never an exception."""

    def text_ok(value, limit: int) -> bool:
        return value is None or (isinstance(value, str) and len(value) <= limit)

    def usage_ok(usage) -> bool:
        if usage is None:
            return True
        if not isinstance(usage, dict):
            return False
        key = usage.get("key", "")
        return (
            ((type(key) is int and key >= 0) or (isinstance(key, str) and len(key) <= MAX_KEY_LENGTH))
            and all(
                text_ok(usage.get(field), MAX_NAME_LENGTH)
                for field in ("name", "canonicalName", "authorship")
            )
            and all(text_ok(usage.get(field), MAX_CODE_LENGTH) for field in ("rank", "status"))
        )

    def classification_ok(classification) -> bool:
        return classification is None or (
            isinstance(classification, list)
            and all(
                isinstance(level, dict)
                and text_ok(level.get("name"), MAX_NAME_LENGTH)
                and text_ok(level.get("rank"), MAX_CODE_LENGTH)
                for level in classification
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
        and classification_ok(payload.get("classification"))
        and all(
            isinstance(other, dict)
            and isinstance(other.get("diagnostics"), dict)
            and isinstance(other.get("usage"), dict)
            and usage_ok(other["usage"])
            and classification_ok(other.get("classification"))
            for other in alternatives or []
        )
    )


def selectable(usage: dict) -> dict:
    """GBIF v2 names a usage `name`; the reviewer's `taxonomy_resolution`
    decision selects by `scientificName` (api.py) and stores it, so each
    candidate's `scientificName` is GBIF's own `name`, within its bound, and
    never a body's field (the steward's review of round 2)."""
    kept = {key: value for key, value in usage.items() if key != "scientificName"}
    if isinstance(usage.get("name"), str) and usage["name"]:
        kept["scientificName"] = usage["name"]
    return kept


def no_name_lookup(literal: str) -> Lookup:
    """A literal that writes no scientific name: `no_match`, with no request."""
    return Lookup(
        provider="gbif",
        adapter_version="species-match-v2.3",
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
            adapter_version="species-match-v2.3",
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
            payload = parse_json(response.content)
            if (
                not isinstance(payload, dict)
                or not _depth_ok(payload)
                or not _shape_ok(payload)
            ):
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
            if parsed.partly_read:
                # A name read only in part never succeeds (section 6).
                result.metadata["partly_read"] = parsed.partly_read
                if result.status == LookupStatus.SUCCESS:
                    result.status = LookupStatus.AMBIGUOUS
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
                result.metadata["index"] = parse_json(metadata.content)
                result.metadata["metadata_raw_ref"] = self.blobs.put(metadata.content)
        except httpx.TimeoutException:
            result.status = LookupStatus.TIMEOUT
        except httpx.HTTPError:
            result.status = LookupStatus.PROVIDER
        except (ValueError, TypeError, AttributeError, KeyError, RecursionError):
            result.status = LookupStatus.MALFORMED
        return result
