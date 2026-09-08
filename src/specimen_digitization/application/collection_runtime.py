"""Application binding for published collection snapshots and explicit selection."""

import hashlib

from .classification import (
    ClassificationRequest,
    ClassificationResult,
    Candidate,
    ManualSelection,
    SelectionPolicy,
    UnconfiguredClassifier,
    classify,
    select_profile,
)
from .collection_profiles import insects_registry
from .domain import Profile
from .image_quality import ImageLimits, diagnose_image


def application_registry(synthetic):
    registry = insects_registry(synthetic=synthetic)
    if synthetic:
        # These approvals label only the local teaching fixture, never museum policy.
        registry = registry.model_copy(
            update={
                "profiles": tuple(
                    profile.model_copy(
                        update={
                            "institutional_policy_approved": True,
                            "semantics_confirmed": True,
                            "allowed_input_formats": ("JPEG", "PNG", "TIFF"),
                        }
                    )
                    for profile in registry.profiles
                )
            }
        )
    return registry


class SyntheticClassifier:
    external = False

    def __init__(self, blobs):
        self.blobs = blobs

    def classify(self, request):
        raw = b'{"mode":"synthetic","classification":"explicit teaching fixture"}'
        return ClassificationResult(
            status="completed",
            input_sha256=request.input_sha256,
            candidates=(
                Candidate(
                    collection_id=request.collection_ids[0],
                    score=1,
                    reasons=("synthetic_fixture_only",),
                ),
            ),
            reason="synthetic_fixture_only",
            adapter_version="synthetic-classifier-v1",
            route_id="synthetic",
            model_version="synthetic-v1",
            prompt_version="synthetic-v1",
            raw_response_ref=self.blobs.put(raw),
            synthetic=True,
        )


def classify_and_select(specimen, registry, classifier, blobs):
    request = ClassificationRequest(
        asset_id=specimen.asset.id,
        input_sha256=specimen.asset.sha256,
        collection_ids=tuple(node.id for node in registry.nodes),
    )
    result = classify(request, classifier or UnconfiguredClassifier())
    specimen.run.classification = result.model_dump(mode="json")
    if result.raw_response_ref:
        specimen.run.classification_raw_sha256 = hashlib.sha256(
            blobs.get(result.raw_response_ref)
        ).hexdigest()
    selection = (
        ManualSelection.model_validate(specimen.run.classification_selection)
        if specimen.run.classification_selection
        else None
    )
    resolved = select_profile(
        result,
        registry,
        SelectionPolicy(
            version="explicit-selection-v1",
            allow_synthetic=specimen.run.profile.synthetic,
        ),
        selection,
    )
    if resolved.status != "selected" or resolved.profile is None:
        return resolved.reason
    published = resolved.profile
    specimen.run.profile_snapshot = published.model_dump(mode="json")
    specimen.run.profile_registry_version = registry.version
    specimen.run.profile = Profile(
        execution=specimen.run.profile.execution,
        id=published.id,
        version=published.version,
        schema_version=published.schema_version,
        policy_version=published.clearance_policy,
        mandatory_fields=published.mandatory_fields,
        routes=published.model_routes,
        synthetic=published.synthetic,
        institutional_policy_approved=published.institutional_policy_approved,
        semantics_confirmed=published.semantics_confirmed,
    )
    return None


def quality_check(specimen, blobs):
    formats = tuple(
        specimen.run.profile_snapshot.get(
            "allowed_input_formats", ("JPEG", "PNG", "TIFF")
        )
    )
    if specimen.asset.processing_derivative:
        metadata = specimen.asset.processing_derivative
        if metadata["actual_format"] not in formats:
            return "image_format_not_approved_by_profile"
        raw = blobs.get_bounded(metadata["blob_ref"], 25 * 1024 * 1024)
        if (
            hashlib.sha256(raw).hexdigest() != metadata["derivative_sha256"]
            or metadata["original_sha256"] != specimen.asset.sha256
        ):
            return "canonical_pixels_digest_mismatch"
        diagnostics = diagnose_image(raw, ImageLimits(allowed_formats=("PNG",)))
        specimen.asset.quality_diagnostics = dict(
            diagnostics.model_dump(mode="json"),
            original_sha256=specimen.asset.sha256,
            pixel_basis=specimen.asset.pixel_basis,
        )
        return None if diagnostics.status == "valid" else "image_quality_rejected"
    diagnostics = diagnose_image(
        blobs.get(specimen.asset.blob_ref), ImageLimits(allowed_formats=formats)
    )
    specimen.asset.quality_diagnostics = diagnostics.model_dump(mode="json")
    if diagnostics.input_sha256 != specimen.asset.sha256:
        return "source_digest_mismatch"
    return (
        None
        if diagnostics.status == "valid"
        else "image_quality_rejected:" + ",".join(diagnostics.issues)
    )
