import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/research/research_host.dart';
import 'package:specimen_digitization/src/research/research_models.dart';
import 'package:specimen_digitization/src/research/research_repository.dart';
import 'package:specimen_digitization/src/research/research_thread_card.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'research_fixture.dart';

const canonicalRunId = '44444444-4444-4444-8444-444444444444';
const nativeRecordVersions = <int, String>{
  1: '55555555-5555-4555-8555-555555555555',
  2: '66666666-6666-4666-8666-666666666666',
  3: '88888888-8888-4888-8888-888888888888',
};
const secondSpecimenId = '77777777-7777-4777-8777-777777777777';
final trusted = ResearchScope.fromJson({
  ...trustedResearchScope().json,
  'organization_id': '11111111-1111-4111-8111-111111111111',
  'collection_id': '22222222-2222-4222-8222-222222222222',
  'specimen_id': '33333333-3333-4333-8333-333333333333',
});
final collection = CollectionScope(
  organizationId: trusted.organizationId,
  collectionId: trusted.collectionId,
  name: 'Test collection',
);
Specimen item([String? id, int revision = 1]) => Specimen({
  'specimen_id': id ?? trusted.specimenId,
  'revision': revision,
  'active_run_id': canonicalRunId,
  'record_version_id': '$canonicalRunId:$revision',
  'sensitive': trusted.sensitive,
  'asset': {'sensitive': trusted.sensitive},
});
Json discovery([String? id, int revision = 1]) => {
  'contract_version': 'canonical-binding/v2',
  'canonical': {
    'organization_id': collection.organizationId,
    'collection_id': collection.collectionId,
    'specimen_id': id ?? trusted.specimenId,
    'record_revision': revision,
    'record_version_id': nativeRecordVersions[revision]!,
    'canonical_run_id': canonicalRunId,
    'host_record_version_id': '$canonicalRunId:$revision',
    'snapshot_sha256': List.filled(64, '$revision').join(),
    'sensitive': trusted.sensitive,
  },
  'scope': {...trusted.json, 'specimen_id': id ?? trusted.specimenId},
  'capabilities': {'read': true, 'retry': false, 'review': false},
  'human_locked_fields': <String>[],
};

Json historicalDiscovery(int currentRevision) => {
  ...discovery(),
  'historical': true,
  'canonical_revision': 1,
  'review_saved_revision': 2,
  'current_host': {
    'organization_id': collection.organizationId,
    'collection_id': collection.collectionId,
    'specimen_id': trusted.specimenId,
    'canonical_run_id': canonicalRunId,
    'record_revision': currentRevision,
    'host_record_version_id': '$canonicalRunId:$currentRevision',
    'sensitive': trusted.sensitive,
  },
};

class HostApi extends ApiSpecimenRepository {
  HostApi(this.respond)
    : super(
        baseUrl: Uri.parse('https://api.example.test'),
        token: () async => 'test-only-token',
      );
  final Future<Json> Function(String path) respond;
  final paths = <String>[];
  final calls = <Json>[];
  final failures = StreamController<ApiFailure>.broadcast(sync: true);
  @override
  Stream<ApiFailure> get accessFailures => failures.stream;
  @override
  Future<Json> request(
    String method,
    String path, {
    Json? body,
    String? key,
    Map<String, String>? query,
    dynamic bytes,
    Map<String, String>? headers,
    int? verificationEpoch,
  }) {
    paths.add('$method $path');
    calls.add({'method': method, 'path': path, 'body': body, 'key': key});
    return respond(path);
  }

  @override
  void close() {
    failures.close();
    super.close();
  }
}

Future<void> pumpHost(
  WidgetTester tester,
  HostApi api,
  Specimen specimen, {
  Widget Function(
    BuildContext,
    Widget Function(String, ValueChanged<ResearchReviewCandidate>?),
  )?
  builder,
  Future<void> Function()? refreshRecord,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light(),
      home: Scaffold(
        body: SingleChildScrollView(
          child: ResearchHost(
            repository: api,
            collection: collection,
            specimen: specimen,
            builder: builder,
            refreshRecord: refreshRecord,
          ),
        ),
      ),
    ),
  );
  await tester.pump();
}

