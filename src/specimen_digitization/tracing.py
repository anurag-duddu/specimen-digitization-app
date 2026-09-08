"""Trace contracts shared by specimen workflow activities."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from enum import StrEnum
from typing import Any

import logfire
from pydantic import BaseModel, ConfigDict, Field


class ProcessingStage(StrEnum):
    INGEST = "ingest"
    SEGMENT = "segment"
    TRANSCRIBE = "transcribe"
    EXTRACT = "extract"
    RECONCILE = "reconcile"
    VALIDATE = "validate"
    PERSIST = "persist"
    REVIEW_ROUTE = "review-route"


class SpecimenTraceContext(BaseModel):
    """Safe correlation identifiers carried across worker boundaries."""

    model_config = ConfigDict(frozen=True)

    specimen_run_id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)
    batch_id: str = Field(min_length=1)
    collection_profile_id: str = Field(min_length=1)
    collection_profile_version: str = Field(min_length=1)

    def span_attributes(self) -> dict[str, str]:
        return {
            "specimen.run.id": self.specimen_run_id,
            "temporal.workflow.id": self.workflow_id,
            "specimen.subject.id": self.subject_id,
            "specimen.batch.id": self.batch_id,
            "specimen.collection_profile.id": self.collection_profile_id,
            "specimen.collection_profile.version": self.collection_profile_version,
        }


@contextmanager
def specimen_run_span(context: SpecimenTraceContext) -> Iterator[logfire.LogfireSpan]:
    """Create the root span for one active specimen-processing segment."""
    with logfire.span("Process specimen run", **context.span_attributes()) as span:
        yield span


@contextmanager
def processing_stage_span(
    stage: ProcessingStage,
    context: SpecimenTraceContext,
    **attributes: Any,
) -> Iterator[logfire.LogfireSpan]:
    """Create a named child span without placing specimen content in its name."""
    with logfire.span(
        "Run specimen processing stage",
        **context.span_attributes(),
        **{"specimen.processing.stage": stage.value},
        **attributes,
    ) as span:
        yield span


def current_trace_context() -> dict[str, str]:
    """Serialize the current OpenTelemetry context for an approved worker hop."""
    return dict(logfire.get_context())


@contextmanager
def attach_trace_context(context: Mapping[str, str]) -> Iterator[None]:
    """Attach explicitly propagated trace context inside a trusted worker."""
    with logfire.attach_context(dict(context)):
        yield
