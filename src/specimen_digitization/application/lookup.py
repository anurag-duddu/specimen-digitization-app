"""Bounded, read-only GBIF COL XR name matching with typed failure fidelity."""

import hashlib
import json
import re
import time
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

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
# The statuses and ranks GBIF and ChecklistBank document. Any other value is
# malformed, so no free text reaches the harness as a status or a rank.
GBIF_STATUSES = frozenset(
    "ACCEPTED PROVISIONALLY_ACCEPTED DOUBTFUL SYNONYM HETEROTYPIC_SYNONYM "
    "HOMOTYPIC_SYNONYM PROPARTE_SYNONYM AMBIGUOUS_SYNONYM MISAPPLIED "
    "BARE_NAME".split()
)
GBIF_RANKS = frozenset(
    "SUPERDOMAIN DOMAIN SUBDOMAIN INFRADOMAIN EMPIRE REALM SUBREALM SUPERKINGDOM "
    "KINGDOM SUBKINGDOM INFRAKINGDOM SUPERPHYLUM PHYLUM SUBPHYLUM INFRAPHYLUM "
    "PARVPHYLUM MICROPHYLUM NANOPHYLUM CLAUDIUS GIGACLASS MEGACLASS SUPERCLASS "
    "CLASS SUBCLASS INFRACLASS SUBTERCLASS PARVCLASS SUPERDIVISION DIVISION "
    "SUBDIVISION INFRADIVISION SUPERLEGION LEGION SUBLEGION INFRALEGION "
    "MEGACOHORT SUPERCOHORT COHORT SUBCOHORT INFRACOHORT GIGAORDER MAGNORDER "
    "GRANDORDER MIRORDER SUPERORDER ORDER NANORDER HYPOORDER MINORDER SUBORDER "
    "INFRAORDER PARVORDER FALANX MEGAFAMILY GRANDFAMILY SUPERFAMILY EPIFAMILY "
    "FAMILY SUBFAMILY INFRAFAMILY SUPERTRIBE TRIBE SUBTRIBE INFRATRIBE "
    "SUPRAGENERIC_NAME SUPERGENUS GENUS SUBGENUS INFRAGENUS SUPERSECTION "
    "SECTION SUBSECTION SUPERSECTION_BOTANY SECTION_BOTANY SUBSECTION_BOTANY "
    "SUPERSECTION_ZOOLOGY SECTION_ZOOLOGY SUBSECTION_ZOOLOGY SUPERSERIES SERIES "
    "SUBSERIES SERIES_ZOOLOGY INFRAGENERIC_NAME SPECIES_AGGREGATE SPECIES INFRASPECIFIC_NAME "
    "GREX KLEPTON SUBSPECIES CULTIVAR_GROUP CONVARIETY INFRASUBSPECIFIC_NAME "
    "PROLES NATIO ABERRATION MORPH SUPERVARIETY VARIETY SUBVARIETY SUPERFORM "
    "FORM SUBFORM PATHOVAR BIOVAR CHEMOVAR MORPHOVAR PHAGOVAR SEROVAR CHEMOFORM "
    "FORMA_SPECIALIS LUSUS CULTIVAR MUTATIO STRAIN OTHER UNRANKED".split()
)
# The name a literal writes (HARNESS.md section 6), read failing closed (the
# steward's review of round 3): a word the reader does not take marks the name
# read only in part, so it never succeeds. A qualifier after the genus makes a
# genus-level identification; before it, it marks the genus doubtful (the
# coordinator's reading of 01:11Z on 2026-09-26).
QUALIFIERS = frozenset("sp spp cf aff nr near".split())
DOUBT_MARKERS = frozenset("cf aff nr near".split())
# A clause naming a person ends the literal: English, Spanish, Latin, French
# and German markers, abbreviated or spelled out.
CLAUSES = frozenset(
    "det determ determined determiner ident identif identified leg legit lg lgt "
    "coll col collected collector collectors vid vidit rev revid revidit conf "
    "confirmed confirmavit teste dt dét déterminé recogn recognovit "
    "determinavit sammler determinado determinada determinó colectado "
    "colectada colectó colector colectores colecta recolectado recolectada "
    "recolector recolectores identificado identificó revisado revisó "
    "confirmado".split()
)
# The particles of an author's name ("de Geer", "van der Linden").
PARTICLES = frozenset("de da di du van von der den la le".split())
# Words that end the name, never an epithet or an author, so nothing after them
# is read: the prepositions in English, Spanish, Latin and German that the
# reader takes as ends (UNREAD_WORDS lists others); the particles, which may
# still begin an author's name; and the sex, life-stage, type-status and
# nomenclatural words that leave the taxon as it is.
NEVER_EPITHETS = PARTICLES | frozenset(
    "by in on at from ex with near prope ad bei en por con cerca del sobre "
    "male males female females fem macho machos hembra hembras larva larvae "
    "nymph nymphs pupa pupae adult adults worker workers queen queens teneral "
    "imago juv juvenile immature egg eggs exuvia exuviae type types holotype "
    "paratype paratypes allotype lectotype paralectotype paralectotypes "
    "neotype syntype syntypes cotype cotypes topotype topotypes holotipo "
    "holotipos paratipo paratipos alotipo alotipos lectotipo lectotipos "
    "paralectotipo paralectotipos neotipo neotipos sintipo sintipos cotipo "
    "cotipos topotipo topotipos nov gen comb stat emend".split()
)
# Words that change the taxon a name stands for: a group, a complex or an
# aggregate of species, or a concept (sensu, auct.). They mark the name, so it
# never clears as the species (the steward's review of round 4).
CONCEPT_WORDS = frozenset(
    "group gr grp grupo complex complejo agg aggr sensu auct auctt auctorum".split()
)
# Months in full and abbreviated, English and Spanish, and the Roman months but
# X, which is also a hybrid sign: a date, never an author.
MONTHS = frozenset(
    "january february march april may june july august september october "
    "november december jan feb mar apr jun jul aug sep sept oct nov dec enero "
    "febrero marzo abril mayo junio julio agosto septiembre setiembre octubre "
    "noviembre diciembre ene abr ago set dic agto sbre obre nbre dbre febr mzo "
    "ag".split()
)
ROMAN_MONTHS = frozenset("i ii iii iv v vi vii viii ix xi xii".split())
# A "V" or "v." standing alone may be "var.", so it marks the name; the other
# Roman months end it (the steward's review of round 4).
ROMAN_MONTH_ENDS = ROMAN_MONTHS - {"v"}
SUBSPECIES_MARKERS = frozenset({"ssp", "subsp"})
MARKERS = SUBSPECIES_MARKERS | {"var"}
# Infraspecific markers the reader does not take: the name is read only in part.
UNREAD_MARKERS = frozenset("f fo forma ab aberr morph morpha race natio subvar".split())
# Other prepositions, articles and conjunctions in English, Spanish, Latin,
# French and German, "et" joining two names among them: never an epithet, and
# not an end, so the name is read only in part and nothing after them is sent
# (HARNESS.md section 6). A title-case one may still be a genus or an author.
UNREAD_WORDS = frozenset(
    "about above across after against along among amongst around before behind "
    "below beneath beside besides between beyond during for inside into of off "
    "onto out outside over past per through throughout till toward towards "
    "under underneath until unto upon via within without an the and or nor but "
    "al ante bajo contra desde durante entre hacia hasta mediante para según "
    "segun sin tras vía junto dentro fuera encima debajo detrás detras delante "
    "alrededor lejos el los las lo un una unos unas ni pero "
    "apud circa circum cum extra infra inter intra iuxta juxta ob post prae "
    "praeter pro propter sec secundum sine sub super supra trans ultra versus "
    "et ac atque aut vel sed nec neque "
    "au aux avec chez contre dans derrière derriere devant hors jusqu jusque "
    "malgré malgre par parmi pendant pour près pres sans selon sous sur vers "
    "les des une ou mais "
    "am an auf aus bis durch für fur gegen hinter im mit nach neben ohne seit um "
    "unter über uber vom vor während wahrend wegen zu zum zur zwischen die das "
    "dem ein eine einem einen einer und oder".split()
)
HYBRID_SIGNS = frozenset({"×", "x", "X", "✕", "✖", "⨯"})
SEX_SIGNS = frozenset("♀♂⚥")
NOT_NAMES = (
    QUALIFIERS
    | CLAUSES
    | NEVER_EPITHETS
    | CONCEPT_WORDS
    | MONTHS
    | ROMAN_MONTHS
    | MARKERS
    | UNREAD_MARKERS
)
# PLAN 4.8's place fields: their literals, and the reading's unassigned
# locality text, are the place text a taxonomy request never carries.
PLACE_FIELDS = ("country", "province_state", "county", "city", "precise_location")
PLACE_WORD = "place_word"  # why a name is marked: the reading's place text
MAX_WORDS = 40  # of a literal read; a name and its authorship are far shorter
MAX_WORD_LENGTH = 64  # a literal with a longer word among them writes no name
MAX_AUTHORS = 4
AUTHORSHIP_WORDS = 24
MAX_AUTHORSHIP_LENGTH = 200
MAX_NAME_LENGTH = 500  # A longer name from GBIF is malformed, not a candidate.
MAX_KEY = 10**12  # a numeric key's bound
MAX_DEPTH = 32  # a body's nesting; GBIF's own is a few levels
# GBIF's alternatives kept as review candidates: the review step takes at most
# 100 proposals, and the diagnostics keep every alternative (the steward's
# review of round 5).
MAX_ALTERNATIVES = 20
KEY = re.compile(r"[A-Za-z0-9]{1,32}\Z")
GENUS = re.compile(r"[A-Z][a-z]+\Z")
SUBGENUS = re.compile(r"\(([A-Z][a-z]*\.?)\)\Z")  # "(Pyrobombus)" or "(P.)"
# An old capitalized epithet (a patronym or a place), never a person's surname.
CAPITALIZED_EPITHET = re.compile(r"[A-Z][a-z]+(?:i|ae|orum|arum|ensis)\Z")
INITIALS = re.compile(r"(?:[A-Z]\.)+\Z")  # "F." or "F.G."
YEAR = re.compile(r"[12]\d{3}\Z")
QUALIFIER = re.compile(r"([A-Za-z]+)[^A-Za-z]*\Z")  # "sp.", "Sp.#1", "cf."


