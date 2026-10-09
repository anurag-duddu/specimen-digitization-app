"""When a resolved answer may settle its field (B1 and B2 of #284's reviews).

`refusal` checks every resolved answer, in the expert's answer check
(experts.py, so the model is sent back) and again in the step before the
answer becomes a value (step._refusal). It enforces, in this order:

1. The decided transcript (G19): for each reading the answer names whose
   label has a decided transcript, the decided reading's text contains the
   literal.
2. A whole candidate (B2): the literal is one of the field's candidate
   literals (FieldTask.candidates: the organiser's, and each keyed line the
   parser read) of each reading the answer names, or, on a label with a
   decided transcript, of the decided reading. Literals are compared after
   NFC and whitespace collapse only (checks.collapse): "E. slope" and
   "E.slope" differ. A field with no such candidate is never resolved.
3. Readers and labels that disagree (B1; G19, G20, G27, G32). From the
   field's candidates and the organiser's per-reader verbatims, whatever
   state the organiser gave the field, each label that writes the field
   settles on its own (`labels`):
   - a label with a decided transcript, on its decided reading's one
     candidate literal; its other readers are evidence only, and a label
     whose decided reading writes nothing for the field takes no part;
   - a label with none whose readers each write the same one literal, on it;
   - any other label (readers that differ, or one that writes nothing) only
     through the field's approved sources: exactly one of its literals is
     confirmed by an answer about it (below), and every other has a captured
     no_match answer about it and no success or ambiguous one. An error, a
     timeout or a literal never asked about is neither. A field with no
     approved source never settles such a label.
   The field settles when every such label settles and all on the same
   literal, which is then the answer's literal (and, when a source settled a
   label, the answer cites a success answer confirming it); or, for labels
   that settle on different literals, when a source confirms each of them as
   the answer's authority_id (G32: the same place ID or GBIF usage) and the
   answer cites the one for its literal. Anything else goes to review.
   A source answer is about a literal when GBIF was asked the whole name it
   writes (checks.taxon_query_grounded), or a place source was asked the
   literal as its whole query or as the query's first comma-separated part,
   the name a place source searches. An answer about a literal confirms it
   as GBIF's decided candidate (its evidence's locator) in a success answer;
   for a place value field (point 4), as the one candidate at the field's
   level of a success or ambiguous answer, when that candidate has the
   literal's name; for precise location, as a success answer's candidate of
   that name. Place names, queries and literals compare by the place tool's
   comparison key (place_name: application.georef_locality.comparison_key,
   casefolded, accents and marks dropped, anything but letters and digits a
   single space, "Mt." read as "mount", unit words such as "Prov." dropped):
   "Yepocapa," and "chimaltenango," were asked about by the queries
   "Yepocapa" and "Chimaltenango". A near spelling is never the same name.
4. A place (country, province or state, county, city): a cited success or
   ambiguous answer of a place source has exactly one candidate at the
   field's level (PLACE_LEVELS: a nation, a first or a second level
   subdivision, an inhabited place, by the source's kinds; every GEOLocate
   candidate), and that candidate is the value (the literal when there is no
   value), exactly, with the answer's authority_id. No candidate or several
   at the level: review. A gazetteer's answer is often ambiguous only
   because the name also matches places at other levels (TGN's answer for
   "Philippines" holds the nation, a village and a sea); the level settles
   it. And that answer was asked about the label's own text (point 3's
   "about", P3); or else, when the literal is a place notation of the
   table in field_research.notations for this field (by comparison key),
   about the expansion the table gives it ("Philippine Islands" for "P.I.",
   P4), for which the step cites one rule row naming the entry; or else
   about the candidate's own name when that name is one letter from the
   literal (application.georef_locality.one_letter_apart, G34's bound as
   the place tool reads it: both full names, comparison keys one insertion,
   deletion or substitution apart), for which the step records a
   near_spelling warning finding, which never routes the record
   (place_basis). A lookup of any other name settles nothing ("Escuintla"
   for "Chimaltenago", "Philippines" for "P.I.").

Point 3 follows research_harness/evidence.py's G20 and G32 rules (725-751:
one confirmed reader beside the other's captured no-match; labels that
differ each settled by a source). It is stricter than field_resolution.py
(178-215), which clears readers that differ when every success names one
value: here two confirmed readers of one label go to review.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from specimen_digitization.application.domain import LookupStatus
from specimen_digitization.application.georef_locality import comparison_key, one_letter_apart

from .checks import collapse, taxon_query_grounded
from .contracts import PLACE_SOURCES, FieldTask, Reading, SourceAnswer, SourceCandidate
from .notations import expansion

DECIDED = "decided_transcript"
# Place fields whose value a place source settles; precise_location is
# verbatim text, checked against places and never replaced (PRD 515).
PLACE_VALUE_FIELDS = frozenset({"country", "province_state", "county", "city"})
SOURCE_IDS = frozenset({"gbif", *PLACE_SOURCES})
# A place field's level, as each gazetteer names its candidates' kinds
# (field_research.sources._place): Getty TGN's place types and Wikidata's
# instance-of labels, comma separated; NGA's feature class and designation
# ("A.ADM1"). A TGN type matches whole; a Wikidata label matches whole or
# followed by " of " ("province of the Philippines"); an NGA code matches by
# its start. GEOLocate is asked for the field's own level (Country, State,
# County or Locality) and returns only matches of that place, so all its
# candidates are at the level.
PLACE_LEVELS = {
    "tgn": {
        "country": ("nations",),
        "province_state": ("first level subdivisions (political entities)",),
        "county": ("second level subdivisions (political entities)", "counties"),
        "city": ("inhabited places", "cities", "towns", "villages"),
    },
    "wikidata": {
        "country": ("country", "sovereign state"),
        "province_state": ("province", "former province", "department", "state",
            "first-level administrative country subdivision"),
        "county": ("county", "second-level administrative country subdivision"),
        "city": ("city", "town", "village", "human settlement", "municipality"),
    },
    "nga": {
        "country": ("A.PCL",),
        "province_state": ("A.ADM1",),
        "county": ("A.ADM2",),
        "city": ("P.",),
    },
}
# The answers a place value may settle on (with one candidate at its level).
PLACE_ANSWERED = frozenset({LookupStatus.SUCCESS, LookupStatus.AMBIGUOUS})

# The field's reason when a resolved answer cannot settle it (plain app text).
DIFFER = "The readings differ, and no approved source confirms one of them."
LABELS_DIFFER = "The labels differ, and no approved source confirms them as one value."
NOT_DECIDED = "The reading chosen for this label does not write this value."
NOT_CANDIDATE = "This value is not the text found for this field in the readings."
NO_PLACE = "No approved place source confirms this value."


@dataclass(frozen=True)
class Refusal:
    """Why a resolved answer cannot settle its field: the field's plain reason,
    and what the expert is told when it can still correct its answer."""

    reason: str
    retry: str
    # The readings disagree: the field is ambiguous, not merely unresolved.
    differ: bool = False


def reader_literals(task: FieldTask, readings: Sequence[Reading]) -> dict[str, set[str]]:
    """Each reading's literals for the field, collapsed: the organiser's
    candidates, and the per-reader verbatims it left (a reading named by its
    observation, a raw reading first)."""
    by_name = {r.name: r for r in readings}
    by_observation: dict[str, str] = {}
    for reading in readings:
        if reading.input_source != DECIDED or reading.observation_id not in by_observation:
            by_observation[reading.observation_id] = reading.name
    found: dict[str, set[str]] = {}
    for candidate in task.candidates:
        if candidate.reading in by_name and candidate.literal.strip():
            found.setdefault(candidate.reading, set()).add(collapse(candidate.literal))
    for observation, text in task.current.verbatim_by_observation.items():
        name = by_observation.get(observation)
        if name is not None and text and text.strip():
            found.setdefault(name, set()).add(collapse(text))
    return found


def candidates_by_reading(task: FieldTask, readings: Sequence[Reading]) -> dict[str, dict[str, str]]:
    """Each reading's candidate literals for the field: collapsed, to the
    literal exactly as its candidate gives it."""
    names = {r.name for r in readings}
    found: dict[str, dict[str, str]] = {}
    for candidate in task.candidates:
        if candidate.reading in names and candidate.literal.strip():
            found.setdefault(candidate.reading, {}).setdefault(collapse(candidate.literal), candidate.literal)
    return found


def _deciding(reading: Reading, readings: Sequence[Reading]) -> Reading:
    """The reading whose candidates decide a literal on this reading's label:
    the label's decided transcript when it has one (G19), else the reading."""
    return next((r for r in readings if r.region_id == reading.region_id and r.input_source == DECIDED),
        reading)


