"""The reader-A option: Kimi K3.1 Pro in reader A's place, behind SPECIMEN_READER_A.

The autonomy program's reader measurement (2026-11-18): on the 100 truth slides
Kimi-K3.1-Pro read a field's decisive text exactly right 96 % of the time
against reader A's 85 %, answered every label, and where the two readers differ
and one is right its own text was the right one 35 times of 43. The option runs
it as reader A with reader B, the organiser and everything else as published;
the published profile is unchanged. These tests make no model call.
"""

import json
from types import SimpleNamespace

import httpx
import pytest
from huggingface_hub.utils import _http as hf_http
from pydantic_ai import BinaryContent
from pydantic_ai.usage import UsageLimits

from specimen_digitization.application.api import SYNTHETIC_COLLECTION
from specimen_digitization.application.collection_profiles import (
    PUBLISHED_PROFILES,
    CollectionProfileRegistry,
    published_registry,
)
from specimen_digitization.application.collection_runtime import classify_and_select
from specimen_digitization.application.domain import Profile, Region, Run
from specimen_digitization.application.lane import queue
from specimen_digitization.application.lane_costs import model_cost
from specimen_digitization.application.lane_reservations import (
    reading_reservation,
    step_reservation,
)
from specimen_digitization.application.model_option import (
    READER_A_SETTING,
    SETTING,
    ModelOptionConfigurationError,
    active_routes,
    reader_a_route,
    reader_a_variant,
)
from specimen_digitization.application.production import ProductionAdapters
from specimen_digitization.application.profile_runtime import published_risk_registry
from specimen_digitization.application.storage import LocalBlobs
from specimen_digitization.model_gateway import (
    HUGGINGFACE_ROUTES,
    INITIAL_HUGGINGFACE_ROUTES,
    READER_A_HUGGINGFACE_ROUTES,
    READER_HUGGINGFACE_ROUTES,
    HuggingFaceModelGateway,
    organiser_route,
)
from specimen_digitization.prompts import PromptName, ResolvedPrompt
from specimen_digitization.transcription import build_literal_transcription_agent

from test_lane_profile import USER
from test_lane_trigger import specimen_with

KIMI = "moonshotai/Kimi-K3.1-Pro"
VARIANT = "1.0.0+reader-a.kimi"
QWEN = {"model_id": "Qwen/Qwen3-VL-30B-A3B-Instruct", "provider": "novita"}
MUSE = {"model_id": "meta-models/Muse-Glimmer-30B", "provider": "deepinfra"}
KIMI_PIN = {"model_id": KIMI, "provider": "deepinfra"}


def as_published() -> CollectionProfileRegistry:
    """The published file as written, with no option applied."""
    return CollectionProfileRegistry.model_validate(json.loads(PUBLISHED_PROFILES.read_text()))


def published_profile() -> dict:
    return as_published().resolve("insects").profile.model_dump(mode="json")


# The switch.


@pytest.mark.parametrize("value", [None, "", " ", "\t\n"])
def test_unset_or_blank_is_off(value):
    environ = {} if value is None else {READER_A_SETTING: value}

    assert reader_a_route(environ) is None
    assert published_registry(environ=environ).model_dump(mode="json") == (
        as_published().model_dump(mode="json")
    )


def test_with_the_switch_unset_the_published_profile_loads_as_written(monkeypatch):
    monkeypatch.delenv(READER_A_SETTING, raising=False)
    monkeypatch.delenv(SETTING, raising=False)

    profile = published_registry().resolve("insects").profile

    assert profile.digest == as_published().resolve("insects").profile.digest
    assert profile.model_routes == ("handwriting-qwen", "handwriting-muse")
    assert profile.version == "1.0.0"


@pytest.mark.parametrize("value", ["kimi", " kimi ", "kimi\n"])
def test_kimi_puts_the_kimi_route_in_reader_as_place(value):
    assert reader_a_route({READER_A_SETTING: value}) == "handwriting-kimi"


@pytest.mark.parametrize(
    "value", ["gpu-secret-value", "Kimi", "qwen", "muse", "yes", "true", "kimi,muse", "kimi k3"]
)
def test_any_other_value_raises_naming_the_setting_never_the_value(value):
    with pytest.raises(ModelOptionConfigurationError) as caught:
        reader_a_route({READER_A_SETTING: value})

    # A ValueError, as the drain's other settings raise (worker._execute_drain).
    assert isinstance(caught.value, ValueError)
    assert READER_A_SETTING in str(caught.value)
    assert value not in str(caught.value)


