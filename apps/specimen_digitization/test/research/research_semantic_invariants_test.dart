// Independent source-prepared probes, NOT EXECUTED.
// Python contract 329b23053b4e2ee21d45133c321f4b2c5ae84089; Dart decoder
// 1048dccceda38dcd4fab44dd01fbc8362194d4c2. Synthetic payloads only.
// Expectations mirror local Pydantic model validators, not scientific policy
// adjudication, authority approval, external receipt existence or live access.
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/research/research_models.dart';

const _fixtureDirectory = '../../tests/fixtures/research_harness/http';
const _scopePin =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _checkpointPin =
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';

Map<String, dynamic> _thread() => Map<String, dynamic>.from(
  jsonDecode(File('$_fixtureDirectory/failed-thread.json').readAsStringSync())
      as Map,
);

Map<String, dynamic> _checkpoint(String fieldKey) =>
    ((_thread()['fields'] as List).cast<Map<String, dynamic>>().singleWhere(
          (field) => field['field_key'] == fieldKey,
        )['checkpoint']
        as Map<String, dynamic>);

Map<String, dynamic> _resolution(String fieldKey) =>
    _checkpoint(fieldKey)['resolution'] as Map<String, dynamic>;

Map<String, dynamic> _coverage() => <String, dynamic>{
  'source_id': 'field_museum_ipt',
  'field_key': 'taxon',
  'state': 'exhausted',
  'source_version': 'synthetic-source-v1',
  'qualification_digest': _scopePin,
  'exact_join_attempted': true,
  'exact_join_proven': true,
  'query_digest': _checkpointPin,
  'receipt_ids': ['synthetic-scoped-search-receipt'],
  'candidate_count': 0,
  'coverage_limit': 'Only the synthetic qualified publisher record',
  'reason': 'Synthetic scoped search found no supported taxon value',
};

Map<String, dynamic> _human() {
  final json = _resolution('taxon');
  json['work_state'] = 'waiting_human';
  json['source_coverage'] = [_coverage()];
  json['question'] = <String, dynamic>{
    'field_key': 'taxon',
    'question': 'Which synthetic reading is intended?',
    'reason': 'semantic_ambiguity',
    'coverage': [_coverage()],
    'evidence_ids': <String>[],
  };
  return json;
}

Map<String, dynamic> _irnException() {
  final json = _resolution('taxon');
  json['field_key'] = 'identified_by_irn';
  json['work_state'] = 'nonblocking_exception';
  json['exception'] = <String, dynamic>{
    'field_key': 'identified_by_irn',
    'dependency': 'qualified_emu_determiner_eparties_identity',
    'policy_version': 'owner-2026-09-29-irn-nonblocking-v1',
    'reason':
        'EMu DB identity/record access unavailable; no verified determiner Parties IRN',
    'reevaluate_when':
        'Qualified read-only EMu connection and specimen determination join become available',
  };
  return json;
}

void _denyResolution(Map<String, dynamic> json) => expect(
  () => ResearchResolution.fromJson(json),
  throwsA(isA<ResearchContractException>()),
);

