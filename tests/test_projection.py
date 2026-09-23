"""The normalized SQL projection's mapping (docs/execution/golive/DATA_CONTRACT.md 11)."""

from __future__ import annotations

import hashlib
import uuid

from specimen_digitization.application.domain import (
    Asset,
    Observation,
    Profile,
    Region,
    Run,
    Scope,
    Specimen,
    Transcript,
)
from specimen_digitization.application.projection import (
    Blob,
    canonical_json,
    derived_id,
    writes,
)
from specimen_digitization.application.storage import digest

SHA = "a" * 64
PROFILE = {
    "id": "zoology_insects_slides",
    "version": "1.0.0",
    "model_routes": ["handwriting-qwen", "handwriting-muse"],
    "segmentation_settings": {"concept_prompt": "label", "score_threshold": 0.5},
}


class TracedRun(Run):
    """The lane's `Run.trace_id` (S3) before it reaches the shared domain model."""

    trace_id: str | None = None


def locate(ref: str) -> Blob:
    sha, generation = ref.split(":")
    return Blob("demo-bucket", f"application/sha256/{sha}", generation)


def size(ref: str) -> int:
    assert not ref.startswith("a" * 64), "the original's size comes from its asset"
    return 321


def reading(region: Region, route: str, text: str, raw: str) -> Observation:
    return Observation(
        region_id=region.id,
        route_id=route,
        model_id=f"model/{route}",
        provider="fixture-provider",
        prompt_version="p" * 64,
        input_sha256="b" * 64,
        literal_text=text,
        unreadable_spans=["Il1."] if route == "handwriting-muse" else [],
        raw_ref=f"{raw * 64}:7",
        raw_sha256=raw * 64,
        input_tokens=11,
        output_tokens=5,
        latency_seconds=1.5,
        latency_basis="validated_agent_call_wall_seconds",
        finish_state="stop",
        completion_state="validated_output",
        parameters={"temperature": 0},
        provider_model_id=f"provider/{route}",
    )


def specimen(**run_fields) -> Specimen:
    asset = Asset(
        sha256=SHA,
        blob_ref=f"{SHA}:1700000000000001",
        media_type="image/jpeg",
        size_bytes=2048,
        width=4000,
        height=3000,
        filename="subject_105526321.jpg",
        uploader="reviewer-uid",
    )
    return Specimen(
        scope=Scope(organization_id="org-1", collection_id="coll-1"),
        asset=asset,
        run=TracedRun(**run_fields),
    )


def pinned(s: Specimen) -> Specimen:
    s.run.profile = Profile(
        id="zoology_insects_slides",
        version="1.0.0",
        routes=("handwriting-qwen", "handwriting-muse"),
    )
    s.run.profile_snapshot = PROFILE
    s.run.profile_registry_version = "registry-1"
    s.run.dependencies = {"profile_snapshot_sha256": digest(PROFILE)}
    return s


def read(s: Specimen) -> Specimen:
    region = Region(
        asset_id=s.asset.id,
        x=10,
        y=20,
        width=390,
        height=160,
        order=0,
        method="sam3",
        version="rev-1",
    )
    left = reading(region, "handwriting-qwen", "Chicago, Ill.", "c")
    right = reading(region, "handwriting-muse", "Chicago, Il1.", "d")
    s.run.regions = [region]
    # The muse reading comes first; a comparison still names its readings in the fixed id order.
    s.run.observations = [right, left]
    s.run.transcripts = [
        Transcript(
            region_id=region.id,
            observation_ids=[right.id, left.id],
            alternatives=[right.literal_text, left.literal_text],
            resolved=False,
            disagreement_ratio=1 / 13,
            alignment_status="difference",
            alignment_algorithm="bounded-levenshtein-fraction-v1",
            alignment_reasons=["one_substitution"],
        )
    ]
    return s


def ops(result):
    return [w.operation for w in result]


def test_derived_ids_are_stable_uuid5_and_distinct():
    first = derived_id("tool-call", "run-1", "lookup:geocode:1")
    assert first == derived_id("tool-call", "run-1", "lookup:geocode:1")
    assert uuid.UUID(first).version == 5
    assert first != derived_id("tool-call", "run-1", "lookup:geocode:2")


