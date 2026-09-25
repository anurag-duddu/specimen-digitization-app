"""PLAN 4.8's place-request filter (HARNESS.md section 7): the one place that
decides what label text a place request may carry. The geography tool applies
it to every request it sends and S8's tiers to every value theirs send, so it
imports nothing of the harness.

A value a request takes from the record or from a tier-1 name must be a
whole-token slice of its sources: the reading's place-field literals and
unassigned locality text, the names tier 1 returns, and in "fill the rest" the
reviewer's value in a place field. The record's readings, which every call
names, are read for the cuts but are no source, and a value drawn from anything
else is refused. From those values, and only there, the filter cuts by
character span every token of every literal any reading assigns to a non-place
field and of every value a reviewer puts in one; every token of every clause,
between commas, semicolons or line breaks, that holds a collector or determiner
marker the profile's notations name, wherever the marker sits in it; every
token that carries a digit; the month names and abbreviations the profile's
date notations list, in English and in Spanish, in any case; a Roman month
beside a day or a year; and a date connector inside a date. So a value cut
short inside a token loses it. A
notation token that survives may then be written out in each of its full forms
from the profile's table; a notation is cut whenever one of its full forms is,
and each form a full form makes is cut again by character, so no expansion
brings back a cut character. A tier-1 identifier goes back unchanged to the
source that returned it in the field that carries that source's ids, when it
matches that source's documented pattern (PLAN 4.8 as #200 states it). Text the
filter cannot recognize, such as text no reading assigns to any field and no
marker accompanies, can still leave: that is its stated limit.
"""

from __future__ import annotations

import itertools
import json
import re
import unicodedata
from bisect import bisect_right
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import NamedTuple, Protocol

# PLAN 4.8's place fields; every other field is a non-place field.
PLACE_FIELDS = ("country", "province_state", "county", "city", "precise_location")
# A clause ends at a comma, a semicolon or a line break.
SEPARATOR = re.compile(r"(\r?\n|[,;])")
TOKEN = re.compile(r"([^\s,;]+)")
# A day or a year as written, which puts a Roman numeral beside it in the month
# position: 3, 14, 1946, the profile's year forms '46 and -46 with any
# apostrophe or dash, or an ordinal day in st, nd, rd, th, d, er, º or ª, each
# read bare, so with any punctuation before or after it, "1946." or "(1946)"
# (PLAN 4.8 on main after #203; the coordinator's rulings of 2026-09-25). A
# range whose parts, split at a dash or a slash, are each one counts too.
DATE_NUMBER = re.compile(
    r"\d{1,2}|\d{4}|\d{1,2}(?:st|nd|rd|th|d|er|º|ª)", re.IGNORECASE
)
DATE_RANGE = re.compile(r"[/\-‐‑‒–—―−]")
# The fields of each tier-1 source's answer that carry its own ids, each with
# its documented pattern and the id a matching value holds (PLAN 4.8 as #200
# states it; S8's readers #139, #188 and #190). An identifier carries no label
# text.
IDENTIFIER_FIELDS = {
    # An item's Q-number, in search hits and statement values.
    "wikidata": {"id": re.compile(r"(Q[1-9][0-9]*)")},
    # A subject id: a reconciliation result's id, or a SPARQL subject URI.
    "tgn": {
        "id": re.compile(r"tgn/([0-9]{1,10})"),
        "value": re.compile(r"http://vocab\.getty\.edu/tgn/([0-9]{1,10})"),
    },
    # A GNS feature id, with its minus sign, or a first-order unit code
    # (coordinator ruling).
    "nga": {
        "ufi": re.compile(r"(-?[0-9]{1,10})"),
        "adm1": re.compile(r"([A-Z]{2}-[A-Z0-9]{1,3})"),
    },
}


class PlaceKnowledge(Protocol):
    """What the filter reads in the profile's harness knowledge (G29)."""

    PERSON_MARKERS: Sequence[str]
    MONTH_WORDS: Sequence[str]
    ROMAN_MONTHS: Sequence[str]
    DATE_CONNECTORS: Sequence[str]
    FULL_FORMS: Mapping[str, Sequence[str]]


