"""Deterministic checks a field's expert may call: dates, elevations, catalog numbers;
and the rule tying a taxon's GBIF question to its literal.

Each wraps the repository's pinned parser unchanged (HARNESS.md sections 8 and 13),
calls no provider and never changes the literal. Like the validators it wraps,
a check answers only for a literal that occurs in one of the record's readings;
otherwise it is policy_blocked with the note literal_not_in_source.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, fields, replace
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Any, Literal

from specimen_digitization.application.derivations import HUNDREDTH, METRES_PER_FOOT
from specimen_digitization.application.domain import LookupStatus
from specimen_digitization.application.field_validators import (
    catalog_number_validator,
    date_parser,
)
from specimen_digitization.application.georef_locality import comparison_key

# The elevation parser and the taxon marker projection live with the
# six-specialist harness; they move with these imports when that harness is deleted.
from specimen_digitization.research_harness.evidence import EvidenceError, parse_measurement
from specimen_digitization.research_harness.taxonomy import taxonomy_scientific_name

from . import date_lines

NOT_IN_SOURCE = "literal_not_in_source"
# The date parser's notes for a literal that is (part of) a hyphen-joined code.
_CODE_NOTES = frozenset({"slide_code", "part_of_hyphenated_token"})
# The part of a date literal a field takes: Date Visited To takes a range's end
# (a single date is its own end); every other date field takes the start.
DATE_PART: dict[str, Literal["start", "end"]] = {"date_visited_to": "end"}


def _as_dict(result: Any) -> dict[str, Any]:
    """The compact form an expert is shown: empty and None values left out."""
    out: dict[str, Any] = {"check": result.check}
    for item in fields(result):
        value = getattr(result, item.name)
        if value is None or value == ():
            continue
        if isinstance(value, tuple):
            value = [v.as_dict() if hasattr(v, "as_dict") else v for v in value]
        out[item.name] = str(value) if isinstance(value, LookupStatus) else value
    return out


@dataclass(frozen=True)
class DateReading:
    """One reading a date's notation allows (G29)."""

    # None when the notation states no year (or no century rule gives one).
    iso: str | None
    precision: Literal["day", "month", "year"]
    # The notation rule that matched (date_notations): the trace shows it.
    order: str
    century_rule: str | None = None
    # A range's end, as the same ISO form and precision; the fields above are its start.
    end: str | None = None
    end_precision: Literal["day", "month", "year"] | None = None
    # How the year was found when the notation gives none: "year_literal" (the
    # year the expert passed), "year_on_next_line" or "year_on_previous_line"
    # (the adjacent line, date_lines), "split_lines" (a literal of two lines).
    via: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in vars(self).items() if v is not None and v != ()}


@dataclass(frozen=True)
class DateCheck:
    literal: str
    status: LookupStatus
    readings: tuple[DateReading, ...] = ()
    notes: tuple[str, ...] = ()
    check: str = "date_parser"
    # "end" for the field that takes a range's last date (date_visited_to); None
    # (the start) for every other field.
    part: Literal["start", "end"] | None = None

    @property
    def values(self) -> tuple[str, ...]:
        """The dates the literal can be for this field: each reading's ISO form,
        or, for the end part, a range's end (a single date is its own end)."""
        if self.part == "end":
            return tuple(dict.fromkeys(r.end or r.iso for r in self.readings if r.end or r.iso))
        return tuple(r.iso for r in self.readings if r.iso)

    def as_dict(self) -> dict[str, Any]:
        return _as_dict(self)


@dataclass(frozen=True)
class ElevationCheck:
    literal: str
    status: LookupStatus
    unit: Literal["m", "ft"] | None = None
    # The written numbers, as plain decimals (thousands commas dropped).
    low: str | None = None
    high: str | None = None
    single: bool | None = None
    approximate: bool | None = None
    uncertainty: str | None = None
    notes: tuple[str, ...] = ()
    check: str = "elevation_parser"

    @property
    def values(self) -> tuple[str, ...]:
        """The numbers the label writes, in its own unit; never a conversion (G41)."""
        return tuple(dict.fromkeys(v for v in (self.low, self.high) if v is not None))

    def as_dict(self) -> dict[str, Any]:
        return _as_dict(self)


@dataclass(frozen=True)
class CatalogCheck:
    literal: str
    status: LookupStatus
    catalog_number: str | None = None
    notes: tuple[str, ...] = ()
    check: str = "catalog_number_validator"

    @property
    def values(self) -> tuple[str, ...]:
        return (self.catalog_number,) if self.catalog_number else ()

    def as_dict(self) -> dict[str, Any]:
        return _as_dict(self)


CheckResult = DateCheck | ElevationCheck | CatalogCheck


def _sources(literal: str, reading_texts: Sequence[str]) -> list[str]:
    if not literal or not literal.strip():
        return []
    return [text for text in reading_texts if literal in text]


def _date_rules(date_rules: Any) -> dict | None:
    """The profile's DateRules (a record or its dict) as the date parser reads it."""
    if date_rules is None:
        return None
    if isinstance(date_rules, Mapping):
        return dict(date_rules)
    return date_rules.model_dump()


@dataclass(frozen=True)
class _Run:
    """One reading's result for a date literal."""

    name: str
    outcome: LookupStatus
    readings: tuple[DateReading, ...]
    notes: tuple[str, ...]

    @property
    def signature(self) -> tuple:
        return self.outcome, tuple((r.iso, r.end, r.precision) for r in self.readings)


def parse_date(
    literal: str,
    *,
    reading_texts: Sequence[str],
    date_rules: Any = None,
    year_literal: str | None = None,
    part: Literal["start", "end"] | None = None,
    reading_names: Sequence[str] | None = None,
) -> DateCheck:
    """Every reading a date literal's notation allows (G24, G29; HARNESS.md section 8).

    `date_rules` is the profile's (century rule, Roman months); without it a
    two-digit year stays partial and a Roman month is not read. `year_literal`
    is a year the same reading states elsewhere, the only year a month and day
    alone can take. A month and day with no year also take the year of a line
    just above or below that holds nothing but the year (`date_lines`), and a
    literal of two lines (the date, then its year, or the reverse) is read as one
    date, under the rules of that module. A literal that is part of a
    slide-preparation code, or of any other hyphen-joined token, in any reading is
    no date. Each reading that holds the literal is read by its own text, and
    readings that give different results leave the date ambiguous, naming them
    (`reading_names` names them, in the order of `reading_texts`; the default is
    their numbers). `part` is "end" for the field that takes a range's last date.
    """
    if not literal or not literal.strip():
        return DateCheck(literal, LookupStatus.POLICY, notes=(NOT_IN_SOURCE,), part=part)
    names = list(reading_names) if reading_names is not None else [
        str(number) for number in range(1, len(reading_texts) + 1)]
    texts = [(name, text) for name, text in zip(names, reading_texts, strict=True) if literal in text]
    if not texts:
        return DateCheck(literal, LookupStatus.POLICY, notes=(NOT_IN_SOURCE,), part=part)
    rules = _date_rules(date_rules)
    split = date_lines.split_literal(literal)
    if split is not None:
        runs = [_split_run(literal, split, name, text, rules) for name, text in texts]
    else:
        runs = [_date_run(literal, name, text, year_literal, rules) for name, text in texts]
        # A year literal must be in the same reading as the date it completes.
        runs = [run for run in runs if run.outcome != LookupStatus.POLICY]
    if not runs:
        return DateCheck(literal, LookupStatus.POLICY, notes=("year_literal_not_in_reading",), part=part)
    return _date_check(literal, runs, part)


