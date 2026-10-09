// A field row that carries a basis chip, captured as a component.
//
// Why this is not a screen golden. The workbench goldens draw a record whose
// fields carry no `layer`, so no row there has a basis and none shows a chip;
// they hold the four-group layout only. This sheet draws the rows the other
// goldens cannot: one of each chip beside its title, and, at double text size,
// the chip moved under the text because the title needs the whole line
// (design 11, section 3.3). It is limited to that one job.

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
        // A guard on the coverage rather than on the pixels, which run on
        // every platform including the Linux CI where the comparison skips.
        expect(find.byType(UiChip), findsNWidgets(4));
        for (final String label in <String>[
          'As written',
          'Derived',
          'Inferred',
        ]) {
          expect(
            find.byWidgetPredicate(
              (Widget w) => w is UiChip && w.label == label,
            ),
            findsWidgets,
            reason: label,
          );
        }
        expect(tester.takeException(), isNull);
        await expectGoldenComponent(
          tester,
          'field-basis-chip__measure-390__${theme}__text${scale.toStringAsFixed(1)}',
        );
      });
    });
  }
}
