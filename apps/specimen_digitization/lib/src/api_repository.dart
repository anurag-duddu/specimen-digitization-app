import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';
import 'package:crypto/crypto.dart' as crypto;
import 'package:http/http.dart' as http;
import 'costs.dart';
import 'models.dart';
import 'sources.dart';
import 'vocabulary.dart';
import 'screens/intake/bulk_intake_repository.dart';

part 'api_repository_scopes.dart';
part 'api_repository_intake.dart';
part 'api_repository_review.dart';
part 'api_repository_sources.dart';

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

/// HTTP, auth, credentials, and session state shared by domain mixins.
///
/// Library-private. Callers construct [ApiSpecimenRepository]; this base exists
/// so those mixins can share private wire helpers without a circular hierarchy.
class _ApiRepositoryBase {
  _ApiRepositoryBase({
    required this.baseUrl,
    required this.token,
    http.Client? client,
    this.expectedMode,
    this.appCheckToken,
    this.expectedUserId,
    this.freshToken,
    this.freshAppCheckToken,
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

  /// Mints a new sign-in token rather than reading the cached one. Without it
  /// the sign-in token is read once per request, and a refusal stands.
  final Future<String?> Function()? freshToken;

  /// Mints a new App Check token rather than reading the cached one. Without
  /// it the App Check token is read once per request, and a refusal stands.
  final Future<String?> Function()? freshAppCheckToken;
  final http.Client _client;
  String mode = 'production';
  List<dynamic> blockers = [];
  final _accessFailures = StreamController<ApiFailure>.broadcast(sync: true);
  ApiFailure? _accessFailure;
  int _accessEpoch = 0;
  bool _rechecking = false;
  bool _hasVerifiedSession = false;
  String? _verifiedUserId;
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
          "This account's access has not been checked yet. Check access again.",
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

  /// Reads one token. A token that can be minted gets one second attempt
  /// before the read counts as a failure.
  ///
  /// Normally the cached token is read first, and a new one is minted only
  /// when that read throws or comes back empty. With [fresh], a new token is
  /// minted first and the cached read is the fallback, because App Check on
  /// the web throws from a forced refresh it cannot finish even while it still
  /// holds a valid token. Both attempts share one [apiRequestTimeout], so a
  /// source that hangs is not waited on twice.
  static Future<String?> _readToken(
    Future<String?> Function() cached,
    Future<String?> Function()? minted, {
    required bool fresh,
  }) async {
    if (minted == null) return cached().timeout(apiRequestTimeout);
    final first = fresh ? minted : cached;
    final second = fresh ? cached : minted;
    final elapsed = Stopwatch()..start();
    try {
      final value = await first().timeout(apiRequestTimeout);
      if (value != null && value.isNotEmpty) return value;
    } catch (_) {
      // The second attempt decides.
    }
    return second().timeout(apiRequestTimeout - elapsed.elapsed);
  }

  /// The headers that prove who is asking and from which app.
  ///
  /// [fresh] mints new tokens instead of reading the cached ones: the server
  /// refused the cached ones, or an access check follows a refusal.
  Future<Map<String, String>> _credentials(
    int epoch,
    String? userId, {
    bool verification = false,
    bool fresh = false,
  }) async {
    _checkAccess(epoch, userId, verification: verification);
    String? bearer;
    try {
      bearer = await _readToken(token, freshToken, fresh: fresh);
    } catch (_) {
      throw _deny(
        const ApiFailure(
          'The sign-in could not be refreshed. Check the connection, or sign in again.',
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
          'The session expired. Sign in again.',
          code: 'unauthenticated',
          status: 401,
        ),
        epoch,
        userId,
      );
    }
    String? check;
    final appCheck = appCheckToken;
    if (appCheck != null || expectedMode == 'production') {
      try {
        check = appCheck == null
            ? null
            : await _readToken(appCheck, freshAppCheckToken, fresh: fresh);
      } catch (_) {
        // Both attempts failed inside this window. On the web the App Check
        // SDK keeps a failed exchange's backoff in page memory. Until it runs
        // out (a full day after a 403) or the page reloads, every exchange
        // fails without a request.
        throw _deny(
          const ApiFailure(
            'App verification stopped before collection access was checked. Reload or reopen the app to start it again.',
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
            'App verification is unavailable. Reload the app, or ask an administrator to check App Check.',
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

  /// Sends a request, and sends a refused read once more on credentials read
  /// afresh.
  ///
  /// [credentials] are the ones the caller read for the first send, so a
  /// failure to read them stays outside the caller's refusal handling. On the
  /// web the App Check SDK does not refresh ahead of expiry, and it stamps a
  /// token's expiry when the exchange answers, after the server issued it. In
  /// the last moments of a token's life it can hand out one the API already
  /// refuses with 403. So a GET refused once is sent again on credentials
  /// read with `fresh`: each token that can be minted is minted, and one whose
  /// mint throws falls back to its cached token. What reaches [_deny] is the
  /// answer to that second send, or a failure to read its credentials. Writes
  /// are never resent here, nor is a send whose tokens were [minted] already,
  /// nor one from a repository that has nothing to mint with.
  Future<http.StreamedResponse> _send(
    http.BaseRequest Function(Map<String, String> credentials) build,
    Map<String, String> credentials,
    int epoch,
    String? userId, {
    bool verification = false,
    bool minted = false,
  }) async {
    final first = build(credentials);
    final response = await _client.send(first).timeout(apiRequestTimeout);
    if (minted ||
        (freshToken == null && freshAppCheckToken == null) ||
        first.method != 'GET' ||
        (response.statusCode != 401 && response.statusCode != 403)) {
      return response;
    }
    await response.stream.drain<void>().timeout(apiRequestTimeout);
    final renewed = await _credentials(
      epoch,
      userId,
      verification: verification,
      fresh: true,
    );
    return _client.send(build(renewed)).timeout(apiRequestTimeout);
  }

  /// Sends one JSON request to the API.
  ///
  /// [freshCredentials] mints new tokens for the first send. The access check
  /// sets it when it follows a refusal.
  Future<Json> request(
    String method,
    String path, {
    Json? body,
    String? key,
    Map<String, String>? query,
    Uint8List? bytes,
    Map<String, String>? headers,
    int? verificationEpoch,
    bool freshCredentials = false,
  }) async {
    final epoch = verificationEpoch ?? _accessEpoch;
    final userId = expectedUserId?.call();
    final verification = verificationEpoch != null;
    final uri = baseUrl.replace(
      path: '${baseUrl.path.replaceFirst(RegExp(r'/$'), '')}$path',
      queryParameters: query,
    );
    http.Request build(Map<String, String> credentials) {
      final request = http.Request(method, uri)..followRedirects = false;
      request.headers.addAll({
        ...credentials,
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
      return request;
    }

    final credentials = await _credentials(
      epoch,
      userId,
      verification: verification,
      fresh: freshCredentials,
    );
    try {
      final response = await http.Response.fromStream(
        await _send(
          build,
          credentials,
          epoch,
          userId,
          verification: verification,
          minted: freshCredentials,
        ),
      ).timeout(apiRequestTimeout);
      _checkAccess(epoch, userId, verification: verification);
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
          fromServer: true,
        );
      }
      if (response.statusCode < 200 || response.statusCode >= 300) {
        final error = result['error'] is Map
            ? Map<String, dynamic>.from(result['error'])
            : <String, dynamic>{};
        // The research routes answer with a bare {"detail": code}.
        final detail = result['detail'];
        throw ApiFailure(
          textOf(error['message'], 'The request did not complete. Retry.'),
          code: textOf(
            error['code'],
            detail is String && detail.isNotEmpty ? detail : 'request_failed',
          ),
          status: response.statusCode,
          details: error['details'] is Map
              ? Map<String, dynamic>.from(error['details'])
              : const {},
          fromServer: true,
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
    http.Request build(Map<String, String> credentials) =>
        http.Request(
            'GET',
            baseUrl.replace(
              path: '${baseUrl.path.replaceFirst(RegExp(r'/$'), '')}$path',
              queryParameters: query,
            ),
          )
          ..followRedirects = false
          ..headers.addAll({
            ...credentials,
            'Accept': artifact.kind == ArtifactKind.activeGraph
                ? 'application/json'
                : 'text/plain',
          });
    final credentials = await _credentials(epoch, userId);
    try {
      return await (() async {
        final response = await _send(build, credentials, epoch, userId);
        _checkAccess(epoch, userId);
        if (response.statusCode == 401 || response.statusCode == 403) {
          await response.stream.listen(null).cancel();
          throw _deny(
            ApiFailure(
              'Evidence access was denied. Check access again, or ask an administrator.',
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
}

/// Runtime API client for collection scopes, intake, review, and sources.
class ApiSpecimenRepository extends _ApiRepositoryBase
    with
        _ApiRepositoryScopes,
        _ApiRepositoryIntake,
        _ApiRepositoryReview,
        _ApiRepositorySources
    implements
        SpecimenRepository,
        IntakeProcessingRepository,
        CandidateReviewBatchRepository,
        SpecimenHistoryRepository,
        SourceRepository,
        CostRepository,
        BulkIntakeRepository,
        AccessFailureSource {
  ApiSpecimenRepository({
    required super.baseUrl,
    required super.token,
    super.client,
    super.expectedMode,
    super.appCheckToken,
    super.expectedUserId,
    super.freshToken,
    super.freshAppCheckToken,
  });
}