def test_a_mistyped_switch_stops_the_profiles_from_loading(monkeypatch):
    monkeypatch.setenv(READER_A_SETTING, "gpu-secret-value")

    with pytest.raises(ModelOptionConfigurationError) as caught:
        published_registry()

    assert READER_A_SETTING in str(caught.value) and "gpu-secret-value" not in str(caught.value)


def test_it_does_not_combine_with_the_nvidia_option():
    with pytest.raises(ModelOptionConfigurationError) as caught:
        published_registry(environ={READER_A_SETTING: "kimi", SETTING: "readers"})

    assert READER_A_SETTING in str(caught.value) and SETTING in str(caught.value)


# The variant.


def test_the_variant_changes_reader_a_its_price_and_the_version_and_nothing_else():
    profile = published_registry(environ={READER_A_SETTING: "kimi"}).resolve("insects").profile
    published = published_profile()
    expected = json.loads(json.dumps(published))
    expected["version"] = VARIANT
    expected["model_routes"] = ["handwriting-kimi", "handwriting-muse"]
    processing = expected["processing"]
    processing["stage_cost_micros"]["cost_micros"]["transcribe:handwriting-kimi"] = 20_000
    processing["price_list"]["version"] = "pilot-prices-2026-10-25+reader-a.kimi"
    processing["price_list"]["models"]["handwriting-kimi"] = {
        "input_micros_per_million": 1_900_000,
        "output_micros_per_million": 9_500_000,
        "context_tokens": 1_048_576,
        "image_tokens": {
            "pixels_per_token": 28,
            "max_tokens": 16_384,
            "source": "https://huggingface.co/moonshotai/Kimi-K3.1-Pro/blob/main/preprocessor_config.json",
        },
    }

    # Reader B, the first-pass and harness routes, every limit, the cost limit
    # and every other price are the published profile's.
    assert profile.model_dump(mode="json") == expected
    assert (profile.first_pass_route, profile.harness_route) == ("first-pass-glm", "harness-deepseek")
    assert len(profile.model_routes) == len(published["model_routes"]) == 2


def test_the_variant_replaces_the_profile_and_its_mapping_names_the_variant():
    base = as_published()

    registry = published_registry(
        {"private-collection-id": "insects"}, environ={READER_A_SETTING: "kimi"}
    )

    assert [profile.version for profile in registry.profiles] == [VARIANT]
    assert [mapping.model_dump() for mapping in registry.mappings] == [
        {"collection_id": "insects", "profile_id": "zoology_insects_slides", "profile_version": VARIANT}
    ]
    assert registry.resolve("private-collection-id").profile.version == VARIANT
    assert (registry.version, registry.nodes) == (base.version, base.nodes)


def test_the_published_file_names_no_kimi_route():
    # The published profile, its price list and its digest stay as they are until
    # the option is made the default.
    text = PUBLISHED_PROFILES.read_text()

    assert "kimi" not in text.lower()
    assert "reader-a" not in text


def test_a_profile_whose_first_reader_is_not_qwen_has_no_variant():
    data = json.loads(PUBLISHED_PROFILES.read_text())
    data["profiles"][0]["model_routes"] = ["handwriting-muse", "handwriting-qwen"]

    with pytest.raises(ValueError, match="not Qwen"):
        reader_a_variant(CollectionProfileRegistry.model_validate(data), "handwriting-kimi")


def test_a_profile_that_already_carries_build_metadata_has_no_variant():
    data = json.loads(PUBLISHED_PROFILES.read_text())
    data["profiles"][0]["version"] = "1.0.0+local"
    data["mappings"][0]["profile_version"] = "1.0.0+local"

    with pytest.raises(ValueError, match="build metadata"):
        reader_a_variant(CollectionProfileRegistry.model_validate(data), "handwriting-kimi")


def test_no_switch_returns_the_registry_itself():
    registry = as_published()

    assert reader_a_variant(registry, None) is registry


# The route.


