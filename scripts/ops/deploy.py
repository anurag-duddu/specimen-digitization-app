#!/usr/bin/env python3
"""Deploy the SAM 3 service and define the worker job, from the committed runtime settings only.

    uv run --frozen python scripts/ops/deploy.py sam
    uv run --frozen python scripts/ops/deploy.py worker

Every environment variable, secret reference, resource limit, probe and argument comes from
scripts/ci/runtime_settings.py; the checkpoint digest from SAM_CHECKPOINT_SHA256 or, by default, the committed one.
Each deploy replaces the whole environment, secret set and volume set, so a re-run converges on the same definition.

sam     Cloud Run service specimen-sam: private (no allUsers invoker), ingress all, the read-only checkpoint mount at
        /model-cache owned by the image's user, CPU always allocated and startup CPU boost on (runtime_settings.SAM
        says why), minimum SAM_MIN_INSTANCES (default 0), maximum 1. scale_sam.py changes the minimum later.
worker  Cloud Run job specimen-worker: one task, no parallelism, no retries, the drain arguments. The job is only
        defined here; the API starts executions (jobs:run, no overrides, named by SPECIMEN_WORKER_JOB). Requires
        specimen-sam to be deployed: its URLs must include runtime_settings.SAM_URL, the endpoint and the audience
        SAM 3 checks the worker's identity token against.

Images: <registry>/<role>:<SOURCE_SHA> (build_images.py), or SAM_IMAGE / WORKER_IMAGE. Both resources are labelled
source-sha=<the image's commit>: the image tag when it is a full commit SHA, else SOURCE_SHA, which must then be set
(and must equal the tag when both are), so the deployed commit can be read back from either resource.
Parameters (environment): PROJECT, REGION (must match runtime_settings, whose values name them), SOURCE_SHA,
SAM_IMAGE, WORKER_IMAGE, SAM_CHECKPOINT_SHA256, SAM_MIN_INSTANCES, DRY_RUN=1.
Grants are separate: iam.py, re-run after this script so the invoker grants find the service and the job.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile

import ops_common as ops

settings = ops.settings
SERVICE, JOB = "specimen-sam", "specimen-worker"
MOUNT = "/model-cache"  # HF_HOME in runtime_settings.SAM["env"]


def checked_settings(role: str) -> dict:
    ops.committed_project()
    missing = settings.pending(role)
    if missing:
        raise SystemExit(f"runtime_settings has pending values for {role}: {', '.join(missing)}")
    return settings.ROLES[role]


def role_env(role: str, digest: str) -> dict[str, str]:
    """The role's plain environment, composed from runtime_settings."""
    values = dict(settings.ROLES[role]["env"])
    values["SPECIMEN_SAM3_CHECKPOINT_SHA256"] = digest
    if role == "sam":
        values.update(settings.SAM_SERVER_ENV)
    return values


def role_secrets(role: str) -> str:
    """--set-secrets value: each variable from its secret at the pinned version, never `latest`."""
    return ",".join(f"{name}={ops.pinned_secret(secret)}"
                    for name, secret in sorted(settings.ROLES[role]["secret_env"].items()))


def probe_flag(probe: dict, prefix: str = "") -> str:
    """{"tcpSocket": {"port": 8080}, "periodSeconds": 10} -> "tcpSocket.port=8080,periodSeconds=10"."""
    return ",".join(probe_flag(value, f"{prefix}{key}.") if isinstance(value, dict) else f"{prefix}{key}={value}"
                    for key, value in probe.items())


def image(role: str) -> tuple[str, str]:
    """(image reference, the commit it was built from), the commit for the source-sha label."""
    given = os.environ.get(f"{role.upper()}_IMAGE")
    if not given:
        sha = ops.source_sha()
        return f"{ops.registry()}/{role}:{sha}", sha
    name = given.split("@", 1)[0].rsplit("/", 1)[-1]
    tag, source = name.partition(":")[2], os.environ.get("SOURCE_SHA")
    if tag and source and tag != source:
        raise SystemExit(f"{role.upper()}_IMAGE's tag differs from SOURCE_SHA; the label must name the image's commit")
    sha = tag or source or ""
    if not ops.SHA.fullmatch(sha):
        raise SystemExit(f"{role.upper()}_IMAGE needs a full commit SHA as its tag (build_images.py tags it so) or "
                         "SOURCE_SHA naming the commit it was built from")
    return given, sha


def checkpoint_prefix(digest: str) -> str:
    return f"application/sha256/{digest}/sam3-cache"


def mount_options(digest: str) -> list[str]:
    """The checkpoint volume's gcsfuse options."""
    return [f"only-dir={checkpoint_prefix(digest)}", *settings.SAM["mount_options"]]


