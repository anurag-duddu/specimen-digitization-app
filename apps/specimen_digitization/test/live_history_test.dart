import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/models.dart';

// Opt-in: use a uniquely owned synthetic specimen with compacted audit history.
void main() {
  test(
    'real HTTP compacted history is complete and does not replace current CAS',
    () async {
      final repo = ApiSpecimenRepository(
        baseUrl: Uri.parse(Platform.environment['SPECIMEN_TEST_API_BASE_URL']!),
        token: () async => Platform.environment['SPECIMEN_SYNTHETIC_TOKEN'],
        expectedMode: 'synthetic',
      );
      addTearDown(repo.close);
      final scope = (await repo.scopes()).single;
      final id = Platform.environment['SPECIMEN_HISTORY_TEST_ID']!;
      final current = await repo.specimen(scope, id);
      expect(current.data['history_through_revision'], isNotNull);
      expect(current.data['audit_offset'], greaterThan(0));
      final bound = current.revision;
      var after = 0;
      final revisions = <int>[];
      do {
        final page = await repo.historyPage(
          scope,
          id,
          throughRevision: bound,
          afterRevision: after,
        );
        expect(page.throughRevision, bound);
        revisions.addAll(page.items.map((e) => e['revision'] as int));
        if (page.nextCursor == null) break;
        after = page.nextCursor!;
      } while (true);
      expect(revisions, List.generate(bound, (i) => i + 1));
      final first = await repo.historicalSpecimen(scope, id, 1);
      expect(first.revision, 1);
      expect(first.data['available_actions'], isEmpty);
      final reference = current.audit.last['before'] as Map;
      final prior = await repo.historicalSpecimen(
        scope,
        id,
        reference['revision'] as int,
        runId: reference['run_id'] as String,
        runSha256: reference['run_sha256'] as String,
      );
      expect(prior.revision, lessThan(bound));
      expect(prior.observations, isNotEmpty);
      await expectLater(
        repo.historicalSpecimen(
          scope,
          id,
          reference['revision'] as int,
          runId: reference['run_id'] as String,
          runSha256: 'a' * 64,
        ),
        throwsA(
          isA<ApiFailure>().having((e) => e.status, 'digest conflict', 409),
        ),
      );
      final updated = await repo.review(scope, current, {
        'kind': 'approve',
        'reason': 'Synthetic history reader current CAS regression',
      }, 'flutter-history-$bound');
      expect(updated.revision, bound + 1);
      expect(current.revision, bound);
      final pinned = await repo.historyPage(
        scope,
        id,
        throughRevision: bound,
        afterRevision: bound - 1,
      );
      expect(pinned.items.single['revision'], bound);
      expect(pinned.nextCursor, isNull);
      await expectLater(
        repo.review(scope, current, {
          'kind': 'approve',
          'reason': 'Synthetic stale review regression',
        }, 'flutter-history-stale-$bound'),
        throwsA(
          isA<ApiFailure>().having((e) => e.conflict, 'stale conflict', true),
        ),
      );
    },
    skip: Platform.environment['SPECIMEN_HISTORY_TEST_ID'] == null,
  );
}
