"""Holds that outlive a recomputation, through the real routes (plan WP K1, Codex rounds 2 and 3 on #455).

Each is derived, every time the reasons are computed, from state recorded on the run when its cause
happened (application/standing_holds.py: run.pending_review, the give-up finding); a blocker may replace
the reasons list freely. On main the same holds were lost on these routes (a blocked refinalize replaced
the reasons with its blocker; a recheck recomputed them), but a mandatory field's own reason almost
always held such a record anyway; with only the catalogue number mandatory it would clear.
"""

from specimen_digitization.application.collection_profiles import published_registry
from specimen_digitization.application.domain import Disposition
from specimen_digitization.application.standing_holds import APPROVAL, GIVEN_UP, HISTORY_RESTORED

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
