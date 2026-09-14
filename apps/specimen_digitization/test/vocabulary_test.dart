import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/vocabulary.dart';

void main() {
  group('vocabularyLabel', () {
    test('renames the queue values the vocabulary table renames', () {
      expect(vocabularyLabel('needs_human_review'), 'Needs review');
      expect(vocabularyLabel('cleared'), 'Cleared');
      expect(vocabularyLabel('deferred'), 'Deferred');
      expect(vocabularyLabel('processing_blocked'), 'Blocked');
      expect(vocabularyLabel('duplicate'), 'Already in collection');
      expect(vocabularyLabel('dead_letter'), 'Stopped after repeated failures');
    });

    test('renders absence as words, never as a value', () {
      expect(vocabularyLabel('unmeasured'), 'Not measured');
      expect(vocabularyLabel('uncalibrated'), 'Not calibrated');
    });

    test('names evidence states in sentence case', () {
      expect(vocabularyLabel('not_present'), 'Not present');
      expect(vocabularyLabel('not_applicable'), 'Not applicable');
      expect(vocabularyLabel('unresolved'), 'Unresolved');
    });

    test('retires internal words inside values the table does not name', () {
      expect(
        vocabularyLabel('segmentation_pending'),
        'label detection pending',
      );
      expect(vocabularyLabel('preflight_blocked'), 'server check blocked');
      expect(vocabularyLabel('revision_mismatch'), 'version mismatch');
      expect(vocabularyLabel('digest_mismatch'), 'checksum mismatch');
    });

    test('falls back to plain English for an unknown value', () {
      expect(vocabularyLabel('numeral_disagreement'), 'numeral disagreement');
      expect(vocabularyLabel(''), '');
    });

    test('never leaks a snake_case token to the screen', () {
      for (final value in <String>[
        'needs_human_review',
        'processing_blocked',
        'external_outcome_unknown',
        'memory_limit_unavailable',
      ]) {
        expect(vocabularyLabel(value), isNot(contains('_')));
      }
    });
  });

  group('environmentLabel', () {
    test('is sentence case and never shouted', () {
      expect(environmentLabel('synthetic'), 'Test');
      expect(environmentLabel('staging'), 'Staging');
      expect(environmentLabel(''), 'Unnamed');
    });
  });

  group('specimen status', () {
    test('reads the queue name a reviewer knows', () {
      const needsReview = Specimen({
        'specimen_id': 's',
        'disposition': 'needs_human_review',
      });
      const cleared = Specimen({'specimen_id': 's', 'disposition': 'cleared'});
      expect(needsReview.status, 'Needs review');
      expect(cleared.status, 'Cleared');
    });
  });

  group('reason strings', () {
    test('are one constant each and contain the fix', () {
      expect(reasonRequired, 'Enter a reason for this decision.');
      expect(reasonHelperText, contains('audit history'));
    });
  });
}
