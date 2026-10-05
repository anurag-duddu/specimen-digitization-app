"""Offline runtime commands and readback; no cloud CLI is invoked."""
import copy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import deploy_models as deploy  # noqa: E402

SHA = "a" * 40


def image(role):
    return f"us-east4-docker.pkg.dev/specimen-digitization/specimen-runtime/{role}@sha256:" + "b" * 64


def test_release_entrypoint_rejects_workstations_branches_and_other_workflows():
    valid = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": deploy.REPOSITORY,
        "GITHUB_REF": "refs/heads/main", "GITHUB_WORKFLOW_REF": deploy.WORKFLOW,
        "GITHUB_SHA": SHA, "GITHUB_EVENT_NAME": "push"}
    assert deploy.release_context(valid) == SHA
    assert deploy.release_context({**valid, "GITHUB_EVENT_NAME": "workflow_dispatch"}) == SHA
    for key in valid:
        with pytest.raises(ValueError):
            deploy.release_context({**valid, key: "other"})


@pytest.mark.parametrize("role", ["sam", "worker"])
def test_only_the_correct_immutable_registry_image_is_admitted(role):
    assert deploy.checked_image(role, image(role)) == image(role)
    for bad in (image(role).replace("@sha256:", ":"), image("api"), image(role)[:-1]):
        with pytest.raises(ValueError):
            deploy.checked_image(role, bad)


def test_worker_is_one_sequential_task_with_no_retry_and_never_executed(tmp_path, monkeypatch):
    monkeypatch.setenv("SAM_MIN_INSTANCES", "9")
    command = deploy.command("worker", image("worker"), SHA, tmp_path / "env.json")
    assert command[:5] == ["gcloud", "run", "jobs", "deploy", "specimen-worker"]
    for flag, value in (("--tasks", "1"), ("--parallelism", "1"), ("--max-retries", "0"),
                        ("--task-timeout", "3600s")):
        assert command[command.index(flag) + 1] == value
    assert "--args=--mode,production,--drain,--max-seconds,3300" in command
    assert not any("execute" in arg for arg in command)


def test_sam_uses_committed_checkpoint_probe_and_zero_minimums(tmp_path, monkeypatch):
    monkeypatch.setenv("SAM_MIN_INSTANCES", "1")
    monkeypatch.setenv("SAM_CHECKPOINT_SHA256", "c" * 64)
    command = deploy.command("sam", image("sam"), SHA, tmp_path / "env.json")
    assert {"--min=0", "--min-instances=0", "--max=1", "--max-instances=1",
        "--no-cpu-throttling", "--cpu-boost", "--concurrency=1", "--timeout=300s"} <= set(command)
    assert any("failureThreshold=60" in arg for arg in command)
    assert any(deploy.settings.SAM_CHECKPOINT_SHA256 in arg and "readonly=true" in arg for arg in command)
    assert not any("allow-unauthenticated" in arg for arg in command)


def policy(role):
    members = [f"serviceAccount:{deploy.settings.WORKER_EMAIL}"]
    if role == "worker":
        members.append(f"serviceAccount:{deploy.settings.API['service_account']}")
    return {"bindings": [{"role": "roles/run.invoker", "members": members}]}


@pytest.mark.parametrize("role", ["sam", "worker"])
def test_expected_invokers_are_present_and_no_public_policy_is_accepted(role):
    deploy.verify_policy(role, policy(role))
    for member in ("allUsers", "allAuthenticatedUsers"):
        unsafe = copy.deepcopy(policy(role))
        unsafe["bindings"][0]["members"].append(member)
        with pytest.raises(ValueError, match="private"):
            deploy.verify_policy(role, unsafe)
    with pytest.raises(ValueError, match="scoped invoker"):
        deploy.verify_policy(role, {})


