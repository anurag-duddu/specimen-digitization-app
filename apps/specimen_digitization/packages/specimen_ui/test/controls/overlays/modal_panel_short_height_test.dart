import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import '../../harness/control_contract.dart';

void main() {
  testWidgets(
    'keyboard-constrained modal keeps body, checkbox and footer actions reachable',
    (tester) async {
      tester.view.physicalSize = const Size(320, 600);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final calls = <String>[];
      EdgeInsets? innerInsets;
      final base =
          uiHarness(
                size: const Size(320, 600),
                textScaler: const TextScaler.linear(2),
                textDirection: TextDirection.rtl,
                child: Builder(
                  builder: (context) => UiButton(
                    label: 'Open',
                    onPressed: () => UiModalPanel.show<void>(
                      context: context,
                      semanticsLabel: 'Review settings',
                      builder: (context) {
                        innerInsets = MediaQuery.viewInsetsOf(context);
                        return UiModalPanel(
                          title: 'Review collection settings',
                          description:
                              'Check the details and choose which updates to receive.',
                          onDismiss: () => Navigator.pop(context),
                          footer: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              UiCheckbox(
                                label: 'Remember this collection preference',
                                value: false,
                                onChanged: (_) => calls.add('checkbox'),
                              ),
                              UiButtonRow(
                                primary: UiButton(
                                  label: 'Apply settings',
                                  onPressed: () => calls.add('apply'),
                                ),
                                secondary: UiButton(
                                  label: 'Cancel changes',
                                  onPressed: () => calls.add('cancel'),
                                ),
                              ),
                            ],
                          ),
                          child: Column(
                            children: [
                              const SizedBox(height: 300),
                              UiButton(
                                label: 'Edit details',
                                onPressed: () => calls.add('body'),
                              ),
                            ],
                          ),
                        );
                      },
                    ),
                  ),
                ),
              )
              as MediaQuery;
      await tester.pumpWidget(
        MediaQuery(
          data: base.data.copyWith(
            viewInsets: const EdgeInsets.only(bottom: 320),
          ),
          child: base.child,
        ),
      );
      await tester.tap(find.text('Open'));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(innerInsets, EdgeInsets.zero);
      final panel = tester.getRect(find.byType(UiModalPanel));
      expect(panel.bottom, lessThanOrEqualTo(280));
      final bodyScroller = find
          .descendant(
            of: find.byType(UiModalPanel),
            matching: find.byType(SingleChildScrollView),
          )
          .first;
      expect(tester.getSize(bodyScroller).height, greaterThan(0));
      for (final label in [
        'Edit details',
        'Remember this collection preference',
        'Apply settings',
        'Cancel changes',
      ]) {
        final target = find.text(label);
        await tester.ensureVisible(target);
        await tester.pumpAndSettle();
        expect(tester.getCenter(target).dy, lessThan(280), reason: label);
        await tester.tap(target);
        await tester.pumpAndSettle();
      }
      expect(calls, ['body', 'checkbox', 'apply', 'cancel']);
      final close = find.bySemanticsLabel('Close dialog');
      await tester.ensureVisible(close);
      await tester.pumpAndSettle();
      await tester.tap(close);
      await tester.pumpAndSettle();
      expect(find.byType(UiModalPanel), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'ordinary footer keeps natural height and stays fixed when body scrolls',
    (tester) async {
      await tester.pumpWidget(
        uiHarness(
          child: const SizedBox(
            width: 560,
            height: 600,
            child: UiModalPanel(
              title: 'Review',
              footer: SizedBox(key: ValueKey('footer-content'), height: 48),
              child: SizedBox(height: 1000),
            ),
          ),
        ),
      );
      final footer = find.byKey(const ValueKey('footer-content'));
      final before = tester.getRect(footer);
      final scrolls = find.descendant(
        of: find.byType(UiModalPanel),
        matching: find.byType(SingleChildScrollView),
      );
      final padding = tester.element(footer).ui.space.s4 * 2;
      expect(tester.getSize(scrolls.last).height, 48 + padding);
      await tester.drag(scrolls.first, const Offset(0, -300));
      await tester.pumpAndSettle();
      expect(tester.getRect(footer), before);
      expect(tester.takeException(), isNull);
    },
  );
}
