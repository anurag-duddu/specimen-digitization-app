import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/research/derivation_models.dart';
import 'package:specimen_digitization/src/research/derivation_repository.dart';

void main() {
  final requestId = 'a' * 64;
  final token = 'b' * 64;
  const versionId = 'run-1:7';

  test(
    'reads current capability through the existing authenticated transport',
    () async {
      final requests = <http.Request>[];
      final api = ApiSpecimenRepository(
        baseUrl: Uri.parse('http://localhost:8080'),
        token: () async => 'synthetic-token',
        appCheckToken: () async => 'synthetic-attestation',
        client: MockClient((request) async {
          requests.add(request);
          return http.Response(
            jsonEncode({
              'contract_version': 'research-derivation-capability/v1',
              'available': true,
              'blocked_reason': null,
              'canonical_revision': 7,
              'eligible_fields': ['province_state', 'county'],
            }),
            200,
          );
        }),
      );
      addTearDown(api.close);
      final repository = ApiResearchDerivationRepository(request: api.request);
      final capability = await repository.capability(
        const CollectionScope(
          organizationId: 'org',
          collectionId: 'collection',
          name: 'Synthetic collection',
          permissions: [],
        ),
        Specimen({
          'specimen_id': 'specimen',
          'revision': 7,
          'latest_record_version_id': versionId,
        }),
      );
      expect(capability.appliesTo(7), isTrue);
      expect(capability.eligibleFields, ['province_state', 'county']);
      expect(
        requests.single.url.path,
        endsWith('/specimens/specimen/research/derivations/capability'),
      );
      expect(
        requests.single.headers['Authorization'],
        'Bearer synthetic-token',
      );
      expect(
        requests.single.headers['X-Firebase-AppCheck'],
        'synthetic-attestation',
      );
    },
  );

  test(
    'posts only chosen targets, current revisions, reason, and idempotency key',
    () async {
      http.Request? sent;
      final api = ApiSpecimenRepository(
        baseUrl: Uri.parse('http://localhost:8080'),
        token: () async => 'synthetic-token',
        appCheckToken: () async => 'synthetic-attestation',
        client: MockClient((request) async {
          sent = request;
          return http.Response(
            jsonEncode({
              'contract_version': 'research-derivation-accepted/v1',
              'request_id': requestId,
              'source_revision': 7,
              'queued_revision': 8,
              'status': 'queued',
              'canonical_run_id': 'run-1',
            }),
            202,
          );
        }),
      );
      addTearDown(api.close);
      final repository = ApiResearchDerivationRepository(request: api.request);
      const collection = CollectionScope(
        organizationId: 'org',
        collectionId: 'collection',
        name: 'Synthetic collection',
        permissions: [],
      );
      final specimen = Specimen({
        'specimen_id': 'specimen',
        'revision': 7,
        'latest_record_version_id': versionId,
        'fields': [
          {'field_key': 'country', 'literal_value': 'Philippines'},
        ],
      });
      final capability = ResearchDerivationCapability.fromJson({
        'contract_version': 'research-derivation-capability/v1',
        'available': true,
        'canonical_revision': 7,
        'eligible_fields': ['province_state', 'county'],
      });

      final accepted = await repository.enqueue(
        collection,
        specimen,
        capability: capability,
        requestedFields: const ['county'],
        reason: 'Review the remaining location details.',
        idempotencyKey: 'synthetic-idempotency-key',
      );

      expect(accepted.requestId, requestId);
      expect(
        sent!.url.path,
        endsWith('/specimens/specimen/research/derivations'),
      );
      expect(sent!.headers['Idempotency-Key'], 'synthetic-idempotency-key');
      expect(jsonDecode(sent!.body), {
        'expected_record_revision': 7,
        'base_record_version_id': versionId,
        'reason': 'Review the remaining location details.',
        'requested_fields': ['county'],
      });
      expect(sent!.body, isNot(contains('Philippines')));
      expect(sent!.body, isNot(contains('coordinate')));
    },
  );

  test(
    'reads only a matching request result and retained selectable proposals',
    () async {
      http.Request? sent;
      final api = ApiSpecimenRepository(
        baseUrl: Uri.parse('http://localhost:8080'),
        token: () async => 'synthetic-token',
        appCheckToken: () async => 'synthetic-attestation',
        client: MockClient((request) async {
          sent = request;
          return http.Response(
            jsonEncode({
              'contract_version': 'research-derivation-result/v1',
              'request_id': requestId,
              'source_revision': 7,
              'queued_revision': 8,
              'status': 'completed',
              'canonical_revision': 8,
              'stale': false,
              'proposals': [
                {
                  'field_key': 'county',
                  'value': 'Bukidnon',
                  'input_fields': ['country'],
                  'input_revisions': [
                    ['country', 7],
                  ],
                  'evidence_ids': ['retained-evidence'],
                  'authority_id': 'retained-authority',
                  'dataset_ids': ['geoboundaries/PH/ADM2'],
                  'tool_call_id': 'retained-tool-call',
                  'value_layer': 'derived',
                  'rule_version': 'georeference-v1',
                  'checkpoint_id': 'c' * 64,
                  'checkpoint_revision': 8,
                  'effect_id': 'd' * 64,
                  'selection_id': token,
                  'source_id': 'georeference_spatial',
                },
              ],
            }),
            200,
          );
        }),
      );
      addTearDown(api.close);
      final repository = ApiResearchDerivationRepository(request: api.request);
      final result = await repository.result(
        const CollectionScope(
          organizationId: 'org',
          collectionId: 'collection',
          name: 'Synthetic collection',
          permissions: [],
        ),
        Specimen({
          'specimen_id': 'specimen',
          'revision': 8,
          'latest_record_version_id': 'run-1:8',
        }),
        requestId,
      );
      expect(sent!.url.path, endsWith('/research/derivations/$requestId'));
      expect(result.status, 'completed');
      expect(result.proposals.single.value, 'Bukidnon');
      expect(result.proposals.single.selectable, isTrue);
    },
  );

  test(
    'stale reports cannot carry selectable candidates into field review',
    () {
      expect(
        () => ResearchDerivationResult.fromJson({
          'contract_version': 'research-derivation-result/v1',
          'request_id': requestId,
          'source_revision': 7,
          'queued_revision': 8,
          'status': 'completed',
          'canonical_revision': 9,
          'stale': true,
          'proposals': [
            {
              'field_key': 'county',
              'value': 'Bukidnon',
              'input_fields': ['country'],
              'input_revisions': [
                ['country', 7],
              ],
              'evidence_ids': ['retained-evidence'],
              'authority_id': 'retained-authority',
              'dataset_ids': ['dataset'],
              'tool_call_id': 'tool',
              'value_layer': 'derived',
              'rule_version': 'georeference-v1',
              'checkpoint_id': 'c' * 64,
              'checkpoint_revision': 8,
              'effect_id': 'd' * 64,
              'selection_id': token,
              'source_id': 'georeference_spatial',
            },
          ],
        }, expectedRequestId: requestId),
        throwsFormatException,
      );
    },
  );
}