def resource(role):
    task = {"serviceAccountName": deploy.settings.ROLES[role]["service_account"],
        "containers": [{"image": image(role), "args": deploy.settings.WORKER["args"],
            "env": [{"name": key, "value": value} for key, value in
                deploy.model_settings.role_env(role, deploy.settings.SAM_CHECKPOINT_SHA256).items()]}]}
    container = task["containers"][0]
    container["resources"] = {"limits": {key: deploy.settings.ROLES[role][key] for key in ("cpu", "memory")}}
    container["env"] += [{"name": key, "valueFrom": {"secretKeyRef": {
        "name": secret, "key": str(deploy.settings.SECRET_VERSIONS[secret])}}}
        for key, secret in deploy.settings.ROLES[role]["secret_env"].items()]
    value = {"metadata": {"labels": {"source-sha": SHA}, "annotations": {"run.googleapis.com/maxScale": "1"}}, "spec": {}}
    if role == "worker":
        task.update(maxRetries=0, timeoutSeconds=3600)
        value["spec"]["template"] = {"spec": {"taskCount": 1, "parallelism": 1, "template": {"spec": task}}}
    else:
        container["startupProbe"] = copy.deepcopy(deploy.settings.SAM["startup_probe"])
        container["volumeMounts"] = [{"name": "checkpoint", "mountPath": "/model-cache"}]
        task["volumes"] = [{"name": "checkpoint", "csi": {"driver": "gcsfuse.run.googleapis.com",
            "readOnly": True, "volumeAttributes": {"bucketName": deploy.settings.BUCKET,
                "mountOptions": ",".join(deploy.model_settings.mount_options(deploy.settings.SAM_CHECKPOINT_SHA256))}}}]
        task.update(containerConcurrency=1, timeoutSeconds=300)
        value["spec"]["template"] = {"spec": task, "metadata": {"annotations": {
            "autoscaling.knative.dev/minScale": "0", "autoscaling.knative.dev/maxScale": "1",
            "run.googleapis.com/execution-environment": "gen2", "run.googleapis.com/cpu-throttling": "false",
            "run.googleapis.com/startup-cpu-boost": "true"}}}
        value["status"] = {"url": deploy.settings.SAM_URL, "latestReadyRevisionName": "revision",
            "conditions": [{"type": "Ready", "status": "True"}],
            "traffic": [{"revisionName": "revision", "percent": 100}]}
    return value


@pytest.mark.parametrize("role", ["sam", "worker"])
def test_readback_requires_the_deployed_digest_sha_identity_and_profile(role):
    value = resource(role)
    deploy.verify_definition(role, value, image(role), SHA)
    for bad_image, bad_sha in ((image("api"), SHA), (image(role), "c" * 40)):
        with pytest.raises(ValueError):
            deploy.verify_definition(role, value, bad_image, bad_sha)


def test_old_warm_tagged_sam_revision_fails_verification():
    value = resource("sam")
    value["status"]["traffic"].append({"revisionName": "old", "tag": "old-warm"})
    with pytest.raises(ValueError, match="tagged"):
        deploy.verify_definition("sam", value, image("sam"), SHA)


def test_processing_is_opt_in_and_cleanup_runs_after_failure():
    import yaml
    workflow = yaml.load((Path(__file__).resolve().parents[2] / ".github/workflows/runtime-release.yml").read_text(),
        Loader=yaml.BaseLoader)
    assert workflow["on"]["workflow_dispatch"]["inputs"]["process_queued"]["default"] == "false"
    steps = workflow["jobs"]["release"]["steps"]
    process, cool = steps[-2:]
    assert "inputs.process_queued" in process["if"] and "workflow_dispatch" in process["if"]
    assert "always()" in cool["if"] and "inputs.process_queued" in cool["if"]


@pytest.mark.parametrize("failure", ["warm", "execute", None])
def test_worker_process_always_cools_even_after_a_warm_failure(monkeypatch, failure):
    import process_worker
    calls = []
    monkeypatch.setattr(process_worker, "release_context", lambda env: SHA)
    def scale(wanted):
        calls.append(("scale", wanted))
        if wanted and failure == "warm":
            raise ValueError("warm failed")
    def run(command, **kwargs):
        calls.append(("execute", command))
        if failure == "execute":
            raise ValueError("execute failed")
    monkeypatch.setattr(process_worker, "scale", scale)
    monkeypatch.setattr(process_worker.subprocess, "run", run)
    if failure:
        with pytest.raises(ValueError):
            process_worker.main("process")
    else:
        process_worker.main("process")
    assert calls[0] == ("scale", 1) and calls[-1] == ("scale", 0)
    if failure == "warm":
        assert len(calls) == 2
    else:
        assert "--wait" in calls[1][1]
        assert not any("override" in arg or "args=" in arg for arg in calls[1][1])


@pytest.mark.parametrize("mutation", ["secret", "resource", "extra_env", "probe", "checkpoint", "sidecar"])
def test_sam_readback_refuses_runtime_drift(mutation):
    value = resource("sam")
    task = value["spec"]["template"]["spec"]
    container = task["containers"][0]
    if mutation == "secret":
        container["env"][-1]["valueFrom"]["secretKeyRef"]["key"] = "latest"
    if mutation == "resource":
        container["resources"]["limits"]["cpu"] = "8"
    if mutation == "extra_env":
        container["env"].append({"name": "UNREVIEWED_OVERRIDE", "value": "true"})
    if mutation == "probe":
        container["startupProbe"]["failureThreshold"] = 600
    if mutation == "checkpoint":
        task["volumes"][0]["csi"]["readOnly"] = False
    if mutation == "sidecar":
        task["containers"].append(copy.deepcopy(container))
    with pytest.raises(ValueError):
        deploy.verify_definition("sam", value, image("sam"), SHA)
