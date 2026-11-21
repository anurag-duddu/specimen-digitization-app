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

  // With the clearing rule (plan WP K1) a mark on an optional field holds
  // nothing: it arrives in `open_reason_codes` on a cleared record, and the
  // field still needs attention, in the same words.
  for (final (String code, String words) in <(String, String)>[
    (differs, secondOpinionDiffersWords),
    (notChecked, secondOpinionNotCheckedWords),
  ]) {
    test('$code on a cleared record flags its field, not the record', () {
      final Specimen cleared = Specimen(<String, dynamic>{
        ...held(code).data,
        'disposition': 'cleared',
        'reason_codes': <String>[],
        'open_reason_codes': <String>[code],
      });
      expect(blockersFor(cleared), isEmpty);
      final List<ClearanceBlocker> attention = fieldAttentionFor(cleared);
      expect(attention, hasLength(1));
      expect(attention.single.fieldKey, 'habitat');
      expect(attention.single.detail, words);
    });
  }

  // Lane H3: a blank field the independent reading gives a value for is
  // marked with no label (`marked:<field>::second_opinion_differs`). It
  // flags the blank field on a cleared record in the same words, and its
  // chip names no label.
  test(
    'a blank field the second opinion fills is flagged, naming no label',
    () {
      const String blank = 'marked:habitat::second_opinion_differs';
      final Specimen cleared = Specimen(<String, dynamic>{
        ...held(blank).data,
        'fields': <Json>[
          <String, dynamic>{'field_key': 'habitat', 'state': 'not_present'},
        ],
        'disposition': 'cleared',
        'reason_codes': <String>[],
        'open_reason_codes': <String>[blank],
      });
      expect(blockersFor(cleared), isEmpty);
      final List<ClearanceBlocker> attention = fieldAttentionFor(cleared);
      expect(attention, hasLength(1));
      expect(attention.single.fieldKey, 'habitat');
      expect(attention.single.detail, secondOpinionDiffersWords);
      final String? phrase = settlementPhrase(cleared, blank);
      expect(
        phrase,
        endsWith('is marked for review: an independent reading differs'),
      );
      expect(phrase, isNot(contains('Label')));
    },
  );

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
