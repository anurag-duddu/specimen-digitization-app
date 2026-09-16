// `UiListRow` is the reference control of the data family: one pressable, one
// merged semantics node, two modes, and a leading edge that has to hold still
// whatever the leading slot is doing.

import 'dart:ui' show CheckedState;

import 'package:flutter/semantics.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_ui/testing.dart';

import '../../harness/control_contract.dart';

/// A leading slot the row is asked to lay out at each of the three states the
/// invariant names: drawn, drawn but invisible, and disabled.
const Map<String, Widget> _leadingStates = <String, Widget>{
  'a 24 glyph': UiIcon(UiIcons.record, size: UiIconSize.action),
  'a 40 disc': UiAvatar(name: 'Ana Ruiz'),
  'hidden': Opacity(
    opacity: 0,
    child: UiIcon(UiIcons.record, size: UiIconSize.action),
  ),
  'disabled': UiButton(label: 'Select', size: UiSize.sm),
};

void main() {
  setUp(() {
    FocusManager.instance.highlightStrategy =
        FocusHighlightStrategy.alwaysTraditional;
  });
  tearDown(() {
    FocusManager.instance.highlightStrategy = FocusHighlightStrategy.automatic;
  });

  testWidgets('it satisfies the control contract', (WidgetTester tester) async {
    await expectControlContract(
      tester,
      (BuildContext context) => UiListRow(
        title: 'SPEC-2026-0041',
        subtitle: 'Two readings disagree on the collector',
        onPressed: () {},
      ),
      semanticsLabel:
          'SPEC-2026-0041, Two readings disagree on the collector',
    );
  });

  testWidgets('a row the server will not open states the reason', (
    WidgetTester tester,
  ) async {
    await expectControlContract(
      tester,
      (BuildContext context) => const UiListRow(
        title: 'SPEC-2026-0041',
        disabledReason: 'This record is open in another reviewer session.',
      ),
      semanticsLabel: 'SPEC-2026-0041',
      disabledWithReason: true,
    );
  });

  testWidgets('a row in a selection satisfies the contract as a checkbox', (
    WidgetTester tester,
  ) async {
    await expectControlContract(
      tester,
      (BuildContext context) => UiListRow(
        title: 'SPEC-2026-0041',
        mode: UiListRowMode.select,
        selected: true,
        onPressed: () {},
      ),
      semanticsLabel: 'SPEC-2026-0041',
    );
  });

  testWidgets('the mode decides what a screen reader calls the row', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(
        child: UiListRow(
          title: 'SPEC-2026-0041',
          onPressed: () {},
        ),
      ),
    );
    await tester.pumpAndSettle();
    SemanticsData data = tester
        .getSemantics(find.bySemanticsLabel('SPEC-2026-0041'))
        .getSemanticsData();
    expect(data.flagsCollection.isButton, isTrue);
    expect(data.flagsCollection.isChecked, CheckedState.none);

    for (final bool checked in <bool>[false, true]) {
      await tester.pumpWidget(
        uiHarness(
          child: UiListRow(
            title: 'SPEC-2026-0041',
            mode: UiListRowMode.select,
            selected: checked,
            onPressed: () {},
          ),
        ),
      );
      await tester.pumpAndSettle();
      data = tester
          .getSemantics(find.bySemanticsLabel('SPEC-2026-0041'))
          .getSemanticsData();
      expect(data.flagsCollection.isButton, isFalse);
      expect(
        data.flagsCollection.isChecked,
        checked ? CheckedState.isTrue : CheckedState.isFalse,
        reason: 'a row in a selection carries its own checked state',
      );
    }
    handle.dispose();
  });

  testWidgets('a tap opens the row and a long press starts a selection', (
    WidgetTester tester,
  ) async {
    int opened = 0;
    int held = 0;
    await tester.pumpWidget(
      uiHarness(
        child: UiListRow(
          title: 'SPEC-2026-0041',
          onPressed: () => opened++,
          onLongPress: () => held++,
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byType(UiListRow));
    await tester.pumpAndSettle();
    expect(opened, 1);
    expect(held, 0);

    await tester.longPress(find.byType(UiListRow));
    await tester.pumpAndSettle();
    expect(held, 1, reason: 'a long press is how a selection starts');
    expect(opened, 1, reason: 'a long press does not also open the record');
  });

  testWidgets('where the caller allows no selection, a slow press is still '
      'a press', (WidgetTester tester) async {
    int opened = 0;
    await tester.pumpWidget(
      uiHarness(
        child: UiListRow(title: 'SPEC-2026-0041', onPressed: () => opened++),
      ),
    );
    await tester.pumpAndSettle();
    await tester.longPress(find.byType(UiListRow));
    await tester.pumpAndSettle();
    expect(
      opened,
      1,
      reason:
          'holding a row in a list that has no selection opens the record, '
          'rather than swallowing the press and doing nothing',
    );
  });

  testWidgets('the title starts in the same place whatever the leading slot '
      'is doing', (WidgetTester tester) async {
    final Map<String, double> edges = <String, double>{};
    for (final MapEntry<String, Widget> state in _leadingStates.entries) {
      await tester.pumpWidget(
        uiHarness(
          child: UiListRow(
            title: 'SPEC-2026-0041',
            leading: state.value,
            onPressed: () {},
          ),
        ),
      );
      await tester.pumpAndSettle();
      edges[state.key] = tester.getTopLeft(find.text('SPEC-2026-0041')).dx;
    }
    expect(
      edges.values.toSet(),
      hasLength(1),
      reason:
          'the leading slot is a fixed box, so the content edge does not move '
          'between $edges',
    );
  });

  testWidgets('selecting a row does not shift its content sideways', (
    WidgetTester tester,
  ) async {
    final List<double> edges = <double>[];
    for (final bool selected in <bool>[false, true]) {
      await tester.pumpWidget(
        uiHarness(
          child: UiListRow(
            title: 'SPEC-2026-0041',
            selected: selected,
            onPressed: () {},
          ),
        ),
      );
      await tester.pumpAndSettle();
      edges.add(tester.getTopLeft(find.text('SPEC-2026-0041')).dx);
    }
    expect(
      edges.first,
      edges.last,
      reason: 'the bar gutter is reserved on every row, drawn or not',
    );
  });

  testWidgets('a selected row fills ink at 6 percent and draws the bar', (
    WidgetTester tester,
  ) async {
    for (final Brightness mode in Brightness.values) {
      final UiThemeData ui = mode == Brightness.dark
          ? UiThemeData.dark()
          : UiThemeData.light();
      final UiListRowStyle style = UiListRowStyle.resolve(ui, UiSize.md);
      expect(
        style.background.resolve(const <WidgetState>{WidgetState.selected}),
        ui.color.stateLayer(UiListRowStyle.selectedFillOpacity),
      );
      expect(
        style.background.resolve(const <WidgetState>{}).a,
        0,
        reason: 'an unselected row has no fill of its own',
      );
      expect(style.bar, ui.color.ink);
      expect(style.barWidth, ui.shape.stroke.bar);
    }

    await tester.pumpWidget(
      uiHarness(
        child: UiListRow(
          title: 'SPEC-2026-0041',
          selected: true,
          onPressed: () {},
        ),
      ),
    );
    await tester.pumpAndSettle();
    final UiThemeData ui = UiThemeData.light();
    final Iterable<ColoredBox> boxes = tester.widgetList<ColoredBox>(
      find.descendant(
        of: find.byType(UiListRow),
        matching: find.byType(ColoredBox),
      ),
    );
    expect(
      boxes.map((ColoredBox box) => box.color),
      contains(ui.color.ink),
      reason: 'the 3 dp leading bar is painted in ink',
    );
  });

  testWidgets('the row height is the density row, floored at the hit box', (
    WidgetTester tester,
  ) async {
    for (final UiDensityMode density in UiDensityMode.values) {
      await tester.pumpWidget(
        uiHarness(
          density: density,
          child: UiListRow(title: 'SPEC-2026-0041', onPressed: () {}),
        ),
      );
      await tester.pumpAndSettle();
      final UiDensity row = UiDensity.of(density);
      final double expected = row.rowHeight < UiDensity.hitBox
          ? UiDensity.hitBox
          : row.rowHeight;
      expect(
        tester.getSize(find.byType(UiListRow)).height,
        expected,
        reason: '${density.name} rows are $expected tall',
      );
    }
  });

  testWidgets('the size decides the title role', (WidgetTester tester) async {
    final UiThemeData ui = UiThemeData.light();
    expect(
      UiListRowStyle.resolve(ui, UiSize.md).title.fontSize,
      ui.type.title.fontSize,
    );
    expect(
      UiListRowStyle.resolve(ui, UiSize.sm).title.fontSize,
      ui.type.body.fontSize,
      reason: 'a menu row is set in body, a list row in title',
    );
    expect(
      UiListRowStyle.resolve(ui, UiSize.md).subtitle.fontSize,
      ui.type.bodySmall.fontSize,
    );
  });

  testWidgets('the row publishes one node, not one per slot', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(
        child: UiListRow(
          title: 'SPEC-2026-0041',
          subtitle: 'Two readings disagree on the collector',
          trailing: const UiChip(label: 'Needs human review'),
          semanticsLabel:
              'SPEC-2026-0041, needs human review, two readings disagree',
          onPressed: () {},
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      find.bySemanticsLabel('Needs human review'),
      findsNothing,
      reason: 'the trailing chip is inside the row node, not beside it',
    );
    expect(
      find.bySemanticsLabel(
        'SPEC-2026-0041, needs human review, two readings disagree',
      ),
      findsOneWidget,
    );
    handle.dispose();
  });

  testWidgets('the label falls back to the title and the subtitle', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(
        child: UiListRow(
          title: 'SPEC-2026-0041',
          subtitle: 'Waiting on label coverage',
          onPressed: () {},
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      find.bySemanticsLabel('SPEC-2026-0041, Waiting on label coverage'),
      findsOneWidget,
    );
    handle.dispose();
  });

  testWidgets('a long title is clipped rather than allowed to widen the row', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: SizedBox(
          width: 240,
          child: UiListRow(
            title: 'SPEC-2026-0041 collected by a very long collector name',
            onPressed: () {},
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(
      tester.renderObject<RenderBox>(find.byType(UiListRow)).size.width,
      lessThanOrEqualTo(240),
    );
  });

  testWidgets('a list of rows draws no glass at all', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            for (int i = 0; i < 8; i++)
              UiListRow(title: 'SPEC-2026-004$i', onPressed: () {}),
          ],
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      glassPaneCount(),
      0,
      reason:
          'a row is a repeated item, and 09 section 11 rejects glass on '
          'repeated items outright',
    );
  });
}
