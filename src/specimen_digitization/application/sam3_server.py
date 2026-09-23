"""Opt-in SAM 3 CPU service. No checkpoint is loaded on module import.

Cloud Run IAM must allow only the worker identity. Durable create-only claims
fence one inference per manifest specimen (the frozen pilot) or per run (the
processing lane, docs/execution/golive/LANE.md T3), including unknown outcomes.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import math
import os
import re
import stat
from pathlib import Path
import threading
import time
from typing import Literal
from uuid import UUID, NAMESPACE_URL, uuid5

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..hub_models import SAM3_MODEL
from .collection_profiles import SegmentationSettings
from .domain import Region
from .sam3_effect import canonical_bytes

SAM3_IMPLEMENTATION = "transformers/5.14.0;torch/2.8.0;cpu"
MAX_PIXELS = 16_000_000
MAX_BYTES = 25_000_000
MAX_MASK_BYTES = 2_000_000


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def encoded(value) -> bytes:
    return canonical_bytes(value)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SourceObject(Strict):
    bucket: str = Field(min_length=3, max_length=222)
    object_name: str = Field(min_length=1, max_length=1024)
    generation: str = Field(pattern=r"^[1-9][0-9]*$")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(gt=0, le=MAX_BYTES)
    crc32c: str | None = None
    md5_hash: str | None = None


class ApplicationSource(Strict):
    blob_ref: str = Field(pattern=r"^[a-f0-9]{64}:[1-9][0-9]*$")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(gt=0, le=MAX_BYTES)
    source_object_index: int = Field(ge=0)


class PilotItem(Strict):
    ordinal: int = Field(ge=1, le=10)
    specimen_id: str
    organization_id: str
    collection_id: str
    source_objects: list[SourceObject] = Field(min_length=1, max_length=10)
    application_source: ApplicationSource

    @model_validator(mode="after")
    def binding(self):
        for value in (self.specimen_id, self.organization_id, self.collection_id):
            if str(UUID(value)) != value:
                raise ValueError("canonical UUID required")
        app = self.application_source
        if app.source_object_index >= len(self.source_objects):
            raise ValueError("source index out of bounds")
        original = self.source_objects[app.source_object_index]
        if (app.sha256, app.size_bytes) != (original.sha256, original.size_bytes):
            raise ValueError("source mapping mismatch")
        if app.blob_ref.split(":")[0] != app.sha256:
            raise ValueError("application reference mismatch")
        return self


class Selection(Strict):
    order: Literal["explicit_source_order"]
    source_inventory_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class PilotManifest(Strict):
    schema_version: Literal["specimen-pilot/v1"]
    status: Literal["ready"]
    project_id: Literal["specimen-digitization"]
    authorization_reference: str = Field(min_length=1, max_length=500)
    selection: Selection
    specimens: list[PilotItem] = Field(min_length=10, max_length=10)

    @model_validator(mode="after")
    def unique(self):
        if len({(x.organization_id, x.collection_id) for x in self.specimens}) != 1:
            raise ValueError("pilot must share one authorized scope")
        if [x.ordinal for x in self.specimens] != list(range(1, 11)):
            raise ValueError("explicit order required")
        for values in (
            [x.specimen_id for x in self.specimens],
            [x.application_source.blob_ref for x in self.specimens],
            [
                (s.bucket, s.object_name, s.generation)
                for x in self.specimens
                for s in x.source_objects
            ],
        ):
            if len(values) != len(set(values)):
                raise ValueError("duplicate pilot binding")
        return self


def read_manifest(path: Path, expected_sha256: str) -> PilotManifest:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        details = os.fstat(stream.fileno())
        if not stat.S_ISREG(details.st_mode) or details.st_mode & 0o077:
            raise ValueError("pilot manifest must be a private regular file")
        raw = stream.read(65537)
    if len(raw) > 65536 or digest(raw) != expected_sha256:
        raise ValueError("pilot manifest digest mismatch")
    return PilotManifest.model_validate_json(raw)


class SegmentRequest(Strict):
    run_id: str = Field(min_length=1, max_length=100)
    asset_id: str = Field(min_length=1, max_length=100)
    specimen_id: str
    organization_id: str
    collection_id: str
    # A generation pins a Cloud Storage copy; the lab's LocalBlobs refs are bare digests.
    blob_ref: str = Field(pattern=r"^[a-f0-9]{64}(:[1-9][0-9]*)?$")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    width: int = Field(gt=0, le=20000)
    height: int = Field(gt=0, le=20000)
    model_id: Literal["facebook/sam3"]
    model_revision: str
    prompt: str = Field(min_length=1, max_length=1000)
    parameters: dict
    adapter_version: Literal["sam3-http-v1"]
    settings_version: Literal["sam3-settings-v1"]

    @model_validator(mode="after")
    def settings(self):
        if self.width * self.height > MAX_PIXELS:
            raise ValueError("pixel limit exceeded")
        SegmentationSettings.model_validate(
            {
                "version": self.settings_version,
                "adapter_version": self.adapter_version,
                "model_id": self.model_id,
                "model_revision": self.model_revision,
                "prompt": self.prompt,
                "parameters": self.parameters,
            }
        )
        return self


class GCSObjects:
    """No listing, no overwrites, no automatic upload retries."""

    def __init__(self, client, output_bucket):
        self.client, self.output_bucket = client, output_bucket

    def _media(self, bucket, name, generation, maximum):
        from urllib.parse import quote
        from .blob_limits import read_limited

        url = (
            "https://storage.googleapis.com/storage/v1/b/"
            + quote(bucket, safe="")
            + "/o/"
            + quote(name, safe="")
        )
        response = self.client._http.get(
            url,
            params={"alt": "media", "generation": str(generation)},
            headers={"Accept-Encoding": "identity"},
            stream=True,
            allow_redirects=False,
            timeout=30,
        )
        with response:
            if response.status_code != 200:
                raise ValueError("sam3_object_generation_unavailable")
            return read_limited(
                lambda count: response.raw.read(count, decode_content=False), maximum
            )

    def source(self, obj: SourceObject):
        return self._media(obj.bucket, obj.object_name, obj.generation, obj.size_bytes)

    def application_source(self, request):
        """The application copy a per-run request names, at its exact generation."""
        sha256, _, generation = request.blob_ref.partition(":")
        if not generation:
            raise HTTPException(422, "application_generation_required")
        return self._media(
            self.output_bucket, "application/sha256/" + sha256, generation, MAX_BYTES
        )

    def put_mask(self, raw):
        name = "application/sha256/" + digest(raw)
        result = self.create(name, raw)
        if result is not None:
            return result
        blob = self.client.bucket(self.output_bucket).blob(name)
        blob.reload(timeout=30, retry=None)
        if blob.size != len(raw) or not blob.generation:
            raise ValueError("sam3_immutable_mask_mismatch")
        existing = self._media(self.output_bucket, name, blob.generation, len(raw))
        if len(existing) != len(raw) or digest(existing) != digest(raw):
            raise ValueError("sam3_immutable_mask_mismatch")
        return {
            "bucket": self.output_bucket,
            "object_name": name,
            "generation": str(blob.generation),
            "sha256": digest(raw),
            "size_bytes": len(raw),
        }

    def create(self, name, raw):
        from google.api_core.exceptions import PreconditionFailed

        blob = self.client.bucket(self.output_bucket).blob(name)
        try:
            blob.upload_from_string(
                raw,
                content_type="application/octet-stream",
                if_generation_match=0,
                timeout=30,
                retry=None,
            )
        except PreconditionFailed:
            return None
        return {
            "bucket": self.output_bucket,
            "object_name": name,
            "generation": str(blob.generation),
            "sha256": digest(raw),
            "size_bytes": len(raw),
        }

    def read(self, name):
        from google.api_core.exceptions import NotFound

        blob = self.client.bucket(self.output_bucket).blob(name)
        try:
            blob.reload(timeout=30, retry=None)
        except NotFound:
            return None
        return self._media(self.output_bucket, name, blob.generation, 1024 * 1024)


def checkpoint_files_digest(checkpoint: Path):
    """The digest of the checkpoint's artifact digests, as the engine pins it."""
    artifacts = sorted(
        path
        for path in Path(checkpoint).iterdir()
        if path.suffix in {".safetensors", ".json", ".txt"}
    )
    if len(artifacts) > 64:
        raise RuntimeError("sam3_checkpoint_artifact_limit")
    files = {}
    for path in artifacts:
        with path.open("rb") as stream:
            files[path.name] = hashlib.file_digest(stream, "sha256").hexdigest()
    return files, digest(encoded(files))


