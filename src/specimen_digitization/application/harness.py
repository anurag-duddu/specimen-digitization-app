"""Bounded typed extraction. Proposed values must match retained source text."""

import hashlib

from pydantic import Field
from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits
from pydantic_ai.messages import ModelMessagesTypeAdapter
from ..prompts import PromptName, ResolvedPrompt
from .domain import Record, Evidence, FieldValue, ValueState
from .reliability import run_agent_bounded


class ExtractionCandidate(Record):
    field_key: str
    region_id: str
    literal: str = Field(min_length=1, max_length=2000)
    source_excerpt: str = Field(min_length=1, max_length=4000)


class ExtractionOutput(Record):
    candidates: list[ExtractionCandidate] = Field(default_factory=list, max_length=100)
    unresolved: list[str] = Field(default_factory=list, max_length=100)


def apply_candidates(
    run, asset_id, output: ExtractionOutput, raw_ref: str, raw_sha256: str | None = None
):
    transcripts = {t.region_id: t for t in run.transcripts if t.resolved and t.text}
    for candidate in output.candidates:
        transcript = transcripts.get(candidate.region_id)
        if candidate.field_key not in run.fields or transcript is None:
            continue
        # A model's unsupported answer is not a data value. No fuzzy repair here.
        if (
            candidate.source_excerpt not in transcript.text
            or candidate.literal not in candidate.source_excerpt
        ):
            continue
        evidence = Evidence(
            kind="literal",
            asset_id=asset_id,
            region_id=candidate.region_id,
            observation_ids=transcript.observation_ids,
            source="bounded_extraction_v1",
            locator="region:" + candidate.region_id,
            excerpt=candidate.source_excerpt,
            raw_ref=raw_ref,
            digest=raw_sha256,
        )
        run.evidence.append(evidence)
        old = run.fields[candidate.field_key]
        if old.literal and old.literal != candidate.literal:
            old.state = ValueState.AMBIGUOUS
            old.reason = "Competing source-supported extraction candidates"
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
    from ..provider_privacy import PrivateProviderModel, private_instrumentation

    agent = Agent(
        PrivateProviderModel(gateway.model_for(run.profile.routes[0])),
        output_type=ExtractionOutput,
        instructions=prompt.text,
        name="insects_bounded_extractor",
    )
    agent.instrument = private_instrumentation()
    source = {t.region_id: t.text for t in run.transcripts if t.resolved and t.text}
    import json

    result = run_agent_bounded(
        agent,
        json.dumps(
            {
                "allowed_field_keys": run.profile.mandatory_fields,
                "source_transcripts": source,
            }
        ),
        usage_limits=UsageLimits(request_limit=2, total_tokens_limit=16000),
        timeout_seconds=run.profile.execution.external_timeout_seconds,
    )
    run.usage.tokens += result.usage.input_tokens + result.usage.output_tokens
    raw = ModelMessagesTypeAdapter.dump_json(
        [m for m in result.all_messages() if m.kind == "response"]
    )
    ref = blobs.put(raw)
    apply_candidates(
        run, specimen.asset.id, result.output, ref, hashlib.sha256(raw).hexdigest()
    )
