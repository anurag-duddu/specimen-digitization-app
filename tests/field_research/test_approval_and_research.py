"""Who cleared a record, through the whole run: research clearing with no person, and an
approval that later processing would otherwise outlive.

What the code guarantees: the workflow withdraws a standing approval before it runs any step
other than the rules-only ones (`workflow.RULES_ONLY_STEPS`: the field research recheck,
validate and finalize), whatever made the run due (a run action, the drain's
`recover_blocked`). So a record the workflow clears after such a step clears as the system
(`cleared_by` "system"), and only an approval given after the last value-producing step reads
as a person's. The routes are driven end to end; a test that sets a stored state by hand says so.
"""

import pytest

from specimen_digitization.application import api as app_api
from specimen_digitization.application.api import summary
from specimen_digitization.application.domain import Disposition, ValueState
from specimen_digitization.application.storage import digest
from specimen_digitization.application.workflow import FIELD_RESEARCH
from specimen_digitization.field_research.contracts import FieldAnswer

from test_step import (
    LABEL, ORG, Scripted, answering, decide, failing, mounted, review_client, rig,  # noqa: F401 (fixture)
)

HEADERS = {"Authorization": "Bearer reviewer"}


def run_to_rest(rig):
    """Step the workflow until the run is finalized or blocked."""
    for _ in range(12):
        current = rig.workflow.step(rig.principal, rig.specimen.id)
        if current.run.stage in {"finalized", "processing_blocked", "retry_scheduled"}:
            return current
    raise AssertionError(current.run.stage)


def act(client, rig, action, key):
    current = rig.repository.get(rig.principal.scope, rig.specimen.id)
    response = client.post(f"/v1/organizations/{ORG}/runs/{current.run.id}/actions",
        headers={**HEADERS, "Idempotency-Key": key},
        json={"expected_revision": current.version, "action": action, "reason": "Research it again."})
    assert response.status_code == 200, response.text
    return rig.repository.get(rig.principal.scope, rig.specimen.id)


def read_back(client, rig):
    """cleared_by from the detail and from the list, which must agree."""
    ident = rig.specimen.id
    detail = client.get(f"/v1/organizations/{ORG}/specimens/{ident}", headers=HEADERS)
    assert detail.status_code == 200, detail.text
    listed = client.get(f"/v1/organizations/{ORG}/specimens", headers=HEADERS,
        params={"collection_id": rig.principal.scope.collection_id, "specimen_id": ident})
    assert listed.status_code == 200, listed.text
    [item] = listed.json()["items"]
    assert item["cleared_by"] == detail.json()["cleared_by"]
    return detail.json()["cleared_by"]


def unresolved_country():
    return Scripted({"country": answering(FieldAnswer(
        outcome="sources_cannot_resolve", literal=LABEL["country"], reading_names=["1A"],
        explanation="The first pass could not settle it."))})


def test_research_that_clears_a_run_no_person_touched_clears_it_as_the_system(rig):
    mounted(rig, Scripted())
    done = run_to_rest(rig)
    assert (done.run.stage, done.run.disposition) == ("finalized", Disposition.CLEARED)
    assert done.run.human_approved is False
    assert summary(done, "reviewer")["cleared_by"] == "system"
    assert read_back(review_client(rig), rig) == "system"


def test_an_approval_then_a_person_approval_of_a_cleared_record_is_the_persons(rig):
    mounted(rig, Scripted())
    run_to_rest(rig)
    client = review_client(rig)
    approved = decide(client, rig, "approve-cleared", "approve")
    assert (approved.disposition, approved.human_approved) == (Disposition.CLEARED, True)
    assert read_back(client, rig) == "person"


def test_a_retry_that_researches_again_withdraws_an_earlier_approval(rig, monkeypatch):
    mounted(rig, unresolved_country())
    done = run_to_rest(rig)
    assert done.run.disposition == Disposition.REVIEW
    assert done.run.fields["country"].state == ValueState.UNRESOLVED
    client = review_client(rig)
    # The reviewer approves; the unresolved fields keep the record in review.
    approved = decide(client, rig, "approve-in-review", "approve")
    assert (approved.disposition, approved.human_approved) == (Disposition.REVIEW, True)
    monkeypatch.setattr(app_api, "queue",
        lambda specimen, registry, actor: setattr(specimen.run, "stage", "pending"))
    retried = act(client, rig, "retry", "retry-research")
    assert FIELD_RESEARCH not in retried.run.completed_steps
    # Research settles country and the rules clear the record: the system's clearance.
    resolver = Scripted()
    mounted(rig, resolver)
    cleared = run_to_rest(rig)
    assert "country" in resolver.calls
    assert (cleared.run.disposition, cleared.run.human_approved) == (Disposition.CLEARED, False)
    assert read_back(client, rig) == "system"