def candidate_literal(task: FieldTask, readings: Sequence[Reading], literal: str,
        named: Sequence[Reading]) -> str | None:
    """The whole candidate literal the answer's literal is, exactly as the
    candidate gives it, or None when it is not a candidate literal of every
    named reading (of the decided reading, on a label with a decided
    transcript). Compared after NFC and whitespace collapse only."""
    allowed = candidates_by_reading(task, readings)
    want = collapse(literal)
    whole = None
    for reading in named:
        found = allowed.get(_deciding(reading, readings).name, {})
        if want not in found:
            return None
        whole = whole or found[want]
    return whole


def literal_refusal(task: FieldTask, readings: Sequence[Reading], *, literal: str,
        named: Sequence[Reading]) -> Refusal | None:
    """Why the answer's literal may not settle the field, or None: a label's
    decided transcript must write it (G19), and it must be a whole candidate
    literal of each reading it names (the decided reading's, on a label with
    one), never a shorter or longer piece of a reading (B2)."""
    for reading in named:
        chosen = _deciding(reading, readings)
        if chosen.input_source == DECIDED and literal not in chosen.text:
            return Refusal(NOT_DECIDED, (
                f"Reading {chosen.name} is the transcript decided for this label: its text decides "
                f"this field (G19), and it does not contain {literal!r}. Copy the literal from "
                f"{chosen.name}, or answer several_possibilities or sources_cannot_resolve."))
    if candidate_literal(task, readings, literal, named) is not None:
        return None
    allowed = candidates_by_reading(task, readings)
    offered = [f"{source.name}: {text!r}" for source in dict.fromkeys(_deciding(r, readings) for r in named)
        for text in allowed.get(source.name, {}).values()]
    shown = "; ".join(offered) or "none"
    return Refusal(NOT_CANDIDATE, (
        "A resolved literal is one of the organiser's candidate literals for every reading you "
        "name (on a label with a decided transcript, that reading's), whole and exactly as the "
        f"candidate gives it. Candidates for the readings you named: {shown}. Never shorten or "
        "extend a candidate. Copy one and name only readings that have it, or answer "
        "several_possibilities or sources_cannot_resolve."))