@dataclass(frozen=True)
class ScientificName:
    """The scientific name a taxon literal writes, word for word."""

    genus: str
    subgenus: str | None
    epithets: tuple[str, ...]  # as written
    marker: str | None  # the subspecies or variety marker, as written
    rank: str  # GENUS, SPECIES, SUBSPECIES or VARIETY
    authorship: str | None
    # Why the name was read only in part: "hybrid", the doubt on the genus, a
    # marker the reader does not take, the first word it could not read, or
    # PLACE_WORD for the reading's place text. Such a name never succeeds
    # (HARNESS.md section 6). A name whose genus is withheld, in doubt or
    # place text, has no genus and sends nothing.
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


def _word(word: str) -> str:
    """A word as the word lists compare it: lower case, without surrounding
    punctuation."""
    return word.strip(".,;:()[]'\"?!").lower()


def _ends(word: str) -> bool:
    """Whether a word ends the name: a comma, a semicolon, a colon or a period."""
    return word[-1:] in {".", ",", ";", ":"}


def _qualifier(word: str) -> str | None:
    """The qualifier a word is ("sp.", "Sp.#1", "cf."), or None."""
    match = QUALIFIER.match(word)
    found = match.group(1).lower() if match else None
    return found if found in QUALIFIERS else None


def _hybrid(word: str) -> bool:
    return word in HYBRID_SIGNS or word.startswith("×")


