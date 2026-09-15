"""Every exception the API answers has one mapping, and it is pinned here.

`classify_error` was lifted out of the application's exception handler so the
single-decision route, the bulk decisions route and the server-side import all
name the same code for the same failure. That extraction is exactly the kind of
change that silently loses a branch: four of the mapped exceptions are
`ValueError` subclasses, so a lost override does not raise, it quietly reports
the generic input error, or worse the 503 default, and a permanent condition
starts looking retryable to the caller.

The order matters as much as the mapping. The `ValueError` arm of the chain
gives those four their message, and the standalone checks after it correct the
code and category without touching that message. A branch moved into the chain
would stop overriding; a branch moved above it would lose the message.
"""

import pytest

from specimen_digitization.application.api import classify_error
from specimen_digitization.application.active_graph import (
    GraphTooLarge,
    WorkspaceTooLarge,
)
from specimen_digitization.application.integrity import EvidenceIntegrityError
from specimen_digitization.application.runtime_auth import EmailVerificationRequired
from specimen_digitization.application.source_reader import SourceObjectChanged
from specimen_digitization.application.storage import (
    Conflict,
    Missing,
    SnapshotTooLarge,
)
from specimen_digitization.application.workflow import OperationalBlock

WORKSPACE_DETAILS = {
    "revision": 3,
    "record_version_id": "run:3",
    "summary_url": "/v1/organizations/o/specimens/s",
    "artifact_url": "/v1/organizations/o/specimens/s/active-graph?revision=3",
    "mutation_committed": True,
    "workspace_max_bytes": 1,
    "graph_max_bytes": 1,
    "artifact_sha256": "0" * 64,
    "artifact_size_bytes": 2,
}


@pytest.mark.parametrize(
    "exc,expected",
    [
        (PermissionError(), (403, "access_denied", "authorization")),
        (
            EmailVerificationRequired(),
            (403, "email_verification_required", "authorization"),
        ),
        (Missing("s"), (404, "not_found", "input")),
        (Conflict("stale"), (409, "revision_or_idempotency_conflict", "conflict")),
        (ValueError("bad"), (422, "invalid_input", "input")),
        # Added by the source registry: a storage object whose generation moved
        # between inventory and import. Unmapped it falls through to the 503
        # default, which tells a reviewer the server is broken when in fact the
        # object changed underneath them, and tells the caller to retry a
        # permanent condition.
        (SourceObjectChanged("generation moved"), (422, "source_object_changed", "conflict")),
        (SnapshotTooLarge("too big"), (413, "snapshot_too_large", "policy")),
        (GraphTooLarge("too big"), (413, "active_graph_limit_exceeded", "policy")),
        (
            WorkspaceTooLarge(WORKSPACE_DETAILS),
            (413, "workspace_artifact_required", "policy"),
        ),
        # These two keep the 503 default on purpose and contribute only their
        # message: an operational block is genuinely a runtime condition.
        (
            OperationalBlock("worker_not_ready"),
            (503, "runtime_unavailable", "operational"),
        ),
        (
            EvidenceIntegrityError("evidence_integrity_failure"),
            (503, "runtime_unavailable", "operational"),
        ),
    ],
    ids=lambda value: type(value).__name__ if isinstance(value, Exception) else "",
)
def test_every_mapped_exception_keeps_its_triple(exc, expected):
    status, code, category, _ = classify_error(exc)
    assert (status, code, category) == expected


@pytest.mark.parametrize(
    "exc",
    [
        SourceObjectChanged("generation moved"),
        SnapshotTooLarge("too big"),
        GraphTooLarge("too big"),
        WorkspaceTooLarge(WORKSPACE_DETAILS),
    ],
    ids=lambda value: type(value).__name__,
)
def test_a_value_error_subclass_keeps_its_own_message(exc):
    """The chain supplies the message; the override corrects only the code.

    Every one of these is a `ValueError`, so the chain has already set the
    message to the exception's own text by the time the override runs. An
    override that reset the message would replace a specific explanation with
    a generic one.
    """
    _, code, _, message = classify_error(exc)
    assert code != "invalid_input", "the override did not run"
    assert message == str(exc)[:200]


def test_an_unmapped_exception_is_the_operational_default():
    status, code, category, message = classify_error(RuntimeError("something"))
    assert (status, code, category) == (503, "runtime_unavailable", "operational")
    assert "inspect server configuration" in message


def test_no_mapped_exception_falls_through_to_the_default():
    """The regression this file exists for.

    A branch lost in a refactor of `classify_error` does not raise. It reports
    503 `runtime_unavailable`, which is indistinguishable from a real outage.
    """
    mapped = [
        PermissionError(),
        EmailVerificationRequired(),
        Missing("s"),
        Conflict("stale"),
        ValueError("bad"),
        SourceObjectChanged("generation moved"),
        SnapshotTooLarge("too big"),
        GraphTooLarge("too big"),
        WorkspaceTooLarge(WORKSPACE_DETAILS),
    ]
    for exc in mapped:
        status, code, _, _ = classify_error(exc)
        assert code != "runtime_unavailable", f"{type(exc).__name__} lost its mapping"
        assert status != 503, f"{type(exc).__name__} lost its mapping"
