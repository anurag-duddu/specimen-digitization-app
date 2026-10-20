"""The cost meter's backfill and repair sweep (docs/execution/golive/COST_METER.md)."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5

import pytest

from specimen_digitization.application import cost_sweep
from specimen_digitization.application.cost_ledger import call_rows
from specimen_digitization.application.cost_sweep import CURSOR_KIND, EPOCH, OVERLAP, cursor_id, sweep
from specimen_digitization.application.domain import Scope
from specimen_digitization.application.lane_costs import record_model_usage, record_segmentation
from specimen_digitization.application.storage import Conflict, Missing
from specimen_digitization.application.workflow import OperationalBlock

from test_lane_costs import QWEN, priced_run
from test_lane_drain import COLLECTION, ORG, Clock, NonSensitiveMember, ScriptedWorkflow, queued, worker

SCOPE = Scope(organization_id=ORG, collection_id=COLLECTION)
START = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
INSTANCE = {"first": False, "idle_seconds": 4.0, "request_seconds": 12.5}


def ident(n):
    return f"00000000-0000-4000-8000-{n:012x}"


def calls(count=1):
    run = priced_run()
    for _ in range(count):
        record_model_usage(run, QWEN, "handwriting-qwen", input_tokens=1, output_tokens=1)
    record_segmentation(run, "segment", seconds=1, instance=INSTANCE)
    return run.paid_calls


class Ticking:
    """A clock that moves `step` seconds each time it is read."""

    def __init__(self, step=0.0, now=START):
        self.now, self.step = now, timedelta(seconds=step)

    def __call__(self):
        value = self.now
        self.now += self.step
        return value


class Repo:
    """The repository surface the sweep uses, with ListRunPaidCallsV1's paging rules."""

    def __init__(self, specimens):
        # id -> {"updated_at": datetime, "runs": {run_id: paid_calls}}
        self.specimens = specimens
        self.documents = {}
        self.sent = []
        self.pages = []
        self.refuse = set()
        self.fail_page = None
        self.fail_put = None

    def document(self, scope, kind, key):
        if (kind, key) not in self.documents:
            raise Missing(key)
        return dict(self.documents[(kind, key)])

    def put_document(self, scope, kind, key, payload, expected):
        if self.fail_put:
            raise self.fail_put
        current = self.documents.get((kind, key), {}).get("revision", 0)
        if current != expected:
            raise Conflict("revision conflict")
        self.documents[(kind, key)] = dict(payload, revision=expected + 1)
        return self.documents[(kind, key)]

    def run_paid_calls_page(self, scope, after_id, since, limit):
        self.pages.append((after_id, since))
        if self.fail_page is not None and len(self.pages) >= self.fail_page:
            raise OperationalBlock("sql_connect_unavailable_or_connector_not_published")
        since = datetime.fromisoformat(since)
        page = [key for key, value in sorted(self.specimens.items())
                if key > after_id and value["updated_at"] >= since][:limit]
        items = [{"specimen_id": key, "run_id": run_id, "revision": 1, "paid_calls": paid}
                 for key in page for run_id, paid in sorted(self.specimens[key]["runs"].items())]
        return {"items": items, "specimens": len(page), "last_id": page[-1] if page else None}

    def send_cost_rows(self, scope, specimen_id, rows):
        if specimen_id in self.refuse:
            raise Conflict("SQL Connect transaction rejected; reload current revision and membership")
        self.sent.append((specimen_id, rows))
        return len(rows)

    def cursor(self):
        return self.documents.get((CURSOR_KIND, cursor_id(SCOPE)))

    def sent_ids(self):
        return [specimen_id for specimen_id, _ in self.sent]


def collection(count, *, updated=START - timedelta(days=30)):
    return {ident(n): {"updated_at": updated, "runs": {ident(1000 + n): calls()}} for n in range(1, count + 1)}


def test_the_cursor_document_is_the_worker_s_own_per_collection():
    assert cursor_id(SCOPE) == str(uuid5(NAMESPACE_URL, f"cost-meter-sweep:{ORG}/{COLLECTION}"))
    assert cursor_id(Scope(organization_id=ORG, collection_id=ident(99))) != cursor_id(SCOPE)
    assert CURSOR_KIND == "worker_cursor"


def test_the_first_sweep_records_every_run_and_sets_the_watermark():
    repo = Repo(collection(23))
    first = ident(5)
    repo.specimens[first]["runs"][ident(2000)] = calls(2)  # A second, earlier run.
    result = sweep(repo, SCOPE, clock=Ticking(), page_size=10)
    assert result == {"status": "complete", "pages": 3, "specimens": 23, "rows": 23 * 2 + 3, "skipped": 0}
    assert repo.pages == [("", EPOCH), (ident(10), EPOCH), (ident(20), EPOCH)]
    assert repo.sent_ids() == [ident(n) for n in range(1, 24)]
    [(_, rows)] = [entry for entry in repo.sent if entry[0] == first]
    assert {row["run_id"] for row in rows} == {ident(1005), ident(2000)}
    assert rows == (call_rows(ORG, COLLECTION, first, ident(1005), repo.specimens[first]["runs"][ident(1005)])
                    + call_rows(ORG, COLLECTION, first, ident(2000), repo.specimens[first]["runs"][ident(2000)]))
    assert repo.cursor() == {"sensitive": False, "swept_since": (START - OVERLAP).isoformat(),
                             "after_id": "", "pass_started_at": None, "revision": 1}