def sam_argv(env_path: str, digest: str) -> list[str]:
    spec = checked_settings("sam")
    low = ops.param("SAM_MIN_INSTANCES", "0")
    if not low.isdigit() or int(low) > spec["max_instances"]:
        raise SystemExit("SAM_MIN_INSTANCES must be a whole number no larger than the maximum")
    high = str(spec["max_instances"])
    reference, sha = image("sam")
    return ["gcloud", "run", "deploy", SERVICE, f"--project={ops.project()}", f"--region={ops.region()}",
            f"--image={reference}", f"--labels=source-sha={sha}", f"--service-account={spec['service_account']}",
            "--no-allow-unauthenticated", "--ingress=all", "--execution-environment=gen2",
            f"--cpu={spec['cpu']}", f"--memory={spec['memory']}",
            "--cpu-throttling" if spec["cpu_idle"] else "--no-cpu-throttling",
            "--cpu-boost" if spec["startup_cpu_boost"] else "--no-cpu-boost",
            f"--concurrency={spec['concurrency']}", f"--timeout={spec['timeout_seconds']}s", "--port=8080",
            # Revision level (--*-instances) and service level (--min/--max), both set to the same values. Cloud Run
            # applies the lesser maximum and the larger minimum
            # (docs.cloud.google.com/run/docs/configuring/max-instances and min-instances).
            f"--min-instances={low}", f"--max-instances={high}", f"--min={low}", f"--max={high}",
            f"--startup-probe={probe_flag(spec['startup_probe'])}",
            f"--env-vars-file={env_path}", f"--set-secrets={role_secrets('sam')}",
            # The gcsfuse options are separated by semicolons (--add-volume in the run deploy help).
            "--clear-volumes", "--add-volume=name=checkpoint,type=cloud-storage,"
            f"bucket={settings.BUCKET},readonly=true,mount-options={';'.join(mount_options(digest))}",
            "--clear-volume-mounts", f"--add-volume-mount=volume=checkpoint,mount-path={MOUNT}", "--quiet"]


def worker_argv(env_path: str) -> list[str]:
    spec = checked_settings("worker")
    args = spec["args"]
    if not all(isinstance(arg, str) and arg and "," not in arg for arg in args):
        raise SystemExit("runtime_settings.WORKER['args'] must be non-empty strings without commas")
    reference, sha = image("worker")
    return ["gcloud", "run", "jobs", "deploy", JOB, f"--project={ops.project()}", f"--region={ops.region()}",
            f"--image={reference}", f"--labels=source-sha={sha}", f"--service-account={spec['service_account']}",
            "--tasks", "1", "--parallelism", "1", "--max-retries", "0",
            "--task-timeout", f"{spec['timeout_seconds']}s",
            f"--cpu={spec['cpu']}", f"--memory={spec['memory']}", "--args=" + ",".join(args),
            f"--env-vars-file={env_path}", f"--set-secrets={role_secrets('worker')}", "--quiet"]


def sam_urls() -> set[str] | None:
    """The deployed service's URLs (status.url and the run.googleapis.com/urls annotation); None under DRY_RUN."""
    out = ops.read(["gcloud", "run", "services", "describe", SERVICE, f"--region={ops.region()}",
                    f"--project={ops.project()}", "--format=json"])
    if out is None:
        if ops.dry_run():
            return None
        raise SystemExit(f"{SERVICE} is not deployed (or not readable); run deploy.py sam first")
    service = json.loads(out)
    urls = {service.get("status", {}).get("url")}
    annotation = service.get("metadata", {}).get("annotations", {}).get("run.googleapis.com/urls")
    if annotation:
        urls.update(json.loads(annotation))
    return {url for url in urls if url}


def deploy(role: str) -> None:
    digest = ops.checkpoint_sha256()
    values = role_env(role, digest)
    if role == "worker":
        urls = sam_urls()
        if urls is not None and settings.SAM_URL not in urls:
            raise SystemExit(f"{SERVICE}'s URLs do not include runtime_settings.SAM_URL; the worker could not reach it")
        ops.note(f"worker SPECIMEN_SAM3_ENDPOINT={values['SPECIMEN_SAM3_ENDPOINT']} (deployed {SERVICE} serves it)")
    with tempfile.TemporaryDirectory(prefix=f"specimen-{role}-deploy-") as work:
        env_path = str(Path(work, "env.yaml"))
        Path(env_path).write_text(json.dumps(values, indent=1, sort_keys=True) + "\n")  # JSON is YAML.
        for name, value in sorted(values.items()):
            ops.note(f"env {name}={value}")  # Plain settings only; secrets travel as references.
        ops.run(sam_argv(env_path, digest) if role == "sam" else worker_argv(env_path))


def main(argv: list[str]) -> int:
    roles = argv or ["sam", "worker"]
    if set(roles) - {"sam", "worker"}:
        raise SystemExit("usage: deploy.py [sam] [worker]")
    for role in roles:
        deploy(role)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
