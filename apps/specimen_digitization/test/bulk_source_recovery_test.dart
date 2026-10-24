import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/intake/bulk_intake_controller.dart';
import 'package:specimen_digitization/src/screens/intake/bulk_intake_repository.dart';

class InterruptedSourceRepository implements BulkIntakeRepository {
  final Map<String, Json> photos = {};
  final Map<String, String> identities = {};
  bool interrupt = true;
  int pageReads = 0, reconcileCalls = 0, preparedPerCall = 50;
  int activeWrites = 0, maxActiveWrites = 0;
  final List<List<Json>> bulkRequests = [];
  Json get draft => {
    'id': 'draft',
    'revision': photos.length + 1,
    'state': 'draft',
    'entries': photos.values
        .map(
          (row) => {
            'id': row['id'],
            'included': row['included'],
            'removed': row['removed'],
            'photo_sensitive': row['photo_sensitive'],
          },
        )
        .toList(),
  };
  Json result(List<Json> inputs) {
    final found = <Json>[], pending = <String>[];
    for (final input in inputs) {
      final id = input['client_id'] as String;
      if (photos.containsKey(id)) {
        if (identities[id] != jsonEncode(input)) {
          throw const ApiFailure(
            'The original selection changed.',
            code: 'conflict',
          );
        }
        found.add(photos[id]!);
      } else {
        pending.add(id);
      }
    }
    return {
      'items': found,
      'pending_client_ids': pending,
      'draft_revision': photos.length + 1,
    };
  }

  @override
  Future<Json> intakeRequest(
    CollectionScope scope,
    String method,
    String path, {
    Json? body,
    Map<String, String>? query,
    Uint8List? bytes,
    int? offset,
  }) async {
    if (path == '/capabilities') return {'bulk_source_admission': true};
    if (path == '/drafts' && method == 'GET') {
      return {
        'items': [draft],
        'next_cursor': null,
      };
    }
    if (path == '/submissions') return {'items': <Json>[], 'next_cursor': null};
    if (path == '/drafts' && method == 'POST' || path == '/drafts/draft') {
      return draft;
    }
    if (path == '/drafts/draft/edit') {
      for (final photo in photos.values.where(
        (row) => (body!['item_ids'] as List).contains(row['id']),
      )) {
        photo['removed'] = body!['action'] == 'remove';
      }
      return draft;
    }
    if (path.endsWith('/items/bulk') || path.endsWith('/items/reconcile')) {
      activeWrites++;
      if (activeWrites > maxActiveWrites) maxActiveWrites = activeWrites;
      try {
        await Future<void>.delayed(Duration.zero);
        final inputs = objects(body!['items']);
        expect(inputs.length, inInclusiveRange(1, 50));
        expect(
          inputs.map((row) => row['client_id']).toSet().length,
          inputs.length,
        );
        if (path.endsWith('/reconcile')) {
          reconcileCalls++;
          return result(inputs);
        }
        bulkRequests.add(inputs);
        for (final input in inputs.take(preparedPerCall)) {
          final id = input['client_id'] as String;
          if (photos.containsKey(id) && identities[id] != jsonEncode(input)) {
            throw const ApiFailure(
              'The original selection changed.',
              code: 'conflict',
            );
          }
          identities.putIfAbsent(id, () => jsonEncode(input));
          photos.putIfAbsent(
            id,
            () => {
              ...input,
              'id': id,
              'state': 'waiting',
              'included': true,
              'removed': false,
              'photo_sensitive': false,
            },
          );
          if (photos.length == 251 && interrupt) {
            interrupt = false;
            throw const ApiFailure(
              'Connection interrupted after saving',
              code: 'offline',
            );
          }
        }
        return result(inputs);
      } finally {
        activeWrites--;
      }
    }
    if (path == '/drafts/draft/items' && method == 'GET') {
      pageReads++;
      final start = int.tryParse(query?['after'] ?? '0') ?? 0;
      final end = (start + 100).clamp(0, photos.length);
      return {
        'items': photos.values.toList().sublist(start, end),
        'next_cursor': end < photos.length ? '$end' : null,
      };
    }
    throw StateError('Unexpected $method $path');
  }

