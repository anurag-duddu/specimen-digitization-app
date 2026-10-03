"""Offline rig for the production research harness end-to-end test.

Everything is the production code except three stand-ins:
- FakeDataConnect replaces the Data Connect HTTP session under a real
  SqlConnectRepository. It keeps the connector's tables in memory and answers
  each operation the way the connector SQL in this branch does, with the owner
  approved removal of the import-proof row and the publication time window.
- scripted pydantic-ai FunctionModels replace the model gateway;
- recorded source responses (fixtures/production_e2e) replace source HTTP.
The research state document is a real SqliteStateBackend; the fake reads and
compare-and-swaps the same document, as the connector does with its table.
Label text is the public synthetic fixture (application.api.SYNTHETIC_VALUES).
"""
from __future__ import annotations

import hashlib
import io
import json
import traceback
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from PIL import Image
from pydantic_ai.messages import ModelRequest, ModelResponse, RetryPromptPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage

from specimen_digitization.application.api import SYNTHETIC_VALUES
from specimen_digitization.application.collection_profiles import published_registry
from specimen_digitization.application.domain import (
    Asset, FieldValue, LookupStatus, Observation, Principal, Profile, Region, Run, Scope, Specimen,
    ValueState,
)
from specimen_digitization.application.profile_runtime import (
    bind_profile_rules, published_risk_registry,
)
from specimen_digitization.application.region_pixels import region_png
from specimen_digitization.application.storage import LocalBlobs, digest as canonical_digest
from specimen_digitization.research_harness.agents import SpecialistOutput
from specimen_digitization.research_harness.contracts import (
    EventKind, FieldKey, FieldResolution, SourceResult, SpecialistRole, WorkState,
)
from specimen_digitization.research_harness.evidence import (
    EvidenceError, catalog_literal, dts_policy_resolution, elevation_resolutions,
    missing_irn_resolution, settle_elevation, temporal_resolutions, validate_resolution,
)
from specimen_digitization.research_harness.persistence import DurabilityScope, canonical
from specimen_digitization.research_harness.sources import FixtureSourceTransport

ORG = "00000000-0000-4000-8000-000000000001"
COLLECTION = "00000000-0000-4000-8000-000000000002"
WORKER = "offline-e2e-worker"
OPERATOR_ROLES = ("operator", "reviewer", "manager", "admin")
TERMINAL_WORK = ("resolved", "waiting_human", "nonblocking_exception")
# The public synthetic label (application.api.SYNTHETIC_VALUES) with a catalog
# number of the catalog parser's 5 to 9 digits and an elevation with its
# written unit, so those fields can settle too.
LABEL_VALUES = {**SYNTHETIC_VALUES, "fmnh_ins_number": "FMNH-INS 0010001",
    "elevation_from_m": "180 to 181 m"}
LABEL_TEXT = "\n".join(f"{key}: {value}" for key, value in LABEL_VALUES.items())

# Output columns the connector SQL selects for each table, beyond
# organizationId, collectionId and createdAt.
TABLE_KEYS = {
    "source_asset": ("id", "specimenId", "kind", "parentAssetId", "bucket", "objectName", "generation",
        "sha256", "mimeType", "byteSize", "width", "height", "acquisitionMethod", "uploaderUid"),
    "profile_version": ("id", "profileKey", "version", "configObject", "configSha256", "approvedBy"),
    "pipeline_run": ("id", "specimenId", "profileVersionId", "supersedesRunId", "pinnedVersions",
        "inputSha256", "traceId"),
    "label_region": ("id", "runId", "domainRegionId", "sourceAssetId", "cropAssetId", "geometry", "ordinal",
        "regionType", "segmentationVersion", "supersedesRegionId"),
    "model_observation": ("id", "runId", "regionId", "rawAssetId", "stepKey", "provider", "modelVersion",
        "promptVersion", "inputSha256", "parameters", "literalText", "outcome", "independent", "routeId",
        "unreadableSpans"),
    "reading_comparison": ("id", "runId", "regionId", "leftObservationId", "rightObservationId", "algorithm",
        "ratio", "editDistance", "lengthBasis", "status", "reasons"),
    "transcription_version": ("id", "runId", "literalText", "spans", "alternatives", "unresolved", "regionId",
        "decisionKind", "selectedObservationId", "firstPassObservationId", "rationale"),
    "harness_input": ("id", "runId", "transcriptionVersionId", "observationId", "role", "handedText", "note"),
    "evidence_item": ("id", "runId", "source", "sourceVersion", "adapterVersion", "query", "outcome",
        "locator", "responseSha256", "capturedAt", "rawAssetId"),
    "tool_call": ("id", "runId", "callKey", "phase", "tool", "toolVersion", "source", "fieldKeys",
        "inputSource", "transcriptionVersionId", "observationId", "attempt", "arguments", "outcome", "result",
        "evidenceId", "startedAt", "completedAt"),
    "field_candidate": ("id", "runId", "fieldKey", "state", "literalValue", "parsedValue", "normalizedValue",
        "authorityId", "derivation", "inputSource", "sourceTranscriptionId", "sourceObservationId"),
    "candidate_evidence": ("id", "candidateId", "evidenceId", "relation"),
    "record_version": ("id", "runId", "predecessorId", "disposition", "policyVersion", "reasonCodes", "summary"),
    "resolved_field": ("id", "recordVersionId", "candidateId", "fieldKey", "state", "fieldGroup"),
    "validation_finding": ("id", "recordVersionId", "ruleId", "ruleVersion", "severity", "outcome", "fieldKey",
        "reasonCode", "evidenceIds"),
    "canonical_value_lineage_v2": ("id", "contractVersion", "specimenId", "runId", "candidateId",
        "recordVersionId", "predecessorId", "priorRevision", "resultRevision", "priorNativeSnapshotDigest",
        "priorGraphSnapshotDigest", "priorActiveGraphDigest", "fieldKey", "researchFieldKey", "layer",
        "resolutionDigest", "typedCheckpointDigest", "nativeCheckpointId", "nativeCheckpointDigest",
        "originalRequestDigest", "originalScope", "derivation", "derivationDigest", "scientificSourceDigest",
        "precision", "centuryRule", "readingSources", "literalGrounding", "selectedObservationId",
        "selectedTranscriptionId", "settledObservationIds", "evidenceIds", "evidenceRelations",
        "consumedDependencies"),
    "canonical_value_dependency_v2": ("id", "lineageId", "ordinal", "researchFieldKey", "canonicalFieldKey",
        "sourceRevision", "dependencyResolutionDigest", "sourceCheckpointId", "sourceCheckpointDigest",
        "sourceTypedCheckpointDigest", "sourceRunId", "sourceCandidateId", "sourceRecordVersionId",
        "sourceCandidateDigest", "sourceRecordDigest", "sourcePublicationLineageDigest",
        "sourceRecordFieldsDigest", "sourceRecordFields"),
    "canonical_value_evidence_v2": ("id", "lineageId", "evidenceId", "researchEvidenceId", "associationKind",
        "originalRelation"),
    "tool_input_lineage_v2": ("id", "contractVersion", "specimenId", "runId", "evidenceId", "nativeCheckpointId",
        "nativeCheckpointDigest", "originalRequestDigest", "originalScope", "originalRequest", "queryDigest",
        "query", "effectId", "attemptId", "receiptDigest", "receiptBindingDigest", "sourcePolicyDigest",
        "capturePolicyDigest", "sourceRegistryDigest", "canonicalMappingDigest", "sourceCaptureProof",
        "fragments", "fragmentDigests", "observationIds", "regionIds", "inputSources", "nativeInputs",
        "nativeTranscriptionProofs", "selectedObservationId", "legacyProducerDigest"),
    "captured_tool_execution_v2": ("id", "contractVersion", "lineageId", "runId", "evidenceId", "execution",
        "executionDigest", "effectId", "attemptId"),
}
APPEND_TABLES = {
    "AppendSourceAssetV2": "source_asset", "AppendProfileVersionV2": "profile_version",
    "AppendPipelineRunV2": "pipeline_run", "AppendLabelRegionV2": "label_region",
    "AppendModelObservationV2": "model_observation", "AppendReadingComparisonV1": "reading_comparison",
    "AppendTranscriptionVersionV2": "transcription_version", "AppendHarnessInputV1": "harness_input",
    "AppendEvidenceItemV2": "evidence_item", "AppendToolCallV1": "tool_call",
    "AppendFieldCandidateV2": "field_candidate", "AppendCandidateEvidenceV2": "candidate_evidence",
    "AppendRecordVersionV2": "record_version", "AppendResolvedFieldV2": "resolved_field",
    "AppendValidationFindingV2": "validation_finding",
}
# PublishCanonicalResearchV2 delta groups and the table each inserts into.
DELTA_TABLES = {
    "assets": "source_asset", "evidence": "evidence_item", "tool_calls": "tool_call",
    "candidates": "field_candidate", "links": "candidate_evidence", "findings": "validation_finding",
    "value_lineages": "canonical_value_lineage_v2", "value_dependencies": "canonical_value_dependency_v2",
    "value_evidence": "canonical_value_evidence_v2", "tool_input_lineage": "tool_input_lineage_v2",
    "captured_tool_executions": "captured_tool_execution_v2",
}


