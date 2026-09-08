"""Real process races exercise immutable publication, not timing-based retries."""

import hashlib
import multiprocessing
import os
import time
from pathlib import Path

import pytest

from specimen_digitization.application.storage import Conflict, LocalBlobs, Missing


def publish_many(root, barrier, count):
    blobs = LocalBlobs(Path(root))
    for index in range(count):
        data = bytes([index]) * (256 * 1024)
        barrier.wait(timeout=20)
        assert blobs.get(blobs.put(data)) == data


def pause_before_publication(root, ready):
    original = os.link

    def blocked_link(source, destination):
        ready.set()
        time.sleep(60)
        return original(source, destination)

    os.link = blocked_link
    LocalBlobs(Path(root)).put(b"synthetic crash publication" * 10000)


def test_two_process_publications_never_expose_partial_objects(tmp_path):
    ctx = multiprocessing.get_context("spawn")
    barrier = ctx.Barrier(2)
    workers = [
        ctx.Process(target=publish_many, args=(str(tmp_path), barrier, 40))
        for _ in range(2)
    ]
    for worker in workers:
        worker.start()
    checks = 0
    deadline = time.monotonic() + 45
    try:
        while any(worker.is_alive() for worker in workers):
            assert time.monotonic() < deadline
            for path in tmp_path.iterdir():
                if len(path.name) == 64:
                    assert hashlib.sha256(path.read_bytes()).hexdigest() == path.name
                    checks += 1
        for worker in workers:
            worker.join(timeout=2)
            assert worker.exitcode == 0
        assert checks > 0
        assert len(list(tmp_path.iterdir())) == 40
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.kill()
            worker.join(timeout=3)


def test_crashed_unpublished_temp_is_not_addressable_and_does_not_block_retry(tmp_path):
    ctx = multiprocessing.get_context("spawn")
    ready = ctx.Event()
    worker = ctx.Process(target=pause_before_publication, args=(str(tmp_path), ready))
    worker.start()
    try:
        assert ready.wait(timeout=15)
        assert not [path for path in tmp_path.iterdir() if len(path.name) == 64]
        worker.kill()
        worker.join(timeout=3)
        stale = list(tmp_path.iterdir())
        assert len(stale) == 1 and stale[0].name.startswith(".blob-")
        blobs = LocalBlobs(tmp_path)
        with pytest.raises(Missing):
            blobs.get(stale[0].name)
        data = b"synthetic crash publication" * 10000
        assert blobs.get(blobs.put(data)) == data
        assert stale[0].exists()  # Another process never deletes an unowned temp.
    finally:
        if worker.is_alive():
            worker.kill()
        worker.join(timeout=3)


def test_failed_write_cleans_owned_temp_and_existing_corruption_fails_closed(
    tmp_path, monkeypatch
):
    blobs = LocalBlobs(tmp_path)
    original = os.fsync
    monkeypatch.setattr(
        os, "fsync", lambda _: (_ for _ in ()).throw(OSError("synthetic fsync failure"))
    )
    with pytest.raises(OSError):
        blobs.put(b"data")
    assert not list(tmp_path.iterdir())
    monkeypatch.setattr(os, "fsync", original)
    ref = blobs.put(b"data")
    (tmp_path / ref).write_bytes(b"bad")
    with pytest.raises(Conflict):
        blobs.put(b"data")
    assert (tmp_path / ref).read_bytes() == b"bad"
    assert not list(tmp_path.glob(".blob-*"))


def test_gcs_publication_uses_create_only_precondition_and_checks_existing_bytes():
    from unittest.mock import Mock
    from google.api_core.exceptions import PreconditionFailed
    from specimen_digitization.application.production import GcsBlobs
    from specimen_digitization.application.storage import Conflict

    blobs = GcsBlobs.__new__(GcsBlobs)
    blob = Mock(generation=17)
    blobs.bucket = Mock()
    blobs.bucket.blob.return_value = blob
    blob.upload_from_string.side_effect = PreconditionFailed("already published")
    blob.download_as_bytes.return_value = b"synthetic object"
    expected = hashlib.sha256(b"synthetic object").hexdigest()
    assert blobs.put(b"synthetic object") == expected + ":17"
    blob.upload_from_string.assert_called_once_with(
        b"synthetic object", if_generation_match=0, checksum="crc32c"
    )
    blob.download_as_bytes.return_value = b"different bytes"
    with pytest.raises(Conflict):
        blobs.put(b"synthetic object")
