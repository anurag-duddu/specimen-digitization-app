"""Holds that outlive a recomputation, through the real routes (plan WP K1, Codex rounds 2 and 3 on #455).

Each is derived, every time the reasons are computed, from state recorded on the run when its cause
happened (application/standing_holds.py: run.pending_review, the give-up finding); a blocker may replace
the reasons list freely. On main the same holds were lost on these routes (a blocked refinalize replaced
the reasons with its blocker; a recheck recomputed them), but a mandatory field's own reason almost
always held such a record anyway; with only the catalogue number mandatory it would clear.
"""

import ast
import importlib
import inspect

from specimen_digitization.application.collection_profiles import published_registry
from specimen_digitization.application.domain import Disposition
from specimen_digitization.application.standing_holds import (
    APPROVAL, GIVEN_UP, HISTORY_RESTORED, REASSESSMENT_UNCONFIRMED as REASSESSMENT)

from test_approval_and_research import act, queue_in_place, run_to_rest
from test_step import ORG, Scripted, build_rig, decide, mounted, review_client

HEADERS = {"Authorization": "Bearer reviewer"}


def cleared(tmp_path):
    rig = build_rig(tmp_path, profile=published_registry().profiles[0])
    mounted(rig, Scripted())
    done = run_to_rest(rig)
    assert (done.run.disposition, done.run.reasons) == (Disposition.CLEARED, [])
    return rig, review_client(rig)


def test_a_pending_approval_survives_an_integrity_block_and_the_resume_after_its_repair(tmp_path, monkeypatch):
    """A person's decision leaves the approval pending; the next decision finds the image's bytes missing and
    blocks the run (evidence_integrity_failure); the bytes are put back and the run resumed. The approval hold
    is back and the record does not clear until a person approves."""
    rig, client = cleared(tmp_path)
    held = decide(client, rig, "coverage-1", "coverage", after={"confirmed": True})
    assert (held.disposition, held.reasons) == (Disposition.REVIEW, [APPROVAL])

    image = rig.blobs.root / rig.specimen.asset.blob_ref
    away = image.with_name(image.name + ".away")
    image.rename(away)
    blocked = decide(client, rig, "coverage-2", "coverage", after={"confirmed": True})
    # The blocker replaces the reasons; the hold stays recorded on the run.
    assert (blocked.blocker, blocked.reasons) == ("evidence_integrity_failure", ["evidence_integrity_failure"])
    assert blocked.pending_review == [APPROVAL]

    away.rename(image)
    queue_in_place(monkeypatch)
    act(client, rig, "resume", "resume-repaired")
    mounted(rig, Scripted())
    after = run_to_rest(rig).run
    assert after.blocker is None
    assert (after.disposition, after.reasons) == (Disposition.REVIEW, [APPROVAL])
    approved = decide(client, rig, "approve-repaired", "approve")
    assert (approved.disposition, approved.human_approved) == (Disposition.CLEARED, True)


def test_a_history_restore_s_review_hold_survives_a_resume(tmp_path, monkeypatch):
    """Restore a completed revision bound to the skeletal profile, with a sound catalogue number and no field
    decision carried, then Resume: the recheck keeps history_restored_requires_review until a person approves."""
    rig, client = cleared(tmp_path)
    source = rig.repository.get(rig.principal.scope, rig.specimen.id)
    decide(client, rig, "coverage-1", "coverage", after={"confirmed": True})
    current = rig.repository.get(rig.principal.scope, rig.specimen.id)
    response = client.post(f"/v1/organizations/{ORG}/specimens/{current.id}/history:restore",
        headers={**HEADERS, "Idempotency-Key": "restore"},
        json={"expected_revision": current.version, "base_record_version_id": f"{current.run.id}:{current.version}",
            "source_revision": source.version, "reset_to_initial": False, "reason": "Back to the system's run"})
    assert response.status_code == 200, response.text
    restored = rig.repository.get(rig.principal.scope, rig.specimen.id).run
    assert (restored.disposition, HISTORY_RESTORED in restored.reasons) == (Disposition.REVIEW, True)

    queue_in_place(monkeypatch)
    act(client, rig, "resume", "resume-restored")
    mounted(rig, Scripted())
    after = run_to_rest(rig).run
    assert after.disposition == Disposition.REVIEW and HISTORY_RESTORED in after.reasons
    approved = decide(client, rig, "approve-restored", "approve")
    assert (approved.disposition, approved.human_approved) == (Disposition.CLEARED, True)


