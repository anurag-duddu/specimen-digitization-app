import 'dart:convert';

import 'package:crypto/crypto.dart' as crypto;
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/research/research_models.dart';
import 'package:specimen_digitization/src/research/research_review_block.dart';

import 'research_fixture.dart';

// Local DTO consistency cases, not a server-route or production fixture.
Map<String, dynamic> _preservedThread() {
  final thread = researchFixture('failed-thread');
  final scope = thread['scope'] as Map<String, dynamic>;
  for (final key in ['city', 'elevation_from_m']) {
    final field = fixtureField(thread, key);
    final original = <String, dynamic>{
      ...field['value'] as Map<String, dynamic>,
      'layer': null,
      'derived_from': <String>[],
      'reason': 'Saved Unknown for $key',
      'evidence_ids': ['original-$key-evidence'],
      'input_source': 'raw_reading',
      'source_region_id': 'original-region',
      'source_observation_id': 'original-observation',
      'verbatim_by_observation': {'original-observation': 'Original words'},
      'input_source_by_observation': {'original-observation': 'raw_reading'},
      'settled_observation_ids': ['original-observation'],
      'evidence_relations': {'original-$key-evidence': 'decides'},
    };
    final current = <String, dynamic>{
      ...original,
      'evidence_ids': ['current-$key-carry-evidence'],
      'evidence_relations': {'current-$key-carry-evidence': 'decides'},
      'input_source': null,
      'source_region_id': null,
      'source_observation_id': null,
      'verbatim_by_observation': <String, dynamic>{},
      'input_source_by_observation': <String, dynamic>{},
      'settled_observation_ids': <String>[],
    };
    field
      ..['work_state'] = 'waiting_human'
      ..['value'] = current
      ..['checkpoint'] = null
      ..['actions'] = <String>[]
      ..['review'] = null
      ..['blocker_code'] = 'preserved_human_decision'
      ..['preserved_human'] = {
        'contract_version': 'preserved-human-field/v1',
        'field_key': key,
        'value': jsonDecode(jsonEncode(current)),
        'original_value': original,
        'organization_id': scope['organization_id'],
        'collection_id': scope['collection_id'],
        'specimen_id': scope['specimen_id'],
        'canonical_run_id': 'fresh-canonical-run',
        'fresh_run_revision': 32,
        'origin_run_id': 'original-canonical-run',
        'origin_event_id': 'original-$key-review-event',
        'origin_revision': key == 'city' ? 31 : 30,
        'actor': 'Synthetic reviewer',
        'reason': 'A deliberate saved Unknown for $key',
        'created_at': '2026-10-06T14:00:00Z',
        'original_evidence_ids': ['original-$key-evidence'],
        'carry_digest': 'c' * 64,
        'proof_digest': 'd' * 64,
        'source_sha256': 'e' * 64,
      };
  }
  thread
    ..['preserved_human_count'] = 2
    ..['preserved_human_base'] = {
      'contract_version': 'preserved-human-base/v2',
      'canonical_run_id': 'fresh-canonical-run',
      'registration_record_revision': 33,
      'registration_snapshot_sha256': scope['input_digest'],
      'source_sha256': 'e' * 64,
      'outcome_count': 2,
      'outcome_digest': 'f' * 64,
      'outcomes_json': '{}',
    };
  _sealPreservedThread(thread);
  return thread;
}

Map<String, dynamic> _carry(
  Map<String, dynamic> thread, [
  String key = 'city',
]) => fixtureField(thread, key)['preserved_human'] as Map<String, dynamic>;

void _sealPreservedThread(Map<String, dynamic> thread) {
  final outcomes = {
    for (final field in (thread['fields'] as List).cast<Map<String, dynamic>>())
      if (field['preserved_human'] != null)
        field['field_key'] as String: field['preserved_human'],
  };
  final raw = jsonEncode(_sortedJson(outcomes));
  final base = thread['preserved_human_base'] as Map;
  base['outcomes_json'] = raw;
  base['outcome_digest'] = crypto.sha256.convert(utf8.encode(raw)).toString();
}

