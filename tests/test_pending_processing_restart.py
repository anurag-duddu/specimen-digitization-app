"""A user retries worker startup without replacing an already queued run."""

from datetime import datetime, timedelta, timezone

import pytest

from specimen_digitization.application.api import summary
from specimen_digitization.application.domain import Disposition, Principal, Profile, Run, Specimen
from specimen_digitization.application.storage import SQLiteRepository, digest

import test_lane_trigger as lane


def pending_specimen():
    return Specimen(
        scope=lane.SCOPE,
        asset=lane.asset(),
        run=Run(
            stage="pending",
            queued_at=datetime.now(timezone.utc).isoformat(),
            profile=Profile(synthetic=False),
        ),
    )


@pytest.mark.parametrize("role", ["operator", "reviewer", "manager", "admin"])
def test_writable_pending_runs_offer_the_existing_process_endpoint(role):
    result = summary(pending_specimen(), role)
    assert result["available_actions"].count("start_processing") == 1


@pytest.mark.parametrize("role", ["viewer", "unknown"])
def test_read_only_roles_are_not_offered_a_processing_start(role):
    assert "start_processing" not in summary(pending_specimen(), role)["available_actions"]


@pytest.mark.parametrize(
    "restriction",
    ["sensitive", "pilot", "leased", "unknown", "budget", "disposition"],
)
def test_pending_start_is_withheld_for_restricted_runs(restriction):
    specimen = pending_specimen()
    if restriction == "sensitive":
        specimen.asset.sensitive = True
    elif restriction == "pilot":
        specimen.run.dependencies["evidence_pilot"] = {"retained": True}
    elif restriction == "leased":
        specimen.run.lease_until = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    elif restriction == "unknown":
        specimen.run.blocker = "external_outcome_unknown"
    elif restriction == "budget":
        specimen.run.blocker = "cost_budget_exhausted"
    else:
        specimen.run.disposition = Disposition.REVIEW
    assert "start_processing" not in summary(specimen, "admin")["available_actions"]


@pytest.mark.parametrize(
    "stage",
    ["ingested", "transcribe", "retry_scheduled", "processing_blocked", "paused", "cancelled", "finalized"],
)
def test_start_is_not_offered_for_other_run_states(stage):
    specimen = pending_specimen()
    specimen.run.stage = stage
    assert "start_processing" not in summary(specimen, "admin")["available_actions"]


def test_an_expired_lease_does_not_hide_safe_pending_start():
    specimen = pending_specimen()
    specimen.run.lease_until = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    assert "start_processing" in summary(specimen, "operator")["available_actions"]


def test_active_lease_withholds_actions_the_post_route_already_refuses():
    specimen = pending_specimen()
    specimen.run.lease_until = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    actions = summary(specimen, "admin")["available_actions"]
    assert not {"start_processing", "retry", "resume", "reprocess", "restore_version"}.intersection(actions)
    assert {"pause", "cancel"}.issubset(actions)


def mutate(root, ident, change):
    repository = SQLiteRepository(root / "state.sqlite3")
    specimen = repository.get(lane.SCOPE, ident)
    change(specimen)
    return repository.save(
        Principal(user_id=lane.USER, scope=lane.SCOPE, role="reviewer"),
        specimen,
        specimen.version,
        "pending-restart-fixture",
        digest(specimen.model_dump(mode="json")),
    )


