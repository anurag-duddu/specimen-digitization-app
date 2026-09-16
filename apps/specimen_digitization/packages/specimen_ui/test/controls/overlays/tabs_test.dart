// `UiTabs` and `UiTabView` (10 section 4.3).

import 'dart:ui' show Tristate;

import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_ui/testing.dart';

import '../../harness/control_contract.dart';

const List<UiTab> _tabs = <UiTab>[
  UiTab(label: 'Readings'),
  UiTab(label: 'Fields'),
  UiTab(label: 'History'),
];

const List<String> _panes = <String>[
  'Two model readings',
  'Field layers',
  'Every decision on this record',
];

class _TabsHost extends StatefulWidget {
  const _TabsHost({this.strip});

  final Widget? strip;

  @override
  State<_TabsHost> createState() => _TabsHostState();
}

class _TabsHostState extends State<_TabsHost> {
  final ValueNotifier<int> selected = ValueNotifier<int>(0);

  @override
  void dispose() {
    selected.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Column(
    mainAxisSize: MainAxisSize.min,
    children: <Widget>[
      UiTabs(
        tabs: _tabs,
        selected: selected,
        semanticsLabel: 'Record panels',
        strip: widget.strip,
      ),
      UiTabView(
        selected: selected,
        children: <Widget>[for (final String pane in _panes) Text(pane)],
      ),
    ],
  );
}

void main() {
  testWidgets('pressing a tab changes the pane', (WidgetTester tester) async {
    await tester.pumpWidget(uiHarness(child: const _TabsHost()));
    await tester.pumpAndSettle();
    expect(find.text(_panes[0]), findsOneWidget);

    await tester.tap(find.text('History'));
    await tester.pumpAndSettle();
    expect(find.text(_panes[2]), findsOneWidget);
    expect(find.text(_panes[0]), findsNothing);
  });

  testWidgets('the strip is a UiSegmented at lg, not a strip of its own', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(child: const _TabsHost()));
    await tester.pumpAndSettle();
    final UiSegmented<int> strip = tester.widget<UiSegmented<int>>(
      find.byType(UiSegmented<int>),
    );
    expect(strip.size, UiSize.lg);
    expect(strip.value, 0);
    expect(
      strip.segments.map((UiSegment<int> segment) => segment.label),
      <String>['Readings', 'Fields', 'History'],
    );
  });

  testWidgets('arrows move along the strip and Enter chooses', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(child: const _TabsHost()));
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pumpAndSettle();
    expect(FocusManager.instance.primaryFocus?.debugLabel, 'Readings');

    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.pumpAndSettle();
    expect(
      find.text(_panes[0]),
      findsOneWidget,
      reason:
          'manual activation: arrowing past a tab does not swap the pane '
          'under the reviewer on the way through (10 section 4.1)',
    );

    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(find.text(_panes[1]), findsOneWidget);

    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(find.text(_panes[2]), findsOneWidget);

    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(
      find.text(_panes[2]),
      findsOneWidget,
      reason:
          'the track clamps at its ends: a reviewer holding an arrow down '
          'lands on the last tab rather than back on the first',
    );
  });

  testWidgets('the arrows mirror under a right to left window', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(textDirection: TextDirection.rtl, child: const _TabsHost()),
    );
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pumpAndSettle();

    await tester.sendKeyEvent(LogicalKeyboardKey.arrowLeft);
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(
      find.text(_panes[1]),
      findsOneWidget,
      reason:
          'forward is to the left in a right to left window '
          '(04 section 5.3)',
    );
  });

  testWidgets('the strip is a tab bar of tabs, one of them selected', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await tester.pumpWidget(uiHarness(child: const _TabsHost()));
    await tester.pumpAndSettle();

    final SemanticsData first = tester
        .getSemantics(find.bySemanticsLabel('Readings'))
        .getSemanticsData();
    expect(first.role, SemanticsRole.tab);
    expect(first.flagsCollection.isSelected, Tristate.isTrue);

    final SemanticsData other = tester
        .getSemantics(find.bySemanticsLabel('History'))
        .getSemanticsData();
    expect(other.flagsCollection.isSelected, Tristate.isFalse);
    handle.dispose();
  });

  testWidgets('a caller can pass its own strip', (WidgetTester tester) async {
    await tester.pumpWidget(
      uiHarness(
        child: const _TabsHost(strip: Text('Somebody else strip')),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Somebody else strip'), findsOneWidget);
    expect(find.text('Readings'), findsNothing);
  });

  testWidgets('panes cross fade and never slide', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(child: const _TabsHost()));
    await tester.pumpAndSettle();
    expect(
      find.descendant(
        of: find.byType(UiTabView),
        matching: find.byType(SlideTransition),
      ),
      findsNothing,
      reason: 'a shared axis is declined per 04 section 3.3',
    );

    await tester.tap(find.text('Fields'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 120));
    expect(
      find.descendant(
        of: find.byType(UiTabView),
        matching: find.byType(FadeTransition),
      ),
      findsWidgets,
    );
    await tester.pumpAndSettle();
  });

  testWidgets('the swap is instant under reduced motion', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(disableAnimations: true, child: const _TabsHost()),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Fields'));
    await tester.pump();
    expect(find.text(_panes[1]), findsOneWidget);
    expect(tester.binding.transientCallbackCount, 0);
  });

  testWidgets('the strip is never glass', (WidgetTester tester) async {
    await tester.pumpWidget(
      uiHarness(
        textScaler: const TextScaler.linear(2),
        child: const _TabsHost(),
      ),
    );
    await tester.pumpAndSettle();
    expect(glassPaneCount(), 0);
    expectGlassBudget(tester);
  });

  testWidgets('a tab satisfies the control contract', (
    WidgetTester tester,
  ) async {
    await expectControlContract(
      tester,
      (BuildContext context) => const _TabsHost(),
      semanticsLabel: 'Readings',
      hasRole: (SemanticsFlags flags) => flags.isSelected != Tristate.none,
    );
  });
}
