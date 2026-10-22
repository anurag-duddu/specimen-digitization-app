"""Small, read-only Intake projection of persisted workflow milestones.

Stage completion describes work accounted for, not scientific acceptance or
elapsed time. No provider calls, artifact reads or mutations belong here.
"""

import re
from datetime import datetime, timedelta, timezone

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
        # Always present, so every reply has one shape. Only the API, which can
        # see the collection's other runs, sets it for a pending run (api.in_line).
        "waiting_in_line": False,
    }


# A live drain saves the run it steps after every step, and one execution
# steps a collection's runs one at a time (lane_worker.DrainWorker, G13). Its
# collection fence lease is the task deadline plus 60 s, so a running row
# saved within that bound is a drain still at work in the collection.
LIVE_DRAIN_SECONDS = 3600 + 60
# Stages whose wire status is `running` but that no drain is stepping.
NOT_LANE_WORK = frozenset({"ingested", "waiting_for_review"})


def _saved_at(value: str) -> datetime:
    # SQL Connect timestamps may carry more than microsecond precision.
    value = re.sub(r"(\.\d{6})\d+", r"\1", value.replace("Z", "+00:00"))
    moment = datetime.fromisoformat(value)
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def lane_busy(rows, specimen_id: str, current: datetime) -> bool:
    """True when another run in the collection is being processed now.

    `rows` are the collection's metadata rows with status `running`. The
    collection fence itself is a worker-only document the API cannot read
    (GetDocumentV2 limits `worker_cursor` reads to the actor that wrote it),
    so the run the drain is stepping stands in for it. A row with no save
    time (the local SQLite listing has none) counts as live; a row whose
    save time cannot be read, or is older than the fence lease, does not.
    """
    oldest = current - timedelta(seconds=LIVE_DRAIN_SECONDS)
    for row in rows:
        if (
            row.get("specimen_id") == specimen_id
            or row.get("status") != "running"
            or row.get("stage") in NOT_LANE_WORK
        ):
            continue
        saved = row.get("updated_at")
        if saved is None:
            return True
        try:
            if _saved_at(str(saved)) >= oldest:
                return True
        except ValueError:
            continue
    return False