def wire(value):
    """A JSON round trip: what crosses the HTTP boundary."""
    return json.loads(json.dumps(value))


def iso_now():
    return datetime.now(timezone.utc).isoformat()


class ConnectorRefusal(Exception):
    """The connector refused the operation (a GraphQL error in the response)."""


class FakeResponse:
    def __init__(self, body, status_code=200):
        self.status_code, self._body = status_code, body

    def json(self):
        return self._body


class FakeDataConnect:
    """In-memory Data Connect connector for one organization and collection.

    It is the `session` of a real SqlConnectRepository: `post` receives the
    exact operation name and variables production sends.
    """

    def __init__(self, state_backend, *, members):
        self.backend = state_backend
        # uid -> list of collection memberships {"organization_id", "collection_id", "role", "can_view_sensitive"}
        self.members = members
        self.calls = []
        self.specimens = {}
        self.snapshots = {}
        self.request_receipts = {}
        self.audit_events = {}
        self.outbox_events = {}
        self.tables = {name: {} for name in TABLE_KEYS}
        self.duplicates = []
        self.bindings = {}
        self.intents = {}
        self.preparations = {}
        self.attempts = {}
        self.receipts = {}
        # Test hooks: an operation name -> callable(variables) raised before it runs.
        self.fail_before = {}

    # ---- transport -------------------------------------------------------
    def post(self, url, json=None, timeout=None):
        name, variables = json["operationName"], wire(json["variables"])
        self.calls.append(name)
        hook = self.fail_before.pop(name, None)
        if hook is not None:
            hook(variables)
        handler = getattr(self, "op_" + name, None)
        if handler is None and name in APPEND_TABLES:
            handler = lambda variables: self.append(APPEND_TABLES[name], variables)
        if handler is None:
            raise AssertionError(f"FakeDataConnect does not implement {name}")
        try:
            data = handler(variables)
        except ConnectorRefusal as refusal:
            return FakeResponse({"errors": [{"message": str(refusal), "extensions": {"code": "FAILED_PRECONDITION"}}]})
        except _AlreadyExists as exists:
            return FakeResponse({"errors": [{"message": f'duplicate key value violates unique constraint "{exists}_pkey"',
                "extensions": {"code": "ALREADY_EXISTS"}}]})
        return FakeResponse({"data": wire(data)})

    # ---- membership ------------------------------------------------------
    def membership(self, uid):
        rows = [row for row in self.members.get(uid, ())
            if row["organization_id"] == ORG and row["collection_id"] == COLLECTION]
        return rows[0] if rows else None

    def envelope(self, variables, specimen_id):
        member = self.membership(variables["actorUid"])
        specimen = self.specimens.get(specimen_id)
        return {"organizationMember": {"active": True} if member else None,
            "collectionMember": None if member is None else {"active": True, "role": member["role"],
                "canViewSensitive": member["can_view_sensitive"]},
            "specimen": None if specimen is None else {"sensitive": specimen["sensitive"]}}

    def require_member(self, variables, roles=OPERATOR_ROLES):
        member = self.membership(variables["actorUid"])
        if member is None or member["role"] not in roles:
            raise ConnectorRefusal("permission denied")
        return member

    def permitted(self, variables, specimen_id):
        member = self.membership(variables["actorUid"])
        specimen = self.specimens.get(specimen_id)
        return (member is not None and specimen is not None
            and (not specimen["sensitive"] or member["can_view_sensitive"]))

    # ---- research state (the research_harness_state row) ----------------
    def _state_scope(self, specimen_id):
        return DurabilityScope(ORG, COLLECTION, specimen_id, "connector-read", 1, WORKER, False)

    def state(self, specimen_id, program_key):
        document = self.backend.load(self._state_scope(specimen_id), program_key)
        return None if document is None else (document.revision, document.state)

    # ---- ordinary operations ---------------------------------------------
    def op_Memberships(self, variables):
        rows = self.members.get(variables["actorUid"], ())
        return {"organizationMembers": [{"organizationId": row["organization_id"], "active": True} for row in rows],
            "collectionMembers": [{"organizationId": row["organization_id"], "collectionId": row["collection_id"],
                "role": row["role"], "canViewSensitive": row["can_view_sensitive"], "active": True} for row in rows]}

    def op_GetReceipt(self, variables):
        self.require_member(variables, OPERATOR_ROLES + ("viewer",))
        row = self.request_receipts.get((variables["actorUid"], variables["operation"], variables["idempotencyKey"]))
        if row is None:
            return {"requestReceipt": None}
        return {"requestReceipt": {"specimenId": row["specimen_id"], "revision": row["revision"],
            "requestSha256": row["request_sha256"], "specimen": {"sensitive": self.specimens[row["specimen_id"]]["sensitive"]}}}

    def _receipt(self, variables, specimen_id, revision):
        key = (variables["actorUid"], variables["operation"], variables["idempotencyKey"])
        if key in self.request_receipts:
            raise _AlreadyExists("request_receipt")
        self.request_receipts[key] = {"specimen_id": specimen_id, "revision": revision,
            "request_sha256": variables["requestSha256"]}

    def _snapshot_row(self, specimen_id, revision, snapshot, sha256, contract):
        if (specimen_id, revision) in self.snapshots:
            raise _AlreadyExists("specimen_snapshot")
        self.snapshots[(specimen_id, revision)] = {"revision": revision, "snapshot": snapshot,
            "sha256": sha256, "contractVersion": contract}

    def op_CreateSpecimenV3(self, variables):
        self.require_member(variables)
        specimen_id = variables["id"]
        assert variables["snapshot"]["asset"]["sha256"] == variables["sourceChecksum"]
        if specimen_id in self.specimens:
            raise _AlreadyExists("specimen")
        self._receipt(variables, specimen_id, 1)
        self._snapshot_row(specimen_id, 1, variables["snapshot"], variables["snapshotSha256"],
            variables["contractVersion"])
        self.specimens[specimen_id] = {"revision": 1, "state": variables["state"],
            "sensitive": variables["sensitive"], "disposition": None, "active_run_id": None,
            "source_checksum": variables["sourceChecksum"], "work_available_at": variables.get("workAvailableAt")}
        return {"specimen_insert": {"id": specimen_id}}

    def op_SaveSpecimenV3(self, variables):
        self.require_member(variables)
        specimen_id = variables["id"]
        current = self.specimens.get(specimen_id)
        if (current is None or current["revision"] != variables["expectedRevision"]
                or current["source_checksum"] != variables["snapshot"]["asset"]["sha256"]):
            raise ConnectorRefusal("revision conflict or access denied")
        revision = variables["expectedRevision"] + 1
        self._receipt(variables, specimen_id, revision)
        self._snapshot_row(specimen_id, revision, variables["snapshot"], variables["snapshotSha256"],
            variables["contractVersion"])
        current.update(revision=revision, state=variables["state"], sensitive=variables["sensitive"],
            disposition=variables.get("disposition"), active_run_id=variables.get("activeRunId"),
            work_available_at=variables.get("workAvailableAt"))
        return {"specimen_updateMany": 1}

    def op_GetSpecimen(self, variables):
        self.require_member(variables, OPERATOR_ROLES + ("viewer",))
        current = self.specimens.get(variables["id"])
        if current is None:
            return {"specimen": None, "specimenSnapshots": []}
        return {"specimen": {"id": variables["id"], "revision": current["revision"], "state": current["state"],
                "disposition": current["disposition"], "activeRunId": current["active_run_id"],
                "sensitive": current["sensitive"]},
            "specimenSnapshots": [self.snapshots[(variables["id"], current["revision"])]]}

    def op_GetSnapshot(self, variables):
        self.require_member(variables, OPERATOR_ROLES + ("viewer",))
        current = self.specimens.get(variables["id"])
        return {"specimen": None if current is None else {"sensitive": current["sensitive"]},
            "specimenSnapshot": self.snapshots.get((variables["id"], variables["revision"]))}

    def append(self, table, variables):
        self.require_member(variables)
        row = {key: value for key, value in variables.items() if key != "actorUid"}
        row.setdefault("createdAt", iso_now())
        self.insert(table, row)
        return {"inserted": 1}

    def insert(self, table, row):
        existing = self.tables[table].get(row["id"])
        if existing is not None:
            if {k: v for k, v in existing.items() if k != "createdAt"} != {k: v for k, v in row.items() if k != "createdAt"}:
                self.duplicates.append((table, row["id"]))
            raise _AlreadyExists(table)
        self.tables[table][row["id"]] = row

    def op_RecordRunTraceV1(self, variables):
        run = self.tables["pipeline_run"].get(variables["id"])
        if run is not None and run.get("traceId") is None:
            run["traceId"] = variables["traceId"]
        return {"updated": 1}

    def rows(self, table, predicate=lambda row: True):
        result = []
        for row in sorted(self.tables[table].values(), key=lambda item: item["id"]):
            if row["organizationId"] == ORG and row["collectionId"] == COLLECTION and predicate(row):
                item = {"organizationId": row["organizationId"], "collectionId": row["collectionId"]}
                item.update({key: row.get(key) for key in TABLE_KEYS[table]})
                item["createdAt"] = row["createdAt"]
                if table == "source_asset" and item["byteSize"] is not None:
                    item["byteSize"] = str(item["byteSize"])
                result.append(item)
        return result

    def specimen_runs(self, specimen_id):
        return {row["id"] for row in self.tables["pipeline_run"].values() if row["specimenId"] == specimen_id}

    # ---- canonical binding ----------------------------------------------
    def active_binding(self, specimen_id):
        row = self.bindings.get(specimen_id)
        return row if row is not None and row["active"] else None

    def _human_locks(self, binding, job, snapshot):
        run = snapshot.get("run", {})
        approved = bool(run.get("human_approved")) or run.get("history_restore_human_locks") is True
        return {binding["semantic_mapping"]["field_mapping"][key]:
            (field.get("locked") if field.get("locked") is not None else True) or approved
            for key, field in job["fields"].items()}

    def _hold_reasons(self, binding, state):
        job_key, reasons = binding["job_key"], []
        if state.get("halted"):
            reasons.append("program_halted")
        if state["jobs"][job_key].get("paused"):
            reasons.append("job_paused")
        if any(effect.get("job_key") == job_key and effect.get("status") in {"sending", "held_unknown"}
                for effect in state["effects"].values()):
            reasons.append("unknown_effect")
        ceiling = state.get("budget_policy", {}).get("ceiling_micro_usd")
        totals = state.get("budget_totals", {})
        if (not isinstance(ceiling, int) or not 1 <= ceiling <= 12_000_000
                or totals["settled_micro_usd"] + totals["held_micro_usd"] > ceiling):
            reasons.append("budget_unavailable")
        return reasons

    def _registration(self, binding, specimen_id, revision, state, snapshot):
        job_key = binding["job_key"]
        job = state["jobs"][job_key]
        identity = {"organization_id": ORG, "collection_id": COLLECTION, "specimen_id": specimen_id,
            "job_id": binding["job_id"]}
        effects = {key: effect for key, effect in state["effects"].items() if effect.get("job_key") == job_key
            and all(effect.get("scope", {}).get(k) == v for k, v in identity.items())}
        outbox = {key: event for key, event in state["outbox"].items() if event.get("kind") == "research_field_retry"
            and all(event.get("command", {}).get("scope", {}).get(k) == v for k, v in identity.items())}
        base = {"record_revision": binding["base_canonical_revision"],
            "record_version_id": binding["base_record_version_id"], "canonical_run_id": binding["canonical_run_id"],
            "host_record_version_id": binding["base_host_record_version_id"],
            "snapshot_sha256": binding["base_snapshot_sha256"]}
        current = {"record_revision": binding["current_canonical_revision"],
            "record_version_id": binding["current_record_version_id"], "canonical_run_id": binding["canonical_run_id"],
            "host_record_version_id": binding["current_host_record_version_id"],
            "snapshot_sha256": binding["current_snapshot_sha256"]}
        return {"binding_id": binding["binding_id"], "registration_revision": binding["registration_revision"],
            "active": binding["active"], "base_canonical": base, "current_canonical": current,
            "job_id": binding["job_id"], "job_key": job_key, "generation": binding["generation"],
            "input_digest": binding["input_digest"], "profile_digest": binding["profile_digest"],
            "runtime_binding_digest": binding["runtime_binding_digest"],
            "canonical_profile_digest": binding["canonical_profile_digest"], "source_sha256": binding["source_sha256"],
            "semantic_mapping_digest": binding["semantic_mapping_digest"], "policy_digest": binding["policy_digest"],
            "program_key": binding["program_key"], "field_mapping": binding["semantic_mapping"]["field_mapping"],
            "semantic_mapping": binding["semantic_mapping"],
            "human_locks": self._human_locks(binding, job, snapshot), "job": job,
            "research_policy_origin": binding["semantic_mapping"]["research_policy_origin"],
            "journal_budget_policy_digest": binding["semantic_mapping"]["journal_budget_policy_digest"],
            "journal_budget_policy_origin": "verified_owner_registration_not_SQL_recomputed",
            "read_bundle": {"state_revision": revision, "server_time": datetime.now(timezone.utc).timestamp(),
                "job_key": job_key, "job": job, "halted": bool(state.get("halted")), "paused": bool(job.get("paused")),
                "effects": effects, "outbox": outbox, "hold_reasons": self._hold_reasons(binding, state)},
            "publication_transition": None}

    def binding_row(self, variables, specimen_id):
        """GetCanonicalResearchBindingV2's `binding` (None when no row matches)."""
        if not self.permitted(variables, specimen_id):
            return None
        specimen = self.specimens[specimen_id]
        snap = self.snapshots[(specimen_id, specimen["revision"])]
        binding = self.active_binding(specimen_id)
        count = sum(1 for row in self.bindings.values() if row["specimen_id"] == specimen_id and row["active"])
        if binding is None:
            return {"canonical": {"organization_id": ORG, "collection_id": COLLECTION, "specimen_id": specimen_id,
                    "record_revision": specimen["revision"], "record_version_id": None, "canonical_run_id": None,
                    "host_record_version_id": None, "snapshot_sha256": snap["sha256"],
                    "sensitive": specimen["sensitive"]},
                "active_registration_count": count, "registrations": [],
                "snapshot": snap, "causal": {"contract_version": None, "authority_digest": None, "import_proof_id": None,
                    "import_proof_digest": None, "head_receipt_id": None, "head_chain_digest": None,
                    "causal_chain": [], "causal_count": 0}, "projection": []}
        record = self.tables["record_version"].get(binding["current_record_version_id"])
        run = self.tables["pipeline_run"].get(binding["canonical_run_id"])
        if (record is None or record["runId"] != binding["canonical_run_id"] or run is None
                or run["id"] != specimen["active_run_id"] or run["specimenId"] != specimen_id
                or binding["current_canonical_revision"] != specimen["revision"]
                or binding["current_snapshot_sha256"] != snap["sha256"]):
            return None
        loaded = self.state(specimen_id, binding["program_key"])
        if loaded is None:
            raise AssertionError("binding without research state")
        revision, state = loaded
        chain = [receipt["causal_proof"] for receipt in sorted(self.receipts.values(),
            key=lambda item: item["used_canonical_revision"]) if receipt["binding_id"] == binding["binding_id"]
            and receipt["specimen_id"] == specimen_id]
        return {"canonical": {"organization_id": ORG, "collection_id": COLLECTION, "specimen_id": specimen_id,
                "record_revision": specimen["revision"], "record_version_id": record["id"], "canonical_run_id": run["id"],
                "host_record_version_id": binding["current_host_record_version_id"], "snapshot_sha256": snap["sha256"],
                "sensitive": specimen["sensitive"]},
            "active_registration_count": count,
            "registrations": [self._registration(binding, specimen_id, revision, state, snap["snapshot"])],
            "snapshot": snap,
            "causal": {"contract_version": binding["publication_version"], "authority_digest": binding["authority_digest"],
                "import_proof_id": binding["import_proof_id"], "import_proof_digest": binding["import_proof_digest"],
                "head_receipt_id": binding["current_receipt_id"], "head_chain_digest": binding["current_chain_digest"],
                "causal_chain": chain if len(chain) <= 20 else None, "causal_count": len(chain)},
            "projection": sorted((self._field_row(row) for row in self.tables["resolved_field"].values()
                if row["recordVersionId"] == binding["current_record_version_id"]), key=lambda row: row["fieldKey"])}

    @staticmethod
    def _field_row(row):
        return {key: row.get(key) for key in ("id", "recordVersionId", "candidateId", "fieldKey", "state", "fieldGroup")}

    def op_GetCanonicalResearchBindingV2(self, variables):
        specimen_id = variables["specimenId"]
        return {**self.envelope(variables, specimen_id), "binding": self.binding_row(variables, specimen_id)}

    def op_RegisterCanonicalResearchBindingV2(self, variables):
        self.require_member(variables)
        specimen_id, r = variables["specimenId"], json.loads(variables["registrationJson"])
        specimen = self.specimens.get(specimen_id)
        snap = None if specimen is None else self.snapshots[(specimen_id, specimen["revision"])]
        record = self.tables["record_version"].get(r["base_canonical"]["record_version_id"])
        run = None if specimen is None else self.tables["pipeline_run"].get(specimen["active_run_id"])
        profile = None if run is None else self.tables["profile_version"].get(run["profileVersionId"])
        loaded = None if specimen is None else self.state(specimen_id, r["program_key"])
        job = None if loaded is None else loaded[1]["jobs"].get(r["job_key"])
        fields = [] if record is None else [row for row in self.tables["resolved_field"].values()
            if row["recordVersionId"] == record["id"]]
        base = r["base_canonical"]
        admitted = (specimen is not None and not specimen["sensitive"] and specimen["revision"] >= 1
            and record is not None and record["runId"] == specimen["active_run_id"]
            and run is not None and run["specimenId"] == specimen_id and profile is not None and job is not None
            and r["publication_version"] == "research-publication/v2"
            and r["authority_digest"] and r["current_chain_digest"]
            and specimen["revision"] == base["record_revision"] and specimen["active_run_id"] == base["canonical_run_id"]
            and snap["sha256"] == base["snapshot_sha256"] and base == r["current_canonical"]
            and r["publication_transition"] is None
            and run["inputSha256"] == r["source_sha256"] and specimen["source_checksum"] == run["inputSha256"]
            and profile["configSha256"] == r["canonical_profile_digest"]
            and job["identity"] == {"organization_id": ORG, "collection_id": COLLECTION,
                "specimen_id": specimen_id, "job_id": r["job_id"]}
            and loaded[0] == r["state_revision"] and loaded[1]["budget_policy"] == r["journal_budget_policy"]
            and job["record_revision"] == specimen["revision"] and job["generation"] == r["generation"]
            and job["pins"]["input_digest"] == r["input_digest"] and job["binding_digest"] == r["runtime_binding_digest"]
            and len(r["semantic_mapping"]["field_mapping"]) == 20
            and len(fields) == 20 and len({row["fieldKey"] for row in fields}) == 20)
        if not admitted:
            raise ConnectorRefusal("research registration unavailable")
        row = {"organization_id": ORG, "collection_id": COLLECTION, "specimen_id": specimen_id,
            "binding_id": r["binding_id"], "registration_revision": 1, "active": True,
            "base_canonical_revision": specimen["revision"], "base_record_version_id": base["record_version_id"],
            "base_snapshot_sha256": base["snapshot_sha256"], "base_host_record_version_id": base["host_record_version_id"],
            "canonical_run_id": specimen["active_run_id"], "current_canonical_revision": specimen["revision"],
            "current_record_version_id": base["record_version_id"], "current_snapshot_sha256": base["snapshot_sha256"],
            "current_host_record_version_id": base["host_record_version_id"], "current_receipt_id": None,
            "job_id": r["job_id"], "job_key": r["job_key"], "generation": r["generation"],
            "input_digest": r["input_digest"], "profile_digest": r["profile_digest"],
            "runtime_binding_digest": r["runtime_binding_digest"], "canonical_profile_digest": r["canonical_profile_digest"],
            "source_sha256": r["source_sha256"], "semantic_mapping_digest": r["semantic_mapping_digest"],
            "policy_digest": r["policy_digest"], "program_key": r["program_key"], "semantic_mapping": r["semantic_mapping"],
            "authority_digest": r["authority_digest"], "import_proof_id": r["import_proof_id"],
            "import_proof_digest": r["import_proof_digest"], "current_chain_digest": r["current_chain_digest"],
            "publication_version": "research-publication/v2", "registered_by": variables["actorUid"],
            "registered_at": iso_now()}
        existing = self.bindings.get(specimen_id)
        registration_columns = [key for key in row if key not in {"registered_by", "registered_at"}]
        if existing is not None:
            stale = (existing["binding_id"] != row["binding_id"] and (not existing["active"]
                or existing["canonical_run_id"] != row["canonical_run_id"]
                or existing["current_canonical_revision"] != row["current_canonical_revision"]
                or existing["current_snapshot_sha256"] != row["current_snapshot_sha256"]))
            replay = (existing["current_receipt_id"] is None
                and all(existing[key] == row[key] for key in registration_columns))
            if not (stale or replay):
                raise ConnectorRefusal("research registration unavailable")
            if replay:
                row["registered_by"], row["registered_at"] = existing["registered_by"], existing["registered_at"]
        self.bindings[specimen_id] = row
        return {"registered": 1}

    # ---- publication intents ---------------------------------------------
    def _intent_for(self, variables, specimen_id, key):
        found = [intent for intent in self.intents.values() if intent["specimen_id"] == specimen_id
            and intent["actor_uid"] == variables["actorUid"] and intent["idempotency_key"] == key]
        assert len(found) <= 1
        return found[0] if found else None

    def _preparations(self, intent_id):
        return sorted((prep for prep in self.preparations.values() if prep["intent_id"] == intent_id),
            key=lambda prep: prep["ordinal"])

    def _attempt(self, intent_id):
        attempt = self.attempts.get(intent_id)
        return None if attempt is None else {key: attempt[key] for key in
            ("id", "preparation_id", "operation_digest", "preparation_digest", "admission_digest")}

    def op_GetResearchPublicationIntentV2(self, variables):
        specimen_id = variables["specimenId"]
        intent = self._intent_for(variables, specimen_id, variables["idempotencyKey"])
        row = None
        if intent is not None and self.permitted(variables, specimen_id) and variables["requestIdentityDigest"]:
            preparations = self._preparations(intent["id"])
            row = {"original": intent["payload"], "preparation_count": len(preparations),
                "preparations": [prep["payload"] for prep in preparations] if len(preparations) <= 20 else None,
                "attempt": self._attempt(intent["id"])}
        return {**self.envelope(variables, specimen_id), "intent": row}

    def op_RetainResearchPublicationIntentV2(self, variables):
        self.require_member(variables)
        specimen_id, i = variables["specimenId"], json.loads(variables["intentJson"])
        binding = self.active_binding(specimen_id)
        loaded = None if binding is None else self.state(specimen_id, binding["program_key"])
        basis = i["original_prepared"]["basis"]
        base = i["original_base"]
        if (binding is None or self.specimens[specimen_id]["sensitive"] or loaded is None
                or i["contract_version"] != "research-publication-intent/v2" or i["actor_uid"] != variables["actorUid"]
                or i["binding_id"] != binding["binding_id"] or i["job_key"] != binding["job_key"]
                or i["program_key"] != binding["program_key"] or i["authority_digest"] != binding["authority_digest"]
                or i["import_proof_id"] != binding["import_proof_id"]
                or i["import_proof_digest"] != binding["import_proof_digest"]
                or base["record_version_id"] != binding["base_record_version_id"]
                or base["record_revision"] != binding["base_canonical_revision"]
                or base["snapshot_sha256"] != binding["base_snapshot_sha256"]
                or base["canonical_run_id"] != binding["canonical_run_id"]
                or base["host_record_version_id"] != binding["base_host_record_version_id"]
                or basis["scope"]["organization_id"] != ORG or basis["scope"]["collection_id"] != COLLECTION
                or basis["scope"]["specimen_id"] != specimen_id or basis["scope"]["job_id"] != binding["job_id"]
                or basis["scope"]["generation"] != binding["generation"]
                or basis["binding_digest"] != binding["runtime_binding_digest"]
                or loaded[0] != basis["state_revision"]):
            raise ConnectorRefusal("native v2 intent unavailable")
        if i["id"] in self.intents or self._intent_for(variables, specimen_id, i["idempotency_key"]):
            raise ConnectorRefusal("native v2 intent unavailable")
        self.intents[i["id"]] = {"id": i["id"], "specimen_id": specimen_id, "actor_uid": variables["actorUid"],
            "idempotency_key": i["idempotency_key"], "operation_digest": i["operation_digest"],
            "scientific_intent_digest": i["scientific_intent_digest"],
            "request_identity_digest": i["server_request_identity_digest"], "payload": i}
        return {"retainedIntent": 1}

    def op_RetainResearchPublicationPreparationV2(self, variables):
        self.require_member(variables)
        specimen_id, p = variables["specimenId"], json.loads(variables["preparationJson"])
        intent = self.intents.get(p["intent_id"])
        binding = self.active_binding(specimen_id)
        loaded = None if binding is None else self.state(specimen_id, binding["program_key"])
        previous = None if intent is None else self._preparations(intent["id"])
        anchor = p["anchor"]
        lease = None if loaded is None else loaded[1]["jobs"][binding["job_key"]].get("lease")
        if (intent is None or intent["actor_uid"] != variables["actorUid"] or intent["specimen_id"] != specimen_id
                or binding is None or intent["payload"]["binding_id"] != binding["binding_id"] or loaded is None
                or p["contract_version"] != "research-publication-preparation/v2"
                or p["scientific_intent_digest"] != intent["scientific_intent_digest"]
                or p["authority_digest"] != binding["authority_digest"]
                or loaded[0] != p["state_revision"] or loaded[1] != p["expected_state"]
                or binding["current_record_version_id"] != anchor["record_version_id"]
                or binding["current_canonical_revision"] != anchor["record_revision"]
                or binding["current_snapshot_sha256"] != anchor["snapshot_sha256"]
                or binding["current_host_record_version_id"] != anchor["host_record_version_id"]
                or binding["current_chain_digest"] != p["anchor_chain_digest"]
                or binding["current_receipt_id"] != p["anchor_receipt_id"]
                or binding["registration_revision"] != p["anchor_registration_revision"]
                or lease != p["prepared"]["basis"]["lease"]
                or lease is None or lease["expires_at"] <= datetime.now(timezone.utc).timestamp()
                or intent["id"] in self.attempts
                or not 1 <= p["ordinal"] <= 20 or p["ordinal"] != len(previous) + 1
                or (p["ordinal"] > 1 and (previous[-1]["id"] != p["prior_preparation_id"]
                    or previous[-1]["preparation_digest"] != p["prior_preparation_digest"]))):
            raise ConnectorRefusal("native v2 preparation unavailable")
        payload = {key: value for key, value in p.items() if key != "preparation_digest"}
        self.preparations[p["id"]] = {"id": p["id"], "intent_id": p["intent_id"], "ordinal": p["ordinal"],
            "preparation_digest": p["preparation_digest"], "admission_digest": p["admission_digest"], "payload": payload}
        return {"retainedPreparation": 1}

    def op_MarkResearchPublicationAttemptV2(self, variables):
        self.require_member(variables)
        specimen_id, a = variables["specimenId"], json.loads(variables["admissionJson"])
        intent = self.intents.get(a["intent_id"])
        prep = self.preparations.get(a["preparation_id"])
        binding = self.active_binding(specimen_id)
        loaded = None if binding is None else self.state(specimen_id, binding["program_key"])
        if (intent is None or intent["operation_digest"] != a["operation_digest"] or prep is None
                or prep["intent_id"] != intent["id"] or prep["preparation_digest"] != a["preparation_digest"]
                or prep["admission_digest"] != a["admission_digest"] or binding is None or loaded is None
                or binding["binding_id"] != intent["payload"]["binding_id"]
                or loaded[0] != a["state_revision"] or loaded[1] != a["expected_state"]
                or binding["current_record_version_id"] != a["used_record_version_id"]
                or binding["registration_revision"] != a["registration_revision"] or intent["id"] in self.attempts):
            raise ConnectorRefusal("native v2 attempt unavailable")
        self.attempts[intent["id"]] = {"id": a["id"], "intent_id": intent["id"], "preparation_id": prep["id"],
            "operation_digest": a["operation_digest"], "preparation_digest": a["preparation_digest"],
            "admission_digest": a["admission_digest"]}
        return {"markedAttempt": 1}

    def op_GetRetainedResearchPublicationLocatorsV2(self, variables):
        specimen_id = variables["specimenId"]
        binding = self.active_binding(specimen_id)
        intents = [] if binding is None or not self.permitted(variables, specimen_id) else sorted(
            (intent for intent in self.intents.values() if intent["specimen_id"] == specimen_id
                and intent["actor_uid"] == variables["actorUid"]
                and intent["payload"]["binding_id"] == binding["binding_id"]), key=lambda item: item["id"])
        locators = [{"contract_version": "retained-publication-locator/v2", "intent_id": intent["id"],
            "original_scope": intent["payload"]["original_prepared"]["basis"]["scope"],
            "program_key": intent["payload"]["original_prepared"]["basis"]["program_key"],
            "idempotency_key": intent["idempotency_key"], "request_identity_digest": intent["request_identity_digest"],
            "receipt_present": any(receipt["intent_id"] == intent["id"] for receipt in self.receipts.values()),
            "attempt_present": intent["id"] in self.attempts} for intent in intents]
        return {**self.envelope(variables, specimen_id),
            "inventory": {"locator_count": len(locators), "locators": locators if len(locators) <= 20 else None}}

    # ---- materialization inputs ------------------------------------------
    def projection_rows(self, run_id):
        records = {row["id"] for row in self.tables["record_version"].values() if row["runId"] == run_id}
        candidates = {row["id"] for row in self.tables["field_candidate"].values() if row["runId"] == run_id}
        return {"record_versions": self.rows("record_version", lambda row: row["runId"] == run_id),
            "resolved_fields": self.rows("resolved_field", lambda row: row["recordVersionId"] in records),
            "candidates": self.rows("field_candidate", lambda row: row["runId"] == run_id),
            "candidate_evidence": self.rows("candidate_evidence", lambda row: row["candidateId"] in candidates),
            "evidence": self.rows("evidence_item", lambda row: row["runId"] == run_id),
            "tool_calls": self.rows("tool_call", lambda row: row["runId"] == run_id),
            "findings": self.rows("validation_finding", lambda row: row["recordVersionId"] in records)}

    def native_input_rows(self, specimen_id):
        runs = self.specimen_runs(specimen_id)
        in_run = lambda row: row["runId"] in runs
        return {"observations": self.rows("model_observation", in_run),
            "transcriptions": self.rows("transcription_version", in_run),
            "handoffs": self.rows("harness_input", in_run), "comparisons": self.rows("reading_comparison", in_run),
            "assets": self.rows("source_asset", lambda row: row["specimenId"] == specimen_id),
            "regions": self.rows("label_region", in_run),
            "runs": self.rows("pipeline_run", lambda row: row["specimenId"] == specimen_id)}

    def lineage_rows(self, specimen_id, run_id):
        lineages = {row["id"] for row in self.tables["canonical_value_lineage_v2"].values()
            if row["specimenId"] == specimen_id}
        return {"value_lineages": self.rows("canonical_value_lineage_v2", lambda row: row["specimenId"] == specimen_id),
            "value_dependencies": self.rows("canonical_value_dependency_v2", lambda row: row["lineageId"] in lineages),
            "value_evidence": self.rows("canonical_value_evidence_v2", lambda row: row["lineageId"] in lineages),
            "tool_input_lineage": self.rows("tool_input_lineage_v2", lambda row: row["specimenId"] == specimen_id),
            "captured_tool_executions": self.rows("captured_tool_execution_v2", lambda row: row["runId"] == run_id)}

    def op_GetCanonicalResearchMaterializationInputsV2(self, variables):
        specimen_id = variables["specimenId"]
        envelope = self.envelope(variables, specimen_id)
        base = self.binding_row(variables, specimen_id)
        binding = self.active_binding(specimen_id)
        prep = self.preparations.get(variables["preparationId"])
        intent = None if prep is None else self.intents.get(prep["intent_id"])
        if (base is None or binding is None or intent is None or intent["specimen_id"] != specimen_id
                or intent["actor_uid"] != variables["actorUid"] or intent["idempotency_key"] != variables["idempotencyKey"]
                or intent["request_identity_digest"] != variables["requestIdentityDigest"]):
            return {**envelope, "binding": None}
        revision, state = self.state(specimen_id, binding["program_key"])
        job_key, job_id, run_id = binding["job_key"], binding["job_id"], binding["canonical_run_id"]
        target = intent["payload"]["original_prepared"]["basis"]["field_key"]
        fields = state["jobs"][job_key]["fields"]
        preparations = self._preparations(intent["id"])
        anchor = prep["payload"]["anchor"]
        anchor_snapshot = self.snapshots.get((specimen_id, anchor["record_revision"]))
        anchor_record = self.tables["record_version"].get(anchor["record_version_id"])
        receipt = self.receipts.get(binding["current_receipt_id"])
        scoped = lambda scope: (scope.get("organization_id") == ORG and scope.get("collection_id") == COLLECTION
            and scope.get("specimen_id") == specimen_id and scope.get("job_id") == job_id)
        inputs = {"contract_version": "research-native-materialization-inputs/v2",
            "observed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "registration": base["registrations"][0],
            "outer_intent": {"original": intent["payload"], "preparation_count": len(preparations),
                "preparations": [item["payload"] for item in preparations] if len(preparations) <= 20 else None,
                "attempt": self._attempt(intent["id"])},
            "scoped_state": base["registrations"][0]["read_bundle"],
            "private_state_integrity": {"revision": revision, "contract_version": state["contract_version"],
                "state_json": canonical(state).decode(), "state": state},
            "current_snapshot": base["snapshot"],
            "preparation_snapshot": {"identity": anchor,
                "snapshot": None if anchor_snapshot is None else anchor_snapshot,
                "record": None if anchor_record is None else {"id": anchor_record["id"], "runId": anchor_record["runId"],
                    "predecessorId": anchor_record["predecessorId"]}},
            "retained_history": base["causal"]["causal_chain"],
            "projection_rows": self.projection_rows(run_id),
            "checkpoint_inputs": {"target": fields[target]["checkpoint"]["payload"] if fields[target].get("checkpoint") else None,
                "terminal_siblings": [fields[key]["checkpoint"]["payload"] for key in sorted(fields) if key != target
                    and fields[key]["work_state"] in TERMINAL_WORK and fields[key].get("checkpoint") is not None]},
            "original_request_sources": [{"run_id": key, "entry": entry} for key, entry in sorted(state["journal"].items())
                if scoped(entry.get("scope", {}))],
            "captured_executions": [{"effect_id": key, "effect": effect} for key, effect in sorted(state["effects"].items())
                if effect.get("job_key") == job_key and scoped(effect.get("scope", {}))],
            "native_input_rows": self.native_input_rows(specimen_id),
            "lineage_rows": self.lineage_rows(specimen_id, run_id),
            "prepack_proof": None if receipt is None else receipt["prepack_proof"]}
        return {**envelope, "binding": {**base, "materialization_inputs": inputs}}

    # ---- publication -------------------------------------------------------
    def op_PublishCanonicalResearchV2(self, variables):
        self.require_member(variables)
        specimen_id, c = variables["specimenId"], json.loads(variables["commitJson"])
        specimen = self.specimens[specimen_id]
        binding = self.active_binding(specimen_id)
        receipt = c["receipt"]
        intent = self.intents.get(c["intent_id"])
        prep = self.preparations.get(c["causal"]["winning_preparation_id"])
        attempt = None if intent is None else self.attempts.get(intent["id"])
        loaded = None if binding is None else self.state(specimen_id, binding["program_key"])
        guard = c["materialization_input_guard"]
        run_id = None if binding is None else binding["canonical_run_id"]
        prior_fields = [] if binding is None else [row for row in self.tables["resolved_field"].values()
            if row["recordVersionId"] == binding["current_record_version_id"]]
        admissible = (binding is not None and not specimen["sensitive"] and loaded is not None
            and binding["registration_revision"] == c["registration_revision"]
            and binding["binding_id"] == receipt["bindingId"]
            and binding["current_receipt_id"] == c["causal"]["parent_receipt_id"]
            and binding["current_chain_digest"] == c["causal"]["parent_chain_digest"]
            and binding["current_canonical_revision"] == specimen["revision"]
            and intent is not None and intent["actor_uid"] == variables["actorUid"]
            and intent["idempotency_key"] == receipt["idempotencyKey"]
            and intent["operation_digest"] == receipt["operationDigest"]
            and intent["scientific_intent_digest"] == c["causal"]["scientific_intent_digest"]
            and binding["authority_digest"] == intent["payload"]["authority_digest"]
            and prep is not None and prep["intent_id"] == intent["id"]
            and prep["preparation_digest"] == receipt["preparedDigest"]
            and prep["payload"]["prepared"] == c["prepared"] and prep["payload"] == c["preparation"]
            and prep["admission_digest"] == c["causal"]["admission_digest"]
            and attempt is not None and attempt["preparation_id"] == prep["id"]
            and loaded[0] == c["state_revision"] and loaded[1] == c["expected_state"]
            and not self._hold_reasons(binding, loaded[1])
            and guard["contract_version"] == "native-materialization-guard/v2"
            and guard["binding_id"] == binding["binding_id"]
            and guard["registration_revision"] == binding["registration_revision"]
            and guard["state_revision"] == loaded[0]
            and guard["projection_rows"] == self.projection_rows(run_id)
            and guard["native_input_rows"] == self.native_input_rows(specimen_id)
            and guard["lineage_rows"] == self.lineage_rows(specimen_id, run_id)
            and c["changed_field"] == binding["semantic_mapping"]["field_mapping"][c["prepared"]["basis"]["field_key"]]
            and c["record"]["runId"] == run_id
            and c["record"]["predecessorId"] == binding["current_record_version_id"]
            and c["record"]["id"] == receipt["nativeRecordVersionId"]
            and (c["record"]["disposition"] is None or c["record"]["disposition"] in {"cleared", "needs_human_review"})
            and c["snapshot"]["id"] == specimen_id and c["snapshot"]["version"] == specimen["revision"] + 1
            and c["snapshot"]["asset"]["sha256"] == binding["source_sha256"]
            and c["snapshot"]["asset"].get("sensitive", True) is False
            and c["snapshot"]["scope"] == {"organization_id": ORG, "collection_id": COLLECTION}
            and c["snapshot"]["run"]["id"] == run_id
            and c["snapshot"]["run"].get("disposition") == c["record"]["disposition"]
            and len(c["fields"]) == 20 and len(prior_fields) == 20
            and receipt["snapshotSha256"] == canonical_digest(c["snapshot"])
            and c["prepack_proof"]["contract_version"] == "research-prepack-proof/v2"
            and receipt["prepackProofDigest"] == c["causal"]["native_commit"]["prepackProofDigest"]
            and c["prepack_proof"]["packed_snapshot_digest"] == receipt["snapshotSha256"]
            and c["prepack_proof"]["packing_metadata"] == c["snapshot"].get("active_graph"))
        if not admissible:
            raise ConnectorRefusal("native research publication unavailable")
        revision = specimen["revision"] + 1
        now = iso_now()
        rows = []
        for group, table in DELTA_TABLES.items():
            for value in c["delta"][group]:
                row = {"organizationId": ORG, "collectionId": COLLECTION, **value, "createdAt": now}
                if group in {"evidence", "tool_calls", "candidates"}:
                    row["runId"] = run_id
                if group == "assets":
                    row["specimenId"] = specimen_id
                if group == "findings":
                    row["recordVersionId"] = c["record"]["id"]
                rows.append((group, table, row))
        # The connector inserts a candidate of the changed field only, citing an
        # independent reading or a transcription of the run, and a link only to
        # recorded or successful evidence of the run (this commit's or retained).
        evidence = {row["id"]: row for group, _, row in rows if group == "evidence"}
        evidence.update({key: row for key, row in self.tables["evidence_item"].items() if key not in evidence})
        candidates = {row["id"] for group, _, row in rows if group == "candidates"}
        for group, _, row in rows:
            observation = self.tables["model_observation"].get(row.get("sourceObservationId") or "")
            transcription = self.tables["transcription_version"].get(row.get("sourceTranscriptionId") or "")
            if group == "candidates" and (row["fieldKey"] != c["changed_field"]
                    or row.get("sourceObservationId") is not None and (observation is None
                        or observation["runId"] != run_id or not observation["independent"])
                    or row.get("sourceTranscriptionId") is not None and (transcription is None
                        or transcription["runId"] != run_id)):
                raise ConnectorRefusal("native research publication unavailable")
            linked = evidence.get(row.get("evidenceId") or "")
            if group == "links" and (row["candidateId"] not in candidates or linked is None
                    or linked["runId"] != run_id or linked["outcome"] not in {"success", "recorded"}
                    or row["relation"] not in {"decides", "supports", "contradicts"}):
                raise ConnectorRefusal("native research publication unavailable")
        rows.append(("record", "record_version", {"organizationId": ORG, "collectionId": COLLECTION,
            "id": c["record"]["id"], "runId": run_id, "predecessorId": binding["current_record_version_id"],
            "disposition": c["record"]["disposition"], "policyVersion": c["record"]["policyVersion"],
            "reasonCodes": list(c["record"]["reasonCodes"]), "summary": c["record"]["summary"], "createdAt": now}))
        new_fields = {value["fieldKey"]: value for value in c["fields"]}
        for prior in prior_fields:
            value = new_fields[prior["fieldKey"]]
            changed = prior["fieldKey"] == c["changed_field"]
            rows.append(("fields", "resolved_field", {"organizationId": ORG, "collectionId": COLLECTION,
                "id": value["id"], "recordVersionId": c["record"]["id"],
                "candidateId": value["candidateId"] if changed else prior["candidateId"],
                "fieldKey": prior["fieldKey"], "state": value["state"] if changed else prior["state"],
                "fieldGroup": value["fieldGroup"] if changed else prior["fieldGroup"], "createdAt": now}))
        if any(row["id"] in self.tables[table] for _, table, row in rows):
            raise ConnectorRefusal("native research publication unavailable")
        for _, table, row in rows:
            self.insert(table, row)
        specimen.update(revision=revision, state=c["state"], disposition=c["record"]["disposition"],
            active_run_id=run_id, work_available_at=now if c["state"] == "running" else None)
        self._snapshot_row(specimen_id, revision, c["snapshot"], receipt["snapshotSha256"], c["snapshot_contract"])
        self.request_receipts[(variables["actorUid"], "research-publication/v2", receipt["idempotencyKey"])] = {
            "specimen_id": specimen_id, "revision": revision, "request_sha256": receipt["operationDigest"]}
        self.audit_events[c["audit_id"]] = {"specimen_id": specimen_id, "actor_uid": variables["actorUid"],
            "action": "research_publication", "revision": revision, "request_sha256": receipt["operationDigest"]}
        self.outbox_events[c["outbox_id"]] = {"specimen_id": specimen_id, "aggregate_revision": revision,
            "event_type": "research_publication_committed", "deduplication_key": receipt["operationDigest"]}
        self.backend.cas(self._state_scope(specimen_id), binding["program_key"], c["state_revision"], c["next_state"])
        used = {"revision": specimen["revision"] - 1, "record": binding["current_record_version_id"],
            "host": binding["current_host_record_version_id"], "sha": binding["current_snapshot_sha256"]}
        binding.update(registration_revision=binding["registration_revision"] + 1,
            current_canonical_revision=revision, current_record_version_id=receipt["nativeRecordVersionId"],
            current_snapshot_sha256=receipt["snapshotSha256"],
            current_host_record_version_id=receipt["hostRecordVersionId"], current_receipt_id=receipt["id"],
            current_chain_digest=c["causal"]["chain_digest"])
        self.receipts[receipt["id"]] = {"id": receipt["id"], "actor_uid": variables["actorUid"],
            "idempotency_key": receipt["idempotencyKey"], "specimen_id": specimen_id,
            "operation_digest": receipt["operationDigest"], "publication_digest": receipt["publicationDigest"],
            "prepared_digest": receipt["preparedDigest"], "intent_id": c["intent_id"],
            "binding_id": binding["binding_id"], "job_id": binding["job_id"], "job_key": binding["job_key"],
            "generation": binding["generation"], "input_digest": binding["input_digest"],
            "profile_digest": binding["profile_digest"], "runtime_binding_digest": binding["runtime_binding_digest"],
            "used_canonical_revision": revision - 1, "used_record_version_id": used["record"],
            "used_host_record_version_id": used["host"], "used_snapshot_sha256": used["sha"],
            "resulting_canonical_revision": revision, "native_record_version_id": receipt["nativeRecordVersionId"],
            "canonical_run_id": run_id, "host_record_version_id": receipt["hostRecordVersionId"],
            "snapshot_sha256": receipt["snapshotSha256"], "projection_digest": receipt["projectionDigest"],
            "projection_count": 20, "audit_id": c["audit_id"], "outbox_id": c["outbox_id"],
            "policy_receipt_digest": c["policy_materialization"]["policy_receipt_digest"],
            "lineage_digest": c["policy_materialization"]["lineage_digest"], "sensitive": False,
            "winning_preparation_id": c["causal"]["winning_preparation_id"], "causal_proof": c["causal"],
            "chain_digest": c["causal"]["chain_digest"], "prepack_proof": c["prepack_proof"],
            "prepack_proof_digest": receipt["prepackProofDigest"]}
        return {"committed": 1}

    def op_GetResearchPublicationReceiptV2(self, variables):
        specimen_id = variables["specimenId"]
        envelope = self.envelope(variables, specimen_id)
        p = next((row for row in self.receipts.values() if row["actor_uid"] == variables["actorUid"]
            and row["idempotency_key"] == variables["idempotencyKey"]), None)
        q = self.request_receipts.get((variables["actorUid"], "research-publication/v2", variables["idempotencyKey"]))
        if (p is None and q is None) or not self.permitted(variables, specimen_id) or not variables["operationDigest"]:
            return {**envelope, "retained": None}
        if p is None:
            return {**envelope, "retained": {"publication": None, "request": self._request(variables, q), "snapshot": None,
                "record": None, "fields": [], "audit": None, "outbox": None, "intent": None, "preparation": None,
                "causal": None, "attempt": None, "prepack": None}}
        intent = self.intents.get(p["intent_id"])
        prep = self.preparations.get(p["winning_preparation_id"])
        record = self.tables["record_version"].get(p["native_record_version_id"])
        audit = self.audit_events.get(p["audit_id"])
        outbox = self.outbox_events.get(p["outbox_id"])
        attempt = None if intent is None else self.attempts.get(intent["id"])
        publication = {"id": p["id"], "actorUid": p["actor_uid"], "idempotencyKey": p["idempotency_key"],
            "specimenId": p["specimen_id"], "operationDigest": p["operation_digest"],
            "publicationDigest": p["publication_digest"], "preparedDigest": p["prepared_digest"],
            "bindingId": p["binding_id"], "jobId": p["job_id"], "jobKey": p["job_key"], "generation": p["generation"],
            "inputDigest": p["input_digest"], "profileDigest": p["profile_digest"],
            "runtimeBindingDigest": p["runtime_binding_digest"], "usedCanonicalRevision": p["used_canonical_revision"],
            "usedRecordVersionId": p["used_record_version_id"], "usedHostRecordVersionId": p["used_host_record_version_id"],
            "usedSnapshotSha256": p["used_snapshot_sha256"], "resultingCanonicalRevision": p["resulting_canonical_revision"],
            "nativeRecordVersionId": p["native_record_version_id"], "canonicalRunId": p["canonical_run_id"],
            "hostRecordVersionId": p["host_record_version_id"], "snapshotSha256": p["snapshot_sha256"],
            "projectionDigest": p["projection_digest"], "projectionCount": p["projection_count"],
            "sensitive": p["sensitive"], "auditId": p["audit_id"], "outboxId": p["outbox_id"],
            "policyReceiptDigest": p["policy_receipt_digest"], "lineageDigest": p["lineage_digest"],
            "prepackProofDigest": p["prepack_proof_digest"]}
        return {**envelope, "retained": {"publication": publication, "request": self._request(variables, q),
            "snapshot": self.snapshots.get((specimen_id, p["resulting_canonical_revision"])),
            "record": None if record is None else {"id": record["id"], "runId": record["runId"],
                "predecessorId": record["predecessorId"]},
            "fields": sorted((self._field_row(row) for row in self.tables["resolved_field"].values()
                if row["recordVersionId"] == p["native_record_version_id"]), key=lambda row: row["fieldKey"]),
            "audit": None if audit is None else {"actorUid": audit["actor_uid"], "revision": audit["revision"],
                "requestSha256": audit["request_sha256"]},
            "outbox": None if outbox is None else {"aggregateRevision": outbox["aggregate_revision"],
                "deduplicationKey": outbox["deduplication_key"]},
            "intent": None if intent is None else intent["payload"],
            "preparation": None if prep is None else prep["payload"], "causal": p["causal_proof"],
            "attempt": None if attempt is None else self._attempt(intent["id"]), "prepack": p["prepack_proof"]}}

    @staticmethod
    def _request(variables, q):
        if q is None:
            return None
        return {"operation": "research-publication/v2", "actorUid": variables["actorUid"],
            "idempotencyKey": variables["idempotencyKey"], "requestSha256": q["request_sha256"],
            "specimenId": q["specimen_id"], "revision": q["revision"]}


