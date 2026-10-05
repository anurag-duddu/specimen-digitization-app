// Synthetic frontend review captures, using the production app and its shell.
// The photograph, regions, readings, fields and history come from the existing
// checked-in golden fixture. Only its filename and the two recorded model
// identifiers change. These images are not authenticated production evidence.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/reader_heading.dart';
import 'package:specimen_digitization/src/screens/workbench/reader_identity.dart';
import 'package:specimen_digitization/src/screens/workbench/source_pane.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../reading_region_comparison_test.dart' show selectLabel;
import '../ui_finders.dart';
import 'golden_harness.dart';

const qwenModel = 'Qwen/Qwen3-VL-30B-A3B-Instruct';
const museModel = 'meta-models/Muse-Glimmer-30B';
const desktop = Size(1440, 900);

Specimen frontendReviewSpecimen() {
  final base = goldenVerifiedSpecimen();
  const modelsByObservation = {'o1': qwenModel, 'o2': museModel};
  return Specimen({
    ...base.data,
    'filename': 'subject_105526321.jpeg',
    'observations': [
      for (final observation in base.observations)
        {
          ...observation,
          if (modelsByObservation.containsKey(observation['observation_id']))
            'model_id': modelsByObservation[observation['observation_id']],
        },
    ],
  });
}

Future<void> showFrontendReview(WidgetTester tester) async {
  final record = frontendReviewSpecimen();
  await pumpGoldenApp(
    tester,
    window: desktop,
    brightness: Brightness.light,
    location: goldenSpecimenLocationOf(record.id),
    repository: GoldenQueueRepository([record]),
  );
}

WorkbenchSourcePane sourcePane(WidgetTester tester) =>
    tester.widget<WorkbenchSourcePane>(find.byType(WorkbenchSourcePane));

UiTabs recordTabs(WidgetTester tester) =>
    tester.widget<UiTabs>(uiTabs('Record view'));

Finder readerMark(ReaderBrand brand) => find.byWidgetPredicate(
  (widget) =>
      widget is Image &&
      widget.image is AssetImage &&
      (widget.image as AssetImage).assetName == brand.asset,
  description: 'recorded model mark ${brand.name}',
);

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  testWidgets('synthetic desktop entry shows fields and the whole photograph', (
    tester,
  ) async {
    await showFrontendReview(tester);
    expect(recordTabs(tester).tabs.map((tab) => tab.label), [
      'Specimen data',
      'Labels',
      'History',
    ]);
    expect(recordTabs(tester).selected.value, 0);
    expect(sourcePane(tester).selectedRegionId, isNull);
    expect(sourcePane(tester).labelReviewActive, isFalse);
    final viewer = tester.widget<InteractiveViewer>(
      find.byType(InteractiveViewer),
    );
    expect(viewer.transformationController!.value.getMaxScaleOnAxis(), 1);
    expect(find.text('#105526321'), findsWidgets);
    expect(find.textContaining('Supported · United States'), findsOneWidget);
    expect(find.text('Needs review · Unknown · Required'), findsOneWidget);
    expect(find.text('As written'), findsNothing);
    expect(find.byType(ReaderHeading), findsNothing);
    expect(find.bySemanticsLabel(RegExp('Test environment')), findsWidgets);
    expect(tester.takeException(), isNull);
    await expectGolden(
      tester,
      'frontend-review-fields__synthetic__large-1440x900__light__text1.0',
    );
  });

  testWidgets(
    'synthetic desktop label review shows full model names and marks',
    (tester) async {
      await showFrontendReview(tester);
      expect(sourcePane(tester).selectedRegionId, isNull);
      await selectLabel(tester, 1);
      await settleImages(tester);
      expect(recordTabs(tester).selected.value, 1);
      expect(sourcePane(tester).selectedRegionId, 'r1');
      expect(sourcePane(tester).labelReviewActive, isTrue);
      expect(find.text(qwenModel), findsOneWidget);
      expect(find.text(museModel), findsOneWidget);
      expect(readerMark(ReaderBrand.qwen3Vl), findsOneWidget);
      expect(readerMark(ReaderBrand.muse), findsOneWidget);
      expect(find.text('Chicago 1912'), findsWidgets);
      expect(find.text('Differs in 1 place'), findsOneWidget);
      expect(find.text('#105526321'), findsWidgets);
      expect(find.byType(Scrim), findsNothing);
      expect(tester.takeException(), isNull);
      await expectGolden(
        tester,
        'frontend-review-readings__synthetic__large-1440x900__light__text1.0',
      );
    },
  );
}
