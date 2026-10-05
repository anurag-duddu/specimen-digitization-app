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

import 'research_fixture.dart';

const canonicalRunId = '44444444-4444-4444-8444-444444444444';
const nativeRecordVersions = <int, String>{
  1: '55555555-5555-4555-8555-555555555555',
  2: '66666666-6666-4666-8666-666666666666',
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
  'record_version_id': '$canonicalRunId:$revision',
  'sensitive': trusted.sensitive,
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

class HostApi extends ApiSpecimenRepository {
  HostApi(this.respond)
    : super(
        baseUrl: Uri.parse('https://api.example.test'),
        token: () async => 'test-only-token',
      );
  final Future<Json> Function(String path) respond;
  final paths = <String>[];
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
  Specimen specimen,
) async {
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light(),
      home: Scaffold(
        body: SingleChildScrollView(
          child: ResearchHost(
            repository: api,
            collection: collection,
            specimen: specimen,
          ),
        ),
      ),
    ),
  );
  await tester.pump();
}

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
}