@dataclass(frozen=True)
class ReviewerValue:
    """A place value the reviewer entered or changed in "fill the rest"
    (HARNESS.md section 13; the coordinator's rulings of 06:36Z, 07:33Z and
    08:01Z on 2026-09-25). `anchors` are every text the run holds for that
    field, none when it holds nothing; `non_place_literals` are the reviewer's
    own non-place values. The reviewer's own text, the tokens matching no
    anchor token by a folded word or by letters and digits run together, is
    cut by those and the other cuts alone; what matches is cut like any other
    source."""

    anchors: Sequence[str]
    non_place_literals: Sequence[str]


class _Cuts(NamedTuple):
    """What the cuts compare a token with: folded words, and the non-place
    values' tokens by their letters and digits run together (08:24Z)."""

    words: frozenset[str]
    runs: frozenset[str]


class _Dates(NamedTuple):
    """The folded words the date cuts read: the Roman months I to XII, the
    month words, and the connectors a date's parts may be joined by."""

    roman: frozenset[str]
    months: frozenset[str]
    connectors: frozenset[str]


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
    readings: Sequence[str],
    reviewer: ReviewerValue | None = None,
) -> list[str] | None:
    """Every form of `text` a place request may carry. None refuses the
    request: `text` is not a whole-token slice of a source, or of a source
    written out in full. Otherwise the clauses that survive the cuts,
    single-spaced and joined by their own separators, first as written, then
    with every notation token in each of its full forms (G29); [] when nothing
    survives, and then nothing is sent.

    `sources` are the reading's place-field literals and unassigned locality
    text, the names tier 1 returned and the reviewer's values in place fields.
    `readings` are the record's reading texts, read for the cuts but no source,
    and required: a call without them is refused.
    `non_place_literals` are every literal any reading assigns to a non-place
    field and every value a reviewer puts in one: a corrected collector's
    spelling matches no reading's literal. `reviewer` marks a place value the
    reviewer entered or changed, whose own text the readings' and the
    harness's non-place values spare (PLAN 4.8 as #209 states it)."""
    table = _full_forms(knowledge)
    allowed = [form for source in sources for form in _forms(source, table)]
    if (
        not readings
        or not text.strip()
        or not any(
            _on_token_edges(source, at, text)
            for source in allowed
            for at in _found(source, text)
        )
    ):
        return None
    context = list(
        dict.fromkeys([*allowed, *(f for r in readings for f in _forms(r, table))])
    )
    places = [(source, at) for source in context for at in _found(source, text)]
    cut = _cut_words(context, non_place_literals, knowledge, table)
    dates = _Dates(
        roman=frozenset(fold(month) for month in knowledge.ROMAN_MONTHS),
        months=frozenset(w for m in knowledge.MONTH_WORDS for w in fold(m).split()),
        connectors=frozenset(fold(c) for c in knowledge.DATE_CONNECTORS),
    )
    literals = {f for literal in non_place_literals for f in _forms(literal, table)}
    spared = None
    if reviewer is not None:
        spared = (
            _cut_words(context, reviewer.non_place_literals, knowledge, table),
            {
                f
                for literal in reviewer.non_place_literals
                for f in _forms(literal, table)
            },
            frozenset(w for a in reviewer.anchors for w in fold(a).split()),
            frozenset(_run(t) for a in reviewer.anchors for t in TOKEN.findall(a)),
        )

    def dropped(value: str, where: Sequence[tuple[str, int]]) -> set[int]:
        """The cut tokens of `value`; with `reviewer`, those of the reviewer's
        own text as its own cuts take them, the rest as every cut does."""
        taken = _dropped(value, where, cut, dates, literals)
        if spared is None:
            return taken
        own_cut, own_literals, anchor_words, anchor_runs = spared
        own = {
            token.start()
            for token in TOKEN.finditer(value)
            if anchor_words.isdisjoint(fold(token.group()).split())
            and _run(token.group()) not in anchor_runs
        }
        return (taken - own) | (
            _dropped(value, where, own_cut, dates, own_literals) & own
        )

    written = _surviving(text, dropped(text, places))
    if not written:
        return []
    # Each form a full form makes is cut again, by character span in the form
    # itself, and a form any cut touches is not sent: an expansion never brings
    # back a cut character (the steward's review of #191).
    written_out = _forms(written, table)[1:]
    return [written, *(f for f in written_out if not dropped(f, [(f, 0)]))]


