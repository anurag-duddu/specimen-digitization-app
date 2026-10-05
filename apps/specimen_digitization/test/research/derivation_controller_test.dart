import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/research/derivation_controller.dart';
import 'package:specimen_digitization/src/research/derivation_models.dart';
import 'package:specimen_digitization/src/research/derivation_repository.dart';

class FakeDerivationRepository implements ResearchDerivationRepository {
  FakeDerivationRepository({
    required this.capabilityResponse,
    required this.readResult,
  });

  ResearchDerivationCapability capabilityResponse;
  ResearchDerivationResult readResult;
  List<String>? requestedFields;
  String? reason;
  String? idempotencyKey;
  int resultReads = 0;

  @override
  Future<ResearchDerivationCapability> capability(
    CollectionScope collection,
    Specimen specimen,
  ) async => capabilityResponse;

  @override
  Future<ResearchDerivationAccepted> enqueue(
    CollectionScope collection,
    Specimen specimen, {
    required ResearchDerivationCapability capability,
    required List<String> requestedFields,
    required String reason,
    required String idempotencyKey,
  }) async {
    this.requestedFields = requestedFields;
    this.reason = reason;
    this.idempotencyKey = idempotencyKey;
    return ResearchDerivationAccepted.fromJson({
      'contract_version': 'research-derivation-accepted/v1',
      'request_id': 'a' * 64,
      'source_revision': specimen.revision,
      'queued_revision': specimen.revision + 1,
      'status': 'queued',
      'canonical_run_id': 'run',
    }, expectedSourceRevision: specimen.revision);
  }

  @override
  Future<ResearchDerivationResult> result(
    CollectionScope collection,
    Specimen specimen,
    String requestId,
  ) async {
    resultReads++;
    return readResult;
  }
}

ResearchDerivationCapability cap({bool available = true, int revision = 7}) =>
    ResearchDerivationCapability.fromJson({
      'contract_version': 'research-derivation-capability/v1',
      'available': available,
      'canonical_revision': revision,
      'eligible_fields': available ? ['county'] : <String>[],
    });

ResearchDerivationResult result({
  String status = 'running',
  int revision = 8,
  bool stale = false,
}) => ResearchDerivationResult.fromJson({
  'contract_version': 'research-derivation-result/v1',
  'request_id': 'a' * 64,
  'source_revision': 7,
  'queued_revision': 8,
  'status': status,
  'canonical_revision': revision,
  'stale': stale,
  'proposals': <Object>[],
}, expectedRequestId: 'a' * 64);

const collection = CollectionScope(
  organizationId: 'org',
  collectionId: 'collection',
  name: 'Synthetic collection',
);
final specimen = Specimen({
  'specimen_id': 'specimen',
  'revision': 7,
  'latest_record_version_id': 'run:7',
});

void main() {
  test(
    'queues only the review choice and shows backend progress after reload',
    () async {
      final repository = FakeDerivationRepository(
        capabilityResponse: cap(),
        readResult: result(status: 'running'),
      );
      final controller = ResearchDerivationController(
        repository: repository,
        collection: collection,
        specimen: specimen,
      );
      addTearDown(controller.dispose);
      await controller.loadCapability();
      expect(controller.canRequest, isTrue);

      var reloaded = 0;
      await controller.request(
        fields: const ['county'],
        reason: 'Review the place.',
        refreshRecord: () async => reloaded++,
      );

      expect(repository.requestedFields, ['county']);
      expect(repository.reason, 'Review the place.');
      expect(repository.idempotencyKey, startsWith('research-derivation-'));
      expect(reloaded, 1);
      expect(controller.accepted?.queuedRevision, 8);
      expect(controller.result?.status, 'running');
      expect(controller.canRequest, isFalse);
    },
  );

  test(
    'stale retained result is shown as stale and triggers a record refresh',
    () async {
      final repository = FakeDerivationRepository(
        capabilityResponse: cap(),
        readResult: result(status: 'completed'),
      );
      final controller = ResearchDerivationController(
        repository: repository,
        collection: collection,
        specimen: specimen,
      );
      addTearDown(controller.dispose);
      await controller.loadCapability();
      await controller.request(
        fields: const ['county'],
        reason: 'Review the place.',
        refreshRecord: () async {},
      );
      repository.readResult = result(
        status: 'completed',
        revision: 9,
        stale: true,
      );

      var reloaded = 0;
      await controller.refreshResult(refreshRecord: () async => reloaded++);

      expect(controller.result?.stale, isTrue);
      expect(controller.message, contains('record changed'));
      expect(reloaded, 1);
      expect(controller.canRequest, isFalse);
    },
  );

  test(
    'queued result stays current at Q and becomes nonselectable after Q advances',
    () async {
      final repository = FakeDerivationRepository(
        capabilityResponse: cap(),
        readResult: result(status: 'completed', revision: 8),
      );
      final controller = ResearchDerivationController(
        repository: repository,
        collection: collection,
        specimen: specimen,
      );
      addTearDown(controller.dispose);
      await controller.loadCapability();
      await controller.request(
        fields: const ['county'],
        reason: 'Review the place.',
        refreshRecord: () async {},
      );
      final accepted = controller.accepted;
      expect(accepted?.queuedRevision, 8);

      final queuedRecord = Specimen({
        'specimen_id': 'specimen',
        'revision': 8,
        'latest_record_version_id': 'run:8',
      });
      controller.bind(collection: collection, specimen: queuedRecord);
      expect(controller.result?.canonicalRevision, 8);
      expect(controller.hasCurrentResult, isTrue);
      expect(controller.accepted?.requestId, accepted?.requestId);

      final laterRecord = Specimen({
        'specimen_id': 'specimen',
        'revision': 9,
        'latest_record_version_id': 'run:9',
      });
      controller.bind(collection: collection, specimen: laterRecord);
      expect(controller.result, isNull);
      expect(controller.hasCurrentResult, isFalse);
      expect(controller.accepted?.requestId, accepted?.requestId);
      expect(controller.message, contains('record changed'));
      expect(controller.canRequest, isFalse);

      repository.capabilityResponse = cap(revision: 9);
      repository.readResult = result(
        status: 'completed',
        revision: 9,
        stale: true,
      );
      await controller.loadCapability();
      expect(controller.canRequest, isFalse);
      await controller.refreshResult(refreshRecord: () async {});
      expect(controller.accepted, isNull);
      expect(controller.result?.stale, isTrue);
      expect(controller.hasCurrentResult, isFalse);
      expect(controller.canRequest, isTrue);
    },
  );

  test('unavailable capability never enables a request', () async {
    final repository = FakeDerivationRepository(
      capabilityResponse: cap(available: false),
      readResult: result(),
    );
    final controller = ResearchDerivationController(
      repository: repository,
      collection: collection,
      specimen: specimen,
    );
    addTearDown(controller.dispose);
    await controller.loadCapability();

    expect(controller.canRequest, isFalse);
    await controller.request(
      fields: const ['county'],
      reason: 'Should not post.',
      refreshRecord: () async {},
    );
    expect(repository.requestedFields, isNull);
    expect(repository.resultReads, 0);
  });
}
