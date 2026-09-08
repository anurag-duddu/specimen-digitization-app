"""Actual configured classifier factory, source retrieval and sink in a child process."""

import base64
import json
import time
from pathlib import Path

from fastapi.testclient import TestClient
from test_application import HEADERS, PREFIX, TOKEN, intake

from specimen_digitization.application.api import create_app, SYNTHETIC_TEXT
from specimen_digitization.application.classifier_runtime import ConfiguredClassifier
from specimen_digitization.application.hf_collection_classifier import (
    HFClassifierConfig,
)
from specimen_digitization.application.storage import LocalBlobs, SQLiteRepository
from specimen_digitization.application.workflow import SyntheticAdapters


def local_classifier_factory(payload):
    from pydantic_ai.models.function import FunctionModel
    from pydantic_ai.messages import ModelResponse, ToolCallPart
    from specimen_digitization import model_gateway
    from specimen_digitization.application.classifier_runtime import classifier_child

    class Gateway:
        def __init__(self, *, routes, timeout_seconds):
            self.routes = routes

        def route(self, route_id):
            return self.routes[route_id]

        def model_for(self, route_id):
            def respond(messages, info):
                return ModelResponse(
                    parts=[
                        ToolCallPart(
                            info.output_tools[0].name,
                            {
                                "candidates": [
                                    {
                                        "collection_id": payload["request"][
                                            "collection_ids"
                                        ][0],
                                        "score": 0.6,
                                        "reasons": ["synthetic_visible_structure"],
                                    }
                                ]
                            },
                        )
                    ],
                    provider_name="function",
                    finish_reason="tool_call",
                )

            return FunctionModel(
                respond, model_name=payload["config"]["expected_model_id"]
            )

    model_gateway.HuggingFaceModelGateway = Gateway
    # The source loader and provenance sink below are the actual production factory.
    with SQLiteRepository(
        Path(payload["storage"]["root"]).parent / "state.db"
    ).connect() as db:
        latest = json.loads(db.execute("SELECT payload FROM records").fetchone()[0])
        assert latest["run"]["blocker"] == "external_outcome_unknown"
        assert latest["run"]["lease_until"]
    return classifier_child(payload)


def slow_classifier_factory(payload):
    time.sleep(10)
    return local_classifier_factory(payload)


def exercise_configured_classifier(tmp_path):
    blobs = LocalBlobs(tmp_path / "blobs")
    repo = SQLiteRepository(tmp_path / "state.db")
    config = HFClassifierConfig(
        route_id="synthetic-classifier",
        expected_model_id="fixture/classifier",
        expected_provider="novita",
        prompt_text="Inspect the approved image and return only allowed collection candidates.",
        prompt_version="synthetic-prompt-v1",
        approved=True,
        total_deadline_seconds=5,
    )
    facade = ConfiguredClassifier(
        blobs, config, allow_sensitive=True, effect=local_classifier_factory
    )
    app = create_app(
        mode="synthetic",
        repository=repo,
        blobs=blobs,
        adapters=SyntheticAdapters(blobs, SYNTHETIC_TEXT),
        classifier=facade,
        token=TOKEN,
    )
    with TestClient(app) as http:
        row = intake(http)
        work = http.get(
            PREFIX + "/specimens/" + row["specimen_id"] + "/workspace", headers=HEADERS
        ).json()
        classification = work["run"]["classification"]
        assert classification.get("status") == "completed", (
            work["blocker"],
            work["run"]["reasons"],
            classification,
        )
        assert classification["calibration_version"] is None
        assert classification["model_version"] == config.expected_model_id
        assert work["run"]["dependencies"]["classifier"]["config"] == config.model_dump(
            mode="json"
        )
        envelope = json.loads(blobs.get(classification["raw_response_ref"]))
        original_response = json.loads(
            base64.b64decode(envelope["raw_response_base64"])
        )
        assert original_response["model_name"] == config.expected_model_id
        assert envelope["request"]["input_sha256"] == work["asset"]["sha256"]
        assert envelope["structured_output"]["candidates"][0]["score"] == 0.6
        assert work["disposition"] == "needs_human_review"
        return {"workspace": work, "provenance": envelope}


def test_classifier_factory_timeout_keeps_durable_unknown_without_automatic_retry(
    tmp_path,
):
    blobs = LocalBlobs(tmp_path / "blobs")
    repo = SQLiteRepository(tmp_path / "state.db")
    config = HFClassifierConfig(
        route_id="synthetic-classifier",
        expected_model_id="fixture/classifier",
        expected_provider="novita",
        prompt_text="Inspect",
        prompt_version="1",
        approved=True,
        total_deadline_seconds=2,
    )
    facade = ConfiguredClassifier(
        blobs, config, allow_sensitive=True, effect=slow_classifier_factory
    )
    app = create_app(
        mode="synthetic",
        repository=repo,
        blobs=blobs,
        adapters=SyntheticAdapters(blobs, SYNTHETIC_TEXT),
        classifier=facade,
        token=TOKEN,
    )
    with TestClient(app) as http:
        row = intake(http)
        path = PREFIX + "/specimens/" + row["specimen_id"]
        work = http.get(path + "/workspace", headers=HEADERS).json()
        assert work["blocker"] == "external_outcome_unknown"
        assert work["run"]["lease_until"] and work["disposition"] is None
        calls = work["run"]["usage"]["external_calls"]
        http.post(path + "/process", headers=HEADERS)
        after = http.get(path + "/workspace", headers=HEADERS).json()
        assert after["run"]["usage"]["external_calls"] == calls


def test_http_configured_classifier_pins_scope_source_route_and_provenance(tmp_path):
    exercise_configured_classifier(tmp_path)
