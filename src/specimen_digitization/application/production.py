"""Explicit production adapters: ADC SQL Connect/GCS and approved HF routes."""

from __future__ import annotations
from ..observability import model_trace_context, tenant_ids
import contextvars
from contextlib import contextmanager
import hashlib
from .active_graph import original_run_digest, unpack
import json
import logging
import os
import re
import time
from collections import OrderedDict
from uuid import UUID

import google.auth
import requests
from google.auth.transport.requests import AuthorizedSession
from google.cloud import storage
from pydantic_ai import BinaryContent
from pydantic_ai.messages import ModelMessagesTypeAdapter

from ..model_gateway import (
    HUGGINGFACE_ROUTES,
    READER_HUGGINGFACE_ROUTES,
    HuggingFaceModelGateway,
)
from ..prompts import CollectionPromptInputs, PromptName, resolve_prompt, ResolvedPrompt
from ..transcription import build_literal_transcription_agent
from .domain import Observation, WorkItem, WorkPage, now
from .lane import run_status
from .lookup import GbifTaxonomy
from .projection import Blob, writes
from .storage import (
    compact_history,
    Conflict,
    Missing,
    ProjectionResult,
    digest,
    check_snapshot,
    work_available_at,
    stamp_review_events,
    ReviewSnapshot,
    ReviewProofReader,
    verify_review_decision_row,
)
from .workflow import OperationalBlock, crop_bytes
from .reliability import ReadingStopped, run_agent_bounded, stopped_usage
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.usage import UsageLimits

from .upload_documents import bind_sqlite_upload_lookups
from .worker_deadline import deadline_call, guarded
from ..process_logging import log_code

bind_sqlite_upload_lookups()

actor_uid = contextvars.ContextVar("verified_actor_uid", default=None)


@contextmanager
def verified_actor_context(user_id: str):
    """Bind one verified actor across await/to_thread, always reset its token."""
    if not isinstance(user_id, str) or not user_id:
        raise PermissionError("Verified actor context required")
    token = actor_uid.set(user_id)
    try:
        yield
    finally:
        actor_uid.reset(token)

LOGGER = logging.getLogger(__name__)
# Specimens whose written projection rows this process remembers (DATA_CONTRACT.md 11).
PROJECTED_SPECIMENS = 256
# Roles whose saves also write review decisions; additive V2 admits no other.
REVIEW_ROLES = {"reviewer", "manager", "admin"}
# Specimens whose cost rows this process remembers sending, and the rows one
# UpsertCostEntriesV1 call carries (the connector takes at most 500).
COSTED_SPECIMENS = 256
COST_ROWS_PER_CALL = 200


class ProjectionRejected(RuntimeError):
    """A projection write the connector refused for a reason other than a replay."""


# A request whose connection drops, or whose answer times out, is sent again at
# most twice more, after a pause of 1 s and then 2 s. An HTTP answer is final.
SQL_CONNECT_SENDS = 3
SQL_CONNECT_DROPPED = (requests.ConnectionError, requests.ReadTimeout)
# The mutations a repeat cannot apply twice. Each is one @transaction that
# applies only at its expected revision, or as a first revision, and inserts a
# receipt keyed by its idempotency key (dataconnect/connector/checksum.gql and
# sensitivity.gql), so the connector refuses a repeat of a committed send whole.
# Any other mutation is sent once. A query is a read and is always sent again.
REPEATABLE_MUTATIONS = frozenset(
    {"CreateSpecimenV3", "SaveSpecimenV3", "CreateDocumentV2", "SaveDocumentV2"}
)


class RepeatRefused(Conflict):
    """A save sent again after a dropped connection, and refused. The first
    send may have committed before its answer was lost; its receipt says so."""


# A specimen id as GetSpecimen's `$id: UUID!` takes it: 8-4-4-4-12 hex digits, with
# or without the hyphens (the connector returns them without).
SPECIMEN_UUID = re.compile(
    r"[0-9a-fA-F]{8}(-?)[0-9a-fA-F]{4}\1[0-9a-fA-F]{4}\1[0-9a-fA-F]{4}\1[0-9a-fA-F]{12}"
)


def graphql_error_code(errors) -> str:
    """The first GraphQL error's `extensions.code`, safe to log (never its message)."""
    first = errors[0] if isinstance(errors, list) and errors else None
    extensions = first.get("extensions") if isinstance(first, dict) else None
    return log_code(extensions.get("code") if isinstance(extensions, dict) else None)


def sql_emulator_host() -> str:
    host = os.getenv("SPECIMEN_SQL_EMULATOR_HOST", "127.0.0.1:9499")
    match = re.fullmatch(r"127\.0\.0\.1:([0-9]{1,5})", host)
    if not match or not 1 <= int(match.group(1)) <= 65535:
        raise ValueError("SQL emulator host must be 127.0.0.1 with a valid TCP port")
    return host


SQL_ENDPOINT_KEYS = (
    ("location", "SPECIMEN_SQL_LOCATION"),
    ("service", "SPECIMEN_SQL_SERVICE"),
    ("connector", "SPECIMEN_SQL_CONNECTOR"),
)
SQL_ENDPOINT_NAME = re.compile(r"[a-z][a-z0-9-]{1,62}")


