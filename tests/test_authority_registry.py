import hashlib
from contextlib import ExitStack, contextmanager
import threading
import selectors
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
from pydantic import ValidationError

from specimen_digitization.application.authority_registry import (
    AuthorityQuery,
    AuthorityRegistry,
    AuthoritySource,
    PartiesIdentity,
)


class Blobs:
    def __init__(self):
        self.values = {}

    def put(self, content):
        key = hashlib.sha256(content).hexdigest()
        self.values[key] = content
        return key


def query(**changes):
    return AuthorityQuery(
        organization_id="synthetic",
        collection_id="insects",
        data_classification="public",
        literal="Illinois",
        evidence_ids=("pixel-evidence-1",),
        **changes,
    )


def source(parties=False, **changes):
    values = dict(
        source_id="parties" if parties else "example_places",
        version="synthetic-source-v1",
        endpoint="https://museum.example/fmnh/eparties"
        if parties
        else "https://places.example/search",
        operations=("eparties_search",) if parties else ("place_search",),
        scopes=(("synthetic", "insects"),),
        classifications=("public",),
        approved=True,
    )
    values.update(changes)
    return AuthoritySource(**values)


@contextmanager
def loopback_server(handler, server_class=ThreadingHTTPServer):
    """A fresh TCP server whose accept loop, handlers and sockets we own.

    A socketpair wakes the accept loop without a shutdown poll or a synthetic
    HTTP request. Stop-aware handlers return without finishing delayed replies;
    shutting down accepted sockets also releases incomplete request reads.
    """
    stopped = threading.Event()
    handlers, connections, errors = [], [], []

    class OwnedServer(server_class):
        # Join our explicit handler inventory below, including still-running
        # requests. Daemon threads are not a substitute for fixture cleanup.
        daemon_threads = False
        block_on_close = False
        stop_event = stopped

        def get_request(self):
            connection, address = super().get_request()
            connections.append(connection)
            return connection, address

        def process_request(self, request, client_address):
            worker = threading.Thread(
                target=self.process_request_thread, args=(request, client_address)
            )
            handlers.append(worker)
            worker.start()

        def handle_error(self, request, client_address):
            errors.append(client_address)
            super().handle_error(request, client_address)

    with ExitStack() as stack:
        service = stack.enter_context(OwnedServer(("127.0.0.1", 0), handler))
        wake_read, wake_write = socket.socketpair()
        stack.enter_context(wake_read)
        stack.enter_context(wake_write)
        selector = stack.enter_context(selectors.DefaultSelector())
        selector.register(service, selectors.EVENT_READ)
        selector.register(wake_read, selectors.EVENT_READ)

        def serve():
            while not stopped.is_set():
                ready = selector.select()
                if stopped.is_set():
                    return
                if any(key.fileobj is service for key, _ in ready):
                    service.handle_request()

        worker = threading.Thread(target=serve)
        worker.start()
        try:
            yield service
        finally:
            stopped.set()
            wake_write.send(b"x")
            worker.join(timeout=2)
            assert not worker.is_alive(), "owned loopback accept thread survived teardown"
            # The accept thread has ended, so the inventories cannot grow.
            for connection in connections:
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass  # A normally completed request already closed it.
            for handler_thread in handlers:
                handler_thread.join(timeout=2)
            service.server_close()
            assert all(not thread.is_alive() for thread in handlers), (
                "owned loopback handler survived teardown"
            )
            assert all(connection.fileno() == -1 for connection in connections), (
                "owned loopback accepted socket survived teardown"
            )
            assert service.socket.fileno() == -1, "loopback listener survived teardown"
            assert not errors, "owned loopback handler raised an unexpected exception"


@pytest.fixture
def authority_server():
    state = {"status": 200, "body": b"", "headers": {}, "requests": []}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            if self.server.stop_event.is_set():
                return
            state["requests"].append(
                (self.command, self.path, dict(self.headers), body)
            )
            self.send_response(state["status"])
            self.send_header("Content-Length", str(len(state["body"])))
            for key, value in state["headers"].items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(state["body"])

        do_POST = do_GET

        def log_message(self, *_):
            pass

    class LocalWire(httpx.BaseTransport):
        def __init__(self):
            self.transport = httpx.HTTPTransport()

        def handle_request(self, request):
            # Test-only routing preserves adapter validation; actual HTTP bytes hit TCP.
            request.url = request.url.copy_with(
                scheme="http", host="127.0.0.1", port=server.server_port
            )
            return self.transport.handle_request(request)

        def close(self):
            self.transport.close()

    with loopback_server(Handler) as server:
        with httpx.Client(transport=LocalWire()) as client:
            yield state, client


def test_registry_denies_cross_scope_classification_operation_and_unapproved():
    registry = AuthorityRegistry(version="1", sources=(source(),))
    assert registry.authorize("example_places", "place_search", query())
    for change in (
        {"organization_id": "other"},
        {"collection_id": "other"},
        {"data_classification": "restricted"},
    ):
        assert (
            registry.authorize(
                "example_places", "place_search", query().model_copy(update=change)
            )
            is None
        )
    assert registry.authorize("example_places", "write", query()) is None
    assert (
        AuthorityRegistry(version="1", sources=(source(approved=False),)).authorize(
            "example_places", "place_search", query()
        )
        is None
    )
    with pytest.raises(ValidationError):
        AuthorityRegistry(version="1", sources=(source(), source()))


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://example.org",
        "https://x:y@example.org",
        "https://example.org?q=secret",
        "https://example.org/#fragment",
    ],
)
def test_fixed_endpoint_rejects_credentials_redirect_inputs(endpoint):
    with pytest.raises(ValidationError):
        source(endpoint=endpoint)


def test_party_identity_immutable_qualified_and_strict():
    values = dict(
        source_system="emu",
        connection_id="read-only",
        tenant="fmnh",
        environment="synthetic",
        irn=1,
    )
    identity = PartiesIdentity(**values)
    with pytest.raises(ValidationError):
        identity.irn = 2
    for invalid in (True, 0, "1"):
        with pytest.raises(ValidationError):
            PartiesIdentity(**(values | {"irn": invalid}))
    with pytest.raises(ValidationError):
        PartiesIdentity(**values, module="ecatalogue")


def test_loopback_cases_have_independent_reply_and_request_state():
    fixture = contextmanager(authority_server.__wrapped__)
    with fixture() as (first, first_client), fixture() as (second, second_client):
        assert first is not second and first_client is not second_client
        assert first["headers"] is not second["headers"]
        assert first["requests"] is not second["requests"]
        first.update(body=b"first", status=201, headers={"X-Case": "first"})
        second.update(body=b"second", status=202, headers={"X-Case": "second"})
        response = first_client.post("https://authority.example/first", content=b"one")
        assert (response.content, response.status_code, response.headers["X-Case"]) == (
            b"first", 201, "first"
        )
        assert second["requests"] == []
        response = second_client.post("https://authority.example/second", content=b"two")
        assert (response.content, response.status_code, response.headers["X-Case"]) == (
            b"second", 202, "second"
        )
        assert first["requests"][0][1] == "/first"
        assert first["requests"][0][3] == b"one"
        assert second["requests"][0][1] == "/second"
        assert second["requests"][0][3] == b"two"
        first["requests"].clear()
        first["headers"].clear()
        assert len(second["requests"]) == 1 and second["headers"] == {"X-Case": "second"}
