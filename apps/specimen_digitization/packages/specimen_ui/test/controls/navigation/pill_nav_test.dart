// The pill navigation (10 section 4.4, `UiPillNav`).

import 'dart:ui' show Tristate;

import 'package:flutter/gestures.dart' show PointerDeviceKind;
import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';
import 'destinations.dart';

/// A pill whose selection is real, so a tap and a key press can be observed
/// changing the control rather than only calling back.
class _PillHost extends StatefulWidget {
  const _PillHost({required this.destinations, this.onSelect});

  final List<UiNavDestination> destinations;
  final ValueChanged<int>? onSelect;

  @override
  State<_PillHost> createState() => _PillHostState();
}

class _PillHostState extends State<_PillHost> {
  int _current = 0;

  @override
  Widget build(BuildContext context) => UiPillNav(
    destinations: widget.destinations,
    currentIndex: _current,
    onSelect: (int index) {
      widget.onSelect?.call(index);
      setState(() => _current = index);
    },
  );
}

/// Where the gliding `ink` disc is right now.
double _discStart(WidgetTester tester) => tester
    .getTopLeft(
      find.descendant(
        of: find.byType(UiPillNav),
        matching: find.byType(AnimatedPositionedDirectional),
      ),
    )
    .dx;

void main() {
  testWidgets('a pointer selects the destination it lands on', (
    WidgetTester tester,
  ) async {
    final List<int> selected = <int>[];
    await tester.pumpWidget(
      uiHarness(
        child: _PillHost(
          destinations: threeDestinations,
          onSelect: selected.add,
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.bySemanticsLabel('Sources'));
    await tester.pumpAndSettle();
    expect(selected, <int>[2]);

    await tester.tap(find.bySemanticsLabel('Intake'));
    await tester.pumpAndSettle();
    expect(selected, <int>[2, 1]);
  });

  testWidgets('arrows move and Enter selects', (WidgetTester tester) async {
    final List<int> selected = <int>[];
    await tester.pumpWidget(
      uiHarness(
        child: _PillHost(
          destinations: threeDestinations,
          onSelect: selected.add,
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.pumpAndSettle();
    // Arrows move focus only. Nothing is selected until a key says so.
    expect(selected, isEmpty);

    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(selected, <int>[2]);
  });

  testWidgets('focus wraps at both ends', (WidgetTester tester) async {
    final List<int> selected = <int>[];
    await tester.pumpWidget(
      uiHarness(
        child: _PillHost(
          destinations: threeDestinations,
          onSelect: selected.add,
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowLeft);
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(selected, <int>[2], reason: 'left from the first wraps to the last');
  });

  testWidgets('the arrow keys mirror under RTL', (WidgetTester tester) async {
    final List<int> selected = <int>[];
    await tester.pumpWidget(
      uiHarness(
        textDirection: TextDirection.rtl,
        child: _PillHost(
          destinations: threeDestinations,
          onSelect: selected.add,
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowLeft);
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(
      selected,
      <int>[1],
      reason: 'left is forward under RTL, so it lands on the second',
    );
  });

  testWidgets('the disc glides to the destination it was sent to', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(child: const _PillHost(destinations: threeDestinations)),
    );
    await tester.pumpAndSettle();
    final double start = _discStart(tester);

    await tester.tap(find.bySemanticsLabel('Sources'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 120));
    final double midway = _discStart(tester);

    await tester.pumpAndSettle();
    final double end = _discStart(tester);

    expect(end, greaterThan(start));
    expect(midway, greaterThan(start));
    expect(
      midway,
      lessThan(end),
      reason: 'the disc jumped instead of gliding (09 section 8)',
    );
  });

  testWidgets('under reduced motion the disc appears in place', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        disableAnimations: true,
        child: const _PillHost(destinations: threeDestinations),
      ),
    );
    await tester.pumpAndSettle();
    final double start = _discStart(tester);

    await tester.tap(find.bySemanticsLabel('Sources'));
    await tester.pump();
    expect(
      _discStart(tester),
      greaterThan(start),
      reason: 'the disc is already at the new destination on the next frame',
    );
    expect(tester.binding.transientCallbackCount, 0);
  });

  testWidgets('every disc is a tab, one is selected, each carries its label', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(child: const _PillHost(destinations: threeDestinations)),
    );
    await tester.pumpAndSettle();

    for (final MapEntry<int, UiNavDestination> entry
        in threeDestinations.asMap().entries) {
      final SemanticsNode node = tester.getSemantics(
        find.bySemanticsLabel(entry.value.label),
      );
      final SemanticsData data = node.getSemanticsData();
      expect(data.label, entry.value.label);
      expect(
        data.role,
        SemanticsRole.tab,
        reason: '${entry.value.label} is not a tab',
      );
      expect(
        data.flagsCollection.isSelected,
        entry.key == 0 ? Tristate.isTrue : Tristate.isFalse,
      );
      expect(
        data.tooltip,
        entry.value.label,
        reason:
            'a disc draws no words, so the label has to reach a pointer '
            'reviewer as a tooltip (10 section 4.4)',
      );
    }
    handle.dispose();
  });

  testWidgets('a disc draws its label after the hover delay', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(child: const _PillHost(destinations: threeDestinations)),
    );
    await tester.pumpAndSettle();
    expect(find.text('Intake'), findsNothing, reason: 'no words are drawn');

    final TestGesture pointer = await tester.createGesture(
      kind: PointerDeviceKind.mouse,
    );
    await pointer.addPointer(location: Offset.zero);
    addTearDown(pointer.removePointer);
    await tester.pump();
    await pointer.moveTo(tester.getCenter(find.bySemanticsLabel('Intake')));
    await tester.pump();
    await tester.pump(UiTooltipStyle.hoverDelay);
    await tester.pumpAndSettle();
    expect(
      find.text('Intake'),
      findsOneWidget,
      reason:
          'the undrawn label reaches a pointer reviewer as a drawn UiTooltip, '
          'not only as a semantics property (10 section 4.4)',
    );

    await pointer.moveTo(const Offset(5, 5));
    await tester.pumpAndSettle();
    expect(find.text('Intake'), findsNothing);
  });

  testWidgets('the extended rail draws its words and no tooltip', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: SizedBox(
          height: 600,
          child: UiRail(
            destinations: threeDestinations,
            currentIndex: 0,
            onSelect: (int _) {},
            extended: true,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Intake'), findsOneWidget, reason: 'the words are drawn');
    expect(
      find.byType(UiTooltip),
      findsNothing,
      reason: 'a label a reviewer can already read needs no tooltip',
    );
  });

  testWidgets('the pill publishes a tab list around the discs', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(child: const _PillHost(destinations: twoDestinations)),
    );
    await tester.pumpAndSettle();
    expect(
      find.byWidgetPredicate(
        (Widget widget) =>
            widget is Semantics &&
            widget.properties.role == SemanticsRole.tabBar,
      ),
      findsOneWidget,
    );
    handle.dispose();
  });

  testWidgets('the current disc lifts toward paper so a press shows on it', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(child: const _PillHost(destinations: threeDestinations)),
    );
    await tester.pumpAndSettle();
    final UiThemeData ui = tester.element(find.byType(UiPillNav)).ui;

    Color? layerOf(String label) => tester
        .widget<StateLayer>(
          find
              .descendant(
                of: find.bySemanticsLabel(label),
                matching: find.byType(StateLayer),
              )
              .first,
        )
        .colour;

    expect(
      layerOf('Queue'),
      ui.color.paper,
      reason:
          'ink at 12 percent over an ink disc is the same colour, so the '
          'current disc would show no press at all',
    );
    expect(
      layerOf('Intake'),
      isNull,
      reason: 'a disc on the sky takes the contract default',
    );
  });

  testWidgets('the height it reports is the height it draws', (
    WidgetTester tester,
  ) async {
    late double reported;
    late double inset;
    await tester.pumpWidget(
      uiHarness(
        child: Builder(
          builder: (BuildContext context) {
            reported = UiPillNav.heightOf(context);
            inset = UiPillNav.insetOf(context);
            return const _PillHost(destinations: threeDestinations);
          },
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(tester.getSize(find.byType(UiPillNav)).height, reported);
    expect(
      inset,
      reported + UiPillNav.gapOf(tester.element(find.byType(UiPillNav))),
    );
  });

  testWidgets('two to five destinations, and no more', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(child: const _PillHost(destinations: fiveDestinations)),
    );
    await tester.pumpAndSettle();
    expect(find.byType(UiPillNav), findsOneWidget);

    await tester.pumpWidget(
      uiHarness(
        child: UiPillNav(
          destinations: const <UiNavDestination>[
            UiNavDestination(label: 'Queue', icon: UiIcons.queue),
          ],
          currentIndex: 0,
          onSelect: (int _) {},
        ),
      ),
    );
    expect(tester.takeException(), isAssertionError);
  });

  testWidgets('it holds the glass budget', (WidgetTester tester) async {
    await tester.pumpWidget(
      uiHarness(child: const _PillHost(destinations: fiveDestinations)),
    );
    await tester.pumpAndSettle();
    expectGlassBudget(tester, window: 'the pill on its own');
  });

  for (final UiNavDestination destination in threeDestinations) {
    testWidgets('control contract: ${destination.label}', (
      WidgetTester tester,
    ) async {
      await expectControlContract(
        tester,
        (BuildContext context) =>
            const _PillHost(destinations: threeDestinations),
        semanticsLabel: destination.label,
      );
    });
  }
}
