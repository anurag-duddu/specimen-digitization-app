// The source wire model (`lib/src/sources.dart`).
//
// Three things here are load bearing and each has a test: a count the server
// did not make is absent rather than zero, a row state this client does not
// know never enables an action, and an import declares back the generation
// the snapshot recorded.

import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/sources.dart';

import 'source_fixtures.dart';

void main() {
  group('a count the server did not make', () {
    test('is null, and null is not zero', () {
      const SourceObjectPage page = SourceObjectPage(
        <SourceObject>[],
        inventoryId: 'inv-1',
      );
      expect(page.matchingCount, isNull);
      expect(page.matchingCount, isNot(0));
    });

    test('is absent from the listing under the in-queue filter', () async {
      final FakeSourceRepository repository = FakeSourceRepository();
      final SourceObjectPage page = await repository.sourceObjectPage(
        testScope,
        'src-1',
        filters: const <String, String>{'imported': 'true'},
      );
      // Resolving imported costs a checksum lookup per object, so the server
      // refuses to count rather than estimating.
      expect(page.matchingCount, isNull);
    });

    test('is exact when the filter is one the server can scan', () async {
      final FakeSourceRepository repository = FakeSourceRepository();
      final SourceObjectPage page = await repository.sourceObjectPage(
        testScope,
        'src-1',
        filters: const <String, String>{'media_type': 'image/jpeg'},
      );
      expect(page.matchingCount, 10);
    });
  });

  group('a row state', () {
    test('reads the three the server sends', () {
      expect(object('a.jpg').state, SourceObjectState.available);
      expect(
        object('a.jpg', state: 'imported').state,
        SourceObjectState.imported,
      );
      expect(
        object('a.jpg', state: 'unsupported_media_type').state,
        SourceObjectState.unsupportedMediaType,
      );
    });

    test('this client does not know never enables an action', () {
      // A later server may add a state. Showing the row is right; offering it
      // is not, because the client cannot know the action would be accepted.
      final SourceObject unknown = object('a.jpg', state: 'quarantined');
      expect(unknown.state, SourceObjectState.unsupportedMediaType);
    });
  });

  group('an import selection', () {
    test('declares back the generation the snapshot recorded', () {
      // The generation binding is what replaces the client declaration that
      // upload completion checks against. Sending the name alone would give
      // the server nothing to refuse a changed object with.
      final SourceObject row = object('a.jpg', generation: '17518');
      expect(row.selection, <String, dynamic>{
        'object_name': 'microscopic-slides/a.jpg',
        'generation': '17518',
      });
    });

    test('is bounded at the size the server bounds it at', () {
      expect(sourceImportBatchSize, 50);
    });
  });

  group('a size the server did not report', () {
    test('is null rather than zero', () {
      expect(object('a.jpg', sizeBytes: null).sizeBytes, isNull);
      expect(object('a.jpg', sizeBytes: 0).sizeBytes, 0);
    });
  });

  group('import progress', () {
    test('folds several requests into one running total', () {
      SourceImportProgress progress = const SourceImportProgress(
        requested: 4,
      );
      progress = progress.add(
        SourceImportResult(<String, dynamic>{
          'requested': 2,
          'imported': 2,
          'duplicates': 0,
          'items': <Map<String, dynamic>>[
            <String, dynamic>{'object_name': 'a', 'state': 'imported'},
            <String, dynamic>{'object_name': 'b', 'state': 'imported'},
          ],
        }),
      );
      progress = progress.add(
        SourceImportResult(<String, dynamic>{
          'requested': 2,
          'imported': 0,
          'duplicates': 1,
          'items': <Map<String, dynamic>>[
            <String, dynamic>{'object_name': 'c', 'state': 'duplicate'},
            <String, dynamic>{
              'object_name': 'd',
              'state': 'unsupported_media_type',
            },
          ],
        }),
      );
      expect(progress.imported, 2);
      expect(progress.duplicates, 1);
      expect(progress.settled, 4);
      expect(progress.complete, isTrue);
      expect(
        progress.unchanged.map((SourceImportOutcome o) => o.objectName),
        <String>['c', 'd'],
      );
    });

    test('that stopped keeps what already landed', () {
      // The server names the objects it created before refusing rather than
      // concealing them, and so does the report.
      final SourceImportProgress progress =
          const SourceImportProgress(requested: 100, imported: 50)
              .stoppedBy('This source changed.');
      expect(progress.imported, 50);
      expect(progress.complete, isFalse);
      expect(progress.stoppedReason, 'This source changed.');
    });
  });

  group('sourcesIn', () {
    test('is null for a repository that does not serve sources', () {
      expect(sourcesIn(Object()), isNull);
      expect(sourcesIn(null), isNull);
      expect(sourcesIn(FakeSourceRepository()), isNotNull);
    });
  });
}
