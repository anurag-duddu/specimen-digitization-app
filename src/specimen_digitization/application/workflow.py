"""Checkpointed application workflow; external engines can dispatch one step at a time."""

from __future__ import annotations
import copy
import hashlib
import json
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Protocol
import logfire
from ..process_logging import log_code
from .domain import (
    AuditEvent,
    Disposition,
    Evidence,
    FieldValue,
    FirstPassDecision,
    Lookup,
    LookupStatus,
    Observation,
    OPERATIONAL,
    Principal,
    ReadingPairComparison,
    Region,
    Run,
    Specimen,
    Transcript,
    ValueState,
)
from .reading_units import ReadingUnits
from .collection_runtime import (
    application_registry,
    SyntheticClassifier,
    classify_and_select,
    quality_check,
)
from .evidence_runtime import execute_phase, refresh_review_evidence, apply_phase_gate
from .evidence_runtime import plan_authorities, authority_query, harness_spec
from .evidence_harness import (
    HarnessRunner,
    ToolCall,
    ToolReceipt,
    BudgetUsage as HarnessUsage,
)
from .region_pixels import region_png
from .integrity import EvidenceIntegrityError, verify_evidence
from .lookup import PLACE_FIELDS, taxonomy_lookup
from .policy import finalize
from .storage import BlobStore, Repository, digest
from .reliability import (
    AdapterFailure,
    ReadingStopped,
    extraction_failure_is_recoverable,
    failure_is_retryable,
    first_pass_failure_is_recoverable,
    model_read_is_recoverable,
    reader_failure_is_recoverable,
    retry_delay,
)


LOGGER = logging.getLogger(__name__)

# Field research (field_research/step.py): one external, billable step that
# replaces plan..finalize for a run whose profile names a harness route, when
# SPECIMEN_RESEARCH_HARNESS=fields mounts it as `Workflow.field_research`.
FIELD_RESEARCH = "field_research"
# A run field research has completed reaches the handover again: the clearance
# rules only, nothing researched, external or paid (FieldResearchStep.recheck).
FIELD_RECHECK = "field_research_recheck"


def current_human_location_fields(repository, specimen) -> set[str]:
    """Current ordinary field decisions, verified against immutable save audits.

    Legacy decisions predate field locks. Reuse the existing review proof
    reader rather than infer a human choice from a value or an authority ID.
    """
    from .human_field_carry import _pass, _proofs, _latest
    from ..field_research.location_reassessment import FIELDS

    reader, _ = _pass(repository, None)
    proofs = [proof for proof in _proofs(reader, specimen)
        if proof.event.action in {"review_field", "review_authority_resolution"}
        and proof.event.after.get("field_key") in FIELDS]
    protected = set()
    for key, (_, proof, original) in _latest(reader, specimen, proofs).items():
        if original.run.id != specimen.run.id:
            continue
        field = original.run.fields.get(key)
        if (not proof.event.reason.strip() or field is None
                or specimen.run.fields.get(key) != field):
            raise ValueError("Current human location decision could not be verified")
        if proof.event.action == "review_field":
            declared = {name: proof.event.after[name] for name in FieldValue.model_fields
                if name in proof.event.after}
            matches = FieldValue.model_validate(declared) == field
        else:
            matches = (proof.event.after.get("authority_id") == field.authority_id
                and proof.event.after.get("value") == field.normalized
                and proof.event.after.get("evidence_ids") == field.evidence_ids)
        if not matches:
            raise ValueError("Current human location decision could not be verified")
        protected.add(key)
    return protected


def can_reassess_locations(run: Run, protected=(), *, specimen=None) -> bool:
    """An explicit, bounded reassessment of a completed location hierarchy.

    This does not repin the profile, repeat readings or replenish any budget.
    Settled records continue to use ordinary Retry's rules-only recheck.
    """
    from .reliability import has_active_lease
    from .location_reassessment_authorization import authorization_for
    from ..field_research.location_reassessment import eligible_keys

    if (
        FIELD_RESEARCH not in run.completed_steps
        or run.stage != "finalized"
        or run.disposition != Disposition.REVIEW
        or run.blocker is not None
        or has_active_lease(run)
        or "evidence_pilot" in run.dependencies
        or (run.attempts.get(FIELD_RESEARCH, 0) >= run.profile.execution.max_attempts
            and authorization_for(run, specimen) is None)
    ):
        return False
    eligible = eligible_keys(run) - set(protected)
    unsettled = {ValueState.UNRESOLVED, ValueState.AMBIGUOUS, ValueState.UNKNOWN}
    return any(key in eligible and value.state in unsettled for key, value in run.fields.items())


def requeue_location_reassessment(run: Run, protected=(), *, specimen=None) -> list[str]:
    """Queue one location-only pass, leaving fields and accounting untouched."""
    from ..field_research.location_reassessment import eligible_keys
    from .location_reassessment_authorization import authorization_for

    if not can_reassess_locations(run, protected, specimen=specimen):
        return []
    fields = sorted(eligible_keys(run) - set(protected))
    run.dependencies["location_reassessment"] = {
        "attempt": run.attempts.get(FIELD_RESEARCH, 0) + 1,
        "fields": fields,
        "protected": sorted(protected),
    }
    if authorization := authorization_for(run, specimen):
        run.dependencies["location_reassessment"]["authorization_id"] = authorization
    run.completed_steps = [step for step in run.completed_steps if step != FIELD_RESEARCH]
    return fields


def requeue_completed_field_research(run: Run) -> bool:
    """Make an explicit retry of a reviewed field-research run research again.

    The normal handover after completed field research is rules-only recheck:
    reviewer decisions and approvals must not start another paid harness pass.
    When an operator explicitly retries a completed field-research run that is
    still in Needs human review because automatic fields remain unsettled, remove
    the completed marker so the next workflow step re-enters ``field_research``
    on the unresolved fields instead of ``field_research_recheck``.
    """
    if (
        FIELD_RESEARCH not in run.completed_steps
        or run.disposition != Disposition.REVIEW
        or run.blocker is not None
        or run.dependencies.get("human_review_field_locks")
        or run.attempts.get(FIELD_RESEARCH, 0) >= run.profile.execution.max_attempts
    ):
        return False
    unsettled = {ValueState.UNRESOLVED, ValueState.AMBIGUOUS, ValueState.UNKNOWN}
    if not any(value.state in unsettled for value in run.fields.values()):
        return False
    run.completed_steps = [step for step in run.completed_steps if step != FIELD_RESEARCH]
    return True


# A reading whose worker stopped after saving its intent and before saving its
# result (Workflow._settle_lost_reading).
LOST_READING = "reading_result_lost"
# The same for an ordinary first pass (Workflow._settle_lost_reading).
LOST_FIRST_PASS = "first_pass_result_lost"
# The same for the organiser's extraction, parse's model call.
LOST_EXTRACTION = "extraction_result_lost"
# An ordinary first pass or extraction whose attempts are used up when its step
# comes round again: given up on unsent (Workflow._step).
ATTEMPTS_USED = "max_attempts_used"
# A run's own budgets that leave no room for another call. At an ordinary first
# pass the run gives the comparison up instead of blocking (HARNESS.md 3).
UNAFFORDABLE = frozenset(
    {
        "cost_budget_exhausted",
        "token_budget_exhausted",
        "external_call_budget_exhausted",
        "active_time_budget_exhausted",
    }
)
# The run's own limits other than money. Field research the run has no room
# for under one of them is given up on unsent, and the record goes to review
# (Workflow._give_up_field_research); the drain recovers a run an earlier
# worker left blocked there by one (Workflow.recover_blocked). The cost
# ceiling and the program's allowance are limits on money: they still block
# (FIELD_RESEARCH.md 8).
RESEARCH_LIMITS = frozenset(
    {
        "step_budget_exhausted",
        "token_budget_exhausted",
        "external_call_budget_exhausted",
        "active_time_budget_exhausted",
    }
)
# Blockers of an ordinary first pass that the drain recovers on its own
# (Workflow.recover_blocked). The two lane codes are lane_worker's RUN_STALLED
# and HANDOVER_STALLED.
RECOVERABLE_FIRST_PASS_BLOCKERS = UNAFFORDABLE | {
    "external_outcome_unknown",
    "pinned_model_route_unavailable",
    "lane_run_not_progressing",
    "lane_handover_without_progress",
}
RECOVERABLE_FIRST_PASS_PREFIXES = ("retry_budget_exhausted:", "provider_circuit:")
# A model read whose answer stayed malformed after its output retry: given up
# on when the run is recovered (a run blocked by it before 2026-10-12).
MALFORMED_ANSWER = "model_malformed_response"
# What each unknown outcome of an ordinary first pass or extraction is, saved
# with the run as {"<step>:<attempt>": kind} in run.dependencies (2026-10-12).
# Every save of such an unknown outcome writes one (Workflow._step):
# UNANSWERED when the call's intent is saved (a worker that stops then leaves
# the call unanswered: asking again can mend it), HELD when the step saves a
# result the parent could not accept (an invalid child result, mismatched
# fields, a child whose cleanup is not confirmed, an unexpected exception: it
# stays for a person). An unknown attempt with no kind was saved by code
# before this record existed (LEGACY_UNKNOWN).
UNKNOWN_OUTCOME_KINDS = "unknown_outcome_kinds"
UNANSWERED, HELD = "unanswered", "held"
# The rule recorded with an automatic recovery of such a legacy row.
LEGACY_UNKNOWN = "legacy_unknown_recovered"


def unknown_key(run, step) -> str:
    return f"{step}:{run.attempts.get(step, 0)}"


def _keep_kinds(run, keep) -> None:
    kinds = {
        key: kind
        for key, kind in run.dependencies.get(UNKNOWN_OUTCOME_KINDS, {}).items()
        if keep(key)
    }
    if kinds:
        run.dependencies[UNKNOWN_OUTCOME_KINDS] = kinds
    else:
        run.dependencies.pop(UNKNOWN_OUTCOME_KINDS, None)


def _settled(step, attempt):
    """A key of the step whose attempt is at or before ``attempt``: settled once
    that attempt is (an attempt starts only after the one before it ended)."""

    def match(key):
        name, _, number = key.rpartition(":")
        return name == step and number.isdigit() and int(number) <= attempt

    return match


def mark_unknown_outcome(run, step, kind) -> None:
    """Record what the step's current attempt's unknown outcome is. Earlier
    attempts of the step are settled by now: their kinds go (``_settled``)."""
    attempt = run.attempts.get(step, 0)
    settled = _settled(step, attempt - 1)
    _keep_kinds(run, lambda key: not settled(key))
    run.dependencies[UNKNOWN_OUTCOME_KINDS] = {
        **run.dependencies.get(UNKNOWN_OUTCOME_KINDS, {}),
        unknown_key(run, step): kind,
    }


