import 'package:flutter/cupertino.dart' as cupertino;
import 'package:flutter/material.dart' show NavigationBar;
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/app/shell.dart';
import 'package:specimen_digitization/src/region_editor.dart';
import 'package:specimen_digitization/src/screens/queue/queue_screen.dart';
import 'package:specimen_digitization/src/screens/workbench/decision_bar.dart';
import 'package:specimen_digitization/src/widgets/queue_row.dart';
import 'package:specimen_digitization/src/workbench.dart';
import 'package:specimen_digitization/src/workspace.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../golden/golden_harness.dart';
import '../ui_finders.dart';

Finder get _tabs => find.byKey(const ValueKey('mobile-navigation'));
Finder get _record => find.byType(ReviewWorkbench);
Finder get _back => uiIconButton(AppShell.backLabel);

void _expectRecordNavigation() {
  expect(_record, findsOneWidget);
  expect(_tabs, findsNothing);
  expect(find.byType(NavigationBar), findsNothing);
  expect(find.byType(cupertino.CupertinoTabBar), findsNothing);
  expect(find.byKey(const ValueKey('global-rail')), findsNothing);
  expect(_back.hitTestable(), findsOneWidget);
}

Future<void> _tap(WidgetTester tester, Finder target) async {
  await tester.ensureVisible(target);
  await tester.tap(target);
  await tester.pumpAndSettle();
}

