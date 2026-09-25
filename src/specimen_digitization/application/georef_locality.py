"""Reading locality text for the retrospective georeferencing tool (GEO.md 1).

One locality literal, exactly as a reading has it, becomes the parts the later
tiers compare locally: names with their label notations read (G29), the headings
of slopes and offsets, elevation phrases kept as written (G27, G38; G41's
conversion and fill happen in S4's later layer) and text that is no place.
Nothing here makes a request or decides an outcome, and the literal is kept
verbatim (G27). Nothing it produces leaves the tool except through PLAN 4.8's
filter, which expands notations itself after its cuts. The one-letter gate
compares full names only, never codes or abbreviations (the coordinator's reading
of G34, 2026-09-24).
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
# A line ending in one of these words runs on into the next line.
JOINERS = frozenset({*FEATURES, *UNITS_BEFORE, *LINKS})
# Unicode categories fold drops, and those that make a character a number.
MARKS = frozenset({"Mn", "Me", "Cf"})
NUMERALS = frozenset({"Nd", "Nl", "No"})
# The Hangul fillers are letters by category but show nothing, so fold drops them.
FILLERS = frozenset("\u115f\u1160\u3164\uffa0")
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
# A heading followed by "slope", "side" or "flank" never heads an offset: in
# "1500 m N slope Mt. Apo" the "1500 m" is an elevation.
OFFSET = re.compile(
    r"^(?P<distance>\d+(?:[.,]\d+)*)\s*"
    r"(?P<unit>kms?|kilomet(?:er|re)s?|mi|miles?|m|met(?:er|re)s?)\b\.?\s+"
    r"(?P<head>[A-Za-z][A-Za-z.\-]*)\s+(?!(?:slope|side|flank)s?\b)"
    r"(?:(?:of|from)\s+)?(?P<rest>\S.*)$",
    re.I,
)
# A number is read whole, its dots and commas included: "1,463", "1.463",
# "6.400", "0,5", "1463,5" (G36).
NUMBER = r"\d+(?:[.,]\d+)*"
# Dashes of every kind: hyphen-minus, hyphen, non-breaking hyphen, figure, en, em
# and horizontal-bar dashes, minus sign, and small and fullwidth hyphen-minus.
DASHES = "-\u2010\u2011\u2012\u2013\u2014\u2015\u2212\ufe58\ufe63\uff0d"
# A range joins its numbers by a dash of any kind or a slash, or by "to", or by
# "a", "and" or "y" between spaces: "4000-4500 ft", "4000—4500 ft", "1500 a 2000
# m", "entre 1500 y 2000 m".
RANGE = (
    rf"(?P<low>{NUMBER})"
    rf"(?:(?:\s*(?:[{DASHES}/]|to)\s*|\s+(?:a|and|y)\s+)(?P<high>{NUMBER}))?"
)
PREFIX = r"\b(?:elev(?:ation)?|alt(?:itude)?)\b\.?\s*:?\s*"
# An elevation has a prefix, a unit or both; a foot mark followed by a digit is
# a year ("'46"), not an elevation.
ELEVATION = re.compile(
    rf"(?P<prefix>{PREFIX})?{RANGE}(?:\s*"
    r"(?P<unit>ft\b\.?|feet\b|foot\b|['’′](?!\d)|m\b\.?|met(?:er|re)s?\b))?",
    re.I,
)
# Commas and semicolons separate parts. A comma is inside a number in a thousands
# group led by one to three digits ("1,463", "1,463,200") or before a one- or
# two-digit decimal ("0,5", "1463,5"); any other comma between digits separates:
# after a four-digit year even before three digits ("6-Sept-1946,640'"), and
# before four digits ("6-Sept-1946,6400'").
SEPARATOR = re.compile(r";|(?<!\d),|,(?!\d{1,3}(?!\d))|(?<=\d{4}),(?=\d{3}(?!\d))")
# Thousands groups of three digits marked all by commas or all by dots, with an
# optional decimal after the other mark: "1,463", "1,463,200", "1.463.200,5".
THOUSANDS = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{1,3}(?:\.\d{3})+(?:,\d+)?"
GROUPED = re.compile(THOUSANDS)
# A number is read only in a valid grouping: digits with at most one comma or dot
# ("1,463", "0,125", "1463,5"), or thousands groups. Any other grouping ("1,5,3",
# "12,34,567") is set aside.
VALID_NUMBER = re.compile(rf"\d+(?:[.,]\d+)?|{THOUSANDS}")
# An elevation needs a space, the part's start, one of these opening brackets
# (full-width ones too) or another elevation right before it; a number glued to
# other text may be a date's year ("12.IV.1948,95 m") or a range's upper number
# ("4000a4500 ft").
OPENINGS = "([{\uff08\uff3b\uff5b"
# After other text, two or four digits before a number's first comma or dot could
# be a year run into another number: "12 IV 1948,95 m", "IV 26,950 m".
YEAR_LEAD = re.compile(r"(?:\d\d|\d{4})[.,]")
# Four digits after a mark could be a date's year: "4.1948", "12.4.1948".
YEAR_TAIL = re.compile(r"[.,]\d{4}(?!\d)")
# A range's lower number that could be a year, two digits or four from 1700 to
# 2099, sets the range aside unless its prefix comes first: the coordinator's
# reading of G36 and G40 at 15:32Z on 2026-09-25.
YEAR = re.compile(r"\d\d|1[7-9]\d\d|20\d\d")
# Metres in a foot, exactly (G41): beside an elevation it converts to, such a range
# reads, since a year would not convert (the same reading, extended at 17:40Z).
FOOT = 0.3048
# A number after another number with only words or marks between them may be a
# range's upper number, joined by one no range join lists: "4000 hasta 4500 ft",
# "4000 ~ 4500 m".
TOP_ALONE = re.compile(r"\d\s+(?:[^\d\s]+\s+)+$")
# The brackets an elevation leaves empty: "Mt. Apo (1463 m)", full-width ones too.
EMPTY_BRACKETS = re.compile(
    r"[(\uff08]\s*[)\uff09]|[\[\uff3b]\s*[\]\uff3d]|[{\uff5b]\s*[}\uff5d]"
)
# A number beside another digit group across a space ("4 800 ft.") has an unsure
# grouping, so it is set aside rather than cut short. A two-digit year after an
# apostrophe ("'46 850 m") is no such group, but one digit is ("'4 800 ft.").
GROUP_BEFORE = re.compile(r"(?<!\d)(?!(?<=['‘’′])\d\d\s)\d{1,3}\s+$")
GROUP_AFTER = re.compile(r"\s+\d{3}(?!\d)")


@dataclass(frozen=True, slots=True)
class Heading:
    """A compass heading as written, with its bearing in degrees."""

    text: str
    degrees: float


@dataclass(frozen=True, slots=True)
class Elevation:
    """An elevation phrase as written (G27, G38): the numbers whole as written,
    the unit as "ft" or "m", or None when the label gives none. Nothing is
    converted here: G41's conversion and fill happen in S4's later layer."""

    text: str
    low: str
    high: str | None
    unit: str | None


@dataclass(frozen=True, slots=True)
class Part:
    """One place in a locality literal: `name` as written without its unit word,
    `readings` the full names it is compared by locally, most specific first, and
    `key` the comparison key of the first reading. None of these is sent as it
    stands; requests come only through PLAN 4.8's filter."""

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
    """One literal's reading: georeferencing evidence, never the elevation fields,
    which settle from the harness's own reading of the label. A phrase set aside
    as unsure stays in `unplaced`, so an empty `elevations` is not "no elevation
    stated" (GEO.md 1)."""

    verbatim: str
    parts: tuple[Part, ...]
    elevations: tuple[Elevation, ...]
    institutions: tuple[str, ...]
    unplaced: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Variant:
    """Readers' literals whose parts share their keys (G19, G20). Each literal is
    kept as written, with its observation id and its own reading, headings,
    offsets and elevations included, in the order the literals came."""

    keys: tuple[str, ...]
    localities: tuple[LocalityText, ...]
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
    """Casefold, strip diacritics, other marks and format characters (Unicode Mn,
    Me and Cf, such as a variation selector or a zero-width space) and the
    invisible Hangul fillers, before and after case folding (U+0345 would fold to
    an iota), and turn anything else but letters and digits into single spaces:
    "Chimaltenángo," folds to "chimaltenango"."""
    kept = "".join(
        c if c.isalnum() else " " for c in _unmarked(_unmarked(text).casefold())
    )
    return " ".join(kept.split())


