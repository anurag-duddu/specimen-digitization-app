import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/research/research_models.dart';

import 'probe_helpers.dart';

void main() {
  test(
    'positive control: matching resolution and question receipts remain readable',
    () {
      final json = probeFixture();
      final field = probeField(json, 'taxon');
      final resolution = field['checkpoint']['resolution'] as Map;
      field['work_state'] = 'waiting_human';
      field['actions'] = ['supply_information'];
      resolution['work_state'] = 'waiting_human';
      resolution['source_coverage'] = [probeCoverage('taxon')];
      resolution['question'] = {
        'field_key': 'taxon',
        'question': 'Synthetic question',
        'reason': 'semantic_ambiguity',
        'coverage': [probeCoverage('taxon')],
      };
      final thread = ResearchThread.fromJson(json, expectedScope: probeScope());
      expect(
        thread.field('taxon')!.checkpoint!.resolution.sourceCoverage,
        hasLength(1),
      );
    },
  );

  test('rejects a schema-valid foreign resolution source receipt', () {
    final json = probeFixture();
    final resolution =
        probeField(json, 'taxon')['checkpoint']['resolution'] as Map;
    resolution['source_coverage'] = [probeCoverage('country')];
    expect(
      () => ResearchThread.fromJson(json, expectedScope: probeScope()),
      throwsA(isA<ResearchContractException>()),
    );
  });

  test('rejects a schema-valid foreign human-question coverage receipt', () {
    final json = probeFixture();
    final field = probeField(json, 'taxon');
    final resolution = field['checkpoint']['resolution'] as Map;
    field['work_state'] = 'waiting_human';
    field['actions'] = ['supply_information'];
    resolution['work_state'] = 'waiting_human';
    resolution['question'] = {
      'field_key': 'taxon',
      'question': 'Synthetic question',
      'reason': 'semantic_ambiguity',
      'coverage': [probeCoverage('country')],
    };
    expect(
      () => ResearchThread.fromJson(json, expectedScope: probeScope()),
      throwsA(isA<ResearchContractException>()),
    );
  });
}
