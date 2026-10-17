// One arrangement per window (05 section 2, amended 2026-10-17).
//
// The shell used to decide "phone" with literals of its own (768 times the
// text scale, or under 600 tall) while every sheet, dialog and band asked the
// width class (under 600). A phone on its side, a 700 dp window and a tablet
// at 200 percent text therefore drew the phone's tab bar and a desktop's
// dialog at once. Both questions now go to `WindowArrangement`, so these
// windows get the tab bar and the sheet together, and the docked windows get
// the rail and the dialog together.
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_digitization/src/app/shell.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../ui_finders.dart';
import '../widget_test.dart' show TestRepository, TestSession;

Future<void> _pump(WidgetTester tester, Size window, double textScale) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = window;
  tester.platformDispatcher.textScaleFactorTestValue = textScale;
  addTearDown(tester.view.reset);
  addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
  final session = TestSession();
  addTearDown(session.controller.close);
  await tester.pumpWidget(
    SpecimenDigitizationApp(session: session, repository: TestRepository()),
  );
  await tester.pumpAndSettle();
}

void main() {
  for (final (Size window, double scale, bool stacked) in <(Size, double, bool)>[
    // A phone on its side: the expanded width class, the phone's arrangement.
    (const Size(844, 390), 1, true),
    // Medium by width, under the docked minimum.
    (const Size(700, 1000), 1, true),
    // A tablet at 200 percent text.
    (const Size(1180, 820), 2, true),
    (const Size(390, 844), 1, true),
    (const Size(1180, 820), 1, false),
    (const Size(1440, 900), 1, false),
  ]) {
    testWidgets('$window at ${scale}x: the navigation and the modal agree', (
      tester,
    ) async {
      await _pump(tester, window, scale);
      final context = tester.element(find.byType(AppShell));
      expect(WindowArrangement.of(context).isStacked, stacked);
      expect(find.byType(UiTabBar), stacked ? findsOneWidget : findsNothing);
      expect(
        find.byKey(const ValueKey('global-rail')),
        stacked ? findsNothing : findsOneWidget,
      );

      // The environment control is in the compact top bar on a stacked window
      // and at the foot of the rail on a docked one; either way it opens the
      // product's adaptive modal.
      final environment = find.bySemanticsLabel('Test environment');
      await tester.ensureVisible(environment);
      await tester.pumpAndSettle();
      await tester.tap(environment);
      await tester.pumpAndSettle();
      expect(
        find.byType(UiSheet),
        stacked ? findsOneWidget : findsNothing,
        reason: 'a window that draws the tab bar gets the sheet',
      );
      expect(find.byType(UiDialog), stacked ? findsNothing : findsOneWidget);
      await tester.sendKeyEvent(LogicalKeyboardKey.escape);
      await tester.pumpAndSettle();
      await tester.pumpWidget(const SizedBox());
    });
  }

  testWidgets('the docked rail keeps its arrow keys, Enter and its name', (
    tester,
  ) async {
    final semantics = tester.ensureSemantics();
    await _pump(tester, const Size(1440, 900), 1);
    final rail = find.byKey(const ValueKey('global-rail'));
    expect(
      find.descendant(of: rail, matching: find.byType(UiRail)),
      findsOneWidget,
    );
    expect(
      find.bySemanticsLabel(AppShell.navigationLabel),
      findsOneWidget,
      reason: 'the tab list keeps the name the hand-built column had',
    );
    final specimens = uiDestination('Specimens');
    final intake = uiDestination('Intake');
    expect(specimens, findsOneWidget);
    expect(intake, findsOneWidget);

    final nodes = tester
        .widgetList<Pressable>(
          find.descendant(of: rail, matching: find.byType(Pressable)),
        )
        .where((Pressable p) => p.role == PressableRole.tab)
        .toList();
    expect(nodes.map((p) => p.semanticsLabel), ['Specimens', 'Intake']);
    nodes.first.focusNode!.requestFocus();
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
    await tester.pumpAndSettle();
    expect(nodes.last.focusNode!.hasPrimaryFocus, isTrue);
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
    await tester.pumpAndSettle();
    expect(
      nodes.first.focusNode!.hasPrimaryFocus,
      isTrue,
      reason: 'focus wraps, as the hand-built column did',
    );
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowUp);
    await tester.pumpAndSettle();
    expect(nodes.last.focusNode!.hasPrimaryFocus, isTrue);
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    final current = tester.widget<UiRail>(find.byType(UiRail)).currentIndex;
    expect(AppShell.destinations[current].label, 'Intake');
    semantics.dispose();
    await tester.pumpWidget(const SizedBox());
  });
}
