"""The cost meter's rows and totals (docs/execution/golive/COST_METER.md).

Pure: no I/O. ``paid_call_rows`` maps a run's paid calls, in the shape
``lane_costs._record`` and ``field_research.step.record_cost`` write them, to
CostEntry rows; ``cost_report`` builds the ``GET .../costs`` body from the
grouped sums ``CostTotalsV1`` returns.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from decimal import ROUND_CEILING, Decimal
from functools import lru_cache
from pathlib import Path
from uuid import UUID

from .projection import derived_id

SOURCE = "paid_call"
KINDS = ("model", "service", "tool")
# The bases a paid call records (lane_costs); "allocated" belongs to the shared
# Google cost rows (cost_allocation).
BASES = frozenset({"computed", "billed", "reserved", "refused"})
HELD = "reserved"
# The basis the ledger gives a call it re-values after the fact from evidence
# the call did not carry (true_up below); the call's own record is unchanged.
TRUED_UP = "trued_up"
PROVIDER_DAY_MEAN = "provider-day-mean"
SAM_REQUEST_SECONDS = "sam-request-seconds"
# Before the fix of 2026-10-25 a parse call that was held or refused named its
# step as its route. Parse calls the profile's first model route, which every
# published profile has named "handwriting-qwen" since the first one
# (profiles/published.json, 2026-10-01); the settled parse calls say so too.
LEGACY_ROUTES = {("parse", "parse"): "handwriting-qwen"}
# What the rows derive from besides the calls themselves. The sweep reads every
# record again when it changes (cost_sweep), so earlier rows follow the rules.
RULES = "cost-rules-2026-10-25"
# How a direct SAM 3 row is valued. The specimen-sam residual is the day's
# instance time less those rows, so when this changes the allocator computes
# the days it allocated under the old value again (cost_allocator).
SAM_DIRECT_RULES = "sam-direct-2026-10-25"
BILLS = Path(__file__).with_name("profiles") / "provider_bills.json"
INSTANCE_PRICES = Path(__file__).with_name("profiles") / "infrastructure_prices.json"
# Whole steps, then step prefixes, named by the pipeline stage they belong to.
STEP_STAGES = {
    "segment": "label_finding",
    "parse": "structuring",
    "classify": "classification",
    "field_research": "field_research",
}
PREFIX_STAGES = {"transcribe": "reading", "first_pass": "first_pass"}
# Model routes are served through Hugging Face's router; the SAM 3 service is
# Cloud Run. Neither the price list nor a registry names a provider for a paid
# tool, so a tool's provider is "tool".
MODEL_PROVIDER = "huggingface"
SERVICE_PROVIDERS = {"sam3": "google_cloud"}
TOOL_PROVIDER = "tool"
# The connector's bounds (dataconnect/connector/cost_meter.gql): an amount has
# at most fifteen digits; texts are bounded so one row cannot carry content.
MAX_MICROS = 10**15 - 1
TEXT_LIMITS = {"step": 300, "stage": 64, "provider": 64, "resource": 300, "outcome": 64,
               "failure_code": 200, "price_list_version": 64, "price_list_as_of": 64}
MAX_MONTHS = 24


class CostRowInvalid(ValueError):
    """A paid call the ledger cannot record as it stands; the code names the part."""


def stage_of(step: str) -> str:
    """The pipeline stage a run step belongs to, or the step's prefix for any other."""
    if step in STEP_STAGES:
        return STEP_STAGES[step]
    prefix = step.split(":", 1)[0]
    return PREFIX_STAGES.get(prefix, prefix)


def _exact(value, code, *, optional=False):
    """A whole number of micro-USD, as the snapshot's transport may return it (17.0)."""
    if value is None and optional:
        return None
    if type(value) is float and math.isfinite(value) and value.is_integer():
        value = int(value)
    if type(value) is not int or not 0 <= value <= MAX_MICROS:
        raise CostRowInvalid(code)
    return value


