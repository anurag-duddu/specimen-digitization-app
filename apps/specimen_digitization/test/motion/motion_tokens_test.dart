// The motion token layer and its four reduced-motion sources
// (motion and microinteractions, sections 2.2, 2.5, 6.2 and 6.3 B).
//
// The trap this file exists to catch: wrapping a test in
// `MediaQuery(data: MediaQueryData(disableAnimations: true))` does not disable
// framework animations. `AnimationController` reads
// `SemanticsBinding.instance.disableAnimations`, never `MediaQuery`. A
// `MediaQuery` override only reaches widgets that literally call
// `MediaQuery.disableAnimationsOf`, which in this app means `MotionTokens` and
// nothing else. So each source is driven the way production drives it.

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_digitization/src/theme/motion.dart';
import 'package:specimen_digitization/src/theme/motion_preference.dart';

/// Pumps a probe that captures the tokens the tree resolves.
Future<MotionTokens> resolve(
  WidgetTester tester, {
  bool mediaQueryDisablesAnimations = false,
  MotionPreferenceController? preference,
}) async {
  late MotionTokens seen;
  Widget probe = Builder(
    builder: (BuildContext context) {
      seen = MotionTokens.of(context);
      return const SizedBox.shrink();
    },
  );
  if (preference != null) {
    probe = MotionPreference(controller: preference, child: probe);
  }
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light(),
      home: Builder(
        builder: (BuildContext context) => MediaQuery(
          data: MediaQuery.of(
            context,
          ).copyWith(disableAnimations: mediaQueryDisablesAnimations),
          child: probe,
        ),
      ),
    ),
  );
  return seen;
}

