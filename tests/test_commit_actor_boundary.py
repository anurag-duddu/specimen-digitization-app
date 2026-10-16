"""The commit actor guard, independently of scope and upstream API checks."""

from unittest.mock import Mock, call

import pytest

from specimen_digitization.application.domain import (
    Asset, Principal, Profile, Run, Scope, Specimen,
)
from specimen_digitization.application.production import (
    SqlConnectRepository, actor_uid, verified_actor_context,
)


class TransportReached(RuntimeError):
    """Stop at the first synthetic dispatch, before any connector response."""


@pytest.mark.parametrize("expected", [0, 1], ids=["create", "save"])
@pytest.mark.parametrize("verified_actor", ["foreign-actor", "principal-actor"])
def test_commit_requires_the_principal_actor_before_transport(expected, verified_actor):
    scope = Scope(organization_id="fixture-org", collection_id="fixture-collection")
    principal = Principal(user_id="principal-actor", scope=scope, role="reviewer")
    specimen = Specimen(
        scope=scope.model_copy(deep=True),
        asset=Asset(
            sha256="a" * 64, blob_ref="fixture-blob", media_type="image/png",
            size_bytes=1, width=1, height=1, filename="fixture.png",
            uploader=principal.user_id,
        ),
        run=Run(profile=Profile()),
    )
    before = specimen.model_copy(deep=True)
    session = Mock(spec=["post"])
    session.post.side_effect = TransportReached("synthetic connector dispatch")
    repository = SqlConnectRepository(session=session)
    assert principal.scope == specimen.scope, "Scope must not mask the actor guard"

    with verified_actor_context(verified_actor):
        assert actor_uid.get() == verified_actor
        with pytest.raises((PermissionError, TransportReached)) as caught:
            repository._commit(principal, specimen, expected, "fixture-key", "fixture-digest")

    if verified_actor != principal.user_id:
        assert session.mock_calls == [], "Foreign verified actor reached commit transport"
        assert isinstance(caught.value, PermissionError)
        assert str(caught.value) == "Verified actor/scope mismatch"
    else:
        assert isinstance(caught.value, TransportReached), "Matching actor must reach transport"
        operation = "create" if expected == 0 else "save:" + specimen.id
        assert session.mock_calls == [call.post(
            repository.url + ":impersonateQuery",
            json={
                "operationName": "GetReceipt",
                "variables": {
                    "organizationId": scope.organization_id,
                    "collectionId": scope.collection_id,
                    "actorUid": principal.user_id,
                    "operation": operation,
                    "idempotencyKey": "fixture-key",
                },
            },
            timeout=30,
        )]
    assert specimen == before, "Admission must not modify the caller's specimen"