def _unmarked(text: str) -> str:
    """The text's compatibility form without marks, format characters or Hangul
    fillers."""
    return "".join(
        c
        for c in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(c)
        and unicodedata.category(c) not in MARKS
        and c not in FILLERS
    )


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
    keys, counted up to `cap`. A cell farther than `cap` from the diagonal holds
    at least `cap`, so only the band within it is computed, and the work grows
    with the keys' length rather than its square."""
    if a == b:
        return 0
    if abs(len(a) - len(b)) >= cap:
        return cap
    previous = {j: j for j in range(min(len(b), cap) + 1)}
    for i, left in enumerate(a, 1):
        current: dict[int, int] = {}
        for j in range(max(0, i - cap), min(len(b), i + cap) + 1):
            if j == 0:
                current[0] = min(i, cap)
                continue
            current[j] = min(
                previous.get(j, cap) + 1,
                current.get(j - 1, cap) + 1,
                previous.get(j - 1, cap) + (left != b[j - 1]),
                cap,
            )
        if min(current.values()) >= cap:
            return cap
        previous = current
    return previous.get(len(b), cap)


def is_full_name(name: str) -> bool:
    """True when every word is a notation in the table or a full word (no period
    inside it, no period after four letters or fewer, no digit or other numeral,
    and not three capitals or fewer: "PH", "PHL", "RP"), and some word is not a
    notation."""
    words = [word.strip(",;:") for word in name.split()]
    names = [word for word in words if not _notation(word)]
    return bool(names) and all(_full_word(word) for word in names)


