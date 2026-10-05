import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/auth.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/fields_panel.dart';
import 'package:specimen_digitization/src/screens/workbench/pending_changes.dart';
import 'package:specimen_digitization/src/screens/workbench/status_strip.dart';
import 'package:specimen_digitization/src/widgets/widgets.dart';
import 'package:specimen_digitization/src/workbench.dart';
import 'package:specimen_digitization/src/workspace.dart';

import 'ui_finders.dart';
import 'workbench_harness.dart';

class _TestSession implements SessionAccess {
  final controller = StreamController<bool>.broadcast();
  String principal = 'synthetic-reviewer';
  @override
  bool get signedIn => true;
  @override
  String get userId => principal;
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

Json reviewWorkspace(int revision) => {
  ...workspace(revision),
  'available_actions': ['field'],
  'operational_state': 'completed',
  'disposition': 'needs_human_review',
  'fields': {
    'county': {'value_state': 'unknown', 'literal': null},
    'city': {'value_state': 'unknown', 'literal': null},
  },
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
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

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
        expect(saved.saved, 2);
        expect(saved.confirmed?.revision, 19);
        expect(saved.requiresReconciliation, isFalse);
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
      final uncertain = await controller.mutateBatch(
        choices(),
        'Evidence reviewed',
      );
      expect(uncertain.saved, 0);
      expect(uncertain.requiresReconciliation, isTrue);
      expect(controller.selected?.revision, 18);
      final confirmed = await controller.mutateBatch(
        choices(),
        'Evidence reviewed',
      );
      expect(confirmed.saved, 2);
      expect(confirmed.confirmed?.revision, 19);
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
    'mixed and malformed acknowledgements cannot become a saved prefix',
    () async {
      for (final shape in ['applied-first', 'refused-first', 'corrupt']) {
        var reads = 0;
        final repo = repository((request) async {
          if (request.method == 'GET') {
            reads++;
            return http.Response(jsonEncode(workspace(19)), 200);
          }
          final result = answerFor(
            request,
            outcomes: switch (shape) {
              'applied-first' => ['applied', 'refused'],
              'refused-first' => ['refused', 'applied'],
              _ => null,
            },
          );
          if (shape == 'corrupt') {
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
              0,
            ),
          ),
        );
        expect(reads, 0);
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

  test('a lost readback also keeps the known committed count', () async {
    final repo = repository(
      (request) async => request.method == 'POST'
          ? http.Response(jsonEncode(answerFor(request)), 200)
          : throw http.ClientException('readback unavailable'),
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
            .having((failure) => failure.saved, 'known committed', 2)
            .having((failure) => failure.retainKeys, 'retry keys', isTrue)
            .having((failure) => failure.specimen.revision, 'old view', 18),
      ),
    );
    repo.close();
  });

  test(
    'workspace preserves known commits and keys until a newer readback',
    () async {
      final session = _TestSession();
      final posts = <http.Request>[];
      var revision = 18;
      var readAfterPost = 0;
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
          if (posts.isNotEmpty) readAfterPost++;
          return http.Response(
            jsonEncode(workspace(readAfterPost == 1 ? 18 : revision)),
            200,
          );
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
        final first = await controller.mutateBatch(
          choices(),
          'Evidence reviewed',
        );
        expect(first.saved, 2);
        expect(first.confirmed, isNull);
        expect(first.requiresReconciliation, isTrue);
        expect(controller.selected?.revision, 18);
        final retry = await controller.mutateBatch(
          choices(),
          'Evidence reviewed',
        );
        expect(retry.saved, 2);
        expect(retry.confirmed?.revision, 19);
        expect(retry.requiresReconciliation, isFalse);
        expect(controller.selected?.revision, 19);
        expect(posts, hasLength(2));
        expect(
          posts.first.headers['Idempotency-Key'],
          posts.last.headers['Idempotency-Key'],
        );
        final firstEntries = objects(
          (jsonDecode(posts.first.body) as Json)['decisions'],
        );
        final retryEntries = objects(
          (jsonDecode(posts.last.body) as Json)['decisions'],
        );
        expect(
          firstEntries.map((entry) => entry['idempotency_key']).toList(),
          retryEntries.map((entry) => entry['idempotency_key']).toList(),
        );
      } finally {
        controller.dispose();
        repo.close();
        await session.controller.close();
      }
    },
  );

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

  for (final firstReadback in [
    'stale',
    'network',
    'unknown',
    'wrong-version',
    'changed-account',
    'edited',
  ]) {
    testWidgets(
      'real $firstReadback outcome handles two choices on scoped refresh',
      (tester) async {
        useWindow(tester, largeWindow);
        final session = _TestSession();
        var serverRevision = 18;
        var detailReadsAfterCommit = 0;
        var posts = 0;
        String? countyLiteral;
        bool? navigationBlocked;
        Future<bool> Function()? exitGuard;
        Future<void>? refresh;
        ReviewBatchSaveOutcome? initialOutcome;
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
                'items': [workspace(serverRevision)],
              }),
              200,
            );
          }
          if (path.endsWith('/specimens/s1/workspace')) {
            if (posts > 0) detailReadsAfterCommit++;
            if (detailReadsAfterCommit == 1 && firstReadback != 'unknown') {
              if (firstReadback == 'network') {
                throw http.ClientException('first readback unavailable');
              }
              return http.Response(jsonEncode(reviewWorkspace(18)), 200);
            }
            if (firstReadback == 'wrong-version' && posts > 0) {
              return http.Response(
                jsonEncode({
                  ...reviewWorkspace(19),
                  'record_version_id': 'unrelated:19',
                  'disposition': 'cleared',
                }),
                200,
              );
            }
            if (firstReadback == 'unknown' && posts > 0) {
              return http.Response(
                jsonEncode({...reviewWorkspace(19), 'disposition': 'cleared'}),
                200,
              );
            }
            return http.Response(
              jsonEncode({
                ...reviewWorkspace(serverRevision),
                if (countyLiteral != null)
                  'fields': {
                    ...reviewWorkspace(serverRevision)['fields'] as Json,
                    'county': {
                      'value_state': 'unknown',
                      'literal': countyLiteral,
                    },
                  },
              }),
              200,
            );
          }
          if (path.endsWith('/decisions:batch')) {
            posts++;
            serverRevision = 19;
            final answer = answerFor(request);
            if (firstReadback == 'unknown') {
              (answer['results'] as List)[1]['idempotency_key'] = 'invalid';
            }
            return http.Response(jsonEncode(answer), 200);
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
          await tester.pumpWidget(
            workbenchHost(
              AnimatedBuilder(
                animation: controller,
                builder: (context, _) => controller.selected == null
                    ? const SizedBox.shrink()
                    : ReviewWorkbench(
                        specimen: controller.selected!,
                        reviewerId: session.userId,
                        onChange: (change) async => false,
                        onChangeBatch: (changes, reason, stillApplies) async {
                          final result = await controller.mutateBatch(
                            changes,
                            reason,
                            stillApplies: stillApplies,
                          );
                          initialOutcome ??= result;
                          return result;
                        },
                        verifyBatchReadback:
                            controller.isAcknowledgedBatchReadback,
                        onExitGuardChanged: (guard, active) {
                          exitGuard = active ? guard : null;
                        },
                        onNavigationBlockedChanged: (blocked) {
                          navigationBlocked = blocked;
                        },
                        onRetry: (reason) async {},
                        onRefresh: () {
                          refresh = controller.refresh();
                        },
                      ),
              ),
            ),
          );
          await tester.pumpAndSettle();
          await tester.tap(find.text('Specimen data'));
          await tester.pumpAndSettle();
          tester
              .widget<WorkbenchFields>(find.byType(WorkbenchFields))
              .onPendingChanged([
                PendingFieldChange(
                  fieldKey: 'county',
                  displayName: 'County',
                  state: 'supported',
                  candidateSelectionId: 'a' * 64,
                  baseLiteral: null,
                ),
                PendingFieldChange(
                  fieldKey: 'city',
                  displayName: 'City',
                  state: 'supported',
                  candidateSelectionId: 'b' * 64,
                  baseLiteral: null,
                ),
              ]);
          await tester.pumpAndSettle();
          await tester.tap(find.text('Save 2 pending changes').last);
          await tester.pumpAndSettle();
          await tester.enterText(uiField('Reason'), 'Compared both sources');
          await tester.pumpAndSettle();
          await tester.tap(
            find.descendant(
              of: find.byType(ReasonForm),
              matching: uiButton('Save 2 pending changes'),
            ),
          );
          await tester.pumpAndSettle();
          expect(posts, 1);
          final known = firstReadback != 'unknown';
          expect(initialOutcome?.saved, known ? 2 : 0);
          expect(initialOutcome?.confirmed, isNull);
          expect(initialOutcome?.acknowledgement?.revision, known ? 19 : null);
          expect(
            initialOutcome?.acknowledgement?.recordVersionId,
            known ? 'run:19' : null,
          );
          expect(controller.selected?.revision, 18);
          if (known) {
            expect(
              controller.isAcknowledgedBatchReadback(
                initialOutcome!.acknowledgement!,
                controller.selected!,
              ),
              isFalse,
            );
          }
          expect(
            tester
                .widget<WorkbenchFields>(find.byType(WorkbenchFields))
                .pending,
            hasLength(2),
          );
          expect(
            tester
                .widget<WorkbenchStatusStrip>(find.byType(WorkbenchStatusStrip))
                .saved,
            isFalse,
          );
          if (firstReadback == 'edited') {
            tester
                .widget<WorkbenchFields>(find.byType(WorkbenchFields))
                .onPendingChanged([
                  PendingFieldChange(
                    fieldKey: 'county',
                    displayName: 'County',
                    state: 'supported',
                    candidateSelectionId: 'a' * 64,
                    baseLiteral: null,
                  ),
                  PendingFieldChange(
                    fieldKey: 'city',
                    displayName: 'City',
                    state: 'supported',
                    candidateSelectionId: 'c' * 64,
                    baseLiteral: null,
                  ),
                ]);
            await tester.pumpAndSettle();
          }
          if (firstReadback == 'changed-account') {
            session.principal = 'different-reviewer';
          }
          await tester.tap(find.text('Refresh and compare'));
          await refresh;
          await tester.pumpAndSettle();
          if (firstReadback == 'changed-account') {
            expect(controller.selected, isNull);
            expect(controller.scopesVerified, isFalse);
            expect(posts, 1);
            return;
          }
          expect(controller.selected?.revision, 19);
          expect(
            controller.selected?.recordVersionId,
            firstReadback == 'wrong-version' ? 'unrelated:19' : 'run:19',
          );
          expect(
            controller.selected?.fields.map((field) => field['literal_value']),
            everyElement(isNull),
            reason: 'candidate review preserves original label literals',
          );
          final reconciled = !{
            'unknown',
            'wrong-version',
            'changed-account',
          }.contains(firstReadback);
          if (known) {
            expect(
              controller.isAcknowledgedBatchReadback(
                initialOutcome!.acknowledgement!,
                controller.selected!,
              ),
              reconciled,
            );
          }
          expect(posts, 1, reason: 'refresh reconciles the original CAS');
          expect(
            tester
                .widget<WorkbenchFields>(find.byType(WorkbenchFields))
                .pending,
            isEmpty,
          );
          final status = tester.widget<WorkbenchStatusStrip>(
            find.byType(WorkbenchStatusStrip),
          );
          if (reconciled && firstReadback != 'edited') {
            expect(status.reconciliationMessage, isNull);
            expect(status.saved, isTrue);
            expect(status.staleChanges, isEmpty);
          } else {
            expect(status.saved, isFalse);
            if (firstReadback == 'edited') {
              expect(status.reconciliationMessage, isNull);
              expect(status.staleChanges, hasLength(1));
              expect(status.staleChanges.single.candidateSelectionId, 'c' * 64);
            } else if (firstReadback != 'changed-account') {
              expect(status.reconciliationMessage, contains('did not confirm'));
              expect(status.staleChanges, hasLength(2));
              expect(find.text('Review current fields'), findsOneWidget);
              expect(find.text('Saved'), findsNothing);
            }
          }
          final oldTokenRetry = await controller.mutateBatch(
            choices(),
            'Compared both sources',
          );
          expect(oldTokenRetry.saved, 0);
          expect(
            posts,
            1,
            reason: 'old selection IDs must not be rebased to Q19',
          );
          if (firstReadback == 'edited') {
            expect(navigationBlocked, isTrue);
            final keepEditing = exitGuard!();
            await tester.pumpAndSettle();
            expect(find.text('Discard unsaved corrections?'), findsOneWidget);
            await tester.tap(uiButton('Keep editing'));
            await tester.pumpAndSettle();
            expect(await keepEditing, isFalse);
            expect(
              tester
                  .widget<WorkbenchStatusStrip>(
                    find.byType(WorkbenchStatusStrip),
                  )
                  .staleChanges
                  .single
                  .candidateSelectionId,
              'c' * 64,
            );

            // A later edit going stale must preserve the earlier quarantined
            // choice as well; both remain guarded until explicitly discarded.
            tester
                .widget<WorkbenchFields>(find.byType(WorkbenchFields))
                .onPendingChanged([
                  PendingFieldChange(
                    fieldKey: 'county',
                    displayName: 'County',
                    state: 'supported',
                    candidateSelectionId: 'd' * 64,
                    baseLiteral: null,
                  ),
                ]);
            await tester.pumpAndSettle();
            countyLiteral = 'Changed by another reviewer';
            serverRevision = 20;
            await controller.refresh();
            await tester.pumpAndSettle();
            final later = tester.widget<WorkbenchStatusStrip>(
              find.byType(WorkbenchStatusStrip),
            );
            expect(
              later.staleChanges.map((change) => change.candidateSelectionId),
              containsAll(['c' * 64, 'd' * 64]),
            );
            expect(later.staleChanges, hasLength(2));
            expect(navigationBlocked, isTrue);
            final discard = exitGuard!();
            await tester.pumpAndSettle();
            expect(find.text('Discard unsaved corrections?'), findsOneWidget);
            await tester.tap(uiButton('Discard changes'));
            await tester.pumpAndSettle();
            expect(await discard, isTrue);
            expect(find.byType(WorkbenchStatusStrip), findsNothing);
            expect(navigationBlocked, isFalse);
          }
        } finally {
          await tester.pumpWidget(const SizedBox());
          controller.dispose();
          repo.close();
          await session.controller.close();
        }
      },
    );
  }

  for (final quietCase in [
    'matching-ack',
    'different-version',
    'malformed-ack',
  ]) {
    final quietRevision = quietCase == 'different-version' ? 20 : 19;
    final malformedAck = quietCase == 'malformed-ack';
    testWidgets(
      'quiet $quietCase refresh before failed save answer checks batch',
      (tester) async {
        useWindow(tester, largeWindow);
        final session = _TestSession();
        final blockedReadback = Completer<http.Response>();
        final blockedPostAnswer = Completer<http.Response>();
        final inFlightStarted = Completer<void>();
        var serverRevision = 18;
        var posts = 0;
        var blockedOnce = false;
        http.Request? postedRequest;
        ReviewBatchSaveOutcome? repositoryOutcome;
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
                'items': [workspace(serverRevision)],
              }),
              200,
            );
          }
          if (path.endsWith('/specimens/s1/workspace')) {
            if (!malformedAck && posts > 0 && !blockedOnce) {
              blockedOnce = true;
              inFlightStarted.complete();
              return blockedReadback.future;
            }
            return http.Response(
              jsonEncode(reviewWorkspace(serverRevision)),
              200,
            );
          }
          if (path.endsWith('/decisions:batch')) {
            posts++;
            postedRequest = request;
            serverRevision = 19;
            if (malformedAck) {
              inFlightStarted.complete();
              return blockedPostAnswer.future;
            }
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
          await tester.pumpWidget(
            workbenchHost(
              AnimatedBuilder(
                animation: controller,
                builder: (context, _) => controller.selected == null
                    ? const SizedBox.shrink()
                    : ReviewWorkbench(
                        specimen: controller.selected!,
                        reviewerId: session.userId,
                        onChange: (change) async => false,
                        onChangeBatch: (changes, reason, stillApplies) async {
                          final result = await controller.mutateBatch(
                            changes,
                            reason,
                            stillApplies: stillApplies,
                          );
                          repositoryOutcome = result;
                          return result;
                        },
                        verifyBatchReadback:
                            controller.isAcknowledgedBatchReadback,
                        onRetry: (reason) async {},
                        onRefresh: () => unawaited(controller.refresh()),
                      ),
              ),
            ),
          );
          await tester.pumpAndSettle();
          await tester.tap(find.text('Specimen data'));
          await tester.pumpAndSettle();
          tester
              .widget<WorkbenchFields>(find.byType(WorkbenchFields))
              .onPendingChanged([
                PendingFieldChange(
                  fieldKey: 'county',
                  displayName: 'County',
                  state: 'supported',
                  candidateSelectionId: 'a' * 64,
                  baseLiteral: null,
                ),
                PendingFieldChange(
                  fieldKey: 'city',
                  displayName: 'City',
                  state: 'supported',
                  candidateSelectionId: 'b' * 64,
                  baseLiteral: null,
                ),
              ]);
          await tester.pumpAndSettle();
          await tester.tap(find.text('Save 2 pending changes').last);
          await tester.pumpAndSettle();
          await tester.enterText(uiField('Reason'), 'Compared both sources');
          await tester.pumpAndSettle();
          await tester.tap(
            find.descendant(
              of: find.byType(ReasonForm),
              matching: uiButton('Save 2 pending changes'),
            ),
          );
          await tester.pump();
          await inFlightStarted.future;
          expect(posts, 1);
          expect(controller.selected?.revision, 18);

          // The poll completes before the save's readback and ticket. Q+2 must
          // remain unproven even though its original label literals are equal.
          serverRevision = quietRevision;
          await controller.refresh(quiet: true);
          await tester.pump();
          expect(controller.selected?.revision, quietRevision);
          expect(controller.selected?.recordVersionId, 'run:$quietRevision');
          expect(
            controller.selected?.fields.map((field) => field['literal_value']),
            everyElement(isNull),
            reason:
                'unchanged label literals cannot prove candidate acceptance',
          );
          if (malformedAck) {
            final answer = answerFor(postedRequest!);
            (answer['results'] as List)[1]['idempotency_key'] = 'invalid';
            blockedPostAnswer.complete(http.Response(jsonEncode(answer), 200));
          } else {
            blockedReadback.complete(
              http.Response(jsonEncode(reviewWorkspace(18)), 200),
            );
          }
          await tester.pumpAndSettle();
          expect(repositoryOutcome?.saved, malformedAck ? 0 : 2);
          expect(repositoryOutcome?.requiresReconciliation, isTrue);
          if (malformedAck) {
            expect(repositoryOutcome?.acknowledgement, isNull);
          } else {
            expect(
              controller.isAcknowledgedBatchReadback(
                repositoryOutcome!.acknowledgement!,
                controller.selected!,
              ),
              quietCase == 'matching-ack',
            );
          }
          final reconciled = tester.widget<WorkbenchStatusStrip>(
            find.byType(WorkbenchStatusStrip),
          );
          expect(reconciled.saved, quietCase == 'matching-ack');
          if (quietCase == 'matching-ack') {
            expect(reconciled.reconciliationMessage, isNull);
            expect(reconciled.staleChanges, isEmpty);
          } else {
            expect(
              reconciled.reconciliationMessage,
              contains('did not confirm'),
            );
            expect(reconciled.staleChanges, hasLength(2));
            expect(
              reconciled.staleChanges.map(
                (choice) => choice.candidateSelectionId,
              ),
              containsAll(['a' * 64, 'b' * 64]),
            );
            expect(find.text('Review current fields'), findsOneWidget);
            expect(find.text('Saved'), findsNothing);
          }
          expect(
            tester
                .widget<WorkbenchFields>(find.byType(WorkbenchFields))
                .pending,
            isEmpty,
          );
          expect(find.textContaining('Version 18.'), findsNothing);

          await controller.refresh();
          await tester.pumpAndSettle();
          expect(controller.selected?.revision, quietRevision);
          expect(
            tester
                .widget<WorkbenchStatusStrip>(find.byType(WorkbenchStatusStrip))
                .saved,
            quietCase == 'matching-ack',
          );
          if (quietCase != 'matching-ack') {
            final retry = await controller.mutateBatch(
              choices(),
              'Compared both sources',
            );
            expect(retry.saved, 0);
            expect(find.text('Saved'), findsNothing);
          }
          expect(posts, 1);
        } finally {
          await tester.pumpWidget(const SizedBox());
          controller.dispose();
          repo.close();
          await session.controller.close();
        }
      },
    );
  }

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