def offline_checkpoint_digest():
    """Only the worker owns inference credentials; SAM consumes pinned files."""
    import re
    from huggingface_hub import constants

    if not constants.HF_HUB_OFFLINE:
        raise RuntimeError("sam3_offline_checkpoint_required")
    if any(os.getenv(key) for key in (
        "HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACEHUB_API_TOKEN",
    )):
        raise RuntimeError("sam3_inference_credential_forbidden")
    expected = os.getenv("SPECIMEN_SAM3_CHECKPOINT_SHA256", "")
    if not re.fullmatch(r"[a-f0-9]{64}", expected):
        raise RuntimeError("sam3_checkpoint_digest_required")
    return expected


class Sam3Engine:
    def __init__(self):
        import torch
        from huggingface_hub import constants, snapshot_download
        from transformers import Sam3Model, Sam3Processor

        expected_digest = offline_checkpoint_digest() if constants.HF_HUB_OFFLINE else None

        # Only this immutable checkpoint. Download needs the existing approved
        # HF secret and accepted SAM license; neither is required by local tests.
        checkpoint = Path(
            snapshot_download(
                repo_id=SAM3_MODEL.repo_id,
                revision=SAM3_MODEL.revision,
                allow_patterns=["*.json", "*.safetensors", "*.txt"],
                token=False if constants.HF_HUB_OFFLINE else os.environ["HF_TOKEN"],
                # Explicitly choose cache lookup. The pinned Hub client's
                # patterned-snapshot path can otherwise request a remote tree
                # even when its HTTP transport is in offline mode.
                local_files_only=constants.HF_HUB_OFFLINE,
            )
        )
        weights = sorted(checkpoint.glob("*.safetensors"))
        if not weights:
            raise RuntimeError("sam3_checkpoint_missing")
        self.checkpoint_files, self.checkpoint_sha256 = checkpoint_files_digest(
            checkpoint
        )
        if expected_digest is not None and self.checkpoint_sha256 != expected_digest:
            raise RuntimeError("sam3_checkpoint_digest_mismatch")
        torch.set_num_threads(4)
        self.model = Sam3Model.from_pretrained(
            checkpoint, local_files_only=True, trust_remote_code=False
        ).eval()
        self.processor = Sam3Processor.from_pretrained(
            checkpoint, local_files_only=True, trust_remote_code=False
        )
        self.torch = torch

    def predict(self, image, prompt):
        inputs = self.processor(images=image, text=prompt, return_tensors="pt")
        with self.torch.inference_mode():
            output = self.model(**inputs)
        result = self.processor.post_process_instance_segmentation(
            output,
            threshold=0.5,
            mask_threshold=0.5,
            target_sizes=inputs.get("original_sizes").tolist(),
        )[0]
        if len(result["masks"]) > 64:
            raise ValueError("sam3_mask_count_exceeded")
        return [
            (
                Image.fromarray(mask.cpu().numpy().astype("uint8") * 255),
                float(score.item()),
            )
            for mask, score in zip(result["masks"], result["scores"], strict=True)
        ]


