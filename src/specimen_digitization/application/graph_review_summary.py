"""Bounded queue-only compatibility counts for older externalized active graphs.

The authorized search returns identities and graph metadata, never snapshots.
Only successful compact counts are retained; graph bytes die with each read.
"""

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore, Event, Lock
import time

from .active_graph import validate_graph_metadata, verified_graph_run
from .review_summary import project_fields, review_summary

CACHE_ENTRIES = 256
PAGE_READS = 32
PAGE_BYTES = 32 * 1024 * 1024
PAGE_SECONDS = 8.0
CONCURRENT_READS = 2


def bound_metadata(row, metadata):
    return validate_graph_metadata(
        metadata,
        scope={"organization_id": row["organization_id"], "collection_id": row["collection_id"]},
        specimen_id=row["specimen_id"], revision=row["revision"], run_id=row["active_run_id"],
    )


def compact_summary(row, fields, metadata):
    """Use inline fields or the exact graph's versioned content-free projection."""
    from .storage import digest

    if metadata is None:
        return review_summary(fields, row.get("reason_codes"))
    try:
        bound_metadata(row, metadata)
        projection = metadata["field_review"]
        if (projection["version"] != "field-review-v1"
                or projection["reasons_sha256"] != digest(row["reason_codes"])
                or projection["fields"] != fields):
            return None
        return review_summary(fields, row["reason_codes"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


class _PageBudget:
    def __init__(self):
        self.deadline = time.monotonic() + PAGE_SECONDS
        self.reads = 0
        self.bytes = 0
        self.attempted = set()
        self.lock = Lock()

    def reserve(self, key, size):
        with self.lock:
            if (time.monotonic() >= self.deadline or self.reads >= PAGE_READS
                    or self.bytes + size > PAGE_BYTES or key in self.attempted):
                return False
            self.attempted.add(key)
            self.reads += 1
            self.bytes += size
            return True


class GraphReviewCache:
    """Repository-local, scoped positive LRU and cross-page single-flight reads."""

    def __init__(self):
        self._values = OrderedDict()
        self._inflight = {}
        self._lock = Lock()
        self._slots = BoundedSemaphore(CONCURRENT_READS)

    def _cached(self, key):
        with self._lock:
            value = self._values.get(key)
            if value is not None:
                self._values.move_to_end(key)
                return dict(value)
        return None

    def _load(self, key, row, metadata, size, blobs, budget):
        from .storage import digest

        cached = self._cached(key)
        if cached is not None:
            return cached
        with self._lock:
            # Recheck while claiming ownership, so a completed read is not repeated.
            if key in self._values:
                self._values.move_to_end(key)
                return dict(self._values[key])
            event = self._inflight.get(key)
            owner = event is None
            if owner:
                event = self._inflight[key] = Event()
        if not owner:
            event.wait(max(0, budget.deadline - time.monotonic()))
            return self._cached(key)
        acquired = False
        try:
            acquired = self._slots.acquire(timeout=max(0, budget.deadline - time.monotonic()))
            if not acquired or not budget.reserve(key, size):
                return None
            raw = blobs.get_bounded_until(metadata["blob_ref"], size, budget.deadline)
            if time.monotonic() >= budget.deadline:
                return None
            run = verified_graph_run(raw, metadata)
            if digest(run.get("reasons", [])) != digest(row["reason_codes"]):
                return None
            result = review_summary(project_fields(run.get("fields")), row["reason_codes"])
            if result is not None:
                with self._lock:
                    self._values[key] = dict(result)
                    self._values.move_to_end(key)
                    while len(self._values) > CACHE_ENTRIES:
                        self._values.popitem(last=False)
            return result
        except Exception:  # Unavailable/invalid evidence is unknown, never zero.
            return None
        finally:
            if acquired:
                self._slots.release()
            with self._lock:
                self._inflight.pop(key, None)
                event.set()

    def hydrate(self, rows, metadata, blobs):
        """At most two joined workers; no futures/streams outlive this page."""
        from .storage import digest

        if blobs is None or not callable(getattr(blobs, "get_bounded_until", None)):
            return
        jobs = []
        for row, graph in zip(rows, metadata, strict=True):
            if row.get("review_summary") is not None or not isinstance(graph, dict) or "field_review" in graph:
                continue
            try:
                size = bound_metadata(row, graph)
                reasons = row["reason_codes"]
                if not isinstance(reasons, list) or any(not isinstance(reason, str) for reason in reasons):
                    continue
                key = (id(blobs), row["organization_id"], row["collection_id"], row["specimen_id"],
                    row["revision"], row["active_run_id"], graph["blob_ref"], graph["sha256"],
                    graph["run_sha256"], size, digest(reasons), "field-review-v1")
                cached = self._cached(key)
                if cached is not None:
                    row["review_summary"] = cached
                else:
                    jobs.append((key, row, graph, size))
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
        if not jobs:
            return
        budget = _PageBudget()
        iterator = iter(jobs)
        jobs_lock = Lock()

        def worker():
            while time.monotonic() < budget.deadline:
                with jobs_lock:
                    job = next(iterator, None)
                if job is None:
                    return
                key, row, graph, size = job
                row["review_summary"] = self._load(key, row, graph, size, blobs, budget)

        # Reads have explicit I/O deadlines. Joining, rather than abandoning a
        # timed-out future, keeps the concurrency/resource bound real.
        with ThreadPoolExecutor(max_workers=min(CONCURRENT_READS, len(jobs))) as executor:
            futures = [executor.submit(worker) for _ in range(min(CONCURRENT_READS, len(jobs)))]
            for future in futures:
                future.result()
