// The reduced-motion pass of the second verification report
// (04 section 2.5; `design/12-verification-report-v2.md`).
//
// `test/motion/reduced_motion_test.dart` holds one test per animated
// component. This file asks the other half of the question: with the
// reviewer's setting on, does every transition a reviewer actually crosses
// collapse, on the routed application rather than on a component pumped bare.
//
// Two signals, because 04 section 2.5 proves they are not one signal. Android
// sets `AccessibilityFeatures.disableAnimations`, which reaches `MediaQuery`
// and which Flutter itself honours by running every default controller at five
// percent of its duration. iOS sets `reduceMotion` only, which reaches
// `MediaQuery` nowhere and which Flutter honours nowhere: on an iPad the
// product's own token layer is the whole of the policy. The iPad is the
// primary review surface, so the iOS column is the one that matters.
//
// The measurement is always the same shape: cross the transition, flush the routed
// application's post-frame updates with no clock advance, and ask whether anything is still moving. A
// transition that went through `MotionTokens.d` is already at its
// destination. One that did not is still travelling, and the residual is
// measured in milliseconds rather than described, so the report can say how
// long a reviewer who asked for no motion still waits.

import 'dart:ui' show Tristate;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/app/help_screen.dart';
import 'package:specimen_digitization/src/app/shell.dart';
import 'package:specimen_digitization/src/screens/queue/workbench_screen.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../golden/golden_harness.dart';
import '../ui_finders.dart';

// All authored transitions collapse. The only measured platform residual is
// Material's indicator opacity, held separately below; there is no ticker or
// transition backlog exemption.

/// The two ways the reviewer's setting reaches Flutter 3.38.5.
const Map<String, FakeAccessibilityFeatures> reducedMotionSignals =
    <String, FakeAccessibilityFeatures>{
      'android': FakeAccessibilityFeatures(disableAnimations: true),
      'ios': FakeAccessibilityFeatures(reduceMotion: true),
    };

/// The platform each signal belongs to, so the page transition under test is
/// the one that platform actually draws.
const Map<String, TargetPlatform> signalPlatforms = <String, TargetPlatform>{
  'android': TargetPlatform.android,
  'ios': TargetPlatform.iOS,
};

/// A phone.
const Size compactWindow = Size(390, 844);

/// The window where the record is a pane beside the list rather than a push.
const Size largeWindow = Size(1440, 900);

