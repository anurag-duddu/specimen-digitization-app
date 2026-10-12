"""How a label writes a range and an elevation's unit, in any language (the
review of PR #300 at 6fd595b3b, findings 1, 2 and 5; the review of PR #305
at c59a371dd, notes 1 to 6).

The tables here are the data the guards in agreement.py read, and the
experts' shared brief renders its range and unit lines from them
(prompts.instructions), so the two cannot drift:

- RANGE_WORDS, RANGE_SIGNS and DASHES: what joins two numbers or dates into a
  range ("IV-24-48 to V-2-48", "1200 a 1500 m", "1200 bis 1500 m", "entre 1200
  y 1500 m", "1200 & 1500 m", "1200 - 1500 m", "1200- 1500 m").
- BESIDE_A_NUMBER: the words that may stand between a range's number and its
  joiner ("1200 m to 1500 m", "April 24 to May 2, 1948", "1200 to ca. 1500
  m"): a unit, a month, an approximate marker; a Roman numeral I to XII in
  capitals is a month too.
- OTHER_UNITS: what a number counts or measures that is no elevation and no
  date ("5 km", "2 ex.", "10-12 h"); a range joins only ends of one kind.
- ELEVATION_UNITS: the spellings of an elevation's unit, metres or feet
  ("m", "msnm", "m a.s.l.", "m alt.", "ft.", "'", "pies", "Fuss").
- COMPASS_POINTS, RELATIONS, ELEVATION_WORDS, ASPECTS: the words after a
  number and its unit that make it a distance, not an elevation ("500 m N
  of the bridge", "200 m upstream of the ford"), or keep it an elevation
  ("1500 m above sea level", "1500 m N slope"); HEADINGS, the words before
  a number that make it one ("alt. 1200").
- PLACE_WORDS: the words before a number that make it part of a place, not
  a date ("Hill 1800", "km 1850").

Text is compared folded (`fold`): lower case, each letter's accents dropped,
one character for one so offsets hold, and a curly apostrophe or a prime
read as "'". The range words are written as labels write them and folded
when compared (an "a" with a grave accent is "a"); the other tables are
written folded ("fuss" is "Fuss"; the German sharp s
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

from specimen_digitization.application.domain import LookupStatus
from specimen_digitization.application.field_validators import date_parser

# A comma or a semicolon ends a word even with no space after it
# ("Yepocapa,4800 ft."), except between two digits ("1,200 m").
WORD_ENDS = frozenset(",;")

# Every character of Unicode's dash punctuation category (Pd), pinned by
# name: Unicode 14.0 (the local Python 3.11), 15.0 (CI's Python 3.12) and
# 15.1 list these same 26, and a later Unicode's new dash is not added
# silently by reading the category at run time.
PD_DASHES = frozenset({
    "-",  # hyphen-minus
    "\N{ARMENIAN HYPHEN}",
    "\N{HEBREW PUNCTUATION MAQAF}",
    "\N{CANADIAN SYLLABICS HYPHEN}",
    "\N{MONGOLIAN TODO SOFT HYPHEN}",
    "\N{HYPHEN}",
    "\N{NON-BREAKING HYPHEN}",
    "\N{FIGURE DASH}",
    "\N{EN DASH}",
    "\N{EM DASH}",
    "\N{HORIZONTAL BAR}",
    "\N{DOUBLE OBLIQUE HYPHEN}",
    "\N{HYPHEN WITH DIAERESIS}",
    "\N{TWO-EM DASH}",
    "\N{THREE-EM DASH}",
    "\N{DOUBLE HYPHEN}",
    "\N{OBLIQUE HYPHEN}",
    "\N{WAVE DASH}",  # East Asian labels: 1200\N{WAVE DASH}1500 m
    "\N{WAVY DASH}",
    "\N{KATAKANA-HIRAGANA DOUBLE HYPHEN}",
    "\N{PRESENTATION FORM FOR VERTICAL EM DASH}",
    "\N{PRESENTATION FORM FOR VERTICAL EN DASH}",
    "\N{SMALL EM DASH}",
    "\N{SMALL HYPHEN-MINUS}",
    "\N{FULLWIDTH HYPHEN-MINUS}",
    "\N{YEZIDI HYPHENATION MARK}",
})
# Every form of dash: each joins a range's two ends, standing as a word of
# its own, alone or in a run of any length ("1200 - 1500 m", "1200 \N{EM DASH} 1500 m",
# "1200 --- 1500 m"), or at a word's edge ("1200- 1500 m", "IV-24-48 -V-2-48").
# The Pd dashes, and the signs of other categories written for one: the
# minus sign, the swung dash, the full-width tilde, the hyphen bullet and
# the tilde operator.
DASHES = PD_DASHES | frozenset({
    "\N{MINUS SIGN}",
    "\N{SWUNG DASH}",
    "\N{FULLWIDTH TILDE}",
    "\N{HYPHEN BULLET}",
    "\N{TILDE OPERATOR}",
})
# The words that join two numbers or dates into a range, by language, as
# words of their own between them, compared folded ("A" and an "a" with a
# grave accent are "a"). A run of them is one joiner ("fino a", "usque ad").
# A joiner of several words ("bis zum") is one run too: its first word joins
# on its own, and its later words ("zum", "el", "met") join only after
# another joiner's word (CONTINUATIONS).
A_GRAVE, E_ACUTE = "\N{LATIN SMALL LETTER A WITH GRAVE}", "\N{LATIN SMALL LETTER E WITH ACUTE}"
RANGE_WORDS = {
    "English": ("to", "till", "until", "thru", "through", "and"),
    "Spanish": ("a", "al", "hasta", "hasta el", "y"),
    "Portuguese": ("a", "ao", "at" + E_ACUTE, "e"),
    "French": (A_GRAVE, "au", "jusqu'" + A_GRAVE, "jusqu'au", "et"),
    "German": ("bis", "bis zum", "und"),
    "Italian": ("a", "al", "fino", "e"),
    "Dutch": ("tot", "tot en met", "en", "t/m"),
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
# How many pieces on each side of a joiner are searched for a range's end,
# the end's own piece included (a piece is a word, or a dash split from a
# word's edge): so at most four pieces that may stand beside a number come
# between an end and its joiner ("1200 m a. s. l. to 1500 m" has four; with
# a fifth, "1200 m a. s. l. ca. to 1500 m", "1200" is outside the window
# and the joiner joins no range).
BESIDE_WORDS = 5

# What a number counts or measures when it is no elevation and no date, by
# kind, folded, periods dropped: a distance, a count of specimens or of
# males and females, a time of day. Written right after a range's end,
# glued to its number or as the next piece ("5 km", "2 ex.", "3" with the
# female sign, "10-12 h"), it makes that end of its kind, and a range joins
# only ends of one kind (_kind): "1500 m - 5 km W" and "24.IV.1948 en 2 ex."
# are no ranges.
OTHER_UNITS = {
    "distance": ("km", "kms", "kilometre", "kilometres", "kilometer", "kilometers", "kilometro", "kilometros",
        "kilometri", "mi", "mile", "miles", "milla", "millas", "milha", "milhas", "meile", "meilen", "yd", "yds",
        "yard", "yards", "legua", "leguas"),
    "count": ("ex", "exs", "exx", "expl", "exempl", "exemplar", "exemplare", "exemplares", "exemplaires",
        "esemplari", "ejemplar", "ejemplares", "ejs", "specimen", "specimens", "spec", "specs", "spms",
        "individuals", "ind", "inds", "others", "more", "otros", "outros", "autres", "andere", "altri"),
    "sex": ("\N{MALE SIGN}", "\N{FEMALE SIGN}", "male", "males", "female", "females", "macho", "machos", "hembra",
        "hembras", "femea", "femeas", "femelle", "femelles", "maschio", "maschi", "femmina", "femmine",
        "mannchen", "weibchen"),
    "time": ("h", "hr", "hrs", "hour", "hours", "hora", "horas", "uhr", "heure", "heures", "ore", "uur", "min"),
}
OTHER_OF = {spelling: kind for kind, spellings in OTHER_UNITS.items() for spelling in spellings}
OTHER_KINDS = frozenset(OTHER_UNITS)

# What makes a number and its unit a distance, not an elevation (_distance),
# in its own clause (no comma or semicolon after the unit): a word of
# RELATIONS right after the unit ("2 m from the stream", "500 m de la
# carretera", "300 m al S", "500 m along road", "200 m upstream of ford",
# "100 m above the bridge") with a word after it in the clause, the place it
# is measured from (only RELATIONS_ALONE need none: "500 m inland", "200 m
# upstream"), unless a word of ELEVATION_WORDS follows within three words
# ("1500 m above sea level", "1500 m de altitud"); or a compass
# point right after it ("500 m N of the bridge", "Yepocapa, 500 m N"),
# unless a word of ASPECTS follows it ("1500 m N slope": the side of a
# mountain at that elevation). A heading before the number makes it an
# elevation whatever follows ("alt. 1500 m E side"). Folded, periods dropped.
COMPASS_POINTS = frozenset({
    "n", "s", "e", "w", "o", "ne", "nw", "se", "sw", "no", "so", "nne", "ene", "ese", "sse", "ssw", "wsw",
    "wnw", "nnw", "nno", "ono", "oso", "sso",
    "north", "south", "east", "west", "northeast", "northwest", "southeast", "southwest",
    "norte", "sur", "este", "oeste", "nord", "sud", "est", "ouest", "ost", "sued",
})
RELATIONS = frozenset({
    # of, from, off, to the: English, Spanish, Portuguese, French, Italian, German, Dutch
    "of", "from", "off", "de", "del", "desde", "da", "do", "dos", "das", "du", "des", "dal", "dalla", "von",
    "vom", "van", "al",
    # along, above, below, past, beyond, before, after, up or down a river, inland: English
    "along", "above", "below", "past", "beyond", "before", "after", "upstream", "downstream", "inland",
    # above and below: Spanish "arriba", "abajo", Portuguese "acima", "abaixo", German "oberhalb", "unterhalb"
    "arriba", "abajo", "acima", "abaixo", "oberhalb", "unterhalb",
})
RELATIONS_ALONE = frozenset({"inland", "upstream", "downstream"})
# Sea level and altitude, by language: after a word of RELATIONS they make
# the number an elevation ("above sea level", "s.l.", "acima do nivel do
# mar" with its accent, "oberhalb des Meeresspiegels", "de altitud").
ELEVATION_WORDS = frozenset({
    "sea", "level", "sealevel", "msl", "sl", "asl", "nivel", "niveau", "mar", "meer", "meeres", "meeresspiegel",
    "meeresspiegels", "nn", "altitud", "altitude", "altura", "elevacion", "elevation", "alt", "elev", "hohe",
    "quota", "cota",
})
# The side of a mountain a compass point names, not a way to go: English,
# Spanish, Portuguese, French, Italian, German.
ASPECTS = frozenset({
    "side", "slope", "slopes", "face", "facing", "flank", "ridge", "aspect", "exposure", "lado", "ladera",
    "vertiente", "falda", "flanco", "encosta", "vertente", "versant", "flanc", "pente", "versante", "hang",
    "seite", "flanke",
})
# The headings of an elevation, folded, periods dropped ("alt. 1200", "Elev:
# 1200", "Hohe 1200" with its umlaut, "cota 1200"; "el." only with its
# period): a number right after one is written as an elevation even with no
# unit, which the overlap guard counts (other_kind), though it settles no
# field of a unit (units_of).
HEADINGS = frozenset({
    "alt", "altitude", "altitud", "altura", "elev", "elevation", "elevacion", "hohe", "quota", "cota",
})
HEADING_WITH_PERIOD = "el."

# The words before a number that make it part of a place's name or position,
# never a date, in a place's text (other_kind): a road or a route, a
# kilometre or mile post, a hill, a farm or an estate, by language, folded,
# periods dropped. A run of words right after one is no date ("Hill 1800",
# "FM 1960", "km 1850", "Hwy I-5", "Calle 5 de Mayo"); a number with any
# other word between it and the place word stays a date when the date
# parser reads one ("Finca Moca 1948" may be the farm and the year it was
# collected).
PLACE_WORDS = {
    "road": ("road", "rd", "route", "rte", "rt", "highway", "hwy", "hiway", "freeway", "fwy", "interstate",
        "fm", "ruta", "carretera", "camino", "calle", "avenida", "av", "rodovia", "estrada", "rua", "strasse",
        "str", "chaussee", "strada"),
    "km": ("km", "kms", "kilometre", "kilometer", "kilometro", "mile", "milepost"),
    "hill": ("hill", "cerro", "colina", "loma", "morro", "collina", "colle", "berg", "hugel"),
    "farm or estate": ("farm", "finca", "hacienda", "fazenda", "estancia", "estate", "ranch", "rancho",
        "granja", "chacra", "quinta", "plantation"),
}
PLACE_WORD = frozenset(word for words in PLACE_WORDS.values() for word in words)
# What makes a place word a person's surname instead ("Hill", "Berg",
# "Calle"): initials or a collector's or a determiner's mark right before
# it ("J. Hill 1948", "R.D. Hill 1948", "leg. Berg 1948"), folded, periods
# dropped; the year after it is then a date again.
PERSON_MARKS = frozenset({"leg", "legit", "coll", "col", "colr", "collector", "colector", "coletor", "det",
    "sammler"})
INITIALS = re.compile(r"(?:[^\W\d_]\.)+")

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


JOINERS = frozenset(fold(word).split(" ")[0] for words in RANGE_WORDS.values() for word in words) | frozenset(
    RANGE_SIGNS)
CONTINUATIONS = frozenset(part for words in RANGE_WORDS.values() for word in words
    for part in fold(word).split(" ")[1:]) - JOINERS


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
    return bool(text) and all(char in DASHES for char in text)


def is_joiner(text: str) -> bool:
    """Whether a piece joins a range: a dash, a sign or a word of the tables
    (the first of a joiner of several words)."""
    return _is_dash(text) or fold(text) in JOINERS


def _beside(text: str) -> bool:
    """Whether a piece may stand between a range's number and its joiner: a
    unit's word, a month, a Roman month in capitals, an approximate marker."""
    return _bare(text) in BESIDE_A_NUMBER or _month(text)


