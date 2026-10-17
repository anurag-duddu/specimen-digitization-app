"""A dropped SQL Connect connection is sent again only where a repeat cannot apply twice.

On 2026-10-17 the drain (execution specimen-worker-4fk49) died on one
`RemoteDisconnected` from a save, and due work waited an hour for a person.
Reads are sent again. Of the mutations, only the four saves whose connector
transaction refuses a repeat whole (dataconnect/connector/checksum.gql and
sensitivity.gql) are: each applies only at its expected revision, or as a first
revision, and inserts a receipt keyed by its idempotency key. A refused repeat
is then settled by that receipt.
"""

from __future__ import annotations

import pytest
import requests

from specimen_digitization.application.domain import Asset, Principal, Profile, Run, Scope, Specimen
from specimen_digitization.application.production import (
    SqlConnectRepository,
    verified_actor_context,
)
from specimen_digitization.application.storage import Conflict
from specimen_digitization.application.workflow import OperationalBlock

SCOPE = Scope(
    organization_id="00000000-0000-4000-8000-000000000001",
    collection_id="00000000-0000-4000-8000-000000000002",
)
ACTOR = "worker-actor"
PRINCIPAL = Principal(user_id=ACTOR, scope=SCOPE, role="operator")
FENCE = "00000000-0000-4000-8000-0000000000f1"
REFUSED = {"errors": [{"message": "revision conflict", "extensions": {"code": "FAILED_PRECONDITION"}}]}


class Response:
    def __init__(self, body, status=200):
        self.status_code = status
        self.body = body

    def json(self):
        return self.body


class Connector:
    """The connector's guards on the four repeatable saves, in memory.

    A save applies only at its expected revision (0 for a create) and only once
    per receipt key; a refusal applies nothing, as one SQL transaction does.
    `drops[operation]` lists what happens to its next sends: "before" (the
    connection drops before the request arrives), "after" (it commits, then the
    answer is lost), "timeout" (a read timeout before it arrives) or "taken"
    (another writer saves first, then this connection drops before arrival).
    """

    def __init__(self, drops=None, status=200):
        self.status = status
        self.drops = {operation: list(sends) for operation, sends in (drops or {}).items()}
        self.calls = []
        self.snapshots = {}  # specimen id -> {revision: snapshot row}
        self.receipts = {}  # (operation, key) -> receipt
        self.documents = {}  # (kind, id) -> payload
        self.document_receipts = {}  # (operation, key) -> receipt

    def post(self, url, json, timeout):
        operation, variables = json["operationName"], json["variables"]
        self.calls.append(operation)
        if self.status != 200:
            return Response({}, self.status)
        drop = self.drops[operation].pop(0) if self.drops.get(operation) else None
        if drop == "before":
            raise requests.ConnectionError("Remote end closed connection without response")
        if drop == "timeout":
            raise requests.ReadTimeout("Read timed out")
        if drop == "taken":
            self._commit_specimen(variables["id"], variables["expectedRevision"],
                ("save:" + variables["id"], "another-writer"), "other", variables)
            raise requests.ConnectionError("Remote end closed connection without response")
        body = self._answer(operation, variables)
        if drop == "after":
            raise requests.ConnectionError("Remote end closed connection without response")
        return Response(body)

    def _commit_specimen(self, ident, expected, key, request_sha, variables):
        rows = self.snapshots.setdefault(ident, {})
        if max(rows, default=0) != expected or key in self.receipts:
            return REFUSED
        rows[expected + 1] = {
            "revision": expected + 1,
            "snapshot": variables["snapshot"],
            "sha256": variables["snapshotSha256"],
        }
        self.receipts[key] = {
            "specimenId": ident, "revision": expected + 1, "requestSha256": request_sha,
        }
        return {"data": {}}

    def _answer(self, operation, variables):
        key = (variables.get("operation"), variables.get("idempotencyKey"))
        if operation == "GetReceipt":
            return {"data": {"requestReceipt": self.receipts.get(key)}}
        if operation == "GetSnapshot":
            row = self.snapshots.get(variables["id"], {}).get(variables["revision"])
            return {"data": {"specimenSnapshot": row}}
        if operation in {"CreateSpecimenV3", "SaveSpecimenV3"}:
            return self._commit_specimen(variables["id"], variables.get("expectedRevision", 0),
                key, variables["requestSha256"], variables)
        if operation == "GetDocumentV2":
            payload = self.documents.get((variables["kind"], variables["id"]))
            row = payload and {"sensitive": payload["sensitive"], "payload": payload}
            return {"data": {"auxiliaryDocument": row}}
        if operation in {"CreateDocumentV2", "SaveDocumentV2"}:
            document = (variables["kind"], variables["id"])
            current = self.documents.get(document, {}).get("revision", 0)
            if current != variables.get("expectedRevision", 0) or key in self.document_receipts:
                return REFUSED
            self.documents[document] = variables["payload"]
            self.document_receipts[key] = {
                "kind": variables["kind"], "documentId": variables["id"],
                "revision": current + 1, "requestSha256": variables["requestSha256"],
            }
            return {"data": {}}
        if operation == "GetDocumentReceiptV2":
            return {"data": {"auxiliaryReceipt": self.document_receipts.get(key)}}
        if operation.startswith("Append"):
            return {"data": {}}  # Projection rows; their own replays are tested elsewhere.
        raise AssertionError("Unexpected operation: " + operation)


