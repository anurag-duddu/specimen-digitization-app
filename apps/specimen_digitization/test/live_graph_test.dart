import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/models.dart';

void main() {
  test(
    'actual oversized HTTP workspace, committed receipt, pinned history and cancel',
    () async {
      final repo = ApiSpecimenRepository(
        baseUrl: Uri.parse(Platform.environment['SPECIMEN_TEST_API_BASE_URL']!),
        token: () async => Platform.environment['SPECIMEN_SYNTHETIC_TOKEN'],
        expectedMode: 'synthetic',
      );
      addTearDown(repo.close);
      final scope = (await repo.scopes()).single;
      final id = Platform.environment['SPECIMEN_GRAPH_SPECIMEN_ID']!;
      final before = await repo.specimen(scope, id);
      expect(
        before.data['artifact_receipt']['artifact_size_bytes'],
        greaterThan(2000000),
      );
      Future<Json> graph(Specimen s) => repo.artifact(
        scope,
        s,
        ArtifactRequest(
          ArtifactKind.activeGraph,
          s.id,
          sha256: s.data['artifact_receipt']['artifact_sha256'],
        ),
      );
      final original = await graph(before);
      expect(
        original['run']['observations'].first['literal_text'].length,
        greaterThan(2000000),
      );
      final after = await repo.review(scope, before, {
        'kind': 'coverage',
        'reason': 'Actual Flutter graph receipt verification',
      }, 'graph-coverage-${before.revision}');
      expect(after.revision, before.revision + 1);
      expect(after.data['mutation_saved'], true);
      expect(after.data['artifact_receipt']['mutation_committed'], true);
      expect((await graph(after))['run']['coverage_confirmed'], true);
      final historical = await repo.historicalSpecimen(
        scope,
        id,
        before.revision,
      );
      expect(historical.data['available_actions'], isEmpty);
      expect(await graph(historical), original);
      await expectLater(
        repo.review(scope, before, {
          'kind': 'coverage',
          'reason': 'Stale revision verification',
        }, 'graph-stale-${before.revision}'),
        throwsA(isA<ApiFailure>().having((e) => e.conflict, 'conflict', true)),
      );
      final cancelled = await repo.review(scope, after, {
        'kind': 'run_action',
        'action': 'cancel',
        'reason': 'Actual Flutter oversized-record recovery',
      }, 'graph-cancel-${after.revision}');
      expect(cancelled.revision, after.revision + 1);
      expect(cancelled.state, 'cancelled');
      expect(await graph(historical), original);
      // ignore: avoid_print
      print(
        'GRAPH HTTP specimen=$id before=${before.revision} committed=${after.revision} cancelled=${cancelled.revision} bytes=${before.data['artifact_receipt']['artifact_size_bytes']}',
      );
    },
    skip: Platform.environment['SPECIMEN_GRAPH_LIVE_TEST'] != 'true',
  );
}