def test_the_kimi_route_is_kimi_k31_pro_on_deepinfra_through_the_router_at_low_reasoning():
    route = HUGGINGFACE_ROUTES["handwriting-kimi"]

    assert (route.model_id, route.provider, route.transport) == (KIMI, "deepinfra", "router")
    assert (route.logical_capability, route.required_input_modalities) == (
        "handwriting_transcriber",
        ("text", "image"),
    )
    # The settings the benchmark measured it on: reasoning "low", the output tool
    # forced (Pydantic AI's own "required"; no unforced tool).
    assert route.request_options == (("reasoning_effort", "low"),)
    assert route.forced_tool_choice_disables_thinking is False
    assert route.served_model_name == f"{KIMI}:deepinfra"


def test_the_kimi_route_is_a_reader_route_and_the_initial_pair_is_unchanged():
    assert set(READER_A_HUGGINGFACE_ROUTES) == {"handwriting-kimi"}
    assert READER_HUGGINGFACE_ROUTES["handwriting-kimi"] is READER_A_HUGGINGFACE_ROUTES["handwriting-kimi"]
    assert set(INITIAL_HUGGINGFACE_ROUTES) == {"handwriting-qwen", "handwriting-muse"}


def test_preflight_checks_the_kimi_route_with_the_option_on_and_not_otherwise():
    off = active_routes(())
    on = active_routes((), "handwriting-kimi")

    assert "handwriting-kimi" not in off
    # Qwen stays: the organiser runs on it.
    assert set(on) == set(off) | {"handwriting-kimi"}
    assert "handwriting-qwen" in on


