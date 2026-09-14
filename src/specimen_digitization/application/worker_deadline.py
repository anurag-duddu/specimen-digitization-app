"""One non-renewable worker deadline, including parent I/O and finalization.

Expiry deliberately bypasses ordinary workflow error handlers: an already-sent
request has an unknown outcome and must not trigger cleanup writes or replay.
The production process supervisor also enforces this clock during blocking I/O.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import time


class WorkerDeadlineExceeded(BaseException):
    pass


_active = ContextVar("worker_operation_deadline", default=None)


class WorkerDeadline:
    def __init__(self, deadline, *, monotonic=time.monotonic, publish=None):
        self.deadline = deadline
        self.monotonic = monotonic
        self.publish = publish

    def remaining(self):
        return self.deadline - self.monotonic()

    def check(self):
        if self.remaining() <= 0:
            raise WorkerDeadlineExceeded

    def tighten_until(self, deadline_unix, current_unix):
        self.deadline = min(
            self.deadline, self.monotonic() + deadline_unix - current_unix
        )
        if self.publish is not None:
            self.publish(self.deadline)
        self.check()

    @contextmanager
    def scope(self):
        token = _active.set(self)
        try:
            self.check()
            yield self
        finally:
            _active.reset(token)


def current_deadline():
    return _active.get()


def check_deadline():
    deadline = current_deadline()
    if deadline is not None:
        deadline.check()


def deadline_call(function, *args, **kwargs):
    check_deadline()
    try:
        return function(*args, **kwargs)
    finally:
        # Also replace a late SDK error with expiry before generic handlers can
        # issue a blocker/checkpoint mutation. Never expose the late response.
        check_deadline()


def guarded(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        return deadline_call(function, *args, **kwargs)

    return wrapped
