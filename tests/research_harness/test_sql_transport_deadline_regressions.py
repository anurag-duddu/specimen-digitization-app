"""Synthetic SQL transport clocks and custody; no network or live timing proof."""

import copy
from dataclasses import replace
from types import SimpleNamespace

import pytest
from requests.exceptions import ReadTimeout

from specimen_digitization.application.production import SqlConnectRepository, actor_uid
from specimen_digitization.application.worker_deadline import (
    WorkerDeadline,
    WorkerDeadlineExceeded,
    current_deadline,
)
from specimen_digitization.research_harness.native_canonical import SqlConnectNativeOperationClient
from specimen_digitization.research_harness.persistence import (
    HeldUnknown,
    ResearchStore,
    SqlConnectStateBackend,
)
from test_research_harness_persistence import fixture
from test_sql_transport_read_retry_20261007 import (
    CANARY,
    Clock,
    Response,
    Session,
    native_data,
    repository,
    state_response,
)


OPERATION = "GetResearchPublicationIntentV2"
LOGGER = "specimen_digitization.research_harness.persistence"


def transport_records(caplog):
    return [record for record in caplog.records if record.name == LOGGER]


def assert_safe_context(caplog, operation, phase, attempt):
    message = f"SQL Connect transport operation={operation} phase={phase} attempt={attempt}"
    records = transport_records(caplog)
    assert any(record.getMessage() == message for record in records)
    assert all(record.exc_info is None and record.stack_info is None for record in records)
    assert CANARY not in caplog.text


def test_retries_keep_the_same_parent_deadline_and_clamp_each_socket_timeout(caplog):
    clock = Clock()
    published = []
    parent = WorkerDeadline(45, monotonic=clock, publish=published.append)

    def first(_):
        assert current_deadline() is parent
        clock.now = 30
        raise ReadTimeout(CANARY)

    def second(_):
        assert current_deadline() is parent
        clock.now = 44
        return Response(native_data(OPERATION))

    session = Session([first, second])
    variables = {"actorUid": CANARY, "privateVariable": CANARY}
    with parent.scope():
        result = SqlConnectNativeOperationClient(repository(session)).execute(OPERATION, variables)
        assert current_deadline() is parent
    assert result == {"intent": {"quantity": 15.0}}
    assert [kwargs["timeout"] for _, kwargs in session.calls] == [30, 15]
    assert session.calls[0][1]["json"] == session.calls[1][1]["json"]
    assert parent.deadline == 45 and published == []
    assert current_deadline() is None
    assert_safe_context(caplog, OPERATION, "http_request", 1)


def test_first_socket_timeout_is_clamped_to_already_elapsed_parent_budget():
    clock = Clock()
    clock.now = 43
    parent = WorkerDeadline(45, monotonic=clock)
    session = Session([Response(native_data(OPERATION))])
    with parent.scope():
        SqlConnectNativeOperationClient(repository(session)).execute(OPERATION, {})
    assert session.calls[0][1]["timeout"] == 2
    assert parent.deadline == 45


def test_expired_parent_rejects_admission_before_any_http_send(caplog):
    clock = Clock()
    parent = WorkerDeadline(5, monotonic=clock)
    session = Session([Response(native_data(OPERATION))])
    with parent.scope():
        clock.now = 5
        with pytest.raises(WorkerDeadlineExceeded) as error:
            SqlConnectNativeOperationClient(repository(session)).execute(OPERATION, {"actorUid": CANARY})
    assert session.calls == []
    assert_safe_context(caplog, OPERATION, "request_admission", 1)
    assert error.value.__notes__ == [f"sql_connect_operation={OPERATION}; phase=request_admission; attempt=1"]


@pytest.mark.parametrize("late_timeout", (False, True))
def test_parent_expiry_during_send_exposes_neither_late_response_nor_retry(late_timeout, caplog):
    clock = Clock()
    parent = WorkerDeadline(5, monotonic=clock)

    def late(_):
        clock.now = 5
        if late_timeout:
            raise ReadTimeout(CANARY)
        return Response(native_data(OPERATION))

    session = Session([late, Response(native_data(OPERATION))])
    with parent.scope():
        with pytest.raises(WorkerDeadlineExceeded) as error:
            SqlConnectNativeOperationClient(repository(session)).execute(OPERATION, {"actorUid": CANARY})
    assert len(session.calls) == 1
    assert session.calls[0][1]["timeout"] == 5
    assert parent.deadline == 5
    assert_safe_context(caplog, OPERATION, "http_request", 1)
    assert CANARY not in " ".join(error.value.__notes__)


