import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/auth.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/pending_changes.dart';
import 'package:specimen_digitization/src/workspace.dart';

class _TestSession implements SessionAccess {
  final controller = StreamController<bool>.broadcast();
  @override
  bool get signedIn => true;
  @override
  String get userId => 'synthetic-reviewer';
  @override
  String get displayName => 'Synthetic reviewer';
  @override
  Stream<bool> get changes => controller.stream;
  @override
  Future<String?> token() async => 'synthetic-token';
  @override
  Future<void> signIn(String email, String password) async {}
  @override
  Future<void> signOut() async {}
  @override
  Future<void> resetPassword(String email) async {}
}

const scope = CollectionScope(
  organizationId: 'org',
  collectionId: 'collection',
  name: 'Synthetic collection',
  permissions: ['reviewer'],
);
const original = Specimen({
  'specimen_id': 's1',
  'revision': 18,
  'latest_record_version_id': 'run:18',
});

List<Json> choices() => [
  PendingFieldChange(
    fieldKey: 'county',
    displayName: 'County',
    state: 'supported',
    candidateSelectionId: 'a' * 64,
    candidateLabel: 'First source place',
    candidateValue: 'First normalized value',
  ).toChange('Evidence reviewed'),
  PendingFieldChange(
    fieldKey: 'city',
    displayName: 'City',
    state: 'supported',
    candidateSelectionId: 'b' * 64,
    candidateLabel: 'Second source place',
    candidateValue: 'Second normalized value',
  ).toChange('Evidence reviewed'),
];

ApiSpecimenRepository repository(
  Future<http.Response> Function(http.Request) handler, {
  String Function()? expectedUserId,
}) => ApiSpecimenRepository(
  baseUrl: Uri.parse('http://localhost:8000'),
  token: () async => 'synthetic-token',
  client: MockClient(handler),
  expectedUserId: expectedUserId,
);

Json workspace(int revision) => {
  'specimen_id': 's1',
  'organization_id': 'org',
  'collection_id': 'collection',
  'revision': revision,
  'record_version_id': 'run:$revision',
  'active_run_id': 'run',
  'fields': <String, dynamic>{},
};

