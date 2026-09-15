// Multi-select and bulk decisions in the queue (blueprint 3, "Multi-select";
// pass criteria 5.2, 7.2 and 7.3).
//
// The criterion this closes is not "a checkbox exists". It is that a reviewer
// acting on several records is told exactly how many before anything is
// written, and told exactly which ones changed afterwards. This product has no
// true delete: a decision is recorded on the version it was taken against and
// superseded by a later one, never removed. So the count has to be right, and
// a count that moved under the reviewer while they read it would not be.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_digitization/src/app/routes.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/widgets/widgets.dart';
import 'package:specimen_digitization/src/workspace.dart';

import '../widget_test.dart' show TestRepository, TestSession, fixture;

/// One bulk call, as the repository received it.
typedef BulkCall = ({
  List<String> ids,
  BulkDecisionKind kind,
  String reason,
  String key,
});

/// A queue of records that answers whatever the test set on it, and records
/// every bulk call it is asked to make.
class BulkRepository extends TestRepository {
  BulkRepository(this.records);

  List<Specimen> records;

  /// Null until the test wants a page that is not the last one.
  String? nextCursor;

  final List<BulkCall> calls = <BulkCall>[];

  /// What the server answers. Null means every record changed.
  BulkDecisionReport Function(List<Specimen> sent)? answer;

  /// Set to fail the call itself rather than refuse individual records.
  Object? failure;

  @override
  Future<SpecimenPage> specimenPage(
    CollectionScope scope, {
    Map<String, String> filters = const <String, String>{},
    String? cursor,
  }) async => SpecimenPage(records, nextCursor: nextCursor);

  @override
  Future<List<Specimen>> specimens(
    CollectionScope scope, {
    String query = '',
    String status = '',
  }) async => records;

  @override
  Future<BulkDecisionReport> reviewMany(
    CollectionScope scope,
    List<Specimen> specimens,
    BulkDecisionKind kind,
    String reason,
    String key,
  ) async {
    calls.add((
      ids: specimens.map((Specimen s) => s.id).toList(),
      kind: kind,
      reason: reason,
      key: key,
    ));
    final Object? thrown = failure;
    if (thrown != null) throw thrown;
    return answer?.call(specimens) ??
        BulkDecisionReport(<BulkDecisionResult>[
          for (final Specimen specimen in specimens)
            BulkDecisionResult(
              specimenId: specimen.id,
              outcome: BulkOutcome.applied,
              revision: specimen.revision + 1,
            ),
        ]);
  }
}

/// Records built from the shared fixture, so they carry everything a row draws
/// and everything a bulk call has to send.
List<Specimen> queue(int count) => <Specimen>[
  for (int i = 1; i <= count; i++)
    Specimen(<String, dynamic>{
      ...fixture.data,
      'specimen_id': 'fixture-00$i',
      'display_name': 'Pinned beetle $i',
      'revision': 3,
      'record_version_id': 'run-00$i:3',
    }),
];

/// Wide enough for the checkbox column, narrow enough to stay a single pane.
const Size wideQueue = Size(800, 1400);

/// A phone: the column is revealed on a long press rather than kept open.
const Size narrowQueue = Size(390, 1200);

Future<void> pumpQueue(
  WidgetTester tester,
  BulkRepository repository, {
  Size window = wideQueue,
}) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = window;
  addTearDown(tester.view.reset);
  final TestSession session = TestSession();
  addTearDown(session.controller.close);
  await tester.pumpWidget(
    SpecimenDigitizationApp(
      session: session,
      repository: repository,
      initialLocation: AppRoutes.queueOf(encodeCollectionKey('org/insects')),
    ),
  );
  await tester.pumpAndSettle();
}

/// Picks the row whose record is named [title].
Future<void> pick(WidgetTester tester, String title) async {
  final Finder row = find.ancestor(
    of: find.text(title),
    matching: find.byType(SelectableRow),
  );
  await tester.tap(find.descendant(of: row, matching: find.byType(Checkbox)));
  await tester.pumpAndSettle();
}

