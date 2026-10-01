import 'dart:convert';
import 'dart:io';

import 'package:specimen_digitization/src/research/research_models.dart';

Map<String, dynamic> researchFixture(String name) => Map<String, dynamic>.from(
  jsonDecode(
        File(
          '../../tests/fixtures/research_harness/http/$name.json',
        ).readAsStringSync(),
      )
      as Map,
);

ResearchScope trustedResearchScope() =>
    ResearchScope.fromJson(researchFixture('failed-thread')['scope']);

ResearchThread fixtureThread([String name = 'failed-thread']) =>
    ResearchThread.fromJson(
      researchFixture(name),
      expectedScope: trustedResearchScope(),
    );

Map<String, dynamic> fixtureField(Map<String, dynamic> thread, String key) =>
    (thread['fields'] as List).cast<Map<String, dynamic>>().singleWhere(
      (field) => field['field_key'] == key,
    );
