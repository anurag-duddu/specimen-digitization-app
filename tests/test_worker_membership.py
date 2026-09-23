"""The worker membership bootstrap document (docs/execution/golive/WORKER_MEMBERSHIP.md)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bootstrap_admin", ROOT / "scripts/data/bootstrap_admin.py")
admin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(admin)

ORGANIZATION = str(uuid4())
COLLECTIONS = [str(uuid4()), str(uuid4())]


def test_one_organization_member_and_an_operator_row_per_collection():
    document = admin.worker_membership_mutation(2)
    assert document.startswith("mutation PrepareWorkerMembership(")
    assert "@transaction" in document
    assert document.count("organizationMember_insert(") == 1
    assert document.count("collectionMember_insert(") == 2
    assert document.count('role: "operator", canViewSensitive: false') == 2
    for forbidden in ("admin", "_upsert", "_update", "$canViewSensitive", "$role"):
        assert forbidden not in document
    assert "$c0: UUID!" in document and "$c1: UUID!" in document
    assert admin.worker_membership_mutation(2) == document
    assert admin.worker_membership_mutation(3) != document


def test_the_request_carries_only_the_reviewed_document_and_its_values():
    request = admin.worker_membership_request(
        organization_id=ORGANIZATION, uid="worker-account-uid", collection_ids=COLLECTIONS
    )
    assert request["mode"] == "worker-membership-bootstrap/v1"
    assert request["query"] == admin.worker_membership_mutation(2)
    assert request["variables"] == {
        "organizationId": ORGANIZATION,
        "uid": "worker-account-uid",
        "c0": COLLECTIONS[0],
        "c1": COLLECTIONS[1],
    }


@pytest.mark.parametrize(
    "change",
    [
        {"organization_id": "not-a-uuid"},
        {"organization_id": ORGANIZATION.upper()},
        {"collection_ids": []},
        {"collection_ids": [COLLECTIONS[0], COLLECTIONS[0]]},
        {"collection_ids": [str(uuid4()) for _ in range(65)]},
        {"collection_ids": ["insects"]},
        {"uid": ""},
        {"uid": " worker"},
        {"uid": "worker\n"},
        {"uid": "w" * 129},
        {"uid": None},
    ],
    ids=lambda change: next(iter(change)),
)
def test_every_input_is_explicit_and_canonical(change):
    values = {"organization_id": ORGANIZATION, "uid": "worker-account-uid", "collection_ids": COLLECTIONS}
    with pytest.raises(ValueError):
        admin.worker_membership_request(**{**values, **change})


def test_the_worker_membership_is_not_published_as_a_runtime_operation():
    for path in (ROOT / "dataconnect/connector").glob("*.gql"):
        assert "PrepareWorkerMembership" not in path.read_text()
