"""WP 1.8 part B (fix round 1 of PR #446): a person's field decision on a run the old first pass
processed is carried across the run's move to the units path (workflow.Workflow._move,
workflow.move_carries), as reprocess carries one to a new run (application/human_field_carry.py),
on every route that reopens the run: the decision itself (a taxon decision reopens the run at
lookup, api.py kind field), resume, retry and reassess_locations. Each test of the four routes
failed on dbaeace10, whose move ran parse again and replaced the person's value.

The record is test_human_field_carry_api's: the named SQL Connect repository over its synthetic
proof rows (the server's save audits a carry is proved from), its finished run then recorded as
the old path recorded one (test_old_path_migration.to_old_path)."""

from __future__ import annotations

import pytest

from specimen_digitization.application.api import SYNTHETIC_TEXT
from specimen_digitization.application.domain import Disposition, FieldValue, Principal
from specimen_digitization.application.human_field_carry import KEY, verify
from specimen_digitization.application.integrity import verify_evidence
from specimen_digitization.application.production import actor_uid
from specimen_digitization.application.reading_units import OLD, UNITS
from specimen_digitization.application.storage import digest
from specimen_digitization.application.workflow import SyntheticAdapters, Workflow
from test_human_field_carry_api import ACTORS, CarryApiCase, _drive, _finished_classified_run
from test_old_path_migration import Calls, to_old_path

FIELD_RESEARCH = "field_research"
VALUE = "Person Land"


@pytest.fixture
def case(tmp_path):
    value = CarryApiCase(tmp_path)
    yield value
    value.client.close()


def old_path(case, *, researched=False, carried=False):
    """The case's record, its first run finished with readers that differ and then recorded as the
    old path recorded it. ``researched``: as a run field research finished, in review, its city
    unsettled (what a location reassessment asks for, workflow.can_reassess_locations).
    ``carried``: that run was a new run (Start new run) carrying a person's city decision."""
    case.workflow.adapters = Calls(case.blobs)
    if carried:
        saved = case.save_unknown("city", "No city appears on the label")
        assert saved.status_code == 200, saved.text
    _finished_classified_run(case)
    specimen = to_old_path(case.current.model_copy(deep=True), case.blobs)
    if researched:
        specimen.run.completed_steps.append(FIELD_RESEARCH)
        specimen.run.attempts[FIELD_RESEARCH] = 1
        specimen.run.disposition = Disposition.REVIEW
        specimen.run.fields["city"] = FieldValue()
    principal = Principal(user_id=ACTORS[0], scope=specimen.scope, role="reviewer")
    token = actor_uid.set(ACTORS[0])
    try:
        case.current = case.repository.save(principal, specimen, specimen.version, "old-path",
            digest({"old_path": True}))
    finally:
        actor_uid.reset(token)
    assert case.current.run.first_pass_path == OLD
    case.workflow.adapters.labels.clear()
    return case.current


def post(case, path, body, key):
    current = case.workspace().json()
    body = {"expected_revision": current["revision"], **body}
    return case.client.post(f"{case.prefix}{path.format(**current)}", headers=case.headers(ACTORS[0], key), json=body)


def decide(case, field):
    current = case.workspace().json()
    evidence = case.current.run.evidence[0].id
    return post(case, f"/specimens/{case.current.id}/decisions", {
        "base_record_version_id": f"{current['active_run_id']}:{current['revision']}", "kind": "field",
        "target_id": field, "after": {"state": "supported", "literal": VALUE, "parsed": VALUE,
            "reason": "The person reads it on the label"},
        "evidence_ids": [evidence], "reason": "The person reads it on the label"}, f"decide-{field}")


def edit(case, text):
    current = case.workspace().json()
    return post(case, f"/specimens/{case.current.id}/decisions", {
        "base_record_version_id": f"{current['active_run_id']}:{current['revision']}", "kind": "transcription",
        "target_id": current["run"]["regions"][0]["id"], "after": {"text": text, "state": "supported"},
        "reason": "The person reads the label"}, "edit")


def moves(current):
    """The move's audit events: a reprocess of the run into itself (workflow.move_carries)."""
    run_id = current.run.id
    return [e for e in current.audit if e.action == "reprocess" and e.before.get("source_run_id") == run_id
        and e.after.get("target_run_id") == run_id]


def proved(case, current):
    token = actor_uid.set(ACTORS[0])
    try:
        return set(verify(case.repository, current, case.blobs).outcomes)
    finally:
        actor_uid.reset(token)


