"""Behavioral vertical-slice tests across HTTP, immutable storage and restart."""

import hashlib
import io
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from specimen_digitization.application.api import (
    local_app,
    SYNTHETIC_ORG,
    SYNTHETIC_COLLECTION,
    SYNTHETIC_TEXT,
)
from specimen_digitization.application.domain import (
    MANDATORY,
    Disposition,
    LookupStatus,
    Principal,
    Scope,
)
from specimen_digitization.application.lookup import GbifTaxonomy
from specimen_digitization.application.policy import evaluate, finalize
from specimen_digitization.application.storage import (
    SQLiteRepository,
    LocalBlobs,
    Conflict,
    digest,
)
from specimen_digitization.application.workflow import (
    Workflow,
    SyntheticAdapters,
)

TOKEN = "test-only-local-token"
PREFIX = f"/v1/organizations/{SYNTHETIC_ORG}"
HEADERS = {"Authorization": "Bearer " + TOKEN, "Idempotency-Key": "test-request"}


def image_bytes():
    output = io.BytesIO()
    Image.new("RGB", (120, 80), "white").save(output, format="PNG")
    return output.getvalue()


def client(root):
    return TestClient(local_app(root, TOKEN), raise_server_exceptions=False)


def intake(c, split=False):
    batch = c.post(
        PREFIX + "/batches",
        headers=HEADERS,
        json={"collection_id": SYNTHETIC_COLLECTION, "display_name": "Synthetic"},
    )
    assert batch.status_code == 200, batch.text
    data = image_bytes()
    item = c.post(
        PREFIX + f"/batches/{batch.json()['batch_id']}/items",
        headers=HEADERS,
        json={
            "client_item_id": "one",
            "filename": "synthetic.png",
            "media_type": "image/png",
            "size_bytes": len(data),
            "width": 120,
            "height": 80,
            "sha256": hashlib.sha256(data).hexdigest(),
        },
    )
    assert item.status_code == 200, item.text
    upload = item.json()
    if split:
        part = data[:20]
        response = c.put(
            PREFIX + f"/uploads/{upload['upload_id']}/content",
            headers=dict(HEADERS, **{"Upload-Offset": "0"}),
            content=part,
        )
        assert response.status_code == 200, response.text
        return upload, data, response.json()
    response = c.put(
        PREFIX + f"/uploads/{upload['upload_id']}/content",
        headers=HEADERS,
        content=data,
    )
    assert response.status_code == 200, response.text
    done = c.post(
        PREFIX + f"/uploads/{upload['upload_id']}/complete",
        headers=HEADERS,
        json={"expected_revision": response.json()["revision"]},
    )
    assert done.status_code == 200, done.text
    return done.json()


