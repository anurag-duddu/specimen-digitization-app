/// Progress (10 section 4.5, `UiProgress`).
library;

import 'dart:math' as math;

import 'package:flutter/widgets.dart';

import '../../foundation/motion.dart';
import '../../foundation/theme.dart';

/// The three ring diameters 10 section 4.5 names.
enum UiProgressSize {
  /// 16. Inside a button's leading slot, or beside a `label.small`.
  small(16),

  /// 24. Beside a row or an action.
  medium(24),

  /// 40. The one on a pane that has nothing else on it yet.
  large(40);

  const UiProgressSize(this.diameter);

  /// The ring's overall size in logical pixels.
  final double diameter;
}

/// Which shape a progress indicator takes.
enum UiProgressForm {
  /// A ring. Determinate draws an arc on a track; indeterminate turns.
  ring,

  /// A 4 dp capsule bar. Determinate fills from the start edge.
  bar,
}

/// The resolved paint of one progress indicator.
@immutable
class UiProgressStyle {
  /// Binds every token a progress indicator draws with.
  const UiProgressStyle({
    required this.arc,
    required this.track,
    required this.stroke,
    required this.barThickness,
    required this.catchUp,
    required this.cycle,
    required this.pulseFloor,
  });

  /// The measured part: the arc, or the filled part of the bar.
  final Color arc;

  /// The unmeasured part, behind [arc]. Determinate only: a track behind an
  /// indeterminate indicator would draw a scale for a value nobody has.
  final Color track;

  /// The ring's stroke width.
  final double stroke;

  /// The bar's height.
  final double barThickness;

  /// How long the indicator takes to reach a newly reported value.
  ///
  /// Linear and short. It smooths the jitter between two real values and
  /// never runs ahead of the last one (04 section 5.5).
  final Duration catchUp;

  /// One turn of an indeterminate indicator, and one full opacity pulse of
  /// the same indicator under reduced motion.
  final Duration cycle;

  /// The opacity an indeterminate indicator pulses down to under reduced
  /// motion, where it fades in place instead of turning.
  final double pulseFloor;

  /// The style in [ui], drawn in [color] where a caller paints its own
  /// foreground.
  ///
  /// A ring inside a filled control takes the control's foreground, because
  /// `ink` is a colour chosen against `paper` and would disappear on an
  /// `ink` fill.
  static UiProgressStyle resolve(UiThemeData ui, {Color? color}) =>
      UiProgressStyle(
        arc: color ?? ui.color.ink,
        track: ui.color.hairline,
        stroke: ui.shape.stroke.emphasis,
        barThickness: ui.space.s1,
        // `meaningful`, not `d`: a determinate indicator is the rendering of
        // a number the byte stream gave us, so removing its motion removes
        // data (04 sections 1.5 and 2.5).
        catchUp: ui.motion.meaningful(MotionTokens.standardRaw),
        // 04 section 2.2 has no token for a repeating cycle, because nothing
        // else in the catalog repeats. Composing the longest token it does
        // have keeps the value inside the token system.
        cycle: MotionTokens.slowRaw * 2,
        pulseFloor: ui.color.hoverOpacity,
      );

  /// The fraction of the bar an indeterminate segment covers.
  static const double indeterminateBarExtent = 1 / 3;

  /// Three quarters of the circle.
  ///
  /// An arc that closed would read as a determinate ring at 100 percent,
  /// which is the one thing an indeterminate indicator must not say.
  static const double indeterminateSweep = math.pi * 1.5;
}

/// Where an indeterminate indicator is in its cycle.
///
/// The reduced-motion rule for an indeterminate indicator lives here rather
/// than inside a painter, because it is a rule rather than a drawing: the
/// indicator turns, and under reduced motion it holds still and pulses its
/// opacity instead. Nothing else in the product substitutes one motion for
/// another, so the one that does says so out loud.
@immutable
class UiProgressPhase {
  /// Binds one frame of the cycle.
  const UiProgressPhase({required this.turn, required this.opacity});

  /// How far round, 0 to 1. Always 0 under reduced motion.
  final double turn;

  /// How opaque, 0 to 1. Always 1 unless motion is reduced.
  final double opacity;

  /// The frame at [t], a fraction of one cycle.
  ///
  /// [pulseFloor] is the opacity the pulse falls to and comes back from; the
  /// wave is a triangle so the indicator fades rather than snapping at the
  /// loop point.
  factory UiProgressPhase.at(
    double t, {
    required bool reduced,
    required double pulseFloor,
  }) {
    if (!reduced) return UiProgressPhase(turn: t, opacity: 1);
    final double triangle = 1 - (2 * t - 1).abs();
    return UiProgressPhase(
      turn: 0,
      opacity: pulseFloor + (1 - pulseFloor) * triangle,
    );
  }
}

