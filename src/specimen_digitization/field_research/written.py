"""How a label writes a range and an elevation's unit, in any language (the
review of PR #300 at 6fd595b3b, findings 1 and 5).

The tables here are the data the guards in agreement.py read:

- RANGE_WORDS, RANGE_SIGNS and DASHES: what joins two numbers or dates into a
  range ("IV-24-48 to V-2-48", "1200 a 1500 m", "1200 bis 1500 m", "entre 1200
  y 1500 m", "1200 & 1500 m", "1200 - 1500 m", "1200- 1500 m").
- BESIDE_A_NUMBER: the words that may stand between a range's number and its
  joiner ("1200 m to 1500 m", "April 24 to May 2, 1948", "1200 to ca. 1500
  m"): a unit, a month, an approximate marker; a Roman numeral I to XII in
  capitals is a month too.
- ELEVATION_UNITS: the spellings of an elevation's unit, metres or feet
  ("m", "msnm", "m a.s.l.", "m alt.", "ft.", "'", "pies", "Fuss").
- DISTANCE_AFTER: the words after a number and its unit that make it a
  distance, not an elevation ("500 m N of the bridge").

Text is compared folded (`fold`): lower case, each letter's accents dropped,
one character for one so offsets hold, and a curly apostrophe or a prime
read as "'". The range words are written as labels write them and folded
when compared (an "a" with a grave accent is "a"); the unit, month and
distance tables are written folded ("fuss" is "Fuss"; the German sharp s
folds to itself, and that spelling is listed too). A word is compared with
its edge punctuation and its periods dropped as well, and a unit's words
joined: "m.s.n.m.", "m s.n.m." and "msnm" are one spelling.

A label's words are split as agreement reads them (`words`): at spaces, and
after a comma or a semicolon that does not stand between two digits. Here a
dash at a word's edge is split off as a piece of its own (`pieces`), so
"1200-" is "1200" and "-"; a dash inside a word ("1200-1500 m", "IV-24-48")
is part of it, and such a word of two numbers is a range of its own
(`glued_range`).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

# A comma or a semicolon ends a word even with no space after it
# ("Yepocapa,4800 ft."), except between two digits ("1,200 m").
WORD_ENDS = frozenset(",;")

# Every form of dash, pinned by name (a newer Unicode adds none of these
# silently): each joins a range's two ends, standing as a word of its own
# ("1200 - 1500 m", "1200 \N{EM DASH} 1500 m") or at a word's edge ("1200- 1500 m",
# "IV-24-48 -V-2-48").
DASHES = frozenset({
    "-",  # hyphen-minus
    "\N{HYPHEN}",
    "\N{NON-BREAKING HYPHEN}",
    "\N{FIGURE DASH}",
    "\N{EN DASH}",
    "\N{EM DASH}",
    "\N{HORIZONTAL BAR}",
    "\N{MINUS SIGN}",
    "\N{SMALL HYPHEN-MINUS}",
    "\N{FULLWIDTH HYPHEN-MINUS}",
    "\N{SWUNG DASH}",
    "\N{WAVE DASH}",  # East Asian labels: 1200\N{WAVE DASH}1500 m
    "\N{FULLWIDTH TILDE}",
})
# The words that join two numbers or dates into a range, by language, as
# words of their own between them, compared folded ("A" and an "a" with a
# grave accent are "a"). A run of them is one joiner ("fino a", "usque ad").
A_GRAVE, E_ACUTE = "\N{LATIN SMALL LETTER A WITH GRAVE}", "\N{LATIN SMALL LETTER E WITH ACUTE}"
RANGE_WORDS = {
    "English": ("to", "till", "until", "thru", "through", "and"),
    "Spanish": ("a", "al", "hasta", "y"),
    "Portuguese": ("a", "ao", "at" + E_ACUTE, "e"),
    "French": (A_GRAVE, "au", "jusqu'" + A_GRAVE, "jusqu'au", "et"),
    "German": ("bis", "und"),
    "Italian": ("a", "al", "fino", "e"),
    "Dutch": ("tot", "en", "t/m"),
    "Latin": ("ad", "usque"),
}
# Signs that join a range as words of their own: "1200 & 1500 m", "IV-24-48 /
# V-2-48", "1200 ~ 1500 m". Ends written in different units or kinds join no
# range ("4800 ft. / 1463 m", "1200 m / 24.IV.1948"; ranges).
RANGE_SIGNS = ("&", "/", "~")

# An elevation's units, folded, periods and spaces dropped. A unit follows its
# number, glued to it ("4800ft.") or after spaces on its line, as one word or
# several ("m a. s. l."), or, as Italian labels write it, stands right before
# it ("m 1200"); a foot mark is glued to it ("6400'"). "mt" is none: it may be
# Mount (the briefs; parse_elevation reads no "mt" either).
ELEVATION_UNITS = {
    "m": (
        # metres, by language
        "m", "mts", "mtr", "mtrs", "metre", "metres", "meter", "meters", "metro", "metros", "metri",
        # metres above sea level: Spanish "msnm" and "msm" (sobre el nivel del mar), English "masl",
        # "mamsl" and "msl", Italian "mslm" (sul livello del mare), German "m u. M.", "m u.d.M.", "m u.
        # NN" with an umlaut and "m NN" (ueber Meer, Normalnull), Portuguese "manm" (acima do nivel do mar)
        "msnm", "msm", "masl", "mamsl", "msl", "mslm", "mum", "mudm", "munn", "mnn", "manm",
        # a heading after the unit: "1200 m alt.", "1200 m elev."
        "malt", "melev",
    ),
    "ft": (
        # feet, by language: English, Spanish "pies", Portuguese "pes" with an acute accent, German
        # "Fuss" with a sharp s or without, French "pieds", Italian "piedi", Dutch "voet"
        "ft", "feet", "foot", "pies", "pie", "pes", "fuss", "fu\N{LATIN SMALL LETTER SHARP S}", "pieds", "pied",
        "piedi", "piede", "voet",
        # feet above sea level: "ft a.s.l.", Spanish "p.s.n.m." (pies sobre el nivel del mar)
        "ftasl", "ftamsl", "psnm", "piessnm", "ftalt",
        # the foot mark, straight, curly or a prime (fold reads each as "'")
        "'",
    ),
}
UNIT_OF = {spelling: unit for unit, spellings in ELEVATION_UNITS.items() for spelling in spellings}
# The most words after its number one unit is written in ("m", "a.", "s.", "l.").
UNIT_WORDS = 4
# What a unit's words may be on their own, beside a range's number: the
# spellings, and the parts of a sea-level unit written apart ("m a.s.l.", "m
# s. n. m.", "m u. M." with an umlaut).
UNIT_PARTS = frozenset(UNIT_OF) | {"snm", "sm", "asl", "amsl", "slm", "s", "n", "l", "a", "u", "d", "ud", "udm",
    "unn", "nn", "anm", "alt", "elev"}

# Months by language, folded, with their usual abbreviations (periods
# dropped): "April 24 to May 2, 1948", "24 avril au 2 mai 1948".
MONTHS = {
    "English": ("january", "jan", "february", "feb", "march", "mar", "april", "apr", "may", "june", "jun",
        "july", "jul", "august", "aug", "september", "sep", "sept", "october", "oct", "november", "nov",
        "december", "dec"),
    "Spanish": ("enero", "ene", "febrero", "marzo", "abril", "abr", "mayo", "junio", "julio", "agosto", "ago",
        "septiembre", "setiembre", "set", "octubre", "noviembre", "diciembre", "dic"),
    "Portuguese": ("janeiro", "fevereiro", "fev", "marco", "maio", "mai", "junho", "julho", "setembro",
        "outubro", "out", "novembro", "dezembro", "dez"),
    "French": ("janvier", "janv", "fevrier", "fevr", "mars", "avril", "avr", "mai", "juin", "juillet", "juil",
        "aout", "septembre", "octobre", "novembre", "decembre"),
    "German": ("januar", "janner", "februar", "marz", "maerz", "mrz", "mai", "juni", "juli", "august",
        "september", "oktober", "okt", "november", "dezember", "dez"),
    "Italian": ("gennaio", "genn", "gen", "febbraio", "febbr", "marzo", "aprile", "maggio", "magg", "mag",
        "giugno", "giu", "luglio", "lug", "agosto", "settembre", "sett", "ottobre", "ott", "novembre",
        "dicembre"),
    "Dutch": ("januari", "februari", "maart", "mrt", "april", "mei", "juni", "juli", "augustus", "september",
        "oktober", "november", "december"),
}
MONTH_WORDS = frozenset(word for words in MONTHS.values() for word in words)
# A Roman numeral I to XII in capitals, as its own word, is a month ("24 IV to
# 2 V 1948").
ROMAN_MONTHS = frozenset({"I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"})
# Approximate markers ("1200 to ca. 1500 m").
APPROXIMATE = frozenset({"ca", "c", "circa", "approx", "about", "aprox", "env", "etwa", "cerca"})
BESIDE_A_NUMBER = UNIT_PARTS | MONTH_WORDS | APPROXIMATE
# The most such words between a range's number and its joiner ("1200 m a. s.
# l. to 1500 m").
BESIDE_WORDS = 5

# The words after a number and its unit that make it a distance ("500 m N of
# the bridge", "300 m al S", "2 m from the stream", "500 m de la carretera"):
# compass points, by language, and "of" or "from".
DISTANCE_AFTER = frozenset({
    "n", "s", "e", "w", "o", "ne", "nw", "se", "sw", "no", "so", "nne", "ene", "ese", "sse", "ssw", "wsw",
    "wnw", "nnw", "nno", "ono", "oso", "sso",
    "north", "south", "east", "west", "northeast", "northwest", "southeast", "southwest",
    "norte", "sur", "este", "oeste", "nord", "sud", "est", "ouest", "ost", "sued",
    "of", "from", "off", "de", "del", "desde", "da", "do", "dos", "das", "du", "des", "dal", "dalla", "von",
    "vom", "van", "al",
})

# A foot mark: straight, curly or a prime (extraction_guard's ticks).
FOOT_MARKS = frozenset({"'", "\N{RIGHT SINGLE QUOTATION MARK}", "\N{PRIME}"})
# A foot mark after a degree sign is a minute of arc ("14\N{DEGREE SIGN}30'"), never feet.
DEGREE_SIGNS = frozenset({"\N{DEGREE SIGN}", "\N{MASCULINE ORDINAL INDICATOR}"})
# A number: digits, with thousands or decimals ("1,200", "1.200", "12.5"),
# not inside a word of letters ("km12" is none).
NUMBER = re.compile(r"(?<![^\W\d_])\d+(?:[.,]\d+)*")
# Characters at a word's edge that are punctuation, not part of its text.
EDGE = "()[]{}\"\N{LEFT DOUBLE QUOTATION MARK}\N{RIGHT DOUBLE QUOTATION MARK},;:!?"


def fold(text: str) -> str:
    """The text as the tables are written: each character lower case with its
    accents dropped, one character for one, and a foot mark read as "'"."""
    out = []
    for char in text:
        if char in FOOT_MARKS:
            out.append("'")
            continue
        base = unicodedata.normalize("NFD", char)
        if len(base) > 1 and all(unicodedata.combining(mark) for mark in base[1:]):
            char = base[0]
        lower = char.lower()
        out.append(lower if len(lower) == 1 else char)
    return "".join(out)


JOINERS = frozenset(fold(word) for words in RANGE_WORDS.values() for word in words) | frozenset(RANGE_SIGNS)


def _bare(text: str) -> str:
    """A word as the tables compare it: folded, with its edge punctuation and
    its periods dropped ("Sept." is "sept", "a.s.l.," is "asl")."""
    return fold(text.strip(EDGE)).replace(".", "")


def separates(line: str, index: int) -> bool:
    """Whether the character at `index` is a comma or a semicolon that ends a
    word and a clause: any but one between two digits ("1,200 m")."""
    return line[index] in WORD_ENDS and not (0 < index < len(line) - 1 and line[index - 1].isdigit()
        and line[index + 1].isdigit())


def words(line: str) -> list[tuple[int, int]]:
    """The words of one line, as (start, end): split at spaces, and after a
    comma or a semicolon that does not stand between two digits."""
    found: list[tuple[int, int]] = []
    start = None
    for index, char in enumerate(line):
        if char.isspace():
            if start is not None:
                found.append((start, index))
            start = None
            continue
        if start is None:
            start = index
        if separates(line, index):
            found.append((start, index + 1))
            start = None
    if start is not None:
        found.append((start, len(line)))
    return found


def pieces(line: str, spans: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    """The words, each dash at a word's start or end split off as a piece of
    its own: "1200-" is "1200" and "-", "-V-2-48" is "-" and "V-2-48"."""
    found: list[tuple[int, int]] = []
    for start, end in spans:
        head, tail = start, end
        while head < end and line[head] in DASHES:
            head += 1
        while tail > head and line[tail - 1] in DASHES:
            tail -= 1
        if head == end:  # a dash, or several, standing alone
            found.append((start, end))
            continue
        if head > start:
            found.append((start, head))
        found.append((head, tail))
        if tail < end:
            found.append((tail, end))
    return found


def _is_dash(text: str) -> bool:
    return bool(text) and len(text) <= 2 and all(char in DASHES for char in text)


def is_joiner(text: str) -> bool:
    """Whether a piece joins a range: a dash, a sign or a word of the tables."""
    return _is_dash(text) or fold(text) in JOINERS


def _beside(text: str) -> bool:
    """Whether a piece may stand between a range's number and its joiner: a
    unit's word, a month, a Roman month in capitals, an approximate marker."""
    return _bare(text) in BESIDE_A_NUMBER or text.strip(EDGE).rstrip(".") in ROMAN_MONTHS


