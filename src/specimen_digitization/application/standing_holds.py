"""Standing holds: reasons a path outside the clearance rules' recomputation writes onto a run.

The clearance rules recompute a run's reasons from its fields on every finalize
(field_research.step.finalize_fields and refinalize; policy.finalize on the ordinary path).
A hold another path writes (a person's decision, a history restore, a location reassessment)
is not recomputed by them, so every recomputation, and every path that replaces the reasons
with a blocker, carries it until the event that resolves it (plan WP K1, Codex round 2 on PR
#455). `tests/test_standing_holds.py` scans the source for every writer of a run's reasons and
fails on one it does not know, so a new writer is classified before it ships.
"""

from collections.abc import Iterable

APPROVAL = "human_approval_required"
HISTORY_RESTORED = "history_restored_requires_review"
REASSESSMENT_UNCONFIRMED = "location_reassessment_unconfirmed"

# Each standing hold's code (a reason is `<code>` or `<code>:<detail>`) and what resolves it.
STANDING = {
    # field_research.step.refinalize(decided=True), after a person's decision.
    APPROVAL: "a person's approval",
    # history_restore.restored_specimen, after a restore of a completed revision.
    HISTORY_RESTORED: "a person's approval",
    # FieldResearchStep._retained_reassessment, an explicit location reassessment left unproved.
    REASSESSMENT_UNCONFIRMED: "a person's approval, or the location reassessment that settles it",
}


def is_standing(reason: str) -> bool:
    return reason.partition(":")[0] in STANDING


def standing_holds(reasons: Iterable[str], *, approved: bool, settles_reassessment: bool = False) -> list[str]:
    """The standing holds among `reasons` that are still unresolved: none once a person has approved
    the record; a location reassessment's, unless the reassessment that settles it is the step that
    is deciding (`settles_reassessment`: it names what it still leaves unconfirmed itself)."""
    if approved:
        return []
    return [reason for reason in dict.fromkeys(reasons) if is_standing(reason)
        and not (settles_reassessment and reason.partition(":")[0] == REASSESSMENT_UNCONFIRMED)]
