"""The cost meter's allocation job at each drain (cost_allocator; COST_METER.md, PR 3)."""

from __future__ import annotations

import logging
import threading
from datetime import date, datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5

import pytest

from specimen_digitization.application import cost_allocator
from specimen_digitization.application.cost_allocation import day_bounds, day_hours
from specimen_digitization.application.cost_allocator import CURSOR_KIND, CostAllocator, cursor_id
from specimen_digitization.application.cost_monitoring import MonitoringClient, MonitoringFailed, MonitoringUnavailable
from specimen_digitization.application.domain import Scope
from specimen_digitization.application.lane_worker import DrainWorker
from specimen_digitization.application.storage import Conflict, Missing

from test_cost_sweep import CostingMember, Recording
from test_lane_drain import COLLECTION, ORG, WORKER, Clock, NonSensitiveMember, ScriptedWorkflow, queued

UTC = timezone.utc
SCOPE = Scope(organization_id=ORG, collection_id=COLLECTION)
SIBLING = "00000000-0000-4000-8000-000000000004"
SECOND = Scope(organization_id=ORG, collection_id=SIBLING)
OTHER_ORG = "00000000-0000-4000-8000-0000000000f1"
FOREIGN = "00000000-0000-4000-8000-0000000000f2"
NOW = datetime(2026, 10, 5, 12, tzinfo=UTC)  # 2026-10-01 to 2026-10-04 are complete
JOB = "specimen-worker"


def ident(n):
    return f"00000000-0000-4000-8000-{n:012x}"


def collections():
    """The connector's per-collection measures: this collection, a sibling and another organization's."""
    return [
        {"organization_id": ORG, "collection_id": COLLECTION, "saves": "3", "month_saves": "3",
         "worker_seconds": "300", "month_worker_seconds": "300", "sam_seconds": "10", "month_sam_seconds": "10",
         "sam_direct_micros": "500", "asset_bytes": "100", "specimens": "2"},
        {"organization_id": ORG, "collection_id": SIBLING, "saves": "1", "month_saves": "1",
         "worker_seconds": "100", "month_worker_seconds": "100", "sam_seconds": "10", "month_sam_seconds": "10",
         "sam_direct_micros": "0", "asset_bytes": "100", "specimens": "2"},
        {"organization_id": OTHER_ORG, "collection_id": FOREIGN, "saves": "4", "month_saves": "4",
         "specimens": "4"},
    ]


class Monitoring:
    """The client surface read_usage uses: one SAM 3 and one worker reading in each day's first hour."""

    def __init__(self, error=None, days=(1, 2, 3, 4), location="us-east4", on_read=None):
        self.error, self.days, self.location, self.on_read = error, days, location, on_read
        self.calls = []

    def series(self, metric_filter, start, end, aligner, *, stop_at=None):
        self.calls.append((metric_filter, start, end, stop_at))
        if self.on_read:
            self.on_read()
        if self.error is not None:
            raise self.error
        def points(value):
            return [{"interval": {"endTime": (day_hours(date(2026, 10, n))[0] + timedelta(hours=1))
                                  .strftime("%Y-%m-%dT%H:%M:%SZ")}, "value": {"doubleValue": value}}
                    for n in self.days]
        if 'resource.type="cloud_run_job"' in metric_filter:
            return [{"resource": {"labels": {"job_name": JOB}}, "points": points(100)}]
        if "cloud_run_revision" in metric_filter and "billable_instance_time" in metric_filter:
            return [{"resource": {"labels": {"service_name": "specimen-sam"}}, "points": points(50)}]
        if "storage/v2" in metric_filter:
            return [{"resource": {"labels": {"location": self.location}}, "points": points(2**30)}]
        return []


class Repo:
    """The repository surface the allocator uses, with the worker cursor's compare-and-set."""

    def __init__(self):
        self.documents, self.sent, self.inputs = {}, [], []
        self.fail_send = self.fail_put = None
        self.after_send = None

    def document(self, scope, kind, key):
        if (scope.collection_id, kind, key) not in self.documents:
            raise Missing(key)
        return dict(self.documents[(scope.collection_id, kind, key)])

    def put_document(self, scope, kind, key, payload, expected):
        if self.fail_put:
            raise self.fail_put
        current = self.documents.get((scope.collection_id, kind, key), {}).get("revision", 0)
        if current != expected:
            raise Conflict("revision conflict")
        self.documents[(scope.collection_id, kind, key)] = dict(payload, revision=expected + 1)
        return self.documents[(scope.collection_id, kind, key)]

    def cost_allocation_inputs(self, scope, day_start, day_end, month_start, gap_seconds):
        self.inputs.append((scope.collection_id, day_start, day_end, month_start, gap_seconds))
        return collections()

    def send_cost_allocations(self, scope, rows):
        if self.fail_send and self.fail_send(rows):
            raise Conflict("cost_allocations_refused")
        self.sent.append((scope, rows))
        if self.after_send:
            self.after_send()
        return len(rows)

    def cursor(self, scope=SCOPE):
        return self.documents.get((scope.collection_id, CURSOR_KIND, cursor_id(scope)))

    def days(self):
        return sorted({row["billing_day"] for _, rows in self.sent for row in rows})