def test_a_later_sweep_reads_only_records_saved_since_the_watermark_less_the_overlap():
    repo = Repo(collection(5))
    sweep(repo, SCOPE, clock=Ticking())
    later = START + timedelta(hours=6)
    repo.specimens[ident(2)]["updated_at"] = START - timedelta(minutes=30)  # Inside the overlap.
    repo.specimens[ident(4)]["updated_at"] = later - timedelta(minutes=1)
    repo.sent, repo.pages = [], []
    result = sweep(repo, SCOPE, clock=Ticking(now=later))
    assert repo.pages == [("", (START - OVERLAP).isoformat())]
    assert repo.sent_ids() == [ident(2), ident(4)]
    assert result["status"] == "complete"
    assert repo.cursor()["swept_since"] == (later - OVERLAP).isoformat()
    assert repo.cursor()["revision"] == 2


def test_the_time_budget_stops_the_sweep_and_the_next_one_resumes_the_same_pass():
    repo = Repo(collection(30))
    # Each read of the clock is 4 s later: a 60 s budget ends inside the second page.
    result = sweep(repo, SCOPE, clock=Ticking(step=4), page_size=10, seconds=60)
    assert result["status"] == "partial" and result["pages"] == 1
    assert repo.cursor() == {"sensitive": False, "swept_since": EPOCH, "after_id": ident(10),
                             "pass_started_at": START.isoformat(), "revision": 1}
    sent_first = repo.sent_ids()
    assert sent_first[:10] == [ident(n) for n in range(1, 11)]
    # Resumed by a later execution: the same pass, from the last page done in full.
    resumed_at = START + timedelta(minutes=10)
    result = sweep(repo, SCOPE, clock=Ticking(now=resumed_at), page_size=10)
    assert result["status"] == "complete"
    # The first sweep read two pages (the second cut short); this one starts at that second page.
    assert repo.pages[2:] == [(ident(10), EPOCH), (ident(20), EPOCH), (ident(30), EPOCH)]
    assert set(repo.sent_ids()) == {ident(n) for n in range(1, 31)}
    # The watermark is the pass's own start, not the resumed execution's.
    assert repo.cursor()["swept_since"] == (START - OVERLAP).isoformat()
    assert (repo.cursor()["after_id"], repo.cursor()["pass_started_at"]) == ("", None)


def test_the_drain_window_and_a_stop_end_the_sweep_before_its_budget():
    repo = Repo(collection(30))
    result = sweep(repo, SCOPE, clock=Ticking(step=1), page_size=10, until=START + timedelta(seconds=5))
    assert result["status"] == "partial" and result["specimens"] < 10 and result["pages"] == 0
    assert repo.cursor() is None, "no page was done in full, so the watermark stays"
    stop = threading.Event()
    stop.set()
    assert sweep(repo, SCOPE, clock=Ticking(), stop=stop)["pages"] == 0


def test_the_page_count_bounds_one_sweep():
    repo = Repo(collection(30))
    result = sweep(repo, SCOPE, clock=Ticking(), page_size=10, pages=2)
    assert (result["status"], result["pages"], result["specimens"]) == ("partial", 2, 20)
    assert repo.cursor()["after_id"] == ident(20)


def test_a_failure_is_logged_never_raised_and_keeps_the_pages_done(caplog):
    repo = Repo(collection(30))
    repo.fail_page = 2
    with caplog.at_level(logging.WARNING):
        result = sweep(repo, SCOPE, clock=Ticking(), page_size=10)
    assert result["status"] == "failed" and result["pages"] == 1
    assert repo.cursor()["after_id"] == ident(10)
    assert "cost sweep stopped: OperationalBlock" in caplog.text
    # The next sweep starts at the page that failed.
    repo.fail_page = None
    assert sweep(repo, SCOPE, clock=Ticking(), page_size=10)["status"] == "complete"
    assert repo.pages[2] == (ident(10), EPOCH)


