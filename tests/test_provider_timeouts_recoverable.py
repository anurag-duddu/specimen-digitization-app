"""A provider call that times out is handled as a timeout (reader, first pass, organiser).

Truth slide 105526335, autonomy confirmation runs C1 to C3 (2026-11-19 to 2026-11-21):
the `handwriting-qwen` reader on one label never answered within the HTTP
client's bound (half the reader's deadline: 60 s), four times. The client raises
its own timeout class, `httpx.ReadTimeout`, which is no `TimeoutError`.
`provider_privacy.PrivateProviderModel` turned it into a bare
`RuntimeError("provider_request_failed")`, so `reliability.run_agent_bounded`'s
timeout branch never saw it. In the isolated model child that RuntimeError ends
the child as `worker_failed`:

- a reader: `reader_worker_failed`, a known failure, retried and given up
  (unchanged in outcome; the code it records now says it was a timeout);
- a first pass or the organiser's extraction: `worker_call_failed`, which
  `model_runtime.child_without_answer` does not recover, so the run blocked as
  `external_outcome_unknown`, held for a person.

The three agents now wrap their model in the field experts' `ClientTimeouts`
(field_research/experts.py), inside `PrivateProviderModel`, as the experts and
the second opinion already do: the client's timeout becomes
`TimeoutError("provider_request_timeout")`, and run_agent_bounded's existing
branch makes it `provider_deadline_outcome_unknown` (an unknown outcome, held
at its full reservation), which each step already retries and gives up.

Authority: the coordinator's engineering ruling of 2026-11-21 ("a timeout is a
timeout"), not an owner ruling; no adjudication or queue rule is added.

The lab is tests/test_rate_limit_refusal.py's: the real isolated model child
with an offline fixture provider (here raising the HTTP client's own timeout),
the published pilot profile's prices and pins, both ledgers wired as production
wires them. No network.
"""

import traceback

import httpx
import pytest
from pydantic_ai.messages import ModelResponse
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import UsageLimits

from specimen_digitization.application.collection_profiles import published_registry
from specimen_digitization.application.domain import Disposition
from specimen_digitization.application.lane_reservations import step_reservation
from specimen_digitization.application.reliability import AdapterFailure, run_agent_bounded
from specimen_digitization.application.storage import LocalBlobs
from specimen_digitization.application.api import SYNTHETIC_COLLECTION

import test_rate_limit_refusal
from test_extraction_recovery import extraction_findings, extraction_lab, parse_calls
from test_first_pass_given_up import GIVEN_UP, first_pass_step, given_up_findings
from test_lane_reservations import with_models
from test_lane_routes import FIRST_PASS_RESERVATION, PARSE_RESERVATION, start
from test_rate_limit_refusal import MUSE, ChildLab, drains, lab, ledger_rows, requests

TIMEOUT = "provider_deadline_outcome_unknown"
CANARY = "PRIVATE-TIMEOUT-CANARY"


def no_canary(run):
    assert CANARY not in run.model_dump_json()


def both_ledgers_hold(last, step, attempts, reserved):
    """Every attempt held in full in the research ledger (never settled) and the
    program ledger equal to the run's own held total."""
    reservations = last.research["ordinary_reservations"]
    assert [reservations[f"{step}:{n}"] for n in attempts] == [
        {"reserved_micros": reserved, "settled_micros": None}
    ] * len(attempts)
    assert last.program == last.run.usage.reserved_cost_micros


def three_first_passes_fit(monkeypatch):
    """Three held first-pass attempts fit the run's limit when the route's
    context is small (test_first_pass_given_up's provider-error test). At the
    published prices only two do: see the published-prices test below."""
    registry = with_models(
        published_registry({SYNTHETIC_COLLECTION: "insects"}),
        **{"first-pass-glm": {"context_tokens": 32_768}},
    )
    monkeypatch.setattr(
        test_rate_limit_refusal, "start", lambda path, kept: start(path, kept, registry)
    )


# The three steps, each through the real child and workflow ---------------------------------


def test_a_reader_whose_provider_times_out_records_a_timeout_and_is_given_up(tmp_path, monkeypatch):
    # Before: the same three attempts and the same end, but recorded as
    # `reader_worker_failed` (the child died of an unmapped RuntimeError).
    adapters = ChildLab(LocalBlobs(tmp_path / "blobs"), readings=3)
    workflow, principal, ident, backend = lab(tmp_path, monkeypatch, adapters, "client_timeout")

    *retried, last = drains(workflow, principal, ident, backend)

    run = last.run
    region = run.regions[0].id
    step = f"transcribe:{region}:{MUSE}"
    assert [d.run.blocker for d in retried] == [TIMEOUT] * 2
    assert [d.run.stage for d in retried] == ["retry_scheduled"] * 2
    assert requests(tmp_path, "transcribe") == 3
    assert (run.stage, run.blocker, run.disposition) == ("finalized", None, Disposition.REVIEW)
    assert run.attempts[step] == 3 and step in run.completed_steps
    assert f"independent_observations_missing:{region}" in [*run.reasons, *run.open_reasons]
    # Each attempt is held at its full reservation: never free.
    reading = step_reservation(run, step)
    assert reading > 0
    assert ledger_rows([c for c in run.paid_calls if c["step"] == step]) == [
        (n, "failed", "reserved", reading, None, TIMEOUT) for n in (1, 2, 3)
    ]
    both_ledgers_hold(last, step, (1, 2, 3), reading)
    no_canary(run)


