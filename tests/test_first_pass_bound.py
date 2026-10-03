"""The first pass's request bound: what it reserves is what it can spend.

The coordinator (2026-10-03) asked for the first pass's reservation to come from
a bound on its request rather than the route's context. The published price for
first-pass-glm sets `max_input_tokens` and `max_output_tokens`; each request is
sized before it is sent and refused when it could exceed its input bound, and
each answer is capped at its output bound (lane_reservations; first_pass).
"""

import io

import pytest
from PIL import Image

from specimen_digitization.application import first_pass as first_pass_module
from specimen_digitization.application.collection_profiles import (
    ModelPrice,
    published_registry,
)
from specimen_digitization.application.domain import ExecutionPolicy, Profile
from specimen_digitization.application.lane_reservations import (
    image_rule,
    image_tokens,
    request_input_tokens,
)
from specimen_digitization.application.workflow import OperationalBlock

from test_first_pass import INCOMPLETE, MUSE, QWEN, ROUTE, VALID, direct_first_pass, reading

PRICES = published_registry().resolve("insects").profile.processing.price_list
GLM = PRICES.models["first-pass-glm"].model_dump(mode="json")
# The largest pilot slide (subject_105526324, 1,798 x 615) rounded up: the
# whole slide as one crop is the largest crop a pilot region can be.
SLIDE = (1_798, 640)


def png(width, height):
    output = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(output, format="PNG")
    return output.getvalue()


def priced(**bounds):
    """A profile whose first-pass route has the published GLM price and bounds."""
    prices = PRICES.model_dump(mode="json")
    prices["models"][ROUTE.route_id] = dict(GLM, **bounds)
    return Profile(
        first_pass_route=ROUTE.route_id, execution=ExecutionPolicy(price_list=prices)
    )


def test_glm_counts_its_crop_under_the_most_conservative_pinned_rule():
    # GLM documents no image rule, so its crop counts under the smallest pinned
    # square (handwriting-muse's 28 pixels) with no maximum (the 2026-09-24 ruling).
    prices = PRICES.model_dump(mode="json")
    rule = image_rule(prices, "first-pass-glm")
    assert rule == {"pixels_per_token": 28}
    assert image_rule(prices, "handwriting-qwen")["pixels_per_token"] == 32
    # A lab crop of 650 x 609 is 24 x 22 squares, plus separators and slack.
    assert image_tokens(rule, 650, 609) == 24 * 22 + 46 + 256


def test_a_whole_pilot_slide_as_the_crop_is_sent_with_each_answer_capped(
    monkeypatch, tmp_path
):
    calls, infos = [], []
    decision, (_, second) = direct_first_pass(
        monkeypatch, tmp_path, calls, VALID, profile=priced(), crop=png(*SLIDE),
        infos=infos,
    )

    assert decision.selected_observation_id == second.id
    [info] = infos
    assert info.model_settings["max_tokens"] == 4_096
    assert decision.call.parameters == {"max_tokens": 4_096}
    size = request_input_tokens(
        calls[0], info.model_request_parameters, {"pixels_per_token": 28}
    )
    # About a sixth of the 32,768 bound: the crop, the readings, the prompt
    # and the answer's schema, counted a token a byte.
    assert 4_000 < size < 32_768 // 5


def test_each_answer_is_capped_at_the_routes_output_bound(monkeypatch, tmp_path):
    infos = []
    direct_first_pass(
        monkeypatch, tmp_path, [], INCOMPLETE, VALID,
        profile=priced(max_output_tokens=1_000), crop=png(60, 40), infos=infos,
    )

    assert [info.model_settings["max_tokens"] for info in infos] == [1_000, 1_000]


@pytest.mark.parametrize(
    "texts,crop",
    [
        # Readings far past any label: 2 x 40,000 bytes of text.
        (("Epipocous " * 4_000, "Epipsocus " * 4_000), png(60, 40)),
        # A crop that cannot be sized cannot be bounded.
        ((QWEN, MUSE), b"PNG"),
    ],
    ids=["readings past the bound", "an unsized crop"],
)
def test_an_input_that_could_exceed_its_bound_is_refused_before_any_request(
    monkeypatch, tmp_path, texts, crop
):
    calls = []
    readings = [
        reading("handwriting-qwen", texts[0]),
        reading("handwriting-muse", texts[1]),
    ]

    with pytest.raises(OperationalBlock, match="^first_pass_input_over_bound$"):
        direct_first_pass(
            monkeypatch, tmp_path, calls, VALID, readings=readings,
            profile=priced(), crop=crop,
        )

    assert calls == []


def test_a_retry_that_could_exceed_its_bound_is_not_sent(monkeypatch, tmp_path):
    # The first answer is incomplete and 40,000 bytes long, so the retry, which
    # resends it, could pass 32,768 tokens: it stops at its cap, no reading.
    calls = []
    long = dict(INCOMPLETE, rationale="x" * 40_000)

    decision, _ = direct_first_pass(
        monkeypatch, tmp_path, calls, long, VALID, profile=priced(), crop=png(60, 40)
    )

    assert len(calls) == 1
    assert decision.selected_observation_id is None
    assert decision.rationale == first_pass_module.CAP_RATIONALE
    assert decision.call.completion_state == "usage_limit"


def test_an_input_bound_must_fit_the_routes_context():
    price = {"input_micros_per_million": 1, "output_micros_per_million": 1}
    assert ModelPrice(**price, context_tokens=2_000, max_input_tokens=2_000)
    with pytest.raises(ValueError, match="fit the route's context length"):
        ModelPrice(**price, context_tokens=1_000, max_input_tokens=2_000)
    with pytest.raises(ValueError, match="fit the route's context length"):
        ModelPrice(**price, max_input_tokens=2_000)
