// Placeholders: no shimmer, no semantics, one live "Loading" node.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/widgets/skeleton.dart';

import 'harness.dart';

void main() {
  testWidgets('a skeleton row draws three bars at 60, 40 and 80 percent', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      const SizedBox(width: 200, child: SkeletonRow()),
    );
    final Iterable<SkeletonBar> bars = tester.widgetList<SkeletonBar>(
      find.byType(SkeletonBar),
    );
    expect(
      bars.map((SkeletonBar bar) => bar.widthFactor),
      SkeletonRow.widthFactors,
    );
  });

  testWidgets('placeholders are not in the semantics tree', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await pumpComponent(
      tester,
      const Column(children: <Widget>[SkeletonRow(), SkeletonBlock()]),
    );
    expect(
      find.bySemanticsLabel(RegExp('.+')),
      findsNothing,
      reason: 'a screen of placeholders exposes no nodes of its own',
    );
    handle.dispose();
  });

  testWidgets('no placeholder starts a repeating animation', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      const Column(children: <Widget>[SkeletonRow(), SkeletonBlock()]),
    );
    // A pending frame after settling means something is still animating, and
    // a shimmer would never settle at all.
    expect(tester.binding.hasScheduledFrame, isFalse);
  });

  testWidgets('the loading announcement is a live region, spoken once', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await pumpComponent(
      tester,
      const Column(
        children: <Widget>[
          SkeletonRow(),
          SkeletonRow(),
          LoadingAnnouncement(thing: 'queue'),
        ],
      ),
    );
    expect(find.bySemanticsLabel('Loading queue'), findsOneWidget);
    handle.dispose();
  });

  testWidgets('the visible form uses the ellipsis character', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      const LoadingAnnouncement(thing: 'evidence', visible: true),
    );
    expect(find.text('Loading evidence…'), findsOneWidget);
    expect(find.text('Loading evidence...'), findsNothing);
  });

  testWidgets('renders in both themes and meets the guidelines', (
    WidgetTester tester,
  ) async {
    for (final ThemeData theme in productThemes.values) {
      await pumpComponent(
        tester,
        const SizedBox(width: 300, child: SkeletonRow()),
        theme: theme,
      );
      await expectAccessible(tester);
    }
  });
}
