"""When a field's readers disagree, and what may settle it (B1 of #284's review).

The native rules this ports, where the native code is the stricter:
- A label with a decided transcript takes that reading's literal, whatever the
  other reader wrote (G19; harness.apply_candidates and field_resolution): a
  resolved literal is text that reading writes, and another reader's
  difference is evidence only.
- Readers that disagree with no decided transcript to settle them settle only
  when a success answer of the field's approved sources confirms exactly one
  reader's literal (G20); otherwise the field goes to review
  (research_harness/evidence.py 937-942, "literal assertions disagree without
  source settlement"). A field with no approved source cannot settle them.
- A place field settles only on a place source's success answer whose
  candidate is the value (evidence.py 920-926 and _candidate_matches).

A field disagrees when the organiser marked it ambiguous, or when its
candidates across readers carry more than one literal. Literals are compared
after NFC and whitespace collapse only (checks.collapse): "E. slope" and
"E.slope" disagree; the owner has not ruled such differences equal.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from specimen_digitization.application.domain import LookupStatus, ValueState

from .checks import collapse, taxon_query_grounded
from .contracts import PLACE_SOURCES, FieldTask, Reading, SourceAnswer

DECIDED = "decided_transcript"
# Place fields whose value a place source settles; precise_location is
# verbatim text, checked against places and never replaced (PRD 515).
PLACE_VALUE_FIELDS = frozenset({"country", "province_state", "county", "city"})
SOURCE_IDS = frozenset({"gbif", *PLACE_SOURCES})

# The field's reason when a resolved answer cannot settle it (plain app text).
DIFFER = "The readings differ, and no approved source confirms one of them."
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


def contested(task: FieldTask, readings: Sequence[Reading]) -> frozenset[str] | None:
    """The literals still in contention, or None when the readers do not
    disagree or the decided transcripts settle it (G19).

    The organiser keeps a value for readers that differ only where a decided
    transcript decides (harness._settle), so a supported organiser value is
    settled. Otherwise the other reader of a decided label is evidence only,
    and what remains is contested; an ambiguous field with no literal left
    contests nothing a source could confirm."""
    literals = reader_literals(task, readings)
    every = {literal for found in literals.values() for literal in found}
    state = task.current.state
    if state == ValueState.SUPPORTED or (state != ValueState.AMBIGUOUS and len(every) <= 1):
        return None
    by_name = {r.name: r for r in readings}
    decided = {r.region_id: r.name for r in readings if r.input_source == DECIDED}
    kept: set[str] = set()
    for name, found in literals.items():
        region = by_name[name].region_id
        if region in decided and decided[region] != name:
            continue
        kept |= found
    regions = {by_name[name].region_id for name in literals}
    if state != ValueState.AMBIGUOUS and len(kept) == 1 and regions <= set(decided):
        return None
    return frozenset(kept)


def confirmed(literals: Iterable[str], answers: Iterable[SourceAnswer],
        sources: Iterable[str]) -> set[str]:
    """The literals a success answer of `sources` confirms: GBIF asked about
    exactly that name (checks.taxon_query_grounded), or a place source
    returned a candidate of exactly that name."""
    sources = frozenset(sources) & SOURCE_IDS
    literals = set(literals)
    found: set[str] = set()
    for answer in answers:
        if answer.status != LookupStatus.SUCCESS or answer.source_id not in sources:
            continue
        for literal in literals:
            if answer.source_id == "gbif":
                if taxon_query_grounded(answer.query, literal):
                    found.add(literal)
            elif any(collapse(c.name) == literal for c in answer.candidates):
                found.add(literal)
    return found


def place_confirmed(task: FieldTask, settled: str, authority_id: str | None,
        cited: Iterable[SourceAnswer]) -> bool:
    """Whether a cited success answer of the field's place sources has the
    settled value as a candidate, with the answer's authority_id."""
    sources = frozenset(task.tools) & frozenset(PLACE_SOURCES)
    return any(
        answer.source_id in sources and answer.status == LookupStatus.SUCCESS
        and any(collapse(c.name) == collapse(settled) and c.authority_id == authority_id
            for c in answer.candidates)
        for answer in cited
    )


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
    found = contested(task, readings)
    if found is not None:
        sources = frozenset(task.tools) & SOURCE_IDS
        settled = confirmed(found, received, sources)
        if len(settled) != 1:
            shown = "; ".join(sorted(found)) or "no single text"
            return Refusal(DIFFER, (
                f"The readers disagree on this field ({shown}) and no approved source answer "
                "confirms exactly one reader's text, so a person must choose: answer "
                "several_possibilities with each reader's text, or sources_cannot_resolve."),
                differ=True)
        [one] = settled
        if collapse(literal) != one:
            return Refusal(DIFFER, (
                f"A source confirms the reader's text {one!r}: copy the literal from the reading "
                "that writes it, or answer several_possibilities."), differ=True)
        if not confirmed([one], cited, sources):
            return Refusal(DIFFER, (
                f"Cite the evidence_id of the source answer that confirms {one!r}."), differ=True)
    if task.key in PLACE_VALUE_FIELDS:
        settled_value = value if value is not None else literal
        if not place_confirmed(task, settled_value, authority_id, cited):
            return Refusal(NO_PLACE, (
                "A place field settles only on a place source's success answer whose candidate "
                "is the value: cite its evidence_id, give that candidate's name (as value, or as "
                "the literal when they are the same) and its authority_id. Otherwise answer "
                "several_possibilities or sources_cannot_resolve."))
    return None