/// The longest residual this test will wait out before giving up on a
/// transition. Nothing in the catalog is longer than 500 ms, and a platform
/// page transition on Android is 450.
const Duration residualCeiling = Duration(milliseconds: 1200);

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  reducedMotionSignals.forEach((
    String signal,
    FakeAccessibilityFeatures features,
  ) {
    group('reduced motion, $signal', () {
      /// Runs [body] with the signal on, on the platform that sends it.
      ///
      /// The platform override is put back inside the body rather than in a
      /// tear down, because the binding checks the foundation debug variables
      /// before the tear downs run and reports a changed one as a failure of
      /// the test that set it.
      Future<void> reduced(
        WidgetTester tester,
        Future<void> Function() body,
      ) async {
        tester.platformDispatcher.accessibilityFeaturesTestValue = features;
        addTearDown(
          tester.platformDispatcher.clearAccessibilityFeaturesTestValue,
        );
        debugDefaultTargetPlatformOverride = signalPlatforms[signal];
        try {
          await body();
        } finally {
          debugDefaultTargetPlatformOverride = null;
        }
      }

      testWidgets('the queue is at rest once it has loaded', (
        WidgetTester tester,
      ) async {
        await reduced(tester, () async {
          await pumpGoldenApp(
            tester,
            window: compactWindow,
            brightness: Brightness.light,
            location: goldenQueueLocation,
          );
          await tester.pump();
          await recordTransition(tester, signal, 'queue at rest');
        });
      });

      testWidgets('a record opened from a phone queue arrives whole', (
        WidgetTester tester,
      ) async {
        await reduced(tester, () async {
          await pumpGoldenApp(
            tester,
            window: compactWindow,
            brightness: Brightness.light,
            location: goldenQueueLocation,
            repository: GoldenQueueRepository(goldenQueue(3)),
          );
          await tester.tap(
            find.descendant(
              of: find.byKey(const ValueKey<String>('queue-row-fixture-001')),
              matching: find.byType(UiListRow),
            ),
          );
          await tester.pump();
          await recordTransition(
            tester,
            signal,
            'queue to record, push below large',
          );
          expect(find.byType(WorkbenchScreen), findsOneWidget);
        });
      });

      testWidgets('a record opened beside the list cross-fades in place', (
        WidgetTester tester,
      ) async {
        await reduced(tester, () async {
          await pumpGoldenApp(
            tester,
            window: largeWindow,
            brightness: Brightness.light,
            location: goldenQueueLocation,
            repository: GoldenQueueRepository(goldenQueue(3)),
          );
          await tester.tap(
            find.descendant(
              of: find.byKey(const ValueKey<String>('queue-row-fixture-001')),
              matching: find.byType(UiListRow),
            ),
          );
          await tester.pump();
          await recordTransition(
            tester,
            signal,
            'queue to record, cross-fade at large',
          );
          expect(find.byType(WorkbenchScreen), findsOneWidget);
        });
      });

      testWidgets('the evidence segment changes without a slide', (
        WidgetTester tester,
      ) async {
        await reduced(tester, () async {
          await pumpGoldenApp(
            tester,
            window: largeWindow,
            brightness: Brightness.light,
            location: goldenSpecimenLocation,
          );
          // Specimen data is the default view; R crosses into Labels.
          await tester.sendKeyEvent(LogicalKeyboardKey.keyR);
          await tester.pump();
          await recordTransition(tester, signal, 'record segment change');
          expect(
            find.descendant(
              of: find.byType(AnimatedSwitcher),
              matching: find.byType(SlideTransition),
            ),
            findsNothing,
            reason:
                'under reduced motion a panel change is a cross-fade in '
                'place, never an x-axis slide (04 section 2.5)',
          );
        });
      });

      testWidgets('the status filter changes without travel', (
        WidgetTester tester,
      ) async {
        await reduced(tester, () async {
          await pumpGoldenApp(
            tester,
            window: compactWindow,
            brightness: Brightness.light,
            location: goldenQueueLocation,
          );
          final filter = find.byKey(const ValueKey('queue-view'));
          expect(filter.hitTestable(), findsOneWidget);
          await pickSpecimenQueue(tester, 'Deferred');
          await recordTransition(tester, signal, 'status filter change');
          expect(tester.widget<UiViewTabs<String>>(filter).value, 'deferred');
          final destination = tester.getRect(filter);
          await tester.pump(const Duration(milliseconds: 400));
          expect(
            tester.getRect(filter),
            destination,
            reason: 'selected geometry must already be final at zero time',
          );
        });
      });

      testWidgets('help opens without travel', (WidgetTester tester) async {
        await reduced(tester, () async {
          await pumpGoldenApp(
            tester,
            window: largeWindow,
            brightness: Brightness.light,
            location: goldenQueueLocation,
          );
          await tester.tap(uiMenuTrigger(RegExp('^Account menu')));
          await tester.pumpAndSettle();
          await tester.tap(find.text(AppShell.helpLabel));
          await tester.pump();
          await recordTransition(tester, signal, 'help route enter');
          expect(find.byType(HelpScreen), findsOneWidget);
        });
      });

      testWidgets('the tab bar destination does not cross-fade', (
        WidgetTester tester,
      ) async {
        await reduced(tester, () async {
          await pumpGoldenApp(
            tester,
            window: compactWindow,
            brightness: Brightness.light,
            location: goldenQueueLocation,
          );
          final handle = tester.ensureSemantics();
          try {
            final target = uiDestination('Intake').first;
            // The glyph is inside the cell, which is the focus owner: asking
            // the focus tree from the glyph reaches the cell's own node.
            final glyph = find.byKey(const ValueKey('mobile-nav-intake'));
            final focus = Focus.of(tester.element(glyph));
            focus.requestFocus();
            await tester.pump();
            expect(focus.hasPrimaryFocus, isTrue);
            final bar = find.byKey(const ValueKey('mobile-navigation'));
            final originalBar = tester.element(bar);
            // The same token layer collapses the bar's cross-fade whichever
            // signal the platform sends: the bar is one component, so the
            // Android residual that the stock `NavigationBar` carried (an
            // SDK indicator fade, up to 6 ms) is gone, and so is its row.
            expect(
              tester.element(bar).ui.motion.navigationGlide,
              Duration.zero,
            );
            await tester.tap(target);
            await tester.pump();
            await recordTransition(
              tester,
              signal,
              'navigation destination change',
            );
            expect(tester.widget<UiTabBar>(bar).currentIndex, 1);
            expect(
              tester
                  .getSemantics(target)
                  .getSemanticsData()
                  .flagsCollection
                  .isSelected,
              Tristate.isTrue,
            );
            // Both layers of the glyph are already at their destination.
            final layers = find.descendant(
              of: glyph,
              matching: find.byType(FadeTransition),
            );
            expect(
              tester
                  .widgetList<FadeTransition>(layers)
                  .map((fade) => fade.opacity.value),
              orderedEquals([0.0, 1.0]),
            );
            expect(tester.element(bar), same(originalBar));
            expect(
              Focus.of(
                tester.element(find.byKey(const ValueKey('mobile-nav-intake'))),
              ),
              same(focus),
            );
            // The newly activated branch may legitimately take route focus.
            // The existing cell's node remains attached and usable.
            expect(focus.context, isNotNull);
            focus.requestFocus();
            await tester.pump();
            expect(focus.hasPrimaryFocus, isTrue);
          } finally {
            handle.dispose();
          }
        });
      });
    });
  });
}

