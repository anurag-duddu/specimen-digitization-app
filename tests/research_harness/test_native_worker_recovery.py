"""A retained canonical commit must precede a freshly bound paid window."""
import asyncio
import copy
from types import SimpleNamespace
import pytest
from requests.exceptions import ReadTimeout

from specimen_digitization.research_harness.native_worker import (
    NativeResearchWorker, NativeResearchWorkerOutcomeV2,
)
from test_production_bridge import RESEARCH_SCOPE, principal
from test_native_canonical_v2_contract import basis_v1, causal, call, retained_fixture
from specimen_digitization.research_harness.compatibility import PublicationUnavailable
from specimen_digitization.research_harness.native_service import SqlConnectNativeCanonicalServiceV2
from specimen_digitization.research_harness.persistence import HeldUnknown


@pytest.mark.parametrize("publication_only", [False, True])
def test_retained_publication_reopens_binding_before_the_next_provider_window(publication_only):
    state = {"revision": 7, "retained": True, "pending": True}
    opened, released, provider_revisions = [], [], []

    class Factory:
        async def retained_publication_locators(self, *_):
            return ()

        async def open(self, *_args, **_kwargs):
            revision = state["revision"]
            opened.append(revision)

            async def run(*, role_limit):
                assert revision == state["revision"]
                provider_revisions.append(revision)
                state["pending"] = False

            return SimpleNamespace(
                binding=SimpleNamespace(research_scope=lambda: RESEARCH_SCOPE),
                scope="scope", lease=revision, role_window=1,
                publication_only=publication_only,
                engine=SimpleNamespace(run=run),
                store=SimpleNamespace(
                    _read=lambda _: SimpleNamespace(state={"outbox": {}}),
                    release=lambda _scope, lease, **_: released.append(lease),
                    job=lambda _: {"fields": {"country": {
                        "work_state": "pending" if state["pending"] else "resolved", "locked": False}}}),
            )

    class Worker(NativeResearchWorker):
        async def _publish_committed(self, *_args, publication_progress=None):
            if state["retained"]:
                state.update(retained=False, revision=8)
                publication_progress.append("retained-receipt")
            return NativeResearchWorkerOutcomeV2(scope=RESEARCH_SCOPE,
                status="pending" if state["pending"] else "completed",
                publication_receipt_ids=("retained-receipt",))

    result = asyncio.run(Worker(Factory()).run_registered(principal(),
        RESEARCH_SCOPE.specimen_id, owner="worker"))
    assert opened == [7, 8] and released == [7, 8]
    assert provider_revisions == ([] if publication_only else [8])
    assert result.status == ("blocked" if publication_only else "completed")
    assert result.reason_code == ("research_program_headroom_unavailable" if publication_only else None)
    assert result.publication_receipt_ids == ("retained-receipt",)


@pytest.fixture
def retained_timeout(causal, monkeypatch):
    """Actual V2 writer/receipt facade, with inert retained SQL responses.

    These controls prove response-loss handling, not a live SQL commit. The
    connector refuses every operation outside the two immutable receipt reads.
    """
    c = causal
    writer, connector = retained_fixture(c)
    service = SqlConnectNativeCanonicalServiceV2(connector, None, blobs=None,
        materializer=None, evidence_provider=None, projection_services=None, operation_client=connector)
    assert writer.journal is None and service.writer.journal is None
    original = connector.execute
    requests = []
    receipts = []
    first_error = ReadTimeout("synthetic lost receipt response")

    def execute(operation, variables, mutation=False):
        requests.append((operation, copy.deepcopy(variables), mutation))
        assert mutation is False
        if operation == "GetResearchPublicationReceiptV2":
            receipts.append(operation)
            if len(receipts) == 1:
                raise first_error
        return original(operation, variables, mutation=mutation)

    monkeypatch.setattr(connector, "execute", execute)
    worker = NativeResearchWorker(None)
    # The legacy contract fixture deliberately uses an opaque job id outside
    # telemetry's syntax. Exercise the actual writer and receipt facade without
    # substituting a different scientific scope or disabling production checks.
    runtime = SimpleNamespace(canonical_service=SimpleNamespace(
        publish_checkpoint=writer.publish_checkpoint, winning_receipt=service.winning_receipt))
    before = copy.deepcopy((c.p.model_dump(mode="json"), c.state, connector.row, connector.intent_row))

    def recover():
        return call(c, lambda: worker._publish_checkpoint(runtime, c.b.principal,
            c.p.basis.scope.specimen_id, c.p, c.intent.server_request_identity_digest))

    return SimpleNamespace(c=c, connector=connector, service=service, requests=requests,
        receipts=receipts, first_error=first_error, before=before, recover=recover)


