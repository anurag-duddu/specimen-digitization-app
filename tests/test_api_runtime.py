"""Credential-free runtime contracts; these are not live Firebase auth evidence."""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
import pytest

from specimen_digitization.application.api import create_app
from specimen_digitization.application import runtime_auth, runtime_config
from specimen_digitization.application.runtime_health import (
    DependencyReadiness,
    cloud_probe,
    install_health,
)


def config_env():
    return {
        "SPECIMEN_FIREBASE_PROJECT": "specimen-digitization",
        "SPECIMEN_FIREBASE_PROJECT_NUMBER": "123",
        "SPECIMEN_SQL_LOCATION": "us-east4",
        "SPECIMEN_SQL_SERVICE": "specimen-digitization-service",
        "SPECIMEN_SQL_CONNECTOR": "specimen-server",
        "SPECIMEN_GCS_BUCKET": "specimen-digitization.firebasestorage.app",
        "SPECIMEN_FIREBASE_APP_IDS": "1:123:web:abc123",
        "SPECIMEN_CORS_ORIGINS": "https://specimen-digitization.web.app",
        "SPECIMEN_READINESS_OBJECT": "synthetic-contract/metadata-only",
        "SPECIMEN_READINESS_GENERATION": "123",
    }


@pytest.mark.parametrize(
    "key,value",
    [
        ("FIREBASE_AUTH_EMULATOR_HOST", "127.0.0.1:9099"),
        ("STORAGE_EMULATOR_HOST", "http://127.0.0.1:9199"),
        ("SPECIMEN_SQL_EMULATOR_HOST", "127.0.0.1:9499"),
        ("HF_TOKEN", "fixture-not-a-credential"),
        ("SPECIMEN_APPROVED_INFERENCE", "true"),
        ("SPECIMEN_FIREBASE_PROJECT", "wrong-project"),
        ("GOOGLE_CLOUD_PROJECT", "wrong-project"),
        ("SPECIMEN_SQL_CONNECTOR", "../other"),
        ("SPECIMEN_GCS_BUCKET", "other-bucket"),
        ("SPECIMEN_FIREBASE_APP_IDS", ""),
        ("SPECIMEN_CORS_ORIGINS", "*"),
        ("SPECIMEN_CORS_ORIGINS", "https://specimen-digitization.web.app/"),
        ("SPECIMEN_CORS_ORIGINS", "https://fixture-user@example.invalid"),
        ("SPECIMEN_CORS_ORIGINS", "http://localhost:3000"),
        ("SPECIMEN_READINESS_GENERATION", "0"),
        ("SPECIMEN_READINESS_OBJECT", ""),
        ("PORT", "65536"),
        ("PORT", "no"),
    ],
)
def test_production_config_denials(key, value):
    with pytest.raises(ValueError):
        runtime_config.RuntimeConfig.from_env(dict(config_env(), **{key: value}))


def test_config_and_immutable_provenance(tmp_path, monkeypatch):
    assert runtime_config.RuntimeConfig.from_env(config_env()).port == 8080
    build = tmp_path / "build.json"
    monkeypatch.setattr(runtime_config, "BUILD_FILE", build)
    with pytest.raises(ValueError, match="provenance"):
        runtime_config.build_provenance(required=True)
    assert runtime_config.build_provenance()["source_sha"] == "unbuilt"
    build.write_text(json.dumps({"source_sha": "a" * 40}))
    monkeypatch.setenv("SOURCE_SHA", "b" * 40)
    assert runtime_config.build_provenance(True)["source_sha"] == "a" * 40
    build.write_text('{"source_sha":"unbuilt"}')
    with pytest.raises(ValueError):
        runtime_config.build_provenance(True)