void _expectWithinSafeArea(
  WidgetTester tester,
  Finder target,
  Size window,
  EdgeInsets padding,
) {
  final bounds = tester.getRect(target);
  expect(bounds.left, greaterThanOrEqualTo(padding.left), reason: '$target');
  expect(bounds.top, greaterThanOrEqualTo(padding.top), reason: '$target');
  expect(
    bounds.right,
    lessThanOrEqualTo(window.width - padding.right),
    reason: '$target',
  );
  expect(
    bounds.bottom,
    lessThanOrEqualTo(window.height - padding.bottom),
    reason: '$target',
  );
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test(
    'record recognition includes nested paths and ignores query contents',
    () {
      for (final location in [
        goldenSpecimenLocation,
        '$goldenSpecimenLocation?panel=history#label-1',
        '$goldenSpecimenLocation/history',
        '$goldenSpecimenLocation/labels/label-1',
      ]) {
        expect(AppShell.insideRecord(Uri.parse(location)), isTrue);
      }
      for (final location in [
        goldenQueueLocation,
        '$goldenQueueLocation?specimen=fixture-001',
        goldenIntakeLocation,
        goldenSourcesLocation,
        '$goldenQueueLocation?returnTo=$goldenSpecimenLocation',
      ]) {
        expect(AppShell.insideRecord(Uri.parse(location)), isFalse);
      }
    },
  );

  for (final platform in [TargetPlatform.iOS, TargetPlatform.android]) {
    for (final brightness in Brightness.values) {
      testWidgets(
        '$platform $brightness restores tabs and retained list after record Back',
        (tester) async {
          await pumpGoldenApp(
            tester,
            window: const Size(390, 844),
            brightness: brightness,
            location: goldenQueueLocation,
            repository: GoldenQueueRepository(goldenQueue(20)),
          );
          expect(_tabs, findsOneWidget);
          final list = tester.state(find.byType(QueuePane));
          final controller = WorkspaceScope.read(
            tester.element(find.byType(QueuePane)),
          );
          final row = find.byWidgetPredicate(
            (widget) => widget is QueueRow && widget.id == 'fixture-0018',
          );
          await tester.scrollUntilVisible(
            row,
            240,
            scrollable: find
                .descendant(
                  of: find.byType(QueuePane),
                  matching: find.byType(Scrollable),
                )
                .first,
          );
          await tester.ensureVisible(row);
          await tester.pumpAndSettle();
          final offset = controller.queueScroll.offset;
          expect(offset, greaterThan(0));
          await tester.tap(row);
          await tester.pumpAndSettle();
          _expectRecordNavigation();

          final state = tester.state(_record);
          for (final label in [
            'Label review',
            'Review history',
            'Structured specimen data',
          ]) {
            await _tap(tester, uiRecordView(label));
            _expectRecordNavigation();
            expect(tester.state(_record), same(state));
          }

          final semantics = tester.ensureSemantics();
          try {
            await tester.pump();
            expect(find.bySemanticsLabel(AppShell.backLabel), findsOneWidget);
            final target = tester.getSize(_back);
            expect(target.width, greaterThanOrEqualTo(48));
            expect(target.height, greaterThanOrEqualTo(48));
          } finally {
            semantics.dispose();
          }
          await _tap(tester, _back);
          expect(_record, findsNothing);
          expect(_tabs, findsOneWidget);
          expect(tester.state(find.byType(QueuePane)), same(list));
          expect(controller.queueScroll.offset, closeTo(offset, .01));
          expect(
            GoRouter.of(
              tester.element(find.byType(QueuePane)),
            ).routerDelegate.currentConfiguration.uri.path,
            Uri.parse(goldenQueueLocation).path,
          );
          expect(tester.takeException(), isNull);
        },
        variant: TargetPlatformVariant({platform}),
      );

      testWidgets(
        '$platform $brightness deep link hides tabs until keyboard-activated Back',
        (tester) async {
          await pumpGoldenApp(
            tester,
            window: const Size(390, 844),
            brightness: brightness,
            location: '$goldenSpecimenLocation?panel=history#label-1',
          );
          _expectRecordNavigation();
          final previous = FocusManager.instance.highlightStrategy;
          FocusManager.instance.highlightStrategy =
              FocusHighlightStrategy.alwaysTraditional;
          try {
            final focus = Focus.of(
              tester.element(
                find.descendant(of: _back, matching: find.byType(UiIcon)),
              ),
            );
            focus.requestFocus();
            await tester.pumpAndSettle();
            expect(focus.hasPrimaryFocus, isTrue);
            final ring = find.descendant(
              of: _back,
              matching: find.byType(FocusRing),
            );
            expect(tester.widget<FocusRing>(ring).visible, isTrue);
            expect(
              tester
                  .widget<CustomPaint>(
                    find
                        .descendant(
                          of: ring,
                          matching: find.byType(CustomPaint),
                        )
                        .first,
                  )
                  .foregroundPainter,
              isNotNull,
            );
            await tester.sendKeyEvent(LogicalKeyboardKey.enter);
            await tester.pumpAndSettle();
          } finally {
            FocusManager.instance.highlightStrategy = previous;
          }
          expect(_record, findsNothing);
          expect(find.byType(QueuePane), findsOneWidget);
          expect(_tabs, findsOneWidget);
          expect(uiDestination('Intake').hitTestable(), findsOneWidget);
          expect(tester.takeException(), isNull);
        },
        variant: TargetPlatformVariant({platform}),
      );

      testWidgets(
        '$platform $brightness record and region editor clear system regions',
        (tester) async {
          await pumpGoldenApp(
            tester,
            window: const Size(390, 844),
            brightness: brightness,
            location: goldenSpecimenLocation,
            repository: GoldenRepository.verified(),
          );
          final state = tester.state(_record);
          for (final layout in [
            (
              window: const Size(390, 844),
              padding: const EdgeInsets.only(top: 44, bottom: 34),
            ),
            (
              window: const Size(844, 390),
              padding: const EdgeInsets.only(left: 44, right: 24, bottom: 21),
            ),
          ]) {
            tester.view.physicalSize = layout.window;
            final insets = FakeViewPadding(
              left: layout.padding.left,
              top: layout.padding.top,
              right: layout.padding.right,
              bottom: layout.padding.bottom,
            );
            tester.view.padding = insets;
            tester.view.viewPadding = insets;
            await tester.pumpAndSettle();
            _expectRecordNavigation();
            _expectWithinSafeArea(
              tester,
              _record,
              layout.window,
              layout.padding,
            );
            _expectWithinSafeArea(tester, _back, layout.window, layout.padding);
            final decision = find.byType(WorkbenchDecisionBar);
            await tester.ensureVisible(decision);
            await tester.pumpAndSettle();
            _expectWithinSafeArea(
              tester,
              decision,
              layout.window,
              layout.padding,
            );

            // Open the actual product editor through its record overflow menu.
            final overflow = uiMenuTrigger(UiTopBarStyle.overflowLabel);
            await _tap(tester, overflow);
            await _tap(tester, find.text(regionEditorTitle));
            expect(find.byType(RegionEditorBody), findsOneWidget);
            expect(_tabs, findsNothing);
            expect(find.byKey(const ValueKey('global-rail')), findsNothing);
            if (layout.window.width < 840) {
              final close = uiIconButton(closeEditorLabel);
              _expectWithinSafeArea(
                tester,
                close,
                layout.window,
                layout.padding,
              );
              await _tap(tester, close);
            } else {
              await _tap(tester, uiButton('Cancel'));
            }
            expect(find.byType(RegionEditorBody), findsNothing);
            expect(tester.state(_record), same(state));
            expect(_tabs, findsNothing);
            await tester.ensureVisible(_back);
            await tester.pumpAndSettle();
            _expectWithinSafeArea(tester, _back, layout.window, layout.padding);
            expect(tester.takeException(), isNull);
          }
          await _tap(tester, _back);
          expect(find.byType(QueuePane), findsOneWidget);
          expect(_tabs, findsOneWidget);
          expect(tester.takeException(), isNull);
        },
        variant: TargetPlatformVariant({platform}),
      );
    }
  }

  for (final scale in [1.0, 2.0]) {
    testWidgets('record resizing preserves navigation at scale $scale', (
      tester,
    ) async {
      await pumpGoldenApp(
        tester,
        window: const Size(390, 844),
        brightness: Brightness.dark,
        textScale: scale,
        location: goldenSpecimenLocation,
      );
      final state = tester.state(_record);
      final widthBoundary = 768 * scale;
      for (final size in [
        Size(widthBoundary - 1, 1000),
        Size(widthBoundary, 1000),
        Size(widthBoundary + 100, 599),
        Size(widthBoundary + 100, 600),
        const Size(390, 844),
      ]) {
        tester.view.physicalSize = size;
        await tester.pumpAndSettle();
        final mobile = size.width < widthBoundary || size.height < 600;
        expect(_record, findsOneWidget);
        expect(tester.state(_record), same(state));
        expect(_tabs, findsNothing);
        expect(
          find.byKey(const ValueKey('global-rail')),
          mobile ? findsNothing : findsOneWidget,
        );
        if (!mobile) {
          expect(uiDestination('Specimens').hitTestable(), findsOneWidget);
          expect(uiDestination('Intake').hitTestable(), findsOneWidget);
        }
        expect(tester.takeException(), isNull, reason: '$size at $scale');
      }
      await _tap(tester, _back);
      expect(_tabs, findsOneWidget);
      expect(find.byType(QueuePane), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  }
}