void main() {
  group('the tokens are the generated Material 3 constants', () {
    test('durations', () {
      expect(MotionTokens.instantRaw, Duration.zero);
      expect(MotionTokens.quickRaw, Durations.short2);
      expect(MotionTokens.standardRaw, Durations.short4);
      expect(MotionTokens.emphasizedRaw, Durations.medium3);
      expect(MotionTokens.slowRaw, Durations.long2);
    });

    test('no duration exceeds the 500 ms ceiling the blocklist sets', () {
      for (final Duration token in <Duration>[
        MotionTokens.quickRaw,
        MotionTokens.standardRaw,
        MotionTokens.emphasizedRaw,
        MotionTokens.slowRaw,
      ]) {
        expect(token.inMilliseconds, lessThanOrEqualTo(500));
      }
    });

    test('curves', () {
      expect(MotionTokens.standardCurve, Easing.standard);
      expect(MotionTokens.enterCurve, Easing.standardDecelerate);
      expect(MotionTokens.exitCurve, Easing.standardAccelerate);
      // There is no `Easing.emphasized`. The full emphasized curve is a
      // `ThreePointCubic` and only exists on `Curves`. Getting this wrong is
      // the most common way a Flutter M3 motion spec drifts from the tokens.
      expect(MotionTokens.emphasizedCurve, Curves.easeInOutCubicEmphasized);
      expect(MotionTokens.emphasizedCurve, isA<ThreePointCubic>());
      expect(MotionTokens.emphasizedEnterCurve, Easing.emphasizedDecelerate);
      expect(MotionTokens.emphasizedExitCurve, Easing.emphasizedAccelerate);
      expect(MotionTokens.progressCurve, Curves.linear);
    });

    test('reduced motion collapses every decorative duration to zero', () {
      const MotionTokens reduced = MotionTokens(reduced: true);
      expect(reduced.quick, Duration.zero);
      expect(reduced.standard, Duration.zero);
      expect(reduced.emphasized, Duration.zero);
      expect(reduced.slow, Duration.zero);
    });

    test('a duration that carries information keeps it', () {
      const MotionTokens reduced = MotionTokens(reduced: true);
      // A determinate progress bar is the rendering of a number. Removing its
      // motion removes data, so it goes through `meaningful` instead of `d`.
      expect(
        reduced.meaningful(MotionTokens.standardRaw),
        MotionTokens.standardRaw,
      );
    });

    test(
      'durations are discrete, so lerp picks a side rather than blending',
      () {
        const MotionTokens off = MotionTokens();
        const MotionTokens on = MotionTokens(reduced: true);
        expect(off.lerp(on, 0.2).reduced, isFalse);
        expect(off.lerp(on, 0.8).reduced, isTrue);
      },
    );
  });

  group('the four reduced-motion sources', () {
    testWidgets('none of them asks for it', (WidgetTester tester) async {
      final MotionTokens motion = await resolve(tester);
      expect(motion.reduced, isFalse);
      expect(motion.standard, MotionTokens.standardRaw);
    });

    testWidgets('Android: MediaQuery disableAnimations', (
      WidgetTester tester,
    ) async {
      final MotionTokens motion = await resolve(
        tester,
        mediaQueryDisablesAnimations: true,
      );
      expect(motion.reduced, isTrue);
      expect(motion.standard, Duration.zero);
    });

    testWidgets('iOS: AccessibilityFeatures.reduceMotion', (
      WidgetTester tester,
    ) async {
      // The iPad case. `MediaQueryData` carries no field for it, so this test
      // fails against any implementation that reads `MediaQuery` alone, and
      // the iPad is the primary review surface.
      tester.platformDispatcher.accessibilityFeaturesTestValue =
          const FakeAccessibilityFeatures(reduceMotion: true);
      addTearDown(
        tester.platformDispatcher.clearAccessibilityFeaturesTestValue,
      );
      final MotionTokens motion = await resolve(tester);
      expect(MediaQueryData.fromView(tester.view).disableAnimations, isFalse);
      expect(motion.reduced, isTrue);
      expect(motion.emphasized, Duration.zero);
    });

    testWidgets('any platform: the stored in-app preference', (
      WidgetTester tester,
    ) async {
      final MotionPreferenceController preference = MotionPreferenceController(
        store: MemoryMotionPreferenceStore(true),
      );
      addTearDown(preference.dispose);
      await preference.load();
      final MotionTokens motion = await resolve(tester, preference: preference);
      expect(motion.reduced, isTrue);
      expect(motion.quick, Duration.zero);
    });

    testWidgets('the preference is off until the reviewer turns it on', (
      WidgetTester tester,
    ) async {
      final MemoryMotionPreferenceStore store = MemoryMotionPreferenceStore();
      final MotionPreferenceController preference = MotionPreferenceController(
        store: store,
      );
      addTearDown(preference.dispose);
      await preference.load();
      expect(preference.forceReducedMotion, isFalse);

      MotionTokens motion = await resolve(tester, preference: preference);
      expect(motion.reduced, isFalse);

      await preference.set(true);
      // The setting outlives the session, which is the whole point of it.
      expect(store.value, isTrue);
      motion = await resolve(tester, preference: preference);
      expect(motion.reduced, isTrue);
    });

    testWidgets('a tree with no scope simply has no in-app override', (
      WidgetTester tester,
    ) async {
      final MotionTokens motion = await resolve(tester);
      expect(motion.reduced, isFalse);
    });
  });

  group('the haptic budget', () {
    test('the surface is three calls and no more', () {
      // Two approved delight moments plus the selection tick. Anything else
      // is a new row in the catalog, which is a design review.
      expect(SpecimenHaptics.decisionLanded, isA<void Function()>());
      expect(SpecimenHaptics.batchComplete, isA<void Function()>());
      expect(SpecimenHaptics.selectionChanged, isA<void Function()>());
    });

    test('nothing fires off the two platforms that have haptics', () {
      debugDefaultTargetPlatformOverride = TargetPlatform.macOS;
      addTearDown(() => debugDefaultTargetPlatformOverride = null);
      expect(SpecimenHaptics.available, isFalse);
    });

    test('both mobile platforms are covered', () {
      for (final TargetPlatform platform in <TargetPlatform>[
        TargetPlatform.iOS,
        TargetPlatform.android,
      ]) {
        debugDefaultTargetPlatformOverride = platform;
        expect(SpecimenHaptics.available, isTrue, reason: '$platform');
      }
      debugDefaultTargetPlatformOverride = null;
    });
  });
}
