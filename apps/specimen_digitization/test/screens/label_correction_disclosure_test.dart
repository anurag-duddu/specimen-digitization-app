import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/readings_panel.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../ui_finders.dart';
import '../widgets/harness.dart';

const specimen = Specimen({
  'specimen_id': 'synthetic-label-correction',
  'revision': 1,
  'regions': [
    {'region_id': 'r1'},
  ],
  'observations': [
    {
      'id': 'reading-1',
      'model_id': 'Recorded-model-v2',
      'region_id': 'r1',
      'literal_text': 'Chicago 1917',
    },
  ],
  'transcriptions': [
    {
      'region_id': 'r1',
      'verbatim_text': 'Chicago 1912',
      'value_state': 'supported',
    },
  ],
});

Future<void> showReadings(
  WidgetTester tester,
  LabelDraftController controller,
) => pumpComponent(
  tester,
  SingleChildScrollView(
    child: WorkbenchReadings(
      specimen: specimen,
      anchors: {'r1': GlobalKey()},
      selectedRegionId: 'r1',
      onSelectRegion: (_) {},
      onChange: (_) async =>
          fail('A label draft must not save before confirmation'),
      onCommit: (_) async => false,
      transcriptionBlockedReason: null,
      declarationsBlocked: true,
      draftController: controller,
    ),
  ),
  size: const Size(800, 1800),
);

Future<void> toggleCorrection(WidgetTester tester) async {
  final header = find
      .descendant(
        of: uiDisclosure('Correct label transcription'),
        matching: find.byWidgetPredicate(
          (widget) =>
              widget is Pressable &&
              widget.semanticsLabel == 'Correct label transcription',
        ),
      )
      .first;
  await tester.ensureVisible(header);
  await tester.tap(header);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets(
    'label correction is supporting and its dirty draft survives collapse',
    (tester) async {
      final controller = LabelDraftController();
      addTearDown(controller.dispose);
      await showReadings(tester, controller);
      expect(uiField('Accepted label text'), findsNothing);
      expect(uiDisclosure('Correct label transcription'), findsOneWidget);
      await toggleCorrection(tester);
      await tester.enterText(uiField('Accepted label text'), 'Chicago 1913');
      await tester.pumpAndSettle();
      await tester.enterText(
        uiField('Reason for correction'),
        'Verified against the photograph',
      );
      await tester.pumpAndSettle();
      expect(controller.hasChanges, isTrue);

      await toggleCorrection(tester);
      expect(uiField('Accepted label text'), findsNothing);
      expect(controller.hasChanges, isTrue);
      await toggleCorrection(tester);
      expect(
        tester.widget<UiField>(uiField('Accepted label text')).controller!.text,
        'Chicago 1913',
      );
      expect(
        tester
            .widget<UiField>(uiField('Reason for correction'))
            .controller!
            .text,
        'Verified against the photograph',
      );
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('using a reading opens a draft and unconfirmed saves keep it', (
    tester,
  ) async {
    final controller = LabelDraftController();
    addTearDown(controller.dispose);
    await showReadings(tester, controller);
    expect(uiField('Accepted label text'), findsNothing);
    await tester.tap(uiButton('Use this text'));
    await tester.pumpAndSettle();
    expect(
      tester.widget<UiField>(uiField('Accepted label text')).controller!.text,
      'Chicago 1917',
    );
    expect(controller.hasChanges, isTrue);
    await tester.enterText(
      uiField('Reason for correction'),
      'Compared the two dates',
    );
    await tester.pumpAndSettle();
    await tester.tap(uiButton('Save label text'));
    await tester.pumpAndSettle();
    expect(
      find.text('Save not confirmed. Your changes are kept.'),
      findsOneWidget,
    );
    expect(controller.hasChanges, isTrue);
    expect(
      tester.widget<UiField>(uiField('Accepted label text')).controller!.text,
      'Chicago 1917',
    );
    expect(tester.takeException(), isNull);
  });
}
