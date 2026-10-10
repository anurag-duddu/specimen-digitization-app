"""Abbreviations a label writes, read by one letter rule rather than a table.

Labels abbreviate place names in every language and country: "P.I.",
"N.S.W.", "Guat.", "Edo.", "Dpto.", "Qld.", "Mts.", "Ft.". No list of them is
kept. A place expert that knows what an abbreviation stands for looks up the
expansion ("Philippine Islands" for "P.I."; "Davao Province" for "Davao,
Prov.", a unit word written out), and the place rule
(agreement.place_settling) accepts that lookup for the label's text only when
the text fits the expansion (`fit`):

- The text is abbreviated: it has a period, or its letters are all capitals
  and at most four ("NSW", "UK"), or one of its groups is a form written
  without a period (PERIOD_FREE: "Mt", "St", "Ft").
- The expansion has more letters than the text.
- The text splits into letter groups at periods, spaces and hyphens, and the
  expansion into words at the same. Letters and digits are compared
  casefolded with accents dropped; any other character is left out.
- The groups map, in order, onto consecutive words of the expansion, which
  may skip only its minor words (MINOR_WORDS: "Estado de Mexico" for "Edo.
  Mex."). Every group maps onto one word, and every word left over is minor.
- Each group is its word written in full, or one of the two forms an
  abbreviation takes (`_form`), at most 60% of the word's letters
  (MAX_SHARE): a truncation, the word's first letters ("Guat" for
  "Guatemala", "Prov" for "Province", "P" for "Philippine"), or a
  contraction, the word's first and last letters with letters of the word
  between them in order ("Sta" for "Santa", "Ft" for "Fort", "Mts" for
  "Mountains", "Dpto" for "Departamento", "Qld" for "Queensland"). A name
  with a letter or two dropped is no abbreviation, period or not:
  "Chimaltenago." keeps 12 of 13 letters and "Guatmala." 8 of 9; such a name
  is a near spelling (G34) or nothing.
- At least one group is a truncation or a contraction: names written in
  full with a minor word left out ("Rio Janeiro." for "Rio de Janeiro") fit
  nothing.
- Text of four capitals or fewer and no period ("UK", "USA", "NSW", "MALI")
  is read only as initials, one letter for each word of an expansion of two
  or more words: "UK" fits "United Kingdom", never "Ukraine", "MALI" or
  "IRAN" fits no country, and one capital alone fits nothing.

A fit whose groups are all single letters (or minor words written in full)
is an initialism (`initialism`: "P.I.", "S.A.", "N.S.W.", "UK"). The letters
of an initialism allow many places ("S.A." fits "South Africa", "South
Australia" and "Saudi Arabia"), so the step settles a place on one only when
another place field of the label, settled on its own evidence, lies inside
it (step._corroborate). In every case an approved gazetteer's answer still
decides the place, and an expansion or the label's own text that a source
answers as a different place leaves the field for review
(agreement.rival_expansion).
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
# A truncation or a contraction has at most this share of its word's letters
# (3/5, 60%): "Sta" of "Santa" (3 of 5) is one, "Guatmala" of "Guatemala" is not.
MAX_SHARE = (3, 5)
WHOLE, TRUNCATION, CONTRACTION = "whole", "truncation", "contraction"


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


def _capitals_only(text: str) -> bool:
    """Four capitals or fewer and no period ("UK", "NSW", "MALI", "S"):
    initials only, of two words or more."""
    letters = [c for c in text if c.isalpha()]
    return "." not in text and 0 < len(letters) <= MAX_CAPITALS and all(c.isupper() for c in letters)


def _form(group: str, word: str) -> str | None:
    """How a group stands for its word (both as _letters gives them): WHOLE,
    the word itself; TRUNCATION, the word's first letters; CONTRACTION, the
    word's first and last letters with letters of the word between them in
    order. A truncation or a contraction has at most MAX_SHARE of the word's
    letters. None when it is none of these."""
    if not group or not word:
        return None
    if group == word:
        return WHOLE
    most, of = MAX_SHARE
    if len(group) * of > len(word) * most:
        return None
    if word.startswith(group):
        return TRUNCATION
    if group[0] == word[0] and group[-1] == word[-1]:
        rest = iter(word[1:-1])
        if all(letter in rest for letter in group[1:-1]):
            return CONTRACTION
    return None


def _mapped(groups: tuple[tuple[str, str], ...], words: tuple[tuple[str, str], ...], *, initials: bool = False):
    """The groups mapped in order onto consecutive words, minor words skipped,
    as (group, word) pairs as written; None when they do not map. With
    `initials`, each group is one letter, the first of its word."""

    @cache
    def step(g: int, w: int) -> tuple[tuple[str, str], ...] | None:
        if g == len(groups):
            return () if all(letters in MINOR_WORDS for _, letters in words[w:]) else None
        if w == len(words):
            return None
        (group, group_letters), (word, word_letters) = groups[g], words[w]
        form = _form(group_letters, word_letters)
        if initials:
            form = TRUNCATION if len(group_letters) == 1 and word_letters.startswith(group_letters) else None
        if form is not None:
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
    if _capitals_only(abbreviation):
        letters = tuple((c, _letters(c)) for c in abbreviation if c.isalpha())
        return _mapped(letters, words, initials=True) if len(letters) >= 2 else None
    found = _mapped(groups, words)
    if found is None or all(_letters(group) == _letters(word) for group, word in found):
        return None
    return found


def fits(abbreviation: str, expansion: str) -> bool:
    """Whether the abbreviation fits the expansion by the letter rule."""
    return fit(abbreviation, expansion) is not None


def initialism(pairs: tuple[tuple[str, str], ...]) -> bool:
    """Whether a fit is an initialism: every group one letter, or a minor
    word written in full ("P.I.", "S.A.", "N.S.W.", "UK", "R. de J.")."""
    return bool(pairs) and all(
        len(_letters(group)) == 1 or _letters(group) in MINOR_WORDS for group, _ in pairs) and any(
        len(_letters(group)) == 1 for group, _ in pairs)


def shown(pairs: tuple[tuple[str, str], ...]) -> str:
    """A fit as the evidence row shows it: "P = Philippine, I = Islands"."""
    return ", ".join(f"{group} = {word}" for group, word in pairs)
