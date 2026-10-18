"""Define the worker job and private SAM service through runtime-release.yml only.

The release does not execute the worker or submit segmentation. It reads the
resulting Cloud Run definitions and policies to verify the pinned images and
bounded runtime settings. Inference acceptance is a separate application run.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ops"))
import deploy as model_settings  # noqa: E402

settings = model_settings.settings
REPOSITORY = "anurag-duddu/specimen-digitization-app"
WORKFLOW = f"{REPOSITORY}/.github/workflows/runtime-release.yml@refs/heads/main"
LOCATION = ["--region", settings.REGION, "--project", settings.PROJECT]


def release_context(env):
    if (env.get("GITHUB_ACTIONS") != "true" or env.get("GITHUB_REPOSITORY") != REPOSITORY
        or env.get("GITHUB_REF") != "refs/heads/main" or env.get("GITHUB_WORKFLOW_REF") != WORKFLOW
        or env.get("GITHUB_EVENT_NAME") not in {"push", "workflow_dispatch"}
        or not re.fullmatch(r"[a-f0-9]{40}", env.get("GITHUB_SHA", ""))):
        raise ValueError("only runtime-release.yml on main may define these runtimes")
    return env["GITHUB_SHA"]


def checked_image(role, reference):
    prefix = f"{settings.REGION}-docker.pkg.dev/{settings.PROJECT}/specimen-runtime/{role}"
    if not re.fullmatch(re.escape(prefix) + r"@sha256:[a-f0-9]{64}", reference):
        raise ValueError(f"{role} requires its immutable pushed image digest")
    return reference


def command(role, image, sha, env_path, *, job_name=None):
    """Reuse the reviewed operational settings, replacing all optional overrides."""
    checked_image(role, image)
    # The ops constructors only read settings/environment and produce argv. No
    # ops deploy entrypoint is invoked; all cloud effects live in this workflow.
    previous = dict(os.environ)
    try:
        os.environ.update(PROJECT=settings.PROJECT, REGION=settings.REGION, SOURCE_SHA=sha,
            SAM_MIN_INSTANCES="0", SAM_CHECKPOINT_SHA256=settings.SAM_CHECKPOINT_SHA256,
            **{f"{role.upper()}_IMAGE": image})
        argv = (model_settings.sam_argv(str(env_path), settings.SAM_CHECKPOINT_SHA256)
            if role == "sam" else model_settings.worker_argv(str(env_path)))
    finally:
        os.environ.clear()
        os.environ.update(previous)
    # Preserve IAM on deploy. Check that the existing SAM policy is private and
    # its worker invoker is present; no broader project permission is needed.
    argv = [arg for arg in argv if arg != "--no-allow-unauthenticated"]
    if job_name is not None:
        if role != "worker" or not re.fullmatch(r"specimen-worker-[a-z0-9-]+", job_name):
            raise ValueError("Dedicated scientific jobs require an explicit worker name")
        argv[4] = job_name
    return argv


def collection_routes():
    """Read only the reviewed routes version; never print its private payload."""
    secret = "specimen-collection-job-routes"  # pragma: allowlist secret -- resource name, never a credential
    version = settings.OPTIONAL_SECRET_VERSIONS[secret]
    if version is None:
        return {}
    if (type(version) is not int or version < 1 or settings.SECRET_VERSIONS.get(secret) != version
        or any(spec["secret_env"].get("SPECIMEN_COLLECTION_WORKER_JOBS_JSON") != secret
               for spec in (settings.API, settings.INTAKE, settings.WORKER))):
        raise ValueError("The same numbered routing secret must reach API and both shared workers")
    response = subprocess.run(["gcloud", "secrets", "versions", "access", str(version),
        f"--secret={secret}", f"--project={settings.PROJECT}"],
        capture_output=True, text=True, check=False)
    if response.returncode:
        raise ValueError("Pinned collection routes could not be read; run owner setup --intake-only")
    try:
        from specimen_digitization.application.runtime_config import collection_worker_jobs
        routes = dict(collection_worker_jobs({"SPECIMEN_COLLECTION_WORKER_JOBS_JSON": response.stdout}, settings.PROJECT))
        if not routes or len({route["actor_uid"] for route in routes.values()}) != 1:
            raise ValueError()
        for route in routes.values():
            for lane in ("worker", "intake"):
                prefix = f"{settings.PREFIX}/jobs/specimen-{lane}-"
                if not route[f"{lane}_job"].startswith(prefix):
                    raise ValueError()
        return routes
    except (ValueError, TypeError, KeyError):
        raise ValueError("Pinned collection routes must name distinct dedicated jobs in the approved region and one actor") from None


def scoped_job_env(base, scope, route):
    organization, collection = scope.split("/")
    return {**base, "SPECIMEN_WORKER_JOB": route["worker_job"],
        "SPECIMEN_INTAKE_JOB": route["intake_job"],
        "SPECIMEN_WORKER_SCOPE_JSON": json.dumps({"organization_id": organization,
            "collection_id": collection}, sort_keys=True, separators=(",", ":"))}


def intake_setup_metadata():
    """Bounded owner setup input: names and versions, never secret contents."""
    optional = settings.optional_secret_env("api")
    rows = [f"PIN\tapi\tspecimen-worker-actor-uid\t{settings.CORE_SECRET_VERSIONS['specimen-worker-actor-uid']}",
            "JOB\tintake\tspecimen-intake"]
    for name in sorted(set(optional.values())):
        rows.append(f"PIN\tapi\t{name}\t{settings.OPTIONAL_SECRET_VERSIONS[name]}")
        if name == "specimen-collection-job-routes":
            rows.append(f"PIN\tworker\t{name}\t{settings.OPTIONAL_SECRET_VERSIONS[name]}")
            rows.append(f"PIN\trelease\t{name}\t{settings.OPTIONAL_SECRET_VERSIONS[name]}")
    for name, version in sorted(settings.OAUTH_CLIENT_SECRET_VERSIONS.items()):
        rows.append(f"PIN\tapi\t{name}\t{version}")
    apis = settings.INTAKE_PROVIDER_APIS
    if (not isinstance(apis, (list, tuple)) or len(set(apis)) != len(apis)
        or set(apis) - {"drive.googleapis.com", "picker.googleapis.com"}
        or (apis and ("specimen-cloud-import-config" not in optional.values()
                      or not settings.OAUTH_CLIENT_SECRET_VERSIONS))):
        raise ValueError("Provider APIs require pinned import configuration and client-secret prerequisites")
    rows.extend(f"API\t{name}" for name in sorted(apis))
    for route in collection_routes().values():
        rows.append(f"JOB\tintake\t{route['intake_job'].rsplit('/', 1)[1]}")
        rows.append(f"JOB\tworker\t{route['worker_job'].rsplit('/', 1)[1]}")
    return rows


def read(group, name, action="describe"):
    result = subprocess.run(["gcloud", "run", group, action, name, *LOCATION, "--format=json"],
        capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def verify_policy(role, policy):
    bindings = policy.get("bindings", [])
    members = {member for binding in bindings for member in binding.get("members", [])}
    if members & {"allUsers", "allAuthenticatedUsers"}:
        raise ValueError(f"specimen-{role} must stay private")
    expected = {f"serviceAccount:{settings.WORKER_EMAIL}"}
    if role == "worker":
        expected.add(f"serviceAccount:{settings.API['service_account']}")
    invokers = {member for binding in bindings if binding.get("role") == "roles/run.invoker"
        and not binding.get("condition") for member in binding.get("members", [])}
    if not expected <= invokers:
        raise ValueError(f"specimen-{role} is missing its scoped invoker grant; owner setup required")


def verify_definition(role, resource, image, sha, *, expected_env=None):
    metadata, spec = resource.get("metadata", {}), resource.get("spec", {})
    if metadata.get("labels", {}).get("source-sha") != sha:
        raise ValueError(f"{role}: deployed source SHA differs")
    if role == "worker":
        template = spec.get("template", {}).get("spec", {})
        task = template.get("template", {}).get("spec", {})
        if (int(template.get("taskCount", 0)), int(template.get("parallelism", 0)),
            int(task.get("maxRetries", -1)), int(task.get("timeoutSeconds", 0))) != (1, 1, 0, 3600):
            raise ValueError("worker: task count, parallelism, retries or timeout differs")
        container = task.get("containers", [{}])[0]
        if container.get("args") != settings.WORKER["args"]:
            raise ValueError("worker: drain arguments differ")
    else:
        template = spec.get("template", {})
        annotations = template.get("metadata", {}).get("annotations", {})
        task = template.get("spec", {})
        container = task.get("containers", [{}])[0]
        if (annotations.get("autoscaling.knative.dev/minScale", "0") != "0"
            or metadata.get("annotations", {}).get("run.googleapis.com/minScale", "0") != "0"
            or annotations.get("autoscaling.knative.dev/maxScale") != "1"
            or int(task.get("containerConcurrency", 0)) != 1
            or metadata.get("annotations", {}).get("run.googleapis.com/maxScale") != "1"
            or annotations.get("run.googleapis.com/execution-environment") != "gen2"
            or annotations.get("run.googleapis.com/cpu-throttling") != "false"
            or annotations.get("run.googleapis.com/startup-cpu-boost") != "true"
            or int(task.get("timeoutSeconds", 0)) != 300):
            raise ValueError("sam: scaling, concurrency or timeout differs")
        urls = {resource.get("status", {}).get("url")}
        urls.update(json.loads(metadata.get("annotations", {}).get("run.googleapis.com/urls", "[]")))
        if settings.SAM_URL not in urls:
            raise ValueError("sam: endpoint differs from the worker's pinned audience")
        ready = resource.get("status", {}).get("conditions", [])
        if not any(row.get("type") == "Ready" and row.get("status") == "True" for row in ready):
            raise ValueError("sam: deployed revision is not ready")
        traffic = resource.get("status", {}).get("traffic", [])
        if (any(row.get("tag") for row in traffic)
            or sum(row.get("percent", 0) for row in traffic
                if row.get("revisionName") == resource.get("status", {}).get("latestReadyRevisionName")) != 100):
            raise ValueError("sam: old traffic or tagged revisions remain")
        if container.get("startupProbe") != settings.SAM["startup_probe"]:
            raise ValueError("sam: startup profile differs")
        expected_volume = {"name": "checkpoint", "csi": {"driver": "gcsfuse.run.googleapis.com",
            "readOnly": True, "volumeAttributes": {"bucketName": settings.BUCKET,
                "mountOptions": ",".join(model_settings.mount_options(settings.SAM_CHECKPOINT_SHA256))}}}
        if (task.get("volumes") != [expected_volume]
            or container.get("volumeMounts") != [{"name": "checkpoint", "mountPath": "/model-cache"}]):
            raise ValueError("sam: checkpoint volume differs")
    if len(task.get("containers", [])) != 1 or container.get("command"):
        raise ValueError(f"{role}: unexpected sidecar or entrypoint")
    limits = container.get("resources", {}).get("limits", {})
    if (limits.get("cpu"), limits.get("memory")) != (settings.ROLES[role]["cpu"], settings.ROLES[role]["memory"]):
        raise ValueError(f"{role}: bounded resource limits differ")
    if container.get("image") != image or task.get("serviceAccountName") != settings.ROLES[role]["service_account"]:
        raise ValueError(f"{role}: image digest or runtime identity differs")
    actual_env = {row["name"]: row.get("value") for row in container.get("env", []) if "value" in row}
    expected_env = model_settings.role_env(role, settings.SAM_CHECKPOINT_SHA256) if expected_env is None else expected_env
    if actual_env != expected_env:
        raise ValueError(f"{role}: pinned runtime environment differs")
    secrets = {row["name"]: row.get("valueFrom", {}).get("secretKeyRef")
        for row in container.get("env", []) if "valueFrom" in row}
    expected_secrets = {key: {"name": secret, "key": str(settings.SECRET_VERSIONS[secret])}
        for key, secret in settings.ROLES[role]["secret_env"].items()}
    if secrets != expected_secrets:
        raise ValueError(f"{role}: pinned secret references differ")


def main(argv):
    if argv[1:] == ["--intake-setup"]:
        for line in intake_setup_metadata():
            print(line)
        return
    if len(argv) != 3:
        raise ValueError("usage: deploy_models.py SAM_IMAGE_DIGEST WORKER_IMAGE_DIGEST")
    sha = release_context(os.environ)
    routes = collection_routes()
    images = {role: checked_image(role, image) for role, image in zip(("sam", "worker"), argv[1:], strict=True)}
    env = {**os.environ, "CLOUDSDK_CORE_DISABLE_PROMPTS": "1", "CLOUDSDK_CORE_SHOULD_PROMPT_TO_ENABLE_API": "false"}
    for role, image in images.items():
        group = "services" if role == "sam" else "jobs"
        # These runtimes already exist. Refuse missing/private-invoker setup
        # before the deploy rather than inventing access from a release identity.
        verify_policy(role, read(group, f"specimen-{role}", "get-iam-policy"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "env.json"
            path.write_text(json.dumps(model_settings.role_env(role, settings.SAM_CHECKPOINT_SHA256)))
            subprocess.run(command(role, image, sha, path), env=env, check=True)
        if role == "sam":
            # A tagged old revision with minScale=1 would keep spending after a
            # min0 deployment. Move all traffic and remove those tag references.
            subprocess.run(["gcloud", "run", "services", "update-traffic", "specimen-sam", *LOCATION,
                "--to-latest", "--clear-tags", "--quiet"], env=env, check=True)
        verify_definition(role, read(group, f"specimen-{role}"), image, sha)
        verify_policy(role, read(group, f"specimen-{role}", "get-iam-policy"))
        print(f"verified specimen-{role}: {sha} {image}; no inference executed", flush=True)
    for scope, route in routes.items():
        name = route["worker_job"].rsplit("/", 1)[1]
        values = scoped_job_env(model_settings.role_env("worker", settings.SAM_CHECKPOINT_SHA256), scope, route)
        # As for intake, first creation precedes its resource-level owner grant.
        # Missing access fails verification; it never starts or broadens a job.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "env.json"
            path.write_text(json.dumps(values))
            subprocess.run(command("worker", images["worker"], sha, path, job_name=name), env=env, check=True)
        verify_definition("worker", read("jobs", name), images["worker"], sha, expected_env=values)
        verify_policy("worker", read("jobs", name, "get-iam-policy"))
        print(f"verified dedicated scientific job {name}: {sha}; no inference executed", flush=True)


if __name__ == "__main__":
    try:
        main(sys.argv)
    except (ValueError, subprocess.CalledProcessError) as error:
        sys.exit(f"runtime definition release failed: {error}")