def resolve_unknown_outcome(run, step) -> None:
    """Drop the kinds of the step's current attempt and of every earlier one once
    its outcome is known (completed, a known failure, given up, settled as lost).
    The kinds live in the run's dependencies only while an attempt is
    unresolved, so they add no drift of their own to the pins the append-once
    pipeline-run row holds (#146)."""
    settled = _settled(step, run.attempts.get(step, 0))
    _keep_kinds(run, lambda key: not settled(key))


def resolve_step_unknown_outcomes(run, step) -> None:
    """Drop every kind of the step's attempts: a person's reconcile settles the
    unknown outcome it clears (api.py, action "reconcile")."""
    _keep_kinds(run, lambda key: key.rpartition(":")[0] != step)


def end_step(run, step) -> None:
    """Complete the step. Every step that ends passes here, and a step that has
    ended has no unresolved unknown outcome: every kind of it goes."""
    run.completed_steps.append(step)
    resolve_step_unknown_outcomes(run, step)


def give_up_the_extraction(run, code) -> None:
    """Give the organiser's extraction up (``harness.give_up_extraction``). Its
    call is over, though parse still runs without it: every kind of parse goes."""
    from .harness import give_up_extraction

    give_up_extraction(run, code)
    resolve_step_unknown_outcomes(run, "parse")


def unknown_outcome_kind(run, step) -> str | None:
    return run.dependencies.get(UNKNOWN_OUTCOME_KINDS, {}).get(unknown_key(run, step))


def unknown_outcome_recoverable(run, step) -> bool:
    """Whether a first pass's or an extraction's saved ``external_outcome_unknown``
    may be made due again (``Workflow.recover_blocked``, and the step's
    lost-attempt settlement).

    A kind written by this code decides: an ``UNANSWERED`` call may be asked
    again, a ``HELD`` result never is. An attempt with no kind is a legacy row:
    the code before 2026-10-12 saved a provider's HTTP 5xx and an invalid child
    result alike, so its cause cannot be read from the run. Logfire (2026-10-12
    13:00Z-13:34Z) shows the known stuck rows were HTTP 504s, and recovery is
    bounded (max_attempts, three automatic recoveries, each attempt reserved in
    full under the run's limit) and ends at worst in review, so a legacy row is
    recovered and recorded as ``LEGACY_UNKNOWN``.
    """
    return unknown_outcome_kind(run, step) in {None, UNANSWERED}


# Each recovery is recorded here; a step is recovered at most this many times.
AUTOMATIC_RECOVERIES = "automatic_recoveries"
MAX_AUTOMATIC_RECOVERIES = 3


class OperationalBlock(RuntimeError):
    """Sanitized actionable code, never an exception containing provider credentials."""


def _http_status(*errors):
    """The HTTP status a provider error keeps: a number, never its body."""
    for error in errors:
        status = getattr(error, "status_code", None)
        if type(status) is int:
            return status
    return None


def _log_step_failure(run, step, branch, *, error=None, **fields):
    """Write one WARNING line for a failed step, so the worker's process log shows it.

    The stored blocker alone does not say which branch failed or why (an ambiguous
    provider failure and a deadline overrun both become ``external_outcome_unknown``).
    The line carries the run id, step, branch, attempt and codes and classes only:
    never a prompt, a response, a provider body or label text. Every value is a
    number, an identifier, or a string that ``log_code`` has checked.

    The cause class and HTTP status are only present when the provider error was
    raised in this process. Model calls run in an isolated child process and the
    parent rebuilds the ``AdapterFailure`` from JSON without a cause, so for those
    steps both read ``-`` and the code, status and branch carry the diagnosis.

    This runs inside the failure handlers: it must never change what the step does,
    so any error while describing the failure is reduced to a bare line.
    """
    try:
        if error is not None:
            cause = error.__cause__
            fields["error_class"] = type(error).__name__
            fields["cause_class"] = None if cause is None else type(cause).__name__
            fields["http_status"] = _http_status(error, cause)
        values = {
            "run": run.id,
            "step": step,
            "branch": branch,
            **fields,
            "attempt": run.attempts.get(step, 0),
        }
        LOGGER.warning(
            "Specimen step failed: %s",
            " ".join(
                f"{key}={'-' if value is None else value}"
                for key, value in values.items()
            ),
        )
    except Exception:  # noqa: BLE001 - describing a failure must not change the step
        LOGGER.warning("Specimen step failed: branch=%s fields=unavailable", branch)


class PipelineAdapters(Protocol):
    def segment(self, specimen: Specimen) -> list[Region]: ...
    def transcribe(
        self, specimen: Specimen, region: Region, route: str
    ) -> Observation: ...
    def first_pass(
        self, specimen: Specimen, region: Region, readings: list[Observation]
    ) -> FirstPassDecision: ...
    def first_pass_units(
        self, specimen: Specimen, region: Region, readings: list[Observation]
    ) -> tuple[FirstPassDecision, ReadingUnits]: ...
    def lookup(self, name: str) -> Lookup: ...