class Segmenter:
    def __init__(
        self, manifest, manifest_sha256, objects, engine, expires_at, *, clock=time.time
    ):
        self.manifest, self.manifest_sha256 = manifest, manifest_sha256
        self.objects, self.engine, self.expires_at, self.clock = (
            objects,
            engine,
            expires_at,
            clock,
        )
        self.lock = threading.Lock()

    def segment(self, request: SegmentRequest):
        if self.clock() + 125 >= self.expires_at:
            raise HTTPException(403, "pilot_launch_expired")
        matches = [
            s
            for s in self.manifest.specimens
            if (
                s.specimen_id,
                s.organization_id,
                s.collection_id,
                s.application_source.blob_ref,
                s.application_source.sha256,
            )
            == (
                request.specimen_id,
                request.organization_id,
                request.collection_id,
                request.blob_ref,
                request.sha256,
            )
        ]
        if len(matches) != 1:
            raise HTTPException(403, "pilot_source_not_authorized")
        if not self.lock.acquire(blocking=False):
            raise HTTPException(429, "sam3_busy")
        try:
            return self._segment(request, matches[0])
        finally:
            self.lock.release()

    def _segment(self, request, item):
        request_sha256 = digest(encoded(request.model_dump()))
        prefix = f"sam3/{self.manifest_sha256}/{item.specimen_id}"
        storage_prefix = (
            f"application/sha256/{self.manifest_sha256}/sam3/{item.specimen_id}"
        )
        claim = self.objects.create(
            storage_prefix + "/claim.json", encoded({"request_sha256": request_sha256})
        )
        if claim is None:
            previous = self.objects.read(storage_prefix + "/response.json")
            if previous:
                result = json.loads(previous)
                if result["request_sha256"] == request_sha256:
                    return result
            raise HTTPException(409, "sam3_outcome_unknown_requires_reconciliation")
        source = item.source_objects[item.application_source.source_object_index]
        # Intake already verified this immutable application copy. Runtime IAM
        # covers that copy; the original locator remains provenance only.
        app = item.application_source
        raw = self.objects.source(SourceObject(
            bucket=f"{self.manifest.project_id}.firebasestorage.app",
            object_name="application/sha256/" + app.sha256,
            generation=app.blob_ref.split(":")[1],
            sha256=app.sha256,
            size_bytes=app.size_bytes,
        ))
        if len(raw) != source.size_bytes or digest(raw) != source.sha256:
            raise HTTPException(409, "pilot_source_integrity_mismatch")
        image = decode_source(raw, request)
        regions, evidence = mask_regions(
            self.objects,
            self.engine.predict(image, request.prompt),
            image,
            request,
            prefix,
            lambda stored: f"{stored['sha256']}:{stored['generation']}",
        )
        response = {
            "model_id": SAM3_MODEL.repo_id,
            "model_revision": SAM3_MODEL.revision,
            "implementation": SAM3_IMPLEMENTATION,
            "checkpoint_sha256": self.engine.checkpoint_sha256,
            "checkpoint_files": self.engine.checkpoint_files,
            "request_sha256": request_sha256,
            "manifest_sha256": self.manifest_sha256,
            "source": source.model_dump(),
            "threshold": 0.5,
            "mask_threshold": 0.5,
            "regions": regions,
            "masks": evidence,
        }
        if self.objects.create(storage_prefix + "/response.json", encoded(response)) is None:
            raise HTTPException(409, "sam3_response_collision")
        return response


