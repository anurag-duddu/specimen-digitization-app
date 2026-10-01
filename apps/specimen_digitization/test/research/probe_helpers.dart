import 'dart:convert';
import 'dart:io';

import 'package:specimen_digitization/src/research/research_models.dart';

Map<String, dynamic> probeFixture([String name = 'failed-thread']) =>
    Map<String, dynamic>.from(
      jsonDecode(
            File(
              '../../tests/fixtures/research_harness/http/$name.json',
            ).readAsStringSync(),
          )
          as Map,
    );

ResearchScope probeScope() => ResearchScope.fromJson(probeFixture()['scope']);

ResearchThread probeThread([String name = 'failed-thread']) =>
    ResearchThread.fromJson(probeFixture(name), expectedScope: probeScope());

Map<String, dynamic> probeField(Map<String, dynamic> thread, String fieldKey) =>
    (thread['fields'] as List).cast<Map<String, dynamic>>().singleWhere(
      (field) => field['field_key'] == fieldKey,
    );

Map<String, dynamic> probeCoverage(String owner) => <String, dynamic>{
  'source_id': 'gbif',
  'field_key': owner,
  'state': 'exhausted',
  'source_version': 'synthetic-v1',
  'qualification_digest': 'a' * 64,
  'exact_join_attempted': true,
  'exact_join_proven': true,
  'query_digest': 'b' * 64,
  'receipt_ids': ['synthetic-scoped-search-receipt'],
  'candidate_count': 0,
  'coverage_limit': 'Synthetic typed name query only',
  'reason': 'Synthetic scoped search receipt for a structural test only',
};