def _run(name: str, result: Any, via: tuple[str, ...]) -> _Run:
    readings = tuple(
        DateReading(
            iso=r["iso"],
            precision=r["precision"],
            order=r["order"],
            century_rule=r["century_rule"],
            end=r["end"]["iso"] if "end" in r else None,
            end_precision=r["end"]["precision"] if "end" in r else None,
            via=via,
        )
        for r in (result.parsed or {}).get("readings", ())
    )
    return _Run(name, result.outcome, readings, tuple(result.warnings))


def _date_run(literal: str, name: str, text: str, year_literal: str | None,
        rules: dict | None) -> _Run:
    """The date parser on one reading's text, with the year the line beside the
    literal gives when the literal itself and the expert give none."""
    result = date_parser(literal, source_text=text, year_literal=year_literal, date_rules=rules,
        year_literal_decides=True)
    via = ("year_literal",) if year_literal and result.parsed and result.parsed["year_literal"] else ()
    if year_literal is None and "year_missing" in result.warnings:
        beside = date_lines.year_beside(literal, text)
        if beside is not None:
            year, where = beside
            again = date_parser(literal, source_text=text, year_literal=year, date_rules=rules,
                year_literal_decides=True)
            if again.parsed and again.parsed["year_literal"]:
                return _run(name, again, (f"year_on_{where}",))
    return _run(name, result, via)


def _split_run(literal: str, split: tuple[str, str], name: str, text: str, rules: dict | None) -> _Run:
    """A literal of two lines, the date and its year, as one date in one reading."""
    date_part, year = split
    if (problem := date_lines.split_problem(literal, text)) is not None:
        return _Run(name, LookupStatus.NO_MATCH, (), (problem,))
    result = date_parser(date_part, source_text=text, year_literal=year, date_rules=rules,
        year_literal_decides=True)
    # A date that states a year of its own is not a date split from its year.
    if not (result.parsed and result.parsed["year_literal"]):
        notes = ("split_lines_state_two_years",) if result.parsed else ()
        return _Run(name, LookupStatus.NO_MATCH, (), notes)
    return _run(name, result, ("split_lines",))


def _date_check(literal: str, runs: Sequence[_Run], part: Literal["start", "end"] | None) -> DateCheck:
    # Where one reader shows the literal inside a code, it is not a date at all.
    chosen = next((run for run in runs if _CODE_NOTES & set(run.notes)), None)
    if chosen is None:
        chosen = runs[0]
        if any(run.signature != chosen.signature for run in runs):
            return _readers_disagree(literal, runs, part)
    return DateCheck(literal, chosen.outcome, chosen.readings, chosen.notes, part=part)


def _readers_disagree(literal: str, runs: Sequence[_Run], part: Literal["start", "end"] | None) -> DateCheck:
    """Readings of one label that give different dates (or one a date and another
    none) leave the date open: no reading's result is taken for the others. The
    note names each reading and what it gives."""
    given = []
    for run in runs:
        said = "/".join(r.iso or "no year" for r in run.readings) if run.readings else (
            "not a date" + (f" ({run.notes[0]})" if run.notes else ""))
        given.append(f"{run.name}: {said}")
    readings = tuple(dict.fromkeys(r for run in runs for r in run.readings))
    return DateCheck(literal, LookupStatus.AMBIGUOUS, readings,
        ("readers_disagree_on_date", "; ".join(given)), part=part)


def collapse(text: str) -> str:
    """Text as two readers' literals, or a query and a name, are compared: NFC
    and whitespace collapsed, nothing else. Case, punctuation and the spacing
    between words still differ ("E. slope" is not "E.slope")."""
    return " ".join(unicodedata.normalize("NFC", text).split())


def taxon_queries(literal: str) -> frozenset[str]:
    """The GBIF queries that ask about the whole name a taxon literal writes.

    The scientific-name parser's query for the literal (the genus, any
    subgenus, the species epithet and any infraspecific epithet with its
    marker, as written, and the author and year when written), and the same
    without the author and year. What is not part of the name the parser
    leaves out (sex signs, counts, specimen numbers). For a genus-level
    identification ("Epipsocus sp. 1", G25) its query is the genus alone. A
    literal it reads only in part ("Aus bus n. sp."), or that writes no genus
    ("sp. 30"), has none. This is the native rule: the deciding query is the
    declared reading's complete name (research_harness.evidence
    _validate_taxon_inputs, with _taxon_assertions' complete()).
    """
    name = taxonomy_scientific_name(literal)
    if name is None or not name.genus or name.partly_read is not None:
        return frozenset()
    forms = {name.query}
    if name.authorship:
        forms.add(replace(name, authorship=None).query)
    return frozenset(collapse(form) for form in forms)


# The words after "sp." that qualify a name rather than code a morphospecies:
# "sp. n." and "sp. nov." (a new species), "sp. aff." and "sp. cf." (close to a
# species), "sp. nr." (near one), "sp. gr." and "sp. grp." (a species group),
# "sp. ind." and "sp. inc." (undetermined).
QUALIFIERS = ("n", "nov", "aff", "cf", "nr", "gr", "grp", "ind", "inc")
# A space inside one line.
_GAP = r"[^\S\n]"
# A morphocode with no genus: "sp." (or "Sp", "sp #"), not the end of a longer
# word ("wasp"), then a number with an optional letter, or a short lower-case
# code after a space or a period that is no qualifier, then optional sex signs:
# "sp. 30 <female sign>", "Sp. 22", "Sp.30", "sp aa", "sp #1", "Sp.#1". "spp",
# "sp nov", "sp. nov.", "sp aff", "sp cf" and "sp. n." are none. Within one
# line only, so that it can also be searched for in a reading's text.
NO_GENUS = re.compile(
    r"(?<![A-Za-z])[Ss][Pp]"
    r"(?:\.?" + _GAP + r"*#?" + _GAP + r"*(?P<number>\d+[a-z]?)(?![A-Za-z0-9])"
    r"|(?:\." + _GAP + r"*|" + _GAP + r"+)#?" + _GAP + r"*"
    r"(?!(?:" + "|".join(QUALIFIERS) + r")(?![a-z]))(?P<letters>[a-z]{1,3})(?![A-Za-z0-9.]))"
    r"(?:" + _GAP + "*[\N{FEMALE SIGN}\N{MALE SIGN}])*")