@pytest.mark.parametrize("outcome", ["requested", "failed", "unconfigured"])
def test_explicit_pending_restart_preserves_every_saved_field_and_reports_dispatch(tmp_path, outcome):
    dispatcher = None if outcome == "unconfigured" else lane.RecordingDispatcher(outcome)
    client = lane.lane_client(tmp_path, dispatcher=dispatcher)
    uploaded = lane.intake(client)

    def checkpoint(specimen):
        specimen.run.completed_steps = ["pin_dependencies", "classify", "quality_check", "segment"]
        specimen.run.attempts = {"segment": 1, "transcribe:retained:reader": 2}
        specimen.run.usage.steps = 8
        specimen.run.usage.external_calls = 5
        specimen.run.usage.reserved_cost_micros = 12_345
        specimen.run.usage.actual_cost_micros = 6_789
        specimen.run.usage.reserved_tokens = 1_234

    before = mutate(tmp_path, uploaded["specimen_id"], checkpoint)
    detail = client.get(lane.PREFIX + f"/specimens/{before.id}", headers=lane.HEADERS)
    assert detail.status_code == 200, detail.text
    assert "start_processing" in detail.json()["available_actions"]
    if dispatcher is not None:
        assert dispatcher.calls == 1  # Reading status did not dispatch anything.

    response = lane.process(client, before.id, key="explicit-retry-start")
    assert response.status_code == 202, response.text
    result = response.json()
    assert result["dispatch"] == {
        "status": outcome,
        "reason": "http_503" if outcome == "failed" else None,
    }
    assert (result["active_run_id"], result["revision"]) == (before.run.id, before.version)
    assert result["status"] == "pending"
    # Includes queue time, completed steps, attempt history, policy and all
    # spend/reservations: a worker-start retry is not a run retry or reset.
    assert lane.stored(tmp_path, before.id).model_dump() == before.model_dump()
    if dispatcher is not None:
        assert dispatcher.calls == 2


@pytest.mark.parametrize("blocker", ["model_provider_error", "external_outcome_unknown", "cost_budget_exhausted"])
def test_process_cannot_bypass_a_historical_processing_block(tmp_path, blocker):
    dispatcher = lane.RecordingDispatcher()
    client = lane.lane_client(tmp_path, dispatcher=dispatcher)
    uploaded = lane.intake(client)

    def block(specimen):
        specimen.run.stage = "processing_blocked"
        specimen.run.blocker = blocker

    before = mutate(tmp_path, uploaded["specimen_id"], block)
    response = lane.process(client, before.id)
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "run_action_required"
    assert lane.stored(tmp_path, before.id).model_dump() == before.model_dump()
    assert dispatcher.calls == 1


def test_a_viewer_cannot_start_an_existing_pending_run(tmp_path):
    dispatcher = lane.RecordingDispatcher()
    uploaded = lane.intake(lane.lane_client(tmp_path, dispatcher=dispatcher))
    before = lane.stored(tmp_path, uploaded["specimen_id"])
    client = lane.lane_client(tmp_path, dispatcher=dispatcher, role="viewer")
    detail = client.get(lane.PREFIX + f"/specimens/{before.id}", headers=lane.HEADERS)
    assert detail.status_code == 200, detail.text
    assert "start_processing" not in detail.json()["available_actions"]
    response = lane.process(client, before.id)
    assert response.status_code == 403, response.text
    assert lane.stored(tmp_path, before.id).model_dump() == before.model_dump()
    assert dispatcher.calls == 1


@pytest.mark.parametrize("action", ["retry", "resume", "reprocess"])
def test_live_lease_actions_are_withheld_and_post_still_refuses_them(tmp_path, action):
    dispatcher = lane.RecordingDispatcher()
    client = lane.lane_client(tmp_path, dispatcher=dispatcher)
    uploaded = lane.intake(client)

    def lease(specimen):
        specimen.run.lease_until = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()

    before = mutate(tmp_path, uploaded["specimen_id"], lease)
    detail = client.get(lane.PREFIX + f"/specimens/{before.id}", headers=lane.HEADERS)
    assert detail.status_code == 200, detail.text
    assert action not in detail.json()["available_actions"]
    assert "start_processing" not in detail.json()["available_actions"]
    response = lane.action(client, before.id, action, "leased-action")
    assert response.status_code == 409, response.text
    assert "still leased" in response.json()["error"]["message"]
    assert lane.stored(tmp_path, before.id).model_dump() == before.model_dump()
    assert dispatcher.calls == 1