/// A ring or a bar reporting how far something has got.
///
/// Retires `CircularProgressIndicator` and `LinearProgressIndicator`.
///
/// [value] is a real fraction between 0 and 1, or null when no denominator
/// exists. Determinate only when a real fraction exists; indeterminate
/// otherwise (04 section 1.5). Two rules from 04 section 5.5 are enforced
/// here rather than left to each call site:
///
///  * **Monotonic.** A reported value below the highest one seen is held at
///    the highest. A resumed upload can report a lower server offset, and a
///    bar that runs backwards reads as data loss. A genuinely new attempt is
///    a new indicator: give it its own `Key`, as a retry gets its own row.
///  * **Already complete is drawn already complete.** The first value is
///    painted where it is, with no fill animation. Replaying history as if
///    it were happening now is a lie about when it happened.
///
/// Determinate progress keeps its motion under reduced motion because the
/// motion is the information. An indeterminate indicator turns, and under
/// reduced motion pulses its opacity in place, so it still says "the server
/// has not answered" without moving.
///
/// [semanticsLabel] is required because an indicator has no visible text of
/// its own (10 section 11). The percentage is the semantics value; the counts
/// a reviewer needs ("Uploading 3 of 12") belong in the text beside it
/// (02 section 4.8).
class UiProgress extends StatefulWidget {
  /// A ring at [size].
  const UiProgress.ring({
    super.key,
    required this.semanticsLabel,
    this.value,
    this.size = UiProgressSize.medium,
    this.color,
    this.announce = false,
  }) : form = UiProgressForm.ring;

  /// A 4 dp capsule bar, as wide as the space it is given.
  const UiProgress.bar({
    super.key,
    required this.semanticsLabel,
    this.value,
    this.color,
    this.announce = false,
  }) : form = UiProgressForm.bar,
       size = UiProgressSize.medium;

  /// Which shape this indicator takes.
  final UiProgressForm form;

  /// The ring's diameter. Ignored by [UiProgress.bar], which takes its width
  /// from its parent and its height from the token.
  final UiProgressSize size;

  /// How far along, between 0 and 1. Null when no denominator exists.
  final double? value;

  /// What a screen reader reads. A complete phrase: "Upload progress", never
  /// "Progress" (02 section 4.16).
  final String semanticsLabel;

  /// Overrides the arc colour, for an indicator drawn inside a filled
  /// control.
  final Color? color;

  /// True to announce the value as it changes.
  ///
  /// Off by default: a live region on every indicator would talk over a
  /// reviewer for the length of a batch upload. The one indicator a screen
  /// reader user is waiting on sets it (06 section 3.1).
  final bool announce;

  @override
  State<UiProgress> createState() => _UiProgressState();
}

