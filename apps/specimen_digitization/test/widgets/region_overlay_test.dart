// The region overlay: a hittable box over an arbitrary photograph.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/widgets/region_overlay.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'harness.dart';

/// The overlay's hit target, by the role it publishes rather than by a
/// Material type: the box a reviewer presses is a `Pressable` now.
final Finder target = find.byWidgetPredicate(
  (Widget widget) => widget is Pressable && widget.semanticsLabel == 'Label 2',
  description: 'the overlay\'s hit target',
);

Widget _overlay({
  Rect rect = const Rect.fromLTWH(60, 60, 200, 120),
  bool selected = false,
  VoidCallback? onTap,
  int index = 2,
}) => SizedBox(
  width: 400,
  height: 300,
  child: RegionOverlay(
    index: index,
    rect: rect,
    selected: selected,
    onTap: onTap,
  ),
);

void main() {
  testWidgets('draws a box and a numbered tab', (WidgetTester tester) async {
    await pumpComponent(tester, _overlay(onTap: () {}));
    expect(find.byType(CustomPaint), findsWidgets);
    expect(find.text('2'), findsOneWidget);
  });

  testWidgets('the tab sits outside the box', (WidgetTester tester) async {
    await pumpComponent(tester, _overlay(onTap: () {}));
    final Rect overlay = tester.getRect(find.byType(RegionOverlay));
    final Rect tab = tester.getRect(find.text('2'));
    // The box top is 60 logical pixels down from the overlay origin.
    expect(tab.bottom, lessThanOrEqualTo(overlay.top + 60));
  });

  testWidgets('speaks the same name the region list shows', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await pumpComponent(tester, _overlay(onTap: () {}));
    expect(find.bySemanticsLabel('Label 2'), findsOneWidget);
    handle.dispose();
  });

  testWidgets('a tiny region still has a full sized hit box', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      _overlay(rect: const Rect.fromLTWH(150, 150, 6, 4), onTap: () {}),
    );
    final Size hit = tester.getSize(target);
    expect(hit.width, greaterThanOrEqualTo(44));
    expect(hit.height, greaterThanOrEqualTo(44));
  });

  testWidgets('a large region keeps its own hit box', (
    WidgetTester tester,
  ) async {
    await pumpComponent(tester, _overlay(onTap: () {}));
    final Size hit = tester.getSize(target);
    expect(hit.width, 200);
    expect(hit.height, 120);
  });

  testWidgets('tapping selects the region', (WidgetTester tester) async {
    int taps = 0;
    await pumpComponent(tester, _overlay(onTap: () => taps++));
    await tester.tap(target);
    await tester.pumpAndSettle();
    expect(taps, 1);
  });

  testWidgets('the selected state changes the painter and the tab', (
    WidgetTester tester,
  ) async {
    RegionBoxPainter painterOf() => tester
        .widgetList<CustomPaint>(find.byType(CustomPaint))
        .map((CustomPaint paint) => paint.painter)
        .whereType<RegionBoxPainter>()
        .single;

    await pumpComponent(tester, _overlay(onTap: () {}));
    final RegionBoxPainter plain = painterOf();

    await pumpComponent(tester, _overlay(onTap: () {}, selected: true));
    final RegionBoxPainter chosen = painterOf();

    expect(chosen.stroke, isNot(plain.stroke));
    expect(chosen.strokeWidth, greaterThan(plain.strokeWidth));
  });

  testWidgets('selection reaches the semantics tree', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await pumpComponent(tester, _overlay(onTap: () {}, selected: true));
    expect(
      tester.getSemantics(target),
      containsSemantics(label: 'Label 2', isSelected: true),
    );
    handle.dispose();
  });

  testWidgets('the hit target draws the system focus ring', (
    WidgetTester tester,
  ) async {
    await pumpComponent(tester, _overlay(onTap: () {}));
    // The ring is the package's, drawn on the superellipse the target names,
    // rather than a tinted fill this pattern used to pick for itself
    // (09 section 3.6).
    expect(tester.widget<Pressable>(target).focusRing, isTrue);
    expect(
      find.descendant(of: target, matching: find.byType(FocusRing)),
      findsOneWidget,
    );
  });

  testWidgets('the selected region is the screen\'s one accent', (
    WidgetTester tester,
  ) async {
    RegionBoxPainter painterOf() => tester
        .widgetList<CustomPaint>(find.byType(CustomPaint))
        .map((CustomPaint paint) => paint.painter)
        .whereType<RegionBoxPainter>()
        .single;

    for (final ThemeData theme in productThemes.values) {
      final UiThemeData ui = theme.brightness == Brightness.dark
          ? UiThemeData.dark()
          : UiThemeData.light();
      await pumpComponent(tester, _overlay(onTap: () {}), theme: theme);
      expect(painterOf().stroke, ui.color.status.regionOverlayStroke);

      await pumpComponent(
        tester,
        _overlay(onTap: () {}, selected: true),
        theme: theme,
      );
      // 09 section 3.4: the active region marker over the photograph is an
      // accent use, and the accent carries a 1 dp ink casing wherever it is
      // the only thing saying where a value is.
      expect(painterOf().stroke, ui.color.accent);
      expect(painterOf().casing, ui.color.ink);
    }
  });

  test('the painter repaints only when something it draws changes', () {
    const RegionBoxPainter first = RegionBoxPainter(
      rect: Rect.fromLTWH(0, 0, 10, 10),
      stroke: Color(0xFF000001),
      casing: Color(0xFF000002),
      strokeWidth: 2,
      casingWidth: 1,
    );
    const RegionBoxPainter same = RegionBoxPainter(
      rect: Rect.fromLTWH(0, 0, 10, 10),
      stroke: Color(0xFF000001),
      casing: Color(0xFF000002),
      strokeWidth: 2,
      casingWidth: 1,
    );
    const RegionBoxPainter wider = RegionBoxPainter(
      rect: Rect.fromLTWH(0, 0, 10, 10),
      stroke: Color(0xFF000001),
      casing: Color(0xFF000002),
      strokeWidth: 3,
      casingWidth: 1,
    );
    expect(first.shouldRepaint(same), isFalse);
    expect(first.shouldRepaint(wider), isTrue);
  });

  testWidgets('renders in both themes and meets the guidelines', (
    WidgetTester tester,
  ) async {
    for (final ThemeData theme in productThemes.values) {
      await pumpComponent(tester, _overlay(onTap: () {}), theme: theme);
      await expectAccessible(tester);
    }
  });
}
