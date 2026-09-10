"""The production boundary checks the verified token email, not the login form."""

from types import SimpleNamespace

import pytest

from specimen_digitization.application import runtime_auth


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
