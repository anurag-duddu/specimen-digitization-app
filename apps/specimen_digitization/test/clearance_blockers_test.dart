// What blocks clearance (UI.md T1.3 and T1.4).
//
// The pilot leaves every transcription unresolved, including those whose two
// readings are identical, and the workspace publishes each run reason twice.
// The list says the readings differ only when they do, and states each reason
// once.

import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/blockers.dart';

/// A pilot record at the review stop: one region, the given alternatives, and
/// the reasons the pilot records, published the way `workspace()` does.
Specimen pilotRecord({
  required List<String> alternatives,
  bool resolved = false,
  List<String> reasons = const <String>[],
}) => Specimen(<String, dynamic>{
  'specimen_id': 'pilot-1',
  'revision': 4,
  'regions': <Json>[
    <String, dynamic>{'region_id': 'r1'},
  ],
  'transcriptions': <Json>[
    <String, dynamic>{
      'region_id': 'r1',
      'resolved': resolved,
      'alternatives': alternatives,
      'alignment_status': 'policy_blocked',
    },
  ],
  'reason_codes': reasons,
  'validation_findings': <Json>[
    for (final String reason in reasons)
      <String, dynamic>{
        'rule_id': reason,
        'severity': 'hard',
        'outcome': 'fail',
        'reason_code': reason,
      },
  ],
});

List<String> messages(Specimen specimen) => blockersFor(
  specimen,
).map((ClearanceBlocker blocker) => blocker.message).toList();

void main() {
  test('identical readings are never said to differ', () {
    final List<String> said = messages(
      pilotRecord(alternatives: <String>['Chicago 1912']),
    );
    expect(said, contains('Transcription not resolved for Label 1'));
    expect(said.where((String m) => m.contains('differ')), isEmpty);
  });

  test('readings that differ are said to differ, once', () {
    final List<String> said = messages(
      pilotRecord(alternatives: <String>['Chicago 1912', 'Chicago 1917']),
    );
    expect(said.where((String m) => m == 'Two readings differ for Label 1'), [
      'Two readings differ for Label 1',
    ]);
  });

  test('a region with no reading text is still not resolved', () {
    expect(
      messages(pilotRecord(alternatives: const <String>[])),
      contains('Transcription not resolved for Label 1'),
    );
  });

  test('a resolved transcription blocks nothing', () {
    expect(
      messages(
        pilotRecord(
          alternatives: <String>['Chicago 1912', 'Chicago 1917'],
          resolved: true,
        ),
      ),
      isEmpty,
    );
  });

  test('each reason blocks clearance once', () {
    final List<ClearanceBlocker> blockers = blockersFor(
      pilotRecord(
        alternatives: <String>['Chicago 1912'],
        resolved: true,
        reasons: <String>[
          'pilot_risk_unmeasured',
          'institutional_policy_not_approved',
        ],
      ),
    );
    expect(blockers, hasLength(2));
  });

  test('a reason no finding states is still listed', () {
    final Specimen specimen = Specimen(<String, dynamic>{
      ...pilotRecord(alternatives: <String>['A'], resolved: true).data,
      'reason_codes': <String>['coverage_unconfirmed'],
    });
    expect(blockersFor(specimen), hasLength(1));
  });
}
