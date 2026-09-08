"""Bind pure evidence phases to verified application sources and immutable artifacts."""

import hashlib
from .blob_limits import BlobTooLarge

from .authority_registry import (
    AuthorityResult,
    AuthorityCandidate,
    canonical,
    digest as bytes_digest,
)
from .domain import LookupStatus, Disposition
from .evidence_harness import (
    HarnessSpec,
    HarnessBudget,
    PhaseSpec,
    PhaseInput,
    PhaseResult,
    SourceLiteral,
    FieldProposal,
    Finding,
    BudgetUsage,
    run_phase,
)
from .integrity import verify_evidence, EvidenceIntegrityError
from .review_risk import RiskSignal, review_risk
from .reading_evidence import (
    ReadingEvidenceInput,
    align_readings,
    summarize_reading,
    reading_risk_evidence,
)

PHASES = ("parse", "plan", "lookup", "resolve", "normalize", "validate", "finalize")


def source_literals(specimen, blobs):
    verify_evidence(specimen, blobs)
    run = specimen.run
    literals = []
    for key, field in run.fields.items():
        if not field.literal:
            continue
        for evidence in run.evidence:
            if evidence.id not in field.evidence_ids or evidence.kind != "literal":
                continue
            if not evidence.region_id or not evidence.observation_ids:
                continue
            if field.literal not in evidence.excerpt:
                continue
            if not any(
                t.region_id == evidence.region_id
                and t.resolved
                and t.text
                and evidence.excerpt in t.text
                for t in run.transcripts
            ):
                continue
            literals.append(
                SourceLiteral(
                    field_key=key,
                    literal=field.literal,
                    source_excerpt=evidence.excerpt,
                    asset_id=specimen.asset.id,
                    region_id=evidence.region_id,
                    observation_ids=tuple(evidence.observation_ids),
                    evidence_ids=(evidence.id,),
                )
            )
            break
    return tuple(literals)


def harness_spec(specimen):
    run = specimen.run
    tools = tuple(run.profile_snapshot.get("tools", ("taxonomy_verifier",)))
    return HarnessSpec(
        profile_id=run.profile.id,
        profile_version=run.profile.version,
        phases=tuple(
            PhaseSpec(
                name=phase,
                version="evidence-phase-v1",
                allowed_tools=tools if phase in {"plan", "lookup"} else (),
            )
            for phase in PHASES
        ),
        budgets=HarnessBudget(
            max_tool_calls=min(100, run.profile.execution.max_external_calls),
            max_elapsed_seconds=min(600, run.profile.execution.max_active_seconds),
            max_tokens=run.profile.execution.max_tokens,
            max_cost_microunits=run.profile.execution.approved_cost_limit_micros or 0,
        ),
    )


def taxonomy_results(specimen, literals):
    matching = next((item for item in literals if item.field_key == "taxon"), None)
    if not matching:
        return ()
    results = []
    for lookup in specimen.run.lookups[-1:]:
        query = canonical(lookup.query)
        candidates = []
        for candidate in lookup.candidates:
            item = candidate.get("usage", candidate)
            name = item.get("scientificName")
            identifier = item.get("key")
            if name and identifier:
                candidates.append(
                    AuthorityCandidate(
                        identifier=str(identifier),
                        name=name,
                        source_version=lookup.adapter_version,
                        relation="supports"
                        if lookup.status == LookupStatus.SUCCESS
                        else "unresolved",
                        reason="Retained taxonomy lookup; ambiguity needs explicit selection",
                        evidence_ids=matching.evidence_ids,
                    )
                )
        results.append(
            AuthorityResult(
                source_id=lookup.provider,
                source_version=lookup.adapter_version,
                adapter_version=lookup.adapter_version,
                operation="species_match",
                status=lookup.status,
                literal=matching.literal,
                evidence_ids=matching.evidence_ids,
                query_json=query,
                input_sha256=bytes_digest(query.encode()),
                retrieved_at=lookup.retrieved_at,
                candidates=tuple(candidates),
                raw_ref=lookup.raw_ref,
                response_sha256=lookup.digest,
            )
        )
    return tuple(results)