def _month(text: str) -> bool:
    """Whether a piece is a month: a month's name or abbreviation in the
    tables, or a Roman numeral I to XII in capitals."""
    return _bare(text) in MONTH_WORDS or text.strip(EDGE).rstrip(".") in ROMAN_MONTHS


def _has_digit(text: str) -> bool:
    return any(char.isdigit() for char in text)


@dataclass(frozen=True)
class Number:
    """A number a line writes, with the elevation unit written with it (None
    when it has none) and the span of the number and its unit together
    (`whole`); `distance` when the words after its unit make it a distance
    (_distance: "500 m N of", "2 m from", "200 m upstream of"). `sign`, for
    a number with no unit, is the span of the number with what still marks
    it as an elevation: a heading right before it ("alt. 1200") or a capital
    "M" right after it that may be a person's initial ("4800 M. Smith"); the
    overlap guard counts it (other_kind), and it settles no unit's field.
    `capital_m` is the span of a capital "M" alone right before a number
    with no unit ("M 1200"): no unit, as a code writes it ("M 12"), but in
    a place's text it may be metres, and the guard counts it there."""

    start: int
    end: int
    unit: str | None = None
    whole: tuple[int, int] | None = None
    distance: bool = False
    sign: tuple[int, int] | None = None
    capital_m: tuple[int, int] | None = None


