import 'dart:typed_data';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/intake/bulk_intake_controller.dart';
import 'package:specimen_digitization/src/screens/intake/bulk_intake_repository.dart';

class InterruptedSourceRepository implements BulkIntakeRepository {
  final Map<String, Json> photos = {};
  bool interrupt = true;
  int pageReads = 0;
  Json get draft => {
    'id': 'draft',
    'revision': photos.length + 1,
    'state': 'draft',
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
    if (path == '/drafts' && method == 'POST' || path == '/drafts/draft') {
      return draft;
    }
    if (path == '/drafts/draft/items' && method == 'POST') {
      final id = body!['client_id'] as String;
      photos.putIfAbsent(id, () => {...body, 'id': id, 'state': 'waiting'});
      if (photos.length == 251 && interrupt) {
        interrupt = false;
        throw const ApiFailure(
          'Connection interrupted after saving',
          code: 'offline',
        );
      }
      return photos[id]!;
    }
    if (path == '/drafts/draft/items') {
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

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test(
    '500 source selections reconcile a lost acknowledgement without duplicates or false capacity rejection',
    () async {
      SharedPreferences.setMockInitialValues({});
      final repository = InterruptedSourceRepository();
      final controller = BulkIntakeController(
        repository: repository,
        scope: const CollectionScope(
          organizationId: 'org',
          collectionId: 'collection',
          name: 'Collection',
        ),
        userId: 'owner',
      );
      addTearDown(controller.dispose);
      final photos = List.generate(
        500,
        (i) => <String, dynamic>{
          'filename': '$i.png',
          'source': {
            'provider': i.isEven ? 'google_drive' : 'dropbox',
            'object_id': '$i',
          },
        },
      );
      await controller.addSource(photos);
      expect(controller.error, isNotNull);
      expect(controller.visible.length, 251);
      await controller.addSource(photos);
      expect(controller.error, isNull);
      expect(controller.visible.length, 500);
      expect(repository.photos.length, 500);
      expect(repository.pageReads, 8);
      expect(controller.submissions, isEmpty);
      await controller.newDraft();
      expect(controller.savedDrafts.single['id'], 'draft');
    },
  );
}
