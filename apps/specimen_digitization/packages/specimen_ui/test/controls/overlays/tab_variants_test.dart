import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

void main() {
  for (final axis in Axis.values) {
    for (final variant in UiTabsVariant.values) {
      testWidgets(
        '$axis $variant fits narrow scaled RTL with icons and badges',
        (tester) async {
          tester.view.physicalSize = const Size(320, 640);
          tester.view.devicePixelRatio = 1;
          addTearDown(tester.view.reset);
          final selected = ValueNotifier(0);
          addTearDown(selected.dispose);
          await tester.pumpWidget(
            uiHarness(
              size: const Size(320, 640),
              textDirection: TextDirection.rtl,
              textScaler: const TextScaler.linear(2),
              brightness: Brightness.dark,
              child: SizedBox(
                width: 280,
                height: axis == Axis.vertical ? 240 : null,
                child: UiTabs(
                  axis: axis,
                  variant: variant,
                  selected: selected,
                  semanticsLabel: 'Record panes',
                  tabs: const [
                    UiTab(
                      label: 'Collection overview',
                      icon: UiIcons.record,
                      badge: '24',
                    ),
                    UiTab(
                      label: 'Photographic evidence',
                      icon: UiIcons.search,
                      badge: '8',
                    ),
                    UiTab(label: 'Activity history', icon: UiIcons.history),
                  ],
                ),
              ),
            ),
          );
          await tester.pumpAndSettle();
          expect(tester.takeException(), isNull);
          selected.value = 2;
          await tester.pumpAndSettle();
          expect(tester.takeException(), isNull);
        },
      );
    }
  }

  testWidgets(
    'vertical arrows skip disabled tabs and preserve manual activation',
    (tester) async {
      final selected = ValueNotifier(0);
      addTearDown(selected.dispose);
      final calls = <int>[];
      await tester.pumpWidget(
        uiHarness(
          child: SizedBox(
            width: 260,
            height: 220,
            child: UiTabs(
              axis: Axis.vertical,
              selected: selected,
              semanticsLabel: 'Details',
              onSelected: calls.add,
              tabs: const [
                UiTab(label: 'Overview'),
                UiTab(
                  label: 'Private files',
                  enabled: false,
                  disabledReason: 'Access required',
                ),
                UiTab(label: 'History'),
                UiTab(label: 'Notes'),
              ],
            ),
          ),
        ),
      );
      await tester.sendKeyEvent(LogicalKeyboardKey.tab);
      await tester.pumpAndSettle();
      expect(FocusManager.instance.primaryFocus?.debugLabel, 'Overview');
      calls.clear();
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
      await tester.pumpAndSettle();
      expect(selected.value, 0);
      expect(calls, isEmpty);
      expect(FocusManager.instance.primaryFocus?.debugLabel, 'History');
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pumpAndSettle();
      expect(selected.value, 2);
      expect(calls, [2]);
      await tester.sendKeyEvent(LogicalKeyboardKey.end);
      await tester.pumpAndSettle();
      expect(FocusManager.instance.primaryFocus?.debugLabel, 'Notes');
      await tester.sendKeyEvent(LogicalKeyboardKey.home);
      await tester.pumpAndSettle();
      expect(FocusManager.instance.primaryFocus?.debugLabel, 'Overview');
    },
  );

  testWidgets(
    'tab label includes its badge and cannot activate when disabled',
    (tester) async {
      final selected = ValueNotifier(0);
      addTearDown(selected.dispose);
      final semantics = tester.ensureSemantics();
      try {
        await tester.pumpWidget(
          uiHarness(
            child: UiTabs(
              selected: selected,
              semanticsLabel: 'Pages',
              tabs: const [
                UiTab(label: 'Overview', badge: '12'),
                UiTab(
                  label: 'Export',
                  enabled: false,
                  disabledReason: 'Finish review first',
                ),
              ],
            ),
          ),
        );
        expect(find.bySemanticsLabel('Overview, 12'), findsOneWidget);
        expect(
          tester
              .getSemantics(find.bySemanticsLabel('Export'))
              .getSemanticsData()
              .hint,
          'Finish review first',
        );
        await tester.tap(find.text('Export'));
        await tester.pumpAndSettle();
        expect(selected.value, 0);
      } finally {
        semantics.dispose();
      }
    },
  );
}
