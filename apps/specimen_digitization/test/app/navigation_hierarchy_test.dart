import 'package:flutter/widgets.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/screens/queue/queue_screen.dart';
import 'package:specimen_digitization/src/widgets/queue_row.dart';
import 'package:specimen_digitization/src/workbench.dart';
import 'package:specimen_digitization/src/workspace.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../golden/golden_harness.dart';
import '../ui_finders.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  for (final width in [768.0, 820.0, 1024.0, 1280.0]) {
    testWidgets(
      'queue overlays a $width workspace without squeezing the record',
      (tester) async {
        await pumpGoldenApp(
          tester,
          window: Size(width, 1000),
          brightness: Brightness.light,
          location: goldenSpecimenLocation,
        );
        final panel = find.byType(UiSidePanel);
        expect(tester.widget<UiSidePanel>(panel).mode, UiSidePanelMode.overlay);
        final record = find.byType(ReviewWorkbench);
        final state = tester.state(record);
        final before = tester.getRect(record);
        final opener = uiIconButton('Show queue');
        expect(opener.hitTestable(), findsOneWidget);
        await tester.tap(opener);
        await tester.pumpAndSettle();
        expect(tester.widget<UiSidePanel>(panel).open, isTrue);
        expect(tester.getRect(record), before);
        expect(tester.state(record), same(state));
        expect(find.byType(QueuePane).hitTestable(), findsOneWidget);
        expect(uiDestination('Intake').hitTestable(), findsNothing);
        final queueState = tester.state(find.byType(QueuePane));
        await tester.sendKeyEvent(LogicalKeyboardKey.escape);
        await tester.pumpAndSettle();
        expect(tester.widget<UiSidePanel>(panel).open, isFalse);
        expect(tester.getRect(record), before);
        expect(tester.widget<UiIconButton>(opener).focusNode!.hasFocus, isTrue);
        expect(
          tester.state(find.byType(QueuePane, skipOffstage: false)),
          same(queueState),
        );
        await tester.tap(opener);
        await tester.pumpAndSettle();
        await tester.binding.handlePopRoute();
        await tester.pumpAndSettle();
        expect(tester.widget<UiSidePanel>(panel).open, isFalse);
        expect(tester.state(record), same(state));
        expect(tester.widget<UiIconButton>(opener).focusNode!.hasFocus, isTrue);
        expect(tester.takeException(), isNull);
      },
    );
  }

  testWidgets(
    'desktop navigation leaves the queue central and Intake independent',
    (tester) async {
      await pumpGoldenApp(
        tester,
        window: const Size(1440, 900),
        brightness: Brightness.light,
        location: goldenQueueLocation,
        repository: GoldenQueueRepository(goldenQueue(40)),
      );
      final pane = find.byType(QueuePane);
      final state = tester.state(pane);
      final controller = WorkspaceScope.read(tester.element(pane));
      expect(find.byType(UiSidebar), findsOneWidget);
      expect(find.byType(UiRail), findsNothing);
      for (final label in ['Specimens', 'Intake', 'Account']) {
        expect(
          find.descendant(
            of: find.byType(UiSidebar),
            matching: find.text(label),
          ),
          findsOneWidget,
        );
      }
      expect(uiDestination('Intake'), findsOneWidget);
      expect(
        tester.getSize(pane).width,
        greaterThan(tester.getSize(find.byType(UiSidebar)).width * 2),
      );
      expect(find.text('From specimens to knowledge.'), findsNothing);
      expect(
        find.bySemanticsLabel(RegExp('^Authorized collection,')),
        findsOneWidget,
      );
      final list = find.byKey(const PageStorageKey<String>('queue-list'));
      await tester.drag(list, const Offset(0, -400));
      await tester.pumpAndSettle();
      final offset = controller.queueScroll.offset;
      expect(offset, greaterThan(0));
      await tester.tap(uiDestination('Intake'));
      await tester.pumpAndSettle();
      expect(pane, findsNothing);
      expect(
        tester.state(find.byType(QueuePane, skipOffstage: false)),
        same(state),
      );
      expect(
        find.bySemanticsLabel(RegExp('^Authorized collection,')),
        findsOneWidget,
      );
      await tester.tap(uiDestination('Specimens'));
      await tester.pumpAndSettle();
      expect(tester.state(pane), same(state));
      expect(controller.queueScroll.offset, closeTo(offset, .01));
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'optional record queue preserves the same list through resizing',
    (tester) async {
      await pumpGoldenApp(
        tester,
        window: const Size(1440, 900),
        brightness: Brightness.light,
        location: goldenQueueLocation,
        repository: GoldenQueueRepository(goldenQueue(20)),
      );
      final queue = tester.state(find.byType(QueuePane));
      await tester.tap(find.byType(QueueRow).first);
      await tester.pumpAndSettle();
      final record = tester.state(find.byType(ReviewWorkbench));
      expect(tester.state(find.byType(QueuePane)), same(queue));
      for (final size in [
        const Size(1180, 820),
        const Size(390, 844),
        const Size(1440, 900),
      ]) {
        tester.view.physicalSize = size;
        await tester.pumpAndSettle();
        expect(tester.state(find.byType(ReviewWorkbench)), same(record));
        expect(
          tester.state(find.byType(QueuePane, skipOffstage: false)),
          same(queue),
        );
        if (size.width == 1180) {
          expect(find.byType(QueuePane), findsNothing);
          expect(uiIconButton('Show queue'), findsOneWidget);
        }
        expect(tester.takeException(), isNull, reason: '$size');
      }
    },
  );
}