class _AlreadyExists(Exception):
    pass


# ---- the synthetic specimen -------------------------------------------------
class GenerationBlobs(LocalBlobs):
    """Local files addressed as production's Cloud Storage refs: "<sha256>:<generation>"."""

    def put(self, data: bytes) -> str:
        return super().put(data).partition(":")[0] + ":1"

    def get_bounded(self, ref: str, max_bytes: int) -> bytes:
        return super().get_bounded(ref.partition(":")[0], max_bytes)


def published_profile():
    return published_registry().profiles[0]


def worker_principal(role="operator", user_id=WORKER):
    return Principal(user_id=user_id, role=role, scope=Scope(organization_id=ORG, collection_id=COLLECTION))


def specimen_before_adjudication(blobs):
    """A non-sensitive specimen whose two readers agree, at the ordinary adjudicate step.

    Intake, classify, quality check, segmentation and both readings are done, as
    the ordinary chain leaves them; classify pinned the published profile.
    """
    published = published_profile()
    output = io.BytesIO()
    Image.new("RGB", (100, 100), "white").save(output, format="JPEG", quality=95)
    image = output.getvalue()
    ref = blobs.put(image)
    sha = ref.partition(":")[0]
    asset = Asset(sha256=sha, blob_ref=ref, media_type="image/jpeg", size_bytes=len(image),
        width=100, height=100, filename="synthetic-e2e.jpeg", uploader=WORKER, sensitive=False)
    region = Region(asset_id=asset.id, x=0, y=0, width=100, height=100, order=0,
        method="synthetic_fixture_region", version="1")
    # The readers saw the region crop, retained as segmentation retains it.
    crop_png = region_png(Image.open(io.BytesIO(image)), region)
    region.crop_ref = blobs.put(crop_png)
    crop = hashlib.sha256(crop_png).hexdigest()
    specimen = Specimen(scope=Scope(organization_id=ORG, collection_id=COLLECTION), asset=asset,
        run=Run(regions=[region]))
    run = specimen.run
    language = bind_profile_rules(specimen, published, published_risk_registry())
    run.profile_snapshot = published.model_dump(mode="json")
    run.profile_registry_version = published_registry().version
    run.profile = Profile(language_handling=language, id=published.id, version=published.version,
        schema_version=published.schema_version, policy_version=published.clearance_policy,
        mandatory_fields=published.mandatory_fields, routes=published.model_routes,
        first_pass_route=published.first_pass_route, synthetic=published.synthetic,
        institutional_policy_approved=published.institutional_policy_approved,
        semantics_confirmed=published.semantics_confirmed)
    groups = {key: "mandatory" for key in published.mandatory_fields} | {
        key: "optional" for key in published.optional_fields}
    run.fields = {key: FieldValue() for key in groups}
    run.field_groups = groups
    run.dependencies = {"adapter": "OfflineE2E", "synthetic": False,
        "profile_snapshot_sha256": canonical_digest(run.profile_snapshot),
        "profile_registry_version": run.profile_registry_version}
    for route in run.profile.routes:
        raw = ("SYNTHETIC FIXTURE " + route + "\n" + LABEL_TEXT).encode()
        run.observations.append(Observation(region_id=region.id, route_id=route, model_id="synthetic-" + route,
            provider="synthetic", prompt_version=hashlib.sha256(("prompt:" + route).encode()).hexdigest(),
            input_sha256=crop, input_asset_id=asset.id, input_crop_ref=region.crop_ref,
            literal_text=LABEL_TEXT, raw_ref=blobs.put(raw),
            raw_sha256=hashlib.sha256(raw).hexdigest()))
    run.completed_steps = ["pin_dependencies", "classify", "quality_check", "segment"] + [
        f"transcribe:{region.id}:{route}" for route in run.profile.routes]
    run.stage = "running"
    return specimen


