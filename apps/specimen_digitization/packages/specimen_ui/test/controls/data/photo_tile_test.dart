import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

void main() {
  testWidgets('settled captions can be quiet without hiding photo state', (
    tester,
  ) async {
    final semantics = tester.ensureSemantics();
    for (final included in [true, false]) {
      var opened = false;
      bool? selected;
      await tester.pumpWidget(
        uiHarness(
          child: SizedBox(
            width: 240,
            height: 300,
            child: UiPhotoTile(
              preview: const SizedBox.expand(),
              name: 'Label photo',
              status: 'Saved',
              showStatus: false,
              included: included,
              selected: false,
              onSelected: (value) => selected = value,
              onOpen: () => opened = true,
            ),
          ),
        ),
      );
      expect(find.text('Saved'), findsNothing);
      final status = included ? 'Saved' : 'Excluded from submission';
      expect(
        find.text('Excluded from submission'),
        included ? findsNothing : findsOneWidget,
      );
      final inspect = find.bySemanticsLabel('Review Label photo. $status');
      expect(inspect, findsOneWidget);
      await tester.tap(inspect);
      expect(opened, isTrue);
      expect(selected, isNull);
      await tester.tap(find.byType(UiCheckbox));
      await tester.pump();
      expect(selected, isTrue);
      expect(tester.takeException(), isNull);
    }
    semantics.dispose();
  });
}
