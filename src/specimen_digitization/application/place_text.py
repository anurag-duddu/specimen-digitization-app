"""PLAN 4.8's place-request filter (HARNESS.md section 7): the one place that
decides what label text a place request may carry. The geography tool applies
it to every request it sends and S8's tiers to every value theirs send, so it
imports nothing of the harness.

A value a request takes from the record or from a tier-1 name must be a
whole-token slice of its sources: the reading's place-field literals and
unassigned locality text, the names tier 1 returns, and in "fill the rest" the
reviewer's value in a place field. The record's readings are read for the cuts
but are no source, and a value drawn from anything else is refused. From those
values, and only there, the filter cuts by character span every token of every
literal any reading assigns to a non-place field and of every value a reviewer
puts in one; every token of every clause, between commas, semicolons or line
breaks, that holds a collector or determiner marker the profile's notations
name, wherever the marker sits in it; every token that carries a digit; the
month names and abbreviations the profile lists, in any case; and a Roman month
beside a day or a year. So a value cut short inside a token loses it. A
notation token that survives may then be written out in each of its full forms
from the profile's table, and a notation is cut whenever one of its full forms
is. A tier-1 identifier goes back unchanged to the source that returned it when
it matches that source's documented pattern (PLAN 4.8 in #191). Text the filter
cannot recognize, such as a name no reading assigns to any field and no marker
accompanies, can still leave: that is its stated limit.
"""

from __future__ import annotations

import itertools
import re
import unicodedata
from bisect import bisect_right
from collections.abc import Mapping, Sequence
from typing import Protocol

# PLAN 4.8's place fields; every other field is a non-place field.
PLACE_FIELDS = ("country", "province_state", "county", "city", "precise_location")
# A clause ends at a comma, a semicolon or a line break.
SEPARATOR = re.compile(r"(\r?\n|[,;])")
TOKEN = re.compile(r"([^\s,;]+)")
# A day or a year as written, which puts a Roman numeral beside it in the month
# position: 3, 14, 1946, or the profile's year forms '46 and -46.
DATE_NUMBER = re.compile(r"\d{1,2}|\d{4}|['’-]\d{2}")
# Each tier-1 source's documented identifier patterns (PLAN 4.8 in #191; S8's
# readers #139, #188 and #190). An identifier carries no label text.
IDENTIFIERS = {
    "wikidata": (re.compile(r"Q[1-9][0-9]*"),),  # An item's Q-number.
    "tgn": (re.compile(r"[0-9]{1,10}"),),  # A TGN subject id.
    # A GNS feature id, or a first-order unit code (coordinator ruling).
    "nga": (re.compile(r"-?[0-9]{1,10}"), re.compile(r"[A-Z]{2}-[A-Z0-9]{1,3}")),
}


class PlaceKnowledge(Protocol):
    """What the filter reads in the profile's harness knowledge (G29)."""

    PERSON_MARKERS: Sequence[str]
    MONTH_WORDS: Sequence[str]
    ROMAN_MONTHS: Sequence[str]
    FULL_FORMS: Mapping[str, Sequence[str]]


def fold(text: str) -> str:
    """Casefold, strip diacritics and turn anything but letters and digits into
    single spaces: "Chimaltenángo," folds to "chimaltenango", "P.I." to "p i"."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    kept = "".join(
        c if c.isalnum() else " " for c in decomposed if not unicodedata.combining(c)
    )
    return " ".join(kept.split())


def place_request_forms(
    text: str,
    *,
    sources: Sequence[str],
    non_place_literals: Sequence[str],
    knowledge: PlaceKnowledge,
    readings: Sequence[str] = (),
) -> list[str] | None:
    """Every form of `text` a place request may carry. None refuses the
    request: `text` is not a whole-token slice of a source, or of a source
    written out in full. Otherwise the clauses that survive the cuts,
    single-spaced and joined by their own separators, first as written, then
    with every notation token in each of its full forms (G29); [] when nothing
    survives, and then nothing is sent.

    `sources` are the reading's place-field literals and unassigned locality
    text, the names tier 1 returned and the reviewer's values in place fields.
    `readings` are the record's reading texts, read for the cuts but no source.
    `non_place_literals` are every literal any reading assigns to a non-place
    field and every value a reviewer puts in one: a corrected collector's
    spelling matches no reading's literal."""
    table = _full_forms(knowledge)
    allowed = [form for source in sources for form in _forms(source, table)]
    if not text.strip() or not any(
        _on_token_edges(source, at, text)
        for source in allowed
        for at in _found(source, text)
    ):
        return None
    context = list(
        dict.fromkeys([*allowed, *(f for r in readings for f in _forms(r, table))])
    )
    places = [(source, at) for source in context for at in _found(source, text)]
    cut = _cut_words(context, non_place_literals, knowledge, table)
    roman = frozenset(fold(month) for month in knowledge.ROMAN_MONTHS)
    literals = {f for literal in non_place_literals for f in _forms(literal, table)}
    written = _surviving(text, _dropped(text, places, cut, roman, literals))
    return _forms(written, table) if written else []


