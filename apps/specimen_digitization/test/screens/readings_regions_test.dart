// The Readings segment, one section per label region (UI.md T2.2, part
// one): a two-label slide shows two sections, each with its own readings,
// its heading, and each reading's route and prompt version.

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

Future<void> pumpReadings(WidgetTester tester, Specimen specimen) =>
    pumpComponent(
      tester,
      SingleChildScrollView(
        child: WorkbenchReadings(
          specimen: specimen,
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
    await pumpReadings(tester, specimenFor(thread));
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
    await pumpReadings(tester, specimenFor(thread));
    expect(
      tester.getSemantics(inSection('region-right', find.text('Label 2'))),
      matchesSemantics(label: 'Label 2', isHeader: true),
    );
    handle.dispose();
  });

  testWidgets('a card names its route and its prompt version', (
    WidgetTester tester,
  ) async {
    await pumpReadings(tester, specimenFor(thread));
    expect(
      inSection(
        'region-left',
        find.text('Route handwriting-qwen · Prompt literal-transcription-v3'),
      ),
      findsOneWidget,
    );
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
    );
    expect(
      inSection(
        'region-empty',
        find.text('No reading recorded for this label.'),
      ),
      findsOneWidget,
    );
  });
}