/// Types [reason] into the confirmation and takes the action named [action].
Future<void> confirm(
  WidgetTester tester,
  String action, {
  String reason = 'Reviewed together at the copy stand',
}) async {
  await tester.enterText(find.byType(TextField).last, reason);
  await tester.pumpAndSettle();
  await tester.tap(find.widgetWithText(FilledButton, action));
  await tester.pumpAndSettle();
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  group('picking records', () {
    testWidgets('a wide window keeps the checkbox column open', (
      WidgetTester tester,
    ) async {
      await pumpQueue(tester, BulkRepository(queue(4)));
      expect(find.byType(Checkbox), findsNWidgets(4));
      expect(
        find.textContaining('selected'),
        findsNothing,
        reason: 'an empty selection has no bar',
      );
    });

    testWidgets('a narrow window reveals the column on a long press', (
      WidgetTester tester,
    ) async {
      await pumpQueue(
        tester,
        BulkRepository(queue(3)),
        window: narrowQueue,
      );
      expect(find.byType(Checkbox), findsNothing);
      await tester.longPress(find.text('Pinned beetle 2'));
      await tester.pumpAndSettle();
      expect(find.byType(Checkbox), findsNWidgets(3));
      expect(find.text('1 record selected'), findsOneWidget);
    });

    testWidgets('the count is on screen from the first pick', (
      WidgetTester tester,
    ) async {
      await pumpQueue(tester, BulkRepository(queue(4)));
      await pick(tester, 'Pinned beetle 1');
      expect(find.text('1 record selected'), findsOneWidget);
      await pick(tester, 'Pinned beetle 3');
      expect(find.text('2 records selected'), findsOneWidget);
    });

    testWidgets('select all reaches the loaded page and says so', (
      WidgetTester tester,
    ) async {
      final BulkRepository repository = BulkRepository(queue(5))
        ..nextCursor = 'page-2';
      await pumpQueue(tester, repository);
      await pick(tester, 'Pinned beetle 1');
      await tester.tap(find.text(SelectionBar.selectAllLabel));
      await tester.pumpAndSettle();
      expect(find.text('5 records selected'), findsOneWidget);
      expect(
        find.text(SelectionBar.recordsMoreMatch),
        findsOneWidget,
        reason: 'the server still has a page, so the reach has to be named',
      );
    });

    testWidgets('escape leaves the selection', (WidgetTester tester) async {
      await pumpQueue(tester, BulkRepository(queue(3)));
      await pick(tester, 'Pinned beetle 1');
      expect(find.text('1 record selected'), findsOneWidget);
      await tester.sendKeyEvent(LogicalKeyboardKey.escape);
      await tester.pumpAndSettle();
      expect(find.textContaining('selected'), findsNothing);
    });

    testWidgets('opening a record still works while a selection is live', (
      WidgetTester tester,
    ) async {
      await pumpQueue(tester, BulkRepository(queue(3)));
      await pick(tester, 'Pinned beetle 1');
      await tester.tap(find.text('Pinned beetle 2'));
      await tester.pumpAndSettle();
      expect(
        find.byType(QueueRow),
        findsNothing,
        reason: 'the row body opens the record, it does not select it',
      );
    });
  });

  group('the confirmation', () {
    testWidgets('names the exact count before anything is written', (
      WidgetTester tester,
    ) async {
      final BulkRepository repository = BulkRepository(queue(5));
      await pumpQueue(tester, repository);
      await pick(tester, 'Pinned beetle 1');
      await pick(tester, 'Pinned beetle 2');
      await pick(tester, 'Pinned beetle 4');
      await tester.tap(find.text('Approve'));
      await tester.pumpAndSettle();
      expect(find.text('Approve 3 records?'), findsOneWidget);
      expect(
        find.widgetWithText(FilledButton, 'Approve 3 records'),
        findsOneWidget,
      );
      expect(
        repository.calls,
        isEmpty,
        reason: 'the count is stated before the call, not after it',
      );
    });

    testWidgets('says the decision cannot be taken back', (
      WidgetTester tester,
    ) async {
      await pumpQueue(tester, BulkRepository(queue(2)));
      await pick(tester, 'Pinned beetle 1');
      await tester.tap(find.text('Approve'));
      await tester.pumpAndSettle();
      expect(find.text(ReasonForm.finality), findsOneWidget);
      expect(find.textContaining('Nothing is removed'), findsOneWidget);
    });

    testWidgets('will not commit without a reason', (
      WidgetTester tester,
    ) async {
      final BulkRepository repository = BulkRepository(queue(2));
      await pumpQueue(tester, repository);
      await pick(tester, 'Pinned beetle 1');
      await tester.tap(find.text('Approve'));
      await tester.pumpAndSettle();
      expect(
        tester
            .widget<FilledButton>(
              find.widgetWithText(FilledButton, 'Approve 1 record'),
            )
            .onPressed,
        isNull,
      );
      expect(repository.calls, isEmpty);
    });

    testWidgets('backing out writes nothing and keeps the selection', (
      WidgetTester tester,
    ) async {
      final BulkRepository repository = BulkRepository(queue(3));
      await pumpQueue(tester, repository);
      await pick(tester, 'Pinned beetle 1');
      await pick(tester, 'Pinned beetle 2');
      await tester.tap(find.text('Approve'));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(TextButton, 'Cancel'));
      await tester.pumpAndSettle();
      expect(repository.calls, isEmpty);
      expect(find.text('2 records selected'), findsOneWidget);
    });

    testWidgets('coverage names the count too', (WidgetTester tester) async {
      await pumpQueue(tester, BulkRepository(queue(3)));
      await pick(tester, 'Pinned beetle 1');
      await pick(tester, 'Pinned beetle 3');
      await tester.tap(find.text('Confirm coverage'));
      await tester.pumpAndSettle();
      expect(
        find.text('Confirm label coverage on 2 records?'),
        findsOneWidget,
      );
    });
  });

  group('the call', () {
    testWidgets('is one call carrying every selected record', (
      WidgetTester tester,
    ) async {
      final BulkRepository repository = BulkRepository(queue(5));
      await pumpQueue(tester, repository);
      await pick(tester, 'Pinned beetle 1');
      await pick(tester, 'Pinned beetle 3');
      await pick(tester, 'Pinned beetle 5');
      await tester.tap(find.text('Approve'));
      await tester.pumpAndSettle();
      await confirm(tester, 'Approve 3 records');
      expect(repository.calls, hasLength(1));
      expect(repository.calls.single.ids, <String>[
        'fixture-001',
        'fixture-003',
        'fixture-005',
      ]);
      expect(repository.calls.single.kind, BulkDecisionKind.approve);
      expect(
        repository.calls.single.reason,
        'Reviewed together at the copy stand',
      );
      expect(repository.calls.single.key, isNotEmpty);
    });

    testWidgets('a batch that landed whole clears and says so', (
      WidgetTester tester,
    ) async {
      await pumpQueue(tester, BulkRepository(queue(3)));
      await pick(tester, 'Pinned beetle 1');
      await pick(tester, 'Pinned beetle 2');
      await tester.tap(find.text('Approve'));
      await tester.pumpAndSettle();
      await confirm(tester, 'Approve 2 records');
      expect(find.text('2 records approved.'), findsOneWidget);
      expect(find.textContaining('selected'), findsNothing);
    });

    testWidgets('a batch that half worked names what did not change', (
      WidgetTester tester,
    ) async {
      final BulkRepository repository = BulkRepository(queue(3));
      repository.answer = (List<Specimen> sent) =>
          BulkDecisionReport(<BulkDecisionResult>[
            BulkDecisionResult(
              specimenId: sent[0].id,
              outcome: BulkOutcome.applied,
              revision: 4,
            ),
            BulkDecisionResult(
              specimenId: sent[1].id,
              outcome: BulkOutcome.refused,
              code: 'revision_or_idempotency_conflict',
              message: 'Wrong base record version',
            ),
            BulkDecisionResult(
              specimenId: sent[2].id,
              outcome: BulkOutcome.skipped,
            ),
          ]);
      await pumpQueue(tester, repository);
      await pick(tester, 'Pinned beetle 1');
      await pick(tester, 'Pinned beetle 2');
      await pick(tester, 'Pinned beetle 3');
      await tester.tap(find.text('Approve'));
      await tester.pumpAndSettle();
      await confirm(tester, 'Approve 3 records');

      expect(find.text('1 of 3 records changed'), findsOneWidget);
      expect(find.text('Pinned beetle 2'), findsWidgets);
      expect(find.text('Wrong base record version'), findsOneWidget);
      expect(find.text(BulkOutcomeReport.skippedReason), findsOneWidget);
      expect(
        find.textContaining('records approved.'),
        findsNothing,
        reason: 'a partial result is not something to announce and dismiss',
      );
    });

    testWidgets('a call that did not complete keeps the selection', (
      WidgetTester tester,
    ) async {
      final BulkRepository repository = BulkRepository(queue(3))
        ..failure = const ApiFailure('The server is unreachable.');
      await pumpQueue(tester, repository);
      await pick(tester, 'Pinned beetle 1');
      await pick(tester, 'Pinned beetle 2');
      await tester.tap(find.text('Approve'));
      await tester.pumpAndSettle();
      await confirm(tester, 'Approve 2 records');
      expect(
        find.text('2 records selected'),
        findsOneWidget,
        reason: "the reviewer's work is still on screen to try again",
      );
    });

    testWidgets('the same selection retried carries the same key', (
      WidgetTester tester,
    ) async {
      final BulkRepository repository = BulkRepository(queue(3))
        ..failure = const ApiFailure('The server is unreachable.');
      await pumpQueue(tester, repository);
      await pick(tester, 'Pinned beetle 1');
      await tester.tap(find.text('Approve'));
      await tester.pumpAndSettle();
      await confirm(tester, 'Approve 1 record');
      await tester.tap(find.text('Approve'));
      await tester.pumpAndSettle();
      await confirm(tester, 'Approve 1 record');
      expect(repository.calls, hasLength(2));
      expect(
        repository.calls[0].key,
        repository.calls[1].key,
        reason: 'an uncertain answer retried under a new key records the '
            'decision twice',
      );
    });
  });

  group('the count does not move under the reviewer', () {
    testWidgets('a poll that answers is deferred while a selection is live', (
      WidgetTester tester,
    ) async {
      final BulkRepository repository = BulkRepository(queue(4));
      await pumpQueue(tester, repository);
      await pick(tester, 'Pinned beetle 1');
      await tester.tap(find.text(SelectionBar.selectAllLabel));
      await tester.pumpAndSettle();
      expect(find.text('4 records selected'), findsOneWidget);

      // Two of the four are cleared by another reviewer and drop out of the
      // filter. The poll answers, and the list does not move.
      repository.records = queue(4).sublist(0, 2);
      await tester.pump(const Duration(seconds: 21));
      await tester.pumpAndSettle();
      expect(
        find.text('4 records selected'),
        findsOneWidget,
        reason: 'the count a reviewer is about to confirm must not change '
            'between reading it and confirming it',
      );
    });
  });
}
