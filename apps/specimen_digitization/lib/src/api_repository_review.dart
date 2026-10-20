part of 'api_repository.dart';

mixin _ApiRepositoryReview on _ApiRepositoryScopes {
  Future<HistoryPage> historyPage(
    CollectionScope scope,
    String id, {
    required int throughRevision,
    int afterRevision = 0,
  }) async {
    if (throughRevision < 1 ||
        afterRevision < 0 ||
        afterRevision > throughRevision) {
      throw const ApiFailure(
        'Choose a history version range inside this record.',
        code: 'invalid_history_range',
      );
    }
    final result = await request(
      'GET',
      '${_root(scope)}/specimens/${Uri.encodeComponent(id)}/history',
      query: {
        'after_revision': '$afterRevision',
        'through_revision': '$throughRevision',
        'limit': '10',
      },
    );
    final items = objects(result['items']);
    final next = result['next_cursor'];
    var last = afterRevision;
    final validItems =
        result['items'] is List &&
        items.length == (result['items'] as List).length &&
        items.length <= 10 &&
        items.every((item) {
          final revision = item['revision'];
          if (revision is! int ||
              revision != last + 1 ||
              revision > throughRevision ||
              item['sha256'] is! String ||
              !RegExp(r'^[a-f0-9]{64}$').hasMatch(item['sha256'])) {
            return false;
          }
          last = revision;
          return true;
        });
    if (result['through_revision'] != throughRevision ||
        !validItems ||
        (next == null && last != throughRevision) ||
        (next != null &&
            (next is! int ||
                next != last ||
                next <= afterRevision ||
                next >= throughRevision))) {
      throw const ApiFailure(
        'The history page could not be verified. Retry, or ask your administrator.',
        code: 'invalid_history_page',
      );
    }
    return HistoryPage(
      items: items,
      throughRevision: throughRevision,
      nextCursor: next as int?,
    );
  }

  Future<Specimen> restoreVersion(
    CollectionScope scope,
    Specimen specimen, {
    required int sourceRevision,
    required bool resetToInitial,
    required String reason,
    required String idempotencyKey,
  }) async {
    final epoch = _accessEpoch;
    final userId = expectedUserId?.call();
    if (sourceRevision < 1 ||
        sourceRevision > specimen.revision ||
        (resetToInitial && sourceRevision != 1) ||
        reason.trim().isEmpty) {
      throw const ApiFailure(
        'Choose a retained version and enter a reason.',
        code: 'invalid_restore',
      );
    }
    try {
      final result = await request(
        'POST',
        '${_root(scope)}/specimens/${Uri.encodeComponent(specimen.id)}/history:restore',
        body: {
          'expected_revision': specimen.revision,
          'base_record_version_id': specimen.recordVersionId,
          'source_revision': sourceRevision,
          'reset_to_initial': resetToInitial,
          'reason': reason.trim(),
        },
        key: idempotencyKey,
      );
      _checkAccess(epoch, userId);
      if (result['specimen_id'] != specimen.id ||
          result['revision'] != specimen.revision + 1) {
        throw const ApiFailure(
          'The restored version could not be verified.',
          code: 'invalid_restore_response',
        );
      }
      return _workspace(result, scope);
    } on ApiFailure catch (error) {
      if (!error.artifactRequired ||
          error.details['mutation_committed'] != true ||
          error.details['revision'] != specimen.revision + 1) {
        rethrow;
      }
      _checkAccess(epoch, userId);
      return _artifactSummary(scope, specimen.id, error);
    }
  }

  Future<Specimen> historicalSpecimen(
    CollectionScope scope,
    String id,
    int revision, {
    String? runId,
    String? runSha256,
  }) async {
    final epoch = _accessEpoch;
    final userId = expectedUserId?.call();
    if (revision < 1) {
      throw const ApiFailure(
        'Choose a saved record version.',
        code: 'invalid_revision',
      );
    }
    if ((runId == null) != (runSha256 == null) ||
        (runId != null && runId.isEmpty) ||
        (runSha256 != null && !RegExp(r'^[a-f0-9]{64}$').hasMatch(runSha256))) {
      throw const ApiFailure(
        'The earlier run reference could not be read.',
        code: 'invalid_history_reference',
      );
    }
    Json result;
    try {
      result = await request(
        'GET',
        '${_root(scope)}/specimens/${Uri.encodeComponent(id)}/history/$revision',
        query: {'run_id': ?runId, 'run_sha256': ?runSha256},
      );
    } on ApiFailure catch (e) {
      if (!e.artifactRequired ||
          e.details['revision'] != revision ||
          (runId != null &&
              e.details['record_version_id'] != '$runId:$revision')) {
        rethrow;
      }
      _checkAccess(epoch, userId);
      return _artifactSummary(scope, id, e, historical: true);
    }
    _checkAccess(epoch, userId);
    if (result['specimen_id'] != id || result['revision'] != revision) {
      throw const ApiFailure(
        'The record that came back is not the version that was requested.',
        code: 'invalid_history_record',
      );
    }
    // A historical model is never an editable current snapshot. Source bytes are
    // not fetched implicitly; retained asset IDs/digests remain in its evidence.
    return _workspace(
      {...result, 'available_actions': <String>[]},
      scope,
      loadImage: false,
    );
  }

  Future<Specimen> review(
    CollectionScope scope,
    Specimen specimen,
    Json change,
    String key,
  ) async {
    final epoch = _accessEpoch;
    final userId = expectedUserId?.call();
    try {
      final result = await _review(scope, specimen, change, key);
      _checkAccess(epoch, userId);
      if (result.data['artifact_receipt'] is Map) {
        return Specimen({...result.data, 'mutation_saved': true});
      }
      return result;
    } on ApiFailure catch (e) {
      if (!e.artifactRequired || e.details['mutation_committed'] != true) {
        rethrow;
      }
      _checkAccess(epoch, userId);
      final result = await _artifactSummary(scope, specimen.id, e);
      _checkAccess(epoch, userId);
      return Specimen({...result.data, 'mutation_saved': true});
    }
  }

  Future<Specimen> _review(
    CollectionScope scope,
    Specimen specimen,
    Json change,
    String key,
  ) async {
    final epoch = _accessEpoch;
    final userId = expectedUserId?.call();
    final kind = change['kind'];
    if (kind == 'run_action') {
      final action = change['action'];
      if (![
        'pause',
        'resume',
        'cancel',
        'reprocess',
        'reconcile',
        'reassess_locations',
      ].contains(action)) {
        throw const ApiFailure(
          'This run action is not supported.',
          code: 'invalid_action',
        );
      }
      await request(
        'POST',
        '${_root(scope)}/runs/${Uri.encodeComponent(specimen.data['active_run_id'])}/actions',
        key: key,
        body: {
          'expected_revision': specimen.revision,
          'action': action,
          'reason': change['reason'],
        },
      );
      _checkAccess(epoch, userId);
      return this.specimen(scope, specimen.id);
    }

    final path = kind == 'classification_correction'
        ? 'classification'
        : kind == 'segmentation_correction'
        ? 'regions'
        : 'decisions';
    await request(
      'POST',
      '${_root(scope)}/specimens/${Uri.encodeComponent(specimen.id)}/$path',
      key: key,
      body: {
        'expected_revision': specimen.revision,
        'reason': change['reason'],
        if (path == 'classification') ...{
          'collection_id': change['value'],
          if (change['profile_collection_id'] != null)
            'profile_collection_id': change['profile_collection_id'],
        },
        if (path == 'regions') ...{
          'base_run_id': specimen.data['active_run_id'],
          'regions': objects(change['regions']).map((r) {
            final b = (r['bbox'] as List).cast<num>();
            return <String, dynamic>{
              'id': r['region_id'],
              'asset_id': specimen.assets.first['asset_id'],
              'x': b[0].toInt(),
              'y': b[1].toInt(),
              'width': (b[2] - b[0]).toInt(),
              'height': (b[3] - b[1]).toInt(),
              'order': r['order'],
              'rotation_quarter_turns': r['rotation_quarter_turns'] ?? 0,
              'method': 'human',
              'version': 'review-v1',
            };
          }).toList(),
        },
        if (path == 'decisions') ...{
          'base_record_version_id': specimen.data['latest_record_version_id'],
          ..._decisionWire(change),
        },
      },
    );
    _checkAccess(epoch, userId);
    return this.specimen(scope, specimen.id);
  }

  Json _decisionWire(Json change) {
    final kind = change['kind'];
    return <String, dynamic>{
      'kind': kind == 'field_correction'
          ? 'field'
          : kind == 'transcription_adjudication'
          ? 'transcription'
          : kind,
      'target_id': change['target_id'] ?? '',
      'after': kind == 'field_correction'
          ? {
              'literal': change['value'],
              if (change.containsKey('parsed')) 'parsed': change['parsed'],
              if (change.containsKey('normalized'))
                'normalized': change['normalized'],
              if (change.containsKey('authority_id'))
                'authority_id': change['authority_id'],
              'state': change['state'],
              'reason': change['reason'],
            }
          : kind == 'transcription_adjudication'
          ? {'text': change['value'], 'state': change['state']}
          : kind == 'reading_metadata'
          ? {
              'language_candidates': change['language_candidates'],
              'script_candidates': change['script_candidates'],
              'language_relation': change['language_relation'],
            }
          : kind == 'authority_resolution'
          ? {
              'tool_id': change['tool_id'],
              'identifier': change['identifier'],
              'field_key': change['target_id'],
            }
          : kind == 'research_candidate'
          ? {'selection_id': change['selection_id']}
          : {'confirmed': true},
      // Candidate authority and evidence are resolved from the retained
      // server receipt. The client sends only its opaque selection identifier.
      if (kind != 'research_candidate')
        'evidence_ids': kind == 'transcription_adjudication'
            ? <String>[]
            : change['evidence_ids'] ?? [],
    };
  }

  Future<ReviewBatchResult> reviewCandidateBatch(
    CollectionScope scope,
    Specimen specimen,
    List<Json> changes,
    String reason,
    String keyPrefix, {
    bool Function(Specimen current, Json change)? stillApplies,
    String Function(Specimen current, Json change, int index)? keyFor,
  }) async {
    if (changes.isEmpty) return (specimen: specimen, saved: 0, stopped: false);
    final epoch = _accessEpoch;
    final userId = expectedUserId?.call();
    _checkAccess(epoch, userId);
    if (reason.trim().isEmpty ||
        specimen.id.isEmpty ||
        specimen.revision < 1 ||
        specimen.recordVersionId.isEmpty ||
        changes.length > bulkDecisionLimit) {
      throw const ApiFailure(
        'Reopen the current record and provide one reason before saving.',
        code: 'invalid_review_batch',
      );
    }
    final bodies = <Json>[
      for (final change in changes)
        <String, dynamic>{...change, 'reason': reason},
    ];
    const supported = <String>{
      'research_candidate',
      'field_correction',
      'approve',
      'coverage',
    };
    if (!bodies.any((body) => body['kind'] == 'research_candidate') ||
        bodies.any((body) => !supported.contains(body['kind']))) {
      throw const ApiFailure(
        'Save source or transcription changes before choosing research candidates.',
        code: 'invalid_review_batch',
      );
    }
    // Every pending change was staged against the same original record. No
    // decision may be sent if even one is stale on that original view.
    for (final body in bodies) {
      if (stillApplies != null && !stillApplies(specimen, body)) {
        return (specimen: specimen, saved: 0, stopped: true);
      }
    }
    final entryKeys = <String>[
      for (final (index, body) in bodies.indexed)
        keyFor?.call(specimen, body, index) ?? '$keyPrefix-$index',
    ];
    if (entryKeys.toSet().length != entryKeys.length ||
        entryKeys.any((key) => key.isEmpty || key.length > 200)) {
      throw const ApiFailure(
        'These pending decisions could not be safely submitted. Refresh the record and try again.',
        code: 'invalid_review_batch',
      );
    }
    final expectedKinds = <String>[
      for (final body in bodies) _decisionWire(body)['kind'] as String,
    ];
    final batchKey = crypto.sha256
        .convert(
          utf8.encode(
            jsonEncode(<String, dynamic>{
              'scope': scope.key,
              'specimen_id': specimen.id,
              'revision': specimen.revision,
              'record_version_id': specimen.recordVersionId,
              'reason': reason,
              'entry_keys': entryKeys,
            }),
          ),
        )
        .toString();
    final Json answer;
    try {
      _checkAccess(epoch, userId);
      answer = await request(
        'POST',
        '${_root(scope)}/decisions:batch',
        key: batchKey,
        body: <String, dynamic>{
          'reason': reason,
          'decisions': <Json>[
            for (final (index, body) in bodies.indexed)
              <String, dynamic>{
                'specimen_id': specimen.id,
                'expected_revision': specimen.revision,
                'base_record_version_id': specimen.recordVersionId,
                ..._decisionWire(body),
                'idempotency_key': entryKeys[index],
              },
          ],
        },
      );
      _checkAccess(epoch, userId);
    } catch (error) {
      // The server may have committed before the response was lost. The
      // workspace keeps these decision keys for an identical retry.
      throw ReviewBatchFailure(
        saved: 0,
        specimen: specimen,
        cause: error,
        retainKeys: true,
      );
    }

    ReviewBatchFailure invalidAck() => ReviewBatchFailure(
      saved: 0,
      specimen: specimen,
      cause: const ApiFailure(
        'The server could not confirm which decisions were saved. Refresh and compare, or try saving these choices again.',
        code: 'invalid_batch_ack',
      ),
      retainKeys: true,
    );
    final rawRows = answer['results'];
    if (rawRows is! List ||
        rawRows.length != changes.length ||
        answer['requested'] is! int ||
        answer['requested'] != changes.length) {
      throw invalidAck();
    }
    var applied = 0;
    var refused = 0;
    var skipped = 0;
    int? savedRevision;
    String? savedVersion;
    ApiFailure? refusal;
    for (final (index, raw) in rawRows.indexed) {
      if (raw is! Map) throw invalidAck();
      final row = Json.from(raw);
      if (row['index'] is! int ||
          row['index'] != index ||
          row['specimen_id'] != specimen.id ||
          row['kind'] != expectedKinds[index] ||
          row['idempotency_key'] != entryKeys[index]) {
        throw invalidAck();
      }
      switch (row['outcome']) {
        case 'applied':
          final revision = row['revision'];
          final version = row['record_version_id'];
          if (revision is! int ||
              revision != specimen.revision + 1 ||
              version is! String ||
              version.isEmpty ||
              (savedRevision != null && savedRevision != revision) ||
              (savedVersion != null && savedVersion != version)) {
            throw invalidAck();
          }
          savedRevision = revision;
          savedVersion = version;
          applied++;
          break;
        case 'refused':
          final error = row['error'];
          if (error is! Map ||
              error['code'] is! String ||
              (error['code'] as String).isEmpty) {
            throw invalidAck();
          }
          refusal ??= ApiFailure(
            textOf(error['message'], 'The review decision was refused.'),
            code: error['code'] as String,
            status: error['status'] is int ? error['status'] as int : null,
          );
          refused++;
          break;
        case 'skipped':
          skipped++;
          break;
        default:
          throw invalidAck();
      }
    }
    if (answer['applied'] is! int ||
        answer['refused'] is! int ||
        answer['skipped'] is! int ||
        answer['applied'] != applied ||
        answer['refused'] != refused ||
        answer['skipped'] != skipped ||
        applied + refused + skipped != changes.length ||
        (applied == 0 && refused == 0)) {
      throw invalidAck();
    }
    if (applied == 0) {
      throw ReviewBatchFailure(
        saved: 0,
        specimen: specimen,
        cause:
            refusal ??
            const ApiFailure(
              'The server did not apply any pending decision.',
              code: 'batch_refused',
            ),
      );
    }
    if (applied != changes.length) {
      // One specimen's candidate-bearing group is one CAS. A mixed answer
      // cannot identify a saved prefix; even [refused, applied] must leave
      // every original choice and key intact for reconciliation.
      throw ReviewBatchFailure(
        saved: 0,
        specimen: specimen,
        cause: const ApiFailure(
          'The server returned a mixed result for one record. Refresh and compare.',
          code: 'batch_partial_unexpected',
        ),
        retainKeys: true,
      );
    }
    final Specimen reloaded;
    try {
      reloaded = await this.specimen(scope, specimen.id);
      _checkAccess(epoch, userId);
      if (reloaded.id != specimen.id ||
          reloaded.revision != savedRevision ||
          reloaded.recordVersionId != savedVersion) {
        throw const ApiFailure(
          'The saved record version could not be read back. Refresh before continuing.',
          code: 'batch_readback_mismatch',
        );
      }
    } catch (error) {
      throw ReviewBatchFailure(
        saved: applied,
        specimen: specimen,
        cause: error,
        retainKeys: true,
        acknowledgement: (
          specimenId: specimen.id,
          baseRevision: specimen.revision,
          baseRecordVersionId: specimen.recordVersionId,
          revision: savedRevision!,
          recordVersionId: savedVersion!,
        ),
      );
    }
    return (specimen: reloaded, saved: applied, stopped: false);
  }

  Future<BulkDecisionReport> reviewMany(
    CollectionScope scope,
    List<Specimen> specimens,
    BulkDecisionKind kind,
    String reason,
    String key,
  ) async {
    if (specimens.isEmpty) return const BulkDecisionReport([]);
    final epoch = _accessEpoch;
    final userId = expectedUserId?.call();
    final missing = specimens.where((s) => s.recordVersionId.isEmpty).toList();
    if (missing.isNotEmpty) {
      // Without the version the server last answered there is no optimistic
      // concurrency check, and the decision would be taken against whatever
      // the record happens to be now.
      throw const ApiFailure(
        'The queue is out of date. Refresh it and select again.',
        code: 'missing_record_version',
      );
    }
    final result = await request(
      'POST',
      '${_root(scope)}/decisions:batch',
      key: key,
      body: {
        'reason': reason,
        'decisions': [
          for (final (index, specimen) in specimens.indexed)
            <String, dynamic>{
              'specimen_id': specimen.id,
              'expected_revision': specimen.revision,
              'base_record_version_id': specimen.recordVersionId,
              'kind': kind.wire,
              'idempotency_key': '$key-$index',
              if (kind == BulkDecisionKind.confirmCoverage)
                'after': {'confirmed': true},
            },
        ],
      },
    );
    _checkAccess(epoch, userId);
    return BulkDecisionReport.fromWire(result);
  }

  Future<Specimen> retry(
    CollectionScope scope,
    Specimen specimen,
    String reason,
    String key,
  ) async {
    final epoch = _accessEpoch;
    final userId = expectedUserId?.call();
    await request(
      'POST',
      '${_root(scope)}/runs/${Uri.encodeComponent(specimen.data['active_run_id'])}/actions',
      key: key,
      body: {
        'expected_revision': specimen.revision,
        'action': 'retry',
        'reason': reason,
      },
    );
    _checkAccess(epoch, userId);
    return this.specimen(scope, specimen.id);
  }
}