def place_request_text(
    text: str,
    *,
    sources: Sequence[str],
    non_place_literals: Sequence[str],
    knowledge: PlaceKnowledge,
    readings: Sequence[str],
    reviewer: ReviewerValue | None = None,
) -> str | None:
    """The first of `place_request_forms`, the value as written after the cuts;
    "" when nothing survives, None when it is refused."""
    forms = place_request_forms(
        text,
        sources=sources,
        non_place_literals=non_place_literals,
        knowledge=knowledge,
        readings=readings,
        reviewer=reviewer,
    )
    return None if forms is None else next(iter(forms), "")


def place_request_identifier(
    identifier: str, *, source: str, response: str
) -> str | None:
    """An identifier sent back unchanged to the tier-1 source that returned it
    in the field that carries that source's ids (PLAN 4.8 as #200 states it).
    `response` is that answer's JSON as the tool received it. The identifier is
    checked against that field alone, never another token of the answer, the
    record or a list the agent supplies, so a date or a coordinate the answer
    holds never leaves as one. It carries no label text, so no cut applies;
    None refuses it, and any identifier when the answer isn't JSON."""
    try:
        answer = json.loads(response)
    except ValueError:
        return None
    if identifier in _answered_ids(answer, IDENTIFIER_FIELDS.get(source, {})):
        return identifier
    return None


