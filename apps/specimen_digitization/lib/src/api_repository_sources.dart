part of 'api_repository.dart';

mixin _ApiRepositorySources on _ApiRepositoryBase {
  Future<List<RegisteredSource>> sources(CollectionScope scope) async =>
      objects((await request('GET', '${_root(scope)}/sources'))['items'])
          .map(RegisteredSource.new)
          .where(
            (RegisteredSource source) =>
                source.collectionId == scope.collectionId,
          )
          .toList();

  Future<SourceObjectPage> sourceObjectPage(
    CollectionScope scope,
    String sourceId, {
    Map<String, String> filters = const {},
    String? cursor,
  }) async {
    // The server refuses an unknown or duplicated filter outright, so a typo
    // here would be a page that never loads. Named rather than passed through.
    const Set<String> allowed = {'imported', 'media_type'};
    if (filters.keys.any((String key) => !allowed.contains(key))) {
      throw const ApiFailure(
        'This source filter is not supported.',
        code: 'invalid_filter',
      );
    }
    final Json result = await request(
      'GET',
      '${_root(scope)}/sources/${Uri.encodeComponent(sourceId)}/objects',
      query: <String, String>{
        ...filters,
        'limit': '$sourcePageSize',
        'cursor': ?cursor,
      },
    );
    final Object? next = result['next_cursor'];
    if (next != null && (next is! String || next.isEmpty || next == cursor)) {
      throw const ApiFailure(
        'This page link is out of date. Reload the source.',
        code: 'pagination',
      );
    }
    final Object? capturedAt = result['captured_at'];
    return SourceObjectPage(
      objects(result['items']).map(SourceObject.new).toList(),
      inventoryId: textOf(result['inventory_id'], ''),
      nextCursor: next as String?,
      capturedAt: capturedAt is String ? DateTime.tryParse(capturedAt) : null,
      objectCount: (result['object_count'] as num?)?.toInt() ?? 0,
      // Absent means the server did not count, which is not zero. Carried
      // through as null so the screen can withhold a select all it could not
      // put an honest number on.
      matchingCount: (result['matching_count'] as num?)?.toInt(),
    );
  }

  Future<SourceImportResult> importFromSource(
    CollectionScope scope,
    String sourceId,
    List<SourceObject> selection,
    String key, {
    bool sensitive = true,
  }) async {
    if (selection.isEmpty) {
      throw const ApiFailure(
        'Choose at least one object to add.',
        code: 'empty_selection',
      );
    }
    final int epoch = _accessEpoch;
    final String? userId = expectedUserId?.call();
    final Json batch = await request(
      'POST',
      '${_root(scope)}/batches',
      key: '${scope.collectionId}-$key-batch',
      body: <String, dynamic>{
        'collection_id': scope.collectionId,
        'display_name': 'Source import',
        'acquisition_method': 'source_import',
        'sensitive': sensitive,
      },
    );
    _checkAccess(epoch, userId);
    // Same rule as an uploaded item: omission is the legacy Sensitive
    // declaration, never permission to downgrade a batch that already exists.
    final Object? batchSensitive = batch.containsKey('sensitive')
        ? batch['sensitive']
        : true;
    if (batchSensitive is! bool || batchSensitive != sensitive) {
      throw const ApiFailure(
        'This batch has a different sensitivity from the chosen objects. Its original classification is unchanged.',
        code: 'intake_sensitivity_mismatch',
      );
    }
    return SourceImportResult(
      await request(
        'POST',
        '${_root(scope)}/batches/${Uri.encodeComponent(textOf(batch['batch_id'], ''))}/items:from-source',
        key: '${scope.collectionId}-$key',
        body: <String, dynamic>{
          'source_id': sourceId,
          'sensitive': sensitive,
          'objects': selection
              .map((SourceObject object) => object.selection)
              .toList(),
        },
      ),
    );
  }
}
