// The main queue follows the server without a restart: a return to the app
// asks at once, a paginated queue still learns what arrived, changed or left,
// and a poll that cannot reach the service retries quietly and reports the
// outage once.

import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/workspace.dart';

import 'widget_test.dart' show TestRepository, TestSession;

Specimen row(
  String id, {
  int revision = 1,
  String disposition = 'needs_human_review',
}) => Specimen(<String, dynamic>{
  'specimen_id': id,
  'revision': revision,
  'disposition': disposition,
});

/// Answers the queue the way the server does: oldest first, a fixed page
/// size, and a cursor after a full page.
class KeysetRepository extends TestRepository {
  KeysetRepository(this.server);

  List<Specimen> server;
  int pageReads = 0;
  int failures = 0;
  final Map<String, Completer<void>> gates = <String, Completer<void>>{};
  static const int pageSize = 2;

  @override
  Future<SpecimenPage> specimenPage(
    CollectionScope scope, {
    Map<String, String> filters = const <String, String>{},
    String? cursor,
  }) async {
    pageReads++;
    if (failures > 0) {
      failures--;
      throw const ApiFailure(
        'The service could not be reached.',
        code: 'network',
      );
    }
    // The answer is the server as it stood when asked; a gate delays only
    // its arrival, like a slow network.
    final Completer<void>? gate = gates.remove(cursor ?? '');
    final String? disposition = filters['disposition'];
    final List<Specimen> matching = server
        .where(
          (Specimen s) => disposition == null || s.disposition == disposition,
        )
        .toList();
    final int start = cursor == null
        ? 0
        : matching.indexWhere((Specimen s) => 'after:${s.id}' == cursor) + 1;
    final List<Specimen> page = matching.skip(start).take(pageSize).toList();
    if (gate != null) await gate.future;
    return SpecimenPage(
      page,
      nextCursor: page.length == pageSize ? 'after:${page.last.id}' : null,
    );
  }

  /// Holds the next open-record read until completed.
  Completer<void>? detailGate;

  /// Holds the next review save until completed with the saved record.
  Completer<Specimen>? heldReview;

  @override
  Future<Specimen> review(
    CollectionScope scope,
    Specimen specimen,
    Json change,
    String key,
  ) async => heldReview!.future;

  @override
  Future<Specimen> specimen(CollectionScope scope, String id) async {
    final Completer<void>? gate = detailGate;
    detailGate = null;
    if (gate != null) await gate.future;
    return server.firstWhere((Specimen s) => s.id == id);
  }
}

Future<WorkspaceController> started(
  WidgetTester tester,
  KeysetRepository repository,
  TestSession session,
) async {
  final WorkspaceController controller = WorkspaceController(
    repository: repository,
    session: session,
  );
  controller.start();
  await tester.pumpAndSettle();
  return controller;
}

/// Walks the lifecycle one legal step at a time, as the platform reports it.
void move(WidgetTester tester, List<AppLifecycleState> states) {
  for (final AppLifecycleState state in states) {
    tester.binding.handleAppLifecycleStateChanged(state);
  }
}

List<String> ids(WorkspaceController controller) =>
    controller.items.map((Specimen s) => s.id).toList();

