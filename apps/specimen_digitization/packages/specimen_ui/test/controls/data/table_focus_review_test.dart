import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

void main() {
  for (final closeWithButton in [false, true]) {
    testWidgets(
      'pointer table help returns focus to its trigger: close button $closeWithButton',
      (tester) async {
        final previous = FocusNode(debugLabel: 'Previous field');
        addTearDown(previous.dispose);
        await tester.pumpWidget(
          uiHarness(
            child: Column(
              children: [
                UiField(label: 'Previous field', focusNode: previous),
                UiDataTable<String>(
                  label: 'Records',
                  columns: [
                    UiDataColumn(
                      id: 'name',
                      label: 'Name',
                      helpText: 'Original specimen name.',
                      cellBuilder: (_, value) => Text(value),
                    ),
                  ],
                  rows: const [
                    UiDataRow(id: 'one', value: 'Specimen', label: 'Specimen'),
                  ],
                ),
              ],
            ),
          ),
        );
        previous.requestFocus();
        await tester.pumpAndSettle();
        final trigger = find.bySemanticsLabel('About Name');
        await tester.tap(trigger);
        await tester.pumpAndSettle();
        expect(find.text('Close help'), findsOneWidget);
        if (closeWithButton) {
          await tester.tap(find.text('Close help'));
        } else {
          await tester.sendKeyEvent(LogicalKeyboardKey.escape);
        }
        await tester.pumpAndSettle();
        expect(find.text('Close help'), findsNothing);
        expect(
          previous.hasFocus,
          isFalse,
          reason: 'The previously focused field did not open this help pane.',
        );
        final pressable = tester.widget<Pressable>(
          find
              .descendant(
                of: find.byType(UiIconButton),
                matching: find.byType(Pressable),
              )
              .first,
        );
        expect(pressable.focusNode?.hasFocus, isTrue);
        expect(tester.takeException(), isNull);
      },
    );
  }
}