def test_canonical_json_hashes_to_the_snapshot_digest():
    value = {"b": [1.0, {"z": 2, "a": 0.5}], "a": "x"}
    assert hashlib.sha256(canonical_json(value).encode()).hexdigest() == digest(value)


def test_before_the_profile_is_pinned_only_the_original_image_is_written():
    s = specimen()
    result = writes(s, locate, size, "worker-uid")
    assert ops(result) == ["AppendSourceAssetV2"]
    original = result[0].variables
    assert original["id"] == s.asset.id
    assert original["specimenId"] == s.id
    assert original["kind"] == "original"
    assert original["bucket"] == "demo-bucket"
    assert original["objectName"] == f"application/sha256/{SHA}"
    assert original["generation"] == "1700000000000001"
    assert (original["width"], original["height"]) == (4000, 3000)
    assert original["byteSize"] == "2048"
    assert original["mimeType"] == "image/jpeg"
    assert original["uploaderUid"] == "reviewer-uid"


def test_a_pinned_run_writes_its_profile_version_then_the_run():
    s = pinned(specimen(trace_id=None))
    result = writes(s, locate, size, "worker-uid")
    assert ops(result) == [
        "AppendSourceAssetV2",
        "AppendProfileVersionV2",
        "AppendPipelineRunV2",
    ]
    profile, run = result[1].variables, result[2].variables
    assert profile["profileKey"] == "zoology_insects_slides"
    assert profile["version"] == "1.0.0"
    assert profile["configSha256"] == digest(PROFILE)
    assert hashlib.sha256(profile["configObject"].encode()).hexdigest() == digest(PROFILE)
    assert profile["id"] == derived_id(
        "profile", "coll-1", "zoology_insects_slides", "1.0.0", digest(PROFILE)
    )
    assert run["id"] == s.run.id
    assert run["specimenId"] == s.id
    assert run["profileVersionId"] == profile["id"]
    assert run["inputSha256"] == SHA
    assert run["traceId"] is None
    assert run["pinnedVersions"]["segmentation"] == PROFILE["segmentation_settings"]
    assert run["pinnedVersions"]["routes"] == ["handwriting-qwen", "handwriting-muse"]
    assert run["pinnedVersions"]["profile"]["registry_version"] == "registry-1"


def test_a_trace_id_is_carried_on_the_run_and_recorded_once():
    trace = "0af7" * 8
    result = writes(pinned(specimen(trace_id=trace)), locate, size, "worker-uid")
    assert result[2].variables["traceId"] == trace
    assert ops(result)[3] == "RecordRunTraceV1"
    assert result[3].variables == {"id": result[2].variables["id"], "traceId": trace}


def test_regions_readings_and_comparisons_follow_their_parents():
    s = read(pinned(specimen()))
    result = writes(s, locate, size, "worker-uid")
    assert ops(result) == [
        "AppendSourceAssetV2",
        "AppendProfileVersionV2",
        "AppendPipelineRunV2",
        "AppendLabelRegionV2",
        "AppendSourceAssetV2",
        "AppendModelObservationV2",
        "AppendSourceAssetV2",
        "AppendModelObservationV2",
        "AppendReadingComparisonV1",
    ]
    region = s.run.regions[0]
    right, left = s.run.observations
    written_region = result[3].variables
    # The domain's region id repeats across runs, so the row's id is per run (section 5).
    assert written_region["id"] == derived_id("region", s.run.id, region.id)
    assert written_region["domainRegionId"] == region.id
    assert written_region["runId"] == s.run.id
    assert written_region["sourceAssetId"] == s.asset.id
    assert written_region["cropAssetId"] is None
    assert written_region["geometry"] == {
        "x": 10,
        "y": 20,
        "width": 390,
        "height": 160,
        "rotation_quarter_turns": 0,
        "pixel_basis": "original_pixel_edges",
    }
    assert written_region["segmentationVersion"] == "sam3:rev-1"
    raw, observation = result[4].variables, result[5].variables
    assert raw["kind"] == "raw_response"
    assert raw["id"] == derived_id("asset", s.id, "demo-bucket", f"application/sha256/{'d' * 64}", "7")
    assert (raw["width"], raw["height"], raw["byteSize"]) == (None, None, "321")
    assert raw["mimeType"] == "application/json"
    assert raw["uploaderUid"] == "worker-uid"
    assert observation["id"] == right.id
    assert observation["rawAssetId"] == raw["id"]
    assert observation["regionId"] == written_region["id"]
    assert observation["stepKey"] == f"transcribe:{region.id}:handwriting-muse"
    assert observation["routeId"] == "handwriting-muse"
    assert observation["modelVersion"] == "model/handwriting-muse"
    assert observation["independent"] is True
    assert observation["outcome"] == "validated_output"
    assert observation["unreadableSpans"] == ["Il1."]
    assert observation["parameters"] == {
        "model_settings": {"temperature": 0},
        "provider_model_id": "provider/handwriting-muse",
        "input_tokens": 11,
        "output_tokens": 5,
        "latency_seconds": 1.5,
        "latency_basis": "validated_agent_call_wall_seconds",
    }
    comparison = result[8].variables
    # One fixed order, the ids as lowercase hex without dashes (section 3.1).
    first, second = sorted((left.id, right.id), key=lambda i: i.replace("-", "").lower())
    assert (comparison["leftObservationId"], comparison["rightObservationId"]) == (first, second)
    assert comparison["regionId"] == written_region["id"]
    assert comparison["id"] == derived_id("comparison", s.run.id, region.id, first, second)
    assert comparison["ratio"] == 1 / 13
    assert (comparison["editDistance"], comparison["lengthBasis"]) == (1, 13)
    assert comparison["status"] == "difference"
    assert comparison["reasons"] == ["one_substitution"]