def test_parent_expiry_during_response_decode_exposes_no_result_or_retry(caplog):
    clock = Clock()
    parent = WorkerDeadline(5, monotonic=clock)

    class LateDecode(Response):
        def json(self):
            clock.now = 5
            return super().json()

    session = Session([LateDecode(native_data(OPERATION)), Response(native_data(OPERATION))])
    with parent.scope():
        with pytest.raises(WorkerDeadlineExceeded):
            SqlConnectNativeOperationClient(repository(session)).execute(OPERATION, {"actorUid": CANARY})
    assert len(session.calls) == 1 and parent.deadline == 5
    assert_safe_context(caplog, OPERATION, "response_validation", 1)


@pytest.mark.parametrize("finish", (59.5, 60.0))
def test_no_parent_read_budget_is_sixty_seconds_across_both_attempts(monkeypatch, finish, caplog):
    clock = Clock()
    monkeypatch.setattr("specimen_digitization.research_harness.persistence.time.monotonic", clock)
    assert current_deadline() is None

    def first(_):
        # Fake an SDK overrun; the transport does not preempt synchronous work.
        clock.now = 50
        raise ReadTimeout(CANARY)

    def second(_):
        clock.now = finish
        return Response(native_data(OPERATION))

    session = Session([first, second, Response(native_data(OPERATION))])
    client = SqlConnectNativeOperationClient(repository(session))
    if finish == 60:
        with pytest.raises(ReadTimeout, match="semantic read deadline exceeded"):
            client.execute(OPERATION, {"privateVariable": CANARY})
        assert_safe_context(caplog, OPERATION, "response_validation", 2)
    else:
        assert client.execute(OPERATION, {"privateVariable": CANARY}) == {"intent": {"quantity": 15.0}}
    assert [kwargs["timeout"] for _, kwargs in session.calls] == [30, 10]
    assert current_deadline() is None
    assert_safe_context(caplog, OPERATION, "http_request", 1)


def test_read_budget_does_not_extend_a_longer_parent_when_decode_finishes_at_sixty(caplog):
    clock = Clock()
    parent = WorkerDeadline(120, monotonic=clock)

    def first(_):
        clock.now = 30
        raise ReadTimeout(CANARY)

    def second(_):
        clock.now = 60
        return Response(native_data(OPERATION))

    session = Session([first, second])
    with parent.scope():
        with pytest.raises(ReadTimeout, match="semantic read deadline exceeded"):
            SqlConnectNativeOperationClient(repository(session)).execute(OPERATION, {})
        assert current_deadline() is parent
        parent.check()
    assert [kwargs["timeout"] for _, kwargs in session.calls] == [30, 30]
    assert parent.deadline == 120
    assert_safe_context(caplog, OPERATION, "response_validation", 2)


def test_verified_actor_change_before_second_clock_read_prevents_the_send(tmp_path, caplog):
    original, scope, _lease, _broker, _blobs = fixture(tmp_path)
    state = original._read(scope).state

    def first(_):
        actor_uid.set(CANARY)
        raise ReadTimeout(CANARY)

    session = Session([first, state_response(state)])
    token = actor_uid.set(scope.actor_uid)
    try:
        with pytest.raises(PermissionError, match="Scope actor differs from verified repository context") as error:
            SqlConnectStateBackend(repository(session)).load(scope, original.program_key)
    finally:
        actor_uid.reset(token)
    assert len(session.calls) == 1
    assert session.calls[0][1]["json"]["variables"]["actorUid"] == scope.actor_uid
    assert_safe_context(caplog, "ReadResearchHarnessStateV1", "http_request", 1)
    assert_safe_context(caplog, "ReadResearchHarnessStateV1", "authorization", 2)
    assert error.value.__notes__ == [
        "sql_connect_operation=ReadResearchHarnessStateV1; phase=authorization; attempt=2"
    ]


