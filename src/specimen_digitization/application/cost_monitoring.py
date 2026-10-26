"""Cloud Monitoring's hourly readings for the cost meter's allocation (COST_METER.md, PR 3).

Reads ``projects.timeSeries.list`` through ``google.auth.default`` and an
``AuthorizedSession``, as ``lane_dispatch.CloudRunJobDispatcher`` starts jobs:
no client library. Every query aligns each series to hours (``ALIGN_SUM`` for
the counters, ``ALIGN_MEAN`` for the storage gauge) and leaves the grouping to
Python, so no cross-series reducer or group-by field is sent. A 401 or 403 means
the worker may not read Monitoring (the owner's ``--cost-meter-only`` setup has
not run): ``MonitoringUnavailable``. A 404 is a metric with no data yet (the
log-based metric before it exists): no series.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from .cost_allocation import (
    API_SERVICE, BILLABLE_METRIC, ORGANIZATION_METRIC_NAME, REQUEST_METRIC, SAM_SERVICE, Usage,
)

MONITORING_API = "https://monitoring.googleapis.com/v3/"
SCOPES = ["https://www.googleapis.com/auth/monitoring.read"]
STORAGE_V2 = "storage.googleapis.com/storage/v2/total_bytes"
STORAGE_V1 = "storage.googleapis.com/storage/total_bytes"
PAGE_SIZE = 1000
MAX_PAGES = 20


class MonitoringUnavailable(Exception):
    """The worker's identity may not read Cloud Monitoring (HTTP 401 or 403)."""


class MonitoringFailed(Exception):
    """A read failed for any other reason; the code names it, never a response body."""


class OutOfTime(Exception):
    """The caller's budget ran out between two reads."""


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _moment(value) -> datetime:
    """An RFC 3339 time as Monitoring writes it (Z, up to nanoseconds)."""
    if not isinstance(value, str) or not value.endswith("Z"):
        raise MonitoringFailed("cost_allocation_monitoring_invalid")
    head, _, fraction = value[:-1].partition(".")
    if not fraction.isdigit() and fraction:
        raise MonitoringFailed("cost_allocation_monitoring_invalid")
    try:
        moment = datetime.fromisoformat(head).replace(tzinfo=timezone.utc)
    except ValueError:
        raise MonitoringFailed("cost_allocation_monitoring_invalid") from None
    # Nanoseconds past the last whole microsecond round up: only the hour is read.
    micros = int(fraction[:6].ljust(6, "0")) + (1 if fraction[6:].strip("0") else 0)
    return moment + timedelta(microseconds=micros)


def _value(point) -> Decimal:
    value = point.get("value") if isinstance(point, dict) else None
    if not isinstance(value, dict):
        raise MonitoringFailed("cost_allocation_monitoring_invalid")
    raw = value.get("doubleValue", value.get("int64Value"))
    if type(raw) is bool or not isinstance(raw, (str, int, float, Decimal)):
        raise MonitoringFailed("cost_allocation_monitoring_invalid")
    try:
        number = Decimal(str(raw))
    except ArithmeticError:
        raise MonitoringFailed("cost_allocation_monitoring_invalid") from None
    if not number.is_finite() or number < 0:
        raise MonitoringFailed("cost_allocation_monitoring_invalid")
    return number


def hour_of(end: datetime) -> datetime:
    """The UTC hour an aligned point covers: the hour holding the instant just before its end."""
    before = end - timedelta(microseconds=1)
    return before.replace(minute=0, second=0, microsecond=0)


def hourly(series: list, key=None) -> dict:
    """{key: {hour start: summed value}} over the series; ``key(series)`` None skips one."""
    found: dict = {}
    for item in series:
        if not isinstance(item, dict) or not isinstance(item.get("points", []), list):
            raise MonitoringFailed("cost_allocation_monitoring_invalid")
        name = key(item) if key else None
        if key and name is None:
            continue
        target = found.setdefault(name, {})
        for point in item.get("points", []):
            interval = point.get("interval") if isinstance(point, dict) else None
            if not isinstance(interval, dict):
                raise MonitoringFailed("cost_allocation_monitoring_invalid")
            hour = hour_of(_moment(interval.get("endTime")))
            target[hour] = target.get(hour, Decimal(0)) + _value(point)
    return found


def _labels(item, part) -> dict:
    labels = (item.get(part) or {}).get("labels") or {}
    return labels if isinstance(labels, dict) else {}


def _organization(item):
    value = _labels(item, "metric").get("organization_id")
    try:
        return str(UUID(value)) if isinstance(value, str) and len(value) == 36 else None
    except ValueError:
        return None


