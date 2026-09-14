"""The generation precondition, at both source adapters.

`GcsSourceReader.read` sends `ifGenerationMatch`, not `generation`. The
difference is the whole guarantee: `generation` would return that version's
bytes even after the live object moved on, which proves the bytes are authentic
but not that the object is unchanged. `ifGenerationMatch` refuses with 412 the
moment the live object is a different generation, which is the claim an import
actually rests on.
"""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
import requests

from specimen_digitization.application.blob_limits import BlobTooLarge
from specimen_digitization.application.source_reader import (
    GcsSourceReader,
    LocalSourceReader,
    SourceObjectChanged,
    SourceUnavailable,
    sniff_media_type,
    valid_generation,
)
from specimen_digitization.application.storage import Missing

from source_fixtures import BUCKET, FIRST_GENERATION, jpeg_bytes, png_bytes


def gcs_reader(state):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state["queries"].append(parse_qs(urlparse(self.path).query))
            self.send_response(state["status"])
            self.end_headers()
            try:
                self.wfile.write(state["body"])
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    class LocalTransport:
        def get(self, url, **kwargs):
            assert url.startswith("https://storage.googleapis.com/storage/v1/b/")
            return requests.get(
                f"http://127.0.0.1:{server.server_port}/object", **kwargs
            )

    reader = GcsSourceReader.__new__(GcsSourceReader)
    reader.client = SimpleNamespace(_http=LocalTransport())
    return reader, server, thread


def test_cloud_read_binds_the_current_generation_not_a_past_one():
    state = {"body": b"slide bytes", "status": 200, "queries": []}
    reader, server, thread = gcs_reader(state)
    try:
        assert reader.read(BUCKET, "microscopic-slides/subject_1.jpeg", "17") == (
            b"slide bytes"
        )
        query = state["queries"][-1]
        assert query["ifGenerationMatch"] == ["17"]
        assert "generation" not in query

        # 412 is what Cloud Storage answers when the live object has moved on.
        state["status"] = 412
        with pytest.raises(SourceObjectChanged):
            reader.read(BUCKET, "microscopic-slides/subject_1.jpeg", "17")

        state["status"] = 404
        with pytest.raises(Missing):
            reader.read(BUCKET, "microscopic-slides/subject_1.jpeg", "17")

        state["status"] = 503
        with pytest.raises(SourceUnavailable):
            reader.read(BUCKET, "microscopic-slides/subject_1.jpeg", "17")
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_cloud_read_stays_inside_the_intake_byte_limit():
    state = {"body": b"x" * 4096, "status": 200, "queries": []}
    reader, server, thread = gcs_reader(state)
    try:
        from specimen_digitization.application import source_reader

        original = source_reader.ORIGINAL_BYTES
        source_reader.ORIGINAL_BYTES = 100
        try:
            with pytest.raises(BlobTooLarge):
                reader.read(BUCKET, "microscopic-slides/subject_1.jpeg", "17")
        finally:
            source_reader.ORIGINAL_BYTES = original
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize("generation", ["0", "", "latest", "-1", "1.0", None, 17])
def test_a_generation_is_a_positive_integer(generation):
    with pytest.raises(ValueError):
        valid_generation(generation)


def test_local_read_refuses_bytes_rewritten_under_it(tmp_path):
    reader = LocalSourceReader(tmp_path)
    path = tmp_path / BUCKET / "microscopic-slides" / "subject_1.jpeg"
    path.parent.mkdir(parents=True)
    path.write_bytes(jpeg_bytes())
    import os

    os.utime(path, ns=(FIRST_GENERATION, FIRST_GENERATION))
    name = "microscopic-slides/subject_1.jpeg"

    assert reader.read(BUCKET, name, str(FIRST_GENERATION)) == jpeg_bytes()

    path.write_bytes(jpeg_bytes(colour="black"))
    os.utime(path, ns=(FIRST_GENERATION + 10**9, FIRST_GENERATION + 10**9))
    with pytest.raises(SourceObjectChanged):
        reader.read(BUCKET, name, str(FIRST_GENERATION))


@pytest.mark.parametrize(
    "name",
    ["../escape.jpeg", "microscopic-slides/../../escape.jpeg", "./slide.jpeg", ""],
)
def test_local_read_cannot_leave_its_bucket(tmp_path, name):
    (tmp_path / "escape.jpeg").write_bytes(jpeg_bytes())
    reader = LocalSourceReader(tmp_path)

    with pytest.raises((Missing, ValueError)):
        reader.read(BUCKET, name, str(FIRST_GENERATION))


def test_local_reader_reports_an_absent_object(tmp_path):
    reader = LocalSourceReader(tmp_path)

    with pytest.raises(Missing):
        reader.current_generation(BUCKET, "microscopic-slides/absent.jpeg")


def test_media_type_comes_from_the_bytes():
    assert sniff_media_type(jpeg_bytes()) == "image/jpeg"
    assert sniff_media_type(png_bytes()) == "image/png"
    assert sniff_media_type(b"not an image") == "application/octet-stream"
    assert sniff_media_type(b"") == "application/octet-stream"
