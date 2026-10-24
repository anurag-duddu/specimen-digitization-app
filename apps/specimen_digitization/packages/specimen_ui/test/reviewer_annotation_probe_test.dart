import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'harness/control_contract.dart';

void main() {
  testWidgets(
    'annotation pointers and measurement positions fit narrow large RTL',
    (tester) async {
      final semantics = tester.ensureSemantics();
      for (final kind in UiDesignPointerKind.values) {
        await tester.pumpWidget(
          uiHarness(
            textScaler: const TextScaler.linear(2),
            textDirection: TextDirection.rtl,
            child: SizedBox(
              width: 320,
              child: UiDesignPointer(
                kind: kind,
                label: 'Collection reviewer with an extended name',
              ),
            ),
          ),
        );
        expect(
          find.bySemanticsLabel(
            '${kind.name}: Collection reviewer with an extended name',
          ),
          findsOneWidget,
        );
        expect(tester.takeException(), isNull);
      }
      for (final spacer in [false, true]) {
        for (final position in UiMeasurementLabelPosition.values) {
          await tester.pumpWidget(
            uiHarness(
              textScaler: const TextScaler.linear(2),
              textDirection: TextDirection.rtl,
              child: SizedBox(
                width: 320,
                child: UiMeasurement(
                  label: '24 logical pixels',
                  position: position,
                  spacer: spacer,
                  extent: 180,
                ),
              ),
            ),
          );
          expect(
            find.bySemanticsLabel(
              '${spacer ? 'Spacing' : 'Dimension'}: 24 logical pixels',
            ),
            findsOneWidget,
          );
          final text = tester.getRect(find.text('24 logical pixels'));
          final paint = tester.getRect(
            find.descendant(
              of: find.byType(UiMeasurement),
              matching: find.byType(CustomPaint),
            ),
          );
          switch (position) {
            case UiMeasurementLabelPosition.left:
              expect(text.right, lessThanOrEqualTo(paint.left));
            case UiMeasurementLabelPosition.right:
              expect(text.left, greaterThanOrEqualTo(paint.right));
            case UiMeasurementLabelPosition.top:
              expect(text.bottom, lessThanOrEqualTo(paint.top));
            case UiMeasurementLabelPosition.bottom:
              expect(text.top, greaterThanOrEqualTo(paint.bottom));
          }
          expect(tester.takeException(), isNull);
        }
      }
      semantics.dispose();
    },
  );
}
