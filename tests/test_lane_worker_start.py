"""Starting the worker and importing from Storage in production (LANE.md, T1)."""

import json
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from specimen_digitization.application import cli, runtime_config
from specimen_digitization.application.api import (
    SYNTHETIC_COLLECTION,
    SYNTHETIC_ORG,
    SYNTHETIC_TEXT,
    create_app,
)
from specimen_digitization.application.lane_dispatch import CloudRunJobDispatcher
from specimen_digitization.application.source_reader import (
    LocalSourceReader,
    SourceObjectChanged,
)
from specimen_digitization.application.source_registry import SourceRegistry
from specimen_digitization.application.storage import LocalBlobs, SQLiteRepository
from specimen_digitization.application.workflow import SyntheticAdapters

import source_fixtures
from test_api_runtime import config_env
from test_lane_trigger import SCOPE, RecordingDispatcher, due_ids, registry, stored

JOB = "projects/specimen-digitization/locations/us-east4/jobs/specimen-worker"
SOURCE = {
    "source_id": "00000000-0000-4000-8000-0000000000f1",
    "collection_id": "00000000-0000-4000-8000-0000000000c1",
    "bucket": "specimen-digitization.firebasestorage.app",
    "prefix": "microscopic-slides/",
    "media_types": ["image/jpeg"],
    "registered_by": "release-owner",
    "registered_at": "2026-09-23T00:00:00+00:00",
}


def lane_config(**env):
    return runtime_config.RuntimeConfig.from_env(dict(config_env(), **env))


def test_lane_configuration_is_optional():
    config = lane_config()
    assert config.worker_job is None
    assert config.sources == ()
    assert lane_config(SPECIMEN_SOURCE_REGISTRY_JSON="[]").sources == ()


def test_lane_configuration_parses_the_job_and_the_sources():
    config = lane_config(
        SPECIMEN_WORKER_JOB=JOB, SPECIMEN_SOURCE_REGISTRY_JSON=json.dumps([SOURCE])
    )
    assert config.worker_job == JOB
    assert [source.source_id for source in config.sources] == [SOURCE["source_id"]]
    assert config.sources[0].prefix == "microscopic-slides/"


@pytest.mark.parametrize(
    "key,value",
    [
        ("SPECIMEN_WORKER_JOB", "specimen-worker"),
        ("SPECIMEN_WORKER_JOB", JOB.replace("specimen-digitization", "other-project")),
        ("SPECIMEN_WORKER_JOB", JOB + ":run"),
        ("SPECIMEN_SOURCE_REGISTRY_JSON", "not json"),
        ("SPECIMEN_SOURCE_REGISTRY_JSON", json.dumps(SOURCE)),
        ("SPECIMEN_SOURCE_REGISTRY_JSON", json.dumps([dict(SOURCE, bucket="other-bucket")])),
        ("SPECIMEN_SOURCE_REGISTRY_JSON", json.dumps([dict(SOURCE, prefix="microscopic-slides")])),
        ("SPECIMEN_SOURCE_REGISTRY_JSON", json.dumps([dict(SOURCE, extra=True)])),
        ("SPECIMEN_SOURCE_REGISTRY_JSON", json.dumps([SOURCE, SOURCE])),
    ],
)
def test_lane_configuration_denials(key, value):
    with pytest.raises(ValueError):
        lane_config(**{key: value})


@pytest.mark.parametrize("invalid_field", ["source_id", "prefix", "private_note"])
def test_runtime_startup_conceals_invalid_private_registry_values(
    monkeypatch, invalid_field
):
    import firebase_admin

    canary = "private-source-value-for-test"
    source = dict(SOURCE, **{invalid_field: canary})
    for key, value in dict(
        config_env(), SPECIMEN_SOURCE_REGISTRY_JSON=json.dumps([source])
    ).items():
        monkeypatch.setenv(key, value)

    def no_native_startup(*args, **kwargs):
        pytest.fail("Invalid registry configuration must refuse before native startup")

    monkeypatch.setattr(firebase_admin, "get_app", no_native_startup)
    monkeypatch.setattr(firebase_admin, "initialize_app", no_native_startup)
    monkeypatch.setattr(cli, "GcsBlobs", no_native_startup)
    monkeypatch.setattr(cli, "SqlConnectRepository", no_native_startup)
    with pytest.raises(ValueError) as error:
        cli.production_app()

    rendered = "".join(traceback.format_exception(error.value))
    assert str(error.value) == (
        "SPECIMEN_SOURCE_REGISTRY_JSON contains invalid registered sources"
    )
    assert canary not in rendered
    assert error.value.__suppress_context__