def test_http_upload_restart_transcribe_review_clear_and_reconstruct(tmp_path):
    c = client(tmp_path)
    upload, data, progress = intake(c, split=True)
    c.close()
    c = client(tmp_path)  # new app/repository against only retained disk state
    status = c.get(PREFIX + f"/uploads/{upload['upload_id']}", headers=HEADERS).json()
    assert status["offset"] == 20
    replay = c.put(
        PREFIX + f"/uploads/{upload['upload_id']}/content",
        headers=HEADERS,
        content=data[:20],
    )
    assert replay.json()["offset"] == 20
    rest = c.put(
        PREFIX + f"/uploads/{upload['upload_id']}/content",
        headers=dict(HEADERS, **{"Upload-Offset": "20"}),
        content=data[20:],
    )
    done = c.post(
        PREFIX + f"/uploads/{upload['upload_id']}/complete",
        headers=HEADERS,
        json={"expected_revision": rest.json()["revision"]},
    )
    assert done.status_code == 200, done.text
    ident = done.json()["specimen_id"]
    processed = c.post(PREFIX + f"/specimens/{ident}/process", headers=HEADERS)
    assert processed.status_code == 200, processed.text
    work = processed.json()
    assert work["disposition"] == "needs_human_review"
    assert len(work["observations"]) == 2
    assert set(work["fields"]) == set(MANDATORY)
    request = {
        "expected_revision": work["revision"],
        "base_record_version_id": work["record_version_id"],
        "kind": "approve",
        "reason": "Synthetic fixture reviewed",
    }
    approved = c.post(
        PREFIX + f"/specimens/{ident}/decisions", headers=HEADERS, json=request
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["disposition"] == "cleared", approved.text
    same = c.post(
        PREFIX + f"/specimens/{ident}/decisions", headers=HEADERS, json=request
    )
    assert same.json()["revision"] == approved.json()["revision"]
    request["reason"] = "Altered payload"
    assert (
        c.post(
            PREFIX + f"/specimens/{ident}/decisions", headers=HEADERS, json=request
        ).status_code
        == 409
    )
    c.close()
    c = client(tmp_path)
    saved = c.get(PREFIX + f"/specimens/{ident}/workspace", headers=HEADERS).json()
    assert saved == approved.json()
    source = c.get(PREFIX + f"/assets/{saved['asset']['id']}/content", headers=HEADERS)
    assert source.content == data


def test_mandatory_gate_every_field_and_semantics(tmp_path):
    c = client(tmp_path)
    specimen = intake(c)
    c.post(PREFIX + f"/specimens/{specimen['specimen_id']}/process", headers=HEADERS)
    repo = SQLiteRepository(tmp_path / "state.sqlite3")
    s = repo.list(
        Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
    )[0]
    s.run.human_approved = True
    assert not evaluate(s.run)
    for key in MANDATORY:
        run = s.run.model_copy(deep=True)
        run.fields[key].literal = "unknown"
        assert f"mandatory_unresolved:{key}" in evaluate(run)
        run = s.run.model_copy(deep=True)
        run.fields[key].evidence_ids = []
        assert f"evidence_missing:{key}" in evaluate(run)
    s.run.profile.semantics_confirmed = False
    finalize(s.run)
    assert s.run.disposition == Disposition.REVIEW
    assert "mandatory_semantics_unconfirmed" in s.run.reasons


def test_auth_scope_stale_write_and_concurrent_cas(tmp_path):
    c = client(tmp_path)
    assert c.get("/v1/session").status_code == 401
    assert (
        c.get("/v1/session", headers={"Authorization": "Bearer wrong"}).status_code
        == 401
    )
    assert (
        c.get(
            "/v1/organizations/other/specimens",
            params={"collection_id": SYNTHETIC_COLLECTION},
            headers=HEADERS,
        ).status_code
        == 403
    )
    specimen = intake(c)
    scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
    repo = SQLiteRepository(tmp_path / "state.sqlite3")
    s = repo.get(scope, specimen["specimen_id"])
    p = Principal(user_id="synthetic-reviewer", scope=scope, role="reviewer")

    def save(i):
        try:
            repo.save(p, s, s.version, str(i), digest({"write": i}))
            return "saved"
        except Conflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(save, [1, 2])) == ["conflict", "saved"]


@pytest.mark.parametrize(
    "status,expected",
    [
        (401, LookupStatus.AUTHENTICATION),
        (403, LookupStatus.AUTHORIZATION),
        (429, LookupStatus.RATE_LIMITED),
        (503, LookupStatus.PROVIDER),
    ],
)
def test_lookup_http_failure_taxonomy(tmp_path, status, expected):
    transport = httpx.MockTransport(
        lambda req: httpx.Response(
            status, headers={"Retry-After": "17"}, json={"error": "synthetic"}
        )
    )
    result = GbifTaxonomy(
        LocalBlobs(tmp_path), httpx.Client(transport=transport)
    ).lookup("Danaus plexippus")
    assert result.status == expected
    assert result.raw_ref
    if status == 429:
        assert result.retry_after_seconds == 17


@pytest.mark.parametrize(
    "match,usage,expected",
    [
        ("NONE", None, LookupStatus.NO_MATCH),
        ("HIGHERRANK", {"key": "1", "rank": "GENUS"}, LookupStatus.AMBIGUOUS),
        ("EXACT", {"key": "x", "rank": "SPECIES"}, LookupStatus.SUCCESS),
    ],
)
def test_lookup_match_not_confidence(tmp_path, match, usage, expected):
    def response(req):
        if req.url.path.endswith("metadata"):
            return httpx.Response(200, json={"alias": "fixture-index"})
        assert req.url.params["checklistKey"]
        return httpx.Response(
            200,
            json={
                "usage": usage,
                "diagnostics": {"matchType": match, "confidence": 100},
            },
        )

    result = GbifTaxonomy(
        LocalBlobs(tmp_path), httpx.Client(transport=httpx.MockTransport(response))
    ).lookup("fixture")
    assert result.status == expected
    assert result.metadata["index"]["alias"] == "fixture-index"


