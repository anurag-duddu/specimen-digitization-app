"""A later request carries bounded feedback and fits its call's reservation.

docs/execution/golive/HARNESS.md section 15; the coordinator's G30 ruling.
"""

import json
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
)
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage, UsageLimits

from specimen_digitization.application import production
from specimen_digitization.application.domain import LookupStatus
from specimen_digitization.application.production import ProductionAdapters
from specimen_digitization.application.reliability import (
    RETRY_FEEDBACK_MAX_BYTES,
    AdapterFailure,
    CallBudget,
    run_agent_bounded,
)
from specimen_digitization.model_gateway import INITIAL_HUGGINGFACE_ROUTES
from specimen_digitization.provider_privacy import PrivateProviderModel
from test_cohort_reading_barrier import segment_all
from specimen_digitization.application.api import SYNTHETIC_COLLECTION, SYNTHETIC_ORG, SYNTHETIC_TEXT
from specimen_digitization.application.domain import Disposition, Principal, Run, Scope
from specimen_digitization.application.reliability import ReadingStopped
from specimen_digitization.application.storage import LocalBlobs, SQLiteRepository, digest
from specimen_digitization.application.workflow import SyntheticAdapters, Workflow
from test_application import client, intake
from test_dynamic_pilot_reservations import dynamic_cohort

LIMITS = UsageLimits(request_limit=2, total_tokens_limit=16000)
# The muse reader's prices, in micro-dollars per million tokens.
MUSE = {"input_micros_per_million": 300_000, "output_micros_per_million": 1_200_000}
VALID = {"text": "Exact label text", "lines": ["Exact label text"]}
USED = RequestUsage(input_tokens=2_000, output_tokens=500)


class Reading(BaseModel):
    text: str = Field(min_length=1)
    lines: list[str] = Field(min_length=1)


def reader(answers, usage=USED):
    """A reader answering in order, keeping what each request carried."""
    seen = []

    def respond(messages, info):
        seen.append(messages)
        tool = info.output_tools[0].name
        return ModelResponse(
            parts=[ToolCallPart(tool, answers[len(seen) - 1])], usage=usage
        )

    agent = Agent(PrivateProviderModel(FunctionModel(respond)), output_type=Reading)
    return agent, seen


def feedback(messages):
    [part] = [
        p
        for m in messages
        if isinstance(m, ModelRequest)
        for p in m.parts
        if isinstance(p, RetryPromptPart)
    ]
    return part.model_response()


def read(agent, budget=None):
    return run_agent_bounded(
        agent, "Read the label", timeout_seconds=5, usage_limits=LIMITS, budget=budget
    )


def test_many_wrong_typed_items_give_bounded_feedback():
    agent, seen = reader([{"text": "x", "lines": list(range(2_000))}, VALID])
    assert read(agent).output.text == "Exact label text"
    sent = feedback(seen[1])
    assert len(sent.encode()) <= RETRY_FEEDBACK_MAX_BYTES
    assert sent.count('"type": "string_type"') == 20
    assert '"input": 7' in sent  # A short input keeps its type.
    assert "1980 more errors not shown" in sent


def test_a_long_text_feedback_is_cut_to_fit():
    agent, seen = reader([VALID, VALID])

    @agent.output_validator
    def once(output: Reading) -> Reading:
        if len(seen) == 1:
            raise ModelRetry("reread line 1 " * 5_000)
        return output

    read(agent)
    sent = feedback(seen[1])
    assert len(sent.encode()) <= RETRY_FEEDBACK_MAX_BYTES
    assert sent.startswith("reread line 1")
    assert sent.endswith("…\n\nFix the errors and try again.")


def test_a_retry_that_would_cross_the_reservation_is_not_sent():
    # Spent: 2,000 in and 500 out, 1,200 at muse's prices. The retry could
    # take about 2,800 in and 4,096 out, about 5,800 more: 7,000 in all.
    agent, seen = reader([{"text": "", "lines": ["x"]}, VALID])
    with pytest.raises(UsageLimitExceeded, match="reservation"):
        read(agent, CallBudget(reserved_micros=6_000, **MUSE))
    assert len(seen) == 1


def test_a_retry_that_fits_the_reservation_is_sent():
    agent, seen = reader([{"text": "", "lines": ["x"]}, VALID])
    assert read(agent, CallBudget(reserved_micros=20_000, **MUSE)).output == Reading(
        **VALID
    )
    assert len(seen) == 2


