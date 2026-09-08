import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/reading_alignment.dart';

void main() {
  final fixture =
      jsonDecode(
            File(
              'test/fixtures/backend-next-wire-examples.json',
            ).readAsStringSync(),
          )
          as Json;
  final workspace = fixture['workspace_before_selection'] as Json;
  final specimen = Specimen(workspace);
  final scope = CollectionScope(
    organizationId: workspace['organization_id'],
    collectionId: workspace['collection_id'],
    name: 'Synthetic',
  );
  ApiSpecimenRepository repo(
    Future<http.Response> Function(http.Request) handle,
  ) => ApiSpecimenRepository(
    baseUrl: Uri.parse('http://localhost:8014'),
    token: () async => 'test-only',
    client: MockClient((r) async {
      expect(r.headers['Authorization'], 'Bearer test-only');
      expect(r.followRedirects, isFalse);
      return handle(r);
    }),
  );
  test(
    'named search is one bounded opaque page and preserves server matches',
    () async {
      var calls = 0;
      final repository = repo((r) async {
        calls++;
        expect(r.url.queryParameters['limit'], '50');
        expect(r.url.queryParameters['risk_min'], '0');
        expect(r.url.queryParameters['reason_code'], 'some_issue');
        expect(r.url.queryParameters.containsKey('q'), isFalse);
        expect(
          r.url.queryParameters['cursor'],
          calls == 1 ? null : 'opaque+cursor/=',
        );
        return http.Response(
          jsonEncode({
            ...fixture['search_page'],
            'next_cursor': calls == 1 ? 'opaque+cursor/=' : null,
          }),
          200,
        );
      });
      final first = await repository.specimenPage(
        scope,
        filters: {'risk_min': '0', 'reason_code': 'some_issue'},
      );
      expect(calls, 1);
      expect(first.items, hasLength(1));
      final second = await repository.specimenPage(
        scope,
        filters: {'risk_min': '0', 'reason_code': 'some_issue'},
        cursor: first.nextCursor,
      );
      expect(second.nextCursor, isNull);
      expect(calls, 2);
    },
  );
  test(
    'typed artifacts pin revision and disambiguate authority field',
    () async {
      final repository = repo((r) async {
        expect(r.url.queryParameters['revision'], '${specimen.revision}');
        if (r.url.path.endsWith('/authority-results/parties')) {
          expect(r.url.queryParameters['field_key'], 'identified_by_irn');
          return http.Response(jsonEncode(fixture['authority_result']), 200);
        }
        if (r.url.path.endsWith('/phases/lookup')) {
          return http.Response(jsonEncode(fixture['lookup_phase']), 200);
        }
        if (r.url.path.endsWith('/metadata')) {
          return http.Response(jsonEncode(fixture['reading_metadata']), 200);
        }
        return http.Response(jsonEncode(fixture['reading_alignment']), 200);
      });
      final authority = await repository.artifact(
        scope,
        specimen,
        const ArtifactRequest(
          ArtifactKind.authority,
          'parties',
          fieldKey: 'identified_by_irn',
        ),
      );
      expect(
        authority['candidates'],
        fixture['authority_result']['candidates'],
      );
      expect(authority['candidates'][0]['identity']['module'], 'eparties');
      expect(
        (await repository.artifact(
          scope,
          specimen,
          const ArtifactRequest(ArtifactKind.phase, 'lookup'),
        ))['phase'],
        'lookup',
      );
      expect(
        (await repository.artifact(
          scope,
          specimen,
          const ArtifactRequest(ArtifactKind.readingMetadata, 'observation'),
        ))['language_state'],
        'unknown',
      );
      expect(
        (await repository.artifact(
          scope,
          specimen,
          const ArtifactRequest(ArtifactKind.disagreement, 'region'),
        ))['status'],
        'agreement',
      );
    },
  );
  test(
    'raw evidence digest, size, access and UTF8 are checked without partial display',
    () async {
      List<int> body = utf8.encode('😀a\r\nb');
      var status = 200;
      final repository = repo((r) async => http.Response.bytes(body, status));
      final request = ArtifactRequest(
        ArtifactKind.observationRaw,
        'o',
        sha256: sha256.convert(body).toString(),
      );
      expect(
        (await repository.artifact(scope, specimen, request))['text'],
        '😀a\r\nb',
      );
      body = [0xff];
      await expectLater(
        repository.artifact(scope, specimen, request),
        throwsA(
          isA<ApiFailure>().having((e) => e.code, 'code', 'evidence_digest'),
        ),
      );
      body = List.filled(1048577, 65);
      await expectLater(
        repository.artifact(scope, specimen, request),
        throwsA(
          isA<ApiFailure>().having((e) => e.code, 'code', 'evidence_limit'),
        ),
      );
      body = [];
      status = 403;
      await expectLater(
        repository.artifact(scope, specimen, request),
        throwsA(isA<ApiFailure>().having((e) => e.status, 'status', 403)),
      );
    },
  );
  test(
    'authority selection uses exact retained candidate and current CAS',
    () async {
      final expected = fixture['authority_resolution']['request'] as Json;
      final repository = repo((r) async {
        if (r.method == 'POST') {
          final data = jsonDecode(r.body) as Json;
          expect(data['after'], expected['after']);
          expect(data['target_id'], expected['target_id']);
          expect(data['expected_revision'], specimen.revision);
          expect(
            data['base_record_version_id'],
            workspace['record_version_id'],
          );
          return http.Response(
            jsonEncode(fixture['authority_resolution']['response']),
            200,
          );
        }
        if (r.url.path.endsWith('/content')) {
          return http.Response.bytes([1], 200);
        }
        return http.Response(jsonEncode(workspace), 200);
      });
      await repository.review(
        scope,
        Specimen({
          ...workspace,
          'latest_record_version_id': workspace['record_version_id'],
        }),
        {
          'kind': 'authority_resolution',
          'target_id': expected['target_id'],
          'tool_id': expected['after']['tool_id'],
          'identifier': expected['after']['identifier'],
          'reason': expected['reason'],
        },
        'synthetic-selection',
      );
      expect(
        workspace['fields']['identified_by_irn']['literal'],
        'Synthetic Collector',
      );
    },
  );
  test(
    'server preflight sends original bytes explicitly and rejects mismatched identity',
    () async {
      var response = Map<String, dynamic>.from(
        fixture['server_preflight_default_policy'],
      );
      final bytes = Uint8List.fromList([1, 2, 3]);
      final file = IntakeFile(
        name: 'source.png',
        bytes: bytes,
        mimeType: 'image/png',
        sha256: sha256.convert(bytes).toString(),
        method: 'upload',
      );
      final repository = repo((r) async {
        expect(r.method, 'POST');
        expect(r.url.path.endsWith('/images/preflight'), isTrue);
        expect(r.headers['Content-Type'], 'image/png');
        expect(r.bodyBytes, bytes);
        return http.Response(jsonEncode(response), 200);
      });
      await expectLater(
        repository.preflight(scope, file),
        throwsA(isA<ApiFailure>()),
      );
      response = {
        ...response,
        'input_sha256': file.sha256,
        'size_bytes': bytes.length,
      };
      expect((await repository.preflight(scope, file))['status'], 'blocked');
    },
  );
  test(
    'serialized astral CRLF offsets retain exact raw span and bounded input is not agreement',
    () {
      final alignment = fixture['standalone_unicode_alignment_example'];
      final span = alignment['alternatives'][0]['left'];
      expect(
        exactUtf16Span(
          '😀a\r\nb',
          span['start']['utf16_codeunit'],
          span['end']['utf16_codeunit'],
        ),
        'b',
      );
      final blocked = fixture['standalone_bounded_alignment_example'];
      expect(blocked['status'], 'policy_blocked');
      expect(blocked['alternatives'], isEmpty);
      expect(blocked['edit_distance'], isNull);
    },
  );
}