def _date(word: str) -> bool:
    """A number or a written date ("1946", "13-5-48", "12.v.1948"): digits,
    with no letters but a Roman month or a month's."""
    if not any(ch.isdigit() for ch in word):
        return False
    runs = re.findall(r"[^\W\d_]+", word)
    return all(run.lower() in ROMAN_MONTHS or run.lower() in MONTHS for run in runs)


def _ends_name(word: str) -> bool:
    """A word that ends the name, so nothing after it is read: a qualifier, a
    word that is never an epithet, a listed month, a Roman month but V, a
    number or date, or sex signs."""
    bare = _word(word)
    return bool(
        _qualifier(word)
        or bare in NEVER_EPITHETS
        or bare in MONTHS
        or bare in ROMAN_MONTH_ENDS
        or _date(word)
        or (word and all(ch in SEX_SIGNS or ch.isdigit() for ch in word))
    )


def _epithet(word: str) -> bool:
    """An epithet as written, and nothing else in the word but trailing
    punctuation: lower-case letters with any accents and inner hyphens, or an
    old capitalized epithet; never a word the lists hold."""
    core = _core(word)
    if len(core) < 2 or core.lower() in NOT_NAMES or core.lower() in UNREAD_WORDS:
        return False
    if CAPITALIZED_EPITHET.match(core):
        return True
    return all(part.isalpha() and part == part.lower() for part in core.split("-"))


