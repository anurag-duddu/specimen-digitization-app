"""PLAN 4.8's place-request filter (HARNESS.md section 7): the one place that
decides what label text a place request may carry. The geography tool applies
it to every request it sends and S8's tiers to every value theirs send, so it
imports nothing of the harness.

A value a request takes from the reading, from tier 1 or from a reviewer draws
only on exact substrings of its sources: the record's readings, the names tier
1 returns, and in "fill the rest" the reviewer's value in a place field. A value
drawn from anything else is refused. From those values, and only there, the
filter cuts every token of every literal any reading assigns to a non-place
field and of every value a reviewer puts in one; every token of every clause,
between commas, semicolons or line breaks, that holds a collector or determiner
marker the profile's notations name, wherever the marker sits in it; every
token that carries a digit; and the month names, abbreviations and Roman months
the profile lists. A notation token that survives may then be written out in
each of its full forms from the profile's table, and a notation is cut whenever
one of its full forms is. Text the filter cannot recognize, such as a name no
reading assigns to any field and no marker accompanies, can still leave: that
is its stated limit.
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
) -> list[str] | None:
    """Every form of `text` a place request may carry. None refuses the
    request: `text` is not an exact substring of a source, or of a source
    written out in full. Otherwise the clauses that survive the cuts,
    single-spaced and joined by their own separators, first as written, then
    with every notation token in each of its full forms (G29); [] when nothing
    survives, and then nothing is sent.

    `sources` are the record's reading texts, the names tier 1 returned and the
    reviewer's values in place fields. `non_place_literals` are every literal
    any reading assigns to a non-place field and every value a reviewer puts
    in one: a corrected collector's spelling matches no reading's literal."""
    table = _full_forms(knowledge)
    readable = [form for source in sources for form in _forms(source, table)]
    if not text.strip() or not any(text in source for source in readable):
        return None
    cut = _cut_words(readable, non_place_literals, knowledge, table)
    roman = frozenset(fold(month) for month in knowledge.ROMAN_MONTHS)
    written = _surviving(text, cut, roman)
    return _forms(written, table) if written else []


def place_request_text(
    text: str,
    *,
    sources: Sequence[str],
    non_place_literals: Sequence[str],
    knowledge: PlaceKnowledge,
) -> str | None:
    """The first of `place_request_forms`, the value as written after the cuts;
    "" when nothing survives, None when it is refused."""
    forms = place_request_forms(
        text,
        sources=sources,
        non_place_literals=non_place_literals,
        knowledge=knowledge,
    )
    return None if forms is None else next(iter(forms), "")


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
    for literal in {*place_literals, *assigned}:
        for at in _found(text, literal):
            free[at : at + len(literal)] = [False] * len(literal)
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


def _surviving(text: str, cut: frozenset[str], roman: frozenset[str]) -> str:
    """The clauses of `text` that keep a word after the cuts, single-spaced and
    joined by their own separators."""
    parts = SEPARATOR.split(text)
    left: list[str] = []
    between: list[str] = []
    for index, clause in enumerate(parts[::2]):
        tokens = [token for token in clause.split() if not _cut(token, cut, roman)]
        if fold(" ".join(tokens)):
            left.append((_joint(between) if left else "") + " ".join(tokens))
            between = []
        if 2 * index + 1 < len(parts):
            between.append(parts[2 * index + 1])
    return "".join(left)


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


def _cut(token: str, words: frozenset[str], roman: frozenset[str]) -> bool:
    """A token that carries a digit or any word the cuts name, or whose every
    word is a Roman month ("VIII", never the "I" of "P.I.")."""
    found = fold(token).split()
    return (
        any(c.isdigit() for c in token)
        or not words.isdisjoint(found)
        or bool(found)
        and roman.issuperset(found)
    )


def _joint(separators: Sequence[str]) -> str:
    """What joins two surviving clauses: a line break when the text between
    them held one, otherwise its first comma or semicolon."""
    if any("\n" in separator for separator in separators):
        return "\n"
    return separators[0] + " "
