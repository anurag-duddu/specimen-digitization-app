// The app's side of the shared field-attention contract
// (tests/fixtures/field_attention.json, plan WP K1). The server's side is
// tests/test_field_attention_contract.py; both read the same fixture, so the
// field rows and the server's per-field counts map reason codes to fields the
// same way. The codes arrive as `open_reason_codes`, as on a cleared record.

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/blockers.dart';
import 'package:specimen_digitization/src/screens/workbench/field_presentation.dart';

void main() {
  final Map<String, dynamic> fixture =
      jsonDecode(
            File(
              '../../tests/fixtures/field_attention.json',
            ).readAsStringSync(),
          )
          as Map<String, dynamic>;

  for (final Object? raw in fixture['cases'] as List) {
    final Map<String, dynamic> item = raw! as Map<String, dynamic>;
    test(item['name'] as String, () {
      final Map<String, dynamic> fields =
          item['fields'] as Map<String, dynamic>;
      final Specimen specimen = Specimen(<String, dynamic>{
        'specimen_id': 'contract',
        'revision': 1,
        'disposition': 'cleared',
        'regions': <Json>[
          <String, dynamic>{'region_id': 'L1'},
          <String, dynamic>{'region_id': 'L2'},
        ],
        'fields': <Json>[
          for (final MapEntry<String, dynamic> entry in fields.entries)
            <String, dynamic>{
              'field_key': entry.key,
              'state': (entry.value as Map)['state'],
              if ((entry.value as Map)['has_value'] == true)
                'literal_value': 'A value',
            },
        ],
        'reason_codes': <String>[],
        'open_reason_codes': <String>[
          for (final Object? code in item['codes'] as List) code.toString(),
        ],
      });
      final List<ClearanceBlocker> attention = fieldAttentionFor(specimen);
      final List<String> needing = <String>[
        for (final Json field in specimen.fields)
          if (fieldReviewStatus(
            field,
            hasIssues: attention.any(
              (ClearanceBlocker issue) => issue.fieldKey == field['field_key'],
            ),
          ).needsReview)
            field['field_key'].toString(),
      ]..sort();
      expect(needing, <String>[
        for (final Object? key in item['attention'] as List) key.toString(),
      ]);
      expect(blockersFor(specimen), isEmpty);
    });
  }
}
