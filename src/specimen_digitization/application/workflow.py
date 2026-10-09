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
    Evidence,
    FieldValue,
    FirstPassDecision,
    Lookup,
    LookupStatus,
    Observation,
    OPERATIONAL,
    Principal,
    Region,
    Run,
    Specimen,
    Transcript,
    ValueState,
)
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
from .reliability import AdapterFailure, retry_delay


LOGGER = logging.getLogger(__name__)

# Field research (field_research/step.py): one external, billable step that
# replaces plan..finalize for a run whose profile names a harness route, when
# SPECIMEN_RESEARCH_HARNESS=fields mounts it as `Workflow.field_research`.
FIELD_RESEARCH = "field_research"
# A run field research has completed reaches the handover again: the clearance
# rules only, nothing researched, external or paid (FieldResearchStep.recheck).
FIELD_RECHECK = "field_research_recheck"


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
        from .human_field_carry import KEY as CARRY_KEY, verify as verify_carries
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
        # Persist intent before network/model work. Crash with intent but no result is
        # blocked for explicit replay: provider calls may not support deduplication.
        if run.blocker == "external_outcome_unknown":
            if (
                run.lease_until
                and datetime.fromisoformat(run.lease_until) > self.clock()
            ):
                return specimen
            run.stage = "processing_blocked"
            return self.repository.save(
                principal,
                specimen,
                revision,
                f"unknown:{revision}",
                digest({"unknown": step}),
            )
        external = (
            step.startswith(("transcribe:", "first_pass:"))
            or step in {"segment", "lookup", FIELD_RESEARCH}
            or step.startswith("authority:")
            or (step == "parse" and hasattr(self.adapters, "extract"))
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
        issue = None
        if run.usage.steps >= policy.max_steps:
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
        elif (
            billable
            and not run.profile.synthetic
            and (cost is None or policy.approved_cost_limit_micros is None)
        ):
            issue = "approved_cost_budget_unavailable"
        elif retained_cost_issue:
            issue = retained_cost_issue
        elif (
            cost is not None
            and policy.approved_cost_limit_micros is not None
            and run.usage.reserved_cost_micros + retained_cost + cost
            > policy.approved_cost_limit_micros
        ):
            issue = "cost_budget_exhausted"
        if issue is None and billable and not run.profile.synthetic and self.reserve_retained_cost is not None:
            try:
                self.reserve_retained_cost(principal, specimen, step, cost)
            except OperationalBlock as error:
                issue = str(error)
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

            # The program's allowance (LANE.md T2b), once the circuit admits the call.
            allowance_issue = reserve_step(
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
        # A SAM 3 failure keeps its retry even past the budget (below).
        repeatable = False
        observed = len(run.observations)
        try:
            if step == "pin_dependencies":
                retained_carries = copy.deepcopy(run.dependencies.get(CARRY_KEY, {}))
                run.dependencies = (
                    self.adapters.pin_dependencies(run)
                    if hasattr(self.adapters, "pin_dependencies")
                    else {
                        "adapter": type(self.adapters).__name__,
                        "synthetic": run.profile.synthetic,
                    }
                )
                if CARRY_KEY in run.dependencies and run.dependencies[CARRY_KEY] != retained_carries:
                    raise OperationalBlock("preserved_human_field_provenance_unavailable")
                if retained_carries:
                    run.dependencies[CARRY_KEY] = retained_carries
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
                observation = self.adapters.transcribe(specimen, region, route)
                if observation.region_id != region.id or observation.route_id != route:
                    raise OperationalBlock("observation_contract_invalid")
                run.observations.append(observation)
            elif step.startswith("first_pass:"):
                region = next(r for r in run.regions if r.id == step.split(":", 1)[1])
                readings = [o for o in run.observations if o.region_id == region.id]
                decision = self.adapters.first_pass(specimen, region, readings)
                from .first_pass import UNRESOLVED_VERDICTS, g19_pick, is_material

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
                ):
                    raise OperationalBlock("first_pass_contract_invalid")
                run.first_pass_decisions = [
                    d for d in run.first_pass_decisions if d.region_id != region.id
                ] + [decision]
                call = decision.call
                run.usage.tokens += call.input_tokens + call.output_tokens
            elif step == "adjudicate":
                run.transcripts = []
                decisions = {d.region_id: d for d in run.first_pass_decisions}
                for region in run.regions:
                    readings = [o for o in run.observations if o.region_id == region.id]
                    texts = list(dict.fromkeys(o.literal_text for o in readings))
                    from .first_pass import adjudication_record
                    from .reading_evidence import ReadingEvidenceInput, align_readings

                    alignment = None
                    if len(readings) == 2:
                        alignment = align_readings(
                            *(
                                ReadingEvidenceInput(
                                    observation_id=o.id,
                                    region_id=region.id,
                                    source_ref=o.raw_ref,
                                    source_sha256=o.raw_sha256,
                                    text=o.literal_text,
                                )
                                for o in readings
                            )
                        )
                    measured = (
                        alignment is not None and alignment.status != "policy_blocked"
                    )
                    resolved = (
                        measured
                        and len(texts) == 1
                        and bool(texts[0].strip())
                        and not any(o.unreadable_spans for o in readings)
                    )
                    text, resolved, record = adjudication_record(
                        readings, texts, resolved, decisions.get(region.id)
                    )
                    run.transcripts.append(
                        Transcript(
                            region_id=region.id,
                            text=text,
                            observation_ids=[o.id for o in readings],
                            alternatives=texts,
                            resolved=resolved,
                            disagreement_ratio=(
                                alignment.edit_distance
                                / max(1, *(len(o.literal_text) for o in readings))
                            )
                            if measured
                            else None,
                            alignment_status=alignment.status
                            if alignment
                            else "policy_blocked",
                            alignment_algorithm="bounded-levenshtein-fraction-v1",
                            alignment_reasons=list(alignment.reasons)
                            if alignment
                            else ["independent_pair_incomplete"],
                            **record,
                        )
                    )
            elif step == "parse":
                proposal = specimen.model_copy(deep=True) if run.dependencies.get(CARRY_KEY) else specimen
                self.parse(proposal.run, specimen.asset.id, self.blobs)
                if hasattr(self.adapters, "extract"):
                    self.adapters.extract(proposal)
                if proposal is not specimen:
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
                run.completed_steps.append(step)
            if step not in {"finalize", FIELD_RESEARCH, FIELD_RECHECK}:
                run.stage = self.next_step(run).split(":")[0]
        except AdapterFailure as exc:
            circuit_failure = exc.status.value
            circuit_retry_after = exc.retry_after_seconds
            run.blocker = (
                "external_outcome_unknown" if exc.outcome_unknown else exc.code
            )
            run.stage = "processing_blocked"
            run.disposition = None
            if not exc.outcome_unknown and exc.status in {
                LookupStatus.RATE_LIMITED,
                LookupStatus.TIMEOUT,
                LookupStatus.PROVIDER,
            }:
                self.schedule_retry(run, step, exc.retry_after_seconds)
            # The SAM 3 service answers a repeat of a run's request from the
            # response it stored (sam3_server.RunSegmenter).
            repeatable = (
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
                outcome_unknown=exc.outcome_unknown,
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
        elapsed = max(0, self.monotonic() - started)
        if external and elapsed > effect_timeout and not repeatable:
            circuit_failure = "timeout"
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

    def schedule_retry(self, run, step, provider_seconds=None):
        if run.attempts.get(step, 0) < run.profile.execution.max_attempts:
            delay = retry_delay(
                run.attempts.get(step, 1), provider_seconds, self.random_value
            )
            run.next_retry_at = (self.clock() + timedelta(seconds=delay)).isoformat()
            run.stage = "retry_scheduled"
        else:
            run.dead_letter = True
            run.blocker = "retry_budget_exhausted:" + (run.blocker or "adapter_failure")

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
            # Differing readings get the LLM first pass (HARNESS.md section 3).
            for region in run.regions:
                texts = {
                    o.literal_text for o in run.observations if o.region_id == region.id
                }
                key = f"first_pass:{region.id}"
                if len(texts) > 1 and key not in run.completed_steps:
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


class SyntheticAdapters:
    """Explicit fixture generator. Never represents SAM 3 or live inference."""

    def __init__(self, blobs: BlobStore, text: str, alternate_text: str | None = None):
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
        text = (
            self.alternate
            if route == specimen.run.profile.routes[1] and self.alternate is not None
            else self.text
        )
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


def crop_bytes(blobs: BlobStore, specimen: Specimen, region: Region) -> bytes:
    from .source_pixels import source_image

    with source_image(specimen.asset, blobs) as image:
        return region_png(image, region)
