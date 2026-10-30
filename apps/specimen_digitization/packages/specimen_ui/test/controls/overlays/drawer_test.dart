import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

void main() {
  for (final direction in TextDirection.values) {
    for (final width in [320.0, 768.0, 1180.0]) {
      testWidgets('drawer fits $width and anchors to reading end $direction', (
        tester,
      ) async {
        final size = Size(width, 720);
        tester.view.physicalSize = size;
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.reset);
        String? result;
        await tester.pumpWidget(
          uiHarness(
            size: size,
            textDirection: direction,
            textScaler: const TextScaler.linear(2),
            brightness: Brightness.dark,
            child: Builder(
              builder: (context) => UiButton(
                label: 'Open filters',
                onPressed: () async {
                  result = await UiDrawer.show<String>(
                    context: context,
                    title: 'Filter records',
                    body: (_) => Column(
                      children: [for (var i = 0; i < 40; i++) Text('Field $i')],
                    ),
                    footer: (context) => UiButton(
                      label: 'Apply filters',
                      onPressed: () => Navigator.of(context).pop('applied'),
                    ),
                  );
                },
              ),
            ),
          ),
        );
        await tester.tap(find.text('Open filters'));
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
        final rect = tester.getRect(find.byType(UiDrawer));
        expect(rect.height, size.height);
        expect(rect.width, width < 600 ? width : UiSpace.standard.dialogMax);
        expect(
          direction == TextDirection.rtl ? rect.left : rect.right,
          direction == TextDirection.rtl ? 0 : width,
        );
        final footerBefore = tester.getRect(find.text('Apply filters'));
        await tester.drag(
          find.ancestor(
            of: find.text('Field 0'),
            matching: find.byType(SingleChildScrollView),
          ),
          const Offset(0, -500),
        );
        await tester.pumpAndSettle();
        expect(tester.getRect(find.text('Apply filters')), footerBefore);
        await tester.tap(find.text('Apply filters'));
        await tester.pumpAndSettle();
        expect(result, 'applied');
        expect(find.byType(UiDrawer), findsNothing);
      });
    }
  }

  testWidgets('drawer Escape restores focus to its trigger', (tester) async {
    final focus = FocusNode();
    addTearDown(focus.dispose);
    await tester.pumpWidget(
      uiHarness(
        child: Builder(
          builder: (context) => UiButton(
            label: 'Open panel',
            focusNode: focus,
            onPressed: () => UiDrawer.show<void>(
              context: context,
              title: 'Details',
              body: (_) => const Text('Record details'),
            ),
          ),
        ),
      ),
    );
    focus.requestFocus();
    await tester.pump();
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(find.byType(UiDrawer), findsOneWidget);
    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    await tester.pumpAndSettle();
    expect(find.byType(UiDrawer), findsNothing);
    expect(focus.hasFocus, isTrue);
  });

  testWidgets('nondismissible drawer keeps its host-controlled exit', (
    tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: Builder(
          builder: (context) => UiButton(
            label: 'Open panel',
            onPressed: () => UiDrawer.show<void>(
              context: context,
              title: 'Saving',
              dismissible: false,
              body: (_) => const Text('Changes are being saved'),
              footer: (context) => UiButton(
                label: 'Finish',
                onPressed: () => Navigator.of(context).pop(),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('Open panel'));
    await tester.pumpAndSettle();
    expect(find.bySemanticsLabel('Close panel'), findsNothing);
    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    await tester.pumpAndSettle();
    expect(find.byType(UiDrawer), findsOneWidget);
    await tester.tap(find.text('Finish'));
    await tester.pumpAndSettle();
    expect(find.byType(UiDrawer), findsNothing);
  });
}