def test_a_retry_after_an_answer_without_usage_is_not_sent():
    agent, seen = reader(
        [{"text": "", "lines": ["x"]}, VALID], usage=RequestUsage(output_tokens=500)
    )
    with pytest.raises(UsageLimitExceeded):
        read(agent, CallBudget(reserved_micros=20_000, **MUSE))
    assert len(seen) == 1


def test_without_a_budget_the_retry_goes_as_before():
    agent, seen = reader([{"text": "", "lines": ["x"]}, VALID])
    assert read(agent).output.text == "Exact label text"
    assert len(seen) == 2


def test_a_reading_stopped_by_its_limits_is_reported_as_stopped(tmp_path, monkeypatch):
    c = dynamic_cohort(tmp_path, monkeypatch)
    segment_all(c)
    item = c.repo.get(c.launch.scope, c.launch.specimens[0].specimen_id)
    region = item.run.regions[0]
    route = next(iter(INITIAL_HUGGINGFACE_ROUTES))

    class Gateway:
        def __init__(self, timeout_seconds=None):
            pass

        def route(self, route):
            return INITIAL_HUGGINGFACE_ROUTES[route]

        def model_for(self, route):
            def respond(messages, info):
                # A crop past the token limit: billed, then stopped.
                return ModelResponse(
                    parts=[
                        ToolCallPart(
                            info.output_tools[0].name,
                            {
                                "verbatim_text": "LOCAL FIXTURE",
                                "lines": ["LOCAL FIXTURE"],
                                "unreadable_spans": [],
                            },
                        )
                    ],
                    usage=RequestUsage(input_tokens=20_000, output_tokens=40),
                )

            return FunctionModel(respond, model_name="local-reader-limit")

    monkeypatch.setattr(production, "HuggingFaceModelGateway", Gateway)
    get_bounded = c.flow.blobs.get_bounded
    monkeypatch.setattr(
        c.flow.blobs,
        "get_bounded",
        lambda ref, limit: get_bounded(ref.split(":")[0], limit),
    )
    with pytest.raises(ReadingStopped) as stopped:
        ProductionAdapters(c.flow.blobs)._transcribe_direct(item, region, route)
    assert stopped.value.code == "model_usage_limit"


def test_the_model_child_reports_a_stopped_reading_as_stopped(tmp_path, monkeypatch):
    # Across the process boundary it is a known status, not a failure.
    from specimen_digitization.application import model_runtime

    body = model_runtime.stopped_result(ReadingStopped("model_usage_limit"))
    assert json.loads(body) == {"status": "stopped", "code": "model_usage_limit"}
    c = dynamic_cohort(tmp_path, monkeypatch)
    segment_all(c)
    item = c.repo.get(c.launch.scope, c.launch.specimens[0].specimen_id)
    isolated = SimpleNamespace(status="completed", cleanup_complete=True, value=body)
    monkeypatch.setattr(model_runtime, "run_isolated", lambda *args, **kwargs: isolated)
    route = next(iter(INITIAL_HUGGINGFACE_ROUTES))
    with pytest.raises(ReadingStopped) as stopped:
        model_runtime.invoke_model(
            ProductionAdapters(c.flow.blobs),
            item,
            "transcribe",
            region=item.run.regions[0],
            route=route,
        )
    assert stopped.value.code == "model_usage_limit"


class StoppingReader(SyntheticAdapters):
    """The second route's reading stops at its limits."""

    def transcribe(self, specimen, region, route):
        if route == specimen.run.profile.routes[1]:
            raise ReadingStopped("model_usage_limit")
        return super().transcribe(specimen, region, route)


def test_a_stopped_reading_completes_its_step_and_the_record_goes_to_review(tmp_path):
    row = intake(client(tmp_path))
    repo = SQLiteRepository(tmp_path / "state.sqlite3")
    scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
    principal = Principal(user_id="synthetic-reviewer", scope=scope, role="reviewer")
    specimen = repo.get(scope, row["specimen_id"])
    specimen.run = Run(profile=specimen.run.profile)
    repo.save(principal, specimen, specimen.version, "new-run", digest({"new": True}))
    adapters = StoppingReader(LocalBlobs(tmp_path / "blobs"), SYNTHETIC_TEXT)

    run = Workflow(repo, adapters.blobs, adapters).drain(principal, specimen.id).run

    stopped = [s for s in run.completed_steps if s.endswith(":" + run.profile.routes[1])]
    assert stopped and all(s.startswith("transcribe:") for s in stopped)
    assert {o.route_id for o in run.observations} == {run.profile.routes[0]}
    assert run.stage == "finalized" and run.disposition == Disposition.REVIEW
    assert any(r.startswith("independent_observations_missing:") for r in run.reasons)
