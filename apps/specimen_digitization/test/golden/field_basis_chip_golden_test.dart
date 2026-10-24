// Field values stay concise until opened. This component image explicitly
// opens one field so its requirement, basis and source details can be reviewed
// alongside the neighboring collapsed values at normal and enlarged text.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/fields_panel.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'golden_harness.dart';

/// The measure of a phone-width record pane, where the chip has to fit.
const double chipMeasure = 390;

/// One chip of each kind, and one row with none.
final Specimen chipRecord = Specimen(<String, dynamic>{
  'specimen_id': 'basis-chip-golden',
  'regions': const <Json>[],
  'fields': <Json>[
    <String, dynamic>{
      'field_key': 'country',
      'state': 'supported',
      'required': true,
      'layer': 'settled',
      'literal_value': 'P.I.',
      'normalized': 'Philippines',
    },
    <String, dynamic>{
      'field_key': 'province_state',
      'state': 'supported',
      'layer': 'settled',
      'literal_value': 'Davao',
      'normalized': 'Davao',
    },
    <String, dynamic>{
      'field_key': 'city',
      'state': 'supported',
      'literal_value': 'Manila',
    },
    <String, dynamic>{
      'field_key': 'elevation_from_m',
      'state': 'supported',
      'layer': 'derived',
      'literal_value': "6400'",
      'normalized': '1950.72',
      'derived_from': <String>['elevation_from_ft'],
    },
    <String, dynamic>{
      'field_key': 'habitat',
      'state': 'supported',
      'layer': 'verbatim',
      'basis': 'inferred',
      'literal_value': 'Mossy forest',
    },
  ],
});

void main() {
  for (final double scale in <double>[1.0, 2.0]) {
    goldenThemes.forEach((String theme, Brightness brightness) {
      testWidgets('field rows with a basis chip in $theme at ${scale}x text', (
        WidgetTester tester,
      ) async {
        await pumpGoldenComponent(
          tester,
          brightness: brightness,
          measure: chipMeasure,
          textScale: scale,
          child: WorkbenchFields(
            specimen: chipRecord,
            anchors: const <String, GlobalKey>{},
            pending: const [],
            onPendingChanged: (_) {},
          ),
        );
        expect(find.byType(UiChip), findsNothing);
        final field = find.byWidgetPredicate(
          (widget) => widget is UiDisclosure && widget.title == 'Country',
        );
        final trigger = find
            .descendant(
              of: field,
              matching: find.byWidgetPredicate((widget) => widget is Pressable),
            )
            .first;
        await tester.tap(trigger);
        await tester.pumpAndSettle();
        expect(
          find.byWidgetPredicate(
            (widget) => widget is UiChip && widget.label == 'Derived',
          ),
          findsOneWidget,
        );
        expect(find.text('Required field · Supported'), findsOneWidget);
        expect(tester.takeException(), isNull);
        await expectGoldenComponent(
          tester,
          'field-basis-chip__measure-390__${theme}__text${scale.toStringAsFixed(1)}',
        );
      });
    });
  }
}
