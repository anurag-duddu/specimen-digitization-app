import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'harness/control_contract.dart';

void main() {
  testWidgets(
    'expanded compact tabs reveal keyboard target when narrow at 2x',
    (tester) async {
      final selected = ValueNotifier<int>(0);
      addTearDown(selected.dispose);
      await tester.pumpWidget(
        uiHarness(
          textScaler: const TextScaler.linear(2),
          textDirection: TextDirection.rtl,
          child: SizedBox(
            width: 320,
            child: UiTabs(
              tabs: [
                for (var i = 0; i < 8; i++)
                  UiTab(label: 'Review category $i', badge: '$i'),
              ],
              selected: selected,
              semanticsLabel: 'Sections',
              size: UiTabsSize.compact,
              expanded: true,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.sendKeyEvent(LogicalKeyboardKey.tab);
      await tester.sendKeyEvent(LogicalKeyboardKey.end);
      await tester.pumpAndSettle();
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pumpAndSettle();
      expect(selected.value, 7);
      final strip = tester.getRect(find.byType(UiTabs));
      final label = tester.getRect(find.text('Review category 7'));
      expect(strip.contains(label.center), isTrue);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('short drawer scrolls each region to real tappable controls', (
    tester,
  ) async {
    final called = <String>[];
    await tester.pumpWidget(
      uiHarness(
        textScaler: const TextScaler.linear(2),
        textDirection: TextDirection.rtl,
        child: SizedBox(
          width: 320,
          height: 280,
          child: UiDrawer(
            title: 'Notification settings',
            description: 'Choose which collection updates you want to receive.',
            header: Column(
              children: [
                const UiSearchField(
                  label: 'Search settings',
                  clearLabel: 'Clear',
                ),
                UiButton(
                  label: 'Reset settings',
                  onPressed: () => called.add('header'),
                ),
              ],
            ),
            footer: UiButtonRow(
              primary: UiButton(
                label: 'Apply locally',
                onPressed: () => called.add('apply'),
              ),
              secondary: UiButton(
                label: 'Cancel',
                onPressed: () => called.add('cancel'),
              ),
            ),
            child: Column(
              children: [
                const SizedBox(height: 400),
                UiButton(
                  label: 'Edit preferences',
                  onPressed: () => called.add('body'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
    for (final label in [
      'Reset settings',
      'Edit preferences',
      'Apply locally',
      'Cancel',
    ]) {
      final target = find.text(label);
      await tester.ensureVisible(target);
      await tester.pumpAndSettle();
      await tester.tap(target);
      await tester.pumpAndSettle();
    }
    expect(called, ['header', 'body', 'apply', 'cancel']);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'expanded compact tabs fill width and preserve disabled RTL navigation',
    (tester) async {
      final selected = ValueNotifier<int>(0);
      addTearDown(selected.dispose);
      const tabs = [
        UiTab(label: 'First'),
        UiTab(label: 'Unavailable', enabled: false),
        UiTab(label: 'Third'),
      ];
      await tester.pumpWidget(
        uiHarness(
          textDirection: TextDirection.rtl,
          child: SizedBox(
            width: 760,
            child: UiTabs(
              tabs: tabs,
              selected: selected,
              semanticsLabel: 'Sections',
              size: UiTabsSize.compact,
              expanded: true,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      final slots = find.descendant(
        of: find.byType(UiTabs),
        matching: find.byWidgetPredicate((w) => w is Pressable),
      );
      expect(slots, findsNWidgets(3));
      for (final slot in slots.evaluate()) {
        final box = slot.renderObject! as RenderBox;
        expect(box.size.width, closeTo(760 / 3, .1));
        expect(box.size.height, greaterThanOrEqualTo(48));
      }
      await tester.sendKeyEvent(LogicalKeyboardKey.tab);
      await tester.pump();
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowLeft);
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pump();
      expect(selected.value, 2);
      expect(tester.takeException(), isNull);
    },
  );
}
