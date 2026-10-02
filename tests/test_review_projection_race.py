"""Actual adapter race/replay controls with synthetic named-call transport only."""

from copy import deepcopy
from uuid import uuid4

import pytest

from specimen_digitization.application.domain import AuditEvent
from specimen_digitization.application.production import SqlConnectRepository, actor_uid
from specimen_digitization.application.storage import LocalBlobs, ProjectionResult, digest
from test_projection_writer import Response
from test_review_projection_provenance import CanonicalSession, ORIGINAL_TIME, failed_original, specimen


class RaceSession:
    """Interleave a V1-style row between observed proof and actual V2 insertion."""

    def __init__(self, retained):
        self.retained = retained
        self.before_review_insert = None
        self.after_proof_observation = None
        self.conflict_read = None
        self.saw_conflict = False
        self.proof_queries = 0

    def post(self, url, json, timeout):
        operation, variables = json["operationName"], json["variables"]
        if operation == "AppendReviewDecisionV2" and self.before_review_insert:
            interleave, self.before_review_insert = self.before_review_insert, None
            interleave(variables)
        if operation == "GetReviewSaveProofV1":
            self.proof_queries += 1
            if self.saw_conflict and self.conflict_read == "unobservable":
                self.retained.calls.append((operation, deepcopy(variables)))
                return Response({}, status=503)
        response = self.retained.post(url, json, timeout)
        # A response is the already-observed state, not an alias to mutable fake rows.
        response = Response(deepcopy(response.body), response.status_code)
        if operation == "AppendReviewDecisionV2" and response.body.get("errors"):
            self.saw_conflict = True
        if operation == "GetReviewSaveProofV1":
            if self.saw_conflict and self.conflict_read == "missing":
                response.body["data"]["decision"] = None
            if self.after_proof_observation:
                interleave, self.after_proof_observation = self.after_proof_observation, None
                interleave(variables)
        return response


def row_from(variables):
    return {"id": variables["id"], "specimenId": variables["specimenId"],
            "actorUid": variables["decisionActorUid"], "baseRevision": variables["baseRevision"],
            "resultingRevision": variables["resultingRevision"], "reason": variables["reason"],
            "correction": deepcopy(variables["correction"]), "createdAt": variables["createdAt"]}


def project(repo, value):
    token = actor_uid.set("B")
    try:
        return repo.write_projection(value.scope, value, reviewer=True)
    finally:
        actor_uid.reset(token)


@pytest.mark.parametrize("field", ["id", "specimenId", "actorUid", "baseRevision", "resultingRevision", "reason", "correction", "createdAt"])
def test_wrong_row_winning_v2_pk_race_is_never_certified(tmp_path, field, caplog):
    _, retained, blobs, value = failed_original(tmp_path)
    session = RaceSession(retained)
    def raced(variables):
        row = row_from(variables)
        row[field] = {"id": str(uuid4()), "specimenId": str(uuid4()), "actorUid": "B",
                      "baseRevision": 2, "resultingRevision": 3, "reason": "different",
                      "correction": {"action": "other"}, "createdAt": "2026-09-30T00:00:00Z"}[field]
        retained.decisions[variables["id"]] = row
    session.before_review_insert = raced
    repo = SqlConnectRepository(session=session, graph_blobs=blobs)
    result = project(repo, value)
    assert result == ProjectionResult(False, "AppendReviewDecisionV2")
    assert session.saw_conflict and session.proof_queries == 2
    assert "review_decision_provenance_invalid" in caplog.text
    assert max(retained.snapshots) == 2 and retained.snapshots[2]["sha256"] == digest(retained.snapshots[2]["snapshot"])


@pytest.mark.parametrize("observation", ["missing", "unobservable"])
def test_post_conflict_missing_or_unobservable_row_stays_incomplete(tmp_path, observation):
    _, retained, blobs, value = failed_original(tmp_path)
    session = RaceSession(retained)
    session.before_review_insert = lambda variables: retained.decisions.update({variables["id"]: row_from(variables)})
    session.conflict_read = observation
    assert project(SqlConnectRepository(session=session, graph_blobs=blobs), value) == ProjectionResult(False, "AppendReviewDecisionV2")
    assert session.saw_conflict and session.proof_queries == 2


