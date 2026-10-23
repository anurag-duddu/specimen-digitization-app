"""Shared Google costs split across tenants by measured usage (COST_METER.md, PR 3).

Pure: no I/O. ``allocate_day`` turns one billing day's Cloud Monitoring
readings (``Usage``) and the deployment's per-collection measures
(``Tenant``, from CostAllocationInputsV1) into CostEntry allocation rows, one
per collection, service and method, with the free allowance as negative credit
rows. The same inputs always give the same rows, so each worker writes the
same values for the collections it serves.

A billing day is a calendar day in BILLING_ZONE (Google's billing report
starts its days at midnight US Pacific time). Every reading is hourly, so a
23- or 25-hour day is its own hours. A row's ``occurred_at`` is the day's start
in UTC; its UTC month is the Pacific invoice month, since Pacific midnight is
07:00 or 08:00 UTC of the same date.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_FLOOR, ROUND_HALF_EVEN, Decimal, localcontext
from functools import lru_cache
from pathlib import Path
from typing import Mapping
from uuid import UUID

from .projection import derived_id

BILLING_ZONE = "America/Los_Angeles"
# A day is allocated once it ended this long ago: Cloud Run metrics show within
# minutes, and paid calls reach the ledger with their run's saves.
COMPLETE_AFTER = timedelta(hours=3)
# The first billing day the meter allocates.
FIRST_DAY = date(2026, 10, 1)
# Every pass allocates the last this many complete days again, by the same ids,
# so a paid call or a save recorded after its day was first allocated counts.
REALLOCATE_DAYS = 2
# A gap between two of a worker's saves counts at most this long: the longest
# step lease a profile may set (domain.ExecutionPolicy.lease_seconds, le=900).
MAX_GAP_SECONDS = 900
HOUR = timedelta(hours=1)
MILLION = Decimal(1_000_000)
GIB = Decimal(2**30)
PRICES = Path(__file__).with_name("profiles") / "infrastructure_prices.json"

SOURCE, KIND, BASIS, PROVIDER = "allocation", "allocation", "allocated", "google_cloud"
SAM_SERVICE, API_SERVICE, DATABASE = "specimen-sam", "specimen-api", "cloud-sql"
WORKER_METHOD = "worker-processing-time"
SAM_METHOD = "sam-residual"
API_METHOD = "api-requests"
STORAGE_METHOD = "storage-bytes"
DATABASE_METHOD = "database-specimens"
FREE_METHOD = "free-allowance"
METHODS = (WORKER_METHOD, SAM_METHOD, API_METHOD, STORAGE_METHOD, DATABASE_METHOD, FREE_METHOD)
# The connector lets only a credit and the SAM 3 residual (when the per-request
# charges came to more than the measured instance time) be negative.
STAGES = {"worker": "worker", SAM_SERVICE: "label_finding", API_SERVICE: "api",
          "storage": "storage", DATABASE: "database"}
BILLABLE_METRIC = "run.googleapis.com/container/billable_instance_time"
REQUEST_METRIC = "run.googleapis.com/request_count"
ORGANIZATION_METRIC_NAME = "specimen_api_requests_by_organization"


class AllocationInputsInvalid(ValueError):
    """The connector's per-collection measures do not have the expected shape."""


@lru_cache(maxsize=1)
def prices() -> dict:
    """The committed infrastructure price file (never the profile's price list)."""
    return json.loads(PRICES.read_text())


@lru_cache(maxsize=1)
def zone():
    from zoneinfo import ZoneInfo

    return ZoneInfo(BILLING_ZONE)


# ---- billing days ----------------------------------------------------------

def day_bounds(day: date) -> tuple[datetime, datetime]:
    """The billing day's start and end, in UTC. Midnight always exists in the zone."""
    following = day + timedelta(days=1)
    start = datetime(day.year, day.month, day.day, tzinfo=zone()).astimezone(timezone.utc)
    end = datetime(following.year, following.month, following.day, tzinfo=zone()).astimezone(timezone.utc)
    return start, end


