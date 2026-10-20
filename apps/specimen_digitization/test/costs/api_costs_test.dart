// The three cost calls over the wire (`ApiSpecimenRepository`): the paths,
// the bodies and the failures the contract names.

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/costs.dart';
import 'package:specimen_digitization/src/models.dart';

import 'cost_fixtures.dart';

ApiSpecimenRepository repository(
  Future<http.Response> Function(http.Request) handler,
) => ApiSpecimenRepository(
  baseUrl: Uri.parse('http://localhost:8000'),
  token: () async => 'synthetic-test-token',
  appCheckToken: () async => 'synthetic-app-check',
  client: MockClient(handler),
);

http.Response json(Object body, [int status = 200]) => http.Response(
  jsonEncode(body),
  status,
  headers: <String, String>{'content-type': 'application/json'},
);

void main() {
  test('the API repository serves costs', () {
    expect(
      costsIn(repository((http.Request _) async => json(<String, dynamic>{}))),
      isNotNull,
    );
  });

  group('reading the costs', () {
    test('asks for one organization and the months from to', () async {
      late http.Request seen;
      final ApiSpecimenRepository repo = repository((http.Request r) async {
        seen = r;
        return json(costWire('2026-09'));
      });

      final CostReport report = await repo.costs(
        costOrganization,
        from: '2026-09',
        to: '2026-10',
      );

      expect(seen.method, 'GET');
      expect(seen.url.path, '/v1/organizations/org/costs');
      expect(seen.url.queryParameters, <String, String>{
        'from': '2026-09',
        'to': '2026-10',
      });
      expect(seen.headers['Authorization'], 'Bearer synthetic-test-token');
      expect(report.organizationId, costOrganization);
      expect(report.totals.costMicros, 12345678);
      expect(report.collections, hasLength(4));
    });

    test('encodes an organization that is not a plain word', () async {
      late http.Request seen;
      final ApiSpecimenRepository repo = repository((http.Request r) async {
        seen = r;
        return json(costWire(thisMonth));
      });

      await repo.costs('a b/c', from: thisMonth, to: thisMonth);

      expect(seen.url.path, '/v1/organizations/a%20b%2Fc/costs');
    });

    test('reads a report whose limits and meter are null', () async {
      final ApiSpecimenRepository repo = repository(
        (http.Request _) async => json(emptyCostWire('2026-09')),
      );

      final CostReport report = await repo.costs(
        costOrganization,
        from: '2026-09',
        to: '2026-09',
      );

      expect(report.organizationLimit, isNull);
      expect(report.meter, isNull);
      expect(report.totals.hasCosts, isFalse);
    });

    test(
      'names a deployment with no meter by the server\'s own code',
      () async {
        final ApiSpecimenRepository repo = repository(
          (http.Request _) async => json(<String, dynamic>{
            'error': <String, dynamic>{
              'code': 'cost_meter_unavailable',
              'message': 'No cost meter is configured.',
            },
          }, 503),
        );

        await expectLater(
          repo.costs(costOrganization, from: thisMonth, to: thisMonth),
          throwsA(
            isA<ApiFailure>()
                .having((ApiFailure f) => f.status, 'status', 503)
                .having(
                  (ApiFailure f) => f.code,
                  'code',
                  'cost_meter_unavailable',
                ),
          ),
        );
      },
    );

    test('reads the same code from a bare detail', () async {
      final ApiSpecimenRepository repo = repository(
        (http.Request _) async =>
            json(<String, dynamic>{'detail': 'cost_meter_unavailable'}, 503),
      );

      await expectLater(
        repo.costs(costOrganization, from: thisMonth, to: thisMonth),
        throwsA(
          isA<ApiFailure>().having(
            (ApiFailure f) => f.code,
            'code',
            'cost_meter_unavailable',
          ),
        ),
      );
    });

    test('a 503 is not a loss of access', () async {
      final List<ApiFailure> denials = <ApiFailure>[];
      final ApiSpecimenRepository repo = repository(
        (http.Request _) async => json(<String, dynamic>{
          'error': <String, dynamic>{'code': 'cost_meter_unavailable'},
        }, 503),
      );
      repo.accessFailures.listen(denials.add);

      await expectLater(
        repo.costs(costOrganization, from: thisMonth, to: thisMonth),
        throwsA(isA<ApiFailure>()),
      );
      await Future<void>.delayed(Duration.zero);

      expect(denials, isEmpty);
    });

    test(
      'a 403 is the session\'s failure, which is why nobody else asks',
      () async {
        // The reason the screen asks `costOrganizationOf` before it sends
        // anything: the repository keeps the first 401 or 403 and refuses every
        // later request with it.
        int requests = 0;
        final List<ApiFailure> denials = <ApiFailure>[];
        final ApiSpecimenRepository repo = repository((http.Request _) async {
          requests++;
          return json(<String, dynamic>{
            'error': <String, dynamic>{
              'code': 'forbidden',
              'message': 'Administrators only.',
            },
          }, 403);
        });
        repo.accessFailures.listen(denials.add);

        await expectLater(
          repo.costs(costOrganization, from: thisMonth, to: thisMonth),
          throwsA(
            isA<ApiFailure>().having((ApiFailure f) => f.status, 'status', 403),
          ),
        );
        await expectLater(
          repo.costs(costOrganization, from: thisMonth, to: thisMonth),
          throwsA(isA<ApiFailure>()),
        );

        expect(denials, hasLength(1));
        expect(requests, 1, reason: 'the second read never left the client');
      },
    );

    test('refuses a body that is not a report', () async {
      final ApiSpecimenRepository repo = repository(
        (http.Request _) async => json(<String, dynamic>{'items': <Object>[]}),
      );

      await expectLater(
        repo.costs(costOrganization, from: thisMonth, to: thisMonth),
        throwsA(
          isA<ApiFailure>().having(
            (ApiFailure f) => f.code,
            'code',
            'invalid_response',
          ),
        ),
      );
    });

    test('refuses a body that is not JSON', () async {
      final ApiSpecimenRepository repo = repository(
        (http.Request _) async => http.Response('<html>', 200),
      );

      await expectLater(
        repo.costs(costOrganization, from: thisMonth, to: thisMonth),
        throwsA(
          isA<ApiFailure>().having(
            (ApiFailure f) => f.code,
            'code',
            'invalid_response',
          ),
        ),
      );
    });

    test('refuses figures in another currency', () async {
      final ApiSpecimenRepository repo = repository(
        (http.Request _) async =>
            json(<String, dynamic>{...costWire(thisMonth), 'currency': 'GBP'}),
      );

      await expectLater(
        repo.costs(costOrganization, from: thisMonth, to: thisMonth),
        throwsA(
          isA<ApiFailure>().having(
            (ApiFailure f) => f.code,
            'code',
            'unsupported_currency',
          ),
        ),
      );
    });
  });

  group('asking for an update', () {
    test('posts to refresh and reads whether one started', () async {
      late http.Request seen;
      final ApiSpecimenRepository repo = repository((http.Request r) async {
        seen = r;
        return json(<String, dynamic>{'started': true});
      });

      expect(await repo.refreshCosts(costOrganization), isTrue);
      expect(seen.method, 'POST');
      expect(seen.url.path, '/v1/organizations/org/costs/refresh');
    });

    test('says no when the server started nothing', () async {
      final ApiSpecimenRepository repo = repository(
        (http.Request _) async => json(<String, dynamic>{'started': false}),
      );

      expect(await repo.refreshCosts(costOrganization), isFalse);
    });

    test('says no to an answer that does not say yes', () async {
      for (final Object? body in <Object?>[
        <String, dynamic>{},
        <String, dynamic>{'started': 'true'},
        <String, dynamic>{'started': null},
      ]) {
        final ApiSpecimenRepository repo = repository(
          (http.Request _) async => json(body! as Map<String, dynamic>),
        );
        expect(
          await repo.refreshCosts(costOrganization),
          isFalse,
          reason: '$body',
        );
      }
    });

    test('fails with the server\'s reason', () async {
      final ApiSpecimenRepository repo = repository(
        (http.Request _) async => json(<String, dynamic>{
          'error': <String, dynamic>{
            'code': 'cost_meter_unavailable',
            'message': 'No cost meter is configured.',
          },
        }, 503),
      );

      await expectLater(
        repo.refreshCosts(costOrganization),
        throwsA(
          isA<ApiFailure>().having(
            (ApiFailure f) => f.message,
            'message',
            'No cost meter is configured.',
          ),
        ),
      );
    });
  });

  group('changing a limit', () {
    Future<Map<String, dynamic>> sent(
      Future<void> Function(ApiSpecimenRepository repo) call,
    ) async {
      late http.Request seen;
      final ApiSpecimenRepository repo = repository((http.Request r) async {
        seen = r;
        return json(<String, dynamic>{
          'organization_id': costOrganization,
          'caps': <Object>[],
        });
      });
      await call(repo);
      expect(seen.method, 'PUT');
      expect(seen.url.path, '/v1/organizations/org/costs/caps');
      expect(seen.headers['Content-Type'], contains('application/json'));
      return jsonDecode(seen.body) as Map<String, dynamic>;
    }

    test('sets the organization\'s limit with no collection', () async {
      final Map<String, dynamic> body = await sent(
        (ApiSpecimenRepository repo) =>
            repo.setCostLimit(costOrganization, micros: 5000000),
      );

      expect(body, <String, dynamic>{
        'collection_id': null,
        'monthly_cap_micros': 5000000,
      });
    });

    test('sets one collection\'s limit', () async {
      final Map<String, dynamic> body = await sent(
        (ApiSpecimenRepository repo) => repo.setCostLimit(
          costOrganization,
          collectionId: 'col-insects',
          micros: 10000000,
        ),
      );

      expect(body, <String, dynamic>{
        'collection_id': 'col-insects',
        'monthly_cap_micros': 10000000,
      });
    });

    test('removes a limit by sending null, not zero', () async {
      final Map<String, dynamic> body = await sent(
        (ApiSpecimenRepository repo) =>
            repo.setCostLimit(costOrganization, collectionId: 'col-insects'),
      );

      expect(body, <String, dynamic>{
        'collection_id': 'col-insects',
        'monthly_cap_micros': null,
      });
    });

    test('fails with the server\'s reason and sends nothing more', () async {
      int requests = 0;
      final ApiSpecimenRepository repo = repository((http.Request _) async {
        requests++;
        return json(<String, dynamic>{
          'error': <String, dynamic>{
            'code': 'invalid_cap',
            'message': 'The limit is below what is already spent.',
          },
        }, 422);
      });

      await expectLater(
        repo.setCostLimit(costOrganization, micros: 1),
        throwsA(
          isA<ApiFailure>()
              .having((ApiFailure f) => f.status, 'status', 422)
              .having(
                (ApiFailure f) => f.message,
                'message',
                'The limit is below what is already spent.',
              ),
        ),
      );
      expect(requests, 1, reason: 'a write is never sent twice');
    });
  });
}
