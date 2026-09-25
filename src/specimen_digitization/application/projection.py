"""The normalized SQL projection of a specimen's run (docs/execution/golive/DATA_CONTRACT.md 11).

Pure apart from the two blob functions the repository supplies: maps domain
objects to the connector writes of section 7, parents before children, with the
ids of section 5. The repository adds the scope and the actor, sends each write
and counts a primary-key conflict as already written.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass

from .domain import Observation, Run, Specimen, Transcript
from .storage import canonical_json, digest

NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL, "urn:fieldmuseum:specimen-digitization:projection:v1"
)


def derived_id(*parts: object) -> str:
    """The stable id of a row that has no domain id (section 5)."""
    return str(uuid.uuid5(NAMESPACE, "/".join(str(part) for part in parts)))


def _region_row(run_id: str, region_id: str) -> str:
    """A region row's id: the domain's region id repeats across runs (rule 1.5)."""
    return derived_id("region", run_id, region_id)


def _fixed_order(*ids: str) -> list[str]:
    """Readings in the connector's order: ids as lowercase hex without dashes (section 3.1)."""
    return sorted(ids, key=lambda i: i.replace("-", "").lower())


@dataclass(frozen=True)
class Blob:
    """Where the bytes behind a blob ref live, as `SourceAsset` records them."""

    bucket: str
    object_name: str
    generation: str


@dataclass(frozen=True)
class Write:
    """One connector mutation; the repository adds the scope and the actor."""

    operation: str
    variables: dict
    key: str


Locate = Callable[[str], Blob]
Size = Callable[[str], int]
# A material difference with one of these verdicts stays among the decision's alternatives.
OPEN_VERDICTS = ("neither", "uncertain")
# The one source string Google's evidence may carry (rule 1.6); the connector refuses any other.
GOOGLE = "google-maps-geocoding"
# Evidence that may back a candidate: a successful lookup, or recorded evidence (section 6).
LINKABLE = ("success", "recorded")


def _write(operation: str, variables: dict, *key_parts: object) -> Write:
    key = ":".join(str(part) for part in (operation, variables["id"], *key_parts))
    return Write(operation, variables, key)


def writes(
    specimen: Specimen,
    locate: Locate,
    size: Size,
    actor: str,
    reviewer: bool = False,
) -> list[Write]:
    """Every row the specimen supports so far, each after the rows it references.

    Review decisions and reviewers' transcript decisions are included only for a
    reviewer's save: their operations admit no other role.
    """
    result = [_original(specimen, locate)]
    run = specimen.run
    if not run.profile_snapshot:
        # Until the profile is pinned the run has only the default profile.
        return result
    profile = _profile_version(specimen)
    result += [profile, _run(specimen, profile.variables["id"])]
    trace_id = getattr(run, "trace_id", None)
    if trace_id:
        # The run row may predate its trace; recording the same id again is a no-op.
        result.append(
            _write("RecordRunTraceV1", {"id": run.id, "traceId": trace_id}, trace_id)
        )
    result += [_region(specimen, region) for region in run.regions]
    assets: set[str] = set()

    def asset(ref: str, kind: str) -> str:
        """Write a blob's asset row once, before the first row that refers to it."""
        write = _blob_asset(specimen, ref, kind, locate, actor)
        if write.key not in assets:
            write.variables["byteSize"] = str(size(ref))
            assets.add(write.key)
            result.append(write)
        return write.variables["id"]

    for observation in run.observations:
        result.append(_reading(run, observation, asset(observation.raw_ref, "raw_response")))
    result += [c for t in run.transcripts if (c := _comparison(run, t)) is not None]
    decisions: dict[str, str] = {}
    for transcript in run.transcripts:
        result += _first_pass(run, transcript, asset, decisions, reviewer)
    evidence = _evidence(run, asset)
    result += evidence
    recorded = {w.variables["id"] for w in evidence}
    linkable = {w.variables["id"] for w in evidence if w.variables["outcome"] in LINKABLE}
    result += [
        _tool_call(run, record, decisions, recorded)
        for record in getattr(run, "tool_calls", None) or []
    ]
    candidates: dict[str, str | None] = {}
    result += _fields(run, decisions, linkable, candidates)
    if run.disposition:
        result += _record(run, candidates, recorded)
    if reviewer:
        result += _review_decisions(specimen)
    return result


def _value(item):
    return item.value if hasattr(item, "value") else item


def _plain(item):
    return item.model_dump(mode="json") if hasattr(item, "model_dump") else item


