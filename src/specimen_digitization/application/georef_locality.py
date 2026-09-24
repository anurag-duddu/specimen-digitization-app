"""Reading locality text for the retrospective georeferencing tool (GEO.md 1).

One locality literal, exactly as a reading has it, becomes the parts the later
tiers compare locally: names with their label notations read (G29), the headings
of slopes and offsets, elevation phrases kept as written (G22) and text that is
no place. Nothing here makes a request or decides an outcome, and the literal is
kept verbatim (G27). The readings built here serve local comparison only: what a
tier sends is the literal passed through PLAN 4.8's filter, which expands
notations itself after its cuts. G34's one-letter gate compares full names only,
never codes or abbreviations (the coordinator's reading, 2026-09-24).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

# Unit words by their folded form (G29): written after the name ("Davao Prov.")
# or before it ("Mun. Yepocapa"). A bare unit word joins the part it points to.
UNITS_AFTER = {
    **dict.fromkeys(("prov", "province"), "province"),
    **dict.fromkeys(("dept", "department"), "department"),
    **dict.fromkeys(("co", "county"), "county"),
    "state": "state",
    "region": "region",
}
UNITS_BEFORE = {
    **dict.fromkeys(("mun", "municipio", "municipality"), "municipality"),
    **dict.fromkeys(("depto", "departamento"), "department"),
    "provincia": "province",
    "estado": "state",
}
UNIT_WORDS = {**UNITS_AFTER, **UNITS_BEFORE}
UNIT_NAMES = {
    "province": "Province",
    "department": "Department",
    "county": "County",
    "municipality": "Municipality",
    "state": "State",
    "region": "Region",
}
# A "de", "del" or "of" after a leading unit word links it to the name.
LINKS = frozenset({"de", "del", "of"})
# Feature notations: the word they read as and the feature they name.
FEATURES = {"mt": ("Mount", "mountain"), "mount": ("Mount", "mountain")}
COUNTRIES = ((re.compile(r"P\.\s?I\.?", re.I), "Philippine Islands"),)
# The museum's own names on its labels, never a place.
INSTITUTIONS = re.compile(r"\b(?:CNHM|FMNH)\b\.?", re.I)

# The 16 compass points and the words for the eight main ones, in degrees.
POINTS = {
    point: index * 22.5
    for index, point in enumerate(
        "n nne ne ene e ese se sse s ssw sw wsw w wnw nw nnw".split()
    )
}
HEADING_WORDS = {
    "north": 0.0,
    "northeast": 45.0,
    "east": 90.0,
    "southeast": 135.0,
    "south": 180.0,
    "southwest": 225.0,
    "west": 270.0,
    "northwest": 315.0,
}
RELATION = r"(?P<relation>slope|side|flank)s?"
LEADING_HEADING = re.compile(
    rf"^(?P<head>[A-Za-z.\-]+?)(?P<gap>\s*){RELATION}\b\.?(?:\s+of\b)?[\s,]*(?P<rest>.*)$",
    re.I,
)
TRAILING_HEADING = re.compile(
    rf"^(?P<rest>.+?)[\s,]+(?P<head>[A-Za-z.\-]+?)(?P<gap>\s*){RELATION}\.?$", re.I
)
OFFSET = re.compile(
    r"^(?P<distance>\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>kms?|kilomet(?:er|re)s?|mi|miles?|m|met(?:er|re)s?)\b\.?\s+"
    r"(?P<head>[A-Za-z][A-Za-z.\-]*)\s+(?:(?:of|from)\s+)?(?P<rest>\S.*)$",
    re.I,
)
NUMBER = r"\d{1,3}(?:,\d{3})+|\d+"
RANGE = rf"(?P<low>{NUMBER})(?:\s*(?:-|–|to)\s*(?P<high>{NUMBER}))?"
PREFIX = r"\b(?:elev(?:ation)?|alt(?:itude)?)\b\.?\s*:?\s*"
# An elevation has a prefix, a unit or both; a foot mark followed by a digit is
# a year ("'46"), not an elevation.
ELEVATION = re.compile(
    rf"(?P<prefix>{PREFIX})?{RANGE}(?:\s*"
    r"(?P<unit>ft\b\.?|feet\b|foot\b|['’′](?!\d)|m\b\.?|met(?:er|re)s?\b))?",
    re.I,
)
# Commas and semicolons separate parts; a comma inside "1,463" does not.
SEPARATOR = re.compile(r";|(?<!\d),|,(?!\d{3}(?!\d))")


@dataclass(frozen=True, slots=True)
class Heading:
    """A compass heading as written, with its bearing in degrees."""

    text: str
    degrees: float


@dataclass(frozen=True, slots=True)
class Elevation:
    """An elevation phrase as written (G22): the numbers as written, the unit as
    "ft" or "m", or None when the label gives none. Nothing is converted."""

    text: str
    low: str
    high: str | None
    unit: str | None


@dataclass(frozen=True, slots=True)
class Part:
    """One place in a locality literal: `name` as written without its unit word,
    `readings` the full names to search, most specific first, and `key` the
    comparison key of the first reading."""

    text: str
    name: str
    readings: tuple[str, ...]
    key: str
    full_name: bool
    unit: str | None = None
    feature: str | None = None
    heading: Heading | None = None
    relation: str | None = None
    distance: str | None = None
    distance_unit: str | None = None


@dataclass(frozen=True, slots=True)
class LocalityText:
    verbatim: str
    parts: tuple[Part, ...]
    elevations: tuple[Elevation, ...]
    institutions: tuple[str, ...]
    unplaced: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Variant:
    """Readers' literals whose parts share their keys, each kept as written with
    its observation id (G19, G20); `locality` is the first literal's reading."""

    keys: tuple[str, ...]
    locality: LocalityText
    observations: tuple[str, ...]
    literals: tuple[str, ...]