  @override
  Future<Uint8List> intakePreview(
    CollectionScope scope,
    String id, {
    bool full = false,
  }) async => Uint8List(0);
}

class CompletedSourceRepository extends InterruptedSourceRepository {
  bool completed = false, discarded = false;
  int completions = 0;
  List<String> chosen = [];
  @override
  Json get draft => {
    ...super.draft,
    'state': discarded
        ? 'discarded'
        : completed
        ? 'submitted'
        : 'draft',
    if (completed)
      'submitted_entries': [
        for (final entry in objects(super.draft['entries']))
          if (chosen.contains(entry['id'])) entry,
      ],
  };
  @override
  Future<Json> intakeRequest(
    CollectionScope scope,
    String method,
    String path, {
    Json? body,
    Map<String, String>? query,
    Uint8List? bytes,
    int? offset,
  }) async {
    if (method == 'POST' && path == '/drafts' && (completed || discarded)) {
      photos.clear();
      identities.clear();
      completed = false;
      discarded = false;
    }
    if (path.endsWith('/submit')) {
      completed = true;
      chosen = List<String>.from(body!['item_ids'] as List);
      return {
        'id': 'submission-${completions++}',
        'total': photos.length,
        'counts': {'sent': photos.length},
      };
    }
    if (path.endsWith('/discard')) {
      discarded = true;
      return draft;
    }
    return super.intakeRequest(
      scope,
      method,
      path,
      body: body,
      query: query,
      bytes: bytes,
      offset: offset,
    );
  }
}

class HeldSourceRepository extends CompletedSourceRepository {
  final started = Completer<void>(), release = Completer<void>();
  @override
  Future<Json> intakeRequest(
    CollectionScope scope,
    String method,
    String path, {
    Json? body,
    Map<String, String>? query,
    Uint8List? bytes,
    int? offset,
  }) async {
    if (path.endsWith('/bulk') && !started.isCompleted) {
      started.complete();
      await release.future;
    }
    if (path == '/drafts/other') {
      return {'id': 'other', 'state': 'draft', 'revision': 1};
    }
    if (path == '/drafts/other/items') {
      return {'items': <Json>[], 'next_cursor': null};
    }
    return super.intakeRequest(
      scope,
      method,
      path,
      body: body,
      query: query,
      bytes: bytes,
      offset: offset,
    );
  }
}

class RemainingSourceRepository extends CompletedSourceRepository {
  String remainingState = 'draft';
  List<String> remainingIds = [];
  Json get remaining => {
    'id': 'remaining',
    'revision': 1,
    'state': remainingState,
    'entries': [
      for (final photo in photos.values)
        if (remainingIds.contains(photo['id']))
          {
            'id': photo['id'],
            'included': photo['included'],
            'removed': photo['removed'],
            'photo_sensitive': photo['photo_sensitive'],
          },
    ],
    if (remainingState == 'submitted')
      'submitted_entries': [
        for (final id in remainingIds) {'id': id},
      ],
  };
  @override
  Future<Json> intakeRequest(
    CollectionScope scope,
    String method,
    String path, {
    Json? body,
    Map<String, String>? query,
    Uint8List? bytes,
    int? offset,
  }) async {
    if (path == '/drafts/remaining') return remaining;
    if (path == '/drafts/remaining/items') {
      return {
        'items': photos.values
            .where((row) => remainingIds.contains(row['id']))
            .toList(),
        'next_cursor': null,
      };
    }
    if (path == '/drafts/remaining/submit' ||
        path == '/drafts/remaining/discard') {
      remainingState = path.endsWith('/submit') ? 'submitted' : 'discarded';
      return {
        'id': 'remaining-submission',
        'total': remainingIds.length,
        'counts': {'sent': remainingIds.length},
      };
    }
    final response = await super.intakeRequest(
      scope,
      method,
      path,
      body: body,
      query: query,
      bytes: bytes,
      offset: offset,
    );
    if (path == '/drafts/draft/submit') {
      remainingIds = photos.values
          .where((row) => !chosen.contains(row['id']))
          .map((row) => row['id'] as String)
          .toList();
      return {...response, 'remaining_draft_id': 'remaining'};
    }
    if (method == 'GET' && path == '/drafts' && completed) {
      return {
        ...response,
        'items': [...objects(response['items']), remaining],
      };
    }
    return response;
  }
}

