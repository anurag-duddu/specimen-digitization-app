"""Actual TCP slow headers/drips and bounded production-adapter response capture."""

import hashlib
import socket
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from test_authority_registry import loopback_server

from specimen_digitization.application.http_effect import bounded_http
from specimen_digitization.application.storage import LocalBlobs


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            try:
                if self.server.stop_event.is_set():
                    return
                if self.path.startswith("/headers"):
                    if self.server.stop_event.wait(5):
                        return
                self.send_response(200)
                if self.path.startswith("/encoding"):
                    self.send_header("Content-Encoding", "gzip")
                self.end_headers()
                if self.path.startswith("/drip"):
                    for _ in range(100):
                        self.wfile.write(b"x")
                        self.wfile.flush()
                        if self.server.stop_event.wait(0.05):
                            return
                elif self.path.startswith("/large"):
                    self.wfile.write(b"z" * 65536)
                else:
                    self.wfile.write(b'{"diagnostics":{"matchType":"NONE"}}')
            except (BrokenPipeError, ConnectionResetError):
                pass

    with loopback_server(Handler, ThreadingHTTPServer) as service:
        yield "http://127.0.0.1:" + str(service.server_port)


@pytest.mark.parametrize("path", ["/headers", "/drip"])
def test_entire_http_call_is_bounded_and_child_is_reaped(server, path):
    started = time.monotonic()
    value = bounded_http(server + path, timeout_seconds=2, max_bytes=1024)
    assert value["failure"] == "timeout" and value["status_code"] is None
    assert value["cleanup_complete"] and value["body"] == b""
    assert time.monotonic() - started < 5.5
    if value["worker_pid"]:
        with pytest.raises(ProcessLookupError):
            os.kill(value["worker_pid"], 0)


@pytest.mark.parametrize(
    "path,truncated,encoding",
    [("/ok", False, False), ("/large", True, False), ("/encoding", False, True)],
)
def test_raw_response_cap_and_encoding_are_explicit(server, path, truncated, encoding):
    value = bounded_http(server + path, timeout_seconds=4, max_bytes=1024)
    assert value["failure"] is None
    assert value["truncated"] == truncated and value["unsupported_encoding"] == encoding
    assert len(value["body"]) <= 1024 and value["cleanup_complete"]


def test_default_gbif_and_authority_paths_use_bounded_tcp_transport(
    server, tmp_path, monkeypatch
):
    from specimen_digitization.application import http_effect
    from specimen_digitization.application.authority_registry import (
        AuthoritySource,
        read_authority,
    )
    from specimen_digitization.application.lookup import GbifTaxonomy
    from specimen_digitization.application.domain import LookupStatus

    endpoint = "/ok"
    original = bounded_http
    monkeypatch.setattr(
        http_effect,
        "bounded_http",
        lambda url, **kwargs: original(server + endpoint, **kwargs),
    )
    blobs = LocalBlobs(tmp_path)
    lookup = GbifTaxonomy(blobs)
    assert lookup.client is None
    good = lookup.lookup("Synthetic name")
    assert good.status == LookupStatus.NO_MATCH
    assert hashlib.sha256(blobs.get(good.raw_ref)).hexdigest() == good.digest
    endpoint = "/large"
    source = AuthoritySource(
        source_id="synthetic",
        version="1",
        endpoint="https://synthetic.invalid/source",
        operations=("lookup",),
        scopes=(("org", "collection"),),
        classifications=("public",),
        approved=True,
        max_response_bytes=1024,
        timeout_seconds=4,
    )
    captured = read_authority(source, blobs, None)
    assert captured.status == LookupStatus.MALFORMED and captured.truncated
    assert len(blobs.get(captured.raw_ref)) == 1024
    assert hashlib.sha256(captured.body).hexdigest() == captured.response_sha256


@pytest.mark.parametrize("path", ["/headers", "/drip", "/partial"])
def test_server_teardown_releases_blocked_handlers(monkeypatch, path):
    # Observe only resources accepted/started by this fixture, never unrelated
    # process threads or sockets. Keep the peer open through teardown.
    handlers, connections = [], []
    entered = threading.Event()
    original = ThreadingHTTPServer

    class ObservedServer(original):
        def get_request(self):
            connection, address = super().get_request()
            connections.append(connection)
            return connection, address

        def process_request_thread(self, request, client_address):
            handlers.append(threading.current_thread())
            entered.set()
            super().process_request_thread(request, client_address)

    monkeypatch.setitem(globals(), "ThreadingHTTPServer", ObservedServer)
    running = server.__wrapped__()
    try:
        url = next(running)
        with socket.create_connection(("127.0.0.1", int(url.rsplit(":", 1)[1]))) as peer:
            request = (b"GET /headers HTTP/1.0\r\n" if path == "/partial" else
                       f"GET {path} HTTP/1.0\r\n\r\n".encode())
            peer.sendall(request)
            assert entered.wait(2), "fixture did not start its owned handler"
            if path == "/drip":
                peer.settimeout(2)
                received = b""
                while b"\r\n\r\nx" not in received:
                    chunk = peer.recv(4096)
                    assert chunk, "drip handler closed before sending its first byte"
                    received += chunk
            # Close the fixture while the peer remains connected.
            active = handlers[:]
            # Explicit generator close exercises exceptional fixture exit too.
            # Keep peer alive by closing the generator within this scope.
            running.close()
            assert all(not thread.is_alive() for thread in active), (
                "fixture teardown left an owned blocked handler alive"
            )
            assert all(connection.fileno() == -1 for connection in connections), (
                "fixture teardown left an accepted socket open"
            )
            if path != "/drip":
                peer.settimeout(2)
                assert peer.recv(4096) == b"", (
                    "teardown completed a delayed response instead of cancelling it"
                )
    finally:
        running.close()
        for thread in handlers:
            thread.join(timeout=6)
