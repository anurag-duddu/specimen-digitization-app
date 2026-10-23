import 'package:flutter/rendering.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

RenderParagraph paragraph(WidgetTester tester, String text) =>
    tester.renderObject<RenderParagraph>(
      find.descendant(of: find.text(text), matching: find.byType(RichText)),
    );

void main() {
  testWidgets('metric titles wrap without losing the distinguishing words', (
    tester,
  ) async {
    const label = 'Evidence collection completeness';
    for (final direction in TextDirection.values) {
      for (final scale in [1.0, 2.0, 4.0]) {
        await tester.pumpWidget(
          uiHarness(
            textDirection: direction,
            textScaler: TextScaler.linear(scale),
            child: const SizedBox(
              width: 240,
              child: UiDataTile(label: label, value: '62'),
            ),
          ),
        );
        await tester.pump();
        expect(paragraph(tester, label).didExceedMaxLines, isFalse);
        expect(
          paragraph(tester, label).size.height,
          greaterThan(paragraph(tester, label).preferredLineHeight),
        );
        expect(tester.takeException(), isNull);
      }
    }
  });

  testWidgets(
    'gauge range words reflow independently of its decorative diameter',
    (tester) async {
      final semantics = tester.ensureSemantics();
      for (final direction in TextDirection.values) {
        for (final scale in [1.0, 2.0, 4.0]) {
          await tester.pumpWidget(
            uiHarness(
              textDirection: direction,
              textScaler: TextScaler.linear(scale),
              child: const SizedBox(
                width: 160,
                child: UiArcIndicator(
                  value: .5,
                  semanticsLabel: 'Coverage',
                  minLabel: 'No evidence',
                  maxLabel: 'Complete evidence',
                ),
              ),
            ),
          );
          await tester.pump();
          for (final text in ['No evidence', 'Complete evidence']) {
            expect(paragraph(tester, text).didExceedMaxLines, isFalse);
            expect(paragraph(tester, text).size.width, lessThanOrEqualTo(160));
          }
          final data = tester
              .getSemantics(find.bySemanticsLabel('Coverage'))
              .getSemanticsData();
          expect(data.value, contains('No evidence'));
          expect(data.value, contains('Complete evidence'));
          expect(tester.takeException(), isNull);
        }
      }
      semantics.dispose();
    },
  );
}
