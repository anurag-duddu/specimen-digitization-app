import '../models.dart' show ApiFailure, CollectionScope, Specimen;
import 'derivation_models.dart';
import 'research_repository.dart' show ResearchFailure, ResearchFailureKind;

/// The existing authenticated transport with its Idempotency-Key option.
typedef DerivationRequestTransport =
    Future<Map<String, dynamic>> Function(
      String method,
      String path, {
      Map<String, dynamic>? body,
      String? key,
    });

/// Typed access to the server-owned capability and retained work result.
abstract interface class ResearchDerivationRepository {
  Future<ResearchDerivationCapability> capability(
    CollectionScope collection,
    Specimen specimen,
  );

  Future<ResearchDerivationAccepted> enqueue(
    CollectionScope collection,
    Specimen specimen, {
    required ResearchDerivationCapability capability,
    required List<String> requestedFields,
    required String reason,
    required String idempotencyKey,
  });

  Future<ResearchDerivationResult> result(
    CollectionScope collection,
    Specimen specimen,
    String requestId,
  );
}

class ApiResearchDerivationRepository implements ResearchDerivationRepository {
  const ApiResearchDerivationRepository({
    required DerivationRequestTransport request,
  }) : _request = request;

  final DerivationRequestTransport _request;

  String _root(CollectionScope collection, Specimen specimen) {
    String part(String value) => Uri.encodeComponent(value);
    return '/v1/organizations/${part(collection.organizationId)}'
        '/collections/${part(collection.collectionId)}'
        '/specimens/${part(specimen.id)}/research/derivations';
  }

  Future<Map<String, dynamic>> _send(
    String method,
    String path, {
    Map<String, dynamic>? body,
    String? key,
  }) async {
    try {
      return await _request(method, path, body: body, key: key);
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
  Future<ResearchDerivationCapability> capability(
    CollectionScope collection,
    Specimen specimen,
  ) async {
    final response = await _send(
      'GET',
      '${_root(collection, specimen)}/capability',
    );
    try {
      final capability = ResearchDerivationCapability.fromJson(response);
      if (capability.canonicalRevision != specimen.revision) {
        throw const FormatException();
      }
      return capability;
    } catch (_) {
      throw const ResearchFailure(ResearchFailureKind.invalidResponse);
    }
  }

  @override
  Future<ResearchDerivationAccepted> enqueue(
    CollectionScope collection,
    Specimen specimen, {
    required ResearchDerivationCapability capability,
    required List<String> requestedFields,
    required String reason,
    required String idempotencyKey,
  }) async {
    final distinct = requestedFields.toSet();
    if (specimen.revision < 1 ||
        specimen.recordVersionId.isEmpty ||
        !capability.appliesTo(specimen.revision) ||
        requestedFields.isEmpty ||
        distinct.length != requestedFields.length ||
        !capability.eligibleFields.toSet().containsAll(requestedFields) ||
        reason.trim().isEmpty ||
        idempotencyKey.trim().isEmpty) {
      throw const ResearchFailure(ResearchFailureKind.invalidResponse);
    }
    final response = await _send(
      'POST',
      _root(collection, specimen),
      key: idempotencyKey,
      body: {
        'expected_record_revision': specimen.revision,
        'base_record_version_id': specimen.recordVersionId,
        'reason': reason,
        'requested_fields': requestedFields,
      },
    );
    try {
      return ResearchDerivationAccepted.fromJson(
        response,
        expectedSourceRevision: specimen.revision,
      );
    } catch (_) {
      throw const ResearchFailure(ResearchFailureKind.invalidResponse);
    }
  }

  @override
  Future<ResearchDerivationResult> result(
    CollectionScope collection,
    Specimen specimen,
    String requestId,
  ) async {
    if (!RegExp(r'^[a-f0-9]{64}$').hasMatch(requestId)) {
      throw const ResearchFailure(ResearchFailureKind.invalidResponse);
    }
    final response = await _send(
      'GET',
      '${_root(collection, specimen)}/${Uri.encodeComponent(requestId)}',
    );
    try {
      return ResearchDerivationResult.fromJson(
        response,
        expectedRequestId: requestId,
      );
    } catch (_) {
      throw const ResearchFailure(ResearchFailureKind.invalidResponse);
    }
  }
}
