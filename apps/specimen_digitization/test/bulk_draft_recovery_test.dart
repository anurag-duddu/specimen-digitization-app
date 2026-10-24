import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:crypto/crypto.dart';
import 'package:file_selector/file_selector.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_platform_interface.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/intake/bulk_intake_controller.dart';
import 'package:specimen_digitization/src/screens/intake/bulk_intake_repository.dart';

class FailingDraftPreferences extends InMemorySharedPreferencesStore {
  FailingDraftPreferences() : super.empty();
  String? failure;
  bool failNextRead = false;
  int readCount = 0;
  int? failOnReadNumber;
  Completer<void>? pause;
  Completer<void>? entered;

  @override
  Future<bool> setValue(String type, String key, Object value) async {
    if (key.contains('bulk-intake-v1:') && pause != null) {
      entered?.complete();
      await pause!.future;
    }
    if (key.contains('bulk-intake-v1:') && failure != null) {
      final current = failure;
      failure = null;
      if (current == 'commit-throw') {
        await super.setValue(type, key, value);
        throw StateError('Acknowledgement lost');
      }
      if (current == 'throw') throw StateError('Storage full');
      return false;
    }
    return super.setValue(type, key, value);
  }

  @override
  Future<Map<String, Object>> getAll() async {
    readCount++;
    if (failNextRead || readCount == failOnReadNumber) {
      failNextRead = false;
      failOnReadNumber = null;
      throw StateError('Reload unavailable');
    }
    return super.getAll();
  }
}

class OfflineIntake implements BulkIntakeRepository {
  final List<String> calls = [];
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
    calls.add('$method $path');
    throw const ApiFailure('Needs connection', code: 'offline');
  }

  @override
  Future<Uint8List> intakePreview(
    CollectionScope scope,
    String id, {
    bool full = false,
  }) async => throw StateError('Offline');
}

class RegisteringIntake extends OfflineIntake {
  final List<Json> registrations = [];
  final Map<String, Json> items = {};
  final Completer<void> twoRegistrations = Completer<void>();
  Completer<void>? pauseRegistration;
  Completer<void>? registrationEntered;

