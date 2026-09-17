// A deep link to a record must not cancel the queue load, and the list pane
// must never claim a collection is empty while it is still being asked for.
//
// Finding V-5 in design/08-verification-report.md. One generation counter
// guarded two independent loads: the router mounted the workbench, its
// `openSpecimen` bumped the counter while `refresh` was still awaiting its
// page, and `refresh` then discarded the page it had already been given. The
// pane rendered "No specimens yet" about a collection with records.
//
// The page is held open by a completer here rather than by a delay, so the
// assertion is about the state the reviewer actually sees mid-flight, not
// about how long a fake clock ran.

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/widgets/widgets.dart';
import 'package:specimen_digitization/src/workspace.dart';

import '../golden/golden_harness.dart';
import '../widget_test.dart' show TestSession;

/// A repository whose queue page does not answer until it is let go.
class HeldPageRepository extends GoldenRepository {
  HeldPageRepository() : super.verified();

  /// Completed by the test when the page should arrive.
  final Completer<void> gate = Completer<void>();

  /// How many pages were asked for, so a fix cannot pay for itself with an
  /// extra round trip.
  int pageRequests = 0;

  @override
  Future<SpecimenPage> specimenPage(
    CollectionScope scope, {
    Map<String, String> filters = const <String, String>{},
    String? cursor,
  }) async {
    pageRequests++;
    await gate.future;
    return SpecimenPage(<Specimen>[record]);
  }
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  testWidgets(
    'a deep link to a record leaves the queue pane loading, not empty',
    (WidgetTester tester) async {
      tester.view.devicePixelRatio = 1;
      // A large window, where the list and the record are on screen together
      // and the defect was visible.
      tester.view.physicalSize = const Size(1440, 900);
      addTearDown(tester.view.reset);

      final HeldPageRepository repository = HeldPageRepository();
      final TestSession session = TestSession();
      addTearDown(session.controller.close);

      await tester.pumpWidget(
        SpecimenDigitizationApp(
          session: session,
          repository: repository,
          initialLocation: goldenSpecimenLocation,
          motionPreferences: MemoryMotionPreferenceStore(),
        ),
      );
      // Frames enough for the router to mount the workbench and for its
      // `openSpecimen` microtask to run, while the page is still out.
      for (int i = 0; i < 6; i++) {
        await tester.pump(const Duration(milliseconds: 16));
      }

      expect(
        find.text('No specimens yet'),
        findsNothing,
        reason:
            'the pane claimed the collection was empty while it was loading',
      );
      expect(
        find.byType(UiSkeleton),
        findsWidgets,
        reason: 'a list that has never been answered shows placeholders',
      );

      repository.gate.complete();
      await tester.pumpAndSettle();

      expect(find.byType(QueueRow), findsOneWidget);
      expect(find.text('No specimens yet'), findsNothing);
      expect(
        repository.pageRequests,
        1,
        reason:
            'the fix must not turn one page request into two '
            '(test/app/request_budget_test.dart)',
      );
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets('the record and the list load on separate counters', (
    WidgetTester tester,
  ) async {
    // The unit of the same finding: opening a record while a list load is
    // outstanding must not cancel it.
    final HeldPageRepository repository = HeldPageRepository();
    final TestSession session = TestSession();
    addTearDown(session.controller.close);
    final WorkspaceController controller = WorkspaceController(
      repository: repository,
      session: session,
    );

    controller.start();
    await tester.pump();
    // The collection list has been answered and the page is outstanding.
    unawaited(controller.openSpecimen(goldenSpecimenId));
    await tester.pump();
    repository.gate.complete();
    await tester.pump();
    await tester.pump();

    expect(
      controller.items,
      isNotEmpty,
      reason: 'opening a record discarded the page the list already had',
    );
    expect(controller.listAnswered, isTrue);
    expect(controller.selected, isNotNull);
    controller.dispose();
  });
}