def _takes(words: list[str]) -> bool:
    """Whether the first word is an epithet the reader takes: an epithet, and,
    when capitalized, not the start of an author-year authorship ("Rossi,
    1790" is an author, not an epithet)."""
    return (
        bool(words)
        and not _ends_name(words[0])
        and _epithet(words[0])
        and not (words[0][0].isupper() and _authorship(words)[0])
    )


def _surname(word: str) -> bool:
    """A title-case surname, perhaps abbreviated ("Fabr."), in any script; never
    a month, a Roman month or a word that ends the name."""
    core = word[:-1] if word.endswith(".") else word
    return (
        len(core) > 1
        and core[0].isupper()
        and core.replace("'", "").replace("-", "").isalpha()
        and core.lower() not in NOT_NAMES
    )


def _authorship(words: list[str]) -> tuple[str | None, int]:
    """An author-year authorship at the start of `words`, and the words it
    takes: one to four authors (title-case surnames, with any particles and
    initials), joined by "&", "et" or a comma, then a year; in parentheses or
    not, and bounded. A joiner needs an author after it ("Smith & 1900" is
    none). Anything else is no authorship."""
    # `dangling`: a joiner no author has followed yet.
    authors, pending, joined, dangling = 0, False, True, False
    for count, word in enumerate(words[:AUTHORSHIP_WORDS], 1):
        token = word[1:] if count == 1 and word.startswith("(") else word
        if YEAR.match(token.rstrip(".,;:)")):
            text = " ".join(words[:count])
            complete = authors and not (pending or dangling)
            if complete and len(text) <= MAX_AUTHORSHIP_LENGTH:
                return text, count
            return None, 0
        bare = token.rstrip(",")
        if bare in {"&", "et"} and authors and not (pending or dangling):
            joined = dangling = True
        elif bare == "al." and joined and authors:
            authors, joined, dangling = authors + 1, token.endswith(","), False
        elif (INITIALS.match(bare) or bare in PARTICLES) and (joined or pending):
            pending = True
        elif _surname(bare) and (joined or pending):
            authors, pending, dangling = authors + 1, False, False
            joined = token.endswith(",")
            if authors > MAX_AUTHORS:
                return None, 0
        else:
            return None, 0
    return None, 0


def _normalized(literal: str) -> str:
    """NFC, without format characters (zero-width spaces, soft hyphens and the
    like), so that a word reads as it is written."""
    text = unicodedata.normalize("NFC", literal)
    return "".join(ch for ch in text if unicodedata.category(ch) != "Cf")


