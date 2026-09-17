// `UiEmptyState` is not interactive; the button inside it is, and that button
// already carries the contract. What the empty state owes is the three parts
// in order, at most one of them a button, and no pane around nothing.

import 'package:flutter/semantics.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_ui/testing.dart';

import '../../harness/control_contract.dart';

/// The filtered queue state, which is the one with something to do
/// (02 section 4.6).
Widget _filtered({VoidCallback? onClear}) => UiEmptyState(
  icon: UiIcons.noResults,
  title: 'No matches',
  body: 'No records match the current search and filters.',
  action: onClear == null
      ? null
      : UiButton(label: 'Clear filters', onPressed: onClear),
);

void main() {
  testWidgets('the three parts are drawn in order', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(child: _filtered(onClear: () {})));
    await tester.pumpAndSettle();
    final double glyph = tester.getTopLeft(find.byType(UiIcon)).dy;
    final double title = tester.getTopLeft(find.text('No matches')).dy;
    final double body = tester
        .getTopLeft(
          find.text('No records match the current search and filters.'),
        )
        .dy;
    final double button = tester.getTopLeft(find.byType(UiButton)).dy;
    expect(glyph, lessThan(title), reason: 'the glyph is above the title');
    expect(title, lessThan(body), reason: 'the title names the absence first');
    expect(body, lessThan(button), reason: 'the way out is last');
  });

  testWidgets('the glyph is 40 and adds nothing to the semantics tree', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(child: _filtered()));
    await tester.pumpAndSettle();
    expect(tester.widget<UiIcon>(find.byType(UiIcon)).size, UiIconSize.display);
    expect(tester.widget<UiIcon>(find.byType(UiIcon)).spec, UiIcons.noResults);
    expect(
      UiIcons.noResults.weight,
      UiIconWeight.light,
      reason: '09 section 7 draws a decorative glyph at 40 in light',
    );
  });

  testWidgets('a state with nothing to do has no button', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: const UiEmptyState(
          icon: UiIcons.queue,
          title: 'Queue clear',
          body: 'Nothing needs review in this collection.',
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byType(UiButton), findsNothing);
    expect(find.text('Queue clear'), findsOneWidget);
  });

  testWidgets('the one action runs', (WidgetTester tester) async {
    int cleared = 0;
    await tester.pumpWidget(
      uiHarness(child: _filtered(onClear: () => cleared++)),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byType(UiButton));
    await tester.pumpAndSettle();
    expect(cleared, 1);
  });

  testWidgets('it sits on the sky with no glass of its own', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(child: _filtered(onClear: () {})));
    await tester.pumpAndSettle();
    expect(
      glassPaneCount(),
      0,
      reason: 'a pane around nothing is a pane around nothing',
    );
  });

  testWidgets('the words carry the state and the glyph adds nothing', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await tester.pumpWidget(uiHarness(child: _filtered()));
    await tester.pumpAndSettle();
    final List<String> spoken = find.semantics
        .byPredicate((SemanticsNode node) => node.label.isNotEmpty)
        .evaluate()
        .map((SemanticsNode node) => node.label)
        .toList(growable: false);
    expect(
      spoken,
      hasLength(1),
      reason:
          'the absence is one thing, so it is one node: the glyph repeats '
          'the title and is kept out of the tree',
    );
    expect(
      spoken.single,
      'No matches\nNo records match the current search and filters.',
      reason: 'the title is read before the sentence that explains it',
    );
    handle.dispose();
  });

  testWidgets('it builds right to left and at 200 percent text', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        textDirection: TextDirection.rtl,
        textScaler: const TextScaler.linear(2),
        child: _filtered(onClear: () {}),
      ),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });

  testWidgets('nothing about it animates, in either motion mode', (
    WidgetTester tester,
  ) async {
    for (final bool reduced in <bool>[false, true]) {
      await tester.pumpWidget(
        uiHarness(
          disableAnimations: reduced,
          child: _filtered(onClear: () {}),
        ),
      );
      await tester.pump();
      expect(tester.binding.transientCallbackCount, 0);
    }
  });
}