Object? _sortedJson(Object? value) {
  if (value is Map) {
    final keys = value.keys.cast<String>().toList()..sort();
    return {for (final key in keys) key: _sortedJson(value[key])};
  }
  if (value is List) return value.map(_sortedJson).toList();
  return value;
}

void main() {
  test(
    'preserved human fields are typed, immutable and counted separately',
    () {
      final json = _preservedThread();
      final thread = ResearchThread.fromJson(
        json,
        expectedScope: trustedResearchScope(),
      );
      expect(thread.fields, hasLength(20));
      expect(thread.resolvedCount, 1);
      expect(thread.exceptionCount, 0);
      expect(thread.preservedHumanCount, 2);
      expect(thread.preservedHumanBase!.registrationRecordRevision, 33);
      for (final key in ['city', 'elevation_from_m']) {
        final field = thread.field(key)!;
        final outcome = field.preservedHumanOutcome!;
        expect(field.workState, ResearchWorkState.waitingHuman);
        expect(field.checkpoint, isNull);
        expect(field.review, isNull);
        expect(field.canRetry, isFalse);
        expect(field.actions, isEmpty);
        expect(outcome.value.state, 'unknown');
        expect(outcome.value.json['source_observation_id'], isNull);
        expect(
          outcome.originalValue.json['source_observation_id'],
          'original-observation',
        );
        expect(outcome.originalEvidenceIds, ['original-$key-evidence']);
        expect(outcome.actor, 'Synthetic reviewer');
        expect(outcome.originEventId, 'original-$key-review-event');
        expect(outcome.freshRunRevision, 32);
        expect(() => outcome.json['actor'] = 'other', throwsUnsupportedError);
      }
    },
  );

  test('carry scope is checked even when a field is decoded in isolation', () {
    for (final key in ['organization_id', 'collection_id', 'specimen_id']) {
      final json = _preservedThread();
      _carry(json)[key] = 'other';
      expect(
        () => ResearchFieldThread.fromJson(
          fixtureField(json, 'city'),
          trustedResearchScope(),
        ),
        throwsA(isA<ResearchContractException>()),
      );
    }
  });

  group(
    'preserved human contradictions fail with a recomputed base digest',
    () {
      void rejects(String name, void Function(Map<String, dynamic>) change) {
        test(name, () {
          final json = _preservedThread();
          change(json);
          _sealPreservedThread(json);
          expect(
            () => ResearchThread.fromJson(
              json,
              expectedScope: trustedResearchScope(),
            ),
            throwsA(isA<ResearchContractException>()),
          );
        });
      }

      rejects(
        'wrong owning field',
        (json) => _carry(json)['field_key'] = 'county',
      );
      rejects('wrong active value', (json) {
        fixtureField(json, 'city')['value']['literal'] = 'Replacement';
      });
      rejects('replacement repeated in carry value', (json) {
        fixtureField(json, 'city')['value']['normalized'] = 'Replacement';
        _carry(json)['value']['normalized'] = 'Replacement';
      });
      rejects('old observation masquerades as current ancestry', (json) {
        fixtureField(json, 'city')['value']['source_observation_id'] = 'old';
        _carry(json)['value']['source_observation_id'] = 'old';
      });
      rejects('original evidence list disagrees', (json) {
        _carry(json)['original_evidence_ids'] = ['other'];
      });
      rejects('original evidence references are duplicated', (json) {
        final evidence = ['original-city-evidence', 'original-city-evidence'];
        _carry(json)['original_evidence_ids'] = evidence;
        _carry(json)['original_value']['evidence_ids'] = evidence;
      });
      rejects('origin run is the fresh run', (json) {
        _carry(json)['origin_run_id'] = 'fresh-canonical-run';
      });
      rejects('origin revision does not precede fresh revision', (json) {
        _carry(json)['origin_revision'] = 32;
      });
      rejects(
        'missing origin event',
        (json) => _carry(json)['origin_event_id'] = '',
      );
      rejects('blank actor', (json) => _carry(json)['actor'] = '  ');
      rejects('blank reason', (json) => _carry(json)['reason'] = '  ');
      rejects('unknown carry origin contract', (json) {
        _carry(json)['contract_version'] = 'native-model-field/v1';
      });
      rejects('native checkpoint accompanies carry', (json) {
        final checkpoint =
            jsonDecode(
                  jsonEncode(
                    fixtureField(
                      researchFixture('server-thread'),
                      'city',
                    )['checkpoint'],
                  ),
                )
                as Map<String, dynamic>;
        checkpoint['scope'] = jsonDecode(jsonEncode(json['scope']));
        checkpoint['resolution']['value'] = jsonDecode(
          jsonEncode(fixtureField(json, 'city')['value']),
        );
        fixtureField(json, 'city')['checkpoint'] = checkpoint;
      });
      for (final action in [
        'retry_field',
        'supply_information',
        'review_proposal',
      ]) {
        rejects('injected $action action', (json) {
          fixtureField(json, 'city')['actions'] = [action];
        });
      }
      rejects('native source review accompanies carry', (json) {
        fixtureField(json, 'city')['review'] = <String, dynamic>{};
      });
      rejects('native phase accompanies carry', (json) {
        fixtureField(json, 'city')['work_state'] = 'resolved';
      });
      rejects('wrong blocker', (json) {
        fixtureField(json, 'city')['blocker_code'] = 'human_decision_required';
      });
      rejects('wrong current run', (json) {
        _carry(json)['canonical_run_id'] = 'other';
      });
      rejects('wrong current source', (json) {
        _carry(json)['source_sha256'] = 'a' * 64;
      });
      rejects('fresh revision exceeds registration', (json) {
        _carry(json)['fresh_run_revision'] = 34;
      });
      rejects('wrong current base snapshot', (json) {
        json['preserved_human_base']['registration_snapshot_sha256'] = '9' * 64;
      });
      rejects('retained count includes only one carry', (json) {
        json['preserved_human_count'] = 1;
      });
      rejects('native resolved count includes human outcomes', (json) {
        json['resolved_count'] = 3;
      });
      rejects('native exception count includes human outcomes', (json) {
        json['exception_count'] = 2;
      });
    },
  );

  test('carry digest binds the complete original decision DTO', () {
    final json = _preservedThread();
    _carry(json)['origin_event_id'] = 'different-original-event';
    expect(
      () =>
          ResearchThread.fromJson(json, expectedScope: trustedResearchScope()),
      throwsA(isA<ResearchContractException>()),
    );
  });

  test('exact outcome text retains integral numeric spelling and Unicode', () {
    for (final metadata in [
      '{"measure":1}',
      '{"measure":1.0}',
      '{"measure":1e+20}',
      '{"measure":9007199254740993}',
      '{"measure":1${'0' * 400}}',
      '{"measure":-0.0}',
      '{"\uE000":"BMP","\ud83d\ude00":"Supplementary"}',
    ]) {
      final json = _preservedThread();
      final base = json['preserved_human_base'] as Map<String, dynamic>;
      final raw = (base['outcomes_json'] as String).replaceAll(
        '"authority_identity":null',
        '"authority_identity":$metadata',
      );
      for (final key in ['city', 'elevation_from_m']) {
        final field = fixtureField(json, key);
        final carry = _carry(json, key);
        field['value']['authority_identity'] = jsonDecode(metadata);
        carry['value']['authority_identity'] = jsonDecode(metadata);
        carry['original_value']['authority_identity'] = jsonDecode(metadata);
      }
      base['outcomes_json'] = raw;
      base['outcome_digest'] = crypto.sha256
          .convert(utf8.encode(raw))
          .toString();
      final thread = ResearchThread.fromJson(
        json,
        expectedScope: trustedResearchScope(),
      );
      expect(thread.preservedHumanBase!.outcomesJson, raw);
      expect(raw, contains(metadata));
      for (final key in ['city', 'elevation_from_m']) {
        expect(thread.field(key)!.preservedHumanOutcomesJson, raw);
      }
    }
  });

  test('isolated field projections cannot export exact server provenance', () {
    final json = _preservedThread();
    final field = ResearchFieldThread.fromJson(
      fixtureField(json, 'city'),
      trustedResearchScope(),
    );
    expect(field.preservedHumanOutcome, isNotNull);
    expect(field.preservedHumanOutcomesJson, isNull);
  });

  test('overflow projection permission stays inside validated v2 carries', () {
    final json = _preservedThread();
    final field = fixtureField(json, 'city');
    field['value']['authority_identity'] = {'measure': double.infinity};
    expect(
      () => ResearchValue.fromJson(field['value']),
      throwsA(isA<ResearchContractException>()),
    );
    expect(
      () => ResearchFieldThread.fromJson(field, trustedResearchScope()),
      throwsA(isA<ResearchContractException>()),
    );
    final native = researchFixture('failed-thread');
    fixtureField(native, 'habitat')['value']['authority_identity'] = {
      'measure': double.infinity,
    };
    expect(
      () => ResearchThread.fromJson(
        native,
        expectedScope: trustedResearchScope(),
      ),
      throwsA(isA<ResearchContractException>()),
    );
    final withBase = _preservedThread();
    fixtureField(withBase, 'habitat')['value']['authority_identity'] = {
      'measure': double.infinity,
    };
    expect(
      () => ResearchThread.fromJson(
        withBase,
        expectedScope: trustedResearchScope(),
      ),
      throwsA(isA<ResearchContractException>()),
    );
  });

  test('changed exact text and changed projections are both rejected', () {
    final changedText = _preservedThread();
    changedText['preserved_human_base']['outcomes_json'] += ' ';
    expect(
      () => ResearchThread.fromJson(
        changedText,
        expectedScope: trustedResearchScope(),
      ),
      throwsA(isA<ResearchContractException>()),
    );
    final changedProjection = _preservedThread();
    _carry(changedProjection)['actor'] = 'another actor';
    expect(
      () => ResearchThread.fromJson(
        changedProjection,
        expectedScope: trustedResearchScope(),
      ),
      throwsA(isA<ResearchContractException>()),
    );
    final malformed = _preservedThread();
    malformed['preserved_human_base']['outcomes_json'] = '{{';
    malformed['preserved_human_base']['outcome_digest'] = crypto.sha256
        .convert(utf8.encode('{{'))
        .toString();
    expect(
      () => ResearchThread.fromJson(
        malformed,
        expectedScope: trustedResearchScope(),
      ),
      throwsA(isA<ResearchContractException>()),
    );
  });

  test('v2 base requires exact text and safe revision/count bounds', () {
    for (final change in <void Function(Map<String, dynamic>)>[
      (base) => base.remove('outcomes_json'),
      (base) => base['contract_version'] = 'preserved-human-base/v1',
      (base) => base['registration_record_revision'] = 9007199254740992,
    ]) {
      final base =
          _preservedThread()['preserved_human_base'] as Map<String, dynamic>;
      change(base);
      expect(
        () => ResearchPreservedHumanBase.fromJson(base),
        throwsA(isA<ResearchContractException>()),
      );
    }
    final json = _preservedThread();
    _carry(json)['fresh_run_revision'] = 9007199254740992;
    _sealPreservedThread(json);
    expect(
      () =>
          ResearchThread.fromJson(json, expectedScope: trustedResearchScope()),
      throwsA(isA<ResearchContractException>()),
    );
  });

  test('v2 raw outcome limit applies to UTF-8 bytes as well as characters', () {
    final raw = jsonEncode({'padding': '🧭' * (1024 * 1024)});
    expect(raw.runes.length, lessThan(4 * 1024 * 1024));
    expect(utf8.encode(raw).length, greaterThan(4 * 1024 * 1024));
    final base =
        _preservedThread()['preserved_human_base'] as Map<String, dynamic>;
    base['outcomes_json'] = raw;
    base['outcome_digest'] = crypto.sha256.convert(utf8.encode(raw)).toString();
    expect(
      () => ResearchPreservedHumanBase.fromJson(base),
      throwsA(isA<ResearchContractException>()),
    );
  });

  test(
    'the registration base enforces the schema maximum of twenty outcomes',
    () {
      final base =
          _preservedThread()['preserved_human_base'] as Map<String, dynamic>;
      base['outcome_count'] = 21;
      expect(
        () => ResearchPreservedHumanBase.fromJson(base),
        throwsA(isA<ResearchContractException>()),
      );
    },
  );

  test('schema text bounds count Unicode characters', () {
    expect(
      ResearchFieldReview.fromJson({'reason': '🧭' * 600}).reason,
      '🧭' * 600,
    );
    expect(
      () => ResearchFieldReview.fromJson({'reason': '🧭' * 601}),
      throwsA(isA<ResearchContractException>()),
    );
  });

  test(
    'carries require their base and ordinary waitingHuman still needs proof',
    () {
      final carried = _preservedThread()..remove('preserved_human_base');
      expect(
        () => ResearchThread.fromJson(
          carried,
          expectedScope: trustedResearchScope(),
        ),
        throwsA(isA<ResearchContractException>()),
      );
      final ordinary = researchFixture('failed-thread');
      fixtureField(ordinary, 'city')['work_state'] = 'waiting_human';
      expect(
        () => ResearchThread.fromJson(
          ordinary,
          expectedScope: trustedResearchScope(),
        ),
        throwsA(isA<ResearchContractException>()),
      );
    },
  );

  test('legacy threads omit retained outcomes and stay unchanged', () {
    final thread = fixtureThread();
    expect(thread.preservedHumanCount, 0);
    expect(thread.preservedHumanBase, isNull);
    expect(
      thread.fields.every((field) => field.preservedHumanOutcome == null),
      isTrue,
    );
  });

  test(
    'review candidates preserve exact values and explain derived proposals',
    () {
      final json = researchFixture('failed-thread');
      final taxon = fixtureField(json, 'taxon');
      taxon['work_state'] = 'waiting_human';
      taxon['checkpoint']['resolution']['work_state'] = 'waiting_human';
      taxon['actions'] = ['review_proposal'];
      taxon['review'] = {
        'question_reason': 'derived_proposal',
        'reason': 'Two retained source possibilities remain.',
        'question': {
          'field_key': 'taxon',
          'question': 'Which retained source candidate is supported?',
          'reason': 'derived_proposal',
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
            'selection_id': 'a' * 64,
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
      expect(field.review!.candidates.first.selectionId, 'a' * 64);
      expect(field.review!.candidates.last.selectionId, isNull);
      expect(field.review!.evidence.single.evidenceId, 'source-evidence');
      expect(researchReviewCase(field), ResearchReviewCase.derivedProposal);
      expect(
        ResearchReviewCase.derivedProposal.headline,
        'A proposed value is ready for review. It has not been applied.',
      );
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

  test(
    'historical report metadata is parsed and suppresses fresh retry tokens',
    () {
      final current = fixtureThread();
      expect(current.historical, isFalse);
      expect(current.canonicalRevision, isNull);
      expect(current.reviewSavedRevision, isNull);

      final json = researchFixture('failed-thread')
        ..['historical'] = true
        ..['canonical_revision'] = 41
        ..['review_saved_revision'] = 42;
      final historical = ResearchThread.fromJson(
        json,
        expectedScope: trustedResearchScope(),
      );
      expect(historical.historical, isTrue);
      expect(historical.canonicalRevision, 41);
      expect(historical.reviewSavedRevision, 42);
      expect(historical.canRetry('taxon'), isFalse);
    },
  );

  test(
    'historical report metadata rejects invalid types and negative revisions',
    () {
      for (final edit in <void Function(Map<String, dynamic>)>[
        (json) => json['historical'] = 'true',
        (json) => json['canonical_revision'] = '41',
        (json) => json['canonical_revision'] = -1,
        (json) => json['review_saved_revision'] = 42.0,
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
