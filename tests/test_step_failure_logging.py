"""A failed workflow step leaves one WARNING line an operator can act on.

Before this, the worker's step failures (``AdapterFailure``, ``OperationalBlock``,
the deadline override) wrote nothing to the process log, and the unexpected-error
branch wrote only to Logfire. The blocker was visible only in the stored snapshot,
so Cloud Run showed a successful execution with no hint of which run or step
failed. The line names codes and classes only: never a provider body, a prompt, a
response or label text.
"""

import logging

import pytest
from pydantic_ai.exceptions import ModelHTTPError
from test_application import client, intake
from test_step_outcome import ExtractingAdapters, drain_to_parse_failure

from specimen_digitization.application import workflow as workflow_module
from specimen_digitization.application.api import (
    SYNTHETIC_COLLECTION,
    SYNTHETIC_ORG,
    SYNTHETIC_TEXT,
)
from specimen_digitization.application.domain import (
    LookupStatus,
    Principal,
    Run,
    Scope,
)
from specimen_digitization.application.integrity import EvidenceIntegrityError
from specimen_digitization.application.reliability import AdapterFailure
from specimen_digitization.application.storage import (
    LocalBlobs,
    SQLiteRepository,
    digest,
)
from specimen_digitization.application.workflow import (
    OperationalBlock,
    SyntheticAdapters,
    Workflow,
)

WORKFLOW_LOGGER = "specimen_digitization.application.workflow"
PREFIX = "Specimen step failed: "
CANARY = "LABEL-TEXT-CANARY-Smith-1923"


@pytest.fixture(autouse=True)
def capture_workflow_log(caplog):
    caplog.set_level(logging.DEBUG, logger=WORKFLOW_LOGGER)


def failure_records(caplog):
    return [
        record
        for record in caplog.records
        if record.name == WORKFLOW_LOGGER and record.getMessage().startswith(PREFIX)
    ]


def only_failure(caplog):
    (record,) = failure_records(caplog)
    assert record.levelno == logging.WARNING
    assert record.exc_info is None and record.exc_text is None
    assert "\n" not in record.getMessage()
    assert CANARY not in caplog.text
    pairs = record.getMessage().removeprefix(PREFIX).split(" ")
    return dict(pair.split("=", 1) for pair in pairs)


def raising(error_factory):
    def extract(self, specimen):
        self.extractions += 1
        raise error_factory()

    return extract


def adapter_failure(code, status, *, outcome_unknown=False, cause=None):
    def make():
        error = AdapterFailure(code, status, outcome_unknown=outcome_unknown)
        error.__cause__ = cause
        return error

    return make


def test_operational_block_logs_run_step_code_and_cause_class(
    tmp_path, monkeypatch, caplog
):
    _, _, result = drain_to_parse_failure(
        tmp_path, monkeypatch, EvidenceIntegrityError("evidence_integrity_failure")
    )

    assert result.run.blocker == "evidence_integrity_failure"
    fields = only_failure(caplog)
    assert fields["run"] == result.run.id
    assert fields["step"] == "parse"
    assert fields["branch"] == "operational_block"
    assert fields["code"] == "evidence_integrity_failure"
    assert fields["blocker"] == "evidence_integrity_failure"
    assert fields["stage"] == "processing_blocked"
    assert fields["error_class"] == "OperationalBlock"
    assert fields["cause_class"] == "EvidenceIntegrityError"
    assert fields["attempt"] == "1"


def test_unexpected_error_logs_its_class_and_never_its_message(
    tmp_path, monkeypatch, caplog
):
    _, _, result = drain_to_parse_failure(tmp_path, monkeypatch, KeyError(CANARY))

    assert result.run.blocker == "stage_failed_inspect_private_worker_logs"
    fields = only_failure(caplog)
    assert fields["run"] == result.run.id
    assert fields["step"] == "parse"
    assert fields["branch"] == "unexpected_exception"
    assert fields["error_class"] == "KeyError"
    assert fields["blocker"] == "stage_failed_inspect_private_worker_logs"
    assert fields["outcome_unknown"] == "False"


