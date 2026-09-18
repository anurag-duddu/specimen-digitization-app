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
import 'package:specimen_digitization/src/screens/intake/manifest_panel.dart';
import 'package:specimen_digitization/src/screens/queue/queue_screen.dart';
import 'package:specimen_digitization/src/widgets/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../golden/golden_harness.dart';
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
      reason:
          '$candidate should ${candidate == navigation ? '' : 'not '}'
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

  testWidgets('large windows carry a sidebar and a list pane', (tester) async {
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

  // The chrome the route decides (13 sections 2.3 and 3.4). The frame is
  // built once and the router swaps the body inside it, so what the bar says,
  // whether the navigation is drawn and which form the band takes are the
  // shell's answers and not the screen's.
  group('by route', () {
    /// True where the navigation of [type] is drawn rather than kept.
    ///
    /// A hidden navigation is `Offstage` rather than absent, so a pill keeps
    /// the destination it was on and still holds no viewport height. The
    /// finder therefore has to look past the offstage that a default finder
    /// skips, which is also why "the pill is gone" and "the pill is hidden"
    /// are not the same assertion.
    bool navigationShown(WidgetTester tester, Type type) {
      final Finder nav = find.byType(type, skipOffstage: false);
      expect(nav, findsOneWidget, reason: '$type is not in the frame at all');
      final Finder offstage = find.ancestor(
        of: nav,
        matching: find.byType(Offstage, skipOffstage: false),
      );
      if (offstage.evaluate().isEmpty) return true;
      return !tester.widget<Offstage>(offstage.first).offstage;
    }

    testWidgets(
      'a record names itself, offers the way out and hides the pill',
      (WidgetTester tester) async {
        await pumpGoldenApp(
          tester,
          window: const Size(390, 844),
          brightness: Brightness.light,
          location: goldenSpecimenLocation,
        );

        expect(
          find.bySemanticsLabel(AppShell.backLabel),
          findsWidgets,
          reason: '13 section 2.3 gives the way out to the top bar',
        );
        // The bar's own label, not every drawing of the identifier: the
        // record screen still prints its own id in the evidence below, which
        // is slot A2's to reconcile with 13 section 2.4.
        expect(
          tester
              .widgetList<UiLabel>(
                find.descendant(
                  of: find.byType(UiTopBar),
                  matching: find.byType(UiLabel),
                ),
              )
              .map((UiLabel label) => label.text),
          contains(goldenSpecimenId),
          reason: '13 section 4.1: the bar names the record',
        );
        expect(
          find.byType(UiSelect<String>),
          findsNothing,
          reason: 'the collection switcher is not shown inside a record',
        );
        expect(
          navigationShown(tester, UiPillNav),
          isFalse,
          reason: 'the pill hides on a screen that is inside a record',
        );
        // Below large the account menu closes the record's bar in the slot
        // the queue's bar gives it, so a reviewer inside a record can read
        // which account they are using and sign out without leaving it
        // (13 section 4.1, polish 3; 05 section 2).
        expect(
          uiMenuTrigger(RegExp('^Account menu')),
          findsOneWidget,
          reason: 'the account menu is not on the record bar below large',
        );
      },
    );

    testWidgets('a record keeps the navigation that sits beside the body', (
      WidgetTester tester,
    ) async {
      await pumpGoldenApp(
        tester,
        window: const Size(1440, 900),
        brightness: Brightness.light,
        location: goldenSpecimenLocation,
      );
      expect(
        navigationShown(tester, UiSidebar),
        isTrue,
        reason:
            'a sidebar is a column beside the body rather than chrome over '
            'it, so it spends width and the budget is a share of the height',
      );
      // The sidebar's footer carries the account at large, so neither bar
      // draws the menu inside a record (`AppShell.accountInBar`).
      expect(
        uiMenuTrigger(RegExp('^Account menu')),
        findsNothing,
        reason: 'the sidebar carries the account, so the bar does not',
      );
    });

    testWidgets('a screen that names the bar through the frame is heard', (
      WidgetTester tester,
    ) async {
      // 13 section 3.4, polish 3: `UiScaffoldSlots.setTitle` and `setLeading`
      // are the one hook a routed screen names the frame's bar through, and
      // `UiTopBar` reads the ask itself through `UiTopBarAsk`, so the shell
      // holds no hook of its own. Published from inside the routed screen,
      // which is where a screen publishes from.
      await pumpAt(tester, 700);
      final BuildContext inside = tester.element(find.byType(QueueScreen));
      final UiScaffoldSlots slots = UiScaffoldSlots.of(inside)!;
      final Object owner = Object();
      const String named = 'Named by the screen';
      List<String?> barLabels() => tester
          .widgetList<UiLabel>(
            find.descendant(
              of: find.byType(UiTopBar),
              matching: find.byType(UiLabel),
            ),
          )
          .map((UiLabel label) => label.text)
          .toList();
      expect(barLabels(), contains(AppShell.markLabel));

      slots.setTitle(named, owner: owner);
      await tester.pump();
      await tester.pump();
      expect(
        barLabels(),
        contains(named),
        reason: 'the ask did not reach the bar the shell built',
      );
      expect(
        barLabels(),
        isNot(contains(AppShell.markLabel)),
        reason: 'what the screen asked for wins over what the route derived',
      );
      expect(
        find.byType(UiSelect<String>),
        findsOneWidget,
        reason: 'naming the bar keeps everything else the shell put on it',
      );

      slots.release(owner);
      await tester.pump();
      await tester.pump();
      expect(barLabels(), contains(AppShell.markLabel));
      expect(barLabels(), isNot(contains(named)));
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('the band is one line on a phone and the full band above it', (
      WidgetTester tester,
    ) async {
      await pumpAt(tester, 390);
      final double strip = tester
          .getSize(find.byType(EnvironmentBanner))
          .height;
      await pumpAt(tester, 768);
      final double full = tester.getSize(find.byType(EnvironmentBanner)).height;
      expect(
        strip,
        lessThanOrEqualTo(UiDensity.hitBox),
        reason:
            '13 section 2.3: at compact the band is one line inside a hit box '
            'that is never shrunk',
      );
      expect(
        full,
        greaterThan(strip),
        reason: 'a window with room keeps the sentence and its control',
      );
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('the navigation returns to a destination it is already in', (
      WidgetTester tester,
    ) async {
      await pumpGoldenApp(
        tester,
        window: const Size(390, 844),
        brightness: Brightness.light,
        location: goldenSourcesLocation,
        repository: GoldenSourceRepository(),
      );
      // Pressing Intake while browsing the sources under it used to do
      // nothing, which left the sources list with no way back but the system
      // gesture. That is half of finding V2-4.
      await tester.tap(
        find
            .descendant(
              of: find.byType(UiPillNav),
              matching: find.bySemanticsLabel(RegExp('Intake')),
            )
            .first,
      );
      await tester.pumpAndSettle();
      expect(find.byType(IntakeManifest), findsOneWidget);
    });
  });
}