def test_a_refused_record_or_an_unreadable_run_is_passed_over(caplog):
    repo = Repo(collection(4))
    repo.refuse = {ident(2)}
    bad = calls()
    bad[0] = dict(bad[0], kind="allocation")
    repo.specimens[ident(3)]["runs"][ident(3000)] = bad
    with caplog.at_level(logging.WARNING):
        result = sweep(repo, SCOPE, clock=Ticking())
    assert result == {"status": "complete", "pages": 1, "specimens": 4, "rows": 6, "skipped": 2}
    assert repo.sent_ids() == [ident(1), ident(3), ident(4)]
    # The readable run of the record with an unreadable one is still sent.
    assert {row["run_id"] for row in dict(repo.sent)[ident(3)]} == {ident(1003)}
    assert "cost sweep skipped a record: Conflict" in caplog.text
    assert "cost sweep skipped a run: cost_kind_invalid" in caplog.text


def test_a_cursor_written_meanwhile_fails_the_save_but_not_the_caller(caplog):
    repo = Repo(collection(3))
    repo.fail_put = Conflict("revision conflict")
    with caplog.at_level(logging.WARNING):
        assert sweep(repo, SCOPE, clock=Ticking())["status"] == "failed"
    assert "cost sweep stopped: Conflict" in caplog.text


def test_an_unreadable_cursor_starts_a_pass_over_everything():
    repo = Repo(collection(3))
    repo.documents[(CURSOR_KIND, cursor_id(SCOPE))] = {"revision": 4, "swept_since": "not a time", "after_id": 7}
    assert sweep(repo, SCOPE, clock=Ticking())["status"] == "complete"
    assert repo.pages == [("", EPOCH)]
    assert repo.cursor()["revision"] == 5


def test_a_repository_without_the_cost_operations_is_left_alone():
    class Plain:
        def document(self, *args):
            raise AssertionError("read")

    assert sweep(Plain(), SCOPE, clock=Ticking())["status"] == "unsupported"


# ---- in the drain ----------------------------------------------------------

class CostingMember(NonSensitiveMember):
    """A SQLite lane repository with the sweep's two cost operations."""

    def __init__(self, path, specimens):
        super().__init__(path)
        self.fake = Repo(specimens)
        self.order = []

    def run_paid_calls_page(self, scope, after_id, since, limit):
        self.order.append("sweep")
        return self.fake.run_paid_calls_page(scope, after_id, since, limit)

    def send_cost_rows(self, scope, specimen_id, rows):
        return self.fake.send_cost_rows(scope, specimen_id, rows)


class Recording(ScriptedWorkflow):
    def step(self, principal, key):
        self.repository.order.append("step")
        return super().step(principal, key)


def test_each_collection_s_drain_sweeps_its_costs_before_any_run_is_stepped(tmp_path):
    clock = Clock()
    repository = CostingMember(tmp_path / "lane.sqlite3", collection(2))
    queued(repository, ident(77), minutes=5)
    summary = worker(repository, Recording(repository, clock), clock).run()
    assert summary["status"] == "drained" and summary["processed"] == [ident(77)]
    assert repository.order[0] == "sweep" and "step" in repository.order
    assert repository.fake.sent_ids() == [ident(1), ident(2)]
    # The watermark is the worker's own document, marked not sensitive.
    stored = repository.document(SCOPE, CURSOR_KIND, cursor_id(SCOPE))
    assert stored["sensitive"] is False and stored["after_id"] == ""


def test_a_failing_sweep_never_stops_the_drain(tmp_path, caplog):
    clock = Clock()
    repository = CostingMember(tmp_path / "lane.sqlite3", collection(2))
    repository.fake.fail_page = 1
    queued(repository, ident(77), minutes=5)
    with caplog.at_level(logging.WARNING):
        summary = worker(repository, Recording(repository, clock), clock).run()
    assert summary["status"] == "drained" and summary["processed"] == [ident(77)]
    assert "cost sweep stopped: OperationalBlock" in caplog.text


def test_an_unexpected_sweep_error_is_logged_and_the_drain_goes_on(tmp_path, caplog, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("PRIVATE-CANARY")

    monkeypatch.setattr(cost_sweep, "sweep", broken)
    clock = Clock()
    repository = CostingMember(tmp_path / "lane.sqlite3", collection(1))
    queued(repository, ident(77), minutes=5)
    with caplog.at_level(logging.WARNING):
        summary = worker(repository, Recording(repository, clock), clock).run()
    assert summary["processed"] == [ident(77)]
    assert "cost sweep skipped: RuntimeError" in caplog.text and "PRIVATE-CANARY" not in caplog.text


@pytest.mark.parametrize("repository_class", [NonSensitiveMember])
def test_a_drain_without_the_cost_operations_is_unchanged(tmp_path, repository_class):
    clock = Clock()
    repository = repository_class(tmp_path / "lane.sqlite3")
    queued(repository, ident(77), minutes=5)
    summary = worker(repository, ScriptedWorkflow(repository, clock), clock).run()
    assert summary["processed"] == [ident(77)]
    with pytest.raises(Missing):
        repository.document(SCOPE, CURSOR_KIND, cursor_id(SCOPE))
