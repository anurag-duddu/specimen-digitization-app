import 'package:flutter/cupertino.dart'
    show cupertinoTextSelectionHandleControls;
import 'package:flutter/material.dart'
    show Theme, materialTextSelectionHandleControls;
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../harness/control_contract.dart';

void main() {
  testWidgets('evidence selection uses platform handles and context menu', (
    tester,
  ) async {
    for (final platform in [
      TargetPlatform.iOS,
      TargetPlatform.android,
      TargetPlatform.macOS,
      TargetPlatform.windows,
    ]) {
      await tester.pumpWidget(
        uiHarness(
          child: Theme(
            data: UiThemeData.light().toThemeData().copyWith(
              platform: platform,
            ),
            child: const UiSelectionArea(
              child: Text('Original specimen label remains selectable.'),
            ),
          ),
        ),
      );
      final region = tester.widget<SelectableRegion>(
        find.byType(SelectableRegion),
      );
      expect(region.contextMenuBuilder, isNotNull);
      expect(region.selectionControls, isNot(same(emptyTextSelectionControls)));
      if (platform == TargetPlatform.iOS) {
        expect(
          region.selectionControls,
          same(cupertinoTextSelectionHandleControls),
        );
      }
      if (platform == TargetPlatform.android) {
        expect(
          region.selectionControls,
          same(materialTextSelectionHandleControls),
        );
      }
      expect(
        find.text('Original specimen label remains selectable.'),
        findsOneWidget,
      );
      expect(tester.takeException(), isNull);
    }
  });
}
