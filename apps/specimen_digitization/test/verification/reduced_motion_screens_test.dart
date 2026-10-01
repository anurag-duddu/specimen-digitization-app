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
import 'package:flutter/cupertino.dart' show CupertinoTabBar;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter/semantics.dart';
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
          await tester.tap(find.text('fixture-001'));
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
          await tester.tap(find.text('fixture-001'));
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
          await tester.sendKeyEvent(LogicalKeyboardKey.keyF);
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
          final filter = find.byKey(const ValueKey('queue-filter-deferred'));
          expect(filter.hitTestable(), findsOneWidget);
          await tester.tap(filter);
          await tester.pump();
          await recordTransition(tester, signal, 'status filter change');
          expect(tester.widget<Pressable>(filter).selected, isTrue);
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

      testWidgets('the native navigation destination does not glide', (
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
            final focus = Focus.of(tester.element(target));
            if (signal == 'android') {
              focus.requestFocus();
              await tester.pump();
              expect(focus.hasPrimaryFocus, isTrue);
            }
            final bar = find.byKey(const ValueKey('mobile-navigation'));
            final originalBar = tester.element(bar);
            if (signal == 'android') {
              expect(
                tester.widget<NavigationBar>(bar).animationDuration,
                Duration.zero,
              );
            }
            await tester.tap(target);
            await tester.pump();
            if (signal == 'android') {
              await recordNativeIndicatorOpacity(tester);
            } else {
              await recordTransition(
                tester,
                signal,
                'navigation destination change',
              );
              expect(tester.widget<CupertinoTabBar>(bar).currentIndex, 1);
              expect(
                tester
                    .getSemantics(target)
                    .getSemanticsData()
                    .flagsCollection
                    .isSelected,
                Tristate.isTrue,
              );
            }
            expect(tester.element(bar), same(originalBar));
            expect(
              Focus.of(tester.element(uiDestination('Intake').first)),
              same(focus),
            );
            if (signal == 'android') {
              // The newly activated branch may legitimately take route focus.
              // The existing native button's node remains attached and usable.
              expect(focus.context, isNotNull);
              focus.requestFocus();
              await tester.pump();
              expect(focus.hasPrimaryFocus, isTrue);
            }
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

/// Qualifies the SDK's remaining indicator opacity, not arbitrary tickers.
///
/// Flutter's NavigationIndicator has an independent hardcoded 100 ms fade
/// (material/navigation_bar.dart), compressed to 5% by Android's platform
/// disableAnimations flag. NavigationBar.animationDuration controls its scale
/// and label geometry but not this fade. The product motion guidance explicitly
/// permits native indicator motion (04, row 12) and stationary fades (2.5).
/// This records a <=6 ms sampled opacity residual, never a zero-animation claim.
Future<void> recordNativeIndicatorOpacity(WidgetTester tester) async {
  await flushRoutedFrames(tester);
  final bar = find.byType(NavigationBar);
  final selectedTab = find.descendant(
    of: bar,
    matching: find.byWidgetPredicate(
      (widget) =>
          widget is Semantics &&
          widget.properties.role == SemanticsRole.tab &&
          widget.properties.selected == true,
    ),
  );
  expect(selectedTab, findsOneWidget);
  expect(tester.getSemantics(selectedTab).label, contains('Intake'));
  final indicators = find.descendant(
    of: bar,
    matching: find.byType(NavigationIndicator),
  );
  expect(indicators, findsNWidgets(2));
  final fades = find.descendant(
    of: indicators,
    matching: find.byType(FadeTransition),
  );
  expect(fades, findsNWidgets(2));
  final allowedFades = tester.widgetList<FadeTransition>(fades).toList();
  final allFades = tester.widgetList<FadeTransition>(
    find.byType(FadeTransition),
  );
  for (final fade in allFades) {
    if (!allowedFades.contains(fade)) {
      expect(
        fade.opacity.isAnimating,
        isFalse,
        reason: 'the exception belongs only to the native indicator opacity',
      );
    }
  }
  expect(
    tester
        .widgetList<NavigationIndicator>(indicators)
        .map((indicator) => indicator.animation.value),
    orderedEquals([0.0, 1.0]),
  );
  expect(_travelling(tester).difference({'FadeTransition'}), isEmpty);

  List<Rect> geometry() => [
    for (final label in ['Specimens', 'Intake']) ...[
      tester.getRect(uiDestination(label).first),
      tester.getRect(find.descendant(of: bar, matching: find.text(label))),
    ],
    for (final element in indicators.evaluate())
      tester.getRect(
        find.byElementPredicate((candidate) => identical(candidate, element)),
      ),
  ];
  List<List<double>> transforms() => tester
      .widgetList<Transform>(
        find.descendant(of: bar, matching: find.byType(Transform)),
      )
      .map((transform) => transform.transform.storage.toList())
      .toList();
  void expectOnlyIndicatorTickers() {
    final activeFades = tester
        .widgetList<FadeTransition>(fades)
        .where((fade) => fade.opacity.isAnimating)
        .length;
    expect(
      tester.binding.transientCallbackCount,
      activeFades,
      reason: 'no unrelated ticker may share the native opacity allowance',
    );
  }

  expectOnlyIndicatorTickers();
  final initialGeometry = geometry();
  final initialTransforms = transforms();
  var elapsed = 0;
  while (tester.hasRunningAnimations && elapsed < 6) {
    await tester.pump(const Duration(milliseconds: 1));
    elapsed++;
    expectOnlyIndicatorTickers();
    expect(geometry(), orderedEquals(initialGeometry));
    expect(transforms(), equals(initialTransforms));
  }
  expect(
    tester.hasRunningAnimations,
    isFalse,
    reason: 'only the SDK indicator fade may remain, for at most 6 ms',
  );
  expect(
    tester.widgetList<FadeTransition>(fades).map((fade) => fade.opacity.value),
    orderedEquals([0.0, 1.0]),
  );
  debugPrint(
    'MOTIONROW|android|navigation destination change|'
    'geometry instant; SDK indicator opacity only|residual ${elapsed}ms',
  );
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
