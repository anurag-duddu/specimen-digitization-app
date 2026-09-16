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

/// The leading bar of the row labelled [label].
BorderSide _bar(WidgetTester tester, String label) {
  final DecoratedBox box = tester.widget<DecoratedBox>(
    find
        .descendant(
          of: find.bySemanticsLabel(label),
          matching: find.byType(DecoratedBox),
        )
        .first,
  );
  return ((box.decoration as BoxDecoration).border! as BorderDirectional).start;
}

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
    expect(
      UiSidebar.widthOf(tester.element(find.byType(UiSidebar))),
      280,
    );
    expect(glassPaneCount(), 1);
  });

  testWidgets('the current row carries the bar and the fill glyph', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(child: const _SidebarHost(destinations: threeDestinations)),
    );
    await tester.pumpAndSettle();
    final UiThemeData ui = tester.element(find.byType(UiSidebar)).ui;

    expect(_bar(tester, 'Queue').color, ui.color.ink);
    expect(_bar(tester, 'Queue').width, ui.shape.stroke.bar);
    expect(_bar(tester, 'Queue').width, 3);
    expect(
      _bar(tester, 'Intake').color.a,
      0,
      reason:
          'every row carries the bar so the current one does not shift its '
          'words when it becomes current',
    );
    expect(_glyph(tester, 'Queue'), UiIcons.queue.filled);
    expect(_glyph(tester, 'Intake'), UiIcons.intake.glyph);

    await tester.tap(find.bySemanticsLabel('Intake'));
    await tester.pumpAndSettle();
    expect(_bar(tester, 'Intake').color, ui.color.ink);
    expect(_glyph(tester, 'Intake'), UiIcons.intake.filled);
    expect(_bar(tester, 'Queue').color.a, 0);
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

  for (final UiNavDestination destination in threeDestinations) {
    testWidgets('control contract: ${destination.label}', (
      WidgetTester tester,
    ) async {
      await expectControlContract(
        tester,
        (BuildContext context) =>
            const _SidebarHost(destinations: threeDestinations),
        semanticsLabel: destination.label,
      );
    });
  }
}
