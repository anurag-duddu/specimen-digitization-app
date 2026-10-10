"""Abbreviations a label writes, read by one letter rule rather than a table.

Labels abbreviate place names in every language and country: "P.I.",
"N.S.W.", "Guat.", "Edo.", "Dpto.", "Qld.", "Mts.", "Ft.". No list of them is
kept. A place expert that knows what an abbreviation stands for looks up the
expansion ("Philippine Islands" for "P.I."; "Davao Province" for "Davao,
Prov.", a unit word written out), and the place rule
(agreement.place_settling) accepts that lookup for the label's text only when
the text fits the expansion (`fit`):

- The text is abbreviated: it has a period, or its letters are all capitals
  and at most four ("NSW", "GUAT"), or one of its groups is a form written
  without a period (PERIOD_FREE: "Mt", "St", "Ft").
- The expansion has more letters than the text.
- The text splits into letter groups at periods, spaces and hyphens, and the
  expansion into words at the same. Letters and digits are compared
  casefolded with accents dropped; any other character is left out.
- The groups map, in order, onto consecutive words of the expansion, which
  may skip only its minor words (MINOR_WORDS: "Estado de Mexico" for "Edo.
  Mex."). Every group maps onto one word, and every word left over is minor.
- Each group's letters are a subsequence of its word that starts with the
  word's first letter: "Mts" fits "Mountains", "Guat" fits "Guatemala", "P"
  and "I" fit "Philippine Islands"; a group of one letter is its word's first
  letter.
- A text of two to four capitals and nothing else ("NSW", "USA") may also be
  read one letter per group ("New South Wales").

The rule says only that the letters allow the expansion: "S.A." fits both
"South Australia" and "South Africa". An approved gazetteer's answer still
decides the place, and two fitting expansions that sources answer as
different places leave the field for review (agreement.rival_expansion).
"""

from __future__ import annotations

import re
import unicodedata
from functools import cache

# The words an expansion may skip between the words its groups map onto.
MINOR_WORDS = frozenset("of the and de del la le da do dos das van von y et".split())
# Abbreviations written without a period that are still abbreviations.
PERIOD_FREE = frozenset("mt mts mtn mtns st ste sta sto ft pt co is".split())
# Where a text splits into groups: periods, spaces and hyphens.
SPLIT = re.compile(r"[.\s-]+")
# What a group or word shows without at its ends: anything but a letter or digit.
EDGES = re.compile(r"^[\W_]+|[\W_]+$")
MAX_CAPITALS = 4


def _letters(text: str) -> str:
    """The text's letters and digits, casefolded, accents and other marks dropped."""
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold()) if c.isalnum())


def _groups(text: str) -> tuple[tuple[str, str], ...]:
    """The text's groups split at periods, spaces and hyphens: each as written,
    without the punctuation at its ends ("Davao," is "Davao"), with its
    letters (_letters). A group with no letter or digit is left out."""
    return tuple((EDGES.sub("", piece), letters) for piece in SPLIT.split(text)
        if (letters := _letters(piece)))


def abbreviated(text: str) -> bool:
    """Whether the text is written as an abbreviation: it has a period, its
    letters are all capitals and at most four, or one of its groups is a form
    written without a period (PERIOD_FREE)."""
    letters = [c for c in text if c.isalpha()]
    return ("." in text
        or (0 < len(letters) <= MAX_CAPITALS and all(c.isupper() for c in letters))
        or any(letters in PERIOD_FREE for _, letters in _groups(text)))


def _starts_and_follows(group: str, word: str) -> bool:
    """Whether the group's letters are a subsequence of the word starting with
    the word's first letter."""
    if not group or not word or group[0] != word[0]:
        return False
    rest = iter(word[1:])
    return all(letter in rest for letter in group[1:])


def _mapped(groups: tuple[tuple[str, str], ...], words: tuple[tuple[str, str], ...]):
    """The groups mapped in order onto consecutive words, minor words skipped,
    as (group, word) pairs as written; None when they do not map."""

    @cache
    def step(g: int, w: int) -> tuple[tuple[str, str], ...] | None:
        if g == len(groups):
            return () if all(letters in MINOR_WORDS for _, letters in words[w:]) else None
        if w == len(words):
            return None
        (group, group_letters), (word, word_letters) = groups[g], words[w]
        if _starts_and_follows(group_letters, word_letters):
            rest = step(g + 1, w + 1)
            if rest is not None:
                return ((group, word), *rest)
        return step(g, w + 1) if word_letters in MINOR_WORDS else None

    return step(0, 0)


def fit(abbreviation: str, expansion: str) -> tuple[tuple[str, str], ...] | None:
    """How the abbreviation fits the expansion by the letter rule (module
    docstring): each group, as written, with the word of the expansion it
    stands for; None when it does not fit."""
    if not abbreviated(abbreviation):
        return None
    groups, words = _groups(abbreviation), _groups(expansion)
    if not groups or sum(len(w) for _, w in words) <= sum(len(g) for _, g in groups):
        return None
    readings = [groups]
    written = abbreviation.strip()
    if 2 <= len(written) <= MAX_CAPITALS and written.isalpha() and written.isupper():
        readings.append(tuple((letter, _letters(letter)) for letter in written))
    for reading in readings:
        found = _mapped(reading, words)
        if found is not None:
            return found
    return None


def fits(abbreviation: str, expansion: str) -> bool:
    """Whether the abbreviation fits the expansion by the letter rule."""
    return fit(abbreviation, expansion) is not None


def shown(pairs: tuple[tuple[str, str], ...]) -> str:
    """A fit as the evidence row shows it: "P = Philippine, I = Islands"."""
    return ", ".join(f"{group} = {word}" for group, word in pairs)