def fold(text: str) -> str:
    """PLAN 4.8's folding: casefold, strip diacritics and turn anything but
    letters and digits into single spaces, so "Petén," folds to "peten" and
    "P.I." to "p i"."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    kept = "".join(
        c if c.isalnum() else " " for c in decomposed if not unicodedata.combining(c)
    )
    return " ".join(kept.split())


def _words(literal: str) -> list[str]:
    """The words the reader reads: the literal's first MAX_WORDS, normalized."""
    return _normalized(literal).split(maxsplit=MAX_WORDS)[:MAX_WORDS]


def _place_words(place_text: Sequence[str]) -> frozenset[str]:
    """The reading's place text as the reader compares it: each folded word, and
    each whole folded literal (PLAN 4.8's folding). A bare string is refused,
    since it would be read letter by letter (the steward's review of round 4)."""
    if isinstance(place_text, str):
        raise TypeError("place_text is a sequence of texts, not one string")
    folded = [fold(text) for text in place_text]
    return frozenset(word for text in folded for word in text.split()) | frozenset(
        text for text in folded if text
    )


def _without_places(words: list[str], places: frozenset[str]) -> list[str]:
    """`words` without the place words their authorship holds (the
    coordinator's ruling of 02:07Z on 2026-09-26, applying PLAN 4.8): each
    token of the authorship that shares a folded word with the reading's place
    text is dropped, and the name is read again, until its authorship holds
    none. What remains is read by the reader's own rules."""
    while places:
        span = _read(words)[1] or (0, 0)
        dropped = {
            index
            for index in range(*span)
            if not places.isdisjoint(fold(words[index]).split())
        }
        if not dropped:
            break
        words = [word for index, word in enumerate(words) if index not in dropped]
    return words


def _slots(name: ScientificName) -> tuple:
    return (name.genus, name.subgenus, name.epithets, name.marker, name.rank)


def _withheld(reason: str) -> ScientificName:
    """A name with nothing it may send: no genus, marked with why."""
    return ScientificName("", None, (), None, "GENUS", None, reason)


def _without_place_parts(name: ScientificName, places: frozenset[str]) -> ScientificName:
    """The name up to its first part equal to the reading's place text, marked
    (the coordinator's ruling of 03:24Z on 2026-09-26, word by word as confirmed
    at 03:31Z): a genus, subgenus or epithet whose folded form is a folded word
    of the place text, or a whole folded literal, is never sent."""
    if fold(name.genus) in places:
        return _withheld(PLACE_WORD)
    if name.subgenus and fold(name.subgenus) in places:
        return ScientificName(name.genus, None, (), None, "GENUS", None, PLACE_WORD)
    for index, epithet in enumerate(name.epithets):
        if fold(epithet) in places:
            kept = name.epithets[:index]
            rank = "SPECIES" if kept else "GENUS"
            return ScientificName(
                name.genus, name.subgenus, kept, None, rank, None, PLACE_WORD
            )
    return name


def scientific_name(
    literal: str, place_text: Sequence[str] = ()
) -> ScientificName | None:
    """The scientific name a taxon literal writes, or None when it writes none
    (HARNESS.md section 6). `place_text` is the reading's place-field literals
    and unassigned locality text: their words leave the authorship, and a name
    part equal to one is withheld, marking the name (the coordinator's rulings
    of 02:07Z and 03:24Z on 2026-09-26). A name with no genus left sends
    nothing.

    The literal must begin with a title-case genus; a qualifier before it, or a
    question mark on it, leaves it in doubt, so nothing is sent. The words
    after it are read as a parenthesized subgenus, written out or abbreviated;
    epithets in lower case, with any accents or inner hyphens, or an old
    capitalized epithet; a subspecies or variety marker with its epithet; and a
    bounded author-year authorship. A qualifier right after the genus makes a
    genus-level identification. A clause naming a person cuts the literal.
    Any other word that ends the name (a preposition listed as an end, a listed
    sex, stage, type-status or nomenclatural word, a listed month, a date) ends
    the reading, unless an epithet-shaped word follows it. Any other word the
    reader does not take, the words that change the taxon and the other listed
    prepositions, articles and conjunctions among them, marks the name read
    only in part. A word the literal does not write is never sent, and neither
    is text that is no name (PLAN 4.8)."""
    places = _place_words(place_text)
    words = _words(literal)
    name = _read(words)[0]
    if name is None or not name.genus or not places:
        return name
    again = _read(_without_places(words, places))[0]
    if again is not None and _slots(again) == _slots(name):
        name = again
    else:
        # The drop changed the name: it is asked as first read, without its
        # authorship, and marked (the steward's review of round 4).
        name = replace(name, authorship=None, partly_read=PLACE_WORD)
    return _without_place_parts(name, places)


