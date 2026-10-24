import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import '../../harness/control_contract.dart';

void main() {
  for (final tone in UiBannerTone.values) {
    testWidgets('notice $tone fits 320 at 2x RTL and exposes both commands', (
      tester,
    ) async {
      tester.view.physicalSize = const Size(320, 720);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final calls = <String>[];
      await tester.pumpWidget(
        uiHarness(
          size: const Size(320, 720),
          brightness: Brightness.dark,
          textDirection: TextDirection.rtl,
          textScaler: const TextScaler.linear(2),
          child: SingleChildScrollView(
            child: UiNotice(
              title: 'Record updated',
              description: 'A colleague added source evidence.',
              timestamp: 'A moment ago',
              tone: tone,
              onDismiss: () => calls.add('dismiss'),
              actions: [
                UiButton(label: 'Review', onPressed: () => calls.add('review')),
                UiButton(label: 'Later', onPressed: () => calls.add('later')),
              ],
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      await tester.tap(find.text('Review'));
      await tester.tap(find.text('Later'));
      await tester.tap(find.bySemanticsLabel('Dismiss notification'));
      expect(calls, ['review', 'later', 'dismiss']);
    });
  }
  for (final layout in UiModalLayout.values) {
    testWidgets(
      'rich modal $layout preserves footer and scrolls long content',
      (tester) async {
        tester.view.physicalSize = const Size(320, 640);
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.reset);
        await tester.pumpWidget(
          uiHarness(
            size: const Size(320, 640),
            textScaler: const TextScaler.linear(2),
            textDirection: TextDirection.rtl,
            child: Builder(
              builder: (context) => UiButton(
                label: 'Open',
                onPressed: () => UiModalPanel.show<void>(
                  context: context,
                  semanticsLabel: 'Invite colleagues',
                  builder: (context) => UiModalPanel(
                    title: 'Invite colleagues',
                    description: 'Provide access to your collection.',
                    leading: const UiIcon(UiIcons.reviewer),
                    layout: layout,
                    onDismiss: () => Navigator.pop(context),
                    footer: UiButton(
                      label: 'Done',
                      onPressed: () => Navigator.pop(context),
                    ),
                    child: Column(
                      children: [
                        for (var i = 0; i < 30; i++) Text('Member $i'),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        );
        await tester.tap(find.text('Open'));
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
        final footer = tester.getRect(find.text('Done'));
        await tester.drag(
          find
              .descendant(
                of: find.byType(UiModalPanel),
                matching: find.byType(SingleChildScrollView),
              )
              .first,
          const Offset(0, -500),
        );
        await tester.pumpAndSettle();
        expect(tester.getRect(find.text('Done')), footer);
        await tester.sendKeyEvent(LogicalKeyboardKey.escape);
        await tester.pumpAndSettle();
        expect(find.byType(UiModalPanel), findsNothing);
      },
    );
  }
}
