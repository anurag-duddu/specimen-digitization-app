"""Local generated fixtures exercise the evidence-only lane, never live models."""

from types import SimpleNamespace
import hashlib

import pytest

from specimen_digitization.application.collection_profiles import (
    insects_registry,
    SegmentationSettings,
)
from specimen_digitization.application.domain import Region, Observation
from specimen_digitization.application.evidence_pilot import (
    EvidencePilotWorkflow,
    read_evidence_profile,
)
from specimen_digitization.application.production import ProductionAdapters
from specimen_digitization.application.worker_launch import PilotAdmission
from specimen_digitization.application.workflow import Workflow, OperationalBlock
from specimen_digitization.application.storage import LocalBlobs, digest
from test_worker_launch import fixture
from test_application import image_bytes


class FixtureProvider:
    classifier = None

    def __init__(self, blobs):
        self.blobs = blobs

    pin_dependencies = ProductionAdapters.pin_dependencies

    def transcribe(self, specimen, region, route):
        raw = ("local fixture " + route).encode()
        return Observation(
            region_id=region.id,
            route_id=route,
            model_id=route,
            provider="local-fixture",
            prompt_version="fixture",
            input_sha256=specimen.asset.sha256,
            input_asset_id=specimen.asset.id,
            literal_text=raw.decode(),
            raw_ref=self.blobs.put(raw),
            raw_sha256=hashlib.sha256(raw).hexdigest(),
        )


def pilot(tmp_path, monkeypatch):
    repo, principal, specimens, launch = fixture(tmp_path)
    blobs = LocalBlobs(tmp_path / "pilot-blobs")
    raw = image_bytes()
    source_ref = blobs.put(raw)
    s = repo.get(principal.scope, specimens[0].id)
    s.asset.sha256 = hashlib.sha256(raw).hexdigest()
    s.asset.blob_ref = s.asset.sha256 + ":123"
    repo.save(principal, s, s.version, "pilot-fixture-source", digest(s.asset.sha256))
    launch.specimens[0].asset_sha256 = s.asset.sha256
    launch.specimens[0].blob_ref = s.asset.blob_ref
    original_get = blobs.get
    blobs.get = lambda ref: original_get(source_ref if ref == s.asset.blob_ref else ref)
    profile = (
        insects_registry()
        .profiles[0]
        .model_copy(
            update={
                "collection_id": principal.scope.collection_id,
                "segmentation_settings": SegmentationSettings(prompt="label"),
            }
        )
    )
    profile_path = tmp_path / "draft.json"
    profile_path.write_text(profile.model_dump_json())
    profile_path.chmod(0o600)
    profile_hash = hashlib.sha256(profile_path.read_bytes()).hexdigest()
    profile = read_evidence_profile(profile_path, profile_hash)
    launch.evidence_only = True
    launch.evidence_profile_sha256 = profile_hash
    monkeypatch.setenv("SPECIMEN_APPROVED_INFERENCE", "true")
    monkeypatch.setenv("SPECIMEN_APPROVED_EVIDENCE_PILOT", "true")
    admission = PilotAdmission(repo, launch)
    workflow = EvidencePilotWorkflow(
        repo, blobs, admission, profile, production=FixtureProvider(blobs)
    )
    calls = []

    def segment(item):
        calls.append(item.id)
        return [
            Region(
                asset_id=item.asset.id,
                x=0,
                y=0,
                width=120,
                height=80,
                order=0,
                method="sam3",
                version="local-fixture",
            )
        ]

    workflow.adapters.segment = segment
    return repo, principal, s, launch, workflow, calls