def verified_sdk(monkeypatch):
    id_token = Mock(return_value={"uid": "fixture-user", "email": "fixture@fieldmuseum.org", "email_verified": True})
    app_token = Mock(
        return_value={
            "app_id": "1:123:web:abc123",
            "iss": "https://firebaseappcheck.googleapis.com/123",
        }
    )
    monkeypatch.setattr(runtime_auth.auth, "verify_id_token", id_token)
    monkeypatch.setattr(runtime_auth.app_check, "verify_token", app_token)
    app = SimpleNamespace(project_id="123")
    verifier = runtime_auth.firebase_verifier(app, ("1:123:web:abc123",), app)
    return verifier, id_token, app_token, app


def test_sdk_revocation_flag_and_email_policy(monkeypatch):
    verify, identity, appcheck, app = verified_sdk(monkeypatch)
    assert verify("id-fixture", "app-fixture") == "fixture-user"
    identity.assert_called_once_with("id-fixture", app=app, check_revoked=True)
    appcheck.assert_called_once_with("app-fixture", app=app)
    identity.return_value = {"uid": "fixture-user", "email_verified": False}
    with pytest.raises(runtime_auth.EmailVerificationRequired):
        verify("id-fixture", "app-fixture")
    identity.return_value = {"uid": "fixture-user"}
    with pytest.raises(runtime_auth.EmailVerificationRequired):
        verify("id-fixture", "app-fixture")


@pytest.mark.parametrize(
    "failure",
    [
        "revoked",
        "disabled",
        "expired",
        "wrong-project",
        "bad-app",
        "missing-app",
        "missing-id",
    ],
)
def test_sdk_failure_denies_without_membership(monkeypatch, failure):
    verify, identity, appcheck, _ = verified_sdk(monkeypatch)
    if failure in {"revoked", "disabled", "expired", "wrong-project"}:
        # Inject an SDK verification failure; not a fabricated valid signed token.
        identity.side_effect = ValueError(failure)
    if failure == "bad-app":
        appcheck.return_value = {"app_id": "1:123:web:deaddead"}
    with pytest.raises(PermissionError):
        verify(
            "" if failure == "missing-id" else "id-fixture",
            "" if failure == "missing-app" else "app-fixture",
        )
    if failure in {"bad-app", "missing-app", "missing-id"}:
        identity.assert_not_called()


def production_fixture(verifier):
    memberships = Mock(return_value=[])
    app = create_app(
        mode="production",
        repository=SimpleNamespace(),
        blobs=SimpleNamespace(),
        adapters=SimpleNamespace(),
        identity_verifier=verifier,
        memberships=memberships,
        origins=["https://specimen-digitization.web.app"],
    )
    return TestClient(app), memberships


