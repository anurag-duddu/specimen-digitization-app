"""When a resolved answer may settle its field (B1 and B2 of #284's reviews).

`refusal` checks every resolved answer, in the expert's answer check
(experts.py, so the model is sent back) and again in the step before the
answer becomes a value (step._refusal). It enforces points 1 to 4, in this
order; the step alone adds point 5 (parents_refusal), which needs the other
fields' outcomes:

1. No reader is preferred (the owner, 2026-10-25: "Harness can decide as it
   goes out and learns more than what the raw transcriptions are capable
   of"): the first pass names no reading (since WP 1.8, the units path's
   alone), every rule here reads the readings the answer names, whichever
   reader wrote them, and a label's readers settle by point 3. A label's
   text a person decided binds it (point 3, BY_PERSON).
2. A whole candidate (B2): the literal is one of the field's candidate
   literals (FieldTask.candidates: the organiser's, and each keyed line the
   parser read) of each reading the answer names. Literals are compared after
   NFC and whitespace collapse only (checks.collapse): "E. slope" and
   "E.slope" differ. Or else, read from the transcript (literal_basis,
   TRANSCRIPT; coordinator's ruling of 2026-10-09): each of those readings
   writes the literal as a run of whole words within one line
   (verbatim_runs), or, for a field in ACROSS_LINES (the precise location
   and the habitat) whose literal holds a line break, over consecutive
   lines (written_runs), and it cuts or extends none of that reading's
   candidates (_cut_candidate); a taxon so read must sit in no longer name
   on its reading (_longer_written), a date or an elevation so read is
   never one end of a range its clause writes, joined in any of the
   languages and with any of the dashes field_research.written lists
   (_part_of_range), and a place or the collection code so read never holds
   a date, an elevation or a range of them (_holds_another_kind). An
   elevation, a candidate or so read, settles only a field of the unit its
   reading writes it in, and a number with no unit settles none
   (_unit_refusal). Points 1, 3
   and 4 hold for it as for a candidate, its readers per point 3. For a
   taxon, the candidate's quote, the reading's text it was taken from, must
   write no longer name around the literal (checks.longer_name): a candidate
   "Danaus plexippus" quoting "Danaus plexippus megalippe" (N3 of the third
   review), or "sp. 1" quoting "Epipsocus sp. 1" (B1 of #289's review), is a
   piece of the name the label writes, and never settles the taxon. Nor does
   a literal whose genus the candidate's quote, or the text of a reading the
   answer names or of any other reader of its label, marks as doubtful with
   a qualifier or a "?" right before it or on it (checks.genus_in_doubt:
   "Epipsocus" quoting "cfr. Epipsocus" or "Epipsocus?"; 1c of #289's fifth
   review); a qualifier on the line above counts only standing alone on
   that line ("cf." above "Epipsocus sp. 1", never "Danum Valley NR"). The
   step's unmatched taxon (owner decision B) meets these rules too. For a
   place value field (point 4), a candidate or a reader's verbatim that
   names no place (names_no_place: only unit words, f35af3a5's "Prov.") is
   no candidate at all, here and in point 3.
3. Readers and labels that disagree (B1; G20, G27, G32). From the field's
   candidates and the organiser's per-reader verbatims, whatever state the
   organiser gave the field, each label that writes the field settles on
   its own (`labels`), by the settlement rule of
   FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md section 4 (labels_by_rule: the
   owner, 2026-10-25: "Evidence is settlement which can be actual match from
   the lookups raw transcription itself being very clear and so on"): a
   label whose transcript a person decided settles on the person's text
   (BY_PERSON); any other label's candidates, the readers' texts grouped
   letter case and spacing aside (agreement_key: "shrubs" and "Shrubs",
   "sp. 30" and "Sp.30"; a punctuation mark or a letter more or less is a
   different text), are backed by the image the first pass read (IMAGE:
   its units name the text), by the field's approved sources (SOURCE,
   below) or by readers that agree, on this label or another
   (TEXT: MIN_BACKING_READERS); exactly one backed candidate settles,
   cleared with an IMAGE or a SOURCE backing, else marked for a person;
   backed candidates that rival each other settle on the best backed,
   marked, or leave the label to a person; a label with no backed
   candidate does not settle. A source backs a label's text when exactly
   one of its literals is confirmed by an answer about it (below), and
   every other has a captured no_match answer about it and no success or
   ambiguous one. An error, a timeout or a literal never asked about is
   neither. For a place value field (point 4), a literal its gazetteers
   found only as another kind of place than the field's is ruled out too
   (found_only_elsewhere: 48a71d53's "Mindanao," beside "Davao Prov." on a
   province, which Wikidata and NGA hold only as an island, an island
   group, a river, streets, towns and a third-level unit): every Getty TGN,
   Wikidata or NGA success or ambiguous answer about it lists candidates,
   those of two or more of them hold one of its name, each of those has a
   kind, and none of that name or one letter from it is at the field's
   level (one capped list of candidates, Wikidata's at most seven, is not
   enough); GEOLocate's answers count only for a city, where any candidate
   keeps the literal. An abbreviated literal (abbreviations.abbreviated)
   never is, as it may stand for a name no source was asked. A field with
   no approved source has no SOURCE backing. For a place value field
   (point 4) a label's texts are also one candidate when every one of them
   is confirmed and one authority_id confirms them all: its readers name
   the same place ("Yepocapa," and "Yepocapa", N4 of the third review).
   That rests on the source's evidence, and each literal must match the
   candidate's name by the place comparison key (case, accents,
   punctuation, unit words: "Chimaltenango Dept." and "Chimaltenango"
   too); the label settles on each of its literals; readers confirmed as
   different places, or not all confirmed, still go to review.
   How each label settled is Label.basis, and whether it is cleared or
   marked, Label.marked (the step records it: step._settlement).
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
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import NamedTuple

from specimen_digitization.application.derivations import UNITS
from specimen_digitization.application.domain import LookupStatus
from specimen_digitization.application.georef_locality import comparison_key, fold, one_letter_apart
from specimen_digitization.application.georef_wikidata import FIRST_LEVEL, LEVEL_NAMES

from . import date_lines, written
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
HOST_NAME = "The label writes this name as the host the specimen was taken from, not its taxon."
NO_PLACE = "No approved place source confirms this value."
EXPANSIONS_DIFFER = "The sources found different places for the label's abbreviation."
FIRST_LEVEL_TOO = ("The sources also find this name as a province or state, so they cannot tell which the "
    "label means.")
PART_OF_RANGE = "The label writes this value as one end of a range."
UNIT_DIFFERS = "The label writes this elevation in the other unit."
NO_UNIT = "The label writes no elevation unit with this number."
A_DISTANCE = "The label writes this number as a distance, not an elevation."
HOLDS_AN_ELEVATION = "This text holds an elevation, which is another field's."
HOLDS_A_DATE = "This text holds a date, which is another field's."
HOLDS_A_RANGE = "This text holds a range of dates or elevations, which is another field's."
# The units path (the ontology's notation collected_by, plan WP 2.3c): a collectors literal that
# is a collected_by marker alone ("leg.") names no one.
ROLE_ONLY = "This text is the collectors' role marker alone, which names no one."
HOST_HEADING = "This text starts with the heading \"Host\", which is not part of the host's name."
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
# lines; the third rerun of 2026-10-18); and the habitat, where a label writes
# a host's name over two lines, a genus above its species (lane H4 of the
# autonomy program, 2026-11-21: in the habitat-only rerun of that day the
# check refused the whole name and accepted one line of it). Every other
# field, places among them, keeps its literal on one line.
ACROSS_LINES = frozenset({"precise_location", "habitat"})
# The field of ACROSS_LINES whose answer read from the transcript over consecutive lines gives way
# where it shares text with another field's (step._taken): the habitat. origin/main 3eb37c11 read a
# habitat from the transcript within one line only (a habitat literal with a line break settled
# there only as a whole organiser candidate of each reading it names, and still does, with the
# claims it had), so that accepting a host read over two lines changes no other field's outcome for
# the same answers (the coordinator's ruling of 2026-11-21 on review round 1 of #464). The precise
# location keeps the rules it had.
GIVES_WAY = frozenset({"habitat"})
# What each of those fields' text is called where the check tells its expert so
# (literal_refusal's retry and experts._Expert._validate_resolved's).
ACROSS_LINES_TEXT = {"precise_location": "A locality", "habitat": "A host or a habitat"}


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
    whole words within one line (verbatim_runs; for a field in ACROSS_LINES,
    the precise location and the habitat, over consecutive lines when it
    holds a line break: written_runs), and it cuts
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


# On the units path (plan WP 2.4, the coordinator's ruling of 2026-11-15 on pilot slide 105526330,
# "IV-25" ending a line above "1948, R.D. Mitchell"): a date field's literal that extends an organiser
# candidate across one line break by the year that starts the next line (year_below, next_line_year).
DATE_FIELDS = frozenset({"date_visited_from", "date_visited_to", "date_identified"})
# A year alone on its line as the date rules read one (date_lines.YEAR_TOKEN: four digits, or two after an
# apostrophe), and the punctuation that may end its token.
_YEAR_TOKEN = re.compile(date_lines.YEAR_TOKEN)
_AFTER_YEAR = ",.;"


def year_below(task: FieldTask, readings: Sequence[Reading], literal: str,
        named: Sequence[Reading]) -> tuple[str, str] | None:
    """A date field's literal of two lines that extends an organiser candidate by the year starting
    the next line, as its first line and its second, or None. (a) Its first line is, exactly, a
    candidate literal of every reading it names (candidate_literal); (b) its second is the first
    token of the next line alone, a year (four digits, or two after an apostrophe), with or
    without the punctuation ending that token ("1948" or "1948," of "1948, R.D. Mitchell"; never
    "1948, R.D." nor the "1948" of "1948,R.D. Mitchell"); (c) every
    reading of the labels it names writes the first line, then a line break, and at each place it
    does so that same token first on the next line. Whether the date rules read the two lines as one
    date is next_line_year's to say."""
    if task.key not in DATE_FIELDS or not named or literal.count("\n") != 1:
        return None
    first, second = literal.split("\n")
    if (not first or first != first.strip() or not _YEAR_TOKEN.fullmatch(second.rstrip(_AFTER_YEAR))
            or candidate_literal(task, readings, first, named) != first):
        return None
    regions = {reading.region_id for reading in named}
    tokens = set()
    for reading in (reading for reading in readings if reading.region_id in regions):
        at = reading.text.find(first + "\n")
        if at < 0:
            return None
        while at >= 0:
            # The next line's first token: what it holds before its first white space.
            tokens.add(re.match(r"\S*", reading.text[at + len(first) + 1:]).group())
            at = reading.text.find(first + "\n", at + 1)
    if len(tokens) != 1 or second not in (token := next(iter(tokens)), token.rstrip(_AFTER_YEAR)):
        return None
    return first, second


