"""Literal, evidence-preserving specimen-label transcription agent."""

from __future__ import annotations

from typing import Literal

import logfire
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_ai import Agent, BinaryContent

from .model_gateway import HuggingFaceModelGateway
from .prompts import (
    CollectionPromptInputs,
    PromptName,
    ResolvedPrompt,
    resolve_prompt,
)
from .tracing import SpecimenTraceContext

SupportedImageMediaType = Literal["image/jpeg", "image/png"]


class LiteralTranscription(BaseModel):
    """Faithful visual reading before any field normalization or enrichment."""

    model_config = ConfigDict(frozen=True)

    verbatim_text: str = Field(min_length=1)
    lines: list[str] = Field(min_length=1)
    unreadable_spans: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def lines_must_reconstruct_verbatim_text(self) -> LiteralTranscription:
        if "\n".join(self.lines) != self.verbatim_text:
            raise ValueError("lines must reconstruct verbatim_text exactly")
        return self


class LiteralTranscriptionRun(BaseModel):
    """Typed output plus the route and prompt evidence needed for replay."""

    model_config = ConfigDict(frozen=True)

    output: LiteralTranscription
    route_id: str
    model_id: str
    upstream_provider: str
    prompt_name: PromptName
    prompt_requested_label: str
    prompt_served_label: str | None
    prompt_version: int | None
    input_tokens: int
    output_tokens: int


def _agent_name(route_id: str) -> str:
    return f"literal_transcriber_{route_id.replace('-', '_')}"


def build_literal_transcription_agent(
    gateway: HuggingFaceModelGateway,
    *,
    route_id: str,
    prompt: ResolvedPrompt,
) -> Agent[None, LiteralTranscription]:
    """Build a stably named agent for the Logfire Agents view."""
    return Agent(
        gateway.model_for(route_id),
        name=_agent_name(route_id),
        output_type=LiteralTranscription,
        instructions=prompt.text,
    )


def transcribe_label_image(
    gateway: HuggingFaceModelGateway,
    *,
    route_id: str,
    image: bytes,
    media_type: SupportedImageMediaType,
    prompt_inputs: CollectionPromptInputs,
    prompt_label: str | None = None,
    trace_context: SpecimenTraceContext | None = None,
) -> LiteralTranscriptionRun:
    """Run one literal transcription without placing image bytes in trace data."""
    route = gateway.route(route_id)
    prompt = resolve_prompt(
        PromptName.LITERAL_TRANSCRIPTION,
        prompt_inputs,
        label=prompt_label,
    )
    agent = build_literal_transcription_agent(
        gateway,
        route_id=route_id,
        prompt=prompt,
    )
    trace_attributes = trace_context.span_attributes() if trace_context else {}
    with logfire.span(
        "Transcribe specimen label",
        **trace_attributes,
        **{
            "specimen.model.route_id": route.route_id,
            "specimen.model.id": route.model_id,
            "specimen.model.upstream_provider": route.provider,
            "specimen.prompt.name": prompt.name.value,
            "specimen.prompt.requested_label": prompt.requested_label,
            "specimen.prompt.served_label": prompt.served_label or "code-default",
            "specimen.prompt.version": prompt.version or 0,
        },
    ):
        result = agent.run_sync(
            [
                "Produce a literal transcription of this label image.",
                BinaryContent(data=image, media_type=media_type),
            ]
        )

    return LiteralTranscriptionRun(
        output=result.output,
        route_id=route.route_id,
        model_id=route.model_id,
        upstream_provider=route.provider,
        prompt_name=prompt.name,
        prompt_requested_label=prompt.requested_label,
        prompt_served_label=prompt.served_label,
        prompt_version=prompt.version,
        input_tokens=result.usage.input_tokens,
        output_tokens=result.usage.output_tokens,
    )
