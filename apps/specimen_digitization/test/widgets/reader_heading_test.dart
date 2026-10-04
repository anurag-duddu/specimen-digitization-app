import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/screens/workbench/reader_heading.dart';
import 'package:specimen_digitization/src/screens/workbench/reader_identity.dart';

import 'harness.dart';

void main() {
  for (final model in [
    'Qwen/Qwen3-VL-30B-A3B-Instruct',
    'meta-models/Muse-Glimmer-30B',
  ]) {
    testWidgets('$model remains readable at a narrow width and large text', (
      tester,
    ) async {
      tester.platformDispatcher.textScaleFactorTestValue = 2;
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      final observation = <String, dynamic>{'model_id': model};
      await pumpComponent(
        tester,
        Align(
          alignment: Alignment.topLeft,
          child: SizedBox(
            width: 200,
            child: ReaderHeading(
              observation: observation,
              name: readerModelName(observation),
            ),
          ),
        ),
        size: const Size(390, 844),
      );
      await tester.pumpAndSettle();
      expect(find.text(model), findsOneWidget);
      final mark = tester.widget<Image>(find.byType(Image));
      expect(
        (mark.image as AssetImage).assetName,
        readerBrand(observation)!.asset,
      );
      expect(mark.excludeFromSemantics, isTrue);
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('an unfamiliar model has accurate text and no invented mark', (
    tester,
  ) async {
    await pumpComponent(
      tester,
      const ReaderHeading(
        observation: {'model_id': 'unfamiliar/model-v7'},
        name: 'unfamiliar/model-v7',
      ),
    );
    expect(find.text('unfamiliar/model-v7'), findsOneWidget);
    expect(find.byType(Image), findsNothing);
  });
}
