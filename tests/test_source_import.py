"""Server-side import from a registered source keeps intake's integrity proof.

Upload completion proves declared-equals-actual because a client declared the
metadata first and the server checked it against the uploaded bytes. The
from-source path has no client declaration, so the equivalent proof is the
generation binding plus the digest the server itself recorded at capture. The
first test in this file is that proof; everything else depends on it holding.
"""

from source_fixtures import (
    FIRST_GENERATION,
    HEADERS,
    OBJECT_PREFIX,
    PREFIX,
    SECOND_GENERATION,
    SOURCE_ID,
    capture,
    import_objects,
    jpeg_bytes,
    listed,
    open_batch,
    png_bytes,
    queued,
    registered,
    source_client,
    write_object,
)


def test_import_refuses_an_object_changed_since_the_inventory(tmp_path):
    """The whole point: bytes that are not the bytes the reviewer saw are refused."""
    objects = tmp_path / "objects"
    write_object(
        objects, OBJECT_PREFIX + "subject_1.jpeg", jpeg_bytes(), FIRST_GENERATION
    )
    client = source_client(tmp_path, objects)
    capture(client)
    selected = listed(client)["items"]
    assert len(selected) == 1

    # The object is replaced after the reviewer chose it and before they import.
    replaced = write_object(
        objects,
        OBJECT_PREFIX + "subject_1.jpeg",
        jpeg_bytes(colour="black"),
        SECOND_GENERATION,
    )
    assert replaced != selected[0]["generation"]

    response = import_objects(client, open_batch(client), selected)

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "source_object_changed"
    assert queued(client) == []


def test_import_refuses_a_generation_never_inventoried(tmp_path):
    """A reviewer cannot bind an import to a generation the server never saw."""
    objects = tmp_path / "objects"
    write_object(
        objects, OBJECT_PREFIX + "subject_1.jpeg", jpeg_bytes(), FIRST_GENERATION
    )
    client = source_client(tmp_path, objects)
    capture(client)
    row = dict(listed(client)["items"][0], generation=str(SECOND_GENERATION))

    response = import_objects(client, open_batch(client), [row])

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "source_object_changed"
    assert queued(client) == []


def test_import_refuses_every_object_when_one_changed(tmp_path):
    """A partly valid selection never part-imports: nothing is created."""
    objects = tmp_path / "objects"
    for ordinal in (1, 2, 3):
        write_object(
            objects,
            OBJECT_PREFIX + f"subject_{ordinal}.jpeg",
            jpeg_bytes(size=(120 + ordinal, 80)),
            FIRST_GENERATION,
        )
    client = source_client(tmp_path, objects)
    capture(client)
    selected = listed(client)["items"]
    assert len(selected) == 3
    write_object(
        objects,
        OBJECT_PREFIX + "subject_2.jpeg",
        jpeg_bytes(colour="black", size=(122, 80)),
        SECOND_GENERATION,
    )

    response = import_objects(client, open_batch(client), selected)

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "source_object_changed"
    assert queued(client) == []


def test_import_creates_specimens_bound_to_the_inventoried_bytes(tmp_path):
    objects = tmp_path / "objects"
    payloads = {
        OBJECT_PREFIX + f"subject_{ordinal}.jpeg": jpeg_bytes(size=(120 + ordinal, 80))
        for ordinal in (1, 2)
    }
    for name, data in payloads.items():
        write_object(objects, name, data, FIRST_GENERATION)
    client = source_client(tmp_path, objects)
    capture(client)
    selected = listed(client)["items"]

    response = import_objects(client, open_batch(client), selected)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["requested"] == 2
    assert body["imported"] == 2
    assert body["duplicates"] == 0
    assert {item["state"] for item in body["items"]} == {"imported"}
    import hashlib

    for item in body["items"]:
        assert item["sha256"] == hashlib.sha256(payloads[item["object_name"]]).hexdigest()
        assert item["specimen_id"]
    assert len(queued(client)) == 2


