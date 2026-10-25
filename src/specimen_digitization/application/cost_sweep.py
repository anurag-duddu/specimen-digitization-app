"""The cost meter's backfill and repair sweep (docs/execution/golive/COST_METER.md).

At the start of each collection's drain the worker pages through the specimens
saved since its watermark, reads every run's paid calls (ListRunPaidCallsV1)
and upserts their rows (UpsertCostEntriesV1). It is bounded by a time budget
and a page count, resumes where it stopped, and fails open: a failure is
logged by code and the drain goes on as it would have without it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5

from .storage import Conflict, Missing

LOGGER = logging.getLogger(__name__)
CURSOR_KIND = "worker_cursor"  # The worker's own state documents, one actor only.
SWEEP_SECONDS = 60
SWEEP_PAGES = 40
PAGE_SPECIMENS = 10
# Specimens saved this long before the previous pass began are swept again:
# the connector stamps saves with its own clock, and a save may commit late.
OVERLAP = timedelta(hours=1)
EPOCH = "1970-01-01T00:00:00+00:00"
OPERATIONS = ("run_paid_calls_page", "send_cost_rows", "document", "put_document")


class _OutOfTime(Exception):
    """The sweep's budget ran out inside a page; that page is read again next time."""


def cursor_id(scope) -> str:
    return str(uuid5(NAMESPACE_URL, f"cost-meter-sweep:{scope.organization_id}/{scope.collection_id}"))


def _code(error) -> str:
    from ..process_logging import log_code
    from .cost_ledger import CostRowInvalid

    return log_code(str(error) if isinstance(error, CostRowInvalid) else type(error).__name__)


def _moment(value) -> bool:
    try:
        return isinstance(value, str) and datetime.fromisoformat(value).tzinfo is not None
    except ValueError:
        return False


def _cursor(repository, scope, rules):
    """The stored watermark; a missing or unreadable one starts a pass over everything.

    So does one written under other rules (``cost_ledger.rules_version``: the
    true-up rules and the committed bills), so every earlier row is derived again.
    """
    from .lane_worker import stored_integer

    fresh = {"swept_since": EPOCH, "after_id": "", "pass_started_at": None}
    try:
        stored = repository.document(scope, CURSOR_KIND, cursor_id(scope))
    except Missing:
        return {"revision": 0, **fresh}
    revision = stored_integer(stored["revision"])
    since, after, started = stored.get("swept_since"), stored.get("after_id"), stored.get("pass_started_at")
    if not _moment(since) or not isinstance(after, str) or (after and not _moment(started)):
        LOGGER.warning("cost sweep cursor unreadable; sweeping everything again")
        return {"revision": revision, **fresh}
    if stored.get("rules") != rules:
        LOGGER.info("cost sweep rules changed; sweeping everything again")
        return {"revision": revision, **fresh}
    return {"revision": revision, "swept_since": since, "after_id": after,
            "pass_started_at": started if after else None}


def _specimen_rows(scope, specimen_id, items, result):
    """The rows of every run of one specimen; a run whose calls cannot be read is skipped."""
    from .cost_ledger import CostRowInvalid, call_rows

    rows = []
    for item in items:
        try:
            rows += call_rows(scope.organization_id, scope.collection_id, specimen_id,
                              item["run_id"], item["paid_calls"])
        except (CostRowInvalid, ValueError, KeyError, TypeError) as error:
            result["skipped"] += 1
            LOGGER.warning("cost sweep skipped a run: %s", _code(error))
    return rows


def sweep(repository, scope, *, clock=None, stop=None, until=None, seconds=SWEEP_SECONDS,
          pages=SWEEP_PAGES, page_size=PAGE_SPECIMENS) -> dict:
    """Upsert the cost rows of the specimens saved since the watermark, bounded.

    ``until`` (a datetime) ends the sweep before its own budget does, at the
    drain's window for one; a call already sent finishes first. The watermark
    is saved after the last page done in full, so a stopped or failed pass
    resumes there; a completed pass moves it to that pass's start, less
    OVERLAP. A refused record is logged and passed over. A repository without
    the cost operations is left alone.
    """
    clock = clock or (lambda: datetime.now(timezone.utc))
    result = {"status": "unsupported", "pages": 0, "specimens": 0, "rows": 0, "skipped": 0}
    if not all(callable(getattr(repository, name, None)) for name in OPERATIONS):
        return result
    started = clock()
    stop_at = started + timedelta(seconds=seconds)
    if until is not None:
        stop_at = min(stop_at, until)

    def out_of_time():
        return (stop is not None and stop.is_set()) or clock() >= stop_at

    try:
        from .cost_ledger import rules_version

        rules = rules_version()
        cursor = _cursor(repository, scope, rules)
    except Exception as error:  # noqa: BLE001 - the sweep never stops the drain
        LOGGER.warning("cost sweep stopped: %s", _code(error))
        result["status"] = "failed"
        return result
    since, after = cursor["swept_since"], cursor["after_id"]
    pass_started = cursor["pass_started_at"] or started.isoformat()
    result["status"], failure = "partial", None
    try:
        while result["pages"] < pages and not out_of_time():
            page = repository.run_paid_calls_page(scope, after, since, page_size)
            by_specimen: dict[str, list] = {}
            for item in page["items"]:
                by_specimen.setdefault(item["specimen_id"], []).append(item)
            for specimen_id, items in sorted(by_specimen.items()):
                if out_of_time():
                    raise _OutOfTime()
                rows = _specimen_rows(scope, specimen_id, items, result)
                try:
                    if rows:
                        result["rows"] += repository.send_cost_rows(scope, rows[0]["specimen_id"], rows)
                except Conflict as error:
                    # The connector refused this record's rows: passed over.
                    result["skipped"] += 1
                    LOGGER.warning("cost sweep skipped a record: %s", _code(error))
                result["specimens"] += 1
            result["pages"] += 1
            after = page.get("last_id") or after
            if page["specimens"] < page_size:
                result["status"] = "complete"
                break
    except _OutOfTime:
        pass
    except Exception as error:  # noqa: BLE001 - the sweep never stops the drain
        failure = error
    try:
        if result["status"] == "complete":
            payload = {"swept_since": (datetime.fromisoformat(pass_started) - OVERLAP).isoformat(),
                       "after_id": "", "pass_started_at": None}
        else:
            payload = {"swept_since": since, "after_id": after, "pass_started_at": pass_started}
        if result["pages"]:
            repository.put_document(scope, CURSOR_KIND, cursor_id(scope),
                                    {"sensitive": False, **payload, "rules": rules}, cursor["revision"])
    except Exception as error:  # noqa: BLE001 - the next pass starts from the old watermark
        failure = failure or error
    if failure is not None:
        LOGGER.warning("cost sweep stopped: %s", _code(failure))
        result["status"] = "failed"
    return result
