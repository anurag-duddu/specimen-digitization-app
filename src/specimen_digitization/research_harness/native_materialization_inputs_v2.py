"""Authoritative private V2 materialization loader.

Only a fresh SQL response enters this module. It does not create an import,
ledger, request preimage, selected reader, price proof or original SDK output.
The live program state is verified privately here. This server-only DTO must
never be returned by public discovery/thread/output routes. Immutable retained
preparation/intent proofs also contain their native CAS state preimages.
"""
from __future__ import annotations

import copy
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping
from uuid import UUID

from specimen_digitization.application.storage import digest as graph_digest

from .contracts import FieldCheckpoint, digest
from .native_canonical import CANONICAL_KEYS, RESEARCH_KEYS, fail

OUTER = frozenset({'organizationMember', 'collectionMember', 'specimen', 'binding'})
OLD_BINDING = frozenset({'canonical', 'registrations', 'snapshot', 'projection', 'active_registration_count', 'causal'})
INPUT_KEYS = frozenset({'contract_version', 'observed_at', 'registration', 'outer_intent',
    'scoped_state', 'private_state_integrity', 'current_snapshot', 'preparation_snapshot',
    'retained_history', 'projection_rows', 'checkpoint_inputs', 'original_request_sources',
    'captured_executions', 'native_input_rows', 'lineage_rows', 'prepack_proof'})
INPUT_VERSION = 'research-native-materialization-inputs/v2'
MAX_JSON = 32 * 1024 * 1024
MAX_ROWS = 4096
MAX_INT64 = 9223372036854775807


def exact_object(value: Any, keys: set[str] | frozenset[str], code: str) -> dict:
    if type(value) is not dict or set(value) != keys:
        fail(code)
    return value


def strict_int(value: Any, *, minimum=0, maximum=MAX_INT64) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        fail('native_materialization_integer_invalid')
    return value


def int64_decimal(value: Any) -> int:
    """The new query deliberately emits canonical decimal strings, not Any numbers."""
    if type(value) is not str or re.fullmatch(r'0|[1-9][0-9]{0,18}', value) is None:
        fail('native_materialization_int64_wire_invalid')
    number = int(value)
    if number > MAX_INT64:
        fail('native_materialization_int64_wire_invalid')
    return number


def strict_json(text: Any, *, limit=MAX_JSON) -> Any:
    if type(text) is not str or not 0 < len(text.encode()) <= limit:
        fail('native_materialization_json_unavailable')
    def pairs(items):
        result = {}
        for key, item in items:
            if key in result:
                fail('native_materialization_duplicate_json_key')
            result[key] = item
        return result
    def nonfinite(_):
        fail('native_materialization_nonfinite_json')
    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=nonfinite)
    except (ValueError, TypeError, RecursionError):
        fail('native_materialization_json_invalid')


def exact_types_equal(left, right):
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return set(left) == set(right) and all(exact_types_equal(left[k], right[k]) for k in left)
    if type(left) is list:
        return len(left) == len(right) and all(exact_types_equal(a, b) for a, b in zip(left, right))
    return left == right


def _identity(scope):
    return {k: getattr(scope, k) for k in ('organization_id', 'collection_id', 'specimen_id', 'job_id', 'generation')}


def _rows(rows, scope, *, key='id'):
    if type(rows) is not list or len(rows) > MAX_ROWS:
        fail('native_materialization_rows_unavailable')
    result = {}; native_scope = (scope.organization_id, scope.collection_id)
    for row in rows:
        if (type(row) is not dict or (row.get('organizationId'), row.get('collectionId')) != native_scope
            or type(row.get(key)) is not str or not row[key] or row[key] in result):
            fail('native_materialization_row_scope_or_duplicate')
        try:
            if str(UUID(row[key])) != row[key]:
                fail('native_materialization_row_uuid_invalid')
        except (ValueError, AttributeError):
            fail('native_materialization_row_uuid_invalid')
        result[row[key]] = copy.deepcopy(row)
    return result


