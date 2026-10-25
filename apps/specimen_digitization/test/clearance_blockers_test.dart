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
  test('message-less provenance notes use their recorded meaning', () {
    final specimen = Specimen({
      'fields': [
        {
          'field_key': 'country',
          'state': 'supported',
          'literal_value': 'Philippines',
        },
      ],
      'validation_findings': [
        for (final code in ['transcript_literal', 'near_spelling'])
          {'field_key': 'country', 'severity': 'info', 'reason_code': code},
      ],
    });
    expect(blockersFor(specimen), isEmpty);
    expect(fieldNotesFor(specimen).map((note) => note.message), [
      'Read from the label transcript',
      'Matched using a close spelling',
    ]);
  });

  test(
    'warning and info findings retain context without creating blockers',
    () {
      final specimen = Specimen({
        'specimen_id': 'context',
        'fields': [
          {
            'field_key': 'country',
            'state': 'supported',
            'literal_value': 'Philippines',
          },
        ],
        'validation_findings': [
          {
            'field_key': 'country',
            'severity': 'info',
            'rule_id': 'transcript_literal',
            'message': 'The label states P.I.',
          },
          {
            'field_key': 'country',
            'severity': 'warning',
            'rule_id': 'normalization_note',
            'message': 'Original punctuation retained in the label wording.',
          },
        ],
      });
      expect(blockersFor(specimen), isEmpty);
      final notes = fieldNotesFor(specimen);
      expect(notes, hasLength(2));
      expect(notes.every((note) => !note.isBlocking), isTrue);
      expect(
        notes.map((note) => note.message),
        contains('The label states P.I.'),
      );
    },
  );

  test('context cannot suppress an identical actual blocking reason', () {
    final specimen = Specimen({
      'specimen_id': 'context-plus-gate',
      'fields': [
        {
          'field_key': 'country',
          'state': 'supported',
          'literal_value': 'Philippines',
        },
      ],
      'reason_codes': ['evidence_missing:country'],
      'validation_findings': [
        {
          'field_key': 'country',
          'severity': 'info',
          'reason_code': 'evidence_missing:country',
          'message': 'Retained note',
        },
      ],
    });
    final blockers = blockersFor(specimen);
    expect(blockers, hasLength(1));
    expect(blockers.single.isBlocking, isTrue);
    expect(blockers.single.fieldKey, 'country');
    expect(fieldNotesFor(specimen).single.message, 'Retained note');
  });

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

  // The safety property: distinct means exactly distinct, as the server
  // counts it. A client that normalised case or spacing would hide real
  // disagreements, and nothing else would notice.
  test('readings that differ only in case or spacing still differ', () {
    for (final List<String> pair in <List<String>>[
      <String>['Chicago 1912', 'chicago 1912'],
      <String>['Chicago 1912', 'Chicago  1912'],
      <String>['Chicago 1912', 'Chicago 1912 '],
    ]) {
      expect(
        messages(pilotRecord(alternatives: pair)),
        contains('Two readings differ for Label 1'),
        reason: pair.join(' | '),
      );
    }
  });

  test('three distinct readings are counted in words', () {
    expect(
      messages(
        pilotRecord(
          alternatives: <String>[
            'Chicago 1912',
            'Chicago 1917',
            'Chicago 1911',
          ],
        ),
      ),
      contains('Three readings differ for Label 1'),
    );
  });

  test('a transcription with no alternatives is judged by its readings', () {
    final Specimen specimen = Specimen(<String, dynamic>{
      ...pilotRecord(alternatives: const <String>[]).data,
      'transcriptions': <Json>[
        <String, dynamic>{'region_id': 'r1', 'resolved': false},
      ],
      'observations': <Json>[
        <String, dynamic>{'region_id': 'r1', 'literal_text': 'Chicago 1912'},
        <String, dynamic>{'region_id': 'r1', 'literal_text': 'Chicago 1917'},
      ],
    });
    expect(messages(specimen), contains('Two readings differ for Label 1'));
  });
}
