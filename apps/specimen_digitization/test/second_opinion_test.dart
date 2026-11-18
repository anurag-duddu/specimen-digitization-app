// The marks the fields' second opinion adds (field_research/second_opinion.py):
// `marked:<field>:<label>:second_opinion_differs`, when an independent reading
// of the labels gives the field another value or none, and
// `marked:<field>:<label>:second_opinion_not_checked`, when that reading did
// not run. Their words among a record's blockers and in the reason chip.

import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/blockers.dart';
import 'package:specimen_digitization/src/settlement_codes.dart';

const String differs = 'marked:habitat:L1:second_opinion_differs';
const String notChecked = 'marked:habitat:L1:second_opinion_not_checked';

Specimen held(String code) => Specimen(<String, dynamic>{
  'specimen_id': 'held',
  'revision': 1,
  'regions': <Json>[
    <String, dynamic>{'region_id': 'L1'},
  ],
  'fields': <Json>[
    <String, dynamic>{
      'field_key': 'habitat',
      'state': 'supported',
      'literal_value': 'Shrubs, mostly forest',
    },
  ],
  'reason_codes': <String>[code],
});

void main() {
  test('the differs words say what was found and what to do', () {
    expect(
      secondOpinionDiffersWords,
      'An independent reading of the labels gives a different value. Check '
      'this value against the image.',
    );
  });

  test('the not-checked words say the value is not confirmed', () {
    expect(
      secondOpinionNotCheckedWords,
      'The independent reading of the labels did not run, so this value is '
      'not confirmed. Check it against the image.',
    );
  });

  test('a differing second opinion blocks the field in words', () {
    final List<ClearanceBlocker> blockers = blockersFor(
      held(differs),
    ).where((ClearanceBlocker b) => b.rawCode == differs).toList();
    expect(blockers, hasLength(1));
    expect(blockers.single.fieldKey, 'habitat');
    expect(blockers.single.detail, secondOpinionDiffersWords);
  });

  test('an unchecked value blocks the field in words', () {
    final List<ClearanceBlocker> blockers = blockersFor(
      held(notChecked),
    ).where((ClearanceBlocker b) => b.rawCode == notChecked).toList();
    expect(blockers, hasLength(1));
    expect(blockers.single.fieldKey, 'habitat');
    expect(blockers.single.detail, secondOpinionNotCheckedWords);
  });

  test('an agreeing reading is a field note, never a blocker', () {
    final Specimen agreed = Specimen(<String, dynamic>{
      ...held(differs).data,
      'reason_codes': <String>[],
      'validation_findings': <Json>[
        <String, dynamic>{
          'rule_id': 'second_opinion',
          'severity': 'info',
          'field_key': 'habitat',
          'reason_code': 'second_opinion_agrees:habitat',
        },
      ],
    });
    expect(blockersFor(agreed), isEmpty);
    final List<ClearanceBlocker> notes = fieldNotesFor(agreed);
    expect(notes, hasLength(1));
    expect(notes.single.fieldKey, 'habitat');
    expect(notes.single.message, contains(secondOpinionAgreesWords));
  });

  test('the reason chips say why in a short phrase', () {
    expect(
      settlementPhrase(held(differs), differs),
      endsWith(
        'is marked for review on Label 1: an independent reading differs',
      ),
    );
    expect(
      settlementPhrase(held(notChecked), notChecked),
      endsWith(
        'is marked for review on Label 1: not confirmed by an independent '
        'reading',
      ),
    );
  });
}