def test_lookup_timeout_and_malformed(tmp_path):
    def timeout(req):
        raise httpx.ReadTimeout("test")

    assert (
        GbifTaxonomy(
            LocalBlobs(tmp_path), httpx.Client(transport=httpx.MockTransport(timeout))
        )
        .lookup("fixture")
        .status
        == LookupStatus.TIMEOUT
    )
    assert (
        GbifTaxonomy(
            LocalBlobs(tmp_path),
            httpx.Client(
                transport=httpx.MockTransport(
                    lambda r: httpx.Response(200, content=b"")
                )
            ),
        )
        .lookup("fixture")
        .status
        == LookupStatus.MALFORMED
    )


def test_disagreement_abstains_and_crash_intent_does_not_repeat(tmp_path):
    c = client(tmp_path)
    row = intake(c)
    repo = SQLiteRepository(tmp_path / "state.sqlite3")
    blobs = LocalBlobs(tmp_path / "blobs")
    scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
    p = Principal(user_id="synthetic-reviewer", scope=scope, role="reviewer")
    adapters = SyntheticAdapters(blobs, SYNTHETIC_TEXT, "taxon: different")
    existing = repo.get(scope, row["specimen_id"])
    from specimen_digitization.application.domain import Run

    existing.run = Run(profile=existing.run.profile)
    repo.save(p, existing, existing.version, "reset-fixture", digest({"reset": True}))
    workflow = Workflow(repo, blobs, adapters)
    result = workflow.drain(p, row["specimen_id"])
    assert not result.run.transcripts[0].resolved
    assert result.run.disposition == Disposition.REVIEW
    assert result.run.fields["taxon"].literal is None
    # Simulate durable intent followed by process death before network result.
    result.run.stage = "lookup"
    result.run.blocker = "external_outcome_unknown"
    result = repo.save(p, result, result.version, "crash", digest({"crash": True}))
    prior = len(result.run.observations)
    result = Workflow(
        SQLiteRepository(tmp_path / "state.sqlite3"), blobs, adapters
    ).step(p, result.id)
    assert result.run.stage == "processing_blocked"
    assert len(result.run.observations) == prior


def test_operational_retry_resumes_without_duplicate_observations(tmp_path):
    c = client(tmp_path)
    row = intake(c)
    repo = SQLiteRepository(tmp_path / "state.sqlite3")
    blobs = LocalBlobs(tmp_path / "blobs")
    scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
    p = Principal(user_id="synthetic-reviewer", scope=scope, role="reviewer")
    from specimen_digitization.application.domain import Run, Lookup

    s = repo.get(scope, row["specimen_id"])
    s.run = Run(profile=s.run.profile)
    repo.save(p, s, s.version, "new-run", digest({"new": True}))

    class FailingOnce(SyntheticAdapters):
        calls = 0

        def lookup(self, name):
            self.calls += 1
            if self.calls == 1:
                return Lookup(
                    provider="synthetic",
                    adapter_version="1",
                    query={"name": name},
                    status=LookupStatus.RATE_LIMITED,
                    retry_after_seconds=1,
                )
            return super().lookup(name)

    adapters = FailingOnce(blobs, SYNTHETIC_TEXT)
    workflow = Workflow(repo, blobs, adapters)
    s = workflow.drain(p, s.id)
    assert s.run.disposition is None
    assert s.run.stage == "retry_scheduled"
    ids = [o.id for o in s.run.observations]
    s.run.next_retry_at = "2000-01-01T00:00:00+00:00"
    repo.save(p, s, s.version, "clock-fixture", digest({"clock": True}))
    restarted_repo = SQLiteRepository(tmp_path / "state.sqlite3")
    s = Workflow(restarted_repo, blobs, adapters).drain(p, s.id)
    assert s.run.blocker.startswith("provider_circuit:")
    assert adapters.calls == 1  # A forced record retry cannot bypass shared backoff.
    from datetime import datetime, timezone, timedelta

    s = Workflow(
        restarted_repo,
        blobs,
        adapters,
        clock=lambda: datetime.now(timezone.utc) + timedelta(seconds=31),
    ).drain(p, s.id)
    assert s.run.disposition == Disposition.REVIEW
    assert [o.id for o in s.run.observations] == ids
    assert len(s.run.lookups) == 2