def next_line_year(task: FieldTask, readings: Sequence[Reading], literal: str, named: Sequence[Reading],
        date_rules) -> bool:
    """Whether a date field's literal extends an organiser candidate by the year below it
    (year_below) and (d) parse_date, under the profile's date rules, reads the two lines as one date
    at day precision in every reading of its labels, through split_lines. False without date rules."""
    from .checks import DATE_PART, parse_date

    if date_rules is None or year_below(task, readings, literal, named) is None:
        return False
    regions = {reading.region_id for reading in named}
    texts = [reading for reading in readings if reading.region_id in regions]
    found = parse_date(literal, reading_texts=[reading.text for reading in texts], date_rules=date_rules,
        part=DATE_PART.get(task.key), reading_names=[reading.name for reading in texts], field=task.key)
    return (found.status == LookupStatus.SUCCESS and bool(found.readings)
        and all(reading.precision == "day" and "split_lines" in reading.via for reading in found.readings))


# The field that holds a host as written (the ontology's habitat row: "The habitat, host or
# substrate the label writes"), and the heading a label may print or write before the host's
# name, which is not part of it (host_heading).
HOST_FIELD = "habitat"
_HOST_HEADING = re.compile(r"[^\w]*host(?![^\W_])", re.IGNORECASE)


def host_heading(literal: str | None) -> bool:
    """Whether a text starts with the heading "Host": the whole word, letter case aside, with or
    without punctuation around it ("Host <name>", "HOST: <name>", "Host:<name>", "(host) <name>",
    "Host" alone). A word that only starts with it ("Hosts", "Hostel") is none, nor is the word
    anywhere after the first ("on host <name>")."""
    return bool(literal) and _HOST_HEADING.match(literal) is not None


