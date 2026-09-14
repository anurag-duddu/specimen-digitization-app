// The caveat: the label alone is sufficient, and "Why" says more.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/widgets/caveat_text.dart';

import 'harness.dart';

const CaveatText _caveat = CaveatText(
  label: 'Not calibrated',
  body:
      'A risk score orders the queue. It is not a probability that the record '
      'is wrong. Scores never override coverage, evidence or validation '
      'gates.',
);

void main() {
  testWidgets('shows the label and the Why affordance, closed', (
    WidgetTester tester,
  ) async {
    await pumpComponent(tester, _caveat);
    expect(find.text('Not calibrated'), findsOneWidget);
    expect(find.text('Why'), findsOneWidget);
    expect(find.textContaining('orders the queue'), findsNothing);
  });

  testWidgets('Why opens the body and closes it again', (
    WidgetTester tester,
  ) async {
    await pumpComponent(tester, _caveat);
    await tester.tap(find.text('Why'));
    await tester.pumpAndSettle();
    expect(find.textContaining('orders the queue'), findsOneWidget);

    await tester.tap(find.text('Why'));
    await tester.pumpAndSettle();
    expect(find.textContaining('orders the queue'), findsNothing);
  });

  testWidgets('the disclosure reports its expanded state', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await pumpComponent(tester, _caveat);
    expect(
      tester.getSemantics(find.bySubtype<TextButton>()),
      containsSemantics(label: 'Why', isButton: true, isExpanded: false),
    );

    await tester.tap(find.text('Why'));
    await tester.pumpAndSettle();
    expect(
      tester.getSemantics(find.bySubtype<TextButton>()),
      containsSemantics(label: 'Why', isButton: true, isExpanded: true),
    );
    handle.dispose();
  });

  testWidgets('under reduced motion the body arrives without an animation', (
    WidgetTester tester,
  ) async {
    await pumpComponent(tester, _caveat, reduceMotion: true);
    await tester.tap(find.text('Why'));
    // One frame, no settle: with motion off the size change is a jump.
    await tester.pump();
    expect(find.textContaining('orders the queue'), findsOneWidget);
  });

  testWidgets('renders in both themes', (WidgetTester tester) async {
    for (final ThemeData theme in productThemes.values) {
      await pumpComponent(tester, _caveat, theme: theme);
      expect(find.text('Not calibrated'), findsOneWidget);
    }
  });

  testWidgets('meets the tap target and label guidelines', (
    WidgetTester tester,
  ) async {
    await pumpComponent(tester, _caveat);
    await expectAccessible(tester);
  });
}
