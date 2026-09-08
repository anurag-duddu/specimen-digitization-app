"""Runtime release guards are exercised without credentials or cloud changes."""
import copy
from datetime import datetime, timezone
import hashlib
import importlib
import json
from pathlib import Path
import sys
from uuid import UUID

import pytest

sys.path.insert(0, str(Path(__file__).parent))
M = importlib.import_module("deploy_runtime")
SHA = "a" * 40
NOW = 1788890400


def plan():
    return {
        "version": "runtime-prepare/v1", "source_sha": SHA,
        "data_receipt": {"sha256": "1" * 64, "run_id": 123, "run_attempt": 1, "source_sha": SHA},
        "api": {"expected_etag": None, "previous_revision": None, "environment": {
            "SPECIMEN_FIREBASE_PROJECT": "specimen-digitization", "SPECIMEN_FIREBASE_PROJECT_NUMBER": "123456789",
            "SPECIMEN_FIREBASE_APP_IDS": "1:123456789:web:abcd",
            "SPECIMEN_SQL_LOCATION": "us-east4", "SPECIMEN_SQL_SERVICE": "specimen-digitization-service",
            "SPECIMEN_SQL_CONNECTOR": "specimen-server", "SPECIMEN_GCS_BUCKET": "specimen-digitization.firebasestorage.app",
            "SPECIMEN_CORS_ORIGINS": "https://specimen-digitization.web.app", "SPECIMEN_READINESS_OBJECT": "application/sha256/" + "a" * 64,
            "SPECIMEN_READINESS_GENERATION": "123"}},
        "worker": {"expected_etag": None, "launch_secret": "projects/specimen-digitization/secrets/pilot-launch/versions/1",  # pragma: allowlist secret (resource ID only)
                   "manifest_secret": "projects/specimen-digitization/secrets/pilot-manifest/versions/1",  # pragma: allowlist secret (resource ID only)
                   "launch_sha256": "2" * 64, "manifest_sha256": "3" * 64},
        "sam": {"expected_etag": None, "previous_revision": None, "expires_at_unix": NOW + 1800,
                "manifest_secret": "projects/specimen-digitization/secrets/pilot-manifest/versions/1",  # pragma: allowlist secret (resource ID only)
                "manifest_sha256": "3" * 64,
                "checkpoint_prefix": "application/sha256/" + "4" * 64 + "/sam3-cache", "checkpoint_sha256": "4" * 64,
                "audience": "https://specimen-sam-123456789.us-east4.run.app"},
    }


def packet():
    return {"source_sha": SHA, "identity": {"project_number": "123456789"},
            "pilot": {"manifest_sha256": "3" * 64}, "expires_at_unix": NOW + 2000,
            "authorization_sha256": "4" * 64}


def test_accept_preparation_without_claiming_native_or_product_acceptance():
    assert M.validate_plan(plan(), packet(), now=NOW)["version"] == "runtime-prepare/v1"


@pytest.mark.parametrize("change", [
    lambda p: p.update(source_sha="b" * 40),
    lambda p: p.update(version="run-paid-models"),
    lambda p: p["api"]["environment"].update(HF_TOKEN="forbidden"),
    lambda p: p["api"]["environment"].update(SPECIMEN_SQL_SERVICE="unapproved"),
    lambda p: p["api"]["environment"].update(SPECIMEN_FIREBASE_PROJECT_NUMBER="987654321"),
    lambda p: p["api"]["environment"].update(SPECIMEN_CORS_ORIGINS="https://unapproved.example"),
    lambda p: p["api"].update(previous_revision="foreign-revision"),
    lambda p: p["sam"].update(expires_at_unix=NOW + 3601),
    lambda p: p["sam"].update(expires_at_unix=NOW + 120),
    lambda p: p["sam"].update(audience="http://localhost:8000"),
    lambda p: p["sam"].update(hf_secret="projects/other/secrets/hf/versions/1"),
    lambda p: p["worker"].update(launch_secret="projects/specimen-digitization/secrets/launch/versions/latest"),
    lambda p: p["worker"].update(manifest_sha256="5" * 64),
    lambda p: p["worker"].update(run=True),
    lambda p: p["data_receipt"].update(source_sha="5" * 40),
])
def test_runtime_input_scope_and_deadlines_fail_closed(change):
    p = plan()
    change(p)
    with pytest.raises(ValueError):
        M.validate_plan(p, packet(), now=NOW)


