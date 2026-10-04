"""Bounded typed extraction: the organiser. Proposed values must match retained source text.

One text-only call per specimen reads every reading of every label, decided or
raw, and organises what they state into field-value candidates, each quoted from
one named reading (organiser.py). Trusted code keeps a candidate only when its
quote is a verbatim piece of that reading and its literal a verbatim piece of the
quote, and computes every offset itself.
"""

import hashlib
import re

from pydantic import Field
from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits
from pydantic_ai.messages import ModelMessagesTypeAdapter
from ..prompts import PromptName, ResolvedPrompt
from .domain import Record, Evidence, FieldValue, ValueState
from .extraction_guard import extraction_refusal
from .field_harness import labelled
from .field_resolution import DECIDED
from .organiser import (
    SOURCE,
    CandidateLocation,
    extraction_readings,
    format_locator,
    request_text,
)
from .reliability import run_agent_bounded

COMPETING = "Competing source-supported extraction candidates"
LEAD = "Only the other reader's reading states a value: kept as evidence, not as the value"


# One field value as one reading states it. There is no offset or span for the model
# to claim: the code finds the quote in the reading, and the literal in the quote,
# itself. (A comment, not a docstring: a docstring is part of the schema the model
# is shown.)
class ExtractionCandidate(Record):
    field_key: str
    reading: str = Field(
        description="The one reading you quote, named as in the request, such as 1A."
    )
    literal: str = Field(
        min_length=1,
        max_length=2000,
        description="The value exactly as that reading writes it, copied from the quote.",
    )
    source_excerpt: str = Field(
        min_length=1,
        max_length=4000,
        description=(
            "A short piece of that reading, copied exactly, that contains the literal: "
            "normally the one line it is on."
        ),
    )


class ExtractionOutput(Record):
    # Up to a candidate per reading per field: 20 fields over ten readings. The call's
    # own token limits bound the answer; a bound below the answer's size would reject
    # the whole answer, not the surplus.
    candidates: list[ExtractionCandidate] = Field(default_factory=list, max_length=200)
    unresolved: list[str] = Field(default_factory=list, max_length=100)


def _label(name: str) -> str:
    """A reading's name as a model may write it: `1a`, ` 1A ` and `Reading 1A`."""
    return re.sub(r"^reading\s+", "", name.strip(), flags=re.IGNORECASE).upper()


