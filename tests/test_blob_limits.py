"""Bounded local and generation-pinned streaming object reads."""

import hashlib
import io
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest
import requests

from specimen_digitization.application.blob_limits import BlobTooLarge, read_limited
from specimen_digitization.application.storage import LocalBlobs, Conflict
from specimen_digitization.application.production import GcsBlobs


def test_reader_consumes_only_cap_plus_one_and_local_digest(tmp_path):
    source = io.BytesIO(b"x" * 10000)
    with pytest.raises(BlobTooLarge):
        read_limited(source.read, 100)
    assert source.tell() == 101
    blobs = LocalBlobs(tmp_path)
    ref = blobs.put(b"complete")
    assert blobs.get_bounded(ref, 8) == b"complete"
    with pytest.raises(BlobTooLarge):
        blobs.get_bounded(ref, 7)
    (tmp_path / ref).write_bytes(b"tampered")
    with pytest.raises(Conflict):
        blobs.get_bounded(ref, 8)


def test_gcs_generation_stream_bounds_overshoot_cleanup_and_integrity():
    state = {"body": b"complete", "declared": None, "paths": []}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state["paths"].append(self.path)
            self.send_response(200)
            if state["declared"] is not None:
                self.send_header("Content-Length", str(state["declared"]))
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
    responses = []

    class LocalTransport:
        def get(self, url, **kwargs):
            assert kwargs["stream"] is True and kwargs["allow_redirects"] is False
            assert url.startswith("https://storage.googleapis.com/storage/v1/b/")
            response = requests.get(
                f"http://127.0.0.1:{server.server_port}/object", **kwargs
            )
            responses.append(response)
            return response

    blobs = GcsBlobs.__new__(GcsBlobs)
    blobs.bucket = SimpleNamespace(
        name="synthetic-bucket", client=SimpleNamespace(_http=LocalTransport())
    )
    ref = hashlib.sha256(b"complete").hexdigest() + ":12345"
    try:
        assert blobs.get_bounded(ref, 8) == b"complete"
        assert "generation=12345" in state["paths"][-1]
        state["body"] = b"x" * 100000
        with pytest.raises(BlobTooLarge):
            blobs.get_bounded(ref, 100)
        state["declared"] = 100000
        with pytest.raises(BlobTooLarge):
            blobs.get_bounded(ref, 100)
        state["declared"] = None
        state["body"] = b"tampered"
        with pytest.raises(Conflict):
            blobs.get_bounded(ref, 100)
        assert all(response.raw.closed for response in responses)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
