// Paging one snapshot and adding out of it
// (`lib/src/screens/sources/source_controller.dart`).
//
// The behaviours that matter: a select all loads everything before it selects
// anything, because an object cannot be imported without the generation its
// listing row carries; a snapshot recaptured under the reviewer restarts the
// list rather than straddling two; and an import larger than the server's
// bound is several requests that report progress and stop honestly.

import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/sources/source_controller.dart';
import 'package:specimen_digitization/src/sources.dart';

import 'source_fixtures.dart';

SourceBrowseController controllerFor(FakeSourceRepository repository) =>
    SourceBrowseController(
      repository: repository,
      scope: testScope,
      sourceId: 'src-1',
    );

void main() {
  group('paging', () {
    test('loads the first page and says there is more', () async {
      final FakeSourceRepository repository = FakeSourceRepository();
      final SourceBrowseController controller = controllerFor(repository);
      addTearDown(controller.dispose);

      await controller.load();

      expect(controller.items, hasLength(4));
      expect(controller.moreToLoad, isTrue);
      expect(controller.objectCount, 10);
      expect(controller.loaded, isTrue);
    });

    test('appends later pages without losing earlier ones', () async {
      final FakeSourceRepository repository = FakeSourceRepository();
      final SourceBrowseController controller = controllerFor(repository);
      addTearDown(controller.dispose);

      await controller.load();
      await controller.loadMore();

      expect(controller.items, hasLength(8));
      expect(
        controller.items.first.displayName,
        'subject_105526321.jpg',
      );
    });

    test('changing a filter starts the list again', () async {
      final FakeSourceRepository repository = FakeSourceRepository();
      final SourceBrowseController controller = controllerFor(repository);
      addTearDown(controller.dispose);

      await controller.load();
      await controller.loadMore();
      await controller.applyFilter(filter: SourceFilter.inQueue);

      // A filter is part of a cursor's binding, so every loaded page is
      // invalid and the request goes out with no cursor.
      expect(repository.listCursors.last, isNull);
      expect(repository.listFilters.last, <String, String>{
        'imported': 'true',
      });
    });
  });

  group('a snapshot recaptured under the reviewer', () {
    test('restarts the list rather than straddling two', () async {
      final FakeSourceRepository repository = FakeSourceRepository();
      final SourceBrowseController controller = controllerFor(repository);
      addTearDown(controller.dispose);

      await controller.load();
      expect(controller.items, hasLength(4));

      repository.inventoryId = 'inv-2';
      await controller.loadMore();

      // Four rows, not eight: the second answer belongs to a different list,
      // so it replaces rather than appends.
      expect(controller.items, hasLength(4));
      expect(controller.inventoryId, 'inv-2');
      expect(controller.refreshed, isTrue);
    });

    test('recovers when the cursor itself is refused', () async {
      final FakeSourceRepository repository = FakeSourceRepository();
      final SourceBrowseController controller = controllerFor(repository);
      addTearDown(controller.dispose);

      await controller.load();
      repository.listFailure = const ApiFailure(
        'This page link is out of date.',
        code: 'pagination',
      );
      await controller.loadMore();

      expect(controller.refreshed, isTrue);
      expect(controller.error, isNull);
      expect(controller.items, hasLength(4));
    });

    test('tells the reviewer once', () async {
      final FakeSourceRepository repository = FakeSourceRepository();
      final SourceBrowseController controller = controllerFor(repository);
      addTearDown(controller.dispose);

      await controller.load();
      repository.inventoryId = 'inv-2';
      await controller.loadMore();
      expect(controller.refreshed, isTrue);

      controller.acknowledgeRefresh();
      expect(controller.refreshed, isFalse);
    });
  });

  group('how far a select all reaches', () {
    test('is the server count while pages are still unloaded', () async {
      final FakeSourceRepository repository = FakeSourceRepository();
      final SourceBrowseController controller = controllerFor(repository);
      addTearDown(controller.dispose);

      await controller.load();

      expect(controller.allLoaded, isFalse);
      expect(controller.reachableCount, 10);
    });

    test('cannot be stated under the in-queue filter until all is loaded',
        () async {
      final FakeSourceRepository repository = FakeSourceRepository(
        objects: <SourceObject>[
          object('a.jpg', state: 'imported', specimenId: 'spec-a'),
          object('b.jpg', state: 'imported', specimenId: 'spec-b'),
          object('c.jpg', state: 'imported', specimenId: 'spec-c'),
          object('d.jpg', state: 'imported', specimenId: 'spec-d'),
          object('e.jpg', state: 'imported', specimenId: 'spec-e'),
        ],
      );
      final SourceBrowseController controller = controllerFor(repository);
      addTearDown(controller.dispose);

      await controller.applyFilter(filter: SourceFilter.inQueue);

      // The server does not count under this filter, so there is no honest
      // number to put on a select all and the screen must not invent one.
      expect(controller.matchingCount, isNull);
      expect(controller.reachableCount, isNull);

      await controller.loadAll();

      // Once everything is loaded the loaded count is the exact answer,
      // whatever the server counted.
      expect(controller.reachableCount, 5);
    });

    test('loadAll pages until the snapshot is exhausted', () async {
      final FakeSourceRepository repository = FakeSourceRepository(
        objects: manyObjects(20),
        pageSize: 5,
      );
      final SourceBrowseController controller = controllerFor(repository);
      addTearDown(controller.dispose);

      await controller.load();
      await controller.loadAll();

      expect(controller.items, hasLength(20));
      expect(controller.moreToLoad, isFalse);
      expect(repository.listCursors, hasLength(4));
    });
  });

  group('adding a selection', () {
    test('sends it in requests no larger than the server admits', () async {
      final FakeSourceRepository repository = FakeSourceRepository(
        objects: manyObjects(120),
        pageSize: 120,
      );
      final SourceBrowseController controller = controllerFor(repository);
      addTearDown(controller.dispose);
      await controller.load();

      final SourceImportProgress progress = await controller.importSelection(
        controller.items,
      );

      expect(repository.imports.map((List<String> c) => c.length), <int>[
        50,
        50,
        20,
      ]);
      expect(progress.imported, 120);
      expect(progress.complete, isTrue);
    });

    test('reports progress as each request lands', () async {
      final FakeSourceRepository repository = FakeSourceRepository(
        objects: manyObjects(120),
        pageSize: 120,
      );
      final SourceBrowseController controller = controllerFor(repository);
      addTearDown(controller.dispose);
      await controller.load();

      final List<int> seen = <int>[];
      await controller.importSelection(
        controller.items,
        onProgress: (SourceImportProgress p) => seen.add(p.settled),
      );

      // A selection of a hundred is visibly moving rather than one spinner
      // over three calls.
      expect(seen, <int>[50, 100, 120]);
    });

    test('carries one key per chunk, memoised on what that chunk names',
        () async {
      final FakeSourceRepository repository = FakeSourceRepository(
        objects: manyObjects(60),
        pageSize: 60,
      );
      final SourceBrowseController controller = controllerFor(repository);
      addTearDown(controller.dispose);
      await controller.load();

      await controller.importSelection(controller.items);
      final List<String> first = List<String>.from(repository.importKeys);
      await controller.importSelection(controller.items);

      // A retry after an uncertain answer carries the key it carried the
      // first time, so the server reconciles rather than importing twice.
      expect(repository.importKeys.sublist(2), first);
      expect(first.toSet(), hasLength(2));
    });

    test('stops on an integrity failure and names what already landed',
        () async {
      final FakeSourceRepository repository = FakeSourceRepository(
        objects: manyObjects(120),
        pageSize: 120,
      )
        ..importsBeforeFailure = 1
        ..importFailure = const ApiFailure(
          'An object changed.',
          code: 'source_object_changed',
          status: 422,
        );
      final SourceBrowseController controller = controllerFor(repository);
      addTearDown(controller.dispose);
      await controller.load();

      final SourceImportProgress progress = await controller.importSelection(
        controller.items,
      );

      expect(progress.imported, 50);
      expect(progress.complete, isFalse);
      expect(progress.stoppedReason, contains('Reload the source'));
      // The run stopped rather than sending the remaining chunk into a
      // snapshot that is no longer true.
      expect(repository.imports, hasLength(2));
    });

    test('an unsupported photograph is refused alone, not the selection',
        () async {
      final FakeSourceRepository repository = FakeSourceRepository(
        objects: <SourceObject>[
          object('a.jpg'),
          object('b.pdf', state: 'unsupported_media_type'),
          object('c.jpg'),
        ],
        pageSize: 10,
      );
      final SourceBrowseController controller = controllerFor(repository);
      addTearDown(controller.dispose);
      await controller.load();

      final SourceImportProgress progress = await controller.importSelection(
        controller.items,
      );

      expect(progress.imported, 2);
      expect(progress.unchanged, hasLength(1));
      expect(progress.stoppedReason, isNull);
    });
  });

  group('a listing that did not answer', () {
    test('keeps the failure rather than showing an empty source', () async {
      final FakeSourceRepository repository = FakeSourceRepository()
        ..listFailure = const ApiFailure(
          'Access denied',
          code: 'access_denied',
          status: 403,
        );
      final SourceBrowseController controller = controllerFor(repository);
      addTearDown(controller.dispose);

      await controller.load();

      expect(controller.error?.status, 403);
      expect(controller.items, isEmpty);
      // Not loaded and empty are different facts.
      expect(controller.loaded, isFalse);
    });
  });
}