def sql_endpoint_from_env(env=None) -> dict[str, str]:
    """Bind the worker to the same named SQL endpoint the API was pinned to.

    The API reads these three variables in ``RuntimeConfig.from_env`` and the
    release pins the same values on the worker job, so both processes reach one
    endpoint. They are accepted here under the API's own validation, all three
    together or not at all: a half-supplied endpoint would silently mix a
    configured value with a built-in default, which is exactly the drift this
    exists to prevent. Nothing set means the constructor defaults apply.
    """
    env = os.environ if env is None else env
    supplied = {field: env.get(key) for field, key in SQL_ENDPOINT_KEYS if env.get(key)}
    if not supplied:
        return {}
    if len(supplied) != len(SQL_ENDPOINT_KEYS) or not all(
        SQL_ENDPOINT_NAME.fullmatch(value) for value in supplied.values()
    ):
        raise ValueError(
            "Explicit SQL location, service and connector required together"
        )
    return supplied


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
        from .graph_review_summary import GraphReviewCache

        self.project = project
        self.graph_blobs = graph_blobs
        self.review_graph_cache = GraphReviewCache()
        self._projected: OrderedDict[str, set[str]] = OrderedDict()
        # Specimen id -> {cost row id: digest of the row as last sent}.
        self._costed: OrderedDict[str, dict[str, str]] = OrderedDict()
        self._sizes: dict[str, int] = {}
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
            if session is None:
                credentials, _ = google.auth.default(
                    scopes=["https://www.googleapis.com/auth/cloud-platform"]
                )
                session = AuthorizedSession(credentials)
            self.session = session
            origin = "https://firebasedataconnect.googleapis.com"
        self.url = f"{origin}/v1/projects/{project}/locations/{location}/services/{service}/connectors/{connector}"

    # Between sends after a dropped connection; tests replace it.
    pause = staticmethod(time.sleep)

    @guarded
    def execute(self, operation, variables, mutation=False):
        sends = SQL_CONNECT_SENDS if not mutation or operation in REPEATABLE_MUTATIONS else 1
        for send in range(1, sends + 1):
            try:
                response = deadline_call(
                    self.session.post,
                    self.url + (":impersonateMutation" if mutation else ":impersonateQuery"),
                    json={"operationName": operation, "variables": variables},
                    timeout=30,
                )
                break
            except SQL_CONNECT_DROPPED as exc:
                if send == sends:
                    raise
                LOGGER.warning("SQL Connect %s connection dropped (%s); sending again",
                               log_code(operation), type(exc).__name__)
                self.pause(send)
        if response.status_code in {401, 403}:
            raise PermissionError("SQL Connect access denied")
        if response.status_code != 200:
            raise OperationalBlock("sql_connect_unavailable_or_connector_not_published")
        body = deadline_call(response.json)
        if body.get("errors"):
            # Every GraphQL error becomes a Conflict (409); the code says which kind it was.
            LOGGER.warning("SQL Connect %s rejected: code=%s",
                           log_code(operation), graphql_error_code(body["errors"]))
            if mutation and send > 1:
                raise RepeatRefused(
                    "SQL Connect refused a repeat; the receipt says whether the first send committed"
                )
            raise Conflict(
                "SQL Connect transaction rejected; reload current revision and membership"
            )
        from ..research_harness.native_json import decode_native_json
        return decode_native_json(operation, body.get("data", {}))

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

    def current_research_binding(self, scope, specimen_id):
        """Read the owner-installed coherent native pointer/registration operation."""
        from ..research_harness.canonical_binding import (
            BindingUnavailable, CanonicalBindingSnapshot,
        )
        from pydantic import ValidationError

        variables = dict(self.variables(scope), specimenId=specimen_id)
        try:
            data = self.execute("GetCanonicalResearchBindingV1", variables)
        except PermissionError:
            raise
        except (OperationalBlock, Conflict) as error:
            raise BindingUnavailable("canonical_binding_unavailable") from error
        try:
            return CanonicalBindingSnapshot.from_native_response(data)
        except (ValidationError, TypeError, ValueError) as error:
            raise BindingUnavailable("canonical_binding_unavailable") from error

    def research_store(self, binding):
        """Bind the existing program journal without creating or initializing it."""
        from ..research_harness.discovery import ScopedCanonicalReadStore

        return ScopedCanonicalReadStore(binding, verified_actor=actor_uid.get())

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
                "collection_name": (m.get("collection") or {}).get("name"),
                "role": m["role"],
                "can_view_sensitive": m["canViewSensitive"],
            }
            for m in result.get("collectionMembers", [])
            if m["active"] and str(UUID(m["organizationId"])) in orgs
        ]

    def collection_hierarchy(self, organization_id, uid):
        """Organization navigation names; membership checks still authorize every action."""
        result = self.execute("ListCollectionHierarchy", {"organizationId": organization_id, "actorUid": uid})
        rows = result.get("collections")
        try:
            if not isinstance(rows, list) or len(rows) > 1000:
                raise ValueError
            nodes = {}
            for row in rows:
                ident = str(UUID(row['id']))
                if (ident in nodes or not isinstance(row['name'], str) or not row['name'].strip()
                        or row.get('kind') not in {None, 'museum', 'testing'}):
                    raise ValueError
                nodes[ident] = {'collection_id': ident, 'display_name': row['name'],
                                'parent_collection_id': str(UUID(row['parentId'])) if row.get('parentId') else None,
                                'kind': row.get('kind') or 'museum'}

            def path(node):
                names, seen = [], set()
                while node:
                    if node['collection_id'] in seen:
                        raise ValueError
                    seen.add(node['collection_id'])
                    names.append((node['display_name'].casefold(), node['collection_id']))
                    parent = node['parent_collection_id']
                    node = nodes[parent] if parent else None
                return tuple(reversed(names))

            return sorted(nodes.values(), key=path)
        except (ValueError, KeyError, TypeError, AttributeError):
            raise OperationalBlock('collection_hierarchy_invalid') from None

    def get(self, scope, specimen_id):
        # GetSpecimen takes `$id: UUID!`. Any other id names no specimen: it is
        # Missing (404), not a refused query read as a conflict (409).
        if not isinstance(specimen_id, str) or not SPECIMEN_UUID.fullmatch(specimen_id):
            raise Missing(specimen_id)
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
        specimen = self._snapshot(row)
        sensitive = data["specimen"].get("sensitive", True)
        if type(sensitive) is not bool or sensitive != specimen.asset.sensitive:
            raise Conflict("Specimen sensitivity metadata mismatch")
        return specimen

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
        *,
        hydrate_review=False,
    ):
        from .search import sql_item

        mapping = {
            "specimen_id": "specimenId",
            "display_reference": "displayReference",
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
        items = [sql_item(row, scope) for row in rows]
        if hydrate_review:
            self.review_graph_cache.hydrate(items, [row.get("activeGraph") for row in rows], self.graph_blobs)
        return items

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

    def latest_run_version(self, scope, ident, run_id, through_revision):
        if type(through_revision) is not int or through_revision < 1:
            raise ValueError("Invalid historical run bound")
        row = self.execute(
            "GetLatestRetainedRunSnapshot",
            dict(self.variables(scope),id=ident,runId=str(UUID(run_id)),
                 throughRevision=through_revision),
        ).get("retained")
        if not row:
            raise Missing(ident)
        result = self._snapshot(row)
        if (result.id != ident or result.scope != scope or result.run.id != run_id
            or not 1 <= result.version <= through_revision):
            raise Conflict("Historical run identity mismatch")
        return result

    def oldest_due(self, scope, cutoff, limit=1):
        """Due, non-sensitive work, oldest request first (LANE.md T2, G13)."""
        if not 1 <= limit <= 100:
            raise ValueError("Invalid page size")
        rows = self.execute(
            "ListDueWorkV2",
            dict(
                self.variables(scope),
                cutoff=cutoff,
                afterAt="1970-01-01T00:00:00Z",
                afterId="",
                limit=limit,
                includeSensitive=False,
            ),
        ).get("items", [])
        return [
            WorkItem(
                specimen_id=str(UUID(row["id"])),
                revision=row["revision"],
                state=row["state"],
                work_available_at=row["workAvailableAt"],
                created_at=row["createdAt"],
            )
            for row in rows
        ]

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
        # Memberships once per call. ListSpecimenPage is metadata-only (no snapshot
        # payload), so each row still needs get(); a payload-bearing specimen list
        # would be a data-release follow-up.
        results, after, cutoff = [], "", now()
        sensitive = self._can_view_sensitive(scope)
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

    def blocked_ids(self, scope):
        """Blocked, non-sensitive records with no disposition, by id
        (lane_worker.DrainWorker._recover_blocked). ListSpecimenPage's metadata
        rows only: no snapshot is read here. Yielded one page at a time, an
        empty page too, so the caller can stop between any two pages."""
        from datetime import datetime, timedelta

        # A second behind, so it is never later than the connector's clock.
        cutoff = (datetime.fromisoformat(now()) - timedelta(seconds=1)).isoformat()
        after = ""
        while True:
            rows = self.execute(
                "ListSpecimenPage",
                dict(
                    self.variables(scope),
                    cutoff=cutoff,
                    afterId=after,
                    limit=100,
                    includeSensitive=False,
                ),
            ).get("specimens", [])
            yield [
                str(UUID(row["id"]))
                for row in rows
                if row.get("state") == "processing_blocked"
                and not row.get("disposition")
                and not row.get("sensitive")
            ]
            if len(rows) < 100:
                return
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

    def _review_proofs(self, scope, specimen):
        """Read original proofs under the current scoped operator/reviewer authority."""
        if not specimen.audit_offset and not any(
            event.action.startswith("review_") for event in specimen.audit
        ):
            return [], None
        base = self.variables(scope)

        def snapshot(revision):
            row = self.execute(
                "GetSnapshot", dict(base, id=specimen.id, revision=revision)
            ).get("specimenSnapshot")
            if not row or row.get("revision") != revision:
                raise ValueError("review_decision_provenance_invalid")
            parsed = self._snapshot(row)  # Includes canonical/legacy digest and graph checks.
            return ReviewSnapshot(row["snapshot"], row["sha256"], parsed)

        def save_audits(previous, resulting, event, prior, target):
            response = self.execute(
                "GetReviewSaveProofV1",
                dict(
                    base, specimenId=specimen.id, decisionId=event["id"],
                    decisionActorUid=event["actor"], baseRevision=previous,
                    resultingRevision=resulting,
                ),
            )
            for name, expected in (("prior", prior), ("target", target)):
                row = response.get(name)
                if (
                    not row or row.get("sha256") != expected.sha256
                    or row.get("revision") != expected.specimen.version
                    or self._snapshot(row) != expected.specimen
                ):
                    raise ValueError("review_decision_provenance_invalid")
            return response

        reader = ReviewProofReader(specimen, snapshot, save_audits)
        proofs = reader.prove()
        by_id = {proof.event.id: proof for proof in proofs}

        def recheck_conflict(variables):
            proof = by_id.get(variables.get("id"))
            if proof is None:
                raise ValueError("review_decision_provenance_invalid")
            # Verify the attempted envelope against the same authoritative proof.
            verify_review_decision_row(proof, {
                **variables, "actorUid": variables.get("decisionActorUid"),
            }, required=True)
            # This fresh observation deliberately bypasses the pre-insert query's
            # cached result. It consumes another read slot and requires a row.
            response = reader._read(
                ("decision_after_pk_conflict", proof.event.id),
                lambda: self.execute("GetReviewSaveProofV1", dict(
                    base, specimenId=specimen.id, decisionId=proof.event.id,
                    decisionActorUid=proof.event.actor, baseRevision=proof.base_revision,
                    resultingRevision=proof.resulting_revision,
                )),
            )
            verify_review_decision_row(proof, response.get("decision"), required=True)

        return proofs, recheck_conflict

    def _receipted(self, principal, base, operation, key, request_digest):
        """The snapshot this request already committed, or None when it has not."""
        receipt = self.execute(
            "GetReceipt", dict(base, operation=operation, idempotencyKey=key)
        ).get("requestReceipt")
        if not receipt:
            return None
        if receipt["requestSha256"] != request_digest:
            raise Conflict("Idempotency key reused")
        row = self.execute(
            "GetSnapshot",
            dict(base, id=receipt["specimenId"], revision=receipt["revision"]),
        )["specimenSnapshot"]
        committed = self._snapshot(row)
        # A replayed save still catches up rows a lost pass did not write.
        self.write_projection(principal.scope, committed, principal.role in REVIEW_ROLES)
        self.write_costs(principal.scope, committed)
        return committed

    def _commit(self, principal, specimen, expected, key, request_digest):
        if principal.scope != specimen.scope or principal.user_id != actor_uid.get():
            raise PermissionError("Verified actor/scope mismatch")
        operation = "create" if not expected else "save:" + specimen.id
        base = self.variables(principal.scope)
        committed = self._receipted(principal, base, operation, key, request_digest)
        if committed is not None:
            return committed
        specimen = specimen.model_copy(deep=True)
        specimen.version = expected + 1
        previous = self.version(principal.scope, specimen.id, expected) if expected else None
        if previous and previous.asset.sensitive and not specimen.asset.sensitive:
            raise Conflict("Sensitive history cannot be downgraded")
        stamp_review_events(principal, specimen, previous, expected)
        if previous:
            specimen = compact_history(specimen, previous)
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
            state=run_status(specimen.run),
            sensitive=specimen.asset.sensitive,
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
        try:
            self.execute(
                "SaveSpecimenV3" if expected else "CreateSpecimenV3",
                variables,
                mutation=True,
            )
        except RepeatRefused:
            committed = self._receipted(principal, base, operation, key, request_digest)
            if committed is None:
                raise
            return committed
        self.write_projection(principal.scope, specimen, principal.role in REVIEW_ROLES)
        self.write_costs(principal.scope, specimen)
        return specimen

    def write_costs(self, scope, specimen) -> bool:
        """Record the active run's paid calls in the cost meter (COST_METER.md).

        Only rows this process has not sent as they now stand are sent. Never
        raises: the snapshot is the record, and the worker's sweep repairs any
        row this pass could not write. The warning names a code, never a value.
        """
        from .cost_ledger import CostRowInvalid, paid_call_rows

        try:
            rows = paid_call_rows(scope.organization_id, scope.collection_id, specimen.id, specimen.run)
            if rows:
                self.send_cost_rows(scope, rows[0]["specimen_id"], rows)
            return True
        except Exception as error:
            code = str(error) if isinstance(error, CostRowInvalid) else type(error).__name__
            LOGGER.warning("Cost rows not written: %s", log_code(code))
            return False

    def send_cost_rows(self, scope, specimen_id, rows) -> int:
        """Upsert one specimen's cost rows that differ from what this process sent.

        Raises when the connector refuses or cannot be reached; a row counts as
        sent only once its call is answered with every row upserted.
        """
        sent = self._costed.setdefault(specimen_id, {})
        self._costed.move_to_end(specimen_id)
        while len(self._costed) > COSTED_SPECIMENS:
            self._costed.popitem(last=False)
        pending = [(row, digest(row)) for row in rows]
        pending = [(row, key) for row, key in pending if sent.get(row["id"]) != key]
        for start in range(0, len(pending), COST_ROWS_PER_CALL):
            chunk = pending[start:start + COST_ROWS_PER_CALL]
            response = self.execute(
                "UpsertCostEntriesV1",
                dict(
                    self.variables(scope),
                    specimenId=specimen_id,
                    rowsJson=json.dumps([row for row, _ in chunk], separators=(",", ":"), allow_nan=False),
                ),
                mutation=True,
            )
            if response.get("upserted") != len(chunk):
                raise Conflict("cost_entries_refused")
            sent.update({row["id"]: key for row, key in chunk})
        return len(pending)

    def run_paid_calls_page(self, scope, after_id, since, limit):
        """One page of the cost sweep: each run's paid calls, from ListRunPaidCallsV1."""
        if not 1 <= limit <= 25:
            raise ValueError("Invalid page size")
        row = self.execute(
            "ListRunPaidCallsV1",
            dict(self.variables(scope), afterId=after_id, since=since, limit=limit),
        ).get("page")
        if not isinstance(row, dict) or not isinstance(row.get("page_json"), str):
            raise OperationalBlock("cost_sweep_page_unavailable")
        page = json.loads(row["page_json"])
        if not isinstance(page.get("items"), list) or type(page.get("specimens")) is not int:
            raise OperationalBlock("cost_sweep_page_unavailable")
        return page

    def cost_totals(self, organization_id, from_month, to_month):
        """The organization's collections and grouped cost sums (CostTotalsV1)."""
        uid = actor_uid.get()
        if not uid:
            raise PermissionError("Verified actor context required")
        data = self.execute(
            "CostTotalsV1",
            {"organizationId": organization_id, "actorUid": uid,
             "fromMonth": from_month, "toMonth": to_month},
        )
        row = data.get("totals")
        if not isinstance(row, dict) or not isinstance(row.get("totals_json"), str):
            raise OperationalBlock("cost_meter_unavailable")
        totals = json.loads(row["totals_json"])
        if totals.get("admitted") is not True:
            raise PermissionError("Cost totals need an administrator")
        if not isinstance(totals.get("groups"), list) or not isinstance(data.get("collections"), list):
            raise OperationalBlock("cost_meter_unavailable")
        return {"collections": data["collections"], "groups": totals["groups"]}

    def cost_allocation_inputs(self, scope, day_start, day_end, month_start, gap_seconds) -> list:
        """Every collection's measures for one billing day (CostAllocationInputsV1).

        Ids and numbers only, for the whole deployment: the caller must be an
        active operator, reviewer, manager or admin of ``scope``.
        """
        from datetime import timezone

        def stamp(moment):
            return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        row = self.execute(
            "CostAllocationInputsV1",
            dict(self.variables(scope), dayStart=stamp(day_start), dayEnd=stamp(day_end),
                 monthStart=stamp(month_start), gapSeconds=gap_seconds),
        ).get("inputs")
        if not isinstance(row, dict) or not isinstance(row.get("inputs_json"), str):
            raise OperationalBlock("cost_allocation_inputs_unavailable")
        inputs = json.loads(row["inputs_json"])
        if inputs.get("admitted") is not True:
            raise PermissionError("Cost allocation inputs need an active operator")
        if not isinstance(inputs.get("collections"), list):
            raise OperationalBlock("cost_allocation_inputs_unavailable")
        return inputs["collections"]

    def send_cost_allocations(self, scope, rows) -> int:
        """Upsert one collection's allocation rows; raises unless every row is written."""
        written = 0
        for start in range(0, len(rows), COST_ROWS_PER_CALL):
            chunk = rows[start:start + COST_ROWS_PER_CALL]
            response = self.execute(
                "UpsertCostAllocationsV1",
                dict(self.variables(scope),
                     rowsJson=json.dumps(chunk, separators=(",", ":"), allow_nan=False)),
                mutation=True,
            )
            if response.get("upserted") != len(chunk):
                raise Conflict("cost_allocations_refused")
            written += len(chunk)
        return written

    def cost_allocation_status(self, organization_id) -> dict:
        """The latest allocation row's time for the organization (CostAllocationStatusV1)."""
        uid = actor_uid.get()
        if not uid:
            raise PermissionError("Verified actor context required")
        row = self.execute(
            "CostAllocationStatusV1", {"organizationId": organization_id, "actorUid": uid}
        ).get("status")
        if not isinstance(row, dict) or not isinstance(row.get("status_json"), str):
            raise OperationalBlock("cost_meter_unavailable")
        status = json.loads(row["status_json"])
        if status.get("admitted") is not True:
            raise PermissionError("Cost allocation status needs an administrator")
        latest = status.get("latest_occurred_at")
        if latest is not None and not isinstance(latest, str):
            raise OperationalBlock("cost_meter_unavailable")
        return {"latest_occurred_at": latest}

    def write_projection(self, scope, specimen, reviewer=False) -> ProjectionResult:
        """Write the normalized rows this revision supports (DATA_CONTRACT.md 11).

        Never raises: the snapshot is already committed, and the next save resumes
        wherever this pass stopped. The result says whether every row is written, or
        the step the pass stopped at, so the lane can re-project a run's final save.
        """
        try:
            base = self.variables(scope)
            needs_human_proofs = reviewer or bool(specimen.run.dependencies.get("human_review_field_locks")) or bool(specimen.run.dependencies.get("preserved_human_fields"))
            review_proofs, review_conflict_check = self._review_proofs(scope, specimen) if needs_human_proofs else (None, None)
            written = self._projected.setdefault(specimen.id, set())
            self._projected.move_to_end(specimen.id)
            while len(self._projected) > PROJECTED_SPECIMENS:
                self._projected.popitem(last=False)
            pending = [
                w
                for w in writes(
                    specimen, self.locate, self._sized, base["actorUid"], reviewer,
                    review_proofs=review_proofs,
                )
                if w.operation == "AppendReviewDecisionV2" or w.key not in written
            ]
            if specimen.run.dependencies.get("preserved_human_fields"):
                from .human_field_carry import verify, adapt_projection
                verified = verify(self, specimen, self.graph_blobs, proofs=review_proofs)
                # Adapt before filtering the complete composed record/candidate
                # graph; every replay derives the same fresh-run row identities.
                rows = adapt_projection(writes(specimen, self.locate, self._sized,
                    base["actorUid"], reviewer, review_proofs=review_proofs), specimen, verified)
                pending = [w for w in rows if w.operation == "AppendReviewDecisionV2" or w.key not in written]
        except Exception as error:
            LOGGER.warning(
                "Projection for specimen %s not computed: %s", specimen.id, error
            )
            return ProjectionResult(False, "not_computed")
        for write in pending:
            try:
                variables = {**base, **write.variables}
                if write.operation == "AppendReviewDecisionV2":
                    self._insert(write.operation, variables, review_conflict_check=review_conflict_check)
                else:
                    self._insert(write.operation, variables)
            except Exception as error:
                # Later rows may reference this one, so the pass stops here.
                LOGGER.warning(
                    "Projection for specimen %s run %s stopped at %s: %s",
                    specimen.id,
                    specimen.run.id,
                    write.operation,
                    error,
                )
                return ProjectionResult(False, write.operation)
            if write.operation != "AppendReviewDecisionV2":
                written.add(write.key)
        return ProjectionResult(True)

    @guarded
    def _insert(self, operation, variables, *, review_conflict_check=None):
        response = deadline_call(
            self.session.post,
            self.url + ":impersonateMutation",
            json={"operationName": operation, "variables": variables},
            timeout=30,
        )
        if response.status_code in {401, 403}:
            raise PermissionError("SQL Connect access denied")
        if response.status_code != 200:
            raise OperationalBlock("sql_connect_unavailable_or_connector_not_published")
        errors = deadline_call(response.json).get("errors") or []
        if not errors:
            return
        first = errors[0]
        message = str(first.get("message", "rejected"))
        # A replayed row hits its primary key; any other conflict is a defect.
        if (first.get("extensions") or {}).get("code") == "ALREADY_EXISTS" and (
            "_pkey" in message
        ):
            if operation == "AppendReviewDecisionV2":
                if review_conflict_check is None:
                    raise ValueError("review_decision_provenance_invalid")
                review_conflict_check(variables)
            return
        raise ProjectionRejected(message[:200])

    def locate(self, ref):
        """Where a blob ref's bytes live: Cloud Storage objects, or local files."""
        sha, _, generation = ref.partition(":")
        if self.graph_blobs is None:
            raise LookupError("No blob store to locate projection assets")
        bucket = getattr(self.graph_blobs, "bucket", None)
        if bucket is not None:
            return Blob(bucket.name, "application/sha256/" + sha, generation)
        return Blob("local", sha, generation or "0")

    def blob_size(self, ref):
        blob = self.locate(ref)
        bucket = getattr(self.graph_blobs, "bucket", None)
        if bucket is not None:
            return bucket.get_blob(blob.object_name, generation=int(blob.generation)).size
        return (self.graph_blobs.root / blob.object_name).stat().st_size

    def _sized(self, ref):
        # Content-addressed blobs never change size; read each once per process.
        if ref not in self._sizes:
            if len(self._sizes) >= 4096:
                self._sizes.clear()
            self._sizes[ref] = self.blob_size(ref)
        return self._sizes[ref]

    def _can_view_sensitive(self, scope):
        return any(
            m["organization_id"] == scope.organization_id
            and m["collection_id"] == scope.collection_id
            and m["can_view_sensitive"]
            for m in self.memberships(actor_uid.get())
        )

    @staticmethod
    def _document_payload(row):
        if (
            type(row.get("sensitive")) is not bool
            or type(row["payload"].get("sensitive", True)) is not bool
            or row["sensitive"] != row["payload"].get("sensitive", True)
        ):
            raise Conflict("Document sensitivity metadata mismatch")
        return row["payload"]

    def document(self, scope, kind, ident):
        row = self.execute(
            "GetDocumentV2", dict(self.variables(scope), kind=kind, id=ident)
        ).get("auxiliaryDocument")
        if not row:
            raise Missing(ident)
        return self._document_payload(row)

    def _document_payloads(self, scope, kind, include_sensitive=None):
        """Page ListDocumentsV2 payloads (limit/offset). Memberships resolved once.

        The query is newest first and the offset is not insert-stable: a document
        created between two pages shifts every row down one place, so the next
        page opens with the last row of the previous one. Rows are de-duplicated
        by id and returned by id ascending, the order the SQLite helper and
        ``ListDocumentPageV2`` give, so both backends list a kind the same way.
        """
        if include_sensitive is None:
            include_sensitive = self._can_view_sensitive(scope)
        rows_by_id, offset = {}, 0
        while True:
            rows = self.execute(
                "ListDocumentsV2",
                dict(
                    self.variables(scope),
                    kind=kind,
                    limit=100,
                    offset=offset,
                    includeSensitive=include_sensitive,
                ),
            ).get("auxiliaryDocuments", [])
            for row in rows:
                rows_by_id.setdefault(str(UUID(row["id"])), row)
            if len(rows) < 100:
                return [
                    self._document_payload(rows_by_id[ident])
                    for ident in sorted(rows_by_id)
                ]
            offset += len(rows)

    def documents(self, scope, kind):
        return self._document_payloads(scope, kind)

    def uploads_for_batch(self, scope, batch_id, include_sensitive=False):
        # ListDocumentsV2 has no batch_id filter yet; a filtered GQL query is a
        # data-release follow-up. Page payloads and filter in process.
        return [
            payload
            for payload in self._document_payloads(
                scope, "upload", include_sensitive=include_sensitive
            )
            if payload.get("batch_id") == batch_id
        ]

    def upload_by_idempotency(self, scope, batch_id, idempotency_key):
        # Early-stop on match. batch_id/idempotency GQL filters are a
        # data-release follow-up.
        include_sensitive = self._can_view_sensitive(scope)
        offset = 0
        while True:
            rows = self.execute(
                "ListDocumentsV2",
                dict(
                    self.variables(scope),
                    kind="upload",
                    limit=100,
                    offset=offset,
                    includeSensitive=include_sensitive,
                ),
            ).get("auxiliaryDocuments", [])
            for row in rows:
                payload = self._document_payload(row)
                if (
                    payload.get("batch_id") == batch_id
                    and payload.get("idempotency_key") == idempotency_key
                ):
                    return payload
            if len(rows) < 100:
                return None
            offset += len(rows)

    def put_document(self, scope, kind, ident, payload, expected):
        payload = dict(payload, revision=expected + 1)
        sensitive = payload.get("sensitive", True)
        if type(sensitive) is not bool:
            raise ValueError("Document sensitivity must be boolean")
        if (
            expected
            and not sensitive
            and self.document(scope, kind, ident).get("sensitive", True)
        ):
            raise Conflict("Sensitive document cannot be downgraded")
        variables = dict(
            self.variables(scope),
            kind=kind,
            id=ident,
            payload=payload,
            operation=f"{kind}:{ident}",
            idempotencyKey=f"revision:{expected}",
            requestSha256=digest(payload),
            sensitive=sensitive,
        )
        if expected:
            variables["expectedRevision"] = expected
        try:
            self.execute(
                "SaveDocumentV2" if expected else "CreateDocumentV2", variables, mutation=True
            )
        except RepeatRefused:
            receipt = self.execute(
                "GetDocumentReceiptV2",
                dict(
                    self.variables(scope),
                    operation=variables["operation"],
                    idempotencyKey=variables["idempotencyKey"],
                ),
            ).get("auxiliaryReceipt")
            # The receipt's key names this document and revision; its digest, this payload.
            if not receipt or (receipt.get("revision"), receipt.get("requestSha256")) != (
                expected + 1, variables["requestSha256"]
            ):
                raise
        return payload

    def active_intake_jobs(self, scope):
        after = ''
        while True:
            rows = self.execute('ListActiveIntakeJobs', dict(self.variables(scope), afterId=after, limit=100)).get('items', [])
            for row in rows:
                value = row['payload']
                if value.get('state') != 'waiting' or value.get('sensitive') is not False or value['id'] != str(UUID(row['id'])):
                    raise Conflict('Intake job inventory mismatch')
                yield value
            if len(rows) < 100:
                return
            after = str(UUID(rows[-1]['id']))

    def private_document_page(self, scope, kind, owner, after, limit, include_sensitive=False):
        from .intake_models import PRIVATE_KINDS
        if kind not in PRIVATE_KINDS or owner != actor_uid.get() or not 1 <= limit <= 101:
            raise PermissionError('Private intake inventory unavailable')
        rows = self.execute('ListPrivateIntakePage', dict(self.variables(scope),
            kind=kind, afterId=after, limit=limit, includeSensitive=include_sensitive)).get('items', [])
        ids = [str(UUID(row['id'])) for row in rows]
        documents = {}
        for start in range(0, len(ids), 100):
            documents.update({row['id']: row for row in self.private_documents(scope, kind, owner, ids[start:start + 100])})
        return [documents[id] for id in ids if id in documents]

    def commit_intake_submission(self, scope, draft, job):
        if draft['owner_id'] != actor_uid.get() or job['owner_id'] != actor_uid.get():
            raise PermissionError('Private submission unavailable')
        expected = draft['revision']
        payload = dict(draft, revision=expected + 1)
        self.execute('CommitIntakeSubmission', dict(self.variables(scope), id=draft['id'],
            expectedRevision=expected, sensitive=draft['sensitive'], payload=payload,
            jobId=job['id'], jobPayload=job), mutation=True)
        return payload

    def private_documents(self, scope, kind, owner, ids):
        from .intake_models import PRIVATE_KINDS
        if kind not in PRIVATE_KINDS or owner != actor_uid.get() or len(ids) > 100:
            raise PermissionError('Private intake selection unavailable')
        if not ids:
            return []
        sensitive = any(m['organization_id'] == scope.organization_id
            and m['collection_id'] == scope.collection_id and m['can_view_sensitive']
            for m in self.memberships(owner))
        rows = self.execute('GetPrivateIntakeItems', dict(self.variables(scope),
            kind=kind, ids=ids, includeSensitive=sensitive)).get('items', [])
        for row in rows:
            if type(row.get('sensitive')) is not bool or row['payload'].get('sensitive', True) != row['sensitive']:
                raise Conflict('Document sensitivity metadata mismatch')
        return [row['payload'] for row in rows]

    # Optional monthly budget caps per organization and collection (cost meter,
    # docs/execution/golive/TENANT_BUDGETS.md; dataconnect/connector/tenant_budget.gql).
    def tenant_caps(self, scope):
        """The organization's caps and its collection tree, read as the actor in
        ``scope`` (any active member of that collection). Ids are normalized."""
        from .tenant_budget import MAX_ROWS, cap_key, cap_micros

        data = self.execute("TenantBudgetCapsV1", self.variables(scope))
        rows, collections = data.get("tenantBudgetCaps"), data.get("collections")
        if (not isinstance(rows, list) or not isinstance(collections, list)
                or len(rows) > MAX_ROWS or len(collections) > MAX_ROWS):
            raise Conflict("Tenant budget caps unreadable")
        return {
            "caps": [{"collection_key": cap_key(row["collectionKey"]),
                "monthly_cap_micros": cap_micros(row.get("monthlyCapMicros")),
                "updated_by": row.get("updatedBy"), "updated_at": row.get("updatedAt")}
                for row in rows],
            "collections": [{"id": str(UUID(row["id"])),
                "parent_id": None if row.get("parentId") is None else str(UUID(row["parentId"]))}
                for row in collections],
        }

    def set_tenant_cap(self, scope, collection_key, micros):
        """Set or clear (None) one cap, as an active admin of ``scope``'s collection."""
        from .tenant_budget import cap_key, cap_micros

        self.execute("SetTenantBudgetCapV1", dict(self.variables(scope),
            collectionKey=cap_key(collection_key), monthlyCapMicros=cap_micros(micros)), mutation=True)


class GcsBlobs:
    def __init__(self, bucket="specimen-digitization.firebasestorage.app"):
        self.bucket = storage.Client(project="specimen-digitization").bucket(bucket)

    @guarded
    def put(self, data):
        checksum = hashlib.sha256(data).hexdigest()
        blob = self.bucket.blob("application/sha256/" + checksum)
        from google.api_core.exceptions import PreconditionFailed

        try:
            deadline_call(
                blob.upload_from_string, data, if_generation_match=0, checksum="crc32c"
            )
        except PreconditionFailed:
            if deadline_call(blob.download_as_bytes) != data:
                raise Conflict("Immutable object mismatch")
        deadline_call(blob.reload)
        return f"{checksum}:{blob.generation}"

    def get(self, ref):
        from .blob_limits import ORIGINAL_BYTES

        return self.get_bounded(ref, ORIGINAL_BYTES)

    def get_bounded_until(self, ref, max_bytes, deadline):
        """Deadline-aware queue read, separate from supervised worker I/O.

        read1 performs one underlying read, rather than waiting to fill a large
        buffer across an arbitrarily slow stream. The socket inactivity timeout
        is at most one second; the absolute deadline is checked between reads.
        All responses are closed before this call returns or raises.
        """
        from urllib.parse import quote
        from .blob_limits import read_limited, verify_digest, BlobTooLarge

        if not isinstance(ref, str) or not re.fullmatch(r"[0-9a-f]{64}:[1-9][0-9]*", ref):
            raise Missing("Invalid object reference")
        checksum, generation = ref.split(":")

        def remaining():
            left = deadline - time.monotonic()
            if left <= 0:
                raise TimeoutError("Graph count read expired")
            return left

        left = remaining()
        timeout = min(1.0, left)
        url = ("https://storage.googleapis.com/storage/v1/b/"
            + quote(self.bucket.name, safe="") + "/o/"
            + quote("application/sha256/" + checksum, safe=""))
        response = self.bucket.client._http.get(
            url, params={"alt": "media", "generation": generation}, stream=True,
            headers={"Accept-Encoding": "identity"}, allow_redirects=False,
            timeout=(timeout, timeout), max_allowed_time=left,
        )
        with response:
            remaining()
            if response.status_code == 404:
                raise Missing("Object generation not found")
            if response.status_code != 200:
                raise OperationalBlock("object_storage_unavailable")
            declared = response.headers.get("Content-Length")
            if declared is not None:
                declared = int(declared)
                if declared < 0:
                    raise ValueError("Invalid object length")
                if declared > max_bytes:
                    raise BlobTooLarge("Evidence exceeds the configured byte limit")

            def read(count):
                remaining()
                chunk = response.raw.read1(count, decode_content=False)
                remaining()
                return chunk

            data = read_limited(read, max_bytes)
        remaining()
        return verify_digest(data, checksum)

    @guarded
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
        response = deadline_call(
            self.bucket.client._http.get,
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
                lambda count: deadline_call(response.raw.read, count, decode_content=False),
                max_bytes
            )
        return verify_digest(data, checksum)


class ProductionAdapters:
    def __init__(self, blobs, *, model_effect=None, sam3_expected=None):
        self.sam3_expected = sam3_expected or {}
        self.model_effect = model_effect
        self.blobs = blobs
        self.taxonomy = GbifTaxonomy(blobs)
        from .classifier_runtime import configured_classifier

        self.classifier = configured_classifier(blobs)
        from .authority_registry import AuthorityRegistry
        from .parties import PartiesAdapter

        registry = AuthorityRegistry(version="unconfigured")
        # No GADM geography source: GADM is not used (PLAN 4.8).
        self.authority_tools = {"parties": PartiesAdapter(registry, blobs)}
        self.authority_cost_reservations = {}

    def pin_dependencies(self, run):
        inputs = CollectionPromptInputs(
            collection_profile_id=run.profile.id,
            collection_name="Insects",
            schema_version=run.profile.schema_version,
        )
        # The units path's first-pass prompt is pinned on a run that takes that path and only
        # there, so an old-path run pins what it pinned before the path existed.
        units = getattr(run, "first_pass_path", "old") == "units"
        prompts = {
            name.value: resolve_prompt(name, inputs).model_dump(mode="json")
            for name in PromptName
            if units or name is not PromptName.FIRST_PASS_UNITS
        }
        # A reader is pinned from the reader routes only (the initial pair and
        # the NVIDIA option's); a stage route named as a reader raises.
        routes = {
            route: {
                "model_id": READER_HUGGINGFACE_ROUTES[route].model_id,
                "provider": READER_HUGGINGFACE_ROUTES[route].provider,
            }
            for route in run.profile.routes
        }
        # A first-pass route is pinned only in its role, with image input; any
        # other stays unpinned, so its step blocks (HARNESS.md section 5).
        first_pass = HUGGINGFACE_ROUTES.get(run.profile.first_pass_route)
        if first_pass is not None and first_pass.serves_with_images(
            "transcription_first_pass"
        ):
            routes[first_pass.route_id] = {
                "model_id": first_pass.model_id,
                "provider": first_pass.provider,
            }
        return {
            "prompts": prompts,
            "routes": routes,
            "adapter_version": "production-v2",
            "sam3_expected_sha256": digest(getattr(self, "sam3_expected", {})),
            "classifier": self.classifier.pin(run) if self.classifier else None,
            "segmentation": segmentation_pins(),
            "policy": run.profile.execution.model_dump(mode="json"),
        }

    def segment(self, specimen):
        if os.getenv("SPECIMEN_APPROVED_INFERENCE") != "true":
            raise OperationalBlock(
                "provider_data_policy_and_spending_approval_required"
            )
        # A deployment-specific SAM3 endpoint must implement the reviewed adapter.
        # No rectangle substitution, no hidden Hub download or paid execution.
        endpoint = os.getenv("SPECIMEN_SAM3_ENDPOINT")
        if specimen.run.dependencies.get("segmentation") != segmentation_pins():
            raise OperationalBlock(
                "segmentation_configuration_changed_requires_new_run"
            )
        if not endpoint:
            raise OperationalBlock(
                "sam3_serving_contract_not_configured_use_reviewed_regions"
            )
        lab = (
            os.getenv("SPECIMEN_SAM3_LAB") == "true"
            and os.getenv("APP_ENV") != "production"
        )
        lab_token = os.getenv("SPECIMEN_SAM3_LAB_TOKEN") if lab else None
        if lab and not lab_token:
            raise OperationalBlock("sam3_lab_token_required")
        return Sam3Service(
            endpoint,
            self.blobs,
            expected=self.sam3_expected.get(specimen.id),
            lab_token=lab_token,
        ).segment(specimen)

    def transcribe(self, specimen, region, route):
        from .model_runtime import invoke_model

        return invoke_model(self, specimen, "transcribe", region=region, route=route)

    def first_pass(self, specimen, region, readings):
        from .model_runtime import invoke_model

        return invoke_model(
            self, specimen, "first_pass", region=region, readings=readings
        )

    def first_pass_units(self, specimen, region, readings):
        """The units path's first pass in the model child: (decision, units). The run's path
        decides what the child returns (model_runtime.invoke_model)."""
        from .model_runtime import invoke_model

        if specimen.run.first_pass_path != "units":
            raise OperationalBlock("first_pass_contract_invalid")
        return invoke_model(
            self, specimen, "first_pass", region=region, readings=readings
        )

    def _transcribe_direct(self, specimen, region, route):
        if os.getenv("SPECIMEN_APPROVED_INFERENCE") != "true":
            raise OperationalBlock(
                "provider_data_policy_and_spending_approval_required"
            )
        reader_timeout = specimen.run.profile.execution.effect_timeout_for_step(
            "transcribe:" + region.id + ":" + route
        )
        gateway = HuggingFaceModelGateway(timeout_seconds=reader_timeout / 2)
        selected = gateway.route(route)
        if not selected.serves_with_images("handwriting_transcriber"):
            # Only an image reader's route reads a crop (HARNESS.md section 5).
            raise OperationalBlock("pinned_model_route_unavailable")
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
        started = time.monotonic()
        try:
            result = run_agent_bounded(
                agent,
                [
                    "Transcribe only the supplied source image.",
                    BinaryContent(data=image, media_type="image/png"),
                ],
                timeout_seconds=reader_timeout,
                usage_limits=UsageLimits(request_limit=2, total_tokens_limit=16000),
            )
        except UsageLimitExceeded as exc:
            # Stopped by its token limits or cut off at its output cap: a failed
            # reading with a known outcome, not an unknown one (#153).
            raise ReadingStopped("model_usage_limit", stopped_usage(exc)) from exc
        latency_seconds = time.monotonic() - started
        # Preserve every provider response (including retries), excluding image-bearing requests.
        responses = [m for m in result.all_messages() if m.kind == "response"]
        raw = ModelMessagesTypeAdapter.dump_json(responses)
        from .reading_declarations import model_evidence

        raw_ref = self.blobs.put(raw)
        raw_sha256 = hashlib.sha256(raw).hexdigest()
        prompt_version = hashlib.sha256(prompt.text.encode()).hexdigest()
        last_response = responses[-1] if responses else None
        return Observation(
            latency_seconds=latency_seconds,
            latency_basis="validated_agent_call_wall_seconds",
            finish_state=getattr(last_response, "finish_reason", None),
            completion_state="validated_output",
            parameters=agent.model_settings,
            provider_model_id=getattr(last_response, "model_name", None),
            input_asset_id=specimen.asset.id,
            input_crop_ref=self.blobs.put(image),
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
        from .model_runtime import invoke_model

        return invoke_model(self, specimen, "extract")

    def _extract_direct(self, specimen):
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
        return extract_with_agent(gateway, self.blobs, specimen)

    def lookup(self, name):
        return self.taxonomy.lookup(name)


def cross_check_override(*, lab):
    """The lab may name another cross-check concept, for calibration only."""
    return os.getenv("SPECIMEN_SAM3_LAB_CROSS_CHECK_CONCEPT") or None if lab else None


def segmentation_pins():
    """The SAM 3 service a run is pinned to, and the checkpoint it must serve."""
    pins = {
        "endpoint": os.getenv("SPECIMEN_SAM3_ENDPOINT"),
        "revision": os.getenv("SPECIMEN_SAM3_REVISION"),
    }
    checkpoint = os.getenv("SPECIMEN_SAM3_CHECKPOINT_SHA256")
    return dict(pins, checkpoint_sha256=checkpoint) if checkpoint else pins


# The SAM 3 service ends a request at 240 s, and answers busy while it serves
# another or a run's claim is younger than that (sam3_server.serve_runs,
# RunSegmenter). 250 s after a timeout or a busy answer, a claim taken before
# it has its response stored or can be taken over. The service sends no
# Retry-After; the drain waits under its 300 s fence lease (lane_worker).
SAM3_RETRY_SECONDS = 250


class Sam3Service:
    """Pinned remote SAM3 activity contract. Service must return original pixel regions.

    This adapter is executable once a separately approved GPU service exists; no
    service is provisioned by the application or substituted by a fixture.
    """

    def __init__(
        self, endpoint: str, blobs, effect=None, *, expected=None, lab_token=None
    ):
        from urllib.parse import urlparse

        parsed = urlparse(endpoint)
        if lab_token is not None:
            # The lab (LANE.md T3): the service on host loopback, never elsewhere.
            approved = (
                parsed.scheme == "http"
                and parsed.hostname == "127.0.0.1"
                and parsed.port is not None
                and parsed.path in {"", "/"}
            )
        else:
            approved = (
                parsed.scheme == "https"
                and bool(parsed.hostname)
                and parsed.hostname.endswith(".run.app")
            )
        if not approved or parsed.username or parsed.query or parsed.fragment:
            raise ValueError(
                "SAM3 endpoint must be an approved HTTPS Cloud Run service"
            )
        self.endpoint = endpoint.rstrip("/")
        self.blobs = blobs
        self.expected = expected
        self.lab_token = lab_token
        from .sam3_effect import sam3_request, sam3_run_request

        self.effect = effect or (sam3_request if expected else sam3_run_request)

    def segment(self, specimen):
        from .collection_profiles import SegmentationSettings
        from .profile_runtime import pinned_risk_resolution

        if pinned_risk_resolution(specimen.run).status != "resolved":
            raise OperationalBlock("segmentation_profile_rules_unresolved")
        try:
            settings = SegmentationSettings.model_validate(
                specimen.run.profile_rules["segmentation_settings"]
            )
        except (KeyError, ValueError) as exc:
            raise OperationalBlock("segmentation_settings_unresolved") from exc
        if not self.expected:
            return self.segment_per_run(specimen)
        return self._segment_with_settings(specimen, settings)

    def segment_per_run(self, specimen):
        """One claimed inference per run; failures retry safely (LANE.md T3)."""
        import base64
        from . import bounded_effect
        from .collection_profiles import SegmentationSettings
        from .domain import LookupStatus, Region
        from .reliability import AdapterFailure
        from .sam3_effect import canonical_sha256, instance_accounting
        from ..hub_models import SAM3_MODEL

        try:
            settings = SegmentationSettings.model_validate(
                specimen.run.profile_rules["segmentation_settings"]
            )
        except (KeyError, ValueError) as exc:
            raise OperationalBlock("segmentation_settings_unresolved") from exc
        if settings.model_revision != SAM3_MODEL.revision:
            raise OperationalBlock("segmentation_model_revision_unsupported")
        checkpoint = specimen.run.dependencies.get("segmentation", {}).get(
            "checkpoint_sha256"
        )
        if not checkpoint:
            raise OperationalBlock("sam3_checkpoint_pin_required")
        parameters = settings.parameters.model_dump()
        override = cross_check_override(lab=self.lab_token is not None)
        if override:
            parameters["cross_check_concept"] = override
        request = {
            "run_id": specimen.run.id,
            "specimen_id": specimen.id,
            "organization_id": specimen.scope.organization_id,
            "collection_id": specimen.scope.collection_id,
            "asset_id": specimen.asset.id,
            "blob_ref": specimen.asset.blob_ref,
            "sha256": specimen.asset.sha256,
            "width": specimen.asset.width,
            "height": specimen.asset.height,
            "model_id": settings.model_id,
            "model_revision": settings.model_revision,
            "prompt": settings.prompt,
            "parameters": parameters,
            "adapter_version": settings.adapter_version,
            "settings_version": settings.version,
        }
        timeout = specimen.run.profile.execution.effect_timeout_for_step("segment")
        result = bounded_effect.run_isolated(
            self.effect,
            {
                "endpoint": self.endpoint,
                "telemetry": model_trace_context(specimen.id, specimen.run.id, **tenant_ids(specimen)),
                "request": request,
                "pins": {
                    "checkpoint_sha256": checkpoint,
                    "lab": self.lab_token is not None,
                },
                "lab_token": self.lab_token,
                "timeout_seconds": timeout,
                "max_response_bytes": 1024 * 1024,
            },
            timeout,
            2 * 1024 * 1024,
        )
        # The service's per-run claim makes a repeat safe: it returns a finished
        # inference instead of running it again, so these failures retry (G6).
        if result.status == "deadline_exceeded":
            raise AdapterFailure(
                "sam3_timeout",
                LookupStatus.TIMEOUT,
                retry_after_seconds=SAM3_RETRY_SECONDS,
            )
        if result.status == "worker_failed":
            raise AdapterFailure("sam3_unavailable", LookupStatus.PROVIDER)
        if result.status != "completed":
            raise OperationalBlock("sam3_" + result.reason)
        envelope = json.loads(result.value)
        raw = base64.b64decode(envelope["body_base64"], validate=True)
        status = envelope["http_status"]
        if status != 200:
            try:
                detail = json.loads(raw).get("detail")
            except (ValueError, AttributeError):
                detail = None
            if status == 429 or (status == 409 and detail == "sam3_busy"):
                raise AdapterFailure(
                    "sam3_busy",
                    LookupStatus.RATE_LIMITED,
                    retry_after_seconds=SAM3_RETRY_SECONDS,
                )
            if status >= 500:
                raise AdapterFailure("sam3_unavailable", LookupStatus.PROVIDER)
            raise OperationalBlock(f"sam3_http_{status}")
        specimen.run.segmentation = {
            "blob_ref": self.blobs.put(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "model_id": settings.model_id,
            "model_revision": settings.model_revision,
            "checkpoint_sha256": checkpoint,
            "input_sha256": specimen.asset.sha256,
            "http_status": status,
            "validation": envelope["validation"],
            "settings": settings.model_dump(mode="json"),
            "request_sha256": canonical_sha256(request),
            "elapsed_seconds": result.elapsed_seconds,
            # The instance time SAM 3 reported the request used: what Cloud Run
            # bills for it (lane_costs.record_segmentation); None if it sent none.
            "instance": instance_accounting(envelope.get("instance")),
        }
        if envelope["validation"] != "valid":
            raise OperationalBlock("sam3_" + envelope["validation"])
        response = json.loads(raw)
        # The evidence the lab calibrates from and the coverage check reads.
        specimen.run.segmentation.update(
            parameters=response["parameters"],
            region_scores=[mask["score"] for mask in response["masks"]],
            label_detections=response["detections"]["label"],
            cross_check=response["cross_check"],
        )
        return [Region.model_validate(item) for item in response["regions"]]

    def _segment_with_settings(self, specimen, settings):
        # Private transport shared with the explicitly guarded evidence pilot.
        # Normal segment() above still requires a resolved institutional policy.
        import base64
        from .domain import Region
        from .bounded_effect import run_isolated
        from .sam3_effect import canonical_sha256, validate_expected_binding
        from ..hub_models import SAM3_MODEL

        if not self.expected:
            raise OperationalBlock("sam3_provenance_configuration_required")
        revision = settings.model_revision
        if revision != SAM3_MODEL.revision:
            raise OperationalBlock("segmentation_model_revision_unsupported")
        request = {
            "run_id": specimen.run.id,
            "specimen_id": specimen.id,
            "organization_id": specimen.scope.organization_id,
            "collection_id": specimen.scope.collection_id,
            "asset_id": specimen.asset.id,
            "blob_ref": specimen.asset.blob_ref,
            "sha256": specimen.asset.sha256,
            "width": specimen.asset.width,
            "height": specimen.asset.height,
            "model_id": settings.model_id,
            "model_revision": revision,
            "prompt": settings.prompt,
            "parameters": settings.parameters.model_dump(),
            "adapter_version": settings.adapter_version,
            "settings_version": settings.version,
        }
        if not validate_expected_binding(
            {"request": request, "expected": self.expected}
        ):
            raise OperationalBlock("sam3_provenance_configuration_invalid")
        result = run_isolated(
            self.effect,
            {
                "endpoint": self.endpoint,
                "telemetry": model_trace_context(specimen.id, specimen.run.id, **tenant_ids(specimen)),
                "request": request,
                "expected": self.expected,
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
            "settings": settings.model_dump(mode="json"),
            "request_sha256": canonical_sha256(request),
            "elapsed_seconds": result.elapsed_seconds,
        }
        if envelope["validation"] != "valid":
            raise OperationalBlock("sam3_" + envelope["validation"])
        payload = json.loads(raw)
        return [Region.model_validate(item) for item in payload["regions"]]
