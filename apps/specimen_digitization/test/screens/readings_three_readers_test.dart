// A label read by three models (two verified families and one with no mark).
//
// The backend keeps the rule that a label needs at least two independent
// readings. It writes one disagreement entry per label: with three or more
// readings, the least-agreeing pair's fields sit at the top level and every
// pair is listed in `comparisons`. Some fixtures here still give one label
// several rows, as a guard. These tests hold the Readings segment to every
// reading shown, one comparison and one status per label, and the pair a
// comparison describes named rather than "Left" and "Right".

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/risk_assessment.dart';
import 'package:specimen_digitization/src/screens/workbench/reader_heading.dart';
import 'package:specimen_digitization/src/screens/workbench/reader_identity.dart';
import 'package:specimen_digitization/src/screens/workbench/readings_panel.dart';
import 'package:specimen_digitization/src/widgets/diff_text.dart';

import '../widgets/harness.dart';

const String qwen = 'Qwen/Qwen3-VL-30B-A3B-Instruct';
const String muse = 'meta-models/Muse-Glimmer-30B';

/// A model family with no verified mark. It must read as text alone.
const String third = 'nvidia/nemotron-nano-vl';

Json reading(String id, String model, String text) => <String, dynamic>{
  'id': id,
  'observation_id': id,
  'region_id': 'r1',
  'model_id': model,
  'literal_text': text,
};

/// The three readers of one label. The first (in reader order) and the second
/// agree; the third differs from them in one place.
final List<Json> readings = <Json>[
  reading('o-qwen', qwen, 'Chicago 1912'),
  reading('o-muse', muse, 'Chicago 1912'),
  reading('o-third', third, 'Chicago 1917'),
];

/// One pair's row in the run's list of comparisons.
Json comparisonRow(String status) => <String, dynamic>{
  'region_id': 'r1',
  'blob_ref': 'blob-$status',
  'status': status,
  'reasons': <String>[],
};

Json transcription(String status, double? ratio) => <String, dynamic>{
  'region_id': 'r1',
  'resolved': false,
  'alternatives': <String>['Chicago 1912', 'Chicago 1917'],
  'observation_ids': <String>['o-qwen', 'o-muse', 'o-third'],
  'alignment_status': status,
  'disagreement_ratio': ?ratio,
  'alignment_reasons': <String>[],
};

Specimen record({
  List<Json> transcriptions = const <Json>[],
  List<Json> comparisons = const <Json>[],
}) => Specimen(<String, dynamic>{
  'specimen_id': 'three-readers',
  'revision': 2,
  'regions': <Json>[
    <String, dynamic>{'region_id': 'r1'},
  ],
  'observations': readings,
  'transcriptions': transcriptions,
  'run': <String, dynamic>{'disagreements': comparisons},
});

Future<void> pumpReadings(
  WidgetTester tester,
  Specimen specimen, {
  String? selected = 'r1',
  Future<Json> Function(ArtifactRequest)? loadArtifact,
}) => pumpComponent(
  tester,
  SingleChildScrollView(
    child: WorkbenchReadings(
      specimen: specimen,
      anchors: <String, GlobalKey>{'r1': GlobalKey()},
      selectedRegionId: selected,
      onSelectRegion: (_) {},
      onChange: (_) async {},
      transcriptionBlockedReason: null,
      declarationsBlocked: true,
      loadArtifact: loadArtifact,
    ),
  ),
  size: const Size(1000, 2400),
);

Future<void> openComparison(WidgetTester tester) async {
  await tester.tap(find.text(WorkbenchReadings.differencesHeading));
  await tester.pumpAndSettle();
}

Finder mark(ReaderBrand brand) => find.byWidgetPredicate(
  (Widget widget) =>
      widget is Image &&
      widget.image is AssetImage &&
      (widget.image as AssetImage).assetName == brand.asset,
  description: 'the ${brand.name} mark',
);