/// Measures one authored transition and requires it to collapse at zero time.
///
/// [tester] has already been pumped one frame past the action. A transition
/// that collapsed is at its destination on that frame; one that did not is
/// pumped a millisecond at a time so the residual can be stated as a number
/// rather than as "still moving".
Future<void> recordTransition(
  WidgetTester tester,
  String signal,
  String transition,
) async {
  await flushRoutedFrames(tester);
  final bool moving = tester.hasRunningAnimations;
  final String detail = moving
      ? await _residual(tester)
      : 'no transition part way';
  debugPrint(
    'MOTIONROW|$signal|$transition|${moving ? 'TRAVELS' : 'collapsed'}|$detail',
  );
  expect(
    moving,
    isFalse,
    reason:
        '$signal/$transition was still moving after zero-clock frames. '
        'Authored travel, scale, rotation and clip changes must be instant.',
  );
}

/// Drains route/focus notifications without spending animation time.
Future<void> flushRoutedFrames(WidgetTester tester) async {
  final before = tester.binding.clock.now();
  for (var frame = 0; frame < 8; frame++) {
    await tester.pump();
  }
  expect(tester.binding.clock.now(), before);
}

/// How long the transition still had to run, and what was travelling.
Future<String> _residual(WidgetTester tester) async {
  final Set<String> kinds = _travelling(tester);
  int elapsed = 0;
  while (tester.hasRunningAnimations &&
      elapsed < residualCeiling.inMilliseconds) {
    await tester.pump(const Duration(milliseconds: 1));
    elapsed++;
    kinds.addAll(_travelling(tester));
  }
  final String what = kinds.isEmpty
      ? 'a ticker with no transition'
      : kinds.join(' ');
  return tester.hasRunningAnimations
      ? 'still running past ${residualCeiling.inMilliseconds} ms, $what'
      : 'residual ${elapsed}ms, $what';
}

/// The transitions that are part way through their travel right now.
///
/// A tree is full of transition widgets sitting at either end, so the presence
/// of one says nothing. What says something is a value that is neither its
/// start nor its finish while the reviewer has asked for no motion.
Set<String> _travelling(WidgetTester tester) {
  final Set<String> moving = <String>{};
  for (final SlideTransition slide in tester.widgetList<SlideTransition>(
    find.byType(SlideTransition),
  )) {
    if (slide.position.value != Offset.zero) moving.add('SlideTransition');
  }
  for (final FadeTransition fade in tester.widgetList<FadeTransition>(
    find.byType(FadeTransition),
  )) {
    final double value = fade.opacity.value;
    if (value > 0.001 && value < 0.999) moving.add('FadeTransition');
  }
  for (final ScaleTransition scale in tester.widgetList<ScaleTransition>(
    find.byType(ScaleTransition),
  )) {
    final double value = scale.scale.value;
    if (value > 0.001 && value < 0.999) moving.add('ScaleTransition');
  }
  return moving;
}
