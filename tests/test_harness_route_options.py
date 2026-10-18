"""A route's request options reach the harness's settings pin (PR #382 review, finding 2).

`EffectModel` blocks any request whose settings differ from `expected_settings`.
A route's request options are the wrapped model's own settings
(`HuggingFaceModelGateway.model_for`), which Pydantic AI layers under the
agent's on every request, so they are part of what each request carries. Before,
`expected_settings` held the caller's settings only, and a request option on
`harness-deepseek` would have blocked every harness request as
`model_settings_differ_from_pin`. No harness route carries one today
(`test_first_pass_reasoning_bound.py`); this keeps adding one safe.
"""

from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage

from specimen_digitization.model_gateway import HUGGINGFACE_ROUTES
from specimen_digitization.research_harness.contracts import SpecialistRole

from test_research_harness_agents import model, requests, sql_broker

OPTION = {"reasoning_effort": "low"}


def test_a_route_option_on_the_harness_model_is_part_of_its_settings_pin(tmp_path):
    store, scope, lease, broker = sql_broker(tmp_path)
    request = requests()[SpecialistRole.TAXONOMY]
    sent = []

    def respond(messages, info):
        sent.append(dict(info.model_settings or {}))
        return ModelResponse([TextPart("settled")], usage=RequestUsage(input_tokens=11, output_tokens=7))

    wrapped = FunctionModel(respond, settings={"extra_body": OPTION})
    gateway = model(wrapped, request=request, broker=broker, scope=scope, lease=lease)

    assert dict(gateway.expected_settings) == {"extra_body": OPTION, "max_tokens": 128}
    result = Agent(gateway, model_settings=dict(gateway.expected_settings)).run_sync("Research it.")

    assert result.output == "settled"
    assert [settings.get("extra_body") for settings in sent] == [OPTION]


def test_the_harness_route_carries_no_request_option_today():
    assert HUGGINGFACE_ROUTES["harness-deepseek"].request_options == ()