class Workflow:
    # The field research step's runner (field_research.step.FieldResearchStep),
    # mounted by research_harness.workflow_bridge; None keeps the ordinary chain.
    field_research = None

    def __init__(
        self,
        repository: Repository,
        blobs: BlobStore,
        adapters: PipelineAdapters,
        *,
        clock=None,
        monotonic=None,
        random_value=None,
        profile_registry=None,
        risk_registry=None,
        classifier=None,
        authority_tools=None,
        authority_cost_reservations=None,
        admission=None,
        retained_cost=None,
        reserve_retained_cost=None,
        settle_retained_cost=None,
    ):
        self.repository, self.blobs, self.adapters = repository, blobs, adapters
        self.admission = admission
        # Other durable stages can retain paid/unknown liabilities on this run.
        # Consult them before sending, without duplicating them in ordinary usage.
        self.retained_cost = retained_cost
        self.reserve_retained_cost = reserve_retained_cost
        self.settle_retained_cost = settle_retained_cost
        if hasattr(repository, "graph_blobs") and repository.graph_blobs is None:
            repository.graph_blobs = blobs
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.monotonic = monotonic or time.monotonic
        self.random_value = random_value
        self.profile_registry = profile_registry
        self.risk_registry = risk_registry
        self.classifier = (
            classifier
            if classifier is not None
            else getattr(adapters, "classifier", None)
        )
        self.authority_tools = (
            authority_tools
            if authority_tools is not None
            else getattr(adapters, "authority_tools", {})
        )
        self.authority_cost_reservations = (
            authority_cost_reservations
            if authority_cost_reservations is not None
            else getattr(adapters, "authority_cost_reservations", {})
        )

    def authority_pins(self):
        return {
            key: {
                "version": tool.version,
                "registry_sha256": digest(tool.registry.model_dump(mode="json"))
                if hasattr(tool, "registry")
                else None,
                "connection_sha256": digest(tool.connection.model_dump(mode="json"))
                if getattr(tool, "connection", None)
                else None,
                "reserved_cost_microunits": self.authority_cost_reservations.get(key),
            }
            for key, tool in self.authority_tools.items()
        }

    def step(self, principal: Principal, specimen_id: str) -> Specimen:
        with logfire.span(
            "Process specimen checkpoint",
            specimen_id=specimen_id,
            organization_id=principal.scope.organization_id,
            collection_id=principal.scope.collection_id,
        ):
            return self._step(principal, specimen_id)

    def _step(self, principal: Principal, specimen_id: str) -> Specimen:
        specimen = self.repository.get(principal.scope, specimen_id)
        run = specimen.run
        if "evidence_pilot" in run.dependencies and not getattr(
            self, "evidence_pilot", False
        ):
            raise OperationalBlock("evidence_pilot_worker_required")
        if run.stage in {"finalized", "paused", "cancelled", "processing_blocked"}:
            return specimen
        revision = specimen.version
        from .human_field_carry import KEY as CARRY_KEY, REGIONS as CARRY_REGIONS, verify as verify_carries
        if run.dependencies.get(CARRY_KEY) or any(e.kind == "ordinary_human_field_carry" for e in run.evidence):
            try:
                # specimen is still the authoritative persisted base here; later
                # worker staging must not be compared wholesale to this snapshot.
                verify_carries(self.repository, specimen, self.blobs)
            except (ValueError, AttributeError, KeyError, OSError):
                run.blocker = "preserved_human_field_provenance_unavailable"
                run.stage = "processing_blocked"
                return self.repository.save(principal, specimen, revision,
                    f"human-carry-block:{revision}", digest({"human_carry_block": revision}))
        if self.admission is not None:
            self.admission.admit(specimen)
        if run.stage == "retry_scheduled":
            if (
                run.next_retry_at
                and datetime.fromisoformat(run.next_retry_at) > self.clock()
            ):
                return specimen
            # An unknown effect is never cleared by a scheduling timestamp.
            if run.blocker != "external_outcome_unknown":
                run.blocker = None
                run.next_retry_at = None
        step = self.next_step(run)
        if (
            step == "plan"
            and self.field_research is not None
            and self.field_research.handles(run)
        ):
            step = FIELD_RECHECK if FIELD_RESEARCH in run.completed_steps else FIELD_RESEARCH
        ordinary_first_pass = step.startswith("first_pass:") and first_pass_failure_is_recoverable(
            run, step
        )
        if ordinary_first_pass:
            from .first_pass import repin_first_pass_route

            # A pin whose provider the registry moved, same model and price: the
            # move is saved with the step's next save (HARNESS.md 3, Failures).
            repin_first_pass_route(run, self.clock())
        from .harness import extraction_given_up

        # parse's model call (the organiser's extraction), while the run has not
        # given it up; once given up, parse runs without it (HARNESS.md 3).
        extracting = (
            step == "parse"
            and hasattr(self.adapters, "extract")
            and not extraction_given_up(run)
        )
        ordinary_extraction = extracting and extraction_failure_is_recoverable(run, step)
        # Persist intent before network/model work. Crash with intent but no result is
        # blocked for explicit replay: provider calls may not support deduplication.
        if run.blocker == "external_outcome_unknown":
            if (
                run.lease_until
                and datetime.fromisoformat(run.lease_until) > self.clock()
            ):
                return specimen
            if (
                (
                    step.startswith("transcribe:")
                    and reader_failure_is_recoverable(run, step)
                )
                or (
                    (ordinary_first_pass or ordinary_extraction)
                    and unknown_outcome_recoverable(run, step)
                )
            ) and run.attempts.get(step, 0) >= 1:
                # A reading or an ordinary first pass is the exception: asking
                # again is safe (G6; reliability.first_pass_failure_is_recoverable).
                return self._settle_lost_reading(principal, specimen, revision, step)
            run.stage = "processing_blocked"
            return self.repository.save(
                principal,
                specimen,
                revision,
                f"unknown:{revision}",
                digest({"unknown": step}),
            )
        if (
            (ordinary_first_pass or ordinary_extraction)
            and run.attempts.get(step, 0) >= run.profile.execution.max_attempts
        ):
            # Its attempts are used up, as the saved intent of the last one
            # records. Its result was then lost (the active graph's size limit
            # reloads that intent, without the give-up the attempt had
            # recorded), or a person retried a block on its last attempt: it
            # is given up on unsent, never sent beyond max_attempts. Nothing
            # is reserved or released; earlier attempts keep what they hold.
            if ordinary_first_pass:
                return self._give_up_first_pass(principal, specimen, revision, step, ATTEMPTS_USED)
            return self._give_up_extraction_unsent(principal, specimen, revision, step, ATTEMPTS_USED)
        external = (
            step.startswith(("transcribe:", "first_pass:"))
            or step in {"segment", "lookup", FIELD_RESEARCH}
            or step.startswith("authority:")
            or extracting
            or (
                step == "classify"
                and self.classifier is not None
                and getattr(self.classifier, "external", True)
            )
        )
        policy = run.profile.execution
        effect_timeout = policy.effect_timeout_for_step(step)
        external_weight = (
            2
            if (step.startswith(("transcribe:", "first_pass:")) or step == "parse")
            and not run.profile.synthetic
            else 1
        )
        billable = external and (
            step.startswith(("transcribe:", "first_pass:"))
            or step in {"parse", "segment", "classify", FIELD_RESEARCH}
        )
        reservation_tokens = 16000 if billable and not run.profile.synthetic else 0
        from .lane_reservations import step_reservation

        cost = 0 if run.profile.synthetic or not billable else step_reservation(run, step)
        retained_cost = 0
        retained_cost_issue = None
        if billable and not run.profile.synthetic and self.retained_cost is not None:
            try:
                retained_cost = self.retained_cost(principal, specimen)
                if type(retained_cost) is not int or retained_cost < 0:
                    raise ValueError("invalid retained cost")
            except Exception:
                # A missing research state returns zero; an unreadable or malformed
                # state cannot establish headroom for another paid call.
                retained_cost_issue = "research_budget_state_unavailable"
        if (
            step == FIELD_RESEARCH
            and billable
            and not run.profile.synthetic
            and policy.approved_cost_limit_micros is not None
        ):
            # Field research reserves the run's whole remaining headroom: its
            # meter never lets the experts' calls together cross it, and the
            # step settles to what they spent (FIELD_RESEARCH.md, Budget).
            cost = max(
                0,
                policy.approved_cost_limit_micros
                - run.usage.reserved_cost_micros
                - retained_cost,
            )
            # Never more than the program's allowance has left (when that fits
            # one expert request): the step's meter has this as its cap.
            cost = self.field_research.reservation(self, principal, specimen, cost)
        if billable and not run.profile.synthetic and cost:
            from .tenant_budget import recorded_micros

            # An attempt that already holds on a monthly cap's ledger was never
            # sent (a refusal later in the chain blocked it): it reserves the
            # recorded amount again, so its holds replay (TENANT_BUDGETS.md).
            cost = recorded_micros(run, step) or cost
        # The limits on money, in the order they block: the cost settings, the
        # saved cost totals, then the run's cost ceiling.
        money_issue = None
        if (
            billable
            and not run.profile.synthetic
            and (cost is None or policy.approved_cost_limit_micros is None)
        ):
            money_issue = "approved_cost_budget_unavailable"
        elif retained_cost_issue:
            money_issue = retained_cost_issue
        elif (
            cost is not None
            and policy.approved_cost_limit_micros is not None
            and run.usage.reserved_cost_micros + retained_cost + cost
            > policy.approved_cost_limit_micros
        ):
            money_issue = "cost_budget_exhausted"
        from .location_reassessment_authorization import authorized_queued_attempt

        issue = None
        if (step == FIELD_RESEARCH and run.attempts.get(step, 0) >= policy.max_attempts
                and not authorized_queued_attempt(specimen)):
            issue = ATTEMPTS_USED
        elif run.usage.steps >= policy.max_steps:
            issue = "step_budget_exhausted"
        elif (
            external
            and run.usage.external_calls + external_weight > policy.max_external_calls
        ):
            issue = "external_call_budget_exhausted"
        elif run.usage.reserved_tokens + reservation_tokens > policy.max_tokens:
            issue = "token_budget_exhausted"
        elif (
            run.usage.active_seconds
            + run.usage.reserved_active_seconds
            + (effect_timeout if external else 0)
            > policy.max_active_seconds
        ):
            issue = "active_time_budget_exhausted"
        elif money_issue:
            issue = money_issue
        if issue is None and billable and not run.profile.synthetic and self.reserve_retained_cost is not None:
            try:
                self.reserve_retained_cost(principal, specimen, step, cost)
            except OperationalBlock as error:
                issue = str(error)
        if (issue in RESEARCH_LIMITS or issue == ATTEMPTS_USED) and step == FIELD_RESEARCH:
            # Money comes first: a run whose cost ceiling, cost settings or
            # totals, monthly cap or program allowance would refuse this attempt
            # keeps that block. The caps' ledgers and the allowance are only
            # read here (tenant_budget.admits, lane_allowance.admits), never
            # reserved on.
            from .lane_allowance import admits
            from .tenant_budget import admits as tenant_budget_admits

            money_issue = money_issue or (
                tenant_budget_admits(self.repository, principal, specimen, step, cost, self.clock)
                or admits(self.repository, principal, specimen, cost, self.clock)
                if billable and not run.profile.synthetic
                else None
            )
            if money_issue:
                issue = money_issue
            else:
                # No room for another attempt under the run's own limits other
                # than money: given up on unsent, the fields it could not check
                # for a person. No model call, nothing reserved.
                return self._give_up_field_research(principal, specimen, revision, issue)
        if issue in UNAFFORDABLE and ordinary_first_pass:
            # No room for another comparison under the run's limits: give it up
            # unsent, as a first pass whose last attempt failed is given up on.
            return self._give_up_first_pass(principal, specimen, revision, step, issue)
        if issue in UNAFFORDABLE and ordinary_extraction:
            # The same for the organiser's extraction: given up on unsent, and
            # the next step runs parse without it.
            return self._give_up_extraction_unsent(principal, specimen, revision, step, issue)
        if issue:
            run.blocker = issue
            run.stage = "processing_blocked"
            run.disposition = None
            return self.repository.save(
                principal,
                specimen,
                revision,
                f"budget:{revision}",
                digest({"budget": issue}),
            )
        circuit = permit = None
        circuit_failure = None
        circuit_retry_after = None
        # Field research calls several providers and sources, each with its own
        # retries; no one provider circuit describes it. Its outages block the
        # run with a scheduled retry instead (schedule_retry below).
        if external and step != FIELD_RESEARCH:
            from .circuit_runtime import circuit_for

            circuit, circuit_key = circuit_for(self, principal, run, step)
            admission = circuit.admit(circuit_key, policy.lease_seconds)
            run.circuit = {
                "storage_key": circuit_key.storage_key,
                "provider": circuit_key.provider,
                "admission": admission.model_dump(mode="json"),
            }
            if admission.status != "permitted":
                run.blocker = "provider_circuit:" + admission.reason
                run.disposition = None
                run.stage = (
                    "retry_scheduled" if admission.retry_at else "processing_blocked"
                )
                run.next_retry_at = (
                    admission.retry_at.isoformat() if admission.retry_at else None
                )
                return self.repository.save(
                    principal,
                    specimen,
                    revision,
                    f"circuit:{revision}",
                    digest(run.circuit),
                )
            permit = admission.token
        if billable and not run.profile.synthetic:
            from .lane_allowance import reserve_step
            from .tenant_budget import reserve_step as reserve_tenant_budget

            # The program's allowance (LANE.md T2b), once the circuit admits the
            # call, after any monthly cap of the organization or the collection
            # (TENANT_BUDGETS.md): with none set, only the caps are read.
            allowance_issue = reserve_tenant_budget(
                self.repository, principal, specimen, step, cost, self.clock
            ) or reserve_step(
                self.repository, principal, specimen, step, cost, self.clock
            )
            if allowance_issue:
                run.blocker = allowance_issue
                run.stage = "processing_blocked"
                run.disposition = None
                return self.repository.save(
                    principal,
                    specimen,
                    revision,
                    f"allowance:{revision}",
                    digest({"allowance": allowance_issue}),
                )
        run.usage.steps += 1
        if external:
            run.usage.external_calls += external_weight
            run.usage.reserved_tokens += reservation_tokens
            run.usage.reserved_cost_micros += cost or 0
            run.usage.reserved_active_seconds += effect_timeout
            if run.profile.synthetic:
                run.usage.actual_cost_micros = 0
            run.blocker = "external_outcome_unknown"
            run.lease_until = (
                self.clock() + timedelta(seconds=policy.lease_seconds)
            ).isoformat()
            run.attempts[step] = run.attempts.get(step, 0) + 1
            if ordinary_first_pass or ordinary_extraction:
                # Until its result is saved, this call is unanswered.
                mark_unknown_outcome(run, step, UNANSWERED)
            specimen = self.repository.save(
                principal,
                specimen,
                revision,
                f"intent:{revision}",
                digest({"intent": step}),
            )
            revision = specimen.version
            run = specimen.run
        reserved = specimen.model_copy(deep=True)
        started = self.monotonic()
        previous_tokens = sum(
            o.input_tokens + o.output_tokens for o in run.observations
        )
        # Set once the step's model or lookup call has returned: a later failure
        # is deterministic and its outcome known (issue #80, HARNESS.md 2).
        effect_settled = False
        # A SAM 3 failure keeps its retry even past the budget (below). So does
        # a reader or an ordinary first-pass comparison: neither publishes a
        # result itself. A late answer is retained and a transient failure is
        # retried with its old cost reservation still held.
        # The organiser's extraction is such a read too.
        repeatable = model_read_is_recoverable(run, step) and (
            step != "parse" or extracting
        )
        # The code a reading that gave no observation, or a first pass that was
        # given up on, failed with, for its record (lane_costs.record_step).
        reading_failure = None
        # The code of a model call the provider refused before any work (an HTTP
        # 429 to its first request): it is recorded at no cost (lane_costs).
        refusal = None
        # The tokens the provider reported for the step's model call: a failed
        # call's (reliability.reported_usage), or parse's extraction. Recorded at
        # what they cost (lane_costs.record_step); None stays reserved in full.
        call_usage = None
        observed = len(run.observations)
        # The run's fields, evidence and usage before parse touches them; put
        # back when parse does not end (below).
        parse_base = None
        try:
            if step == "pin_dependencies":
                retained_carries = copy.deepcopy(run.dependencies.get(CARRY_KEY, {}))
                retained_regions = copy.deepcopy(run.dependencies.get(CARRY_REGIONS))
                pinned = (
                    self.adapters.pin_dependencies(run)
                    if hasattr(self.adapters, "pin_dependencies")
                    else {
                        "adapter": type(self.adapters).__name__,
                        "synthetic": run.profile.synthetic,
                    }
                )
                # Checked before the pins replace anything: a block saves the
                # run, and must keep the carries and the regions lineage intact.
                if (CARRY_KEY in pinned and pinned[CARRY_KEY] != retained_carries
                        or CARRY_REGIONS in pinned):
                    raise OperationalBlock("preserved_human_field_provenance_unavailable")
                run.dependencies = pinned
                if retained_carries:
                    run.dependencies[CARRY_KEY] = retained_carries
                if retained_regions is not None:
                    run.dependencies[CARRY_REGIONS] = retained_regions
                if self.classifier is not None and hasattr(self.classifier, "pin"):
                    run.dependencies["classifier"] = self.classifier.pin(run)
                run.dependencies["authority_pins"] = self.authority_pins()
                run.dependencies["profile_snapshot_sha256"] = digest(
                    run.profile_snapshot
                )
                run.dependencies["profile_registry_version"] = (
                    run.profile_registry_version
                )
            elif step == "classify":
                registry = self.profile_registry or application_registry(
                    run.profile.synthetic
                )
                classifier = self.classifier or (
                    SyntheticClassifier(self.blobs) if run.profile.synthetic else None
                )
                if classifier is not None and hasattr(classifier, "bind"):
                    classifier = classifier.bind(specimen, registry)
                if run.profile.synthetic and run.classification_selection is None:
                    run.classification_selection = {
                        "collection_id": registry.nodes[0].id,
                        "actor_id": principal.user_id,
                        "reason": "Explicit synthetic fixture intake selection",
                    }
                issue = classify_and_select(
                    specimen, registry, classifier, self.blobs, self.risk_registry
                )
                if issue:
                    raise OperationalBlock("classification_review_required:" + issue)
                # Resolve prompts again for the selected immutable profile, before inference.
                run.completed_steps = [
                    s for s in run.completed_steps if s != "pin_dependencies"
                ]
            elif step == "quality_check":
                issue = quality_check(specimen, self.blobs)
                if issue:
                    raise OperationalBlock(issue)
            elif step == "segment":
                run.regions = self.adapters.segment(specimen)
                for region in run.regions:
                    if (
                        region.asset_id != specimen.asset.id
                        or region.x + region.width > specimen.asset.width
                        or region.y + region.height > specimen.asset.height
                    ):
                        raise OperationalBlock("segmentation_geometry_invalid")
                run.coverage_confirmed = run.profile.synthetic
                if not run.profile.synthetic:
                    from .label_coverage import check_run
                    check_run(specimen)
            elif step.startswith("transcribe:"):
                _, region_id, route = step.split(":", 2)
                region = next(r for r in run.regions if r.id == region_id)
                try:
                    observation = self.adapters.transcribe(specimen, region, route)
                except ReadingStopped as stopped:
                    if not reader_failure_is_recoverable(run, step):
                        # An evidence-pilot reader keeps what a child that ended
                        # without an answer always was: an unknown outcome.
                        raise OperationalBlock("external_outcome_unknown") from stopped
                    # A reading stopped by its token limits (#153) is not asked
                    # again: the step completes with no observation, and the
                    # region stays one reading short.
                    reading_failure = stopped.code
                    call_usage = stopped.usage
                    _log_step_failure(
                        run,
                        step,
                        "reading_stopped",
                        error=stopped,
                        code=log_code(stopped.code),
                    )
                    observation = None
                except AdapterFailure as failure:
                    if not self.reading_has_no_attempt_left(run, step, failure):
                        raise  # Retried, or a block that names its cause (below).
                    # The last attempt failed too (a reader's failure is known,
                    # reliability.reader_failure_is_recoverable): end the reading
                    # with no observation, and the record goes to review.
                    reading_failure = failure.code
                    refusal = failure.code if failure.refused else None
                    call_usage = failure.usage
                    circuit_failure = failure.status.value
                    circuit_retry_after = failure.retry_after_seconds
                    _log_step_failure(
                        run,
                        step,
                        "reading_given_up",
                        error=failure,
                        status=failure.status.value,
                        code=log_code(failure.code),
                    )
                    observation = None
                if observation is not None:
                    if observation.region_id != region.id or observation.route_id != route:
                        raise OperationalBlock("observation_contract_invalid")
                    run.observations.append(observation)
            elif step.startswith("first_pass:"):
                region = next(r for r in run.regions if r.id == step.split(":", 1)[1])
                readings = [o for o in run.observations if o.region_id == region.id]
                from .first_pass import (
                    UNITS,
                    UNRESOLVED_VERDICTS,
                    g19_pick,
                    give_up,
                    is_material,
                )
                from .reading_units import problems as unit_problems

                units_path, units = run.first_pass_path == UNITS, None
                try:
                    if units_path:
                        decision, units = self.adapters.first_pass_units(
                            specimen, region, readings
                        )
                    else:
                        decision = self.adapters.first_pass(specimen, region, readings)
                except AdapterFailure as failure:
                    if not self.first_pass_has_no_attempt_left(run, step, failure):
                        raise  # Retried, or a block that names its cause (below).
                    # The last attempt failed too, with a known failure that is
                    # retried (a rate limit, a timeout, a provider error): end
                    # the first pass with no decision, as a reader is given up
                    # on. The label keeps its readings, unresolved, and the
                    # record goes to review (HARNESS.md section 3, Failures).
                    give_up(run, region.id, failure.code)
                    reading_failure = failure.code
                    refusal = failure.code if failure.refused else None
                    call_usage = failure.usage
                    circuit_failure = failure.status.value
                    circuit_retry_after = failure.retry_after_seconds
                    _log_step_failure(
                        run,
                        step,
                        "first_pass_given_up",
                        error=failure,
                        status=failure.status.value,
                        code=log_code(failure.code),
                    )
                    decision = None
                if decision is not None:
                    ids = {o.id for o in readings}
                    selected = decision.selected_observation_id
                    if (
                        decision.region_id != region.id
                        or decision.call.region_id != region.id
                        or selected not in ids | {None}
                        or any(
                            set(d.spans) != ids
                            or d.verdict not in ids | UNRESOLVED_VERDICTS
                            or d.material != is_material(d.spans.values())
                            for d in decision.differences
                        )
                        or g19_pick(selected, decision.differences) != selected
                        # Units path: no selected reading, `uncertain` verdicts, and units of
                        # this region that pass `problems`.
                        or units_path
                        and (
                            selected is not None
                            or any(d.verdict != "uncertain" for d in decision.differences)
                            or units is None
                            or units.label != region.id
                            or unit_problems(units, {o.id: o.literal_text for o in readings})
                        )
                    ):
                        raise OperationalBlock("first_pass_contract_invalid")
                    run.first_pass_decisions = [
                        d for d in run.first_pass_decisions if d.region_id != region.id
                    ] + [decision]
                    if units is not None:
                        store_reading_units(run, [units])
                    call = decision.call
                    run.usage.tokens += call.input_tokens + call.output_tokens
            elif step == "adjudicate":
                run.transcripts = []
                decisions = {d.region_id: d for d in run.first_pass_decisions}
                if run.first_pass_path == "units":
                    # A region with no units entry gets alignment_units.
                    from .first_pass import alignment_units

                    held = {entry.label for entry in run.reading_units}
                    store_reading_units(
                        run,
                        [
                            units
                            for region in run.regions
                            if region.id not in held
                            and (
                                units := alignment_units(
                                    region.id,
                                    [o for o in run.observations if o.region_id == region.id],
                                )
                            )
                            is not None
                        ],
                    )
                for region in run.regions:
                    readings = [o for o in run.observations if o.region_id == region.id]
                    texts = list(dict.fromkeys(o.literal_text for o in readings))
                    from .first_pass import adjudication_record
                    from .reading_evidence import (
                        ReadingEvidenceInput,
                        disagreement_ratio,
                        label_comparison,
                        pairwise_alignments,
                    )

                    # Every pair of the label's readings, in route order; two
                    # readings are one pair, as before. A label is measured
                    # when every pair is, and reports its least-agreeing pair
                    # (reading_evidence.label_comparison).
                    alignments = pairwise_alignments(
                        [
                            ReadingEvidenceInput(
                                observation_id=o.id,
                                region_id=region.id,
                                source_ref=o.raw_ref,
                                source_sha256=o.raw_sha256,
                                text=o.literal_text,
                            )
                            for o in readings
                        ]
                    )
                    comparison = label_comparison(alignments)
                    measured = (
                        comparison is not None and comparison.status != "policy_blocked"
                    )
                    resolved = (
                        measured
                        and len(texts) == 1
                        and bool(texts[0].strip())
                        and not any(o.unreadable_spans for o in readings)
                    )
                    text, resolved, record = adjudication_record(
                        readings,
                        texts,
                        resolved,
                        decisions.get(region.id),
                        keep_call=run.first_pass_path == "units",
                    )
                    run.transcripts.append(
                        Transcript(
                            region_id=region.id,
                            text=text,
                            observation_ids=[o.id for o in readings],
                            alternatives=texts,
                            resolved=resolved,
                            disagreement_ratio=disagreement_ratio(comparison.alignment)
                            if measured
                            else None,
                            alignment_status=comparison.status
                            if comparison
                            else "policy_blocked",
                            alignment_algorithm="bounded-levenshtein-fraction-v1",
                            alignment_reasons=list(comparison.reasons)
                            if comparison
                            else ["independent_pair_incomplete"],
                            comparisons=[
                                ReadingPairComparison(
                                    left_observation_id=a.left.observation_id,
                                    right_observation_id=a.right.observation_id,
                                    status=a.status,
                                    reasons=list(a.reasons),
                                    disagreement_ratio=disagreement_ratio(a),
                                )
                                for a in alignments
                            ]
                            if len(alignments) > 1
                            else [],
                            **record,
                        )
                    )
            elif step == "parse":
                # Parse and extract into a working copy, applied to the run only
                # when the step ends: an attempt whose extraction fails and is
                # retried leaves no fields or evidence behind, so a retry does
                # not add a second evidence row per parsed line.
                proposal = specimen.model_copy(deep=True)
                parse_base = (
                    copy.deepcopy(run.fields),
                    copy.deepcopy(run.evidence),
                    run.usage.model_copy(deep=True),
                )
                self.parse(proposal.run, specimen.asset.id, self.blobs)
                # Asked again here, as before: offline adapters that hide their
                # extract from the first check (unmetered) still extract.
                if hasattr(self.adapters, "extract") and not extraction_given_up(run):
                    try:
                        call_usage = self.adapters.extract(proposal)
                    except (AdapterFailure, ReadingStopped) as failure:
                        if not self.extraction_has_no_attempt_left(run, step, failure):
                            raise  # Retried, or a block that names its cause (below).
                        # Its last attempt failed, its answer stayed malformed or
                        # it was stopped by its limits: the run goes on without
                        # the extraction's candidates; the deterministic parse
                        # above stands, and what does not settle goes to review.
                        give_up_the_extraction(run, failure.code)
                        reading_failure = failure.code
                        call_usage = failure.usage
                        status = {}
                        if isinstance(failure, AdapterFailure):
                            refusal = failure.code if failure.refused else None
                            circuit_failure = failure.status.value
                            circuit_retry_after = failure.retry_after_seconds
                            status = {"status": failure.status.value}
                        _log_step_failure(
                            run,
                            step,
                            "extraction_given_up",
                            error=failure,
                            code=log_code(failure.code),
                            **status,
                        )
                if not run.dependencies.get(CARRY_KEY):
                    run.fields = proposal.run.fields
                    run.evidence = proposal.run.evidence
                    run.usage = proposal.run.usage
                else:
                    from .human_field_carry import manifests
                    protected = set(manifests(specimen))
                    run.fields.update({k: v for k, v in proposal.run.fields.items() if k not in protected})
                    run.evidence = proposal.run.evidence
                    run.usage = proposal.run.usage
                    # New model evidence remains an honest proposal. Verify on
                    # the fresh persisted base, then only protected proposed bytes.
                    base = self.repository.version(principal.scope, specimen.id, revision)
                    verified = verify_carries(self.repository, base, self.blobs)
                    if any(run.fields[k] != v.value for k, v in verified.outcomes.items()):
                        raise OperationalBlock("preserved_human_field_provenance_unavailable")
            elif step == FIELD_RESEARCH:
                # Researches, applies and finalizes in memory; the save below is
                # the step's only one. An outage raises AdapterFailure after the
                # settled fields are applied, so they are kept and retried around.
                self.field_research.run(
                    self,
                    principal,
                    specimen,
                    cap_micros=cost or 0,
                    deadline_seconds=effect_timeout,
                )
            elif step == FIELD_RECHECK:
                self.field_research.recheck(self, principal, specimen)
            elif step == "plan":
                run.authority_plan = plan_authorities(specimen)
            elif step.startswith("authority:"):
                task = run.authority_plan[int(step.split(":")[1])]
                query = authority_query(specimen, task, self.blobs)
                if query is None:
                    run.authority_unresolved[step] = dict(
                        task, reason="source_literal_unresolved"
                    )
                else:
                    tool = self.authority_tools.get(task["tool_id"])
                    pinned = run.dependencies.get("authority_pins", {}).get(
                        task["tool_id"]
                    )
                    if tool and pinned != self.authority_pins().get(task["tool_id"]):
                        raise OperationalBlock(
                            "authority_configuration_changed_requires_new_run"
                        )
                    call_id = step + ":" + str(run.attempts.get(step, 1))
                    call = ToolCall(
                        call_id=call_id,
                        phase="lookup",
                        tool_id=task["tool_id"],
                        tool_version=getattr(tool, "version", "unconfigured"),
                        reserved_cost_microunits=self.authority_cost_reservations.get(
                            task["tool_id"]
                        ),
                    )
                    previous = run.authority_receipts.get(call_id)
                    if previous:
                        raw = self.blobs.get(previous["blob_ref"])
                        if hashlib.sha256(raw).hexdigest() != previous["sha256"]:
                            raise OperationalBlock(
                                "authority_receipt_integrity_failure"
                            )
                        previous = ToolReceipt.model_validate_json(raw)

                    def checkpoint(receipt):
                        nonlocal specimen, run, revision
                        raw = receipt.model_dump_json().encode()
                        run.authority_receipts[call_id] = {
                            "blob_ref": self.blobs.put(raw),
                            "sha256": hashlib.sha256(raw).hexdigest(),
                            "state": receipt.state,
                            "call_id": call_id,
                        }
                        run.authority_usage = receipt.usage.model_dump(mode="json")
                        specimen = self.repository.save(
                            principal,
                            specimen,
                            revision,
                            f"authority:{call_id}:{receipt.state}:{revision}",
                            digest(receipt.model_dump(mode="json")),
                        )
                        revision = specimen.version
                        run = specimen.run

                    receipt = HarnessRunner(self.authority_tools).execute_one(
                        harness_spec(specimen),
                        call,
                        query,
                        HarnessUsage.model_validate(run.authority_usage),
                        checkpoint,
                        previous,
                    )
                    if receipt.state != "completed" or receipt.result is None:
                        raise OperationalBlock(
                            receipt.reason or "authority_call_blocked"
                        )
                    result = receipt.result
                    raw = result.model_dump_json().encode()
                    run.authority_results[step] = {
                        "tool_id": task["tool_id"],
                        "field_key": task["field_key"],
                        "source_id": result.source_id,
                        "status": result.status.value,
                        "blob_ref": self.blobs.put(raw),
                        "sha256": hashlib.sha256(raw).hexdigest(),
                    }
                    if result.operationally_blocked:
                        raise AdapterFailure(
                            "authority_" + result.status.value,
                            result.status,
                            retry_after_seconds=result.retry_after_seconds,
                        )
            elif step == "lookup":
                name = run.fields["taxon"].literal
                if name:
                    # No word of the run's place-field literals is sent, and
                    # a genus in doubt sends nothing (the coordinator's rulings
                    # of 02:07Z, 03:24Z and 03:31Z on 2026-09-26, PLAN 4.8).
                    places = [
                        run.fields[key].literal
                        for key in PLACE_FIELDS
                        if key in run.fields and run.fields[key].literal
                    ]
                    outcome = taxonomy_lookup(self.adapters.lookup, name, places, self.blobs)
                    run.lookups.append(outcome)
                    if outcome.status in OPERATIONAL:
                        raise OperationalBlock("taxonomy_" + outcome.status.value)
                    if outcome.status == LookupStatus.SUCCESS:
                        evidence = Evidence(
                            kind="authority",
                            source=outcome.provider,
                            locator="/v2/species/match",
                            excerpt=str(outcome.candidates),
                            raw_ref=outcome.raw_ref,
                            digest=outcome.digest,
                        )
                        run.evidence.append(evidence)
                        field = run.fields["taxon"]
                        field.evidence_ids.append(evidence.id)
                        if outcome.candidates:
                            field.normalized = outcome.candidates[0].get(
                                "scientificName"
                            )
                            field.authority_id = str(
                                outcome.candidates[0].get("key", "")
                            )
                else:
                    run.lookups.append(
                        Lookup(
                            provider="profile",
                            adapter_version="1",
                            query={},
                            status=LookupStatus.NO_MATCH,
                        )
                    )
            elif step == "finalize":
                try:
                    verify_evidence(specimen, self.blobs)
                except EvidenceIntegrityError as exc:
                    raise OperationalBlock(str(exc)) from exc
                phase_result = refresh_review_evidence(specimen, self.blobs)
                finalize(run)
                apply_phase_gate(run, phase_result)
            effect_settled = True
            try:
                if step.startswith("authority:"):
                    execute_phase(specimen, "lookup", self.blobs)
                if step in {"parse", "plan", "lookup", "resolve", "normalize", "validate"}:
                    execute_phase(specimen, step, self.blobs)
            except EvidenceIntegrityError as exc:
                raise OperationalBlock(str(exc)) from exc
            if run.stage != "processing_blocked":
                run.blocker = None
            run.lease_until = None
            if step != FIELD_RECHECK:
                end_step(run, step)
            if step not in {"finalize", FIELD_RESEARCH, FIELD_RECHECK}:
                run.stage = self.next_step(run).split(":")[0]
        except AdapterFailure as exc:
            # These model reads cannot duplicate a specimen or publication.
            # Their unknown billing remains reserved, independently of whether
            # the workflow can safely retry; other effects keep the block.
            recoverable = model_read_is_recoverable(run, step) and (
                step != "parse" or extracting
            )
            outcome_unknown = exc.outcome_unknown and not recoverable
            if reader_failure_is_recoverable(run, step) or (
                recoverable and (step == "parse" or exc.outcome_unknown)
            ):
                reading_failure = exc.code
            refusal = exc.code if exc.refused else None
            call_usage = exc.usage
            circuit_failure = exc.status.value
            circuit_retry_after = exc.retry_after_seconds
            run.blocker = "external_outcome_unknown" if outcome_unknown else exc.code
            run.stage = "processing_blocked"
            run.disposition = None
            if not outcome_unknown and failure_is_retryable(run, step, exc.status):
                self.schedule_retry(
                    run,
                    step,
                    exc.retry_after_seconds,
                    rate_limited=exc.status == LookupStatus.RATE_LIMITED,
                )
            # The SAM 3 service answers a repeat of a run's request from the
            # response it stored (sam3_server.RunSegmenter). These repeatable
            # model failures stay known past the deadline override (set above).
            repeatable = recoverable or (
                step == "segment"
                and exc.code.startswith("sam3_")
                and not exc.outcome_unknown
            )
            _log_step_failure(
                run,
                step,
                "adapter_failure",
                error=exc,
                status=exc.status.value,
                code=log_code(exc.code),
                blocker=log_code(run.blocker),
                stage=run.stage,
                outcome_unknown=outcome_unknown,
            )
        except OperationalBlock as exc:
            circuit_failure = (
                None if effect_settled else str(exc).removeprefix("taxonomy_")
            )
            run.blocker = str(exc)
            run.stage = "processing_blocked"
            run.disposition = None
            if run.blocker in {
                "taxonomy_rate_limited",
                "taxonomy_timeout",
                "taxonomy_provider_error",
            }:
                self.schedule_retry(run, step, run.lookups[-1].retry_after_seconds)
            _log_step_failure(
                run,
                step,
                "operational_block",
                error=exc,
                code=log_code(str(exc)),
                blocker=log_code(run.blocker),
                stage=run.stage,
            )
        except Exception as exc:
            outcome_unknown = external and not effect_settled
            circuit_failure = "provider_error" if outcome_unknown else None
            # Do not expose raw exceptions containing provider headers or source text.
            logfire.warn(
                "Specimen step failed",
                step=step,
                exception_class=type(exc).__name__,
                outcome_unknown=outcome_unknown,
            )
            run.blocker = (
                "external_outcome_unknown"
                if outcome_unknown
                else "stage_failed_inspect_private_worker_logs"
            )
            run.stage = "processing_blocked"
            run.disposition = None
            _log_step_failure(
                run,
                step,
                "unexpected_exception",
                error=exc,
                blocker=log_code(run.blocker),
                stage=run.stage,
                outcome_unknown=outcome_unknown,
            )
        if parse_base is not None and step not in run.completed_steps:
            # parse did not end (a retried extraction, an integrity failure
            # after it, a human-field check that refused): none of this
            # attempt's fields, evidence or token usage stays, so the next
            # attempt does not add them again. Its reservations were made
            # before the snapshot and stay.
            run.fields, run.evidence, run.usage = parse_base
        if (
            (ordinary_first_pass or ordinary_extraction)
            and run.stage == "processing_blocked"
            and run.blocker == "external_outcome_unknown"
        ):
            # A provider or deadline failure of these reads is a known failure
            # (above), so an unknown outcome here is a result the parent could
            # not accept (an invalid child result, a child whose cleanup is not
            # confirmed, an unexpected exception). It is held for a person:
            # recorded so that recover_blocked never makes it due again.
            mark_unknown_outcome(run, step, HELD)
        elif run.blocker != "external_outcome_unknown":
            # Known now (completed, retried or given up): no longer recorded.
            resolve_unknown_outcome(run, step)
        elapsed = max(0, self.monotonic() - started)
        if external and elapsed > effect_timeout and not repeatable:
            circuit_failure = "timeout"
            # Past its deadline this step's outcome is unknown, so even a refusal
            # releases nothing. A repeatable reader or first-pass comparison
            # never comes here: a known refusal stays known past its deadline,
            # while an unknown bill remains fully reserved.
            refusal = None
            call_usage = None
            # Field research's meter knows what its calls cost even when the
            # step overran: its paid call stays, so the settlement below frees
            # the rest of its reservation.
            researched = run if step == FIELD_RESEARCH else None
            specimen = reserved
            run = specimen.run
            if researched is not None:
                run.paid_calls.extend([call for call in researched.paid_calls if call not in run.paid_calls])
                run.usage.actual_cost_micros = researched.usage.actual_cost_micros
            run.blocker = "external_outcome_unknown"
            run.stage = "processing_blocked"
            run.disposition = None
            run.reasons = ["external_stage_deadline_exceeded"]
            _log_step_failure(
                run,
                step,
                "external_deadline_exceeded",
                code=run.reasons[0],
                blocker=run.blocker,
                stage=run.stage,
                elapsed_seconds=f"{elapsed:.1f}",
                effect_timeout_seconds=effect_timeout,
            )
        run.usage.active_seconds += elapsed
        run.usage.tokens += max(
            0,
            sum(o.input_tokens + o.output_tokens for o in run.observations)
            - previous_tokens,
        )
        if billable and not run.profile.synthetic and step == FIELD_RESEARCH:
            from .lane_costs import settle_step

            # The step recorded its own paid call (its meter's spend); settle the
            # run's budget and the program ledger to it. A deadline overrun
            # restored the reserved copy with that paid call copied onto it
            # (above), so it settles to the meter's spend as well.
            settle_step(self.repository, principal, specimen, step, cost, self.clock)
        elif billable and not run.profile.synthetic:
            from .lane_costs import record_step

            # Each paid call's cost, and the program ledger settled (LANE.md T2c).
            record_step(
                self.repository,
                principal,
                specimen,
                step,
                run.observations[observed:],
                elapsed,
                cost,
                self.clock,
                failure=reading_failure,
                refusal=refusal,
                usage=call_usage,
            )
        if billable and not run.profile.synthetic:
            if self.settle_retained_cost is not None:
                self.settle_retained_cost(principal, specimen, step)
        if external and run.blocker != "external_outcome_unknown":
            run.lease_until = None
            run.usage.reserved_active_seconds = max(
                0, run.usage.reserved_active_seconds - effect_timeout
            )
        specimen.audit.append(
            AuditEvent(
                actor=principal.user_id,
                action="workflow_step",
                reason=step,
                after={"stage": run.stage, "blocker": run.blocker},
            )
        )
        from .active_graph import save_recoverably

        saved = save_recoverably(
            self.repository,
            principal,
            specimen,
            revision,
            f"result:{revision}",
            digest({"step": step, "run": run.id}),
        )
        if circuit is not None and permit is not None:
            if circuit_failure is None:
                circuit.record_success(permit)
            else:
                known = {
                    "rate_limited",
                    "timeout",
                    "provider_error",
                    "authentication_error",
                    "authorization_error",
                    "policy_blocked",
                    "malformed_response",
                }
                failure = (
                    circuit_failure if circuit_failure in known else "policy_blocked"
                )
                if step == "lookup" and run.lookups:
                    circuit_retry_after = run.lookups[-1].retry_after_seconds
                circuit.record_failure(permit, failure, circuit_retry_after)
        return saved

    def _settle_lost_reading(self, principal, specimen, revision, step):
        """End a reading whose worker stopped before saving it, as a failed reading.

        The reading's intent was saved (``external_outcome_unknown`` and a lease)
        and the lease ran out with no result saved: the worker that sent it
        stopped. A reading is a pure read (``reader_failure_is_recoverable``), so
        this is a known failure, not a block for an administrator. The attempt is
        recorded failed with its reservation held in full, as any failed reading
        is (``lane_costs.record_step``). The reading is asked again within
        ``max_attempts``; after the last attempt it ends with no observation and
        the record goes to review (G6), as ``reading_has_no_attempt_left`` does.

        An ordinary first pass (``first_pass_failure_is_recoverable``) is settled
        the same way, with ``LOST_FIRST_PASS``: after its last attempt it is given
        up on (``first_pass.give_up``) and the label keeps its readings,
        unresolved. So is one whose unknown outcome a step already saved, with
        its attempt recorded and held (``recover_blocked`` makes it due): that
        attempt is not recorded or counted again.
        """
        run = specimen.run
        policy = run.profile.execution
        first_pass = step.startswith("first_pass:")
        extraction = step == "parse"
        code = (
            LOST_FIRST_PASS if first_pass else LOST_EXTRACTION if extraction else LOST_READING
        )
        attempt = run.attempts.get(step, 0)
        recorded = any(
            call.get("step") == step and call.get("attempt") == attempt
            for call in run.paid_calls
        )
        run.lease_until = None
        run.disposition = None
        # The call may have run to its effect timeout: that time is spent, not
        # released, so the run's active-time budget still counts it. A recorded
        # attempt already counted the time it took.
        timeout = policy.effect_timeout_for_step(step)
        if not recorded:
            run.usage.active_seconds += min(timeout, run.usage.reserved_active_seconds)
        run.usage.reserved_active_seconds = max(0, run.usage.reserved_active_seconds - timeout)
        # The lost attempt is settled: its outcome is known (a failed attempt).
        resolve_unknown_outcome(run, step)
        if attempt >= policy.max_attempts:
            if first_pass:
                from .first_pass import give_up

                give_up(run, step.split(":", 1)[1], code)
            run.blocker = None
            run.next_retry_at = None
            run.dead_letter = False
            if extraction:
                # The extraction is given up on; parse itself still runs, next,
                # without the call (its deterministic parse and phase).
                give_up_the_extraction(run, code)
            else:
                end_step(run, step)
            run.stage = self.next_step(run).split(":")[0]
        else:
            run.blocker = code
            run.stage = "processing_blocked"
            self.schedule_retry(run, step)
        _log_step_failure(
            run,
            step,
            code,
            code=code,
            blocker=run.blocker,  # The code, or None once given up
            stage=run.stage,
        )
        if not run.profile.synthetic and not recorded:
            from .lane_costs import record_settled, record_step, settle_step
            from .lane_reservations import step_reservation

            reserved = step_reservation(run, step)
            settled = self._ledger_settlement(principal, specimen, step, reserved)
            if settled is None:
                record_step(
                    self.repository,
                    principal,
                    specimen,
                    step,
                    [],
                    0,
                    reserved,
                    self.clock,
                    failure=code,
                )
            else:
                # The stopped worker had settled the ledger before saving: the
                # run's budget is settled to the same known cost.
                record_settled(
                    run,
                    step,
                    "model",
                    cost_micros=settled,
                    failure_code=code,
                    route_id=run.profile.first_pass_route
                    if first_pass
                    else step.split(":")[-1],
                )
                settle_step(
                    self.repository, principal, specimen, step, reserved, self.clock
                )
            if self.settle_retained_cost is not None:
                self.settle_retained_cost(principal, specimen, step)
        specimen.audit.append(
            AuditEvent(
                actor=principal.user_id,
                action="workflow_step",
                reason=step,
                after={"stage": run.stage, "blocker": run.blocker},
            )
        )
        from .active_graph import save_recoverably

        return save_recoverably(
            self.repository,
            principal,
            specimen,
            revision,
            f"lost-reading:{revision}",
            digest({"lost_reading": step, "run": run.id}),
        )

    def _give_up_first_pass(self, principal, specimen, revision, step, code):
        """Give an ordinary first pass up without sending it: the run cannot
        afford another call (``UNAFFORDABLE``). Nothing is reserved or recorded;
        earlier attempts keep what they hold. The label keeps its readings,
        unresolved, and the record goes on to review (HARNESS.md 3, Failures)."""
        from .first_pass import give_up

        run = specimen.run
        give_up(run, step.split(":", 1)[1], code)
        run.blocker = None
        run.next_retry_at = None
        run.dead_letter = False
        run.disposition = None
        end_step(run, step)
        run.stage = self.next_step(run).split(":")[0]
        _log_step_failure(run, step, "first_pass_unaffordable", code=code, stage=run.stage)
        specimen.audit.append(
            AuditEvent(
                actor=principal.user_id,
                action="workflow_step",
                reason=step,
                after={"stage": run.stage, "blocker": run.blocker},
            )
        )
        return self.repository.save(
            principal,
            specimen,
            revision,
            f"first-pass-unaffordable:{revision}",
            digest({"first_pass_unaffordable": step, "run": run.id, "code": code}),
        )

    def _give_up_extraction_unsent(self, principal, specimen, revision, step, code):
        """Give the organiser's extraction up without sending it: the run cannot
        afford another call (``UNAFFORDABLE``). Nothing is reserved or recorded;
        earlier attempts keep what they hold. The next step runs parse without
        the call, and the record goes on to field research and review."""
        run = specimen.run
        give_up_the_extraction(run, code)
        run.blocker = None
        run.next_retry_at = None
        run.dead_letter = False
        run.disposition = None
        run.stage = self.next_step(run).split(":")[0]
        _log_step_failure(run, step, "extraction_unaffordable", code=code, stage=run.stage)
        specimen.audit.append(
            AuditEvent(
                actor=principal.user_id,
                action="workflow_step",
                reason=step,
                after={"stage": run.stage, "blocker": run.blocker},
            )
        )
        return self.repository.save(
            principal,
            specimen,
            revision,
            f"extraction-unaffordable:{revision}",
            digest({"extraction_unaffordable": step, "run": run.id, "code": code}),
        )

    def _give_up_field_research(self, principal, specimen, revision, code):
        """Give field research up without starting it: the run's own limits
        other than money (``RESEARCH_LIMITS``) leave no room for another
        attempt. Nothing is reserved, attempted or paid; earlier attempts keep
        what they hold and the fields they settled. The step's rules finalize
        the record, the fields it could not check unresolved for a person
        (``FieldResearchStep.give_up``), and it goes on to review.

        This attempt itself may hold on a monthly cap's ledger: a refusal
        later in the chain blocked it after its holds, and the run records
        them (tenant_budget.recorded_micros). It was never sent, so once the
        give-up is saved they settle at zero (tenant_budget.release_unsent,
        TENANT_BUDGETS.md)."""
        from .active_graph import save_recoverably
        from .tenant_budget import release_unsent, settle_released

        run = specimen.run
        release = None
        try:
            self.field_research.give_up(self, principal, specimen, code)
        except OperationalBlock as error:
            run.blocker = str(error)
            run.stage = "processing_blocked"
            run.disposition = None
        else:
            run.next_retry_at = None
            run.dead_letter = False
            run.lease_until = None
            end_step(run, FIELD_RESEARCH)
            release = release_unsent(run, FIELD_RESEARCH)
        _log_step_failure(
            run, FIELD_RESEARCH, "field_research_unaffordable", code=code, stage=run.stage
        )
        specimen.audit.append(
            AuditEvent(
                actor=principal.user_id,
                action="workflow_step",
                reason=FIELD_RESEARCH,
                after={"stage": run.stage, "blocker": run.blocker},
            )
        )
        saved = save_recoverably(
            self.repository,
            principal,
            specimen,
            revision,
            f"field-research-unaffordable:{revision}",
            digest({"field_research_unaffordable": code, "run": run.id}),
        )
        settle_released(self.repository, principal, saved, release, self.clock)
        return saved

    def recover_blocked(self, principal: Principal, specimen_id: str) -> bool:
        """Make a blocked ordinary first pass or extraction due again; whether it did.

        The drain calls this for each blocked record when it takes a collection
        (lane_worker.DrainWorker), so a run blocked at its first pass, or at the
        organiser's extraction (``parse``), by a transient cause goes on through
        the normal workflow with no action:

        - ``external_outcome_unknown`` (lease ended): due, kept as it is; the
          step settles it as a lost attempt (``_settle_lost_reading``). Only an
          unanswered call or a legacy row (``unknown_outcome_recoverable``); a
          result the parent could not accept (``HELD``) stays blocked for a
          person.
        - ``retry_budget_exhausted:<code>``: its attempts are used up, so the
          first pass (or the extraction) is given up on with ``<code>``. So is
          one blocked by an answer that stayed malformed (``MALFORMED_ANSWER``),
          which the step now gives up on at once.
        - A budget the run cannot afford (``UNAFFORDABLE``), a pin whose provider
          moved (``first_pass.repinnable_first_pass_route``, a first pass only),
          a provider circuit, or a lane stall: due; the step gives the call up,
          moves the pin, or asks the circuit again.

        - Field research blocked by one of the run's own limits other than
          money (``RESEARCH_LIMITS``): due; the step gives it up unsent and the
          record goes to review (``_give_up_field_research``).

        Only an ordinary first pass (``first_pass_failure_is_recoverable``),
        extraction (``extraction_failure_is_recoverable``) or field research
        held by such a limit, on a record that is not sensitive, has no
        disposition and holds no live lease. An extraction
        given up on leaves parse due without its call.
        Each recovery is recorded in ``run.dependencies[AUTOMATIC_RECOVERIES]``,
        at most ``MAX_AUTOMATIC_RECOVERIES`` per step. No call is made here, and
        no reservation is released or added.
        """
        from .reliability import has_active_lease

        specimen = self.repository.get(principal.scope, specimen_id)
        run = specimen.run
        if (
            run.stage != "processing_blocked"
            or run.disposition is not None
            or specimen.asset.sensitive
        ):
            return False
        step = self.next_step(run)
        blocker = run.blocker or ""
        from .harness import extraction_given_up

        first_pass = step.startswith("first_pass:") and first_pass_failure_is_recoverable(
            run, step
        )
        extraction = (
            step == "parse"
            and hasattr(self.adapters, "extract")
            and extraction_failure_is_recoverable(run, step)
            and not extraction_given_up(run)
        )
        research = (
            step == "plan"
            and self.field_research is not None
            and FIELD_RESEARCH not in run.completed_steps
            and blocker in RESEARCH_LIMITS
            and self.field_research.handles(run)
        )
        if research:
            step = FIELD_RESEARCH
        if (
            not (first_pass or extraction or research)
            or has_active_lease(run, self.clock())
            # Only an unknown outcome whose cause the run durably shows can be
            # mended by asking again; any other stays for a person.
            or (
                blocker == "external_outcome_unknown"
                and not unknown_outcome_recoverable(run, step)
            )
            or not (
                research
                or blocker in RECOVERABLE_FIRST_PASS_BLOCKERS
                or blocker == MALFORMED_ANSWER
                or blocker.startswith(RECOVERABLE_FIRST_PASS_PREFIXES)
            )
        ):
            return False
        from .first_pass import give_up, repinnable_first_pass_route

        if blocker == "pinned_model_route_unavailable" and (
            not first_pass or repinnable_first_pass_route(run) is None
        ):
            return False  # Another model, or no route: not a provider move.
        history = run.dependencies.get(AUTOMATIC_RECOVERIES, [])
        if sum(1 for item in history if item.get("step") == step) >= MAX_AUTOMATIC_RECOVERIES:
            return False
        at = self.clock()
        run.dependencies[AUTOMATIC_RECOVERIES] = [
            *history,
            {
                "step": step,
                "blocker": blocker,
                "attempt": run.attempts.get(step, 0),
                "at": at.isoformat(),
                **(
                    {"rule": LEGACY_UNKNOWN}
                    if blocker == "external_outcome_unknown"
                    and unknown_outcome_kind(run, step) is None
                    else {}
                ),
            },
        ]
        if blocker.startswith("retry_budget_exhausted:") or blocker == MALFORMED_ANSWER:
            code = blocker.removeprefix("retry_budget_exhausted:")
            if first_pass:
                give_up(run, step.split(":", 1)[1], code)
                end_step(run, step)
            else:
                # parse runs next, without the call it gave up on.
                give_up_the_extraction(run, code)
            run.blocker = None
            run.dead_letter = False
            run.next_retry_at = None
            run.stage = self.next_step(run).split(":")[0]
        else:
            # Due now. An unknown outcome keeps its blocker for the step to settle.
            run.stage = "retry_scheduled"
            run.next_retry_at = at.isoformat()
        _log_step_failure(run, step, "automatic_recovery", blocker=log_code(blocker), stage=run.stage)
        specimen.audit.append(
            AuditEvent(
                actor=principal.user_id,
                action="automatic_recovery",
                reason=step,
                after={"stage": run.stage, "blocker": run.blocker},
            )
        )
        self.repository.save(
            principal,
            specimen,
            specimen.version,
            f"automatic-recovery:{specimen.version}",
            digest({"automatic_recovery": step, "run": run.id, "blocker": blocker}),
        )
        return True

    def _ledger_settlement(self, principal, specimen, step, reserved):
        """What the program ledger settled for the step's current attempt, or None.

        Only an envelope this run reserved exactly as ``settle_step`` would
        settle it: the same reservation and allowance, its numbers read back as
        exact integers (``stored_integer``: the transport may return doubles).
        None when the ledger cannot be read, the envelope differs, or the
        attempt is reserved but not settled; the lost attempt then stays held
        in full. A run with no program allowance asks the monthly cap ledgers
        the attempt reserved in (tenant_budget.settled_micros): None when it
        reserved in none, or they do not all hold one settled amount.
        """
        from .domain import Scope
        from .lane_allowance import ORDINARY, ProgramLedger
        from .lane_worker import stored_integer
        from .tenant_budget import settled_micros

        run = specimen.run
        policy = run.profile.execution
        if not reserved:
            return None
        if policy.program_allowance_micros is None:
            return settled_micros(self.repository, principal, specimen, step,
                run.attempts.get(step, 0), reserved)
        try:
            ledger = ProgramLedger(
                self.repository,
                Scope(
                    organization_id=principal.scope.organization_id,
                    collection_id=policy.program_ledger_collection,
                ),
                clock=self.clock,
            )
            key = ProgramLedger._ordinary_key(
                specimen.id, run.id, step, run.attempts.get(step, 0)
            )
            entry = ledger.effect(ORDINARY, key)  # The head's, else its archive's.
            if not isinstance(entry, dict) or entry.get("settled_micros") is None:
                return None
            if (
                stored_integer(entry.get("reserved_micros")) != reserved
                or stored_integer(entry.get("allowance_micros"))
                != policy.program_allowance_micros
            ):
                return None
            return stored_integer(entry["settled_micros"])
        except Exception:  # noqa: BLE001 - an unreadable ledger proves no settlement
            return None

    def schedule_retry(self, run, step, provider_seconds=None, *, rate_limited=False):
        """Wait before the step's next attempt, or end its retries.

        A rate-limited step waits at least ``reliability.RATE_LIMIT_FLOORS``.
        The run holds no lease while it waits, and ``step`` returns it unchanged
        until ``next_retry_at``.
        """
        if run.attempts.get(step, 0) < run.profile.execution.max_attempts:
            delay = retry_delay(
                run.attempts.get(step, 1),
                provider_seconds,
                self.random_value,
                rate_limited=rate_limited,
            )
            run.next_retry_at = (self.clock() + timedelta(seconds=delay)).isoformat()
            run.stage = "retry_scheduled"
        else:
            run.dead_letter = True
            run.blocker = "retry_budget_exhausted:" + (run.blocker or "adapter_failure")

    @staticmethod
    def reading_has_no_attempt_left(run, step, failure) -> bool:
        """Whether a reader's failed attempt was its last one.

        The same test as ``schedule_retry``: attempts are counted when the call
        is sent, so a failure at ``max_attempts`` has no retry left. A failure
        that is not retried at all (a credential error) is not given up on: it
        stays a block that names its cause.
        """
        return (
            reader_failure_is_recoverable(run, step)
            and failure_is_retryable(run, step, failure.status)
            and run.attempts.get(step, 0) >= run.profile.execution.max_attempts
        )

    @staticmethod
    def first_pass_has_no_attempt_left(run, step, failure) -> bool:
        """Whether a first pass's failed attempt was its last one, and is given up on.

        The reader's test (``reading_has_no_attempt_left``) where it applies: a
        failure that is retried (``failure_is_retryable``: a rate limit, a
        timeout or a provider error, HTTP 402 included) on the attempt that used
        up ``max_attempts``. A malformed answer (still invalid after the agent's
        one output retry, so at most two requests) is given up on at once and is
        not asked again: bounded by that one call, and recorded as the
        ``first_pass_given_up`` finding with its code and a ``failed`` cost row
        that keeps the whole reservation; the label's readings go to review
        unresolved. Any other failure that is not retried still blocks and names
        its cause (a credential or permission error, a request the provider
        rejects). An ordinary first pass's transient failure can be given up on
        even if its bill is unknown: every attempt keeps its reservation and no
        transcript is selected. The evidence pilot stays excluded, as it does
        from reader recovery.
        """
        return (
            step.startswith("first_pass:")
            and first_pass_failure_is_recoverable(run, step)
            and (
                # A malformed answer (still invalid after the agent's output
                # retry) is a known outcome: given up on at once, never retried
                # (2026-10-12, specimen 19f0f1f6).
                failure.status == LookupStatus.MALFORMED
                or (
                    failure_is_retryable(run, step, failure.status)
                    and run.attempts.get(step, 0) >= run.profile.execution.max_attempts
                )
            )
        )

    @staticmethod
    def extraction_has_no_attempt_left(run, step, failure) -> bool:
        """Whether the organiser's extraction is given up on after this failure.

        The first pass's rule (``first_pass_has_no_attempt_left``): a failure
        that is retried (a rate limit, a timeout, a provider error, an unknown
        outcome after an HTTP 5xx or a child's deadline) on the attempt that
        used up ``max_attempts``, or a malformed answer. An extraction stopped by
        its token limits (``ReadingStopped``) is given up on at once, as a
        reading is (#153). A credential or permission error and a request the
        provider rejects still block and name their cause; so does the evidence
        pilot (``reliability.extraction_failure_is_recoverable``).
        """
        if step != "parse" or not extraction_failure_is_recoverable(run, step):
            return False
        if isinstance(failure, ReadingStopped):
            return True
        return failure.status == LookupStatus.MALFORMED or (
            failure_is_retryable(run, step, failure.status)
            and run.attempts.get(step, 0) >= run.profile.execution.max_attempts
        )

    @staticmethod
    def next_step(run: Run) -> str:
        for step in ("pin_dependencies", "classify", "quality_check", "segment"):
            if step not in run.completed_steps:
                return step
        for region in run.regions:
            for route in run.profile.routes:
                key = f"transcribe:{region.id}:{route}"
                if key not in run.completed_steps:
                    return key
        if "adjudicate" not in run.completed_steps:
            # Differing readings get the LLM first pass (HARNESS.md section 3). Units path:
            # two readings or more, and some text.
            for region in run.regions:
                readings = [o for o in run.observations if o.region_id == region.id]
                texts = {o.literal_text for o in readings}
                key = f"first_pass:{region.id}"
                due = (
                    len(readings) > 1 and any(text.strip() for text in texts)
                    if run.first_pass_path == "units"
                    else len(texts) > 1
                )
                if due and key not in run.completed_steps:
                    return key
        for step in (
            "adjudicate",
            "parse",
            "plan",
            "lookup",
        ):
            if step not in run.completed_steps:
                return step
        for index, task in enumerate(run.authority_plan):
            step = f"authority:{index}:{task['tool_id']}"
            if step not in run.completed_steps:
                return step
        for step in (
            "resolve",
            "normalize",
            "validate",
            "finalize",
        ):
            if step not in run.completed_steps:
                return step
        return "finalize"

    @staticmethod
    def parse(run: Run, asset_id: str, blobs: BlobStore | None = None) -> None:
        # Deliberately narrow deterministic parser for explicit key:value text.
        # Unstructured real labels remain reviewable and abstain; never guess mapping.
        # Every field classify bound, mandatory and optional; a run without
        # bound field groups keeps the profile's mandatory fields.
        groups = tuple(run.field_groups) or run.profile.mandatory_fields
        run.fields = {key: FieldValue() for key in groups}
        for transcript in run.transcripts:
            if not transcript.resolved or not transcript.text:
                continue
            for line in transcript.text.splitlines():
                key, sep, value = line.partition(":")
                key, value = key.strip(), value.strip()
                if not sep or key not in run.fields or not value:
                    continue
                # With a blob store each line's evidence keeps its record, as the field
                # harness does (field_resolution._ground), so it projects as recorded
                # evidence (#88).
                record = json.dumps(
                    {
                        "region_id": transcript.region_id,
                        "observation_ids": transcript.observation_ids,
                        "excerpt": line,
                    },
                    sort_keys=True,
                ).encode()
                stored = blobs is not None
                evidence = Evidence(
                    kind="literal",
                    asset_id=asset_id,
                    region_id=transcript.region_id,
                    observation_ids=transcript.observation_ids,
                    source="label",
                    locator=f"region:{transcript.region_id}",
                    excerpt=line,
                    raw_ref=blobs.put(record) if stored else None,
                    digest=hashlib.sha256(record).hexdigest() if stored else None,
                )
                run.evidence.append(evidence)
                old = run.fields[key]
                if old.literal and old.literal != value:
                    old.state = ValueState.AMBIGUOUS
                    old.reason = "Conflicting literal values"
                    old.evidence_ids.append(evidence.id)
                else:
                    run.fields[key] = FieldValue(
                        state=ValueState.SUPPORTED,
                        literal=value,
                        parsed=value,
                        evidence_ids=[evidence.id],
                        reason="Explicit labeled source line",
                    )

    def drain(
        self, principal: Principal, specimen_id: str, max_steps: int = 100
    ) -> Specimen:
        for _ in range(max_steps):
            specimen = self.step(principal, specimen_id)
            if (
                specimen.run.blocker == "external_outcome_unknown"
                or specimen.run.stage
                in {
                    "finalized",
                    "processing_blocked",
                    "retry_scheduled",
                    "paused",
                    "cancelled",
                }
            ):
                return specimen
        raise OperationalBlock("step_budget_exhausted")


