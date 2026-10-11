import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/models.dart'
    show ApiFailure, CollectionScope, Specimen;
import 'package:specimen_digitization/src/research/research_models.dart';
import 'package:specimen_digitization/src/research/research_repository.dart';

import 'research_fixture.dart';

void main() {
  test(
    'uses the existing authenticated request and sends only field revision',
    () async {
      final requests = <http.Request>[];
      final legacy = ApiSpecimenRepository(
        baseUrl: Uri.parse('http://localhost:8080'),
        token: () async => 'synthetic-token',
        appCheckToken: () async => 'synthetic-attestation',
        client: MockClient((request) async {
          requests.add(request);
          return http.Response(
            jsonEncode(
              researchFixture(
                request.method == 'POST' ? 'queued-retry' : 'failed-thread',
              ),
            ),
            200,
          );
        }),
      );
      addTearDown(legacy.close);
      final repository = ApiResearchRepository(request: legacy.request);
      final scope = trustedResearchScope();
      final thread = await repository.read(scope);
      await repository.retry(
        scope,
        'taxon',
        expectedCheckpointRevision: thread.field('taxon')!.checkpoint!.revision,
      );
      expect(requests, hasLength(2));
      expect(
        requests.first.url.path,
        '/v1/organizations/org/collections/insects/specimens/specimen/research/jobs/job/generations/1/thread',
      );
      expect(requests.last.url.path, endsWith('/fields/taxon/retry'));
      expect(jsonDecode(requests.last.body), {
        'expected_checkpoint_revision': 1,
      });
      expect(requests.first.headers['Authorization'], 'Bearer synthetic-token');
      expect(
        requests.first.headers['X-Firebase-AppCheck'],
        'synthetic-attestation',
      );
      expect(
        requests.any((request) => request.url.path.endsWith('/session')),
        isFalse,
      );
    },
  );

  test(
    'encodes each trusted path segment without adding discovery or query',
    () async {
      String? path;
      final scope = ResearchScope(
        organizationId: 'org /?',
        collectionId: 'collection /?',
        specimenId: 'specimen /?',
        jobId: 'job /?',
        generation: 1,
        inputDigest: 'a' * 64,
        profileDigest: 'b' * 64,
        sensitive: true,
      );
      final repository = ApiResearchRepository(
        request: (method, requested, {body}) async {
          path = requested;
          final json = researchFixture('failed-thread');
          json['scope'] = scope.json;
          for (final field in json['fields'] as List) {
            if (field['checkpoint'] != null) {
              field['checkpoint']['scope'] = scope.json;
            }
          }
          return json;
        },
      );
      await repository.read(scope);
      expect(path, contains('org%20%2F%3F/collections/collection%20%2F%3F'));
      expect(
        path,
        contains('/specimens/specimen%20%2F%3F/research/jobs/job%20%2F%3F/'),
      );
    },
  );

  test('invalid input never reaches the transport', () async {
    var calls = 0;
    final repository = ApiResearchRepository(
      request: (method, path, {body}) async {
        calls++;
        return {};
      },
    );
    for (final field in ['unknown', 'taxon']) {
      await expectLater(
        repository.retry(
          trustedResearchScope(),
          field,
          expectedCheckpointRevision: 0,
        ),
        throwsA(isA<ResearchFailure>()),
      );
    }
    expect(calls, 0);
  });

  for (final status in [401, 403, 409, 503]) {
    test('sanitizes failure status ${status.toString()}', () async {
      final repository = ApiResearchRepository(
        request: (method, path, {body}) async {
          throw ApiFailure('PRIVATE RAW SERVER DETAIL', status: status);
        },
      );
      try {
        await repository.read(trustedResearchScope());
        fail('Expected sanitized failure.');
      } on ResearchFailure catch (failure) {
        expect(failure.message, isNot(contains('PRIVATE')));
        expect(failure.kind, switch (status) {
          401 => ResearchFailureKind.unauthenticated,
          403 => ResearchFailureKind.forbidden,
          409 => ResearchFailureKind.conflict,
          _ => ResearchFailureKind.unavailable,
        });
      }
    });
  }

  // The API answers research/current with 404 research_not_registered when the
  // record has no research for its current revision. Only that answer is "not
  // registered"; any other 404 stays unavailable.
  for (final (detail, kind) in [
    ('research_not_registered', 'notRegistered'),
    ('not_found', 'unavailable'),
  ]) {
    test('a 404 $detail from discovery is $kind', () async {
      final legacy = ApiSpecimenRepository(
        baseUrl: Uri.parse('http://localhost:8080'),
        token: () async => 'synthetic-token',
        client: MockClient(
          (request) async => http.Response(jsonEncode({'detail': detail}), 404),
        ),
      );
      addTearDown(legacy.close);
      final repository = ApiResearchRepository(request: legacy.request);
      await expectLater(
        repository.discover(
          const CollectionScope(
            organizationId: 'org',
            collectionId: 'insects',
            name: 'Insects',
          ),
          Specimen({'specimen_id': 'specimen', 'revision': 88}),
        ),
        throwsA(
          isA<ResearchFailure>().having((f) => f.kind.name, 'kind', kind),
        ),
      );
    });
  }

  test('malformed and cross-scope responses fail closed', () async {
    for (final json in [
      <String, dynamic>{},
      researchFixture('failed-thread')..['contract_version'] = 'other',
    ]) {
      final repository = ApiResearchRepository(
        request: (method, path, {body}) async => json,
      );
      await expectLater(
        repository.read(trustedResearchScope()),
        throwsA(
          isA<ResearchFailure>().having(
            (f) => f.kind,
            'kind',
            ResearchFailureKind.invalidResponse,
          ),
        ),
      );
    }
  });
}