@pytest.mark.parametrize("route", ["decision", "resume", "retry", "reassess_locations"])
def test_a_persons_field_decision_is_carried_across_the_move(case, route):
    old_path(case, researched=route == "reassess_locations")
    field = "taxon" if route == "decision" else "country"
    decided = decide(case, field)
    assert decided.status_code == 200, decided.text
    if route == "decision":
        assert decided.json()["run"]["stage"] == "lookup"  # api.py: a taxon decision reopens the run
    else:
        response = post(case, "/runs/{active_run_id}/actions",
            {"action": route, "reason": "The person reopens the record"}, route)
        assert response.status_code == 200, response.text

    current = _drive(case, lambda s: False)
    run = current.run
    assert (run.first_pass_path, run.stage, run.blocker) == (UNITS, "finalized", None)
    assert case.workflow.adapters.labels == [region.id for region in run.regions]
    assert (run.fields[field].literal, run.fields[field].state) == (VALUE, "supported")
    [transition] = run.dependencies[KEY][field]["transitions"]
    assert [e.id for e in moves(current)] == [transition["event_id"]]
    assert transition["source_run_id"] == transition["target_run_id"] == run.id
    assert proved(case, current) == {field}
    verify_evidence(current, case.blobs)
    # A location reassessment it was queued for goes: every field is researched again.
    assert "location_reassessment" not in run.dependencies


def test_a_field_a_new_run_carried_stays_carried_beside_the_moves(case):
    """A run Start new run made with a person's city decision carried, then recorded on the old
    path: the move keeps that carry as it is and adds its own for the country decision."""
    old_path(case, carried=True)
    assert set(case.current.run.dependencies[KEY]) == {"city"}
    assert decide(case, "country").status_code == 200
    response = post(case, "/runs/{active_run_id}/actions", {"action": "resume", "reason": "Reopen"}, "resume")
    assert response.status_code == 200, response.text

    current = _drive(case, lambda s: False)
    run = current.run
    assert (run.first_pass_path, run.stage, run.blocker) == (UNITS, "finalized", None)
    assert run.fields["city"].reason == "No city appears on the label"
    assert run.fields["country"].literal == VALUE
    [city] = run.dependencies[KEY]["city"]["transitions"]
    assert city["source_run_id"] != city["target_run_id"] == run.id
    assert proved(case, current) == {"city", "country"}


def test_a_transcript_edit_after_a_field_decision_replaces_it_as_on_any_run(case):
    """A transcript edit makes the run parse again, which replaces the field decisions saved before
    it (api.py, kind transcription), on a units-path run as on this one: the move carries none."""
    old_path(case)
    assert decide(case, "country").status_code == 200
    assert edit(case, "country: Edited Land").status_code == 200

    current = _drive(case, lambda s: False)
    run = current.run
    assert (run.first_pass_path, run.stage, run.blocker) == (UNITS, "finalized", None)
    assert run.fields["country"].literal == "Edited Land"
    assert KEY not in run.dependencies and moves(current) == []


def test_a_field_decision_after_a_transcript_edit_is_carried_with_the_edit(case):
    """Both of a person's decisions stay: the transcript (adjudicate applies it again) and the field
    decision saved after it (carried: move_carries reads the run's proofs with its transcript
    decisions kept, where reprocess refuses a run that holds one)."""
    old_path(case)
    text = "country: Edited Land"
    assert edit(case, text).status_code == 200
    assert decide(case, "country").status_code == 200

    current = _drive(case, lambda s: False)
    run = current.run
    assert (run.first_pass_path, run.stage, run.blocker) == (UNITS, "finalized", None)
    assert run.fields["country"].literal == VALUE
    [transcript] = run.transcripts
    assert (transcript.actor, transcript.text) == (ACTORS[0], text)
    assert proved(case, current) == {"country"}


def test_a_due_retry_moves_with_carries_proved_from_the_record_as_saved(case):
    """A step clears a due retry's blocker before it moves the run (Workflow._step): the move's
    carries are proved against the record as saved, which the server's proofs hold."""
    old_path(case)
    assert decide(case, "country").status_code == 200
    principal = Principal(user_id=ACTORS[0], scope=case.current.scope, role="reviewer")
    token = actor_uid.set(ACTORS[0])
    try:
        waiting = case.repository.get(case.current.scope, case.current.id)
        waiting.run.stage, waiting.run.blocker = "retry_scheduled", "temporary_provider_failure"
        waiting.run.next_retry_at = "2026-01-01T00:00:00+00:00"
        case.current = case.repository.save(principal, waiting, waiting.version, "due-retry", digest({"due": True}))
    finally:
        actor_uid.reset(token)

    current = _drive(case, lambda s: False)
    run = current.run
    assert (run.first_pass_path, run.stage, run.blocker) == (UNITS, "finalized", None)
    assert run.fields["country"].literal == VALUE
    assert proved(case, current) == {"country"}


