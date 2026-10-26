"""Setting a monthly budget cap: PUT /v1/organizations/{org}/costs/caps (TENANT_BUDGETS.md).

The production repository over the in-memory connector, which answers
TenantBudgetCapsV1 and SetTenantBudgetCapV1 as dataconnect/connector/
tenant_budget.gql does. Only an active admin of a collection of the
organization sets or clears a cap; nothing is set by default.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from specimen_digitization.application.api import create_app
from specimen_digitization.application.domain import Scope
from specimen_digitization.application.production import SqlConnectRepository, actor_uid
from specimen_digitization.application.storage import LocalBlobs, SQLiteRepository
from specimen_digitization.application.workflow import SyntheticAdapters

sys.path.insert(0, str(Path(__file__).resolve().parent / "research_harness"))
import production_e2e_support as support  # noqa: E402

USER = "cap-user"
URL = f"/v1/organizations/{support.ORG}/costs/caps"
HEADERS = {"Authorization": "Bearer fixture"}
OTHER = "00000000-0000-4000-8000-0000000000b7"


def client(tmp_path, role="admin", *, organization=support.ORG, sqlite=False, **row):
    members = {USER: [{"organization_id": organization, "collection_id": support.COLLECTION, "role": role,
        "can_view_sensitive": False, **row}]}
    fake = support.FakeDataConnect(None, members=members)
    blobs = LocalBlobs(tmp_path / "blobs")
    repository = (SQLiteRepository(tmp_path / "state.sqlite3") if sqlite
        else SqlConnectRepository(session=fake, graph_blobs=blobs))
    app = create_app(mode="emulator", repository=repository, blobs=blobs,
        adapters=SyntheticAdapters(blobs, support.LABEL_TEXT),
        identity_verifier=lambda bearer, check: USER, memberships=lambda user: members.get(user, []))
    return TestClient(app, raise_server_exceptions=False), fake, repository


def put(test_client, body):
    return test_client.put(URL, headers=HEADERS, json=body)


def test_no_cap_is_set_until_an_administrator_sets_one(tmp_path):
    _, fake, repository = client(tmp_path)
    token = actor_uid.set(USER)
    try:
        assert repository.tenant_caps(Scope(organization_id=support.ORG, collection_id=support.COLLECTION)) == {
            "caps": [], "collections": [{"id": support.COLLECTION, "parent_id": None}]}
    finally:
        actor_uid.reset(token)
    assert fake.tenant_budget_caps == {}


@pytest.mark.parametrize("role", ["viewer", "operator", "reviewer", "manager"])
def test_only_an_organization_administrator_sets_a_cap(tmp_path, role):
    test_client, fake, _ = client(tmp_path, role)
    reply = put(test_client, {"collection_id": None, "monthly_cap_micros": 5_000_000})
    assert reply.status_code == 403, reply.text
    assert reply.json()["error"]["code"] == "access_denied"
    assert fake.tenant_budget_caps == {} and "SetTenantBudgetCapV1" not in fake.calls


def test_an_administrator_of_another_organization_sets_nothing(tmp_path):
    test_client, fake, _ = client(tmp_path, organization=OTHER)
    reply = put(test_client, {"collection_id": None, "monthly_cap_micros": 5_000_000})
    assert reply.status_code == 403, reply.text
    assert fake.tenant_budget_caps == {}


def test_an_administrator_sets_and_clears_caps(tmp_path):
    test_client, fake, repository = client(tmp_path)
    reply = put(test_client, {"collection_id": None, "monthly_cap_micros": 5_000_000})
    assert reply.status_code == 200, reply.text
    assert reply.json() == {"organization_id": support.ORG,
        "caps": [{"collection_id": None, "monthly_cap_micros": 5_000_000}]}
    # A collection id in any UUID spelling names the same collection.
    reply = put(test_client, {"collection_id": support.COLLECTION.upper().replace("-", ""),
        "monthly_cap_micros": 2_000_000})
    assert reply.status_code == 200, reply.text
    assert reply.json()["caps"] == [{"collection_id": None, "monthly_cap_micros": 5_000_000},
        {"collection_id": support.COLLECTION, "monthly_cap_micros": 2_000_000}]
    assert fake.tenant_budget_caps[support.COLLECTION][:2] == (2_000_000, USER)
    # A null cap clears it: the row says no cap, and no cap is reported.
    reply = put(test_client, {"collection_id": None, "monthly_cap_micros": None})
    assert reply.status_code == 200, reply.text
    assert reply.json()["caps"] == [{"collection_id": support.COLLECTION, "monthly_cap_micros": 2_000_000}]
    assert fake.tenant_budget_caps["organization"][0] is None
    # The worker reads them back as whole micros (the wire carries Int64 as text here).
    token = actor_uid.set(USER)
    try:
        caps = repository.tenant_caps(Scope(organization_id=support.ORG, collection_id=support.COLLECTION))["caps"]
    finally:
        actor_uid.reset(token)
    assert [(row["collection_key"], row["monthly_cap_micros"]) for row in caps] == [
        (support.COLLECTION, 2_000_000), ("organization", None)]


@pytest.mark.parametrize("body", [
    {},
    {"collection_id": None},
    {"monthly_cap_micros": 1},
    {"collection_id": None, "monthly_cap_micros": -1},
    {"collection_id": None, "monthly_cap_micros": "5000000"},
    {"collection_id": None, "monthly_cap_micros": True},
    {"collection_id": None, "monthly_cap_micros": 1.5},
    {"collection_id": None, "monthly_cap_micros": 2**53},
    {"collection_id": "insects", "monthly_cap_micros": 1},
    {"collection_id": OTHER, "monthly_cap_micros": 1},
    {"collection_id": None, "monthly_cap_micros": 1, "currency": "USD"},
], ids=["empty", "no_cap", "no_collection", "negative", "text", "boolean", "fraction", "too_large",
    "not_a_uuid", "not_this_organizations", "extra_key"])
def test_a_cap_that_does_not_fit_the_contract_is_422(tmp_path, body):
    test_client, fake, _ = client(tmp_path)
    reply = put(test_client, body)
    assert reply.status_code == 422, reply.text
    assert reply.json()["error"]["code"] == "invalid_input"
    assert fake.tenant_budget_caps == {} and "SetTenantBudgetCapV1" not in fake.calls


def test_a_store_that_keeps_no_caps_answers_503(tmp_path):
    test_client, _, _ = client(tmp_path, sqlite=True)
    reply = put(test_client, {"collection_id": None, "monthly_cap_micros": 5_000_000})
    assert reply.status_code == 503, reply.text
    assert reply.json()["error"]["code"] == "cost_meter_unavailable"


def test_an_inactive_administrator_row_sets_nothing(tmp_path):
    test_client, fake, _ = client(tmp_path, active=False)
    reply = put(test_client, {"collection_id": None, "monthly_cap_micros": 5_000_000})
    assert reply.status_code == 403, reply.text
    assert fake.tenant_budget_caps == {} and "TenantBudgetCapsV1" not in fake.calls


def test_a_cap_the_connector_refuses_for_this_membership_is_403(tmp_path):
    # The connector checks the membership again. The admin row was deactivated
    # after the route read it: the memberships, read again, explain the
    # refusal, so it is an authorization answer, not a conflict.
    test_client, fake, _ = client(tmp_path)

    def refused(variables):
        fake.members[USER][0]["active"] = False
        raise support.ConnectorRefusal("tenant budget cap refused")
    fake.op_SetTenantBudgetCapV1 = refused
    reply = put(test_client, {"collection_id": None, "monthly_cap_micros": 5_000_000})
    assert reply.status_code == 403, reply.text
    assert reply.json()["error"]["code"] == "access_denied"


def test_a_cap_the_connector_refuses_while_the_membership_holds_is_503(tmp_path):
    # A transaction rejection the caller's membership does not explain (the
    # admin row is still active) is the store's, not an authorization answer.
    test_client, fake, _ = client(tmp_path)

    def refused(variables):
        raise support.ConnectorRefusal("transaction rejected")
    fake.op_SetTenantBudgetCapV1 = refused
    reply = put(test_client, {"collection_id": None, "monthly_cap_micros": 5_000_000})
    assert reply.status_code == 503, reply.text
    assert reply.json()["error"]["message"] == "tenant_budget_unavailable"
    assert fake.tenant_budget_caps == {}


@pytest.mark.parametrize("answer", [
    {"tenantBudgetCaps": None, "collections": []},
    {"tenantBudgetCaps": [], "collections": [{"id": "not-a-uuid", "parentId": None}]},
    {"tenantBudgetCaps": [{"collectionKey": "organization", "monthlyCapMicros": "-1"}], "collections": []},
], ids=["not_a_list", "malformed_collection", "not_a_cap"])
def test_a_caps_answer_the_store_cannot_read_is_503_before_anything_is_set(tmp_path, answer):
    # SqlConnectRepository.tenant_caps raises Conflict("Tenant budget caps
    # unreadable"), ValueError or TenantBudgetUnavailable for such an answer:
    # each is 503 tenant_budget_unavailable, never 409, 422 or 403.
    test_client, fake, _ = client(tmp_path)
    fake.op_TenantBudgetCapsV1 = lambda variables: {"organizationMember": {"active": True},
        "collectionMember": {"active": True, "role": "admin"}, **answer}
    reply = put(test_client, {"collection_id": support.COLLECTION, "monthly_cap_micros": 1})
    assert reply.status_code == 503, reply.text
    assert reply.json()["error"]["message"] == "tenant_budget_unavailable"
    assert fake.tenant_budget_caps == {} and "SetTenantBudgetCapV1" not in fake.calls


def test_a_caps_read_the_connector_refuses_for_this_membership_is_403(tmp_path):
    test_client, fake, _ = client(tmp_path)

    def refused(variables):
        fake.members[USER][0]["role"] = "viewer"  # No longer an administrator.
        raise support.ConnectorRefusal("permission denied")
    fake.op_TenantBudgetCapsV1 = refused
    reply = put(test_client, {"collection_id": support.COLLECTION, "monthly_cap_micros": 1})
    assert reply.status_code == 403, reply.text
    assert reply.json()["error"]["code"] == "access_denied"
    assert "SetTenantBudgetCapV1" not in fake.calls


def test_caps_that_cannot_be_read_are_503_before_anything_is_set(tmp_path):
    test_client, fake, _ = client(tmp_path)
    fake.tenant_budget_caps["organization"] = (-5, USER, "2026-10-20T00:00:00Z")  # Not a cap.
    reply = put(test_client, {"collection_id": support.COLLECTION, "monthly_cap_micros": 1})
    assert reply.status_code == 503, reply.text
    assert reply.json()["error"]["message"] == "tenant_budget_unavailable"
    assert support.COLLECTION not in fake.tenant_budget_caps and "SetTenantBudgetCapV1" not in fake.calls