def test_reimporting_the_same_selection_creates_nothing_new(tmp_path):
    """Select-all run twice must not duplicate, via the existing checksum index."""
    objects = tmp_path / "objects"
    for ordinal in (1, 2):
        write_object(
            objects,
            OBJECT_PREFIX + f"subject_{ordinal}.jpeg",
            jpeg_bytes(size=(120 + ordinal, 80)),
            FIRST_GENERATION,
        )
    client = source_client(tmp_path, objects)
    capture(client)
    selected = listed(client)["items"]
    batch = open_batch(client)
    first = import_objects(client, batch, selected)
    assert first.status_code == 200, first.text

    second = import_objects(client, open_batch(client, "Second pass"), selected)

    assert second.status_code == 200, second.text
    body = second.json()
    assert body["imported"] == 0
    assert body["duplicates"] == 2
    assert {item["state"] for item in body["items"]} == {"duplicate"}
    assert {item["specimen_id"] for item in body["items"]} == {
        item["specimen_id"] for item in first.json()["items"]
    }
    assert len(queued(client)) == 2


def test_import_does_not_dispatch_processing(tmp_path):
    """Importing is not running. Workstream C owns dispatch and is blocked."""
    objects = tmp_path / "objects"
    write_object(
        objects, OBJECT_PREFIX + "subject_1.jpeg", jpeg_bytes(), FIRST_GENERATION
    )
    client = source_client(tmp_path, objects)
    capture(client)

    import_objects(client, open_batch(client), listed(client)["items"])

    assert [item["stage"] for item in queued(client)] == ["ingested"]


def test_import_refuses_media_the_source_does_not_permit(tmp_path):
    objects = tmp_path / "objects"
    write_object(
        objects, OBJECT_PREFIX + "subject_1.jpeg", jpeg_bytes(), FIRST_GENERATION
    )
    # A PNG named as a JPEG: the bytes decide, exactly as completion decides.
    write_object(
        objects, OBJECT_PREFIX + "subject_2.jpeg", png_bytes(), FIRST_GENERATION
    )
    client = source_client(tmp_path, objects)
    capture(client)
    rows = {row["object_name"]: row for row in listed(client)["items"]}
    assert rows[OBJECT_PREFIX + "subject_2.jpeg"]["media_type"] == "image/png"

    response = import_objects(client, open_batch(client), list(rows.values()))

    assert response.status_code == 200, response.text
    states = {item["object_name"]: item["state"] for item in response.json()["items"]}
    assert states[OBJECT_PREFIX + "subject_1.jpeg"] == "imported"
    assert states[OBJECT_PREFIX + "subject_2.jpeg"] == "unsupported_media_type"
    assert len(queued(client)) == 1


def test_import_refuses_an_object_absent_from_the_inventory(tmp_path):
    objects = tmp_path / "objects"
    write_object(
        objects, OBJECT_PREFIX + "subject_1.jpeg", jpeg_bytes(), FIRST_GENERATION
    )
    client = source_client(tmp_path, objects)
    capture(client)
    write_object(
        objects,
        OBJECT_PREFIX + "subject_later.jpeg",
        jpeg_bytes(colour="red"),
        FIRST_GENERATION,
    )

    response = import_objects(
        client,
        open_batch(client),
        [
            {
                "object_name": OBJECT_PREFIX + "subject_later.jpeg",
                "generation": str(FIRST_GENERATION),
            }
        ],
    )

    assert response.status_code == 200, response.text
    assert [item["state"] for item in response.json()["items"]] == ["not_in_source"]
    assert queued(client) == []


def test_import_refuses_an_object_outside_the_registered_prefix(tmp_path):
    objects = tmp_path / "objects"
    write_object(
        objects, OBJECT_PREFIX + "subject_1.jpeg", jpeg_bytes(), FIRST_GENERATION
    )
    write_object(objects, "elsewhere/private.jpeg", jpeg_bytes(), FIRST_GENERATION)
    client = source_client(tmp_path, objects)
    capture(client)

    response = import_objects(
        client,
        open_batch(client),
        [
            {
                "object_name": "elsewhere/private.jpeg",
                "generation": str(FIRST_GENERATION),
            }
        ],
    )

    assert response.status_code == 422, response.text
    assert queued(client) == []