def _answered_ids(node: object, fields: Mapping[str, re.Pattern[str]]) -> set[str]:
    """The ids a JSON answer holds: each value of a field `fields` names, at any
    depth, that the field's pattern matches whole, as the id it holds."""
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            pattern = fields.get(key)
            if (
                pattern
                and isinstance(value, str | int)
                and not isinstance(value, bool)
                and (match := pattern.fullmatch(str(value)))
            ):
                found.add(match.group(1))
            found |= _answered_ids(value, fields)
    elif isinstance(node, list):
        for item in node:
            found |= _answered_ids(item, fields)
    return found


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
    cut: _Cuts,
    dates: _Dates,
    literals: set[str],
) -> set[int]:
    """Where each token of `text` the cuts take starts. A token is cut when the
    cuts name it, or when the token it lies in is cut in any text the value
    occurs in, so a value that starts or ends inside a token loses it too: the
    "Hoogstraa" of "H. Hoogstraal leg." (the steward's review of #185). There a
    token is cut when the cuts name it, when a date takes it (a Roman month in
    the month position, or a connector inside a date), or when a non-place
    literal covers any of it, so a literal copied short still cuts its whole
    token (PLAN 4.8 in #191)."""
    tokens = [(token.start(), token.end()) for token in TOKEN.finditer(text)]
    dropped = {start for start, end in tokens if _cut(text[start:end], cut)}
    spans: dict[str, list[tuple[int, int]]] = {}
    for source, at in places:
        if source not in spans:
            dated = _date_cuts(source, dates)
            covered = [
                (a, a + len(lit)) for lit in literals for a in _found(source, lit)
            ]
            spans[source] = [
                (token.start(), token.end())
                for token in TOKEN.finditer(source)
                if token.start() in dated
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


def _date_cuts(text: str, dates: _Dates) -> set[int]:
    """Where each token of `text` starts that a date takes beyond its digits
    and month words (the coordinator's rulings of 2026-09-24 and 2026-09-25):
    - a Roman month in the month position, a token whose every word is a
      numeral I to XII, beside a day or a year, before or after it, across
      separators ("3 VIII 1946", "Mindanao, VIII, 1946"), and never the "I" of
      "P.I." or the "IV" of "Camp IV". The search for its neighbour skips lone
      punctuation and the date connectors ("3 - VIII - 1946", "3 de VIII");
    - a date connector whose neighbours on both sides, past lone punctuation,
      are cut date tokens: a token with a digit, a month word or a Roman month
      ("3 de VIII de 1946", but never the "de" of "San Juan de Dios")."""
    tokens = list(TOKEN.finditer(text))
    words = [fold(token.group()).split() for token in tokens]
    lone = [not any(c.isalnum() for c in token.group()) for token in tokens]
    joins = [len(w) == 1 and w[0] in dates.connectors for w in words]

    def beside(index: int, step: int, past_connectors: bool) -> int | None:
        index += step
        while 0 <= index < len(tokens) and (
            lone[index] or (past_connectors and joins[index])
        ):
            index += step
        return index if 0 <= index < len(tokens) else None

    roman = {
        index
        for index, word in enumerate(words)
        if word
        and dates.roman.issuperset(word)
        and any(
            found is not None and _date_number(tokens[found].group())
            for found in (beside(index, -1, True), beside(index, 1, True))
        )
    }

    def cut_date(index: int | None) -> bool:
        return index is not None and (
            index in roman
            or any(c.isdigit() for c in tokens[index].group())
            or not dates.months.isdisjoint(words[index])
        )

    inside = {
        index
        for index in range(len(tokens))
        if joins[index]
        and cut_date(beside(index, -1, False))
        and cut_date(beside(index, 1, False))
    }
    return {tokens[index].start() for index in roman | inside}


def _date_number(token: str) -> bool:
    """A day or a year as the month position reads it, bare: 3, 1946, '46,
    "3rd", "1º", or a range of them split at a dash or a slash ("3-4",
    "1946/47")."""
    bare = _bare(token)
    if DATE_NUMBER.fullmatch(bare):
        return True
    parts = DATE_RANGE.split(bare)
    return len(parts) > 1 and all(DATE_NUMBER.fullmatch(part) for part in parts)


def _bare(token: str) -> str:
    """`token` without what isn't a letter or a digit at either end: "'46" and
    "–46" are "46", and "(1946)" and "1946?" are "1946". A modifier letter such
    as U+02BC ("ʼ46") is an apostrophe here, not a letter (08:01Z)."""
    start, end = 0, len(token)
    while start < end and not _letter_or_digit(token[start]):
        start += 1
    while end > start and not _letter_or_digit(token[end - 1]):
        end -= 1
    return token[start:end]


def _letter_or_digit(character: str) -> bool:
    return character.isalnum() and unicodedata.category(character) != "Lm"


def _run(text: str) -> str:
    """`text`'s letters and digits run together, folded: "F.G." is "fg"."""
    return "".join(fold(text).split())


def _cut_words(
    sources: Sequence[str],
    non_place_literals: Sequence[str],
    knowledge: PlaceKnowledge,
    table: Mapping[str, tuple[str, ...]],
) -> _Cuts:
    """The folded words the cuts name, and every character of a token that
    holds one is cut: every word of every non-place literal in any of its
    forms; every word of every source clause that holds a marker; the month
    words; and a notation's own when a full form of it is cut. The non-place
    literals' tokens also cut by their letters and digits run together, so
    "F.G. Wermer" cuts "FG" and "Wer-mer" (the coordinator's ruling of 08:24Z
    on 2026-09-25)."""
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
    runs = {
        _run(token)
        for literal in non_place_literals
        for form in _forms(literal, table)
        for token in TOKEN.findall(form)
    }
    return _Cuts(frozenset(words), frozenset(runs - {""}))


def _cut(token: str, cuts: _Cuts) -> bool:
    """A token that carries a digit, any word the cuts name, or a non-place
    literal's token by its letters and digits run together."""
    return (
        any(c.isdigit() for c in token)
        or not cuts.words.isdisjoint(fold(token).split())
        or _run(token) in cuts.runs
    )


def _joint(separators: Sequence[str]) -> str:
    """What joins two surviving clauses: a line break when the text between
    them held one, otherwise its first comma or semicolon."""
    if any("\n" in separator for separator in separators):
        return "\n"
    return separators[0] + " "
