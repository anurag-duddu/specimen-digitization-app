import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

void main() {
  testWidgets(
    'autofill purpose reaches the editor and can be explicitly disabled',
    (WidgetTester tester) async {
      Future<void> pumpField(Iterable<String>? hints) async {
        await tester.pumpWidget(
          uiHarness(
            child: AutofillGroup(
              child: SizedBox(
                width: 320,
                child: UiField(
                  label: 'Work email',
                  autofillHints: hints,
                  keyboardType: TextInputType.emailAddress,
                ),
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();
      }

      await pumpField(const <String>[AutofillHints.email]);
      final EditableText enabled = tester.widget(find.byType(EditableText));
      expect(enabled.autofillHints, <String>[AutofillHints.email]);
      await tester.enterText(find.byType(EditableText), 'staff@example.org');
      expect(enabled.controller.text, 'staff@example.org');

      await pumpField(null);
      final EditableText disabled = tester.widget(find.byType(EditableText));
      expect(disabled.autofillHints, isNull);
      expect(disabled.controller.text, 'staff@example.org');
    },
  );
}
