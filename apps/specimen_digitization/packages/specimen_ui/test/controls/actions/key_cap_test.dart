// `UiKeyCap` is a picture of a key. It is never pressed, so like `UiBadge` it
// carries no role and the control contract does not apply; what it owes is the
// monospace role that keeps `I` and `l` apart on a cap one character wide.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

void main() {
  testWidgets('it draws the key it is given', (WidgetTester tester) async {
    await tester.pumpWidget(uiHarness(child: const UiKeyCap(label: 'J')));
    await tester.pumpAndSettle();
    expect(find.text('J'), findsOneWidget);
  });

  testWidgets('it uses the monospace identifier role on paper with a boundary '
      'edge', (WidgetTester tester) async {
    final UiThemeData ui = UiThemeData.light();
    final UiKeyCapStyle style = UiKeyCapStyle.resolve(ui);
    expect(style.label, ui.type.mono.identifier);
    expect(style.background, ui.color.paper);
    expect(style.side.color, ui.color.boundary);
    expect(style.side.width, ui.shape.stroke.boundary);
    expect(
      style.radius,
      ui.shape.inner,
      reason: 'a key cap is a nested element (09 section 5)',
    );
  });

  testWidgets('a one character cap is square', (WidgetTester tester) async {
    await tester.pumpWidget(uiHarness(child: const UiKeyCap(label: 'K')));
    await tester.pumpAndSettle();
    final Size size = tester.getSize(find.byType(UiKeyCap));
    final UiKeyCapStyle style = UiKeyCapStyle.resolve(UiThemeData.light());
    expect(size.height, style.minSize);
    expect(size.width, greaterThanOrEqualTo(style.minSize));
  });

  testWidgets('a longer key name widens the cap rather than clipping it', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(child: const UiKeyCap(label: 'K')));
    await tester.pumpAndSettle();
    final double narrow = tester.getSize(find.byType(UiKeyCap)).width;

    await tester.pumpWidget(uiHarness(child: const UiKeyCap(label: 'Shift')));
    await tester.pumpAndSettle();
    expect(tester.getSize(find.byType(UiKeyCap)).width, greaterThan(narrow));
    expect(tester.takeException(), isNull);
  });

  testWidgets('a printed form that does not say itself aloud gets a spoken '
      'one', (WidgetTester tester) async {
    await tester.pumpWidget(
      uiHarness(child: const UiKeyCap(label: '/', semanticsLabel: 'Slash')),
    );
    await tester.pumpAndSettle();
    expect(find.bySemanticsLabel('Slash'), findsOneWidget);
  });

  testWidgets('it builds right to left and at 200 percent text', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        textDirection: TextDirection.rtl,
        textScaler: const TextScaler.linear(2),
        child: const UiKeyCap(label: 'Esc'),
      ),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(
      tester.getSize(find.byType(UiKeyCap)).height,
      greaterThan(UiKeyCapStyle.resolve(UiThemeData.light()).minSize),
    );
  });

  testWidgets('nothing about it animates, in either motion mode', (
    WidgetTester tester,
  ) async {
    for (final bool reduced in <bool>[false, true]) {
      await tester.pumpWidget(
        uiHarness(
          disableAnimations: reduced,
          child: const UiKeyCap(label: 'Esc'),
        ),
      );
      await tester.pump();
      expect(tester.binding.transientCallbackCount, 0);
    }
  });
}
