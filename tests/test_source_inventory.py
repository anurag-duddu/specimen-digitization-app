"""Source registry is configuration; inventory is a snapshot, never a live listing."""

import pytest

from source_fixtures import (
    BUCKET,
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
    registered,
    source_client,
    write_object,
)
from specimen_digitization.application.source_registry import (
    SUPPORTED_MEDIA_TYPES,
    RegisteredSource,
    SourceRegistry,
)


def slides(objects, count, generation=FIRST_GENERATION):
    for ordinal in range(1, count + 1):
        write_object(
            objects,
            OBJECT_PREFIX + f"subject_{ordinal:04d}.jpeg",
            jpeg_bytes(size=(100 + ordinal, 80)),
            generation,
        )


# Registration is configuration, validated once, at construction.


@pytest.mark.parametrize(
    "field,value",
    [
        ("media_types", ("image/heic",)),
        ("media_types", ("image/dng",)),
        ("media_types", ()),
        ("media_types", ("image/jpeg", "image/jpeg")),
        ("prefix", "../escape/"),
        ("prefix", "/absolute/"),
        ("prefix", "no-trailing-separator"),
        ("prefix", "control" + chr(0) + "char/"),
        ("prefix", ""),
        ("bucket", "UPPERCASE"),
        ("bucket", ""),
        ("source_id", "not-a-uuid"),
        ("collection_id", "not-a-uuid"),
        ("registered_by", ""),
        ("registered_at", "2026-09-14"),
        ("registered_at", "2026-09-14T00:00:00+02:00"),
    ],
)
def test_registration_refuses_unsound_configuration(field, value):
    with pytest.raises(ValueError):
        registered(**{field: value})


def test_registration_admits_only_verifiable_media_types():
    source = registered(media_types=SUPPORTED_MEDIA_TYPES)
    assert set(source.media_types) == set(SUPPORTED_MEDIA_TYPES)
    assert "image/heic" not in SUPPORTED_MEDIA_TYPES


def test_registry_refuses_duplicate_source_identifiers():
    with pytest.raises(ValueError):
        SourceRegistry([registered(), registered(prefix="other/")])


def test_registered_source_is_frozen():
    with pytest.raises(ValueError):
        registered().prefix = "elsewhere/"


def test_the_frozen_release_cohort_is_untouched():
    """This surface reuses SourceObject and changes nothing else in that module."""
    from specimen_digitization.application import pilot_manifest

    assert not issubclass(RegisteredSource, pilot_manifest.PilotSpecimen)
    bounds = {
        type(item).__name__: item
        for item in pilot_manifest.PilotManifest.model_fields["specimens"].metadata
    }
    assert bounds["MinLen"].min_length == 10
    assert bounds["MaxLen"].max_length == 10
    ordinal = pilot_manifest.PilotSpecimen.model_fields["ordinal"].metadata
    assert {getattr(item, "ge", None) for item in ordinal} & {1}
    assert {getattr(item, "le", None) for item in ordinal} & {10}
    assert set(pilot_manifest.Selection.model_fields) == {
        "order",
        "source_inventory_sha256",
    }
    assert set(pilot_manifest.SourceObject.model_fields) == {
        "bucket",
        "object_name",
        "generation",
        "sha256",
        "size_bytes",
        "crc32c",
        "md5_hash",
    }


# The registry over HTTP.


def test_sources_lists_registered_configuration(tmp_path):
    objects = tmp_path / "objects"
    slides(objects, 1)
    client = source_client(tmp_path, objects)

    body = client.get(PREFIX + "/sources", headers=HEADERS).json()

    assert body["next_cursor"] is None
    assert len(body["items"]) == 1
    source = body["items"][0]
    assert source["source_id"] == SOURCE_ID
    assert source["bucket"] == BUCKET
    assert source["prefix"] == OBJECT_PREFIX
    assert source["media_types"] == ["image/jpeg"]
    assert source["registered_by"] == "fixture-administrator"
    assert source["inventory"] is None


def test_sources_hides_a_source_registered_to_another_collection(tmp_path):
    objects = tmp_path / "objects"
    slides(objects, 1)
    client = source_client(
        tmp_path,
        objects,
        sources=[registered(collection_id="00000000-0000-4000-8000-0000000000cc")],
    )

    assert client.get(PREFIX + "/sources", headers=HEADERS).json()["items"] == []


