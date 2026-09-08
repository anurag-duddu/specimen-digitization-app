"""Explicit production adapters: ADC SQL Connect/GCS and approved HF routes."""

from __future__ import annotations
import contextvars
import hashlib
import json
import os
from uuid import UUID

import google.auth
from google.auth.transport.requests import AuthorizedSession
from google.cloud import storage
from pydantic_ai import BinaryContent
from pydantic_ai.messages import ModelMessagesTypeAdapter

from ..model_gateway import HuggingFaceModelGateway
from ..prompts import CollectionPromptInputs, PromptName, resolve_prompt
from ..transcription import build_literal_transcription_agent
from .domain import Observation, Specimen
from .lookup import GbifTaxonomy
from .storage import Conflict, Missing, digest, check_snapshot
from .workflow import OperationalBlock, crop_bytes

actor_uid = contextvars.ContextVar("verified_actor_uid", default=None)


class SqlConnectRepository:
    def __init__(
        self,
        project="specimen-digitization",
        location="us-east4",
        service="specimen-digitization-service",
        connector="specimen-server",
        session=None,
        emulator_host=None,
    ):
        self.project = project
        if emulator_host:
            if project != "demo-specimen-data" or emulator_host != "127.0.0.1:9499":
                raise ValueError("Emulator must use isolated loopback demo project")
            import requests

            self.session = session or requests.Session()
            origin = "http://" + emulator_host
        else:
            credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            self.session = session or AuthorizedSession(credentials)
            origin = "https://firebasedataconnect.googleapis.com"
        self.url = f"{origin}/v1/projects/{project}/locations/{location}/services/{service}/connectors/{connector}"

    def execute(self, operation, variables, mutation=False):
        response = self.session.post(
            self.url + (":impersonateMutation" if mutation else ":impersonateQuery"),
            json={"operationName": operation, "variables": variables},
            timeout=30,
        )
        if response.status_code in {401, 403}:
            raise PermissionError("SQL Connect access denied")
        if response.status_code != 200:
            raise OperationalBlock("sql_connect_unavailable_or_connector_not_published")
        body = response.json()
        if body.get("errors"):
            raise Conflict(
                "SQL Connect transaction rejected; reload current revision and membership"
            )
        return body.get("data", {})

    @staticmethod
    def variables(scope):
        uid = actor_uid.get()
        if not uid:
            raise PermissionError("Verified actor context required")
        return {
            "organizationId": scope.organization_id,
            "collectionId": scope.collection_id,
            "actorUid": uid,
        }

    def memberships(self, uid):
        result = self.execute("Memberships", {"actorUid": uid})
        orgs = {
            str(UUID(m["organizationId"]))
            for m in result.get("organizationMembers", [])
            if m["active"]
        }
        return [
            {
                "organization_id": str(UUID(m["organizationId"])),
                "collection_id": str(UUID(m["collectionId"])),
                "role": m["role"],
                "can_view_sensitive": m["canViewSensitive"],
            }
            for m in result.get("collectionMembers", [])
            if m["active"] and str(UUID(m["organizationId"])) in orgs
        ]

    def get(self, scope, specimen_id):
        data = self.execute("GetSpecimen", dict(self.variables(scope), id=specimen_id))
        snapshots = data.get("specimenSnapshots", [])
        if not data.get("specimen") or not snapshots:
            raise Missing(specimen_id)
        row = self.execute(
            "GetSnapshot",
            dict(
                self.variables(scope),
                id=specimen_id,
                revision=data["specimen"]["revision"],
            ),
        )["specimenSnapshot"]
        return self._snapshot(row)

    @staticmethod
    def _snapshot(row):
        payload = row["snapshot"]
        specimen = Specimen.model_validate(payload)

        # Canonical numeric JSON survives protobuf Struct / PostgreSQL round-trips.
        if digest(payload) != row["sha256"]:
            # Compatibility with early development fixtures whose sole float field
            # was serialized as 0.0 (including copies inside review audit snapshots).
            def legacy(item):
                if isinstance(item, dict):
                    return {
                        k: float(v)
                        if k == "disagreement_ratio" and isinstance(v, (int, float))
                        else legacy(v)
                        for k, v in item.items()
                    }
                if isinstance(item, list):
                    return [legacy(v) for v in item]
                return item

            previous = hashlib.sha256(
                json.dumps(
                    legacy(payload),
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode()
            ).hexdigest()
            if previous != row["sha256"]:
                raise Conflict("Snapshot digest mismatch")
        return specimen

    def list(self, scope):
        results = []
        for offset in range(0, 10000, 100):
            data = self.execute(
                "ListSpecimens",
                dict(
                    self.variables(scope),
                    limit=100,
                    offset=offset,
                    includeSensitive=any(
                        m["organization_id"] == scope.organization_id
                        and m["collection_id"] == scope.collection_id
                        and m["can_view_sensitive"]
                        for m in self.memberships(actor_uid.get())
                    ),
                ),
            )
            rows = data.get("specimens", [])
            results.extend(self.get(scope, row["id"]) for row in rows)
            if len(rows) < 100:
                break
        return results

    def create(self, principal, specimen, key, digest):
        return self._commit(principal, specimen, 0, key, digest)

    def save(self, principal, specimen, expected_revision, key, digest):
        return self._commit(principal, specimen, expected_revision, key, digest)

    def _commit(self, principal, specimen, expected, key, request_digest):
        if principal.scope != specimen.scope or principal.user_id != actor_uid.get():
            raise PermissionError("Verified actor/scope mismatch")
        operation = "create" if not expected else "save:" + specimen.id
        base = self.variables(principal.scope)
        receipt = self.execute(
            "GetReceipt", dict(base, operation=operation, idempotencyKey=key)
        ).get("requestReceipt")
        if receipt:
            if receipt["requestSha256"] != request_digest:
                raise Conflict("Idempotency key reused")
            row = self.execute(
                "GetSnapshot",
                dict(base, id=receipt["specimenId"], revision=receipt["revision"]),
            )["specimenSnapshot"]
            return self._snapshot(row)
        specimen = specimen.model_copy(deep=True)
        specimen.version = expected + 1
        check_snapshot(specimen.model_dump_json())
        payload = specimen.model_dump(mode="json")
        variables = dict(
            base,
            id=specimen.id,
            snapshot=payload,
            snapshotSha256=digest(payload),
            requestSha256=request_digest,
            idempotencyKey=key,
            operation=operation,
            state=(
                "completed"
                if specimen.run.disposition
                else specimen.run.stage
                if specimen.run.stage
                in {"retry_scheduled", "paused", "cancelled", "processing_blocked"}
                else "running"
            ),
            sensitive=True,
            contractVersion="0.1",
        )
        if expected:
            variables.update(
                expectedRevision=expected,
                activeRunId=specimen.run.id,
                disposition=specimen.run.disposition,
                action="checkpoint_or_review",
            )
        self.execute(
            "SaveSpecimen" if expected else "CreateSpecimen", variables, mutation=True
        )
        return specimen

    def document(self, scope, kind, ident):
        row = self.execute(
            "GetDocument", dict(self.variables(scope), kind=kind, id=ident)
        ).get("auxiliaryDocument")
        if not row:
            raise Missing(ident)
        return row["payload"]

    def documents(self, scope, kind):
        results = []
        for offset in range(0, 10000, 100):
            rows = self.execute(
                "ListDocuments",
                dict(self.variables(scope), kind=kind, limit=100, offset=offset),
            ).get("auxiliaryDocuments", [])
            results.extend(r["payload"] for r in rows)
            if len(rows) < 100:
                break
        return results

    def put_document(self, scope, kind, ident, payload, expected):
        payload = dict(payload, revision=expected + 1)
        variables = dict(
            self.variables(scope),
            kind=kind,
            id=ident,
            payload=payload,
            operation=f"{kind}:{ident}",
            idempotencyKey=f"revision:{expected}",
            requestSha256=digest(payload),
        )
        if expected:
            variables["expectedRevision"] = expected
        self.execute(
            "SaveDocument" if expected else "CreateDocument", variables, mutation=True
        )
        return payload


class GcsBlobs:
    def __init__(self, bucket="specimen-digitization.firebasestorage.app"):
        self.bucket = storage.Client(project="specimen-digitization").bucket(bucket)

    def put(self, data):
        checksum = hashlib.sha256(data).hexdigest()
        blob = self.bucket.blob("application/sha256/" + checksum)
        from google.api_core.exceptions import PreconditionFailed

        try:
            blob.upload_from_string(data, if_generation_match=0, checksum="crc32c")
        except PreconditionFailed:
            if blob.download_as_bytes() != data:
                raise Conflict("Immutable object mismatch")
        blob.reload()
        return f"{checksum}:{blob.generation}"

    def get(self, ref):
        checksum, generation = ref.split(":")
        if (
            len(checksum) != 64
            or not all(c in "0123456789abcdef" for c in checksum)
            or not generation.isdigit()
        ):
            raise Missing("Invalid object reference")
        data = self.bucket.blob(
            "application/sha256/" + checksum, generation=int(generation)
        ).download_as_bytes()
        if hashlib.sha256(data).hexdigest() != checksum:
            raise Conflict("Object digest mismatch")
        return data


class ProductionAdapters:
    def __init__(self, blobs):
        self.blobs = blobs
        self.taxonomy = GbifTaxonomy(blobs)

    def segment(self, specimen):
        # A deployment-specific SAM3 endpoint must implement the reviewed adapter.
        # No rectangle substitution, no hidden Hub download or paid execution.
        endpoint = os.getenv("SPECIMEN_SAM3_ENDPOINT")
        if not endpoint:
            raise OperationalBlock(
                "sam3_serving_contract_not_configured_use_reviewed_regions"
            )
        return Sam3Service(endpoint, self.blobs).segment(specimen)

    def transcribe(self, specimen, region, route):
        if os.getenv("SPECIMEN_APPROVED_INFERENCE") != "true":
            raise OperationalBlock(
                "provider_data_policy_and_spending_approval_required"
            )
        gateway = HuggingFaceModelGateway()
        selected = gateway.route(route)
        prompt = resolve_prompt(
            PromptName.LITERAL_TRANSCRIPTION,
            CollectionPromptInputs(
                collection_profile_id=specimen.run.profile.id,
                collection_name="Insects",
                schema_version=specimen.run.profile.schema_version,
            ),
        )
        agent = build_literal_transcription_agent(
            gateway, route_id=route, prompt=prompt
        )
        image = crop_bytes(self.blobs, specimen, region)
        result = agent.run_sync(
            [
                "Transcribe only the supplied source image.",
                BinaryContent(data=image, media_type="image/png"),
            ]
        )
        # Preserve every provider response (including retries), excluding image-bearing requests.
        responses = [m for m in result.all_messages() if m.kind == "response"]
        raw = ModelMessagesTypeAdapter.dump_json(responses)
        return Observation(
            region_id=region.id,
            route_id=route,
            model_id=selected.model_id,
            provider=selected.provider,
            prompt_version=hashlib.sha256(prompt.text.encode()).hexdigest(),
            input_sha256=hashlib.sha256(image).hexdigest(),
            literal_text=result.output.verbatim_text,
            unreadable_spans=result.output.unreadable_spans,
            raw_ref=self.blobs.put(raw),
            raw_sha256=hashlib.sha256(raw).hexdigest(),
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
        )

    def extract(self, specimen):
        if os.getenv("SPECIMEN_APPROVED_INFERENCE") != "true":
            raise OperationalBlock(
                "provider_data_policy_and_spending_approval_required"
            )
        from .harness import extract_with_agent

        extract_with_agent(HuggingFaceModelGateway(), self.blobs, specimen)

    def lookup(self, name):
        return self.taxonomy.lookup(name)


class Sam3Service:
    """Pinned remote SAM3 activity contract. Service must return original pixel regions.

    This adapter is executable once a separately approved GPU service exists; no
    service is provisioned by the application or substituted by a fixture.
    """

    def __init__(self, endpoint: str, blobs, session=None):
        from urllib.parse import urlparse

        parsed = urlparse(endpoint)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or not parsed.hostname.endswith(".run.app")
            or parsed.username
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "SAM3 endpoint must be an approved HTTPS Cloud Run service"
            )
        self.endpoint = endpoint.rstrip("/")
        self.blobs = blobs
        self.session = session

    def segment(self, specimen):
        import httpx
        from google.auth.transport.requests import Request
        from google.oauth2.id_token import fetch_id_token
        from .domain import Region

        from ..hub_models import SAM3_MODEL

        revision = SAM3_MODEL.revision
        bearer = fetch_id_token(Request(), self.endpoint)
        client = self.session or httpx.Client(timeout=120, follow_redirects=False)
        response = client.post(
            self.endpoint + "/v1/segment",
            headers={
                "Authorization": "Bearer " + bearer,
                "Idempotency-Key": specimen.run.id + ":segment",
            },
            json={
                "run_id": specimen.run.id,
                "asset_id": specimen.asset.id,
                "blob_ref": specimen.asset.blob_ref,
                "sha256": specimen.asset.sha256,
                "width": specimen.asset.width,
                "height": specimen.asset.height,
                "model_id": "facebook/sam3",
                "model_revision": revision,
                "prompt": "label",
            },
        )
        if response.status_code != 200:
            raise OperationalBlock("sam3_service_failed")
        payload = response.json()
        if (
            payload.get("model_revision") != revision
            or payload.get("model_id") != "facebook/sam3"
        ):
            raise OperationalBlock("sam3_unpinned_response")
        regions = [Region.model_validate(r) for r in payload["regions"]]
        if any(
            r.method != "sam3" or r.version != revision or not r.mask_ref
            for r in regions
        ):
            raise OperationalBlock("sam3_missing_mask_provenance")
        return regions
