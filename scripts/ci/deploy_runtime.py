#!/usr/bin/env python3
"""Protected runtime build, preparation, promotion and one-execution entrypoint.

Never run from a workstation. The workflow obtains credentials only after
admission. Preparation does not run the worker or claim product acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import stat
import tempfile
import time

from release_admission import (admit, digest, exact_keys, integer, materialize_inputs,
                               private_bytes, read_bound_plan, read_packet, require, strict_json)
from release_context import PROJECT, REPOSITORY
from release_google import Google
import release_publication_deadline as publication
from validate_release_packet import IMAGE
from specimen_digitization.hub_models import SAM3_MODEL

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = f"us-east4-docker.pkg.dev/{PROJECT}/specimen-runtime"
PREFIX = f"projects/{PROJECT}/locations/us-east4"
SECRET = re.compile(rf"projects/{PROJECT}/secrets/[a-zA-Z0-9_-]+/versions/[1-9][0-9]*")
API_ENV = {"SPECIMEN_FIREBASE_PROJECT", "SPECIMEN_FIREBASE_PROJECT_NUMBER", "SPECIMEN_FIREBASE_APP_IDS",
           "SPECIMEN_SQL_LOCATION", "SPECIMEN_SQL_SERVICE", "SPECIMEN_SQL_CONNECTOR", "SPECIMEN_GCS_BUCKET",
           "SPECIMEN_CORS_ORIGINS", "SPECIMEN_READINESS_OBJECT", "SPECIMEN_READINESS_GENERATION"}
SAM_REVISION = SAM3_MODEL.revision


def validate_expected_runtime(role, value):
    require(value["expected_etag"] is None or isinstance(value["expected_etag"], str)
            and 1 <= len(value["expected_etag"]) <= 200, "invalid expected etag")
    if role != "worker":
        previous = value["previous_revision"]
        require(previous is None or isinstance(previous, str) and re.fullmatch(rf"specimen-{role}-[a-z0-9-]{{1,45}}", previous), "foreign previous revision")
        require((previous is None) == (value["expected_etag"] is None), "previous revision and expected state must agree")


def validate_plan(plan: object, packet: dict, *, now=None):
    require(isinstance(plan, dict), "runtime plan required")
    keys = {"version", "source_sha", "data_receipt", "api", "worker", "sam"}
    if plan.get("version") == "runtime-activate/v1":
        keys.add("activation")
    plan = exact_keys(plan, keys, "activation" if "activation" in keys else "runtime plan")
    require(plan["version"] in {"runtime-prepare/v1", "runtime-activate/v1"}, "unsupported runtime phase")
    require(plan["source_sha"] == packet["source_sha"], "runtime plan source mismatch")
    receipt = exact_keys(plan["data_receipt"], {"sha256", "run_id", "run_attempt", "source_sha"}, "data receipt")
    digest(receipt["sha256"], "data receipt")
    integer(receipt["run_id"], 1, 2**53, "data receipt run")
    integer(receipt["run_attempt"], 1, 2**53, "data receipt attempt")
    require(receipt["source_sha"] == packet["source_sha"], "incompatible data source")
    api = exact_keys(plan["api"], {"expected_etag", "previous_revision", "environment"}, "API plan")
    validate_expected_runtime("api", api)
    exact_keys(api["environment"], API_ENV, "API environment")
    from specimen_digitization.application.runtime_config import RuntimeConfig
    config = RuntimeConfig.from_env(api["environment"])
    require(config.project_number == packet["identity"]["project_number"] and config.location == "us-east4"
            and config.service == "specimen-digitization-service" and config.connector == "specimen-server"
            and set(config.origins) <= {"https://specimen-digitization.web.app", "https://specimen-digitization.firebaseapp.com"},
            "unapproved API targets")
    if plan["version"] == "runtime-prepare/v1" and plan["worker"] is None and plan["sam"] is None:
        return plan
    worker = exact_keys(plan["worker"], {"expected_etag", "launch_secret", "manifest_secret", "launch_sha256", "manifest_sha256"}, "worker plan")
    sam = exact_keys(plan["sam"], {"expected_etag", "previous_revision", "expires_at_unix", "manifest_secret", "manifest_sha256", "checkpoint_prefix", "checkpoint_sha256", "audience"}, "SAM plan")
    for role, value in (("api", api), ("worker", worker), ("sam", sam)):
        validate_expected_runtime(role, value)
    for value, keys in ((worker, ("launch_secret", "manifest_secret")), (sam, ("manifest_secret",))):
        for key in keys:
            require(isinstance(value[key], str) and SECRET.fullmatch(value[key]), "immutable secret version required")
    for key in ("launch_sha256", "manifest_sha256"):
        digest(worker[key], key)
    require(worker["manifest_sha256"] == sam["manifest_sha256"], "manifest mismatch")
    digest(sam["checkpoint_sha256"], "SAM checkpoint content")
    require(isinstance(sam["checkpoint_prefix"], str) and re.fullmatch(
        r"application/sha256/[a-f0-9]{64}/sam3-cache", sam["checkpoint_prefix"]), "approved immutable SAM cache prefix required")
    require(sam["audience"] == f"https://specimen-sam-{packet['identity']['project_number']}.us-east4.run.app",
            "approved deterministic SAM audience required")
    now = time.time() if now is None else now
    integer(sam["expires_at_unix"], 1, 2**53, "SAM expiry")
    require(now + 125 < sam["expires_at_unix"] <= min(now + 3600, packet["expires_at_unix"]), "SAM deadline outside approved window")
    if plan["version"] == "runtime-activate/v1":
        validate_activation_inputs(plan, packet, now=now)
    return plan


def secret_volume(name, resource, filename):
    secret, version = resource.rsplit("/versions/", 1)
    return {"name": name, "secret": {"secret": secret, "items": [{"version": version, "path": filename, "mode": 0o444}]}}


def env_secret(name, resource):
    secret, version = resource.rsplit("/versions/", 1)
    return {"name": name, "valueSource": {"secretKeyRef": {"secret": secret, "version": version}}}


def resource_bodies(plan, packet, images, run_id, attempt, *, now=None):
    validate_plan(plan, packet, now=now)
    require(set(images) == {"api", "worker", "sam"}, "three runtime images required")
    require(re.fullmatch(r"[1-9][0-9]*", run_id) and re.fullmatch(r"[1-9][0-9]*", attempt), "invalid release run")
    for role, image in images.items():
        require(isinstance(image, str) and IMAGE.fullmatch(image) and f"/{role}@sha256:" in image, "invalid immutable role image")
    bodies = {}
    for role in (("api",) if plan["sam"] is None else ("api", "sam")):
        settings = plan[role]
        revision = f"specimen-{role}-{packet['source_sha'][:12]}-{run_id}-{attempt}"
        require(len(revision) <= 63, "revision name too long")
        container = {"image": images[role], "ports": [{"containerPort": 8080}],
                     "resources": {"limits": {"cpu": "1" if role == "api" else "4", "memory": "1Gi" if role == "api" else "16Gi"},
                                   "cpuIdle": True, "startupCpuBoost": False}}
        body = {"name": f"{PREFIX}/services/specimen-{role}", "ingress": "INGRESS_TRAFFIC_ALL",
                "scaling": {"minInstanceCount": 0, "maxInstanceCount": 2 if role == "api" else 1},
                "labels": {"source-sha": packet["source_sha"], "release-run": run_id},
                "template": {"revision": revision, "serviceAccount": f"specimen-{role}-runtime@{PROJECT}.iam.gserviceaccount.com",
                             "scaling": {"minInstanceCount": 0, "maxInstanceCount": 2 if role == "api" else 1},
                             "timeout": "60s" if role == "api" else "130s", "maxInstanceRequestConcurrency": 8 if role == "api" else 1,
                             "executionEnvironment": "EXECUTION_ENVIRONMENT_GEN2", "containers": [container]}}
        if settings["expected_etag"] is not None:
            body["etag"] = settings["expected_etag"]
            body["traffic"] = [{"type": "TRAFFIC_TARGET_ALLOCATION_TYPE_REVISION", "revision": settings["previous_revision"], "percent": 100},
                               {"type": "TRAFFIC_TARGET_ALLOCATION_TYPE_REVISION", "revision": revision, "percent": 0, "tag": "candidate"}]
        if role == "api":
            container["env"] = [{"name": name, "value": value} for name, value in sorted(settings["environment"].items())]
        else:
            body["template"]["volumes"] = [secret_volume("manifest", settings["manifest_secret"], "manifest.json"),
                {"name": "checkpoint", "gcs": {"bucket": f"{PROJECT}.firebasestorage.app", "readOnly": True,
                                              "mountOptions": ["only-dir=" + settings["checkpoint_prefix"]]}}]
            container["volumeMounts"] = [{"name": "manifest", "mountPath": "/inputs/manifest"}, {"name": "checkpoint", "mountPath": "/model-cache"}]
            container["args"] = ["--materialize-config"]
            values = {"SPECIMEN_SAM3_ENABLE": "authorized-pilot", "SPECIMEN_SAM3_BUDGET_AUTHORIZATION": packet["authorization_sha256"],
                      "SPECIMEN_PILOT_MANIFEST_PATH": "/inputs/manifest/manifest.json", "SPECIMEN_PILOT_MANIFEST_SHA256": settings["manifest_sha256"],
                      "SPECIMEN_SAM3_EXPIRES_UNIX": str(settings["expires_at_unix"]), "SPECIMEN_SAM3_AUDIENCE": settings["audience"],
                      "SPECIMEN_SAM3_CALLER_EMAIL": f"specimen-worker-runtime@{PROJECT}.iam.gserviceaccount.com",
                      "SPECIMEN_SAM3_OUTPUT_BUCKET": f"{PROJECT}.firebasestorage.app", "HF_HOME": "/model-cache",
                      "HF_HUB_OFFLINE": "1", "SPECIMEN_SAM3_CHECKPOINT_SHA256": settings["checkpoint_sha256"]}
            container["env"] = [{"name": k, "value": v} for k, v in sorted(values.items())]
        bodies[role] = body
    if plan["worker"] is None:
        return bodies
    worker = plan["worker"]
    bodies["worker"] = {"name": f"{PREFIX}/jobs/specimen-worker", "labels": {"source-sha": packet["source_sha"], "release-run": run_id},
                        "template": {"taskCount": 1, "parallelism": 1, "template": {
                            "serviceAccount": f"specimen-worker-runtime@{PROJECT}.iam.gserviceaccount.com",
                            "timeout": "1800s", "maxRetries": 0,
                            "volumes": [secret_volume("launch", worker["launch_secret"], "launch.json"),
                                        secret_volume("manifest", worker["manifest_secret"], "manifest.json")],
                            "containers": [{"image": images["worker"], "resources": {"limits": {"cpu": "1", "memory": "1Gi"}},
                                            "args": ["--mode", "production", "--materialize-config", "--check-config", "--launch-policy", "/inputs/launch/launch.json",
                                                     "--source-manifest", "/inputs/manifest/manifest.json", "--max-seconds", "1500"],
                                            "env": [{"name": "SPECIMEN_LAUNCH_POLICY_SHA256", "value": worker["launch_sha256"]}],
                                            "volumeMounts": [{"name": "launch", "mountPath": "/inputs/launch"}, {"name": "manifest", "mountPath": "/inputs/manifest"}]}]}}}
    if worker["expected_etag"] is not None:
        bodies["worker"]["etag"] = worker["expected_etag"]
    return bodies


def checked(command, *, output=False, timeout=120, env=None):
    if publication.CURRENT is not None:
        timeout = publication.publication_budget(cap=timeout)
    result = subprocess.run(command, check=False, capture_output=True, timeout=timeout, cwd=ROOT, env=env)
    require(result.returncode == 0, "release command failed; captured command output is withheld from public logs")
    return result.stdout if output else None


def publish_role(path: Path, role: str, output: Path):
    require(role in {"api", "worker", "sam"}, "unknown image role")
    publication.publication_budget()
    google = Google(path, "runtime-build")
    repository = google.request("registry", "GET", f"{PREFIX}/repositories/specimen-runtime")
    require(repository.get("format") == "DOCKER" and repository.get("dockerConfig", {}).get("immutableTags") is True,
            "existing immutable Docker registry required")
    tag_name = f"sha-{google.packet['source_sha']}-{google.packet['release_run_id']}-{google.packet['release_run_attempt']}"
    prior = google.request("registry", "GET", f"{PREFIX}/repositories/specimen-runtime/packages/{role}/tags/{tag_name}", missing=True)
    require(prior is None, "image publication already exists for this operation; reconcile without rebuilding")
    build_env = {key: os.environ[key] for key in ("PATH", "HOME", "TMPDIR", "GITHUB_SHA", "DOCKER_CONFIG", "DOCKER_HOST")
                 if key in os.environ}
    checked(["scripts/ci/build_runtime_image.sh", role], timeout=3600, env=build_env)
    # Re-check source, time, attempt and budget after a potentially long build.
    packet = admit(path, "runtime-build")
    publication.publication_budget(packet)
    image = f"{REGISTRY}/{role}"
    tag = f"{image}:sha-{packet['source_sha']}-{packet['release_run_id']}-{packet['release_run_attempt']}"
    google.registry_login()
    checked(["docker", "tag", f"specimen-ci-{role}:{packet['source_sha']}", tag])
    checked(["docker", "push", tag], timeout=600)
    digests = json.loads(checked(["docker", "image", "inspect", tag, "--format", "{{json .RepoDigests}}"], output=True))
    refs = [value for value in digests if value.startswith(image + "@sha256:")]
    require(len(refs) == 1 and IMAGE.fullmatch(refs[0]), "registry returned no unique role digest")
    receipt = {"version": "runtime-image/v1", "role": role, "source_sha": packet["source_sha"],
               "run_id": packet["release_run_id"], "run_attempt": packet["release_run_attempt"], "reference": refs[0]}
    publication.publication_budget(packet)
    publication.private_write(output, json.dumps(receipt, sort_keys=True) + "\n")
    # Only the outside supervisor can promote this candidate to public outputs.


def verify_attestation(path_or_image: str, source_sha: str, workflow: str):
    return checked(["gh", "attestation", "verify", path_or_image, "--repo", REPOSITORY,
                    "--signer-workflow", f"{REPOSITORY}/.github/workflows/{workflow}",
                    "--source-digest", source_sha, "--signer-digest", source_sha,
                    "--source-ref", "refs/heads/main", "--deny-self-hosted-runners", "--format", "json"], output=True)


def verified_receipt_bytes(path, expected_sha256, source_sha, workflow):
    """Bind the parsed buffer to the actual subject returned by gh verification."""
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as handle:
        info = os.fstat(handle.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid(), "owned receipt file required")
        raw = handle.read(1048577)
    require(len(raw) <= 1048576 and hashlib.sha256(raw).hexdigest() == expected_sha256, "signed receipt digest mismatch")
    proof = verify_attestation(str(path), source_sha, workflow)
    require(isinstance(proof, (bytes, str)), "verified attestation subject evidence missing")
    records = strict_json(proof)
    require(isinstance(records, list) and records, "verified attestation subject evidence missing")
    subjects = [subject for record in records if isinstance(record, dict)
                for subject in record.get("verificationResult", {}).get("statement", {}).get("subject", [])]
    require(any(isinstance(subject, dict) and subject.get("digest", {}).get("sha256") == expected_sha256 for subject in subjects),
            "verified attestation subject does not match the consumed receipt bytes")
    return raw


def deploy(path: Path, receipts: Path, output: Path):
    google = Google(path, "runtime")
    packet = google.packet
    plan = validate_plan(read_bound_plan(path.parent / "plan.json", packet), packet)
    if plan["version"] == "runtime-activate/v1":
        activate(google, plan, output)
        return
    google.registry_login()
    images = {}
    for role in ("api", "worker", "sam"):
        receipt = json.loads((receipts / f"runtime-image-{role}-{packet['source_sha']}-{packet['release_run_attempt']}" / f"{role}.json").read_text())
        exact_keys(receipt, {"version", "role", "source_sha", "run_id", "run_attempt", "reference"}, "image receipt")
        require(receipt["version"] == "runtime-image/v1" and receipt["role"] == role
                and receipt["source_sha"] == packet["source_sha"] and receipt["run_id"] == packet["release_run_id"]
                and receipt["run_attempt"] == packet["release_run_attempt"], "stale build receipt")
        require(isinstance(receipt["reference"], str) and IMAGE.fullmatch(receipt["reference"])
                and f"/{role}@sha256:" in receipt["reference"], "invalid role image receipt")
        verify_attestation("oci://" + receipt["reference"], packet["source_sha"], "runtime-release.yml")
        images[role] = receipt["reference"]
    verify_data_receipt(plan, packet, google)
    bodies = resource_bodies(plan, packet, images, str(packet["release_run_id"]), str(packet["release_run_attempt"]))
    observations = {}
    for role in (role for role in ("api", "sam", "worker") if role in bodies):
        body = bodies[role]
        existing = google.request("run", "GET", body["name"], missing=True)
        expected = plan[role]["expected_etag"]
        require((existing is None and expected is None) or existing is not None and existing.get("etag") == expected,
                f"{role} changed since approval; reconcile")
        if existing is not None and role != "worker":
            require(existing.get("latestReadyRevision", "").split("/")[-1] == plan[role]["previous_revision"], "previous runtime revision differs")
        if existing is None:
            collection, name = body["name"].rsplit("/", 1)
            operation = google.request("run", "POST", collection, body=body,
                                       params={"jobId" if role == "worker" else "serviceId": name})
        else:
            operation = google.request("run", "PATCH", body["name"], body=body)
        google.wait("run", operation, maximum_seconds=900)
        observed = google.request("run", "GET", body["name"])
        require(observed.get("reconciling") is False and observed.get("terminalCondition", {}).get("state") == "CONDITION_SUCCEEDED",
                f"{role} deployment did not reconcile")
        verify_runtime_template(observed, body, role=role)
        observations[role] = {"name": observed["name"], "etag": observed["etag"], "image": images[role],
                              "revision": observed.get("latestReadyRevision"), "uri": observed.get("uri"), "traffic": observed.get("trafficStatuses", [])}
    output.write_text(json.dumps({"version": "runtime-prepared/v1", "source_sha": packet["source_sha"],
                                 "run_id": packet["release_run_id"], "run_attempt": packet["release_run_attempt"],
                                 "resources": observations, "images": images, "worker_executed": False, "release_accepted": False}, sort_keys=True) + "\n")


def verify_data_receipt(plan, packet, google):
    from deploy_data import verify_schema_receipt
    require(plan["data_receipt"]["source_sha"] == packet["source_sha"], "current source compatibility receipt required")
    return verify_schema_receipt(google, {"schema_receipt": plan["data_receipt"]})



def validate_activation_inputs(plan, packet, *, now=None):
    activation = exact_keys(plan["activation"], {"prepared_receipt", "manifest_bytes", "launch_bytes", "profile_bytes",
                                              "profile_secret", "hf_secret", "actor_uid", "human_review_authorization_sha256"}, "activation")
    prepared = exact_keys(activation["prepared_receipt"], {"run_id", "run_attempt", "sha256"}, "prepared runtime receipt")
    for name in ("run_id", "run_attempt"):
        integer(prepared[name], 1, 2**53, name)
    digest(prepared["sha256"], "prepared runtime receipt")
    scope_hash = activation["human_review_authorization_sha256"]
    digest(scope_hash, "human review authority")
    require(scope_hash == os.environ.get("RELEASE_HUMAN_REVIEW_AUTHORIZATION_SHA256"), "human review release authority mismatch")
    for name in ("profile_secret", "hf_secret"):
        require(isinstance(activation[name], str) and SECRET.fullmatch(activation[name]), "immutable worker secret required")
    require(isinstance(activation["actor_uid"], str) and 1 <= len(activation["actor_uid"]) <= 128, "verified worker actor required")
    from specimen_digitization.application.pilot_manifest import PilotManifest
    from specimen_digitization.application.worker_launch import PilotLaunch
    from specimen_digitization.application.collection_profiles import CollectionProfile
    from specimen_digitization.model_gateway import INITIAL_HUGGINGFACE_ROUTES
    values = {}
    for field, expected in (("manifest_bytes", plan["worker"]["manifest_sha256"]), ("launch_bytes", plan["worker"]["launch_sha256"])):
        raw = activation[field]
        require(isinstance(raw, str) and len(raw.encode()) <= 65536, "bounded private activation bytes required")
        require(hashlib.sha256(raw.encode()).hexdigest() == expected, "activation input digest mismatch")
        values[field] = strict_json(raw)
    manifest = PilotManifest.model_validate(values["manifest_bytes"])
    launch = PilotLaunch.model_validate(values["launch_bytes"])
    from specimen_digitization.application.sam3_effect import canonical_sha256
    require(launch.sam3_checkpoint_files is not None
            and canonical_sha256(launch.sam3_checkpoint_files) == plan["sam"]["checkpoint_sha256"]
            and plan["sam"]["checkpoint_prefix"] == "application/sha256/" + plan["sam"]["checkpoint_sha256"] + "/sam3-cache",
            "offline checkpoint map or content-addressed cache binding mismatch")
    require(launch.stage_cost_reservations is not None, "complete model stage cost map required")
    require(manifest.selection.source_inventory_sha256 == packet["pilot"]["manifest_sha256"],
            "ready manifest does not preserve the original frozen cohort budget identity")
    require(all(source.bucket == f"{PROJECT}.firebasestorage.app" for item in manifest.specimens for source in item.source_objects),
            "foreign specimen source bucket")
    require(launch.source_manifest_sha256 == plan["worker"]["manifest_sha256"] and launch.evidence_only is True
            and launch.hf_secret_resource == activation["hf_secret"], "human review launch mismatch")
    budget = {item["category"]: item["ceiling_micros"] for item in packet["budget"]["reservations"]}
    require(launch.total_cost_limit_micros <= budget["provider"] + budget["sam"], "worker launch exceeds its shared provider/SAM allocation")
    costs = launch.stage_cost_reservations.cost_micros
    require(sum(costs.values()) <= launch.per_specimen_cost_limit_micros
            and costs["segment"] * 10 <= budget["sam"]
            and sum(v for k, v in costs.items() if k.startswith("transcribe:")) * 10 <= budget["provider"],
            "ten first-pass model stages do not fit their reviewed category allocations")
    now = time.time() if now is None else now
    require(now + 125 < launch.expires_at.timestamp() <= min(plan["sam"]["expires_at_unix"], packet["expires_at_unix"]), "worker launch expiry mismatch")
    actual = [(s.specimen_id, s.asset_sha256, s.blob_ref) for s in launch.specimens]
    expected = [(s.specimen_id, s.application_source.sha256, s.application_source.blob_ref) for s in manifest.specimens]
    require(actual == expected and all((s.organization_id, s.collection_id) ==
            (launch.scope.organization_id, launch.scope.collection_id) for s in manifest.specimens), "launch and intake scope/bindings disagree")
    raw = activation["profile_bytes"]
    require(isinstance(raw, str) and len(raw.encode()) <= 65536 and hashlib.sha256(raw.encode()).hexdigest() == launch.evidence_profile_sha256,
            "immutable human review profile mismatch")
    profile = CollectionProfile.model_validate(strict_json(raw))
    require(profile.state == "draft" and not profile.synthetic and not profile.institutional_policy_approved
            and not profile.semantics_confirmed and profile.segmentation_settings is not None
            and tuple(profile.model_routes) == tuple(INITIAL_HUGGINGFACE_ROUTES), "unapproved human review model/profile policy")
    return manifest, launch, profile


def verify_public_api(uri, source_sha):
    import requests
    require(isinstance(uri, str) and re.fullmatch(r"https://[a-z0-9.-]+\.run\.app", uri), "invalid observed API URL")
    session = requests.Session()
    version = session.get(uri + "/version", timeout=15, allow_redirects=False)
    require(version.status_code == 200 and version.json().get("source_sha") == source_sha and version.json().get("mode") == "production", "public API source/mode mismatch")
    ready = session.get(uri + "/health/ready", timeout=15, allow_redirects=False)
    require(ready.status_code == 200 and ready.json().get("status") == "ready" and ready.json().get("mode") == "production", "named SQL/object readiness failed")
    denied = session.get(uri + "/v1/session", timeout=15, allow_redirects=False)
    require(denied.status_code in {401, 403}, "anonymous protected session was not denied")


def verify_imported_cohort(google, manifest, launch, actor_uid):
    from specimen_digitization.application.production import GcsBlobs, SqlConnectRepository, actor_uid as actor_context
    from google.cloud import storage
    from specimen_digitization.application.worker_launch import PilotAdmission
    # Bypass GcsBlobs' default constructor because it discovers ADC independently.
    # Both SQL and generation-pinned graph reads use this admitted job's session.
    blobs = GcsBlobs.__new__(GcsBlobs)
    blobs.bucket = storage.Client(project=PROJECT, credentials=google.credentials,
                                  _http=google.session).bucket(f"{PROJECT}.firebasestorage.app")
    repo = SqlConnectRepository(session=google.session, graph_blobs=blobs)
    members = repo.memberships(actor_uid)
    require(any(m["organization_id"] == launch.scope.organization_id and m["collection_id"] == launch.scope.collection_id
                and m["role"] in {"admin", "manager", "reviewer", "operator"} and not m["can_view_sensitive"] for m in members), "verified nonsensitive collection membership required")
    admission = PilotAdmission(repo, launch)
    require(getattr(launch, "stage_cost_reservations", None) is not None, "complete stage cost reservations required")
    token = actor_context.set(actor_uid)
    try:
        for item in manifest.specimens:
            record = repo.get(launch.scope, item.specimen_id)
            require(admission.binding_matches(record) and record.asset.size_bytes == item.application_source.size_bytes,
                    "imported specimen generation or run binding mismatch")
            execution = record.run.profile.execution
            require(execution.stage_cost_reservations == launch.stage_cost_reservations
                    and execution.approved_cost_limit_micros is not None
                    and execution.approved_cost_limit_micros <= launch.per_specimen_cost_limit_micros,
                    "persisted run budget differs from the immutable launch")
    finally:
        actor_context.reset(token)



def verify_runtime_template(observed, expected, *, role):
    require(observed.get("name") == expected["name"], "wrong runtime resource")
    template = observed.get("template", {})
    wanted = expected["template"]
    if role == "worker":
        require(template.get("taskCount") == wanted["taskCount"] and template.get("parallelism") == wanted["parallelism"], "worker task count changed")
        template, wanted = template.get("template", {}), wanted["template"]
        require(template.get("maxRetries", 0) == 0, "worker platform retries enabled")
    else:
        require(observed.get("invokerIamDisabled", False) is False and observed.get("scaling", {}).get("minInstanceCount", 0) == 0,
                "runtime invoker check or minimum changed")
        require(observed.get("scaling", {}).get("maxInstanceCount") == expected["scaling"]["maxInstanceCount"],
                "runtime total service instance cap changed")
        require(template.get("executionEnvironment") == wanted["executionEnvironment"] == "EXECUTION_ENVIRONMENT_GEN2",
                "runtime execution environment changed")
        actual_scaling = template.get("scaling", {})
        require(actual_scaling.get("minInstanceCount", 0) == 0 and actual_scaling.get("maxInstanceCount") == wanted["scaling"]["maxInstanceCount"], "runtime instance cap changed")
        require(template.get("maxInstanceRequestConcurrency") == wanted["maxInstanceRequestConcurrency"], "runtime concurrency changed")
    require(template.get("serviceAccount") == wanted["serviceAccount"] and template.get("timeout") == wanted["timeout"], "runtime identity or timeout changed")
    actual_containers = template.get("containers", [])
    require(len(actual_containers) == len(wanted["containers"]) == 1, "unexpected runtime sidecar")
    actual, desired = actual_containers[0], wanted["containers"][0]
    require(actual.get("image") == desired["image"] and actual.get("command", []) == []
            and actual.get("args", []) == desired.get("args", []), "runtime image or entrypoint changed")
    require(actual.get("resources", {}).get("limits") == desired["resources"]["limits"], "runtime CPU or memory changed")
    if role != "worker":
        require(actual.get("resources", {}).get("cpuIdle") is True
                and actual.get("resources", {}).get("startupCpuBoost", False) is False,
                "runtime billing or startup CPU policy changed")
    require(actual.get("env", []) == desired.get("env", []) and actual.get("volumeMounts", []) == desired.get("volumeMounts", []), "runtime environment or mounts changed")
    require(template.get("volumes", []) == wanted.get("volumes", []), "runtime volume definition changed")

def activation_worker(body, plan, packet, *, now=None):
    """Bind one immutable cohort execution; the Cloud Run token is never random."""
    activation = plan["activation"]
    _, launch, _ = validate_activation_inputs(plan, packet, now=now)
    task = body["template"]["template"]
    container = task["containers"][0]
    now = time.time() if now is None else now
    maximum = min(1800, int(launch.expires_at.timestamp() - now - 10))
    require(maximum > 135, "no bounded worker window remains")
    task["timeout"] = f"{maximum}s"
    container["args"] = ["--mode", "production", "--materialize-config", "--evidence-only", "--launch-policy", "/inputs/launch/launch.json",
                         "--source-manifest", "/inputs/manifest/manifest.json", "--evidence-profile", "/inputs/profile/profile.json",
                         "--max-seconds", str(min(1500, maximum - 10))]
    task["volumes"].append(secret_volume("profile", activation["profile_secret"], "profile.json"))
    container["volumeMounts"].append({"name": "profile", "mountPath": "/inputs/profile"})
    values = {"SPECIMEN_APPROVED_INFERENCE": "true", "SPECIMEN_APPROVED_EVIDENCE_PILOT": "true",
              "SPECIMEN_HF_SECRET_RESOURCE": activation["hf_secret"], "SPECIMEN_WORKER_ACTOR_UID": activation["actor_uid"],
              "SPECIMEN_SAM3_REVISION": SAM_REVISION, "SPECIMEN_SAM3_ENDPOINT": plan["sam"]["audience"]}
    container["env"].extend({"name": k, "value": v} for k, v in sorted(values.items()))
    container["env"].append(env_secret("HF_TOKEN", activation["hf_secret"]))
    body["runExecutionToken"] = "pilot-" + packet["pilot"]["manifest_sha256"][:24]
    return body


def activate(google, plan, output):
    packet = google.packet
    manifest, launch, _ = validate_activation_inputs(plan, packet)
    prepared = plan["activation"]["prepared_receipt"]
    with tempfile.TemporaryDirectory() as folder:
        checked(["gh", "run", "download", str(prepared["run_id"]), "--repo", REPOSITORY, "--name",
                 f"runtime-receipt-{packet['source_sha']}-{prepared['run_attempt']}", "--dir", folder])
        receipt_path = Path(folder) / "runtime-receipt.json"
        raw = verified_receipt_bytes(receipt_path, prepared["sha256"], packet["source_sha"], "runtime-release.yml")
        receipt = strict_json(raw)
    require(receipt.get("version") == "runtime-prepared/v1" and receipt.get("source_sha") == packet["source_sha"]
            and receipt.get("run_id") == prepared["run_id"] and receipt.get("run_attempt") == prepared["run_attempt"]
            and receipt.get("worker_executed") is False, "prepared runtime receipt is not usable for first activation")
    google.registry_login()
    exact_keys(receipt["images"], {"api", "worker", "sam"}, "prepared images")
    for role, image in receipt["images"].items():
        require(isinstance(image, str) and IMAGE.fullmatch(image) and f"/{role}@sha256:" in image, "invalid prepared image")
        verify_attestation("oci://" + image, packet["source_sha"], "runtime-release.yml")
    verify_data_receipt(plan, packet, google)
    api = google.request("run", "GET", f"{PREFIX}/services/specimen-api")
    require(api.get("etag") == plan["api"]["expected_etag"] and api.get("latestReadyRevision") == receipt["resources"]["api"]["revision"], "API changed after preparation")
    bodies = resource_bodies(plan, packet, receipt["images"], str(packet["release_run_id"]), str(packet["release_run_attempt"]))
    verify_runtime_template(api, bodies["api"], role="api")
    revision = google.request("run", "GET", api["latestReadyRevision"])
    require(revision.get("containers", [{}])[0].get("image") == receipt["images"]["api"], "native API revision image differs")
    statuses = api.get("trafficStatuses", [])
    uri = next((v["uri"] for v in statuses if v.get("tag") == "candidate" and v.get("uri")), api.get("uri"))
    verify_public_api(uri, packet["source_sha"])
    verify_imported_cohort(google, manifest, launch, plan["activation"]["actor_uid"])
    sam = bodies["sam"]
    current = google.request("run", "GET", sam["name"], missing=True)
    require((current is None and plan["sam"]["expected_etag"] is None) or current and current.get("etag") == plan["sam"]["expected_etag"], "SAM changed after admission")
    if current is None:
        operation = google.request("run", "POST", f"{PREFIX}/services", body=sam, params={"serviceId": "specimen-sam"})
        google.wait("run", operation, maximum_seconds=900)
    else:
        verify_runtime_template(current, sam, role="sam")
    observed = google.request("run", "GET", sam["name"])
    require(observed.get("terminalCondition", {}).get("state") == "CONDITION_SUCCEEDED" and observed.get("reconciling") is False,
            "native SAM model startup not ready")
    require(plan["sam"]["audience"] in observed.get("urls", []) or observed.get("uri") == plan["sam"]["audience"], "native SAM URL differs from configured audience")
    native = google.request("run", "GET", observed["latestReadyRevision"])
    require(native.get("containers", [{}])[0].get("image") == receipt["images"]["sam"], "native SAM revision/image mismatch")
    verify_runtime_template(observed, sam, role="sam")
    # Keep invoker IAM default-deny. Only bootstrap may grant the worker the
    # exact SAM invocation permission; this path never changes an IAM policy.
    policy = google.run_iam_policy(sam["name"])
    invokers = {member for binding in policy.get("bindings", []) if binding.get("role") == "roles/run.invoker" for member in binding.get("members", [])}
    require(invokers == {f"serviceAccount:specimen-worker-runtime@{PROJECT}.iam.gserviceaccount.com"}, "exact worker-only SAM invocation binding required")
    existing = google.request("run", "GET", f"{PREFIX}/jobs/specimen-worker", missing=True)
    if existing is not None:
        require(existing.get("etag") == plan["worker"]["expected_etag"] and existing.get("executionCount", 0) == 0,
                "worker state changed or the single execution was already used")
    else:
        require(plan["worker"]["expected_etag"] is None, "expected worker no longer exists")
    promoted = google.request("run", "PATCH", api["name"], body={"name": api["name"], "etag": api["etag"],
        "traffic": [{"type": "TRAFFIC_TARGET_ALLOCATION_TYPE_REVISION", "revision": api["latestReadyRevision"].split("/")[-1], "percent": 100}]}, params={"updateMask": "traffic"})
    google.wait("run", promoted)
    current_api = google.request("run", "GET", api["name"])
    verify_public_api(current_api["uri"], packet["source_sha"])
    worker = activation_worker(bodies["worker"], plan, packet)
    if existing is None:
        operation = google.request("run", "POST", f"{PREFIX}/jobs", body=worker, params={"jobId": "specimen-worker"})
    else:
        operation = google.request("run", "PATCH", worker["name"], body=worker)
    # runExecutionToken names one cohort execution. Never call jobs:run or
    # generate a new token after an ambiguous response.
    try:
        google.wait("run", operation, maximum_seconds=1800)
    finally:
        observation = google.request("run", "GET", worker["name"])
        output.write_text(json.dumps({"version": "runtime-human-review/v1", "source_sha": packet["source_sha"],
            "run_id": packet["release_run_id"], "run_attempt": packet["release_run_attempt"],
            "api_revision": current_api["latestReadyRevision"], "sam_revision": observed["latestReadyRevision"],
            "worker_execution": observation.get("latestCreatedExecution"), "release_accepted": False,
            "native_reading_and_human_review_acceptance_pending": True}, sort_keys=True) + "\n")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plane", choices=["runtime", "runtime-build"], required=True)
    parser.add_argument("--packet", type=Path, required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare-inputs", action="store_true")
    action.add_argument("--admit", action="store_true")
    action.add_argument("--publish-role", choices=["api", "worker", "sam"])
    action.add_argument("--deploy", action="store_true")
    parser.add_argument("--receipts", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.prepare_inputs:
            materialize_inputs(args.packet.parent, dict(os.environ))
        if args.publish_role:
            publication.bind_child(read_packet(args.packet, dict(os.environ)))
        packet = admit(args.packet, args.plane)
        if args.publish_role:
            require(args.plane == "runtime-build" and args.output is not None, "build identity and output required")
            publish_role(args.packet, args.publish_role, args.output)
        elif args.deploy:
            require(args.plane == "runtime" and args.output is not None and args.receipts is not None, "release inputs required")
            deploy(args.packet, args.receipts, args.output)
        else:
            plan = validate_plan(read_bound_plan(args.packet.parent / "plan.json", packet), packet)
            with Path(os.environ["GITHUB_OUTPUT"]).open("a") as handle:
                handle.write(f"provider={packet['identity']['provider']}\nphase={plan['version']}\n")
            print("Protected admission passed; cloud readiness and product acceptance are separate gates.")
    except (ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        # Never echo packet values, identity claims, credentials or API bodies.
        raise SystemExit(f"Runtime release blocked ({type(exc).__name__}); inspect the named admission gate privately.") from None


if __name__ == "__main__":
    main()