  Json get draft => {
    'id': 'draft',
    'state': 'draft',
    'revision': 1,
    'created_at': '2026-10-23',
    'entries': [
      for (final item in items.values)
        {
          'id': item['id'],
          'included': true,
          'photo_sensitive': item['photo_sensitive'],
          'removed': false,
        },
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
    calls.add('$method $path');
    if (path == '/capabilities') return {};
    if (path == '/drafts' && method == 'POST') return draft;
    if (path == '/drafts') {
      return {
        'items': items.isEmpty ? <Json>[] : [draft],
        'next_cursor': null,
      };
    }
    if (path == '/submissions') return {'items': <Json>[], 'next_cursor': null};
    if (path == '/drafts/draft') return draft;
    if (path == '/drafts/draft/items' && method == 'GET') {
      return {'items': items.values.toList(), 'next_cursor': null};
    }
    if (path == '/drafts/draft/items' && method == 'POST') {
      registrationEntered?.complete();
      await pauseRegistration?.future;
      registrations.add(Map<String, dynamic>.from(body!));
      if (registrations.length == 2 && !twoRegistrations.isCompleted) {
        twoRegistrations.complete();
      }
      final item = <String, dynamic>{
        ...body,
        'id': 'item-${registrations.length}',
        'draft_id': 'draft',
        'offset': 0,
        'state': 'transferring',
        'included': true,
      };
      items[item['id'] as String] = item;
      return item;
    }
    if (path.startsWith('/items/')) {
      final id = path.split('/')[2];
      final item = items[id]!;
      if (path.endsWith('/content')) {
        item['offset'] = offset! + bytes!.length;
      } else if (path.endsWith('/save')) {
        item['state'] = 'ready';
      }
      return item;
    }
    throw StateError('Unexpected request: $method $path');
  }
}

class SubmittedRecovery extends OfflineIntake {
  SubmittedRecovery(this.hash);
  final String hash;
  final List<int> received = [];
  bool saved = false;
  Json get item => {
    'id': 'original-item',
    'client_id': 'original-client',
    'draft_id': 'frozen-draft',
    'filename': 'original.png',
    'source': {'provider': 'files'},
    'sensitive': true,
    'size_bytes': 4,
    'sha256': hash,
    'offset': saved ? 4 : 2,
    'state': saved ? 'ready' : 'transferring',
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
    calls.add('$method $path');
    if (path == '/capabilities') return {};
    if (path == '/drafts' || path == '/submissions') {
      expect(method, 'GET');
      return {'items': [], 'next_cursor': null};
    }
    if (path == '/submissions/old-submission/items') {
      return {
        'items': [
          {
            'item_id': 'original-item',
            'needs_original': !saved,
            'sha256': hash,
            'size_bytes': 4,
          },
        ],
        'next_cursor': null,
      };
    }
    if (path == '/items/original-item') return item;
    if (path == '/drafts/frozen-draft') {
      return {'id': 'frozen-draft', 'state': 'submitted'};
    }
    if (path == '/items/original-item/content') {
      expect(method, 'PUT');
      expect(offset, 2);
      received.addAll(bytes!);
      return {...item, 'offset': 4};
    }
    if (path == '/items/original-item/save') {
      saved = true;
      return item;
    }
    throw StateError('Unexpected request: $method $path');
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const scope = CollectionScope(
    organizationId: 'org',
    collectionId: 'collection',
    name: 'Collection',
  );
  late Directory directory;
  const channel = MethodChannel('plugins.flutter.io/path_provider');
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    directory = await Directory.systemTemp.createTemp('intake-recovery-');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (_) async => directory.path);
  });
  tearDown(() async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null);
    await directory.delete(recursive: true);
  });
  Future<List<Json>> storedFiles() async {
    final prefs = await SharedPreferences.getInstance();
    final key = prefs.getKeys().singleWhere(
      (key) => key.startsWith('bulk-intake-v1:'),
    );
    return objects((jsonDecode(prefs.getString(key)!) as Map)['files']);
  }

  for (final failure in ['false', 'throw']) {
    test(
      'failed $failure metadata ACK keeps prior captures and permits one retry',
      () async {
        final store = FailingDraftPreferences();
        SharedPreferences.resetStatic();
        SharedPreferencesStorePlatform.instance = store;
        final source = File('${directory.path}/camera.png');
        await source.writeAsBytes([1, 2, 3, 4]);
        final controller = BulkIntakeController(
          repository: OfflineIntake(),
          scope: scope,
          userId: 'owner',
        );
        await controller.initialize();
        await controller.addFiles([XFile(source.path)], camera: true);
        final firstId = (await storedFiles()).single['client_id'];
        store.failure = failure;
        await expectLater(
          controller.addFiles([XFile(source.path)], camera: true),
          throwsStateError,
        );
        expect(controller.visible.length, 1);
        expect((await storedFiles()).single['client_id'], firstId);
        final retained = await Directory(
          '${directory.path}/intake',
        ).list(recursive: true).where((entry) => entry is File).toList();
        expect(retained.length, 1);
        // A rejected write does not poison either serial queue.
        await controller.addFiles(
          [XFile(source.path)],
          camera: true,
          sensitive: true,
        );
        expect(controller.visible.length, 2);
        expect((await storedFiles()).length, 2);
        controller.dispose();
        await source.delete();
        // Reload from the host store rather than the optimistic plugin cache.
        SharedPreferences.resetStatic();
        final recovered = BulkIntakeController(
          repository: OfflineIntake(),
          scope: scope,
          userId: 'owner',
        );
        await recovered.initialize();
        expect(recovered.visible.length, 2);
        expect(recovered.needsReselection, isFalse);
        expect(recovered.visible.where((item) => item.sensitive).length, 1);
        recovered.dispose();
      },
    );
  }

  test(
    'failed reselection preserves earlier retained bytes and identity',
    () async {
      final store = FailingDraftPreferences();
      SharedPreferences.resetStatic();
      SharedPreferencesStorePlatform.instance = store;
      final source = File('${directory.path}/camera.png');
      await source.writeAsBytes([1, 2, 3, 4]);
      final first = BulkIntakeController(
        repository: OfflineIntake(),
        scope: scope,
        userId: 'owner',
      );
      await first.initialize();
      await first.addFiles([XFile(source.path)], camera: true);
      final original = (await storedFiles()).single;
      final oldPath = original['path'] as String;
      first.dispose();

      // The file is unavailable while restoring, then becomes available before
      // reselection. The old path must still survive a rejected metadata save.
      await File(oldPath).delete();
      SharedPreferences.resetStatic();
      final recovered = BulkIntakeController(
        repository: OfflineIntake(),
        scope: scope,
        userId: 'owner',
      );
      await recovered.initialize();
      expect(recovered.needsReselection, isTrue);
      await File(oldPath).writeAsBytes([1, 2, 3, 4]);
      store.failure = 'false';
      await recovered.addFiles([XFile(source.path)]);
      expect(recovered.visible.length, 1);
      expect((await storedFiles()).single['path'], oldPath);
      expect(await File(oldPath).readAsBytes(), [1, 2, 3, 4]);

      await recovered.addFiles([XFile(source.path)]);
      final replacement = (await storedFiles()).single;
      expect(replacement['client_id'], original['client_id']);
      expect(replacement['path'], isNot(oldPath));
      expect(await File(replacement['path'] as String).readAsBytes(), [
        1,
        2,
        3,
        4,
      ]);
      expect(await File(oldPath).exists(), isFalse);
      expect(recovered.visible.length, 1);
      recovered.dispose();
    },
  );

  test(
    'disposal during metadata ACK keeps durable row off stale controller',
    () async {
      final store = FailingDraftPreferences();
      SharedPreferences.resetStatic();
      SharedPreferencesStorePlatform.instance = store;
      final source = File('${directory.path}/camera.png');
      await source.writeAsBytes([1, 2, 3, 4]);
      final controller = BulkIntakeController(
        repository: OfflineIntake(),
        scope: scope,
        userId: 'owner',
      );
      await controller.initialize();
      store.pause = Completer<void>();
      store.entered = Completer<void>();
      final admission = controller.addFiles([XFile(source.path)], camera: true);
      await store.entered!.future;
      controller.dispose();
      store.pause!.complete();
      await admission;
      expect(controller.visible, isEmpty);
      expect((await storedFiles()).length, 1);
      SharedPreferences.resetStatic();
      final recovered = BulkIntakeController(
        repository: OfflineIntake(),
        scope: scope,
        userId: 'owner',
      );
      await recovered.initialize();
      expect(recovered.visible.length, 1);
      expect(recovered.needsReselection, isFalse);
      recovered.dispose();
    },
  );

  test('persisted metadata with lost ACK admits exactly one photo', () async {
    final store = FailingDraftPreferences();
    SharedPreferences.resetStatic();
    SharedPreferencesStorePlatform.instance = store;
    final source = File('${directory.path}/camera.png');
    await source.writeAsBytes([1, 2, 3, 4]);
    final controller = BulkIntakeController(
      repository: OfflineIntake(),
      scope: scope,
      userId: 'owner',
    );
    await controller.initialize();
    store.failure = 'commit-throw';
    await controller.addFiles([XFile(source.path)], camera: true);
    expect(controller.visible.length, 1);
    expect((await storedFiles()).length, 1);
    controller.dispose();
    SharedPreferences.resetStatic();
    final recovered = BulkIntakeController(
      repository: OfflineIntake(),
      scope: scope,
      userId: 'owner',
    );
    await recovered.initialize();
    expect(recovered.visible.length, 1);
    expect(recovered.needsReselection, isFalse);
    recovered.dispose();
  });

  test(
    'unknown ACK retains bytes and retry reuses the same identity',
    () async {
      final store = FailingDraftPreferences();
      SharedPreferences.resetStatic();
      SharedPreferencesStorePlatform.instance = store;
      final source = File('${directory.path}/camera.png');
      await source.writeAsBytes([1, 2, 3, 4]);
      final controller = BulkIntakeController(
        repository: OfflineIntake(),
        scope: scope,
        userId: 'owner',
      );
      await controller.initialize();
      store.failure = 'commit-throw';
      store.failNextRead = true;
      await expectLater(
        controller.addFiles([XFile(source.path)], camera: true),
        throwsStateError,
      );
      expect(controller.visible, isEmpty);
      final first = (await storedFiles()).single;
      expect(await File(first['path'] as String).readAsBytes(), [1, 2, 3, 4]);

      await controller.addFiles([XFile(source.path)], camera: true);
      expect(controller.visible.length, 1);
      final retried = (await storedFiles()).single;
      expect(retried['client_id'], first['client_id']);
      expect(retried['path'], first['path']);
      controller.dispose();
      SharedPreferences.resetStatic();
      final recovered = BulkIntakeController(
        repository: OfflineIntake(),
        scope: scope,
        userId: 'owner',
      );
      await recovered.initialize();
      expect(recovered.visible.length, 1);
      expect(recovered.needsReselection, isFalse);
      recovered.dispose();
    },
  );

  test(
    'unknown ACK resolves after camera closes and new draft opens',
    () async {
      final store = FailingDraftPreferences();
      SharedPreferences.resetStatic();
      SharedPreferencesStorePlatform.instance = store;
      final source = File('${directory.path}/closed-camera.png');
      await source.writeAsBytes([1, 2, 3, 4]);
      final controller = BulkIntakeController(
        repository: OfflineIntake(),
        scope: scope,
        userId: 'owner',
      );
      await controller.initialize();
      store.failure = 'commit-throw';
      store.failNextRead = true;
      await expectLater(
        controller.addFiles([XFile(source.path)], camera: true),
        throwsStateError,
      );
      final accepted = (await storedFiles()).single;
      await source.delete();
      await controller.retrySaving();
      expect(controller.visible.length, 1);
      expect(await File(accepted['path'] as String).exists(), isTrue);
      final next = File('${directory.path}/next-camera.png');
      await next.writeAsBytes([9, 8, 7, 6]);
      await controller.addFiles([XFile(next.path)], camera: true);
      expect(controller.visible.length, 2);
      expect((await storedFiles()).length, 2);
      await controller.newDraft();
      expect(controller.visible, isEmpty);
      expect(
        controller.savedDrafts.any((draft) => draft['local_client_id'] != null),
        isTrue,
      );
      controller.dispose();
    },
  );

  test('reconciliation keeps a photo out of another opened draft', () async {
    final store = FailingDraftPreferences();
    SharedPreferences.resetStatic();
    SharedPreferencesStorePlatform.instance = store;
    final other = File('${directory.path}/other-draft.png');
    final uncertain = File('${directory.path}/uncertain-draft.png');
    await other.writeAsBytes([1, 2, 3, 4]);
    await uncertain.writeAsBytes([5, 6, 7, 8]);
    final controller = BulkIntakeController(
      repository: OfflineIntake(),
      scope: scope,
      userId: 'owner',
    );
    await controller.initialize();
    await controller.addFiles([XFile(other.path)], camera: true);
    final otherRow = (await storedFiles()).single;
    await controller.newDraft();
    store.failure = 'commit-throw';
    store.failNextRead = true;
    await expectLater(
      controller.addFiles([XFile(uncertain.path)], camera: true),
      throwsStateError,
    );
    await controller.openDraft({
      'local_client_id': otherRow['batch_client_id'],
    });
    expect(controller.visible.length, 1);
    expect(controller.visible.single.data['filename'], 'other-draft.png');
    expect((await storedFiles()).length, 2);
    controller.dispose();
  });

  test(
    'new camera route cannot replace an uncertain earlier specimen',
    () async {
      final store = FailingDraftPreferences();
      SharedPreferences.resetStatic();
      SharedPreferencesStorePlatform.instance = store;
      final first = File('${directory.path}/first-route.png');
      final second = File('${directory.path}/second-route.png');
      await first.writeAsBytes([1, 2, 3, 4]);
      await second.writeAsBytes([5, 6, 7, 8]);
      final controller = BulkIntakeController(
        repository: OfflineIntake(),
        scope: scope,
        userId: 'owner',
      );
      await controller.initialize();
      store.failure = 'commit-throw';
      store.failNextRead = true;
      await expectLater(
        controller.addFiles(
          [XFile(first.path)],
          camera: true,
          captureAttempt: Object(),
        ),
        throwsStateError,
      );
      final original = (await storedFiles()).single;
      await first.delete();
      await controller.addFiles(
        [XFile(second.path)],
        camera: true,
        captureAttempt: Object(),
      );
      final rows = await storedFiles();
      expect(rows.length, 2);
      expect(rows.map((row) => row['client_id']).toSet().length, 2);
      expect(await File(original['path'] as String).readAsBytes(), [
        1,
        2,
        3,
        4,
      ]);
      expect(controller.visible.length, 2);
      controller.dispose();
    },
  );

  test('unknown committed photo counts before the 500-photo limit', () async {
    final store = FailingDraftPreferences();
    SharedPreferences.resetStatic();
    SharedPreferencesStorePlatform.instance = store;
    final first = File('${directory.path}/limit-first.png');
    final second = File('${directory.path}/limit-second.png');
    await first.writeAsBytes([1, 2, 3, 4]);
    await second.writeAsBytes([5, 6, 7, 8]);
    final controller = BulkIntakeController(
      repository: OfflineIntake(),
      scope: scope,
      userId: 'owner',
    );
    await controller.initialize();
    controller.items = [
      for (var i = 0; i < 499; i++)
        IntakeDraftItem({'id': 'existing-$i', 'state': 'waiting'}),
    ];
    final attempt = Object();
    store.failure = 'commit-throw';
    store.failNextRead = true;
    await expectLater(
      controller.addFiles(
        [XFile(first.path)],
        camera: true,
        captureAttempt: attempt,
      ),
      throwsStateError,
    );
    expect(controller.visible.length, 499);
    await expectLater(
      controller.addFiles(
        [XFile(second.path)],
        camera: true,
        captureAttempt: Object(),
      ),
      throwsA(isA<ApiFailure>().having((e) => e.code, 'code', 'batch_limit')),
    );
    expect(controller.visible.length, 500);
    expect((await storedFiles()).length, 1);
    await controller.addFiles(
      [XFile(first.path)],
      camera: true,
      captureAttempt: attempt,
    );
    expect(controller.visible.length, 500);
    expect((await storedFiles()).length, 1);
    controller.dispose();
  });

  test('a later capture also starts transfer of a reconciled photo', () async {
    final store = FailingDraftPreferences();
    SharedPreferences.resetStatic();
    SharedPreferencesStorePlatform.instance = store;
    final repository = RegisteringIntake();
    final first = File('${directory.path}/first-online.png');
    final second = File('${directory.path}/second-online.png');
    await first.writeAsBytes([1, 2, 3, 4]);
    await second.writeAsBytes([5, 6, 7, 8]);
    final controller = BulkIntakeController(
      repository: repository,
      scope: scope,
      userId: 'owner',
    );
    await controller.initialize();
    store.failure = 'commit-throw';
    store.failNextRead = true;
    await expectLater(
      controller.addFiles(
        [XFile(first.path)],
        camera: true,
        captureAttempt: Object(),
      ),
      throwsStateError,
    );
    await controller.addFiles(
      [XFile(second.path)],
      camera: true,
      captureAttempt: Object(),
    );
    await repository.twoRegistrations.future.timeout(
      const Duration(seconds: 2),
    );
    expect(repository.registrations.length, 2);
    expect(
      repository.registrations.map((row) => row['client_id']).toSet().length,
      2,
    );
    controller.dispose();
  });

  test(
    'retake at capacity waits for an in-flight registration identity',
    () async {
      final store = FailingDraftPreferences();
      SharedPreferences.resetStatic();
      SharedPreferencesStorePlatform.instance = store;
      final repository = RegisteringIntake();
      final originalFile = File('${directory.path}/queued-original.png');
      final retakeFile = File('${directory.path}/queued-retake.png');
      await originalFile.writeAsBytes([1, 2, 3, 4]);
      await retakeFile.writeAsBytes([5, 6, 7, 8]);
      final controller = BulkIntakeController(
        repository: repository,
        scope: scope,
        userId: 'owner',
      );
      await controller.initialize();
      controller.items = [
        for (var i = 0; i < 499; i++)
          IntakeDraftItem({'id': 'existing-$i', 'state': 'waiting'}),
      ];
      final attempt = Object();
      store.failure = 'commit-throw';
      store.failNextRead = true;
      await expectLater(
        controller.addFiles(
          [XFile(originalFile.path)],
          camera: true,
          captureAttempt: attempt,
        ),
        throwsStateError,
      );
      final original = (await storedFiles()).single;
      repository.pauseRegistration = Completer<void>();
      repository.registrationEntered = Completer<void>();
      final retry = controller.retrySaving();
      await repository.registrationEntered!.future.timeout(
        const Duration(seconds: 2),
      );
      expect(controller.visible.length, 500);
      await expectLater(
        controller.addFiles(
          [XFile(retakeFile.path)],
          camera: true,
          captureAttempt: attempt,
        ),
        throwsA(isA<ApiFailure>().having((e) => e.code, 'code', 'batch_limit')),
      );
      expect((await storedFiles()).single['path'], original['path']);
      expect(await File(original['path'] as String).readAsBytes(), [
        1,
        2,
        3,
        4,
      ]);
      expect(controller.visible.length, 500);
      repository.pauseRegistration!.complete();
      repository.pauseRegistration = null;
      await retry;
      expect(repository.registrations.length, 1);
      controller.dispose();
    },
  );

  test('retake after remote registration uses a new client identity', () async {
    final store = FailingDraftPreferences();
    SharedPreferences.resetStatic();
    SharedPreferencesStorePlatform.instance = store;
    final repository = RegisteringIntake();
    final first = File('${directory.path}/first-camera.png');
    final retake = File('${directory.path}/retake-camera.png');
    await first.writeAsBytes([1, 2, 3, 4]);
    await retake.writeAsBytes([5, 6, 7, 8]);
    final controller = BulkIntakeController(
      repository: repository,
      scope: scope,
      userId: 'owner',
    );
    await controller.initialize();
    final attempt = Object();
    store.failure = 'commit-throw';
    store.failNextRead = true;
    await expectLater(
      controller.addFiles(
        [XFile(first.path)],
        camera: true,
        captureAttempt: attempt,
      ),
      throwsStateError,
    );
    await controller.retrySaving();
    expect(repository.registrations.length, 1);
    final original = repository.registrations.single;
    await controller.addFiles(
      [XFile(retake.path)],
      camera: true,
      captureAttempt: attempt,
    );
    await controller.retrySaving();
    expect(repository.registrations.length, 2);
    expect(
      repository.registrations.last['client_id'],
      isNot(original['client_id']),
    );
    expect(repository.registrations.last['sha256'], isNot(original['sha256']));
    expect(repository.registrations.last['replaces_id'], 'item-1');
    controller.dispose();
  });

  test('retake after unknown ACK replaces the committed photo once', () async {
    final store = FailingDraftPreferences();
    SharedPreferences.resetStatic();
    SharedPreferencesStorePlatform.instance = store;
    final firstSource = File('${directory.path}/first-camera.png');
    final retake = File('${directory.path}/retake-camera.png');
    await firstSource.writeAsBytes([1, 2, 3, 4]);
    await retake.writeAsBytes([5, 6, 7, 8]);
    final controller = BulkIntakeController(
      repository: OfflineIntake(),
      scope: scope,
      userId: 'owner',
    );
    await controller.initialize();
    final attempt = Object();
    store.failure = 'commit-throw';
    store.failNextRead = true;
    await expectLater(
      controller.addFiles(
        [XFile(firstSource.path)],
        camera: true,
        captureAttempt: attempt,
      ),
      throwsStateError,
    );
    final original = (await storedFiles()).single;
    await firstSource.delete();
    store.failure = 'false';
    await expectLater(
      controller.addFiles(
        [XFile(retake.path)],
        camera: true,
        captureAttempt: attempt,
      ),
      throwsStateError,
    );
    expect((await storedFiles()).single['path'], original['path']);
    expect(await File(original['path'] as String).readAsBytes(), [1, 2, 3, 4]);
    expect(controller.visible.length, 1);
    await controller.addFiles(
      [XFile(retake.path)],
      camera: true,
      captureAttempt: attempt,
    );
    final replacement = (await storedFiles()).single;
    expect(replacement['client_id'], original['client_id']);
    expect(replacement['path'], isNot(original['path']));
    expect(await File(replacement['path'] as String).readAsBytes(), [
      5,
      6,
      7,
      8,
    ]);
    expect(await File(original['path'] as String).exists(), isFalse);
    expect(controller.visible.length, 1);
    controller.dispose();
  });

  test(
    'uncertain retake keeps both bytes until replacement is confirmed',
    () async {
      final store = FailingDraftPreferences();
      SharedPreferences.resetStatic();
      SharedPreferencesStorePlatform.instance = store;
      final firstSource = File('${directory.path}/first-camera.png');
      final retake = File('${directory.path}/retake-camera.png');
      await firstSource.writeAsBytes([1, 2, 3, 4]);
      await retake.writeAsBytes([5, 6, 7, 8]);
      final controller = BulkIntakeController(
        repository: OfflineIntake(),
        scope: scope,
        userId: 'owner',
      );
      await controller.initialize();
      final attempt = Object();
      store.failure = 'commit-throw';
      store.failNextRead = true;
      await expectLater(
        controller.addFiles(
          [XFile(firstSource.path)],
          camera: true,
          captureAttempt: attempt,
        ),
        throwsStateError,
      );
      final original = (await storedFiles()).single;
      store.failure = 'commit-throw';
      store.failOnReadNumber = store.readCount + 2;
      await expectLater(
        controller.addFiles(
          [XFile(retake.path)],
          camera: true,
          captureAttempt: attempt,
        ),
        throwsStateError,
      );
      final replacement = (await storedFiles()).single;
      expect(replacement['client_id'], original['client_id']);
      expect(replacement['path'], isNot(original['path']));
      expect(await File(original['path'] as String).readAsBytes(), [
        1,
        2,
        3,
        4,
      ]);
      expect(await File(replacement['path'] as String).readAsBytes(), [
        5,
        6,
        7,
        8,
      ]);

      await controller.retrySaving();
      expect(controller.visible.length, 1);
      expect(await File(original['path'] as String).exists(), isFalse);
      expect(await File(replacement['path'] as String).readAsBytes(), [
        5,
        6,
        7,
        8,
      ]);
      controller.dispose();
    },
  );

  test(
    'later failed edit and retry preserve committed uncertain bytes',
    () async {
      final store = FailingDraftPreferences();
      SharedPreferences.resetStatic();
      SharedPreferencesStorePlatform.instance = store;
      final firstSource = File('${directory.path}/first.png');
      final uncertainSource = File('${directory.path}/uncertain.png');
      await firstSource.writeAsBytes([1, 2, 3, 4]);
      await uncertainSource.writeAsBytes([5, 6, 7, 8]);
      final controller = BulkIntakeController(
        repository: OfflineIntake(),
        scope: scope,
        userId: 'owner',
      );
      await controller.initialize();
      await controller.addFiles([XFile(firstSource.path)], camera: true);
      final firstId = controller.visible.single.id;
      store.failure = 'commit-throw';
      store.failNextRead = true;
      await expectLater(
        controller.addFiles([XFile(uncertainSource.path)], camera: true),
        throwsStateError,
      );
      final before = await storedFiles();
      final uncertain = before.singleWhere(
        (row) => row['filename'] == 'uncertain.png',
      );
      store.failure = 'false';
      await expectLater(
        controller.edit('sensitive', value: true, ids: [firstId]),
        throwsStateError,
      );
      expect(controller.visible.length, 2);
      expect(await File(uncertain['path'] as String).readAsBytes(), [
        5,
        6,
        7,
        8,
      ]);
      expect((await storedFiles()).length, 2);
      // The camera callback can retry its original even after an unrelated
      // snapshot failed. It must recognize the already committed identity.
      await controller.addFiles([XFile(uncertainSource.path)], camera: true);
      expect(controller.visible.length, 2);
      expect((await storedFiles()).length, 2);
      expect(await File(uncertain['path'] as String).readAsBytes(), [
        5,
        6,
        7,
        8,
      ]);
      controller.dispose();
    },
  );

  test(
    'thirty retained captures survive restart without their temporary originals',
    () async {
      final repo = OfflineIntake();
      final controller = BulkIntakeController(
        repository: repo,
        scope: scope,
        userId: 'owner',
      );
      await controller.initialize();
      for (var index = 0; index < 30; index++) {
        final source = File('${directory.path}/capture-$index.png');
        await source.writeAsBytes([1, 2, 3, index]);
        await controller.addFiles(
          [XFile(source.path)],
          camera: true,
          sensitive: index.isEven,
        );
        await source.delete();
      }
      expect(controller.visible.length, 30);
      final prefs = await SharedPreferences.getInstance();
      final snapshot = {
        for (final key in prefs.getKeys()) key: prefs.get(key)!,
      };
      final rows = await storedFiles();
      expect(rows.map((row) => row['client_id']).toSet().length, 30);
      controller.dispose();
      SharedPreferences.setMockInitialValues(snapshot);
      final recovered = BulkIntakeController(
        repository: repo,
        scope: scope,
        userId: 'owner',
      );
      await recovered.initialize();
      expect(recovered.visible.length, 30);
      expect(recovered.needsReselection, isFalse);
      expect(recovered.visible.where((item) => item.sensitive).length, 15);
      for (var index = 0; index < rows.length; index++) {
        expect(await File(rows[index]['path'] as String).readAsBytes(), [
          1,
          2,
          3,
          index,
        ]);
      }
      expect(repo.calls.any((request) => request.contains('/submit')), isFalse);
      recovered.dispose();
    },
  );

  test(
    'native capture survives original deletion and stays private across accounts',
    () async {
      final source = File('${directory.path}/camera.png');
      await source.writeAsBytes([1, 2, 3, 4]);
      final repo = OfflineIntake();
      final first = BulkIntakeController(
        repository: repo,
        scope: scope,
        userId: 'owner',
      );
      await first.initialize();
      await first.addFiles([XFile(source.path)], camera: true, sensitive: true);
      final rows = await storedFiles();
      expect(rows.single['path'], isNot(source.path));
      expect(await File(rows.single['path'] as String).readAsBytes(), [
        1,
        2,
        3,
        4,
      ]);
      first.dispose();
      await source.delete();
      final restored = BulkIntakeController(
        repository: repo,
        scope: scope,
        userId: 'owner',
      );
      await restored.initialize();
      expect(restored.visible.length, 1);
      expect(restored.visible.single.data['photo_sensitive'], isTrue);
      expect(restored.needsReselection, isFalse);
      restored.dispose();
      final other = BulkIntakeController(
        repository: repo,
        scope: scope,
        userId: 'other',
      );
      await other.initialize();
      expect(other.visible, isEmpty);
      other.dispose();
      expect(repo.calls.any((call) => call.contains('/submit')), isFalse);
    },
  );
  test(
    'reselecting missing bytes preserves classification and camera provenance',
    () async {
      final source = File('${directory.path}/camera.png');
      await source.writeAsBytes([5, 6, 7, 8]);
      final repo = OfflineIntake();
      final first = BulkIntakeController(
        repository: repo,
        scope: scope,
        userId: 'owner',
      );
      await first.initialize();
      await first.addFiles([XFile(source.path)], camera: true, sensitive: true);
      final original = (await storedFiles()).single;
      first.dispose();
      await File(original['path'] as String).delete();
      final restored = BulkIntakeController(
        repository: repo,
        scope: scope,
        userId: 'owner',
      );
      await restored.initialize();
      expect(restored.needsReselection, isTrue);
      await restored.addFiles([XFile(source.path)]);
      final repaired = (await storedFiles()).single;
      expect(repaired['client_id'], original['client_id']);
      expect(repaired['photo_sensitive'], isTrue);
      expect((repaired['source'] as Map)['provider'], 'camera');
      restored.dispose();
    },
  );
  test(
    'new offline batch does not mix saved local drafts on reopening',
    () async {
      final source = File('${directory.path}/camera.png');
      await source.writeAsBytes([9, 8, 7]);
      final repo = OfflineIntake();
      final first = BulkIntakeController(
        repository: repo,
        scope: scope,
        userId: 'owner',
      );
      await first.initialize();
      await first.addFiles([XFile(source.path)]);
      final originalBatch = first.savedDrafts.single['local_client_id'];
      await first.newDraft();
      await first.addFiles([XFile(source.path)]);
      expect((await storedFiles()).length, 2);
      first.dispose();
      final restored = BulkIntakeController(
        repository: repo,
        scope: scope,
        userId: 'owner',
      );
      await restored.initialize();
      expect(restored.visible.length, 1);
      expect(restored.savedDrafts.length, 2);
      await restored.openDraft(
        restored.savedDrafts.singleWhere(
          (d) => d['local_client_id'] == originalBatch,
        ),
      );
      expect(restored.visible.single.data['batch_client_id'], originalBatch);
      expect(restored.needsReselection, isFalse);
      restored.dispose();
    },
  );
  test(
    'submitted originals resume their immutable item after reopening',
    () async {
      final source = File('${directory.path}/original.png');
      await source.writeAsBytes([1, 2, 3, 4]);
      final first = BulkIntakeController(
        repository: OfflineIntake(),
        scope: scope,
        userId: 'owner',
      );
      await first.initialize();
      await first.addFiles([XFile(source.path)], sensitive: true);
      final prefs = await SharedPreferences.getInstance();
      final key = prefs.getKeys().singleWhere(
        (key) => key.startsWith('bulk-intake-v1:'),
      );
      final state = jsonDecode(prefs.getString(key)!) as Map<String, dynamic>;
      final row = objects(state['files']).single;
      first.dispose();
      await File(row['path'] as String).delete();
      state['client_id'] = null;
      state['active_draft_id'] = null;
      state['files'] = [
        {
          ...row,
          'client_id': 'original-client',
          'item_id': 'original-item',
          'draft_id': 'frozen-draft',
          'saved': false,
        },
      ];
      await prefs.setString(key, jsonEncode(state));
      final repo = SubmittedRecovery(sha256.convert([1, 2, 3, 4]).toString());
      final restored = BulkIntakeController(
        repository: repo,
        scope: scope,
        userId: 'owner',
      );
      await restored.initialize();
      expect(restored.visible, isEmpty);
      expect(restored.hasPendingLocalTransfers, isTrue);
      final wrong = File('${directory.path}/different.png');
      await wrong.writeAsBytes([4, 3, 2, 1]);
      await restored.reselectSubmission('old-submission', [XFile(wrong.path)]);
      expect(repo.received, isEmpty);
      expect(restored.error, contains('did not match'));
      await restored.reselectSubmission('old-submission', [XFile(source.path)]);
      expect(repo.received, [3, 4]);
      expect(repo.saved, isTrue);
      expect(restored.hasPendingLocalTransfers, isFalse);
      expect(restored.visible, isEmpty);
      expect((await storedFiles()).single['photo_sensitive'], isTrue);
      expect(repo.calls.where((call) => call.startsWith('POST ')), [
        'POST /items/original-item/save',
      ]);
      restored.dispose();
    },
  );
  test(
    'a full draft can reselect missing originals without adding photo 501',
    () async {
      final source = File('${directory.path}/photo.png');
      await source.writeAsBytes([1, 2, 3]);
      final first = BulkIntakeController(
        repository: OfflineIntake(),
        scope: scope,
        userId: 'owner',
      );
      await first.initialize();
      await first.addFiles([XFile(source.path)]);
      final prefs = await SharedPreferences.getInstance();
      final key = prefs.getKeys().singleWhere(
        (key) => key.startsWith('bulk-intake-v1:'),
      );
      final state = jsonDecode(prefs.getString(key)!) as Map<String, dynamic>;
      final original = objects(state['files']).single;
      first.dispose();
      await File(original['path'] as String).delete();
      state['files'] = List.generate(
        500,
        (i) => {...original, 'client_id': 'missing-$i'},
      );
      await prefs.setString(key, jsonEncode(state));
      final restored = BulkIntakeController(
        repository: OfflineIntake(),
        scope: scope,
        userId: 'owner',
      );
      await restored.initialize();
      expect(restored.visible.length, 500);
      await restored.addFiles([XFile(source.path)]);
      expect(restored.visible.length, 500);
      expect((await storedFiles()).length, 500);
      expect(
        await File((await storedFiles()).first['path'] as String).exists(),
        isTrue,
      );
      await expectLater(
        restored.addFiles([XFile(source.path)], camera: true),
        throwsA(isA<ApiFailure>()),
      );
      restored.dispose();
    },
  );
}