def test_real_orchestration_retains_blind_fixture_readings_and_stops_without_clearance(
    tmp_path, monkeypatch
):
    repo, principal, s, launch, workflow, calls = pilot(tmp_path, monkeypatch)
    for _ in range(10):
        result = workflow.step(principal, s.id)
        if result.run.stage == "processing_blocked":
            break
    assert result.run.blocker == "pilot_evidence_review_required"
    assert result.run.disposition is None and not result.run.human_approved
    assert len(result.run.observations) == 2 and len(result.run.transcripts) == 1
    assert (
        not result.run.transcripts[0].resolved
        and result.run.transcripts[0].text is None
    )
    assert all(field.literal is None for field in result.run.fields.values())
    assert result.run.risk_policy_snapshot["status"] == "blocked"
    assert result.run.profile_snapshot["state"] == "draft"
    assert not result.run.profile.institutional_policy_approved
    assert not {"classify", "adjudicate", "parse", "lookup", "finalize"} & set(
        result.run.completed_steps
    )
    assert calls == [s.id]
    # Ordinary orchestration cannot resume this lane even if a caller clears stage.
    with pytest.raises(OperationalBlock, match="pilot_worker_required"):
        Workflow(repo, workflow.blobs, workflow.adapters).step(principal, s.id)


@pytest.mark.parametrize(
    "issue", ["outside", "approval", "launch", "profile", "pins", "normal_marker"]
)
def test_pilot_entry_and_mutated_binding_denials(tmp_path, monkeypatch, issue):
    repo, principal, s, launch, workflow, calls = pilot(tmp_path, monkeypatch)
    if issue == "outside":
        s.id = "not-authorized"
    if issue == "approval":
        monkeypatch.delenv("SPECIMEN_APPROVED_EVIDENCE_PILOT")
    if issue == "launch":
        launch.evidence_only = False
        with pytest.raises(OperationalBlock, match="not_authorized"):
            EvidencePilotWorkflow(
                repo, workflow.blobs, workflow.admission, workflow.pilot_profile
            )
        return
    if issue in {"profile", "pins", "normal_marker"}:
        result = workflow.step(principal, s.id)
        if issue == "profile":
            result.run.profile_snapshot["state"] = "active"
        if issue == "pins":
            result.run.dependencies["prompts"] = {}
        if issue == "normal_marker":
            result.run.dependencies["evidence_pilot"] = None
        repo.save(principal, result, result.version, "mutated-fixture", digest(issue))
    if issue == "outside":
        from specimen_digitization.application.storage import Missing

        with pytest.raises(Missing):
            workflow.step(principal, s.id)
    else:
        with pytest.raises(OperationalBlock):
            workflow.step(principal, s.id)
    assert not calls


def test_pilot_rejects_unfrozen_processing_derivative_before_pixels(
    tmp_path, monkeypatch
):
    repo, principal, s, launch, workflow, calls = pilot(tmp_path, monkeypatch)
    s = repo.get(principal.scope, s.id)
    s.asset.processing_derivative = {
        "blob_ref": "unrelated-object",
        "original_sha256": s.asset.sha256,
        "derivative_sha256": "b" * 64,
    }
    repo.save(principal, s, s.version, "bad-derivative", digest("bad-derivative"))
    with pytest.raises(OperationalBlock, match="binding_mismatch"):
        workflow.step(principal, s.id)
    assert not calls


def test_pilot_finalized_record_cannot_be_reported_as_completed(tmp_path, monkeypatch):
    from specimen_digitization.application.worker import PilotWorker

    repo, principal, s, launch, workflow, calls = pilot(tmp_path, monkeypatch)
    result = workflow.step(principal, s.id)
    result.run.stage = "finalized"
    repo.save(
        principal, result, result.version, "invalid-final", digest("invalid-final")
    )
    with pytest.raises(OperationalBlock, match="configuration_changed"):
        workflow.step(principal, s.id)
    worker = PilotWorker(
        repo,
        workflow,
        principal.user_id,
        lambda uid: [dict(principal.scope.model_dump(), role="reviewer")],
        workflow.admission,
    )
    summary = worker.result_summary()
    assert summary["specimens"][s.id] == {
        "state": "blocked",
        "blocker": "pilot_clearance_forbidden",
    }
    assert summary["status"] == "incomplete"
