import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

void main() {
  testWidgets('compact heading command has an unbounded host fallback', (
    tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: UiSectionHeader(
            title: 'Review queue',
            role: UiSectionHeaderRole.page,
            trailingAction: UiIconButton(
              icon: UiIcons.selectAll,
              semanticsLabel: 'Select specimens',
              onPressed: () {},
            ),
          ),
        ),
      ),
    );
    expect(find.text('Review queue'), findsOneWidget);
    expect(find.byType(UiIconButton).hitTestable(), findsOneWidget);
    expect(tester.getSize(find.byType(UiSectionHeader)).width.isFinite, isTrue);
    expect(tester.takeException(), isNull);
  });

  for (final scale in [1.0, 2.0]) {
    for (final direction in TextDirection.values) {
      testWidgets('compact heading command at $scale in $direction', (
        tester,
      ) async {
        var activated = 0;
        await tester.pumpWidget(
          uiHarness(
            textScaler: TextScaler.linear(scale),
            textDirection: direction,
            child: SizedBox(
              width: 272,
              child: UiSectionHeader(
                title: 'Review queue',
                role: UiSectionHeaderRole.page,
                trailingAction: UiIconButton(
                  icon: UiIcons.selectAll,
                  semanticsLabel: 'Select specimens',
                  tooltip: 'Select specimens',
                  onPressed: () => activated++,
                ),
              ),
            ),
          ),
        );
        final header = tester.getRect(find.byType(UiSectionHeader));
        final title = tester.getRect(find.text('Review queue'));
        final command = tester.getRect(find.byType(UiIconButton));
        expect(command.top, header.top);
        expect(command.width, greaterThanOrEqualTo(UiDensity.hitBox));
        expect(command.height, greaterThanOrEqualTo(UiDensity.hitBox));
        expect(title.top, header.top);
        expect(title.left, greaterThanOrEqualTo(header.left));
        expect(title.right, lessThanOrEqualTo(header.right));
        expect(
          direction == TextDirection.ltr
              ? title.right <= command.left
              : command.right <= title.left,
          isTrue,
        );
        await tester.tap(find.byType(UiIconButton));
        expect(activated, 1);
        expect(tester.takeException(), isNull);
      });
    }
  }
}
