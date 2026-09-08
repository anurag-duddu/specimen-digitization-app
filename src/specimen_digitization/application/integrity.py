"""Resolve retained evidence bytes before any final disposition is persisted."""

import hashlib
import json

from PIL import Image

from .domain import Specimen
from .storage import BlobStore
from .region_pixels import region_png


class EvidenceIntegrityError(RuntimeError):
    """Retained evidence cannot currently substantiate the stored graph."""


def verify_evidence(specimen: Specimen, blobs: BlobStore) -> None:
    """Check bytes and graph associations; missing storage is an operational block."""

    def require(condition):
        if not condition:
            raise EvidenceIntegrityError("evidence_integrity_failure")

    def read(ref, expected=None):
        require(bool(ref))
        data = blobs.get(ref)
        if expected is not None:
            require(hashlib.sha256(data).hexdigest() == expected)
        return data

    try:
        asset, run = specimen.asset, specimen.run
        original = read(asset.blob_ref, asset.sha256)
        if asset.view_derivative:
            view = asset.view_derivative
            require(view["original_sha256"] == asset.sha256)
            read(view["blob_ref"], view["derivative_sha256"])
        if run.segmentation:
            require(run.segmentation["input_sha256"] == asset.sha256)
            read(run.segmentation["blob_ref"], run.segmentation["sha256"])
        for metadata in [
            *run.phase_results.values(),
            *run.reading_metadata.values(),
            *run.reading_declarations,
            *run.disagreements,
            *run.authority_receipts.values(),
            *run.authority_results.values(),
        ]:
            read(metadata["blob_ref"], metadata["sha256"])
        for metadata in run.authority_results.values():
            result = json.loads(read(metadata["blob_ref"], metadata["sha256"]))
            if result.get("raw_ref") or result.get("response_sha256"):
                require(
                    bool(result.get("raw_ref")) and bool(result.get("response_sha256"))
                )
                read(result["raw_ref"], result["response_sha256"])
        if run.classification.get("raw_response_ref"):
            require(bool(run.classification_raw_sha256))
            read(run.classification["raw_response_ref"], run.classification_raw_sha256)
        if run.profile_snapshot:
            from .collection_profiles import CollectionProfile

            published = CollectionProfile.model_validate(run.profile_snapshot)
            require(published.state == "active")
            for name in (
                "id",
                "version",
                "schema_version",
                "mandatory_fields",
                "synthetic",
                "institutional_policy_approved",
                "semantics_confirmed",
            ):
                require(getattr(published, name) == getattr(run.profile, name))
            require(published.model_routes == run.profile.routes)
        require(len(original) == asset.size_bytes)
        from .source_pixels import source_image

        with source_image(asset, blobs) as image:
            image.load()
            require(image.size == (asset.width, asset.height))
            if not asset.processing_derivative:
                require(Image.MIME.get(image.format) == asset.media_type)
            else:
                require(
                    asset.processing_derivative["coordinate_space"] == asset.pixel_basis
                )
            regions = {region.id: region for region in run.regions}
            require(len(regions) == len(run.regions))
            input_hashes = {}
            for region in run.regions:
                require(region.asset_id == asset.id)
                require(region.x + region.width <= asset.width)
                require(region.y + region.height <= asset.height)
                crop = region_png(image, region)
                input_hashes[region.id] = hashlib.sha256(crop).hexdigest()
                if region.crop_ref:
                    require(read(region.crop_ref) == crop)
                if region.mask_ref:
                    read(region.mask_ref)
            observations = {o.id: o for o in run.observations}
            require(len(observations) == len(run.observations))
            for observation in run.observations:
                require(observation.region_id in regions)
                require(bool(observation.raw_sha256))
                read(observation.raw_ref, observation.raw_sha256)
                from .reading_declarations import effective_declarations

                effective_declarations(specimen, observation, blobs)
                expected_input = (
                    asset.sha256
                    if run.profile.synthetic
                    else input_hashes[observation.region_id]
                )
                require(observation.input_sha256 == expected_input)
                if observation.input_asset_id is not None:
                    require(observation.input_asset_id == asset.id)
                if observation.input_crop_ref is not None:
                    read(observation.input_crop_ref, observation.input_sha256)
            for transcript in run.transcripts:
                require(transcript.region_id in regions)
                require(bool(transcript.observation_ids))
                require(
                    all(
                        ident in observations
                        and observations[ident].region_id == transcript.region_id
                        for ident in transcript.observation_ids
                    )
                )
            for evidence in run.evidence:
                if evidence.asset_id is not None:
                    require(evidence.asset_id == asset.id)
                if evidence.region_id is not None:
                    require(evidence.region_id in regions)
                require(
                    all(
                        ident in observations
                        and observations[ident].region_id == evidence.region_id
                        for ident in evidence.observation_ids
                    )
                )
                if evidence.kind == "literal":
                    require(evidence.asset_id == asset.id)
                    require(bool(evidence.observation_ids))
                if evidence.raw_ref or evidence.digest:
                    require(bool(evidence.raw_ref) and bool(evidence.digest))
                    read(evidence.raw_ref, evidence.digest)
            for lookup in run.lookups:
                if (
                    lookup.raw_ref
                    or lookup.digest
                    or lookup.status.value in {"success", "ambiguous"}
                ):
                    require(bool(lookup.raw_ref) and bool(lookup.digest))
                    read(lookup.raw_ref, lookup.digest)
    except EvidenceIntegrityError:
        raise
    except Exception as exc:
        # Storage access errors and decode failures cannot become scientific outcomes.
        raise EvidenceIntegrityError("evidence_integrity_failure") from exc
