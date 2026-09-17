// The field row: three named slots, an abstention where a value is missing.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/widgets/field_row.dart';
import 'package:specimen_digitization/src/widgets/specimen_status.dart';
import 'package:specimen_digitization/src/widgets/status_chip.dart';

import '../ui_finders.dart';
import 'harness.dart';

void main() {
  testWidgets('names the field, its state and all three layers', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      const SizedBox(
        width: 600,
        child: FieldRow(
          name: 'Locality',
          state: SpecimenStatus.supported,
          asWritten: 'Chicago, Ills.',
          readAs: 'Chicago, Illinois',
          standardized: 'Chicago, Illinois, United States',
        ),
      ),
    );
    expect(find.text('Locality'), findsOneWidget);
    expect(find.byType(StatusChip), findsOneWidget);
    for (final FieldLayer layer in FieldLayer.values) {
      expect(find.text(layer.label), findsOneWidget);
    }
    expect(find.text('Chicago, Ills.'), findsOneWidget);
    expect(find.text('Chicago, Illinois'), findsOneWidget);
    expect(find.text('Chicago, Illinois, United States'), findsOneWidget);
  });

  testWidgets('the layers keep their order', (WidgetTester tester) async {
    await pumpComponent(
      tester,
      const SizedBox(
        width: 600,
        child: FieldRow(name: 'Locality', state: SpecimenStatus.supported),
      ),
    );
    final double written = tester.getTopLeft(find.text('As written')).dy;
    final double read = tester.getTopLeft(find.text('Read as')).dy;
    final double standard = tester.getTopLeft(find.text('Standardized')).dy;
    expect(written, lessThan(read));
    expect(read, lessThan(standard));
  });

  testWidgets('the required marker is in the name', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      const SizedBox(
        width: 600,
        child: FieldRow(
          name: 'Catalog number',
          state: SpecimenStatus.supported,
          required: true,
        ),
      ),
    );
    expect(find.text('Catalog number (required)'), findsOneWidget);
  });

  testWidgets('a missing layer shows the abstention, never a blank', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      const SizedBox(
        width: 600,
        child: FieldRow(
          name: 'Collector',
          state: SpecimenStatus.unreadable,
          asWritten: 'illegible',
        ),
      ),
    );
    expect(
      find.text('Unreadable'),
      findsNWidgets(3),
      reason: 'the chip plus the two missing layers',
    );
  });

  testWidgets('the edit callback names the layer it came from', (
    WidgetTester tester,
  ) async {
    final List<FieldLayer> edited = <FieldLayer>[];
    await pumpComponent(
      tester,
      SizedBox(
        width: 700,
        child: FieldRow(
          name: 'Locality',
          state: SpecimenStatus.supported,
          asWritten: 'Chicago, Ills.',
          readAs: 'Chicago, Illinois',
          standardized: 'Chicago, Illinois, United States',
          onEdit: edited.add,
        ),
      ),
    );
    await tester.tap(uiIconButton('Edit read as'));
    await tester.pumpAndSettle();
    expect(edited, <FieldLayer>[FieldLayer.readAs]);
  });

  testWidgets('the authority line and the findings slot render', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      const SizedBox(
        width: 700,
        child: FieldRow(
          name: 'Locality',
          state: SpecimenStatus.ambiguous,
          standardized: 'Chicago, Illinois, United States',
          authority: 'Matched in the gazetteer, accepted name',
          findings: Text('Two candidates scored the same'),
        ),
      ),
    );
    expect(
      find.text('Matched in the gazetteer, accepted name'),
      findsOneWidget,
    );
    expect(find.text('Two candidates scored the same'), findsOneWidget);
  });

  testWidgets('renders in both themes and meets the guidelines', (
    WidgetTester tester,
  ) async {
    for (final ThemeData theme in productThemes.values) {
      await pumpComponent(
        tester,
        SizedBox(
          width: 700,
          child: FieldRow(
            name: 'Locality',
            state: SpecimenStatus.supported,
            asWritten: 'Chicago, Ills.',
            readAs: 'Chicago, Illinois',
            standardized: 'Chicago, Illinois, United States',
            onEdit: (FieldLayer _) {},
          ),
        ),
        theme: theme,
      );
      await expectAccessible(tester);
    }
  });
}