def _has_digit(text: str) -> bool:
    return any(char.isdigit() for char in text)


@dataclass(frozen=True)
class Number:
    """A number a line writes, with the elevation unit written with it (None
    when it has none) and the span of the number and its unit together
    (`whole`); `distance` when a compass point or "of" follows it ("500 m N
    of", "2 m from")."""

    start: int
    end: int
    unit: str | None = None
    whole: tuple[int, int] | None = None
    distance: bool = False


def _unit_after(line: str, spans: Sequence[tuple[int, int]], index: int, end: int) -> tuple[str, int] | None:
    """The unit written right after a number ending at `end` inside the piece
    spans[index]: the rest of the piece and up to UNIT_WORDS following pieces
    with no digit, the longest that ELEVATION_UNITS spells, as (unit, where it
    ends). A foot mark after a degree sign is a minute of arc, never feet
    ("14\N{DEGREE SIGN}30'")."""
    rest = line[end:spans[index][1]]
    following = []
    for start, stop in spans[index + 1:index + 1 + UNIT_WORDS]:
        if _has_digit(line[start:stop]):
            break
        following.append((start, stop))
    best = None
    for count in range(len(following) + 1):
        text = rest + "".join(line[start:stop] for start, stop in following[:count])
        unit = UNIT_OF.get(_bare(text))
        if unit is not None:
            best = (unit, _bare(text), following[count - 1][1] if count else spans[index][1])
    if best is None:
        return None
    unit, spelled, stop = best
    if spelled == "'" and line[:end].rstrip("0123456789.,").rstrip()[-1:] in DEGREE_SIGNS:
        return None
    return unit, stop