def research_state(fake, specimen_id):
    """The run's research state document as the connector stores it."""
    binding = fake.active_binding(specimen_id)
    return fake.state(specimen_id, binding["program_key"])


# ---- scripted models and recorded sources -----------------------------------
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "production_e2e"
# The taxonomy sources source_readiness.py makes ready. GBIF decides (G23);
# the other two support and are looked up for the record.
TAXONOMY_SOURCES = ("gbif", "global_names_verifier", "catalogue_of_life")
LITERAL_FIELDS = {FieldKey.COLLECTION_CODE, FieldKey.HABITAT, FieldKey.COLLECTION_METHOD,
    FieldKey.COLLECTORS, FieldKey.PRECISE_LOCATION, FieldKey.FMNH_INS_NUMBER}
ELEVATIONS = (FieldKey.ELEVATION_FROM_M, FieldKey.ELEVATION_TO_M,
    FieldKey.ELEVATION_FROM_FT, FieldKey.ELEVATION_TO_FT)
UNAVAILABLE = "Qualified applicable source strategy remains unavailable."
USAGE = RequestUsage(input_tokens=3, output_tokens=2)


def _waiting_source(key, reason=UNAVAILABLE):
    return FieldResolution(field_key=key, work_state=WorkState.WAITING_SOURCE,
        value=FieldValue(), reason=reason)


