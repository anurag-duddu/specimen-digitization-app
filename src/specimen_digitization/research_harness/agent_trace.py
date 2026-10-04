"""What one specialist agent run puts on its Logfire spans, beyond Pydantic AI's own.

Two things are scoped to a single agent run and held in a context variable that the
run's ``SpecialistRunTrace`` capability (agents.py) opens:

* the settled cost of the run's own model requests, recorded by ``EffectModel`` from
  each effect receipt, so the run's spans can carry the application's cost figure
  (Pydantic AI's price lookup has no entry for the Hugging Face route);
* the large texts already recorded in full on an earlier model request of the run.

Each model request carries the whole scoped research input (about 150 KB) again in
``gen_ai.input.messages``. The first request of a run keeps it complete; a later
request of the same run replaces an identical repeat with its first characters and an
explicit ``[truncated N bytes ...]`` marker. Nothing else is capped: the system prompt,
tool definitions, tool calls and results, model output and the agent's own
``pydantic_ai.all_messages`` stay whole, and only a text the run already recorded is
ever shortened. What the model receives is never touched.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from pydantic_ai.models.instrumented import InstrumentationSettings

LOGGER = logging.getLogger(__name__)

# Shorter texts are never worth a marker, and nothing under this size repeats at scale.
REPEATED_INPUT_MIN_BYTES = 4_096
# Characters of the repeated text kept in front of the marker, so the span still says what it was.
REPEATED_INPUT_HEAD_CHARS = 200


@dataclass
class RunTrace:
    """State for one agent run."""

    seen: set[str] = field(default_factory=set)
    # One entry per model request of this run (not of agents it delegated to):
    # the receipt's settled micro-USD, or None when the provider usage cannot price it.
    requests: list[int | None] = field(default_factory=list)

    def record_cost(self, micro_usd: int | None) -> None:
        self.requests.append(micro_usd)

    @property
    def cost_micro_usd(self) -> int:
        return sum(cost for cost in self.requests if cost is not None)

    @property
    def unknown_requests(self) -> int:
        return sum(cost is None for cost in self.requests)

    def cap_repeated_input(self, messages_json: str) -> str:
        """``gen_ai.input.messages`` with a repeated long user text shortened and marked.

        The text of a user message part seen earlier in this run (same bytes) and at least
        REPEATED_INPUT_MIN_BYTES long becomes its first REPEATED_INPUT_HEAD_CHARS characters
        followed by ``[truncated N bytes ...]``, N being the UTF-8 bytes removed. The first
        occurrence is recorded and returned whole; so is every other kind of part.
        """
        try:
            messages = json.loads(messages_json)
            changed = False
            for message in messages:
                if message.get("role") != "user":
                    continue
                for part in message.get("parts", ()):
                    content = part.get("content")
                    if part.get("type") != "text" or not isinstance(content, str):
                        continue
                    encoded = content.encode()
                    if len(encoded) < REPEATED_INPUT_MIN_BYTES:
                        continue
                    digest = hashlib.sha256(encoded).hexdigest()
                    if digest not in self.seen:
                        self.seen.add(digest)
                        continue
                    head = content[:REPEATED_INPUT_HEAD_CHARS]
                    removed = len(encoded) - len(head.encode())
                    part["content"] = (f"{head} ... [truncated {removed} bytes: the same text is recorded "
                                       "in full on an earlier model request of this agent run and in the "
                                       "agent run's pydantic_ai.all_messages]")
                    changed = True
            if not changed:
                return messages_json
            return json.dumps(messages, ensure_ascii=False, separators=(",", ":"))
        except Exception as error:
            # A trace is never worth failing a model request that was paid for: record what
            # pydantic-ai produced. Only the class is logged, never the message (it may quote text).
            LOGGER.debug("trace_input_cap_failed: %s", type(error).__name__)
            return messages_json


_RUN: ContextVar[RunTrace | None] = ContextVar("specimen_specialist_run_trace", default=None)


def current_run() -> RunTrace | None:
    return _RUN.get()


@contextmanager
def run_scope() -> Iterator[RunTrace]:
    """Open the state of one agent run; a delegated run opens its own inside it."""
    run = RunTrace()
    token = _RUN.set(run)
    try:
        yield run
    finally:
        _RUN.reset(token)


def cost_metadata(costs) -> dict[str, int]:
    """Span metadata for the settled costs of some requests (None: not priced).

    ``cost_micro_usd`` is the sum of the priced ones, present when any was priced;
    ``cost_unknown_requests`` counts the unpriced ones, present only when there are some.
    """
    costs = list(costs)
    priced = [cost for cost in costs if cost is not None]
    metadata = {"cost_micro_usd": sum(priced)} if priced else {}
    if len(priced) != len(costs):
        metadata["cost_unknown_requests"] = len(costs) - len(priced)
    return metadata


def annotate_cost(trace, span, costs) -> None:
    """Put the settled cost of some requests on an application span.

    A value the telemetry allowlist refuses (a cost above any possible reservation) and any
    other failure are dropped: a trace attribute never fails a request that was paid for.
    """
    try:
        trace.annotate(span, **cost_metadata(costs))
    except Exception as error:
        LOGGER.debug("trace_cost_annotation_failed: %s", type(error).__name__)


def record_request_cost(micro_usd: int | None) -> None:
    """Called by EffectModel for each completed request; a no-op outside an agent run.

    Never raises: the request has been paid for and its receipt settled.
    """
    try:
        run = _RUN.get()
        if run is not None:
            run.record_cost(micro_usd)
    except Exception as error:
        LOGGER.debug("trace_cost_record_failed: %s", type(error).__name__)


class _CappingSpan:
    """Hands pydantic-ai's ``set_attributes`` call to the span with the input capped."""

    def __init__(self, span, run: RunTrace):
        self._span, self._run = span, run

    def set_attributes(self, attributes):
        attributes = dict(attributes)
        key = "gen_ai.input.messages"
        if isinstance(attributes.get(key), str):
            attributes[key] = self._run.cap_repeated_input(attributes[key])
        self._span.set_attributes(attributes)

    def __getattr__(self, name):
        return getattr(self._span, name)


class RepeatCappedInstrumentationSettings(InstrumentationSettings):
    """The same settings as ``provider_privacy.agent_instrumentation()``, plus the repeat cap.

    Outside a ``run_scope`` (the readers, the first pass, the classifier) it records exactly
    what the base class does.
    """

    def handle_messages(self, input_messages, response, span, parameters=None, *, message_json_cache=None):
        run = _RUN.get()
        super().handle_messages(input_messages, response, span if run is None else _CappingSpan(span, run),
                                parameters, message_json_cache=message_json_cache)
