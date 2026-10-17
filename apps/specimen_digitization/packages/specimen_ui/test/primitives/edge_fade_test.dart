// `EdgeFadedRow` (11 section 3.3): a row too wide for its column, scrolled
// with fading edges.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../harness/control_contract.dart';

/// A row of [count] 48 dp items inside a [width] dp column.
Widget _row({
  required int count,
  required int index,
  required double width,
  bool reveal = false,
}) => Align(
  alignment: Alignment.topLeft,
  child: SizedBox(
    width: width,
    height: 48,
    child: EdgeFadedRow(
      index: index,
      length: count,
      fadeExtent: 24,
      revealInitially: reveal,
      extent: reveal ? 48.0 * count : null,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          for (int i = 0; i < count; i++)
            SizedBox.square(dimension: 48, key: ValueKey<int>(i)),
        ],
      ),
    ),
  ),
);

double _pixels(WidgetTester tester) =>
    tester.state<ScrollableState>(find.byType(Scrollable)).position.pixels;

void main() {
  testWidgets(
    'by default the row starts at its beginning, whatever the index',
    (WidgetTester tester) async {
      await tester.pumpWidget(
        uiHarness(child: _row(count: 5, index: 4, width: 120)),
      );
      expect(
        _pixels(tester),
        0,
        reason: 'a strip or a pill opens on its first',
      );
      await tester.pumpAndSettle();
      expect(
        _pixels(tester),
        0,
        reason: 'and stays there until the index moves',
      );
    },
  );

  testWidgets('revealInitially starts the row on its item before the first '
      'frame is painted', (WidgetTester tester) async {
    for (int index = 0; index < 5; index++) {
      await tester.pumpWidget(const SizedBox());
      // A row moved after it was painted sends scroll notifications, which is
      // what a post frame `jumpTo` does; one that was built on its item sends
      // none, and sat there for the first paint.
      final List<Type> scrolls = <Type>[];
      await tester.pumpWidget(
        uiHarness(
          child: NotificationListener<ScrollNotification>(
            onNotification: (ScrollNotification n) {
              scrolls.add(n.runtimeType);
              return false;
            },
            child: _row(count: 5, index: index, width: 120, reveal: true),
          ),
        ),
      );
      expect(scrolls, isEmpty, reason: 'index $index was moved: $scrolls');
      // The reach is 240 - 120, and item `index` of 5 sits that fraction of
      // the way along it.
      expect(
        _pixels(tester),
        closeTo(120 * index / 4, 0.001),
        reason: '$index',
      );
      final Rect item = tester.getRect(find.byKey(ValueKey<int>(index)));
      expect(item.left, greaterThanOrEqualTo(-0.5));
      expect(item.right, lessThanOrEqualTo(120.5));
    }
  });

  testWidgets('revealInitially in a row that fits does not scroll', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(child: _row(count: 3, index: 2, width: 300, reveal: true)),
    );
    expect(_pixels(tester), 0);
  });

  testWidgets('a change of index still animates to the new item', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(child: _row(count: 5, index: 0, width: 120, reveal: true)),
    );
    await tester.pumpWidget(
      uiHarness(child: _row(count: 5, index: 4, width: 120, reveal: true)),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(_pixels(tester), greaterThan(0));
    expect(_pixels(tester), lessThan(120), reason: 'it is travelling');
    await tester.pumpAndSettle();
    expect(_pixels(tester), closeTo(120, 0.001));
  });

  testWidgets('a change of width puts the row back on its item', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(child: _row(count: 5, index: 4, width: 120, reveal: true)),
    );
    expect(_pixels(tester), closeTo(120, 0.001));
    await tester.pumpWidget(
      uiHarness(child: _row(count: 5, index: 4, width: 200, reveal: true)),
    );
    await tester.pumpAndSettle();
    expect(
      _pixels(tester),
      closeTo(40, 0.001),
      reason: 'reach is now 240 - 200',
    );
    final Rect item = tester.getRect(find.byKey(const ValueKey<int>(4)));
    expect(item.right, lessThanOrEqualTo(200.5));
  });

  testWidgets('revealInitially without an extent is a mistake that says so', (
    WidgetTester tester,
  ) async {
    expect(
      () => EdgeFadedRow(
        index: 0,
        length: 3,
        fadeExtent: 24,
        revealInitially: true,
        child: const SizedBox(),
      ),
      throwsAssertionError,
    );
  });

  testWidgets('it mirrors under right to left', (WidgetTester tester) async {
    await tester.pumpWidget(
      uiHarness(
        textDirection: TextDirection.rtl,
        child: _row(count: 5, index: 4, width: 120, reveal: true),
      ),
    );
    final Rect item = tester.getRect(find.byKey(const ValueKey<int>(4)));
    expect(item.left, greaterThanOrEqualTo(-0.5));
    expect(item.right, lessThanOrEqualTo(120.5));
  });
}
