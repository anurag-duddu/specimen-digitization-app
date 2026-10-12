"""Small, read-only Intake projection of persisted workflow milestones.

Stage completion describes work accounted for, not scientific acceptance or
elapsed time. No provider calls, artifact reads or mutations belong here.
"""

from .domain import Run
from .workflow import Workflow


def _next_step(run: Run) -> str | None:
    # Fail closed: a legacy run whose saved plan the workflow cannot walk
    # (for example an authority task without a tool_id) reports no next step,
    # and the client falls back to the run's stage. It never breaks a summary.
    try:
        return Workflow.next_step(run).split(":")[0]
    except (KeyError, TypeError):
        return None


def intake_progress(run: Run) -> dict:
    completed = set(run.completed_steps)
    # A single reader/region finishing is not the end of the reading stage.
    readings = {
        f"transcribe:{region.id}:{route}"
        for region in run.regions
        for route in run.profile.routes
    }
    stages = []
    if "segment" in completed:
        stages.append("segment")
        if readings and readings <= completed:
            stages.append("read")
    for stage, markers in (
        ("compare", {"adjudicate"}),
        ("extract", {"parse"}),
        # A recheck is never appended to completed_steps, so it has no marker.
        ("research", {"validate", "field_research"}),
        ("finalize", {"finalize"}),
    ):
        if completed & markers:
            stages.append(stage)
    # Field research can finalize in the same persisted step. A disposition
    # alone is insufficient: a record can be deferred before processing.
    if run.stage == "finalized" and "finalize" not in stages:
        stages.append("finalize")
    next_step = None if run.disposition else _next_step(run)
    if "evidence_pilot" in run.dependencies:
        # The pilot has its own abbreviated workflow. Do not infer ordinary
        # work from its missing dependency/classification milestones.
        next_step = run.stage if run.stage in {"quality_check", "segment", "transcribe"} else None
    return {
        "next_step": next_step,
        "completed_stages": stages,
        "next_retry_at": run.next_retry_at if run.stage == "retry_scheduled" else None,
    }
