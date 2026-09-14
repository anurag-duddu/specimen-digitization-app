// The adaptive shell at each window class
// (responsive and platform adaptation, section 2).
//
// One navigation component per class, and never two at once: a bottom bar
// below 600, a collapsed rail to 839, an extended rail to 1199, and a
// permanent drawer at 1200 and above.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/queue/queue_screen.dart';

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

void main() {
  testWidgets('compact windows carry a bottom navigation bar', (tester) async {
    await pumpAt(tester, 400);
    expect(find.byType(NavigationBar), findsOneWidget);
    expect(find.byType(NavigationRail), findsNothing);
    expect(find.byType(NavigationDrawer), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('medium windows carry a collapsed rail', (tester) async {
    await pumpAt(tester, 700);
    expect(find.byType(NavigationBar), findsNothing);
    expect(find.byType(NavigationDrawer), findsNothing);
    final NavigationRail rail = tester.widget<NavigationRail>(
      find.byType(NavigationRail),
    );
    expect(rail.extended, isFalse);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('expanded windows carry an extended rail', (tester) async {
    await pumpAt(tester, 900);
    expect(find.byType(NavigationBar), findsNothing);
    expect(find.byType(NavigationDrawer), findsNothing);
    final NavigationRail rail = tester.widget<NavigationRail>(
      find.byType(NavigationRail),
    );
    expect(rail.extended, isTrue);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('large windows carry a permanent drawer and a list pane', (
    tester,
  ) async {
    await pumpAt(tester, 1300);
    expect(find.byType(NavigationDrawer), findsOneWidget);
    expect(find.byType(NavigationBar), findsNothing);
    expect(find.byType(NavigationRail), findsNothing);
    // List detail: the queue keeps its own pane beside the detail half.
    expect(find.byType(QueuePane), findsOneWidget);
    expect(find.text('No record open'), findsOneWidget);
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
