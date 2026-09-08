from __future__ import annotations

from logfire.testing import CaptureLogfire

from specimen_digitization.tracing import (
    ProcessingStage,
    SpecimenTraceContext,
    processing_stage_span,
    specimen_run_span,
)


def test_specimen_stages_share_safe_correlation_attributes(
    capfire: CaptureLogfire,
) -> None:
    context = SpecimenTraceContext(
        specimen_run_id="run-001",
        workflow_id="workflow-001",
        subject_id="subject-001",
        batch_id="batch-001",
        collection_profile_id="insects",
        collection_profile_version="v1",
    )

    with (
        specimen_run_span(context),
        processing_stage_span(ProcessingStage.TRANSCRIBE, context),
    ):
        pass

    spans = capfire.exporter.exported_spans_as_dict()
    stage_span = next(
        span for span in spans if span["name"] == "Run specimen processing stage"
    )
    assert stage_span["attributes"]["specimen.processing.stage"] == "transcribe"
    assert stage_span["attributes"]["specimen.run.id"] == "run-001"
    assert stage_span["attributes"]["temporal.workflow.id"] == "workflow-001"
