"""Offline identity validation and private artifact tests; no Firebase access."""

import importlib.util
import json
from pathlib import Path
import stat

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts/data/bootstrap_admin.py"
SPEC = importlib.util.spec_from_file_location("bootstrap_admin", MODULE_PATH)
assert SPEC and SPEC.loader
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


@pytest.fixture
def inputs():
    return {
        "auth_record": {
            "uid": "synthetic-admin",
            "email": "synthetic@example.invalid",
            "emailVerified": True,
            "disabled": False,
            "private_extra": "must-not-be-copied",
        },
        "requested_uid": "synthetic-admin",
        "requested_email": "synthetic@example.invalid",
        "organization_id": "11111111-1111-4111-8111-111111111111",
        "collection_id": "22222222-2222-4222-8222-222222222222",
    }


def test_prepares_transaction_with_explicit_scope_and_no_sensitive_default(inputs):
    artifact = bootstrap.prepare_bootstrap(**inputs)
    assert artifact["state"] == "prepared_not_applied"
    assert artifact["request"]["variables"] == {
        "organizationId": inputs["organization_id"],
        "collectionId": inputs["collection_id"],
        "uid": inputs["requested_uid"],
        "canViewSensitive": False,
    }
    assert "must-not-be-copied" not in json.dumps(artifact)
    assert artifact == bootstrap.prepare_bootstrap(**inputs)
    inputs["can_view_sensitive"] = True
    assert bootstrap.prepare_bootstrap(**inputs)["artifact_sha256"] != artifact["artifact_sha256"]


@pytest.mark.parametrize(
    ("field", "value"),
    [("uid", "different"), ("email", "Synthetic@example.invalid"),
     ("emailVerified", False), ("emailVerified", 1), ("disabled", True), ("disabled", 0)],
)
def test_auth_record_must_match_exact_verified_enabled_account(inputs, field, value):
    inputs["auth_record"][field] = value
    with pytest.raises(ValueError):
        bootstrap.prepare_bootstrap(**inputs)


@pytest.mark.parametrize("field", ["uid", "email", "emailVerified", "disabled"])
def test_missing_auth_claim_is_denied(inputs, field):
    del inputs["auth_record"][field]
    with pytest.raises(ValueError):
        bootstrap.prepare_bootstrap(**inputs)


@pytest.mark.parametrize(
    ("field", "value"),
    [("requested_uid", ""), ("requested_uid", " space"),
     ("requested_email", ""), ("requested_email", "bad"),
     ("organization_id", "unknown"), ("collection_id", None),
     ("can_view_sensitive", "false"), ("can_view_sensitive", 1)],
)
def test_no_guessed_or_coerced_inputs(inputs, field, value):
    inputs[field] = value
    with pytest.raises(ValueError):
        bootstrap.prepare_bootstrap(**inputs)


def test_private_artifact_exclusive_and_outside_git(inputs, tmp_path):
    tmp_path.chmod(0o700)
    output = tmp_path / "private.json"
    artifact = bootstrap.prepare_bootstrap(**inputs)
    bootstrap.write_private_artifact(output, artifact)
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert json.loads(output.read_text()) == artifact
    with pytest.raises(FileExistsError):
        bootstrap.write_private_artifact(output, artifact)
    (tmp_path / "alias.json").symlink_to(output)
    with pytest.raises(FileExistsError):
        bootstrap.write_private_artifact(tmp_path / "alias.json", artifact)
    (tmp_path / ".git").write_text("gitdir: fake")
    with pytest.raises(ValueError, match="outside Git"):
        bootstrap.write_private_artifact(tmp_path / "new.json", artifact)


def test_private_artifact_rejects_public_directory(inputs, tmp_path):
    tmp_path.chmod(0o755)
    with pytest.raises(ValueError, match="mode0700"):
        bootstrap.write_private_artifact(tmp_path / "private.json", bootstrap.prepare_bootstrap(**inputs))


def test_bootstrap_not_published_as_runtime_operation():
    connector = MODULE_PATH.parents[2] / "dataconnect/connector"
    assert all("PrepareFirstAdministrator" not in path.read_text() for path in connector.glob("*.gql"))
