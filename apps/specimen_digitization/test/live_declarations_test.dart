import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/models.dart';

void main() {
  test(
    'actual declaration save, supersession, replay, approval invalidation and immutable evidence',
    () async {
      final repo = ApiSpecimenRepository(
        baseUrl: Uri.parse(Platform.environment['SPECIMEN_TEST_API_BASE_URL']!),
        token: () async => Platform.environment['SPECIMEN_SYNTHETIC_TOKEN'],
        expectedMode: 'synthetic',
      );
      addTearDown(repo.close);
      final scope = (await repo.scopes()).single;
      final id = Platform.environment['SPECIMEN_DECLARATION_SPECIMEN_ID']!;
      var current = await repo.specimen(scope, id);
      expect(current.data['available_actions'], contains('reading_metadata'));
      final original = current;
      final observation = current.observations.first;
      final obsId = observation['id'] as String;
      final rawRequest = ArtifactRequest(
        ArtifactKind.observationRaw,
        obsId,
        sha256: observation['raw_sha256'],
      );
      final raw = await repo.artifact(scope, current, rawRequest);
      final provenanceRequest = ArtifactRequest(
        ArtifactKind.readingDeclarations,
        obsId,
      );
      final model = (await repo.artifact(
        scope,
        current,
        provenanceRequest,
      ))['model'];
      expect(
        current
            .data['run']['label_language_handling']['labels']
            .first['mixed_declared'],
        true,
      );
      current = await repo.review(scope, current, {
        'kind': 'approve',
        'reason': 'Synthetic approval before metadata change',
      }, 'declaration-initial-approve-${current.revision}');
      expect(current.data['run']['human_approved'], true);
      for (final language in ['French', 'Italian']) {
        final before = current;
        final change = <String, dynamic>{
          'kind': 'reading_metadata',
          'target_id': obsId,
          'reason': 'Synthetic declaration for $language',
          'language_candidates': [language],
          'script_candidates': ['Latin'],
          'language_relation': 'unspecified',
        };
        final key = 'declaration-${before.revision}';
        current = await repo.review(scope, before, change, key);
        expect(current.revision, before.revision + 1);
        expect(current.data['run']['human_approved'], false);
        expect(current.observations, original.observations);
        expect(
          current.data['run']['phase_results'],
          before.data['run']['phase_results'],
        );
        expect(
          current.data['run']['authority_receipts'],
          before.data['run']['authority_receipts'],
        );
        expect(await repo.artifact(scope, current, rawRequest), raw);
        final replay = await repo.review(scope, before, change, key);
        expect(replay.revision, current.revision);
        await expectLater(
          repo.review(scope, before, change, 'stale-$key'),
          throwsA(
            isA<ApiFailure>().having((e) => e.conflict, 'conflict', true),
          ),
        );
      }
      final provenance = await repo.artifact(scope, current, provenanceRequest);
      expect(provenance['model'], model);
      final history = provenance['human_history'] as List;
      expect(history.length, 2);
      expect(history[1]['supersedes'], history[0]['id']);
      final metadata = await repo.artifact(
        scope,
        current,
        ArtifactRequest(ArtifactKind.readingMetadata, obsId),
      );
      expect(
        objects(metadata['declarations'])
            .where(
              (d) => d['kind'] == 'language' && d['method'] == 'human_recorded',
            )
            .map((d) => d['value']),
        ['Italian'],
      );
      final historical = await repo.historicalSpecimen(
        scope,
        id,
        original.revision,
      );
      final historicalProvenance = await repo.artifact(
        scope,
        historical,
        provenanceRequest,
      );
      expect(historicalProvenance['human_history'], isEmpty);
      expect(historicalProvenance['model'], model);
      // ignore: avoid_print
      print(
        'DECLARATIONS HTTP specimen=$id initial=${original.revision} final=${current.revision} observation=$obsId preserved_model_raw=true',
      );
    },
    skip: Platform.environment['SPECIMEN_DECLARATIONS_LIVE_TEST'] != 'true',
  );
}