void main() {
  testWidgets('returning to the app refreshes the queue at once', (
    WidgetTester tester,
  ) async {
    final KeysetRepository repository = KeysetRepository(<Specimen>[row('a')]);
    final TestSession session = TestSession();
    final WorkspaceController controller = await started(
      tester,
      repository,
      session,
    );
    try {
      expect(ids(controller), <String>['a']);
      await tester.pump(const Duration(seconds: 15));
      move(tester, <AppLifecycleState>[
        AppLifecycleState.inactive,
        AppLifecycleState.hidden,
        AppLifecycleState.paused,
      ]);
      await tester.pump();
      expect(controller.foreground, isFalse);
      // Another device sends a photograph to the main queue meanwhile.
      repository.server = <Specimen>[row('a'), row('b')];
      final int beforeResume = repository.pageReads;

      move(tester, <AppLifecycleState>[
        AppLifecycleState.hidden,
        AppLifecycleState.inactive,
        AppLifecycleState.resumed,
      ]);
      await tester.pump();
      await tester.pump();

      expect(repository.pageReads, beforeResume + 1);
      expect(ids(controller), <String>['a', 'b']);
      // The timer restarts on return, so the tick that was due five seconds
      // later does not ask the same question again.
      await tester.pump(const Duration(seconds: 10));
      expect(repository.pageReads, beforeResume + 1);
      await tester.pump(const Duration(seconds: 10));
      expect(repository.pageReads, beforeResume + 2);
    } finally {
      controller.dispose();
      await session.controller.close();
    }
  });

  testWidgets(
    'a paginated queue learns what arrived, changed or left and keeps its pages',
    (WidgetTester tester) async {
      final KeysetRepository repository = KeysetRepository(<Specimen>[
        row('a'),
        row('b'),
        row('c'),
      ]);
      final TestSession session = TestSession();
      final WorkspaceController controller = await started(
        tester,
        repository,
        session,
      );
      try {
        await controller.loadMore();
        await controller.openSpecimen('c');
        expect(ids(controller), <String>['a', 'b', 'c']);
        expect(controller.nextCursor, isNull);

        repository.server = <Specimen>[
          row('a', revision: 2, disposition: 'cleared'),
          row('b', revision: 2),
          row('c'),
          row('d'),
        ];
        await tester.pump(queuePollInterval);
        await tester.pumpAndSettle();

        expect(ids(controller), <String>['b', 'c', 'd']);
        expect(controller.items.first.revision, 2);
        expect(controller.nextCursor, isNull);
        expect(controller.selectedId, 'c');
        expect(controller.error, isNull);

        // The reread kept the loaded depth, so Load more continues from the
        // reread's own cursor.
        repository.server = <Specimen>[
          ...repository.server,
          row('e'),
          row('f'),
        ];
        await tester.pump(queuePollInterval);
        await tester.pumpAndSettle();
        expect(ids(controller), <String>['b', 'c', 'd', 'e']);
        expect(controller.nextCursor, 'after:e');
        await controller.loadMore();
        expect(ids(controller), <String>['b', 'c', 'd', 'e', 'f']);
        expect(controller.error, isNull);
      } finally {
        controller.dispose();
        await session.controller.close();
      }
    },
  );

  testWidgets('a quiet reread never drops a page loaded while it was asking', (
    WidgetTester tester,
  ) async {
    final KeysetRepository repository = KeysetRepository(<Specimen>[
      row('a'),
      row('b'),
      row('c'),
      row('d'),
    ]);
    final TestSession session = TestSession();
    final WorkspaceController controller = await started(
      tester,
      repository,
      session,
    );
    try {
      expect(ids(controller), <String>['a', 'b']);
      // An Intake handoff rereads the queue; its first page is slow.
      final Completer<void> slow = Completer<void>();
      repository.gates[''] = slow;
      final Future<void> reread = controller.refresh(quiet: true);
      await tester.pump();
      // Meanwhile the reviewer loads the next page.
      await controller.loadMore();
      expect(ids(controller), <String>['a', 'b', 'c', 'd']);
      slow.complete();
      await reread;
      expect(
        ids(controller),
        <String>['a', 'b', 'c', 'd'],
        reason: 'the reread was asked for one page and must not replace two',
      );
      expect(controller.error, isNull);
    } finally {
      controller.dispose();
      await session.controller.close();
    }
  });

  testWidgets(
    'a failed quiet poll retries each tick and reports the outage once',
    (WidgetTester tester) async {
      final KeysetRepository repository = KeysetRepository(<Specimen>[
        row('a'),
      ]);
      final TestSession session = TestSession();
      final WorkspaceController controller = await started(
        tester,
        repository,
        session,
      );
      try {
        repository.failures = 3;
        final int before = repository.pageReads;
        await tester.pump(queuePollInterval);
        await tester.pump();
        final WorkspaceError? first = controller.error;
        expect(first, isNotNull);

        await tester.pump(queuePollInterval);
        await tester.pump();
        expect(repository.pageReads, before + 2, reason: 'each tick retries');
        expect(
          identical(controller.error, first),
          isTrue,
          reason:
              'a replaced banner names a new age and is announced again '
              'every tick',
        );

        controller.clearError();
        await tester.pump(queuePollInterval);
        await tester.pump();
        expect(repository.pageReads, before + 3);
        expect(
          controller.error,
          isNull,
          reason: 'a dismissed outage banner is not brought back by a retry',
        );

        repository.server = <Specimen>[row('a'), row('b')];
        await tester.pump(queuePollInterval);
        await tester.pump();
        expect(ids(controller), <String>['a', 'b']);
        expect(controller.error, isNull);

        // A later outage is a new one and is reported.
        repository.failures = 1;
        await tester.pump(queuePollInterval);
        await tester.pump();
        expect(controller.error, isNotNull);
        expect(ids(controller), <String>['a', 'b']);
      } finally {
        controller.dispose();
        await session.controller.close();
      }
    },
  );

  testWidgets(
    'a page loaded while the open record is reread outranks the reread',
    (WidgetTester tester) async {
      final KeysetRepository repository = KeysetRepository(<Specimen>[
        row('a'),
        row('b'),
        row('c'),
        row('d'),
      ]);
      final TestSession session = TestSession();
      final WorkspaceController controller = await started(
        tester,
        repository,
        session,
      );
      try {
        await controller.openSpecimen('a');
        expect(ids(controller), <String>['a', 'b']);
        // Page one answers at once; the open record's read is slow.
        final Completer<void> slowDetail = Completer<void>();
        repository.detailGate = slowDetail;
        repository.server = <Specimen>[
          row('a', revision: 2),
          row('b'),
          row('c'),
          row('d'),
        ];
        final Future<void> reread = controller.refresh(quiet: true);
        await tester.pump();
        // The reviewer loads the next page in that later window.
        await controller.loadMore();
        expect(ids(controller), <String>['a', 'b', 'c', 'd']);
        slowDetail.complete();
        await reread;
        expect(
          ids(controller),
          <String>['a', 'b', 'c', 'd'],
          reason: 'the older one-page snapshot must not replace two pages',
        );
        expect(controller.nextCursor, 'after:d');
        expect(controller.selected?.revision, 2);
        expect(controller.error, isNull);
      } finally {
        controller.dispose();
        await session.controller.close();
      }
    },
  );

  testWidgets('a recovery answered while the list is held ends the outage', (
    WidgetTester tester,
  ) async {
    final KeysetRepository repository = KeysetRepository(<Specimen>[row('a')]);
    final TestSession session = TestSession();
    final WorkspaceController controller = await started(
      tester,
      repository,
      session,
    );
    try {
      repository.failures = 1;
      await tester.pump(queuePollInterval);
      await tester.pump();
      expect(controller.error, isNotNull);
      controller.clearError();

      // The service recovers while a selection holds the list.
      controller.holdList();
      repository.server = <Specimen>[row('a'), row('b')];
      await tester.pump(queuePollInterval);
      await tester.pump();
      expect(ids(controller), <String>['a']);
      controller.releaseList();
      expect(ids(controller), <String>['a', 'b']);

      // A later outage is a new one and is reported.
      repository.failures = 1;
      await tester.pump(queuePollInterval);
      await tester.pump();
      expect(controller.error, isNotNull);
    } finally {
      controller.dispose();
      await session.controller.close();
    }
  });

  for (final bool held in <bool>[false, true]) {
    testWidgets(
      'returning while a poll is in flight asks once more when it ends'
      '${held ? ' (held list)' : ''}',
      (WidgetTester tester) async {
        final KeysetRepository repository = KeysetRepository(<Specimen>[
          row('a'),
        ]);
        final TestSession session = TestSession();
        final WorkspaceController controller = await started(
          tester,
          repository,
          session,
        );
        try {
          if (held) controller.holdList();
          final Completer<void> slow = Completer<void>();
          repository.gates[''] = slow;
          await tester.pump(queuePollInterval);
          final int asked = repository.pageReads;
          move(tester, <AppLifecycleState>[
            AppLifecycleState.inactive,
            AppLifecycleState.hidden,
            AppLifecycleState.paused,
          ]);
          // Another device adds a record while this one is away.
          repository.server = <Specimen>[row('a'), row('b')];
          move(tester, <AppLifecycleState>[
            AppLifecycleState.hidden,
            AppLifecycleState.inactive,
            AppLifecycleState.resumed,
          ]);
          await tester.pump();
          expect(repository.pageReads, asked, reason: 'no overlapping poll');
          slow.complete();
          await tester.pump();
          await tester.pump();
          expect(
            repository.pageReads,
            asked + 1,
            reason: 'exactly one follow-up poll',
          );
          if (held) {
            expect(ids(controller), <String>['a']);
            controller.releaseList();
          }
          expect(ids(controller), <String>['a', 'b']);
          await tester.pump(const Duration(seconds: 1));
          expect(repository.pageReads, asked + 1);
        } finally {
          controller.dispose();
          await session.controller.close();
        }
      },
    );
  }

  void leaveAndReturn(WidgetTester tester, void Function() meanwhile) {
    move(tester, <AppLifecycleState>[
      AppLifecycleState.inactive,
      AppLifecycleState.hidden,
      AppLifecycleState.paused,
    ]);
    meanwhile();
    move(tester, <AppLifecycleState>[
      AppLifecycleState.hidden,
      AppLifecycleState.inactive,
      AppLifecycleState.resumed,
    ]);
  }

  testWidgets(
    'a record opened before a stale poll ends still gets the owed poll',
    (WidgetTester tester) async {
      final KeysetRepository repository = KeysetRepository(<Specimen>[
        row('a'),
      ]);
      final TestSession session = TestSession();
      final WorkspaceController controller = await started(
        tester,
        repository,
        session,
      );
      try {
        final Completer<void> slowPage = Completer<void>();
        repository.gates[''] = slowPage;
        await tester.pump(queuePollInterval);
        final int asked = repository.pageReads;
        leaveAndReturn(tester, () {
          repository.server = <Specimen>[row('a'), row('b')];
        });
        // The reviewer opens a record before the stale poll answers.
        final Completer<void> slowDetail = Completer<void>();
        repository.detailGate = slowDetail;
        final Future<void> opening = controller.openSpecimen('a');
        await tester.pump();
        slowPage.complete();
        await tester.pump();
        await tester.pump();
        expect(ids(controller), <String>['a'], reason: 'the stale answer');
        expect(repository.pageReads, asked, reason: 'the open record blocks');
        slowDetail.complete();
        await opening;
        await tester.pump();
        await tester.pump();
        expect(repository.pageReads, asked + 1);
        expect(ids(controller), <String>['a', 'b']);
        await tester.pump(const Duration(seconds: 1));
        expect(repository.pageReads, asked + 1, reason: 'one follow-up');
      } finally {
        controller.dispose();
        await session.controller.close();
      }
    },
  );

  testWidgets('a return during a save polls once the save ends', (
    WidgetTester tester,
  ) async {
    final KeysetRepository repository = KeysetRepository(<Specimen>[row('a')]);
    final TestSession session = TestSession();
    final WorkspaceController controller = await started(
      tester,
      repository,
      session,
    );
    try {
      await controller.openSpecimen('a');
      final Completer<Specimen> saving = Completer<Specimen>();
      repository.heldReview = saving;
      final Future<bool> saved = controller.mutate(<String, dynamic>{
        'kind': 'field',
      }, null);
      await tester.pump();
      final int asked = repository.pageReads;
      leaveAndReturn(tester, () {
        repository.server = <Specimen>[row('a'), row('b')];
      });
      await tester.pump();
      expect(repository.pageReads, asked, reason: 'the save blocks the poll');
      saving.complete(row('a', revision: 2));
      expect(await saved, isTrue);
      await tester.pump();
      await tester.pump();
      expect(repository.pageReads, asked + 1);
      expect(ids(controller), <String>['a', 'b']);
      await tester.pump(const Duration(seconds: 1));
      expect(repository.pageReads, asked + 1, reason: 'one follow-up');
    } finally {
      controller.dispose();
      await session.controller.close();
    }
  });
}
