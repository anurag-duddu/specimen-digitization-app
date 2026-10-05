"""Session configuration reporting; fixtures are not live worker readiness proof."""

from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest

from specimen_digitization.application.api import create_app
from specimen_digitization.application.collection_profiles import published_registry


COLLECTION = "00000000-0000-4000-8000-0000000000c1"
MEMBER = {
    "organization_id": "00000000-0000-4000-8000-000000000001",
    "collection_id": COLLECTION,
    "role": "reviewer",
    "can_view_sensitive": True,
}


def session_response(*, registry, dispatcher, members=None, mode="production"):
    memberships = Mock(return_value=[MEMBER] if members is None else members)
    app = create_app(
        mode=mode,
        repository=SimpleNamespace(),
        blobs=SimpleNamespace(),
        adapters=SimpleNamespace(),
        token="fixture" if mode == "synthetic" else None,
        identity_verifier=lambda *_: "fixture-reviewer",
        memberships=memberships,
        origins=["https://specimen-digitization.web.app"],
        profile_registry=registry,
        worker_dispatcher=dispatcher,
    )
    with TestClient(app) as client:
        response = client.get(
            "/v1/session", headers={"Authorization": "Bearer fixture"}
        )
    assert response.status_code == 200
    if mode != "synthetic":
        memberships.assert_called_once_with("fixture-reviewer")
    return response.json()


def registry_with(**profile_changes):
    registry = published_registry({COLLECTION: "insects"})
    return registry.model_copy(
        update={
            "profiles": tuple(
                p.model_copy(update=profile_changes) for p in registry.profiles
            )
        }
    )


def test_configured_g1_session_has_no_fabricated_policy_or_worker_blockers():
    registry = registry_with()
    profile = registry.resolve(COLLECTION).profile
    assert profile.harness_route and profile.processing
    assert not profile.institutional_policy_approved
    dispatcher = Mock()

    result = session_response(registry=registry, dispatcher=dispatcher)

    assert result["runtime_blockers"] == []
    assert result["memberships"] == [MEMBER]
    assert result["mode"] == "production"
    assert result["persistence"] == "sql_connect"
    assert not profile.institutional_policy_approved
    dispatcher.start.assert_not_called()


@pytest.mark.parametrize(
    "profile_changes,expected",
    [
        ({}, []),
        ({"harness_route": None}, ["institutional_policy_unapproved"]),
        (
            {"harness_route": None, "institutional_policy_approved": True},
            [],
        ),
        ({"processing": None}, ["collection_processing_unconfigured"]),
        ({"state": "draft"}, ["collection_processing_unconfigured"]),
        ({"state": "revoked"}, ["collection_processing_unconfigured"]),
    ],
)
def test_session_uses_selected_profile_without_inventing_approval(
    profile_changes, expected
):
    dispatcher = Mock()
    result = session_response(
        registry=registry_with(**profile_changes), dispatcher=dispatcher
    )
    assert result["runtime_blockers"] == expected
    dispatcher.start.assert_not_called()


def test_configured_profile_does_not_hide_a_missing_worker_dispatcher():
    result = session_response(registry=registry_with(), dispatcher=None)
    assert result["runtime_blockers"] == ["worker_readiness_not_verified"]


def test_missing_collection_binding_is_reported_even_with_a_configured_worker():
    result = session_response(registry=published_registry(), dispatcher=Mock())
    assert result["runtime_blockers"] == ["collection_processing_unconfigured"]


def test_unrelated_unapproved_profile_does_not_block_callers_collection():
    registry = registry_with()
    unrelated = registry.profiles[0].model_copy(
        update={"id": "unrelated", "collection_id": "mammals", "harness_route": None}
    )
    registry = registry.model_copy(update={"profiles": (*registry.profiles, unrelated)})
    result = session_response(registry=registry, dispatcher=Mock())
    assert result["runtime_blockers"] == []


def test_no_membership_does_not_claim_a_collection_policy_is_unapproved():
    result = session_response(
        registry=registry_with(harness_route=None), dispatcher=Mock(), members=[]
    )
    assert result["memberships"] == []
    assert result["runtime_blockers"] == []


def test_duplicate_membership_collections_do_not_duplicate_blockers():
    result = session_response(
        registry=registry_with(harness_route=None),
        dispatcher=None,
        members=[MEMBER, dict(MEMBER, organization_id="other-org")],
    )
    assert result["runtime_blockers"] == [
        "institutional_policy_unapproved", "worker_readiness_not_verified"
    ]


def test_synthetic_session_keeps_local_processing_exemption():
    result = session_response(
        registry=registry_with(harness_route=None),
        dispatcher=None,
        mode="synthetic",
    )
    assert result["runtime_blockers"] == []
    assert result["synthetic_token_required"] is True
