"""Resolve retained evidence bytes before any final disposition is persisted."""

import hashlib
import io

from PIL import Image

from .domain import Specimen
from .storage import BlobStore


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
        require(len(original) == asset.size_bytes)
        with Image.open(io.BytesIO(original)) as image:
            image.load()
            require(image.size == (asset.width, asset.height))
            require(Image.MIME.get(image.format) == asset.media_type)
            regions = {region.id: region for region in run.regions}
            require(len(regions) == len(run.regions))
            input_hashes = {}
            for region in run.regions:
                require(region.asset_id == asset.id)
                require(region.x + region.width <= asset.width)
                require(region.y + region.height <= asset.height)
                crop = image.crop(
                    (
                        region.x,
                        region.y,
                        region.x + region.width,
                        region.y + region.height,
                    )
                ).convert("RGB")
                output = io.BytesIO()
                crop.save(output, format="PNG")
                input_hashes[region.id] = hashlib.sha256(output.getvalue()).hexdigest()
                if region.crop_ref:
                    require(read(region.crop_ref) == output.getvalue())
                if region.mask_ref:
                    read(region.mask_ref)
            observations = {o.id: o for o in run.observations}
            require(len(observations) == len(run.observations))
            for observation in run.observations:
                require(observation.region_id in regions)
                require(bool(observation.raw_sha256))
                read(observation.raw_ref, observation.raw_sha256)
                expected_input = (
                    asset.sha256
                    if run.profile.synthetic
                    else input_hashes[observation.region_id]
                )
                require(observation.input_sha256 == expected_input)
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
