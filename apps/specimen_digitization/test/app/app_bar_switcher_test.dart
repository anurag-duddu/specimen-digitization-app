// The collection chooser must stay within its sidebar or mobile header at
// every text scale. Its accessible name replaces the former floating label,
// and its hit target must still open the available collections.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/app/shell.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../golden/golden_harness.dart';

/// Desktop and tablet widths; enlarged text can select the mobile layout.
const Map<String, Size> switcherWindows = <String, Size>{
  'medium-768x1024': Size(768, 1024),
  'expanded-1180x820': Size(1180, 820),
};

/// The text scales a reviewer can be on.
const List<double> textScales = <double>[1.0, 1.3, 1.5, 2.0];

/// The switcher, wherever the window class put it.
final Finder switcher = find.bySemanticsLabel(
  RegExp('^Authorized collection,'),
);
final Finder collectionHeader = find.byKey(
  const ValueKey('global-sidebar-collection'),
);

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  for (final MapEntry<String, Size> window in switcherWindows.entries) {
    for (final double scale in textScales) {
      testWidgets(
        'the switcher is inside its collection header at ${window.key} at text $scale',
        (WidgetTester tester) async {
          await pumpGoldenApp(
            tester,
            window: window.value,
            brightness: Brightness.light,
            textScale: scale,
            location: goldenQueueLocation,
          );

          expect(
            switcher,
            findsOneWidget,
            reason: 'the header has no collection switcher at ${window.key}',
          );

          final Rect box = tester.getRect(switcher);
          final Rect bar = tester.getRect(collectionHeader);
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
            box.top,
            greaterThanOrEqualTo(bar.top),
            reason: 'the switcher started above the bar it sits in',
          );
          expect(
            box.bottom,
            lessThanOrEqualTo(bar.bottom + 0.5),
            reason: 'the switcher grew past the bar it sits in',
          );
        },
      );
    }
  }

  testWidgets('nothing in the collection header draws above the window', (
    WidgetTester tester,
  ) async {
    await pumpGoldenApp(
      tester,
      window: const Size(1180, 820),
      brightness: Brightness.light,
      textScale: 2.0,
      location: goldenQueueLocation,
    );
    final Rect bar = tester.getRect(collectionHeader);
    for (final Element element
        in find
            .descendant(of: collectionHeader, matching: find.byType(Text))
            .evaluate()) {
      final RenderBox box = element.renderObject! as RenderBox;
      final Offset top = box.localToGlobal(Offset.zero);
      expect(
        top.dy,
        greaterThanOrEqualTo(bar.top),
        reason: 'a label in the top bar starts above the bar',
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
    final Size target = tester.getSize(switcher);
    expect(target.height, greaterThanOrEqualTo(UiDensity.hitBox));
    expect(target.width, greaterThanOrEqualTo(UiDensity.hitBox));
    expect(
      target.width,
      lessThanOrEqualTo(tester.getSize(collectionHeader).width),
    );

    await tester.tap(switcher);
    await tester.pumpAndSettle();
    expect(
      find.byType(UiPopoverMenu),
      findsWidgets,
      reason: 'the switcher opens the collections it may choose between',
    );
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets(
    'the switcher has one accessible name and no floating field label',
    (tester) async {
      await pumpGoldenApp(
        tester,
        window: const Size(1180, 820),
        brightness: Brightness.light,
        location: goldenQueueLocation,
      );
      expect(switcher, findsOneWidget);
      expect(
        find.descendant(
          of: collectionHeader,
          matching: find.byType(UiSelect<String>),
        ),
        findsNothing,
      );
      expect(
        tester.getSemantics(switcher).label,
        startsWith(AppShell.switcherLabel),
      );
      await tester.pumpWidget(const SizedBox());
    },
  );
}
