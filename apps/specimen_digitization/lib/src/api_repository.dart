import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';
import 'package:crypto/crypto.dart' as crypto;
import 'package:http/http.dart' as http;
import 'models.dart';
import 'sources.dart';
import 'vocabulary.dart';

/// How long the client waits for one exchange with the runtime API.
///
/// Elapsed time, not motion. No reviewer ever sees this duration, so it is a
/// named constant in the file that owns the policy rather than a motion token
/// (10 section 8, the fit amendment). One value covers the whole wire: the
/// sign in token refresh, the App Check token, every JSON request, the
/// evidence stream and the source photograph. A reviewer waiting on any of
/// them is waiting on the same collection service, and a wire that timed out
/// at seven different moments would report seven different waits for one
/// failure.
const Duration apiRequestTimeout = Duration(seconds: 30);

/// The search filters the API parses as UUIDs (`search.py`,
/// `SearchFilters.bounds`).
const Set<String> uuidFilters = {
  'specimen_id',
  'asset_id',
  'active_run_id',
  'batch_id',
};

/// [value] as the API writes a UUID, or null when it is not one.
///
/// Accepts the spellings Python's `uuid.UUID` accepts from a string: an
/// optional `urn:uuid:` prefix, optional braces and optional hyphens around
/// 32 hexadecimal digits, in either case. Surrounding space is ignored.
String? canonicalUuid(String value) {
  final hex = value
      .trim()
      .toLowerCase()
      .replaceAll('urn:', '')
      .replaceAll('uuid:', '')
      .replaceAll(RegExp(r'^[{}]+|[{}]+$'), '')
      .replaceAll('-', '');
  if (!RegExp(r'^[0-9a-f]{32}$').hasMatch(hex)) return null;
  return '${hex.substring(0, 8)}-${hex.substring(8, 12)}-'
      '${hex.substring(12, 16)}-${hex.substring(16, 20)}-${hex.substring(20)}';
}

