"""A reading whose worker stopped before saving it is a failed reading (G6).

The workflow saves a reading's intent (``external_outcome_unknown`` and a lease)
before the call, and its result after. When the worker stops between the two (a
job's time limit, a lost instance), the lease runs out with no result saved.
That parked the run until an administrator reconciled it. A reading is a pure
read (``reliability.reader_failure_is_recoverable``), so the lost attempt is now
settled as any failed reading is: asked again within ``max_attempts``, then
ended with no observation, and the record goes to review. Every other step
still parks.

Specimen 105526322 has waited since 2026-10-09 with a reading's outcome
unknown, from a release before the reader rules. An administrator's reconcile
reads it again, and the reader rules then end a reading that keeps failing
(the last test).
"""

from datetime import datetime, timedelta, timezone

import pytest

from specimen_digitization.application.lane_reservations import step_reservation
from specimen_digitization.application.reliability import AdapterFailure
from specimen_digitization.application.workflow import LOST_READING, Workflow
from test_lane_costs import TokenAdapters, lab, ledger_total
from test_reader_failures_recoverable import step_of

UNKNOWN = "external_outcome_unknown"
MUSE = "handwriting-muse"


class WorkerStopped(BaseException):
    """The worker process ending during a call: no handler of the step runs."""


def dying_lab(tmp_path, monkeypatch, *, reading_deaths=0, segment_deaths=0):
    """A priced run whose Muse reader, or segmentation, stops the worker mid-call."""
    calls = {"muse": 0}
    kept_transcribe, kept_segment = TokenAdapters.transcribe, TokenAdapters.segment

    def transcribe(self, specimen, region, route):
        if route == MUSE:
            calls["muse"] += 1
            if calls["muse"] <= reading_deaths:
                raise WorkerStopped
        return kept_transcribe(self, specimen, region, route)

    def segment(self, specimen):
        if calls.setdefault("segment", 0) < segment_deaths:
            calls["segment"] += 1
            raise WorkerStopped
        return kept_segment(self, specimen)

    monkeypatch.setattr(TokenAdapters, "transcribe", transcribe)
    monkeypatch.setattr(TokenAdapters, "segment", segment)
    app, principal, row = lab(tmp_path)
    return app, principal, row["specimen_id"], calls


def drain_days(app, principal, specimen_id, days=12):
    """Drain once a day, as a worker that keeps being stopped would; the stored runs."""
    workflow = app.state.workflow
    now = datetime.now(timezone.utc)
    runs = []
    for day in range(days):
        workflow.clock = lambda later=now + timedelta(days=day): later
        try:
            run = workflow.drain(principal, specimen_id).run
        except WorkerStopped:
            run = workflow.repository.get(principal.scope, specimen_id).run
            assert run.blocker == UNKNOWN and run.lease_until  # The intent alone.
        runs.append(run)
        if run.stage in {"finalized", "processing_blocked"}:
            return runs
    raise AssertionError("the run did not stop: " + str(run.blocker))


def muse_calls(run):
    step = step_of(run, 1)
    return [(c["attempt"], c["outcome"], c.get("failure_code"), c["cost_basis"])
        for c in run.paid_calls if c["step"] == step]


def test_a_lost_reading_is_asked_again_instead_of_parking_the_run(tmp_path, monkeypatch):
    app, principal, specimen_id, calls = dying_lab(tmp_path, monkeypatch, reading_deaths=1)
    runs = drain_days(app, principal, specimen_id)
    lost, settled, done = runs[0], runs[1], runs[-1]
    step = step_of(done, 1)
    assert lost.attempts[step] == 1
    # The next drain after the lease settles the lost attempt as a failed
    # reading and schedules the reading again; before, it parked the run here.
    assert settled.stage == "retry_scheduled" and settled.blocker == LOST_READING
    assert settled.lease_until is None and step not in settled.completed_steps
    assert muse_calls(settled) == [(1, "failed", LOST_READING, "reserved")]
    # The call may have run to its timeout: that time is spent, not released.
    timeout = lost.profile.execution.effect_timeout_for_step(step)
    assert settled.usage.active_seconds - lost.usage.active_seconds == timeout
    assert lost.usage.reserved_active_seconds - settled.usage.reserved_active_seconds == timeout
    assert done.stage == "finalized" and done.blocker is None, done.blocker
    assert done.attempts[step] == 2 and calls["muse"] == 2
    assert sorted(o.route_id for o in done.observations) == ["handwriting-muse", "handwriting-qwen"]
    assert muse_calls(done) == [(1, "failed", LOST_READING, "reserved"), (2, "completed", None, "computed")]
    # The lost attempt stays held in full in the run's budget and the ledger.
    assert [c["cost_micros"] for c in done.paid_calls if c["step"] == step][0] == step_reservation(done, step)
    assert ledger_total(app) == done.usage.reserved_cost_micros


