import 'dart:ui' show Tristate;

import 'package:flutter/gestures.dart' show PointerDeviceKind;
import 'package:flutter/semantics.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';
import 'destinations.dart';

void _expectDestinationsReadOnce(WidgetTester tester, int selectedIndex) {
  final SemanticsNode list = tester.getSemantics(
    find.byWidgetPredicate(
      (Widget widget) =>
          widget is Semantics && widget.properties.role == SemanticsRole.tabBar,
    ),
  );
  final List<SemanticsNode> children = <SemanticsNode>[];
  list.visitChildren((SemanticsNode child) {
    children.add(child);
    return true;
  });
  expect(children, hasLength(threeDestinations.length));
  for (final MapEntry<int, UiNavDestination> entry
      in threeDestinations.asMap().entries) {
    expect(find.bySemanticsLabel(entry.value.label), findsOneWidget);
    final SemanticsData data = children[entry.key].getSemanticsData();
    expect(data.label, entry.value.label);
    expect(data.tooltip, isEmpty);
    expect(data.role, SemanticsRole.tab);
    expect(data.hasAction(SemanticsAction.tap), isTrue);
    expect(
      data.flagsCollection.isSelected,
      entry.key == selectedIndex ? Tristate.isTrue : Tristate.isFalse,
    );
  }
}

void main() {
  for (final bool rail in <bool>[false, true]) {
    for (final bool hover in <bool>[false, true]) {
      testWidgets(
        '${rail ? 'rail' : 'pill'} tab reads once before, during and after '
        '${hover ? 'hover' : 'long-press'} guidance',
        (WidgetTester tester) async {
          final SemanticsHandle semantics = tester.ensureSemantics();
          int selectedIndex = 0;
          final List<int> selections = <int>[];
          await tester.pumpWidget(
            uiHarness(
              child: StatefulBuilder(
                builder: (BuildContext context, StateSetter setState) {
                  void select(int index) {
                    selections.add(index);
                    setState(() => selectedIndex = index);
                  }

                  return rail
                      ? UiRail(
                          destinations: threeDestinations,
                          currentIndex: selectedIndex,
                          onSelect: select,
                          labelPresentation: UiRailLabelPresentation.icons,
                        )
                      : UiPillNav(
                          destinations: threeDestinations,
                          currentIndex: selectedIndex,
                          onSelect: select,
                        );
                },
              ),
            ),
          );
          await tester.pumpAndSettle();
          _expectDestinationsReadOnce(tester, 0);
          expect(find.text('Intake'), findsNothing);

          TestGesture? pointer;
          if (hover) {
            pointer = await tester.createGesture(kind: PointerDeviceKind.mouse);
            await pointer.addPointer(location: Offset.zero);
            addTearDown(pointer.removePointer);
            await tester.pump();
            await pointer.moveTo(
              tester.getCenter(find.bySemanticsLabel('Intake')),
            );
            await tester.pump();
            await tester.pump(UiTooltipStyle.hoverDelay);
            await tester.pumpAndSettle();
          } else {
            await tester.longPress(find.bySemanticsLabel('Intake'));
            await tester.pump();
            await tester.pump(const Duration(milliseconds: 100));
          }
          expect(find.text('Intake'), findsOneWidget);
          _expectDestinationsReadOnce(tester, 0);
          expect(selections, isEmpty);

          if (pointer != null) {
            await pointer.moveTo(const Offset(5, 5));
          } else {
            await tester.pump(UiTooltipStyle.touchDuration);
          }
          await tester.pumpAndSettle();
          expect(find.text('Intake'), findsNothing);
          _expectDestinationsReadOnce(tester, 0);

          await tester.tap(find.bySemanticsLabel('Intake'));
          await tester.pumpAndSettle();
          expect(selections, <int>[1]);
          _expectDestinationsReadOnce(tester, 1);
          semantics.dispose();
        },
      );
    }
  }

  for (final presentation in [
    UiRailLabelPresentation.adaptive,
    UiRailLabelPresentation.below,
  ]) {
    testWidgets(
      '$presentation touch rail labels remain visible and read once',
      (WidgetTester tester) async {
        final SemanticsHandle semantics = tester.ensureSemantics();
        try {
          int selectedIndex = 0;
          final selections = <int>[];
          await tester.pumpWidget(
            uiHarness(
              density: UiDensityMode.touch,
              child: StatefulBuilder(
                builder: (context, setState) => UiRail(
                  destinations: threeDestinations,
                  currentIndex: selectedIndex,
                  labelPresentation: presentation,
                  onSelect: (index) {
                    selections.add(index);
                    setState(() => selectedIndex = index);
                  },
                ),
              ),
            ),
          );
          await tester.pumpAndSettle();

          void expectPersistentLabels(int current) {
            for (final destination in threeDestinations) {
              expect(find.text(destination.label), findsOneWidget);
            }
            expect(find.byType(UiTooltip), findsNothing);
            _expectDestinationsReadOnce(tester, current);
          }

          expectPersistentLabels(0);
          final pointer = await tester.createGesture(
            kind: PointerDeviceKind.mouse,
          );
          await pointer.addPointer(location: Offset.zero);
          addTearDown(pointer.removePointer);
          await pointer.moveTo(
            tester.getCenter(find.bySemanticsLabel('Intake')),
          );
          await tester.pump(UiTooltipStyle.hoverDelay);
          await tester.pumpAndSettle();
          expectPersistentLabels(0);
          expect(selections, isEmpty);

          await tester.tap(find.text('Intake'));
          await tester.pumpAndSettle();
          expect(selections, <int>[1]);
          expectPersistentLabels(1);

          await pointer.moveTo(const Offset(5, 5));
          await tester.pumpAndSettle();
          expectPersistentLabels(1);
        } finally {
          semantics.dispose();
        }
      },
    );
  }
}
