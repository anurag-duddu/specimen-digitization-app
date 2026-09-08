import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/models.dart';

void main() {
  final fixture =
      jsonDecode(
            File('test/fixtures/backend-wire-examples.json').readAsStringSync(),
          )
          as Json;
  const scope = CollectionScope(
    organizationId: 'org',
    collectionId: 'collection',
    name: 'Synthetic collection',
  );
  ApiSpecimenRepository repository(
    Future<http.Response> Function(http.Request) handler,
  ) => ApiSpecimenRepository(
    baseUrl: Uri.parse('http://localhost:8000'),
    token: () async => 'synthetic-test-token',
    appCheckToken: () async => 'synthetic-app-check',
    client: MockClient(handler),
  );

  test(
    'wire fixture session and exact workspace projection are consumed',
    () async {
      final repo = repository((r) async {
        expect(r.headers['Authorization'], 'Bearer synthetic-test-token');
        if (r.url.path == '/v1/session') {
          return http.Response(jsonEncode(fixture['session']), 200);
        }
        if (r.url.path.endsWith('/content')) {
          return http.Response.bytes([1, 2, 3], 200);
        }
        return http.Response(jsonEncode(fixture['workspace_response']), 200);
      });
      final scopes = await repo.scopes();
      expect(
        scopes.single.collectionId,
        fixture['session']['memberships'][0]['collection_id'],
      );
      expect(repo.mode, 'synthetic');
      final s = await repo.specimen(scope, 'sample');
      expect(s.id, fixture['workspace_response']['specimen_id']);
      expect(s.fields, hasLength(20));
      expect(s.assets.single['preview_bytes'], [1, 2, 3]);
      expect(
        s.data['latest_record_version_id'],
        fixture['workspace_response']['record_version_id'],
      );
    },
  );

  test(
    'interrupted upload resumes from acknowledged byte offset without replaying prefix',
    () async {
      final offsets = <int>[];
      var offset = 3;
      final repo = repository((r) async {
        if (r.method == 'GET') {
          return http.Response(
            jsonEncode({'upload_id': 'u1', 'offset': offset, 'revision': 2}),
            200,
          );
        }
        offsets.add(int.parse(r.headers['Upload-Offset']!));
        expect(r.bodyBytes, [4, 5, 6]);
        offset += r.bodyBytes.length;
        return http.Response(jsonEncode({'offset': offset}), 200);
      });
      double progress = 0;
      await repo.upload(
        scope,
        {'upload_id': 'u1'},
        IntakeFile(
          name: 'fixture.png',
          bytes: Uint8List.fromList([1, 2, 3, 4, 5, 6]),
          mimeType: 'image/png',
          sha256: 'a' * 64,
          method: 'files',
        ),
        (p) => progress = p,
      );
      expect(offsets, [3]);
      expect(progress, 1);
    },
  );

  test(
    'review submits server schema, revision and idempotency and never sets disposition',
    () async {
      Json? body;
      final repo = repository((r) async {
        if (r.method == 'POST') {
          body = jsonDecode(r.body) as Json;
          expect(r.headers['Idempotency-Key'], 'decision-stable');
          return http.Response('{}', 200);
        }
        return http.Response(jsonEncode(fixture['workspace_response']), 200);
      });
      await repo.review(
        scope,
        const Specimen({
          'specimen_id': 's1',
          'revision': 7,
          'latest_record_version_id': 'r1:7',
        }),
        {
          'kind': 'field_correction',
          'target_id': 'country',
          'state': 'unknown',
          'value': null,
          'reason': 'No visible evidence',
          'evidence_ids': [],
        },
        'decision-stable',
      );
      expect(body?['expected_revision'], 7);
      expect(body?['kind'], 'field');
      expect(body?['after'], {
        'literal': null,
        'state': 'unknown',
        'reason': 'No visible evidence',
      });
      expect(body?.containsKey('disposition'), false);
    },
  );

  test(
    'stale response stays a conflict and does not trigger automatic retry',
    () async {
      var calls = 0;
      final repo = repository((r) async {
        calls++;
        return http.Response(
          jsonEncode({
            'error': {'code': 'conflict', 'message': 'Stale record'},
          }),
          409,
        );
      });
      await expectLater(
        repo.review(
          scope,
          const Specimen({'specimen_id': 's', 'revision': 1}),
          {'kind': 'approve', 'reason': 'reviewed'},
          'same-key',
        ),
        throwsA(isA<ApiFailure>().having((e) => e.conflict, 'conflict', true)),
      );
      expect(calls, 1);
    },
  );

  test(
    'API credentials never follow redirects to a different origin',
    () async {
      final repo = repository((r) async {
        expect(r.followRedirects, false);
        return http.Response(
          '{}',
          302,
          headers: {'location': 'https://example.invalid'},
        );
      });
      await expectLater(repo.scopes(), throwsA(isA<ApiFailure>()));
    },
  );
  test(
    'field correction keeps literal, parsed and authority layers separate',
    () async {
      Json? body;
      final repo = repository((r) async {
        if (r.method == 'POST') {
          body = jsonDecode(r.body) as Json;
          return http.Response('{}', 200);
        }
        return http.Response(jsonEncode(fixture['workspace_response']), 200);
      });
      await repo.review(
        scope,
        const Specimen({
          'specimen_id': 's',
          'revision': 1,
          'latest_record_version_id': 'r:1',
        }),
        {
          'kind': 'field_correction',
          'target_id': 'country',
          'value': 'U.S.A.',
          'parsed': 'USA',
          'normalized': 'United States',
          'authority_id': 'source:US',
          'state': 'supported',
          'reason': 'Supported source',
          'evidence_ids': ['e1'],
        },
        'layers',
      );
      expect(body?['after']['literal'], 'U.S.A.');
      expect(body?['after']['normalized'], 'United States');
      expect(body?['after']['authority_id'], 'source:US');
    },
  );

  test(
    'region correction serializes original-pixel bounds without overwriting originals',
    () async {
      Json? body;
      final repo = repository((r) async {
        if (r.method == 'POST') {
          body = jsonDecode(r.body) as Json;
          expect(r.url.path.endsWith('/regions'), true);
          return http.Response('{}', 200);
        }
        return http.Response(jsonEncode(fixture['workspace_response']), 200);
      });
      await repo.review(
        scope,
        const Specimen({
          'specimen_id': 's',
          'revision': 1,
          'active_run_id': 'r',
          'assets': [
            {'asset_id': 'a'},
          ],
        }),
        {
          'kind': 'segmentation_correction',
          'reason': 'Missed label',
          'regions': [
            {
              'region_id': 'region1',
              'bbox': [10, 20, 110, 220],
              'order': 0,
            },
          ],
        },
        'regions',
      );
      expect(body?['regions'][0], {
        'id': 'region1',
        'asset_id': 'a',
        'x': 10,
        'y': 20,
        'width': 100,
        'height': 200,
        'order': 0,
        'method': 'human',
        'version': 'review-v1',
      });
      expect(body?['base_run_id'], 'r');
    },
  );
  test(
    'transcription abstention preserves typed unresolved state on the wire',
    () async {
      Json? body;
      final repo = repository((r) async {
        if (r.method == 'POST') {
          body = jsonDecode(r.body) as Json;
          return http.Response('{}', 200);
        }
        return http.Response(jsonEncode(fixture['workspace_response']), 200);
      });
      await repo.review(
        scope,
        const Specimen({
          'specimen_id': 's',
          'revision': 1,
          'latest_record_version_id': 'r:1',
        }),
        {
          'kind': 'transcription_adjudication',
          'target_id': 'region',
          'state': 'unreadable',
          'value': null,
          'reason': 'Source damaged',
          'evidence_ids': [],
        },
        'abstain-transcript',
      );
      expect(body?['kind'], 'transcription');
      expect(body?['after'], {'text': null, 'state': 'unreadable'});
    },
  );
  test(
    'history pages pin the review bound and authenticate every read',
    () async {
      final repo = repository((r) async {
        expect(r.headers['Authorization'], 'Bearer synthetic-test-token');
        expect(r.headers['X-Firebase-AppCheck'], 'synthetic-app-check');
        expect(r.url.path, '/v1/organizations/org/specimens/s/history');
        expect(r.url.queryParameters['through_revision'], '12');
        expect(r.url.queryParameters['limit'], '10');
        final after = int.parse(r.url.queryParameters['after_revision']!);
        return http.Response(
          jsonEncode({
            'items': [
              for (var n = after + 1; n <= (after == 0 ? 10 : 12); n++)
                {'revision': n, 'sha256': 'a' * 64},
            ],
            'through_revision': 12,
            'next_cursor': after == 0 ? 10 : null,
          }),
          200,
        );
      });
      final first = await repo.historyPage(scope, 's', throughRevision: 12);
      final next = await repo.historyPage(
        scope,
        's',
        throughRevision: 12,
        afterRevision: first.nextCursor!,
      );
      expect(first.items, hasLength(10));
      expect(next.items.map((e) => e['revision']), [11, 12]);
      expect(next.nextCursor, isNull);
    },
  );

  test(
    'history rejects gaps cursor stalls bound drift and omitted records',
    () async {
      for (final page in [
        {
          'items': [
            {'revision': 2, 'sha256': 'a' * 64},
          ],
          'through_revision': 3,
          'next_cursor': 2,
        },
        {
          'items': [
            {'revision': 1, 'sha256': 'a' * 64},
          ],
          'through_revision': 3,
          'next_cursor': 0,
        },
        {
          'items': [
            {'revision': 1, 'sha256': 'a' * 64},
          ],
          'through_revision': 4,
          'next_cursor': 1,
        },
        {'items': [], 'through_revision': 3, 'next_cursor': null},
        {
          'items': [null],
          'through_revision': 3,
          'next_cursor': null,
        },
      ]) {
        final repo = repository(
          (r) async => http.Response(jsonEncode(page), 200),
        );
        await expectLater(
          repo.historyPage(scope, 's', throughRevision: 3),
          throwsA(isA<ApiFailure>()),
        );
      }
    },
  );

  test(
    'historical references are scoped verified read only and keep current CAS',
    () async {
      final current = Specimen({
        ...fixture['workspace_response'] as Json,
        'specimen_id': 's',
        'revision': 12,
      });
      var historyRequests = 0;
      Json? edit;
      final repo = repository((r) async {
        if (r.url.path.endsWith('/history/2')) {
          historyRequests++;
          expect(r.headers['Authorization'], 'Bearer synthetic-test-token');
          expect(r.url.queryParameters, {
            'run_id': 'run-2',
            'run_sha256': 'b' * 64,
          });
          return http.Response(
            jsonEncode({
              ...fixture['workspace_response'] as Json,
              'specimen_id': 's',
              'revision': 2,
              'available_actions': ['approve'],
            }),
            200,
          );
        }
        if (r.method == 'POST') {
          edit = jsonDecode(r.body) as Json;
          return http.Response('{}', 200);
        }
        if (r.url.path.endsWith('/content')) {
          return http.Response.bytes([1], 200);
        }
        return http.Response(jsonEncode(current.data), 200);
      });
      final old = await repo.historicalSpecimen(
        scope,
        's',
        2,
        runId: 'run-2',
        runSha256: 'b' * 64,
      );
      expect(historyRequests, 1);
      expect(old.data['available_actions'], isEmpty);
      expect(old.assets.single['preview_bytes'], isNull);
      expect(current.revision, 12);
      await repo.review(scope, current, {
        'kind': 'approve',
        'reason': 'Reviewed',
      }, 'current-cas');
      expect(edit?['expected_revision'], 12);
    },
  );

  test(
    'historical identity mismatches revoked access and digest failures surface',
    () async {
      for (final status in [200, 403, 409]) {
        var calls = 0;
        final repo = repository((r) async {
          calls++;
          return http.Response(
            jsonEncode(
              status == 200
                  ? {
                      ...fixture['workspace_response'] as Json,
                      'specimen_id': 'other',
                      'revision': 2,
                    }
                  : {
                      'error': {
                        'code': 'history_unavailable',
                        'message': 'Unavailable',
                      },
                    },
            ),
            status,
          );
        });
        await expectLater(
          repo.historicalSpecimen(scope, 's', 2),
          throwsA(isA<ApiFailure>()),
        );
        expect(calls, 1);
      }
    },
  );
}