def apply_candidates(
    run,
    asset_id,
    output: ExtractionOutput,
    raw_ref: str,
    raw_sha256: str | None = None,
    readings=None,
):
    """Store each verified candidate as an evidence row and settle each field.

    `readings` defaults to the run's own (`organiser.extraction_readings`). A
    candidate is kept only if its field is the run's, its reading is one named in
    the request, its quote is an exact substring of that reading and its literal an
    exact substring of the quote. No fuzzy repair. The written-rule guard
    (extraction_guard) runs on the cited reading's text. The offsets are computed
    here, from the verified strings, and stored with the reading's label in the
    row's locator (organiser.py). The same span proposed twice is one row.

    A label's decided transcript is its verbatim (G19, G27), so a candidate sets or
    contests a field's value only if it quotes a decided transcript or a reading of
    a label that has none. The first such candidate, the decided ones first, is the
    value; a repeat of its literal adds its row; a candidate with another literal (a
    second label, or the two readers of a label with no decided transcript) marks the
    field AMBIGUOUS and leaves the first literal in place (G32). A candidate quoting
    the other reader's reading of a decided label is evidence beside the value and
    never the value (G20's fallback belongs to the harness): where the decided
    transcript has no value for the field, the field stays unknown and cites that row.
    Every row is cited in the field's evidence_ids, the value's rows first.
    """
    readings = extraction_readings(run) if readings is None else list(readings)
    names = labelled(readings)
    decided_labels = {r.region_id for r in readings if r.role == DECIDED}
    seen: set[tuple[str, str, int, int]] = set()
    kept: list[tuple[ExtractionCandidate, int, Evidence]] = []
    for candidate in output.candidates:
        label = _label(candidate.reading)
        reading = names.get(label)
        if candidate.field_key not in run.fields or reading is None:
            continue
        quote, literal = candidate.source_excerpt, candidate.literal
        # A model's unsupported answer is not a data value. No fuzzy repair here.
        if (
            not quote.strip()
            or not literal.strip()
            or quote not in reading.text
            or literal not in quote
        ):
            continue
        # A value a written rule calls wrong (G41, G45, GEOREFERENCING.md:173) is not
        # stored: the field stays unknown and the generic mandatory_unresolved reason
        # sends the record to review. The raw answer is already in the blob. The rule
        # reads the cited reading, the text the value was taken from.
        if extraction_refusal(candidate.field_key, literal, reading.text):
            continue
        quote_start = reading.text.index(quote)
        literal_start = quote_start + quote.index(literal)
        span = (
            candidate.field_key,
            reading.observation_id,
            literal_start,
            literal_start + len(literal),
        )
        if span in seen:
            continue
        seen.add(span)
        evidence = Evidence(
            kind="literal",
            asset_id=asset_id,
            region_id=reading.region_id,
            observation_ids=[reading.observation_id],
            source=SOURCE,
            locator=format_locator(
                CandidateLocation(
                    label,
                    reading.observation_id,
                    quote_start,
                    quote_start + len(quote),
                    literal_start,
                    literal_start + len(literal),
                )
            ),
            excerpt=quote,
            raw_ref=raw_ref,
            digest=raw_sha256,
        )
        run.evidence.append(evidence)
        # 0: a decided transcript; 1: a reading of a label with none; 2: the other
        # reader's reading of a decided label, evidence only.
        rank = (
            0
            if reading.role == DECIDED
            else 1
            if reading.region_id not in decided_labels
            else 2
        )
        kept.append((candidate, rank, evidence))
    # Each rank in the model's own order (the sort is stable).
    for candidate, rank, evidence in sorted(kept, key=lambda item: item[1]):
        old = run.fields[candidate.field_key]
        if rank == 2:
            old.evidence_ids.append(evidence.id)
            if not old.literal:
                old.reason = LEAD
        elif old.literal and old.literal != candidate.literal:
            old.state = ValueState.AMBIGUOUS
            old.reason = COMPETING
            old.evidence_ids.append(evidence.id)
        elif old.literal:
            old.evidence_ids.append(evidence.id)
        else:
            run.fields[candidate.field_key] = FieldValue(
                state=ValueState.SUPPORTED,
                literal=candidate.literal,
                parsed=candidate.literal,
                evidence_ids=[evidence.id],
                reason="Exact source-supported typed extraction",
            )


def extract_with_agent(gateway, blobs, specimen):
    run = specimen.run
    prompt = ResolvedPrompt.model_validate(
        run.dependencies["prompts"][PromptName.STRUCTURED_EXTRACTION.value]
    )
    from ..provider_privacy import PrivateProviderModel, agent_instrumentation

    agent = Agent(
        PrivateProviderModel(gateway.model_for(run.profile.routes[0])),
        output_type=ExtractionOutput,
        instructions=prompt.text,
        name="insects_bounded_extractor",
    )
    # Prompt and messages follow the configured capture mode (G3).
    agent.instrument = agent_instrumentation()
    readings = extraction_readings(run)
    result = run_agent_bounded(
        agent,
        request_text(run.profile.mandatory_fields, labelled(readings)),
        usage_limits=UsageLimits(request_limit=2, total_tokens_limit=16000),
        timeout_seconds=run.profile.execution.external_timeout_seconds,
    )
    run.usage.tokens += result.usage.input_tokens + result.usage.output_tokens
    raw = ModelMessagesTypeAdapter.dump_json(
        [m for m in result.all_messages() if m.kind == "response"]
    )
    ref = blobs.put(raw)
    apply_candidates(
        run,
        specimen.asset.id,
        result.output,
        ref,
        hashlib.sha256(raw).hexdigest(),
        readings,
    )
