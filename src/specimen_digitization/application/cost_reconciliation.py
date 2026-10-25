"""Monthly check of the cost meter against the real bills (docs/execution/golive/COST_RECONCILIATION.md).

Pure: no I/O and no network. ``reconcile`` compares one month of CostEntry rows
(as Data Connect returns them) with a Hugging Face usage bill and a Google
Cloud bill that the operator supplies as data, and returns a JSON-serializable
report; ``render_markdown`` turns that report into plain language.

Units. Meter rows carry micro-USD. Bills are read at their own precision and
kept as integer nano-USD while they are summed, then rounded to micro-USD once
per figure, so a table's rows add up to its total exactly. A gap is always
``metered - billed``: positive when the meter is above the bill.
"""

from __future__ import annotations

import calendar
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

from .cost_ledger import month_of

MICRO = 1_000_000
NANO_PER_MICRO = 1_000
NANO = 1_000_000_000
HELD = "reserved"
REFUSED = "refused"
TRUED_UP = "trued_up"  # cost_ledger.TRUED_UP: re-valued after the call, from its usage or its provider's bill

DEFAULT_BILLING_ZONE = "America/Los_Angeles"
CANDIDATE_ZONES = ("UTC", "America/Los_Angeles", "UTC-5")
# The credit types that stand for Google's free allowance. Which type the Cloud
# Run free tier carries in the export is not confirmed (the pricing page says it
# is "applied as a spending based discount"), so the operator can widen the set.
FREE_CREDIT_TYPES = frozenset({"FREE_TIER"})
# Two zones fit "equally well" when their errors differ by less than this
# (USD 0.01 in nano-USD): the console rounds every figure to cents.
ZONE_TIE_NANO = 10_000_000
# A line fits when it is within half the console's rounding step (USD 0.005).
ZONE_LINE_FIT_NANO = 5_000_000

GOOGLE_FAMILIES = (
    ("specimen-sam", "Cloud Run: SAM 3 service (instance-based billing)"),
    ("specimen-worker", "Cloud Run: Jobs (the specimen-worker job)"),
    ("specimen-api", "Cloud Run: request-based services (the API)"),
    ("storage", "Cloud Storage"),
    ("database", "Cloud SQL"),
)
FAMILY_LABELS = dict(GOOGLE_FAMILIES)
SAM_RESOURCES = ("specimen-sam", "specimen-worker", "specimen-api")
STAGE_FAMILIES = {"label_finding": "specimen-sam", "worker": "specimen-worker", "api": "specimen-api",
                  "storage": "storage", "database": "database"}
NON_STORAGE_SKU = re.compile(r"operations|transfer|egress|network|retrieval", re.I)


class ReconciliationInputError(ValueError):
    """An input file is not in a shape the reconciliation can read; the text says where."""


@dataclass(frozen=True)
class Thresholds:
    """A gap is flagged when it is larger than max(absolute, relative x billed)."""

    absolute_micros: int = 50_000
    relative: float = 0.05

    def limit(self, billed_micros: int) -> int:
        share = (Decimal(max(billed_micros, 0)) * Decimal(str(self.relative))).to_integral_value(ROUND_HALF_EVEN)
        return max(self.absolute_micros, int(share))

    def exceeded(self, gap_micros: int, billed_micros: int) -> bool:
        return abs(gap_micros) > self.limit(billed_micros)


# ---- numbers and times ------------------------------------------------------

def _fail(where: str, what: str):
    raise ReconciliationInputError(f"{where}: {what}")


def _whole(value, where: str) -> int:
    """A whole number as JSON or Data Connect carries it: an int, "12", or 12.0."""
    if isinstance(value, bool):
        _fail(where, "expected a whole number")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value == value and value not in (float("inf"), float("-inf")):
        return int(value) if value.is_integer() else int(round(value))
    if isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
        return int(value.strip())
    _fail(where, "expected a whole number")


def _nano(value, where: str) -> int:
    """A USD amount (float, int or numeric text) as integer nano-USD."""
    if value is None or isinstance(value, bool):
        _fail(where, "expected an amount in USD")
    try:
        amount = Decimal(str(value).strip())
    except InvalidOperation:
        _fail(where, "expected an amount in USD")
    if not amount.is_finite():
        _fail(where, "expected an amount in USD")
    return int((amount * NANO).to_integral_value(ROUND_HALF_EVEN))