def allocator(monitoring=None, clock=lambda: NOW, **kwargs):
    return CostAllocator(monitoring or Monitoring(), job=JOB, bucket="specimen-digitization.firebasestorage.app",
                         clock=clock, **kwargs)


SERVED = [(ORG, COLLECTION), (ORG, SIBLING)]


def test_the_cursor_is_the_worker_s_own_document_per_collection():
    assert cursor_id(SCOPE) == str(uuid5(NAMESPACE_URL, f"cost-meter-allocation:{ORG}/{COLLECTION}"))
    assert cursor_id(SECOND) != cursor_id(SCOPE) and CURSOR_KIND == "worker_cursor"


def test_every_due_day_is_written_for_this_collection_only_and_the_cursor_follows_each_day():
    repo, monitoring = Repo(), Monitoring()
    result = allocator(monitoring).run(repo, SCOPE, job_collections=SERVED)
    assert result == {"status": "complete", "days": 4, "rows": result["rows"], "through": "2026-10-04"}
    assert repo.days() == ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"]
    assert {(row["organization_id"], row["collection_id"]) for _, rows in repo.sent for row in rows} == {
        (ORG, COLLECTION)}
    assert result["rows"] == sum(len(rows) for _, rows in repo.sent) > 0
    assert repo.cursor() == {"sensitive": False, "allocated_through": "2026-10-04", "revision": 4}
    # Monitoring is read once for the invoice month so far, and each day's measures once.
    assert {(start, end) for _, start, end, _ in monitoring.calls} - {
        (datetime(2026, 9, 30, 7, tzinfo=UTC), day_bounds(date(2026, 10, 4))[1])} == {
        (datetime(2026, 10, 1, 7, tzinfo=UTC), day_bounds(date(2026, 10, 4))[1])}
    assert [(start, end, first, gap) for _, start, end, first, gap in repo.inputs] == [
        (*day_bounds(date(2026, 10, n)), datetime(2026, 10, 1, 7, tzinfo=UTC), 900) for n in range(1, 5)]
    # Nothing more is due until the 5th ends: no read, no write.
    again = Repo()
    again.documents = dict(repo.documents)
    later = allocator(monitoring := Monitoring()).run(again, SCOPE, job_collections=SERVED)
    assert later == {"status": "current", "days": 0, "rows": 0, "through": "2026-10-04"}
    assert again.sent == [] and monitoring.calls == []


def test_a_second_collection_of_the_execution_reuses_the_readings_and_writes_its_own_rows():
    repo, monitoring = Repo(), Monitoring()
    shared = allocator(monitoring)
    shared.run(repo, SCOPE, job_collections=SERVED)
    reads = len(monitoring.calls)
    result = shared.run(repo, SECOND, job_collections=SERVED)
    assert result["status"] == "complete" and len(monitoring.calls) == reads
    assert len(repo.inputs) == 4  # each day's measures, once for both collections
    second = [row for scope, rows in repo.sent if scope == SECOND for row in rows]
    assert {row["collection_id"] for row in second} == {SIBLING}
    assert repo.cursor(SECOND)["allocated_through"] == "2026-10-04"


def test_the_day_bound_leaves_the_rest_to_the_next_run():
    repo = Repo()
    assert allocator(days=2).run(repo, SCOPE, job_collections=SERVED)["status"] == "partial"
    assert repo.cursor()["allocated_through"] == "2026-10-02" and repo.days() == ["2026-10-01", "2026-10-02"]
    result = allocator(days=2).run(repo, SCOPE, job_collections=SERVED)
    assert (result["status"], result["through"]) == ("complete", "2026-10-04")


@pytest.mark.parametrize("error", [MonitoringUnavailable("cost_allocation_monitoring_unavailable")])
def test_without_monitoring_access_nothing_is_written_the_cursor_stays_and_one_warning_is_logged(error, caplog):
    repo, monitoring = Repo(), Monitoring(error=error)
    shared = allocator(monitoring)
    with caplog.at_level(logging.WARNING):
        first = shared.run(repo, SCOPE, job_collections=SERVED)
        second = shared.run(repo, SECOND, job_collections=SERVED)
    assert first["status"] == second["status"] == "monitoring_unavailable"
    assert repo.sent == [] and repo.inputs == [] and repo.documents == {}
    assert len(monitoring.calls) == 1  # the second collection does not ask again
    warnings = [record.getMessage() for record in caplog.records if record.levelno == logging.WARNING]
    assert warnings == ["cost allocation stopped: cost_allocation_monitoring_unavailable"]


