// The approved shell uses native phone tabs and a global desktop icon rail.
// Collection selection and specimen rows share one sidebar on larger windows.
import 'package:flutter/material.dart' show NavigationBar;
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_digitization/src/app/shell.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/intake.dart';
import 'package:specimen_digitization/src/screens/queue/queue_screen.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../golden/golden_harness.dart';
import '../ui_finders.dart';
import '../widget_test.dart' show TestRepository, TestSession;

class EmptyRepository extends TestRepository {
  @override
  Future<SpecimenPage> specimenPage(
    CollectionScope scope, {
    Map<String, String> filters = const {},
    String? cursor,
  }) async => const SpecimenPage(<Specimen>[]);
}

Future<void> pumpAt(WidgetTester tester, double width) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = Size(width, 1000);
  addTearDown(tester.view.reset);
  final session = TestSession();
  addTearDown(session.controller.close);
  await tester.pumpWidget(
    SpecimenDigitizationApp(session: session, repository: EmptyRepository()),
  );
  await tester.pumpAndSettle();
}

void main() {
  for (final width in [400.0, 700.0, 900.0, 1300.0]) {
    testWidgets('one global navigation surface at width $width', (
      tester,
    ) async {
      await pumpAt(tester, width);
      final mobile = width < 768;
      expect(
        find.byKey(const ValueKey('mobile-navigation')),
        mobile ? findsOneWidget : findsNothing,
      );
      expect(
        find.byType(NavigationBar),
        mobile ? findsOneWidget : findsNothing,
      );
      expect(
        find.byKey(const ValueKey('global-rail')),
        mobile ? findsNothing : findsOneWidget,
      );
      expect(find.byType(UiPillNav), findsNothing);
      expect(find.byType(UiRail), findsNothing);
      expect(find.byType(UiSidebar), findsNothing);
      expect(uiDestination('Specimens'), findsOneWidget);
      expect(uiDestination('Intake'), findsOneWidget);
      expect(find.byType(QueuePane), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('collection and account remain reachable at width $width', (
      tester,
    ) async {
      await pumpAt(tester, width);
      final switcher = find.bySemanticsLabel(RegExp('^Authorized collection,'));
      expect(switcher, findsOneWidget);
      expect(switcher.hitTestable(), findsOneWidget);
      expect(uiMenuTrigger(RegExp('^Account menu')), findsOneWidget);
      await tester.tap(uiMenuTrigger(RegExp('^Account menu')));
      await tester.pumpAndSettle();
      expect(find.text(AppShell.helpLabel), findsOneWidget);
      expect(find.text(AppShell.reloadLabel), findsOneWidget);
      expect(find.text('Sign out'), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    });
  }

  testWidgets(
    'large windows group the collection and specimen list beside the content',
    (tester) async {
      await pumpAt(tester, 1300);
      final sidebar = find.byKey(const ValueKey('global-sidebar'));
      expect(sidebar, findsOneWidget);
      expect(
        find.descendant(of: sidebar, matching: find.byType(QueuePane)),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: sidebar,
          matching: find.bySemanticsLabel(RegExp('^Authorized collection,')),
        ),
        findsOneWidget,
      );
      expect(find.text('No record open'), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets(
    'environment context is available without a repeated full-width banner',
    (tester) async {
      await pumpAt(tester, 400);
      await tester.tap(find.bySemanticsLabel('Test environment'));
      await tester.pumpAndSettle();
      expect(find.textContaining('Test environment'), findsWidgets);
      expect(find.textContaining('Synthetic'), findsWidgets);
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets('a phone record retains native navigation and a way back', (
    tester,
  ) async {
    await pumpGoldenApp(
      tester,
      window: const Size(390, 844),
      brightness: Brightness.light,
      location: goldenSpecimenLocation,
    );
    expect(find.byKey(const ValueKey('mobile-navigation')), findsOneWidget);
    expect(find.byKey(const ValueKey('global-sidebar')), findsNothing);
    expect(uiIconButton(AppShell.backLabel), findsOneWidget);
    expect(find.text(goldenVerifiedSpecimen().displayReference), findsWidgets);
    expect(
      find.bySemanticsLabel(RegExp('^Authorized collection,')),
      findsNothing,
    );
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets(
    'a desktop record retains global actions and can collapse its specimen list',
    (tester) async {
      await pumpGoldenApp(
        tester,
        window: const Size(1440, 900),
        brightness: Brightness.light,
        location: goldenSpecimenLocation,
      );
      expect(find.byKey(const ValueKey('global-rail')), findsOneWidget);
      expect(uiMenuTrigger(RegExp('^Account menu')), findsOneWidget);
      expect(find.byKey(const ValueKey('global-sidebar')), findsOneWidget);
      await tester.tap(uiIconButton('Close sidebar'));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('global-sidebar')), findsNothing);
      expect(uiIconButton('Open sidebar'), findsOneWidget);
      await tester.tap(uiIconButton('Open sidebar'));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('global-sidebar')), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets(
    'native Intake navigation returns from sources to the intake root',
    (tester) async {
      await pumpGoldenApp(
        tester,
        window: const Size(390, 844),
        brightness: Brightness.light,
        location: goldenSourcesLocation,
        repository: GoldenSourceRepository(),
      );
      await tester.tap(uiDestination('Intake'));
      await tester.pumpAndSettle();
      expect(find.byType(IntakeScreen), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    },
  );
}