def test_a_reading_lost_on_its_last_attempt_ends_and_the_record_goes_to_review(tmp_path, monkeypatch):
    app, principal, specimen_id, calls = dying_lab(tmp_path, monkeypatch, reading_deaths=99)
    done = drain_days(app, principal, specimen_id)[-1]
    step = step_of(done, 1)
    assert done.stage == "finalized" and done.blocker is None, done.blocker
    assert not done.dead_letter
    assert done.attempts[step] == 3 and step in done.completed_steps
    assert calls["muse"] == 3  # Never a fourth call.
    assert [o.route_id for o in done.observations] == ["handwriting-qwen"]
    assert f"independent_observations_missing:{done.regions[0].id}" in done.reasons
    assert muse_calls(done) == [(n, "failed", LOST_READING, "reserved") for n in (1, 2, 3)]
    assert ledger_total(app) == done.usage.reserved_cost_micros


def test_a_lost_step_that_is_not_a_reading_still_parks(tmp_path, monkeypatch):
    app, principal, specimen_id, _ = dying_lab(tmp_path, monkeypatch, segment_deaths=1)
    parked = drain_days(app, principal, specimen_id)[-1]
    assert parked.stage == "processing_blocked" and parked.blocker == UNKNOWN
    assert parked.attempts == {"segment": 1}


def test_a_reconciled_reading_that_keeps_timing_out_ends_and_the_run_goes_on(tmp_path):
    # 105526322's state: a reading parked as unknown (here by an unmapped
    # error, as the reconcile tests make it). The administrator reconciles; the
    # second reading times out on every attempt, as its Muse call did.
    from test_reconcile_unknown_outcome import ROUTES, SCOPE, Readers, admin, blocked_run, operator, reconcile

    repo, blobs, blocked = blocked_run(tmp_path, "transcribe:" + ROUTES[1])
    step = f"transcribe:{blocked.run.regions[0].id}:{ROUTES[1]}"
    assert reconcile(admin(tmp_path), blocked.run, blocked.version).status_code == 200

    class TimingOut(Readers):
        def transcribe(self, specimen, region, route):
            self.calls.append("transcribe:" + route)
            raise AdapterFailure("provider_deadline_outcome_unknown", outcome_unknown=True)

    readers = TimingOut(blobs)
    now = datetime.now(timezone.utc)
    for day in range(1, 6):
        workflow = Workflow(repo, blobs, readers, clock=lambda later=now + timedelta(days=day): later)
        run = workflow.drain(operator(), blocked.id).run
        if run.stage != "retry_scheduled":
            break
    assert readers.calls == ["transcribe:" + ROUTES[1]] * 2
    assert run.attempts[step] == 3 and step in run.completed_steps
    assert run.blocker != UNKNOWN and "adjudicate" in run.completed_steps, run.blocker
    assert [o.route_id for o in run.observations] == [ROUTES[0]]
    assert repo.get(SCOPE, blocked.id).run.blocker != UNKNOWN


def test_a_reading_the_ledger_settled_before_its_worker_stopped_keeps_that_cost(tmp_path, monkeypatch):
    # The worker read the label, settled the program ledger to the reading's
    # cost, and stopped before saving the run (review of c15d4f73).
    from specimen_digitization.application import active_graph

    app, principal, specimen_id, calls = dying_lab(tmp_path, monkeypatch)
    kept_save, stopped = active_graph.save_recoverably, []

    def save(repository, principal, specimen, revision, key, value):
        if (key.startswith("result:") and not stopped
                and any(o.route_id == MUSE for o in specimen.run.observations)):
            stopped.append(key)
            raise WorkerStopped
        return kept_save(repository, principal, specimen, revision, key, value)

    monkeypatch.setattr(active_graph, "save_recoverably", save)
    runs = drain_days(app, principal, specimen_id)
    settled, done = runs[1], runs[-1]
    step = step_of(done, 1)
    assert stopped and calls["muse"] == 2
    assert settled.stage == "retry_scheduled" and settled.blocker == LOST_READING
    first = [c for c in done.paid_calls if c["step"] == step][0]
    assert (first["attempt"], first["outcome"], first["failure_code"], first["cost_basis"]) == (
        1, "failed", LOST_READING, "computed")
    assert first["cost_micros"] == 900  # The Muse reading's cost in this lab.
    assert done.stage == "finalized" and done.attempts[step] == 2
    assert ledger_total(app) == done.usage.reserved_cost_micros
