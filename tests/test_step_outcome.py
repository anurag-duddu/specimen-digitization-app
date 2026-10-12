"""A step that fails after its external effect settled is a known block (issue #80)."""

import pytest

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
        json={
            "action": "retry",
            "expected_revision": result.version,
            "reason": "integrity cause fixed",
        },
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


class FlakyExtraction(ExtractingAdapters):
    """The extraction call fails with an HTTP 5xx `failures` times, then answers."""

    def __init__(self, blobs, failures):
        super().__init__(blobs)
        self.failures = failures

    def extract(self, specimen):
        from specimen_digitization.application.domain import LookupStatus
        from specimen_digitization.application.reliability import AdapterFailure

        self.extractions += 1
        if self.extractions <= self.failures:
            raise AdapterFailure("model_provider_error", LookupStatus.PROVIDER, outcome_unknown=True)




@pytest.mark.parametrize(("failures", "given_up"), [(1, False), (3, True)])
def test_a_retried_parse_keeps_one_evidence_row_per_parsed_line(tmp_path, failures, given_up):
    # 2026-10-12 review: parse ran into the persisted run before the extraction,
    # so a retried extraction left the parsed lines' evidence behind and the next
    # attempt added it again.
    from datetime import datetime, timedelta, timezone

    c = client(tmp_path)
    row = intake(c)
    repo = SQLiteRepository(tmp_path / "state.sqlite3")
    blobs = LocalBlobs(tmp_path / "blobs")
    scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
    principal = Principal(user_id="synthetic-reviewer", scope=scope, role="reviewer")
    specimen = repo.get(scope, row["specimen_id"])
    specimen.run = Run(profile=specimen.run.profile)
    repo.save(principal, specimen, specimen.version, "new-run", digest({"new": True}))
    adapters = FlakyExtraction(blobs, failures)
    now = [datetime.now(timezone.utc)]
    workflow = Workflow(repo, blobs, adapters, clock=lambda: now[0])

    for _ in range(failures + 1):
        result = workflow.drain(principal, specimen.id)
        if result.run.stage != "retry_scheduled":
            break
        now[0] += timedelta(hours=1)

    run = result.run
    assert run.stage == "finalized" and "parse" in run.completed_steps
    assert adapters.extractions == min(failures + 1, 3)
    assert any(f.rule_id == "extraction_given_up" for f in run.findings) is given_up
    lines = [e.excerpt for e in run.evidence if e.kind == "literal" and e.source == "label"]
    assert lines and len(lines) == len(set(lines))
    # Each parsed field cites the one row its line has.
    cited = [i for field in run.fields.values() for i in field.evidence_ids]
    assert set(cited) <= {e.id for e in run.evidence}
