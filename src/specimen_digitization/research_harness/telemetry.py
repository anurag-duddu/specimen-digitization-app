"""Content-free application spans; diagnostics never own durable state."""

from __future__ import annotations

import re
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from typing import Iterator

import logfire
from opentelemetry.trace import (
    NonRecordingSpan, SpanContext, TraceFlags, get_current_span, use_span,
)

_FIELDS = frozenset({
    "fmnh_ins_number", "collection_code", "country", "province_state", "county",
    "city", "precise_location", "elevation_from_m", "elevation_to_m",
    "elevation_from_ft", "elevation_to_ft", "habitat", "collection_method",
    "date_visited_from", "date_visited_to", "collectors", "verbatim_dts", "taxon",
    "identified_by_irn", "date_identified",
})
_ROLES = frozenset(f"specimen_{role}" for role in (
    "taxonomy", "geography", "temporal", "measurement", "parties", "collection"
))
_EVENTS = frozenset({
    "research", "specialist", "model", "tool", "effect", "checkpoint", "writer",
    "resume", "human_decision", "proposal", "failure",
})
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_OPTIONAL_IDS = frozenset({"attempt_id", "checkpoint_id", "native_run_id"})
_OPTIONAL_DIGESTS = frozenset({
    "effect_id", "prompt_digest", "source_registry_digest", "binding_digest",
})


def _identifier(value: object) -> bool:
    return isinstance(value, str) and _IDENTIFIER.fullmatch(value) is not None


@dataclass(frozen=True, slots=True)
class TraceIdentity:
    specimen_id: str
    job_id: str
    generation: int

    def __post_init__(self) -> None:
        if not _identifier(self.specimen_id) or not _identifier(self.job_id):
            raise ValueError("invalid_trace_identity")
        if type(self.generation) is not int or self.generation < 0:
            raise ValueError("invalid_trace_generation")


@dataclass(frozen=True, slots=True)
class TraceParent:
    trace_id: str
    span_id: str
    trace_flags: int = 1

    def __post_init__(self):
        if (
            not isinstance(self.trace_id, str) or re.fullmatch(r"[0-9a-f]{32}", self.trace_id) is None
            or int(self.trace_id, 16) == 0
            or not isinstance(self.span_id, str) or re.fullmatch(r"[0-9a-f]{16}", self.span_id) is None
            or int(self.span_id, 16) == 0
            or type(self.trace_flags) is not int or self.trace_flags not in {0, 1}
        ):
            raise ValueError("invalid_trace_parent")

    def context(self):
        return SpanContext(int(self.trace_id, 16), int(self.span_id, 16), is_remote=True,
                           trace_flags=TraceFlags(self.trace_flags))


def current_trace_parent() -> TraceParent | None:
    context = get_current_span().get_span_context()
    if not context.is_valid:
        return None
    return TraceParent(format(context.trace_id, "032x"), format(context.span_id, "016x"),
                       int(context.trace_flags) & 1)


class ResearchTrace:
    """Uses the process's approved exporter, with no credential/config discovery."""

    def __init__(self, identity: TraceIdentity, *, parent: TraceParent | None = None) -> None:
        self.identity = identity
        self.parent = parent

    @contextmanager
    def span(self, event: str, **metadata: object) -> Iterator[object]:
        if event not in _EVENTS:
            raise ValueError("invalid_trace_event")
        attributes: dict[str, object] = {
            "specimen.id": self.identity.specimen_id,
            "research.job_id": self.identity.job_id,
            "research.generation": self.identity.generation,
        }
        for key, value in metadata.items():
            valid = (
                key in _OPTIONAL_IDS and _identifier(value)
                or key in _OPTIONAL_DIGESTS and isinstance(value, str)
                and _DIGEST.fullmatch(value) is not None
                or key == "role" and isinstance(value, str) and value in _ROLES
                or key == "field_key" and isinstance(value, str) and value in _FIELDS
                or key == "revision" and type(value) is int and value >= 0
            )
            if not valid:
                raise ValueError("invalid_trace_metadata")
            attributes[f"research.{key}"] = value
        # Do not export original exception messages/tracebacks. Provider text and
        # validation feedback can contain private material even in metadata mode.
        span_name = "research_harness." + event
        failure: BaseException | None = None
        parent_context = (use_span(NonRecordingSpan(self.parent.context()), end_on_exit=False)
                          if self.parent is not None and event == "research" else nullcontext())
        with parent_context:
            with logfire.span(span_name, **attributes) as span:
                try:
                    yield span
                except BaseException as exc:
                    span.set_attribute("research.outcome", "failed")
                    # Exit the SDK context cleanly; re-raise only outside it so the
                    # exporter cannot capture the exception's content automatically.
                    failure = exc
                else:
                    span.set_attribute("research.outcome", "completed")
        if failure is not None:
            raise failure