@pytest.mark.parametrize("restriction", ["sensitive", "pilot"])
def test_process_still_refuses_sensitive_or_pilot_records(tmp_path, restriction):
    dispatcher = lane.RecordingDispatcher()
    client = lane.lane_client(tmp_path, dispatcher=dispatcher)
    uploaded = lane.intake(client, sensitive=restriction == "sensitive")

    def restrict(specimen):
        specimen.run.stage = "pending"
        specimen.run.blocker = None
        if restriction == "pilot":
            specimen.run.dependencies["evidence_pilot"] = {"retained": True}

    before = mutate(tmp_path, uploaded["specimen_id"], restrict)
    previous_dispatches = dispatcher.calls
    response = lane.process(client, before.id)
    assert response.status_code == 409, response.text
    assert lane.stored(tmp_path, before.id).model_dump() == before.model_dump()
    assert dispatcher.calls == previous_dispatches


# A pending run behind the collection's live drain is in line (G13): one
# execution steps the collection's runs one at a time, and another worker
# start skips the held fence, so it cannot move the run forward.


def another_running_record(root, stage="transcribe"):
    from specimen_digitization.application.domain import Asset

    repository = SQLiteRepository(root / "state.sqlite3")
    other = Specimen(
        scope=lane.SCOPE,
        asset=Asset(
            sensitive=False,
            sha256="1" * 64,
            blob_ref="1" * 64,
            media_type="image/png",
            size_bytes=1,
            width=1,
            height=1,
            filename="ahead.png",
            uploader=lane.USER,
        ),
        run=Run(stage=stage, profile=Profile(synthetic=False)),
    )
    return repository.create(
        Principal(user_id=lane.USER, scope=lane.SCOPE, role="reviewer"),
        other,
        "running-ahead-fixture",
        digest(other.model_dump(mode="json")),
    )


def test_a_pending_run_behind_a_running_one_is_in_line_without_a_start(tmp_path):
    dispatcher = lane.RecordingDispatcher()
    client = lane.lane_client(tmp_path, dispatcher=dispatcher)
    uploaded = lane.intake(client)
    another_running_record(tmp_path)
    detail = client.get(lane.PREFIX + f"/specimens/{uploaded['specimen_id']}", headers=lane.HEADERS)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["status"] == "pending"
    assert "start_processing" not in body["available_actions"]
    assert body["intake_progress"]["waiting_in_line"] is True
    assert {"pause", "cancel"}.issubset(body["available_actions"])
    # The explicit start still answers, and reports the run as in line.
    response = lane.process(client, uploaded["specimen_id"], key="in-line-start")
    assert response.status_code == 202, response.text
    assert response.json()["intake_progress"]["waiting_in_line"] is True
    assert "start_processing" not in response.json()["available_actions"]


@pytest.mark.parametrize("other", [None, "ingested", "waiting_for_review"])
def test_a_pending_run_with_no_live_work_ahead_still_offers_a_start(tmp_path, other):
    client = lane.lane_client(tmp_path, dispatcher=lane.RecordingDispatcher())
    uploaded = lane.intake(client)
    if other:
        another_running_record(tmp_path, other)
    detail = client.get(lane.PREFIX + f"/specimens/{uploaded['specimen_id']}", headers=lane.HEADERS)
    assert detail.status_code == 200, detail.text
    assert detail.json()["intake_progress"]["waiting_in_line"] is False
    assert "start_processing" in detail.json()["available_actions"]


def test_lane_busy_counts_only_recent_running_work_by_another_record():
    from specimen_digitization.application.intake_progress import LIVE_DRAIN_SECONDS, lane_busy

    current = datetime(2026, 10, 12, 18, 0, tzinfo=timezone.utc)
    recent = (current - timedelta(minutes=2)).isoformat()
    stale = (current - timedelta(seconds=LIVE_DRAIN_SECONDS + 1)).isoformat()

    def row(ident="other", status="running", stage="transcribe", updated_at=recent):
        return {"specimen_id": ident, "status": status, "stage": stage, "updated_at": updated_at}

    assert lane_busy([row()], "self", current)
    # SQL Connect's nanosecond, Z-suffixed timestamps read as the same instant.
    assert lane_busy([row(updated_at="2026-10-12T17:59:00.123456789Z")], "self", current)
    assert lane_busy([row(updated_at=None)], "self", current)  # SQLite has no save time.
    assert not lane_busy([], "self", current)
    assert not lane_busy([row(ident="self")], "self", current)
    assert not lane_busy([row(updated_at=stale)], "self", current)
    assert not lane_busy([row(updated_at="not a time")], "self", current)
    assert not lane_busy([row(status="pending")], "self", current)
    assert not lane_busy([row(stage="ingested"), row(stage="waiting_for_review")], "self", current)
    assert lane_busy([row(updated_at=stale), row(ident="third")], "self", current)


