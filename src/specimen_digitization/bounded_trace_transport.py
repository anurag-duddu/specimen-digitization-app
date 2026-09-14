"""One fixed US HTTPS POST for the approved metadata-only worker processor.

No constructor performs I/O. The existing effect/worker process supervisor is
the hard stop during DNS or kernel stalls; this module never extends that clock.
"""

from __future__ import annotations

import http.client
import math
import os
import re
import socket
import ssl
import time

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceResponse,
)

from .bounded_telemetry import HEADER_ALLOWANCE

HOST = "logfire-us.pydantic.dev"
HEADER_LIMIT = 16 * 1024
BODY_LIMIT = 64 * 1024
REQUEST_LIMIT = 2 * 1024**2


class TraceTransportError(RuntimeError):
    """Content-free failure: no credential or response body is retained."""


def _remaining(deadline):
    value = deadline - time.monotonic()
    if not math.isfinite(value) or value <= 0:
        raise TraceTransportError("trace_transport_deadline")
    return value


def _open_tls(deadline):
    """Resolve once, attempt one address, and verify the fixed TLS hostname."""
    _remaining(deadline)
    if any(os.getenv(name) is not None for name in (
        "SSL_CERT_FILE", "SSL_CERT_DIR", "SSLKEYLOGFILE",
    )):
        raise TraceTransportError("trace_tls_override_forbidden")
    addresses = socket.getaddrinfo(
        HOST, 443, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP,
    )
    _remaining(deadline)
    if not addresses:
        raise TraceTransportError("trace_transport_unavailable")
    family, kind, protocol, _, address = addresses[0]
    connection = socket.socket(family, kind, protocol)
    try:
        connection.settimeout(_remaining(deadline))
        connection.connect(address)
        _remaining(deadline)
        context = ssl.create_default_context()
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.set_alpn_protocols(["http/1.1"])
        _remaining(deadline)
        connection = context.wrap_socket(
            connection, server_hostname=HOST, do_handshake_on_connect=False,
        )
        connection.settimeout(_remaining(deadline))
        connection.do_handshake()
        _remaining(deadline)
        return connection
    except BaseException:
        connection.close()
        raise


class _ResponseReader:
    """No buffered prefetch; headers and body each have one overflow sentinel.

Every raw receive checks the same absolute deadline, including slow drip data.
Chunk framing and trailers consume the conservative body allowance. Counters
are decrypted application bytes, not a measurement of TLS or network overhead.
"""

    def __init__(self, connection, deadline):
        self.connection = connection
        self.deadline = deadline
        self.available = HEADER_LIMIT
        self.closed = False
        self.eof = False

    def makefile(self, *args, **kwargs):
        return self

    def close(self):
        self.closed = True

    def flush(self):
        pass

    def _recv(self, size):
        if self.closed:
            return b""
        self.connection.settimeout(_remaining(self.deadline))
        data = self.connection.recv(min(size, self.available + 1))
        _remaining(self.deadline)
        self.available -= len(data)
        self.eof |= not data
        if self.available < 0:
            raise TraceTransportError("trace_response_limit")
        return data

    def read(self, size=-1):
        size = self.available + 1 if size < 0 else size
        output = bytearray()
        while len(output) < size:
            data = self._recv(size - len(output))
            if not data:
                break
            output.extend(data)
        return bytes(output)

    def readline(self, size=-1):
        size = self.available + 1 if size < 0 else size
        output = bytearray()
        while len(output) < size:
            data = self._recv(1)
            if not data:
                break
            output.extend(data)
            if data == b"\n":
                break
        if not output.endswith(b"\r\n"):
            raise TraceTransportError("trace_response_incomplete")
        return bytes(output)


