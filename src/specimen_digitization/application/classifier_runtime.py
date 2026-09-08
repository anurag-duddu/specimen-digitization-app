"""Configured classification runs entirely inside the trusted hard process boundary."""

import hashlib
import io
import json
import os
from pathlib import Path

from .classification import ClassificationRequest, ClassificationResult
from .hf_collection_classifier import HFClassifierConfig
from .storage import LocalBlobs


def classifier_child(payload):
    from ..model_gateway import HuggingFaceInferenceRoute, HuggingFaceModelGateway
    from .domain import Asset
    from .hf_collection_classifier import (
        ApprovedClassificationImage,
        HFCollectionClassifier,
    )
    from .source_pixels import source_image
    from .production import GcsBlobs

    descriptor = payload["storage"]
    blobs = (
        LocalBlobs(Path(descriptor["root"]))
        if descriptor["kind"] == "local"
        else GcsBlobs(descriptor["bucket"])
    )
    config = HFClassifierConfig.model_validate(payload["config"])
    asset = Asset.model_validate(payload["asset"])
    request = ClassificationRequest.model_validate(payload["request"])
    if request.asset_id != asset.id or request.input_sha256 != asset.sha256:
        raise ValueError("Classification source identity mismatch")
    if getattr(asset, "sensitive", True) and not payload["allow_sensitive"]:
        return (
            ClassificationResult(
                status="blocked",
                input_sha256=request.input_sha256,
                reason="classifier_sensitive_source_not_approved",
                adapter_version="classifier-runtime-v1",
            )
            .model_dump_json()
            .encode()
        )

    def loader(query):
        if query != request or asset.width * asset.height > config.max_image_pixels:
            raise ValueError("Classification source or pixel bound mismatch")
        raw = blobs.get_bounded(asset.blob_ref, 25 * 1024 * 1024)
        if hashlib.sha256(raw).hexdigest() != asset.sha256:
            raise ValueError("Classification original digest mismatch")
        with source_image(asset, blobs) as image:
            output = io.BytesIO()
            image.convert("RGB").save(output, "PNG")
        png = output.getvalue()
        if len(png) > config.max_image_bytes:
            raise ValueError("Classification PNG byte limit")
        return ApprovedClassificationImage(
            asset_id=asset.id, original_sha256=asset.sha256, png=png
        )

    route = HuggingFaceInferenceRoute(
        route_id=config.route_id,
        logical_capability="collection_classifier",
        model_id=config.expected_model_id,
        provider=config.expected_provider,
    )
    gateway = HuggingFaceModelGateway(
        routes={config.route_id: route}, timeout_seconds=config.total_deadline_seconds
    )
    classifier = HFCollectionClassifier(
        config=config,
        gateway=gateway,
        image_loader=loader,
        provenance_sink=blobs.put,
        catalog=payload["catalog"],
    )
    return classifier.classify(request).model_dump_json().encode()


class ConfiguredClassifier:
    def __init__(self, blobs, config, *, allow_sensitive=False, effect=None):
        self.blobs, self.config, self.allow_sensitive, self.effect = (
            blobs,
            config,
            allow_sensitive,
            effect,
        )
        self.external = config is not None and config.approved

    def pin(self, run):
        if self.config is None:
            return None
        config = self.config.model_copy(
            update={
                "total_deadline_seconds": min(
                    self.config.total_deadline_seconds,
                    run.profile.execution.external_timeout_seconds,
                )
            }
        )
        return {
            "config": config.model_dump(mode="json"),
            "allow_sensitive": self.allow_sensitive,
            "adapter_version": "classifier-runtime-v1",
        }

    def bind(self, specimen, registry):
        from .bounded_effect import run_isolated
        from .workflow import OperationalBlock
        from .production import GcsBlobs

        facade = self

        class Bound:
            external = facade.external

            def classify(self, request):
                pinned = facade.pin(specimen.run)
                if pinned != specimen.run.dependencies.get("classifier"):
                    raise OperationalBlock(
                        "classifier_configuration_changed_requires_new_run"
                    )
                if pinned is None or not facade.external:
                    return ClassificationResult(
                        status="blocked",
                        input_sha256=request.input_sha256,
                        reason="approved_classifier_route_missing",
                        adapter_version="classifier-runtime-v1",
                    )
                if isinstance(facade.blobs, LocalBlobs):
                    storage = {"kind": "local", "root": str(facade.blobs.root)}
                elif isinstance(facade.blobs, GcsBlobs):
                    storage = {"kind": "gcs", "bucket": facade.blobs.bucket.name}
                else:
                    raise OperationalBlock("classifier_storage_not_supported")
                result = run_isolated(
                    facade.effect or classifier_child,
                    {
                        **pinned,
                        "storage": storage,
                        "asset": specimen.asset.model_dump(mode="json"),
                        "request": request.model_dump(mode="json"),
                        "catalog": {node.id: node.name for node in registry.nodes},
                    },
                    pinned["config"]["total_deadline_seconds"],
                    65536,
                )
                if result.status != "completed" or not result.cleanup_complete:
                    raise OperationalBlock("external_outcome_unknown")
                return ClassificationResult.model_validate_json(result.value)

        return Bound()


def configured_classifier(blobs):
    raw = os.getenv("SPECIMEN_CLASSIFIER_CONFIG_JSON")
    if raw is None:
        return None
    try:
        config = HFClassifierConfig.model_validate_json(raw)
        config = config.model_copy(
            update={
                "approved": config.approved
                and os.getenv("SPECIMEN_APPROVED_INFERENCE") == "true"
            }
        )
    except ValueError:
        config = None
    return ConfiguredClassifier(
        blobs,
        config,
        allow_sensitive=os.getenv("SPECIMEN_CLASSIFIER_ALLOW_SENSITIVE") == "true",
    )
