// The navigation rail (10 section 4.4, `UiRail`).

import 'dart:ui' show Tristate;

import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_ui/testing.dart';

import '../../harness/control_contract.dart';
import 'destinations.dart';

class _RailHost extends StatefulWidget {
  const _RailHost({
    required this.destinations,
    this.onSelect,
    this.extended = false,
    this.leading,
  });

  final List<UiNavDestination> destinations;
  final ValueChanged<int>? onSelect;
  final bool extended;
  final Widget? leading;

  @override
  State<_RailHost> createState() => _RailHostState();
}

class _RailHostState extends State<_RailHost> {
  int _current = 0;

  @override
  Widget build(BuildContext context) => UiRail(
    destinations: widget.destinations,
    currentIndex: _current,
    extended: widget.extended,
    leading: widget.leading,
    onSelect: (int index) {
      widget.onSelect?.call(index);
      setState(() => _current = index);
    },
  );
}

double _discTop(WidgetTester tester) => tester
    .getTopLeft(
      find.descendant(
        of: find.byType(UiRail),
        matching: find.byType(AnimatedPositionedDirectional),
      ),
    )
    .dy;

void main() {
  testWidgets('a pointer selects the destination it lands on', (
    WidgetTester tester,
  ) async {
    final List<int> selected = <int>[];
    await tester.pumpWidget(
      uiHarness(
        child: _RailHost(
          destinations: threeDestinations,
          onSelect: selected.add,
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.bySemanticsLabel('Sources'));
    await tester.pumpAndSettle();
    expect(selected, <int>[2]);
  });

  testWidgets('down and up move, Enter selects', (WidgetTester tester) async {
    final List<int> selected = <int>[];
    await tester.pumpWidget(
      uiHarness(
        child: _RailHost(
          destinations: threeDestinations,
          onSelect: selected.add,
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
    await tester.pumpAndSettle();
    expect(selected, isEmpty);
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(selected, <int>[2]);

    await tester.sendKeyEvent(LogicalKeyboardKey.arrowUp);
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(selected, <int>[2, 1]);
  });

  testWidgets('the cross axis keys are left for the reviewer to leave with', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(child: const _RailHost(destinations: threeDestinations)),
    );
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pumpAndSettle();
    final FocusNode? before = FocusManager.instance.primaryFocus;
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.pumpAndSettle();
    expect(
      FocusManager.instance.primaryFocus,
      same(before),
      reason:
          'a vertical group that swallowed Right would trap a keyboard '
          'reviewer inside the rail',
    );
  });

  testWidgets('the disc glides down the column', (WidgetTester tester) async {
    await tester.pumpWidget(
      uiHarness(child: const _RailHost(destinations: threeDestinations)),
    );
    await tester.pumpAndSettle();
    final double start = _discTop(tester);

    await tester.tap(find.bySemanticsLabel('Sources'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 120));
    final double midway = _discTop(tester);
    await tester.pumpAndSettle();
    final double end = _discTop(tester);

    expect(midway, greaterThan(start));
    expect(midway, lessThan(end));
  });

  testWidgets('collapsed is 72 dp and draws no words', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(child: const _RailHost(destinations: threeDestinations)),
    );
    await tester.pumpAndSettle();
    final BuildContext context = tester.element(find.byType(UiRail));
    expect(
      tester.getSize(find.byType(UiRail)).width,
      UiRailStyle.minWidthOf(context.ui),
    );
    expect(UiRailStyle.minWidthOf(context.ui), 72);
    expect(find.text('Sources'), findsNothing);
  });

  testWidgets('extended draws the words under each glyph', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: const _RailHost(
          destinations: threeDestinations,
          extended: true,
        ),
      ),
    );
    await tester.pumpAndSettle();
    for (final UiNavDestination destination in threeDestinations) {
      expect(find.text(destination.label), findsOneWidget);
    }
    final Offset glyph = tester.getCenter(
      find.descendant(
        of: find.bySemanticsLabel('Queue'),
        matching: find.byType(Icon).first,
      ),
    );
    expect(
      tester.getCenter(find.text('Queue')).dy,
      greaterThan(glyph.dy),
      reason: 'the words sit under the glyph, not beside it',
    );
  });

  testWidgets('extended widens rather than clipping at 200 percent text', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: const _RailHost(
          destinations: threeDestinations,
          extended: true,
        ),
      ),
    );
    await tester.pumpAndSettle();
    final double atRest = tester.getSize(find.byType(UiRail)).width;

    await tester.pumpWidget(
      uiHarness(
        textScaler: const TextScaler.linear(2),
        child: const _RailHost(
          destinations: threeDestinations,
          extended: true,
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      tester.getSize(find.byType(UiRail)).width,
      greaterThan(atRest),
      reason: 'a 72 dp column cannot hold a word it cannot break',
    );
    expect(find.text('Sources'), findsOneWidget);
  });

  testWidgets('the leading slot sits above the destinations', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: const _RailHost(
          destinations: threeDestinations,
          leading: SizedBox.square(
            key: ValueKey<String>('mark'),
            dimension: 24,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      tester.getBottomLeft(find.byKey(const ValueKey<String>('mark'))).dy,
      lessThan(tester.getTopLeft(find.bySemanticsLabel('Queue')).dy),
    );
  });

  testWidgets('every destination is a tab, one is selected', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(child: const _RailHost(destinations: threeDestinations)),
    );
    await tester.pumpAndSettle();
    for (final MapEntry<int, UiNavDestination> entry
        in threeDestinations.asMap().entries) {
      final SemanticsData data = tester
          .getSemantics(find.bySemanticsLabel(entry.value.label))
          .getSemanticsData();
      expect(data.role, SemanticsRole.tab);
      expect(
        data.flagsCollection.isSelected,
        entry.key == 0 ? Tristate.isTrue : Tristate.isFalse,
      );
    }
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

  testWidgets('a rail carries no glass of its own', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(child: const _RailHost(destinations: threeDestinations)),
    );
    await tester.pumpAndSettle();
    expect(glassPaneCount(), 0);
  });

  for (final bool extended in <bool>[false, true]) {
    for (final UiNavDestination destination in threeDestinations) {
      testWidgets(
        'control contract: ${destination.label}, '
        '${extended ? 'extended' : 'collapsed'}',
        (WidgetTester tester) async {
          await expectControlContract(
            tester,
            (BuildContext context) => _RailHost(
              destinations: threeDestinations,
              extended: extended,
            ),
            semanticsLabel: destination.label,
          );
        },
      );
    }
  }
}
