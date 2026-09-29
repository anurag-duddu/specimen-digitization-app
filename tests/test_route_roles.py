"""A reader route is pinned and called only as an image reader.

The first-pass and harness routes share the gateway with the readers
(HARNESS.md section 5), so neither may stand in for a reader, and a reader no
longer registered blocks with a typed reason before any request.
"""

from types import SimpleNamespace

import pytest

from specimen_digitization.application import harness, production
from specimen_digitization.application.domain import Profile, Region, Run
from specimen_digitization.application.storage import LocalBlobs
from specimen_digitization.application.workflow import OperationalBlock
from specimen_digitization.model_gateway import (
    HUGGINGFACE_ROUTES,
    ModelGatewayConfigurationError,
)
from specimen_digitization.prompts import CollectionPromptInputs
from specimen_digitization.transcription import transcribe_label_image

STAGE_ROUTES = ["first-pass-glm", "harness-deepseek"]
# A reader retired or renamed after a run pinned it.
RETIRED_READER = "handwriting-retired"


@pytest.mark.parametrize("route", [*STAGE_ROUTES, RETIRED_READER])
def test_a_route_outside_the_reader_set_blocks_the_pin_step(tmp_path, route):
    # As on main, a reader is pinned from the initial reader set only; any other
    # route blocks the step with a typed reason, not a bare KeyError.
    run = Run(profile=Profile(routes=("handwriting-qwen", route)))

    with pytest.raises(OperationalBlock, match="^pinned_model_route_unavailable$"):
        production.ProductionAdapters(LocalBlobs(tmp_path)).pin_dependencies(run)


def test_a_reader_call_blocks_on_a_route_no_longer_registered(monkeypatch, tmp_path):
    # Not an unknown outcome: the call blocks before any request is sent.
    monkeypatch.setenv("SPECIMEN_APPROVED_INFERENCE", "true")
    monkeypatch.setenv("HF_TOKEN", "hf_test")
    run = Run(
        profile=Profile(),
        dependencies={"routes": {RETIRED_READER: {"model_id": "m", "provider": "p"}}},
    )
    region = Region(
        asset_id="asset-1", x=0, y=0, width=9, height=9, order=0, method="m", version="1"
    )

    with pytest.raises(OperationalBlock, match="^pinned_model_route_unavailable$"):
        production.ProductionAdapters(LocalBlobs(tmp_path))._transcribe_direct(
            SimpleNamespace(run=run), region, RETIRED_READER
        )


def test_extraction_blocks_on_a_reader_no_longer_registered(monkeypatch, tmp_path):
    def extract(*args):
        raise AssertionError("no extraction runs once a pinned reader is gone")

    monkeypatch.setenv("SPECIMEN_APPROVED_INFERENCE", "true")
    monkeypatch.setenv("HF_TOKEN", "hf_test")
    monkeypatch.setattr(harness, "extract_with_agent", extract)
    reader = HUGGINGFACE_ROUTES["handwriting-qwen"]
    run = Run(
        profile=Profile(routes=("handwriting-qwen", RETIRED_READER)),
        dependencies={
            "routes": {
                "handwriting-qwen": {
                    "model_id": reader.model_id,
                    "provider": reader.provider,
                },
                RETIRED_READER: {"model_id": "m", "provider": "p"},
            }
        },
    )

    with pytest.raises(
        OperationalBlock, match="^pinned_model_route_changed_requires_new_run$"
    ):
        production.ProductionAdapters(LocalBlobs(tmp_path))._extract_direct(
            SimpleNamespace(run=run)
        )


@pytest.mark.parametrize("route", STAGE_ROUTES)
def test_a_reader_call_refuses_a_route_that_is_not_an_image_reader(
    monkeypatch, tmp_path, route
):
    built = []

    class Gateway:
        def __init__(self, timeout_seconds=None):
            pass

        def route(self, route_id):
            return HUGGINGFACE_ROUTES[route_id]

        def model_for(self, route_id):
            built.append(route_id)
            raise AssertionError("no model is built for a refused route")

    monkeypatch.setenv("SPECIMEN_APPROVED_INFERENCE", "true")
    monkeypatch.setattr(production, "HuggingFaceModelGateway", Gateway)
    adapters = production.ProductionAdapters(LocalBlobs(tmp_path))
    selected = HUGGINGFACE_ROUTES[route]
    # Pinned exactly, with the reader prompt, so only the route's role refuses it.
    run = Run(
        profile=Profile(),
        dependencies={
            "routes": {
                route: {"model_id": selected.model_id, "provider": selected.provider}
            },
            "prompts": adapters.pin_dependencies(Run(profile=Profile()))["prompts"],
        },
    )
    region = Region(
        asset_id="asset-1", x=0, y=0, width=9, height=9, order=0, method="m", version="1"
    )

    with pytest.raises(OperationalBlock, match="^pinned_model_route_unavailable$"):
        adapters._transcribe_direct(SimpleNamespace(run=run), region, route)

    assert built == []


@pytest.mark.parametrize("route", STAGE_ROUTES)
def test_a_label_transcription_refuses_a_route_that_is_not_an_image_reader(route):
    # No caller today; the default gateway resolves the stage routes too.
    built = []

    class Gateway:
        def route(self, route_id):
            return HUGGINGFACE_ROUTES[route_id]

        def model_for(self, route_id):
            built.append(route_id)
            raise AssertionError("no model is built for a refused route")

    with pytest.raises(ModelGatewayConfigurationError):
        transcribe_label_image(
            Gateway(),
            route_id=route,
            image=b"PNG",
            media_type="image/png",
            prompt_inputs=CollectionPromptInputs(
                collection_profile_id="insects",
                collection_name="Insects",
                schema_version="1",
            ),
        )

    assert built == []
