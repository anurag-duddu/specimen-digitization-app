import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import '../../harness/control_contract.dart';

void main() {
  testWidgets(
    'crop keyboard moves physical image coordinates in RTL and clamps resizing',
    (tester) async {
      var crop = const Rect.fromLTWH(.1, .1, .5, .5);
      await tester.pumpWidget(
        uiHarness(
          textDirection: TextDirection.rtl,
          child: StatefulBuilder(
            builder: (context, setState) => SingleChildScrollView(
              child: UiCropEditor(
                image: const Text('Image'),
                value: crop,
                onChanged: (value) => setState(() => crop = value),
              ),
            ),
          ),
        ),
      );
      await tester.sendKeyEvent(LogicalKeyboardKey.tab);
      await tester.pumpAndSettle();
      expect(FocusManager.instance.primaryFocus?.debugLabel, 'Crop image');
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
      await tester.pumpAndSettle();
      expect(crop.left, closeTo(.11, .0001));
      await tester.sendKeyDownEvent(LogicalKeyboardKey.shiftLeft);
      for (var i = 0; i < 50; i++) {
        await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
        await tester.pump();
      }
      await tester.sendKeyUpEvent(LogicalKeyboardKey.shiftLeft);
      await tester.pumpAndSettle();
      expect(crop.right, closeTo(1, .0001));
      expect(crop.width, greaterThan(.5));
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets(
    'crop fits 320 at 2x and readonly sliders cannot propose changes',
    (tester) async {
      tester.view.physicalSize = const Size(320, 720);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(
        uiHarness(
          size: const Size(320, 720),
          textScaler: const TextScaler.linear(2),
          brightness: Brightness.dark,
          child: SingleChildScrollView(
            child: UiCropEditor(
              image: const Text('Image'),
              value: const Rect.fromLTWH(.1, .1, .5, .5),
              disabledReason: 'Read only',
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(
        tester
            .widgetList<UiSlider>(find.byType(UiSlider))
            .every((slider) => slider.onChanged == null),
        isTrue,
      );
    },
  );
}
