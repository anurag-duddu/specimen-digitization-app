// The app's side of the shared field-review-words contract
// (tests/fixtures/field_review_words.json; the waiting-fields program, fix
// 1). The server's side is tests/test_field_review_words.py. The field rows
// are drawn and read by their words: "Review needed", "Not on labels", the
// settled check or none. The queue row's count is the server's summary the
// fixture names, and it must agree with the rows.

import 'dart:convert';
import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/field_presentation.dart';
import 'package:specimen_digitization/src/screens/workbench/fields_panel.dart';
import 'package:specimen_digitization/src/screens/workbench/pending_changes.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'ui_finders.dart';
import 'widgets/harness.dart';

/// The word a drawn field row reads as.
String rowWord(UiDisclosure row) {
  final String label = row.semanticsLabel!;
  if (label.contains('. Review needed')) return 'review';
  if (row.summary == notOnLabelsLabel) return 'no_source';
  if (row.collapsedIcon != null) return 'settled';
  return 'none';
}

void main() {
  final Map<String, dynamic> fixture =
      jsonDecode(
            File(
              '../../tests/fixtures/field_review_words.json',
            ).readAsStringSync(),
          )
          as Map<String, dynamic>;

  test('the app names the server\'s fields with no approved authority', () {
    expect(noApprovedAuthorityFields.toList()..sort(), <String>[
      for (final Object? key in fixture['no_approved_authority'] as List)
        key.toString(),
    ]);
  });

  group('an unknown IRN with no value', () {
    final Json irn = <String, dynamic>{
      'field_key': 'identified_by_irn',
      'state': 'unknown',
      'literal_value': ' ',
    };

    test('is not for review, and is missing', () {
      final FieldReviewStatus status = fieldReviewStatus(irn);
      expect(status.hasNoApprovedSource, isTrue);
      expect(status.needsReview, isFalse);
      expect(status.isMissing, isTrue);
      expect(status.isSettledValue, isFalse);
    });

    test('needs review when an issue names it', () {
      final FieldReviewStatus status = fieldReviewStatus(irn, hasIssues: true);
      expect(status.hasNoApprovedSource, isFalse);
      expect(status.needsReview, isTrue);
    });

    test('needs review while an edit to it is unsaved', () {
      final FieldReviewStatus status = fieldReviewStatus(
        irn,
        pending: const PendingFieldChange(
          fieldKey: 'identified_by_irn',
          displayName: 'Identified by IRN',
          state: 'supported',
          literal: '12345',
        ),
      );
      expect(status.hasNoApprovedSource, isFalse);
      expect(status.needsReview, isTrue);
    });

    test('another field left unknown still needs review', () {
      final FieldReviewStatus status = fieldReviewStatus(<String, dynamic>{
        ...irn,
        'field_key': 'date_identified',
      });
      expect(status.hasNoApprovedSource, isFalse);
      expect(status.needsReview, isTrue);
    });
  });

  for (final Object? raw in fixture['cases'] as List) {
    final Map<String, dynamic> item = raw! as Map<String, dynamic>;
    final Map<String, dynamic> fields = item['fields'] as Map<String, dynamic>;
    final Specimen specimen = Specimen(<String, dynamic>{
      'specimen_id': 'words',
      'revision': 1,
      'disposition': item['disposition'],
      'regions': <Json>[
        <String, dynamic>{'region_id': 'L1'},
      ],
      'fields': <Json>[
        for (final MapEntry<String, dynamic> entry in fields.entries)
          <String, dynamic>{
            'field_key': entry.key,
            'state': (entry.value as Map)['state'],
            'required': false,
            if ((entry.value as Map)['has_value'] == true)
              'literal_value': 'A value',
          },
      ],
      'reason_codes': const <String>[],
      'open_reason_codes': <String>[
        for (final Object? code in item['codes'] as List) code.toString(),
      ],
      'review_summary': item['summary'],
    });
    final Map<String, dynamic> status = item['status'] as Map<String, dynamic>;

    testWidgets('${item['name']}: each field row reads its word', (
      WidgetTester tester,
    ) async {
      await pumpComponent(
        tester,
        SingleChildScrollView(
          child: WorkbenchFields(
            specimen: specimen,
            anchors: const <String, GlobalKey>{},
            pending: const [],
            onPendingChanged: (_) {},
          ),
        ),
        size: const Size(900, 3200),
      );
      final Map<String, String> words = <String, String>{
        for (final Json field in specimen.fields)
          field['field_key'].toString(): rowWord(
            tester.widget<UiDisclosure>(uiDisclosure(fieldReviewName(field))),
          ),
      };
      expect(words, status);
      expect(tester.takeException(), isNull);
    });

    test('${item['name']}: the queue row counts what the rows show', () {
      expect(
        specimen.reviewSummary?.review,
        status.values.where((Object? word) => word == 'review').length,
      );
    });
  }
}