def _read_response(reader):
    response = http.client.HTTPResponse(reader, method="POST")
    try:
        response.begin()
        if response.headers.defects:
            raise TraceTransportError("trace_response_framing")
        headers = {}
        for name, value in response.getheaders():
            name = name.lower()
            if name in {"content-length", "transfer-encoding", "content-encoding", "content-type"}:
                if name in headers:
                    raise TraceTransportError("trace_response_framing")
                headers[name] = value.strip().lower()
        length = headers.get("content-length")
        transfer = headers.get("transfer-encoding")
        if (length is not None and (not re.fullmatch(r"[0-9]+", length)
                                    or int(length) > BODY_LIMIT)
                or transfer is not None and (transfer != "chunked" or length is not None)
                or headers.get("content-encoding", "identity") != "identity"):
            raise TraceTransportError("trace_response_framing")
        reader.available = BODY_LIMIT
        if transfer:
            body = bytearray()
            while True:
                chunk = reader.readline()[:-2].split(b";", 1)[0]
                if not re.fullmatch(rb"[0-9A-Fa-f]{1,16}", chunk):
                    raise TraceTransportError("trace_response_framing")
                size = int(chunk, 16)
                if size > reader.available:
                    raise TraceTransportError("trace_response_limit")
                if size == 0:
                    while True:
                        trailer = reader.readline()
                        if trailer == b"\r\n":
                            break
                        if not re.fullmatch(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+:[\t\x20-\x7e]*\r\n", trailer):
                            raise TraceTransportError("trace_response_framing")
                    break
                part = reader.read(size)
                if len(part) != size or reader.read(2) != b"\r\n":
                    raise TraceTransportError("trace_response_incomplete")
                body.extend(part)
            body = bytes(body)
        elif length is not None:
            body = reader.read(int(length))
            if len(body) != int(length):
                raise TraceTransportError("trace_response_incomplete")
        else:
            body = reader.read(BODY_LIMIT + 1)
        if response.status == 200:
            if body and headers.get("content-type") != "application/x-protobuf":
                raise TraceTransportError("trace_response_type")
            result = ExportTraceServiceResponse.FromString(body)
            # OTLP can return HTTP 200 while rejecting records. Never call that
            # a full acknowledgement, retry it, or retain its diagnostic text.
            if result.partial_success.rejected_spans != 0:
                raise TraceTransportError("trace_response_partial")
        elif 200 <= response.status < 300:
            raise TraceTransportError("trace_response_status")
        _remaining(reader.deadline)
        return response.status
    finally:
        response.close()


class TraceTransport:
    """Fixed destination dispatcher, called after a durable one-use claim.

There is no GET, retry, redirect, proxy, background work, or SDK exporter. A
status does not replace the processor's timely local finalization or the live
release's independent trace-delivery verification.
"""

    def __init__(self, token, *, remaining):
        if (not isinstance(token, str)
                or not re.fullmatch(r"[!-~]{1,4096}", token)):
            raise TraceTransportError("invalid_trace_credential")
        self._token = token
        self._remaining = remaining

    def __call__(self, body, timeout):
        connection = None
        status = None
        try:
            if (type(body) is not bytes or not body
                    or len(body) + HEADER_ALLOWANCE > REQUEST_LIMIT
                    or type(timeout) not in (int, float) or not math.isfinite(timeout)):
                return None
            deadline = time.monotonic() + min(timeout, self._remaining(), 2.0)
            _remaining(deadline)
            headers = (
                "POST /v1/traces HTTP/1.1\r\n"
                f"Host: {HOST}\r\n"
                f"Authorization: {self._token}\r\n"
                "Content-Type: application/x-protobuf\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Accept-Encoding: identity\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii")
            # These are all request headers: no HTTP library adds more.
            if len(headers) > HEADER_ALLOWANCE:
                return None
            connection = _open_tls(deadline)
            connection.settimeout(_remaining(deadline))
            connection.sendall(headers + body)
            _remaining(deadline)
            status = _read_response(_ResponseReader(connection, deadline))
        except Exception:
            status = None
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    status = None
        if status is not None:
            try:
                _remaining(deadline)
                if self._remaining() <= 0:
                    return None
                _remaining(deadline)
            except Exception:
                return None
        return status
