"""research/current for a record with no research registered for its current revision.

The production app (research V2) over a real SqlConnectRepository whose session is
the in-memory connector (FakeDataConnect), which answers GetCanonicalResearchBindingV2
the way research_binding_v2.gql does: a row with no registration when none was ever
made, and no row at all when the active registration is for an earlier revision.

The first production field-research run (2026-10-10) hit the second case: the record
had moved on from the revision its native research was registered at, and every field
row showed "Research is unavailable right now" from 36 x 503. Nothing is unavailable:
the record has no current research, so the answer is a 404 the app can tell apart.
"""

import logging

import pytest
from fastapi.testclient import TestClient

import production_e2e_support as support
from specimen_digitization.application.api import create_app
from specimen_digitization.application.production import SqlConnectRepository, actor_uid
from specimen_digitization.application.workflow import SyntheticAdapters
from specimen_digitization.research_harness.compatibility import PublicationUnavailable
from specimen_digitization.research_harness.native_canonical_v2 import CanonicalBindingV2
from specimen_digitization.research_harness.persistence import SqliteStateBackend

API_LOGGER = "specimen_digitization.research_harness.api"
HEADERS = {"Authorization": "Bearer viewer-fixture"}


@pytest.fixture
def host(tmp_path):
    backend = SqliteStateBackend(tmp_path / "research-state.sqlite")
    fake = support.FakeDataConnect(backend, members={support.WORKER: [{
        "organization_id": support.ORG, "collection_id": support.COLLECTION,
        "role": "operator", "can_view_sensitive": False}]})
    blobs = support.GenerationBlobs(tmp_path / "blobs")
    repository = SqlConnectRepository(session=fake, graph_blobs=blobs)
    token = actor_uid.set(support.WORKER)
    try:
        created = repository.create(support.worker_principal(),
            support.specimen_before_adjudication(blobs), "not-registered-intake", "not-registered-intake")
    finally:
        actor_uid.reset(token)
    app = create_app(mode="emulator", repository=repository, blobs=blobs,
        adapters=SyntheticAdapters(blobs, support.LABEL_TEXT),
        identity_verifier=lambda bearer, check: support.WORKER if bearer == "viewer-fixture" else "unknown",
        memberships=repository.memberships, research_version="v2")
    url = (f"/v1/organizations/{support.ORG}/collections/{support.COLLECTION}"
           f"/specimens/{created.id}/research/current")
    with TestClient(app) as client:
        yield client, fake, created, url


def stale_registration(fake, specimen):
    """An active registration for an earlier revision and run of the record."""
    fake.bindings[specimen.id] = {"specimen_id": specimen.id, "active": True,
        "current_record_version_id": "earlier-record-version", "canonical_run_id": "earlier-run",
        "current_canonical_revision": specimen.version - 1, "current_snapshot_sha256": "0" * 64}


@pytest.mark.parametrize("registration", ["never_registered", "registered_for_an_earlier_revision"])
def test_a_record_with_no_current_research_is_404_not_503(host, caplog, registration):
    client, fake, specimen, url = host
    if registration == "registered_for_an_earlier_revision":
        stale_registration(fake, specimen)
    caplog.set_level(logging.DEBUG, logger=API_LOGGER)

    reply = client.get(url, headers=HEADERS)

    assert reply.status_code == 404, reply.text
    assert reply.json() == {"detail": "research_not_registered"}
    assert reply.headers["cache-control"] == "no-store, private"
    assert "GetCanonicalResearchBindingV2" in fake.calls
    # Not an outage: no "research route unavailable" line for the operator.
    assert [record for record in caplog.records if record.name == API_LOGGER] == []


def test_the_binding_reader_tells_no_registration_from_an_unreadable_one():
    scope = support.worker_principal().scope
    specimen_id = "00000000-0000-4000-8000-000000000003"
    # The row the read returns when no registration was ever made (research_binding_v2.gql).
    canonical = dict.fromkeys(("organization_id", "collection_id", "specimen_id", "record_revision",
        "record_version_id", "canonical_run_id", "host_record_version_id", "snapshot_sha256", "sensitive"))
    empty = {"canonical": canonical, "registrations": [], "snapshot": {}, "projection": [],
             "active_registration_count": 0, "causal": {}}

    def code(row):
        with pytest.raises(PublicationUnavailable) as raised:
            CanonicalBindingV2.from_native(scope, specimen_id, row)
        return type(raised.value).__name__, raised.value.args[0]

    assert code(None) == ("ResearchNotRegistered", "native_v2_registration_not_current")
    assert code(empty) == ("ResearchNotRegistered", "native_v2_registration_missing")
    # A count that disagrees with the rows, or two registrations, is not "none": it stays a 503.
    assert code({**empty, "active_registration_count": 1}) == (
        "PublicationUnavailable", "native_v2_registration_missing_or_ambiguous")
    assert code({**empty, "registrations": [{}, {}], "active_registration_count": 2}) == (
        "PublicationUnavailable", "native_v2_registration_missing_or_ambiguous")
    assert code({"canonical": {}}) == ("PublicationUnavailable", "native_v2_binding_unavailable")
