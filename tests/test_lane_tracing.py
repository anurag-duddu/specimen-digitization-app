"""The run's trace (docs/execution/golive/LANE.md, T5a)."""

from fastapi.testclient import TestClient
from logfire.testing import CaptureLogfire

from specimen_digitization.application.api import (
    SYNTHETIC_COLLECTION,
    SYNTHETIC_ORG,
    SYNTHETIC_TEXT,
    create_app,
)
from specimen_digitization.application.collection_profiles import published_registry
from specimen_digitization.application.domain import Principal, Scope
from specimen_digitization.application.profile_runtime import published_risk_registry
from specimen_digitization.application.storage import LocalBlobs, SQLiteRepository

from test_lane_profile import USER, ProductionLikeAdapters
from test_lane_trigger import RecordingDispatcher, action, intake

SCOPE = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
ROOT = "Process specimen run"
STAGE = "Run specimen processing stage"
DECISION = "Specimen queue decision"


def lab(tmp_path):
    blobs = LocalBlobs(tmp_path / "blobs")
    app = create_app(
        mode="emulator",
        repository=SQLiteRepository(tmp_path / "state.sqlite3"),
        blobs=blobs,
        adapters=ProductionLikeAdapters(blobs, SYNTHETIC_TEXT),
        identity_verifier=lambda token, check: USER,
        memberships=lambda user: [
            {
                "organization_id": SYNTHETIC_ORG,
                "collection_id": SYNTHETIC_COLLECTION,
                "role": "reviewer",
                "can_view_sensitive": True,
            }
        ],
        profile_registry=published_registry({SYNTHETIC_COLLECTION: "insects"}),
        risk_registry=published_risk_registry(),
        worker_dispatcher=RecordingDispatcher(),
    )
    client = TestClient(app, raise_server_exceptions=False)
    principal = Principal(user_id=USER, scope=SCOPE, role="reviewer")
    return app, client, principal, intake(client)["specimen_id"]


def named(capfire, name):
    return [s for s in capfire.exporter.exported_spans_as_dict() if s["name"] == name]


def test_a_run_is_one_trace_whose_steps_hang_from_its_root(tmp_path, capfire: CaptureLogfire):
    app, _, principal, ident = lab(tmp_path)
    run = app.state.workflow.drain(principal, ident).run
    [root] = named(capfire, ROOT)
    stages = named(capfire, STAGE)
    # Each step is its own call with no enclosing span, as in separate
    # executions of the worker: every one attaches the run's stored context.
    assert len(stages) >= 5
    trace = root["context"]["trace_id"]
    assert root["parent"] is None
    assert all(s["context"]["trace_id"] == trace for s in stages)
    assert all(s["parent"]["span_id"] == root["context"]["span_id"] for s in stages)
    assert run.trace_id == format(trace, "032x")
    assert run.trace_context["traceparent"].split("-")[1] == run.trace_id


def test_the_root_carries_the_specimen_run_collection_and_profile(
    tmp_path, capfire: CaptureLogfire
):
    app, _, principal, ident = lab(tmp_path)
    run = app.state.workflow.drain(principal, ident).run
    [root] = named(capfire, ROOT)
    attributes = root["attributes"]
    assert attributes["specimen.id"] == ident
    assert attributes["specimen.run.id"] == run.id
    assert attributes["specimen.collection.id"] == SYNTHETIC_COLLECTION
    assert attributes["specimen.collection_profile.id"] == "zoology_insects_slides"
    assert attributes["specimen.collection_profile.version"] == "1.0.0"


def test_each_step_names_its_stage(tmp_path, capfire: CaptureLogfire):
    app, _, principal, ident = lab(tmp_path)
    app.state.workflow.drain(principal, ident)
    stages = [s["attributes"] for s in named(capfire, STAGE)]
    assert {"pin_dependencies", "classify", "segment", "transcribe", "parse"} <= {
        a["specimen.processing.stage"] for a in stages
    }
    assert any(a["specimen.processing.step"].startswith("transcribe:") for a in stages)


def test_the_queue_decision_is_logged_with_its_reasons(tmp_path, capfire: CaptureLogfire):
    app, _, principal, ident = lab(tmp_path)
    run = app.state.workflow.drain(principal, ident).run
    assert run.stage == "finalized", run.blocker
    [decision] = named(capfire, DECISION)
    assert decision["attributes"]["disposition"] == run.disposition
    assert list(decision["attributes"]["reason_codes"]) == run.reasons
    assert decision["context"]["trace_id"] == named(capfire, ROOT)[0]["context"]["trace_id"]


def test_a_reprocessed_run_starts_a_new_trace(tmp_path, capfire: CaptureLogfire):
    app, client, principal, ident = lab(tmp_path)
    first = app.state.workflow.drain(principal, ident).run
    response = action(client, ident, "reprocess", "reprocess-1")
    assert response.status_code == 200, response.text
    second = app.state.workflow.drain(principal, ident).run
    assert second.id != first.id
    assert second.trace_id and second.trace_id != first.trace_id
    assert len(named(capfire, ROOT)) == 2