def test_deferred_requires_capability_attempts_and_never_operational(tmp_path):
    c = client(tmp_path)
    row = intake(c)
    scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
    s = SQLiteRepository(tmp_path / "state.sqlite3").get(scope, row["specimen_id"])
    s.run.capability_reason = "unsupported_script_after_approved_attempts"
    s.run.retry_eligibility = "new_approved_script_model"
    finalize(s.run)
    assert s.run.disposition != Disposition.DEFERRED
    s.run.completed_steps.append("capability_attempts_exhausted")
    finalize(s.run)
    assert s.run.disposition == Disposition.DEFERRED
    s.run.blocker = "credential_error"
    finalize(s.run)
    assert s.run.disposition is None
    assert s.run.stage == "processing_blocked"


def test_extraction_rejects_coerced_value_and_retains_supported_candidates(tmp_path):
    from specimen_digitization.application.harness import (
        ExtractionOutput,
        ExtractionCandidate,
        apply_candidates,
    )

    c = client(tmp_path)
    row = intake(c)
    scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
    s = SQLiteRepository(tmp_path / "state.sqlite3").get(scope, row["specimen_id"])
    region = s.run.regions[0].id
    before = s.run.fields["country"].model_copy(deep=True)
    output = ExtractionOutput(
        candidates=[
            ExtractionCandidate(
                field_key="country",
                region_id=region,
                literal="Invented",
                source_excerpt="country: United States",
            )
        ]
    )
    apply_candidates(s.run, s.asset.id, output, "synthetic-raw")
    assert s.run.fields["country"] == before
    # Evidence ids alone cannot launder an unsupported review value.
    s.run.fields["country"].literal = "Invented"
    assert "evidence_does_not_support_value:country" in evaluate(s.run)


def test_production_transcriber_does_not_receive_peer_observations(
    tmp_path, monkeypatch
):
    from pydantic_ai.models.function import FunctionModel
    from pydantic_ai.messages import ModelResponse, ToolCallPart
    from specimen_digitization.application import production
    from specimen_digitization.model_gateway import INITIAL_HUGGINGFACE_ROUTES

    captured = []

    def model(messages, info):
        captured.append(messages)
        return ModelResponse(
            model_name="synthetic-observation-model",
            finish_reason="stop",
            parts=[
                ToolCallPart(
                    info.output_tools[0].name,
                    {
                        "verbatim_text": "Independent source",
                        "lines": ["Independent source"],
                        "unreadable_spans": [],
                        "language_candidates": ["English", "German"],
                        "script_candidates": ["Latin"],
                        "language_relation": "cooccurring",
                    },
                )
            ],
        )

    class Gateway:
        def __init__(self, timeout_seconds=None):
            self.timeout_seconds = timeout_seconds

        def route(self, route):
            return INITIAL_HUGGINGFACE_ROUTES[route]

        def model_for(self, route):
            return FunctionModel(model)

    monkeypatch.setenv("SPECIMEN_APPROVED_INFERENCE", "true")
    monkeypatch.setattr(production, "HuggingFaceModelGateway", Gateway)
    c = client(tmp_path)
    row = intake(c)
    scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
    specimen = SQLiteRepository(tmp_path / "state.sqlite3").get(
        scope, row["specimen_id"]
    )
    specimen.run.observations[0].literal_text = "PEER-OUTPUT-MUST-NOT-LEAK"
    blobs = LocalBlobs(tmp_path / "blobs")
    adapter = production.ProductionAdapters(blobs)
    specimen.run.dependencies = adapter.pin_dependencies(specimen.run)
    for route in specimen.run.profile.routes:
        observation = adapter._transcribe_direct(
            specimen, specimen.run.regions[0], route
        )
        assert observation.literal_text == "Independent source"
        assert observation.finish_state == "stop"
        import json

        assert (
            observation.provider_model_id
            == json.loads(blobs.get(observation.raw_ref))[-1]["model_name"]
        )
        assert observation.completion_state == "validated_output"
        assert (
            observation.latency_seconds is not None and observation.latency_seconds >= 0
        )
        assert observation.latency_basis == "validated_agent_call_wall_seconds"
        assert (
            observation.parameters is None
        )  # No sampling settings were explicitly supplied.
        assert observation.input_asset_id == specimen.asset.id
        import hashlib

        assert (
            hashlib.sha256(blobs.get(observation.input_crop_ref)).hexdigest()
            == observation.input_sha256
        )
        from specimen_digitization.application.reading_declarations import checked_value

        declaration = checked_value(observation.declaration_evidence, blobs)
        assert declaration["structured_output"]["language_candidates"] == [
            "English",
            "German",
        ]
        assert declaration["candidates"]["language_relation"] == "cooccurring"
        assert declaration["raw_sha256"] == observation.raw_sha256
        assert declaration["producer"] == observation.model_id
        assert declaration["version"] == observation.prompt_version
        raw = blobs.get(observation.raw_ref)
        assert b"Independent source" in raw
        assert b"PEER-OUTPUT-MUST-NOT-LEAK" not in raw
    assert len(captured) == 2
    assert all(
        "PEER-OUTPUT-MUST-NOT-LEAK" not in repr(messages) for messages in captured
    )


