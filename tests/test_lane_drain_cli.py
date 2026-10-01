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
        shutdown.assert_called_once_with(timeout_millis=1000)


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
            seen["stop"] = stop
            return {"status": "drained", "processed": []}

    actor = contextvars.ContextVar("test_actor_uid", default=None)
    drain_env.setattr(worker, "actor_uid", actor)
    drain_env.setattr(worker, "sql_endpoint_from_env", lambda: {})
    drain_env.setattr(worker, "SqlConnectRepository", Repository)
    drain_env.setattr(worker, "GcsBlobs", lambda: "blobs")
    drain_env.setattr(worker, "ProductionAdapters", lambda blobs: "adapters")
    drain_env.setattr(worker, "Workflow", workflow)
    # This existing offline wiring control proves no admission authority. The
    # genuine missing-authority CLI refusal has a separate actual-caller case.
    drain_env.setattr("specimen_digitization.application.native_drain.compose_registered_native_drain",
        lambda ordinary, **_: ordinary)
    drain_env.setattr(lane_worker, "DrainWorker", Worker)
    drain_env.setattr("signal.signal", lambda signum, handler: None)

    cli(drain_env, "--mode", "production", "--drain")

    assert json.loads(capsys.readouterr().out) == {"status": "drained", "processed": []}
    assert actor.get() == "worker"
    options = seen["worker"]
    assert options["user_id"] == "worker"
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
    drain_env.setattr("specimen_digitization.application.native_drain.compose_registered_native_drain",
        lambda ordinary, **_: ordinary)
    drain_env.setattr(lane_worker, "DrainWorker", Worker)
    drain_env.setattr("signal.signal", lambda signum, handler: None)

    cli(drain_env, "--mode", "production", "--drain", "--max-seconds", "1800")

    assert json.loads(capsys.readouterr().out) == {"continuation": "unconfigured"}
    # Configuration and setup spend from the same original 1800-second clock.
    assert 600 < seen["deadline_seconds"] <= 1800
    # Outside Cloud Run each run of the command is its own holder.
    assert len(seen["execution_id"]) == 36


def test_actual_drain_without_protected_origin_refuses_before_fence_or_paid_work(drain_env, capsys):
    from types import SimpleNamespace
    from specimen_digitization import observability
    from specimen_digitization.application import lane_worker
    class Repository:
        def __init__(self, **_):
            pass
        def memberships(self, _):
            raise AssertionError("no collection fence/discovery before installed admission")
    drain_env.setattr(worker, "SqlConnectRepository", Repository)
    drain_env.setattr(worker, "sql_endpoint_from_env", lambda: {})
    drain_env.setattr(worker, "GcsBlobs", lambda: object())
    drain_env.setattr(worker, "ProductionAdapters", lambda _: object())
    drain_env.setattr(worker, "Workflow", lambda *_, **__: SimpleNamespace(admission=None))
    drain_env.setattr("signal.signal", lambda *args: None)
    def no_worker(*_, **__):
        raise AssertionError("a missing protected origin must not construct a drain")
    drain_env.setattr(lane_worker, "DrainWorker", no_worker)
    with pytest.raises(SystemExit) as caught:
        cli(drain_env, "--mode", "production", "--drain")
    assert caught.value.code == 2
    assert json.loads(capsys.readouterr().out) == {
        "status":"blocked", "reason":"legacy_import_protected_authority_origin_unavailable"}
