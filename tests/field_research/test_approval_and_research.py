"""Who cleared a record, through the whole run: an approval holds only on the values it approved.

What the code guarantees: a cleared record is "person" only while its values are the ones a
person approved. `approve` records a digest of the run's values (lane.approved_values_digest:
every field's state and value layers, each label's resolved transcript text); wherever a
disposition is decided (lane.settle_approval, called first by policy.finalize,
field_research.step.finalize_fields and the research harness's materializations) a standing
approval whose digest no longer matches is withdrawn. A person's later decision on the record
(field, transcription, authority, taxonomy, metadata, research candidate) also withdraws it,
whether or not it changes a value, as on main. A system step that leaves the values as approved
(a retry, resume, recovery, reconcile or reassessment, or research writing the same values
again) keeps it; research or a derivation that changes one ends it. An approval with no
recorded digest (given before this change) stands, as on main.

The routes are driven end to end through the workflow, the API and the drain; each test says
what it sets by hand.
"""

from datetime import datetime

import pytest

from specimen_digitization.application import api as app_api
from specimen_digitization.application.api import summary
from specimen_digitization.application.domain import Disposition, ValueState
from specimen_digitization.application.lane import approved_values_digest
from specimen_digitization.application.storage import digest
from specimen_digitization.application.workflow import FIELD_RESEARCH
from specimen_digitization.field_research.contracts import FieldAnswer

from test_step import (
    LABEL, ORG, Scripted, answering, build_rig, decide, failing, label_with, mounted, review_client,
    rig,  # noqa: F401 (fixture)
)

HEADERS = {"Authorization": "Bearer reviewer"}
LACKS = FieldAnswer(outcome="label_lacks_value", explanation="Not on the label.")
CANNOT = FieldAnswer(outcome="sources_cannot_resolve", explanation="No unit is written with this number.")


def run_to_rest(rig, *, through_retries=False):
    """Step the workflow until the run is finalized or blocked; with ``through_retries``, a
    scheduled retry is waited out on the rig's clock and stepped on."""
    for _ in range(16):
        current = rig.workflow.step(rig.principal, rig.specimen.id)
        if through_retries and current.run.stage == "retry_scheduled" and current.run.next_retry_at:
            rig.clock.now = datetime.fromisoformat(current.run.next_retry_at)
            continue
        if current.run.stage in {"finalized", "processing_blocked", "retry_scheduled"}:
            return current
    raise AssertionError(current.run.stage)


def act(client, rig, action, key):
    current = rig.repository.get(rig.principal.scope, rig.specimen.id)
    response = client.post(f"/v1/organizations/{ORG}/runs/{current.run.id}/actions",
        headers={**HEADERS, "Idempotency-Key": key},
        json={"expected_revision": current.version, "action": action, "reason": "Run it again."})
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


def queue_in_place(monkeypatch):
    monkeypatch.setattr(app_api, "queue",
        lambda specimen, registry, actor: setattr(specimen.run, "stage", "pending"))


def save_by_hand(rig, change, label):
    stored = rig.repository.get(rig.principal.scope, rig.specimen.id)
    change(stored.run)
    rig.specimen = rig.repository.save(rig.principal, stored, stored.version, label, digest({label: 1}))
    return rig.specimen


def approved_and_cleared(rig):
    """The rig researched and cleared with no person, then approved through the decisions route."""
    mounted(rig, Scripted())
    run_to_rest(rig)
    client = review_client(rig)
    approved = decide(client, rig, "approve-cleared", "approve")
    assert (approved.disposition, approved.human_approved) == (Disposition.CLEARED, True)
    assert approved.approved_values_sha256 == approved_values_digest(approved)
    return client


def unresolved_country():
    return Scripted({"country": answering(FieldAnswer(
        outcome="sources_cannot_resolve", literal=LABEL["country"], reading_names=["1A"],
        explanation="The first pass could not settle it."))})


# ---- no person, and a person's approval of the values as they are ----------------------------

def test_research_that_clears_a_run_no_person_touched_clears_it_as_the_system(rig):
    mounted(rig, Scripted())
    done = run_to_rest(rig)
    assert (done.run.stage, done.run.disposition) == ("finalized", Disposition.CLEARED)
    assert done.run.human_approved is False and done.run.approved_values_sha256 is None
    assert summary(done, "reviewer")["cleared_by"] == "system"
    assert read_back(review_client(rig), rig) == "system"


def test_an_approval_of_a_cleared_record_is_the_persons(rig):
    client = approved_and_cleared(rig)
    assert read_back(client, rig) == "person"