def test_http_origin_token_and_email_denials(monkeypatch):
    verify, identity, _, _ = verified_sdk(monkeypatch)
    client, memberships = production_fixture(verify)
    headers = {
        "Authorization": "Bearer id-fixture",
        "X-Firebase-AppCheck": "app-fixture",
    }
    assert client.get("/v1/session").status_code == 401
    assert (
        client.get(
            "/v1/session", headers=dict(headers, Origin="https://evil.example")
        ).status_code
        == 403
    )
    assert (
        client.get("/v1/session", headers=dict(headers, Origin="null")).status_code
        == 403
    )
    memberships.assert_not_called()
    identity.assert_not_called()
    response = client.options(
        "/v1/session",
        headers={
            "Origin": "https://specimen-digitization.web.app",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization,X-Firebase-AppCheck",
        },
    )
    assert response.status_code == 200
    assert (
        response.headers["access-control-allow-origin"]
        == "https://specimen-digitization.web.app"
    )
    response = client.get("/v1/session", headers=headers)
    assert response.status_code == 200 and response.json()["memberships"] == []
    assert response.headers["cache-control"] == "no-store"
    memberships.reset_mock()
    identity.return_value["email_verified"] = False
    response = client.get("/v1/session", headers=headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "email_verification_required"
    memberships.assert_not_called()
    assert client.get("/docs").status_code == 404


def test_health_does_not_confuse_liveness_with_dependencies():
    probe = Mock(side_effect=[False, True, RuntimeError("private-detail")])
    readiness = DependencyReadiness(probe, ttl=0)
    app = FastAPI()
    install_health(
        app, mode="production", provenance={"source_sha": "a" * 40}, readiness=readiness
    )
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
        probe.assert_not_called()
        assert client.get("/health/ready").status_code == 503
        assert client.get("/health/ready").status_code == 200
        result = client.get("/health/ready")
        assert result.status_code == 503 and "private-detail" not in result.text
        assert client.get("/version").json()["source_sha"] == "a" * 40
        assert result.headers["cache-control"] == "no-store"
    cached = DependencyReadiness(Mock(return_value=True))
    assert cached() and cached()
    cached.probe.assert_called_once()


def test_readiness_only_queries_and_reads_pinned_metadata():
    config = runtime_config.RuntimeConfig.from_env(config_env())
    session = Mock()
    session.post.return_value = SimpleNamespace(
        status_code=200, json=lambda: {"data": {}}
    )
    repository = SimpleNamespace(session=session, url="https://sql.example/connector")
    blobs = SimpleNamespace(bucket=Mock())
    assert cloud_probe(repository, blobs, config)()
    session.post.assert_called_once_with(
        "https://sql.example/connector:impersonateQuery",
        json={"operationName": "Readiness", "variables": {}},
        timeout=3,
    )
    blobs.bucket.blob.assert_called_once_with(config.readiness_object, generation=123)
    blobs.bucket.blob.return_value.reload.assert_called_once_with(
        timeout=3, retry=None, if_generation_match=123
    )
    blobs.bucket.reload.assert_not_called()
    blobs.bucket.blob.return_value.download_as_bytes.assert_not_called()
    session.post.return_value = SimpleNamespace(
        status_code=200, json=lambda: {"errors": ["no"]}
    )
    assert not cloud_probe(repository, blobs, config)()


def test_real_http_subprocess_shutdown(tmp_path):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = dict(
        os.environ,
        SPECIMEN_SYNTHETIC_TOKEN="local-fixture-only",
        LOGFIRE_SEND_TO_LOGFIRE="false",
    )
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "specimen_digitization.application.cli",
            "--mode",
            "synthetic",
            "--state-dir",
            str(tmp_path),
            "--port",
            str(port),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 20
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=1) as client:
            while time.monotonic() < deadline:
                assert proc.poll() is None, "server exited during startup"
                try:
                    response = client.get("/version")
                    if response.status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.05)
            else:
                pytest.fail("server startup deadline exceeded")
            assert response.json()["mode"] == "synthetic"
            assert client.get("/health/live").status_code == 200
            assert client.get("/health/ready").json()["scope"] == "local_fixture"
            assert client.get("/v1/session").status_code == 401
        start = time.monotonic()
        proc.terminate()
        proc.wait(timeout=10)
        assert time.monotonic() - start < 10
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)


