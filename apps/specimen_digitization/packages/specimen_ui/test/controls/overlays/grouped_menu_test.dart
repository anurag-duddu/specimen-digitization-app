import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import '../../harness/control_contract.dart';

void main() {
  testWidgets(
    'grouped chooser keeps headings out of keyboard traversal and marks one current choice',
    (tester) async {
      var chosen = '';
      await tester.pumpWidget(
        uiHarness(
          child: UiMenuTrigger(
            label: 'Insects',
            icon: UiIcons.expand,
            trailingIcon: true,
            semanticsLabel: 'Collection chooser',
            menuDescription: 'Only enabled collections can be opened.',
            items: [
              UiMenuItem(
                label: 'Insects',
                groupLabel: 'Zoology',
                selected: true,
                onSelected: () => chosen = 'insects',
              ),
              const UiMenuItem(
                label: 'Mammals',
                selected: false,
                disabledReason: 'Not enabled for this account',
                onSelected: null,
              ),
              UiMenuItem(
                label: 'Intake example',
                groupLabel: 'Testing',
                selected: false,
                onSelected: () => chosen = 'testing',
              ),
            ],
          ),
        ),
      );
      await tester.tap(find.bySemanticsLabel('Collection chooser'));
      await tester.pumpAndSettle();
      expect(
        tester.getSemantics(find.text('Zoology')).flagsCollection.isHeader,
        isTrue,
      );
      expect(
        tester
            .getSemantics(find.bySemanticsLabel('Insects').last)
            .flagsCollection
            .isSelected
            .toBoolOrNull(),
        isTrue,
      );
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pumpAndSettle();
      expect(chosen, 'testing');
      expect(find.text('Zoology'), findsNothing);
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pumpAndSettle();
      expect(find.text('Zoology'), findsOneWidget);
    },
  );
  testWidgets('ordinary commands do not acquire selectable semantics', (
    tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: UiMenuTrigger(
          semanticsLabel: 'Actions',
          items: [UiMenuItem(label: 'Copy', onSelected: () {})],
        ),
      ),
    );
    await tester.tap(find.bySemanticsLabel('Actions'));
    await tester.pumpAndSettle();
    expect(
      tester
          .getSemantics(find.bySemanticsLabel('Copy'))
          .flagsCollection
          .isSelected
          .toBoolOrNull(),
      isNull,
    );
  });
}