def _code(match: re.Match) -> str:
    """A NO_GENUS match's number or code, case aside."""
    return (match["number"] or match["letters"]).casefold()


def names_no_genus(literal: str | None) -> bool:
    """Whether a taxon literal is a morphocode that names no genus, the case
    owner decision B clears as written and unmatched (2026-10-09): the
    scientific-name parser reads no name in it ("Aus bus n. sp." is a name read
    in part, not this), it has no whole-name GBIF query (taxon_queries), and
    the whole literal, whitespace collapsed, is NO_GENUS. A genus anywhere
    ("Epipsocus sp. 1", "sp. 30 <female sign> Epipsocus") or a misread one
    ("Ep1psocus sp. 1") is not."""
    if not literal or not literal.strip():
        return False
    return (taxonomy_scientific_name(literal) is None and not taxon_queries(literal)
        and NO_GENUS.fullmatch(collapse(literal)) is not None)


def morphocode(literal: str | None) -> str | None:
    """The code a taxon literal that names no genus writes (names_no_genus),
    case aside: "30" for "sp. 30 <female sign>" and for "Sp.30", "1" for
    "sp #1". Two readers' texts are the same morphocode when their codes are
    equal: spacing, punctuation, case and sex signs aside ("sp. 30" and
    "sp. 39" are not). None for any other literal."""
    if not names_no_genus(literal):
        return None
    return _code(NO_GENUS.fullmatch(collapse(literal)))


def writes_code(text: str, code: str) -> bool:
    """Whether the text writes a morphocode (NO_GENUS, searched in it) whose
    code is `code` (morphocode)."""
    return any(_code(match) == code for match in NO_GENUS.finditer(text))


# A word that may be a genus: a capital, then letters or digits ("Epipsocus",
# a misread "Ep1psocus", "EPIPSOCUS"), or a capital's abbreviation ("E.").
GENUS_SHAPED = re.compile(r"[A-Z](?:[A-Za-z0-9]*[A-Za-z])?\.?")
# Words that may stand between a genus and its morphocode ("Epipsocus cf. sp. 1").
BETWEEN_WORDS = frozenset({"cf", "cf.", "aff", "aff.", "nr", "nr.", "near"})
# Brackets, quotes and punctuation around a word.
_AROUND = "()[]{}\"'`,;:"


def _words(text: str) -> list[str]:
    """The text's words: its whitespace-separated parts that hold a letter or
    a digit, brackets, quotes and punctuation around them dropped. A sex sign,
    a "+" or a "?" is none."""
    found = []
    for part in text.split():
        part = part.strip(_AROUND)
        if any(c.isalnum() for c in part):
            found.append(part)
    return found


def word_before(text: str, start: int) -> str | None:
    """The word written immediately before text[start:]: the last word before
    it on its line, or, when nothing but sex signs and punctuation precedes it
    there, the last word of the nearest line above that has one. A qualifier
    ("cf.", "aff.", "nr.") is passed over. None when there is none."""
    line_start = text.rfind("\n", 0, start) + 1
    for part in (text[line_start:start], *reversed(text[:line_start].splitlines())):
        words = [w for w in _words(part) if w.casefold() not in BETWEEN_WORDS]
        if words:
            return words[-1]
    return None


# What a token sheds at either end before the label check judges it (B2 of
# #289's third review): "?", "*" and "_", straight and curly quotes,
# brackets, and the punctuation _AROUND drops.
_SHED = _AROUND + "?*_\N{LEFT SINGLE QUOTATION MARK}\N{RIGHT SINGLE QUOTATION MARK}" + (
    "\N{LEFT DOUBLE QUOTATION MARK}\N{RIGHT DOUBLE QUOTATION MARK}")
# The qualifiers that put a name in doubt (B4 of #289's fifth review): each a
# whole word, in any case ("vic" in lower case only: LOWER_CASE_QUALIFIERS),
# its periods aside ("cf", "cf.", "Cf.", "CF" and
# "c.f." are "cf"; "n.r." is "nr"). Capitals each followed by a period are
# a person's initials, never a qualifier ("C.F." in "C.F. Baker", "N.R.";
# _initials).
DOUBT_QUALIFIERS = ("cf", "cfr", "aff", "affin", "affinis", "nr", "near", "prob", "probably", "poss", "possibly",
    "conf", "vic", "prope")
# The qualifiers that count in lower case only: "vic." (vicinity), never
# "Vic." or "VIC" (Victoria).
LOWER_CASE_QUALIFIERS = frozenset({"vic"})
# One of them as a text writes it: its letters, each with an optional period
# after it ("c.f", "cf", "C.F"), in any case unless it is lower case only.
_QUALIFIER_WORD = "(?:" + "|".join((r"(?-i:{})" if word in LOWER_CASE_QUALIFIERS else "{}").format(r"\.?".join(word))
    for word in DOUBT_QUALIFIERS) + ")"
# Two or more capitals, each followed by a period: initials ("C.F.", "N.R.", "A.F.F.").
_INITIALS = re.compile(r"(?:[A-Z]\.){2,}")


def _initials(written: str) -> bool:
    """Whether a qualifier as written, with the period after it, is a
    person's initials instead (_INITIALS: "C.F.", never "c.f.", "Cf." or
    "CF.")."""
    return _INITIALS.fullmatch(written) is not None


# A qualifier a token sheds when it starts it, or ends it with no letter
# right before it, with its final period, written against the word
# ("cf.Epipsocus", "c.f.Epipsocus", "Epipsocus,aff.") or as a word of its own
# ("cfr." in "cfr. Epipsocus"): DOUBT_QUALIFIERS, the doubt signs' own list,
# initials aside ("C.F." and "C.F.Baker" keep their letters).
_QUALIFIER_FIRST = re.compile(r"^" + _QUALIFIER_WORD + r"\.", re.I)
_QUALIFIER_LAST = re.compile(r"(?<![^\W\d_])" + _QUALIFIER_WORD + r"\.$", re.I)


def _shed_qualifier(part: str) -> str:
    """The part with a qualifier that starts it, then one that ends it
    (_QUALIFIER_FIRST, _QUALIFIER_LAST), shed, unless it is initials."""
    for pattern in (_QUALIFIER_FIRST, _QUALIFIER_LAST):
        found = pattern.search(part)
        if found is not None and not _initials(found.group()):
            part = part[:found.start()] + part[found.end():]
    return part