def offline_reader_request(monkeypatch, route_id):
    """Run the real reader agent on the route over an offline transport, as
    production._transcribe_direct runs it; return (url, headers, body)."""
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        sent.append((str(request.url), request.headers, body))
        output = {"verbatim_text": "synthetic alpha", "lines": ["synthetic alpha"]}
        return httpx.Response(200, json={
            "id": "synthetic-completion", "object": "chat.completion", "created": 0,
            "model": KIMI, "system_fingerprint": "offline-synthetic",
            "choices": [{"index": 0, "finish_reason": "tool_calls", "logprobs": None,
                         "message": {"role": "assistant", "content": None, "tool_calls": [{
                             "id": "synthetic-call", "type": "function", "function": {
                                 "name": body["tools"][0]["function"]["name"],
                                 "arguments": json.dumps(output)}}]}}],
            "usage": {"prompt_tokens": 809, "completion_tokens": 133, "total_tokens": 942}})

    monkeypatch.setattr(hf_http, "_GLOBAL_ASYNC_CLIENT_FACTORY",
                        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    gateway = HuggingFaceModelGateway(token="hf_synthetic_offline", bill_to="field-museum")
    prompt = ResolvedPrompt(name=PromptName.LITERAL_TRANSCRIPTION, text="Read the synthetic fixture literally.",
                            requested_label="offline", served_label=None, version=None,
                            resolution_reason="code-default")
    agent = build_literal_transcription_agent(gateway, route_id=route_id, prompt=prompt)
    from specimen_digitization.application.reliability import run_agent_bounded

    result = run_agent_bounded(
        agent,
        ["Transcribe only the supplied source image.",
         BinaryContent(data=b"synthetic image fixture", media_type="image/png")],
        timeout_seconds=30,
        usage_limits=UsageLimits(request_limit=2, total_tokens_limit=16000),
    )
    assert result.output.verbatim_text == "synthetic alpha"
    (request,) = sent
    return request


def test_the_kimi_reader_request_is_the_one_the_benchmark_measured(monkeypatch):
    url, headers, body = offline_reader_request(monkeypatch, "handwriting-kimi")

    # One request to the router, pinned to DeepInfra by the model's name, on the
    # pipeline's token and org billing.
    assert url == "https://router.huggingface.co/v1/chat/completions"
    assert body["model"] == f"{KIMI}:deepinfra"
    assert headers["x-hf-bill-to"] == "field-museum"
    assert headers["authorization"] == "Bearer hf_synthetic_offline"
    # The reader's own call: the prompt as the system message, the user text and
    # the crop as an image part, the one output tool, forced, the answer capped
    # at the 4,096 tokens run_agent_bounded allows (the longest of the benchmark's
    # 269 answers was 736 tokens, reasoning included).
    assert body["tool_choice"] == "required"
    assert [tool["function"]["name"] for tool in body["tools"]] == ["final_result"]
    assert body["max_tokens"] == 4096
    assert body["reasoning_effort"] == "low"
    assert "response_format" not in body
    system, user = body["messages"]
    assert (system["role"], user["role"]) == ("system", "user")
    assert [part["type"] for part in user["content"]] == ["text", "image_url"]
    assert user["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_reader_a_and_reader_b_today_send_no_request_option():
    for route_id in ("handwriting-qwen", "handwriting-muse"):
        assert HUGGINGFACE_ROUTES[route_id].request_options == ()


# The price.


def test_kimi_is_priced_at_the_router_list_price_on_deepinfra():
    prices = published_registry(environ={READER_A_SETTING: "kimi"}).profiles[0].processing.price_list.model_dump(
        mode="json"
    )

    # The benchmark's first Kimi call: 809 input and 133 output tokens, USD
    # 0.0028006 at USD 1.90 in and 9.50 out per million (ceil: 2,801 micro-dollars).
    assert model_cost(prices, "handwriting-kimi", 809, 133) == 2_801
    # Its 269 calls: 1.186 USD in all, 0.00441 a label.
    assert model_cost(prices, "handwriting-kimi", 1_000_000, 0) == 1_900_000
    assert model_cost(prices, "handwriting-kimi", 0, 1_000_000) == 9_500_000
    # Today's reader A and reader B keep their rows.
    assert model_cost(prices, "handwriting-qwen", 1_000_000, 1_000_000) == 900_000
    assert model_cost(prices, "handwriting-muse", 1_000_000, 1_000_000) == 1_500_000


def test_kimi_image_tokens_follow_its_28_pixel_rule():
    from math import ceil

    from specimen_digitization.application.lane_reservations import image_tokens

    prices = published_registry(environ={READER_A_SETTING: "kimi"}).profiles[0].processing.price_list
    rule = prices.models["handwriting-kimi"].image_tokens.model_dump(mode="json")

    # The benchmark's crops came out at 781 + ceil(h / 28) x ceil(w / 28) prompt
    # tokens each (269 of 269); the reservation's grid is that count (plus
    # separators and slack, a bound above it).
    for width, height in [(92, 175), (473, 10), (620, 563)]:
        grid = ceil(height / 28) * ceil(width / 28)
        assert image_tokens(rule, width, height) >= grid
        assert image_tokens(rule, width, height) == grid + ceil(height / 28) + ceil(width / 28) + 256


# A run under the variant.


def variant_run(tmp_path, monkeypatch):
    """A run the API queued and the worker classified, both under the option."""
    monkeypatch.setenv(READER_A_SETTING, "kimi")
    monkeypatch.delenv(SETTING, raising=False)
    registry = published_registry({SYNTHETIC_COLLECTION: "insects"})
    specimen = specimen_with(Run(profile=Profile(synthetic=False)))
    queue(specimen, registry, USER)
    issue = classify_and_select(
        specimen, registry, None, LocalBlobs(tmp_path), published_risk_registry()
    )
    assert issue is None
    run = specimen.run
    run.dependencies = ProductionAdapters.pin_dependencies(SimpleNamespace(classifier=None), run)
    return specimen


def with_region(specimen, width, height):
    region = Region(
        asset_id=specimen.asset.id, x=0, y=0, width=width, height=height,
        order=0, method="test", version="1",
    )
    specimen.run.regions = [region]
    return region


def test_a_run_under_the_variant_reads_with_kimi_and_muse_and_pins_all_three_routes(tmp_path, monkeypatch):
    run = variant_run(tmp_path, monkeypatch).run

    assert (run.profile.id, run.profile.version) == ("zoology_insects_slides", VARIANT)
    assert run.profile.routes == ("handwriting-kimi", "handwriting-muse")
    assert run.profile.first_pass_route == "first-pass-glm"
    assert run.profile_snapshot["version"] == VARIANT
    # Qwen stays pinned: the organiser runs on it.
    assert run.dependencies["routes"] == {
        "handwriting-kimi": KIMI_PIN,
        "handwriting-muse": MUSE,
        "handwriting-qwen": QWEN,
        "first-pass-glm": {"model_id": "zai-org/GLM-5.3-Flash", "provider": "novita"},
    }
    execution = run.profile.execution
    assert execution.price_list["version"] == "pilot-prices-2026-10-25+reader-a.kimi"
    assert execution.stage_cost_reservations.for_step("transcribe:r:handwriting-kimi") == 20_000
    # The same limits as the pair: two readers.
    published = published_profile()["processing"]
    assert (execution.max_tokens, execution.max_external_calls) == (
        published["max_tokens"],
        published["max_external_calls"],
    )


def test_a_run_with_the_switch_off_pins_no_kimi_route(tmp_path, monkeypatch):
    monkeypatch.delenv(READER_A_SETTING, raising=False)
    monkeypatch.delenv(SETTING, raising=False)
    registry = published_registry({SYNTHETIC_COLLECTION: "insects"})
    specimen = specimen_with(Run(profile=Profile(synthetic=False)))
    queue(specimen, registry, USER)
    classify_and_select(specimen, registry, None, LocalBlobs(tmp_path), published_risk_registry())
    run = specimen.run
    run.dependencies = ProductionAdapters.pin_dependencies(SimpleNamespace(classifier=None), run)

    assert run.profile.routes == ("handwriting-qwen", "handwriting-muse")
    assert set(run.dependencies["routes"]) == {"handwriting-qwen", "handwriting-muse", "first-pass-glm"}
    # No Kimi row in a run the option did not touch.
    assert "handwriting-kimi" not in run.profile.execution.price_list["models"]


def test_a_variant_reading_reserves_from_the_kimi_row(tmp_path, monkeypatch):
    specimen = variant_run(tmp_path, monkeypatch)
    region = with_region(specimen, 8_000, 5_000)
    step = f"transcribe:{region.id}:handwriting-kimi"
    run = specimen.run

    # The crop under Kimi's rule: 28-pixel squares, 179 x 286 of them, capped at
    # 16,384 tokens, plus 179 + 286 separators and 256 of slack: 17,105 tokens.
    # With the 3,415 tokens of the pinned reading prompt and schema:
    # Request 1: 20,520 in, 4,096 out at USD 1.90 / 9.50:
    #   ceil((20,520 x 1,900,000 + 4,096 x 9,500,000) / 10^6) = 77,900.
    # Request 2 (the retry adds the answer, the feedback and framing): 33,064 in:
    #   ceil((33,064 x 1,900,000 + 4,096 x 9,500,000) / 10^6) = 101,734.
    assert reading_reservation(run, step, 1) == 77_900 + 101_734 == 179_634
    # Above the 20,000 floor, so the reservation is the worst case.
    assert step_reservation(run, step) == 179_634


def test_variant_parse_stays_on_qwen(tmp_path, monkeypatch):
    specimen = variant_run(tmp_path, monkeypatch)
    with_region(specimen, 600, 400)

    # Reader A's route is Kimi's, but the organiser's is Qwen's: parse reserves
    # two whole Qwen contexts, as with the option off (test_nvidia_option).
    assert specimen.run.profile.routes[0] == "handwriting-kimi"
    assert step_reservation(specimen.run, "parse") == 58_164


def test_the_organiser_route_follows_reader_a_unless_the_readers_option_names_another():
    assert organiser_route(("handwriting-qwen", "handwriting-muse")) == "handwriting-qwen"
    assert organiser_route(("handwriting-kimi", "handwriting-muse")) == "handwriting-qwen"
    # With the NVIDIA readers stage reader A stays Qwen, and so does parse.
    assert organiser_route(("handwriting-qwen", "handwriting-muse", "handwriting-nemotron")) == (
        "handwriting-qwen"
    )
    assert organiser_route(()) is None


def test_parse_is_called_on_qwen_and_checks_its_pin(monkeypatch):
    from specimen_digitization.application import harness

    seen = []

    class Stop(Exception):
        pass

    class Gateway:
        def model_for(self, route):
            seen.append(route)
            raise Stop

    run = SimpleNamespace(
        profile=SimpleNamespace(routes=("handwriting-kimi", "handwriting-muse"), mandatory_fields=()),
        dependencies={"prompts": {PromptName.STRUCTURED_EXTRACTION.value: {
            "name": PromptName.STRUCTURED_EXTRACTION.value, "text": "Extract.", "requested_label": "x",
            "served_label": None, "version": None, "resolution_reason": "code-default"}}},
    )
    with pytest.raises(Stop):
        harness.extract_with_agent(Gateway(), None, SimpleNamespace(run=run))

    assert seen == ["handwriting-qwen"]
