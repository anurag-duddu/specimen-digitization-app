/// The gauge (10 section 4.5, `UiArcIndicator`).
library;

import 'dart:math' as math;

import 'package:flutter/widgets.dart';

import '../../foundation/icons.dart';
import '../../foundation/theme.dart';
import '../../primitives/label.dart';

/// How much of the circle the arc covers.
enum UiArcSweep {
  /// 180 degrees, over the top. The flatter form, for a tile footer.
  half(math.pi, math.pi),

  /// 270 degrees, with the gap at the bottom. The fuller form, for a tile's
  /// child slot.
  threeQuarter(math.pi * 0.75, math.pi * 1.5);

  const UiArcSweep(this.start, this.sweep);

  /// Where the arc begins, in radians clockwise from 3 o'clock.
  final double start;

  /// How far it runs, in radians.
  final double sweep;
}

/// The resolved paint of one gauge.
@immutable
class UiArcIndicatorStyle {
  /// Binds every token a gauge draws with.
  const UiArcIndicatorStyle({
    required this.track,
    required this.marker,
    required this.markerCasing,
    required this.unmeasured,
    required this.stroke,
    required this.casingStroke,
    required this.markerExtent,
    required this.label,
    required this.absence,
    required this.diameter,
  });

  /// The arc itself. Thin, and decorative: the value is the marker.
  final Color track;

  /// The marker at the value.
  final Color marker;

  /// The marker's edge.
  final Color markerCasing;

  /// The glyph and the word that stand where a marker would be.
  final Color unmeasured;

  /// The arc's stroke width.
  final double stroke;

  /// The marker's edge width.
  final double casingStroke;

  /// The marker triangle's base.
  final double markerExtent;

  /// The minimum and maximum labels' type role.
  final TextStyle label;

  /// The word that replaces a marker, in a role that is not upper case.
  final TextStyle absence;

  /// The gauge's default width.
  final double diameter;

  /// The style in [ui].
  static UiArcIndicatorStyle resolve(UiThemeData ui) => UiArcIndicatorStyle(
    track: ui.color.hairline,
    marker: ui.color.accent,
    // The accent is luminous by design and measures near 1:1 on `paper`
    // (09 section 3.4). A 1 dp `ink` casing is what keeps the one graphic
    // that carries the value visible on every surface it is drawn over; the
    // same casing rule already applies to a region stroke over a photograph
    // (09 section 3.6).
    markerCasing: ui.color.ink,
    unmeasured: ui.color.inkSecondary,
    stroke: ui.shape.stroke.hairline,
    casingStroke: ui.shape.stroke.hairline,
    markerExtent: ui.space.s2,
    label: ui.type.unit.copyWith(color: ui.color.inkTertiary),
    // Not `unit`: `unit` is the one upper case role in the product
    // (09 section 4.2), and "Unmeasured" is a word, not a unit.
    absence: ui.type.label.copyWith(color: ui.color.inkSecondary),
    diameter: ui.space.s16,
  );
}

/// A thin arc with a marker at the value, or the absence of one.
///
/// Used by the `RiskMeter` pattern for the total beside its components.
///
/// A null [value] renders the `unmeasured` glyph and the word "Unmeasured"
/// where the marker would be, and draws no marker at all. A marker at zero
/// would assert a measurement nobody made, and unmeasured stays unmeasured
/// (00, principle 2). The minimum and maximum labels are dropped with it,
/// because a scale beside no value is a scale for nothing.
///
/// [semanticsLabel] is required: a gauge has no text of its own, and its
/// value is a shape (10 section 11).
class UiArcIndicator extends StatelessWidget {
  /// A gauge reading [value], a fraction between 0 and 1, or null.
  const UiArcIndicator({
    super.key,
    required this.value,
    required this.semanticsLabel,
    this.valueLabel,
    this.sweep = UiArcSweep.threeQuarter,
    this.minLabel,
    this.maxLabel,
    this.size,
  });

  /// How far along the scale, between 0 and 1. Null when nothing was
  /// measured.
  final double? value;

  /// What a screen reader reads before the value. A complete phrase: "Risk",
  /// never the bare number (02 section 4.16).
  final String semanticsLabel;

  /// The spoken form of the value, where the fraction reads badly aloud.
  ///
  /// "62 of 100" rather than "62 percent", for instance: a score is stated
  /// out of one hundred and never as a percentage (02 section 4.14).
  final String? valueLabel;

  /// How much of the circle the arc covers.
  final UiArcSweep sweep;

  /// The bottom of the scale, in the `unit` role.
  final String? minLabel;

  /// The top of the scale, in the `unit` role.
  final String? maxLabel;

  /// The gauge's width. Defaults to the token in the style.
  final double? size;

