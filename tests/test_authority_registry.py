import hashlib
import threading
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
        source_id="parties" if parties else "gbif_gadm",
        version="synthetic-source-v1",
        endpoint="https://museum.example/fmnh/eparties"
        if parties
        else "https://api.gbif.org/v1/geocode/gadm/search",
        operations=("eparties_search",) if parties else ("gadm_search",),
        scopes=(("synthetic", "insects"),),
        classifications=("public",),
        approved=True,
    )
    values.update(changes)
    return AuthoritySource(**values)


@pytest.fixture
def authority_server():
    state = {"status": 200, "body": b"", "headers": {}, "requests": []}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
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

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

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

    with httpx.Client(transport=LocalWire()) as client:
        yield state, client
    server.shutdown()
    server.server_close()
    thread.join()


def test_registry_denies_cross_scope_classification_operation_and_unapproved():
    registry = AuthorityRegistry(version="1", sources=(source(),))
    assert registry.authorize("gbif_gadm", "gadm_search", query())
    for change in (
        {"organization_id": "other"},
        {"collection_id": "other"},
        {"data_classification": "restricted"},
    ):
        assert (
            registry.authorize(
                "gbif_gadm", "gadm_search", query().model_copy(update=change)
            )
            is None
        )
    assert registry.authorize("gbif_gadm", "write", query()) is None
    assert (
        AuthorityRegistry(version="1", sources=(source(approved=False),)).authorize(
            "gbif_gadm", "gadm_search", query()
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