def test_generated_resources_have_exact_caps_and_no_worker_execution_or_public_iam():
    p = plan()
    images = {role: f"us-east4-docker.pkg.dev/specimen-digitization/specimen-runtime/{role}@sha256:" + "6" * 64
              for role in ("api", "worker", "sam")}
    bodies = M.resource_bodies(p, packet(), images, "123", "1", now=NOW)
    api, worker, sam = bodies["api"], bodies["worker"], bodies["sam"]
    assert api["template"]["scaling"] == {"minInstanceCount": 0, "maxInstanceCount": 2}
    assert api["template"]["containers"][0]["resources"]["limits"] == {"cpu": "1", "memory": "1Gi"}
    assert sam["template"]["scaling"] == {"minInstanceCount": 0, "maxInstanceCount": 1}
    assert sam["template"]["containers"][0]["resources"]["limits"] == {"cpu": "4", "memory": "16Gi"}
    assert worker["template"]["taskCount"] == worker["template"]["parallelism"] == 1
    assert worker["template"]["template"]["timeout"] == "1800s"
    assert worker["template"]["template"]["maxRetries"] == 0
    assert "--check-config" in worker["template"]["template"]["containers"][0]["args"]
    assert not any("ExecutionToken" in key for key in worker)
    assert all("iam" not in key.lower() for body in bodies.values() for key in body)


def test_no_mutable_or_cross_role_images_and_no_previous_traffic_change():
    p = plan()
    p["api"].update(expected_etag="existing", previous_revision="specimen-api-old")
    images = {role: f"us-east4-docker.pkg.dev/specimen-digitization/specimen-runtime/{role}@sha256:" + "6" * 64
              for role in ("api", "worker", "sam")}
    bodies = M.resource_bodies(p, packet(), images, "123", "1", now=NOW)
    assert bodies["api"]["traffic"][0] == {"type": "TRAFFIC_TARGET_ALLOCATION_TYPE_REVISION", "revision": "specimen-api-old", "percent": 100}
    assert bodies["api"]["traffic"][1]["percent"] == 0
    for role in images:
        changed = copy.deepcopy(images)
        changed[role] = "foreign/image:latest"
        with pytest.raises(ValueError):
            M.resource_bodies(p, packet(), changed, "123", "1", now=NOW)


def test_first_api_preparation_does_not_require_post_intake_manifest_or_model_startup():
    p = plan()
    p["worker"] = p["sam"] = None
    assert M.validate_plan(p, packet(), now=NOW)
    images = {role: f"us-east4-docker.pkg.dev/specimen-digitization/specimen-runtime/{role}@sha256:" + "6" * 64
              for role in ("api", "worker", "sam")}
    assert set(M.resource_bodies(p, packet(), images, "123", "1", now=NOW)) == {"api"}


def test_activation_cannot_accept_missing_ready_cohort_or_launch_and_receipt():
    p = plan()
    p["version"] = "runtime-activate/v1"
    with pytest.raises(ValueError, match="activation"):
        M.validate_plan(p, packet(), now=NOW)


@pytest.mark.parametrize("change", [lambda p: p["api"].update(expected_etag=123),
                                      lambda p: p["api"].update(previous_revision="specimen-sam-other"),
                                      lambda p: p["api"].update(expected_etag="existing")])
def test_api_only_preparation_keeps_expected_revision_guards(change):
    p = plan()
    p["sam"] = p["worker"] = None
    change(p)
    with pytest.raises(ValueError):
        M.validate_plan(p, packet(), now=NOW)


@pytest.mark.parametrize("change", [
    lambda b: b["template"]["scaling"].update(maxInstanceCount=2),
    lambda b: b["template"]["containers"][0]["resources"].update(cpuIdle=False),
    lambda b: b["template"]["containers"][0]["resources"].update(startupCpuBoost=True),
    lambda b: b["template"]["containers"][0]["env"].append({"name": "HF_TOKEN", "value": "not-allowed"}),
    lambda b: b["template"].update(serviceAccount="foreign@example.com"),
    lambda b: b.update(invokerIamDisabled=True),
    lambda b: b.update(scaling={"minInstanceCount": 0, "maxInstanceCount": 50}),
    lambda b: b["template"].update(executionEnvironment="EXECUTION_ENVIRONMENT_GEN1"),
])
def test_native_template_verification_rejects_capacity_credentials_or_identity_drift(change):
    images = {role: f"{M.REGISTRY}/{role}@sha256:" + "6" * 64 for role in ("api", "worker", "sam")}
    expected = M.resource_bodies(plan(), packet(), images, "123", "1", now=NOW)["sam"]
    observed = copy.deepcopy(expected)
    M.verify_runtime_template(observed, expected, role="sam")
    change(observed)
    with pytest.raises(ValueError):
        M.verify_runtime_template(observed, expected, role="sam")


