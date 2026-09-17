/// Motion tokens and the reduced-motion policy (04 sections 2.2, 2.3, 2.5 and
/// 6.2; 09 section 8).
///
/// Carried from the application's `lib/src/theme/motion.dart` with its
/// behaviour intact, plus the three signature motions this direction adds.
///
/// One difference from 04 section 2.1, which asks for Flutter's generated
/// `Durations` and `Easing` constants: both live in `package:flutter/material.dart`
/// and nothing in `foundation/` may import it (10 section 8, gate `layering`).
/// The values are therefore written here, in the one file in the product
/// allowed to hold a duration literal, and `test/foundation/motion_test.dart`
/// imports Material and asserts every token still equals its Material
/// constant. The pin is a test rather than a reference, and it fails loudly if
/// the Material token database ever moves.
library;

import 'package:flutter/semantics.dart';
import 'package:flutter/widgets.dart';

import 'reduced_motion_platform.dart';

/// Durations and curves, with the live reduced-motion state folded in.
@immutable
class MotionTokens {
  /// Builds the tokens. [reduced] is normally set by [of].
  const MotionTokens({this.reduced = false});

  /// True when the platform, or the reviewer, asks for reduced motion.
  final bool reduced;

  // Raw tokens. Widgets do not read these directly; they call [d].

  /// Direct manipulation: pinch, pan, drag, typing, focus rings.
  static const Duration instantRaw = Duration.zero;

  /// State swaps inside one component. `Durations.short2`.
  static const Duration quickRaw = Duration(milliseconds: 100);

  /// The capsule fill and the numeral tick (09 section 8). `Durations.short3`.
  static const Duration shortRaw = Duration(milliseconds: 150);

  /// The default: content cross-fades, expand and collapse, banner enter.
  /// `Durations.short4`.
  static const Duration standardRaw = Duration(milliseconds: 200);

  /// The navigation glide (09 section 8). `Durations.medium1`.
  static const Duration mediumRaw = Duration(milliseconds: 250);

  /// Changes that move attention across a large area. `Durations.medium3`.
  static const Duration emphasizedRaw = Duration(milliseconds: 350);

  /// Reserved, so a future container transform has a token to reach for.
  /// `Durations.long2`.
  static const Duration slowRaw = Duration(milliseconds: 500);

  /// The state layer's fade in (10 section 2 clause 6).
  static const Duration pressInRaw = Duration(milliseconds: 60);

  /// The state layer's fade out. Longer than [pressInRaw]: a press that has
  /// ended should not snap.
  static const Duration pressOutRaw = Duration(milliseconds: 120);

  // Curves are compile-time constants and are not affected by [reduced]; a
  // zero-duration animation never samples them.

  /// Default for anything that begins and ends on screen. `Easing.standard`.
  static const Curve standardCurve = Cubic(0.2, 0, 0, 1);

  /// Something arriving on screen. `Easing.standardDecelerate`.
  static const Curve enterCurve = Cubic(0, 0, 0, 1);

  /// Something leaving permanently. `Easing.standardAccelerate`.
  static const Curve exitCurve = Cubic(0.3, 0, 1, 1);

  /// There is no `Easing.emphasized`. The full emphasized curve is a
  /// `ThreePointCubic` and exists only on `Curves`.
  static const Curve emphasizedCurve = Curves.easeInOutCubicEmphasized;

  /// Sheet and dialog enter. `Easing.emphasizedDecelerate`.
  static const Curve emphasizedEnterCurve = Cubic(0.05, 0.7, 0.1, 1);

  /// Sheet and dialog dismiss. `Easing.emphasizedAccelerate`.
  static const Curve emphasizedExitCurve = Cubic(0.3, 0, 0.8, 0.15);

  /// Progress bars only. A progress value must not ease; easing misreports
  /// the rate.
  static const Curve progressCurve = Curves.linear;

  /// Zero. Direct manipulation never animates.
  Duration get instant => instantRaw;

  /// 100 ms, or zero under reduced motion.
  Duration get quick => d(quickRaw);

  /// 150 ms, or zero under reduced motion.
  Duration get short => d(shortRaw);

  /// 200 ms, or zero under reduced motion.
  Duration get standard => d(standardRaw);