def _numbers(value, depth=0):
    """Usage as recorded, numbers only: a string anywhere below the keys is refused.

    Integral floats become ints, so a row read back through the snapshot's
    transport has the same digest as the row the save sent.
    """
    if depth > 4:
        raise CostRowInvalid("cost_usage_too_deep")
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise CostRowInvalid("cost_usage_not_numeric")
        return {key: _numbers(item, depth + 1) for key, item in value.items()}
    if isinstance(value, list):
        return [_numbers(item, depth + 1) for item in value]
    if value is None or type(value) is bool or type(value) is int:
        return value
    if type(value) is float and math.isfinite(value):
        return int(value) if value.is_integer() else value
    raise CostRowInvalid("cost_usage_not_numeric")


def _text(call, key, *, optional=True):
    value = call.get(key)
    if value is None and optional:
        return None
    if not isinstance(value, str) or not 1 <= len(value) <= TEXT_LIMITS[key]:
        raise CostRowInvalid("cost_" + key + "_invalid")
    return value


def _moment(value):
    """The call's ``at`` in UTC (a naive time is read as UTC) and its UTC month."""
    if not isinstance(value, str):
        raise CostRowInvalid("cost_occurred_at_invalid")
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise CostRowInvalid("cost_occurred_at_invalid") from None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    moment = moment.astimezone(timezone.utc)
    return moment.isoformat(), moment.strftime("%Y-%m")


def provider_of(kind: str, call: dict) -> str:
    if kind == "model":
        return MODEL_PROVIDER
    if kind == "service":
        return SERVICE_PROVIDERS.get(call.get("service"), "google_cloud")
    return TOOL_PROVIDER


def resource_of(kind: str, call: dict):
    resource = call.get({"model": "route_id", "service": "service", "tool": "tool_id"}[kind])
    return LEGACY_ROUTES.get((call.get("step"), resource), resource) if kind == "model" else resource


# ---- re-valuing a call from evidence it did not carry ----------------------

@lru_cache(maxsize=1)
def provider_bills() -> dict:
    """The committed provider bills: per UTC day and model, requests and nano-USD."""
    return json.loads(BILLS.read_text())


@lru_cache(maxsize=1)
def _instance_rates() -> dict:
    table = json.loads(INSTANCE_PRICES.read_text())
    return {"version": table["version"], **table["cloud_run"]["instance_based"]}


@lru_cache(maxsize=1)
def _route_models() -> dict:
    from ..model_gateway import HUGGINGFACE_ROUTES

    return {route_id: route.model_id for route_id, route in HUGGINGFACE_ROUTES.items()}


def rules_version() -> str:
    """The rules and the bills the rows are derived with, for the sweep's watermark."""
    return f"{RULES}/{provider_bills()['version']}"


def _whole(value) -> bool:
    return type(value) is int and value >= 0


def _ceil(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_CEILING))


def _day_mean(resource, occurred_at, requests):
    """``requests`` requests at the provider's billed mean for the model that UTC day.

    None when the committed bills hold no request of that model that day.
    """
    model = _route_models().get(resource)
    bills = provider_bills()
    day = occurred_at[:10]
    cell = bills["huggingface"]["days"].get(day, {}).get(model)
    if model is None or cell is None or not cell["requests"] > 0:
        return None
    estimate = _ceil(Decimal(cell["nano_usd"]) * requests / (Decimal(cell["requests"]) * 1000))
    return estimate, {"provider": "huggingface", "bills": bills["version"], "day": day, "model": model,
                      "billed_requests": cell["requests"], "billed_nano_usd": cell["nano_usd"]}


