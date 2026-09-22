"""The worker binds the API's named SQL endpoint; no cloud call is made here."""

import pytest

from specimen_digitization.application.production import (
    SqlConnectRepository,
    sql_endpoint_from_env,
)

PINNED = {
    "SPECIMEN_SQL_LOCATION": "us-east4",
    "SPECIMEN_SQL_SERVICE": "specimen-digitization-service",
    "SPECIMEN_SQL_CONNECTOR": "specimen-server",
}


@pytest.fixture(autouse=True)
def no_emulator(monkeypatch):
    monkeypatch.delenv("SPECIMEN_SQL_EMULATOR_HOST", raising=False)


def repository(**overrides):
    # A supplied session keeps this construction offline and credential-free.
    return SqlConnectRepository(session=object(), **overrides)


def test_no_configuration_keeps_the_existing_defaults():
    assert sql_endpoint_from_env({}) == {}
    assert repository().url.endswith(
        "/projects/specimen-digitization/locations/us-east4"
        "/services/specimen-digitization-service/connectors/specimen-server"
    )


def test_the_pinned_endpoint_is_read_the_way_the_api_reads_it():
    values = sql_endpoint_from_env(PINNED)
    assert values == {
        "location": "us-east4",
        "service": "specimen-digitization-service",
        "connector": "specimen-server",
    }
    assert repository(**values).url == (
        "https://firebasedataconnect.googleapis.com/v1"
        "/projects/specimen-digitization/locations/us-east4"
        "/services/specimen-digitization-service/connectors/specimen-server"
    )


def test_a_different_approved_endpoint_reaches_the_worker():
    changed = dict(PINNED, SPECIMEN_SQL_CONNECTOR="specimen-server-two")
    assert repository(**sql_endpoint_from_env(changed)).url.endswith(
        "/connectors/specimen-server-two"
    )


@pytest.mark.parametrize("key", list(PINNED))
def test_a_half_supplied_endpoint_is_refused_rather_than_mixed_with_defaults(key):
    partial = {k: v for k, v in PINNED.items() if k != key}
    with pytest.raises(ValueError, match="location, service and connector"):
        sql_endpoint_from_env(partial)


@pytest.mark.parametrize(
    "value",
    ["", "../other", "Specimen-Server", "specimen_server", "a", "x" * 64,
     "specimen server", "specimen-server/", "-specimen"],
)
def test_the_same_validation_the_api_applies_rejects_a_bad_name(value):
    with pytest.raises(ValueError, match="location, service and connector"):
        sql_endpoint_from_env(dict(PINNED, SPECIMEN_SQL_CONNECTOR=value))


def test_the_process_environment_is_the_default_source(monkeypatch):
    for key, value in dict(PINNED, SPECIMEN_SQL_SERVICE="other-service").items():
        monkeypatch.setenv(key, value)
    assert sql_endpoint_from_env()["service"] == "other-service"
