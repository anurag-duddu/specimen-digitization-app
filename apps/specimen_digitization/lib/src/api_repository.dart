import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';
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
      request.headers['Content-Type'] = 'application/octet-stream';
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
  }) async {
    final results = <Specimen>[];
    String? cursor;
    final seen = <String>{};
    do {
      final result = await request(
        'GET',
        '${_root(scope)}/specimens',
        query: {
          'collection_id': scope.collectionId,
          if (query.isNotEmpty) 'q': query,
          if (status.isNotEmpty)
            (['cleared', 'needs_human_review', 'deferred'].contains(status)
                    ? 'disposition'
                    : 'state'):
                status,
          'cursor': ?cursor,
        },
      );
      results.addAll(objects(result['items']).map(Specimen.new));
      cursor = result['next_cursor'] as String?;
      if (cursor != null && !seen.add(cursor)) {
        throw const ApiFailure(
          'The server repeated a page cursor. Refresh the queue.',
          code: 'pagination',
        );
      }
    } while (cursor != null);
    return results
        .where(
          (s) =>
              query.isEmpty ||
              [
                s.id,
                s.title,
                s.data['batch_id'],
                s.data['profile_version'],
                s.data['reason_codes'],
              ].join(' ').toLowerCase().contains(query.toLowerCase()),
        )
        .toList();
  }

  @override
  Future<Specimen> specimen(CollectionScope scope, String id) async {
    final result = await request(
      'GET',
      '${_root(scope)}/specimens/${Uri.encodeComponent(id)}/workspace',
    );
    return _workspace(result, scope);
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
    final result = await request(
      'GET',
      '${_root(scope)}/specimens/${Uri.encodeComponent(id)}/history/$revision',
      query: {'run_id': ?runId, 'run_sha256': ?runSha256},
    );
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
        final uri = baseUrl.replace(
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
          asset['preview_bytes'] = response.bodyBytes;
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
          'required': true,
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
  Future<Json> createIntake(
    CollectionScope scope,
    IntakeFile file,
    String key,
  ) async {
    if (file.width == null || file.height == null) {
      throw const ApiFailure(
        'This format cannot be decoded on this device. Retain the original and use a supported intake workstation.',
        code: 'decoder_unavailable',
      );
    }
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
        'width': file.width,
        'height': file.height,
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
    final kind = change['kind'];
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
        if (path == 'classification') 'collection_id': change['value'],
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
