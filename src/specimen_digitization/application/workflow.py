"""Checkpointed application workflow; external engines can dispatch one step at a time."""

from __future__ import annotations
import hashlib
import io
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
from .policy import finalize
from .storage import BlobStore, Repository, digest


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
        self, repository: Repository, blobs: BlobStore, adapters: PipelineAdapters
    ):
        self.repository, self.blobs, self.adapters = repository, blobs, adapters

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
            if run.next_retry_at and datetime.fromisoformat(
                run.next_retry_at
            ) > datetime.now(timezone.utc):
                return specimen
            run.blocker = None
            run.next_retry_at = None
        revision = specimen.version
        step = self.next_step(run)
        # Persist intent before network/model work. Crash with intent but no result is
        # blocked for explicit replay: provider calls may not support deduplication.
        if run.blocker == "external_outcome_unknown":
            if run.lease_until and datetime.fromisoformat(
                run.lease_until
            ) > datetime.now(timezone.utc):
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
        if external:
            run.blocker = "external_outcome_unknown"
            run.lease_until = (
                datetime.now(timezone.utc) + timedelta(minutes=5)
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
        try:
            if step == "classify":
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
                finalize(run)
            run.blocker = None
            run.lease_until = None
            run.completed_steps.append(step)
            if step != "finalize":
                run.stage = self.next_step(run).split(":")[0]
        except OperationalBlock as exc:
            run.blocker = str(exc)
            run.stage = "processing_blocked"
            run.disposition = None
            if run.blocker in {
                "taxonomy_rate_limited",
                "taxonomy_timeout",
                "taxonomy_provider_error",
            }:
                if run.attempts.get(step, 0) < 3:
                    delay = run.lookups[-1].retry_after_seconds or (
                        2 ** run.attempts.get(step, 1)
                    )
                    run.next_retry_at = (
                        datetime.now(timezone.utc) + timedelta(seconds=delay)
                    ).isoformat()
                    run.stage = "retry_scheduled"
                else:
                    run.dead_letter = True
                    run.blocker = "retry_budget_exhausted:" + run.blocker
        except Exception:
            # Do not expose raw exceptions containing provider headers or source text.
            run.blocker = "stage_failed_inspect_private_worker_logs"
            run.stage = "processing_blocked"
            run.disposition = None
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

    @staticmethod
    def next_step(run: Run) -> str:
        for step in ("classify", "segment"):
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