# The label words that may stand beside a morphocode and are no genus, as
# written (NFC): the parts a slide mounts, the slide or mount itself and the
# specimen's sex, in English, Spanish, French, German (its nouns with their
# capital) and Portuguese, and the sex signs. A genus is written with a
# capital, so the lower-case words are listed only in lower case ("Legs" and
# "Ala" are not listed). "perna" is not listed: Perna is a mussel genus. The
# one list the label check passes over, before or after the code
# (genus_beside).
NOT_GENERA = frozenset({
    # English.
    "head", "leg", "legs", "wing", "wings", "abdomen", "antenna", "antennae", "genitalia", "terminalia", "slide",
    "mount", "male", "males", "female", "females",
    # Spanish.
    "cabeza", "pata", "patas", "ala", "alas", "antena", "antenas", "l\N{LATIN SMALL LETTER A WITH ACUTE}mina",
    "montaje", "macho", "machos", "hembra", "hembras",
    # French.
    "t\N{LATIN SMALL LETTER E WITH CIRCUMFLEX}te", "patte", "pattes", "aile", "ailes", "antenne", "antennes", "lame",
    "montage", "m\N{LATIN SMALL LETTER A WITH CIRCUMFLEX}le", "m\N{LATIN SMALL LETTER A WITH CIRCUMFLEX}les",
    "femelle", "femelles",
    # German.
    "Kopf", "Bein", "Beine", "Fl\N{LATIN SMALL LETTER U WITH DIAERESIS}gel",
    "F\N{LATIN SMALL LETTER U WITH DIAERESIS}hler", "Pr\N{LATIN SMALL LETTER A WITH DIAERESIS}parat",
    "M\N{LATIN SMALL LETTER A WITH DIAERESIS}nnchen", "Weibchen",
    # Portuguese.
    "cabe\N{LATIN SMALL LETTER C WITH CEDILLA}a", "pernas", "asa", "asas",
    "l\N{LATIN SMALL LETTER A WITH CIRCUMFLEX}mina", "montagem", "f\N{LATIN SMALL LETTER E WITH CIRCUMFLEX}mea", "f\N{LATIN SMALL LETTER E WITH CIRCUMFLEX}meas",
    "\N{FEMALE SIGN}", "\N{MALE SIGN}"})
# A keyed line, as Workflow.parse reads "key: value" lines: a field key and a
# colon at the line's start; and the taxon's key alone.
_KEYED_LINE = re.compile(r"[^\S\n]*[a-z][a-z_]*[^\S\n]*:")
_TAXON_KEY = re.compile(r"[^\S\n]*taxon[^\S\n]*:[^\S\n]*")


def _token(part: str) -> str:
    """A whitespace-separated part of a text as the label check reads it:
    _SHED's characters and a qualifier (_QUALIFIER_FIRST, _QUALIFIER_LAST)
    shed at either end, again until nothing more is ("[unreadable]" is
    "unreadable", "Epipsocus(?)" and "cf.Epipsocus" are "Epipsocus", "E.?" is
    "E.", "6400'" is "6400", a lone "?" or "cf." is empty)."""
    while True:
        shed = _shed_qualifier(part.strip(_SHED))
        if shed == part:
            return part
        part = shed


def _tokens(text: str) -> list[str]:
    """The text's tokens (_token) that hold a letter or a digit. A sex sign,
    a "+", a "?" or a qualifier alone is none."""
    return [token for token in map(_token, text.split()) if any(c.isalnum() for c in token)]


def may_be_genus(token: str) -> bool:
    """Whether a token (_token) may be a genus, judged with its first letter
    a capital, so that the label check and the query check normalise case
    alike (N2 of #289's fourth review): it holds a letter and no digit
    ("Epipsocus", "epipsocus", "E.", "unreadable" from the reader's
    "[unreadable]"); it is GENUS_SHAPED (a misread "Ep1psocus", or
    "ep1psocus"); or it holds three letters or more and one digit at most,
    a genus misread with a digit ("Epipsocu5", "3pipsocus"; with one digit,
    no date or number punctuation stands between digits). A code, a date or
    a number holds more digits or fewer letters ("V-4-67-1", "6400",
    "IX-14-46"), and is none."""
    token = _first_letter_capital(token)
    letters, digits = sum(c.isalpha() for c in token), sum(c.isdigit() for c in token)
    return GENUS_SHAPED.fullmatch(token) is not None or (letters > 0 and digits == 0) or (letters >= 3 and digits <= 1)


def _lines_before(text: str, start: int) -> list[str]:
    """The lines the label check reads before text[start:], nearest first:
    its line up to it, then the nearest line above that has a token
    (_tokens). When its line writes only the taxon's key before it
    ("taxon: sp. 30", a keyed line Workflow.parse reads), the key is no
    token and that line is not read, and a keyed line above (_KEYED_LINE:
    "habitat: Mossy forest") is another field's: none is read."""
    line_start = text.rfind("\n", 0, start) + 1
    own, above = text[line_start:start], list(reversed(text[:line_start].splitlines()))
    nearest = next((part for part in above if _tokens(part)), None)
    if _TAXON_KEY.fullmatch(own) is not None:
        return [] if nearest is None or _KEYED_LINE.match(nearest) else [nearest]
    return [own] if nearest is None else [own, nearest]


def token_before(text: str, start: int) -> str | None:
    """The token (_tokens) written immediately before text[start:]: the last
    one before it on its line, or, when its line has none there, the last
    one of the nearest line above that has one. None when there is none.
    When its line writes only the taxon's key before it ("taxon: sp. 30", a
    keyed line Workflow.parse reads), the key is no token, and a keyed line
    above (_KEYED_LINE: "habitat: Mossy forest") is another field's: None."""
    tokens = next((found for found in map(_tokens, _lines_before(text, start)) if found), None)
    return tokens[-1] if tokens else None


def _line_after(text: str, end: int) -> str:
    """The rest of the line after text[:end]."""
    line_end = text.find("\n", end)
    return text[end:] if line_end < 0 else text[end:line_end]


def token_after(text: str, end: int) -> str | None:
    """The first token (_tokens) after text[:end] on its line, or None."""
    tokens = _tokens(_line_after(text, end))
    return tokens[0] if tokens else None


# A person's name written with initials, as a collector or a determiner is:
# initials run into the surname ("R.D.mitchell", "R.D.Mitchell"), initials
# then a capitalised surname ("R. D. Mitchell", "F.G. Werner", "H.
# Hoogstraal"), a surname, a comma and initials ("Mitchell, R.D.",
# "Mitchell, R. D.", "Baker, C.F"), or two or more initials alone ("R.D.").
# One capital and a period alone ("E.") abbreviates a genus, never a person.
_PERSON = (r"(?:[A-Z]\.){2,}[^\W\d_]+|(?:[A-Z]\.[^\S\n]*)+[A-Z][^\W\d_]+"
    r"|[A-Z][^\W\d_]+,[^\S\n]*(?:[A-Z]\.[^\S\n]*)*[A-Z]\.?|(?:[A-Z]\.){2,}")