def _unit_before(line: str, spans: Sequence[tuple[int, int]], index: int, start: int) -> tuple[str, int] | None:
    """The unit written right before a number that starts the piece
    spans[index], as Italian and other European labels write it ("m 1200",
    "m 1200 s.l.m."): the piece before is a spelling of ELEVATION_UNITS other
    than a foot mark, and the piece before that, if any, holds no digit (so
    the "m" of "1200 m 1500" stays 1200's). As (unit, where it starts)."""
    if index == 0 or start != spans[index][0]:
        return None
    unit_start, unit_stop = spans[index - 1]
    spelled = _bare(line[unit_start:unit_stop])
    if spelled == "'" or spelled not in UNIT_OF:
        return None
    if index > 1 and _has_digit(line[spans[index - 2][0]:spans[index - 2][1]]):
        return None
    return UNIT_OF[spelled], unit_start


def _raw_numbers(line: str, spans: Sequence[tuple[int, int]]) -> list[Number]:
    """Every number the pieces write, in order, each with the unit written
    right after it (_unit_after; only a piece's last number can have one),
    else right before it (_unit_before)."""
    found: list[Number] = []
    for index, (start, stop) in enumerate(spans):
        hits = list(NUMBER.finditer(line, start, stop))
        for position, hit in enumerate(hits):
            after = _unit_after(line, spans, index, hit.end()) if position == len(hits) - 1 else None
            before = _unit_before(line, spans, index, hit.start()) if after is None and position == 0 else None
            if after is not None:
                unit, whole = after[0], (hit.start(), after[1])
            elif before is not None:
                unit, whole = before[0], (before[1], hit.end())
            else:
                found.append(Number(hit.start(), hit.end()))
                continue
            next_word = next((line[a:b] for a, b in spans if a >= whole[1]), "")
            found.append(Number(hit.start(), hit.end(), unit, whole, _bare(next_word) in DISTANCE_AFTER))
    return found