@pytest.mark.parametrize("execute_only", (False, True))
@pytest.mark.parametrize("raises_timeout", (False, True))
def test_custom_execute_is_preserved_even_with_session_and_url_attributes(
    tmp_path, execute_only, raises_timeout, caplog
):
    original, scope, _lease, _broker, _blobs = fixture(tmp_path)
    state = original._read(scope).state
    calls = []

    class Override(SqlConnectRepository):
        def execute(self, operation, variables, mutation=False):
            calls.append((operation, copy.deepcopy(variables), mutation))
            if raises_timeout:
                raise ReadTimeout(CANARY)
            return state_response(state, revision=7).json()["data"]

    session = Session([])
    override = Override(project="demo-specimen-data", emulator_host="127.0.0.1:9399", session=session)
    adapter = SimpleNamespace(variables=override.variables, execute=override.execute,
        session=session, url=override.url) if execute_only else override
    token = actor_uid.set(scope.actor_uid)
    try:
        backend = SqlConnectStateBackend(adapter)
        if raises_timeout:
            with pytest.raises(ReadTimeout) as error:
                backend.load(scope, original.program_key)
            assert_safe_context(caplog, "ReadResearchHarnessStateV1", "adapter_execute", 1)
            assert CANARY not in " ".join(error.value.__notes__)
        else:
            output = backend.load(scope, original.program_key)
            assert output.state == state and output.revision == 7
    finally:
        actor_uid.reset(token)
    assert session.calls == []
    assert len(calls) == 1
    assert calls[0] == ("ReadResearchHarnessStateV1", {
        "organizationId": scope.organization_id, "collectionId": scope.collection_id,
        "actorUid": scope.actor_uid, "programKey": original.program_key,
        "specimenId": scope.specimen_id, "sensitive": scope.sensitive,
    }, True)


def test_clock_only_read_replays_exact_state_and_revision_with_new_observed_time(tmp_path):
    original, scope, _lease, _broker, _blobs = fixture(tmp_path)
    document = original._read(scope)
    state = copy.deepcopy(document.state)
    retained = copy.deepcopy(state)
    observed = int(document.server_time) + 1
    session = Session([ReadTimeout("synthetic"), state_response(state, document.revision, observed)])
    token = actor_uid.set(scope.actor_uid)
    try:
        output = SqlConnectStateBackend(repository(session)).load(scope, original.program_key)
    finally:
        actor_uid.reset(token)
    assert output.state == retained and output.revision == document.revision
    assert output.server_time == observed and state == retained
    assert len(session.calls) == 2 and session.calls[0] == session.calls[1]
    assert session.calls[0][0].endswith(":impersonateMutation")
    assert session.calls[0][1]["json"]["operationName"] == "ReadResearchHarnessStateV1"
    assert original._read(scope).state == retained


def test_retried_clock_read_retains_pending_publication_lease_before_any_cas(tmp_path):
    original, scope, lease, _broker, _blobs = fixture(tmp_path)
    document = original._read(scope)
    state = copy.deepcopy(document.state)
    lease = replace(lease, fence=2)
    state["jobs"][scope.key]["fence"] = 2
    state["jobs"][scope.key]["lease"]["fence"] = 2
    state["outbox"]["pending"] = {
        "kind": "canonical_publication_required", "delivered": False,
        "guard": {"scope": scope.identity()},
    }
    retained = copy.deepcopy(state)
    session = Session([ReadTimeout("synthetic"), state_response(state, document.revision, document.server_time + 1)])
    token = actor_uid.set(scope.actor_uid)
    try:
        store = ResearchStore(SqlConnectStateBackend(repository(session)), original.program_key)
        with pytest.raises(HeldUnknown, match="publication in doubt retains its lease custody"):
            store.release(scope, lease, blocked=True)
    finally:
        actor_uid.reset(token)
    assert state == retained and state["jobs"][scope.key]["lease"]["fence"] == 2
    assert len(session.calls) == 2
    assert [call["json"]["operationName"] for _, call in session.calls] == ["ReadResearchHarnessStateV1"] * 2
