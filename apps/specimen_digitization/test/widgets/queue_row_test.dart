// The queue row: keyed, hittable, and readable as one phrase.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/widgets/queue_row.dart';
import 'package:specimen_digitization/src/widgets/risk_meter.dart';
import 'package:specimen_digitization/src/widgets/specimen_status.dart';
import 'package:specimen_digitization/src/widgets/status_chip.dart';
import 'package:specimen_digitization/src/widgets/thumbnail.dart';

import 'harness.dart';

final DateTime _updated = DateTime(2026, 9, 13, 14, 32);
final DateTime _now = DateTime(2026, 9, 14, 9);

Widget _row({
  bool selected = false,
  VoidCallback? onOpen,
  num? risk = 62,
  List<String> components = const <String>['Reading disagreement'],
}) => SizedBox(
  width: 700,
  child: QueueRow(
    key: const ValueKey<String>('fixture-001'),
    id: 'fixture-001',
    title: 'FMNH-0001',
    reason: 'Two readings disagree on the locality',
    status: SpecimenStatus.needsReview,
    riskComposite: risk,
    riskComponents: components,
    updatedAt: _updated,
    now: _now,
    selected: selected,
    onOpen: onOpen,
  ),
);

void main() {
  group('relativeAge', () {
    test('is coarse and never negative', () {
      final DateTime now = DateTime(2026, 9, 14, 12);
      expect(relativeAge(now, now: now), 'just now');
      expect(
        relativeAge(now.add(const Duration(hours: 1)), now: now),
        'just now',
      );
      expect(
        relativeAge(now.subtract(const Duration(minutes: 5)), now: now),
        '5 min',
      );
      expect(
        relativeAge(now.subtract(const Duration(hours: 5)), now: now),
        '5 h',
      );
      expect(
        relativeAge(now.subtract(const Duration(days: 3)), now: now),
        '3 d',
      );
      expect(
        relativeAge(now.subtract(const Duration(days: 21)), now: now),
        '3 w',
      );
    });
  });

  test('the absolute form is the citable one', () {
    expect(
      absoluteTime(DateTime(2026, 9, 13, 14, 32)),
      startsWith('13 Sep 2026, 14:32 '),
    );
  });

  testWidgets('renders the title, reason, chip, meter and relative age', (
    WidgetTester tester,
  ) async {
    await pumpComponent(tester, _row(onOpen: () {}));
    expect(find.text('FMNH-0001'), findsOneWidget);
    expect(find.text('Two readings disagree on the locality'), findsOneWidget);
    expect(find.byType(StatusChip), findsOneWidget);
    expect(find.byType(RiskMeter), findsOneWidget);
    expect(find.text('18 h'), findsOneWidget);
  });

  testWidgets('a row with no thumbnail draws the placeholder', (
    WidgetTester tester,
  ) async {
    await pumpComponent(tester, _row(onOpen: () {}));
    expect(find.byType(SpecimenThumbnail), findsOneWidget);
    expect(find.byType(Image), findsNothing);
  });

  testWidgets('the row is at least 48 logical pixels tall', (
    WidgetTester tester,
  ) async {
    await pumpComponent(tester, _row(onOpen: () {}));
    expect(
      tester.getSize(find.byType(QueueRow)).height,
      greaterThanOrEqualTo(48),
    );
  });

  testWidgets('opening fires once', (WidgetTester tester) async {
    int opened = 0;
    await pumpComponent(tester, _row(onOpen: () => opened++));
    await tester.tap(find.byType(QueueRow));
    await tester.pumpAndSettle();
    expect(opened, 1);
  });

  testWidgets('the row is one node, with the absolute time in it', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await pumpComponent(tester, _row(onOpen: () {}));
    expect(
      find.bySemanticsLabel(
        RegExp(
          'FMNH-0001, Queue: needs human review, Two readings disagree on '
          'the locality, updated 13 Sep 2026, 14:32',
        ),
      ),
      findsOneWidget,
    );
    // Relative time is never the only form a reader gets.
    expect(find.bySemanticsLabel('18 h'), findsNothing);
    handle.dispose();
  });

  testWidgets('selection reaches the semantics tree', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await pumpComponent(tester, _row(onOpen: () {}, selected: true));
    expect(
      tester.getSemantics(find.byType(QueueRow)),
      containsSemantics(isSelected: true),
    );
    handle.dispose();
  });

  testWidgets('the row carries a hover and a focus treatment', (
    WidgetTester tester,
  ) async {
    await pumpComponent(tester, _row(onOpen: () {}));
    final InkWell ink = tester.widget<InkWell>(find.byType(InkWell));
    expect(ink.focusColor, isNotNull, reason: 'a visible focus state');
    expect(ink.onTap, isNotNull, reason: 'hover and pressed come with it');
  });

  testWidgets('a row with no risk score shows the abstention', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      _row(onOpen: () {}, risk: null, components: const <String>[]),
    );
    expect(find.text('Not measured'), findsOneWidget);
  });

  testWidgets('renders in both themes and meets the guidelines', (
    WidgetTester tester,
  ) async {
    for (final ThemeData theme in productThemes.values) {
      await pumpComponent(tester, _row(onOpen: () {}), theme: theme);
      await expectAccessible(tester);
    }
  });
}