class ApiSpecimenRepository
    implements SpecimenRepository, SourceRepository, AccessFailureSource {
  ApiSpecimenRepository({
    required this.baseUrl,
    required this.token,
    http.Client? client,
    this.expectedMode,
    this.appCheckToken,
    this.expectedUserId,
  }) : _client = client ?? http.Client() {
    if (baseUrl.host.isEmpty ||
        baseUrl.userInfo.isNotEmpty ||
        baseUrl.hasQuery ||
        baseUrl.hasFragment ||
        (baseUrl.scheme != 'https' &&
            !(baseUrl.scheme == 'http' &&
                [
                  'localhost',
                  '127.0.0.1',
                  '::1',
                  '10.0.2.2',
                ].contains(baseUrl.host)))) {
      throw const ApiFailure(
        'The API must use HTTPS. Local emulator hosts may use HTTP.',
        code: 'configuration',
      );
    }
  }
  final Future<String?> Function()? appCheckToken;
  final String? expectedMode;
  final String Function()? expectedUserId;
  final Uri baseUrl;
  final Future<String?> Function() token;
  final http.Client _client;
  @override
  String mode = 'production';
  @override
  List<dynamic> blockers = [];
  final _accessFailures = StreamController<ApiFailure>.broadcast(sync: true);
  ApiFailure? _accessFailure;
  int _accessEpoch = 0;
  bool _rechecking = false;
  bool _hasVerifiedSession = false;
  String? _verifiedUserId;
  @override
  Stream<ApiFailure> get accessFailures => _accessFailures.stream;
  bool _current(int epoch, String? userId) =>
      epoch == _accessEpoch && expectedUserId?.call() == userId;
  ApiFailure _deny(ApiFailure failure, int epoch, String? userId) {
    if (_current(epoch, userId) &&
        (failure.status == 401 || failure.status == 403) &&
        _accessFailure == null) {
      _accessFailure = failure;
      if (!_accessFailures.isClosed) _accessFailures.add(failure);
    }
    return failure;
  }

  void _checkAccess(int epoch, String? userId, {bool verification = false}) {
    if (!_current(epoch, userId)) {
      // An old response cannot restore access or revoke a newer session.
      throw const ApiFailure(
        'Collection access changed. Check access again.',
        code: 'access_changed',
        status: 403,
      );
    }
    if (!verification) {
      if (_accessFailure != null) throw _accessFailure!;
      if (_rechecking || (_hasVerifiedSession && _verifiedUserId != userId)) {
        throw const ApiFailure(
          'Collection access must be verified before continuing.',
          code: 'access_not_verified',
          status: 403,
        );
      }
    }
  }

  void close() {
    _client.close();
    _accessFailures.close();
  }

  String _root(CollectionScope scope) =>
      '/v1/organizations/${Uri.encodeComponent(scope.organizationId)}';
  Future<Map<String, String>> _credentials(
    int epoch,
    String? userId, {
    bool verification = false,
  }) async {
    _checkAccess(epoch, userId, verification: verification);
    String? bearer;
    try {
      bearer = await token().timeout(apiRequestTimeout);
    } catch (_) {
      throw _deny(
        const ApiFailure(
          'Your sign-in could not be refreshed. Check your connection or sign in again.',
          code: 'unauthenticated',
          status: 401,
        ),
        epoch,
        userId,
      );
    }
    if (bearer == null || bearer.isEmpty) {
      throw _deny(
        const ApiFailure(
          'Your session expired. Sign in again.',
          code: 'unauthenticated',
          status: 401,
        ),
        epoch,
        userId,
      );
    }
    String? check;
    if (appCheckToken != null || expectedMode == 'production') {
      try {
        check = await appCheckToken?.call().timeout(apiRequestTimeout);
      } catch (_) {
        throw _deny(
          const ApiFailure(
            'App verification could not be completed. Check your connection and retry. If it persists, ask your administrator to check App Check for this app.',
            code: 'app_check_unavailable',
            status: 403,
          ),
          epoch,
          userId,
        );
      }
      if (check == null || check.isEmpty) {
        throw _deny(
          const ApiFailure(
            'App verification is unavailable. Retry or contact your administrator. Collection access has not been verified.',
            code: 'app_check_unavailable',
            status: 403,
          ),
          epoch,
          userId,
        );
      }
    }
    _checkAccess(epoch, userId, verification: verification);
    return {'Authorization': 'Bearer $bearer', 'X-Firebase-AppCheck': ?check};
  }

  Future<Json> request(
    String method,
    String path, {
    Json? body,
    String? key,
    Map<String, String>? query,
    Uint8List? bytes,
    Map<String, String>? headers,
    int? verificationEpoch,
  }) async {
    final epoch = verificationEpoch ?? _accessEpoch;
    final userId = expectedUserId?.call();
    final uri = baseUrl.replace(
      path: '${baseUrl.path.replaceFirst(RegExp(r'/$'), '')}$path',
      queryParameters: query,
    );
    final request = http.Request(method, uri)..followRedirects = false;
    request.headers.addAll({
      ...await _credentials(
        epoch,
        userId,
        verification: verificationEpoch != null,
      ),
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
        await _client.send(request).timeout(apiRequestTimeout),
      ).timeout(apiRequestTimeout);
      _checkAccess(epoch, userId, verification: verificationEpoch != null);
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
          textOf(error['message'], 'The request did not complete. Retry.'),
          code: textOf(error['code'], 'request_failed'),
          status: response.statusCode,
          details: error['details'] is Map
              ? Map<String, dynamic>.from(error['details'])
              : const {},
        );
      }
      return result;
    } on ApiFailure catch (failure) {
      throw _deny(failure, epoch, userId);
    } on TimeoutException {
      throw const ApiFailure(
        'The request timed out. Retry to reconcile the saved server state.',
        code: 'timeout',
      );
    } on http.ClientException {
      throw const ApiFailure(
        'Connection interrupted. Retry to resume where the server stopped.',
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
      ArtifactKind.readingDeclarations => 'observations/$id/declarations',
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
      final result = await request('GET', path, query: query);
      if (artifact.kind == ArtifactKind.readingDeclarations) {
        final observation = specimen.observations
            .where(
              (o) =>
                  o['id'] == artifact.id || o['observation_id'] == artifact.id,
            )
            .firstOrNull;
        final model = result['model'];
        if (result['revision'] != specimen.revision ||
            result['run_id'] != specimen.data['active_run_id'] ||
            result['observation_id'] != artifact.id ||
            observation == null ||
            result['region_id'] != observation['region_id'] ||
            (model is Map &&
                model['raw_sha256'] != observation['raw_sha256'])) {
          throw const ApiFailure(
            'The declaration evidence does not match the current reading and version. Refresh evidence.',
            code: 'invalid_evidence',
          );
        }
      }
      return result;
    }
    final epoch = _accessEpoch;
    final userId = expectedUserId?.call();
    final req = http.Request(
      'GET',
      baseUrl.replace(
        path: '${baseUrl.path.replaceFirst(RegExp(r'/$'), '')}$path',
        queryParameters: query,
      ),
    )..followRedirects = false;
    req.headers.addAll({
      ...await _credentials(epoch, userId),
      'Accept': artifact.kind == ArtifactKind.activeGraph
          ? 'application/json'
          : 'text/plain',
    });
    try {
      return await (() async {
        final response = await _client.send(req);
        _checkAccess(epoch, userId);
        if (response.statusCode == 401 || response.statusCode == 403) {
          await response.stream.listen(null).cancel();
          throw _deny(
            ApiFailure(
              'Evidence access was denied. Check your account and collection access.',
              code: 'access_denied',
              status: response.statusCode,
            ),
            epoch,
            userId,
          );
        }
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
        _checkAccess(epoch, userId);
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
            'Raw evidence does not match the saved checksum. Refresh evidence.',
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
              'The complete graph does not match its saved scope, version or size. Refresh evidence.',
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
      })().timeout(apiRequestTimeout);
    } on ApiFailure catch (failure) {
      throw _deny(failure, epoch, userId);
    } on TimeoutException {
      throw const ApiFailure(
        'Evidence request timed out. Retry to read the same version.',
        code: 'timeout',
      );
    } on http.ClientException {
      throw const ApiFailure(
        'Evidence connection interrupted. Retry to read the same version.',
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
    final epoch = ++_accessEpoch;
    _images.clear();
    final userId = expectedUserId?.call();
    _rechecking = true;
    try {
      final result = await request(
        'GET',
        '/v1/session',
        verificationEpoch: epoch,
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
        'This search filter is not supported.',
        code: 'invalid_filter',
      );
    }
    // The API reads these four as UUIDs and answers anything else with 422
    // (`search.py`, `SearchFilters.bounds`). A value that is not a UUID names
    // no record, so the page is empty and nothing is asked (UI.md T1.6).
    final sent = Map<String, String>.of(filters);
    for (final key in uuidFilters) {
      final value = filters[key];
      if (value == null) continue;
      final id = canonicalUuid(value);
      if (id == null) return const SpecimenPage(<Specimen>[]);
      sent[key] = id;
    }
    final result = await request(
      'GET',
      '${_root(scope)}/specimens',
      query: {
        'collection_id': scope.collectionId,
        ...sent,
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

  @override
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

  @override
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

  Future<Specimen> _workspace(
    Json result,
    CollectionScope scope, {
    bool loadImage = true,
  }) async {
    final asset = result['asset'] is Map
        ? Map<String, dynamic>.from(result['asset'])
        : <String, dynamic>{};
    asset['asset_id'] = asset['id'];
    if (loadImage && asset['id'] != null && !_reuseImage(scope, asset)) {
      final epoch = _accessEpoch;
      final userId = expectedUserId?.call();
      try {
        final derivative = asset['view_derivative'] is Map;
        final uri = baseUrl.replace(
          queryParameters: derivative ? {'view': 'true'} : null,
          path:
              '${baseUrl.path.replaceFirst(RegExp(r'/$'), '')}${_root(scope)}/assets/${Uri.encodeComponent(asset['id'])}/content',
        );
        final req = http.Request('GET', uri)..followRedirects = false;
        req.headers.addAll(await _credentials(epoch, userId));
        final response = await http.Response.fromStream(
          await _client.send(req).timeout(apiRequestTimeout),
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
            _keepImage(scope, asset, response.bodyBytes, userId);
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
      // The regions whose readings differ and are not resolved. Unresolved
      // alone is not a difference: the pilot resolves nothing (UI.md T1.3).
      'disagreements': objects(
        result['transcriptions'],
      ).where((t) => t['resolved'] != true && readingsDiffer(t)).toList(),
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

  /// The photographs this session already downloaded, most recently used
  /// last (UI.md T1.5).
  ///
  /// The queue's poll reloads the open record every 20 seconds, and an
  /// original can be 25 MB. An asset never changes, so the same id and
  /// checksums are the same bytes. Reusing the same bytes also keeps the
  /// decoded image, which `Image.memory` keys on their identity. Every access
  /// check empties it, so it never outlives the session that fetched it.
  final Map<String, ({Uint8List bytes, String? userId})> _images = {};

  /// How many photographs [_images] keeps: the open record and the few a
  /// reviewer moves between.
  static const int _imageCacheEntries = 4;

  /// What identifies a photograph's bytes: the collection, the asset, the
  /// original's checksum and, for a view derivative, the derivative's.
  ///
  /// Null when a checksum is missing, or when a derivative does not name this
  /// original, so an unidentified or mismatched image is always fetched and
  /// checked again rather than reused.
  String? _imageKey(CollectionScope scope, Json asset) {
    final sha = asset['sha256'];
    if (sha is! String || sha.isEmpty) return null;
    final view = asset['view_derivative'];
    if (view is! Map) {
      return [scope.key, asset['id'], sha, 'original'].join(' ');
    }
    final viewSha = view['derivative_sha256'];
    if (view['original_sha256'] != sha ||
        viewSha is! String ||
        viewSha.isEmpty) {
      return null;
    }
    return [scope.key, asset['id'], sha, viewSha].join(' ');
  }

  /// Puts back on [asset] the photograph this session already accepted for
  /// it, and answers whether there was one.
  ///
  /// No request is made, so there is nothing to re-check: the workspace
  /// response that carried [asset] was itself authorised a moment ago.
  bool _reuseImage(CollectionScope scope, Json asset) {
    final key = _imageKey(scope, asset);
    final cached = key == null ? null : _images.remove(key);
    if (cached == null || cached.userId != expectedUserId?.call()) {
      return false;
    }
    // Put back last, so the photograph in use is the last one dropped.
    _images[key!] = cached;
    asset['preview_bytes'] = cached.bytes;
    asset['preview_is_derivative'] = asset['view_derivative'] is Map;
    return true;
  }

  /// Keeps the bytes just accepted for [asset], dropping the photograph used
  /// least recently. Bytes that were refused are never kept, so they are
  /// asked for again on the next load.
  void _keepImage(
    CollectionScope scope,
    Json asset,
    Uint8List bytes,
    String? userId,
  ) {
    final key = _imageKey(scope, asset);
    if (key == null) return;
    _images[key] = (bytes: bytes, userId: userId);
    while (_images.length > _imageCacheEntries) {
      _images.remove(_images.keys.first);
    }
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
        'The server check response does not match this image. No quality result is recorded.',
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

  @override
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

  @override
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
      if (!['pause', 'resume', 'cancel', 'reprocess'].contains(action)) {
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
              : {'confirmed': true},
          'evidence_ids': change['evidence_ids'] ?? [],
        },
      },
    );
    _checkAccess(epoch, userId);
    return this.specimen(scope, specimen.id);
  }

  @override
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

  @override
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

  @override
  Future<List<RegisteredSource>> sources(CollectionScope scope) async =>
      objects((await request('GET', '${_root(scope)}/sources'))['items'])
          .map(RegisteredSource.new)
          .where(
            (RegisteredSource source) =>
                source.collectionId == scope.collectionId,
          )
          .toList();

  @override
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

  @override
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
