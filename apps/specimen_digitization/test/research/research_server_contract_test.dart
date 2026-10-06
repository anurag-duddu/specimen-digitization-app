// The thread the app must accept is the thread the server's route emits.
//
// `server-thread.json` is the real route's response for a rig with a resolved
// field, a failed one, two geography questions and pending fields
// (tests/test_research_harness_api.py writes it and fails when it drifts).
// The older fixtures in this directory predate two server changes the app's
// copy of the contract did not follow, so nothing here had decoded a thread
// of the shape the server sends today.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/research/research_controller.dart';
import 'package:specimen_digitization/src/research/research_models.dart';
import 'package:specimen_digitization/src/research/research_thread_card.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';

import 'research_fixture.dart';

Map<String, dynamic> _serverThread() => researchFixture('server-thread');

// The backend integrator owns this fixture and its offline actual-route emitter.
Map<String, dynamic> _preservedServerThread() =>
    researchFixture('server-preserved-human-thread');

ResearchThread _decodePreserved(Map<String, dynamic> json) =>
    ResearchThread.fromJson(
      json,
      expectedScope: ResearchScope.fromJson(_preservedServerThread()['scope']),
    );

Map<String, dynamic> _preservedOutcome(
  Map<String, dynamic> json, [
  String key = 'city',
]) => fixtureField(json, key)['preserved_human'] as Map<String, dynamic>;

ResearchThread _decode(Map<String, dynamic> json) => ResearchThread.fromJson(
  json,
  expectedScope: ResearchScope.fromJson(json['scope']),
);

Map<String, dynamic> _coverage(Map<String, dynamic> json, String key) =>
    ((fixtureField(json, key)['checkpoint']['resolution']['question']
                    as Map)['coverage']
                as List)
            .single
        as Map<String, dynamic>;

void _expectRejected(Map<String, dynamic> json) =>
    expect(() => _decode(json), throwsA(isA<ResearchContractException>()));

/// Removes the two keys a server that predates c8e4d931 does not send.
void _dropLayerKeys(Object? node) {
  if (node is Map<String, dynamic>) {
    if (node.containsKey('verbatim_by_observation')) {
      node.remove('layer');
      node.remove('derived_from');
    }
    node.values.forEach(_dropLayerKeys);
  } else if (node is List) {
    node.forEach(_dropLayerKeys);
  }
}

/// Turns habitat, a field outside geography, into a field that asks a person.
void _askAboutHabitat(
  Map<String, dynamic> json,
  Map<String, dynamic> coverage,
) {
  final field = fixtureField(json, 'habitat');
  expect(field['checkpoint'], isNull, reason: 'habitat is pending');
  field['work_state'] = 'waiting_human';
  final city = fixtureField(json, 'city');
  final copy = Map<String, dynamic>.from(
    (city['checkpoint'] as Map).cast<String, dynamic>(),
  );
  final resolved = Map<String, dynamic>.from(
    (copy['resolution'] as Map).cast<String, dynamic>(),
  );
  resolved['field_key'] = 'habitat';
  resolved['question'] = {
    'field_key': 'habitat',
    'question': 'Which habitat does the label name?',
    'reason': 'scoped_absence',
    'coverage': [coverage],
    'evidence_ids': <String>[],
  };
  copy['field_key'] = 'habitat';
  copy['resolution'] = resolved;
  field['checkpoint'] = copy;
  field['value'] = resolved['value'];
  field['blocker_code'] = 'human_decision_required';
}