def test_there_is_no_endpoint_that_creates_a_source(tmp_path):
    objects = tmp_path / "objects"
    slides(objects, 1)
    client = source_client(tmp_path, objects)

    created = client.post(
        PREFIX + "/sources",
        headers=HEADERS,
        json={
            "source_id": "00000000-0000-4000-8000-0000000000ee",
            "collection_id": "00000000-0000-4000-8000-000000000002",
            "bucket": BUCKET,
            "prefix": "anything/",
            "media_types": ["image/jpeg"],
        },
    )

    assert created.status_code == 405, created.text


def test_objects_require_a_captured_snapshot(tmp_path):
    objects = tmp_path / "objects"
    slides(objects, 1)
    client = source_client(tmp_path, objects)

    response = client.get(PREFIX + f"/sources/{SOURCE_ID}/objects", headers=HEADERS)

    assert response.status_code == 404, response.text


# Capture.


def test_capture_snapshots_only_objects_under_the_prefix(tmp_path):
    objects = tmp_path / "objects"
    slides(objects, 2)
    write_object(objects, "elsewhere/private.jpeg", jpeg_bytes(), FIRST_GENERATION)
    client = source_client(tmp_path, objects)

    inventory = capture(client)

    assert inventory["object_count"] == 2
    names = [row["object_name"] for row in listed(client)["items"]]
    assert names == [
        OBJECT_PREFIX + "subject_0001.jpeg",
        OBJECT_PREFIX + "subject_0002.jpeg",
    ]


def test_capture_records_the_source_object_shape(tmp_path):
    import hashlib

    objects = tmp_path / "objects"
    data = jpeg_bytes(size=(101, 80))
    generation = write_object(
        objects, OBJECT_PREFIX + "subject_0001.jpeg", data, FIRST_GENERATION
    )
    client = source_client(tmp_path, objects)
    capture(client)

    row = listed(client)["items"][0]

    assert row["bucket"] == BUCKET
    assert row["object_name"] == OBJECT_PREFIX + "subject_0001.jpeg"
    assert row["generation"] == generation
    assert row["sha256"] == hashlib.sha256(data).hexdigest()
    assert row["size_bytes"] == len(data)
    assert row["media_type"] == "image/jpeg"
    assert row["state"] == "available"
    assert row["specimen_id"] is None


def test_internal_storage_handles_stay_off_the_wire(tmp_path):
    """`summary` never exposes `asset.blob_ref`; a snapshot header matches that."""
    objects = tmp_path / "objects"
    slides(objects, 1)
    client = source_client(tmp_path, objects)

    inventory = capture(client)
    detail = client.get(PREFIX + f"/sources/{SOURCE_ID}", headers=HEADERS).json()

    assert "entries_blob_ref" not in inventory
    assert "entries_blob_ref" not in detail["inventory"]
    assert inventory["entries_sha256"] == detail["inventory"]["entries_sha256"]


def test_capture_is_a_snapshot_not_a_live_listing(tmp_path):
    objects = tmp_path / "objects"
    slides(objects, 1)
    client = source_client(tmp_path, objects)
    first = capture(client)

    write_object(
        objects, OBJECT_PREFIX + "subject_0002.jpeg", jpeg_bytes(), FIRST_GENERATION
    )

    # The listing still shows the snapshot the reviewer is choosing from.
    body = listed(client)
    assert body["object_count"] == 1
    assert body["inventory_id"] == first["inventory_id"]
    assert len(body["items"]) == 1

    second = capture(client)
    assert second["inventory_id"] != first["inventory_id"]
    assert listed(client)["object_count"] == 2


def test_recapturing_identical_rows_keeps_the_same_snapshot(tmp_path):
    objects = tmp_path / "objects"
    slides(objects, 2)
    client = source_client(tmp_path, objects)
    first = capture(client)

    second = capture(client)

    assert second["inventory_id"] == first["inventory_id"]
    assert second["entries_sha256"] == first["entries_sha256"]
    assert second["revision"] == first["revision"]


