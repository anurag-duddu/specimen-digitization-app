"""Holds a record keeps until their own event, derived from durable state on the run.

The clearance rules compute a run's reasons afresh on every finalize, and a blocker may replace the
reasons list outright. A hold that must outlive that is never recovered from an earlier reasons list
(plan WP K1, Codex rounds 2 and 3 on PR #455): it is derived, every time the reasons are computed,
from state recorded on the run when its cause happened.

- `run.pending_review` (one optional list, omitted while unset): what a person must still review.
  `human_approval_required` is recorded by a person's decision (field_research.step.refinalize with
  `decided`), `history_restored_requires_review` by a history restore (history_restore.restored_specimen),
  `location_reassessment_unconfirmed:<field>` by a reassessment that leaves a field unproved
  (FieldResearchStep._retained_reassessment). A person's approval (lane.approve) clears the list; the
  reassessment that settles a location family clears that family's entries (clear_reassessment).
- Research given up for the run as a whole: the step's give-up finding (rule `field_research_given_up`,
  FieldResearchStep.give_up), which the next research attempt removes before it researches.

`tests/test_standing_holds.py` scans the source for every writer of a run's reasons and fails on one
that is neither the recomputation, a blocker, nor backed by this state.
"""

APPROVAL = "human_approval_required"
HISTORY_RESTORED = "history_restored_requires_review"
REASSESSMENT_UNCONFIRMED = "location_reassessment_unconfirmed"
# The research step's give-up finding (field_research.step.GIVEN_UP) and the reason it derives.
GIVEN_UP = "field_research_given_up"
# The codes this module derives; a writer outside the recomputation may write only these, or a blocker.
DERIVED = frozenset({APPROVAL, HISTORY_RESTORED, REASSESSMENT_UNCONFIRMED, GIVEN_UP})


def note_pending(run, *codes: str) -> None:
    """Record what a person must still review, when its cause happens."""
    run.pending_review = list(dict.fromkeys((*(run.pending_review or ()), *codes)))


def clear_on_approval(run) -> None:
    """A person's approval resolves everything they were to review."""
    run.pending_review = []


def clear_reassessment(run) -> None:
    """The reassessment that settles a location family: it records what it still leaves unproved."""
    run.pending_review = [code for code in run.pending_review or ()
        if code.partition(":")[0] != REASSESSMENT_UNCONFIRMED]


def adopt_legacy(run) -> None:
    """A run stored before pending_review existed (unset, None): its stored reasons are the only record
    of a person's pending review, so they are adopted once, at its first finalize; a run with the key
    set, even to an empty list, never reads them."""
    if run.pending_review is not None:
        return
    note_pending(run, *(() if run.human_approved else (reason for reason in run.reasons
        if reason.partition(":")[0] in {APPROVAL, HISTORY_RESTORED, REASSESSMENT_UNCONFIRMED})))


def derived_holds(run) -> list[str]:
    """The holds derived from the run's state: none once a person has approved it; else what a person
    must still review, and research given up for the run as a whole."""
    if run.human_approved:
        return []
    given_up = any(getattr(finding, "rule_id", None) == GIVEN_UP for finding in run.findings)
    return [*(run.pending_review or ()), *([GIVEN_UP] if given_up else [])]
