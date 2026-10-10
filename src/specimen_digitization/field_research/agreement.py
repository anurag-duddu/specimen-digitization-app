"""When a resolved answer may settle its field (B1 and B2 of #284's reviews).

`refusal` checks every resolved answer, in the expert's answer check
(experts.py, so the model is sent back) and again in the step before the
answer becomes a value (step._refusal). It enforces points 1 to 4, in this
order; the step alone adds point 5 (parents_refusal), which needs the other
fields' outcomes:

1. The decided transcript (G19): for each reading the answer names whose
   label has a decided transcript, the decided reading's text contains the
   literal.
2. A whole candidate (B2): the literal is one of the field's candidate
   literals (FieldTask.candidates: the organiser's, and each keyed line the
   parser read) of each reading the answer names, or, on a label with a
   decided transcript, of the decided reading. Literals are compared after
   NFC and whitespace collapse only (checks.collapse): "E. slope" and
   "E.slope" differ. A field with no such candidate is never resolved. For a
   taxon, the candidate's quote, the reading's text it was taken from, must
   write no longer name around the literal (checks.longer_name): a candidate
   "Danaus plexippus" quoting "Danaus plexippus megalippe" (N3 of the third
   review), or "sp. 1" quoting "Epipsocus sp. 1" (B1 of #289's review), is a
   piece of the name the label writes, and never settles the taxon. Nor does
   a literal whose genus the candidate's quote, or the text of a reading the
   answer names (or of its label's decided reading), marks as doubtful with
   a qualifier or a "?" right before it or on it (checks.genus_in_doubt:
   "Epipsocus" quoting "cfr. Epipsocus" or "Epipsocus?"; 1c of #289's fifth
   review). The step's unmatched taxon (owner decision B) meets these rules
   too.
3. Readers and labels that disagree (B1; G19, G20, G27, G32). From the
   field's candidates and the organiser's per-reader verbatims, whatever
   state the organiser gave the field, each label that writes the field
   settles on its own (`labels`):
   - a label with a decided transcript, on its decided reading's one
     candidate literal; its other readers are evidence only, and a label
     whose decided reading writes nothing for the field takes no part;
   - a label with none whose readers each write the same text, letter case
     and spacing aside (agreement_key: "shrubs" and "Shrubs", "sp. 30" and
     "Sp.30", "Mt." and "MT."), on its first reader's spelling, which the
     answer's literal then is; a punctuation mark or a letter more or less
     is a different text;
   - any other label (readers that differ, or one that writes nothing) only
     through the field's approved sources: exactly one of its literals is
     confirmed by an answer about it (below), and every other has a captured
     no_match answer about it and no success or ambiguous one. An error, a
     timeout or a literal never asked about is neither. A field with no
     approved source never settles such a label. For a place value field
     (point 4) such a label also settles when every one of its literals is
     confirmed and one authority_id confirms them all: its readers name the
     same place ("Yepocapa," and "Yepocapa", N4 of the third review). That
     rests on the source's evidence, and each literal must match the
     candidate's name by the place comparison key (case, accents,
     punctuation, unit words: "Chimaltenango Dept." and "Chimaltenango"
     too); the label settles on each of its literals; readers confirmed as
     different places, or not all confirmed, still go to review.
   The field settles when every such label settles and all on the same
   literal, which is then the answer's literal (and, when a source settled a
   label, the answer cites a success answer confirming it); or, for labels
   (or a place's readers) that settle on different literals, when a source
   confirms each of them as the answer's authority_id (G32: the same place ID
   or GBIF usage), the answer's literal is one of them and the answer cites
   the answer confirming it. Anything else goes to review.
   A source answer is about a literal when GBIF was asked the whole name it
   writes (checks.taxon_query_grounded), or a place source was asked the
   literal as the query's first comma-separated part, the only name a
   gazetteer searches and the place GEOLocate looks for ("San Pedro,
   Sacatepequez" asks about "San Pedro"). An answer about a literal confirms it
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
   subdivision, an inhabited place, by the source's kinds; for a city, every
   GEOLocate candidate, and for any other field none, as GEOLocate's candidate
   there is a part of the query itself), and that
   candidate is the value (the literal when there is no
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
   literal (application.georef_locality.one_letter_apart: both full names,
   comparison keys one insertion, deletion or substitution apart), the
   one-letter half of G34, which the step settles only on the rest of G34
   (point 5) and then records a near_spelling warning finding, which never
   routes the record (place_settling). A lookup of any other name settles
   nothing ("Escuintla" for "Chimaltenago", "Philippines" for "P.I.").
5. The place fits the label's other place fields (B3 and N1 of the third
   review; parents_refusal). The step checks it once every field's outcome
   is in, the country first and then the province, county and city
   (step._misfit), as the fields run at once and the country must be known.
   For each reading the answer names (its label's decided reading, on a
   label with one), the settling candidate's parents (SourceCandidate.parents,
   as its source gives them) are compared with that reading's other place
   fields. Another field is written by the reading when the reading has
   texts for it (candidate literals or verbatims), and settled for it when
   its value is supported, the step has done with it in this attempt (or
   settled it earlier) and the reading writes its literal (compared as place
   names). A parent is that field when it is the field's settled record (its
   authority_id), or when its name has the comparison key of one of the
   field's texts, of the notation table's expansion of one, or of the value
   the field settled on:
   - below the country, the candidate has parents, one of them is the
     country settled for the reading, and for a county or a city one is the
     province settled for it too, when one is. No country settled for the
     reading, no parents, or none that is that country or province: the
     field goes to review with the reason. A country needs no parent;
   - a near spelling, of any place field, settles only when every place
     field the reading writes above it (PLACE_ORDER: a province's country; a
     county's province and country; a city's county, province and country),
     all of them and at least one, is one of the candidate's parents (G34's
     whole condition). Parents are only larger places, so a county or a city
     the reading writes below a near-spelled province is never checked as
     its parent (105526330's province beside its city Yepocapa). A country
     has no place field above it, so a near-spelled country never settles.

Point 3 follows research_harness/evidence.py's G20 and G32 rules (725-751:
one confirmed reader beside the other's captured no-match; labels that
differ each settled by a source). It is stricter than field_resolution.py
(178-215), which clears readers that differ when every success names one
value: here two confirmed readers of one label go to review, unless they are
a place's readers whose texts one candidate at the field's level confirms.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from specimen_digitization.application.domain import LookupStatus
from specimen_digitization.application.georef_locality import comparison_key, one_letter_apart

from .checks import collapse, genus_in_doubt, longer_name, taxon_query_grounded
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
# its start. GEOLocate's candidates are at a city's level only (at_level).
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
PART_OF_NAME = "The label writes a longer scientific name than this value."
DOUBTFUL_GENUS = "The label marks this name's genus as doubtful."
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
    one), never a shorter or longer piece of a reading (B2); for a taxon, a
    candidate whose quote writes a longer name from it on is such a piece too
    (_part_of_name), and a literal whose genus the label marks as doubtful
    never settles (_genus_in_doubt)."""
    for reading in named:
        chosen = _deciding(reading, readings)
        if chosen.input_source == DECIDED and literal not in chosen.text:
            return Refusal(NOT_DECIDED, (
                f"Reading {chosen.name} is the transcript decided for this label: its text decides "
                f"this field (G19), and it does not contain {literal!r}. Copy the literal from "
                f"{chosen.name}, or answer several_possibilities or sources_cannot_resolve."))
    if candidate_literal(task, readings, literal, named) is not None:
        return _part_of_name(task, readings, literal, named) or _genus_in_doubt(task, readings, literal, named)
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