# A unit spelled with a capital "M" alone, its periods aside ("M", "M."):
# metres, unless it is a person's initial or a count of males (_unit_after).
CAPITAL_M = "M"
# What marks a count of males and females ("3 M. 2 F."): a capital "F", its
# period aside, right after a number.
CAPITAL_F = "F"
# Every word the tables read, folded: never a person's name (_a_name).
TABLE_WORDS = (frozenset(UNIT_OF) | UNIT_PARTS | MONTH_WORDS | APPROXIMATE | COMPASS_POINTS | RELATIONS
    | ELEVATION_WORDS | ASPECTS | HEADINGS | frozenset(OTHER_OF) | PLACE_WORD | JOINERS)


def _a_name(text: str) -> bool:
    """Whether a piece may be a person's name or initial: letters only, the
    first a capital and another in lower case ("Smith", "McRae"), all of two
    or more in capitals ("SMITH": Codex's review of #324 at 77fdaeba), or one
    capital and a period ("R."), and no word of the tables ("Elev.", "N.",
    "Above", "ALT" are none)."""
    word = text.strip(EDGE)
    letters = word.rstrip(".")
    if not letters.isalpha() or not letters[0].isupper() or _bare(word) in TABLE_WORDS:
        return False
    return ((len(letters) == 1 and word.endswith(".")) or any(char.islower() for char in letters[1:])
        or len(letters) >= 2 and letters.isupper())


