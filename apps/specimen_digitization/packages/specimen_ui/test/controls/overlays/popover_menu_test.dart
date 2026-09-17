// `UiPopoverMenu` and `UiMenuTrigger` (10 section 4.3).

import 'dart:ui' show Tristate;

import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_ui/testing.dart';

import '../../harness/control_contract.dart';

/// What the menu did, so a test asserts on the command rather than on paint.
final List<String> chosen = <String>[];

List<UiMenuItem> items() => <UiMenuItem>[
  UiMenuItem(
    label: 'Copy record id',
    icon: UiIcons.copy,
    shortcut: 'Cmd C',
    onSelected: () => chosen.add('copy'),
  ),
  const UiMenuItem(
    label: 'Retry processing',
    icon: UiIcons.retry,
    onSelected: null,
    disabledReason: 'Wait for the run in flight to finish',
  ),
  UiMenuItem(
    label: 'Correct label regions',
    icon: UiIcons.correctRegions,
    onSelected: () => chosen.add('regions'),
  ),
  UiMenuItem(
    label: 'Discard this correction',
    icon: UiIcons.remove,
    destructive: true,
    onSelected: () => chosen.add('discard'),
  ),
];

class _MenuHost extends StatefulWidget {
  const _MenuHost();

  @override
  State<_MenuHost> createState() => _MenuHostState();
}

class _MenuHostState extends State<_MenuHost> {
  final PopoverController controller = PopoverController();

  @override
  void dispose() {
    controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => UiPopoverMenu(
    controller: controller,
    items: items(),
    child: UiButton(label: 'Record actions', onPressed: controller.toggle),
  );
}

void main() {
  setUp(chosen.clear);

  testWidgets('it opens on the trigger and closes on an outside tap', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(child: const _MenuHost()));
    expect(find.text('Copy record id'), findsNothing);

    await tester.tap(find.text('Record actions'));
    await tester.pumpAndSettle();
    expect(find.text('Copy record id'), findsOneWidget);
    expect(find.text('Cmd C'), findsOneWidget);

    await tester.tapAt(const Offset(10, 10));
    await tester.pumpAndSettle();
    expect(find.text('Copy record id'), findsNothing);
  });

  testWidgets('choosing an item runs it and closes the menu', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(child: const _MenuHost()));
    await tester.tap(find.text('Record actions'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Correct label regions'));
    await tester.pumpAndSettle();
    expect(chosen, <String>['regions']);
    expect(find.text('Copy record id'), findsNothing);
  });

  testWidgets('Escape closes it and focus returns to the trigger', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(child: const _MenuHost()));
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pumpAndSettle();
    final FocusNode? trigger = FocusManager.instance.primaryFocus;
    expect(trigger, isNotNull);

    await tester.tap(find.text('Record actions'));
    await tester.pumpAndSettle();
    expect(find.text('Copy record id'), findsOneWidget);

    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    await tester.pumpAndSettle();
    expect(find.text('Copy record id'), findsNothing);
    expect(FocusManager.instance.primaryFocus, trigger);
  });

  testWidgets('Down and Up move over the enabled items and wrap', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(child: const _MenuHost()));
    await tester.tap(find.text('Record actions'));
    await tester.pumpAndSettle();

    String? focused() => FocusManager.instance.primaryFocus?.debugLabel;
    // The first enabled item takes focus when the pane opens.
    expect(focused(), 'UiMenuItem 0');

    await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
    await tester.pumpAndSettle();
    // Item 1 is disabled, so Down skips it.
    expect(focused(), 'UiMenuItem 2');

    await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
    await tester.pumpAndSettle();
    expect(focused(), 'UiMenuItem 3');

    await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
    await tester.pumpAndSettle();
    expect(focused(), 'UiMenuItem 0', reason: 'Down wraps to the first item');

    await tester.sendKeyEvent(LogicalKeyboardKey.arrowUp);
    await tester.pumpAndSettle();
    expect(focused(), 'UiMenuItem 3', reason: 'Up wraps to the last item');
  });

  testWidgets('Enter activates the item the reviewer is on', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(child: const _MenuHost()));
    await tester.tap(find.text('Record actions'));
    await tester.pumpAndSettle();

    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(chosen, <String>['copy']);
    expect(find.text('Copy record id'), findsNothing);
  });

  testWidgets('the pane is a menu and its rows are menu items', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await tester.pumpWidget(uiHarness(child: const _MenuHost()));
    await tester.tap(find.text('Record actions'));
    await tester.pumpAndSettle();

    expect(
      tester
          .getSemantics(_withRole(SemanticsRole.menu))
          .getSemanticsData()
          .role,
      SemanticsRole.menu,
    );
    for (final UiMenuItem item in items()) {
      expect(
        tester
            .getSemantics(find.bySemanticsLabel(item.label))
            .getSemanticsData()
            .role,
        SemanticsRole.menuItem,
        reason: item.label,
      );
    }

    final SemanticsData disabled = tester
        .getSemantics(find.bySemanticsLabel('Retry processing'))
        .getSemanticsData();
    expect(disabled.flagsCollection.isEnabled, Tristate.isFalse);
    expect(disabled.hint, 'Wait for the run in flight to finish');
    handle.dispose();
  });

  testWidgets('the menu pane is the window only frosted pane', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(child: const _MenuHost()));
    await tester.tap(find.text('Record actions'));
    await tester.pumpAndSettle();
    expect(glassPaneCount(), 1);
    expectGlassBudget(tester);
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
          child: const _MenuHost(),
        ),
      );
      await tester.tap(find.text('Record actions'));
      await tester.pumpAndSettle();
      expect(find.text('Copy record id'), findsOneWidget);
      await tester.sendKeyEvent(LogicalKeyboardKey.escape);
      await tester.pumpAndSettle();
    }
  });

  testWidgets('nothing animates under reduced motion', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(disableAnimations: true, child: const _MenuHost()),
    );
    await tester.tap(find.text('Record actions'));
    await tester.pump();
    expect(find.text('Copy record id'), findsOneWidget);
    expect(tester.binding.transientCallbackCount, 0);
  });

  testWidgets('UiMenuTrigger satisfies the control contract', (
    WidgetTester tester,
  ) async {
    await expectControlContract(
      tester,
      (BuildContext context) =>
          UiMenuTrigger(semanticsLabel: 'Record actions', items: items()),
      semanticsLabel: 'Record actions',
      labelsNeverWrap: true,
      geometryFromType: true,
      fit: FitExpectation(
        check: (WidgetTester tester, double width) async {
          expect(find.bySemanticsLabel('Record actions'), findsOneWidget);
        },
      ),
    );
  });
}

/// The one `Semantics` widget declaring [role].
///
/// Read from the widget tree rather than walked from the root semantics node,
/// because the binding's own owner is deprecated and the root pipeline owner
/// carries no semantics owner of its own.
Finder _withRole(SemanticsRole role) => find.byWidgetPredicate(
  (Widget widget) => widget is Semantics && widget.properties.role == role,
);
