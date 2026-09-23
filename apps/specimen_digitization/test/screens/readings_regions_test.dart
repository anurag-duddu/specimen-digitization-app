// The Readings segment, one section per label region (UI.md T2.2).
//
// A two-label slide shows two sections, each with its own readings, and, when
// the thread carries them, the comparison beside its components and the
// decision with what each reader handed to the harness.

import 'dart:convert';
import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/readings_panel.dart';
import 'package:specimen_digitization/src/thread/thread.dart';
import 'package:specimen_digitization/src/widgets/widgets.dart';

import '../widgets/harness.dart';

Json fixtureJson() =>
    jsonDecode(
          File('test/fixtures/thread-two-label-slide.json').readAsStringSync(),
        )
        as Json;

/// The workspace response for the same record: the regions it lists and the
/// observations the readers returned, keyed as the workspace keys them.
Specimen specimenFor(
  SpecimenThread thread, {
  List<Json> extraObservations = const <Json>[],
  List<Json> extraRegions = const <Json>[],
}) => Specimen(<String, dynamic>{
  'specimen_id': thread.specimenId,
  'revision': thread.revision,
  'regions': <Json>[
    for (final ThreadRegion region in thread.regions)
      <String, dynamic>{'region_id': region.regionId},
    ...extraRegions,
  ],
  'observations': <Json>[
    for (final ThreadRegion region in thread.regions)
      for (final ThreadReading reading in region.readings)
        <String, dynamic>{
          'id': reading.observationId,
          'observation_id': reading.observationId,
          'region_id': region.regionId,
          'model_id': reading.model,
          'provider': reading.provider,
          'route_id': reading.routeId,
          'prompt_version': reading.promptVersion,
          'literal_text': reading.literalText,
        },
    ...extraObservations,
  ],
  'transcriptions': <Json>[
    <String, dynamic>{
      'region_id': 'region-right',
      'resolved': true,
      'text': 'GUATEMALA Zacapa Sa. de las Minas',
      'alternatives': <String>[
        'GUATEMALA Zacapa Sa. de los Minas',
        'GUATEMALA Zacapa Sa. de las Minas',
      ],
      'alignment_status': 'disagreement',
      'disagreement_ratio': 0.0303,
    },
  ],
});

Future<void> pumpReadings(
  WidgetTester tester,
  Specimen specimen, {
  SpecimenThread? thread,
}) => pumpComponent(
  tester,
  SingleChildScrollView(
    child: WorkbenchReadings(
      specimen: specimen,
      thread: thread,
      anchors: <String, GlobalKey>{
        for (final Json region in specimen.regions)
          region['region_id'] as String: GlobalKey(),
      },
      selectedRegionId: null,
      onSelectRegion: (_) {},
      onChange: (_) async {},
      transcriptionBlockedReason: null,
      declarationsBlocked: true,
    ),
  ),
  size: const Size(1000, 4000),
);

Finder section(String? regionId) => find.byWidgetPredicate(
  (Widget w) => w is ReadingsRegionSection && w.regionId == regionId,
);

Finder inSection(String? regionId, Finder matching) =>
    find.descendant(of: section(regionId), matching: matching);

