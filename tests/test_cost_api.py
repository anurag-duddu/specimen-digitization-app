"""The cost meter's API: an organization's costs for its administrators (COST_METER.md)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from specimen_digitization.application.api import create_app
from specimen_digitization.application.lane_dispatch import DispatchOutcome

ORG = "00000000-0000-4000-8000-0000000000a1"
INSECTS = "00000000-0000-4000-8000-0000000000b2"
BEETLES = "00000000-0000-4000-8000-0000000000b3"
OTHER_ORG = "00000000-0000-4000-8000-0000000000a9"
USER = "verified-fixture-user"
HEADERS = {"Authorization": "Bearer fixture-id-token", "X-Firebase-AppCheck": "fixture-app-token"}
COLLECTIONS = [
    {"id": INSECTS.replace("-", ""), "name": "Insects", "parentId": None},
    {"id": BEETLES.replace("-", ""), "name": "Beetles", "parentId": INSECTS.replace("-", "")},
]
GROUPS = [
    {"collection_id": BEETLES, "month": "2026-10", "stage": "reading", "source": "paid_call", "kind": "model",
     "provider": "huggingface", "resource": "handwriting-qwen", "cost_basis": "computed",
     "cost_micros": "550", "list_cost_micros": "550", "entries": "1", "updated_at": "2026-10-20T15:04:05Z"},
    {"collection_id": INSECTS, "month": "2026-10", "stage": "label_finding", "source": "paid_call",
     "kind": "service", "provider": "google_cloud", "resource": "sam3", "cost_basis": "reserved",
     "cost_micros": "9000", "list_cost_micros": "9000", "entries": "1", "updated_at": "2026-10-19T00:00:00Z"},
]


def membership(role, organization=ORG, collection=INSECTS):
    return {"organization_id": organization, "collection_id": collection, "role": role, "can_view_sensitive": False}


def client(rows, repository=None, dispatcher=None):
    if repository is None:
        repository = Mock(spec=["cost_totals"])
        repository.cost_totals.return_value = {"collections": COLLECTIONS, "groups": GROUPS}
    app = create_app(
        mode="production", repository=repository, blobs=SimpleNamespace(), adapters=SimpleNamespace(),
        identity_verifier=Mock(return_value=USER), memberships=Mock(return_value=rows),
        origins=["https://specimen-digitization.web.app"], worker_dispatcher=dispatcher,
    )
    return TestClient(app), repository


def amount(cost, held=0, entries=1):
    return {"cost_micros": cost, "held_micros": held, "list_cost_micros": cost, "entries": entries}


def test_an_administrator_reads_the_organization_s_costs_in_the_contract_shape():
    http, repository = client([membership("viewer"), membership("admin", collection=BEETLES)])
    with http:
        response = http.get(f"/v1/organizations/{ORG}/costs", params={"from": "2026-09", "to": "2026-10"},
                            headers=HEADERS)
    assert response.status_code == 200, response.text
    repository.cost_totals.assert_called_once_with(ORG, "2026-09", "2026-10")
    body = response.json()
    assert set(body) == {"organization_id", "currency", "from_month", "to_month", "updated_at", "totals",
                         "organization_cap", "collections", "months", "models", "meter"}
    assert (body["organization_id"], body["currency"], body["from_month"], body["to_month"]) == (
        ORG, "USD", "2026-09", "2026-10")
    assert (body["organization_cap"], body["meter"], body["updated_at"]) == (None, None, "2026-10-20T15:04:05Z")
    assert body["totals"] == amount(9_550, 9_000, 2)
    assert body["collections"] == [
        {"collection_id": BEETLES, "name": "Beetles", "parent_id": INSECTS, "own": amount(550),
         "total": amount(550), "cap": None},
        {"collection_id": INSECTS, "name": "Insects", "parent_id": None, "own": amount(9_000, 9_000),
         "total": amount(9_550, 9_000, 2), "cap": None},
    ]
    assert [month["month"] for month in body["months"]] == ["2026-09", "2026-10"]
    assert body["months"][1]["stages"] == [{"stage": "label_finding", **amount(9_000, 9_000)},
                                           {"stage": "reading", **amount(550)}]
    assert body["models"] == [
        {"month": "2026-10", "stage": "label_finding", "provider": "google_cloud", "resource": "sam3",
         **amount(9_000, 9_000)},
        {"month": "2026-10", "stage": "reading", "provider": "huggingface", "resource": "handwriting-qwen",
         **amount(550)},
    ]


def test_the_range_defaults_to_the_current_utc_month():
    http, repository = client([membership("admin")])
    repository.cost_totals.return_value = {"collections": COLLECTIONS, "groups": []}
    current = datetime.now(timezone.utc).strftime("%Y-%m")
    with http:
        response = http.get(f"/v1/organizations/{ORG}/costs", headers=HEADERS)
        only_to = http.get(f"/v1/organizations/{ORG}/costs", params={"to": "2026-03"}, headers=HEADERS)
    assert response.status_code == 200, response.text
    assert (response.json()["from_month"], response.json()["to_month"]) == (current, current)
    assert (only_to.json()["from_month"], only_to.json()["to_month"]) == ("2026-03", "2026-03")


@pytest.mark.parametrize("rows", [
    [membership("viewer")], [membership("operator")], [membership("reviewer")], [membership("manager")],
    [membership("admin", organization=OTHER_ORG)], [],
], ids=["viewer", "operator", "reviewer", "manager", "admin-of-another-organization", "no-membership"])
@pytest.mark.parametrize("method,path", [("get", "/costs"), ("post", "/costs/refresh")])
def test_anyone_but_an_administrator_of_the_organization_is_refused(rows, method, path):
    dispatcher = Mock()
    http, repository = client(rows, dispatcher=dispatcher)
    with http:
        response = getattr(http, method)(f"/v1/organizations/{ORG}{path}", headers=HEADERS)
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "access_denied"
    assert repository.mock_calls == [] and dispatcher.mock_calls == []


@pytest.mark.parametrize("params", [
    {"from": "2026-13"}, {"from": "2026-1", "to": "2026-02"}, {"from": "2026-11", "to": "2026-10"},
    {"from": "2024-10", "to": "2026-10"}, {"to": "October"}, {"from": "2026-10-01", "to": "2026-10"},
])
def test_a_malformed_or_too_long_range_is_refused(params):
    http, repository = client([membership("admin")])
    with http:
        response = http.get(f"/v1/organizations/{ORG}/costs", params=params, headers=HEADERS)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "invalid_input"
    assert repository.mock_calls == []


def test_twenty_four_months_are_accepted():
    http, repository = client([membership("admin")])
    with http:
        response = http.get(f"/v1/organizations/{ORG}/costs", params={"from": "2024-11", "to": "2026-10"},
                            headers=HEADERS)
    assert response.status_code == 200, response.text
    assert len(response.json()["months"]) == 24


def test_a_repository_without_the_cost_meter_is_unavailable():
    http, _ = client([membership("admin")], repository=Mock(spec=["search"]))
    with http:
        response = http.get(f"/v1/organizations/{ORG}/costs", headers=HEADERS)
    assert response.status_code == 503, response.text
    assert (response.json()["error"]["message"], response.json()["error"]["retryable"]) == (
        "cost_meter_unavailable", True)


def test_a_cycle_in_the_collection_tree_is_reported_not_rolled_up():
    repository = Mock(spec=["cost_totals"])
    cyclic = [dict(COLLECTIONS[0], parentId=BEETLES), COLLECTIONS[1]]
    repository.cost_totals.return_value = {"collections": cyclic, "groups": GROUPS}
    http, _ = client([membership("admin")], repository=repository)
    with http:
        response = http.get(f"/v1/organizations/{ORG}/costs", params={"from": "2026-10"}, headers=HEADERS)
    assert response.status_code == 503, response.text
    assert response.json()["error"]["message"] == "cost_collection_tree_invalid"


@pytest.mark.parametrize("outcome,started", [
    (DispatchOutcome(status="requested"), True),
    (DispatchOutcome(status="failed", reason="http_503"), False),
])
def test_refresh_starts_the_worker_job_through_the_dispatcher(outcome, started):
    dispatcher = Mock()
    dispatcher.start.return_value = outcome
    http, repository = client([membership("admin")], dispatcher=dispatcher)
    with http:
        response = http.post(f"/v1/organizations/{ORG}/costs/refresh", headers=HEADERS)
    assert response.status_code == 200, response.text
    assert response.json() == {"started": started}
    dispatcher.start.assert_called_once_with()
    assert repository.mock_calls == []


def test_refresh_starts_each_collection_s_own_worker_job_once():
    from specimen_digitization.application.lane_dispatch import CollectionJobDispatcher

    insects, beetles, other = Mock(), Mock(), Mock()
    insects.start.return_value = DispatchOutcome(status="failed", reason="http_503")
    beetles.start.return_value = DispatchOutcome(status="requested")
    dispatcher = CollectionJobDispatcher(None, {
        f"{ORG}/{INSECTS}": insects, f"{ORG}/{BEETLES}": beetles, f"{OTHER_ORG}/{INSECTS}": other,
    })
    rows = [membership("admin"), membership("viewer", collection=BEETLES),
            membership("admin", organization=OTHER_ORG)]
    http, _ = client(rows, dispatcher=dispatcher)
    with http:
        response = http.post(f"/v1/organizations/{ORG}/costs/refresh", headers=HEADERS)
    assert response.status_code == 200, response.text
    assert response.json() == {"started": True}
    insects.start.assert_called_once_with()
    beetles.start.assert_called_once_with()
    other.start.assert_not_called()


def test_refresh_without_a_worker_job_starts_nothing():
    http, _ = client([membership("admin")])
    with http:
        response = http.post(f"/v1/organizations/{ORG}/costs/refresh", headers=HEADERS)
    assert response.status_code == 200, response.text
    assert response.json() == {"started": False}
