"""General API principal collection admission (not the research principal)."""

from types import SimpleNamespace
from unittest.mock import Mock, call

from fastapi.testclient import TestClient
import pytest

from specimen_digitization.application.api import create_app
from specimen_digitization.application.domain import Scope


@pytest.mark.parametrize("member_collection", ["foreign-collection", "requested-collection"])
def test_general_principal_requires_collection_match_before_search(member_collection):
    user = "verified-fixture-user"
    scope = Scope(organization_id="fixture-org", collection_id="requested-collection")
    verify = Mock(return_value=user)
    memberships = Mock(return_value=[{
        "organization_id": scope.organization_id,
        "collection_id": member_collection,
        "role": "reviewer",
        "can_view_sensitive": True,
    }])
    repository = Mock(spec=["search"])
    repository.search.return_value = []
    app = create_app(
        mode="production", repository=repository,
        blobs=SimpleNamespace(), adapters=SimpleNamespace(),
        identity_verifier=verify, memberships=memberships,
        origins=["https://specimen-digitization.web.app"],
    )
    with TestClient(app) as client:
        response = client.get(
            f"/v1/organizations/{scope.organization_id}/specimens",
            params={"collection_id": scope.collection_id},
            headers={
                "Authorization": "Bearer fixture-id-token",
                "X-Firebase-AppCheck": "fixture-app-token",
            },
        )

    verify.assert_called_once_with("fixture-id-token", "fixture-app-token")
    if member_collection != scope.collection_id:
        assert repository.mock_calls == [], "Foreign collection reached general API repository"
        assert response.status_code == 403, response.text
        assert response.json()["error"]["category"] == "authorization"
        memberships.assert_called_once_with(user)
    else:
        assert response.status_code == 200, response.text
        assert response.json()["items"] == []
        assert response.json()["next_cursor"] is None
        assert memberships.mock_calls == [call(user), call(user)]
        repository.search.assert_called_once()
        args = repository.search.call_args.args
        assert args[0] == scope
        assert args[2] == response.json()["cutoff"]
        assert args[3:] == (None, "", 50, True)
        assert repository.search.call_args.kwargs == {"hydrate_review": True}
        assert repository.mock_calls == [call.search(*args, hydrate_review=True)]