def test_a_first_pass_whose_provider_times_out_is_retried_then_given_up_when_three_attempts_fit(
    tmp_path, monkeypatch
):
    # Before: the first attempt blocked the run as `external_outcome_unknown`
    # (the child's `worker_call_failed`), held for a person: no retry, and an
    # operator's Retry refused. What the code allows when three reservations
    # fit the run's limit (the route's context made small).
    three_first_passes_fit(monkeypatch)
    adapters = ChildLab(LocalBlobs(tmp_path / "blobs"), first_passes=3)
    workflow, principal, ident, backend = lab(tmp_path, monkeypatch, adapters, "client_timeout")

    *retried, last = drains(workflow, principal, ident, backend)

    run = last.run
    region = run.regions[0].id
    step = first_pass_step(run)
    assert [(d.run.stage, d.run.blocker) for d in retried] == [("retry_scheduled", TIMEOUT)] * 2
    assert requests(tmp_path, "first_pass") == 3
    assert (run.stage, run.blocker, run.disposition) == ("finalized", None, Disposition.REVIEW)
    assert run.attempts[step] == 3 and step in run.completed_steps
    assert given_up_findings(run) == [(GIVEN_UP, "warning", f"{GIVEN_UP}:{region}:{TIMEOUT}")]
    assert "unknown_outcome_kinds" not in run.dependencies
    reserved = step_reservation(run, step)
    assert reserved > 0
    # Each attempt is held at its full reservation and names the timeout (an
    # unknown outcome is a reading failure on every attempt: workflow.py, the
    # AdapterFailure branch).
    assert ledger_rows([c for c in run.paid_calls if c["step"] == step]) == [
        (n, "failed", "reserved", reserved, None, TIMEOUT) for n in (1, 2, 3)
    ]
    both_ledgers_hold(last, step, (1, 2, 3), reserved)
    no_canary(run)


def test_at_the_published_prices_a_first_pass_timing_out_sends_two_attempts_and_the_rest_go_unsent(
    tmp_path, monkeypatch
):
    # The published pilot profile: a first pass holds 318,670 micro-USD and the
    # specimen's limit is USD 1. Two labels. The first label's first pass times
    # out twice, each attempt held in full; the third attempt does not fit the
    # specimen's limit and is not sent, so the label is given up on
    # `cost_budget_exhausted`; the second label's first pass is given up unsent
    # for the same reason. Before: blocked after the first attempt.
    adapters = ChildLab(LocalBlobs(tmp_path / "blobs"), first_passes=4)
    adapters.regions = 2
    workflow, principal, ident, backend = lab(tmp_path, monkeypatch, adapters, "client_timeout")

    *retried, last = drains(workflow, principal, ident, backend)

    run = last.run
    first, second = (r.id for r in run.regions)
    step = "first_pass:" + first
    assert [(d.run.stage, d.run.blocker) for d in retried] == [("retry_scheduled", TIMEOUT)] * 2
    assert requests(tmp_path, "first_pass") == 2
    assert (run.stage, run.blocker) == ("finalized", None)
    assert run.disposition is not None
    assert run.attempts[step] == 2 and step in run.completed_steps
    assert "first_pass:" + second not in run.attempts
    assert step_reservation(run, step) == FIRST_PASS_RESERVATION == 318_670
    assert run.profile.execution.approved_cost_limit_micros == 1_000_000
    assert given_up_findings(run) == [
        (GIVEN_UP, "warning", f"{GIVEN_UP}:{first}:cost_budget_exhausted"),
        (GIVEN_UP, "warning", f"{GIVEN_UP}:{second}:cost_budget_exhausted"),
    ]
    # The two sent attempts are held in full; nothing is recorded for the unsent.
    assert ledger_rows([c for c in run.paid_calls if c["step"].startswith("first_pass:")]) == [
        (n, "failed", "reserved", FIRST_PASS_RESERVATION, None, TIMEOUT) for n in (1, 2)
    ]
    both_ledgers_hold(last, step, (1, 2), FIRST_PASS_RESERVATION)
    assert not any(k.startswith("first_pass:" + second) for k in last.research["ordinary_reservations"])
    no_canary(run)


