"""Missing/corrupt immutable evidence must not produce a scientific disposition."""

import hashlib

import pytest

from test_application import client, intake, HEADERS, PREFIX, TOKEN
from specimen_digitization.application.api import local_app
from specimen_digitization.application.integrity import (
    EvidenceIntegrityError,
    verify_evidence,
)
from specimen_digitization.application.storage import LocalBlobs


@pytest.mark.parametrize("target", ["source", "observation", "lookup"])
@pytest.mark.parametrize("damage", ["missing", "corrupt"])
def test_http_approval_blocks_until_retained_bytes_restored(tmp_path, target, damage):
    with client(tmp_path) as http:
        row = intake(http)
        path = PREFIX + f"/specimens/{row['specimen_id']}"
        before = http.get(path + "/workspace", headers=HEADERS).json()
        ref = {
            "source": before["asset"]["blob_ref"],
            "observation": before["observations"][0]["raw_ref"],
            "lookup": before["run"]["lookups"][0]["raw_ref"],
        }[target]
        blob = tmp_path / "blobs" / ref
        original = blob.read_bytes()
        if damage == "missing":
            blob.unlink()
        else:
            blob.write_bytes(b"corrupt synthetic fixture")

        def approve(work, key):
            return http.post(
                path + "/decisions",
                headers=dict(HEADERS, **{"Idempotency-Key": key}),
                json={
                    "kind": "approve",
                    "reason": "Synthetic review",
                    "expected_revision": work["revision"],
                    "base_record_version_id": work["record_version_id"],
                },
            )

        blocked = approve(before, "damaged-evidence")
        assert blocked.status_code == 200, blocked.text
        blocked = blocked.json()
        assert blocked["disposition"] is None
        assert blocked["status"] == "processing_blocked"
        assert blocked["reason_codes"] == ["evidence_integrity_failure"]
        assert http.get("/v1/session", headers=HEADERS).status_code == 200
        blob.write_bytes(original)
        restored = approve(blocked, "restored-evidence")
        assert restored.status_code == 200, restored.text
        assert restored.json()["disposition"] == "cleared"
        # Receipt preserves the blocked result even after storage is restored.
        assert approve(before, "damaged-evidence").json() == blocked