# ---- a system step that leaves the values as approved keeps the approval --------------------

@pytest.mark.parametrize("action", ["retry", "resume"])
def test_a_retry_or_resume_that_changes_no_value_keeps_the_approval(rig, monkeypatch, action):
    client = approved_and_cleared(rig)
    queue_in_place(monkeypatch)
    again = act(client, rig, action, action + "-no-change")
    assert FIELD_RESEARCH in again.run.completed_steps
    resolver = Scripted()
    mounted(rig, resolver)
    after = run_to_rest(rig)
    assert resolver.calls == []
    assert (after.run.disposition, after.run.human_approved) == (Disposition.CLEARED, True)
    assert read_back(client, rig) == "person"


def test_research_that_writes_the_identical_value_again_keeps_the_approval(rig, monkeypatch):
    """The value's layers and state unchanged, its reason rewritten (set by hand, as a research
    writer would leave the identical value)."""
    client = approved_and_cleared(rig)
    before = rig.repository.get(rig.principal.scope, rig.specimen.id).run.fields["country"]

    def rewrite(run):
        run.fields["country"] = before.model_copy(update={"reason": "Researched again: the same value."})

    save_by_hand(rig, rewrite, "same-value")
    queue_in_place(monkeypatch)
    act(client, rig, "resume", "resume-same-value")
    mounted(rig, Scripted())
    after = run_to_rest(rig)
    assert (after.run.disposition, after.run.human_approved) == (Disposition.CLEARED, True)
    assert read_back(client, rig) == "person"


def test_an_approval_given_before_the_digest_existed_stands(rig, monkeypatch):
    """A legacy approval (set by hand, with no digest, as every record approved on main) stands
    as on main, through a later finalize."""
    mounted(rig, Scripted())
    run_to_rest(rig)
    legacy = save_by_hand(rig, lambda run: setattr(run, "human_approved", True), "legacy-approval")
    assert legacy.run.approved_values_sha256 is None
    assert "approved_values_sha256" not in legacy.run.model_dump(mode="json")
    client = review_client(rig)
    queue_in_place(monkeypatch)
    act(client, rig, "resume", "resume-legacy")
    mounted(rig, Scripted())
    after = run_to_rest(rig)
    assert (after.run.disposition, after.run.human_approved) == (Disposition.CLEARED, True)
    assert read_back(client, rig) == "person"


# ---- a writer that changes a value ends the approval ----------------------------------------

def test_a_retry_whose_research_changes_a_value_ends_an_earlier_approval(rig, monkeypatch):
    mounted(rig, unresolved_country())
    done = run_to_rest(rig)
    assert done.run.disposition == Disposition.REVIEW
    assert done.run.fields["country"].state == ValueState.UNRESOLVED
    client = review_client(rig)
    approved = decide(client, rig, "approve-in-review", "approve")
    assert (approved.disposition, approved.human_approved) == (Disposition.REVIEW, True)
    queue_in_place(monkeypatch)
    retried = act(client, rig, "retry", "retry-research")
    assert FIELD_RESEARCH not in retried.run.completed_steps
    resolver = Scripted()
    mounted(rig, resolver)
    cleared = run_to_rest(rig)
    assert "country" in resolver.calls
    assert (cleared.run.disposition, cleared.run.human_approved) == (Disposition.CLEARED, False)
    assert read_back(client, rig) == "system"


def test_a_resume_of_research_that_did_not_finish_ends_an_earlier_approval(rig, monkeypatch):
    mounted(rig, Scripted({"country": failing("source_unavailable")}))
    blocked = rig.workflow.step(rig.principal, rig.specimen.id)
    assert blocked.run.stage == "retry_scheduled"
    client = review_client(rig)
    assert decide(client, rig, "approve-blocked", "approve").human_approved is True
    queue_in_place(monkeypatch)
    act(client, rig, "resume", "resume-research")
    mounted(rig, Scripted())
    after = run_to_rest(rig)
    assert after.run.human_approved is False
    assert read_back(client, rig) in {None, "system"}


def test_a_persons_edit_after_approving_ends_the_approval(rig):
    client = approved_and_cleared(rig)
    country = rig.repository.get(rig.principal.scope, rig.specimen.id).run.fields["country"]
    after = decide(client, rig, "edit-after-approval", "field", target_id="country",
        after=country.model_dump(mode="json", exclude={"evidence_ids"}) | {
            "parsed": "United States of America", "reason": "A person wrote the full name."},
        evidence_ids=list(country.evidence_ids))
    assert after.human_approved is False
    assert read_back(client, rig) != "person"


