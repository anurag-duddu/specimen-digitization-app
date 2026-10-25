"""The cost meter's allocation job, run by the worker at each collection's drain (COST_METER.md, PR 3).

Right after the cost sweep, under the collection's fence and before any run is
stepped, the worker allocates every complete billing day after the
collection's cursor (at most ALLOCATION_DAYS a pass): it reads Cloud
Monitoring for the invoice month so far, reads the deployment's
per-collection measures for the day (CostAllocationInputsV1), writes this
collection's rows (UpsertCostAllocationsV1) and then moves the cursor past
that day. Each pass also allocates the last REALLOCATE_DAYS complete days
already allocated again, by the same ids, so a paid call recorded late
counts; it never moves the cursor back. It runs only when this drain's sweep
completed its pass: until the ledger's paid calls are caught up, a SAM 3
residual would be computed against charges still missing. It is bounded by a
time budget and fails open: a failure is logged by code, nothing more is
written, and the drain goes on as it would have. Before the owner's
``--cost-meter-only`` setup the worker may not read Monitoring: one warning,
``cost_allocation_monitoring_unavailable``, no row and no cursor change.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5

from .cost_ledger import SAM_DIRECT_RULES
from .storage import Conflict, Missing

LOGGER = logging.getLogger(__name__)
CURSOR_KIND = "worker_cursor"  # The worker's own state documents, one actor only.
ALLOCATION_SECONDS = 45
ALLOCATION_DAYS = 7
ROWS_PER_CALL = 200
OPERATIONS = ("cost_allocation_inputs", "send_cost_allocations", "document", "put_document")
UNAVAILABLE = "cost_allocation_monitoring_unavailable"
WAITING = "cost_allocation_waiting_for_sweep"


class _OutOfTime(Exception):
    """The budget ran out; the day under way is allocated again next time."""


def cursor_id(scope) -> str:
    return str(uuid5(NAMESPACE_URL, f"cost-meter-allocation:{scope.organization_id}/{scope.collection_id}"))


def _code(error) -> str:
    from ..process_logging import log_code

    text = str(error)
    return log_code(text if text.startswith(("cost_", "http_")) else type(error).__name__)


def job_name(value: str) -> tuple[str, str] | None:
    """(project, job) of ``projects/P/locations/L/jobs/J``, or None."""
    from .lane_dispatch import JOB_NAME

    if not value or not JOB_NAME.fullmatch(value):
        return None
    parts = value.split("/")
    return parts[1], parts[5]


class CostAllocator:
    """One worker execution's allocation: Monitoring is read once and shared by its collections."""

    def __init__(self, monitoring, *, job: str, bucket: str | None, clock=None, table=None,
                 seconds=ALLOCATION_SECONDS, days=ALLOCATION_DAYS):
        self.monitoring, self.job, self.bucket = monitoring, job, bucket
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.table, self.seconds, self.days = table, seconds, days
        self._usage = None
        self._inputs: dict[date, list] = {}
        self._stopped: str | None = None  # Set once Monitoring cannot be read this execution.

    @classmethod
    def from_env(cls, env):
        """The drain's allocator, or None when its job or bucket is not configured. Never raises."""
        try:
            from .cost_monitoring import MonitoringClient

            named = job_name(env.get("SPECIMEN_WORKER_JOB", ""))
            if named is None:
                return None
            project, job = named
            return cls(MonitoringClient(project), job=job, bucket=env.get("SPECIMEN_GCS_BUCKET") or None)
        except Exception as error:  # noqa: BLE001 - the meter never stops the drain
            LOGGER.warning("cost allocation not configured: %s", type(error).__name__)
            return None

    def _cursor(self, repository, scope) -> tuple[int, date | None, str | None]:
        """The revision, the last day allocated and the direct SAM 3 rules it was allocated under."""
        from .lane_worker import stored_integer

        try:
            stored = repository.document(scope, CURSOR_KIND, cursor_id(scope))
        except Missing:
            return 0, None, None
        revision = stored_integer(stored["revision"])
        through = stored.get("allocated_through")
        try:
            return revision, date.fromisoformat(through), stored.get("direct_rules")
        except (TypeError, ValueError):
            raise Conflict("cost_allocation_cursor_unreadable") from None

    def _read_usage(self, start, end, stop_at):
        from .cost_monitoring import read_usage

        if self._usage is None or not self._usage.covers(start, end):
            if self._usage is not None:
                start, end = min(start, self._usage.start), max(end, self._usage.end)
            self._usage = read_usage(self.monitoring, start, end, bucket=self.bucket, stop_at=stop_at)
        return self._usage

    def _tenants(self, repository, scope, day):
        from .cost_allocation import MAX_GAP_SECONDS, day_bounds, month_start, tenants

        if day not in self._inputs:
            start, end = day_bounds(day)
            first, _ = day_bounds(month_start(day))
            self._inputs[day] = tenants(repository.cost_allocation_inputs(scope, start, end, first, MAX_GAP_SECONDS))
        return self._inputs[day]

    def run(self, repository, scope, *, job_collections=(), stop=None, until=None, swept=False) -> dict:
        """Allocate the collection's due days and its recent days again; never raises.

        ``swept`` says this drain's cost sweep completed its pass, so the
        ledger holds the collection's paid calls; without it nothing is read
        or written. ``until`` ends the pass early.
        """
        from .cost_allocation import allocate_day, day_bounds, due_days, month_start, reallocation_days

        result = {"status": "unsupported", "days": 0, "reallocated": 0, "rows": 0, "through": None}
        if not all(callable(getattr(repository, name, None)) for name in OPERATIONS):
            return result
        if self._stopped:
            return {**result, "status": self._stopped}
        if not swept:
            LOGGER.info("cost allocation skipped: %s", WAITING)
            return {**result, "status": "waiting_for_sweep"}
        started = self.clock()
        stop_at = started + timedelta(seconds=self.seconds)
        if until is not None:
            stop_at = min(stop_at, until)

        def out_of_time():
            return (stop is not None and stop.is_set()) or self.clock() >= stop_at

        try:
            from .cost_allocation import zone

            zone()
        except Exception:  # noqa: BLE001 - no tz database in this image: nothing to allocate by
            LOGGER.warning("cost allocation stopped: cost_allocation_time_zone_unavailable")
            self._stopped = "failed"
            return {**result, "status": "failed"}
        try:
            revision, through, rules = self._cursor(repository, scope)
        except Exception as error:  # noqa: BLE001 - the meter never stops the drain
            LOGGER.warning("cost allocation stopped: %s", _code(error))
            return {**result, "status": "failed"}
        result.update(status="current", through=through and through.isoformat())
        if through is not None and rules != SAM_DIRECT_RULES:
            # Its days were allocated against direct SAM 3 rows valued another way:
            # allocated again from the first day, by the same ids, the cursor with them.
            LOGGER.info("cost allocation: direct SAM 3 rules changed; allocating again from the first day")
            through = None
        now = self.clock()
        days = due_days(through, now, self.days)
        # Already allocated, so before every due day: written again, the cursor left as it is.
        again = reallocation_days(through, now)
        if not days and not again:
            return result
        mine = (scope.organization_id, scope.collection_id)
        served = sorted({tuple(key) for key in job_collections} | {mine})
        result["status"] = "partial"
        try:
            if out_of_time():
                raise _OutOfTime()
            ordered = again + days
            usage = self._read_usage(day_bounds(month_start(ordered[0]))[0], day_bounds(ordered[-1])[1], stop_at)
            for day in ordered:
                if out_of_time():
                    raise _OutOfTime()
                collections = self._tenants(repository, scope, day)
                rows = [row for row in allocate_day(day, collections, usage, self.table, job=self.job,
                                                    job_collections=served, bucket=self.bucket)
                        if (row["organization_id"], row["collection_id"]) == mine]
                for at in range(0, len(rows), ROWS_PER_CALL):
                    result["rows"] += repository.send_cost_allocations(scope, rows[at:at + ROWS_PER_CALL])
                if day in again:
                    result["reallocated"] += 1
                    continue
                # The cursor moves only once every row of the day is written.
                stored = repository.put_document(
                    scope, CURSOR_KIND, cursor_id(scope),
                    {"sensitive": False, "allocated_through": day.isoformat(),
                     "direct_rules": SAM_DIRECT_RULES}, revision)
                revision = stored["revision"]
                result["days"] += 1
                result["through"] = day.isoformat()
            last = days[-1] if days else through
            result["status"] = "partial" if due_days(last, self.clock(), 1) else "complete"
        except _OutOfTime:
            pass
        except Exception as error:  # noqa: BLE001 - the meter never stops the drain
            from .cost_monitoring import MonitoringFailed, MonitoringUnavailable, OutOfTime

            if isinstance(error, OutOfTime):
                return result
            if isinstance(error, MonitoringUnavailable):
                self._stopped = "monitoring_unavailable"
                LOGGER.warning("cost allocation stopped: %s", UNAVAILABLE)
                return {**result, "status": self._stopped}
            if isinstance(error, MonitoringFailed):
                self._stopped = "failed"
            LOGGER.warning("cost allocation stopped: %s", _code(error))
            result["status"] = "failed"
        return result