def day_hours(day: date) -> list[datetime]:
    """The start of every hour of the day, in UTC: 23, 24 or 25 of them."""
    start, end = day_bounds(day)
    return [start + HOUR * index for index in range(int((end - start) / HOUR))]


def billing_day_of(moment: datetime) -> date:
    return moment.astimezone(zone()).date()


def latest_complete_day(now: datetime) -> date:
    """The last billing day that ended at least COMPLETE_AFTER before ``now``."""
    return billing_day_of(now - COMPLETE_AFTER) - timedelta(days=1)


def due_days(through: date | None, now: datetime, limit: int) -> list[date]:
    """The complete days after ``through`` (from FIRST_DAY when none), at most ``limit``."""
    day = FIRST_DAY if through is None else max(FIRST_DAY, through + timedelta(days=1))
    last = latest_complete_day(now)
    days = []
    while day <= last and len(days) < limit:
        days.append(day)
        day += timedelta(days=1)
    return days


def reallocation_days(through: date | None, now: datetime) -> list[date]:
    """The last REALLOCATE_DAYS complete days already allocated (through ``through``).

    Each pass computes them again, so a paid call or save recorded after its
    day was first allocated is reflected; older days' rows stay as written.
    """
    if through is None:
        return []
    last = latest_complete_day(now)
    days = [last - timedelta(days=back) for back in range(REALLOCATE_DAYS - 1, -1, -1)]
    return [day for day in days if FIRST_DAY <= day <= through]


def month_start(day: date) -> date:
    return day.replace(day=1)


