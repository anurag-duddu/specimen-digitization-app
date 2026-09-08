"""Checkpointed application workflow; external engines can dispatch one step at a time."""

from __future__ import annotations
import hashlib
import time
from datetime import datetime, timezone, timedelta
from typing import Protocol
import logfire
from .domain import (
    AuditEvent,
    Evidence,
    FieldValue,
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
from .policy import finalize
from .storage import BlobStore, Repository, digest
from .reliability import AdapterFailure, retry_delay


class OperationalBlock(RuntimeError):
    """Sanitized actionable code, never an exception containing provider credentials."""


class PipelineAdapters(Protocol):
    def segment(self, specimen: Specimen) -> list[Region]: ...
    def transcribe(
        self, specimen: Specimen, region: Region, route: str
    ) -> Observation: ...
    def lookup(self, name: str) -> Lookup: ...


class Workflow:
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
    ):
        self.repository, self.blobs, self.adapters = repository, blobs, adapters
        self.admission = admission
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
        if self.admission is not None:
            self.admission.admit(specimen)
        if run.stage == "retry_scheduled":
            if (
                run.next_retry_at
                and datetime.fromisoformat(run.next_retry_at) > self.clock()
            ):
                return specimen
            run.blocker = None
            run.next_retry_at = None
        revision = specimen.version
        step = self.next_step(run)
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
            step.startswith("transcribe:")
            or step in {"segment", "lookup"}
            or step.startswith("authority:")
            or (step == "parse" and hasattr(self.adapters, "extract"))
            or (
                step == "classify"
                and self.classifier is not None
                and getattr(self.classifier, "external", True)
            )
        )
        policy = run.profile.execution
        external_weight = (
            2
            if (step.startswith("transcribe:") or step == "parse")
            and not run.profile.synthetic
            else 1
        )
        billable = external and (
            step.startswith("transcribe:") or step in {"parse", "segment", "classify"}
        )
        reservation_tokens = 16000 if billable and not run.profile.synthetic else 0
        cost = (
            0
            if run.profile.synthetic or not billable
            else (
                policy.stage_cost_reservations.for_step(step)
                if policy.stage_cost_reservations is not None
                else policy.request_cost_reservation_micros
            )
        )
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
            + (policy.external_timeout_seconds if external else 0)
            > policy.max_active_seconds
        ):
            issue = "active_time_budget_exhausted"
        elif (
            billable
            and not run.profile.synthetic
            and (cost is None or policy.approved_cost_limit_micros is None)
        ):
            issue = "approved_cost_budget_unavailable"
        elif (
            cost is not None
            and policy.approved_cost_limit_micros is not None
            and run.usage.reserved_cost_micros + cost
            > policy.approved_cost_limit_micros
        ):
            issue = "cost_budget_exhausted"
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
        if external:
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
        run.usage.steps += 1
        if external:
            run.usage.external_calls += external_weight
            run.usage.reserved_tokens += reservation_tokens
            run.usage.reserved_cost_micros += cost or 0
            run.usage.reserved_active_seconds += policy.external_timeout_seconds
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
        try:
            if step == "pin_dependencies":
                run.dependencies = (
                    self.adapters.pin_dependencies(run)
                    if hasattr(self.adapters, "pin_dependencies")
                    else {
                        "adapter": type(self.adapters).__name__,
                        "synthetic": run.profile.synthetic,
                    }
                )
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
            elif step.startswith("transcribe:"):
                _, region_id, route = step.split(":", 2)
                region = next(r for r in run.regions if r.id == region_id)
                observation = self.adapters.transcribe(specimen, region, route)
                if observation.region_id != region.id or observation.route_id != route:
                    raise OperationalBlock("observation_contract_invalid")
                run.observations.append(observation)
            elif step == "adjudicate":
                run.transcripts = []
                for region in run.regions:
                    readings = [o for o in run.observations if o.region_id == region.id]
                    texts = list(dict.fromkeys(o.literal_text for o in readings))
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
                    run.transcripts.append(
                        Transcript(
                            region_id=region.id,
                            text=texts[0] if resolved else None,
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
                        )
                    )
            elif step == "parse":
                self.parse(run, specimen.asset.id)
                if hasattr(self.adapters, "extract"):
                    self.adapters.extract(specimen)
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
                    outcome = self.adapters.lookup(name)
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
            if step.startswith("authority:"):
                execute_phase(specimen, "lookup", self.blobs)
            if step in {"parse", "plan", "lookup", "resolve", "normalize", "validate"}:
                execute_phase(specimen, step, self.blobs)
            if run.stage != "processing_blocked":
                run.blocker = None
            run.lease_until = None
            run.completed_steps.append(step)
            if step != "finalize":
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
        except OperationalBlock as exc:
            circuit_failure = str(exc).removeprefix("taxonomy_")
            run.blocker = str(exc)
            run.stage = "processing_blocked"
            run.disposition = None
            if run.blocker in {
                "taxonomy_rate_limited",
                "taxonomy_timeout",
                "taxonomy_provider_error",
            }:
                self.schedule_retry(run, step, run.lookups[-1].retry_after_seconds)
        except Exception:
            circuit_failure = "provider_error"
            # Do not expose raw exceptions containing provider headers or source text.
            run.blocker = (
                "external_outcome_unknown"
                if external
                else "stage_failed_inspect_private_worker_logs"
            )
            run.stage = "processing_blocked"
            run.disposition = None
        elapsed = max(0, self.monotonic() - started)
        if external and elapsed > policy.external_timeout_seconds:
            circuit_failure = "timeout"
            specimen = reserved
            run = specimen.run
            run.blocker = "external_outcome_unknown"
            run.stage = "processing_blocked"
            run.disposition = None
            run.reasons = ["external_stage_deadline_exceeded"]
        run.usage.active_seconds += elapsed
        run.usage.tokens += max(
            0,
            sum(o.input_tokens + o.output_tokens for o in run.observations)
            - previous_tokens,
        )
        if external and run.blocker != "external_outcome_unknown":
            run.lease_until = None
            run.usage.reserved_active_seconds = max(
                0, run.usage.reserved_active_seconds - policy.external_timeout_seconds
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
    def parse(run: Run, asset_id: str) -> None:
        # Deliberately narrow deterministic parser for explicit key:value text.
        # Unstructured real labels remain reviewable and abstain; never guess mapping.
        run.fields = {key: FieldValue() for key in run.profile.mandatory_fields}
        for transcript in run.transcripts:
            if not transcript.resolved or not transcript.text:
                continue
            for line in transcript.text.splitlines():
                key, sep, value = line.partition(":")
                key, value = key.strip(), value.strip()
                if not sep or key not in run.fields or not value:
                    continue
                evidence = Evidence(
                    kind="literal",
                    asset_id=asset_id,
                    region_id=transcript.region_id,
                    observation_ids=transcript.observation_ids,
                    source="label",
                    locator=f"region:{transcript.region_id}",
                    excerpt=line,
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