def test_snapshot_bound_never_truncates_history(tmp_path):
    from specimen_digitization.application.storage import SnapshotTooLarge

    c = client(tmp_path)
    row = intake(c)
    scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
    repo = SQLiteRepository(tmp_path / "state.sqlite3")
    specimen = repo.get(scope, row["specimen_id"])
    prior = specimen.version
    specimen.run.reasons = ["x" * 300000]
    principal = Principal(user_id="synthetic-reviewer", scope=scope, role="reviewer")
    with pytest.raises(SnapshotTooLarge):
        repo.save(principal, specimen, prior, "oversize", digest({"test": "oversize"}))
    assert repo.get(scope, specimen.id).version == prior


def test_whitespace_and_unbacked_normalization_cannot_clear(tmp_path):
    c = client(tmp_path)
    row = intake(c)
    scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
    s = SQLiteRepository(tmp_path / "state.sqlite3").get(scope, row["specimen_id"])
    s.run.fields["country"].literal = "  "
    assert "mandatory_unresolved:country" in evaluate(s.run)
    s.run.fields["country"].literal = "United States"
    s.run.fields["country"].normalized = "Invented normalized country"
    assert "unsupported_normalized:country" in evaluate(s.run)


def test_review_resolves_authority_ambiguity_without_overwriting_lookup(tmp_path):
    from specimen_digitization.application.domain import Lookup

    app = local_app(tmp_path, TOKEN)

    class Ambiguous(SyntheticAdapters):
        def lookup(self, name):
            retained = super().lookup(name)
            return Lookup(
                raw_ref=retained.raw_ref,
                digest=retained.digest,
                provider="synthetic",
                adapter_version="1",
                query={"name": name},
                status=LookupStatus.AMBIGUOUS,
                candidates=[
                    {"key": "candidate-one", "scientificName": name},
                    {"key": "candidate-two", "scientificName": "Alternative"},
                ],
            )

    app.state.workflow.adapters = Ambiguous(
        LocalBlobs(tmp_path / "blobs"), SYNTHETIC_TEXT
    )
    c = TestClient(app, raise_server_exceptions=False)
    row = intake(c)
    work = c.get(
        PREFIX + f"/specimens/{row['specimen_id']}/workspace", headers=HEADERS
    ).json()
    assert "taxonomy_unresolved" in work["reason_codes"]
    request = {
        "expected_revision": work["revision"],
        "base_record_version_id": work["record_version_id"],
        "kind": "taxonomy_resolution",
        "after": {"authority_id": "candidate-one"},
        "reason": "Reviewed retained synthetic candidate",
    }
    result = c.post(
        PREFIX + f"/specimens/{row['specimen_id']}/decisions",
        headers=dict(HEADERS, **{"Idempotency-Key": "resolve-authority"}),
        json=request,
    )
    assert result.status_code == 200, result.text
    resolved = result.json()
    assert resolved["run"]["lookups"][-1]["status"] == "ambiguous"
    assert "taxonomy_unresolved" not in resolved["reason_codes"]
    assert resolved["fields"]["taxon"]["authority_id"] == "candidate-one"


