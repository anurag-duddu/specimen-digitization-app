"""Synthetic native-code stalls prove the outside guard survives hard exit."""
import json
import os
from pathlib import Path
import sys
import time

import pytest

import release_publication_deadline as M


@pytest.mark.skipif(sys.platform != "linux", reason="qualified on the protected Linux process model")
@pytest.mark.parametrize("stage", ["refresh", "headers", "body", "close"])
def test_swallowed_soft_request_deadline_cannot_leave_owned_work(stage, tmp_path):
    marker = tmp_path / "entered"
    script = f'''
import signal, sys, time
sys.path.insert(0, {str(Path(__file__).parent)!r})
import release_publication_deadline as p
with p.total_request(.15):
    open({str(marker)!r}, 'w').write({stage!r})
    while True:
        try: time.sleep(1)
        except p.RequestExpired: pass
'''
    supervisor = M.Supervisor(M.Deadline(time.time() + 15))
    began = time.monotonic()
    with pytest.raises(M.PublicationStopped):
        supervisor.run_owned([sys.executable, "-c", script], env=dict(os.environ), cwd=tmp_path,
                             stage=stage, limit=2)
    assert marker.read_text() == stage
    assert time.monotonic() - began < 2
    assert not M.process_group_alive(supervisor.last_group)


def test_runtime_build_transport_bounds_implicit_refresh_and_close(monkeypatch):
    import release_google as google
    packet = {"expires_at_unix": time.time() + 30, "identity": {"project_number": "123"}}
    monkeypatch.setattr(M, "CURRENT", M.Deadline(packet["expires_at_unix"]))
    monkeypatch.setattr(M, "BOUND_PACKET", packet)
    seen = []
    class Response:
        status_code = 200
        def json(self):
            seen.append("body")
            return {"ok": True}
        def close(self):
            seen.append("close")
    class Session:
        def request(self, method, url, **kwargs):
            assert 0 < kwargs["timeout"] <= 20
            assert kwargs["max_allowed_time"] == kwargs["timeout"]
            assert kwargs["allow_redirects"] is False
            assert __import__('signal').getitimer(__import__('signal').ITIMER_REAL)[0] > 0
            seen.append("implicit_refresh_inside_guard")
            return Response()
    client = google.Google.__new__(google.Google)
    client.plane, client.packet, client.session = "runtime-build", packet, Session()
    assert client.request("registry", "GET", "projects/specimen-digitization/locations/us-east4/repositories/specimen-runtime") == {"ok": True}
    assert seen == ["implicit_refresh_inside_guard", "body", "close"]
    assert __import__('signal').getitimer(__import__('signal').ITIMER_REAL) == (0.0, 0.0)


def test_expired_runtime_build_request_never_refreshes(monkeypatch):
    import release_google as google
    packet = {"expires_at_unix": time.time(), "identity": {"project_number": "123"}}
    monkeypatch.setattr(M, "CURRENT", M.Deadline(packet["expires_at_unix"]))
    monkeypatch.setattr(M, "BOUND_PACKET", packet)
    client = google.Google.__new__(google.Google)
    client.plane, client.packet = "runtime-build", packet
    class Session:
        def request(self, *args, **kwargs):
            pytest.fail("expired request reached credential-capable session")
    client.session = Session()
    with pytest.raises(M.PublicationStopped):
        client.request("registry", "GET", "projects/specimen-digitization/locations/us-east4/repositories/specimen-runtime")
