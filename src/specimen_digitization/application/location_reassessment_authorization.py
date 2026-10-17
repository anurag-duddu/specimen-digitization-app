"""The owner's single additional EBFC location attempt, without repinning limits.

This authorization is server-owned and consumed by the ordinary saved attempt
counter. It cannot authorize another run, a fifth attempt, or additional money.
"""
from collections.abc import Mapping

AUTHORIZATION_ID = "owner-2026-10-16-ebfc-location-attempt-4"
ORGANIZATION_ID = "e4b2a17f-c28b-4e13-8273-c8297083d215"
COLLECTION_ID = "200d7057-23fa-41ab-875b-682c8ba218c9"
SPECIMEN_ID = "ebfc6171-bf2f-56b8-a35b-442798810461"
RUN_ID = "e7b00556-f006-4be7-9bd8-82ebf41173be"


def authorization_for(run, specimen=None) -> str | None:
    """Require actual specimen scope and the unchanged execution/accounting pins."""
    policy = run.profile.execution
    if (specimen is not None
            and specimen.id == SPECIMEN_ID and specimen.run.id == run.id == RUN_ID
            and specimen.scope.organization_id == ORGANIZATION_ID
            and specimen.scope.collection_id == COLLECTION_ID
            and type(run.attempts.get("field_research")) is int
            and run.attempts["field_research"] == 3
            and policy.max_attempts == 3
            and policy.approved_cost_limit_micros == 1_000_000
            and policy.program_allowance_micros == 16_000_000
            and policy.program_ledger_collection == COLLECTION_ID):
        return AUTHORIZATION_ID
    return None


def authorized_queued_attempt(specimen) -> bool:
    """Validate the prospective fourth pass before any reservation or send.

    Use the same eligibility/protection checks as the engine, on a private
    prospective counter. The canonical counter is incremented only by Workflow.
    """
    from ..field_research.location_reassessment import FIELDS, KEY, active_keys

    run = specimen.run
    marker = run.dependencies.get(KEY)
    if (authorization_for(run, specimen) is None or not isinstance(marker, Mapping)
            or marker.get("authorization_id") != AUTHORIZATION_ID
            or type(marker.get("attempt")) is not int or marker["attempt"] != 4
            or "evidence_pilot" in run.dependencies):
        return False
    protected = marker.get("protected")
    if (not isinstance(protected, list)
            or any(not isinstance(key, str) or key not in FIELDS for key in protected)
            or len(set(protected)) != len(protected)):
        return False
    prospective = run.model_copy(update={"attempts": {**run.attempts, "field_research": 4}})
    return bool(active_keys(prospective))
