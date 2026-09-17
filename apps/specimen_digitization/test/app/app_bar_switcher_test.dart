// Finding V-9: the collection switcher's floating label sat 1.5 px above the
// window.
//
// A `Scaffold`'s `AppBar` stretched an action to the full 56 dp toolbar, and a
// 48 dp outlined field, which is the minimum target size, drew its floating
// label across its own top border. On a phone or a tablet the status-bar inset
// hid the overflow; in a browser, where the toolbar starts at y 0, it did not.
//
// `UiTopBar` and `UiSelect` remove the cause rather than working around it:
// the bar grows with its content instead of stretching it, and a select draws
// its label above its box or, as here, not at all. These tests hold what the
// finding was about: nothing in the bar draws above the window at any size
// class or text scale, the switcher stays inside the bar, and the control is
// still a full target that opens the list of collections.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/app/shell.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../golden/golden_harness.dart';

/// The two size classes that draw the switcher in the bar.
const Map<String, Size> switcherWindows = <String, Size>{
  'medium-768x1024': Size(768, 1024),
  'expanded-1180x820': Size(1180, 820),
};

/// The text scales a reviewer can be on.
const List<double> textScales = <double>[1.0, 1.3, 1.5, 2.0];

/// The switcher, wherever the window class put it.
final Finder switcher = find.byType(UiSelect<String>);

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  for (final MapEntry<String, Size> window in switcherWindows.entries) {
    for (final double scale in textScales) {
      testWidgets(
        'the switcher is inside the bar at ${window.key} at text $scale',
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
            reason: 'the bar has no collection switcher at ${window.key}',
          );

          final Rect box = tester.getRect(switcher);
          final Rect bar = tester.getRect(find.byType(UiTopBar));
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

  testWidgets('nothing in the top bar draws above the window', (
    WidgetTester tester,
  ) async {
    await pumpGoldenApp(
      tester,
      window: const Size(1180, 820),
      brightness: Brightness.light,
      textScale: 2.0,
      location: goldenQueueLocation,
    );
    final Rect bar = tester.getRect(find.byType(UiTopBar));
    for (final Element element
        in find
            .descendant(of: find.byType(UiTopBar), matching: find.byType(Text))
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
    expect(target.width, lessThanOrEqualTo(AppShell.switcherMaxWidth));

    await tester.tap(switcher);
    await tester.pumpAndSettle();
    expect(
      find.byType(UiListRow),
      findsWidgets,
      reason: 'the switcher opens the collections it may choose between',
    );
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('the bar carries no field with a label of its own', (
    WidgetTester tester,
  ) async {
    await pumpGoldenApp(
      tester,
      window: const Size(1180, 820),
      brightness: Brightness.light,
      location: goldenQueueLocation,
    );
    for (final UiSelect<String> select in tester.widgetList<UiSelect<String>>(
      switcher,
    )) {
      expect(
        select.showLabel,
        isFalse,
        reason:
            'a label drawn above a 48 dp control inside a 56 dp bar is '
            'finding V-9 again; the name is on the semantics node instead',
      );
      expect(select.semanticsLabel, isNotNull);
    }
    await tester.pumpWidget(const SizedBox());
  });
}