def test_a_persons_unchanged_field_submission_after_approving_ends_the_approval(rig):
    """Main's rule, kept: a person's own decision on the record withdraws a standing approval
    even when it submits the field exactly as it is (api.py, the field decision). The person
    has just acted on the record and approves again."""
    client = approved_and_cleared(rig)
    current = rig.repository.get(rig.principal.scope, rig.specimen.id).run
    country = current.fields["country"]
    after = decide(client, rig, "unchanged-field", "field", target_id="country",
        after=country.model_dump(mode="json", exclude={"evidence_ids"}),
        evidence_ids=list(country.evidence_ids))
    assert approved_values_digest(after) == current.approved_values_sha256
    assert after.human_approved is False
    assert read_back(client, rig) != "person"


def left_blocked(rig, redo, **state):
    """Save by hand the run as a worker left it, blocked before ``redo`` (as
    tests/test_first_pass_stuck_recovery.py `leave` does), holding no field values yet: the
    steps from ``redo`` on are not done, and the run holds the given state."""
    stored = rig.repository.get(rig.principal.scope, rig.specimen.id)
    run = stored.run
    order = ("first_pass:", "adjudicate", "parse")
    later = order[order.index(redo):]
    run.completed_steps = [step for step in run.completed_steps
        if not any(step == name or (name.endswith(":") and step.startswith(name)) for name in later)]
    if redo == "first_pass:":
        run.first_pass_decisions = []
    run.fields = {key: value.model_copy(update={"state": ValueState.UNKNOWN, "literal": None,
        "parsed": None, "normalized": None, "authority_id": None}) for key, value in run.fields.items()}
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
def test_the_drains_recovery_after_an_approval_on_a_record_with_no_values_never_reads_person(rig, case):
    """An approval lands on a blocked run holding no values (the decisions route), the drain's
    recovery makes it due with no run action, and the run produces its values: the approval
    no longer matches them by the time a disposition is decided."""
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
        # approval standing, is saved by hand instead.
        assert recovered is False
        save_by_hand(rig, lambda run: (setattr(run, "stage", "retry_scheduled"),
            setattr(run, "blocker", None)), "due")
    else:
        assert recovered is True
    mounted(rig, Scripted())
    after = run_to_rest(rig, through_retries=True)
    assert after.run.stage == "finalized"
    assert after.run.human_approved is False
    assert read_back(client, rig) != "person"


def test_a_derivation_in_the_recheck_after_an_approval_ends_it(tmp_path, monkeypatch):
    """Codex's round 3 case 2. Research is complete with the start date unresolved and the end
    date waiting on it. A resume, then the drain's `lane_handover_without_progress` before the
    recheck runs (saved by hand, as lane_worker's handover writes it). While blocked a person
    settles the start date and approves (the decisions route); a resume; the recheck derives
    the end date (ontology_checks.follow_sources), a value the approval did not cover."""
    rig = build_rig(tmp_path, label_with(date_visited_from="1X-14-46"))
    mounted(rig, Scripted({"date_visited_from": answering(CANNOT), "date_visited_to": answering(LACKS)}))
    done = run_to_rest(rig)
    assert done.run.fields["date_visited_to"].state == ValueState.UNKNOWN
    client = review_client(rig)
    queue_in_place(monkeypatch)
    act(client, rig, "resume", "resume-1")
    save_by_hand(rig, lambda run: (setattr(run, "stage", "processing_blocked"),
        setattr(run, "blocker", "lane_handover_without_progress")), "handover-stalled")
    start = rig.repository.get(rig.principal.scope, rig.specimen.id).run.fields["date_visited_from"]
    decide(client, rig, "start-1", "field", target_id="date_visited_from",
        after=start.model_dump(mode="json", exclude={"evidence_ids"}) | {
            "state": "supported", "literal": "1X-14-46", "parsed": "1946-09-14",
            "reason": "A person read the Roman month IX."},
        evidence_ids=list(start.evidence_ids))
    approved = decide(client, rig, "approve-1", "approve")
    assert approved.human_approved is True
    assert approved.fields["date_visited_to"].state == ValueState.UNKNOWN
    act(client, rig, "resume", "resume-2")
    mounted(rig, Scripted())
    after = run_to_rest(rig)
    end = after.run.fields["date_visited_to"]
    assert (end.state, end.parsed, end.layer) == (ValueState.SUPPORTED, "1946-09-14", "derived")
    assert after.run.human_approved is False
    assert read_back(client, rig) != "person"