def test_a_first_decision_that_meets_an_integrity_block_still_waits_for_approval(tmp_path, monkeypatch):
    """Codex round 3: the person's first decision finds the image's bytes missing; refinalize returns at the
    block, but the decision's approval hold was recorded first. After the repair and Resume the record waits
    for approval."""
    rig, client = cleared(tmp_path)
    image = rig.blobs.root / rig.specimen.asset.blob_ref
    away = image.with_name(image.name + ".away")
    image.rename(away)
    blocked = decide(client, rig, "coverage-1", "coverage", after={"confirmed": True})
    assert (blocked.blocker, blocked.pending_review) == ("evidence_integrity_failure", [APPROVAL])

    away.rename(image)
    queue_in_place(monkeypatch)
    act(client, rig, "resume", "resume-repaired")
    mounted(rig, Scripted())
    after = run_to_rest(rig).run
    assert after.blocker is None
    assert (after.disposition, after.reasons) == (Disposition.REVIEW, [APPROVAL])


def test_research_given_up_survives_a_size_limit_block_and_a_resume(tmp_path, monkeypatch):
    """Codex round 3: research given up for the run (FieldResearchStep.give_up, its finding on the run); a
    save then over the snapshot limit blocks the run and replaces its reasons (active_graph.save_recoverably's
    recovery, applied here by hand as it applies it); Resume rechecks. The give-up still holds the record,
    derived from its finding, until research runs again or a person approves."""
    from test_approval_and_research import save_by_hand

    rig, client = cleared(tmp_path)
    specimen = rig.repository.get(rig.principal.scope, rig.specimen.id)
    rig.workflow.field_research.give_up(rig.workflow, rig.principal, specimen, "token_budget_exhausted")
    assert specimen.run.reasons == [GIVEN_UP] and specimen.run.disposition == Disposition.REVIEW
    rig.specimen = rig.repository.save(rig.principal, specimen, specimen.version, "given-up", "given-up")

    def size_limit(run):
        run.stage, run.disposition, run.blocker = "processing_blocked", None, "snapshot_limit_exceeded"
        run.reasons, run.human_approved, run.lease_until = ["snapshot_limit_exceeded"], False, None

    save_by_hand(rig, size_limit, "size-limit")
    queue_in_place(monkeypatch)
    act(client, rig, "resume", "resume-after-size-limit")
    mounted(rig, Scripted())
    after = run_to_rest(rig).run
    assert after.blocker is None
    assert (after.disposition, after.reasons) == (Disposition.REVIEW, [GIVEN_UP])


# ---- Codex round 4 on #455 ----------------------------------------------------------------------

# Every decision kind the API accepts (api.py apply_decision); a new kind fails the test below until listed.
KINDS = {"research_candidate", "field", "transcription", "authority_resolution", "taxonomy_resolution",
    "capability_defer", "reading_metadata", "approve", "coverage"}


def decision_entry():
    """api.py's apply_decision, the one place a person's decision enters, and the kinds it names."""
    from specimen_digitization.application import api

    tree = ast.parse(inspect.getsource(api))
    entry = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "apply_decision")
    kinds, lines = set(), []
    for node in ast.walk(entry):
        if (isinstance(node, ast.Compare) and isinstance(node.left, ast.Attribute) and node.left.attr == "kind"
                and isinstance(node.left.value, ast.Name) and node.left.value.id == "body"):
            if isinstance(node.ops[0], ast.Eq):  # a kind's own branch (a refusal before it changes nothing)
                lines.append(node.lineno)
            kinds |= {constant.value for comparator in node.comparators for constant in ast.walk(comparator)
                if isinstance(constant, ast.Constant) and isinstance(constant.value, str)}
    acted = [node.lineno for node in ast.walk(entry)
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "person_acted"]
    return kinds, min(lines), acted


