import 'dart:convert';
import 'dart:io';
import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/large_record.dart';
import 'package:specimen_digitization/src/workbench.dart';

void main() {
  final fixture =
      jsonDecode(
            File(
              'test/fixtures/backend-graph-wire-examples.json',
            ).readAsStringSync(),
          )
          as Json;
  final summary = fixture['summary_get']['body'] as Json;
  final receipt = fixture['workspace_get']['body']['error']['details'] as Json;
  final scope = CollectionScope(
    organizationId: summary['organization_id'],
    collectionId: summary['collection_id'],
    name: 'Synthetic graph',
  );
  final current = Specimen({
    ...summary,
    'latest_record_version_id': summary['record_version_id'],
  });
  test(
    'actual GET and committed mutation receipts preserve revision without repeating POST',
    () async {
      int posts = 0;
      bool committed = false, unavailable = false;
      final repo = ApiSpecimenRepository(
        baseUrl: Uri.parse('http://localhost:8014'),
        token: () async => 'test-only',
        client: MockClient((request) async {
          if (request.method == 'POST') {
            posts++;
            final body = jsonDecode(request.body);
            expect(body['expected_revision'], 57);
            expect(
              body['base_record_version_id'],
              current.data['latest_record_version_id'],
            );
            committed = true;
            return http.Response(
              jsonEncode(fixture['committed_mutation']['response']['body']),
              413,
            );
          }
          if (request.url.path.endsWith('/workspace')) {
            return http.Response(
              jsonEncode(fixture['workspace_get']['body']),
              413,
            );
          }
          if (unavailable) {
            return http.Response(
              '{"error":{"code":"forbidden","message":"Summary unavailable"}}',
              503,
            );
          }
          return http.Response(
            jsonEncode(committed ? fixture['summary_after_mutation'] : summary),
            200,
          );
        }),
      );
      final loaded = await repo.specimen(scope, current.id);
      expect(loaded.data['artifact_receipt'], receipt);
      expect(loaded.revision, 57);
      expect(loaded.data['available_actions'], contains('cancel'));
      unavailable = true;
      final saved = await repo.review(scope, current, {
        'kind': 'coverage',
        'reason': 'Synthetic review',
      }, 'one-key');
      expect(posts, 1);
      expect(saved.revision, 58);
      expect(saved.data['mutation_saved'], true);
      expect(saved.data['available_actions'], isEmpty);
      expect(saved.data['artifact_summary_error'], 'Summary unavailable');
    },
  );
  test(
    'graph is scope and revision pinned, digest checked and bounded, ignoring supplied URLs',
    () async {
      final graph = {
        'contract_version': 'active-run-v1',
        'scope': {
          'organization_id': scope.organizationId,
          'collection_id': scope.collectionId,
        },
        'specimen_id': current.id,
        'revision': 57,
        'run': {
          'id': current.data['active_run_id'],
          'observations': 'é😀' * 20000,
        },
      };
      final bytes = utf8.encode(jsonEncode(graph));
      final digest = sha256.convert(bytes).toString();
      final record = Specimen({
        ...current.data,
        'artifact_receipt': {
          ...receipt,
          'artifact_url': 'https://untrusted.invalid/leak',
          'artifact_size_bytes': bytes.length,
          'artifact_sha256': digest,
        },
      });
      var fault = '';
      final repo = ApiSpecimenRepository(
        baseUrl: Uri.parse('http://localhost:8014'),
        token: () async => 'current-test-token',
        client: MockClient((request) async {
          expect(request.url.host, 'localhost');
          expect(
            request.url.path.endsWith('/specimens/${current.id}/active-graph'),
            true,
          );
          expect(request.url.queryParameters, {'revision': '57'});
          expect(request.headers['Authorization'], 'Bearer current-test-token');
          return http.Response.bytes(
            fault == 'limit'
                ? List.filled(16777217, 0)
                : fault == 'body'
                ? [...bytes, 32]
                : bytes,
            fault == 'access' ? 403 : 200,
            headers: {
              'x-content-sha256': fault == 'header' ? 'wrong' : digest,
              'x-specimen-revision': '57',
            },
          );
        }),
      );
      Future<Json> read({String? hash}) => repo.artifact(
        scope,
        record,
        ArtifactRequest(
          ArtifactKind.activeGraph,
          record.id,
          sha256: hash ?? digest,
        ),
      );
      expect(await read(), graph);
      await expectLater(
        read(hash: 'wrong'),
        throwsA(
          isA<ApiFailure>().having((e) => e.code, 'code', 'invalid_evidence'),
        ),
      );
      fault = 'body';
      await expectLater(
        read(),
        throwsA(
          isA<ApiFailure>().having((e) => e.code, 'code', 'evidence_digest'),
        ),
      );
      fault = 'header';
      await expectLater(
        read(),
        throwsA(
          isA<ApiFailure>().having((e) => e.code, 'code', 'invalid_evidence'),
        ),
      );
      fault = 'limit';
      await expectLater(
        read(),
        throwsA(
          isA<ApiFailure>().having((e) => e.code, 'code', 'evidence_limit'),
        ),
      );
      fault = 'access';
      await expectLater(
        read(),
        throwsA(isA<ApiFailure>().having((e) => e.status, 'status', 403)),
      );
      fault = '';
      await expectLater(
        read(),
        throwsA(
          isA<ApiFailure>().having((e) => e.status, 'latched denial', 403),
        ),
      );
      repo.close();
    },
  );
  test('historical 413 stays pinned and grants no current controls', () async {
    final repo = ApiSpecimenRepository(
      baseUrl: Uri.parse('http://localhost:8014'),
      token: () async => 'test-only',
      client: MockClient((request) async {
        expect(request.url.path.endsWith('/history/57'), true);
        return http.Response(jsonEncode(fixture['workspace_get']['body']), 413);
      }),
    );
    final historical = await repo.historicalSpecimen(scope, current.id, 57);
    expect(historical.revision, 57);
    expect(historical.data['available_actions'], isEmpty);
    expect(historical.data['artifact_receipt'], receipt);
  });
  testWidgets(
    'committed large record stays read-only with controls and bounded complete text pages',
    (tester) async {
      final semantics = tester.ensureSemantics();
      final record = Specimen({
        ...current.data,
        'artifact_receipt': receipt,
        'mutation_saved': true,
      });
      int loads = 0;
      final value = 'q' * 13000 + '😀 end';
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ReviewWorkbench(
              specimen: record,
              onChange: (_) async {},
              onRetry: (_) async {},
              onRefresh: () {},
              loadArtifact: (_) async {
                loads++;
                return {
                  'contract_version': 'active-run-v1',
                  'run': {'observations': value},
                };
              },
            ),
          ),
        ),
      );
      expect(
        find.textContaining('Action saved at revision 57'),
        findsOneWidget,
      );
      expect(find.text('Approve record'), findsNothing);
      expect(loads, 0);
      await tester.tap(find.text('Load complete evidence'));
      await tester.pumpAndSettle();
      expect(loads, 1);
      await tester.tap(find.byType(DropdownButtonFormField<String>));
      await tester.pumpAndSettle();
      await tester.tap(find.text('observations').last);
      await tester.pumpAndSettle();
      expect(find.text('Text page 1 of 2'), findsOneWidget);
      expect(
        tester
            .widgetList<Text>(
              find.descendant(
                of: find.byType(LargeRecordEvidence),
                matching: find.byType(Text),
              ),
            )
            .every((t) => (t.data?.length ?? 0) <= 12000),
        true,
      );
      await tester.ensureVisible(find.text('Next text page'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Next text page'));
      await tester.pumpAndSettle();
      expect(find.textContaining('😀 end'), findsOneWidget);
      expect(find.bySemanticsLabel(RegExp('😀 end')), findsOneWidget);
      semantics.dispose();
    },
  );
}
