// The thread in each field: what was written, by whom, and what settled it
// (UI.md T2.3, part two).

import 'dart:convert';
import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/fields_panel.dart';
import 'package:specimen_digitization/src/screens/workbench/pending_changes.dart';
import 'package:specimen_digitization/src/thread/thread.dart';

import '../widgets/harness.dart';

Json fixtureJson() =>
    jsonDecode(
          File('test/fixtures/thread-two-label-slide.json').readAsStringSync(),
        )
        as Json;

/// The field [key] of a decoded response, to change in place.
Json fieldIn(Json json, String key) => (json['fields'] as List<dynamic>)
    .cast<Json>()
    .firstWhere((Json f) => f['field_key'] == key);

/// The workspace's account of the same record, as the run left it.
Json recordJson(SpecimenThread thread) => <String, dynamic>{
  'specimen_id': thread.specimenId,
  'revision': thread.revision,
  'observations': <Json>[
    for (final ThreadRegion region in thread.regions)
      for (final ThreadReading reading in region.readings)
        <String, dynamic>{
          'id': reading.observationId,
          'model_id': reading.model,
        },
  ],
  'fields': <Json>[
    for (final ThreadField f in thread.fields)
      <String, dynamic>{
        'field_key': f.fieldKey,
        'display_name': f.fieldKey,
        'required': f.group == ThreadFieldGroup.mandatory,
        'state': f.state,
        'literal_value': f.verbatim.length == 1 ? f.verbatim.single.text : null,
        'parsed_value': f.parsed,
        'normalized': f.normalized,
        'authority_id': f.authorityId,
      },
  ],
};

final Map<String, GlobalKey> rows = <String, GlobalKey>{};

Future<void> pumpFields(
  WidgetTester tester,
  Json record, {
  SpecimenThread? thread,
  List<PendingFieldChange> pending = const <PendingFieldChange>[],
}) {
  final Specimen specimen = Specimen(record);
  rows
    ..clear()
    ..addAll(<String, GlobalKey>{
      for (final Json f in specimen.fields)
        f['field_key'] as String: GlobalKey(),
    });
  return pumpComponent(
    tester,
    SingleChildScrollView(
      child: WorkbenchFields(
        specimen: specimen,
        thread: thread,
        anchors: rows,
        pending: pending,
        onPendingChanged: (_) {},
        onFocusRegion: (_) {},
      ),
    ),
    size: const Size(1000, 4000),
  );
}

Finder inRow(String key, Finder matching) =>
    find.descendant(of: find.byKey(rows[key]!), matching: matching);

const String googleLine =
    'Google Maps supports this value · place ID fixture-place-id-zacapa';

