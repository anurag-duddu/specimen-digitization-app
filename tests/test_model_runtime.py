"""Real subprocess model construction, isolated readings, sink and recovery."""

import json
import os
import time
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_application import HEADERS, PREFIX, SYNTHETIC_ORG, TOKEN, intake
from test_hardening_concurrency import repository

from specimen_digitization.application.api import SYNTHETIC_TEXT, create_app
from specimen_digitization.application.production import (
    ProductionAdapters,
    actor_uid,
    sql_emulator_host,
)
from specimen_digitization.application.storage import LocalBlobs
from specimen_digitization.application.workflow import SyntheticAdapters


def local_model_factory(payload):
    from pydantic_ai.messages import ModelResponse, ToolCallPart
    from pydantic_ai.models.function import FunctionModel

    from specimen_digitization.application import production
    from specimen_digitization.application.model_runtime import model_child
    from specimen_digitization.model_gateway import INITIAL_HUGGINGFACE_ROUTES

    root = Path(payload["storage"]["root"]).parent
    phase = os.getenv("SPECIMEN_TEST_MODEL_SLOW_PHASE")

    def pause(stage):
        if phase == stage and payload["operation"] == os.getenv(
            "SPECIMEN_TEST_MODEL_SLOW_OPERATION", "transcribe"
        ):
            (root / "child-pid").write_text(str(os.getpid()))
            time.sleep(10)
            (root / "late-output").write_text(stage)

    assert "observations" not in payload and "previous_runs" not in payload
    assert "PEER-CANARY" not in json.dumps(payload)
    if payload["operation"] == "transcribe":
        assert set(payload) == {
            "operation",
            "storage",
            "asset",
            "profile",
            "dependencies",
            "region",
            "route",
        }
    if os.getenv("SPECIMEN_TEST_MODEL_CHECK_INTENT") == "true":
        repo = repository(root, os.environ["SPECIMEN_TEST_MODEL_REPO"])
        token = actor_uid.set("synthetic-reviewer")
        try:
            if os.environ["SPECIMEN_TEST_MODEL_REPO"] == "sqlite":
                with repo.connect() as db:
                    snapshot = json.loads(
                        db.execute("SELECT payload FROM records").fetchone()[0]
                    )
            else:
                from specimen_digitization.application.domain import Scope

                scope = Scope(
                    organization_id=SYNTHETIC_ORG,
                    collection_id=os.environ["SPECIMEN_TEST_MODEL_COLLECTION"],
                )
                row = repo.list(scope)[0]
                snapshot = row.model_dump(mode="json")
            assert snapshot["run"]["blocker"] == "external_outcome_unknown"
            assert snapshot["run"]["lease_until"]
        finally:
            actor_uid.reset(token)

    class Gateway:
        def __init__(self, timeout_seconds=None):
            pause("construction")

        def route(self, route):
            return INITIAL_HUGGINGFACE_ROUTES[route]

        def model_for(self, route):
            def respond(messages, info):
                pause("model")
                assert "PEER-CANARY" not in str(messages)
                assert (info.model_settings or {}).get("max_tokens") == 4096
                output = (
                    {
                        "verbatim_text": SYNTHETIC_TEXT,
                        "lines": SYNTHETIC_TEXT.splitlines(),
                        "unreadable_spans": [],
                    }
                    if payload["operation"] == "transcribe"
                    else {
                        "candidates": [
                            {
                                "field_key": "country",
                                "region_id": payload["transcripts"][0]["region_id"],
                                "literal": "United States",
                                "source_excerpt": "United States",
                            }
                        ],
                        "unresolved": [],
                    }
                )
                return ModelResponse(
                    parts=[ToolCallPart(info.output_tools[0].name, output)],
                    finish_reason="stop",
                )

            return FunctionModel(respond, model_name="synthetic-model-runtime")

    production.HuggingFaceModelGateway = Gateway
    original_put = LocalBlobs.put

    def put(self, data):
        pause("sink")
        return original_put(self, data)

    LocalBlobs.put = put
    return model_child(payload)


class ModelAdapters(SyntheticAdapters):
    def pin_dependencies(self, run):
        if os.getenv("SPECIMEN_TEST_MODEL_SLOW_PHASE"):
            run.profile.execution.external_timeout_seconds = 3
        return ProductionAdapters.pin_dependencies(self, run)

    transcribe = ProductionAdapters.transcribe
    extract = ProductionAdapters.extract

    def __init__(self, blobs):
        super().__init__(blobs, SYNTHETIC_TEXT)
        self.classifier = None
        self.model_effect = local_model_factory