def decode_source(raw, request):
    with Image.open(io.BytesIO(raw)) as decoded:
        if (
            decoded.size != (request.width, request.height)
            or decoded.width * decoded.height > MAX_PIXELS
        ):
            raise HTTPException(422, "source_dimensions_mismatch")
        if getattr(decoded, "n_frames", 1) != 1:
            raise HTTPException(422, "multi_frame_source_unsupported")
        return decoded.convert("RGB")


def mask_regions(objects, masks, image, request, prefix, mask_ref):
    """Binary original-pixel masks to stored masks and their bounding regions."""
    if not 0 < len(masks) <= 64:
        raise HTTPException(422, "sam3_no_usable_regions")
    regions, evidence = [], []
    total_bytes = 0
    for index, (mask, score) in enumerate(masks):
        if (
            mask.size != image.size
            or mask.mode != "L"
            or not math.isfinite(score)
            or not 0 <= score <= 1
        ):
            raise HTTPException(422, "sam3_invalid_mask")
        if set(mask.tobytes()) - {0, 255}:
            raise HTTPException(422, "sam3_nonbinary_mask")
        bounds = mask.getbbox()
        if bounds is None:
            raise HTTPException(422, "sam3_empty_mask")
        out = io.BytesIO()
        mask.save(out, format="PNG")
        mask_raw = out.getvalue()
        total_bytes += len(mask_raw)
        if len(mask_raw) > MAX_MASK_BYTES or total_bytes > 16_000_000:
            raise HTTPException(422, "sam3_mask_byte_limit")
        stored = objects.put_mask(mask_raw)
        if stored is None:
            raise HTTPException(409, "sam3_mask_collision")
        x, y, right, bottom = bounds
        regions.append(
            Region(
                id=str(uuid5(NAMESPACE_URL, prefix + f"/{index}")),
                asset_id=request.asset_id,
                x=x,
                y=y,
                width=right - x,
                height=bottom - y,
                order=index,
                method="sam3",
                version=SAM3_MODEL.revision,
                mask_ref=mask_ref(stored),
            ).model_dump()
        )
        evidence.append(dict(stored, score=score, encoding="binary-png-original-pixels"))
    return regions, evidence


# A run id names storage paths, so it may not contain a separator or a dot.
RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}")
MAX_RUN_ATTEMPTS = 10


