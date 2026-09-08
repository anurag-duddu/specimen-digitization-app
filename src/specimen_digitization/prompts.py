"""Versioned Logfire prompt contracts with code-owned safe fallbacks."""

from __future__ import annotations

import os
from enum import StrEnum

import logfire
from pydantic import BaseModel, ConfigDict, Field


class PromptName(StrEnum):
    LITERAL_TRANSCRIPTION = "literal-label-transcription"
    STRUCTURED_EXTRACTION = "structured-field-extraction"
    DISAGREEMENT_ADJUDICATION = "transcription-disagreement-adjudication"


class CollectionPromptInputs(BaseModel):
    """Typed variables shared by collection-aware prompt templates."""

    model_config = ConfigDict(frozen=True)

    collection_profile_id: str = Field(min_length=1)
    collection_name: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)


class ResolvedPrompt(BaseModel):
    """Prompt text plus the immutable resolution evidence stored with a run."""

    model_config = ConfigDict(frozen=True)

    name: PromptName
    text: str
    requested_label: str
    served_label: str | None
    version: int | None
    resolution_reason: str


_LITERAL_TRANSCRIPTION_DEFAULT = """
You are the literal label transcriber for {{collection_name}} using collection
profile {{collection_profile_id}} and output schema {{schema_version}}.

Transcribe only text that is visually supported by the supplied label image.
Preserve line order, capitalization, punctuation, abbreviations, and apparent
spelling. Represent every unreadable span as [unreadable]. Do not normalize
dates, names, taxonomy, geography, elevations, or collection codes. Do not
fill missing text from context. Return the requested structured output.
""".strip()

_STRUCTURED_EXTRACTION_DEFAULT = """
You are the structured-field extractor for {{collection_name}} using collection
profile {{collection_profile_id}} and output schema {{schema_version}}.

Extract fields only from the supplied literal transcript and its evidence.
Preserve verbatim source text separately from normalized values. Use null when
the evidence is missing or ambiguous, and never invent locality, person,
taxonomy, date, identifier, or elevation values. Return the requested
structured output.
""".strip()

_DISAGREEMENT_ADJUDICATION_DEFAULT = """
You are the transcription adjudicator for {{collection_name}} using collection
profile {{collection_profile_id}} and output schema {{schema_version}}.

Compare the independent candidate transcripts against the supplied image.
Resolve a value only when the visual evidence supports it. Preserve unresolved
differences explicitly and route material ambiguity to human review. Never
choose a candidate merely because it is more fluent. Return the requested
structured output.
""".strip()


PROMPT_VARIABLES = {
    PromptName.LITERAL_TRANSCRIPTION: logfire.template_var(
        name="prompt__literal_label_transcription",
        type=str,
        default=_LITERAL_TRANSCRIPTION_DEFAULT,
        inputs_type=CollectionPromptInputs,
    ),
    PromptName.STRUCTURED_EXTRACTION: logfire.template_var(
        name="prompt__structured_field_extraction",
        type=str,
        default=_STRUCTURED_EXTRACTION_DEFAULT,
        inputs_type=CollectionPromptInputs,
    ),
    PromptName.DISAGREEMENT_ADJUDICATION: logfire.template_var(
        name="prompt__transcription_disagreement_adjudication",
        type=str,
        default=_DISAGREEMENT_ADJUDICATION_DEFAULT,
        inputs_type=CollectionPromptInputs,
    ),
}


def resolve_prompt(
    name: PromptName,
    inputs: CollectionPromptInputs,
    *,
    label: str | None = None,
    targeting_key: str | None = None,
) -> ResolvedPrompt:
    """Resolve a managed prompt and retain the served version as run evidence."""
    requested_label = label or os.getenv("LOGFIRE_PROMPT_LABEL", "development")
    variable = PROMPT_VARIABLES[name]
    with variable.get(
        inputs,
        targeting_key=targeting_key or inputs.collection_profile_id,
        attributes={
            "collection_profile_id": inputs.collection_profile_id,
            "schema_version": inputs.schema_version,
        },
        label=requested_label,
    ) as resolved:
        return ResolvedPrompt(
            name=name,
            text=resolved.value,
            requested_label=requested_label,
            served_label=resolved.label,
            version=resolved.version,
            resolution_reason=resolved.reason,
        )