def true_up(kind, resource, basis, cost, reserved, usage, outcome, occurred_at):
    """A better-evidenced cost for a call, or None to keep the call's own.

    - A held SAM 3 call that completed and reported its request seconds but no
      instance time (a server older than the instance meter): those seconds at
      Cloud Run's instance-based rates (``sam-request-seconds``). The instance's
      start and idle time are not the request's; the specimen-sam allocation's
      residual carries them, against these rows as they stand.
    - A held model call: its requests (``usage.model_calls``, else one) at the
      provider's billed mean per request for that model and UTC day
      (``provider-day-mean``), from the committed bills.
    - A settled call on a route whose provider bills cached input below list
      (the bills' ``cached_input_routes``) that recorded no cached input
      tokens: its ``model_calls`` at that day's billed mean, the same way.

    Never above what the call already counts at, and never without the
    evidence: with none, the call keeps its own cost and basis. The method and
    its inputs go in the row's method fields; the reservation stays on the row.
    """
    usage = usage if isinstance(usage, dict) else {}
    original = {"original_basis": basis, "original_cost_micros": cost}
    if kind == "service" and resource == "sam3" and basis == HELD and outcome == "completed" \
            and reserved is not None and "instance" not in usage:
        seconds, vcpus, gib = usage.get("seconds"), usage.get("vcpus"), usage.get("memory_gib")
        if not all(type(v) in (int, float) and math.isfinite(v) and v >= 0 for v in (seconds, vcpus, gib)):
            return None
        rates = _instance_rates()
        per_second = (Decimal(str(vcpus)) * rates["vcpu_micros_per_million_seconds"]
                      + Decimal(str(gib)) * rates["gib_micros_per_million_seconds"]) / 1_000_000
        measured = _ceil(Decimal(str(seconds)) * per_second)
        return min(reserved, measured), SAM_REQUEST_SECONDS, {
            **original, "request_seconds": seconds, "vcpus": vcpus, "memory_gib": gib,
            "rate_micros_per_second": format(per_second.normalize(), "f"), "rates": rates["version"],
            "note": "the request's own seconds at Cloud Run's instance-based rates; the instance's start "
                    "and idle time are in the specimen-sam allocation's residual"}
    if kind != "model":
        return None
    calls = usage.get("model_calls")
    if basis == HELD and reserved is not None:
        requests, counted = (calls, "usage.model_calls") if _whole(calls) and calls > 0 else (1, "one request")
        ceiling = reserved
    elif basis == "computed" and resource in provider_bills()["huggingface"].get("cached_input_routes", ()) \
            and not usage.get("cached_input_tokens") and _whole(calls) and calls > 0:
        requests, counted, ceiling = calls, "usage.model_calls", cost
    else:
        return None
    found = _day_mean(resource, occurred_at, requests)
    if found is None:
        return None
    estimate, bill = found
    return min(ceiling, estimate), PROVIDER_DAY_MEAN, {
        **original, "requests": requests, "requests_from": counted, **bill,
        "note": "the call's requests at the provider's billed mean per request for the model that UTC day"}


def call_rows(organization_id, collection_id, specimen_id, run_id, paid_calls) -> list[dict]:
    """One row per paid call, keyed by (step, attempt, kind) and its place among
    the run's calls with that key (``ordinal``), so a resend, a sweep or a
    restored copy of the same run derives the same ids.

    A call with no cost recorded counts at its reservation, else at zero: an
    unknown cost is held in full, as the program ledger holds it (G30).
    """
    organization_id, collection_id = str(UUID(organization_id)), str(UUID(collection_id))
    specimen_id, run_id = str(UUID(specimen_id)), str(UUID(run_id))
    if not isinstance(paid_calls, list):
        raise CostRowInvalid("cost_paid_calls_invalid")
    seen: dict[tuple, int] = {}
    rows = []
    for call in paid_calls:
        if not isinstance(call, dict):
            raise CostRowInvalid("cost_call_invalid")
        kind, step = call.get("kind"), _text(call, "step", optional=False)
        if kind not in KINDS:
            raise CostRowInvalid("cost_kind_invalid")
        attempt = call.get("attempt")
        if type(attempt) is float and attempt.is_integer():
            attempt = int(attempt)
        if type(attempt) is not int or not 1 <= attempt < 10**9:
            raise CostRowInvalid("cost_attempt_invalid")
        key = (step, attempt, kind)
        ordinal = seen.get(key, 0)
        seen[key] = ordinal + 1
        basis = call.get("cost_basis")
        if basis not in BASES:
            raise CostRowInvalid("cost_basis_invalid")
        reserved = _exact(call.get("reserved_micros"), "cost_reserved_invalid", optional=True)
        cost = _exact(call.get("cost_micros"), "cost_micros_invalid", optional=True)
        if cost is None:
            cost, basis = (reserved, HELD) if reserved is not None else (0, basis)
        resource = resource_of(kind, call)
        if not isinstance(resource, str) or not 1 <= len(resource) <= TEXT_LIMITS["resource"]:
            raise CostRowInvalid("cost_resource_invalid")
        prices = call.get("price_list") if isinstance(call.get("price_list"), dict) else {}
        occurred_at, month = _moment(call.get("at"))
        usage = call.get("usage")
        if usage is not None and not isinstance(usage, dict):
            raise CostRowInvalid("cost_usage_not_numeric")
        usage = None if usage is None else _numbers(usage)
        outcome = _text(call, "outcome")
        method = details = None
        adjusted = true_up(kind, resource, basis, cost, reserved, usage, outcome, occurred_at)
        if adjusted is not None:
            cost, method, details = adjusted
            basis = TRUED_UP
        stage = stage_of(step)
        rows.append({
            "organization_id": organization_id,
            "collection_id": collection_id,
            "id": derived_id("cost", specimen_id, run_id, step, attempt, kind, ordinal),
            "source": SOURCE,
            "specimen_id": specimen_id,
            "run_id": run_id,
            "step": step,
            "stage": _text({"stage": stage}, "stage", optional=False),
            "attempt": attempt,
            "kind": kind,
            "ordinal": ordinal,
            "provider": provider_of(kind, call),
            "resource": resource,
            "usage": usage,
            "reserved_micros": reserved,
            "cost_micros": cost,
            # A paid call has no free allowance; shared Google costs do.
            "list_cost_micros": cost,
            "cost_basis": basis,
            "outcome": outcome,
            "failure_code": _text(call, "failure_code"),
            "price_list_version": _text({"price_list_version": prices.get("version")}, "price_list_version"),
            "price_list_as_of": _text({"price_list_as_of": prices.get("as_of")}, "price_list_as_of"),
            "occurred_at": occurred_at,
            "month": month,
            # Set only on a row the ledger re-valued (true_up): how, and from what.
            "allocation_method_id": method,
            "allocation_method_details": details,
        })
    return rows


