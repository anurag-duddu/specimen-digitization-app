"""Approved fixed-clock timing, exercised with generated local fixtures only."""

from datetime import timedelta
import pytest

from specimen_digitization.application.worker_launch import PilotLaunch
from specimen_digitization.application.workflow import OperationalBlock
from specimen_digitization.application.worker_deadline import WorkerDeadlineExceeded
from specimen_digitization.release_budget import APPROVAL_SHA256
from test_dynamic_pilot_reservations import dynamic_cohort, ledger
from test_cohort_reading_barrier import segment_all


def approved_cohort(tmp_path, monkeypatch):
    c = dynamic_cohort(tmp_path, monkeypatch)
    origin = int(c.clock[0].timestamp())
    c.clock[0] = c.clock[0].replace(microsecond=0)
    data = c.launch.model_dump(mode="json")
    data["timing"] = {
        "version": "approved-worker-timing/v1", "approval_sha256": APPROVAL_SHA256,
        "dispatch_started_at_unix": origin, "sam_expires_at_unix": origin + 2200,
    }
    data["expires_at"] = (c.clock[0] + timedelta(seconds=3500)).isoformat()
    validated = PilotLaunch.model_validate(data)
    # assemble closes over the original launch instance.
    c.launch.__dict__.update(validated.__dict__)
    c.worker, c.flow = c.assemble(c.repo)
    return c, origin


def test_startup_and_restart_cannot_replace_original_dispatch_clock(tmp_path, monkeypatch):
    c, origin = approved_cohort(tmp_path, monkeypatch)
    c.clock[0] += timedelta(seconds=300)
    c.flow.admission.bind_execution_window(3485)
    original = ledger(c)["execution_window"]
    assert original["started_at_unix"] == origin
    assert original["deadline_unix"] == origin + 3485
    c.clock[0] += timedelta(seconds=100)
    c.worker, c.flow = c.assemble(c.repo)
    c.flow.admission.bind_execution_window(3485)
    assert ledger(c)["execution_window"] == original


def test_slow_startup_blocks_complete_sam_phase_before_any_effect(tmp_path, monkeypatch):
    c, _ = approved_cohort(tmp_path, monkeypatch)
    c.clock[0] += timedelta(seconds=400)
    item = c.repo.get(c.launch.scope, c.launch.specimens[0].specimen_id)
    with pytest.raises(OperationalBlock, match="sam.*time"):
        c.flow.admission.admit(item)
    assert not c.events


def test_only_atomic_admitted_readers_continue_after_original_sam_expiry(tmp_path, monkeypatch):
    c, origin = approved_cohort(tmp_path, monkeypatch)
    segment_all(c)
    held = c.flow.admission.reserve_cohort_readings()
    phase = ledger(c)["sam_phase"]
    assert phase["state"] == "readers"
    assert phase["identity_sha256"] == held["identity_sha256"]
    c.clock[0] += timedelta(seconds=2201)
    for binding in c.launch.specimens:
        for _ in range(3):
            c.flow.step(c.principal, binding.specimen_id)
    assert len([event for event in c.events if event[0] == "read"]) == 20
    assert c.worker.result_summary()["counts"] == {"review_required": 10}
    assert ledger(c)["execution_window"]["deadline_unix"] == origin + 3485


def test_late_all_region_cas_cannot_be_adopted_as_reader_phase(tmp_path, monkeypatch):
    c, _ = approved_cohort(tmp_path, monkeypatch)
    segment_all(c)
    write = c.repo.put_document

    def late(scope, kind, ident, value, revision):
        result = write(scope, kind, ident, value, revision)
        if "reading_cohort" in value:
            c.clock[0] += timedelta(seconds=2201)
        return result

    monkeypatch.setattr(c.repo, "put_document", late)
    with pytest.raises(WorkerDeadlineExceeded):
        c.flow.admission.reserve_cohort_readings()
    c.worker, c.flow = c.assemble(c.repo)
    with pytest.raises(OperationalBlock, match="phase.*unknown"):
        c.flow.admission.reserve_cohort_readings()
    assert not any(event[0] == "read" for event in c.events)