Json answerFor(
  http.Request request, {
  List<String>? outcomes,
  bool artifact = false,
}) {
  final body = jsonDecode(request.body) as Json;
  final decisions = objects(body['decisions']);
  final states = outcomes ?? List<String>.filled(decisions.length, 'applied');
  return {
    'requested': decisions.length,
    'applied': states.where((state) => state == 'applied').length,
    'refused': states.where((state) => state == 'refused').length,
    'skipped': states.where((state) => state == 'skipped').length,
    'results': [
      for (final (index, decision) in decisions.indexed)
        {
          'index': index,
          'specimen_id': decision['specimen_id'],
          'kind': decision['kind'],
          'idempotency_key': decision['idempotency_key'],
          'outcome': states[index],
          if (states[index] == 'applied') ...{
            'revision': 19,
            'record_version_id': 'run:19',
            if (artifact) 'artifact_required': true,
          },
          if (states[index] == 'refused')
            'error': {
              'code': 'conflict',
              'status': 409,
              'message': 'Reopen the record',
            },
        },
    ],
  };
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test(
    'normal workspace Save sends two opaque choices in one CAS batch',
    () async {
      final session = _TestSession();
      final posts = <http.Request>[];
      var revision = 18;
      var workspaceReads = 0;
      final repo = repository((request) async {
        final path = request.url.path;
        if (path == '/v1/session') {
          return http.Response(
            jsonEncode({
              'user_id': session.userId,
              'mode': 'synthetic',
              'memberships': [
                {
                  'organization_id': 'org',
                  'collection_id': 'collection',
                  'role': 'reviewer',
                  'permissions': ['review'],
                },
              ],
            }),
            200,
          );
        }
        if (path.endsWith('/collections')) {
          return http.Response(
            jsonEncode({
              'items': [
                {
                  'collection_id': 'collection',
                  'display_name': 'Synthetic collection',
                },
              ],
            }),
            200,
          );
        }
        if (path.endsWith('/specimens')) {
          return http.Response(
            jsonEncode({
              'items': [workspace(revision)],
            }),
            200,
          );
        }
        if (path.endsWith('/specimens/s1/workspace')) {
          workspaceReads++;
          return http.Response(jsonEncode(workspace(revision)), 200);
        }
        if (path.endsWith('/decisions:batch')) {
          posts.add(request);
          revision = 19;
          return http.Response(jsonEncode(answerFor(request)), 200);
        }
        fail('Unexpected request: ${request.method} $path');
      }, expectedUserId: () => session.userId);
      final controller = WorkspaceController(
        repository: repo,
        session: session,
        pollInterval: const Duration(days: 1),
      );
      try {
        await controller.checkAccess();
        await controller.openSpecimen('s1');
        expect(controller.selected?.revision, 18);
        final saved = await controller.mutateBatch(
          choices(),
          'Evidence reviewed',
          stillApplies: (current, change) =>
              current.revision == 18 &&
              {'county', 'city'}.contains(change['target_id']),
        );
        expect(saved, 2);
        expect(controller.selected?.revision, 19);
        expect(controller.selected?.recordVersionId, 'run:19');
        expect(controller.error, isNull);
        expect(posts, hasLength(1));
        expect(workspaceReads, 2);
        final body = jsonDecode(posts.single.body) as Json;
        expect(body['reason'], 'Evidence reviewed');
        final decisions = objects(body['decisions']);
        expect(decisions.map((d) => d['kind']).toList(), [
          'research_candidate',
          'research_candidate',
        ]);
        expect(decisions.map((d) => d['target_id']).toList(), [
          'county',
          'city',
        ]);
        expect(decisions.map((d) => d['after']).toList(), [
          {'selection_id': 'a' * 64},
          {'selection_id': 'b' * 64},
        ]);
        expect(decisions.map((d) => d['expected_revision']).toSet(), {18});
        expect(decisions.map((d) => d['base_record_version_id']).toSet(), {
          'run:18',
        });
        expect(
          decisions.map((d) => d['idempotency_key']).toSet(),
          hasLength(2),
        );
        expect(decisions.every((d) => !d.containsKey('evidence_ids')), isTrue);
        expect(posts.single.headers['Idempotency-Key'], isNotEmpty);
      } finally {
        controller.dispose();
        repo.close();
        await session.controller.close();
      }
    },
  );

  test('all pending choices are checked before any batch is sent', () async {
    var calls = 0;
    final repo = repository((_) async {
      calls++;
      return http.Response('{}', 500);
    });
    final SpecimenRepository typed = repo;
    final result = await typed.reviewBatch(
      scope,
      original,
      choices(),
      'Evidence reviewed',
      'first',
      stillApplies: (current, change) => change['target_id'] != 'city',
    );
    expect((result.saved, result.stopped), (0, true));
    expect(calls, 0);
    repo.close();
  });

  test('a candidate and a separate field correction share one save', () async {
    Json? sent;
    final repo = repository((request) async {
      if (request.method == 'GET') {
        return http.Response(jsonEncode(workspace(19)), 200);
      }
      sent = jsonDecode(request.body) as Json;
      return http.Response(jsonEncode(answerFor(request)), 200);
    });
    final SpecimenRepository typed = repo;
    final result = await typed.reviewBatch(
      scope,
      original,
      [
        choices().first,
        {
          'kind': 'field_correction',
          'target_id': 'habitat',
          'value': 'Forest edge',
          'state': 'supported',
          'evidence_ids': ['retained-evidence-1'],
        },
      ],
      'Evidence reviewed',
      'mixed',
    );
    expect(result.saved, 2);
    final decisions = objects(sent?['decisions']);
    expect(decisions.map((d) => d['kind']).toList(), [
      'research_candidate',
      'field',
    ]);
    expect(decisions.first['after'], {'selection_id': 'a' * 64});
    expect(decisions.first.containsKey('evidence_ids'), isFalse);
    expect(decisions.last['after'], {
      'literal': 'Forest edge',
      'state': 'supported',
      'reason': 'Evidence reviewed',
    });
    expect(decisions.last['evidence_ids'], ['retained-evidence-1']);
    repo.close();
  });

  test('workspace retries an uncertain batch with its original keys', () async {
    final session = _TestSession();
    final posts = <http.Request>[];
    var revision = 18;
    final repo = repository((request) async {
      final path = request.url.path;
      if (path == '/v1/session') {
        return http.Response(
          jsonEncode({
            'user_id': session.userId,
            'mode': 'synthetic',
            'memberships': [
              {
                'organization_id': 'org',
                'collection_id': 'collection',
                'role': 'reviewer',
              },
            ],
          }),
          200,
        );
      }
      if (path.endsWith('/collections')) {
        return http.Response(
          jsonEncode({
            'items': [
              {'collection_id': 'collection'},
            ],
          }),
          200,
        );
      }
      if (path.endsWith('/specimens')) {
        return http.Response(
          jsonEncode({
            'items': [workspace(revision)],
          }),
          200,
        );
      }
      if (path.endsWith('/specimens/s1/workspace')) {
        return http.Response(jsonEncode(workspace(revision)), 200);
      }
      if (path.endsWith('/decisions:batch')) {
        posts.add(request);
        if (posts.length == 1) throw http.ClientException('answer lost');
        revision = 19;
        return http.Response(jsonEncode(answerFor(request)), 200);
      }
      fail('Unexpected request: ${request.method} $path');
    }, expectedUserId: () => session.userId);
    final controller = WorkspaceController(
      repository: repo,
      session: session,
      pollInterval: const Duration(days: 1),
    );
    try {
      await controller.checkAccess();
      await controller.openSpecimen('s1');
      expect(await controller.mutateBatch(choices(), 'Evidence reviewed'), 0);
      expect(controller.selected?.revision, 18);
      expect(await controller.mutateBatch(choices(), 'Evidence reviewed'), 2);
      expect(controller.selected?.revision, 19);
      expect(posts, hasLength(2));
      expect(
        posts[0].headers['Idempotency-Key'],
        posts[1].headers['Idempotency-Key'],
      );
      final first = objects((jsonDecode(posts[0].body) as Json)['decisions']);
      final second = objects((jsonDecode(posts[1].body) as Json)['decisions']);
      expect(
        first.map((d) => d['idempotency_key']).toList(),
        second.map((d) => d['idempotency_key']).toList(),
      );
    } finally {
      controller.dispose();
      repo.close();
      await session.controller.close();
    }
  });

  test(
    'a refused candidate group reports zero saved without readback',
    () async {
      var reads = 0;
      final repo = repository((request) async {
        if (request.method == 'GET') reads++;
        return http.Response(
          jsonEncode(answerFor(request, outcomes: ['refused', 'skipped'])),
          200,
        );
      });
      final SpecimenRepository typed = repo;
      await expectLater(
        typed.reviewBatch(
          scope,
          original,
          choices(),
          'Evidence reviewed',
          'batch',
        ),
        throwsA(
          isA<ReviewBatchFailure>()
              .having((failure) => failure.saved, 'saved', 0)
              .having(
                (failure) => (failure.cause as ApiFailure).code,
                'code',
                'conflict',
              ),
        ),
      );
      expect(reads, 0);
      repo.close();
    },
  );

  test(
    'partial and malformed acknowledgements cannot become full success',
    () async {
      for (final corrupt in [false, true]) {
        var reads = 0;
        final repo = repository((request) async {
          if (request.method == 'GET') {
            reads++;
            return http.Response(jsonEncode(workspace(19)), 200);
          }
          final result = answerFor(
            request,
            outcomes: corrupt ? null : ['applied', 'refused'],
          );
          if (corrupt) {
            (result['results'] as List)[1]['idempotency_key'] = 'wrong-key';
          }
          return http.Response(jsonEncode(result), 200);
        });
        final SpecimenRepository typed = repo;
        await expectLater(
          typed.reviewBatch(
            scope,
            original,
            choices(),
            'Evidence reviewed',
            'batch',
          ),
          throwsA(
            isA<ReviewBatchFailure>().having(
              (failure) => failure.saved,
              'saved',
              corrupt ? 0 : 1,
            ),
          ),
        );
        expect(reads, corrupt ? 0 : 1);
        repo.close();
      }
    },
  );

  test('an acknowledged save keeps its count when readback is stale', () async {
    final repo = repository(
      (request) async => request.method == 'POST'
          ? http.Response(jsonEncode(answerFor(request)), 200)
          : http.Response(jsonEncode(workspace(18)), 200),
    );
    final SpecimenRepository typed = repo;
    await expectLater(
      typed.reviewBatch(
        scope,
        original,
        choices(),
        'Evidence reviewed',
        'batch',
      ),
      throwsA(
        isA<ReviewBatchFailure>()
            .having((failure) => failure.saved, 'saved', 2)
            .having((failure) => failure.retainKeys, 'retain keys', isTrue)
            .having(
              (failure) => (failure.cause as ApiFailure).code,
              'code',
              'batch_readback_mismatch',
            ),
      ),
    );
    repo.close();
  });

  test(
    'uncertain retry reuses the same batch key despite a new prefix',
    () async {
      final batchKeys = <String>[];
      var posts = 0;
      final repo = repository((request) async {
        if (request.method == 'GET') {
          return http.Response(jsonEncode(workspace(19)), 200);
        }
        posts++;
        batchKeys.add(request.headers['Idempotency-Key']!);
        if (posts == 1) throw http.ClientException('response lost');
        return http.Response(jsonEncode(answerFor(request)), 200);
      });
      final SpecimenRepository typed = repo;
      String stableKey(Specimen current, Json change, int index) =>
          '${current.id}:${current.revision}:${change['target_id']}:$index';
      await expectLater(
        typed.reviewBatch(
          scope,
          original,
          choices(),
          'Evidence reviewed',
          'new-1',
          keyFor: stableKey,
        ),
        throwsA(
          isA<ReviewBatchFailure>()
              .having((failure) => failure.saved, 'saved', 0)
              .having((failure) => failure.retainKeys, 'retain keys', isTrue),
        ),
      );
      final result = await typed.reviewBatch(
        scope,
        original,
        choices(),
        'Evidence reviewed',
        'new-2',
        keyFor: stableKey,
      );
      expect(result.saved, 2);
      expect(batchKeys, hasLength(2));
      expect(batchKeys[0], batchKeys[1]);
      repo.close();
    },
  );

  test(
    'a membership identity switch cannot turn an old answer into success',
    () async {
      var principal = 'original-reviewer';
      var reads = 0;
      final repo = repository((request) async {
        if (request.method == 'GET') reads++;
        principal = 'new-reviewer';
        return http.Response(jsonEncode(answerFor(request)), 200);
      }, expectedUserId: () => principal);
      final SpecimenRepository typed = repo;
      await expectLater(
        typed.reviewBatch(
          scope,
          original,
          choices(),
          'Evidence reviewed',
          'batch',
        ),
        throwsA(
          isA<ReviewBatchFailure>()
              .having((failure) => failure.saved, 'saved', 0)
              .having(
                (failure) => (failure.cause as ApiFailure).code,
                'code',
                'access_changed',
              ),
        ),
      );
      expect(reads, 0);
      repo.close();
    },
  );

  test('a server access denial cannot claim a candidate save', () async {
    var reads = 0;
    final repo = repository((request) async {
      if (request.method == 'GET') reads++;
      return http.Response(
        jsonEncode({
          'error': {
            'code': 'permission_denied',
            'message': 'Review role required',
          },
        }),
        403,
      );
    });
    final SpecimenRepository typed = repo;
    await expectLater(
      typed.reviewBatch(
        scope,
        original,
        choices(),
        'Evidence reviewed',
        'batch',
      ),
      throwsA(
        isA<ReviewBatchFailure>()
            .having((failure) => failure.saved, 'saved', 0)
            .having(
              (failure) => (failure.cause as ApiFailure).status,
              'status',
              403,
            ),
      ),
    );
    expect(reads, 0);
    repo.close();
  });

  test('ordinary-only corrections retain their sequential decisions', () async {
    final paths = <String>[];
    var revision = 18;
    final repo = repository((request) async {
      paths.add(request.url.path);
      if (request.method == 'POST') {
        final body = jsonDecode(request.body) as Json;
        expect(body['expected_revision'], revision);
        revision++;
        return http.Response('{}', 200);
      }
      return http.Response(jsonEncode(workspace(revision)), 200);
    });
    final SpecimenRepository typed = repo;
    final result = await typed.reviewBatch(
      scope,
      original,
      [
        {'kind': 'field_correction', 'target_id': 'county', 'state': 'unknown'},
        {'kind': 'field_correction', 'target_id': 'city', 'state': 'unknown'},
      ],
      'No source evidence',
      'ordinary',
    );
    expect(result.saved, 2);
    expect(result.specimen.revision, 20);
    expect(paths.where((path) => path.endsWith('/decisions')).length, 2);
    expect(paths.where((path) => path.endsWith('/decisions:batch')), isEmpty);
    repo.close();
  });

  test(
    'artifact-required readback retains a committed two-choice count',
    () async {
      final repo = repository((request) async {
        final path = request.url.path;
        if (request.method == 'POST') {
          return http.Response(
            jsonEncode(answerFor(request, artifact: true)),
            200,
          );
        }
        if (path.endsWith('/workspace')) {
          return http.Response(
            jsonEncode({
              'error': {
                'code': 'workspace_artifact_required',
                'message': 'Use the summary',
                'details': {'revision': 19, 'record_version_id': 'run:19'},
              },
            }),
            413,
          );
        }
        return http.Response(jsonEncode(workspace(19)), 200);
      });
      final SpecimenRepository typed = repo;
      final result = await typed.reviewBatch(
        scope,
        original,
        choices(),
        'Evidence reviewed',
        'batch',
      );
      expect(result.saved, 2);
      expect(result.specimen.revision, 19);
      expect(result.specimen.recordVersionId, 'run:19');
      expect(result.specimen.data['artifact_receipt'], isA<Map>());
      repo.close();
    },
  );
}