_PERSON_LAST = re.compile(r"(?:^|(?<=[\s,;:(]))(?:" + _PERSON + r")\.?$")
_PERSON_FIRST = re.compile(r"^(?:" + _PERSON + r")(?![^\W\d_])")
# A capital standing alone, no letter right before or after it: an initial.
_LONE_CAPITAL = re.compile(r"(?<![^\W\d_])[A-Z](?![^\W\d_])")


def _a_persons_name(found: re.Match | None) -> bool:
    """Whether a _PERSON match is a person's name: its initials do not spell
    a qualifier of DOUBT_QUALIFIERS ("C.F. Epipsocus" and "N.R. Epipsocus"
    may be "cf." and "nr." before a genus; "R.D. Mitchell" is a name)."""
    return found is not None and _DOUBT_QUALIFIER.fullmatch("".join(_LONE_CAPITAL.findall(found.group()))) is None


def _no_genus_word(token: str) -> bool:
    """Whether a token is one of NOT_GENERA, as written (NFC)."""
    return unicodedata.normalize("NFC", token) in NOT_GENERA


def _read_token(words: list[str], *, last: bool) -> tuple[str, str] | None:
    """The token (_tokens) the label check reads among one line's
    whitespace-separated words: the last (or, not `last`, the first) that is
    not one of NOT_GENERA, with the line's text through it (from it), its
    words joined by single spaces and _SHED's characters shed at that end.
    None when every token of the words is one of NOT_GENERA."""
    words = list(words)
    while words:
        token = _token(words[-1] if last else words[0])
        if any(c.isalnum() for c in token) and not _no_genus_word(token):
            joined = " ".join(words)
            return token, joined.rstrip(_SHED) if last else joined.lstrip(_SHED)
        words.pop(-1 if last else 0)
    return None


def genus_beside(text: str, start: int, end: int) -> str | None:
    """The token beside text[start:end] that may be a genus (may_be_genus):
    the token written immediately before it ("Epipsocus" in "Epipsocus sp.
    1", in "Epipsocus?" with "sp. 1" on the next line, and "unreadable" in
    "[unreadable] sp. 1"), else the first token after it on its line
    ("Epipsocus" in "sp. 1 Epipsocus"). Words of NOT_GENERA are passed over
    (_read_token). Before the code, the token read is the last on its line
    that is not one of them ("Epipsocus" in "Epipsocus legs sp. 1"), or,
    when its line has none, the last such of the nearest line above that
    has a token (_lines_before: "Epipsocus" above "<female sign> legs
    Sp.#1"); when every token of that line is one of them, none is read
    ("wings + head" above "sp. 30", "legs" above "sp. 1"). After it, the
    first on its line that is not one of them ("sp. 1 legs Epipsocus"), and
    none when every token there is one ("sp. 1 legs"). A token that ends
    (before) or starts (after) a person's name written with initials is
    none either (_PERSON, _a_persons_name: "R.D.mitchell" or "1948, R.D.
    Mitchell" above the code, "sp. 1 R.D. Mitchell"). None when neither may
    be a genus."""
    found = next(filter(None, (_read_token(part.split(), last=True) for part in _lines_before(text, start))), None)
    if found is not None and not _a_persons_name(_PERSON_LAST.search(found[1])) and may_be_genus(found[0]):
        return found[0]
    found = _read_token(_line_after(text, end).split(), last=False)
    if found is not None and not _a_persons_name(_PERSON_FIRST.match(found[1])) and may_be_genus(found[0]):
        return found[0]
    return None


def label_names_no_genus(code: str, reading_texts: Sequence[str]) -> bool:
    """Whether the label writes the morphocode `code` (morphocode) with no
    genus beside it: some reading writes it, and wherever any reading writes a
    morphocode of that code (NO_GENUS, searched in its text), no token beside
    it may be a genus (genus_beside). This judges the label, not the
    organiser's literal: a candidate "sp. 1" taken from "Epipsocus sp. 1", or
    from "Epipsocus" with "sp. 1" on the next line (105526328's label), names
    a genus, and so does one beside an unclear word ("Epipsocus?", "E.?",
    "[unreadable]"). "Mossy forest 6400'" above "sp. 30" (105526321),
    "V-4-67-1" above "sp 22" (105526327), "Sp. 22" on a label of its own
    (105526326), "wings + head" above "sp. 30" (105526322), "genitalia +
    legs" above "Sp 30" (105526323), "R.D.mitchell" above "sp #1"
    (105526329) and "legs" before "Sp.#1" (105526330) do not."""
    found = False
    for text in reading_texts:
        for match in NO_GENUS.finditer(text):
            if _code(match) != code:
                continue
            found = True
            if genus_beside(text, match.start(), match.end()) is not None:
                return False
    return found


# One of DOUBT_QUALIFIERS with no letter right before or after it: attached
# to a word or apart, in any case, with or without its periods
# ("cf.Epipsocus", "CF. Epipsocus", "c.f. Epipsocus", "Epipsocus nr.",
# "near Epipsocus"), never inside a longer word ("Nearctic", "Staff").
_DOUBT_QUALIFIER = re.compile(r"(?<![^\W\d_])" + _QUALIFIER_WORD + r"(?![^\W\d_])", re.I)


def _has_a_letter(part: str) -> bool:
    return any(c.isalpha() for c in part)


# The question marks that put a name in doubt wherever "?" does: "?", the
# full-width "?" (U+FF1F) and the inverted "?" (U+00BF).
QUESTION_MARKS = ("?", "\N{FULLWIDTH QUESTION MARK}", "\N{INVERTED QUESTION MARK}")


def _has_question_mark(part: str) -> bool:
    return any(mark in part for mark in QUESTION_MARKS)


def _alone_a_question_mark(part: str) -> bool:
    """A part that is a question mark standing alone: one of QUESTION_MARKS
    and no letter or digit ("?", "(?)")."""
    return _has_question_mark(part) and not any(c.isalnum() for c in part)


def _alone_on_its_line(text: str, part: re.Match) -> bool:
    """Whether a whitespace-separated part of the text is the only one on
    its line, with nothing before it there ("cf." on a line of its own).
    The caller knows that nothing follows it on its line."""
    return not text[text.rfind("\n", 0, part.start()) + 1:part.start()].strip()


