"""Who cleared a record, through the whole run: research clearing with no person, and an
approval that later research would otherwise outlive.

A reviewer's approval covers the values they saw. A run action that researches again
(`retry` that requeues field research, `resume` or `retry` of a run whose research is not
complete) withdraws it, so research that later clears the record clears it as the system
(`cleared_by` "system"), never as a person's approval of values nobody saw. The routes are
driven end to end; nothing sets the approval by hand.
"""

from specimen_digitization.application import api as app_api
from specimen_digitization.application.api import summary
from specimen_digitization.application.domain import Disposition, ValueState
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
    assert retried.run.human_approved is False
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
    resumed = act(client, rig, "resume", "resume-research")
    assert resumed.run.human_approved is False
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
    # Research is complete and not requeued: nothing researches again.
    assert FIELD_RESEARCH in retried.run.completed_steps
    assert retried.run.human_approved is True
