// One arrangement per window (05 section 2, amended 2026-10-17).
//
// The shell used to decide "phone" with literals of its own (768 times the
// text scale, or under 600 tall) while every sheet, dialog and band asked the
// width class (under 600). A phone on its side, a 700 dp window and a tablet
// at 200 percent text therefore drew the phone's tab bar and a desktop's
// dialog at once. Both questions now go to `WindowArrangement`, so these
// windows get the tab bar and the sheet together, and the docked windows get
// the adaptive primary rail and the dialog together.
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_digitization/src/app/shell.dart';
import 'package:specimen_digitization/src/workspace.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../ui_finders.dart';
import '../widget_test.dart' show TestRepository, TestSession;
import 'error_persistence_test.dart' show FlakyRepository;

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

  // The queue is now the main page. The band precedes its content while
  // global navigation remains fixed at the edge.
  testWidgets('a band keeps navigation fixed and precedes the central queue', (
    tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(1180, 820);
    addTearDown(tester.view.reset);
    final repository = FlakyRepository()..failNext = true;
    final session = TestSession();
    addTearDown(session.controller.close);
    await tester.pumpWidget(
      SpecimenDigitizationApp(session: session, repository: repository),
    );
    await tester.pumpAndSettle();
    final band = find.byWidgetPredicate(
      (Widget widget) =>
          widget is UiBanner &&
          widget.message.startsWith('The service could not be reached.'),
      description: 'the failure band',
    );
    expect(band, findsOneWidget);
    final rail = find.byKey(const ValueKey('global-rail'));
    final pane = find.byKey(const ValueKey('global-sidebar'));
    final railWith = tester.getRect(rail);
    final paneWith = tester.getRect(pane);
    expect(railWith.top, 0);
    expect(paneWith.top, greaterThanOrEqualTo(tester.getRect(band).bottom));
    expect(
      tester.getRect(band).left,
      greaterThanOrEqualTo(railWith.right),
      reason: 'the band belongs to the main page beside global navigation',
    );

    await tester.tap(uiControl('Dismiss'));
    await tester.pumpAndSettle();
    expect(band, findsNothing);
    expect(tester.getRect(rail), railWith);
    final paneWithout = tester.getRect(pane);
    expect(paneWithout.left, paneWith.left);
    expect(paneWithout.width, paneWith.width);
    expect(paneWithout.top, lessThan(paneWith.top));
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a record band never moves navigation or its companion queue', (
    tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(1440, 900);
    addTearDown(tester.view.reset);
    final repository = FlakyRepository();
    final session = TestSession();
    addTearDown(session.controller.close);
    await tester.pumpWidget(
      SpecimenDigitizationApp(session: session, repository: repository),
    );
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('fixture-001'));
    await tester.tap(find.text('fixture-001'));
    await tester.pumpAndSettle();
    final controller = WorkspaceScope.read(
      tester.element(find.byType(AppShell)),
    );
    repository.failNext = true;
    await controller.refresh();
    await tester.pumpAndSettle();
    final band = find.byWidgetPredicate(
      (Widget widget) =>
          widget is UiBanner &&
          widget.message.startsWith('The service could not be reached.'),
      description: 'the record failure band',
    );
    expect(band, findsOneWidget);
    final rail = find.byKey(const ValueKey('global-rail'));
    final pane = find.byKey(const ValueKey('global-sidebar'));
    final railWith = tester.getRect(rail);
    final paneWith = tester.getRect(pane);
    expect(railWith.top, 0);
    expect(paneWith.top, 0);
    expect(tester.getRect(band).left, greaterThanOrEqualTo(paneWith.right));
    if (uiControl('Dismiss').evaluate().isEmpty) {
      // The narrower record work area can use the banner's strip variant;
      // its recovery and dismissal remain available in the opened sheet.
      await tester.tap(band);
      await tester.pumpAndSettle();
    }
    await tester.tap(uiControl('Dismiss'));
    await tester.pumpAndSettle();
    expect(band, findsNothing);
    expect(tester.getRect(rail), railWith);
    expect(tester.getRect(pane), paneWith);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('the docked rail keeps its arrow keys, Enter and its name', (
    tester,
  ) async {
    final semantics = tester.ensureSemantics();
    await _pump(tester, const Size(1440, 900), 1);
    final rail = find.byKey(const ValueKey('global-rail'));
    expect(tester.widget(rail), isA<UiRail>());
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