@dataclass(slots=True)
class _Piece:
    kind: str  # "place", "unit", "heading" or "unplaced"
    text: str
    name: str = ""
    unit: str | None = None
    unit_first: bool = False
    heading: Heading | None = None
    relation: str | None = None
    distance: str | None = None
    distance_unit: str | None = None


def fold(text: str) -> str:
    """Casefold, strip diacritics and turn anything but letters and digits into
    single spaces: "Chimaltenángo," folds to "chimaltenango"."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    kept = "".join(
        c if c.isalnum() else " " for c in decomposed if not unicodedata.combining(c)
    )
    return " ".join(kept.split())


def comparison_key(name: str) -> str:
    """The key names compare by: folded, feature notations read ("Mt." is
    "mount"), unit words dropped, with a link word after a leading one."""
    kept: list[str] = []
    after_unit = False
    for word in fold(name).split():
        word = FEATURES[word][0].casefold() if word in FEATURES else word
        if word in UNIT_WORDS:
            after_unit = not kept
        elif after_unit and word in LINKS:
            after_unit = False
        else:
            after_unit = False
            kept.append(word)
    return " ".join(kept)


def letters_apart(a: str, b: str, cap: int = 2) -> int:
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
                min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (left != right))
            )
        if min(current) >= cap:
            return cap
        previous = current
    return min(previous[-1], cap)


def is_full_name(name: str) -> bool:
    """True when every word is a notation in the table or a full word (no period
    inside it, no period after four letters or fewer, no digit, and not three
    capitals or fewer: "PH", "PHL", "RP"), and some word is not a notation."""
    words = [word.strip(",;:") for word in name.split()]
    names = [word for word in words if not _notation(word)]
    return bool(names) and all(_full_word(word) for word in names)


def one_letter_apart(a: str, b: str) -> bool:
    """G34's gate on two names: both full names, keys exactly one letter apart."""
    return (
        is_full_name(a)
        and is_full_name(b)
        and letters_apart(comparison_key(a), comparison_key(b)) == 1
    )


