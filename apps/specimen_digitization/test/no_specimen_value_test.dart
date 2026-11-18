// The empty-record guard's reason (field_research/step.py NO_SPECIMEN_VALUE, plan
// WP S1): its words in a list row and among a record's blockers.

import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/blockers.dart';

const String words =
    'No field describes the specimen. Check the labels in the photograph';

void main() {
  test('a list row words the empty-record reason', () {
    expect(reviewIssueSummary('no_specimen_value'), words);
  });

  test('the empty-record reason blocks the record in words', () {
    final Specimen specimen = Specimen(<String, dynamic>{
      'specimen_id': 'empty',
      'revision': 1,
      'regions': <Json>[
        <String, dynamic>{'region_id': 'L1'},
      ],
      'fields': <Json>[],
      'reason_codes': <String>['no_specimen_value'],
    });
    final List<ClearanceBlocker> blockers = blockersFor(specimen);
    expect(
      blockers.where((ClearanceBlocker b) => b.rawCode == 'no_specimen_value'),
      hasLength(1),
    );
    expect(
      blockers
          .firstWhere((ClearanceBlocker b) => b.rawCode == 'no_specimen_value')
          .message,
      words,
    );
  });
}
