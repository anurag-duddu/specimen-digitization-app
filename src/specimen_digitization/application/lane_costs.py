"""The cost of every paid call (docs/execution/golive/LANE.md, T2c; G9, G30).

One entry per paid call on the run, with its usage and its cost at the run's
pinned price list. A call that reports usage, or a billed amount, settles the
program ledger to what it cost; one that does not stays reserved in full
(the coordinator's G30 ruling). The one exception is a call the provider
refused before any work, an HTTP 429 answering its first request: nothing was
generated or billed, so it is recorded at zero (cost basis `refused`) and its
reservation is released.
"""

from __future__ import annotations

from decimal import ROUND_CEILING, Decimal

from .domain import Scope, now
from .lane_reservations import SAM_BOOST_SECONDS, SAM_SHUTDOWN_SECONDS, SAM_STARTUP_SECONDS
from .reliability import checked_usage
from .sam3_effect import instance_accounting

MILLION = 1_000_000
# Cloud Run keeps an idle specimen-sam instance at most 15 minutes after its
# last request, then stops it (about-instance-autoscaling). On 2026-10-17 its
# stop signal came 902.6 s and 906.2 s after the two instances' last requests.
SAM_IDLE_SECONDS = 900
SAM_IDLE_LAG_SECONDS = 20
# An instance's start before the SAM 3 server's own clock begins
# (sam3_server.PROCESS_STARTED): the container, the interpreter and the
# imports. Both instances of 2026-10-17 started in 80.4 s in all.
SAM_STARTUP_SLACK_SECONDS = 30


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


def segmentation_instance_cost(prices, instance):
    """What a SAM 3 request cost Cloud Run, from the instance time it reported.

    specimen-sam is billed by instance (CPU always allocated): its whole life,
    idle time included, at the price list's instance-based rates (its
    request-based ones where it names none). A request pays its own seconds and
    the instance's idle seconds before it, at most the idle wait Cloud Run
    allows: longer, a minimum instance was kept warm, which the infrastructure
    budget carries (lane_reservations). The instance's first request also pays
    what only it causes and nothing later can be charged for: the start (its
    measured seconds, at most the startup probe's 600, plus
    SAM_STARTUP_SLACK_SECONDS) with the startup CPU boost over it and 10 s
    after, and the instance's last idle wait and shutdown, which follow
    whichever request ends up last. So each run pays the instance time it
    caused, and together they pay the whole life of an instance a request
    started. A run whose price list predates the instance-based rates settles
    at its request-based ones, which are higher.
    """
    service = prices.get("segmentation")
    if service is None:
        return None
    vcpu = service.get("instance_vcpu_micros_per_million_seconds")
    gib = service.get("instance_gib_micros_per_million_seconds")
    fee = 0
    if vcpu is None or gib is None:
        vcpu = service["vcpu_micros_per_million_seconds"]
        gib = service["gib_micros_per_million_seconds"]
        fee = service.get("request_micros_per_million", 0)
    vcpus = Decimal(str(service["vcpus"]))
    per_second = vcpus * vcpu + Decimal(str(service["memory_gib"])) * gib
    request = Decimal(str(instance["request_seconds"]))
    idle = Decimal(str(instance["idle_seconds"]))
    boost = 0
    if instance["first"]:
        startup = min(idle, SAM_STARTUP_SECONDS) + SAM_STARTUP_SLACK_SECONDS
        seconds = (
            startup + request + SAM_IDLE_SECONDS + SAM_IDLE_LAG_SECONDS + SAM_SHUTDOWN_SECONDS
        )
        boost = (startup + SAM_BOOST_SECONDS) * vcpus * vcpu
    else:
        seconds = min(idle, SAM_IDLE_SECONDS + SAM_IDLE_LAG_SECONDS) + request
    return _ceil((seconds * per_second + boost + fee) / MILLION)


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
    # A held liability is not a measured actual. Once any retained call is
    # unknown, later known usage cannot turn the whole run into a known total.
    if any(call["cost_basis"] == "reserved" for call in run.paid_calls):
        run.usage.actual_cost_micros = None
    elif cost is not None:
        run.usage.actual_cost_micros = (run.usage.actual_cost_micros or 0) + cost


def record_model_usage(
    run, step, route_id, *, input_tokens, output_tokens, outcome="completed",
    billed_micros=None, failure_code=None,
):
    prices = run.profile.execution.price_list
    if prices is None:
        return
    name = {"route_id": route_id}
    if failure_code:
        name["failure_code"] = failure_code
    _record(
        run,
        step,
        "model",
        {"input_tokens": input_tokens, "output_tokens": output_tokens},
        model_cost(prices, route_id, input_tokens, output_tokens),
        outcome,
        billed_micros,
        **name,
    )


