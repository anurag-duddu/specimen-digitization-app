"""The field harness in the workflow's `parse` step (HARNESS.md section 14).

The parent builds the isolated model child's input from the run: every reading
handed to the harness (G40), the profile's field plan and rules. The child runs
the harness (section 11) with the production tools, and the parent merges what
it returns. A harness tool's operational outcome is returned to the workflow,
which blocks the run once the model call has settled (QUE-005).
"""

from __future__ import annotations

import os
from functools import partial

from ..model_gateway import HuggingFaceModelGateway
from ..prompts import PromptName, ResolvedPrompt
from .domain import (
    Evidence,
    FieldValue,
    HarnessCall,
    Lookup,
    RunFinding,
    ToolCallRecord,
)


def harness_payload(run) -> dict:
    """The child's input: every reading handed to the harness, the fields with
    their tools, and the profile's date rules and harness knowledge."""
    snapshot = run.profile_snapshot or {}
    readings = []
    for transcript in run.transcripts:
        if transcript.handoffs:
            readings += [
                {
                    "region_id": transcript.region_id,
                    "observation_id": handoff.observation_id,
                    "role": handoff.role,
                    "text": handoff.handed_text,
                    "note": handoff.note,
                }
                for handoff in transcript.handoffs
            ]
        elif transcript.resolved and transcript.text:
            # A region decided before the first pass kept no handoffs.
            readings.append(
                {
                    "region_id": transcript.region_id,
                    "observation_id": (
                        transcript.observation_ids or [transcript.region_id]
                    )[0],
                    "role": "decided_transcript",
                    "text": transcript.text,
                    "note": None,
                }
            )
    field_tools = snapshot.get("field_tools") or {}
    return {
        "readings": readings,
        "plan": {
            "mandatory": list(run.profile.mandatory_fields),
            "optional": list(snapshot.get("optional_fields") or []),
            "tools": {key: tools[0] for key, tools in field_tools.items() if tools},
        },
        "date_rules": snapshot.get("date_rules"),
        "knowledge": snapshot.get("harness_knowledge"),
    }


