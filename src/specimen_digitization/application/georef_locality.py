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
from bisect import bisect_left
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from fractions import Fraction

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
# ASCII letters and digits, once lowered: what fold keeps of ASCII text.
ASCII_WORDS = re.compile(r"[a-z0-9]+")
# The Hangul fillers are letters by category but show nothing, so fold drops them.
FILLERS = frozenset("\u115f\u1160\u3164\uffa0")
COUNTRIES = ((re.compile(r"P\.\s?I\.?", re.I), "Philippine Islands"),)
# The apostrophe-shaped modifier letters, which Python counts as letters and fold
# keeps; a two-digit year may follow one.
APOSTROPHE_LETTERS = "\u02bb\u02bc\u02bd"
# The museum's own names on its labels, never a place, matched on folded text so
# that any width or form of the letters is found ("CNHM", full-width too).
INSTITUTIONS = re.compile(r"\b(?:cnhm|fmnh)\b")
# The month words the Insects profile lists for PLAN 4.8's filter (S4's #183),
# folded: each month in full and abbreviated, in English and in Spanish, in the
# usual forms and older ones ("Sept.", "setiembre", "Agto."), and the Roman months
# I to XII (G29). A part of only these and the links between them is a month.
MONTHS = frozenset(
    (
        "january february march april may june july august september october"
        " november december jan feb mar apr jun jul aug sep sept oct nov dec"
        " enero febrero marzo abril mayo junio julio agosto septiembre setiembre"
        " octubre noviembre diciembre ene abr ago set dic agto sbre obre nbre dbre"
        " febr mzo ag i ii iii iv v vi vii viii ix x xi xii"
    ).split()
)

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
# The words a range joins its numbers by: a name of only these is no place.
JOINS = frozenset({"to", "a", "and", "y"})
# An elevation's prefix, in any case, then an optional colon. The coordinator's
# reading at 15:32Z on 2026-09-25 names "Elev.", "Alt." and the like, as the
# profile's notations list them: "Elev." is how the pilot's labels write it, and the
# Insects profile lists "Alt." and "el." (with its period). "Elevation", "Altitude",
# the forms without a period and the colon are S8's reading of "and the like".
PREFIX = r"\b(?:(?:elev(?:ation)?|alt(?:itude)?)\b\.?|el\.)\s*:?\s*"
# A prefix that ends the text before a number is that number's own, not text
# between it and the number before.
PREFIX_END = re.compile(rf"(?:{PREFIX})$", re.I)
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
# 2099 in any script, sets the range aside unless its prefix comes first: the
# coordinator's reading of G36 and G40 at 15:32Z on 2026-09-25.
YEAR = re.compile(r"\d\d|1[7-9]\d\d|20\d\d")
# Metres in a foot, exactly (G41): beside an elevation it converts to, such a range
# reads, since a year would not convert (the coordinator's reading, extended at
# 17:40Z). Compared as exact fractions, so a tolerance's edge is kept.
FOOT = Fraction("0.3048")
# A bracket pair and what it holds, for the brackets an elevation leaves empty:
# "Mt. Apo (1463 m)", full-width ones too.
BRACKETED = re.compile(
    r"[(\uff08][^()\uff08\uff09]*[)\uff09]"
    r"|[\[\uff3b][^\[\]\uff3b\uff3d]*[\]\uff3d]"
    r"|[{\uff5b][^{}\uff5b\uff5d]*[}\uff5d]"
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
    the unit as "ft" or "m", or None when the label gives none. Nothing converted
    is kept: G41's conversion and fill happen in S4's later layer, and this module
    converts only to pair a phrase in feet with one in metres."""

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
    invisible Hangul fillers, before case folding and, when the folded text is not
    ASCII, after it (U+0345 would fold to an iota), and turn anything else but
    letters and digits into single spaces:
    "Chimaltenángo," folds to "chimaltenango"."""
    if text.isascii():
        return " ".join(ASCII_WORDS.findall(text.lower()))
    folded = _unmarked(text).casefold()
    if not folded.isascii():
        folded = _unmarked(folded)
    return " ".join("".join(c if c.isalnum() else " " for c in folded).split())


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
    notation. The words are read as they show, what `fold` drops aside."""
    words = [word.strip(",;:") for word in _visible(name)[0].split()]
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
    parts: list[tuple[str, bool]] = []
    for part, separated in _parts(text):
        cleaned, found = _institutions(part)
        institutions += found
        parts.append((cleaned, separated))
    aheads = _aheads(parts)
    firsts = _firsts([segment for segment, _ in parts])
    numbered = False
    # Whether a word or a mark stands between the last number no elevation took
    # and this part; None when no such number stands before it. Line breaks read
    # as spaces, since a range's join may stand across them ("4000 -" / "4500 ft").
    # Commas and semicolons do too, but only after a number that could be a range's
    # low (`low`): the coordinator's reading at 22:22Z on 2026-09-25 ("4000, hasta
    # 4500 m"), refined at 00:38Z on 2026-09-26 and ruled at 00:52Z. A number with
    # its own unit or prefix is a complete elevation, and a glued one could be no
    # range's low: either ends the check.
    gap: bool | None = None
    low = False
    for index, (segment, separated) in enumerate(parts):
        if separated and not low:
            gap = None
        # The number ahead is looked for across line breaks only: a phrase with no
        # unit has a prefix, so it is a complete elevation.
        ahead = None if index + 1 < len(parts) and parts[index + 1][1] else aheads[index + 1]
        # A part right after one that holds a number, or only a month, may start
        # with the year: "July 4, 1946.9500 ft", "IV-26" / "1948.950 m",
        # "July, 1946.950 m". A part that folds to nothing ("?", a Hangul filler, or
        # "CNHM" once the institution leaves it) passes that on.
        after_number = numbered
        if fold(segment):
            numbered = _numeral(segment) or _dated(segment)
        offset = _offset(segment, ahead, firsts[index + 1])
        if offset is not None:
            piece, found, tail, tail_low = offset
            pieces.append(piece)
        else:
            rest, found, tail, tail_low = _elevations(
                segment, after_number, gap, ahead, firsts[index + 1]
            )
            rest = rest.strip(" ,;:")
            if rest:
                pieces.append(_piece(rest))
        elevations += found
        if tail is not None:
            gap, low = tail, tail_low
        elif any(c.isdecimal() for c in segment):
            gap = None
        elif gap is not None:
            gap = gap or _gap(segment)
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


def _parts(text: str) -> list[tuple[str, bool]]:
    """The literal's parts in order, each with whether a comma or semicolon stands
    between it and the part before. Lines are joined where a word needs the next
    one (a feature notation, a unit written before its name, or a linking word) and
    where a line starts with "of" in any case ("OF MT. APO"; "of" begins no name) or
    a lowercase "de" or "del" (a capitalized one begins a name, "Del Carmen"),
    unless that line is a date: the link, a month, and a number right after the
    month or at the start of the next line (`_date_line`: "de julio, 1946", "de
    julio" / "1946"). Otherwise it is a name ("Viña" / "del Mar", "of May Hill").
    The joins read the words that show: a word of only what `fold` drops is none of
    them. A soft hyphen that ends a line shows as a hyphen. Separators are found in
    the visible text (`_visible`) and cut from the text as written. Lines are kept as
    word lists, so the joins stay linear in the text's length."""
    raw: list[list[str]] = []
    for line, whole in zip(text.splitlines(), text.splitlines(keepends=True)):
        if line != whole:
            line = _line_end_hyphen(line)
        words = line.split()
        if words:
            raw.append(words)
    shown = [[word for word in words if _visible(word)[0]] for words in raw]
    # For each line, and one past the last: whether the next line with more than
    # what folds to nothing or institution codes starts with a number.
    starts: list[bool] = [False] * (len(raw) + 1)
    for row in reversed(range(len(raw))):
        kept = fold(_institutions(" ".join(raw[row]))[0])
        starts[row] = _number_first(kept) if kept else starts[row + 1]
    lines: list[list[str]] = []
    # Each line's last word that shows, which says whether the next line joins it.
    lasts: list[str] = []
    carry: list[str] = []
    last = ""
    for row, words in enumerate(raw):
        seen = shown[row]
        link = fold(seen[0]) if seen else ""
        if (
            not carry
            and lines
            and link in LINKS
            and (link == "of" or seen[0].islower())
            and not _date_line(seen, starts[row + 1])
        ):
            carry, last = lines.pop(), lasts.pop()
        carry += words
        last = seen[-1] if seen else last
        if fold(last) in JOINERS:
            continue
        lines.append(carry)
        lasts.append(last)
        carry, last = [], ""
    if carry:
        lines.append(carry)
    parts: list[tuple[str, bool]] = []
    separated = False
    for words in lines:
        line = " ".join(words)
        seen_line, where = _visible(line)
        cuts = [-1, *(where[match.start()] for match in SEPARATOR.finditer(seen_line)), len(line)]
        for number, (start, end) in enumerate(zip(cuts, cuts[1:])):
            piece = line[start + 1 : end]
            separated = separated or number > 0
            if piece.strip():
                parts.append((" ".join(piece.split()), separated))
                separated = False
    return parts


def _date_line(words: list[str], number_next: bool) -> bool:
    """Whether a line that starts with a link begins a date: a month follows the
    link, and a number comes right after the month, a link between them aside
    ("de julio, 1946", "de julio,1946", "de julio de 1946"), or starts the next
    line when the month ends this one. Institution codes and what `fold` drops are
    no words here, so "of May Hill" / "1500 m" is a name; an apostrophe-shaped
    letter before the number is none either (`_number_first`)."""
    after = fold(_institutions(" ".join(words[1:]))[0]).split()
    if not after or after[0] not in MONTHS:
        return False
    rest = after[1:]
    if rest and rest[0] in LINKS:
        rest = rest[1:]
    return _number_first(rest[0]) if rest else number_next


def _line_end_hyphen(line: str) -> str:
    """The line, with a soft hyphen that ends it shown as the hyphen it shows as: one
    that only spaces and what `fold` drops follow."""
    end = len(line)
    while end > 0 and (line[end - 1].isspace() or not _kept(line[end - 1])):
        end -= 1
    at = line.find("\u00ad", end)
    return line if at < 0 else f"{line[:at]}-{line[at + 1 :]}"


def _number_first(folded: str) -> bool:
    """Whether folded text starts with a digit, after any of the apostrophe-shaped
    modifier letters (U+02BB, U+02BC, U+02BD), which Python counts as letters and
    `fold` keeps: a two-digit year may follow one."""
    return folded.lstrip(APOSTROPHE_LETTERS)[:1].isdecimal()


def _visible(text: str) -> tuple[str, Sequence[int]]:
    """The text without what `fold` drops (a zero-width space, a soft hyphen, a word
    joiner, a combining mark, a Hangul filler), which the reader's patterns read,
    and where each of its characters, and one past the last, stands in `text`: what
    they find is cut from the text as written, as `_institutions` cuts its codes.
    Spaces that dropping leaves side by side, or at either end, go too, so the
    visible text holds single spaces as the parts do. Parts in ASCII hold nothing
    `fold` drops and are single-spaced already."""
    if text.isascii():
        return text, range(len(text) + 1)
    kept: list[int] = []
    for index, c in enumerate(text):
        if _kept(c) and not (c.isspace() and (not kept or text[kept[-1]].isspace())):
            kept.append(index)
    if kept and text[kept[-1]].isspace():
        kept.pop()
    return "".join(text[index] for index in kept), [*kept, len(text)]


def _written(text: str, where: Sequence[int], start: int, end: int) -> str:
    """The text as written from the visible characters `start` to `end`, what
    `fold` drops between them included."""
    return text[where[start] : where[end - 1] + 1] if end > start else ""


def _institutions(part: str) -> tuple[str, list[str]]:
    """The part without the museum's own names in it, matched as `fold` reads them
    ("CNHM.", full-width "\uff23\uff2e\uff28\uff2d"), and those names as written,
    with the period after one, what `fold` drops before it aside."""
    if part.isascii() and not INSTITUTIONS.search(fold(part)):
        return part, []
    folded: list[str] = []
    where: list[int] = []
    for index, c in enumerate(part):
        for kept in _kept(c):
            folded.append(kept if kept.isalnum() else " ")
            where.append(index)
    found: list[str] = []
    keep: list[str] = []
    last = 0
    for match in INSTITUTIONS.finditer("".join(folded)):
        start, end = where[match.start()], where[match.end() - 1] + 1
        after = end
        while after < len(part) and not _kept(part[after]):
            after += 1
        if after < len(part) and _kept(part[after]) == ".":
            end = after + 1
        found.append(part[start:end])
        keep.append(part[last:start])
        last = end
    keep.append(part[last:])
    return " ".join(" ".join(keep).split()), found


def _kept(c: str) -> str:
    """What `fold` keeps of one character, folded, before anything but letters and
    digits turns into spaces: "" when `fold` drops it."""
    if c.isascii():
        return c.lower()
    kept = _unmarked(c).casefold()
    return _unmarked(kept) if not kept.isascii() else kept


def _aheads(parts: list[tuple[str, bool]]) -> list[bool | None]:
    """For each part, and one past the last, whether a word or a mark stands
    between the end of the part before it and the next number, across line breaks
    but no comma or semicolon; None when no number follows before one. The later
    number's own prefix is no part of it. It reads the visible parts."""
    aheads: list[bool | None] = [None] * (len(parts) + 1)
    for index in reversed(range(len(parts))):
        segment = _visible(parts[index][0])[0]
        digit = next((i for i, c in enumerate(segment) if c.isdecimal()), None)
        if digit is not None:
            aheads[index] = _gap(PREFIX_END.sub("", segment[:digit]))
        elif aheads[index + 1] is not None and not parts[index + 1][1]:
            aheads[index] = _gap(segment) or aheads[index + 1]
    return aheads


def _firsts(parts: list[str]) -> list[tuple[str, ...]]:
    """For each part, and one past the last, its first two words as `fold` reads
    them, running on into the parts after it."""
    firsts: list[tuple[str, ...]] = [()] * (len(parts) + 1)
    for index in reversed(range(len(parts))):
        words = tuple(fold(parts[index]).split()[:2])
        firsts[index] = (words + firsts[index + 1])[:2]
    return firsts


def _offset(
    segment: str, ahead: bool | None = None, following: tuple[str, ...] = ()
) -> tuple[_Piece, list[Elevation], bool | None, bool] | None:
    """An offset ("5 km NE of Yepocapa") and the elevation phrases after it. Its
    place follows the rules for any part: a place with a digit or without a
    letter is kept aside with its offset. A malformed distance ("1,5,3 km") is no
    offset, so the segment is kept aside whole. It reads the visible segment."""
    seen, where = _visible(segment)
    match = OFFSET.match(seen)
    bearing = _bearing(match["head"]) if match else None
    if match is None or bearing is None or not VALID_NUMBER.fullmatch(match["distance"]):
        return None
    rest, found, tail, low = _elevations(
        segment[where[match.start("rest")] :], ahead=ahead, following=following
    )
    rest = rest.strip(" ,;:")
    if not _placeable(rest):
        return _Piece("unplaced", segment), found, tail, low
    unit = match["unit"].casefold()
    piece = _place(rest, segment)
    piece.heading = Heading(_written(segment, where, *match.span("head")), bearing)
    piece.relation = "offset"
    piece.distance = match["distance"]
    piece.distance_unit = "km" if unit[0] == "k" else "mi" if unit[:2] == "mi" else "m"
    return piece, found, tail, low


def _placeable(text: str) -> bool:
    """A place's text has a letter and no numeral, of any script ("½" too):
    gazetteer names carry no digits."""
    return any(c.isalpha() for c in text) and not _numeral(text)


def _numeral(text: str) -> bool:
    """A numeral of any script, as written or in its compatibility form: "½", "Ⅳ"
    (whose form is the letters "IV"), or "㏠" (whose form is "1日")."""
    forms = (text, unicodedata.normalize("NFKD", text))
    return any(unicodedata.category(c) in NUMERALS for form in forms for c in form)


def _dated(text: str) -> bool:
    """A part of only a date's month: month words and Roman months, with "de",
    "del" or "of" beside them ("Sept.", "IV", "VIII/IX", "de julio")."""
    words = fold(text).split()
    return any(word in MONTHS for word in words) and all(
        word in MONTHS or word in LINKS for word in words
    )


def _unsure(
    segment: str,
    match: re.Match[str],
    paired: bool,
    after: bool,
    converts: bool,
    following: tuple[str, ...] = (),
) -> bool:
    """Whether an elevation's number is unsure, so the phrase is set aside rather
    than read (GEO.md 1, "Unsure numbers"):
    - a malformed grouping ("1,5,3 m"), or four digits after a mark ("4.1948");
    - glued to the text before it, where no space, part start, opening bracket or
      other elevation (`paired`) comes first ("12.IV.1948,95 m", "4'800 m"), or,
      with no unit, running straight into more letters or digits ("Elev.6400,13.XI"),
      or with a decimal part that a number or a month follows, in its part or the
      next (`following`: "el. 6400,12 Sep", "Elev.6400,12, XI.1946");
    - a range, or first digits that could be a year, after other text or right
      after a part that holds a number or only a month (`after`), unless its
      prefix or another elevation comes first ("Sept. 1946 - 850 m",
      "July 4, 1946.9500 ft", "July, 1946.950 m");
    - a range that runs downward, by its whole parts in any digits, or either of
      whose numbers has a decimal part, in thousands groups or not ("1946 - 850 m",
      "4-1948,95 m", "1946,95-2500 m", "1.463,26-9500 m"), or whose lower number
      could be a year in any digits, unless
      its prefix comes first or it converts with the elevation beside it
      (`converts`: "1800-2200 m" is set aside, "Elev. 1800-2200 m" and
      "6000-7000 ft 1829-2134 m" read);
    - beside another digit group across a space ("4 800 ft.", "Elev. 4 800 ft.").
    The check between two numbers is `_joined`'s."""
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
    # A number with no unit that runs straight into more text, or, with a decimal
    # part, that a number or a month follows, in its part or the next, may have a
    # date's day or year run into it: "Elev.6400,13.XI", "alt 1.463,27-of jun.",
    # "el. 6400,12 Sep", "Elev.6400,12, XI.1946".
    end = match.end()
    if not match["unit"] and (
        _runs_on(segment, end) or (_fraction(low) and _date_next(segment, end, following))
    ):
        return True
    if high and (_fraction(low) or _fraction(high) or _size(low) > _size(high)):
        return True
    if high and not converts and not match["prefix"] and YEAR.fullmatch(_ascii(low)):
        return True
    # Searched only in the few characters before the number, so a long segment
    # stays linear: segments hold single spaces, so a digit group and its space
    # take at most four characters.
    begin = match.start("low")
    before = GROUP_BEFORE.search(segment, max(0, begin - 8), begin)
    end = match.end("high") if high else match.end("low")
    return bool((before and re.match(r"\d{3}(?!\d)", low)) or GROUP_AFTER.match(segment, end))


def _runs_on(segment: str, end: int) -> bool:
    """Whether the text from `end` runs straight into a letter or digit before the
    next space, marks and what `fold` drops aside. It reads only up to that letter,
    digit or space, so a long segment stays linear."""
    for index in range(end, len(segment)):
        c = segment[index]
        if c.isspace():
            return False
        if any(kept.isalnum() for kept in _kept(c)):
            return True
    return False


def _date_next(segment: str, end: int, following: tuple[str, ...] = ()) -> bool:
    """Whether a number or a month comes next after `end`, marks and spaces aside,
    and what `fold` drops too; a "de", "del" or "of" before the month too ("12 Sep",
    "12 de julio", "12 4 1948"). It reads on into the next parts (`following`)."""
    words = (*_next_words(segment, end), *following)[:2]
    if not words:
        return False
    first = words[0]
    if first[0].isdecimal() or first in MONTHS:
        return True
    return first in LINKS and len(words) > 1 and words[1] in MONTHS


def _next_words(segment: str, end: int) -> list[str]:
    """The next two words after `end` as `fold` reads them. It reads only up to the
    end of the second word."""
    words: list[str] = []
    current: list[str] = []
    for index in range(end, len(segment)):
        for kept in _kept(segment[index]):
            if kept.isalnum():
                current.append(kept)
            elif current:
                words.append("".join(current))
                current = []
                if len(words) == 2:
                    return words
    if current:
        words.append("".join(current))
    return words[:2]


def _joined(
    segment: str,
    match: re.Match[str],
    digits: list[int],
    since: int,
    before: bool | None,
    ahead: bool | None,
) -> bool:
    """Whether the phrase's number may be one end of a range whose join no rule
    lists ("4000 hasta 4500 ft", "4000~ 4500 m"): another number comes before it
    since the last elevation read (`since`), or after it when it has no unit, with
    a word or a mark between them, opening brackets, the later number's own prefix
    and what `fold` drops aside. Across parts, `before` and `ahead` say whether a
    word or a mark stands between this part and the number before it, or after
    it. `digits` are the segment's digit positions, so each check reads only the
    text between two numbers."""
    start, end = match.start(), match.end()
    index = bisect_left(digits, start)
    if index and digits[index - 1] >= since:
        if _gap(segment[digits[index - 1] + 1 : start]):
            return True
    elif since == 0 and before is not None and (before or _gap(segment[:start])):
        return True
    if match["unit"]:
        return False
    index = bisect_left(digits, end)
    if index < len(digits):
        return _gap(PREFIX_END.sub("", segment[end : digits[index]]))
    return ahead is not None and (ahead or _gap(segment[end:]))


def _gap(text: str) -> bool:
    """Whether a text between two numbers may join them as a range: it holds a word
    or a mark as `fold` reads it, across a line break too, and across a comma or a
    semicolon after a bare number (the coordinator's reading at 22:22Z on 2026-09-25,
    refined at 00:38Z on 2026-09-26: "4000, hasta 4500 m" is set aside). What `fold`
    drops is nothing; a character it keeps as a space is a mark (`_mark`)."""
    if text.isspace() or not text:
        return False
    return bool(fold(text)) or any(_mark(c) for c in text)


def _mark(c: str) -> bool:
    """A character that is no space or opening bracket, which `fold` keeps as
    something other than letters and digits: a spacing mark whose compatibility
    form is a space and combining marks ("\u02dc", "\u203e") is one, while what
    `fold` drops is none."""
    if c.isspace() or c in OPENINGS:
        return False
    kept = _kept(c)
    return bool(kept) and not any(k.isalnum() for k in kept)


def _ascii(number: str) -> str:
    """The number with its digits, of any script, written in ASCII."""
    return "".join(str(unicodedata.decimal(c)) if c.isdecimal() else c for c in number)


def _size(number: str) -> tuple[int, str]:
    """A number's whole part, for a range's order, compared as ASCII digits rather
    than converted: thousands marks dropped, a decimal cut at its point ("1463,5",
    and "1,463.5", whose second kind of mark is the point)."""
    digits = _ascii(number)
    if _decimal(number) or ("," in digits and "." in digits):
        digits = digits[: max(digits.rfind(","), digits.rfind("."))]
    whole = re.sub("[.,]", "", digits).lstrip("0")
    return len(whole), whole


def _fraction(number: str) -> bool:
    """A number with a decimal part, in thousands groups or not: "1463,5",
    "1.463,5"."""
    return _decimal(number) or ("," in number and "." in number)


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
        if foot is None or metre is None or abs(foot * FOOT - metre) > max(10, metre / 50):
            return False
    return True


def _value(number: str) -> Fraction | None:
    """A valid number's exact value, or None past an elevation's length: a decimal
    reads its mark as the point, thousands marks are dropped, and in a grouped
    number with a decimal the second kind of mark is the point ("1.463,5")."""
    if len(number) > 12 or not VALID_NUMBER.fullmatch(number):
        return None
    number = _ascii(number)
    if _decimal(number):
        return Fraction(number.replace(",", "."))
    if "," in number and "." in number:
        grouping, point = (",", ".") if number.index(",") < number.index(".") else (".", ",")
        return Fraction(number.replace(grouping, "").replace(point, "."))
    return Fraction(number.replace(",", "").replace(".", ""))


def _elevations(
    segment: str,
    after_number: bool = False,
    before: bool | None = None,
    ahead: bool | None = None,
    following: tuple[str, ...] = (),
) -> tuple[str, list[Elevation], bool | None, bool]:
    """Elevation phrases out of the segment, each as written (G27, G38),
    whether a word or a mark follows the last number no elevation took (None when
    every number was taken), and whether that number could be a range's low
    (`_range_low`). `after_number` says the part before this one holds a
    number or only a month; `before` and `ahead` are `_joined`'s, and `following`
    the next parts' first words. The patterns read the visible segment
    (`_visible`); each phrase and the rest are cut from the segment as written, and
    a phrase's numbers are its visible ones."""
    seen, where = _visible(segment)
    found: list[Elevation] = []
    rest: list[str] = []
    last = 0
    written = 0
    # Opening brackets at the part's start are no text before a number.
    lead = len(seen) - len(seen.lstrip(" " + OPENINGS))
    digits = [index for index, c in enumerate(seen) if c.isdecimal()]
    phrases = [match for match in ELEVATION.finditer(seen) if match["prefix"] or match["unit"]]
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
        # Only the last phrase in the segment reads on into the next parts.
        later = following if index == len(phrases) - 1 else ()
        if _unsure(seen, match, paired, after, index in converting, later) or _joined(
            seen, match, digits, last, before, ahead
        ):
            continue
        text = _written(segment, where, *match.span())
        found.append(Elevation(text.strip(), match["low"], match["high"], _unit(match)))
        rest.append(segment[written : where[match.start()]])
        last, written = match.end(), where[match.end() - 1] + 1
    rest.append(segment[written:])
    tail, low = None, False
    if digits and digits[-1] >= last:
        tail = _gap(seen[digits[-1] + 1 :])
        low = _range_low(seen, digits[-1], lead, phrases[-1] if phrases else None)
    return " ".join(_unbracketed(" ".join(rest)).split()), found, tail, low


def _unbracketed(text: str) -> str:
    """The text without the brackets an elevation left empty ("Mt. Apo (1463 m)"
    leaves "Mt. Apo"), where brackets that hold only what `fold` drops are empty too."""
    return BRACKETED.sub(
        lambda match: match[0] if _visible(match[0][1:-1])[0].strip() else " ", text
    )


def _range_low(segment: str, end: int, lead: int, phrase: re.Match[str] | None) -> bool:
    """Whether the number whose last digit is at `end` could be a range's low: it
    is bare, with no unit or prefix of its own (no phrase holds it), and nothing is
    glued to it before (a space, the part's start or an opening bracket comes
    first, as an elevation's number needs). A date's year ("12-IV-1948") is none.
    It reads back only over the number."""
    if phrase is not None and phrase.start() <= end < phrase.end():
        return False
    start = end
    while start > 0 and (
        segment[start - 1].isdecimal()
        or (segment[start - 1] in ".," and start > 1 and segment[start - 2].isdecimal())
    ):
        start -= 1
    return start <= lead or segment[start - 1].isspace() or segment[start - 1] in OPENINGS


def _piece(segment: str) -> _Piece:
    if not _placeable(segment) or _dated(segment):
        return _Piece("unplaced", segment)
    word = fold(segment)
    if word in UNIT_WORDS:
        return _Piece(
            "unit", segment, unit=UNIT_WORDS[word], unit_first=word in UNITS_BEFORE
        )
    # The heading patterns read the visible segment; the rest is cut as written.
    seen, where = _visible(segment)
    for pattern in (LEADING_HEADING, TRAILING_HEADING):
        match = pattern.match(seen)
        heading = _heading(match, segment, where) if match else None
        if heading is None:
            continue
        rest = _written(segment, where, *match.span("rest")).strip(" ,;:")
        if not any(c.isalpha() for c in rest):  # nothing, or no letter: "E. slope -"
            return _Piece("heading", segment, heading=heading, relation=_relation(match))
        piece = _place(rest, segment)
        piece.heading, piece.relation = heading, _relation(match)
        return piece
    return _place(segment, segment)


def _place(written: str, text: str) -> _Piece:
    """A place piece: the unit word, before or after the name, leaves the name. A
    name left with no letter ("Depto. de ?"), keying to nothing ("Prov. Dept.") or
    only a linking word is set aside. It reads the words that show, each as written."""
    words = [word for word in written.split() if _visible(word)[0]]
    unit = None
    if len(words) > 1 and fold(words[0]) in UNIT_WORDS:
        unit, words = UNIT_WORDS[fold(words[0])], words[1:]
        if len(words) > 1 and fold(words[0]) in LINKS:
            words = words[1:]
    elif len(words) > 1 and fold(words[-1]) in UNIT_WORDS:
        unit, words = UNIT_WORDS[fold(words[-1])], words[:-1]
    name = " ".join(words).strip(" ,;:")
    if not comparison_key(name) or {fold(word) for word in name.split()} <= LINKS | JOINS:
        return _Piece("unplaced", text)
    seen, where = _visible(name)
    if seen.endswith(".") and not _abbreviated(seen.split()[-1]):
        name = name[: where[len(seen) - 1]] + name[where[len(seen) - 1] + 1 :]
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
        if pattern.fullmatch(_visible(piece.name)[0]):
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


def _heading(match: re.Match[str], segment: str, where: Sequence[int]) -> Heading | None:
    """The heading of a slope phrase, found in the visible segment and kept as
    written; a word run into its relation ("Eastside") is a name, while a reader's
    joined "ESlope" is still a heading."""
    head = match["head"]
    bearing = _bearing(head)
    letters = sum(c.isalpha() for c in head)
    if bearing is None or (not match["gap"] and not head.endswith(".") and letters > 3):
        return None
    return Heading(_written(segment, where, *match.span("head")), bearing)


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
