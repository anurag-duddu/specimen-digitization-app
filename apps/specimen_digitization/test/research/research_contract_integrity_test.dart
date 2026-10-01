// Independent source-prepared probes. NOT EXECUTED at preparation time.
// Review target: latest-kit 1048dccceda38dcd4fab44dd01fbc8362194d4c2,
// HTTP/thread implementation 329b23053b4e2ee21d45133c321f4b2c5ae84089.
// Run only in a separately granted focused Flutter test slot.
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/research/research_models.dart';

const _fixtureDirectory = '../../tests/fixtures/research_harness/http';

// Independent fixed public contract vocabulary, not read from the decoder.
const _requiredFields = <String>[
  'fmnh_ins_number',
  'collection_code',
  'country',
  'province_state',
  'county',
  'city',
  'precise_location',
  'elevation_from_m',
  'elevation_to_m',
  'elevation_from_ft',
  'elevation_to_ft',
  'habitat',
  'collection_method',
  'date_visited_from',
  'date_visited_to',
  'collectors',
  'verbatim_dts',
  'taxon',
  'identified_by_irn',
  'date_identified',
];

Map<String, dynamic> _fixture(String name) => Map<String, dynamic>.from(
  jsonDecode(File('$_fixtureDirectory/$name.json').readAsStringSync()) as Map,
);

ResearchScope _scope() =>
    ResearchScope.fromJson(_fixture('failed-thread')['scope']);

ResearchThread _decode(Map<String, dynamic> json) =>
    ResearchThread.fromJson(json, expectedScope: _scope());

Map<String, dynamic> _field(Map<String, dynamic> json, String key) =>
    (json['fields'] as List).cast<Map<String, dynamic>>().singleWhere(
      (field) => field['field_key'] == key,
    );

// Keep summary counts consistent, so a denial must address the omitted field
// or contradictory checkpoint phase rather than an unrelated count mismatch.
void _recount(Map<String, dynamic> json) {
  final fields = (json['fields'] as List).cast<Map<String, dynamic>>();
  json['resolved_count'] = fields
      .where((field) => field['work_state'] == 'resolved')
      .length;
  json['exception_count'] = fields
      .where((field) => field['work_state'] == 'nonblocking_exception')
      .length;
}

void main() {
  test(
    'unchanged frozen fixture includes exactly all twenty mandatory fields',
    () {
      final thread = _decode(_fixture('failed-thread'));
      expect(
        thread.fields.map((field) => field.fieldKey).toSet(),
        _requiredFields.toSet(),
      );
      expect(thread.fields, hasLength(20));
      expect(thread.canRetry('taxon'), isTrue);
      expect(thread.field('country')!.workState, ResearchWorkState.resolved);
    },
  );

  for (final key in _requiredFields) {
    test('denies a v1 thread omitting mandatory field $key', () {
      final json = _fixture('failed-thread');
      (json['fields'] as List).removeWhere(
        (dynamic field) => field['field_key'] == key,
      );
      _recount(json);
      expect(() => _decode(json), throwsA(isA<ResearchContractException>()));
    });
  }

  for (final phase in ['resolved', 'nonblocking_exception', 'waiting_human']) {
    test('denies $phase with a retained operational-failure checkpoint', () {
      final json = _fixture('failed-thread');
      final taxon = _field(json, 'taxon');
      expect(
        taxon['checkpoint']['resolution']['work_state'],
        'operational_failed',
      );
      taxon['work_state'] = phase;
      _recount(json);
      expect(() => _decode(json), throwsA(isA<ResearchContractException>()));
    });
  }

  test('denies operational failure with a retained resolved checkpoint', () {
    final json = _fixture('failed-thread');
    final country = _field(json, 'country');
    expect(country['checkpoint']['resolution']['work_state'], 'resolved');
    country['work_state'] = 'operational_failed';
    _recount(json);
    expect(() => _decode(json), throwsA(isA<ResearchContractException>()));
  });

  // Queued and running are intentional mutable command overlays: a fresh
  // command retains its earlier failed checkpoint until execution completes.
  for (final phase in ['retry_scheduled', 'researching']) {
    test('preserves legitimate $phase overlay over the failed checkpoint', () {
      final json = _fixture('queued-thread');
      _field(json, 'taxon')['work_state'] = phase;
      _recount(json);
      final thread = _decode(json);
      expect(thread.field('taxon')!.workState, ResearchWorkState.parse(phase));
      expect(
        thread.field('taxon')!.checkpoint!.resolution.workState,
        ResearchWorkState.operationalFailed,
      );
      expect(thread.field('taxon')!.value.state, 'unknown');
      expect(thread.canRetry('taxon'), isFalse);
      expect(thread.field('country')!.workState, ResearchWorkState.resolved);
    });
  }

  test('keeps a novel phase readable while disabling all retry actions', () {
    final json = _fixture('failed-thread');
    _field(json, 'country')['work_state'] = 'future_phase';
    final thread = _decode(json);
    expect(thread.hasUnknownState, isTrue);
    expect(thread.canRetry('taxon'), isFalse);
  });
}
