"""New native tracing needs its own approval and exact fifth writer secret."""

import pytest

from test_approved_runtime_timing import approved_activation, body
from test_runtime_release import M, NOW
from specimen_digitization.release_budget import APPROVAL_SHA256


TRACE_APPROVAL = "06af8483b7b190a5b0f2549475681a60483f2aff98a714472baad28376703b48"  # pragma: allowlist secret (approval digest)
WRITER_PARENT = "projects/specimen-digitization/secrets/specimen-worker-logfire"


def trace_activation(monkeypatch):
    plan, packet = approved_activation(monkeypatch)
    plan["activation"]["worker_trace"].update(
        version="worker-trace/v2", approval_sha256=TRACE_APPROVAL,
        token_secret=WRITER_PARENT + "/versions/7",
    )
    return plan, packet


def worker_env(plan, packet):
    worker = M.activation_worker(body(plan, packet), plan, packet, now=NOW)
    return {item["name"]: item for item in worker["template"]["template"]["containers"][0]["env"]}


def test_new_trace_approval_is_explicit_and_distinct_from_native_identity(monkeypatch):
    plan, packet = trace_activation(monkeypatch)
    M.validate_plan(plan, packet, now=NOW)
    env = worker_env(plan, packet)
    assert env["SPECIMEN_TRACE_APPROVAL_SHA256"]["value"] == TRACE_APPROVAL
    assert env["SPECIMEN_TRACE_SCOPE_SHA256"]["value"] == "b" * 64
    assert packet["budget"]["approval_sha256"] == APPROVAL_SHA256 != TRACE_APPROVAL
    assert env["LOGFIRE_TOKEN"] == M.env_secret("LOGFIRE_TOKEN", WRITER_PARENT + "/versions/7")
    assert env["LOGFIRE_SEND_TO_LOGFIRE"]["value"] == "false"
    assert "SPECIMEN_TRACE_LEDGER_PATH" not in env
    assert "LOGFIRE_BASE_URL" not in env


def test_legacy_trace_shape_does_not_receive_native_transport_authority(monkeypatch):
    plan, packet = approved_activation(monkeypatch)
    env = worker_env(plan, packet)
    assert "SPECIMEN_TRACE_APPROVAL_SHA256" not in env
    assert plan["activation"]["worker_trace"]["version"] == "worker-trace/v1"
    plan["activation"]["worker_trace"]["approval_sha256"] = TRACE_APPROVAL
    with pytest.raises(ValueError):
        M.validate_plan(plan, packet, now=NOW)


@pytest.mark.parametrize("change", [
    lambda trace: trace.pop("approval_sha256"),
    lambda trace: trace.update(approval_sha256=APPROVAL_SHA256),
    lambda trace: trace.update(approval_sha256="0" * 64),
    lambda trace: trace.update(approval_sha256=True),
    lambda trace: trace.update(token_secret="projects/specimen-digitization/secrets/other-writer/versions/7"),
    lambda trace: trace.update(token_secret=WRITER_PARENT + "-other/versions/7"),
    lambda trace: trace.update(token_secret=WRITER_PARENT + "/versions/latest"),
    lambda trace: trace.update(token_secret=WRITER_PARENT + "/versions/0"),
    lambda trace: trace.update(token_secret=WRITER_PARENT + "/versions/07"),
    lambda trace: trace.update(token_secret=WRITER_PARENT.replace("specimen-digitization/", "foreign/") + "/versions/7"),
    lambda trace: trace.update(endpoint="https://unreviewed.example/v1/traces"),
    lambda trace: trace.update(token_value="synthetic-canary"),
    lambda trace: trace.update(version="worker-trace/v3"),
])
def test_new_trace_binding_rejects_missing_or_substituted_scope(monkeypatch, change):
    plan, packet = trace_activation(monkeypatch)
    change(plan["activation"]["worker_trace"])
    with pytest.raises(ValueError):
        M.validate_plan(plan, packet, now=NOW)


def test_trace_approval_cannot_replace_budget_authority(monkeypatch):
    plan, packet = trace_activation(monkeypatch)
    packet["budget"]["approval_sha256"] = TRACE_APPROVAL
    with pytest.raises(ValueError):
        M.validate_plan(plan, packet, now=NOW)


def test_only_worker_gets_the_additive_trace_approval(monkeypatch):
    plan, packet = trace_activation(monkeypatch)
    images = {role: f"{M.REGISTRY}/{role}@sha256:" + "6" * 64 for role in ("api", "worker", "sam")}
    bodies = M.resource_bodies(plan, packet, images, "123", "1", now=NOW)
    for role in ("api", "sam"):
        assert not any(item["name"].startswith(("SPECIMEN_TRACE_", "LOGFIRE_"))
                       for item in bodies[role]["template"]["containers"][0]["env"])
    assert worker_env(plan, packet)["SPECIMEN_TRACE_APPROVAL_SHA256"]["value"] == TRACE_APPROVAL