def test_every_decision_kind_records_the_approval_hold_where_it_enters(tmp_path, monkeypatch):
    """A person's decision records human_approval_required where it enters (api.py apply_decision), before any
    kind's own effect and whatever the run's stage or blocker. Every kind the API accepts, through the
    decisions route: the hold is recorded on the record it decides, whether or not that kind's own checks then
    accept the request (an approve decision's approval then clears it, lane.approve). A research candidate
    choice enters the same way: candidate_decisions applies each choice through apply_decision."""
    from specimen_digitization.application import standing_holds

    kinds, first_kind, acted = decision_entry()
    assert kinds == KINDS, "a decision kind was added or removed: list it in KINDS"
    assert len(acted) == 1 and acted[0] < first_kind
    assert "apply_decision(organization_id, specimen_id, item," in inspect.getsource(
        importlib.import_module("specimen_digitization.application.api"))

    rig, client = cleared(tmp_path)
    recorded = []

    def spy(run):
        real(run)
        recorded.append(list(run.pending_review))

    real = standing_holds.person_acted
    monkeypatch.setattr(standing_holds, "person_acted", spy)
    for kind in sorted(KINDS - {"research_candidate"}):
        recorded.clear()
        current = rig.repository.get(rig.principal.scope, rig.specimen.id)
        client.post(f"/v1/organizations/{ORG}/specimens/{current.id}/decisions",
            headers={**HEADERS, "Idempotency-Key": "kind-" + kind},
            json={"expected_revision": current.version, "kind": kind, "reason": "Reviewed.",
                "base_record_version_id": f"{current.run.id}:{current.version}", "after": {"confirmed": True}})
        assert recorded == [[APPROVAL]] or (kind == "approve" and recorded and APPROVAL in recorded[0]), kind
        stored = rig.repository.get(rig.principal.scope, rig.specimen.id)
        if kind == "approve":
            assert (stored.run.human_approved, stored.run.pending_review) == (True, []), kind
        elif stored.version != current.version:
            # Recorded on the record the decision saved, an approved record included: an approval that
            # later stops standing (lane.settle_approval) leaves it waiting for the person again.
            assert APPROVAL in stored.run.pending_review, kind


def test_a_transcript_edit_on_a_system_cleared_record_waits_for_approval_after_research(tmp_path):
    """Codex round 4: a person edits a label's transcript on a record the system cleared. The edit sends the run
    back to parse, so no finalize follows it; research then runs again and would clear the record. It waits for
    the person's approval, recorded where their decision entered."""
    rig, client = cleared(tmp_path)
    run = rig.repository.get(rig.principal.scope, rig.specimen.id).run
    assert run.pending_review == []
    region = run.regions[-1].id
    text = next(t.text for t in run.transcripts if t.region_id == region)
    edited = decide(client, rig, "transcription-1", "transcription", target_id=region,
        after={"text": text, "state": "supported"})
    assert edited.stage == "parse" and edited.pending_review == [APPROVAL]
    mounted(rig, Scripted())
    after = run_to_rest(rig).run
    assert after.blocker is None
    assert (after.disposition, after.reasons) == (Disposition.REVIEW, [APPROVAL])
    approved = decide(client, rig, "approve-edited", "approve")
    assert (approved.disposition, approved.human_approved) == (Disposition.CLEARED, True)


def size_limit(run):
    """What active_graph.save_recoverably's recovery leaves on a run."""
    run.stage, run.disposition, run.blocker = "processing_blocked", None, "snapshot_limit_exceeded"
    run.reasons, run.human_approved, run.lease_until = ["snapshot_limit_exceeded"], False, None


def test_a_first_decision_on_an_already_blocked_record_waits_for_approval_after_resume(tmp_path, monkeypatch):
    """Codex round 4: the person's first decision (coverage) is made while the run is blocked, so no finalize
    follows it. After Resume the record waits for their approval."""
    from test_approval_and_research import save_by_hand

    rig, client = cleared(tmp_path)
    save_by_hand(rig, size_limit, "size-limit")
    decided = decide(client, rig, "coverage-blocked", "coverage", after={"confirmed": True})
    assert (decided.blocker, decided.pending_review) == ("snapshot_limit_exceeded", [APPROVAL])
    queue_in_place(monkeypatch)
    act(client, rig, "resume", "resume-after-decision")
    mounted(rig, Scripted())
    after = run_to_rest(rig).run
    assert after.blocker is None
    assert (after.disposition, after.reasons) == (Disposition.REVIEW, [APPROVAL])


def stored_before_the_key(rig, change=None):
    """The rig's record as a run stored before pending_review existed holds a person's pending approval: in
    its reasons alone, with no key."""
    legacy = rig.repository.get(rig.principal.scope, rig.specimen.id)
    legacy.run.pending_review, legacy.run.reasons = None, [APPROVAL]
    legacy.run.disposition, legacy.run.human_approved = Disposition.REVIEW, False
    if change is not None:
        change(legacy.run)
    rig.specimen = rig.repository.save(rig.principal, legacy, legacy.version, "legacy", "legacy")
    return rig.specimen


