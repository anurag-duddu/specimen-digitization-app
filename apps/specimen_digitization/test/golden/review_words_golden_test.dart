// The words a record's fields read (the waiting-fields program, fix 1): the
// Identified by IRN, which no label carries and no approved source looks up,
// reads "Not on labels" and is missing, not for review; a field a person must
// decide reads "Review needed"; a settled value keeps its check. Phone
// measure, normal and enlarged text, both themes.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/field_presentation.dart';
import 'package:specimen_digitization/src/screens/workbench/fields_panel.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'golden_harness.dart';

/// The measure of a phone-width record pane.
const double rowsMeasure = 390;

/// A cleared record with a field of each word.
final Specimen wordsRecord = Specimen(<String, dynamic>{
  'specimen_id': 'review-words-golden',
  'disposition': 'cleared',
  'regions': const <Json>[
    <String, dynamic>{'region_id': 'L1'},
  ],
  'fields': <Json>[
    <String, dynamic>{
      'field_key': 'country',
      'state': 'supported',
      'required': false,
      'literal_value': 'Guatemala',
    },
    <String, dynamic>{
      'field_key': 'county',
      'state': 'supported',
      'required': false,
      'literal_value': 'Yepocapa',
    },
    <String, dynamic>{
      'field_key': 'precise_location',
      'state': 'ambiguous',
      'required': false,
      'literal_value': 'Yepocapa, 4800ft',
    },
    <String, dynamic>{
      'field_key': 'identified_by_irn',
      'state': 'unknown',
      'required': false,
      'reason': 'No qualified determiner Parties identity',
    },
  ],
  'reason_codes': const <String>[],
  'open_reason_codes': const <String>[
    'marked:county:L1:second_opinion_differs',
    'mandatory_unresolved:precise_location',
  ],
});

void main() {
  for (final double scale in <double>[1.0, 2.0]) {
    goldenThemes.forEach((String theme, Brightness brightness) {
      final String text = scale.toStringAsFixed(1);
      testWidgets('field rows read their words in $theme at ${text}x text', (
        WidgetTester tester,
      ) async {
        await pumpGoldenComponent(
          tester,
          brightness: brightness,
          measure: rowsMeasure,
          textScale: scale,
          child: WorkbenchFields(
            specimen: wordsRecord,
            anchors: const <String, GlobalKey>{},
            pending: const [],
            onPendingChanged: (_) {},
          ),
        );
        final irn = find.byWidgetPredicate(
          (widget) =>
              widget is UiDisclosure && widget.title == 'Identified by IRN',
        );
        await tester.tap(
          find
              .descendant(
                of: irn,
                matching: find.byWidgetPredicate(
                  (widget) => widget is Pressable,
                ),
              )
              .first,
        );
        await tester.pumpAndSettle();
        expect(find.text('2 review · 0 missing'), findsOneWidget);
        expect(find.text('0 review · 1 missing'), findsOneWidget);
        expect(find.text(notOnLabelsWords), findsOneWidget);
        expect(find.text('Optional field · $notOnLabelsLabel'), findsOneWidget);
        expect(find.text('Unknown'), findsNothing);
        expect(tester.takeException(), isNull);
        await expectGoldenComponent(
          tester,
          'review-words-fields__measure-390__${theme}__text$text',
        );
      });
    });
  }
}
