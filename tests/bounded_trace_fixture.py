"""Real SDK and application child lifecycle with an entirely local TLS double."""

from pathlib import Path


def traced_child(payload):
    import socket
    import requests
    import logfire
    from specimen_digitization import bounded_trace_transport
    from specimen_digitization.observability import isolated_model_span

    def forbidden(*args, **kwargs):
        raise AssertionError("native requests forbidden in synthetic fixture")

    socket.getaddrinfo = forbidden
    requests.Session.request = forbidden

    class LocalConnection:
        response = b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n"
        def settimeout(self, timeout):
            assert timeout > 0
        def sendall(self, wire):
            with open(payload["wire"], "ab") as output:
                output.write(wire)
        def recv(self, count):
            data, self.response = self.response[:count], self.response[count:]
            return data
        def close(self):
            pass

    bounded_trace_transport._open_tls = lambda deadline: LocalConnection()
    with isolated_model_span(
        {"specimen_id": "synthetic-specimen", "run_id": "synthetic-run"},
        operation="transcribe", region_id="synthetic-region", route_id="reader-a",
    ):
        with logfire.span("PRIVATE-LABEL-CANARY", prompt="PRIVATE-PROMPT-CANARY"):
            Path(payload["model_done"]).write_text("known result")
    return b"known model result"
