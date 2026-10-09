import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/field_presentation.dart';
import 'package:specimen_digitization/src/screens/workbench/value_basis.dart';
import 'package:specimen_digitization/src/vocabulary.dart';
import 'package:specimen_digitization/src/widgets/field_row.dart';

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

  group('field groups and basis words', () {
    // Section 4.2 (section titles), 4.13 (chips) and 6 (rules for agents).
    final words = <String, int>{
      for (final group in fieldReviewGroups) group: 32,
      for (final basis in ValueBasis.values) basis.label: 20,
    };

    test('stay inside the length budgets and the writing rules', () {
      expect(fieldReviewGroups.take(4), ['IDs', 'Collection', 'Date', 'Taxa']);
      for (final entry in words.entries) {
        final word = entry.key;
        expect(word.length, lessThanOrEqualTo(entry.value), reason: word);
        expect(
          word,
          matches(RegExp(r'^[A-Z]')),
          reason: '$word: sentence case',
        );
        expect(word, isNot(endsWith('.')), reason: '$word: no terminal period');
        for (final dash in [0x2014, 0x2013]) {
          expect(
            word,
            isNot(contains(String.fromCharCode(dash))),
            reason: '$word: no em-dash or en-dash',
          );
        }
        // Sentence case: no capital after the first letter of a plain word.
        if (word != 'IDs') {
          expect(word.substring(1), equals(word.substring(1).toLowerCase()));
        }
      }
    });

    test('name a basis in the words the layers already use', () {
      // "As written" is the first layer's label (section 3, "literal").
      expect(ValueBasis.asWritten.label, FieldLayer.asWritten.label);
      expect(ValueBasis.derived.label, 'Derived');
      expect(ValueBasis.inferred.label, 'Inferred');
      expect(vocabularyLabel('literal'), 'as written');
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
