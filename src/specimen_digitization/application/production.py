"""Explicit production adapters: ADC SQL Connect/GCS and approved HF routes."""

from __future__ import annotations
import contextvars
import hashlib
from .active_graph import original_run_digest, unpack
import json
import os
import re
from uuid import UUID

import google.auth
from google.auth.transport.requests import AuthorizedSession
from google.cloud import storage
from pydantic_ai import BinaryContent
from pydantic_ai.messages import ModelMessagesTypeAdapter

from ..model_gateway import HuggingFaceModelGateway, INITIAL_HUGGINGFACE_ROUTES
from ..prompts import CollectionPromptInputs, PromptName, resolve_prompt, ResolvedPrompt
from ..transcription import build_literal_transcription_agent
from .domain import Observation, WorkItem, WorkPage, now
from .lookup import GbifTaxonomy
from .storage import (
    compact_history,
    Conflict,
    Missing,
    digest,
    check_snapshot,
    work_available_at,
)
from .workflow import OperationalBlock, crop_bytes
from .reliability import run_agent_bounded
from pydantic_ai.usage import UsageLimits

actor_uid = contextvars.ContextVar("verified_actor_uid", default=None)


def sql_emulator_host() -> str:
    host = os.getenv("SPECIMEN_SQL_EMULATOR_HOST", "127.0.0.1:9499")
    match = re.fullmatch(r"127\.0\.0\.1:([0-9]{1,5})", host)
    if not match or not 1 <= int(match.group(1)) <= 65535:
        raise ValueError("SQL emulator host must be 127.0.0.1 with a valid TCP port")
    return host