class RunSegmenter:
    """Per-run mode (LANE.md T3): the authenticated worker authorizes each run.

    One create-only claim per attempt fences inference; the stored response
    answers any repeat of the same request. A claim with no response older than
    the process's hard deadline belongs to an attempt that died with it.
    """

    def __init__(self, objects, engine, *, clock=time.time, hard_deadline_seconds=240):
        self.objects, self.engine, self.clock = objects, engine, clock
        self.hard_deadline_seconds = hard_deadline_seconds
        self.lock = threading.Lock()

    def segment(self, request: SegmentRequest):
        if not RUN_ID.fullmatch(request.run_id):
            raise HTTPException(422, "invalid_run_id")
        if not self.lock.acquire(blocking=False):
            raise HTTPException(429, "sam3_busy")
        try:
            return self._segment(request)
        finally:
            self.lock.release()

    def _stored(self, prefix, request_sha256):
        previous = self.objects.read(prefix + "/response.json")
        if previous is None:
            return None
        result = json.loads(previous)
        if result["request_sha256"] != request_sha256:
            raise HTTPException(409, "sam3_run_request_mismatch")
        return result

    def _claim(self, prefix, request_sha256):
        for attempt in range(1, MAX_RUN_ATTEMPTS + 1):
            name = f"{prefix}/claim-{attempt}.json"
            claim = {"request_sha256": request_sha256, "claimed_at": self.clock()}
            if self.objects.create(name, encoded(claim)) is not None:
                return
            existing = json.loads(self.objects.read(name))
            if existing["request_sha256"] != request_sha256:
                raise HTTPException(409, "sam3_run_request_mismatch")
            if self.clock() - existing["claimed_at"] <= self.hard_deadline_seconds:
                raise HTTPException(409, "sam3_busy")
        raise HTTPException(409, "sam3_run_attempts_exhausted")

    def _segment(self, request):
        request_sha256 = digest(encoded(request.model_dump()))
        prefix = f"application/sha256/sam3-runs/{request.run_id}"
        stored = self._stored(prefix, request_sha256)
        if stored is not None:
            return stored
        raw = self.objects.application_source(request)
        if digest(raw) != request.sha256:
            raise HTTPException(409, "source_integrity_mismatch")
        image = decode_source(raw, request)
        self._claim(prefix, request_sha256)
        regions, evidence = mask_regions(
            self.objects,
            self.engine.predict(image, request.prompt),
            image,
            request,
            f"sam3-run/{request.run_id}",
            lambda stored: stored.get("ref")
            or f"{stored['sha256']}:{stored['generation']}",
        )
        evidence = [
            dict(item, ref=region["mask_ref"])
            for item, region in zip(evidence, regions, strict=True)
        ]
        response = {
            "model_id": SAM3_MODEL.repo_id,
            "model_revision": SAM3_MODEL.revision,
            "implementation": SAM3_IMPLEMENTATION,
            "checkpoint_sha256": self.engine.checkpoint_sha256,
            "checkpoint_files": self.engine.checkpoint_files,
            "request_sha256": request_sha256,
            "run_id": request.run_id,
            "source": {
                "blob_ref": request.blob_ref,
                "sha256": request.sha256,
                "size_bytes": len(raw),
            },
            "threshold": 0.5,
            "mask_threshold": 0.5,
            "regions": regions,
            "masks": evidence,
        }
        if self.objects.create(prefix + "/response.json", encoded(response)) is None:
            stored = self._stored(prefix, request_sha256)
            if stored is None:
                raise HTTPException(409, "sam3_response_collision")
            return stored
        return response


class LocalObjects:
    """Lab storage in the application's LocalBlobs layout (LANE.md T3)."""

    def __init__(self, root):
        from .storage import LocalBlobs

        self.root = Path(root)
        self.blobs = LocalBlobs(self.root)

    def application_source(self, request):
        return self.blobs.get_bounded(request.blob_ref.split(":")[0], MAX_BYTES)

    def put_mask(self, raw):
        ref = self.blobs.put(raw)
        return {"ref": ref, "sha256": digest(raw), "size_bytes": len(raw)}

    def _path(self, name):
        parts = name.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise ValueError("invalid lab object name")
        return self.root.joinpath(*parts)

    def create(self, name, raw):
        import tempfile

        path = self._path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".object-", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, path)  # Create-only: never replaces a claim.
            except FileExistsError:
                return None
        finally:
            Path(temporary).unlink(missing_ok=True)
        return {"object_name": name, "sha256": digest(raw), "size_bytes": len(raw)}

    def read(self, name):
        path = self._path(name)
        return path.read_bytes() if path.exists() else None


