"""Trusted model factories with minimal context and whole-effect process deadlines."""

import json
from pathlib import Path
from types import SimpleNamespace

from ..observability import isolated_model_span, model_trace_context
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
from .reliability import AdapterFailure
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
            run.fields = {
                k: FieldValue.model_validate(v) for k, v in payload["fields"].items()
            }
            run.evidence = []
            run.usage = BudgetUsage()
            adapter._extract_direct(specimen)
            value = {
                "fields": {k: v.model_dump(mode="json") for k, v in run.fields.items()},
                "evidence": [e.model_dump(mode="json") for e in run.evidence],
                "tokens": run.usage.tokens,
            }
        else:
            raise ValueError("Unknown trusted model operation")
        return json.dumps({"status": "completed", "value": value}).encode()
    except AdapterFailure as exc:
        return json.dumps(
            {
                "status": "adapter_failure",
                "code": exc.code,
                "lookup_status": exc.status.value,
                "retry_after_seconds": exc.retry_after_seconds,
                "outcome_unknown": exc.outcome_unknown,
            }
        ).encode()
    except OperationalBlock as exc:
        # Only application-owned fixed codes cross this boundary. Provider error
        # strings and tracebacks are suppressed by the worker process runner.
        return json.dumps({"status": "blocked", "code": str(exc)}).encode()


def invoke_model(
    adapter, specimen, operation, *, region=None, route=None, readings=None
):
    from .domain import LookupStatus
    from .workflow import OperationalBlock

    run = specimen.run
    payload = {
        "operation": operation,
        "telemetry": model_trace_context(specimen.id, run.id),
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
        step = "first_pass:" + region.id
    else:
        # Resolved source is authorized extraction context. Raw independent
        # observations, prior runs, audit logs and authority outputs are excluded.
        payload.update(
            transcripts=[
                # A resolved transcript with its text as its only alternative, and
                # without its first-pass handoffs, differences and call (HARNESS.md
                # section 4).
                t.model_copy(update={"alternatives": [t.text]}).model_dump(
                    mode="json", exclude={"handoffs", "differences", "first_pass_call"}
                )
                for t in run.transcripts
                if t.resolved and t.text
            ],
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
    if result.status != "completed" or not result.cleanup_complete:
        raise OperationalBlock("external_outcome_unknown")
    body = json.loads(result.value)
    if body["status"] == "adapter_failure":
        raise AdapterFailure(
            body["code"],
            LookupStatus(body["lookup_status"]),
            retry_after_seconds=body["retry_after_seconds"],
            outcome_unknown=body["outcome_unknown"],
        )
    if body["status"] == "blocked":
        raise OperationalBlock(body["code"])
    if body["status"] != "completed":
        raise OperationalBlock("external_outcome_unknown")
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
        return decision
    fields = {k: FieldValue.model_validate(v) for k, v in value["fields"].items()}
    evidence = [Evidence.model_validate(e) for e in value["evidence"]]
    tokens = value["tokens"]
    if fields.keys() != run.fields.keys() or type(tokens) is not int or tokens < 0:
        raise OperationalBlock("external_outcome_unknown")
    run.fields = fields
    run.evidence.extend(evidence)
    run.usage.tokens += tokens