def meter(latest_occurred_at: str | None, now: datetime) -> dict:
    """GET .../costs ``meter``: the last day with allocation rows and whether it lags.

    ``behind`` when more than two complete days follow it; ``never_run`` with no
    allocation row at all.
    """
    if latest_occurred_at is None:
        return {"allocated_through": None, "allocation_status": "never_run"}
    moment = datetime.fromisoformat(latest_occurred_at.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    through = billing_day_of(moment)
    lag = (latest_complete_day(now) - through).days
    return {"allocated_through": through.isoformat(), "allocation_status": "behind" if lag > 2 else "ok"}


# ---- inputs ------------------------------------------------------------------

@dataclass(frozen=True)
class Tenant:
    """One collection's measures for a billing day (CostAllocationInputsV1).

    ``worker_seconds`` are the calling worker's processing seconds; the month
    figures run from the invoice month's first day through this day.
    """

    organization_id: str
    collection_id: str
    saves: int = 0
    month_saves: int = 0
    worker_seconds: Decimal = Decimal(0)
    month_worker_seconds: Decimal = Decimal(0)
    sam_seconds: Decimal = Decimal(0)
    month_sam_seconds: Decimal = Decimal(0)
    sam_direct_micros: int = 0
    asset_bytes: int = 0
    specimens: int = 0

    @property
    def key(self) -> tuple[str, str]:
        return (self.organization_id, self.collection_id)


@dataclass(frozen=True)
class Usage:
    """Cloud Monitoring's hourly readings over [start, end), keyed by each hour's UTC start.

    ``services`` and ``jobs`` hold billable instance seconds by Cloud Run service
    and job name; ``requests`` the API's request count; ``organizations`` the
    API's requests by organization (the log-based metric); ``storage`` the
    bucket's mean bytes, priced at ``storage_location``.
    """

    start: datetime
    end: datetime
    services: Mapping[str, Mapping[datetime, Decimal]] = field(default_factory=dict)
    jobs: Mapping[str, Mapping[datetime, Decimal]] = field(default_factory=dict)
    requests: Mapping[datetime, Decimal] = field(default_factory=dict)
    organizations: Mapping[str, Mapping[datetime, Decimal]] = field(default_factory=dict)
    storage: Mapping[datetime, Decimal] = field(default_factory=dict)
    storage_location: str | None = None
    storage_metric: str | None = None

    def covers(self, start: datetime, end: datetime) -> bool:
        return self.start <= start and end <= self.end


def _uuid(value) -> str:
    if not isinstance(value, str):
        raise AllocationInputsInvalid("cost_allocation_inputs_invalid")
    try:
        return str(UUID(value))
    except ValueError:
        raise AllocationInputsInvalid("cost_allocation_inputs_invalid") from None


def _number(value, *, whole=False) -> Decimal:
    """A non-negative amount the connector sends as text (or a JSON number)."""
    if type(value) is bool or not isinstance(value, (str, int, Decimal, float)):
        raise AllocationInputsInvalid("cost_allocation_inputs_invalid")
    try:
        number = Decimal(str(value))
    except ArithmeticError:
        raise AllocationInputsInvalid("cost_allocation_inputs_invalid") from None
    if not number.is_finite() or number < 0 or (whole and number != number.to_integral_value()):
        raise AllocationInputsInvalid("cost_allocation_inputs_invalid")
    return number


def tenants(collections) -> list[Tenant]:
    """The connector's per-collection rows as Tenants, in (organization, collection) order."""
    if not isinstance(collections, list):
        raise AllocationInputsInvalid("cost_allocation_inputs_invalid")
    found = {}
    for item in collections:
        if not isinstance(item, dict):
            raise AllocationInputsInvalid("cost_allocation_inputs_invalid")
        tenant = Tenant(
            organization_id=_uuid(item.get("organization_id")),
            collection_id=_uuid(item.get("collection_id")),
            saves=int(_number(item.get("saves", 0), whole=True)),
            month_saves=int(_number(item.get("month_saves", 0), whole=True)),
            worker_seconds=_number(item.get("worker_seconds", 0)),
            month_worker_seconds=_number(item.get("month_worker_seconds", 0)),
            sam_seconds=_number(item.get("sam_seconds", 0)),
            month_sam_seconds=_number(item.get("month_sam_seconds", 0)),
            sam_direct_micros=int(_number(item.get("sam_direct_micros", 0), whole=True)),
            asset_bytes=int(_number(item.get("asset_bytes", 0), whole=True)),
            specimens=int(_number(item.get("specimens", 0), whole=True)),
        )
        if tenant.key in found:
            raise AllocationInputsInvalid("cost_allocation_inputs_invalid")
        found[tenant.key] = tenant
    return [found[key] for key in sorted(found)]


# ---- arithmetic ----------------------------------------------------------------

def whole(amount: Decimal) -> int:
    """Micro-USD to a whole number, half to even."""
    return int(amount.quantize(Decimal(1), rounding=ROUND_HALF_EVEN))


def split(total: int, weights: Mapping) -> dict:
    """``total`` whole micro-USD (either sign) in proportion to the positive weights.

    The parts add up to ``total`` exactly: each takes its floor and the largest
    remainders take one more micro-USD each, ties by key. A zero part is left out.
    """
    keys = sorted(key for key, weight in weights.items() if weight > 0)
    if not keys or total == 0:
        return {}
    sign, amount = (-1 if total < 0 else 1), abs(total)
    with localcontext() as context:
        context.prec = 60
        whole_weight = sum((Decimal(weights[key]) for key in keys), Decimal(0))
        exact = {key: Decimal(amount) * Decimal(weights[key]) / whole_weight for key in keys}
        parts = {key: int(exact[key].to_integral_value(rounding=ROUND_FLOOR)) for key in keys}
        left = amount - sum(parts.values())
        for key in sorted(keys, key=lambda key: (-(exact[key] - parts[key]), key))[:left]:
            parts[key] += 1
    return {key: sign * part for key, part in parts.items() if part}


def choose(day: Mapping, month: Mapping, even) -> tuple[dict, str | None]:
    """The day's weights; else the month's so far; else equal weights over ``even``."""
    if any(weight > 0 for weight in day.values()):
        return dict(day), "day"
    if any(weight > 0 for weight in month.values()):
        return dict(month), "month"
    even = sorted(set(even))
    if even:
        return {key: Decimal(1) for key in even}, "even"
    return {}, None


def _text(value) -> str:
    return format(Decimal(value).normalize(), "f") if Decimal(value) else "0"


def _hourly(series: Mapping[datetime, Decimal], day: date) -> list[Decimal]:
    return [Decimal(series.get(hour, 0)) for hour in day_hours(day)]


def _carried(series: Mapping[datetime, Decimal], day: date) -> list[Decimal]:
    """A gauge's hourly values over the day, each empty hour holding the last earlier value.

    Cloud Storage measures bytes once a day and repeats the value; a bucket
    with no object has no series at all, so no value before an hour is zero.
    """
    known = sorted(series.items())
    values, at, last = [], 0, Decimal(0)
    for hour in day_hours(day):
        while at < len(known) and known[at][0] <= hour:
            last = Decimal(known[at][1])
            at += 1
        values.append(last)
    return values


# ---- the day's measured usage --------------------------------------------------

def _per_second(shape: dict, rates: dict) -> Decimal:
    """Micro-USD per second of one instance of this shape at these rates."""
    return (Decimal(shape["vcpus"]) * Decimal(rates["vcpu_micros_per_million_seconds"])
            + Decimal(shape["memory_gib"]) * Decimal(rates["gib_micros_per_million_seconds"])) / MILLION


def _pool_draws(day: date, usage: Usage, table: dict) -> dict:
    """Units of each free-tier pool each service drew on ``day``.

    Instance-based: SAM 3 and every Cloud Run job (jobs bill at instance-based
    rates; that they share one pool with instance-based services is assumed).
    Request-based: the API.
    """
    run = table["cloud_run"]
    draws = {"instance_based": {"vcpu_seconds": {}, "gib_seconds": {}},
             "request_based": {"vcpu_seconds": {}, "gib_seconds": {}, "requests": {}}}
    sam = run["services"][SAM_SERVICE]
    seconds = sum(_hourly(usage.services.get(SAM_SERVICE, {}), day), Decimal(0))
    draws["instance_based"]["vcpu_seconds"][SAM_SERVICE] = seconds * Decimal(sam["vcpus"])
    draws["instance_based"]["gib_seconds"][SAM_SERVICE] = seconds * Decimal(sam["memory_gib"])
    for job, series in sorted(usage.jobs.items()):
        seconds = sum(_hourly(series, day), Decimal(0))
        draws["instance_based"]["vcpu_seconds"]["job:" + job] = seconds * Decimal(run["jobs"]["vcpus"])
        draws["instance_based"]["gib_seconds"]["job:" + job] = seconds * Decimal(run["jobs"]["memory_gib"])
    api = run["services"][API_SERVICE]
    seconds = sum(_hourly(usage.services.get(API_SERVICE, {}), day), Decimal(0))
    draws["request_based"]["vcpu_seconds"][API_SERVICE] = seconds * Decimal(api["vcpus"])
    draws["request_based"]["gib_seconds"][API_SERVICE] = seconds * Decimal(api["memory_gib"])
    draws["request_based"]["requests"][API_SERVICE] = sum(_hourly(usage.requests, day), Decimal(0))
    return draws


RATE_KEYS = {"vcpu_seconds": "vcpu_micros_per_million_seconds", "gib_seconds": "gib_micros_per_million_seconds",
             "requests": "request_micros_per_million"}


def allowance(day: date, usage: Usage, table: dict) -> tuple[dict, dict]:
    """Each service's free-tier credit on ``day`` (micro-USD), and how the pools stood.

    The monthly pools are drawn chronologically from the invoice month's first
    day; a day that would overdraw a pool takes what is left, shared by the
    services in proportion to what each drew that day. The credit is the
    consumed units at the pool's Tier 1 rates (Google applies the free tier as
    a spending-based discount at Tier 1 prices).
    """
    run = table["cloud_run"]
    remaining = {pool: {unit: Decimal(amount) for unit, amount in units.items()}
                 for pool, units in run["free_tier"].items()}
    credits: dict[str, Decimal] = {}
    pools: dict = {}
    at = month_start(day)
    while at <= day:
        draws = _pool_draws(at, usage, table)
        for pool, units in draws.items():
            for unit, by_service in units.items():
                drawn = sum(by_service.values(), Decimal(0))
                before = remaining[pool][unit]
                taken = min(before, drawn)
                remaining[pool][unit] = before - taken
                if at != day:
                    continue
                pools.setdefault(pool, {})[unit] = {
                    "remaining_before": _text(before), "drawn": _text(drawn), "consumed": _text(taken),
                    "remaining_after": _text(before - taken)}
                if drawn <= 0:
                    continue
                rate = Decimal(run[pool][RATE_KEYS[unit]]) / MILLION
                for service, units_drawn in by_service.items():
                    credits[service] = credits.get(service, Decimal(0)) + taken * units_drawn / drawn * rate
        at += timedelta(days=1)
    return credits, pools


# ---- rows ----------------------------------------------------------------------

def _row(day, key, resource, stage, method, cost, list_cost, usage, details, table) -> dict:
    organization_id, collection_id = key
    start, _ = day_bounds(day)
    return {
        "organization_id": organization_id,
        "collection_id": collection_id,
        "id": derived_id("cost-allocation", day.isoformat(), resource, collection_id, method),
        "source": SOURCE,
        "specimen_id": None,
        "run_id": None,
        "step": "allocation:" + resource,
        "stage": stage,
        "attempt": 1,
        "kind": KIND,
        "ordinal": 0,
        "provider": PROVIDER,
        "resource": resource,
        "usage": usage,
        "reserved_micros": None,
        "cost_micros": cost,
        "list_cost_micros": list_cost,
        "cost_basis": BASIS,
        "outcome": None,
        "failure_code": None,
        "price_list_version": table["version"],
        "price_list_as_of": table["as_of"],
        "occurred_at": start.isoformat(),
        "month": start.strftime("%Y-%m"),
        "billing_day": day.isoformat(),
        "allocation_method_id": method,
        "allocation_method_details": details,
    }


def _window(day: date) -> dict:
    start, end = day_bounds(day)
    return {"billing_day": day.isoformat(), "time_zone": BILLING_ZONE, "start": start.isoformat(),
            "end": end.isoformat(), "hours": len(day_hours(day)),
            # Computed again at every pass while among the last complete days; then left as written.
            "reallocated_while_within_last_days": REALLOCATE_DAYS}


def _share(measure, basis, weights, key) -> dict:
    return {"measure": measure, "basis": basis, "numerator": _text(weights.get(key, 0)),
            "denominator": _text(sum((Decimal(value) for value in weights.values() if value > 0), Decimal(0)))}


def _credit_rows(day, resource, stage, credit, weights, measure, basis, usage_of, pools, pool, table, extra=None):
    """The service's credit as negative rows, split like the service's own cost."""
    amount = whole(credit)
    rows = []
    for key, part in sorted(split(-amount, weights).items()):
        details = {**_window(day), "service": resource, "pool": pool, "pools": pools.get(pool, {}),
                   "credit_micros": amount, "share": _share(measure, basis, weights, key),
                   "note": "Cloud Run's monthly free tier, drawn day by day from the invoice month's first day by "
                           "this project's usage; Cloud Run jobs are assumed to share the instance-based pool.",
                   **(extra(key) if extra else {})}
        rows.append(_row(day, key, resource, stage, FREE_METHOD, part, 0, usage_of(key), details, table))
    return rows


def _number_out(value: Decimal):
    value = Decimal(value)
    return int(value) if value == value.to_integral_value() else float(value)


def allocate_day(day: date, collections: list[Tenant], usage: Usage, table: dict | None = None, *,
                 job: str | None, job_collections=(), bucket: str | None) -> list[dict]:
    """Every allocation row of ``day`` for every collection, deterministically.

    ``job`` is the Cloud Run job whose actor's saves gave ``worker_seconds``;
    ``job_collections`` the collections it serves (its even fallback);
    ``bucket`` the Cloud Storage bucket the storage readings are of.
    """
    table = table or prices()
    run = table["cloud_run"]
    start, end = day_bounds(day)
    if not usage.covers(month_start_bounds(day), end):
        raise ValueError("cost_allocation_usage_incomplete")
    by_key = {tenant.key: tenant for tenant in collections}
    everyone = sorted(by_key)
    credits, pools = allowance(day, usage, table)
    window = _window(day)
    rows: list[dict] = []

    # 1. The worker job: its billable time, split by each collection's processing time.
    if job:
        hourly = _hourly(usage.jobs.get(job, {}), day)
        seconds = sum(hourly, Decimal(0))
        rate = _per_second(run["jobs"], run["instance_based"])
        listed = seconds * rate
        weights, basis = choose({key: t.worker_seconds for key, t in by_key.items()},
                                {key: t.month_worker_seconds for key, t in by_key.items()}, job_collections)
        measure = "the job's processing seconds: gaps between its actor's consecutive saves, each at most " \
                  f"{MAX_GAP_SECONDS} s, counted to the collection of the save that ends it"

        def worker_usage(key):
            tenant = by_key.get(key)
            value = Decimal(0) if tenant is None else (
                tenant.month_worker_seconds if basis == "month" else tenant.worker_seconds)
            return {"processing_seconds": _number_out(value)}

        total = whole(listed)
        for key, part in sorted(split(total, weights).items()):
            details = {**window, "service": job, "metric": BILLABLE_METRIC, "resource_type": "cloud_run_job",
                       "hourly_seconds": [_text(value) for value in hourly], "billable_seconds": _text(seconds),
                       "rate_micros_per_second": _text(rate), "list_micros": _text(listed),
                       "allocated_micros": total, "share": _share(measure, basis, weights, key),
                       "note": {"day": "split by the day's processing time",
                                "month": "no save by the job's actor this day: split by the month's so far",
                                "even": "no save by the job's actor this month: split evenly over its collections"
                                }[basis]}
            rows.append(_row(day, key, job, STAGES["worker"], WORKER_METHOD, part, part, worker_usage(key),
                             details, table))
        rows += _credit_rows(day, job, STAGES["worker"], credits.get("job:" + job, Decimal(0)), weights,
                             measure, basis, worker_usage, pools, "instance_based", table)

    # 2. SAM 3: the measured instance time less what its requests already paid.
    hourly = _hourly(usage.services.get(SAM_SERVICE, {}), day)
    seconds = sum(hourly, Decimal(0))
    rate = _per_second(run["services"][SAM_SERVICE], run["instance_based"])
    listed = seconds * rate
    direct = sum(t.sam_direct_micros for t in collections)
    residual = whole(listed) - direct
    weights, basis = choose({key: t.sam_seconds for key, t in by_key.items()},
                            {key: t.month_sam_seconds for key, t in by_key.items()}, everyone)
    measure = "SAM 3 request seconds of the collection's paid calls (usage.instance.request_seconds, else usage.seconds)"

    def sam_usage(key):
        tenant = by_key[key]
        value = tenant.month_sam_seconds if basis == "month" else tenant.sam_seconds
        return {"request_seconds": _number_out(value)}

    for key, part in sorted(split(residual, weights).items()):
        details = {**window, "service": SAM_SERVICE, "metric": BILLABLE_METRIC, "resource_type": "cloud_run_revision",
                   "hourly_seconds": [_text(value) for value in hourly], "billable_seconds": _text(seconds),
                   "rate_micros_per_second": _text(rate), "list_micros": _text(listed),
                   "direct_micros": direct, "allocated_micros": residual,
                   "share": _share(measure, basis, weights, key),
                   "note": ("the residual is the measured instance time at instance-based rates less the day's "
                            "direct SAM 3 charges in the ledger; negative when the per-request charges came to "
                            "more. billable_instance_time counts time, so the startup CPU boost's extra vCPU is "
                            "not in it.")}
        rows.append(_row(day, key, SAM_SERVICE, STAGES[SAM_SERVICE], SAM_METHOD, part, part, sam_usage(key),
                         details, table))
    rows += _credit_rows(day, SAM_SERVICE, STAGES[SAM_SERVICE], credits.get(SAM_SERVICE, Decimal(0)), weights,
                         measure, basis, sam_usage, pools, "instance_based", table)

    # 3. The API: its billable time and requests, split by organization, then by collection.
    rows += _api_rows(day, collections, usage, table, credits, pools)

    # 4. Storage: the bucket's mean bytes at the location's Standard rate.
    rows += _storage_rows(day, collections, usage, table, bucket)

    # 5. The database: the instance's list price for the day's hours, by specimens held.
    sql = table["cloud_sql"]
    hours = len(day_hours(day))
    per_hour = Decimal(sql["instance_micros_per_hour"]) + (
        Decimal(sql["storage_gib"]) * Decimal(sql["ssd_micros_per_gib_month"]) / Decimal(sql["hours_per_month"]))
    listed = per_hour * hours
    weights, basis = choose({key: Decimal(t.specimens) for key, t in by_key.items()}, {}, everyone)
    total = whole(listed)
    for key, part in sorted(split(total, weights).items()):
        details = {**window, "service": DATABASE, "machine": sql["machine"], "storage_gib": sql["storage_gib"],
                   "rate_micros_per_hour": _text(per_hour), "list_micros": _text(listed), "allocated_micros": total,
                   "share": _share("specimens held at the day's end", basis, weights, key),
                   "note": ("Firebase Data Connect's default Cloud SQL instance, priced as db-f1-micro with 10 GiB "
                            "SSD at the stated list rate; a Data Connect no-cost trial may make the bill zero, "
                            "which the monthly reconciliation checks.")}
        rows.append(_row(day, key, DATABASE, STAGES[DATABASE], DATABASE_METHOD, part, part,
                         {"specimens": by_key[key].specimens}, details, table))
    return rows


def month_start_bounds(day: date) -> datetime:
    """The UTC start of the invoice month that holds ``day``."""
    return day_bounds(month_start(day))[0]


def _api_rows(day, collections, usage, table, credits, pools) -> list[dict]:
    run = table["cloud_run"]
    by_key = {tenant.key: tenant for tenant in collections}
    hourly_seconds = _hourly(usage.services.get(API_SERVICE, {}), day)
    hourly_requests = _hourly(usage.requests, day)
    seconds, requests = sum(hourly_seconds, Decimal(0)), sum(hourly_requests, Decimal(0))
    rate = _per_second(run["services"][API_SERVICE], run["request_based"])
    fee = Decimal(run["request_based"]["request_micros_per_million"]) / MILLION
    listed = seconds * rate + requests * fee
    organizations = sorted({tenant.organization_id for tenant in collections})
    members = {organization: sorted(key for key in by_key if key[0] == organization) for organization in organizations}
    counted = {organization: sum(_hourly(usage.organizations.get(organization, {}), day), Decimal(0))
               for organization in organizations}
    if any(value > 0 for value in counted.values()):
        org_weights, org_basis, org_measure = counted, "requests", "the organization's API requests (log-based metric)"
    else:
        org_weights, org_basis = choose(
            {organization: Decimal(sum(by_key[key].saves for key in members[organization]))
             for organization in organizations},
            {organization: Decimal(sum(by_key[key].month_saves for key in members[organization]))
             for organization in organizations}, organizations)
        org_measure = "no request was counted by organization: the organization's saves"
    inner: dict = {}
    for organization in organizations:
        inner[organization] = choose({key: Decimal(by_key[key].saves) for key in members[organization]},
                                     {key: Decimal(by_key[key].month_saves) for key in members[organization]},
                                     members[organization])

    def two_level(total):
        parts = {}
        for organization, amount in split(total, org_weights).items():
            weights, _ = inner[organization]
            parts.update(split(amount, weights))
        return parts

    def api_usage(key):
        return {"organization_requests": _number_out(counted.get(key[0], 0)), "saves": by_key[key].saves}

    def share(key):
        weights, basis = inner[key[0]]
        return {"share": {"organization": _share(org_measure, org_basis, org_weights, key[0]),
                          "collection": _share("the collection's saves", basis, weights, key)}}

    rows = []
    total = whole(listed)
    for key, part in sorted(two_level(total).items()):
        details = {**_window(day), "service": API_SERVICE, "metric": BILLABLE_METRIC,
                   "request_metric": REQUEST_METRIC, "hourly_seconds": [_text(value) for value in hourly_seconds],
                   "hourly_requests": [_text(value) for value in hourly_requests], "billable_seconds": _text(seconds),
                   "requests": _text(requests), "rate_micros_per_second": _text(rate),
                   "fee_micros_per_request": _text(fee), "list_micros": _text(listed), "allocated_micros": total,
                   **share(key)}
        rows.append(_row(day, key, API_SERVICE, STAGES[API_SERVICE], API_METHOD, part, part, api_usage(key),
                         details, table))
    credit = whole(credits.get(API_SERVICE, Decimal(0)))
    for key, part in sorted(two_level(-credit).items()):
        details = {**_window(day), "service": API_SERVICE, "pool": "request_based",
                   "pools": pools.get("request_based", {}), "credit_micros": credit,
                   "note": "Cloud Run's monthly free tier, drawn day by day from the invoice month's first day by "
                           "this project's usage.", **share(key)}
        rows.append(_row(day, key, API_SERVICE, STAGES[API_SERVICE], FREE_METHOD, part, 0, api_usage(key),
                         details, table))
    return rows


def _storage_rows(day, collections, usage, table, bucket) -> list[dict]:
    storage = table["cloud_storage"]
    if not bucket:
        return []
    location = (usage.storage_location or "").lower()
    hourly = _carried(usage.storage, day)
    mean = sum(hourly, Decimal(0)) / len(hourly)
    if mean <= 0:
        return []
    rate = storage["standard_micros_per_gib_month"].get(location)
    if rate is None:
        raise ValueError("cost_allocation_storage_location_unpriced")
    hours = len(hourly)
    listed = mean / GIB * Decimal(rate) * hours / Decimal(storage["hours_per_month"])
    by_key = {tenant.key: tenant for tenant in collections}
    weights, basis = choose({key: Decimal(t.asset_bytes) for key, t in by_key.items()}, {}, sorted(by_key))
    total = whole(listed)
    rows = []
    for key, part in sorted(split(total, weights).items()):
        details = {**_window(day), "service": bucket, "metric": usage.storage_metric, "location": location,
                   "hourly_bytes": [_text(value) for value in hourly], "mean_bytes": _text(mean),
                   "rate_micros_per_gib_month": rate, "hours_per_month": storage["hours_per_month"],
                   "list_micros": _text(listed), "allocated_micros": total,
                   "share": _share("bytes of the collection's source assets at the day's end", basis, weights, key),
                   "note": "Standard storage; the bucket's bytes include soft-deleted and noncurrent objects "
                           "when the v2 metric is read."}
        rows.append(_row(day, key, bucket, STAGES["storage"], STORAGE_METHOD, part, part,
                         {"bytes": by_key[key].asset_bytes}, details, table))
    return rows
