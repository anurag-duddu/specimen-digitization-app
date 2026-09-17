// The navigation sidebar (10 section 4.4, `UiSidebar`).

import 'dart:ui' show Tristate;

import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_ui/testing.dart';

import '../../harness/control_contract.dart';
import 'destinations.dart';

class _SidebarHost extends StatefulWidget {
  const _SidebarHost({
    required this.destinations,
    this.onSelect,
    this.header,
    this.footer,
  });

  final List<UiNavDestination> destinations;
  final ValueChanged<int>? onSelect;
  final Widget? header;
  final Widget? footer;

  @override
  State<_SidebarHost> createState() => _SidebarHostState();
}

class _SidebarHostState extends State<_SidebarHost> {
  int _current = 0;

  @override
  Widget build(BuildContext context) => SizedBox(
    height: 600,
    child: UiSidebar(
      destinations: widget.destinations,
      currentIndex: _current,
      header: widget.header,
      footer: widget.footer,
      onSelect: (int index) {
        widget.onSelect?.call(index);
        setState(() => _current = index);
      },
    ),
  );
}

/// The leading bar of the row labelled [label], drawn or not.
///
/// `UiListRow` paints the bar as a positioned `ColoredBox` in the row's own
/// stack, and only on a selected row; the gutter it sits in is reserved on
/// every row by padding, so nothing shifts when a row becomes current.
Finder _bar(WidgetTester tester, String label) => find.descendant(
  of: find.bySemanticsLabel(label),
  matching: find.byWidgetPredicate(
    (Widget widget) => widget is ColoredBox && widget.child == null,
  ),
);

/// The fill behind the row labelled [label].
Color _fill(WidgetTester tester, String label) => tester
    .widget<ColoredBox>(
      find
          .descendant(
            of: find.bySemanticsLabel(label),
            matching: find.byWidgetPredicate(
              (Widget widget) => widget is ColoredBox && widget.child != null,
            ),
          )
          .first,
    )
    .color;

/// The glyph of the row labelled [label].
IconData _glyph(WidgetTester tester, String label) => tester
    .widget<Icon>(
      find
          .descendant(
            of: find.bySemanticsLabel(label),
            matching: find.byType(Icon),
          )
          .first,
    )
    .icon!;