def place_name(text: str) -> str:
    """A place name as a place source's query or candidate is compared with a
    label's text: the native comparison key of the place tool
    (application.georef_locality.comparison_key: casefolded, marks and
    accents dropped, anything but letters and digits a single space, "Mt." read
    as "mount", unit words such as "Prov." or "Dept." dropped). The literal
    itself stays exactly as written."""
    return comparison_key(text)


def about(answer: SourceAnswer, literal: str) -> bool:
    """Whether a source was asked about this (collapsed) literal: GBIF about
    the whole name it writes (checks.taxon_query_grounded), a place source
    about the literal itself, as its whole query or as the query's first
    comma-separated part, the name a place source searches, compared as place
    names (place_name). An empty name is never asked about."""
    if answer.source_id == "gbif":
        return taxon_query_grounded(answer.query, literal)
    asked = {place_name(answer.query), place_name(answer.query.split(",", 1)[0])}
    return bool(place_name(literal)) and place_name(literal) in asked


def _kind_matches(source_id: str, kind: str, level: str) -> bool:
    kind, level = kind.strip().casefold(), level.casefold()
    if source_id == "nga":
        return kind.startswith(level)
    if source_id == "wikidata":
        return kind == level or kind.startswith(level + " of ")
    return kind == level


def at_level(key: str, answer: SourceAnswer) -> list[SourceCandidate]:
    """The answer's candidates at the place field `key`'s level (PLACE_LEVELS):
    every GEOLocate candidate, and a gazetteer's whose kinds name the level."""
    if answer.source_id == "geolocate":
        return list(answer.candidates)
    levels = PLACE_LEVELS.get(answer.source_id, {}).get(key, ())
    return [candidate for candidate in answer.candidates
        if any(_kind_matches(answer.source_id, kind, level)
            for kind in (candidate.kind or "").split(",") for level in levels)]


def placed(key: str, answer: SourceAnswer) -> SourceCandidate | None:
    """The one candidate a place source's answer settles the place field
    `key` on: a success or ambiguous answer with exactly one candidate at the
    field's level. None when it has none or several there (P1 of #284)."""
    if answer.source_id not in PLACE_SOURCES or answer.status not in PLACE_ANSWERED:
        return None
    level = at_level(key, answer)
    return level[0] if len(level) == 1 else None