def genus_in_doubt(text: str, literal: str) -> bool:
    """Whether the text, wherever it writes the taxon literal, marks the
    literal's first word, its genus, as doubtful (1c of #289's fifth review):
    - a qualifier (DOUBT_QUALIFIERS, read by _qualifier: in any case except
      "vic", with or without its periods, a person's initials such as "C.F."
      aside) in the whitespace-separated part of the text that holds that
      word ("cfr.Epipsocus"), in the part just before it on its line
      ("cfr. Epipsocus", "nr. Epipsocus", "NR Epipsocus"), or standing alone
      on the line above, the only part of that line ("cf." on a line of its
      own above "Epipsocus sp. 1"). A qualifier that ends a longer line above
      is none: it belongs to that line ("Sabah, Danum Valley NR" or
      "Mindanao, Davao vic." above "Epipsocus sp. 1"; N2 of #289's sixth
      review);
    - a "?" on that word, in its own part ("Epipsocus?", "?Epipsocus",
      "Epipsocus(?)"), or a "?" standing alone, a part with no letter or
      digit, just before or just after it on its line ("? Epipsocus",
      "(?) Epipsocus", "Epipsocus ?", "Epipsocus ? sp. 1").
    A "?" is any of QUESTION_MARKS. A "?" on another word ("Davao?
    Epipsocus"), any "?" on the line above ("1946?" above "Epipsocus sp.
    1") or below, and a qualifier after the genus ("Epipsocus cf. sp. 1",
    G25) are none. The doubt signs' narrower reading of a qualifier
    (_qualifier_sign) is not used here: right before a genus, "NR", "C.F"
    and "conf." stay qualifiers. False when the text does not write the
    literal."""
    literal = literal.strip()
    if not literal:
        return False
    parts = list(re.finditer(r"\S+", text))
    start = text.find(literal)
    while start >= 0:
        at = next(i for i, part in enumerate(parts) if part.start() <= start < part.end())
        own = parts[at].group()
        if _has_question_mark(own) or _qualifier(own):
            return True
        if at > 0:
            before = parts[at - 1]
            on_its_line = "\n" not in text[before.end():parts[at].start()]
            if on_its_line and (_qualifier(before.group()) or _alone_a_question_mark(before.group())):
                return True
            if not on_its_line and _qualifier(before.group()) and _alone_on_its_line(text, before):
                return True
        if at + 1 < len(parts):
            after = parts[at + 1]
            if "\n" not in text[parts[at].end():after.start()] and _alone_a_question_mark(after.group()):
                return True
        start = text.find(literal, start + 1)
    return False


def _question_mark(text: str) -> bool:
    """A "?", any of QUESTION_MARKS, attached to a letter-token, a
    whitespace-separated part that holds a letter ("Epipsocus?",
    "?Epipsocus", "E.?", "Epipsocus(?)"), or standing beside one, as the part
    just before or after it ("Epipsocus ?", "(?) Epipsocus", or "Epipsocus"
    with "?" on the next line)."""
    parts = text.split()
    return any(_has_question_mark(part) and any(map(_has_a_letter, parts[max(i - 1, 0):i + 2]))
        for i, part in enumerate(parts))


def _qualifier(text: str) -> bool:
    """One of DOUBT_QUALIFIERS, a whole word or against a word, unless it
    is written as initials with the period after it (_initials: "C.F." in
    "C.F. Baker")."""
    return any(not _initials(found.group() + text[found.end():found.end() + 1])
        for found in _DOUBT_QUALIFIER.finditer(text))


# Capitals with a period between each two, with or without the final
# period: a person's initials ("C.F" in "leg. Baker, C.F" and "C.F Baker",
# "N.R"; N3 of #289's sixth review).
_DOTTED_CAPITALS = re.compile(r"(?:[A-Z]\.)+[A-Z]")
# A number on the line after "Nr" or "NR" and its optional period: German
# "Nummer" ("Praep. Nr. 1234").
_NUMBER_AFTER = re.compile(r"\.?[^\S\n]*\d")
# What follows "conf" and its optional period when it means "confirmed by":
# the word "by" in any case, or a person's initials, capitals each followed
# by a period, before a capitalised surname ("K. Yoshizawa", "E.L.
# Mockford", "E. L. Mockford") or two or more of them alone ("E.L.M.").
_CONFIRMED_BY = re.compile(
    r"\.?\s*(?:(?i:by)(?![^\W\d_])|(?:[A-Z]\.[^\S\n]*)+[A-Z][^\W\d_]|(?:[A-Z]\.){2,})")
# The qualifiers that may place a locality near a place: "near" and "nr"
# before the place, "vic" (vicinity) before or after it.
PLACE_QUALIFIERS = ("near", "nr", "vic")


def _beside_a_place(text: str, found: re.Match, keys: frozenset[str], *, either_side: bool) -> bool:
    """Whether the qualifier `found` stands right before a place whose
    comparison key (application.georef_locality.comparison_key: case,
    accents, punctuation and unit words such as "Prov." aside) is one of
    `keys`, on its line: the rest of its line, after its period, starts with
    that place's whole name. With `either_side`, also right after one: its
    line up to it ends with that name ("Chicago vic.", "Chicago, vic.")."""
    line_start = text.rfind("\n", 0, found.start()) + 1
    line_end = text.find("\n", found.end())
    line_end = len(text) if line_end < 0 else line_end
    after = comparison_key(text[found.end() + text.startswith(".", found.end()):line_end])
    if any(after == key or after.startswith(key + " ") for key in keys):
        return True
    ahead = comparison_key(text[line_start:found.start()]) if either_side else ""
    return any(ahead == key or ahead.endswith(" " + key) for key in keys)


def _says_nothing_of_a_name(text: str, found: re.Match, keys: frozenset[str]) -> bool:
    """Whether a qualifier the doubt signs find (_DOUBT_QUALIFIER) is one of
    the ordinary label words _qualifier_sign passes over."""
    written, after = found.group(), text[found.end():]
    word = written.replace(".", "").casefold()
    if _DOTTED_CAPITALS.fullmatch(written):
        return True
    if written == "NR" and not after.startswith("."):
        return True
    if written in ("Nr", "NR") and _NUMBER_AFTER.match(after):
        return True
    if word == "conf" and _CONFIRMED_BY.match(after):
        return True
    return word in PLACE_QUALIFIERS and bool(keys) and _beside_a_place(text, found, keys, either_side=word == "vic")


