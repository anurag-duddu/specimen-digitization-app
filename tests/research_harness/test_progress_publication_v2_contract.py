"""Pure typed progress/packing boundaries; genuine native admission is separate."""
import copy
from types import SimpleNamespace

import pytest

from test_canonical_progress_materialization_v2 import progress_case, prepared, produce
from test_native_canonical_contract import basis as native_basis
from specimen_digitization.application.projection import derived_id
from specimen_digitization.research_harness.contracts import digest
from specimen_digitization.research_harness.compatibility import PublicationUnavailable
from specimen_digitization.research_harness.native_progress_writer_v2 import _payload
from specimen_digitization.research_harness.native_prepack_proof_v2 import verify_prepack_proof_v2
from specimen_digitization.research_harness.persistence import DurabilityScope
from specimen_digitization.research_harness.progress_publication_v2 import (
    ProgressOnlyReceiptV2, ProgressIntentV2, ProgressPreparationV2,
    progress_basis_digest, progress_operation_digest,
)
from specimen_digitization.research_harness.publication_v2 import NativeCausalReceiptV2, parse_causal_receipt_v2


@pytest.mark.parametrize('which', ['research_field_work','canonical_field_work'])
@pytest.mark.parametrize('state', ['pending','researching','retry_scheduled'])
def test_neither_map_can_claim_completion_for_runnable_work(progress_case, which, state):
    receipt = produce(progress_case).progress_receipt.model_dump(mode='json')
    receipt[which]['country'] = state
    with pytest.raises(PublicationUnavailable, match='native_progress_mapping_unproved'):
        ProgressOnlyReceiptV2.model_validate(receipt)


@pytest.mark.parametrize('key', ['changed_field','target_research_field','target_canonical_field','checkpoint_outbox_key'])
def test_target_free_receipt_refuses_field_or_checkpoint_placeholder(progress_case, key):
    receipt = produce(progress_case).progress_receipt.model_dump(mode='json')
    receipt[key] = 'country'
    with pytest.raises(ValueError):
        ProgressOnlyReceiptV2.model_validate(receipt)


def payload(case):
    reg = case.binding.registration
    scope = DurabilityScope(**{key:getattr(case.scope,key) for key in (
        'organization_id','collection_id','specimen_id','job_id','generation')},
        actor_uid=case.principal.user_id, sensitive=False)
    p = prepared(case)
    state = {'jobs':{reg.job_key:copy.deepcopy(reg.job)}, 'outbox':{
        p.basis.publication_outbox_key:{'kind':'canonical_publication_required','guard':p.guard,'delivered':False}}}
    p = p.model_copy(update={'basis':p.basis.model_copy(update={'state_digest':digest(state)})})
    sha = progress_basis_digest(p)
    key = digest('typed unit operation')
    identity = digest('typed unit request')
    intent = ProgressIntentV2(id=derived_id('typed unit intent'), actor_uid=case.principal.user_id,
        server_request_identity_digest=identity, idempotency_key=key,
        operation_digest=progress_operation_digest(case.principal.user_id,key,identity,sha), progress_basis_digest=sha,
        original_base=reg.base_canonical, binding_id=reg.binding_id, job_key=reg.job_key, program_key=reg.program_key,
        import_proof_id=case.binding.import_proof_id, import_proof_digest=case.binding.import_proof_digest,
        authority_digest=case.binding.authority_digest, human_locks=reg.human_locks, original_prepared=p)
    values = dict(contract_version='research-progress-preparation/v2', id=derived_id('typed unit prep'), intent_id=str(intent.id),
        ordinal=1, prior_preparation_id=None, prior_preparation_digest=None, anchor=case.binding.canonical.model_dump(mode='json'),
        anchor_receipt_id=None, anchor_chain_digest=case.binding.head_chain_digest, anchor_registration_revision=reg.registration_revision,
        state_revision=p.basis.state_revision, state_digest=digest(state), expected_state=state, authority_digest=intent.authority_digest,
        human_locks=reg.human_locks, progress_basis_digest=sha, prepared=p.model_dump(mode='json'))
    prep = ProgressPreparationV2(**values, admission_digest=digest(values))
    inputs = SimpleNamespace(raw_binding={'projection':case.rows}, state_document=state,
        state_revision=p.basis.state_revision, guard={})
    writer = SimpleNamespace(repository=SimpleNamespace(graph_blobs=None), journal=SimpleNamespace(scope=scope))
    # A pure policy test has no accepted native source authority; this invokes
    # only the payload boundary after the separately validated policy producer.
    materialized = produce(case).model_copy(update={'prepared_digest':digest(p), 'publication_digest':digest(p.publication)})
    return intent, _payload(writer,case.principal,intent,prep,case.binding,inputs,case.prior,materialized)


def test_progress_payload_copies_exact_twenty_native_candidates_and_states(progress_case):
    intent, commit = payload(progress_case)
    assert 'changed_field' not in commit and 'delta' not in commit
    assert 'checkpoint_outbox_key' not in commit['causal']
    assert 'field_key' not in commit['prepared']['basis']
    old = {row['fieldKey']:row for row in commit['prior_fields']}
    for row in commit['fields']:
        assert {key:row[key] for key in ('candidateId','state','fieldGroup')} == {
            key:old[row['fieldKey']][key] for key in ('candidateId','state','fieldGroup')}
    assert len(commit['fields']) == 20
    causal = parse_causal_receipt_v2(commit['causal'])
    with pytest.raises(ValueError):
        NativeCausalReceiptV2.model_validate(commit['causal'])
    assert causal.native_commit['operationDigest'] == intent.operation_digest
    before, after = copy.deepcopy(commit['expected_state']), copy.deepcopy(commit['next_state'])
    own = intent.original_prepared.basis.publication_outbox_key
    after['outbox'][own] = before['outbox'][own]
    assert after == before
    retained = progress_case.prior.model_validate({**commit['snapshot'],'active_graph':None})
    verify_prepack_proof_v2(commit['prepack_proof'], expected_digest=commit['receipt']['prepackProofDigest'],
        retained=retained, packed_snapshot=commit['snapshot'], progress=causal.progress_receipt,
        audit_id=causal.audit_id, actor_uid=intent.actor_uid, operation_digest=intent.operation_digest,
        native_record_version_id=causal.resulting.record_version_id)