def _original(specimen: Specimen, locate: Locate) -> Write:
    asset = specimen.asset
    blob = locate(asset.blob_ref)
    return _write(
        "AppendSourceAssetV2",
        {
            "id": asset.id,
            "specimenId": specimen.id,
            "kind": "original",
            "parentAssetId": None,
            "bucket": blob.bucket,
            "objectName": blob.object_name,
            "generation": blob.generation,
            "sha256": asset.sha256,
            "mimeType": asset.media_type,
            "byteSize": str(asset.size_bytes),
            "width": asset.width,
            "height": asset.height,
            "acquisitionMethod": "intake",
            "uploaderUid": asset.uploader,
        },
    )


def _profile_version(specimen: Specimen) -> Write:
    run = specimen.run
    config = canonical_json(run.profile_snapshot)
    sha256 = run.dependencies["profile_snapshot_sha256"]
    return _write(
        "AppendProfileVersionV2",
        {
            "id": derived_id(
                "profile",
                specimen.scope.collection_id,
                run.profile.id,
                run.profile.version,
                sha256,
            ),
            "profileKey": run.profile.id,
            "version": run.profile.version,
            "configObject": config,
            "configSha256": sha256,
            "approvedBy": None,
        },
    )


def _run(specimen: Specimen, profile_version_id: str) -> Write:
    run = specimen.run
    previous = specimen.previous_runs[-1].id if specimen.previous_runs else None
    return _write(
        "AppendPipelineRunV2",
        {
            "id": run.id,
            "specimenId": specimen.id,
            "profileVersionId": profile_version_id,
            "supersedesRunId": previous,
            "pinnedVersions": {
                "profile": {
                    "key": run.profile.id,
                    "version": run.profile.version,
                    "registry_version": run.profile_registry_version,
                    "sha256": run.dependencies["profile_snapshot_sha256"],
                },
                "routes": list(run.profile.routes),
                "schema_version": run.profile.schema_version,
                "policy_version": run.profile.policy_version,
                "segmentation": run.profile_snapshot.get("segmentation_settings"),
                "dependencies": run.dependencies,
            },
            "inputSha256": specimen.asset.sha256,
            "traceId": getattr(run, "trace_id", None),
        },
    )


def _region(specimen: Specimen, region) -> Write:
    return _write(
        "AppendLabelRegionV2",
        {
            "id": _region_row(specimen.run.id, region.id),
            "runId": specimen.run.id,
            "domainRegionId": region.id,
            "sourceAssetId": region.asset_id,
            "cropAssetId": None,
            "geometry": {
                "x": region.x,
                "y": region.y,
                "width": region.width,
                "height": region.height,
                "rotation_quarter_turns": region.rotation_quarter_turns,
                "pixel_basis": specimen.asset.pixel_basis,
            },
            "ordinal": region.order,
            "regionType": "label",
            "segmentationVersion": f"{region.method}:{region.version}",
            "supersedesRegionId": None,
        },
    )


def _blob_asset(
    specimen: Specimen, ref: str, kind: str, locate: Locate, actor: str
) -> Write:
    blob = locate(ref)
    return _write(
        "AppendSourceAssetV2",
        {
            # Per specimen: a content-addressed object can hold several specimens' responses.
            "id": derived_id(
                "asset", specimen.id, blob.bucket, blob.object_name, blob.generation
            ),
            "specimenId": specimen.id,
            "kind": kind,
            "parentAssetId": None,
            "bucket": blob.bucket,
            "objectName": blob.object_name,
            "generation": blob.generation,
            # The stored bytes' own digest; a recorded response digest can differ (G26).
            "sha256": ref.partition(":")[0],
            "mimeType": "application/json",
            "byteSize": None,
            "width": None,
            "height": None,
            "acquisitionMethod": "model_response" if kind == "raw_response" else "lookup",
            "uploaderUid": actor,
        },
    )


def _reading(
    run: Run,
    observation: Observation,
    raw_asset_id: str,
    independent: bool = True,
    step_key: str | None = None,
) -> Write:
    return _write(
        "AppendModelObservationV2",
        {
            "id": observation.id,
            "runId": run.id,
            "regionId": _region_row(run.id, observation.region_id),
            "rawAssetId": raw_asset_id,
            "stepKey": step_key
            or f"transcribe:{observation.region_id}:{observation.route_id}",
            "provider": observation.provider,
            "modelVersion": observation.model_id,
            "promptVersion": observation.prompt_version,
            "inputSha256": observation.input_sha256,
            "parameters": {
                "model_settings": observation.parameters or {},
                "provider_model_id": observation.provider_model_id,
                "input_tokens": observation.input_tokens,
                "output_tokens": observation.output_tokens,
                "latency_seconds": observation.latency_seconds,
                "latency_basis": observation.latency_basis,
            },
            "literalText": observation.literal_text,
            "outcome": observation.completion_state
            or observation.finish_state
            or "unknown",
            "independent": independent,
            "routeId": observation.route_id,
            "unreadableSpans": list(observation.unreadable_spans),
        },
    )


