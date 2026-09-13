"""The deployed worker must honor the admitted serial reading schedule."""

from datetime import timedelta
from types import SimpleNamespace

import pytest

from specimen_digitization.application.storage import digest
from test_dynamic_pilot_reservations import dynamic_cohort, ledger
from test_cohort_reading_barrier import segment_all


@pytest.mark.parametrize("reader_timeout", [30, 45, 60])
def test_admitted_uneven_cohort_finishes_within_its_retained_window(
    tmp_path, monkeypatch, reader_timeout
):
    import specimen_digitization.application.worker as module

    c = dynamic_cohort(tmp_path, monkeypatch, reader_timeout=reader_timeout)
    segment_all(c)
    reading_seconds = 15 + 22 * (reader_timeout + 1)
    assert c.flow.admission.reserve_cohort_readings()["reading_seconds"] == reading_seconds
    window = dict(ledger(c)["execution_window"])
    c.clock[0] += timedelta(seconds=1500 - reading_seconds - 1)
    origin = c.clock[0]
    reader = c.flow.adapters.production.transcribe

    def bounded_reader(*args):
        result = reader(*args)
        c.clock[0] += timedelta(seconds=reader_timeout)
        return result

    c.flow.adapters.production.transcribe = bounded_reader
    monkeypatch.setattr(
        module,
        "time",
        SimpleNamespace(monotonic=lambda: (c.clock[0] - origin).total_seconds()),
    )
    summaries = []
    summarize = c.worker.result_summary

    def record_summary():
        summaries.append(c.worker.rotation)
        return summarize()

    monkeypatch.setattr(c.worker, "result_summary", record_summary)

    class Stop:
        waits = 0

        def is_set(self):
            return False

        def wait(self, seconds):
            self.waits += 1
            assert self.waits < 100
            c.clock[0] += timedelta(seconds=seconds)

    c.worker.run(Stop(), max_seconds=1500)
    # Keep the same four summary operations as the old ten-tick cadence, moving
    # its final summary to completion instead of adding a read on every tick.
    assert summaries == [10, 20, 30, 32]
    reads = [event for event in c.events if event[0] == "read"]
    assert len(reads) == len(set(reads)) == 22
    assert c.worker.result_summary()["counts"] == {"review_required": 10}
    assert ledger(c)["execution_window"] == window
    assert c.clock[0].timestamp() <= window["deadline_unix"]


def test_completed_review_row_remains_in_all_cohort_checks(tmp_path, monkeypatch):
    c = dynamic_cohort(tmp_path, monkeypatch)
    segment_all(c)
    completed_id = c.launch.specimens[0].specimen_id
    for _ in range(3):
        c.flow.step(c.principal, completed_id)
    completed = c.repo.get(c.launch.scope, completed_id)
    assert completed.run.blocker == "pilot_evidence_review_required"
    completed.run.regions[0].x += 1
    c.repo.save(c.principal, completed, completed.version, "tamper", digest("tamper"))
    before = list(c.events)
    c.worker.tick()
    assert c.events == before
    assert c.worker.result_summary()["status"] != "evidence_review_required"
    assert c.worker.health.blocked_scopes


def test_already_completed_cohort_does_not_wait_for_rotation(tmp_path, monkeypatch):
    c = dynamic_cohort(tmp_path, monkeypatch)
    segment_all(c)
    for binding in c.launch.specimens:
        item = c.repo.get(c.launch.scope, binding.specimen_id)
        for _ in range(2 * len(item.run.regions) + 1):
            c.flow.step(c.principal, binding.specimen_id)
    before = list(c.events)

    class Stop:
        def is_set(self):
            return False

        def wait(self, seconds):
            pytest.fail("A completed cohort must return before another polling wait")

    c.worker.run(Stop(), max_seconds=1500)
    assert c.events == before
    assert c.worker.result_summary()["counts"] == {"review_required": 10}
