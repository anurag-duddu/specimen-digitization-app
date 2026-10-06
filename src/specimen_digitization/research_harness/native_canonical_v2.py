"""Additive sole V2 native writer SOURCE. Native/whole dependency tests UNRUN.

No generic save, paid retry, zero-ledger import, old-jobbase reset or pointer
repair. Receipt replay reads fresh access and immutable intent before discovery.
A retained attempt without complete native receipt is unknown and fails closed.
I4B/I4C source-policy and genuine derived projection extensions are composed
through their concrete accepted-output/native-input methods. Missing original
acceptance, retained bytes or policy proof remains an explicit HOLD.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from specimen_digitization.application.active_graph import pack
from specimen_digitization.application.domain import AuditEvent, ValueState
from specimen_digitization.application.projection import derived_id
from specimen_digitization.application.storage import check_snapshot, digest as canonical_digest

from .compatibility import PublishedResearch
from .contracts import Digest, FieldCheckpoint, FrozenRecord, ResearchScope, digest
from .native_canonical import (
    ACCESS_DENIED, CANONICAL_KEYS, RESEARCH_KEYS, CanonicalIdentityV1,
    CanonicalPolicyMaterializationV1, CanonicalProjectionServicesV1,
    CanonicalRegistrationV1, CapturedCanonicalEvidenceV1, OwnerRegistrationV1,
    SqlConnectCanonicalResearchWriter, SqlConnectNativeOperationClient,
    _projection_fields, canonical_value_v1, exact_json, fail,
)
from .publication import PreparedNativePublication, _native_checkpoint, _translate
from .native_prepack_proof_v2 import make_prepack_proof_v2, verify_prepack_proof_v2
from .publication_v2 import (
    OPERATION_V2, Positive, CanonicalSourceBasisV2, CanonicalProgressReceiptV2, NativeCausalReceiptV2,
    PreparationV2, ScientificIntentV2, chain_digest, genesis_digest,
    operation_digest, outbox_completion, scientific_basis_digest,
    verify_admission, verify_chain,
)


class CanonicalBindingV2(FrozenRecord):
    contract_version: Literal["canonical-binding/v2"]="canonical-binding/v2"
    organization_id: UUID
    collection_id: UUID
    specimen_id: UUID
    canonical: CanonicalIdentityV1
    sensitive: bool=Field(strict=True)
    registration: CanonicalRegistrationV1
    authority_digest: Digest
    import_proof_id: UUID
    import_proof_digest: Digest
    head_receipt_id: UUID | None
    head_chain_digest: Digest
    causal_chain: tuple[NativeCausalReceiptV2,...]

    @classmethod
    def from_native(cls,scope,specimen_id,row):
        if not isinstance(row,dict) or set(row)!={"canonical","registrations","snapshot","projection","active_registration_count","causal"}:
            fail("native_v2_binding_unavailable")
        canonical=row["canonical"]
        if not isinstance(canonical,dict) or set(canonical)!={"organization_id","collection_id","specimen_id","record_revision",
            "record_version_id","canonical_run_id","host_record_version_id","snapshot_sha256","sensitive"}:
            fail("native_v2_canonical_identity_unproved")
        registrations=row["registrations"];causal=row["causal"]
        if (not isinstance(registrations,list) or len(registrations)!=1
            or type(row["active_registration_count"]) is not int or row["active_registration_count"]!=1):
            fail("native_v2_registration_missing_or_ambiguous")
        if (not isinstance(causal,dict) or set(causal)!={"contract_version","authority_digest","import_proof_id","import_proof_digest",
            "head_receipt_id","head_chain_digest","causal_chain","causal_count"}
            or causal["contract_version"]!=OPERATION_V2 or type(causal["causal_count"]) is not int
            or not 0<=causal["causal_count"]<=20 or not isinstance(causal["causal_chain"],list)
            or len(causal["causal_chain"])!=causal["causal_count"]):
            fail("native_v2_causal_inventory_unproved")
        reg=CanonicalRegistrationV1.model_validate(registrations[0])
        result=cls(organization_id=canonical["organization_id"],collection_id=canonical["collection_id"],
            specimen_id=canonical["specimen_id"],sensitive=canonical["sensitive"],registration=reg,
            canonical={k:v for k,v in canonical.items() if k not in {"organization_id","collection_id","specimen_id","sensitive"}},
            **{k:v for k,v in causal.items() if k not in {"contract_version","causal_count"}})
        if (str(result.organization_id)!=scope.organization_id or str(result.collection_id)!=scope.collection_id
            or str(result.specimen_id)!=str(UUID(str(specimen_id))) or not reg.active
            or result.canonical!=reg.current_canonical or reg.publication_transition is not None):
            fail("native_v2_registration_stale")
        job=reg.job
        identity={"organization_id":scope.organization_id,"collection_id":scope.collection_id,
            "specimen_id":str(result.specimen_id),"job_id":reg.job_id}
        if (job.get("identity")!=identity or type(job.get("record_revision")) is not int
            or job["record_revision"]!=reg.base_canonical.record_revision or type(job.get("generation")) is not int
            or job["generation"]!=reg.generation or job.get("sensitive") is not result.sensitive
            or job.get("pins",{}).get("input_digest")!=reg.input_digest
            or digest(job.get("pins",{}).get("profile"))!=reg.profile_digest
            or job.get("binding_digest")!=reg.runtime_binding_digest or digest(job.get("pins"))!=reg.runtime_binding_digest
            or set(job.get("fields",{}))!=RESEARCH_KEYS):
            fail("native_v2_job_binding_invalid")
        bundle=reg.read_bundle
        if (set(bundle)!={"state_revision","server_time","job_key","job","halted","paused","effects","outbox","hold_reasons"}
            or type(bundle["state_revision"]) is not int or bundle["state_revision"]<1
            or type(bundle["server_time"]) not in {int,float} or bundle["server_time"]<=0
            or bundle["job_key"]!=reg.job_key or bundle["job"]!=job
            or type(bundle["halted"]) is not bool or bundle["paused"] is not job.get("paused")
            or not isinstance(bundle["effects"],dict) or not isinstance(bundle["outbox"],dict)
            or not isinstance(bundle["hold_reasons"],list) or len(set(bundle["hold_reasons"]))!=len(bundle["hold_reasons"])
            or not set(bundle["hold_reasons"])<={"legacy_live_import_not_confirmed","program_halted","job_paused","unknown_effect","budget_unavailable"}):
            fail("native_v2_scoped_bundle_invalid")
        for effect in bundle["effects"].values():
            if (not isinstance(effect,dict) or effect.get("job_key")!=reg.job_key
                or any(effect.get("scope",{}).get(k)!=v for k,v in identity.items())):
                fail("native_v2_scoped_bundle_invalid")
        for outbox in bundle["outbox"].values():
            if (not isinstance(outbox,dict) or outbox.get("kind")!="research_field_retry"
                or any(outbox.get("command",{}).get("scope",{}).get(k)!=v for k,v in identity.items())):
                fail("native_v2_scoped_bundle_invalid")
        # Native ancestry is complete, ordered and causal. Never choose a latest
        # row or infer publication count from CAS subtraction.
        previous=reg.base_canonical;parent=None;sha=genesis_digest(reg.binding_id,previous);seen=set();ids=set()
        scoped={**identity,"generation":reg.generation}
        for receipt in result.causal_chain:
            if (receipt.used!=previous or receipt.parent_receipt_id!=parent or receipt.parent_chain_digest!=sha
                or receipt.original_base!=reg.base_canonical or receipt.binding_id!=reg.binding_id
                or receipt.scope_identity!=scoped or receipt.job_key!=reg.job_key or receipt.program_key!=reg.program_key
                or receipt.authority_digest!=result.authority_digest or receipt.import_proof_id!=result.import_proof_id
                or receipt.import_proof_digest!=result.import_proof_digest or receipt.input_digest!=reg.input_digest
                or receipt.profile_digest!=reg.profile_digest or receipt.runtime_binding_digest!=reg.runtime_binding_digest
                or receipt.changed_field in seen or receipt.receipt_id in ids):
                fail("native_v2_full_chain_unproved")
            seen.add(receipt.changed_field);ids.add(receipt.receipt_id)
            previous=receipt.resulting;parent=receipt.receipt_id;sha=receipt.chain_digest
        if (previous!=result.canonical or parent!=result.head_receipt_id or sha!=result.head_chain_digest
            or reg.registration_revision!=(1 if not result.causal_chain else result.causal_chain[-1].after_registration_revision)):
            fail("native_v2_current_pointer_unproved")
        _projection_fields(row["projection"],result.canonical.record_version_id)
        return result


class OwnerRegistrationV2(OwnerRegistrationV1):
    publication_version: Literal["research-publication/v2"]="research-publication/v2"
    authority_digest: Digest
    import_proof_id: UUID
    import_proof_digest: Digest
    current_chain_digest: Digest

    @model_validator(mode="after")
    def genesis(self):
        if self.current_chain_digest!=genesis_digest(self.binding_id,self.base_canonical):
            fail("native_v2_owner_genesis_unproved")
        return self


class CanonicalPolicyMaterializationV2(CanonicalPolicyMaterializationV1):
    contract_version: Literal["canonical-policy-materialization/v2"]="canonical-policy-materialization/v2"
    progress_receipt: CanonicalProgressReceiptV2
    progress_receipt_digest: Digest

    @model_validator(mode="after")
    def exact_progress(self):
        progress=self.progress_receipt
        if (digest(progress)!=self.progress_receipt_digest or progress.result_digest!=self.result_digest
            or progress.policy_digest!=self.policy_digest or progress.prior_canonical!=self.prior_canonical
            or self.result.run.stage!=progress.run_stage
            or (None if self.result.run.disposition is None else str(self.result.run.disposition))!=progress.disposition
            or not set(progress.operational_reason_codes+progress.human_reason_codes)<=set(self.result.run.reasons)):
            fail("native_v2_materialized_progress_unproved")
        return self


class RetainedAttemptV2(FrozenRecord):
    id: UUID
    preparation_id: UUID
    operation_digest: Digest
    preparation_digest: Digest
    admission_digest: Digest


class RetainedIntentV2(FrozenRecord):
    original: ScientificIntentV2
    preparations: tuple[PreparationV2,...]
    attempt: RetainedAttemptV2 | None

    @model_validator(mode="after")
    def immutable_history(self):
        previous=None;seen=set()
        if len(self.preparations)>20:
            fail("native_v2_preparation_inventory_unproved")
        for ordinal,p in enumerate(self.preparations,1):
            if (p.intent_id!=self.original.id or p.ordinal!=ordinal or p.id in seen
                or p.scientific_intent_digest!=self.original.scientific_intent_digest
                or p.source_basis!=self.original.dependency_sources
                or p.authority_digest!=self.original.authority_digest or p.human_locks!=self.original.human_locks
                or p.prior_preparation_id!=(None if previous is None else previous.id)
                or p.prior_preparation_digest!=(None if previous is None else digest(previous))):
                fail("native_v2_preparation_inventory_unproved")
            seen.add(p.id);previous=p
        if self.attempt is not None:
            winners=[p for p in self.preparations if p.id==self.attempt.preparation_id]
            if (len(winners)!=1 or self.attempt.operation_digest!=self.original.operation_digest
                or self.attempt.preparation_digest!=digest(winners[0])
                or self.attempt.admission_digest!=winners[0].admission_digest):
                fail("native_v2_attempt_partial")
        return self


class NativeCanonicalResultV2(FrozenRecord):
    receipt_version: Literal["native-canonical-publication/v2"]="native-canonical-publication/v2"
    published: PublishedResearch
    causal: NativeCausalReceiptV2
    snapshot_sha256: Digest
    opaque_record_version: str=Field(min_length=1,max_length=512)
    replayed: bool=Field(strict=True)

    @model_validator(mode="after")
    def exact_result(self):
        if (self.published.record_revision!=self.causal.resulting.record_revision
            or self.snapshot_sha256!=self.causal.resulting.snapshot_sha256
            or self.opaque_record_version!=self.causal.resulting.host_record_version_id):
            fail("native_v2_result_unproved")
        return self


class RetainedPublicationLocatorV2(FrozenRecord):
    contract_version: Literal["retained-publication-locator/v2"]="retained-publication-locator/v2"
    intent_id: UUID
    original_scope: ResearchScope
    program_key: str=Field(min_length=1,max_length=300)
    idempotency_key: Digest
    request_identity_digest: Digest
    receipt_present: bool=Field(strict=True)
    attempt_present: bool=Field(strict=True)


class SqlConnectCanonicalResearchWriterV2(SqlConnectCanonicalResearchWriter):
    research_contract_version="research-publication-v2"

    async def publish_native_research(self,principal,prepared):
        # The old wrapper compares to immutable jobbase+1 and invokes mutable
        # validation before replay. It is not a V2 entrypoint or fallback.
        fail("native_v2_explicit_intent_preparation_entrypoint_required")

    async def publish_receipt_first(self,principal,prepared):
        fail("native_v2_explicit_intent_preparation_entrypoint_required")

    async def _execute(self,operation,variables,*,mutation=False):
        data=await super()._execute(operation,variables,mutation=mutation)
        aliases={"GetCanonicalResearchBindingV2":"GetCanonicalResearchBindingV1",
            "GetCanonicalResearchMaterializationInputsV2":"GetCanonicalResearchBindingV1",
            "GetResearchPublicationReceiptV2":"GetResearchPublicationReceiptV1",
            "GetResearchPublicationIntentV2":"GetResearchPublicationIntentV1"}
        if operation in aliases:
            SqlConnectNativeOperationClient._access_data(data,aliases[operation])
        return data

    async def read_current_binding(self,principal,specimen_id):
        principal=self._principal(principal,specimen_id)
        data=await self._execute("GetCanonicalResearchBindingV2",self._variables(principal,specimen_id))
        return CanonicalBindingV2.from_native(principal.scope,specimen_id,data["binding"])

    async def list_retained_publication_locators(self,principal,specimen_id):
        principal=self._principal(principal,specimen_id)
        response=await self._execute("GetRetainedResearchPublicationLocatorsV2",self._variables(principal,specimen_id))
        if not isinstance(response,dict) or set(response)!={"organizationMember","collectionMember","specimen","inventory"}:
            fail("native_v2_locator_envelope_unavailable")
        org,member,specimen=response["organizationMember"],response["collectionMember"],response["specimen"]
        if (not isinstance(org,dict) or set(org)!={"active"} or not isinstance(member,dict)
            or set(member)!={"active","role","canViewSensitive"} or not isinstance(specimen,dict)
            or set(specimen)!={"sensitive"} or type(specimen["sensitive"]) is not bool
            or type(member["canViewSensitive"]) is not bool):
            fail("native_v2_locator_access_unavailable")
        if (org["active"] is not True or member["active"] is not True or member["role"]!=principal.role
            or specimen["sensitive"] and not member["canViewSensitive"]):
            raise PermissionError("native_v2_locator_access_denied")
        inventory=response["inventory"]
        if (not isinstance(inventory,dict) or set(inventory)!={"locator_count","locators"}
            or type(inventory["locator_count"]) is not int or not 0<=inventory["locator_count"]<=20
            or not isinstance(inventory["locators"],list) or len(inventory["locators"])!=inventory["locator_count"]):
            fail("native_v2_locator_inventory_incomplete")
        result=[];ids=set();keys=set()
        fields={"contract_version","intent_id","original_scope","program_key","idempotency_key",
            "request_identity_digest","receipt_present","attempt_present"}
        for raw in inventory["locators"]:
            if (not isinstance(raw,dict) or set(raw)!=fields or not isinstance(raw["original_scope"],dict)
                or type(raw["original_scope"].get("generation")) is not int
                or raw["original_scope"].get("generation",-1)<0):
                fail("native_v2_locator_identity_unproved")
            row=RetainedPublicationLocatorV2.model_validate(raw)
            if (row.original_scope.organization_id!=principal.scope.organization_id
                or row.original_scope.collection_id!=principal.scope.collection_id
                or row.original_scope.specimen_id!=str(UUID(str(specimen_id)))
                or row.intent_id in ids or row.idempotency_key in keys):
                fail("native_v2_locator_identity_unproved")
            ids.add(row.intent_id);keys.add(row.idempotency_key);result.append(row)
        # No latest-row guess. Flags are inventory hints, never proof that a
        # winning receipt is complete or that whole20/new work has completed.
        return tuple(result)

    async def get_materialization_bundle_v2(self,principal,specimen_id,*,idempotency_key,request_identity_digest,preparation_id):
        from .native_materialization_inputs_v2 import load_materialization_v2
        return await load_materialization_v2(self,principal,specimen_id,idempotency_key=idempotency_key,
            request_identity_digest=request_identity_digest,preparation_id=preparation_id)

    async def _accepted_originals_v2(self,inputs):
        from .accepted_output import read_accepted_checkpoint_proof
        proofs={};cache={}
        job=inputs.binding.registration.job
        target=str(inputs.intent.original_prepared.basis.field_key)
        for key,pair in inputs.checkpoint_pairs.items():
            if key!=target and job["fields"][key]["work_state"] not in {"resolved","waiting_human","nonblocking_exception"}:
                continue
            native=pair["original"];binding=native.get("accepted_output_proof")
            if not isinstance(binding,dict):
                fail("native_v2_historical_accepted_output_unavailable")
            sha=binding.get("proof_digest")
            if sha not in cache:
                cache[sha]=await asyncio.to_thread(read_accepted_checkpoint_proof,
                    self.journal.store,self.journal.scope,self.blobs,native["id"])
            proof=cache[sha]
            matches=[cp for cp in proof.checkpoints if str(cp.field_key)==key]
            if (len(matches)!=1 or matches[0].model_dump(mode="json")!=native["payload"]
                or proof.acceptance.original_request.scope!=matches[0].scope
                or proof.proof_digest!=sha):
                fail("native_v2_accepted_original_checkpoint_conflict")
            # Actual request body, successful acceptance and complete checkpoint
            # transform are recovered, not reconstructed from digest preimages.
            proofs[key]=proof
        return proofs

    def _verify_capture_bindings_v2(self,prepared,binding,prior,items,accepted):
        from .canonical_evidence_provider_v2 import CapturedCanonicalEvidenceV2
        cp=prepared.publication.checkpoints[0]
        proof=accepted.get(str(cp.field_key))
        if proof is None:
            fail("canonical_v2_accepted_checkpoint_unavailable")
        expected=set(cp.resolution.evidence_ids)|set(cp.resolution.value.evidence_ids)
        if len(items)!=len(expected) or {item.evidence.id for item in items}!=expected:
            fail("canonical_captured_evidence_scope_invalid")
        receipts={receipt.effect_id:receipt for receipt in prepared.basis.receipts}
        if len(receipts)!=len(prepared.basis.receipts):
            fail("canonical_v2_capture_receipt_ambiguous")
        ids=set()
        for item in items:
            identifier=str(UUID(item.canonical_evidence.id))
            if (identifier in ids or str(item.canonical_run_id)!=prior.run.id
                or item.canonical_mapping_digest!=binding.registration.semantic_mapping_digest
                or item.source_registry_digest!=cp.source_registry_digest
                or item.canonical_region_id!=item.canonical_evidence.region_id
                or tuple(str(v) for v in item.canonical_observation_ids)!=tuple(item.canonical_evidence.observation_ids)
                or item.canonical_region_id is not None and not any(row.id==item.canonical_region_id for row in prior.run.regions)
                or any(not any(row.id==str(v) for row in prior.run.observations) for v in item.canonical_observation_ids)):
                fail("canonical_v2_capture_mapping_unproved")
            ids.add(identifier)
            if isinstance(item,CapturedCanonicalEvidenceV1):
                if (item.origin!="existing_canonical" or item.receipt is not None
                    or sum(row==item.canonical_evidence for row in prior.run.evidence)!=1
                    or item.canonical_producer is not None and sum(row==item.canonical_producer for row in prior.run.tool_calls)!=1):
                    fail("canonical_existing_evidence_unproved")
                continue
            if not isinstance(item,CapturedCanonicalEvidenceV2):
                fail("canonical_v2_captured_evidence_type_unproved")
            receipt=item.proof.receipt
            original=proof.acceptance.original_request
            tools=[tool for tool in proof.acceptance.source_results
                if tool.model_copy(update={"receipt":None})==item.source_result.model_copy(update={"receipt":None})]
            # NativeReceiptBinding deliberately has no scope. Use the actual
            # accepted ToolReceipt below and the persisted same-job effect here.
            from .canonical_evidence_provider_v2 import strict_effect_scope_v2
            effects=binding.registration.read_bundle.get("effects")
            effect=effects.get(receipt.effect_id) if isinstance(effects,dict) else None
            original_identity={key:getattr(original.scope,key) for key in
                ("organization_id","collection_id","specimen_id","job_id","generation")}
            if (not isinstance(effect,dict)
                or strict_effect_scope_v2(effect.get("scope"))!=original_identity
                or effect.get("job_key")!=prepared.basis.job_key):
                fail("canonical_v2_capture_effect_scope_unproved")
            if (len(tools)!=1 or item.original_specialist_request!=original or item.proof.original_request!=original
                or receipts.get(receipt.effect_id)!=receipt
                or receipt.effect_id not in cp.effect_receipt_ids
                or item.tool_execution.effect_id!=receipt.effect_id or item.tool_execution.attempt_id!=receipt.attempt_id
                or item.evidence not in tools[0].evidence or item.source_result.status!=tools[0].status
                or item.source_result.coverage!=tools[0].coverage):
                fail("canonical_v2_capture_original_acceptance_unproved")
            tool=tools[0].receipt
            if (tool is None or tool.scope!=original.scope or tool.effect_status!="completed"
                or tool.effect_id!=receipt.effect_id or receipt.attempt_id not in tool.attempt_ids
                or tool.request_digest!=receipt.request_digest or tool.binding_digest!=receipt.binding_digest
                or tool.binding_digest!=prepared.basis.source_binding_digest
                or tool.capture_locator!=receipt.capture.locator or tool.outcome!=item.source_result.status
                or tool.settled_micro_usd is None or tool.held_micro_usd!=0):
                fail("canonical_v2_capture_tool_receipt_unproved")
            mapping=binding.registration.semantic_mapping.get("evidence_sources",{}).get(item.evidence.source_id)
            if (not isinstance(mapping,dict) or mapping.get("policy_digest")!=item.source_policy_digest
                or mapping.get("canonical_source")!=item.canonical_evidence.source
                or item.canonical_evidence.kind!="lookup"
                or item.canonical_evidence.raw_ref!=item.proof.canonical_copy_ref
                or item.canonical_evidence.digest!=item.proof.canonical_copy_sha256
                or item.proof.original_response_fingerprint!=item.evidence.response_digest):
                fail("canonical_v2_capture_source_policy_unproved")
            # Concrete bounded provider has read the immutable original capture,
            # request/response and permitted canonical body. Native SQL rechecks
            # their retained receipt/effect identities in the same commit. This
            # consumer never refetches providers or aliases stored-object SHA to
            # a response fingerprint; each proof retains its separate identity.

    async def publish_checkpoint(self,principal,prepared,*,server_request_identity_digest):
        # The HTTP/worker supplies no policy graph. Retained original intent and
        # winning receipt are checked before current registration or preparation.
        prepared=PreparedNativePublication.model_validate(prepared.model_dump(mode="json"))
        scope=prepared.basis.scope
        principal=self._principal(principal,scope.specimen_id)
        retained=await self.read_same_operation_intent(principal,scope.specimen_id,
            prepared.basis.idempotency_key,server_request_identity_digest)
        if retained is not None:
            old=await self._read_receipt_v2(principal,retained.original,replayed=True)
            if old is not None:
                return old
            if retained.attempt is not None:
                fail("native_v2_attempt_outcome_unknown")
            intent=retained.original
        else:
            intent=await self.establish_intent(principal,prepared,
                server_request_identity_digest=server_request_identity_digest)
            retained=await self.read_same_operation_intent(principal,scope.specimen_id,
                intent.idempotency_key,server_request_identity_digest)
            if retained is None or retained.original!=intent:
                fail("native_v2_original_intent_unavailable")
        if retained.preparations and retained.preparations[-1].prepared==prepared:
            preparation=retained.preparations[-1]
        else:
            preparation=await self.append_preparation(principal,intent,prepared)
        return await self.publish_preparation(principal,intent,preparation)

    async def register_current_binding(self,principal,specimen_id,registration,*,store=None,scope=None):
        # The provisioner registers before any journal or lease exists, so it
        # passes the run's research store and scope; a journal supplies both.
        if store is None or scope is None:
            if self.journal is None:
                raise ValueError("native_v2_registration_store_and_scope_required")
            store=self.journal.store if store is None else store
            scope=self.journal.scope if scope is None else scope
        principal=self._principal(principal,specimen_id)
        if principal.role not in {"operator","reviewer","manager","admin"}:
            raise PermissionError("native_canonical_operator_required")
        registration=OwnerRegistrationV2.model_validate(registration.model_dump(mode="json"))
        document=await asyncio.to_thread(store._read,scope)
        if (scope.actor_uid!=principal.user_id or scope.specimen_id!=str(UUID(str(specimen_id)))
            or digest(document.state.get("budget_policy"))!=registration.semantic_mapping.get("journal_budget_policy_digest")):
            fail("native_v2_owner_policy_pin_unproved")
        payload={**registration.model_dump(mode="json"),"journal_budget_policy":document.state["budget_policy"],"state_revision":document.revision}
        result=await self._execute("RegisterCanonicalResearchBindingV2",{**self._variables(principal,specimen_id),"registrationJson":exact_json(payload)},mutation=True)
        if type(result.get("registered")) is not int or result["registered"]!=1:
            fail("native_v2_registration_rejected")
        return await self.read_current_binding(principal,specimen_id)

    async def read_same_operation_intent(self,principal,specimen_id,idempotency_key,request_identity_digest):
        principal=self._principal(principal,specimen_id)
        variables={**self._variables(principal,specimen_id),"idempotencyKey":idempotency_key,"requestIdentityDigest":request_identity_digest}
        data=await self._execute("GetResearchPublicationIntentV2",variables)
        row=data["intent"]
        if row is None:
            return None
        if (not isinstance(row,dict) or set(row)!={"original","preparation_count","preparations","attempt"}
            or type(row["preparation_count"]) is not int or not 0<=row["preparation_count"]<=20
            or not isinstance(row["preparations"],list) or len(row["preparations"])!=row["preparation_count"]):
            fail("native_v2_intent_partial")
        retained=RetainedIntentV2.model_validate({k:row[k] for k in ("original","preparations","attempt")})
        intent=retained.original;b=intent.original_prepared.basis;s=b.scope
        if (intent.actor_uid!=principal.user_id or s.organization_id!=principal.scope.organization_id
            or s.collection_id!=principal.scope.collection_id or s.specimen_id!=str(UUID(str(specimen_id)))
            or intent.idempotency_key!=idempotency_key or intent.server_request_identity_digest!=request_identity_digest):
            fail("native_v2_original_intent_conflict")
        return retained

    async def _read_receipt_v2(self,principal,intent,*,replayed):
        # NO mutable binding/lease/budget/discovery on this path. Winning native
        # preparation is retained, not reconstructed from whichever job is live.
        variables={**self._variables(principal,intent.original_prepared.basis.scope.specimen_id),
            "idempotencyKey":intent.idempotency_key,"operationDigest":intent.operation_digest}
        row=(await self._execute("GetResearchPublicationReceiptV2",variables))["retained"]
        if row is None:
            return None
        if not isinstance(row,dict) or set(row)!={"publication","request","snapshot","record","fields","audit","outbox","intent","preparation","causal","attempt","prepack"}:
            fail("native_v2_receipt_partial")
        if any(not isinstance(row[k],dict) for k in ("publication","request","snapshot","record","audit","outbox","intent","preparation","causal","attempt")):
            fail("native_v2_receipt_partial")
        original=ScientificIntentV2.model_validate(row["intent"])
        prep=PreparationV2.model_validate(row["preparation"])
        proof=NativeCausalReceiptV2.model_validate(row["causal"])
        attempt=RetainedAttemptV2.model_validate(row["attempt"])
        pub=row["publication"];p=prep.prepared;s=p.basis.scope
        if (original!=intent or prep.intent_id!=intent.id or proof.intent_id!=intent.id
            or proof.operation_digest!=intent.operation_digest or proof.scientific_intent_digest!=intent.scientific_intent_digest
            or proof.winning_preparation_id!=prep.id or proof.preparation_digest!=digest(prep)
            or proof.admission_digest!=prep.admission_digest or prep.source_basis!=intent.dependency_sources
            or scientific_basis_digest(p,prep.source_basis)!=intent.scientific_intent_digest
            or attempt.preparation_id!=prep.id or attempt.preparation_digest!=digest(prep)
            or attempt.operation_digest!=intent.operation_digest or attempt.admission_digest!=prep.admission_digest
            or proof.authority_digest!=intent.authority_digest or proof.import_proof_id!=intent.import_proof_id
            or proof.import_proof_digest!=intent.import_proof_digest or proof.binding_id!=intent.binding_id
            or proof.original_base!=intent.original_base or proof.actor_uid!=principal.user_id
            or proof.human_locks!=intent.human_locks or prep.human_locks!=intent.human_locks
            or proof.input_digest!=s.input_digest or proof.profile_digest!=s.profile_digest
            or proof.runtime_binding_digest!=p.basis.binding_digest
            or proof.scope_identity!={key:getattr(s,key) for key in ("organization_id","collection_id","specimen_id","job_id","generation")}):
            fail("native_v2_receipt_intent_conflict")
        expected={"id":str(proof.receipt_id),"actorUid":principal.user_id,"idempotencyKey":intent.idempotency_key,
            "operationDigest":intent.operation_digest,"preparedDigest":digest(prep),"publicationDigest":digest(p.publication),
            "specimenId":s.specimen_id,"bindingId":str(intent.binding_id),"jobId":s.job_id,"jobKey":intent.job_key,
            "generation":s.generation,"inputDigest":s.input_digest,"profileDigest":s.profile_digest,
            "runtimeBindingDigest":p.basis.binding_digest,"usedCanonicalRevision":proof.used.record_revision,
            "usedRecordVersionId":str(proof.used.record_version_id),"usedHostRecordVersionId":proof.used.host_record_version_id,
            "usedSnapshotSha256":proof.used.snapshot_sha256,"resultingCanonicalRevision":proof.resulting.record_revision,
            "nativeRecordVersionId":str(proof.resulting.record_version_id),"canonicalRunId":str(proof.resulting.canonical_run_id),
            "hostRecordVersionId":proof.resulting.host_record_version_id,"snapshotSha256":proof.resulting.snapshot_sha256,
            "projectionDigest":proof.projection_digest,"projectionCount":20,"auditId":str(proof.audit_id),"outboxId":str(proof.outbox_id),
            "policyReceiptDigest":proof.policy_receipt_digest,"lineageDigest":proof.lineage_digest,"sensitive":s.sensitive,
            "prepackProofDigest":proof.native_commit.get("prepackProofDigest")}
        if pub!=expected or pub!=proof.native_commit:
            fail("native_v2_receipt_conflict")
        request={"operation":OPERATION_V2,"actorUid":principal.user_id,"idempotencyKey":intent.idempotency_key,
            "requestSha256":intent.operation_digest,"specimenId":s.specimen_id,"revision":proof.resulting.record_revision}
        if row["request"]!=request or row["snapshot"].get("sha256")!=proof.resulting.snapshot_sha256:
            fail("native_v2_receipt_partial")
        retained=await asyncio.to_thread(self.repository._snapshot,row["snapshot"])
        if (retained.id!=s.specimen_id or retained.version!=proof.resulting.record_revision
            or retained.scope!=principal.scope or retained.run.id!=str(proof.resulting.canonical_run_id)
            or retained.asset.sensitive is not s.sensitive or canonical_digest(row["snapshot"]["snapshot"])!=proof.resulting.snapshot_sha256
            or row["record"]!={"id":str(proof.resulting.record_version_id),"runId":str(proof.resulting.canonical_run_id),"predecessorId":str(proof.used.record_version_id)}
            or row["audit"]!={"actorUid":principal.user_id,"revision":retained.version,"requestSha256":intent.operation_digest}
            or row["outbox"]!={"aggregateRevision":retained.version,"deduplicationKey":intent.operation_digest}):
            fail("native_v2_receipt_partial")
        verify_prepack_proof_v2(row["prepack"], expected_digest=pub["prepackProofDigest"],
            retained=retained, packed_snapshot=row["snapshot"]["snapshot"], progress=proof.progress_receipt,
            audit_id=proof.audit_id, actor_uid=principal.user_id, operation_digest=intent.operation_digest,
            native_record_version_id=proof.resulting.record_version_id)
        _projection_fields(row["fields"],proof.resulting.record_version_id)
        if digest(row["fields"])!=proof.projection_digest:
            fail("native_v2_receipt_projection_unproved")
        return NativeCanonicalResultV2(published=PublishedResearch(scope=s,record_revision=retained.version,
            publication_digest=digest(p.publication)),causal=proof,snapshot_sha256=proof.resulting.snapshot_sha256,
            opaque_record_version=proof.resulting.host_record_version_id,replayed=replayed)

    async def read_winning_receipt(self,principal,specimen_id,idempotency_key,request_identity_digest):
        retained=await self.read_same_operation_intent(principal,specimen_id,idempotency_key,request_identity_digest)
        if retained is None:
            fail("native_v2_original_intent_unavailable")
        result=await self._read_receipt_v2(principal,retained.original,replayed=True)
        if result is not None:
            return result
        if retained.attempt is not None:
            fail("native_v2_attempt_outcome_unknown")
        # Only the exact native absence of both marker and winning receipt is
        # unexecuted. A later authorized mutable continuation remains separate.
        return None

    async def resume_same_operation(self,principal,specimen_id,idempotency_key,request_identity_digest):
        retained=await self.read_same_operation_intent(principal,specimen_id,idempotency_key,request_identity_digest)
        if retained is None:
            fail("native_v2_original_intent_unavailable")
        result=await self._read_receipt_v2(principal,retained.original,replayed=True)
        if result is not None:
            return result
        if retained.attempt is not None:
            fail("native_v2_attempt_outcome_unknown")
        if not retained.preparations:
            fail("native_v2_preparation_unavailable")
        return await self.publish_preparation(principal,retained.original,retained.preparations[-1])

    async def _current_science(self,principal,prepared):
        # Existing immutable-capture/native-checkpoint validator, with all
        # accounting/lease/runtime/effect status checks intact. Only exact
        # current state CAS/digest may differ by separately proved V2 delta.
        current=await _translate(self.journal,prepared.basis.scope,principal,prepared.publication.checkpoints[0],
            json.loads(prepared.basis.native_guard_json),self.blobs)
        before=prepared.model_dump(mode="json");after=current.model_dump(mode="json")
        for value in (before,after):
            value["basis"].pop("state_revision");value["basis"].pop("state_digest")
        if before!=after:
            fail("native_v2_scientific_preparation_changed")
        return current

    @staticmethod
    def _source_basis(prepared,binding,raw,prior):
        fields=_projection_fields(raw["projection"],binding.canonical.record_version_id)
        sources=[];cp=prepared.publication.checkpoints[0]
        for dep in prepared.basis.dependencies:
            key=binding.registration.field_mapping[str(dep.field_key)];native=binding.registration.job["fields"][str(dep.field_key)]["checkpoint"]
            typed=FieldCheckpoint.model_validate(native["payload"]);_native_checkpoint(binding.registration.job,typed,typed.scope)
            if (native["id"]!=dep.checkpoint_id or digest(native)!=dep.checkpoint_digest
                or typed.revision!=dep.revision or digest(typed.resolution)!=dep.resolution_digest
                or fields[key]["candidateId"] is None or prior.run.fields[key].state.value!="supported"):
                fail("native_v2_source_candidate_unproved")
            scientific=cp.resolution.derivation.source_digest if cp.resolution.derivation is not None and cp.resolution.derivation.source_field==dep.field_key else None
            sources.append(CanonicalSourceBasisV2(field_key=dep.field_key,canonical_field_key=key,
                checkpoint_id=dep.checkpoint_id,checkpoint_digest=dep.checkpoint_digest,checkpoint_revision=dep.revision,
                resolution_digest=dep.resolution_digest,scientific_source_digest=scientific,
                candidate_id=fields[key]["candidateId"],source_record_version_id=binding.canonical.record_version_id,
                projection_record_version_id=binding.canonical.record_version_id,canonical_run_id=binding.canonical.canonical_run_id,
                evidence_ids=tuple(UUID(str(e)) for e in prior.run.fields[key].evidence_ids),
                lineage_digest=digest({"resolved":fields[key],"canonical_value":prior.run.fields[key].model_dump(mode="json")})))
        return tuple(sources)

    async def establish_intent(self,principal,prepared,*,server_request_identity_digest):
        """I1 verified server command supplies its immutable identity, never flags.

        This retains scientific identity only. It never prepares paid work or
        changes a canonical version. Restart must call resume_same_operation
        before mutable journal preparation. No public arbitrary payload route.
        """
        prepared=PreparedNativePublication.model_validate(prepared.model_dump(mode="json"))
        principal=self._principal(principal,prepared.basis.scope.specimen_id);s=prepared.basis.scope
        old=await self.read_same_operation_intent(principal,s.specimen_id,prepared.basis.idempotency_key,server_request_identity_digest)
        if old is not None:
            # Do not compare mutable original prepare state on restart; the exact
            # retained original is the sole basis. Mutable replacement is refused.
            if scientific_basis_digest(prepared,old.original.dependency_sources)!=old.original.scientific_intent_digest:
                fail("native_v2_changed_scientific_intent")
            return old.original
        if principal.role not in {"operator","reviewer","manager","admin"}:
            raise PermissionError("native_canonical_write_role_denied")
        await self._current_science(principal,prepared)
        raw=(await self._execute("GetCanonicalResearchBindingV2",self._variables(principal,s.specimen_id)))["binding"]
        binding=CanonicalBindingV2.from_native(principal.scope,s.specimen_id,raw);reg=binding.registration
        if binding.sensitive or binding.sensitive is not s.sensitive or reg.read_bundle["hold_reasons"]:
            fail("native_v2_authority_unavailable")
        if (reg.job_id!=s.job_id or reg.generation!=s.generation or reg.job_key!=prepared.basis.job_key
            or reg.program_key!=prepared.basis.program_key or reg.base_canonical.record_revision!=prepared.basis.expected_record_revision
            or reg.input_digest!=s.input_digest or reg.profile_digest!=s.profile_digest or reg.runtime_binding_digest!=prepared.basis.binding_digest):
            fail("native_v2_initial_basis_unproved")
        prior=await asyncio.to_thread(self.repository._snapshot,raw["snapshot"])
        sources=self._source_basis(prepared,binding,raw,prior);science=scientific_basis_digest(prepared,sources)
        intent=ScientificIntentV2(id=derived_id(OPERATION_V2,"intent",principal.user_id,prepared.basis.idempotency_key),
            actor_uid=principal.user_id,server_request_identity_digest=server_request_identity_digest,idempotency_key=prepared.basis.idempotency_key,
            operation_digest=operation_digest(principal.user_id,prepared.basis.idempotency_key,server_request_identity_digest,science),
            scientific_intent_digest=science,original_base=reg.base_canonical,binding_id=reg.binding_id,job_key=reg.job_key,
            program_key=reg.program_key,import_proof_id=binding.import_proof_id,import_proof_digest=binding.import_proof_digest,
            authority_digest=binding.authority_digest,changed_field=reg.field_mapping[str(prepared.basis.field_key)],
            human_locks=reg.human_locks,dependency_sources=sources,original_prepared=prepared)
        variables={**self._variables(principal,s.specimen_id),"intentJson":exact_json(intent.model_dump(mode="json"))}
        try:
            result=await self._execute("RetainResearchPublicationIntentV2",variables,mutation=True)
            if type(result.get("retainedIntent")) is not int or result["retainedIntent"]!=1:
                fail("native_v2_intent_rejected")
        except asyncio.CancelledError:
            raise
        except Exception:
            found=await self.read_same_operation_intent(principal,s.specimen_id,intent.idempotency_key,server_request_identity_digest)
            if found is None or found.original!=intent:
                fail("native_v2_intent_outcome_unknown")
            return found.original
        found=await self.read_same_operation_intent(principal,s.specimen_id,intent.idempotency_key,server_request_identity_digest)
        if found is None or found.original!=intent:
            fail("native_v2_intent_not_retained")
        return found.original

    async def append_preparation(self,principal,intent,prepared,*,mode="NEW_AFTER_PROGRESS"):
        intent=ScientificIntentV2.model_validate(intent.model_dump(mode="json"));s=intent.original_prepared.basis.scope
        principal=self._principal(principal,s.specimen_id)
        retained=await self.read_same_operation_intent(principal,s.specimen_id,intent.idempotency_key,intent.server_request_identity_digest)
        if retained is None or retained.original!=intent:
            fail("native_v2_original_intent_unavailable")
        # Winning receipt first, then any attempt blocks admission refresh. Native
        # refused/unknown attempts are conservatively terminal absent a separately
        # qualified protected refusal receipt. No caller 'known_failed' waiver.
        if await self._read_receipt_v2(principal,intent,replayed=True) is not None:
            fail("native_v2_operation_already_published")
        if retained.attempt is not None:
            fail("native_v2_attempt_outcome_unknown")
        prepared=PreparedNativePublication.model_validate(prepared.model_dump(mode="json"))
        await self._current_science(principal,prepared)
        raw=(await self._execute("GetCanonicalResearchBindingV2",self._variables(principal,s.specimen_id)))["binding"]
        binding=CanonicalBindingV2.from_native(principal.scope,s.specimen_id,raw);reg=binding.registration
        verify_chain(intent,intent.original_base,binding.canonical,binding.head_receipt_id,binding.head_chain_digest,binding.causal_chain)
        if reg.read_bundle["hold_reasons"] or binding.sensitive:
            fail("native_v2_authority_unavailable")
        document=await asyncio.to_thread(self.journal.store._read,self.journal.scope)
        self.journal.store._lease(document.state,self.journal.scope,self.journal.lease,document.server_time)
        if document.revision!=prepared.basis.state_revision or digest(document.state)!=prepared.basis.state_digest:
            fail("native_v2_fresh_preparation_state_unproved")
        previous=retained.preparations[-1] if retained.preparations else None
        values=dict(id=derived_id(OPERATION_V2,"preparation",str(intent.id),str(len(retained.preparations)+1),digest(prepared)),
            intent_id=intent.id,ordinal=len(retained.preparations)+1,prior_preparation_id=None if previous is None else previous.id,
            prior_preparation_digest=None if previous is None else digest(previous),mode=mode,anchor=binding.canonical,
            anchor_receipt_id=binding.head_receipt_id,anchor_chain_digest=binding.head_chain_digest,
            anchor_registration_revision=reg.registration_revision,state_revision=document.revision,state_digest=digest(document.state),
            expected_state=copy.deepcopy(document.state),source_basis=intent.dependency_sources,authority_digest=intent.authority_digest,
            human_locks=reg.human_locks,scientific_intent_digest=intent.scientific_intent_digest,prepared=prepared)
        json_values={**values,"contract_version":"research-publication-preparation/v2","id":str(values["id"]),"intent_id":str(intent.id),
            "prior_preparation_id":None if previous is None else str(previous.id),"anchor":binding.canonical.model_dump(mode="json"),
            "anchor_receipt_id":None if binding.head_receipt_id is None else str(binding.head_receipt_id),
            "source_basis":[source.model_dump(mode="json") for source in intent.dependency_sources],"prepared":prepared.model_dump(mode="json")}
        prep=PreparationV2(**json_values,admission_digest=digest(json_values))
        verify_admission(intent,prep,binding.canonical,binding.head_receipt_id,binding.head_chain_digest,binding.causal_chain,
            document.revision,document.state,reg.registration_revision,reg.job)
        payload={**prep.model_dump(mode="json"),"preparation_digest":digest(prep)}
        result=await self._execute("RetainResearchPublicationPreparationV2",{**self._variables(principal,s.specimen_id),"preparationJson":exact_json(payload)},mutation=True)
        if type(result.get("retainedPreparation")) is not int or result["retainedPreparation"]!=1:
            fail("native_v2_preparation_not_retained")
        found=await self.read_same_operation_intent(principal,s.specimen_id,intent.idempotency_key,intent.server_request_identity_digest)
        if found is None or not found.preparations or found.preparations[-1]!=prep or found.attempt is not None:
            fail("native_v2_preparation_outcome_unknown")
        return prep

    def _materialization_v2(self, principal, prepared, binding, raw, prior, materialized, *, intent, bundle, projection_services=None, captured_evidence=()):
        from .canonical_projection_v2 import project_canonical_value_v2, project_tool_input_lineage_v2
        from .canonical_evidence_provider_v2 import CapturedCanonicalEvidenceV2
        reg, result = binding.registration, materialized.result.model_copy(deep=True)
        cp = prepared.publication.checkpoints[0]
        key = reg.field_mapping[str(cp.field_key)]
        if (materialized.prepared_digest != digest(prepared) or materialized.publication_digest != digest(prepared.publication)
            or materialized.prior_canonical != binding.canonical
            or materialized.source_sha256 != reg.source_sha256
            or materialized.canonical_profile_digest != reg.canonical_profile_digest
            or materialized.research_profile_digest != reg.profile_digest
            or materialized.runtime_binding_digest != reg.runtime_binding_digest
            or materialized.semantic_mapping_digest != reg.semantic_mapping_digest or materialized.policy_digest != reg.policy_digest
            or result.id != prior.id or result.scope != prior.scope or result.asset != prior.asset
            or result.version != prior.version + 1 or result.run.id != prior.run.id
            or result.previous_runs != prior.previous_runs or result.audit != prior.audit
            or result.audit_offset != prior.audit_offset or result.history_through_revision != prior.history_through_revision
            or result.run.human_approved != prior.run.human_approved
            or set(prior.run.fields) != CANONICAL_KEYS or set(result.run.fields) != CANONICAL_KEYS
            or any(reg.human_locks[field] and result.run.fields[field] != prior.run.fields[field] for field in CANONICAL_KEYS)):
            fail("canonical_policy_materialization_invalid")
        id_map = {k:str(v) for k,v in materialized.evidence_id_mapping.items()}
        if ({item.evidence.id:str(UUID(item.canonical_evidence.id)) for item in captured_evidence} != id_map
            or set(id_map) != set(cp.resolution.evidence_ids) | set(cp.resolution.value.evidence_ids)) :
            fail("canonical_policy_evidence_mapping_invalid")
        for item in captured_evidence:
            if sum(e == item.canonical_evidence for e in result.run.evidence) != 1:
                fail("canonical_policy_evidence_body_changed")
            if item.canonical_producer is not None and sum(p == item.canonical_producer for p in result.run.tool_calls) != 1:
                fail("canonical_policy_evidence_producer_changed")
        expected_value=canonical_value_v1(cp.resolution,reg.field_mapping,id_map)
        if result.run.fields[key] != expected_value:
            fail("canonical_policy_checkpoint_value_changed")
        if any(result.run.fields[k] != prior.run.fields[k] for k in CANONICAL_KEYS - {key}):
            fail("canonical_policy_untouched_fields_changed")
        # Immutable input/readings/costs/authority history must not roll back or revive.
        allowed = {"fields", "evidence", "lookups", "tool_calls", "disposition", "disposition_summary", "reasons", "findings", "stage"}
        before, after = prior.run.model_dump(mode="json"), result.run.model_dump(mode="json")
        if {k:v for k,v in before.items() if k not in allowed} != {k:v for k,v in after.items() if k not in allowed}:
            fail("canonical_policy_immutable_history_changed")
        for name in ("evidence", "lookups", "tool_calls"):
            if after[name][:len(before[name])] != before[name]:
                fail("canonical_policy_immutable_history_changed")
        expected_policy_basis = {"publication_digest": digest(prepared.publication), "prior_canonical": binding.canonical.model_dump(mode="json"),
            "result_digest": materialized.result_digest, "policy_digest": reg.policy_digest,
            "semantic_mapping_digest": reg.semantic_mapping_digest, "exact_field_keys": sorted(CANONICAL_KEYS)}
        if any(materialized.policy_receipt.get(k) != v for k,v in expected_policy_basis.items()) or materialized.policy_receipt.get("status") != "computed":
            fail("canonical_policy_receipt_unproved")
        services = projection_services or self.projection_services or CanonicalProjectionServicesV1.from_repository(self.repository)
        services.verify()
        context=bundle.target.lineage_context
        projected=project_canonical_value_v2(principal,prior=prior,result=result,checkpoint=cp,context=context)
        tools=tuple(write for item in captured_evidence if isinstance(item,CapturedCanonicalEvidenceV2)
            for write in project_tool_input_lineage_v2(principal,prior=prior,checkpoint=cp,context=context,contribution=item))
        if (projected.lineage_digest!=materialized.lineage_digest
            or materialized.policy_receipt.get("tool_input_execution_projection_digest")!=digest([
                {"operation":w.operation,"variables":w.variables} for w in tools])):
            fail("native_v2_genuine_projection_receipt_unproved")
        ordinary=services.projector(result,services.locate,services.size,principal.user_id)
        old_projection=services.projector(prior,services.locate,services.size,principal.user_id)
        if prior.run.dependencies.get("preserved_human_fields"):
            from specimen_digitization.application.human_field_carry import adapt_projection, VerifiedHumanCarries
            verified = bundle.human_carries
            if not isinstance(verified, VerifiedHumanCarries) or not verified.matches(prior):
                fail("preserved_human_current_base_unproved")
            old_projection = adapt_projection(old_projection, prior, verified)
            # Other-field publication does not modify the protected outcomes;
            # bind the adapter separately to the actual result graph.
            result_verified = VerifiedHumanCarries(result.id, result.run.id, result.version,
                canonical_digest(result.model_dump(mode="json")), verified.outcomes)
            ordinary = adapt_projection(ordinary, result, result_verified)
        superseded={w.variables["id"] for w in ordinary
            if w.operation=="AppendFieldCandidateV2" and w.variables["fieldKey"]==key}
        # Genuine V2 maps candidate-less/derived values with the complete original
        # record; the ordinary reader/evidence/asset graph remains its producer.
        projection=[w for w in ordinary if w.operation not in {
            "AppendRecordVersionV2","AppendResolvedFieldV2","AppendValidationFindingV2"}
            and not (w.operation=="AppendFieldCandidateV2" and w.variables["fieldKey"]==key)
            and not (w.operation=="AppendCandidateEvidenceV2" and w.variables["candidateId"] in superseded)]
        projection.extend(projected.target_writes)
        projection.extend(projected.record_writes)
        projection.extend(tools)
        records = [w.variables for w in projection if w.operation == "AppendRecordVersionV2"]
        if len(records) != 1:
            fail("canonical_policy_record_projection_missing")
        record = records[0]
        record["predecessorId"] = str(binding.canonical.record_version_id)
        fields = sorted([w.variables for w in projection if w.operation == "AppendResolvedFieldV2"], key=lambda row:row["fieldKey"])
        new_fields = _projection_fields(fields, record["id"])
        old_fields = _projection_fields(raw["projection"], binding.canonical.record_version_id)
        for field in CANONICAL_KEYS - {key}:
            if any(new_fields[field][k] != old_fields[field][k] for k in ("candidateId", "state", "fieldGroup")):
                fail("canonical_policy_retained_projection_changed")
        if result.run.fields[key].state == ValueState.SUPPORTED and new_fields[key]["candidateId"] is None:
            fail("canonical_policy_supported_candidate_missing")
        old_keys = {w.key for w in old_projection}
        operation_names = {"AppendSourceAssetV2":"assets", "AppendEvidenceItemV2":"evidence", "AppendToolCallV1":"tool_calls",
            "AppendFieldCandidateV2":"candidates", "AppendFieldCandidateLineageV2":"candidates",
            "AppendCandidateEvidenceV2":"links", "AppendCandidateEvidenceLineageV2":"links", "AppendValidationFindingV2":"findings",
            "AppendCanonicalValueLineageV2":"value_lineages", "AppendCanonicalValueDependencyV2":"value_dependencies",
            "AppendCanonicalValueEvidenceV2":"value_evidence", "AppendToolInputLineageV2":"tool_input_lineage",
            "AppendCapturedToolExecutionV2":"captured_tool_executions"}
        delta = {name:[] for name in operation_names.values()}
        for write in projection:
            if write.key in old_keys or write.operation in {"AppendRecordVersionV2", "AppendResolvedFieldV2"}:
                continue
            if write.operation not in operation_names:
                fail("canonical_policy_projection_delta_unavailable")
            if write.operation in {"AppendFieldCandidateV2","AppendFieldCandidateLineageV2"} and write.variables["fieldKey"] != key:
                fail("canonical_policy_untouched_candidate_changed")
            delta[operation_names[write.operation]].append(write.variables)
        operation_digest=intent.operation_digest
        receipt_id=derived_id(OPERATION_V2,intent.actor_uid,intent.idempotency_key)
        snapshot=result.model_dump(mode="json")
        # Existing host representation is opaque to consumers. Its producer is
        # the same canonical API convention, never a UUID parser or job=run guess.
        opaque = f"{result.run.id}:{result.version}"
        receipt = {"id":receipt_id, "actorUid":principal.user_id, "idempotencyKey":prepared.basis.idempotency_key,
            "operationDigest":operation_digest, "publicationDigest":digest(prepared.publication), "preparedDigest":digest(prepared),
            "specimenId":result.id, "bindingId":str(reg.binding_id), "jobId":reg.job_id,"jobKey":reg.job_key,"generation":reg.generation,
            "inputDigest":reg.input_digest,"profileDigest":reg.profile_digest,"runtimeBindingDigest":reg.runtime_binding_digest,
            "usedCanonicalRevision":prior.version,"usedRecordVersionId":str(binding.canonical.record_version_id),
            "usedHostRecordVersionId":binding.canonical.host_record_version_id,"usedSnapshotSha256":binding.canonical.snapshot_sha256,
            "resultingCanonicalRevision":result.version,"nativeRecordVersionId":record["id"],"canonicalRunId":result.run.id,
            "hostRecordVersionId":opaque,"snapshotSha256":canonical_digest(snapshot),"projectionDigest":digest(fields),
            "projectionCount":20,"sensitive":result.asset.sensitive,
            "auditId":derived_id(receipt_id,"audit"), "outboxId":derived_id(receipt_id,"outbox"),
            "policyReceiptDigest":materialized.policy_receipt_digest, "lineageDigest":materialized.lineage_digest}
        return {"receipt":receipt, "snapshot":snapshot, "snapshot_contract":"0.1", "state":materialized.progress_receipt.wire_status,
            "record":record,"fields":fields,"prior_fields":sorted(raw["projection"],key=lambda r:r["fieldKey"]),
            "delta":delta,"changed_field":key,"registration_revision":reg.registration_revision,
            "program_key":reg.program_key,"state_revision":prepared.basis.state_revision,
            "native_guard":json.loads(prepared.basis.native_guard_json),"prepared":prepared.model_dump(mode="json"),
            "policy_materialization":materialized.model_dump(mode="json"),
            "audit_id":derived_id(receipt_id,"audit"),"outbox_id":derived_id(receipt_id,"outbox")}

    async def publish_preparation(self,principal,intent,preparation):
        intent=ScientificIntentV2.model_validate(intent.model_dump(mode="json"))
        preparation=PreparationV2.model_validate(preparation.model_dump(mode="json"));s=intent.original_prepared.basis.scope
        principal=self._principal(principal,s.specimen_id)
        # Receipt path first, INCLUDING on direct publication. A caller-supplied
        # copy cannot substitute for the actual retained native original/prep.
        retained=await self.read_same_operation_intent(principal,s.specimen_id,intent.idempotency_key,intent.server_request_identity_digest)
        if retained is None or retained.original!=intent:
            fail("native_v2_original_intent_unavailable")
        old=await self._read_receipt_v2(principal,intent,replayed=True)
        if old is not None:
            return old
        if retained.attempt is not None:
            fail("native_v2_attempt_outcome_unknown")
        if preparation not in retained.preparations or preparation!=retained.preparations[-1]:
            fail("native_v2_preparation_not_current")
        if principal.role not in {"operator","reviewer","manager","admin"}:
            raise PermissionError("native_canonical_write_role_denied")
        p=preparation.prepared
        loaded=await self.get_materialization_bundle_v2(principal,s.specimen_id,
            idempotency_key=intent.idempotency_key,request_identity_digest=intent.server_request_identity_digest,
            preparation_id=preparation.id)
        if loaded.replayed_result is not None:
            return loaded.replayed_result
        inputs=loaded.inputs
        await self._current_science(principal,p)
        raw=inputs.raw_binding
        binding=inputs.binding;reg=binding.registration
        if reg.read_bundle["hold_reasons"] or binding.sensitive or reg.human_locks!=preparation.human_locks:
            fail("native_v2_authority_or_locks_changed")
        document=await asyncio.to_thread(self.journal.store._read,self.journal.scope)
        self.journal.store._lease(document.state,self.journal.scope,self.journal.lease,document.server_time)
        if document.revision!=inputs.state_revision or document.state!=inputs.state_document:
            fail("native_v2_materialization_load_state_changed")
        verify_admission(intent,preparation,binding.canonical,binding.head_receipt_id,binding.head_chain_digest,binding.causal_chain,
            document.revision,document.state,reg.registration_revision,reg.job)
        if self.materializer is None:
            fail("canonical_policy_materializer_unavailable")
        prior=await asyncio.to_thread(self.repository._snapshot,raw["snapshot"])
        if (prior.version!=binding.canonical.record_revision or prior.run.id!=str(binding.canonical.canonical_run_id)
            or prior.asset.sha256!=reg.source_sha256 or canonical_digest(prior.run.profile_snapshot)!=reg.canonical_profile_digest):
            fail("native_v2_snapshot_binding_invalid")
        services=self.projection_services or CanonicalProjectionServicesV1.from_repository(self.repository);services.verify()
        human_carries = None
        if prior.run.dependencies.get("preserved_human_fields"):
            from specimen_digitization.application.human_field_carry import verify as verify_carries
            human_carries = await asyncio.to_thread(verify_carries, self.repository, prior, self.repository.graph_blobs)
        from .canonical_evidence_provider_v2 import CapturedCanonicalEvidenceV2
        from .canonical_materialization_v2 import NativeMaterializationInputBundleV2
        accepted=await self._accepted_originals_v2(inputs)
        if (self.evidence_provider is None
            or not callable(getattr(self.evidence_provider,"capture_native_v2",None))
            or not callable(getattr(self.materializer,"materialize_v2",None))):
            fail("canonical_v2_genuine_producer_unavailable")
        graph_bytes=None
        graph=raw["snapshot"]["snapshot"].get("active_graph")
        if graph is not None:
            if (not isinstance(graph,dict) or type(graph.get("size_bytes")) is not int
                or not 0<graph["size_bytes"]<=16*1024*1024
                or type(graph.get("blob_ref")) is not str or not graph["blob_ref"]
                or type(graph.get("sha256")) is not str or len(graph["sha256"])!=64
                or not callable(getattr(self.repository.graph_blobs,"get_bounded",None))):
                fail("canonical_v2_active_graph_read_unavailable")
            graph_bytes=await asyncio.to_thread(self.repository.graph_blobs.get_bounded,graph["blob_ref"],graph["size_bytes"])
            if (type(graph_bytes) is not bytes or len(graph_bytes)!=graph["size_bytes"]
                or hashlib.sha256(graph_bytes).hexdigest()!=graph["sha256"]):
                fail("canonical_v2_active_graph_bytes_changed")
        provided=await self.evidence_provider.capture_native_v2(principal,p,binding,prior.model_copy(deep=True),
            native_inputs=copy.deepcopy(inputs.native_inputs),accepted_checkpoint_proofs=accepted,
            projection_services=services,active_graph_bytes=graph_bytes)
        captured=[]
        for item in provided:
            if isinstance(item,CapturedCanonicalEvidenceV2):
                captured.append(CapturedCanonicalEvidenceV2.model_validate(item.model_dump(mode="json")))
            elif isinstance(item,CapturedCanonicalEvidenceV1) and item.origin=="existing_canonical":
                captured.append(CapturedCanonicalEvidenceV1.model_validate(item.model_dump(mode="json")))
            else:
                fail("canonical_v2_captured_evidence_type_unproved")
        captured=tuple(captured)
        self._verify_capture_bindings_v2(p,binding,prior,captured,accepted)
        bundle=NativeMaterializationInputBundleV2.from_native_inputs(
            native_inputs=copy.deepcopy(inputs.native_inputs),current_binding=binding,intent=intent,
            preparation=preparation,prior=prior.model_copy(deep=True),accepted_checkpoint_proofs=accepted,
            captured_tools=captured,projection_services=services,active_graph_bytes=graph_bytes,
            human_carries=human_carries)
        materialized=await self.materializer.materialize_v2(principal,p,binding,prior.model_copy(deep=True),
            bundle=bundle,prior_projection=tuple(copy.deepcopy(raw["projection"])),
            captured_evidence=captured,projection_services=services)
        materialized=CanonicalPolicyMaterializationV2.model_validate(materialized.model_dump(mode="json"))
        progress=materialized.progress_receipt
        actual_work=reg.job.get("fields")
        if (not isinstance(actual_work,dict) or set(actual_work)!=RESEARCH_KEYS
            or any(not isinstance(field,dict) or type(field.get("work_state")) is not str for field in actual_work.values())
            or progress.binding_id!=reg.binding_id or progress.job_key!=reg.job_key or progress.generation!=reg.generation
            or progress.field_work_digest!=digest(actual_work) or progress.field_mapping_digest!=digest(reg.field_mapping)
            or progress.research_field_work!={key:field["work_state"] for key,field in actual_work.items()}
            or progress.canonical_field_work!={reg.field_mapping[key]:field["work_state"] for key,field in actual_work.items()}
            or progress.target_research_field!=p.basis.field_key or progress.target_canonical_field!=intent.changed_field
            or progress.research_field_work[str(p.basis.field_key)] not in {"resolved","waiting_human","nonblocking_exception"}):
            fail("native_v2_current_whole20_progress_unproved")
        payload=self._materialization_v2(principal,p,binding,raw,prior,materialized,intent=intent,bundle=bundle,
            projection_services=services,captured_evidence=captured)
        # Explicit V2 status; never inherit lane.run_status's completed-on-any-
        # disposition convention for running/blocked progress, which has none.
        payload["state"]=progress.wire_status
        payload["materialization_input_guard"]=copy.deepcopy(inputs.guard)
        # The genuine V2 producer/context/projection are recomputed above.
        # Missing historical acceptance/capture/source-policy proof still HOLDs.
        # Rebind ONLY operation/audit identities; canonical graph/materialization
        # science/value/other19/policy/projection remain exact original producers.
        receipt=payload["receipt"];receipt_id=derived_id(OPERATION_V2,"receipt",intent.actor_uid,intent.idempotency_key)
        receipt.update(id=receipt_id,operationDigest=intent.operation_digest,preparedDigest=digest(preparation),
            auditId=derived_id(receipt_id,"audit"),outboxId=derived_id(receipt_id,"outbox"))
        result=materialized.result.model_copy(deep=True)
        result.audit.append(AuditEvent(id=receipt["auditId"],actor=principal.user_id,action="research_publication",
            reason=intent.operation_digest,before={"revision":prior.version},
            after={"revision":result.version,"record_version_id":receipt["nativeRecordVersionId"]}))
        post_audit=result.model_copy(deep=True)
        payload["snapshot"]=pack(result,self.repository.graph_blobs);check_snapshot(exact_json(payload["snapshot"]))
        prepack=make_prepack_proof_v2(materialized.result,post_audit,payload["snapshot"],progress=progress,
            audit_id=receipt["auditId"],actor_uid=principal.user_id,operation_digest=intent.operation_digest,
            native_record_version_id=receipt["nativeRecordVersionId"])
        receipt["prepackProofDigest"]=digest(prepack)
        payload["prepack_proof"]=prepack
        receipt["snapshotSha256"]=canonical_digest(payload["snapshot"])
        payload["audit_id"]=receipt["auditId"];payload["outbox_id"]=receipt["outboxId"]
        await self._current_science(principal,p)
        final=await asyncio.to_thread(self.journal.store._read,self.journal.scope)
        self.journal.store._lease(final.state,self.journal.scope,self.journal.lease,final.server_time)
        if final.revision!=document.revision or final.state!=document.state:
            fail("native_v2_materialization_state_changed")
        after=outbox_completion(final.state,p.basis.publication_outbox_key,p.basis.checkpoint_outbox_key,receipt)
        causal_values=dict(receipt_id=receipt_id,intent_id=intent.id,winning_preparation_id=preparation.id,
            operation_digest=intent.operation_digest,scientific_intent_digest=intent.scientific_intent_digest,
            preparation_digest=digest(preparation),admission_digest=preparation.admission_digest,authority_digest=intent.authority_digest,
            input_digest=s.input_digest,profile_digest=s.profile_digest,runtime_binding_digest=p.basis.binding_digest,
            actor_uid=principal.user_id,scope_identity={k:getattr(s,k) for k in ("organization_id","collection_id","specimen_id","job_id","generation")},
            binding_id=intent.binding_id,job_key=intent.job_key,program_key=intent.program_key,
            import_proof_id=intent.import_proof_id,import_proof_digest=intent.import_proof_digest,original_base=intent.original_base,
            used=binding.canonical,resulting=CanonicalIdentityV1(record_revision=result.version,record_version_id=receipt["nativeRecordVersionId"],
                canonical_run_id=result.run.id,host_record_version_id=receipt["hostRecordVersionId"],snapshot_sha256=receipt["snapshotSha256"]),
            parent_receipt_id=binding.head_receipt_id,parent_chain_digest=binding.head_chain_digest,changed_field=intent.changed_field,
            dependency_sources=intent.dependency_sources,human_locks=reg.human_locks,before_state_revision=final.revision,
            after_state_revision=final.revision+1,before_state_digest=digest(final.state),after_state_digest=digest(after),
            before_state=final.state,after_state=after,publication_outbox_key=p.basis.publication_outbox_key,
            checkpoint_outbox_key=p.basis.checkpoint_outbox_key,native_commit=receipt,before_registration_revision=reg.registration_revision,
            after_registration_revision=reg.registration_revision+1,projection_digest=receipt["projectionDigest"],projection_count=20,
            prior_projection_digest=digest(payload["prior_fields"]),policy_receipt_digest=receipt["policyReceiptDigest"],
            lineage_digest=receipt["lineageDigest"],progress_receipt=progress,progress_receipt_digest=digest(progress),
            audit_id=receipt["auditId"],outbox_id=receipt["outboxId"])
        # Chain digest does not hash full state or itself: no recursive receipt
        # inside state, no self-referential state/prepared digest.
        chain_sha=digest({"parent":binding.head_chain_digest,"receipt":receipt_id,"operation":intent.operation_digest,
            "used":binding.canonical.model_dump(mode="json"),"resulting":causal_values["resulting"].model_dump(mode="json"),
            "field":intent.changed_field,"preparation":digest(preparation),"lineage":receipt["lineageDigest"]})
        causal=NativeCausalReceiptV2(**causal_values,chain_digest=chain_sha)
        capture_scope,reuse_history=self._capture_lineage(p,binding)
        payload.update(intent_id=str(intent.id),preparation=preparation.model_dump(mode="json"),causal=causal.model_dump(mode="json"),
            causal_chain=[row.model_dump(mode="json") for row in binding.causal_chain],capture_scope=capture_scope.model_dump(mode="json"),
            reuse_history=reuse_history,state_revision=final.revision,expected_state=final.state,next_state=after,next_state_json=exact_json(after),
            dependency_checkpoint_proofs=[{"field_key":str(d.field_key),"native_checkpoint":reg.job["fields"][str(d.field_key)]["checkpoint"]}
                for d in p.basis.dependencies])
        admission={"id":derived_id(OPERATION_V2,"attempt",str(intent.id)),"intent_id":str(intent.id),
            "preparation_id":str(preparation.id),"operation_digest":intent.operation_digest,"preparation_digest":digest(preparation),
            "admission_digest":preparation.admission_digest,"state_revision":final.revision,"expected_state":final.state,
            "used_record_version_id":str(binding.canonical.record_version_id),"registration_revision":reg.registration_revision}
        # ACK of our successful insert is the only authority to issue ONE native
        # publication. Lost marker ACK/PK conflict cannot refresh or reissue it.
        try:
            marked=await self._execute("MarkResearchPublicationAttemptV2",{**self._variables(principal,s.specimen_id),"admissionJson":exact_json(admission)},mutation=True)
        except asyncio.CancelledError:
            raise
        except Exception:
            fail("native_v2_attempt_outcome_unknown")
        if type(marked.get("markedAttempt")) is not int or marked["markedAttempt"]!=1:
            fail("native_v2_attempt_outcome_unknown")
        try:
            committed=await self._execute("PublishCanonicalResearchV2",{**self._variables(principal,s.specimen_id),"commitJson":exact_json(payload)},mutation=True)
            if type(committed.get("committed")) is not int or committed["committed"]!=1:
                fail("native_v2_transaction_rejected")
        except asyncio.CancelledError:
            raise
        except Exception:
            found=await self._read_receipt_v2(principal,intent,replayed=True)
            if found is None:
                fail("native_v2_commit_outcome_unknown")
            return found
        found=await self._read_receipt_v2(principal,intent,replayed=False)
        if found is None:
            fail("native_v2_commit_receipt_missing")
        return found