def _capital(text: str, letter: str) -> bool:
    """Whether a piece is that capital letter alone, its periods and edge
    punctuation aside ("M", "M.", "M.,")."""
    return text.strip(EDGE).replace(".", "") == letter


def _a_sex(text: str) -> bool:
    """Whether a piece names a sex: a capital "F" alone, its period aside, or
    a word or sign of OTHER_UNITS' "sex" ("females", "hembras", the female
    sign)."""
    return _capital(text, CAPITAL_F) or OTHER_OF.get(_bare(text)) == "sex"


def _counts_sexes(line: str, spans: Sequence[tuple[int, int]], number: int, unit_end: int) -> bool:
    """Whether the capital "M" after the number in the piece spans[number],
    ending at `unit_end`, counts males beside a count of another sex: a
    number and a sex (_a_sex) follow it ("3 M. 2 F.") or stand right before
    the number ("2 F. 3 M."), with at most a joiner word between ("3 M. and
    5 females", "5 females y 3 M.": Codex's review of #324 at 77fdaeba)."""
    texts = [line[a:b] for a, b in spans]
    after = [index for index, (start, _) in enumerate(spans) if start >= unit_end][:3]
    if after and _bare(texts[after[0]]) in JOINERS:
        after = after[1:]
    if len(after) >= 2 and NUMBER.fullmatch(texts[after[0]].strip(EDGE)) and _a_sex(texts[after[1]]):
        return True
    before = number - 1
    if before >= 0 and _bare(texts[before]) in JOINERS:
        before -= 1
    return (before >= 1 and _a_sex(texts[before])
        and NUMBER.fullmatch(texts[before - 1].strip(EDGE)) is not None)


def _unit_after(line: str, spans: Sequence[tuple[int, int]], index: int, end: int) -> tuple[str | None, int] | None:
    """The unit written right after a number ending at `end` inside the piece
    spans[index]: the rest of the piece and up to UNIT_WORDS following pieces
    with no digit, the longest that ELEVATION_UNITS spells, as (unit, where it
    ends). A foot mark after a degree sign is a minute of arc, never feet
    ("14\N{DEGREE SIGN}30'"). A capital "M" alone is no unit when it counts males
    beside a count of females ("3 M. 2 F.": None), and a doubtful one when a
    person's name or initial follows it ("4800 M. Smith": (None, where it
    ends))."""
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
            best = (unit, _bare(text), following[count - 1][1] if count else spans[index][1], text)
    if best is None:
        return None
    unit, spelled, stop, text = best
    if spelled == "'" and line[:end].rstrip("0123456789.,").rstrip()[-1:] in DEGREE_SIGNS:
        return None
    if _capital(text, CAPITAL_M):
        if _counts_sexes(line, spans, index, stop):
            return None
        name = next((line[a:b] for a, b in spans if a >= stop), "")
        if _a_name(name):
            return None, stop
    return unit, stop


def _unit_before(line: str, spans: Sequence[tuple[int, int]], index: int, start: int) -> tuple[str, int] | None:
    """The unit written right before a number that starts the piece
    spans[index], as Italian and other European labels write it ("m 1200",
    "m 1200 s.l.m."): the piece before is a spelling of ELEVATION_UNITS other
    than a foot mark or a capital "M" alone (a person's initial or a code's
    letter: "M. 12", "M 12"), and the piece before that, if any, holds no
    digit (so the "m" of "1200 m 1500" stays 1200's). As (unit, where it
    starts)."""
    found = _spelled_before(line, spans, index, start)
    if found is None or found[0] == "'" or _capital(line[found[1]:spans[index - 1][1]], CAPITAL_M):
        return None
    return UNIT_OF[found[0]], found[1]