class SqlConnectRepository:
    def __init__(
        self,
        project="specimen-digitization",
        location="us-east4",
        service="specimen-digitization-service",
        connector="specimen-server",
        session=None,
        emulator_host=None,
        graph_blobs=None,
    ):
        self.project = project
        self.graph_blobs = graph_blobs
        if emulator_host:
            if (
                project != "demo-specimen-data"
                or not re.fullmatch(r"127\.0\.0\.1:[0-9]{1,5}", emulator_host)
                or not 1 <= int(emulator_host.rsplit(":", 1)[1]) <= 65535
            ):
                raise ValueError("Emulator must use isolated loopback demo project")
            import requests

            self.session = session or requests.Session()
            origin = "http://" + emulator_host
        else:
            if os.getenv("SPECIMEN_SQL_EMULATOR_HOST"):
                raise ValueError("Production rejects SQL emulator configuration")
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

    def find_checksum(self, scope, checksum, include_sensitive=False):
        return self.execute(
            "FindSpecimenByChecksum",
            dict(
                self.variables(scope),
                checksum=checksum,
                includeSensitive=include_sensitive,
            ),
        ).get("specimens", [])

    def search(
        self,
        scope,
        filters,
        cutoff,
        after_created=None,
        after_id="",
        limit=50,
        include_sensitive=False,
    ):
        from .search import sql_item

        mapping = {
            "specimen_id": "specimenId",
            "asset_id": "assetId",
            "active_run_id": "activeRunId",
            "batch_id": "batchId",
            "uploader_id": "uploader",
            "state": "status",
            "stage": "stage",
            "disposition": "disposition",
            "profile_id": "profileId",
            "profile_version": "profileVersion",
            "reason_code": "reasonCode",
            "blocker": "blocker",
            "created_from": "createdFrom",
            "created_before": "createdBefore",
            "risk_min": "riskMin",
            "risk_max": "riskMax",
        }
        variables = dict(
            self.variables(scope),
            cutoff=cutoff,
            afterCreatedAt=after_created,
            afterId=after_id,
            limit=limit,
            includeSensitive=include_sensitive,
        )
        variables.update(
            {mapping[key]: value for key, value in filters.model_dump().items()}
        )
        rows = self.execute("SearchSpecimens", variables).get("items", [])
        return [sql_item(row, scope) for row in rows]

    def _snapshot(self, row):
        payload = row["snapshot"]
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

        return unpack(payload, self.graph_blobs)

    def history_page(
        self, scope, ident, after_revision=0, through_revision=None, limit=50
    ):
        current = self.get(scope, ident)
        through = current.version if through_revision is None else through_revision
        if (
            not 1 <= limit <= 100
            or not 0 <= after_revision <= through <= current.version
        ):
            raise ValueError("Invalid history page bounds")
        rows = self.execute(
            "ListSnapshotHistory",
            dict(
                self.variables(scope),
                id=ident,
                afterRevision=after_revision,
                throughRevision=through,
                limit=limit,
            ),
        ).get("specimenSnapshots", [])
        items = [{"revision": row["revision"], "sha256": row["sha256"]} for row in rows]
        return {
            "items": items,
            "through_revision": through,
            "next_cursor": items[-1]["revision"]
            if len(items) == limit and items[-1]["revision"] < through
            else None,
        }

    def version(self, scope, ident, revision):
        row = self.execute(
            "GetSnapshot", dict(self.variables(scope), id=ident, revision=revision)
        ).get("specimenSnapshot")
        if not row:
            raise Missing(ident)
        return self._snapshot(row)

    def due_page(self, scope, cutoff, after_id=None, limit=50):
        if not 1 <= limit <= 100:
            raise ValueError("Invalid page size")
        rows = self.execute(
            "ListDueWork",
            dict(
                self.variables(scope),
                cutoff=cutoff,
                afterId=after_id or "",
                limit=limit,
            ),
        ).get("items", [])
        items = [
            WorkItem(
                specimen_id=str(UUID(row["id"])),
                revision=row["revision"],
                state=row["state"],
                work_available_at=row.get("workAvailableAt") or row["createdAt"],
                created_at=row["createdAt"],
            )
            for row in rows
        ]
        return WorkPage(
            items=items,
            next_cursor=items[-1].specimen_id if len(items) == limit else None,
        )

    def list(self, scope):
        results, after, cutoff = [], "", now()
        sensitive = any(
            m["organization_id"] == scope.organization_id
            and m["collection_id"] == scope.collection_id
            and m["can_view_sensitive"]
            for m in self.memberships(actor_uid.get())
        )
        while True:
            rows = self.execute(
                "ListSpecimenPage",
                dict(
                    self.variables(scope),
                    cutoff=cutoff,
                    afterId=after,
                    limit=100,
                    includeSensitive=sensitive,
                ),
            ).get("specimens", [])
            results.extend(self.get(scope, str(UUID(row["id"]))) for row in rows)
            if len(rows) < 100:
                return results
            after = str(UUID(rows[-1]["id"]))

    def version_info(self, scope, ident, revision):
        row = self.execute(
            "GetSnapshot", dict(self.variables(scope), id=ident, revision=revision)
        ).get("specimenSnapshot")
        if not row:
            raise Missing(ident)
        self._snapshot(row)
        return {
            "revision": revision,
            "sha256": row["sha256"],
            "run_sha256": original_run_digest(row["snapshot"], self.graph_blobs),
            "run_id": row["snapshot"]["run"]["id"],
        }

    def graph_bytes(self, scope, ident, revision):
        row = self.execute(
            "GetSnapshot", dict(self.variables(scope), id=ident, revision=revision)
        ).get("specimenSnapshot")
        if not row:
            raise Missing(ident)
        self._snapshot(row)
        from .active_graph import read_graph, encoded

        graph = read_graph(row["snapshot"], self.graph_blobs)
        return (
            graph[0]
            if graph
            else encoded(
                {
                    "contract_version": "active-run-v1",
                    "scope": scope.model_dump(),
                    "specimen_id": ident,
                    "revision": revision,
                    "run": row["snapshot"]["run"],
                }
            )
        )

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
        if expected and len(specimen.model_dump_json().encode()) > 128 * 1024:
            specimen = compact_history(
                specimen, self.version(principal.scope, specimen.id, expected)
            )
        from .active_graph import pack

        payload = pack(specimen, self.graph_blobs)
        check_snapshot(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
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
            workAvailableAt=work_available_at(specimen),
        )
        if expected:
            variables.update(
                expectedRevision=expected,
                activeRunId=specimen.run.id,
                disposition=specimen.run.disposition,
                action="checkpoint_or_review",
            )
        if not expected:
            variables["sourceChecksum"] = specimen.asset.sha256
        self.execute(
            "SaveSpecimenV3" if expected else "CreateSpecimenV3",
            variables,
            mutation=True,
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
        results, after, cutoff = [], "", now()
        while True:
            rows = self.execute(
                "ListDocumentPage",
                dict(
                    self.variables(scope),
                    kind=kind,
                    cutoff=cutoff,
                    afterId=after,
                    limit=100,
                ),
            ).get("auxiliaryDocuments", [])
            results.extend(
                self.document(scope, kind, str(UUID(row["id"]))) for row in rows
            )
            if len(rows) < 100:
                return results
            after = str(UUID(rows[-1]["id"]))

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
        from .blob_limits import ORIGINAL_BYTES

        return self.get_bounded(ref, ORIGINAL_BYTES)

    def get_bounded(self, ref, max_bytes):
        from urllib.parse import quote
        from .blob_limits import read_limited, verify_digest, BlobTooLarge

        try:
            checksum, generation = ref.split(":")
        except ValueError as exc:
            raise Missing("Invalid object reference") from exc
        if (
            len(checksum) != 64
            or not all(c in "0123456789abcdef" for c in checksum)
            or not generation.isdigit()
        ):
            raise Missing("Invalid object reference")
        # AuthorizedSession streams the generation-pinned media response. Reading
        # raw in requested chunks avoids download_as_bytes allocation and survives
        # a dishonest Content-Length or an ignored Range response without truncation.
        url = (
            "https://storage.googleapis.com/storage/v1/b/"
            + quote(self.bucket.name, safe="")
            + "/o/"
            + quote("application/sha256/" + checksum, safe="")
        )
        response = self.bucket.client._http.get(
            url,
            params={"alt": "media", "generation": generation},
            stream=True,
            headers={"Accept-Encoding": "identity"},
            allow_redirects=False,
            timeout=30,
        )
        with response:
            if response.status_code == 404:
                raise Missing("Object generation not found")
            if response.status_code != 200:
                raise OperationalBlock("object_storage_unavailable")
            declared = response.headers.get("Content-Length")
            if declared is not None:
                try:
                    declared = int(declared)
                except ValueError as exc:
                    raise OperationalBlock("invalid_object_length") from exc
                if declared < 0:
                    raise OperationalBlock("invalid_object_length")
                if declared > max_bytes:
                    raise BlobTooLarge("Evidence exceeds the configured byte limit")
            data = read_limited(
                lambda count: response.raw.read(count, decode_content=False), max_bytes
            )
        return verify_digest(data, checksum)


class ProductionAdapters:
    def __init__(self, blobs):
        self.blobs = blobs
        self.taxonomy = GbifTaxonomy(blobs)
        from .authority_registry import AuthorityRegistry
        from .parties import PartiesAdapter
        from .geography import GeographyAdapter

        registry = AuthorityRegistry(version="unconfigured")
        self.authority_tools = {
            "parties": PartiesAdapter(registry, blobs),
            "geography": GeographyAdapter(registry, blobs),
        }
        self.authority_cost_reservations = {"geography": 0}

    def pin_dependencies(self, run):
        inputs = CollectionPromptInputs(
            collection_profile_id=run.profile.id,
            collection_name="Insects",
            schema_version=run.profile.schema_version,
        )
        prompts = {
            name.value: resolve_prompt(name, inputs).model_dump(mode="json")
            for name in PromptName
        }
        routes = {
            route: {
                "model_id": INITIAL_HUGGINGFACE_ROUTES[route].model_id,
                "provider": INITIAL_HUGGINGFACE_ROUTES[route].provider,
            }
            for route in run.profile.routes
        }
        return {
            "prompts": prompts,
            "routes": routes,
            "adapter_version": "production-v2",
            "segmentation": {
                "endpoint": os.getenv("SPECIMEN_SAM3_ENDPOINT"),
                "revision": os.getenv("SPECIMEN_SAM3_REVISION"),
            },
            "policy": run.profile.execution.model_dump(mode="json"),
        }

    def segment(self, specimen):
        # A deployment-specific SAM3 endpoint must implement the reviewed adapter.
        # No rectangle substitution, no hidden Hub download or paid execution.
        endpoint = os.getenv("SPECIMEN_SAM3_ENDPOINT")
        if specimen.run.dependencies.get("segmentation") != {
            "endpoint": endpoint,
            "revision": os.getenv("SPECIMEN_SAM3_REVISION"),
        }:
            raise OperationalBlock(
                "segmentation_configuration_changed_requires_new_run"
            )
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
        gateway = HuggingFaceModelGateway(
            timeout_seconds=specimen.run.profile.execution.external_timeout_seconds / 2
        )
        selected = gateway.route(route)
        pins = specimen.run.dependencies
        expected = pins.get("routes", {}).get(route)
        if not expected or expected != {
            "model_id": selected.model_id,
            "provider": selected.provider,
        }:
            raise OperationalBlock("pinned_model_route_unavailable")
        try:
            prompt = ResolvedPrompt.model_validate(
                pins["prompts"][PromptName.LITERAL_TRANSCRIPTION.value]
            )
        except (KeyError, ValueError) as exc:
            raise OperationalBlock("pinned_prompt_unavailable") from exc
        agent = build_literal_transcription_agent(
            gateway, route_id=route, prompt=prompt
        )
        image = crop_bytes(self.blobs, specimen, region)
        result = run_agent_bounded(
            agent,
            [
                "Transcribe only the supplied source image.",
                BinaryContent(data=image, media_type="image/png"),
            ],
            timeout_seconds=specimen.run.profile.execution.external_timeout_seconds,
            usage_limits=UsageLimits(request_limit=2, total_tokens_limit=16000),
        )
        # Preserve every provider response (including retries), excluding image-bearing requests.
        responses = [m for m in result.all_messages() if m.kind == "response"]
        raw = ModelMessagesTypeAdapter.dump_json(responses)
        from .reading_declarations import model_evidence

        raw_ref = self.blobs.put(raw)
        raw_sha256 = hashlib.sha256(raw).hexdigest()
        prompt_version = hashlib.sha256(prompt.text.encode()).hexdigest()
        return Observation(
            declaration_evidence=model_evidence(
                self.blobs,
                result.output,
                raw_ref,
                raw_sha256,
                selected.model_id,
                prompt_version,
            ),
            region_id=region.id,
            route_id=route,
            model_id=selected.model_id,
            provider=selected.provider,
            prompt_version=prompt_version,
            input_sha256=hashlib.sha256(image).hexdigest(),
            literal_text=result.output.verbatim_text,
            unreadable_spans=result.output.unreadable_spans,
            raw_ref=raw_ref,
            raw_sha256=raw_sha256,
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
        )

    def extract(self, specimen):
        if os.getenv("SPECIMEN_APPROVED_INFERENCE") != "true":
            raise OperationalBlock(
                "provider_data_policy_and_spending_approval_required"
            )
        from .harness import extract_with_agent

        gateway = HuggingFaceModelGateway(
            timeout_seconds=specimen.run.profile.execution.external_timeout_seconds / 2
        )
        for route in specimen.run.profile.routes:
            selected = gateway.route(route)
            if specimen.run.dependencies.get("routes", {}).get(route) != {
                "model_id": selected.model_id,
                "provider": selected.provider,
            }:
                raise OperationalBlock("pinned_model_route_changed_requires_new_run")
        extract_with_agent(gateway, self.blobs, specimen)

    def lookup(self, name):
        return self.taxonomy.lookup(name)


class Sam3Service:
    """Pinned remote SAM3 activity contract. Service must return original pixel regions.

    This adapter is executable once a separately approved GPU service exists; no
    service is provisioned by the application or substituted by a fixture.
    """

    def __init__(self, endpoint: str, blobs, effect=None):
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
        from .sam3_effect import sam3_request

        self.effect = effect or sam3_request

    def segment(self, specimen):
        import base64
        from .domain import Region
        from .bounded_effect import run_isolated
        from ..hub_models import SAM3_MODEL

        revision = SAM3_MODEL.revision
        request = {
            "run_id": specimen.run.id,
            "asset_id": specimen.asset.id,
            "blob_ref": specimen.asset.blob_ref,
            "sha256": specimen.asset.sha256,
            "width": specimen.asset.width,
            "height": specimen.asset.height,
            "model_id": "facebook/sam3",
            "model_revision": revision,
            "prompt": "label",
        }
        result = run_isolated(
            self.effect,
            {
                "endpoint": self.endpoint,
                "request": request,
                "timeout_seconds": specimen.run.profile.execution.external_timeout_seconds,
                "max_response_bytes": 1024 * 1024,
            },
            specimen.run.profile.execution.external_timeout_seconds,
            2 * 1024 * 1024,
        )
        if result.status != "completed" or not result.cleanup_complete:
            # The remote service may have accepted a timed-out request. The outer
            # retained intent/lease remains fenced, and no automatic retry occurs.
            raise OperationalBlock("external_outcome_unknown")
        envelope = json.loads(result.value)
        raw = base64.b64decode(envelope["body_base64"], validate=True)
        specimen.run.segmentation = {
            "blob_ref": self.blobs.put(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "model_id": "facebook/sam3",
            "model_revision": revision,
            "input_sha256": specimen.asset.sha256,
            "http_status": envelope["http_status"],
            "validation": envelope["validation"],
            "elapsed_seconds": result.elapsed_seconds,
        }
        if envelope["validation"] != "valid":
            raise OperationalBlock("sam3_" + envelope["validation"])
        payload = json.loads(raw)
        return [Region.model_validate(item) for item in payload["regions"]]
