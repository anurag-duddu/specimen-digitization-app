"""The organiser: what the first agent reads, and how its candidates are stored.

The owner's words (2026-10-03, relayed by the go-live coordinator): "maybe the
LLM that looks at the raw transcript can organize the data into field value
pairs and share it with the harness along with the transcript. Because if the
data is kinda spread out on different labels it becomes a little chaotic. taxa
can be on multiple else. So the first agent LLM that interfaces with raw VLM
transcripts can do this. The reason raw transcript is important is because LLM
can make mistakes and invent stuff so evidence is always necessary."

The ordinary pipeline's extraction call (`harness.extract_with_agent`) is that
first agent. This module holds the parts that are not the model call:

- `extraction_readings`: every non-empty reading of every label, decided or raw,
  in label order. A label with no decided transcript still has its readings.
- `request_text`: those readings as the model reads them, each named by
  `field_harness.labelled` (1A, 1B, 2A ...), the stage-7 harness's own naming.
- the stored shape of a candidate, with no typed field added to `Evidence` or
  `FieldValue` (`domain.py` is hashed into the projector pin): one `Evidence`
  row per verified candidate, its `excerpt` the narrow quote, its `locator` the
  reading label, the reading's observation ID and two spans, all computed by
  `harness.apply_candidates` from the strings it verified and never claimed by
  the model.

Stored shape, read by `stored_candidates` and by the harness hand-over:

- a label's decided transcript is its verbatim (G19, G27), so only a candidate
  quoted from a decided transcript, or from a reading of a label with none, sets or
  contests a field's value. `run.fields[key].literal` is the primary: the first such
  candidate in the model's order, the decided ones first.
- two such candidates with the same literal (two labels, or the two readers of an
  undecided label) leave the field SUPPORTED with a row each; differing literals
  leave it AMBIGUOUS (G32), the primary literal kept.
- a candidate quoted from the other reader's reading of a DECIDED label is evidence
  beside the value: it never changes the literal or the state. Where the decided
  transcript has no value for the field, the field stays UNKNOWN and still cites
  that row.
- `run.fields[key].evidence_ids` lists the field's candidate rows, the value's rows
  first.
- a row is a candidate row when its source is `bounded_extraction_v1` and its
  locator parses (`parse_locator`). Its `observation_ids` is the one reading it
  quotes. The quote is `excerpt`; the literal is
  `reading_text[literal_start:literal_end]` and lies inside the quote.
- offsets are 0-based, end-exclusive character indices (Python `str`) into that
  reading's text, as `initial_requests._graph` counts fragment offsets. When the
  quote or the literal occurs more than once, the first occurrence is meant: any
  occurrence is the same text, so the evidence is the same.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from .domain import Evidence, FieldValue
from .field_harness import labelled
from .field_resolution import DECIDED, RAW, Reading

# The ordinary extraction call's evidence source, unchanged: rows written before
# the organiser carry it too, with a `region:<id>` locator that does not parse.
SOURCE = "bounded_extraction_v1"

_LOCATOR = re.compile(
    r"reading:(?P<label>[0-9]+[A-Z]):(?P<observation>[^#;\s]+)"
    r"#quote=(?P<qs>[0-9]+)-(?P<qe>[0-9]+);literal=(?P<ls>[0-9]+)-(?P<le>[0-9]+)"
)


@dataclass(frozen=True)
class CandidateLocation:
    """Where a verified candidate sits: a reading, and two spans of its text."""

    label: str
    observation_id: str
    quote_start: int
    quote_end: int
    literal_start: int
    literal_end: int


def format_locator(location: CandidateLocation) -> str:
    return (
        f"reading:{location.label}:{location.observation_id}"
        f"#quote={location.quote_start}-{location.quote_end}"
        f";literal={location.literal_start}-{location.literal_end}"
    )


def parse_locator(locator: str | None) -> CandidateLocation | None:
    """The location a candidate row's locator names; None for any other locator
    (a keyed label line's `region:<id>`, a lookup's, a row from before the
    organiser)."""
    found = _LOCATOR.fullmatch(locator or "")
    if found is None:
        return None
    return CandidateLocation(
        found["label"],
        found["observation"],
        int(found["qs"]),
        int(found["qe"]),
        int(found["ls"]),
        int(found["le"]),
    )


def extraction_readings(run) -> list[Reading]:
    """Every non-empty reading of every label of the specimen, label by label.

    A label with a decided transcript lists it first (role `decided_transcript`,
    the transcript's own text, cited to the reading the first pass selected), then
    each other reading as a raw reading. A label with none lists all its readings
    as raw readings. The extraction child has no observations: the parent builds
    this list and hands it over as `run.readings`.
    """
    explicit = getattr(run, "readings", None)
    if explicit is not None:
        return list(explicit)
    observations = list(getattr(run, "observations", None) or [])
    transcripts = {t.region_id: t for t in getattr(run, "transcripts", None) or []}
    regions = [r.id for r in getattr(run, "regions", None) or []]
    regions += [o.region_id for o in observations] + list(transcripts)
    readings: list[Reading] = []
    for region in dict.fromkeys(regions):
        transcript = transcripts.get(region)
        anchor = None
        if transcript is not None and transcript.resolved and transcript.text:
            ids = list(transcript.observation_ids)
            selected = transcript.selected_observation_id
            anchor = selected if selected in ids else (ids[0] if ids else None)
        if anchor is not None:
            readings.append(Reading(region, anchor, DECIDED, transcript.text))
        for observation in observations:
            if observation.region_id != region or not observation.literal_text.strip():
                continue
            if anchor == observation.id and observation.literal_text == transcript.text:
                continue  # This reading is the decided transcript, listed above.
            readings.append(Reading(region, observation.id, RAW, observation.literal_text))
    return readings


def request_text(field_keys: Iterable[str], names: Mapping[str, Reading]) -> str:
    """The user message: the fields, then every reading under its label, as plain
    text so that the model copies a quote exactly as written (JSON would escape
    newlines, quotes and non-ASCII characters)."""
    lines = ["Fields: " + ", ".join(field_keys)]
    decided = {r.region_id for r in names.values() if r.role == DECIDED}
    region = None
    for name, reading in names.items():
        if reading.region_id != region:
            region = reading.region_id
            absent = "" if region in decided else " (no decided transcript)"
            lines += ["", f"Label {name[:-1]}{absent}"]
        kind = "decided transcript" if reading.role == DECIDED else "raw reading"
        lines += ["", f"Reading {name} ({kind}):", reading.text, f"End of reading {name}."]
    return "\n".join(lines)


@dataclass(frozen=True)
class StoredCandidate:
    field_key: str
    label: str
    observation_id: str
    literal: str
    quote: str
    evidence_id: str
    primary: bool


def stored_candidates(
    fields: Mapping[str, FieldValue],
    evidence: Sequence[Evidence],
    reading_texts: Mapping[str, str],
) -> list[StoredCandidate]:
    """The organiser's candidates as `apply_candidates` stored them, per field in
    the field's own order. `reading_texts` maps an observation ID to the text the
    spans index (the observation's literal text). A row whose spans do not fit
    the text it names is skipped: a stored candidate is never guessed."""
    by_id = {e.id: e for e in evidence}
    found: list[StoredCandidate] = []
    for key, value in fields.items():
        primary_taken = False
        for evidence_id in value.evidence_ids:
            row = by_id.get(evidence_id)
            location = parse_locator(row.locator) if row else None
            text = reading_texts.get(location.observation_id) if location else None
            if (
                row is None
                or location is None
                or row.source != SOURCE
                or text is None
                or text[location.quote_start : location.quote_end] != row.excerpt
                or not location.quote_start <= location.literal_start
                or not location.literal_end <= location.quote_end
                or location.literal_start >= location.literal_end
            ):
                continue
            literal = text[location.literal_start : location.literal_end]
            primary = literal == value.literal and not primary_taken
            primary_taken = primary_taken or primary
            found.append(
                StoredCandidate(
                    field_key=key,
                    label=location.label,
                    observation_id=location.observation_id,
                    literal=literal,
                    quote=row.excerpt,
                    evidence_id=row.id,
                    primary=primary,
                )
            )
    return found
