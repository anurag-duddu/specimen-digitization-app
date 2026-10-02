"""Meaningful strict metadata controls; native SQL lock semantics require native gates."""
import copy

import pytest
from pydantic import ValidationError

from specimen_digitization.application.domain import Run
from specimen_digitization.research_harness.native_canonical import PublicationUnavailable
from specimen_digitization.research_harness.native_materialization_inputs_v2 import _current_checkpoint
# Pytest registers fixture dependency names in the consuming module.
from test_native_canonical_v2_contract import basis_v1, causal


@pytest.mark.parametrize('bad', ['missing', None, True, False, 7, 1.0, '', 'f' * 63, 'F' * 64, 'not-a-digest'])
def test_actual_retained_checkpoint_missing_or_malformed_binding_is_typed_hold(causal, bad):
    original = copy.deepcopy(causal.job)
    before = copy.deepcopy(original)
    stored = original['fields']['country']['checkpoint']
    if bad == 'missing':
        del stored['binding_digest']
    else:
        stored['binding_digest'] = bad
    rejected = copy.deepcopy(original)
    with pytest.raises(PublicationUnavailable, match='checkpoint_binding_invalid'):
        _current_checkpoint(original, 'country', causal.p.basis.scope)
    assert original == rejected
    assert causal.job == before


def test_actual_valid_retained_checkpoint_keeps_original_and_current_proof(causal):
    original = copy.deepcopy(causal.job)
    current, pair = _current_checkpoint(original, 'country', causal.p.basis.scope)
    assert current == causal.p.publication.checkpoints[0]
    assert pair['original'] == causal.job['fields']['country']['checkpoint']
    assert pair['current'] == current.model_dump(mode='json')
    assert original == causal.job


def test_actual_well_formed_wrong_binding_remains_hold_not_coerced(causal):
    original = copy.deepcopy(causal.job)
    original['fields']['country']['checkpoint']['binding_digest'] = '0' * 64
    with pytest.raises(PublicationUnavailable, match='original_runtime_invalid'):
        _current_checkpoint(original, 'country', causal.p.basis.scope)


def test_legacy_run_false_marker_is_omitted_without_reapproving_restore():
    legacy = Run(id='legacy-run', human_approved=False)
    legacy_body = legacy.model_dump(mode='json')
    assert 'history_restore_human_locks' not in legacy_body
    restored = Run.model_validate({**legacy_body, 'history_restore_human_locks': True})
    assert restored.human_approved is False
    assert restored.model_dump(mode='json')['history_restore_human_locks'] is True
    assert Run.model_validate(restored.model_dump(mode='json')).history_restore_human_locks is True


@pytest.mark.parametrize('bad', [None, 'true', 'false', 1, 0, 1.0])
def test_restore_lock_marker_rejects_nonboolean_native_snapshot_metadata(bad):
    with pytest.raises(ValidationError):
        Run(id='restored-run', human_approved=False, history_restore_human_locks=bad)
