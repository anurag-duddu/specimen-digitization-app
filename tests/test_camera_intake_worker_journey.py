"""Camera admission through the dispatched worker into the real review query.

This is a composed, offline contract test, not physical-device or production
acceptance. The API, worker, workflow and queue query are real; cloud dispatch,
provider responses and time are controlled. An explicit user Retry start is
also exercised after a failed dispatch. No administrator reconciliation,
direct workflow stepping or forced disposition makes the record reach the queue.
"""

import hashlib
import io
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from specimen_digitization.application.api import (
    SYNTHETIC_COLLECTION,
    SYNTHETIC_ORG,
    create_app,
)
from specimen_digitization.application.collection_profiles import published_registry
from specimen_digitization.application.domain import Disposition
from specimen_digitization.application.lane_dispatch import DispatchOutcome
from specimen_digitization.application.lane_worker import DrainWorker
from specimen_digitization.application.profile_runtime import published_risk_registry
from specimen_digitization.application.storage import LocalBlobs
from specimen_digitization.research_harness.persistence import DurabilityScope, SqliteStateBackend
from specimen_digitization.research_harness.program_budget import (
    research_liability_micros,
    reserve_ordinary_liability,
    settle_ordinary_liability,
)

from test_application import HEADERS, PREFIX
from test_lane_costs import seed_synthetic_ledger
from test_lane_drain import Clock, NonSensitiveMember
from test_lane_profile import USER
from test_lane_routes import FIRST_PASS_RESERVATION, SCOPE
from test_rate_limit_refusal import FAILURE, ChildLab, requests


class SubmittedExecutions:
    """Only the ordinary API/worker dispatch paths can request an execution."""

    def __init__(self, *, fail_first=False):
        self.requested = 0
        self.calls = 0
        self.fail_first = fail_first

    def start(self):
        self.calls += 1
        if self.fail_first and self.calls == 1:
            return DispatchOutcome(status="failed", reason="http_503")
        self.requested += 1
        return DispatchOutcome(status="requested")

    def run(self, workflow, members, clock):
        executed = 0
        while executed < self.requested:
            assert executed < 3, "Worker unexpectedly kept dispatching itself"
            executed += 1
            result = DrainWorker(
                workflow.repository,
                workflow,
                USER,
                members,
                execution_id=f"camera-execution-{executed}",
                clock=clock,
                sleep=clock.sleep,
                continuation=self.start,
            ).run()
            assert result["status"] == "drained", result
        assert executed > 0, "Intake did not dispatch the normal worker"


def camera_photo(orientation):
    output = io.BytesIO()
    image = Image.new("RGB", (120, 80), "white")
    exif = Image.Exif()
    exif[274] = orientation
    image.save(output, format="JPEG", exif=exif)
    return output.getvalue()


def submit_photo(client, data):
    batch = client.post(
        PREFIX + "/batches",
        headers=dict(HEADERS, **{"Idempotency-Key": "camera-batch"}),
        json={"collection_id": SYNTHETIC_COLLECTION, "display_name": "Camera", "sensitive": False},
    )
    assert batch.status_code == 200, batch.text
    item = client.post(
        PREFIX + f"/batches/{batch.json()['batch_id']}/items",
        headers=dict(HEADERS, **{"Idempotency-Key": "camera-item"}),
        json={
            "client_item_id": "photo-one",
            "filename": "camera.jpg",
            "media_type": "image/jpeg",
            "size_bytes": len(data),
            "width": 120,
            "height": 80,
            "sha256": hashlib.sha256(data).hexdigest(),
            "sensitive": False,
        },
    )
    assert item.status_code == 200, item.text
    upload = item.json()["upload_id"]
    content = client.put(PREFIX + f"/uploads/{upload}/content", headers=HEADERS, content=data)
    assert content.status_code == 200, content.text
    revision = content.json()["revision"]

    def complete():
        return client.post(
            PREFIX + f"/uploads/{upload}/complete",
            headers=dict(HEADERS, **{"Idempotency-Key": "camera-complete"}),
            json={"expected_revision": revision},
        )

    done = complete()
    assert done.status_code == 200, done.text
    return done.json(), complete


