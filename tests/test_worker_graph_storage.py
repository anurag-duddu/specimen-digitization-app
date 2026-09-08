"""Production assembly preserves large graphs; all transport and text are local."""

from datetime import datetime, timedelta, timezone
import hashlib
import json
from types import SimpleNamespace

import pytest

from specimen_digitization.application import worker
from specimen_digitization.application.active_graph import pack
from specimen_digitization.application.collection_profiles import insects_registry, SegmentationSettings
from specimen_digitization.application.domain import Asset, Observation, Principal, Profile, Region, Run, Scope, Specimen
from specimen_digitization.application.production import SqlConnectRepository, actor_uid
from specimen_digitization.application.storage import Conflict, LocalBlobs, digest
from specimen_digitization.application.worker_launch import PilotLaunch


class LocalSnapshotTransport:
    """Named-operation fixture, not a SQL Connect emulator or cloud substitute."""

    def __init__(self, scope):
        self.scope = scope
        self.versions = {}
        self.documents = {}

    def execute(self, operation, variables, mutation=False):
        if operation == "Memberships":
            return {
                "organizationMembers": [{"organizationId": self.scope.organization_id, "active": True}],
                "collectionMembers": [{
                    "organizationId": self.scope.organization_id,
                    "collectionId": self.scope.collection_id, "active": True,
                    "role": "reviewer", "canViewSensitive": False,
                }],
            }
        ident = variables.get("id")
        if operation == "GetSpecimen":
            revision = max(self.versions[ident])
            return {
                "specimen": {"revision": revision, "sensitive": False},
                "specimenSnapshots": [{"revision": revision}],
            }
        if operation == "GetSnapshot":
            return {"specimenSnapshot": self.versions[ident][variables["revision"]]}
        if operation == "GetReceipt":
            return {}
        if operation == "SaveSpecimenV3":
            assert mutation and variables["expectedRevision"] == max(self.versions[ident])
            payload = variables["snapshot"]
            self.versions[ident][payload["version"]] = {
                "snapshot": payload, "sha256": variables["snapshotSha256"],
            }
            return {}
        if operation == "GetDocumentV2":
            payload = self.documents.get(ident)
            return {"auxiliaryDocument": {"sensitive": False, "payload": payload} if payload else None}
        if operation in {"CreateDocumentV2", "SaveDocumentV2"}:
            assert mutation and variables["sensitive"] is False
            self.documents[ident] = variables["payload"]
            return {}
        raise AssertionError("Unexpected operation: " + operation)

    def repository(self, *, graph_blobs=None):
        # The named transport is replaced; reconstruction and persistence methods
        # remain the actual SqlConnectRepository implementation.
        repository = object.__new__(SqlConnectRepository)
        repository.graph_blobs = graph_blobs
        repository.execute = self.execute
        return repository


def retained_graphs(tmp_path, evidence_only=False):
    scope = Scope(
        organization_id="00000000-0000-4000-8000-000000000001",
        collection_id="00000000-0000-4000-8000-000000000002",
    )
    transport = LocalSnapshotTransport(scope)
    blobs = LocalBlobs(tmp_path / "graphs")
    blobs.bucket = SimpleNamespace(name="specimen-digitization.firebasestorage.app")
    response = b"Generated text-only fixture response; no image or model invocation."
    response_ref = blobs.put(response)
    records = []
    for index in range(10):
        source_sha = hashlib.sha256(f"source-reference-only-{index}".encode()).hexdigest()
        asset = Asset(
            sensitive=False, sha256=source_sha, blob_ref=source_sha + ":1",
            media_type="image/png", size_bytes=1, width=64, height=1,
            filename="unread-source-reference.png", uploader="graph-fixture",
        )
        run = Run(profile=Profile(synthetic=False), stage="processing_blocked",
                  blocker="pilot_evidence_review_required")
        for number in range(64):
            region = Region(asset_id=asset.id, x=number, y=0, width=1, height=1,
                            order=number, method="fixture", version="text-only-v1")
            run.regions.append(region)
            for route in run.profile.routes:
                run.observations.append(Observation(
                    region_id=region.id, route_id=route, model_id="fixture-" + route,
                    provider="local-fixture", prompt_version="text-only-v1",
                    input_sha256=source_sha, literal_text=(f"{index}/{number}/{route} " + "x" * 2048),
                    raw_ref=response_ref, raw_sha256=hashlib.sha256(response).hexdigest(),
                ))
        specimen = Specimen(scope=scope, asset=asset, run=run, version=1)
        payload = pack(specimen, blobs)
        assert payload["active_graph"]["size_bytes"] > 256 * 1024
        assert payload["run"]["observations"] == []
        transport.versions[specimen.id] = {1: {"snapshot": payload, "sha256": digest(payload)}}
        records.append(specimen)
    launch = PilotLaunch(
        sensitive=False, evidence_only=evidence_only,
        evidence_profile_sha256="f" * 64 if evidence_only else None,
        source_manifest_sha256="a" * 64, authorization_reference="local-test-only",
        scope=scope, specimens=[{
            "specimen_id": record.id, "asset_sha256": record.asset.sha256,
            "blob_ref": record.asset.blob_ref,
        } for record in records], expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        total_cost_limit_micros=10000, per_specimen_cost_limit_micros=1000,
        per_specimen_call_limit=32, per_specimen_token_limit=160000,
        effect_timeout_seconds=120,
        hf_secret_resource="/".join((
            "projects", "specimen-digitization", "secrets", "unused-fixture", "versions", "1",
        )),
    )
    return transport, blobs, records, launch


