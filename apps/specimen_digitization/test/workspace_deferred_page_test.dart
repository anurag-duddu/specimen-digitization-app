// Synthetic, controller-only regressions for G18-FRONTEND-P1-DEFERRED-PAGE.
// No existing assertions or fixtures are replaced by this new test file.
import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/workspace.dart';

import 'widget_test.dart' show TestRepository, TestSession;

const _scopeA = CollectionScope(
  organizationId: 'fixture-org-a',
  collectionId: 'fixture-collection-a',
  name: 'Synthetic collection A',
  permissions: ['reviewer'],
);
const _scopeB = CollectionScope(
  organizationId: 'fixture-org-b',
  collectionId: 'fixture-collection-b',
  name: 'Synthetic collection B',
  permissions: ['reviewer'],
);

SpecimenPage _page(
  String id, {
  String disposition = 'needs_human_review',
  String? cursor,
}) => SpecimenPage([
  Specimen({
    'specimen_id': id,
    'filename': '$id.jpg',
    'revision': 1,
    'disposition': disposition,
    'available_actions': <String>[],
  }),
], nextCursor: cursor);

class _QueueRepository extends TestRepository implements AccessFailureSource {
  final failures = StreamController<ApiFailure>.broadcast(sync: true);
  final pageAnswers = <Object>[];
  final scopeAnswers = <Object>[];
  final requests =
      <({String scopeKey, Map<String, String> filters, String? cursor})>[];

  @override
  Stream<ApiFailure> get accessFailures => failures.stream;

  @override
  Future<List<CollectionScope>> scopes() async {
    if (scopeAnswers.isEmpty) return [_scopeA, _scopeB];
    final answer = scopeAnswers.removeAt(0);
    if (answer is ApiFailure) throw answer;
    if (answer is Completer<List<CollectionScope>>) return answer.future;
    return answer as List<CollectionScope>;
  }

  @override
  Future<SpecimenPage> specimenPage(
    CollectionScope scope, {
    Map<String, String> filters = const {},
    String? cursor,
  }) async {
    requests.add((
      scopeKey: scope.key,
      filters: Map<String, String>.from(filters),
      cursor: cursor,
    ));
    // An extra request is a fixture failure, rather than silently reusing a
    // response from another collection or read view.
    if (pageAnswers.isEmpty) {
      throw StateError('No synthetic page was queued for ${scope.key}');
    }
    final answer = pageAnswers.removeAt(0);
    if (answer is ApiFailure) throw answer;
    return answer as SpecimenPage;
  }
}

List<String> _ids(WorkspaceController controller) =>
    controller.items.map((record) => record.id).toList();

// Completes on the controller's observable result, including the scheduled
// refresh after selectRouteKey. No timed sleeps or periodic poll are needed.
Future<void> _observe(
  WorkspaceController controller,
  bool Function() done,
  void Function() begin,
) async {
  final completed = Completer<void>();
  void changed() {
    if (done() && !completed.isCompleted) completed.complete();
  }

  controller.addListener(changed);
  try {
    begin();
    changed();
    await completed.future;
  } finally {
    controller.removeListener(changed);
  }
}

Future<void> _holdQuietPage(
  WorkspaceController controller,
  _QueueRepository repository, {
  bool start = false,
}) async {
  repository.pageAnswers.add(_page('initial-a', cursor: 'initial-a-cursor'));
  if (start) {
    await _observe(
      controller,
      () => !controller.loading && _ids(controller).contains('initial-a'),
      controller.start,
    );
  } else {
    await controller.checkAccess();
  }
  expect(controller.scope?.key, _scopeA.key);
  expect(controller.scopesVerified, isTrue);
  expect(_ids(controller), ['initial-a']);

  controller.holdList();
  repository.pageAnswers.add(_page('deferred-a', cursor: 'deferred-a-cursor'));
  await controller.refresh(quiet: true);
  expect(controller.listHeld, isTrue);
  expect(_ids(controller), ['initial-a']);
  expect(repository.requests, hasLength(2));
  expect(repository.requests.last.scopeKey, _scopeA.key);
  expect(repository.requests.last.filters, {
    'disposition': 'needs_human_review',
  });
}

