// The thread in each field: what was written, by whom, and what settled it
// (UI.md T2.3, part two).

import 'dart:convert';
import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
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

    testWidgets("a field's own findings are read first (#171)", (
      WidgetTester tester,
    ) async {
      final Json json = fixtureJson();
      fieldIn(json, 'country')['findings'] = <Json>[
        <String, dynamic>{
          'rule_id': 'value-shape',
          'severity': 'warning',
          'field_key': 'country',
          'reason_code': 'value_shape_mismatch:country',
        },
      ];
      final SpecimenThread thread = SpecimenThread.fromJson(json);
      await pumpFields(tester, recordJson(thread), thread: thread);
      expect(
        inRow('country', find.text("Doesn't look like a country")),
        findsOneWidget,
        reason: "the field's list, though the decision's does not name it",
      );
    });

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

    testWidgets("a label's fallback names the label and the reading it used", (
      WidgetTester tester,
    ) async {
      // Label 1 settled on its own decided reading; label 2 through a
      // fallback lookup on its other reader's raw reading (#171, section 8).
      final SpecimenThread thread = countryAs(
        verbatim: <Json>[
          entry(
            'GUATEMALA',
            'decided_transcript',
            'region-left',
            'obs-left-qwen',
          ),
          entry(
            'GUATEMALA',
            'decided_transcript',
            'region-right',
            'obs-right-muse',
          ),
        ],
        settled: <String>['obs-left-qwen', 'obs-right-qwen'],
      );
      await pumpFields(tester, recordJson(thread), thread: thread);
      expect(
        inRow(
          'country',
          find.text('Label 1 · $qwen · decided transcript · settled the value'),
        ),
        findsOneWidget,
      );
      expect(
        inRow('country', find.text('Label 2 · $muse · decided transcript')),
        findsOneWidget,
        reason: 'its own reading did not settle the value',
      );
      expect(
        inRow(
          'country',
          find.text('Label 2 · $qwen · raw reading · settled the value'),
        ),
        findsOneWidget,
      );
    });
  });

  group("each value's layer (UI.md T2.3 part four)", () {
    /// The row's face: its name and the one label under it.
    Finder onFace(String key, String text) => inRow(
      key,
      find.descendant(of: find.byType(UiListRow), matching: find.text(text)),
    );

    /// The fixture with each named field's layer set, and [extra] fields.
    SpecimenThread withLayers(
      Map<String, String?> layers, {
      List<Json> extra = const <Json>[],
    }) {
      final Json json = fixtureJson();
      for (final MapEntry<String, String?> entry in layers.entries) {
        fieldIn(json, entry.key)['layer'] = entry.value;
      }
      (json['fields'] as List<dynamic>).addAll(extra);
      return SpecimenThread.fromJson(json);
    }

    /// A derived field of the run, filled from [from] (G37, G41, G44).
    Json derived(String key, List<String> from) => <String, dynamic>{
      'field_key': key,
      'group': 'mandatory',
      'state': 'supported',
      'layer': 'derived',
      'derived_from': from,
      'verbatim': <Json>[],
      'parsed': '1978-05-12',
      'precision': 'day',
      'century_rule': null,
      'normalized': null,
      'authority_id': null,
      'evidence': <Json>[
        <String, dynamic>{
          'evidence_id': 'evidence-derivation-1',
          'relation': 'decides',
          'source': 'derivation-rules-v1',
          'locator': null,
          'outcome': 'recorded',
          'observation_ids': <String>[],
        },
      ],
    };

    /// A settled field with nothing else to say, for a derivation to name.
    Json plain(String key) => <String, dynamic>{
      'field_key': key,
      'group': 'optional',
      'state': 'supported',
      'layer': 'settled',
      'verbatim': <Json>[],
      'parsed': null,
      'precision': null,
      'century_rule': null,
      'normalized': null,
      'authority_id': null,
      'evidence': <Json>[],
    };

    /// The record, with [names] as the fields' display names.
    Json named(SpecimenThread thread, Map<String, String> names) {
      final Json record = recordJson(thread);
      for (final Json f in (record['fields'] as List<dynamic>).cast<Json>()) {
        if (names[f['field_key']] case final String name) {
          f['display_name'] = name;
        }
      }
      return record;
    }

    testWidgets('a verbatim and a settled value each name their layer', (
      WidgetTester tester,
    ) async {
      final SpecimenThread thread = withLayers(<String, String?>{
        'country': 'settled',
        'collectors': 'verbatim',
      });
      await pumpFields(tester, recordJson(thread), thread: thread);
      expect(onFace('country', 'Settled'), findsOneWidget);
      expect(onFace('collectors', 'As written'), findsOneWidget);
      expect(
        inRow('collectors', find.textContaining('not settled')),
        findsNothing,
        reason: 'a field no lookup checks clears as written',
      );
    });

    testWidgets('a derived value names the fields it came from', (
      WidgetTester tester,
    ) async {
      // G44: one date fills To. G37: a county from the coordinates, when
      // the whole uncertainty circle lies in one unit.
      final SpecimenThread thread = withLayers(
        const <String, String?>{},
        extra: <Json>[
          derived('date_visited_to', <String>['date_visited_from']),
          plain('latitude'),
          plain('longitude'),
          derived('county', <String>['latitude', 'longitude']),
        ],
      );
      await pumpFields(
        tester,
        named(thread, <String, String>{
          'date_visited_from': 'Date visited from',
          'latitude': 'Latitude',
          'longitude': 'Longitude',
        }),
        thread: thread,
      );
      expect(
        onFace('date_visited_to', 'Derived from Date visited from'),
        findsOneWidget,
      );
      expect(
        onFace('county', 'Derived from Latitude and Longitude'),
        findsOneWidget,
      );
      expect(
        inRow('date_visited_to', find.textContaining('decides this value')),
        findsOneWidget,
        reason: 'its evidence is one step away, in the Values disclosure',
      );
    });

    testWidgets('no recorded layer, no label; an unknown one keeps its word', (
      WidgetTester tester,
    ) async {
      final SpecimenThread thread = withLayers(<String, String?>{
        'country': null,
        'collectors': 'imputed',
      });
      await pumpFields(tester, recordJson(thread), thread: thread);
      for (final String word in <String>['As written', 'Settled']) {
        expect(onFace('country', word), findsNothing);
      }
      expect(onFace('collectors', 'Imputed'), findsOneWidget);
    });

    testWidgets('a field the record has changed shows no layer', (
      WidgetTester tester,
    ) async {
      final SpecimenThread thread = withLayers(<String, String?>{
        'country': 'settled',
      });
      final Json record = recordJson(thread);
      (record['fields'] as List<dynamic>).cast<Json>().firstWhere(
        (Json f) => f['field_key'] == 'country',
      )['parsed_value'] = 'Honduras';
      await pumpFields(tester, record, thread: thread);
      expect(onFace('country', 'Settled'), findsNothing);
    });

    testWidgets('the layer is heard right after the name', (
      WidgetTester tester,
    ) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      final SpecimenThread thread = withLayers(<String, String?>{
        'country': 'settled',
      });
      await pumpFields(tester, recordJson(thread), thread: thread);
      expect(
        find.bySemanticsLabel(RegExp(r'^country, required\. Settled\. ')),
        findsOneWidget,
      );
      handle.dispose();
    });
  });

  group('evidence in words (UI.md T2.3 part five)', () {
    const String qwen = 'Qwen/Qwen2.5-VL-72B-Instruct';
    const String muse = 'muse-handwriting-fixture';

    /// Inside the row's Values disclosure, never on its face.
    Finder inValues(String key, String text) => inRow(
      key,
      find.descendant(of: find.byType(UiDisclosure), matching: find.text(text)),
    );

    /// One evidence entry from [source], quoting [readings].
    Json evidence(
      String source, {
      String relation = 'supports',
      List<String> readings = const <String>[],
    }) => <String, dynamic>{
      'evidence_id': 'evidence-$source',
      'relation': relation,
      'source': source,
      'locator': null,
      'outcome': 'recorded',
      'observation_ids': readings,
    };

    testWidgets("the harness's evidence names the reading it quotes", (
      WidgetTester tester,
    ) async {
      final Json json = fixtureJson();
      fieldIn(json, 'country')['evidence'] = <Json>[
        evidence('field_harness', readings: <String>['obs-right-qwen']),
      ];
      fieldIn(json, 'province_state')['evidence'] = <Json>[
        evidence(
          'field_harness',
          readings: <String>['obs-right-qwen', 'obs-right-muse'],
        ),
      ];
      final SpecimenThread thread = SpecimenThread.fromJson(json);
      await pumpFields(tester, recordJson(thread), thread: thread);
      expect(
        inValues('country', "$qwen's reading supports this value"),
        findsOneWidget,
      );
      expect(
        inValues(
          'province_state',
          "$qwen's and $muse's readings support this value",
        ),
        findsOneWidget,
      );
      expect(find.textContaining('field_harness'), findsNothing);
    });

    testWidgets("a reviewer's filled value says so", (
      WidgetTester tester,
    ) async {
      final Json json = fixtureJson();
      fieldIn(json, 'country')['evidence'] = <Json>[
        evidence('review_decision', relation: 'decides'),
      ];
      final SpecimenThread thread = SpecimenThread.fromJson(json);
      await pumpFields(tester, recordJson(thread), thread: thread);
      expect(inValues('country', 'Set by a reviewer'), findsOneWidget);
      expect(
        inRow('country', find.textContaining('decides this value')),
        findsNothing,
      );
    });

    testWidgets("the authority's record and credit sit in the disclosure", (
      WidgetTester tester,
    ) async {
      final Json json = fixtureJson();
      fieldIn(json, 'country')['authority_identity'] = <String, dynamic>{
        'source': 'google-maps-geocoding',
        'source_record_id': 'fixture-place-id-zacapa',
      };
      (json['fields'] as List<dynamic>).add(<String, dynamic>{
        'field_key': 'taxon',
        'group': 'mandatory',
        'state': 'supported',
        'layer': 'settled',
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
        'authority_identity': <String, dynamic>{
          'name': 'Tachinidae',
          'source': 'gbif',
          'source_record_id': '1111111',
          'credit': 'GBIF.org (2026) GBIF Backbone Taxonomy',
        },
        'evidence': <Json>[],
      });
      final SpecimenThread thread = SpecimenThread.fromJson(json);
      await pumpFields(tester, recordJson(thread), thread: thread);
      expect(
        inValues('country', 'Google Maps place ID fixture-place-id-zacapa'),
        findsOneWidget,
        reason: 'a Google identity has no name (G26)',
      );
      expect(inValues('taxon', 'GBIF record 1111111'), findsOneWidget);
      expect(
        inValues('taxon', 'GBIF.org (2026) GBIF Backbone Taxonomy'),
        findsOneWidget,
      );
      expect(
        inRow(
          'taxon',
          find.descendant(
            of: find.byType(UiListRow),
            matching: find.textContaining('GBIF'),
          ),
        ),
        findsNothing,
        reason: 'never on the row face',
      );
    });

    testWidgets('a derived value shows no identity line until its rules', (
      WidgetTester tester,
    ) async {
      final Json json = fixtureJson();
      fieldIn(json, 'habitat')
        ..['state'] = 'supported'
        ..['layer'] = 'derived'
        ..['derived_from'] = <String>['country']
        ..['authority_identity'] = <String, dynamic>{
          'source': 'apply_derivations',
          'source_record_id': 'derivation-rules-v1',
        };
      final SpecimenThread thread = SpecimenThread.fromJson(json);
      await pumpFields(tester, recordJson(thread), thread: thread);
      expect(inRow('habitat', find.textContaining(' record ')), findsNothing);
      expect(
        inRow('habitat', find.textContaining('apply_derivations')),
        findsNothing,
      );
    });
  });
}
