"""Only local synthetic effects. Helper functions are importable spawn targets."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import threading
import time
from urllib.request import urlopen

import pytest

from specimen_digitization.application.bounded_effect import run_isolated


def echo_bytes(payload):
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()


def slow_auth_then_http(payload):
    Path(payload["auth_marker"]).write_text("authentication started")
    time.sleep(payload["auth_delay"])
    with urlopen(payload["url"], timeout=10) as response:
        return response.read(payload["read_limit"])


def raw_http(payload):
    with urlopen(payload["url"], timeout=10) as response:
        return response.read(payload["read_limit"])


def die_in_worker(payload):
    os._exit(7)


def ignore_term_and_finish_late(payload):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    Path(payload["started"]).write_text("started")
    time.sleep(10)
    Path(payload["late"]).write_text("must not happen")
    return b"late output"


def noisy_failure(payload):
    print("synthetic sensitive response")
    raise RuntimeError("synthetic sensitive response")


def non_bytes(payload):
    return {"wrong": "contract"}


@contextmanager
def local_server(*, drip=False, size=1024):
    requests = []
    stopping = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            requests.append(self.path)
            self.send_response(200)
            self.send_header("Content-Length", str(size))
            self.end_headers()
            try:
                if drip:
                    for _ in range(size):
                        if stopping.is_set():
                            return
                        self.wfile.write(b"x")
                        self.wfile.flush()
                        time.sleep(0.04)
                else:
                    self.wfile.write(b"x" * size)
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = False
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/effect", requests
    finally:
        stopping.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()


def assert_reaped(result):
    assert result.cleanup_complete
    if result.worker_pid:
        with pytest.raises(ProcessLookupError):
            os.kill(result.worker_pid, 0)


def test_raw_response_exact_bytes_and_json_boundary():
    value = {"x": "é"}
    encoded = b'{"x":"\xc3\xa9"}'
    result = run_isolated(
        echo_bytes, value, 3, len(encoded), max_input_bytes=len(encoded)
    )
    assert result.status == "completed"
    assert result.value == encoded
    assert result.input_bytes == result.result_bytes == len(encoded)
    assert result.elapsed_seconds > 0
    assert_reaped(result)


def test_slow_auth_consumes_same_deadline_and_never_starts_http(tmp_path):
    with local_server() as (url, requests):
        result = run_isolated(
            slow_auth_then_http,
            {
                "auth_marker": str(tmp_path / "auth"),
                "auth_delay": 2,
                "url": url,
                "read_limit": 100,
            },
            0.6,
            100,
        )
        assert (tmp_path / "auth").exists()
        assert result.status == "deadline_exceeded" and result.value is None
        assert requests == []
        assert result.elapsed_seconds < 2
        assert_reaped(result)


def test_drip_http_cannot_reset_overall_deadline():
    with local_server(drip=True, size=100) as (url, requests):
        result = run_isolated(raw_http, {"url": url, "read_limit": 100}, 0.6, 100)
        assert requests == ["/effect"]
        assert result.status == "deadline_exceeded" and result.value is None
        assert result.elapsed_seconds < 2
        assert_reaped(result)


def test_oversized_actual_http_response_not_received_by_parent():
    with local_server(size=4096) as (url, requests):
        result = run_isolated(raw_http, {"url": url, "read_limit": 4096}, 3, 32)
        assert result.status == "output_limit" and result.value is None
        assert requests == ["/effect"]
        assert_reaped(result)


def test_process_death_has_no_response_and_no_retry():
    result = run_isolated(die_in_worker, {}, 3, 32)
    assert result.status == "worker_failed" and result.value is None
    assert result.reason == "worker_process_exit"
    assert_reaped(result)


def test_term_resistance_requires_kill_and_no_late_output(tmp_path):
    result = run_isolated(
        ignore_term_and_finish_late,
        {"started": str(tmp_path / "started"), "late": str(tmp_path / "late")},
        0.6,
        100,
    )
    assert (tmp_path / "started").exists()
    assert not (tmp_path / "late").exists()
    assert result.status == "deadline_exceeded" and result.value is None
    assert 0.6 <= result.elapsed_seconds < 4
    assert_reaped(result)


def test_failure_does_not_log_or_return_sensitive_details(capfd):
    result = run_isolated(noisy_failure, {}, 3, 100)
    assert result.status == "worker_failed" and result.value is None
    assert "synthetic sensitive" not in repr(result)
    captured = capfd.readouterr()
    assert "synthetic sensitive" not in captured.out + captured.err
    assert_reaped(result)


def test_invalid_inputs_and_callable_do_not_spawn():
    for value in ({"v": "x" * 100}, [0] * 100):
        result = run_isolated(echo_bytes, value, 3, 100, max_input_bytes=10)
        assert result.reason == "input_limit" and result.worker_pid is None
    cycle = []
    cycle.append(cycle)
    for value in (cycle, float("nan"), {1: "bad key"}, object()):
        result = run_isolated(echo_bytes, value, 3, 100)
        assert result.status == "worker_failed" and result.worker_pid is None
    with pytest.raises(ValueError):
        run_isolated("user.module.function", {}, 3, 100)
    with pytest.raises(ValueError):
        run_isolated(lambda p: b"not importable", {}, 3, 100)
    result = run_isolated(echo_bytes, {"v": 1}, 1e-12, 100)
    assert result.status == "deadline_exceeded" and result.worker_pid is None


def test_non_bytes_response_rejected():
    result = run_isolated(non_bytes, {}, 3, 100)
    assert result.status == "worker_failed" and result.value is None
    assert_reaped(result)


def test_spawn_delay_counts_toward_deadline(monkeypatch):
    from specimen_digitization.application import bounded_effect

    real = bounded_effect.subprocess.Popen

    def slow_start(*args, **kwargs):
        time.sleep(0.15)
        return real(*args, **kwargs)

    monkeypatch.setattr(bounded_effect.subprocess, "Popen", slow_start)
    result = run_isolated(echo_bytes, {}, 0.1, 100)
    assert result.status == "deadline_exceeded" and result.value is None
    assert_reaped(result)


def test_private_ipc_files_removed_on_success_and_failure(tmp_path, monkeypatch):
    from specimen_digitization.application import bounded_effect

    real = bounded_effect.TemporaryDirectory

    def owned_directory(*args, **kwargs):
        return real(*args, dir=tmp_path, **kwargs)

    monkeypatch.setattr(bounded_effect, "TemporaryDirectory", owned_directory)
    for helper in (echo_bytes, noisy_failure, die_in_worker):
        result = run_isolated(helper, {"private": "synthetic"}, 3, 100)
        assert_reaped(result)
        assert list(tmp_path.iterdir()) == []


def test_nested_input_limit_and_output_byte_count():
    nested = []
    for _ in range(65):
        nested = [nested]
    result = run_isolated(echo_bytes, nested, 3, 1000)
    assert result.reason == "input_limit" and result.worker_pid is None
    result = run_isolated(echo_bytes, {"x": "a" * 100}, 3, 10)
    assert result.status == "output_limit"
    assert result.result_bytes == len(b'{"x":"' + b"a" * 100 + b'"}')
    assert result.value is None
    assert_reaped(result)
