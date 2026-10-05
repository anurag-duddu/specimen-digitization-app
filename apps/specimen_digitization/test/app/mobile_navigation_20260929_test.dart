import 'dart:async';

import 'package:flutter/cupertino.dart' as cupertino;
import 'package:flutter/material.dart' as material;
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/intake.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/queue/queue_screen.dart';
import 'package:specimen_digitization/src/widgets/queue_row.dart';
import 'package:specimen_digitization/src/workbench.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../golden/golden_harness.dart';
import '../ui_finders.dart';
import '../reading_region_comparison_test.dart' show selectLabel;

Finder _nativeBar(TargetPlatform platform) => platform == TargetPlatform.iOS
    ? find.byType(cupertino.CupertinoTabBar)
    : find.byType(material.NavigationBar);

Finder _tab(TargetPlatform platform, String label) =>
    find.descendant(of: _nativeBar(platform), matching: find.text(label));

Finder get _record => find.byType(ReviewWorkbench);
Finder get _backToSpecimens => uiIconButton('Back to specimens');

class _RecoverableQueueRepository extends GoldenQueueRepository {
  _RecoverableQueueRepository() : super(goldenQueue(3));

  bool fail = false;

  @override
  Future<SpecimenPage> specimenPage(
    CollectionScope scope, {
    Map<String, String> filters = const {},
    String? cursor,
  }) async {
    if (fail) throw StateError('The specimen service is unavailable.');
    return super.specimenPage(scope, filters: filters, cursor: cursor);
  }
}

Future<void> _pump(
  WidgetTester tester,
  TargetPlatform platform, {
  String? location,
  Size size = const Size(390, 844),
  double scale = 1,
  GoldenRepository? repository,
}) async {
  await pumpGoldenApp(
    tester,
    window: size,
    textScale: scale,
    brightness: Brightness.light,
    location: location ?? goldenQueueLocation,
    repository: repository ?? GoldenQueueRepository(goldenQueue(3)),
  );
}

Future<void> _tap(WidgetTester tester, Finder control) async {
  await tester.ensureVisible(control);
  await tester.pumpAndSettle();
  await tester.tap(control);
  await tester.pumpAndSettle();
}

Future<void> _edit(WidgetTester tester, String text) async {
  await selectLabel(tester, 1);
  await openLabelCorrection(tester);
  await tester.ensureVisible(uiField('Accepted label text'));
  await tester.enterText(uiField('Accepted label text'), text);
  await tester.pumpAndSettle();
}

TextEditingController _draft(WidgetTester tester) =>
    tester.widget<UiField>(uiField('Accepted label text')).controller!;

int _selectedTab(WidgetTester tester, TargetPlatform platform) =>
    platform == TargetPlatform.iOS
    ? tester
          .widget<cupertino.CupertinoTabBar>(_nativeBar(platform))
          .currentIndex
    : tester.widget<material.NavigationBar>(_nativeBar(platform)).selectedIndex;

void _expectNoSidebar() {
  expect(find.byKey(const ValueKey('global-rail')), findsNothing);
  expect(find.byKey(const ValueKey('global-sidebar')), findsNothing);
  expect(uiIconButton('Open sidebar'), findsNothing);
  expect(uiIconButton('Close sidebar'), findsNothing);
  expect(
    find.byWidgetPredicate(
      (widget) =>
          widget is ModalBarrier && widget.semanticsLabel == 'Close sidebar',
    ),
    findsNothing,
  );
}

