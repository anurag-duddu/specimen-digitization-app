// The empty state on the product theme: title, one sentence, at most one
// action. The screens draw `UiEmptyState` from specimen_ui directly; this
// holds it to the product's two themes and its tap target guidelines.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'harness.dart';

void main() {
  testWidgets('renders the three parts in order', (WidgetTester tester) async {
    await pumpComponent(
      tester,
      UiEmptyState(
        icon: UiIcons.queue,
        title: 'No specimens yet',
        body: 'Upload a photograph to create the first record.',
        action: UiButton(label: 'Add photographs', onPressed: () {}),
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
      const UiEmptyState(
        icon: UiIcons.queue,
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
      UiEmptyState(
        icon: UiIcons.noResults,
        title: 'No matches',
        body: 'No records match the current search and filters.',
        action: UiButton(label: 'Clear filters', onPressed: () => taps++),
      ),
    );
    await tester.tap(find.text('Clear filters'));
    await tester.pumpAndSettle();
    expect(taps, 1);
  });

  testWidgets('a label without a callback is refused', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: productThemes['light'],
        home: const UiEmptyState(
          icon: UiIcons.queue,
          title: 'No specimens yet',
          body: 'Upload a photograph to create the first record.',
          action: UiButton(label: 'Add photographs'),
        ),
      ),
    );
    expect(tester.takeException(), isAssertionError);
  });

  testWidgets('renders in both themes and meets the guidelines', (
    WidgetTester tester,
  ) async {
    for (final ThemeData theme in productThemes.values) {
      await pumpComponent(
        tester,
        UiEmptyState(
          icon: UiIcons.queue,
          title: 'No specimens yet',
          body: 'Upload a photograph to create the first record.',
          action: UiButton(label: 'Add photographs', onPressed: () {}),
        ),
        theme: theme,
      );
      await expectAccessible(tester);
    }
  });
}
