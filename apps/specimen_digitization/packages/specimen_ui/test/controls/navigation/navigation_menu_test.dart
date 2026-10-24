import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import '../../harness/control_contract.dart';

const sections = [
  UiNavigationSection(
    label: 'Workspace',
    items: [
      UiNavigationItem(
        id: 'collection',
        label: 'Collections',
        icon: UiIcons.collection,
        children: [
          UiNavigationItem(id: 'records', label: 'Records', badge: '12'),
          UiNavigationItem(
            id: 'restricted',
            label: 'Restricted',
            enabled: false,
            disabledReason: 'Access required',
          ),
          UiNavigationItem(id: 'history', label: 'History'),
        ],
      ),
      UiNavigationItem(id: 'settings', label: 'Settings'),
    ],
  ),
];
void main() {
  for (final direction in TextDirection.values) {
    testWidgets(
      'tree keyboard expands, skips disabled, selects and returns to parent $direction',
      (tester) async {
        var expanded = <String>{};
        String? selected;
        await tester.pumpWidget(
          uiHarness(
            textDirection: direction,
            child: StatefulBuilder(
              builder: (context, setState) => SizedBox(
                width: 300,
                height: 500,
                child: UiNavigationMenu(
                  sections: sections,
                  selectedId: selected,
                  expandedIds: expanded,
                  onSelected: (value) => setState(() => selected = value),
                  onExpandedChanged: (value) =>
                      setState(() => expanded = value),
                ),
              ),
            ),
          ),
        );
        await tester.sendKeyEvent(LogicalKeyboardKey.tab);
        await tester.pumpAndSettle();
        expect(FocusManager.instance.primaryFocus?.debugLabel, 'Collections');
        final forward = direction == TextDirection.ltr
            ? LogicalKeyboardKey.arrowRight
            : LogicalKeyboardKey.arrowLeft;
        final back = direction == TextDirection.ltr
            ? LogicalKeyboardKey.arrowLeft
            : LogicalKeyboardKey.arrowRight;
        await tester.sendKeyEvent(forward);
        await tester.pumpAndSettle();
        expect(expanded, {'collection'});
        expect(find.text('Records'), findsOneWidget);
        await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
        await tester.pumpAndSettle();
        expect(FocusManager.instance.primaryFocus?.debugLabel, 'Records');
        expect(selected, isNull);
        await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
        await tester.pumpAndSettle();
        expect(FocusManager.instance.primaryFocus?.debugLabel, 'History');
        await tester.sendKeyEvent(LogicalKeyboardKey.enter);
        await tester.pumpAndSettle();
        expect(selected, 'history');
        await tester.sendKeyEvent(back);
        await tester.pumpAndSettle();
        expect(FocusManager.instance.primaryFocus?.debugLabel, 'Collections');
        await tester.sendKeyEvent(back);
        await tester.pumpAndSettle();
        expect(expanded, isEmpty);
        expect(find.text('History'), findsNothing);
        await tester.sendKeyEvent(LogicalKeyboardKey.end);
        await tester.pumpAndSettle();
        expect(FocusManager.instance.primaryFocus?.debugLabel, 'Settings');
      },
    );
  }
  testWidgets('menu scrolls every slot into reach in a short, 2x RTL window', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(320, 400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      uiHarness(
        size: const Size(320, 400),
        brightness: Brightness.dark,
        textDirection: TextDirection.rtl,
        textScaler: const TextScaler.linear(2),
        child: SizedBox(
          width: 300,
          height: 350,
          child: UiNavigationMenu(
            sections: sections,
            selectedId: 'records',
            expandedIds: {'collection'},
            onSelected: (_) {},
            onExpandedChanged: (_) {},
            header: const Text('Specimen digitization'),
            leadingRail: const Text('Collections'),
            featured: const Text('Progress and guidance'),
            footer: const Text('Account and help'),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    await tester.drag(
      find.byType(SingleChildScrollView).first,
      const Offset(0, -1400),
    );
    await tester.pumpAndSettle();
    expect(find.text('Account and help').hitTestable(), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