void main() {
  testWidgets('a pointer selects the row it lands on', (
    WidgetTester tester,
  ) async {
    final List<int> selected = <int>[];
    await tester.pumpWidget(
      uiHarness(
        child: _SidebarHost(
          destinations: threeDestinations,
          onSelect: selected.add,
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.bySemanticsLabel('Intake'));
    await tester.pumpAndSettle();
    expect(selected, <int>[1]);
  });

  testWidgets('down and up move, Enter selects', (WidgetTester tester) async {
    final List<int> selected = <int>[];
    await tester.pumpWidget(
      uiHarness(
        child: _SidebarHost(
          destinations: threeDestinations,
          onSelect: selected.add,
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(selected, <int>[1]);
  });

  testWidgets('it is 280 dp wide and carries one flat pane', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(child: const _SidebarHost(destinations: threeDestinations)),
    );
    await tester.pumpAndSettle();
    expect(tester.getSize(find.byType(UiSidebar)).width, 280);
    expect(UiSidebar.widthOf(tester.element(find.byType(UiSidebar))), 280);
    expect(glassPaneCount(), 1);
  });

  testWidgets('the current row carries the bar, the fill and the fill glyph', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(child: const _SidebarHost(destinations: threeDestinations)),
    );
    await tester.pumpAndSettle();
    final UiThemeData ui = tester.element(find.byType(UiSidebar)).ui;

    expect(_bar(tester, 'Queue'), findsOneWidget);
    expect(
      tester.widget<ColoredBox>(_bar(tester, 'Queue').first).color,
      ui.color.ink,
    );
    expect(
      tester.getSize(_bar(tester, 'Queue').first).width,
      ui.shape.stroke.bar,
    );
    expect(tester.getSize(_bar(tester, 'Queue').first).width, 3);
    expect(
      _fill(tester, 'Queue'),
      ui.color.stateLayer(UiListRowStyle.selectedFillOpacity),
      reason: 'a selected row fills ink at 6 percent (10 section 4.5)',
    );
    expect(_bar(tester, 'Intake'), findsNothing);
    expect(_fill(tester, 'Intake').a, 0);
    expect(_glyph(tester, 'Queue'), UiIcons.queue.filled);
    expect(_glyph(tester, 'Intake'), UiIcons.intake.glyph);

    // The bar's gutter is reserved whether or not the bar is drawn, so a row
    // becoming current never shifts its words sideways.
    final double before = tester.getTopLeft(find.text('Intake')).dx;
    await tester.tap(find.bySemanticsLabel('Intake'));
    await tester.pumpAndSettle();
    expect(tester.getTopLeft(find.text('Intake')).dx, before);
    expect(
      tester.widget<ColoredBox>(_bar(tester, 'Intake').first).color,
      ui.color.ink,
    );
    expect(_glyph(tester, 'Intake'), UiIcons.intake.filled);
    expect(_bar(tester, 'Queue'), findsNothing);
  });

  testWidgets('the header sits above the rows and the footer below', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: const _SidebarHost(
          destinations: threeDestinations,
          header: Text('Specimen Digitization'),
          footer: Text('Signed in as a reviewer'),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      tester.getBottomLeft(find.text('Specimen Digitization')).dy,
      lessThan(tester.getTopLeft(find.bySemanticsLabel('Queue')).dy),
    );
    expect(
      tester.getTopLeft(find.text('Signed in as a reviewer')).dy,
      greaterThan(tester.getBottomLeft(find.bySemanticsLabel('Sources')).dy),
    );
  });

  testWidgets('every row is a tab, one is selected', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(child: const _SidebarHost(destinations: threeDestinations)),
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

  testWidgets('a row holds its words at every text scale', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(child: const _SidebarHost(destinations: threeDestinations)),
    );
    await tester.pumpAndSettle();
    final double atRest = tester.getSize(find.bySemanticsLabel('Queue')).height;

    // At 200 percent the words still fit inside the density's row height, so
    // the row holds and nothing is clipped.
    await tester.pumpWidget(
      uiHarness(
        textScaler: const TextScaler.linear(2),
        child: const _SidebarHost(destinations: threeDestinations),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      tester.getSize(find.bySemanticsLabel('Queue')).height,
      greaterThanOrEqualTo(tester.getSize(find.text('Queue')).height),
    );

    // Past the point where they do not, the row grows rather than clipping:
    // the row height is a floor, not a fixed height (10 section 2 clause 7).
    await tester.pumpWidget(
      uiHarness(
        textScaler: const TextScaler.linear(3),
        child: const _SidebarHost(destinations: threeDestinations),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      tester.getSize(find.bySemanticsLabel('Queue')).height,
      greaterThan(atRest),
    );
  });

  testWidgets('the destinations scroll when the pane is too short for them', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: SizedBox(
          height: 200,
          child: UiSidebar(
            destinations: fiveDestinations,
            currentIndex: 0,
            onSelect: (int _) {},
            header: const Text('Specimen Digitization'),
            footer: const Text('Signed in as a reviewer'),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(find.text('Specimen Digitization'), findsOneWidget);
    expect(find.text('Signed in as a reviewer'), findsOneWidget);

    // The last destination is off the bottom of the list and reachable by
    // scrolling rather than lost with the pane clipped over it.
    await tester.drag(
      find.byType(SingleChildScrollView),
      const Offset(0, -400),
    );
    await tester.pumpAndSettle();
    expect(
      tester.getRect(find.bySemanticsLabel('Account')).bottom,
      lessThanOrEqualTo(tester.getRect(find.byType(UiSidebar)).bottom),
    );
  });

  for (final UiNavDestination destination in threeDestinations) {
    testWidgets('control contract: ${destination.label}', (
      WidgetTester tester,
    ) async {
      await expectControlContract(
        tester,
        (BuildContext context) =>
            const _SidebarHost(destinations: threeDestinations),
        semanticsLabel: destination.label,
        labelsNeverWrap: true,
        geometryFromType: true,
        fit: FitExpectation(
          check: (WidgetTester tester, double width) async {
            expect(
              find.bySemanticsLabel(destination.label),
              findsOneWidget,
              reason: 'every destination stays reachable at $width dp',
            );
          },
        ),
      );
    });
  }
}
