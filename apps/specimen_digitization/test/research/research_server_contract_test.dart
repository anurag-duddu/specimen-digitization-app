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
