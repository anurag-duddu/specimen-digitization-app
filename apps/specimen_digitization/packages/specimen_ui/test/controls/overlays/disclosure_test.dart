// `UiDisclosure` (10 section 4.3).

import 'dart:ui' show Tristate;

import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_ui/testing.dart';

import '../../harness/control_contract.dart';

const String _title = 'Label coverage';
const String _summary = 'Three regions, one unmeasured';
const String _body =
    'Region 3 has no measured area, so coverage is reported for two regions.';
const String _label = '$_title. $_summary';

Widget _disclosure({
  Key? key,
  bool initiallyExpanded = false,
  ValueChanged<bool>? onExpansionChanged,
}) => SizedBox(
  width: 360,
  child: UiDisclosure(
    key: key,
    title: _title,
    summary: _summary,
    initiallyExpanded: initiallyExpanded,
    onExpansionChanged: onExpansionChanged,
    child: const Text(_body),
  ),
);

void main() {
  testWidgets('the body is hidden until the row is pressed', (
    WidgetTester tester,
  ) async {
    final List<bool> changes = <bool>[];
    await tester.pumpWidget(
      uiHarness(child: _disclosure(onExpansionChanged: changes.add)),
    );
    expect(find.text(_body), findsNothing);

    await tester.tap(find.bySemanticsLabel(_label));
    await tester.pumpAndSettle();
    expect(find.text(_body), findsOneWidget);
    expect(changes, <bool>[true]);

    await tester.tap(find.bySemanticsLabel(_label));
    await tester.pumpAndSettle();
    expect(find.text(_body), findsNothing);
    expect(changes, <bool>[true, false]);
  });

  testWidgets('it can be built open', (WidgetTester tester) async {
    await tester.pumpWidget(
      uiHarness(child: _disclosure(initiallyExpanded: true)),
    );
    await tester.pumpAndSettle();
    expect(find.text(_body), findsOneWidget);
  });

  testWidgets('Space and Enter toggle it', (WidgetTester tester) async {
    for (final LogicalKeyboardKey key in <LogicalKeyboardKey>[
      LogicalKeyboardKey.space,
      LogicalKeyboardKey.enter,
    ]) {
      // A fresh key, so the second pass starts closed rather than reusing
      // the state the first one left open.
      await tester.pumpWidget(
        uiHarness(child: _disclosure(key: ValueKey<String>(key.keyLabel))),
      );
      await tester.sendKeyEvent(LogicalKeyboardKey.tab);
      await tester.pumpAndSettle();
      await tester.sendKeyEvent(key);
      await tester.pumpAndSettle();
      expect(find.text(_body), findsOneWidget, reason: key.keyLabel);
    }
  });

  testWidgets('the caret turns half a circle and the row reports expanded', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await tester.pumpWidget(uiHarness(child: _disclosure()));

    double turns() =>
        tester.widget<AnimatedRotation>(find.byType(AnimatedRotation)).turns;
    Tristate expanded() => tester
        .getSemantics(find.bySemanticsLabel(_label))
        .getSemanticsData()
        .flagsCollection
        .isExpanded;

    expect(turns(), 0);
    expect(expanded(), Tristate.isFalse);

    await tester.tap(find.bySemanticsLabel(_label));
    await tester.pumpAndSettle();
    expect(turns(), UiDisclosureStyle.caretTurns);
    expect(expanded(), Tristate.isTrue);
    handle.dispose();
  });

  testWidgets('the body keeps its own semantics and is never glass', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(child: _disclosure(initiallyExpanded: true)),
    );
    await tester.pumpAndSettle();
    expect(
      find.text(_body),
      findsOneWidget,
      reason: 'the header wrapper must not swallow the body',
    );
    expect(
      glassPaneCount(),
      0,
      reason: 'a disclosure is content inside a pane, not a pane',
    );
    expectGlassBudget(tester);
  });

  testWidgets('it collapses its motion under reduced motion', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(disableAnimations: true, child: _disclosure()),
    );
    await tester.tap(find.bySemanticsLabel(_label));
    await tester.pump();
    expect(find.text(_body), findsOneWidget);
    expect(tester.binding.transientCallbackCount, 0);
  });

  testWidgets('it builds right to left and at 200 percent text', (
    WidgetTester tester,
  ) async {
    for (final (TextDirection direction, TextScaler scaler)
        in <(TextDirection, TextScaler)>[
          (TextDirection.rtl, TextScaler.noScaling),
          (TextDirection.ltr, const TextScaler.linear(2)),
        ]) {
      await tester.pumpWidget(
        uiHarness(
          textDirection: direction,
          textScaler: scaler,
          child: _disclosure(initiallyExpanded: true),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text(_body), findsOneWidget);
    }
  });

  testWidgets('it satisfies the control contract', (
    WidgetTester tester,
  ) async {
    await expectControlContract(
      tester,
      (BuildContext context) => _disclosure(),
      semanticsLabel: _label,
    );
  });
}
