"""The worker's queued-command exception preserves lifecycle and human locks."""
from types import ModuleType
import sys

import pytest

from specimen_digitization.research_harness.contracts import FieldKey, digest
from specimen_digitization.research_harness.persistence import ResearchStore, StaleWork
from specimen_digitization.research_harness.production_runtime import research_program_key

from test_provisioning import rig, job_scope  # noqa: F401

contracts = pytest.importorskip("specimen_digitization.research_harness.derivation_contracts")


@pytest.fixture
def queued(rig, monkeypatch):
    specimen = rig.specimen
    item = contracts.SettledDerivationInput(field_key=FieldKey.COUNTRY, value="Kenya",
        evidence_ids=("review-decision:offline-country",), revision=specimen.version - 1,
        authority_id="review-decision:offline-country", field_digest=digest(specimen.run.fields["country"]),
        review_decision_id="offline-country", provenance_blob_ref="e" * 64 + ":1",
        provenance_sha256="e" * 64, original_review_revision=specimen.version - 1)
    command = contracts.DerivationCommand(id="c" * 64, actor_uid="offline-reviewer",
        reason="Derive the missing province", source_revision=specimen.version - 1,
        queued_revision=specimen.version, canonical_run_id=specimen.run.id,
        source_snapshot_sha256="b" * 64, inputs=(item,),
        input_digest=contracts.derivation_input_digest((item,)),
        human_locked_fields=(FieldKey.COUNTRY, FieldKey.TAXON),
        requested_fields=(FieldKey.PROVINCE_STATE,), idempotency_key="offline-request", request_digest="a" * 64)
    specimen.run.dependencies["research_derivation_request"] = command.model_dump(mode="json")
    specimen.run.stage = "finalized"
    rig.repository.graph_blobs = object()
    rig.repository.version_info = lambda scope, ident, revision: {"sha256": "b" * 64}
    module = ModuleType("specimen_digitization.research_harness.derivation_inputs")
    rig.proof_checks = []
    def verify(repository, current, blobs, inputs, *, proofs=None):
        assert repository is rig.repository and current is specimen and blobs is rig.repository.graph_blobs
        assert tuple(inputs) == command.inputs and proofs == []
        rig.proof_checks.append("verified")
    module.verify_settled_inputs = verify
    module.genuine_human_locked_fields = lambda *args, **kwargs: (FieldKey.COUNTRY, FieldKey.TAXON)
    monkeypatch.setitem(sys.modules, module.__name__, module)
    rig.proof_module, rig.command = module, command
    return rig


@pytest.mark.parametrize("stage", ["finalized", "waiting_for_review"])
def test_verified_command_provisions_at_queue_revision_without_rewinding_science(queued, stage):
    queued.specimen.run.stage = stage
    before = queued.specimen.model_dump(mode="json")
    queued.provision()
    assert queued.specimen.model_dump(mode="json") == before and queued.proof_checks == ["verified"]
    store = ResearchStore(queued.backend, research_program_key(queued.specimen.run.id))
    job = store.job(job_scope(queued))
    assert job["record_revision"] == queued.command.queued_revision
    assert set(job["human_lock_proofs"]) == {"country", "taxon"}
    for key in ("country", "taxon"):
        assert job["fields"][key]["locked"] is True
        assert job["fields"][key]["work_state"] == "waiting_human"
    assert job["fields"]["province_state"]["locked"] is False


@pytest.mark.parametrize("change", ["missing", "run", "revision", "reason", "completed", "source_sha", "locks", "proof"])
def test_stage_alone_or_stale_unproved_command_cannot_create_a_job(queued, change):
    raw = queued.specimen.run.dependencies["research_derivation_request"]
    if change == "missing":
        queued.specimen.run.dependencies.pop("research_derivation_request")
    elif change == "run":
        raw["canonical_run_id"] = "another-run"
    elif change == "revision":
        queued.specimen.version += 1
    elif change == "reason":
        raw["reason"] = " "
    elif change == "completed":
        raw["status"] = "completed"
    elif change == "source_sha":
        queued.repository.version_info = lambda *args: {"sha256": "0" * 64}
    elif change == "locks":
        raw["human_locked_fields"].remove("taxon")
    else:
        def unproved(*args, **kwargs):
            raise ValueError("unproved original review")
        queued.proof_module.verify_settled_inputs = unproved
    with pytest.raises(StaleWork, match="research_provision_derivation_unproved"):
        queued.provision()
    assert queued.repository.inserts == [] and queued.writer.registered == []
