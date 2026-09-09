"""A short reader deadline reaches both actual adapter layers and child cleanup."""

from types import SimpleNamespace

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from fastapi.testclient import TestClient

from specimen_digitization.application import model_runtime, production
from specimen_digitization.application.domain import ExecutionPolicy
from specimen_digitization.application.production import ProductionAdapters
from specimen_digitization.application.storage import LocalBlobs
from specimen_digitization.model_gateway import INITIAL_HUGGINGFACE_ROUTES
from test_dynamic_pilot_reservations import dynamic_cohort
from test_cohort_reading_barrier import segment_all


@pytest.mark.parametrize("reader_timeout", [30, 45, 60])
@pytest.mark.parametrize("route", list(INITIAL_HUGGINGFACE_ROUTES))
def test_actual_reader_gateway_agent_and_process_share_timeout(
    tmp_path, monkeypatch, reader_timeout, route
):
    c = dynamic_cohort(tmp_path, monkeypatch, reader_timeout=reader_timeout)
    segment_all(c)
    item = c.repo.get(c.launch.scope, c.launch.specimens[0].specimen_id)
    region = item.run.regions[0]
    observed = []

    class Gateway:
        def __init__(self, timeout_seconds=None):
            observed.append(("http", timeout_seconds))

        def route(self, route):
            return INITIAL_HUGGINGFACE_ROUTES[route]

        def model_for(self, route):
            def respond(messages, info):
                assert (info.model_settings or {}).get("max_tokens") == 4096
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
                    finish_reason="stop",
                )

            return FunctionModel(respond, model_name="local-reader-timeout")

    monkeypatch.setattr(production, "HuggingFaceModelGateway", Gateway)
    original_agent = production.run_agent_bounded

    def agent(*args, **kwargs):
        observed.append(("agent", kwargs["timeout_seconds"]))
        assert kwargs["usage_limits"].request_limit == 2
        return original_agent(*args, **kwargs)

    monkeypatch.setattr(production, "run_agent_bounded", agent)
    get_bounded = c.flow.blobs.get_bounded
    monkeypatch.setattr(
        c.flow.blobs,
        "get_bounded",
        lambda ref, limit: get_bounded(ref.split(":")[0], limit),
    )
    adapter = ProductionAdapters(c.flow.blobs)
    actual = adapter._transcribe_direct(item, region, route)
    assert actual.literal_text == "LOCAL FIXTURE"
    assert observed == [("http", reader_timeout / 2), ("agent", reader_timeout)]

    def isolate(target, payload, timeout, max_result_bytes, **kwargs):
        assert payload["profile"]["execution"]["external_timeout_seconds"] == 120
        assert (
            payload["profile"]["execution"]["reader_timeout_seconds"] == reader_timeout
        )
        assert timeout == reader_timeout
        import json

        return SimpleNamespace(
            status="completed",
            cleanup_complete=True,
            value=json.dumps(
                {
                    "status": "completed",
                    "value": {"observation": actual.model_dump(mode="json")},
                }
            ).encode(),
        )

    monkeypatch.setattr(model_runtime, "run_isolated", isolate)
    assert adapter.transcribe(item, region, route) == actual


def test_real_reader_child_timeout_kills_process_without_using_sam_limit(
    tmp_path, monkeypatch
):
    import os
    from specimen_digitization.application.api import create_app
    from test_application import HEADERS, PREFIX, TOKEN, intake
    from test_hardening_concurrency import repository
    from test_model_runtime import ModelAdapters

    class ShortReaders(ModelAdapters):
        def pin_dependencies(self, run):
            run.profile.execution = ExecutionPolicy.model_validate(
                dict(
                    run.profile.execution.model_dump(),
                    external_timeout_seconds=120,
                    reader_timeout_seconds=3,
                )
            )
            return ProductionAdapters.pin_dependencies(self, run)

    monkeypatch.setenv("SPECIMEN_APPROVED_INFERENCE", "true")
    monkeypatch.setenv("SPECIMEN_TEST_MODEL_SLOW_PHASE", "construction")
    monkeypatch.setenv("SPECIMEN_TEST_MODEL_SLOW_OPERATION", "transcribe")
    blobs = LocalBlobs(tmp_path / "blobs")
    app = create_app(
        mode="synthetic",
        repository=repository(tmp_path, "sqlite"),
        blobs=blobs,
        adapters=ShortReaders(blobs),
        token=TOKEN,
    )
    with TestClient(app) as http:
        row = intake(http)
        path = PREFIX + "/specimens/" + row["specimen_id"]
        result = http.get(path + "/workspace", headers=HEADERS).json()
        assert result["blocker"] == "external_outcome_unknown"
        assert result["run"]["profile"]["execution"]["external_timeout_seconds"] == 120
        assert result["run"]["usage"]["reserved_active_seconds"] == 3
        pid = int((tmp_path / "child-pid").read_text())
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
        assert not (tmp_path / "late-output").exists()
        assert not result["run"]["observations"]
        calls = result["run"]["usage"]["external_calls"]
        http.post(path + "/process", headers=HEADERS)
        after = http.get(path + "/workspace", headers=HEADERS).json()
        assert after["run"]["usage"]["external_calls"] == calls