void main() {
  test('decodes preserved human outcomes from the actual server route', () {
    final json = _preservedServerThread();
    final thread = _decodePreserved(json);
    expect(thread.fields, hasLength(20));
    expect(thread.resolvedCount, 0);
    expect(thread.exceptionCount, 0);
    expect(thread.preservedHumanCount, 2);
    expect(thread.effects, isEmpty);
    expect(thread.fields.where((field) => field.checkpoint != null), isEmpty);
    // This response starts fresh research: pending rows are not native results.
    expect(
      thread.fields.where(
        (field) => field.workState == ResearchWorkState.pending,
      ),
      hasLength(18),
    );
    final base = thread.preservedHumanBase!;
    expect(base.outcomesJson, json['preserved_human_base']['outcomes_json']);
    expect(base.registrationRecordRevision, 4);
    expect(base.registrationSnapshotSha256, thread.scope.inputDigest);
    expect(base.outcomeCount, 2);
    for (final key in ['city', 'elevation_from_m']) {
      final field = thread.field(key)!;
      final outcome = field.preservedHumanOutcome!;
      final wire = _preservedOutcome(json, key);
      expect(field.workState, ResearchWorkState.waitingHuman);
      expect(field.checkpoint, isNull);
      expect(field.review, isNull);
      expect(field.actions, isEmpty);
      expect(thread.canRetry(key), isFalse);
      expect(field.value.state, 'unknown');
      expect(field.value.literal, isNull);
      expect(field.value.parsed, isNull);
      expect(field.value.normalized, isNull);
      expect(outcome.value.json, field.value.json);
      expect(field.preservedHumanOutcomesJson, base.outcomesJson);
      expect(outcome.originalValue.state, 'unknown');
      expect(
        outcome.originalValue.json['reason'],
        key == 'city' ? 'slope is not a city' : 'feet are not asserted metres',
      );
      expect(outcome.reason, 'checked original label');
      expect(outcome.actor, 'A');
      expect(outcome.createdAt, wire['created_at']);
      expect(outcome.originEventId, wire['origin_event_id']);
      expect(outcome.originRunId, wire['origin_run_id']);
      expect(outcome.originRevision, key == 'city' ? 3 : 2);
      expect(outcome.freshRunRevision, 4);
      expect(outcome.canonicalRunId, base.canonicalRunId);
      expect(outcome.sourceSha256, base.sourceSha256);
      expect(outcome.originalEvidenceIds, isEmpty);
      expect(field.value.evidenceIds, hasLength(1));
      expect(field.value.json['evidence_relations'], {
        field.value.evidenceIds.single: 'decides',
      });
    }
  });

  group('actual-route preserved outcome contradictions are refused', () {
    void rejects(String name, void Function(Map<String, dynamic>) change) {
      test(name, () {
        final json = _preservedServerThread();
        change(json);
        expect(
          () => _decodePreserved(json),
          throwsA(isA<ResearchContractException>()),
        );
      });
    }

    rejects('response scope differs from the trusted fixture binding', (json) {
      json['scope']['specimen_id'] = 'other';
    });
    rejects('carry belongs to another scoped specimen', (json) {
      _preservedOutcome(json)['specimen_id'] = 'other';
    });
    rejects('current field value differs from the carry', (json) {
      fixtureField(json, 'city')['value']['normalized'] = 'Replacement';
    });
    rejects('original event differs from the bound outcome map', (json) {
      _preservedOutcome(json)['origin_event_id'] = 'another-original-event';
    });
    rejects('original run is the fresh run', (json) {
      final outcome = _preservedOutcome(json);
      outcome['origin_run_id'] = outcome['canonical_run_id'];
    });
    rejects('registration base differs from the scoped input', (json) {
      json['preserved_human_base']['registration_snapshot_sha256'] = 'a' * 64;
    });
    rejects('registration predates the carry transition', (json) {
      json['preserved_human_base']['registration_record_revision'] = 3;
    });
    rejects('exact outcome text changes', (json) {
      json['preserved_human_base']['outcomes_json'] += ' ';
    });
    rejects('exact outcome text is missing', (json) {
      (json['preserved_human_base'] as Map).remove('outcomes_json');
    });
    rejects('native checkpoint accompanies a preserved decision', (json) {
      final checkpoint =
          fixtureField(_serverThread(), 'city')['checkpoint']
              as Map<String, dynamic>;
      checkpoint['scope'] = json['scope'];
      checkpoint['resolution']['value'] = fixtureField(json, 'city')['value'];
      // The checkpoint itself is valid; exclusivity with the carry must fail.
      expect(
        ResearchCheckpoint.fromJson(
          checkpoint,
          expectedScope: ResearchScope.fromJson(json['scope']),
          expectedFieldKey: 'city',
        ).resolution.workState,
        ResearchWorkState.waitingHuman,
      );
      fixtureField(json, 'city')['checkpoint'] = checkpoint;
    });
    for (final action in [
      'retry_field',
      'supply_information',
      'review_proposal',
    ]) {
      rejects('native $action action accompanies a preserved decision', (json) {
        fixtureField(json, 'city')['actions'] = [action];
      });
    }
    rejects('native source review accompanies a preserved decision', (json) {
      fixtureField(json, 'city')['review'] = <String, dynamic>{};
    });
    rejects('retained count omits a carried field', (json) {
      json['preserved_human_count'] = 1;
    });
    rejects('resolved native count includes human decisions', (json) {
      json['resolved_count'] = 2;
    });
    rejects('exception native count includes human decisions', (json) {
      json['exception_count'] = 2;
    });
    rejects('unprotected waitingHuman still lacks a native checkpoint', (json) {
      fixtureField(json, 'habitat')['work_state'] = 'waiting_human';
    });
  });

  test('decodes the thread the real route emits', () {
    final json = _serverThread();
    final thread = _decode(json);
    expect(thread.fields, hasLength(20));
    expect(thread.field('country')!.workState, ResearchWorkState.resolved);
    expect(thread.field('taxon')!.canRetry, isTrue);
    for (final key in ['province_state', 'city']) {
      final field = thread.field(key)!;
      expect(field.workState, ResearchWorkState.waitingHuman);
      expect(field.checkpoint!.resolution.question!.text, isNotEmpty);
    }
    expect(_coverage(json, 'city')['state'], 'searched');
    expect(_coverage(json, 'city')['source_id'], 'geolocate');
  });

  test('the fixture carries the keys the server dumps on every value', () {
    final values = [
      for (final field in _serverThread()['fields'] as List)
        (field as Map<String, dynamic>)['value'] as Map<String, dynamic>,
    ];
    expect(values, hasLength(20));
    for (final value in values) {
      expect(value.containsKey('layer'), isTrue);
      expect(value['derived_from'], isEmpty);
    }
  });

  test('a server that predates layer and derived_from still decodes', () {
    final json = _serverThread();
    _dropLayerKeys(json);
    expect(_decode(json).fields, hasLength(20));
    expect(fixtureThread().fields, hasLength(20));
    expect(fixtureThread('queued-thread').fields, hasLength(20));
  });

  test('an unknown key on a value is still refused', () {
    final json = _serverThread();
    (fixtureField(json, 'country')['value'] as Map<String, dynamic>)['extra'] =
        1;
    _expectRejected(json);
  });

  test(
    'the same question with exhausted coverage is accepted outside geography',
    () {
      // The control for the refusals below: the scaffolding is a valid thread.
      final json = _serverThread();
      _askAboutHabitat(json, {
        'source_id': 'field_museum_ipt',
        'field_key': 'habitat',
        'state': 'exhausted',
        'source_version': 'v1',
        'qualification_digest': 'a' * 64,
        'exact_join_attempted': true,
        'exact_join_proven': true,
        'query_digest': 'b' * 64,
        'receipt_ids': ['receipt'],
        'candidate_count': 0,
        'coverage_limit': 'Scoped',
        'reason': 'no_match',
      });
      expect(
        _decode(json).field('habitat')!.workState,
        ResearchWorkState.waitingHuman,
      );
    },
  );

  group('a question coverage the server would refuse is refused', () {
    void rejects(String name, void Function(Map<String, dynamic> json) change) {
      test(name, () {
        final json = _serverThread();
        change(json);
        _expectRejected(json);
      });
    }

    rejects(
      'a searched receipt from another source',
      (json) => _coverage(json, 'city')['source_id'] = 'gbif',
    );
    rejects(
      'a searched GEOLocate receipt for a field outside geography',
      (json) => _askAboutHabitat(json, {
        ..._coverage(json, 'city'),
        'field_key': 'habitat',
      }),
    );
    rejects(
      'a reason that does not lead with its typed outcome',
      (json) => _coverage(json, 'city')['reason'] = 'GEOLocate found nothing',
    );
    rejects(
      'a typed outcome with nothing after it',
      (json) => _coverage(json, 'city')['reason'] = 'no_match: ',
    );
    rejects(
      'a receipt for another field',
      (json) => _coverage(json, 'city')['field_key'] = 'county',
    );
    rejects('searched and exhausted receipts mixed', (json) {
      final question =
          fixtureField(json, 'city')['checkpoint']['resolution']['question']
              as Map<String, dynamic>;
      question['coverage'] = [
        ...question['coverage'] as List,
        {
          'source_id': 'field_museum_ipt',
          'field_key': 'city',
          'state': 'exhausted',
          'source_version': 'v1',
          'qualification_digest': 'a' * 64,
          'exact_join_attempted': true,
          'exact_join_proven': true,
          'query_digest': 'b' * 64,
          'receipt_ids': ['receipt'],
          'candidate_count': 0,
          'coverage_limit': 'Scoped',
          'reason': 'no_match',
        },
      ];
    });
  });

  testWidgets(
    'the research card shows a real geography question, not an unverifiable thread',
    (tester) async {
      final json = _serverThread();
      final thread = _decode(json);
      tester.view.physicalSize = const Size(640, 1600);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.light(),
          home: Builder(
            builder: (context) => MediaQuery(
              data: MediaQuery.of(context).copyWith(disableAnimations: true),
              child: Scaffold(
                body: SingleChildScrollView(
                  child: ResearchThreadCard(
                    scope: thread.scope,
                    recordRevision: 100,
                    fieldKey: 'city',
                    fieldLabel: 'City',
                    field: thread.field('city'),
                    networkState: ResearchNetworkState.ready,
                    onRefresh: () {},
                  ),
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pump();
      await tester.tap(find.text('Research'));
      await tester.pump();
      expect(find.text('Needs information'), findsOneWidget);
      expect(find.text('Which place does the label mean?'), findsOneWidget);
      expect(find.textContaining('could not be verified'), findsNothing);
    },
  );
}