def numbers(line: str, spans: Sequence[tuple[int, int]] | None = None) -> list[Number]:
    """Every number the line writes (or its `spans`, from `pieces`), in order,
    each with the elevation unit written with it: right after it
    (_unit_after) or right before it (_unit_before), or, for an end of a
    range that writes none, the other end's unit ("1200" of "1200 to 1500 m"
    or of "1200-1500 m": a trailing unit applies to both ends, as
    parse_elevation reads it; "1500" of "m 1200-1500")."""
    spans = pieces(line, words(line)) if spans is None else list(spans)
    found = _raw_numbers(line, spans)
    by_start = {number.start: number for number in found}
    pairs = [(left.start, right.start) for left, right in zip(found, found[1:])
        if len(line[left.end:right.start]) == 1 and line[left.end:right.start] in GLUE]
    for joined in ranges(line, spans, found=found):
        lefts = [n for n in found if joined.start <= n.start < joined.left_end]
        rights = [n for n in found if joined.right_start <= n.start < joined.end]
        if not joined.glued and lefts and rights:
            pairs.append((lefts[-1].start, rights[0].start))
    for left, right in pairs:
        one, other = by_start[left], by_start[right]
        if one.unit is None and other.unit is not None and other.whole is not None:
            by_start[left] = Number(one.start, one.end, other.unit, (one.start, other.whole[1]), other.distance)
        elif other.unit is None and one.unit is not None and one.whole is not None:
            by_start[right] = Number(other.start, other.end, one.unit, (one.whole[0], other.end), one.distance)
    return [by_start[number.start] for number in found]