void main() {
  final SpecimenThread thread = SpecimenThread.fromJson(fixtureJson());

  testWidgets('each region is a section, in order, holding its readings', (
    WidgetTester tester,
  ) async {
    await pumpReadings(tester, specimenFor(thread), thread: thread);
    expect(inSection('region-left', find.text('Label 1')), findsOneWidget);
    expect(inSection('region-right', find.text('Label 2')), findsOneWidget);
    expect(
      tester.getTopLeft(section('region-left')).dy,
      lessThan(tester.getTopLeft(section('region-right')).dy),
    );
    expect(
      inSection('region-left', find.byType(ReadingCard)),
      findsNWidgets(2),
    );
    expect(
      inSection('region-right', find.byType(ReadingCard)),
      findsNWidgets(2),
    );
  });

  testWidgets('the region name is a heading', (WidgetTester tester) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await pumpReadings(tester, specimenFor(thread), thread: thread);
    expect(
      tester.getSemantics(inSection('region-right', find.text('Label 2'))),
      matchesSemantics(label: 'Label 2', isHeader: true),
    );
    handle.dispose();
  });

  testWidgets('a card names its route and its prompt version', (
    WidgetTester tester,
  ) async {
    await pumpReadings(tester, specimenFor(thread), thread: thread);
    expect(
      inSection(
        'region-left',
        find.text('Route handwriting-qwen · Prompt literal-transcription-v3'),
      ),
      findsOneWidget,
    );
  });

  testWidgets('a difference stands beside its components and its caveat', (
    WidgetTester tester,
  ) async {
    await pumpReadings(tester, specimenFor(thread), thread: thread);
    expect(
      inSection('region-right', find.text('Difference 0.03')),
      findsOneWidget,
    );
    expect(
      inSection('region-right', find.text('1 edit over 33 characters')),
      findsOneWidget,
    );
    expect(
      inSection('region-right', find.byType(NotCalibratedChip)),
      findsOneWidget,
    );
    expect(
      inSection('region-left', find.text('No edits over 23 characters')),
      findsOneWidget,
      reason: 'a measured zero is a measurement, and says so',
    );
  });

  testWidgets('an unmeasured difference says so, with the reason behind Why', (
    WidgetTester tester,
  ) async {
    final Json json = fixtureJson();
    final Json region = (json['regions'] as List<dynamic>)[1] as Json;
    region['comparisons'] = <Json>[
      <String, dynamic>{
        'left_observation_id': 'obs-right-qwen',
        'right_observation_id': 'obs-right-muse',
        'algorithm': 'bounded-levenshtein-fraction-v1',
        'ratio': null,
        'status': 'policy_blocked',
        'reasons': <String>['pilot_risk_unmeasured'],
      },
    ];
    final SpecimenThread unmeasured = SpecimenThread.fromJson(json);
    await pumpReadings(tester, specimenFor(unmeasured), thread: unmeasured);
    expect(
      inSection('region-right', find.text('Difference not measured')),
      findsOneWidget,
    );
    expect(
      inSection('region-right', find.textContaining('Difference 0.')),
      findsNothing,
      reason: 'absence is never drawn as a number',
    );
  });

  testWidgets('the decision says who decided and what each reader handed on', (
    WidgetTester tester,
  ) async {
    await pumpReadings(tester, specimenFor(thread), thread: thread);
    expect(
      inSection(
        'region-right',
        find.text('The first pass chose muse-handwriting-fixture'),
      ),
      findsOneWidget,
    );
    expect(
      inSection('region-right', find.textContaining('The fourth word reads')),
      findsOneWidget,
    );
    expect(
      inSection(
        'region-right',
        find.textContaining('first-pass-fixture-model'),
      ),
      findsOneWidget,
    );
    expect(
      inSection('region-right', find.text('Handed to the harness')),
      findsOneWidget,
    );
    expect(
      inSection(
        'region-right',
        find.text('muse-handwriting-fixture · decided transcript'),
      ),
      findsOneWidget,
    );
    expect(
      inSection(
        'region-right',
        find.text('Qwen/Qwen2.5-VL-72B-Instruct · raw reading'),
      ),
      findsOneWidget,
    );
    expect(
      inSection('region-right', find.textContaining('Kept for the raw check')),
      findsOneWidget,
    );
    expect(
      inSection('region-left', find.text('The readings match')),
      findsOneWidget,
    );
  });

  testWidgets('a region with no recorded decision names where the run is', (
    WidgetTester tester,
  ) async {
    final Json json = fixtureJson();
    ((json['regions'] as List<dynamic>)[1] as Json)['first_pass'] = null;
    json['run'] = <String, dynamic>{
      'run_id': 'run-fixture-1',
      'status': 'processing_blocked',
      'stage': 'adjudicate',
      'blocker': 'provider_error',
    };
    final SpecimenThread stopped = SpecimenThread.fromJson(json);
    await pumpReadings(tester, specimenFor(stopped), thread: stopped);
    expect(
      inSection('region-right', find.text('No decision recorded')),
      findsOneWidget,
    );
    expect(
      inSection('region-right', find.textContaining('provider error')),
      findsOneWidget,
    );
  });

  testWidgets('without a thread the sections still group the readings', (
    WidgetTester tester,
  ) async {
    await pumpReadings(tester, specimenFor(thread));
    expect(section('region-left'), findsOneWidget);
    expect(section('region-right'), findsOneWidget);
    expect(find.text('Handed to the harness'), findsNothing);
    expect(find.textContaining('Difference 0.'), findsNothing);
  });

  testWidgets('a reading outside the listed regions goes to the last section', (
    WidgetTester tester,
  ) async {
    await pumpReadings(
      tester,
      specimenFor(
        thread,
        extraObservations: <Json>[
          <String, dynamic>{
            'id': 'obs-stray',
            'region_id': 'region-elsewhere',
            'model_id': 'stray-model',
            'provider': 'stray-provider',
            'literal_text': 'Stray reading',
          },
        ],
      ),
      thread: thread,
    );
    final Finder stray = find.byWidgetPredicate(
      (Widget w) => w is ReadingsRegionSection && w.unassigned,
    );
    expect(
      find.descendant(of: stray, matching: find.text('Unassigned label')),
      findsOneWidget,
    );
    expect(
      tester.getTopLeft(stray).dy,
      greaterThan(tester.getTopLeft(section('region-right')).dy),
    );
  });

  testWidgets('a region no reader read says so', (WidgetTester tester) async {
    await pumpReadings(
      tester,
      specimenFor(
        thread,
        extraRegions: <Json>[
          <String, dynamic>{'region_id': 'region-empty'},
        ],
      ),
      thread: thread,
    );
    expect(
      inSection(
        'region-empty',
        find.text('No reading recorded for this label.'),
      ),
      findsOneWidget,
    );
  });

  testWidgets('the ratio appears once', (WidgetTester tester) async {
    await pumpReadings(tester, specimenFor(thread), thread: thread);
    expect(
      find.textContaining('Difference fraction'),
      findsNothing,
      reason: 'the region section states the ratio with its components',
    );
    await pumpReadings(tester, specimenFor(thread));
    expect(
      find.textContaining('Difference fraction'),
      findsOneWidget,
      reason: 'without a thread the row is still where the ratio is stated',
    );
  });
}