def _spelled_before(line: str, spans: Sequence[tuple[int, int]], index: int, start: int) -> tuple[str, int] | None:
    """The unit spelling (folded) of the piece right before a number that
    starts the piece spans[index], with no digit in the piece before that,
    as (spelling, where it starts); None when there is none."""
    if index == 0 or start != spans[index][0]:
        return None
    unit_start, unit_stop = spans[index - 1]
    spelled = _bare(line[unit_start:unit_stop])
    if spelled not in UNIT_OF:
        return None
    if index > 1 and _has_digit(line[spans[index - 2][0]:spans[index - 2][1]]):
        return None
    return spelled, unit_start


def _heading(line: str, spans: Sequence[tuple[int, int]], at: int) -> int | None:
    """Where the heading right before position `at` starts (HEADINGS: "alt.
    1200", "Elev:1200", "el. 1200"), in the same piece or as the piece before
    it with no comma or semicolon between; None when there is none."""
    index = next((i for i, (start, stop) in enumerate(spans) if start <= at < stop), None)
    if index is None:
        return None
    start = spans[index][0]
    if at > start:
        text = line[start:at]
    elif index > 0 and not separates(line, spans[index - 1][1] - 1):
        start, text = spans[index - 1][0], line[spans[index - 1][0]:spans[index - 1][1]]
    else:
        return None
    heading = _bare(text) in HEADINGS or text.strip(EDGE).lower() == HEADING_WITH_PERIOD
    return start if heading else None


def _distance(line: str, spans: Sequence[tuple[int, int]], number_end: int, unit_end: int) -> bool:
    """Whether the words after a number's unit, ending at `unit_end`, make it
    a distance (COMPASS_POINTS, RELATIONS): only within its clause, so a
    comma or a semicolon after the unit makes what follows another part of
    the line ("1500 m, N slope" is an elevation), and never a joiner word
    before a number ("1200 m e 2 ex.": "e" is no east there)."""
    after = [(a, b) for a, b in spans if a >= unit_end]
    if not after or any(separates(line, index) for index in range(number_end, after[0][0])):
        return False
    following = []
    for start, stop in after[:4]:
        following.append(_bare(line[start:stop]))
        if separates(line, stop - 1):
            break
    first, rest = following[0], following[1:]
    # A word that is also a joiner ("e", "al") before a number joins two
    # values, no distance: "1200 m e 2 ex.", "1200 m al 1500 m" (Codex's
    # review of #324 at 77fdaeba).
    if first in JOINERS and rest and rest[0][:1].isdigit():
        return False
    if first in RELATIONS:
        return bool(rest or first in RELATIONS_ALONE) and not any(part in ELEVATION_WORDS for word in rest
            for part in (word, *word.split("-")))
    if first in COMPASS_POINTS:
        return not (rest and rest[0] in ASPECTS)
    return False


def _raw_numbers(line: str, spans: Sequence[tuple[int, int]]) -> list[Number]:
    """Every number the pieces write, in order, each with the unit written
    right after it (_unit_after; only a piece's last number can have one),
    else right before it (_unit_before); with no unit, its sign of an
    elevation (a heading before it, a doubtful capital "M" after it)."""
    found: list[Number] = []
    for index, (start, stop) in enumerate(spans):
        hits = list(NUMBER.finditer(line, start, stop))
        for position, hit in enumerate(hits):
            after = _unit_after(line, spans, index, hit.end()) if position == len(hits) - 1 else None
            before = _unit_before(line, spans, index, hit.start()) if after is None and position == 0 else None
            if after is not None and after[0] is not None:
                unit, whole = after[0], (hit.start(), after[1])
            elif before is not None:
                unit, whole = before[0], (before[1], hit.end())
            else:
                heading = _heading(line, spans, hit.start())
                sign = ((heading, hit.end()) if heading is not None
                    else (hit.start(), after[1]) if after is not None else None)
                spelled = _spelled_before(line, spans, index, hit.start()) if position == 0 else None
                capital_m = ((spelled[1], hit.end()) if spelled is not None
                    and _capital(line[spelled[1]:spans[index - 1][1]], CAPITAL_M) else None)
                found.append(Number(hit.start(), hit.end(), sign=sign, capital_m=capital_m))
                continue
            headed = _heading(line, spans, whole[0]) is not None
            found.append(Number(hit.start(), hit.end(), unit, whole,
                not headed and _distance(line, spans, hit.end(), whole[1])))
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


def _numbers_at(text: str, literal: str) -> list[list[Number]]:
    """The numbers (`numbers`) that start inside the literal, one list for
    each place the text writes the literal as whole numbers (never the tail
    of "11500" or the head of "1500.5"), each read on its own line."""
    found = []
    pattern = re.compile(r"(?<!\d)(?<!\d[.,])" + re.escape(literal) + r"(?!\d|[.,]\d)")
    for hit in pattern.finditer(text) if literal else ():
        line_start = text.rfind("\n", 0, hit.start()) + 1
        line_end = text.find("\n", hit.end())
        line = text[line_start:len(text) if line_end < 0 else line_end]
        start, end = hit.start() - line_start, hit.end() - line_start
        found.append([n for n in numbers(line) if start <= n.start < end])
    return found