def _comparison(run: Run, transcript: Transcript) -> Write | None:
    if len(transcript.observation_ids) != 2 or not transcript.alignment_algorithm:
        return None
    readings = {o.id: o for o in run.observations}
    if not all(i in readings for i in transcript.observation_ids):
        return None
    left, right = _fixed_order(*transcript.observation_ids)
    ratio = transcript.disagreement_ratio
    length_basis = max(1, *(len(readings[i].literal_text) for i in (left, right)))
    return _write(
        "AppendReadingComparisonV1",
        {
            "id": derived_id("comparison", run.id, transcript.region_id, left, right),
            "runId": run.id,
            "regionId": _region_row(run.id, transcript.region_id),
            "leftObservationId": left,
            "rightObservationId": right,
            "algorithm": transcript.alignment_algorithm,
            "ratio": ratio,
            "editDistance": None if ratio is None else round(ratio * length_basis),
            "lengthBasis": length_basis,
            "status": transcript.alignment_status or "unknown",
            "reasons": list(transcript.alignment_reasons),
        },
    )


def _decision_kind(run: Run, transcript: Transcript) -> str | None:
    kind = getattr(transcript, "decision_kind", None)
    if kind:
        return kind
    if transcript.actor:
        return "human"
    readings = {o.id: o for o in run.observations}
    texts = {readings[i].literal_text for i in transcript.observation_ids if i in readings}
    if transcript.resolved and len(transcript.observation_ids) >= 2 and len(texts) == 1:
        return "identical_readings"
    return None


def _first_pass(
    run: Run, transcript: Transcript, asset, decisions: dict, reviewer: bool
) -> list[Write]:
    """A region's decided transcript, the first pass's call and each handoff."""
    kind = _decision_kind(run, transcript)
    if kind is None:
        return []
    result = []
    call = getattr(transcript, "first_pass_call", None) if kind == "first_pass" else None
    if call is not None:
        step = f"first_pass:{transcript.region_id}"
        raw = asset(call.raw_ref, "raw_response")
        result.append(_reading(run, call, raw, independent=False, step_key=step))
    if hasattr(transcript, "selected_observation_id"):
        selected = transcript.selected_observation_id
    else:
        # Today's domain: identical readings decide by any one of them.
        selected = transcript.observation_ids[0] if kind == "identical_readings" else None
    differences = [_plain(d) for d in getattr(transcript, "differences", None) or []]
    still_open = [
        d for d in differences if d.get("material") and d.get("verdict") in OPEN_VERDICTS
    ]
    # Unresolved means no reading was selected (G19); a reviewer says so explicitly.
    unresolved = not transcript.resolved if kind == "human" else selected is None
    content = {
        "kind": kind,
        "selected": selected,
        "text": transcript.text or "",
        "differences": differences,
        "unresolved": unresolved,
        "rationale": transcript.reason,
        "call": call.id if call else None,
    }
    decision = derived_id("transcription", run.id, transcript.region_id, digest(content))
    decisions[transcript.region_id] = decision
    if kind == "human" and not reviewer:
        # The reviewer's own save writes it; later rows may still name it.
        return result
    result.append(
        _write(
            "AppendTranscriptionVersionV2",
            {
                "id": decision,
                "runId": run.id,
                "literalText": transcript.text or "",
                "spans": differences,
                "alternatives": still_open if differences else list(transcript.alternatives),
                "unresolved": unresolved,
                "regionId": _region_row(run.id, transcript.region_id),
                "decisionKind": kind,
                "selectedObservationId": selected,
                "firstPassObservationId": call.id if call else None,
                "rationale": transcript.reason,
            },
        )
    )
    for handoff in getattr(transcript, "handoffs", None) or []:
        if handoff.handed_text is None:
            continue
        result.append(
            _write(
                "AppendHarnessInputV1",
                {
                    "id": derived_id("handoff", decision, handoff.observation_id),
                    "runId": run.id,
                    "transcriptionVersionId": decision,
                    "observationId": handoff.observation_id,
                    "role": handoff.role,
                    "handedText": handoff.handed_text,
                    "note": handoff.note,
                },
            )
        )
    return result