  /// The word that stands in for a marker when nothing was measured.
  static const String unmeasuredLabel = 'Unmeasured';

  /// The same absence, in the middle of a spoken sentence.
  static const String unmeasuredValue = 'unmeasured';

  /// The spoken value: the caller's wording, the percentage, or the absence.
  String _spokenValue() {
    final double? fraction = value;
    if (fraction == null) return unmeasuredValue;
    return valueLabel ?? '${(fraction.clamp(0, 1) * 100).round()} percent';
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiArcIndicatorStyle style = UiArcIndicatorStyle.resolve(ui);
    final double width = size ?? style.diameter;
    final double? fraction = value?.clamp(0, 1).toDouble();
    final String? min = minLabel;
    final String? max = maxLabel;

    return Semantics(
      label: semanticsLabel,
      value: _spokenValue(),
      excludeSemantics: true,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: <Widget>[
          SizedBox(
            width: width,
            // The half form needs only the top of the circle plus room for
            // the marker, so it does not carry an empty square around with
            // it.
            height: sweep == UiArcSweep.half ? width / 2 + style.stroke : width,
            child: CustomPaint(
              painter: _ArcPainter(style: style, sweep: sweep, value: fraction),
              child: fraction == null
                  ? Center(
                      child: UiIcon(
                        UiIcons.unmeasured,
                        size: UiIconSize.inline,
                        color: style.unmeasured,
                      ),
                    )
                  : null,
            ),
          ),
          if (fraction == null)
            Padding(
              padding: EdgeInsetsDirectional.only(top: ui.space.s1),
              child: UiLabel(unmeasuredLabel, style: style.absence),
            )
          else if (min != null || max != null)
            Padding(
              padding: EdgeInsetsDirectional.only(top: ui.space.s1),
              child: SizedBox(
                width: width,
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: <Widget>[
                    Flexible(child: UiLabel(min ?? '', style: style.label)),
                    Flexible(child: UiLabel(max ?? '', style: style.label)),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// Draws the track, and the marker where there is a value.
class _ArcPainter extends CustomPainter {
  const _ArcPainter({
    required this.style,
    required this.sweep,
    required this.value,
  });

  final UiArcIndicatorStyle style;
  final UiArcSweep sweep;
  final double? value;

  @override
  void paint(Canvas canvas, Size size) {
    // The circle the arc sits on is as wide as the box and centred on it,
    // which for the half form puts its centre on the bottom edge.
    final double radius = (size.width - style.stroke) / 2;
    final Offset centre = Offset(
      size.width / 2,
      sweep == UiArcSweep.half ? size.height - style.stroke / 2 : size.width / 2,
    );
    final Rect bounds = Rect.fromCircle(center: centre, radius: radius);
    canvas.drawArc(
      bounds,
      sweep.start,
      sweep.sweep,
      false,
      Paint()
        ..color = style.track
        ..style = PaintingStyle.stroke
        ..strokeCap = StrokeCap.round
        ..strokeWidth = style.stroke,
    );

    final double? fraction = value;
    if (fraction == null) return;

    final double angle = sweep.start + sweep.sweep * fraction;
    final Offset at = centre + Offset(math.cos(angle), math.sin(angle)) * radius;
    // The tip sits on the arc and the base falls away inside it, so the
    // marker points at the value without covering the scale it is read
    // against and without reaching outside the box the gauge was given.
    final Path marker = Path()
      ..moveTo(at.dx, at.dy)
      ..lineTo(
        at.dx - math.cos(angle - _markerSpread) * style.markerExtent,
        at.dy - math.sin(angle - _markerSpread) * style.markerExtent,
      )
      ..lineTo(
        at.dx - math.cos(angle + _markerSpread) * style.markerExtent,
        at.dy - math.sin(angle + _markerSpread) * style.markerExtent,
      )
      ..close();
    canvas
      ..drawPath(
        marker,
        Paint()
          ..color = style.marker
          ..style = PaintingStyle.fill,
      )
      ..drawPath(
        marker,
        Paint()
          ..color = style.markerCasing
          ..style = PaintingStyle.stroke
          ..strokeWidth = style.casingStroke
          ..strokeJoin = StrokeJoin.round,
      );
  }

  /// How far the two outer points of the marker sit from the radius through
  /// its tip. A third of a right angle gives a triangle that reads as a
  /// pointer rather than as a wedge.
  static const double _markerSpread = math.pi / 6;

  @override
  bool shouldRepaint(_ArcPainter oldDelegate) =>
      oldDelegate.value != value ||
      oldDelegate.sweep != sweep ||
      oldDelegate.style.marker != style.marker ||
      oldDelegate.style.track != style.track;
}
