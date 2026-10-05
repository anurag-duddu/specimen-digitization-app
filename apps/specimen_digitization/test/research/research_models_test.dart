import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/research/research_models.dart';

import 'research_fixture.dart';

void main() {
  test(
    'review candidates preserve display labels and exact selectable values',
    () {
      final json = researchFixture('failed-thread');
      final taxon = fixtureField(json, 'taxon');
      taxon['work_state'] = 'waiting_human';
      taxon['checkpoint']['resolution']['work_state'] = 'waiting_human';
      taxon['actions'] = ['review_proposal'];
      taxon['review'] = {
        'question_reason': 'semantic_ambiguity',
        'reason': 'Two retained source possibilities remain.',
        'question': {
          'field_key': 'taxon',
          'question': 'Which retained source candidate is supported?',
          'reason': 'semantic_ambiguity',
          'coverage': [
            {
              'source_id': 'gbif',
              'field_key': 'taxon',
              'state': 'exhausted',
              'source_version': 'test-v1',
              'qualification_digest': 'a' * 64,
              'exact_join_attempted': true,
              'query_digest': 'b' * 64,
              'receipt_ids': ['coverage-receipt'],
              'candidate_count': 2,
              'coverage_limit': 'bounded test scope',
              'reason': 'Search completed within the fixture scope',
            },
          ],
          'evidence_ids': ['source-evidence'],
        },
        'evidence': [
          {
            'evidence_id': 'source-evidence',
            'source_id': 'geolocate',
            'kind': 'lookup',
            'searched_text': 'Mindanao',
            'outcome': 'ambiguous',
          },
        ],
        'candidates': [
          {
            'label': 'Mindanao',
            'source_id': 'geolocate',
            'selection_id': 'candidate-receipt',
            'selection_value': 'Philippines',
            'evidence_id': 'source-evidence',
          },
          {
            'label': 'Philippines',
            'source_id': 'geolocate',
            'selection_id': null,
            'selection_value': null,
          },
        ],
        'evidence_not_shown': 0,
        'candidates_not_shown': 0,
      };
      taxon['checkpoint']['resolution']['question'] = taxon['review'].remove(
        'question',
      );
      final field = ResearchThread.fromJson(
        json,
        expectedScope: trustedResearchScope(),
      ).field('taxon')!;
      expect(field.review!.candidates.first.label, 'Mindanao');
      expect(field.review!.candidates.first.selectionValue, 'Philippines');
      expect(field.review!.candidates.first.selectionId, 'candidate-receipt');
      expect(field.review!.candidates.last.selectionId, isNull);
      expect(field.review!.evidence.single.evidenceId, 'source-evidence');
    },
  );

  test(
    'frozen thread preserves value layers, evidence and retained queued failure',
    () {
      final failed = fixtureThread();
      expect(failed.canRetry('taxon'), isTrue);
      expect(failed.field('country')!.value.literal, 'Synthetic country');
      expect(failed.field('country')!.checkpoint!.resolution.evidenceIds, [
        'synthetic-country-evidence',
      ]);
      final queued = fixtureThread('queued-thread');
      expect(
        queued.field('taxon')!.workState,
        ResearchWorkState.retryScheduled,
      );
      expect(
        queued.field('taxon')!.checkpoint!.resolution.workState,
        ResearchWorkState.operationalFailed,
      );
      expect(queued.canRetry('taxon'), isFalse);
      expect(() => failed.scope.json['generation'] = 2, throwsUnsupportedError);
      expect(
        () => failed.field('country')!.value.json['literal'] = 'changed',
        throwsUnsupportedError,
      );
    },
  );

  for (final key in [
    'organization_id',
    'collection_id',
    'specimen_id',
    'job_id',
    'generation',
    'input_digest',
    'profile_digest',
    'sensitive',
  ]) {
    test('rejects a mismatched full scope field: $key', () {
      final json = researchFixture('failed-thread');
      final scope = json['scope'] as Map<String, dynamic>;
      scope[key] = switch (key) {
        'generation' => 2,
        'sensitive' => true,
        'input_digest' || 'profile_digest' => 'c' * 64,
        _ => 'other',
      };
      expect(
        () => ResearchThread.fromJson(
          json,
          expectedScope: trustedResearchScope(),
        ),
        throwsA(isA<ResearchContractException>()),
      );
    });
  }

  for (final value in [null, false, '1', 1.0, -1]) {
    test('rejects checkpoint revision type/value: ${value.toString()}', () {
      final json = researchFixture('failed-thread');
      fixtureField(json, 'taxon')['checkpoint']['revision'] = value;
      expect(
        () => ResearchThread.fromJson(
          json,
          expectedScope: trustedResearchScope(),
        ),
        throwsA(isA<ResearchContractException>()),
      );
    });
  }

  test('requires explicit version and sensitivity, and rejects extra keys', () {
    for (final edit in <void Function(Map<String, dynamic>)>[
      (json) => json.remove('contract_version'),
      (json) => json['contract_version'] = 'research-thread-v2',
      (json) => (json['scope'] as Map).remove('sensitive'),
      (json) => json['scope']['input_digest'] = '${'a' * 64}\n',
      (json) => json['secret_prompt'] = 'unrecognized',
      (json) => fixtureField(json, 'taxon')['value']['literal'] = 12,
    ]) {
      final json = researchFixture('failed-thread');
      edit(json);
      expect(
        () => ResearchThread.fromJson(
          json,
          expectedScope: trustedResearchScope(),
        ),
        throwsA(isA<ResearchContractException>()),
      );
    }
  });

  test('rejects duplicate keys and checkpoint owner/scope/value conflicts', () {
    for (final edit in <void Function(Map<String, dynamic>)>[
      (json) => (json['fields'] as List).add(fixtureField(json, 'taxon')),
      (json) => fixtureField(json, 'taxon')['field_key'] = 'new_field',
      (json) =>
          fixtureField(json, 'taxon')['checkpoint']['field_key'] = 'country',
      (json) => fixtureField(json, 'taxon')['checkpoint']['scope']['job_id'] =
          'other',
      (json) =>
          fixtureField(json, 'taxon')['checkpoint']['resolution']['field_key'] =
              'country',
      (json) => fixtureField(
        json,
        'taxon',
      )['checkpoint']['resolution']['value']['literal'] = 'forged',
      (json) => json['resolved_count'] = 19,
    ]) {
      final json = researchFixture('failed-thread');
      edit(json);
      expect(
        () => ResearchThread.fromJson(
          json,
          expectedScope: trustedResearchScope(),
        ),
        throwsA(isA<ResearchContractException>()),
      );
    }
  });

  test('novel work phase remains readable and disables every action', () {
    final json = researchFixture('failed-thread');
    fixtureField(json, 'country')['work_state'] = 'future_phase';
    final thread = ResearchThread.fromJson(
      json,
      expectedScope: trustedResearchScope(),
    );
    expect(thread.field('country')!.workState, ResearchWorkState.unknown);
    expect(thread.hasUnknownState, isTrue);
    expect(thread.canRetry('taxon'), isFalse);
  });

  test('blocked and paused states suppress advertised retries', () {
    final json = researchFixture('failed-thread');
    fixtureField(json, 'taxon')['blocker_code'] = 'research_retry_blocked';
    expect(
      ResearchThread.fromJson(
        json,
        expectedScope: trustedResearchScope(),
      ).canRetry('taxon'),
      isFalse,
    );
    final paused = researchFixture('failed-thread')..['paused'] = true;
    expect(
      ResearchThread.fromJson(
        paused,
        expectedScope: trustedResearchScope(),
      ).canRetry('taxon'),
      isFalse,
    );
  });

  test(
    'queued ACK requires exact version, key, generation, revision and command ID',
    () {
      final scope = trustedResearchScope();
      final valid = ResearchRetryAck.fromJson(
        researchFixture('queued-retry'),
        expectedScope: scope,
        expectedFieldKey: 'taxon',
        expectedCheckpointRevision: 1,
      );
      expect(valid.scope.matches(scope), isTrue);
      expect(valid.checkpointRevision, 1);
      for (final edit in <void Function(Map<String, dynamic>)>[
        (json) => json.remove('contract_version'),
        (json) => json['contract_version'] = 'research-thread-v1',
        (json) => json['command_id'] = 'invalid',
        (json) => json['status'] = 'completed',
        (json) => json['field_key'] = 'country',
        (json) => json['generation'] = 2,
        (json) => json['expected_checkpoint_revision'] = 2,
        (json) => json['expected_checkpoint_revision'] = 1.0,
        (json) => json['specimen_revision'] = 1,
      ]) {
        final json = researchFixture('queued-retry');
        edit(json);
        expect(
          () => ResearchRetryAck.fromJson(
            json,
            expectedScope: scope,
            expectedFieldKey: 'taxon',
            expectedCheckpointRevision: 1,
          ),
          throwsA(isA<ResearchContractException>()),
        );
      }
    },
  );
}