void main() {
  test('retains the supported evidenced frozen resolution', () {
    final resolution = ResearchResolution.fromJson(_resolution('country'));
    expect(resolution.workState, ResearchWorkState.resolved);
    expect(resolution.value.state, 'supported');
    expect(resolution.evidenceIds, isNotEmpty);
  });

  test('accepts a structurally qualified field-specific human question', () {
    final resolution = ResearchResolution.fromJson(_human());
    expect(resolution.workState, ResearchWorkState.waitingHuman);
    expect(resolution.question!.text, 'Which synthetic reading is intended?');
  });

  test('preserves the explicit unresolved IRN policy exception', () {
    final resolution = ResearchResolution.fromJson(_irnException());
    expect(resolution.workState, ResearchWorkState.nonblockingException);
    expect(resolution.value.state, 'unknown');
    expect(resolution.value.parsed, isNull);
    expect(resolution.value.normalized, isNull);
    expect(resolution.value.authorityId, isNull);
    expect(resolution.value.json['authority_identity'], isNull);
  });

  test('denies resolved with an unsupported value', () {
    final json = _resolution('country');
    json['value']['state'] = 'unknown';
    _denyResolution(json);
  });

  test('denies resolved without resolution evidence', () {
    final json = _resolution('country');
    json['evidence_ids'] = <String>[];
    _denyResolution(json);
  });

  test('denies a derived layer without a derivation record', () {
    final json = _resolution('country');
    json['value_layer'] = 'derived';
    json['derivation'] = null;
    _denyResolution(json);
  });

  test('denies waiting human without a question', () {
    final json = _human();
    json['question'] = null;
    _denyResolution(json);
  });

  test(
    'denies a human question using unavailable rather than exhausted coverage',
    () {
      final json = _human();
      json['question']['coverage'][0]['state'] = 'inaccessible';
      _denyResolution(json);
    },
  );

  test('denies human coverage owned by another field', () {
    final json = _human();
    json['question']['coverage'][0]['field_key'] = 'country';
    _denyResolution(json);
  });

  for (final entry in <String, Object?>{
    'exact_join_attempted': false,
    'receipt_ids': <String>[],
    'query_digest': null,
    'qualification_digest': null,
  }.entries) {
    test('denies exhausted source coverage without ${entry.key}', () {
      final json = _coverage();
      json[entry.key] = entry.value;
      if (entry.key == 'exact_join_attempted') {
        json['exact_join_proven'] = false;
      }
      expect(
        () => ResearchSourceCoverage.fromJson(json),
        throwsA(isA<ResearchContractException>()),
      );
    });
  }

  test('denies join proof without an actual join attempt', () {
    final json = _coverage();
    json['state'] = 'searched';
    json['exact_join_attempted'] = false;
    expect(
      () => ResearchSourceCoverage.fromJson(json),
      throwsA(isA<ResearchContractException>()),
    );
  });

  test('denies nonblocking exception without an explicit receipt', () {
    final json = _irnException();
    json['exception'] = null;
    _denyResolution(json);
  });

  for (final entry in <String, Object?>{
    'state': 'supported',
    'authority_id': 'invented-irn',
    'authority_identity': <String, dynamic>{'id': 'invented-irn'},
    'parsed': '12345',
    'normalized': '12345',
  }.entries) {
    test('denies an unresolved exception carrying ${entry.key}', () {
      final json = _irnException();
      json['value'][entry.key] = entry.value;
      _denyResolution(json);
    });
  }

  // Existing implemented ownership and paired-reuse checks are positive
  // regression controls, not new source findings.
  test('denies a question receipt with a different outer owner', () {
    final json = _human();
    json['question']['field_key'] = 'country';
    _denyResolution(json);
  });

  test('denies an exception receipt with a different outer owner', () {
    final json = _irnException();
    json['exception']['field_key'] = 'country';
    _denyResolution(json);
  });

  for (final present in [
    'reused_from_scope_digest',
    'reused_from_checkpoint_digest',
  ]) {
    test('denies only one reuse pin: $present', () {
      final json = _checkpoint('country');
      json[present] = _scopePin;
      expect(
        () => ResearchCheckpoint.fromJson(
          json,
          expectedScope: ResearchScope.fromJson(_thread()['scope']),
          expectedFieldKey: 'country',
        ),
        throwsA(isA<ResearchContractException>()),
      );
    });
  }

  test(
    'preserves paired reuse pins without claiming server-side reuse proof',
    () {
      final json = _checkpoint('country');
      json['reused_from_scope_digest'] = _scopePin;
      json['reused_from_checkpoint_digest'] = _checkpointPin;
      final checkpoint = ResearchCheckpoint.fromJson(
        json,
        expectedScope: ResearchScope.fromJson(_thread()['scope']),
        expectedFieldKey: 'country',
      );
      expect(checkpoint.json['reused_from_scope_digest'], _scopePin);
      expect(checkpoint.json['reused_from_checkpoint_digest'], _checkpointPin);
    },
  );
}
