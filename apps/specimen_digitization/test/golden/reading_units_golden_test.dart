// Size-class goldens of a label's reading units (docs/execution/units/
// PLAN.md, WP 1.6): the record screen at the compact, medium and expanded
// windows (design/05-responsive-and-platform-adaptation.md, `WindowClass`),
// in both themes, with Label 1 selected in the readings segment.
//
// The record is the golden fixture's (golden_harness.dart) with three
// readings of Label 1, named by the reader routes' model ids
// (src/specimen_digitization/model_gateway.py, handwriting-*), and units cut
// from them. These images are not production evidence.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/reading_units_view.dart';
import 'package:specimen_digitization/src/screens/workbench/source_pane.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../reading_region_comparison_test.dart' show selectLabel;
import 'golden_harness.dart';
import 'size_classes_golden_test.dart'
    show captureLayoutErrors, expectKnownOverflow;

const Map<String, String> readings = <String, String>{
  'Qwen/Qwen3-VL-30B-A3B-Instruct':
      'FMNH-INS 1001\nDanaus plexippus\nChicago, Illinois',
  'meta-models/Muse-Glimmer-30B':
      'FMNH-INS 1001\nDanaus plexipus\nChicago, Illinois',
  'nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4':
      'FMNH-INS 1007\nDanaus plexippus\nChicago, Ilinois',
};

/// Observation ids, one per reader, in the order above.
List<String> get ids => <String>[
  for (int i = 1; i <= readings.length; i++) 'o$i',
];

/// One unit of Label 1: each reader's [texts] where they stand in its reading.
Json unit(
  int number,
  int line,
  List<String> texts, {
  required String image,
  String means = '',
  String role = '',
  List<String> fields = const <String>[],
  String note = '',
}) {
  final List<String> whole = readings.values.toList();
  return <String, dynamic>{
    'id': 'r1:$number',
    'label': 'r1',
    'lines': <int>[line, line],
    'readers': <String, dynamic>{
      for (final (int i, String id) in ids.indexed)
        id: <String, dynamic>{
          'text': texts[i],
          // Every reading here is in the Basic Multilingual Plane, so its
          // UTF-16 index is its code-point index.
          'start': whole[i].indexOf(texts[i]),
          'end': whole[i].indexOf(texts[i]) + texts[i].length,
        },
    },
    'image': image,
    'means': means,
    'role': role,
    'fields': fields,
    'note': note,
  };
}

Specimen unitsSpecimen() {
  final Specimen base = goldenVerifiedSpecimen();
  return Specimen(<String, dynamic>{
    ...base.data,
    'filename': 'subject_105526321.jpeg',
    'observations': <Json>[
      for (final (int i, MapEntry<String, String> reading)
          in readings.entries.indexed)
        <String, dynamic>{
          'id': ids[i],
          'observation_id': ids[i],
          'model_id': reading.key,
          'region_id': 'r1',
          'literal_text': reading.value,
        },
    ],
    'run': <String, dynamic>{
      'reading_units': <Json>[
        <String, dynamic>{
          'label': 'r1',
          'units': <Json>[
            unit(
              1,
              1,
              <String>['FMNH-INS 1001', 'FMNH-INS 1001', 'FMNH-INS 1007'],
              image: 'FMNH-INS 1001',
              means: 'Field Museum insect catalogue number 1001',
              fields: <String>['fmnh_ins_number'],
            ),
            unit(
              2,
              2,
              <String>[
                'Danaus plexippus',
                'Danaus plexipus',
                'Danaus plexippus',
              ],
              image: 'uncertain',
              means: 'genus Danaus, species plexippus',
              fields: <String>['taxon'],
              note: 'One reading drops a p.',
            ),
            unit(
              3,
              3,
              <String>[
                'Chicago, Illinois',
                'Chicago, Illinois',
                'Chicago, Ilinois',
              ],
              image: 'Chicago, Illinois',
              means: 'Chicago, Illinois, United States',
              fields: <String>['city', 'province_state'],
            ),
          ],
        },
      ],
    },
  });
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  for (final String window in <String>[
    'compact-390x844',
    'medium-768x1024',
    'expanded-1180x820',
  ]) {
    goldenThemes.forEach((String theme, Brightness brightness) {
      testWidgets('reading units at $window in $theme', (
        WidgetTester tester,
      ) async {
        captureLayoutErrors();
        final Specimen record = unitsSpecimen();
        await pumpGoldenApp(
          tester,
          window: goldenWindows[window]!,
          brightness: brightness,
          location: goldenSpecimenLocationOf(record.id),
          repository: GoldenQueueRepository(<Specimen>[record]),
        );
        await selectLabel(tester, 1);
        await settleImages(tester);
        expect(
          tester
              .widget<WorkbenchSourcePane>(find.byType(WorkbenchSourcePane))
              .selectedRegionId,
          'r1',
        );
        expect(find.byType(ReadingUnitsView), findsOneWidget);
        expect(find.text(ReadingUnitsView.title).hitTestable(), findsOneWidget);
        expect(find.byType(Scrim), findsNothing);
        final String golden = 'workbench-reading-units__${window}__$theme';
        expectKnownOverflow(tester, golden);
        await expectGolden(tester, golden);
      });
    });
  }
}
