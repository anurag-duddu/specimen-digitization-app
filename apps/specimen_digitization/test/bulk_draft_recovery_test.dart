import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'package:file_selector/file_selector.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/intake/bulk_intake_controller.dart';
import 'package:specimen_digitization/src/screens/intake/bulk_intake_repository.dart';

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
      restored.dispose();
    },
  );
}
