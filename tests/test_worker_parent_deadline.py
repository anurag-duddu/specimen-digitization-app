"""Desired deadline behavior; RED demonstrates current late parent dispatch."""

from datetime import timedelta
from types import SimpleNamespace

from test_dynamic_pilot_reservations import dynamic_cohort


def test_parent_io_cannot_start_new_mutations_after_original_deadline(tmp_path, monkeypatch):
    import specimen_digitization.application.worker as module

    c = dynamic_cohort(tmp_path, monkeypatch)
    origin = c.clock[0]
    monkeypatch.setattr(module, "time", SimpleNamespace(
        monotonic=lambda: (c.clock[0]-origin).total_seconds()))
    memberships = c.worker.membership_loader

    def delayed_membership(uid):
        c.clock[0] += timedelta(seconds=1501)
        return memberships(uid)

    c.worker.membership_loader = delayed_membership
    dispatches = []
    write = c.repo.put_document

    def recorded_write(*args, **kwargs):
        dispatches.append((c.clock[0]-origin).total_seconds())
        return write(*args, **kwargs)

    monkeypatch.setattr(c.repo, "put_document", recorded_write)

    class Stop:
        def is_set(self):
            return False

        def wait(self, seconds):
            c.clock[0] += timedelta(seconds=seconds)

    c.worker.run(Stop(), max_seconds=1500)
    assert dispatches == [0], "No mutation may be dispatched after retained deadline"


class FakeStop:
    def __init__(self, clock):
        self.clock = clock

    def is_set(self):
        return False

    def wait(self, seconds):
        self.clock[0] += timedelta(seconds=seconds)


def fake_worker_clock(c, monkeypatch):
    from specimen_digitization.application import worker

    origin = c.clock[0]
    monkeypatch.setattr(worker, "time", SimpleNamespace(
        monotonic=lambda: (c.clock[0] - origin).total_seconds()))
    return origin


def test_late_dispatch_acknowledgement_retains_fence_and_never_replays(tmp_path, monkeypatch):
    from test_dynamic_pilot_reservations import ledger

    c = dynamic_cohort(tmp_path, monkeypatch)
    fake_worker_clock(c, monkeypatch)
    sent = []

    def late_step(*args):
        sent.append(args[1])
        c.clock[0] += timedelta(seconds=1501)
        raise RuntimeError("unknown remote outcome")

    c.worker.workflow.step = late_step
    c.worker.run(FakeStop(c.clock), max_seconds=1500)
    retained = ledger(c)
    assert len(sent) == 1
    assert retained["dispatches"]
    assert c.worker.result_summary()["status"] == "incomplete"
    assert ledger(c) == retained  # No late summary or cleanup mutation.
    restarted, flow = c.assemble(c.repo)
    flow.step = late_step
    restarted.run(FakeStop(c.clock), max_seconds=1500)
    assert len(sent) == 1
    assert ledger(c) == retained


def test_retained_window_tightens_restart_before_late_membership(tmp_path, monkeypatch):
    from test_dynamic_pilot_reservations import ledger

    c = dynamic_cohort(tmp_path, monkeypatch)
    c.flow.admission.bind_execution_window(1500)
    original = ledger(c)
    c.clock[0] += timedelta(seconds=1499)
    fake_worker_clock(c, monkeypatch)
    loader = c.worker.membership_loader

    def late_membership(uid):
        c.clock[0] += timedelta(seconds=2)
        return loader(uid)

    c.worker.membership_loader = late_membership
    c.worker.run(FakeStop(c.clock), max_seconds=1500)
    assert not c.events
    assert ledger(c) == original
    assert c.worker.result_summary()["counts"] == {"unavailable": 10}


def test_late_final_membership_cannot_persist_success(tmp_path, monkeypatch):
    from specimen_digitization.application.worker_deadline import WorkerDeadline
    from test_dynamic_pilot_reservations import ledger

    c = dynamic_cohort(tmp_path, monkeypatch)
    c.flow.admission.bind_execution_window(1500)
    before = ledger(c)
    origin = fake_worker_clock(c, monkeypatch)
    c.worker.deadline = WorkerDeadline(1500, monotonic=lambda: (c.clock[0]-origin).total_seconds())
    loader = c.worker.membership_loader

    def late(uid):
        c.clock[0] += timedelta(seconds=1501)
        return loader(uid)

    c.worker.membership_loader = late
    assert c.worker.result_summary()["status"] == "incomplete"
    assert ledger(c) == before


def test_sql_late_response_is_unknown_and_cannot_dispatch_next_mutation():
    import pytest
    from specimen_digitization.application.production import SqlConnectRepository
    from specimen_digitization.application.worker_deadline import WorkerDeadline, WorkerDeadlineExceeded

    clock, calls = [0], []

    def post(*args, **kwargs):
        calls.append("sent")
        clock[0] = 11
        return SimpleNamespace(status_code=200, json=lambda: calls.append("decoded"))

    repo = SqlConnectRepository(session=SimpleNamespace(post=post))
    with WorkerDeadline(10, monotonic=lambda: clock[0]).scope():
        with pytest.raises(WorkerDeadlineExceeded):
            repo.execute("CreateDocumentV2", {}, mutation=True)
        with pytest.raises(WorkerDeadlineExceeded):
            repo.execute("CreateDocumentV2", {}, mutation=True)
    assert calls == ["sent"]


def test_late_gcs_precondition_does_not_start_fallback_or_reload():
    import pytest
    from google.api_core.exceptions import PreconditionFailed
    from specimen_digitization.application.production import GcsBlobs
    from specimen_digitization.application.worker_deadline import WorkerDeadline, WorkerDeadlineExceeded

    clock, calls = [0], []

    def upload(*args, **kwargs):
        calls.append("sent")
        clock[0] = 11
        raise PreconditionFailed("late synthetic response")

    blob = SimpleNamespace(upload_from_string=upload,
                           download_as_bytes=lambda: calls.append("download"),
                           reload=lambda: calls.append("reload"))
    blobs = object.__new__(GcsBlobs)
    blobs.bucket = SimpleNamespace(blob=lambda name: blob)
    with WorkerDeadline(10, monotonic=lambda: clock[0]).scope():
        with pytest.raises(WorkerDeadlineExceeded):
            blobs.put(b"synthetic")
    assert calls == ["sent"]


def test_late_accepted_fence_write_is_not_retried_or_dispatched(tmp_path, monkeypatch):
    from test_dynamic_pilot_reservations import ledger

    c = dynamic_cohort(tmp_path, monkeypatch)
    fake_worker_clock(c, monkeypatch)
    writes, dispatched = [], []
    write = c.repo.put_document

    def accepted_late(scope, kind, ident, payload, expected):
        result = write(scope, kind, ident, payload, expected)
        writes.append(payload)
        if payload.get("dispatches"):
            c.clock[0] += timedelta(seconds=1501)
        return result

    monkeypatch.setattr(c.repo, "put_document", accepted_late)
    c.worker.workflow.step = lambda *args: dispatched.append(args)
    c.worker.run(FakeStop(c.clock), max_seconds=1500)
    assert not dispatched
    assert len([payload for payload in writes if payload.get("dispatches")]) == 1
    retained = ledger(c)
    assert retained["dispatches"]
    assert c.worker.result_summary()["status"] == "incomplete"
    assert ledger(c) == retained