# ---- Fix round 2 (Codex's and G51's reviews of 3ff7459a). Each test failed on 3ff7459a, except
# the units-run control of test_a_transcript_edit_after_the_move_replaces_a_carried_field_as_on_a_units_run
# and test_only_the_field_decisions_after_the_latest_edit_are_carried, added for a mutant of
# move_carries' own check of the latest edit.

def step_once(case):
    token = actor_uid.set(ACTORS[0])
    try:
        principal = Principal(user_id=ACTORS[0], scope=case.current.scope, role="reviewer")
        case.current = case.workflow.step(principal, case.current.id)
    finally:
        actor_uid.reset(token)
    return case.current


def test_the_save_after_an_edited_runs_first_step_passes_the_integrity_check(case):
    """Codex's input: a person's edit of an old-path transcript, then one worker step. The edited
    label's text source is the person's text, so it gets no units call (Workflow.next_step): the
    first step is adjudicate, which cuts the person's text into the label's units, and the save
    passes the integrity check, so an approval then blocks nothing."""
    old_path(case)
    assert edit(case, "country: Edited Land").status_code == 200
    current = step_once(case)
    verify_evidence(current, case.blobs)
    assert current.run.first_pass_path == UNITS and case.workflow.adapters.labels == []
    current_ws = case.workspace().json()
    approved = post(case, f"/specimens/{case.current.id}/decisions", {
        "base_record_version_id": f"{current_ws['active_run_id']}:{current_ws['revision']}", "kind": "approve",
        "target_id": case.current.id, "after": {}, "reason": "Reviewed"}, "approve")
    assert approved.status_code == 200, approved.text
    assert approved.json()["run"]["blocker"] != "evidence_integrity_failure"


class Same(Calls):
    """Both readers read the label alike, so the units run's parse gives fields and evidence."""

    def __init__(self, blobs):
        SyntheticAdapters.__init__(self, blobs, SYNTHETIC_TEXT)
        self.labels = []


def units_run(case):
    """The case's record, its first run finished on the units path (no move)."""
    case.workflow.adapters = Same(case.blobs)
    _finished_classified_run(case)
    assert case.current.run.first_pass_path == UNITS
    case.workflow.adapters.labels.clear()


@pytest.mark.parametrize("record", ["moved", "units-run"])
def test_a_transcript_edit_after_the_move_replaces_a_carried_field_as_on_a_units_run(case, record):
    """Codex's input: country decided ("Person Land"), the run moved with that decision carried,
    then the transcript edited to "country: Edited Land": the edit ends the move's carry
    (workflow.end_move_carries) and the re-parse gives "Edited Land", as on a units-path run with
    the same two decisions and no carry (the control)."""
    if record == "moved":
        old_path(case)
        assert decide(case, "country").status_code == 200
        response = post(case, "/runs/{active_run_id}/actions", {"action": "resume", "reason": "Reopen"}, "resume")
        assert response.status_code == 200, response.text
        moved = _drive(case, lambda s: False)
        assert moved.run.fields["country"].literal == VALUE and set(moved.run.dependencies[KEY]) == {"country"}
    else:
        units_run(case)
        assert decide(case, "country").status_code == 200
    edited = edit(case, "country: Edited Land")
    assert edited.status_code == 200, edited.text

    current = _drive(case, lambda s: False)
    run = current.run
    assert (run.first_pass_path, run.stage, run.blocker) == (UNITS, "finalized", None)
    assert run.fields["country"].literal == "Edited Land"
    assert KEY not in run.dependencies
    assert not [e for e in run.evidence if e.kind == "ordinary_human_field_carry"]
    event = [e for e in edited.json()["events"] if e["action"] == "review_transcription"][-1]
    assert event["after"].get("superseded_carried_fields", []) == (["country"] if record == "moved" else [])


def test_only_the_field_decisions_after_the_latest_edit_are_carried(case):
    """Country decided, the transcript edited, then city decided: the move carries city, and the
    re-parse the edit started replaces country, as on any run (move_carries)."""
    old_path(case)
    assert decide(case, "country").status_code == 200
    assert edit(case, "country: Edited Land").status_code == 200
    assert decide(case, "city").status_code == 200

    current = _drive(case, lambda s: False)
    run = current.run
    assert (run.first_pass_path, run.stage, run.blocker) == (UNITS, "finalized", None)
    assert (run.fields["country"].literal, run.fields["city"].literal) == ("Edited Land", VALUE)
    assert set(run.dependencies[KEY]) == {"city"} and proved(case, current) == {"city"}

def many_decisions(case, count):
    from specimen_digitization.application.domain import MANDATORY

    keys = list(MANDATORY)
    for index in range(count):
        response = case.save_unknown(keys[index % len(keys)], f"No value on the label ({index})", key=f"d{index}")
        assert response.status_code == 200, response.text