def test_a_legacy_run_s_approval_survives_a_size_limit_recovery_and_a_resume(tmp_path, monkeypatch):
    """Codex round 4: the first save after the upgrade of a run stored before the key is over the snapshot
    limit; the recovery (active_graph.save_recoverably) replaces the stored reasons with its blocker. The run
    adopted its hold where it was loaded, before the recovery wrote the reasons, so after Resume the record
    waits for approval."""
    from specimen_digitization.application.active_graph import save_recoverably
    from specimen_digitization.application.storage import SnapshotTooLarge

    rig, client = cleared(tmp_path)
    legacy = stored_before_the_key(rig)

    class OverTheLimitOnce:
        def __init__(self, inner):
            self.inner, self.refused = inner, False

        def save(self, *args):
            if not self.refused:
                self.refused = True
                raise SnapshotTooLarge("snapshot_limit_exceeded")
            return self.inner.save(*args)

        def get(self, *args):
            return self.inner.get(*args)

    recovered = save_recoverably(OverTheLimitOnce(rig.repository), rig.principal, legacy, legacy.version,
        "over-the-limit", "over-the-limit")
    assert (recovered.run.blocker, recovered.run.reasons) == ("snapshot_limit_exceeded", ["snapshot_limit_exceeded"])
    rig.specimen = recovered
    queue_in_place(monkeypatch)
    act(client, rig, "resume", "resume-legacy")
    mounted(rig, Scripted())
    after = run_to_rest(rig).run
    assert after.blocker is None
    assert (after.disposition, after.reasons) == (Disposition.REVIEW, [APPROVAL])


def test_a_legacy_run_s_approval_survives_a_successful_reassessment(tmp_path, monkeypatch):
    """Codex round 4: a run stored before the key, with a person's pending approval in its reasons alone, has
    its location family reassessed successfully. The approval still holds the record."""
    from test_location_reassessment import execute, old_location_run

    rig = old_location_run(tmp_path)
    rig.specimen.run.pending_review, rig.specimen.run.reasons = None, [APPROVAL]
    _, done, _, _, _ = execute(rig, monkeypatch)
    assert not any(code.startswith(REASSESSMENT + ":") for code in done.run.reasons)
    assert done.run.pending_review == [APPROVAL]
    assert APPROVAL in done.run.reasons and done.run.disposition == Disposition.REVIEW


def test_an_integrity_failure_during_a_reassessment_keeps_its_earlier_unconfirmed_location(tmp_path, monkeypatch):
    """Codex round 4: a supported city carries location_reassessment_unconfirmed:city; another reassessment
    again cannot qualify it, and the final evidence check then fails. The earlier entry stays exactly as it
    was, so the record stays held for it after the repair."""
    from specimen_digitization.application.integrity import EvidenceIntegrityError
    from specimen_digitization.field_research import step as field_step
    from test_location_reassessment import execute, old_location_run

    rig = old_location_run(tmp_path)
    rig.specimen.run.pending_review = [f"{REASSESSMENT}:city"]

    def unavailable(specimen, blobs):
        raise EvidenceIntegrityError("evidence_integrity_failure")

    monkeypatch.setattr(field_step, "verify_evidence", unavailable)
    _, done, _, _, _ = execute(rig, monkeypatch, outage=True)
    assert done.run.blocker is not None
    assert done.run.pending_review == [f"{REASSESSMENT}:city"]
    # Repaired: the finalize after it derives the hold again.
    monkeypatch.undo()
    done.run.blocker = None
    field_step.refinalize(done.run)
    assert f"{REASSESSMENT}:city" in done.run.reasons and done.run.disposition == Disposition.REVIEW


def test_a_reassessment_that_researches_removes_an_earlier_give_up(tmp_path, monkeypatch):
    """Codex round 4: research given up for the run, then an admitted reassessment researches and succeeds. Its
    commit does not copy the give-up finding back: research ran again, so it no longer holds the record."""
    from specimen_digitization.application.domain import RunFinding
    from specimen_digitization.field_research import step as field_step
    from test_location_reassessment import execute, old_location_run

    rig = old_location_run(tmp_path)
    rig.specimen.run.findings.append(RunFinding(rule_id=GIVEN_UP, rule_version=field_step.GIVEN_UP_RULES,
        severity="warning", reason_code=f"{GIVEN_UP}:token_budget_exhausted"))
    _, done, _, _, _ = execute(rig, monkeypatch)
    assert not any(finding.rule_id == GIVEN_UP for finding in done.run.findings)
    assert GIVEN_UP not in done.run.reasons