def identities(answers: Iterable[SourceAnswer], literal: str, key: str) -> set[str]:
    """What captured answers about this literal confirm it as, for the field
    `key`: the authority_id of GBIF's decided candidate (the one its
    evidence's locator names) in a success answer; for a place value field,
    of the one candidate at its level (placed) when it has the literal's name;
    for another field a place source answers, of a success answer's candidate
    of that name. Names compare as place names. Empty when nothing confirms it."""
    found: set[str] = set()
    for answer in answers:
        if answer.evidence is None or not about(answer, literal):
            continue
        if answer.source_id == "gbif" or key not in PLACE_VALUE_FIELDS:
            if answer.status != LookupStatus.SUCCESS:
                continue
            found.update(candidate.authority_id for candidate in answer.candidates if candidate.authority_id
                and (candidate.authority_id == answer.evidence.locator if answer.source_id == "gbif"
                    else place_name(candidate.name) == place_name(literal)))
        elif (one := placed(key, answer)) is not None and one.authority_id and (
                place_name(one.name) == place_name(literal)):
            found.add(one.authority_id)
    return found


def ruled_out(answers: Iterable[SourceAnswer], literal: str) -> bool:
    """Whether the sources found nothing for this literal: a captured no_match
    answer about it, and no success or ambiguous answer about it. An error, a
    timeout or a literal never asked about is not ruled out."""
    asked = [a for a in answers if a.evidence is not None and about(a, literal)]
    return (any(a.status == LookupStatus.NO_MATCH for a in asked)
        and not any(a.status in (LookupStatus.SUCCESS, LookupStatus.AMBIGUOUS) for a in asked))


@dataclass(frozen=True)
class Label:
    """One label that writes the field: its readings' literals, and the
    literal it settles to (None when it does not settle)."""

    literals: frozenset[str]
    settled: str | None
    # A source settled readers that differ (G20), rather than a decided
    # transcript or readers that agree.
    by_source: bool = False


def labels(task: FieldTask, readings: Sequence[Reading], answers: Sequence[SourceAnswer]) -> dict[str, Label]:
    """Each label that writes the field, by region, settled on its own
    (G19, G20, G27, G32):
    - a label with a decided transcript, on the one candidate literal its
      decided reading has; its other readers are evidence only, and a label
      whose decided reading writes nothing for the field takes no part;
    - a label whose readers each write the same one literal, on that literal;
    - a label whose readers differ (or where one writes nothing), only through
      the field's approved sources (`answers`): exactly one of its literals
      is confirmed (identities), and every other is ruled out (ruled_out)."""
    literals = reader_literals(task, readings)
    allowed = candidates_by_reading(task, readings)
    sourced = bool(frozenset(task.tools) & SOURCE_IDS)
    regions: dict[str, list[Reading]] = {}
    for reading in readings:
        regions.setdefault(reading.region_id, []).append(reading)
    found: dict[str, Label] = {}
    for region, group in regions.items():
        decided = next((r for r in group if r.input_source == DECIDED), None)
        if decided is not None:
            texts = frozenset(literals.get(decided.name, ()))
            if texts:
                one = len(texts) == 1 and texts <= set(allowed.get(decided.name, {}))
                found[region] = Label(texts, next(iter(texts)) if one else None)
            continue
        each = [frozenset(literals.get(r.name, ())) for r in group]
        texts = frozenset().union(*each)
        if not texts:
            continue
        if len(texts) == 1 and all(len(own) == 1 for own in each):
            found[region] = Label(texts, next(iter(texts)))
            continue
        confirmed = {text for text in texts if identities(answers, text, task.key)} if sourced else set()
        if len(confirmed) == 1 and all(ruled_out(answers, text) for text in texts - confirmed):
            found[region] = Label(texts, next(iter(confirmed)), by_source=True)
        else:
            found[region] = Label(texts, None)
    return found


