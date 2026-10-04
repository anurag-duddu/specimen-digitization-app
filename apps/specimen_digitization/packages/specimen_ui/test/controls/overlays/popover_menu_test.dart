// `UiPopoverMenu` and `UiMenuTrigger` (10 section 4.3).

import 'dart:ui' show PointerDeviceKind, Tristate;

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

  for (final PointerDeviceKind kind in <PointerDeviceKind>[
    PointerDeviceKind.mouse,
    PointerDeviceKind.touch,
  ]) {
    for (final bool sharedTrigger in <bool>[false, true]) {
      testWidgets(
        '${sharedTrigger ? 'UiMenuTrigger' : 'a custom menu trigger'} '
        'closes on a second ${kind.name} press without reopening',
        (WidgetTester tester) async {
          await tester.pumpWidget(
            uiHarness(
              child: sharedTrigger
                  ? UiMenuTrigger(
                      semanticsLabel: 'Record actions',
                      items: items(),
                    )
                  : const _MenuHost(),
            ),
          );
          final Finder trigger = find.bySemanticsLabel('Record actions');
          final Offset position = tester.getCenter(trigger);
          final TestGesture first = await tester.startGesture(
            position,
            kind: kind,
          );
          await first.up();
          await tester.pumpAndSettle();
          expect(find.text('Copy record id'), findsOneWidget);

          // A browser sends down and up in separate frames. Dismissal must
          // not treat the trigger as outside on down, then reopen on up.
          final TestGesture second = await tester.startGesture(
            position,
            kind: kind,
          );
          await tester.pump();
          final bool remainedOpen = find
              .text('Copy record id')
              .evaluate()
              .isNotEmpty;
          await second.up();
          await tester.pumpAndSettle();
          expect(find.text('Copy record id'), findsNothing);
          expect(
            remainedOpen,
            isTrue,
            reason: 'the trigger is inside its menu',
          );
          expect(chosen, isEmpty, reason: 'closing the menu runs no command');

          final TestGesture third = await tester.startGesture(
            position,
            kind: kind,
          );
          await third.up();
          await tester.pumpAndSettle();
          expect(find.text('Copy record id'), findsOneWidget);
          final TestGesture outside = await tester.startGesture(
            const Offset(10, 10),
            kind: kind,
          );
          await tester.pump();
          expect(find.text('Copy record id'), findsNothing);
          await outside.up();
          await tester.pumpAndSettle();
          expect(find.text('Copy record id'), findsNothing);
        },
      );
    }
  }

  testWidgets('pressing another menu trigger closes only the first menu', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            UiMenuTrigger(
              semanticsLabel: 'First actions',
              items: <UiMenuItem>[
                UiMenuItem(label: 'Copy first specimen', onSelected: () {}),
              ],
            ),
            UiMenuTrigger(
              semanticsLabel: 'Second actions',
              items: <UiMenuItem>[
                UiMenuItem(label: 'Copy second specimen', onSelected: () {}),
              ],
            ),
          ],
        ),
      ),
    );
    await tester.tap(find.bySemanticsLabel('First actions'));
    await tester.pumpAndSettle();
    expect(find.text('Copy first specimen'), findsOneWidget);

    final TestGesture next = await tester.startGesture(
      tester.getCenter(find.bySemanticsLabel('Second actions')),
      kind: PointerDeviceKind.mouse,
    );
    await tester.pump();
    expect(find.text('Copy first specimen'), findsNothing);
    await next.up();
    await tester.pumpAndSettle();
    expect(find.text('Copy second specimen'), findsOneWidget);
    expect(find.text('Copy first specimen'), findsNothing);
  });

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

  testWidgets('a trigger at the end of a phone\'s line keeps its menu on it', (
    WidgetTester tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(390, 800);
    addTearDown(tester.view.reset);
    for (final TextDirection direction in TextDirection.values) {
      await tester.pumpWidget(
        uiHarness(
          size: const Size(390, 800),
          textDirection: direction,
          child: Align(
            alignment: AlignmentDirectional.centerEnd,
            child: UiMenuTrigger(
              semanticsLabel: 'Record actions',
              items: items(),
            ),
          ),
        ),
      );
      await tester.tap(find.bySemanticsLabel('Record actions'));
      await tester.pumpAndSettle();

      final Rect anchor = tester.getRect(
        find.bySemanticsLabel('Record actions'),
      );
      final Rect pane = tester.getRect(find.byType(GlassSurface));
      expect(pane.left, greaterThanOrEqualTo(0), reason: direction.name);
      expect(pane.right, lessThanOrEqualTo(390), reason: direction.name);
      if (direction == TextDirection.ltr) {
        expect(pane.right, moreOrLessEquals(anchor.right, epsilon: 0.5));
      } else {
        expect(pane.left, moreOrLessEquals(anchor.left, epsilon: 0.5));
      }
      await tester.sendKeyEvent(LogicalKeyboardKey.escape);
      await tester.pumpAndSettle();
    }
  });

  testWidgets('the menu draws one matte floating surface', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(child: const _MenuHost()));
    await tester.tap(find.text('Record actions'));
    await tester.pumpAndSettle();
    expect(glassPaneCount(), 0);
    expect(
      find.byWidgetPredicate(
        (Widget widget) =>
            widget is GlassSurface && widget.level == GlassLevel.floating,
      ),
      findsOneWidget,
    );
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
