"""Starting the worker job from the API (docs/execution/golive/LANE.md, T1).

The API never waits for the execution or reads its status. SQL is the only
record of work, so a failed start leaves the run queued for the next start.
"""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict


class DispatchOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["requested", "failed", "unconfigured"]
    # Only an HTTP status or an error class: never a response body or message.
    reason: str | None = None


UNCONFIGURED = DispatchOutcome(status="unconfigured")


class WorkerDispatcher(Protocol):
    def start(self) -> DispatchOutcome: ...