def read_locality(text: str) -> LocalityText:
    """Read one locality literal into its parts; the literal stays verbatim."""
    pieces: list[_Piece] = []
    elevations: list[Elevation] = []
    institutions: list[str] = []
    for segment in _segments(text):
        institutions += [m.group(0) for m in INSTITUTIONS.finditer(segment)]
        segment = " ".join(INSTITUTIONS.sub(" ", segment).split())
        offset = _offset(segment)
        if offset is not None:
            pieces.append(offset)
            continue
        segment, found = _elevations(segment)
        elevations += found
        segment = segment.strip(" ,;:")
        if segment:
            pieces.append(_piece(segment))
    _join(pieces)
    return LocalityText(
        verbatim=text,
        parts=tuple(_part(piece) for piece in pieces if piece.kind == "place"),
        elevations=tuple(elevations),
        institutions=tuple(institutions),
        unplaced=tuple(piece.text for piece in pieces if piece.kind != "place"),
    )


def variants(literals: Iterable[tuple[str, str]]) -> tuple[Variant, ...]:
    """Group (literal, observation id) pairs by their parts' keys, in order."""
    groups: dict[tuple[str, ...], tuple[LocalityText, list[str], list[str]]] = {}
    for literal, observation_id in literals:
        reading = read_locality(literal)
        keys = tuple(part.key for part in reading.parts)
        _, observations, written = groups.setdefault(keys, (reading, [], []))
        observations.append(observation_id)
        written.append(literal)
    return tuple(
        Variant(keys, reading, tuple(observations), tuple(written))
        for keys, (reading, observations, written) in groups.items()
    )


def _segments(text: str) -> Iterable[str]:
    """Lines joined where a notation needs the next word, then split into parts."""
    lines: list[str] = []
    carry = ""
    for line in text.splitlines():
        line = " ".join(f"{carry} {line}".split())
        words = line.split()
        if words and fold(words[-1]) in {*FEATURES, *UNITS_BEFORE}:
            carry = line
            continue
        carry = ""
        lines.append(line)
    if carry:
        lines.append(carry)
    for line in lines:
        for segment in SEPARATOR.split(line):
            if segment.strip():
                yield " ".join(segment.split())


def _offset(segment: str) -> _Piece | None:
    match = OFFSET.match(segment)
    bearing = _bearing(match["head"]) if match else None
    if match is None or bearing is None:
        return None
    unit = match["unit"].casefold()
    piece = _place(match["rest"], segment)
    piece.heading = Heading(match["head"], bearing)
    piece.relation = "offset"
    piece.distance = match["distance"]
    piece.distance_unit = "km" if unit[0] == "k" else "mi" if unit[:2] == "mi" else "m"
    return piece


def _elevations(segment: str) -> tuple[str, list[Elevation]]:
    """Elevation phrases out of the segment, each as written (G22)."""
    found: list[Elevation] = []
    rest: list[str] = []
    last = 0
    for match in ELEVATION.finditer(segment):
        if not (match["prefix"] or match["unit"]):
            continue
        unit = match["unit"]
        if unit:
            unit = "m" if unit.casefold().startswith("m") else "ft"
        found.append(Elevation(match.group(0).strip(), match["low"], match["high"], unit))
        rest.append(segment[last : match.start()])
        last = match.end()
    rest.append(segment[last:])
    return " ".join(" ".join(rest).split()), found


def _piece(segment: str) -> _Piece:
    if not any(c.isalpha() for c in segment) or any(c.isdigit() for c in segment):
        return _Piece("unplaced", segment)
    word = fold(segment)
    if word in UNIT_WORDS:
        return _Piece(
            "unit", segment, unit=UNIT_WORDS[word], unit_first=word in UNITS_BEFORE
        )
    for pattern in (LEADING_HEADING, TRAILING_HEADING):
        match = pattern.match(segment)
        heading = _heading(match) if match else None
        if heading is None:
            continue
        rest = match["rest"].strip(" ,;:")
        if not rest:
            return _Piece("heading", segment, heading=heading, relation=_relation(match))
        piece = _place(rest, segment)
        piece.heading, piece.relation = heading, _relation(match)
        return piece
    return _place(segment, segment)