def setup_scope(kind, monkeypatch):
    import test_application

    from specimen_digitization.application import api

    if kind == "sql":
        if os.getenv("SPECIMEN_TEST_SQL_EMULATOR") != "true":
            pytest.skip("Requires explicitly enabled isolated local SQL emulator")
        import httpx

        collection = str(uuid4())
        query = f'''mutation @transaction {{ collection_insert(data:{{organizationId:"{SYNTHETIC_ORG}",id:"{collection}",name:"Model boundary fixture"}}) collectionMember_insert(data:{{organizationId:"{SYNTHETIC_ORG}",collectionId:"{collection}",uid:"synthetic-reviewer",active:true,role:"reviewer",canViewSensitive:true}}) }}'''
        result = httpx.post(
            f"http://{sql_emulator_host()}/v1/projects/demo-specimen-data/locations/us-east4/services/specimen-digitization-service:executeGraphql",
            json={"query": query},
        ).json()
        assert not result.get("errors") and not result.get("code")
        monkeypatch.setattr(test_application, "SYNTHETIC_COLLECTION", collection)
        monkeypatch.setattr(api, "SYNTHETIC_COLLECTION", collection)
    else:
        collection = test_application.SYNTHETIC_COLLECTION
    return collection


@pytest.mark.parametrize("kind", ["sqlite", "sql"])
def test_hard_model_factories_independent_observations_extraction_and_restart(
    tmp_path, monkeypatch, kind
):
    collection = setup_scope(kind, monkeypatch)
    monkeypatch.setenv("SPECIMEN_APPROVED_INFERENCE", "true")
    monkeypatch.setenv("SPECIMEN_TEST_MODEL_CHECK_INTENT", "true")
    monkeypatch.setenv("SPECIMEN_TEST_MODEL_REPO", kind)
    monkeypatch.setenv("SPECIMEN_TEST_MODEL_COLLECTION", collection)
    blobs = LocalBlobs(tmp_path / "blobs")

    def make_app():
        return create_app(
            mode="synthetic",
            repository=repository(tmp_path, kind),
            blobs=blobs,
            adapters=ModelAdapters(blobs),
            token=TOKEN,
        )

    with TestClient(make_app()) as http:
        row = intake(http)
        path = PREFIX + "/specimens/" + row["specimen_id"] + "/workspace"
        work = http.get(path, headers=HEADERS).json()
        assert work["blocker"] is None, work["blocker"]
        observations = work["run"]["observations"]
        assert len(observations) == 2
        assert len({o["id"] for o in observations}) == 2
        assert len({o["route_id"] for o in observations}) == 2
        for observation in observations:
            assert observation["finish_state"] == "stop"
            assert observation["input_crop_ref"] and observation["latency_seconds"] >= 0
            assert (
                json.loads(blobs.get(observation["raw_ref"]))[-1]["model_name"]
                == "synthetic-model-runtime"
            )
        assert any(
            e["source"] == "bounded_extraction_v1" for e in work["run"]["evidence"]
        )
    with TestClient(make_app()) as restarted:
        after = restarted.get(path, headers=HEADERS).json()
        assert after["run"] == work["run"]


@pytest.mark.parametrize("operation", ["transcribe", "extract"])
@pytest.mark.parametrize("phase", ["construction", "model", "sink"])
def test_whole_model_deadline_kills_child_preserves_unknown_and_no_replay(
    tmp_path, monkeypatch, phase, operation
):
    monkeypatch.setenv("SPECIMEN_APPROVED_INFERENCE", "true")
    monkeypatch.setenv("SPECIMEN_TEST_MODEL_SLOW_PHASE", phase)
    monkeypatch.setenv("SPECIMEN_TEST_MODEL_SLOW_OPERATION", operation)
    blobs = LocalBlobs(tmp_path / "blobs")
    app = create_app(
        mode="synthetic",
        repository=repository(tmp_path, "sqlite"),
        blobs=blobs,
        adapters=ModelAdapters(blobs),
        token=TOKEN,
    )
    with TestClient(app) as http:
        row = intake(http)
        path = PREFIX + "/specimens/" + row["specimen_id"]
        work = http.get(path + "/workspace", headers=HEADERS).json()
        assert work["blocker"] == "external_outcome_unknown"
        assert work["run"]["lease_until"] and work["disposition"] is None
        pid = int((tmp_path / "child-pid").read_text())
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
        calls = work["run"]["usage"]["external_calls"]
        http.post(path + "/process", headers=HEADERS)
        after = http.get(path + "/workspace", headers=HEADERS).json()
        assert after["run"]["usage"]["external_calls"] == calls
        assert not (tmp_path / "late-output").exists()
        assert len(after["run"]["observations"]) == (
            0 if operation == "transcribe" else 2
        )
        assert not any(
            e["source"] == "bounded_extraction_v1" for e in after["run"]["evidence"]
        )
