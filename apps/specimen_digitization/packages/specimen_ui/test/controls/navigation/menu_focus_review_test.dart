import 'package:flutter/services.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

bool _triggerFocused(String label) {
  var found = false;
  FocusManager.instance.primaryFocus?.context?.visitAncestorElements((element) {
    if (element.widget case Pressable(semanticsLabel: final name)) {
      if (name == label) found = true;
    }
    return !found;
  });
  return found;
}

void main() {
  testWidgets(
    'long menu commands retain distinguishing words at 200 percent RTL',
    (tester) async {
      tester.view.physicalSize = const Size(320, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      const label =
          'Export selected collection records with original source photographs';
      var chosen = 0;
      await tester.pumpWidget(
        uiHarness(
          size: const Size(320, 900),
          textScaler: const TextScaler.linear(2),
          textDirection: TextDirection.rtl,
          child: Align(
            alignment: Alignment.topCenter,
            child: UiMenuTrigger(
              semanticsLabel: 'Record commands',
              label: 'Record commands',
              items: [
                UiMenuItem(
                  label: label,
                  icon: UiIcons.record,
                  shortcut: '⌘ E',
                  onSelected: () => chosen++,
                ),
              ],
            ),
          ),
        ),
      );
      await tester.tap(find.text('Record commands'));
      await tester.pumpAndSettle();
      final paragraph = tester.renderObject<RenderParagraph>(
        find.descendant(of: find.text(label), matching: find.byType(RichText)),
      );
      final complete = TextPainter(
        text: paragraph.text,
        textDirection: paragraph.textDirection,
        textScaler: paragraph.textScaler,
      )..layout(maxWidth: paragraph.size.width);
      expect(paragraph.didExceedMaxLines, isFalse);
      expect(
        paragraph.size.height,
        greaterThanOrEqualTo(complete.height - .01),
      );
      complete.dispose();
      await tester.ensureVisible(find.text(label));
      await tester.tap(find.text(label));
      await tester.pumpAndSettle();
      expect(chosen, 1);
      expect(find.text(label), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );
  for (final dismissal in ['select', 'outside', 'keyboard']) {
    testWidgets('menu $dismissal returns to trigger and can reopen', (
      tester,
    ) async {
      var chosen = 0;
      await tester.pumpWidget(
        uiHarness(
          child: Column(
            children: [
              UiMenuTrigger(
                semanticsLabel: 'Commands',
                label: 'Commands',
                items: [
                  UiMenuItem(
                    label: 'Inspect record',
                    onSelected: () => chosen++,
                  ),
                ],
              ),
              const SizedBox(height: 300),
              UiButton(label: 'Outside action', onPressed: () {}),
            ],
          ),
        ),
      );
      if (dismissal == 'keyboard') {
        await tester.sendKeyEvent(LogicalKeyboardKey.tab);
        await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      } else {
        await tester.tap(find.text('Commands'));
      }
      await tester.pumpAndSettle();
      expect(find.text('Inspect record'), findsOneWidget);
      if (dismissal == 'select') {
        await tester.tap(find.text('Inspect record'));
      } else if (dismissal == 'outside') {
        await tester.tap(find.text('Outside action'));
      } else {
        await tester.sendKeyEvent(LogicalKeyboardKey.escape);
      }
      await tester.pumpAndSettle();
      expect(find.text('Inspect record'), findsNothing);
      expect(_triggerFocused('Commands'), isTrue);
      expect(chosen, dismissal == 'select' ? 1 : 0);
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pumpAndSettle();
      expect(find.text('Inspect record'), findsOneWidget);
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    });
  }
  for (final kind in ['marketing', 'enabled', 'disabled', 'empty']) {
    testWidgets('pointer $kind menu takes Escape and restores actual trigger', (
      tester,
    ) async {
      tester.view.physicalSize = const Size(1180, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final previous = FocusNode(debugLabel: 'Unrelated field');
      addTearDown(previous.dispose);
      var parentEscapes = 0;
      await tester.pumpWidget(
        uiHarness(
          size: const Size(1180, 900),
          child: CallbackShortcuts(
            bindings: {
              const SingleActivator(LogicalKeyboardKey.escape): () =>
                  parentEscapes++,
            },
            child: Column(
              children: [
                UiField(label: 'Unrelated field', focusNode: previous),
                if (kind == 'marketing')
                  UiMarketingHeader(
                    identity: const Text('Specimen'),
                    groups: [
                      UiMarketingLinkGroup(
                        title: 'Resources',
                        links: [
                          UiMarketingAction(
                            'Collection guide',
                            onPressed: () {},
                          ),
                        ],
                      ),
                    ],
                  )
                else
                  UiMenuTrigger(
                    semanticsLabel: 'Resources',
                    label: 'Resources',
                    menuLabel: 'Resource commands',
                    items: [
                      if (kind != 'empty')
                        UiMenuItem(
                          label: 'Collection guide',
                          onSelected: kind == 'enabled' ? () {} : null,
                        ),
                    ],
                  ),
              ],
            ),
          ),
        ),
      );
      previous.requestFocus();
      await tester.pumpAndSettle();
      await tester.tap(find.text('Resources'));
      await tester.pumpAndSettle();
      expect(
        kind == 'empty'
            ? find.bySemanticsLabel('Resource commands')
            : find.text('Collection guide'),
        findsOneWidget,
      );
      await tester.sendKeyEvent(LogicalKeyboardKey.escape);
      await tester.pumpAndSettle();
      expect(
        kind == 'empty'
            ? find.bySemanticsLabel('Resource commands')
            : find.text('Collection guide'),
        findsNothing,
      );
      expect(parentEscapes, 0);
      expect(_triggerFocused('Resources'), isTrue);
      await tester.sendKeyEvent(LogicalKeyboardKey.escape);
      expect(parentEscapes, 1);
      expect(tester.takeException(), isNull);
    });
  }
}