def harness_direct(adapter, specimen, payload: dict) -> dict:
    """Run the harness in the isolated model child."""
    from ..provider_privacy import PrivateProviderModel
    from .field_harness import FieldPlan, run_harness
    from .field_resolution import Reading
    from .field_validators import catalog_number_validator, date_parser
    from .geography_tool import geocode_locality
    from .harness_knowledge import KNOWLEDGE, instructions_for
    from .harness_ledger import ToolLedger, Tools
    from .taxonomy_tool import verify_taxon
    from .workflow import OperationalBlock

    if os.getenv("SPECIMEN_APPROVED_INFERENCE") != "true":
        raise OperationalBlock("provider_data_policy_and_spending_approval_required")
    run = specimen.run
    route_id = run.profile.harness_route
    timeout = run.profile.execution.effect_timeout_for_step("parse")
    gateway = HuggingFaceModelGateway(timeout_seconds=timeout / 2)
    if route_id is None or route_id not in gateway.routes:
        raise OperationalBlock("pinned_model_route_unavailable")
    selected = gateway.route(route_id)
    pinned = {"model_id": selected.model_id, "provider": selected.provider}
    if run.dependencies.get("routes", {}).get(route_id) != pinned:
        raise OperationalBlock("pinned_model_route_unavailable")
    try:
        prompt = ResolvedPrompt.model_validate(
            run.dependencies["prompts"][PromptName.FIELD_HARNESS.value]
        )
    except (KeyError, ValueError) as exc:
        raise OperationalBlock("pinned_prompt_unavailable") from exc
    knowledge = payload.get("knowledge") or {}
    try:
        instructions = instructions_for(
            prompt.text, knowledge.get("id"), knowledge.get("version")
        )
        aliases = KNOWLEDGE[knowledge["id"]].PLACE_ALIASES
    except (KeyError, ValueError) as exc:
        raise OperationalBlock("harness_knowledge_unavailable") from exc
    tools = Tools(
        verify_taxon=partial(verify_taxon, blobs=adapter.blobs),
        geocode=partial(geocode_locality, blobs=adapter.blobs, aliases=aliases),
        parse_date=partial(date_parser, date_rules=payload.get("date_rules")),
        check_catalog_number=catalog_number_validator,
    )
    plan = FieldPlan(
        mandatory=tuple(payload["plan"]["mandatory"]),
        optional=tuple(payload["plan"]["optional"]),
        tools=payload["plan"]["tools"],
    )
    readings = [
        Reading(r["region_id"], r["observation_id"], r["role"], r["text"])
        for r in payload["readings"]
    ]
    notes = {r["observation_id"]: r["note"] for r in payload["readings"] if r["note"]}
    ledger = ToolLedger(tools, asset_id=specimen.asset.id)
    outcome = run_harness(
        PrivateProviderModel(gateway.model_for(route_id)),
        instructions,
        plan=plan,
        readings=readings,
        notes=notes,
        ledger=ledger,
        asset_id=specimen.asset.id,
        blobs=adapter.blobs,
        timeout_seconds=timeout,
        knowledge_id=knowledge["id"],  # PLAN 4.8's filter reads its tables.
    )
    usage = outcome.usage
    google = sum(1 for c in outcome.tool_calls if c.source == "google-maps-geocoding")
    return {
        "fields": {k: v.model_dump(mode="json") for k, v in outcome.fields.items()},
        "evidence": [e.model_dump(mode="json") for e in outcome.evidence],
        "findings": [f.model_dump(mode="json") for f in outcome.findings],
        "tool_calls": [c.model_dump(mode="json") for c in outcome.tool_calls],
        "lookups": [lookup.model_dump(mode="json") for lookup in outcome.lookups],
        "blocker": outcome.blocker,
        "failure": outcome.failure,
        "usage": {
            "input_tokens": getattr(usage, "input_tokens", 0) or 0,
            "output_tokens": getattr(usage, "output_tokens", 0) or 0,
            "requests": getattr(usage, "requests", 0) or 0,
        },
        # The model call and its geocoding, for the lane's cost record.
        "call": {
            "route_id": route_id,
            "model_id": selected.model_id,
            "provider": selected.provider,
            "geocoding_requests": google,
        },
    }


def merge_harness(run, value: dict) -> str | None:
    """Merge the child's outcome into the run, and return a harness tool's
    operational block for the workflow to raise once the call has settled."""
    from .workflow import OperationalBlock

    plan = harness_payload(run)["plan"]
    expected = {*plan["mandatory"], *plan["optional"]}
    fields = {k: FieldValue.model_validate(v) for k, v in value["fields"].items()}
    usage = value["usage"]
    counts = (usage["input_tokens"], usage["output_tokens"], usage["requests"])
    if set(fields) != expected or any(type(n) is not int or n < 0 for n in counts):
        raise OperationalBlock("external_outcome_unknown")
    # Tokens a provider did not report are unknown, not zero (S3's record_step
    # then keeps the step reserved).
    reported = usage["input_tokens"] > 0 or usage["requests"] == 0
    try:
        call = HarnessCall(
            attempt=run.attempts.get("parse", 1),
            **value["call"],
            requests=usage["requests"],
            input_tokens=usage["input_tokens"] if reported else None,
            output_tokens=usage["output_tokens"] if reported else None,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise OperationalBlock("external_outcome_unknown") from exc
    run.fields = fields
    run.evidence.extend(Evidence.model_validate(e) for e in value["evidence"])
    run.findings.extend(RunFinding.model_validate(f) for f in value["findings"])
    run.tool_calls.extend(ToolCallRecord.model_validate(c) for c in value["tool_calls"])
    run.lookups.extend(Lookup.model_validate(item) for item in value["lookups"])
    run.usage.tokens += usage["input_tokens"] + usage["output_tokens"]
    run.harness_calls.append(call)
    run.harness_failure = value["failure"]
    return value["blocker"]