Map<String, dynamic> countryReviewThread({
  bool historical = false,
  bool includeCountryReview = true,
  bool includeHistoricalCandidate = false,
  bool omitCounty = false,
}) {
  final json = researchFixture('failed-thread')..['scope'] = trusted.json;
  for (final field in json['fields'] as List) {
    if (field['checkpoint'] != null) {
      field['checkpoint']['scope'] = trusted.json;
    }
  }
  json['resolved_count'] = 0;
  final country = fixtureField(json, 'country');
  country['work_state'] = 'waiting_human';
  final resolution = country['checkpoint']['resolution'];
  resolution['work_state'] = 'waiting_human';
  resolution['question'] = {
    'field_key': 'country',
    'question': 'Which country does this location describe?',
    'reason': 'scoped_absence',
    'coverage': [
      {
        'source_id': 'field_museum_ipt',
        'field_key': 'country',
        'state': 'exhausted',
        'source_version': 'fixture-v1',
        'qualification_digest': 'a' * 64,
        'exact_join_attempted': true,
        'query_digest': 'b' * 64,
        'receipt_ids': ['country-coverage'],
        'candidate_count': 0,
        'coverage_limit': 'bounded test scope',
        'reason': 'Search exhausted within the fixture scope.',
      },
    ],
    'evidence_ids': [],
  };
  country['actions'] = ['review_proposal'];
  country['review'] = {
    'question_reason': 'scoped_absence',
    'reason': 'The available place details leave a location question.',
    'evidence': [],
    'candidates': [],
    'evidence_not_shown': 0,
    'candidates_not_shown': 0,
  };
  if (includeHistoricalCandidate) {
    country['review']['candidates'] = [
      {
        'label': 'Old retained place',
        'source_id': 'geolocate',
        'selection_id': 'f' * 64,
        'selection_value': 'Old source value',
      },
    ];
  }
  if (!includeCountryReview) {
    country['review'] = null;
    country['actions'] = [];
    country['checkpoint'] = null;
    country['work_state'] = 'pending';
    country['blocker_code'] = null;
  }
  if (historical) {
    json['historical'] = true;
    json['canonical_revision'] = 1;
    json['review_saved_revision'] = 2;
  }
  if (omitCounty) {
    (json['fields'] as List).removeWhere(
      (field) => (field as Map)['field_key'] == 'county',
    );
  }
  return json;
}

Map<String, dynamic> derivationCapability({
  bool available = true,
  int revision = 1,
}) => {
  'contract_version': 'research-derivation-capability/v1',
  'available': available,
  'blocked_reason': available ? null : 'worker_unavailable',
  'canonical_revision': revision,
  'eligible_fields': available ? ['province_state', 'county'] : <String>[],
};

Map<String, dynamic> derivationResult({
  required String requestId,
  String status = 'running',
  int revision = 2,
  int sourceRevision = 1,
  bool includeProposal = false,
}) => {
  'contract_version': 'research-derivation-result/v1',
  'request_id': requestId,
  'source_revision': sourceRevision,
  'queued_revision': sourceRevision + 1,
  'status': status,
  'canonical_revision': revision,
  'stale': false,
  'proposals': includeProposal
      ? [
          {
            'field_key': 'county',
            'value': 'Synthetic County',
            'input_fields': ['country'],
            'input_revisions': [
              ['country', 1],
            ],
            'evidence_ids': ['retained-evidence'],
            'authority_id': 'retained-authority',
            'dataset_ids': ['geoboundaries/PH/ADM2'],
            'tool_call_id': 'retained-tool-call',
            'value_layer': 'derived',
            'rule_version': 'georeference-v1',
            'checkpoint_id': 'c' * 64,
            'checkpoint_revision': 2,
            'effect_id': 'd' * 64,
            'selection_id': 'e' * 64,
            'source_id': 'georeference_spatial',
          },
        ]
      : <Object>[],
};