def test_lane_wiring_builds_the_registry_reader_and_dispatcher(monkeypatch):
    readers = []
    monkeypatch.setattr(
        cli,
        "GcsSourceReader",
        lambda **kwargs: readers.append(kwargs) or SimpleNamespace(kind="gcs"),
    )
    wired = cli.lane_wiring(
        lane_config(
            SPECIMEN_WORKER_JOB=JOB, SPECIMEN_SOURCE_REGISTRY_JSON=json.dumps([SOURCE])
        )
    )
    assert isinstance(wired["source_registry"], SourceRegistry)
    assert [s.source_id for s in wired["source_registry"].for_collections(
        {SOURCE["collection_id"]}
    )] == [SOURCE["source_id"]]
    assert wired["source_reader"].kind == "gcs"
    assert readers == [{"project": "specimen-digitization"}]
    assert isinstance(wired["worker_dispatcher"], CloudRunJobDispatcher)
    assert wired["worker_dispatcher"].job == JOB


def test_lane_wiring_without_configuration_is_today_s_behaviour(monkeypatch):
    monkeypatch.setattr(
        cli, "GcsSourceReader", lambda **_: pytest.fail("No source was configured")
    )
    wired = cli.lane_wiring(lane_config())
    assert not wired["source_registry"]
    assert wired["source_reader"] is None
    assert wired["worker_dispatcher"] is None


def test_production_app_passes_the_lane_wiring(monkeypatch):
    import firebase_admin

    from specimen_digitization.application import runtime_auth, runtime_health

    config = lane_config(SPECIMEN_WORKER_JOB=JOB)
    captured = {}
    monkeypatch.setattr(runtime_config, "build_provenance", lambda required: {})
    monkeypatch.setattr(
        firebase_admin,
        "get_app",
        lambda name: SimpleNamespace(
            project_id=config.project_number
            if name == "specimen-api-app-check"
            else config.project
        ),
    )
    monkeypatch.setattr(runtime_auth, "firebase_verifier", lambda *_: None)
    monkeypatch.setattr(runtime_health, "install_health", lambda *_, **__: None)
    monkeypatch.setattr(runtime_health, "cloud_probe", lambda *_: None)
    monkeypatch.setattr(runtime_health, "DependencyReadiness", lambda *_: None)
    monkeypatch.setattr(cli, "GcsBlobs", lambda **_: object())
    monkeypatch.setattr(
        cli,
        "SqlConnectRepository",
        lambda **_: SimpleNamespace(memberships=lambda user: []),
    )
    monkeypatch.setattr(cli, "ProductionAdapters", lambda blobs: object())
    monkeypatch.setattr(
        cli, "create_app", lambda **kwargs: captured.update(kwargs) or object()
    )
    cli.production_app(config)
    assert captured["mode"] == "production"
    assert isinstance(captured["worker_dispatcher"], CloudRunJobDispatcher)
    assert not captured["source_registry"]
    assert captured["source_reader"] is None


