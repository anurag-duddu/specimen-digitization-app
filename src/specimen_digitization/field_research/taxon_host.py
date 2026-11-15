"""The host a label writes, which is never the specimen's taxon (the ontology's rule host_is_no_taxon).

A host is the animal or plant the specimen was taken from: Darwin Core's associatedTaxa holds
it, never the specimen's scientificName, and none of the profile's 20 fields holds it. A label
writes it after a host marker, the ontology's notation host_marker ("Host Thomomys", "Ex. Canis
familiaris", "ex Peromyscus leucopus"). The markers are read from that notation, the one source
of the label's notations (plan WP 2.2).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from functools import cache

# Brackets, quotes and punctuation a marker may carry around it ("(ex", "Host:").
_AROUND = "()[]{}\"'`,;:"


@cache
def host_markers() -> frozenset[str]:
    """The host markers, the written forms of the ontology's notation host_marker, folded and
    without a final period: "host", "ex", "on", "from"."""
    from specimen_digitization.ontology import ontology

    [entry] = [notation for notation in ontology().notations if notation.id == "host_marker"]
    return frozenset(form.casefold().rstrip(".") for form in entry.written)


def _marker(word: str) -> bool:
    """Whether a word is a host marker: the whole word, its brackets, quotes and punctuation
    around it set aside, letter case and one final period aside ("Ex.", "(ex", "Host:"). A
    word that only ends in a marker ("Mex.", "Hosts", "Upon") is none."""
    word = word.strip(_AROUND)
    if word.endswith("."):
        word = word[:-1]
    return bool(word) and word.casefold() in host_markers()


def _places(text: str, literal: str) -> list[int]:
    """Where the text writes the literal as whole name tokens, any run of white space standing
    for each of its runs of white space: the start of each occurrence, a letter or a digit
    neither right before nor right after it ("Musca" is not written inside "Muscardinus"; the
    "Canis familiaris" of "Ex.Canis familiaris" is written)."""
    words = literal.split()
    if not words:
        return []
    pattern = re.compile(r"(?<![^\W_])" + r"\s+".join(re.escape(word) for word in words) + r"(?![^\W_])")
    return [match.start() for match in pattern.finditer(text)]


def host_written(literal: str | None, reading_texts: Sequence[str]) -> bool:
    """Whether a taxon literal is a host, or a taxon associated with one, that the labels write:
    its first word is a host marker ("Ex. Canis familiaris"), or some reading writes the
    literal, as whole name tokens, after a marker anywhere before it on its line, glued to it or
    not ("ex Peromyscus\\nleucopus", "Ex.Canis familiaris", "from nest of Formica rufa"). Each
    occurrence of the literal in each reading counts: one after a marker makes it a host. A
    name with no marker before it on its line ("CYNOMYS", "Mex. Canis familiaris", the "Aus
    bus" of "Aus bus on Quercus") is not, nor is a name written only inside a longer word
    ("Musca" in "Host Muscardinus avellanarius")."""
    if not literal or not literal.strip():
        return False
    if _marker(literal.split()[0]):
        return True
    for text in reading_texts:
        for start in _places(text, literal):
            # The words before the literal on its line, a marker glued to the literal ("Ex.Canis")
            # among them.
            if any(_marker(word) for word in text[:start].rpartition("\n")[2].split()):
                return True
    return False
