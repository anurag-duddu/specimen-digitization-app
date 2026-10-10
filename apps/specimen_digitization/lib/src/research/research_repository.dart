import '../models.dart' show ApiFailure, CollectionScope, Specimen;
import 'research_models.dart';

/// The existing authenticated JSON request tear-off.
///
/// ApiSpecimenRepository.request supplies identity, App Check and access epochs.
/// This adapter adds no credentials, session or discovery calls.
typedef ResearchRequest =
    Future<Map<String, dynamic>> Function(
      String method,
      String path, {
      Map<String, dynamic>? body,
    });

/// A safe local classification of a failed exchange.
enum ResearchFailureKind {
  unauthenticated,
  forbidden,
  conflict,
  invalidResponse,
  unavailable,

  /// The record has no research for its current version. Not a failure to
  /// show: the host hides the research line.
  notRegistered,
}

/// A fixed reviewer-facing failure without raw service or exception text.
class ResearchFailure implements Exception {
  const ResearchFailure(this.kind);
  final ResearchFailureKind kind;
  String get message => switch (kind) {
    ResearchFailureKind.unauthenticated => 'Sign in again to view research.',
    ResearchFailureKind.forbidden =>
      'Research access is unavailable for this collection.',
    ResearchFailureKind.conflict =>
      'Research changed. Review the refreshed state before retrying.',
    ResearchFailureKind.invalidResponse =>
      'Research could not be verified. Refresh the current record.',
    ResearchFailureKind.unavailable =>
      'Research is unavailable right now. Refresh to try again.',
    ResearchFailureKind.notRegistered =>
      'No research is recorded for this version.',
  };
  @override
  String toString() => message;
}

/// An optional capability independent of the legacy specimen repository.
abstract interface class ResearchRepository {
  /// Reads a thread using the complete trusted scope.
  Future<ResearchThread> read(ResearchScope scope);

  /// Queues one field using its checkpoint revision.
  ///
  /// This returns an acknowledgment and never updates a specimen value.
  Future<ResearchRetryAck> retry(
    ResearchScope scope,
    String fieldKey, {
    required int expectedCheckpointRevision,
  });
}

/// A research adapter over the host's existing authenticated transport.
class ApiResearchRepository implements ResearchRepository {
  const ApiResearchRepository({required ResearchRequest request})
    : _request = request;
  final ResearchRequest _request;

  /// Resolves the current registered job against the opened canonical revision.
  Future<ResearchScope> discover(
    CollectionScope collection,
    Specimen specimen,
  ) async {
    String part(String value) => Uri.encodeComponent(value);
    final response = await _send(
      'GET',
      '/v1/organizations/${part(collection.organizationId)}'
          '/collections/${part(collection.collectionId)}'
          '/specimens/${part(specimen.id)}/research/current',
    );
    try {
      if (response['contract_version'] != 'canonical-binding/v2') {
        throw const ResearchContractException();
      }
      final canonical = response['canonical'];
      final capabilities = response['capabilities'];
      final historical = response['historical'];
      if (canonical is! Map ||
          capabilities is! Map ||
          (historical != null && historical is! bool) ||
          capabilities['read'] != true ||
          canonical['organization_id'] != collection.organizationId ||
          canonical['collection_id'] != collection.collectionId ||
          canonical['specimen_id'] != specimen.id ||
          canonical['record_revision'] is! int ||
          specimen.recordVersionId.isEmpty) {
        throw const ResearchContractException();
      }
      final scope = ResearchScope.fromJson(response['scope']);
      if (scope.generation < 1 ||
          scope.organizationId != collection.organizationId ||
          scope.collectionId != collection.collectionId ||
          scope.specimenId != specimen.id ||
          canonical['sensitive'] != scope.sensitive) {
        throw const ResearchContractException();
      }
      if (historical == true) {
        // A saved report keeps the native UUID and digest of its source Q.
        // It must not be presented as the native binding of the opened Q.
        final host = response['current_host'];
        final sourceRevision = canonical['record_revision'] as int;
        final savedRevision = response['review_saved_revision'];
        final runId = canonical['canonical_run_id'];
        final asset = specimen.data['asset'];
        // Legacy true classifications are omitted from the saved asset JSON.
        final assetSensitive = asset is Map
            ? (asset.containsKey('sensitive') ? asset['sensitive'] : true)
            : null;
        final nativeId = canonical['record_version_id'];
        final sourceDigest = canonical['snapshot_sha256'];
        final nativeUuid = RegExp(
          r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
        );
        final sha256 = RegExp(r'^[0-9a-f]{64}$');
        if (host is! Map ||
            sourceRevision < 1 ||
            response['canonical_revision'] is! int ||
            response['canonical_revision'] != sourceRevision ||
            savedRevision is! int ||
            savedRevision != sourceRevision + 1 ||
            savedRevision > specimen.revision ||
            runId is! String ||
            !nativeUuid.hasMatch(runId) ||
            runId != specimen.data['active_run_id'] ||
            nativeId is! String ||
            !nativeUuid.hasMatch(nativeId) ||
            sourceDigest is! String ||
            !sha256.hasMatch(sourceDigest) ||
            canonical['host_record_version_id'] != '$runId:$sourceRevision' ||
            asset is! Map ||
            assetSensitive is! bool ||
            host['organization_id'] != collection.organizationId ||
            host['collection_id'] != collection.collectionId ||
            host['specimen_id'] != specimen.id ||
            host['canonical_run_id'] != runId ||
            host['record_revision'] is! int ||
            host['record_revision'] != specimen.revision ||
            host['host_record_version_id'] != specimen.recordVersionId ||
            host['host_record_version_id'] != '$runId:${specimen.revision}' ||
            host['sensitive'] is! bool ||
            host['sensitive'] != assetSensitive ||
            (canonical['sensitive'] == true && host['sensitive'] != true) ||
            capabilities['retry'] != false ||
            capabilities['review'] != false) {
          throw const ResearchContractException();
        }
      } else if (canonical['record_revision'] != specimen.revision ||
          // The native record UUID is distinct from the workspace's run:revision.
          canonical['host_record_version_id'] != specimen.recordVersionId ||
          (specimen.data['sensitive'] is bool &&
              specimen.data['sensitive'] != scope.sensitive)) {
        throw const ResearchContractException();
      }
      return scope;
    } catch (_) {
      throw const ResearchFailure(ResearchFailureKind.invalidResponse);
    }
  }