def one_letter_apart(a: str, b: str) -> bool:
    """The one-letter gate on two names, as the coordinator reads G34 (2026-09-24):
    both full names, their keys exactly one letter apart."""
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
    numbered = False
    for segment in _segments(text):
        institutions += [m.group(0) for m in INSTITUTIONS.finditer(segment)]
        segment = " ".join(INSTITUTIONS.sub(" ", segment).split())
        # A part right after one that holds a number may start with that number's
        # year: "July 4, 1946.9500 ft", "IV-26" / "1948.950 m".
        after_number, numbered = numbered, _numeral(segment)
        offset = _offset(segment)
        if offset is not None:
            piece, found = offset
            elevations += found
            pieces.append(piece)
            continue
        segment, found = _elevations(segment, after_number)
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
    """Group (literal, observation id) pairs by their parts' keys, in order; each
    literal keeps its own reading."""
    groups: dict[tuple[str, ...], tuple[list[LocalityText], list[str], list[str]]] = {}
    for literal, observation_id in literals:
        reading = read_locality(literal)
        keys = tuple(part.key for part in reading.parts)
        readings, observations, written = groups.setdefault(keys, ([], [], []))
        readings.append(reading)
        observations.append(observation_id)
        written.append(literal)
    return tuple(
        Variant(keys, tuple(readings), tuple(observations), tuple(written))
        for keys, (readings, observations, written) in groups.items()
    )


def _segments(text: str) -> Iterable[str]:
    """Lines joined where a word needs the next one (a feature notation, a unit
    written before its name, or a linking word) and where a line starts with "of"
    in any case ("OF MT. APO"; "of" begins no name) or a lowercase "de" or "del"
    (a capitalized one begins a name, "Del Carmen"), then split into parts. Lines
    are kept as word lists, so the joins stay linear in the text's length."""
    lines: list[list[str]] = []
    carry: list[str] = []
    for line in text.splitlines():
        words = line.split()
        if not words:
            continue
        link = fold(words[0])
        if not carry and lines and link in LINKS and (link == "of" or words[0].islower()):
            carry = lines.pop()
        carry += words
        if fold(carry[-1]) in JOINERS:
            continue
        lines.append(carry)
        carry = []
    if carry:
        lines.append(carry)
    for words in lines:
        for segment in SEPARATOR.split(" ".join(words)):
            if segment.strip():
                yield " ".join(segment.split())