def paid_call_rows(organization_id, collection_id, specimen_id, run) -> list[dict]:
    """The rows of one run (a domain Run, or a run as a snapshot stores it)."""
    if isinstance(run, dict):
        return call_rows(organization_id, collection_id, specimen_id, run.get("id"),
                         run.get("paid_calls") or [])
    return call_rows(organization_id, collection_id, specimen_id, run.id, run.paid_calls)


# ---- the GET .../costs body ------------------------------------------------

def month_of(value) -> tuple[int, int]:
    """A ``YYYY-MM`` month as (year, month); anything else is refused."""
    if not isinstance(value, str) or len(value) != 7 or value[4] != "-":
        raise ValueError("Months are YYYY-MM")
    year, month = value[:4], value[5:]
    if not (year.isdigit() and month.isdigit() and year.isascii() and month.isascii()):
        raise ValueError("Months are YYYY-MM")
    if not 1 <= int(month) <= 12 or int(year) < 1970:
        raise ValueError("Months are YYYY-MM")
    return int(year), int(month)


def months_between(from_month: str, to_month: str) -> list[str]:
    """Every month from ``from_month`` through ``to_month``, at most MAX_MONTHS."""
    start, end = month_of(from_month), month_of(to_month)
    count = (end[0] - start[0]) * 12 + end[1] - start[1] + 1
    if count < 1:
        raise ValueError("The first month must not follow the last")
    if count > MAX_MONTHS:
        raise ValueError(f"At most {MAX_MONTHS} months")
    months, (year, month) = [], start
    for _ in range(count):
        months.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def _zero():
    return {"cost_micros": 0, "held_micros": 0, "settled_micros": 0, "estimated_micros": 0,
            "list_cost_micros": 0, "entries": 0}


def _add(total, amount):
    for key in total:
        total[key] += amount[key]
    return total


