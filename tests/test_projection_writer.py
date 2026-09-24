"""The projection writer in SqlConnectRepository (docs/execution/golive/DATA_CONTRACT.md 11)."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from specimen_digitization.application import production
from specimen_digitization.application.domain import Principal
from specimen_digitization.application.production import SqlConnectRepository, actor_uid
from specimen_digitization.application.storage import LocalBlobs, ProjectionResult, SQLiteRepository

from test_projection import pinned, read, specimen

ALREADY_WRITTEN = {
    "message": "violates SQL unique constraint: label_region_pkey",
    "extensions": {"code": "ALREADY_EXISTS"},
}
NATURAL_DUPLICATE = {
    "message": "violates SQL unique constraint: reading_comparison_pair",
    "extensions": {"code": "ALREADY_EXISTS"},
}
DENIED = {"message": "access denied (aborted)", "extensions": {"code": "PERMISSION_DENIED"}}


class Response:
    def __init__(self, body, status=200):
        self.status_code = status
        self.body = body

    def json(self):
        return self.body


class Session:
    """Records every connector call; `answer(operation)` returns a response or None for success."""

    def __init__(self, answer=lambda operation: None):
        self.calls = []
        self.answer = answer

    def post(self, url, json, timeout):
        operation = json["operationName"]
        self.calls.append((operation, json["variables"]))
        answer = self.answer(operation)
        if isinstance(answer, Response):
            return answer
        if operation == "GetReceipt":
            return Response({"data": {"requestReceipt": None}})
        return Response({"data": {}} if answer is None else {"errors": [answer]})


@pytest.fixture
def actor():
    token = actor_uid.set("worker-uid")
    yield "worker-uid"
    actor_uid.reset(token)


def repository(tmp_path, session):
    blobs = LocalBlobs(tmp_path / "blobs")
    return SqlConnectRepository(session=session, graph_blobs=blobs), blobs


def stored(blobs, s):
    """Put the raw responses the fixture's readings refer to, as the reader would."""
    for observation in s.run.observations:
        ref = blobs.put(b'{"reading": "%s"}' % observation.route_id.encode())
        observation.raw_ref, observation.raw_sha256 = ref, ref
    s.asset.blob_ref = blobs.put(b"original image bytes")
    return s


def projected(session):
    return [op for op, _ in session.calls if op not in {"GetReceipt", "CreateSpecimenV3", "SaveSpecimenV3"}]


def test_every_row_is_sent_once_in_order_with_scope_and_actor(tmp_path, actor):
    session = Session()
    repo, blobs = repository(tmp_path, session)
    s = stored(blobs, read(pinned(specimen())))
    repo.write_projection(s.scope, s)
    assert projected(session) == [
        "AppendSourceAssetV2",
        "AppendProfileVersionV2",
        "AppendPipelineRunV2",
        "AppendLabelRegionV2",
        "AppendSourceAssetV2",
        "AppendModelObservationV2",
        "AppendSourceAssetV2",
        "AppendModelObservationV2",
        "AppendReadingComparisonV1",
    ]
    for _, variables in session.calls:
        assert variables["organizationId"] == "org-1"
        assert variables["collectionId"] == "coll-1"
        assert variables["actorUid"] == "worker-uid"
    original = session.calls[0][1]
    assert (original["bucket"], original["generation"]) == ("local", "0")
    assert original["objectName"] == s.asset.blob_ref
    raw = session.calls[4][1]
    assert raw["byteSize"] == str(len(b'{"reading": "handwriting-muse"}'))
    session.calls.clear()
    repo.write_projection(s.scope, s)
    assert session.calls == []


def test_a_primary_key_conflict_counts_as_written(tmp_path, actor):
    session = Session(lambda op: ALREADY_WRITTEN if op == "AppendLabelRegionV2" else None)
    repo, blobs = repository(tmp_path, session)
    s = stored(blobs, read(pinned(specimen())))
    repo.write_projection(s.scope, s)
    assert projected(session)[-1] == "AppendReadingComparisonV1"
    session.calls.clear()
    repo.write_projection(s.scope, s)
    assert session.calls == []


