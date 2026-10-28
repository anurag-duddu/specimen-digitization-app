"""Trusted model factories with minimal context and whole-effect process deadlines."""

import json
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

from ..observability import isolated_model_span, model_trace_context, tenant_ids
from .bounded_effect import run_isolated
from .domain import (
    Asset,
    BudgetUsage,
    Evidence,
    FieldValue,
    FirstPassDecision,
    Observation,
    Profile,
    Region,
    Transcript,
)
from .field_resolution import Reading
from .organiser import extraction_readings
from .reading_units import ReadingUnits
from .reliability import (
    AdapterFailure,
    ReadingStopped,
    checked_usage,
    extraction_failure_is_recoverable,
    first_pass_failure_is_recoverable,
    reader_failure_is_recoverable,
)
from .storage import LocalBlobs


def storage_descriptor(blobs):
    from .production import GcsBlobs
    from .workflow import OperationalBlock

    if isinstance(blobs, LocalBlobs):
        return {"kind": "local", "root": str(blobs.root)}
    if isinstance(blobs, GcsBlobs):
        return {"kind": "gcs", "bucket": blobs.bucket.name}
    raise OperationalBlock("model_storage_not_supported")


def model_child(payload):
    with isolated_model_span(
        payload.get("telemetry", {}),
        operation=payload["operation"],
        region_id=payload.get("region", {}).get("id"),
        route_id=payload.get("route"),
    ) as span:
        result = _model_child(payload)
        body = json.loads(result)
        span.set_attribute("specimen.model.outcome", body["status"])
        if body["status"] == "completed" and payload["operation"] == "transcribe":
            # The existing persisted observation ID links the private evidence
            # record to this span without logging prompts, responses, or blobs.
            span.set_attribute(
                "specimen.observation.id", body["value"]["observation"]["id"]
            )
        return result


def _model_child(payload):
    # Imports, credential discovery, model construction, source decode and all
    # provenance writes occur after the hard parent's clock has started.
    from .production import GcsBlobs, ProductionAdapters
    from .workflow import OperationalBlock

    try:
        descriptor = payload["storage"]
        blobs = (
            LocalBlobs(Path(descriptor["root"]))
            if descriptor["kind"] == "local"
            else GcsBlobs(descriptor["bucket"])
        )
        adapter = ProductionAdapters(blobs)
        run = SimpleNamespace(
            profile=Profile.model_validate(payload["profile"]),
            dependencies=payload["dependencies"],
        )
        specimen = SimpleNamespace(
            asset=Asset.model_validate(payload["asset"]), run=run
        )
        if payload["operation"] == "transcribe":
            observation = adapter._transcribe_direct(
                specimen, Region.model_validate(payload["region"]), payload["route"]
            )
            value = {"observation": observation.model_dump(mode="json")}
        elif payload["operation"] == "first_pass" and payload.get("first_pass_path") == "units":
            # The units path (first_pass.SETTING): the label's units beside the decision.
            from .first_pass import first_pass_units_direct

            decision, units = first_pass_units_direct(
                adapter,
                specimen,
                Region.model_validate(payload["region"]),
                [Observation.model_validate(o) for o in payload["readings"]],
            )
            value = {
                "decision": decision.model_dump(mode="json"),
                "units": units.model_dump(mode="json"),
            }
        elif payload["operation"] == "first_pass":
            from .first_pass import first_pass_direct

            decision = first_pass_direct(
                adapter,
                specimen,
                Region.model_validate(payload["region"]),
                [Observation.model_validate(o) for o in payload["readings"]],
            )
            value = {"decision": decision.model_dump(mode="json")}
        elif payload["operation"] == "extract":
            run.transcripts = [
                Transcript.model_validate(t) for t in payload["transcripts"]
            ]
            run.readings = [Reading(**r) for r in payload["readings"]]
            run.fields = {
                k: FieldValue.model_validate(v) for k, v in payload["fields"].items()
            }
            run.evidence = []
            run.usage = BudgetUsage()
            usage = adapter._extract_direct(specimen)
            value = {
                "fields": {k: v.model_dump(mode="json") for k, v in run.fields.items()},
                "evidence": [e.model_dump(mode="json") for e in run.evidence],
                "tokens": run.usage.tokens,
                # Its input and output tokens apart, so parse can be priced.
                "usage": usage,
            }
        else:
            raise ValueError("Unknown trusted model operation")
        return json.dumps({"status": "completed", "value": value}).encode()
    except ReadingStopped as exc:
        # A reading stopped by its token limits crosses as a known status (#153).
        return json.dumps(
            {"status": "stopped", "code": exc.code, "usage": exc.usage}
        ).encode()
    except AdapterFailure as exc:
        return json.dumps(
            {
                "status": "adapter_failure",
                "code": exc.code,
                "lookup_status": exc.status.value,
                "retry_after_seconds": exc.retry_after_seconds,
                "outcome_unknown": exc.outcome_unknown,
                # A refusal before any work (reliability.AdapterFailure) costs nothing.
                "refused": exc.refused,
                # A malformed answer's reported tokens (reliability.reported_usage).
                "usage": exc.usage,
            }
        ).encode()
    except OperationalBlock as exc:
        # Only application-owned fixed codes cross this boundary. Provider error
        # strings and tracebacks are suppressed by the worker process runner.
        return json.dumps({"status": "blocked", "code": str(exc)}).encode()


