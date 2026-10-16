"""Require expiry at the I/O boundary without a later guarded operation."""

import pytest

from specimen_digitization.application.worker_deadline import (
    WorkerDeadline,
    WorkerDeadlineExceeded,
    deadline_call,
)


@pytest.mark.parametrize("outcome", ("success", "error"))
def test_deadline_call_rejects_late_result_or_error(outcome):
    now = 0
    calls = []

    def late_io():
        nonlocal now
        calls.append(outcome)
        now = 11
        if outcome == "error":
            raise RuntimeError("late SDK error must not escape deadline_call")
        return "late SDK result must not escape deadline_call"

    with WorkerDeadline(10, monotonic=lambda: now).scope():
        # Nothing after this call checks the deadline: the wrapper itself must
        # replace both the late response and the late error with expiry.
        with pytest.raises(WorkerDeadlineExceeded):
            deadline_call(late_io)

    assert calls == [outcome], "The I/O must run once before expiry is observed"


@pytest.mark.parametrize("outcome", ("success", "error"))
def test_deadline_call_preserves_timely_result_or_error(outcome):
    now = 0
    result = object()
    error = RuntimeError("timely SDK error")
    calls = []

    def timely_io():
        nonlocal now
        calls.append(outcome)
        now = 9
        if outcome == "error":
            raise error
        return result

    with WorkerDeadline(10, monotonic=lambda: now).scope():
        if outcome == "error":
            with pytest.raises(RuntimeError) as caught:
                deadline_call(timely_io)
            assert caught.value is error, "Preserve the original timely SDK error"
        else:
            assert deadline_call(timely_io) is result, "Preserve the timely SDK result"

    assert calls == [outcome], "The wrapper must invoke the timely I/O exactly once"
