// The adaptive shell at each window class (05 section 2; 07 section 1.2).
//
// One navigation control per class, and never two at once: a floating pill
// below 600, a collapsed rail to 839, an extended rail to 1199, and a sidebar
// at 1200 and above.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_digitization/src/app/shell.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/queue/queue_screen.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../ui_finders.dart';
import '../widget_test.dart' show TestRepository, TestSession;

/// A collection with no records.
///
/// The shell is what is under test here, and an empty queue keeps `QueueRow`
/// out of a 349 dp row, which it does not yet fit. See the skipped test in
/// `test/screens/queue_test.dart`.
class EmptyRepository extends TestRepository {
  @override
  Future<SpecimenPage> specimenPage(
    CollectionScope scope, {
    Map<String, String> filters = const {},
    String? cursor,
  }) async => const SpecimenPage(<Specimen>[]);
}

/// Pumps the app into a window of exactly [width] logical pixels.
Future<TestSession> pumpAt(WidgetTester tester, double width) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = Size(width, 1000);
  addTearDown(tester.view.reset);
  final TestSession session = TestSession();
  addTearDown(session.controller.close);
  await tester.pumpWidget(
    SpecimenDigitizationApp(session: session, repository: EmptyRepository()),
  );
  await tester.pumpAndSettle();
  return session;
}

/// Asserts that exactly one of the three navigations is on screen.
void expectOnly(Type navigation) {
  for (final Type candidate in <Type>[UiPillNav, UiRail, UiSidebar]) {
    expect(
      find.byType(candidate),
      candidate == navigation ? findsOneWidget : findsNothing,
      reason: '$candidate should ${candidate == navigation ? '' : 'not '}'
          'be the navigation here',
    );
  }
}

void main() {
  testWidgets('compact windows carry the floating pill', (tester) async {
    await pumpAt(tester, 400);
    expectOnly(UiPillNav);
    // The pill draws no words, so the name a screen reader reads is the only
    // one there is (10 section 4.4).
    expect(uiDestination('Queue'), findsOneWidget);
    expect(uiDestination('Intake'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('medium windows carry a collapsed rail', (tester) async {
    await pumpAt(tester, 700);
    expectOnly(UiRail);
    expect(tester.widget<UiRail>(find.byType(UiRail)).extended, isFalse);
    expect(
      find.text('Intake'),
      findsNothing,
      reason: 'a collapsed rail is glyphs only',
    );
    expect(uiDestination('Intake'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('expanded windows carry an extended rail', (tester) async {
    await pumpAt(tester, 900);
    expectOnly(UiRail);
    expect(tester.widget<UiRail>(find.byType(UiRail)).extended, isTrue);
    expect(
      find.text('Intake'),
      findsOneWidget,
      reason: 'an extended rail draws the words under the glyphs',
    );
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('large windows carry a sidebar and a list pane', (
    tester,
  ) async {
    await pumpAt(tester, 1300);
    expectOnly(UiSidebar);
    // List detail: the queue keeps its own pane beside the detail half.
    expect(find.byType(QueuePane), findsOneWidget);
    expect(find.text('No record open'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('the mark leads the navigation at every window class', (
    tester,
  ) async {
    for (final double width in <double>[400, 700, 900, 1300]) {
      await pumpAt(tester, width);
      expect(
        find.byType(UiMark),
        findsWidgets,
        reason: 'the mark is missing at $width',
      );
    }
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('the collection switcher is reachable at every window class', (
    tester,
  ) async {
    for (final double width in <double>[400, 700, 900, 1300]) {
      await pumpAt(tester, width);
      expect(
        find.byType(UiSelect<String>),
        findsOneWidget,
        reason: 'the switcher is missing at $width (07 section 1.2)',
      );
    }
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('help is in the account menu until the sidebar carries it', (
    tester,
  ) async {
    await pumpAt(tester, 900);
    expect(uiMenuTrigger(RegExp('^Account menu')), findsOneWidget);
    expect(uiIconButton(AppShell.helpLabel), findsNothing);

    await pumpAt(tester, 1300);
    expect(uiMenuTrigger(RegExp('^Account menu')), findsNothing);
    expect(
      uiIconButton(AppShell.helpLabel),
      findsOneWidget,
      reason: 'the sidebar carries the account, so the bar carries help',
    );
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('the environment band replaces the amber container', (
    tester,
  ) async {
    await pumpAt(tester, 400);
    expect(find.textContaining('Test environment.'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });
}
