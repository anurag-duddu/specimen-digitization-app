"""The cost meter's forward write in SqlConnectRepository (docs/execution/golive/COST_METER.md)."""

from __future__ import annotations

import json
import logging
from json import loads

import pytest
import requests

from specimen_digitization.application import production
from specimen_digitization.application.active_graph import pack
from specimen_digitization.application.cost_ledger import paid_call_rows
from specimen_digitization.application.domain import Asset, Principal, Scope, Specimen
from specimen_digitization.application.lane_costs import record_model_usage, record_segmentation
from specimen_digitization.application.production import SqlConnectRepository, actor_uid
from specimen_digitization.application.storage import LocalBlobs, digest

from test_lane_costs import QWEN, priced_run

SCOPE = Scope(organization_id="00000000-0000-4000-8000-0000000000a1",
              collection_id="00000000-0000-4000-8000-0000000000b2")
ACTOR = "worker-uid"
INSTANCE = {"first": False, "idle_seconds": 4.0, "request_seconds": 12.5}
REFUSED = {"message": "cost entries refused", "extensions": {"code": "PERMISSION_DENIED"}}


class Response:
    def __init__(self, body, status=200):
        self.status_code, self.body = status, body

    def json(self):
        return self.body


class Session:
    """Answers every operation; UpsertCostEntriesV1 as the connector does, or as `answer` says."""

    def __init__(self, answer=None, receipts=None):
        self.calls, self.answer, self.receipts = [], answer, receipts or {}

    def post(self, url, json, timeout):
        operation, variables = json["operationName"], json["variables"]
        self.calls.append((operation, variables))
        if operation == "UpsertCostEntriesV1":
            if self.answer is not None:
                answer = self.answer(variables)
                if isinstance(answer, BaseException):
                    raise answer
                return Response(answer)
            return Response({"data": {"upserted": len(loads(variables["rowsJson"]))}})
        if operation == "GetReceipt":
            return Response({"data": {"requestReceipt": self.receipts.get(variables["idempotencyKey"])}})
        if operation == "GetSnapshot":
            return Response({"data": {"specimenSnapshot": self.receipts["snapshot"]}})
        return Response({"data": {}})

    def upserts(self):
        return [json.loads(variables["rowsJson"]) for operation, variables in self.calls
                if operation == "UpsertCostEntriesV1"]


@pytest.fixture(autouse=True)
def actor():
    token = actor_uid.set(ACTOR)
    yield
    actor_uid.reset(token)


def specimen(calls=1, ident="00000000-0000-4000-8000-0000000000c3"):
    run = priced_run()
    for _ in range(calls):
        record_model_usage(run, QWEN, "handwriting-qwen", input_tokens=1_000, output_tokens=500)
    asset = Asset(sensitive=False, sha256="a" * 64, blob_ref="blob", media_type="image/png", size_bytes=1,
                  width=1, height=1, filename="label.png", uploader=ACTOR)
    return Specimen(id=ident, scope=SCOPE, asset=asset, run=run)


def repository(tmp_path, session):
    repo = SqlConnectRepository(session=session, graph_blobs=LocalBlobs(tmp_path / "blobs"))
    repo.pause = lambda seconds: None
    return repo


def test_a_save_upserts_the_run_s_paid_calls_after_its_projection(tmp_path):
    session = Session()
    repo = repository(tmp_path, session)
    s = specimen()
    repo.create(Principal(user_id=ACTOR, scope=SCOPE, role="operator"), s, "create-1", "request-1")
    names = [operation for operation, _ in session.calls]
    assert names[:2] == ["GetReceipt", "CreateSpecimenV3"] and names[-1] == "UpsertCostEntriesV1"
    variables = session.calls[-1][1]
    assert {key: variables[key] for key in ("organizationId", "collectionId", "actorUid", "specimenId")} == {
        "organizationId": SCOPE.organization_id, "collectionId": SCOPE.collection_id, "actorUid": ACTOR,
        "specimenId": s.id}
    assert json.loads(variables["rowsJson"]) == paid_call_rows(
        SCOPE.organization_id, SCOPE.collection_id, s.id, s.run)


def test_only_rows_not_yet_sent_as_they_stand_are_sent_again(tmp_path):
    session = Session()
    repo = repository(tmp_path, session)
    s = specimen()
    assert repo.write_costs(SCOPE, s) is True
    assert repo.write_costs(SCOPE, s) is True
    assert len(session.upserts()) == 1, "an unchanged run sends nothing"
    record_segmentation(s.run, "segment", seconds=1, instance=INSTANCE)
    repo.write_costs(SCOPE, s)
    assert [[row["step"] for row in rows] for rows in session.upserts()] == [[QWEN], ["segment"]]
    s.run.paid_calls[0]["cost_micros"] += 1  # A changed row is sent again.
    repo.write_costs(SCOPE, s)
    assert [row["cost_micros"] for row in session.upserts()[-1]] == [s.run.paid_calls[0]["cost_micros"]]
    # Another process remembers nothing: it sends every row, which the upsert absorbs.
    other = Session()
    repository(tmp_path, other).write_costs(SCOPE, s)
    assert len(other.upserts()[0]) == 2