def _qualifier_sign(text: str, places: Iterable[str] = ()) -> bool:
    """A qualifier as a doubt sign (DOUBT_SIGNS; N3 of #289's sixth review):
    one of DOUBT_QUALIFIERS, as _DOUBT_QUALIFIER finds one, that is none of
    these ordinary label words:
    - capitals with a period between each two, with or without the final
      period: a person's initials ("C.F." and "C.F" in "leg. Baker, C.F",
      "C.F Baker", "N.R. Smith");
    - "NR", all capitals with no period after it: a nature reserve ("Sabah,
      Danum Valley NR");
    - "Nr" or "NR", with or without its period, before a number on its line:
      German "Nummer" ("Praep. Nr. 1234");
    - "conf", with or without its period, before "by" or a person's initials
      (_CONFIRMED_BY): "confirmed by" ("conf. by J. Smith", "conf. K.
      Yoshizawa", "conf. E.L. Mockford"). A surname with no initials
      ("conf. Yoshizawa") cannot be told from a genus and stays a sign;
    - "near" or "nr" right before a place of `places`, or "vic" right
      before or after one, on its line (_beside_a_place): "5 mi near
      Chicago", "nr. Chicago", "Chicago vic." beside a settled city
      "Chicago". With no `places`, every "near", "nr" and "vic" stays a
      sign ("5 km nr. Davao").
    Every other spelling stays a sign: "cf. Epipsocus", "nr. Epipsocus",
    "NR. Epipsocus", "Nr. Epipsocus", "conf. Epipsocus"."""
    keys = frozenset(key for key in map(comparison_key, places) if key)
    return any(not _says_nothing_of_a_name(text, found, keys) for found in _DOUBT_QUALIFIER.finditer(text))


# What a reader may write in place of a word it cannot read: the reader
# prompt's "[unreadable]", and the other placeholders a transcriber uses
# (N1 of #289's fourth and fifth reviews), anywhere in a text, in any case;
# the words "illegible" and "unreadable" standing alone, with no letter
# right before or after them; three periods for a missing word
# (_ELLIPSIS); and three or more periods in brackets (_BRACKETED_PERIODS).
# Rule A (step._whole_label_read) and rule B (DOUBT_SIGNS and
# step._code_label_unreadable) read this one test (shows_placeholder).
DOUBT_PLACEHOLDERS = ("[unreadable]", "(unreadable)", "[illegible]", "(illegible)", "[illeg.]", "[illeg]", "(illeg.)",
    "[unclear]", "(unclear)", "[?]", "???", "[...]", "\N{HORIZONTAL ELLIPSIS}")
PLACEHOLDER_WORDS = ("illegible", "unreadable")
_PLACEHOLDER_WORD = re.compile(r"(?<![^\W\d_])(?:" + "|".join(PLACEHOLDER_WORDS) + r")(?![^\W\d_])", re.I)
# Exactly three periods, with no period right before or after them ("Mossy
# ...", "(...)"). A run of four or more is a printed form's dot leader
# ("Det. ..........", "Loc. ......"), never a placeholder (N3 of #289's
# sixth review).
_ELLIPSIS = re.compile(r"(?<!\.)\.{3}(?!\.)")
# Three or more periods in brackets, however many ("[...]", "[....]", "(....)").
_BRACKETED_PERIODS = re.compile(r"[\[(][^\S\n]*\.{3,}[^\S\n]*[\])]")


def _after_etc(text: str, start: int) -> bool:
    """Whether text[start:] follows the word "etc", in any case, with no
    letter before it ("etc..." ends a list; it leaves no word out)."""
    return text[max(start - 3, 0):start].casefold() == "etc" and not (start > 3 and text[start - 4].isalpha())


def shows_placeholder(text: str) -> bool:
    """Whether the text writes a placeholder for a word a reader could not
    read: one of DOUBT_PLACEHOLDERS in any case; one of PLACEHOLDER_WORDS as
    a whole word in any case ("Illegible", "UNREADABLE"; never "illegibly");
    exactly three periods (_ELLIPSIS: "Mossy ...", "(...)"), unless right
    after the word "etc" ("etc..."); or three or more periods in brackets
    (_BRACKETED_PERIODS: "[....]"). Four or more periods outside brackets
    are a printed form's dot leader ("Det. .........."), none."""
    folded = text.casefold()
    return (any(placeholder in folded for placeholder in DOUBT_PLACEHOLDERS)
        or _PLACEHOLDER_WORD.search(text) is not None or _BRACKETED_PERIODS.search(text) is not None
        or any(not _after_etc(text, found.start()) for found in _ELLIPSIS.finditer(text)))


# The signs that a name on a label is in doubt or that part of a label
# cannot be read, the one list (B3 of #289's fourth review): each sign's
# name and its test of a text. Owner decision B (step._unmatched_taxon, and
# step.taxon_unmatched on a stored value) refuses when any of them shows in
# any reading of any label of the specimen, beside the code or not. They sit
# on top of the label check (label_names_no_genus), which reads only the
# tokens beside the code: "Epipsocus?" on a line or a label the label check
# does not read would otherwise clear as "the label names no genus" when the
# expert makes no GBIF lookup for it. The taxon brief has the expert look a
# doubtful genus up alone (B4 of #289's fifth review), which the GBIF guard
# (step._gbif_asked_another_name) refuses; these signs hold the taxon back
# when the expert does not. "unreadable_span" is a reader's listed
# unreadable span, or a transcript marked unreadable, on any label; no text
# shows it. The qualifier sign (_qualifier_sign) also reads the label's
# settled places.
DOUBT_SIGNS: tuple[tuple[str, Callable[..., bool] | None], ...] = (
    ("question_mark", _question_mark),
    ("qualifier", _qualifier_sign),
    ("placeholder", shows_placeholder),
    ("unreadable_span", None),
)


def doubt_signs(texts: Iterable[str], *, unreadable: bool = False, places: Iterable[str] = ()) -> tuple[str, ...]:
    """The names of the DOUBT_SIGNS that show, in the list's order: a sign
    whose test any of the texts meets, and "unreadable_span" when
    `unreadable`. `places` are the texts of the label's settled places,
    which the qualifier sign reads (_qualifier_sign). Empty when none
    shows."""
    texts, places = list(texts), tuple(places)

    def shows(test, text):
        return test(text, places) if test is _qualifier_sign else test(text)

    return tuple(name for name, test in DOUBT_SIGNS
        if (unreadable if test is None else any(shows(test, text) for text in texts)))


# Markdown emphasis a reader or an expert may write around a name ("*Epipsocus*").
_EMPHASIS = str.maketrans("", "", "*_")


def _first_letter_capital(text: str) -> str:
    """The text with its first letter a capital."""
    return re.sub(r"[^\W\d_]", lambda letter: letter.group().upper(), text, count=1)


