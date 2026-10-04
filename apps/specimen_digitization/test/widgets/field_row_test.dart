// Field summaries state the value layer and actual state. Details stay optional.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/widgets/field_row.dart';
import 'package:specimen_digitization/src/widgets/specimen_status.dart';
import 'package:specimen_ui/specimen_ui.dart' show UiDisclosure;

import '../ui_finders.dart';
import 'harness.dart';

void main() {
  testWidgets(
    'one preview becomes three named layers without duplicate values',
    (WidgetTester tester) async {
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
      expect(find.byType(UiDisclosure), findsOneWidget);
      expect(
        find.text('Supported · Standardized: Chicago, Illinois, United States'),
        findsOneWidget,
      );
      expect(find.text('Chicago, Ills.'), findsNothing);
      expect(find.text('Chicago, Illinois'), findsNothing);
      expect(find.text('Chicago, Illinois, United States'), findsNothing);
      for (final FieldLayer layer in FieldLayer.values) {
        expect(find.text(layer.label), findsNothing);
      }
      await tester.tap(find.text('Locality'));
      await tester.pumpAndSettle();
      for (final FieldLayer layer in FieldLayer.values) {
        expect(find.text(layer.label), findsOneWidget);
      }
      expect(
        find.text('Supported · Standardized: Chicago, Illinois, United States'),
        findsNothing,
      );
      expect(find.text('Chicago, Ills.'), findsOneWidget);
      expect(find.text('Chicago, Illinois'), findsOneWidget);
      expect(find.text('Chicago, Illinois, United States'), findsOneWidget);
      await tester.tap(find.text('Locality'));
      await tester.pumpAndSettle();
      expect(
        find.text('Supported · Standardized: Chicago, Illinois, United States'),
        findsOneWidget,
      );
      expect(find.text('Chicago, Ills.'), findsNothing);
      expect(find.text('Chicago, Illinois'), findsNothing);
      expect(find.text('Chicago, Illinois, United States'), findsNothing);
      for (final FieldLayer layer in FieldLayer.values) {
        expect(find.text(layer.label), findsNothing);
      }
    },
  );

  testWidgets('the layers keep their order', (WidgetTester tester) async {
    await pumpComponent(
      tester,
      const SizedBox(
        width: 600,
        child: FieldRow(name: 'Locality', state: SpecimenStatus.supported),
      ),
    );
    await tester.tap(find.text('Locality'));
    await tester.pumpAndSettle();
    final double written = tester.getTopLeft(find.text('As written')).dy;
    final double read = tester.getTopLeft(find.text('Read as')).dy;
    final double standard = tester.getTopLeft(find.text('Standardized')).dy;
    expect(written, lessThan(read));
    expect(read, lessThan(standard));
    expect(find.text('Field state: Supported'), findsOneWidget);
    expect(find.text('Not recorded'), findsNWidgets(3));
    expect(find.text('Supported'), findsNothing);
  });

  testWidgets(
    'the required marker remains visible and announced when expanded',
    (WidgetTester tester) async {
      final semantics = tester.ensureSemantics();
      await pumpComponent(
        tester,
        const SizedBox(
          width: 600,
          child: FieldRow(
            name: 'Catalog number',
            state: SpecimenStatus.supported,
            required: true,
            asWritten: 'FMNH1001',
          ),
        ),
      );
      expect(find.text('Catalog number (required)'), findsOneWidget);
      expect(
        find.bySemanticsLabel(
          'Catalog number (required). Supported · As written: FMNH1001',
        ),
        findsOneWidget,
      );
      await tester.tap(find.text('Catalog number (required)'));
      await tester.pumpAndSettle();
      expect(find.text('Catalog number (required)'), findsOneWidget);
      expect(
        find.bySemanticsLabel('Catalog number (required)'),
        findsOneWidget,
      );
      expect(find.text('FMNH1001'), findsOneWidget);
      semantics.dispose();
    },
  );

  for (final required in [true, false]) {
    final requirement = required ? 'required' : 'optional';
    testWidgets(
      'a grouped $requirement field keeps its requirement in disclosure semantics',
      (WidgetTester tester) async {
        final semantics = tester.ensureSemantics();
        await pumpComponent(
          tester,
          SizedBox(
            width: 600,
            child: FieldRow(
              name: 'Catalog number',
              state: SpecimenStatus.supported,
              required: required,
              showRequirementMarker: false,
              asWritten: 'FMNH1001',
            ),
          ),
        );
        expect(find.text('Catalog number'), findsOneWidget);
        expect(find.text('Catalog number (required)'), findsNothing);
        final collapsedLabel =
            'Catalog number, $requirement. Supported · As written: FMNH1001';
        expect(find.bySemanticsLabel(collapsedLabel), findsOneWidget);
        await tester.tap(find.text('Catalog number'));
        await tester.pumpAndSettle();
        expect(find.bySemanticsLabel(collapsedLabel), findsNothing);
        expect(
          find.bySemanticsLabel('Catalog number, $requirement'),
          findsOneWidget,
        );
        expect(find.text('Supported · As written: FMNH1001'), findsNothing);
        expect(find.text('FMNH1001'), findsOneWidget);
        expect(find.text('As written'), findsOneWidget);
        await tester.tap(find.text('Catalog number'));
        await tester.pumpAndSettle();
        expect(find.bySemanticsLabel(collapsedLabel), findsOneWidget);
        expect(find.text('Supported · As written: FMNH1001'), findsOneWidget);
        expect(find.text('FMNH1001'), findsNothing);
        semantics.dispose();
      },
    );
  }

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
    expect(find.text('Unreadable · As written: illegible'), findsOneWidget);
    await tester.tap(find.text('Collector'));
    await tester.pumpAndSettle();
    expect(find.text('Unreadable · As written: illegible'), findsNothing);
    expect(find.text('illegible'), findsOneWidget);
    expect(
      find.text('Unreadable'),
      findsNWidgets(2),
      reason: 'each missing layer states its abstention',
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
    expect(uiIconButton('Edit read as'), findsNothing);
    await tester.tap(find.text('Locality'));
    await tester.pumpAndSettle();
    for (final FieldLayer layer in FieldLayer.values) {
      await tester.tap(uiIconButton('Edit ${layer.label.toLowerCase()}'));
      await tester.pumpAndSettle();
    }
    expect(edited, FieldLayer.values);
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
          findingCount: 1,
        ),
      ),
    );
    expect(find.text('Two candidates scored the same'), findsNothing);
    expect(find.textContaining('1 check to review'), findsOneWidget);
    expect(find.text('Matched in the gazetteer, accepted name'), findsNothing);
    await tester.tap(find.text('Locality'));
    await tester.pumpAndSettle();
    expect(
      find.text('Matched in the gazetteer, accepted name'),
      findsOneWidget,
    );
    expect(find.text('Two candidates scored the same'), findsOneWidget);
    await tester.tap(find.text('Locality'));
    await tester.pumpAndSettle();
    expect(find.text('Matched in the gazetteer, accepted name'), findsNothing);
    expect(find.text('Two candidates scored the same'), findsNothing);
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
      await tester.tap(find.text('Locality'));
      await tester.pumpAndSettle();
      await expectAccessible(tester);
      // Each theme starts with the same collapsed disclosure state.
      await tester.pumpWidget(const SizedBox());
    }
  });
}