def test_a_record_whose_field_decisions_an_edit_replaced_moves_reading_no_proofs(case):
    """G51's input: 24 field decisions, then a transcript edit. The edit replaces them, so the move
    has nothing to carry and reads no proofs (Workflow._move, _field_decided_since_edit): it moves
    and completes, where reading them passed the proof reader's bound (storage.REVIEW_PROOF_READS)
    and blocked."""
    old_path(case)
    many_decisions(case, 24)
    assert edit(case, "country: Edited Land").status_code == 200
    current = _drive(case, lambda s: False)
    assert (current.run.first_pass_path, current.run.stage, current.run.blocker) == (UNITS, "finalized", None)
    assert current.run.fields["country"].literal == "Edited Land"


@pytest.mark.parametrize(("count", "path"), [(24, UNITS), (26, OLD)], ids=["moved", "unmoved"])
def test_a_record_over_the_proof_bound_stays_blocked_until_a_transcript_edit(case, count, path):
    """A record that does need a carry (field decisions, then a resume) and whose proofs the proof
    reader cannot read within its bound (storage.REVIEW_PROOF_READS) blocks, the person's values
    kept: unmoved when the move cannot read them (26 decisions), or moved, before adjudicate, with
    the carried values in place when a later step's check of the carries cannot, the record having
    grown (24). A transcript edit is the way out: it replaces those decisions and ends the move's
    carries, as on any run (on a moved run before adjudicate it gives the label its first
    transcript, api.py), and the run completes."""
    old_path(case)
    many_decisions(case, count)
    reason = f"No value on the label ({max(i for i in range(count) if i % 20 == 5)})"  # city, MANDATORY[5]
    response = post(case, "/runs/{active_run_id}/actions", {"action": "resume", "reason": "Reopen"}, "resume")
    assert response.status_code == 200, response.text
    blocked = _drive(case, lambda s: False)
    assert (blocked.run.first_pass_path, blocked.run.stage, blocked.run.blocker) == (
        path, "processing_blocked", "preserved_human_field_provenance_unavailable")
    assert (blocked.run.fields["city"].state, blocked.run.fields["city"].reason) == ("unknown", reason)

    assert edit(case, "country: Edited Land").status_code == 200
    current = _drive(case, lambda s: False)
    assert (current.run.first_pass_path, current.run.stage, current.run.blocker) == (UNITS, "finalized", None)
    assert current.run.fields["country"].literal == "Edited Land"


def test_a_restore_of_the_run_before_its_move_does_not_refill_its_allowance(case):
    """Codex's sequence of round 2, through HTTP: the run moves and its first pass fails on every
    attempt of its fresh allowance; the person restores the revision from before the move and
    resumes. The restored run keeps the move's count of attempts as it keeps its attempts
    (history_restore), so its second move refills nothing: no further first-pass call, the step
    given up unsent."""
    from datetime import datetime, timedelta, timezone

    from test_old_path_migration import FailingFirstPass

    old_path(case)
    before_move = case.current.version
    adapters = FailingFirstPass(case.blobs)
    clock = {"now": datetime.now(timezone.utc)}

    def later():
        clock["now"] += timedelta(hours=2)
        return clock["now"]

    case.workflow = Workflow(case.repository, case.blobs, adapters, profile_registry=case.registry, clock=later)
    resumed = post(case, "/runs/{active_run_id}/actions", {"action": "resume", "reason": "Reopen"}, "resume")
    assert resumed.status_code == 200, resumed.text
    run = _drive(case, lambda s: False).run
    region = run.regions[0].id
    step, cap = f"first_pass:{region}", run.profile.execution.max_attempts
    assert (run.first_pass_path, run.stage) == (UNITS, "finalized") and len(adapters.labels) == cap
    attempts, count = run.attempts[step], run.dependencies["attempts_at_units_move"]
    assert attempts == count[step] + cap

    current = case.workspace().json()
    restored = post(case, f"/specimens/{case.current.id}/history:restore", {
        "base_record_version_id": f"{current['active_run_id']}:{current['revision']}",
        "source_revision": before_move, "reset_to_initial": False, "reason": "Restore the run before its move"},
        "restore")
    assert restored.status_code == 200, restored.text
    assert restored.json()["run"].get("first_pass_path", OLD) == OLD  # the stored default is left out
    resumed = post(case, "/runs/{active_run_id}/actions", {"action": "resume", "reason": "Reopen again"}, "resume-2")
    assert resumed.status_code == 200, resumed.text

    run = _drive(case, lambda s: False).run
    assert (run.first_pass_path, run.stage, run.blocker) == (UNITS, "finalized", None)
    assert len(adapters.labels) == cap and run.attempts[step] == attempts
    assert run.dependencies["attempts_at_units_move"] == count