class LostAdmissionRepliesRepository extends CompletedSourceRepository {
  @override
  Future<Json> intakeRequest(
    CollectionScope scope,
    String method,
    String path, {
    Json? body,
    Map<String, String>? query,
    Uint8List? bytes,
    int? offset,
  }) async {
    if (path.endsWith('/reconcile')) {
      throw const ApiFailure('Lost reconciliation reply');
    }
    final response = await super.intakeRequest(
      scope,
      method,
      path,
      body: body,
      query: query,
      bytes: bytes,
      offset: offset,
    );
    if (path.endsWith('/bulk')) throw const ApiFailure('Lost admission reply');
    return response;
  }
}

class LegacySourceRepository extends InterruptedSourceRepository {
  LegacySourceRepository({this.advertised = false});
  final bool advertised;
  int singleCalls = 0, missingRouteCalls = 0;
  bool loseReply = true;
  @override
  Future<Json> intakeRequest(
    CollectionScope scope,
    String method,
    String path, {
    Json? body,
    Map<String, String>? query,
    Uint8List? bytes,
    int? offset,
  }) async {
    if (path == '/capabilities') {
      return advertised ? {'bulk_source_admission': true} : {};
    }
    if (path.endsWith('/bulk') || path.endsWith('/reconcile')) {
      missingRouteCalls++;
      throw const ApiFailure('Route unavailable', status: 404);
    }
    if (method == 'POST' && path == '/drafts/draft/items') {
      singleCalls++;
      final input = body!;
      final id = input['client_id'] as String;
      if (identities[id] != null && identities[id] != jsonEncode(input)) {
        throw const ApiFailure('Identity changed', status: 409);
      }
      identities[id] = jsonEncode(input);
      photos.putIfAbsent(
        id,
        () => {
          ...input,
          'id': id,
          'state': 'waiting',
          'included': false,
          'removed': false,
          'photo_sensitive': true,
        },
      );
      if (loseReply) {
        loseReply = false;
        throw const ApiFailure('Lost item reply', status: 503);
      }
      return {...photos[id]!}..removeWhere(
        (key, _) =>
            const ['included', 'removed', 'photo_sensitive'].contains(key),
      );
    }
    return super.intakeRequest(
      scope,
      method,
      path,
      body: body,
      query: query,
      bytes: bytes,
      offset: offset,
    );
  }
}