def _current_checkpoint(job, field_key, scope):
    """Reproduce the qualified journal reuse view from native originals, never rebase."""
    field = job['fields'][field_key]; stored = field.get('checkpoint')
    if stored is None:
        return None, None
    if type(stored) is not dict or type(stored.get('payload')) is not dict or type(stored['payload'].get('scope')) is not dict:
        fail('native_materialization_checkpoint_original_invalid')
    original_binding_digest = stored.get('binding_digest')
    if (type(original_binding_digest) is not str
        or re.fullmatch(r'[0-9a-f]{64}', original_binding_digest) is None):
        fail('native_materialization_checkpoint_binding_invalid')
    strict_int(stored.get('revision'), minimum=1)
    strict_int(stored['payload'].get('revision'), minimum=1)
    strict_int(stored['payload']['scope'].get('generation'))
    for pin in stored['payload'].get('resolution', {}).get('dependencies', []):
        strict_int(pin.get('revision'), minimum=1)
    checkpoint = FieldCheckpoint.model_validate(stored['payload'])
    original_scope = _identity(checkpoint.scope)
    if (str(checkpoint.field_key) != field_key or stored.get('field_key') != field_key
        or strict_int(field.get('revision')) != checkpoint.revision
        or stored.get('revision') != checkpoint.revision or stored.get('scope') != original_scope
        or stored.get('id') != digest({'scope': original_scope, 'field': field_key,
            'revision': checkpoint.revision, 'payload': stored['payload']})
        or tuple(stored.get('receipt_ids', ())) != checkpoint.effect_receipt_ids
        or stored.get('dependencies') != {str(p.field_key): p.revision for p in checkpoint.resolution.dependencies}
        or stored.get('dependency_digests') != {str(p.field_key): p.digest for p in checkpoint.resolution.dependencies}
        or stored.get('retry_command_id') != checkpoint.retry_command_id):
        fail('native_materialization_checkpoint_original_invalid')
    current = checkpoint
    original_pins = job['pins']
    if checkpoint.scope != scope:
        matches = [h for h in job['history'] if h.get('scope') == original_scope
            and h.get('fields', {}).get(field_key, {}).get('checkpoint') == stored]
        if len(matches) != 1:
            fail('native_materialization_reuse_history_ambiguous')
        history = matches[0]; reuse = field.get('reuse')
        if (type(reuse) is not dict or reuse.get('reused_from_scope_digest') != digest(stored['scope'])
            or reuse.get('checkpoint_digest') != digest(stored)
            or reuse.get('into_scope_digest') != digest(_identity(scope))
            or reuse.get('source_binding_digest') != original_binding_digest
            or original_binding_digest != history.get('binding_digest')
            or reuse.get('target_binding_digest') != job.get('binding_digest')
            or reuse.get('retained_dependencies') != stored['dependencies']
            or reuse.get('retained_dependency_digests') != stored['dependency_digests']
            or any(job['dependencies'].get(k) != v for k, v in stored['dependencies'].items())
            or set(job['pins']) != set(history['pins'])
            or any(job['pins'][k] != history['pins'][k] for k in job['pins'] if k != 'input_digest')
            or checkpoint.scope.input_digest != history['pins']['input_digest']
            or checkpoint.scope.profile_digest != digest(history['pins']['profile'])):
            fail('native_materialization_reuse_proof_invalid')
        original_pins = history['pins']
        current = FieldCheckpoint.model_validate({**checkpoint.model_dump(mode='json'),
            'scope': scope.model_dump(mode='json'), 'reused_from_scope_digest': digest(checkpoint.scope),
            'reused_from_checkpoint_digest': digest(checkpoint)})
    elif field.get('reuse') is not None:
        fail('native_materialization_unnecessary_reuse')
    if original_binding_digest != digest(original_pins):
        fail('native_materialization_original_runtime_invalid')
    return current, {'current': current.model_dump(mode='json'), 'original': copy.deepcopy(stored),
        'reuse': copy.deepcopy(field.get('reuse')), 'original_pins': copy.deepcopy(original_pins)}


