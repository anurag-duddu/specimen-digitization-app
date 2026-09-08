"""A hard local process boundary around an entire trusted synchronous effect.

Callables must be hardcoded application helpers, never supplied by API clients.
A terminated local child does not cancel a request already accepted remotely.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import inspect
import json
import math
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from typing import Callable, Literal

MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_DEPTH = 64
TERMINATE_GRACE_SECONDS = 1.0
KILL_GRACE_SECONDS = 2.0


@dataclass(frozen=True)
class IsolatedResult:
    status: Literal["completed", "deadline_exceeded", "worker_failed", "output_limit"]
    value: bytes | None
    elapsed_seconds: float
    input_bytes: int
    result_bytes: int
    reason: str
    worker_pid: int | None = None
    cleanup_complete: bool = True


class _JsonLimit(Exception):
    pass


class _Deadline(Exception):
    pass


def _check_deadline(deadline: float):
    if time.monotonic() >= deadline:
        raise _Deadline


def _json_bytes(value: object, limit: int, deadline: float) -> bytes:
    """Reject custom Python objects and bound traversal before encoder allocation."""
    remaining = limit
    active: set[int] = set()
    stack = [(iter((value,)), None)]
    nodes = 0
    while stack:
        _check_deadline(deadline)
        iterator, container_id = stack[-1]
        try:
            item = next(iterator)
        except StopIteration:
            stack.pop()
            if container_id is not None:
                active.remove(container_id)
            continue
        nodes += 1
        if nodes > 100_000 or len(stack) > MAX_DEPTH:
            raise _JsonLimit
        kind = type(item)
        if kind in (dict, list):
            if id(item) in active:
                raise ValueError("non_json_input")
            remaining -= 2 + max(0, len(item) - 1)
            if kind is dict:
                for key in item:
                    _check_deadline(deadline)
                    if type(key) is not str:
                        raise ValueError("non_json_key")
                    remaining -= len(key) + 3
                    if remaining < 0:
                        raise _JsonLimit
                children = iter(item.values())
            else:
                children = iter(item)
            active.add(id(item))
            stack.append((children, id(item)))
        elif kind is str:
            remaining -= len(item) + 2
        elif kind is float:
            if not math.isfinite(item):
                raise ValueError("non_finite_json_number")
            remaining -= 1
        elif kind is int:
            if item.bit_length() > limit * 4:
                raise _JsonLimit
            remaining -= 1
        elif item is None or kind is bool:
            remaining -= 1
        else:
            raise ValueError("non_json_value")
        if remaining < 0:
            raise _JsonLimit
    output = bytearray()
    for piece in json.JSONEncoder(
        ensure_ascii=False, allow_nan=False, separators=(",", ":")
    ).iterencode(value):
        _check_deadline(deadline)
        if len(piece) > limit - len(output):
            raise _JsonLimit
        encoded = piece.encode("utf-8")
        if len(output) + len(encoded) > limit:
            raise _JsonLimit
        output.extend(encoded)
    _check_deadline(deadline)
    return bytes(output)


def _callable_reference(function: Callable) -> tuple[str, str]:
    if not inspect.isfunction(function) or function.__module__ == "__main__":
        raise ValueError("trusted callable must be an importable top-level function")
    if "." in function.__qualname__ or function.__name__ == "<lambda>":
        raise ValueError("trusted callable must be an importable top-level function")
    if inspect.iscoroutinefunction(function) or inspect.isgeneratorfunction(function):
        raise ValueError("trusted callable must be synchronous")
    module = sys.modules.get(function.__module__)
    if module is None or getattr(module, function.__name__, None) is not function:
        raise ValueError("trusted callable must be its module's exported function")
    return function.__module__, function.__name__


def _cleanup(process: subprocess.Popen) -> bool:
    """Bounded TERM -> KILL -> reap. Never return a late response after cleanup."""
    if process.poll() is not None:
        process.wait()
        return True
    try:
        process.terminate()
        process.wait(timeout=TERMINATE_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=KILL_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            return False
    except ProcessLookupError:
        try:
            process.wait(timeout=KILL_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            return False
    return process.poll() is not None


def run_isolated(
    trusted_callable: Callable[[object], bytes],
    payload: object,
    timeout_seconds: float,
    max_result_bytes: int,
    *,
    max_input_bytes: int = 1024 * 1024,
) -> IsolatedResult:
    """Budget covers serialization, startup, import, authentication, HTTP and result.

    The helper returns raw response bytes; no provider deserialization occurs here.
    No automatic retry. Caller must persist intent/fence and treat unknown remote
    outcomes conservatively. Lease must exceed deadline by at least 30 seconds.
    """
    started = time.monotonic()
    if not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 3600:
        raise ValueError("timeout_seconds must be finite and in (0, 3600]")
    if any(
        type(n) is not int or not 1 <= n <= MAX_JSON_BYTES
        for n in (max_input_bytes, max_result_bytes)
    ):
        raise ValueError("JSON byte limits must be in [1, 16777216]")
    deadline = started + timeout_seconds
    module, name = _callable_reference(trusted_callable)
    input_size = 0
    process = None
    cleanup_attempted = False

    def result(status, reason, *, value=None, result_bytes=0, cleanup=True):
        return IsolatedResult(
            status=status,
            reason=reason,
            value=value,
            elapsed_seconds=time.monotonic() - started,
            input_bytes=input_size,
            result_bytes=result_bytes,
            worker_pid=process.pid if process else None,
            cleanup_complete=cleanup,
        )

    try:
        encoded = _json_bytes(payload, max_input_bytes, deadline)
        input_size = len(encoded)
    except _Deadline:
        return result("deadline_exceeded", "input_serialization_deadline")
    except _JsonLimit:
        return result("worker_failed", "input_limit")
    except (ValueError, OverflowError):
        return result("worker_failed", "invalid_json_input")
    with TemporaryDirectory(prefix="specimen-effect-") as directory:
        root = Path(directory)
        try:
            (root / "input.json").write_bytes(encoded)
            # sys.path propagation supports installed/editable application modules and
            # importable test fixtures. This trusted metadata is never client-controlled.
            request = dict(
                module=module,
                name=name,
                max_result_bytes=max_result_bytes,
                deadline=deadline,
                search_path=[str(p) for p in sys.path],
            )
            (root / "request.json").write_bytes(_json_bytes(request, 65536, deadline))
            _check_deadline(deadline)
            process = subprocess.Popen(
                [sys.executable, "-m", __name__, "--worker", directory],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            # Interpreter startup/import time is inside this same deadline.
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise _Deadline
            try:
                process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                raise _Deadline from None
            _check_deadline(deadline)
            if process.returncode != 0:
                return result("worker_failed", "worker_process_exit")
            control_path = root / "control.json"
            if not control_path.is_file() or control_path.stat().st_size > 4096:
                return result("worker_failed", "invalid_worker_control")
            control = json.loads(control_path.read_bytes())
            if type(control) is not dict:
                return result("worker_failed", "invalid_worker_control")
            if control.get("status") == "output_limit":
                size = control.get("result_bytes", 0)
                size = size if type(size) is int and 0 <= size <= 2**63 - 1 else 0
                return result("output_limit", "result_limit", result_bytes=size)
            if control.get("status") == "deadline_exceeded":
                return result("deadline_exceeded", "worker_deadline")
            if control.get("status") != "completed":
                return result("worker_failed", "worker_call_failed")
            output_path = root / "output.json"
            if not output_path.is_file():
                return result("worker_failed", "missing_worker_output")
            size = output_path.stat().st_size
            if size > max_result_bytes:
                return result("output_limit", "result_limit", result_bytes=size)
            with output_path.open("rb") as stream:
                output = stream.read(max_result_bytes + 1)
            if len(output) > max_result_bytes:
                return result("output_limit", "result_limit", result_bytes=len(output))
            _check_deadline(deadline)
            return result(
                "completed", "completed", value=output, result_bytes=len(output)
            )
        except _Deadline:
            cleanup_attempted = True
            cleaned = _cleanup(process) if process else True
            return result("deadline_exceeded", "overall_deadline", cleanup=cleaned)
        except (OSError, ValueError, _JsonLimit):
            cleanup_attempted = True
            cleaned = _cleanup(process) if process else True
            return result("worker_failed", "worker_transport_failed", cleanup=cleaned)
        finally:
            if process and not cleanup_attempted and process.poll() is None:
                _cleanup(process)


def _worker(directory: str):
    root = Path(directory)
    control = {"status": "worker_failed"}
    result_size = 0
    try:
        request = json.loads((root / "request.json").read_bytes())
        sys.path[:] = request["search_path"]
        _check_deadline(request["deadline"])
        function = getattr(importlib.import_module(request["module"]), request["name"])
        payload = json.loads((root / "input.json").read_bytes())
        _check_deadline(request["deadline"])
        value = function(payload)
        _check_deadline(request["deadline"])
        if type(value) is not bytes:
            raise ValueError("helper_must_return_bytes")
        result_size = len(value)
        if result_size > request["max_result_bytes"]:
            raise _JsonLimit
        (root / "output.json").write_bytes(value)
        _check_deadline(request["deadline"])
        control = {"status": "completed"}
    except _Deadline:
        control = {"status": "deadline_exceeded"}
    except _JsonLimit:
        control = {"status": "output_limit", "result_bytes": result_size}
    except BaseException:
        # No exception strings, payloads, credential values or tracebacks cross IPC.
        pass
    (root / "control.json").write_text(json.dumps(control))


if __name__ == "__main__" and len(sys.argv) == 3 and sys.argv[1] == "--worker":
    _worker(sys.argv[2])