def _part_of_name(task: FieldTask, readings: Sequence[Reading], literal: str,
        named: Sequence[Reading]) -> Refusal | None:
    """For a taxon, why the candidate the literal is cannot settle it: its
    quote, the reading's text it was taken from, writes a longer name around
    the literal (checks.longer_name; N3 of #284's third review, B1 of #289's
    review), so the literal is a piece of the name the label writes. Every
    candidate of that literal of the readings named (the decided reading's,
    on a label with one) is checked. None otherwise, and for any other
    field."""
    if task.key != "taxon":
        return None
    want = collapse(literal)
    deciding = {_deciding(reading, readings).name for reading in named}
    for candidate in task.candidates:
        if candidate.reading not in deciding or collapse(candidate.literal) != want:
            continue
        longer = longer_name(candidate.quote, candidate.literal)
        if longer is not None:
            return Refusal(PART_OF_NAME, (
                f"The candidate {candidate.literal!r} of reading {candidate.reading} quotes "
                f"{candidate.quote!r}, which writes the longer name {longer!r}. A taxon settles only "
                "on the whole name its reading writes, so this candidate cannot settle it: answer "
                "several_possibilities or sources_cannot_resolve."))
    return None


def _genus_in_doubt(task: FieldTask, readings: Sequence[Reading], literal: str,
        named: Sequence[Reading]) -> Refusal | None:
    """For a taxon, why the literal cannot settle it: the label marks its
    genus as doubtful (checks.genus_in_doubt: a qualifier or a "?" right
    before the literal's first word or on it) in the quote of a candidate of
    that literal, or in the text of a reading the answer names or of its
    label's decided reading, wherever that text writes the literal (1c of
    #289's fifth review). The taxon brief has the expert look such a genus up
    alone and answer sources_cannot_resolve; GBIF may still decide it, and
    this refuses an answer that resolves it. None otherwise, and for any
    other field."""
    if task.key != "taxon":
        return None
    want = collapse(literal)
    names = {reading.name for reading in named} | {_deciding(reading, readings).name for reading in named}
    texts = [(candidate.quote, candidate.literal) for candidate in task.candidates
        if candidate.reading in names and collapse(candidate.literal) == want]
    texts += [(reading.text, literal) for reading in readings if reading.name in names]
    for text, written in texts:
        if genus_in_doubt(text, written):
            return Refusal(DOUBTFUL_GENUS, (
                f"{text!r} writes a qualifier or a '?' right before or on the genus of {written!r}, so the "
                "label marks that genus as doubtful. A doubtful genus never settles the taxon, whatever "
                "GBIF says: answer sources_cannot_resolve."))
    return None


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
    the whole name it writes (checks.taxon_query_grounded); a place source
    about the literal as the query's first comma-separated part, compared as
    place names (place_name). That part is the only name a gazetteer searches
    (sources.place_name) and the place GEOLocate looks for; the parts after it
    are larger units, so "San Pedro, Sacatepequez" asks about "San Pedro",
    never "San Pedro Sacatepequez" (N2 of #284's third review). An empty name
    is never asked about."""
    if answer.source_id == "gbif":
        return taxon_query_grounded(answer.query, literal)
    asked = place_name(answer.query.split(",", 1)[0])
    return bool(asked) and place_name(literal) == asked


def _kind_matches(source_id: str, kind: str, level: str) -> bool:
    kind, level = kind.strip().casefold(), level.casefold()
    if source_id == "nga":
        return kind.startswith(level)
    if source_id == "wikidata":
        return kind == level or kind.startswith(level + " of ")
    return kind == level


def at_level(key: str, answer: SourceAnswer) -> list[SourceCandidate]:
    """The answer's candidates at the place field `key`'s level (PLACE_LEVELS):
    a gazetteer's whose kinds name the level, and, for a city only, every
    GEOLocate candidate. For a country, a province or state or a county,
    GEOLocate's candidate is a part of the query itself (its country, its
    state or county part, or else its place part; sources.interpretation),
    which it only echoes: no confirmation of it (N2 of #284's third
    review)."""
    if answer.source_id == "geolocate":
        return list(answer.candidates) if key == "city" else []
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


def agreement_key(text: str) -> str:
    """A reader's text as readers' texts are compared for agreement: NFC,
    casefolded, with every space and line break removed. "shrubs" and
    "Shrubs", "sp. 30" and "Sp.30", "Mt." and "MT." are one text; a
    punctuation mark or a letter more or less is another ("Mun." and
    "Mum.", "6-Sept.-1946" and "6-Sept.-1948")."""
    return "".join(unicodedata.normalize("NFC", text).casefold().split())


def _spelling(task: FieldTask, name: str, texts: Iterable[str]) -> str:
    """The reader's own spelling a label settles on when its readers agree:
    the reader's candidate literal (the organiser's first, when the reader
    has more than one spelling), else its first text in sorted order."""
    texts = set(texts)
    return next((collapse(candidate.literal) for candidate in task.candidates
        if candidate.reading == name and collapse(candidate.literal) in texts), min(texts))


@dataclass(frozen=True)
class Label:
    """One label that writes the field: its readings' literals, and the
    literals it settles to: one, or, for readers a source confirms as one
    place, each of theirs (N4); none when it does not settle."""

    literals: frozenset[str]
    settled: frozenset[str] = frozenset()
    # A source settled readers that differ (G20, N4), rather than a decided
    # transcript or readers that agree.
    by_source: bool = False


def labels(task: FieldTask, readings: Sequence[Reading], answers: Sequence[SourceAnswer]) -> dict[str, Label]:
    """Each label that writes the field, by region, settled on its own
    (G19, G20, G27, G32):
    - a label with a decided transcript, on the one candidate literal its
      decided reading has; its other readers are evidence only, and a label
      whose decided reading writes nothing for the field takes no part;
    - a label whose readers each write the same text, letter case and
      spacing aside (agreement_key: "shrubs" and "Shrubs", "sp. 30" and
      "Sp.30"), on the first reader's spelling (_spelling);
    - a label whose readers differ (or where one writes nothing), only through
      the field's approved sources (`answers`): exactly one of its literals
      is confirmed (identities), and every other is ruled out (ruled_out);
      or, for a place value field, every one of its literals is confirmed and
      one authority_id confirms them all, so its readers name the same place
      ("Yepocapa," and "Yepocapa"; N4 of #284's third review). That settles
      on the source's evidence, each literal matching the candidate's name
      by the place comparison key (case, accents, punctuation, unit words),
      and on each of the literals: the answer gives one of them, with that
      authority_id."""
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
                found[region] = Label(texts, texts if one else frozenset())
            continue
        each = [frozenset(literals.get(r.name, ())) for r in group]
        texts = frozenset().union(*each)
        if not texts:
            continue
        if all(each) and len({agreement_key(text) for text in texts}) == 1:
            # Every reader writes it, at most letter case or spacing apart
            # ("shrubs" and "Shrubs", "sp. 30" and "Sp.30"): they agree, on
            # the first reader's spelling.
            found[region] = Label(texts, frozenset({_spelling(task, group[0].name, each[0])}))
            continue
        confirmed = {text: identities(answers, text, task.key) for text in texts} if sourced else {}
        ones = frozenset(text for text, ids in confirmed.items() if ids)
        if len(ones) == 1 and all(ruled_out(answers, text) for text in texts - ones):
            found[region] = Label(texts, ones, by_source=True)
        elif (task.key in PLACE_VALUE_FIELDS and ones == texts
                and frozenset.intersection(*(frozenset(confirmed[text]) for text in texts))):
            found[region] = Label(texts, texts, by_source=True)
        else:
            found[region] = Label(texts)
    return found


def _disagreement(task: FieldTask, readings: Sequence[Reading], *, literal: str,
        authority_id: str | None, cited: Sequence[SourceAnswer],
        received: Sequence[SourceAnswer]) -> Refusal | None:
    """Why readers or labels that disagree do not settle the field on this
    answer, or None (B1 of #284's reviews; G19, G20, G27, G32, N4)."""
    sources = frozenset(task.tools) & SOURCE_IDS
    answers = [a for a in received if a.source_id in sources]
    found = labels(task, readings, answers)
    settled = frozenset().union(*(label.settled for label in found.values())) if found else frozenset()
    every = sorted(frozenset().union(*(label.literals for label in found.values()))) if found else []
    shown = "; ".join(repr(text) for text in every)
    if not found:
        return None
    if (all(label.settled for label in found.values()) and len(settled) == 1
            and not any(label.by_source for label in found.values())):
        # Every label settles on its own text, and they agree: on that text,
        # as the label's decided transcript or its first reader spells it.
        [one] = settled
        if collapse(literal) == one:
            return None
        return Refusal(DIFFER, (
            f"The readers write {shown}, which agree on {one!r} (a decided transcript's spelling, "
            "or the first reader's when the label has none; letter case and spacing aside, they "
            f"are one text). Copy the literal {one!r} exactly from a reading that writes it, and "
            "name only readings that write it so."), differ=True)
    if not all(label.settled for label in found.values()):
        return Refusal(DIFFER, (
            f"The readers disagree on this field ({shown}). A label with no decided transcript "
            "whose readers differ settles only when your approved sources were asked about each "
            "reader's text: exactly one confirmed by a success answer, every other found by none "
            "(a no_match answer, and no success or ambiguous one)"
            + ("; or, for a place, each reader's text confirmed as the same place (one candidate "
               "at this field's level, with one authority_id)." if task.key in PLACE_VALUE_FIELDS
               else "." if sources else "; this field has no such source.")
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
    # G32 and N4: labels, or readers of one label, that settle on different
    # text agree only through a source that confirms each text as the same
    # place or name.
    common = None
    for text in settled:
        ids = identities(answers, text, task.key)
        common = ids if common is None else common & ids
    if want in settled and authority_id in (common or set()) and authority_id in identities(cited, want, task.key):
        return None
    if len(found) == 1:
        return Refusal(DIFFER, (
            f"The readers write {shown}, which a source confirms as the same place: give one "
            "reader's text as the literal, that place's authority_id, and cite the answer that "
            "confirms your literal."), differ=True)
    return Refusal(LABELS_DIFFER, (
        f"The labels write different text for this field ({shown}). They settle only when an "
        "approved source confirms each label's text as the same place or name: ask about each, "
        "give that authority_id and cite the answer for your literal, or answer "
        "several_possibilities."), differ=True)


ASKED, NOTATION, NEAR_SPELLING = "asked", "notation", "near_spelling"


def place_settling(task: FieldTask, literal: str, settled: str, authority_id: str | None,
        cited: Iterable[SourceAnswer]) -> tuple[str, SourceCandidate] | None:
    """How a cited answer of the field's place sources settles the place value
    (P1 and P3 of #284), and on which candidate; None when none does. The
    answer has exactly one candidate at the field's level (placed), that
    candidate is the settled value (its name exactly, after NFC and whitespace
    collapse) with the answer's authority_id, and the answer was asked
    - about the label's own text (about): ASKED; or else
    - about the expansion the notation table gives the literal for this field
      (notations.expansion: "Philippine Islands" for "P.I."): NOTATION, for
      which the step cites a rule row naming the entry; or else
    - about that candidate's own name, when the name is one letter from the
      label's text (application.georef_locality.one_letter_apart: both full
      names, comparison keys one single-letter edit apart): NEAR_SPELLING. It
      is G34's one-letter half only; the step settles it only when the rest
      of G34 holds too (parents_refusal), and then records a near_spelling
      warning finding that never routes the record."""
    sources = frozenset(task.tools) & frozenset(PLACE_SOURCES)
    entry = expansion(literal, task.key)
    found: dict[str, SourceCandidate] = {}
    for answer in cited:
        one = placed(task.key, answer) if answer.source_id in sources else None
        if one is None or collapse(one.name) != collapse(settled) or one.authority_id != authority_id:
            continue
        if about(answer, collapse(literal)):
            found.setdefault(ASKED, one)
        elif entry is not None and about(answer, collapse(entry.expansion)):
            found.setdefault(NOTATION, one)
        elif about(answer, collapse(one.name)) and one_letter_apart(literal, one.name):
            found.setdefault(NEAR_SPELLING, one)
    return next(((basis, found[basis]) for basis in (ASKED, NOTATION, NEAR_SPELLING) if basis in found), None)


def place_basis(task: FieldTask, literal: str, settled: str, authority_id: str | None,
        cited: Iterable[SourceAnswer]) -> str | None:
    """The basis place_settling finds, or None."""
    found = place_settling(task, literal, settled, authority_id, cited)
    return found[0] if found is not None else None


# Why a place value's candidate does not fit the label's other place fields
# (B3 and N1 of #284's third review; the step's check, parents_refusal).
NO_PARENTS = "The source does not say which country this place is in."
NO_COUNTRY = "No country is settled for the reading that writes this place."
NOT_IN_COUNTRY = "The place found is not in the country the label gives."
NOT_IN_PROVINCE = "The place found is not in the province the label gives."
NEAR_UNFIT = ("The place found is one letter from the label's spelling, and the larger places the label "
    "gives do not confirm it.")
PLACE_ORDER = ("country", "province_state", "county", "city")


@dataclass(frozen=True)
class PlaceField:
    """Another place field as one reading writes it: the texts that reading
    writes for it (its candidate literals and verbatims), with the value it
    settled on when one is settled from that reading's text, and that value's
    authority_id."""

    texts: tuple[str, ...]
    authority_id: str | None = None


def place_keys(key: str, texts: Iterable[str]) -> frozenset[str]:
    """The comparison keys (place_name) a place field's texts name a parent by:
    each text, and the expansion the notation table gives it for the field
    ("Philippine Islands" for the country "P.I."), the alias field research
    reads a notation by."""
    found = set()
    for text in texts:
        found.add(place_name(text))
        entry = expansion(text, key)
        if entry is not None:
            found.add(place_name(entry.expansion))
    return frozenset(found - {""})


def lies_in(candidate: SourceCandidate, key: str, field: PlaceField) -> bool:
    """Whether a parent of the candidate is this place field: the same record
    (the field's authority_id), or a name with one of its comparison keys."""
    names = place_keys(key, field.texts)
    return any((field.authority_id is not None and parent.authority_id == field.authority_id)
        or place_name(parent.name) in names for parent in candidate.parents)


def parents_refusal(key: str, candidate: SourceCandidate, basis: str, *,
        written: Mapping[str, PlaceField], settled: Mapping[str, PlaceField]) -> Refusal | None:
    """Why the candidate a place value settles on does not fit the label's
    other place fields of one reading (B3 and N1 of #284's third review), or
    None. `written` is every other place field that reading writes; `settled`
    those of them settled from that reading's text.
    - Below the country, the candidate has parents (SourceCandidate.parents),
      the country settled for the reading is one of them, and for a county or
      a city, the province settled for the reading too when one is. A
      candidate with no parents, or none of whose parents is that country,
      does not settle; nor does any place when no country is settled for the
      reading. A country needs no parent.
    - A near spelling (NEAR_SPELLING) settles only on G34's whole condition,
      on the larger places: every place field the reading writes above the
      field's own (PLACE_ORDER), all of them and at least one, names a
      parent of the candidate (lies_in). A county or a city below a
      near-spelled province is no parent of it and is not checked; a country
      has nothing above it, so a near-spelled country never settles."""
    if key != "country":
        if not candidate.parents:
            return Refusal(NO_PARENTS, NO_PARENTS)
        country = settled.get("country")
        if country is None:
            return Refusal(NO_COUNTRY, NO_COUNTRY)
        if not lies_in(candidate, "country", country):
            return Refusal(NOT_IN_COUNTRY, NOT_IN_COUNTRY)
        province = settled.get("province_state")
        if key in ("county", "city") and province is not None and not lies_in(
                candidate, "province_state", province):
            return Refusal(NOT_IN_PROVINCE, NOT_IN_PROVINCE)
    if basis == NEAR_SPELLING:
        # Parents are only larger places: a county or a city the reading
        # writes below the field is never one of its parents.
        above = {other: field for other, field in written.items()
            if other in PLACE_ORDER and PLACE_ORDER.index(other) < PLACE_ORDER.index(key)}
        if not above or not all(lies_in(candidate, other, field) for other, field in above.items()):
            return Refusal(NEAR_UNFIT, NEAR_UNFIT)
    return None


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
                "was asked the label's own text: the literal as the query's first comma-separated "
                "part, the name it searches (case, accents, punctuation and notations such as Prov. "
                "aside), or the name the label notations give it, or the candidate's own name when "
                "it is one letter from the literal; with exactly one candidate at this field's "
                "level (by its kind: a "
                "nation for a country, a first level subdivision for a province or state, a second "
                "level one for a county, an inhabited place for a city; GEOLocate's candidate "
                "only for a city, as for the other fields it repeats a part of your query), and "
                "that candidate is the value: cite its "
                "evidence_id, give that candidate's name (as value, or as the literal when they "
                "are the same) and its authority_id. Otherwise answer several_possibilities or "
                "sources_cannot_resolve."))
    return None