def place_request_text(
    text: str,
    *,
    sources: Sequence[str],
    non_place_literals: Sequence[str],
    knowledge: PlaceKnowledge,
    readings: Sequence[str] = (),
) -> str | None:
    """The first of `place_request_forms`, the value as written after the cuts;
    "" when nothing survives, None when it is refused."""
    forms = place_request_forms(
        text,
        sources=sources,
        non_place_literals=non_place_literals,
        knowledge=knowledge,
        readings=readings,
    )
    return None if forms is None else next(iter(forms), "")


def place_request_identifier(
    identifier: str, *, source: str, returned: Sequence[str]
) -> str | None:
    """An identifier a tier-1 source returned, sent back to that same source
    unchanged when it matches one of the source's documented patterns. It
    carries no label text, so no cut applies; None refuses it (PLAN 4.8 in
    #191)."""
    patterns = IDENTIFIERS.get(source, ())
    if identifier in returned and any(p.fullmatch(identifier) for p in patterns):
        return identifier
    return None


def unassigned_text(
    text: str, place_literals: Sequence[str], assigned: Sequence[str]
) -> list[str]:
    """PLAN 4.8's unassigned locality text of one reading: on the lines holding
    its place literals, each piece that no literal any reading assigns covers,
    in order ("Mindanao" in 105526321's "Mindanao, P.I.")."""
    starts = [0, *(i + 1 for i, c in enumerate(text) if c == "\n")]
    held: set[int] = set()
    for literal in place_literals:
        for at in _found(text, literal):
            first = bisect_right(starts, at) - 1
            held.update(range(first, bisect_right(starts, at + len(literal) - 1)))
    free = [True] * len(text)
    tokens = list(TOKEN.finditer(text))
    for literal in {*place_literals, *assigned}:
        for at in _found(text, literal):
            end = at + len(literal)
            free[at:end] = [False] * len(literal)
            for token in tokens:  # A literal copied short covers its whole token.
                if token.start() < end and at < token.end():
                    free[token.start() : token.end()] = [False] * len(token.group())
    pieces = []
    for number in sorted(held):
        end = starts[number + 1] - 1 if number + 1 < len(starts) else len(text)
        line = "".join(text[i] if free[i] else "\n" for i in range(starts[number], end))
        pieces += [piece.strip(" \t\r,;") for piece in line.split("\n")]
    return [piece for piece in pieces if any(c.isalpha() for c in piece)]


def _found(text: str, literal: str) -> list[int]:
    """Where each occurrence of `literal` starts in `text`."""
    found, at = [], text.find(literal) if literal else -1
    while at != -1:
        found.append(at)
        at = text.find(literal, at + 1)
    return found


def _on_token_edges(source: str, at: int, text: str) -> bool:
    """Whether `text`, found at `at` in `source`, starts and ends on token edges
    once its own outer spaces and separators are set aside (PLAN 4.8 in #191):
    "Mt. McKinley" of "E. slope Mt. McKinley", never "t. McKinl"."""
    core = text.strip().strip(",;").strip()
    if not core:
        return False
    start = at + text.index(core)
    end = start + len(core)
    return (start == 0 or _edge(source[start - 1])) and (
        end == len(source) or _edge(source[end])
    )


def _edge(character: str) -> bool:
    return character.isspace() or character in ",;"


def _full_forms(knowledge: PlaceKnowledge) -> dict[str, tuple[str, ...]]:
    return {
        fold(written): tuple(full) for written, full in knowledge.FULL_FORMS.items()
    }


def _forms(text: str, table: Mapping[str, tuple[str, ...]]) -> list[str]:
    """`text`, then each way of writing all its notation tokens out in full
    ("Mindanao Is." is also "Mindanao Island" and "Mindanao Islands")."""
    parts = TOKEN.split(text)
    choices = [
        table.get(fold(part), (part,)) if i % 2 else (part,)
        for i, part in enumerate(parts)
    ]
    return list(dict.fromkeys([text, *map("".join, itertools.product(*choices))]))


