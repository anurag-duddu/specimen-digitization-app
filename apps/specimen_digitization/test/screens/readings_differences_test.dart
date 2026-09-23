// The Readings segment's differences list (UI.md T1.3).
//
// One row per label region, and "the readings differ" only when the region's
// transcription carries two or more distinct readings. The pilot leaves every
// transcription unresolved, so this is what the ten pilot records show.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/readings_panel.dart';

import '../widgets/harness.dart';

/// The whole words "differ" and "differs", in any case. The segment's heading,
/// "Differences and resolution", is not a claim about any region.
final RegExp claimsDifference = RegExp(r'\bdiffers?\b', caseSensitive: false);

Json reading(String id, String text) => <String, dynamic>{
  'id': id,
  'observation_id': id,
  'region_id': 'r1',
  'model_id': 'Reader $id',
  'provider': 'Provider $id',
  'literal_text': text,
};

Specimen record({
  required List<String> texts,
  bool withTranscription = true,
  bool withDisagreement = true,
  bool resolved = false,
}) {
  final List<String> alternatives = texts.toSet().toList();
  final Json transcription = <String, dynamic>{
    'region_id': 'r1',
    'resolved': resolved,
    if (resolved) 'text': texts.first,
    'alternatives': alternatives,
    'alignment_status': 'policy_blocked',
    'alignment_reasons': <String>['pilot_risk_unmeasured'],
  };
  return Specimen(<String, dynamic>{
    'specimen_id': 'pilot-1',
    'revision': 4,
    'regions': <Json>[
      <String, dynamic>{'region_id': 'r1'},
    ],
    'observations': <Json>[
      for (final (int i, String text) in texts.indexed) reading('o$i', text),
    ],
    if (withTranscription) 'transcriptions': <Json>[transcription],
    // The list the client used to synthesise from every unresolved
    // transcription, and the shape older fixtures still inject.
    if (withDisagreement) 'disagreements': <Json>[transcription],
  });
}

Future<void> pumpReadings(WidgetTester tester, Specimen specimen) =>
    pumpComponent(
      tester,
      SingleChildScrollView(
        child: WorkbenchReadings(
          specimen: specimen,
          anchors: <String, GlobalKey>{'r1': GlobalKey()},
          selectedRegionId: null,
          onSelectRegion: (_) {},
          onChange: (_) async {},
          transcriptionBlockedReason: null,
          declarationsBlocked: true,
        ),
      ),
      size: const Size(1000, 2400),
    );

void main() {
  testWidgets('identical readings are unresolved, never said to differ', (
    WidgetTester tester,
  ) async {
    await pumpReadings(
      tester,
      record(texts: <String>['Chicago 1912', 'Chicago 1912']),
    );
    expect(find.text('Label 1: unresolved'), findsOneWidget);
    expect(find.textContaining(claimsDifference), findsNothing);
  });

  testWidgets('readings that differ get one row, which says so', (
    WidgetTester tester,
  ) async {
    await pumpReadings(
      tester,
      record(texts: <String>['Chicago 1912', 'Chicago 1917']),
    );
    expect(find.text('Label 1: the readings differ'), findsOneWidget);
    expect(
      find.text('Label 1: unresolved'),
      findsNothing,
      reason: 'one row per region, not a difference row and a state row',
    );
  });

  testWidgets('a difference with no transcription is still shown', (
    WidgetTester tester,
  ) async {
    await pumpReadings(
      tester,
      record(
        texts: <String>['Chicago 1912', 'Chicago 1917'],
        withTranscription: false,
      ),
    );
    expect(find.text('Label 1: the readings differ'), findsOneWidget);
  });

  testWidgets('a resolved region keeps the readings it chose between', (
    WidgetTester tester,
  ) async {
    await pumpReadings(
      tester,
      record(texts: <String>['Chicago 1912', 'Chicago 1917'], resolved: true),
    );
    expect(find.text('Label 1: resolved'), findsOneWidget);
    expect(
      find.text('Readings: Chicago 1912 · Chicago 1917', findRichText: true),
      findsOneWidget,
    );
  });

  testWidgets('an older difference row follows the same rule', (
    WidgetTester tester,
  ) async {
    await pumpReadings(
      tester,
      record(
        texts: <String>['Chicago 1912', 'Chicago 1912'],
        withTranscription: false,
      ),
    );
    expect(find.text('Label 1: unresolved'), findsOneWidget);
    expect(find.textContaining(claimsDifference), findsNothing);
  });
}
