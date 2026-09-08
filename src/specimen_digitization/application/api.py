"""Authenticated version-one API shared by Flutter and local end-to-end tests."""

from __future__ import annotations
import hashlib
import hmac
import io
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from fastapi import BackgroundTasks, Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse, Response
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import Field
from PIL import Image, UnidentifiedImageError

from .domain import (
    Asset,
    AuditEvent,
    Evidence,
    FieldValue,
    ValueState,
    Principal,
    Profile,
    Record,
    Region,
    Run,
    Scope,
    Specimen,
    uid,
)
from .collection_runtime import application_registry
from .image_quality import ImageLimits, orientation_view
from .classification import ManualSelection
from .evidence_runtime import phase_artifact, refresh_review_evidence, apply_phase_gate
from .active_graph import (
    GraphTooLarge,
    WorkspaceTooLarge,
    WORKSPACE_LIMIT,
    GRAPH_LIMIT,
    encoded,
    save_recoverably,
)
from .evidence_runtime import read_authority_result, read_artifact
from .integrity import EvidenceIntegrityError, verify_evidence
from .policy import finalize
from .reliability import has_active_lease
from .production import actor_uid
from .storage import (
    Conflict,
    LocalBlobs,
    Missing,
    SQLiteRepository,
    SnapshotTooLarge,
    digest,
)
from .workflow import OperationalBlock, SyntheticAdapters, Workflow

SYNTHETIC_ORG = "00000000-0000-4000-8000-000000000001"
SYNTHETIC_COLLECTION = "00000000-0000-4000-8000-000000000002"
SYNTHETIC_VALUES = {
    "fmnh_ins_number": "FMNH-INS 1001",
    "collection_code": "SYNTHETIC",
    "country": "United States",
    "province_state": "Illinois",
    "county": "Cook",
    "city": "Chicago",
    "precise_location": "Synthetic teaching garden",
    "elevation_from_m": "180",
    "elevation_to_m": "181",
    "elevation_from_ft": "590.55",
    "elevation_to_ft": "593.83",
    "habitat": "Synthetic grassland",
    "collection_method": "Synthetic net",
    "date_visited_from": "2020-06-01",
    "date_visited_to": "2020-06-01",
    "collectors": "Synthetic Collector",
    "verbatim_dts": "Synthetic D/T/S",
    "taxon": "Danaus plexippus",
    "identified_by_irn": "synthetic:eparties:1",
    "date_identified": "2020-06-02",
}
SYNTHETIC_TEXT = "\n".join(f"{k}: {v}" for k, v in SYNTHETIC_VALUES.items())


class BatchInput(Record):
    collection_id: str
    display_name: str = Field(min_length=1, max_length=200)
    acquisition_method: str = "files"


class ItemInput(Record):
    client_item_id: str = Field(min_length=1, max_length=100)
    filename: str = Field(min_length=1, max_length=255)
    media_type: str
    size_bytes: int = Field(gt=0, le=25000000)
    width: int | None = Field(default=None, gt=0, le=20000)
    height: int | None = Field(default=None, gt=0, le=20000)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class RevisionInput(Record):
    expected_revision: int = Field(ge=1)
    reason: str = ""


class DecisionInput(RevisionInput):
    base_record_version_id: str
    kind: str
    target_id: str = ""
    before: dict = Field(default_factory=dict)
    after: dict = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)


class RegionsInput(RevisionInput):
    base_run_id: str
    regions: list[Region]


class ClassificationInput(RevisionInput):
    collection_id: str
    profile_collection_id: str = "insects"


class ActionInput(RevisionInput):
    action: str


def summary(specimen: Specimen, role: str = "viewer") -> dict:
    run = specimen.run
    status = (
        "completed"
        if run.disposition
        else (
            run.stage
            if run.stage
            in {"processing_blocked", "retry_scheduled", "paused", "cancelled"}
            else "running"
        )
    )
    return {
        "specimen_id": specimen.id,
        "asset_id": specimen.asset.id,
        "collection_id": specimen.scope.collection_id,
        "organization_id": specimen.scope.organization_id,
        "revision": specimen.version,
        "batch_id": specimen.batch_id,
        "filename": specimen.asset.filename,
        "created_at": specimen.created_at,
        "domain_created_at": specimen.created_at,
        "active_run_id": run.id,
        "record_version_id": f"{run.id}:{specimen.version}",
        "status": status,
        "stage": run.stage,
        "disposition": run.disposition,
        "reason_codes": run.reasons,
        "blocker": run.blocker,
        "profile_id": run.profile.id,
        "profile_version": run.profile.version,
        "synthetic": run.profile.synthetic,
        "available_actions": (
            ["retry", "resume", "pause", "cancel", "reprocess"]
            if role in {"operator", "reviewer", "manager", "admin"}
            else []
        )
        + (
            [
                "field",
                "transcription",
                "coverage",
                "approve",
                "classification",
                "regions",
                "taxonomy_resolution",
                "authority_resolution",
                "capability_defer",
            ]
            if role in {"reviewer", "manager", "admin"}
            else []
        ),
    }


def workspace(specimen: Specimen, role: str = "viewer") -> dict:
    run = specimen.run
    return dict(
        summary(specimen, role),
        history_through_revision=specimen.history_through_revision,
        audit_offset=specimen.audit_offset,
        history_url=f"/v1/organizations/{specimen.scope.organization_id}/specimens/{specimen.id}/history",
        asset=specimen.asset.model_dump(),
        run=run.model_dump(mode="json"),
        regions=[
            dict(
                r.model_dump(),
                region_id=r.id,
                bbox=[r.x, r.y, r.x + r.width, r.y + r.height],
            )
            for r in run.regions
        ],
        observations=[
            dict(o.model_dump(), observation_id=o.id, verbatim_text=o.literal_text)
            for o in run.observations
        ],
        transcriptions=[
            dict(
                t.model_dump(mode="json"),
                verbatim_text=t.text,
                state=t.value_state.value
                if t.value_state
                else "supported"
                if t.resolved
                else "unresolved",
            )
            for t in run.transcripts
        ],
        fields={
            k: dict(v.model_dump(mode="json"), value_state=v.state.value)
            for k, v in run.fields.items()
        },
        evidence=[dict(e.model_dump(), evidence_id=e.id) for e in run.evidence],
        validations=[
            {"rule_id": r, "severity": "hard", "outcome": "fail", "reason_code": r}
            for r in run.reasons
        ],
        decisions=[
            e.model_dump() for e in specimen.audit if e.action.startswith("review")
        ],
        events=[
            dict(e.model_dump(), sequence=specimen.audit_offset + i + 1)
            for i, e in enumerate(specimen.audit)
        ],
    )