def without_place_words(literal: str, place_text: Sequence[str]) -> str:
    """The literal without the place words its authorship holds, so that
    reading it gives the name `scientific_name` reads with that place text,
    when no name part is place text."""
    words = _words(literal)
    kept = _without_places(words, _place_words(place_text))
    return literal if kept == words else " ".join(kept)


def taxonomy_lookup(
    lookup: Callable[[str], Lookup],
    literal: str,
    place_text: Sequence[str],
    blobs: BlobStore,
) -> Lookup:
    """The workflow's taxonomy lookup, through an adapter that takes a literal
    (HARNESS.md section 6; the coordinator's rulings of 02:07Z, 03:24Z and
    03:31Z on 2026-09-26). A name with nothing it may send, its genus in doubt
    or place text, makes no request and goes to review. A name marked for
    place text is asked as far as it may be, and never succeeds. Any other
    literal goes without the place words its authorship holds."""
    name = scientific_name(literal, place_text)
    if name is not None and not name.genus:
        return withheld_lookup(literal, name.partly_read, blobs)
    if name is not None and name.partly_read == PLACE_WORD:
        found = lookup(name.query)
        found.metadata["partly_read"] = PLACE_WORD
        if found.status == LookupStatus.SUCCESS:
            found.status = LookupStatus.AMBIGUOUS
        return found
    return lookup(without_place_words(literal, place_text))


def _read(words: list[str]) -> tuple[ScientificName | None, tuple[int, int] | None]:
    """The name `words` write, or None, and where its authorship lies among
    them."""
    for index, word in enumerate(words):
        if _word(word) in CLAUSES:
            words = words[:index]
            break
    if not words or any(len(word) > MAX_WORD_LENGTH for word in words):
        return None, None
    cut = words
    # A qualifier or a question mark before the genus, or on it, leaves the
    # genus in doubt: nothing is sent (the coordinator's reading of 01:11Z and
    # its confirmation of 03:31Z on 2026-09-26).
    doubt = None
    if _qualifier(words[0]) in DOUBT_MARKERS or words[0] == "?":
        doubt, words = _qualifier(words[0]) or "?", words[1:]
    if not words:
        return None, None
    first = words[0]
    if "?" in first:
        doubt, first = doubt or "?", first.replace("?", "")
    genus = _core(first)
    if not GENUS.match(genus) or genus.lower() in NOT_NAMES:
        return None, None
    if doubt:
        return _withheld(doubt), None
    subgenus, epithets, marker, rank, partly = None, [], None, "GENUS", None
    ended, rest = _ends(first), words[1:]
    if not ended and rest and SUBGENUS.match(rest[0].rstrip(",;:")):
        subgenus = SUBGENUS.match(rest[0].rstrip(",;:")).group(1)
        ended, rest = rest[0][-1:] in {",", ";", ":"}, rest[1:]
    if not ended and _takes(rest):
        epithets, rank = [_core(rest[0])], "SPECIES"
        ended, rest = _ends(rest[0]), rest[1:]
        # A marker without its epithet, or one the reader does not take, is
        # left for the fail-closed check below.
        if not ended and rest:
            core = _core(rest[0])
            if core in MARKERS and _takes(rest[1:]):
                epithets.append(_core(rest[1]))
                marker, rank = rest[0], "VARIETY" if core == "var" else "SUBSPECIES"
                rest = rest[2:]
            elif _takes(rest):
                epithets.append(core)
                rank, rest = "SUBSPECIES", rest[1:]
    if partly is None and rest and _hybrid(rest[0]):
        partly = "hybrid"
    authorship, span = None, None
    if partly is None and rest and (
        not _ends_name(rest[0]) or _word(rest[0]) in PARTICLES
    ):
        start = len(cut) - len(rest)
        authorship, used = _authorship(rest)
        span = (start, start + used) if authorship else None
        rest = rest[used:]
    # Fail closed: whatever follows must end the name. An epithet-shaped word
    # after an end word may be the name's own, so it marks the name too (the
    # steward's review of round 4), but after a qualifier right after the genus,
    # the 01:11Z reading's genus-level identification.
    if partly is None and rest:
        if not _ends_name(rest[0]):
            partly = _core(rest[0]) or rest[0]
        elif epithets or not _qualifier(rest[0]):
            after = next((word for word in rest[1:] if not _ends_name(word)), None)
            if after is not None and _epithet(after):
                partly = _core(after)
    name = ScientificName(
        genus, subgenus, tuple(epithets), marker, rank, authorship, partly
    )
    return name, span


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
    with no homonym conflict for the label's name, which is S4's reading of
    whose conflict counts (HARNESS.md section 6). GBIF v2's accepted usage is
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