def test_http_transcription_abstention_preserves_readings_and_blocks_clear(tmp_path):
    c = client(tmp_path)
    row = intake(c)
    path = PREFIX + f"/specimens/{row['specimen_id']}"
    before = c.get(path + "/workspace", headers=HEADERS).json()
    request = {
        "expected_revision": before["revision"],
        "base_record_version_id": before["record_version_id"],
        "kind": "transcription",
        "target_id": before["regions"][0]["region_id"],
        "after": {"state": "unreadable", "text": None},
        "reason": "Source span cannot be read",
    }
    changed = c.post(
        path + "/decisions",
        headers=dict(HEADERS, **{"Idempotency-Key": "abstention"}),
        json=request,
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["transcriptions"][0]["state"] == "unreadable"
    assert changed.json()["transcriptions"][0]["verbatim_text"] is None
    assert changed.json()["observations"] == before["observations"]
    finished = c.get(path + "/workspace", headers=HEADERS).json()
    assert finished["stage"] == "finalized"
    assert finished["disposition"] == "needs_human_review"
    assert all(v["value_state"] != "supported" for v in finished["fields"].values())


def test_http_available_actions_match_role_and_server_rejects_viewer_edit(tmp_path):
    from specimen_digitization.application.api import create_app

    c = client(tmp_path)
    row = intake(c)
    repo = SQLiteRepository(tmp_path / "state.sqlite3")
    blobs = LocalBlobs(tmp_path / "blobs")
    app = create_app(
        mode="emulator",
        repository=repo,
        blobs=blobs,
        adapters=SyntheticAdapters(blobs, SYNTHETIC_TEXT),
        identity_verifier=lambda token, check: "viewer",
        memberships=lambda user: [
            {
                "organization_id": SYNTHETIC_ORG,
                "collection_id": SYNTHETIC_COLLECTION,
                "role": "viewer",
                "can_view_sensitive": True,
            }
        ],
    )
    viewer = TestClient(app, raise_server_exceptions=False)
    path = PREFIX + f"/specimens/{row['specimen_id']}"
    detail = viewer.get(path + "/workspace", headers=HEADERS)
    assert detail.status_code == 200, detail.text
    assert detail.json()["available_actions"] == []
    body = {
        "expected_revision": detail.json()["revision"],
        "base_record_version_id": detail.json()["record_version_id"],
        "kind": "approve",
        "reason": "Attempt unauthorized clear",
    }
    assert (
        viewer.post(path + "/decisions", headers=HEADERS, json=body).status_code == 403
    )


@pytest.mark.parametrize(
    "host",
    [
        "localhost:9499",
        "127.0.0.2:9499",
        "0.0.0.0:9499",
        "example.com:9499",
        "127.0.0.1:0",
        "127.0.0.1:65536",
        "127.0.0.1:9499/path",
    ],
)
def test_emulator_configuration_rejects_nonloopback_or_invalid_ports(monkeypatch, host):
    from specimen_digitization.application.production import (
        sql_emulator_host,
        SqlConnectRepository,
    )

    monkeypatch.setenv("SPECIMEN_SQL_EMULATOR_HOST", host)
    with pytest.raises(ValueError):
        sql_emulator_host()
    with pytest.raises(ValueError):
        SqlConnectRepository(project="demo-specimen-data", emulator_host=host)


def test_emulator_port_config_is_explicit_and_production_rejects_it(monkeypatch):
    from specimen_digitization.application.production import (
        sql_emulator_host,
        SqlConnectRepository,
    )

    monkeypatch.setenv("SPECIMEN_SQL_EMULATOR_HOST", "127.0.0.1:18499")
    assert sql_emulator_host() == "127.0.0.1:18499"
    repo = SqlConnectRepository(
        project="demo-specimen-data", emulator_host=sql_emulator_host()
    )
    assert repo.url.startswith("http://127.0.0.1:18499/")
    with pytest.raises(ValueError, match="Production rejects"):
        SqlConnectRepository()
