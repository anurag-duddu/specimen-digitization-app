"""Trusted process-isolated HTTP reads with bounded raw bytes and whole-call time."""

import base64
import json
from urllib.parse import urlsplit

import httpx

from .bounded_effect import run_isolated


def _http_read(payload):
    """Child entry point; caller supplies only a server-approved fixed endpoint."""
    url = urlsplit(payload["url"])
    if (
        url.username
        or url.password
        or url.fragment
        or url.scheme not in {"https", "http"}
        or (url.scheme == "http" and url.hostname != "127.0.0.1")
    ):
        raise ValueError("Unsupported HTTP destination")
    limit = payload["max_bytes"]
    if not 0 < limit <= 1024 * 1024:
        raise ValueError("Invalid response bound")
    body = bytearray()
    headers = {**(payload.get("headers") or {}), "Accept-Encoding": "identity"}
    with httpx.Client(
        follow_redirects=False, timeout=httpx.Timeout(payload["timeout_seconds"])
    ) as client:
        with client.stream(
            payload.get("method", "GET"),
            payload["url"],
            params=payload.get("params"),
            data=payload.get("data"),
            headers=headers,
        ) as response:
            truncated = False
            for chunk in response.iter_raw(chunk_size=8192):
                available = limit - len(body)
                body.extend(chunk[:available])
                if len(chunk) > available:
                    truncated = True
                    break
            encoded = response.headers.get("content-encoding", "identity").lower()
            return json.dumps(
                {
                    "status_code": response.status_code,
                    "body_base64": base64.b64encode(body).decode(),
                    "retry_after": response.headers.get("retry-after", ""),
                    "truncated": truncated,
                    "unsupported_encoding": encoded not in {"", "identity"},
                },
                separators=(",", ":"),
            ).encode()


def http_read(payload):
    try:
        return _http_read(payload)
    except httpx.TimeoutException:
        failure = "timeout"
    except httpx.HTTPError:
        failure = "provider_error"
    return json.dumps(
        {
            "status_code": None,
            "body_base64": "",
            "retry_after": "",
            "truncated": False,
            "unsupported_encoding": False,
            "failure": failure,
        }
    ).encode()


def bounded_http(
    url,
    *,
    timeout_seconds,
    max_bytes,
    method="GET",
    params=None,
    data=None,
    headers=None,
    effect=None,
):
    result = run_isolated(
        effect or http_read,
        {
            "url": url,
            "timeout_seconds": timeout_seconds,
            "max_bytes": max_bytes,
            "method": method,
            "params": params,
            "data": data,
            "headers": headers,
        },
        timeout_seconds,
        2 * 1024 * 1024,
    )
    if result.status != "completed" or not result.cleanup_complete:
        return {
            "status_code": None,
            "body": b"",
            "retry_after": "",
            "truncated": False,
            "failure": "timeout"
            if result.status == "deadline_exceeded"
            else "provider_error",
            "cleanup_complete": result.cleanup_complete,
            "worker_pid": result.worker_pid,
            "elapsed_seconds": result.elapsed_seconds,
        }
    value = json.loads(result.value)
    value["body"] = base64.b64decode(value.pop("body_base64"), validate=True)
    if len(value["body"]) > max_bytes:
        raise ValueError("Child response exceeded declared byte bound")
    value.setdefault("failure", None)
    value["cleanup_complete"] = True
    value["worker_pid"] = result.worker_pid
    value["elapsed_seconds"] = result.elapsed_seconds
    return value