def _evidence(run: Run, asset) -> list[Write]:
    """Lookups and evidence with a stored response; the rest stay in the snapshot."""
    result = []
    for found in run.lookups:
        if not (found.raw_ref and found.digest):
            continue
        outcome = _value(found.status)
        # A lookup has a locator exactly when it succeeded (section 6).
        locator = found.metadata.get("locator") or f"lookup/{found.id}"
        # G26: Google's stored record is our reduced record, never its response.
        kind = "evidence_record" if found.provider == GOOGLE else "lookup_response"
        result.append(
            _write(
                "AppendEvidenceItemV2",
                {
                    "id": found.id,
                    "runId": run.id,
                    "source": found.provider,
                    "sourceVersion": str(
                        found.metadata.get("source_version") or found.adapter_version
                    ),
                    "adapterVersion": found.adapter_version,
                    "query": dict(found.query),
                    "outcome": outcome,
                    "locator": str(locator) if outcome == "success" else None,
                    "responseSha256": found.digest,
                    "capturedAt": found.retrieved_at,
                    "rawAssetId": asset(found.raw_ref, kind),
                },
            )
        )
    for item in run.evidence:
        if not (item.raw_ref and item.digest):
            continue
        result.append(
            _write(
                "AppendEvidenceItemV2",
                {
                    "id": item.id,
                    "runId": run.id,
                    "source": item.source,
                    "sourceVersion": "unrecorded",
                    "adapterVersion": item.kind,
                    "query": {},
                    "outcome": "recorded",
                    "locator": item.locator,
                    "responseSha256": item.digest,
                    "capturedAt": item.created_at,
                    "rawAssetId": asset(item.raw_ref, "evidence_record"),
                },
            )
        )
    return result


def _tool_call(run: Run, record, decisions: dict, recorded: set) -> Write:
    decided = record.input_source == "decided_transcript"
    return _write(
        "AppendToolCallV1",
        {
            "id": derived_id("tool-call", run.id, record.call_key),
            "runId": run.id,
            "callKey": record.call_key,
            "phase": record.phase,
            "tool": record.tool,
            "toolVersion": record.tool_version,
            "source": record.source,
            "fieldKeys": list(record.field_keys),
            "inputSource": record.input_source,
            "transcriptionVersionId": decisions.get(record.region_id) if decided else None,
            "observationId": None if decided else record.observation_id,
            "attempt": record.attempt,
            "arguments": _plain(record.arguments),
            "outcome": _value(record.outcome),
            "result": _plain(record.result),
            "evidenceId": record.evidence_id if record.evidence_id in recorded else None,
            "startedAt": record.started_at,
            "completedAt": record.completed_at,
        },
    )


def _derivation(value, relations: dict) -> str:
    """Lookup only when a source decides the value; Google supports, never decides (G26)."""
    if value.normalized and "decides" in relations.values():
        return "lookup"
    if value.normalized:
        return "normalized"
    return "parsed" if value.parsed else "literal"


def _fields(run: Run, decisions: dict, linkable: set, candidates: dict) -> list[Write]:
    """A candidate per verbatim value; the settling one carries the value and evidence."""
    result = []
    for key, value in run.fields.items():
        verbatim = getattr(value, "verbatim_by_observation", None) or {}
        source = getattr(value, "input_source", None)
        if verbatim:
            # G27, G28: no reading was selected, so each reader's literal is kept.
            entries = [(text, "raw_reading", reading) for reading, text in verbatim.items()]
        elif value.literal is not None:
            reading = getattr(value, "source_observation_id", None)
            entries = [(value.literal, source, reading if source == "raw_reading" else None)]
        else:
            continue
        region = getattr(value, "source_region_id", None)
        precision = getattr(value, "precision", None)
        century_rule = getattr(value, "century_rule", None)
        parsed = (
            {"value": value.parsed, "precision": precision, "century_rule": century_rule}
            if precision or century_rule
            else value.parsed
        )
        relations = getattr(value, "evidence_relations", None) or {}
        content = digest(value.model_dump(mode="json"))
        # With no pick, the settled value belongs to the reader a lookup confirmed (G20).
        confirmed = getattr(value, "source_observation_id", None) if verbatim else None
        candidates[key] = None
        for text, entry_source, reading in entries:
            candidate = derived_id("candidate", run.id, key, reading or "-", content)
            settles = not verbatim or (confirmed is not None and reading == confirmed)
            if settles:
                candidates[key] = candidate
            result.append(
                _write(
                    "AppendFieldCandidateV2",
                    {
                        "id": candidate,
                        "runId": run.id,
                        "fieldKey": key,
                        "state": _value(value.state),
                        "literalValue": text,
                        "parsedValue": parsed if settles else None,
                        "normalizedValue": value.normalized if settles else None,
                        "authorityId": value.authority_id if settles else None,
                        "derivation": _derivation(value, relations) if settles else "literal",
                        "inputSource": entry_source,
                        "sourceTranscriptionId": decisions.get(region)
                        if entry_source == "decided_transcript"
                        else None,
                        "sourceObservationId": reading,
                    },
                )
            )
            if not settles:
                continue
            for evidence in value.evidence_ids:
                # Only a success or recorded evidence, and only with its relation: no default (G23).
                if evidence in linkable and relations.get(evidence):
                    result.append(
                        _write(
                            "AppendCandidateEvidenceV2",
                            {
                                "id": derived_id("candidate-evidence", candidate, evidence),
                                "candidateId": candidate,
                                "evidenceId": evidence,
                                "relation": relations[evidence],
                            },
                        )
                    )
    return result


