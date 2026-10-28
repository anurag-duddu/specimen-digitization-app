"""When a resolved answer may settle its field (B1 and B2 of #284's reviews).

`refusal` checks every resolved answer, in the expert's answer check
(experts.py, so the model is sent back) and again in the step before the
answer becomes a value (step._refusal). It enforces points 1 to 4, in this
order; the step alone adds point 5 (parents_refusal), which needs the other
fields' outcomes:

1. The first pass's preferred reading (G19's decided transcript) is advice,
   never a constraint (the owner, 2026-10-25: "Harness can decide as it goes
   out and learns more than what the raw transcriptions are capable of"):
   every rule here reads the readings the answer names, whichever reader
   wrote them, and a label's readers settle by point 3. Until then a
   label's decided transcript had to write the literal (NOT_DECIDED), and
   its other readers took no part.
2. A whole candidate (B2): the literal is one of the field's candidate
   literals (FieldTask.candidates: the organiser's, and each keyed line the
   parser read) of each reading the answer names. Literals are compared after
   NFC and whitespace collapse only (checks.collapse): "E. slope" and
   "E.slope" differ. Or else, read from the transcript (literal_basis,
   TRANSCRIPT; coordinator's ruling of 2026-10-09): each of those readings
   writes the literal as a run of whole words within one line
   (verbatim_runs), and it cuts or extends none of that reading's
   candidates (_cut_candidate); a taxon so read must sit in no longer name
   on its reading (_longer_written), a date or an elevation so read is
   never one end of a range its clause writes, joined in any of the
   languages and with any of the dashes field_research.written lists
   (_part_of_range), and a place or the collection code so read never holds
   a date, an elevation or a range of them (_holds_another_kind). An
   elevation, a candidate or so read, settles only a field of the unit its
   reading writes it in, and a number with no unit settles none
   (_unit_refusal). Points 1, 3
   and 4 hold for it as for a candidate, its readers per point 3 as
   agreeing_runs reads them, and on a label the first pass preferred no
   reader of, the clauses holding it agree in every reader
   (holding_clauses). For a
   taxon, the candidate's quote, the reading's text it was taken from, must
   write no longer name around the literal (checks.longer_name): a candidate
   "Danaus plexippus" quoting "Danaus plexippus megalippe" (N3 of the third
   review), or "sp. 1" quoting "Epipsocus sp. 1" (B1 of #289's review), is a
   piece of the name the label writes, and never settles the taxon. Nor does
   a literal whose genus the candidate's quote, or the text of a reading the
   answer names (or of any reader of its label, unless the answer names the
   reader the first pass preferred for that label), marks as doubtful with
   a qualifier or a "?" right before it or on it (checks.genus_in_doubt:
   "Epipsocus" quoting "cfr. Epipsocus" or "Epipsocus?"; 1c of #289's fifth
   review); a qualifier on the line above counts only standing alone on
   that line ("cf." above "Epipsocus sp. 1", never "Danum Valley NR"). The
   step's unmatched taxon (owner decision B) meets these rules too. For a
   place value field (point 4), a candidate or a reader's verbatim that
   names no place (names_no_place: only unit words, f35af3a5's "Prov.") is
   no candidate at all, here and in point 3.
3. Readers and labels that disagree (B1; G19, G20, G27, G32). From the
   field's candidates and the organiser's per-reader verbatims, whatever
   state the organiser gave the field, each label that writes the field
   settles on its own (`labels`): on its own evidence, else on another
   label's, else on the first pass's advice (the owner, 2026-10-25:
   "Evidence is settlement which can be actual match from the lookups raw
   transcription itself being very clear and so on"; asked whether the
   harness should be free to settle a field on any model's raw
   transcription when evidence supports it, even if the LLM pass picked a
   different one: "This is exactly what should have been happening"):
   - a label whose readers each write the same text, letter case and
     spacing aside (agreement_key: "shrubs" and "Shrubs", "sp. 30" and
     "Sp.30", "Mt." and "MT."), on the spelling of the reader the first
     pass preferred, else of its first reader, which the answer's literal
     then is; a punctuation mark or a letter more or less is a different
     text;
   - a label whose readers differ (or where one writes nothing), through
     the field's approved sources, even against the first pass's
     preference: exactly one of its literals is
     confirmed by an answer about it (below), and every other has a captured
     no_match answer about it and no success or ambiguous one. An error, a
     timeout or a literal never asked about is neither. For a place value
     field (point 4), a literal its gazetteers found only as another kind of
     place than the field's is ruled out too (found_only_elsewhere:
     48a71d53's "Mindanao," beside "Davao Prov." on a province, which
     Wikidata and NGA hold only as an island, an island group, a river,
     streets, towns and a third-level unit): every Getty TGN, Wikidata or NGA
     success or ambiguous answer about it lists candidates, those of two or
     more of them hold one of its name, each of those has a kind, and none of
     that name or one letter from it is at the field's level (one capped list
     of candidates, Wikidata's at most seven, is not enough); GEOLocate's answers count
     only for a city, where any candidate keeps the literal. An abbreviated
     literal (abbreviations.abbreviated) never is, as it may stand for a name
     no source was asked. A field with no
     approved source never settles such a label so. For a place value field
     (point 4) such a label also settles when every one of its literals is
     confirmed and one authority_id confirms them all: its readers name the
     same place ("Yepocapa," and "Yepocapa", N4 of the third review). That
     rests on the source's evidence, and each literal must match the
     candidate's name by the place comparison key (case, accents,
     punctuation, unit words: "Chimaltenango Dept." and "Chimaltenango"
     too); the label settles on each of its literals; readers confirmed as
     different places, or not all confirmed, still go to review;
   - else, a label whose readers differ, on the one text of its readers
     that another label of the specimen, two or more of whose readers agree
     on it (MIN_BACKING_READERS), settled on, letter case and spacing aside
     (agreement_key);
   - else, a label whose first pass preferred a reader, on that reader's one
     candidate literal, or, when that reader has several texts for the
     field, only through the field's approved sources as above, on one of
     them; a label whose preferred reader writes nothing for the field takes
     no part, unless the answer names one of its readers;
   - any other label does not settle: a person decides.
   A source's exact confirmation of a reader's text settles against the
   first pass's preference anywhere; a place's near spelling (below) or
   another label settles against it only where the first pass's verdict at
   that difference does not name the preferred reader
   (confirmed_against_image). Where it does, the label does not settle
   either way (Label.preference CONFLICT; FIRST_PASS_CONFLICT: a person
   chooses; the coordinator's decision of 2026-10-25 on #414's review).
   How each label settled, and whether it followed the first pass's
   preference, overrode it or had none, is Label.basis and
   Label.preference (the step records it: step._first_pass_preference).
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
   that name. Where a label's readers differ and the sources confirm none
   of their texts by its own name, a place value field's answer asked the
   candidate's own name confirms a text one letter from it (point 4's near
   spelling: identities' `near`, _by_source), whichever reader writes it;
   every other text must still be ruled out. Place names, queries and
   literals compare by the place tool's comparison key (place_name: application.georef_locality.comparison_key,
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
   "about", P3); or else about an expansion of the literal, a name the
   literal abbreviates by the letter rule (field_research.abbreviations.fit:
   "Philippine Islands" for "P.I.", "New South Wales" for "N.S.W.", "Davao
   Province" for "Davao, Prov."), for which the step cites one rule row
   naming the abbreviation, the expansion and how its letters fit, and which
   settles nothing when another fitting expansion, or the label's own text,
   was answered as another place at the field's level (rival_expansion: the
   field is ambiguous). A query that fits is taken as an expansion even when
   it also has the literal's comparison key, as one that writes out a unit
   word does. Initials ("P.I.", "UK": abbreviations.initialism) settle only
   when the step finds another place of the label inside them
   (step._corroborate); or else about the candidate's
   own name when that name is one letter from the literal
   (application.georef_locality.one_letter_apart: both full names,
   comparison keys one insertion, deletion or substitution apart), the
   one-letter half of G34, which the step settles only on the rest of G34
   (point 5) and then records a near_spelling warning finding, which never
   routes the record (place_settling). A lookup of any other name settles
   nothing ("Escuintla" for "Chimaltenago", "Philippines" for "P.I.").
   A county is the country's second-level unit, whatever the country calls
   it (a municipio of Guatemala is one: the owner's ruling of 2026-10-11),
   and settles on no literal for which an answer about it, of one of its
   place sources, has a candidate of the literal's name at a province's
   level, unless the literal writes a county or municipality unit word
   (first_level_namesake): the label may name that first-level unit.
5. The place fits the label's other place fields (B3 and N1 of the third
   review; parents_refusal). The step checks it once every field's outcome
   is in, the country first and then the province, county and city
   (step._misfit), as the fields run at once and the country must be known.
   For each reading the answer names, the settling candidate's parents
   (SourceCandidate.parents,
   as its source gives them) are compared with that reading's other place
   fields. Another field is written by the reading when the reading has
   texts for it (candidate literals or verbatims), and settled for it when
   its value is supported, the step has done with it in this attempt (or
   settled it earlier) and the reading writes its literal (compared as place
   names). A parent is that field when it is the field's settled record (its
   authority_id), or when its name has the comparison key of one of the
   field's texts, of the value the field settled on, or of the expansion it
   settled through (the step's abbreviation row), or, for the country, when
   its source names it only by a country code (NGA's "GT") that is the ISO
   3166-1 alpha-2 code the record the country settled on carries (Wikidata's
   P297 for Guatemala), the same two capital letters, outside ISO's
   user-assigned codes (lies_in):
   - below the country, the candidate has parents, one of them is the
     country settled for the reading, and for a county or a city one is the
     province settled for it too, when one is. No country settled for the
     reading, no parents, or none that is that country or province: the
     field goes to review with the reason. A country needs no parent;
   - a county also needs the province its reading writes to be settled,
     and is never that province itself: its record, or one of its texts
     with letter case, accents and punctuation aside and unit words kept;
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

import re
import unicodedata
from functools import lru_cache
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import NamedTuple

from specimen_digitization.application.derivations import UNITS
from specimen_digitization.application.domain import LookupStatus
from specimen_digitization.application.georef_locality import comparison_key, fold, one_letter_apart
from specimen_digitization.application.georef_wikidata import FIRST_LEVEL, LEVEL_NAMES

from . import written
from .abbreviations import abbreviated, fit, fits, initialism
from .checks import collapse, genus_in_doubt, longer_name, taxon_query_grounded
from .contracts import GAZETTEERS, PLACE_SOURCES, FieldTask, Reading, SourceAnswer, SourceCandidate
from .written import separates as _separates
from .written import words as _words

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
# A county is the country's second-level unit, whatever the country calls it
# (the owner, 2026-10-11, on a Guatemalan municipio: "however the local
# government does it so if that is the equivalent then yes"): TGN's second
# level subdivisions, NGA's A.ADM2, and for Wikidata a place whose classes
# reach its second-level administrative division (sources._levels names
# that class among a county lookup's kinds; "second-level administrative
# country subdivision" is the class's former label).
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
            "U.S. state", "first-level administrative division", "first-level administrative country subdivision"),
        "county": ("county", "second-level administrative division",
            "second-level administrative country subdivision"),
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
FIRST_PASS_CONFLICT = ("The first pass read this label's image as one reader's text, and only another label "
    "or a near spelling backs another reader's: a person decides.")
PERSON_DECIDED = "A person transcribed this label, and that transcription is its text."
# The units path's reasons (labels_by_rule): one reader's text that nothing backs, and
# texts that only readers' agreement or another label backs, each against another.
ONE_READER = "One reader wrote this text, and neither the image, nor an approved source, nor another label backs it."
TEXTS_CONTESTED = ("More than one reader's text is backed only by readers that agree or by another label, and "
    "neither the image nor an approved source backs one: a person decides.")
TIED = ("Two or more texts have the same backing, as many readers and the same first reader, so nothing ranks one "
    "above the others: a person decides.")
NOT_CANDIDATE = "This value is not the text found for this field in the readings."
PART_OF_NAME = "The label writes a longer scientific name than this value."
DOUBTFUL_GENUS = "The label marks this name's genus as doubtful."
NO_PLACE = "No approved place source confirms this value."
EXPANSIONS_DIFFER = "The sources found different places for the label's abbreviation."
FIRST_LEVEL_TOO = ("The sources also find this name as a province or state, so they cannot tell which the "
    "label means.")
NOT_EVERY_READER = "Not every reader of the label writes this text."
PART_OF_RANGE = "The label writes this value as one end of a range."
UNIT_DIFFERS = "The label writes this elevation in the other unit."
NO_UNIT = "The label writes no elevation unit with this number."
A_DISTANCE = "The label writes this number as a distance, not an elevation."
HOLDS_AN_ELEVATION = "This text holds an elevation, which is another field's."
HOLDS_A_DATE = "This text holds a date, which is another field's."
HOLDS_A_RANGE = "This text holds a range of dates or elevations, which is another field's."
HOLDS = {written.ELEVATION: HOLDS_AN_ELEVATION, written.DATE: HOLDS_A_DATE, written.RANGE: HOLDS_A_RANGE}
# The unit each elevation field holds (application.derivations.UNITS), and
# its name in the experts' retry.
FIELD_UNITS = {key: unit for unit, keys in UNITS.items() for key in keys}
UNIT_NAMES = {"m": "metres", "ft": "feet"}
# The fields whose text read from the transcript never holds a date, an
# elevation or a range of them (_holds_another_kind): the place fields
# (precise location among them) and the collection code.
NO_DATES_OR_ELEVATIONS = frozenset({"country", "province_state", "county", "city", "precise_location",
    "collection_code"})


@dataclass(frozen=True)
class Refusal:
    """Why a resolved answer cannot settle its field: the field's plain reason,
    and what the expert is told when it can still correct its answer."""

    reason: str
    retry: str
    # The readings disagree: the field is ambiguous, not merely unresolved.
    differ: bool = False
    # The texts a person chooses from (the units path's TEXTS_CONTESTED), which the
    # field's reason lists (step._field_value).
    options: tuple[str, ...] = ()


def names_no_place(task: FieldTask, text: str) -> bool:
    """For a place value field, whether a text the organiser left names no
    place at all: by the place comparison key (place_name) it is nothing but
    unit words and punctuation, as f35af3a5's candidate "Prov." for the
    province, cut from "Davao, Prov." (the batch rerun of 2026-10-18). Such
    a text is no literal of the field: it neither constrains an answer's
    literal (_cut_candidate) nor counts as a reader's text (labels). It
    still shows that its reading writes the field, for the parents check
    (step._place_texts, parents_refusal's NO_PROVINCE)."""
    return task.key in PLACE_VALUE_FIELDS and not place_name(text)


def reader_literals(task: FieldTask, readings: Sequence[Reading], *,
        unit_words: bool = False) -> dict[str, set[str]]:
    """Each reading's literals for the field, collapsed: the organiser's
    candidates, and the per-reader verbatims it left (a reading named by its
    observation, a raw reading first), less a place's texts that name no
    place (names_no_place) unless `unit_words` keeps them, as for the
    parents check, which asks only whether a reading writes the field."""
    by_name = {r.name: r for r in readings}
    by_observation: dict[str, str] = {}
    for reading in readings:
        if reading.input_source != DECIDED or reading.observation_id not in by_observation:
            by_observation[reading.observation_id] = reading.name
    found: dict[str, set[str]] = {}
    for candidate in task.candidates:
        if candidate.reading in by_name and candidate.literal.strip() and (
                unit_words or not names_no_place(task, candidate.literal)):
            found.setdefault(candidate.reading, set()).add(collapse(candidate.literal))
    for observation, text in task.current.verbatim_by_observation.items():
        name = by_observation.get(observation)
        if name is not None and text and text.strip() and (unit_words or not names_no_place(task, text)):
            found.setdefault(name, set()).add(collapse(text))
    return found


def candidates_by_reading(task: FieldTask, readings: Sequence[Reading]) -> dict[str, dict[str, str]]:
    """Each reading's candidate literals for the field: collapsed, to the
    literal exactly as its candidate gives it; for a place value field, none
    that names no place (names_no_place)."""
    names = {r.name for r in readings}
    found: dict[str, dict[str, str]] = {}
    for candidate in task.candidates:
        if candidate.reading in names and candidate.literal.strip() and not names_no_place(task, candidate.literal):
            found.setdefault(candidate.reading, {}).setdefault(collapse(candidate.literal), candidate.literal)
    return found


def candidate_literal(task: FieldTask, readings: Sequence[Reading], literal: str,
        named: Sequence[Reading]) -> str | None:
    """The whole candidate literal the answer's literal is, exactly as the
    candidate gives it, or None when it is not a candidate literal of every
    named reading. Compared after NFC and whitespace collapse only."""
    allowed = candidates_by_reading(task, readings)
    want = collapse(literal)
    whole = None
    for reading in named:
        found = allowed.get(reading.name, {})
        if want not in found:
            return None
        whole = whole or found[want]
    return whole


# Where a resolved literal comes from (literal_basis): an organiser's whole
# candidate, or text the expert read in the transcript itself.
CANDIDATE, TRANSCRIPT = "candidate", "transcript"


def _lines(text: str) -> Iterable[tuple[int, str]]:
    """Each line of the text, with the offset it starts at."""
    offset = 0
    for line in text.split("\n"):
        yield offset, line
        offset += len(line) + 1


def _line_of(text: str, start: int, end: int) -> tuple[int, str]:
    """The line of the text that holds the span [start, end), with the offset
    it starts at."""
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    return line_start, text[line_start:len(text) if line_end < 0 else line_end]


def _clause(line: str, start: int, end: int) -> tuple[int, int]:
    """The comma- or semicolon-separated part of the line that holds the span
    [start, end), as (start, end): from just after the last separator before
    the span to just before the first one at or after its end (a separator
    inside the span is part of it); the whole line when it has none."""
    marks = [index for index in range(len(line)) if _separates(line, index)]
    first = max((index for index in marks if index < start), default=-1) + 1
    last = min((index for index in marks if index >= end), default=len(line))
    return first, last


def _in_a_range(line: str, start: int, end: int) -> bool:
    """Whether the span [start, end) of the line is part of a range: the
    clause holding it (_clause) writes a range (written.ranges: two ends that
    each hold a digit, written alike, joined by a dash of any form standing
    alone or at a word's edge, or by a joiner of written.RANGE_WORDS or
    written.RANGE_SIGNS, in any of the languages listed, with a unit, a month
    or an approximate marker allowed between a number and the joiner), and
    the span does not hold both its ends (the whole range); or a word of two
    numbers joined by a dash or a "/" (written.glued_range: "10-12") stands
    right before or after the span ("Sept. 1946" of "10-12 Sept. 1946").
    Either is written alike with the span (written.part_of_a_range): a range
    of another kind is another field's ("24.IV.1948" of "24.IV.1948 10-12
    h", "1200 m" of "1200 m 10-12 Sept. 1946"). The clause's words are its
    line's words cut at its comma or semicolon, so the word that ends in it
    stays in it ("V-2-48" of "IV-24-48 to V-2-48, Yepocapa")."""
    first, last = _clause(line, start, end)
    spans = written.pieces(line, [(max(a, first), min(b, last)) for a, b in _words(line) if a < last and b > first])
    return written.part_of_a_range(line, spans, start, end)


def _edges(line: str) -> tuple[frozenset[int], frozenset[int]]:
    """Where a run of whole words may start and where it may end on the line:
    at a word's edge, or past any characters other than letters and digits
    at its edge (the comma of "Yepocapa,", the brackets of "(Davao)", the
    quote of "'46", the foot mark of "6400'"), never between two letters or
    digits of one word ("24-48" is no run of "IV-24-48", nor "30" of
    "Sp.30")."""
    starts: set[int] = set()
    ends: set[int] = set()
    for start, end in _words(line):
        letters = [index for index in range(start, end) if line[index].isalnum()]
        first, last = (letters[0], letters[-1] + 1) if letters else (start, end)
        starts.update(range(start, first + 1))
        ends.update(range(last, end + 1))
    return frozenset(starts), frozenset(ends)


def verbatim_runs(text: str, literal: str) -> list[tuple[int, int]]:
    """Where the text writes the literal exactly as a run of whole words within
    one line (or that whole line), as (start, end) offsets in the text: the
    literal holds a letter or a digit, lies on one line, and starts and ends
    at word edges (_edges), so it cuts no word. Empty when it writes none."""
    found: list[tuple[int, int]] = []
    if (not literal or "\n" in literal or literal != literal.strip()
            or not any(char.isalnum() for char in literal)):
        return found
    for offset, line in _lines(text):
        at = line.find(literal)
        if at < 0:
            continue
        starts, ends = _edges(line)
        while at >= 0:
            if at in starts and at + len(literal) in ends:
                found.append((offset + at, offset + at + len(literal)))
            at = line.find(literal, at + 1)
    return found


# The fields whose literal may run over consecutive lines of one reading:
# precise location, the label's verbatim locality, which labels often write
# over two lines (e98a924c's "E Slope Mt." / "McKinley, Davao Prov.", the
# organiser's two candidates "Seliban Riv." and "Mt. Apo" on 2b02009d's two
# lines; the third rerun of 2026-10-18). Every other field, places among
# them, keeps its literal on one line.
ACROSS_LINES = frozenset({"precise_location"})


def _flat(text: str) -> str:
    """The text with each line break read as a space: the same length, so an
    offset in it is the same offset in the text."""
    return text.replace("\n", " ")


def runs_across_lines(text: str, literal: str) -> list[tuple[int, int]]:
    """Where the text writes the literal, which holds a line break, exactly as
    a run of whole words over consecutive lines, as (start, end): it starts
    at a word's edge on its first line and ends at one on its last line
    (_edges), every line between lies wholly inside it, and no line of it is
    blank. Empty when the literal holds no line break or is not so written."""
    found: list[tuple[int, int]] = []
    if ("\n" not in literal or literal != literal.strip()
            or any(not line.strip() for line in literal.split("\n"))):
        return found
    at = text.find(literal)
    while at >= 0:
        end = at + len(literal)
        first_start, first = _line_of(text, at, at)
        last_start, last = _line_of(text, end, end)
        starts, _ = _edges(first)
        _, ends = _edges(last)
        if at - first_start in starts and end - last_start in ends:
            found.append((at, end))
        at = text.find(literal, at + 1)
    return found


def written_runs(key: str, text: str, literal: str) -> list[tuple[int, int]]:
    """Where the text writes the field `key`'s literal as a run of whole
    words: within one line (verbatim_runs), or, for a field in ACROSS_LINES
    whose literal holds a line break, over consecutive lines
    (runs_across_lines)."""
    if key in ACROSS_LINES and "\n" in literal:
        return runs_across_lines(text, literal)
    return verbatim_runs(text, literal)


def across_lines(key: str, readings: Sequence[Reading], literal: str) -> str | None:
    """For a field in ACROSS_LINES, the text each of these readings writes for
    the literal over consecutive lines, its line breaks as the readings write
    them, when the literal reads each line break as a space or a line break
    (_flat) and every reading writes that one text so (runs_across_lines):
    e98a924c's expert gave "E Slope Mt. McKinley, Davao Prov.", which both
    readers of its label write as "E Slope Mt.\\nMcKinley, Davao Prov.".
    None for any other field, when no reading is given, or when a reading
    writes no such text or several."""
    if key not in ACROSS_LINES or not readings or not literal or literal != literal.strip():
        return None
    want = _flat(literal)
    found: set[str] = set()
    for reading in readings:
        flat = _flat(reading.text)
        texts = set()
        at = flat.find(want)
        while at >= 0:
            written = reading.text[at:at + len(want)]
            if "\n" in written and runs_across_lines(reading.text, written):
                texts.add(written)
            at = flat.find(want, at + 1)
        if len(texts) != 1:
            return None
        found |= texts
    return found.pop() if len(found) == 1 else None


def _agreeing_spans(text: str, literal: str) -> list[tuple[str, int, int]]:
    """Each run of whole words within one line of the text (as verbatim_runs
    reads them) that is the literal, letter case and spacing aside
    (agreement_key), as (line, start, end)."""
    want = agreement_key(literal)
    found: list[tuple[str, int, int]] = []
    if not want or not any(char.isalnum() for char in want):
        return found
    for _, line in _lines(text):
        if want not in agreement_key(line):
            continue
        starts, ends = _edges(line)
        for start in sorted(starts):
            for end in sorted(ends):
                if end > start and agreement_key(line[start:end]) == want:
                    found.append((line, start, end))
    return found


def agreeing_runs(text: str, literal: str) -> list[str]:
    """The runs of whole words within one line of the text (as verbatim_runs
    reads them) that are the literal, letter case and spacing aside
    (agreement_key), each as the text writes it."""
    return list(dict.fromkeys(line[start:end] for line, start, end in _agreeing_spans(text, literal)))


def _agreeing_spans_across(text: str, literal: str) -> list[tuple[int, int]]:
    """Each run of whole words over one or more consecutive lines of the text
    that is the literal, letter case, spacing and line breaks aside
    (agreement_key), as (start, end) in the text: it starts at a word's edge
    of its line and ends at one of its line (_edges)."""
    want = agreement_key(literal)
    if not want or not any(char.isalnum() for char in want) or want not in agreement_key(text):
        return []
    starts: list[int] = []
    ends: set[int] = set()
    for offset, line in _lines(text):
        line_starts, line_ends = _edges(line)
        starts.extend(offset + index for index in sorted(line_starts))
        ends.update(offset + index for index in line_ends)
    found = []
    for start in dict.fromkeys(starts):
        for end in sorted(ends):
            if end > start and agreement_key(text[start:end]) == want:
                found.append((start, end))
    return list(dict.fromkeys(found))


def _holding_across(text: str, start: int, end: int) -> str:
    """The text holding the span [start, end) over consecutive lines: from
    just after the last comma or semicolon before it on its first line to
    just before the first one at or after its end on its last line (_clause),
    each line's edge where it has none."""
    first_start, first = _line_of(text, start, start)
    last_start, last = _line_of(text, end, end)
    return text[first_start + _clause(first, start - first_start, start - first_start)[0]:
        last_start + _clause(last, end - last_start, end - last_start)[1]]


def _within_runs(text: str, piece: str, spans: Sequence[tuple[int, int]]) -> bool:
    """Whether the text writes `piece` (line breaks read as spaces) and every
    place it does lies wholly inside one of the spans."""
    flat, want = _flat(text), _flat(piece)
    places = []
    at = flat.find(want) if want else -1
    while at >= 0:
        places.append((at, at + len(want)))
        at = flat.find(want, at + 1)
    return bool(places) and all(any(start <= at and stop <= end for start, end in spans) for at, stop in places)


def holding_clauses(text: str, literal: str) -> list[str]:
    """The clauses of the text that hold the literal: for each run that is
    the literal, letter case and spacing aside (_agreeing_spans), the comma-
    or semicolon-separated part of its line around it (_clause), the whole
    line when it has none. "trap" is held by "light trap", "Yepocapa" by
    "Yepocapa" in "Yepocapa, Mun.", "IV-24-48" by "IV-24-48 to V-2-48"."""
    found = []
    for line, start, end in _agreeing_spans(text, literal):
        first, last = _clause(line, start, end)
        found.append(line[first:last])
    return list(dict.fromkeys(found))


def _cut_candidate(task: FieldTask, readings: Sequence[Reading], literal: str,
        named: Sequence[Reading]) -> tuple[str, str] | None:
    """A candidate of a reading the answer names that the literal cuts or
    extends, as (reading, candidate literal): one holds the other and they
    differ ("Sept. '46" and
    "3 Sept. '46", "Danaus" and "Danaus plexippus", B2). A literal over
    consecutive lines (ACROSS_LINES: it holds a line break) may hold whole
    candidates, the organiser's lines of one locality joined in their order
    on the label (2b02009d's "Seliban Riv." and "Mt. Apo"): it cuts a
    candidate when it is a piece of one, or when one of the candidate's
    places in the reading lies partly inside one of its runs and partly
    outside (runs_across_lines). It extends one when a line of a run holds a
    candidate and other words besides ("near Mt. Apo" of "Seliban Riv." /
    "near Mt. Apo", as "near Mt. Apo" on one line extends "Mt. Apo"; round 1
    of #379's review, finding 3): a line holding a candidate holds no letter
    or digit but its candidates', only punctuation and spaces between them. A
    line holding none may join them (e98a924c's lines, no candidate filed).
    None otherwise."""
    want = collapse(literal)
    allowed = candidates_by_reading(task, readings)
    across = task.key in ACROSS_LINES and "\n" in literal
    for reading in dict.fromkeys(named):
        spans = runs_across_lines(reading.text, literal) if across else []
        places: list[tuple[int, int, str]] = []
        for text, given in allowed.get(reading.name, {}).items():
            if text == want:
                continue
            if want in text:
                return reading.name, given
            if not across:
                if text in want:
                    return reading.name, given
                continue
            flat = _flat(reading.text)
            at = flat.find(_flat(given))
            while at >= 0:
                stop = at + len(given)
                if any(start < stop and at < end and not (start <= at and stop <= end) for start, end in spans):
                    return reading.name, given
                if any(start <= at and stop <= end for start, end in spans):
                    places.append((at, stop, given))
                at = flat.find(_flat(given), at + 1)
        for start, end in spans:
            for offset, line in _lines(reading.text):
                first, last = max(start, offset), min(end, offset + len(line))
                held = [(at, stop, given) for at, stop, given in places if first <= at and stop <= last]
                if first >= last or not held:
                    continue
                left = list(reading.text[first:last])
                for at, stop, _ in held:
                    left[at - first:stop - first] = " " * (stop - at)
                if any(char.isalnum() for char in left):
                    return reading.name, held[0][2]
    return None


def literal_basis(task: FieldTask, readings: Sequence[Reading], literal: str,
        named: Sequence[Reading]) -> str | None:
    """Where the answer's literal comes from. CANDIDATE: it is a whole
    candidate literal of every reading it names (candidate_literal).
    TRANSCRIPT: it is not, but each of those readings writes it as a run of
    whole words within one line (verbatim_runs; for precise location, over
    consecutive lines when it holds a line break: written_runs), and it cuts
    or extends no
    candidate of that reading (_cut_candidate): the expert read it in the
    transcript itself (the owner's design: experts with every raw
    transcription). None otherwise."""
    if not named:
        return None
    if candidate_literal(task, readings, literal, named) is not None:
        return CANDIDATE
    if (all(written_runs(task.key, reading.text, literal) for reading in named)
            and _cut_candidate(task, readings, literal, named) is None):
        return TRANSCRIPT
    return None


def literal_refusal(task: FieldTask, readings: Sequence[Reading], *, literal: str,
        named: Sequence[Reading]) -> Refusal | None:
    """Why the answer's literal may not settle the field, or None: it must be
    a whole candidate literal of each reading it names, whichever reader
    wrote it (the first pass's preferred reading is advice, never a
    constraint: the owner, 2026-10-25), or text each of those readings
    writes as a run of whole words
    within one line that cuts or extends no candidate of it (literal_basis),
    never a shorter or longer piece of a candidate (B2); for a taxon, a
    candidate whose quote writes a longer name from it on is such a piece too
    (_part_of_name), as is text read from a reading that writes a longer
    name around it (_longer_written), and a literal whose genus the label
    marks as doubtful never settles (_genus_in_doubt). An elevation, by
    candidate or read from the transcript, settles only a field of the unit
    the reading writes it in (_unit_refusal). Text read from the transcript
    is never one end of a range for a date or an elevation (_part_of_range),
    and never holds a date, an elevation or a range of them for a place or
    the collection code (_holds_another_kind)."""
    basis = literal_basis(task, readings, literal, named)
    if basis == CANDIDATE:
        return (_unit_refusal(task, readings, literal, named) or _part_of_name(task, readings, literal, named)
            or _genus_in_doubt(task, readings, literal, named))
    if basis == TRANSCRIPT:
        return (_part_of_range(task, readings, literal, named) or _unit_refusal(task, readings, literal, named)
            or _holds_another_kind(task, literal) or _longer_written(task, readings, literal, named)
            or _genus_in_doubt(task, readings, literal, named))
    allowed = candidates_by_reading(task, readings)
    offered = [f"{source.name}: {text!r}" for source in dict.fromkeys(named)
        for text in allowed.get(source.name, {}).values()]
    shown = "; ".join(offered) or "none"
    cut = _cut_candidate(task, readings, literal, named)
    why = f"{literal!r} cuts or extends the candidate {cut[1]!r} of reading {cut[0]}. " if cut else ""
    return Refusal(NOT_CANDIDATE, why + (
        "A resolved literal is one of the organiser's candidate literals for every reading you "
        "name, whole and exactly as the "
        f"candidate gives it. Candidates for the readings you named: {shown}. Never shorten or "
        "extend a candidate. When no candidate is the right text (the organiser may have given "
        "this field another field's text, or a place of another kind), the literal may be text "
        "that each reading you name writes itself for this field: whole words within one line, "
        "cutting no word and no candidate. "
        + ("A locality written over consecutive lines may run over them: copy those lines as the "
           "reading writes them, holding whole candidates in their order on the label and cutting none. "
           if task.key in ACROSS_LINES else "")
        + "Copy it and name only readings that have it, or answer "
        "several_possibilities or sources_cannot_resolve."))


def _part_of_range(task: FieldTask, readings: Sequence[Reading], literal: str,
        named: Sequence[Reading]) -> Refusal | None:
    """For a date or an elevation read from the transcript (TRANSCRIPT), why
    it cannot settle: wherever a reading it is read from writes it, it is
    part of a range the clause writes (_in_a_range): "V-2-48" or "IV-24-48"
    of "IV-24-48 to V-2-48", "1500 m" of "1200 to 1500 m". The whole range keeps the rules a candidate
    has. None otherwise, and for any other field."""
    if FIELD_KINDS.get(task.key) not in ("date", "elevation"):
        return None
    for reading in dict.fromkeys(named):
        for start, end in verbatim_runs(reading.text, literal):
            line_start, line = _line_of(reading.text, start, end)
            if _in_a_range(line, start - line_start, end - line_start):
                return Refusal(PART_OF_RANGE, (
                    f"Reading {reading.name} writes {literal!r} as one end of a range ({line!r}). Text "
                    "read from the readings is never one end of a range: copy the whole range as the "
                    "literal and take the end your brief names from a check run on exactly it, or answer "
                    "several_possibilities or sources_cannot_resolve."))
    return None


def _unit_refusal(task: FieldTask, readings: Sequence[Reading], literal: str,
        named: Sequence[Reading]) -> Refusal | None:
    """For an elevation field, why the literal cannot settle it, by candidate
    or read from the transcript (PR #300's review, finding 5): a reading it
    names writes its numbers in the other unit anywhere it writes it
    (written.units_of: the unit after a number, glued or after spaces, or a range's trailing unit,
    in any spelling of written.ELEVATION_UNITS: "1500 m" or "1500" of "alt.
    1500 m", "2000 msnm" or "6400 pies" in the wrong field); or with no unit
    anywhere (a bare number: a unit is never guessed, G41); or as a distance
    anywhere it writes it (written.written_as_a_distance: "1200 m" of "1200 m
    along road"). Each field holds
    the unit application.derivations.UNITS gives it; the other unit's field
    is filled by its exact conversion afterwards (derive). None otherwise,
    and for any other field."""
    unit = FIELD_UNITS.get(task.key)
    if unit is None:
        return None
    for reading in dict.fromkeys(named):
        if written.written_as_a_distance(reading.text, literal):
            return Refusal(A_DISTANCE, (
                f"Reading {reading.name} writes {literal!r} as a distance: a relation word or a compass point "
                "follows it in its clause ('<n> m along', '<n> m N of'). A distance is no elevation: copy "
                "the elevation the label writes, or answer label_lacks_value when it writes none."))
        found = written.units_of(reading.text, literal)
        other = sorted(frozenset().union(*found) - {unit})
        if other:
            return Refusal(UNIT_DIFFERS, (
                f"Reading {reading.name} writes {literal!r} in {UNIT_NAMES[other[0]]}, and this field holds "
                f"{UNIT_NAMES[unit]}. An elevation settles only the fields of the unit the label writes it "
                "in: never convert it yourself. When the label states this elevation only in the other "
                "unit, answer label_lacks_value (the step converts it exactly); otherwise copy the "
                f"elevation the label writes in {UNIT_NAMES[unit]}."))
        if not any(found):
            return Refusal(NO_UNIT, (
                f"Reading {reading.name} writes {literal!r} with no unit ({', '.join(UNIT_NAMES.values())}"
                " in any spelling). A unit is never guessed from the magnitude, the place or a map: answer "
                "sources_cannot_resolve and quote it."))
    return None


def _holds_another_kind(task: FieldTask, literal: str) -> Refusal | None:
    """For a place field or the collection code read from the transcript
    (TRANSCRIPT), why it cannot settle: the literal holds text that is plainly
    another kind of field's (written.other_kind; PR #300's review, finding
    2), whether or not another field's expert claimed that text: an
    elevation ("Yepocapa, 4800ft."), a date the date parser reads
    ("IV-24-48" as the collection code) or a range of dates or elevations.
    A distance ("500 m N of the bridge", "200 m upstream of the ford") is no
    elevation, and in a place, a number right after a road, km, hill, farm
    or estate word is part of the place, no date ("Hill <yyyy>", "km
    <yyyy>"; written.PLACE_WORDS); in the collection code it is still a date.
    None otherwise, and for any other field."""
    if task.key not in NO_DATES_OR_ELEVATIONS:
        return None
    found = written.other_kind(literal, place=task.key != "collection_code")
    if found is None:
        return None
    kind, text = found
    return Refusal(HOLDS[kind], (
        f"{literal!r} holds {text!r}, which is {('an ' if kind == written.ELEVATION else 'a ') + kind}: "
        "another field's text, never this one's. Copy only this field's own text, leaving that out, or "
        "answer several_possibilities or sources_cannot_resolve."))


def _longer_written(task: FieldTask, readings: Sequence[Reading], literal: str,
        named: Sequence[Reading]) -> Refusal | None:
    """For a taxon read from the transcript (TRANSCRIPT), why it cannot settle:
    a reading it is read from writes a longer name around it, as a
    candidate's quote would (checks.longer_name, on the reading's text from the line above the
    literal on): "Danaus plexippus" on a line that writes "Danaus plexippus
    megalippe", "sp. 1" below "Epipsocus". None otherwise, and for any other
    field."""
    if task.key != "taxon":
        return None
    for reading in dict.fromkeys(named):
        text = reading.text
        for start, _ in verbatim_runs(text, literal):
            line_start = text.rfind("\n", 0, start) + 1
            above = text.rfind("\n", 0, line_start - 1) + 1 if line_start else 0
            longer = longer_name(text[above:], literal)
            if longer is not None:
                return Refusal(PART_OF_NAME, (
                    f"Reading {reading.name} writes the longer name {longer!r} around {literal!r}. A "
                    "taxon settles only on the whole name its reading writes, so this text cannot "
                    "settle it: answer several_possibilities or sources_cannot_resolve."))
    return None


def _part_of_name(task: FieldTask, readings: Sequence[Reading], literal: str,
        named: Sequence[Reading]) -> Refusal | None:
    """For a taxon, why the candidate the literal is cannot settle it: its
    quote, the reading's text it was taken from, writes a longer name around
    the literal (checks.longer_name; N3 of #284's third review, B1 of #289's
    review), so the literal is a piece of the name the label writes. Every
    candidate of that literal of the readings named is checked. None
    otherwise, and for any other field."""
    if task.key != "taxon":
        return None
    want = collapse(literal)
    names = {reading.name for reading in named}
    for candidate in task.candidates:
        if candidate.reading not in names or collapse(candidate.literal) != want:
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
    before the literal's first word or on it, a qualifier on the line above
    only standing alone there) in the quote of a candidate of
    that literal, or in the text of a reading the answer names, or of any
    reader of its label unless the answer names the reader the first pass
    preferred for that label (then every reader is the label's text: 1A's
    "cf. Epipsocus sp. 1" holds back an answer naming only 1B's "Epipsocus
    sp. 1", and on a label whose preferred reader writes "cf." it holds back
    an answer that overrides that reader), wherever that text writes the
    literal (1c of #289's fifth review;
    the sixth review's probe 3). The taxon brief has the expert look such a genus up
    alone and answer sources_cannot_resolve; GBIF may still decide it, and
    this refuses an answer that resolves it. None otherwise, and for any
    other field."""
    if task.key != "taxon":
        return None
    want = collapse(literal)
    names = {reading.name for reading in named}
    # Unless the answer follows the first pass's preferred reader of a label,
    # every reader is the label's text: one reader's "cf." holds the genus
    # back whichever reader is named.
    followed = {reading.region_id for reading in named if reading.input_source == DECIDED}
    names |= {reading.name for reading in readings
        if reading.region_id in {r.region_id for r in named} - followed}
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
    found = [candidate for candidate in answer.candidates
        if any(_kind_matches(answer.source_id, kind, level)
            for kind in (candidate.kind or "").split(",") for level in levels)]
    if key == "county" and answer.source_id == "wikidata":
        # A Wikidata place whose classes reach the first-level division is
        # never a county, whatever its other kinds say (sources._place names
        # that class among its kinds; Codex's review of #325 at 9f5319ca).
        first = LEVEL_NAMES[FIRST_LEVEL]
        found = [candidate for candidate in found
            if first not in (kind.strip().casefold() for kind in (candidate.kind or "").split(","))]
    return found


def placed(key: str, answer: SourceAnswer) -> SourceCandidate | None:
    """The one candidate a place source's answer settles the place field
    `key` on: a success or ambiguous answer with exactly one candidate at the
    field's level. None when it has none or several there (P1 of #284)."""
    if answer.source_id not in PLACE_SOURCES or answer.status not in PLACE_ANSWERED:
        return None
    level = at_level(key, answer)
    return level[0] if len(level) == 1 else None


def identities(answers: Iterable[SourceAnswer], literal: str, key: str, *, near: bool = False) -> set[str]:
    """What captured answers about this literal confirm it as, for the field
    `key`: the authority_id of GBIF's decided candidate (the one its
    evidence's locator names) in a success answer; for a place value field,
    of the one candidate at its level (placed) when it has the literal's name,
    or, for a literal written as an abbreviation, of the one candidate at its
    level of a place source's answer asked an expansion its letters fit
    (abbreviations.fit, the rule place_settling settles such a value by:
    "United States of America" for 3781e440's "USA", "Illinois" for its
    "Ill."; a place settled so on initials still needs another place inside
    it, step._corroborate); for another field a place source answers, of a
    success answer's candidate of that name. Names compare as place names.
    With `near`, for a place value field, also of the one candidate at its
    level of an answer asked that candidate's own name, when the name is one
    letter from the literal (application.georef_locality.one_letter_apart:
    place_settling's NEAR_SPELLING), for a label whose readers' texts no
    answer confirms by their own names (_by_source), whichever reader writes
    it (the owner, 2026-10-25: "As matches could be close to raw but not
    exact"); the step still settles such a value only on G34's whole
    condition (parents_refusal). Empty when nothing confirms it."""
    found: set[str] = set()
    for answer in answers:
        if answer.evidence is None:
            continue
        if not about(answer, literal):
            if (key in PLACE_VALUE_FIELDS and answer.source_id in PLACE_SOURCES
                    and fits(literal, asked_name(answer))
                    and (one := placed(key, answer)) is not None and one.authority_id):
                found.add(one.authority_id)
            elif (near and key in PLACE_VALUE_FIELDS and (one := placed(key, answer)) is not None
                    and one.authority_id and about(answer, collapse(one.name))
                    and one_letter_apart(literal, one.name)):
                found.add(one.authority_id)
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


def found_only_elsewhere(answers: Iterable[SourceAnswer], literal: str, key: str) -> bool:
    """Whether the place value field `key`'s sources found this literal, but
    only as another kind of place than the field's, so that it is ruled out
    for the field as a literal no source found is (ruled_out): 48a71d53's
    "Mindanao," on a province, which Wikidata finds as an island and an
    island group and NGA as an island, a stream, streets, towns and a
    third-level unit, beside "Davao Prov.", a province. Every Getty TGN,
    Wikidata or NGA answer about it (about) with a success or ambiguous
    status and its evidence stored lists candidates; those of two or more of
    these gazetteers hold one of the literal's name (place_name), as one
    answer's list may be cut short (Wikidata's holds at most seven); each
    candidate of that name has a kind; and no candidate at the field's level
    (at_level) has its name or one letter from it (one_letter_apart).
    GEOLocate's candidates repeat a part of the
    query except for a city (at_level), so its answers count only for a
    city, where any candidate keeps the literal. Never for an abbreviated
    literal (abbreviations.abbreviated: "Ill.", "Mt. Apo"), which may stand
    for a name no source was asked, nor for a literal asked of no gazetteer."""
    want = place_name(literal)
    if key not in PLACE_VALUE_FIELDS or not want or abbreviated(literal):
        return False
    named: set[str] = set()
    for answer in answers:
        if (answer.source_id not in PLACE_SOURCES or answer.evidence is None
                or answer.status not in PLACE_ANSWERED or not about(answer, literal)):
            continue
        if answer.source_id == "geolocate":
            if key == "city" and answer.candidates:
                return False
            continue
        if not answer.candidates:
            return False
        for candidate in answer.candidates:
            if place_name(candidate.name) == want:
                if not (candidate.kind or "").strip():
                    return False
                named.add(answer.source_id)
        if any(place_name(candidate.name) == want or one_letter_apart(literal, candidate.name)
                for candidate in at_level(key, answer)):
            return False
    return len(named) >= 2


def only_a_possibility(text: str, reading: Reading, readings: Sequence[Reading]) -> bool:
    """Whether the reading writes the text only as a possibility nothing on
    the labels backs: it is another reader of a label whose first pass
    preferred a reader, that preferred reading does not write the text, and
    no reading of another label writes it as whole words (verbatim_runs),
    which could corroborate it (labels). Such a text is raw transcription
    the harness may leverage, never by itself a value (the owner,
    2026-10-25: "It's raw transcription per model that can be leveraged if
    harness wants to think of possibilities LLM may have missed on its
    interpretation"). d10333ff's "BONITELL": reader 1B's line where the
    preferred 1A writes "ILLINOIS"."""
    preferred = next((r for r in readings if r.region_id == reading.region_id and r.input_source == DECIDED),
        None)
    return (preferred is not None and preferred is not reading and text not in preferred.text
        and not any(verbatim_runs(other.text, text) for other in readings if other.region_id != reading.region_id))


def disputed(text: str, reading: Reading, readings: Sequence[Reading],
        claimed: Mapping[str, Iterable[str]]) -> bool:
    """Whether the readers of the reading's label dispute the text where the
    reading writes it: every other reader reads that very ink as the text of a
    field of another kind. The label's first pass preferred no reader, it
    has at least one other reader, and no other reader writes the text; for
    each other reader (_disputed_by, the test two readers have always had):
    each run of the text in the reading (verbatim_runs) lies wholly inside the token
    differences between the two readings (application.first_pass.reading_differences:
    the differences the label's first pass is asked to judge), each with text on
    the other reader's side; that side, joined, is neither the text's place
    name (place_name) nor a spelling one letter from it (one_letter_apart);
    and it is written, as whole words, in one of the other reader's texts for
    a field of another kind (`claimed`, by reading name: the organiser's
    candidates and those fields' literals; step._claimed_texts leaves out
    every place field). d10333ff's determination label: reader 3A writes
    "Panama" where 3B writes "Panorpa", 3B's taxon; a collector's "Chas." or
    a date's "1945" there is another kind too. A reader that leaves the text
    out (no text on its side) disputes nothing, nor does one that writes it
    with other accents or one letter off ("Panamá"), nor one whose other
    words no such field holds: two spellings of one country, or another
    place field's text ("Texas" where the other writes "Mexico"), a rival
    reading of the same place. With three or more readers, one reader that
    does not dispute the text (one that writes it, say) leaves it undisputed."""
    group = [r for r in readings if r.region_id == reading.region_id]
    others = [r for r in group if r is not reading]
    if len(group) < 2 or not others or any(r.input_source == DECIDED for r in group):
        return False
    runs = verbatim_runs(reading.text, text)
    if not runs or any(verbatim_runs(other.text, text) for other in others):
        return False
    return all(_disputed_by(text, reading, other, runs, claimed) for other in others)


def _disputed_by(text: str, reading: Reading, other: Reading, runs,
        claimed: Mapping[str, Iterable[str]]) -> bool:
    """Whether one other reader disputes the text's runs in the reading (disputed)."""
    from specimen_digitization.application.first_pass import reading_differences

    theirs_elsewhere = [held for held in claimed.get(other.name, ()) if held and held.strip()]
    pairs = [(mine, theirs) for mine, theirs in reading_differences(reading.text, other.text) if mine.end > mine.start]
    for start, end in runs:
        covering: list[int] = []
        for index in range(start, end):
            if reading.text[index].isspace():
                continue
            at = next((n for n, (mine, _) in enumerate(pairs) if mine.start <= index < mine.end), None)
            if at is None:
                return False
            if at not in covering:
                covering.append(at)
        theirs = [pairs[n][1].text for n in covering]
        if not all(part.strip() for part in theirs):
            return False
        counterpart = " ".join(theirs)
        if place_name(counterpart) == place_name(text) or one_letter_apart(text, counterpart):
            return False
        if not any(verbatim_runs(held, counterpart) for held in theirs_elsewhere):
            return False
    return True


def set_aside(text: str, readings: Sequence[Reading], claimed: Mapping[str, Iterable[str]]) -> bool:
    """Whether a place text stands on no reading that may settle a field: some
    reading writes it as whole words (verbatim_runs), and every reading that
    does writes it only as a possibility nothing backs (only_a_possibility)
    or as text its label's readers dispute (disputed, with `claimed`, each
    reading's texts for the other fields). Such a text never holds back a country that the record's
    settled places derive (step._country_alternatives_are_lower_places).
    Only that check reads it: everywhere else it is still its label's text
    (labels)."""
    writers = [reading for reading in readings if verbatim_runs(reading.text, text)]
    return bool(writers) and all(only_a_possibility(text, reading, readings)
        or disputed(text, reading, readings, claimed) for reading in writers)


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


# How a label settled (Label.basis): its readers agree; a source confirms
# one reader's text by its own name (or its expansion), or, for a place, by
# a near spelling, or every reader's text as one place (N4); another label
# whose readers agree writes one reader's text; or the first pass's
# preferred reading, when nothing backs another reader's text.
BY_AGREEMENT, BY_SOURCE, BY_NEAR_SPELLING, BY_SAME_PLACE, BY_OTHER_LABEL, BY_FIRST_PASS = (
    "readers_agree", "source", "near_spelling", "same_place", "other_label", "first_pass")
# The least number of readers (distinct readings with text) of a label whose
# agreement backs another label's reader: a label one reader read backs
# nothing (the coordinator's decision of 2026-10-25 on #414's review).
MIN_BACKING_READERS = 2
# Whether a label whose readers differ settled on the text of the reader its
# first pass preferred (Label.preference): followed, overridden, or no
# preference to follow (no first pass, or one that preferred no reader); or
# CONFLICT: the first pass's verdict at that difference names its preferred
# reader, and only another label or a near spelling backs another reader's
# text, so the label does not settle and a person decides.
FOLLOWED, OVERRIDDEN, ABSENT, CONFLICT = "followed", "overridden", "absent", "conflict"
# The units path (FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md section 4, the rule): a label a
# person transcribed settles on the person's text (rule 2), and a candidate's backings are of
# three kinds (rule 3), ranked in a conflict SOURCE above IMAGE above TEXT (rule 5).
BY_PERSON, BY_IMAGE = "person", "image"
IMAGE, SOURCE, TEXT = "image", "source", "text"
STRENGTH = {SOURCE: 3, IMAGE: 2, TEXT: 1}
# Why a settled value is marked for a person (the finding marked:<field>:<label>:<why>): only
# TEXT backs it (rule 4), or another candidate has a backing too (rule 5).
TEXT_ONLY, CONTESTED = "text_only", "conflict"


@dataclass(frozen=True)
class Backed:
    """One candidate of a label on the units path (rule 1): its texts, collapsed, the
    backings it has (rule 3), how many readers of the label write it and the place of
    the first of them in the label's reading order."""

    texts: frozenset[str]
    backings: frozenset[str]
    readers: int
    first: int


@dataclass(frozen=True)
class Label:
    """One label that writes the field: its readings' literals, and the
    literals it settles to: one, or, for readers a source confirms as one
    place, each of theirs (N4); none when it does not settle."""

    literals: frozenset[str]
    settled: frozenset[str] = frozenset()
    # A source settled readers that differ (G20, N4), rather than readers
    # that agree, another label or the first pass's preferred reading.
    by_source: bool = False
    # Readers of a label the answer's text from the transcript is read on
    # that write it nowhere, letter case and spacing aside, and have no text
    # the organiser found: what they write for the field is unknown.
    unread: frozenset[str] = frozenset()
    # Its readers write the answer's text from the transcript, but different
    # text around it in the clause that holds it (holding_clauses).
    around: bool = False
    # How it settled (BY_AGREEMENT and the others); None when it did not.
    basis: str | None = None
    # For a settled label whose readers differ: whether it settled on the
    # text of the reader its first pass preferred (FOLLOWED, OVERRIDDEN,
    # ABSENT); CONFLICT for a label that does not settle because only weaker
    # backing opposes an image-confirmed pick; None for readers that agree or
    # a label that did not settle otherwise.
    preference: str | None = None
    # The reading that holds the label's transcript a person decided
    # (FirstPassAdvice.person_decided), which binds its text; None otherwise.
    person: str | None = None
    # For a label settled on its preferred reader's spelling through another
    # reader's text one letter from it, which a source confirms by its own
    # name (_preferred_spelling): that text and the readers that write it.
    matched: str | None = None
    matched_by: tuple[str, ...] = ()
    # The units path (labels_by_rule). Its candidates with their backings; for a settled
    # label, whether it is cleared (rule 4: an IMAGE or a SOURCE backing, or a person's
    # text) and else why it is marked (TEXT_ONLY, CONTESTED); for a marked conflict, the
    # other backed candidates' texts; for two or more candidates that only TEXT backs, or
    # that tie on rule 5's rank, their texts, the options a person chooses from.
    candidates: tuple[Backed, ...] = ()
    cleared: bool = False
    why: str | None = None
    others: tuple[str, ...] = ()
    options: tuple[str, ...] = ()
    # The options are candidates that tie on rule 5's rank (labels_by_rule).
    tied: bool = False
    # The units path: texts readers write at a candidate's place that are no candidate
    # (_label_texts); a source settles the label only when it rules each of them out.
    blocked: tuple[str, ...] = ()
    # The units path: how many of the label's readers have a candidate.
    writing: int = 0


def _places(text: str, literal: str) -> list[tuple[int, int]]:
    """Where the text writes the (collapsed) literal as whole words, any run
    of whitespace standing for each of its spaces, as (start, end) offsets:
    it starts and ends at word edges of its lines as verbatim_runs reads
    them (_edges), so "la" is no place of "Guatemala" (round 2 of #414's
    review)."""
    words = literal.split()
    if not words:
        return []
    pattern = re.compile(r"\s+".join(re.escape(word) for word in words))
    found = []
    for match in pattern.finditer(text):
        start, end = match.span()
        first_at, first = _line_of(text, start, start)
        last_at, last = _line_of(text, end, end)
        if start - first_at in _edges(first)[0] and end - last_at in _edges(last)[1]:
            found.append((start, end))
    return found


def _confirms(difference: Mapping, preferred: str) -> bool:
    """Whether a first pass difference's verdict confirms the preferred
    reader there: it names that reader, or a reader whose text there is the
    preferred reader's, letter case aside (application.first_pass.supports)."""
    verdict, texts = difference.get("verdict"), difference.get("texts", {})
    return verdict == preferred or (verdict in texts and preferred in texts
        and texts[verdict].lower() == texts[preferred].lower())


def confirmed_against_image(preferred: Reading, readers: Sequence[Reading], text: str,
        literals: Mapping[str, Iterable[str]]) -> bool:
    """Whether the first pass judged the label's image where another reader
    writes `text` and found its preferred reader's text there: a material
    difference of the label's first pass (Reading.first_pass) whose span in
    one of `readers` (the other readers whose texts for the field, in
    `literals`, are `text`, letter case and spacing aside) overlaps a place
    where that reader writes it (an empty span: one at or inside it), and
    whose verdict confirms the preferred reader (_confirms). No first pass,
    no difference there, or a verdict of neither or uncertain: not confirmed
    (the coordinator's decision of 2026-10-25 on #414's review). A label
    whose transcript a person decided never gets here: labels holds it to
    the person's text."""
    advice = preferred.first_pass
    if advice is None:
        return False
    want = agreement_key(text)
    for reader in readers:
        if reader is preferred:
            continue
        written = [own for own in literals.get(reader.name, ()) if agreement_key(own) == want]
        places = [place for own in written for place in _places(reader.text, own)]
        for difference in advice.differences:
            span = difference.get("spans", {}).get(reader.name)
            if span is None or not _confirms(difference, preferred.name):
                continue
            start, end = span
            if any((start < stop and at < end) if start < end else at <= start <= stop for at, stop in places):
                return True
    return False


def _preference(settled: frozenset[str], preferred: Reading | None, mine: frozenset[str]) -> str:
    """Whether a label whose readers differ settled on its preferred reader's
    text (Label.preference): FOLLOWED when one of the texts it settled on is
    that reader's, letter case and spacing aside; OVERRIDDEN when none is;
    ABSENT when the first pass preferred no reader of it."""
    if preferred is None:
        return ABSENT
    keys = {agreement_key(text) for text in mine}
    return FOLLOWED if any(agreement_key(text) in keys for text in settled) else OVERRIDDEN


def _preferred_spelling(task: FieldTask, preferred: Reading | None, group: Sequence[Reading],
        mine: frozenset[str], confirmed: str, literals: Mapping[str, Iterable[str]]) -> str | None:
    """For a place value field, the preferred reader's text that a source's
    exact confirmation of another reader's text corrects rather than
    overrides, or None: the preferred reader has exactly one text one letter
    from the confirmed one (application.georef_locality.one_letter_apart),
    and the first pass confirmed its preferred reader against the image where
    the other reader writes the confirmed text (confirmed_against_image). The
    label then writes the preferred reader's spelling, and the confirmed name
    is its value through a near spelling (t1-329's province: the preferred
    "Chimaltenago" beside the other reader's "Chimaltenango"; the
    coordinator's ruling of 2026-10-25 after the real-run measurement)."""
    if task.key not in PLACE_VALUE_FIELDS or preferred is None:
        return None
    near = [text for text in mine if one_letter_apart(text, confirmed)]
    if len(near) != 1 or not confirmed_against_image(preferred, group, confirmed, literals):
        return None
    return near[0]


def labels(task: FieldTask, readings: Sequence[Reading], answers: Sequence[SourceAnswer], *,
        transcript: str | None = None, named: Sequence[Reading] = (), offered: Iterable[str] = ()) -> dict[str, Label]:
    """Each label that writes the field, by region, settled on its own
    (G19, G20, G27, G32), on its own evidence first, then on another label's,
    then on the first pass's advice (the owner, 2026-10-25: "There an LLM
    opinion that's put in front along with actual Raw transcription per
    model to the harness if needed as then harness does its thing per field
    and settles as written or derived and so on"):
    - a label whose readers each write the same text, letter case and
      spacing aside (agreement_key: "shrubs" and "Shrubs", "sp. 30" and
      "Sp.30"), on the spelling (_spelling) of the reader its first pass
      preferred, else of its first reader (BY_AGREEMENT);
    - a label whose readers differ (or where one writes nothing), through
      the field's approved sources (`answers`): exactly one of its literals
      is confirmed by its own name or expansion (identities), and every other
      is ruled out (ruled_out, or, for a place value field,
      found_only_elsewhere), whichever reader the first pass preferred
      (BY_SOURCE); or, for a place none of whose texts is confirmed so, one is
      a near spelling of the one candidate at the field's level of an answer
      asked that candidate's name, every other ruled out (_by_source,
      BY_NEAR_SPELLING); or, for a place value field, every one of its literals is
      confirmed and one authority_id confirms them all, so its readers name
      the same place ("Yepocapa," and "Yepocapa"; N4 of #284's third
      review). That settles on the source's evidence, each literal matching
      the candidate's name by the place comparison key (case, accents,
      punctuation, unit words), and on each of the literals: the answer
      gives one of them, with that authority_id (BY_SAME_PLACE);
    - else, a label whose readers differ, on the one text of its readers
      (letter case and spacing aside) that another label of the specimen,
      whose MIN_BACKING_READERS or more readers agree on it (BY_AGREEMENT),
      settled on (BY_OTHER_LABEL);
    - else, a label whose first pass preferred a reader (the reading whose
      input_source is decided_transcript), on the one candidate literal
      that reader has, or, when it has several texts for the field, through
      the field's approved sources as above, on one of its candidate
      literals (48a71d53's "Davao Prov." beside "Mindanao,") (BY_FIRST_PASS).
      A label whose preferred reader writes nothing for the field takes no
      part, unless the answer names one of its readers (`named`): then it
      settles only on a source, a near spelling or another label, as above;
    - any other label does not settle.
    A label whose transcript a person decided (FirstPassAdvice.person_decided)
    is bound to that reading: it settles only on readers that agree or on the
    person's text (BY_FIRST_PASS), never on another reader's, whatever the
    sources say, as the person saw the image (the coordinator's ruling of
    2026-10-25); lookups still work on the person's text.
    A source's exact confirmation (BY_SOURCE) settles against the first
    pass's preference anywhere, except that a place whose preferred reader
    writes a text one letter from the confirmed one, where the first pass
    confirmed it, keeps the preferred reader's spelling as its literal, the
    confirmed name its value through a near spelling (_preferred_spelling;
    BY_NEAR_SPELLING, FOLLOWED, Label.matched). A near spelling or another label settles
    against it too, except where the first pass judged the image at that
    difference and found its preferred reader's text there
    (confirmed_against_image): then the label does not settle either way,
    and its preference is CONFLICT (the coordinator's decision of 2026-10-25
    on #414's review, citing the owner's design of 2026-10-03: a field where
    several possibilities remain for the user to choose from is unresolved).
    A settled label whose readers differ says whether it followed the first
    pass's preference (Label.preference).

    `transcript` is the answer's literal when it is read from the transcript
    (TRANSCRIPT), and `named` the readings it names. On each of their labels,
    every reader then also writes the runs of whole words within one line
    that are that text, letter case and spacing aside (agreeing_runs), as it
    writes them, and a reading that writes it exactly has it as a
    candidate. A reader of such a label (one its first pass preferred no
    reader of) that writes it nowhere and has no text the organiser found
    for the field is unread: what it writes is unknown, so no lookup can
    have covered it, and the label does not settle. Nor does such a label
    when its readers' clauses holding the text (holding_clauses: the comma-
    or semicolon-separated part of the line around it, else the whole line)
    differ beyond letter case and spacing: 1A's "trap" beside 1B's "light
    trap", or "IV-24-48" beside "IV-24-48 to V-2-48" (Label.around). On a
    label whose first pass preferred a reader, such readers only differ."""
    if any(reading.units is not None for reading in readings):
        # The units path: the transcript's text, and any `offered`, is offered to every
        # label whichever readings the answer names (labels_by_rule).
        return _labels_on_units(task, readings, answers, transcript=transcript, offered=offered)
    literals = reader_literals(task, readings)
    allowed = candidates_by_reading(task, readings)
    sourced = bool(frozenset(task.tools) & SOURCE_IDS)
    read_on = frozenset(reading.region_id for reading in named) if transcript is not None else frozenset()
    answered = frozenset(reading.region_id for reading in named)
    # A literal over consecutive lines (ACROSS_LINES): each reader's runs of it.
    across = transcript is not None and task.key in ACROSS_LINES and "\n" in transcript
    spans_of: dict[str, list[tuple[int, int]]] = {}
    regions: dict[str, list[Reading]] = {}
    for reading in readings:
        regions.setdefault(reading.region_id, []).append(reading)
        if reading.region_id in read_on:
            if across:
                spans_of[reading.name] = _agreeing_spans_across(reading.text, transcript)
                runs = [reading.text[start:end] for start, end in spans_of[reading.name]]
            else:
                runs = agreeing_runs(reading.text, transcript)
            if runs:
                literals.setdefault(reading.name, set()).update(collapse(run) for run in runs)
            if written_runs(task.key, reading.text, transcript):
                allowed.setdefault(reading.name, {}).setdefault(collapse(transcript), transcript)
    if across:
        # The texts a reader's run of the literal holds wholly are parts of it
        # (the organiser's "Seliban Riv." and "Mt. Apo" of 2b02009d's two
        # lines), not rival texts of the field.
        by_name = {reading.name: reading for reading in readings}
        whole = collapse(transcript)
        for name, spans in spans_of.items():
            if spans and name in literals:
                literals[name] = {text for text in literals[name]
                    if text == whole or not _within_runs(by_name[name].text, text, spans)}
    found: dict[str, Label] = {}
    # Labels whose readers differ and that settled on no evidence of their own.
    waiting: dict[str, tuple[frozenset[str], Reading | None, frozenset[str]]] = {}
    for region, group in regions.items():
        preferred = next((r for r in group if r.input_source == DECIDED), None)
        mine = frozenset(literals.get(preferred.name, ())) if preferred is not None else frozenset()
        bound = preferred is not None and preferred.first_pass is not None and preferred.first_pass.person_decided
        each = [frozenset(literals.get(r.name, ())) for r in group]
        texts = frozenset().union(*each)
        if not texts or (preferred is not None and not mine and region not in answered):
            # A label whose preferred reader writes nothing for the field
            # takes no part, unless the answer names one of its readers.
            continue
        differ = False
        if region in read_on:
            unread = frozenset(r.name for r, own in zip(group, each) if not own)
            if unread and preferred is None:
                found[region] = Label(texts, unread=unread)
                continue
            # Each reader's clauses holding the text agree, letter case and
            # spacing aside, or the readers write different text around it
            # ("trap" and "light trap", "Yepocapa" and "near Yepocapa").
            held = {r.name: (list(dict.fromkeys(_holding_across(r.text, start, end)
                for start, end in spans_of.get(r.name, ()))) if across else holding_clauses(r.text, transcript))
                for r in group}
            keys = {frozenset(agreement_key(clause) for clause in clauses) for clauses in held.values() if clauses}
            if len(keys) > 1:
                if preferred is None:
                    found[region] = Label(texts | frozenset(collapse(clause) for clauses in held.values()
                        for clause in clauses), around=True)
                    continue
                differ = True
        if not differ and all(each) and len({agreement_key(text) for text in texts}) == 1:
            # Every reader writes it, at most letter case or spacing apart
            # ("shrubs" and "Shrubs", "sp. 30" and "Sp.30"): they agree, on
            # the preferred reader's spelling, else the first reader's.
            speller, own = (preferred, mine) if preferred is not None and mine else (group[0], each[0])
            found[region] = Label(texts, frozenset({_spelling(task, speller.name, own)}), basis=BY_AGREEMENT)
            continue
        if bound:
            # A person's transcript: no other reader's text overrides it.
            waiting[region] = (texts, preferred, mine)
            continue
        confirmed = {text: identities(answers, text, task.key) for text in texts} if sourced else {}
        if sourced and (label := _by_source(task, texts, texts, answers)) is not None:
            preference = _preference(label.settled, preferred, mine)
            [one] = label.settled
            spelled = (_preferred_spelling(task, preferred, group, mine, one, literals)
                if label.basis == BY_SOURCE and preference == OVERRIDDEN else None)
            if spelled is not None:
                found[region] = Label(texts, frozenset({spelled}), by_source=True, basis=BY_NEAR_SPELLING,
                    preference=FOLLOWED, matched=one, matched_by=tuple(r.name for r in group if r is not preferred
                        and any(agreement_key(text) == agreement_key(one) for text in literals.get(r.name, ()))))
            elif (label.basis == BY_NEAR_SPELLING and preference == OVERRIDDEN
                    and confirmed_against_image(preferred, group, one, literals)):
                found[region] = Label(texts, preference=CONFLICT)
            else:
                found[region] = Label(texts, label.settled, by_source=True, basis=label.basis,
                    preference=preference)
        elif (task.key in PLACE_VALUE_FIELDS and confirmed and all(confirmed.values())
                and frozenset.intersection(*(frozenset(ids) for ids in confirmed.values()))):
            found[region] = Label(texts, texts, by_source=True, basis=BY_SAME_PLACE,
                preference=_preference(texts, preferred, mine))
        else:
            waiting[region] = (texts, preferred, mine)
    # Another label backs a reader's text: its MIN_BACKING_READERS or more
    # readers agree on it, letter case and spacing aside.
    written = {agreement_key(text) for region, label in found.items() if label.basis == BY_AGREEMENT
        and len({r.observation_id for r in regions[region]}) >= MIN_BACKING_READERS for text in label.settled}
    for region, (texts, preferred, mine) in waiting.items():
        bound = preferred is not None and preferred.first_pass is not None and preferred.first_pass.person_decided
        backed = frozenset() if bound else frozenset(text for text in texts if agreement_key(text) in written)
        if backed and len({agreement_key(text) for text in backed}) == 1:
            preference = _preference(backed, preferred, mine)
            if preference == OVERRIDDEN and confirmed_against_image(preferred, regions[region], next(iter(backed)),
                    literals):
                found[region] = Label(texts, preference=CONFLICT)
            else:
                found[region] = Label(texts, backed, basis=BY_OTHER_LABEL, preference=preference)
        elif mine:
            own = set(allowed.get(preferred.name, {}))
            label = _by_source(task, mine & own, mine, answers) if len(mine) > 1 and sourced else None
            settled = label.settled if label is not None else (mine if len(mine) == 1 and mine <= own
                else frozenset())
            found[region] = Label(texts, settled, by_source=label is not None,
                basis=BY_FIRST_PASS if settled else None, preference=FOLLOWED if settled else None,
                person=preferred.name if bound else None)
        else:
            found[region] = Label(texts, person=preferred.name if bound else None)
    return found


def _by_source(task: FieldTask, choices: frozenset[str], texts: frozenset[str],
        answers: Sequence[SourceAnswer]) -> Label | None:
    """A label settled through the field's approved sources on the one of its
    `texts` they confirm (identities), when that one is among `choices` and
    every other is ruled out (ruled_out, or, for a place value field,
    found_only_elsewhere); None otherwise. Only when they confirm none of
    them by its own name may a place's near spelling confirm one (identities'
    `near`): a text one letter from the one candidate at the field's level
    of an answer asked that candidate's name, every other text still ruled
    out, so a reader's exact name and another's near spelling of it never
    both count, and a text no source was asked about is never ruled out
    (its basis is then BY_NEAR_SPELLING, else BY_SOURCE)."""
    basis = BY_SOURCE
    ones = frozenset(text for text in texts if identities(answers, text, task.key))
    if not ones:
        basis = BY_NEAR_SPELLING
        ones = frozenset(text for text in texts if identities(answers, text, task.key, near=True))
    if len(ones) == 1 and ones <= choices and all(ruled_out(answers, text)
            or found_only_elsewhere(answers, text, task.key) for text in texts - ones):
        return Label(texts, ones, by_source=True, basis=basis)
    return None


# ---- the units path: how a literal maps to the units that cover it, and the rule ----

@lru_cache(maxsize=4096)
def _normal(text: str) -> tuple[str, dict[int, int] | None]:
    """The text in NFC (as collapse gives a literal) and, when that changes it, the map
    from each offset of the NFC text where a normalisation segment starts or ends to the
    text's own offset there; None when NFC keeps the text. A segment ends before each
    character of canonical combining class 0 that composes with nothing before it (the
    NFC of the segment so far and the character is the two NFCs joined), so the text's
    NFC is its segments' NFCs joined, and an offset inside a segment ("e" and a combining
    accent; a Hangul syllable's jamo) has no place in the text."""
    normal = unicodedata.normalize("NFC", text)
    if normal == text:
        return text, None
    offsets, start, length = {0: 0}, 0, 0
    for index in range(1, len(text) + 1):
        if index < len(text):
            segment = unicodedata.normalize("NFC", text[start:index])
            char = text[index]
            if unicodedata.combining(char) or unicodedata.normalize("NFC", text[start:index + 1]) != (
                    segment + unicodedata.normalize("NFC", char)):
                continue
        length += len(unicodedata.normalize("NFC", text[start:index]))
        offsets[length] = index
        start = index
    if length != len(normal):
        return normal, {0: 0, len(normal): len(text)}
    return normal, offsets


def literal_places(text: str, literal: str, *, inside: bool | None = None) -> list[tuple[int, int]]:
    """Where a reading writes the literal, as (start, end) code-point offsets into the
    reading, any run of white space standing for each of its spaces, both compared in NFC
    (a literal is collapsed, so in NFC, where "e" and a combining acute accent are one
    character): the places where it stands as whole words (_places), else every place it
    stands, inside a word too ("6400" of "Elev.6400", "Yepocapa" of "Yepocapa,4800"). A
    place starts and ends at no combining mark, except at the reading's ends (_normal's
    segments; "x" is not written in "x" with an acute accent), and the whole-word places
    that pass that filter come first: when none does, the places inside a word that pass
    it (`inside` False or True gives one kind alone). Empty when it writes it nowhere."""
    words = unicodedata.normalize("NFC", literal).split()
    if not words:
        return []
    normal, offsets = _normal(text)
    pattern = re.compile(r"\s+".join(re.escape(word) for word in words))

    def kept(found: list[tuple[int, int]]) -> list[tuple[int, int]]:
        if offsets is not None:
            found = [(offsets[start], offsets[end]) for start, end in found if start in offsets and end in offsets]
        return [(start, end) for start, end in found
            if all(at in (0, len(text)) or not unicodedata.combining(text[at]) for at in (start, end))]

    whole = [] if inside else kept(_places(normal, " ".join(words)))
    if whole or inside is False:
        return whole
    return kept([match.span() for match in pattern.finditer(normal)])


def covering_units(reading: Reading, literal: str) -> list[list]:
    """For each place of the literal in the reading (literal_places), the units of its
    label whose span for that reading overlaps the place, in reading order: one unit for
    a literal that is a unit or a part of one, several for one that runs over units. Empty
    when the reading's label has no units, the units do not name the reading, or the
    reading writes the literal nowhere."""
    return [cover for _, cover in _covered(reading, literal)]


def _covered(reading: Reading, literal: str) -> list[tuple[tuple[int, int], list]]:
    """Each place of the literal in the reading with the units covering it (covering_units)."""
    units = reading.units
    if units is None or reading.observation_id not in units.units[0].readers:
        return []
    key = reading.observation_id
    return [((start, end), [unit for unit in units.units
        if unit.readers[key].start < end and start < unit.readers[key].end])
        for start, end in literal_places(reading.text, literal)]


def _differs(unit) -> bool:
    """Whether the label's readers do not all write the same text at the unit, letter case
    and spacing aside: one wrote text and another nothing, or two wrote different texts."""
    return len({agreement_key(span.text) for span in unit.readers.values()}) > 1


def image_names(reading: Reading, literal: str, *, exact: bool = False) -> bool:
    """Whether the first pass names this reading's text at the literal (rule 3's IMAGE):
    at every place the reading writes it, every covering unit's image is the reading's own
    text there, letter case and spacing aside (agreement_key), or character for character
    with `exact`; and every unit next to the covering units, outward from each end, while
    the label's readers do not all write the same text there (_differs), is judged not
    visible, so a text another reader writes beside it ("megalippe" after "Danaus
    plexippus"), or a text the readers write differently there ("cloud" and "rain" before
    "forest"), is not on the label. A unit the readers write alike bounds nothing. A unit
    whose image is uncertain, or another reader's different text, names nothing for it.
    The units' fields advice takes no part."""
    from specimen_digitization.application.reading_units import NOT_VISIBLE, UNCERTAIN

    places = covering_units(reading, literal)
    if not places or not all(places):
        return False
    units = reading.units.units
    key = reading.observation_id
    for cover in places:
        for unit in cover:
            own = unit.readers[key].text
            if unit.image in (UNCERTAIN, NOT_VISIBLE) or (
                    unit.image != own if exact else agreement_key(unit.image) != agreement_key(own)):
                return False
        first, last = units.index(cover[0]), units.index(cover[-1])
        for step, at in ((-1, first - 1), (1, last + 1)):
            while 0 <= at < len(units) and _differs(units[at]):
                if units[at].image != NOT_VISIBLE:
                    return False
                at += step
    return True


def _key_offset(text: str, key: str) -> int | None:
    """The least offset j of the text whose prefix text[:j] has the agreement key `key`."""
    return next((j for j in range(len(text) + 1) if agreement_key(text[:j]) == key), None)


def _span(reading: Reading, cover: list) -> tuple[int, int]:
    """The reading's offsets over consecutive units, from the first's start to the last's end."""
    key = reading.observation_id
    return cover[0].readers[key].start, cover[-1].readers[key].end


def _label_texts(group: Sequence[Reading], offered: Iterable[str]
        ) -> tuple[list[frozenset[str]], tuple[str, ...], dict[str, frozenset[str]]]:
    """Each reader's candidates for the field, the texts readers write at their places that
    are no candidate, and, by agreement key, the readers that agree on a candidate. A
    literal offered for the label (`offered`: its readers' organiser literals and the
    expert's literal) is a candidate of each reader in whose own text it is found
    (literal_places; inside a word only where no reader of the label writes it as whole
    words), in that reader's spelling there; and of each reader whose text over
    the covering units of one of those places is that reader's, letter case and spacing
    aside, in its own spelling, through the agreement key's offsets. The readers that agree
    on a candidate are, at the place where most do, its reader and those whose text over
    its covering units is the same and into whose text the candidate maps through those
    offsets ("s" of "s s" maps into no part of "\u00df"). A reader that writes another text over those units
    agrees with nothing there, and when none of its own candidates lies in its text there,
    it has that text at the place: no part of it is cut out of the unit as a candidate."""
    offered = [text for text in dict.fromkeys(collapse(text) for text in offered) if text]
    found: list[set[str]] = [set() for _ in group]
    for literal in offered:
        # Inside a word only where no reader of the label writes it as whole words.
        inside = not any(literal_places(reading.text, literal, inside=False) for reading in group)
        for index, reading in enumerate(group):
            found[index].update(collapse(reading.text[start:end])
                for start, end in literal_places(reading.text, literal, inside=inside))

    def over(other: Reading, cover: list) -> str | None:
        if other.observation_id not in cover[0].readers:
            return None
        low, high = _span(other, cover)
        return other.text[low:high]

    own = [frozenset(texts) for texts in found]
    for index, reading in enumerate(group):
        for text in own[index]:
            for (start, end), cover in _covered(reading, text):
                low, _ = _span(reading, cover)
                mine = over(reading, cover)
                for other_index, other in enumerate(group):
                    theirs = over(other, cover) if other is not reading else None
                    if not theirs or not theirs.strip() or agreement_key(theirs) != agreement_key(mine):
                        continue
                    first = _key_offset(theirs, agreement_key(reading.text[low:start]))
                    last = _key_offset(theirs, agreement_key(reading.text[low:end]))
                    if first is not None and last is not None and first < last:
                        found[other_index].add(collapse(theirs[first:last]))
    blocked: list[str] = []
    agreeing: dict[str, frozenset[str]] = {}
    for index, reading in enumerate(group):
        for text in found[index]:
            best = frozenset({reading.observation_id})
            for (start, end), cover in _covered(reading, text):
                low, _ = _span(reading, cover)
                mine = over(reading, cover)
                same = {reading.observation_id}
                for other_index, other in enumerate(group):
                    theirs = over(other, cover) if other is not reading else None
                    if not theirs or not theirs.strip():
                        continue
                    if agreement_key(theirs) == agreement_key(mine):
                        first = _key_offset(theirs, agreement_key(reading.text[low:start]))
                        last = _key_offset(theirs, agreement_key(reading.text[low:end]))
                        if first is not None and last is not None and first < last:
                            same.add(other.observation_id)
                        continue
                    their_low, their_high = _span(other, cover)
                    if not any(start < their_high and their_low < end for one in found[other_index]
                            for start, end in literal_places(other.text, one)):
                        blocked.append(collapse(theirs))
                if len(same) > len(best):
                    best = frozenset(same)
            key = agreement_key(text)
            if len(best) > len(agreeing.get(key, ())):
                agreeing[key] = best
    return [frozenset(texts) for texts in found], tuple(dict.fromkeys(blocked)), agreeing


def _nested(group: Sequence[Reading], each: Sequence[frozenset[str]], inner: frozenset[str],
        outer: frozenset[str]) -> bool:
    """Whether a candidate (`inner`, its texts) lies inside another (`outer`) at every place a
    reader writes it: each place lies over units within those of a place of the other's,
    in any reader of the label, whose text holds it (agreement_key), and in the same reader
    within that place (an organiser's line inside the expert's two-line locality; 1B's
    "Mt. McKinley" under 1A's "E Slope Mt. McKinley"). One place of it outside the other
    ("forest" on a line of its own below "dry forest") keeps it a rival."""
    containers = [(reading, agreement_key(one), (low, high), frozenset(unit.id for unit in cover))
        for reading, own in zip(group, each) for one in own & outer for (low, high), cover in _covered(reading, one)]
    found = False
    for reading, own in zip(group, each):
        for text in own & inner:
            key = agreement_key(text)
            for (start, end), cover in _covered(reading, text):
                ids = frozenset(unit.id for unit in cover)
                if not any(key != theirs and key in theirs and ids <= units and (other is not reading
                        or (low <= start and end <= high)) for other, theirs, (low, high), units in containers):
                    return False
                found = True
    return found


def _within(reading: Reading, text: str, texts: Iterable[str]) -> bool:
    """Whether every place the reading writes `text` lies inside a place of another of
    `texts` in it."""
    places = literal_places(reading.text, text)
    return bool(places) and all(any(low <= start and end <= high and (low, high) != (start, end)
        for one in texts if one != text for low, high in literal_places(reading.text, one)) for start, end in places)


def _spelled(task: FieldTask, group: Sequence[Reading], each: Sequence[frozenset[str]], keys: frozenset[str],
        confirmed: frozenset[str] = frozenset()) -> str:
    """The text a candidate (its agreement keys) settles on: the text the image names, of
    the first reader that writes it so; else the first reader's text of `confirmed` (the
    texts a source confirms); else the first reader's spelling (_spelling)."""
    for reading, own in zip(group, each):
        for text in sorted(own):
            if agreement_key(text) in keys and image_names(reading, text, exact=True):
                return text
    for reading, own in zip(group, each):
        for text in sorted(own):
            if agreement_key(text) in keys and text in confirmed:
                return text
    reading, own = next((reading, own) for reading, own in zip(group, each)
        if any(agreement_key(text) in keys for text in own))
    return _spelling(task, reading.name, {text for text in own if agreement_key(text) in keys})


def _confirmed_group(task: FieldTask, groups: Sequence[frozenset[str]], answers: Sequence[SourceAnswer],
        others: Iterable[str] = ()) -> tuple[frozenset[str] | None, str | None]:
    """_by_source over candidates (rule 1's groups of texts by agreement_key): the one group
    a source confirms by its own name or expansion (identities), every text of every other
    group ruled out (ruled_out, or for a place value field found_only_elsewhere), with
    BY_SOURCE; else, when no group is so confirmed, the one group with a near spelling of a
    source's one candidate, every other ruled out, with BY_NEAR_SPELLING; else (None, None).
    `others` (Label.blocked) must each be ruled out too."""
    for near, basis in ((False, BY_SOURCE), (True, BY_NEAR_SPELLING)):
        ones = [group for group in groups if any(identities(answers, text, task.key, near=near) for text in group)]
        if ones:
            break
    if len(ones) == 1 and all(ruled_out(answers, text) or found_only_elsewhere(answers, text, task.key)
            for text in [*(text for group in groups if group != ones[0] for text in group), *others]):
        return ones[0], basis
    return None, None


def _labels_on_units(task: FieldTask, readings: Sequence[Reading], answers: Sequence[SourceAnswer], *,
        transcript: str | None, offered: Iterable[str]) -> dict[str, Label]:
    """`labels` on the units path: each label's readings, the organiser's literals and the
    texts offered to every label (the expert's literal read from the transcript, and
    `offered`), for labels_by_rule."""
    regions: dict[str, list[Reading]] = {}
    for reading in readings:
        regions.setdefault(reading.region_id, []).append(reading)
    allowed = candidates_by_reading(task, readings)
    extra = tuple(text for text in ((transcript,) if transcript else ()) + tuple(offered) if text and text.strip())
    if transcript:
        for reading in readings:
            if written_runs(task.key, reading.text, transcript):
                allowed.setdefault(reading.name, {}).setdefault(collapse(transcript), transcript)
    return labels_by_rule(task, regions, reader_literals(task, readings), allowed, answers,
        sourced=bool(frozenset(task.tools) & SOURCE_IDS), offered=extra)


def labels_by_rule(task: FieldTask, regions: Mapping[str, Sequence[Reading]],
        literals: Mapping[str, Iterable[str]], allowed: Mapping[str, Mapping[str, str]],
        answers: Sequence[SourceAnswer], *, sourced: bool, offered: Sequence[str] = ()) -> dict[str, Label]:
    """`labels` on the units path: each label that writes the field, settled by the rule of
    FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md section 4.

    1. The candidates are the readers' texts for the field (_label_texts): each literal
       offered for the label (its readers' candidates and verbatims, and `offered`, the
       expert's literal, whichever readings the answer names) found in a reader's own text,
       and in another reader's whose text over the units there is the same, letter case and
       spacing aside; a reader that writes another text there agrees with none of them, and
       one with no candidate in its text there has that text at the place (Label.blocked),
       which a source must rule out before it backs any candidate.
       They are grouped by agreement_key. For a place value field, the groups a source confirms as
       one authority, every text of the label confirmed (BY_SAME_PLACE's condition), are one
       candidate; so are the group a source confirms by its own name, every other ruled out
       (_confirmed_group, BY_SOURCE), and the one other group one letter from it
       (one_letter_apart).
    2. A label whose transcript a person decided (FirstPassAdvice.person_decided) settles
       on the person's text as `labels` settles it, cleared (BY_PERSON), a text of it
       inside another of it set aside (_within); a label whose person's reading writes
       nothing for the field takes no part.
    3. A candidate's backings: IMAGE, the first pass names one of its texts where a reader
       writes it (image_names); SOURCE, _confirmed_group gives it, or it is a merged
       candidate of point 1; TEXT, MIN_BACKING_READERS or more readers of the label agree on
       it at one place (_label_texts), or another label has that many readers agreeing on it.
    4. Exactly one candidate has a backing: it settles, cleared with an IMAGE or a SOURCE
       backing, else marked (TEXT_ONLY). A candidate settles on the text the image names
       (_spelled), else, for one a source confirms, on the confirmed text, else the first
       reader's; a same-place candidate the image names no single text of settles on each.
    5. Several have (a candidate inside a backed one at the same place, _nested, is no
       rival of it at those places and takes no part): with an IMAGE or a SOURCE backing among them, the best-backed settles
       (SOURCE above IMAGE above TEXT, then more readers, then the earlier reader), marked
       (CONTESTED), the others listed in Label.others; when two or more rank first alike
       (the same first reader too), the label does not settle and their texts are its
       options (Label.tied); with no IMAGE or SOURCE backing among them, the label does not
       settle, and the backed candidates' texts are its options.
    6. None has: the label does not settle."""
    found: dict[str, Label] = {}
    prepared = {}
    agreed: dict[str, frozenset[str]] = {}
    for region, group in regions.items():
        preferred = next((r for r in group if r.input_source == DECIDED), None)
        bound = preferred is not None and preferred.first_pass is not None and preferred.first_pass.person_decided
        writers: dict[str, set[str]] = {}
        if bound:
            # Offered text as the field writes it (written_runs: over consecutive lines for a
            # precise location), and the person's texts inside another of them set aside.
            each, blocked = [frozenset(set(literals.get(reading.name, ())) | {collapse(reading.text[start:end])
                for text in offered for start, end in written_runs(task.key, reading.text, text)})
                for reading in group], ()
            each = [frozenset(text for text in own if not _within(reading, text, own)) for reading, own in zip(group, each)]
            for reading, own in zip(group, each):
                for text in own:
                    writers.setdefault(agreement_key(text), set()).add(reading.observation_id)
        else:
            each, blocked, agreeing = _label_texts(group, [*(text for reading in group
                for text in literals.get(reading.name, ())), *offered])
            writers = {key: set(ids) for key, ids in agreeing.items()}
        agreed[region] = frozenset(key for key, ids in writers.items() if len(ids) >= MIN_BACKING_READERS)
        prepared[region] = (group, preferred, bound, each, writers, blocked)
    for region, (group, preferred, bound, each, writers, blocked) in prepared.items():
        mine = each[group.index(preferred)] if bound else frozenset()
        texts = frozenset().union(*each)
        if not texts or (bound and not mine):
            continue
        if bound:
            own = set(allowed.get(preferred.name, {}))
            source = _by_source(task, mine & own, mine, answers) if len(mine) > 1 and sourced else None
            if all(each) and len({agreement_key(text) for text in texts}) == 1:
                settled = frozenset({_spelling(task, preferred.name, mine)}) if mine else frozenset()
            else:
                settled = source.settled if source is not None else (mine if len(mine) == 1 and mine <= own
                    else frozenset())
            found[region] = Label(texts, settled, by_source=source is not None, basis=BY_PERSON if settled else None,
                person=preferred.name, cleared=bool(settled))
            continue
        found[region] = _settle_by_rule(task, group, each, writers, texts, answers, sourced=sourced,
            elsewhere=frozenset().union(*(keys for other, keys in agreed.items() if other != region)), blocked=blocked)
    return found


def _settle_by_rule(task: FieldTask, group: Sequence[Reading], each: Sequence[frozenset[str]],
        writers: Mapping[str, set[str]], texts: frozenset[str], answers: Sequence[SourceAnswer], *,
        sourced: bool, elsewhere: frozenset[str], blocked: tuple[str, ...] = ()) -> Label:
    """One label no person transcribed, by points 1 and 3 to 6 of labels_by_rule;
    `elsewhere` holds the agreement keys of the texts another label backs as TEXT, and
    `blocked` the texts readers write at the candidates' places that are no candidate: a
    source settles a candidate only when it rules each of them out too, and no same-place
    candidate forms while there is one."""
    key_of = {text: agreement_key(text) for text in texts}
    keys_in_order = list(dict.fromkeys(key_of[text] for text in sorted(texts)))
    by_key = {key: frozenset(text for text in texts if key_of[text] == key) for key in keys_in_order}
    order = {reading.observation_id: index for index, reading in enumerate(group)}

    def named(keys: frozenset[str]) -> bool:
        return any(image_names(reading, text) for reading, own in zip(group, each) for text in own
            if key_of.get(text, agreement_key(text)) in keys)

    confirmed, basis = (_confirmed_group(task, list(by_key.values()), answers, blocked) if sourced else (None, None))
    groups = [frozenset({key}) for key in keys_in_order]
    sourced_keys: frozenset[str] = frozenset()
    near: frozenset[str] = frozenset()
    members: frozenset[str] = frozenset()
    if confirmed is not None:
        sourced_keys = frozenset(key_of[text] for text in confirmed)
        # The texts of the group the source confirms by their own name (or a near spelling).
        members = frozenset(text for text in confirmed
            if identities(answers, text, task.key, near=basis == BY_NEAR_SPELLING))
        if basis == BY_SOURCE and task.key in PLACE_VALUE_FIELDS:
            close = {key_of[text] for text in texts if key_of[text] not in sourced_keys
                and any(one_letter_apart(text, one) for one in confirmed)}
            if len(close) == 1:
                near = frozenset(close)
        groups = [keys for keys in groups if not keys & (sourced_keys | near)] + [sourced_keys | near]
    elif sourced and not blocked and task.key in PLACE_VALUE_FIELDS:
        identified = [frozenset(identities(answers, text, task.key)) for text in texts]
        if all(identified) and frozenset.intersection(*identified):
            # Readers whose texts one authority confirms name one place: one candidate, on
            # the text the image names when it names the texts of one group alone, else on each.
            seen = [key for key in keys_in_order if named(frozenset({key}))]
            settled = (frozenset({_spelled(task, group, each, frozenset(seen))}) if len(seen) == 1 else texts)
            backed = Backed(texts, frozenset({SOURCE}), len(set().union(*writers.values())), 0)
            return Label(texts, settled, by_source=True, basis=BY_SAME_PLACE, candidates=(backed,), cleared=True,
                blocked=blocked)

    def backings(keys: frozenset[str]) -> frozenset[str]:
        kinds = set()
        if keys & sourced_keys:
            kinds.add(SOURCE)
        if named(keys):
            kinds.add(IMAGE)
        if len(set().union(*(writers.get(key, set()) for key in keys))) >= MIN_BACKING_READERS or keys & elsewhere:
            kinds.add(TEXT)
        return frozenset(kinds)

    candidates = []
    literal_of = {}
    for keys in groups:
        ids = set().union(*(writers.get(key, set()) for key in keys))
        candidate = Backed(frozenset(text for text in texts if key_of[text] in keys), backings(keys), len(ids),
            min(order[i] for i in ids))
        candidates.append(candidate)
        if sourced_keys and keys == sourced_keys | near:
            # The confirmed candidate settles on the text the image names, else the confirmed text.
            literal_of[candidate] = (_spelled(task, group, each, near) if near and named(near)
                and not named(sourced_keys) else _spelled(task, group, each, sourced_keys, members))
        else:
            literal_of[candidate] = _spelled(task, group, each, keys)
    writing = sum(1 for own in each if own)
    backed = [candidate for candidate in candidates if candidate.backings]
    # A candidate inside a backed one at the same place is no rival of it (_nested).
    backed = [candidate for candidate in backed if not any(other is not candidate
        and _nested(group, each, candidate.texts, other.texts) for other in backed)]
    if not backed:
        return Label(texts, candidates=tuple(candidates), blocked=blocked, writing=writing)
    strong = [candidate for candidate in backed if candidate.backings & {IMAGE, SOURCE}]
    if len(backed) > 1 and not strong:
        return Label(texts, candidates=tuple(candidates), blocked=blocked,
            options=tuple(literal_of[candidate] for candidate in sorted(backed, key=lambda c: c.first)))

    def rank(candidate: Backed) -> tuple[int, int, int]:
        return max(STRENGTH[kind] for kind in candidate.backings), candidate.readers, -candidate.first

    best = max(backed, key=rank)
    if sum(rank(candidate) == rank(best) for candidate in backed) > 1:
        # Nothing ranks one above the others (the same strongest backing, as many
        # readers, the same first reader): the label does not settle.
        return Label(texts, candidates=tuple(candidates), tied=True, blocked=blocked,
            options=tuple(literal_of[candidate] for candidate in backed if rank(candidate) == rank(best)))
    literal = literal_of[best]
    matched, matched_by = None, ()
    if SOURCE in best.backings:
        if key_of.get(literal, agreement_key(literal)) in near:
            # The image names the text one letter from the confirmed one: the label writes it,
            # and the confirmed name is its value through a near spelling.
            basis = BY_NEAR_SPELLING
            matched = _spelled(task, group, each, sourced_keys, members)
            matched_by = tuple(reading.name for reading, own in zip(group, each)
                if any(key_of[text] in sourced_keys for text in own))
    elif IMAGE in best.backings:
        basis = BY_IMAGE
    else:
        basis = BY_AGREEMENT if best.readers >= MIN_BACKING_READERS else BY_OTHER_LABEL
    cleared = len(backed) == 1 and bool(best.backings & {IMAGE, SOURCE})
    return Label(texts, frozenset({literal}), by_source=SOURCE in best.backings, basis=basis, matched=matched,
        matched_by=matched_by, candidates=tuple(candidates), cleared=cleared, blocked=blocked,
        why=None if cleared else (TEXT_ONLY if len(backed) == 1 else CONTESTED),
        others=tuple(literal_of[candidate] for candidate in sorted(backed, key=lambda c: c.first)
            if candidate is not best))


def _disagreement(task: FieldTask, readings: Sequence[Reading], *, literal: str,
        authority_id: str | None, cited: Sequence[SourceAnswer],
        received: Sequence[SourceAnswer], transcript: str | None = None,
        named: Sequence[Reading] = ()) -> Refusal | None:
    """Why readers or labels that disagree do not settle the field on this
    answer, or None (B1 of #284's reviews; G19, G20, G27, G32, N4). For text
    read from the transcript (`transcript`, on the `named` readings' labels),
    a reader of such a label that writes it nowhere and has no text the
    organiser found leaves the label unsettled (labels, Label.unread)."""
    sources = frozenset(task.tools) & SOURCE_IDS
    answers = [a for a in received if a.source_id in sources]
    found = labels(task, readings, answers, transcript=transcript, named=named)
    settled = frozenset().union(*(label.settled for label in found.values())) if found else frozenset()
    every = sorted(frozenset().union(*(label.literals for label in found.values()))) if found else []
    shown = "; ".join(repr(text) for text in every)
    if not found:
        return None
    if any(reading.units is not None for reading in readings):
        return _disagreement_by_rule(task, found, literal=literal, authority_id=authority_id, cited=cited,
            answers=answers, sources=sources)
    unread = sorted(frozenset().union(*(label.unread for label in found.values())))
    if unread:
        return Refusal(NOT_EVERY_READER, (
            f"You read {literal!r} from the transcript, and reading {', '.join(unread)} of the same "
            "label writes it nowhere (letter case and spacing aside), nor did the organiser find "
            "other text for this field there. On a label whose first pass preferred no reader, text "
            "read from the transcript settles only when every reader of the label writes it. Answer "
            "several_possibilities with each reader's text, or sources_cannot_resolve."), differ=True)
    conflicts = [label for label in found.values() if label.preference == CONFLICT]
    if conflicts:
        shown_here = "; ".join(repr(text) for text in sorted(frozenset().union(*(c.literals for c in conflicts))))
        return Refusal(FIRST_PASS_CONFLICT, (
            f"The readers of a label write {shown_here}. The first pass judged the image at that difference "
            "and found the reader it preferred, while only another label or a near spelling backs another "
            "reader's text, and no source confirms it by its own name. That is for a person to choose: "
            "answer several_possibilities with both texts."), differ=True)
    persons = [label for label in found.values() if label.person and collapse(literal) not in label.settled]
    if persons:
        [label, *_] = persons
        theirs = (f"its text for this field, {', '.join(repr(text) for text in sorted(label.settled))}, "
            if label.settled else "no single text for this field that settles, ")
        return Refusal(PERSON_DECIDED, (
            f"A person transcribed this label: reading {label.person} holds their transcription, and it writes "
            f"{theirs}which is the label's text whatever your sources found for another reader. Answer with "
            f"the literal from reading {label.person}, naming that reading; your sources may still settle its "
            "value (a candidate whose name is one letter from it, or its expansion), cited with its "
            "authority_id. Or answer several_possibilities or sources_cannot_resolve."), differ=True)
    if any(label.around for label in found.values()):
        return Refusal(DIFFER, (
            f"You read {literal!r} from the transcript, and the readers of its label write different "
            f"text around it ({shown}): the part of the line holding it (between commas or "
            "semicolons, else the whole line) must be the same in every reader, letter case and "
            "spacing aside. Answer several_possibilities with each reader's text, or "
            "sources_cannot_resolve."), differ=True)
    if (all(label.settled for label in found.values()) and len(settled) == 1
            and not any(label.by_source for label in found.values())):
        # Every label settles on its own text, and they agree: on that text,
        # as its readers, another label or the first pass's preferred reader
        # spells it.
        [one] = settled
        if collapse(literal) == one:
            return None
        if all(label.basis == BY_AGREEMENT for label in found.values()):
            return Refusal(DIFFER, (
                f"The readers write {shown}, which agree on {one!r} (the spelling of the reader the "
                "first pass preferred, or the first reader's when it preferred none; letter case and "
                f"spacing aside, they are one text). Copy the literal {one!r} exactly from a reading "
                "that writes it, and name only readings that write it so."), differ=True)
        return Refusal(DIFFER, (
            f"The readers write {shown}, and the labels settle on {one!r}: readers that agree, another "
            "label of this specimen that writes it, or the reading the first pass preferred where "
            "nothing supports another reader's text. Copy the literal "
            f"{one!r} exactly from a reading that writes it, and name only readings that write it so; "
            "to settle on another reader's text, ask your approved sources about each reader's text, or "
            "answer several_possibilities."), differ=True)
    if not all(label.settled for label in found.values()):
        return Refusal(DIFFER, (
            f"The readers disagree on this field ({shown}). A label whose readers differ settles on one "
            "reader's text when your approved sources were asked about each reader's text: exactly one "
            "confirmed by a success answer (for a place written as an abbreviation, an answer asked its "
            "expansion may confirm it; for a place none of whose readers' texts is found by its own "
            "name, an answer asked the candidate's own name one letter from it), every other found by "
            "none (a no_match answer, and no success or ambiguous one)"
            + (", or found only as another kind of place than this field's (no candidate of its name, "
               "or one letter from it, at this field's level); or, for a place, each reader's text "
               "confirmed as the same place (one candidate at this field's level, with one "
               "authority_id)" if task.key in PLACE_VALUE_FIELDS
               else "" if sources else " (this field has no such source)")
            + "; or when another label of this specimen settles on that text on its own evidence (its "
            "readers agree, or a source confirms it); or else on the reading the first pass preferred, "
            "when it preferred one that writes this field. "
            "Ask about each reader's text, or answer several_possibilities with each reader's "
            "text, or sources_cannot_resolve."), differ=True)
    return _sourced_refusal(task, found, settled, shown, literal=literal, authority_id=authority_id, cited=cited,
        answers=answers, sources=sources, seen="which the first pass confirmed against the image")


def _unbacked(label: Label) -> bool:
    """A units-path label that settles nothing and none of whose candidates has a backing."""
    return not (label.settled or label.person or label.tied or label.options
        or any(candidate.backings for candidate in label.candidates))


def _disagreement_by_rule(task: FieldTask, found: Mapping[str, Label], *, literal: str,
        authority_id: str | None, cited: Sequence[SourceAnswer], answers: Sequence[SourceAnswer],
        sources: frozenset[str]) -> Refusal | None:
    """_disagreement on the units path: the labels as labels_by_rule settles them, with
    retries that name the rule's backings. A label none of whose candidates has a backing
    is no evidence against a text another label backs: while another label settles or has
    a backed candidate, it takes no part."""
    if any(not _unbacked(label) for label in found.values()):
        found = {region: label for region, label in found.items() if not _unbacked(label)}
    settled = frozenset().union(*(label.settled for label in found.values()))
    shown = "; ".join(repr(text) for text in sorted(frozenset().union(*(label.literals | frozenset(label.blocked)
        for label in found.values()))))
    persons = [label for label in found.values() if label.person and collapse(literal) not in label.settled]
    if persons:
        [label, *_] = persons
        theirs = (f"its text for this field, {', '.join(repr(text) for text in sorted(label.settled))}, "
            if label.settled else "no single text for this field that settles, ")
        return Refusal(PERSON_DECIDED, (
            f"A person transcribed this label: reading {label.person} holds their transcription, and it writes "
            f"{theirs}which is the label's text whatever your sources found for another reader. Answer with "
            f"the literal from reading {label.person}, naming that reading; your sources may still settle its "
            "value (a candidate whose name is one letter from it, or its expansion), cited with its "
            "authority_id. Or answer several_possibilities or sources_cannot_resolve."), differ=True)
    tied = [label for label in found.values() if label.tied]
    if tied:
        options = tuple(dict.fromkeys(option for label in tied for option in label.options))
        return Refusal(TIED, (
            f"The readers write {shown}: {', '.join(repr(option) for option in options)} each have the same "
            "backing, as many readers and the same first reader, so nothing ranks one above the others. That is "
            f"for a person to choose: answer several_possibilities with {', '.join(repr(option) for option in options)}."),
            differ=True, options=options)
    contested = [label for label in found.values() if label.options]
    if contested:
        options = tuple(dict.fromkeys(option for label in contested for option in label.options))
        return Refusal(TEXTS_CONTESTED, (
            f"The readers write {shown}: {', '.join(repr(option) for option in options)} each have the backing "
            "of readers that agree or of another label of this specimen, and neither the image nor an approved "
            "source backs one. That is for a person to choose: answer several_possibilities with "
            f"{', '.join(repr(option) for option in options)}."), differ=True, options=options)
    if all(label.settled for label in found.values()) and len(settled) == 1 and not any(
            label.by_source for label in found.values()):
        [one] = settled
        if collapse(literal) == one:
            return None
        return Refusal(DIFFER, (
            f"The readers write {shown}, and the labels settle on {one!r}: the text the image names, else the "
            "first reader's spelling of the text that readers who agree or another label of this specimen "
            f"write (letter case and spacing aside, they are one text). Copy the literal {one!r} exactly from "
            "a reading that writes it, and name only readings that write it so; to settle on another reader's "
            "text, ask your approved sources about each reader's text, or answer several_possibilities."),
            differ=True)
    unsettled = [label for label in found.values() if not label.settled]
    if unsettled:
        retry = (
            f"The readers write {shown} for this field, and nothing backs one reader's text. A label settles on "
            "a reader's text that has backing: the image names it at its unit (units: image); your approved "
            "sources were asked about each reader's text, a success answer confirms exactly that one by its own "
            "name (for a place written as an abbreviation, by its expansion; for a place none of whose readers' "
            "texts is found by its own name, an answer asked the candidate's own name one letter from it), and "
            "every other found none (a no_match answer, and no success or ambiguous one)"
            + (", or found only as another kind of place than this field's; or, for a place, each reader's "
               "text confirmed as the same place (one candidate at this field's level, with one authority_id)"
               if task.key in PLACE_VALUE_FIELDS else "" if sources else " (this field has no such source)")
            + "; two or more readers of the label write it; or another label of this specimen, read by two or "
            "more readers who agree, writes it. Ask about each reader's text, or answer several_possibilities "
            "with each reader's text, or sources_cannot_resolve.")
        if any(len({agreement_key(text) for text in label.literals}) > 1 or label.blocked or label.writing > 1
                for label in unsettled):
            return Refusal(DIFFER, retry, differ=True)
        return Refusal(ONE_READER, retry, differ=True)
    return _sourced_refusal(task, found, settled, shown, literal=literal, authority_id=authority_id, cited=cited,
        answers=answers, sources=sources, seen="which the image names on the label")


def _source_members(task: FieldTask, readings: Sequence[Reading], received: Sequence[SourceAnswer], literal: str,
        *, transcript: str | None) -> frozenset[str]:
    """On the units path, the other texts of the source-backed candidate whose texts hold the
    literal, letter case and spacing aside the literal (labels_by_rule's Backed.texts)."""
    sources = frozenset(task.tools) & SOURCE_IDS
    found = labels(task, readings, [a for a in received if a.source_id in sources], transcript=transcript)
    want = collapse(literal)
    return frozenset(text for label in found.values() for candidate in label.candidates
        if SOURCE in candidate.backings and want in candidate.texts for text in candidate.texts
        if text != want and agreement_key(text) == agreement_key(want))


def _sourced_refusal(task: FieldTask, found: Mapping[str, Label], settled: frozenset[str], shown: str, *,
        literal: str, authority_id: str | None, cited: Sequence[SourceAnswer], answers: Sequence[SourceAnswer],
        sources: frozenset[str], seen: str) -> Refusal | None:
    """_disagreement's last checks, for labels that all settle and a source settled one
    of them, or for labels that settle on different texts: the answer's literal is the
    labels' text and cites the answer confirming it, or one authority confirms each."""
    cited = [a for a in cited if a.source_id in sources]
    want = collapse(literal)
    if len(settled) == 1:
        [one] = settled
        # The units path: the texts of the settled candidate a source backs, letter case and
        # spacing aside the settled text (Backed.texts); any of them, confirmed, is the answer.
        members = frozenset(text for label in found.values() for candidate in label.candidates
            if SOURCE in candidate.backings and one in candidate.texts for text in candidate.texts
            if agreement_key(text) == agreement_key(one)) or frozenset({one})
        if want not in members:
            spelled = next((label for label in found.values() if label.matched and label.settled == {one}), None)
            if spelled is not None:
                return Refusal(DIFFER, (
                    f"Your source confirms reader {', '.join(spelled.matched_by)}'s {spelled.matched!r}, one "
                    f"letter from {one!r}, {seen}: the label writes "
                    f"{one!r}. Give {one!r} as the literal, naming the reading that writes it, and the source's "
                    "candidate as the value with its authority_id (a near spelling)."), differ=True)
            return Refusal(DIFFER, (
                f"The labels settle on the reader's text {one!r}: copy the literal from a reading "
                "that writes it, or answer several_possibilities."), differ=True)
        if not any(identities(cited, member, task.key, near=True) for member in members):
            return Refusal(DIFFER, (
                f"Cite the evidence_id of the source answer that confirms {one!r}"
                + (" (for an abbreviation, the answer asked its expansion, whose one candidate at this "
                   "field's level is your value)" if task.key in PLACE_VALUE_FIELDS and abbreviated(one)
                   else "") + "."), differ=True)
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


# What kind of text each field's value is, for the guard on text read from
# the transcript (step._taken): a reading's text settled as one field's value
# is never also settled, from the transcript, as a field's of another kind.
# Fields of one kind may share text: places nest (a town inside the precise
# location), a date or an elevation is a range's end or a unit's copy, and a
# determiner may be a collector. Verbatim D/T/S may share any field's text,
# as what it holds is an open museum question. Any other field is a kind of
# its own.
FIELD_KINDS = {
    **dict.fromkeys(("country", "province_state", "county", "city", "precise_location"), "place"),
    **dict.fromkeys(("date_visited_from", "date_visited_to", "date_identified"), "date"),
    **dict.fromkeys(("elevation_from_m", "elevation_to_m", "elevation_from_ft", "elevation_to_ft"), "elevation"),
    **dict.fromkeys(("collectors", "identified_by_irn"), "person"),
}
SHARES_ANY_TEXT = frozenset({"verbatim_dts"})


def may_share_text(key: str, other: str) -> bool:
    """Whether two fields' values may be the same text of a reading: fields of
    one kind (FIELD_KINDS), or either of them verbatim D/T/S."""
    return (key in SHARES_ANY_TEXT or other in SHARES_ANY_TEXT
        or FIELD_KINDS.get(key, key) == FIELD_KINDS.get(other, other))


ASKED, ABBREVIATION, NEAR_SPELLING = "asked", "abbreviation", "near_spelling"


def asked_name(answer: SourceAnswer) -> str:
    """The name a place source was asked: its query's first comma-separated
    part, the only name a gazetteer searches and the place GEOLocate looks
    for."""
    return answer.query.split(",", 1)[0].strip()


class Settling(NamedTuple):
    """How a place value settles (place_settling): its basis, the candidate
    it settles on, and the cited answer that has that candidate."""

    basis: str
    candidate: SourceCandidate
    answer: SourceAnswer


def place_settling(task: FieldTask, literal: str, settled: str, authority_id: str | None,
        cited: Iterable[SourceAnswer]) -> Settling | None:
    """How a cited answer of the field's place sources settles the place value
    (P1 and P3 of #284), and on which candidate; None when none does. The
    answer has exactly one candidate at the field's level (placed), that
    candidate is the settled value (its name exactly, after NFC and whitespace
    collapse) with the answer's authority_id, and the answer was asked
    - an expansion of the literal (asked_name), a name the literal
      abbreviates by the letter rule (abbreviations.fit: "Philippine Islands"
      for "P.I.", "Davao Province" for "Davao, Prov."): ABBREVIATION, for
      which the step cites a rule row naming the abbreviation, the expansion
      and how its letters fit, and which refusal holds back when another
      fitting expansion was answered as another place (rival_expansion). An
      expansion that writes out only a unit word has the literal's
      comparison key too ("Davao Province" and "Davao, Prov." are both
      "davao"); it is still an expansion; or else
    - about the label's own text (about): ASKED; or else
    - about that candidate's own name, when the name is one letter from the
      label's text (application.georef_locality.one_letter_apart: both full
      names, comparison keys one single-letter edit apart): NEAR_SPELLING. It
      is G34's one-letter half only; the step settles it only when the rest
      of G34 holds too (parents_refusal), and then records a near_spelling
      warning finding that never routes the record."""
    sources = frozenset(task.tools) & frozenset(PLACE_SOURCES)
    found: dict[str, Settling] = {}
    for answer in cited:
        one = placed(task.key, answer) if answer.source_id in sources else None
        if one is None or collapse(one.name) != collapse(settled) or one.authority_id != authority_id:
            continue
        if fits(literal, asked_name(answer)):
            found.setdefault(ABBREVIATION, Settling(ABBREVIATION, one, answer))
        elif about(answer, collapse(literal)):
            found.setdefault(ASKED, Settling(ASKED, one, answer))
        elif about(answer, collapse(one.name)) and one_letter_apart(literal, one.name):
            found.setdefault(NEAR_SPELLING, Settling(NEAR_SPELLING, one, answer))
    return next((found[basis] for basis in (ASKED, ABBREVIATION, NEAR_SPELLING) if basis in found), None)


def place_basis(task: FieldTask, literal: str, settled: str, authority_id: str | None,
        cited: Iterable[SourceAnswer]) -> str | None:
    """The basis place_settling finds, or None."""
    found = place_settling(task, literal, settled, authority_id, cited)
    return found.basis if found is not None else None


def another_place(candidate: SourceCandidate, settled: SourceCandidate) -> bool:
    """Whether a candidate is another place than the settled one: another
    record (another authority_id, or none) and another name (place_name).
    The same nation in two gazetteers has two records and one name."""
    return ((candidate.authority_id is None or candidate.authority_id != settled.authority_id)
        and place_name(candidate.name) != place_name(settled.name))


class Rival(NamedTuple):
    """Another name the sources found the label's abbreviation as (rival_expansion)."""

    name: str
    # The label's own text, rather than another expansion of it.
    own: bool


def rival_expansion(task: FieldTask, literal: str, settling: Settling,
        received: Iterable[SourceAnswer]) -> Rival | None:
    """For a place value settled on an expansion of its literal (ABBREVIATION),
    another name a place source of the field answered (success or ambiguous,
    with its evidence stored) as another place (another_place) at the field's
    level; None when there is none. The name is another query than the
    settling expansion (compared by georef_locality.fold: case, accents and
    punctuation aside, unit words kept) and either
    - another expansion the literal fits by the letter rule, with any
      candidate at the field's level that is another place: "S.A." looked up
      as "South Africa" and as "Saudi Arabia"; or
    - the label's own text (about: "Davao" for "Davao, Prov."), with exactly
      one candidate at the field's level, another place: the source found
      the text itself as a place, and the expansion names another."""
    used = fold(asked_name(settling.answer))
    sources = frozenset(task.tools) & frozenset(PLACE_SOURCES)
    for answer in received:
        if (answer.source_id not in sources or answer.status not in PLACE_ANSWERED
                or answer.evidence is None):
            continue
        name = asked_name(answer)
        if fold(name) in (used, ""):
            continue
        level = at_level(task.key, answer)
        if fits(literal, name):
            own = False
        elif about(answer, collapse(literal)) and len(level) == 1:
            own = True
        else:
            continue
        if any(another_place(candidate, settling.candidate) for candidate in level):
            return Rival(name, own)
    return None


def initialism_of(literal: str, settling: Settling) -> str | None:
    """The expansion of a place value settled on initials
    (abbreviations.initialism: "Philippine Islands" for "P.I."), or None.
    Only the step can corroborate such a value (step._corroborate)."""
    if settling.basis != ABBREVIATION:
        return None
    expansion = asked_name(settling.answer)
    pairs = fit(literal, expansion)
    return expansion if pairs is not None and initialism(pairs) else None


def initialism_alone(literal: str, expansion: str) -> str:
    """The reason of a place value whose initials no other place confirms."""
    return (f'The initials "{literal}" fit "{expansion}", but no other place on the label was found '
        "inside it, so the initials alone do not decide.")


# Why a place value's candidate does not fit the label's other place fields
# (B3 and N1 of #284's third review; the step's check, parents_refusal).
NO_PARENTS = "The source does not say which country this place is in."
NO_COUNTRY = "No country is settled for the reading that writes this place."
NOT_IN_COUNTRY = "The place found is not in the country the label gives."
NOT_IN_PROVINCE = "The place found is not in the province the label gives."
NEAR_UNFIT = ("The place found is one letter from the label's spelling, and the larger places the label "
    "gives do not confirm it.")
NO_PROVINCE = "The province the label gives is not settled, so this county cannot be confirmed inside it."
IS_THE_PROVINCE = "The label gives this place as the province, and a province is never also the county."
PLACE_ORDER = ("country", "province_state", "county", "city")


@dataclass(frozen=True)
class PlaceField:
    """Another place field as one reading writes it: the texts that reading
    writes for it (its candidate literals and verbatims), with, when it is
    settled from that reading's text, the value it settled on and the
    expansion it settled through (the step's abbreviation row), that
    value's authority_id, and, for the country, the ISO 3166-1 alpha-2 code
    that record carries (SourceCandidate.iso_code), when it carries one."""

    texts: tuple[str, ...]
    authority_id: str | None = None
    iso_code: str | None = None


def place_keys(texts: Iterable[str]) -> frozenset[str]:
    """The comparison keys (place_name) a place field's texts name a parent by."""
    return frozenset(place_name(text) for text in texts) - {""}


# ISO 3166-1's user-assigned alpha-2 codes (AA, QM to QZ, XA to XZ, ZZ):
# the standard gives them no country, so any source may give one a place of
# its own choosing ("XK" for Kosovo), and two sources need not mean one
# place by it.
USER_ASSIGNED = re.compile(r"AA|Q[M-Z]|X[A-Z]|ZZ")


def country_code(code: str | None) -> str | None:
    """A country code lies_in compares: two capital letters, exactly as
    written, and none of ISO 3166-1's user-assigned codes (USER_ASSIGNED).
    None for anything else."""
    if code is None or not re.fullmatch(r"[A-Z]{2}", code) or USER_ASSIGNED.fullmatch(code):
        return None
    return code


def lies_in(candidate: SourceCandidate, key: str, field: PlaceField) -> bool:
    """Whether a parent of the candidate is this place field: the same record
    (the field's authority_id), a name with one of its comparison keys, or,
    for a parent its source names only by a country code (PlaceRef.iso_code:
    NGA's "GT"), the same code as the ISO 3166-1 alpha-2 code the field's
    settled record carries (Wikidata's P297 "GT" for Guatemala), compared
    exactly (country_code); never a code guessed from a name."""
    names = place_keys(field.texts)
    code = country_code(field.iso_code)
    return any((field.authority_id is not None and parent.authority_id == field.authority_id)
        or place_name(parent.name) in names
        or (code is not None and country_code(parent.iso_code) == code) for parent in candidate.parents)


def confirmed_place(answers: Iterable[SourceAnswer], texts: Iterable[str], key: str) -> PlaceField | None:
    """The one place the gazetteers confirm every one of a place field's texts
    as, or None. For each text, the Getty TGN, Wikidata or NGA answers about
    it (about) or asked an expansion its letters fit (abbreviations.fit),
    success or ambiguous and with their evidence stored, confirm it as the one
    candidate at the field's level (identities: of the text's own name, or of
    an expansion's answer); at least one does, and every candidate at the
    field's level that one of those answers settles on (placed), of whatever
    name, is that same place (another_place: another record and another
    name). 3781e440's "USA" is the United States: Wikidata's answer for
    "United States of America" confirms it, and its answer for "USA" itself
    has that nation as its one nation. One text placed as two places, or two
    texts as different places, give None. The result names the place by
    those candidates' names, with their record and ISO code when they share
    one."""
    texts = [text for text in dict.fromkeys(texts) if text and text.strip()]
    if key not in PLACE_VALUE_FIELDS or not texts:
        return None
    usable = [answer for answer in answers if answer.source_id in GAZETTEERS and answer.evidence is not None
        and answer.status in PLACE_ANSWERED]
    found: list[SourceCandidate] = []
    for text in texts:
        if not identities(usable, text, key):
            return None
        asked = [answer for answer in usable if about(answer, text) or fits(text, asked_name(answer))]
        found.extend(one for answer in asked if (one := placed(key, answer)) is not None)
    if not found or any(another_place(one, other) for one in found for other in found):
        return None
    ids = {one.authority_id for one in found if one.authority_id}
    codes = {one.iso_code for one in found if one.iso_code}
    return PlaceField(tuple(dict.fromkeys(one.name for one in found)), ids.pop() if len(ids) == 1 else None,
        codes.pop() if len(codes) == 1 else None)


def _written_ancestor_fits(field: PlaceField, literal: str | None) -> bool:
    """Whether an unsettled larger field is the same misplaced literal.

    An unsettled larger field may be the same misplaced text that is being
    moved to its real level ("Illinois" written under country, then settled
    as province/state). If it is merely a candidate parent ("United States"
    above "Illinois"), the larger field's own failure must not be hidden by a
    lower field.
    """
    names = place_keys(field.texts)
    return literal is not None and place_name(literal) in names


def _written_ancestor_is_settled_lower(key: str, ancestor: str, candidate: SourceCandidate,
        field: PlaceField, settled: Mapping[str, PlaceField]) -> bool:
    """Whether an unsettled ancestor's text has already settled lower down.

    Example: Country writes "Illinois", Province/State has been reconciled to
    Illinois, and a city candidate lies in Illinois. The written country is not
    a country failure to hide; it is the same misfiled state text.
    """
    names = place_keys(field.texts)
    for lower in PLACE_ORDER[PLACE_ORDER.index(ancestor) + 1:PLACE_ORDER.index(key)]:
        lower_field = settled.get(lower)
        if lower_field is not None and names & place_keys(lower_field.texts) and lies_in(
                candidate, lower, lower_field):
            return True
    return False


def _can_derive_ancestor(key: str, ancestor: str, candidate: SourceCandidate, basis: str,
        written: Mapping[str, PlaceField], settled: Mapping[str, PlaceField],
        literal: str | None, confirmed: Mapping[str, PlaceField] | None = None) -> bool:
    """Whether an exact place match can stand while an ancestor is filled later.

    Near spellings still need already-settled ancestors; otherwise a typo could
    silently move a label into the wrong hierarchy. A written ancestor that is
    not settled holds the place back unless it is the same misfiled text, has
    settled lower down, or the gazetteers confirm every text the record writes
    for it as one place that is the candidate's parent (`confirmed`,
    confirmed_place): 3781e440's country "USA", one reader's text, which no
    answer settled, while its county Coles County lies in the United States
    that "USA" is confirmed as. An ancestor left with no value and no text
    is then derived from the place (derive.fill); its text never supplies
    the value.
    """
    if basis == NEAR_SPELLING:
        return False
    if ancestor == "country" and not candidate.parents:
        return False
    if ancestor == "province_state" and key in ("county", "city") and len(candidate.parents) < 2:
        return False
    field = written.get(ancestor)
    found = (confirmed or {}).get(ancestor)
    return (field is None or _written_ancestor_fits(field, literal)
        or _written_ancestor_is_settled_lower(key, ancestor, candidate, field, settled)
        or (found is not None and lies_in(candidate, ancestor, found)))


def parents_refusal(key: str, candidate: SourceCandidate, basis: str, *,
        written: Mapping[str, PlaceField], settled: Mapping[str, PlaceField],
        literal: str | None = None, unsettled: frozenset[str] = frozenset(),
        confirmed: Mapping[str, PlaceField] | None = None) -> Refusal | None:
    """Why the candidate a place value settles on does not fit the label's
    other place fields of one reading (B3 and N1 of #284's third review), or
    None. `written` is every other place field that reading writes; `settled`
    those of them settled from that reading's text; `unsettled` those of them
    whose field has no settled value at all; `literal` the value's literal;
    `confirmed` the place the gazetteers confirm every text the record writes
    for an unsettled field as (confirmed_place), by field.
    - Below the country, the candidate has parents (SourceCandidate.parents),
      the country settled for the reading is one of them, and for a county or
      a city, the province settled for the reading too when one is. A
      candidate with no parents, or none of whose parents is that country,
      does not settle; nor does any place when no country is settled for the
      reading, unless the reading writes no country, writes the place's own
      misfiled text there, or writes a country whose every text on the
      record the gazetteers confirm as a parent of the candidate (`confirmed`,
      _can_derive_ancestor). A country needs no parent.
    - A county also needs the province its reading writes to be settled
      (NO_PROVINCE, when that field has no settled value: `unsettled`): a
      second-level unit's parent chain is confirmed only inside a settled
      province. And it is never the settled province
      itself (IS_THE_PROVINCE): neither that province's record nor, letter
      case, accents and punctuation aside (georef_locality.fold, unit words
      kept), one of its texts, values or expansions, so "<Province>" or
      "<Province> Prov." written once as the province is no county, while
      "<Name> Co." in the state "<Name>" may be.
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
        if country is None and not _can_derive_ancestor(
                key, "country", candidate, basis, written, settled, literal, confirmed):
            return Refusal(NO_COUNTRY, NO_COUNTRY)
        if country is not None and not lies_in(candidate, "country", country):
            return Refusal(NOT_IN_COUNTRY, NOT_IN_COUNTRY)
        province = settled.get("province_state")
        if (key == "county" and "province_state" in unsettled
                and not _can_derive_ancestor(
                    key, "province_state", candidate, basis, written, settled, literal)):
            return Refusal(NO_PROVINCE, NO_PROVINCE)
        if (key == "city" and "province_state" in unsettled
                and not _can_derive_ancestor(
                    key, "province_state", candidate, basis, written, settled, literal)):
            return Refusal(NO_PROVINCE, NO_PROVINCE)
        if key == "county" and province is not None and (
                (province.authority_id is not None and candidate.authority_id == province.authority_id)
                or (literal is not None and fold(literal) in {fold(text) for text in province.texts})):
            return Refusal(IS_THE_PROVINCE, IS_THE_PROVINCE)
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
    # The units path offers the answer's literal to every label, whatever readings it names.
    transcript = literal if (any(reading.units is not None for reading in readings)
        or literal_basis(task, readings, literal, named) == TRANSCRIPT) else None
    refused = _disagreement(task, readings, literal=literal, authority_id=authority_id, cited=cited,
        received=received, transcript=transcript, named=named)
    if refused is not None:
        return refused
    if task.key in PLACE_VALUE_FIELDS:
        settled_value = value if value is not None else literal
        found = place_settling(task, literal, settled_value, authority_id, cited)
        if found is None and any(reading.units is not None for reading in readings):
            # The units path: the cited answer may confirm another spelling of the source-backed
            # candidate the literal settles with ("Chimaltenango" for "Chi mal ten ango").
            for member in sorted(_source_members(task, readings, received, literal, transcript=transcript)):
                found = place_settling(task, member, value if value is not None else member, authority_id, cited)
                if found is not None:
                    break
        if found is None:
            return Refusal(NO_PLACE, (
                "A place field settles only on a place source's success or ambiguous answer that "
                "was asked the label's own text: the literal as the query's first comma-separated "
                "part, the name it searches (case, accents, punctuation and notations such as Prov. "
                "aside), or an expansion of the literal when it is an abbreviation whose letters "
                "fit the expansion's words in order (\"Philippine Islands\" for \"P.I.\"), or the "
                "candidate's own name when it is one letter from the literal; with exactly one "
                "candidate at this field's level (by its kind: a "
                "nation for a country, a first level subdivision for a province or state, a second "
                "level one for a county, an inhabited place for a city; GEOLocate's candidate "
                "only for a city, as for the other fields it repeats a part of your query), and "
                "that candidate is the value: cite its "
                "evidence_id, give that candidate's name (as value, or as the literal when they "
                "are the same) and its authority_id. Otherwise answer several_possibilities or "
                "sources_cannot_resolve."))
        if found.basis == ABBREVIATION and (
                rival := rival_expansion(task, literal, found, received)) is not None:
            told = (f"your sources found the label's own text {rival.name!r} as another place at this "
                f"field's level than {asked_name(found.answer)!r}" if rival.own else
                f"{literal!r} fits both {asked_name(found.answer)!r} and {rival.name!r}, and your sources "
                "found each at this field's level as different places")
            return Refusal(EXPANSIONS_DIFFER, (
                f"{told[0].upper()}{told[1:]}. The letters do not decide between them: answer "
                "several_possibilities, or sources_cannot_resolve."), differ=True)
        if task.key == "county" and (first := first_level_namesake(task, literal, received)) is not None:
            return Refusal(FIRST_LEVEL_TOO, (
                f"Your sources also found {first!r}, a first-level unit (a province, state or department), "
                f"for the label's text {literal!r}, which writes no county or municipality unit word: the "
                "label may name that unit, and the sources cannot tell which it means. A first-level "
                "unit is never the county: answer several_possibilities, or sources_cannot_resolve."),
                differ=True)
    return None


def writes_county_unit(literal: str) -> bool:
    """Whether the literal writes a unit word that marks a county or a
    municipality (admin_markers.ADMIN_MARKERS: "Co.", "County", "Kreis",
    "Mun.", "Municipio" and the others), as a word of its own; one of
    admin_markers.AFTER_A_NAME ("Co.") only after a name ("<County> Co.",
    never "Co. <Name>", a hill)."""
    from .admin_markers import ADMIN_MARKERS, AFTER_A_NAME

    words = fold(literal).split()
    return any("county" in ADMIN_MARKERS.get(word, ()) and (word not in AFTER_A_NAME or index > 0)
        for index, word in enumerate(words))


def first_level_namesake(task: FieldTask, literal: str, received: Iterable[SourceAnswer]) -> str | None:
    """For a county, a first-level unit its place sources found for the label's
    own text, or None: a candidate at a province's or state's level (at_level)
    with the literal's name (place_name), in a success or ambiguous answer of
    one of the field's place sources asked about the literal (about), with
    its evidence stored. Such a text may name the first-level unit rather
    than a county ("<Province>", or a Philippine "<Province> Prov.", which
    Getty TGN, NGA and Wikidata hold at the first level), and the sources
    cannot tell which the label means. None too when the literal writes a
    county or municipality unit word (writes_county_unit: "<Name> Co.",
    "Mun. <Name>"), which says which it means."""
    if writes_county_unit(literal):
        return None
    sources = frozenset(task.tools) & frozenset(PLACE_SOURCES)
    want = place_name(literal)
    for answer in received:
        if (answer.source_id not in sources or answer.status not in PLACE_ANSWERED or answer.evidence is None
                or not about(answer, collapse(literal))):
            continue
        for candidate in at_level("province_state", answer):
            if place_name(candidate.name) == want:
                return candidate.name
    return None