def test_a_run_without_paid_calls_sends_nothing(tmp_path):
    session = Session()
    assert repository(tmp_path, session).write_costs(SCOPE, specimen(calls=0)) is True
    assert session.calls == []


@pytest.mark.parametrize("answer", [
    lambda variables: {"errors": [REFUSED]},
    lambda variables: {"data": {"upserted": 0}},
    lambda variables: {"data": {}},
], ids=["refused", "short", "no-count"])
def test_a_refused_upsert_never_raises_and_is_sent_again_next_time(tmp_path, caplog, answer):
    session = Session(answer)
    repo = repository(tmp_path, session)
    s = specimen()
    with caplog.at_level(logging.WARNING):
        assert repo.write_costs(SCOPE, s) is False
        assert repo.write_costs(SCOPE, s) is False
    assert len(session.upserts()) == 2, "nothing refused counts as sent"
    messages = [record.getMessage() for record in caplog.records if "Cost rows" in record.getMessage()]
    assert messages == ["Cost rows not written: Conflict"] * 2
    assert not any(s.id in record.getMessage() for record in caplog.records)


def test_a_dropped_connection_is_sent_once_and_never_raises(tmp_path, caplog):
    """The upsert is not one of REPEATABLE_MUTATIONS: the next save, or the sweep, sends it again."""
    session = Session(lambda variables: requests.ConnectionError("dropped"))
    repo = repository(tmp_path, session)
    with caplog.at_level(logging.WARNING):
        assert repo.write_costs(SCOPE, specimen()) is False
    assert len(session.upserts()) == 1
    assert "UpsertCostEntriesV1" not in production.REPEATABLE_MUTATIONS
    assert "Cost rows not written: ConnectionError" in caplog.text


def test_a_call_the_ledger_cannot_record_is_logged_by_code_only(tmp_path, caplog):
    session = Session()
    s = specimen()
    s.run.paid_calls[0]["usage"] = {"input_tokens": "PRIVATE-CANARY"}
    with caplog.at_level(logging.WARNING):
        assert repository(tmp_path, session).write_costs(SCOPE, s) is False
    assert session.calls == []
    assert "Cost rows not written: cost_usage_not_numeric" in caplog.text
    assert "PRIVATE-CANARY" not in caplog.text


def test_many_rows_are_sent_in_bounded_calls(tmp_path):
    session = Session()
    repo = repository(tmp_path, session)
    repo.write_costs(SCOPE, specimen(calls=450))
    assert [len(rows) for rows in session.upserts()] == [200, 200, 50]
    assert len({row["id"] for rows in session.upserts() for row in rows}) == 450


def test_the_remembered_rows_are_bounded_by_specimen(tmp_path, monkeypatch):
    monkeypatch.setattr(production, "COSTED_SPECIMENS", 2)
    session = Session()
    repo = repository(tmp_path, session)
    first, second, third = (specimen(ident=f"00000000-0000-4000-8000-00000000000{n}") for n in (1, 2, 3))
    for s in (first, second, third, first):
        repo.write_costs(SCOPE, s)
    assert [rows[0]["specimen_id"] for rows in session.upserts()] == [first.id, second.id, third.id, first.id]
    assert list(repo._costed) == [third.id, first.id]


def test_a_replayed_save_also_catches_up_its_cost_rows(tmp_path):
    s = specimen()
    payload = pack(s.model_copy(deep=True), None)
    receipts = {
        "replayed": {"specimenId": s.id, "revision": 1, "requestSha256": "request-1"},
        "snapshot": {"revision": 1, "snapshot": payload, "sha256": digest(payload)},
    }
    session = Session(receipts=receipts)
    repo = repository(tmp_path, session)
    committed = repo.create(Principal(user_id=ACTOR, scope=SCOPE, role="operator"), s, "replayed", "request-1")
    assert committed.run.paid_calls == s.run.paid_calls
    assert [operation for operation, _ in session.calls if operation in {"CreateSpecimenV3", "UpsertCostEntriesV1"}] == [
        "UpsertCostEntriesV1"]
    assert session.upserts() == [paid_call_rows(SCOPE.organization_id, SCOPE.collection_id, s.id, s.run)]