@pytest.mark.parametrize(
    "damage", ["wrong_digest", "wrong_ref", "wrong_asset", "wrong_input"]
)
def test_graph_integrity_rejects_substituted_provenance(tmp_path, damage):
    app = local_app(tmp_path, TOKEN)
    from fastapi.testclient import TestClient

    with TestClient(app) as http:
        row = intake(http)
    repo = app.state.workflow.repository
    from specimen_digitization.application.domain import Scope

    scope = Scope(
        organization_id=row["organization_id"], collection_id=row["collection_id"]
    )
    specimen = repo.get(scope, row["specimen_id"])
    if damage == "wrong_digest":
        specimen.run.observations[0].raw_sha256 = hashlib.sha256(b"wrong").hexdigest()
    elif damage == "wrong_ref":
        specimen.run.observations[0].raw_ref = specimen.asset.blob_ref
    elif damage == "wrong_asset":
        specimen.run.evidence[0].asset_id = "different-asset"
    else:
        specimen.run.observations[0].input_sha256 = hashlib.sha256(b"wrong").hexdigest()
    with pytest.raises(EvidenceIntegrityError):
        verify_evidence(specimen, LocalBlobs(tmp_path / "blobs"))
    # Persist the malformed graph as a storage fault, then exercise normal HTTP approval.
    from specimen_digitization.application.domain import Principal
    from specimen_digitization.application.storage import digest

    principal = Principal(user_id="synthetic-reviewer", role="reviewer", scope=scope)
    damaged = repo.save(
        principal, specimen, specimen.version, "fault-injection", digest(damage)
    )
    with TestClient(app) as http:
        path = PREFIX + f"/specimens/{specimen.id}"
        current = http.get(path + "/workspace", headers=HEADERS).json()
        response = http.post(
            path + "/decisions",
            headers=HEADERS,
            json={
                "kind": "approve",
                "reason": "Synthetic provenance fault probe",
                "expected_revision": damaged.version,
                "base_record_version_id": current["record_version_id"],
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["disposition"] is None
        assert response.json()["blocker"] == "evidence_integrity_failure"


def test_same_integrity_gate_checks_production_crop_lineage(tmp_path):
    """Use real retained bytes and production input hashing without a provider call."""
    app = local_app(tmp_path, TOKEN)
    from fastapi.testclient import TestClient
    from specimen_digitization.application.domain import Scope
    from specimen_digitization.application.workflow import crop_bytes

    with TestClient(app) as http:
        row = intake(http)
    specimen = app.state.workflow.repository.get(
        Scope(
            organization_id=row["organization_id"], collection_id=row["collection_id"]
        ),
        row["specimen_id"],
    )
    blobs = LocalBlobs(tmp_path / "blobs")
    specimen.run.profile.synthetic = False
    specimen.run.profile_snapshot = {}  # Exercise production crop hashing without a published fixture profile.
    for observation in specimen.run.observations:
        region = next(r for r in specimen.run.regions if r.id == observation.region_id)
        observation.input_sha256 = hashlib.sha256(
            crop_bytes(blobs, specimen, region)
        ).hexdigest()
    verify_evidence(specimen, blobs)
    raw = tmp_path / "blobs" / specimen.run.observations[0].raw_ref
    raw.unlink()
    with pytest.raises(EvidenceIntegrityError):
        verify_evidence(specimen, blobs)


def test_worker_finalization_blocks_missing_raw_storage(tmp_path):
    app = local_app(tmp_path, TOKEN)
    from fastapi.testclient import TestClient
    from specimen_digitization.application.domain import Principal, Scope
    from specimen_digitization.application.storage import digest

    with TestClient(app) as http:
        row = intake(http)
    workflow = app.state.workflow
    principal = Principal(
        user_id="synthetic-reviewer",
        role="reviewer",
        scope=Scope(
            organization_id=row["organization_id"], collection_id=row["collection_id"]
        ),
    )
    specimen = workflow.repository.get(principal.scope, row["specimen_id"])
    specimen.run.completed_steps.remove("finalize")
    specimen.run.stage = "validate"
    specimen.run.disposition = None
    specimen = workflow.repository.save(
        principal, specimen, specimen.version, "test-before-finalize", digest("fixture")
    )
    (tmp_path / "blobs" / specimen.run.observations[0].raw_ref).unlink()
    blocked = workflow.step(principal, specimen.id)
    assert blocked.run.stage == "processing_blocked"
    assert blocked.run.blocker == "evidence_integrity_failure"
    assert blocked.run.disposition is None


def test_source_supported_extraction_retains_verifiable_raw_digest(tmp_path):
    app = local_app(tmp_path, TOKEN)
    from fastapi.testclient import TestClient
    from specimen_digitization.application.domain import Scope
    from specimen_digitization.application.harness import (
        ExtractionOutput,
        ExtractionCandidate,
        apply_candidates,
    )

    with TestClient(app) as http:
        row = intake(http)
    specimen = app.state.workflow.repository.get(
        Scope(
            organization_id=row["organization_id"], collection_id=row["collection_id"]
        ),
        row["specimen_id"],
    )
    blobs = LocalBlobs(tmp_path / "blobs")
    raw = b'{"synthetic_extraction": "United States"}'
    ref = blobs.put(raw)
    apply_candidates(
        specimen.run,
        specimen.asset.id,
        ExtractionOutput(
            candidates=[
                ExtractionCandidate(
                    field_key="country",
                    region_id=specimen.run.regions[0].id,
                    literal="United States",
                    source_excerpt="country: United States",
                )
            ]
        ),
        ref,
        hashlib.sha256(raw).hexdigest(),
    )
    verify_evidence(specimen, blobs)
    assert specimen.run.evidence[-1].digest == hashlib.sha256(raw).hexdigest()
