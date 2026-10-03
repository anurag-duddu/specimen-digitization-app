#!/usr/bin/env python3
"""Start a SAM 3 instance before a worker execution, so the worker's first segmentation call meets a loaded model.

    uv run --frozen python scripts/ops/warm_sam.py

A cold SAM 3 start (hash and load of the 3.4 GB checkpoint) can outlast the worker's 270 s segmentation call. This
sends an authenticated GET to <SAM_URL>/health/live, which answers only once the model is loaded, and retries until
it returns 200 or WARM_TIMEOUT_SECONDS (default 900) pass. An idle instance then stays for roughly 15 minutes.
Safe to repeat: a warm instance answers at once.

The identity token is the caller's own (`gcloud auth print-identity-token`), held in this process and never
printed. The caller needs run.routes.invoke on specimen-sam (the project owner has it; for a service account, grant
roles/run.invoker on the service). A service-account caller gets a token for the SAM URL as its audience.

Parameters (environment): SAM_URL (default runtime_settings.SAM_URL), WARM_TIMEOUT_SECONDS, DRY_RUN=1.
"""
from __future__ import annotations

import sys
import time
import urllib.error
import urllib.request

import ops_common as ops

PATH = "/health/live"  # sam3_server.create_app; the app itself does not authenticate this path.
# A request waiting for an instance pends for up to 3.5 times the service's average startup time or 10 s, whichever
# is greater, then fails with 429 (docs.cloud.google.com/run/docs/about-instance-autoscaling; "no available instance"
# in docs.cloud.google.com/run/docs/troubleshooting). The loop below retries a 429 like any status but 200, 401, 403.
ATTEMPT_SECONDS = 330  # Longer than the service's 300 s request timeout.


def token_argv(url: str) -> list[str]:
    account = ops.read(["gcloud", "config", "get-value", "account"]) or ""
    audience = [f"--audiences={url}"] if account.strip().endswith(".gserviceaccount.com") else []
    return ["gcloud", "auth", "print-identity-token", *audience]


def get(url: str, token: str) -> int:
    request = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(request, timeout=ATTEMPT_SECONDS) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0


def main() -> int:
    base = ops.param("SAM_URL", ops.settings.SAM_URL).rstrip("/")
    budget = int(ops.param("WARM_TIMEOUT_SECONDS", "900"))
    token = ops.secret_value(token_argv(base))
    ops.note(f"GET {base}{PATH} with the caller's identity token, until 200 or {budget} s")
    if ops.dry_run():
        return 0
    deadline = time.monotonic() + budget
    while True:
        status = get(base + PATH, token)
        if status == 200:
            ops.note("SAM 3 is warm")
            return 0
        if status in {401, 403}:
            raise SystemExit(f"SAM 3 refused the caller ({status}); it needs run.routes.invoke on specimen-sam")
        if time.monotonic() > deadline:
            raise SystemExit(f"SAM 3 was not warm within {budget} s (last status {status or 'no response'})")
        ops.note(f"not warm yet (status {status or 'no response'}); retrying")
        time.sleep(10)


if __name__ == "__main__":
    sys.exit(main())