def test_source_import_is_intake_and_queues_each_new_specimen(tmp_path):
    objects = tmp_path / "objects"
    for index, colour in enumerate(("white", "black")):
        source_fixtures.write_object(
            objects,
            f"{source_fixtures.OBJECT_PREFIX}subject_{index}.jpg",
            source_fixtures.jpeg_bytes(colour),
            source_fixtures.FIRST_GENERATION,
        )
    dispatcher = RecordingDispatcher()
    blobs = LocalBlobs(tmp_path / "blobs")
    app = create_app(
        mode="emulator",
        repository=SQLiteRepository(tmp_path / "state.sqlite3"),
        blobs=blobs,
        adapters=SyntheticAdapters(blobs, SYNTHETIC_TEXT),
        identity_verifier=lambda token, check: "lane-reviewer",
        memberships=lambda user: [
            {
                "organization_id": SYNTHETIC_ORG,
                "collection_id": SYNTHETIC_COLLECTION,
                "role": "reviewer",
                "can_view_sensitive": True,
            }
        ],
        profile_registry=registry(),
        worker_dispatcher=dispatcher,
        source_registry=SourceRegistry([source_fixtures.registered()]),
        source_reader=LocalSourceReader(objects),
    )
    c = TestClient(app, raise_server_exceptions=False)
    source_fixtures.capture(c)
    rows = source_fixtures.listed(c)["items"]
    batch = source_fixtures.open_batch(c, sensitive=False)
    imported = source_fixtures.import_objects(c, batch, rows, sensitive=False)
    assert imported.status_code == 200, imported.text
    assert imported.json()["imported"] == 2
    assert dispatcher.calls == 1
    ids = [item["specimen_id"] for item in imported.json()["items"]]
    assert sorted(due_ids(tmp_path)) == sorted(ids)
    for ident in ids:
        run = stored(tmp_path, ident).run
        assert run.stage == "pending"
        assert run.profile.execution.approved_cost_limit_micros == 250_000
        assert run.classification_selection["collection_id"] == SYNTHETIC_COLLECTION
    again = source_fixtures.import_objects(c, batch, rows, sensitive=False)
    assert again.json()["duplicates"] == 2
    assert dispatcher.calls == 1