def units_of(text: str, literal: str) -> list[frozenset[str]]:
    """The units the text writes the literal's numbers in, one set for each
    place it writes the literal as whole numbers (never the tail of "11500"
    or the head of "1500.5"): the units `numbers` reads on that line for
    the numbers that start inside the literal ("1500 m" and "1500" of "alt.
    1500 m" are metres, "1200" of "1200 to 1500 m" too, "6400" of "6400'"
    feet). An empty set where it writes none of them with a unit."""
    found = []
    pattern = re.compile(r"(?<!\d)(?<!\d[.,])" + re.escape(literal) + r"(?!\d|[.,]\d)")
    for hit in pattern.finditer(text) if literal else ():
        line_start = text.rfind("\n", 0, hit.start()) + 1
        line_end = text.find("\n", hit.end())
        line = text[line_start:len(text) if line_end < 0 else line_end]
        start, end = hit.start() - line_start, hit.end() - line_start
        found.append(frozenset(n.unit for n in numbers(line) if start <= n.start < end and n.unit))
    return found


@dataclass(frozen=True)
class Range:
    """A range a line writes: from its left end's piece to its right end's,
    joined by `joiner` (words, a sign or a dash); or one word of two numbers
    joined by a dash or a "/" (`glued`). `marked` when it is a range of dates or
    elevations: a unit, a month or a Roman month stands with an end, or an
    end writes letters ("V-2-48")."""

    start: int
    end: int
    left_end: int
    right_start: int
    joiner: str
    marked: bool = False
    glued: bool = False


