"""On-demand processing outside synthetic mode (docs/execution/golive/LANE.md, T1)."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from specimen_digitization.application.api import (
    SYNTHETIC_COLLECTION,
    SYNTHETIC_ORG,
    SYNTHETIC_TEXT,
    create_app,
)
from specimen_digitization.application.collection_profiles import (
    CollectionNode,
    CollectionProfile,
    CollectionProfileRegistry,
    ProcessingPolicy,
    ProfileMapping,
)
from specimen_digitization.application.domain import (
    MANDATORY,
    Asset,
    Principal,
    Profile,
    Run,
    Scope,
    Specimen,
    StageCostReservations,
)
from specimen_digitization.application.lane import run_status
from specimen_digitization.application.lane_dispatch import DispatchOutcome
from specimen_digitization.application.storage import (
    LocalBlobs,
    SQLiteRepository,
    work_available_at,
)
from specimen_digitization.application.workflow import SyntheticAdapters

from test_application import HEADERS, PREFIX, image_bytes

SCOPE = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
USER = "lane-reviewer"
STAGE_COSTS = StageCostReservations(
    version="stage-cost-reservations-v1",
    cost_micros={
        "segment": 5_000,
        "transcribe:handwriting-qwen": 2_000,
        "transcribe:handwriting-muse": 2_000,
    },
)


class RecordingDispatcher:
    def __init__(self, status="requested"):
        self.status = status
        self.calls = 0

    def start(self):
        self.calls += 1
        return DispatchOutcome(
            status=self.status,
            reason=None if self.status == "requested" else "http_503",
        )


def registry(*, processing=True):
    profile = CollectionProfile(
        id="zoology_insects_lane_test",
        version="test-1",
        collection_id=SYNTHETIC_COLLECTION,
        state="active",
        schema_version="insects-v1",
        mandatory_fields=MANDATORY,
        prompt_set="fmnh_insects_transcription_v1",
        model_routes=("handwriting-qwen", "handwriting-muse"),
        segmentation_policy="sam3-v1",
        tools=("taxonomy_verifier",),
        data_sources=("gbif-col-xr",),
        validators=("insects-rules-v1",),
        scoring_policy="insects-review-risk-v1",
        clearance_policy="insects-clearance-v1",
        processing=ProcessingPolicy(
            run_cost_limit_micros=250_000, stage_cost_micros=STAGE_COSTS
        )
        if processing
        else None,
    )
    return CollectionProfileRegistry(
        version="lane-test-registry",
        nodes=(CollectionNode(id=SYNTHETIC_COLLECTION, name="Insects"),),
        profiles=(profile,),
        mappings=(
            ProfileMapping(
                collection_id=SYNTHETIC_COLLECTION,
                profile_id=profile.id,
                profile_version=profile.version,
            ),
        ),
    )


def lane_client(root, *, dispatcher=None, profiles=None):
    blobs = LocalBlobs(root / "blobs")
    app = create_app(
        mode="emulator",
        repository=SQLiteRepository(root / "state.sqlite3"),
        blobs=blobs,
        adapters=SyntheticAdapters(blobs, SYNTHETIC_TEXT),
        identity_verifier=lambda token, check: USER,
        memberships=lambda user: [
            {
                "organization_id": SYNTHETIC_ORG,
                "collection_id": SYNTHETIC_COLLECTION,
                "role": "reviewer",
                "can_view_sensitive": True,
            }
        ],
        profile_registry=profiles or registry(),
        worker_dispatcher=dispatcher,
    )
    return TestClient(app, raise_server_exceptions=False)


def intake(client, sensitive=False):
    """Upload one image into a batch with an explicit sensitivity declaration."""
    import hashlib

    batch = client.post(
        PREFIX + "/batches",
        headers=dict(HEADERS, **{"Idempotency-Key": "lane-batch"}),
        json={
            "collection_id": SYNTHETIC_COLLECTION,
            "display_name": "Lane",
            "sensitive": sensitive,
        },
    )
    assert batch.status_code == 200, batch.text
    data = image_bytes()
    item = client.post(
        PREFIX + f"/batches/{batch.json()['batch_id']}/items",
        headers=dict(HEADERS, **{"Idempotency-Key": "lane-item"}),
        json={
            "client_item_id": "one",
            "filename": "slide.png",
            "media_type": "image/png",
            "size_bytes": len(data),
            "width": 120,
            "height": 80,
            "sha256": hashlib.sha256(data).hexdigest(),
            "sensitive": sensitive,
        },
    )
    assert item.status_code == 200, item.text
    upload = item.json()["upload_id"]
    content = client.put(
        PREFIX + f"/uploads/{upload}/content", headers=HEADERS, content=data
    )
    assert content.status_code == 200, content.text
    done = client.post(
        PREFIX + f"/uploads/{upload}/complete",
        headers=dict(HEADERS, **{"Idempotency-Key": "lane-complete"}),
        json={"expected_revision": content.json()["revision"]},
    )
    assert done.status_code == 200, done.text
    return done.json()


def stored(root, specimen_id):
    return SQLiteRepository(root / "state.sqlite3").get(SCOPE, specimen_id)


def force_stage(root, specimen_id, stage):
    repository = SQLiteRepository(root / "state.sqlite3")
    specimen = repository.get(SCOPE, specimen_id)
    specimen.run.stage = stage
    repository.save(
        Principal(user_id=USER, scope=SCOPE, role="reviewer"),
        specimen,
        specimen.version,
        "force-" + stage,
        stage,
    )


def due_ids(root):
    cutoff = datetime.now(timezone.utc).isoformat()
    page = SQLiteRepository(root / "state.sqlite3").due_page(SCOPE, cutoff)
    return [item.specimen_id for item in page.items]


def process(client, specimen_id, key="process-1"):
    return client.post(
        PREFIX + f"/specimens/{specimen_id}/process",
        headers=dict(HEADERS, **{"Idempotency-Key": key}),
    )


def action(client, specimen_id, name, key):
    detail = client.get(PREFIX + f"/specimens/{specimen_id}", headers=HEADERS).json()
    return client.post(
        PREFIX + f"/runs/{detail['active_run_id']}/actions",
        headers=dict(HEADERS, **{"Idempotency-Key": key}),
        json={
            "expected_revision": detail["revision"],
            "action": name,
            "reason": "Lane test " + name,
        },
    )


def test_every_upload_is_queued_with_its_budget_and_intake_selection(tmp_path):
    dispatcher = RecordingDispatcher()
    row = intake(lane_client(tmp_path, dispatcher=dispatcher))
    assert row["status"] == "pending"
    assert row["stage"] == "pending"
    assert dispatcher.calls == 1
    run = stored(tmp_path, row["specimen_id"]).run
    assert run.queued_at is not None
    assert run.profile.execution.approved_cost_limit_micros == 250_000
    assert run.profile.execution.stage_cost_reservations == STAGE_COSTS
    assert run.classification_selection == {
        "collection_id": SYNTHETIC_COLLECTION,
        "actor_id": USER,
        "reason": "Intake collection",
    }
    assert due_ids(tmp_path) == [row["specimen_id"]]


def test_sensitive_records_are_never_queued(tmp_path):
    dispatcher = RecordingDispatcher()
    c = lane_client(tmp_path, dispatcher=dispatcher)
    row = intake(c, sensitive=True)
    assert row["status"] == "processing_blocked"
    assert row["blocker"] == "sensitive_record_not_processed"
    assert due_ids(tmp_path) == []
    assert dispatcher.calls == 0
    refused = process(c, row["specimen_id"])
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "sensitive_record_not_processed"
    retried = action(c, row["specimen_id"], "retry", "retry-sensitive")
    assert retried.status_code == 409, retried.text
    assert retried.json()["error"]["code"] == "sensitive_record_not_processed"
    assert dispatcher.calls == 0


def test_upload_without_an_allowance_is_blocked_with_the_reason(tmp_path):
    dispatcher = RecordingDispatcher()
    unconfigured = lane_client(
        tmp_path, dispatcher=dispatcher, profiles=registry(processing=False)
    )
    row = intake(unconfigured)
    assert row["status"] == "processing_blocked"
    assert row["blocker"] == "collection_processing_unconfigured"
    assert due_ids(tmp_path) == []
    assert dispatcher.calls == 0
    refused = action(unconfigured, row["specimen_id"], "retry", "retry-1")
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "collection_processing_unconfigured"
    retried = action(
        lane_client(tmp_path, dispatcher=dispatcher),
        row["specimen_id"],
        "retry",
        "retry-2",
    )
    assert retried.status_code == 200, retried.text
    assert retried.json()["status"] == "pending"
    assert dispatcher.calls == 1


def test_process_restarts_the_worker_for_a_queued_run_without_writing(tmp_path):
    dispatcher = RecordingDispatcher()
    c = lane_client(tmp_path, dispatcher=dispatcher)
    row = intake(c)
    response = process(c, row["specimen_id"])
    assert response.status_code == 202, response.text
    assert response.json()["status"] == "pending"
    assert response.json()["revision"] == row["revision"]
    assert response.json()["dispatch"] == {"status": "requested", "reason": None}
    assert dispatcher.calls == 2


def test_process_queues_a_run_that_was_never_requested(tmp_path):
    dispatcher = RecordingDispatcher()
    specimen = Specimen(
        scope=SCOPE,
        run=Run(profile=Profile(synthetic=False)),
        asset=asset(),
    )
    SQLiteRepository(tmp_path / "state.sqlite3").create(
        Principal(user_id=USER, scope=SCOPE, role="reviewer"),
        specimen,
        "legacy",
        "legacy",
    )
    c = lane_client(tmp_path, dispatcher=dispatcher)
    response = process(c, specimen.id)
    assert response.status_code == 202, response.text
    assert response.json()["status"] == "pending"
    run = stored(tmp_path, specimen.id).run
    assert run.profile.execution.approved_cost_limit_micros == 250_000
    assert run.classification_selection["actor_id"] == USER
    assert dispatcher.calls == 1


@pytest.mark.parametrize("stage", ["processing_blocked", "paused", "finalized"])
def test_process_leaves_blocked_paused_and_finished_runs_to_run_actions(
    tmp_path, stage
):
    dispatcher = RecordingDispatcher()
    c = lane_client(tmp_path, dispatcher=dispatcher)
    row = intake(c)
    force_stage(tmp_path, row["specimen_id"], stage)
    response = process(c, row["specimen_id"])
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "run_action_required"
    assert dispatcher.calls == 1


def test_failed_worker_start_keeps_the_request_queued(tmp_path):
    dispatcher = RecordingDispatcher(status="failed")
    c = lane_client(tmp_path, dispatcher=dispatcher)
    row = intake(c)
    response = process(c, row["specimen_id"])
    assert response.status_code == 202, response.text
    assert response.json()["dispatch"] == {"status": "failed", "reason": "http_503"}
    assert stored(tmp_path, row["specimen_id"]).run.stage == "pending"
    assert due_ids(tmp_path) == [row["specimen_id"]]


def test_no_configured_job_reports_unconfigured(tmp_path):
    c = lane_client(tmp_path, dispatcher=None)
    row = intake(c)
    response = process(c, row["specimen_id"])
    assert response.status_code == 202, response.text
    assert response.json()["dispatch"]["status"] == "unconfigured"
    assert stored(tmp_path, row["specimen_id"]).run.stage == "pending"


def test_run_actions_queue_the_run_and_start_the_worker(tmp_path):
    dispatcher = RecordingDispatcher()
    c = lane_client(tmp_path, dispatcher=dispatcher)
    row = intake(c)
    paused = action(c, row["specimen_id"], "pause", "pause-1")
    assert paused.status_code == 200, paused.text
    assert paused.json()["status"] == "paused"
    assert dispatcher.calls == 1
    resumed = action(c, row["specimen_id"], "resume", "resume-1")
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["status"] == "pending"
    assert dispatcher.calls == 2
    old_run = stored(tmp_path, row["specimen_id"]).run.id
    again = action(c, row["specimen_id"], "reprocess", "reprocess-1")
    assert again.status_code == 200, again.text
    assert again.json()["status"] == "pending"
    assert dispatcher.calls == 3
    run = stored(tmp_path, row["specimen_id"]).run
    assert run.id != old_run
    assert run.profile.execution.approved_cost_limit_micros == 250_000


def test_listing_filters_and_reports_the_waiting_state(tmp_path):
    c = lane_client(tmp_path, dispatcher=RecordingDispatcher())
    row = intake(c)

    def listed(state):
        response = c.get(
            PREFIX + "/specimens",
            params={"collection_id": SYNTHETIC_COLLECTION, "state": state},
            headers=HEADERS,
        )
        assert response.status_code == 200, response.text
        return [(i["specimen_id"], i["status"]) for i in response.json()["items"]]

    assert listed("pending") == [(row["specimen_id"], "pending")]
    assert listed("running") == []
    force_stage(tmp_path, row["specimen_id"], "segment")
    assert listed("pending") == []
    assert listed("running") == [(row["specimen_id"], "running")]


def test_status_and_due_rules():
    run = Run(profile=Profile(synthetic=False))
    assert run_status(run) == "running"
    assert work_available_at(specimen_with(run)) is not None
    run.stage = "pending"
    run.queued_at = "2026-09-23T12:00:00+00:00"
    assert run_status(run) == "pending"
    assert work_available_at(specimen_with(run)) == "2026-09-23T12:00:00+00:00"
    run.stage = "segment"
    assert run_status(run) == "running"
    run.stage = "processing_blocked"
    assert run_status(run) == "processing_blocked"
    assert work_available_at(specimen_with(run)) is None
    run.disposition = "needs_human_review"
    assert run_status(run) == "completed"


def test_never_queued_runs_serialize_as_before():
    assert "queued_at" not in Run().model_dump()
    queued = Run(queued_at="2026-09-23T12:00:00+00:00")
    assert Run.model_validate(queued.model_dump()).queued_at == queued.queued_at


def test_profiles_without_an_allowance_keep_their_digest():
    plain = registry(processing=False).profiles[0]
    assert "processing" not in plain.model_dump()
    with_policy = registry().profiles[0]
    assert with_policy.digest != plain.digest
    assert CollectionProfile.model_validate(with_policy.model_dump()) == with_policy


@pytest.mark.parametrize("stage", ["ingested", "pending"])
def test_sql_connect_rows_carry_the_lane_state(monkeypatch, stage):
    from types import SimpleNamespace

    from specimen_digitization.application.production import (
        SqlConnectRepository,
        actor_uid,
    )

    monkeypatch.delenv("SPECIMEN_SQL_EMULATOR_HOST", raising=False)
    calls = []

    class Session:
        def post(self, url, **kwargs):
            calls.append(kwargs["json"])
            return SimpleNamespace(status_code=200, json=lambda: {"data": {}})

    run = Run(profile=Profile(synthetic=False), stage=stage)
    if stage == "pending":
        run.queued_at = "2026-09-23T12:00:00+00:00"
    token = actor_uid.set(USER)
    try:
        SqlConnectRepository(session=Session()).create(
            Principal(user_id=USER, scope=SCOPE, role="reviewer"),
            specimen_with(run),
            "lane-state",
            "lane-state",
        )
    finally:
        actor_uid.reset(token)
    variables = calls[-1]["variables"]
    assert calls[-1]["operationName"] == "CreateSpecimenV3"
    assert variables["state"] == ("pending" if stage == "pending" else "running")
    assert variables["workAvailableAt"] is not None


def asset():
    return Asset(
        sha256="0" * 64,
        blob_ref="0" * 64,
        media_type="image/png",
        size_bytes=1,
        width=1,
        height=1,
        filename="lane.png",
        uploader=USER,
    )


def specimen_with(run):
    return Specimen(scope=SCOPE, run=run, asset=asset())