void _expectNoAccessCache(WorkspaceController controller) {
  expect(controller.scopesVerified, isFalse);
  expect(controller.scopes, isEmpty);
  expect(controller.scope, isNull);
  expect(controller.items, isEmpty);
  expect(controller.selected, isNull);
  expect(controller.selectedId, isNull);
  expect(controller.nextCursor, isNull);
  expect(controller.error?.clearsAccess, isTrue);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('deferred queue page ownership', () {
    late _QueueRepository repository;
    late TestSession session;
    late WorkspaceController controller;

    setUp(() {
      repository = _QueueRepository();
      session = TestSession();
      controller = WorkspaceController(
        repository: repository,
        session: session,
        // Stream-denial cases start the controller but do not need a poll.
        pollInterval: const Duration(days: 1),
      );
    });

    tearDown(() async {
      controller.dispose();
      await session.controller.close();
      await repository.failures.close();
    });

    test(
      'same-view quiet page applies only after the last hold releases',
      () async {
        await _holdQuietPage(controller, repository);
        controller.holdList();

        controller.releaseList();
        expect(controller.listHeld, isTrue);
        expect(_ids(controller), ['initial-a']);

        controller.releaseList();
        expect(controller.listHeld, isFalse);
        expect(_ids(controller), ['deferred-a']);
        expect(controller.nextCursor, 'deferred-a-cursor');
        expect(controller.scope?.key, _scopeA.key);
        expect(controller.activeFilters, {'disposition': 'needs_human_review'});
        expect(repository.requests, hasLength(2));
        expect(controller.error, isNull);
      },
    );

    test(
      'successful disposition refresh is not overwritten at release',
      () async {
        await _holdQuietPage(controller, repository);
        repository.pageAnswers.add(
          _page(
            'cleared-a',
            disposition: 'cleared',
            cursor: 'cleared-a-cursor',
          ),
        );

        await controller.selectDisposition('cleared');
        expect(_ids(controller), ['cleared-a']);
        controller.releaseList();

        expect(controller.disposition, 'cleared');
        expect(_ids(controller), ['cleared-a']);
        expect(controller.items.single.disposition, 'cleared');
        expect(controller.nextCursor, 'cleared-a-cursor');
        expect(repository.requests.last.filters, {'disposition': 'cleared'});
        expect(repository.requests, hasLength(3));
        expect(controller.error, isNull);
      },
    );

    test('successful filter refresh is not overwritten at release', () async {
      await _holdQuietPage(controller, repository);
      repository.pageAnswers.add(
        _page('filtered-a', cursor: 'filtered-a-cursor'),
      );

      await controller.applyFilters({'specimen_id': 'filtered-a'});
      expect(_ids(controller), ['filtered-a']);
      controller.releaseList();

      expect(controller.filters, {'specimen_id': 'filtered-a'});
      expect(_ids(controller), ['filtered-a']);
      expect(controller.nextCursor, 'filtered-a-cursor');
      expect(repository.requests.last.filters, {
        'specimen_id': 'filtered-a',
        'disposition': 'needs_human_review',
      });
      expect(repository.requests, hasLength(3));
      expect(controller.error, isNull);
    });

    test(
      'synchronous disposition notification cannot release an old-view page',
      () async {
        await _holdQuietPage(controller, repository);
        repository.pageAnswers.add(_page('cleared-a', disposition: 'cleared'));
        List<String>? idsAtRelease;
        String? cursorAtRelease;
        bool released = false;
        void changed() {
          if (controller.disposition == 'cleared' && !released) {
            // Set this before release because release itself may notify.
            released = true;
            controller.releaseList();
            idsAtRelease = _ids(controller);
            cursorAtRelease = controller.nextCursor;
          }
        }

        controller.addListener(changed);
        try {
          await controller.selectDisposition('cleared');
        } finally {
          controller.removeListener(changed);
        }

        expect(released, isTrue);
        expect(idsAtRelease, isNotNull);
        expect(idsAtRelease, isNot(contains('deferred-a')));
        expect(cursorAtRelease, isNot('deferred-a-cursor'));
        expect(_ids(controller), ['cleared-a']);
        expect(repository.requests.last.filters, {'disposition': 'cleared'});
        expect(repository.requests, hasLength(3));
      },
    );

    for (final status in [500, 401, 403]) {
      test(
        'scope switch with $status refresh cannot restore old-scope data',
        () async {
          await _holdQuietPage(controller, repository);
          repository.pageAnswers.add(
            ApiFailure('Synthetic collection B failure.', status: status),
          );

          await _observe(
            controller,
            () => !controller.loading && controller.error != null,
            () => expect(
              controller.selectRouteKey(encodeCollectionKey(_scopeB.key)),
              isTrue,
            ),
          );
          expect(repository.requests.last.scopeKey, _scopeB.key);
          expect(controller.items, isEmpty);
          final errorBeforeRelease = controller.error;

          controller.releaseList();

          expect(controller.items, isEmpty);
          expect(controller.nextCursor, isNull);
          expect(controller.error, same(errorBeforeRelease));
          expect(repository.requests, hasLength(3));
          if (status == 500) {
            expect(controller.scope?.key, _scopeB.key);
            expect(controller.scopesVerified, isTrue);
            expect(controller.error?.clearsAccess, isFalse);
          } else {
            _expectNoAccessCache(controller);
          }
        },
      );
    }

    test(
      'access recheck discards the old page while memberships are pending',
      () async {
        await _holdQuietPage(controller, repository);
        final pendingScopes = Completer<List<CollectionScope>>();
        repository.scopeAnswers.add(pendingScopes);
        repository.pageAnswers.add(
          _page('initial-b', cursor: 'initial-b-cursor'),
        );

        final recheck = controller.checkAccess();
        expect(controller.scope, isNull);
        expect(controller.scopesVerified, isFalse);
        controller.releaseList();
        final idsBeforeMemberships = _ids(controller);
        final cursorBeforeMemberships = controller.nextCursor;
        // Always settle the controlled future before asserting the snapshot.
        pendingScopes.complete([_scopeB]);
        await recheck;

        expect(idsBeforeMemberships, isEmpty);
        expect(cursorBeforeMemberships, isNull);
        expect(controller.scope?.key, _scopeB.key);
        expect(controller.scopesVerified, isTrue);
        expect(_ids(controller), ['initial-b']);
        expect(controller.nextCursor, 'initial-b-cursor');
        expect(repository.requests.last.scopeKey, _scopeB.key);
        expect(repository.requests, hasLength(3));
      },
    );

    test(
      'denied access recheck remains empty after the old hold releases',
      () async {
        await _holdQuietPage(controller, repository);
        repository.scopeAnswers.add(
          const ApiFailure('Synthetic membership denial.', status: 403),
        );

        await controller.checkAccess();
        _expectNoAccessCache(controller);
        final errorBeforeRelease = controller.error;
        controller.releaseList();

        _expectNoAccessCache(controller);
        expect(controller.error, same(errorBeforeRelease));
        expect(repository.requests, hasLength(2));
      },
    );

    for (final status in [401, 403]) {
      test(
        'child access revocation $status remains empty after release',
        () async {
          await _holdQuietPage(controller, repository, start: true);

          repository.failures.add(
            ApiFailure('Synthetic child access revocation.', status: status),
          );
          _expectNoAccessCache(controller);
          final errorBeforeRelease = controller.error;
          controller.releaseList();

          _expectNoAccessCache(controller);
          expect(controller.error, same(errorBeforeRelease));
          expect(repository.requests, hasLength(2));
        },
      );
    }

    test(
      'session reset and late release cannot restore the prior cache',
      () async {
        await _holdQuietPage(controller, repository, start: true);

        session.signedIn = false;
        controller.resetSession();
        controller.releaseList();

        expect(controller.scopesLoaded, isFalse);
        expect(controller.scopesVerified, isFalse);
        expect(controller.scopes, isEmpty);
        expect(controller.scope, isNull);
        expect(controller.items, isEmpty);
        expect(controller.selected, isNull);
        expect(controller.selectedId, isNull);
        expect(controller.nextCursor, isNull);
        expect(controller.updatedAt, isNull);
        expect(controller.listHeld, isFalse);
        expect(controller.error, isNull);
        expect(repository.requests, hasLength(2));
      },
    );
  });
}