def _place(written: str, text: str) -> _Piece:
    """A place piece: the unit word, before or after the name, leaves the name."""
    words = written.split()
    unit = None
    if len(words) > 1 and fold(words[0]) in UNIT_WORDS:
        unit, words = UNIT_WORDS[fold(words[0])], words[1:]
        if len(words) > 1 and fold(words[0]) in LINKS:
            words = words[1:]
    elif len(words) > 1 and fold(words[-1]) in UNIT_WORDS:
        unit, words = UNIT_WORDS[fold(words[-1])], words[:-1]
    name = " ".join(words).strip(" ,;:")
    if name.endswith(".") and not _abbreviated(name.split()[-1]):
        name = name[:-1]
    return _Piece("place", text, name=name, unit=unit)


def _join(pieces: list[_Piece]) -> None:
    """Bare unit words, then heading phrases, join the place they point to; one
    with no place to join is left unplaced."""
    for kind in ("unit", "heading"):
        for index, piece in enumerate(pieces):
            if piece.kind != kind:
                continue
            if kind == "unit":
                order = (index + 1, index - 1) if piece.unit_first else (index - 1, index + 1)
                found = _target(pieces, order, lambda p: p.unit is None)
            else:
                order = (index - 1, index + 1)
                found = _target(
                    pieces, order, lambda p: p.heading is None and _feature(p.name) is not None
                )
                if found is None:
                    found = _target(pieces, order, lambda p: p.heading is None)
            if found is None:
                piece.kind = "unplaced"
                continue
            target = pieces[found]
            if kind == "unit":
                target.unit = piece.unit
            else:
                target.heading, target.relation = piece.heading, piece.relation
            target.text = (
                f"{piece.text} {target.text}" if found > index else f"{target.text} {piece.text}"
            )
            piece.kind = "joined"
        pieces[:] = [piece for piece in pieces if piece.kind != "joined"]


def _target(pieces: list[_Piece], order: tuple[int, int], fits) -> int | None:
    """The first index in `order` holding a place that `fits`."""
    for index in order:
        if 0 <= index < len(pieces) and pieces[index].kind == "place" and fits(pieces[index]):
            return index
    return None


def _part(piece: _Piece) -> Part:
    reading = " ".join(
        FEATURES[fold(word)][0] if fold(word) in FEATURES else word
        for word in piece.name.split()
    )
    for pattern, country in COUNTRIES:
        if pattern.fullmatch(piece.name):
            reading = country
    readings = (
        (f"{reading} {UNIT_NAMES[piece.unit]}", reading) if piece.unit else (reading,)
    )
    return Part(
        text=piece.text,
        name=piece.name,
        readings=readings,
        key=comparison_key(readings[0]),
        full_name=is_full_name(piece.name),
        unit=piece.unit,
        feature=_feature(piece.name),
        heading=piece.heading,
        relation=piece.relation,
        distance=piece.distance,
        distance_unit=piece.distance_unit,
    )


def _feature(name: str) -> str | None:
    for word in name.split():
        if fold(word) in FEATURES:
            return FEATURES[fold(word)][1]
    return None


def _heading(match: re.Match[str]) -> Heading | None:
    """The heading of a slope phrase; a word run into its relation ("Eastside")
    is a name, while a reader's joined "ESlope" is still a heading."""
    head = match["head"]
    bearing = _bearing(head)
    letters = sum(c.isalpha() for c in head)
    if bearing is None or (not match["gap"] and not head.endswith(".") and letters > 3):
        return None
    return Heading(head, bearing)


def _bearing(head: str) -> float | None:
    letters = head.replace(".", "").replace("-", "").casefold()
    if letters in POINTS and len(letters) <= 3:
        return POINTS[letters]
    return HEADING_WORDS.get(letters.removesuffix("ern"))


def _relation(match: re.Match[str]) -> str:
    return match["relation"].casefold()


def _notation(word: str) -> bool:
    return fold(word) in FEATURES or fold(word) in UNIT_WORDS


def _abbreviated(word: str) -> bool:
    letters = sum(c.isalpha() for c in word)
    return (
        bool(re.search(r"\.\w", word))
        or (word.endswith(".") and letters <= 4)
        or _notation(word)
    )


def _full_word(word: str) -> bool:
    letters = sum(c.isalpha() for c in word)
    if any(c.isdigit() for c in word) or re.search(r"\.\w", word):
        return False
    if word.endswith(".") and letters <= 4:
        return False
    return not (word.isupper() and letters <= 3)
