import 'dart:io';
import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/models.dart';

void main() {
  test(
    'real local HTTP intake, checkpoint, evidence, correction and reopen',
    () async {
      final repo = ApiSpecimenRepository(
        baseUrl: Uri.parse(
          Platform.environment['SPECIMEN_TEST_API_BASE_URL'] ??
              'http://127.0.0.1:8000',
        ),
        token: () async => Platform.environment['SPECIMEN_SYNTHETIC_TOKEN'],
        expectedMode: 'synthetic',
      );
      final scope = (await repo.scopes()).single;
      final bytes = File('test/fixtures/synthetic-label.png').readAsBytesSync();
      final file = IntakeFile(
        name: 'synthetic-label.png',
        bytes: bytes,
        mimeType: 'image/png',
        sha256: sha256.convert(bytes).toString(),
        method: 'files',
        width: 800,
        height: 600,
      );
      final session = await repo.createIntake(
        scope,
        file,
        'live-${DateTime.now().microsecondsSinceEpoch}',
      );
      if (session['state'] != 'duplicate') {
        // Send only a prefix, then reconstruct the repository to emulate client restart.
        await repo.request(
          'PUT',
          '/v1/organizations/${scope.organizationId}/uploads/${session['upload_id']}/content',
          headers: {'Upload-Offset': '0'},
          bytes: bytes.sublist(0, 100),
        );
        final reopened = ApiSpecimenRepository(
          baseUrl: Uri.parse(
            Platform.environment['SPECIMEN_TEST_API_BASE_URL'] ??
                'http://127.0.0.1:8000',
          ),
          token: () => repo.token(),
          expectedMode: 'synthetic',
        );
        await reopened.upload(scope, session, file, (_) {});
        await reopened.completeIntake(
          scope,
          session['upload_id'],
          'complete-${session['upload_id']}',
        );
        reopened.close();
      }
      final id = session['duplicate_specimen_id'] ?? session['specimen_id'];
      var specimen = await repo.specimen(scope, id);
      for (var i = 0; i < 50 && specimen.disposition == null; i++) {
        await Future<void>.delayed(const Duration(milliseconds: 100));
        specimen = await repo.specimen(scope, id);
      }
      expect(specimen.disposition, 'needs_human_review');
      expect(specimen.observations.length, greaterThanOrEqualTo(2));
      expect(specimen.fields, hasLength(20));
      expect(specimen.assets.single['sha256'], file.sha256);
      expect(specimen.assets.single['preview_bytes'], isNotEmpty);
      final evidenceId = specimen.evidence.first['evidence_id'];
      final revised = await repo.review(scope, specimen, {
        'kind': 'field_correction',
        'target_id': 'country',
        'state': 'unknown',
        'value': null,
        'reason': 'Synthetic abstention test',
        'evidence_ids': [evidenceId],
      }, 'abstain-${specimen.revision}');
      expect(revised.revision, greaterThan(specimen.revision));
      expect(revised.disposition, isNot('cleared'));
      expect(
        revised.fields.firstWhere((f) => f['field_key'] == 'country')['state'],
        'unknown',
      );
      await expectLater(
        repo.review(scope, specimen, {
          'kind': 'approve',
          'reason': 'stale fixture',
        }, 'stale-${specimen.revision}'),
        throwsA(
          isA<ApiFailure>().having((e) => e.conflict, 'stale conflict', true),
        ),
      );
      final restored = await repo.specimen(scope, id);
      expect(restored.revision, revised.revision);
      expect(restored.observations.length, specimen.observations.length);
      expect(restored.audit.last['reason'], 'Synthetic abstention test');
      var abstained = await repo.review(scope, restored, {
        'kind': 'transcription_adjudication',
        'target_id': restored.regions.first['region_id'],
        'state': 'unreadable',
        'value': null,
        'reason': 'Synthetic source abstention',
        'evidence_ids': [],
      }, 'transcript-${restored.revision}');
      for (var i = 0; i < 50 && abstained.disposition == null; i++) {
        await Future<void>.delayed(const Duration(milliseconds: 100));
        abstained = await repo.specimen(scope, id);
      }
      expect(abstained.disposition, 'needs_human_review');
      expect(abstained.observations.length, restored.observations.length);
      expect(abstained.data['transcriptions'][0]['resolved'], false);
      expect(abstained.data['transcriptions'][0]['state'], 'unreadable');
      expect(abstained.disposition, isNot('cleared'));
      repo.close();
    },
    skip: Platform.environment['SPECIMEN_LIVE_TEST'] != 'true',
  );
}