@pytest.mark.parametrize(("orientation", "failed_start"), [(1, False), (6, False), (8, True)])
def test_camera_photo_recovers_a_503_and_enters_review_without_administrator_recovery(
    tmp_path, monkeypatch, orientation, failed_start
):
    monkeypatch.setenv("SPECIMEN_APPROVED_INFERENCE", "true")
    monkeypatch.setenv(FAILURE, "http_503")
    repository = NonSensitiveMember(tmp_path / "state.sqlite3")
    seed_synthetic_ledger(repository, reserved_total_micros=0)
    adapters = ChildLab(LocalBlobs(tmp_path / "blobs"), first_passes=1)
    dispatch = SubmittedExecutions(fail_first=failed_start)
    members = lambda user: [{
        "organization_id": SYNTHETIC_ORG,
        "collection_id": SYNTHETIC_COLLECTION,
        "role": "reviewer",
        "can_view_sensitive": True,
    }]
    app = create_app(
        mode="emulator",
        repository=repository,
        blobs=adapters.blobs,
        adapters=adapters,
        identity_verifier=lambda token, check: USER,
        memberships=members,
        profile_registry=published_registry({SYNTHETIC_COLLECTION: "insects"}),
        risk_registry=published_risk_registry(),
        worker_dispatcher=dispatch,
    )
    workflow = app.state.workflow
    backend = SqliteStateBackend(tmp_path / "research.sqlite3")
    backend.grant(
        DurabilityScope(SYNTHETIC_ORG, SYNTHETIC_COLLECTION, "any", "any", 1, USER, False),
        role="admin",
    )
    workflow.retained_cost = lambda p, s: research_liability_micros(repository, p, s, state_backend=backend)
    workflow.reserve_retained_cost = lambda p, s, step, cost: reserve_ordinary_liability(
        repository, p, s, step, cost, state_backend=backend
    )
    workflow.settle_retained_cost = lambda p, s, step: settle_ordinary_liability(
        repository, p, s, step, state_backend=backend
    )
    client = TestClient(app)
    data = camera_photo(orientation)
    accepted, complete = submit_photo(client, data)
    ident = accepted["specimen_id"]
    assert accepted["status"] == "pending" and accepted["disposition"] is None
    assert dispatch.calls == 1
    assert dispatch.requested == (0 if failed_start else 1)

    def review_items():
        response = client.get(
            PREFIX + "/specimens",
            headers=HEADERS,
            params={"collection_id": SYNTHETIC_COLLECTION, "disposition": "needs_human_review"},
        )
        assert response.status_code == 200, response.text
        return response.json()["items"]

    # A detail route exists at upload time, but that is not queue acceptance.
    assert client.get(PREFIX + f"/specimens/{ident}", headers=HEADERS).status_code == 200
    assert review_items() == []
    if failed_start:
        # The explicit user Retry start uses the existing dispatch endpoint;
        # unlike reconciliation it does not alter any processing state.
        before = repository.get(SCOPE, ident)
        response = client.post(
            PREFIX + f"/specimens/{ident}/process",
            headers=dict(HEADERS, **{"Idempotency-Key": "camera-retry-start"}),
        )
        assert response.status_code == 202, response.text
        assert response.json()["dispatch"]["status"] == "requested"
        assert repository.get(SCOPE, ident) == before
        assert dispatch.requested == 1 and dispatch.calls == 2
    clock = Clock()
    clock.now = datetime.now(timezone.utc) + timedelta(seconds=2)
    workflow.clock = clock
    dispatch.run(workflow, members, clock)

    specimen = repository.get(SCOPE, ident)
    run = specimen.run
    assert (run.stage, run.disposition, run.blocker) == ("finalized", Disposition.REVIEW, None)
    assert [item["specimen_id"] for item in review_items()] == [ident]
    assert adapters.blobs.get(specimen.asset.blob_ref) == data
    assert specimen.asset.sha256 == hashlib.sha256(data).hexdigest()
    assert (specimen.asset.width, specimen.asset.height) == (120, 80)
    [first_pass] = [step for step in run.attempts if step.startswith("first_pass:")]
    assert run.attempts[first_pass] == 2
    assert run.attempts["segment"] == 1
    assert all(count == 1 for step, count in run.attempts.items() if step.startswith("transcribe:"))
    assert requests(tmp_path, "first_pass") == 1
    failed = next(call for call in run.paid_calls if call["step"] == first_pass)
    assert (failed["outcome"], failed["cost_basis"], failed["cost_micros"]) == (
        "failed", "reserved", FIRST_PASS_RESERVATION
    )
    assert not {"retry", "reconcile", "reprocess"} & {event.action for event in specimen.audit}
    # Repeating a successful upload completion returns its original receipt;
    # it neither creates another specimen nor starts the pipeline a second time.
    requested = dispatch.requested
    replay = complete()
    assert replay.status_code == 200 and replay.json() == accepted
    assert dispatch.requested == requested
    assert [item["specimen_id"] for item in review_items()] == [ident]
