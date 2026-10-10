"""A specimen id that is not a UUID names no specimen: 404, never a 409 conflict.

GetSpecimen takes `$id: UUID!`, so Data Connect refuses a request for
"subject_105526321" with a GraphQL error, and SqlConnectRepository.execute turns any
GraphQL error into Conflict (409 revision_or_idempotency_conflict). Production answered
workspace requests for such ids with 409 (2026-10-09).
"""

import logging
import sys
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from specimen_digitization.application.api import create_app
from specimen_digitization.application.domain import Scope
from specimen_digitization.application.production import SqlConnectRepository, actor_uid
from specimen_digitization.application.storage import Conflict, Missing
from specimen_digitization.application.workflow import SyntheticAdapters

sys.path.insert(0, str(Path(__file__).resolve().parent / "research_harness"))
import production_e2e_support as support  # noqa: E402

SCOPE = Scope(organization_id=support.ORG, collection_id=support.COLLECTION)
NOT_A_UUID = "subject_105526321"
INVALID_UUID = {"errors": [{"message": f'invalid value "{NOT_A_UUID}" for $id: UUID!',
                            "extensions": {"code": "INVALID_ARGUMENT"}}]}


class Response:
    def __init__(self, body):
        self.status_code, self.body = 200, body

    def json(self):
        return self.body


class TypedSession:
    """Answers GetSpecimen as the connector does: a GraphQL error for an id that is not a UUID."""

    def __init__(self):
        self.calls = []

    def post(self, url, json, timeout):
        self.calls.append((json["operationName"], json["variables"]))
        try:
            UUID(json["variables"]["id"])
        except ValueError:
            return Response(INVALID_UUID)
        return Response({"data": {"specimen": None, "specimenSnapshots": []}})


@pytest.fixture
def actor():
    token = actor_uid.set(support.WORKER)
    yield
    actor_uid.reset(token)


def test_an_id_that_is_not_a_uuid_is_missing_without_a_connector_call(actor):
    session = TypedSession()
    repository = SqlConnectRepository(session=session)
    with pytest.raises(Missing):
        repository.get(SCOPE, NOT_A_UUID)
    assert session.calls == []


@pytest.mark.parametrize("ident", [
    "01b79931-2233-5a81-8010-aeefe951bb0f",
    "01b7993122335a818010aeefe951bb0f",  # pragma: allowlist secret (a specimen UUID, unhyphenated)
])
def test_a_uuid_in_either_form_still_reaches_the_connector(actor, ident):
    session = TypedSession()
    with pytest.raises(Missing):
        SqlConnectRepository(session=session).get(SCOPE, ident)
    assert [operation for operation, _ in session.calls] == ["GetSpecimen"]


def test_a_graphql_error_logs_its_code_before_it_becomes_a_conflict(actor, caplog):
    session = TypedSession()
    caplog.set_level(logging.WARNING, logger="specimen_digitization.application.production")
    with pytest.raises(Conflict):
        SqlConnectRepository(session=session).execute("GetSpecimen", {"id": NOT_A_UUID})
    (record,) = [r for r in caplog.records if r.name == "specimen_digitization.application.production"]
    assert record.getMessage() == "SQL Connect GetSpecimen rejected: code=INVALID_ARGUMENT"
    # The message can carry request values; only the code is logged.
    assert NOT_A_UUID not in record.getMessage()


def test_the_workspace_of_an_id_that_is_not_a_uuid_is_404(tmp_path, actor):
    fake = support.FakeDataConnect(None, members={support.WORKER: [{
        "organization_id": support.ORG, "collection_id": support.COLLECTION,
        "role": "operator", "can_view_sensitive": False}]})
    typed = TypedSession()
    original = fake.post

    def post(url, json=None, timeout=None):
        if json["operationName"] == "GetSpecimen" and json["variables"]["id"] == NOT_A_UUID:
            return typed.post(url, json, timeout)
        return original(url, json=json, timeout=timeout)

    fake.post = post
    blobs = support.GenerationBlobs(tmp_path / "blobs")
    repository = SqlConnectRepository(session=fake, graph_blobs=blobs)
    app = create_app(mode="emulator", repository=repository, blobs=blobs,
        adapters=SyntheticAdapters(blobs, support.LABEL_TEXT),
        identity_verifier=lambda bearer, check: support.WORKER if bearer == "worker-fixture" else "unknown",
        memberships=repository.memberships)
    with TestClient(app) as client:
        reply = client.get(f"/v1/organizations/{support.ORG}/specimens/{NOT_A_UUID}/workspace",
                           headers={"Authorization": "Bearer worker-fixture"})
    assert reply.status_code == 404, reply.text
    assert reply.json()["error"]["code"] == "not_found"
