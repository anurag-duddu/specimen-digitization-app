"""Start one execution of the worker job (docs/execution/golive/LANE.md, T1).

The API never waits for the execution or reads its status. SQL is the only
record of work, so a failed start leaves the run queued for the next start.
"""

from __future__ import annotations

import re
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

RUN_API = "https://run.googleapis.com/v2/"
JOB_NAME = re.compile(
    r"projects/[a-z][a-z0-9-]{4,28}[a-z0-9]"
    r"/locations/[a-z][a-z0-9-]{1,30}[a-z0-9]"
    r"/jobs/[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?"
)


class DispatchOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["requested", "failed", "unconfigured"]
    # Only an HTTP status or an error class: never a response body or message.
    reason: str | None = None


UNCONFIGURED = DispatchOutcome(status="unconfigured")


class WorkerDispatcher(Protocol):
    def start(self) -> DispatchOutcome: ...


class CloudRunJobDispatcher:
    """Cloud Run Admin API v2 `jobs:run`, with no overrides."""

    def __init__(self, job: str, *, session=None, timeout_seconds: float = 10):
        if not JOB_NAME.fullmatch(job):
            raise ValueError("Worker job must be projects/*/locations/*/jobs/*")
        self.job = job
        self.timeout_seconds = timeout_seconds
        self._session = session

    def session(self):
        if self._session is None:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession

            credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            self._session = AuthorizedSession(credentials)
        return self._session

    def start(self) -> DispatchOutcome:
        try:
            response = self.session().post(
                RUN_API + self.job + ":run", json={}, timeout=self.timeout_seconds
            )
        except Exception as exc:  # A start is best effort; the run stays queued.
            return DispatchOutcome(status="failed", reason=type(exc).__name__)
        if 200 <= response.status_code < 300:
            return DispatchOutcome(status="requested")
        return DispatchOutcome(status="failed", reason=f"http_{response.status_code}")


def dispatcher_from_value(value: str | None) -> CloudRunJobDispatcher | None:
    """`SPECIMEN_WORKER_JOB`: absent or empty means no worker can be started."""
    return CloudRunJobDispatcher(value) if value else None
