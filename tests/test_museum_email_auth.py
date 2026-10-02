"""The production boundary checks the verified token email, not the login form."""

from types import SimpleNamespace
from unittest.mock import Mock, call

from fastapi.testclient import TestClient
import pytest

from specimen_digitization.application import runtime_auth
from specimen_digitization.application.api import create_app


def verifier(monkeypatch, email, *, verified=True):
    monkeypatch.setattr(
        runtime_auth.app_check,
        "verify_token",
        lambda *_args, **_kwargs: {
            "iss": "https://firebaseappcheck.googleapis.com/123",
            "app_id": "allowed-app",
        },
    )
    monkeypatch.setattr(
        runtime_auth.auth,
        "verify_id_token",
        lambda *_args, **_kwargs: {
            "uid": "museum-staff",
            "email": email,
            "email_verified": verified,
        },
    )
    app = SimpleNamespace(project_id="123")
    return runtime_auth.firebase_verifier(app, ("allowed-app",), app)


@pytest.mark.parametrize(
    "email",
    [
        None,
        True,
        1,
        [],
        {},
        "",
        "staff@example.org",
        "staff@fieldmuseum.org.evil.example",
        "staff@sub.fieldmuseum.org",
        "staff@fieldmuseum.org@evil.example",
        "staff@@fieldmuseum.org",
        "@fieldmuseum.org",
        "staff@fieldmuseum.org.",
        "staff @fieldmuseum.org",
        " staff@fieldmuseum.org",
        "staff@fieldmuseum.org\n",
        "staff\x00@fieldmuseum.org",
        "staff@f\u0131eldmuseum.org",
        "staff@fieldmuseum\uff0eorg",
        ".staff@fieldmuseum.org",
        "staff.@fieldmuseum.org",
        "staff..name@fieldmuseum.org",
        "x" * 65 + "@fieldmuseum.org",
    ],
)
def test_non_museum_or_malformed_verified_claim_cannot_reach_repository(monkeypatch, email):
    verify = verifier(monkeypatch, email)
    with pytest.raises(PermissionError, match="Museum email required"):
        verify("signed-id-token", "signed-app-token")


@pytest.mark.parametrize(
    "email",
    ["staff@fieldmuseum.org", "STAFF@FIELDMUSEUM.ORG", "first.last+review@fieldmuseum.org"],
)
def test_any_verified_museum_identity_can_proceed_to_membership_check(monkeypatch, email):
    # The verifier returns identity only; it never creates a role or membership.
    verify = verifier(monkeypatch, email)
    assert verify("signed-id-token", "signed-app-token") == "museum-staff"


@pytest.mark.parametrize("verified", [False, None, "true", 1])
def test_domain_does_not_replace_email_ownership_verification(monkeypatch, verified):
    with pytest.raises(runtime_auth.EmailVerificationRequired):
        verifier(monkeypatch, "staff@fieldmuseum.org", verified=verified)("id", "check")


OWNER_EMAIL = "anurag@infinative.com"
OWNER_HEADERS = {
    "Authorization": "Bearer owner-id-fixture",
    "X-Firebase-AppCheck": "owner-app-fixture",
    "Idempotency-Key": "owner-auth-fixture",
}
OWNER_BATCH_PATH = "/v1/organizations/fixture-org/batches"
OWNER_BATCH = {"collection_id": "fixture-collection", "display_name": "Auth control"}


def owner_sdk(monkeypatch, *, email=OWNER_EMAIL, verified=True, uid="owner-uid-fixture"):
    # Credential-free SDK responses: no native UID, role, or signed credential.
    identity = Mock(
        return_value={"uid": uid, "email": email, "email_verified": verified}
    )
    appcheck = Mock(
        return_value={
            "iss": "https://firebaseappcheck.googleapis.com/123",
            "app_id": "allowed-app",
        }
    )
    monkeypatch.setattr(runtime_auth.auth, "verify_id_token", identity)
    monkeypatch.setattr(runtime_auth.app_check, "verify_token", appcheck)
    app = SimpleNamespace(project_id="123")
    verify = runtime_auth.firebase_verifier(app, ("allowed-app",), app)
    return verify, identity, appcheck, app


def owner_api(verify, memberships):
    repository = Mock()
    app = create_app(
        mode="production",
        repository=repository,
        blobs=SimpleNamespace(),
        adapters=SimpleNamespace(),
        identity_verifier=verify,
        memberships=memberships,
        origins=["https://specimen-digitization.web.app"],
    )
    return TestClient(app), repository


def owner_membership(**overrides):
    return {
        "organization_id": "fixture-org",
        "collection_id": "fixture-collection",
        "role": "admin",
        "can_view_sensitive": True,
        **overrides,
    }


@pytest.mark.parametrize(
    "email", [OWNER_EMAIL, "ANURAG@INFINATIVE.COM", "AnUrAg@InFiNaTiVe.CoM"]
)
@pytest.mark.parametrize("uid", ["owner-uid-fixture", "another-verified-uid-fixture"])
def test_exact_verified_owner_returns_sdk_uid_without_assigning_membership(
    monkeypatch, email, uid
):
    verify, identity, appcheck, app = owner_sdk(monkeypatch, email=email, uid=uid)
    memberships = Mock(return_value=[])
    client, repository = owner_api(verify, memberships)

    response = client.get("/v1/session", headers=OWNER_HEADERS)

    assert response.status_code == 200
    assert response.json()["user_id"] == uid
    assert response.json()["memberships"] == []
    memberships.assert_called_once_with(uid)
    identity.assert_called_once_with("owner-id-fixture", app=app, check_revoked=True)
    appcheck.assert_called_once_with("owner-app-fixture", app=app)
    repository.document.assert_not_called()
    repository.put_document.assert_not_called()