def test_supervisor_is_anchored_before_materialization(tmp_path, monkeypatch, capsys):
    from types import SimpleNamespace
    from specimen_digitization.application import worker, bounded_effect

    c, origin = approved_cohort(tmp_path, monkeypatch)
    monkeypatch.setenv("SPECIMEN_WORKER_TIMING", c.launch.timing.model_dump_json())
    monkeypatch.setattr(worker, "time", SimpleNamespace(time=lambda: origin + 300, monotonic=lambda: 1000))
    calls = []

    def supervise(function, payload, timeout, maximum, **kwargs):
        calls.append((timeout, kwargs))
        return SimpleNamespace(status="deadline_exceeded", cleanup_complete=True)

    monkeypatch.setattr(bounded_effect, "run_isolated", supervise)
    with pytest.raises(SystemExit) as exit_code:
        worker._supervise(SimpleNamespace(max_seconds=3485))
    assert exit_code.value.code == 2
    assert calls == [(3485, {"process_group": True, "deadline_monotonic": 4185, "cleanup_until": 4200})]
    assert '"status": "incomplete"' in capsys.readouterr().out


def test_reader_phase_cannot_return_to_sam_or_gain_time_from_wall_rollback(tmp_path, monkeypatch):
    c, origin = approved_cohort(tmp_path, monkeypatch)
    segment_all(c)
    c.flow.admission.reserve_cohort_readings()
    item = c.repo.get(c.launch.scope, c.launch.specimens[0].specimen_id)
    item.run.completed_steps.remove("segment")
    with pytest.raises(OperationalBlock, match="return_to_sam"):
        c.flow.admission.assert_sam_dispatch(item)
    c.clock[0] += timedelta(seconds=3486)
    observed = c.flow.admission.timing_now()
    c.clock[0] -= timedelta(seconds=3000)
    assert c.flow.admission.timing_now() >= observed > origin + 3485
    with pytest.raises(WorkerDeadlineExceeded):
        c.flow.admission.save_summary({"status": "completed"})


def test_actual_twenty_five_regions_use_both_readers_under_original_window(tmp_path, monkeypatch):
    from specimen_digitization.application.domain import Region
    from test_worker_parent_deadline import FakeStop, fake_worker_clock

    c, origin = approved_cohort(tmp_path, monkeypatch)
    c.launch.total_cost_limit_micros = 3870
    c.worker, c.flow = c.assemble(c.repo)
    segment = c.flow.adapters.segment
    last_five = {item.specimen_id for item in c.launch.specimens[5:]}

    def sam(item):
        c.flow.admission.assert_sam_dispatch(item)
        result = segment(item)
        for n in range(1, 3 if item.id in last_five else 2):
            result.append(Region(asset_id=item.asset.id, x=n, y=0, width=50, height=50,
                                 order=n, method="sam3", version="generated-local-fixture"))
        c.clock[0] += timedelta(seconds=120)
        return result

    read = c.flow.adapters.production.transcribe

    def reader(*args):
        result = read(*args)
        c.clock[0] += timedelta(seconds=30)
        return result

    c.flow.adapters.segment = sam
    c.flow.adapters.production.transcribe = reader
    fake_worker_clock(c, monkeypatch)
    # This is a feasible bounded schedule, not a worst-case native startup claim.
    c.clock[0] += timedelta(seconds=50)
    c.worker.run(FakeStop(c.clock), max_seconds=3485)
    assert c.worker.result_summary()["counts"] == {"review_required": 10}, set(c.worker.health.blocked_scopes.values())
    reads = [event for event in c.events if event[0] == "read"]
    assert len(reads) == len(set(reads)) == 50
    assert ledger(c)["reading_cohort"]["region_count"] == 25
    assert ledger(c)["execution_window"]["deadline_unix"] == origin + 3485
    assert c.clock[0].timestamp() <= origin + 3485


def test_cleanup_reaping_cannot_add_time_after_original_absolute_end(monkeypatch):
    import os
    import signal
    from types import SimpleNamespace
    from specimen_digitization.application import bounded_effect

    clock, waited = [100.0], []

    def no_child(*args):
        raise ChildProcessError

    def group(pid, signum):
        if signum == 0:
            raise ProcessLookupError
        assert signum == signal.SIGKILL

    def wait(timeout):
        waited.append(timeout)
        clock[0] += timeout + 0.001

    monkeypatch.setattr(bounded_effect, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(bounded_effect, "os", SimpleNamespace(killpg=group, waitpid=no_child, WNOHANG=os.WNOHANG))
    process = SimpleNamespace(pid=424242, wait=wait)
    assert not bounded_effect._cleanup(process, process_group=True, cleanup_until=100.1)
    assert waited == [pytest.approx(0.1)]
