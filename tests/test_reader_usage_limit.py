"""A reader stopped by its token limits ends its reading, not the run.

Salvaged from #153. Readers still run as the ordinary `transcribe:` steps in
the isolated model child (research_harness/workflow_bridge.py), so these tests
drive that real child process with a local fixture model.
"""

import os

import pytest
from fastapi.testclient import TestClient

from specimen_digitization.application.api import SYNTHETIC_TEXT, create_app
from specimen_digitization.application.domain import Disposition
from specimen_digitization.application.production import ProductionAdapters
from specimen_digitization.application.storage import LocalBlobs
from specimen_digitization.application.workflow import SyntheticAdapters
from test_application import HEADERS, PREFIX, TOKEN, intake
from test_hardening_concurrency import repository


def stopping_reader_child(payload):
    """The model child, with one route's reader stopped by its token limits."""
    from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
    from pydantic_ai.models.function import FunctionModel
    from pydantic_ai.usage import RequestUsage

    from specimen_digitization.application import production
    from specimen_digitization.application.model_runtime import model_child
    from specimen_digitization.model_gateway import INITIAL_HUGGINGFACE_ROUTES

    stop = os.environ["SPECIMEN_TEST_READER_STOP"]
    stopped_route = payload["profile"]["routes"][
        int(os.environ["SPECIMEN_TEST_READER_STOP_ROUTE"])
    ]

    class Gateway:
        def __init__(self, timeout_seconds=None):
            pass

        def route(self, route):
            return INITIAL_HUGGINGFACE_ROUTES[route]

        def model_for(self, route):
            def respond(messages, info):
                if route == stopped_route and stop == "output_cap":
                    # Cut off at its output cap before it gave an answer.
                    return ModelResponse(
                        parts=[TextPart("SYNTHETIC FIXTURE CUT")],
                        usage=RequestUsage(input_tokens=1_000, output_tokens=4_096),
                        finish_reason="length",
                    )
                answer = {
                    "verbatim_text": SYNTHETIC_TEXT,
                    "lines": SYNTHETIC_TEXT.splitlines(),
                    "unreadable_spans": [],
                }
                # A crop past the reading's 16,000-token limit: billed, then stopped.
                billed = 20_000 if route == stopped_route else 1_000
                return ModelResponse(
                    parts=[ToolCallPart(info.output_tools[0].name, answer)],
                    usage=RequestUsage(input_tokens=billed, output_tokens=40),
                    finish_reason="stop",
                )

            return FunctionModel(respond, model_name="local-reader-usage-limit")

    production.HuggingFaceModelGateway = Gateway
    return model_child(payload)


class StoppingReaders(SyntheticAdapters):
    """Production readers in the real isolated child; the rest synthetic."""

    pin_dependencies = ProductionAdapters.pin_dependencies
    transcribe = ProductionAdapters.transcribe

    def __init__(self, blobs):
        super().__init__(blobs, SYNTHETIC_TEXT)
        self.classifier = None
        self.model_effect = stopping_reader_child


@pytest.mark.parametrize(
    ("stop", "stopped_index"), [("total_tokens", 1), ("output_cap", 0)]
)
def test_a_reader_stopped_by_its_token_limits_ends_its_reading_not_the_run(
    tmp_path, monkeypatch, stop, stopped_index
):
    monkeypatch.setenv("SPECIMEN_APPROVED_INFERENCE", "true")
    monkeypatch.setenv("SPECIMEN_TEST_READER_STOP", stop)
    monkeypatch.setenv("SPECIMEN_TEST_READER_STOP_ROUTE", str(stopped_index))
    blobs = LocalBlobs(tmp_path / "blobs")
    app = create_app(
        mode="synthetic",
        repository=repository(tmp_path, "sqlite"),
        blobs=blobs,
        adapters=StoppingReaders(blobs),
        token=TOKEN,
    )
    with TestClient(app) as http:
        row = intake(http)
        path = PREFIX + "/specimens/" + row["specimen_id"]
        work = http.get(path + "/workspace", headers=HEADERS).json()
    run = work["run"]
    routes = run["profile"]["routes"]
    [region] = [r["id"] for r in run["regions"]]
    stopped = f"transcribe:{region}:{routes[stopped_index]}"
    # Before #153's piece, the child's unmapped UsageLimitExceeded parked the
    # run here as external_outcome_unknown (model_runtime.py invoke_model).
    assert work["blocker"] is None, work["blocker"]
    assert stopped in run["completed_steps"] and run["attempts"][stopped] == 1
    assert [o["route_id"] for o in run["observations"]] == [
        routes[1 - stopped_index]
    ]
    assert run["stage"] == "finalized" and work["disposition"] == Disposition.REVIEW
    assert f"independent_observations_missing:{region}" in run["reasons"]