def child_without_answer(run, operation, reason):
    """The failure of a model child that ended without an answer.

    Whatever ended it (a deadline, a kill, a transport error or any exception
    the child does not map, whose text never crosses the process boundary), the
    parent cannot tell whether the provider answered. A reader or ordinary
    first-pass comparison is safe to repeat within its existing attempt and
    financial limits; its uncertain cost stays reserved. Other operations
    retain an unknown outcome that blocks the run.
    """
    from .domain import LookupStatus
    from .workflow import OperationalBlock

    comparison = first_pass_failure_is_recoverable(run, operation) or (
        extraction_failure_is_recoverable(run, operation)
    )
    if not (
        reader_failure_is_recoverable(run, operation)
        or (comparison and reason in {"deadline_exceeded", "worker_process_exit"})
    ):
        return OperationalBlock("external_outcome_unknown")
    prefix = {"first_pass": "first_pass_", "extract": "extract_"}.get(operation, "reader_")
    return AdapterFailure(
        prefix + reason,
        LookupStatus.TIMEOUT if reason == "deadline_exceeded" else LookupStatus.PROVIDER,
        outcome_unknown=comparison,
    )


def invoke_model(
    adapter, specimen, operation, *, region=None, route=None, readings=None
):
    from .domain import LookupStatus
    from .workflow import OperationalBlock

    run = specimen.run
    payload = {
        "operation": operation,
        "telemetry": model_trace_context(specimen.id, run.id, **tenant_ids(specimen)),
        "storage": storage_descriptor(adapter.blobs),
        "asset": specimen.asset.model_dump(mode="json"),
        "profile": run.profile.model_dump(mode="json"),
        "dependencies": {
            k: run.dependencies[k]
            for k in ("routes", "prompts")
            if k in run.dependencies
        },
    }
    step = operation
    if operation == "transcribe":
        payload.update(region=region.model_dump(mode="json"), route=route)
        step = "transcribe:region:route"
    elif operation == "first_pass":
        # The first pass compares the region's raw readings (HARNESS.md 3).
        payload.update(
            region=region.model_dump(mode="json"),
            readings=[o.model_dump(mode="json") for o in readings],
        )
        if run.first_pass_path == "units":
            # The child follows the run's path, never its own process's switch.
            payload["first_pass_path"] = "units"
        step = "first_pass:" + region.id
    else:
        # The organiser reads every reading of every label, decided or raw: the
        # owner's message of 2026-10-03, which reverses HARNESS.md section 4's old
        # rule that the extraction call gets the decided text alone. Prior runs,
        # audit logs, authority outputs and the first pass's notes, differences and
        # call stay out.
        payload.update(
            transcripts=[
                # A resolved transcript with its text as its only alternative.
                t.model_copy(update={"alternatives": [t.text]}).model_dump(
                    mode="json", exclude={"handoffs", "differences", "first_pass_call"}
                )
                for t in run.transcripts
                if t.resolved and t.text
            ],
            readings=[asdict(r) for r in extraction_readings(run)],
            fields={k: v.model_dump(mode="json") for k, v in run.fields.items()},
        )
    result = run_isolated(
        adapter.model_effect or model_child,
        payload,
        run.profile.execution.effect_timeout_for_step(step),
        4 * 1024 * 1024,
        max_input_bytes=4 * 1024 * 1024,
        trace_required=True,
    )
    comparison = first_pass_failure_is_recoverable(run, operation) or (
        extraction_failure_is_recoverable(run, operation)
    )
    if not result.cleanup_complete and comparison:
        # No automatic comparison or extraction retry while its old child might
        # still run.
        raise OperationalBlock("external_outcome_unknown")
    if result.status != "completed" or not result.cleanup_complete:
        reason = result.status if result.status != "completed" else "cleanup_incomplete"
        if operation in {"first_pass", "extract"} and result.status == "worker_failed":
            # The broad status also includes malformed input and invalid IPC.
            # Only a child that exited after starting gets first-pass recovery;
            # do not turn an opaque call/contract failure into a provider retry.
            reason = result.reason
        raise child_without_answer(
            run,
            operation,
            reason,
        )
    body = json.loads(result.value)
    if body["status"] == "adapter_failure":
        raise AdapterFailure(
            body["code"],
            LookupStatus(body["lookup_status"]),
            retry_after_seconds=body["retry_after_seconds"],
            outcome_unknown=body["outcome_unknown"],
            refused=body.get("refused") is True,
            usage=checked_usage(body.get("usage")),
        )
    if body["status"] == "blocked":
        raise OperationalBlock(body["code"])
    if body["status"] == "stopped":
        raise ReadingStopped(body["code"], checked_usage(body.get("usage")))
    if body["status"] != "completed":
        raise child_without_answer(run, operation, "unrecognized_answer")
    value = body["value"]
    if operation == "transcribe":
        observation = Observation.model_validate(value["observation"])
        if (
            observation.region_id != region.id
            or observation.route_id != route
            or observation.input_asset_id != specimen.asset.id
        ):
            raise OperationalBlock("external_outcome_unknown")
        return observation
    if operation == "first_pass":
        decision = FirstPassDecision.model_validate(value["decision"])
        if (
            decision.region_id != region.id
            or decision.call.route_id != run.profile.first_pass_route
            or decision.call.input_asset_id != specimen.asset.id
        ):
            raise OperationalBlock("external_outcome_unknown")
        if run.first_pass_path != "units":
            return decision
        # The units path: the parent validates the label's units as the run stores them
        # (reading_units.ReadingUnits); the workflow's step checks them against the readings.
        try:
            units = ReadingUnits.model_validate(value["units"])
        except (KeyError, TypeError, ValueError) as exc:
            raise OperationalBlock("external_outcome_unknown") from exc
        if units.label != region.id:
            raise OperationalBlock("external_outcome_unknown")
        return decision, units
    fields = {k: FieldValue.model_validate(v) for k, v in value["fields"].items()}
    evidence = [Evidence.model_validate(e) for e in value["evidence"]]
    tokens = value["tokens"]
    if fields.keys() != run.fields.keys() or type(tokens) is not int or tokens < 0:
        raise OperationalBlock("external_outcome_unknown")
    run.fields = fields
    run.evidence.extend(evidence)
    run.usage.tokens += tokens
    usage = checked_usage(value.get("usage"))
    # The extraction's tokens, priced only when they are the tokens it counted.
    return usage if usage and sum(usage.values()) == tokens else None