def test_unexpected_error_before_the_provider_answered_logs_outcome_unknown(
    tmp_path, monkeypatch, caplog
):
    monkeypatch.setattr(
        ExtractingAdapters, "extract", raising(lambda: RuntimeError(CANARY))
    )
    _, _, result = drain_to_parse_failure(tmp_path, monkeypatch, None)

    assert result.run.blocker == "external_outcome_unknown"
    fields = only_failure(caplog)
    assert fields["branch"] == "unexpected_exception"
    assert fields["error_class"] == "RuntimeError"
    assert fields["blocker"] == "external_outcome_unknown"
    assert fields["outcome_unknown"] == "True"
    assert fields["attempt"] == "1"


def test_malformed_response_logs_status_and_code(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(
        ExtractingAdapters,
        "extract",
        raising(adapter_failure("model_malformed_response", LookupStatus.MALFORMED)),
    )
    _, _, result = drain_to_parse_failure(tmp_path, monkeypatch, None)

    assert result.run.blocker == "model_malformed_response"
    fields = only_failure(caplog)
    assert fields["run"] == result.run.id
    assert fields["step"] == "parse"
    assert fields["branch"] == "adapter_failure"
    assert fields["status"] == "malformed_response"
    assert fields["code"] == "model_malformed_response"
    assert fields["blocker"] == "model_malformed_response"
    assert fields["error_class"] == "AdapterFailure"
    assert fields["outcome_unknown"] == "False"


def test_ambiguous_provider_failure_logs_the_code_the_blocker_hides(
    tmp_path, monkeypatch, caplog
):
    def cause():
        return ModelHTTPError(502, "reader-model", body=CANARY)

    monkeypatch.setattr(
        ExtractingAdapters,
        "extract",
        raising(
            adapter_failure(
                "model_provider_error",
                LookupStatus.PROVIDER,
                outcome_unknown=True,
                cause=cause(),
            )
        ),
    )
    _, _, result = drain_to_parse_failure(tmp_path, monkeypatch, None)

    # The stored blocker says only "unknown"; the log says why.
    assert result.run.blocker == "external_outcome_unknown"
    fields = only_failure(caplog)
    assert fields["branch"] == "adapter_failure"
    assert fields["blocker"] == "external_outcome_unknown"
    assert fields["code"] == "model_provider_error"
    assert fields["status"] == "provider_error"
    assert fields["outcome_unknown"] == "True"
    assert fields["cause_class"] == "ModelHTTPError"
    assert fields["http_status"] == "502"


def test_model_step_failure_rebuilt_in_the_parent_logs_the_code_without_a_cause(
    tmp_path, monkeypatch, caplog
):
    # Production model calls run in an isolated child process; invoke_model
    # rebuilds the AdapterFailure from JSON (code, status, retry, outcome_unknown),
    # so the parent sees no __cause__ and no HTTP status. The code is still logged.
    monkeypatch.setattr(
        ExtractingAdapters,
        "extract",
        raising(
            adapter_failure(
                "model_provider_error", LookupStatus.PROVIDER, outcome_unknown=True
            )
        ),
    )
    _, _, result = drain_to_parse_failure(tmp_path, monkeypatch, None)

    assert result.run.blocker == "external_outcome_unknown"
    fields = only_failure(caplog)
    assert fields["code"] == "model_provider_error"
    assert fields["blocker"] == "external_outcome_unknown"
    assert fields["outcome_unknown"] == "True"
    assert fields["cause_class"] == "-"
    assert fields["http_status"] == "-"


class UninspectableError(Exception):
    """An error whose attributes raise when the logging code reads them."""

    @property
    def status_code(self):
        raise ValueError("raised while the failure was being logged")


def test_a_failure_that_cannot_be_logged_does_not_change_the_step_outcome(
    tmp_path, monkeypatch, caplog
):
    monkeypatch.setattr(ExtractingAdapters, "extract", raising(UninspectableError))
    _, _, result = drain_to_parse_failure(tmp_path, monkeypatch, None)

    assert result.run.stage == "processing_blocked"
    assert result.run.blocker == "external_outcome_unknown"
    fields = only_failure(caplog)
    assert fields["branch"] == "unexpected_exception"
    assert fields["fields"] == "unavailable"


def test_retryable_provider_failure_logs_the_scheduled_retry(
    tmp_path, monkeypatch, caplog
):
    monkeypatch.setattr(
        ExtractingAdapters,
        "extract",
        raising(adapter_failure("model_rate_limited", LookupStatus.RATE_LIMITED)),
    )
    _, _, result = drain_to_parse_failure(tmp_path, monkeypatch, None)

    assert result.run.stage == "retry_scheduled"
    fields = only_failure(caplog)
    assert fields["branch"] == "adapter_failure"
    assert fields["status"] == "rate_limited"
    assert fields["code"] == "model_rate_limited"
    assert fields["stage"] == "retry_scheduled"
    assert fields["attempt"] == "1"


def test_a_blocker_that_is_not_a_code_is_never_logged(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(
        ExtractingAdapters,
        "extract",
        raising(lambda: OperationalBlock(CANARY + "\nsecond line")),
    )
    _, _, result = drain_to_parse_failure(tmp_path, monkeypatch, None)

    # The stored blocker is unchanged by this task; only the log line is guarded.
    assert result.run.blocker.startswith(CANARY)
    fields = only_failure(caplog)
    assert fields["branch"] == "operational_block"
    assert fields["code"] == "unrecognized"
    assert fields["blocker"] == "unrecognized"


class SlowSegmenter(SyntheticAdapters):
    """The segmentation call returns, but only after the effect deadline passed."""

    def __init__(self, blobs, text, clock):
        super().__init__(blobs, text)
        self.clock = clock

    def segment(self, specimen):
        self.clock[0] += 100_000
        return super().segment(specimen)


def test_deadline_override_logs_the_outcome_unknown_it_forces(
    tmp_path, monkeypatch, caplog
):
    c = client(tmp_path)
    row = intake(c)
    repo = SQLiteRepository(tmp_path / "state.sqlite3")
    blobs = LocalBlobs(tmp_path / "blobs")
    scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
    principal = Principal(user_id="synthetic-reviewer", scope=scope, role="reviewer")
    specimen = repo.get(scope, row["specimen_id"])
    specimen.run = Run(profile=specimen.run.profile)
    repo.save(principal, specimen, specimen.version, "new-run", digest({"new": True}))
    clock = [0.0]
    adapters = SlowSegmenter(blobs, SYNTHETIC_TEXT, clock)
    workflow = Workflow(repo, blobs, adapters, monotonic=lambda: clock[0])

    result = workflow.drain(principal, specimen.id)

    assert result.run.blocker == "external_outcome_unknown"
    assert result.run.reasons == ["external_stage_deadline_exceeded"]
    fields = only_failure(caplog)
    assert fields["run"] == result.run.id
    assert fields["step"] == "segment"
    assert fields["branch"] == "external_deadline_exceeded"
    assert fields["code"] == "external_stage_deadline_exceeded"
    assert fields["blocker"] == "external_outcome_unknown"
    assert float(fields["elapsed_seconds"]) > float(fields["effect_timeout_seconds"])


def test_a_step_that_succeeds_logs_no_failure(tmp_path, monkeypatch, caplog):
    _, adapters, result = drain_to_parse_failure(tmp_path, monkeypatch, None)

    assert adapters.extractions == 1
    assert result.run.stage != "processing_blocked"
    assert failure_records(caplog) == []


def test_logfire_warning_for_the_unexpected_branch_is_kept(
    tmp_path, monkeypatch, caplog
):
    warned = []
    monkeypatch.setattr(
        workflow_module.logfire,
        "warn",
        lambda message, **kw: warned.append((message, kw)),
    )
    drain_to_parse_failure(tmp_path, monkeypatch, KeyError(CANARY))

    assert warned == [
        (
            "Specimen step failed",
            {"step": "parse", "exception_class": "KeyError", "outcome_unknown": False},
        )
    ]
