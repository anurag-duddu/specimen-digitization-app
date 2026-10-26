// Controller-only regressions for the notification channels a quiet poll uses.
//
// A quiet, list-only poll skips the shell's chrome, but a state change the
// shell or the workbench draws must still reach them: the busy strip and the
// refresh control when a quiet read ends a load, and the workbench's
// next/previous and "N of M" when a held page is released.
import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/workspace.dart';

import 'widget_test.dart' show TestRepository, TestSession;

const _scope = CollectionScope(
  organizationId: 'fixture-org',
  collectionId: 'fixture-collection',
  name: 'Synthetic collection',
  permissions: ['reviewer'],
);

Specimen _record(String id) => Specimen({
  'specimen_id': id,
  'filename': '$id.jpg',
  'revision': 1,
  'disposition': 'needs_human_review',
  'available_actions': <String>[],
});

SpecimenPage _page(List<String> ids) =>
    SpecimenPage([for (final String id in ids) _record(id)]);

class _QueueRepository extends TestRepository {
  /// Each answer is a [SpecimenPage] or a [Completer] of one the test holds.
  final List<Object> pageAnswers = <Object>[];

  @override
  Future<List<CollectionScope>> scopes() async => <CollectionScope>[_scope];

  @override
  Future<SpecimenPage> specimenPage(
    CollectionScope scope, {
    Map<String, String> filters = const {},
    String? cursor,
  }) async {
    if (pageAnswers.isEmpty) {
      throw StateError('No synthetic page was queued');
    }
    final Object answer = pageAnswers.removeAt(0);
    if (answer is Completer<SpecimenPage>) return answer.future;
    return answer as SpecimenPage;
  }

  @override
  Future<Specimen> specimen(CollectionScope scope, String id) async =>
      _record(id);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late _QueueRepository repository;
  late TestSession session;
  late WorkspaceController controller;

  setUp(() {
    repository = _QueueRepository();
    session = TestSession();
    controller = WorkspaceController(
      repository: repository,
      session: session,
      pollInterval: const Duration(days: 1),
    );
  });

  tearDown(() async {
    controller.dispose();
    await session.controller.close();
  });

  test('a quiet read that ends a load in flight reaches the chrome', () async {
    repository.pageAnswers.add(_page(<String>['a', 'b']));
    await controller.checkAccess();
    expect(controller.loading, isFalse);

    // The reviewer asks for a refresh and its answer is slow.
    final Completer<SpecimenPage> slow = Completer<SpecimenPage>();
    repository.pageAnswers.add(slow);
    final Future<void> asked = controller.refresh();
    expect(controller.loading, isTrue);

    // An Intake hand-off rereads quietly meanwhile and takes the list over.
    final List<bool> loadingAtChromeNotify = <bool>[];
    void chromeChanged() => loadingAtChromeNotify.add(controller.loading);
    controller.chromeChanges.addListener(chromeChanged);
    addTearDown(() => controller.chromeChanges.removeListener(chromeChanged));

    repository.pageAnswers.add(_page(<String>['a', 'b', 'c']));
    await controller.refresh(quiet: true);

    expect(controller.loading, isFalse);
    expect(controller.items.map((Specimen s) => s.id), <String>['a', 'b', 'c']);
    // The shell draws its progress strip from `loading` and rebuilds on the
    // chrome channel only, so the last thing it hears must be "not loading".
    expect(loadingAtChromeNotify, isNotEmpty);
    expect(loadingAtChromeNotify.last, isFalse);

    slow.complete(_page(<String>['stale']));
    await asked;
    expect(controller.items.map((Specimen s) => s.id), <String>['a', 'b', 'c']);
  });

  test('a quiet poll with nothing in flight leaves the chrome alone', () async {
    repository.pageAnswers.add(_page(<String>['a', 'b']));
    await controller.checkAccess();

    int chrome = 0;
    int inherited = 0;
    void chromeChanged() => chrome++;
    controller.chromeChanges.addListener(chromeChanged);
    controller.addListener(() => inherited++);
    addTearDown(() => controller.chromeChanges.removeListener(chromeChanged));

    repository.pageAnswers.add(_page(<String>['a', 'b', 'c']));
    await controller.refresh(quiet: true);

    expect(controller.items, hasLength(3));
    expect(chrome, 0, reason: 'a list-only poll must not wake the shell');
    expect(inherited, 0, reason: 'nor the inherited dependants');
  });

  test('releasing a held page wakes the open record\'s listeners', () async {
    repository.pageAnswers.add(_page(<String>['a', 'b', 'c']));
    await controller.checkAccess();
    await controller.openSpecimen('b');
    expect(controller.selectedPosition, 2);
    expect(controller.nextSpecimen?.id, 'c');

    // A row has focus while the poll answers: the page is held.
    controller.holdList();
    repository.pageAnswers.add(_page(<String>['b', 'x']));
    await controller.refresh(quiet: true);
    expect(controller.listHeld, isTrue);
    expect(controller.items, hasLength(3));

    int selectionNotifies = 0;
    void selectionChanged() => selectionNotifies++;
    controller.selectionChanges.addListener(selectionChanged);
    addTearDown(
      () => controller.selectionChanges.removeListener(selectionChanged),
    );

    controller.releaseList();

    expect(controller.items.map((Specimen s) => s.id), <String>['b', 'x']);
    expect(
      selectionNotifies,
      greaterThan(0),
      reason:
          'the workbench computes next, previous and "N of M" from the list '
          'in a build that listens to the selection channel',
    );
    expect(controller.selectedPosition, 1);
    expect(controller.nextSpecimen?.id, 'x');
  });

  test(
    'releasing a held page with no record open skips the selection',
    () async {
      repository.pageAnswers.add(_page(<String>['a', 'b']));
      await controller.checkAccess();
      controller.holdList();
      repository.pageAnswers.add(_page(<String>['a', 'c']));
      await controller.refresh(quiet: true);

      int selectionNotifies = 0;
      int listNotifies = 0;
      void selectionChanged() => selectionNotifies++;
      void listChanged() => listNotifies++;
      controller.selectionChanges.addListener(selectionChanged);
      controller.listChanges.addListener(listChanged);
      addTearDown(() {
        controller.selectionChanges.removeListener(selectionChanged);
        controller.listChanges.removeListener(listChanged);
      });

      controller.releaseList();

      expect(controller.items.map((Specimen s) => s.id), <String>['a', 'c']);
      expect(listNotifies, 1);
      expect(selectionNotifies, 0);
    },
  );
}
