import 'dart:io';
import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/models.dart';

void main() {
  test(
    'real HTTP authority evidence, explicit selection, separate approval and pinned prior revision',
    () async {
      final repo = ApiSpecimenRepository(
        baseUrl: Uri.parse(Platform.environment['SPECIMEN_TEST_API_BASE_URL']!),
        token: () async => Platform.environment['SPECIMEN_SYNTHETIC_TOKEN'],
        expectedMode: 'synthetic',
      );
      addTearDown(repo.close);
      final scope = (await repo.scopes()).single;
      expect(scope.configuration['profiles'], isNotEmpty);
      final bytes = File(
        'test/fixtures/synthetic-wide-label.png',
      ).readAsBytesSync();
      final file = IntakeFile(
        name: 'synthetic-wide-label.png',
        bytes: bytes,
        mimeType: 'image/png',
        sha256: sha256.convert(bytes).toString(),
        method: 'files',
        width: 1000,
        height: 520,
      );
      final preflight = await repo.preflight(scope, file);
      expect(preflight['status'], isNot('ready'));
      expect(preflight['specimen_created'], false);
      final session = await repo.createIntake(
        scope,
        file,
        'live-next-${DateTime.now().microsecondsSinceEpoch}',
      );
      if (session['state'] != 'duplicate') {
        await repo.upload(scope, session, file, (_) {});
        await repo.completeIntake(
          scope,
          session['upload_id'],
          'next-complete-${session['upload_id']}',
        );
      }
      final id = session['duplicate_specimen_id'] ?? session['specimen_id'];
      Future<Specimen> settled() async {
        var s = await repo.specimen(scope, id);
        for (var i = 0; i < 100 && s.disposition == null; i++) {
          await Future<void>.delayed(const Duration(milliseconds: 100));
          s = await repo.specimen(scope, id);
        }
        return s;
      }

      final original = await settled();
      expect(original.disposition, 'needs_human_review');
      expect(original.assets.single['preview_is_derivative'], true);
      final phase = await repo.artifact(
        scope,
        original,
        const ArtifactRequest(ArtifactKind.phase, 'lookup'),
      );
      expect(phase['phase'], 'lookup');
      final authority = await repo.artifact(
        scope,
        original,
        const ArtifactRequest(
          ArtifactKind.authority,
          'parties',
          fieldKey: 'identified_by_irn',
        ),
      );
      final candidate = objects(authority['candidates']).single;
      expect(candidate['identity']['irn'], 7);
      final raw = await repo.artifact(
        scope,
        original,
        ArtifactRequest(
          ArtifactKind.authorityRaw,
          'parties',
          fieldKey: 'identified_by_irn',
          sha256: authority['response_sha256'],
        ),
      );
      expect(raw['size_bytes'], greaterThan(0));
      for (final o in original.observations) {
        final metadata = await repo.artifact(
          scope,
          original,
          ArtifactRequest(ArtifactKind.readingMetadata, o['id']),
        );
        expect(metadata['language_state'], 'unknown');
        final reading = await repo.artifact(
          scope,
          original,
          ArtifactRequest(
            ArtifactKind.observationRaw,
            o['id'],
            sha256: o['raw_sha256'],
          ),
        );
        expect(reading['size_bytes'], greaterThan(0));
      }
      final alignment = await repo.artifact(
        scope,
        original,
        ArtifactRequest(
          ArtifactKind.disagreement,
          original.regions.first['region_id'],
        ),
      );
      expect(alignment['status'], 'agreement');
      final selected = await repo.review(scope, original, {
        'kind': 'authority_resolution',
        'target_id': 'identified_by_irn',
        'tool_id': 'parties',
        'identifier': candidate['identifier'],
        'reason': 'Synthetic exact retained Parties candidate',
      }, 'next-select-${original.revision}');
      expect(
        selected.fields.firstWhere(
          (f) => f['field_key'] == 'identified_by_irn',
        )['literal_value'],
        'Synthetic Collector',
      );
      var current = await settled();
      expect(current.disposition, isNot('cleared'));
      await expectLater(
        repo.review(scope, original, {
          'kind': 'approve',
          'reason': 'Synthetic stale review',
        }, 'next-stale-${original.revision}'),
        throwsA(isA<ApiFailure>().having((e) => e.conflict, 'CAS', true)),
      );
      await repo.review(scope, current, {
        'kind': 'approve',
        'reason': 'Synthetic separate explicit approval',
      }, 'next-approve-${current.revision}');
      current = await settled();
      expect(current.disposition, 'cleared');
      final prior = await repo.artifact(
        scope,
        original,
        const ArtifactRequest(
          ArtifactKind.authority,
          'parties',
          fieldKey: 'identified_by_irn',
        ),
      );
      expect(prior, authority);
      final page = await repo.specimenPage(
        scope,
        filters: {'specimen_id': id, 'risk_min': '0'},
      );
      expect(page.items.single.id, id);
      // This is synthetic local evidence, retained for browser inspection.
      // ignore: avoid_print
      print(
        'HTTP evidence specimen=$id original=${original.revision} final=${current.revision} state=${current.disposition}',
      );
    },
    skip: Platform.environment['SPECIMEN_NEXT_LIVE_TEST'] != 'true',
  );
}