def lab_authenticator(token):
    """The lab's shared secret replaces the identity token; Docker hides loopback."""
    if len(token) < 32:
        raise ValueError("lab token must be at least 32 characters")
    expected = ("Bearer " + token).encode()

    def authenticate(header):
        if not hmac.compare_digest(header.encode(), expected):
            raise ValueError("unapproved caller")

    return authenticate


def serving_mode(env):
    mode = env.get("SPECIMEN_SAM3_ENABLE")
    if mode in {"authorized-pilot", "authorized-run"} and env.get("K_SERVICE"):
        return mode
    if mode == "lab":
        if env.get("K_SERVICE") or env.get("APP_ENV") == "production":
            raise RuntimeError("sam3_lab_mode_refused_in_production")
        return mode
    raise RuntimeError("sam3_requires_authorized_cloud_run_launch")


def create_app(segmenter, authenticate, *, hard_deadline=False, deadline_seconds=120):
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        # Pydantic errors include original inputs; never echo specimen data.
        return JSONResponse(
            status_code=422, content={"detail": "invalid_segmentation_request"}
        )

    @app.middleware("http")
    async def perimeter(request: Request, call_next):
        if request.url.path != "/health/live":
            try:
                authenticate(request.headers.get("authorization", ""))
            except Exception:
                return JSONResponse(
                    status_code=403, content={"detail": "worker_identity_required"}
                )
        if request.method == "POST":
            raw = bytearray()
            async for chunk in request.stream():
                raw.extend(chunk)
                if len(raw) > 16384:
                    return JSONResponse(
                        status_code=413, content={"detail": "request_byte_limit"}
                    )
            request._body = bytes(raw)
        return await call_next(request)

    @app.get("/health/live")
    def live():
        return {"status": "live"}

    @app.post("/v1/segment")
    def segment(request: SegmentRequest):
        # A hosting request timeout does not stop model execution. A hard process
        # deadline does; durable claims ensure that restart cannot replay it.
        timer = (
            threading.Timer(deadline_seconds, lambda: os._exit(70))
            if hard_deadline
            else None
        )
        if timer:
            timer.start()
        try:
            return segmenter.segment(request)
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(503, "sam3_failed_requires_reconciliation") from None
        finally:
            if timer:
                timer.cancel()

    return app


def read_runtime_manifest(*, materialize=False):
    """Read the pinned manifest through the unchanged private-file contract."""
    from .runtime_input_materialization import (
        MANIFEST_MAX_BYTES,
        materialize_inputs,
    )

    try:
        source = Path(os.environ["SPECIMEN_PILOT_MANIFEST_PATH"])
        expected = os.environ["SPECIMEN_PILOT_MANIFEST_SHA256"]
        if not materialize:
            return read_manifest(source, expected)
        with materialize_inputs({"manifest": (source, expected, MANIFEST_MAX_BYTES)}) as paths:
            return read_manifest(paths["manifest"], expected)
    except (KeyError, OSError, ValueError):
        raise RuntimeError("sam3_private_manifest_unavailable") from None


def offline_checkpoint_path():
    """The pinned checkpoint in the local Hub cache; never a download."""
    from huggingface_hub import constants, snapshot_download

    if not constants.HF_HUB_OFFLINE:
        raise RuntimeError("sam3_offline_checkpoint_required")
    return Path(
        snapshot_download(
            repo_id=SAM3_MODEL.repo_id,
            revision=SAM3_MODEL.revision,
            allow_patterns=["*.json", "*.safetensors", "*.txt"],
            token=False,
            local_files_only=True,
        )
    )


