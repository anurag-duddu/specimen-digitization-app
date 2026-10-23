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
    if (failNextRead) {
      failNextRead = false;
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
