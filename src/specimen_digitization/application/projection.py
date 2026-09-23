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
from .storage import canonical_json

NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL, "urn:fieldmuseum:specimen-digitization:projection:v1"
)


def derived_id(*parts: object) -> str:
    """The stable id of a row that has no domain id (section 5)."""
    return str(uuid.uuid5(NAMESPACE, "/".join(str(part) for part in parts)))


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


def _write(operation: str, variables: dict, *key_parts: object) -> Write:
    key = ":".join(str(part) for part in (operation, variables["id"], *key_parts))
    return Write(operation, variables, key)


def writes(specimen: Specimen, locate: Locate, size: Size, actor: str) -> list[Write]:
    """Every row the specimen supports so far, each after the rows it references."""
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
    for observation in run.observations:
        raw = _raw_asset(specimen, observation, locate, actor)
        if raw.key not in assets:
            raw.variables["byteSize"] = str(size(observation.raw_ref))
            assets.add(raw.key)
            result.append(raw)
        result.append(_reading(run, observation, raw.variables["id"]))
    result += [c for t in run.transcripts if (c := _comparison(run, t)) is not None]
    return result


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
            "id": region.id,
            "runId": specimen.run.id,
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


def _raw_asset(
    specimen: Specimen, observation: Observation, locate: Locate, actor: str
) -> Write:
    blob = locate(observation.raw_ref)
    return _write(
        "AppendSourceAssetV2",
        {
            "id": derived_id("asset", blob.bucket, blob.object_name, blob.generation),
            "specimenId": specimen.id,
            "kind": "raw_response",
            "parentAssetId": None,
            "bucket": blob.bucket,
            "objectName": blob.object_name,
            "generation": blob.generation,
            "sha256": observation.raw_sha256,
            "mimeType": "application/json",
            "byteSize": None,
            "width": None,
            "height": None,
            "acquisitionMethod": "model_response",
            "uploaderUid": actor,
        },
    )


def _reading(run: Run, observation: Observation, raw_asset_id: str) -> Write:
    return _write(
        "AppendModelObservationV2",
        {
            "id": observation.id,
            "runId": run.id,
            "regionId": observation.region_id,
            "rawAssetId": raw_asset_id,
            "stepKey": f"transcribe:{observation.region_id}:{observation.route_id}",
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
            "independent": True,
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
    routes = list(run.profile.routes)
    left, right = sorted(
        transcript.observation_ids,
        key=lambda i: (
            routes.index(readings[i].route_id)
            if readings[i].route_id in routes
            else len(routes),
            readings[i].route_id,
        ),
    )
    ratio = transcript.disagreement_ratio
    length_basis = max(1, *(len(readings[i].literal_text) for i in (left, right)))
    return _write(
        "AppendReadingComparisonV1",
        {
            "id": derived_id("comparison", run.id, transcript.region_id, left, right),
            "runId": run.id,
            "regionId": transcript.region_id,
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
