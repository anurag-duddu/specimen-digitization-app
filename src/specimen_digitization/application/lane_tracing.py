"""The run's trace (docs/execution/golive/LANE.md, T5a; PLAN 4.5, DoD-5).

A run's first step opens its root span and keeps the root's W3C context on the
run. Every later step, in whatever execution, attaches that context, so the
whole run is one trace.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from datetime import datetime

import logfire

ROOT = "Process specimen run"
STAGE = "Run specimen processing stage"
DECISION = "Specimen queue decision"
TRACEPARENT = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}$")
# `Workflow._step` returns without doing anything for these.
IDLE = {"finalized", "paused", "cancelled", "processing_blocked"}


def steppable(run, now: datetime) -> bool:
    """Whether a step would do work now, so its span says something."""
    if run.stage in IDLE:
        return False
    waiting = run.next_retry_at if run.stage == "retry_scheduled" else None
    if run.blocker == "external_outcome_unknown":
        waiting = run.lease_until
    return not (waiting and datetime.fromisoformat(waiting) > now)


def _profile(run, registry):
    """The profile the run is processed under, as far as the run knows it."""
    rules = run.profile_rules or {}
    if rules.get("profile_id"):
        return rules["profile_id"], rules.get("profile_version")
    selection = run.classification_selection or {}
    if registry is not None and selection.get("collection_id"):
        profile = registry.resolve(selection["collection_id"]).profile
        if profile is not None:
            return profile.id, profile.version
    return run.profile.id, run.profile.version


def _keep_root(run):
    """Keep the root span's context on the run; the id is set once."""
    traceparent = dict(logfire.get_context()).get("traceparent", "")
    match = TRACEPARENT.match(traceparent)
    if match and match.group(1) != "0" * 32:
        run.trace_context = {"traceparent": traceparent}
        run.trace_id = match.group(1)


@contextmanager
def step_span(specimen, step, registry=None):
    """The step's span, under the run's root. The run's first step opens the root."""
    run = specimen.run
    stage = {
        "specimen.id": specimen.id,
        "specimen.run.id": run.id,
        "specimen.processing.stage": step.split(":")[0],
        "specimen.processing.step": step,
    }
    if run.trace_context is None:
        profile_id, profile_version = _profile(run, registry)
        with logfire.span(
            ROOT,
            **{
                "specimen.id": specimen.id,
                "specimen.run.id": run.id,
                "specimen.collection.id": specimen.scope.collection_id,
                "specimen.collection_profile.id": profile_id,
                "specimen.collection_profile.version": profile_version,
            },
        ):
            _keep_root(run)
            with logfire.span(STAGE, **stage):
                yield
        return
    with logfire.attach_context(dict(run.trace_context)):
        with logfire.span(STAGE, **stage):
            yield


def log_decision(run) -> None:
    """The queue decision with its reason codes, inside the finalize step's span."""
    # Plain strings: an enum or a list would reach Logfire JSON-encoded.
    logfire.info(
        DECISION,
        disposition=getattr(run.disposition, "value", run.disposition),
        reason_codes=tuple(str(reason) for reason in run.reasons),
    )