def _disagreement(task: FieldTask, readings: Sequence[Reading], *, literal: str,
        authority_id: str | None, cited: Sequence[SourceAnswer],
        received: Sequence[SourceAnswer]) -> Refusal | None:
    """Why readers or labels that disagree do not settle the field on this
    answer, or None (B1 of #284's reviews; G19, G20, G27, G32)."""
    sources = frozenset(task.tools) & SOURCE_IDS
    answers = [a for a in received if a.source_id in sources]
    found = labels(task, readings, answers)
    settled = {label.settled for label in found.values()}
    if not found or (settled != {None} and len(settled) == 1
            and not any(label.by_source for label in found.values())):
        return None  # Every label settles on its own text, and they agree.
    every = sorted(frozenset().union(*(label.literals for label in found.values())))
    shown = "; ".join(repr(text) for text in every)
    if None in settled:
        return Refusal(DIFFER, (
            f"The readers disagree on this field ({shown}). A label with no decided transcript "
            "whose readers differ settles only when your approved sources were asked about each "
            "reader's text: exactly one confirmed by a success answer, every other found by none "
            "(a no_match answer, and no success or ambiguous one)"
            + ("." if sources else "; this field has no such source.")
            + " Ask about each reader's text, or answer several_possibilities with each reader's "
            "text, or sources_cannot_resolve."), differ=True)
    cited = [a for a in cited if a.source_id in sources]
    want = collapse(literal)
    if len(settled) == 1:
        [one] = settled
        if want != one:
            return Refusal(DIFFER, (
                f"The labels settle on the reader's text {one!r}: copy the literal from a reading "
                "that writes it, or answer several_possibilities."), differ=True)
        if not identities(cited, one, task.key):
            return Refusal(DIFFER, (
                f"Cite the evidence_id of the source answer that confirms {one!r}."), differ=True)
        return None
    # G32: labels that settle on different text agree only through a source
    # that confirms each label's text as the same place or name.
    common = None
    for text in settled:
        found = identities(answers, text, task.key)
        common = found if common is None else common & found
    if want in settled and authority_id in (common or set()) and authority_id in identities(cited, want, task.key):
        return None
    return Refusal(LABELS_DIFFER, (
        f"The labels write different text for this field ({shown}). They settle only when an "
        "approved source confirms each label's text as the same place or name: ask about each, "
        "give that authority_id and cite the answer for your literal, or answer "
        "several_possibilities."), differ=True)


ASKED, NOTATION, NEAR_SPELLING = "asked", "notation", "near_spelling"


def place_basis(task: FieldTask, literal: str, settled: str, authority_id: str | None,
        cited: Iterable[SourceAnswer]) -> str | None:
    """How a cited answer of the field's place sources settles the place value
    (P1 and P3 of #284), or None when none does. The answer has exactly one
    candidate at the field's level (placed), that candidate is the settled
    value (its name exactly, after NFC and whitespace collapse) with the
    answer's authority_id, and the answer was asked
    - about the label's own text (about): ASKED; or else
    - about the expansion the notation table gives the literal for this field
      (notations.expansion: "Philippine Islands" for "P.I."): NOTATION, for
      which the step cites a rule row naming the entry; or else
    - about that candidate's own name, when the name is one letter from the
      label's text (application.georef_locality.one_letter_apart, G34's
      bound as the place tool reads it: both full names, comparison keys one
      single-letter edit apart): NEAR_SPELLING, which the step records as a
      warning finding that never routes the record."""
    sources = frozenset(task.tools) & frozenset(PLACE_SOURCES)
    entry = expansion(literal, task.key)
    found = set()
    for answer in cited:
        one = placed(task.key, answer) if answer.source_id in sources else None
        if one is None or collapse(one.name) != collapse(settled) or one.authority_id != authority_id:
            continue
        if about(answer, collapse(literal)):
            found.add(ASKED)
        elif entry is not None and about(answer, collapse(entry.expansion)):
            found.add(NOTATION)
        elif about(answer, collapse(one.name)) and one_letter_apart(literal, one.name):
            found.add(NEAR_SPELLING)
    return next((basis for basis in (ASKED, NOTATION, NEAR_SPELLING) if basis in found), None)


def refusal(task: FieldTask, readings: Sequence[Reading], *, literal: str,
        named: Sequence[Reading], value: str | None, authority_id: str | None,
        cited: Sequence[SourceAnswer], received: Sequence[SourceAnswer]) -> Refusal | None:
    """Why a resolved answer may not settle its field, or None.

    `named` are the readings the answer names (each already writes the
    literal), `cited` the source answers it cites and `received` every source
    answer its field received."""
    refused = literal_refusal(task, readings, literal=literal, named=named)
    if refused is not None:
        return refused
    refused = _disagreement(task, readings, literal=literal, authority_id=authority_id, cited=cited,
        received=received)
    if refused is not None:
        return refused
    if task.key in PLACE_VALUE_FIELDS:
        settled_value = value if value is not None else literal
        if place_basis(task, literal, settled_value, authority_id, cited) is None:
            return Refusal(NO_PLACE, (
                "A place field settles only on a place source's success or ambiguous answer that "
                "was asked the label's own text (the literal, or the query's first comma-separated "
                "part; case, accents, punctuation and notations such as Prov. aside), or the "
                "candidate's own name when it is one letter from the literal, with exactly one "
                "candidate at this field's level (by its kind: a nation for a country, a first "
                "level subdivision for a province or state, a second level one for a county, an "
                "inhabited place for a city), and that candidate is the value: cite its "
                "evidence_id, give that candidate's name (as value, or as the literal when they "
                "are the same) and its authority_id. Otherwise answer several_possibilities or "
                "sources_cannot_resolve."))
    return None
