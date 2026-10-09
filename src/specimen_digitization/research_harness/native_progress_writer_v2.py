"""Target-free terminal progress behind the sole native canonical writer.

No model/source invocation or scientific projection occurs on this route. An
immutable attempted operation without its complete retained receipt remains held.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
from dataclasses import asdict
from uuid import UUID

from specimen_digitization.application.active_graph import pack, encoded, envelope
from specimen_digitization.application.domain import AuditEvent, FieldValue
from specimen_digitization.application.projection import _record, derived_id
from specimen_digitization.application.storage import check_snapshot, digest as graph_digest
from .contracts import ALL_FIELDS, FieldCheckpoint, FieldKey, FieldResolution, WorkState, digest
from .compatibility import PublishedResearch
from .native_canonical import CanonicalIdentityV1, CanonicalProjectionServicesV1, _projection_fields, exact_json, fail
from .native_prepack_proof_v2 import make_prepack_proof_v2, verify_prepack_proof_v2
from .progress_publication_v2 import (
    PROGRESS_OPERATION_V2, MAX_CAUSAL_RECEIPTS, MAX_PROGRESS_RECEIPTS, ProgressPublicationV2,
    ProgressBasisV2, PreparedNativeProgressV2, ProgressIntentV2, ProgressPreparationV2,
    ProgressMaterializationV2, NativeProgressCausalReceiptV2, ProgressAttemptV2, NativeProgressResultV2,
    progress_basis_digest, progress_operation_digest, progress_outbox_completion, progress_chain_digest,
)
from .publication import _runtime_pins, _receipt
from .publication_v2 import verify_chain


def _preserved_projection(fields):
    return [{k: row[k] for k in ('fieldKey', 'candidateId', 'state', 'fieldGroup')}
        for row in sorted(fields, key=lambda row: row['fieldKey'])]


def _safety(writer, principal, scope, binding, document, *, own_guard=None):
    reg = binding.registration
    writer.journal.store._lease(document.state, writer.journal.scope, writer.journal.lease, document.server_time)
    job = writer.journal.store._job(document.state, writer.journal.scope)
    _runtime_pins(job, scope)
    if (principal.role not in {'operator','reviewer','manager','admin'} or principal.user_id != scope_actor(writer) or writer.journal.scope.identity() != {
            k: getattr(scope, k) for k in ('organization_id', 'collection_id', 'specimen_id', 'job_id', 'generation')}
        or job != reg.job or document.revision != reg.read_bundle['state_revision']
        or reg.read_bundle['hold_reasons'] or reg.read_bundle['halted'] or reg.read_bundle['paused']
        or binding.sensitive or scope.sensitive or reg.human_locks != {reg.field_mapping[k]: row['locked'] for k, row in job['fields'].items()}
        or any(row['work_state'] in {'pending', 'researching', 'retry_scheduled'} for row in job['fields'].values())
        or set(job['fields']) != {str(key) for key in ALL_FIELDS}
        or len(binding.causal_chain) >= MAX_CAUSAL_RECEIPTS
        or sum(isinstance(row, NativeProgressCausalReceiptV2) for row in binding.causal_chain) >= MAX_PROGRESS_RECEIPTS):
        fail('native_progress_current_custody_unproved')
    budget = writer.journal.store._budget(document.state)
    if budget != document.state.get('budget_totals') or document.state['halted'] or document.state['budget_policy'].get('hold_reason'):
        fail('native_progress_budget_custody_unproved')
    for effect in document.state['effects'].values():
        if effect.get('job_key') == reg.job_key and (
                effect.get('status') in {'reserved', 'sending', 'held_unknown'}
                or type(effect.get('actual_micro_usd')) is not int or effect['actual_micro_usd'] < 0
                or effect.get('held_micro_usd') != 0
                or effect.get('receipt') is not None and (type(effect['receipt'].get('actual_micro_usd')) is not int
                    or effect['receipt'].get('held_micro_usd') != 0)):
            fail('native_progress_effect_custody_unproved')
    for event in document.state['outbox'].values():
        if (event.get('kind') == 'canonical_publication_required' and event.get('delivered') is False
            and event.get('guard', {}).get('scope') == writer.journal.scope.identity()
            and event.get('guard') != own_guard):
            fail('native_progress_publication_custody_unproved')
    return job


def scope_actor(writer):
    return writer.journal.scope.actor_uid


async def _accepted_all(writer, inputs):
    """Re-read actual successful acceptance for every ordinary current CP."""
    from .accepted_output import read_accepted_checkpoint_proof
    from .output_admission import is_validation_failure
    proofs, cache, receipts_seen = {}, {}, set()
    for key, pair in inputs.checkpoint_pairs.items():
        native = pair['original']; cp = FieldCheckpoint.model_validate(pair['current'])
        proof_binding = native.get('accepted_output_proof')
        if not isinstance(proof_binding, dict):
            without_context = cp.resolution.model_copy(update={'dependencies': ()})
            bare = without_context == FieldResolution(field_key=FieldKey(key), work_state=WorkState.OPERATIONAL_FAILED,
                value=FieldValue(), reason='specialist_operational_failure')
            if not bare and not is_validation_failure(without_context):
                fail('native_progress_accepted_output_unavailable')
            for pin in cp.resolution.dependencies:
                source = inputs.checkpoint_pairs.get(str(pin.field_key))
                source_cp = None if source is None else FieldCheckpoint.model_validate(source['current'])
                source_row = inputs.binding.registration.job['fields'].get(str(pin.field_key), {})
                if (source_cp is None or source_cp.revision != pin.revision or digest(source_cp.resolution) != pin.digest
                    or source_cp.resolution.work_state != WorkState.RESOLVED or source_row.get('locked') is not False
                    or not isinstance(source['original'].get('accepted_output_proof'), dict)):
                    fail('native_progress_bare_failure_dependency_unproved')
        else:
            sha = proof_binding.get('proof_digest')
            if sha not in cache:
                cache[sha] = await asyncio.to_thread(read_accepted_checkpoint_proof, writer.journal.store,
                    writer.journal.scope, writer.blobs, native['id'])
            proof = cache[sha]
            matches = [row for row in proof.checkpoints if str(row.field_key) == key]
            if (len(matches) != 1 or matches[0].model_dump(mode='json') != native['payload']
                or proof.proof_digest != sha or proof.acceptance.original_request.scope != matches[0].scope):
                fail('native_progress_accepted_checkpoint_changed')
            proofs[key] = proof
        # Every immutable consumed receipt/capture is verified, including policy
        # waits. A settled numerical cost alone cannot supply source authority.
        for effect_id in native['receipt_ids']:
            if effect_id in receipts_seen:
                continue
            effect = inputs.state_document['effects'].get(effect_id)
            if effect is None or effect.get('receipt') is None:
                fail('native_progress_effect_receipt_unavailable')
            receipt = effect['receipt']
            _receipt(effect, {'scope': effect['scope'], 'binding_digest': effect['binding_digest'],
                'attempt_id': receipt['attempt_id'], 'capture': receipt['capture']}, FieldKey(key), writer.blobs)
            receipts_seen.add(effect_id)
    return proofs


async def _graph_bytes(writer, raw):
    graph = raw['snapshot']['snapshot'].get('active_graph')
    if graph is None:
        return None
    if (not isinstance(graph, dict) or type(graph.get('size_bytes')) is not int
        or not 0 < graph['size_bytes'] <= 16*1024*1024 or not isinstance(graph.get('blob_ref'), str)
        or not callable(getattr(writer.repository.graph_blobs, 'get_bounded', None))):
        fail('native_progress_graph_reader_unavailable')
    data = await asyncio.to_thread(writer.repository.graph_blobs.get_bounded, graph['blob_ref'], graph['size_bytes'])
    if type(data) is not bytes or len(data) != graph['size_bytes'] or hashlib.sha256(data).hexdigest() != graph.get('sha256'):
        fail('native_progress_graph_bytes_changed')
    return data


async def publish_progress(writer, principal, specimen_id, *, scope):
    principal = writer._principal(principal, specimen_id)
    binding = await writer.read_current_binding(principal, specimen_id)
    reg = binding.registration
    from .native_worker import _current_progress_matches_job
    if binding.causal_chain and _current_progress_matches_job(binding, writer.journal.scope, reg.job):
        head = binding.causal_chain[-1]
        if isinstance(head, NativeProgressCausalReceiptV2):
            # Fresh access first; immutable original/receipt next. A new lease or
            # Q cannot manufacture another identical terminal progress receipt.
            retained = await writer.read_same_operation_intent(principal, specimen_id,
                head.native_commit['idempotencyKey'], digest({'contract_version':'native-progress-request/v2',
                    'scope':scope.model_dump(mode='json'), 'field_work_digest':head.progress_receipt.field_work_digest,
                    'anchor':head.used.model_dump(mode='json')}))
            if retained is None:
                fail('native_progress_retained_operation_unavailable')
            return await read_progress_receipt(writer, principal, retained.original, replayed=True)
        fail('native_progress_current_receipt_already_proved')
    document = await asyncio.to_thread(writer.journal.store._read, writer.journal.scope)
    pending = [event['guard'] for event in document.state['outbox'].values()
        if event.get('kind') == 'canonical_publication_required' and event.get('delivered') is False
        and event.get('guard', {}).get('operation_kind') == 'progress_only'
        and event['guard'].get('scope') == writer.journal.scope.identity()]
    if len(pending) > 1:
        fail('native_progress_operation_ambiguous')
    if pending:
        guard = pending[0]
        return await writer.resume_same_operation(principal, specimen_id, guard['idempotency_key'], guard['request_identity_digest'])
    _safety(writer, principal, scope, binding, document)
    raw = (await writer._execute('GetCanonicalResearchBindingV2', writer._variables(principal, specimen_id)))['binding']
    prior = await asyncio.to_thread(writer.repository._snapshot, raw['snapshot'])
    if prior.run.human_approved or prior.run.history_restore_human_locks or prior.run.stage in {'paused','cancelled'}:
        fail('native_progress_human_decision_locked')
    if prior.version != binding.canonical.record_revision or prior.run.id != str(binding.canonical.canonical_run_id):
        fail('native_progress_current_snapshot_changed')
    identity = digest({'contract_version':'native-progress-request/v2', 'scope':scope.model_dump(mode='json'),
        'field_work_digest':digest(reg.job['fields']), 'anchor':binding.canonical.model_dump(mode='json')})
    guard = {'operation_kind':'progress_only', 'scope':writer.journal.scope.identity(), 'lease':asdict(writer.journal.lease),
        'binding_digest':reg.runtime_binding_digest, 'field_work_digest':digest(reg.job['fields']),
        'field_mapping_digest':digest(reg.field_mapping), 'policy_digest':reg.policy_digest,
        'canonical_anchor':binding.canonical.model_dump(mode='json'), 'request_identity_digest':identity}
    guard['idempotency_key'] = digest({'operation':PROGRESS_OPERATION_V2, **guard})
    key = 'publish-progress/' + guard['idempotency_key']
    def retain(state, now):
        writer.journal.store._lease(state, writer.journal.scope, writer.journal.lease, now)
        if state != document.state:
            fail('native_progress_prepare_state_changed')
        state['outbox'][key] = {'kind':'canonical_publication_required', 'guard':copy.deepcopy(guard), 'delivered':False}
    await asyncio.to_thread(writer.journal.store._mutate, writer.journal.scope, retain, lease=writer.journal.lease)
    binding = await writer.read_current_binding(principal, specimen_id)
    document = await asyncio.to_thread(writer.journal.store._read, writer.journal.scope)
    _safety(writer, principal, scope, binding, document, own_guard=guard)
    prepared = PreparedNativeProgressV2(basis=ProgressBasisV2(scope=scope, actor_uid=principal.user_id,
        job_key=reg.job_key, program_key=reg.program_key, binding_digest=reg.runtime_binding_digest,
        pins_digest=digest(reg.job['pins']), field_work_digest=guard['field_work_digest'], field_mapping_digest=guard['field_mapping_digest'],
        policy_digest=reg.policy_digest, human_locks=reg.human_locks, expected_record_revision=binding.canonical.record_revision,
        lease=writer.journal.lease, state_revision=document.revision, state_digest=digest(document.state),
        publication_outbox_key=key, native_guard_digest=digest(guard)),
        publication=ProgressPublicationV2(scope=scope, field_work_digest=guard['field_work_digest'],
            field_mapping_digest=guard['field_mapping_digest'], canonical_anchor=binding.canonical), guard=guard)
    basis_sha = progress_basis_digest(prepared)
    intent = ProgressIntentV2(id=derived_id(PROGRESS_OPERATION_V2, 'intent', principal.user_id, guard['idempotency_key']),
        actor_uid=principal.user_id, server_request_identity_digest=identity, idempotency_key=guard['idempotency_key'],
        operation_digest=progress_operation_digest(principal.user_id, guard['idempotency_key'], identity, basis_sha),
        progress_basis_digest=basis_sha, original_base=reg.base_canonical, binding_id=reg.binding_id, job_key=reg.job_key,
        program_key=reg.program_key, import_proof_id=binding.import_proof_id, import_proof_digest=binding.import_proof_digest,
        authority_digest=binding.authority_digest, human_locks=reg.human_locks, original_prepared=prepared)
    verify_chain(intent, intent.original_base, binding.canonical, binding.head_receipt_id, binding.head_chain_digest, binding.causal_chain)
    values = dict(contract_version='research-progress-preparation/v2', id=derived_id(PROGRESS_OPERATION_V2, 'preparation', str(intent.id), '1', digest(prepared)),
        intent_id=str(intent.id), ordinal=1, prior_preparation_id=None, prior_preparation_digest=None,
        anchor=binding.canonical.model_dump(mode='json'), anchor_receipt_id=None if binding.head_receipt_id is None else str(binding.head_receipt_id),
        anchor_chain_digest=binding.head_chain_digest, anchor_registration_revision=reg.registration_revision,
        state_revision=document.revision, state_digest=digest(document.state), expected_state=copy.deepcopy(document.state),
        authority_digest=intent.authority_digest, human_locks=reg.human_locks, progress_basis_digest=basis_sha,
        prepared=prepared.model_dump(mode='json'))
    prep = ProgressPreparationV2(**values, admission_digest=digest(values))
    for operation, variable, payload, count in (
        ('RetainResearchProgressIntentV2','intentJson',intent.model_dump(mode='json'),'retainedIntent'),
        ('RetainResearchProgressPreparationV2','preparationJson',{**prep.model_dump(mode='json'),'preparation_digest':digest(prep)},'retainedPreparation')):
        try:
            response = await writer._execute(operation, {**writer._variables(principal, specimen_id), variable:exact_json(payload)}, mutation=True)
        except asyncio.CancelledError:
            raise
        except Exception:
            fail('native_progress_retention_outcome_unknown')
        if type(response.get(count)) is not int or response[count] != 1:
            fail('native_progress_retention_rejected')
    return await publish_progress_preparation(writer, principal, intent, prep)


async def publish_progress_preparation(writer, principal, intent, preparation):
    intent = ProgressIntentV2.model_validate(intent.model_dump(mode='json'))
    preparation = ProgressPreparationV2.model_validate(preparation.model_dump(mode='json'))
    scope = intent.original_prepared.basis.scope
    principal = writer._principal(principal, scope.specimen_id)
    retained = await writer.read_same_operation_intent(principal, scope.specimen_id, intent.idempotency_key, intent.server_request_identity_digest)
    if retained is None or retained.original != intent:
        fail('native_progress_original_intent_unavailable')
    winner = await read_progress_receipt(writer, principal, intent, replayed=True)
    if winner is not None:
        return winner
    if retained.attempt is not None:
        fail('native_progress_attempt_outcome_unknown')
    if not retained.preparations or retained.preparations[-1] != preparation:
        fail('native_progress_preparation_not_current')
    loaded = await writer.get_materialization_bundle_v2(principal, scope.specimen_id, idempotency_key=intent.idempotency_key,
        request_identity_digest=intent.server_request_identity_digest, preparation_id=preparation.id)
    if loaded.replayed_result is not None:
        return loaded.replayed_result
    inputs = loaded.inputs; binding = inputs.binding; reg = binding.registration; prepared = preparation.prepared
    document = await asyncio.to_thread(writer.journal.store._read, writer.journal.scope)
    _safety(writer, principal, scope, binding, document, own_guard=prepared.guard)
    verify_chain(intent, intent.original_base, binding.canonical, binding.head_receipt_id, binding.head_chain_digest, binding.causal_chain)
    if (document.state != inputs.state_document or document.revision != inputs.state_revision
        or document.state != preparation.expected_state or document.revision != preparation.state_revision
        or binding.canonical != preparation.anchor or binding.head_receipt_id != preparation.anchor_receipt_id
        or binding.head_chain_digest != preparation.anchor_chain_digest or reg.registration_revision != preparation.anchor_registration_revision
        or reg.human_locks != preparation.human_locks or reg.policy_digest != prepared.basis.policy_digest
        or digest(reg.job['fields']) != prepared.basis.field_work_digest
        or document.state['outbox'].get(prepared.basis.publication_outbox_key) != {
            'kind':'canonical_publication_required', 'guard':prepared.guard, 'delivered':False}):
        fail('native_progress_admission_changed')
    prior = await asyncio.to_thread(writer.repository._snapshot, inputs.raw_binding['snapshot'])
    if prior.run.human_approved or prior.run.history_restore_human_locks or prior.run.stage in {'paused','cancelled'}:
        fail('native_progress_human_decision_locked')
    services = writer.projection_services or CanonicalProjectionServicesV1.from_repository(writer.repository)
    services.verify()
    carries = None
    if prior.run.dependencies.get('preserved_human_fields'):
        from specimen_digitization.application.human_field_carry import verify
        carries = await asyncio.to_thread(verify, writer.repository, prior, writer.repository.graph_blobs)
    accepted = await _accepted_all(writer, inputs)
    from .native_materialization_context_v2 import NativeMaterializationInputBundleV2
    bundle = NativeMaterializationInputBundleV2.from_native_inputs(native_inputs=copy.deepcopy(inputs.native_inputs),
        current_binding=binding, intent=intent, preparation=preparation, prior=prior.model_copy(deep=True),
        accepted_checkpoint_proofs=accepted, projection_services=services,
        active_graph_bytes=await _graph_bytes(writer, inputs.raw_binding), human_carries=carries)
    from .canonical_progress_materialization_v2 import CanonicalProgressMaterializerV2
    if writer.materializer is None or not hasattr(writer.materializer, 'policy'):
        fail('native_progress_policy_materializer_unavailable')
    materialized = await CanonicalProgressMaterializerV2(writer.materializer.policy).materialize_progress_v2(principal,
        prepared, binding, prior.model_copy(deep=True), terminal_contexts=bundle.terminal_contexts,
        prior_projection=tuple(copy.deepcopy(inputs.raw_binding['projection'])), human_carries=carries,
        native_prior_snapshot=bundle.native_prior_snapshot)
    materialized = ProgressMaterializationV2.model_validate(materialized.model_dump(mode='json'))
    payload = _payload(writer, principal, intent, preparation, binding, inputs, prior, materialized)
    final = await asyncio.to_thread(writer.journal.store._read, writer.journal.scope)
    _safety(writer, principal, scope, binding, final, own_guard=prepared.guard)
    if final.revision != document.revision or final.state != document.state:
        fail('native_progress_materialization_state_changed')
    admission = {'id':derived_id(PROGRESS_OPERATION_V2,'attempt',str(intent.id)), 'intent_id':str(intent.id),
        'preparation_id':str(preparation.id), 'operation_digest':intent.operation_digest, 'preparation_digest':digest(preparation),
        'admission_digest':preparation.admission_digest, 'state_revision':final.revision, 'expected_state':final.state,
        'used_record_version_id':str(binding.canonical.record_version_id), 'registration_revision':reg.registration_revision}
    try:
        marked = await writer._execute('MarkResearchProgressAttemptV2', {**writer._variables(principal, scope.specimen_id),
            'admissionJson':exact_json(admission)}, mutation=True)
    except asyncio.CancelledError:
        raise
    except Exception:
        fail('native_progress_attempt_outcome_unknown')
    if type(marked.get('markedAttempt')) is not int or marked['markedAttempt'] != 1:
        fail('native_progress_attempt_outcome_unknown')
    try:
        committed = await writer._execute('PublishCanonicalResearchProgressV2', {**writer._variables(principal, scope.specimen_id),
            'commitJson':exact_json(payload)}, mutation=True)
        if type(committed.get('committed')) is not int or committed['committed'] != 1:
            fail('native_progress_transaction_rejected')
    except asyncio.CancelledError:
        raise
    except Exception:
        winner = await read_progress_receipt(writer, principal, intent, replayed=True)
        if winner is None:
            fail('native_progress_commit_outcome_unknown')
        return winner
    winner = await read_progress_receipt(writer, principal, intent, replayed=False)
    if winner is None:
        fail('native_progress_commit_receipt_missing')
    return winner


def _payload(writer, principal, intent, prep, binding, inputs, prior, materialized):
    from specimen_digitization.application.storage import canonical_json
    reg, result = binding.registration, materialized.result.model_copy(deep=True)
    old = sorted(copy.deepcopy(inputs.raw_binding['projection']), key=lambda row:row['fieldKey'])
    _projection_fields(old, binding.canonical.record_version_id)
    receipt_id = derived_id(PROGRESS_OPERATION_V2,'receipt',intent.actor_uid,intent.idempotency_key)
    record_id = derived_id(receipt_id,'record')
    candidates = {row['fieldKey']:row['candidateId'] for row in old}
    writes = _record(result.run, candidates, set())
    records = [copy.deepcopy(row.variables) for row in writes if row.operation == 'AppendRecordVersionV2']
    if len(records) != 1:
        fail('native_progress_record_projection_unavailable')
    record = records[0]; record.update(id=record_id, predecessorId=str(binding.canonical.record_version_id))
    fields = [{**row, 'id':derived_id(record_id,'field',row['fieldKey']), 'recordVersionId':record_id} for row in old]
    findings = [{**copy.deepcopy(row.variables), 'id':derived_id(record_id,'finding',digest(row.variables)),
        'recordVersionId':record_id} for row in writes if row.operation == 'AppendValidationFindingV2']
    if _preserved_projection(fields) != _preserved_projection(old):
        fail('native_progress_scientific_projection_changed')
    progress = materialized.progress_receipt
    receipt = {'id':receipt_id, 'actorUid':principal.user_id, 'idempotencyKey':intent.idempotency_key,
        'operationDigest':intent.operation_digest, 'publicationDigest':digest(prep.prepared.publication), 'preparedDigest':digest(prep),
        'specimenId':result.id, 'bindingId':str(reg.binding_id), 'jobId':reg.job_id, 'jobKey':reg.job_key, 'generation':reg.generation,
        'inputDigest':reg.input_digest, 'profileDigest':reg.profile_digest, 'runtimeBindingDigest':reg.runtime_binding_digest,
        'usedCanonicalRevision':prior.version, 'usedRecordVersionId':str(binding.canonical.record_version_id),
        'usedHostRecordVersionId':binding.canonical.host_record_version_id, 'usedSnapshotSha256':binding.canonical.snapshot_sha256,
        'resultingCanonicalRevision':result.version, 'nativeRecordVersionId':record_id, 'canonicalRunId':result.run.id,
        'hostRecordVersionId':f'{result.run.id}:{result.version}', 'snapshotSha256':'', 'projectionDigest':digest(fields),
        'projectionCount':20, 'sensitive':False, 'auditId':derived_id(receipt_id,'audit'), 'outboxId':derived_id(receipt_id,'outbox'),
        'policyReceiptDigest':materialized.policy_receipt_digest, 'lineageDigest':materialized.lineage_digest}
    result.audit.append(AuditEvent(id=receipt['auditId'], actor=principal.user_id, action='research_publication',
        reason=intent.operation_digest, before={'revision':prior.version}, after={'revision':result.version,'record_version_id':record_id}))
    post_audit = result.model_copy(deep=True)
    snapshot = pack(result, writer.repository.graph_blobs); check_snapshot(exact_json(snapshot))
    prepack = make_prepack_proof_v2(materialized.result, post_audit, snapshot, progress=progress,
        audit_id=receipt['auditId'], actor_uid=principal.user_id, operation_digest=intent.operation_digest, native_record_version_id=record_id)
    receipt['prepackProofDigest'] = digest(prepack); receipt['snapshotSha256'] = graph_digest(snapshot)
    after = progress_outbox_completion(inputs.state_document, prep.prepared.basis.publication_outbox_key, receipt)
    values = dict(receipt_id=receipt_id, intent_id=intent.id, winning_preparation_id=prep.id,
        operation_digest=intent.operation_digest, progress_basis_digest=intent.progress_basis_digest,
        preparation_digest=digest(prep), admission_digest=prep.admission_digest, authority_digest=intent.authority_digest,
        input_digest=reg.input_digest, profile_digest=reg.profile_digest, runtime_binding_digest=reg.runtime_binding_digest,
        actor_uid=principal.user_id, scope_identity=writer.journal.scope.identity(), binding_id=reg.binding_id,
        job_key=reg.job_key, program_key=reg.program_key, import_proof_id=intent.import_proof_id,
        import_proof_digest=intent.import_proof_digest, original_base=intent.original_base, used=binding.canonical,
        resulting=CanonicalIdentityV1(record_revision=result.version, record_version_id=record_id, canonical_run_id=result.run.id,
            host_record_version_id=receipt['hostRecordVersionId'], snapshot_sha256=receipt['snapshotSha256']),
        parent_receipt_id=binding.head_receipt_id, parent_chain_digest=binding.head_chain_digest,
        human_locks=reg.human_locks, before_state_revision=inputs.state_revision, after_state_revision=inputs.state_revision+1,
        before_state_digest=digest(inputs.state_document), after_state_digest=digest(after),
        before_state=inputs.state_document, after_state=after, publication_outbox_key=prep.prepared.basis.publication_outbox_key,
        native_commit=receipt, before_registration_revision=reg.registration_revision, after_registration_revision=reg.registration_revision+1,
        projection_digest=receipt['projectionDigest'], prior_projection_digest=digest(old),
        preserved_projection_digest=digest(_preserved_projection(old)), projection_count=20,
        policy_receipt_digest=receipt['policyReceiptDigest'], lineage_digest=receipt['lineageDigest'],
        progress_receipt=progress, progress_receipt_digest=digest(progress), audit_id=receipt['auditId'], outbox_id=receipt['outboxId'])
    # Calculate the nonrecursive tagged chain recipe before strict validation.
    from types import SimpleNamespace
    causal = NativeProgressCausalReceiptV2(**values, chain_digest=progress_chain_digest(SimpleNamespace(**values)))
    return {'receipt':receipt, 'snapshot':snapshot, 'snapshot_contract':'0.1', 'state':progress.wire_status,
        'record':record, 'fields':fields, 'prior_fields':old, 'findings':findings,
        'registration_revision':reg.registration_revision, 'program_key':reg.program_key, 'state_revision':inputs.state_revision,
        'native_guard':prep.prepared.guard, 'prepared':prep.prepared.model_dump(mode='json'),
        'policy_materialization':materialized.model_dump(mode='json'), 'audit_id':receipt['auditId'], 'outbox_id':receipt['outboxId'],
        'prepack_proof':prepack, 'materialization_input_guard':copy.deepcopy(inputs.guard), 'intent_id':str(intent.id),
        'preparation':prep.model_dump(mode='json'), 'causal':causal.model_dump(mode='json'),
        'causal_chain':[row.model_dump(mode='json') for row in binding.causal_chain], 'expected_state':inputs.state_document,
        'next_state':after, 'next_state_json':exact_json(after), 'prior_graph_json':canonical_json(prior.model_dump(mode='json')),
        'prior_run_json':canonical_json(prior.run.model_dump(mode='json')), 'snapshot_json':canonical_json(snapshot),
        'field_work_json':exact_json(reg.job['fields']), 'field_mapping_json':exact_json(reg.field_mapping),
        'pins_json':exact_json(reg.job['pins']), 'post_run_json':canonical_json(result.run.model_dump(mode='json')),
        'post_graph_envelope_json':encoded(envelope(result)).decode() if snapshot.get('active_graph') is not None else None}


async def read_progress_receipt(writer, principal, intent, *, replayed):
    intent = ProgressIntentV2.model_validate(intent.model_dump(mode='json'))
    scope = intent.original_prepared.basis.scope
    response = await writer._execute('GetResearchPublicationReceiptV2', {**writer._variables(principal, scope.specimen_id),
        'idempotencyKey':intent.idempotency_key, 'operationDigest':intent.operation_digest})
    row = response['retained']
    if row is None:
        return None
    if (not isinstance(row, dict) or set(row) != {'publication','request','snapshot','record','fields','audit','outbox','intent','preparation','causal','attempt','prepack'}):
        fail('native_progress_receipt_partial')
    original = ProgressIntentV2.model_validate(row['intent'])
    prep = ProgressPreparationV2.model_validate(row['preparation'])
    causal = NativeProgressCausalReceiptV2.model_validate(row['causal'])
    attempt = ProgressAttemptV2.model_validate(row['attempt'])
    pub = row['publication']
    if (original != intent or prep.intent_id != intent.id or causal.intent_id != intent.id
        or causal.operation_digest != intent.operation_digest or causal.progress_basis_digest != intent.progress_basis_digest
        or prep.progress_basis_digest != intent.progress_basis_digest or progress_basis_digest(prep.prepared) != intent.progress_basis_digest
        or causal.winning_preparation_id != prep.id or causal.preparation_digest != digest(prep)
        or causal.admission_digest != prep.admission_digest or causal.used != prep.anchor
        or causal.parent_receipt_id != prep.anchor_receipt_id or causal.parent_chain_digest != prep.anchor_chain_digest
        or causal.before_state != prep.expected_state or causal.before_state_revision != prep.state_revision
        or attempt.preparation_id != prep.id or attempt.preparation_digest != digest(prep)
        or attempt.operation_digest != intent.operation_digest or attempt.admission_digest != prep.admission_digest
        or causal.authority_digest != intent.authority_digest or causal.import_proof_id != intent.import_proof_id
        or causal.import_proof_digest != intent.import_proof_digest or causal.binding_id != intent.binding_id
        or causal.original_base != intent.original_base or causal.actor_uid != principal.user_id
        or causal.human_locks != intent.human_locks or prep.human_locks != intent.human_locks
        or causal.input_digest != scope.input_digest or causal.profile_digest != scope.profile_digest
        or causal.runtime_binding_digest != prep.prepared.basis.binding_digest
        or causal.scope_identity != {key:getattr(scope,key) for key in ('organization_id','collection_id','specimen_id','job_id','generation')}):
        fail('native_progress_receipt_intent_conflict')
    expected = {'id':str(causal.receipt_id), 'actorUid':principal.user_id, 'idempotencyKey':intent.idempotency_key,
        'operationDigest':intent.operation_digest, 'preparedDigest':digest(prep), 'publicationDigest':digest(prep.prepared.publication),
        'specimenId':scope.specimen_id, 'bindingId':str(intent.binding_id), 'jobId':scope.job_id, 'jobKey':intent.job_key,
        'generation':scope.generation, 'inputDigest':scope.input_digest, 'profileDigest':scope.profile_digest,
        'runtimeBindingDigest':prep.prepared.basis.binding_digest, 'usedCanonicalRevision':causal.used.record_revision,
        'usedRecordVersionId':str(causal.used.record_version_id), 'usedHostRecordVersionId':causal.used.host_record_version_id,
        'usedSnapshotSha256':causal.used.snapshot_sha256, 'resultingCanonicalRevision':causal.resulting.record_revision,
        'nativeRecordVersionId':str(causal.resulting.record_version_id), 'canonicalRunId':str(causal.resulting.canonical_run_id),
        'hostRecordVersionId':causal.resulting.host_record_version_id, 'snapshotSha256':causal.resulting.snapshot_sha256,
        'projectionDigest':causal.projection_digest, 'projectionCount':20, 'auditId':str(causal.audit_id), 'outboxId':str(causal.outbox_id),
        'policyReceiptDigest':causal.policy_receipt_digest, 'lineageDigest':causal.lineage_digest, 'sensitive':scope.sensitive,
        'prepackProofDigest':causal.native_commit.get('prepackProofDigest')}
    if pub != expected or pub != causal.native_commit:
        fail('native_progress_receipt_metadata_changed')
    request = {'operation':PROGRESS_OPERATION_V2, 'actorUid':principal.user_id, 'idempotencyKey':intent.idempotency_key,
        'requestSha256':intent.operation_digest, 'specimenId':scope.specimen_id, 'revision':causal.resulting.record_revision}
    retained = await asyncio.to_thread(writer.repository._snapshot, row['snapshot'])
    if (row['request'] != request or row['snapshot'].get('sha256') != causal.resulting.snapshot_sha256
        or graph_digest(row['snapshot']['snapshot']) != causal.resulting.snapshot_sha256
        or retained.id != scope.specimen_id or retained.scope != principal.scope or retained.version != causal.resulting.record_revision
        or retained.run.id != str(causal.resulting.canonical_run_id) or retained.asset.sensitive is not scope.sensitive
        or row['record'] != {'id':str(causal.resulting.record_version_id), 'runId':str(causal.resulting.canonical_run_id),
            'predecessorId':str(causal.used.record_version_id)}
        or row['audit'] != {'actorUid':principal.user_id, 'revision':retained.version, 'requestSha256':intent.operation_digest}
        or row['outbox'] != {'aggregateRevision':retained.version, 'deduplicationKey':intent.operation_digest}):
        fail('native_progress_receipt_partial')
    verify_prepack_proof_v2(row['prepack'], expected_digest=pub['prepackProofDigest'], retained=retained,
        packed_snapshot=row['snapshot']['snapshot'], progress=causal.progress_receipt,
        audit_id=causal.audit_id, actor_uid=principal.user_id, operation_digest=intent.operation_digest,
        native_record_version_id=causal.resulting.record_version_id)
    _projection_fields(row['fields'], causal.resulting.record_version_id)
    if digest(row['fields']) != causal.projection_digest or digest(_preserved_projection(row['fields'])) != causal.preserved_projection_digest:
        fail('native_progress_receipt_projection_changed')
    return NativeProgressResultV2(published=PublishedResearch(scope=scope,record_revision=retained.version,
        publication_digest=digest(prep.prepared.publication)), causal=causal, snapshot_sha256=causal.resulting.snapshot_sha256,
        opaque_record_version=causal.resulting.host_record_version_id, replayed=replayed)