def test_a_resume_of_research_that_did_not_finish_withdraws_an_earlier_approval(rig, monkeypatch):
    mounted(rig, Scripted({"country": failing("source_unavailable")}))
    blocked = rig.workflow.step(rig.principal, rig.specimen.id)
    assert blocked.run.stage == "retry_scheduled"
    assert FIELD_RESEARCH not in blocked.run.completed_steps
    client = review_client(rig)
    approved = decide(client, rig, "approve-blocked", "approve")
    assert approved.human_approved is True
    monkeypatch.setattr(app_api, "queue",
        lambda specimen, registry, actor: setattr(specimen.run, "stage", "pending"))
    act(client, rig, "resume", "resume-research")
    mounted(rig, Scripted())
    after = run_to_rest(rig)
    assert after.run.human_approved is False
    assert read_back(client, rig) in {None, "system"}


def test_a_retry_that_only_applies_the_rules_keeps_the_approval(rig, monkeypatch):
    mounted(rig, Scripted())
    run_to_rest(rig)
    client = review_client(rig)
    decide(client, rig, "approve-cleared", "approve")
    monkeypatch.setattr(app_api, "queue",
        lambda specimen, registry, actor: setattr(specimen.run, "stage", "pending"))
    retried = act(client, rig, "retry", "retry-rules")
    # Research is complete and not requeued: only the rules are applied again, and the
    # approval of the unchanged values stands through the workflow's finalize.
    assert FIELD_RESEARCH in retried.run.completed_steps
    resolver = Scripted()
    mounted(rig, resolver)
    after = run_to_rest(rig)
    assert resolver.calls == []
    assert (after.run.disposition, after.run.human_approved) == (Disposition.CLEARED, True)
    assert read_back(client, rig) == "person"


def left_blocked(rig, redo, **state):
    """Save the run as a worker left it, blocked before ``redo`` (as
    tests/test_first_pass_stuck_recovery.py `leave` does): the steps from ``redo`` on are not
    done, and the run holds the given state."""
    stored = rig.repository.get(rig.principal.scope, rig.specimen.id)
    run = stored.run
    order = ("first_pass:", "adjudicate", "parse")
    later = order[order.index(redo):]
    run.completed_steps = [step for step in run.completed_steps
        if not any(step == name or (name.endswith(":") and step.startswith(name)) for name in later)]
    if redo == "first_pass:":
        run.first_pass_decisions = []
    run.stage, run.next_retry_at = "processing_blocked", None
    for key, value in state.items():
        setattr(run, key, value)
    rig.specimen = rig.repository.save(rig.principal, stored, stored.version, "left-" + redo,
        digest({"left": redo}))
    return rig.specimen


# G51's round 2 case (a lane stall at the first pass) and Codex's two (extraction held by a
# provider circuit; a first pass whose unanswered call's lease ended, settled as a lost attempt).
DRAIN_CASES = {
    "first-pass-stall": ("first_pass:", {"blocker": "lane_run_not_progressing"}),
    "extraction-circuit": ("parse", {"blocker": "provider_circuit:organiser"}),
    "first-pass-lost-call": ("first_pass:", {"blocker": "external_outcome_unknown",
        "lease_until": "2000-01-01T00:00:00+00:00"}),
}


@pytest.mark.parametrize("case", sorted(DRAIN_CASES))
def test_the_drain_recovering_a_blocked_run_withdraws_an_approval_given_while_blocked(rig, case):
    """An approval lands on a blocked run (the decisions route) and the drain's recovery makes it
    due with no run action; the first step that produces values withdraws it."""
    redo, state = DRAIN_CASES[case]
    left = left_blocked(rig, redo, **state)
    step = rig.workflow.next_step(left.run)
    assert step.startswith(redo), step
    if case == "first-pass-lost-call":
        left.run.attempts[step] = 1
        rig.specimen = rig.repository.save(rig.principal, left, left.version, "attempted", digest({"a": 1}))
    client = review_client(rig)
    approved = decide(client, rig, "approve-" + case, "approve")
    assert (approved.stage, approved.disposition, approved.human_approved) == (
        "processing_blocked", None, True)
    recovered = rig.workflow.recover_blocked(rig.principal, rig.specimen.id)
    if case == "extraction-circuit":
        # This rig's adapters make no extraction call (parse runs without one), so the drain
        # does not take it; the state its recovery leaves, the run due at parse with the
        # approval standing, is saved by hand instead, which is what the drain saves.
        assert recovered is False
        held = rig.repository.get(rig.principal.scope, rig.specimen.id)
        held.run.stage, held.run.blocker = "retry_scheduled", None
        rig.specimen = rig.repository.save(rig.principal, held, held.version, "due", digest({"due": 1}))
        assert rig.specimen.run.human_approved is True
    else:
        assert recovered is True
    mounted(rig, Scripted())
    rig.workflow.step(rig.principal, rig.specimen.id)
    # The step that ran first produces values: the approval is withdrawn and saved with it.
    assert rig.repository.get(rig.principal.scope, rig.specimen.id).run.human_approved is False
    after = run_to_rest(rig)
    assert after.run.human_approved is False
    assert read_back(client, rig) != "person"
