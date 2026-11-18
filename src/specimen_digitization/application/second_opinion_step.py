"""The workflow step `field_second_opinion` (field_research/second_opinion.py): its lifecycle.

WHERE IT SITS. Field research finalizes the record in memory (its step, or its recheck when a
completed run reaches the handover again). When that leaves the run finalized, with no retryable
research failure pending and nothing further to ask, and a value the second opinion answers for has
no recorded verdict for its current value (`second_opinion.due`), the workflow does not finalize the
record yet: `mark_due` sets the run's stage to the step and its disposition to none, in the same
save. The next workflow step runs it (`run_step`), and it finalizes the record (second_opinion.finish).

ITS LIFECYCLE is a paid step's: what it reserves (one request's cap, second_opinion.CAP_MICROS) is
checked against the run's cost ceiling, the retained research liabilities, the run's limits on steps,
external calls and active time, any monthly cap and the program's allowance, and reserved on them; an
intent is saved with a lease, the attempt and the unknown-outcome blocker before the request; the
request runs inside the step's deadline (the profile's external timeout, the request's own
TIMEOUT_SECONDS and the worker's deadline); its paid call is recorded under the second opinion's route
and the reservation settled to what the provider reported (lane_costs.settle_step), or held in full
when that is not known.

HOW ITS FAILURE DIFFERS FROM A MANDATORY STEP'S. A mandatory paid step that cannot be afforded, that
fails, times out or loses its outcome blocks the run (processing_blocked, a retry scheduled, or a
person's attention). This step never does: whatever stops it ends it "not obtained" with a code, and
the workflow finalizes the record in the same save, with the stage and blocker field research gave it
(finalized, none) and the not-checked marks derived from the current values. The refusals before any
reservation (switched off, attempts used, a run limit, no price, money) reserve nothing; a refusal on
the monthly-cap or allowance ledgers releases what it held there. After the intent: a provider error
(HTTP 402 included), a timeout, a malformed answer, a spent meter or any exception is recorded and
finalized at once; a lost outcome (the worker's deadline, a crash, a save that failed) is found by the
next workflow step once the lease ends, recorded "not obtained: outcome_unknown" with its whole
reservation held, and finalized. It is never sent twice for one due: each attempt makes at most one
request, and a lost one is not repeated.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .domain import AuditEvent
from .storage import digest

UNKNOWN = "external_outcome_unknown"


def mark_due(run) -> None:
    """After field research's step or recheck: when research left the run finalized and the second
    opinion is due, the record waits for it (stage `field_second_opinion`, no disposition)."""
    from ..field_research import second_opinion

    if run.stage == "finalized" and second_opinion.due(run):
        run.stage, run.disposition = second_opinion.STEP, None


def _paid_call(run, *, attempt: int, reserved: int, result) -> None:
    """The step's one paid-call entry, in lane_costs' shape (field_research.step.record_cost's): what the
    provider reported, or the reservation when that is not known."""
    from ..field_research import second_opinion
    from ..model_gateway import SECOND_OPINION_ROUTE
    from .domain import now

    prices = run.profile.execution.price_list
    known = result.spent is not None
    usage = {"model_calls": result.requests}
    if result.tokens:
        usage.update(reported_requests=result.tokens["requests"], input_tokens=result.tokens["input_tokens"],
            cached_input_tokens=result.tokens["cached_input_tokens"], output_tokens=result.tokens["output_tokens"])
    run.paid_calls.append({
        "step": second_opinion.STEP,
        "attempt": attempt,
        "kind": "model",
        "route_id": SECOND_OPINION_ROUTE,
        "reserved_micros": reserved,
        "usage": usage if known else None,
        "outcome": "completed" if result.status == second_opinion.OBTAINED else "failed" if known else "unknown",
        "cost_micros": result.spent if known else reserved,
        "cost_basis": "computed" if known else "reserved",
        **({"failure_code": result.reason} if result.reason else {}),
        "price_list": {"version": prices["version"], "as_of": prices["as_of"]},
        "at": now(),
    })
    if any(call["cost_basis"] == "reserved" for call in run.paid_calls):
        run.usage.actual_cost_micros = None
    elif known:
        run.usage.actual_cost_micros = (run.usage.actual_cost_micros or 0) + result.spent


def _refusal(workflow, principal, specimen, cost: int, timeout: float) -> str | None:
    """Why the step makes no request, before anything is reserved, or None."""
    from ..field_research import second_opinion
    from .workflow import attempts_used

    run = specimen.run
    policy = run.profile.execution
    if attempts_used(run, second_opinion.STEP) >= policy.max_attempts:
        return "attempts_used"
    if (run.usage.steps >= policy.max_steps or run.usage.external_calls + 1 > policy.max_external_calls
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


def _end(workflow, principal, specimen, revision, *, label: str, release=None):
    """Finalize the record (second_opinion.finish) and save it with an audit event; then settle at zero
    any monthly-cap hold a refusal released (tenant_budget.settle_released)."""
    from ..field_research import second_opinion
    from .active_graph import save_recoverably
    from .tenant_budget import settle_released

    run = specimen.run
    second_opinion.finish(run)
    run.lease_until = None
    specimen.audit.append(AuditEvent(actor=principal.user_id, action="workflow_step", reason=second_opinion.STEP,
        after={"stage": run.stage, "blocker": run.blocker}))
    saved = save_recoverably(workflow.repository, principal, specimen, revision, f"{label}:{revision}",
        digest({"step": second_opinion.STEP, "run": run.id, "label": label}))
    if release is not None:
        settle_released(workflow.repository, principal, saved, release, workflow.clock)
    return saved


def run_step(workflow, principal, specimen, revision):
    """The step, once (module docstring). Returns the saved record."""
    from ..field_research import second_opinion
    from .lane_allowance import reserve_step
    from .region_pixels import region_png
    from .source_pixels import source_image
    from .tenant_budget import release_unsent, reserve_step as reserve_tenant_budget
    from .worker_deadline import current_deadline
    from .workflow import OperationalBlock

    step = second_opinion.STEP
    run = specimen.run
    policy = run.profile.execution
    timeout = policy.effect_timeout_for_step(step)
    at = workflow.clock()
    if run.blocker == UNKNOWN:
        if run.lease_until and datetime.fromisoformat(run.lease_until) > at:
            return specimen  # Another worker holds it.
        # The attempt's intent was saved and its result never was: not obtained, its reservation held.
        attempt = run.attempts.get(step, 1)
        result = second_opinion.Result(second_opinion.NOT_OBTAINED, "outcome_unknown", spent=None)
        if not any(call["step"] == step and call["attempt"] == attempt for call in run.paid_calls):
            _paid_call(run, attempt=attempt, reserved=0 if run.profile.synthetic else second_opinion.CAP_MICROS,
                result=result)
        second_opinion.record(run, result, attempt=attempt, at=at.isoformat())
        run.usage.reserved_active_seconds = max(0, run.usage.reserved_active_seconds - timeout)
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
        if workflow.reserve_retained_cost is not None:
            try:
                workflow.reserve_retained_cost(principal, specimen, step, cost)
            except OperationalBlock:
                code = "budget"
        if code is None and (reserve_tenant_budget(workflow.repository, principal, specimen, step, cost, workflow.clock)
                or reserve_step(workflow.repository, principal, specimen, step, cost, workflow.clock)):
            code = "budget"
            # A monthly cap may hold the attempt while the allowance refused it: released at zero.
            release = release_unsent(run, step)
    if code is not None:
        second_opinion.record(run, second_opinion.Result(second_opinion.NOT_OBTAINED, code),
            attempt=run.attempts.get(step, 0), at=at.isoformat())
        return _end(workflow, principal, specimen, revision, label="second-opinion-refused", release=release)
    # The intent, saved before the request: a lost outcome is found by the next step (above).
    run.usage.steps += 1
    run.usage.external_calls += 1
    run.usage.reserved_cost_micros += cost
    run.usage.reserved_active_seconds += timeout
    run.blocker = UNKNOWN
    run.lease_until = (at + timedelta(seconds=policy.lease_seconds)).isoformat()
    run.attempts[step] = run.attempts.get(step, 0) + 1
    attempt = run.attempts[step]
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
    _paid_call(run, attempt=attempt, reserved=cost, result=result)
    second_opinion.record(run, result, attempt=attempt, at=at.isoformat())
    run.blocker = None
    if not run.profile.synthetic:
        from .lane_costs import settle_step

        settle_step(workflow.repository, principal, specimen, step, cost, workflow.clock)
        if workflow.settle_retained_cost is not None:
            workflow.settle_retained_cost(principal, specimen, step)
    return _end(workflow, principal, specimen, revision, label="second-opinion")
