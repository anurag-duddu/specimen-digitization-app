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

  group('what was written, by whom, and what settled it (UI.md T2.3)', () {
    const List<AttributedText> twoReaders = <AttributedText>[
      (source: 'Reader one · raw reading', text: 'GUATEMALA'),
      (source: 'Reader two · raw reading', text: 'GUATEMALA.'),
    ];

    testWidgets('each text stands under its source, in As written', (
      WidgetTester tester,
    ) async {
      await pumpComponent(
        tester,
        const SizedBox(
          width: 700,
          child: FieldRow(
            name: 'Country',
            state: SpecimenStatus.unresolved,
            writtenBy: twoReaders,
          ),
        ),
      );
      final double label = tester.getTopLeft(find.text('As written')).dy;
      final double readAs = tester.getTopLeft(find.text('Read as')).dy;
      for (final String text in <String>[
        'Reader one · raw reading',
        'GUATEMALA',
        'Reader two · raw reading',
        'GUATEMALA.',
      ]) {
        expect(
          tester.getTopLeft(find.text(text)).dy,
          inExclusiveRange(label, readAs),
        );
      }
      expect(
        tester.getTopLeft(find.text('Reader one · raw reading')).dy,
        lessThan(tester.getTopLeft(find.text('GUATEMALA')).dy),
      );
      expect(find.text('As written: GUATEMALA and 1 more'), findsOneWidget);
    });

    testWidgets('a screen reader hears each text with its source', (
      WidgetTester tester,
    ) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      await pumpComponent(
        tester,
        const SizedBox(
          width: 700,
          child: FieldRow(
            name: 'Country',
            state: SpecimenStatus.unresolved,
            writtenBy: twoReaders,
          ),
        ),
      );
      expect(
        find.bySemanticsLabel(
          RegExp(
            'As written: Reader one · raw reading, GUATEMALA; '
            'Reader two · raw reading, GUATEMALA',
          ),
        ),
        findsOneWidget,
      );
      handle.dispose();
    });

    testWidgets('source lines stand in place of the authority line', (
      WidgetTester tester,
    ) async {
      await pumpComponent(
        tester,
        const SizedBox(
          width: 700,
          child: FieldRow(
            name: 'Country',
            state: SpecimenStatus.supported,
            asWritten: 'GUATEMALA',
            authority: 'Authority match fixture-place',
            evidence: <String>[
              'Google Maps supports this value · place ID fixture-place',
            ],
          ),
        ),
      );
      expect(
        find.text('Google Maps supports this value · place ID fixture-place'),
        findsOneWidget,
      );
      expect(find.text('Authority match fixture-place'), findsNothing);
    });

    testWidgets('a note under Read as says how it was derived', (
      WidgetTester tester,
    ) async {
      const String note = "Century from the profile's rule: 1900s";
      final SemanticsHandle handle = tester.ensureSemantics();
      await pumpComponent(
        tester,
        const SizedBox(
          width: 700,
          child: FieldRow(
            name: 'Date collected',
            state: SpecimenStatus.supported,
            asWritten: '12.v.78',
            readAs: '1978-05-12',
            readAsNote: note,
          ),
        ),
      );
      expect(
        tester.getTopLeft(find.text(note)).dy,
        greaterThan(tester.getTopLeft(find.text('1978-05-12')).dy),
      );
      expect(
        tester.getSemantics(find.text(note)),
        matchesSemantics(label: '1978-05-12\n$note'),
        reason: 'the note is heard with the value it explains',
      );
      handle.dispose();
    });

    testWidgets('a note under As written says who settled the value', (
      WidgetTester tester,
    ) async {
      const String note = 'Reader two · raw reading · settled the value';
      final SemanticsHandle handle = tester.ensureSemantics();
      await pumpComponent(
        tester,
        const SizedBox(
          width: 700,
          child: FieldRow(
            name: 'Country',
            state: SpecimenStatus.supported,
            asWritten: 'GUATEMALA',
            asWrittenNote: note,
          ),
        ),
      );
      expect(
        tester.getTopLeft(find.text(note)).dy,
        greaterThan(tester.getTopLeft(find.text('GUATEMALA')).dy),
      );
      expect(
        tester.getSemantics(find.text(note)),
        matchesSemantics(label: 'GUATEMALA\n$note'),
        reason: 'the note is heard with the text it explains',
      );
      handle.dispose();
    });

    testWidgets('a note under attributed texts stands under all of them', (
      WidgetTester tester,
    ) async {
      const String note =
          'Label 2 · Reader one · raw reading · settled the value';
      final SemanticsHandle handle = tester.ensureSemantics();
      await pumpComponent(
        tester,
        const SizedBox(
          width: 700,
          child: FieldRow(
            name: 'Country',
            state: SpecimenStatus.supported,
            writtenBy: <AttributedText>[
              (
                source: 'Label 1 · Reader one · decided transcript',
                text: 'GUATEMALA',
              ),
              (
                source: 'Label 2 · Reader two · decided transcript',
                text: 'Guatemala',
              ),
            ],
            asWrittenNote: note,
          ),
        ),
      );
      expect(
        tester.getTopLeft(find.text(note)).dy,
        greaterThan(tester.getTopLeft(find.text('Guatemala')).dy),
      );
      expect(
        tester.getSemantics(find.text(note)),
        matchesSemantics(label: note),
        reason: 'it is about every text, so it joins none of them',
      );
      handle.dispose();
    });

    testWidgets('meets the guidelines in both themes', (
      WidgetTester tester,
    ) async {
      for (final ThemeData theme in productThemes.values) {
        await pumpComponent(
          tester,
          SizedBox(
            width: 700,
            child: FieldRow(
              name: 'Country',
              state: SpecimenStatus.unresolved,
              writtenBy: twoReaders,
              readAs: '1978-05-12',
              readAsNote: "Century from the profile's rule: 1900s",
              evidence: const <String>[
                'GBIF decides this value · species/1111111',
              ],
              onEdit: (FieldLayer _) {},
            ),
          ),
          theme: theme,
        );
        await expectAccessible(tester);
      }
    });
  });
}