void _testOn(
  TargetPlatform platform,
  String description,
  WidgetTesterCallback body,
) => testWidgets(description, body, variant: TargetPlatformVariant({platform}));

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  for (final platform in [TargetPlatform.iOS, TargetPlatform.android]) {
    _testOn(
      platform,
      '$platform specimen list shows service errors and supports recovery',
      (tester) async {
        final repository = _RecoverableQueueRepository();
        await _pump(tester, platform, repository: repository);
        repository.fail = true;
        await _tap(tester, uiMenuTrigger(RegExp('^Account menu')));
        await _tap(tester, find.text('Refresh collection'));
        final error = find.textContaining('The service could not be reached.');
        expect(error.hitTestable(), findsOneWidget);
        expect(uiButton('Retry').hitTestable(), findsOneWidget);
        expect(_nativeBar(platform), findsOneWidget);
        repository.fail = false;
        await _tap(tester, uiButton('Retry'));
        expect(error, findsNothing);
        expect(find.byType(QueueRow), findsNWidgets(3));

        repository.fail = true;
        await _tap(tester, uiMenuTrigger(RegExp('^Account menu')));
        await _tap(tester, find.text('Refresh collection'));
        expect(error.hitTestable(), findsOneWidget);
        await _tap(tester, uiControl('Dismiss'));
        expect(error, findsNothing);
        repository.fail = false;
        await _tap(tester, uiMenuTrigger(RegExp('^Account menu')));
        await _tap(tester, find.text('Refresh collection'));
        expect(error, findsNothing);
        expect(find.byType(QueueRow), findsNWidgets(3));
        expect(tester.takeException(), isNull);
      },
    );

    _testOn(
      platform,
      '$platform specimen list exposes processing blockers and their details',
      (tester) async {
        final repository = GoldenQueueRepository(goldenQueue(3))
          ..blockers = ['storage_unavailable'];
        await _pump(tester, platform, repository: repository);
        final blocker = find.text('Processing awaits collection setup.');
        expect(blocker.hitTestable(), findsOneWidget);
        await _tap(tester, uiControl('Show who unblocks it'));
        expect(
          find.textContaining('An operator must review the processing setup.'),
          findsOneWidget,
        );
        expect(find.byType(QueueRow), findsNWidgets(3));
        expect(_nativeBar(platform), findsOneWidget);
        expect(tester.takeException(), isNull);
      },
    );

    for (final location in [
      goldenQueueLocation,
      goldenIntakeLocation,
      goldenSpecimenLocation,
    ]) {
      _testOn(platform, '$platform uses native phone tabs on $location', (
        tester,
      ) async {
        await _pump(tester, platform, location: location);
        expect(_nativeBar(platform), findsOneWidget);
        expect(
          platform == TargetPlatform.iOS
              ? find.byType(material.NavigationBar)
              : find.byType(cupertino.CupertinoTabBar),
          findsNothing,
        );
        expect(_tab(platform, 'Specimens').hitTestable(), findsOneWidget);
        expect(_tab(platform, 'Intake').hitTestable(), findsOneWidget);
        expect(
          _selectedTab(tester, platform),
          location == goldenIntakeLocation ? 1 : 0,
        );
        _expectNoSidebar();
        final content = location == goldenQueueLocation
            ? find.byType(QueuePane)
            : location == goldenIntakeLocation
            ? find.byType(IntakeScreen)
            : _record;
        final bounds = tester.getRect(content);
        expect(bounds.left, 0);
        expect(bounds.width, 390);
        expect(
          bounds.bottom,
          lessThanOrEqualTo(tester.getRect(_nativeBar(platform)).top),
        );
        expect(tester.takeException(), isNull);
      });
    }

    _testOn(
      platform,
      '$platform opens a specimen and returns to its full-width list',
      (tester) async {
        await _pump(tester, platform);
        final list = tester.state(find.byType(QueuePane));
        await _tap(
          tester,
          find.byWidgetPredicate(
            (widget) => widget is QueueRow && widget.id == goldenSpecimenId,
          ),
        );
        expect(_record, findsOneWidget);
        expect(_backToSpecimens.hitTestable(), findsOneWidget);
        _expectNoSidebar();
        await _tap(tester, _backToSpecimens);
        expect(_record, findsNothing);
        expect(find.byType(QueuePane), findsOneWidget);
        expect(tester.state(find.byType(QueuePane)), same(list));
        expect(tester.getRect(find.byType(QueuePane)).left, 0);
        expect(tester.getRect(find.byType(QueuePane)).width, 390);
        expect(tester.takeException(), isNull);
      },
    );

    _testOn(
      platform,
      '$platform native tab selection respects the active label draft',
      (tester) async {
        await _pump(tester, platform, location: goldenSpecimenLocation);
        final state = tester.state(_record);
        final router = GoRouter.of(tester.element(_record));
        await _edit(tester, 'Keep this transcription');
        final draft = _draft(tester);
        await _tap(tester, _tab(platform, 'Intake'));
        expect(find.text('Discard unsaved corrections?'), findsOneWidget);
        await _tap(tester, uiButton('Keep editing'));
        expect(tester.state(_record), same(state));
        expect(_draft(tester), same(draft));
        expect(draft.text, 'Keep this transcription');
        expect(_selectedTab(tester, platform), 0);
        expect(
          router.routerDelegate.currentConfiguration.uri.toString(),
          goldenSpecimenLocation,
        );

        await _tap(tester, _tab(platform, 'Intake'));
        await _tap(tester, uiButton('Discard changes').hitTestable());
        expect(find.byType(IntakeScreen), findsOneWidget);
        expect(_record, findsNothing);
        expect(_selectedTab(tester, platform), 1);
        expect(
          router.routerDelegate.currentConfiguration.uri.toString(),
          goldenIntakeLocation,
        );
        _expectNoSidebar();
        expect(tester.takeException(), isNull);
      },
    );

    for (final platformBack in [false, true]) {
      _testOn(
        platform,
        '$platform record Back retains or discards draft, system=$platformBack',
        (tester) async {
          await _pump(tester, platform, location: goldenSpecimenLocation);
          final state = tester.state(_record);
          await _edit(tester, 'Unsaved reading');
          final draft = _draft(tester);
          Future<void> requestBack() async {
            if (platformBack) {
              unawaited(tester.binding.handlePopRoute());
              await tester.pumpAndSettle();
            } else {
              await _tap(tester, _backToSpecimens);
            }
          }

          await requestBack();
          expect(find.text('Discard unsaved corrections?'), findsOneWidget);
          await _tap(tester, uiButton('Keep editing'));
          expect(tester.state(_record), same(state));
          expect(_draft(tester), same(draft));
          expect(draft.text, 'Unsaved reading');
          await requestBack();
          await _tap(tester, uiButton('Discard changes').hitTestable());
          expect(_record, findsNothing);
          expect(find.byType(QueuePane), findsOneWidget);
          expect(_selectedTab(tester, platform), 0);
          _expectNoSidebar();
          expect(tester.takeException(), isNull);
        },
      );
    }

    _testOn(
      platform,
      '$platform native tabs clear safe areas and the keyboard',
      (tester) async {
        tester.view.padding = const FakeViewPadding(top: 44, bottom: 34);
        tester.view.viewPadding = const FakeViewPadding(top: 44, bottom: 34);
        await _pump(tester, platform, location: goldenSpecimenLocation);
        final navLabel = tester.getRect(_tab(platform, 'Intake'));
        expect(navLabel.bottom, lessThanOrEqualTo(844 - 34));
        expect(tester.getRect(_backToSpecimens).top, greaterThanOrEqualTo(44));
        await _edit(tester, 'Continue with keyboard');
        tester.view.viewInsets = const FakeViewPadding(bottom: 300);
        await tester.pumpAndSettle();
        await tester.ensureVisible(uiField('Accepted label text'));
        await tester.pumpAndSettle();
        expect(
          tester.getRect(uiField('Accepted label text')).bottom,
          lessThanOrEqualTo(544),
        );
        if (_nativeBar(platform).evaluate().isNotEmpty) {
          expect(
            tester.getRect(_nativeBar(platform)).bottom,
            lessThanOrEqualTo(544),
          );
        }
        expect(_draft(tester).text, 'Continue with keyboard');
        tester.view.viewInsets = const FakeViewPadding();
        await tester.pumpAndSettle();
        expect(_nativeBar(platform), findsOneWidget);
        expect(tester.takeException(), isNull);
      },
    );

    _testOn(
      platform,
      '$platform 320px at double text keeps native navigation usable',
      (tester) async {
        await _pump(tester, platform, size: const Size(320, 844), scale: 2);
        _expectNoSidebar();
        for (final label in ['Intake', 'Specimens']) {
          final tab = _tab(platform, label);
          expect(tab.hitTestable(), findsOneWidget);
          final bounds = tester.getRect(tab);
          expect(bounds.left, greaterThanOrEqualTo(0));
          expect(bounds.right, lessThanOrEqualTo(320));
          expect(bounds.bottom, lessThanOrEqualTo(844));
          await _tap(tester, tab);
          expect(tester.takeException(), isNull);
        }
        expect(find.byType(QueuePane), findsOneWidget);
        expect(tester.getRect(find.byType(QueuePane)).width, 320);
      },
    );

    _testOn(
      platform,
      '$platform landscape phone keeps native navigation and the draft',
      (tester) async {
        await _pump(tester, platform, location: goldenSpecimenLocation);
        final state = tester.state(_record);
        await _edit(tester, 'Same record through rotation');
        final draft = _draft(tester);
        for (final size in [
          const Size(844, 390),
          const Size(1024, 1366),
          const Size(390, 844),
        ]) {
          tester.view.physicalSize = size;
          await tester.pumpAndSettle();
          expect(tester.state(_record), same(state));
          expect(_draft(tester), same(draft));
          expect(draft.text, 'Same record through rotation');
          if (size.height < 600 || size.width < 768) {
            expect(_nativeBar(platform), findsOneWidget);
            _expectNoSidebar();
            expect(tester.getRect(_record).left, 0);
          } else {
            expect(_nativeBar(platform), findsNothing);
            expect(find.byKey(const ValueKey('global-rail')), findsOneWidget);
          }
          expect(tester.takeException(), isNull, reason: '$size');
        }
      },
    );
  }
}