def _amount(group) -> dict:
    """One grouped row's sums: whole numbers sent as text by the connector.

    Amounts may be negative: a free-allowance credit, or a SAM 3 residual below
    the per-request charges (cost_allocation). A count never is. ``held`` is
    what is counted at reservation (spend unknown), ``settled`` the rest, and
    ``estimated`` the part of settled the ledger re-valued after the call
    (``trued_up``), so a reservation is never shown as spend.
    """
    def whole(key, signed=True):
        value = group[key]
        digits = value[1:] if signed and type(value) is str and value.startswith("-") else value
        if type(value) is str and digits and digits.isascii() and digits.isdigit():
            return int(value)
        if type(value) is int and (signed or value >= 0):
            return value
        raise ValueError("cost_totals_invalid")

    cost = whole("cost_micros")
    held = cost if group["cost_basis"] == HELD else 0
    return {"cost_micros": cost, "held_micros": held, "settled_micros": cost - held,
            "estimated_micros": cost if group["cost_basis"] == TRUED_UP else 0,
            "list_cost_micros": whole("list_cost_micros"), "entries": whole("entries", signed=False)}


def _uuid(value):
    return str(UUID(value)) if value is not None else None


def collection_totals(collections: list[dict], own: dict[str, dict]) -> dict[str, dict]:
    """Each collection's own sums plus every descendant's, over the parentId tree.

    A parent that is not a listed collection makes a root. A cycle is refused.
    """
    parents = {item["collection_id"]: item["parent_id"] for item in collections}
    for start in parents:
        seen, at = set(), start
        while at in parents:
            if at in seen:
                raise ValueError("collection_tree_cycle")
            seen.add(at)
            at = parents[at]
    totals = {ident: _zero() for ident in parents}
    for ident, amount in own.items():
        at = ident
        while at in parents:
            _add(totals[at], amount)
            at = parents[at]
    return totals


def cost_report(organization_id: str, from_month: str, to_month: str,
                collections: list[dict], groups: list[dict], meter: dict | None = None) -> dict:
    """The contract body of ``GET /v1/organizations/{organization_id}/costs``.

    ``collections`` are the organization's collections ({"id", "name",
    "parentId"}); ``groups`` are CostTotalsV1's sums per (collection, month,
    stage, source, kind, provider, resource, cost basis); ``meter`` is how far
    the shared-cost allocation has run (cost_allocation.meter). Caps are not
    built yet: they are null.
    """
    months = months_between(from_month, to_month)
    listed = [{"collection_id": _uuid(item["id"]), "name": item.get("name"),
               "parent_id": _uuid(item.get("parentId"))} for item in collections]
    known = {item["collection_id"] for item in listed}
    own: dict[str, dict] = {}
    by_month = {month: {"totals": _zero(), "stages": {}} for month in months}
    models: dict[tuple, dict] = {}
    totals, updated = _zero(), None
    for group in groups:
        collection, month = _uuid(group["collection_id"]), group["month"]
        if month not in by_month:
            raise ValueError("cost_totals_invalid")
        amount = _amount(group)
        if collection not in known:
            # No such collection is listed: kept, so the organization's totals add up.
            listed.append({"collection_id": collection, "name": None, "parent_id": None})
            known.add(collection)
        _add(own.setdefault(collection, _zero()), amount)
        _add(totals, amount)
        _add(by_month[month]["totals"], amount)
        _add(by_month[month]["stages"].setdefault(group["stage"], _zero()), amount)
        if group["kind"] in KINDS:
            key = (month, group["stage"], group["provider"], group["resource"])
            _add(models.setdefault(key, _zero()), amount)
        if group.get("updated_at") and (updated is None or group["updated_at"] > updated):
            updated = group["updated_at"]
    rolled = collection_totals(listed, own)
    return {
        "organization_id": str(UUID(organization_id)),
        "currency": "USD",
        "from_month": months[0],
        "to_month": months[-1],
        "updated_at": updated,
        "totals": totals,
        "organization_cap": None,
        "collections": [
            {**item, "own": own.get(item["collection_id"], _zero()),
             "total": rolled[item["collection_id"]], "cap": None}
            for item in sorted(listed, key=lambda item: (item["name"] or "", item["collection_id"]))
        ],
        "months": [
            {"month": month, "totals": by_month[month]["totals"],
             "stages": [{"stage": stage, **amount}
                        for stage, amount in sorted(by_month[month]["stages"].items())]}
            for month in months
        ],
        "models": [
            {"month": month, "stage": stage, "provider": provider, "resource": resource, **amount}
            for (month, stage, provider, resource), amount in sorted(models.items())
        ],
        "meter": meter,
    }
