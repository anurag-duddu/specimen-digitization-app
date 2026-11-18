// Plan WP K1's two research codes (field_research/step.py): an optional field
// research could not finish (INCOMPLETE, the field's own reason) and research
// given up for the run as a whole (GIVEN_UP_REASON, which holds the record).
// `no_specimen_value` is no longer produced.

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

  test('research given up for the run is worded in a list row', () {
    expect(
      reviewIssueSummary('field_research_given_up'),
      'Field research stopped at a processing limit before every field was checked',
    );
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