def read_artifact(metadata, blobs, max_bytes=4 * 1024 * 1024):
    try:
        raw = blobs.get_bounded(metadata["blob_ref"], max_bytes)
        if hashlib.sha256(raw).hexdigest() != metadata["sha256"]:
            raise ValueError("Artifact checksum mismatch")
        return raw
    except BlobTooLarge:
        raise
    except Exception as exc:
        raise EvidenceIntegrityError("evidence_artifact_unavailable") from exc


def phase_artifact(specimen, phase, blobs):
    metadata = specimen.run.phase_results.get(phase)
    if metadata is None:
        raise KeyError(phase)
    try:
        result = PhaseResult.model_validate_json(read_artifact(metadata, blobs))
        payload = result.model_dump(mode="json", exclude={"output_sha256"})
        if bytes_digest(canonical(payload).encode()) != result.output_sha256:
            raise ValueError("Phase output digest mismatch")
        return result
    except Exception as exc:
        raise EvidenceIntegrityError("phase_artifact_integrity_failure") from exc


def execute_phase(specimen, phase, blobs):
    run = specimen.run
    literals = source_literals(specimen, blobs)
    spec = harness_spec(specimen)
    run.harness_spec = spec.model_dump(mode="json")
    base = tuple(
        FieldProposal(
            field_key=item.field_key,
            literal=item.literal,
            candidate=item.literal,
            relation="supports",
            evidence_ids=item.evidence_ids,
            reason="Verified retained transcript literal",
        )
        for item in literals
    )
    lookups = (
        *taxonomy_results(specimen, literals),
        *(
            read_authority_result(metadata, blobs)
            for metadata in run.authority_results.values()
        ),
    )
    findings = ()
    proposals = base
    if phase == "parse":
        proposals = ()
    elif phase == "resolve" and "lookup" in run.phase_results:
        # Literal and normalized layers remain distinct; compare authority alternatives.
        source = phase_artifact(specimen, "lookup", blobs)
        findings = source.findings
        proposals = tuple(p for p in source.proposals if p.source_id is not None)
        selected = []
        for proposal in proposals:
            field = run.fields.get(proposal.field_key)
            human_choice = field and any(
                e.kind == "authority_selection" and e.id in field.evidence_ids
                for e in run.evidence
            )
            if human_choice:
                if proposal.authority_identifier == field.authority_id:
                    selected.append(
                        proposal.model_copy(update={"relation": "supports"})
                    )
            else:
                ambiguous = any(
                    result.source_id == proposal.source_id
                    and result.status == LookupStatus.AMBIGUOUS
                    for result in lookups
                )
                selected.append(
                    proposal.model_copy(update={"relation": "unresolved"})
                    if ambiguous
                    else proposal
                )
        proposals = tuple(selected)
    elif phase in {"validate", "finalize"} and "resolve" in run.phase_results:
        findings = phase_artifact(specimen, "resolve", blobs).findings
        for task in run.authority_plan:
            metadata = next(
                (
                    m
                    for m in run.authority_results.values()
                    if m["tool_id"] == task["tool_id"]
                    and m["field_key"] == task["field_key"]
                ),
                None,
            )
            if metadata is None:
                absent_literal = any(
                    item["tool_id"] == task["tool_id"]
                    and item["field_key"] == task["field_key"]
                    for item in run.authority_unresolved.values()
                )
                findings = (
                    *findings,
                    Finding(
                        code="authority_source_literal_unresolved"
                        if absent_literal
                        else "required_authority_not_run",
                        field_key=task["field_key"],
                        severity="hard" if absent_literal else "operational",
                    ),
                )

            elif task["tool_id"] != "parties" and metadata["status"] != "success":
                result = read_authority_result(metadata, blobs)
                field = run.fields.get(task["field_key"])
                selected = field and any(
                    e.kind == "authority_selection"
                    and e.source == result.source_id
                    and e.locator == "candidate:" + (field.authority_id or "")
                    and e.id in field.evidence_ids
                    for e in run.evidence
                )
                if not selected:
                    findings = (
                        *findings,
                        Finding(
                            code="authority_result_requires_review",
                            field_key=task["field_key"],
                            severity="hard",
                        ),
                    )
            if task["tool_id"] != "parties":
                continue
            field = run.fields.get(task["field_key"])
            qualified = False
            for result in lookups:
                for candidate in result.candidates:
                    if (
                        not field
                        or not candidate.identity
                        or field.authority_id != candidate.identifier
                    ):
                        continue
                    qualified = (
                        field.authority_identity
                        == candidate.identity.model_dump(mode="json")
                        and any(
                            e.kind == "authority_selection"
                            and e.source == result.source_id
                            and e.locator == "candidate:" + candidate.identifier
                            and e.id in field.evidence_ids
                            and e.raw_ref == result.raw_ref
                            and e.digest == result.response_sha256
                            for e in run.evidence
                        )
                    )
            if not qualified:
                findings = (
                    *findings,
                    Finding(
                        code="parties_identity_resolution_required",
                        field_key=task["field_key"],
                        severity="hard",
                    ),
                )
    result = run_phase(
        spec,
        PhaseInput(
            phase=phase,
            literals=literals,
            proposals=proposals,
            lookups=lookups,
            required_fields=run.profile.mandatory_fields,
            semantics_confirmed=run.profile.semantics_confirmed,
            findings=findings,
            usage=BudgetUsage(
                tool_calls=run.usage.external_calls,
                elapsed_seconds=run.usage.active_seconds,
                tokens=run.usage.tokens,
                cost_microunits=run.usage.reserved_cost_micros,
            ),
        ),
    )
    raw = result.model_dump_json().encode()
    run.phase_results[phase] = {
        "phase": phase,
        "version": result.version,
        "applicability": result.applicability,
        "reason": result.reason,
        "findings": [f.model_dump(mode="json") for f in result.findings],
        "input_sha256": result.input_sha256,
        "output_sha256": result.output_sha256,
        "blob_ref": blobs.put(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    return result


def refresh_review_evidence(specimen, blobs, *, metadata_only=False):
    result = None
    if not metadata_only:
        specimen.run.authority_plan = plan_authorities(specimen)
        for phase in PHASES:
            result = execute_phase(specimen, phase, blobs)
    signals = []
    differences = []
    unmeasured = set()
    reading_metadata = {}
    declaration_sources = {}
    from .reading_declarations import effective_declarations, label_handling

    for region in specimen.run.regions:
        readings = [o for o in specimen.run.observations if o.region_id == region.id]
        observed_declarations = {}
        for observation in readings:
            declarations, candidates = effective_declarations(
                specimen, observation, blobs
            )
            observed_declarations[observation.id] = declarations
            declaration_sources.setdefault(region.id, []).extend(candidates)
        inputs = tuple(
            ReadingEvidenceInput(
                observation_id=o.id,
                region_id=region.id,
                text=o.literal_text,
                source_ref=o.raw_ref,
                source_sha256=o.raw_sha256,
                declarations=observed_declarations[o.id],
            )
            for o in readings[:2]
        )
        metadata = tuple(summarize_reading(item) for item in inputs)
        for item in metadata:
            raw = item.model_dump_json().encode()
            reading_metadata[item.reference.observation_id] = {
                "blob_ref": blobs.put(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "status": item.status,
                "language_state": item.language_state,
                "script_state": item.script_state,
                "reasons": list(item.reasons),
            }
        if len(inputs) < 2:
            unmeasured.update(("reading_disagreement", "language", "script"))
            continue
        alignment = align_readings(*inputs)
        raw = alignment.model_dump_json().encode()
        differences.append(
            {
                "region_id": region.id,
                "blob_ref": blobs.put(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "status": alignment.status,
                "difference_count": len(alignment.alternatives)
                if alignment.status != "policy_blocked"
                else None,
                "reasons": list(alignment.reasons),
            }
        )
        risk = reading_risk_evidence(alignment, metadata)
        signals.extend(risk.signals)
        unmeasured.update(risk.unmeasured)
    specimen.run.disagreements = differences
    specimen.run.reading_metadata = reading_metadata
    specimen.run.label_language_handling = label_handling(specimen, declaration_sources)
    if result is not None and result.findings:
        signals.append(
            RiskSignal(
                code="hard_validation",
                count=len(result.findings),
                evidence_ids=tuple(e.id for e in specimen.run.evidence)
                or (specimen.asset.id,),
            )
        )
    # Merge the same signal across regions before weighting, without duplicating it.
    merged = {}
    for signal in signals:
        key = (signal.code, signal.field_key)
        if key in merged:
            previous = merged[key]
            signal = signal.model_copy(
                update={
                    "count": min(10000, previous.count + signal.count),
                    "evidence_ids": tuple(
                        dict.fromkeys((*previous.evidence_ids, *signal.evidence_ids))
                    ),
                }
            )
        merged[key] = signal
    specimen.run.review_risk = review_risk(tuple(merged.values())).model_dump(
        mode="json"
    )
    specimen.run.review_risk["unmeasured"] = sorted(unmeasured)
    specimen.run.review_risk["measurement_complete"] = not unmeasured
    return result


def apply_phase_gate(run, result):
    if result.applicability == "blocked":
        run.blocker = "evidence_harness_blocked:" + next(
            (f.code for f in result.findings if f.severity == "operational"),
            result.reason,
        )
        run.disposition = None
        run.stage = "processing_blocked"
        run.reasons = [run.blocker]
    elif any(f.severity == "hard" for f in result.findings):
        run.reasons = list(
            dict.fromkeys(
                [
                    *run.reasons,
                    *(
                        f.code + (":" + f.field_key if f.field_key else "")
                        for f in result.findings
                        if f.severity == "hard"
                    ),
                ]
            )
        )
        if run.disposition == Disposition.CLEARED:
            run.disposition = Disposition.REVIEW


def plan_authorities(specimen):
    tools = specimen.run.profile_snapshot.get("tools", ())
    plan = []
    if "parties" in tools or (
        not specimen.run.profile.synthetic
        and "identified_by_irn" in specimen.run.profile.mandatory_fields
    ):
        plan.append(
            {"tool_id": "parties", "field_key": "identified_by_irn", "required": True}
        )
    if "geography" in tools:
        plan.append(
            {"tool_id": "geography", "field_key": "province_state", "required": True}
        )
    return plan


def authority_query(specimen, task, blobs):
    from .authority_registry import AuthorityQuery

    literal = next(
        (
            item
            for item in source_literals(specimen, blobs)
            if item.field_key == task["field_key"]
        ),
        None,
    )
    if literal is None:
        return None
    return AuthorityQuery(
        organization_id=specimen.scope.organization_id,
        collection_id=specimen.scope.collection_id,
        data_classification="public"
        if specimen.run.profile.synthetic
        else "restricted",
        literal=literal.literal,
        evidence_ids=literal.evidence_ids,
        historical_context=specimen.run.fields["date_visited_from"].literal
        if task["tool_id"] == "geography"
        else None,
    )


def read_authority_result(metadata, blobs):
    try:
        result = AuthorityResult.model_validate_json(read_artifact(metadata, blobs))
        if result.raw_ref:
            source = blobs.get(result.raw_ref)
            if hashlib.sha256(source).hexdigest() != result.response_sha256:
                raise ValueError("Authority raw source checksum mismatch")
        return result
    except Exception as exc:
        raise EvidenceIntegrityError("authority_artifact_integrity_failure") from exc
