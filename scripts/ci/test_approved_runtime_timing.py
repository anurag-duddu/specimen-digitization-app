"""The protected one-job request retains the approved original clock."""

import copy
import hashlib
import json
from datetime import datetime, timezone
import pytest

from test_runtime_release import activation_fixture, NOW, M
from specimen_digitization.release_budget import APPROVAL_SHA256


def approved_activation(monkeypatch):
    plan, packet = activation_fixture(monkeypatch)
    packet["issued_at_unix"] = NOW
    packet["expires_at_unix"] = NOW + 4000
    packet["budget"].update(version="shared-release-reservations/v2", approval_sha256=APPROVAL_SHA256)
    plan["worker"]["timing_version"] = "approved-worker-timing/v1"
    plan["sam"]["expires_at_unix"] = NOW + 2200
    launch = json.loads(plan["activation"]["launch_bytes"])
    launch["cohort_allocation_mode"] = "actual-regions-v1"
    launch["timing"] = {"version": "approved-worker-timing/v1", "approval_sha256": APPROVAL_SHA256,
                        "dispatch_started_at_unix": NOW, "sam_expires_at_unix": NOW + 2200}
    launch["expires_at"] = datetime.fromtimestamp(NOW + 3500, timezone.utc).isoformat()
    plan["activation"]["launch_bytes"] = json.dumps(launch)
    plan["worker"]["launch_sha256"] = hashlib.sha256(plan["activation"]["launch_bytes"].encode()).hexdigest()
    plan["activation"]["worker_trace"] = {
        "version": "worker-trace/v1", "project_id": "synthetic-existing-project",
        "token_secret": "projects/specimen-digitization/secrets/synthetic-logfire-writer/versions/1",  # pragma: allowlist secret (synthetic resource ID)
        "service_name": "specimen-worker", "identity_receipt_sha256": "b" * 64,
    }
    return plan, packet


def body(plan, packet):
    images = {role: f"{M.REGISTRY}/{role}@sha256:" + "6" * 64 for role in ("api", "worker", "sam")}
    return M.resource_bodies(plan, packet, images, "123", "1", now=NOW)["worker"]


def test_approved_template_and_dispatch_use_same_original_clock(monkeypatch):
    plan, packet = approved_activation(monkeypatch)
    worker = M.activation_worker(body(plan, packet), plan, packet, now=NOW + 30)
    task = worker["template"]["template"]
    assert task["timeout"] == "3470s"
    assert task["maxRetries"] == 0
    assert worker["template"]["taskCount"] == worker["template"]["parallelism"] == 1
    container = task["containers"][0]
    assert container["resources"]["limits"] == {"cpu": "1", "memory": "1Gi"}
    assert container["args"][-2:] == ["--max-seconds", "3485"]
    env = {entry["name"]: entry.get("value") for entry in container["env"]}
    timing = json.loads(env["SPECIMEN_WORKER_TIMING"])
    assert timing["dispatch_started_at_unix"] == NOW
    assert timing["sam_expires_at_unix"] == NOW + 2200
    assert worker["runExecutionToken"] == "pilot-" + packet["pilot"]["manifest_sha256"][:24]


def test_trace_reference_is_worker_only_and_metadata_settings_are_exact(monkeypatch):
    plan, packet = approved_activation(monkeypatch)
    images = {role: f"{M.REGISTRY}/{role}@sha256:" + "6" * 64 for role in ("api", "worker", "sam")}
    bodies = M.resource_bodies(plan, packet, images, "123", "1", now=NOW)
    worker = M.activation_worker(bodies["worker"], plan, packet, now=NOW)
    env = {v["name"]: v for v in worker["template"]["template"]["containers"][0]["env"]}
    assert env["LOGFIRE_TOKEN"] == M.env_secret("LOGFIRE_TOKEN", plan["activation"]["worker_trace"]["token_secret"])
    expected = {"LOGFIRE_SEND_TO_LOGFIRE": "true", "LOGFIRE_SERVICE_NAME": "specimen-worker",
                "APP_ENV": "production", "LOGFIRE_CAPTURE_MODE": "metadata", "LOGFIRE_HEAD_SAMPLE_RATE": "1.0",
                "LOGFIRE_DISTRIBUTED_TRACING": "false"}
    assert {key: env[key]["value"] for key in expected} == expected
    assert "LOGFIRE_BASE_URL" not in env
    for role in ("api", "sam"):
        assert not any(item["name"].startswith("LOGFIRE_") for item in bodies[role]["template"]["containers"][0]["env"])