def test_lost_publication_response_recovers_only_the_exact_retained_winner(retained_timeout):
    case = retained_timeout
    result = case.recover()
    assert result.replayed and result.causal.intent_id == case.c.intent.id
    assert result.causal.winning_preparation_id == case.c.prep.id
    assert result.causal.native_commit == case.connector.row["publication"]
    assert (case.c.p.model_dump(mode="json"), case.c.state, case.connector.row,
        case.connector.intent_row) == case.before
    assert [operation for operation, _, _ in case.requests] == [
        "GetResearchPublicationIntentV2", "GetResearchPublicationReceiptV2",
        "GetResearchPublicationIntentV2", "GetResearchPublicationIntentV2",
        "GetResearchPublicationReceiptV2"]
    assert all(variables["idempotencyKey"] == case.c.p.basis.idempotency_key
        for _, variables, _ in case.requests)
    assert all(variables["requestIdentityDigest"] == case.c.intent.server_request_identity_digest
        for operation, variables, _ in case.requests if operation == "GetResearchPublicationIntentV2")


def test_timeout_with_retained_attempt_and_no_winner_remains_held(retained_timeout):
    case = retained_timeout
    case.connector.row = None
    with pytest.raises(HeldUnknown, match="native_publication_receipt_requires_reconciliation"):
        case.recover()
    assert len(case.receipts) == 2 and case.c.state == case.before[1]
    assert case.connector.intent_row == case.before[3]
    assert all(operation.startswith("GetResearchPublication") and not mutation
        for operation, _, mutation in case.requests)


def test_timeout_without_winner_or_attempt_does_not_resume_mutable_publication(retained_timeout):
    case = retained_timeout
    case.connector.row = None
    case.connector.intent_row["attempt"] = None
    with pytest.raises(ReadTimeout) as caught:
        case.recover()
    assert caught.value is case.first_error and len(case.receipts) == 2
    assert case.c.state == case.before[1]
    assert all(operation.startswith("GetResearchPublication") and not mutation
        for operation, _, mutation in case.requests)


def test_second_receipt_timeout_stops_without_another_publication(retained_timeout, monkeypatch):
    case = retained_timeout
    original = case.connector.execute

    def timeouts(operation, variables, mutation=False):
        if operation == "GetResearchPublicationReceiptV2" and case.receipts:
            case.requests.append((operation, copy.deepcopy(variables), mutation))
            case.receipts.append(operation)
            raise ReadTimeout("synthetic recovery read timeout")
        return original(operation, variables, mutation=mutation)

    monkeypatch.setattr(case.connector, "execute", timeouts)
    with pytest.raises(ReadTimeout, match="synthetic recovery read timeout"):
        case.recover()
    assert len(case.receipts) == 2 and case.c.state == case.before[1]
    assert all(not mutation for _, _, mutation in case.requests)


@pytest.mark.parametrize("error", [PublicationUnavailable("native_v2_receipt_partial"),
    PermissionError("synthetic denied member"), ValueError("synthetic validation failure")])
def test_nontransport_publication_failure_does_not_read_or_retry_a_winner(retained_timeout, monkeypatch, error):
    case = retained_timeout
    original = case.connector.execute

    def rejected(operation, variables, mutation=False):
        if operation == "GetResearchPublicationReceiptV2":
            case.requests.append((operation, copy.deepcopy(variables), mutation))
            raise error
        return original(operation, variables, mutation=mutation)

    monkeypatch.setattr(case.connector, "execute", rejected)
    with pytest.raises(type(error)) as caught:
        case.recover()
    assert caught.value is error
    assert [operation for operation, _, _ in case.requests] == [
        "GetResearchPublicationIntentV2", "GetResearchPublicationReceiptV2"]
    assert case.c.state == case.before[1]


def test_timeout_recovery_keeps_the_existing_worker_deadline(retained_timeout, monkeypatch):
    from specimen_digitization.application.worker_deadline import WorkerDeadline, WorkerDeadlineExceeded
    case = retained_timeout
    original = case.connector.execute
    clock = [0.0]

    def expired(operation, variables, mutation=False):
        if operation == "GetResearchPublicationReceiptV2":
            clock[0] = 2.0
        return original(operation, variables, mutation=mutation)

    monkeypatch.setattr(case.connector, "execute", expired)
    with WorkerDeadline(1.0, monotonic=lambda: clock[0]).scope():
        with pytest.raises(WorkerDeadlineExceeded):
            case.recover()
    assert len(case.receipts) == 1
    assert len(case.requests) == 2 and case.c.state == case.before[1]