def _assemblies(request, key):
    """The first event's complete assemblies for a field, in request order."""
    rows = [item for item in request.assemblies if item.field_key == key]
    return [item for item in rows if item.event_id == rows[0].event_id] if rows else []


def _verbatims(request, rows):
    """Each reading's verbatim behind the cited assemblies, as evidence.temporal_resolutions keeps it."""
    fragments = {item.id: item for item in request.fragments}
    verbatims = {fragments[key].observation_id: fragments[key].observation_text
        for item in rows for key in item.fragment_ids}
    return {"verbatim_by_observation": verbatims, "settled_observation_ids": list(verbatims)}


def _literal(request, key):
    """A complete written assertion; the label evidence it cites supports it (G23)."""
    rows = _assemblies(request, key)
    if not rows:
        return None
    text = rows[0].interpreted_text
    settled = catalog_literal(text) if key == FieldKey.FMNH_INS_NUMBER else text
    evidence = tuple(dict.fromkeys(eid for item in rows for eid in item.evidence_ids))
    return FieldResolution(field_key=key, work_state=WorkState.RESOLVED,
        value=FieldValue(state=ValueState.SUPPORTED, literal=text, parsed=settled,
            normalized=settled, evidence_ids=list(evidence),
            evidence_relations=dict.fromkeys(evidence, "supports"), **_verbatims(request, rows)),
        evidence_ids=evidence, assembly_ids=tuple(item.id for item in rows),
        event_id=rows[0].event_id, reason="Complete written field assertion")