def test_another_monitoring_failure_is_logged_by_code_and_ends_the_execution_s_allocation(caplog):
    repo, monitoring = Repo(), Monitoring(error=MonitoringFailed("http_503"))
    shared = allocator(monitoring)
    with caplog.at_level(logging.WARNING):
        assert shared.run(repo, SCOPE, job_collections=SERVED)["status"] == "failed"
        assert shared.run(repo, SECOND, job_collections=SERVED)["status"] == "failed"
    assert repo.sent == [] and repo.documents == {} and len(monitoring.calls) == 1
    assert "cost allocation stopped: http_503" in caplog.text


def test_a_refused_write_leaves_the_cursor_on_the_last_day_written(caplog):
    repo = Repo()
    repo.fail_send = lambda rows: rows[0]["billing_day"] == "2026-10-02"
    with caplog.at_level(logging.WARNING):
        result = allocator().run(repo, SCOPE, job_collections=SERVED)
    assert (result["status"], result["through"], result["days"]) == ("failed", "2026-10-01", 1)
    assert repo.cursor()["allocated_through"] == "2026-10-01"
    assert "cost allocation stopped: cost_allocations_refused" in caplog.text


def test_a_cursor_taken_meanwhile_stops_the_pass_without_moving_it():
    repo = Repo()
    repo.fail_put = Conflict("revision conflict")
    result = allocator().run(repo, SCOPE, job_collections=SERVED)
    assert (result["status"], result["days"]) == ("failed", 0) and repo.cursor() is None


def test_an_unpriced_bucket_location_holds_the_day(caplog):
    repo = Repo()
    with caplog.at_level(logging.WARNING):
        result = allocator(Monitoring(location="asia-south2")).run(repo, SCOPE, job_collections=SERVED)
    assert result["status"] == "failed" and repo.sent == [] and repo.cursor() is None
    assert "cost allocation stopped: cost_allocation_storage_location_unpriced" in caplog.text


def test_an_unreadable_cursor_is_logged_and_nothing_is_written(caplog):
    repo = Repo()
    repo.documents[(COLLECTION, CURSOR_KIND, cursor_id(SCOPE))] = {"revision": 1, "allocated_through": "soon"}
    with caplog.at_level(logging.WARNING):
        assert allocator().run(repo, SCOPE, job_collections=SERVED)["status"] == "failed"
    assert repo.sent == [] and "cost_allocation_cursor_unreadable" in caplog.text


def test_a_stop_ends_the_pass_between_days_and_a_closed_window_before_any_read():
    repo, stop = Repo(), threading.Event()
    repo.after_send = stop.set
    result = allocator().run(repo, SCOPE, job_collections=SERVED, stop=stop)
    assert (result["status"], result["through"]) == ("partial", "2026-10-01")
    monitoring = Monitoring()
    result = allocator(monitoring).run(Repo(), SCOPE, job_collections=SERVED, until=NOW)
    assert (result["status"], result["days"]) == ("partial", 0) and monitoring.calls == []


def test_a_repository_without_the_operations_is_left_alone():
    class Plain:
        def document(self, *args):
            raise AssertionError("read")

    assert allocator().run(Plain(), SCOPE)["status"] == "unsupported"


def test_the_drain_s_allocator_comes_from_its_job_and_bucket():
    assert CostAllocator.from_env({}) is None
    assert CostAllocator.from_env({"SPECIMEN_WORKER_JOB": "not-a-job"}) is None
    built = CostAllocator.from_env({"SPECIMEN_WORKER_JOB": "projects/specimen-digitization/locations/us-east4/jobs/"
                                                           "specimen-worker-insects",
                                    "SPECIMEN_GCS_BUCKET": "specimen-digitization.firebasestorage.app"})
    assert (built.job, built.bucket, built.monitoring.project) == (
        "specimen-worker-insects", "specimen-digitization.firebasestorage.app", "specimen-digitization")


# ---- in the drain ------------------------------------------------------------

class Allocating(CostingMember):
    """A SQLite lane repository with the sweep's and the allocation's operations."""

    def cost_allocation_inputs(self, scope, day_start, day_end, month_start, gap_seconds):
        self.order.append("allocate")
        return collections()

    def send_cost_allocations(self, scope, rows):
        return len(rows)


class SpyAllocation:
    def __init__(self, repository, error=None):
        self.repository, self.error, self.calls = repository, error, []

    def run(self, repository, scope, **kwargs):
        self.calls.append((scope, kwargs))
        self.repository.order.append("allocate")
        if self.error:
            raise self.error
        return {"status": "complete", "days": 1, "rows": 3, "through": "2026-10-04"}


