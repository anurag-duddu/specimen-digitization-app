"""Unpinned research does not suppress canonical human review decisions."""

from copy import deepcopy

import pytest

from specimen_digitization.application.domain import AuditEvent, Principal
from specimen_digitization.application.production import SqlConnectRepository, actor_uid
from specimen_digitization.application.storage import ProjectionResult, digest
from test_review_projection_provenance import ORIGINAL_TIME, failed_original, save
from test_review_projection_race import project


def unpin(value, state="absent"):
    if state == "absent":
        value.run.profile_snapshot = {}
        value.run.dependencies = {}
    else:
        value.run.dependencies["profile_snapshot_sha256"] = "f" * 64
    return value


def worker_save(repo, value):
    token = actor_uid.set("B")
    try:
        return repo.save(Principal(user_id="B", scope=value.scope, role="operator"),
                         unpin(value), value.version, "worker-unpin", digest("worker-unpin"))
    finally:
        actor_uid.reset(token)


@pytest.mark.parametrize("pin_state", ["absent", "mismatch"])
def test_unpinned_current_reviewer_catches_up_original_author_time_and_revisions(tmp_path, pin_state):
    repo, session, blobs, value = failed_original(tmp_path)
    original = value.audit[0].model_dump()
    session.active.remove("A")
    value = unpin(value, pin_state)
    value.audit.append(AuditEvent(actor="B", action="review_classification", reason="repin research"))
    before = len(session.calls)
    committed = save(SqlConnectRepository(session=session, graph_blobs=blobs), value, "B", "review-unpin")
    actual = session.decisions[original["id"]]
    assert (actual["actorUid"], actual["baseRevision"], actual["resultingRevision"], actual["createdAt"]) == ("A", 1, 2, ORIGINAL_TIME)
    assert committed.audit[0].model_dump() == original
    writes = [(op, variables) for op, variables in session.calls[before:] if op.startswith(("Append", "Register", "Record"))]
    assert [op for op, _ in writes] == ["AppendSourceAssetV2", "AppendReviewDecisionV2", "AppendReviewDecisionV2"]
    assert all(variables["actorUid"] == "B" for _, variables in writes)
    assert session.decisions[committed.audit[1].id]["baseRevision"] == 2
    assert session.decisions[committed.audit[1].id]["resultingRevision"] == 3


def test_actual_unpinned_worker_save_excludes_human_rows(tmp_path):
    repo, session, blobs, value = failed_original(tmp_path)
    original = deepcopy(value.audit[0].model_dump())
    before = len(session.calls)
    committed = worker_save(repo, value)
    assert committed.version == 3 and committed.audit[0].model_dump() == original
    assert session.decisions == {}
    assert not any(op in {"GetReviewSaveProofV1", "AppendReviewDecisionV2"} for op, _ in session.calls[before:])


def test_unpinned_missing_original_proof_is_incomplete_with_zero_normalized_writes(tmp_path):
    repo, session, blobs, value = failed_original(tmp_path)
    current = worker_save(repo, value)
    session.snapshots.pop(1)
    before = len(session.calls)
    assert project(SqlConnectRepository(session=session, graph_blobs=blobs), current) == ProjectionResult(False, "not_computed")
    assert not any(op.startswith(("Append", "Register", "Record")) for op, _ in session.calls[before:])
    assert session.decisions == {} and session.snapshots[3]["sha256"] == digest(session.snapshots[3]["snapshot"])