@dataclass(frozen=True)
class NativeMaterializationInputsV2:
    binding: Any
    intent: Any
    preparation: Any
    native_inputs: Mapping[str, Any]
    raw_binding: Mapping[str, Any]
    state_document: Mapping[str, Any]
    state_revision: int
    server_time: float
    checkpoint_pairs: Mapping[str, Mapping[str, Any]]
    guard: Mapping[str, Any]

    @classmethod
    def from_response(cls, principal, intent, preparation, response):
        from .native_canonical_v2 import CanonicalBindingV2, RetainedIntentV2
        outer = exact_object(response, OUTER, 'native_materialization_outer_shape')
        org = exact_object(outer['organizationMember'], {'active'}, 'native_materialization_access_unavailable')
        member = exact_object(outer['collectionMember'], {'active', 'role', 'canViewSensitive'}, 'native_materialization_access_unavailable')
        specimen = exact_object(outer['specimen'], {'sensitive'}, 'native_materialization_access_unavailable')
        if org['active'] is not True or member['active'] is not True:
            raise PermissionError('native_materialization_access_denied')
        if type(specimen['sensitive']) is not bool or type(member['canViewSensitive']) is not bool:
            fail('native_materialization_access_unavailable')
        if member['role'] != principal.role or (specimen['sensitive'] and not member['canViewSensitive']):
            raise PermissionError('native_materialization_access_denied')
        row = exact_object(outer['binding'], OLD_BINDING | {'materialization_inputs'}, 'native_materialization_binding_shape')
        legacy = {k: copy.deepcopy(row[k]) for k in OLD_BINDING}
        binding = CanonicalBindingV2.from_native(principal.scope, intent.original_prepared.basis.scope.specimen_id, legacy)
        raw = exact_object(row['materialization_inputs'], INPUT_KEYS, 'native_materialization_inputs_shape')
        if raw['contract_version'] != INPUT_VERSION or specimen['sensitive'] is not binding.sensitive:
            fail('native_materialization_version_or_sensitivity')
        try:
            observed = datetime.fromisoformat(raw['observed_at'].replace('Z', '+00:00'))
            if observed.tzinfo is None:
                fail('native_materialization_server_time_invalid')
            server_time = observed.timestamp()
        except (ValueError, AttributeError, TypeError):
            fail('native_materialization_server_time_invalid')
        if not math.isfinite(server_time) or server_time <= 0:
            fail('native_materialization_server_time_invalid')
        if raw['registration'] != row['registrations'][0]:
            fail('native_materialization_registration_split')
        retained_row = exact_object(raw['outer_intent'], {'original', 'preparations', 'preparation_count', 'attempt'}, 'native_materialization_intent_shape')
        if strict_int(retained_row['preparation_count'], maximum=20) != len(retained_row['preparations']):
            fail('native_materialization_preparation_count')
        retained = RetainedIntentV2.model_validate({k: retained_row[k] for k in ('original', 'preparations', 'attempt')})
        if retained.original != intent or preparation not in retained.preparations or retained.attempt is not None:
            fail('native_materialization_retained_intent_conflict')
        if preparation != retained.preparations[-1]:
            fail('native_materialization_preparation_not_current')
        integrity = exact_object(raw['private_state_integrity'], {'revision', 'contract_version', 'state_json', 'state'}, 'native_materialization_state_shape')
        revision = strict_int(integrity['revision'], minimum=1)
        state = strict_json(integrity['state_json'])
        if (type(state) is not dict or integrity['contract_version'] != 'research-durability/v1'
            or state.get('contract_version') != integrity['contract_version']
            or state.get('program_key') != binding.registration.program_key
            or not exact_types_equal(state, integrity['state'])):
            fail('native_materialization_state_integrity')
        reg = binding.registration; job = state.get('jobs', {}).get(reg.job_key)
        if job != reg.job or revision != reg.read_bundle['state_revision']:
            fail('native_materialization_state_registration_split')
        scope = intent.original_prepared.basis.scope
        strict_int(scope.generation)
        if (job.get('generation') != scope.generation or reg.generation != scope.generation
            or job.get('identity') != {k: getattr(scope, k) for k in ('organization_id', 'collection_id', 'specimen_id', 'job_id')}
            or digest(job.get('pins')) != reg.runtime_binding_digest):
            fail('native_materialization_current_job_identity')
        if raw['scoped_state'] != reg.read_bundle or raw['current_snapshot'] != row['snapshot']:
            fail('native_materialization_scoped_state_split')
        native_snapshot=exact_object(raw['current_snapshot'], {'snapshot','sha256','revision','contractVersion'}, 'native_materialization_snapshot_shape')
        body=native_snapshot['snapshot']
        if (native_snapshot['contractVersion']!='0.1' or type(body) is not dict or strict_int(native_snapshot['revision'],minimum=1)!=binding.canonical.record_revision
            or native_snapshot['sha256']!=binding.canonical.snapshot_sha256
            or graph_digest(body)!=native_snapshot['sha256']
            or strict_int(body.get('version'),minimum=1)!=binding.canonical.record_revision
            or body.get('id')!=scope.specimen_id or body.get('scope')!=principal.scope.model_dump(mode='json')
            or body.get('run',{}).get('id')!=str(binding.canonical.canonical_run_id)
            or body.get('asset',{}).get('sha256')!=reg.source_sha256
            or body.get('asset',{}).get('sensitive') is not binding.sensitive):
            fail('native_materialization_snapshot_identity_unproved')
        history = raw['retained_history']
        if history != [receipt.model_dump(mode='json') for receipt in binding.causal_chain]:
            fail('native_materialization_causal_history_split')
        anchor = exact_object(raw['preparation_snapshot'], {'identity', 'snapshot', 'record'}, 'native_materialization_anchor_unavailable')
        if anchor['identity'] != preparation.anchor.model_dump(mode='json'):
            fail('native_materialization_preparation_anchor_changed')
        if (type(anchor['snapshot']) is not dict or anchor['snapshot'].get('contractVersion')!='0.1'
            or type(anchor['snapshot'].get('snapshot')) is not dict
            or graph_digest(anchor['snapshot']['snapshot']) != preparation.anchor.snapshot_sha256
            or strict_int(anchor['snapshot'].get('revision'),minimum=1) != preparation.anchor.record_revision
            or anchor['snapshot'].get('sha256') != preparation.anchor.snapshot_sha256
            or anchor['snapshot'].get('revision') != preparation.anchor.record_revision
            or anchor['record'].get('id') != str(preparation.anchor.record_version_id)):
            fail('native_materialization_anchor_proof_partial')
        projection = exact_object(raw['projection_rows'], {'record_versions', 'resolved_fields', 'candidates', 'candidate_evidence', 'evidence', 'tool_calls', 'findings'}, 'native_materialization_projection_shape')
        indexes = {name: _rows(values, principal.scope) for name, values in projection.items()}
        required_versions = {str(binding.canonical.record_version_id), str(preparation.anchor.record_version_id)}
        required_versions.update(str(d.source_record_version_id) for d in intent.dependency_sources)
        if not required_versions <= set(indexes['record_versions']):
            fail('native_materialization_source_record_missing')
        for record_id in required_versions:
            fields = [r for r in projection['resolved_fields'] if r['recordVersionId'] == record_id]
            if len(fields) != 20 or {r['fieldKey'] for r in fields} != CANONICAL_KEYS:
                fail('native_materialization_whole20_missing_or_duplicate')
            for field in fields:
                candidate = field.get('candidateId')
                if candidate is not None and (candidate not in indexes['candidates']
                    or indexes['candidates'][candidate]['fieldKey'] != field['fieldKey']
                    or indexes['candidates'][candidate]['runId'] != indexes['record_versions'][record_id]['runId']):
                    fail('native_materialization_candidate_lineage')
        for link in indexes['candidate_evidence'].values():
            if link['candidateId'] not in indexes['candidates'] or link['evidenceId'] not in indexes['evidence']:
                fail('native_materialization_evidence_closure')
        native_rows = exact_object(raw['native_input_rows'], {'runs', 'regions', 'observations', 'transcriptions', 'handoffs', 'comparisons', 'assets'}, 'native_materialization_input_rows_shape')
        native_index = {name: _rows(values, principal.scope) for name, values in native_rows.items()}
        for asset in native_index['assets'].values():
            if asset['specimenId'] != scope.specimen_id or type(asset['generation']) is not str or not asset['generation']:
                fail('native_materialization_asset_identity')
            int64_decimal(asset['byteSize'])
        for run in native_index['runs'].values():
            if run['specimenId'] != scope.specimen_id:
                fail('native_materialization_run_scope')
        for name in ('regions', 'observations', 'transcriptions', 'handoffs', 'comparisons'):
            if any(row['runId'] not in native_index['runs'] for row in native_index[name].values()):
                fail('native_materialization_input_run_lineage')
        for region in native_index['regions'].values():
            if any(region.get(key) is not None and region[key] not in native_index['assets'] for key in ('sourceAssetId', 'cropAssetId')):
                fail('native_materialization_region_asset_lineage')
        lineage_rows = exact_object(raw['lineage_rows'], {'value_lineages', 'value_dependencies', 'value_evidence', 'tool_input_lineage', 'captured_tool_executions'}, 'native_materialization_lineage_rows_shape')
        for lineage_values in lineage_rows.values():
            _rows(lineage_values, principal.scope)
        pairs = {}; current = {}
        for field_key in RESEARCH_KEYS:
            checkpoint, pair = _current_checkpoint(job, field_key, scope)
            if checkpoint is not None:
                pairs[field_key] = pair; current[field_key] = checkpoint
        target = str(intent.original_prepared.basis.field_key)
        if target not in current or current[target] != preparation.prepared.publication.checkpoints[0]:
            fail('native_materialization_target_checkpoint_split')
        expected_cp = {'target': current[target].model_dump(mode='json'),
            'terminal_siblings': [current[k].model_dump(mode='json') for k in sorted(current) if k != target
                and job['fields'][k]['work_state'] in {'resolved', 'waiting_human', 'nonblocking_exception'}]}
        expected_original = {'target': pairs[target]['original']['payload'],
            'terminal_siblings': [pairs[k]['original']['payload'] for k in sorted(current) if k != target
                and job['fields'][k]['work_state'] in {'resolved', 'waiting_human', 'nonblocking_exception'}]}
        if raw['checkpoint_inputs'] != expected_original:
            fail('native_materialization_checkpoint_inventory_split')
        journal = raw['original_request_sources']
        if type(journal) is not list or len(journal) > 256:
            fail('native_materialization_original_request_inventory')
        for item in journal:
            exact_object(item, {'run_id', 'entry'}, 'native_materialization_journal_shape')
            entry = state.get('journal', {}).get(item['run_id'])
            if (entry != item['entry'] or entry['scope'].get('job_id') != scope.job_id
                or any(entry['scope'].get(k) != getattr(scope, k) for k in ('organization_id', 'collection_id', 'specimen_id'))):
                fail('native_materialization_original_journal_scope')
            strict_int(entry['scope'].get('generation'))
        executions = raw['captured_executions']
        if type(executions) is not list or len(executions) > MAX_ROWS:
            fail('native_materialization_capture_inventory')
        for item in executions:
            exact_object(item, {'effect_id', 'effect'}, 'native_materialization_effect_shape')
            effect = state.get('effects', {}).get(item['effect_id'])
            if effect != item['effect'] or effect.get('job_key') != reg.job_key:
                fail('native_materialization_effect_scope')
        inputs = copy.deepcopy(raw)
        inputs['checkpoint_inputs'] = expected_cp
        # Hide the fresh raw program state in this producer integrity alias.
        # Retained immutable preparation CAS proofs remain server-private;
        # neither this DTO nor its intent/preparation is an HTTP response.
        inputs['private_state_integrity'] = {'revision': revision, 'contract_version': integrity['contract_version'], 'state_digest': digest(state)}
        guard = {'contract_version': 'native-materialization-guard/v2', 'binding_id': str(reg.binding_id),
            'registration_revision': reg.registration_revision, 'state_revision': revision,
            'state_digest': digest(state), 'preparation_id': str(preparation.id),
            'preparation_digest': digest(preparation), 'current_canonical': binding.canonical.model_dump(mode='json'),
            'inputs_digest': digest(inputs), 'record_version_ids': sorted(required_versions),
            'projection_rows': copy.deepcopy(projection), 'native_input_rows': copy.deepcopy(native_rows),
            'lineage_rows': copy.deepcopy(raw['lineage_rows']), 'prepack_proof': copy.deepcopy(raw['prepack_proof'])}
        return cls(binding, intent, preparation, inputs, legacy, state, revision, server_time, pairs, guard)