def test_genuine_original_row_winning_pk_race_is_verified(tmp_path):
    _, retained, blobs, value = failed_original(tmp_path)
    retained.active.remove("A")
    session = RaceSession(retained)
    session.before_review_insert = lambda variables: retained.decisions.update({variables["id"]: row_from(variables)})
    assert project(SqlConnectRepository(session=session, graph_blobs=blobs), value) == ProjectionResult(True)
    assert session.saw_conflict and session.proof_queries == 2
    assert retained.decisions[value.audit[0].id]["createdAt"] == ORIGINAL_TIME


def test_same_process_replay_cannot_skip_changed_row_after_proof_read(tmp_path):
    _, retained, blobs, value = failed_original(tmp_path)
    session = RaceSession(retained)
    repo = SqlConnectRepository(session=session, graph_blobs=blobs)
    assert project(repo, value) == ProjectionResult(True)
    before = len(retained.calls)
    def raced(variables):
        bad = deepcopy(retained.decisions[variables["decisionId"]])
        bad["actorUid"] = "B"
        retained.decisions[variables["decisionId"]] = bad
    session.after_proof_observation = raced
    assert project(repo, value) == ProjectionResult(False, "AppendReviewDecisionV2")
    after = retained.calls[before:]
    assert sum(op == "AppendReviewDecisionV2" for op, _ in after) == 1
    assert sum(op == "GetReviewSaveProofV1" for op, _ in after) == 2
    assert not any(op in {"SaveSpecimenV3", "CreateSpecimenV3"} for op, _ in after)


def test_same_process_genuine_replay_rechecks_without_duplicate_decision(tmp_path):
    _, retained, blobs, value = failed_original(tmp_path)
    session = RaceSession(retained)
    repo = SqlConnectRepository(session=session, graph_blobs=blobs)
    assert project(repo, value) == ProjectionResult(True)
    original = deepcopy(retained.decisions)
    before = len(retained.calls)
    assert project(repo, value) == ProjectionResult(True)
    assert retained.decisions == original
    after = retained.calls[before:]
    assert sum(op == "AppendReviewDecisionV2" for op, _ in after) == 1
    assert sum(op == "GetReviewSaveProofV1" for op, _ in after) == 2


@pytest.mark.parametrize("total_reads,complete", [(49, True), (50, True), (51, False)])
def test_actual_writer_conflict_read_obeys_total_pass_boundary(tmp_path, total_reads, complete):
    blobs = LocalBlobs(tmp_path / "legacy-race")
    current = specimen(blobs)
    current.version = total_reads - 2
    event = AuditEvent(actor="A", action="review_field", reason="legacy", created_at=ORIGINAL_TIME)
    current.audit = [event]
    retained = CanonicalSession()
    for revision in range(1, current.version + 1):
        version = current.model_copy(deep=True)
        version.version = revision
        if revision < current.version:
            version.audit = []
        payload = version.model_dump(mode="json")
        retained.snapshots[revision] = {"revision": revision, "snapshot": payload,
                                         "sha256": digest(payload), "contractVersion": "0.1"}
    retained.audit = [{"id": str(uuid4()), "organizationId": current.scope.organization_id,
                       "collectionId": current.scope.collection_id, "specimenId": current.id,
                       "actorUid": "A", "revision": current.version, "action": "checkpoint_or_review"}]
    retained.decisions[event.id] = {"id": event.id, "specimenId": current.id, "actorUid": "A",
                                   "baseRevision": current.version - 1, "resultingRevision": current.version,
                                   "reason": event.reason, "correction": {"action": event.action, "before": {}, "after": {}},
                                   "createdAt": ORIGINAL_TIME}
    repo = SqlConnectRepository(session=retained, graph_blobs=blobs)
    result = project(repo, current)
    assert result == (ProjectionResult(True) if complete else ProjectionResult(False, "AppendReviewDecisionV2"))
    observations = [op for op, _ in retained.calls if op in {"GetSnapshot", "GetReviewSaveProofV1"}]
    assert len(observations) == min(total_reads, 50)