# The steps an admin may reconcile by running them again: each makes exactly one
# external effect, a model reading, which answers from inputs the run already
# holds. No record is written twice, but the provider may bill a repeat again.
RECONCILABLE_READ_PREFIXES = ("transcribe:", "first_pass:")
# Stages in which an unknown outcome is never reconciled: a cancelled run must
# stay stopped, since a reconcile queues paid work, and a finished run has none.
RECONCILE_REFUSED_STAGES = frozenset({"cancelled", "finalized"})


def reconcilable_step(run: Run) -> str | None:
    """The step an unknown outcome blocks, when running it again is safe; else None.

    The ``reconcile`` run action clears an ``external_outcome_unknown`` blocker by
    letting the worker run the blocked step once more. That is only safe when a
    second run cannot repeat an effect the first one may already have had:

    - ``transcribe:<region>:<route>`` is one model reading of one label crop. Its
      result joins the run (``run.observations``) only when the call returns, so no
      reading is recorded twice. The isolated child writes content-addressed blobs
      before the run is saved, and ending it does not cancel a request the provider
      already accepted (bounded_effect.py), so a repeat may bill again.
    - ``first_pass:<region>`` is one model comparison of readings the run holds.
      Its decision replaces that region's earlier decision, so no decision is
      recorded twice, and a repeat may bill again in the same way.

    Everything else is refused: ``segment`` (a service call), ``lookup`` and
    ``authority:`` (source requests), ``parse`` (the organiser rewrites the run's
    fields and evidence in place and honours preserved human fields), field
    research (several paid calls and a program ledger), ``finalize`` and every step
    this function does not name. A step it cannot classify is a step it refuses.

    A cancelled run, a finished run and a run with a disposition are refused too.
    A paused run is allowed: the action clears its blocker and leaves it paused.

    The blocked step is the one ``Workflow.next_step`` names, the same function the
    worker used when it recorded the intent, and it must have been attempted: the
    intent raised ``run.attempts[step]`` before the call. A reading the run already
    holds for that label and route is never read a second time.
    """
    if run.blocker != "external_outcome_unknown":
        return None
    if run.stage in RECONCILE_REFUSED_STAGES or run.disposition is not None:
        return None
    step = Workflow.next_step(run)
    if not step.startswith(RECONCILABLE_READ_PREFIXES):
        return None
    if run.attempts.get(step, 0) < 1:
        return None
    parts = step.split(":")
    if parts[0] == "transcribe":
        if len(parts) != 3 or not all(parts[1:]):
            return None
        if any(o.region_id == parts[1] and o.route_id == parts[2] for o in run.observations):
            return None
    elif len(parts) != 2 or not parts[1]:
        return None
    return step


