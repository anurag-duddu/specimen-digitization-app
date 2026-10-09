// The rows a field with parts opens into, captured as a component.
//
// Why this is not a screen golden. No record the server writes today has
// `parts`, so no screen golden can draw a part row, and the screen goldens that
// exist must not change: a field without parts draws as it always did. This
// sheet draws the rows those goldens cannot, at the measure of a phone-width
// record pane where the tree has the least room, and at double text size where
// the chips move under the title. It is limited to that one job.
//
// The place tree is the worked example of subject 105526321, with its named
// place flagged and open. The elevation is subject 105526322, with an inferred
// unit and the metres that follow from it, both flagged and open.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/screens/workbench/field_parts.dart';
import 'package:specimen_digitization/src/screens/workbench/part_rows.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../screens/field_parts_fixture.dart';
import 'golden_harness.dart';

/// The measure of a phone-width record pane, where the tree has least room.
const double partRowsMeasure = 390;

void main() {
  final Map<String, (String, List<Map<String, dynamic>>, int)> sheets =
      <String, (String, List<Map<String, dynamic>>, int)>{
        // field key, parts, and the chips the sheet carries: one basis chip per
        // part and one check chip per part a person is asked about.
        'location': ('precise_location', locationParts(), 5),
        'elevation': ('elevation_from_m', inferredElevationParts(), 5),
      };

  for (final MapEntry<String, (String, List<Map<String, dynamic>>, int)> sheet
      in sheets.entries) {
    for (final double scale in <double>[1.0, 2.0]) {
      goldenThemes.forEach((String theme, Brightness brightness) {
        testWidgets(
          'part rows of the ${sheet.key} in $theme at ${scale}x text',
          (WidgetTester tester) async {
            final String fieldKey = sheet.value.$1;
            final FieldParts parts = FieldParts.read(
              sheet.value.$2,
              fieldKey: fieldKey,
            );
            expect(parts.ignored, isNull);
            await pumpGoldenComponent(
              tester,
              brightness: brightness,
              measure: partRowsMeasure,
              textScale: scale,
              child: FieldPartRows(
                specimenId: 'golden',
                fieldKey: fieldKey,
                parts: parts,
                evidence: partEvidence(),
                onCorrect: () {},
              ),
            );
            // A guard on the coverage rather than on the pixels, which run on
            // every platform including the Linux CI where the comparison skips.
            expect(find.byType(UiChip), findsNWidgets(sheet.value.$3));
            expect(find.text(FieldPartRows.checkChipLabel), findsWidgets);
            expect(find.text('Why'), findsWidgets);
            expect(tester.takeException(), isNull);
            await expectGoldenComponent(
              tester,
              'field-part-rows__${sheet.key}-measure-390__${theme}__text'
              '${scale.toStringAsFixed(1)}',
            );
          },
        );
      });
    }
  }
}