def drain(repository, clock, allocation, *, deadline_seconds=3600):
    return DrainWorker(
        repository, Recording(repository, clock), WORKER,
        lambda user: [{"organization_id": ORG, "collection_id": COLLECTION, "role": "operator",
                       "can_view_sensitive": False}],
        execution_id="exec-a", clock=clock, sleep=clock.sleep, deadline_seconds=deadline_seconds,
        cost_allocation=allocation)


def test_each_drain_allocates_after_the_sweep_and_before_any_run_is_stepped(tmp_path):
    clock = Clock()
    repository = CostingMember(tmp_path / "lane.sqlite3", {})
    queued(repository, ident(77), minutes=5)
    allocation = SpyAllocation(repository)
    worker = drain(repository, clock, allocation)
    summary = worker.run()
    assert summary["status"] == "drained" and summary["processed"] == [ident(77)]
    assert repository.order[:3] == ["sweep", "allocate", "step"]
    [(scope, kwargs)] = allocation.calls
    assert scope == SCOPE and kwargs["until"] == worker.close_at and kwargs["job_collections"] == ((ORG, COLLECTION),)


def test_a_failing_allocation_never_stops_the_drain(tmp_path, caplog):
    clock = Clock()
    repository = CostingMember(tmp_path / "lane.sqlite3", {})
    queued(repository, ident(77), minutes=5)
    with caplog.at_level(logging.WARNING):
        summary = drain(repository, clock, SpyAllocation(repository, RuntimeError("PRIVATE-CANARY"))).run()
    assert summary["processed"] == [ident(77)]
    assert "cost allocation skipped: RuntimeError" in caplog.text and "PRIVATE-CANARY" not in caplog.text


def test_slow_monitoring_reads_end_at_the_budget_and_the_runs_are_stepped(tmp_path):
    clock = Clock()
    clock.now = NOW
    repository = Allocating(tmp_path / "lane.sqlite3", {})
    queued(repository, ident(77), minutes=5)

    class Slow:
        """Each page takes 30 s of the drain's clock."""

        def __init__(self):
            self.calls = 0

        def get(self, url, params, timeout):
            self.calls += 1
            clock.now += timedelta(seconds=30)

            class Response:
                status_code, text = 200, "{}"
            return Response()

    session = Slow()
    allocation = CostAllocator(MonitoringClient("specimen-digitization", session=session, clock=clock), job=JOB,
                               bucket=None, clock=clock)
    started = clock.now
    summary = drain(repository, clock, allocation).run()
    assert summary["processed"] == [ident(77)]
    # Two reads fit the 45-second budget; the third would start past it and is never sent.
    assert session.calls == 2 and clock.now - started <= timedelta(seconds=60 + 1)
    assert "allocate" not in repository.order  # no day's measures read, nothing written
    with pytest.raises(Missing):
        repository.document(SCOPE, CURSOR_KIND, cursor_id(SCOPE))


def test_the_window_s_close_bounds_the_allocation_before_its_own_budget(tmp_path):
    clock = Clock()
    clock.now = NOW
    repository = Allocating(tmp_path / "lane.sqlite3", {})
    monitoring = Monitoring()
    worker = drain(repository, clock, allocator(monitoring, clock=clock), deadline_seconds=610)
    worker.run()
    assert {stop_at for *_, stop_at in monitoring.calls} == {NOW + timedelta(seconds=10)}


def test_a_real_drain_writes_its_collection_s_days_and_its_cursor(tmp_path):
    clock = Clock()
    clock.now = NOW
    repository = Allocating(tmp_path / "lane.sqlite3", {})
    queued(repository, ident(77), minutes=5)
    summary = drain(repository, clock, allocator(clock=clock)).run()
    assert summary["processed"] == [ident(77)]
    assert repository.document(SCOPE, CURSOR_KIND, cursor_id(SCOPE))["allocated_through"] == "2026-10-04"
    assert repository.order.count("allocate") == 4 and repository.order[-1] == "step"


def test_a_drain_without_an_allocator_is_unchanged(tmp_path):
    clock = Clock()
    repository = NonSensitiveMember(tmp_path / "lane.sqlite3")
    queued(repository, ident(77), minutes=5)
    worker = DrainWorker(repository, ScriptedWorkflow(repository, clock), WORKER,
                         lambda user: [{"organization_id": ORG, "collection_id": COLLECTION, "role": "operator",
                                        "can_view_sensitive": False}],
                         execution_id="exec-a", clock=clock, sleep=clock.sleep)
    assert worker.run()["processed"] == [ident(77)] and worker._allocate_costs(SCOPE) is None
    with pytest.raises(Missing):
        repository.document(SCOPE, CURSOR_KIND, cursor_id(SCOPE))


def test_the_allocator_module_names_its_operations():
    assert cost_allocator.OPERATIONS == ("cost_allocation_inputs", "send_cost_allocations", "document", "put_document")