def serve_runs(mode):
    """Per-run serving: Cloud Run behind the worker identity, or the local lab."""
    import uvicorn

    offline_checkpoint_digest()
    if mode == "lab":
        authenticate = lab_authenticator(os.environ["SPECIMEN_SAM3_LAB_TOKEN"])
        objects = LocalObjects(os.environ["SPECIMEN_SAM3_LAB_DIR"])
    else:
        from google.auth.transport.requests import Request as GoogleRequest
        from google.cloud import storage
        from google.oauth2.id_token import verify_oauth2_token

        audience, caller = (
            os.environ["SPECIMEN_SAM3_AUDIENCE"],
            os.environ["SPECIMEN_SAM3_CALLER_EMAIL"],
        )

        def authenticate(header):
            if not header.startswith("Bearer "):
                raise ValueError("missing token")
            claims = verify_oauth2_token(header[7:], GoogleRequest(), audience=audience)
            if claims.get("email") != caller or claims.get("email_verified") is not True:
                raise ValueError("unapproved caller")

        objects = GCSObjects(
            storage.Client(project="specimen-digitization"),
            os.environ["SPECIMEN_SAM3_OUTPUT_BUCKET"],
        )
    # No launch window: the service scales to zero between runs instead.
    uvicorn.run(
        create_app(
            RunSegmenter(objects, Sam3Engine(), hard_deadline_seconds=240),
            authenticate,
            hard_deadline=True,
            deadline_seconds=240,
        ),
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
        workers=1,
        access_log=False,
        timeout_graceful_shutdown=5,
    )


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Opt-in authorized-ten SAM CPU service"
    )
    parser.add_argument("--version", action="store_true")
    parser.add_argument("--materialize-config", action="store_true")
    parser.add_argument(
        "--checkpoint-digest",
        action="store_true",
        help="print the offline checkpoint's digest without loading the model",
    )
    args = parser.parse_args()
    if args.checkpoint_digest:
        print(checkpoint_files_digest(offline_checkpoint_path())[1])
        return
    if args.version:
        print(
            json.dumps(
                {
                    "source_sha": json.loads(
                        (Path(__file__).parents[1] / "_build.json").read_text()
                    )["source_sha"],
                    "model_id": SAM3_MODEL.repo_id,
                    "model_revision": SAM3_MODEL.revision,
                    "implementation": SAM3_IMPLEMENTATION,
                }
            )
        )
        return
    import uvicorn
    from google.auth.transport.requests import Request as GoogleRequest
    from google.oauth2.id_token import verify_oauth2_token
    from google.cloud import storage

    mode = serving_mode(os.environ)
    if mode != "authorized-pilot":
        serve_runs(mode)
        return
    if not os.getenv("SPECIMEN_SAM3_BUDGET_AUTHORIZATION"):
        raise RuntimeError("sam3_budget_authorization_required")
    offline_checkpoint_digest()
    manifest_sha256 = os.environ["SPECIMEN_PILOT_MANIFEST_SHA256"]
    manifest = read_runtime_manifest(materialize=args.materialize_config)
    expiry = float(os.environ["SPECIMEN_SAM3_EXPIRES_UNIX"])
    if (
        not math.isfinite(expiry)
        or not time.time() + 125 < expiry <= time.time() + 3600
    ):
        raise RuntimeError("sam3_launch_window_must_be_at_most_one_hour")
    audience, caller = (
        os.environ["SPECIMEN_SAM3_AUDIENCE"],
        os.environ["SPECIMEN_SAM3_CALLER_EMAIL"],
    )

    def authenticate(header):
        if not header.startswith("Bearer "):
            raise ValueError("missing token")
        claims = verify_oauth2_token(header[7:], GoogleRequest(), audience=audience)
        if claims.get("email") != caller or claims.get("email_verified") is not True:
            raise ValueError("unapproved caller")

    # Shutdown even if no inference is submitted. Never persist an idle model pilot.
    expiry_timer = threading.Timer(expiry - time.time(), lambda: os._exit(0))
    # The deadline bounds an active service; it must not keep failed startup or
    # an already stopped server alive (and billable) until the pilot expires.
    expiry_timer.daemon = True
    expiry_timer.start()
    try:
        objects = GCSObjects(
            storage.Client(project="specimen-digitization"),
            os.environ["SPECIMEN_SAM3_OUTPUT_BUCKET"],
        )
        segmenter = Segmenter(manifest, manifest_sha256, objects, Sam3Engine(), expiry)
        uvicorn.run(
            create_app(segmenter, authenticate, hard_deadline=True),
            host="0.0.0.0",
            port=int(os.getenv("PORT", "8080")),
            workers=1,
            access_log=False,
            timeout_graceful_shutdown=5,
        )
    finally:
        expiry_timer.cancel()


if __name__ == "__main__":
    main()