def record_reported_usage(run, step, route_id, usage, *, outcome, failure_code=None):
    """A model call whose provider reported every request's tokens, at their cost.

    A failed call (an answer that stayed malformed after its retry, a call
    stopped by its limits; reliability.reported_usage) is recorded ``failed``
    at what those tokens cost (``computed``), so its step settles and the rest
    of its reservation is released (PLAN 4.3). A completed parse records its
    extraction's tokens the same way, with its own outcome.
    """
    record_model_usage(
        run,
        step,
        route_id,
        input_tokens=usage["input_tokens"],
        output_tokens=usage["output_tokens"],
        outcome=outcome,
        failure_code=failure_code,
    )


def record_segmentation(
    run, step, *, seconds, outcome="completed", billed_micros=None, instance=None
):
    """A SAM 3 call: at the instance time SAM 3 reported it used, which settles.

    `seconds` is the worker's wall time for the call, kept as a diagnostic: it
    omits the instance's idle time, which Cloud Run bills. Without the
    instance's report (`instance`, sam3_server.InstanceMeter: a service that
    sends none) the call's cost is unknown and its full reservation is held.
    """
    prices = run.profile.execution.price_list
    if prices is None:
        return
    service = prices.get("segmentation") or {}
    instance = instance_accounting(instance)
    usage = {
        "seconds": seconds,
        "vcpus": service.get("vcpus"),
        "memory_gib": service.get("memory_gib"),
    }
    if billed_micros is None and instance is not None:
        _record(
            run, step, "service", dict(usage, instance=instance),
            segmentation_instance_cost(prices, instance), outcome, None, service="sam3",
        )
        return
    _record(
        run,
        step,
        "service",
        usage,
        _reservation(run, step) if billed_micros is None else billed_micros,
        outcome,
        billed_micros,
        basis="reserved" if billed_micros is None else "billed",
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


def record_refused(run, step, kind, *, failure_code, **name):
    """A call the provider refused before any work costs nothing.

    Only a proven refusal: an HTTP 429 answering the call's first request
    (reliability.AdapterFailure.refused). It is a known zero, so it settles and
    releases its step's reservation; any other failure stays reserved in full.
    """
    if run.profile.execution.price_list is None:
        return
    _record(
        run, step, kind, None, 0, "failed", None,
        basis="refused", **name, failure_code=failure_code,
    )


def record_settled(run, step, kind, *, cost_micros, failure_code, **name):
    """A call whose result was lost after the program ledger settled its cost.

    The worker that sent it settled the shared ledger (``settle_step``) and then
    stopped before saving the run, so the ledger's settled amount is the call's
    known cost. It is recorded ``failed`` at that cost, so ``settle_step`` brings
    the run's budget to the same amount the ledger holds.
    """
    if run.profile.execution.price_list is None:
        return
    _record(
        run, step, kind, None, cost_micros, "failed", None,
        basis="computed", **name, failure_code=failure_code,
    )


def step_outcome(run, step):
    if run.blocker == "external_outcome_unknown":
        return "unknown"
    if run.completed_steps and run.completed_steps[-1] == step:
        return "completed"
    return "failed"


def settle_step(repository, principal, specimen, step, reserved, clock=None):
    """Settle the run's budget, the program ledger and any monthly cap ledger the
    attempt reserved in to what the step's calls cost.

    Only when every call recorded for the attempt reported usage or a billed
    amount, or was refused before any work (a known zero). A reserved call, or a
    step whose calls nobody recorded, stays fully reserved. A settled cost above
    the reservation counts in full.
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
    # The run's own budget and shared ledger both replay settlement exactly once.
    settlements = run.dependencies.setdefault("ordinary_cost_settlements", {})
    key = f"{step}:{attempt}"
    envelope = {"reserved_micros": reserved, "settled_micros": cost}
    if key in settlements:
        if settlements[key] != envelope:
            raise ValueError("Ordinary settlement changed")
    else:
        run.usage.reserved_cost_micros += cost - reserved
        settlements[key] = envelope
    if policy.program_allowance_micros is not None:
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
    from .tenant_budget import settle_step as settle_tenant_budget

    # The monthly cap ledgers the attempt reserved in, in the month it reserved
    # in (TENANT_BUDGETS.md); nothing when it reserved in none.
    settle_tenant_budget(repository, principal, specimen, step, attempt, reserved, cost, clock)


def record_step(
    repository, principal, specimen, step, observations, seconds, reserved,
    clock=None, failure=None, refusal=None, usage=None,
):
    """The workflow's hook after a paid step: record its calls, then settle.

    A reading reports its tokens on its observation. A reading that gave none
    failed, even when its step then completed (a reader that is given up on, or
    stopped by its limits, completes with no observation): it is recorded as
    `failed` with the code it failed with. So is a first pass that is given up
    on (its step completes with no decision). Such a failed call settles at
    what it cost when its provider reported every request's tokens (`usage`,
    reliability.reported_usage: an answer that stayed malformed, a call stopped
    by its limits); otherwise its spend is unknown (a timeout, a 5xx, a child
    that ended without an answer) and its reservation stays held in full.
    Parse records its extraction's reported tokens (`usage`) in the same way.

    A completed SAM 3 call settles at the instance time it reported
    (record_segmentation): the worker's request seconds alone omit startup,
    its CPU boost and the idle time Cloud Run bills. One with no report stays
    reserved in full unless a billed amount is supplied.

    `refusal` is the code of a model call the provider refused before any work
    (reliability.AdapterFailure.refused); that call is recorded at no cost
    (record_refused), and its reservation is released.
    """
    run = specimen.run
    if run.profile.execution.price_list is None:
        return
    outcome = step_outcome(run, step)
    usage = checked_usage(usage)
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
        if not readings and refusal:
            record_refused(
                run, step, "model", route_id=step.split(":")[-1], failure_code=refusal
            )
        elif not readings and usage:
            record_reported_usage(
                run, step, step.split(":")[-1], usage,
                outcome="failed" if outcome == "completed" else outcome,
                failure_code=failure,
            )
        elif not readings:
            name = {"route_id": step.split(":")[-1]}
            if failure:
                name["failure_code"] = failure
                outcome = "failed" if outcome == "completed" else outcome
            record_reserved(run, step, "model", outcome=outcome, **name)
    elif step.startswith("first_pass:"):
        matching = [d.call for d in run.first_pass_decisions
            if d.region_id == step.split(":", 1)[1]]
        if outcome == "completed" and len(matching) == 1:
            call = matching[0]
            record_model_usage(run, step, call.route_id,
                input_tokens=call.input_tokens, output_tokens=call.output_tokens,
                outcome=outcome)
        elif refusal:
            record_refused(run, step, "model",
                route_id=run.profile.first_pass_route, failure_code=refusal)
        elif usage:
            record_reported_usage(run, step, run.profile.first_pass_route, usage,
                outcome="failed" if outcome == "completed" else outcome,
                failure_code=failure)
        else:
            name = {"route_id": run.profile.first_pass_route}
            if failure:
                # A first pass given up on completes its step with no decision:
                # its last call failed, as a reading's does.
                name["failure_code"] = failure
                outcome = "failed" if outcome == "completed" else outcome
            record_reserved(run, step, "model", outcome=outcome, **name)
    elif step in {"parse", "classify"}:
        # Parse's one model call (extract_with_agent) settles at its reported
        # tokens (`usage`) at the price of the route it calls, the profile's
        # first route (lane_reservations.step_reservation sizes it the same
        # way). Without them its whole liability stays held. A refusal of that
        # call is proof that nothing was billed. Held or refused, a parse call
        # names that route too, so the cost meter can match it to its model's
        # bill (it named its step before 2026-10-25: cost_ledger.LEGACY_ROUTES).
        attempt = run.attempts.get(step, 1)
        if not any(c["step"] == step and c["attempt"] == attempt for c in run.paid_calls):
            route = run.profile.routes[0] if run.profile.routes else None
            named = route if step == "parse" and route else step
            if refusal:
                record_refused(run, step, "model", route_id=named, failure_code=refusal)
            elif usage and step == "parse" and route:
                if failure:
                    outcome = "failed" if outcome == "completed" else outcome
                record_reported_usage(
                    run, step, route, usage, outcome=outcome, failure_code=failure
                )
            elif failure:
                # An extraction that failed, or was given up on (its step then
                # completes): recorded failed with its code, held in full.
                outcome = "failed" if outcome == "completed" else outcome
                record_reserved(
                    run, step, "model", outcome=outcome, route_id=named, failure_code=failure
                )
            else:
                record_reserved(run, step, "model", outcome=outcome, route_id=named)
    elif step == "segment":
        if outcome == "completed":
            measured = (run.segmentation or {}).get("elapsed_seconds")
            record_segmentation(
                run,
                step,
                seconds=round(seconds, 3) if measured is None else measured,
                outcome=outcome,
                instance=(run.segmentation or {}).get("instance"),
            )
        else:
            record_reserved(run, step, "service", outcome=outcome, service="sam3")
    settle_step(repository, principal, specimen, step, reserved, clock)
