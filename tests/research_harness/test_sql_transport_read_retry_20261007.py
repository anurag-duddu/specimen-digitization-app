"""Bounded fake-session SQL transport; no network, model or database effects."""
import copy
from datetime import datetime, timezone
import json

import pytest
from requests.exceptions import ReadTimeout

from specimen_digitization.application.production import SqlConnectRepository, actor_uid
from specimen_digitization.application.storage import Conflict
from specimen_digitization.application.workflow import OperationalBlock
from specimen_digitization.research_harness.compatibility import PublicationUnavailable
from specimen_digitization.research_harness.native_canonical import SqlConnectNativeOperationClient
from specimen_digitization.research_harness.persistence import (
    CasConflict, SqlConnectStateBackend, _SQL_SEMANTIC_READS,
)
from test_research_harness_persistence import fixture

CANARY = "PRIVATE_CANARY_BODY_ACTOR_TOKEN"


class Response:
    def __init__(self, data=None, *, status=200, body=None):
        self.status_code = status
        self.body = {"data": data} if body is None else body

    def json(self):
        return self.body


class Session:
    def __init__(self, outcomes):
        self.outcomes, self.calls = list(outcomes), []
        self.headers = {"Authorization": CANARY}

    def post(self, url, **kwargs):
        self.calls.append((url, copy.deepcopy(kwargs)))
        outcome = self.outcomes.pop(0)
        if callable(outcome):
            return outcome(kwargs)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def repository(session):
    return SqlConnectRepository(project="demo-specimen-data", emulator_host="127.0.0.1:9399", session=session)


def native_data(operation):
    field = {"GetCanonicalResearchBindingV2": "binding", "GetCanonicalResearchMaterializationInputsV2": "binding",
        "GetResearchPublicationIntentV2": "intent", "GetResearchPublicationReceiptV2": "retained"}.get(operation)
    return {field: {"exact_json": '{"quantity":15.0}'}} if field else {"locators": []}


@pytest.mark.parametrize("operation", sorted(_SQL_SEMANTIC_READS))
def test_explicit_semantic_query_retries_once_with_identical_body_session_and_exact_json(operation, caplog):
    session = Session([ReadTimeout(CANARY), Response(native_data(operation))])
    variables = {"actorUid": CANARY, "specimenId": CANARY, "operationDigest": "x" * 64}
    output = SqlConnectNativeOperationClient(repository(session)).execute(operation, variables)
    assert len(session.calls) == 2 and session.calls[0] == session.calls[1]
    assert session.calls[0][1] == {"json": {"operationName": operation, "variables": variables}, "timeout": 30}
    assert session.calls[0][0].endswith(":impersonateQuery")
    if operation != "GetRetainedResearchPublicationLocatorsV2":
        row = output[next(iter(output))]
        assert row["quantity"] == 15.0 and type(row["quantity"]) is float
    assert f"operation={operation} phase=http_request attempt=1" in caplog.text
    assert CANARY not in caplog.text


@pytest.mark.parametrize(("operation", "mutation"), [
    (name, True) for name in ("RetainResearchPublicationIntentV2", "RetainResearchPublicationPreparationV2",
        "MarkResearchPublicationAttemptV2", "PublishCanonicalResearchV2", "CompareResearchHarnessStateV1",
        "CreateResearchHarnessStateV1")
] + [("GetCanonicalResearchBindingV2", True), ("GetCanonicalResearchBindingV1", False), (CANARY, False)])
def test_writes_legacy_unknown_and_query_name_as_mutation_are_single_send(operation, mutation, caplog):
    session = Session([ReadTimeout(CANARY), Response({})])
    with pytest.raises(ReadTimeout) as error:
        SqlConnectNativeOperationClient(repository(session)).execute(operation, {"actorUid": CANARY}, mutation)
    assert len(session.calls) == 1
    assert CANARY not in caplog.text and CANARY not in " ".join(error.value.__notes__)


def test_final_read_timeout_exhausts_exactly_two_attempts_and_logs_only_safe_context(caplog):
    operation = "GetResearchPublicationIntentV2"
    session = Session([ReadTimeout(CANARY), ReadTimeout(CANARY), Response({})])
    with pytest.raises(ReadTimeout):
        SqlConnectNativeOperationClient(repository(session)).execute(operation, {"actorUid": CANARY})
    assert len(session.calls) == 2
    assert "attempt=1" in caplog.text and "attempt=2" in caplog.text and CANARY not in caplog.text


@pytest.mark.parametrize("status", (401, 403, 503))
def test_native_http_denial_or_unavailable_is_not_retried(status):
    session = Session([Response({}, status=status), Response({})])
    with pytest.raises(PermissionError if status in {401, 403} else PublicationUnavailable):
        SqlConnectNativeOperationClient(repository(session)).execute("GetResearchPublicationReceiptV2", {})
    assert len(session.calls) == 1


