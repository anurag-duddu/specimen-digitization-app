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

# The elevation parser and the taxon marker projection live with the
# six-specialist harness; they move with these imports when that harness is deleted.
from specimen_digitization.research_harness.evidence import EvidenceError, parse_measurement
from specimen_digitization.research_harness.taxonomy import taxonomy_scientific_name

NOT_IN_SOURCE = "literal_not_in_source"
# The date parser's notes for a literal that is (part of) a hyphen-joined code.
_CODE_NOTES = frozenset({"slide_code", "part_of_hyphenated_token"})


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
    order: str
    century_rule: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in vars(self).items() if v is not None}


@dataclass(frozen=True)
class DateCheck:
    literal: str
    status: LookupStatus
    readings: tuple[DateReading, ...] = ()
    notes: tuple[str, ...] = ()
    check: str = "date_parser"

    @property
    def values(self) -> tuple[str, ...]:
        """The dates the literal can be: each reading's ISO form."""
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


def parse_date(
    literal: str,
    *,
    reading_texts: Sequence[str],
    date_rules: Any = None,
    year_literal: str | None = None,
) -> DateCheck:
    """Every reading a date literal's notation allows (G24, G29; HARNESS.md section 8).

    `date_rules` is the profile's (century rule, Roman months); without it a
    two-digit year stays partial and a Roman month is not read. `year_literal`
    is a year the same reading states elsewhere, the only year a month and day
    alone can take. A literal that is part of a slide-preparation code, or of
    any other hyphen-joined token, in any reading is no date.
    """
    texts = _sources(literal, reading_texts)
    if not texts:
        return DateCheck(literal, LookupStatus.POLICY, notes=(NOT_IN_SOURCE,))
    rules = _date_rules(date_rules)
    results = [
        date_parser(literal, source_text=t, year_literal=year_literal, date_rules=rules)
        for t in texts
    ]
    # A year literal must be in the same reading as the date it completes.
    results = [r for r in results if r.outcome != LookupStatus.POLICY]
    if not results:
        return DateCheck(literal, LookupStatus.POLICY, notes=("year_literal_not_in_reading",))
    # Where one reader shows the literal inside a code, it is not a date at all.
    result = next(
        (r for r in results if _CODE_NOTES & set(r.warnings)), results[0]
    )
    readings = tuple(
        DateReading(
            iso=r["iso"],
            precision=r["precision"],
            order=r["order"],
            century_rule=r["century_rule"],
        )
        for r in (result.parsed or {}).get("readings", ())
    )
    return DateCheck(literal, result.outcome, readings, tuple(result.warnings))


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
# The label words that may follow a morphocode on its line and are no genus,
# as written: the parts a slide mounts, and the sex signs. The one list the
# label check passes over (genus_beside).
NOT_GENERA = frozenset({"legs", "leg", "wings", "wing", "head", "terminalia", "genitalia", "slide", "mount",
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


def token_before(text: str, start: int) -> str | None:
    """The token (_tokens) written immediately before text[start:]: the last
    one before it on its line, or, when its line has none there, the last
    one of the nearest line above that has one. None when there is none.
    When its line writes only the taxon's key before it ("taxon: sp. 30", a
    keyed line Workflow.parse reads), the key is no token, and a keyed line
    above (_KEYED_LINE: "habitat: Mossy forest") is another field's: None."""
    line_start = text.rfind("\n", 0, start) + 1
    own, above = text[line_start:start], list(reversed(text[:line_start].splitlines()))
    keyed = _TAXON_KEY.fullmatch(own) is not None
    for part in above if keyed else [own, *above]:
        tokens = _tokens(part)
        if tokens:
            return None if keyed and _KEYED_LINE.match(part) else tokens[-1]
    return None


def token_after(text: str, end: int) -> str | None:
    """The first token (_tokens) after text[:end] on its line, or None."""
    line_end = text.find("\n", end)
    tokens = _tokens(text[end:] if line_end < 0 else text[end:line_end])
    return tokens[0] if tokens else None


def genus_beside(text: str, start: int, end: int) -> str | None:
    """The token beside text[start:end] that may be a genus (may_be_genus):
    the token written immediately before it (token_before: "Epipsocus" in
    "Epipsocus sp. 1", in "Epipsocus?" with "sp. 1" on the next line, and
    "unreadable" in "[unreadable] sp. 1"), else the first token after it on
    its line unless it is one of NOT_GENERA ("Epipsocus" in "sp. 1
    Epipsocus", never "legs" in "sp. 1 legs"). None when neither is."""
    before = token_before(text, start)
    if before is not None and may_be_genus(before):
        return before
    after = token_after(text, end)
    if after is not None and after not in NOT_GENERA and may_be_genus(after):
        return after
    return None


def label_names_no_genus(code: str, reading_texts: Sequence[str]) -> bool:
    """Whether the label writes the morphocode `code` (morphocode) with no
    genus beside it: some reading writes it, and wherever any reading writes a
    morphocode of that code (NO_GENUS, searched in its text), no token beside
    it may be a genus (genus_beside). This judges the label, not the
    organiser's literal: a candidate "sp. 1" taken from "Epipsocus sp. 1", or
    from "Epipsocus" with "sp. 1" on the next line (105526328's label), names
    a genus, and so does one beside an unclear word ("Epipsocus?", "E.?",
    "[unreadable]", "legs" before it). "Mossy forest 6400'" above "sp. 30"
    (105526321), "V-4-67-1" above "sp 22" (105526327) and "Sp. 22" on a
    label of its own (105526326) do not."""
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


def genus_in_doubt(text: str, literal: str) -> bool:
    """Whether the text, wherever it writes the taxon literal, marks the
    literal's first word, its genus, as doubtful (1c of #289's fifth review):
    - a qualifier (DOUBT_QUALIFIERS, read as the doubt signs read one) in
      the whitespace-separated part of the text that holds that word
      ("cfr.Epipsocus") or in the part just before it, across a line break
      too ("cfr. Epipsocus", "cf." ending the line above);
    - a "?" on that word, in its own part ("Epipsocus?", "?Epipsocus",
      "Epipsocus(?)"), or a "?" standing alone, a part with no letter or
      digit, just before it on its line ("? Epipsocus", "(?) Epipsocus").
    A "?" is any of QUESTION_MARKS. A "?" on another word ("Davao?
    Epipsocus"), any "?" on the line above ("1946?" above "Epipsocus sp.
    1"), one after the genus ("Epipsocus ?") and a qualifier after the genus
    ("Epipsocus cf. sp. 1", G25) are none. False when the text does not
    write the literal."""
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
            if _qualifier(before.group()) or (on_its_line and _has_question_mark(before.group())
                    and not any(c.isalnum() for c in before.group())):
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


# What a reader may write in place of a word it cannot read: the reader
# prompt's "[unreadable]", and the other placeholders a transcriber uses
# (N1 of #289's fourth and fifth reviews), anywhere in a text, in any case;
# and the words "illegible" and "unreadable" standing alone, with no letter
# right before or after them. Rule A (step._whole_label_read) and rule B
# (DOUBT_SIGNS and step._code_label_unreadable) read this one test
# (shows_placeholder).
DOUBT_PLACEHOLDERS = ("[unreadable]", "(unreadable)", "[illegible]", "(illegible)", "[illeg.]", "[illeg]", "(illeg.)",
    "[unclear]", "(unclear)", "[?]", "???", "...", "[...]", "\N{HORIZONTAL ELLIPSIS}")
PLACEHOLDER_WORDS = ("illegible", "unreadable")
_PLACEHOLDER_WORD = re.compile(r"(?<![^\W\d_])(?:" + "|".join(PLACEHOLDER_WORDS) + r")(?![^\W\d_])", re.I)


def shows_placeholder(text: str) -> bool:
    """Whether the text writes a placeholder for a word a reader could not
    read: one of DOUBT_PLACEHOLDERS in any case ("..." also inside "...."),
    or one of PLACEHOLDER_WORDS as a whole word in any case ("Illegible",
    "UNREADABLE"; never "illegibly")."""
    folded = text.casefold()
    return any(placeholder in folded for placeholder in DOUBT_PLACEHOLDERS) or (
        _PLACEHOLDER_WORD.search(text) is not None)


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
# shows it.
DOUBT_SIGNS: tuple[tuple[str, Callable[[str], bool] | None], ...] = (
    ("question_mark", _question_mark),
    ("qualifier", _qualifier),
    ("placeholder", shows_placeholder),
    ("unreadable_span", None),
)


def doubt_signs(texts: Iterable[str], *, unreadable: bool = False) -> tuple[str, ...]:
    """The names of the DOUBT_SIGNS that show, in the list's order: a sign
    whose test any of the texts meets, and "unreadable_span" when
    `unreadable`. Empty when none shows."""
    texts = list(texts)
    return tuple(name for name, shows in DOUBT_SIGNS
        if (unreadable if shows is None else any(shows(text) for text in texts)))


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
