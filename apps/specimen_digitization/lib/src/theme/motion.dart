/// Motion tokens (motion and microinteractions, sections 2.2, 2.3 and 6.2).
///
/// Durations and curves come from Flutter's generated Material 3 token
/// constants, `Durations` and `Easing`. This class names them for product use
/// and folds in the reduced-motion policy, so that no widget in the app types
/// a millisecond literal.
library;

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart';

import 'motion_preference.dart';
import 'reduced_motion_platform.dart';

@immutable
class MotionTokens extends ThemeExtension<MotionTokens> {
  const MotionTokens({this.reduced = false});

  /// True when the platform, or the user, asks for reduced motion. Set by [of].
  final bool reduced;

  // Raw tokens. Widgets do not read these directly; they call [d].

  /// Direct manipulation: pinch, pan, drag, typing, focus rings.
  static const Duration instantRaw = Duration.zero;

  /// State swaps inside one component.
  static const Duration quickRaw = Durations.short2; // 100 ms

  /// The default: content cross-fades, expand and collapse, banner enter.
  static const Duration standardRaw = Durations.short4; // 200 ms

  /// Changes that move attention across a large area.
  static const Duration emphasizedRaw = Durations.medium3; // 350 ms

  /// Reserved, so a future container transform has a token to reach for.
  static const Duration slowRaw = Durations.long2; // 500 ms

  // Curves are compile-time constants and are not affected by [reduced]; a
  // zero-duration animation never samples them.

  /// Default for anything that begins and ends on screen.
  static const Curve standardCurve = Easing.standard; // (0.2, 0, 0, 1)

  /// Something arriving on screen.
  static const Curve enterCurve = Easing.standardDecelerate; // (0, 0, 0, 1)

  /// Something leaving permanently.
  static const Curve exitCurve = Easing.standardAccelerate; // (0.3, 0, 1, 1)

  /// There is no `Easing.emphasized`. The full emphasized curve is a
  /// `ThreePointCubic` and only exists on `Curves`.
  static const Curve emphasizedCurve = Curves.easeInOutCubicEmphasized;

  /// Bottom sheet and dialog enter.
  static const Curve emphasizedEnterCurve = Easing.emphasizedDecelerate;

  /// Bottom sheet and dialog dismiss.
  static const Curve emphasizedExitCurve = Easing.emphasizedAccelerate;

  /// Progress bars only. A progress value must not ease; easing misreports
  /// the rate.
  static const Curve progressCurve = Curves.linear;

  Duration get instant => instantRaw;
  Duration get quick => d(quickRaw);
  Duration get standard => d(standardRaw);
  Duration get emphasized => d(emphasizedRaw);
  Duration get slow => d(slowRaw);

  /// Collapses a decorative duration to zero under reduced motion. Flutter
  /// treats a zero duration as a synchronous jump without starting a ticker.
  Duration d(Duration token) => reduced ? Duration.zero : token;

  /// Motion that carries information, such as a determinate progress bar,
  /// keeps its duration. Call this explicitly so every exception to the
  /// reduced-motion policy is visible in the diff.
  Duration meaningful(Duration token) => token;

  /// Reads the tokens and the live reduced-motion state.
  static MotionTokens of(BuildContext context) {
    final MotionTokens base =
        Theme.of(context).extension<MotionTokens>() ?? const MotionTokens();
    return base.copyWith(reduced: prefersReducedMotion(context));
  }

  /// True when any of the four sources asks for reduced motion.
  ///
  /// Four, because no single one covers our platforms on Flutter 3.38.5
  /// (motion and microinteractions, section 2.5, verified against the
  /// installed SDK):
  ///
  ///   Android -> `MediaQueryData.disableAnimations`, which the engine sets
  ///              from the three animator duration scales.
  ///   iOS     -> `AccessibilityFeatures.reduceMotion`. `MediaQueryData`
  ///              carries no field for it, so an iPad with Reduce Motion on
  ///              reports `disableAnimations` false. The iPad is our primary
  ///              review surface, which is why reading `MediaQuery` alone
  ///              would ship a spec that is broken for the reviewers most
  ///              likely to need it.
  ///   Web     -> our own `matchMedia` bridge. The 3.38.5 web engine reports
  ///              `highContrast` and nothing else.
  ///   Any     -> the stored in-app preference, so a reviewer on a managed
  ///              desktop can force it without an operating system setting.
  static bool prefersReducedMotion(BuildContext context) =>
      MotionPreference.forcedOf(context) ||
      MediaQuery.disableAnimationsOf(context) ||
      SemanticsBinding.instance.accessibilityFeatures.reduceMotion ||
      platformPrefersReducedMotion();

  @override
  MotionTokens copyWith({bool? reduced}) =>
      MotionTokens(reduced: reduced ?? this.reduced);

  /// Durations are discrete tokens; interpolating them is meaningless.
  @override
  MotionTokens lerp(MotionTokens? other, double t) =>
      t < 0.5 ? this : (other ?? this);
}

/// The app's entire haptic surface (motion and microinteractions, 4.7).
///
/// Two delight moments are approved, and only two: the disposition settling
/// after a save the reviewer committed (catalog row 50), and a whole upload
/// batch finishing while the operator is at a copy stand rather than looking
/// at the screen (row 67). The per-item version of row 67 is banned outright,
/// because a two hundred image batch would produce two hundred buzzes, which
/// is noise rather than feedback. The selection tick the catalog attaches to
/// choosing a region and a segment is the only other call, and it is the one
/// Flutter documents as the lightest of the five.
///
/// `HapticFeedback` is already a no-op on web and desktop, but every call is
/// gated here anyway, so the platform rule is a line of code a reviewer can
/// read rather than a property of a plugin.
abstract final class SpecimenHaptics {
  /// True on the two platforms whose system haptics these calls reach.
  static bool get available =>
      !kIsWeb &&
      (defaultTargetPlatform == TargetPlatform.iOS ||
          defaultTargetPlatform == TargetPlatform.android);

  /// Delight moment 1: a decision the reviewer committed has landed.
  ///
  /// The reviewer is looking at the screen, so this is redundancy beside the
  /// chip change and the spoken announcement, never the only channel.
  static void decisionLanded() {
    if (available) unawaited(HapticFeedback.mediumImpact());
  }

  /// Delight moment 2: one upload batch reached its final states.
  ///
  /// Fired once per batch, never once per item.
  static void batchComplete() {
    if (available) unawaited(HapticFeedback.lightImpact());
  }

  /// The selection tick for choosing a region (catalog rows 36 and 37) and
  /// for the segment that changes which panel a reviewer is reading (row 41).
  static void selectionChanged() {
    if (available) unawaited(HapticFeedback.selectionClick());
  }
}
