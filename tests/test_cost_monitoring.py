"""Cloud Monitoring's hourly readings for the cost meter (cost_monitoring; COST_METER.md, PR 3).

The fixtures under tests/fixtures/cost_monitoring are timeSeries.list response bodies in the
shape the Monitoring v3 reference documents (synthetic values, not read from the project).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal as D
from pathlib import Path

import pytest

from specimen_digitization.application.cost_monitoring import (
    MonitoringClient, MonitoringFailed, MonitoringUnavailable, OutOfTime, hour_of, hourly, read_usage,
)

FIXTURES = Path(__file__).parent / "fixtures" / "cost_monitoring"
UTC = timezone.utc
START, END = datetime(2026, 10, 1, 7, tzinfo=UTC), datetime(2026, 10, 20, 7, tzinfo=UTC)
BUCKET = "specimen-digitization.firebasestorage.app"
JOB = {"type": "cloud_run_job", "labels": {"job_name": "specimen-worker"}}


class Response:
    def __init__(self, status, body=None):
        self.status_code = status
        self.text = body if isinstance(body, str) else json.dumps(body if body is not None else {})


class Session:
    """Answers each read by the metric its filter names, page by page; records every call."""

    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def get(self, url, params, timeout):
        self.calls.append((url, dict(params), timeout))
        query = dict(params)
        for needle, answer in self.answers.items():
            if needle in query["filter"]:
                pages = answer if isinstance(answer, list) else [answer]
                token = query.get("pageToken")
                index = 0 if token is None else int(token.rsplit("-", 1)[1]) - 1
                return pages[index]
        raise AssertionError(f"unexpected filter {query['filter']}")


def fixture(name):
    return Response(200, (FIXTURES / name).read_text())


def answers(**overrides):
    found = {
        'resource.type="cloud_run_revision" AND resource.labels.service_name=one_of':
            [fixture("services_page_1.json"), fixture("services_page_2.json")],
        'resource.type="cloud_run_job"': fixture("jobs.json"),
        "run.googleapis.com/request_count": fixture("requests.json"),
        "logging.googleapis.com/user/specimen_api_requests_by_organization": fixture("organizations.json"),
        "storage.googleapis.com/storage/v2/total_bytes": Response(200, {}),
        "storage.googleapis.com/storage/total_bytes": fixture("storage_v1.json"),
    }
    found.update(overrides)
    return found


def hour(day, value):
    return datetime(2026, 10, day, value, tzinfo=UTC)


def test_every_reading_is_hourly_by_service_job_organization_and_bucket():
    session = Session(answers())
    usage = read_usage(MonitoringClient("specimen-digitization", session=session), START, END, bucket=BUCKET)
    # Two pages, two SAM 3 revisions summed in the 10:00 hour.
    assert usage.services["specimen-sam"] == {hour(19, 9): D(3600), hour(19, 10): D("1300.0")}
    assert usage.services["specimen-api"] == {hour(19, 9): D("41.3")}
    assert usage.jobs == {"specimen-worker": {hour(19, 9): D(2950)}, "specimen-intake": {hour(19, 9): D(60)}}
    assert usage.requests == {hour(19, 9): D(830)}  # every response code
    # The organization label, as a lowercase id; an empty label is no organization.
    assert usage.organizations == {"00000000-0000-4000-8000-0000000000a1": {hour(19, 9): D(600)},
                                   "00000000-0000-4000-8000-0000000000a2": {hour(19, 9): D(200)}}
    # v2 had no series, so v1 was read, from a day before the window; its location prices it.
    assert usage.storage == {hour(19, 9): D(5368709120), hour(18, 8): D(4294967296)}
    assert (usage.storage_location, usage.storage_metric) == ("us-east4", "storage.googleapis.com/storage/total_bytes")
    assert (usage.start, usage.end) == (START, END)
    first = session.calls[0]
    assert first[0] == "https://monitoring.googleapis.com/v3/projects/specimen-digitization/timeSeries"
    assert first[1]["interval.startTime"] == "2026-10-01T07:00:00Z" and first[1]["interval.endTime"] == "2026-10-20T07:00:00Z"
    assert (first[1]["aggregation.alignmentPeriod"], first[1]["aggregation.perSeriesAligner"]) == ("3600s", "ALIGN_SUM")
    assert first[2] == 10
    # No cross-series reducer or group-by field is sent: Python groups the series.
    assert not [call for call in session.calls if "aggregation.crossSeriesReducer" in call[1]]
    storage = [call for call in session.calls if "storage" in call[1]["filter"]]
    assert [call[1]["aggregation.perSeriesAligner"] for call in storage] == ["ALIGN_MEAN", "ALIGN_MEAN"]
    assert storage[0][1]["interval.startTime"] == "2026-09-30T07:00:00Z"
    assert f'resource.labels.bucket_name="{BUCKET}"' in storage[0][1]["filter"]


def test_a_second_page_is_asked_for_with_its_token_and_the_last_page_ends_the_read():
    session = Session(answers())
    client = MonitoringClient("specimen-digitization", session=session)
    series = client.series('metric.type="run.googleapis.com/container/billable_instance_time" AND '
                           'resource.type="cloud_run_revision" AND resource.labels.service_name=one_of("a")',
                           START, END, "ALIGN_SUM")
    assert len(series) == 3
    assert [call[1].get("pageToken") for call in session.calls] == [None, "services-page-2"]


def test_an_empty_answer_and_a_metric_not_found_are_no_series():
    session = Session(answers(**{
        "logging.googleapis.com/user/specimen_api_requests_by_organization": Response(404, {"error": {"code": 404}}),
        "storage.googleapis.com/storage/total_bytes": Response(200, {"unit": "By"}),
        'resource.type="cloud_run_job"': Response(200, {"timeSeries": []}),
    }))
    usage = read_usage(MonitoringClient("specimen-digitization", session=session), START, END, bucket=BUCKET)
    assert usage.organizations == {} and usage.jobs == {} and usage.storage == {}
    assert (usage.storage_location, usage.storage_metric) == (None, None)


@pytest.mark.parametrize("status", [401, 403])
def test_no_permission_to_read_monitoring_is_monitoring_unavailable(status):
    session = Session(answers(**{'resource.type="cloud_run_revision" AND resource.labels.service_name=one_of':
                                 Response(status, {"error": {"code": status, "message": "PRIVATE-CANARY"}})}))
    with pytest.raises(MonitoringUnavailable) as raised:
        read_usage(MonitoringClient("specimen-digitization", session=session), START, END, bucket=BUCKET)
    assert str(raised.value) == "cost_allocation_monitoring_unavailable" and len(session.calls) == 1


@pytest.mark.parametrize("answer,code", [
    (Response(500, {"error": {"message": "PRIVATE-CANARY"}}), "http_500"),
    (Response(429, {}), "http_429"),
    (Response(200, "not json PRIVATE-CANARY"), "cost_allocation_monitoring_invalid"),
    (Response(200, {"timeSeries": [{"resource": JOB, "points": [{"interval": {"endTime": "2026-10-19T10:00:00Z"},
                                                 "value": {"stringValue": "x"}}]}]}),
     "cost_allocation_monitoring_invalid"),
    (Response(200, {"timeSeries": [{"resource": JOB, "points": [{"interval": {"endTime": "2026-10-19T10:00:00Z"},
                                                 "value": {"doubleValue": -1}}]}]}),
     "cost_allocation_monitoring_invalid"),
])
def test_any_other_failure_is_named_by_a_code_and_never_by_the_response(answer, code):
    session = Session(answers(**{'resource.type="cloud_run_job"': answer}))
    with pytest.raises(MonitoringFailed) as raised:
        read_usage(MonitoringClient("specimen-digitization", session=session), START, END, bucket=BUCKET)
    assert str(raised.value) == code and "PRIVATE-CANARY" not in str(raised.value)


def test_a_transport_error_is_its_class_name():
    class Broken:
        def get(self, url, params, timeout):
            raise ConnectionError("PRIVATE-CANARY")

    with pytest.raises(MonitoringFailed, match="^ConnectionError$"):
        MonitoringClient("p", session=Broken()).series("f", START, END, "ALIGN_SUM")


def test_endless_pages_are_refused_and_a_spent_budget_stops_before_the_next_page():
    class Endless:
        calls = 0

        def get(self, url, params, timeout):
            Endless.calls += 1
            return Response(200, {"timeSeries": [], "nextPageToken": "again"})

    with pytest.raises(MonitoringFailed, match="too_many_pages"):
        MonitoringClient("p", session=Endless()).series("f", START, END, "ALIGN_SUM")
    assert Endless.calls == 20
    clock = iter([START, END])
    with pytest.raises(OutOfTime):
        MonitoringClient("p", session=Endless(), clock=lambda: next(clock)).series(
            "f", START, END, "ALIGN_SUM", stop_at=START)


def test_an_aligned_point_counts_in_the_hour_it_closes():
    assert hour_of(datetime(2026, 10, 19, 10, tzinfo=UTC)) == hour(19, 9)
    assert hour_of(datetime(2026, 10, 19, 10, 0, 0, 1, tzinfo=UTC)) == hour(19, 10)
    found = hourly([{"points": [{"interval": {"endTime": "2026-10-19T10:00:00.000000001Z"}, "value": {"int64Value": "2"}},
                                {"interval": {"endTime": "2026-10-19T10:00:00.000000000Z"}, "value": {"doubleValue": 1}}]}])
    assert found == {None: {hour(19, 10): D(2), hour(19, 9): D(1)}}


def test_windows_start_and_end_on_the_hour():
    with pytest.raises(ValueError):
        read_usage(MonitoringClient("p", session=Session({})), START.replace(minute=30), END, bucket=None)
