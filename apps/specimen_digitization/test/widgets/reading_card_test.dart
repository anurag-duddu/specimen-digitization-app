// The reading card: which model, which provider, and how it differs.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/widgets/diff_text.dart';
import 'package:specimen_digitization/src/widgets/reading_card.dart';

import 'harness.dart';

void main() {
  testWidgets('names the model and the provider and shows the literal', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      const SizedBox(
        width: 500,
        child: ReadingCard(
          modelName: 'Synthetic reading B',
          provider: 'Fixture provider',
          literal: 'Chicago 1913',
          reference: 'Chicago 1912',
        ),
      ),
    );
    expect(find.text('Synthetic reading B'), findsOneWidget);
    expect(find.text('Fixture provider'), findsOneWidget);
    expect(find.byType(DiffText), findsOneWidget);
    expect(find.text('Differs at 1 position'), findsOneWidget);
  });

  testWidgets('with no reference there is no comparison sentence', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      const SizedBox(
        width: 500,
        child: ReadingCard(
          modelName: 'Synthetic reading A',
          provider: 'Fixture provider',
          literal: 'Chicago 1912',
        ),
      ),
    );
    expect(find.textContaining('Differs at'), findsNothing);
    expect(find.textContaining('Matches the reference'), findsNothing);
  });

  testWidgets('the optional slots render when they are given', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      const SizedBox(
        width: 500,
        child: ReadingCard(
          modelName: 'Synthetic reading B',
          provider: 'Fixture provider',
          literal: 'Chicago 1913',
          executionDetails: Text('Latency: 1.4 seconds'),
          footerActions: Text('Support this reading'),
        ),
      ),
    );
    expect(find.text('Latency: 1.4 seconds'), findsOneWidget);
    expect(find.text('Support this reading'), findsOneWidget);
  });

  testWidgets('the slots are absent when they are not given', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      const SizedBox(
        width: 500,
        child: ReadingCard(
          modelName: 'Synthetic reading B',
          provider: 'Fixture provider',
          literal: 'Chicago 1913',
        ),
      ),
    );
    expect(find.textContaining('Latency'), findsNothing);
  });

  testWidgets('the selected state reaches the semantics tree', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await pumpComponent(
      tester,
      const SizedBox(
        width: 500,
        child: ReadingCard(
          modelName: 'Synthetic reading B',
          provider: 'Fixture provider',
          literal: 'Chicago 1913',
          selected: true,
        ),
      ),
    );
    expect(
      tester.getSemantics(find.byType(ReadingCard)),
      containsSemantics(isSelected: true),
    );
    handle.dispose();
  });

  testWidgets('renders in both themes and meets the guidelines', (
    WidgetTester tester,
  ) async {
    for (final ThemeData theme in productThemes.values) {
      await pumpComponent(
        tester,
        const SizedBox(
          width: 500,
          child: ReadingCard(
            modelName: 'Synthetic reading B',
            provider: 'Fixture provider',
            literal: 'Chicago 1913',
            reference: 'Chicago 1912',
          ),
        ),
        theme: theme,
      );
      await expectAccessible(tester);
    }
  });
}
