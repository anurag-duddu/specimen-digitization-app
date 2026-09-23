// The heading over one group within a segment (UI.md T2.2 and T2.3).

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/widgets/widgets.dart';

import 'harness.dart';

/// A heading in a column that stretches its children, as both segments do.
Widget stretched(String text) => SizedBox(
  width: 600,
  child: Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    mainAxisSize: MainAxisSize.min,
    children: <Widget>[GroupHeading(text)],
  ),
);

void main() {
  testWidgets('it is a heading named by its words', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await pumpComponent(tester, stretched('Required fields'));
    expect(
      tester.getSemantics(find.text('Required fields')),
      matchesSemantics(label: 'Required fields', isHeader: true),
    );
    handle.dispose();
  });

  testWidgets('its node is the size of its words, not of the column', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await pumpComponent(tester, stretched('Optional fields'));
    // A node the width of the pane is mostly background, which is what a
    // contrast check samples and what a focus highlight outlines.
    expect(
      tester.getSemantics(find.text('Optional fields')).rect.width,
      lessThan(300),
    );
    handle.dispose();
  });

  testWidgets('it is set without leading above or below its line', (
    WidgetTester tester,
  ) async {
    await pumpComponent(tester, stretched('Label 1'));
    final Text text = tester.widget<Text>(find.text('Label 1'));
    expect(text.textHeightBehavior?.applyHeightToFirstAscent, isFalse);
    expect(text.textHeightBehavior?.applyHeightToLastDescent, isFalse);
  });
}
