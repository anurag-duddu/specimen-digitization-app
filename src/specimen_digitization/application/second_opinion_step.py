"""The workflow step `field_second_opinion` (field_research/second_opinion.py): its lifecycle.

WHERE IT SITS. Field research finalizes the record in memory (its step, or its recheck when a
completed run reaches the handover again). When that leaves the run finalized, with no retryable
research failure pending and nothing further to ask, and a value the second opinion answers for has
no recorded verdict for its current value (`second_opinion.due`), the workflow does not finalize the
record yet: `mark_due` sets the run's stage to the step and its disposition to none, in the same
save. The next workflow step runs it (`run_step`), and it finalizes the record (second_opinion.finish).

THE STEP IS OPTIONAL: every way it can go wrong ends it "not obtained" with a code and the record is
finalized with the stage and blocker field research gave it (finalized, none) and the not-checked
marks derived from the current values; and it obeys every guard a mandatory paid step obeys. A
mandatory paid step that cannot be afforded, fails, times out or loses its outcome blocks the run
(processing_blocked, a retry scheduled, or a person's attention); this one never does.

ITS LIFECYCLE is a paid step's:
- Guards before anything is reserved (`_refusal`): its attempts, the run's limits on steps, external
  calls, reserved tokens (RESERVED_TOKENS, as a mandatory paid step reserves) and active time, a price
  row, the cost ceiling with the retained research liabilities. Then the reservations (the retained
  research cost, any monthly cap, the program's allowance), all inside one handler: any refusal or
  error there releases what the monthly caps held (tenant_budget.release_unsent, settled at zero once
  saved) and ends it not obtained ("budget"), so nothing is retried in a loop.
- The intent, saved before the request: the stored result's status `asking`, the attempt, a lease,
  the reserved cost, tokens and time. It sets no blocker: an open intent is never an unknown external
  outcome that blocks. Whatever else finalizes the run meanwhile (a person's decision or approval,
  research again) abandons it first (second_opinion.abandon, from step.finalize_fields): not obtained,
  "abandoned", its whole reservation held as for any call whose outcome is unknown. If the step's own
  result then loses its save, it reads the record again and leaves it as that finalize left it.
- The request, inside the step's deadline: the profile's external timeout, at most TIMEOUT_SECONDS, and
  the worker's deadline less research's margin. Reading the crops runs in a worker thread waited for
  until the deadline, the request and the client's closing are each cut at it (second_opinion.obtain,
  bounded, ask). A malformed answer is asked again once inside the same deadline and reservation.
- The result: its paid call recorded under its own route and settled to what the provider reported
  (lane_costs.settle_step), or held in full when that is not known; the reported tokens counted. A
  result that would pass the record's size limit is not stored: "not obtained: result_too_large".
- A lost outcome (the worker's deadline, a crash, the result's save failing) is found by the next
  workflow step once the lease ends: not obtained "outcome_unknown", its reservation held, and the
  record finalized. Each attempt sends at most one request, or two when the first answer is
  malformed; a lost one is not repeated.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .domain import AuditEvent
from .storage import digest


def mark_due(run) -> None:
    """After field research's step or recheck: when research left the run finalized and the second
    opinion is due, the record waits for it (stage `field_second_opinion`, no disposition)."""
    from ..field_research import second_opinion

    if run.stage == "finalized" and second_opinion.due(run):
        run.stage, run.disposition = second_opinion.STEP, None


def _refusal(workflow, principal, specimen, cost: int, timeout: float) -> str | None:
    """Why the step makes no request, before anything is reserved, or None."""
    from ..field_research import second_opinion
    from .workflow import attempts_used

    run = specimen.run
    policy = run.profile.execution
    if attempts_used(run, second_opinion.STEP) >= policy.max_attempts:
        return "attempts_used"
    tokens = 0 if run.profile.synthetic else second_opinion.RESERVED_TOKENS
    if (run.usage.steps >= policy.max_steps or run.usage.external_calls + 1 > policy.max_external_calls
            or run.usage.reserved_tokens + tokens > policy.max_tokens
            or run.usage.active_seconds + run.usage.reserved_active_seconds + timeout > policy.max_active_seconds):
        return "run_limit"
    if second_opinion.route_price(run) is None or policy.price_list is None:
        return "unconfigured"
    if run.profile.synthetic:
        return None
    if policy.approved_cost_limit_micros is None:
        return "budget"
    retained = 0
    if workflow.retained_cost is not None:
        try:
            retained = workflow.retained_cost(principal, specimen)
        except Exception:  # noqa: BLE001 - an unreadable state establishes no headroom
            return "budget"
        if type(retained) is not int or retained < 0:
            return "budget"
    if run.usage.reserved_cost_micros + retained + cost > policy.approved_cost_limit_micros:
        return "budget"
    return None


def _reserve(workflow, principal, specimen, cost: int):
    """The reservations, all inside one handler: (None, None) when every one holds; else ("budget",
    what the monthly caps held, released on the run for settle_released)."""
    from ..field_research import second_opinion
    from .lane_allowance import reserve_step
    from .tenant_budget import release_unsent, reserve_step as reserve_tenant_budget

    step = second_opinion.STEP
    try:
        if workflow.reserve_retained_cost is not None:
            workflow.reserve_retained_cost(principal, specimen, step, cost)
        if not (reserve_tenant_budget(workflow.repository, principal, specimen, step, cost, workflow.clock)
                or reserve_step(workflow.repository, principal, specimen, step, cost, workflow.clock)):
            return None, None
    except Exception:  # noqa: BLE001 - a refusal or an unreadable ledger: not obtained, never a loop
        pass
    try:
        return "budget", release_unsent(specimen.run, step)
    except Exception:  # noqa: BLE001 - the holds then stay, as release_unsent's own rule says
        return "budget", None


def _save(workflow, principal, specimen, revision, label: str):
    from .active_graph import save_recoverably

    return save_recoverably(workflow.repository, principal, specimen, revision, f"{label}:{revision}",
        digest({"step": "field_second_opinion", "run": specimen.run.id, "label": label}))


def _end(workflow, principal, specimen, revision, *, label: str, release=None, prior=None, attempt=0):
    """Finalize the record (second_opinion.finish) and save it with an audit event; then settle at zero
    any monthly-cap hold a refusal released (tenant_budget.settle_released). A result that would pass
    the record's size limit is put back to `prior` (the stored result before this attempt) and stored
    "not obtained: result_too_large" instead. A save that loses to another writer returns the record
    as that writer left it (an open intent is abandoned by its finalize)."""
    from ..field_research import second_opinion
    from .active_graph import GraphTooLarge
    from .storage import Conflict, SnapshotTooLarge
    from .tenant_budget import settle_released

    run = specimen.run
    second_opinion.finish(run)
    run.lease_until = None
    specimen.audit.append(AuditEvent(actor=principal.user_id, action="workflow_step", reason=second_opinion.STEP,
        after={"stage": run.stage, "blocker": run.blocker}))
    try:
        try:
            saved = workflow.repository.save(principal, specimen, revision, f"{label}:{revision}",
                digest({"step": second_opinion.STEP, "run": run.id, "label": label}))
        except (GraphTooLarge, SnapshotTooLarge):
            if not (isinstance(run.second_opinion, dict) and run.second_opinion.get("status") == second_opinion.OBTAINED):
                raise
            run.second_opinion = prior
            second_opinion.record(run, second_opinion.Result(second_opinion.NOT_OBTAINED, "result_too_large"),
                attempt=attempt, at=workflow.clock().isoformat())
            second_opinion.finish(run)
            saved = _save(workflow, principal, specimen, revision, label + "-too-large")
    except Conflict:
        return workflow.repository.get(principal.scope, specimen.id)
    except (GraphTooLarge, SnapshotTooLarge):
        saved = _save(workflow, principal, specimen, revision, label)
    if release is not None:
        settle_released(workflow.repository, principal, saved, release, workflow.clock)
    return saved


def run_step(workflow, principal, specimen, revision):
    """The step, once (module docstring). Returns the saved record."""
    from ..field_research import second_opinion
    from .region_pixels import region_png
    from .source_pixels import source_image
    from .worker_deadline import current_deadline

    step = second_opinion.STEP
    run = specimen.run
    policy = run.profile.execution
    timeout = policy.effect_timeout_for_step(step)
    at = workflow.clock()
    if second_opinion.open_intent(run):
        if run.lease_until and datetime.fromisoformat(run.lease_until) > at:
            return specimen  # Another worker holds it (storage.work_available_at waits for the lease).
        # The attempt's intent was saved and its result never was: not obtained, its reservation held.
        second_opinion.abandon(run, "outcome_unknown")
        return _end(workflow, principal, specimen, revision, label="second-opinion-lost")
    runner = getattr(workflow, "second_opinion", None)
    if runner is None:
        second_opinion.record(run, second_opinion.Result(second_opinion.SWITCHED_OFF), attempt=run.attempts.get(step, 0),
            at=at.isoformat())
        return _end(workflow, principal, specimen, revision, label="second-opinion-off")
    if not second_opinion.due(run):
        return _end(workflow, principal, specimen, revision, label="second-opinion-covered")
    cost = 0 if run.profile.synthetic else second_opinion.CAP_MICROS
    code = _refusal(workflow, principal, specimen, cost, timeout)
    release = None
    if code is None and not run.profile.synthetic:
        code, release = _reserve(workflow, principal, specimen, cost)
    if code is not None:
        second_opinion.record(run, second_opinion.Result(second_opinion.NOT_OBTAINED, code),
            attempt=run.attempts.get(step, 0), at=at.isoformat())
        return _end(workflow, principal, specimen, revision, label="second-opinion-refused", release=release)
    # The intent, saved before the request: no blocker; a lost outcome is found by the next step (above),
    # and anything else that finalizes the run abandons it (second_opinion.at_finalize).
    prior = run.second_opinion
    run.usage.steps += 1
    run.usage.external_calls += 1
    run.usage.reserved_tokens += 0 if run.profile.synthetic else second_opinion.RESERVED_TOKENS
    run.usage.reserved_cost_micros += cost
    run.usage.reserved_active_seconds += timeout
    run.lease_until = (at + timedelta(seconds=policy.lease_seconds)).isoformat()
    run.attempts[step] = run.attempts.get(step, 0) + 1
    attempt = run.attempts[step]
    second_opinion.record(run, second_opinion.Result(second_opinion.ASKING), attempt=attempt, at=at.isoformat())
    specimen = workflow.repository.save(principal, specimen, revision, f"intent:{revision}", digest({"intent": step}))
    revision, run = specimen.version, specimen.run
    seconds = min(second_opinion.TIMEOUT_SECONDS, timeout)
    deadline = current_deadline()
    if deadline is not None:
        from ..field_research.step import MARGIN_SECONDS

        seconds = min(seconds, deadline.remaining() - MARGIN_SECONDS)

    def crops():
        with source_image(specimen.asset, workflow.blobs) as image:
            return {region.id: region_png(image, region) for region in run.regions}

    started = workflow.monotonic()
    try:
        result = second_opinion.obtain(run, model_factory=runner.model_factory, crops=crops,
            price=second_opinion.route_price(run), seconds=seconds, meter_factory=runner.meter_factory)
    except Exception:  # noqa: BLE001 - obtain catches its own; nothing else may fail the run
        result = second_opinion.Result(second_opinion.NOT_OBTAINED, "error", spent=None)
    run.usage.active_seconds += max(0, workflow.monotonic() - started)
    run.usage.reserved_active_seconds = max(0, run.usage.reserved_active_seconds - timeout)
    second_opinion.paid_call(run, attempt=attempt, reserved=cost, result=result)
    second_opinion.record(run, result, attempt=attempt, at=at.isoformat())
    if not run.profile.synthetic:
        from .lane_costs import settle_step

        settle_step(workflow.repository, principal, specimen, step, cost, workflow.clock)
        if workflow.settle_retained_cost is not None:
            workflow.settle_retained_cost(principal, specimen, step)
    return _end(workflow, principal, specimen, revision, label="second-opinion", prior=prior, attempt=attempt)
