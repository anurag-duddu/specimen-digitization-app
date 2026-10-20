part of 'api_repository.dart';

mixin _ApiRepositoryIntake on _ApiRepositoryBase {
  Specimen _intakeProcessingSummary(
    CollectionScope scope,
    String id,
    Json data,
  ) {
    if (data['specimen_id'] != id ||
        data['organization_id'] != scope.organizationId ||
        data['collection_id'] != scope.collectionId ||
        data['revision'] is! num ||
        data['status'] is! String ||
        data['available_actions'] is! List ||
        (data['available_actions'] as List).any(
          (Object? item) => item is! String,
        )) {
      throw const ApiFailure(
        'This photograph’s processing status could not be verified.',
        code: 'invalid_response',
      );
    }
    return Specimen(data);
  }

  Future<Specimen> intakeProcessingStatus(
    CollectionScope scope,
    String id,
  ) async {
    final Json data = await request(
      'GET',
      '${_root(scope)}/specimens/${Uri.encodeComponent(id)}',
    );
    return _intakeProcessingSummary(scope, id, data);
  }

  Future<Json> startIntakeProcessing(
    CollectionScope scope,
    Specimen specimen,
    String idempotencyKey,
  ) async {
    final Json data = await request(
      'POST',
      '${_root(scope)}/specimens/${Uri.encodeComponent(specimen.id)}/process',
      key: idempotencyKey,
    );
    _intakeProcessingSummary(scope, specimen.id, data);
    return data;
  }

  Future<Specimen> retryIntakeProcessing(
    CollectionScope scope,
    Specimen specimen,
    String reason,
    String idempotencyKey,
  ) async {
    final Json data = await request(
      'POST',
      '${_root(scope)}/runs/${Uri.encodeComponent(specimen.data['active_run_id'])}/actions',
      key: idempotencyKey,
      body: <String, dynamic>{
        'expected_revision': specimen.revision,
        'action': 'retry',
        'reason': reason,
      },
    );
    return _intakeProcessingSummary(scope, specimen.id, data);
  }

  Future<Json> preflight(CollectionScope scope, IntakeFile file) async {
    final result = await request(
      'POST',
      '${_root(scope)}/images/preflight',
      query: {'collection_id': scope.collectionId},
      bytes: file.bytes,
      headers: {'Content-Type': file.mimeType},
    );
    if (result['contract_version'] != 'image-preflight-v1' ||
        result['input_sha256'] != file.sha256 ||
        result['size_bytes'] != file.bytes.length ||
        !['review', 'blocked', 'rejected'].contains(result['status'])) {
      throw const ApiFailure(
        'The server check response does not match this image. No quality result is recorded.',
        code: 'invalid_preflight',
      );
    }
    return result;
  }

  Future<Json> createIntake(
    CollectionScope scope,
    IntakeFile file,
    String key,
  ) async {
    if ((file.width == null) != (file.height == null)) {
      throw const ApiFailure(
        'Image dimension claims must include both width and height, or neither.',
        code: 'invalid_dimensions',
      );
    }
    // HEIF primary-image and RAW active-area bases are established by the
    // approved server codec, even when the client can show a local preview.
    final serverCoordinates = {
      'image/heic',
      'image/heif',
      'image/dng',
      'image/x-adobe-dng',
    }.contains(file.mimeType);
    final epoch = _accessEpoch;
    final userId = expectedUserId?.call();
    final batch = await request(
      'POST',
      '${_root(scope)}/batches',
      key: '${scope.collectionId}-$key-batch',
      body: {
        'collection_id': scope.collectionId,
        'display_name': 'Image intake',
        'acquisition_method': file.method,
        'sensitive': file.sensitive,
      },
    );
    _checkAccess(epoch, userId);
    // Omission is the legacy Sensitive declaration, never permission to
    // downgrade an existing batch after an interrupted creation request.
    final batchSensitive = batch.containsKey('sensitive')
        ? batch['sensitive']
        : true;
    if (batchSensitive is! bool || batchSensitive != file.sensitive) {
      throw const ApiFailure(
        'This batch has a different sensitivity from the selected photograph. Its original classification is unchanged.',
        code: 'intake_sensitivity_mismatch',
      );
    }
    return request(
      'POST',
      '${_root(scope)}/batches/${batch['batch_id']}/items',
      key: '${scope.collectionId}-$key',
      body: {
        'client_item_id': file.sha256,
        'filename': file.name,
        'media_type': file.mimeType,
        'size_bytes': file.bytes.length,
        'sensitive': file.sensitive,
        if (!serverCoordinates && file.width != null) 'width': file.width,
        if (!serverCoordinates && file.height != null) 'height': file.height,
        'sha256': file.sha256,
      },
    );
  }

  Future<Json> resumeIntake(CollectionScope scope, String id) =>
      request('GET', '${_root(scope)}/uploads/${Uri.encodeComponent(id)}');
  Future<void> upload(
    CollectionScope scope,
    Json session,
    IntakeFile file,
    void Function(double) progress,
  ) async {
    final epoch = _accessEpoch;
    final userId = expectedUserId?.call();
    var state = await resumeIntake(scope, session['upload_id']);
    _checkAccess(epoch, userId);
    var offset = (state['offset'] as num?)?.toInt() ?? 0;
    if (offset < 0 || offset > file.bytes.length) {
      throw const ApiFailure(
        'The server upload position could not be read. Ask your administrator.',
        code: 'offset',
      );
    }
    const chunkSize = 1024 * 1024;
    while (offset < file.bytes.length) {
      _checkAccess(epoch, userId);
      final end = (offset + chunkSize).clamp(0, file.bytes.length);
      state = await request(
        'PUT',
        '${_root(scope)}/uploads/${Uri.encodeComponent(session['upload_id'])}/content',
        key: 'chunk-${session['upload_id']}-$offset',
        headers: {'Upload-Offset': '$offset'},
        bytes: Uint8List.sublistView(file.bytes, offset, end),
      );
      _checkAccess(epoch, userId);
      final next = (state['offset'] as num?)?.toInt();
      if (next == null || next <= offset || next > file.bytes.length) {
        throw const ApiFailure(
          'The upload did not advance. Retry to match its position on the server.',
          code: 'offset',
        );
      }
      offset = next;
      progress(offset / file.bytes.length);
    }
  }

  Future<Json> completeIntake(
    CollectionScope scope,
    String id,
    String key,
  ) async {
    final epoch = _accessEpoch;
    final userId = expectedUserId?.call();
    final current = await resumeIntake(scope, id);
    _checkAccess(epoch, userId);
    return request(
      'POST',
      '${_root(scope)}/uploads/${Uri.encodeComponent(id)}/complete',
      key: key,
      body: {'expected_revision': current['revision']},
    );
  }
}
