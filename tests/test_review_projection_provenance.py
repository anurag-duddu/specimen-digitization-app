"""Original human decision provenance; synthetic connector, never native SQL proof."""

from copy import deepcopy
from uuid import uuid4

import pytest

from specimen_digitization.application.domain import AuditEvent, Asset, Principal, Profile, Run, Scope, Specimen
from specimen_digitization.application.production import SqlConnectRepository, actor_uid
from specimen_digitization.application.storage import (
    Conflict, LocalBlobs, ProjectionResult, ReviewProofReader, ReviewSnapshot,
    SQLiteRepository, digest,
)
from test_projection import PROFILE
from test_projection_writer import Response

ORIGINAL_TIME = "2020-01-02T03:04:05.123456+00:00"


def specimen(blobs):
    ref = blobs.put(b"synthetic original")
    run = Run(profile=Profile(id=PROFILE["id"], version=PROFILE["version"]))
    run.profile_snapshot = PROFILE
    run.profile_registry_version = "registry-1"
    run.dependencies = {"profile_snapshot_sha256": digest(PROFILE), "profile_registry_version": "registry-1"}
    return Specimen(
        scope=Scope(organization_id=str(uuid4()), collection_id=str(uuid4())),
        asset=Asset(sha256=ref, blob_ref=ref, media_type="image/png", size_bytes=18,
                    width=1, height=1, filename="synthetic.png", uploader="A", sensitive=False),
        run=run,
    )


class CanonicalSession:
    """Named-call fake retaining canonical CAS, receipts and atomic save-audit rows."""

    def __init__(self):
        self.snapshots = {}
        self.receipts = {}
        self.audit = []
        self.decisions = {}
        self.calls = []
        self.active = {"A", "B"}
        self.fail_projection = False

    def post(self, url, json, timeout):
        op, v = json["operationName"], deepcopy(json["variables"])
        self.calls.append((op, v))
        if v["actorUid"] not in self.active:
            return Response({}, status=403)
        if op == "GetReceipt":
            key = (v["actorUid"], v["operation"], v["idempotencyKey"])
            return Response({"data": {"requestReceipt": self.receipts.get(key)}})
        if op == "GetSnapshot":
            return Response({"data": {"specimenSnapshot": self.snapshots.get(v["revision"])}})
        if op in {"CreateSpecimenV3", "SaveSpecimenV3"}:
            expected = v.get("expectedRevision", 0)
            assert max(self.snapshots, default=0) == expected, "fake CAS rejected"
            revision = expected + 1
            self.snapshots[revision] = {"revision": revision, "snapshot": v["snapshot"],
                                        "sha256": v["snapshotSha256"], "contractVersion": "0.1"}
            self.receipts[v["actorUid"], v["operation"], v["idempotencyKey"]] = {
                "requestSha256": v["requestSha256"], "revision": revision, "specimenId": v["id"],
            }
            self.audit.append({"id": str(uuid4()), "organizationId": v["organizationId"],
                               "collectionId": v["collectionId"], "specimenId": v["id"],
                               "actorUid": v["actorUid"], "revision": revision,
                               "action": "create" if not expected else "checkpoint_or_review"})
            return Response({"data": {}})
        if op == "GetReviewSaveProofV1":
            matching = [row for row in self.audit if row["revision"] == v["resultingRevision"]
                        and row["actorUid"] == v["decisionActorUid"]
                        and row["action"] == "checkpoint_or_review"]
            return Response({"data": {"prior": self.snapshots.get(v["baseRevision"]),
                                      "target": self.snapshots.get(v["resultingRevision"]),
                                      "saveAudits": matching[:2],
                                      "decision": self.decisions.get(v["decisionId"])}})
        if op == "AppendReviewDecisionV2":
            if self.fail_projection:
                return Response({}, status=503)
            if v["id"] in self.decisions:
                return Response({"errors": [{"message": "review_decision_pkey", "extensions": {"code": "ALREADY_EXISTS"}}]})
            self.decisions[v["id"]] = {key: v[key] for key in (
                "id", "specimenId", "baseRevision", "resultingRevision", "reason", "correction", "createdAt"
            )}
            self.decisions[v["id"]]["actorUid"] = v["decisionActorUid"]
        return Response({"data": {}})


def save(repo, value, actor, key):
    principal = Principal(user_id=actor, scope=value.scope, role="reviewer")
    token = actor_uid.set(actor)
    try:
        return repo.save(principal, value, value.version, key, digest(key))
    finally:
        actor_uid.reset(token)