  String _root(ResearchScope scope) {
    if (scope.generation < 1) {
      throw const ResearchFailure(ResearchFailureKind.invalidResponse);
    }
    String part(String value) => Uri.encodeComponent(value);
    return '/v1/organizations/${part(scope.organizationId)}'
        '/collections/${part(scope.collectionId)}'
        '/specimens/${part(scope.specimenId)}'
        '/research/jobs/${part(scope.jobId)}'
        '/generations/${scope.generation.toString()}';
  }

  Future<Map<String, dynamic>> _send(
    String method,
    String path, {
    Map<String, dynamic>? body,
  }) async {
    try {
      return await _request(method, path, body: body);
    } on ApiFailure catch (failure) {
      throw ResearchFailure(switch (failure.status) {
        401 => ResearchFailureKind.unauthenticated,
        403 => ResearchFailureKind.forbidden,
        409 || 412 => ResearchFailureKind.conflict,
        404 when failure.code == 'research_not_registered' =>
          ResearchFailureKind.notRegistered,
        _ => ResearchFailureKind.unavailable,
      });
    } on ResearchFailure {
      rethrow;
    } catch (_) {
      throw const ResearchFailure(ResearchFailureKind.unavailable);
    }
  }

  @override
  Future<ResearchThread> read(ResearchScope scope) async {
    final response = await _send('GET', '${_root(scope)}/thread');
    try {
      return ResearchThread.fromJson(response, expectedScope: scope);
    } catch (_) {
      throw const ResearchFailure(ResearchFailureKind.invalidResponse);
    }
  }

  @override
  Future<ResearchRetryAck> retry(
    ResearchScope scope,
    String fieldKey, {
    required int expectedCheckpointRevision,
  }) async {
    if (!researchFieldKeys.contains(fieldKey) ||
        expectedCheckpointRevision < 1) {
      throw const ResearchFailure(ResearchFailureKind.invalidResponse);
    }
    final response = await _send(
      'POST',
      '${_root(scope)}/fields/${Uri.encodeComponent(fieldKey)}/retry',
      body: {'expected_checkpoint_revision': expectedCheckpointRevision},
    );
    try {
      return ResearchRetryAck.fromJson(
        response,
        expectedScope: scope,
        expectedFieldKey: fieldKey,
        expectedCheckpointRevision: expectedCheckpointRevision,
      );
    } catch (_) {
      throw const ResearchFailure(ResearchFailureKind.invalidResponse);
    }
  }
}
