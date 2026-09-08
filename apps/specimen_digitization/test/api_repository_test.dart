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
}