@pytest.mark.parametrize(
    "email",
    [
        "other@infinative.com",
        "anurag+review@infinative.com",
        "an.urag@infinative.com",
        "anurag@sub.infinative.com",
        "anurag@infinative.com.evil.example",
        "anurag@infinative.com@fieldmuseum.org",
        "anurag@@infinative.com",
        "@infinative.com",
        "anurag@infinative.com.",
        " anurag@infinative.com",
        "anurag@infinative.com ",
        "anurag @infinative.com",
        "anurag@infinative.com\n",
        "anurag\x00@infinative.com",
        "anurag\u200b@infinative.com",
        "\u0430nurag@infinative.com",
        "anurag@\u0131nfinative.com",
        "anurag@infinative\uff0ecom",
        "anurag@infinative\u3002com",
        ".anurag@infinative.com",
        "anurag.@infinative.com",
        "anurag..review@infinative.com",
        '"anurag"@infinative.com',
        "x" * 65 + "@infinative.com",
        "x" * 255 + "@infinative.com",
    ],
)
def test_owner_exception_denies_other_mailboxes_and_lookalikes_before_membership(
    monkeypatch, email
):
    verify, _, _, _ = owner_sdk(monkeypatch, email=email)
    memberships = Mock(return_value=[owner_membership()])
    client, repository = owner_api(verify, memberships)

    response = client.get("/v1/session", headers=OWNER_HEADERS)

    assert response.status_code == 403
    memberships.assert_not_called()
    repository.document.assert_not_called()
    repository.put_document.assert_not_called()


@pytest.mark.parametrize("verified", [False, None, "true", 1])
def test_owner_exception_still_requires_true_verified_email(monkeypatch, verified):
    verify, _, _, _ = owner_sdk(monkeypatch, verified=verified)
    memberships = Mock(return_value=[owner_membership()])
    client, _ = owner_api(verify, memberships)

    response = client.get("/v1/session", headers=OWNER_HEADERS)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "email_verification_required"
    memberships.assert_not_called()


@pytest.mark.parametrize(
    "failure",
    [
        "revoked", "app-sdk-failure", "wrong-issuer", "wrong-app", "missing-id", "missing-app"
    ],
)
def test_owner_exception_preserves_revocation_and_app_check_denials(monkeypatch, failure):
    verify, identity, appcheck, app = owner_sdk(monkeypatch)
    headers = dict(OWNER_HEADERS)
    if failure == "revoked":
        identity.side_effect = ValueError("revoked fixture")
    elif failure == "app-sdk-failure":
        appcheck.side_effect = ValueError("App Check fixture rejected")
    elif failure == "wrong-issuer":
        appcheck.return_value["iss"] = "https://firebaseappcheck.googleapis.com/999"
    elif failure == "wrong-app":
        appcheck.return_value["app_id"] = "unapproved-app"
    elif failure == "missing-id":
        headers["Authorization"] = "Bearer "
    elif failure == "missing-app":
        headers.pop("X-Firebase-AppCheck")
    memberships = Mock(return_value=[owner_membership()])
    client, _ = owner_api(verify, memberships)

    response = client.get("/v1/session", headers=headers)

    assert response.status_code == 403
    memberships.assert_not_called()
    if failure == "revoked":
        identity.assert_called_once_with("owner-id-fixture", app=app, check_revoked=True)
    else:
        identity.assert_not_called()


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [owner_membership(role="viewer")],
        [owner_membership(organization_id="another-org")],
        [owner_membership(collection_id="another-collection")],
        [owner_membership(can_view_sensitive=False)],
    ],
)
def test_owner_exception_does_not_bypass_membership_role_scope_or_sensitivity(
    monkeypatch, rows
):
    verify, _, _, _ = owner_sdk(monkeypatch)
    memberships = Mock(return_value=rows)
    client, repository = owner_api(verify, memberships)

    session = client.get("/v1/session", headers=OWNER_HEADERS)
    assert session.status_code == 200
    assert session.json()["memberships"] == rows
    response = client.post(OWNER_BATCH_PATH, headers=OWNER_HEADERS, json=OWNER_BATCH)

    assert response.status_code == 403
    assert all(entry == call("owner-uid-fixture") for entry in memberships.call_args_list)
    repository.document.assert_not_called()
    repository.put_document.assert_not_called()


@pytest.mark.parametrize("fresh_rows", [[], [owner_membership(role="viewer")]])
def test_owner_write_rechecks_removed_or_downgraded_membership_after_session(
    monkeypatch, fresh_rows
):
    verify, identity, _, _ = owner_sdk(monkeypatch)
    initial_rows = [owner_membership()]
    memberships = Mock(side_effect=[initial_rows, fresh_rows])
    client, repository = owner_api(verify, memberships)

    session = client.get("/v1/session", headers=OWNER_HEADERS)
    assert session.status_code == 200
    assert session.json()["memberships"] == initial_rows
    response = client.post(OWNER_BATCH_PATH, headers=OWNER_HEADERS, json=OWNER_BATCH)

    assert response.status_code == 403
    assert memberships.call_args_list == [
        call("owner-uid-fixture"), call("owner-uid-fixture")
    ]
    assert identity.call_count == 2
    repository.document.assert_not_called()
    repository.put_document.assert_not_called()
