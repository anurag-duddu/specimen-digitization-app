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

Stored shape, read by `stored_candidates` (the single read contract, for these rows
and for the whole-region rows the extraction call wrote before the organiser) and
by the harness hand-over:

- the field's value follows `field_resolution.Resolver` (G19, G27, G32), label by
  label and then across labels, whatever the order of the model's answer: a label
  with a decided transcript has the decided reading's literal; a label with none has
  a value only when EVERY reading of it states the same literal; labels that all
  have a value and agree leave the field SUPPORTED with that literal; any other mix
  (a reader that does not state it, readers or labels that differ) leaves it
  AMBIGUOUS with NO literal: none is chosen. `harness.apply_candidates` has the rules
  in full; tests/test_organiser.py runs both on every combination of one and two
  labels and compares.
- a candidate quoted from the other reader's reading of a DECIDED label is evidence
  beside the value: it never changes the literal or the state. Where the decided
  transcript has no value for the field, the field stays UNKNOWN and still cites
  that row.
- `run.fields[key].evidence_ids` lists the row of EVERY verified candidate of the
  field, whatever its state, the value's rows first, then in label order. The rows
  are what the harness checks against the raw readings.
- a row is a candidate row when its source is `bounded_extraction_v1` and its
  locator parses (`parse_locator`). Its `observation_ids` is the one reading it
  quotes. The quote is `excerpt`; the literal is
  `reading_text[literal_start:literal_end]` and lies inside the quote.
- a row the extraction call wrote before the organiser has the locator
  `region:<region_id>`, the whole region transcript as its excerpt and every
  reader's observation ID; only the field's FIRST row carries the field's own
  literal (later rows of an AMBIGUOUS field carry a literal the run never stored),
  so `stored_candidates` returns that one, with no label and no spans.
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
    """One candidate as the ordinary run stored it: the same structure for a row the
    organiser wrote and for a whole-region row the extraction call wrote before it
    (`legacy`: no label, no spans, the readings of the whole region)."""

    field_key: str
    literal: str
    quote: str
    evidence_id: str
    region_id: str | None
    label: str | None  # 1A, 2B ...; None for a legacy row
    observation_ids: tuple[str, ...]  # the one reading cited; a legacy row: all the region's
    quote_span: tuple[int, int] | None  # in that reading's text; None for a legacy row
    literal_span: tuple[int, int] | None
    primary: bool  # the first row whose literal is the field's own (None when AMBIGUOUS: never)

    @property
    def legacy(self) -> bool:
        return self.label is None

    @property
    def observation_id(self) -> str | None:
        """The one reading cited (None for a legacy row, which cites every reader's)."""
        return self.observation_ids[0] if len(self.observation_ids) == 1 else None

    @property
    def quote_start(self) -> int | None:
        return self.quote_span[0] if self.quote_span else None

    @property
    def literal_start(self) -> int | None:
        return self.literal_span[0] if self.literal_span else None

    @property
    def literal_end(self) -> int | None:
        return self.literal_span[1] if self.literal_span else None


def reading_texts_of(run) -> dict[str, str]:
    """The texts `stored_candidates` needs, from a run: each observation's text under its
    ID, and each organiser reading's text under `"<label>:<observation id>"`, which is
    the key that finds a reviewer-edited decided text (it shares the machine-selected
    observation's ID but not its text)."""
    texts = {o.id: o.literal_text for o in getattr(run, "observations", None) or []}
    for name, reading in labelled(extraction_readings(run)).items():
        texts[f"{name}:{reading.observation_id}"] = reading.text
    return texts


def stored_candidates(
    fields: Mapping[str, FieldValue],
    evidence: Sequence[Evidence],
    reading_texts: Mapping[str, str],
) -> list[StoredCandidate]:
    """The extraction call's candidates as the ordinary run stored them, per field in the
    field's own order: the single read contract.

    `reading_texts` maps an observation ID (or `"<label>:<observation id>"`, which wins;
    see `reading_texts_of`) to the text the spans index. A row whose spans do not fit
    the text it names is skipped: a stored candidate is never guessed. Rows of every
    state of field are returned (an AMBIGUOUS field's candidates, a lead under an
    unknown field), so a field whose literal is None still hands over what each reading
    states.

    A row from before the organiser (source `bounded_extraction_v1`, locator
    `region:<region_id>`) is returned only when it is the field's first row and the
    field's own literal lies in its excerpt: that is the one literal such a row can
    stand for. It has no label and no spans; its excerpt is the whole region transcript
    and its observation IDs are every reader's of the region.
    """
    by_id = {e.id: e for e in evidence}
    found: list[StoredCandidate] = []
    for key, value in fields.items():
        primary_taken = False
        for place, evidence_id in enumerate(value.evidence_ids):
            row = by_id.get(evidence_id)
            if row is None or row.source != SOURCE or row.kind != "literal":
                continue
            location = parse_locator(row.locator)
            if location is None:
                if (
                    place == 0
                    and row.region_id
                    and row.locator == "region:" + row.region_id
                    and value.literal
                    and value.literal in row.excerpt
                ):
                    found.append(
                        StoredCandidate(
                            field_key=key,
                            literal=value.literal,
                            quote=row.excerpt,
                            evidence_id=row.id,
                            region_id=row.region_id,
                            label=None,
                            observation_ids=tuple(row.observation_ids),
                            quote_span=None,
                            literal_span=None,
                            primary=not primary_taken,
                        )
                    )
                    primary_taken = True
                continue
            text = reading_texts.get(f"{location.label}:{location.observation_id}")
            if text is None:
                text = reading_texts.get(location.observation_id)
            if (
                text is None
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
                    literal=literal,
                    quote=row.excerpt,
                    evidence_id=row.id,
                    region_id=row.region_id,
                    label=location.label,
                    observation_ids=(location.observation_id,),
                    quote_span=(location.quote_start, location.quote_end),
                    literal_span=(location.literal_start, location.literal_end),
                    primary=primary,
                )
            )
    return found
