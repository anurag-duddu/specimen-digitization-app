import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import '../../harness/control_contract.dart';

const sources = [
  UiImportSource('drive', 'Google Drive', UiIcons.cloudUpload),
  UiImportSource('dropbox', 'Dropbox', UiIcons.cloudUpload),
];

void main() {
  for (final size in [
    const Size(390, 844),
    const Size(1440, 900),
    const Size(600, 260),
  ]) {
    testWidgets('workspace constrains content and restores focus at $size', (
      tester,
    ) async {
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final focus = FocusNode();
      addTearDown(focus.dispose);
      await tester.pumpWidget(
        uiHarness(
          child: Builder(
            builder: (context) => UiButton(
              label: 'Open sources',
              focusNode: focus,
              onPressed: () => showUiImportWorkspace<void>(
                context: context,
                builder: (context) => UiImportWorkspace(
                  sources: sources,
                  source: 'drive',
                  onSourceChanged: (_) {},
                  onClose: () => Navigator.of(context).pop(),
                  child: ListView(
                    children: [for (var i = 0; i < 100; i++) Text('Photo $i')],
                  ),
                ),
              ),
            ),
          ),
        ),
      );
      focus.requestFocus();
      await tester.tap(find.text('Open sources'));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      final rect = tester.getRect(find.byType(UiImportWorkspace));
      expect(
        rect.width,
        lessThanOrEqualTo(UiSpace.standard.importWorkspaceMax),
      );
      expect(rect.height, lessThanOrEqualTo(size.height));
      expect(
        find
            .byWidgetPredicate(
              (w) =>
                  w is UiIconButton &&
                  w.semanticsLabel == 'Close photo sources',
            )
            .hitTestable(),
        findsOneWidget,
      );
      await tester.sendKeyEvent(LogicalKeyboardKey.escape);
      await tester.pumpAndSettle();
      expect(find.byType(UiImportWorkspace), findsNothing);
      expect(focus.hasFocus, isTrue);
    });
  }
}