def _dates(request):
    """Written collecting and determination dates through the G24/G29/G44 helper.

    A collecting event's single written date also fills date_visited_to (G44).
    The validator admits only the helper's exact result, so a date carries the
    relations the helper gives it.
    """
    found = {}
    events = {item.id: item for item in request.events}
    for key, kind in ((FieldKey.DATE_VISITED_FROM, EventKind.COLLECTING),
                      (FieldKey.DATE_IDENTIFIED, EventKind.DETERMINATION)):
        rows = [item for item in _assemblies(request, key) if events[item.event_id].kind == kind]
        if not rows:
            continue
        try:
            for resolution in temporal_resolutions(request, event_id=rows[0].event_id):
                found.setdefault(resolution.field_key, resolution)
        except EvidenceError as error:
            found.setdefault(key, error)
    return found


def _elevations(request):
    """The first event whose written elevations settle supplies all four endpoints,
    each exactly as the helper gives it (the validator admits nothing else)."""
    events = list(dict.fromkeys(item.event_id for item in request.assemblies
        if item.field_key in ELEVATIONS))
    error = None
    for event_id in events:
        ids = tuple(item.id for item in request.assemblies
            if item.event_id == event_id and item.field_key in ELEVATIONS)
        try:
            return {item.field_key: item for item in elevation_resolutions(
                settle_elevation(request, assembly_ids=ids))}
        except EvidenceError as failure:
            error = error or failure
    return dict.fromkeys(ELEVATIONS, error) if error else {}