def written_as_a_distance(text: str, literal: str) -> bool:
    """Whether the text writes one of the literal's numbers, anywhere it
    writes the literal, as a distance (Number.distance, _distance: "1200 m"
    of "Finca Moca, 1200 m along road", "300 m" of "300 m arriba del
    puente"): no elevation (Codex's review of #324 at 77fdaeba)."""
    return any(number.distance for place in _numbers_at(text, literal) for number in place)


def units_of(text: str, literal: str) -> list[frozenset[str]]:
    """The units the text writes the literal's numbers in, one set for each
    place it writes the literal as whole numbers (never the tail of "11500"
    or the head of "1500.5"): the units `numbers` reads on that line for
    the numbers that start inside the literal ("1500 m" and "1500" of "alt.
    1500 m" are metres, "1200" of "1200 to 1500 m" too, "6400" of "6400'"
    feet). An empty set where it writes none of them with a unit."""
    return [frozenset(n.unit for n in place if n.unit) for place in _numbers_at(text, literal)]


# How dates are found inside other text (other_kind): as the date parser
# reads them, with Roman months read and no century rule (a two-digit year
# stays partial, and the text is still a date).
FINDING_DATES = {"version": "date-rules-v1", "two_digit_year_century": None, "roman_numeral_months": True}
# The most words a date the parser reads is written in ("IV - 24 - 48").
DATE_WORDS = 5
ELEVATION, DATE, RANGE = "elevation", "date", "range"


def _after_a_place_word(text: str, found_words: Sequence[tuple[int, int]], first: int) -> bool:
    """Whether the word found_words[first] stands right after a word of
    PLACE_WORDS that no initials or person's mark stand right before
    (PERSON_MARKS: "Hill 1800", but not "J. Hill 1948" or "leg. Berg
    1948"), with no comma or semicolon between them ("Ruta, 1960" and "Hill; 1800"
    hold a date: Codex's review of #324 at 77fdaeba)."""
    if first == 0 or _bare(text[found_words[first - 1][0]:found_words[first - 1][1]]) not in PLACE_WORD:
        return False
    if any(separates(text, index) for index in range(found_words[first - 1][1] - 1, found_words[first][0])):
        return False
    if first == 1:
        return True
    before = text[found_words[first - 2][0]:found_words[first - 2][1]].strip(EDGE)
    return INITIALS.fullmatch(before) is None and _bare(before) not in PERSON_MARKS


def other_kind(text: str, *, place: bool = False) -> tuple[str, str] | None:
    """Text inside one line of text that is plainly an elevation, a date or a
    range of them, as (ELEVATION, DATE or RANGE, that text); None when it
    holds none:
    - ELEVATION: a number with an elevation unit (numbers), unless the words
      after it make it a distance (_distance: "500 m N of", "200 m upstream
      of"); or a number with no unit that a heading stands right before
      ("alt. 1200") or a capital "M" that may be a person's initial follows
      ("4800 M. Smith"; Number.sign), or, in a `place`'s text, that a capital
      "M" alone stands right before ("M 1200", which may be metres there;
      Number.capital_m; a code's "M 12" is none);
    - RANGE: a range of dates or elevations (ranges, `marked`: "24 IV to 2
      V"), never two bare numbers ("km 12 to 15");
    - DATE: a run of up to DATE_WORDS whole words, its edge punctuation
      aside, that the date parser reads as a date, alone or one of several
      readings (field_validators.date_parser under FINDING_DATES: "IV-24-48",
      "24.IV.1948", "May 2, 1948", "Sept. 1946", a year "1948"), the longest
      such run from the first word where one starts; a slide code
      ("V-4-67-1") is none, and in a `place`'s text so is a run that starts
      right after a word of PLACE_WORDS ("Hill 1800", "FM 1960", "km 1850",
      "Hwy I-5"; a code "FM 1960" still holds a date)."""
    spans = pieces(text, words(text))
    for number in numbers(text, spans):
        if number.unit is not None and number.whole is not None and not number.distance:
            return ELEVATION, text[number.whole[0]:number.whole[1]]
        if number.unit is None and number.sign is not None:
            return ELEVATION, text[number.sign[0]:number.sign[1]]
        if place and number.unit is None and number.capital_m is not None:
            return ELEVATION, text[number.capital_m[0]:number.capital_m[1]]
    for found in ranges(text, spans):
        if found.marked:
            return RANGE, text[found.start:found.end]
    found_words = words(text)
    for first in range(len(found_words)):
        if place and _after_a_place_word(text, found_words, first):
            continue
        # The longest run from the first word where one starts: the parser
        # also reads a shorter run, "24 Apr" of "24 Apr 1948", as a date
        # (ambiguous, with no year).
        dated = None
        for last in range(first, min(len(found_words), first + DATE_WORDS)):
            run = text[found_words[first][0]:found_words[last][1]].strip(EDGE).rstrip(".,;:")
            if _has_digit(run) and date_parser(run, source_text=text, date_rules=FINDING_DATES).outcome in (
                    LookupStatus.SUCCESS, LookupStatus.AMBIGUOUS):
                dated = run
        if dated is not None:
            return DATE, dated
    return None