def _record(run: Run, candidates: dict, recorded: set) -> list[Write]:
    """The queue decision, every field's final state and a finding per reason."""
    fields = {key: _value(value.state) for key, value in run.fields.items()}
    reasons = list(run.reasons)
    findings = list(getattr(run, "findings", None) or [])
    disposition = _value(run.disposition)
    summary = getattr(run, "disposition_summary", None) or "; ".join(reasons) or disposition
    content = {
        "disposition": disposition,
        "reasons": reasons,
        "summary": summary,
        "findings": [_plain(finding) for finding in findings],
        "fields": fields,
        # A new value with the same state is a new record version too (section 5).
        "candidates": {key: candidates.get(key) for key in fields},
    }
    record = derived_id("record", run.id, digest(content))
    policy = run.profile.policy_version
    result = [
        _write(
            "AppendRecordVersionV2",
            {
                "id": record,
                "runId": run.id,
                "predecessorId": None,
                "disposition": disposition,
                "policyVersion": policy,
                "reasonCodes": reasons,
                "summary": summary,
            },
        )
    ]
    groups = getattr(run, "field_groups", None) or {}
    for key, state in fields.items():
        group = groups.get(key) or (
            "mandatory" if key in run.profile.mandatory_fields else "optional"
        )
        result.append(
            _write(
                "AppendResolvedFieldV2",
                {
                    "id": derived_id(record, "field", key),
                    "recordVersionId": record,
                    "candidateId": candidates.get(key),
                    "fieldKey": key,
                    "state": state,
                    "fieldGroup": group,
                },
            )
        )
    for reason in reasons:
        rule, _, rest = reason.partition(":")
        result.append(
            _write(
                "AppendValidationFindingV2",
                {
                    "id": derived_id(
                        record,
                        "finding",
                        "hard",
                        rule,
                        rest if rest in run.fields else "-",
                        reason,
                        digest([]),
                    ),
                    "recordVersionId": record,
                    "runId": run.id,
                    "evidenceIds": None,
                    "ruleId": rule,
                    "ruleVersion": policy,
                    "severity": "hard",
                    "outcome": "fail",
                    "fieldKey": rest if rest in run.fields else None,
                    "reasonCode": reason,
                },
            )
        )
    # Warnings and info never route the record to review (G23, G27); they sit beside it.
    for finding in findings:
        # Only evidence the run recorded, each once; the operation checks each is of the run.
        named = list(
            dict.fromkeys(e for e in getattr(finding, "evidence_ids", None) or [] if e in recorded)
        )
        result.append(
            _write(
                "AppendValidationFindingV2",
                {
                    "id": derived_id(
                        record,
                        "finding",
                        finding.severity,
                        finding.rule_id,
                        finding.field_key or "-",
                        finding.reason_code,
                        digest(named),
                    ),
                    "recordVersionId": record,
                    "runId": run.id,
                    "evidenceIds": named or None,
                    "ruleId": finding.rule_id,
                    "ruleVersion": finding.rule_version,
                    "severity": finding.severity,
                    "outcome": "fail",
                    "fieldKey": finding.field_key,
                    "reasonCode": finding.reason_code,
                },
            )
        )
    return result


def _review_decisions(specimen: Specimen) -> list[Write]:
    """Each reviewer decision, at the revisions of the save that first writes it."""
    return [
        _write(
            "AppendReviewDecisionV1",
            {
                "id": event.id,
                "specimenId": specimen.id,
                "baseRevision": specimen.version - 1,
                "resultingRevision": specimen.version,
                "reason": event.reason,
                "correction": {"action": event.action, "before": event.before, "after": event.after},
            },
        )
        for event in specimen.audit
        if event.action.startswith("review_")
    ]