@pytest.mark.parametrize("body", ([1], {"errors": [{"message": CANARY}], "data": {}}, {"data": None}))
def test_native_graphql_or_malformed_envelope_is_not_retried_or_treated_as_absence(body, caplog):
    session = Session([Response(body=body), Response({})])
    with pytest.raises(PublicationUnavailable):
        SqlConnectNativeOperationClient(repository(session)).execute("GetResearchPublicationReceiptV2", {})
    assert len(session.calls) == 1 and CANARY not in caplog.text


def test_native_membership_failure_keeps_access_guard_and_is_single_send():
    session = Session([Response({"organizationMember": None, "collectionMember": None,
        "specimen": None, "binding": None}), Response({})])
    with pytest.raises(PermissionError):
        SqlConnectNativeOperationClient(repository(session)).execute("GetCanonicalResearchBindingV1", {})
    assert len(session.calls) == 1


class Clock:
    def __init__(self): self.now = 0.0
    def __call__(self): return self.now








def state_response(state=None, revision=1, observed=1_700_000_000):
    row = None if state is None else {"state": state, "stateJson": json.dumps(state), "revision": revision,
        "observedAt": datetime.fromtimestamp(observed, timezone.utc).isoformat()}
    return Response({"read": {"researchHarnessState": row}})


def test_clock_read_retries_only_observed_at_operation_and_preserves_actor_scope(tmp_path):
    store, scope, _lease, _broker, _blobs = fixture(tmp_path)
    state = store._read(scope).state
    session = Session([ReadTimeout("synthetic"), state_response(state)])
    token = actor_uid.set(scope.actor_uid)
    try:
        backend = SqlConnectStateBackend(repository(session))
        output = backend.load(scope, store.program_key)
    finally:
        actor_uid.reset(token)
    assert output.state == state and output.server_time == 1_700_000_000
    assert len(session.calls) == 2 and session.calls[0] == session.calls[1]
    url, call = session.calls[0]
    assert url.endswith(":impersonateMutation")
    assert call["json"] == {"operationName": "ReadResearchHarnessStateV1", "variables": {
        "organizationId": scope.organization_id, "collectionId": scope.collection_id,
        "actorUid": scope.actor_uid, "programKey": store.program_key, "specimenId": scope.specimen_id,
        "sensitive": scope.sensitive}}


@pytest.mark.parametrize(("response", "exception", "message"), (
    (Response({}, status=401), PermissionError, "SQL Connect access denied"),
    (Response({}, status=403), PermissionError, "SQL Connect access denied"),
    (Response({}, status=503), OperationalBlock, "sql_connect_unavailable_or_connector_not_published"),
    (Response(body={"errors": [{"message": CANARY}]}), Conflict,
     "SQL Connect transaction rejected; reload current revision and membership"),
    (Response(body=[1]), AttributeError, None),
    (Response({}), ValueError, "SQL Connect clock-read response invalid"),
    (Response({"read": {}}), ValueError, "SQL Connect clock-read response invalid"),
))
def test_clock_denial_graphql_and_malformed_data_preserve_mapping_without_retry(tmp_path, response, exception, message, caplog):
    store, scope, _lease, _broker, _blobs = fixture(tmp_path)
    session = Session([response, state_response()])
    token = actor_uid.set(scope.actor_uid)
    try:
        with pytest.raises(exception) as error:
            SqlConnectStateBackend(repository(session)).load(scope, store.program_key)
    finally:
        actor_uid.reset(token)
    if message: assert str(error.value) == message
    assert len(session.calls) == 1 and CANARY not in caplog.text


@pytest.mark.parametrize("action", ("create", "cas"))
def test_uncertain_state_write_is_single_send_then_uses_unchanged_clock_readback(tmp_path, action):
    store, scope, _lease, _broker, _blobs = fixture(tmp_path)
    document = store._read(scope)
    session = Session([ReadTimeout("synthetic"), state_response(document.state, document.revision + 1)])
    token = actor_uid.set(scope.actor_uid)
    try:
        backend = SqlConnectStateBackend(repository(session))
        with pytest.raises(CasConflict):
            if action == "create":
                backend.create(scope, store.program_key, document.state)
            else:
                backend.cas(scope, store.program_key, document.revision, document.state)
    finally:
        actor_uid.reset(token)
    expected = "CreateResearchHarnessStateV1" if action == "create" else "CompareResearchHarnessStateV1"
    assert [call["json"]["operationName"] for _, call in session.calls] == [expected, "ReadResearchHarnessStateV1"]
    assert session.calls[0][1]["json"]["variables"]["state"] == document.state
