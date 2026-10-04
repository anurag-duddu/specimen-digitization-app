import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/research/research_models.dart';

import 'research_fixture.dart';
import 'review_test_support.dart';

Map<String, dynamic> _coverage(Map<String, dynamic> json, String key) =>
    ((fixtureField(json, key)['checkpoint']['resolution']['question']
                    as Map)['coverage']
                as List)
            .single
        as Map<String, dynamic>;

void _expectRejected(Map<String, dynamic> json) => expect(
  () => unresolvedThread(json),
  throwsA(isA<ResearchContractException>()),
);

/// Turns habitat, a field outside geography, into a field that asks a person.
void _askAboutHabitat(
  Map<String, dynamic> json,
  Map<String, dynamic> coverage,
) {
  final field = fixtureField(json, 'habitat');
  field['work_state'] = 'waiting_human';
  final resolution = field['checkpoint']['resolution'] as Map<String, dynamic>;
  resolution['work_state'] = 'waiting_human';
  resolution['question'] = {
    'field_key': 'habitat',
    'question': 'Which habitat does the label name?',
    'reason': 'scoped_absence',
    'coverage': [coverage],
    'evidence_ids': <String>[],
  };
}

void main() {
  test('decodes the thread the real reader produced for unresolved fields', () {
    final thread = unresolvedThread();
    final country = thread.field('country')!;
    expect(country.workState, ResearchWorkState.waitingHuman);
    final review = country.review!;
    expect(review.questionReason, 'semantic_ambiguity');
    expect(review.candidates.map((item) => item.authorityId), [
      'geolocate:a863d52e6ff08fe2',
      'geolocate:a71cd5741681e8fa',
      'geolocate:3e5a153ca95eedd5',
    ]);
    expect(review.candidates.map((item) => item.rank), [1, 2, 3]);
    expect(review.candidates.first.label, 'MOUNT APO');
    expect(review.candidates.first.details, ['CENTRAL MINDANAO']);
    expect(review.candidates.first.distanceKm, 46);
    expect(review.candidates.first.sourceId, 'geolocate');
    final evidence = review.evidence.single;
    expect(evidence.outcome, 'ambiguous');
    expect(evidence.searchedText, 'Mount Apo');
    expect(evidence.quote, isNull);
    expect(review.candidates.first.evidenceId, evidence.evidenceId);
    expect(country.checkpoint!.resolution.question!.evidenceIds, [
      evidence.evidenceId,
    ]);
    expect(
      thread.field('province_state')!.review!.questionReason,
      'scoped_absence',
    );
    expect(thread.field('habitat')!.review!.questionReason, isNull);
    expect(thread.field('taxon')!.review, isNull);
  });

  test('a searched GEOLocate outcome is a legitimate question coverage', () {
    // The server loosened "human questions need exhausted sources" for this
    // case only (contracts.py _geolocate_unresolved). The app still demanded
    // exhausted coverage, so it refused every geography question as unverified.
    final json = unresolvedJson();
    expect(_coverage(json, 'country')['state'], 'searched');
    expect(_coverage(json, 'country')['source_id'], 'geolocate');
    expect(unresolvedThread(json).field('country')!.checkpoint, isNotNull);
  });

  test(
    'the same question with exhausted coverage is accepted outside geography',
    () {
      // The control for the refusals below: the scaffolding is a valid thread.
      final json = unresolvedJson();
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
        unresolvedThread(json).field('habitat')!.workState,
        ResearchWorkState.waitingHuman,
      );
    },
  );

  group('a question coverage the server would refuse is refused', () {
    void rejects(String name, void Function(Map<String, dynamic> json) change) {
      test(name, () {
        final json = unresolvedJson();
        change(json);
        _expectRejected(json);
      });
    }

    rejects(
      'a searched receipt from another source',
      (json) => _coverage(json, 'country')['source_id'] = 'gbif',
    );
    rejects(
      'a searched GEOLocate receipt for a field outside geography',
      (json) => _askAboutHabitat(json, {
        ..._coverage(json, 'country'),
        'field_key': 'habitat',
      }),
    );
    rejects(
      'a reason that does not lead with its typed outcome',
      (json) =>
          _coverage(json, 'country')['reason'] = 'GEOLocate was ambiguous',
    );
    rejects(
      'a typed outcome with nothing after it',
      (json) => _coverage(json, 'country')['reason'] = 'ambiguous: ',
    );
    rejects(
      'a receipt for another field',
      (json) => _coverage(json, 'country')['field_key'] = 'city',
    );
    rejects('searched and exhausted receipts mixed', (json) {
      final question =
          fixtureField(json, 'country')['checkpoint']['resolution']['question']
              as Map<String, dynamic>;
      question['coverage'] = [
        ...question['coverage'] as List,
        {
          'source_id': 'field_museum_ipt',
          'field_key': 'country',
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

  test('values carry the layer keys the server sends on every value', () {
    // FieldValue gained layer and derived_from (c8e4d931); the server dumps
    // both on every value, and the embedded schema forbade unknown keys.
    final json = researchFixture('failed-thread');
    void widen(Object? node) {
      if (node is Map<String, dynamic>) {
        if (node.containsKey('verbatim_by_observation')) {
          node['layer'] = null;
          node['derived_from'] = <String>[];
        }
        node.values.forEach(widen);
      } else if (node is List) {
        node.forEach(widen);
      }
    }

    widen(json);
    final thread = ResearchThread.fromJson(
      json,
      expectedScope: trustedResearchScope(),
    );
    expect(thread.field('country')!.value.json['layer'], isNull);
    expect(thread.field('country')!.value.json['derived_from'], isEmpty);
  });

  test('a thread from a server that predates the review still decodes', () {
    final thread = fixtureThread();
    expect(thread.fields.every((field) => field.review == null), isTrue);
  });

  group('the review contract is closed', () {
    void rejects(
      String name,
      void Function(Map<String, dynamic> review) change,
    ) {
      test(name, () {
        final json = unresolvedJson();
        change(reviewOf(json, 'country'));
        _expectRejected(json);
      });
    }

    rejects('an unknown review key', (review) => review['extra'] = 1);
    rejects(
      'an unknown question reason',
      (review) => review['question_reason'] = 'other',
    );
    rejects(
      'an unknown candidate key',
      (review) => (review['candidates'] as List).first['coordinates'] = [1, 2],
    );
    rejects(
      'a candidate rank that is not an integer',
      (review) => (review['candidates'] as List).first['rank'] = '1',
    );
    rejects(
      'an evidence item without its source',
      (review) => (review['evidence'] as List).first.remove('source_id'),
    );
    rejects(
      'a not-shown count that is not an integer',
      (review) => review['candidates_not_shown'] = 'many',
    );
  });
}