def test_a_refresh_reads_only_what_moved(tmp_path):
    """A first capture reads the prefix; a refresh must not read it all again."""
    from source_fixtures import CountingReader
    from specimen_digitization.application.source_reader import LocalSourceReader

    objects = tmp_path / "objects"
    slides(objects, 3)
    reader = CountingReader(LocalSourceReader(objects))
    client = source_client(tmp_path, objects, reader=reader)
    capture(client)
    assert len(reader.reads) == 3

    reader.reads.clear()
    write_object(
        objects,
        OBJECT_PREFIX + "subject_0002.jpeg",
        jpeg_bytes(colour="black"),
        SECOND_GENERATION,
    )
    write_object(
        objects, OBJECT_PREFIX + "subject_0004.jpeg", jpeg_bytes(), FIRST_GENERATION
    )
    capture(client)

    assert sorted(reader.reads) == [
        OBJECT_PREFIX + "subject_0002.jpeg",
        OBJECT_PREFIX + "subject_0004.jpeg",
    ]
    assert listed(client)["object_count"] == 4


def test_a_refresh_of_an_unchanged_prefix_reads_nothing(tmp_path):
    from source_fixtures import CountingReader
    from specimen_digitization.application.source_reader import LocalSourceReader

    objects = tmp_path / "objects"
    slides(objects, 3)
    reader = CountingReader(LocalSourceReader(objects))
    client = source_client(tmp_path, objects, reader=reader)
    capture(client)
    reader.reads.clear()

    capture(client)

    assert reader.reads == []


def test_capture_notices_a_changed_generation(tmp_path):
    objects = tmp_path / "objects"
    write_object(
        objects, OBJECT_PREFIX + "subject_0001.jpeg", jpeg_bytes(), FIRST_GENERATION
    )
    client = source_client(tmp_path, objects)
    first = capture(client)

    replaced = write_object(
        objects,
        OBJECT_PREFIX + "subject_0001.jpeg",
        jpeg_bytes(colour="black"),
        SECOND_GENERATION,
    )
    second = capture(client)

    assert second["inventory_id"] != first["inventory_id"]
    assert listed(client)["items"][0]["generation"] == replaced


def test_capture_is_bounded(tmp_path, monkeypatch):
    from specimen_digitization.application import source_inventory

    monkeypatch.setattr(source_inventory, "MAX_INVENTORY_OBJECTS", 2)
    objects = tmp_path / "objects"
    slides(objects, 3)
    client = source_client(tmp_path, objects)

    response = client.post(
        PREFIX + f"/sources/{SOURCE_ID}/inventory", headers=HEADERS
    )

    assert response.status_code == 422, response.text
    assert client.get(
        PREFIX + f"/sources/{SOURCE_ID}/objects", headers=HEADERS
    ).status_code == 404


def test_capture_records_undecodable_objects_as_unsupported(tmp_path):
    objects = tmp_path / "objects"
    write_object(
        objects, OBJECT_PREFIX + "subject_0001.jpeg", jpeg_bytes(), FIRST_GENERATION
    )
    write_object(
        objects, OBJECT_PREFIX + "notes.txt", b"not an image at all", FIRST_GENERATION
    )
    client = source_client(tmp_path, objects)
    capture(client)

    rows = {row["object_name"]: row for row in listed(client)["items"]}

    assert rows[OBJECT_PREFIX + "notes.txt"]["state"] == "unsupported_media_type"
    assert rows[OBJECT_PREFIX + "subject_0001.jpeg"]["state"] == "available"


def test_capture_marks_media_the_source_does_not_permit(tmp_path):
    objects = tmp_path / "objects"
    write_object(
        objects, OBJECT_PREFIX + "subject_0001.png", png_bytes(), FIRST_GENERATION
    )
    client = source_client(tmp_path, objects)
    capture(client)

    row = listed(client)["items"][0]

    assert row["media_type"] == "image/png"
    assert row["state"] == "unsupported_media_type"


# Imported state resolves through the repository's existing checksum index.


def test_rows_show_what_is_already_in_the_queue(tmp_path):
    objects = tmp_path / "objects"
    slides(objects, 2)
    client = source_client(tmp_path, objects)
    capture(client)
    rows = listed(client)["items"]
    imported = import_objects(client, open_batch(client), rows[:1]).json()

    refreshed = {row["object_name"]: row for row in listed(client)["items"]}

    first = refreshed[rows[0]["object_name"]]
    assert first["state"] == "imported"
    assert first["specimen_id"] == imported["items"][0]["specimen_id"]
    assert refreshed[rows[1]["object_name"]]["state"] == "available"
    assert refreshed[rows[1]["object_name"]]["specimen_id"] is None