def recorded_intake(client):
    """Upload one photo; its completion reply and a way to send it again."""
    sent = []
    post = client.post

    def recording(url, **kwargs):
        sent.append((url, kwargs))
        return post(url, **kwargs)

    client.post = recording
    try:
        completed = lane.intake(client)
    finally:
        client.post = post
    url, kwargs = next((u, k) for u, k in sent if u.endswith("/complete"))
    return completed, lambda: client.post(url, **kwargs)


def test_an_upload_completed_behind_a_running_record_is_in_line_and_replays_fresh(tmp_path):
    dispatcher = lane.RecordingDispatcher()
    client = lane.lane_client(tmp_path, dispatcher=dispatcher)
    ahead = another_running_record(tmp_path)
    completed, replay = recorded_intake(client)
    assert completed["status"] == "pending"
    assert "start_processing" not in completed["available_actions"]
    assert completed["intake_progress"]["waiting_in_line"] is True
    assert dispatcher.calls == 1  # The upload still asks for a worker.

    again = replay()
    assert again.status_code == 200, again.text
    assert again.json()["specimen_id"] == completed["specimen_id"]
    assert again.json()["intake_progress"]["waiting_in_line"] is True
    assert "start_processing" not in again.json()["available_actions"]

    # The record ahead stops: a replay derives the state again, so the
    # stored reply never froze the transient in-line state.
    lane.force_stage(tmp_path, ahead.id, "paused")
    later = replay()
    assert later.status_code == 200, later.text
    assert later.json()["intake_progress"]["waiting_in_line"] is False
    assert "start_processing" in later.json()["available_actions"]
    assert dispatcher.calls == 1  # A replay dispatches nothing.


def test_an_upload_completed_with_nothing_ahead_still_offers_a_start(tmp_path):
    completed, replay = recorded_intake(
        lane.lane_client(tmp_path, dispatcher=lane.RecordingDispatcher())
    )
    assert completed["intake_progress"]["waiting_in_line"] is False
    assert "start_processing" in completed["available_actions"]
    assert replay().json() == completed


@pytest.mark.parametrize("failure", ["operational_block", "connection"])
def test_a_failed_reread_after_an_accepted_upload_returns_the_stored_reply(
    tmp_path, monkeypatch, failure
):
    """The upload is accepted, stored and dispatched before the in-line re-read.

    A read that fails then (a SQL Connect hold, a dropped connection) leaves
    the stored summary as the reply, first time and on replay.
    """
    from specimen_digitization.application.workflow import OperationalBlock

    armed = []
    get, put_document = SQLiteRepository.get, SQLiteRepository.put_document

    def put_and_arm(self, scope, kind, ident, payload, expected):
        stored = put_document(self, scope, kind, ident, payload, expected)
        if kind == "upload" and payload.get("state") == "accepted":
            armed.append(payload["completion_response"])
        return stored

    def failing_get(self, scope, ident):
        if armed:
            raise (
                OperationalBlock("sql_connect_unavailable")
                if failure == "operational_block"
                else ConnectionError("connection reset")
            )
        return get(self, scope, ident)

    monkeypatch.setattr(SQLiteRepository, "put_document", put_and_arm)
    monkeypatch.setattr(SQLiteRepository, "get", failing_get)
    dispatcher = lane.RecordingDispatcher()
    client = lane.lane_client(tmp_path, dispatcher=dispatcher)
    completed, replay = recorded_intake(client)
    assert len(armed) == 1
    assert completed == armed[0]  # The stored summary, unchanged.
    assert "waiting_in_line" not in completed["intake_progress"]
    again = replay()
    assert again.status_code == 200, again.text
    assert again.json() == armed[0]
    assert dispatcher.calls == 1