@pytest.mark.parametrize(
    "failure", [NATURAL_DUPLICATE, DENIED, Response({}, 500)], ids=["natural-key", "denied", "unavailable"]
)
def test_a_failed_write_stops_the_pass_and_the_next_save_resumes_there(
    tmp_path, actor, caplog, failure
):
    failing = {"AppendModelObservationV2"}
    session = Session(lambda op: failure if op in failing else None)
    repo, blobs = repository(tmp_path, session)
    s = stored(blobs, read(pinned(specimen())))
    with caplog.at_level(logging.WARNING):
        repo.write_projection(s.scope, s)
    assert projected(session)[-1] == "AppendModelObservationV2"
    assert "AppendReadingComparisonV1" not in projected(session)
    assert any(
        s.id in record.getMessage() and "AppendModelObservationV2" in record.getMessage()
        for record in caplog.records
    )
    failing.clear()
    session.calls.clear()
    repo.write_projection(s.scope, s)
    assert projected(session) == [
        "AppendModelObservationV2",
        "AppendSourceAssetV2",
        "AppendModelObservationV2",
        "AppendReadingComparisonV1",
    ]


def test_a_save_succeeds_even_when_every_projection_write_fails(tmp_path, actor):
    session = Session(lambda op: DENIED if op.startswith(("Append", "Record")) else None)
    repo, blobs = repository(tmp_path, session)
    s = stored(blobs, specimen())
    principal = Principal(user_id="worker-uid", scope=s.scope, role="operator")
    saved = repo.create(principal, s, "ingest:1", "d" * 64)
    assert saved.id == s.id
    assert [op for op, _ in session.calls] == ["GetReceipt", "CreateSpecimenV3", "AppendSourceAssetV2"]


def test_sizes_are_read_once_per_blob(tmp_path, actor):
    session = Session()
    repo, blobs = repository(tmp_path, session)
    s = stored(blobs, read(pinned(specimen())))
    reads = []
    size = repo.blob_size
    repo.blob_size = lambda ref: reads.append(ref) or size(ref)
    repo.write_projection(s.scope, s)
    repo.write_projection(s.scope, s.model_copy(deep=True))
    assert len(reads) == len(set(reads)) == 2


def test_cloud_storage_refs_carry_bucket_object_and_generation(tmp_path, actor):
    bucket = SimpleNamespace(
        name="specimen-digitization.firebasestorage.app",
        get_blob=lambda name, generation: SimpleNamespace(size=77),
    )
    repo = SqlConnectRepository(session=Session(), graph_blobs=SimpleNamespace(bucket=bucket))
    sha = "e" * 64
    blob = repo.locate(f"{sha}:1700000000000009")
    assert blob.bucket == "specimen-digitization.firebasestorage.app"
    assert blob.object_name == f"application/sha256/{sha}"
    assert blob.generation == "1700000000000009"
    assert repo.blob_size(f"{sha}:1700000000000009") == 77


def test_a_pass_reports_whether_it_wrote_every_row(tmp_path, actor, monkeypatch):
    """After a run's final save the lane re-projects until a pass completes (coordinator ruling)."""
    failing = {"AppendModelObservationV2"}
    session = Session(lambda op: DENIED if op in failing else None)
    repo, blobs = repository(tmp_path, session)
    s = stored(blobs, read(pinned(specimen())))
    assert repo.write_projection(s.scope, s) == ProjectionResult(False, "AppendModelObservationV2")
    failing.clear()
    assert repo.write_projection(s.scope, s) == ProjectionResult(True)
    # A pass with nothing left to write is complete too.
    assert repo.write_projection(s.scope, s) == ProjectionResult(True)

    def uncomputable(*args, **kwargs):
        raise ValueError("no rows")

    monkeypatch.setattr(production, "writes", uncomputable)
    assert repo.write_projection(s.scope, s) == ProjectionResult(False, "not_computed")


def test_the_local_repository_has_nothing_to_project(tmp_path):
    """SQLiteRepository writes no normalized rows (section 11), so every pass is complete."""
    s = specimen()
    assert SQLiteRepository(tmp_path / "local.db").write_projection(s.scope, s) == ProjectionResult(True)
