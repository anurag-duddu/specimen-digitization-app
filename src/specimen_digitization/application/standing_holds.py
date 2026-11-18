"""Holds a record keeps until their own event, derived from durable state on the run.

The clearance rules compute a run's reasons afresh on every finalize, and a blocker may replace the
reasons list outright. A hold that must outlive that is never recovered from an earlier reasons list
(plan WP K1, Codex rounds 2 and 3 on PR #455): it is derived, every time the reasons are computed,
from state recorded on the run when its cause happened.

- `run.pending_review` (one optional list, omitted while unset): what a person must still review.
  `human_approval_required` is recorded where a person's decision enters the application (api.py
  apply_decision, through which the decisions route, decisions:batch and candidate choices all pass:
  person_acted), before any other effect and whatever the run's stage or blocker;
  `history_restored_requires_review` by a history restore (history_restore.restored_specimen);
  `location_reassessment_unconfirmed:<field>` by a reassessment that leaves a field unproved
  (FieldResearchStep._retained_reassessment, which replaces the family's earlier entries only after its
  finalize has succeeded). A person's approval (lane.approve) clears the list.
- Research given up for the run as a whole: the step's give-up finding (rule `field_research_given_up`,
  FieldResearchStep.give_up), which the next research attempt removes before it makes its working copy.

A run stored before the key existed adopts its stored holds once, where a stored run is loaded
(active_graph.unpack: adopt_legacy, when its stored reasons name a hold), before anything can write the
key or the reasons; every helper here that writes the key adopts first, so none turns "unset" into
"empty" without reading the stored reasons.

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
    adopt_legacy(run)
    run.pending_review = list(dict.fromkeys((*run.pending_review, *codes)))


def person_acted(run) -> None:
    """A person acted on this record: it waits for their approval until they give it (an approve
    decision's own approval then clears it, lane.approve)."""
    note_pending(run, APPROVAL)


def clear_on_approval(run) -> None:
    """A person's approval resolves everything they were to review."""
    run.pending_review = []


def replace_reassessment(run, codes) -> None:
    """The reassessment that settles a location family, once its finalize has succeeded: what it still
    leaves unproved replaces the family's earlier entries, in one assignment."""
    adopt_legacy(run)
    run.pending_review = [*(code for code in run.pending_review
        if code.partition(":")[0] != REASSESSMENT_UNCONFIRMED), *dict.fromkeys(codes)]


def adopt_legacy(run) -> None:
    """A run stored before pending_review existed (unset, None): its stored reasons are the only record
    of a person's pending review, so they are adopted once, where the stored run is loaded
    (active_graph.unpack); a run with the key set, even to an empty list, never reads them."""
    if run.pending_review is not None:
        return
    run.pending_review = legacy_holds(run)


def legacy_holds(run) -> list[str]:
    """What a run stored before pending_review existed records of a person's pending review: the holds
    its stored reasons name (none once a person has approved it)."""
    return list(dict.fromkeys(() if run.human_approved else (reason for reason in run.reasons
        if reason.partition(":")[0] in {APPROVAL, HISTORY_RESTORED, REASSESSMENT_UNCONFIRMED})))


def derived_holds(run) -> list[str]:
    """The holds derived from the run's state: none once a person has approved it; else what a person
    must still review, and research given up for the run as a whole."""
    if run.human_approved:
        return []
    given_up = any(getattr(finding, "rule_id", None) == GIVEN_UP for finding in run.findings)
    return [*(run.pending_review or ()), *([GIVEN_UP] if given_up else [])]
