import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';
import 'package:crypto/crypto.dart' as crypto;
import 'package:http/http.dart' as http;
import 'models.dart';

class ApiSpecimenRepository implements SpecimenRepository {
  ApiSpecimenRepository({
    required this.baseUrl,
    required this.token,
    http.Client? client,
    this.expectedMode,
    this.appCheckToken,
  }) : _client = client ?? http.Client() {
    if (baseUrl.scheme != 'https' &&
        !(baseUrl.scheme == 'http' &&
            [
              'localhost',
              '127.0.0.1',
              '::1',
              '10.0.2.2',
            ].contains(baseUrl.host))) {
      throw const ApiFailure(
        'The API must use HTTPS. Local emulator hosts may use HTTP.',
        code: 'configuration',
      );
    }
  }
  final Future<String?> Function()? appCheckToken;
  final String? expectedMode;
  final Uri baseUrl;
  final Future<String?> Function() token;
  final http.Client _client;
  @override
  String mode = 'production';
  @override
  List<dynamic> blockers = [];
  void close() => _client.close();
  String _root(CollectionScope scope) =>
      '/v1/organizations/${Uri.encodeComponent(scope.organizationId)}';
  Future<Json> request(
    String method,
    String path, {
    Json? body,
    String? key,
    Map<String, String>? query,
    Uint8List? bytes,
    Map<String, String>? headers,
  }) async {
    final bearer = await token();
    if (bearer == null || bearer.isEmpty) {
      throw const ApiFailure(
        'Your session expired. Sign in again.',
        code: 'unauthenticated',
        status: 401,
      );
    }
    final uri = baseUrl.replace(
      path: '${baseUrl.path.replaceFirst(RegExp(r'/$'), '')}$path',
      queryParameters: query,
    );
    final request = http.Request(method, uri)..followRedirects = false;
    final check = await appCheckToken?.call();
    request.headers.addAll({
      'X-Firebase-AppCheck': ?check,
      'Authorization': 'Bearer $bearer',
      'Accept': 'application/json',
      'Idempotency-Key': ?key,
      ...?headers,
    });
    if (bytes != null) {
      request.bodyBytes = bytes;
      request.headers['Content-Type'] =
          headers?['Content-Type'] ?? 'application/octet-stream';
    } else if (body != null) {
      request.headers['Content-Type'] = 'application/json';
      request.body = jsonEncode(body);
    }
    try {
      final response = await http.Response.fromStream(
        await _client.send(request).timeout(const Duration(seconds: 30)),
      ).timeout(const Duration(seconds: 30));
      Json result = {};
      try {
        if (response.body.isNotEmpty) {
          result = Map<String, dynamic>.from(jsonDecode(response.body) as Map);
        }
      } catch (_) {
        throw ApiFailure(
          'The service returned an unreadable response. Retry or contact your administrator.',
          code: 'invalid_response',
          status: response.statusCode,
        );
      }
      if (response.statusCode < 200 || response.statusCode >= 300) {
        final error = result['error'] is Map
            ? Map<String, dynamic>.from(result['error'])
            : <String, dynamic>{};
        throw ApiFailure(
          textOf(error['message'], 'The request failed. Please retry.'),
          code: textOf(error['code'], 'request_failed'),
          status: response.statusCode,
          details: error['details'] is Map
              ? Map<String, dynamic>.from(error['details'])
              : const {},
        );
      }
      return result;
    } on TimeoutException {
      throw const ApiFailure(
        'The request timed out. Retry to reconcile the saved server state.',
        code: 'timeout',
      );
    } on http.ClientException {
      throw const ApiFailure(
        'Connection interrupted. Retry to resume from the server checkpoint.',
        code: 'network',
      );
    }
  }

