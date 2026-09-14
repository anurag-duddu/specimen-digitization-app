"""Role and sensitivity gates on the source routes, across every role.

Synthetic mode has exactly one membership, a reviewer who may view sensitive
records, so it cannot exercise these. These build an emulator-mode application
with an explicit membership row instead, which is how the role and
classification rules are actually reachable from a test.

The production connector enforces the same two rules in its own `@check`
expressions — `source_inventory` writes are reviewer-or-above, and a sensitive
document needs `canViewSensitive`. These pin the API half, which is the half
that also holds for the local SQLite repository, whose document store has no
classification gate of its own.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from specimen_digitization.application.api import (
    SYNTHETIC_COLLECTION,
    SYNTHETIC_ORG,
    SYNTHETIC_TEXT,
    create_app,
)
from specimen_digitization.application.source_reader import LocalSourceReader
from specimen_digitization.application.source_registry import SourceRegistry
from specimen_digitization.application.storage import LocalBlobs, SQLiteRepository
from specimen_digitization.application.workflow import SyntheticAdapters

from source_fixtures import (
    FIRST_GENERATION,
    OBJECT_PREFIX,
    PREFIX,
    SOURCE_ID,
    jpeg_bytes,
    registered,
    write_object,
)

HEADERS = {"Authorization": "Bearer emulator-fixture", "Idempotency-Key": "role-test"}


def member_client(root: Path, objects: Path, role: str, can_view_sensitive=True):
    blobs = LocalBlobs(root / "blobs")
    app = create_app(
        mode="emulator",
        repository=SQLiteRepository(root / "state.sqlite3"),
        blobs=blobs,
        adapters=SyntheticAdapters(blobs, SYNTHETIC_TEXT),
        identity_verifier=lambda bearer, appcheck: "member-fixture",
        memberships=lambda user: [
            {
                "organization_id": SYNTHETIC_ORG,
                "collection_id": SYNTHETIC_COLLECTION,
                "role": role,
                "can_view_sensitive": can_view_sensitive,
            }
        ],
        source_registry=SourceRegistry([registered()]),
        source_reader=LocalSourceReader(objects),
    )
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def objects(tmp_path):
    root = tmp_path / "objects"
    write_object(root, OBJECT_PREFIX + "subject_1.jpeg", jpeg_bytes(), FIRST_GENERATION)
    return root


def capture(client):
    return client.post(PREFIX + f"/sources/{SOURCE_ID}/inventory", headers=HEADERS)


@pytest.mark.parametrize("role", ["reviewer", "manager", "admin"])
def test_a_reviewer_or_above_may_capture(tmp_path, objects, role):
    client = member_client(tmp_path / role, objects, role)

    assert capture(client).status_code == 200, capture(client).text


@pytest.mark.parametrize("role", ["viewer", "operator"])
def test_below_reviewer_may_not_capture(tmp_path, objects, role):
    """Capture decides what a whole collection can see; it takes the review tier."""
    client = member_client(tmp_path / role, objects, role)

    response = capture(client)

    assert response.status_code == 403, response.text


def test_a_viewer_may_browse_a_captured_snapshot(tmp_path, objects):
    reviewer = member_client(tmp_path / "shared", objects, "reviewer")
    assert capture(reviewer).status_code == 200
    viewer = member_client(tmp_path / "shared", objects, "viewer")

    listing = viewer.get(PREFIX + f"/sources/{SOURCE_ID}/objects", headers=HEADERS)

    assert listing.status_code == 200, listing.text
    assert len(listing.json()["items"]) == 1


def test_a_viewer_may_not_import(tmp_path, objects):
    reviewer = member_client(tmp_path / "shared", objects, "reviewer")
    assert capture(reviewer).status_code == 200
    batch = reviewer.post(
        PREFIX + "/batches",
        headers=HEADERS,
        json={"collection_id": SYNTHETIC_COLLECTION, "display_name": "Roles"},
    ).json()["batch_id"]
    rows = reviewer.get(
        PREFIX + f"/sources/{SOURCE_ID}/objects", headers=HEADERS
    ).json()["items"]
    viewer = member_client(tmp_path / "shared", objects, "viewer")

    response = viewer.post(
        PREFIX + f"/batches/{batch}/items:from-source",
        headers=HEADERS,
        json={
            "source_id": SOURCE_ID,
            "objects": [
                {"object_name": r["object_name"], "generation": r["generation"]}
                for r in rows
            ],
        },
    )

    assert response.status_code == 403, response.text


def test_a_snapshot_is_sensitive_and_needs_that_permission(tmp_path, objects):
    """Object names under a collection's prefix are collection information."""
    reviewer = member_client(tmp_path / "shared", objects, "reviewer")
    assert capture(reviewer).status_code == 200
    restricted = member_client(
        tmp_path / "shared", objects, "reviewer", can_view_sensitive=False
    )

    listing = restricted.get(
        PREFIX + f"/sources/{SOURCE_ID}/objects", headers=HEADERS
    )
    detail = restricted.get(PREFIX + f"/sources/{SOURCE_ID}", headers=HEADERS)
    sources = restricted.get(PREFIX + "/sources", headers=HEADERS)

    assert listing.status_code == 403, listing.text
    # Configuration is not the snapshot: the source is still visible, its rows
    # are not, and a listing omits them rather than refusing the whole page.
    assert detail.status_code == 200, detail.text
    assert detail.json()["inventory"] is None
    assert sources.json()["items"][0]["inventory"] is None


def test_capturing_needs_permission_for_what_it_will_retain(tmp_path, objects):
    restricted = member_client(
        tmp_path / "restricted", objects, "reviewer", can_view_sensitive=False
    )

    assert capture(restricted).status_code == 403, capture(restricted).text


def test_a_member_of_another_organization_sees_nothing(tmp_path, objects):
    client = member_client(tmp_path / "other", objects, "reviewer")
    other = "00000000-0000-4000-8000-0000000000dd"

    listing = client.get(f"/v1/organizations/{other}/sources", headers=HEADERS)
    named = client.get(
        f"/v1/organizations/{other}/sources/{SOURCE_ID}", headers=HEADERS
    )

    assert listing.json()["items"] == []
    assert named.status_code == 404, named.text