const sourceScope = CollectionScope(
  organizationId: 'org',
  collectionId: 'collection',
  name: 'Collection',
);
List<Json> sourcePhotos(int count, {int start = 0}) => List.generate(
  count,
  (i) => {
    'filename': '${i + start}.png',
    'source': {
      'provider': i.isEven ? 'google_drive' : 'dropbox',
      'object_id': '${i + start}',
      'version': 'original-v1',
    },
  },
);
BulkIntakeController sourceController(InterruptedSourceRepository repository) =>
    BulkIntakeController(
      repository: repository,
      scope: sourceScope,
      userId: 'owner',
    )..capabilities = {'bulk_source_admission': true};

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() => SharedPreferences.setMockInitialValues({}));
  for (final size in [10, 100, 500]) {
    test(
      '$size selections use bounded50-item admission requests without Submit',
      () async {
        final repository = InterruptedSourceRepository()..interrupt = false;
        final controller = sourceController(repository);
        addTearDown(controller.dispose);
        final photos = sourcePhotos(size);
        await controller.addSource(photos);
        expect(controller.error, isNull);
        expect(controller.visible.length, size);
        expect(repository.bulkRequests.length, (size / 50).ceil());
        expect(repository.reconcileCalls, 0);
        expect(repository.maxActiveWrites, 1);
        expect(controller.sourceAddCompleted, size);
        expect(controller.addingSources, isFalse);
        expect(
          controller.visible.map((row) => row.data['client_id']).toSet().length,
          size,
        );
        expect(controller.submissions, isEmpty);
        expect(
          photos.every(
            (row) => (row['source'] as Map)['version'] == 'original-v1',
          ),
          isTrue,
        );
      },
    );
  }
  test(
    '500 selections reconcile a lost reply and resend only exact missing inputs',
    () async {
      final repository = InterruptedSourceRepository();
      final controller = sourceController(repository);
      addTearDown(controller.dispose);
      final photos = sourcePhotos(500);
      await controller.addSource(photos);
      expect(controller.error, isNotNull);
      expect(controller.visible.length, 251);
      final originalIds = photos.map((row) => row['client_id']).toList();
      final initialCalls = repository.bulkRequests.length;
      await controller.addSource(photos);
      expect(controller.error, isNull);
      expect(controller.visible.length, 500);
      expect(repository.photos.length, 500);
      expect(photos.map((row) => row['client_id']).toList(), originalIds);
      final resent = repository.bulkRequests
          .skip(initialCalls)
          .expand((rows) => rows);
      expect(
        resent.map((row) => row['client_id']).toSet(),
        originalIds.skip(251).toSet(),
      );
      expect(repository.pageReads, 8);
      expect(controller.submissions, isEmpty);
      await controller.newDraft();
      expect(controller.savedDrafts.single['id'], 'draft');
    },
  );
  test(
    'reopening the controller reconciles retained original request identities',
    () async {
      final repository = InterruptedSourceRepository();
      final first = sourceController(repository);
      final photos = sourcePhotos(500);
      await first.addSource(photos);
      final oldIds = photos.map((row) => row['client_id']).toSet();
      first.dispose();
      final restored = sourceController(repository);
      addTearDown(restored.dispose);
      await restored.initialize();
      final pickedAgain = sourcePhotos(500);
      for (final row in pickedAgain) {
        row['client_id'] = intakeClientId();
      }
      await restored.addSource(pickedAgain);
      expect(restored.error, isNull);
      expect(repository.photos.length, 500);
      expect(pickedAgain.map((row) => row['client_id']).toSet(), oldIds);
    },
  );
  test(
    'duplicate IDs and499 plus2 are rejected before any admission write',
    () async {
      final repository = InterruptedSourceRepository()..interrupt = false;
      final controller = sourceController(repository);
      addTearDown(controller.dispose);
      final duplicate = sourcePhotos(2);
      for (final row in duplicate) {
        row['client_id'] = 'same-client';
      }
      await controller.addSource(duplicate);
      expect(controller.error, contains('once'));
      expect(repository.bulkRequests, isEmpty);
      controller.items = List.generate(
        499,
        (i) => IntakeDraftItem({
          'id': 'existing-$i',
          'client_id': 'existing-client-$i',
          'state': 'ready',
        }),
      );
      await controller.addSource(sourcePhotos(2));
      expect(controller.error, contains('1 more'));
      expect(repository.bulkRequests, isEmpty);
      expect(controller.items.length, 499);
    },
  );
  test(
    'partial budget progress continues but zero progress waits for explicit retry',
    () async {
      final repository = InterruptedSourceRepository()
        ..interrupt = false
        ..preparedPerCall = 20;
      final controller = sourceController(repository);
      addTearDown(controller.dispose);
      await controller.addSource(sourcePhotos(50));
      expect(controller.visible.length, 50);
      expect(repository.bulkRequests.length, 3);
      await controller.newDraft();
      final emptyRepository = InterruptedSourceRepository()
        ..interrupt = false
        ..preparedPerCall = 0;
      final paused = sourceController(emptyRepository);
      addTearDown(paused.dispose);
      await paused.addSource(sourcePhotos(10));
      expect(paused.error, contains('paused'));
      expect(emptyRepository.bulkRequests.length, 1);
      expect(paused.visible, isEmpty);
    },
  );
  test(
    'changed immutable inputs never reuse an acknowledged client ID',
    () async {
      final repository = InterruptedSourceRepository()..interrupt = false;
      final controller = sourceController(repository);
      addTearDown(controller.dispose);
      final photos = sourcePhotos(1);
      await controller.addSource(photos);
      final clientId = photos.single['client_id'];
      (photos.single['source'] as Map)['version'] = 'changed-v2';
      await controller.addSource(photos);
      expect(controller.error, contains('changed'));
      expect(repository.bulkRequests.length, 1);
      expect(repository.photos.keys.single, clientId);
      expect(
        (repository.photos.values.single['source'] as Map)['version'],
        'original-v1',
      );
    },
  );
  test(
    'confirmed removal permits re-add with a new identity, uncertain IDs stay retained',
    () async {
      final repository = InterruptedSourceRepository()..interrupt = false;
      final controller = sourceController(repository);
      addTearDown(controller.dispose);
      final photos = sourcePhotos(1);
      await controller.addSource(photos);
      final removedId = photos.single['client_id'] as String;
      expect(
        controller.retainedSourceClientId(sourcePhotos(1).single),
        removedId,
      );
      await controller.edit('remove', ids: [controller.visible.single.id]);
      expect(controller.sourceClientIdRemoved(removedId), isTrue);
      expect(controller.retainedSourceClientId(sourcePhotos(1).single), isNull);
      await controller.addSource(photos);
      expect(controller.error, isNull);
      expect(controller.visible.length, 1);
      expect(photos.single['client_id'], isNot(removedId));
      expect(repository.photos.length, 2);

      final uncertain = sourcePhotos(1, start: 10);
      repository.preparedPerCall = 0;
      await controller.addSource(uncertain);
      expect(
        controller.retainedSourceClientId(sourcePhotos(1, start: 10).single),
        uncertain.single['client_id'],
      );
    },
  );
  test(
    'completed and discarded receipts are pruned, uncertain and other draft receipts survive',
    () async {
      final repository = CompletedSourceRepository()..interrupt = false;
      final controller = sourceController(repository);
      addTearDown(controller.dispose);
      Future<List<Json>> receipts() async {
        final prefs = await SharedPreferences.getInstance();
        final key = prefs.getKeys().singleWhere(
          (key) => key.startsWith('bulk-intake-v1:'),
        );
        return objects((jsonDecode(prefs.getString(key)!) as Map)['sources']);
      }

      for (var batch = 0; batch < 3; batch++) {
        await controller.addSource(sourcePhotos(100));
        expect((await receipts()).length, 100);
        expect(await controller.submit(), isNotNull);
        expect(await receipts(), isEmpty);
      }
      repository.preparedPerCall = 0;
      final uncertain = sourcePhotos(2);
      await controller.addSource(uncertain);
      final retainedIds = uncertain.map((row) => row['client_id']).toSet();
      await controller.newDraft();
      expect(
        (await receipts()).map((row) => row['client_id']).toSet(),
        retainedIds,
      );
      await controller.openDraft(repository.draft);
      await controller.discardDraft();
      expect(await receipts(), isEmpty);
    },
  );
  test(
    'partial Submit retains unsubmitted and uncertain original receipts',
    () async {
      final repository = CompletedSourceRepository();
      final controller = sourceController(repository);
      addTearDown(controller.dispose);
      final photos = sourcePhotos(500);
      await controller.addSource(photos);
      expect(controller.visible.length, 251);
      repository.photos.values.last['included'] = false;
      await controller.refreshDraft();
      expect(await controller.submit(), isNotNull);
      final prefs = await SharedPreferences.getInstance();
      final key = prefs.getKeys().singleWhere(
        (key) => key.startsWith('bulk-intake-v1:'),
      );
      final retained = objects(
        (jsonDecode(prefs.getString(key)!) as Map)['sources'],
      );
      expect(
        retained.map((row) => row['client_id']).toSet(),
        photos.skip(250).map((row) => row['client_id']).toSet(),
      );
    },
  );
  for (final discard in [false, true]) {
    test(
      'terminal remainder ${discard ? 'discard' : 'Submit'} prunes ancestor receipts',
      () async {
        final repository = RemainingSourceRepository()..interrupt = false;
        final controller = sourceController(repository);
        addTearDown(controller.dispose);
        await controller.addSource(sourcePhotos(2));
        repository.photos.values.last['included'] = false;
        await controller.refreshDraft();
        expect(await controller.submit(), isNotNull);
        expect(controller.draft!.id, 'remaining');
        if (discard) {
          await controller.discardDraft();
        } else {
          repository.photos.values.last['included'] = true;
          await controller.refreshDraft();
          expect(await controller.submit(), isNotNull);
        }
        final prefs = await SharedPreferences.getInstance();
        final key = prefs.getKeys().singleWhere(
          (key) => key.startsWith('bulk-intake-v1:'),
        );
        expect(
          objects((jsonDecode(prefs.getString(key)!) as Map)['sources']),
          isEmpty,
        );
      },
    );
  }
  test(
    'authoritative refresh recovers receipt identity after both mutation replies are lost',
    () async {
      final repository = LostAdmissionRepliesRepository()..interrupt = false;
      final controller = sourceController(repository);
      addTearDown(controller.dispose);
      await controller.addSource(sourcePhotos(2));
      expect(controller.error, isNotNull);
      expect(controller.visible.length, 2);
      expect(await controller.submit(), isNotNull);
      final prefs = await SharedPreferences.getInstance();
      final key = prefs.getKeys().singleWhere(
        (key) => key.startsWith('bulk-intake-v1:'),
      );
      expect(
        objects((jsonDecode(prefs.getString(key)!) as Map)['sources']),
        isEmpty,
      );
    },
  );
  for (final change in ['new', 'open', 'discard']) {
    test(
      '$change waits for active source admission before changing its draft',
      () async {
        final repository = HeldSourceRepository()..interrupt = false;
        final controller = sourceController(repository);
        addTearDown(controller.dispose);
        final adding = controller.addSource(sourcePhotos(1));
        await repository.started.future;
        final switching = switch (change) {
          'new' => controller.newDraft(),
          'open' => controller.openDraft({
            'id': 'other',
            'state': 'draft',
            'revision': 1,
          }),
          _ => controller.discardDraft(),
        };
        await Future<void>.delayed(Duration.zero);
        expect(controller.draft!.id, 'draft');
        expect(controller.addingSources, isTrue);
        repository.release.complete();
        await adding;
        await switching;
        expect(repository.photos.length, 1);
        expect(controller.draft?.id, change == 'open' ? 'other' : null);
        expect(controller.visible, isEmpty);
      },
    );
  }
  for (final advertised in [false, true]) {
    test(
      'legacy runtime (bulk advertised=$advertised) preserves exact lost-reply IDs and manifest flags',
      () async {
        final repository = LegacySourceRepository(advertised: advertised);
        final controller = sourceController(repository);
        addTearDown(controller.dispose);
        await controller.initialize();
        final photos = sourcePhotos(3);
        await controller.addSource(photos);
        expect(controller.visible.length, 1);
        expect(controller.error, isNotNull);
        final originalIds = photos.map((row) => row['client_id']).toList();
        final reselected = sourcePhotos(3);
        await controller.addSource(reselected);
        expect(controller.error, isNull);
        expect(repository.photos.length, 3);
        expect(reselected.map((row) => row['client_id']).toList(), originalIds);
        expect(
          controller.visible.every((row) => !row.included && row.sensitive),
          isTrue,
        );
        expect(repository.missingRouteCalls, advertised ? 1 : 0);
        expect(repository.singleCalls, 5);
        expect(controller.submissions, isEmpty);
      },
    );
  }
}
