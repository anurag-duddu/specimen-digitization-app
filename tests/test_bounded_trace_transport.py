"""Synthetic sockets only: no credentials, DNS or native network traffic."""

import importlib
from types import SimpleNamespace

import pytest

from specimen_digitization.bounded_telemetry import HEADER_ALLOWANCE


class SocketFixture:
    def __init__(self, response, *, clock, late=None):
        self.response = response
        self.clock = clock
        self.late = late
        self.sent = []
        self.timeouts = []
        self.read_sizes = []
        self.read_bytes = 0
        self.closed = False

    def settimeout(self, timeout):
        assert 0 < timeout <= 2
        self.timeouts.append(timeout)

    def sendall(self, body):
        self.sent.append(body)
        if self.late == "send":
            self.clock[0] = 103

    def recv(self, size):
        self.read_sizes.append(size)
        if self.late == "receive":
            self.clock[0] = 103
        body, self.response = self.response[:size], self.response[size:]
        self.read_bytes += len(body)
        return body

    def close(self):
        self.closed = True
        if self.late == "close":
            self.clock[0] = 103


def setup_transport(monkeypatch, response, *, late=None, token="synthetic-writer"):
    module = importlib.import_module("specimen_digitization.bounded_trace_transport")
    clock = [100.0]
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    sock = SocketFixture(response, clock=clock, late=late)
    opens = []

    def connect(deadline):
        opens.append(deadline)
        if late == "connect":
            clock[0] = 103
        return sock

    monkeypatch.setattr(module, "_open_tls", connect)
    sender = module.TraceTransport(token, remaining=lambda: 102 - clock[0])
    return module, sender, sock, opens, clock


def test_fixed_us_single_post_counts_all_actual_headers_and_ignores_proxy(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "https://private-invalid.example.test")
    monkeypatch.setenv("LOGFIRE_BASE_URL", "https://private-invalid.example.test")
    module, sender, sock, opens, _ = setup_transport(
        monkeypatch, b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n"
    )
    assert sender(b"synthetic-protobuf", 1) == 200
    assert opens == [101]
    wire = b"".join(sock.sent)
    headers, body = wire.split(b"\r\n\r\n", 1)
    assert len(headers) + 4 <= HEADER_ALLOWANCE
    assert headers.startswith(b"POST /v1/traces HTTP/1.1\r\n")
    assert b"Host: logfire-us.pydantic.dev\r\n" in headers
    assert b"Content-Length: 18\r\n" in headers
    assert b"Accept-Encoding: identity" in headers
    assert body == b"synthetic-protobuf"
    assert sock.closed and module.HOST == "logfire-us.pydantic.dev"


@pytest.mark.parametrize("late", ["connect", "send", "receive", "close"])
def test_every_phase_must_complete_before_original_deadline(monkeypatch, late):
    _, sender, sock, opens, _ = setup_transport(
        monkeypatch, b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n", late=late
    )
    assert sender(b"fixture", 1) is None
    assert len(opens) == 1 and sock.closed
    if late == "connect":
        assert not sock.sent


@pytest.mark.parametrize("response", [
    b"HTTP/1.1 200 OK\r\nX: " + b"h" * 16384 + b"\r\n\r\n",
    b"HTTP/1.1 200 OK\r\nContent-Length: 65537\r\n\r\n" + b"b" * 65537,
    b"HTTP/1.1 200 OK\r\n\r\n" + b"b" * 65537,
    b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n10001\r\n" + b"b" * 65537,
    b"PRIVATE-ERROR-CANARY\r\n\r\n",
])
def test_response_overflow_and_invalid_status_fail_closed(monkeypatch, response):
    _, sender, sock, opens, _ = setup_transport(monkeypatch, response)
    assert sender(b"fixture", 1) is None
    assert len(opens) == 1 and sock.closed
    assert sock.read_bytes <= 16385 + 65537


@pytest.mark.parametrize("status", [301, 307, 401, 429, 500])
def test_rejections_and_redirects_are_never_retried(monkeypatch, status):
    response = f"HTTP/1.1 {status} Fixed\r\nContent-Length: 0\r\nLocation: https://invalid.example.test\r\n\r\n".encode()
    _, sender, sock, opens, _ = setup_transport(monkeypatch, response)
    assert sender(b"fixture", 1) == status
    assert len(opens) == 1 and len(sock.sent) == 1 and sock.closed


@pytest.mark.parametrize("token", ["", "x\r\nInjection: yes", "non-ascii-\u2603", "x" * 8192])
def test_invalid_or_oversized_credential_never_opens_socket(monkeypatch, token):
    module = importlib.import_module("specimen_digitization.bounded_trace_transport")
    monkeypatch.setattr(module, "_open_tls", lambda *a: pytest.fail("native socket forbidden"))
    with pytest.raises(module.TraceTransportError, match="invalid_trace_credential"):
        module.TraceTransport(token, remaining=lambda: 1)


def test_expired_or_oversized_request_never_opens_socket(monkeypatch):
    _, sender, sock, opens, clock = setup_transport(monkeypatch, b"")
    assert sender(b"x" * (2 * 1024**2 - HEADER_ALLOWANCE + 1), 1) is None
    clock[0] = 102
    assert sender(b"fixture", 1) is None
    assert not opens and not sock.sent


