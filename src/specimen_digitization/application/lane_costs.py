"""The cost of every paid call (docs/execution/golive/LANE.md, T2c; G9, G30).

One entry per paid call on the run, with its usage and its cost at the run's
pinned price list. Once a step completes, the program ledger is settled to what
its recorded calls cost.
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


def _record(run, step, kind, usage, cost, outcome, billed_micros, **name):
    prices = run.profile.execution.price_list
    reservations = run.profile.execution.stage_cost_reservations
    if billed_micros is not None:
        cost, basis = billed_micros, "billed"
    else:
        basis = "computed" if cost is not None else "unpriced"
    run.paid_calls.append(
        {
            "step": step,
            "attempt": run.attempts.get(step, 1),
            "kind": kind,
            **name,
            "reserved_micros": reservations.for_step(step) if reservations else None,
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


def step_outcome(run, step):
    if run.blocker == "external_outcome_unknown":
        return "unknown"
    if run.completed_steps and run.completed_steps[-1] == step:
        return "completed"
    return "failed"


def settle_step(repository, principal, specimen, step, reserved, clock=None):
    """Settle the program ledger to what a completed step's recorded calls cost.

    Anything else stays fully reserved: a failure, an unknown outcome, a step with
    no recorded calls, or a call without a price. Which failures count as known is
    for the coordinator's next plan PR.
    """
    from .lane_allowance import ProgramLedger

    run = specimen.run
    policy = run.profile.execution
    if (
        policy.program_allowance_micros is None
        or not reserved
        or step_outcome(run, step) != "completed"
    ):
        return
    attempt = run.attempts.get(step, 1)
    calls = [c for c in run.paid_calls if c["step"] == step and c["attempt"] == attempt]
    if not calls or any(c["cost_micros"] is None for c in calls):
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
        sum(c["cost_micros"] for c in calls),
        specimen_id=specimen.id,
        run_id=run.id,
        step=step,
        attempt=attempt,
    )
    if position is not None:
        run.program_allowance = position


def record_step(repository, principal, specimen, step, observations, seconds, reserved, clock=None):
    """The workflow's hook after a paid step: record its calls, then settle.

    Readings report their tokens on their observations. SAM 3's measured request
    seconds come from its response, or from the step's own time when it failed.
    """
    run = specimen.run
    if run.profile.execution.price_list is None:
        return
    outcome = step_outcome(run, step)
    if step.startswith("transcribe:"):
        for observation in observations:
            if observation.route_id:
                record_model_usage(
                    run,
                    step,
                    observation.route_id,
                    input_tokens=observation.input_tokens,
                    output_tokens=observation.output_tokens,
                    outcome=outcome,
                )
    elif step == "segment":
        measured = (run.segmentation or {}).get("elapsed_seconds")
        if outcome != "completed" or measured is None:
            measured = round(seconds, 3)
        record_segmentation(run, step, seconds=measured, outcome=outcome)
    settle_step(repository, principal, specimen, step, reserved, clock)
