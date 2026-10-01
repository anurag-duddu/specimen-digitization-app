"""Actual committed release settings and body constructor; no effect or fixture coercion."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).parent))
import deploy_runtime as D
import runtime_settings as S


def image(role):
    return f"us-east4-docker.pkg.dev/specimen-digitization/specimen-runtime/{role}@sha256:" + "6" * 64


def test_real_committed_generation_reaches_api_body_without_numeric_coercion():
    assert type(S.READINESS_GENERATION) is int
    assert S.READINESS_GENERATION == 1790562271708431
    body = D.released_bodies({"api": image("api")}, "a" * 40, 456, 1, ["api"])["api"]
    env = {row["name"]: row.get("value") for row in body["template"]["containers"][0]["env"]}
    assert env["SPECIMEN_READINESS_GENERATION"] == "1790562271708431"
    assert env["APP_ENV"] == "production" and env["LOGFIRE_CAPTURE_MODE"] == "approved-content"
    assert env["LOGFIRE_SERVICE_NAME"] == "specimen-api" and env["LOGFIRE_SEND_TO_LOGFIRE"] == "true"
    assert not any(key.startswith("SPECIMEN_TRACE_") for key in env)


def test_arbitrary_numeric_string_remains_refused_by_the_real_validator(monkeypatch):
    monkeypatch.setattr(S, "READINESS_GENERATION", "1790562271708431")
    with pytest.raises(Exception, match="invalid readiness generation"):
        D.released_bodies({"api": image("api")}, "a" * 40, 456, 1, ["api"])


@pytest.mark.parametrize("role", ["api", "worker", "sam"])
def test_each_committed_standing_role_uses_g3_production_settings(role):
    env = S.ROLES[role]["env"]
    assert env["APP_ENV"] == "production"
    assert env["LOGFIRE_CAPTURE_MODE"] == "approved-content"
    assert env["LOGFIRE_SEND_TO_LOGFIRE"] == "true"
    assert env["LOGFIRE_SERVICE_NAME"] == "specimen-" + role
    assert env["LOGFIRE_DISTRIBUTED_TRACING"] == "true"
    assert "LOGFIRE_TOKEN" in S.ROLES[role]["secret_env"]
    assert not any(key.startswith("SPECIMEN_TRACE_") for key in env)
