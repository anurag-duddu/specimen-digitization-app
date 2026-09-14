/// Motion tokens (motion and microinteractions, sections 2.2, 2.3 and 6.2).
///
/// Durations and curves come from Flutter's generated Material 3 token
/// constants, `Durations` and `Easing`. This class names them for product use
/// and folds in the reduced-motion policy, so that no widget in the app types
/// a millisecond literal.
library;

import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';

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
  ///
  /// Two sources, because neither covers our platforms alone on Flutter
  /// 3.38.5: `MediaQueryData.disableAnimations` carries Android's "Remove
  /// animations", and `AccessibilityFeatures.reduceMotion` carries the iOS
  /// setting, which `MediaQuery` omits. The web has no signal at all in this
  /// toolchain, so a web bridge and an in-app override arrive with the motion
  /// step of the redesign.
  static MotionTokens of(BuildContext context) {
    final MotionTokens base =
        Theme.of(context).extension<MotionTokens>() ?? const MotionTokens();
    return base.copyWith(reduced: prefersReducedMotion(context));
  }

  /// True when any source asks for reduced motion.
  static bool prefersReducedMotion(BuildContext context) =>
      MediaQuery.disableAnimationsOf(context) ||
      SemanticsBinding.instance.accessibilityFeatures.reduceMotion;

  @override
  MotionTokens copyWith({bool? reduced}) =>
      MotionTokens(reduced: reduced ?? this.reduced);

  /// Durations are discrete tokens; interpolating them is meaningless.
  @override
  MotionTokens lerp(MotionTokens? other, double t) =>
      t < 0.5 ? this : (other ?? this);
}