@pytest.mark.parametrize(
    "sensitive,processing,blocker",
    [
        (True, True, "sensitive_record_not_processed"),
        (False, False, "collection_processing_unconfigured"),
    ],
)
def test_blocked_source_intake_retains_record_without_starting_worker(
    tmp_path, sensitive, processing, blocker
):
    objects = tmp_path / "objects"
    source_fixtures.write_object(
        objects,
        f"{source_fixtures.OBJECT_PREFIX}subject.jpg",
        source_fixtures.jpeg_bytes(),
        source_fixtures.FIRST_GENERATION,
    )
    dispatcher = RecordingDispatcher()
    blobs = LocalBlobs(tmp_path / "blobs")
    app = create_app(
        mode="emulator",
        repository=SQLiteRepository(tmp_path / "state.sqlite3"),
        blobs=blobs,
        adapters=SyntheticAdapters(blobs, SYNTHETIC_TEXT),
        identity_verifier=lambda token, check: "lane-reviewer",
        memberships=lambda user: [
            {
                "organization_id": SYNTHETIC_ORG,
                "collection_id": SYNTHETIC_COLLECTION,
                "role": "reviewer",
                "can_view_sensitive": True,
            }
        ],
        profile_registry=registry(processing=processing),
        worker_dispatcher=dispatcher,
        source_registry=SourceRegistry([source_fixtures.registered()]),
        source_reader=LocalSourceReader(objects),
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        source_fixtures.capture(client)
        rows = source_fixtures.listed(client)["items"]
        batch = source_fixtures.open_batch(client, sensitive=sensitive)
        imported = source_fixtures.import_objects(
            client, batch, rows, sensitive=sensitive
        )
        assert imported.status_code == 200, imported.text
        assert imported.json()["imported"] == 1
        ident = imported.json()["items"][0]["specimen_id"]
        run = stored(tmp_path, ident).run
        assert run.stage == "processing_blocked"
        assert run.blocker == blocker
        assert due_ids(tmp_path) == []
        assert dispatcher.calls == 0

        again = source_fixtures.import_objects(
            client, batch, rows, sensitive=sensitive
        )
        assert again.status_code == 200, again.text
        assert again.json()["imported"] == 0
        assert again.json()["duplicates"] == 1
        assert dispatcher.calls == 0


@pytest.mark.parametrize(
    "sensitive,processing,fail_index,expected_calls",
    [
        (False, True, 1, 1),
        (True, True, 1, 0),
        (False, False, 1, 0),
        (False, True, 0, 0),
    ],
)
def test_partial_source_import_starts_only_retained_pending_work(
    tmp_path, sensitive, processing, fail_index, expected_calls
):
    class RacedReader(LocalSourceReader):
        fail_on = None

        def read(self, bucket, object_name, generation):
            if object_name == self.fail_on:
                raise SourceObjectChanged("Synthetic generation race")
            return super().read(bucket, object_name, generation)

    objects = tmp_path / "objects"
    for index, colour in enumerate(("white", "black")):
        source_fixtures.write_object(
            objects,
            f"{source_fixtures.OBJECT_PREFIX}subject_{index}.jpg",
            source_fixtures.jpeg_bytes(colour),
            source_fixtures.FIRST_GENERATION,
        )
    reader = RacedReader(objects)
    dispatcher = RecordingDispatcher()
    repository = SQLiteRepository(tmp_path / "state.sqlite3")
    blobs = LocalBlobs(tmp_path / "blobs")
    app = create_app(
        mode="emulator",
        repository=repository,
        blobs=blobs,
        adapters=SyntheticAdapters(blobs, SYNTHETIC_TEXT),
        identity_verifier=lambda token, check: "lane-reviewer",
        memberships=lambda user: [
            {
                "organization_id": SYNTHETIC_ORG,
                "collection_id": SYNTHETIC_COLLECTION,
                "role": "reviewer",
                "can_view_sensitive": True,
            }
        ],
        profile_registry=registry(processing=processing),
        worker_dispatcher=dispatcher,
        source_registry=SourceRegistry([source_fixtures.registered()]),
        source_reader=reader,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        source_fixtures.capture(client)
        rows = source_fixtures.listed(client)["items"]
        batch = source_fixtures.open_batch(client, sensitive=sensitive)
        reader.fail_on = rows[fail_index]["object_name"]
        response = source_fixtures.import_objects(
            client, batch, rows, sensitive=sensitive
        )
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "source_object_changed"
        retained = repository.list(SCOPE)
        assert len(retained) == fail_index
        for specimen in retained:
            assert specimen.run.stage == (
                "pending" if processing and not sensitive else "processing_blocked"
            )
        assert len(due_ids(tmp_path)) == expected_calls
        assert dispatcher.calls == expected_calls


def test_concurrent_source_import_replay_requests_one_worker(tmp_path):
    barrier = threading.Barrier(2)

    class RacedRepository(SQLiteRepository):
        armed = False
        prechecks = []

        def find_checksum(self, scope, checksum, include_sensitive=False):
            matches = super().find_checksum(scope, checksum, include_sensitive)
            if self.armed and not matches:
                self.prechecks.append(len(matches))
                barrier.wait(timeout=10)
            return matches

    objects = tmp_path / "objects"
    source_fixtures.write_object(
        objects,
        f"{source_fixtures.OBJECT_PREFIX}subject.jpg",
        source_fixtures.jpeg_bytes(),
        source_fixtures.FIRST_GENERATION,
    )
    repository = RacedRepository(tmp_path / "state.sqlite3")
    dispatcher = RecordingDispatcher()
    blobs = LocalBlobs(tmp_path / "blobs")
    app = create_app(
        mode="emulator",
        repository=repository,
        blobs=blobs,
        adapters=SyntheticAdapters(blobs, SYNTHETIC_TEXT),
        identity_verifier=lambda token, check: "lane-reviewer",
        memberships=lambda user: [
            {
                "organization_id": SYNTHETIC_ORG,
                "collection_id": SYNTHETIC_COLLECTION,
                "role": "reviewer",
                "can_view_sensitive": True,
            }
        ],
        profile_registry=registry(),
        worker_dispatcher=dispatcher,
        source_registry=SourceRegistry([source_fixtures.registered()]),
        source_reader=LocalSourceReader(objects),
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        source_fixtures.capture(client)
        rows = source_fixtures.listed(client)["items"]
        batch = source_fixtures.open_batch(client, sensitive=False)
        repository.armed = True
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(
                    source_fixtures.import_objects,
                    client, batch, rows, sensitive=False,
                )
                for _ in range(2)
            ]
            responses = [future.result(timeout=15) for future in futures]
        repository.armed = False
        assert repository.prechecks == [0, 0]
        assert [response.status_code for response in responses] == [200, 200]
        assert len(repository.list(SCOPE)) == 1
        assert len(due_ids(tmp_path)) == 1
        with repository.connect() as db:
            receipts = db.execute(
                "SELECT count(*) FROM receipts WHERE key LIKE 'source:%'"
            ).fetchone()[0]
        assert receipts == 1
        assert dispatcher.calls == 1
        assert sorted(
            (response.json()["imported"], response.json()["duplicates"])
            for response in responses
        ) == [(0, 1), (1, 0)]

        again = source_fixtures.import_objects(
            client, batch, rows, sensitive=False
        )
        assert again.status_code == 200, again.text
        assert again.json()["imported"] == 0
        assert again.json()["duplicates"] == 1
        assert dispatcher.calls == 1
