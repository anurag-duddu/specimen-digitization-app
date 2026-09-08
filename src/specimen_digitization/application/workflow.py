"""Checkpointed application workflow; external engines can dispatch one step at a time."""

from __future__ import annotations
import hashlib
import io
import time
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher
from typing import Protocol
from PIL import Image
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
    ):
        self.repository, self.blobs, self.adapters = repository, blobs, adapters
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.monotonic = monotonic or time.monotonic
        self.random_value = random_value

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
        if run.stage in {"finalized", "paused", "cancelled", "processing_blocked"}:
            return specimen
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
            or (step == "parse" and hasattr(self.adapters, "extract"))
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
            else policy.request_cost_reservation_micros
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
            elif step == "classify":
                run.stage = "classify"
                # The selected profile is explicit intake context, never a fabricated classifier.
                run.completed_steps.append("classification_selected_at_intake")
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
                    resolved = (
                        len(texts) == 1
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
                            disagreement_ratio=1
                            - SequenceMatcher(None, texts[0], texts[-1]).ratio()
                            if texts
                            else 1,
                        )
                    )
            elif step == "parse":
                self.parse(run, specimen.asset.id)
                if hasattr(self.adapters, "extract"):
                    self.adapters.extract(specimen)
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
                finalize(run)
            run.blocker = None
            run.lease_until = None
            run.completed_steps.append(step)
            if step != "finalize":
                run.stage = self.next_step(run).split(":")[0]
        except AdapterFailure as exc:
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
        return self.repository.save(
            principal,
            specimen,
            revision,
            f"result:{revision}",
            digest({"step": step, "run": run.id}),
        )

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
        for step in ("pin_dependencies", "classify", "segment"):
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
    with Image.open(io.BytesIO(blobs.get(specimen.asset.blob_ref))) as image:
        crop = image.crop(
            (region.x, region.y, region.x + region.width, region.y + region.height)
        ).convert("RGB")
        stream = io.BytesIO()
        crop.save(stream, format="PNG")
        return stream.getvalue()
