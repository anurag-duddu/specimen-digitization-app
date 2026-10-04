"""`specimen-worker --mode production --drain` (docs/execution/golive/LANE.md, T2)."""

import contextvars
import json
import os
import sys
from unittest.mock import Mock

import pytest

from specimen_digitization.application import worker
from specimen_digitization.hub_models import SAM3_MODEL

JOB = "projects/example-project/locations/us-central1/jobs/specimen-worker"
DRAIN_ENV = {
    "SPECIMEN_WORKER_ACTOR_UID": "worker",
    "SPECIMEN_APPROVED_INFERENCE": "true",
    "SPECIMEN_SAM3_ENDPOINT": "https://sam.run.app",
    "SPECIMEN_SAM3_REVISION": SAM3_MODEL.revision,
    "HF_TOKEN": "fixture-not-a-credential",
}


@pytest.fixture
def drain_env(monkeypatch, tmp_path):
    from specimen_digitization import observability

    for key in (
        "SPECIMEN_SQL_EMULATOR_HOST",
        "DATA_CONNECT_EMULATOR_HOST",
        "FIREBASE_AUTH_EMULATOR_HOST",
        "FIREBASE_STORAGE_EMULATOR_HOST",
        "STORAGE_EMULATOR_HOST",
        "SPECIMEN_SAM3_LAB",
        "SPECIMEN_WORKER_JOB",
        "SPECIMEN_COLLECTION_BINDINGS_JSON",
        "SPECIMEN_RESEARCH_HARNESS",
        "CLOUD_RUN_EXECUTION",
        "CLOUD_RUN_TASK_INDEX",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in DRAIN_ENV.items():
        monkeypatch.setenv(key, value)
    for key in list(os.environ):
        if key.startswith(("SPECIMEN_TRACE_", "OTEL_")) or key in {
            "LOGFIRE_BASE_URL", "LOGFIRE_ENVIRONMENT", "LOGFIRE_SERVICE_VERSION"
        }:
            monkeypatch.delenv(key, raising=False)
    package = tmp_path / "built-package"
    package.mkdir()
    source_sha = "a" * 40
    (package / "_build.json").write_text(json.dumps({"source_sha": source_sha}))
    monkeypatch.setattr(observability, "__file__", str(package / "observability.py"))
    monkeypatch.setattr(observability, "_configured_settings", None)
    monkeypatch.setattr(observability, "_bounded_runtime", None)
    for key, value in {
        "APP_ENV": "production", "LOGFIRE_CAPTURE_MODE": "approved-content",
        "LOGFIRE_SEND_TO_LOGFIRE": "true", "LOGFIRE_SERVICE_NAME": "specimen-worker",
        "LOGFIRE_HEAD_SAMPLE_RATE": "1.0", "LOGFIRE_DISTRIBUTED_TRACING": "true",
        "LOGFIRE_TOKEN": "SYNTHETIC-DRAIN-WRITER-CANARY",
    }.items():
        monkeypatch.setenv(key, value)
    # CLI composition calls the real standing application configurator. Only
    # SDK effects are doubled; these wiring tests prove no export authority.
    configure, instrument, shutdown = Mock(), Mock(), Mock(return_value=True)
    monkeypatch.setattr(observability.logfire, "configure", configure)
    monkeypatch.setattr(observability.logfire, "instrument_pydantic_ai", instrument)
    monkeypatch.setattr(observability.logfire, "shutdown", shutdown)

    def no_supervisor(args):
        raise AssertionError("the drain must not run under the pilot's supervisor")

    monkeypatch.setattr(worker, "_supervise", no_supervisor)
    yield monkeypatch
    if configure.called:
        configure.assert_called_once()
        options = configure.call_args.kwargs
        assert options["send_to_logfire"] is True
        assert options["service_name"] == "specimen-worker"
        assert options["service_version"] == source_sha
        assert options["advanced"].base_url == "https://logfire-us.pydantic.dev"
        assert options["advanced"].exception_callback is observability._private_exception_callback
        assert options["inspect_arguments"] is False
        assert options["add_baggage_to_attributes"] is False
        assert options["variables"].instrument is False
        instrument.assert_called_once_with(include_content=True, include_binary_content=False,
            include_model_request_parameters=True, version=5)
        shutdown.assert_called_once_with(timeout_millis=observability.FINAL_FLUSH_MILLIS)


def cli(monkeypatch, *arguments):
    monkeypatch.setattr(sys, "argv", ["specimen-worker", *arguments])
    worker.main()


@pytest.mark.parametrize(
    "arguments",
    [
        ("--mode", "synthetic", "--drain"),
        ("--mode", "production", "--drain", "--once"),
        ("--mode", "production", "--drain", "--launch-policy", "launch.json"),
        ("--mode", "production", "--drain", "--source-manifest", "manifest.json"),
        ("--mode", "production", "--drain", "--evidence-only"),
        ("--mode", "production", "--drain", "--materialize-config"),
        ("--mode", "production", "--drain", "--max-seconds", "600"),
        ("--mode", "production", "--drain", "--max-seconds", "3601"),
    ],
)
def test_the_drain_takes_none_of_the_pilots_inputs(drain_env, capsys, arguments):
    with pytest.raises(SystemExit) as caught:
        cli(drain_env, *arguments)
    assert caught.value.code == 2
    assert "--drain" in capsys.readouterr().err


def test_check_config_validates_the_drain_settings(drain_env, capsys):
    cli(drain_env, "--mode", "production", "--drain", "--check-config")
    assert json.loads(capsys.readouterr().out) == {
        "status": "configured",
        "mode": "drain",
        "live_services_verified": False,
    }


def test_a_configuration_error_names_the_setting_not_its_value(drain_env, capsys):
    drain_env.setenv("SPECIMEN_SAM3_ENDPOINT", "http://unapproved-endpoint.example")
    with pytest.raises(SystemExit) as caught:
        cli(drain_env, "--mode", "production", "--drain", "--check-config")
    assert caught.value.code == 2
    output = capsys.readouterr().out
    report = json.loads(output)
    assert (report["status"], report["reason"]) == (
        "blocked",
        "drain_configuration_invalid",
    )
    assert "SPECIMEN_SAM3_ENDPOINT" in report["detail"]
    assert "unapproved-endpoint" not in output


def test_the_drain_runs_the_lane_worker_with_the_published_registries(
    drain_env, capsys
):
    from specimen_digitization import observability
    from specimen_digitization.application import lane_worker
    from specimen_digitization.application.lane_dispatch import CloudRunJobDispatcher

    drain_env.setenv("SPECIMEN_WORKER_JOB", JOB)
    drain_env.setenv("CLOUD_RUN_EXECUTION", "specimen-worker-abc12")
    drain_env.setenv("CLOUD_RUN_TASK_INDEX", "0")
    drain_env.setenv(
        "SPECIMEN_COLLECTION_BINDINGS_JSON",
        '{"00000000-0000-4000-8000-000000000002": "insects"}',
    )
    seen = {}

    class Repository:
        def __init__(self, **endpoint):
            assert actor.get() == "worker"
            seen["repository"] = self

        def memberships(self, uid):
            return []

    def workflow(repository, blobs, adapters, **registries):
        seen["registries"] = registries
        return "workflow"

    class Worker:
        def __init__(self, repository, workflow, user_id, membership_loader, **options):
            seen["worker"] = dict(options, user_id=user_id, workflow=workflow)

        def run(self, stop):
            assert actor.get() == "worker"
            seen["stop"] = stop
            return {"status": "drained", "processed": []}

    actor = contextvars.ContextVar("test_actor_uid", default=None)
    drain_env.setattr(worker, "actor_uid", actor)
    drain_env.setattr(worker, "sql_endpoint_from_env", lambda: {})
    drain_env.setattr(worker, "SqlConnectRepository", Repository)
    drain_env.setattr(worker, "GcsBlobs", lambda: "blobs")
    drain_env.setattr(worker, "ProductionAdapters", lambda blobs: "adapters")
    drain_env.setattr(worker, "Workflow", workflow)
    drain_env.setattr(lane_worker, "DrainWorker", Worker)
    drain_env.setattr("signal.signal", lambda signum, handler: None)

    cli(drain_env, "--mode", "production", "--drain")

    assert json.loads(capsys.readouterr().out) == {"status": "drained", "processed": []}
    assert actor.get() is None
    options = seen["worker"]
    assert options["user_id"] == "worker"
    assert options["workflow"] == "workflow"  # The ordinary chain, by default.
    assert 600 < options["deadline_seconds"] <= 3600  # Same original clock, including setup.
    assert options["execution_id"] == "specimen-worker-abc12/0"
    continuation = options["continuation"]
    assert isinstance(continuation.__self__, CloudRunJobDispatcher)
    assert continuation.__self__.job == JOB
    registries = seen["registries"]
    assert registries["profile_registry"].bindings == {
        "00000000-0000-4000-8000-000000000002": "insects"
    }
    assert registries["risk_registry"] is not None
    assert not seen["stop"].is_set()


def test_the_drain_without_a_job_reports_an_unconfigured_hand_over(
    drain_env, capsys
):
    from specimen_digitization import observability
    from specimen_digitization.application import lane_worker

    seen = {}

    class Worker:
        def __init__(self, *args, **options):
            seen.update(options)

        def run(self, stop):
            return {"continuation": seen["continuation"]().status}

    class Repository:
        def __init__(self, **endpoint):
            pass

        def memberships(self, uid):
            return []

    drain_env.setattr(worker, "actor_uid", contextvars.ContextVar("test_actor_uid"))
    drain_env.setattr(worker, "sql_endpoint_from_env", lambda: {})
    drain_env.setattr(worker, "SqlConnectRepository", Repository)
    drain_env.setattr(worker, "GcsBlobs", lambda: "blobs")
    drain_env.setattr(worker, "ProductionAdapters", lambda blobs: "adapters")
    drain_env.setattr(worker, "Workflow", lambda *args, **kwargs: "workflow")
    drain_env.setattr(lane_worker, "DrainWorker", Worker)
    drain_env.setattr("signal.signal", lambda signum, handler: None)

    cli(drain_env, "--mode", "production", "--drain", "--max-seconds", "1800")

    assert json.loads(capsys.readouterr().out) == {"continuation": "unconfigured"}
    # Configuration and setup spend from the same original 1800-second clock.
    assert 600 < seen["deadline_seconds"] <= 1800
    # Outside Cloud Run each run of the command is its own holder.
    assert len(seen["execution_id"]) == 36


def test_by_default_the_drain_takes_a_queued_record_through_the_ordinary_chain(
    drain_env, capsys, tmp_path
):
    """The actual Workflow and DrainWorker with the published registries. SQLite,
    local blobs and ProductionLikeAdapters (a whole-image region, readers that
    read their crop, a synthetic taxonomy lookup) stand in for SQL Connect,
    Cloud Storage, SAM 3, the Hugging Face readers and GBIF."""
    import time

    from fastapi.testclient import TestClient

    from specimen_digitization.application.api import (
        SYNTHETIC_COLLECTION,
        SYNTHETIC_ORG,
        SYNTHETIC_TEXT,
        create_app,
    )
    from specimen_digitization.application.collection_profiles import published_registry
    from specimen_digitization.application.domain import Disposition, LookupStatus
    from specimen_digitization.application.lane_allowance import ProgramLedger
    from specimen_digitization.application.profile_runtime import published_risk_registry
    from specimen_digitization.application.storage import LocalBlobs

    from test_lane_costs import seed_synthetic_ledger
    from test_lane_drain import NonSensitiveMember
    from test_lane_profile import ProductionLikeAdapters
    from test_lane_trigger import SCOPE, RecordingDispatcher, intake

    member = {
        "organization_id": SYNTHETIC_ORG,
        "collection_id": SYNTHETIC_COLLECTION,
        "role": "operator",
        "can_view_sensitive": False,
    }

    class Repository(NonSensitiveMember):
        def memberships(self, uid):
            return [member] if uid == "worker" else []

    blobs = LocalBlobs(tmp_path / "blobs")
    repository = Repository(tmp_path / "state.sqlite3")
    seed_synthetic_ledger(repository)
    registry = published_registry({SYNTHETIC_COLLECTION: "insects"})
    # A reviewer uploads one non-sensitive slide, which queues it (LANE.md T1).
    app = create_app(
        mode="emulator",
        repository=repository,
        blobs=blobs,
        adapters=ProductionLikeAdapters(blobs, SYNTHETIC_TEXT),
        identity_verifier=lambda token, check: "lane-reviewer",
        memberships=lambda user: [dict(member, role="reviewer", can_view_sensitive=True)],
        profile_registry=registry,
        risk_registry=published_risk_registry(),
        worker_dispatcher=RecordingDispatcher(),
    )
    ident = intake(TestClient(app, raise_server_exceptions=False))["specimen_id"]
    assert repository.get(SCOPE, ident).run.stage == "pending"
    # The drain lists work created and requested a second before its clock.
    time.sleep(1.1)

    drain_env.setenv(
        "SPECIMEN_COLLECTION_BINDINGS_JSON", json.dumps({SYNTHETIC_COLLECTION: "insects"})
    )
    drain_env.setattr(worker, "sql_endpoint_from_env", lambda: {})
    drain_env.setattr(worker, "SqlConnectRepository", lambda **endpoint: repository)
    drain_env.setattr(worker, "GcsBlobs", lambda: blobs)
    drain_env.setattr(
        worker, "ProductionAdapters", lambda blobs: ProductionLikeAdapters(blobs, SYNTHETIC_TEXT)
    )

    def no_harness(*_, **__):
        raise AssertionError("the research harness is off unless SPECIMEN_RESEARCH_HARNESS is on")

    drain_env.setattr(
        "specimen_digitization.application.native_drain.compose_registered_native_drain",
        no_harness,
    )
    drain_env.setattr("signal.signal", lambda signum, handler: None)

    cli(drain_env, "--mode", "production", "--drain")

    summary = json.loads(capsys.readouterr().out)
    assert (summary["status"], summary["processed"]) == ("drained", [ident])
    run = repository.get(SCOPE, ident).run
    assert (run.stage, run.disposition, run.blocker) == (
        "finalized",
        Disposition.REVIEW,
        None,
    )
    [region] = run.regions
    routes = ("handwriting-qwen", "handwriting-muse")
    for step in (
        "segment",
        *(f"transcribe:{region.id}:{route}" for route in routes),
        "parse",
        "plan",
        "lookup",
        "finalize",
    ):
        assert step in run.completed_steps
    assert run.lookups[-1].status == LookupStatus.SUCCESS
    # The paid steps reserved on the program's allowance, as on any other path.
    assert {"segment", *(f"transcribe:{region.id}:{route}" for route in routes)} <= {
        call["step"] for call in run.paid_calls
    }
    assert ProgramLedger(repository, SCOPE).read()["reserved_total_micros"] > 0


def test_with_the_harness_on_the_drain_mounts_it_over_the_ordinary_chain(
    drain_env, capsys
):
    from specimen_digitization.application import lane_worker

    drain_env.setenv("SPECIMEN_RESEARCH_HARNESS", "on")
    seen = {}

    class Repository:
        def __init__(self, **endpoint):
            pass

        def memberships(self, uid):
            return []

    def compose(ordinary, *, repository):
        seen["composed"] = (ordinary, repository)
        return "harness-workflow"

    class Worker:
        def __init__(self, repository, workflow, *args, **options):
            seen["worker"] = (repository, workflow)

        def run(self, stop):
            return {"status": "drained", "processed": []}

    drain_env.setattr(worker, "sql_endpoint_from_env", lambda: {})
    drain_env.setattr(worker, "SqlConnectRepository", Repository)
    drain_env.setattr(worker, "GcsBlobs", lambda: "blobs")
    drain_env.setattr(worker, "ProductionAdapters", lambda blobs: "adapters")
    drain_env.setattr(worker, "Workflow", lambda *args, **kwargs: "ordinary-workflow")
    drain_env.setattr(
        "specimen_digitization.application.native_drain.compose_registered_native_drain",
        compose,
    )
    drain_env.setattr(lane_worker, "DrainWorker", Worker)
    drain_env.setattr("signal.signal", lambda signum, handler: None)

    cli(drain_env, "--mode", "production", "--drain")

    assert json.loads(capsys.readouterr().out) == {"status": "drained", "processed": []}
    ordinary, repository = seen["composed"]
    assert ordinary == "ordinary-workflow"
    assert seen["worker"] == (repository, "harness-workflow")


def test_with_the_harness_on_the_actual_mount_wraps_the_ordinary_workflow_without_admission(
    drain_env, capsys
):
    from types import SimpleNamespace
    from specimen_digitization.application import lane_worker
    from specimen_digitization.application.native_drain import RegisteredNativeDrainWorkflow
    from specimen_digitization.research_harness.workflow_bridge import NativeResearchWorkflow
    drain_env.setenv("SPECIMEN_RESEARCH_HARNESS", "on")
    seen = {}
    class Repository:
        def __init__(self, **_):
            pass
        def memberships(self, _):
            raise AssertionError("mounting reads no membership; each research open does")
    ordinary = SimpleNamespace(admission=None)
    drain_env.setattr(worker, "SqlConnectRepository", Repository)
    drain_env.setattr(worker, "sql_endpoint_from_env", lambda: {})
    drain_env.setattr(worker, "GcsBlobs", lambda: SimpleNamespace(bucket=object()))
    drain_env.setattr(worker, "ProductionAdapters", lambda _: object())
    drain_env.setattr(worker, "Workflow", lambda *_, **__: ordinary)
    drain_env.setattr("signal.signal", lambda *args: None)
    class Worker:
        def __init__(self, repository, workflow, *args, **options):
            seen["workflow"] = workflow
        def run(self, stop):
            return {"status": "drained", "processed": []}
    drain_env.setattr(lane_worker, "DrainWorker", Worker)
    cli(drain_env, "--mode", "production", "--drain")
    assert json.loads(capsys.readouterr().out) == {"status": "drained", "processed": []}
    assert isinstance(seen["workflow"], RegisteredNativeDrainWorkflow)
    assert isinstance(seen["workflow"].workflow, NativeResearchWorkflow)
    assert seen["workflow"].ordinary is ordinary


@pytest.mark.parametrize("value", ["yes-please", "true", "On", "1", " on"])
def test_an_unknown_harness_setting_stops_the_drain_before_any_work(
    drain_env, capsys, value
):
    drain_env.setenv("SPECIMEN_RESEARCH_HARNESS", value)

    def nothing_constructed(*_, **__):
        raise AssertionError("no repository before the settings are valid")

    drain_env.setattr(worker, "SqlConnectRepository", nothing_constructed)
    with pytest.raises(SystemExit) as caught:
        cli(drain_env, "--mode", "production", "--drain")
    assert caught.value.code == 2
    output = capsys.readouterr().out
    report = json.loads(output)
    assert (report["status"], report["reason"]) == ("blocked", "drain_configuration_invalid")
    assert "SPECIMEN_RESEARCH_HARNESS" in report["detail"]
    assert "yes-please" not in output