def repository(connector):
    repo = SqlConnectRepository(session=connector)
    repo.pauses = []
    repo.pause = repo.pauses.append
    return repo


def specimen():
    return Specimen(
        scope=SCOPE,
        asset=Asset(
            sensitive=False, sha256="a" * 64, blob_ref="fixture-blob", media_type="image/png",
            size_bytes=1, width=1, height=1, filename="fixture.png", uploader=ACTOR,
        ),
        run=Run(profile=Profile()),
    )


def created(repo):
    first = repo.create(PRINCIPAL, specimen(), "queue:fixture", "request-create")
    first.run.stage = "transcribe"
    return first


@pytest.fixture(autouse=True)
def actor():
    with verified_actor_context(ACTOR):
        yield


def test_a_save_whose_connection_drops_before_it_arrives_is_sent_again():
    connector = Connector({"SaveSpecimenV3": ["before"]})
    repo = repository(connector)
    saved = repo.save(PRINCIPAL, created(repo), 1, "step:1", "request-step")
    assert saved.version == 2 and saved.run.stage == "transcribe"
    assert connector.calls.count("SaveSpecimenV3") == 2
    assert sorted(connector.snapshots[saved.id]) == [1, 2]
    assert repo.pauses == [1]


def test_a_save_that_committed_before_its_answer_was_lost_is_settled_by_its_receipt():
    connector = Connector({"SaveSpecimenV3": ["after"]})
    repo = repository(connector)
    saved = repo.save(PRINCIPAL, created(repo), 1, "step:1", "request-step")
    # The repeat was refused whole; the receipt shows the first send committed.
    assert saved.version == 2 and saved.run.stage == "transcribe"
    assert sorted(connector.snapshots[saved.id]) == [1, 2]
    assert connector.calls[-3:] == ["SaveSpecimenV3", "GetReceipt", "GetSnapshot"]


def test_a_repeat_refused_for_another_writers_save_stays_a_conflict():
    connector = Connector({"SaveSpecimenV3": ["taken"]})
    repo = repository(connector)
    first = created(repo)
    with pytest.raises(Conflict):
        repo.save(PRINCIPAL, first, 1, "step:1", "request-step")
    # Revision 2 is the other writer's; nothing of this save was applied.
    assert connector.receipts[("save:" + first.id, "another-writer")]["requestSha256"] == "other"
    assert ("save:" + first.id, "step:1") not in connector.receipts


def test_a_document_save_that_committed_before_its_answer_was_lost_is_settled_by_its_receipt():
    # The collection fence and the program ledger are documents (lane_worker,
    # lane_allowance); the 2026-10-17 drop was on the ledger's settlement.
    connector = Connector({"SaveDocumentV2": ["after"]})
    repo = repository(connector)
    repo.put_document(SCOPE, "worker_cursor", FENCE, {"sensitive": False, "holder": "a"}, 0)
    stored = repo.put_document(SCOPE, "worker_cursor", FENCE, {"sensitive": False, "holder": None}, 1)
    assert stored["revision"] == 2
    assert connector.documents[("worker_cursor", FENCE)] == stored
    assert connector.calls[-2:] == ["SaveDocumentV2", "GetDocumentReceiptV2"]


def test_a_document_save_whose_connection_drops_before_it_arrives_is_sent_again():
    connector = Connector({"CreateDocumentV2": ["before"]})
    repo = repository(connector)
    stored = repo.put_document(SCOPE, "worker_cursor", FENCE, {"sensitive": False}, 0)
    assert stored["revision"] == 1
    assert connector.calls == ["CreateDocumentV2", "CreateDocumentV2"]


def test_a_read_whose_connection_drops_or_times_out_is_sent_again():
    connector = Connector({"GetDocumentV2": ["before", "timeout"]})
    repo = repository(connector)
    repo.put_document(SCOPE, "worker_cursor", FENCE, {"sensitive": False, "holder": "a"}, 0)
    assert repo.document(SCOPE, "worker_cursor", FENCE)["holder"] == "a"
    assert connector.calls.count("GetDocumentV2") == 3
    assert repo.pauses == [1, 2]


def test_a_connection_that_keeps_dropping_is_sent_three_times_then_fails():
    connector = Connector({"GetDocumentV2": ["before"] * 4})
    repo = repository(connector)
    with pytest.raises(requests.ConnectionError):
        repo.document(SCOPE, "worker_cursor", FENCE)
    assert connector.calls == ["GetDocumentV2"] * 3
    assert repo.pauses == [1, 2]


@pytest.mark.parametrize(("status", "error"), [(503, OperationalBlock), (403, PermissionError)])
def test_an_http_answer_is_never_sent_again(status, error):
    connector = Connector(status=status)
    repo = repository(connector)
    with pytest.raises(error):
        repo.document(SCOPE, "worker_cursor", FENCE)
    assert connector.calls == ["GetDocumentV2"]
    assert repo.pauses == []


def test_a_mutation_not_known_to_refuse_a_repeat_is_sent_once():
    connector = Connector({"ScheduleResearchRetryV1": ["before"]})
    repo = repository(connector)
    with pytest.raises(requests.ConnectionError):
        repo.execute("ScheduleResearchRetryV1", {}, mutation=True)
    assert connector.calls == ["ScheduleResearchRetryV1"]
