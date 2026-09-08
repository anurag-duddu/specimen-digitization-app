import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/models.dart';

void main() {
  test(
    'actual retained HTTP profiles preserve nullable scoped risk and reported observation measurements',
    () async {
      final fixture =
          jsonDecode(
                File(
                  'test/fixtures/backend-runtime-wire-examples.json',
                ).readAsStringSync(),
              )
              as Json;
      ApiSpecimenRepository repository(String url) {
        final repo = ApiSpecimenRepository(
          baseUrl: Uri.parse(url),
          token: () async => Platform.environment['SPECIMEN_SYNTHETIC_TOKEN'],
          expectedMode: 'synthetic',
        );
        addTearDown(repo.close);
        return repo;
      }

      final repo = repository(
        Platform.environment['SPECIMEN_TEST_API_BASE_URL']!,
      );
      final scope = (await repo.scopes()).single;
      final first = fixture['profile_variants']['first'] as Json;
      final second = fixture['profile_variants']['second'] as Json;
      final current = await repo.specimen(scope, second['specimen_id']);
      final prior = await repo.historicalSpecimen(
        scope,
        first['specimen_id'],
        first['revision'],
      );
      for (final pair in [(current, second), (prior, first)]) {
        final risk = pair.$1.data['run']['review_risk'] as Json;
        expect(risk, pair.$2['run']['review_risk']);
        expect(risk['composite'], null);
        expect(
          objects(risk['labels']).every((r) => r['composite'] == null),
          true,
        );
        expect(
          objects(risk['fields']).every((r) => r['composite'] == null),
          true,
        );
        expect(risk['clearance_authority'], false);
        expect(
          pair.$1.data['run']['profile_snapshot'],
          pair.$2['run']['profile_snapshot'],
        );
      }
      expect(
        current.data['run']['review_risk']['policy_reference']['digest'],
        isNot(prior.data['run']['review_risk']['policy_reference']['digest']),
      );
      final page = await repo.specimenPage(scope);
      expect(page.items.single.data['risk'], null);
      final telemetry = repository(
        Platform.environment['SPECIMEN_TELEMETRY_API_BASE_URL']!,
      );
      final telemetryScope = (await telemetry.scopes()).single;
      final expected = fixture['observation_telemetry']['workspace'] as Json;
      final observed = await telemetry.specimen(
        telemetryScope,
        expected['specimen_id'],
      );
      expect(observed.observations, expected['observations']);
      expect(observed.observations.first['latency_seconds'], greaterThan(0));
      expect(observed.observations.first['parameters'], null);
      expect(
        observed.observations.first['provider_model_id'],
        'synthetic-model-runtime',
      );
      expect(
        observed.observations.first['completion_state'],
        'validated_output',
      );
      // ignore: avoid_print
      print(
        'RUNTIME HTTP policy revisions=${prior.revision}/${current.revision} nullable_scope_composites=true telemetry_revision=${observed.revision} captured_measurements_preserved=true',
      );
    },
    skip: Platform.environment['SPECIMEN_RUNTIME_LIVE_TEST'] != 'true',
  );
}
