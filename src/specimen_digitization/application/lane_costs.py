"""The cost of every paid call (docs/execution/golive/LANE.md, T2c; G9, G30).

One entry per paid call on the run, with its usage and its cost at the run's
pinned price list. A call that reports usage, or a billed amount, settles the
program ledger to what it cost; one that does not stays reserved in full
(the coordinator's G30 ruling).
"""

from __future__ import annotations

from decimal import ROUND_CEILING, Decimal

from .domain import Scope, now

MILLION = 1_000_000


def _ceil(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_CEILING))


def model_cost(prices, route_id, input_tokens, output_tokens):
    price = prices.get("models", {}).get(route_id)
    if price is None:
        return None
    return _ceil(
        Decimal(
            input_tokens * price["input_micros_per_million"]
            + output_tokens * price["output_micros_per_million"]
        )
        / MILLION
    )


def segmentation_cost(prices, seconds):
    service = prices.get("segmentation")
    if service is None:
        return None
    per_second = (
        Decimal(str(service["vcpus"])) * service["vcpu_micros_per_million_seconds"]
        + Decimal(str(service["memory_gib"])) * service["gib_micros_per_million_seconds"]
    )
    request = service.get("request_micros_per_million", 0)
    return _ceil((Decimal(str(seconds)) * per_second + request) / MILLION)


def tool_cost(prices, tool_id, requests):
    price = prices.get("tools", {}).get(tool_id)
    return None if price is None else requests * price


def _reservation(run, step):
    from .lane_reservations import step_reservation

    return step_reservation(run, step)


def _record(run, step, kind, usage, cost, outcome, billed_micros, basis=None, **name):
    prices = run.profile.execution.price_list
    if billed_micros is not None:
        cost, basis = billed_micros, "billed"
    elif basis is None:
        if cost is None:
            # Profiles price every route and the segmentation; anything else is
            # a configuration error, and the step fails with its reservation held.
            raise ValueError(f"No price for {kind} {next(iter(name.values()))}")
        basis = "computed"
    run.paid_calls.append(
        {
            "step": step,
            "attempt": run.attempts.get(step, 1),
            "kind": kind,
            **name,
            "reserved_micros": _reservation(run, step),
            "usage": usage,
            "outcome": outcome,
            "cost_micros": cost,
            "cost_basis": basis,
            "price_list": {"version": prices["version"], "as_of": prices["as_of"]},
            "at": now(),
        }
    )
    if cost is not None:
        run.usage.actual_cost_micros = (run.usage.actual_cost_micros or 0) + cost


def record_model_usage(
    run, step, route_id, *, input_tokens, output_tokens, outcome="completed",
    billed_micros=None,
):
    prices = run.profile.execution.price_list
    if prices is None:
        return
    _record(
        run,
        step,
        "model",
        {"input_tokens": input_tokens, "output_tokens": output_tokens},
        model_cost(prices, route_id, input_tokens, output_tokens),
        outcome,
        billed_micros,
        route_id=route_id,
    )


def record_segmentation(run, step, *, seconds, outcome="completed", billed_micros=None):
    prices = run.profile.execution.price_list
    if prices is None:
        return
    service = prices.get("segmentation") or {}
    _record(
        run,
        step,
        "service",
        {
            "seconds": seconds,
            "vcpus": service.get("vcpus"),
            "memory_gib": service.get("memory_gib"),
        },
        segmentation_cost(prices, seconds),
        outcome,
        billed_micros,
        service="sam3",
    )


def record_tool_usage(
    run, step, tool_id, *, requests, outcome="completed", billed_micros=None
):
    prices = run.profile.execution.price_list
    if prices is None:
        return
    _record(
        run,
        step,
        "tool",
        {"requests": requests},
        tool_cost(prices, tool_id, requests),
        outcome,
        billed_micros,
        tool_id=tool_id,
    )


def record_reserved(run, step, kind, *, outcome, **name):
    """A call that reported no usage stays reserved at its step's full amount."""
    if run.profile.execution.price_list is None:
        return
    _record(
        run, step, kind, None, _reservation(run, step), outcome, None,
        basis="reserved", **name,
    )


def step_outcome(run, step):
    if run.blocker == "external_outcome_unknown":
        return "unknown"
    if run.completed_steps and run.completed_steps[-1] == step:
        return "completed"
    return "failed"


def settle_step(repository, principal, specimen, step, reserved, clock=None):
    """Settle the run's budget and the program ledger to what the step's calls cost.

    Only when every call recorded for the attempt reported usage or a billed
    amount. A reserved call, or a step whose calls nobody recorded, stays fully
    reserved. A settled cost above the reservation counts in full.
    """
    from .lane_allowance import ProgramLedger

    run = specimen.run
    policy = run.profile.execution
    if not reserved:
        return
    attempt = run.attempts.get(step, 1)
    calls = [c for c in run.paid_calls if c["step"] == step and c["attempt"] == attempt]
    if not calls or any(c["cost_basis"] == "reserved" for c in calls):
        return
    cost = sum(c["cost_micros"] for c in calls)
    # The run's own budget settles like the ledger (the coordinator, 2026-09-24).
    run.usage.reserved_cost_micros += cost - reserved
    if policy.program_allowance_micros is None:
        return
    ledger = ProgramLedger(
        repository,
        Scope(
            organization_id=principal.scope.organization_id,
            collection_id=policy.program_ledger_collection,
        ),
        clock=clock,
    )
    position = ledger.settle(
        policy.program_allowance_micros,
        reserved,
        cost,
        specimen_id=specimen.id,
        run_id=run.id,
        step=step,
        attempt=attempt,
    )
    if position is not None:
        run.program_allowance = position


def record_step(repository, principal, specimen, step, observations, seconds, reserved, clock=None):
    """The workflow's hook after a paid step: record its calls, then settle.

    A reading reports its tokens on its observation. A completed SAM 3 call
    reports its measured request seconds, which include waiting for a cold
    start. A call that reported nothing stays reserved.
    """
    run = specimen.run
    if run.profile.execution.price_list is None:
        return
    outcome = step_outcome(run, step)
    if step.startswith("transcribe:"):
        readings = [o for o in observations if o.route_id]
        for observation in readings:
            record_model_usage(
                run,
                step,
                observation.route_id,
                input_tokens=observation.input_tokens,
                output_tokens=observation.output_tokens,
                outcome=outcome,
            )
        if not readings:
            record_reserved(
                run, step, "model", outcome=outcome, route_id=step.split(":")[-1]
            )
    elif step == "segment":
        if outcome == "completed":
            measured = (run.segmentation or {}).get("elapsed_seconds")
            record_segmentation(
                run,
                step,
                seconds=round(seconds, 3) if measured is None else measured,
                outcome=outcome,
            )
        else:
            record_reserved(run, step, "service", outcome=outcome, service="sam3")
    settle_step(repository, principal, specimen, step, reserved, clock)