def test_imported_filter_separates_what_is_still_offerable(tmp_path):
    objects = tmp_path / "objects"
    slides(objects, 3)
    client = source_client(tmp_path, objects)
    capture(client)
    rows = listed(client)["items"]
    import_objects(client, open_batch(client), rows[:2])

    available = listed(client, imported="false")["items"]
    already = listed(client, imported="true")["items"]

    assert [row["object_name"] for row in available] == [rows[2]["object_name"]]
    assert [row["object_name"] for row in already] == [
        rows[0]["object_name"],
        rows[1]["object_name"],
    ]


# Paging, matching the GET /specimens discipline.


def test_objects_page_with_cursor_and_limit(tmp_path):
    objects = tmp_path / "objects"
    slides(objects, 5)
    client = source_client(tmp_path, objects)
    capture(client)

    seen, cursor, pages = [], None, 0
    while True:
        params = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        body = listed(client, **params)
        pages += 1
        seen.extend(row["object_name"] for row in body["items"])
        cursor = body["next_cursor"]
        if not cursor:
            break
        assert pages < 10

    assert seen == [
        OBJECT_PREFIX + f"subject_{ordinal:04d}.jpeg" for ordinal in range(1, 6)
    ]
    assert len(seen) == len(set(seen))


def test_a_cursor_is_refused_after_a_new_snapshot(tmp_path):
    objects = tmp_path / "objects"
    slides(objects, 4)
    client = source_client(tmp_path, objects)
    capture(client)
    cursor = listed(client, limit=2)["next_cursor"]
    assert cursor
    write_object(
        objects, OBJECT_PREFIX + "subject_0005.jpeg", jpeg_bytes(), FIRST_GENERATION
    )
    capture(client)

    response = client.get(
        PREFIX + f"/sources/{SOURCE_ID}/objects",
        headers=HEADERS,
        params={"cursor": cursor, "limit": 2},
    )

    assert response.status_code == 422, response.text


def test_a_cursor_is_refused_when_the_filters_change(tmp_path):
    objects = tmp_path / "objects"
    slides(objects, 4)
    client = source_client(tmp_path, objects)
    capture(client)
    cursor = listed(client, limit=2)["next_cursor"]

    response = client.get(
        PREFIX + f"/sources/{SOURCE_ID}/objects",
        headers=HEADERS,
        params={"cursor": cursor, "limit": 2, "imported": "false"},
    )

    assert response.status_code == 422, response.text


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"limit": -1}])
def test_listing_limits_are_bounded(tmp_path, params):
    objects = tmp_path / "objects"
    slides(objects, 2)
    client = source_client(tmp_path, objects)
    capture(client)

    response = client.get(
        PREFIX + f"/sources/{SOURCE_ID}/objects", headers=HEADERS, params=params
    )

    assert response.status_code == 422, response.text


def test_unknown_filters_are_refused(tmp_path):
    objects = tmp_path / "objects"
    slides(objects, 2)
    client = source_client(tmp_path, objects)
    capture(client)

    response = client.get(
        PREFIX + f"/sources/{SOURCE_ID}/objects",
        headers=HEADERS,
        params={"object_name": OBJECT_PREFIX + "subject_0001.jpeg"},
    )

    assert response.status_code == 422, response.text


def test_a_cursor_from_another_source_is_refused(tmp_path):
    other_id = "00000000-0000-4000-8000-0000000000f2"
    objects = tmp_path / "objects"
    slides(objects, 4)
    write_object(objects, "other/subject_0001.jpeg", jpeg_bytes(), FIRST_GENERATION)
    client = source_client(
        tmp_path,
        objects,
        sources=[registered(), registered(source_id=other_id, prefix="other/")],
    )
    capture(client)
    capture(client, source_id=other_id)
    cursor = listed(client, limit=2)["next_cursor"]

    response = client.get(
        PREFIX + f"/sources/{other_id}/objects",
        headers=HEADERS,
        params={"cursor": cursor, "limit": 2},
    )

    assert response.status_code == 422, response.text


def test_inventory_survives_a_restart(tmp_path):
    objects = tmp_path / "objects"
    slides(objects, 2)
    client = source_client(tmp_path, objects)
    first = capture(client)

    restarted = source_client(tmp_path, objects)

    body = listed(restarted)
    assert body["inventory_id"] == first["inventory_id"]
    assert body["object_count"] == 2
