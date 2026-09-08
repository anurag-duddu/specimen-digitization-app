"""First-admin maintenance cannot change identity, query or existing membership."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("prepared_admin", ROOT / "scripts/data/bootstrap_admin.py")
prepared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepared)


@pytest.fixture
def artifact():
    return prepared.prepare_bootstrap(
        auth_record={"uid": "fixture-admin", "email": "admin@example.invalid", "emailVerified": True, "disabled": False},
        requested_email="admin@example.invalid", requested_uid="fixture-admin",
        organization_id="11111111-1111-4111-8111-111111111111",
        collection_id="22222222-2222-4222-8222-222222222222",
    )


class FakeGoogle:
    plane = "data"

    def __init__(self, artifact):
        self.artifact, self.calls, self.applied = artifact, [], False
        self.identity = {"localId": "fixture-admin", "email": "admin@example.invalid", "emailVerified": True}
        self.prior = False
        self.mutation_result = {"data": {"organizationMember_insert": {"uid": "fixture-admin"}}}
        self.bad_readback = False

    def request(self, api, method, resource, *, body):
        self.calls.append((api, method, resource, copy.deepcopy(body)))
        if api == "identity":
            return {"users": [self.identity]}
        if resource.endswith(":executeGraphql"):
            assert body == self.artifact["request"]
            if isinstance(self.mutation_result, Exception):
                raise self.mutation_result
            self.applied = True
            return self.mutation_result
        assert resource.endswith(":executeGraphqlRead")
        v = self.artifact["request"]["variables"]
        member = {"uid": v["uid"], "collectionId": v["collectionId"].replace("-", ""),
                  "active": True, "role": "admin", "canViewSensitive": False}
        return {"data": {
            "organization": {"id": v["organizationId"].replace("-", "")},
            "collection": {"id": v["collectionId"].replace("-", ""), "organizationId": v["organizationId"]},
            "organizationMember": {"uid": v["uid"], "active": True} if self.applied or self.prior else None,
            "members": [dict(member, canViewSensitive=self.bad_readback)] if self.applied else [],
            "admins": [{"uid": v["uid"]}] if self.applied else [],
        }}


def execute(google, artifact):
    import bootstrap_release
    return bootstrap_release.bootstrap(google, artifact, artifact["artifact_sha256"])


def test_exact_prepared_identity_transaction_and_readback(artifact):
    google = FakeGoogle(artifact)
    receipt = execute(google, artifact)
    assert receipt["membership_verified"] is True
    assert receipt["sensitive_access"] is False
    assert receipt["artifact_sha256"] == artifact["artifact_sha256"]
    assert "fixture-admin" not in json.dumps(receipt)
    assert "admin@example.invalid" not in json.dumps(receipt)
    assert [call[2].split(":")[-1] for call in google.calls] == [
        "lookup", "executeGraphqlRead", "executeGraphql", "executeGraphqlRead",
    ]
    assert google.calls[0][3] == {"email": ["admin@example.invalid"]}


@pytest.mark.parametrize("field,value", [
    ("localId", "other"), ("email", "other@example.invalid"), ("disabled", True),
    ("disabled", 0), ("emailVerified", False), ("emailVerified", 1), ("tenantId", "other"),
])
def test_fresh_auth_mismatch_prevents_any_data_write(artifact, field, value):
    google = FakeGoogle(artifact)
    google.identity[field] = value
    with pytest.raises(ValueError):
        execute(google, artifact)
    assert len(google.calls) == 1


@pytest.mark.parametrize("change", ["query", "sensitive", "state", "extra", "hash", "project"])
def test_changed_prepared_artifact_is_rejected_before_lookup(artifact, change):
    google = FakeGoogle(artifact)
    if change == "query":
        artifact["request"]["query"] += "\nmutation { organization_deleteMany }"
    elif change == "sensitive":
        artifact["request"]["variables"]["canViewSensitive"] = True
    elif change == "hash":
        artifact["artifact_sha256"] = "0" * 64
    else:
        artifact[{"state": "state", "extra": "unknown", "project": "project_id"}[change]] = "changed"
    with pytest.raises(ValueError):
        execute(google, artifact)
    assert not google.calls


def test_existing_membership_cannot_be_elevated_or_replayed(artifact):
    google = FakeGoogle(artifact)
    google.prior = True
    with pytest.raises(ValueError):
        execute(google, artifact)
    assert not google.applied


@pytest.mark.parametrize("result", [RuntimeError("unknown outcome"), {"errors": [{"message": "fixture denial"}]}, {"data": None}, {"data": {}, "errors": [{"message": "partial"}]}])
def test_failed_or_ambiguous_mutation_is_not_retried(artifact, result):
    google = FakeGoogle(artifact)
    google.mutation_result = result
    with pytest.raises((ValueError, RuntimeError)):
        execute(google, artifact)
    assert sum(call[2].endswith(":executeGraphql") for call in google.calls) == 1


def test_readback_cannot_claim_wrong_sensitive_permission(artifact):
    google = FakeGoogle(artifact)
    google.bad_readback = True
    with pytest.raises(ValueError):
        execute(google, artifact)
    assert google.applied


def test_runtime_identity_cannot_invoke_maintenance(artifact):
    google = FakeGoogle(artifact)
    google.plane = "runtime"
    with pytest.raises(ValueError):
        execute(google, artifact)
    assert not google.calls