def _encodable(text: str) -> bool:
    """Whether a string can be written as UTF-8: a lone surrogate cannot."""
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _storable(value, limit: int = MAX_DEPTH) -> bool:
    """Whether a parsed body can be stored: it nests no deeper than `limit`,
    and every string in it, key or value, can be encoded. Checked without
    recursion, so a body the record cannot store is refused first (the
    steward's reviews of rounds 2 to 4)."""
    stack = [(value, 1)]
    while stack:
        item, depth = stack.pop()
        if isinstance(item, str):
            if not _encodable(item):
                return False
        elif isinstance(item, (dict, list)):
            if depth > limit:
                return False
            if isinstance(item, dict):
                if not all(_encodable(key) for key in item):
                    return False
                stack.extend((child, depth + 1) for child in item.values())
            else:
                stack.extend((child, depth + 1) for child in item)
    return True


# Characters no name holds: control, format, surrogate, private-use and
# unassigned code points, and line and paragraph separators (the steward's
# reviews of rounds 3 and 4).
HIDDEN = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})


def _variation_selector(ch: str) -> bool:
    code = ord(ch)
    return (
        0xFE00 <= code <= 0xFE0F
        or 0xE0100 <= code <= 0xE01EF
        or 0x180B <= code <= 0x180F
    )


def _text_ok(value) -> bool:
    """A string within the name bound, with no hidden character: no control,
    format, surrogate, private-use or unassigned code point, line or paragraph
    separator, or variation selector, so nothing hidden reaches the harness
    (the steward's reviews of rounds 3 and 4)."""
    return (
        isinstance(value, str)
        and len(value) <= MAX_NAME_LENGTH
        and not any(
            unicodedata.category(ch) in HIDDEN or _variation_selector(ch)
            for ch in value
        )
    )


def _one_of(value, values: frozenset) -> bool:
    return value is None or (isinstance(value, str) and value in values)


