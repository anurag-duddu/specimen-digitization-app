"""A step that fails after its external effect settled is a known block (issue #80)."""

from test_application import HEADERS, PREFIX, client, intake

from specimen_digitization.application import workflow as workflow_module
from specimen_digitization.application.api import (
    SYNTHETIC_COLLECTION,
    SYNTHETIC_ORG,
    SYNTHETIC_TEXT,
)
from specimen_digitization.application.domain import Principal, Run, Scope
from specimen_digitization.application.integrity import EvidenceIntegrityError
from specimen_digitization.application.storage import (
    LocalBlobs,
    SQLiteRepository,
    digest,
)
from specimen_digitization.application.workflow import SyntheticAdapters, Workflow


class ExtractingAdapters(SyntheticAdapters):
    """Synthetic adapters whose extraction call makes `parse` an external step."""

    def __init__(self, blobs, *, fail_inside_effect=False):
        super().__init__(blobs, SYNTHETIC_TEXT)
        self.extractions = 0
        self.fail_inside_effect = fail_inside_effect

    def extract(self, specimen):
        self.extractions += 1
        if self.fail_inside_effect:
            raise RuntimeError("connection dropped before the provider answered")


def drain_to_parse_failure(tmp_path, monkeypatch, phase_error, **adapter_options):
    c = client(tmp_path)
    row = intake(c)
    repo = SQLiteRepository(tmp_path / "state.sqlite3")
    blobs = LocalBlobs(tmp_path / "blobs")
    scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
    principal = Principal(user_id="synthetic-reviewer", scope=scope, role="reviewer")
    specimen = repo.get(scope, row["specimen_id"])
    specimen.run = Run(profile=specimen.run.profile)
    repo.save(principal, specimen, specimen.version, "new-run", digest({"new": True}))
    real_execute_phase = workflow_module.execute_phase

    def execute_phase(specimen, phase, blobs):
        if phase == "parse" and phase_error is not None:
            raise phase_error
        return real_execute_phase(specimen, phase, blobs)

    monkeypatch.setattr(workflow_module, "execute_phase", execute_phase)
    adapters = ExtractingAdapters(blobs, **adapter_options)
    result = Workflow(repo, blobs, adapters).drain(principal, specimen.id)
    return c, adapters, result


def test_integrity_failure_after_extraction_is_a_known_retryable_block(
    tmp_path, monkeypatch
):
    c, adapters, result = drain_to_parse_failure(
        tmp_path, monkeypatch, EvidenceIntegrityError("evidence_integrity_failure")
    )

    assert adapters.extractions == 1
    assert result.run.stage == "processing_blocked"
    assert result.run.blocker == "evidence_integrity_failure"
    assert result.run.lease_until is None
    retry = c.post(
        PREFIX + f"/runs/{result.run.id}/actions",
        headers=HEADERS,
        json={"action": "retry", "reason": "integrity cause fixed"},
    )
    assert retry.status_code == 200, retry.text


def test_unexpected_failure_after_extraction_is_a_known_block(tmp_path, monkeypatch):
    _, adapters, result = drain_to_parse_failure(tmp_path, monkeypatch, KeyError("x"))

    assert adapters.extractions == 1
    assert result.run.stage == "processing_blocked"
    assert result.run.blocker == "stage_failed_inspect_private_worker_logs"
    assert result.run.lease_until is None


def test_failure_inside_the_extraction_call_stays_unknown(tmp_path, monkeypatch):
    _, adapters, result = drain_to_parse_failure(
        tmp_path, monkeypatch, None, fail_inside_effect=True
    )

    assert adapters.extractions == 1
    assert result.run.stage == "processing_blocked"
    assert result.run.blocker == "external_outcome_unknown"
