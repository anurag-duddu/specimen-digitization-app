"""`specimen-worker --mode production --drain` (docs/execution/golive/LANE.md, T2)."""

import contextvars
import json
import sys

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
def drain_env(monkeypatch):
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

    def no_supervisor(args):
        raise AssertionError("the drain must not run under the pilot's supervisor")

    monkeypatch.setattr(worker, "_supervise", no_supervisor)
    return monkeypatch


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
    drain_env.setattr(lane_worker, "DrainWorker", Worker)
    drain_env.setattr(observability, "configure_observability", lambda **_: None)
    drain_env.setattr("signal.signal", lambda signum, handler: None)

    cli(drain_env, "--mode", "production", "--drain")

    assert json.loads(capsys.readouterr().out) == {"status": "drained", "processed": []}
    assert actor.get() == "worker"
    options = seen["worker"]
    assert options["user_id"] == "worker"
    assert options["deadline_seconds"] == 3600
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
    drain_env.setattr(observability, "configure_observability", lambda **_: None)
    drain_env.setattr("signal.signal", lambda signum, handler: None)

    cli(drain_env, "--mode", "production", "--drain", "--max-seconds", "1800")

    assert json.loads(capsys.readouterr().out) == {"continuation": "unconfigured"}
    assert seen["deadline_seconds"] == 1800
    # Outside Cloud Run each run of the command is its own holder.
    assert len(seen["execution_id"]) == 36