def test_one_raw_response_shared_by_two_readings_is_one_asset():
    s = read(pinned(specimen()))
    right, left = s.run.observations
    s.run.observations = [right, left.model_copy(update={"raw_ref": right.raw_ref})]
    result = writes(s, locate, size, "worker-uid")
    assert ops(result).count("AppendSourceAssetV2") == 2
    observations = [w.variables for w in result if w.operation == "AppendModelObservationV2"]
    assert observations[0]["rawAssetId"] == observations[1]["rawAssetId"]


def test_specimens_with_one_stored_response_each_record_their_own_asset():
    # The blob store is content-addressed: byte-identical responses are one object.
    s, t = read(pinned(specimen())), read(pinned(specimen()))
    raw = [
        [w.variables for w in writes(x, locate, size, "worker-uid") if w.variables.get("kind") == "raw_response"]
        for x in (s, t)
    ]
    assert [a["objectName"] for a in raw[0]] == [a["objectName"] for a in raw[1]]
    assert not {a["id"] for a in raw[0]} & {a["id"] for a in raw[1]}
    assert {a["specimenId"] for a in raw[1]} == {t.id}


def test_a_region_id_a_later_run_reuses_is_a_new_row():
    s = read(pinned(specimen()))
    region = s.run.regions[0]
    first = next(w for w in writes(s, locate, size, "worker-uid") if w.operation == "AppendLabelRegionV2")
    s.previous_runs = [s.run]
    s.run = read(pinned(specimen())).run.model_copy(update={"regions": [region]})
    second = next(w for w in writes(s, locate, size, "worker-uid") if w.operation == "AppendLabelRegionV2")
    assert first.variables["domainRegionId"] == second.variables["domainRegionId"] == region.id
    assert first.variables["id"] != second.variables["id"]


def test_unmeasured_or_incomplete_pairs_have_no_invented_components():
    s = read(pinned(specimen()))
    s.run.transcripts[0].disagreement_ratio = None
    comparison = writes(s, locate, size, "worker-uid")[-1].variables
    assert (comparison["ratio"], comparison["editDistance"]) == (None, None)
    assert comparison["lengthBasis"] == 13
    s.run.transcripts[0].observation_ids = s.run.transcripts[0].observation_ids[:1]
    assert "AppendReadingComparisonV1" not in ops(writes(s, locate, size, "worker-uid"))


def test_every_write_has_a_distinct_key_and_repeats_are_identical():
    s = read(pinned(specimen(trace_id="0af7" * 8)))
    first, second = writes(s, locate, size, "worker-uid"), writes(s, locate, size, "worker-uid")
    assert [w.key for w in first] == [w.key for w in second]
    assert [w.variables for w in first] == [w.variables for w in second]
    assert len({w.key for w in first}) == len(first)
