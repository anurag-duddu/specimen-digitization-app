"""Requesting processing outside synthetic mode (docs/execution/golive/LANE.md, T1)."""

from __future__ import annotations

from .classification import ManualSelection
from .domain import Run, Specimen, now
from .storage import Conflict

# G13: a requested run waits here for its turn, in `queued_at` order.
PENDING = "pending"
# Stages from which only a run action continues a run, never a process request.
ACTION_OWNED = {
    "processing_blocked",
    "retry_scheduled",
    "paused",
    "cancelled",
    "finalized",
    "waiting_for_review",
}


class LaneConflict(Conflict):
    """A refused request. `code` is the error code the API reports."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def run_status(run: Run) -> str:
    """The wire status of a run: `summary().status` and the SQL listing `state`."""
    if run.disposition:
        return "completed"
    if run.stage in {"processing_blocked", "retry_scheduled", "paused", "cancelled"}:
        return run.stage
    if run.stage == PENDING:
        return PENDING
    return "running"


def refuse_sensitive(specimen: Specimen) -> None:
    """Sensitive records never reach a model provider (PRD principle 9)."""
    if specimen.asset.sensitive:
        raise LaneConflict(
            "sensitive_record_not_processed",
            "A record marked sensitive is not sent to model providers",
        )


def processable(run: Run) -> bool:
    """True when a process request may leave the run as it is and start the worker."""
    return not run.disposition and run.stage not in ACTION_OWNED


def queue(specimen: Specimen, registry, actor: str) -> None:
    """Make the run pending, with its budget, its selection and its request time.

    The budget is the allowance of the collection whose profile the run will use:
    the reviewer's selection when one exists, otherwise the intake collection (G14).
    """
    refuse_sensitive(specimen)
    run = specimen.run
    collection_id = (
        run.classification_selection["collection_id"]
        if run.classification_selection
        else specimen.scope.collection_id
    )
    resolution = registry.resolve(collection_id)
    policy = resolution.profile.processing if resolution.profile else None
    if policy is None:
        raise LaneConflict(
            "collection_processing_unconfigured",
            "No published profile with a processing allowance for this collection: "
            + (
                resolution.reason
                if resolution.status != "selected"
                else "no_allowance"
            ),
        )
    limits = {
        name: getattr(policy, name)
        for name in (
            "max_tokens",
            "max_external_calls",
            "external_timeout_seconds",
            "reader_timeout_seconds",
            "lease_seconds",
        )
        if getattr(policy, name) is not None
    }
    run.profile.execution = run.profile.execution.model_copy(
        update={
            "approved_cost_limit_micros": policy.run_cost_limit_micros,
            "stage_cost_reservations": policy.stage_cost_micros,
            **limits,
        }
    )
    if run.classification_selection is None:
        run.classification_selection = ManualSelection(
            collection_id=collection_id, actor_id=actor, reason="Intake collection"
        ).model_dump(mode="json")
    run.stage = PENDING
    run.queued_at = now()


def queue_on_intake(specimen: Specimen, registry, actor: str) -> None:
    """Intake queues every new specimen (PRD 9.1 step 6, G2).

    Without an allowance the specimen is still created, blocked with the reason,
    and a `retry` queues it once the allowance is published.
    """
    try:
        queue(specimen, registry, actor)
    except LaneConflict as refused:
        specimen.run.stage = "processing_blocked"
        specimen.run.blocker = refused.code