@dataclass(frozen=True)
class Range:
    """A range a line writes: from its left end's piece to its right end's,
    joined by `joiner` (words, a sign or a dash); or one word of two numbers
    joined by a dash or a "/" (`glued`). `kinds` are what its ends are
    written as (_kind). `marked` when it is a range of dates or elevations:
    a unit, a month or a Roman month stands with an end, or an end writes
    letters ("V-2-48")."""

    start: int
    end: int
    left_end: int
    right_start: int
    joiner: str
    marked: bool = False
    glued: bool = False
    kinds: frozenset[str] = frozenset()


# What joins a word's two numbers into a range: a dash, or a "/" ("1200/1500 m").
GLUE = frozenset(DASHES | {"/"})
GLUED = re.compile(r"\d+(?:[.,]\d+)?[" + re.escape("".join(sorted(GLUE))) + r"]\d+(?:[.,]\d+)?")
# What a range's end is written as when nothing marks its kind (_kind).
BARE = "number"
DATE_KIND = "date"


def glued_range(text: str) -> bool:
    """Whether a word is two numbers joined by a dash or a "/" ("10-12",
    "1200\N{EN DASH}1500", "24/30"), its edge punctuation aside."""
    return GLUED.fullmatch(text.strip(EDGE).rstrip(".")) is not None


def _kind(line: str, spans: Sequence[tuple[int, int]], end: int, side: Sequence[int],
        found: Sequence[Number]) -> str:
    """What a range's end is written as:
    - its unit ("m" or "ft") when a number in its piece, or in the pieces
      between it and the joiner, has one;
    - a kind of OTHER_UNITS ("distance", "count", "sex", "time") when one is
      written right after its last number, glued to it or as the next piece
      in its clause ("5 km", "2ex.", "2 ex.", "10-12 h");
    - DATE_KIND when its piece writes letters ("V-2-48") or a month or a
      Roman month stands beside it or as the next piece ("24 IV", "2 V
      1948", "7 May 1948");
    - else BARE, a bare number."""
    held = [spans[end], *(spans[index] for index in side)]
    units = {n.unit for n in found for start, stop in held if start <= n.start < stop and n.unit}
    if units:
        return "/".join(sorted(units))
    start, stop = spans[end]
    last = None
    for last in NUMBER.finditer(line, start, stop):
        pass
    tail = line[last.end():stop] if last is not None else ""
    following = (line[spans[end + 1][0]:spans[end + 1][1]] if end + 1 < len(spans)
        and not separates(line, stop - 1) else "")
    other = OTHER_OF.get(_bare(tail)) or OTHER_OF.get(_bare(following))
    if other is not None:
        return other
    texts = [line[a:b] for a, b in held]
    if any(char.isalpha() for char in texts[0]) or any(_month(text) for text in (*texts[1:], following)):
        return DATE_KIND
    return BARE


def _alike(kinds: Iterable[str]) -> bool:
    """Whether ends of these kinds are written alike: one unit, one date, or
    one other kind, with or without bare numbers ("1200 to 1500 m", "24 al
    30-IV-1948", "5 to 7 May 1948"). Ends in different units are one
    elevation written in both ("4800 ft. / 1463 m"); a unit beside a date,
    or either beside a distance or a count, is two fields ("1200 m /
    24.IV.1948", "1500 m - 5 km W", "24.IV.1948 en 2 ex.")."""
    return len(set(kinds) - {BARE}) <= 1


def ranges(line: str, spans: Sequence[tuple[int, int]], *, found: Sequence[Number] | None = None) -> list[Range]:
    """The ranges the pieces of a line write (`spans`, from `pieces`):
    - a run of joiners (is_joiner, then CONTINUATIONS: "bis zum") with, on
      each side, a piece that holds a digit, up to BESIDE_WORDS pieces away
      past words that may stand beside a number (_beside: "1200 m to 1500 m",
      "April 24 to May 2, 1948"), its two ends written alike (_kind, _alike):
      the same unit, or dates, or a bare number beside either ("24 al
      30-IV-1948", "1200 to 1500 m");
    - each word of two numbers joined by a dash or a "/" (glued_range:
      "10-12" of "10-12 Sept. 1946"), its kind read as an end's."""
    spans = list(spans)
    found = _raw_numbers(line, spans) if found is None else found
    texts = [line[start:stop] for start, stop in spans]
    joined: list[Range] = []
    index = 0
    while index < len(spans):
        if not is_joiner(texts[index]):
            if glued_range(texts[index]):
                start, stop = spans[index]
                kinds = frozenset({_kind(line, spans, index, (), found)})
                joined.append(Range(start, stop, stop, start, "-", marked=bool(kinds - {BARE} - OTHER_KINDS),
                    glued=True, kinds=kinds))
            index += 1
            continue
        last = index
        while last + 1 < len(spans) and (is_joiner(texts[last + 1]) or fold(texts[last + 1]) in CONTINUATIONS):
            last += 1
        left = _end(texts, range(index - 1, max(-1, index - 1 - BESIDE_WORDS), -1))
        right = _end(texts, range(last + 1, min(len(spans), last + 1 + BESIDE_WORDS)))
        if left is not None and right is not None:
            kinds = frozenset({_kind(line, spans, left, range(left + 1, index), found),
                _kind(line, spans, right, range(last + 1, right), found)})
            if _alike(kinds):
                joined.append(Range(spans[left][0], spans[right][1], spans[left][1], spans[right][0],
                    " ".join(texts[index:last + 1]), marked=bool(kinds - {BARE} - OTHER_KINDS), kinds=kinds))
        index = last + 1
    return joined