def literal_refusal(task: FieldTask, readings: Sequence[Reading], *, literal: str,
        named: Sequence[Reading], elevations=None, date_rules=None, heading: bool = True) -> Refusal | None:
    """Why the answer's literal may not settle the field, or None: it must be
    a whole candidate literal of each reading it names, whichever reader
    wrote it (no reader is preferred: the owner, 2026-10-25), or text each
    of those readings
    writes as a run of whole words
    within one line (over consecutive lines for a field in ACROSS_LINES, the
    precise location and the habitat, whose literal holds a line break:
    written_runs) that cuts or extends no candidate of it (literal_basis),
    never a shorter or longer piece of a candidate (B2); for a taxon, a
    candidate whose quote writes a longer name from it on is such a piece too
    (_part_of_name), as is text read from a reading that writes a longer
    name around it (_longer_written), and a literal whose genus the label
    marks as doubtful never settles (_genus_in_doubt), nor one the labels
    write as the specimen's host (_host). An elevation, by
    candidate or read from the transcript, settles only a field of the unit
    the reading writes it in (_unit_refusal). Text read from the transcript
    is never one end of a range for a date or an elevation (_part_of_range),
    and never holds a date, an elevation or a range of them for a place or
    the collection code (_another_kind). A precise location, by candidate or read
    from the transcript, holds an elevation only where `elevations` (the
    literals the elevation fields settled, by label; ANY_ELEVATION for the
    expert's own check, before any field settles) holds its elevation text
    for every label it is read from (_another_kind: the ontology's rule
    precise_location_extent, plan WP 2.3b); a candidate is held to the
    elevation rule only, a date or a range in it passing as on main. A
    collectors literal that is a collected_by marker alone ("leg.", "coll.", "Coll.";
    ontology_checks.without_role) settles nothing (ROLE_ONLY: the marker is the role the ontology's
    notation collected_by names, plan WP 2.3c). A habitat literal that starts with the heading
    "Host" settles nothing either (HOST_HEADING, host_heading: the answer is refused, never rewritten;
    lane H4 of the autonomy program); `heading` false leaves that one check out, which only the
    step's pass before its guard on shared text does (step._first_pass), for a resolved heading
    answer that reaches the step; the expert's own check (experts._Expert) takes the default and
    refuses. A date field's literal that
    extends a candidate by the year starting the next line passes where `date_rules`, the profile's,
    read it as one date (next_line_year)."""
    basis = literal_basis(task, readings, literal, named)
    if heading and task.key == HOST_FIELD and host_heading(literal):
        return Refusal(HOST_HEADING, f"{literal!r} starts with the heading \"Host\", which is not part of the "
            "host's name. Give the name written after the heading as the literal, whole (it may stand on the "
            "heading's line or on the lines below it), and leave the heading out; a written \"Ex.\", \"Ex:\", "
            "\"ex\" or \"On\" before the name stays. Answer label_lacks_value when no name follows the heading.")
    if task.key == "collectors":
        from .ontology_checks import without_role

        role = without_role(literal)
        if role is not None and not role.name:
            return Refusal(ROLE_ONLY, f"{literal!r} is the marker of the collectors' role (collected by), not a "
                "name. Give the name it marks as the literal, without the marker, or answer label_lacks_value "
                "when the label names no collector.")
    if basis == CANDIDATE:
        return (_unit_refusal(task, readings, literal, named)
            or (_another_kind(task, literal, named, elevations, elevation_only=True)
                if task.key == "precise_location" else None)
            or _part_of_name(task, readings, literal, named) or _genus_in_doubt(task, readings, literal, named)
            or _host(task, readings, literal))
    if basis == TRANSCRIPT:
        return (_part_of_range(task, readings, literal, named) or _unit_refusal(task, readings, literal, named)
            or _another_kind(task, literal, named, elevations)
            or _longer_written(task, readings, literal, named) or _genus_in_doubt(task, readings, literal, named)
            or _host(task, readings, literal))
    if next_line_year(task, readings, literal, named, date_rules):
        return None
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
        + (f"{ACROSS_LINES_TEXT[task.key]} written over consecutive lines may run over them: copy those lines as the "
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


# The expert's own check of a precise location (experts.py): no field has settled yet, so an
# elevation the rule could accept passes there, and the step decides on what the elevation fields
# settle (literal_refusal's `elevations`).
ANY_ELEVATION = object()
# The precise location is the one field whose text may hold an elevation (precise_location_extent).
ELEVATION_INSIDE = "precise_location"


def elevation_kept(literal: str) -> str | None:
    """The elevation text a precise location may keep (the ontology's rule
    precise_location_extent, plan WP 2.3b), or None: the literal holds one
    text that is plainly another kind of field's (written.other_kind), an
    elevation; nothing but punctuation
    follows it on its line ("Yepocapa, 4800 ft.", "Davao, Prov. 3300'"; not
    "4800 ft. above sea level", "1500 m de altitud" or "1948 M. Smith"); the
    word before it on its line is no month ("Sept. 46'"); and what the
    literal writes besides it holds no other such text and a word that is
    neither a heading, a unit nor a sea-level word: a locality ("4800 ft."
    and "Elev. 6400'" alone have none)."""
    found = written.other_kind(literal, place=True)
    if found is None or found[0] != written.ELEVATION:
        return None
    text = found[1]
    start = literal.find(text)
    end = start + len(text)
    line_end = literal.find("\n", end)
    if any(char.isalnum() for char in literal[end:None if line_end < 0 else line_end]):
        return None
    before = literal[literal.rfind("\n", 0, start) + 1:start].split()
    if before and written._month(before[-1]):
        return None
    left = literal[:start] + " " * len(text) + literal[end:]
    if written.other_kind(left, place=True) is not None:
        return None
    unit_words = written.HEADINGS | written.UNIT_PARTS | written.ELEVATION_WORDS | {"el"}
    if not any(written._bare(word) not in unit_words for word in re.findall(r"[^\W\d_]+", left)):
        return None
    return text


def elevation_settled_inside(literal: str, named: Sequence[Reading], elevations) -> bool:
    """Whether a precise location's literal keeps an elevation (elevation_kept)
    whose text is, after collapse, a literal an elevation field settled from
    each label the literal is read from (`elevations`: label -> literals;
    ANY_ELEVATION holds every text)."""
    kept = elevation_kept(literal)
    if kept is None or elevations is None or not named:
        return False
    if elevations is ANY_ELEVATION:
        return True
    return all(collapse(kept) in {collapse(text) for text in elevations.get(label, ())}
        for label in {reading.region_id for reading in named})


def _another_kind(task: FieldTask, literal: str, named: Sequence[Reading], elevations, *,
        elevation_only: bool = False) -> Refusal | None:
    """_holds_another_kind, except that a precise location
    keeps an elevation an elevation field settled from its label
    (elevation_settled_inside). With `elevation_only` (an organiser candidate,
    which main lets pass), only an elevation is refused: a date or a range
    passes as on main ("Ejido 20 de Noviembre", the coordinator's ruling on
    G51's round 1 of PR #437)."""
    refused = _holds_another_kind(task, literal)
    if elevation_only and refused is not None and refused.reason != HOLDS_AN_ELEVATION:
        return None
    if (refused is not None and task.key == ELEVATION_INSIDE and refused.reason == HOLDS_AN_ELEVATION
            and elevation_settled_inside(literal, named, elevations)):
        return None
    return refused


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
    reader of its label unless the answer names the label's decided
    transcript (its readers' one text, or a person's), which is then the
    label's text (otherwise every reader is: 1A's "cf. Epipsocus sp. 1"
    holds back an answer naming only 1B's "Epipsocus sp. 1"), wherever that
    text writes the literal (1c of #289's fifth review;
    the sixth review's probe 3). The taxon brief has the expert look such a genus up
    alone and answer sources_cannot_resolve; GBIF may still decide it, and
    this refuses an answer that resolves it. None otherwise, and for any
    other field."""
    if task.key != "taxon":
        return None
    want = collapse(literal)
    names = {reading.name for reading in named}
    # Unless the answer names a label's decided transcript, every reader is
    # the label's text: one reader's "cf." holds the genus back whichever
    # reader is named.
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


def _host(task: FieldTask, readings: Sequence[Reading], literal: str) -> Refusal | None:
    """For a taxon, why the literal cannot settle it: it is a host the labels write
    (taxon_host.host_written: its first word is a host marker, or a reading of the specimen
    writes it right after one, the ontology's rule host_is_no_taxon), which Darwin Core holds
    as associatedTaxa, never as the specimen's scientificName. None otherwise, and for any
    other field."""
    from .taxon_host import host_written

    if task.key != "taxon":
        return None
    if host_written(literal, [reading.text for reading in readings]):
        return Refusal(HOST_NAME, (
            f"A label writes {literal!r} after a host marker (Host, ex, on, from): it is the host the "
            "specimen was taken from, never its taxon. Answer for a name the labels give the specimen "
            "itself, or label_lacks_value when they write no other name."))
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
    the labels backs: it is another reader of a label with a decided
    transcript (its readers' one text, or a person's), that transcript does
    not write the text, and no reading of another label writes it as whole
    words (verbatim_runs),
    which could corroborate it (labels). Such a text is raw transcription
    the harness may leverage, never by itself a value (the owner,
    2026-10-25: "It's raw transcription per model that can be leveraged if
    harness wants to think of possibilities LLM may have missed on its
    interpretation"). d10333ff's "BONITELL": reader 1B's line where 1A, the
    label's decided transcript under the old first pass, writes
    "ILLINOIS"."""
    preferred = next((r for r in readings if r.region_id == reading.region_id and r.input_source == DECIDED),
        None)
    return (preferred is not None and preferred is not reading and text not in preferred.text
        and not any(verbatim_runs(other.text, text) for other in readings if other.region_id != reading.region_id))


def disputed(text: str, reading: Reading, readings: Sequence[Reading],
        claimed: Mapping[str, Iterable[str]]) -> bool:
    """Whether the readers of the reading's label dispute the text where the
    reading writes it: every other reader reads that very ink as the text of a
    field of another kind. The label has no decided transcript, it
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


def reader_writes(text: str, literal: str) -> bool:
    """Whether a reading holds the literal's text as whole words anywhere in it, letter case and
    spacing aside (agreement_key's rule for readers that agree: "Shrubs" for "shrubs", "Sp.30" for
    "sp. 30", a line break for a space or for nothing): a letter or a digit stands neither right
    before nor right after it ("Mus" is not written in "Museum"), and a letter, a hyphen or another
    punctuation mark more or less INSIDE the literal's text is another text ("LIPEUS" does not
    write "LIPYCUS", nor "SYLVI-LAGUS" "SYLVILAGUS"); a mark right before or right after it is not
    looked at ("Mus." and "(Mus" write "Mus"). Both sides are folded the same way, by agreement_key's own steps: NFC,
    then str.casefold (the reading keeps its spaces and line breaks so that whole words can be
    told; the literal loses them, agreement_key). So a letter whose folded form is longer than the
    letter (U+00DF, the sharp s, folds to "ss") is the same text on both sides. The place of the
    text in the reading is not looked at: a reading that holds the same text for something else
    writes it. False for a literal with no text."""
    key = agreement_key(literal)
    if not key:
        return False
    pattern = re.compile(r"(?<![^\W_])" + r"\s*".join(re.escape(char) for char in key) + r"(?![^\W_])")
    return pattern.search(unicodedata.normalize("NFC", text).casefold()) is not None


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
# whose readers agree writes one reader's text.
BY_AGREEMENT, BY_SOURCE, BY_NEAR_SPELLING, BY_SAME_PLACE, BY_OTHER_LABEL = (
    "readers_agree", "source", "near_spelling", "same_place", "other_label")
# The least number of readers (distinct readings with text) of a label whose
# agreement backs another label's reader: a label one reader read backs
# nothing (the coordinator's decision of 2026-10-25 on #414's review).
MIN_BACKING_READERS = 2
# The rule (FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md section 4): a label a person
# transcribed settles on the person's text (rule 2), and a candidate's backings are of three
# kinds (rule 3), ranked in a conflict SOURCE above IMAGE above TEXT (rule 5).
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
    # that agree, the image or another label.
    by_source: bool = False
    # How it settled (BY_AGREEMENT and the others); None when it did not.
    basis: str | None = None
    # The reading that holds the label's transcript a person decided
    # (Reading.person_decided), which binds its text; None otherwise.
    person: str | None = None
    # For a label settled on the text the image names through another reader's text one
    # letter from it, which a source confirms by its own name (labels_by_rule's point 1):
    # that text and the readers that write it.
    matched: str | None = None
    matched_by: tuple[str, ...] = ()
    # labels_by_rule's result. Its candidates with their backings; for a settled
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


def labels(task: FieldTask, readings: Sequence[Reading], answers: Sequence[SourceAnswer], *,
        transcript: str | None = None, offered: Iterable[str] = ()) -> dict[str, Label]:
    """Each label that writes the field, by region, settled by the rule of
    FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md section 4 (labels_by_rule): each label's
    readings, the organiser's literals and the texts offered to every label, whichever
    readings the answer names: the answer's literal when it is read from the transcript
    (`transcript`), and `offered`."""
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


def _key_mapped(reading: Reading, other: Reading, cover: list, start: int, end: int) -> tuple[int, int] | None:
    """The reading's place (start, end) over the units `cover` as offsets of `other`'s text:
    through the agreement key's offsets (_key_offset), where the two readers' texts over
    those units are the same, letter case and spacing aside, and the span, its white space
    at either end left out, is a place literal_places finds for `other`'s own text there;
    else None ("\u03b1" of "\u03b1 \u03b9" maps to no place of "\u03b1" with a combining
    ypogegrammeni, nor "\u03b9" of "x \u03b9" to one of "x" and a combining ypogegrammeni)."""
    if other.observation_id not in cover[0].readers:
        return None
    low, high = _span(reading, cover)
    their_low, their_high = _span(other, cover)
    mine, theirs = reading.text[low:high], other.text[their_low:their_high]
    if not theirs.strip() or agreement_key(theirs) != agreement_key(mine):
        return None
    first = _key_offset(theirs, agreement_key(reading.text[low:start]))
    last = _key_offset(theirs, agreement_key(reading.text[low:end]))
    if first is None or last is None or first >= last:
        return None
    low, high = their_low + first, their_low + last
    while low < high and other.text[low].isspace():
        low += 1
    while high > low and other.text[high - 1].isspace():
        high -= 1
    text = collapse(other.text[low:high])
    if not text or (low, high) not in literal_places(other.text, text):
        return None
    return low, high


def _label_texts(group: Sequence[Reading], offered: Iterable[str]
        ) -> tuple[list[frozenset[str]], tuple[str, ...], dict[str, frozenset[str]]]:
    """Each reader's candidates for the field, the texts readers write at their places that
    are no candidate, and, by agreement key, the readers that agree on a candidate. A
    literal offered for the label (`offered`: its readers' organiser literals and the
    expert's literal) is a candidate of each reader in whose own text it is found
    (literal_places; inside a word only where no reader of the label writes it as whole
    words), in that reader's spelling there; and of each reader whose text over
    the covering units of one of those places is that reader's, letter case and spacing
    aside, in its own spelling, through the agreement key's offsets (_key_mapped). The
    readers that agree on a candidate are, at the place where most do, its reader and those
    whose text over its covering units is the same and into whose text the candidate maps
    so ("s" of "s s" maps into no part of "\u00df"). A reader that writes another text over those units
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
                for other_index, other in enumerate(group):
                    mapped = _key_mapped(reading, other, cover, start, end) if other is not reading else None
                    if mapped is not None:
                        found[other_index].add(collapse(other.text[mapped[0]:mapped[1]]))
    blocked: list[str] = []
    agreeing: dict[str, frozenset[str]] = {}
    for index, reading in enumerate(group):
        for text in found[index]:
            best = frozenset({reading.observation_id})
            for (start, end), cover in _covered(reading, text):
                mine = over(reading, cover)
                same = {reading.observation_id}
                for other_index, other in enumerate(group):
                    theirs = over(other, cover) if other is not reading else None
                    if not theirs or not theirs.strip():
                        continue
                    if agreement_key(theirs) == agreement_key(mine):
                        if _key_mapped(reading, other, cover, start, end) is not None:
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
    reader writes it: inside a place of the other's in the same reader (an organiser's line
    inside the expert's two-line locality), or inside a place of the other's in another
    reader as mapped into this one through the agreement key's offsets (_key_mapped). One
    place of it outside every such place ("forest" after "dry forest; " in one unit, or on
    a line of its own; 1B's "Mt. McKinley" where 1A writes "E Slope Mt. McKinley" over
    more units) keeps it a rival."""
    found = False
    for reading, own in zip(group, each):
        spans = []
        for other, theirs in zip(group, each):
            for one in theirs & outer:
                if other is reading:
                    spans.extend((low, high, True) for low, high in literal_places(reading.text, one))
                    continue
                for (low, high), cover in _covered(other, one):
                    mapped = _key_mapped(other, reading, cover, low, high)
                    if mapped is not None:
                        spans.append((*mapped, False))
        for text in own & inner:
            for start, end in literal_places(reading.text, text):
                if not any(low <= start and end <= high and (not same or (low, high) != (start, end))
                        for low, high, same in spans):
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


def labels_by_rule(task: FieldTask, regions: Mapping[str, Sequence[Reading]],
        literals: Mapping[str, Iterable[str]], allowed: Mapping[str, Mapping[str, str]],
        answers: Sequence[SourceAnswer], *, sourced: bool, offered: Sequence[str] = ()) -> dict[str, Label]:
    """`labels`: each label that writes the field, settled by the rule of
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
    2. A label whose transcript a person decided (Reading.person_decided) settles on the
       person's text, cleared (BY_PERSON): the person's spelling (_spelling) where every
       reader of the label writes the same text, letter case and spacing aside; else the
       person's one candidate literal; else, where the person's reading has several texts
       for the field, the one the field's sources confirm (_by_source). A text of the
       person's inside another of theirs is set aside (_within); a label whose person's
       reading writes nothing for the field takes no part.
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
        bound = preferred is not None and preferred.person_decided
        writers: dict[str, set[str]] = {}
        if bound:
            # Offered text as the field writes it (written_runs: over consecutive lines for a
            # field in ACROSS_LINES), and the person's texts inside another of them set aside.
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
        received: Sequence[SourceAnswer], transcript: str | None = None) -> Refusal | None:
    """Why readers or labels that disagree do not settle the field on this answer, or None
    (B1 of #284's reviews; G19, G20, G27, G32, N4): the labels as labels_by_rule settles
    them (_disagreement_by_rule), the answer's literal offered to every label when it is
    read from the transcript (`transcript`)."""
    sources = frozenset(task.tools) & SOURCE_IDS
    answers = [a for a in received if a.source_id in sources]
    found = labels(task, readings, answers, transcript=transcript)
    if not found:
        return None
    return _disagreement_by_rule(task, readings, found, literal=literal, authority_id=authority_id, cited=cited,
        answers=answers, sources=sources)


def _unbacked(label: Label) -> bool:
    """A label that settles nothing and none of whose candidates has a backing."""
    return not (label.settled or label.person or label.tied or label.options
        or any(candidate.backings for candidate in label.candidates))


def _as_written(readings: Sequence[Reading], text: str) -> str | None:
    """A label's text (collapsed: one space for each run of white space) as the first of
    `readings` that holds it writes it: that reading's own characters at its first place
    there (literal_places), which an answer can copy; None when none of them holds it."""
    for reading in readings:
        for start, end in literal_places(reading.text, text)[:1]:
            return reading.text[start:end]
    return None


def _disagreement_by_rule(task: FieldTask, readings: Sequence[Reading], found: Mapping[str, Label], *,
        literal: str, authority_id: str | None, cited: Sequence[SourceAnswer], answers: Sequence[SourceAnswer],
        sources: frozenset[str]) -> Refusal | None:
    """_disagreement: the labels as labels_by_rule settles them, with
    retries that say what to answer, never how the rule decides (PR #425's seventh to ninth
    rounds). A retry prints a text only as a reading writes it (_as_written; a person's text
    as the person's reading writes it) and leaves out a text no reading holds; where fewer
    than two texts are left for several_possibilities, or none to copy, it asks for
    sources_cannot_resolve. A field with no approved source (`sources` empty) is not told
    to ask one. A label none of whose candidates has a backing is no evidence against a
    text another label backs: while another label settles or has a backed candidate, it
    takes no part."""

    def written(text: str) -> str | None:
        return _as_written(readings, text)

    def quoted(texts: Iterable[str], among: Sequence[Reading] = readings) -> list[str]:
        return [found for text in texts if (found := _as_written(among, text)) is not None]

    if any(not _unbacked(label) for label in found.values()):
        found = {region: label for region, label in found.items() if not _unbacked(label)}
    settled = frozenset().union(*(label.settled for label in found.values()))
    texts = quoted(sorted(frozenset().union(*(label.literals | frozenset(label.blocked) for label in found.values()))))
    shown = "; ".join(repr(text) for text in texts)

    def opening(rest: str, field: str = "") -> str:
        """`rest` after the readers' texts, or alone when no reading writes one of them."""
        return f"The readers write {shown}{field}, and {rest}" if shown else rest[:1].upper() + rest[1:]

    heading = f"The readers write {shown}. " if shown else ""
    persons = [label for label in found.values() if label.person and collapse(literal) not in label.settled]
    if persons:
        [label, *_] = persons
        own = [reading for reading in readings if reading.name == label.person]
        theirs = quoted(sorted(label.settled), own)
        theirs = f", which writes {', '.join(repr(text) for text in theirs)} for this field" if theirs else ""
        return Refusal(PERSON_DECIDED, (
            f"A person transcribed this label: reading {label.person} holds their transcription{theirs}. Answer "
            f"with the literal from reading {label.person}, naming that reading (a source answer you cite may "
            "give its value, with its authority_id), or answer several_possibilities or sources_cannot_resolve."),
            differ=True)
    tied = [label for label in found.values() if label.tied]
    contested = tied or [label for label in found.values() if label.options]
    if contested:
        options = tuple(dict.fromkeys(option for label in contested for option in label.options))
        printed = quoted(options)
        listed = ", ".join(repr(option) for option in printed)
        retry = (opening(f"the evidence does not settle one of {listed}: a person chooses. Answer "
            f"several_possibilities with {listed}.") if len(printed) >= 2 else
            opening("the evidence does not settle one text: a person chooses. Answer sources_cannot_resolve."))
        if tied:
            return Refusal(TIED, retry, differ=True, options=options)
        return Refusal(TEXTS_CONTESTED, retry, differ=True, options=options)
    if all(label.settled for label in found.values()) and len(settled) == 1 and not any(
            label.by_source for label in found.values()):
        [one] = settled
        if collapse(literal) == one:
            return None
        copy = written(one)
        if copy is None:
            return Refusal(DIFFER, heading + "Answer sources_cannot_resolve.", differ=True)
        return Refusal(DIFFER, opening(
            f"the evidence settles on {copy!r}. Copy the literal {copy!r} exactly from a reading that writes it, "
            "and name only readings that write it so; or "
            + ("ask your approved sources about each reader's text, or " if sources else "")
            + "answer several_possibilities."), differ=True)
    unsettled = [label for label in found.values() if not label.settled]
    if unsettled:
        retry = opening("the evidence does not settle one reader's text. "
            + ("Look each reader's text up in your approved sources, or answer " if sources else "Answer ")
            + ("several_possibilities with each reader's text as its options, or sources_cannot_resolve."
               if len(texts) >= 2 else "sources_cannot_resolve."), field=" for this field")
        if any(len({agreement_key(text) for text in label.literals}) > 1 or label.blocked or label.writing > 1
                for label in unsettled):
            return Refusal(DIFFER, retry, differ=True)
        return Refusal(ONE_READER, retry, differ=True)
    refused = _sourced_refusal(task, found, settled, shown, literal=literal, authority_id=authority_id, cited=cited,
        answers=answers, sources=sources, written=written)
    if refused is not None and refused.reason == LABELS_DIFFER:
        # _sourced_refusal's retry says when such labels settle; this one says what to answer.
        return Refusal(LABELS_DIFFER, (
            "The labels write different text for this field" + (f" ({shown})" if shown else "") + ". "
            + ("Ask your approved sources about each label's text, give the authority_id of the place or name "
               "they confirm and cite the answer for your literal, or answer " if sources else "Answer ")
            + ("several_possibilities with each label's text." if len(texts) >= 2 else "sources_cannot_resolve.")),
            differ=True)
    return refused


def _source_members(task: FieldTask, readings: Sequence[Reading], received: Sequence[SourceAnswer], literal: str,
        *, transcript: str | None) -> frozenset[str]:
    """The other texts of the source-backed candidate whose texts hold the literal, letter
    case and spacing aside the literal (labels_by_rule's Backed.texts)."""
    sources = frozenset(task.tools) & SOURCE_IDS
    found = labels(task, readings, [a for a in received if a.source_id in sources], transcript=transcript)
    want = collapse(literal)
    return frozenset(text for label in found.values() for candidate in label.candidates
        if SOURCE in candidate.backings and want in candidate.texts for text in candidate.texts
        if text != want and agreement_key(text) == agreement_key(want))


def _sourced_refusal(task: FieldTask, found: Mapping[str, Label], settled: frozenset[str], shown: str, *,
        literal: str, authority_id: str | None, cited: Sequence[SourceAnswer], answers: Sequence[SourceAnswer],
        sources: frozenset[str], written: Callable[[str], str | None]) -> Refusal | None:
    """_disagreement's last checks, for labels that all settle and a source settled one
    of them, or for labels that settle on different texts: the answer's literal is the
    labels' text and cites the answer confirming it, or one authority confirms each. Each
    text a retry names is as a reading writes it (`written`, _as_written), a retry with no
    such text to copy asks for sources_cannot_resolve, and the near spelling's retry says
    only what to answer."""
    say = written
    cited = [a for a in cited if a.source_id in sources]
    want = collapse(literal)
    if len(settled) == 1:
        [one] = settled
        # The texts of the settled candidate a source backs, letter case and spacing aside
        # the settled text (Backed.texts); any of them, confirmed, is the answer.
        members = frozenset(text for label in found.values() for candidate in label.candidates
            if SOURCE in candidate.backings and one in candidate.texts for text in candidate.texts
            if agreement_key(text) == agreement_key(one)) or frozenset({one})
        if want not in members:
            spelled = next((label for label in found.values() if label.matched and label.settled == {one}), None)
            if spelled is not None:
                return Refusal(DIFFER, (
                    f"Give {say(one)!r} as the literal, naming the reading that writes it, and the source's "
                    "candidate as the value with its authority_id." if say(one) is not None
                    else "Answer sources_cannot_resolve."), differ=True)
            if say(one) is None:
                return Refusal(DIFFER, "Answer sources_cannot_resolve.", differ=True)
            return Refusal(DIFFER, (
                f"The labels settle on the reader's text {say(one)!r}: copy the literal from a reading "
                "that writes it, or answer several_possibilities."), differ=True)
        if not any(identities(cited, member, task.key, near=True) for member in members):
            return Refusal(DIFFER, (
                "Cite the evidence_id of the source answer that confirms "
                + (repr(say(one)) if say(one) is not None else "your literal")
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
            (f"The readers write {shown}, which a source confirms" if shown else "A source confirms the readers' texts")
            + " as the same place: give one reader's text as the literal, that place's authority_id, and cite the "
            "answer that confirms your literal."), differ=True)
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
# determiner may be a collector. Verbatim D/T/S may share any field's text;
# the museum has set no validation rule yet for its date and time
# expressions (PRD.md:1224). Any other field is a kind of its own.
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
        cited: Sequence[SourceAnswer], received: Sequence[SourceAnswer], elevations=None,
        date_rules=None, heading: bool = True) -> Refusal | None:
    """Why a resolved answer may not settle its field, or None.

    `named` are the readings the answer names (each already writes the
    literal), `cited` the source answers it cites and `received` every source
    answer its field received; `elevations`, `date_rules` and `heading` as
    literal_refusal takes them."""
    refused = literal_refusal(task, readings, literal=literal, named=named, elevations=elevations,
        date_rules=date_rules, heading=heading)
    if refused is not None:
        return refused
    # The answer's literal is offered to every label, whatever readings it names.
    transcript = literal
    refused = _disagreement(task, readings, literal=literal, authority_id=authority_id, cited=cited,
        received=received, transcript=transcript)
    if refused is not None:
        return refused
    if task.key in PLACE_VALUE_FIELDS:
        settled_value = value if value is not None else literal
        found = place_settling(task, literal, settled_value, authority_id, cited)
        if found is None:
            # The cited answer may confirm another spelling of the source-backed candidate the
            # literal settles with ("Chimaltenango" for "Chi mal ten ango").
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