def failed_original(tmp_path):
    blobs = LocalBlobs(tmp_path / "blobs")
    session = CanonicalSession()
    repo = SqlConnectRepository(session=session, graph_blobs=blobs)
    initial = specimen(blobs)
    token = actor_uid.set("A")
    try:
        initial = repo.create(Principal(user_id="A", scope=initial.scope, role="reviewer"), initial, "create", digest("create"))
    finally:
        actor_uid.reset(token)
    initial.audit.append(AuditEvent(actor="A", action="review_field", reason="original label",
                                   after={"literal": "Cook"}, created_at=ORIGINAL_TIME))
    session.fail_projection = True
    retained = save(repo, initial, "A", "A-review")
    assert not session.decisions and retained.version == 2
    session.fail_projection = False
    return repo, session, blobs, retained


def test_cross_reviewer_catchup_preserves_original_author_revision_and_time(tmp_path):
    repo, session, blobs, original = failed_original(tmp_path)
    old_event = original.audit[-1].model_dump()
    session.active.remove("A")
    original.audit.append(AuditEvent(actor="B", action="review_field", reason="second label"))
    # Fresh process state, same immutable fake database; A is inactive.
    repo = SqlConnectRepository(session=session, graph_blobs=blobs)
    caught = save(repo, original, "B", "B-review")
    historical = session.decisions[old_event["id"]]
    assert (historical["actorUid"], historical["baseRevision"], historical["resultingRevision"], historical["createdAt"]) == ("A", 1, 2, ORIGINAL_TIME)
    assert caught.audit[0].model_dump() == old_event
    calls = [v for op, v in session.calls if op == "AppendReviewDecisionV2" and v["id"] == old_event["id"]]
    assert calls[-1]["actorUid"] == "B" and calls[-1]["decisionActorUid"] == "A"
    again = save(SqlConnectRepository(session=session, graph_blobs=blobs), caught, "B", "B-review")
    assert again == caught and len(session.decisions) == 2


def test_compacted_original_event_is_caught_up_by_later_reviewer(tmp_path):
    repo, session, blobs, original = failed_original(tmp_path)
    original_id = original.audit[0].id
    original.audit.append(AuditEvent(actor="B", action="worker_note", reason="x" * (130 * 1024)))
    session.fail_projection = True
    compacted = save(repo, original, "B", "compact")
    assert compacted.audit_offset == 1 and all(event.id != original_id for event in compacted.audit)
    assert original_id not in session.decisions
    session.fail_projection = False
    repo = SqlConnectRepository(session=session, graph_blobs=blobs)
    token = actor_uid.set("B")
    try:
        assert repo.write_projection(compacted.scope, compacted, reviewer=True) == ProjectionResult(True)
    finally:
        actor_uid.reset(token)
    assert session.decisions[original_id]["createdAt"] == ORIGINAL_TIME


@pytest.mark.parametrize("damage", ["missing_prior", "missing_target", "duplicate_save_audit", "wrong_save_actor", "wrong_V1_actor", "wrong_V1_time", "wrong_V1_correction", "bad_digest", "missing_original_time", "cross_scope"])
def test_invalid_original_proof_causes_no_normalized_mutation(tmp_path, damage):
    repo, session, blobs, value = failed_original(tmp_path)
    if damage == "missing_prior":
        session.snapshots.pop(1)
    elif damage == "missing_target":
        session.snapshots.pop(2)
    elif damage == "duplicate_save_audit":
        session.audit.append(deepcopy(session.audit[-1]))
    elif damage == "wrong_save_actor":
        session.audit[-1]["actorUid"] = "B"
    elif damage == "bad_digest":
        session.snapshots[2]["sha256"] = "e" * 64
    elif damage in {"missing_original_time", "cross_scope"}:
        raw = session.snapshots[2]["snapshot"]
        if damage == "missing_original_time":
            raw["audit"][0].pop("created_at")
        else:
            raw["scope"]["organization_id"] = str(uuid4())
        session.snapshots[2]["sha256"] = digest(raw)
    else:
        event = value.audit[0]
        session.decisions[event.id] = {"id": event.id, "specimenId": value.id, "actorUid": "A",
            "baseRevision": 1, "resultingRevision": 2, "reason": event.reason,
            "correction": {"action": event.action, "before": event.before, "after": event.after}, "createdAt": ORIGINAL_TIME}
        field = {"wrong_V1_actor": "actorUid", "wrong_V1_time": "createdAt", "wrong_V1_correction": "correction"}[damage]
        session.decisions[event.id][field] = {"wrong_V1_actor": "B", "wrong_V1_time": "2026-09-30T00:00:00Z", "wrong_V1_correction": {"invented": True}}[damage]
    start = len(session.calls)
    token = actor_uid.set("B")
    try:
        result = SqlConnectRepository(session=session, graph_blobs=blobs).write_projection(value.scope, value, reviewer=True)
    finally:
        actor_uid.reset(token)
    assert result == ProjectionResult(False, "not_computed")
    assert not any(op.startswith(("Append", "Register", "Record")) for op, _ in session.calls[start:])


