part of 'api_repository.dart';

mixin _ApiRepositoryScopes on _ApiRepositoryBase {
  Future<List<CollectionScope>> scopes() async {
    final epoch = ++_accessEpoch;
    final userId = expectedUserId?.call();
    // A check that follows a refusal mints new tokens for its first request.
    // Reading the cache again would send the token that was just refused, or
    // repeat the read that just failed.
    final fresh = _accessFailure != null;
    _rechecking = true;
    try {
      final result = await request(
        'GET',
        '/v1/session',
        verificationEpoch: epoch,
        freshCredentials: fresh,
      );
      bool nonempty(dynamic value) =>
          value is String && value.trim().isNotEmpty;
      final rows = result['memberships'];
      if (!nonempty(result['user_id']) ||
          (expectedUserId != null &&
              (userId == null ||
                  userId.isEmpty ||
                  result['user_id'] != userId ||
                  expectedUserId!() != userId)) ||
          rows is! List ||
          rows.any(
            (row) =>
                row is! Map ||
                !nonempty(row['organization_id']) ||
                !nonempty(row['collection_id']) ||
                !nonempty(row['role']) ||
                (row['permissions'] != null &&
                    (row['permissions'] is! List ||
                        (row['permissions'] as List).any((p) => !nonempty(p)))),
          )) {
        throw const ApiFailure(
          'The server could not verify your account and collection roles. Sign in again or contact your administrator.',
          code: 'invalid_session',
          status: 403,
        );
      }
      mode = textOf(result['mode'], 'unsupported');
      blockers = result['runtime_blockers'] as List? ?? [];
      if (!['production', 'emulator', 'synthetic'].contains(mode) ||
          (expectedMode != null && mode != expectedMode)) {
        throw const ApiFailure(
          'The server environment does not match this build. Check configuration before continuing.',
          code: 'mode_mismatch',
        );
      }
      final memberships = objects(rows);
      final keys = <String>{};
      if (memberships.any(
        (m) => !keys.add('${m['organization_id']}/${m['collection_id']}'),
      )) {
        throw const ApiFailure(
          'The server returned conflicting collection roles. Ask your administrator.',
          code: 'invalid_session',
          status: 403,
        );
      }
      final collections = <String, Json>{};
      final catalogs = <String, List<CollectionCatalogNode>>{};
      for (final org
          in memberships.map((m) => m['organization_id'].toString()).toSet()) {
        final data = await request(
          'GET',
          '/v1/organizations/${Uri.encodeComponent(org)}/collections',
          verificationEpoch: epoch,
        );
        if (data['items'] is! List ||
            (data['items'] as List).any(
              (c) => c is! Map || !nonempty(c['collection_id']),
            )) {
          throw const ApiFailure(
            'Collection configuration could not be verified. Check access again.',
            code: 'invalid_collections',
            status: 403,
          );
        }
        for (final c in objects(data['items'])) {
          collections['$org/${c['collection_id']}'] = c;
        }
        catalogs[org] = _collectionCatalog(data, org);
      }
      if (memberships.any(
        (m) => !collections.containsKey(
          '${m['organization_id']}/${m['collection_id']}',
        ),
      )) {
        throw const ApiFailure(
          'An assigned collection is unavailable. Ask your administrator to check collection access.',
          code: 'invalid_collections',
          status: 403,
        );
      }
      final scopes = memberships
          .map(
            (m) => CollectionScope(
              organizationId: m['organization_id'].toString(),
              collectionId: m['collection_id'].toString(),
              name: textOf(
                collections['${m['organization_id']}/${m['collection_id']}']?['display_name'],
                m['collection_id'].toString(),
              ),
              configuration:
                  collections['${m['organization_id']}/${m['collection_id']}'] ??
                  {},
              permissions: [
                m['role'].toString(),
                ...(m['permissions'] as List? ?? []).map((p) => p.toString()),
              ],
              catalogNodes:
                  catalogs[m['organization_id'].toString()] ?? const [],
              defaultSelection:
                  collections['${m['organization_id']}/${m['collection_id']}']?['is_default'] ==
                  true,
            ),
          )
          .toList();
      _checkAccess(epoch, userId, verification: true);
      _verifiedUserId = userId;
      _hasVerifiedSession = true;
      _accessFailure = null;
      _rechecking = false;
      return scopes;
    } catch (_) {
      if (_current(epoch, userId)) {
        _rechecking = false;
        _deny(
          const ApiFailure(
            'Collection access could not be verified. Check access again.',
            code: 'access_not_verified',
            status: 403,
          ),
          epoch,
          userId,
        );
      }
      rethrow;
    }
  }

  /// Catalog relationships describe the chooser; they never create scopes.
  List<CollectionCatalogNode> _collectionCatalog(
    Json data,
    String organizationId,
  ) {
    final raw = data['hierarchy'];
    if (raw == null) return const [];
    bool named(Object? value) => value is String && value.trim().isNotEmpty;
    Never invalid() => throw const ApiFailure(
      'The collection hierarchy could not be verified. Check access again.',
      code: 'invalid_collections',
      status: 403,
    );
    if (raw is! List) invalid();
    final nodes = <String, CollectionCatalogNode>{};
    for (final row in raw) {
      if (row is! Map ||
          !named(row['collection_id']) ||
          !named(row['display_name']) ||
          (row['parent_collection_id'] != null &&
              !named(row['parent_collection_id'])) ||
          (row['organization_id'] != null &&
              row['organization_id'] != organizationId) ||
          (row['kind'] != null &&
              !['museum', 'testing'].contains(row['kind']))) {
        invalid();
      }
      final id = row['collection_id'] as String;
      if (nodes.containsKey(id)) invalid();
      nodes[id] = CollectionCatalogNode(
        collectionId: id,
        name: row['display_name'] as String,
        parentCollectionId: row['parent_collection_id'] as String?,
        testing: row['kind'] == 'testing',
      );
    }
    for (final node in nodes.values) {
      final seen = <String>{node.collectionId};
      var parent = node.parentCollectionId;
      while (parent != null) {
        if (!seen.add(parent) || !nodes.containsKey(parent)) invalid();
        parent = nodes[parent]!.parentCollectionId;
      }
    }
    return List.unmodifiable(nodes.values);
  }

  Future<List<Json>> profiles(CollectionScope scope) async =>
      objects((await request('GET', '${_root(scope)}/collections'))['items']);
  Future<List<Specimen>> specimens(
    CollectionScope scope, {
    String query = '',
    String status = '',
  }) async => (await specimenPage(
    scope,
    filters: {
      ...specimenSearchFilter(query),
      if (status.isNotEmpty)
        (['cleared', 'needs_human_review', 'deferred'].contains(status)
                ? 'disposition'
                : 'state'):
            status,
    },
  )).items;

  Future<SpecimenPage> specimenPage(
    CollectionScope scope, {
    Map<String, String> filters = const {},
    String? cursor,
  }) async {
    const allowed = {
      'specimen_id',
      'display_reference',
      'asset_id',
      'active_run_id',
      'batch_id',
      'uploader_id',
      'state',
      'stage',
      'disposition',
      'profile_id',
      'profile_version',
      'reason_code',
      'blocker',
      'created_from',
      'created_before',
      'risk_min',
      'risk_max',
    };
    if (filters.keys.any((key) => !allowed.contains(key))) {
      throw const ApiFailure(
        'This search filter is not supported.',
        code: 'invalid_filter',
      );
    }
    final result = await request(
      'GET',
      '${_root(scope)}/specimens',
      query: {
        'collection_id': scope.collectionId,
        ...filters,
        'limit': '50',
        'cursor': ?cursor,
      },
    );
    final next = result['next_cursor'];
    if (next != null && (next is! String || next.isEmpty || next == cursor)) {
      throw const ApiFailure(
        'This page link is out of date. Refresh the queue.',
        code: 'pagination',
      );
    }
    return SpecimenPage(
      objects(result['items']).map(Specimen.new).toList(),
      nextCursor: next as String?,
    );
  }

  Future<Specimen> _artifactSummary(
    CollectionScope scope,
    String id,
    ApiFailure failure, {
    bool historical = false,
  }) async {
    final epoch = _accessEpoch;
    final userId = expectedUserId?.call();
    final receipt = failure.details;
    final revision = receipt['revision'];
    final version = receipt['record_version_id'];
    final valid =
        revision is int &&
        revision > 0 &&
        version is String &&
        version.endsWith(':$revision') &&
        version.length > ':$revision'.length;
    if (!valid) throw failure;
    final runId = version.substring(0, version.lastIndexOf(':'));
    Json summary = {};
    String? summaryError;
    try {
      if (historical) {
        return Specimen({
          'specimen_id': id,
          'revision': revision,
          'active_run_id': runId,
          'record_version_id': version,
          'artifact_receipt': receipt,
          'available_actions': <String>[],
        });
      }
      summary = await request(
        'GET',
        '${_root(scope)}/specimens/${Uri.encodeComponent(id)}',
      );
      if (summary['specimen_id'] != id ||
          summary['organization_id'] != scope.organizationId ||
          summary['collection_id'] != scope.collectionId ||
          summary['revision'] != revision ||
          summary['record_version_id'] != version ||
          summary['active_run_id'] != runId) {
        throw const ApiFailure(
          'The current summary changed. Refresh to load its current version.',
          code: 'summary_changed',
        );
      }
    } catch (e) {
      if (e is ApiFailure &&
          (e.status == 401 || e.status == 403 || e.code == 'access_changed')) {
        rethrow;
      }
      summary = {};
      summaryError = e is ApiFailure
          ? e.message
          : 'Summary unavailable. Refresh to check current access and version.';
    }
    _checkAccess(epoch, userId);
    return Specimen({
      ...summary,
      'specimen_id': id,
      'revision': revision,
      'active_run_id': runId,
      'latest_record_version_id': version,
      'artifact_receipt': receipt,
      'artifact_summary_error': ?summaryError,
      // A receipt alone grants no actions; only a matching authenticated summary does.
      'available_actions': summary['available_actions'] ?? <String>[],
    });
  }

  Future<Specimen> specimen(CollectionScope scope, String id) async {
    final epoch = _accessEpoch;
    final userId = expectedUserId?.call();
    try {
      final result = await request(
        'GET',
        '${_root(scope)}/specimens/${Uri.encodeComponent(id)}/workspace',
      );
      _checkAccess(epoch, userId);
      return _workspace(result, scope);
    } on ApiFailure catch (e) {
      if (!e.artifactRequired) rethrow;
      _checkAccess(epoch, userId);
      return _artifactSummary(scope, id, e);
    }
  }

  Future<Specimen> _workspace(
    Json result,
    CollectionScope scope, {
    bool loadImage = true,
  }) async {
    final asset = result['asset'] is Map
        ? Map<String, dynamic>.from(result['asset'])
        : <String, dynamic>{};
    asset['asset_id'] = asset['id'];
    if (loadImage && asset['id'] != null) {
      final epoch = _accessEpoch;
      final userId = expectedUserId?.call();
      try {
        final derivative = asset['view_derivative'] is Map;
        final uri = baseUrl.replace(
          queryParameters: derivative ? {'view': 'true'} : null,
          path:
              '${baseUrl.path.replaceFirst(RegExp(r'/$'), '')}${_root(scope)}/assets/${Uri.encodeComponent(asset['id'])}/content',
        );
        http.Request build(Map<String, String> credentials) =>
            http.Request('GET', uri)
              ..followRedirects = false
              ..headers.addAll(credentials);
        final response = await http.Response.fromStream(
          await _send(build, await _credentials(epoch, userId), epoch, userId),
        ).timeout(apiRequestTimeout);
        _checkAccess(epoch, userId);
        if (response.statusCode == 401 || response.statusCode == 403) {
          throw _deny(
            ApiFailure(
              'Source image access was denied. Check your account and collection access.',
              code: 'access_denied',
              status: response.statusCode,
            ),
            epoch,
            userId,
          );
        }
        if (response.statusCode == 200) {
          final derivativeInfo = derivative
              ? Map<String, dynamic>.from(asset['view_derivative'])
              : <String, dynamic>{};
          if (derivative &&
              (derivativeInfo['original_sha256'] != asset['sha256'] ||
                  crypto.sha256.convert(response.bodyBytes).toString() !=
                      derivativeInfo['derivative_sha256'])) {
            asset['preview_error'] =
                'Preview does not match retained source provenance. Refresh evidence.';
          } else {
            asset['preview_bytes'] = response.bodyBytes;
            asset['preview_is_derivative'] = derivative;
          }
        } else {
          asset['preview_error'] =
              'Source image access is unavailable. Refresh or check collection permissions.';
        }
      } on ApiFailure catch (failure) {
        if (failure.status == 401 || failure.status == 403) {
          throw _deny(failure, epoch, userId);
        }
        asset['preview_error'] = failure.message;
      } catch (_) {
        asset['preview_error'] = 'Image request interrupted. Refresh to retry.';
      }
      _checkAccess(epoch, userId);
    }
    final run = result['run'] is Map
        ? Map<String, dynamic>.from(result['run'])
        : <String, dynamic>{};
    final fieldMap = result['fields'] is Map
        ? Map<String, dynamic>.from(result['fields'])
        : <String, dynamic>{};
    return Specimen({
      ...result,
      'assets': asset.isEmpty ? <Json>[] : [asset],
      'latest_record_version_id': result['record_version_id'],
      'fields': fieldMap.entries.map((e) {
        final f = Map<String, dynamic>.from(e.value);
        final state = f['value_state'] ?? f['state'];
        final resolvedValue = state == 'supported'
            ? f['normalized'] ?? f['parsed'] ?? f['literal']
            : null;
        return <String, dynamic>{
          ...f,
          'field_key': e.key,
          'display_name': vocabularyLabel(e.key),
          'required':
              run['profile_snapshot'] is Map &&
                  run['profile_snapshot']['mandatory_fields'] is List
              ? (run['profile_snapshot']['mandatory_fields'] as List).contains(
                  e.key,
                )
              : true,
          'state': state,
          'literal_value': f['literal'],
          'parsed_value': f['parsed'],
          'resolved_value': resolvedValue,
        };
      }).toList(),
      'validation_findings': [
        ...objects(result['validations']),
        // Run findings are retained context, not clearance gates. Keep their
        // severity so field disclosures can explain how a value was settled.
        ...objects(run['findings']).where(
          (finding) => const {'warning', 'info'}.contains(finding['severity']),
        ),
      ],
      'audit_events': objects(
        result['events'],
      ).map((e) => <String, dynamic>{...e, 'actor_id': e['actor']}).toList(),
      'disagreements': objects(result['transcriptions'])
          .where(
            (t) =>
                t['resolved'] != true ||
                (t['alternatives'] as List? ?? []).length > 1,
          )
          .toList(),
      'evidence': [
        ...objects(result['evidence']),
        ...objects(run['lookups']).map(
          (l) => <String, dynamic>{
            ...l,
            'source': l['provider'],
            'outcome': l['status'],
            'evidence_id': l['id'],
            // A lookup run is available to inspect, but its ID is not a
            // retained Evidence ID accepted by field correction.
            'field_citation_supported': false,
          },
        ),
      ],
    });
  }

  String _costRoot(String organizationId) =>
      '/v1/organizations/${Uri.encodeComponent(organizationId)}/costs';

  Future<CostReport> costs(
    String organizationId, {
    required String from,
    required String to,
  }) async {
    final Json body = await request(
      'GET',
      _costRoot(organizationId),
      query: <String, String>{'from': from, 'to': to},
    );
    // Reads every field defensively and refuses what is not a report with an
    // `ApiFailure`, so a body of the wrong shape ends as a message on screen.
    return CostReport.fromWire(body);
  }

  Future<bool> refreshCosts(String organizationId) async {
    final Json result = await request(
      'POST',
      '${_costRoot(organizationId)}/refresh',
    );
    return result['started'] == true;
  }

  Future<void> setCostLimit(
    String organizationId, {
    String? collectionId,
    int? micros,
  }) async {
    await request(
      'PUT',
      '${_costRoot(organizationId)}/caps',
      body: <String, dynamic>{
        'collection_id': collectionId,
        'monthly_cap_micros': micros,
      },
    );
  }
}