def _dropped(
    text: str,
    places: Sequence[tuple[str, int]],
    cut: frozenset[str],
    roman: frozenset[str],
    literals: set[str],
) -> set[int]:
    """Where each token of `text` the cuts take starts. A token is cut when the
    cuts name it, or when the token it lies in is cut in any text the value
    occurs in, so a value that starts or ends inside a token loses it too: the
    "Hoogstraa" of "H. Hoogstraal leg." (the steward's review of #185). There a
    token is cut when the cuts name it, when it is a Roman month in the month
    position, or when a non-place literal covers any of it, so a literal copied
    short still cuts its whole token (PLAN 4.8 in #191)."""
    tokens = [(token.start(), token.end()) for token in TOKEN.finditer(text)]
    dropped = {start for start, end in tokens if _cut(text[start:end], cut)}
    spans: dict[str, list[tuple[int, int]]] = {}
    for source, at in places:
        if source not in spans:
            months = _roman_months(source, roman)
            covered = [
                (a, a + len(lit)) for lit in literals for a in _found(source, lit)
            ]
            spans[source] = [
                (token.start(), token.end())
                for token in TOKEN.finditer(source)
                if token.start() in months
                or _cut(token.group(), cut)
                or any(lo < token.end() and token.start() < hi for lo, hi in covered)
            ]
        for start, end in tokens:
            if any(low < at + end and at + start < high for low, high in spans[source]):
                dropped.add(start)
    return dropped


def _surviving(text: str, dropped: set[int]) -> str:
    """The clauses of `text` that keep a word after the cuts, single-spaced and
    joined by their own separators."""
    parts = SEPARATOR.split(text)
    left: list[str] = []
    between: list[str] = []
    start = 0  # Where the clause starts in `text`.
    for index, clause in enumerate(parts[::2]):
        tokens = [
            token.group()
            for token in re.finditer(r"\S+", clause)
            if start + token.start() not in dropped
        ]
        if fold(" ".join(tokens)):
            left.append((_joint(between) if left else "") + " ".join(tokens))
            between = []
        start += len(clause)
        if 2 * index + 1 < len(parts):
            between.append(parts[2 * index + 1])
            start += len(parts[2 * index + 1])
    return "".join(left)


def _roman_months(text: str, roman: frozenset[str]) -> set[int]:
    """Where each Roman month in the month position starts: a token whose every
    word is a numeral I to XII, beside a day or a year, before or after it,
    across separators ("3 VIII 1946", "Mindanao, VIII, 1946"), and never the
    "I" of "P.I." or the "IV" of "Camp IV" (the coordinator's ruling of
    2026-09-24)."""
    tokens = list(TOKEN.finditer(text))
    starts = set()
    for index, token in enumerate(tokens):
        words = fold(token.group()).split()
        beside = tokens[max(index - 1, 0) : index] + tokens[index + 1 : index + 2]
        if (
            words
            and roman.issuperset(words)
            and any(DATE_NUMBER.fullmatch(t.group().strip(".()[]:")) for t in beside)
        ):
            starts.add(token.start())
    return starts


def _cut_words(
    sources: Sequence[str],
    non_place_literals: Sequence[str],
    knowledge: PlaceKnowledge,
    table: Mapping[str, tuple[str, ...]],
) -> frozenset[str]:
    """The folded words no request carries: every word of every non-place
    literal in any of its forms; every word of every source clause that holds a
    marker; the month words; and a notation's own when a full form of it is
    cut, so that no form carries a cut word."""
    markers = {w for marker in knowledge.PERSON_MARKERS for w in fold(marker).split()}
    words = {w for month in knowledge.MONTH_WORDS for w in fold(month).split()}
    for literal in non_place_literals:
        for form in _forms(literal, table):
            words.update(fold(form).split())
    for source in sources:
        for clause in SEPARATOR.split(source)[::2]:
            found = set(fold(clause).split())
            if not found.isdisjoint(markers):
                words |= found
    for written, full in table.items():
        if any(not words.isdisjoint(fold(form).split()) for form in full):
            words.update(written.split())
    return frozenset(words)


def _cut(token: str, words: frozenset[str]) -> bool:
    """A token that carries a digit, or any word the cuts name."""
    return any(c.isdigit() for c in token) or not words.isdisjoint(fold(token).split())


def _joint(separators: Sequence[str]) -> str:
    """What joins two surviving clauses: a line break when the text between
    them held one, otherwise its first comma or semicolon."""
    if any("\n" in separator for separator in separators):
        return "\n"
    return separators[0] + " "
