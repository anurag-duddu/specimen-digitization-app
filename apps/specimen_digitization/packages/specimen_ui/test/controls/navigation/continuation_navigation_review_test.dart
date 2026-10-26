import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

void main() {
  for (final direction in TextDirection.values) {
    testWidgets('arrows leave discoverable disabled rows $direction', (
      tester,
    ) async {
      final selected = <String>[];
      await tester.pumpWidget(
        uiHarness(
          textDirection: direction,
          child: SizedBox(
            width: 300,
            height: 500,
            child: UiNavigationMenu(
              sections: const [
                UiNavigationSection(
                  items: [
                    UiNavigationItem(id: 'previous', label: 'Previous'),
                    UiNavigationItem(
                      id: 'restricted',
                      label: 'Restricted',
                      enabled: false,
                      disabledReason: 'Collection access is required',
                    ),
                    UiNavigationItem(id: 'next', label: 'Next'),
                  ],
                ),
              ],
              selectedId: null,
              expandedIds: const {},
              onSelected: selected.add,
              onExpandedChanged: (_) {},
            ),
          ),
        ),
      );
      await tester.sendKeyEvent(LogicalKeyboardKey.tab);
      await tester.sendKeyEvent(LogicalKeyboardKey.tab);
      await tester.pumpAndSettle();
      expect(FocusManager.instance.primaryFocus?.debugLabel, 'Restricted');
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      expect(selected, isEmpty);
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
      await tester.pumpAndSettle();
      expect(FocusManager.instance.primaryFocus?.debugLabel, 'Next');
      await tester.sendKeyDownEvent(LogicalKeyboardKey.shiftLeft);
      await tester.sendKeyEvent(LogicalKeyboardKey.tab);
      await tester.sendKeyUpEvent(LogicalKeyboardKey.shiftLeft);
      await tester.pumpAndSettle();
      expect(FocusManager.instance.primaryFocus?.debugLabel, 'Restricted');
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowUp);
      await tester.pumpAndSettle();
      expect(FocusManager.instance.primaryFocus?.debugLabel, 'Previous');
    });

    testWidgets(
      'forward arrow stays in expanded group with no enabled children $direction',
      (tester) async {
        await tester.pumpWidget(
          uiHarness(
            textDirection: direction,
            child: SizedBox(
              width: 300,
              height: 500,
              child: UiNavigationMenu(
                sections: const [
                  UiNavigationSection(
                    items: [
                      UiNavigationItem(
                        id: 'group',
                        label: 'Collection',
                        children: [
                          UiNavigationItem(
                            id: 'restricted',
                            label: 'Restricted',
                            enabled: false,
                          ),
                        ],
                      ),
                      UiNavigationItem(id: 'settings', label: 'Settings'),
                    ],
                  ),
                ],
                selectedId: null,
                expandedIds: const {'group'},
                onSelected: (_) {},
                onExpandedChanged: (_) {},
              ),
            ),
          ),
        );
        await tester.sendKeyEvent(LogicalKeyboardKey.tab);
        await tester.pumpAndSettle();
        expect(FocusManager.instance.primaryFocus?.debugLabel, 'Collection');
        await tester.sendKeyEvent(
          direction == TextDirection.ltr
              ? LogicalKeyboardKey.arrowRight
              : LogicalKeyboardKey.arrowLeft,
        );
        await tester.pumpAndSettle();
        expect(FocusManager.instance.primaryFocus?.debugLabel, 'Collection');
        await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
        await tester.pumpAndSettle();
        expect(FocusManager.instance.primaryFocus?.debugLabel, 'Settings');
      },
    );
  }
}