def _taxon(request, results):
    rows = _assemblies(request, FieldKey.TAXON)
    if not rows:
        return None
    decided = [item for item in results if item.coverage.source_id == "gbif"
        and item.coverage.field_key == FieldKey.TAXON and item.status == LookupStatus.SUCCESS]
    for result in decided:
        for raw in result.candidate_json:
            candidate = json.loads(raw)
            if candidate.get("input_literal") != rows[0].interpreted_text:
                continue
            evidence = tuple(item.id for item in result.evidence)
            # Each cited evidence's relation is the role its evidence item declares (G23).
            return FieldResolution(field_key=FieldKey.TAXON, work_state=WorkState.RESOLVED,
                value_layer="settled",
                value=FieldValue(state=ValueState.SUPPORTED, parsed=candidate["value"],
                    normalized=candidate["value"], authority_id=candidate["authority_id"],
                    evidence_ids=list(evidence),
                    evidence_relations={item.id: item.role for item in result.evidence}),
                evidence_ids=evidence, assembly_ids=tuple(item.id for item in rows),
                event_id=rows[0].event_id,
                source_coverage=tuple(item.coverage for item in results
                    if item.coverage.field_key == FieldKey.TAXON),
                reason="G23 qualified GBIF COL XR exact match of the written taxon")
    return None