void main() {
  testWidgets('all three readings show, each against the first', (
    WidgetTester tester,
  ) async {
    await pumpReadings(tester, record());
    expect(find.byType(ReaderHeading), findsNWidgets(3));
    for (final String model in <String>[qwen, muse, third]) {
      expect(find.text(model), findsOneWidget);
    }
    expect(find.text('Chicago 1912'), findsNWidgets(2));
    // Silent when identical (it is spoken, not drawn), so count the readings
    // that match the first one instead of looking for a sentence.
    expect(
      find.byWidgetPredicate(
        (Widget widget) =>
            widget is DiffText &&
            widget.reference != null &&
            widget.text == widget.reference,
        description: 'a reading that matches the first',
      ),
      findsOneWidget,
    );
    expect(find.text('Differs in 1 place'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a reader with no verified mark gets text alone', (
    WidgetTester tester,
  ) async {
    await pumpReadings(tester, record());
    expect(mark(ReaderBrand.qwen3Vl), findsOneWidget);
    expect(mark(ReaderBrand.muse), findsOneWidget);
    expect(
      find.byType(Image),
      findsNWidgets(2),
      reason: 'the third reader must not borrow a mark it has no right to',
    );
  });

  testWidgets('the all-labels summary counts three results', (
    WidgetTester tester,
  ) async {
    await pumpReadings(tester, record(), selected: null);
    expect(
      find.text('3 model results · Differences to review'),
      findsOneWidget,
    );
  });

  group('three comparison rows for one label', () {
    testWidgets('are one request and one button', (WidgetTester tester) async {
      final List<ArtifactRequest> requests = <ArtifactRequest>[];
      await pumpReadings(
        tester,
        record(
          transcriptions: <Json>[transcription('disagreement', 0.5)],
          comparisons: <Json>[
            comparisonRow('agreement'),
            comparisonRow('disagreement'),
            comparisonRow('disagreement'),
          ],
        ),
        loadArtifact: (ArtifactRequest request) async {
          requests.add(request);
          return <String, dynamic>{'status': 'agreement'};
        },
      );
      await openComparison(tester);
      final Finder button = find.text('Read the comparison for Label 1');
      expect(button, findsOneWidget);
      await tester.tap(button);
      await tester.pumpAndSettle();
      expect(requests, hasLength(1));
      expect(requests.single.kind, ArtifactKind.disagreement);
      expect(requests.single.id, 'r1');
      expect(find.text('Exact retained readings agree'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('name the pair they compare, not left and right', (
      WidgetTester tester,
    ) async {
      const Map<String, Object> start = <String, Object>{
        'utf16_codeunit': 11,
        'line': 1,
      };
      const Map<String, Object> end = <String, Object>{
        'utf16_codeunit': 12,
        'line': 1,
      };
      await pumpReadings(
        tester,
        record(
          transcriptions: <Json>[transcription('disagreement', 0.5)],
          comparisons: <Json>[
            comparisonRow('disagreement'),
            comparisonRow('disagreement'),
            comparisonRow('disagreement'),
          ],
        ),
        // The pair that is not the first reading's: second against third.
        loadArtifact: (ArtifactRequest request) async => <String, dynamic>{
          'status': 'disagreement',
          'left': <String, dynamic>{'observation_id': 'o-muse'},
          'right': <String, dynamic>{'observation_id': 'o-third'},
          'alternatives': <Json>[
            <String, dynamic>{
              'operation': 'replace',
              'left': <String, dynamic>{
                'start': start,
                'end': end,
                'text': '2',
              },
              'right': <String, dynamic>{
                'start': start,
                'end': end,
                'text': '7',
              },
            },
          ],
        },
      );
      await openComparison(tester);
      await tester.tap(find.text('Read the comparison for Label 1'));
      await tester.pumpAndSettle();
      expect(find.text('Compared: $muse and $third'), findsOneWidget);
      expect(find.text('$muse · Line 1 · UTF-16 [11, 12)'), findsOneWidget);
      expect(find.text('$third · Line 1 · UTF-16 [11, 12)'), findsOneWidget);
      expect(find.textContaining('Left'), findsNothing);
      expect(find.textContaining('Right'), findsNothing);
      expect(find.text('2'), findsOneWidget);
      expect(find.text('7'), findsOneWidget);
      expect(
        find.textContaining('Span does not match'),
        findsNothing,
        reason: 'the pair is checked against the readings it names',
      );
    });
  });

  group('three transcription rows for one label', () {
    testWidgets('give one row and one status, the first the API sent', (
      WidgetTester tester,
    ) async {
      await pumpReadings(
        tester,
        record(
          transcriptions: <Json>[
            transcription('agreement', 0),
            transcription('disagreement', 0.5),
            transcription('policy_blocked', null),
          ],
        ),
      );
      await openComparison(tester);
      expect(find.text('Label 1: the readings differ'), findsOneWidget);
      expect(find.textContaining('Comparison: '), findsOneWidget);
      expect(
        find.text('Comparison: agreement · Difference fraction: 0.0'),
        findsOneWidget,
      );
      expect(find.textContaining('Comparison: disagreement'), findsNothing);
      expect(find.textContaining('Comparison: policy blocked'), findsNothing);
    });

    testWidgets('keep the same choice whatever the rows say', (
      WidgetTester tester,
    ) async {
      await pumpReadings(
        tester,
        record(
          transcriptions: <Json>[
            transcription('policy_blocked', null),
            transcription('agreement', 0),
            transcription('disagreement', 0.5),
          ],
        ),
      );
      await openComparison(tester);
      expect(find.textContaining('Comparison: '), findsOneWidget);
      expect(
        find.text(
          'Comparison: policy blocked · Difference fraction: Not measured',
        ),
        findsOneWidget,
      );
      expect(
        find.text(
          'Comparison limits prevented measurement. This is not agreement.',
        ),
        findsOneWidget,
      );
    });
  });

  testWidgets('the comparison caveat holds for any number of readings', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      TranscriptionComparisonSummary(
        transcription: transcription('agreement', 0),
      ),
    );
    expect(
      find.text('Agreement between readings does not make them right.'),
      findsOneWidget,
    );
    expect(find.textContaining('Two readings'), findsNothing);
  });
}
