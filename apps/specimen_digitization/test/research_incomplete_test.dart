// The holding reason of an optional field research could not finish
// (field_research/step.py INCOMPLETE, plan WP K1): its words in a list row and
// among a record's blockers. `no_specimen_value` is no longer produced.

import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/blockers.dart';

const String words = 'was not checked before research stopped';

void main() {
  test('a list row words the reason after its field', () {
    final String summary = reviewIssueSummary('research_incomplete:country');
    expect(summary, contains(words));
    expect(summary.toLowerCase(), contains('country'));
  });

  test('the reason blocks the record on its field, in words', () {
    final Specimen specimen = Specimen(<String, dynamic>{
      'specimen_id': 'incomplete',
      'revision': 1,
      'regions': <Json>[
        <String, dynamic>{'region_id': 'L1'},
      ],
      'fields': <Json>[
        <String, dynamic>{'field_key': 'country', 'state': 'unresolved'},
      ],
      'reason_codes': <String>['research_incomplete:country'],
    });
    final List<ClearanceBlocker> blockers = blockersFor(specimen)
        .where(
          (ClearanceBlocker b) => b.rawCode == 'research_incomplete:country',
        )
        .toList();
    expect(blockers, hasLength(1));
    expect(blockers.single.message, contains(words));
  });
}
