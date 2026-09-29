"""A reader route is pinned and called only as an image reader.

The first-pass and harness routes share the gateway with the readers
(HARNESS.md section 5), so neither may stand in for a reader.
"""

from types import SimpleNamespace

import pytest

from specimen_digitization.application import production
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


@pytest.mark.parametrize("route", STAGE_ROUTES)
def test_a_stage_route_named_as_a_reader_is_not_pinned(tmp_path, route):
    # As on main: a reader is pinned from the initial reader set only.
    run = Run(profile=Profile(routes=("handwriting-qwen", route)))

    with pytest.raises(KeyError):
        production.ProductionAdapters(LocalBlobs(tmp_path)).pin_dependencies(run)


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