def test_import_requires_a_registered_source(tmp_path):
    objects = tmp_path / "objects"
    write_object(
        objects, OBJECT_PREFIX + "subject_1.jpeg", jpeg_bytes(), FIRST_GENERATION
    )
    client = source_client(tmp_path, objects)
    capture(client)
    rows = listed(client)["items"]

    response = import_objects(
        client,
        open_batch(client),
        rows,
        source_id="00000000-0000-4000-8000-0000000000ff",
    )

    assert response.status_code == 404, response.text
    assert queued(client) == []


def test_import_sensitivity_must_match_the_retained_batch(tmp_path):
    objects = tmp_path / "objects"
    write_object(
        objects, OBJECT_PREFIX + "subject_1.jpeg", jpeg_bytes(), FIRST_GENERATION
    )
    client = source_client(tmp_path, objects)
    capture(client)
    batch = open_batch(client, sensitive=False)

    response = import_objects(
        client, batch, listed(client)["items"], sensitive=True
    )

    assert response.status_code == 422, response.text
    assert queued(client) == []


def test_import_is_bounded_per_request(tmp_path):
    from specimen_digitization.application.source_import import MAX_IMPORT_OBJECTS

    objects = tmp_path / "objects"
    write_object(
        objects, OBJECT_PREFIX + "subject_1.jpeg", jpeg_bytes(), FIRST_GENERATION
    )
    client = source_client(tmp_path, objects)
    capture(client)
    # Distinct names, so the bound is what refuses this and not the repeat check.
    oversized = [
        {
            "object_name": OBJECT_PREFIX + f"subject_{ordinal}.jpeg",
            "generation": str(FIRST_GENERATION),
        }
        for ordinal in range(MAX_IMPORT_OBJECTS + 1)
    ]

    response = import_objects(client, open_batch(client), oversized)

    assert response.status_code == 422, response.text
    assert queued(client) == []


def test_import_rejects_a_repeated_object_in_one_request(tmp_path):
    objects = tmp_path / "objects"
    write_object(
        objects, OBJECT_PREFIX + "subject_1.jpeg", jpeg_bytes(), FIRST_GENERATION
    )
    client = source_client(tmp_path, objects)
    capture(client)
    row = listed(client)["items"][0]

    response = import_objects(client, open_batch(client), [row, row])

    assert response.status_code == 422, response.text
    assert queued(client) == []


def test_import_requires_a_configured_source_runtime(tmp_path):
    """An unconfigured runtime has no sources and offers no import route."""
    from fastapi.testclient import TestClient
    from specimen_digitization.application.api import local_app

    client = TestClient(local_app(tmp_path / "state", "test-only-local-token"))

    response = client.post(
        PREFIX + "/batches/00000000-0000-4000-8000-0000000000aa/items:from-source",
        headers=HEADERS,
        json={
            "source_id": SOURCE_ID,
            "objects": [
                {
                    "object_name": OBJECT_PREFIX + "subject_1.jpeg",
                    "generation": str(FIRST_GENERATION),
                }
            ],
        },
    )

    assert response.status_code == 404, response.text


def test_import_refuses_a_source_registered_to_another_collection(tmp_path):
    objects = tmp_path / "objects"
    write_object(
        objects, OBJECT_PREFIX + "subject_1.jpeg", jpeg_bytes(), FIRST_GENERATION
    )
    other = registered(collection_id="00000000-0000-4000-8000-0000000000cc")
    client = source_client(tmp_path, objects, sources=[other])

    response = client.post(
        PREFIX + f"/sources/{SOURCE_ID}/inventory", headers=HEADERS
    )

    assert response.status_code in {403, 404}, response.text