def test_standalone_readback_requires_explicit_graph_storage(tmp_path):
    transport, blobs, records, launch = retained_graphs(tmp_path)
    repository = transport.repository()
    actor_uid.set("graph-fixture")
    with pytest.raises(Conflict, match="Active graph integrity or storage failure"):
        repository.get(launch.scope, records[0].id)
    configured = transport.repository(graph_blobs=blobs)
    assert configured.get(launch.scope, records[0].id).run == records[0].run


@pytest.mark.parametrize("evidence_only", [False, True])
def test_production_worker_assembly_reads_saves_and_reopens_complete_graphs(
    tmp_path, monkeypatch, capsys, evidence_only
):
    from specimen_digitization import observability
    from specimen_digitization.application import worker_launch, evidence_pilot

    transport, blobs, records, launch = retained_graphs(tmp_path, evidence_only)
    repositories = []
    def factory(**kwargs):
        repository = transport.repository(**kwargs)
        repositories.append(repository)
        return repository

    # Replace only external construction/config validation. Run the real worker,
    # both real Workflow constructors, summary, and graph persistence paths.
    monkeypatch.setattr(worker, "SqlConnectRepository", factory)
    monkeypatch.setattr(worker, "GcsBlobs", lambda: blobs)
    monkeypatch.setattr(worker, "production_launch", lambda _: launch)
    monkeypatch.setattr(worker_launch, "verify_source_manifest", lambda *_: {})
    monkeypatch.setattr(worker_launch, "sam3_expectations", lambda *_: {})
    monkeypatch.setattr(worker, "ProductionAdapters", lambda *_args, **_kwargs: SimpleNamespace(blobs=blobs))
    profile = insects_registry().profiles[0].model_copy(update={
        "segmentation_settings": SegmentationSettings(prompt="label"),
    })
    monkeypatch.setattr(evidence_pilot, "read_evidence_profile", lambda *_: profile)
    monkeypatch.setattr(observability, "configure_observability", lambda **_: None)
    monkeypatch.setattr("signal.signal", lambda *_: None)
    monkeypatch.setenv("SPECIMEN_WORKER_ACTOR_UID", "graph-fixture")
    args = SimpleNamespace(mode="production", evidence_only=evidence_only,
                           evidence_profile="unused", source_manifest="unused",
                           check_config=False, once=True)
    with pytest.raises(SystemExit) as stopped:
        worker._run(args)
    assert stopped.value.code == 2  # Correctly reports review, never clearance.
    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == "evidence_review_required"
    assert summary["counts"] == {"review_required": 10}
    repository = repositories[0]
    assert repository.graph_blobs is blobs
    for original in records:
        restored = repository.get(launch.scope, original.id)
        assert restored.run == original.run
        assert len(restored.run.regions) == 64
        assert len(restored.run.observations) == 128
    principal = Principal(user_id="graph-fixture", scope=launch.scope, role="reviewer")
    current = repository.get(launch.scope, records[0].id)
    current.run.reasons.append("Retained local checkpoint")
    saved = repository.save(principal, current, 1, "checkpoint", digest("checkpoint"))
    fresh = transport.repository(graph_blobs=blobs)
    assert fresh.get(launch.scope, current.id).run == saved.run
    assert fresh.version(launch.scope, current.id, 1).run == records[0].run
    assert len(saved.run.regions) == 64 and len(saved.run.observations) == 128


def test_provided_sql_session_operates_without_ambient_adc(monkeypatch):
    from specimen_digitization.application import production

    monkeypatch.delenv("SPECIMEN_SQL_EMULATOR_HOST", raising=False)
    monkeypatch.setattr(production.google.auth, "default", lambda **_: pytest.fail("Ambient ADC was queried"))
    calls = []
    class SuppliedSession:
        def __bool__(self):
            return False  # A provided session is selected by identity, not truthiness.

        def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return SimpleNamespace(status_code=200, json=lambda: {"data": {}})

    session = SuppliedSession()
    repo = SqlConnectRepository(session=session)
    assert repo.session is session
    assert repo.memberships("fixture-reviewer") == []
    assert calls[0][1]["json"]["operationName"] == "Memberships"


def test_default_sql_construction_still_uses_adc(monkeypatch):
    from specimen_digitization.application import production

    monkeypatch.delenv("SPECIMEN_SQL_EMULATOR_HOST", raising=False)
    credential, session = object(), object()
    calls = []
    def adc(**kwargs):
        calls.append(kwargs)
        return credential, "specimen-digitization"

    monkeypatch.setattr(production.google.auth, "default", adc)
    monkeypatch.setattr(production, "AuthorizedSession", lambda supplied: session if supplied is credential else pytest.fail("Wrong credential"))
    assert SqlConnectRepository().session is session
    assert calls == [{"scopes": ["https://www.googleapis.com/auth/cloud-platform"]}]