def _offset(segment: str) -> tuple[_Piece, list[Elevation]] | None:
    """An offset ("5 km NE of Yepocapa") and the elevation phrases after it. Its
    place follows the rules for any part: a place with a digit or without a
    letter is kept aside with its offset. A malformed distance ("1,5,3 km") is no
    offset, so the segment is kept aside whole."""
    match = OFFSET.match(segment)
    bearing = _bearing(match["head"]) if match else None
    if match is None or bearing is None or not VALID_NUMBER.fullmatch(match["distance"]):
        return None
    rest, found = _elevations(match["rest"])
    rest = rest.strip(" ,;:")
    if not _placeable(rest):
        return _Piece("unplaced", segment), found
    unit = match["unit"].casefold()
    piece = _place(rest, segment)
    piece.heading = Heading(match["head"], bearing)
    piece.relation = "offset"
    piece.distance = match["distance"]
    piece.distance_unit = "km" if unit[0] == "k" else "mi" if unit[:2] == "mi" else "m"
    return piece, found


def _placeable(text: str) -> bool:
    """A place's text has a letter and no numeral, of any script ("½" too):
    gazetteer names carry no digits."""
    return any(c.isalpha() for c in text) and not _numeral(text)


def _numeral(text: str) -> bool:
    """A numeral of any script, as written or in its compatibility form: "½", "Ⅳ"
    (whose form is the letters "IV"), or "㏠" (whose form is "1日")."""
    forms = (text, unicodedata.normalize("NFKD", text))
    return any(unicodedata.category(c) in NUMERALS for form in forms for c in form)


def _unsure(
    segment: str, match: re.Match[str], paired: bool, after: bool, since: int, converts: bool
) -> bool:
    """Whether an elevation's number is unsure, so the phrase is set aside rather
    than read (GEO.md 1, "Unsure numbers"):
    - a malformed grouping ("1,5,3 m"), or four digits after a mark ("4.1948");
    - glued to the text before it, where no space, part start, opening bracket or
      other elevation (`paired`) comes first ("12.IV.1948,95 m", "4'800 m");
    - a range, or first digits that could be a year, after other text or right
      after a part that holds a number (`after`), unless its prefix or another
      elevation comes first ("Sept. 1946 - 850 m", "July 4, 1946.9500 ft");
    - a range that runs downward, or whose upper number has a decimal
      ("1946 - 850 m", "4-1948,95 m"), or whose lower number could be a year,
      unless its prefix comes first or it converts with the elevation beside it
      (`converts`: "1800-2200 m" is set aside, "Elev. 1800-2200 m" and
      "6000-7000 ft 1829-2134 m" read);
    - after another number with only words or marks between them, since the
      last elevation read (`since`) ("4000 ~ 4500 m", "Camp 3 at 1500 m");
    - beside another digit group across a space ("4 800 ft.", "Elev. 4 800 ft.")."""
    low, high = match["low"], match["high"]
    numbers = (low, high) if high else (low,)
    if not all(VALID_NUMBER.fullmatch(number) for number in numbers):
        return True
    if any(YEAR_TAIL.search(number) for number in numbers):
        return True
    start = match.start()
    if start and not (segment[start - 1].isspace() or segment[start - 1] in OPENINGS or paired):
        return True
    if after and not paired and not match["prefix"] and (high or YEAR_LEAD.match(low)):
        return True
    if high and (_decimal(high) or _size(low) > _size(high)):
        return True
    if high and not converts and not match["prefix"] and YEAR.fullmatch(low):
        return True
    if not paired and TOP_ALONE.search(segment, max(since, start - 40), start):
        return True
    # Searched only in the few characters before the number, so a long segment
    # stays linear: segments hold single spaces, so a digit group and its space
    # take at most four characters.
    begin = match.start("low")
    before = GROUP_BEFORE.search(segment, max(0, begin - 8), begin)
    end = match.end("high") if high else match.end("low")
    return bool((before and re.match(r"\d{3}(?!\d)", low)) or GROUP_AFTER.match(segment, end))


def _size(number: str) -> tuple[int, str]:
    """A number's size, for a range's order, compared as digits rather than
    converted: thousands marks dropped, a decimal cut at its mark."""
    whole = number.split(",")[0].split(".")[0] if _decimal(number) else re.sub("[.,]", "", number)
    whole = whole.lstrip("0")
    return len(whole), whole


def _decimal(number: str) -> bool:
    """A number with a comma or dot that is not in thousands groups: "1463,5",
    "1946,63", "1948.950"."""
    return ("," in number or "." in number) and not GROUPED.fullmatch(number)


