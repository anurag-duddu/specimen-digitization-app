"""A call that sends a crop reserves its worst case (docs/execution/golive/LANE.md, T2b).

PLAN 4.3 and the coordinator's ruling of 2026-09-24: each request reserves the
lesser of (a) the route's context length at the input price plus the answer's
cap, and (b), where the route documents its image-token rule, the crop's tokens
plus the prompt and the cap. A reading makes two requests; 20,000 is the floor.
"""

from types import SimpleNamespace

import pytest

from specimen_digitization.application.api import SYNTHETIC_COLLECTION
from specimen_digitization.application.collection_profiles import (
    ProgramAllowance,
    published_registry,
)
from specimen_digitization.application.domain import Profile, Region, Run
from specimen_digitization.application.lane import queue
from specimen_digitization.application.lane_reservations import (
    call_micros,
    image_tokens,
    reading_reservation,
)
from specimen_digitization.application.production import ProductionAdapters

from test_lane_costs import PRICES, lab, priced_registry
from test_lane_profile import USER
from test_lane_trigger import specimen_with

MUSE = {"input_micros_per_million": 300_000, "output_micros_per_million": 1_200_000}


def with_models(registry, **changes):
    """The registry's price list with some routes' entries changed."""
    profiles = []
    for profile in registry.profiles:
        prices = profile.processing and profile.processing.price_list
        if prices:
            models = {
                route: price.model_copy(update=changes.get(route, {}))
                for route, price in prices.models.items()
            }
            processing = profile.processing.model_copy(
                update={"price_list": prices.model_copy(update={"models": models})}
            )
            profile = profile.model_copy(update={"processing": processing})
        profiles.append(profile)
    return registry.model_copy(update={"profiles": tuple(profiles)})


def reading(width, height, registry=None):
    specimen = specimen_with(Run(profile=Profile(synthetic=False)))
    queue(specimen, registry or published_registry({SYNTHETIC_COLLECTION: "insects"}), USER)
    run = specimen.run
    run.dependencies = ProductionAdapters.pin_dependencies(
        SimpleNamespace(classifier=None), run
    )
    region = Region(
        asset_id=specimen.asset.id, x=0, y=0, width=width, height=height,
        order=0, method="test", version="1",
    )
    run.regions = [region]
    return run, lambda route: f"transcribe:{region.id}:{route}"


def test_each_request_reserves_the_lesser_of_the_two_bounds():
    price = dict(MUSE, context_tokens=131_072)
    # (a) alone: 131,072 in and 4,096 out at muse's price, for both requests.
    assert call_micros(price, None) == 2 * 44_237
    # (b): 10,000 in, then the retry with the answer and the feedback; 4,096 out.
    assert call_micros(price, 10_000) == 7_916 + 11_679
    # (a) wins when the context is the smaller bound.
    assert call_micros(dict(price, context_tokens=1_000), 50_000) == 2 * 5_216


def test_a_documented_rule_caps_the_crop_at_the_models_maximum():
    muse = {"pixels_per_token": 28, "max_tokens": 4_096}
    # 8,000 x 5,000 is 286 x 179 patches: capped at 4,096, plus separators and slack.
    assert image_tokens(muse, 8_000, 5_000) == 4_096 + 286 + 179 + 256
    assert image_tokens(dict(muse, max_tokens=None), 8_000, 5_000) == 286 * 179 + 286 + 179 + 256


@pytest.mark.parametrize(
    "width,height",
    [(64, 64), (600, 400), (4_000, 250), (6_325, 6_325), (8_000, 5_000), (40_000, 1_000)],
)
def test_every_pilot_crop_up_to_the_largest_image_reserves_the_floor(width, height):
    run, step = reading(width, height)
    for route in run.profile.routes:
        assert reading_reservation(run, step(route), 20_000) == 20_000


def test_a_large_crop_on_a_route_with_no_maximum_reserves_above_the_floor():
    registry = with_models(
        published_registry({SYNTHETIC_COLLECTION: "insects"}),
        **{"handwriting-muse": {"image_tokens": {
            "pixels_per_token": 28, "max_tokens": None, "source": "https://example.test/rule",
        }}},
    )
    run, step = reading(8_000, 5_000, registry)
    assert reading_reservation(run, step("handwriting-muse"), 20_000) > 20_000


def test_a_route_that_documents_no_rule_reserves_its_context_length():
    registry = with_models(
        published_registry({SYNTHETIC_COLLECTION: "insects"}),
        **{"handwriting-muse": {"image_tokens": None}},
    )
    run, step = reading(600, 400, registry)
    assert reading_reservation(run, step("handwriting-muse"), 20_000) == 2 * 44_237


def test_the_price_list_needs_a_context_length_for_every_route_that_reads_crops():
    from specimen_digitization.application.collection_profiles import CollectionProfile

    profile = published_registry().resolve("insects").profile.model_dump(mode="json")
    del profile["processing"]["price_list"]["models"]["handwriting-qwen"]["context_tokens"]
    with pytest.raises(ValueError, match="context length"):
        CollectionProfile.model_validate(profile)


def test_a_reservation_that_does_not_fit_blocks_before_the_call(tmp_path):
    # Muse without a documented rule reserves 88,474; the allowance leaves less.
    registry = with_models(priced_registry(), **{"handwriting-muse": {"image_tokens": None}})
    profiles = tuple(
        p.model_copy(update={"processing": p.processing.model_copy(update={
            "program_allowance": ProgramAllowance(
                allowance_micros=80_000, ledger_collection="insects"
            ),
        })}) if p.processing else p
        for p in registry.profiles
    )
    registry = registry.model_copy(update={"profiles": profiles})
    app, principal, row = lab(tmp_path, registry=registry)
    run = app.state.workflow.drain(principal, row["specimen_id"]).run
    assert run.blocker == "program_allowance_exhausted"
    readings = {o.route_id for o in run.observations}
    assert "handwriting-muse" not in readings  # Never called.