@pytest.mark.parametrize("change", [
    lambda p: p["activation"].pop("worker_trace"),
    lambda p: p["activation"]["worker_trace"].update(token_secret=p["activation"]["hf_secret"]),
    lambda p: p["activation"]["worker_trace"].update(token_secret="projects/foreign/secrets/writer/versions/1"),
    lambda p: p["activation"]["worker_trace"].update(token_secret="projects/specimen-digitization/secrets/writer/versions/latest"),
    lambda p: p["activation"]["worker_trace"].update(identity_receipt_sha256="missing"),
    lambda p: p["activation"]["worker_trace"].update(project_id=""),
    lambda p: p["activation"]["worker_trace"].update(token_value="synthetic-canary-value"),
    lambda p: p["activation"]["worker_trace"].update(base_url="https://unreviewed.example"),
])
def test_trace_missing_or_substituted_delivery_fails_closed(monkeypatch, change):
    plan, packet = approved_activation(monkeypatch)
    change(plan)
    with pytest.raises(ValueError):
        M.validate_plan(plan, packet, now=NOW)


def test_dispatch_minimum_sam_lifetime_is_rechecked_after_preparation(monkeypatch):
    plan, packet = approved_activation(monkeypatch)
    proposed = body(plan, packet)
    with pytest.raises(ValueError, match="SAM.*dispatch"):
        M.activation_worker(proposed, plan, packet, now=NOW + 66)


@pytest.mark.parametrize("change", [
    lambda p, a: a["budget"].update(version="shared-release-reservations/v1"),
    lambda p, a: a["budget"].update(approval_sha256="0" * 64),
    lambda p, a: p["worker"].pop("timing_version"),
    lambda p, a: p["sam"].update(expires_at_unix=NOW + 2201),
    lambda p, a: a.update(expires_at_unix=NOW + 3499),
])
def test_timing_dialects_and_deadlines_cannot_be_mixed(monkeypatch, change):
    plan, packet = approved_activation(monkeypatch)
    change(plan, packet)
    with pytest.raises(ValueError):
        M.validate_plan(plan, packet, now=NOW)


def test_dispatch_intent_is_durable_before_effect_and_exclusive(tmp_path, monkeypatch):
    plan, packet = approved_activation(monkeypatch)
    worker = M.activation_worker(body(plan, packet), plan, packet, now=NOW)
    intent = M.retain_worker_dispatch(tmp_path, worker, plan, packet, now=NOW)
    retained = json.loads((tmp_path / "worker-dispatch.intent.json").read_bytes())
    assert retained == intent
    assert retained["timing"]["dispatch_started_at_unix"] == NOW
    assert retained["request_sha256"] == hashlib.sha256(json.dumps(worker, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    with pytest.raises(FileExistsError):
        M.retain_worker_dispatch(tmp_path, worker, plan, packet, now=NOW)
    assert json.loads((tmp_path / "worker-dispatch.intent.json").read_bytes()) == retained


def test_transport_rechecks_dispatch_after_slow_fresh_admission(monkeypatch):
    from test_release_google import transport
    import release_google

    google = transport()
    google.plane = "runtime"
    clock, sent = [NOW], []
    monkeypatch.setattr(release_google.time, "time", lambda: clock[0])

    def admission(*args):
        clock[0] += 66
        return google.packet

    monkeypatch.setattr(release_google, "admit", admission)
    monkeypatch.setattr(google.session, "request", lambda *args, **kwargs: sent.append(args))

    def guard(api, method, resource, body):
        M.require(NOW + 2200 - clock[0] >= 2135, "SAM dispatch lifetime exhausted")

    google.worker_dispatch_guard = guard
    with pytest.raises(ValueError, match="SAM dispatch"):
        google.request("run", "PATCH", M.PREFIX + "/jobs/specimen-worker", body={"runExecutionToken": "fixed"})
    assert sent == []