def test_shutdown_watchdog_terminates_stuck_sync_request(tmp_path):
    """Actual SIGTERM while a sync handler cannot cooperate with cancellation."""
    script = tmp_path / "stuck_server.py"
    marker = tmp_path / "entered"
    script.write_text("""import time
from pathlib import Path
from fastapi import FastAPI
from specimen_digitization.application.runtime_server import BoundedServer
import uvicorn
import sys
app = FastAPI()
@app.get("/live")
def live():
    return {"live": True}
@app.get("/stuck")
def stuck():
    Path(sys.argv[2]).touch()
    time.sleep(120)
    return {}
BoundedServer(uvicorn.Config(app, host="127.0.0.1", port=int(sys.argv[1]), timeout_graceful_shutdown=1), hard_shutdown_seconds=2).run()
""")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    proc = subprocess.Popen(
        [sys.executable, str(script), str(port), str(marker)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    connection = None
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            assert proc.poll() is None
            try:
                if (
                    httpx.get(f"http://127.0.0.1:{port}/live", timeout=0.5).status_code
                    == 200
                ):
                    break
            except httpx.TransportError:
                pass
            time.sleep(0.05)
        else:
            pytest.fail("server did not start")
        connection = socket.create_connection(("127.0.0.1", port))
        connection.sendall(b"GET /stuck HTTP/1.1\r\nHost: localhost\r\n\r\n")
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert marker.exists()
        started = time.monotonic()
        proc.terminate()
        proc.wait(timeout=5)
        assert time.monotonic() - started < 4
    finally:
        if connection is not None:
            connection.close()
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)


def test_slow_probe_does_not_queue_other_readiness_requests():
    import threading

    entered, release = threading.Event(), threading.Event()

    def probe():
        entered.set()
        release.wait(timeout=5)
        return True

    readiness = DependencyReadiness(probe)
    thread = threading.Thread(target=readiness)
    thread.start()
    try:
        assert entered.wait(timeout=2)
        start = time.monotonic()
        assert readiness() is False
        assert time.monotonic() - start < 0.1
    finally:
        release.set()
        thread.join(timeout=2)
    assert readiness() is True


def test_real_app_check_sdk_crypto_numeric_audience(monkeypatch):
    """Local ephemeral signing key/JWKS fixture, no Google token or auth claim."""
    import firebase_admin
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from uuid import uuid4

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    app = firebase_admin.initialize_app(options={"projectId": "123"}, name=str(uuid4()))
    try:
        service = runtime_auth.app_check._get_app_check_service(app)
        monkeypatch.setattr(
            service._jwks_client,
            "get_signing_key_from_jwt",
            lambda _: SimpleNamespace(key=key.public_key()),
        )
        monkeypatch.setattr(
            runtime_auth.auth,
            "verify_id_token",
            lambda *args, **kwargs: {"uid": "fixture-user", "email": "fixture@fieldmuseum.org", "email_verified": True},
        )
        verify = runtime_auth.firebase_verifier(app, ("1:123:web:abc123",), app)
        claims = {
            "sub": "1:123:web:abc123",
            "aud": ["projects/123"],
            "iss": "https://firebaseappcheck.googleapis.com/123",
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
        }

        def signed(values, signing_key=key):
            return jwt.encode(
                values, signing_key, algorithm="RS256", headers={"kid": "local-fixture"}
            )

        assert verify("id-fixture", signed(claims)) == "fixture-user"
        for bad in (
            dict(claims, aud=["projects/specimen-digitization"]),
            dict(claims, aud=["projects/456"]),
            dict(claims, iss="https://firebaseappcheck.googleapis.com/456"),
            dict(claims, exp=int(time.time()) - 10),
            dict(claims, sub="1:123:web:deaddead"),
        ):
            with pytest.raises(PermissionError):
                verify("id-fixture", signed(bad))
        wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        with pytest.raises(PermissionError):
            verify("id-fixture", signed(claims, wrong_key))
    finally:
        firebase_admin.delete_app(app)


def test_real_auth_sdk_crypto_text_project_and_revocation(monkeypatch):
    """Real Auth SDK signature/claims/revocation logic with local cert/user transports."""
    import firebase_admin
    from firebase_admin import credentials
    import google.auth.credentials
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    from uuid import uuid4

    class FixtureCredential(credentials.Base):
        def get_credential(self):
            return google.auth.credentials.AnonymousCredentials()

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        .decode()
    )
    app = firebase_admin.initialize_app(
        FixtureCredential(),
        options={"projectId": "specimen-digitization"},
        name=str(uuid4()),
    )
    check_app = SimpleNamespace(project_id="123")
    try:
        client = runtime_auth.auth._get_client(app)
        monkeypatch.setattr(
            client._token_verifier,
            "request",
            lambda *args, **kwargs: SimpleNamespace(
                status=200, data=json.dumps({"local-fixture": pem}).encode()
            ),
        )
        user = SimpleNamespace(disabled=False, tokens_valid_after_timestamp=0)
        lookup = Mock(return_value=user)
        monkeypatch.setattr(client, "get_user", lookup)
        monkeypatch.setattr(
            runtime_auth.app_check,
            "verify_token",
            lambda *args, **kwargs: {
                "app_id": "1:123:web:abc123",
                "iss": "https://firebaseappcheck.googleapis.com/123",
            },
        )
        verify = runtime_auth.firebase_verifier(app, ("1:123:web:abc123",), check_app)
        claims = {
            "sub": "fixture-user",
            "aud": "specimen-digitization",
            "iss": "https://securetoken.google.com/specimen-digitization",
            "email_verified": True,
            "email": "fixture@fieldmuseum.org",
            "auth_time": int(time.time()),
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
        }

        def signed(values):
            return jwt.encode(
                values, key, algorithm="RS256", headers={"kid": "local-fixture"}
            )

        assert verify(signed(claims), "check-fixture") == "fixture-user"
        lookup.assert_called_with("fixture-user")
        for bad in (
            dict(claims, aud="123"),
            dict(claims, aud="other-project"),
            dict(claims, iss="https://securetoken.google.com/123"),
            dict(claims, exp=int(time.time()) - 10),
        ):
            with pytest.raises(PermissionError):
                verify(signed(bad), "check-fixture")
        user.disabled = True
        with pytest.raises(PermissionError):
            verify(signed(claims), "check-fixture")
        user.disabled = False
        user.tokens_valid_after_timestamp = (int(time.time()) + 1) * 1000
        with pytest.raises(PermissionError):
            verify(signed(claims), "check-fixture")
    finally:
        firebase_admin.delete_app(app)