def test_service_caps_bound_total_capacity_across_old_and_candidate_revisions():
    images = {role: f"{M.REGISTRY}/{role}@sha256:" + "6" * 64 for role in ("api", "worker", "sam")}
    bodies = M.resource_bodies(plan(), packet(), images, "123", "1", now=NOW)
    for role, maximum in (("api", 2), ("sam", 1)):
        assert bodies[role]["scaling"] == {"minInstanceCount": 0, "maxInstanceCount": maximum}


def activation_fixture(monkeypatch):
    from specimen_digitization.application.collection_profiles import insects_registry, SegmentationSettings
    from specimen_digitization.application.sam3_effect import canonical_bytes
    p, authority = plan(), packet()
    p["version"] = "runtime-activate/v1"
    scope = {"organization_id": str(UUID(int=100)), "collection_id": str(UUID(int=200))}
    profile = insects_registry().profiles[0].model_copy(update={"collection_id": scope["collection_id"], "segmentation_settings": SegmentationSettings(prompt="label")})
    profile_raw = profile.model_dump_json()
    files = {"model.safetensors": "e" * 64, "config.json": "d" * 64}
    p["sam"]["checkpoint_sha256"] = hashlib.sha256(canonical_bytes(files)).hexdigest()
    p["sam"]["checkpoint_prefix"] = "application/sha256/" + p["sam"]["checkpoint_sha256"] + "/sam3-cache"
    items = []
    for n in range(1, 11):
        sha = f"{n:064x}"
        items.append({"ordinal": n, "specimen_id": str(UUID(int=n)), **scope,
                      "source_objects": [{"bucket": M.PROJECT + ".firebasestorage.app", "object_name": f"synthetic/{n}.jpg",
                                          "generation": "11", "sha256": sha, "size_bytes": 100}],
                      "application_source": {"blob_ref": sha + ":22", "sha256": sha, "size_bytes": 100, "source_object_index": 0}})
    manifest = {"schema_version": "specimen-pilot/v1", "status": "ready", "project_id": M.PROJECT,
                "authorization_reference": "synthetic-test-only", "selection": {"order": "explicit_source_order", "source_inventory_sha256": authority["pilot"]["manifest_sha256"]}, "specimens": items}
    manifest_raw = json.dumps(manifest)
    manifest_sha = hashlib.sha256(manifest_raw.encode()).hexdigest()
    p["sam"]["manifest_sha256"] = p["worker"]["manifest_sha256"] = manifest_sha
    launch = {"version": "authorized-ten-v1", "evidence_only": True, "evidence_profile_sha256": hashlib.sha256(profile_raw.encode()).hexdigest(),
              "sam3_checkpoint_files": files, "source_manifest_sha256": manifest_sha, "authorization_reference": "synthetic-test-only",
              "scope": scope, "specimens": [{"specimen_id": s["specimen_id"], "asset_sha256": s["application_source"]["sha256"],
                                              "blob_ref": s["application_source"]["blob_ref"]} for s in items],
              "expires_at": datetime.fromtimestamp(NOW + 1500, timezone.utc).isoformat(), "total_cost_limit_micros": 10000,
              "per_specimen_cost_limit_micros": 1000, "per_specimen_call_limit": 32, "per_specimen_token_limit": 10000,
              "effect_timeout_seconds": 120, "hf_secret_resource": f"projects/{M.PROJECT}/secrets/pilot-hf/versions/1",
              "stage_cost_reservations": {"version": "stage-cost-reservations-v1", "cost_micros": {
                  "segment": 100, "transcribe:handwriting-qwen": 100, "transcribe:handwriting-muse": 100}}}
    launch_raw = json.dumps(launch)
    p["worker"]["launch_sha256"] = hashlib.sha256(launch_raw.encode()).hexdigest()
    p["activation"] = {"manifest_bytes": manifest_raw, "launch_bytes": launch_raw, "profile_bytes": profile_raw,
                       "prepared_receipt": {"run_id": 123, "run_attempt": 1, "sha256": "a" * 64}, "actor_uid": "test-actor",
                       "profile_secret": f"projects/{M.PROJECT}/secrets/pilot-profile/versions/1", "hf_secret": launch["hf_secret_resource"],
                       "human_review_authorization_sha256": "f" * 64}
    authority["budget"] = {"reservations": [{"category": "provider", "ceiling_micros": 10000}, {"category": "sam", "ceiling_micros": 10000}]}
    monkeypatch.setenv("RELEASE_HUMAN_REVIEW_AUTHORIZATION_SHA256", "f" * 64)
    return p, authority


