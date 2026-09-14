// How many times the client asks the server for the same thing
// (smoke test defect 6).
//
// A screen entry is one question. A reviewer signing in should produce one
// specimen page request, not a handful: every extra one is a round trip the
// reviewer waits for, a row of noise in the server's logs, and, on a
// collection large enough to matter, real money.
//
// Counting is the only honest way to hold this: the screen looks identical
// whether it asked once or seven times.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_digitization/src/app/routes.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/workspace.dart';

import '../widget_test.dart' show TestRepository, TestSession;

/// A repository that counts what it is asked for.
class CountingRepository extends TestRepository {
  /// One entry per specimen page request, in order.
  final List<Map<String, String>> pages = <Map<String, String>>[];

  /// One entry per collection list request.
  int scopeRequests = 0;

  @override
  Future<List<CollectionScope>> scopes() {
    scopeRequests++;
    return super.scopes();
  }

  @override
  Future<SpecimenPage> specimenPage(
    CollectionScope scope, {
    Map<String, String> filters = const <String, String>{},
    String? cursor,
  }) {
    pages.add(Map<String, String>.from(filters));
    return super.specimenPage(scope, filters: filters, cursor: cursor);
  }
}

void main() {
  testWidgets('landing on the queue asks for one page, not seven', (
    WidgetTester tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(800, 1400);
    addTearDown(tester.view.reset);

    final CountingRepository repository = CountingRepository();
    final TestSession session = TestSession();
    addTearDown(session.controller.close);

    await tester.pumpWidget(
      SpecimenDigitizationApp(
        session: session,
        repository: repository,
        initialLocation: AppRoutes.setup,
      ),
    );
    await tester.pumpAndSettle();

    expect(
      repository.scopeRequests,
      1,
      reason: 'the collection list was asked for more than once',
    );
    expect(
      repository.pages.length,
      1,
      reason:
          'the queue asked for ${repository.pages.length} pages on one screen '
          'entry: ${repository.pages}',
    );

    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('opening a record adds no page request', (
    WidgetTester tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(800, 1400);
    addTearDown(tester.view.reset);

    final CountingRepository repository = CountingRepository();
    final TestSession session = TestSession();
    addTearDown(session.controller.close);

    await tester.pumpWidget(
      SpecimenDigitizationApp(session: session, repository: repository),
    );
    await tester.pumpAndSettle();
    final int afterLanding = repository.pages.length;

    await tester.scrollUntilVisible(
      find.text('Synthetic insect label'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.text('Synthetic insect label'));
    await tester.pumpAndSettle();

    // The record is already in the page the queue holds. Opening it is a
    // selection, not a new question for the server.
    expect(repository.pages.length, afterLanding);

    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a window in the background stops polling', (
    WidgetTester tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(800, 1400);
    addTearDown(tester.view.reset);

    final CountingRepository repository = CountingRepository();
    final TestSession session = TestSession();
    addTearDown(session.controller.close);
    final WorkspaceController controller = WorkspaceController(
      repository: repository,
      session: session,
    );
    controller.start();
    await tester.pumpAndSettle();
    final int afterStart = repository.pages.length;

    // In the foreground the quiet poll answers on its own schedule.
    await tester.pump(queuePollInterval);
    await tester.pumpAndSettle();
    expect(repository.pages.length, afterStart + 1);

    // In the background it asks nothing: a poll nobody is reading is a
    // request the collection pays for and no one sees.
    controller.setForeground(false);
    await tester.pump(queuePollInterval);
    await tester.pump(queuePollInterval);
    await tester.pumpAndSettle();
    expect(repository.pages.length, afterStart + 1);

    controller.setForeground(true);
    await tester.pump(queuePollInterval);
    await tester.pumpAndSettle();
    expect(repository.pages.length, afterStart + 2);

    // Disposed inside the body, not in a tear down: the binding checks for a
    // pending timer before tear downs run.
    controller.dispose();
  });

  testWidgets('changing the segment asks exactly once more', (
    WidgetTester tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(800, 1400);
    addTearDown(tester.view.reset);

    final CountingRepository repository = CountingRepository();
    final TestSession session = TestSession();
    addTearDown(session.controller.close);

    await tester.pumpWidget(
      SpecimenDigitizationApp(session: session, repository: repository),
    );
    await tester.pumpAndSettle();
    final int afterLanding = repository.pages.length;

    await tester.tap(find.text('Cleared'));
    await tester.pumpAndSettle();

    expect(repository.pages.length, afterLanding + 1);
    expect(repository.pages.last['disposition'], isNotNull);

    await tester.pumpWidget(const SizedBox());
  });
}
