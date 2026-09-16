// UiTextArea (10 section 4.2).
//
// The field's behaviour plus the two things a text area adds: it opens at
// minLines and it grows with the text.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

const String _label = 'Reason for this decision';

void main() {
  testWidgets('it satisfies the control contract', (WidgetTester tester) async {
    await expectControlContract(
      tester,
      (BuildContext context) =>
          const SizedBox(width: 320, child: UiTextArea(label: _label)),
      semanticsLabel: _label,
      activation: ControlActivation.textEditing,
    );
  });

  testWidgets('a disabled text area carries the reason on its hint', (
    WidgetTester tester,
  ) async {
    await expectControlContract(
      tester,
      (BuildContext context) => const SizedBox(
        width: 320,
        child: UiTextArea(
          label: _label,
          enabled: false,
          disabledReason: 'Sign in again before you record a decision.',
        ),
      ),
      semanticsLabel: _label,
      disabledWithReason: true,
    );
  });

  testWidgets('it opens taller than a single line field', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: const SizedBox(
          width: 320,
          child: Column(
            children: <Widget>[
              UiField(label: 'One line'),
              UiTextArea(label: _label),
            ],
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      tester.getSize(find.byType(UiTextArea)).height,
      greaterThan(tester.getSize(find.byType(UiField).at(0)).height),
    );
  });

  testWidgets('it grows with the text and then stops', (
    WidgetTester tester,
  ) async {
    final TextEditingController controller = TextEditingController();
    addTearDown(controller.dispose);
    await tester.pumpWidget(
      uiHarness(
        child: SizedBox(
          width: 320,
          child: UiTextArea(
            label: _label,
            controller: controller,
            minLines: 2,
            maxLines: 3,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    final double opened = tester.getSize(find.byType(UiTextArea)).height;

    await tester.enterText(find.byType(FieldCore), 'one\ntwo\nthree');
    await tester.pumpAndSettle();
    final double grown = tester.getSize(find.byType(UiTextArea)).height;
    expect(grown, greaterThan(opened), reason: 'it auto grows');

    await tester.enterText(
      find.byType(FieldCore),
      'one\ntwo\nthree\nfour\nfive',
    );
    await tester.pumpAndSettle();
    expect(
      tester.getSize(find.byType(UiTextArea)).height,
      grown,
      reason: 'past maxLines it scrolls rather than growing without a limit',
    );
  });

  testWidgets('the counter counts the paragraph', (WidgetTester tester) async {
    await tester.pumpWidget(
      uiHarness(
        child: const SizedBox(
          width: 320,
          child: UiTextArea(label: _label, maxLength: 240),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('0 / 240'), findsOneWidget);
    await tester.enterText(find.byType(FieldCore), 'The label reads 1946.');
    await tester.pumpAndSettle();
    expect(find.text('21 / 240'), findsOneWidget);
  });
}