def create_app(
    *,
    mode: str,
    repository,
    blobs,
    adapters,
    token: str | None = None,
    identity_verifier=None,
    memberships=None,
    origins: list[str] | None = None,
    profile_registry=None,
    classifier=None,
    authority_tools=None,
    authority_cost_reservations=None,
    codec_policy=None,
) -> FastAPI:
    if mode not in {"synthetic", "emulator", "production"}:
        raise ValueError("Explicit application mode required")
    if mode == "production" and (
        isinstance(repository, SQLiteRepository)
        or isinstance(adapters, SyntheticAdapters)
    ):
        raise ValueError("Synthetic adapters forbidden in production")
    if mode == "synthetic" and not token:
        raise ValueError("Synthetic bearer token required")
    app = FastAPI(title="Specimen Digitization", version="0.1")
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST", "PUT"],
            allow_headers=[
                "Authorization",
                "Content-Type",
                "Idempotency-Key",
                "Upload-Offset",
                "X-Firebase-AppCheck",
            ],
        )
    registry = profile_registry or application_registry(mode == "synthetic")
    workflow = Workflow(
        repository,
        blobs,
        adapters,
        profile_registry=registry,
        classifier=classifier,
        authority_tools=authority_tools,
        authority_cost_reservations=authority_cost_reservations,
    )

    def process_background(p, ident):
        actor_uid.set(p.user_id)
        try:
            workflow.drain(p, ident)
        except Conflict:
            pass  # Another fenced worker won; retained state is authoritative.

    def schedule_local(p, s, background_tasks):
        if mode == "synthetic" and s.run.stage not in {
            "finalized",
            "processing_blocked",
            "paused",
            "cancelled",
        }:
            background_tasks.add_task(process_background, p, s.id)

    @app.exception_handler(Exception)
    async def errors(request, exc):
        status, code, category, message = (
            503,
            "runtime_unavailable",
            "operational",
            "Runtime operation failed; inspect server configuration",
        )
        if isinstance(exc, PermissionError):
            status, code, category, message = (
                403,
                "access_denied",
                "authorization",
                "Access denied",
            )
        elif isinstance(exc, Missing):
            status, code, category, message = (
                404,
                "not_found",
                "input",
                "Resource not found",
            )
        elif isinstance(exc, Conflict):
            status, code, category, message = (
                409,
                "revision_or_idempotency_conflict",
                "conflict",
                str(exc),
            )
        elif isinstance(exc, (ValueError, UnidentifiedImageError)):
            status, code, category, message = (
                422,
                "invalid_input",
                "input",
                str(exc)[:200],
            )
        elif isinstance(exc, (OperationalBlock, EvidenceIntegrityError)):
            message = str(exc)
        if isinstance(exc, SnapshotTooLarge):
            status, code, category = 413, "snapshot_too_large", "policy"
        if isinstance(exc, (GraphTooLarge, WorkspaceTooLarge)):
            status, code, category = (
                413,
                "workspace_artifact_required"
                if isinstance(exc, WorkspaceTooLarge)
                else "active_graph_limit_exceeded",
                "policy",
            )
        return JSONResponse(
            status_code=status,
            content={
                "error": {
                    "code": code,
                    "category": category,
                    "message": message,
                    "retryable": status == 503,
                    "request_id": uid(),
                    "details": exc.details
                    if isinstance(exc, WorkspaceTooLarge)
                    else {},
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "invalid_input",
                    "category": "input",
                    "message": "Request does not match API schema",
                    "retryable": False,
                    "request_id": uid(),
                    "details": {},
                }
            },
        )

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": "http_error",
                    "category": "authorization"
                    if exc.status_code in {401, 403}
                    else "input",
                    "message": str(exc.detail),
                    "retryable": False,
                    "request_id": uid(),
                    "details": {},
                }
            },
        )

    for handled in (
        Conflict,
        Missing,
        PermissionError,
        ValueError,
        OperationalBlock,
        EvidenceIntegrityError,
        SnapshotTooLarge,
    ):
        app.add_exception_handler(handled, errors)

    def identity(
        authorization: str = Header(default=""),
        x_firebase_appcheck: str = Header(default=""),
    ):
        if not authorization.startswith("Bearer "):
            from fastapi import HTTPException

            raise HTTPException(401, "Bearer identity required")
        bearer = authorization[7:]
        if mode == "synthetic":
            if not hmac.compare_digest(bearer, token or ""):
                from fastapi import HTTPException

                raise HTTPException(401, "Invalid synthetic bearer")
            user = "synthetic-reviewer"
        else:
            if identity_verifier is None:
                raise OperationalBlock("firebase_identity_verifier_not_configured")
            user = identity_verifier(bearer, x_firebase_appcheck)
        actor_uid.set(user)
        return user

    def member_rows(user):
        if mode == "synthetic":
            return [
                {
                    "organization_id": SYNTHETIC_ORG,
                    "collection_id": SYNTHETIC_COLLECTION,
                    "role": "reviewer",
                    "can_view_sensitive": True,
                }
            ]
        return memberships(user)

    def principal(user, org, collection, write=False, review=False):
        actor_uid.set(user)
        row = next(
            (
                m
                for m in member_rows(user)
                if m["organization_id"] == org and m["collection_id"] == collection
            ),
            None,
        )
        if (
            row is None
            or (
                write
                and row["role"] not in {"operator", "reviewer", "manager", "admin"}
            )
            or (review and row["role"] not in {"reviewer", "manager", "admin"})
        ):
            raise PermissionError()
        return Principal(
            user_id=user,
            scope=Scope(organization_id=org, collection_id=collection),
            role=row["role"],
        )

    def find(user, org, ident):
        for member in member_rows(user):
            if member["organization_id"] != org:
                continue
            p = principal(user, org, member["collection_id"])
            try:
                return p, repository.get(p.scope, ident)
            except Missing:
                pass
        raise Missing(ident)

    def find_document(user, org, kind, ident):
        for member in member_rows(user):
            if member["organization_id"] == org:
                p = principal(user, org, member["collection_id"])
                try:
                    return p, repository.document(p.scope, kind, ident)
                except Missing:
                    pass
        raise Missing(ident)

    def key(value):
        if not value or len(value) > 200:
            raise ValueError("Idempotency-Key is required and at most 200 characters")
        return value

    prefix = "/v1/organizations/{organization_id}"

    @app.get("/v1/session")
    def session(user=Depends(identity)):
        return {
            "user_id": user,
            "mode": mode,
            "memberships": member_rows(user),
            "persistence": "sqlite"
            if isinstance(repository, SQLiteRepository)
            else "sql_connect",
            "runtime_blockers": []
            if mode == "synthetic"
            else ["sam3_serving_not_configured", "institutional_policy_unapproved"],
            "synthetic_token_required": mode == "synthetic",
        }

    @app.get(prefix + "/collections")
    def collections(organization_id: str, user=Depends(identity)):
        return {
            "items": [
                {
                    "collection_id": m["collection_id"],
                    "display_name": "Insects",
                    "role": m["role"],
                    "profiles": [p.model_dump(mode="json") for p in registry.profiles],
                    "profile_registry_version": registry.version,
                    "classification_nodes": [
                        node.model_dump(mode="json") for node in registry.nodes
                    ],
                }
                for m in member_rows(user)
                if m["organization_id"] == organization_id
            ],
            "next_cursor": None,
        }

    @app.post(prefix + "/images/preflight")
    async def image_preflight(
        organization_id: str,
        collection_id: str,
        request: Request,
        user=Depends(identity),
    ):
        from .image_codecs import CodecPolicy
        from .image_preflight import preflight_image
        from starlette.concurrency import run_in_threadpool

        principal(user, organization_id, collection_id, write=True)
        policy = codec_policy or CodecPolicy()
        content = bytearray()
        async for part in request.stream():
            if len(content) + len(part) > policy.limits.max_bytes:
                raise ValueError("Preflight image exceeds configured byte limit")
            content.extend(part)
        if not content:
            raise ValueError("Preflight image is empty")
        result = await run_in_threadpool(
            preflight_image,
            bytes(content),
            request.headers.get("Content-Type", "application/octet-stream").split(";")[
                0
            ],
            policy,
        )
        return result.model_dump(mode="json")

    @app.post(prefix + "/batches")
    def create_batch(
        organization_id: str,
        body: BatchInput,
        user=Depends(identity),
        idempotency_key: str = Header(default=""),
    ):
        p = principal(user, organization_id, body.collection_id, write=True)
        ident = str(
            uuid5(
                NAMESPACE_URL, organization_id + user + "batch" + key(idempotency_key)
            )
        )
        payload = dict(
            body.model_dump(),
            batch_id=ident,
            items=[],
            request_digest=digest(body.model_dump()),
        )
        try:
            old = repository.document(p.scope, "batch", ident)
            if old["request_digest"] != payload["request_digest"]:
                raise Conflict("Idempotency payload mismatch")
            return old
        except Missing:
            return repository.put_document(p.scope, "batch", ident, payload, 0)

    @app.get(prefix + "/batches/{batch_id}")
    def batch(organization_id: str, batch_id: str, user=Depends(identity)):
        p, document = find_document(user, organization_id, "batch", batch_id)
        document["items"] = [
            u
            for u in repository.documents(p.scope, "upload")
            if u["batch_id"] == batch_id
        ]
        return document

    def duplicate_source(p, user, checksum):
        sensitive = any(
            m["organization_id"] == p.scope.organization_id
            and m["collection_id"] == p.scope.collection_id
            and m.get("can_view_sensitive")
            for m in member_rows(user)
        )
        matches = repository.find_checksum(p.scope, checksum, sensitive)
        if len(matches) > 1:
            raise Conflict("Source checksum migration requires administrator review")
        return matches[0]["id"] if matches else None

    @app.post(prefix + "/batches/{batch_id}/items")
    def item(
        organization_id: str,
        batch_id: str,
        body: ItemInput,
        user=Depends(identity),
        idempotency_key: str = Header(default=""),
    ):
        p, batch = find_document(user, organization_id, "batch", batch_id)
        principal(user, organization_id, p.scope.collection_id, write=True)
        key(idempotency_key)
        if (body.width is None) != (body.height is None):
            raise ValueError("Declare both pixel dimensions or omit both")
        if body.width is not None and body.width * body.height > 40000000:
            raise ValueError("Image exceeds 40 megapixel decoding limit")
        for prior in repository.documents(p.scope, "upload"):
            if (
                prior["batch_id"] == batch_id
                and prior.get("idempotency_key") == idempotency_key
            ):
                if prior["request_digest"] != digest(body.model_dump()):
                    raise Conflict("Idempotency payload mismatch")
                return prior
        ident = str(uuid5(NAMESPACE_URL, batch_id + body.client_item_id))
        payload = dict(
            body.model_dump(),
            upload_id=ident,
            asset_id=str(uuid5(NAMESPACE_URL, ident + "asset")),
            specimen_id=str(uuid5(NAMESPACE_URL, ident + "specimen")),
            batch_id=batch_id,
            collection_id=p.scope.collection_id,
            state="uploading",
            offset=0,
            chunks=[],
            request_digest=digest(body.model_dump()),
            idempotency_key=idempotency_key,
            upload_url=f"/v1/organizations/{organization_id}/uploads/{ident}/content",
            upload_method="PUT",
        )
        try:
            old = repository.document(p.scope, "upload", ident)
            if old["request_digest"] != payload["request_digest"]:
                raise Conflict("client_item_id reused with different content")
            return old
        except Missing:
            duplicate = duplicate_source(p, user, body.sha256)
            if duplicate:
                payload.update(state="duplicate", duplicate_specimen_id=duplicate)
            return repository.put_document(p.scope, "upload", ident, payload, 0)

    @app.get(prefix + "/uploads/{upload_id}")
    def upload(organization_id: str, upload_id: str, user=Depends(identity)):
        return find_document(user, organization_id, "upload", upload_id)[1]

    @app.post(prefix + "/uploads/{upload_id}/resume")
    def resume_upload(
        organization_id: str,
        upload_id: str,
        body: RevisionInput,
        user=Depends(identity),
    ):
        p, doc = find_document(user, organization_id, "upload", upload_id)
        principal(user, organization_id, p.scope.collection_id, write=True)
        if doc["revision"] != body.expected_revision:
            raise Conflict("Stale upload revision")
        return doc

    @app.put(prefix + "/uploads/{upload_id}/content")
    async def chunk(
        organization_id: str,
        upload_id: str,
        request: Request,
        user=Depends(identity),
        upload_offset: int = Header(default=0),
    ):
        p, doc = find_document(user, organization_id, "upload", upload_id)
        principal(user, organization_id, p.scope.collection_id, write=True)
        if doc["state"] != "uploading":
            raise Conflict("Upload no longer accepts content")
        data = bytearray()
        async for part in request.stream():
            data.extend(part)
            if len(data) > 4 * 1024 * 1024:
                raise ValueError("Chunk exceeds 4 MiB")
        content = bytes(data)
        if upload_offset != doc["offset"]:
            # Lost ACK replay is accepted only when the exact chunk was retained.
            prior = next(
                (c for c in doc["chunks"] if c["offset"] == upload_offset), None
            )
            if prior and hashlib.sha256(content).hexdigest() == prior["sha256"]:
                return doc
            raise Conflict("Upload offset mismatch")
        if not content or doc["offset"] + len(content) > doc["size_bytes"]:
            raise ValueError("Invalid chunk size")
        doc["chunks"].append(
            {
                "offset": upload_offset,
                "size": len(content),
                "ref": blobs.put(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
        doc["offset"] += len(content)
        return repository.put_document(
            p.scope, "upload", upload_id, doc, doc["revision"]
        )

    @app.post(prefix + "/uploads/{upload_id}/complete")
    def complete(
        organization_id: str,
        upload_id: str,
        body: RevisionInput,
        background_tasks: BackgroundTasks,
        user=Depends(identity),
        idempotency_key: str = Header(default=""),
    ):
        p, doc = find_document(user, organization_id, "upload", upload_id)
        principal(user, organization_id, p.scope.collection_id, write=True)
        key(idempotency_key)
        completion_digest = digest(
            {
                "upload": upload_id,
                "actor": user,
                "key": idempotency_key,
                "body": body.model_dump(mode="json"),
            }
        )
        if doc["state"] == "accepted":
            if doc.get("completion_digest") != completion_digest:
                raise Conflict(
                    "Upload completion request differs from accepted request"
                )
            return doc["completion_response"]
        if doc["revision"] != body.expected_revision:
            raise Conflict("Stale upload revision")
        if doc["offset"] != doc["size_bytes"]:
            raise Conflict("Upload incomplete")
        content = b"".join(blobs.get(c["ref"]) for c in doc["chunks"])
        if hashlib.sha256(content).hexdigest() != doc["sha256"]:
            raise ValueError("Original checksum mismatch")
        processing = None
        pixel_basis = "original_pixel_edges"
        special = doc["media_type"] in {
            "image/heic",
            "image/heif",
            "image/dng",
            "image/x-adobe-dng",
        }
        if special:
            from .image_codecs import CodecPolicy, decode_image

            policy = codec_policy or CodecPolicy()
            family = (
                "HEIC" if doc["media_type"] in {"image/heic", "image/heif"} else "DNG"
            )
            result, derivative = decode_image(content, family, policy)
            if result.status == "blocked":
                raise OperationalBlock("image_codec_" + result.reason)
            if result.status != "decoded" or derivative is None:
                raise ValueError("Invalid image: " + result.reason)
            provenance = result.provenance
            if provenance.actual_format != family:
                raise ValueError("Decoded image family mismatch")
            # HEIF's primary raster is already container-oriented. DNG's retained
            # view must be inverted to its explicitly recorded active-area basis.
            with Image.open(io.BytesIO(derivative)) as displayed:
                canonical = displayed.convert("RGB")
                orientation = provenance.transform.orientation
                inverse = {
                    2: Image.Transpose.FLIP_LEFT_RIGHT,
                    3: Image.Transpose.ROTATE_180,
                    4: Image.Transpose.FLIP_TOP_BOTTOM,
                    5: Image.Transpose.TRANSPOSE,
                    6: Image.Transpose.ROTATE_90,
                    7: Image.Transpose.TRANSVERSE,
                    8: Image.Transpose.ROTATE_270,
                }.get(orientation)
                if inverse is not None:
                    canonical = canonical.transpose(inverse)
                dimensions = canonical.size
                pixels = io.BytesIO()
                canonical.save(pixels, format="PNG")
                canonical_bytes = pixels.getvalue()
            processing = dict(
                provenance.model_dump(mode="json"),
                blob_ref=blobs.put(canonical_bytes),
                derivative_sha256=hashlib.sha256(canonical_bytes).hexdigest(),
                canonicalization="inverse_view_affine_to_declared_pixel_basis",
            )
            pixel_basis = provenance.coordinate_space
            actual_type = "image/heic" if family == "HEIC" else "image/dng"
        else:
            try:
                with Image.open(io.BytesIO(content)) as image:
                    image.verify()
                with Image.open(io.BytesIO(content)) as image:
                    actual_type = Image.MIME.get(image.format)
                    if actual_type not in {"image/png", "image/jpeg", "image/tiff"}:
                        raise ValueError("Image decoder format not supported")
                    if actual_type != doc["media_type"]:
                        raise ValueError("Declared image media type mismatch")
                    if image.width * image.height > 40000000 or max(image.size) > 20000:
                        raise ValueError("Decoded image resolution limit exceeded")
                    image.load()
                    dimensions = image.size
            except (
                OSError,
                SyntaxError,
                EOFError,
                Image.DecompressionBombError,
            ) as exc:
                raise ValueError("Invalid or truncated image content") from exc
            derivative, provenance = orientation_view(
                content, ImageLimits(allowed_formats=("JPEG", "PNG", "TIFF"))
            )
        if doc["width"] is not None and dimensions != (doc["width"], doc["height"]):
            raise ValueError("Declared image dimensions mismatch")
        doc.update(width=dimensions[0], height=dimensions[1])
        view = dict(provenance.model_dump(mode="json"), blob_ref=blobs.put(derivative))
        profile = Profile(
            synthetic=mode == "synthetic",
            institutional_policy_approved=mode == "synthetic",
            semantics_confirmed=mode == "synthetic",
        )
        specimen = Specimen(
            id=doc["specimen_id"],
            scope=p.scope,
            batch_id=doc["batch_id"],
            run=Run(profile=profile),
            asset=Asset(
                id=doc["asset_id"],
                view_derivative=view,
                processing_derivative=processing,
                pixel_basis=pixel_basis,
                sha256=doc["sha256"],
                blob_ref=blobs.put(content),
                media_type=actual_type,
                size_bytes=len(content),
                width=doc["width"],
                height=doc["height"],
                filename=doc["filename"],
                uploader=user,
            ),
        )
        specimen.audit.append(
            AuditEvent(
                actor=user, action="ingest", reason="Verified immutable original"
            )
        )
        duplicate = None
        try:
            specimen = repository.create(
                p, specimen, "ingest:" + upload_id, completion_digest
            )
        except Conflict:
            duplicate = duplicate_source(p, user, doc["sha256"])
            if not duplicate or duplicate == specimen.id:
                raise
            specimen = repository.get(p.scope, duplicate)
        response = summary(specimen, p.role)
        if duplicate:
            response.update(upload_state="duplicate", duplicate_specimen_id=duplicate)
        doc.update(
            state="accepted",
            completion_digest=completion_digest,
            completion_response=response,
        )
        repository.put_document(p.scope, "upload", upload_id, doc, doc["revision"])
        if mode == "synthetic" and not duplicate:
            background_tasks.add_task(process_background, p, specimen.id)
        return response

    def history_access(user, organization_id, specimen_id):
        p, current = find(user, organization_id, specimen_id)
        if not any(
            m["organization_id"] == p.scope.organization_id
            and m["collection_id"] == p.scope.collection_id
            and m.get("can_view_sensitive")
            for m in member_rows(user)
        ):
            raise PermissionError(
                "Historical evidence requires current sensitive-data permission"
            )
        return p, current

    @app.get(prefix + "/specimens/{specimen_id}/history")
    def history(
        organization_id: str,
        specimen_id: str,
        after_revision: int = 0,
        through_revision: int | None = None,
        limit: int = 10,
        user=Depends(identity),
    ):
        p, _ = history_access(user, organization_id, specimen_id)
        if not 1 <= limit <= 50:
            raise ValueError("Invalid history page bounds")
        return repository.history_page(
            p.scope, specimen_id, after_revision, through_revision, limit
        )

    @app.get(prefix + "/specimens/{specimen_id}/history/{revision}")
    def historical_version(
        organization_id: str,
        specimen_id: str,
        revision: int,
        run_sha256: str | None = None,
        run_id: str | None = None,
        user=Depends(identity),
    ):
        p, _ = history_access(user, organization_id, specimen_id)
        retained = repository.version(p.scope, specimen_id, revision)
        retained_info = repository.version_info(p.scope, specimen_id, revision)
        if run_id is not None and retained_info["run_id"] != run_id:
            raise Conflict("Historical run reference mismatch")
        if run_sha256 is not None and retained_info["run_sha256"] != run_sha256:
            raise Conflict("Historical run digest mismatch")
        return render_workspace(retained, p)

    @app.get(prefix + "/specimens/{specimen_id}/active-graph")
    def active_graph_output(
        organization_id: str,
        specimen_id: str,
        revision: int | None = None,
        user=Depends(identity),
    ):
        p, current = history_access(user, organization_id, specimen_id)
        selected = revision if revision is not None else current.version
        raw = repository.graph_bytes(p.scope, specimen_id, selected)
        if len(raw) > GRAPH_LIMIT:
            raise GraphTooLarge("Active graph exceeds supported retrieval limit")
        return Response(
            raw,
            media_type="application/json",
            headers={
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "X-Specimen-Revision": str(selected),
                "X-Content-SHA256": hashlib.sha256(raw).hexdigest(),
            },
        )

    @app.get(prefix + "/specimens/{specimen_id}/phases/{phase}")
    def phase_output(
        organization_id: str,
        specimen_id: str,
        phase: str,
        revision: int | None = None,
        user=Depends(identity),
    ):
        p, current = history_access(user, organization_id, specimen_id)
        selected = (
            repository.version(p.scope, specimen_id, revision)
            if revision is not None
            else current
        )
        if phase not in selected.run.phase_results:
            raise Missing(phase)
        return phase_artifact(selected, phase, blobs).model_dump(mode="json")

    def artifact_specimen(user, organization_id, specimen_id, revision):
        p, current = history_access(user, organization_id, specimen_id)
        return (
            repository.version(p.scope, specimen_id, revision)
            if revision is not None
            else current
        )

    def authority_metadata(selected, tool_id, field_key):
        matches = [
            m
            for m in selected.run.authority_results.values()
            if m["tool_id"] == tool_id
            and (field_key is None or m["field_key"] == field_key)
        ]
        if not matches:
            raise Missing(tool_id)
        if len(matches) != 1:
            raise ValueError(
                "field_key is required to identify one retained authority result"
            )
        return matches[0]

    @app.get(prefix + "/specimens/{specimen_id}/authority-results/{tool_id}")
    def authority_output(
        organization_id: str,
        specimen_id: str,
        tool_id: str,
        revision: int | None = None,
        field_key: str | None = None,
        user=Depends(identity),
    ):
        selected = artifact_specimen(user, organization_id, specimen_id, revision)
        metadata = authority_metadata(selected, tool_id, field_key)
        return read_authority_result(metadata, blobs).model_dump(mode="json")

    @app.get(prefix + "/specimens/{specimen_id}/authority-results/{tool_id}/raw")
    def authority_raw(
        organization_id: str,
        specimen_id: str,
        tool_id: str,
        revision: int | None = None,
        field_key: str | None = None,
        user=Depends(identity),
    ):
        selected = artifact_specimen(user, organization_id, specimen_id, revision)
        metadata = authority_metadata(selected, tool_id, field_key)
        result = read_authority_result(metadata, blobs)
        if not result.raw_ref or not result.response_sha256:
            raise Missing("Authority response body unavailable")
        content = read_artifact(
            {"blob_ref": result.raw_ref, "sha256": result.response_sha256},
            blobs,
            max_bytes=1048576,
        )
        if len(content) > 1048576:
            raise ValueError("Raw evidence exceeds the 1 MiB response limit")
        return Response(
            content,
            media_type="text/plain",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    @app.get(prefix + "/specimens/{specimen_id}/observations/{observation_id}/raw")
    def observation_raw(
        organization_id: str,
        specimen_id: str,
        observation_id: str,
        revision: int | None = None,
        user=Depends(identity),
    ):
        selected = artifact_specimen(user, organization_id, specimen_id, revision)
        observation = next(
            (o for o in selected.run.observations if o.id == observation_id), None
        )
        if observation is None:
            raise Missing(observation_id)
        content = read_artifact(
            {"blob_ref": observation.raw_ref, "sha256": observation.raw_sha256},
            blobs,
            max_bytes=1048576,
        )
        if len(content) > 1048576:
            raise ValueError("Raw evidence exceeds the 1 MiB response limit")
        return Response(
            content,
            media_type="text/plain",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    @app.get(prefix + "/specimens/{specimen_id}/observations/{observation_id}/metadata")
    def reading_metadata_output(
        organization_id: str,
        specimen_id: str,
        observation_id: str,
        revision: int | None = None,
        user=Depends(identity),
    ):
        import json

        selected = artifact_specimen(user, organization_id, specimen_id, revision)
        metadata = selected.run.reading_metadata.get(observation_id)
        if metadata is None:
            raise Missing(observation_id)
        return json.loads(read_artifact(metadata, blobs))

    @app.get(prefix + "/specimens/{specimen_id}/disagreements/{region_id}")
    def disagreement_output(
        organization_id: str,
        specimen_id: str,
        region_id: str,
        revision: int | None = None,
        user=Depends(identity),
    ):
        import json

        selected = artifact_specimen(user, organization_id, specimen_id, revision)
        metadata = next(
            (m for m in selected.run.disagreements if m["region_id"] == region_id), None
        )
        if metadata is None:
            raise Missing(region_id)
        return json.loads(read_artifact(metadata, blobs))

    def search_metadata(
        p, user, filters, cutoff=None, after_created=None, after_id="", limit=50
    ):
        from .domain import now

        sensitive = any(
            m["organization_id"] == p.scope.organization_id
            and m["collection_id"] == p.scope.collection_id
            and m.get("can_view_sensitive")
            for m in member_rows(user)
        )
        return repository.search(
            p.scope, filters, cutoff or now(), after_created, after_id, limit, sensitive
        )

    def render_workspace(specimen, p, mutation_committed=False):
        from .search import SearchFilters

        result = workspace(specimen, p.role)
        metadata = search_metadata(
            p, p.user_id, SearchFilters(specimen_id=specimen.id), limit=1
        )
        if not metadata:
            raise Missing(specimen.id)
        result["created_at"] = metadata[0]["created_at"]
        result["domain_created_at"] = specimen.created_at
        result["active_graph"] = specimen.active_graph
        result["active_graph_url"] = (
            f"/v1/organizations/{p.scope.organization_id}/specimens/{specimen.id}/active-graph?revision={specimen.version}"
        )
        if len(encoded(result)) > WORKSPACE_LIMIT:
            raise WorkspaceTooLarge(
                {
                    "revision": specimen.version,
                    "record_version_id": result["record_version_id"],
                    "summary_url": f"/v1/organizations/{p.scope.organization_id}/specimens/{specimen.id}",
                    "artifact_url": result["active_graph_url"],
                    "mutation_committed": mutation_committed,
                    "workspace_max_bytes": WORKSPACE_LIMIT,
                    "graph_max_bytes": GRAPH_LIMIT,
                    "artifact_sha256": specimen.active_graph["sha256"],
                    "artifact_size_bytes": specimen.active_graph["size_bytes"],
                }
            )
        return result

    def exact_records(p, user, **filters):
        from .search import SearchFilters

        rows = search_metadata(p, user, SearchFilters(**filters), limit=2)
        return [repository.get(p.scope, row["specimen_id"]) for row in rows]

    @app.get(prefix + "/specimens")
    def specimens(
        organization_id: str,
        collection_id: str,
        request: Request,
        cursor: str | None = None,
        limit: int = 50,
        user=Depends(identity),
    ):
        from .search import SearchFilters, binding, decode_cursor, encode_cursor

        p = principal(user, organization_id, collection_id)
        allowed = set(SearchFilters.model_fields) | {"collection_id", "cursor", "limit"}
        if set(request.query_params) - allowed or any(
            len(request.query_params.getlist(k)) != 1 for k in request.query_params
        ):
            raise ValueError("Unknown or duplicated search filter")
        filters = SearchFilters.model_validate(
            {
                k: v
                for k, v in request.query_params.items()
                if k in SearchFilters.model_fields
            }
        )
        if not 1 <= limit <= 100:
            raise ValueError("Search limit must be 1 to 100")
        sensitive = any(
            m["organization_id"] == organization_id
            and m["collection_id"] == collection_id
            and m.get("can_view_sensitive")
            for m in member_rows(user)
        )
        bound = binding(p.scope, filters, user, sensitive)
        cutoff, after_created, after_id = decode_cursor(cursor, bound)
        items = repository.search(
            p.scope, filters, cutoff, after_created, after_id, limit, sensitive
        )
        # A full page may have an empty terminal page. This keeps each DB query <=100.
        following = (
            encode_cursor(bound, cutoff, items[-1]) if len(items) == limit else None
        )
        for item in items:
            item["available_actions"] = (
                ["retry", "resume", "pause", "cancel", "reprocess"]
                if p.role in {"operator", "reviewer", "manager", "admin"}
                else []
            )
        return {"items": items, "next_cursor": following, "cutoff": cutoff}

    @app.get(prefix + "/specimens/{specimen_id}")
    def detail(organization_id: str, specimen_id: str, user=Depends(identity)):
        p, s = find(user, organization_id, specimen_id)
        from .search import SearchFilters

        result = summary(s, p.role)
        metadata = search_metadata(p, user, SearchFilters(specimen_id=s.id), limit=1)
        if not metadata:
            raise Missing(specimen_id)
        result.update(
            {
                k: metadata[0][k]
                for k in (
                    "created_at",
                    "domain_created_at",
                    "risk",
                    "risk_calibrated",
                    "uploader_id",
                )
            }
        )
        return result

    @app.get(prefix + "/specimens/{specimen_id}/workspace")
    def workbench(organization_id: str, specimen_id: str, user=Depends(identity)):
        p, s = find(user, organization_id, specimen_id)
        return render_workspace(s, p)

    @app.get(prefix + "/assets/{asset_id}/access")
    def asset_access(organization_id: str, asset_id: str, user=Depends(identity)):
        for m in member_rows(user):
            if m["organization_id"] != organization_id or not m.get(
                "can_view_sensitive"
            ):
                continue
            p = principal(user, organization_id, m["collection_id"])
            for s in exact_records(p, user, asset_id=asset_id):
                if s.asset.id == asset_id:
                    return {
                        "url": f"/v1/organizations/{organization_id}/assets/{asset_id}/content",
                        "requires_authorization": True,
                        "view_url": f"/v1/organizations/{organization_id}/assets/{asset_id}/content?view=true"
                        if s.asset.view_derivative
                        else None,
                        "asset": s.asset.model_dump(),
                    }
        raise Missing(asset_id)

    @app.get(prefix + "/assets/{asset_id}/content")
    def asset_content(
        organization_id: str, asset_id: str, view: bool = False, user=Depends(identity)
    ):
        for m in member_rows(user):
            if m["organization_id"] != organization_id or not m.get(
                "can_view_sensitive"
            ):
                continue
            p = principal(user, organization_id, m["collection_id"])
            for s in exact_records(p, user, asset_id=asset_id):
                if s.asset.id == asset_id:
                    if view:
                        if not s.asset.view_derivative:
                            raise Missing("Oriented view unavailable")
                        derived = s.asset.view_derivative
                        content = blobs.get(derived["blob_ref"])
                        if (
                            hashlib.sha256(content).hexdigest()
                            != derived["derivative_sha256"]
                            or derived["original_sha256"] != s.asset.sha256
                        ):
                            raise OperationalBlock("view_integrity_failure")
                    else:
                        content = blobs.get(s.asset.blob_ref)
                    return Response(
                        content,
                        media_type="image/png" if view else s.asset.media_type,
                        headers={"Cache-Control": "no-store"},
                    )
        raise Missing(asset_id)

    def invalidate_authorities(run, field_key=None):
        affected = {
            key
            for key, metadata in run.authority_results.items()
            if field_key is None or metadata["field_key"] == field_key
        }
        affected.update(
            key
            for key, metadata in run.authority_unresolved.items()
            if field_key is None or metadata["field_key"] == field_key
        )
        for key in affected:
            run.authority_results.pop(key, None)
            run.authority_unresolved.pop(key, None)
        run.completed_steps = [
            step
            for step in run.completed_steps
            if step not in affected
            and not (field_key is None and step.startswith("authority:"))
        ]
        # Old attempt receipts remain immutable and attempts are monotone. A new query
        # gets a new attempt ID, so a correction cannot replay an old result.
        run.phase_results = {}
        run.review_risk = {}

    @app.post(prefix + "/specimens/{specimen_id}/decisions")
    def decision(
        organization_id: str,
        specimen_id: str,
        body: DecisionInput,
        background_tasks: BackgroundTasks,
        user=Depends(identity),
        idempotency_key: str = Header(default=""),
    ):
        p, s = find(user, organization_id, specimen_id)
        principal(user, organization_id, p.scope.collection_id, review=True)
        key(idempotency_key)
        if not body.reason.strip():
            raise ValueError("Review reason required")
        if body.base_record_version_id != f"{s.run.id}:{body.expected_revision}":
            raise Conflict("Wrong base record version")
        before_digest = repository.version_info(p.scope, s.id, s.version)["run_sha256"]
        before = {
            "specimen_id": s.id,
            "revision": s.version,
            "run_id": s.run.id,
            "run_sha256": before_digest,
            "history_url": f"/v1/organizations/{organization_id}/specimens/{s.id}/history/{s.version}?run_sha256={before_digest}&run_id={s.run.id}",
        }
        if body.kind == "field":
            if body.target_id not in s.run.fields:
                raise ValueError("Unknown field")
            if any(e not in {x.id for x in s.run.evidence} for e in body.evidence_ids):
                raise ValueError("Unknown evidence reference")
            field = FieldValue.model_validate(
                dict(body.after, evidence_ids=body.evidence_ids)
            )
            s.run.fields[body.target_id] = field
            invalidate_authorities(s.run, body.target_id)
            s.run.human_approved = False
            if body.target_id == "taxon" or any(
                t["field_key"] == body.target_id for t in s.run.authority_plan
            ):
                if body.target_id == "taxon":
                    s.run.lookups = []
                s.run.completed_steps = [
                    x
                    for x in s.run.completed_steps
                    if x
                    not in {"lookup", "resolve", "normalize", "validate", "finalize"}
                ]
                s.run.stage = "lookup"
                s.run.disposition = None
        elif body.kind == "transcription":
            transcript = next(
                (t for t in s.run.transcripts if t.region_id == body.target_id), None
            )
            if transcript is None:
                raise ValueError("Unknown region")
            text = body.after.get("text")
            state = body.after.get("state", "supported")
            if state not in {
                "supported",
                "unknown",
                "unreadable",
                "unresolved",
                "ambiguous",
                "not_present",
            }:
                raise ValueError("Unsupported transcription state")
            if state == "supported" and (not isinstance(text, str) or not text.strip()):
                raise ValueError("Supported literal text required")
            if state != "supported" and text is not None:
                raise ValueError("An abstention carries null text, not a placeholder")
            invalidate_authorities(s.run)
            transcript.text = text
            transcript.resolved = state == "supported"
            transcript.value_state = ValueState(state)
            transcript.actor = user
            transcript.reason = body.reason
            s.run.completed_steps = [
                x
                for x in s.run.completed_steps
                if x
                not in {
                    "parse",
                    "plan",
                    "lookup",
                    "resolve",
                    "normalize",
                    "validate",
                    "finalize",
                }
            ]
            s.run.lookups = []
            s.run.human_approved = False
            s.run.stage = "parse"
            s.run.disposition = None
        elif body.kind == "authority_resolution":
            tool_id = body.after.get("tool_id")
            if body.after.get("field_key", body.target_id) != body.target_id:
                raise ValueError("Authority field_key must match target_id")
            identifier = body.after.get("identifier")
            metadata = next(
                (
                    m
                    for m in s.run.authority_results.values()
                    if m["tool_id"] == tool_id and m["field_key"] == body.target_id
                ),
                None,
            )
            if metadata is None or not identifier:
                raise ValueError("Retained authority candidates are required")
            result = read_authority_result(metadata, blobs)
            if result.status.value not in {"success", "ambiguous"}:
                raise ValueError(
                    "Operational or unmatched authority result cannot be selected"
                )
            candidates = [
                candidate
                for candidate in result.candidates
                if candidate.identifier == identifier
            ]
            if len(candidates) != 1 or body.target_id not in s.run.fields:
                raise ValueError("Select one retained authority candidate")
            candidate = candidates[0]
            if tool_id == "parties" and candidate.identity is None:
                raise ValueError(
                    "Parties selection requires a fully qualified eparties identity"
                )
            evidence = Evidence(
                kind="authority_selection",
                source=result.source_id,
                locator="candidate:" + candidate.identifier,
                excerpt=candidate.name + " | " + candidate.identifier,
                raw_ref=result.raw_ref,
                digest=result.response_sha256,
            )
            s.run.evidence.append(evidence)
            field = s.run.fields[body.target_id]
            field.authority_id = candidate.identifier
            field.authority_identity = (
                candidate.identity.model_dump(mode="json")
                if candidate.identity
                else None
            )
            field.normalized = candidate.name
            field.evidence_ids.append(evidence.id)
            s.run.human_approved = False
        elif body.kind == "taxonomy_resolution":
            if not s.run.lookups or s.run.lookups[-1].status.value not in {
                "success",
                "ambiguous",
            }:
                raise ValueError("A completed candidate-bearing lookup is required")
            lookup = s.run.lookups[-1]
            selected = str(body.after.get("authority_id", ""))
            choices = [
                candidate.get("usage", candidate) for candidate in lookup.candidates
            ]
            choice = next(
                (
                    candidate
                    for candidate in choices
                    if str(candidate.get("key", "")) == selected and selected
                ),
                None,
            )
            if choice is None or not choice.get("scientificName"):
                raise ValueError("Select a retained authoritative candidate")
            evidence = Evidence(
                kind="authority_selection",
                source=lookup.id,
                locator="candidate:" + selected,
                excerpt=str(choice),
                raw_ref=lookup.raw_ref,
                digest=lookup.digest,
            )
            s.run.evidence.append(evidence)
            s.run.fields["taxon"].normalized = choice["scientificName"]
            s.run.fields["taxon"].authority_id = selected
            s.run.fields["taxon"].evidence_ids.append(evidence.id)
            s.run.human_approved = False
        elif body.kind == "capability_defer":
            reason_code = body.after.get("capability_reason")
            retry = body.after.get("retry_eligibility")
            if (
                reason_code not in {"unsupported_script", "severe_source_damage"}
                or not isinstance(retry, str)
                or not retry.strip()
            ):
                raise ValueError(
                    "Documented capability reason and retry eligibility required"
                )
            if not s.run.regions or any(
                len([o for o in s.run.observations if o.region_id == r.id]) < 2
                for r in s.run.regions
            ):
                raise ValueError(
                    "All independent attempts must finish before capability deferral"
                )
            if not all(
                o.unreadable_spans or o.literal_text.strip() == "[unreadable]"
                for o in s.run.observations
            ):
                raise ValueError(
                    "Capability deferral requires retained unreadable-source observations"
                )
            s.run.capability_reason = reason_code
            s.run.retry_eligibility = retry
            s.run.completed_steps.append("capability_attempts_exhausted")
        elif body.kind == "approve":
            s.run.human_approved = True
        elif body.kind == "coverage":
            s.run.coverage_confirmed = body.after.get("confirmed") is True
        else:
            raise ValueError("Unsupported review decision")
        if s.run.stage == "finalized" or body.kind in {"approve", "capability_defer"}:
            try:
                verify_evidence(s, blobs)
                if s.run.blocker == "evidence_integrity_failure":
                    s.run.blocker = None
            except EvidenceIntegrityError:
                s.run.blocker = "evidence_integrity_failure"
            phase_result = None
            if s.run.blocker != "evidence_integrity_failure":
                phase_result = refresh_review_evidence(s, blobs)
            finalize(s.run)
            if phase_result is not None:
                apply_phase_gate(s.run, phase_result)
        s.audit.append(
            AuditEvent(
                actor=user,
                action="review_" + body.kind,
                reason=body.reason,
                before=before,
                after=body.after,
            )
        )
        s = save_recoverably(
            repository,
            p,
            s,
            body.expected_revision,
            "decision:" + idempotency_key,
            digest(body.model_dump()),
        )
        schedule_local(p, s, background_tasks)
        return render_workspace(s, p, mutation_committed=True)

    @app.post(prefix + "/specimens/{specimen_id}/regions")
    def regions(
        organization_id: str,
        specimen_id: str,
        body: RegionsInput,
        background_tasks: BackgroundTasks,
        user=Depends(identity),
        idempotency_key: str = Header(default=""),
    ):
        p, s = find(user, organization_id, specimen_id)
        if has_active_lease(s.run):
            raise Conflict(
                "An external effect is still leased; wait for its result or lease expiry"
            )
        principal(user, organization_id, p.scope.collection_id, review=True)
        if not body.reason.strip() or body.base_run_id != s.run.id:
            raise ValueError("Current run and reason required")
        if len({r.id for r in body.regions}) != len(body.regions):
            raise ValueError("Duplicate region IDs")
        for r in body.regions:
            if (
                r.asset_id != s.asset.id
                or r.x + r.width > s.asset.width
                or r.y + r.height > s.asset.height
            ):
                raise ValueError("Region outside original")
        old = s.run.model_copy(deep=True)
        s.previous_runs.append(old)
        s.run = Run(
            profile=old.profile,
            profile_snapshot=old.profile_snapshot,
            profile_registry_version=old.profile_registry_version,
            classification=old.classification,
            classification_raw_sha256=old.classification_raw_sha256,
            classification_selection=old.classification_selection,
            regions=body.regions,
            coverage_confirmed=True,
            completed_steps=["classify", "segment"],
            stage="transcribe",
        )
        s.audit.append(
            AuditEvent(
                actor=user,
                action="review_regions",
                reason=body.reason,
                before={"run_id": old.id},
                after={"run_id": s.run.id},
            )
        )
        saved = repository.save(
            p,
            s,
            body.expected_revision,
            "regions:" + key(idempotency_key),
            digest(body.model_dump()),
        )
        schedule_local(p, saved, background_tasks)
        return render_workspace(saved, p, mutation_committed=True)

    @app.post(prefix + "/specimens/{specimen_id}/classification")
    def classification(
        organization_id: str,
        specimen_id: str,
        body: ClassificationInput,
        background_tasks: BackgroundTasks,
        user=Depends(identity),
        idempotency_key: str = Header(default=""),
    ):
        p, s = find(user, organization_id, specimen_id)
        if has_active_lease(s.run):
            raise Conflict(
                "An external effect is still leased; wait for its result or lease expiry"
            )
        principal(user, organization_id, p.scope.collection_id, review=True)
        if body.collection_id != p.scope.collection_id:
            raise ValueError(
                "No published profile mapping for requested collection; transfer requires separate authorization"
            )
        if not body.reason.strip():
            raise ValueError("Reason required")
        resolution = registry.resolve(body.profile_collection_id)
        if resolution.status != "selected":
            raise ValueError("Published profile unavailable: " + resolution.reason)
        s.previous_runs.append(s.run)
        s.run = Run(
            profile=s.run.profile,
            classification_selection=ManualSelection(
                collection_id=body.profile_collection_id,
                actor_id=user,
                reason=body.reason,
            ).model_dump(mode="json"),
        )
        s.audit.append(
            AuditEvent(
                actor=user,
                action="review_classification",
                reason=body.reason,
                after={
                    "profile_collection_id": body.profile_collection_id,
                    "profile_version": resolution.profile.version,
                },
            )
        )
        saved = repository.save(
            p,
            s,
            body.expected_revision,
            "classification:" + key(idempotency_key),
            digest(body.model_dump()),
        )
        schedule_local(p, saved, background_tasks)
        return render_workspace(saved, p, mutation_committed=True)

    @app.post(prefix + "/runs/{run_id}/actions")
    def action(
        organization_id: str,
        run_id: str,
        body: ActionInput,
        background_tasks: BackgroundTasks,
        user=Depends(identity),
        idempotency_key: str = Header(default=""),
    ):
        for m in member_rows(user):
            if m["organization_id"] != organization_id:
                continue
            p = principal(user, organization_id, m["collection_id"], write=True)
            for s in exact_records(p, user, active_run_id=run_id):
                if s.run.id != run_id:
                    continue
                if not body.reason.strip():
                    raise ValueError("Action reason required")
                if body.action in {"retry", "resume", "reprocess"} and has_active_lease(
                    s.run
                ):
                    raise Conflict(
                        "An external effect is still leased; concurrent retry is prohibited"
                    )
                if body.action in {"retry", "resume"}:
                    s.run.blocker = None
                    s.run.disposition = None
                    s.run.stage = Workflow.next_step(s.run).split(":")[0]
                    if s.run.lookups and s.run.lookups[-1].status.value not in {
                        "success",
                        "no_match",
                        "ambiguous",
                    }:
                        # Retain failed attempts as history, but rerun the failed lookup.
                        pass
                elif body.action in {"pause", "cancel"}:
                    s.run.stage = "paused" if body.action == "pause" else "cancelled"
                    s.run.disposition = None
                elif body.action == "reprocess":
                    s.previous_runs.append(s.run)
                    s.run = Run(
                        profile=s.run.profile,
                        classification_selection=s.run.classification_selection,
                    )
                else:
                    raise ValueError("Unsupported action")
                s.audit.append(
                    AuditEvent(actor=user, action=body.action, reason=body.reason)
                )
                saved = repository.save(
                    p,
                    s,
                    body.expected_revision,
                    "action:" + key(idempotency_key),
                    digest(body.model_dump()),
                )
                schedule_local(p, saved, background_tasks)
                return summary(saved, p.role)
        raise Missing(run_id)

    @app.get(prefix + "/runs/{run_id}/events")
    def events(
        organization_id: str,
        run_id: str,
        user=Depends(identity),
        after_sequence: int = 0,
    ):
        for m in member_rows(user):
            if m["organization_id"] != organization_id:
                continue
            p = principal(user, organization_id, m["collection_id"])
            for s in exact_records(p, user, active_run_id=run_id):
                if s.run.id == run_id:
                    return {
                        "items": [
                            dict(e.model_dump(), sequence=s.audit_offset + i + 1)
                            for i, e in enumerate(s.audit)
                            if s.audit_offset + i + 1 > after_sequence
                        ],
                        "next_cursor": None,
                        "blocker": s.run.blocker,
                    }
        raise Missing(run_id)

    # Explicit worker endpoint in synthetic mode allows deterministic UI demo; production
    # dispatch is a separate authenticated worker process, never arbitrary client inference.
    if mode == "synthetic":

        @app.post(prefix + "/specimens/{specimen_id}/process")
        def process(organization_id: str, specimen_id: str, user=Depends(identity)):
            p, s = find(user, organization_id, specimen_id)
            return render_workspace(workflow.drain(p, s.id), p, mutation_committed=True)

    app.state.workflow = workflow
    return app


def local_app(root: Path, token: str, persistence: str = "sqlite"):
    if persistence not in {"sqlite", "sql-emulator"}:
        raise ValueError("Invalid local persistence")
    if persistence == "sql-emulator":
        from .production import SqlConnectRepository, sql_emulator_host

        repository = SqlConnectRepository(
            project="demo-specimen-data", emulator_host=sql_emulator_host()
        )
    else:
        repository = SQLiteRepository(root / "state.sqlite3")
    blobs = LocalBlobs(root / "blobs")
    return create_app(
        mode="synthetic",
        repository=repository,
        blobs=blobs,
        adapters=SyntheticAdapters(blobs, SYNTHETIC_TEXT),
        token=token,
        origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    )
