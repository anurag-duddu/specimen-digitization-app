import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/screens/workbench/field_presentation.dart';
import 'package:specimen_digitization/src/screens/workbench/pending_changes.dart';

void main() {
  test('review, absence and supported completion are independent', () {
    for (final (state, value, issues, review, missing, complete) in [
      ('supported', 'Philippines', false, false, false, true),
      ('supported', 'Philippines', true, true, false, false),
      ('supported', ' ', false, true, true, false),
      ('not_present', null, false, false, true, false),
      ('not_present', null, true, true, true, false),
      ('not_applicable', null, false, false, false, false),
      ('not_applicable', null, true, true, false, false),
      ('ambiguous', 'Manila', false, true, false, false),
      ('unresolved', null, false, true, true, false),
      ('unreadable', null, false, true, true, false),
      ('unknown', null, false, true, true, false),
      ('future-state', 'Manila', false, true, false, false),
      (null, null, false, true, true, false),
    ]) {
      final result = fieldReviewStatus({
        'state': state,
        'literal_value': value,
      }, hasIssues: issues);
      expect(result.needsReview, review, reason: '$state / $value / $issues');
      expect(result.isMissing, missing, reason: '$state / $value / $issues');
      expect(
        result.isSettledValue,
        complete,
        reason: '$state / $value / $issues',
      );
    }
  });

  test(
    'value presence matches displayed layers, not observation transcripts',
    () {
      expect(
        fieldReviewStatus({
          'state': 'supported',
          'normalized': ' ',
          'parsed_value': null,
          'literal_value': 'Manila',
        }).isSettledValue,
        isTrue,
      );
      final transcriptOnly = fieldReviewStatus({
        'state': 'supported',
        'verbatim_by_observation': {'reader-a': 'A whole specimen label'},
      });
      expect(transcriptOnly.isMissing, isTrue);
      expect(transcriptOnly.needsReview, isTrue);
      expect(transcriptOnly.isSettledValue, isFalse);
    },
  );

  test('unsaved changes stay in review and do not inherit stored values', () {
    final stored = {'state': 'supported', 'literal_value': 'Manila'};
    final pendingValue = fieldReviewStatus(
      stored,
      pending: const PendingFieldChange(
        fieldKey: 'city',
        displayName: 'City',
        state: 'supported',
        literal: 'Davao',
      ),
    );
    expect(pendingValue.needsReview, isTrue);
    expect(pendingValue.isSettledValue, isFalse);
    expect(pendingValue.isMissing, isFalse);
    final pendingAbsence = fieldReviewStatus(
      stored,
      pending: const PendingFieldChange(
        fieldKey: 'city',
        displayName: 'City',
        state: 'not_present',
      ),
    );
    expect(pendingAbsence.needsReview, isTrue);
    expect(pendingAbsence.isMissing, isTrue);
    expect(pendingAbsence.isSettledValue, isFalse);
  });
}
