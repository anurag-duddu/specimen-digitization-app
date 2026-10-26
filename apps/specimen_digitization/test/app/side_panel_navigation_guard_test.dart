import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/screens/queue/queue_screen.dart';
import 'package:specimen_digitization/src/screens/workbench/fields_panel.dart';
import 'package:specimen_digitization/src/widgets/queue_row.dart';
import 'package:specimen_digitization/src/workbench.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../golden/golden_harness.dart';
import '../ui_finders.dart';

Finder get _record => find.byType(ReviewWorkbench);
Finder get _fields => find.byType(WorkbenchFields);
Finder get _panel => find.byType(UiSidePanel);

Future<void> _tap(WidgetTester tester, Finder finder) async {
  await tester.ensureVisible(finder);
  await tester.pumpAndSettle();
  await tester.tap(finder);
  await tester.pumpAndSettle();
}

Future<GoldenQueueRepository> _pumpWithPendingCorrection(
  WidgetTester tester,
  double width,
) async {
  final repository = GoldenQueueRepository(goldenQueue(3));
  await pumpGoldenApp(
    tester,
    window: Size(width, 1000),
    brightness: Brightness.light,
    location: goldenSpecimenLocationOf(repository.records.first.id),
    repository: repository,
  );
  expect(tester.widget<UiSidePanel>(_panel).mode, UiSidePanelMode.overlay);
  await _tap(tester, uiRecordView('Structured specimen data'));
  await openFieldEditor(tester, 1);
  await pickUiSelect(tester, 'Evidence state', 'Unreadable');
  await _tap(tester, uiButton('Keep this correction'));
  _expectPendingCorrection(tester);
  expect(repository.lastChange, isNull);
  return repository;
}

void _expectPendingCorrection(WidgetTester tester) {
  final pending = tester.widget<WorkbenchFields>(_fields).pending;
  expect(pending, hasLength(1));
  expect(pending.single.fieldKey, 'collectors');
  expect(pending.single.state, 'unreadable');
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  for (final width in [820.0, 1280.0]) {
    testWidgets(
      'Back at $width closes queue overlay before prompting about a correction',
      (tester) async {
        final repository = await _pumpWithPendingCorrection(tester, width);
        final router = GoRouter.of(tester.element(_record));
        final location = router.routerDelegate.currentConfiguration.uri;
        final recordState = tester.state(_record);
        final fieldsState = tester.state(_fields);
        final opener = uiIconButton('Show queue');
        await _tap(tester, opener);
        expect(tester.widget<UiSidePanel>(_panel).open, isTrue);
        final queueState = tester.state(find.byType(QueuePane));

        unawaited(tester.binding.handlePopRoute());
        await tester.pumpAndSettle();

        expect(tester.widget<UiSidePanel>(_panel).open, isFalse);
        expect(find.text('Discard unsaved corrections?'), findsNothing);
        expect(router.routerDelegate.currentConfiguration.uri, location);
        expect(tester.state(_record), same(recordState));
        expect(tester.state(_fields), same(fieldsState));
        expect(
          tester.state(find.byType(QueuePane, skipOffstage: false)),
          same(queueState),
        );
        expect(tester.widget<UiIconButton>(opener).focusNode!.hasFocus, isTrue);
        _expectPendingCorrection(tester);
        expect(repository.lastChange, isNull);

        // Back reaches the record guard only after the overlay has closed.
        unawaited(tester.binding.handlePopRoute());
        await tester.pumpAndSettle();
        expect(find.text('Discard unsaved corrections?'), findsOneWidget);
        await _tap(tester, uiButton('Keep editing'));
        expect(router.routerDelegate.currentConfiguration.uri, location);
        _expectPendingCorrection(tester);
        expect(repository.lastChange, isNull);
        expect(tester.takeException(), isNull);
      },
    );

    testWidgets(
      'canceling a queue record change at $width keeps the overlay and correction',
      (tester) async {
        final repository = await _pumpWithPendingCorrection(tester, width);
        final router = GoRouter.of(tester.element(_record));
        final location = router.routerDelegate.currentConfiguration.uri;
        final recordState = tester.state(_record);
        final fieldsState = tester.state(_fields);
        await _tap(tester, uiIconButton('Show queue'));
        final queueState = tester.state(find.byType(QueuePane));
        final otherRecord = find.byWidgetPredicate(
          (widget) =>
              widget is QueueRow && widget.id == repository.records[1].id,
        );
        expect(otherRecord.hitTestable(), findsOneWidget);
        await _tap(tester, otherRecord);
        expect(find.text('Discard unsaved corrections?'), findsOneWidget);
        expect(tester.widget<UiSidePanel>(_panel).open, isTrue);
        await _tap(tester, uiButton('Keep editing'));

        expect(find.text('Discard unsaved corrections?'), findsNothing);
        expect(tester.widget<UiSidePanel>(_panel).open, isTrue);
        expect(find.byType(QueuePane).hitTestable(), findsOneWidget);
        expect(tester.state(find.byType(QueuePane)), same(queueState));
        expect(router.routerDelegate.currentConfiguration.uri, location);
        expect(tester.state(_record), same(recordState));
        expect(tester.state(_fields), same(fieldsState));
        _expectPendingCorrection(tester);
        expect(repository.lastChange, isNull);

        await _tap(tester, find.byKey(const ValueKey('queue-panel-close')));
        expect(tester.widget<UiSidePanel>(_panel).open, isFalse);
        _expectPendingCorrection(tester);
        expect(tester.takeException(), isNull);
      },
    );
  }
}