  @override
  Future<Json> artifact(
    CollectionScope scope,
    Specimen specimen,
    ArtifactRequest artifact,
  ) async {
    if (specimen.revision < 1 || artifact.id.isEmpty) {
      throw const ApiFailure(
        'Refresh the specimen before reading evidence.',
        code: 'invalid_evidence',
      );
    }
    if (artifact.kind == ArtifactKind.activeGraph) {
      final receipt = specimen.data['artifact_receipt'];
      final size = receipt is Map ? receipt['artifact_size_bytes'] : null;
      if (receipt is! Map ||
          size is! int ||
          size < 1 ||
          size > 16777216 ||
          artifact.sha256 != receipt['artifact_sha256'] ||
          !RegExp(r'^[a-f0-9]{64}$').hasMatch(artifact.sha256 ?? '')) {
        throw const ApiFailure(
          'The complete graph reference is unavailable or exceeds the 16 MiB retrieval limit. Refresh the current record.',
          code: 'invalid_evidence',
        );
      }
    }
    final id = Uri.encodeComponent(artifact.id);
    final suffix = switch (artifact.kind) {
      ArtifactKind.activeGraph => 'active-graph',
      ArtifactKind.phase => 'phases/$id',
      ArtifactKind.authority => 'authority-results/$id',
      ArtifactKind.authorityRaw => 'authority-results/$id/raw',
      ArtifactKind.disagreement => 'disagreements/$id',
      ArtifactKind.observationRaw => 'observations/$id/raw',
      ArtifactKind.readingMetadata => 'observations/$id/metadata',
    };
    final path =
        '${_root(scope)}/specimens/${Uri.encodeComponent(specimen.id)}/$suffix';
    final query = {
      'revision': '${specimen.revision}',
      'field_key': ?artifact.fieldKey,
    };
    if (![
      ArtifactKind.activeGraph,
      ArtifactKind.authorityRaw,
      ArtifactKind.observationRaw,
    ].contains(artifact.kind)) {
      return request('GET', path, query: query);
    }
    final bearer = await token();
    if (bearer == null || bearer.isEmpty) {
      throw const ApiFailure(
        'Your session expired. Sign in again.',
        code: 'unauthenticated',
        status: 401,
      );
    }
    final req = http.Request(
      'GET',
      baseUrl.replace(
        path: '${baseUrl.path.replaceFirst(RegExp(r'/$'), '')}$path',
        queryParameters: query,
      ),
    )..followRedirects = false;
    final check = await appCheckToken?.call();
    req.headers.addAll({
      'Authorization': 'Bearer $bearer',
      'X-Firebase-AppCheck': ?check,
      'Accept': artifact.kind == ArtifactKind.activeGraph
          ? 'application/json'
          : 'text/plain',
    });
    try {
      return await (() async {
        final response = await _client.send(req);
        final graph = artifact.kind == ArtifactKind.activeGraph;
        final limit = graph ? 16777216 : 1048576;
        final bytes = BytesBuilder(copy: false);
        await for (final chunk in response.stream) {
          if (bytes.length + chunk.length > limit) {
            throw ApiFailure(
              graph
                  ? 'The complete graph exceeds the 16 MiB retrieval limit. No partial evidence is shown. Current summary and run controls remain available.'
                  : 'Raw evidence exceeds the 1 MiB display limit. No partial response is shown.',
              code: 'evidence_limit',
            );
          }
          bytes.add(chunk);
        }
        final data = bytes.takeBytes();
        if (response.statusCode != 200) {
          throw ApiFailure(
            'Raw evidence is unavailable. Refresh or check current collection access.',
            code: 'evidence_access',
            status: response.statusCode,
          );
        }
        final digest = crypto.sha256.convert(data).toString();
        if (artifact.sha256 == null || digest != artifact.sha256) {
          throw const ApiFailure(
            'Raw evidence does not match the retained digest. Refresh evidence.',
            code: 'evidence_digest',
          );
        }
        if (graph) {
          final receipt = specimen.data['artifact_receipt'] as Map? ?? const {};
          final decoded = jsonDecode(utf8.decode(data));
          if (data.length != receipt['artifact_size_bytes'] ||
              response.headers['x-content-sha256'] != digest ||
              response.headers['x-specimen-revision'] !=
                  '${specimen.revision}' ||
              decoded is! Map ||
              decoded['contract_version'] != 'active-run-v1' ||
              decoded['specimen_id'] != specimen.id ||
              decoded['revision'] != specimen.revision ||
              decoded['scope'] is! Map ||
              decoded['scope']['organization_id'] != scope.organizationId ||
              decoded['scope']['collection_id'] != scope.collectionId ||
              decoded['run'] is! Map ||
              decoded['run']['id'] != specimen.data['active_run_id']) {
            throw const ApiFailure(
              'The complete graph does not match its retained scope, revision or size. Refresh evidence.',
              code: 'invalid_evidence',
            );
          }
          return Map<String, dynamic>.from(decoded);
        }
        return <String, dynamic>{
          'text': utf8.decode(data),
          'sha256': digest,
          'size_bytes': data.length,
        };
      })().timeout(const Duration(seconds: 30));
    } on TimeoutException {
      throw const ApiFailure(
        'Evidence request timed out. Retry to read the same revision.',
        code: 'timeout',
      );
    } on http.ClientException {
      throw const ApiFailure(
        'Evidence connection interrupted. Retry to read the same revision.',
        code: 'network',
      );
    } on FormatException {
      throw const ApiFailure(
        'Raw evidence is not valid UTF-8 text.',
        code: 'invalid_evidence',
      );
    }
  }