def test_chunked_success_stays_inside_response_wire_budget(monkeypatch):
    _, sender, sock, opens, _ = setup_transport(
        monkeypatch, b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n"
    )
    assert sender(b"fixture", 1) == 200
    assert len(opens) == 1 and sock.closed


@pytest.mark.parametrize("headers,body", [
    (b"Content-Type: application/x-protobuf", b"\x0a\x02\x08\x01"),
    (b"Content-Type: application/x-protobuf", b"malformed"),
    (b"Content-Type: application/json", b"{}"),
    (b"Content-Encoding: gzip", b""),
    (b"Content-Length: 0", b""),
    (b"Transfer-Encoding: chunked", b""),
])
def test_partial_success_malformed_or_ambiguous_response_is_not_accepted(monkeypatch, headers, body):
    response = b"HTTP/1.1 200 OK\r\n" + headers + b"\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
    _, sender, sock, opens, _ = setup_transport(monkeypatch, response)
    assert sender(b"fixture", 1) is None
    assert len(opens) == 1 and sock.closed


@pytest.mark.parametrize("body", [b"0\r\n", b"1\r\nx\r\n", b"1\r\nx\r\n0\r\n", b"1\r\naXX0\r\n\r\n"])
def test_truncated_chunked_response_cannot_count_as_success(monkeypatch, body):
    _, sender, _, opens, _ = setup_transport(
        monkeypatch, b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n" + body,
    )
    assert sender(b"fixture", 1) is None
    assert len(opens) == 1


def test_final_remaining_callback_cannot_extend_the_attempt(monkeypatch):
    _, sender, _, _, clock = setup_transport(
        monkeypatch, b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n",
    )
    calls = []
    def remaining():
        calls.append(1)
        if len(calls) == 2:
            clock[0] = 101.5
        return 20
    sender._remaining = remaining
    assert sender(b"fixture", 1) is None


def test_only_otlp_200_is_a_success(monkeypatch):
    _, sender, _, _, _ = setup_transport(
        monkeypatch, b"HTTP/1.1 204 Empty\r\nContent-Length: 0\r\n\r\n",
    )
    assert sender(b"fixture", 1) is None


@pytest.mark.parametrize("body", [b"\x0a\x00", b"\x0a\x05\x12\x03msg"])
def test_zero_rejections_accepts_empty_partial_or_warning_without_retaining_text(monkeypatch, body):
    _, sender, _, _, _ = setup_transport(
        monkeypatch, b"HTTP/1.1 200 OK\r\nContent-Type: application/x-protobuf\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body,
    )
    assert sender(b"fixture", 1) == 200


@pytest.mark.parametrize("fail", [False, True])
def test_tls_verifies_fixed_host_and_never_falls_back_to_second_address(monkeypatch, fail):
    from specimen_digitization import bounded_trace_transport as module
    calls = []
    class Connection:
        def settimeout(self, timeout):
            assert 0 < timeout <= 2
        def connect(self, address):
            calls.append(("connect", address))
            if fail:
                raise OSError("synthetic failure")
        def do_handshake(self):
            calls.append("handshake")
        def close(self):
            calls.append("close")
    connection = Connection()
    class Context:
        def set_alpn_protocols(self, protocols):
            assert protocols == ["http/1.1"]
        def wrap_socket(self, raw, **options):
            assert raw is connection
            assert options == {"server_hostname": module.HOST, "do_handshake_on_connect": False}
            calls.append("verified_context")
            return connection
    def resolve(host, port, **kwargs):
        assert (host, port) == (module.HOST, 443)
        calls.append("resolve")
        return [(2, 1, 6, "", ("192.0.2.1", 443)), (2, 1, 6, "", ("192.0.2.2", 443))]
    monkeypatch.setattr(module.socket, "getaddrinfo", resolve)
    monkeypatch.setattr(module.socket, "socket", lambda *args: connection)
    monkeypatch.setattr(module.ssl, "create_default_context", Context)
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: 100))
    if fail:
        with pytest.raises(OSError):
            module._open_tls(102)
        assert calls == ["resolve", ("connect", ("192.0.2.1", 443)), "close"]
    else:
        assert module._open_tls(102) is connection
        assert calls == ["resolve", ("connect", ("192.0.2.1", 443)), "verified_context", "handshake"]


def test_slow_drip_checks_absolute_deadline_and_counts_actual_received_bytes(monkeypatch):
    _, sender, sock, opens, clock = setup_transport(
        monkeypatch, b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n",
    )
    receive = sock.recv
    def drip(size):
        clock[0] += 0.1
        return receive(min(size, 1))
    sock.recv = drip
    assert sender(b"fixture", 1) is None
    assert 1 <= sock.read_bytes <= 11
    assert len(opens) == 1 and sock.closed


@pytest.mark.parametrize("extension", [
    b";\x00", b";=invalid", b';name="unterminated', b";name=value",
])
def test_chunk_extensions_are_rejected_without_retry(monkeypatch, extension):
    # The bounded transport accepts only the extension-free framing it parses.
    response = (b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n0"
                + extension + b"\r\n\r\n")
    _, sender, sock, opens, _ = setup_transport(monkeypatch, response)
    assert sender(b"fixture", 1) is None
    assert len(opens) == len(sock.sent) == 1 and sock.closed
