// S5's canonical thread (`test/fixtures/thread-example.json`, #171) through
// every screen that reads a thread: the Readings sections, the Fields
// segment and the Processing detail, at a phone, a tablet and a desktop
// width. The model reads the file whole (`thread_model_test.dart`); this
// proves the screens draw it whole too, with no overflow, and with the parts
// a reviewer relies on in the words the spec gives them.

import 'dart:convert';
import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/operational_panel.dart';
import 'package:specimen_digitization/src/screens/workbench/fields_panel.dart';
import 'package:specimen_digitization/src/screens/workbench/readings_panel.dart';
import 'package:specimen_digitization/src/thread/thread.dart';
import 'package:specimen_digitization/src/vocabulary.dart';

import '../widgets/harness.dart';

SpecimenThread canonical() => SpecimenThread.fromJson(
  jsonDecode(File('test/fixtures/thread-example.json').readAsStringSync())
      as Json,
);

/// The workspace's account of the same record, as the run left it, with
/// each field named as the repository names it.
Specimen recordOf(SpecimenThread thread) => Specimen(<String, dynamic>{
  'specimen_id': thread.specimenId,
  'revision': thread.revision,
  'run': <String, dynamic>{
    'run_id': thread.run.runId,
    'stage': thread.run.stage,
  },
  'regions': <Json>[
    for (final ThreadRegion region in thread.regions)
      <String, dynamic>{'region_id': region.regionId},
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
  ],
  'fields': <Json>[
    for (final ThreadField f in thread.fields)
      <String, dynamic>{
        'field_key': f.fieldKey,
        'display_name': vocabularyLabel(f.fieldKey!),
        'required': f.group == ThreadFieldGroup.mandatory,
        'state': f.state,
        'literal_value': f.verbatim.length == 1 ? f.verbatim.single.text : null,
        'parsed_value': f.parsed,
        'normalized': f.normalized,
        'authority_id': f.authorityId,
      },
  ],
});

/// A phone, a tablet and a desktop pane.
const List<double> widths = <double>[390, 768, 1180];

Future<void> pumpAt(WidgetTester tester, double width, Widget child) =>
    pumpComponent(
      tester,
      SingleChildScrollView(
        child: SizedBox(width: width, child: child),
      ),
      size: Size(width, 6000),
    );

void main() {
  final SpecimenThread thread = canonical();
  final Specimen record = recordOf(thread);
  const String qwen = 'model/handwriting-qwen';
  const String muse = 'model/handwriting-muse';

  for (final double width in widths) {
    group('at $width dp', () {
      testWidgets('the Readings sections draw both labels and decisions', (
        WidgetTester tester,
      ) async {
        await pumpAt(
          tester,
          width,
          WorkbenchReadings(
            specimen: record,
            thread: thread,
            anchors: <String, GlobalKey>{
              for (final ThreadRegion region in thread.regions)
                region.regionId!: GlobalKey(),
            },
            selectedRegionId: null,
            onSelectRegion: (_) {},
            onChange: (_) async {},
            transcriptionBlockedReason: null,
            declarationsBlocked: true,
          ),
        );
        expect(tester.takeException(), isNull);
        for (final String text in <String>[
          'Label 1',
          'Label 2',
          'The first pass chose $qwen',
          'The first pass chose no reading',
          'Transcription not resolved',
          'Handed to the harness',
        ]) {
          expect(find.text(text), findsWidgets, reason: text);
        }
      });

      testWidgets('the Fields segment draws layers, evidence and authority', (
        WidgetTester tester,
      ) async {
        await pumpAt(
          tester,
          width,
          WorkbenchFields(
            specimen: record,
            thread: thread,
            anchors: <String, GlobalKey>{
              for (final Json f in record.fields)
                f['field_key'] as String: GlobalKey(),
            },
            pending: const [],
            onPendingChanged: (_) {},
            onFocusRegion: (_) {},
          ),
        );
        expect(tester.takeException(), isNull);
        // A phone keeps each row's Values disclosure closed; open them all
        // so the evidence is on screen at every width.
        for (final Finder closed in <Finder>[
          for (final Element e in find.byType(UiDisclosure).evaluate())
            if (!tester
                .widget<UiDisclosure>(find.byWidget(e.widget))
                .initiallyExpanded)
              find.byWidget(e.widget),
        ]) {
          await tester.ensureVisible(closed);
          await tester.tap(
            find.descendant(of: closed, matching: find.text('Values')),
          );
          await tester.pumpAndSettle();
        }
        expect(tester.takeException(), isNull);
        for (final String text in <String>[
          'Required fields',
          'Optional fields',
          'Settled',
          'As written',
          "$qwen's reading supports this value · Label 2",
          "$muse's reading supports this value · Label 2",
          'Google Maps supports this value · place ID fixture-place',
          'Google Maps place ID fixture-place',
          'GBIF decides this value · gbif/species/1651891',
          'Catalogue of Life contradicts this value · col/taxon/fixture-col-taxon',
          'GBIF record 1651891',
          'fixture credit',
          "Label 1 · $qwen · decided transcript · settled the value",
          "Label 2 · $qwen · raw reading · settled the value",
        ]) {
          expect(find.text(text), findsWidgets, reason: text);
        }
      });

      testWidgets('the Processing detail names the run and its trace', (
        WidgetTester tester,
      ) async {
        await pumpAt(
          tester,
          width,
          ProcessingDetail(
            specimen: record,
            thread: thread,
            canOperate: false,
            busy: false,
            onAction: (_) async {},
          ),
        );
        expect(tester.takeException(), isNull);
        for (final String text in <String>[
          'Run',
          thread.run.runId!,
          'Profile',
          'zoology insects slides 1.0.0',
          'Policy',
          'insects-clearance-v1',
          'Open trace',
        ]) {
          expect(find.text(text), findsWidgets, reason: text);
        }
      });
    });
  }
}