  @override
  Future<List<CollectionScope>> scopes() async {
    final result = await request('GET', '/v1/session');
    mode = textOf(result['mode'], 'unsupported');
    blockers = result['runtime_blockers'] as List? ?? [];
    if (!['production', 'emulator', 'synthetic'].contains(mode) ||
        (expectedMode != null && mode != expectedMode)) {
      throw const ApiFailure(
        'The server environment does not match this build. Check configuration before continuing.',
        code: 'mode_mismatch',
      );
    }
    final memberships = objects(result['memberships']);
    final collections = <String, Json>{};
    for (final org
        in memberships.map((m) => m['organization_id'].toString()).toSet()) {
      final data = await request(
        'GET',
        '/v1/organizations/${Uri.encodeComponent(org)}/collections',
      );
      for (final c in objects(data['items'])) {
        collections['$org/${c['collection_id']}'] = c;
      }
    }
    return memberships
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
          ),
        )
        .toList();
  }

  @override
  Future<List<Json>> profiles(CollectionScope scope) async =>
      objects((await request('GET', '${_root(scope)}/collections'))['items']);
  @override
  Future<List<Specimen>> specimens(
    CollectionScope scope, {
    String query = '',
    String status = '',
  }) async => (await specimenPage(
    scope,
    filters: {
      if (query.isNotEmpty) 'specimen_id': query,
      if (status.isNotEmpty)
        (['cleared', 'needs_human_review', 'deferred'].contains(status)
                ? 'disposition'
                : 'state'):
            status,
    },
  )).items;

  @override
  Future<SpecimenPage> specimenPage(
    CollectionScope scope, {
    Map<String, String> filters = const {},
    String? cursor,
  }) async {
    const allowed = {
      'specimen_id',
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
        'Unsupported search filter.',
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
        'Invalid page cursor. Refresh the queue.',
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
          'The current summary changed. Refresh to load its current revision.',
          code: 'summary_changed',
        );
      }
    } catch (e) {
      summary = {};
      summaryError = e is ApiFailure
          ? e.message
          : 'Summary unavailable. Refresh to check current access and revision.';
    }
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

  @override
  Future<Specimen> specimen(CollectionScope scope, String id) async {
    try {
      final result = await request(
        'GET',
        '${_root(scope)}/specimens/${Uri.encodeComponent(id)}/workspace',
      );
      return _workspace(result, scope);
    } on ApiFailure catch (e) {
      if (!e.artifactRequired) rethrow;
      return _artifactSummary(scope, id, e);
    }
  }

  @override
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
        'Choose a valid history revision range.',
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
        'The history page could not be verified. Retry or contact your administrator.',
        code: 'invalid_history_page',
      );
    }
    return HistoryPage(
      items: items,
      throughRevision: throughRevision,
      nextCursor: next as int?,
    );
  }

  @override
  Future<Specimen> historicalSpecimen(
    CollectionScope scope,
    String id,
    int revision, {
    String? runId,
    String? runSha256,
  }) async {
    if (revision < 1) {
      throw const ApiFailure(
        'Choose a retained record revision.',
        code: 'invalid_revision',
      );
    }
    if ((runId == null) != (runSha256 == null) ||
        (runId != null && runId.isEmpty) ||
        (runSha256 != null && !RegExp(r'^[a-f0-9]{64}$').hasMatch(runSha256))) {
      throw const ApiFailure(
        'The prior run reference is invalid.',
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
      return _artifactSummary(scope, id, e, historical: true);
    }
    if (result['specimen_id'] != id || result['revision'] != revision) {
      throw const ApiFailure(
        'The returned historical record does not match the requested revision.',
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
      try {
        final bearer = await token();
        final derivative = asset['view_derivative'] is Map;
        final uri = baseUrl.replace(
          queryParameters: derivative ? {'view': 'true'} : null,
          path:
              '${baseUrl.path.replaceFirst(RegExp(r'/$'), '')}${_root(scope)}/assets/${Uri.encodeComponent(asset['id'])}/content',
        );
        final req = http.Request('GET', uri)..followRedirects = false;
        req.headers['Authorization'] = 'Bearer $bearer';
        final check = await appCheckToken?.call();
        if (check != null) req.headers['X-Firebase-AppCheck'] = check;
        final response = await http.Response.fromStream(
          await _client.send(req).timeout(const Duration(seconds: 30)),
        ).timeout(const Duration(seconds: 30));
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
      } catch (_) {
        asset['preview_error'] = 'Image request interrupted. Refresh to retry.';
      }
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
        return <String, dynamic>{
          ...f,
          'field_key': e.key,
          'display_name': labelOf(e.key),
          'required':
              run['profile_snapshot'] is Map &&
                  run['profile_snapshot']['mandatory_fields'] is List
              ? (run['profile_snapshot']['mandatory_fields'] as List).contains(
                  e.key,
                )
              : true,
          'state': f['value_state'] ?? f['state'],
          'literal_value': f['literal'],
          'parsed_value': f['parsed'],
          'resolved_value': f['normalized'] ?? f['parsed'] ?? f['literal'],
        };
      }).toList(),
      'validation_findings': objects(result['validations']),
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
          },
        ),
      ],
    });
  }

  @override
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
        'Preflight response does not match this image. No quality acceptance is inferred.',
        code: 'invalid_preflight',
      );
    }
    return result;
  }

  @override
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
    final batch = await request(
      'POST',
      '${_root(scope)}/batches',
      key: '${scope.collectionId}-$key-batch',
      body: {
        'collection_id': scope.collectionId,
        'display_name': 'Image intake',
        'acquisition_method': file.method,
      },
    );
    return request(
      'POST',
      '${_root(scope)}/batches/${batch['batch_id']}/items',
      key: '${scope.collectionId}-$key',
      body: {
        'client_item_id': file.sha256,
        'filename': file.name,
        'media_type': file.mimeType,
        'size_bytes': file.bytes.length,
        if (!serverCoordinates && file.width != null) 'width': file.width,
        if (!serverCoordinates && file.height != null) 'height': file.height,
        'sha256': file.sha256,
      },
    );
  }

  @override
  Future<Json> resumeIntake(CollectionScope scope, String id) =>
      request('GET', '${_root(scope)}/uploads/${Uri.encodeComponent(id)}');
  @override
  Future<void> upload(
    CollectionScope scope,
    Json session,
    IntakeFile file,
    void Function(double) progress,
  ) async {
    var state = await resumeIntake(scope, session['upload_id']);
    var offset = (state['offset'] as num?)?.toInt() ?? 0;
    if (offset < 0 || offset > file.bytes.length) {
      throw const ApiFailure(
        'Server upload offset is invalid. Contact your administrator.',
        code: 'offset',
      );
    }
    const chunkSize = 1024 * 1024;
    while (offset < file.bytes.length) {
      final end = (offset + chunkSize).clamp(0, file.bytes.length);
      state = await request(
        'PUT',
        '${_root(scope)}/uploads/${Uri.encodeComponent(session['upload_id'])}/content',
        key: 'chunk-${session['upload_id']}-$offset',
        headers: {'Upload-Offset': '$offset'},
        bytes: Uint8List.sublistView(file.bytes, offset, end),
      );
      final next = (state['offset'] as num?)?.toInt();
      if (next == null || next <= offset || next > file.bytes.length) {
        throw const ApiFailure(
          'The upload did not advance. Retry to reconcile its server offset.',
          code: 'offset',
        );
      }
      offset = next;
      progress(offset / file.bytes.length);
    }
  }

  @override
  Future<Json> completeIntake(
    CollectionScope scope,
    String id,
    String key,
  ) async {
    final current = await resumeIntake(scope, id);
    return request(
      'POST',
      '${_root(scope)}/uploads/${Uri.encodeComponent(id)}/complete',
      key: key,
      body: {'expected_revision': current['revision']},
    );
  }

  @override
  Future<Specimen> review(
    CollectionScope scope,
    Specimen specimen,
    Json change,
    String key,
  ) async {
    try {
      final result = await _review(scope, specimen, change, key);
      if (result.data['artifact_receipt'] is Map) {
        return Specimen({...result.data, 'mutation_saved': true});
      }
      return result;
    } on ApiFailure catch (e) {
      if (!e.artifactRequired || e.details['mutation_committed'] != true) {
        rethrow;
      }
      final result = await _artifactSummary(scope, specimen.id, e);
      return Specimen({...result.data, 'mutation_saved': true});
    }
  }

  Future<Specimen> _review(
    CollectionScope scope,
    Specimen specimen,
    Json change,
    String key,
  ) async {
    final kind = change['kind'];
    if (kind == 'run_action') {
      final action = change['action'];
      if (!['pause', 'resume', 'cancel', 'reprocess'].contains(action)) {
        throw const ApiFailure(
          'Unsupported run action.',
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
              : kind == 'authority_resolution'
              ? {
                  'tool_id': change['tool_id'],
                  'identifier': change['identifier'],
                  'field_key': change['target_id'],
                }
              : {'confirmed': true},
          'evidence_ids': change['evidence_ids'] ?? [],
        },
      },
    );
    return this.specimen(scope, specimen.id);
  }

  @override
  Future<Specimen> retry(
    CollectionScope scope,
    Specimen specimen,
    String reason,
    String key,
  ) async {
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
    return this.specimen(scope, specimen.id);
  }
}