def query_names_a_genus(query: str | None) -> bool:
    """Whether a GBIF query names a genus (B1 of #289's second review, B2 of
    its third): the scientific-name parser reads a name in it as written
    ("Epipsocus", "Epipsocus sp. 1", "Epipsocus prob. sp. 1"), with the
    emphasis marks "*" and "_" dropped and its first letter a capital
    ("epipsocus", "*Epipsocus*", "epipsocus sp. 1"), or as its tokens
    (_tokens: what the label check sheds, shed) with the first letter a
    capital ("Epipsocus(?)"); or, its morphocodes (NO_GENUS) aside, a token
    of it may be a genus, as the label check judges one (may_be_genus:
    "EPIPSOCUS", "ep1psocus", "Epipsocu5", "(epipsocus)", "E." in "E. sp.
    1", "E.?", an "Epipsocus" with an accented capital). A morphocode alone
    ("sp. 30 <female sign>", "Sp. 22", "sp 22", "sp #1") names none."""
    if not query or not query.strip():
        return False
    capital = _first_letter_capital(query.translate(_EMPHASIS).strip())
    plain = _first_letter_capital(" ".join(_tokens(query)))
    if any(text and taxonomy_scientific_name(text) is not None for text in (query, capital, plain)):
        return True
    return any(may_be_genus(token) for token in _tokens(NO_GENUS.sub(" ", plain)))


def _bare(text: str) -> str:
    """The text's letters and digits, case folded: case, spaces,
    punctuation and sex signs stripped."""
    return "".join(c for c in text.casefold() if c.isalnum())


def query_is_the_code(query: str, literal: str) -> bool:
    """Whether a GBIF query asks the morphocode `literal` itself, case,
    spaces, punctuation and sex signs aside ("Sp.30" and "SP 30" for "sp. 30
    <female sign>"; N2 of #289's fourth review). Any other query is not: a
    genus, a misread one ("Epipsocu55", which query_names_a_genus does not
    count), a slide number, another code, or nothing at all."""
    return _bare(query) == _bare(literal)


def taxon_query_grounded(query: str, literal: str) -> bool:
    """Whether GBIF was asked about the whole name this taxon literal writes
    (taxon_queries). A query for part of it ("Danaus plexippus" for "Danaus
    plexippus megalippe") or for another name on its line is not."""
    return collapse(query) in taxon_queries(literal)


def _name_parts(text: str) -> tuple | None:
    name = taxonomy_scientific_name(text)
    if name is None or not name.genus:
        return None
    return name.genus, name.subgenus, tuple(name.epithets), name.marker


def longer_name(quote: str, literal: str) -> str | None:
    """The name a taxon candidate's quote writes around its literal, when the
    scientific-name parser reads more of the name there than in the literal
    alone: from the literal on, a subspecies after a species ("Danaus
    plexippus megalippe" quoted for the literal "Danaus plexippus", N3 of
    #284's third review) or an epithet after a genus; or, for a literal in
    which the parser reads no genus, with the word the quote writes
    immediately before the literal when it may be a genus (word_before,
    GENUS_SHAPED), a genus before it ("Epipsocus sp. 1" quoted for the
    literal "sp. 1", and "Epipsocus" with "sp. 1" on the next line; B1 of
    #289's review). None when both name the same genus, subgenus, epithets
    and marker (an author, a year, a sex sign or a keyed line's "taxon:"
    aside), or the quote names nothing more. The quote is the reading's own
    text, so its name, not the literal's, is the whole name the label writes
    there. A word before a literal that names its own genus is never part of
    its name ("Det." or a collector on the line above)."""
    start = quote.find(literal)
    written = quote[start:] if start >= 0 else quote
    before = word_before(quote, start) if start > 0 and _name_parts(literal) is None else None
    texts = [written] + ([before + " " + written] if before and GENUS_SHAPED.fullmatch(before) else [])
    for text in texts:
        whole = taxonomy_scientific_name(text)
        if whole is not None and whole.genus and _name_parts(text) != _name_parts(literal):
            return replace(whole, authorship=None).query
    return None


def _evidence_error_note(message: str) -> str:
    text = message.casefold()
    if "unit" in text and "required" in text:
        return "unit_not_written"
    if "reversed" in text:
        return "range_reversed"
    if "uncertainty" in text:
        return "uncertainty_unclear"
    return "not_an_elevation"


def parse_elevation(literal: str, *, reading_texts: Sequence[str]) -> ElevationCheck:
    """A written elevation: its number or range, unit, and approximate marker (G41).

    The unit is only ever the one written ("m", "ft.", "'", "feet"); a bare number
    has none and is no_match here, since a unit is never guessed.
    """
    if not _sources(literal, reading_texts):
        return ElevationCheck(literal, LookupStatus.POLICY, notes=(NOT_IN_SOURCE,))
    try:
        parsed = parse_measurement(literal)
    except EvidenceError as error:
        return ElevationCheck(
            literal, LookupStatus.NO_MATCH, notes=(_evidence_error_note(str(error)),)
        )
    approximate = bool(parsed.qualifiers)
    if parsed.from_unit != parsed.to_unit:
        return ElevationCheck(
            literal,
            LookupStatus.AMBIGUOUS,
            low=parsed.from_quantity,
            high=parsed.to_quantity,
            single=False,
            approximate=approximate,
            notes=("mixed_units",),
        )
    return ElevationCheck(
        literal,
        LookupStatus.SUCCESS,
        unit=parsed.from_unit,
        low=parsed.from_quantity,
        high=parsed.to_quantity,
        single=parsed.single,
        approximate=approximate,
        uncertainty=parsed.uncertainty,
    )


def check_catalog_number(literal: str, *, reading_texts: Sequence[str]) -> CatalogCheck:
    """A Field Museum insect catalog number: 5 to 9 digits after an optional FMNH INS."""
    texts = _sources(literal, reading_texts)
    if not texts:
        return CatalogCheck(literal, LookupStatus.POLICY, notes=(NOT_IN_SOURCE,))
    result = catalog_number_validator(literal, source_text=texts[0])
    number = (result.parsed or {}).get("catalog_number")
    return CatalogCheck(literal, result.outcome, number, tuple(result.warnings))


def _hundredths(value: Decimal) -> str:
    text = format(value.quantize(HUNDREDTH, rounding=ROUND_HALF_EVEN), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _quantity(text: str) -> Decimal:
    try:
        value = Decimal(text.replace(",", ""))
    except InvalidOperation:
        raise ValueError("not a plain decimal quantity") from None
    if not value.is_finite():
        raise ValueError("not a plain decimal quantity")
    return value


def feet_to_metres(quantity: str) -> str:
    """Feet to metres by the exact factor (1 ft = 0.3048 m), kept to hundredths (G41)."""
    return _hundredths(_quantity(quantity) * METRES_PER_FOOT)


def metres_to_feet(quantity: str) -> str:
    """Metres to feet by the exact factor (1 m = 1/0.3048 ft), kept to hundredths (G41)."""
    return _hundredths(_quantity(quantity) / METRES_PER_FOOT)
