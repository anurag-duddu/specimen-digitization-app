// The hold the slide's QR code adds (field_research/catalogue_code.py DIFFERS):
// a catalog number settled from the label whose number is not the code's,
// `marked:fmnh_ins_number:<label>:barcode_differs`. Its words among a record's
// blockers and in the decision sheet's reason chip.

import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/blockers.dart';
import 'package:specimen_digitization/src/settlement_codes.dart';

const String code = 'marked:fmnh_ins_number:L1:barcode_differs';
const String words =
    'The catalog number read from the label and the number in the slide\'s QR '
    'code differ. Compare them.';

Specimen held() => Specimen(<String, dynamic>{
  'specimen_id': 'held',
  'revision': 1,
  'regions': <Json>[
    <String, dynamic>{'region_id': 'L1'},
  ],
  'fields': <Json>[
    <String, dynamic>{
      'field_key': 'fmnh_ins_number',
      'state': 'supported',
      'literal_value': '4486518',
    },
  ],
  'reason_codes': <String>[code],
});

void main() {
  test('the words say which two numbers differ and what to do', () {
    expect(barcodeDiffersWords, words);
  });

  test('the barcode hold blocks the catalog number in words', () {
    final List<ClearanceBlocker> blockers = blockersFor(
      held(),
    ).where((ClearanceBlocker b) => b.rawCode == code).toList();
    expect(blockers, hasLength(1));
    expect(blockers.single.fieldKey, 'fmnh_ins_number');
    expect(blockers.single.message, contains('Catalog number'));
    expect(blockers.single.detail, words);
  });

  test('the reason chip says why in a short phrase', () {
    expect(
      settlementPhrase(held(), code),
      'Catalog number is marked for review on Label 1: '
      'the label and its QR code differ',
    );
  });
}