def test_pilot_http_corrections_persist_without_restart_or_clearance(tmp_path):
    from test_application import (
        intake,
        HEADERS,
        PREFIX,
        TOKEN,
        SYNTHETIC_ORG,
        SYNTHETIC_COLLECTION,
    )
    from specimen_digitization.application.api import local_app
    from specimen_digitization.application.domain import Principal, Scope
    from specimen_digitization.application.storage import digest

    app = local_app(tmp_path, TOKEN)
    client = TestClient(app)
    created = intake(client)
    ident = created["specimen_id"]
    normal = client.get(PREFIX + "/specimens/" + ident, headers=HEADERS).json()
    assert {"retry", "resume", "reprocess"}.issubset(normal["available_actions"])
    principal = Principal(
        user_id="synthetic-reviewer",
        scope=Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION),
        role="reviewer",
    )
    repo = app.state.workflow.repository
    specimen = repo.get(principal.scope, ident)
    specimen.run.dependencies["evidence_pilot"] = {
        "version": "evidence-pilot-v1",
        "source_manifest_sha256": "a" * 64,
        "launch_sha256": "b" * 64,
        "profile_sha256": "c" * 64,
        "runtime_pins_sha256": digest(specimen.run.dependencies),
    }
    specimen.run.profile_snapshot["state"] = "draft"
    specimen.run.profile_snapshot["institutional_policy_approved"] = False
    specimen.run.profile_snapshot["semantics_confirmed"] = False
    specimen.run.profile_rules = {}
    specimen.run.risk_policy_snapshot = {"status": "blocked"}
    specimen.run.profile.institutional_policy_approved = False
    specimen.run.profile.semantics_confirmed = False
    specimen.run.human_approved = False
    specimen.run.review_risk = {"status": "policy_blocked", "unmeasured": ["pilot"]}
    specimen.run.stage = "processing_blocked"
    specimen.run.blocker = "pilot_evidence_review_required"
    specimen.run.disposition = None
    specimen = repo.save(
        principal, specimen, specimen.version, "pilot-fixture", digest("pilot-fixture")
    )
    url = PREFIX + "/specimens/" + ident
    workspace = client.get(url + "/workspace", headers=HEADERS).json()
    assert workspace["asset"]["view_derivative"] is None
    assert (
        client.get(
            PREFIX + "/assets/" + specimen.asset.id + "/content?view=true",
            headers=HEADERS,
        ).status_code
        == 404
    )
    assert (
        client.get(
            PREFIX + "/assets/" + specimen.asset.id + "/content", headers=HEADERS
        ).status_code
        == 200
    )
    assert workspace["available_actions"] == [
        "field",
        "transcription",
        "reading_metadata",
        "coverage",
    ]
    listed = client.get(
        PREFIX + "/specimens",
        params={"collection_id": SYNTHETIC_COLLECTION},
        headers=HEADERS,
    ).json()
    assert all(item["available_actions"] == [] for item in listed["items"])
    assert (
        client.get(url, headers=HEADERS).json()["available_actions"]
        == workspace["available_actions"]
    )
    revision = specimen.version
    app.state.workflow.drain = Mock(
        side_effect=AssertionError("No pilot inference permitted")
    )
    for action in ("retry", "resume", "reprocess", "pause", "cancel"):
        response = client.post(
            PREFIX + "/runs/" + specimen.run.id + "/actions",
            headers=HEADERS,
            json={
                "action": action,
                "expected_revision": revision,
                "reason": "fixture review",
            },
        )
        assert response.status_code == 409, response.text
    decision = {
        "expected_revision": revision,
        "reason": "fixture review",
        "base_record_version_id": f"{specimen.run.id}:{revision}",
    }
    for kind in ("approve", "capability_defer"):
        response = client.post(
            url + "/decisions", headers=HEADERS, json=dict(decision, kind=kind)
        )
        assert response.status_code == 409, response.text
    response = client.post(
        url + "/regions",
        headers=HEADERS,
        json={
            "expected_revision": revision,
            "reason": "fixture review",
            "base_run_id": specimen.run.id,
            "regions": [region.model_dump() for region in specimen.run.regions],
        },
    )
    assert response.status_code == 409
    response = client.post(
        url + "/classification",
        headers=HEADERS,
        json={
            "expected_revision": revision,
            "reason": "fixture review",
            "collection_id": SYNTHETIC_COLLECTION,
        },
    )
    assert response.status_code == 409
    assert client.post(url + "/process", headers=HEADERS).status_code == 409
    assert repo.get(principal.scope, ident).version == revision
    region = specimen.run.transcripts[0].region_id
    response = client.post(
        url + "/decisions",
        headers=HEADERS,
        json=dict(
            decision,
            kind="transcription",
            target_id=region,
            after={"text": "Human correction"},
        ),
    )
    assert response.status_code == 200, response.text
    result = response.json()
    for kind, target, after in (
        ("field", "taxon", {"state": "unknown", "reason": "Human uncertainty"}),
        ("coverage", "", {"confirmed": True}),
        (
            "reading_metadata",
            specimen.run.observations[0].id,
            {"language_candidates": ["English"]},
        ),
    ):
        response = client.post(
            url + "/decisions",
            headers=dict(HEADERS, **{"Idempotency-Key": "pilot-" + kind}),
            json={
                "kind": kind,
                "target_id": target,
                "after": after,
                "reason": "fixture review",
                "expected_revision": result["revision"],
                "base_record_version_id": result["record_version_id"],
            },
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["run"]["review_risk"] == specimen.run.review_risk
        assert result["run"]["human_approved"] is False
    assert result["stage"] == "processing_blocked" and result["disposition"] is None
    assert result["blocker"] == "pilot_evidence_review_required"
    restarted = TestClient(local_app(tmp_path, TOKEN))
    retained = restarted.get(url + "/workspace", headers=HEADERS).json()
    assert retained == result
    assert (
        retained["run"]["dependencies"]["evidence_pilot"]
        == specimen.run.dependencies["evidence_pilot"]
    )
    assert retained["observations"] == workspace["observations"]
    assert any(
        t["verbatim_text"] == "Human correction" for t in retained["transcriptions"]
    )
    assert restarted.get(url + "/history", headers=HEADERS).status_code == 200
    app.state.workflow.drain.assert_not_called()
    # Empty and unknown server markers remain fenced even though malformed.
    for marker in ({}, {"version": "future-version"}, None):
        invalid = repo.get(principal.scope, ident)
        invalid.run.dependencies["evidence_pilot"] = marker
        invalid = repo.save(
            principal,
            invalid,
            invalid.version,
            "malformed:" + str(invalid.version),
            digest(marker),
        )
        response = restarted.post(
            url + "/decisions",
            headers=HEADERS,
            json={
                "kind": "coverage",
                "after": {"confirmed": True},
                "reason": "fixture review",
                "expected_revision": invalid.version,
                "base_record_version_id": f"{invalid.run.id}:{invalid.version}",
            },
        )
        assert response.status_code == 409
        assert (
            restarted.get(url + "/workspace", headers=HEADERS).json()[
                "available_actions"
            ]
            == []
        )
        assert restarted.get(url, headers=HEADERS).json()["available_actions"] == []
        listed = restarted.get(
            PREFIX + "/specimens",
            params={"collection_id": SYNTHETIC_COLLECTION},
            headers=HEADERS,
        ).json()
        assert all(item["available_actions"] == [] for item in listed["items"])

    unknown = repo.get(principal.scope, ident)
    unknown.run.dependencies.pop("evidence_pilot")
    unknown.run.blocker = "external_outcome_unknown"
    unknown = repo.save(
        principal, unknown, unknown.version, "unknown-fixture", digest("unknown")
    )
    controls = restarted.get(url, headers=HEADERS).json()["available_actions"]
    assert not {"retry", "resume", "reprocess"}.intersection(controls)
    assert {"pause", "cancel"}.issubset(controls)
    for action in ("retry", "resume", "reprocess"):
        response = restarted.post(
            PREFIX + "/runs/" + unknown.run.id + "/actions",
            headers=HEADERS,
            json={
                "action": action,
                "expected_revision": unknown.version,
                "reason": "fixture review",
            },
        )
        assert response.status_code == 409
    assert repo.get(principal.scope, ident).version == unknown.version


@pytest.mark.parametrize("target", ["raw", "source", "crop"])
def test_pilot_declaration_integrity_rejects_changed_retained_bytes(tmp_path, target):
    from test_application import intake, TOKEN, SYNTHETIC_ORG, SYNTHETIC_COLLECTION
    from specimen_digitization.application.api import (
        local_app,
        verify_pilot_observation,
    )
    from specimen_digitization.application.domain import Scope
    from specimen_digitization.application.integrity import EvidenceIntegrityError
    from specimen_digitization.application.workflow import crop_bytes
    import hashlib

    app = local_app(tmp_path, TOKEN)
    created = intake(TestClient(app))
    repository, blobs = app.state.workflow.repository, app.state.workflow.blobs
    specimen = repository.get(
        Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION),
        created["specimen_id"],
    )
    specimen.run.profile.synthetic = False
    specimen.run.profile_snapshot["state"] = "draft"
    observation = specimen.run.observations[0]
    region = next(r for r in specimen.run.regions if r.id == observation.region_id)
    crop = crop_bytes(blobs, specimen, region)
    observation.input_sha256 = hashlib.sha256(crop).hexdigest()
    observation.input_crop_ref = blobs.put(crop)
    observation.input_asset_id = specimen.asset.id
    verify_pilot_observation(specimen, observation, blobs)
    ref = {
        "raw": observation.raw_ref,
        "source": specimen.asset.blob_ref,
        "crop": observation.input_crop_ref,
    }[target]
    (tmp_path / "blobs" / ref).write_bytes(b"corrupted fixture bytes")
    with pytest.raises(EvidenceIntegrityError):
        verify_pilot_observation(specimen, observation, blobs)