# What joins a word's two numbers into a range: a dash, or a "/" ("1200/1500 m").
GLUE = frozenset(DASHES | {"/"})
GLUED = re.compile(r"\d+(?:[.,]\d+)?[" + re.escape("".join(sorted(GLUE))) + r"]\d+(?:[.,]\d+)?")


def glued_range(text: str) -> bool:
    """Whether a word is two numbers joined by a dash or a "/" ("10-12",
    "1200\N{EN DASH}1500", "24/30"), its edge punctuation aside."""
    return GLUED.fullmatch(text.strip(EDGE).rstrip(".")) is not None


def _kind(line: str, spans: Sequence[tuple[int, int]], end: int, side: Sequence[int],
        found: Sequence[Number]) -> str:
    """What a range's end is written as: its unit ("m" or "ft") when a number
    in its piece, or in the pieces between it and the joiner, has one; "date"
    when its piece writes letters ("V-2-48") or a month or a Roman month
    stands beside it; else "number"."""
    held = [spans[end], *(spans[index] for index in side)]
    units = {n.unit for n in found for start, stop in held if start <= n.start < stop and n.unit}
    if units:
        return "/".join(sorted(units))
    texts = [line[start:stop] for start, stop in held]
    if any(char.isalpha() for char in texts[0]) or any(_bare(text) in MONTH_WORDS
            or text.strip(EDGE).rstrip(".") in ROMAN_MONTHS for text in texts[1:]):
        return "date"
    return "number"


def ranges(line: str, spans: Sequence[tuple[int, int]], *, found: Sequence[Number] | None = None) -> list[Range]:
    """The ranges the pieces of a line write (`spans`, from `pieces`):
    - a run of joiners (is_joiner) with, on each side, a piece that holds a
      digit, up to BESIDE_WORDS pieces away past words that may stand beside
      a number (_beside: "1200 m to 1500 m", "April 24 to May 2, 1948"), its
      two ends written alike (_kind): the same unit, or dates, or a bare
      number beside either ("24 al 30-IV-1948", "1200 to 1500 m"). Ends in
      different units are one elevation written in both ("4800 ft. / 1463
      m"), and a unit beside a date is two fields ("1200 m / 24.IV.1948"):
      no range;
    - each word of two numbers joined by a dash or a "/" (glued_range:
      "10-12" of "10-12 Sept. 1946")."""
    spans = list(spans)
    found = _raw_numbers(line, spans) if found is None else found
    texts = [line[start:stop] for start, stop in spans]
    joined: list[Range] = []
    index = 0
    while index < len(spans):
        if not is_joiner(texts[index]):
            if glued_range(texts[index]):
                start, stop = spans[index]
                joined.append(Range(start, stop, stop, start, "-", glued=True))
            index += 1
            continue
        last = index
        while last + 1 < len(spans) and is_joiner(texts[last + 1]):
            last += 1
        left = _end(texts, range(index - 1, max(-1, index - 1 - BESIDE_WORDS), -1))
        right = _end(texts, range(last + 1, min(len(spans), last + 1 + BESIDE_WORDS)))
        if left is not None and right is not None:
            kinds = {_kind(line, spans, left, range(left + 1, index), found),
                _kind(line, spans, right, range(last + 1, right), found)}
            if len(kinds - {"number"}) <= 1:
                joined.append(Range(spans[left][0], spans[right][1], spans[left][1], spans[right][0],
                    " ".join(texts[index:last + 1]), marked=kinds != {"number"}))
        index = last + 1
    return joined


def _end(texts: Sequence[str], order: Iterable[int]) -> int | None:
    """The first piece in `order` that holds a digit, past only pieces that
    may stand beside a number; None when another piece comes first."""
    for index in order:
        if _has_digit(texts[index]):
            return index
        if not _beside(texts[index]):
            return None
    return None