def _shape_ok(payload: dict) -> bool:
    """The parts the decision reads have the types GBIF documents, within their
    bounds: keys of letters and digits, ranks and statuses GBIF and
    ChecklistBank document, and names without control or format characters.
    Anything else is `malformed_response`, never an exception."""

    def key_ok(key) -> bool:
        if type(key) is int:
            return 0 <= key < MAX_KEY
        return isinstance(key, str) and bool(KEY.match(key))

    def usage_ok(usage) -> bool:
        if usage is None:
            return True
        return (
            isinstance(usage, dict)
            and (usage.get("key") is None or key_ok(usage["key"]))
            and _text_ok(usage.get("name"))
            and bool(usage["name"].strip())  # A usage names itself: the final value.
            and all(
                usage.get(field) is None or _text_ok(usage[field])
                for field in ("canonicalName", "authorship")
            )
            and _one_of(usage.get("rank"), GBIF_RANKS)
            and _one_of(usage.get("status"), GBIF_STATUSES)
        )

    def classification_ok(classification) -> bool:
        return classification is None or (
            isinstance(classification, list)
            and all(
                isinstance(level, dict)
                and (level.get("name") is None or _text_ok(level["name"]))
                and _one_of(level.get("rank"), GBIF_RANKS)
                for level in classification
            )
        )

    def match_ok(diagnostics) -> bool:
        return isinstance(diagnostics, dict) and _one_of(
            diagnostics.get("matchType"), GBIF_MATCH_TYPES | {"NONE"}
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
            and match_ok(other.get("diagnostics"))
            and isinstance(other.get("usage"), dict)
            and usage_ok(other["usage"])
            and classification_ok(other.get("classification"))
            for other in alternatives or []
        )
    )


USAGE_FIELDS = ("key", "name", "canonicalName", "authorship", "rank", "status")


def selectable(usage: dict) -> dict:
    """A candidate is a usage's documented fields alone, with `scientificName`
    always GBIF's own `name`: the reviewer's `taxonomy_resolution` decision
    selects by it and stores it (api.py), and unwraps a candidate's "usage", so
    neither a field a body adds nor a usage nested in one reaches it (the
    steward's reviews of rounds 2 and 3)."""
    kept = {field: usage[field] for field in USAGE_FIELDS if field in usage}
    kept["scientificName"] = usage.get("name")
    return kept


def _alternative(other: dict) -> dict:
    """An alternative as a candidate: its usage, its diagnostics and its
    classification, and nothing else."""
    return {
        "usage": selectable(other["usage"]),
        "diagnostics": other["diagnostics"],
        "classification": other.get("classification"),
    }


def withheld_lookup(literal: str, reason: str, blobs: BlobStore) -> Lookup:
    """A name with nothing it may send, its genus in doubt or place text:
    `ambiguous`, with no request, so it goes to review (the coordinator's
    reading of 01:11Z and rulings of 03:24Z and 03:31Z on 2026-09-26). Its
    record of what was withheld and why is stored with its digest, so the run's
    evidence check reads it like any other lookup (the steward's review of
    round 5)."""
    record = json.dumps(
        {"withheld": reason, "verbatim_name": literal}, sort_keys=True
    ).encode()
    return Lookup(
        provider="gbif",
        adapter_version="species-match-v2.3",
        query={},
        status=LookupStatus.AMBIGUOUS,
        raw_ref=blobs.put(record),
        digest=hashlib.sha256(record).hexdigest(),
        metadata={"verbatim_name": literal, "partly_read": reason},
    )


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
        if not parsed.genus:
            literal = name if isinstance(name, str) else ""
            return withheld_lookup(literal, parsed.partly_read, self.blobs)
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
                or not _storable(payload)
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
            ] + [_alternative(other) for other in alternatives[:MAX_ALTERNATIVES]]
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
                index = parse_json(metadata.content)
                if not isinstance(index, dict) or not _storable(index):
                    # Bounded like the match body, so the record can be stored.
                    result.status = LookupStatus.MALFORMED
                else:
                    result.metadata["index"] = index
                    result.metadata["metadata_raw_ref"] = self.blobs.put(
                        metadata.content
                    )
        except httpx.TimeoutException:
            result.status = LookupStatus.TIMEOUT
        except httpx.HTTPError:
            result.status = LookupStatus.PROVIDER
        except (ValueError, TypeError, AttributeError, KeyError, RecursionError):
            result.status = LookupStatus.MALFORMED
        return result