  /// 250 ms, or zero under reduced motion.
  Duration get medium => d(mediumRaw);

  /// 350 ms, or zero under reduced motion.
  Duration get emphasized => d(emphasizedRaw);

  /// 500 ms, or zero under reduced motion.
  Duration get slow => d(slowRaw);

  /// The state layer fading in. Not collapsed: it is 60 ms and it is the
  /// feedback that a press registered.
  Duration get pressIn => d(pressInRaw);

  /// The state layer fading out.
  Duration get pressOut => d(pressOutRaw);

  /// Signature motion 1: the ink disc slides between navigation destinations.
  /// Under reduced motion the disc appears at the new position.
  Duration get navigationGlide => d(mediumRaw);

  /// Signature motion 2: a capsule toggle fills from its centre, the check
  /// fading in after 40 percent. Under reduced motion both appear together.
  Duration get capsuleFill => d(shortRaw);

  /// Signature motion 3: a numeral cross-fades and slides 6 dp upward on
  /// change. Under reduced motion it cross-fades only.
  Duration get numeralTick => d(shortRaw);

  /// How far a numeral travels on a tick, and the only distance this
  /// signature carries.
  static const double numeralTickRise = 6;

  /// The fraction of [capsuleFill] that passes before the check fades in.
  static const double capsuleCheckDelayFraction = 0.4;

  /// How long a pointer rests on a control before its tooltip shows. An
  /// interaction delay, not a transition, so [reduced] leaves it alone.
  static const Duration tooltipHoverDelay = Duration(milliseconds: 400);

  /// How long a tooltip revealed by a long press stays on screen. Touch has
  /// no pointer to leave, so the reveal is a window rather than a state.
  static const Duration tooltipTouchWindow = Duration(milliseconds: 1500);

  /// How long a toast stays before it leaves on its own.
  static const Duration toastDuration = Duration(seconds: 6);

  /// A sheet enters rising this fraction of its height (04 section 5.3).
  static const double sheetEntranceRise = 0.08;

  /// A dialog enters rising this fraction of its height (04 section 5.3).
  static const double dialogEntranceRise = 0.02;

  /// Collapses a decorative duration to zero under reduced motion. Flutter
  /// treats a zero duration as a synchronous jump without starting a ticker.
  Duration d(Duration token) => reduced ? Duration.zero : token;

  /// Motion that carries information, such as a determinate progress bar,
  /// keeps its duration. Call this explicitly so every exception to the
  /// reduced-motion policy is visible in the diff.
  Duration meaningful(Duration token) => token;

  /// The tokens, with the live reduced-motion state folded in.
  static MotionTokens of(BuildContext context) =>
      MotionTokens(reduced: prefersReducedMotion(context));

  /// True when any of the four sources asks for reduced motion.
  ///
  /// Four, because no single one covers our platforms on Flutter 3.38.5
  /// (04 section 2.5, verified against the installed SDK):
  ///
  ///   Android -> `MediaQueryData.disableAnimations`, which the engine sets
  ///              from the three animator duration scales.
  ///   iOS     -> `AccessibilityFeatures.reduceMotion`. `MediaQueryData`
  ///              carries no field for it, so an iPad with Reduce Motion on
  ///              reports `disableAnimations` false. The iPad is the primary
  ///              review surface, which is why reading `MediaQuery` alone
  ///              would ship a spec that is broken for the reviewers most
  ///              likely to need it.
  ///   Web     -> the `matchMedia` bridge in `reduced_motion_platform.dart`.
  ///              The 3.38.5 web engine reports `highContrast` and nothing
  ///              else.
  ///   Any     -> the stored in-app preference, so a reviewer on a managed
  ///              desktop can force it without an operating system setting.
  static bool prefersReducedMotion(BuildContext context) =>
      MotionPreference.forcedOf(context) ||
      MediaQuery.disableAnimationsOf(context) ||
      SemanticsBinding.instance.accessibilityFeatures.reduceMotion ||
      platformPrefersReducedMotion();

  /// A copy with [reduced] replaced.
  MotionTokens copyWith({bool? reduced}) =>
      MotionTokens(reduced: reduced ?? this.reduced);

  /// Durations are discrete tokens; interpolating them is meaningless.
  MotionTokens lerp(MotionTokens? other, double t) =>
      t < 0.5 ? this : (other ?? this);
}