def _written_as(line: str, spans: Sequence[tuple[int, int]], start: int, end: int,
        found: Sequence[Number]) -> str:
    """What the text [start, end) of the line is written as, by the signs of
    a range's end (_kind): the unit of a number that starts inside it
    ("1500 m", "1500" of "1500 m"); DATE_KIND when a piece inside it writes
    letters beside a digit ("IV-24-48", "24.IV.1948") or is a month ("May 2,
    1948", "Sept. 1946"); else BARE."""
    units = {n.unit for n in found if start <= n.start < end and n.unit}
    if units:
        return "/".join(sorted(units))
    texts = [line[a:b] for a, b in spans if start <= a and b <= end]
    if any(_has_digit(text) and any(char.isalpha() for char in text) or _month(text) for text in texts):
        return DATE_KIND
    return BARE


def part_of_a_range(line: str, spans: Sequence[tuple[int, int]], start: int, end: int) -> bool:
    """Whether the text [start, end) of the line is part of a range the
    pieces `spans` write (in agreement, the pieces of the clause holding
    it): a range (ranges) it does not hold whole, or a word of two numbers
    joined by a dash or a "/" (glued_range) right before or after it, either
    written alike with the text (_alike, _written_as): "1500 m" of "1200 to
    1500 m", "Sept. 1946" of "10-12 Sept. 1946". A range of another kind
    than the text is another field's, and the text is no end of it:
    "24.IV.1948" of "24.IV.1948 10-12 h", "IV-24-48" of "IV-24-48 1200-1500
    m", "1200 m" of "1200 m 10-12 Sept. 1946"."""
    spans = list(spans)
    found = _raw_numbers(line, spans)
    own = _written_as(line, spans, start, end, found)
    for joined in ranges(line, spans, found=found):
        if joined.glued or (start <= joined.start and joined.end <= end):
            continue
        if _alike({own, *joined.kinds}):
            return True
    before = [index for index, (_, stop) in enumerate(spans) if stop <= start][-1:]
    after = [index for index, (first, _) in enumerate(spans) if first >= end][:1]
    for index in before + after:
        if glued_range(line[spans[index][0]:spans[index][1]]) and _alike({own, _kind(line, spans, index, (),
                found)}):
            return True
    return False


def _end(texts: Sequence[str], order: Iterable[int]) -> int | None:
    """The first piece in `order` that holds a digit, past only pieces that
    may stand beside a number; None when another piece comes first."""
    for index in order:
        if _has_digit(texts[index]):
            return index
        if not _beside(texts[index]):
            return None
    return None


# The stand-ins common.txt holds for the rendered range and unit lines
# (prompts.instructions), as notations.MARKER for the place notations.
RANGE_MARKER = "- RANGE_JOINERS"
UNIT_MARKER = "- ELEVATION_UNITS"
# The unit spellings the brief shows, as ASCII (the brief is ASCII): each is
# a spelling of ELEVATION_UNITS, accents aside ("pes" is written with an
# acute accent, "m u. M." with an umlaut).
SHOWN_UNITS = {
    "m": ("m", "mts.", "metres", "meters", "metros", "metri", "msnm", "m.s.n.m.", "msm", "m a.s.l.", "masl",
        "m s.l.m.", "m u. M.", "m alt."),
    "ft": ("ft.", "feet", "'", "pies", "p.s.n.m.", "pes", "Fuss", "pieds", "piedi", "voet"),
}


def range_line() -> str:
    """The experts' brief line for what joins a range (common.txt), from
    RANGE_WORDS and RANGE_SIGNS, folded to ASCII."""
    by_language = "; ".join(f"{language} " + ", ".join(f'"{fold(word)}"' for word in spelled)
        for language, spelled in RANGE_WORDS.items())
    signs = ", ".join(f'"{sign}"' for sign in RANGE_SIGNS)
    return ("- A range joins two numbers or dates with a dash of any form (a hyphen, an en or em dash, a minus "
        f"sign), standing alone or touching one end, with {signs}, or with a word: {by_language} (letter case "
        'and accents aside). A unit or a month may stand between a number and the joiner ("<n1> m to <n2> m", '
        '"<Month> <d1> to <Month> <d2>, <yyyy>"). Its two ends are of one kind (a bare number takes the other '
        "end's): a distance, a count or an hour beside an elevation or a date makes no range (\"<n> m - <n> km "
        '<Direction>", "<date> and <n> ex.", "<date> <h1>-<h2> h").')


def unit_line() -> str:
    """The experts' brief line for the elevation units (common.txt), from
    SHOWN_UNITS."""
    metres, feet = (", ".join(f'"{spelling}"' for spelling in SHOWN_UNITS[unit]) for unit in ("m", "ft"))
    return (f"- Elevation units, letter case and accents aside: metres {metres}, also before the number "
        f'("m 1200"); feet {feet}. "mt" may be Mount and "mm" is no elevation. A capital "M" is no unit '
        'before a number ("M <n>", "M. <n>"), before a name ("<n> M. <Surname>") or in a count of males and '
        'females ("<n> M. <n> F."). A number the label writes with no unit settles no elevation field, and an '
        "elevation settles only the fields of the unit it is written in.")
