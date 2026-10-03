"""G3 for the first pass: what its spans record follows the capture mode.

The first-pass agent carries no instrumentation of its own (first_pass.py;
HARNESS.md section 3, "Tracing"), so its spans record what the process's global
setting allows. configure_observability installs that setting: approved-content
records the prompt, the request and the answer; metadata records none of them;
neither ever records the crop's bytes (observability.CaptureMode).
"""

import base64
import json

import logfire
import pytest
from pydantic_ai import Agent
from pydantic_ai.models.instrumented import InstrumentationSettings

from specimen_digitization import observability

from test_first_pass import (
    MUSE,
    PINNED,
    PROMPT,
    QWEN,
    ROUTE,
    VALID,
    direct_first_pass,
    reading,
)

# Plain tokens: Logfire's scrubbing patterns would redact a value with "secret",
# "auth", "session" and the like, which would hide a canary for the wrong reason.
PROMPT_CANARY = "PROMPTCANARY-k7v3"
LABEL_CANARY = "LABELCANARY-m2q8"
ANSWER_CANARY = "ANSWERCANARY-x5w1"
IMAGE_CANARY = b"IMAGECANARY-p9r4"
CONTENT = (PROMPT_CANARY, LABEL_CANARY, ANSWER_CANARY)
CROP = b"\x89PNG\r\n\x1a\n" + IMAGE_CANARY * 8


@pytest.fixture
def global_instrumentation():
    """Put back the process-wide agent instrumentation a test installs."""
    previous = Agent._instrument_default
    try:
        yield
    finally:
        Agent.instrument_all(previous)


def configure(monkeypatch, mode):
    """Run configure_observability for this mode as a non-production model child
    does (observability.isolated_model_span), keeping capfire's exporter: the
    SDK configuration is recorded, not applied, so nothing is sent anywhere."""
    configured = []
    monkeypatch.delenv("SPECIMEN_TRACE_EXPORT_MODE", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("LOGFIRE_CAPTURE_MODE", mode)
    monkeypatch.setattr(observability, "_configured_settings", None)
    monkeypatch.setattr(logfire, "configure", lambda **kw: configured.append(kw))
    settings = observability.configure_observability(send_to_logfire=False)
    assert [options["resource_attributes"] for options in configured] == [
        {"specimen.telemetry.capture_mode": mode}
    ]
    assert configured[0]["send_to_logfire"] is False
    return settings


def first_pass_trace(monkeypatch, tmp_path, capfire):
    """Run the first pass on a crop and return everything Logfire captured."""
    prompt = PROMPT.model_copy(update={"text": PROMPT.text + " " + PROMPT_CANARY})
    dependencies = {
        "routes": {ROUTE.route_id: PINNED},
        "prompts": {prompt.name.value: prompt.model_dump(mode="json")},
    }
    # The same line on both readings keeps their three differences (VALID's).
    readings = [
        reading("handwriting-qwen", QWEN + "\nleg. " + LABEL_CANARY),
        reading("handwriting-muse", MUSE + "\nleg. " + LABEL_CANARY),
    ]
    answer = dict(VALID, rationale="The image shows Epipsocus. " + ANSWER_CANARY)
    calls = []

    decision, (_, second) = direct_first_pass(
        monkeypatch, tmp_path, calls, answer,
        readings=readings, dependencies=dependencies, crop=CROP,
    )

    # The call ran with the canaries in it, so their absence is the setting's.
    assert decision.selected_observation_id == second.id
    assert ANSWER_CANARY in decision.rationale
    [messages] = calls
    assert messages[0].instructions.endswith(PROMPT_CANARY)
    sent = [part.content for part in messages[0].parts]
    assert any(LABEL_CANARY in str(content) for content in sent)
    assert any(getattr(item, "data", None) == CROP for item in sent[0])
    spans = capfire.exporter.exported_spans_as_dict()
    names = [span["name"] for span in spans]
    assert "invoke_agent first_pass_" + ROUTE.route_id.replace("-", "_") in names
    assert any(name.startswith("chat ") for name in names)
    logs = capfire.log_exporter.exported_logs_as_dicts()
    return json.dumps({"spans": spans, "logs": logs}, default=str)


def assert_no_image_bytes(trace):
    assert IMAGE_CANARY.decode() not in trace
    assert base64.b64encode(CROP).decode() not in trace
    # The canary's base64 at each of the three byte alignments in the crop.
    for offset in range(3):
        chunk = base64.b64encode(CROP[8 + offset :]).decode()[4:24]
        assert chunk not in trace
    assert "data:image/" not in trace


@pytest.mark.parametrize("mode", ["approved-content", "metadata"])
def test_first_pass_spans_follow_the_capture_mode_and_never_carry_the_crop(
    capfire, monkeypatch, tmp_path, global_instrumentation, mode
):
    settings = configure(monkeypatch, mode)

    trace = first_pass_trace(monkeypatch, tmp_path, capfire)

    assert settings.include_binary_content is False
    shown = mode == "approved-content"
    assert settings.include_content is shown
    # Both sides: each canary is present under approved-content, absent otherwise.
    for canary in CONTENT:
        assert (canary in trace) is shown, canary
    assert_no_image_bytes(trace)


def test_the_image_check_finds_bytes_that_binary_capture_records(
    capfire, monkeypatch, tmp_path, global_instrumentation
):
    # The control: approved-content with binary capture switched on puts the
    # crop on the spans, and the image check above finds it there.
    configure(monkeypatch, "approved-content")
    Agent.instrument_all(
        InstrumentationSettings(
            include_content=True,
            include_binary_content=True,
            include_model_request_parameters=True,
            version=5,
        )
    )

    trace = first_pass_trace(monkeypatch, tmp_path, capfire)

    with pytest.raises(AssertionError):
        assert_no_image_bytes(trace)
    assert base64.b64encode(CROP).decode() in trace
