// Routing (screen blueprints, section 1.1; responsive, section 6).
//
// Every screen is a location, system and browser back return to the queue from
// a record, and a link to a record opens that record.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_digitization/src/app/routes.dart';
import 'package:specimen_digitization/src/screens/queue/queue_screen.dart';
import 'package:specimen_digitization/src/screens/queue/workbench_screen.dart';
import 'package:specimen_digitization/src/workspace.dart';

import '../widget_test.dart' show TestRepository, TestSession;
import '../ui_finders.dart';

/// The collection the fixture repository publishes.
const String fixtureCollection = 'org/insects';

/// The window every routing test runs in: one pane, so a record is a push.
const Size routingWindow = Size(800, 1400);

String locationOf(WidgetTester tester) => GoRouter.of(
  tester.element(find.byType(Navigator).first),
).routerDelegate.currentConfiguration.uri.toString();

/// The system back gesture, as the platform sends it.
Future<void> systemBack(WidgetTester tester) async {
  await tester.binding.defaultBinaryMessenger.handlePlatformMessage(
    'flutter/navigation',
    const JSONMethodCodec().encodeMethodCall(const MethodCall('popRoute')),
    (_) {},
  );
  await tester.pumpAndSettle();
}

Future<TestSession> pumpApp(
  WidgetTester tester, {
  String initialLocation = AppRoutes.setup,
  Size window = routingWindow,
  List<NavigatorObserver> observers = const <NavigatorObserver>[],
}) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = window;
  addTearDown(tester.view.reset);
  final TestSession session = TestSession();
  addTearDown(session.controller.close);
  await tester.pumpWidget(
    SpecimenDigitizationApp(
      session: session,
      repository: TestRepository(),
      initialLocation: initialLocation,
      navigatorObservers: observers,
    ),
  );
  await tester.pumpAndSettle();
  return session;
}

void main() {
  testWidgets('Help and shortcuts opens, and closes back to the queue', (
    tester,
  ) async {
    // The redirect used to read a collection out of every location and send
    // anything without one home, so the help control opened a route that
    // immediately closed itself.
    await pumpApp(tester);
    final String before = locationOf(tester);
    expect(find.text('Keyboard shortcuts'), findsNothing);

    // Help lives in the account menu on every window narrower than large
    // (07 section 10: a help control in the app bar's overflow).
    await tester.tap(uiMenuTrigger(RegExp('^Account menu')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Help and shortcuts'));
    await tester.pumpAndSettle();
    // The panel is on screen and stays there. Before the redirect learned
    // that a route without a collection is not a route with a missing one,
    // this pushed /help and was sent straight back to the queue.
    expect(find.text('Keyboard shortcuts'), findsOneWidget);
    expect(find.text('Glossary'), findsOneWidget);

    await systemBack(tester);
    expect(find.text('Keyboard shortcuts'), findsNothing);
    expect(locationOf(tester), before);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a deep link to help is honoured rather than bounced', (
    tester,
  ) async {
    await pumpApp(tester, initialLocation: AppRoutes.help);
    expect(locationOf(tester), AppRoutes.help);
    expect(find.text('Glossary'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a signed in window lands on its collection queue', (
    tester,
  ) async {
    await pumpApp(tester);
    expect(
      locationOf(tester),
      AppRoutes.queueOf(encodeCollectionKey(fixtureCollection)),
    );
    expect(find.byType(QueuePane), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('opening a record changes the location, and back returns', (
    tester,
  ) async {
    await pumpApp(tester);
    await tester.scrollUntilVisible(
      find.text('Synthetic insect label'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.text('Synthetic insect label'));
    await tester.pumpAndSettle();
    expect(find.byType(WorkbenchScreen), findsOneWidget);
    expect(locationOf(tester), endsWith('/queue/fixture-001'));

    await systemBack(tester);
    expect(find.byType(WorkbenchScreen), findsNothing);
    expect(find.byType(QueuePane), findsOneWidget);
    expect(locationOf(tester), endsWith('/queue'));
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('the back control returns to the queue as well', (tester) async {
    await pumpApp(
      tester,
      initialLocation: AppRoutes.specimenOf(
        encodeCollectionKey(fixtureCollection),
        'fixture-001',
      ),
    );
    expect(find.byType(WorkbenchScreen), findsOneWidget);
    await tester.tap(find.text('Back to queue'));
    await tester.pumpAndSettle();
    expect(locationOf(tester), endsWith('/queue'));
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a link to a record opens that record', (tester) async {
    await pumpApp(
      tester,
      initialLocation: AppRoutes.specimenOf(
        encodeCollectionKey(fixtureCollection),
        'fixture-001',
      ),
    );
    expect(find.byType(WorkbenchScreen), findsOneWidget);
    expect(locationOf(tester), contains('fixture-001'));
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a link to a collection this account cannot open falls back', (
    tester,
  ) async {
    await pumpApp(
      tester,
      initialLocation: AppRoutes.queueOf(encodeCollectionKey('org/plants')),
    );
    expect(
      locationOf(tester),
      AppRoutes.queueOf(encodeCollectionKey(fixtureCollection)),
    );
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('the intake destination is its own location', (tester) async {
    await pumpApp(tester);
    await tester.tap(uiDestination('Intake'));
    await tester.pumpAndSettle();
    expect(locationOf(tester), endsWith('/intake'));
    await tester.pumpWidget(const SizedBox());
  });
}