/// Where the stored "Reduce motion" setting lives.
///
/// Injected, so a test and the local fixture build run without touching a
/// platform store. The application supplies the `shared_preferences` backed
/// implementation; this package holds no storage dependency of its own.
abstract interface class MotionPreferenceStore {
  /// The stored preference, or null when the reviewer has not set one.
  Future<bool?> read();

  /// Stores [value].
  Future<void> write(bool value);
}

/// An in-memory store, for tests and for the local fixture build.
class MemoryMotionPreferenceStore implements MotionPreferenceStore {
  /// Starts with [value], which may be null for "not set".
  MemoryMotionPreferenceStore([this.value]);

  /// The stored value.
  bool? value;

  @override
  Future<bool?> read() async => value;

  @override
  Future<void> write(bool input) async => value = input;
}

/// The live preference, as a listenable.
class MotionPreferenceController extends ChangeNotifier {
  /// Reads and writes through [store], starting at [initial].
  MotionPreferenceController({
    MotionPreferenceStore store = const _NullMotionPreferenceStore(),
    bool initial = false,
  }) : _store = store,
       _forced = initial;

  final MotionPreferenceStore _store;
  bool _forced;

  /// True when the reviewer has asked for reduced motion inside the app.
  bool get forceReducedMotion => _forced;

  /// Loads the stored value. Safe to call more than once.
  Future<void> load() async {
    final bool? stored = await _store.read();
    if (stored != null && stored != _forced) {
      _forced = stored;
      notifyListeners();
    }
  }

  /// Sets the preference and stores it.
  Future<void> set(bool value) async {
    if (value == _forced) return;
    _forced = value;
    notifyListeners();
    await _store.write(value);
  }
}

/// The store a controller gets when the caller supplies none: the setting
/// applies to the session and does not survive a restart.
class _NullMotionPreferenceStore implements MotionPreferenceStore {
  const _NullMotionPreferenceStore();

  @override
  Future<bool?> read() async => null;

  @override
  Future<void> write(bool value) async {}
}

/// Carries the preference down the tree.
///
/// [MotionTokens.prefersReducedMotion] reads this, so every widget that asks
/// for a duration rebuilds when the reviewer changes the setting.
class MotionPreference extends InheritedNotifier<MotionPreferenceController> {
  /// Publishes [controller] to [child].
  const MotionPreference({
    super.key,
    required MotionPreferenceController controller,
    required super.child,
  }) : super(notifier: controller);

  /// The controller above [context], or null where no scope was installed.
  ///
  /// A component test pumps a bare application, so the absence of a scope is
  /// normal and means "no in-app override", never an error.
  static MotionPreferenceController? maybeOf(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<MotionPreference>()?.notifier;

  /// True when the reviewer asked for reduced motion inside the app.
  static bool forcedOf(BuildContext context) =>
      maybeOf(context)?.forceReducedMotion ?? false;
}

/// Keeps the application rebuilding when a reduced-motion source changes.
///
/// `AccessibilityFeatures` is not an inherited widget, so an iPad reviewer
/// turning Reduce Motion on mid-session would otherwise change nothing until
/// the next unrelated rebuild. The web bridge has the same problem, and the
/// browser reports its change through an event listener rather than through
/// the framework at all.
class MotionScope extends StatefulWidget {
  /// Wraps [child] in the scope that carries [controller].
  const MotionScope({super.key, required this.controller, required this.child});

  /// The in-app preference.
  final MotionPreferenceController controller;

  /// The application beneath the scope.
  final Widget child;

  @override
  State<MotionScope> createState() => _MotionScopeState();
}

class _MotionScopeState extends State<MotionScope> with WidgetsBindingObserver {
  void Function()? _cancelPlatformListener;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _cancelPlatformListener = listenToPlatformReducedMotion(_platformChanged);
  }

  @override
  void dispose() {
    _cancelPlatformListener?.call();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  void _platformChanged() {
    if (mounted) setState(() {});
  }

  @override
  void didChangeAccessibilityFeatures() => _platformChanged();

  @override
  Widget build(BuildContext context) =>
      MotionPreference(controller: widget.controller, child: widget.child);
}