class SyntheticAdapters:
    """Explicit fixture generator. Never represents SAM 3 or live inference."""

    def __init__(
        self,
        blobs: BlobStore,
        text: str,
        alternate_text: str | tuple[str, ...] | list[str] | None = None,
    ):
        """Reader A reads ``text``. ``alternate_text`` is what the readers after
        it read instead: one text, for reader B, or one text each for readers B,
        C and so on. A reader with no alternate reads ``text``."""
        self.blobs, self.text, self.alternate = blobs, text, alternate_text

    def segment(self, specimen):
        if not specimen.run.profile.synthetic:
            raise OperationalBlock("synthetic_adapter_forbidden")
        return [
            Region(
                asset_id=specimen.asset.id,
                x=0,
                y=0,
                width=specimen.asset.width,
                height=specimen.asset.height,
                order=0,
                method="synthetic_fixture_region",
                version="1",
            )
        ]

    def transcribe(self, specimen, region, route):
        routes = specimen.run.profile.routes
        reader = routes.index(route) if route in routes else 0
        alternates = (
            ()
            if self.alternate is None
            else (self.alternate,)
            if isinstance(self.alternate, str)
            else tuple(self.alternate)
        )
        text = alternates[reader - 1] if 0 < reader <= len(alternates) else self.text
        raw = ("SYNTHETIC FIXTURE\n" + text).encode()
        ref = self.blobs.put(raw)
        return Observation(
            region_id=region.id,
            route_id=route,
            model_id="synthetic-" + route,
            provider="synthetic",
            prompt_version="fixture-v1",
            input_sha256=specimen.asset.sha256,
            literal_text=text,
            raw_ref=ref,
            raw_sha256=hashlib.sha256(raw).hexdigest(),
        )

    def first_pass(self, specimen, region, readings):
        if not specimen.run.profile.synthetic:
            raise OperationalBlock("synthetic_adapter_forbidden")
        from .first_pass import synthetic_decision

        return synthetic_decision(self.blobs, region, readings)

    def first_pass_units(self, specimen, region, readings):
        if not specimen.run.profile.synthetic:
            raise OperationalBlock("synthetic_adapter_forbidden")
        from .first_pass import synthetic_units

        return synthetic_units(self.blobs, region, readings)

    def lookup(self, name):
        raw = (
            '{"synthetic":true,"name":' + __import__("json").dumps(name) + "}"
        ).encode()
        return Lookup(
            provider="synthetic_taxonomy",
            adapter_version="fixture-v1",
            query={"name": name},
            status=LookupStatus.SUCCESS,
            candidates=[{"key": "synthetic:taxon:1", "scientificName": name}],
            raw_ref=self.blobs.put(raw),
            digest=hashlib.sha256(raw).hexdigest(),
        )


def store_reading_units(run: Run, entries: list[ReadingUnits], *, dropped=()) -> None:
    """The run's reading units with these labels' entries replaced and the `dropped`
    labels' entries removed, sorted by region order, set through the run's
    validate_assignment (its one-entry-per-label check)."""
    labels = {entry.label for entry in entries} | set(dropped)
    order = {region.id: index for index, region in enumerate(run.regions)}
    value = sorted(
        [*(entry for entry in run.reading_units if entry.label not in labels), *entries],
        key=lambda entry: order.get(entry.label, len(order)),
    )
    run.__pydantic_validator__.validate_assignment(run, "reading_units", value)


def crop_bytes(blobs: BlobStore, specimen: Specimen, region: Region) -> bytes:
    from .source_pixels import source_image

    with source_image(specimen.asset, blobs) as image:
        return region_png(image, region)
