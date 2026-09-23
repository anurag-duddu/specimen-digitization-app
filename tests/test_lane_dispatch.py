"""Starting the worker job from the API (docs/execution/golive/LANE.md, T1)."""

import pytest

from specimen_digitization.application.lane_dispatch import (
    CloudRunJobDispatcher,
    DispatchOutcome,
    dispatcher_from_value,
)

JOB = "projects/specimen-digitization/locations/us-east4/jobs/specimen-worker"


class Response:
    def __init__(self, status_code):
        self.status_code = status_code


class Session:
    def __init__(self, status_code=200, error=None):
        self.status_code = status_code
        self.error = error
        self.requests = []

    def post(self, url, **kwargs):
        self.requests.append((url, kwargs))
        if self.error:
            raise self.error
        return Response(self.status_code)


def test_start_runs_the_configured_job_without_overrides():
    session = Session()
    outcome = CloudRunJobDispatcher(JOB, session=session).start()
    assert outcome == DispatchOutcome(status="requested", reason=None)
    assert session.requests == [
        (
            "https://run.googleapis.com/v2/" + JOB + ":run",
            {"json": {}, "timeout": 10},
        )
    ]


@pytest.mark.parametrize("status_code", [403, 404, 429, 503])
def test_refused_start_is_reported_by_status_code_only(status_code):
    outcome = CloudRunJobDispatcher(JOB, session=Session(status_code)).start()
    assert outcome == DispatchOutcome(status="failed", reason=f"http_{status_code}")


def test_transport_failure_is_reported_by_error_class_only():
    session = Session(error=TimeoutError("token=secret-looking detail"))
    outcome = CloudRunJobDispatcher(JOB, session=session).start()
    assert outcome == DispatchOutcome(status="failed", reason="TimeoutError")


@pytest.mark.parametrize(
    "job",
    [
        "",
        "specimen-worker",
        "projects/specimen-digitization/locations/us-east4/jobs/",
        "projects/specimen-digitization/locations/us-east4/services/specimen-api",
        "projects/Specimen/locations/us-east4/jobs/specimen-worker",
        JOB + "/executions/one",
        JOB + ":run",
    ],
)
def test_invalid_job_names_are_refused(job):
    with pytest.raises(ValueError):
        CloudRunJobDispatcher(job, session=Session())


def test_configuration_value_is_optional():
    assert dispatcher_from_value(None) is None
    assert dispatcher_from_value("") is None
    dispatcher = dispatcher_from_value(JOB)
    assert isinstance(dispatcher, CloudRunJobDispatcher)
    assert dispatcher.job == JOB
    with pytest.raises(ValueError):
        dispatcher_from_value("not-a-job")
