// Finding V-9: the collection switcher's floating label sat 1.5 px above the
// window.
//
// An `AppBar` stretches an action to the full 56 dp toolbar, and a 48 dp
// outlined field, which is the minimum target size, draws its floating label
// across its own top border. On a phone or a tablet the status-bar inset hid
// the overflow; in a browser, where the toolbar starts at y 0, it did not.
//
// The fix is a menu button, which has no floating label to clip. These tests
// hold both halves: nothing in the app bar draws above the window at any size
// class or text scale, and the control is still a 48 dp target that opens the
// list of collections.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/app/shell.dart';
import 'package:specimen_digitization/src/theme/tokens.dart';

import '../golden/golden_harness.dart';

/// The two size classes that draw the inline switcher.
const Map<String, Size> switcherWindows = <String, Size>{
  'medium-768x1024': Size(768, 1024),
  'expanded-1180x820': Size(1180, 820),
};

/// The text scales a reviewer can be on.
const List<double> textScales = <double>[1.0, 1.3, 1.5, 2.0];

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  for (final MapEntry<String, Size> window in switcherWindows.entries) {
    for (final double scale in textScales) {
      testWidgets(
        'the switcher is inside the toolbar at ${window.key} at text $scale',
        (WidgetTester tester) async {
          await pumpGoldenApp(
            tester,
            window: window.value,
            brightness: Brightness.light,
            textScale: scale,
            location: goldenQueueLocation,
          );

          final Finder switcher = find.bySemanticsLabel(
            RegExp('^Authorized collection'),
          );
          expect(
            switcher,
            findsOneWidget,
            reason: 'the app bar has no collection switcher at ${window.key}',
          );

          final Rect box = tester.getRect(switcher);
          expect(
            box.top,
            greaterThanOrEqualTo(0),
            reason:
                'the switcher drew above the top of the window, which is '
                'finding V-9',
          );
          expect(box.left, greaterThanOrEqualTo(0));
          expect(box.right, lessThanOrEqualTo(window.value.width));
          expect(
            box.bottom,
            lessThanOrEqualTo(SizeScale.appBar),
            reason: 'the switcher grew past the toolbar it sits in',
          );
        },
      );
    }
  }

  testWidgets('nothing in the app bar draws above the window', (
    WidgetTester tester,
  ) async {
    await pumpGoldenApp(
      tester,
      window: const Size(1180, 820),
      brightness: Brightness.light,
      textScale: 2.0,
      location: goldenQueueLocation,
    );
    final Rect bar = tester.getRect(find.byType(AppBar));
    for (final Element element
        in find
            .descendant(of: find.byType(AppBar), matching: find.byType(Text))
            .evaluate()) {
      final RenderBox box = element.renderObject! as RenderBox;
      final Offset top = box.localToGlobal(Offset.zero);
      expect(
        top.dy,
        greaterThanOrEqualTo(bar.top),
        reason: 'a label in the app bar starts above the toolbar',
      );
    }
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('the switcher keeps a full target and opens the list', (
    WidgetTester tester,
  ) async {
    await pumpGoldenApp(
      tester,
      window: const Size(1180, 820),
      brightness: Brightness.light,
      location: goldenQueueLocation,
    );
    final Finder switcher = find.bySemanticsLabel(
      RegExp('^Authorized collection'),
    );
    final Size target = tester.getSize(switcher);
    expect(target.height, greaterThanOrEqualTo(SizeScale.targetMin));
    expect(target.width, greaterThanOrEqualTo(SizeScale.targetMin));
    expect(target.width, lessThanOrEqualTo(AppShell.switcherMaxWidth));

    await tester.tap(switcher);
    await tester.pumpAndSettle();
    expect(find.byType(MenuItemButton), findsWidgets);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('the app bar carries no floating-label field at all', (
    WidgetTester tester,
  ) async {
    await pumpGoldenApp(
      tester,
      window: const Size(1180, 820),
      brightness: Brightness.light,
      location: goldenQueueLocation,
    );
    expect(
      find.descendant(
        of: find.byType(AppBar),
        matching: find.byType(DropdownButtonFormField<String>),
      ),
      findsNothing,
      reason: 'a floating label in a 56 dp toolbar is finding V-9 again',
    );
    await tester.pumpWidget(const SizedBox());
  });
}