def _proposals(request, results):
    dates = _dates(request) if request.role == SpecialistRole.TEMPORAL else {}
    elevations = _elevations(request) if request.role == SpecialistRole.MEASUREMENT else {}
    proposed = {}
    for key in request.field_keys:
        try:
            if key == FieldKey.TAXON:
                proposed[key] = _taxon(request, results)
            elif key == FieldKey.IDENTIFIED_BY_IRN:
                proposed[key] = missing_irn_resolution()
            elif key == FieldKey.VERBATIM_DTS:
                rows = _assemblies(request, key)
                # The validator admits only waiting_policy for D/T/S (HARNESS rule:
                # definition and examples not supplied).
                proposed[key] = dts_policy_resolution(rows[0].interpreted_text if rows else None,
                    tuple(dict.fromkeys(eid for item in rows for eid in item.evidence_ids)))
            elif key in ELEVATIONS:
                proposed[key] = elevations.get(key)
            elif str(key).startswith("date_"):
                proposed[key] = dates.get(key)
            elif key in LITERAL_FIELDS:
                proposed[key] = _literal(request, key)
            else:
                proposed[key] = None  # Country, state, county, city: no ready source.
        except EvidenceError as error:
            proposed[key] = error
    return proposed


def _results(messages):
    """The lookup_source results of this run, and how many lookups were made."""
    found, attempted = [], 0
    for message in messages:
        if not isinstance(message, ModelRequest):
            continue
        for part in message.parts:
            if isinstance(part, (ToolReturnPart, RetryPromptPart)) and part.tool_name == "lookup_source":
                attempted += 1
            if isinstance(part, ToolReturnPart) and part.tool_name == "lookup_source":
                content = part.content
                found.append(content if isinstance(content, SourceResult) else
                    SourceResult.model_validate_json(content) if isinstance(content, str)
                    else SourceResult.model_validate(content))
    return found, attempted


def scripted_model_factory(log: list):
    """``(request, binding) -> FunctionModel``; each call appends (role, turn) to log.

    ``factory.fallbacks`` lists (role, field, reason) for every field proposed
    unfinished because no valid settled value exists; ``factory.errors`` keeps
    tracebacks from inside a model call (the gateway wrapper hides them).
    """
    fallbacks, errors = [], []

    def factory(request, binding):
        role = request.role

        def respond(messages, info):
            turn = 1 + sum(isinstance(message, ModelResponse) for message in messages)
            log.append((str(role), turn))
            try:
                results, attempted = _results(messages)
                taxon = _assemblies(request, FieldKey.TAXON)
                if FieldKey.TAXON in request.field_keys and taxon and attempted < len(TAXONOMY_SOURCES):
                    # One lookup per turn: parallel calls for one field leave the
                    # later effects held (SourceCaptureEffectsV2 sees a sibling
                    # sending effect for the same field).
                    source = TAXONOMY_SOURCES[attempted]
                    return ModelResponse(parts=[ToolCallPart("lookup_source", {"query": {
                        "source_id": source, "field_key": str(FieldKey.TAXON),
                        "query_text": taxon[0].interpreted_text}},
                        tool_call_id=f"e2e-{role.value}-lookup-{source}")], usage=USAGE)
                resolutions = []
                for key, proposal in _proposals(request, results).items():
                    reason = str(proposal) if isinstance(proposal, Exception) else "no_settled_value"
                    if isinstance(proposal, FieldResolution):
                        try:
                            resolutions.append(validate_resolution(request, proposal, tuple(results)))
                            continue
                        except EvidenceError as error:
                            reason = str(error)
                    fallbacks.append((str(role), str(key), reason))
                    resolutions.append(_waiting_source(key))
                output = SpecialistOutput(role=role, resolutions=tuple(resolutions))
                return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,
                    output.model_dump(mode="json"), tool_call_id=f"e2e-{role.value}-output")],
                    usage=USAGE)
            except Exception:
                errors.append((str(role), turn, traceback.format_exc()))
                raise

        return FunctionModel(respond)

    factory.fallbacks, factory.errors = fallbacks, errors
    return factory


def _url_key(url):
    """Scheme, host, raw path and the ordered query pairs: an exact request match."""
    parts = urlsplit(url)
    return (parts.scheme, parts.netloc, parts.path,
        tuple(parse_qsl(parts.query, keep_blank_values=True, strict_parsing=bool(parts.query))), parts.fragment)


def fixture_source_transport(log: list, directory: Path | None = None) -> FixtureSourceTransport:
    """Recorded responses by exact URL; each served URL is appended to log."""
    root = Path(directory or FIXTURES)
    manifest = json.loads((root / "sources.json").read_text())
    served = {(source, _url_key(row["url"])): (root / row["body"]).read_bytes()
        for source, row in manifest.items()}

    async def read(url, policy):
        body = served.get((policy.id, _url_key(url)))
        if body is None:
            raise AssertionError(f"unrecorded source request: {policy.id} {url}")
        log.append(url)
        return 200, body

    return FixtureSourceTransport(read)
