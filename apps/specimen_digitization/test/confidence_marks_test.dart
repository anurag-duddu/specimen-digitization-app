// The confidence pass's marks (field_research/confidence.py): a value a
// cleared record carries that something in the run argues against is marked
// on its field, `marked:<field>:<label>:<why>`. Each why's words among a
// record's blockers and in the decision sheet's reason chip.

import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/blockers.dart';
import 'package:specimen_digitization/src/settlement_codes.dart';

/// One case per why: the field it marks in the run, the field's name, the
/// detail and the chip's short phrase.
const List<(String, String, String, String, String)> cases = [
  (
    'readers_differ',
    'date_visited_from',
    'Collection start date',
    'The two readings of this label differ here, and only the image check '
        'chose this one. Compare it with the label.',
    'the readings differ here',
  ),
  (
    'follows_marked',
    'date_visited_to',
    'Collection end date',
    'This value was worked out from another field that is marked for '
        'review. Check that field first.',
    'it comes from a marked field',
  ),
  (
    'extent',
    'precise_location',
    'Locality',
    'Both readings give a longer text for this field than was kept. Check '
        'where it ends on the label.',
    'the readings give a longer text',
  ),
  (
    'not_collection_code',
    'collection_code',
    'Collection code',
    'Only the printed heading LEWIS COLLECTION is a collection code. This '
        'text looks like a slide, preparation or field number.',
    'not the collection heading',
  ),
  (
    'not_verbatim_date',
    'verbatim_dts',
    'Verbatim D/T/S',
    'Verbatim D/T/S keeps only dates that are not exact. This text is an '
        'exact date or holds a slide code.',
    'an exact date belongs in the dates',
  ),
];

Specimen marked(String field, String code) => Specimen(<String, dynamic>{
  'specimen_id': 'marked',
  'revision': 1,
  'regions': <Json>[
    <String, dynamic>{'region_id': 'L1'},
  ],
  'fields': <Json>[
    <String, dynamic>{
      'field_key': field,
      'state': 'supported',
      'literal_value': 'as read',
    },
  ],
  'reason_codes': <String>[code],
});

void main() {
  for (final (why, field, name, detail, phrase) in cases) {
    final String code = 'marked:$field:L1:$why';

    test('$why: the blocker names the field and says why in words', () {
      expect(confidenceWords[why], detail);
      final List<ClearanceBlocker> blockers = blockersFor(
        marked(field, code),
      ).where((ClearanceBlocker b) => b.rawCode == code).toList();
      expect(blockers, hasLength(1));
      expect(blockers.single.fieldKey, field);
      expect(blockers.single.message, contains(name));
      expect(blockers.single.detail, detail);
    });

    test('$why: the reason chip says why in a short phrase', () {
      final String? words = settlementPhrase(marked(field, code), code);
      expect(words, '$name is marked for review on Label 1: $phrase');
      expect(words!.length, lessThanOrEqualTo(100));
    });
  }

  test('every why of the confidence pass has words', () {
    expect(confidenceWords.keys.toSet(), <String>{
      'readers_differ',
      'follows_marked',
      'extent',
      'not_collection_code',
      'not_verbatim_date',
    });
  });
}
