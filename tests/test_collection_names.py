"""Authoritative collection labels through a credential-free SQL/API seam."""
from types import SimpleNamespace
from uuid import UUID

from fastapi.testclient import TestClient

from specimen_digitization.application.api import create_app
from specimen_digitization.application.production import SqlConnectRepository


def client_for(memberships):
    return TestClient(create_app(mode="production", repository=SimpleNamespace(),
        blobs=SimpleNamespace(), adapters=SimpleNamespace(),
        identity_verifier=lambda token, appcheck: "fixture-user", memberships=memberships,
        origins=["https://specimen-digitization.web.app"]))


def test_named_memberships_keep_their_distinct_authoritative_collection_names():
    org, first, second, other_org = (UUID(int=index) for index in range(1, 5))
    rows = [
        {"organizationId": org.hex, "collectionId": first.hex, "collection": {"name": "Insects"}},
        {"organizationId": org.hex, "collectionId": second.hex, "collection": {"name": "Intake E2E"}},
        {"organizationId": other_org.hex, "collectionId": first.hex, "collection": {"name": "Other organization"}},
    ]
    response = {"organizationMembers": [{"organizationId": str(value), "active": True} for value in (org, other_org)],
        "collectionMembers": [{**row, "active": True, "role": "operator", "canViewSensitive": False} for row in rows]}
    repository = object.__new__(SqlConnectRepository)
    calls = []
    def execute(operation, variables):
        calls.append((operation, variables))
        return response
    repository.execute = execute
    with client_for(repository.memberships) as client:
        result = client.get(f"/v1/organizations/{org}/collections", headers={"Authorization": "Bearer fixture"})
    assert result.status_code == 200
    assert [(item["collection_id"], item["display_name"]) for item in result.json()["items"]] == [
        (str(first), "Insects"), (str(second), "Intake E2E")]
    assert calls == [("Memberships", {"actorUid": "fixture-user"})]


def test_legacy_membership_without_a_name_uses_its_id_without_inventing_a_label():
    org, collection = str(UUID(int=1)), str(UUID(int=2))
    with client_for(lambda user: [{"organization_id": org, "collection_id": collection, "role": "operator"}]) as client:
        result = client.get(f"/v1/organizations/{org}/collections", headers={"Authorization": "Bearer fixture"})
    assert result.status_code == 200
    assert result.json()["items"][0]["display_name"] == collection