class _UiProgressState extends State<UiProgress>
    with SingleTickerProviderStateMixin {
  /// The highest fraction reported so far, or null while indeterminate.
  double? _value;

  late final AnimationController _turn = AnimationController(
    vsync: this,
    // `preserve` rather than the default: a repeating controller is the one
    // case Flutter does not compress under `disableAnimations`, and 04
    // section 2.5 says so. The reduced-motion branch in [_ring] applies the
    // policy by hand, which is the point.
    animationBehavior: AnimationBehavior.preserve,
    duration: MotionTokens.slowRaw * 2,
  );

  @override
  void initState() {
    super.initState();
    _value = _clamp(widget.value);
    _syncTicker();
  }

  @override
  void didUpdateWidget(UiProgress oldWidget) {
    super.didUpdateWidget(oldWidget);
    final double? next = _clamp(widget.value);
    if (next == null) {
      if (_value != null) setState(() => _value = null);
    } else if (_value == null || next > _value!) {
      setState(() => _value = next);
    }
    _syncTicker();
  }

  @override
  void dispose() {
    _turn.dispose();
    super.dispose();
  }

  /// An indeterminate indicator turns; a determinate one has nothing to
  /// repeat, so it holds no ticker at all.
  void _syncTicker() {
    if (_value == null) {
      if (!_turn.isAnimating) _turn.repeat();
    } else if (_turn.isAnimating) {
      _turn.stop();
    }
  }

  static double? _clamp(double? value) => value?.clamp(0, 1).toDouble();

  /// The spoken value: the percentage, or nothing while indeterminate.
  String? get _spokenValue {
    final double? fraction = _value;
    if (fraction == null) return null;
    return '${(fraction * 100).round()} percent';
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiProgressStyle style = UiProgressStyle.resolve(
      ui,
      color: widget.color,
    );
    final double? fraction = _value;
    final Widget body = fraction == null
        ? _indeterminate(ui, style)
        : TweenAnimationBuilder<double>(
            // `begin` is read on the first build only, and it equals `end`
            // there, so the first value is painted where it is: a run opened
            // half finished is drawn half finished, with no fill animation
            // (04 section 5.5). Every later build reads `end` alone and
            // catches up from whatever the last frame drew.
            tween: Tween<double>(begin: fraction, end: fraction),
            duration: style.catchUp,
            // A progress value must not ease. Easing misreports the rate.
            curve: MotionTokens.progressCurve,
            builder: (BuildContext context, double drawn, Widget? child) =>
                _determinate(style, drawn),
          );
    return Semantics(
      label: widget.semanticsLabel,
      value: _spokenValue,
      liveRegion: widget.announce,
      excludeSemantics: true,
      child: body,
    );
  }

  /// The measured form: an arc on its track, or a bar filled from the start.
  Widget _determinate(UiProgressStyle style, double fraction) =>
      switch (widget.form) {
        UiProgressForm.ring => _ringBox(
          _RingPainter(
            arc: style.arc,
            track: style.track,
            stroke: style.stroke,
            start: -math.pi / 2,
            sweep: fraction * math.pi * 2,
          ),
        ),
        UiProgressForm.bar => _barBox(
          style,
          FractionallySizedBox(
            // Directional, so the bar fills from the edge the reviewer reads
            // from in either direction.
            alignment: AlignmentDirectional.centerStart,
            widthFactor: fraction,
            child: _barFill(style, style.arc),
          ),
          track: true,
        ),
      };

  /// The unmeasured form: it turns, or pulses in place under reduced motion.
  Widget _indeterminate(UiThemeData ui, UiProgressStyle style) {
    final bool reduced = ui.motion.reduced;
    return AnimatedBuilder(
      animation: _turn,
      builder: (BuildContext context, Widget? child) {
        final UiProgressPhase phase = UiProgressPhase.at(
          _turn.value,
          reduced: reduced,
          pulseFloor: style.pulseFloor,
        );
        final Color arc = style.arc.withValues(
          alpha: style.arc.a * phase.opacity,
        );
        return switch (widget.form) {
          UiProgressForm.ring => _ringBox(
            _RingPainter(
              arc: arc,
              // No track. A track is a scale, and an indeterminate
              // indicator has no scale to draw one against.
              track: null,
              stroke: style.stroke,
              start: phase.turn * math.pi * 2,
              sweep: UiProgressStyle.indeterminateSweep,
            ),
          ),
          UiProgressForm.bar => _barBox(
            style,
            FractionallySizedBox(
              widthFactor: UiProgressStyle.indeterminateBarExtent,
              // Start to end and round again, in the reading direction. Back
              // and forth would be a value falling, which is the one thing a
              // progress indicator never does.
              alignment: AlignmentDirectional(phase.turn * 2 - 1, 0),
              child: _barFill(style, arc),
            ),
            track: false,
          ),
        };
      },
    );
  }

  Widget _ringBox(CustomPainter painter) => SizedBox.square(
    dimension: widget.size.diameter,
    child: CustomPaint(painter: painter),
  );

  /// The capsule track, with [child] laid over the whole of it.
  ///
  /// The fill is a capsule of its own rather than a clipped rectangle, so it
  /// reads as one capsule inside another and costs no save layer. The stack
  /// expands, so the track is the width the bar was given and the fill is
  /// measured against that width rather than against itself.
  Widget _barBox(UiProgressStyle style, Widget child, {required bool track}) =>
      SizedBox(
        height: style.barThickness,
        child: Stack(
          fit: StackFit.expand,
          children: <Widget>[
            if (track)
              DecoratedBox(
                decoration: ShapeDecoration(
                  shape: const StadiumBorder(),
                  color: style.track,
                ),
              ),
            child,
          ],
        ),
      );

  Widget _barFill(UiProgressStyle style, Color colour) => DecoratedBox(
    decoration: ShapeDecoration(shape: const StadiumBorder(), color: colour),
  );
}

/// Draws the ring: an optional full-circle track, then the arc over it.
class _RingPainter extends CustomPainter {
  const _RingPainter({
    required this.arc,
    required this.track,
    required this.stroke,
    required this.start,
    required this.sweep,
  });

  final Color arc;
  final Color? track;
  final double stroke;
  final double start;
  final double sweep;

  @override
  void paint(Canvas canvas, Size size) {
    final Rect bounds = Rect.fromLTWH(
      0,
      0,
      size.width,
      size.height,
    ).deflate(stroke / 2);
    final Color? trackColour = track;
    if (trackColour != null) {
      canvas.drawArc(
        bounds,
        0,
        math.pi * 2,
        false,
        Paint()
          ..color = trackColour
          ..style = PaintingStyle.stroke
          ..strokeWidth = stroke,
      );
    }
    // Nothing at all at zero. A round cap on an empty arc draws a dot, and a
    // dot on the track is a mark a reviewer reads as a value.
    if (sweep <= 0) return;
    canvas.drawArc(
      bounds,
      start,
      sweep,
      false,
      Paint()
        ..color = arc
        ..style = PaintingStyle.stroke
        ..strokeCap = StrokeCap.round
        ..strokeWidth = stroke,
    );
  }

  @override
  bool shouldRepaint(_RingPainter oldDelegate) =>
      oldDelegate.arc != arc ||
      oldDelegate.track != track ||
      oldDelegate.stroke != stroke ||
      oldDelegate.start != start ||
      oldDelegate.sweep != sweep;
}
