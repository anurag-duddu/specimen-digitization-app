// The empty state: title, one sentence, at most one action.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_symbols_icons/symbols.dart';
import 'package:specimen_digitization/src/widgets/empty_state.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'harness.dart';

void main() {
  testWidgets('renders the three parts in order', (WidgetTester tester) async {
    await pumpComponent(
      tester,
      EmptyState(
        icon: Symbols.inbox,
        title: 'No specimens yet',
        body: 'Upload a photograph to create the first record.',
        actionLabel: 'Add photographs',
        onAction: () {},
      ),
    );
    expect(find.text('No specimens yet'), findsOneWidget);
    expect(
      find.text('Upload a photograph to create the first record.'),
      findsOneWidget,
    );
    expect(find.widgetWithText(UiButton, 'Add photographs'), findsOneWidget);
    expect(
      tester.getTopLeft(find.text('No specimens yet')).dy,
      lessThan(tester.getTopLeft(find.byType(UiButton)).dy),
    );
  });

  testWidgets('the action is optional', (WidgetTester tester) async {
    await pumpComponent(
      tester,
      const EmptyState(
        icon: Symbols.inbox,
        title: 'Queue clear',
        body: 'Nothing needs review in this collection.',
      ),
    );
    expect(find.byType(UiButton), findsNothing);
    expect(find.text('Queue clear'), findsOneWidget);
  });

  testWidgets('the action fires', (WidgetTester tester) async {
    int taps = 0;
    await pumpComponent(
      tester,
      EmptyState(
        icon: Symbols.rule,
        title: 'No matches',
        body: 'No records match the current search and filters.',
        actionLabel: 'Clear filters',
        onAction: () => taps++,
      ),
    );
    await tester.tap(find.text('Clear filters'));
    await tester.pumpAndSettle();
    expect(taps, 1);
  });

  test('a label without a callback is refused', () {
    expect(
      () => EmptyState(
        icon: Symbols.inbox,
        title: 'No specimens yet',
        body: 'Upload a photograph to create the first record.',
        actionLabel: 'Add photographs',
      ),
      throwsAssertionError,
    );
  });

  testWidgets('renders in both themes and meets the guidelines', (
    WidgetTester tester,
  ) async {
    for (final ThemeData theme in productThemes.values) {
      await pumpComponent(
        tester,
        EmptyState(
          icon: Symbols.inbox,
          title: 'No specimens yet',
          body: 'Upload a photograph to create the first record.',
          actionLabel: 'Add photographs',
          onAction: () {},
        ),
        theme: theme,
      );
      await expectAccessible(tester);
    }
  });
}
