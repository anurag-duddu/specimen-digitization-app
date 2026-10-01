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
      'Research could not be loaded. Check your connection and refresh.',
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
      if (canonical is! Map ||
          capabilities is! Map ||
          capabilities['read'] != true ||
          canonical['organization_id'] != collection.organizationId ||
          canonical['collection_id'] != collection.collectionId ||
          canonical['specimen_id'] != specimen.id ||
          canonical['record_revision'] is! int ||
          canonical['record_revision'] != specimen.revision ||
          specimen.recordVersionId.isEmpty ||
          // The native record UUID is distinct from the workspace's run:revision.
          canonical['host_record_version_id'] != specimen.recordVersionId) {
        throw const ResearchContractException();
      }
      final scope = ResearchScope.fromJson(response['scope']);
      if (scope.generation < 1 ||
          scope.organizationId != collection.organizationId ||
          scope.collectionId != collection.collectionId ||
          scope.specimenId != specimen.id ||
          canonical['sensitive'] != scope.sensitive ||
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
