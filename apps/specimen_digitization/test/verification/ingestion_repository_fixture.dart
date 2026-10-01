// Synthetic in-memory ingestion service for local browser and native QA.
// It exercises the real intake contract but does not contact a collection.
import 'dart:async';

import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/sources.dart';

const CollectionScope previewScope = CollectionScope(
  organizationId: 'synthetic-org',
  collectionId: 'synthetic-collection',
  name: 'Local preview',
);

class PreviewRepository implements SpecimenRepository, SourceRepository {
  @override
  String get mode => 'synthetic';
  @override
  List<dynamic> get blockers => const <dynamic>[];

  final Set<String> _uploaded = <String>{};

  @override
  Future<Json> preflight(CollectionScope scope, IntakeFile file) async =>
      <String, dynamic>{
        'status': 'review',
        'input_sha256': file.sha256,
        'size_bytes': file.bytes.length,
      };

  @override
  Future<Json> createIntake(
    CollectionScope scope,
    IntakeFile file,
    String key,
  ) async => <String, dynamic>{
    'upload_id': file.sha256,
    'state': _uploaded.contains(file.sha256) ? 'duplicate' : 'ready',
  };

  @override
  Future<Json> resumeIntake(CollectionScope scope, String id) async =>
      <String, dynamic>{'upload_id': id, 'state': 'ready'};

  @override
  Future<void> upload(
    CollectionScope scope,
    Json session,
    IntakeFile file,
    void Function(double) progress,
  ) async {
    for (int step = 1; step <= 5; step++) {
      await Future<void>.delayed(const Duration(milliseconds: 260));
      progress(step / 5);
    }
  }

  @override
  Future<Json> completeIntake(
    CollectionScope scope,
    String id,
    String key,
  ) async {
    _uploaded.add(id);
    return <String, dynamic>{'upload_id': id};
  }

  @override
  Future<List<RegisteredSource>> sources(CollectionScope scope) async =>
      <RegisteredSource>[
        const RegisteredSource(<String, dynamic>{
          'source_id': 'preview-storage',
          'collection_id': 'synthetic-collection',
          'bucket': 'preview-bucket',
          'prefix': 'specimens/',
          'media_types': <String>['image/jpeg', 'image/png'],
        }),
      ];

  @override
  Future<SourceObjectPage> sourceObjectPage(
    CollectionScope scope,
    String sourceId, {
    Map<String, String> filters = const <String, String>{},
    String? cursor,
  }) async => const SourceObjectPage(
    <SourceObject>[],
    inventoryId: 'preview',
    objectCount: 0,
    matchingCount: 0,
  );

  @override
  Future<SourceImportResult> importFromSource(
    CollectionScope scope,
    String sourceId,
    List<SourceObject> selection,
    String key, {
    bool sensitive = true,
  }) async => const SourceImportResult(<String, dynamic>{
    'batch_id': 'preview',
    'requested': 0,
    'imported': 0,
    'duplicates': 0,
    'items': <dynamic>[],
  });

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}