class MonitoringClient:
    """``projects.timeSeries.list`` for one project, page by page."""

    def __init__(self, project: str, *, session=None, timeout_seconds: float = 10, clock=None):
        self.project = project
        self.timeout_seconds = timeout_seconds
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._session = session

    def session(self):
        if self._session is None:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession

            credentials, _ = google.auth.default(scopes=SCOPES)
            self._session = AuthorizedSession(credentials)
        return self._session

    def series(self, metric_filter: str, start: datetime, end: datetime, aligner: str, *, stop_at=None) -> list:
        params = [
            ("filter", metric_filter),
            ("interval.startTime", _stamp(start)),
            ("interval.endTime", _stamp(end)),
            ("aggregation.alignmentPeriod", "3600s"),
            ("aggregation.perSeriesAligner", aligner),
            ("pageSize", str(PAGE_SIZE)),
        ]
        url = f"{MONITORING_API}projects/{self.project}/timeSeries"
        found, token = [], None
        for _ in range(MAX_PAGES):
            if stop_at is not None and self.clock() >= stop_at:
                raise OutOfTime()
            try:
                response = self.session().get(
                    url, params=params + ([("pageToken", token)] if token else []), timeout=self.timeout_seconds)
            except Exception as exc:  # The read is best effort; nothing is written without it.
                raise MonitoringFailed(type(exc).__name__) from None
            if response.status_code in (401, 403):
                raise MonitoringUnavailable("cost_allocation_monitoring_unavailable")
            if response.status_code == 404:
                return []
            if not 200 <= response.status_code < 300:
                raise MonitoringFailed(f"http_{response.status_code}")
            try:
                body = json.loads(response.text, parse_float=Decimal)
            except (ValueError, TypeError):
                raise MonitoringFailed("cost_allocation_monitoring_invalid") from None
            if not isinstance(body, dict) or not isinstance(body.get("timeSeries", []), list):
                raise MonitoringFailed("cost_allocation_monitoring_invalid")
            found += body.get("timeSeries", [])
            token = body.get("nextPageToken")
            if not token:
                return found
        raise MonitoringFailed("cost_allocation_monitoring_too_many_pages")


def read_usage(client: MonitoringClient, start: datetime, end: datetime, *, bucket: str | None,
               stop_at=None) -> Usage:
    """Every reading the allocation needs over [start, end), both on UTC hours."""
    if start.minute or start.second or start.microsecond or end.minute or end.second or end.microsecond:
        raise ValueError("Monitoring windows start and end on the hour")
    billable = f'metric.type="{BILLABLE_METRIC}"'
    services = hourly(client.series(
        billable + ' AND resource.type="cloud_run_revision" AND resource.labels.service_name=one_of('
        f'"{SAM_SERVICE}","{API_SERVICE}")', start, end, "ALIGN_SUM", stop_at=stop_at),
        key=lambda item: _labels(item, "resource").get("service_name"))
    jobs = hourly(client.series(billable + ' AND resource.type="cloud_run_job"', start, end, "ALIGN_SUM",
                                stop_at=stop_at), key=lambda item: _labels(item, "resource").get("job_name"))
    requests = hourly(client.series(
        f'metric.type="{REQUEST_METRIC}" AND resource.type="cloud_run_revision" AND '
        f'resource.labels.service_name="{API_SERVICE}"', start, end, "ALIGN_SUM", stop_at=stop_at)).get(None, {})
    organizations = hourly(client.series(
        f'metric.type="logging.googleapis.com/user/{ORGANIZATION_METRIC_NAME}"', start, end, "ALIGN_SUM",
        stop_at=stop_at), key=_organization)
    storage, location, metric = {}, None, None
    if bucket:
        # Bytes are measured once a day: a day earlier gives the first hours a value to carry.
        for metric in (STORAGE_V2, STORAGE_V1):
            found = client.series(f'metric.type="{metric}" AND resource.type="gcs_bucket" AND '
                                  f'resource.labels.bucket_name="{bucket}"', start - timedelta(days=1), end,
                                  "ALIGN_MEAN", stop_at=stop_at)
            if found:
                locations = {_labels(item, "resource").get("location") for item in found}
                location = locations.pop() if len(locations) == 1 else None
                if location is None:
                    raise MonitoringFailed("cost_allocation_storage_location_unknown")
                storage = hourly(found).get(None, {})
                break
        else:
            metric = None
    return Usage(start=start, end=end, services=services, jobs=jobs, requests=requests,
                 organizations=organizations, storage=storage, storage_location=location, storage_metric=metric)
