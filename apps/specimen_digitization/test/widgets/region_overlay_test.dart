// The region overlay: a hittable box over an arbitrary photograph.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/widgets/region_overlay.dart';

import 'harness.dart';

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
    final Size hit = tester.getSize(find.byType(InkWell));
    expect(hit.width, greaterThanOrEqualTo(44));
    expect(hit.height, greaterThanOrEqualTo(44));
  });

  testWidgets('a large region keeps its own hit box', (
    WidgetTester tester,
  ) async {
    await pumpComponent(tester, _overlay(onTap: () {}));
    final Size hit = tester.getSize(find.byType(InkWell));
    expect(hit.width, 200);
    expect(hit.height, 120);
  });

  testWidgets('tapping selects the region', (WidgetTester tester) async {
    int taps = 0;
    await pumpComponent(tester, _overlay(onTap: () => taps++));
    await tester.tap(find.byType(InkWell));
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
      tester.getSemantics(find.byType(InkWell)),
      containsSemantics(label: 'Label 2', isSelected: true),
    );
    handle.dispose();
  });

  testWidgets('the overlay carries a focus ring from the reserved token', (
    WidgetTester tester,
  ) async {
    await pumpComponent(tester, _overlay(onTap: () {}));
    expect(tester.widget<InkWell>(find.byType(InkWell)).focusColor, isNotNull);
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