def test_one_activation_uses_real_contracts_one_stable_execution_and_offline_sam(monkeypatch):
    p, authority = activation_fixture(monkeypatch)
    manifest, launch, profile = M.validate_activation_inputs(p, authority, now=NOW)
    assert len(manifest.specimens) == 10 and launch.evidence_only and profile.state == "draft"
    images = {role: f"{M.REGISTRY}/{role}@sha256:" + "6" * 64 for role in ("api", "worker", "sam")}
    bodies = M.resource_bodies(p, authority, images, "123", "2", now=NOW)
    worker = M.activation_worker(bodies["worker"], p, authority, now=NOW)
    assert worker["runExecutionToken"] == "pilot-" + authority["pilot"]["manifest_sha256"][:24]
    assert worker["template"]["template"]["maxRetries"] == 0
    assert int(worker["template"]["template"]["timeout"][:-1]) <= 1800
    env = {v["name"]: v.get("value") for v in bodies["sam"]["template"]["containers"][0]["env"]}
    assert "HF_TOKEN" not in env and env["HF_HUB_OFFLINE"] == "1"


@pytest.mark.parametrize("change", [lambda p: p["sam"].update(checkpoint_sha256="1" * 64),
                                      lambda p: p["sam"].update(checkpoint_prefix="application/sha256/" + "1" * 64 + "/sam3-cache")])
def test_activation_binds_actual_checkpoint_map_and_cache_identity(monkeypatch, change):
    p, authority = activation_fixture(monkeypatch)
    p["sam"]["checkpoint_prefix"] = "application/sha256/" + p["sam"]["checkpoint_sha256"] + "/sam3-cache"
    change(p)
    with pytest.raises(ValueError, match="checkpoint"):
        M.validate_activation_inputs(p, authority, now=NOW)


def test_runtime_prepared_receipt_rejects_attested_replacement_bytes(tmp_path, monkeypatch):
    from types import SimpleNamespace
    p, authority = activation_fixture(monkeypatch)
    original = b'{"version":"runtime-prepared/v1","source_sha":"' + SHA.encode() + b'"}'
    replacement = b'{"different_signed_subject":true}'
    p["activation"]["prepared_receipt"]["sha256"] = hashlib.sha256(original).hexdigest()
    def download(command, **kw):
        (Path(command[-1]) / "runtime-receipt.json").write_bytes(original)
    def verify(path, *args):
        Path(path).write_bytes(replacement)
        result = json.dumps([{"verificationResult": {"statement": {"subject": [{"digest": {"sha256": hashlib.sha256(replacement).hexdigest()}}]}}}])
        # Restoring the original file must not hide the different signed subject.
        Path(path).write_bytes(original)
        return result
    monkeypatch.setattr(M, "checked", download)
    monkeypatch.setattr(M, "verify_attestation", verify)
    monkeypatch.setattr(M.time, "time", lambda: NOW)
    with pytest.raises(ValueError, match="subject"):
        M.activate(SimpleNamespace(packet=authority), p, tmp_path / "out.json")


def test_activation_rechecks_api_caps_before_public_warmup_or_new_runtime_effects(tmp_path, monkeypatch):
    from types import SimpleNamespace
    p, authority = activation_fixture(monkeypatch)
    authority.update(release_run_id=123, release_run_attempt=2)
    p["api"].update(expected_etag="observed", previous_revision="specimen-api-old")
    images = {role: f"{M.REGISTRY}/{role}@sha256:" + "6" * 64 for role in ("api", "worker", "sam")}
    observed = M.resource_bodies(p, authority, images, "123", "2", now=NOW)["api"]
    observed.update(etag="observed", latestReadyRevision=f"{M.PREFIX}/services/specimen-api/revisions/specimen-api-old",
                    uri="https://specimen-api-123456789.us-east4.run.app")
    observed["scaling"]["maxInstanceCount"] = 50
    receipt = {"version": "runtime-prepared/v1", "source_sha": SHA, "run_id": 123, "run_attempt": 1,
               "worker_executed": False, "images": images, "resources": {"api": {"revision": observed["latestReadyRevision"]}}}
    def request(api, method, resource, **kw):
        assert method == "GET"
        return {"containers": [{"image": images["api"]}]} if "/revisions/" in resource else observed
    google = SimpleNamespace(packet=authority, registry_login=lambda: None, request=request)
    monkeypatch.setattr(M.time, "time", lambda: NOW)
    monkeypatch.setattr(M, "checked", lambda *a, **kw: None)
    monkeypatch.setattr(M, "verified_receipt_bytes", lambda *a: json.dumps(receipt).encode())
    monkeypatch.setattr(M, "verify_attestation", lambda *a: None)
    monkeypatch.setattr(M, "verify_data_receipt", lambda *a: None)
    monkeypatch.setattr(M, "verify_public_api", lambda *a: pytest.fail("never warm an oversized API"))
    with pytest.raises(ValueError, match="service instance cap"):
        M.activate(google, p, tmp_path / "out.json")