def test_an_extraction_whose_provider_times_out_is_retried_then_given_up(tmp_path, monkeypatch):
    # Before: as the first pass, blocked as `external_outcome_unknown` on the
    # first attempt and held; `parse` is not even reconcilable by an administrator.
    workflow, principal, ident, backend, _ = extraction_lab(tmp_path, monkeypatch, "client_timeout", 3)

    *retried, last = drains(workflow, principal, ident, backend)

    run = last.run
    assert [(d.run.stage, d.run.blocker) for d in retried] == [("retry_scheduled", TIMEOUT)] * 2
    assert requests(tmp_path, "extract") == 3
    assert (run.stage, run.blocker, run.disposition) == ("finalized", None, Disposition.REVIEW)
    assert run.attempts["parse"] == 3 and "parse" in run.completed_steps
    assert extraction_findings(run) == [f"extraction_given_up:{TIMEOUT}"]
    assert parse_calls(run) == [(n, "failed", "reserved", PARSE_RESERVATION, TIMEOUT) for n in (1, 2, 3)]
    both_ledgers_hold(last, "parse", (1, 2, 3), PARSE_RESERVATION)
    no_canary(run)


# A provider error that is not a timeout is unchanged ---------------------------------------


def test_a_first_pass_transport_error_that_is_no_timeout_still_blocks(tmp_path, monkeypatch):
    # httpx.ReadError is no timeout: PrivateProviderModel still makes it a bare
    # RuntimeError, the child ends `worker_call_failed`, and the run blocks as
    # before this change.
    three_first_passes_fit(monkeypatch)
    adapters = ChildLab(LocalBlobs(tmp_path / "blobs"), first_passes=3)
    workflow, principal, ident, backend = lab(tmp_path, monkeypatch, adapters, "client_read_error")

    *_, last = drains(workflow, principal, ident, backend)

    run = last.run
    assert (run.stage, run.blocker, run.disposition) == (
        "processing_blocked", "external_outcome_unknown", None
    )
    assert requests(tmp_path, "first_pass") == 1
    assert "PRIVATE-READ-ERROR-CANARY" not in run.model_dump_json()


# The agents the three steps build, and the privacy of what they raise -----------------------


def raising(error):
    def respond(messages, info):
        raise error

    return FunctionModel(respond, model_name="local-provider")


class Gateway:
    """The three builders' gateway, with every route's model raising `error`."""

    def __init__(self, error):
        from specimen_digitization.model_gateway import HUGGINGFACE_ROUTES

        self.routes = dict(HUGGINGFACE_ROUTES)
        self.error = error

    def route(self, route_id):
        return self.routes[route_id]

    def model_for(self, route_id):
        return raising(self.error)


def reader_agent(gateway):
    from specimen_digitization.prompts import PromptName, ResolvedPrompt
    from specimen_digitization.transcription import build_literal_transcription_agent

    prompt = ResolvedPrompt(
        name=PromptName.LITERAL_TRANSCRIPTION, text="Transcribe.", requested_label="test",
        served_label=None, version=None, resolution_reason="test",
    )
    return build_literal_transcription_agent(gateway, route_id="handwriting-qwen", prompt=prompt)


def bounded(agent):
    return run_agent_bounded(
        agent, "Synthetic text only", timeout_seconds=30,
        usage_limits=UsageLimits(request_limit=2, total_tokens_limit=16_000),
    )


@pytest.mark.parametrize(
    "error_type", [httpx.ReadTimeout, httpx.ConnectTimeout, httpx.WriteTimeout, httpx.PoolTimeout]
)
def test_the_readers_agent_reports_a_client_timeout_as_a_timeout_with_no_provider_text(error_type):
    with pytest.raises(AdapterFailure) as failure:
        bounded(reader_agent(Gateway(error_type(CANARY))))
    assert (failure.value.code, failure.value.outcome_unknown, failure.value.usage) == (TIMEOUT, True, None)
    assert failure.value.refused is False
    # What crosses: PrivateProviderModel's own TimeoutError, raised from None.
    cause = failure.value.__cause__
    assert type(cause) is TimeoutError and str(cause) == "provider_request_timeout"
    assert cause.__cause__ is None and cause.__suppress_context__
    assert CANARY not in "".join(traceback.format_exception(failure.value))


def test_the_readers_agent_leaves_any_other_provider_error_as_it_was():
    with pytest.raises(RuntimeError) as failure:
        bounded(reader_agent(Gateway(httpx.ReadError(CANARY))))
    assert type(failure.value) is RuntimeError and str(failure.value) == "provider_request_failed"
    assert CANARY not in "".join(traceback.format_exception(failure.value))


def test_an_answering_model_is_unchanged_by_the_wrapper():
    from pydantic_ai.messages import ToolCallPart

    def respond(messages, info):
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "verbatim_text": "LEWIS COLLECTION", "lines": ["LEWIS COLLECTION"], "unreadable_spans": [],
        })])

    class Answering(Gateway):
        def model_for(self, route_id):
            return FunctionModel(respond, model_name="local-provider")

    result = bounded(reader_agent(Answering(None)))
    assert result.output.verbatim_text == "LEWIS COLLECTION"