@dataclass(frozen=True)
class NativeMaterializationLoadV2:
    replayed_result: Any | None = None
    inputs: NativeMaterializationInputsV2 | None = None

    def __post_init__(self):
        if (self.replayed_result is None) == (self.inputs is None):
            fail('native_materialization_load_result_invalid')


async def load_materialization_v2(writer, principal, specimen_id, *, idempotency_key, request_identity_digest, preparation_id):
    """Retained same-operation receipt wins before mutable materialization reads."""
    principal = writer._principal(principal, specimen_id)
    retained = await writer.read_same_operation_intent(principal, specimen_id, idempotency_key, request_identity_digest)
    if retained is None:
        fail('native_v2_original_intent_unavailable')
    replayed = await writer._read_receipt_v2(principal, retained.original, replayed=True)
    if replayed is not None:
        return NativeMaterializationLoadV2(replayed_result=replayed)
    if retained.attempt is not None:
        fail('native_v2_attempt_outcome_unknown')
    selected = [p for p in retained.preparations if str(p.id) == str(preparation_id)]
    if len(selected) != 1 or selected[0] != retained.preparations[-1]:
        fail('native_v2_preparation_not_current')
    variables = {**writer._variables(principal, specimen_id), 'idempotencyKey': idempotency_key,
        'requestIdentityDigest': request_identity_digest, 'preparationId': str(selected[0].id)}
    response = await writer._execute('GetCanonicalResearchMaterializationInputsV2', variables)
    return NativeMaterializationLoadV2(inputs=NativeMaterializationInputsV2.from_response(principal, retained.original, selected[0], response))