void main() {
  testWidgets('a Google lookup names its place ID and nothing of Google', (
    WidgetTester tester,
  ) async {
    final SpecimenThread thread = SpecimenThread.fromJson(fixtureJson());
    await pumpFields(tester, recordJson(thread), thread: thread);
    expect(inRow('country', find.text(googleLine)), findsOneWidget);
    expect(
      inRow('country', find.textContaining('Authority match')),
      findsNothing,
      reason: 'the source lines take the place of the one authority line',
    );
  });

  testWidgets('each source says how it bears on the value', (
    WidgetTester tester,
  ) async {
    final Json json = fixtureJson();
    (json['fields'] as List<dynamic>).add(<String, dynamic>{
      'field_key': 'taxon',
      'group': 'mandatory',
      'state': 'supported',
      'verbatim': <Json>[
        <String, dynamic>{
          'text': 'Tachinidae',
          'input_source': 'decided_transcript',
          'region_id': 'region-left',
          'observation_id': null,
        },
      ],
      'parsed': 'Tachinidae',
      'normalized': 'Tachinidae',
      'authority_id': '1111111',
      'evidence': <Json>[
        <String, dynamic>{
          'evidence_id': 'evidence-taxon-1',
          'relation': 'decides',
          'source': 'gbif',
          'locator': 'species/1111111',
          'outcome': 'success',
        },
        <String, dynamic>{
          'evidence_id': 'evidence-name-1',
          'relation': 'supports',
          'source': 'gnv',
          'locator': null,
          'outcome': 'success',
        },
        <String, dynamic>{
          'evidence_id': 'evidence-taxon-2',
          'relation': 'contradicts',
          'source': 'col',
          'locator': 'taxon/FIXTURE',
          'outcome': 'success',
        },
      ],
    });
    final SpecimenThread thread = SpecimenThread.fromJson(json);
    await pumpFields(tester, recordJson(thread), thread: thread);
    for (final String line in <String>[
      'GBIF decides this value · species/1111111',
      'Global Names Verifier supports this value',
      'Catalogue of Life contradicts this value · taxon/FIXTURE',
    ]) {
      expect(inRow('taxon', find.text(line)), findsOneWidget);
    }
  });

  testWidgets("each reader's text stands in As written when none was chosen", (
    WidgetTester tester,
  ) async {
    final Json json = fixtureJson();
    fieldIn(json, 'country')
      ..['state'] = 'unresolved'
      ..['verbatim'] = <Json>[
        <String, dynamic>{
          'text': 'GUATEMALA',
          'input_source': 'raw_reading',
          'region_id': 'region-right',
          'observation_id': 'obs-right-qwen',
        },
        <String, dynamic>{
          'text': 'GUATEMALA.',
          'input_source': 'raw_reading',
          'region_id': 'region-right',
          'observation_id': 'obs-right-muse',
        },
      ];
    final SpecimenThread thread = SpecimenThread.fromJson(json);
    await pumpFields(tester, recordJson(thread), thread: thread);
    for (final String text in <String>[
      'Qwen/Qwen2.5-VL-72B-Instruct · raw reading',
      'GUATEMALA',
      'muse-handwriting-fixture · raw reading',
      'GUATEMALA.',
      'As written: GUATEMALA and 1 more',
    ]) {
      expect(inRow('country', find.text(text)), findsOneWidget);
    }
  });

  testWidgets("a text taken from one reader's raw reading names that reader", (
    WidgetTester tester,
  ) async {
    final Json json = fixtureJson();
    fieldIn(json, 'country')['verbatim'] = <Json>[
      <String, dynamic>{
        'text': 'GUATEMALA',
        'input_source': 'raw_reading',
        'region_id': 'region-right',
        'observation_id': 'obs-right-qwen',
      },
    ];
    final SpecimenThread thread = SpecimenThread.fromJson(json);
    await pumpFields(tester, recordJson(thread), thread: thread);
    expect(
      inRow('country', find.text('Qwen/Qwen2.5-VL-72B-Instruct · raw reading')),
      findsOneWidget,
    );
  });

  testWidgets("the decided transcript's text names no reader", (
    WidgetTester tester,
  ) async {
    final SpecimenThread thread = SpecimenThread.fromJson(fixtureJson());
    await pumpFields(tester, recordJson(thread), thread: thread);
    expect(
      inRow('country', find.textContaining(' · raw reading')),
      findsNothing,
    );
    expect(
      inRow('country', find.textContaining('decided transcript')),
      findsNothing,
      reason: 'the Readings segment shows how the transcript was decided',
    );
  });

  testWidgets('a century a rule set says so under Read as', (
    WidgetTester tester,
  ) async {
    final Json json = fixtureJson();
    fieldIn(json, 'date_visited_from')
      ..['verbatim'] = <Json>[
        <String, dynamic>{
          'text': '12.v.78',
          'input_source': 'decided_transcript',
          'region_id': 'region-left',
          'observation_id': null,
        },
      ]
      ..['century_rule'] = 'date-rules-v1:two_digit_year_century=1900';
    final SpecimenThread thread = SpecimenThread.fromJson(json);
    await pumpFields(tester, recordJson(thread), thread: thread);
    expect(
      inRow(
        'date_visited_from',
        find.text("Century from the profile's rule: 1900s"),
      ),
      findsOneWidget,
    );
    expect(
      find.textContaining('Century from'),
      findsOneWidget,
      reason: 'a four-digit year, or a field that is not a date, has no rule',
    );
  });

  testWidgets('a field the record has changed since the run shows the record', (
    WidgetTester tester,
  ) async {
    final SpecimenThread thread = SpecimenThread.fromJson(fixtureJson());
    final Json record = recordJson(thread);
    fieldIn(record, 'country')['authority_id'] = 'reviewer-place-id';
    await pumpFields(tester, record, thread: thread);
    expect(inRow('country', find.textContaining('Google Maps')), findsNothing);
    expect(
      inRow('country', find.text('Authority match reviewer-place-id')),
      findsOneWidget,
    );
  });

  testWidgets('a pending correction shows its own values', (
    WidgetTester tester,
  ) async {
    final SpecimenThread thread = SpecimenThread.fromJson(fixtureJson());
    await pumpFields(
      tester,
      recordJson(thread),
      thread: thread,
      pending: const <PendingFieldChange>[
        PendingFieldChange(
          fieldKey: 'country',
          displayName: 'country',
          state: 'supported',
          literal: 'GUATEMALA',
          parsed: 'Guatemala',
          authorityId: 'pending-place-id',
          evidenceIds: <String>['evidence-geo-1'],
        ),
      ],
    );
    expect(inRow('country', find.textContaining('Google Maps')), findsNothing);
    expect(
      inRow('country', find.text('Authority match pending-place-id')),
      findsOneWidget,
    );
  });

  testWidgets('without a thread the row keeps its authority line', (
    WidgetTester tester,
  ) async {
    final SpecimenThread thread = SpecimenThread.fromJson(fixtureJson());
    await pumpFields(tester, recordJson(thread));
    expect(
      inRow('country', find.text('Authority match fixture-place-id-zacapa')),
      findsOneWidget,
    );
    expect(find.textContaining('Google Maps'), findsNothing);
  });

  group("the decision's findings on their fields (UI.md T2.4)", () {
    /// The fixture with [finding] added to the decision's findings.
    SpecimenThread withFinding(Json finding) {
      final Json json = fixtureJson();
      ((json['decision'] as Json)['findings'] as List<dynamic>).add(finding);
      return SpecimenThread.fromJson(json);
    }

    Json finding(String severity) => <String, dynamic>{
      'rule_id': 'authority-sources-agree',
      'severity': severity,
      'field_key': 'country',
      'reason_code': 'authority_sources_disagree',
    };

    testWidgets('a warning attaches to its field as worth checking', (
      WidgetTester tester,
    ) async {
      final SpecimenThread thread = withFinding(finding('warning'));
      await pumpFields(tester, recordJson(thread), thread: thread);
      expect(
        inRow('country', find.text('Authority sources disagree')),
        findsOneWidget,
      );
      expect(
        inRow('country', find.text('Worth checking · authority-sources-agree')),
        findsOneWidget,
      );
    });

    testWidgets('an info finding is for information', (
      WidgetTester tester,
    ) async {
      final SpecimenThread thread = withFinding(finding('info'));
      await pumpFields(tester, recordJson(thread), thread: thread);
      expect(
        inRow(
          'country',
          find.text('For information · authority-sources-agree'),
        ),
        findsOneWidget,
      );
    });

    testWidgets('a hard finding comes from the record, not the thread', (
      WidgetTester tester,
    ) async {
      // The fixture's decision carries a hard finding on habitat, and this
      // record publishes none.
      final SpecimenThread thread = SpecimenThread.fromJson(fixtureJson());
      await pumpFields(tester, recordJson(thread), thread: thread);
      expect(inRow('habitat', find.textContaining('Mandatory')), findsNothing);
    });

    testWidgets('a field changed since the run shows no run findings', (
      WidgetTester tester,
    ) async {
      final SpecimenThread thread = withFinding(finding('warning'));
      final Json record = recordJson(thread);
      fieldIn(record, 'country')['authority_id'] = 'reviewer-place-id';
      await pumpFields(tester, record, thread: thread);
      expect(find.text('Authority sources disagree'), findsNothing);
    });
  });

  group('which readings settled the value (UI.md T2.3 part three)', () {
    const String qwen = 'Qwen/Qwen2.5-VL-72B-Instruct';
    const String muse = 'muse-handwriting-fixture';

    /// One verbatim entry, as the thread sends it.
    Json entry(String text, String source, String region, String? reading) =>
        <String, dynamic>{
          'text': text,
          'input_source': source,
          'region_id': region,
          'observation_id': reading,
        };

    /// The fixture with the country field reshaped.
    SpecimenThread countryAs({
      required List<Json> verbatim,
      required List<String> settled,
      String state = 'supported',
    }) {
      final Json json = fixtureJson();
      fieldIn(json, 'country')
        ..['state'] = state
        ..['verbatim'] = verbatim
        ..['settled_observation_ids'] = settled;
      return SpecimenThread.fromJson(json);
    }

    testWidgets('a field on two labels names each label and what settled it', (
      WidgetTester tester,
    ) async {
      final SpecimenThread thread = countryAs(
        verbatim: <Json>[
          entry(
            'GUATEMALA',
            'decided_transcript',
            'region-left',
            'obs-left-qwen',
          ),
          entry(
            'Guatemala',
            'decided_transcript',
            'region-right',
            'obs-right-muse',
          ),
        ],
        settled: <String>['obs-left-qwen', 'obs-right-muse'],
      );
      await pumpFields(tester, recordJson(thread), thread: thread);
      for (final String line in <String>[
        'Label 1 · $qwen · decided transcript · settled the value',
        'Label 2 · $muse · decided transcript · settled the value',
      ]) {
        expect(inRow('country', find.text(line)), findsOneWidget);
      }
    });

    testWidgets('a field that went to review marks nothing', (
      WidgetTester tester,
    ) async {
      final SpecimenThread thread = countryAs(
        verbatim: <Json>[
          entry(
            'GUATEMALA',
            'decided_transcript',
            'region-left',
            'obs-left-qwen',
          ),
          entry(
            'Honduras',
            'decided_transcript',
            'region-right',
            'obs-right-muse',
          ),
        ],
        settled: const <String>[],
        state: 'unresolved',
      );
      await pumpFields(tester, recordJson(thread), thread: thread);
      expect(
        inRow('country', find.text('Label 1 · $qwen · decided transcript')),
        findsOneWidget,
      );
      expect(
        inRow('country', find.text('Label 2 · $muse · decided transcript')),
        findsOneWidget,
        reason: "each label's reading stays in view (G32)",
      );
      expect(
        inRow('country', find.textContaining('settled the value')),
        findsNothing,
      );
    });

    testWidgets('a fallback that settled from a raw reading says so', (
      WidgetTester tester,
    ) async {
      final SpecimenThread thread = countryAs(
        verbatim: <Json>[
          entry('GUATEMALA', 'decided_transcript', 'region-right', null),
        ],
        settled: <String>['obs-right-qwen'],
      );
      await pumpFields(tester, recordJson(thread), thread: thread);
      expect(
        inRow('country', find.text('$qwen · raw reading · settled the value')),
        findsOneWidget,
      );
    });

    testWidgets('a no-pick field marks the reading a lookup confirmed', (
      WidgetTester tester,
    ) async {
      final SpecimenThread thread = countryAs(
        verbatim: <Json>[
          entry('GUATEMALA', 'raw_reading', 'region-right', 'obs-right-qwen'),
          entry('GUATEMALA.', 'raw_reading', 'region-right', 'obs-right-muse'),
        ],
        settled: <String>['obs-right-muse'],
      );
      await pumpFields(tester, recordJson(thread), thread: thread);
      expect(
        inRow('country', find.text('$muse · raw reading · settled the value')),
        findsOneWidget,
      );
      expect(
        inRow('country', find.text('$qwen · raw reading')),
        findsOneWidget,
        reason: 'one label, so no entry names it',
      );
    });
  });
}