@pytest.mark.parametrize("distinct_reads", [49, 50, 51])
def test_legacy_first_appearance_read_boundary_and_cache(tmp_path, distinct_reads):
    blobs = LocalBlobs(tmp_path / "legacy")
    current = specimen(blobs)
    current.version = distinct_reads - 1
    event = AuditEvent(actor="A", action="review_field", reason="legacy", created_at=ORIGINAL_TIME)
    current.audit = [event]
    calls = []
    def snapshot(revision):
        calls.append(("snapshot", revision))
        value = current.model_copy(deep=True)
        value.version = revision
        if revision < current.version:
            value.audit = []
        payload = value.model_dump(mode="json")
        return ReviewSnapshot(payload, digest(payload), value)
    def audit(base, result, original, prior, target):
        calls.append(("proof", result))
        return {"saveAudits": [{"id": str(uuid4()), "organizationId": current.scope.organization_id,
                "collectionId": current.scope.collection_id, "specimenId": current.id,
                "actorUid": "A", "revision": result, "action": "checkpoint_or_review"}]}
    reader = ReviewProofReader(current, snapshot, audit)
    if distinct_reads <= 50:
        proofs = reader.prove()
        assert len(proofs) == 1 and proofs[0].resulting_revision == current.version
    else:
        with pytest.raises(ValueError, match="^review_decision_provenance_invalid$"):
            reader.prove()
    assert len(calls) == min(distinct_reads, 50)
    assert len(set(calls)) == len(calls)


@pytest.mark.parametrize("damage", ["wrong_actor", "wrong_revision", "old_event_edit", "duplicate_id"])
def test_durable_local_stamp_rejects_forgery_before_commit(tmp_path, damage):
    repo = SQLiteRepository(tmp_path / "records.db")
    value = specimen(repo.graph_blobs)
    principal = Principal(user_id="A", scope=value.scope, role="reviewer")
    value = repo.create(principal, value, "create", digest("create"))
    value.audit.append(AuditEvent(actor="A", action="review_field", reason="original", created_at=ORIGINAL_TIME))
    value = repo.save(principal, value, 1, "first", digest("first"))
    original = value.audit[0].model_dump()
    if damage == "old_event_edit":
        value.audit[0].created_at = "2026-09-30T00:00:00Z"
    else:
        event = AuditEvent(actor="B" if damage == "wrong_actor" else "A", action="review_field", reason="new")
        if damage == "wrong_revision":
            event.base_revision = 1
        if damage == "duplicate_id":
            event.id = value.audit[0].id
        value.audit.append(event)
    with pytest.raises(Conflict, match="^review_decision_provenance_invalid$"):
        repo.save(principal, value, 2, "forged", digest("forged"))
    restarted = SQLiteRepository(tmp_path / "records.db")
    restored = restarted.get(principal.scope, value.id)
    assert restored.version == 2 and restored.audit[0].model_dump() == original
    assert (original["base_revision"], original["resulting_revision"], original["created_at"]) == (1, 2, ORIGINAL_TIME)


@pytest.mark.parametrize("route,action", [("decisions", "review_field"), ("regions", "review_regions"), ("classification", "review_classification")])
def test_three_actual_http_review_routes_stamp_original_save_and_restart(tmp_path, route, action):
    from specimen_digitization.application.domain import Scope
    from test_application import client, intake, HEADERS, PREFIX, SYNTHETIC_ORG, SYNTHETIC_COLLECTION

    c = client(tmp_path)
    ident = intake(c)["specimen_id"]
    scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
    path = PREFIX + "/specimens/" + ident
    processed = c.post(path + "/process", headers=HEADERS)
    assert processed.status_code == 200, processed.text
    repo = SQLiteRepository(tmp_path / "state.sqlite3")
    before = repo.get(scope, ident)
    body = {"expected_revision": before.version, "reason": "synthetic original-save proof"}
    if route == "decisions":
        body.update(kind="field", target_id="county", after={"state": "unknown", "reason": "label uncertainty"},
                    base_record_version_id=f"{before.run.id}:{before.version}")
    elif route == "regions":
        body.update(base_run_id=before.run.id, regions=[region.model_dump() for region in before.run.regions])
    else:
        body.update(collection_id=SYNTHETIC_COLLECTION, profile_collection_id="insects")
    response = c.post(path + "/" + route, headers=dict(HEADERS, **{"Idempotency-Key": route}), json=body)
    assert response.status_code == 200, response.text
    original = repo.version(scope, ident, before.version + 1)
    event = next(event for event in original.audit if event.action == action)
    assert event.actor == "synthetic-reviewer"
    assert (event.base_revision, event.resulting_revision) == (before.version, before.version + 1)
    assert event.id not in {old.id for old in before.audit}
    original_bytes = event.model_dump()
    c.close()
    restarted = client(tmp_path)
    assert restarted.get(path + "/workspace", headers=HEADERS).status_code == 200
    retained = SQLiteRepository(tmp_path / "state.sqlite3").version(scope, ident, before.version + 1)
    assert next(event for event in retained.audit if event.id == original_bytes["id"]).model_dump() == original_bytes