void main() {
  test(
    'discovery binds the host version before and after publication',
    () async {
      for (final revision in [1, 2]) {
        final current = item(null, revision);
        final payload = discovery(null, revision);
        expect(
          payload['canonical']['record_version_id'],
          isNot(current.recordVersionId),
        );
        final repository = ApiResearchRepository(
          request: (method, path, {body}) async => payload,
        );
        final scope = await repository.discover(collection, current);
        expect(scope.matches(trusted), isTrue);
      }
    },
  );

  test(
    'discovery rejects stale or missing host versions and foreign scope',
    () async {
      for (final kind in [
        'stale-host',
        'missing-host',
        'native-as-host',
        'scope',
        'revision-type',
        'stale-revision',
      ]) {
        final payload = discovery();
        if (kind == 'stale-host') {
          payload['canonical']['host_record_version_id'] = '$canonicalRunId:0';
        }
        if (kind == 'missing-host') {
          payload['canonical'].remove('host_record_version_id');
          // A matching native ID must not become a legacy fallback.
          payload['canonical']['record_version_id'] = item().recordVersionId;
        }
        if (kind == 'native-as-host') {
          payload['canonical']['host_record_version_id'] =
              nativeRecordVersions[1];
        }
        if (kind == 'scope') payload['scope']['collection_id'] = 'foreign';
        if (kind == 'revision-type') {
          payload['canonical']['record_revision'] = 1.0;
        }
        if (kind == 'stale-revision') {
          payload['canonical']['record_revision'] = 2;
        }
        final repository = ApiResearchRepository(
          request: (method, path, {body}) async => payload,
        );
        await expectLater(
          repository.discover(collection, item()),
          throwsA(
            isA<ResearchFailure>().having(
              (e) => e.kind,
              'kind',
              ResearchFailureKind.invalidResponse,
            ),
          ),
        );
      }
    },
  );

  test(
    'historical discovery binds a fresh host without rewriting source proof',
    () async {
      for (final revision in [2, 3]) {
        final payload = historicalDiscovery(revision);
        final source = payload['canonical'] as Map;
        expect(source['record_revision'], 1);
        expect(source['record_version_id'], nativeRecordVersions[1]);
        final repository = ApiResearchRepository(
          request: (method, path, {body}) async => payload,
        );
        final scope = await repository.discover(
          collection,
          item(null, revision),
        );
        expect(scope.matches(trusted), isTrue);
      }
    },
  );

  test('saved Q21 source reopens at Q22 and later same-run Q23', () async {
    for (final currentRevision in [22, 23]) {
      // The connected offline Save returned this source/current revision shape.
      // The old native UUID and digest remain source proof, not host authority.
      final payload = historicalDiscovery(currentRevision);
      final source = payload['canonical'] as Map;
      source['record_revision'] = 21;
      source['record_version_id'] = 'ddcff5f7-322d-51a8-96a9-9e7ba36414d7';
      source['host_record_version_id'] = '$canonicalRunId:21';
      // Public digest of the retained synthetic offline snapshot.
      source['snapshot_sha256'] =
          '28fd17ae53be797563077a9e332184c88f34c98863dc96621013dcdf18b2d9a7'; // pragma: allowlist secret
      source['sensitive'] = false;
      (payload['scope'] as Map)['sensitive'] = false;
      (payload['current_host'] as Map)['sensitive'] = false;
      payload['canonical_revision'] = 21;
      payload['review_saved_revision'] = 22;
      final opened = Specimen({
        ...item(null, currentRevision).data,
        'sensitive': false,
        'asset': {'sensitive': false},
      });
      final repository = ApiResearchRepository(
        request: (method, path, {body}) async => payload,
      );
      final scope = await repository.discover(collection, opened);
      expect(scope.sensitive, isFalse);
      expect(
        source['record_version_id'],
        'ddcff5f7-322d-51a8-96a9-9e7ba36414d7',
      );
    }
  });

  test(
    'historical discovery refuses stale host, false source or actions',
    () async {
      for (final damage in [
        'missing-host',
        'stale-host',
        'foreign-host',
        'wrong-run',
        'wrong-sensitive',
        'source-run',
        'source-sensitive',
        'source-host',
        'source-native-id',
        'source-digest',
        'source-revision',
        'saved-revision',
        'future-saved',
        'retry-capability',
        'review-capability',
      ]) {
        final payload = historicalDiscovery(2);
        final source = payload['canonical'] as Map;
        final host = payload['current_host'] as Map;
        switch (damage) {
          case 'missing-host':
            payload.remove('current_host');
          case 'stale-host':
            host['record_revision'] = 1;
            host['host_record_version_id'] = '$canonicalRunId:1';
          case 'foreign-host':
            host['collection_id'] = secondSpecimenId;
          case 'wrong-run':
            host['canonical_run_id'] = secondSpecimenId;
          case 'wrong-sensitive':
            host['sensitive'] = !trusted.sensitive;
          case 'source-run':
            source['canonical_run_id'] = secondSpecimenId;
          case 'source-sensitive':
            source['sensitive'] = !trusted.sensitive;
          case 'source-host':
            source['host_record_version_id'] = '$canonicalRunId:2';
          case 'source-native-id':
            source['record_version_id'] = 'not-a-native-uuid';
          case 'source-digest':
            source['snapshot_sha256'] = 'not-a-digest';
          case 'source-revision':
            payload['canonical_revision'] = 2;
          case 'saved-revision':
            payload['review_saved_revision'] = 3;
          case 'future-saved':
            payload['review_saved_revision'] = 4;
          case 'retry-capability':
            (payload['capabilities'] as Map)['retry'] = true;
          case 'review-capability':
            (payload['capabilities'] as Map)['review'] = true;
        }
        final repository = ApiResearchRepository(
          request: (method, path, {body}) async => payload,
        );
        await expectLater(
          repository.discover(collection, item(null, 2)),
          throwsA(
            isA<ResearchFailure>().having(
              (error) => error.kind,
              'kind',
              ResearchFailureKind.invalidResponse,
            ),
          ),
          reason: damage,
        );
      }
      final stale = ApiResearchRepository(
        request: (method, path, {body}) async => historicalDiscovery(2),
      );
      await expectLater(
        stale.discover(collection, item(null, 3)),
        throwsA(
          isA<ResearchFailure>().having(
            (error) => error.kind,
            'kind',
            ResearchFailureKind.invalidResponse,
          ),
        ),
      );
    },
  );

  testWidgets('production host discovers once and leaves field reads lazy', (
    tester,
  ) async {
    final api = HostApi((_) async => discovery());
    addTearDown(api.close);
    await pumpHost(tester, api, item());
    expect(
      find.byType(ResearchThreadCard),
      findsNWidgets(researchFieldKeys.length),
    );
    expect(api.paths, hasLength(1));
    expect(api.paths.single, endsWith('/research/current'));
    await tester.pump();
    expect(api.paths, hasLength(1));
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('revocation during discovery cannot restore field access', (
    tester,
  ) async {
    final pending = Completer<Json>();
    final api = HostApi((_) => pending.future);
    addTearDown(api.close);
    await pumpHost(tester, api, item());
    api.failures.add(const ApiFailure('Denied', status: 403));
    pending.complete(discovery());
    await tester.pump();
    expect(find.byType(ResearchThreadCard), findsNothing);
    expect(
      find.text('Research access is unavailable for this collection.'),
      findsOneWidget,
    );
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('switching records discards an earlier discovery response', (
    tester,
  ) async {
    final first = Completer<Json>();
    final second = Completer<Json>();
    final api = HostApi(
      (path) => path.contains('/specimens/$secondSpecimenId/')
          ? second.future
          : first.future,
    );
    addTearDown(api.close);
    await pumpHost(tester, api, item());
    await pumpHost(tester, api, item(secondSpecimenId));
    expect(api.paths, hasLength(2));
    first.complete(discovery());
    await tester.pump();
    expect(find.byType(ResearchThreadCard), findsNothing);
    second.complete(discovery(secondSpecimenId));
    await tester.pumpAndSettle();
    final cards = tester.widgetList<ResearchThreadCard>(
      find.byType(ResearchThreadCard),
    );
    expect(cards, hasLength(researchFieldKeys.length));
    expect(
      cards.every((card) => card.scope.specimenId == secondSpecimenId),
      isTrue,
    );
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets(
    'Fill the rest appears only when the current server capability allows it',
    (tester) async {
      final calls = <String>[];
      final api = HostApi((path) async {
        if (path.endsWith('/research/current')) return discovery();
        if (path.endsWith('/research/jobs/job/generations/1/thread')) {
          return countryReviewThread();
        }
        if (path.endsWith('/research/derivations/capability')) {
          calls.add(path);
          return derivationCapability(available: false);
        }
        return {};
      });
      addTearDown(api.close);
      await pumpHost(
        tester,
        api,
        item(),
        builder: (context, researchForField) =>
            researchForField('country', (_) {}),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Research'));
      await tester.pumpAndSettle();

      expect(calls, hasLength(1));
      expect(find.text('Fill the rest'), findsNothing);
    },
  );

  testWidgets(
    'repository replacement after revocation uses the fresh derivation transport',
    (tester) async {
      final requestId = 'b' * 64;
      HostApi makeApi() => HostApi((path) async {
        if (path.endsWith('/research/current')) return discovery();
        if (path.endsWith('/research/jobs/job/generations/1/thread')) {
          return countryReviewThread();
        }
        if (path.endsWith('/research/derivations/capability')) {
          return derivationCapability();
        }
        if (path.endsWith('/research/derivations')) {
          return {
            'contract_version': 'research-derivation-accepted/v1',
            'request_id': requestId,
            'source_revision': 1,
            'queued_revision': 2,
            'status': 'queued',
            'canonical_run_id': canonicalRunId,
          };
        }
        if (path.endsWith('/research/derivations/$requestId')) {
          return derivationResult(requestId: requestId);
        }
        return {};
      });

      final oldApi = makeApi();
      final newApi = makeApi();
      addTearDown(oldApi.close);
      addTearDown(newApi.close);
      Widget builder(
        BuildContext context,
        Widget Function(String, ValueChanged<ResearchReviewCandidate>?)
        researchForField,
      ) => researchForField('country', (_) {});

      await pumpHost(tester, oldApi, item(), builder: builder);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Research'));
      await tester.pumpAndSettle();
      expect(find.text('Fill the rest'), findsOneWidget);
      expect(
        oldApi.paths.any(
          (path) => path.endsWith('/research/derivations/capability'),
        ),
        isTrue,
      );

      oldApi.failures.add(const ApiFailure('Denied', status: 403));
      await tester.pumpAndSettle();
      expect(find.byType(ResearchThreadCard), findsNothing);

      final oldApiPathCount = oldApi.paths.length;
      await pumpHost(tester, newApi, item(), builder: builder);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Research'));
      await tester.pumpAndSettle();

      expect(find.text('Fill the rest'), findsOneWidget);
      expect(
        newApi.paths.any(
          (path) => path.endsWith('/research/derivations/capability'),
        ),
        isTrue,
      );
      expect(oldApi.paths, hasLength(oldApiPathCount));
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets(
    'current capability enables a request beside a historical report without a field review',
    (tester) async {
      final requestId = 'c' * 64;
      final api = HostApi((path) async {
        if (path.endsWith('/research/current')) return historicalDiscovery(2);
        if (path.endsWith('/research/jobs/job/generations/1/thread')) {
          return countryReviewThread(
            historical: true,
            includeCountryReview: false,
          );
        }
        if (path.endsWith('/research/derivations/capability')) {
          return derivationCapability(revision: 2);
        }
        if (path.endsWith('/research/derivations')) {
          return {
            'contract_version': 'research-derivation-accepted/v1',
            'request_id': requestId,
            'source_revision': 2,
            'queued_revision': 3,
            'status': 'queued',
            'canonical_run_id': canonicalRunId,
          };
        }
        if (path.endsWith('/research/derivations/$requestId')) {
          return derivationResult(
            requestId: requestId,
            status: 'completed',
            sourceRevision: 2,
            revision: 3,
            includeProposal: true,
          );
        }
        return {};
      });
      addTearDown(api.close);
      await pumpHost(
        tester,
        api,
        item(null, 2),
        builder: (context, researchForField) =>
            researchForField('country', (_) {}),
      );
      await tester.pumpAndSettle();

      final countryCard = find.byKey(
        const ValueKey('research:33333333-3333-4333-8333-333333333333:country'),
      );
      await tester.tap(
        find.descendant(of: countryCard, matching: find.text('Research')),
      );
      await tester.pumpAndSettle();
      expect(
        find.textContaining('Historical research report for'),
        findsOneWidget,
      );
      expect(find.text('Fill the rest'), findsOneWidget);
      expect(find.text('Use this possibility'), findsNothing);

      await tester.tap(find.text('Fill the rest'));
      await tester.pumpAndSettle();
      await tester.enterText(
        find.byType(TextField),
        'Review the remaining place information.',
      );
      await tester.tap(find.text('Request suggestions'));
      await tester.pumpAndSettle();

      final post = api.calls.singleWhere((call) => call['method'] == 'POST');
      expect(post['body']['expected_record_revision'], 2);
      expect(post['body']['requested_fields'], isNotEmpty);
      expect(find.text('Synthetic County'), findsNothing);
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets(
    'historical field candidates stay disabled while current capability is available',
    (tester) async {
      final api = HostApi((path) async {
        if (path.endsWith('/research/current')) return historicalDiscovery(2);
        if (path.endsWith('/research/jobs/job/generations/1/thread')) {
          return countryReviewThread(
            historical: true,
            includeHistoricalCandidate: true,
          );
        }
        if (path.endsWith('/research/derivations/capability')) {
          return derivationCapability(revision: 2);
        }
        return {};
      });
      addTearDown(api.close);
      ResearchReviewCandidate? selected;
      await pumpHost(
        tester,
        api,
        item(null, 2),
        builder: (context, researchForField) =>
            researchForField('country', (candidate) => selected = candidate),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Research'));
      await tester.pumpAndSettle();

      expect(find.text('Fill the rest'), findsOneWidget);
      expect(find.text('Old retained place'), findsOneWidget);
      final oldChoice = tester.widget<UiButton>(
        find.ancestor(
          of: find.text('Use this possibility'),
          matching: find.byType(UiButton),
        ),
      );
      expect(oldChoice.onPressed, isNull);
      await tester.tap(find.text('Use this possibility'), warnIfMissed: false);
      expect(selected, isNull);
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets(
    'current derivation proposal stays selectable when a historical thread lacks its field',
    (tester) async {
      final requestId = 'b' * 64;
      var currentRevision = 2;
      ResearchReviewCandidate? selected;
      final api = HostApi((path) async {
        if (path.endsWith('/research/current')) {
          return discovery(null, currentRevision);
        }
        if (path.endsWith('/research/jobs/job/generations/1/thread')) {
          return countryReviewThread(historical: true, omitCounty: true);
        }
        if (path.endsWith('/research/derivations/capability')) {
          return derivationCapability(revision: currentRevision);
        }
        if (path.endsWith('/research/derivations')) {
          return {
            'contract_version': 'research-derivation-accepted/v1',
            'request_id': requestId,
            'source_revision': currentRevision,
            'queued_revision': currentRevision + 1,
            'status': 'queued',
            'canonical_run_id': canonicalRunId,
          };
        }
        if (path.endsWith('/research/derivations/$requestId')) {
          return derivationResult(
            requestId: requestId,
            status: 'completed',
            sourceRevision: currentRevision,
            revision: currentRevision + 1,
            includeProposal: true,
          );
        }
        return {};
      });
      addTearDown(api.close);
      Widget builder(
        BuildContext context,
        Widget Function(String, ValueChanged<ResearchReviewCandidate>?)
        researchForField,
      ) => Column(
        children: [
          researchForField('country', (_) {}),
          researchForField('county', (candidate) => selected = candidate),
        ],
      );
      await pumpHost(
        tester,
        api,
        item(null, currentRevision),
        builder: builder,
      );
      await tester.pumpAndSettle();

      final countryCard = find.byKey(
        const ValueKey('research:33333333-3333-4333-8333-333333333333:country'),
      );
      await tester.tap(
        find.descendant(of: countryCard, matching: find.text('Research')),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Fill the rest'));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('derive-field-county')));
      await tester.pump();
      await tester.enterText(
        find.byType(TextField),
        'Review the remaining place information.',
      );
      await tester.tap(find.text('Request suggestions'));
      await tester.pumpAndSettle();

      currentRevision = 3;
      await pumpHost(
        tester,
        api,
        item(null, currentRevision),
        builder: builder,
      );
      await tester.pumpAndSettle();
      final countyCard = find.byKey(
        const ValueKey('research:33333333-3333-4333-8333-333333333333:county'),
      );
      await tester.tap(
        find.descendant(of: countyCard, matching: find.text('Research')),
      );
      await tester.pumpAndSettle();
      expect(find.text('Synthetic County'), findsOneWidget);
      final useSuggestion = find.text('Use this suggestion');
      expect(useSuggestion, findsOneWidget);
      await tester.tap(useSuggestion);
      await tester.pump();
      expect(selected?.selectionId, 'e' * 64);
      expect(selected?.selectionValue, 'Synthetic County');
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets(
    'current capability can be checked when no research binding is available',
    (tester) async {
      final requestId = 'd' * 64;
      var currentRevision = 1;
      var refreshes = 0;
      ResearchReviewCandidate? selected;
      final api = HostApi((path) async {
        if (path.endsWith('/research/current')) {
          throw const ResearchFailure(ResearchFailureKind.unavailable);
        }
        if (path.endsWith('/research/derivations/capability')) {
          return derivationCapability(revision: currentRevision);
        }
        if (path.endsWith('/research/derivations')) {
          return {
            'contract_version': 'research-derivation-accepted/v1',
            'request_id': requestId,
            'source_revision': currentRevision,
            'queued_revision': currentRevision + 1,
            'status': 'queued',
            'canonical_run_id': canonicalRunId,
          };
        }
        if (path.endsWith('/research/derivations/$requestId')) {
          return derivationResult(
            requestId: requestId,
            status: 'completed',
            sourceRevision: currentRevision,
            revision: currentRevision + 1,
            includeProposal: true,
          );
        }
        return {};
      });
      addTearDown(api.close);
      Widget builder(
        BuildContext context,
        Widget Function(String, ValueChanged<ResearchReviewCandidate>?)
        researchForField,
      ) => Column(
        children: [
          researchForField('country', (_) {}),
          researchForField('county', (candidate) => selected = candidate),
        ],
      );
      Future<void> refreshRecord() async => refreshes++;
      await pumpHost(
        tester,
        api,
        item(),
        builder: builder,
        refreshRecord: refreshRecord,
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Research').first);
      await tester.pumpAndSettle();

      expect(find.byType(ResearchThreadCard), findsNothing);
      expect(find.text('Fill the rest'), findsOneWidget);
      await tester.tap(find.text('Fill the rest'));
      await tester.pumpAndSettle();
      await tester.enterText(
        find.byType(TextField),
        'Review the saved location.',
      );
      await tester.tap(find.text('Request suggestions'));
      await tester.pumpAndSettle();
      expect(
        api.calls.any(
          (call) =>
              call['method'] == 'POST' &&
              call['body']['expected_record_revision'] == 1,
        ),
        isTrue,
      );
      expect(refreshes, 1);

      // The retained proposal targets Q+1 and remains usable even though
      // ordinary research discovery is still unavailable.
      currentRevision = 2;
      await pumpHost(
        tester,
        api,
        item(null, currentRevision),
        builder: builder,
        refreshRecord: refreshRecord,
      );
      await tester.pumpAndSettle();
      expect(find.text('Synthetic County'), findsOneWidget);
      await tester.tap(find.text('Use this suggestion'));
      await tester.pump();
      expect(selected?.selectionId, 'e' * 64);
      expect(selected?.selectionValue, 'Synthetic County');
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets(
    'reviewer chooses eligible fields and reason; retained value uses the existing candidate callback',
    (tester) async {
      final requestId = 'a' * 64;
      final calls = <String>[];
      var reloads = 0;
      var currentRevision = 1;
      ResearchReviewCandidate? selected;
      final api = HostApi((path) async {
        if (path.endsWith('/research/current')) {
          return discovery(null, currentRevision);
        }
        if (path.endsWith('/research/jobs/job/generations/1/thread')) {
          return countryReviewThread();
        }
        if (path.endsWith('/research/derivations/capability')) {
          calls.add('capability');
          return derivationCapability(revision: currentRevision);
        }
        if (path.endsWith('/research/derivations')) {
          calls.add('enqueue');
          return {
            'contract_version': 'research-derivation-accepted/v1',
            'request_id': requestId,
            'source_revision': currentRevision,
            'queued_revision': currentRevision + 1,
            'status': 'queued',
            'canonical_run_id': canonicalRunId,
          };
        }
        if (path.endsWith('/research/derivations/$requestId')) {
          calls.add('result');
          return derivationResult(
            requestId: requestId,
            status: 'completed',
            sourceRevision: currentRevision,
            revision: currentRevision + 1,
            includeProposal: true,
          );
        }
        return {};
      });
      addTearDown(api.close);
      Widget builder(
        BuildContext context,
        Widget Function(String, ValueChanged<ResearchReviewCandidate>?)
        researchForField,
      ) => Column(
        children: [
          researchForField('country', (_) {}),
          researchForField('county', (candidate) => selected = candidate),
        ],
      );
      late Future<void> Function() refreshRecord;
      refreshRecord = () async {
        reloads++;
      };

      await pumpHost(
        tester,
        api,
        item(),
        refreshRecord: refreshRecord,
        builder: builder,
      );
      await tester.pumpAndSettle();
      final countryCard = find.byKey(
        const ValueKey('research:33333333-3333-4333-8333-333333333333:country'),
      );
      await tester.tap(
        find.descendant(of: countryCard, matching: find.text('Research')),
      );
      await tester.pumpAndSettle();
      expect(calls, ['capability']);
      expect(find.text('Fill the rest'), findsOneWidget);

      await tester.tap(find.text('Fill the rest'));
      await tester.pumpAndSettle();
      await tester.tap(
        find.byKey(const ValueKey('derive-field-province_state')),
      );
      await tester.pump();
      await tester.enterText(
        find.byType(TextField),
        'Review the remaining place information.',
      );
      await tester.tap(find.text('Request suggestions'));
      await tester.pumpAndSettle();

      expect(calls, ['capability', 'enqueue', 'result']);
      expect(reloads, 1);
      final post = api.calls.singleWhere((call) => call['method'] == 'POST');
      expect(post['key'], isNotEmpty);
      expect(post['body'], {
        'expected_record_revision': 1,
        'base_record_version_id': '$canonicalRunId:1',
        'reason': 'Review the remaining place information.',
        'requested_fields': ['county'],
      });
      expect(find.text('Synthetic County'), findsNothing);

      // The backend result targets Q+1. It becomes selectable only after the
      // host refresh supplies that exact canonical record revision.
      currentRevision = 2;
      await pumpHost(
        tester,
        api,
        item(null, currentRevision),
        builder: builder,
        refreshRecord: refreshRecord,
      );
      await tester.pumpAndSettle();

      final countyCard = find.byKey(
        const ValueKey('research:33333333-3333-4333-8333-333333333333:county'),
      );
      await tester.tap(
        find.descendant(of: countyCard, matching: find.text('Research')),
      );
      await tester.pumpAndSettle();
      expect(find.text('Synthetic County'), findsOneWidget);
      await tester.ensureVisible(find.text('Use this suggestion'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Use this suggestion'));
      await tester.pump();
      expect(selected?.selectionId, 'e' * 64);
      expect(selected?.selectionValue, 'Synthetic County');
    },
  );
}