def _unit(match: re.Match[str]) -> str | None:
    """An elevation phrase's unit, "m" or "ft", or None when it gives none."""
    unit = match["unit"]
    return ("m" if unit.casefold().startswith("m") else "ft") if unit else None


def _converts(a: re.Match[str], b: re.Match[str]) -> bool:
    """Whether two elevation phrases, one in feet and one in metres, give the same
    heights: each end by the exact factor, within the larger of 10 m and 2% of the
    metric value. Nothing converted is kept."""
    if {_unit(a), _unit(b)} != {"ft", "m"} or (a["high"] is None) != (b["high"] is None):
        return False
    feet, metres = (a, b) if _unit(a) == "ft" else (b, a)
    for end in ("low", "high"):
        if feet[end] is None:
            continue
        foot, metre = _value(feet[end]), _value(metres[end])
        if foot is None or metre is None or abs(foot * FOOT - metre) > max(10, 0.02 * metre):
            return False
    return True


def _value(number: str) -> float | None:
    """A valid number's value, or None past an elevation's length: a decimal reads
    its mark as the point, thousands marks are dropped, and in a grouped number
    with a decimal the second kind of mark is the point ("1.463,5")."""
    if len(number) > 12 or not VALID_NUMBER.fullmatch(number):
        return None
    if _decimal(number):
        return float(number.replace(",", "."))
    if "," in number and "." in number:
        grouping, point = (",", ".") if number.index(",") < number.index(".") else (".", ",")
        return float(number.replace(grouping, "").replace(point, "."))
    return float(number.replace(",", "").replace(".", ""))


def _elevations(segment: str, after_number: bool = False) -> tuple[str, list[Elevation]]:
    """Elevation phrases out of the segment, each as written (G27, G38).
    `after_number` says the part before this one holds a number."""
    found: list[Elevation] = []
    rest: list[str] = []
    last = 0
    # Opening brackets at the part's start are no text before a number.
    lead = len(segment) - len(segment.lstrip(" " + OPENINGS))
    phrases = [match for match in ELEVATION.finditer(segment) if match["prefix"] or match["unit"]]
    # Neighbours, one in feet and one in metres, that convert to each other.
    converting = {
        index
        for first, (a, b) in enumerate(zip(phrases, phrases[1:]))
        if b.start() - a.end() <= 1 and _converts(a, b)
        for index in (first, first + 1)
    }
    for index, match in enumerate(phrases):
        # A mark right after another elevation pairs the two: "4800 ft/1463 m".
        paired = bool(found) and match.start() - last <= 1
        after = after_number or match.start() > lead
        if _unsure(segment, match, paired, after, last, index in converting):
            continue
        found.append(Elevation(match.group(0).strip(), match["low"], match["high"], _unit(match)))
        rest.append(segment[last : match.start()])
        last = match.end()
    rest.append(segment[last:])
    return " ".join(EMPTY_BRACKETS.sub(" ", " ".join(rest)).split()), found


def _piece(segment: str) -> _Piece:
    if not _placeable(segment):
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
        if not any(c.isalpha() for c in rest):  # nothing, or no letter: "E. slope -"
            return _Piece("heading", segment, heading=heading, relation=_relation(match))
        piece = _place(rest, segment)
        piece.heading, piece.relation = heading, _relation(match)
        return piece
    return _place(segment, segment)


def _place(written: str, text: str) -> _Piece:
    """A place piece: the unit word, before or after the name, leaves the name. A
    name left with no letter ("Depto. de ?"), keying to nothing ("Prov. Dept.") or
    only a linking word is set aside."""
    words = written.split()
    unit = None
    if len(words) > 1 and fold(words[0]) in UNIT_WORDS:
        unit, words = UNIT_WORDS[fold(words[0])], words[1:]
        if len(words) > 1 and fold(words[0]) in LINKS:
            words = words[1:]
    elif len(words) > 1 and fold(words[-1]) in UNIT_WORDS:
        unit, words = UNIT_WORDS[fold(words[-1])], words[:-1]
    name = " ".join(words).strip(" ,;:")
    if not comparison_key(name) or all(fold(word) in LINKS for word in name.split()):
        return _Piece("unplaced", text)
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
    if not letters or _numeral(word) or re.search(r"\.\w", word):
        return False
    if word.endswith(".") and letters <= 4:
        return False
    return not (word.isupper() and letters <= 3)