def _micros(nano: int) -> int:
    """Nano-USD rounded to the nearest micro-USD, halves away from zero."""
    sign = -1 if nano < 0 else 1
    return sign * ((abs(nano) + NANO_PER_MICRO // 2) // NANO_PER_MICRO)


_EPOCH = re.compile(r"-?\d+(\.\d+)?([eE][+-]?\d+)?")


def _moment(value, where: str) -> datetime:
    """A time as UTC: ISO text, BigQuery text ("2026-10-17 05:00:00 UTC") or epoch seconds or milliseconds."""
    if isinstance(value, bool) or value is None:
        _fail(where, "expected a time")
    if isinstance(value, str) and _EPOCH.fullmatch(value.strip()):
        value = float(value.strip())
    if isinstance(value, (int, float)):
        seconds = float(value) / 1000 if abs(value) > 1e11 else float(value)
        return datetime.fromtimestamp(seconds, timezone.utc)
    if not isinstance(value, str):
        _fail(where, "expected a time")
    text = value.strip()
    if text.upper().endswith(" UTC"):
        text = text[:-4]
    text = text.replace(" ", "T", 1) if re.match(r"\d{4}-\d{2}-\d{2} ", text) else text
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        _fail(where, f"{value!r} is not a time")
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment.astimezone(timezone.utc)


def _day(value, where: str) -> date:
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            pass
        _fail(where, f"{value!r} is not a day (YYYY-MM-DD)")
    return _moment(value, where).date()


# ---- billing-day time zones -------------------------------------------------

def _nth_sunday(year: int, month: int, n: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(6 - first.weekday()) % 7 + 7 * (n - 1))


def _pacific_offset(utc: datetime) -> timedelta:
    """US Pacific time under the rule in force since 2007: daylight time from the
    second Sunday of March (02:00 standard = 10:00Z) to the first Sunday of November
    (02:00 daylight = 09:00Z). Written out so the check needs no tz database."""
    start = datetime.combine(_nth_sunday(utc.year, 3, 2), time(10), timezone.utc)
    end = datetime.combine(_nth_sunday(utc.year, 11, 1), time(9), timezone.utc)
    return timedelta(hours=-7 if start <= utc < end else -8)


class BillingZone:
    """A time zone that cuts days: UTC, a fixed offset such as UTC-5, US Pacific, or a tz-database name."""

    def __init__(self, name: str):
        name = name.strip()
        self.name = name
        self._fixed: timedelta | None = None
        self._pacific = False
        self._info = None
        fixed = re.fullmatch(r"(?:UTC|Z)(?:([+-])(\d{1,2})(?::?(\d{2}))?)?", name, re.I)
        if fixed:
            hours = int(fixed.group(2) or 0)
            minutes = int(fixed.group(3) or 0)
            sign = "-" if fixed.group(1) == "-" else "+"
            self._fixed = (-1 if sign == "-" else 1) * timedelta(hours=hours, minutes=minutes)
            self.name = "UTC" if not (hours or minutes) else f"UTC{sign}{hours}" + (f":{minutes:02d}" if minutes else "")
        elif name in ("America/Los_Angeles", "US/Pacific"):
            self._pacific = True
            self.name = "America/Los_Angeles"
        else:
            try:
                from zoneinfo import ZoneInfo
                self._info = ZoneInfo(name)
            except Exception:  # the tz database is missing or has no such zone
                raise ReconciliationInputError(
                    f"billing zone {name!r} is not UTC, UTC+H, UTC-H, America/Los_Angeles or a known zone name") from None

    def offset(self, utc: datetime) -> timedelta:
        if self._fixed is not None:
            return self._fixed
        if self._pacific:
            return _pacific_offset(utc)
        return utc.astimezone(self._info).utcoffset()

    def local_day(self, utc: datetime) -> date:
        return (utc + self.offset(utc)).date()

    def day_bounds(self, day: date) -> tuple[datetime, datetime]:
        """The UTC instants where this zone's ``day`` starts and ends."""
        def midnight(d: date) -> datetime:
            naive = datetime.combine(d, time(0), timezone.utc)
            for guess in (self.offset(naive), self.offset(naive - timedelta(hours=12)),
                          self.offset(naive + timedelta(hours=12))):
                utc = naive - guess
                if self.offset(utc) == guess:
                    return utc
            return naive - self.offset(naive)
        return midnight(day), midnight(day + timedelta(days=1))


# ---- the meter's rows -------------------------------------------------------

@dataclass(frozen=True)
class MeterRow:
    source: str
    kind: str
    stage: str
    provider: str
    resource: str
    cost: int            # micro-USD the meter counts (negative for a free-allowance credit)
    list_cost: int       # micro-USD before the free allowance
    basis: str
    occurred: datetime | None
    month: str
    method: str | None
    price_list: str | None
    # The provider requests the row stands for: usage.model_calls when it recorded
    # them (a field research call is dozens), else one.
    requests: int = 1

    @property
    def is_allocation(self) -> bool:
        # A paid call the ledger trued up carries a method too; it is still a paid call.
        return self.source == "allocation" or self.kind == "allocation" or (
            self.method is not None and self.source != "paid_call")

    @property
    def is_estimated(self) -> bool:
        return self.basis == TRUED_UP

    @property
    def is_credit(self) -> bool:
        return "free-allowance" in (self.method or "")


def _first(row: dict, *names):
    for name in names:
        if name in row and row[name] is not None:
            return row[name]
    return None


def unwrap_rows(doc, where: str, keys: tuple[str, ...]) -> list:
    """The rows of a list, of ``{"data": {"costEntries": [...]}}`` or of ``{"costEntries": [...]}``."""
    if isinstance(doc, list):
        return doc
    if isinstance(doc, dict):
        if isinstance(doc.get("data"), dict):
            return unwrap_rows(doc["data"], where, keys)
        for key in keys:
            if isinstance(doc.get(key), list):
                return doc[key]
    _fail(where, f"expected a list of rows or an object holding one under {' or '.join(keys)}")


def parse_meter_rows(rows, month: str) -> tuple[list[MeterRow], dict]:
    """The month's CostEntry rows, camelCase (Data Connect) or snake_case, deduplicated by key.

    Rows of another month are dropped and counted; a row that cannot be read is an error.
    """
    month_of(month)
    supplied = unwrap_rows(rows, "meter rows", ("costEntries", "rows", "items"))
    kept: list[MeterRow] = []
    seen: set[tuple] = set()
    other_month = duplicates = 0
    for index, raw in enumerate(supplied):
        where = f"meter row {index}"
        if not isinstance(raw, dict):
            _fail(where, "expected an object")
        key = tuple(_first(raw, *names) for names in (("organizationId", "organization_id"),
                                                      ("collectionId", "collection_id"), ("id",)))
        if all(part is not None for part in key):
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
        cost = _whole(_first(raw, "costMicros", "cost_micros"), where + " costMicros")
        listed = _first(raw, "listCostMicros", "list_cost_micros")
        occurred = _first(raw, "occurredAt", "occurred_at")
        moment = None if occurred is None else _moment(occurred, where + " occurredAt")
        row_month = _first(raw, "month") or (moment.strftime("%Y-%m") if moment else None)
        if not isinstance(row_month, str):
            _fail(where, "needs month or occurredAt")
        if row_month != month:
            other_month += 1
            continue
        method = _first(raw, "allocationMethodId", "allocation_method_id")
        provider, resource = _first(raw, "provider"), _first(raw, "resource")
        if not isinstance(provider, str) or not isinstance(resource, str):
            _fail(where, "needs provider and resource")
        source = _first(raw, "source") or ("allocation" if method else "paid_call")
        version = _first(raw, "priceListVersion", "price_list_version")
        as_of = _first(raw, "priceListAsOf", "price_list_as_of")
        usage = _first(raw, "usage")
        calls = usage.get("model_calls") if isinstance(usage, dict) else None
        if type(calls) is float and calls.is_integer():
            calls = int(calls)
        kept.append(MeterRow(
            source=str(source), kind=str(_first(raw, "kind") or ""), stage=str(_first(raw, "stage") or ""),
            provider=provider, resource=resource, cost=cost,
            list_cost=cost if listed is None else _whole(listed, where + " listCostMicros"),
            basis=str(_first(raw, "costBasis", "cost_basis") or ""), occurred=moment, month=row_month,
            method=None if method is None else str(method),
            price_list=None if version is None else f"{version} as of {as_of}" if as_of else str(version),
            requests=calls if type(calls) is int and calls > 0 else 1))
    return kept, {"rows_supplied": len(supplied), "rows_other_month": other_month, "duplicates_dropped": duplicates}


def default_route_models() -> dict[str, str]:
    """Route id -> Hugging Face model id, from the application's route registry.

    A route name the meter's legacy rows carry (cost_ledger.LEGACY_ROUTES: a held
    parse call named its step before 2026-10-25) maps to the model of the route
    it stood for, so rows the sweep has not rewritten yet still match their bill.
    """
    from ..model_gateway import HUGGINGFACE_ROUTES
    from .cost_ledger import LEGACY_ROUTES

    models = {route_id: route.model_id for route_id, route in HUGGINGFACE_ROUTES.items()}
    for (_, legacy), route_id in LEGACY_ROUTES.items():
        models.setdefault(legacy, models[route_id])
    return models


# ---- the Hugging Face bill --------------------------------------------------

def _model_key(name: str) -> str:
    """A model name compared case-blind and without a ":provider" suffix."""
    return name.strip().rsplit(":", 1)[0].lower()


_HF_DAY_KEYS = ("date", "day", "timestamp", "time", "startTime", "start", "from", "bucket", "t", "x")
_HF_BAR_KEYS = ("bars", "models", "perModel", "byModel", "usage", "data", "items", "series", "breakdown", "values")
_HF_MODEL_KEYS = ("model", "modelId", "model_id", "modelName", "name", "id", "key", "label", "repo")
_HF_REQUEST_KEYS = ("numRequests", "num_requests", "requests")
_HF_NANO_KEYS = ("usedNanoUsd", "used_nano_usd", "nanoUsd", "nano_usd")
_HF_LIST_KEYS = ("histogram", "buckets", "data", "entries", "items", "days", "bins")


@dataclass
class HfBill:
    """Per UTC day and model: [requests, nano-USD]."""

    days: dict[date, dict[str, list[int]]] = field(default_factory=dict)
    names: dict[str, str] = field(default_factory=dict)

    def add(self, day: date, name: str, requests: int, nano: int) -> None:
        key = _model_key(name)
        self.names.setdefault(key, name.strip().rsplit(":", 1)[0])
        cell = self.days.setdefault(day, {}).setdefault(key, [0, 0])
        cell[0] += requests
        cell[1] += nano


def _has_nano(entry) -> bool:
    return isinstance(entry, dict) and any(key in entry for key in _HF_NANO_KEYS)


def _text_of(entry: dict, keys):
    return next((entry[key] for key in keys if isinstance(entry.get(key), str) and entry[key].strip()), None)


def _bars_from(container) -> list[tuple[str, int, int]]:
    if isinstance(container, list):
        items = [(None, item) for item in container]
    elif isinstance(container, dict):
        items = list(container.items())
    else:
        return []
    bars = []
    for name, item in items:
        if not _has_nano(item):
            continue
        model = _text_of(item, _HF_MODEL_KEYS) or (name if isinstance(name, str) else None)
        if model is None:
            continue
        requests = _first(item, *_HF_REQUEST_KEYS)
        bars.append((model, 0 if requests is None else _whole(requests, f"huggingface bar {model} requests"),
                     _whole(_first(item, *_HF_NANO_KEYS), f"huggingface bar {model} nano-USD")))
    return bars


def _bars_in(entry) -> list[tuple[str, int, int]]:
    if isinstance(entry, list):
        return _bars_from(entry)
    if not isinstance(entry, dict):
        return []
    for key in _HF_BAR_KEYS:
        bars = _bars_from(entry.get(key))
        if bars:
            return bars
    for value in entry.values():
        bars = _bars_from(value)
        if bars:
            return bars
    bars = _bars_from(entry)  # a day entry that is itself {model: {numRequests, usedNanoUsd}}
    if bars:
        return bars
    if _has_nano(entry) and _text_of(entry, _HF_MODEL_KEYS):  # a flat row: day, model, usage
        return _bars_from([entry])
    return []


def _find_metrics(doc, depth: int = 0):
    """The ``inferenceUsageMetrics`` object inside a page's data-props, however deep."""
    if depth > 8:
        return None
    if isinstance(doc, str):
        try:
            doc = json.loads(doc)
        except ValueError:
            return None
    if isinstance(doc, dict):
        if "inferenceUsageMetrics" in doc:
            return _find_metrics(doc["inferenceUsageMetrics"], depth + 1) or doc["inferenceUsageMetrics"]
        if "histogram" in doc:
            return doc
        values = doc.values()
    elif isinstance(doc, list):
        values = doc
    else:
        return None
    for value in values:
        found = _find_metrics(value, depth + 1)
        if found is not None:
            return found
    return None


def _histogram_entries(histogram) -> list[tuple[object, object]]:
    if isinstance(histogram, list):
        return [(None, entry) for entry in histogram]
    if isinstance(histogram, dict):
        dated = [(key, value) for key, value in histogram.items() if _try_day(key) is not None]
        if histogram and len(dated) == len(histogram):
            return dated
        for key in _HF_LIST_KEYS:
            if isinstance(histogram.get(key), (list, dict)):
                return _histogram_entries(histogram[key])
    raise ReconciliationInputError(
        "huggingface histogram: unrecognized layout (expected a list of days or an object keyed by day); "
        f"saw {type(histogram).__name__} with keys {sorted(histogram)[:8] if isinstance(histogram, dict) else '-'}")


def _try_day(value) -> date | None:
    try:
        return _day(value, "day")
    except ReconciliationInputError:
        return None


def parse_huggingface(doc) -> HfBill:
    """The Hugging Face bill, from either supported shape (both days are UTC).

    Normalized: ``{"days": {"YYYY-MM-DD": {"<model id>": {"requests": n, "nano_usd": n}}}}``.
    Raw: the ``inferenceUsageMetrics`` object of the usage page's ``[data-props]``
    JSON (or any object holding it): a ``histogram`` of UTC days with one bar per
    model carrying ``numRequests`` and ``usedNanoUsd``. The raw reader looks for
    those two names and a model name under a few likely keys; a layout it cannot
    place is an error that names what it saw (the raw field names beyond the two
    are not confirmed).
    """
    if isinstance(doc, str):
        try:
            doc = json.loads(doc)
        except ValueError:
            _fail("huggingface bill", "not JSON")
    bill = HfBill()
    if isinstance(doc, dict) and isinstance(doc.get("days"), dict):
        for day_text, models in doc["days"].items():
            day = _day(day_text, "huggingface bill day")
            if not isinstance(models, dict):
                _fail(f"huggingface bill {day_text}", "expected an object of models")
            for model, usage in models.items():
                if not isinstance(usage, dict):
                    _fail(f"huggingface bill {day_text} {model}", "expected {requests, nano_usd}")
                bill.add(day, model, _whole(usage.get("requests", 0), f"huggingface {day_text} {model} requests"),
                         _whole(usage.get("nano_usd"), f"huggingface {day_text} {model} nano_usd"))
        return bill
    metrics = _find_metrics(doc)
    if metrics is None or "histogram" not in metrics:
        _fail("huggingface bill", 'expected {"days": ...} or the usage page\'s inferenceUsageMetrics (with a histogram)')
    entries = _histogram_entries(metrics["histogram"])
    parsed_bars = 0
    for hint, entry in entries:
        day = None
        if isinstance(entry, dict):
            day = next((d for d in (_try_day(entry.get(key)) for key in _HF_DAY_KEYS if key in entry)
                        if d is not None), None)
        day = day or (_try_day(hint) if hint is not None else None)
        bars = _bars_in(entry)
        if day is None:
            if not bars:
                continue
            _fail("huggingface histogram", "an entry has usage but no day I can read "
                  f"(keys: {sorted(entry)[:8] if isinstance(entry, dict) else '-'})")
        for model, requests, nano in bars:
            bill.add(day, model, requests, nano)
            parsed_bars += 1
    payloads = [e for _, e in entries if isinstance(e, dict) and any(isinstance(v, (list, dict)) and v for v in e.values())]
    if entries and not parsed_bars and payloads:
        first = payloads[0]
        _fail("huggingface histogram", f"no model bars with {'/'.join(_HF_NANO_KEYS[:1])} found "
              f"(first entry keys: {sorted(first)[:8]})")
    return bill


# ---- the Google bill --------------------------------------------------------

@dataclass(frozen=True)
class GoogleLine:
    service: str
    sku: str
    cost: int                    # nano-USD, before credits
    free: int                    # nano-USD, free-allowance credits (zero or negative)
    other_types: tuple[tuple[str, int], ...] = ()  # nano-USD per credit type, every credit that is not the free allowance
    day: date | None = None      # a console line's day, as the console shows it
    start: datetime | None = None  # an export row's usage window
    end: datetime | None = None
    project: str | None = None
    invoice_month: str | None = None
    cost_type: str | None = None

    @property
    def other(self) -> int:
        """Nano-USD of every credit that is not the free allowance (zero or negative)."""
        return sum(amount for _, amount in self.other_types)


@dataclass
class GoogleBill:
    export: list[GoogleLine] = field(default_factory=list)   # rows of the standard export
    console: list[GoogleLine] = field(default_factory=list)  # lines read from the console report


def _get(row: dict, dotted: str):
    """``service.description`` from nested, dotted or underscored export columns."""
    if dotted in row:
        return row[dotted]
    if dotted.replace(".", "_") in row:
        return row[dotted.replace(".", "_")]
    node = row
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _credits(raw, free_types, where: str) -> tuple[int, tuple[tuple[str, int], ...]]:
    """(the free-allowance credits, every other credit summed per type), in nano-USD."""
    if raw is None:
        return 0, ()
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            _fail(where, "credits is not JSON")
    if not isinstance(raw, list):
        _fail(where, "credits must be a list")
    free = 0
    other: dict[str, int] = {}
    for credit in raw:
        if not isinstance(credit, dict):
            _fail(where, "a credit must be an object")
        amount = _nano(credit.get("amount") or 0, where + " credit amount")
        kind = str(credit.get("type") or "").upper()
        name = str(credit.get("name") or credit.get("full_name") or "").strip()
        if kind in free_types or (not kind and "free" in name.lower()):
            free += amount
        else:
            label = kind or name or "UNTYPED"
            other[label] = other.get(label, 0) + amount
    return free, tuple(sorted(other.items()))


def _export_row(raw: dict, index: int, free_types) -> GoogleLine:
    where = f"google export row {index}"
    service, sku = _get(raw, "service.description"), _get(raw, "sku.description")
    if not isinstance(service, str) or not isinstance(sku, str):
        _fail(where, "needs service.description and sku.description")
    start, end = _get(raw, "usage_start_time"), _get(raw, "usage_end_time")
    if start is None:
        _fail(where, "needs usage_start_time")
    free, other_types = _credits(raw.get("credits"), free_types, where)
    invoice, project = _get(raw, "invoice.month"), _get(raw, "project.id")
    cost_type = raw.get("cost_type")
    return GoogleLine(
        service=service, sku=sku, cost=_nano(raw.get("cost") or 0, where + " cost"), free=free, other_types=other_types,
        start=_moment(start, where + " usage_start_time"),
        end=None if end is None else _moment(end, where + " usage_end_time"),
        project=project if isinstance(project, str) else None,
        invoice_month=None if invoice is None else str(invoice),
        cost_type=None if cost_type is None else str(cost_type).lower())


def _console_line(raw: dict, index: int) -> GoogleLine:
    where = f"google line {index}"
    if not isinstance(raw, dict):
        _fail(where, "expected an object")
    service, sku = raw.get("service"), raw.get("sku")
    if not isinstance(service, str) or not isinstance(sku, str):
        _fail(where, "needs service and sku")
    credits = _nano(raw.get("credits_usd", 0), where + " credits_usd")
    if credits > 0:
        _fail(where, "credits_usd must be zero or negative, as the console shows it")
    return GoogleLine(service=service, sku=sku, cost=_nano(raw.get("cost_usd"), where + " cost_usd"),
                      free=credits, day=_day(raw.get("day"), where + " day"),
                      project=raw.get("project") if isinstance(raw.get("project"), str) else None)


def parse_google(*docs, free_credit_types=FREE_CREDIT_TYPES) -> GoogleBill:
    """The Google bill from one or more documents, in either supported shape.

    A list is rows of the Cloud Billing standard export to BigQuery (nested like
    ``bq query --format=json``, or with dotted columns such as ``service.description``).
    An object with ``lines`` holds figures read from the console report:
    ``{"service", "sku", "day", "cost_usd", "credits_usd"}``; an object may also hold
    export rows under ``rows``. Credits of a type in ``free_credit_types`` are the free
    allowance; any other credit is kept apart.
    """
    free_types = {str(kind).upper() for kind in free_credit_types}
    bill = GoogleBill()
    for doc in docs:
        if isinstance(doc, str):
            try:
                doc = json.loads(doc)
            except ValueError:
                _fail("google bill", "not JSON")
        if isinstance(doc, dict) and "data" in doc and not ({"rows", "lines"} & set(doc)):
            doc = doc["data"]
        rows: list = []
        lines: list = []
        if isinstance(doc, list):
            rows = doc
        elif isinstance(doc, dict) and ("rows" in doc or "lines" in doc):
            rows, lines = doc.get("rows") or [], doc.get("lines") or []
        else:
            _fail("google bill", 'expected a list of export rows or an object with "lines" (and/or "rows")')
        if not isinstance(rows, list) or not isinstance(lines, list):
            _fail("google bill", "rows and lines must be lists")
        for index, raw in enumerate(rows):
            if not isinstance(raw, dict):
                _fail(f"google export row {index}", "expected an object")
            bill.export.append(_export_row(raw, index, free_types))
        for index, raw in enumerate(lines):
            bill.console.append(_console_line(raw, index))
    return bill


def google_family(service: str, sku: str) -> str | None:
    """The meter family of a Google line, or None for a service the meter does not cover.

    The standard export does not name the Cloud Run service: instance-based SKUs are
    taken to be specimen-sam, the only instance-based service the app deploys.
    """
    svc, name = service.strip().lower(), sku.strip().lower()
    if svc == "cloud run":
        if name.startswith("jobs "):
            return "specimen-worker"
        if "(instance-based billing)" in name:
            return "specimen-sam"
        if "(request-based billing" in name or name.startswith("requests"):
            return "specimen-api"
        return None
    if svc == "cloud storage":
        return "storage"
    if svc == "cloud sql":
        return "database"
    return None


# What a Google line outside every family is (COST_RECONCILIATION.md, "Lines the
# meter does not split"): a fixed cost of running the platform, which no tenant's
# use drives and the meter states apart; or a cost tenants' use drives that the
# meter does not split yet. Read from the October 2026 bill and Cloud Monitoring.
FIXED_PLATFORM = "fixed_platform"
SHARED_NOT_SPLIT = "shared_not_yet_split"
NOT_METERED = "not_metered"


def line_treatment(service: str, sku: str) -> tuple[str, str]:
    """(treatment, why) for a Google line no meter family holds."""
    svc, name = service.strip().lower(), sku.strip().lower()
    if svc == "cloud run" and ("data transfer out" in name or "egress" in name):
        return SHARED_NOT_SPLIT, ("data the services send over the internet, nearly all of it the API's answers to "
                                  "people's browsers: driven by use, to be split with the API by organization")
    if "connect" in svc and "operation" in name:
        return SHARED_NOT_SPLIT, ("database operations, most of them the API's reads for each request: driven by use, "
                                  "to be split with the API")
    if svc == "artifact registry":
        return FIXED_PLATFORM, "the stored container images of the releases"
    if svc == "cloud build":
        return FIXED_PLATFORM, "the release builds"
    if svc == "secret manager":
        return FIXED_PLATFORM, "the stored secrets"
    return NOT_METERED, "not metered"


def meter_family(row: MeterRow) -> str | None:
    """The Google family a meter row belongs to (a paid SAM 3 call, or an allocation row)."""
    if row.provider != "google_cloud":
        return None
    if row.resource in SAM_RESOURCES:
        return row.resource
    if row.kind == "service" and row.source != "allocation" and row.resource == "sam3":
        return "specimen-sam"
    if row.resource == "cloud-sql" or row.stage == "database":
        return "database"
    return STAGE_FAMILIES.get(row.stage)


# ---- helpers shared by the sections ----------------------------------------

def usd(micros: int) -> str:
    sign = "-" if micros < 0 else ""
    value = abs(micros)
    if value < 100 * MICRO:
        if 0 < value < 50:
            return f"{sign}<$0.0001"
        return f"{sign}${value / MICRO:,.4f}"
    return f"{sign}${value / MICRO:,.2f}"


def _percent(gap: int, billed: int) -> float | None:
    return round(gap * 100 / billed, 2) if billed > 0 else None


def _direction(gap: int) -> str:
    return "above" if gap > 0 else "below"


def _explain(code: str, text: str) -> dict:
    return {"code": code, "text": text}


def _add_credit_types(total: dict, line: GoogleLine) -> None:
    """Add a line's other credits, per type, into ``total`` (nano-USD)."""
    for kind, amount in line.other_types:
        total[kind] = total.get(kind, 0) + amount


def _rounded_types(nano_by_type: dict) -> dict:
    """Per-type nano-USD as micro-USD, rounded once per type, in type order."""
    return {kind: _micros(amount) for kind, amount in sorted(nano_by_type.items()) if _micros(amount) != 0}


def _sum_types(groups) -> dict:
    total: dict = {}
    for group in groups:
        for kind, amount in group.items():
            total[kind] = total.get(kind, 0) + amount
    return dict(sorted(total.items()))


def types_text(by_type: dict) -> str:
    """``PROMOTION -$0.3300, SPENDING_BASED_DISCOUNT -$0.0100``."""
    return ", ".join(f"{kind} {usd(amount)}" for kind, amount in by_type.items())


# ---- Hugging Face -----------------------------------------------------------

def _hf_section(rows: list[MeterRow], bill: HfBill | None, month: str, route_models: dict[str, str],
                limits: Thresholds) -> dict:
    key_of_route = {route: _model_key(model) for route, model in route_models.items()}
    model_name = {_model_key(model): model for model in route_models.values()}
    meter: dict[str, list[MeterRow]] = {}
    unmapped: dict[str, list[MeterRow]] = {}
    for row in rows:
        if row.provider != "huggingface":
            continue
        key = key_of_route.get(row.resource)
        (meter.setdefault(key, []) if key else unmapped.setdefault(row.resource, [])).append(row)
    month_days = {day: models for day, models in (bill.days.items() if bill else ()) if day.strftime("%Y-%m") == month}
    billed_keys = {key for models in month_days.values() for key in models}
    keys = sorted(billed_keys | set(meter))
    entries = []
    names = bill.names if bill else {}
    for key in keys:
        entries.append(_hf_entry(key, model_name.get(key) or names.get(key) or key, meter.get(key, []),
                                 month_days, key in model_name, month, limits, supplied=bill is not None))
    for route, calls in sorted(unmapped.items()):
        entries.append(_hf_entry(None, route, calls, {}, False, month, limits, supplied=bill is not None,
                                 unmapped_route=route))
    entries.sort(key=lambda e: (-abs(e["gap_micros"]), e["label"]))
    totals = {"billed_micros": sum(e["billed_micros"] for e in entries),
              "billed_requests": sum(e["billed_requests"] for e in entries),
              "metered_micros": sum(e["metered_micros"] for e in entries),
              "metered_settled_micros": sum(e["metered_settled_micros"] for e in entries),
              "metered_held_micros": sum(e["metered_held_micros"] for e in entries),
              "metered_estimated_micros": sum(e["metered_estimated_micros"] for e in entries),
              "meter_calls": sum(e["meter_calls"] for e in entries),
              "meter_requests": sum(e["meter_requests"] for e in entries)}
    totals["gap_micros"] = totals["metered_micros"] - totals["billed_micros"]
    totals["gap_percent"] = _percent(totals["gap_micros"], totals["billed_micros"])
    section = {"supplied": bill is not None, "models": entries, "totals": totals,
               "days_in_bill": sorted(d.isoformat() for d in month_days),
               "bill_days_outside_month": 0 if bill is None else len(bill.days) - len(month_days)}
    return section


def _hf_entry(key, label, calls: list[MeterRow], month_days: dict, in_registry: bool, month: str,
              limits: Thresholds, supplied: bool, unmapped_route: str | None = None) -> dict:
    billed_requests = sum(models[key][0] for models in month_days.values() if key in models) if key else 0
    billed_nano = sum(models[key][1] for models in month_days.values() if key in models) if key else 0
    billed = _micros(billed_nano)
    settled = sum(r.cost for r in calls if r.basis != HELD)
    held = sum(r.cost for r in calls if r.basis == HELD)
    estimated = sum(r.cost for r in calls if r.is_estimated)
    held_calls = sum(1 for r in calls if r.basis == HELD)
    refused_calls = sum(1 for r in calls if r.basis == REFUSED)
    settled_calls = len(calls) - held_calls - refused_calls
    # Requests, not rows: one field research call is dozens of requests (usage.model_calls).
    meter_requests = sum(r.requests for r in calls)
    settled_requests = sum(r.requests for r in calls if r.basis not in (HELD, REFUSED))
    metered = settled + held
    gap = metered - billed
    routes: dict[str, dict] = {}
    for r in calls:
        cell = routes.setdefault(r.resource, {"route_id": r.resource, "calls": 0, "settled_micros": 0, "held_micros": 0})
        cell["calls"] += 1
        cell["held_micros" if r.basis == HELD else "settled_micros"] += r.cost
    by_day: dict[date, dict] = {}
    for day, models in month_days.items():
        if key in models:
            cell = by_day.setdefault(day, {"billed": 0, "requests": 0, "metered": 0, "calls": 0})
            cell["billed"] += models[key][1]
            cell["requests"] += models[key][0]
    for r in calls:
        if r.occurred is not None:
            cell = by_day.setdefault(r.occurred.date(), {"billed": 0, "requests": 0, "metered": 0, "calls": 0})
            cell["metered"] += r.cost
            cell["calls"] += 1
            cell["meter_requests"] = cell.get("meter_requests", 0) + r.requests
    days = [{"day": day.isoformat(), "billed_micros": _micros(c["billed"]), "billed_requests": c["requests"],
             "metered_micros": c["metered"], "meter_calls": c["calls"], "meter_requests": c.get("meter_requests", 0),
             "gap_micros": c["metered"] - _micros(c["billed"])} for day, c in sorted(by_day.items())]
    flagged = supplied and limits.exceeded(gap, billed)
    entry = {
        "model_id": label if key else None,
        "label": label,
        "routes": sorted(routes.values(), key=lambda c: c["route_id"]),
        "in_registry": in_registry,
        "billed_micros": billed, "billed_requests": billed_requests,
        "metered_micros": metered, "metered_settled_micros": settled, "metered_held_micros": held,
        "metered_estimated_micros": estimated, "meter_estimated_calls": sum(1 for r in calls if r.is_estimated),
        "meter_calls": len(calls), "meter_settled_calls": settled_calls,
        "meter_held_calls": held_calls, "meter_refused_calls": refused_calls,
        "meter_requests": meter_requests, "meter_settled_requests": settled_requests,
        "meter_held_requests": sum(r.requests for r in calls if r.basis == HELD),
        "gap_micros": gap, "gap_percent": _percent(gap, billed), "gap_settled_micros": settled - billed,
        "threshold_micros": limits.limit(billed), "flagged": flagged,
        "billed_over_settled": round(billed / settled, 4) if settled > 0 and billed > 0 else None,
        "days": days,
        "price_lists": sorted({r.price_list for r in calls if r.price_list}),
    }
    entry["explanations"] = _hf_explanations(entry, days, month, unmapped_route) if flagged else []
    return entry


def _hf_explanations(e: dict, days: list[dict], month: str, unmapped_route: str | None) -> list[dict]:
    out = []
    gap, billed, limit = e["gap_micros"], e["billed_micros"], e["threshold_micros"]
    if unmapped_route:
        out.append(_explain("route_not_in_registry", f"The meter has {e['meter_calls']} calls ({usd(e['metered_micros'])}) "
                            f"on route {unmapped_route}, which the route registry does not name, so no bill model can be "
                            "matched to it. The route may have been retired."))
    elif billed > 0 and e["meter_calls"] == 0:
        where = "the registry names this model" if e["in_registry"] else "no route in the registry names this model"
        out.append(_explain("no_meter_rows", f"The bill has {e['billed_requests']} requests ({usd(billed)}) and the meter "
                            f"has no call for this model ({where}). Likely causes: calls made outside the app on the same "
                            "account, a retired route, or meter rows not written yet."))
    if e["meter_held_calls"] and e["metered_held_micros"] > 0 and gap > 0:
        if abs(e["gap_settled_micros"]) <= limit:
            out.append(_explain("held_calls", f"Settled calls alone are within the limit (gap {usd(e['gap_settled_micros'])}). "
                                f"The rest is held: {e['meter_held_calls']} calls whose spend was unknown (a timeout, a server "
                                "error or no usage reported) are counted at their full reservation "
                                f"({usd(e['metered_held_micros'])}); the bill charges only what the provider billed."))
        else:
            out.append(_explain("held_calls", f"{usd(e['metered_held_micros'])} of the meter's figure is held: "
                                f"{e['meter_held_calls']} calls with unknown spend counted at their full reservation."))
    if e["metered_estimated_micros"]:
        out.append(_explain("trued_up", f"{usd(e['metered_estimated_micros'])} of the meter's figure "
                            f"({e['meter_estimated_calls']} calls) was estimated after the call: a call whose cost the "
                            "run could not know, or one priced at list without its cached input, counted at the "
                            "provider's billed mean per request for that model and day (cost basis trued_up)."))
    # Requests, not rows: a field research row records the requests it made (usage.model_calls).
    requests, settled_requests = e["billed_requests"], e["meter_settled_requests"]
    if billed > 0 and e["meter_calls"] > 0:
        if requests > e["meter_requests"]:
            out.append(_explain("requests_outside_meter", f"Hugging Face counted {requests - e['meter_requests']} more "
                                f"requests ({requests}) than the meter's calls made ({e['meter_requests']}, refused ones "
                                "included): calls made outside the app on the same account (lab runs, experiments), or "
                                "meter rows the sweep has not written yet."))
        elif requests < settled_requests:
            out.append(_explain("calls_not_billed", f"The meter's settled calls made {settled_requests} requests but the "
                                f"bill counted {requests}: some settled calls were not billed."))
        elif settled_requests and requests - settled_requests <= e["meter_held_requests"]:
            ratio = e["billed_over_settled"]
            if ratio is not None and ratio < 0.97:
                out.append(_explain("provider_discount", f"The request counts agree ({requests} billed, "
                                    f"{settled_requests} made by settled calls in the meter), but the bill is "
                                    f"{ratio * 100:.1f}% of the meter's settled figure: the provider charged less than the "
                                    "list price the meter uses, for example cached input at a lower rate."))
            elif ratio is not None and ratio > 1.03:
                lists = "; ".join(e["price_lists"]) or "unknown"
                out.append(_explain("billed_above_list", f"The request counts agree but the bill is {ratio * 100:.1f}% of the "
                                    f"meter's settled figure: the price list may be out of date (the rows use: {lists})."))
    if days and gap != 0:
        first, last = f"{month}-01", f"{month}-{calendar.monthrange(*month_of(month))[1]:02d}"
        total_abs = sum(abs(d["gap_micros"]) for d in days)
        edge_abs = sum(abs(d["gap_micros"]) for d in days if d["day"] in (first, last))
        if total_abs > 0 and edge_abs * 2 >= total_abs and edge_abs > limit // 2:
            out.append(_explain("day_boundary", f"{edge_abs * 100 // total_abs}% of the daily gaps sit on the month's first "
                                "or last day (UTC): a call near midnight may have been billed on the neighbouring day, "
                                "outside this month."))
    if not out:
        out.append(_explain("unexplained", "The inputs show no cause. Compare the per-day table and the request counts, "
                            "then read the meter's calls for the day with the largest gap."))
    return out


# ---- Google -----------------------------------------------------------------

@dataclass
class _Meter:
    list_micros: int = 0
    after_micros: int = 0
    held_micros: int = 0
    direct_micros: int = 0
    allocated_micros: int = 0
    rows: int = 0
    allocation_rows: int = 0
    alloc_days: set = field(default_factory=set)


def _google_meter(rows: list[MeterRow], zone: BillingZone):
    per: dict[str, _Meter] = {name: _Meter() for name, _ in GOOGLE_FAMILIES}
    unplaced = _Meter()
    other: dict[tuple, dict] = {}
    any_allocation = False
    unassigned_credit = 0
    for row in rows:
        if row.provider == "huggingface":
            continue
        any_allocation = any_allocation or row.is_allocation
        if row.provider != "google_cloud":
            cell = other.setdefault((row.provider, row.kind, row.resource), {"rows": 0, "cost": 0, "held": 0})
            cell["rows"] += 1
            cell["cost"] += row.cost
            cell["held"] += row.cost if row.basis == HELD else 0
            continue
        family = meter_family(row)
        if family is None and row.is_credit:
            unassigned_credit += row.cost
            continue
        target = per[family] if family else unplaced
        target.rows += 1
        target.list_micros += row.list_cost
        target.after_micros += row.cost
        if row.basis == HELD and not row.is_credit:
            target.held_micros += row.cost
        if row.is_allocation:
            target.allocated_micros += row.cost
            if not row.is_credit:
                target.allocation_rows += 1
                if row.occurred is not None:
                    # The billing day in the zone in use, not the UTC date: an allocation row is stamped at the start of
                    # its billing day, which falls on the same date in UTC, UTC-5 and Pacific only for midnight Pacific.
                    target.alloc_days.add(zone.local_day(row.occurred))
        else:
            target.direct_micros += row.cost
    return per, unplaced, other, any_allocation, unassigned_credit


def _google_lines(bill: GoogleBill, month: str, zone: BillingZone, project_id: str | None):
    """The lines that count for the month: export rows when supplied, else the console's."""
    source = "export" if bill.export else "console"
    lines = bill.export or bill.console
    kept: list[tuple[GoogleLine, date]] = []
    other_projects = {"lines": 0, "cost_micros": 0, "free_micros": 0}
    other_months = 0
    invoice_shift = {"lines": 0, "cost_micros": 0}
    nano_other_cost = nano_other_free = 0
    for line in lines:
        day = line.day if source == "console" else zone.local_day(line.start)
        if day.strftime("%Y-%m") != month:
            other_months += 1
            continue
        if project_id and line.project and line.project != project_id:
            other_projects["lines"] += 1
            nano_other_cost += line.cost
            nano_other_free += line.free
            continue
        if source == "export" and line.invoice_month and re.fullmatch(r"\d{6}", line.invoice_month) \
                and line.invoice_month != day.strftime("%Y%m"):
            invoice_shift["lines"] += 1
            invoice_shift["cost_micros"] += _micros(line.cost)
        kept.append((line, day))
    other_projects["cost_micros"] = _micros(nano_other_cost)
    other_projects["free_micros"] = _micros(nano_other_free)
    return source, kept, other_projects, other_months, invoice_shift


def _google_section(rows: list[MeterRow], bill: GoogleBill | None, month: str, zone: BillingZone,
                    project_id: str | None, limits: Thresholds, day_check: dict | None) -> tuple[dict, dict]:
    per, unplaced, other_meter, any_allocation, unassigned_credit = _google_meter(rows, zone)
    families = {name: {"cost": 0, "free": 0, "other": {}, "days": {}, "skus": {}} for name, _ in GOOGLE_FAMILIES}
    unmetered: dict[tuple, dict] = {}
    source = None
    other_projects = {"lines": 0, "cost_micros": 0, "free_micros": 0}
    other_months = 0
    invoice_shift = {"lines": 0, "cost_micros": 0}
    if bill is not None:
        source, kept, other_projects, other_months, invoice_shift = _google_lines(bill, month, zone, project_id)
        for line, day in kept:
            family = None if line.cost_type in ("tax", "rounding_error") else google_family(line.service, line.sku)
            if family:
                cell = families[family]
                cell["cost"] += line.cost
                cell["free"] += line.free
                _add_credit_types(cell["other"], line)
                cell["days"][day] = cell["days"].get(day, 0) + line.cost
                cell["skus"][line.sku] = cell["skus"].get(line.sku, 0) + line.cost
            else:
                label = (line.service, line.sku if line.cost_type not in ("tax", "rounding_error")
                         else f"({line.cost_type})")
                cell = unmetered.setdefault(label, {"cost": 0, "free": 0, "other": {}})
                cell["cost"] += line.cost
                cell["free"] += line.free
                _add_credit_types(cell["other"], line)
    result_families = []
    for name, label in GOOGLE_FAMILIES:
        m, b = per[name], families[name]
        cost, free = _micros(b["cost"]), _micros(b["free"])
        other_types = _rounded_types(b["other"])
        other = sum(other_types.values())
        billed_after = cost + free
        gap = m.after_micros - billed_after
        flagged = bill is not None and limits.exceeded(gap, billed_after)
        entry = {
            "family": name, "label": label,
            "billed_cost_micros": cost, "billed_credits_micros": free, "billed_other_credits_micros": other,
            "billed_other_credits_by_type": other_types,
            "billed_net_micros": billed_after + other, "billed_after_allowance_micros": billed_after,
            "meter_list_micros": m.list_micros, "meter_after_allowance_micros": m.after_micros,
            "meter_credits_micros": m.after_micros - m.list_micros,
            "meter_direct_micros": m.direct_micros, "meter_allocated_micros": m.allocated_micros,
            "meter_held_micros": m.held_micros, "meter_rows": m.rows,
            "gap_micros": gap, "gap_list_micros": m.list_micros - cost, "gap_percent": _percent(gap, billed_after),
            "threshold_micros": limits.limit(billed_after), "flagged": flagged,
            "billed_days": sorted(d.isoformat() for d, amount in b["days"].items() if amount > 0),
            "allocation_days": sorted(d.isoformat() for d in m.alloc_days),
            "explanations": [],
        }
        if flagged:
            entry["explanations"] = _google_explanations(entry, b, any_allocation, zone, day_check, other_projects)
        result_families.append(entry)
    unmetered_lines = []
    for (service, sku), c in sorted(unmetered.items(), key=lambda item: (-item[1]["cost"], item[0])):
        types = _rounded_types(c["other"])
        cost, free = _micros(c["cost"]), _micros(c["free"])
        treatment, why = line_treatment(service, sku)
        unmetered_lines.append({
            "service": service, "sku": sku, "cost_micros": cost, "credits_micros": free,
            "other_credits_micros": sum(types.values()), "other_credits_by_type": types,
            "after_allowance_micros": cost + free, "net_micros": cost + free + sum(types.values()),
            "treatment": treatment, "treatment_reason": why})
    unmetered_types = _sum_types([l["other_credits_by_type"] for l in unmetered_lines])
    google = {
        "supplied": bill is not None, "source": source, "families": result_families,
        "unmetered": {"lines": unmetered_lines,
                      "by_treatment": {kind: sum(l["after_allowance_micros"] for l in unmetered_lines
                                                 if l["treatment"] == kind)
                                       for kind in (FIXED_PLATFORM, SHARED_NOT_SPLIT, NOT_METERED)},
                      "cost_micros": sum(l["cost_micros"] for l in unmetered_lines),
                      "credits_micros": sum(l["credits_micros"] for l in unmetered_lines),
                      "other_credits_micros": sum(l["other_credits_micros"] for l in unmetered_lines),
                      "other_credits_by_type": unmetered_types,
                      "after_allowance_micros": sum(l["after_allowance_micros"] for l in unmetered_lines),
                      "net_micros": sum(l["net_micros"] for l in unmetered_lines)},
        "other_projects": other_projects, "lines_outside_month": other_months, "invoice_month_shift": invoice_shift,
        "meter_unplaced": {"rows": unplaced.rows, "cost_micros": unplaced.after_micros},
        "meter_unassigned_credits_micros": unassigned_credit,
    }
    fam_billed = sum(f["billed_after_allowance_micros"] for f in result_families)
    fam_meter = sum(f["meter_after_allowance_micros"] for f in result_families)
    other_total = sum(f["billed_other_credits_micros"] for f in result_families) + google["unmetered"]["other_credits_micros"]
    cost_total = sum(f["billed_cost_micros"] for f in result_families) + google["unmetered"]["cost_micros"]
    free_total = sum(f["billed_credits_micros"] for f in result_families) + google["unmetered"]["credits_micros"]
    google["totals"] = {
        "billed_micros": fam_billed + google["unmetered"]["after_allowance_micros"],
        "billed_families_micros": fam_billed,
        "billed_unmetered_micros": google["unmetered"]["after_allowance_micros"],
        "billed_cost_micros": cost_total,
        "billed_credits_micros": free_total,
        "billed_other_credits_micros": other_total,
        "billed_other_credits_by_type": _sum_types([f["billed_other_credits_by_type"] for f in result_families]
                                                   + [unmetered_types]),
        "billed_net_micros": cost_total + free_total + other_total,
        "metered_micros": fam_meter + unplaced.after_micros + unassigned_credit,
        "metered_families_micros": fam_meter,
        "meter_credits_micros": sum(f["meter_credits_micros"] for f in result_families) + unassigned_credit,
        "gap_families_micros": fam_meter - fam_billed,
    }
    other = [{"provider": p, "kind": k, "resource": r, "rows": c["rows"], "cost_micros": c["cost"],
              "held_micros": c["held"]} for (p, k, r), c in sorted(other_meter.items())]
    return google, {"rows": other, "cost_micros": sum(c["cost_micros"] for c in other)}


def _google_explanations(entry: dict, billed: dict, any_allocation: bool, zone: BillingZone,
                         day_check: dict | None, other_projects: dict) -> list[dict]:
    out = []
    name, gap = entry["family"], entry["gap_micros"]
    below = gap < 0
    if not any_allocation and below:
        out.append(_explain("no_allocation_rows", "The meter holds no allocation rows for this month, so shared Google "
                            f"costs are not in it; only direct SAM 3 charges ({usd(entry['meter_direct_micros'])} here) are."
                            if name == "specimen-sam" else
                            "The meter holds no allocation rows for this month, so this shared Google cost is not in it."))
    elif below and entry["billed_days"]:
        missing = sorted(set(entry["billed_days"]) - set(entry["allocation_days"]))
        if missing:
            more = " and more" if len(missing) > 10 else ""
            note = " (the bill's latest day, which may still be in progress)" if missing == [entry["billed_days"][-1]] else ""
            out.append(_explain("missing_allocation_days", f"No allocation row for {len(missing)} billed day(s): "
                                f"{', '.join(missing[:10])}{more}{note}. Days are cut in {zone.name}."))
    if entry["meter_held_micros"] > 0 and gap > 0:
        out.append(_explain("held_calls", f"{usd(entry['meter_held_micros'])} of the meter's figure is held: direct SAM 3 "
                            "calls with unknown spend counted at their full reservation."))
    credit_gap = entry["meter_credits_micros"] - entry["billed_credits_micros"]
    others = entry["billed_other_credits_by_type"]
    hint = ""
    if others:
        hint = (f"The bill's lines for this family carry other credits ({types_text(others)}); if one of these types is "
                f"the free tier, re-run with --free-credit-type <TYPE> ({', '.join(others)}).")
    if credit_gap * gap > 0 and abs(credit_gap) * 2 >= abs(gap):
        text = (f"The meter's free allowance is {usd(-entry['meter_credits_micros'])} and the bill's (credit type "
                f"FREE_TIER by default) is {usd(-entry['billed_credits_micros'])}; the difference "
                f"({usd(abs(credit_gap))}) accounts for at least half of the gap.")
        if hint:
            text += " " + hint
        if credit_gap < 0:
            text += " Otherwise, Google's free tier" if hint else " Google's free tier"
            text += " is shared by every project on the billing account"
            text += (f"; the export shows {usd(-other_projects['free_micros'])} of free-tier credit on other projects."
                     if other_projects["free_micros"] < 0 else "; other projects' usage may have used part of it.")
        elif entry["meter_credits_micros"] == 0:
            text += " The meter holds no free-allowance rows for this family."
        out.append(_explain("free_allowance", text))
    elif hint:
        out.append(_explain("other_credits", f"{hint} They are not subtracted in the comparison; Google's net charge for "
                            f"this family was {usd(entry['billed_net_micros'])}."))
    if name == "specimen-worker" and below:
        out.append(_explain("intake_jobs", "The Jobs SKUs bill every Cloud Run job of the project. The intake jobs share them "
                            "and are not metered."))
    if name == "storage" and below:
        extra = sum(v for sku, v in billed["skus"].items() if NON_STORAGE_SKU.search(sku))
        if extra > 0:
            out.append(_explain("storage_non_bytes", f"{usd(_micros(extra))} of the bill's Cloud Storage lines are operations "
                                "or data transfer, not stored bytes."))
    if day_check and day_check.get("status") == "ok" and day_check.get("best_fit") not in (None, zone.name):
        out.append(_explain("day_boundary", f"The billing-day check fits {day_check['best_fit']} better than {zone.name}, "
                            "the zone the allocation days and this comparison use."))
    if not out:
        out.append(_explain("unexplained", "The inputs show no cause. Compare the billed SKUs with the meter's allocation rows "
                            "for this family, day by day."))
    return out


# ---- the billing-day check --------------------------------------------------

def check_billing_day(bill: GoogleBill | None, assumed: BillingZone, project_id: str | None = None,
                      candidates=CANDIDATE_ZONES) -> dict:
    """Which day boundary the console's daily figures follow.

    Hourly export rows are bucketed into days under each candidate zone and set
    against the console's daily lines (cost before credits, per day and SKU); the
    zone with the smallest total difference fits best. Only days the export fully
    covers under every candidate are compared.
    """
    zones = [BillingZone(name) for name in dict.fromkeys([*candidates, assumed.name])]
    base = {"assumed_zone": assumed.name, "status": "not_run", "best_fit": None, "candidates": []}
    if bill is None or not bill.export:
        return {**base, "reason": "No hourly export rows were supplied."}
    if not bill.console:
        return {**base, "reason": "No daily console lines were supplied; the check needs the console report's daily figures."}
    hourly = [l for l in bill.export if l.end and l.end - l.start <= timedelta(hours=1, seconds=60)
              and not (project_id and l.project and l.project != project_id)]
    if not hourly:
        return {**base, "reason": "The export rows are not hourly windows, so they cannot be cut into days."}
    low, high = min(l.start for l in hourly), max(l.end for l in hourly)
    console_days = sorted({l.day for l in bill.console})
    comparable = [d for d in console_days if all(low <= z.day_bounds(d)[0] and z.day_bounds(d)[1] <= high for z in zones)]
    if not comparable:
        return {**base, "reason": "No console day lies fully inside the hourly export under every candidate zone."}
    wanted = set(comparable)
    reference: dict[tuple, int] = {}
    for line in bill.console:
        if line.day in wanted:
            key = (line.day, line.service, line.sku)
            reference[key] = reference.get(key, 0) + line.cost
    results = []
    for zone in zones:
        bucket: dict[tuple, int] = {}
        for line in hourly:
            day = zone.local_day(line.start)
            if day in wanted:
                key = (day, line.service, line.sku)
                bucket[key] = bucket.get(key, 0) + line.cost
        keys = set(reference) | set(bucket)
        error = sum(abs(bucket.get(k, 0) - reference.get(k, 0)) for k in keys)
        fits = sum(1 for k in keys if abs(bucket.get(k, 0) - reference.get(k, 0)) <= ZONE_LINE_FIT_NANO)
        results.append({"zone": zone.name, "abs_error_micros": _micros(error), "_error": error,
                        "lines_compared": len(keys), "lines_within_rounding": fits})
    ordered = sorted(results, key=lambda r: r["_error"])
    clear = ordered[1]["_error"] - ordered[0]["_error"] >= ZONE_TIE_NANO
    best = ordered[0]["zone"] if clear else None
    tied = [r["zone"] for r in ordered if r["_error"] - ordered[0]["_error"] < ZONE_TIE_NANO]
    for r in results:
        r.pop("_error")
    if best is None:
        message = (f"The zones {', '.join(tied)} fit equally well on these days (their errors differ by under USD 0.01), so "
                   "the check cannot tell them apart; it needs a boundary hour with more usage.")
    elif best == assumed.name:
        message = f"The bill's days follow {best}, the zone this report assumes."
    else:
        message = (f"The bill's days follow {best} better than {assumed.name}, the zone this report assumes. "
                   f"Re-run with --billing-zone {best}.")
    return {"assumed_zone": assumed.name, "status": "ok", "best_fit": best, "assumed_zone_fits_best": best == assumed.name,
            "days_compared": [d.isoformat() for d in comparable], "candidates": results, "message": message}


# ---- the committed provider bills -------------------------------------------

def bills_with_month(committed: dict, huggingface, month: str, as_of: str,
                     route_models: dict[str, str] | None = None) -> dict:
    """``profiles/provider_bills.json`` with ``month``'s Hugging Face days replaced by this bill's.

    Only the models the route registry names are kept, and only days with
    requests; other months stay as they were. The version becomes
    ``provider-bills-<as_of>``, so the next sweep rewrites the rows
    (cost_ledger.rules_version). Days, model ids, counts and nano-USD only: no
    tenant id is ever in the file.
    """
    month_of(month)
    date.fromisoformat(as_of)
    bill = parse_huggingface(huggingface)
    models = {_model_key(model): model for model in (route_models or default_route_models()).values()}
    days = {day: cells for day, cells in committed["huggingface"]["days"].items() if not day.startswith(month + "-")}
    for day, cells in sorted(bill.days.items()):
        if day.strftime("%Y-%m") != month:
            continue
        kept = {models[key]: {"requests": requests, "nano_usd": nano}
                for key, (requests, nano) in sorted(cells.items()) if key in models and requests > 0}
        if kept:
            days[day.isoformat()] = dict(sorted(kept.items()))
    return {**committed, "version": f"provider-bills-{as_of}", "as_of": as_of,
            "huggingface": {**committed["huggingface"], "days": dict(sorted(days.items()))}}


# ---- the report -------------------------------------------------------------

STRUCTURAL_GAPS = (
    "The Jobs SKUs bill every Cloud Run job of the project, including the intake jobs, which the meter does not allocate.",
    "Google services other than Cloud Run, Cloud Storage and Cloud SQL are not split by tenant: the registry, builds and "
    "secrets are fixed platform costs; internet egress and SQL Connect operations are driven by use and not split yet; "
    "the rest (Logging, Hosting, Monitoring, BigQuery, and so on) is not metered.",
    "Google's free tier is shared by every project on the billing account.",
    "Held calls are counted at their full reservation because their spend is unknown; the bill charges only what finished. "
    "Once a month's provider bill is committed (profiles/provider_bills.json), the meter trues them up to the bill's mean "
    "per request (cost basis trued_up).",
    "A provider may charge less than the list price the meter uses (for example cached input).",
    "Tool calls carry no provider in the meter, so they are listed beside the comparison but never compared with a bill.",
    "Google reports late usage on the next invoice month; the latest days of a bill can still change.",
)


def reconcile(*, meter_rows, huggingface=None, google=None, month: str, thresholds: Thresholds | None = None,
              route_models: dict[str, str] | None = None, project_id: str | None = None,
              billing_zone: str = DEFAULT_BILLING_ZONE, free_credit_types=FREE_CREDIT_TYPES,
              input_warnings=()) -> dict:
    """Compare one month of meter rows with the supplied bills.

    ``meter_rows``: CostEntry rows (a list, or a Data Connect response holding
    ``costEntries``). ``huggingface``: either bill shape of ``parse_huggingface``.
    ``google``: one document, or a tuple of documents (see ``parse_google``). Either bill
    may be None; its section then says it was not supplied. ``project_id`` keeps
    only that project's export rows (others are totalled apart). ``input_warnings``
    are texts the caller noticed about its input files (a possibly truncated page);
    the report carries them under ``warnings``.
    """
    month_of(month)
    limits = thresholds or Thresholds()
    zone = BillingZone(billing_zone)
    rows, meter_info = parse_meter_rows(meter_rows, month)
    hf_bill = None if huggingface is None else parse_huggingface(huggingface)
    documents = () if google is None else google if isinstance(google, tuple) else (google,)
    g_bill = None if google is None else parse_google(*documents, free_credit_types=free_credit_types)
    hf = _hf_section(rows, hf_bill, month, route_models if route_models is not None else default_route_models(), limits)
    day_check = check_billing_day(g_bill, zone, project_id)
    gg, meter_other = _google_section(rows, g_bill, month, zone, project_id, limits, day_check)
    meter_total = sum(r.cost for r in rows)
    hf_billed = hf["totals"]["billed_micros"] if hf["supplied"] else 0
    g_billed = gg["totals"]["billed_micros"] if gg["supplied"] else 0
    hf_metered, g_metered = hf["totals"]["metered_micros"], gg["totals"]["metered_micros"]
    other_metered = meter_other["cost_micros"]
    g_other = gg["totals"]["billed_other_credits_micros"] if gg["supplied"] else 0
    totals = {
        "billed_micros": hf_billed + g_billed,
        "billed_net_micros": hf_billed + g_billed + g_other,
        "billed_huggingface_micros": hf_billed, "billed_google_micros": g_billed,
        "billed_google_cost_micros": gg["totals"]["billed_cost_micros"] if gg["supplied"] else 0,
        "billed_google_credits_micros": gg["totals"]["billed_credits_micros"] if gg["supplied"] else 0,
        "billed_google_other_credits_micros": g_other,
        "billed_google_other_credits_by_type": gg["totals"]["billed_other_credits_by_type"] if gg["supplied"] else {},
        "billed_google_net_micros": gg["totals"]["billed_net_micros"] if gg["supplied"] else 0,
        "billed_google_unmetered_micros": gg["totals"]["billed_unmetered_micros"] if gg["supplied"] else 0,
        "metered_micros": meter_total,
        "metered_huggingface_micros": hf_metered, "metered_google_micros": g_metered,
        "metered_other_micros": other_metered,
    }
    totals["gap_micros"] = totals["metered_micros"] - totals["billed_micros"]
    totals["gap_percent"] = _percent(totals["gap_micros"], totals["billed_micros"])
    comparable_billed = (hf_billed if hf["supplied"] else 0) + (gg["totals"]["billed_families_micros"] if gg["supplied"] else 0)
    comparable_metered = (hf_metered if hf["supplied"] else 0) + (gg["totals"]["metered_families_micros"] if gg["supplied"] else 0)
    totals["comparable_billed_micros"], totals["comparable_metered_micros"] = comparable_billed, comparable_metered
    totals["comparable_gap_micros"] = comparable_metered - comparable_billed
    totals["comparable_gap_percent"] = _percent(totals["comparable_gap_micros"], comparable_billed)
    flags = _flags(hf, gg, totals, limits, day_check, zone)
    return {
        "month": month, "currency": "USD",
        "thresholds": {"absolute_micros": limits.absolute_micros, "relative": limits.relative},
        "billing_zone": {"used": zone.name, "check": day_check},
        "inputs": {**meter_info, "meter_rows_in_month": len(rows),
                   "huggingface_supplied": hf["supplied"], "google_supplied": gg["supplied"],
                   "google_source": gg["source"], "google_project": project_id,
                   "meter_has_allocation_rows": any(r.is_allocation for r in rows)},
        "huggingface": hf, "google": gg, "meter_other": meter_other, "totals": totals, "flags": flags,
        "warnings": [str(text) for text in input_warnings],
        "structural_gaps": list(STRUCTURAL_GAPS),
    }


def _flags(hf: dict, gg: dict, totals: dict, limits: Thresholds, day_check: dict, zone: BillingZone) -> list[dict]:
    flags = []
    for e in hf["models"]:
        if e["flagged"]:
            flags.append({"scope": "huggingface", "key": e["label"], "billed_micros": e["billed_micros"],
                          "metered_micros": e["metered_micros"], "gap_micros": e["gap_micros"],
                          "gap_percent": e["gap_percent"], "threshold_micros": e["threshold_micros"],
                          "explanations": e["explanations"]})
    for f in gg["families"]:
        if f["flagged"]:
            flags.append({"scope": "google", "key": f["family"], "billed_micros": f["billed_after_allowance_micros"],
                          "metered_micros": f["meter_after_allowance_micros"], "gap_micros": f["gap_micros"],
                          "gap_percent": f["gap_percent"], "threshold_micros": f["threshold_micros"],
                          "explanations": f["explanations"]})
    if day_check.get("status") == "ok" and day_check.get("best_fit") not in (None, zone.name):
        flags.append({"scope": "google", "key": "billing_day", "billed_micros": None, "metered_micros": None,
                      "gap_micros": None, "gap_percent": None, "threshold_micros": None,
                      "explanations": [_explain("billing_zone", day_check["message"])]})
    if hf["supplied"] and gg["supplied"] and limits.exceeded(totals["gap_micros"], totals["billed_micros"]):
        parts = []
        if totals["billed_google_unmetered_micros"]:
            parts.append(_explain("unmetered_services", f"{usd(totals['billed_google_unmetered_micros'])} of the bill is for "
                                  "Google services the meter does not cover."))
        if totals["metered_other_micros"]:
            parts.append(_explain("tools_without_bill", f"{usd(totals['metered_other_micros'])} of the meter is tool calls "
                                  "and other rows with no bill to compare."))
        listed = [f["key"] for f in flags if f["scope"] != "total"]
        if listed:
            parts.append(_explain("flagged_items", "Flagged above: " + ", ".join(listed) + "."))
        flags.append({"scope": "total", "key": "all", "billed_micros": totals["billed_micros"],
                      "metered_micros": totals["metered_micros"], "gap_micros": totals["gap_micros"],
                      "gap_percent": totals["gap_percent"], "threshold_micros": limits.limit(totals["billed_micros"]),
                      "explanations": parts or [_explain("unexplained", "The parts do not show a cause for the total gap.")]})
    return flags


# ---- plain-language report --------------------------------------------------

def _table(headers: list[str], body: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(row) + " |" for row in body]
    return lines


def _other_cell(micros: int, by_type: dict) -> str:
    """An amount of other credits and, when there is any, the types that make it up."""
    return f"{usd(micros)} ({', '.join(by_type)})" if by_type else usd(micros)


TREATMENT_LABELS = {FIXED_PLATFORM: "fixed platform", SHARED_NOT_SPLIT: "shared, not split yet",
                    NOT_METERED: "not metered"}


def _treatments_text(by_treatment: dict) -> str:
    """``$1.85 fixed platform, $3.24 shared, not split yet`` (nonzero parts only)."""
    parts = [f"{usd(amount)} {TREATMENT_LABELS[kind]}" for kind, amount in by_treatment.items() if amount]
    return ", ".join(parts) or "none"


def _gap_text(gap: int, percent) -> str:
    if gap == 0:
        return "no difference"
    tail = f" ({abs(percent):.1f}%)" if percent is not None else ""
    return f"the meter is {usd(abs(gap))} {_direction(gap)} the bill{tail}"


def render_markdown(report: dict) -> str:
    """A short report for the owner: the headline, what needs a look and why, then the tables."""
    t, month = report["totals"], report["month"]
    limit = report["thresholds"]
    out = [f"# Cost meter check, {month}", ""]
    hf, gg, other = report["huggingface"], report["google"], report["meter_other"]
    other_credits = t["billed_google_other_credits_micros"]
    net_note = f" ({usd(t['billed_net_micros'])} net of {usd(abs(other_credits))} of other credits)" if other_credits else ""
    if hf["supplied"] and gg["supplied"]:
        out.append(f"Billed: {usd(t['billed_micros'])} after the free tier{net_note}. Metered: {usd(t['metered_micros'])}. "
                   f"Overall, {_gap_text(t['gap_micros'], t['gap_percent'])}.")
    else:
        supplied = "Hugging Face" if hf["supplied"] else "Google Cloud" if gg["supplied"] else None
        lead = (f"Billed: {usd(t['billed_micros'])} after the free tier{net_note}; only the {supplied} bill was supplied."
                if supplied else "No bill was supplied.")
        out.append(f"{lead} Metered: {usd(t['metered_micros'])}, every row of the month. "
                   "The overall comparison is partial; the like-for-like line below is the one to read.")
    out.append("")
    if hf["supplied"]:
        out.append(f"- Hugging Face: billed {usd(t['billed_huggingface_micros'])}, metered {usd(t['metered_huggingface_micros'])}.")
    else:
        out.append("- Hugging Face: no bill supplied.")
    if gg["supplied"]:
        by_type = t["billed_google_other_credits_by_type"]
        others = f"other credits {usd(other_credits)} ({types_text(by_type)})" if other_credits else "no other credits"
        out.append(f"- Google Cloud: cost {usd(t['billed_google_cost_micros'])}, free-tier credits "
                   f"{usd(t['billed_google_credits_micros'])}, {others}; net charge {usd(t['billed_google_net_micros'])}. "
                   f"Compared after the free tier: billed {usd(t['billed_google_micros'])}, of which "
                   f"{usd(t['billed_google_unmetered_micros'])} is for services the meter does not split "
                   f"({_treatments_text(gg['unmetered']['by_treatment'])}); "
                   f"metered {usd(t['metered_google_micros'])}.")
        if other_credits:
            out.append("- The meter holds no counterpart to the other credits, so the comparison does not subtract them. "
                       f"If one of these types is the free tier ({', '.join(by_type)}), re-run with "
                       "--free-credit-type <TYPE>.")
    else:
        out.append("- Google Cloud: no bill supplied.")
    if t["metered_other_micros"]:
        out.append(f"- Tool calls and other rows with no bill to compare: {usd(t['metered_other_micros'])}.")
    out.append(f"- Like for like (the services the meter covers): billed {usd(t['comparable_billed_micros'])}, "
               f"metered {usd(t['comparable_metered_micros'])}; {_gap_text(t['comparable_gap_micros'], t['comparable_gap_percent'])}.")
    if report["warnings"]:
        out += ["", "## Warnings", ""] + [f"- {text}" for text in report["warnings"]]
    out += ["", f"## What needs a look ({len(report['flags'])})", ""]
    if not report["flags"]:
        out.append(f"No gap is above the limit of the larger of {usd(limit['absolute_micros'])} and "
                   f"{limit['relative'] * 100:g}% of the billed amount.")
    else:
        out.append(f"A gap is flagged when it is above the larger of {usd(limit['absolute_micros'])} and "
                   f"{limit['relative'] * 100:g}% of the billed amount. Held calls are calls whose cost was unknown "
                   "(a timeout or server error); the meter counts them at the most they could have cost.")
        for flag in sorted(report["flags"], key=lambda f: -abs(f["gap_micros"] or 0)):
            out += ["", f"### {flag['scope']}: {flag['key']}"]
            if flag["gap_micros"] is not None:
                out.append(f"Billed {usd(flag['billed_micros'])}, metered {usd(flag['metered_micros'])}: "
                           f"{_gap_text(flag['gap_micros'], flag['gap_percent'])}.")
            out += [f"- {x['text']}" for x in flag["explanations"]]
    if hf["supplied"] or hf["models"]:
        out += ["", "## Hugging Face, by model", ""]
        body = [[e["label"], usd(e["billed_micros"]), str(e["billed_requests"]), usd(e["metered_settled_micros"]),
                 usd(e["metered_estimated_micros"]), usd(e["metered_held_micros"]), str(e["meter_calls"]),
                 str(e["meter_requests"]), usd(e["gap_micros"]),
                 "n/a" if e["gap_percent"] is None else f"{e['gap_percent']:.1f}%", "yes" if e["flagged"] else ""]
                for e in hf["models"]]
        body.append(["Total", usd(hf["totals"]["billed_micros"]), str(hf["totals"]["billed_requests"]),
                     usd(hf["totals"]["metered_settled_micros"]), usd(hf["totals"]["metered_estimated_micros"]),
                     usd(hf["totals"]["metered_held_micros"]), str(hf["totals"]["meter_calls"]),
                     str(hf["totals"]["meter_requests"]), usd(hf["totals"]["gap_micros"]),
                     "n/a" if hf["totals"]["gap_percent"] is None else f"{hf['totals']['gap_percent']:.1f}%", ""])
        out += _table(["Model", "Billed", "Requests billed", "Metered settled", "of it estimated", "Metered held",
                       "Meter calls", "Requests they made", "Gap", "Gap %", "Flagged"], body)
    if gg["supplied"] or any(f["meter_rows"] for f in gg["families"]):
        out += ["", "## Google Cloud, by cost family", ""]
        body = [[f["label"], usd(f["billed_cost_micros"]), usd(f["billed_credits_micros"]),
                 _other_cell(f["billed_other_credits_micros"], f["billed_other_credits_by_type"]),
                 usd(f["billed_net_micros"]), usd(f["billed_after_allowance_micros"]), usd(f["meter_list_micros"]),
                 usd(f["meter_after_allowance_micros"]), usd(f["gap_micros"]),
                 "n/a" if f["gap_percent"] is None else f"{f['gap_percent']:.1f}%", "yes" if f["flagged"] else ""]
                for f in gg["families"]]
        out += _table(["Family", "Cost", "Free-tier credits", "Other credits", "Net charge", "Billed after free tier",
                       "Meter before free tier", "Meter after free tier", "Gap", "Gap %", "Flagged"], body)
        if gg["unmetered"]["lines"]:
            out += ["", "### Google lines the meter does not split", ""]
            shown = gg["unmetered"]["lines"][:15]
            out += _table(["Service", "SKU", "Cost", "Free-tier credits", "Other credits", "Net charge", "Treatment"],
                          [[l["service"], l["sku"], usd(l["cost_micros"]), usd(l["credits_micros"]),
                            _other_cell(l["other_credits_micros"], l["other_credits_by_type"]), usd(l["net_micros"]),
                            f"{TREATMENT_LABELS[l['treatment']]}: {l['treatment_reason']}"]
                           for l in shown])
            if len(gg["unmetered"]["lines"]) > len(shown):
                out.append(f"\n{len(gg['unmetered']['lines']) - len(shown)} smaller lines are in the JSON report.")
    unbilled = [[r["provider"], r["kind"], r["resource"], str(r["rows"]), usd(r["cost_micros"])] for r in other["rows"]]
    if gg["meter_unplaced"]["rows"]:
        unbilled.append(["google_cloud", "", "(not placed in a family)", str(gg["meter_unplaced"]["rows"]),
                         usd(gg["meter_unplaced"]["cost_micros"])])
    if gg["meter_unassigned_credits_micros"]:
        unbilled.append(["google_cloud", "", "(free allowance, not placed in a family)", "",
                         usd(gg["meter_unassigned_credits_micros"])])
    if unbilled:
        out += ["", "## Metered rows with no bill to compare", ""]
        out += _table(["Provider", "Kind", "Resource", "Rows", "Metered"], unbilled)
    check = report["billing_zone"]["check"]
    out += ["", "## Billing-day time zone", "",
            f"This report cuts Google's days in {report['billing_zone']['used']}."]
    if check["status"] == "ok":
        out.append(check["message"])
        out += _table(["Zone", "Total difference", "Lines compared", "Lines within rounding"],
                      [[c["zone"], usd(c["abs_error_micros"]), str(c["lines_compared"]), str(c["lines_within_rounding"])]
                       for c in check["candidates"]])
    else:
        out.append(f"The day-boundary check did not run. {check['reason']}")
    out += ["", "## Inputs and limits", ""]
    i = report["inputs"]
    out.append(f"- Meter rows for {month}: {i['meter_rows_in_month']} ({i['rows_supplied']} supplied, "
               f"{i['rows_other_month']} from other months, {i['duplicates_dropped']} duplicates dropped).")
    if not i["meter_has_allocation_rows"]:
        out.append("- The meter holds no allocation rows, so shared Google costs are not in it.")
    if gg["supplied"]:
        what = "export rows" if gg["source"] == "export" else "console lines"
        out.append(f"- Google bill read from the {what}; {gg['lines_outside_month']} fall outside {month}.")
        if gg["other_projects"]["lines"]:
            out.append(f"- {gg['other_projects']['lines']} lines belong to other projects on the billing account "
                       f"({usd(gg['other_projects']['cost_micros'])} before credits) and are left out.")
        if gg["invoice_month_shift"]["lines"]:
            out.append(f"- {gg['invoice_month_shift']['lines']} lines of {month} usage sit on a different invoice month "
                       f"({usd(gg['invoice_month_shift']['cost_micros'])}); the console's billing-period view will differ.")
    out += [f"- {text}" for text in report["structural_gaps"]]
    return "\n".join(out) + "\n"
