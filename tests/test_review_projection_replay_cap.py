"""Unrun source control: actual typed repository, synthetic connector, no SQL claim."""

from copy import deepcopy

from specimen_digitization.application.domain import AuditEvent, Principal
from specimen_digitization.application.production import SqlConnectRepository, actor_uid
from specimen_digitization.application.storage import LocalBlobs, ProjectionResult, digest
from test_review_projection_provenance import CanonicalSession, ORIGINAL_TIME, save, specimen
from test_review_projection_race import project


class RetainedRowsSession(CanonicalSession):
    """Observe successful named-call rows without changing proof/read behavior."""

    def __init__(self):
        super().__init__()
        self.normalized = {}
        self.review_conflicts = []

    def post(self, url, json, timeout):
        response = super().post(url, json, timeout)
        operation, variables = json["operationName"], json["variables"]
        if operation == "AppendReviewDecisionV2" and response.body.get("errors"):
            assert response.body["errors"][0]["extensions"]["code"] == "ALREADY_EXISTS"
            self.review_conflicts.append(variables["id"])
        if operation.startswith(("Append", "Register", "Record")) and response.status_code == 200 and not response.body.get("errors"):
            key = (operation, variables.get("id", digest(variables)))
            self.normalized[key] = deepcopy(variables)
        return response


class ObservedRepository(SqlConnectRepository):
    """Retain the result of the real projection called by canonical create/save."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.projection_results = []

    def write_projection(self, scope, value, reviewer=False):
        result = super().write_projection(scope, value, reviewer)
        self.projection_results.append(result)
        return result


def proof_reads(calls):
    return [(operation, variables) for operation, variables in calls
            if operation in {"GetSnapshot", "GetReviewSaveProofV1"}]


def test_actual_25_event_save_completes_but_same_process_replay_hits_50_read_cap(tmp_path):
    blobs = LocalBlobs(tmp_path / "blobs")
    session = RetainedRowsSession()
    repo = ObservedRepository(session=session, graph_blobs=blobs)
    initial = specimen(blobs)
    principal = Principal(user_id="A", scope=initial.scope, role="reviewer")
    token = actor_uid.set("A")
    try:
        initial = repo.create(principal, initial, "create", digest("create"))
    finally:
        actor_uid.reset(token)
    assert initial.version == 1 and session.decisions == {}
    assert repo.projection_results == [ProjectionResult(True)]

    # All events originate before the actual authorized save. Its shared stamp
    # and canonical pack create revision2; no snapshots or rows are fabricated.
    initial.audit.extend(
        AuditEvent(actor="A", action="review_field", reason=f"original label {index}",
                   before={"literal": None}, after={"literal": str(index)},
                   created_at=ORIGINAL_TIME)
        for index in range(25)
    )
    before_save = len(session.calls)
    current = save(repo, initial, "A", "25-original-reviews")
    assert current.version == 2 and len(current.audit) == 25
    assert repo.projection_results[-1] == ProjectionResult(True)
    assert set(session.snapshots) == {1, 2} and len(session.decisions) == 25
    assert session.review_conflicts == []
    for event in current.audit:
        assert (event.actor, event.base_revision, event.resulting_revision, event.created_at) == ("A", 1, 2, ORIGINAL_TIME)
        row = session.decisions[event.id]
        assert (row["actorUid"], row["baseRevision"], row["resultingRevision"], row["createdAt"]) == ("A", 1, 2, ORIGINAL_TIME)
        assert row["correction"] == {"action": event.action, "before": event.before, "after": event.after}

    first = session.calls[before_save:]
    canonical = [index for index, (operation, _) in enumerate(first) if operation == "SaveSpecimenV3"]
    assert len(canonical) == 1
    first_projection = first[canonical[0] + 1:]
    first_reads = proof_reads(first_projection)
    assert len(first_reads) == 27
    assert sum(operation == "GetSnapshot" for operation, _ in first_reads) == 2
    assert sum(operation == "GetReviewSaveProofV1" for operation, _ in first_reads) == 25
    assert sum(operation == "AppendReviewDecisionV2" for operation, _ in first_projection) == 25

    retained = deepcopy((session.snapshots, session.receipts, session.audit, session.decisions, session.normalized))
    current_bytes = current.model_dump(mode="json")
    before_replay = len(session.calls)
    # Existing helper establishes B's current verified actor context. Original A
    # remains the historical decision author; same repository keeps its cache.
    assert project(repo, current) == ProjectionResult(False, "AppendReviewDecisionV2")
    replay = session.calls[before_replay:]
    reads = proof_reads(replay)
    assert len(reads) == 50  # 2 snapshots +25 proofs +23 fresh conflict reads.
    assert sum(operation == "GetSnapshot" for operation, _ in reads) == 2
    assert sum(operation == "GetReviewSaveProofV1" for operation, _ in reads) == 48
    attempted = [variables for operation, variables in replay if operation == "AppendReviewDecisionV2"]
    event_ids = [event.id for event in current.audit]
    observed_proofs = [variables["decisionId"] for operation, variables in reads
                       if operation == "GetReviewSaveProofV1"]
    assert observed_proofs == event_ids + event_ids[:23]
    assert [variables["id"] for variables in attempted] == event_ids[:24]
    assert session.review_conflicts == event_ids[:24]
    assert all(variables["actorUid"] == "B" and variables["decisionActorUid"] == "A" for variables in attempted)
    assert attempted[-1]["id"] == event_ids[23]
    assert not any(operation in {"CreateSpecimenV3", "SaveSpecimenV3", "AppendReviewDecisionV1"} for operation, _ in replay)
    assert not any(operation.startswith(("Append", "Register", "Record")) and operation != "AppendReviewDecisionV2" for operation, _ in replay)
    assert (session.snapshots, session.receipts, session.audit, session.decisions, session.normalized) == retained
    assert current.model_dump(mode="json") == current_bytes
    assert all(row["sha256"] == digest(row["snapshot"]) for row in session.snapshots.values())
